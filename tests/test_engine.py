"""
Engine tests.  Groups:
  1. cross-implementation: vectorised engine == slow day-by-day reference on thousands of random paths
  2. no look-ahead:        signals use only past closes; fills happen at the NEXT close; the hindsight
                           strategy is the one (and only one) that fails the look-ahead test, proving the test has teeth
  3. cash accounting:      money in == money out, interest accrues correctly, costs are applied
  4. calendar / windows:   first-trading-day deposits, partial months dropped, window length
  5. hand-checked cases:   tiny paths worked out on paper
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dipdca import data
from dipdca.engine import (Market, Prepared, Strategy, god_bottoms, month_grid, new_ath_flags, next_true_index,
                           running_max_and_drawdown, threshold_mask, value_window, window_starts)
from dipdca.reference import simulate
from helpers import make_market, random_market

THR = (0.05, 0.10, 0.20, 0.30)
ALL = ([Strategy("dca")]
       + [Strategy("dip", t, r, sd) for t in THR for r in ("threshold", "until_ath") for sd in (False, True)]
       + [Strategy("god"), Strategy("god", strict_bottom=True)])


# =========================================================================== 1. cross-implementation
@pytest.mark.parametrize("monthly", [False, True])
def test_engine_matches_reference_on_random_paths(monthly):
    n_checked = 0
    for seed in range(40):
        m = random_market(seed, n=1500 if not monthly else 600, monthly=monthly, rates=(seed % 2 == 0))
        prep = Prepared(m, THR)
        N = 24 if not monthly else 60
        starts = window_starts(len(prep.first), N)
        rng = np.random.default_rng(seed)
        for s in rng.choice(starts, size=min(4, len(starts)), replace=False):
            for strat in ALL:
                for cash in ("tbill", "zero"):
                    for cost in (0.0, 0.0005):
                        a = value_window(prep, strat, int(s), N, cash=cash, cost=cost)
                        b = simulate(m, strat, int(prep.first[s]), int(prep.last[s + N - 1]), cash=cash, cost=cost)
                        for x, y in ((a.final_value, b.final_value), (a.equity_value, b.equity_value),
                                     (a.cash_value, b.cash_value), (a.months_in_cash, b.months_in_cash),
                                     (a.contributions, b.contributions)):
                            assert x == pytest.approx(y, rel=1e-9, abs=1e-6), (seed, s, strat, cash, cost)
                        n_checked += 1
    assert n_checked > 5000


# =========================================================================== 2. no look-ahead
def _prep_truncated(m: Market, t0: int, thr=THR):
    cut = Market(m.name, m.dates[: t0 + 1], m.px[: t0 + 1], m.sig[: t0 + 1], m.cash_tbill[: t0 + 1], m.monthly)
    return Prepared(cut, thr)


@pytest.mark.parametrize("seed", range(8))
@pytest.mark.parametrize("same_day", [False, True])
def test_signal_decisions_do_not_depend_on_future_prices(seed, same_day):
    """Truncating the history at T0 must not change any fill that happened on or before T0."""
    m = random_market(seed, n=1600)
    t0 = 1000
    full, trunc = Prepared(m, THR), _prep_truncated(m, t0)
    deposits = full.first[(full.first > 40) & (full.first < t0 - 60)]
    for strat in [Strategy("dca")] + [Strategy("dip", t, r, same_day) for t in THR for r in ("threshold", "until_ath")]:
        e_full = full.exec_index(strat, deposits, len(m.px) - 1)
        e_cut = trunc.exec_index(strat, deposits, t0)
        known = (e_full >= 0) & (e_full <= t0)
        assert np.array_equal(e_cut[known], e_full[known]), strat
        assert np.all(e_cut[~known] == -1), strat      # no fill the full run made after T0 can appear early


@pytest.mark.parametrize("rule", ["threshold", "until_ath"])
def test_dip_mask_unchanged_when_future_is_scrambled(rule):
    rng = np.random.default_rng(1)
    m = random_market(3, n=1200)
    t0 = 700
    scrambled = m.sig.copy()
    scrambled[t0 + 1:] *= rng.uniform(0.3, 3.0, len(scrambled) - t0 - 1)
    for thr in THR:
        a = threshold_mask(m.sig, thr, rule)[: t0 + 1]
        b = threshold_mask(scrambled, thr, rule)[: t0 + 1]
        assert np.array_equal(a, b)


def test_hindsight_strategy_DOES_use_the_future():
    """
    Control: the look-ahead property tested above must be ABLE to fail.  Perfect timing is hindsight by
    construction: its day-3 fill (the 80 bottom) only becomes knowable once the day-5 new high (120) has
    happened, so cutting the history at day 4 changes a fill that was made on day 3.
    """
    sig = np.array([100, 110, 90, 80, 85, 120, 100, 95, 130, 130, 130.0])
    m = make_market(sig, start="2015-01-01")
    full = Prepared(m, (0.1,))
    t0 = 4
    cut = _prep_truncated(m, t0, (0.1,))
    d = np.array([2])
    e_full = full.exec_index(Strategy("god"), d, len(sig) - 1)
    e_cut = cut.exec_index(Strategy("god"), d, t0)
    assert e_full[0] == 3 <= t0          # with the full history the deposit is filled on day 3 (<= t0) ...
    assert e_cut[0] == -1                # ... but with only data through day 4 that fill cannot be known: look-ahead
    f2 = full.exec_index(Strategy("dip", 0.1), d, len(sig) - 1)     # the dip rule, on the same path, passes the property
    c2 = cut.exec_index(Strategy("dip", 0.1), d, t0)
    assert f2[0] > t0 and c2[0] == -1 or f2[0] == c2[0]


def test_fill_is_at_the_next_close_not_the_signal_close():
    """Flat at 100, -30% on day 20 (the first signal close), 72 on day 21 (fill day), 90 afterwards."""
    px = np.full(60, 100.0)
    px[20], px[21], px[22:] = 70.0, 72.0, 90.0
    m = make_market(px, start="2015-01-01")
    prep = Prepared(m, (0.20,))
    assert running_max_and_drawdown(m.sig)[1][19] == 0.0 and running_max_and_drawdown(m.sig)[1][20] == pytest.approx(-0.30)
    e = prep.exec_index(Strategy("dip", 0.20), np.array([5]), 59)    # cash saved on day 5, first signal close is day 20
    assert e[0] == 21                                                # ... acted on at the next close, day 21
    px2 = px.copy()                                                  # the fill DAY cannot depend on the fill-day price
    px2[21] = 60.0
    e2 = Prepared(make_market(px2, start="2015-01-01"), (0.20,)).exec_index(Strategy("dip", 0.20), np.array([5]), 59)
    assert e2[0] == 21


def test_reference_simulator_buys_at_the_next_close_price():
    px = np.full(60, 100.0)
    px[20], px[21], px[22:] = 70.0, 72.0, 90.0
    m = make_market(px, start="2015-01-01")       # business days from Thu 2015-01-01: days 0-21 are all January
    res = simulate(m, Strategy("dip", 0.20), 0, 59, cash="zero", cost=0.0, amount=500.0)
    idx, shares, cash_spent = res.buys[0]
    assert idx == 21                              # filled at the NEXT close after the day-20 signal
    assert (shares, cash_spent) == (pytest.approx(500.0 / 72.0), 500.0)     # one January deposit, paid 72 not 70


def test_drawdown_uses_the_full_history_high_not_the_window_start():
    """Market peaked at 200 BEFORE the window; at window start it is already 40% down, so a 30% dip-buyer buys at once."""
    px = np.r_[np.linspace(100, 200, 40), np.linspace(200, 120, 40), np.full(120, 120.0)]
    m = make_market(px, start="2015-01-01")
    prep = Prepared(m, (0.30,))
    assert running_max_and_drawdown(m.sig)[1][79] == pytest.approx(-0.40)
    d = np.array([80])                                 # a deposit on a day when drawdown is -40% vs the old high
    e = prep.exec_index(Strategy("dip", 0.30), d, len(px) - 1)
    assert e[0] == 81


# =========================================================================== 3. cash accounting
@pytest.mark.parametrize("seed", range(6))
def test_money_in_equals_money_out_with_zero_interest_and_cost(seed):
    m = random_market(seed, n=1500, rates=False)
    prep = Prepared(m, THR)
    s, N = 5, 36
    for strat in ALL:
        r = simulate(m, strat, int(prep.first[s]), int(prep.last[s + N - 1]), cash="zero", cost=0.0)
        spent = sum(b[2] for b in r.buys)
        assert spent + r.cash_value == pytest.approx(r.contributions, rel=1e-12)       # nothing created or lost
        assert r.contributions == N * 500.0
        assert r.final_value == pytest.approx(r.equity_value + r.cash_value)


def test_interest_accrues_on_cash_only_and_is_conserved():
    m = random_market(7, n=1500, rates=True)
    prep = Prepared(m, THR)
    s, N = 5, 36
    strat = Strategy("dip", 0.30)
    r = simulate(m, strat, int(prep.first[s]), int(prep.last[s + N - 1]), cash="tbill", cost=0.0)
    spent = sum(b[2] for b in r.buys)
    interest = spent + r.cash_value - r.contributions
    assert interest > 0                                  # cash earned something
    z = simulate(m, strat, int(prep.first[s]), int(prep.last[s + N - 1]), cash="zero", cost=0.0)
    assert sum(b[2] for b in z.buys) + z.cash_value == pytest.approx(z.contributions)   # and zero-rate cash earns nothing


def test_dca_never_holds_cash_and_pays_the_spread_on_every_dollar():
    m = random_market(4, n=1500)
    prep = Prepared(m, THR)
    s, N = 3, 30
    c = 0.0005
    r = value_window(prep, Strategy("dca"), s, N, cash="tbill", cost=c)
    assert r.months_in_cash == 0.0 and r.cash_value == 0.0
    d = prep.first[s:s + N]
    expect = float(np.sum(500.0 / (m.px[d] * (1 + c))) * m.px[prep.last[s + N - 1]])
    assert r.final_value == pytest.approx(expect, rel=1e-12)
    free = value_window(prep, Strategy("dca"), s, N, cash="tbill", cost=0.0)
    assert r.final_value == pytest.approx(free.final_value / (1 + c), rel=1e-12)       # spread = 1/(1+c) on every purchase


def test_dca_on_a_flat_market_returns_exactly_the_contributions():
    m = make_market(np.full(800, 50.0))
    prep = Prepared(m, THR)
    r = value_window(prep, Strategy("dca"), 0, 24, cash="zero", cost=0.0)
    assert r.final_value == pytest.approx(24 * 500.0)


def test_uninvested_cash_is_counted_in_the_final_value():
    """A market that only rises never dips, so a dip-buyer ends the window entirely in cash - and is credited for it."""
    px = 100.0 * 1.0004 ** np.arange(1200)
    m = make_market(px, rate_pct=4.0)
    prep = Prepared(m, THR)
    r = value_window(prep, Strategy("dip", 0.05), 0, 24, cash="zero", cost=0.0)
    assert r.equity_value == 0.0 and r.cash_value == pytest.approx(24 * 500.0) and r.final_value == pytest.approx(24 * 500.0)
    assert r.months_in_cash > 22.5                                  # cash sat there almost the whole window
    rt = value_window(prep, Strategy("dip", 0.05), 0, 24, cash="tbill", cost=0.0)
    d, end = prep.first[:24], prep.last[23]
    assert rt.equity_value == 0.0
    assert rt.final_value == pytest.approx(float((500.0 * m.cash_tbill[end] / m.cash_tbill[d]).sum()))   # cash + its interest
    assert rt.final_value > 24 * 500.0
    dca = value_window(prep, Strategy("dca"), 0, 24, cash="zero", cost=0.0)
    assert dca.final_value > rt.final_value                         # prices rise ~10%/yr vs 4% cash: DCA wins by construction


def test_cash_growth_index_uses_the_previous_days_rate_and_actual_365():
    dates = pd.DatetimeIndex(["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-10"])
    rate = pd.Series([5.0, 10.0], index=pd.DatetimeIndex(["2019-12-31", "2020-01-03"]))
    ci = data.cash_growth_index(dates, rate)
    assert ci[0] == 1.0
    assert ci[1] == pytest.approx(1 + 0.05 * 1 / 365)                                  # rate on/before 01-01 = 5%
    assert ci[2] == pytest.approx(ci[1] * (1 + 0.05 * 1 / 365))                        # 10% only published ON 01-03 ...
    assert ci[3] == pytest.approx(ci[2] * (1 + 0.10 * 7 / 365))                        # ... so it starts applying after that close


def test_total_return_index_reinvests_dividends():
    close = pd.Series([100.0, 100.0, 98.0, 98.0, 99.0], index=pd.bdate_range("2020-01-01", periods=5))
    div = pd.Series([2.0], index=[close.index[2]])                                      # price fell exactly by the dividend
    tr = data.total_return_index(close, div)
    assert tr.iloc[1] == pytest.approx(100.0) and tr.iloc[2] == pytest.approx(100.0)   # no loss for the holder
    assert tr.iloc[4] == pytest.approx(100.0 * (1 + 1.0 / 98.0))                        # then tracks the price
    flat = pd.Series([100.0] * 4, index=pd.bdate_range("2020-01-01", periods=4))
    assert data.total_return_index(flat, pd.Series([1.0, 1.0], index=flat.index[[1, 3]])).iloc[-1] == pytest.approx(100 * 1.01 * 1.01)
    with pytest.raises(ValueError):                                                     # dividend on a non-trading day
        data.total_return_index(close, pd.Series([1.0], index=[pd.Timestamp("2020-01-04")]))


# =========================================================================== 4. calendar / windows
def test_first_and_last_trading_day_of_month_with_holidays_and_partial_months():
    # Jan 1-2 missing (holiday), a gap mid-Feb, data stops 2020-04-14 (partial April)
    days = pd.bdate_range("2020-01-03", "2020-04-14").drop([pd.Timestamp("2020-02-17"), pd.Timestamp("2020-02-18")])
    m = make_market(np.arange(1, len(days) + 1, dtype=float), dates=days)
    ym, first, last = month_grid(m)
    # the first (Jan, partial: starts 01-03) and last (Apr, partial) months are dropped -> Feb, Mar remain
    assert [str(x) for x in m.dates[first].astype("datetime64[D]")] == ["2020-02-03", "2020-03-02"]
    assert [str(x) for x in m.dates[last].astype("datetime64[D]")] == ["2020-02-28", "2020-03-31"]


def test_window_has_n_deposits_and_ends_on_last_trading_day_of_final_month():
    m = random_market(0, n=1700)
    prep = Prepared(m, THR)
    N = 24
    for s in (0, 7, len(prep.first) - N):
        d = prep.first[s:s + N]
        assert len(d) == N and len(set(d)) == N
        assert np.all(np.diff(prep.ym[s:s + N]) == 1)                    # consecutive calendar months
        end = prep.last[s + N - 1]
        ym_end = m.dates.astype("datetime64[M]")[end]
        assert ym_end == m.dates.astype("datetime64[M]")[prep.first[s + N - 1]]
        assert end == len(m.dates) - 1 or m.dates.astype("datetime64[M]")[end + 1] > ym_end
    assert len(window_starts(len(prep.first), N)) == len(prep.first) - N + 1


def test_monthly_series_uses_every_observation_and_drops_nothing():
    m = random_market(1, n=240, monthly=True)
    ym, first, last = month_grid(m)
    assert len(first) == 240 and np.array_equal(first, last)


# =========================================================================== 5. hand-checked cases
def test_all_time_high_flags_and_next_true_index():
    sig = np.array([100, 110, 110, 90, 80, 111, 100, 112.0])
    assert new_ath_flags(sig).tolist() == [True, True, False, False, False, True, False, True]   # equal close is not a NEW high
    assert next_true_index(np.array([0, 1, 0, 0, 1, 0], bool)).tolist() == [1, 1, 4, 4, 4, 6]


def test_perfect_timing_bottoms_hand_checked():
    #            0    1    2   3   4    5    6   7    8
    sig = np.array([100, 110, 90, 80, 85, 120, 100, 95, 130.0])
    b, c = god_bottoms(sig)
    # episodes: [0,1) bottom 0; [1,5) bottom 3 (80); [5,8) bottom 7 (95); the open episode from 8 has no bottom
    assert b.tolist() == [0, 3, 7] and c.tolist() == [1, 5, 8]


def test_perfect_timing_invests_saved_cash_at_the_exact_bottom():
    sig = np.array([100, 110, 90, 80, 85, 120, 100, 95, 130.0, 130, 130])
    m = make_market(sig, start="2015-01-01")
    prep = Prepared(m, (0.1,))
    # deposits on days 1 and 2 (before the day-3 bottom) go in at 80; a deposit on day 4 (after it) waits for the day-7 bottom;
    # a deposit on day 8 has no later completed episode inside the window (no new high after 130) -> stays cash
    e = prep.exec_index(Strategy("god"), np.array([1, 2, 4, 8]), 10)
    assert e.tolist() == [3, 3, 7, -1]
    # the same deposits seen from a shorter window: the day-7 bottom is not confirmed until day 8
    assert prep.exec_index(Strategy("god"), np.array([1, 2, 4]), 7).tolist() == [3, 3, -1]


def test_threshold_rule_versus_until_ath_rule():
    # down 25% (X=20%) then recovers to -10% without a new high: the literal rule saves new cash, 'until_ath' keeps buying
    px = np.array([100, 100, 75, 75, 90, 90, 90, 90, 101, 101, 101, 101.0])
    m = make_market(px, start="2015-01-01")
    prep = Prepared(m, (0.20,))
    d = np.array([5, 9])
    lit = prep.exec_index(Strategy("dip", 0.20, "threshold"), d, 11)
    stay = prep.exec_index(Strategy("dip", 0.20, "until_ath"), d, 11)
    assert lit.tolist() == [-1, -1]                    # day 5 is only -10%: literal rule keeps the cash (and so does day 9: new high)
    assert stay.tolist() == [6, -1]                    # day 5 is still in dip mode (no new high yet) -> bought at day 6; day 9 is after the new high


def test_fill_convention_for_a_deposit_that_arrives_on_a_fill_day():
    """Flat, then -30% on day 10 (signal) with the order filling on day 11 - the same day a new deposit arrives."""
    px = np.r_[np.full(10, 100.0), 70.0, 72.0, np.full(30, 75.0)]
    m = make_market(px, start="2015-01-01")
    prep = Prepared(m, (0.20,))
    primary, alt = Strategy("dip", 0.20), Strategy("dip", 0.20, same_day=True)
    # primary: the day-11 deposit was not part of the order sized at day 10, so it waits for its OWN signal (day 11) -> fills day 12
    assert prep.exec_index(primary, np.array([5, 11]), 40).tolist() == [11, 12]
    # alternative convention: it joins the order filling on day 11
    assert prep.exec_index(alt, np.array([5, 11]), 40).tolist() == [11, 11]
    # with NO cash waiting at day 10 there is no order to join, so both conventions agree (first deposit on the fill day)
    assert prep.exec_index(alt, np.array([11]), 40).tolist() == [12]
    assert prep.exec_index(primary, np.array([11]), 40).tolist() == [12]
    # only the deposit pending when the signal fired is in the order; a deposit on day 12 (the day AFTER the fill) is not swept
    assert prep.exec_index(alt, np.array([5, 12]), 40).tolist() == [11, 13]
    # a deposit that was itself swept into the day-11 fill leaves no cash behind, so it cannot start an order that the
    # NEXT deposit (day 12) could join: day 12 goes through its own signal (day 12) -> fills day 13
    assert prep.exec_index(alt, np.array([5, 11, 12]), 40).tolist() == [11, 11, 13]


def test_strict_perfect_timing_ignores_episodes_without_a_real_drawdown():
    # highs at days 0, 1, 2 are adjacent (no close between them); day 3-4 is a real dip; new high on day 5
    sig = np.array([100, 110, 120, 100, 105, 130, 130, 130.0])
    assert god_bottoms(sig)[0].tolist() == [0, 1, 3]                  # default: the high itself is the 'bottom' of a no-dip episode
    b, c = god_bottoms(sig, strict=True)
    assert b.tolist() == [3] and c.tolist() == [5]                    # strict: only the real drawdown has a bottom
    m = make_market(sig, start="2015-01-01")
    prep = Prepared(m, (0.1,))
    assert prep.exec_index(Strategy("god"), np.array([0, 1, 2]), 7).tolist() == [0, 1, 3]
    assert prep.exec_index(Strategy("god", strict_bottom=True), np.array([0, 1, 2]), 7).tolist() == [3, 3, 3]
