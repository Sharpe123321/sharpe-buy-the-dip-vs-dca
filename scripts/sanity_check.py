"""
Sanity check against Nick Maggiulli (Of Dollars and Data).

His two posts test different things, so there are two reference points:
  * "Even God Couldn't Beat Dollar-Cost Averaging" (2019): PERFECT-foresight buy-the-dip vs DCA, 40-year
    windows, 1920-1988 start years, S&P 500 with dividends adjusted for inflation, monthly data.
    Reported: buy-the-dip underperforms DCA "over 70% of the time" (i.e. beats it < ~30%).
  * "Why Buying the Dip is a Terrible Investment Strategy" (2021): threshold rules, 20-year windows, US stocks.
    Reported: roughly a one-in-four chance of beating DCA at 10-20% thresholds, nearly 40% at 50%.
(Figures as relayed from the posts' text; his charts could not be read.)

We run the same questions on US data in USD with 0% interest on cash and no trading costs (he assumed none),
varying the things we cannot match exactly (nominal vs real, month-end vs monthly-average prices).

    results/sanity_check_maggiulli.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dipdca import assets  # noqa: E402
from dipdca.study import run_study  # noqa: E402

VARIANTS = [
    ("CRSP monthly, month-end, nominal", lambda: assets.us_total_market_usd("monthly"), (20, 40)),
    ("CRSP monthly, month-end, REAL", lambda: assets.us_total_market_usd("monthly", real=True), (20, 40)),
    ("CRSP monthly, monthly-average, nominal", lambda: assets.us_total_market_usd("daily", month_avg=True), (20, 40)),
    ("CRSP monthly, monthly-average, REAL (closest to Shiller)", lambda: assets.us_total_market_usd("daily", month_avg=True, real=True), (20, 40)),
    ("CRSP daily, nominal (next-trading-day fills)", lambda: assets.us_total_market_usd("daily"), (20, 40)),
    ("S&P 500 total return, USD, daily, nominal (1988+)", lambda: assets.sp500_usd(), (10, 20, 30)),
]


def main() -> pd.DataFrame:
    out = []
    for label, build, horizons in VARIANTS:
        m = build()
        s = run_study(m, label, horizons=horizons, thresholds=(0.10, 0.20, 0.30), rules=("threshold", "until_ath"),
                      cash_modes=("zero",), cost_modes={"no_cost": 0.0}, strict_god=True).summary
        s.insert(0, "variant", label)
        out.append(s)
    df = pd.concat(out, ignore_index=True)
    # 'months in cash' is meaningless on monthly data (a one-observation lag = one month, so some cash is always on hand)
    monthly = df["variant"].str.contains("monthly")
    df.loc[monthly, ["avg_months_in_cash", "median_months_in_cash"]] = float("nan")
    (ROOT / "results").mkdir(exist_ok=True)
    df.drop(columns=["cash_mode", "cost_mode", "median_contributions"]).to_csv(ROOT / "results" / "sanity_check_maggiulli.csv", index=False)

    god = df[df["strategy"].isin(["perfect_timing", "perfect_timing_strict"])]
    print("\nPERFECT TIMING (hindsight) vs monthly DCA - % of windows where it WINS   (Maggiulli 2019: ~30% at 40y)")
    print(god.pivot_table(index=["variant", "strategy"], columns="horizon_years", values="pct_beats_monthly").round(1).to_string())
    print("\nTHRESHOLD dip-buying - % of windows beating DCA, 20-year windows, 'until new high' rule  (Maggiulli 2021: ~25% at 10-20%)")
    t = df[(df["rule"] == "until_ath") & (df["horizon_years"] == 20)]
    print(t.pivot_table(index="variant", columns="strategy", values="pct_beats_monthly").round(1).to_string())
    era_table()
    return df


def era_table() -> None:
    """Perfect timing vs DCA for 40-year windows, split by start year (daily nominal CRSP): shows the eras behind the average."""
    from dipdca.engine import Prepared, Strategy, god_bottoms, value_window, window_starts
    m = assets.us_total_market_usd("daily")
    prep = Prepared(m, (0.10,))
    N = 480
    rows = []
    for s in window_starts(len(prep.first), N):
        g = value_window(prep, Strategy("god"), int(s), N, cash="zero", cost=0.0)
        d = value_window(prep, Strategy("dca"), int(s), N, cash="zero", cost=0.0)
        rows.append({"start_year": int(prep.ym[s]) // 12 + 1970, "diff_pct": (g.final_value / d.final_value - 1) * 100})
    df = pd.DataFrame(rows)
    out = df.groupby("start_year").agg(windows=("diff_pct", "size"), pct_perfect_timing_beats_dca=("diff_pct", lambda x: 100 * (x > 0).mean()),
                                       median_diff_pct=("diff_pct", "median")).reset_index()
    out.to_csv(ROOT / "results" / "sanity_check_by_start_year.csv", index=False, float_format="%.2f")
    b, c = god_bottoms(m.sig)
    gap = (m.dates[c] - m.dates[b]).astype("timedelta64[D]").astype(int) / 365.25
    k = int(gap.argmax())
    print(f"\nlongest bottom-to-next-high stretch (nominal): {m.dates[b[k]]} -> {m.dates[c[k]]}, {gap[k]:.1f} years")
    lo, hi = out[out.pct_perfect_timing_beats_dca == 0].start_year, out[out.pct_perfect_timing_beats_dca == 100].start_year
    print("40y windows where perfect timing NEVER beats DCA start in:", sorted(lo.tolist()))
    print("40y windows where perfect timing ALWAYS beats DCA start in:", sorted(hi.tolist()))


if __name__ == "__main__":
    main()
