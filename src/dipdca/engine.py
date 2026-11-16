"""
Core backtest engine.  Pure numpy: no I/O, no pandas, so it can be unit-tested on
hand-made price paths.

Conventions (all spelled out in METHODOLOGY.md)
-----------------------------------------------
* `px`  : tradeable total-return index (dividends reinvested) in the investor's currency.
          Every purchase and the final valuation use this series' CLOSE.
* `sig` : series the dip signal is read from (default: the same as `px`).
* A deposit of `amount` is made at the CLOSE of the first trading day of each month.
* Signals are computed from closes up to and including day t and can only be acted on at
  the close of day t+1 ("buy at the next trading day's price").  DCA has no signal and buys
  at the close of the deposit day.
* Cash earns the cash-growth index `ci` (interest accrues between consecutive closes).
* Every purchase pays `cost` (a proportional spread): shares = cash / (close * (1 + cost)).
  Nothing is ever sold; the final value marks shares at the last close with NO exit cost
  (identical for every strategy, so it cancels in comparisons).
* Final value = shares * last close + any cash still uninvested (with interest).

Strategies
----------
dca   : invest each deposit on its deposit day.
dip   : "threshold" rule - invest all cash held whenever the signal closes >= X% below its
        all-time high (the user's literal rule).  Variant rule="until_ath": once such a
        dip has occurred, keep investing every new deposit until the signal makes a new
        all-time high (Maggiulli's 2021 formulation).
god   : HYPOTHETICAL perfect timing - cash is invested at the exact lowest close between two
        consecutive all-time highs (the bottom of each COMPLETED drawdown episode).  Needs
        hindsight; nobody could execute it.

Because every strategy treats each deposit independently (its execution day depends only
on its own deposit day), a window can be valued exactly with array arithmetic.  The slow,
obviously-correct day-by-day twin lives in reference.py and is compared to this module in
the test-suite.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

DAYS_PER_MONTH = 30.4375


@dataclass(frozen=True)
class Market:
    name: str
    dates: np.ndarray               # datetime64[D], strictly increasing
    px: np.ndarray                  # tradeable total-return index
    sig: np.ndarray                 # signal series (drawdown / all-time-high are read from here)
    cash_tbill: np.ndarray          # cash growth index when cash earns the T-bill rate
    monthly: bool = False           # True: every observation is a month-end (one deposit each)
    notes: dict = field(default_factory=dict)

    def __post_init__(self):
        n = len(self.dates)
        for a in (self.px, self.sig, self.cash_tbill):
            if len(a) != n:
                raise ValueError("market arrays must have equal length")
        if not (np.all(np.diff(self.dates.astype("datetime64[D]").astype(np.int64)) > 0)):
            raise ValueError("dates must be strictly increasing")
        if not (np.all(self.px > 0) and np.all(self.sig > 0)):
            raise ValueError("prices must be positive")

    def cash_index(self, mode: str) -> np.ndarray:
        if mode == "tbill":
            return self.cash_tbill
        if mode == "zero":
            return np.ones(len(self.dates))
        raise ValueError(mode)


@dataclass(frozen=True)
class Strategy:
    kind: str                       # 'dca' | 'dip' | 'god'
    thr: float | None = None        # dip depth as a positive fraction, e.g. 0.10
    rule: str = "threshold"         # 'threshold' | 'until_ath'
    # Convention for a deposit that arrives on the very day a pending dip order fills (the first trading
    # day of a month).  False (primary): the order was sized from the cash on hand when the signal fired,
    # so the new deposit waits for ITS OWN signal at that day's close and fills one day later.
    # True: the deposit is swept into the same-day fill (cash is only deposited, then invested at the same close).
    same_day: bool = False
    # perfect timing only: True = an episode counts only if its lowest close is strictly BELOW the high that started it
    # (no 'bottom' between two adjacent highs, so cash waits for a real drawdown).  Sanity-check variant.
    strict_bottom: bool = False

    @property
    def label(self) -> str:
        if self.kind == "dca":
            return "monthly_dca"
        if self.kind == "god":
            return "perfect_timing_strict" if self.strict_bottom else "perfect_timing"
        return f"dip_{int(round(self.thr * 100))}pct"


# --------------------------------------------------------------------------- calendar
def month_grid(market: Market) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(ym, first_idx, last_idx) for each usable calendar month.

    Daily series: the first and last month of the data are dropped because the data may
    start/stop mid-month (so 'first/last trading day of the month' would be wrong there).
    """
    ym = market.dates.astype("datetime64[M]").astype(np.int64)
    first = np.flatnonzero(np.r_[True, ym[1:] != ym[:-1]])
    last = np.r_[first[1:] - 1, len(ym) - 1]
    ym_u = ym[first]
    if not market.monthly:
        ym_u, first, last = ym_u[1:-1], first[1:-1], last[1:-1]
    return ym_u, first, last


