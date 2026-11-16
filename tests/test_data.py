"""Data-layer tests: pure parsing on hand-made input, plus integration checks on the cached real series."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dipdca import assets, data

CACHED = all((data.CACHE / f).exists() for f in ("yahoo_XIU.TO.csv", "yahoo_idx_SP500TR.csv", "fred_DEXCAUS.csv",
                                                  "boc_TB.CDN.90D.MID.csv", "fred_INTGSTCAM193N.csv"))
needs_data = pytest.mark.skipif(not CACHED, reason="run `python run_all.py` once to fetch and cache the data")

DAILY = ["This file was created by CRSP", "", ",Mkt-RF,SMB,HML,RF",
         "19260701,    0.09,   -0.23,   -0.28,    0.01",
         "19260702,    0.45,   -0.34,   -0.03,    0.01", "", "Copyright"]
MONTHLY = ["header", "", ",Mkt-RF,SMB,HML,RF", "192607,   2.89,  -2.42,  -2.75,   0.22", "192608,  -99.99,  0, 0, 0.25",
           " Annual Factors: January-December ", ",Mkt-RF,SMB,HML,RF", "  1927,  29.47,  -2.04,  -4.59,   3.12"]


def test_french_daily_parser_converts_percent_to_decimal_and_builds_total_market_return():
    f = data.parse_french(DAILY, "daily")
    assert list(f.index) == [pd.Timestamp("1926-07-01"), pd.Timestamp("1926-07-02")]
    assert f["mkt"].tolist() == pytest.approx([(0.09 + 0.01) / 100, (0.45 + 0.01) / 100])      # Mkt = (Mkt-RF) + RF
    assert f["rf"].tolist() == pytest.approx([0.0001, 0.0001])


def test_french_monthly_parser_skips_annual_block_and_rejects_missing_sentinel():
    ok = [ln for ln in MONTHLY if "99.99" not in ln]
    f = data.parse_french(ok, "monthly")
    assert len(f) == 1 and f.index[0] == pd.Timestamp("1926-07-31")              # month-end label; annual 1927 row ignored
    assert f["mkt"].iloc[0] == pytest.approx((2.89 + 0.22) / 100)
    with pytest.raises(ValueError):
        data.parse_french(MONTHLY, "monthly")                                    # -99.99 is a missing-data code, never a return


def test_real_conversion_divides_by_cpi_relative_to_the_first_month():
    dates = pd.date_range("2000-01-31", periods=4, freq="ME")
    cpi = pd.Series([100.0, 101.0, 103.0, 106.0], index=pd.date_range("2000-01-01", periods=4, freq="MS"))
    nominal = np.array([100.0, 101.0, 103.0, 106.0])                              # a nominal index that tracks CPI exactly
    real = data.deflate_monthly(nominal, dates, cpi)
    assert real == pytest.approx([100.0] * 4)                                    # ... is flat in real terms
    grow = data.deflate_monthly(np.array([100.0, 110.0, 121.0, 133.1]), dates, pd.Series([100.0] * 4, index=cpi.index))
    assert grow == pytest.approx([100.0, 110.0, 121.0, 133.1])                   # zero inflation changes nothing
    # 10%/yr nominal growth with 10%/yr inflation -> zero real growth
    d2 = pd.date_range("2000-01-31", periods=25, freq="ME")
    c2 = pd.Series(100.0 * 1.1 ** (np.arange(25) / 12), index=pd.date_range("2000-01-01", periods=25, freq="MS"))
    assert data.deflate_monthly(100.0 * 1.1 ** (np.arange(25) / 12), d2, c2) == pytest.approx(np.full(25, 100.0))


def test_real_conversion_fills_a_single_missing_cpi_month_but_not_longer_gaps():
    idx = pd.date_range("2025-08-01", periods=5, freq="MS")
    cpi = pd.Series([100.0, 102.0, np.nan, 106.0, 108.0], index=idx).dropna()    # Oct-2025 never published (US shutdown)
    dates = pd.date_range("2025-08-31", periods=5, freq="ME")
    real = data.deflate_monthly(np.array([100.0, 102.0, np.sqrt(102.0 * 106.0), 106.0, 108.0]), dates, cpi)
    assert real == pytest.approx([100.0] * 5)                                    # filled log-linearly (geometric mean of neighbours)
    cpi2 = pd.Series([100.0, 110.0, 120.0], index=pd.to_datetime(["2025-08-01", "2025-11-01", "2025-12-01"]))   # TWO missing months
    with pytest.raises(ValueError):
        data.deflate_monthly(np.ones(5), pd.date_range("2025-08-31", periods=5, freq="ME"), cpi2)


@needs_data
def test_xiu_dividend_adjustment_is_applied():
    m = assets.xiu_cad()
    y = data.load_yahoo("XIU.TO")
    yrs = (m.dates[-1] - m.dates[0]).astype("timedelta64[D]").astype(int) / 365.25
    cagr_tr = (m.px[-1] / m.px[0]) ** (1 / yrs) - 1
    cagr_px = (y["close"].iloc[-1] / y["close"].iloc[0]) ** (1 / yrs) - 1
    assert 0.015 < cagr_tr - cagr_px < 0.045            # dividends add ~2.6%/yr for TSX 60; an unadjusted series would add 0
    own = assets.xiu_cad(tr_source="own_reinvest")
    assert own.px[-1] / own.px[0] > m.px[-1] / m.px[0]   # listing every Yahoo 'dividend' as cash over-counts three year-end rows
    assert not np.allclose(m.px / m.px[0], y["close"].to_numpy() / y["close"].iloc[0])


@needs_data
def test_sp500_total_return_exceeds_its_price_index_by_roughly_the_dividend_yield():
    tr = data.load_yahoo("^SP500TR")["close"]
    px = data.load_yahoo("^GSPC")["close"].reindex(tr.index)
    yrs = (tr.index[-1] - tr.index[0]).days / 365.25
    gap = (tr.iloc[-1] / tr.iloc[0]) ** (1 / yrs) - (px.iloc[-1] / px.iloc[0]) ** (1 / yrs)
    assert 0.01 < gap < 0.03


@needs_data
def test_signal_variants_only_change_the_signal_not_the_traded_series():
    a, b = assets.xiu_cad(signal="total_return"), assets.xiu_cad(signal="price")
    assert np.array_equal(a.px, b.px) and not np.array_equal(a.sig, b.sig)
    c, d = assets.sp500_cad(signal="cad"), assets.sp500_cad(signal="usd")
    assert np.array_equal(c.px, d.px) and not np.array_equal(c.sig, d.sig)


@needs_data
def test_sp500_in_cad_is_usd_total_return_times_the_cad_per_usd_rate():
    m = assets.sp500_cad()
    usd = data.load_yahoo("^SP500TR")["close"]
    fx = data.load_fred("DEXCAUS")
    d = pd.Timestamp("2019-06-14")                                               # a normal trading day with an H.10 print
    i = int(np.flatnonzero(m.dates == np.datetime64(d.date()))[0])
    assert m.px[i] == pytest.approx(usd[d] * fx[d])
    h = pd.Timestamp("2019-07-04")                                               # US holiday: no market, no row
    assert np.datetime64(h.date()) not in m.dates


@needs_data
def test_cash_index_is_increasing_and_uses_the_boc_rate_after_2000():
    for m in (assets.xiu_cad(), assets.sp500_cad()):
        assert m.cash_tbill[0] == 1.0 and np.all(np.diff(m.cash_tbill) >= 0)
    m = assets.xiu_cad()
    boc = data.load_boc("TB.CDN.90D.MID")
    d0, d1 = pd.Timestamp("2008-03-03"), pd.Timestamp("2008-03-04")
    i = int(np.flatnonzero(m.dates == np.datetime64(d1.date()))[0])
    prev_rate = boc[boc.index <= d0].iloc[-1]                                    # the rate published on/before the PREVIOUS close
    assert m.cash_tbill[i] / m.cash_tbill[i - 1] == pytest.approx(1 + prev_rate / 100 * 1 / 365)


@needs_data
def test_early_cash_rate_is_lagged_one_month_not_peeking():
    s, meta = data.tbill_rate_series()
    fred = data.load_fred("INTGSTCAM193N")
    # a month's FRED value only becomes available on the first day of the NEXT month
    assert s[pd.Timestamp("1999-10-01")] == fred[pd.Timestamp("1999-09-01")]
    assert pd.Timestamp("1999-09-01") not in s.index or s[pd.Timestamp("1999-09-01")] == fred[pd.Timestamp("1999-08-01")]


@needs_data
def test_real_us_market_matches_nominal_when_cpi_is_flat_and_differs_otherwise():
    nom = assets.us_total_market_usd("monthly")
    real = assets.us_total_market_usd("monthly", real=True)
    assert len(nom.px) == len(real.px)
    assert real.px[0] == pytest.approx(nom.px[0])                                # same base month
    assert real.px[-1] < nom.px[-1] * 0.2                                        # a century of inflation takes most of it back
