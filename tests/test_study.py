"""Study-level tests: the win-rate / difference / cash-time statistics are computed from the right quantities."""
from __future__ import annotations

import numpy as np
import pytest

from dipdca.engine import Prepared, Strategy, value_window, window_starts
from dipdca.study import run_study
from helpers import make_market, random_market


def test_always_rising_market_dip_buyer_never_beats_dca_and_sits_in_cash():
    m = make_market(100.0 * 1.0004 ** np.arange(3000), rate_pct=0.0)           # every close is a new high
    s = run_study(m, "up", horizons=(5,), cash_modes=("zero",), cost_modes={"no": 0.0}).summary
    dips = s[s.strategy.str.startswith("dip")]
    assert (dips.pct_beats_monthly == 0).all()
    assert (dips.median_diff_pct < 0).all() and (dips.pct_windows_ending_with_cash == 100).all()
    assert (dips.avg_months_in_cash > 58).all()                                 # ~the whole 60-month window
    g = s[s.strategy == "perfect_timing"]
    assert (g.pct_beats_monthly == 0).all()                                     # no completed drawdown -> never invests either


def test_summary_statistics_match_a_manual_recomputation():
    m = random_market(11, n=2600)
    N = 24
    out = run_study(m, "rand", horizons=(2,), thresholds=(0.10,), rules=("threshold",), cash_modes=("tbill",),
                    cost_modes={"spread_0.05pct": 0.0005})              # the name run_study keeps per-window detail for
    row = out.summary[(out.summary.strategy == "dip_10pct")].iloc[0]
    prep = Prepared(m, (0.10,))
    starts = window_starts(len(prep.first), N)
    dca = np.array([value_window(prep, Strategy("dca"), int(s), N, cash="tbill", cost=0.0005).final_value for s in starts])
    dip = np.array([value_window(prep, Strategy("dip", 0.10), int(s), N, cash="tbill", cost=0.0005).final_value for s in starts])
    diff = (dip / dca - 1) * 100
    assert row.n_windows == len(starts) == len(out.windows[out.windows.strategy == "dip_10pct"])
    assert row.pct_beats_monthly == pytest.approx(100 * np.mean(dip > dca))
    assert (row.median_diff_pct, row.worst_diff_pct, row.best_diff_pct) == pytest.approx((np.median(diff), diff.min(), diff.max()))


def test_cost_does_not_change_the_comparison_only_levels():
    """Every dollar pays the same proportional spread whichever strategy buys it, so ratios barely move."""
    m = random_market(5, n=2600)
    a = run_study(m, "x", horizons=(2,), cash_modes=("tbill",), cost_modes={"c": 0.0005}).summary.set_index("strategy")
    b = run_study(m, "x", horizons=(2,), cash_modes=("tbill",), cost_modes={"n": 0.0}).summary.set_index("strategy")
    dip = [s for s in a.index if s.startswith("dip")]
    assert np.allclose(a.loc[dip, "median_diff_pct"].to_numpy(dtype=float), b.loc[dip, "median_diff_pct"].to_numpy(dtype=float), atol=0.06)
    assert (a.loc[dip, "median_dca_final"].to_numpy(dtype=float) < b.loc[dip, "median_dca_final"].to_numpy(dtype=float)).all()
