"""
Reference simulator: a deliberately slow, day-by-day, obviously-correct twin of engine.py.

It holds an explicit cash balance and share count, loops over every trading day, and uses
none of the engine's vectorised tricks.  It serves two purposes:
  1. the test-suite checks that the fast engine reproduces it to floating-point precision on
     thousands of random price paths (cross-implementation check), and
  2. it produces the daily portfolio path for the example-window chart.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .engine import DAYS_PER_MONTH, Market, Strategy


@dataclass
class PathResult:
    final_value: float
    equity_value: float
    cash_value: float
    months_in_cash: float
    contributions: float
    value: np.ndarray          # portfolio value at every close in the window
    cash: np.ndarray           # uninvested cash at every close
    contributed: np.ndarray    # cumulative deposits
    buys: list                 # (index, shares, cost_paid)


def _dip_mask(sig, thr, rule):
    """Naive left-to-right state machine over the FULL history (not just the window)."""
    mask, runmax, deepest = [], -np.inf, 0.0
    for x in sig:
        if x > runmax:          # strictly new all-time high -> new episode
            runmax, deepest = x, 0.0
        deepest = min(deepest, x / runmax - 1.0)
        dd = x / runmax - 1.0
        mask.append(dd <= -thr if rule == "threshold" else deepest <= -thr)
    return mask


def _god_bottom_days(sig, end, strict=False):
    runmax, highs = -np.inf, []
    for i, x in enumerate(sig):
        if x > runmax:
            runmax = x
            highs.append(i)
    out = set()
    for a, b in zip(highs, highs[1:]):
        if b > end:             # episode not complete inside the window -> bottom unknowable
            break
        seg = list(sig[a:b])
        if strict and not min(seg) < seg[0]:
            continue                                   # adjacent highs: no real drawdown inside the episode
        out.add(a + seg.index(min(seg)))
    return out


def simulate(market: Market, strat: Strategy, start: int, end: int, *, cash: str, cost: float,
             amount: float = 500.0) -> PathResult:
    px, sig, ci, dates = market.px, market.sig, market.cash_index(cash), market.dates
    ym = dates.astype("datetime64[M]").astype(np.int64)
    days = dates.astype("datetime64[D]").astype(np.int64)

    mask = _dip_mask(sig, strat.thr, strat.rule) if strat.kind == "dip" else None
    bottoms = _god_bottom_days(sig, end, strat.strict_bottom) if strat.kind == "god" else None

    bal, shares, pending = 0.0, 0.0, False
    contributions, cash_days = 0.0, 0.0
    n = end - start + 1
    value, cashpath, contrib, buys = np.zeros(n), np.zeros(n), np.zeros(n), []

    def buy(i):
        nonlocal bal, shares
        s = bal / (px[i] * (1.0 + cost))
        shares += s
        buys.append((i, s, bal))
        bal = 0.0

    sweep = strat.kind == "dip" and strat.same_day         # alternative fill convention (see engine.Strategy)

    def deposit_today(i):
        return i == start or ym[i] != ym[i - 1]            # first trading day of a month

    for i in range(start, end + 1):
        if i > start:
            bal *= ci[i] / ci[i - 1]                       # overnight interest on cash
        if sweep and deposit_today(i):                     # deposit lands BEFORE yesterday's order fills
            bal += amount
            contributions += amount
        if pending:                                        # yesterday's signal, executed at today's close
            if bal > 0:
                buy(i)
            pending = False
        if not sweep and deposit_today(i):                 # primary convention: deposit lands AFTER the fill
            bal += amount
            contributions += amount
        if strat.kind == "dca":
            if bal > 0:
                buy(i)
        elif strat.kind == "dip":
            if bal > 0 and mask[i]:
                pending = True                             # decided at this close, filled at the next
        elif strat.kind == "god":
            if bal > 0 and i in bottoms:
                buy(i)
        else:
            raise ValueError(strat.kind)

        if bal > 0 and i < end:
            cash_days += days[i + 1] - days[i]
        value[i - start] = shares * px[i] + bal
        cashpath[i - start] = bal
        contrib[i - start] = contributions

    eq = shares * px[end]
    return PathResult(eq + bal, eq, bal, cash_days / DAYS_PER_MONTH, contributions, value, cashpath, contrib, buys)
