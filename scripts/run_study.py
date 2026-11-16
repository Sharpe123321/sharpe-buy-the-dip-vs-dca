"""
Main study.  For a Canadian investor putting $500/month into (a) XIU (TSX 60 ETF, CAD, total return) and
(b) the S&P 500 converted to CAD (total return): every possible start month, 10/20/30-year horizons, monthly
DCA vs buying the dip at 5/10/20/30% below the all-time high vs hypothetical perfect timing, with cash earning
the Canadian T-bill rate or 0%, and with or without a 0.05% spread.

Writes (results/):
    summary_xiu_cad.csv, summary_sp500_cad.csv   every asset x horizon x strategy x rule x cash x cost
    headline_table.csv                           primary settings only (T-bill cash, 0.05% spread, literal threshold rule)
    by_start_year.csv                            primary settings, split by the year the window starts
    sensitivity.csv                              signal/total-return construction alternatives

Writes (local_only/, git-ignored, NOT published):
    windows_primary.csv                          one row per window for the primary settings.  Consecutive windows'
                                                 ending values let anyone rebuild the underlying month-end returns
                                                 (XIU: correlation 0.998), i.e. the provider's data, so it stays local.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dipdca import assets  # noqa: E402
from dipdca.study import PRIMARY, run_study  # noqa: E402

RES, LOCAL = ROOT / "results", ROOT / "local_only"
KEEP = ["asset", "horizon_years", "strategy", "rule", "cash_mode", "cost_mode", "n_windows", "approx_independent_windows",
        "first_start", "last_start", "pct_beats_monthly", "median_diff_pct", "worst_diff_pct", "best_diff_pct",
        "mean_diff_pct", "avg_months_in_cash", "median_months_in_cash", "pct_windows_ending_with_cash", "window_months",
        "median_dca_final"]


def main() -> None:
    RES.mkdir(exist_ok=True)
    markets = {"XIU (TSX 60 ETF), CAD": ("summary_xiu_cad.csv", assets.xiu_cad()),
               "S&P 500, CAD": ("summary_sp500_cad.csv", assets.sp500_cad())}
    all_sum, all_win = [], []
    for name, (fname, m) in markets.items():
        out = run_study(m, name)
        out.summary[KEEP].to_csv(RES / fname, index=False, float_format="%.4f")
        all_sum.append(out.summary)
        all_win.append(out.windows)
        print(f"{name}: {len(m.dates):,} days {m.dates[0]} -> {m.dates[-1]}; horizons run: "
              f"{sorted(out.summary.horizon_years.unique())}")

    summ, win = pd.concat(all_sum, ignore_index=True), pd.concat(all_win, ignore_index=True)
    cash, cost, rule = PRIMARY
    prim = summ[(summ.cash_mode == cash) & (summ.cost_mode == cost) & (summ.rule.isin([rule, "hindsight"]))]
    prim[KEEP].to_csv(RES / "headline_table.csv", index=False, float_format="%.4f")
    LOCAL.mkdir(exist_ok=True)
    win.to_csv(LOCAL / "windows_primary.csv", index=False, float_format="%.4f")

    win = win.assign(start_year=win["start_month"].str[:4].astype(int))
    by = (win.groupby(["asset", "horizon_years", "strategy", "rule", "start_year"])
             .agg(n_windows=("diff_pct", "size"), pct_beats_monthly=("diff_pct", lambda x: 100 * (x > 0).mean()),
                  median_diff_pct=("diff_pct", "median"), avg_months_in_cash=("months_in_cash", "mean")).reset_index())
    by.to_csv(RES / "by_start_year.csv", index=False, float_format="%.3f")

    # ---- sensitivity: does the answer depend on how the series / signal is built?
    sens = []
    variants = [
        ("base case", assets.xiu_cad()),
        ("XIU: dips read from price-only (no dividends)", assets.xiu_cad(signal="price")),
        ("XIU: own reinvestment of every Yahoo 'dividend' (+4.3% over 27y)", assets.xiu_cad(tr_source="own_reinvest")),
        ("S&P 500 CAD: base case", assets.sp500_cad()),
        ("S&P 500 CAD: dips read from the USD index", assets.sp500_cad(signal="usd")),
    ]
    for label, m in variants:
        s = run_study(m, label, cash_modes=(cash,), cost_modes={cost: 0.0005}, keep_windows_for=("none", "none", "none")).summary
        s.insert(0, "sensitivity", label)
        sens.append(s)
    # fill convention: does it matter whether a deposit arriving ON a fill day joins that day's order?
    for label, m in (("XIU: deposit arriving on a fill day joins that day's order", assets.xiu_cad()),
                     ("S&P 500 CAD: deposit arriving on a fill day joins that day's order", assets.sp500_cad())):
        s = run_study(m, label, cash_modes=(cash,), cost_modes={cost: 0.0005}, keep_windows_for=("none", "none", "none"),
                      same_day=True).summary
        s.insert(0, "sensitivity", label)
        sens.append(s)
    pd.concat(sens, ignore_index=True).drop(columns=["cash_mode", "cost_mode", "median_contributions"]).to_csv(
        RES / "sensitivity.csv", index=False, float_format="%.4f")

    show = prim
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 200)
    cols = ["asset", "horizon_years", "strategy", "n_windows", "pct_beats_monthly", "median_diff_pct", "worst_diff_pct",
            "best_diff_pct", "avg_months_in_cash"]
    print("\nHEADLINE (T-bill cash, 0.05% spread, literal threshold rule)")
    print(show[cols].round(1).to_string(index=False))


if __name__ == "__main__":
    main()
