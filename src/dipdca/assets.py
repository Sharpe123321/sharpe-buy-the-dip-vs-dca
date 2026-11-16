"""Build the Market objects the study runs on (data.py supplies the raw series)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import data
from .engine import Market


def _d(index: pd.DatetimeIndex) -> np.ndarray:
    return index.to_numpy().astype("datetime64[D]")


def xiu_cad(refresh: bool = False, signal: str = "total_return", tr_source: str = "adj_close") -> Market:
    """
    XIU.TO (iShares S&P/TSX 60 ETF) in CAD, dividends reinvested, Oct-1999 onward.

    tr_source = 'adj_close'     (default) Yahoo's dividend-adjusted close.  Chosen because three
                                year-end 'dividends' in Yahoo's Dividends column (notably $0.46 on
                                2000-12-27) did not lower XIU's price and are not cash payments;
                                Adj Close correctly ignores them (see scripts/audit_data.py).
                'own_reinvest'  our own reinvestment of every listed dividend - sensitivity only
                                (ends 4.3% higher over 27 years because of those three rows).
    signal    = 'total_return'  (default) reads dips from the same total-return index;
                'price'         reads them from the raw (dividend-unadjusted) price - sensitivity only.
    """
    y = data.load_yahoo("XIU.TO", refresh)
    if tr_source == "adj_close":
        tr = y["adj_close"]
    elif tr_source == "own_reinvest":
        tr = data.total_return_index(y["close"], y["dividends"])
    else:
        raise ValueError(tr_source)
    rate, rate_meta = data.tbill_rate_series(refresh)
    ci = data.cash_growth_index(tr.index, rate)
    sig = tr.to_numpy() if signal == "total_return" else y["close"].to_numpy()
    return Market("XIU (TSX 60 ETF), CAD, total return", _d(tr.index), tr.to_numpy(), sig, ci, False,
                  {"asset": "XIU.TO", "currency": "CAD", "signal": signal, "tr_source": tr_source, **rate_meta})


def sp500_cad(refresh: bool = False, signal: str = "cad") -> Market:
    """
    S&P 500 total return (^SP500TR, USD, 1988 onward) converted to CAD with the daily
    CAD-per-USD rate (FRED DEXCAUS, forward-filled over US days with no H.10 print).
    signal = 'cad' reads dips from the CAD series; 'usd' from the USD index (sensitivity).
    """
    y = data.load_yahoo("^SP500TR", refresh)["close"]
    fx_raw = data.load_fred("DEXCAUS", refresh)
    fx = fx_raw.reindex(y.index.union(fx_raw.index)).ffill().reindex(y.index)
    if fx.isna().any():
        raise ValueError("FX missing for some S&P 500 dates")
    cad = y * fx
    rate, rate_meta = data.tbill_rate_series(refresh)
    ci = data.cash_growth_index(cad.index, rate)
    sig = cad.to_numpy() if signal == "cad" else y.to_numpy()
    return Market("S&P 500 total return, CAD", _d(cad.index), cad.to_numpy(), sig, ci, False,
                  {"asset": "^SP500TR x DEXCAUS", "currency": "CAD", "signal": signal, **rate_meta})


def sp500_usd(refresh: bool = False) -> Market:
    """S&P 500 total return in USD (^SP500TR, 1988 onward).  Sanity-check use only: cash is 0% (cash index = 1)."""
    y = data.load_yahoo("^SP500TR", refresh)["close"]
    return Market("S&P 500 total return, USD", _d(y.index), y.to_numpy(), y.to_numpy(), np.ones(len(y)), False,
                  {"asset": "^SP500TR", "currency": "USD", "cash": "not modelled (0% only)"})


def us_total_market_usd(freq: str = "daily", refresh: bool = False, real: bool = False,
                        month_avg: bool = False) -> Market:
    """
    CRSP value-weighted US total market (Fama/French library), USD total return, 1926 onward.
    Cash earns the library's 1-month T-bill rate.  Used for the long-history sanity check
    against Maggiulli.

    real=True (monthly only) deflates the index by US CPI (FRED CPIAUCNS), reproducing his
    "S&P 500 with dividends, adjusted for inflation" setup.  In real mode the 'zero' cash
    option means 0% REAL interest (idle cash keeps its purchasing power, as in a constant-real-
    dollar simulation) and the 'tbill' option is the nominal T-bill rate valued in real dollars.
    """
    f = data.load_french(freq, refresh)
    px = 100.0 * np.cumprod(np.r_[1.0, 1.0 + f["mkt"].to_numpy()[1:]])
    ci = data.cash_growth_index_from_returns(f["rf"].to_numpy())
    idx = f.index
    label = f"US total market (CRSP), USD, {freq}"
    if month_avg:
        # Shiller-style monthly series: the AVERAGE of the daily index within each month (sensitivity only)
        if freq != "daily":
            raise ValueError("month_avg is built from the daily series")
        m = data.load_french("monthly", refresh)
        avg = pd.Series(px, index=idx).resample("ME").mean()
        if not avg.index.equals(m.index):
            raise ValueError("daily and monthly French calendars disagree")
        px, idx = avg.to_numpy(), avg.index
        ci = data.cash_growth_index_from_returns(m["rf"].to_numpy())
        freq, label = "monthly", label.replace("daily", "monthly average of daily")
    if real:
        if freq != "monthly":
            raise ValueError("real-terms conversion is only defined on monthly series")
        cpi = data.load_fred("CPIAUCNS", refresh)
        px = data.deflate_monthly(px, idx, cpi)
        ci = data.deflate_monthly(ci, idx, cpi)
        label += ", real (CPI-adjusted)"
    return Market(label, _d(idx), px, px.copy(), ci, freq == "monthly",
                  {"asset": "Fama-French Mkt", "currency": "USD", "freq": freq, "real": real, "month_avg": month_avg})
