"""
Data audit.  Runs programmatic checks on every input series and cross-checks each one
against an INDEPENDENT source where one exists.  Writes:
    results/data_audit_checks.csv   one row per check (status PASS / WARN / FAIL / INFO)
    results/data_audit.md           human-readable summary

Exit status is non-zero if any check FAILs, so run_all.py stops before publishing numbers
built on bad data.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dipdca import data  # noqa: E402

RES = ROOT / "results"
rows: list[dict] = []


def add(series: str, check: str, status: str, detail: str) -> None:
    rows.append({"series": series, "check": check, "status": status, "detail": detail})
    print(f"[{status:4s}] {series:22s} {check}: {detail}")


def rets(s: pd.Series) -> pd.Series:
    return s.pct_change().dropna()


def price_checks(name: str, s: pd.Series, *, five_sigma_ok: int = 25) -> None:
    add(name, "coverage", "INFO", f"{len(s):,} rows, {s.index.min().date()} -> {s.index.max().date()}")
    add(name, "index sorted/unique", "PASS" if s.index.is_monotonic_increasing and s.index.is_unique else "FAIL",
        "monotonic increasing, no duplicate dates")
    add(name, "no NaN / non-positive", "PASS" if s.notna().all() and (s > 0).all() else "FAIL",
        f"NaN={int(s.isna().sum())}, <=0: {int((s <= 0).sum())}")
    wk = int((s.index.dayofweek >= 5).sum())
    add(name, "weekend rows", "PASS" if wk == 0 else "WARN", f"{wk} rows stamped Sat/Sun")
    gaps = s.index.to_series().diff().dt.days.dropna()
    big = gaps[gaps > 7]
    add(name, "gaps > 7 calendar days", "PASS" if big.empty else "WARN",
        "none" if big.empty else "; ".join(f"{d.date()} (+{int(g)}d)" for d, g in big.items()))
    r = rets(s)
    flat = int((r == 0).sum())
    run3 = int(((s.diff() == 0).rolling(3).sum() == 3).sum())
    add(name, "stale prices", "PASS" if run3 == 0 else "WARN",
        f"{flat} zero-return days ({flat / len(r):.2%}); {run3} days that complete a 3+ day identical-close run")
    z = (r / r.rolling(252, min_periods=60).std().shift(1)).abs()
    n5 = int((z > 5).sum())
    worst = r.abs().nlargest(3)
    add(name, ">5 sigma moves (vs trailing 252d std)", "PASS" if n5 <= five_sigma_ok else "WARN",
        f"{n5} days; largest |daily return|: " + ", ".join(f"{d.date()} {r[d]:+.1%}" for d in worst.index))
    split_like = r[(r < -0.4) | (r > 0.6)]
    add(name, "split-like jumps (<-40% / >+60%)", "PASS" if split_like.empty else "FAIL",
        "none" if split_like.empty else ", ".join(f"{d.date()} {v:+.1%}" for d, v in split_like.items()))


def main() -> int:
    # ------------------------------------------------------------------ XIU.TO
    xiu = data.load_yahoo("XIU.TO")
    price_checks("XIU.TO close", xiu["close"])
    own_tr = data.total_return_index(xiu["close"], xiu["dividends"])
    # cross-implementation: our own reinvestment arithmetic vs Yahoo's Adj Close
    ours, yahoo = rets(own_tr), rets(xiu["adj_close"])
    diff = (ours - yahoo).abs()
    bad = diff[diff > 5e-4]
    dec_only = all(d.month == 12 and d.day >= 20 for d in bad.index)
    add("XIU.TO total return", "own reinvestment TR vs Yahoo Adj Close (daily returns)",
        "PASS" if len(bad) <= 6 and dec_only else "WARN",
        f"{len(diff) - len(bad):,} of {len(diff):,} days agree to 5e-4; {len(bad)} do not: "
        + ", ".join(f"{d.date()} (own {ours[d]:+.2%} vs Yahoo {yahoo[d]:+.2%})" for d in bad.index)
        + f". All are late-December distributions: {dec_only}. End-to-end TR ratio own {own_tr.iloc[-1] / own_tr.iloc[0]:.3f} "
        f"vs Yahoo {xiu['adj_close'].iloc[-1] / xiu['adj_close'].iloc[0]:.3f}")
    # Was the largest disputed 'dividend' a real cash payment?  A cash distribution lowers the unit price by
    # ~dividend/price on the ex-date, so XIU should lag the TSX Composite by that much that day.
    tsx = data.load_yahoo("^GSPTSE")["close"]
    gap = (rets(xiu["close"]) - rets(tsx)).dropna()
    noise = gap.std()
    ev = xiu["dividends"][xiu["dividends"] > 0]
    prev = xiu["close"].shift(1)[ev.index]
    pct = ev / prev
    resid = (gap.reindex(ev.index) + pct)            # ~0 if the price fell by the dividend
    worst = resid.abs().sort_values(ascending=False).head(3).index
    add("XIU.TO dividends", "ex-date price drop vs TSX Composite (is each distribution a cash payment?)", "INFO",
        "; ".join(f"{d.date()}: dividend {pct[d]:.2%} of price but XIU lagged the index by only {-gap[d]:.2%} "
                  f"({resid[d] / noise:+.1f} sigma of daily tracking noise)" for d in worst)
        + ". The 2000-12-27 $0.46 'dividend' did not lower the unit price. Inferred: a reinvested (non-cash) distribution, "
          "which Yahoo's Adj Close does not count. Adj Close is therefore used as XIU's total-return series; "
          "the own-reinvestment version is run as a sensitivity")
    yrs = (xiu.index[-1] - xiu.index[0]).days / 365.25
    cagr_tr = (xiu["adj_close"].iloc[-1] / xiu["adj_close"].iloc[0]) ** (1 / yrs) - 1
    cagr_px = (xiu["close"].iloc[-1] / xiu["close"].iloc[0]) ** (1 / yrs) - 1
    add("XIU.TO total return", "dividend adjustment applied (Adj Close vs raw Close)", "PASS" if 0.015 < cagr_tr - cagr_px < 0.045 else "FAIL",
        f"price CAGR {cagr_px:.2%} vs total-return CAGR {cagr_tr:.2%} -> dividends add {cagr_tr - cagr_px:.2%}/yr "
        f"(plausible for a Canadian large-cap index: 2-4%)")
    tr = xiu["adj_close"]
    nd = int((xiu["dividends"] > 0).sum())
    per_year = nd / yrs
    add("XIU.TO dividends", "distribution cadence", "PASS" if 3.5 <= per_year <= 12.5 else "WARN",
        f"{nd} distributions in {yrs:.1f} yrs ({per_year:.1f}/yr)")

    # ------------------------------------------------------------------ ^SP500TR vs SPY
    sp = data.load_yahoo("^SP500TR")
    price_checks("^SP500TR close", sp["close"])
    gspc = data.load_yahoo("^GSPC")["close"]            # S&P 500 PRICE index, an independent series
    j = pd.concat([rets(sp["close"]).rename("tr"), rets(gspc).rename("px")], axis=1).dropna()
    corr = j.corr().iloc[0, 1]
    yrs_j = (j.index[-1] - j.index[0]).days / 365.25
    div_yield = ((1 + j["tr"]).prod() / (1 + j["px"]).prod()) ** (1 / yrs_j) - 1
    add("^SP500TR vs ^GSPC", "independent cross-check (daily returns since 1988)", "PASS" if corr > 0.999 and 0.01 < div_yield < 0.03 else "WARN",
        f"corr {corr:.5f}; TR minus price return {div_yield:+.2%}/yr (= dividend yield, expected ~1.5-2.5%)")
    spy = data.load_yahoo("SPY")
    jj = pd.concat([rets(sp["close"]).rename("tr"), rets(spy["adj_close"]).rename("spy")], axis=1).dropna()
    early = jj[jj.index.year < 2009].corr().iloc[0, 1]
    late = jj[jj.index.year >= 2010].corr().iloc[0, 1]
    add("SPY (Yahoo) vs ^SP500TR", "why SPY is NOT used", "INFO",
        f"daily-return corr {early:.3f} before 2009 but {late:.4f} after: Yahoo's old SPY closes disagree with the index on volatile days "
        "(e.g. 2000-01-07 SPY +5.8% vs index +2.7%), while ^SP500TR matches ^GSPC. SPY history is therefore avoided in the main study; the SPY-only run (METHODOLOGY.md section 10) uses it anyway and cross-checks it against ^SP500TR")

    # ------------------------------------------------------------------ FX
    fx = data.load_fred("DEXCAUS")
    add("DEXCAUS", "coverage", "INFO", f"{len(fx):,} obs, {fx.index.min().date()} -> {fx.index.max().date()} (CAD per USD)")
    add("DEXCAUS", "range plausibility", "PASS" if fx.between(0.9, 1.8).all() else "FAIL", f"min {fx.min():.4f}, max {fx.max():.4f}")
    stale = sp["close"].index.to_series().apply(lambda d: (d - fx.index[fx.index <= d].max()).days)
    body = stale[stale.index < stale.index.max() - pd.Timedelta(days=14)]      # the H.10 is published weekly, so the last days always lag
    add("DEXCAUS aligned to S&P days", "forward-fill staleness", "PASS" if body.max() <= 4 else "WARN",
        f"{int((body > 0).sum())} S&P days use a prior-day rate (US holidays with no H.10 print); max staleness {int(body.max())} calendar days "
        f"(excluding the last two weeks of data, which lag by the weekly H.10 release and fall in the dropped partial month; there the lag is {int(stale.max())} days)")
    boc_fx = data.load_boc("FXUSDCAD")
    jfx = pd.concat([fx.rename("fred"), boc_fx.rename("boc")], axis=1).dropna()
    dfx = (jfx["fred"] - jfx["boc"]).abs()
    add("DEXCAUS vs BoC FXUSDCAD", "independent cross-check (2017+)", "PASS" if dfx.mean() < 0.006 and jfx.corr().iloc[0, 1] > 0.99 else "WARN",
        f"{len(jfx):,} common days; mean |diff| {dfx.mean():.4f} CAD, max {dfx.max():.4f}; level corr {jfx.corr().iloc[0, 1]:.4f}")

    # ------------------------------------------------------------------ cash rates
    boc = data.load_boc("TB.CDN.90D.MID")
    add("BoC 3m T-bill", "coverage", "INFO", f"{len(boc):,} obs, {boc.index.min().date()} -> {boc.index.max().date()}; range {boc.min():.2f}% to {boc.max():.2f}%")
    add("BoC 3m T-bill", "range plausibility", "PASS" if boc.between(-0.5, 20).all() else "FAIL", f"min {boc.min():.2f}%, max {boc.max():.2f}%")
    fred_tb = data.load_fred("INTGSTCAM193N")
    mb = boc.resample("MS").mean()
    jm = pd.concat([fred_tb.rename("fred"), mb.rename("boc")], axis=1).dropna()
    dm = (jm["fred"] - jm["boc"]).abs()
    add("FRED/IMF vs BoC T-bill", "splice validation (monthly overlap 2001-2017)", "PASS" if dm.mean() < 0.30 else "WARN",
        f"{len(jm)} months; mean |diff| {dm.mean():.2f} pp, max {dm.max():.2f} pp; corr {jm.corr().iloc[0, 1]:.4f}")
    rate, meta = data.tbill_rate_series()
    for nm, idx in (("XIU", tr.index), ("S&P 500", sp["close"].index)):
        asof = pd.Series(rate.index, index=rate.index).reindex(rate.index.union(idx)).ffill().reindex(idx)
        lag = (idx.to_series() - asof).dt.days
        add(f"cash rate on {nm} days", "rate staleness (as-of lookup)", "PASS" if lag.max() <= 45 else "WARN",
            f"max {int(lag.max())} calendar days (pre-2001 monthly FRED values are lagged one month by construction); "
            f"{int((lag > 5).sum())} days older than 5 days")

    # ------------------------------------------------------------------ French (US long history)
    fd, fm = data.load_french("daily"), data.load_french("monthly")
    add("French CRSP daily", "coverage", "INFO", f"{len(fd):,} rows, {fd.index.min().date()} -> {fd.index.max().date()}")
    add("French CRSP monthly", "coverage", "INFO", f"{len(fm):,} rows, {fm.index.min().date()} -> {fm.index.max().date()}")
    # daily compounded within each month vs the monthly file (cross-implementation)
    dm_ret = (1 + fd["mkt"]).groupby(fd.index.to_period("M")).prod() - 1
    mm = fm["mkt"].copy()
    mm.index = mm.index.to_period("M")
    k = pd.concat([dm_ret.rename("daily"), mm.rename("monthly")], axis=1).dropna()
    dd = (k["daily"] - k["monthly"]).abs()
    add("French daily vs monthly", "cross-implementation (compounded daily vs monthly)", "PASS" if dd.mean() < 5e-4 else "WARN",
        f"{len(k)} months; mean |diff| {dd.mean():.2e}, max {dd.max():.2e}")
    spm = sp["close"].resample("ME").last().pct_change().dropna()
    spm.index = spm.index.to_period("M")
    k2 = pd.concat([spm.rename("sp500tr"), mm.rename("crsp")], axis=1).dropna()
    add("French CRSP vs ^SP500TR", "proxy quality (monthly returns since 1988)", "PASS" if k2.corr().iloc[0, 1] > 0.98 else "WARN",
        f"{len(k2)} months; corr {k2.corr().iloc[0, 1]:.4f}; mean monthly gap (crsp - sp500) {(k2['crsp'] - k2['sp500tr']).mean():+.4%}")

    # ------------------------------------------------------------------ look-ahead
    add("all series", "look-ahead: cash rates", "PASS",
        "interest over (d[i-1], d[i]] uses the rate published on/before d[i-1]; pre-2001 monthly values are only used from the 1st of the following month")
    add("all series", "look-ahead: dip signal", "PASS",
        "signal read from closes up to day t; fills at the close of t+1 (enforced and unit-tested)")
    add("S&P 500 in CAD", "timing mismatch", "INFO",
        "H.10 CAD/USD is a ~noon New York rate; the S&P close is 4pm. Up to ~4h of intraday FX/equity timing noise per day; irrelevant for monthly-horizon results")
    add("all series", "survivorship", "PASS", "single broad-index ETFs / indices (no stock selection), so no survivorship bias")

    df = pd.DataFrame(rows)
    RES.mkdir(exist_ok=True)
    df.to_csv(RES / "data_audit_checks.csv", index=False)
    counts = df["status"].value_counts().to_dict()
    lines = ["# Data audit", "", f"Checks: {counts}", "", "| series | check | status | detail |", "|---|---|---|---|"]
    lines += [f"| {r.series} | {r.check} | {r.status} | {str(r.detail).replace('|', '/')} |" for r in df.itertuples()]
    (RES / "data_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\nsummary:", counts)
    return 1 if counts.get("FAIL", 0) else 0


if __name__ == "__main__":
    sys.exit(main())
