"""
Why did buying the dip work (slightly) for XIU but not for SPY?  Descriptive market metrics over the period the
two series share, plus one mechanism check at the level of 10-year windows.  Uses the cached Yahoo data and the
existing engine; the main study is NOT rerun.

    results/why_canada.csv              one row per market: return, time below the high, drawdown count, recovery time
    results/why_canada_windows.csv      per 10-year window: share of days 10%+ below the high vs the 10% dip-buyer's result

Definitions (all on dividend-adjusted closes, so total return, each market in its own currency):
  * shared period      1999-10-04 (XIU's first day) to the last trading day on or before AS_OF (2026-10-31, the
                       cut-off of the published results, so the last day used is 2026-10-30).
  * all-time high      running maximum from the start of the shared period, for both markets.
  * % of months        month-end closes that are >= 10% (or 20%) below the all-time high.
  * drawdown           the stretch between one strictly-new all-time high and the next.  It counts as a "10% drawdown"
                       when its lowest close is at least 10% below the high that started it (same for 20%).
  * recovery           peak-to-new-high = months from the peak to the next new high; trough-to-new-high = months from
                       the lowest close to that new high.  Only drawdowns that have finished are averaged.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from dipdca import assets, data  # noqa: E402
from dipdca.engine import Prepared, Strategy, running_max_and_drawdown, value_window, window_starts  # noqa: E402
import spy_25y  # noqa: E402

RES = ROOT / "results"
DAYS_PER_MONTH = 30.4375
AS_OF = "2026-10-31"        # data cut-off of the published results; edit it to roll the comparison forward


def shared_series() -> dict[str, pd.Series]:
    xiu = data.load_yahoo("XIU.TO")["adj_close"]
    spy = data.load_yahoo("SPY")["adj_close"]
    start = max(xiu.index.min(), spy.index.min())
    end = min(xiu[xiu.index <= AS_OF].index.max(), spy[spy.index <= AS_OF].index.max())
    return {"SPY (US)": spy.loc[start:end], "XIU (Canada)": xiu.loc[start:end]}


def episodes(s: pd.Series) -> pd.DataFrame:
    """One row per drawdown episode (strictly-new-high to strictly-new-high)."""
    prev_max = s.cummax().shift(1)
    new = (s > prev_max) | (prev_max.isna())
    ep = new.cumsum()
    rows = []
    n = int(ep.max())
    for k, g in s.groupby(ep):
        trough_date = g.idxmin()
        nxt = s.index[np.flatnonzero(ep.to_numpy() == k + 1)[0]] if k < n else pd.NaT
        rows.append({"peak_date": g.index[0], "trough_date": trough_date, "depth": g.min() / g.iloc[0] - 1.0,
                     "new_high_date": nxt})
    e = pd.DataFrame(rows)
    done = e["new_high_date"].notna()
    e["months_peak_to_new_high"] = np.where(done, (e["new_high_date"] - e["peak_date"]).dt.days / DAYS_PER_MONTH, np.nan)
    e["months_trough_to_new_high"] = np.where(done, (e["new_high_date"] - e["trough_date"]).dt.days / DAYS_PER_MONTH, np.nan)
    return e


def metrics(name: str, s: pd.Series) -> dict:
    dd = s / s.cummax() - 1.0
    me = s.groupby(s.index.to_period("M")).tail(1).index                      # month-end observations
    ddm = dd.loc[me]
    years = (s.index[-1] - s.index[0]).days / 365.25
    e = episodes(s)
    row = {"market": name, "currency": "USD" if "SPY" in name else "CAD", "start": str(s.index[0].date()),
           "end": str(s.index[-1].date()), "years": round(years, 2), "months_observed": len(me),
           "annualised_total_return_pct": ((s.iloc[-1] / s.iloc[0]) ** (1 / years) - 1) * 100,
           "pct_months_10pct_below_high": (ddm <= -0.10).mean() * 100,
           "pct_months_20pct_below_high": (ddm <= -0.20).mean() * 100,
           "pct_trading_days_10pct_below_high": (dd <= -0.10).mean() * 100,
           "pct_months_at_a_new_high": (ddm == 0).mean() * 100,
           "worst_drawdown_pct": dd.min() * 100, "average_daily_drawdown_pct": dd.mean() * 100}
    for x in (0.10, 0.20):
        big = e[e["depth"] <= -x]
        fin = big[big["new_high_date"].notna()]
        tag = f"{int(x * 100)}pct"
        below = (dd <= -x).to_numpy()
        row[f"n_times_fell_below_{tag}_line"] = int(below[0]) + int(np.sum(below[1:] & ~below[:-1]))   # counts re-crossings too
        row[f"n_drawdowns_{tag}"] = len(big)
        row[f"n_drawdowns_{tag}_still_open"] = int(len(big) - len(fin))
        row[f"avg_months_peak_to_new_high_{tag}"] = fin["months_peak_to_new_high"].mean()
        row[f"avg_months_trough_to_new_high_{tag}"] = fin["months_trough_to_new_high"].mean()
        row[f"longest_months_peak_to_new_high_{tag}"] = fin["months_peak_to_new_high"].max()
    return row


def window_check() -> pd.DataFrame:
    """10-year windows starting Nov 2001 - Nov 2016 for both markets (same calendar set): time in dip vs dip-buyer result."""
    nov2001 = (2001 - 1970) * 12 + 10
    rows = []
    for name, m in (("SPY (US)", spy_25y.build("SPY", "adj_close")), ("XIU (Canada)", assets.xiu_cad())):
        prep = Prepared(m, (0.10,), rules=("threshold",))
        _, dd = running_max_and_drawdown(m.sig)
        N = 120
        s0 = int(np.flatnonzero(prep.ym >= nov2001)[0])
        for s in window_starts(len(prep.first), N):
            if s < s0:
                continue
            a, b = int(prep.first[s]), int(prep.last[s + N - 1])
            dca = value_window(prep, Strategy("dca"), int(s), N, cash="tbill", cost=0.0005).final_value
            dip = value_window(prep, Strategy("dip", 0.10, "threshold"), int(s), N, cash="tbill", cost=0.0005).final_value
            ym = int(prep.ym[s])
            below = dd[a:b + 1] <= -0.10
            spells = int(below[0]) + int(np.sum(below[1:] & ~below[:-1]))     # separate stretches 10%+ below the high
            rows.append({"market": name, "start_month": f"{1970 + ym // 12}-{ym % 12 + 1:02d}",
                         "pct_days_10pct_below_high_in_window": float(below.mean() * 100),
                         "n_separate_10pct_dips_in_window": spells,
                         "dip10_vs_dca_pct": (dip / dca - 1) * 100})
    return pd.DataFrame(rows)


def explain(w: pd.DataFrame) -> dict:
    """How much of the XIU-vs-SPY gap in the 10% dip-buyer's result does time-in-dip account for?  (descriptive only)"""
    x = w["pct_days_10pct_below_high_in_window"].to_numpy()
    y = w["dip10_vs_dca_pct"].to_numpy()
    xiu = (w["market"] == "XIU (Canada)").to_numpy().astype(float)
    out = {}
    for nm in ("SPY (US)", "XIU (Canada)"):
        g = w[w["market"] == nm]
        out[f"{nm}: windows"] = len(g)
        out[f"{nm}: mean % of days 10%+ below high"] = g["pct_days_10pct_below_high_in_window"].mean()
        out[f"{nm}: mean dip10 vs DCA %"] = g["dip10_vs_dca_pct"].mean()
        out[f"{nm}: slope (pts per 10 pts more time in dip)"] = np.polyfit(g["pct_days_10pct_below_high_in_window"], g["dip10_vs_dca_pct"], 1)[0] * 10
        out[f"{nm}: corr(time in dip, result)"] = g["pct_days_10pct_below_high_in_window"].corr(g["dip10_vs_dca_pct"])
    gap = out["XIU (Canada): mean dip10 vs DCA %"] - out["SPY (US): mean dip10 vs DCA %"]
    A = np.column_stack([np.ones_like(x), x, xiu])                            # y = a + b*time_in_dip + c*[XIU]
    a, b, c = np.linalg.lstsq(A, y, rcond=None)[0]
    out["raw gap XIU minus SPY (pts)"] = gap
    out["pooled slope b (pts per 10 pts of time in dip)"] = b * 10
    out["gap left after allowing for time in dip, c (pts)"] = c
    out["share of the gap accounted for by time in dip"] = 1 - c / gap if gap else np.nan
    r2_x = 1 - np.sum((y - A[:, :2] @ np.linalg.lstsq(A[:, :2], y, rcond=None)[0]) ** 2) / np.sum((y - y.mean()) ** 2)
    out["R^2 of result on time in dip alone (pooled)"] = r2_x
    # exploratory second candidate: how many separate 10%+ dips the window contains
    sp = w["n_separate_10pct_dips_in_window"].to_numpy().astype(float)
    for nm in ("SPY (US)", "XIU (Canada)"):
        g = w[w["market"] == nm]
        out[f"{nm}: mean separate 10%+ dips per window"] = g["n_separate_10pct_dips_in_window"].mean()
        out[f"{nm}: corr(separate dips, result)"] = g["n_separate_10pct_dips_in_window"].corr(g["dip10_vs_dca_pct"])
    for label, cols in (("separate dips alone", [sp]), ("time in dip + separate dips", [x, sp])):
        B = np.column_stack([np.ones_like(x)] + cols + [xiu])
        coef = np.linalg.lstsq(B, y, rcond=None)[0]
        out[f"gap left after allowing for {label} (pts)"] = coef[-1]
        out[f"share of the gap accounted for by {label}"] = 1 - coef[-1] / gap if gap else np.nan
        Bn = B[:, :-1]
        out[f"R^2 of result on {label} (pooled, no market term)"] = 1 - np.sum((y - Bn @ np.linalg.lstsq(Bn, y, rcond=None)[0]) ** 2) / np.sum((y - y.mean()) ** 2)
    return out


def main() -> None:
    RES.mkdir(exist_ok=True)
    series = shared_series()
    df = pd.DataFrame([metrics(n, s) for n, s in series.items()])
    df.to_csv(RES / "why_canada.csv", index=False, float_format="%.3f")
    w = window_check()
    w.to_csv(RES / "why_canada_windows.csv", index=False, float_format="%.3f")
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 40)
    print(df.set_index("market").T.to_string())
    print()
    for k, v in explain(w).items():
        print(f"{k:60s} {v:10.3f}" if isinstance(v, float) else f"{k:60s} {v}")
    for n, s in series.items():
        e = episodes(s)
        big = e[e["depth"] <= -0.10]
        print(f"\n{n}: 10%+ drawdowns")
        print(big.assign(depth=(big["depth"] * 100).round(1), peak=big["peak_date"].dt.date, new_high=big["new_high_date"].dt.date,
                         m_peak=big["months_peak_to_new_high"].round(1), m_trough=big["months_trough_to_new_high"].round(1))
              [["peak", "depth", "new_high", "m_peak", "m_trough"]].to_string(index=False))


if __name__ == "__main__":
    main()
