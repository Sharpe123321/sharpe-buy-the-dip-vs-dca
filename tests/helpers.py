"""Synthetic-market builders shared by the tests (no network, no data files)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from dipdca import data
from dipdca.engine import Market


def make_market(px, *, start="2015-01-01", rate_pct=0.0, sig=None, monthly=False, dates=None, name="synthetic"):
    """Market from a price list.  Daily markets use consecutive business days unless `dates` is given."""
    px = np.asarray(px, dtype=float)
    if dates is None:
        if monthly:
            dates = pd.date_range(start, periods=len(px), freq="ME")
        else:
            dates = pd.bdate_range(start, periods=len(px))
    dates = pd.DatetimeIndex(dates)
    rate = rate_pct if isinstance(rate_pct, pd.Series) else pd.Series([float(rate_pct)], index=[dates[0] - pd.Timedelta(days=1)])
    ci = data.cash_growth_index(dates, rate)
    return Market(name, dates.to_numpy().astype("datetime64[D]"), px, px.copy() if sig is None else np.asarray(sig, float), ci, monthly)


def random_market(seed, n=1700, *, monthly=False, rates=True):
    """Fat-tailed random walk with crashes (so every dip threshold gets exercised) and a time-varying cash rate."""
    rng = np.random.default_rng(seed)
    scale = 0.045 if monthly else 0.012
    r = rng.normal(0.0004 if not monthly else 0.008, scale, n)
    crashes = rng.random(n) < (0.004 if not monthly else 0.03)
    r[crashes] -= rng.uniform(0.04, 0.10) * (3 if monthly else 1)
    px = 100.0 * np.cumprod(1.0 + np.clip(r, -0.6, None))
    if monthly:
        dates = pd.date_range("1980-01-31", periods=n, freq="ME")
    else:
        dates = pd.bdate_range("2010-01-01", periods=n)
    if rates:
        steps = pd.Series(rng.uniform(0.0, 6.0, 12), index=pd.date_range(dates[0] - pd.Timedelta(days=1), dates[-1], periods=12))
    else:
        steps = 0.0
    return make_market(px, dates=dates, rate_pct=steps, monthly=monthly)