def window_starts(n_months_available: int, n_months: int) -> np.ndarray:
    """Every start-month position that leaves room for `n_months` full months."""
    return np.arange(0, max(0, n_months_available - n_months + 1))


# --------------------------------------------------------------------------- signals
def running_max_and_drawdown(sig: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    runmax = np.maximum.accumulate(sig)
    return runmax, sig / runmax - 1.0


def new_ath_flags(sig: np.ndarray) -> np.ndarray:
    """True where the close is a STRICTLY new all-time high (index 0 counts as the first)."""
    prev = np.r_[-np.inf, np.maximum.accumulate(sig)[:-1]]
    return sig > prev


def next_true_index(mask: np.ndarray) -> np.ndarray:
    """out[i] = smallest j >= i with mask[j], or len(mask) if there is none."""
    idx = np.flatnonzero(mask)
    pos = np.searchsorted(idx, np.arange(len(mask)), side="left")
    if len(idx) == 0:
        return np.full(len(mask), len(mask), dtype=np.int64)
    return np.where(pos < len(idx), idx[np.minimum(pos, len(idx) - 1)], len(mask)).astype(np.int64)


def threshold_mask(sig: np.ndarray, thr: float, rule: str) -> np.ndarray:
    """Days on which a dip-buyer is 'in dip mode' (cash held at the close gets invested next day)."""
    _, dd = running_max_and_drawdown(sig)
    if rule == "threshold":
        return dd <= -thr
    if rule == "until_ath":
        # in dip mode from the first close >= thr below the high until a new all-time high
        episode = np.cumsum(new_ath_flags(sig))
        out = np.zeros(len(sig), dtype=bool)
        deepest = 0.0
        cur = -1
        for i in range(len(sig)):
            if episode[i] != cur:
                cur, deepest = episode[i], 0.0
            deepest = min(deepest, dd[i])
            out[i] = deepest <= -thr
        return out
    raise ValueError(rule)


def god_bottoms(sig: np.ndarray, strict: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """
    Hindsight bottoms.  Split the history at every strictly-new all-time high; each piece
    [a_k, a_{k+1}) is a drawdown episode.  Its bottom is the lowest close in the piece (first
    occurrence).  An episode is only 'completed' (and its bottom knowable, even with
    hindsight) once the next all-time high a_{k+1} has happened, so the final, still-open
    episode has no bottom.  Returns (bottom_idx, confirm_idx = a_{k+1}).
    """
    starts = np.flatnonzero(new_ath_flags(sig))
    bottoms, confirms = [], []
    for k in range(len(starts) - 1):
        s, e = starts[k], starts[k + 1]
        j = s + int(np.argmin(sig[s:e]))
        if strict and not sig[j] < sig[s]:
            continue                                   # adjacent highs: no real drawdown, so no bottom
        bottoms.append(j)
        confirms.append(e)
    return np.array(bottoms, dtype=np.int64), np.array(confirms, dtype=np.int64)


class Prepared:
    """Signal-side precomputation for one market (independent of window and cash/cost mode)."""

    def __init__(self, market: Market, thresholds: tuple[float, ...], rules: tuple[str, ...] = ("threshold", "until_ath")):
        self.market = market
        self.days = market.dates.astype("datetime64[D]").astype(np.int64)
        self.ym, self.first, self.last = month_grid(market)
        self.nxt: dict[tuple[float, str], np.ndarray] = {}
        for thr in thresholds:
            for rule in rules:
                self.nxt[(thr, rule)] = next_true_index(threshold_mask(market.sig, thr, rule))
        self.god_b, self.god_c = god_bottoms(market.sig)
        self.god_bs, self.god_cs = god_bottoms(market.sig, strict=True)

    # ---- execution day of each deposit (-1 = never executed inside the window)
    def exec_index(self, strat: Strategy, d: np.ndarray, end: int) -> np.ndarray:
        if strat.kind == "dca":
            return d.copy()
        if strat.kind == "dip":
            nx = self.nxt[(strat.thr, strat.rule)]
            e = nx[d] + 1                                      # first signal close on/after the deposit; act at the NEXT close
            if strat.same_day and len(d) > 1:
                # alternative convention: a deposit joins the order placed at yesterday's close.  That order exists only
                # if cash was waiting, i.e. the PREVIOUS deposit's first signal close was exactly yesterday AND that
                # previous deposit was not itself swept into an earlier fill (then it left no cash behind).  Earlier
                # deposits cannot matter: the first-signal index is non-decreasing in the deposit day.
                cand = np.zeros(len(d), dtype=bool)
                cand[1:] = nx[d[:-1]] + 1 == d[1:]
                hit = np.zeros(len(d), dtype=bool)
                for i in np.flatnonzero(cand):
                    hit[i] = not hit[i - 1]
                e = np.where(hit, d, e)
            return np.where(e <= end, e, -1)
        if strat.kind == "god":
            gb, gc = (self.god_bs, self.god_cs) if strat.strict_bottom else (self.god_b, self.god_c)
            k = np.searchsorted(gb, d, side="left")
            kk = np.minimum(k, max(len(gb) - 1, 0))
            ok = (k < len(gb))
            if len(gb):
                ok &= gc[kk] <= end                            # bottom must be confirmed inside the window
                return np.where(ok, gb[kk], -1)
            return np.full(len(d), -1, dtype=np.int64)
        raise ValueError(strat.kind)


@dataclass(frozen=True)
class WindowResult:
    final_value: float
    equity_value: float
    cash_value: float
    months_in_cash: float       # calendar months with ANY uninvested cash (union of holding spells)
    contributions: float


def value_window(prep: Prepared, strat: Strategy, s_pos: int, n_months: int, *, cash: str, cost: float,
                 amount: float = 500.0) -> WindowResult:
    m = prep.market
    px, ci = m.px, m.cash_index(cash)
    d = prep.first[s_pos:s_pos + n_months]
    end = int(prep.last[s_pos + n_months - 1])
    e = prep.exec_index(strat, d, end)
    done = e >= 0

    amt = amount * ci[e[done]] / ci[d[done]]                   # cash (with interest) at execution
    shares = amt / (px[e[done]] * (1.0 + cost))
    equity = float(shares.sum() * px[end])
    leftover = float((amount * ci[end] / ci[d[~done]]).sum())

    # months holding any cash: union of [deposit day, execution day) spells (execution days are
    # non-decreasing in the deposit day for every strategy, so a one-pass union is exact)
    stop = np.where(done, e, end)
    t0, t1 = prep.days[d], prep.days[stop]
    spell = np.r_[np.minimum(t1[:-1], t0[1:]) - t0[:-1], t1[-1] - t0[-1]]
    return WindowResult(equity + leftover, equity, leftover, float(spell.sum()) / DAYS_PER_MONTH, amount * n_months)
