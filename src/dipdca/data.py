"""
Data loading. Nothing is committed to the repo: every series is fetched from its
public source at run time and cached under data/cache/ (git-ignored).  A manifest
(data/cache/MANIFEST.json) records when and from where each file was fetched, plus a
checksum, so a published result can be traced back to the exact bytes it ran on.

Sources (see METHODOLOGY.md for the licensing notes):
  * Yahoo Finance via yfinance  - XIU.TO (CAD ETF, price + dividends), ^SP500TR (S&P 500
                                  total-return index, USD).  Personal-use data: fetched
                                  at run time, never redistributed by this repo.
  * Bank of Canada Valet API    - 3-month Government of Canada T-bill yield (daily, 2001+).
                                  Reuse allowed with attribution.
  * FRED (St. Louis Fed)        - DEXCAUS (CAD per USD, Federal Reserve H.10, 1971+) and
                                  INTGSTCAM193N (Canadian T-bill rate, IMF, monthly, to 2017)
                                  used only to fill cash rates before the BoC series begins.
  * Kenneth French Data Library - CRSP US market + 1-month T-bill, daily/monthly from 1926
                                  (used for the long-history USD sanity check only).
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "cache"
MANIFEST = CACHE / "MANIFEST.json"

FRENCH_BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
BOC_URL = "https://www.bankofcanada.ca/valet/observations/{series}/csv?order_dir=asc"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
UA = {"User-Agent": "sharpe-dca-vs-dip/1.0 (research code; github.com/Sharpe123321/sharpe-buy-the-dip-vs-dca)"}


# --------------------------------------------------------------------------- caching
def _record(name: str, path: Path, source: str, df: pd.DataFrame | pd.Series) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    manifest[name] = {
        "source": source,
        "fetched_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rows": int(len(df)),
        "first": str(df.index.min().date()),
        "last": str(df.index.max().date()),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True))


def _get(url: str, tries: int = 3, **kw) -> requests.Response:
    last = None
    for k in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=60, **kw)
            r.raise_for_status()
            return r
        except Exception as exc:  # noqa: BLE001 - retry any transport error
            last = exc
            time.sleep(2 * (k + 1))
    raise RuntimeError(f"could not fetch {url}: {last}")


def _cached(name: str, refresh: bool, fetch, source: str) -> pd.DataFrame:
    path = CACHE / f"{name}.csv"
    if refresh or not path.exists():
        df = fetch()
        CACHE.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index_label="date")
        _record(name, path, source, df)
    df = pd.read_csv(path, index_col="date", parse_dates=True)
    df.index = pd.DatetimeIndex(df.index).normalize()
    return df


# --------------------------------------------------------------------------- Yahoo
def load_yahoo(ticker: str, refresh: bool = False) -> pd.DataFrame:
    """Daily Close (split-adjusted, NOT dividend-adjusted), Adj Close and Dividends."""

    def fetch() -> pd.DataFrame:
        import yfinance as yf

        raw = yf.Ticker(ticker).history(period="max", auto_adjust=False, actions=True)
        if raw.empty:
            raise RuntimeError(f"Yahoo returned no data for {ticker}")
        idx = raw.index.tz_localize(None) if raw.index.tz is not None else raw.index
        out = pd.DataFrame(
            {
                "close": raw["Close"].to_numpy(),
                "adj_close": raw["Adj Close"].to_numpy(),
                "dividends": raw["Dividends"].to_numpy(),
            },
            index=pd.DatetimeIndex(idx).normalize(),
        )
        return out[~out.index.duplicated(keep="last")].sort_index()

    return _cached("yahoo_" + ticker.replace("^", "idx_"), refresh, fetch, f"Yahoo Finance via yfinance ({ticker})")


def total_return_index(close: pd.Series, dividends: pd.Series) -> pd.Series:
    """
    Dividend-reinvested index built from raw closes and cash dividends:

        TR_t = TR_{t-1} * (Close_t + Div_t) / Close_{t-1}

    i.e. each dividend is reinvested in the same security at the ex-date close.  This is
    the same arithmetic as Yahoo's 'Adj Close' and is checked against it in the data audit.
    """
    div = dividends.reindex(close.index).fillna(0.0)
    if abs(div.sum() - dividends.fillna(0.0).sum()) > 1e-9:
        raise ValueError("dividends fall on dates with no price - cannot build total return")
    ret = (close + div) / close.shift(1) - 1.0
    ret.iloc[0] = 0.0
    return 100.0 * (1.0 + ret).cumprod()


# --------------------------------------------------------------------------- BoC / FRED
def load_boc(series: str, refresh: bool = False) -> pd.Series:
    def fetch() -> pd.DataFrame:
        text = _get(BOC_URL.format(series=series)).text
        lines = text.splitlines()
        start = next(i for i, ln in enumerate(lines) if ln.startswith('"date"'))
        df = pd.read_csv(io.StringIO("\n".join(lines[start:])), parse_dates=["date"], index_col="date")
        df.columns = ["value"]
        return df

    df = _cached("boc_" + series, refresh, fetch, f"Bank of Canada Valet API ({series})")
    return df["value"].astype(float).dropna()


def load_fred(series: str, refresh: bool = False) -> pd.Series:
    def fetch() -> pd.DataFrame:
        df = pd.read_csv(io.StringIO(_get(FRED_URL.format(series=series)).text), na_values=["."])
        df.columns = ["date", "value"]
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date")

    df = _cached("fred_" + series, refresh, fetch, f"FRED ({series})")
    return df["value"].astype(float).dropna()


def deflate_monthly(index_values: np.ndarray, month_end_dates: pd.DatetimeIndex, cpi: pd.Series) -> np.ndarray:
    """
    Convert a MONTHLY nominal index to real terms: value_t / (CPI_t / CPI_0), using the CPI of the
    calendar month each observation belongs to (FRED stamps CPI with the 1st of its month).
    Note the CPI for month t is published mid-month t+1, so a real series carries a small
    look-ahead; it is used only for the Maggiulli replication, which is itself a hindsight test.
    """
    per = cpi.copy()
    per.index = per.index.to_period("M")
    full = pd.period_range(per.index.min(), per.index.max(), freq="M")
    # BLS did not publish October 2025 CPI (US federal shutdown): fill SINGLE-month holes by
    # log-linear interpolation between the neighbouring months; any longer gap is an error.
    per = np.exp(np.log(per.reindex(full)).interpolate(limit=1, limit_area="inside"))
    c = per.reindex(pd.DatetimeIndex(month_end_dates).to_period("M")).to_numpy(dtype=float)
    if np.isnan(c).any():
        raise ValueError("CPI missing for some months")
    return np.asarray(index_values, dtype=float) / (c / c[0])


# --------------------------------------------------------------------------- French
def _french_zip(name: str, refresh: bool) -> list[str]:
    path = CACHE / f"french_{name}"          # `name` already ends in .zip
    if refresh or not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_get(FRENCH_BASE + name).content)
        manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
        manifest[path.name] = {
            "source": "Kenneth French Data Library (CRSP)",
            "fetched_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    z = zipfile.ZipFile(path)
    return z.read(z.namelist()[0]).decode("latin-1").splitlines()


def load_french(freq: str = "daily", refresh: bool = False) -> pd.DataFrame:
    """
    Fama/French 3-factor file.  Returns DECIMAL returns: mkt (=Mkt-RF+RF, the CRSP
    value-weighted US total market return incl. dividends) and rf (1-month T-bill).
    Monthly rows are labelled with the month-END date.
    """
    fname = {"daily": "F-F_Research_Data_Factors_daily_CSV.zip", "monthly": "F-F_Research_Data_Factors_CSV.zip"}.get(freq)
    if fname is None:
        raise ValueError(freq)
    return parse_french(_french_zip(fname, refresh), freq)


def parse_french(lines: list[str], freq: str) -> pd.DataFrame:
    """Parse the text of a French 3-factor CSV (pure function, unit-tested)."""
    if freq == "daily":
        pat, fmt = re.compile(r"^\s*(\d{8})\s*,"), "%Y%m%d"
    elif freq == "monthly":
        pat, fmt = re.compile(r"^\s*(\d{6})\s*,"), "%Y%m"
    else:
        raise ValueError(freq)
    rows = []
    for ln in lines:
        m = pat.match(ln)
        if m:  # the monthly file also holds an annual block (4-digit years) - the regex skips it
            parts = [p.strip() for p in ln.split(",")]
            rows.append((m.group(1), float(parts[1]), float(parts[4])))
    df = pd.DataFrame(rows, columns=["date", "mktrf", "rf"])
    df["date"] = pd.to_datetime(df["date"], format=fmt)
    if freq == "monthly":
        df["date"] = df["date"] + pd.offsets.MonthEnd(0)
    df = df.set_index("date").sort_index()
    df[df <= -99.0] = np.nan  # French's missing-data sentinels (-99.99 / -999)
    if df.isna().any().any():
        raise ValueError("French file contains missing values in the factors used here")
    out = pd.DataFrame({"mkt": (df["mktrf"] + df["rf"]) / 100.0, "rf": df["rf"] / 100.0})
    if len(out) and not out.index.is_unique:
        raise ValueError("duplicate dates in French file")
    return out


# --------------------------------------------------------------------------- cash
def tbill_rate_series(refresh: bool = False) -> tuple[pd.Series, dict]:
    """
    Daily 'as-published' Canadian 3-month T-bill yield (% p.a.).
    Bank of Canada daily series from 2001-01-02.  Before that, the FRED/IMF monthly T-bill
    rate, with each month's value only available from the 1st of the FOLLOWING month
    (no look-ahead inside the month).  The splice is validated against the overlap in
    scripts/audit_data.py.
    """
    boc = load_boc("TB.CDN.90D.MID", refresh)
    fred = load_fred("INTGSTCAM193N", refresh)
    fred_avail = fred.copy()
    fred_avail.index = fred_avail.index + pd.offsets.MonthBegin(1)  # known from next month's 1st
    first_boc = boc.index.min()
    early = fred_avail[fred_avail.index < first_boc]
    series = pd.concat([early, boc]).sort_index()
    series = series[~series.index.duplicated(keep="last")]
    return series, {"boc_first": str(first_boc.date()), "fred_last": str(fred.index.max().date())}


def cash_growth_index(dates: pd.DatetimeIndex, rate_pct: pd.Series) -> np.ndarray:
    """
    Growth index of cash held between trading days.  For the interval (d_{i-1}, d_i] the
    rate used is the latest one published on or BEFORE d_{i-1} (no look-ahead), applied as
    simple actual/365 interest:  factor_i = 1 + r_{i-1} * (days_i - days_{i-1}) / 365.
    """
    r = rate_pct.sort_index().reindex(rate_pct.index.union(dates)).ffill().reindex(dates)
    if r.isna().any():
        raise ValueError(f"no cash rate available on/before {r[r.isna()].index[0].date()}")
    days = dates.to_numpy().astype("datetime64[D]").astype(np.int64)
    factor = np.ones(len(dates))
    factor[1:] = 1.0 + (r.to_numpy()[:-1] / 100.0) * (np.diff(days) / 365.0)
    return np.cumprod(factor)


def cash_growth_index_from_returns(period_rf: np.ndarray) -> np.ndarray:
    """Cash index from per-period (daily or monthly) risk-free returns; element 0 is the base."""
    f = np.ones(len(period_rf))
    f[1:] = 1.0 + period_rf[1:]
    return np.cumprod(f)
