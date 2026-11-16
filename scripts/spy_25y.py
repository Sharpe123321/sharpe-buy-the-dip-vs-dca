"""
Quick SPY-only study (simplified rerun).

  * Asset: SPY from Yahoo Finance, dividend-adjusted close = total return, USD.  Nothing else is traded.
  * Period: the last 25 years = 300 monthly deposits of $500, first deposit on the first trading day of
    Nov 2001, last on the first trading day of Oct 2026 (Nov 2026 is a partial month), valued at the last
    trading day of Oct 2026 (the published run).  The window rolls forward with the data you download.
  * Idle cash earns the US 3-month Treasury bill (FRED DGS3MO, constant-maturity yield, daily): simple actual/365
    interest, using the rate published on or before the previous close.
  * Strategies: monthly DCA, and buy-the-dip at 5 / 10 / 15 / 20% below SPY's all-time high (the high is measured
    over SPY's full history since 1993, not reset in 2001).  The signal uses closes up to day t; the fill is at the
    next trading day's close; 0.05% spread on every purchase.  Same engine and rules as the main study.
  * Also shown: how the same rules do across every 10-year window that fits inside those 25 years, because one
    25-year path is a single draw.

    results/spy_25y.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dipdca import data  # noqa: E402
from dipdca.engine import Market, Prepared, Strategy, value_window, window_starts  # noqa: E402
from dipdca.reference import simulate  # noqa: E402

THRESHOLDS = (0.05, 0.10, 0.15, 0.20)
YEARS, SUB_YEARS = 25, 10
COST, AMOUNT = 0.0005, 500.0


def build(ticker: str, column: str) -> Market:
    y = data.load_yahoo(ticker)
    px = y[column]
    ci = data.cash_growth_index(px.index, data.load_fred("DGS3MO"))
    d = px.index.to_numpy().astype("datetime64[D]")
    return Market(f"{ticker} total return, USD", d, px.to_numpy(), px.to_numpy(), ci, False, {"ticker": ticker})


def run(m: Market, label: str) -> pd.DataFrame:
    prep = Prepared(m, THRESHOLDS, rules=("threshold",))
    N, n10 = 12 * YEARS, 12 * SUB_YEARS
    s25 = len(prep.first) - N                                    # the last 25 years of complete months
    ym0 = int(prep.ym[s25])
    start = f"{1970 + ym0 // 12}-{ym0 % 12 + 1:02d}"
    end_idx = int(prep.last[s25 + N - 1])
    strats = [Strategy("dca")] + [Strategy("dip", t, "threshold") for t in THRESHOLDS]

    dca = value_window(prep, strats[0], s25, N, cash="tbill", cost=COST, amount=AMOUNT)
    subs = window_starts(N, n10) + s25                           # every 10-year window inside the 25 years
    dca10 = np.array([value_window(prep, strats[0], int(s), n10, cash="tbill", cost=COST).final_value for s in subs])

    rows = []
    for st in strats:
        r = value_window(prep, st, s25, N, cash="tbill", cost=COST, amount=AMOUNT)
        # independent check: slow day-by-day simulator must give the same ending value
        ref = simulate(m, st, int(prep.first[s25]), end_idx, cash="tbill", cost=COST, amount=AMOUNT)
        assert abs(r.final_value / ref.final_value - 1) < 1e-9, (label, st, r.final_value, ref.final_value)
        assert abs(r.months_in_cash - ref.months_in_cash) < 1e-6
        e = prep.exec_index(st, prep.first[s25:s25 + N], end_idx)
        n_buys = N if st.kind == "dca" else len(np.unique(e[e >= 0]))
        fin10 = np.array([value_window(prep, st, int(s), n10, cash="tbill", cost=COST).final_value for s in subs])
        rows.append({
            "source": label, "strategy": st.label, "window": f"{start} to {pd.Timestamp(m.dates[end_idx]).strftime('%Y-%m')}",
            "contributions": r.contributions, "final_value": r.final_value,
            "diff_vs_dca_pct": (r.final_value / dca.final_value - 1) * 100,
            "final_cash": r.cash_value, "months_in_cash": r.months_in_cash, "n_purchases": n_buys,
            f"rolling{SUB_YEARS}y_windows": len(subs),
            f"rolling{SUB_YEARS}y_pct_beating_dca": 100 * float(np.mean(fin10 > dca10)) if st.kind != "dca" else np.nan,
            f"rolling{SUB_YEARS}y_median_diff_pct": float(np.median((fin10 / dca10 - 1) * 100)) if st.kind != "dca" else np.nan,
        })
    return pd.DataFrame(rows)


def main() -> None:
    main_df = run(build("SPY", "adj_close"), "SPY")
    check = run(build("^SP500TR", "close"), "^SP500TR (cross-check)")         # same rules on the index itself
    out = pd.concat([main_df, check], ignore_index=True)
    (ROOT / "results").mkdir(exist_ok=True)
    out.to_csv(ROOT / "results" / "spy_25y.csv", index=False, float_format="%.4f")

    pd.set_option("display.width", 220)
    show = out.copy()
    show["final_value"] = show["final_value"].map("${:,.0f}".format)
    show["diff_vs_dca_pct"] = show["diff_vs_dca_pct"].map("{:+.1f}%".format)
    show["months_in_cash"] = show["months_in_cash"].map("{:.0f}".format)
    for c in ("rolling10y_pct_beating_dca", "rolling10y_median_diff_pct"):
        show[c] = show[c].map(lambda v: "" if pd.isna(v) else (f"{v:.0f}%" if "pct_beating" in c else f"{v:+.1f}%"))
    cols = ["strategy", "final_value", "diff_vs_dca_pct", "months_in_cash", "n_purchases", "rolling10y_pct_beating_dca", "rolling10y_median_diff_pct"]
    for src, g in show.groupby("source", sort=False):
        print(f"\n{src}  |  {g['window'].iloc[0]}  |  $150,000 put in over 300 months  |  {int(g['rolling10y_windows'].iloc[0])} rolling 10y windows")
        print(g[cols].to_string(index=False))


if __name__ == "__main__":
    main()
