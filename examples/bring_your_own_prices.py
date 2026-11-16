"""
Run the same comparison on YOUR OWN price series: build a `Market` from any dividend-adjusted (total-return) price
series and hand it to the engine.  This file is self-contained: it makes up a random-walk price series so that it runs
offline with no downloads.  Replace the "synthetic prices" block with your own data, for example

    px = pd.read_csv("my_prices.csv", index_col=0, parse_dates=True)["Adj Close"].sort_index()

Run it from the repository root:

    python examples/bring_your_own_prices.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))   # not needed after `pip install -e .`

from dipdca.engine import Market, Prepared, Strategy, value_window, window_starts

# ---- synthetic prices (replace with your own: a business-day price series, oldest first, dividends reinvested)
dates = pd.bdate_range("1995-01-02", "2024-12-31")
rng = np.random.default_rng(7)
px = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0004, 0.011, len(dates)))), index=dates)

market = Market(
    name="my asset",
    dates=px.index.to_numpy().astype("datetime64[D]"),
    px=px.to_numpy(),                 # the price you trade
    sig=px.to_numpy(),                # the series the dip signal is read from (usually the same)
    cash_tbill=np.ones(len(px)),      # cash growth index; all ones = idle cash earns nothing
    monthly=False,                    # True only if every observation is a month-end
    notes={},
)

prep = Prepared(market, (0.10, 0.20), rules=("threshold",))
N = 240                               # 20-year windows
starts = window_starts(len(prep.first), N)
for thr in (0.10, 0.20):
    diffs = []
    for s in starts:
        kw = dict(cash="zero", cost=0.0005)                   # idle cash earns 0%; 0.05% spread
        dca = value_window(prep, Strategy("dca"), int(s), N, **kw).final_value
        dip = value_window(prep, Strategy("dip", thr, "threshold"), int(s), N, **kw).final_value
        diffs.append(dip / dca - 1)
    diffs = np.array(diffs)
    print(f"{thr:.0%} dip: beats monthly DCA in {np.mean(diffs > 0):.0%} of {len(diffs)} twenty-year windows; "
          f"median difference {np.median(diffs):+.1%}")
