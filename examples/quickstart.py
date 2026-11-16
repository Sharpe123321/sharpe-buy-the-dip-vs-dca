"""
Smallest useful example: score "buy the dip" against monthly DCA over every 10-year window of XIU, using this
repository's engine directly.

Run it from the repository root (the first run downloads XIU's data into data/cache/):

    python examples/quickstart.py

Expected: about 200 of 205 windows, the same as the 98% in the README.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))   # not needed after `pip install -e .`

from dipdca import assets
from dipdca.engine import Prepared, Strategy, value_window, window_starts

market = assets.xiu_cad()                                    # XIU total return in CAD, with the T-bill cash series
prep = Prepared(market, (0.10,), rules=("threshold",))       # prepare the 10% dip rule once, reuse it for every window
N = 120                                                      # window length in months (10 years)
starts = window_starts(len(prep.first), N)                   # every start month that leaves a full window
kw = dict(cash="tbill", cost=0.0005)                          # idle cash earns the T-bill rate; 0.05% spread per purchase

wins = 0
for s in starts:
    dca = value_window(prep, Strategy("dca"), int(s), N, **kw).final_value
    dip = value_window(prep, Strategy("dip", 0.10, "threshold"), int(s), N, **kw).final_value
    wins += dip > dca
print(f"The 10% dip-buyer beat monthly DCA in {wins} of {len(starts)} ten-year windows ({wins / len(starts):.0%}).")
