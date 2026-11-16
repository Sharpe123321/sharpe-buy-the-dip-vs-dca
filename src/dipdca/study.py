"""Rolling-window study: every possible start month x horizon x strategy x cash/cost variant."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .engine import Market, Prepared, Strategy, value_window, window_starts

THRESHOLDS = (0.05, 0.10, 0.20, 0.30)
RULES = ("threshold", "until_ath")
CASH_MODES = ("tbill", "zero")
COST_MODES = {"spread_0.05pct": 0.0005, "no_cost": 0.0}
PRIMARY = ("tbill", "spread_0.05pct", "threshold")        # the settings every headline number uses


@dataclass
class StudyOutput:
    summary: pd.DataFrame
    windows: pd.DataFrame      # per-window detail for the PRIMARY variant only


def strategies(thresholds=THRESHOLDS, rules=RULES, same_day: bool = False, strict_god: bool = False) -> list[Strategy]:
    out = [Strategy("dip", t, r, same_day) for r in rules for t in thresholds]
    return out + [Strategy("god")] + ([Strategy("god", strict_bottom=True)] if strict_god else [])


def _ym(prep: Prepared, pos: int) -> str:
    v = int(prep.ym[pos])
    return f"{1970 + v // 12:04d}-{v % 12 + 1:02d}"


def run_study(market: Market, asset: str, horizons=(10, 20, 30), thresholds=THRESHOLDS, rules=RULES,
              cash_modes=CASH_MODES, cost_modes=COST_MODES, amount: float = 500.0,
              keep_windows_for=PRIMARY, same_day: bool = False, strict_god: bool = False) -> StudyOutput:
    prep = Prepared(market, thresholds, rules)
    strats = strategies(thresholds, rules, same_day, strict_god)
    months_available = len(prep.first)
    rows, wrows = [], []

    for H in horizons:
        N = 12 * H if not market.monthly else 12 * H
        starts = window_starts(months_available, N)
        if len(starts) == 0:
            continue
        span_months = months_available
        for cash in cash_modes:
            for cost_name, cost in cost_modes.items():
                dca = [value_window(prep, Strategy("dca"), int(s), N, cash=cash, cost=cost, amount=amount) for s in starts]
                dca_final = np.array([r.final_value for r in dca])
                for st in strats:
                    res = [value_window(prep, st, int(s), N, cash=cash, cost=cost, amount=amount) for s in starts]
                    fin = np.array([r.final_value for r in res])
                    diff = (fin / dca_final - 1.0) * 100.0
                    mic = np.array([r.months_in_cash for r in res])
                    ends_cash = np.array([r.cash_value > 0 for r in res])
                    rows.append({
                        "asset": asset, "horizon_years": H, "strategy": st.label,
                        "rule": st.rule if st.kind == "dip" else ("hindsight" if st.kind == "god" else "n/a"),
                        "cash_mode": cash, "cost_mode": cost_name,
                        "fill_convention": ("deposit_joins_same_day_fill" if same_day else "deposit_waits_for_own_signal")
                        if st.kind == "dip" else "n/a",
                        "n_windows": len(starts), "approx_independent_windows": round(span_months / N, 2),
                        "first_start": _ym(prep, int(starts[0])), "last_start": _ym(prep, int(starts[-1])),
                        "pct_beats_monthly": 100.0 * float(np.mean(fin > dca_final)),
                        "median_diff_pct": float(np.median(diff)), "worst_diff_pct": float(diff.min()),
                        "best_diff_pct": float(diff.max()), "mean_diff_pct": float(diff.mean()),
                        "avg_months_in_cash": float(mic.mean()), "median_months_in_cash": float(np.median(mic)),
                        "pct_windows_ending_with_cash": 100.0 * float(ends_cash.mean()),
                        "window_months": N, "median_dca_final": float(np.median(dca_final)),
                        "median_contributions": float(N * amount),
                    })
                    if (cash, cost_name, st.rule if st.kind == "dip" else "threshold") == keep_windows_for or \
                            (st.kind == "god" and (cash, cost_name) == keep_windows_for[:2]):
                        for k, s in enumerate(starts):
                            wrows.append({"asset": asset, "horizon_years": H, "start_month": _ym(prep, int(s)),
                                          "strategy": st.label, "rule": st.rule if st.kind == "dip" else "hindsight",
                                          "final_value": res[k].final_value, "monthly_dca_final": dca_final[k],
                                          "diff_pct": diff[k], "months_in_cash": mic[k], "final_cash": res[k].cash_value})
    return StudyOutput(pd.DataFrame(rows), pd.DataFrame(wrows))
