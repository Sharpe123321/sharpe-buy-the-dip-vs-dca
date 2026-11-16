"""
Guard: is any third-party market data (Yahoo, FRED, Bank of Canada, Kenneth French) in this repository?

Run it after `python run_all.py` (it needs the downloaded provider files in data/cache/ to compare against):

    python scripts/check_no_raw_data.py

It exits non-zero if anything looks like provider data.  The checks:

  1. exact copies     sha256 of every provider file in data/cache/ against every file EVER committed (all history)
  2. verbatim values  long-precision numbers from the provider files, searched for in every tracked file
  3. hidden series    every dated numeric column of every tracked CSV compared with every provider series:
                      return correlation, exact return matches, constant level ratio.  A portfolio's value series
                      fails this test on purpose: its daily returns equal the underlying price's returns, so it
                      contains the price path in disguise.
  4. forbidden paths  nothing tracked under data/, data_cache/ or local_only/, and no zip/parquet/xlsx/feather files
  5. embedded tables  long runs of numbers inside code or docs

Why: Yahoo's terms allow personal use only, so this repository must not redistribute its data, including data that
is trivially recoverable from derived files.  This script is a safety net, not legal advice.
"""
from __future__ import annotations

import glob
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], capture_output=True, check=True).stdout


def main() -> int:
    tracked = git("ls-files").decode().split()
    raw_files = [f for f in glob.glob("data/cache/*") if os.path.basename(f) != "MANIFEST.json"]
    if not raw_files:
        print("data/cache/ is empty: run `python run_all.py` first, so there is something to compare against.")
        return 2
    problems: list[str] = []
    print(f"{len(tracked)} tracked files; {len(raw_files)} provider files in data/cache/ to compare against\n")

    # 1. exact copies, across all history
    raw_hash = {}
    for f in raw_files:
        b = open(f, "rb").read()
        for v in (b, b.replace(b"\r\n", b"\n"), b.replace(b"\n", b"\r\n")):
            raw_hash[hashlib.sha256(v).hexdigest()] = os.path.basename(f)
    n_blobs = 0
    for line in git("rev-list", "--objects", "--all").decode().splitlines():
        if " " not in line:
            continue
        sha, name = line.split(" ", 1)
        if git("cat-file", "-t", sha).decode().strip() != "blob":
            continue
        n_blobs += 1
        h = hashlib.sha256(git("cat-file", "blob", sha)).hexdigest()
        if h in raw_hash:
            problems.append(f"exact copy of provider file {raw_hash[h]} committed as {name}")
    print(f"1. exact copies of provider files: {n_blobs} blobs in all history checked")

    # 2. verbatim long-precision values
    tok = re.compile(r"\d+\.\d{8,}")
    raw_tokens: set[str] = set()
    for f in raw_files:
        if f.endswith(".csv"):
            raw_tokens |= set(tok.findall(open(f, encoding="utf-8", errors="ignore").read()))
    for f in tracked:
        if f.endswith(".png"):
            continue
        hit = set(tok.findall(open(f, encoding="utf-8", errors="ignore").read())) & raw_tokens
        if hit:
            problems.append(f"{f} contains {len(hit)} long-precision number(s) that appear verbatim in provider files")
    print(f"2. verbatim values: {len(raw_tokens):,} long-precision provider numbers searched for")

    # 3. hidden series in dated CSVs
    raw: dict[str, pd.Series] = {}
    for f in glob.glob("data/cache/*.csv"):
        df = pd.read_csv(f)
        idx = pd.to_datetime(df.iloc[:, 0], errors="coerce", utc=True).dt.tz_localize(None).dt.normalize()
        for c in df.columns[1:]:
            s = pd.Series(pd.to_numeric(df[c], errors="coerce").values, index=idx).dropna()
            s = s[~s.index.duplicated()]
            if len(s) > 50 and s.nunique() > 20:
                raw[f"{os.path.basename(f)[:-4]}:{c}"] = s
    n_cols = 0
    for f in tracked:
        if not f.endswith(".csv"):
            continue
        df = pd.read_csv(f)
        if "date" not in df.columns:
            continue
        d = pd.to_datetime(df["date"])
        for c in df.select_dtypes("number").columns:
            n_cols += 1
            s = pd.Series(df[c].values, index=d)
            s = s[~s.index.duplicated()]
            for name, R in raw.items():
                common = s.index.intersection(R.index)
                if len(common) < 50:
                    continue
                x, y = s.loc[common], R.loc[common]
                rx = x.pct_change().replace([np.inf, -np.inf], np.nan)
                ry = y.pct_change().replace([np.inf, -np.inf], np.nan)
                m = rx.notna() & ry.notna()
                if m.sum() < 50:
                    continue
                corr = rx[m].corr(ry[m])
                exact = float((abs(rx[m] - ry[m]) < 1e-9).mean())
                ok = (x > 0) & (y > 0)
                cv = (x / y)[ok].std() / (x / y)[ok].mean() if ok.sum() > 50 else np.nan
                if corr > 0.9 or exact > 0.05 or (cv == cv and cv < 0.02):
                    problems.append(f"{f} :: {c} tracks provider series {name} "
                                    f"(return corr {corr:.3f}, exact return matches {exact:.0%}, level-ratio CV {cv:.3f})")
    print(f"3. hidden series: {n_cols} dated numeric columns compared with {len(raw)} provider series")

    # 4. forbidden paths
    # known outputs from which the provider series can be rebuilt (found by test; they live in local_only/ instead)
    series_like = ("windows_primary.csv", "chart_growth_spy_timeseries", "chart_growth_spy_dip20_purchases")
    bad = [f for f in tracked if f.startswith(("data/", "data_cache/", "local_only/")) or f.endswith((".zip", ".parquet", ".xlsx", ".feather"))
           or any(n in f for n in series_like)]
    problems += [f"forbidden path tracked: {f}" for f in bad]
    print(f"4. forbidden paths: {len(bad)} tracked")

    # 5. embedded number tables in code/docs
    run = re.compile(r"(?:-?\d+\.?\d*\s*,\s*){12,}")
    n_emb = 0
    for f in tracked:
        if f.endswith((".py", ".md", ".toml", ".txt")):
            for m in run.finditer(open(f, encoding="utf-8", errors="ignore").read()):
                n_emb += 1
                problems.append(f"{f} embeds a table of numbers: {m.group(0)[:50]}...")
    print(f"5. embedded number tables in code/docs: {n_emb}")

    print()
    if problems:
        print("PROBLEMS:")
        for p in problems:
            print("  -", p)
        return 1
    print("OK: nothing in this repository looks like third-party market data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
