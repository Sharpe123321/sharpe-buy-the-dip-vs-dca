# Methodology

Study 1 of *Sharpe*: **in Canada, does "buying the dip" beat investing a fixed amount every month?**

This document says, in plain English, exactly what was done, every assumption made, what was checked, and what is
not reliable. Sections 1-9 describe the main study (XIU and the S&P 500 in CAD). Section 10 describes the follow-ups
added later: a simplified SPY-only 25-year run, the SPY-vs-XIU comparison, and the three newsletter charts. If something here disagrees with the code, the code is the truth and this document has a bug: please
open an issue.

---

## 1. The question and the three strategies

An investor has **$500 of new money every month**. Three ways to invest it:

| Strategy | Rule |
|---|---|
| **Monthly (DCA)** | Buy $500 of the index at the close of the first trading day of every month. |
| **Buy the dip** | Save each $500 in cash. Whenever the index closes at least **X% below its all-time high** (X = 5, 10, 20, 30), invest *all* the cash held. The signal uses closes up to and including day *t*; the purchase happens at the **next trading day's close**. |
| **Perfect timing** *(hypothetical)* | Save cash and invest it only at the exact lowest close between two consecutive all-time highs. This needs hindsight; nobody can do it. It is a ceiling, not a strategy, and replicates the thought experiment in Nick Maggiulli's "Even God Couldn't Beat Dollar-Cost Averaging". |

All three put in the same total cash. A strategy that has not invested some cash by the end of a window is credited
with that cash (plus interest) in its final value.

**The score** for one window is `final value of strategy / final value of monthly DCA - 1`. "Beats monthly" means
that number is strictly positive.

## 2. Data

Nothing from the providers is committed to the repository: every series is fetched from its public source at run time and cached
locally (`data/cache/`, git-ignored, with a `MANIFEST.json` of fetch times and SHA-256 checksums).

| Series | Used for | Source | Range |
|---|---|---|---|
| **XIU.TO** adjusted close | Canadian equities (iShares S&P/TSX 60 ETF), dividends reinvested | Yahoo Finance via `yfinance` | 1999-10-04 on |
| **^SP500TR** | S&P 500 total return (dividends reinvested, USD) | Yahoo Finance via `yfinance` | 1988-01-04 on |
| **DEXCAUS** | CAD per USD, to convert the S&P 500 to CAD | FRED (Federal Reserve H.10) | 1971 on |
| **TB.CDN.90D.MID** | Cash rate: Canadian 3-month T-bill yield, daily | Bank of Canada Valet API | 2001-01-02 on |
| **INTGSTCAM193N** | Cash rate before 2001 only: Canadian T-bill rate, monthly | FRED (IMF) | to 2017-04 |
| **Fama/French US market + T-bill** | Long-history US sanity check only (CRSP total market, USD) | Kenneth French Data Library | 1926-07 on |
| **CPIAUCNS** | US CPI, for the *real-terms* sanity check only | FRED (BLS) | 1913 on |
| **SPY** adjusted close | Section 10 only: the SPY-only 25-year run and the SPY-vs-XIU comparison | Yahoo Finance via `yfinance` | 1993-01-29 on |
| **DGS3MO** | Section 10 only: cash rate for the SPY-only run (US 3-month Treasury constant-maturity yield, daily) | FRED | 1981-09 on |
| ^GSPTSE, ^GSPC, BoC FXUSDCAD | **Audit cross-checks only**, never in a result | Yahoo / Bank of Canada | various |

**Why XIU and not the TSX Composite?** There is no free, long, dividend-adjusted TSX Composite total-return
series. XIU has the longest history of a broad Canadian ETF (about 27 years). It holds the 60 largest Canadian
companies, so it is large-cap-tilted.

**Why `Adj Close` for XIU?** Yahoo's `Dividends` column contains three year-end "distributions" (2000-12-27 $0.46,
2003-12-29, 2004-12-29) that Yahoo's own `Adj Close` does not apply. For the largest, on 2000-12-27, XIU lagged the
TSX Composite by only 0.7% when a $0.46 cash payout (3.5% of price) would imply 3.5%, an 11.7-sigma miss: the
payout did not lower the price, so it looks like a reinvested non-cash distribution. The two small ones (about
0.4-0.5% of price) cannot be tested statistically. Counting all three as cash (our own reinvestment arithmetic)
would overstate XIU's 27-year total return by 4.3%. We use `Adj Close` and run the alternative as a sensitivity
(section 9). This is the author's reading of the evidence, not confirmed with iShares.

### Data audit (`scripts/audit_data.py`, output in `results/data_audit.md`)

39 programmatic checks, run on every execution; **0 FAIL, 0 WARN, 30 PASS, 9 INFO** at the time of writing. They cover
gaps, stale prices, outliers, split-like jumps, weekend rows, and **cross-checks against independent series**:

- Our own dividend reinvestment vs Yahoo's `Adj Close`: agree to 5e-4 on 6,807 of 6,810 days; the three that
  differ are the late-December distributions above.
- `^SP500TR` vs the S&P 500 *price* index `^GSPC`: daily-return correlation 0.9996; the excess is +2.1%/yr, i.e. the
  dividend yield.
- FRED CAD/USD vs the Bank of Canada's own CAD/USD (2017+): mean absolute difference 0.0009 CAD.
- FRED/IMF T-bill vs the Bank of Canada T-bill over their 2001-2017 overlap: mean absolute difference 0.05 percentage points.
- French daily returns compounded within each month vs the French monthly file; CRSP vs `^SP500TR` monthly correlation 0.989.
- **Yahoo's SPY history is not used in the main study** (the SPY-only run in section 10 is the one exception, and checks it against `^SP500TR`): its pre-2009 daily closes disagree with the index on volatile days (e.g.
  2000-01-07: SPY +5.8%, index +2.7%) while `^SP500TR` matches `^GSPC`.

## 3. Every assumption

**Timing**
1. $500 is deposited at the **close of the first trading day of each month** of that asset's own market calendar.
   Monthly DCA buys at that same close.
2. A dip signal on day *t* uses only closes up to *t*. The fill is at the **close of day *t+1***. No intraday data
   and no opens are used anywhere.
3. A deposit that arrives on the very day a pending dip order fills is **not** part of that order (the order was
   sized from cash on hand when the signal fired); it waits for its own signal and fills the following day. The
   other reasonable convention (the deposit joins that day's fill) is run as a sensitivity: it moves win rates by at
   most 0.3 percentage points.
4. The **all-time high is the running maximum of the series since the data begins** (XIU: Oct 1999; S&P 500: Jan
   1988). It is not reset at the start of a window, so a window that starts in a deep drawdown sees that drawdown.
   Consequence: highs reached *before* the data starts are unknown (for example the August 1987 S&P 500 peak).
5. The dip is measured on the **total-return series** (the same series that is traded). Reading it from the
   price-only index instead changes the XIU results materially at small thresholds (section 9).

**Money**
6. **Cash earns the Canadian 3-month T-bill yield** (Bank of Canada daily series from 2001; before that, the monthly
   IMF/FRED series, each month's value used only from the *first day of the following month*, so no peeking).
   Interest is simple actual/365, accrued between consecutive closes using the rate published on or *before* the
   earlier close. A second version of every result has cash earning **0%**. We do not model a high-interest savings
   account separately: the 3-month T-bill is the only free, long, clean Canadian cash series.
7. **Cost: $0 commission and a 0.05% spread on every purchase**, modelled as paying `close x 1.0005`. We read
   "0.05% spread" conservatively as the full amount, not half. Every dollar pays the same proportion regardless of
   strategy, so the spread lowers all final values but **leaves the comparison essentially unchanged**; results are
   shown with and without it. Nothing is sold, so there is no exit cost; the final value is marked at the last close.
8. **Dividends are reinvested** (the series are total-return). No taxes, no US dividend withholding tax (^SP500TR is
   a *gross* index), no ETF management fees beyond what is already inside XIU's price, no FX conversion fees.
9. The S&P 500 is converted at the **FRED/Fed H.10 noon New York CAD-per-USD rate** (forward-filled, at most a few
   days, over US days with no print) applied to the 4pm index close. The signal for the S&P 500 is read from the
   **CAD** series (sensitivity: read from the USD index).
10. Canadian results are **nominal**. The US sanity check is run both nominal and real.

**Windows**
11. Every possible **start month** is a window; horizons are 10, 20 and 30 years (30 only where the data allows:
    S&P 500 yes, XIU no). A window starts with the first deposit on the first trading day of the start month and is
    valued at the **last trading day of its final month**. The first and last calendar month in each dataset are
    dropped because the data may start or stop mid-month.
12. Window counts: XIU 205 (10y) and 85 (20y); S&P 500 in CAD 346 (10y), 226 (20y), 106 (30y).

**Perfect timing**
13. History is cut at every *strictly new* all-time high. The bottom of each stretch is its lowest close. Cash that has
    been deposited by that day is invested at that close (spread and interest still apply). Cash deposited *after* a
    bottom waits for the **next** bottom. A bottom only counts once the next all-time high confirms it, inside the
    window; cash still waiting at the end is held and counted at its value. Where two highs are adjacent the "bottom"
    is the high itself. A stricter variant that ignores such episodes is run only in the sanity check.

**"Stay-invested" rule (variant of the dip rule)**: once a dip of X% has occurred, keep investing every new deposit
immediately until the index makes a new all-time high, then go back to saving. This is Maggiulli's 2021 wording.
Our primary rule is the literal one in the brief (invest only while the close is at least X% below the high); the
variant is reported alongside it in `results/summary_*.csv`.

**Statistics**
14. *Ending-value difference* is in percent of the monthly-DCA ending value. *Months in cash* is the number of
    calendar months (30.4375 days) during which the portfolio held **any** uninvested cash, counting overlapping
    cash spells once. Monthly DCA is always zero.
15. `approx_independent_windows` = months of usable data / months in the window. It is how many non-overlapping
    periods the data really contains.

## 4. What the headline numbers mean, and what they do not

The rolling windows **overlap almost completely**: two windows that start a month apart share 99% of their history.
XIU's 27 years hold about **2.7 independent 10-year periods and 1.4 independent 20-year periods**; the S&P 500's 38
years hold about 3.9 / 1.9 / 1.3 for 10 / 20 / 30 years. A bar reading "100% of windows" therefore means "in the one
or two eras this data contains", not a 100% probability. **We do not report confidence intervals**: standard
errors computed across overlapping windows would be badly overconfident, and honest ones would be too wide to be
informative with one or two independent periods.

## 5. Verification (`tests/`, 59 tests, all passing)

- **No look-ahead.** Cutting the history at any day never changes a fill made on or before that day, for DCA and
  every dip rule. The control: the perfect-timing strategy *does* fail this test (it is hindsight by construction),
  so the test can fail. A hand-built path checks the fill is at the close of the day *after* the signal, at that
  day's price, and that the fill *day* cannot depend on the fill-day price.
- **Cash accounting.** With zero interest and zero cost, money spent plus cash left equals contributions for every
  strategy. Interest accrues only on cash. DCA never holds cash and pays the spread on every dollar. A market that
  only rises leaves the dip-buyer wholly in cash, and that cash (plus interest) is in its final value.
- **Dividend adjustment.** Hand-built dividend arithmetic; XIU's total-return CAGR exceeds its price-only CAGR by
  2.6%/yr; the S&P 500 total-return index exceeds its price index by about the dividend yield.
- **Cross-implementation.** The fast engine (`engine.py`) must equal a deliberately slow day-by-day simulator
  (`reference.py`) to 1e-9 on **over 5,000 random-path windows** (daily and monthly data, every strategy, cash and
  cost variant), and the two agree to about 4e-15 on real XIU and S&P 500 windows. A *separately written second
  implementation* (not part of this repository) agreed with the engine to 1.3e-15 across 8,640 real-data
  comparisons once both used the same fill convention; the only difference it exposed was assumption 3 above.
- **Mutation testing.** Nine deliberate bugs were injected into the engine and data code (fill on the signal day,
  wrong threshold, no spread, inverted interest, unconfirmed bottoms, wrong first month, dropped dividends, no CPI
  deflation, a broken fill-convention rule). The suite failed on every one.

Engine correctness rests on these tests. It does **not** rest on matching Maggiulli (next section).

## 6. Sanity check against Maggiulli: **not reproduced**

The brief asked for perfect timing on the S&P 500 in USD over a long history and expected DCA to win in roughly 70%
of periods, as Maggiulli reports. **We did not land there, and we have not established why.**

What his two posts say, as relayed from their text (his charts could not be read, and his data and code are not public):

- *"Even God Couldn't Beat Dollar-Cost Averaging"* (2019): perfect-foresight buy-the-dip vs DCA, **40-year** windows,
  start years 1920-1988, US stocks with dividends **adjusted for inflation**, monthly data. Buy-the-dip
  underperforms DCA "over 70% of the time".
- *"Why Buying the Dip is a Terrible Investment Strategy"* (2021): threshold rules, **20-year** windows, 1920-2020.
  Roughly a one-in-four chance of beating DCA at 10-20% thresholds, nearly 40% at 50%. The post calls the earlier
  article "a bit too extreme". The 70% figure belongs to the first post only.

We ran the same questions on US data (CRSP total market, 1926-2026; 0% interest on cash, no costs, as he assumed):

| Variant (perfect timing, % of windows it **beats** DCA) | 20-year | 40-year |
|---|---:|---:|
| Daily, nominal | 55% | 55% |
| Monthly, month-end, nominal | 58% | 56% |
| Monthly, month-end, **real** | 47% | 50% |
| Monthly **average** prices (Shiller-style), nominal | 49% | 52% |
| Monthly average prices, **real** (closest to his setup) | 42% | 45% |
| Stricter perfect-timing definition (ignore episodes with no real drawdown), same five rows in the same order | 57 / 42 / 48 / 32 / 42% | 59 / 51 / 54 / 31 / 45% |
| S&P 500 total return, USD, 1988-2026 (10 / 20 / 30 years) | 67% / 83% / 100% | |

- Moving toward his setup (real returns, monthly averages) lowers the figure from about 56% to about 45%, but not to
  about 30%.
- One of the ten combinations (monthly-average prices, **nominal**, strict bottoms) gives 32% and 31%. His series
  was real, and the real version of that same combination gives 42% and 45%, so we treat this as a coincidence
  rather than an explanation.
- Across the ten combinations at 40 years the answer ranges from 31% to 59% (45% to 59% in nine of them), depending on
  definition and data choices that his post does not fully pin down.
- For the 2021 post's threshold rule on the closest match (real, monthly-average prices, "stay-invested" rule,
  20-year windows) the win rate is 28% at 10%, 16% at 20% and 20% at 30%: the same ballpark as his roughly 25%.
  On our primary daily nominal data it is 0%, 17% and 2%.
- The result is dominated by eras, not by a stable tendency (`results/sanity_check_by_start_year.csv`). With 40-year
  windows on daily nominal data, perfect timing beats DCA in **every** window starting 1950-1973 and 1976-1983 and in
  **none** starting 1926-1948: in the second group a 12.6-year stretch (July 1932 bottom, February 1945 next high)
  leaves every dollar idle waiting for the next bottom.

Likely reasons for the gap, **none of them confirmed**: differences in the exact strategy definition, in the data
series (Shiller's 1871-based S&P composite vs CRSP, which start 1920 vs 1926), and in the sample (his windows begin
in 1920).

## 7. Limitations

- **Short Canadian history.** About 27 years, one broad large-cap ETF, one or two independent 20-year periods, no
  30-year horizon. The XIU sample starts just before the dot-com crash; every 20-year window contains the
  2008-09 crash and most contain the 2020 crash.
- **XIU is the TSX 60, not the TSX Composite**, and Yahoo is an unofficial source with no SLA. Its `Dividends` column
  contained the three questionable rows above.
- **The result depends on the market and era.** XIU and the S&P 500 (converted to CAD) point in *opposite*
  directions for the same rules. Section 10.2 tests the most obvious market-level explanations (time spent below the
  high, number and depth of drawdowns, recovery time) and finds they do **not** explain it; the cause is still
  unknown. Other plausible explanations (index composition, the timing of crashes relative to deposits, CAD/USD
  swings) remain untested conjecture.
- **Fragile at larger dips.** At the 20-30% thresholds, small changes (how dividends are counted, whether cash
  earns interest, price vs total-return signal) swing the XIU win rate by tens of points (section 9).
- **No taxes, withholding tax, account types (TFSA/RRSP), high-interest-savings rates, or fund fees beyond what is in
  the prices.** Cash earns the T-bill yield, which is not what every bank pays.
- **Behaviour is not modelled.** The study assumes the investor follows the rule perfectly.
- **Past data only.** None of this predicts the future, and nothing here is investment advice.

## 8. Reproducing

```
python -m venv .venv && .venv/Scripts/activate      # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python run_all.py            # audit -> tests -> sanity check -> study -> charts -> tables
python run_all.py --refresh  # re-download every input first (results will then change with new data)
```

`run_all.py` also runs the section 10 scripts at the end.

`requirements-lock.txt` pins the versions used. Results were produced from data fetched on 2026-11-15; later runs
include newer prices. The French library files for this run were copied from a local cache of the same public
files because the Dartmouth server refused connections that day (see `data/cache/MANIFEST.json`); the code fetches
them from Dartmouth on a clean machine. That cached copy ends 2026-07-31, while Dartmouth now serves data to
2026-09-30, so a fresh run adds two months and two windows; the sanity-check win rates move by at most 0.16
percentage points and the conclusion is unchanged. A full `run_all.py` from a fresh clone (2026-11-15) passed all 59
tests and reproduced the main results to within 0.05 percentage points.

## 9. Sensitivity (all in `results/sensitivity.csv` and `results/summary_*.csv`)

Win rate for the 10-year / 20-year horizon, primary settings unless stated:

| XIU | 5% dip | 10% dip | 20% dip | 30% dip | Perfect timing |
|---|---:|---:|---:|---:|---:|
| **Primary** | 15 / 0 | 98 / 100 | 67 / 84 | 44 / 59 | 24 / 0 |
| Cash earns 0% | 0 / 0 | 92 / 100 | 47 / 21 | 25 / 0 | 14 / 0 |
| No spread | 15 / 0 | 98 / 100 | 67 / 84 | 44 / 59 | 24 / 0 |
| "Stay-invested" rule | 19 / 4 | 98 / 100 | 91 / 89 | 78 / 100 | n/a |
| Dips read from price-only index | 61 / 56 | 98 / 100 | 83 / 91 | 30 / 0 | 42 / 35 |
| Own reinvestment of every Yahoo "dividend" | 15 / 0 | 98 / 100 | 54 / 76 | 43 / 11 | 24 / 13 |
| Deposit joins the same-day fill | 15 / 0 | 98 / 100 | 67 / 84 | 44 / 59 | 24 / 0 |


## 10. Follow-ups: the SPY-only run, "why was Canada different?", and the newsletter charts

These were added after the main study. Everything in sections 1-3 (strategies, timing, cash, spread, dividends)
applies unchanged except where a subsection says otherwise. They are deliberately quicker and simpler than the main
study: they reuse the same engine, and they have no separate data audit beyond the cross-check described in 10.1.

### 10.1 SPY only, last 25 years (`scripts/spy_25y.py` -> `results/spy_25y.csv`)

- **Asset and period.** SPY, Yahoo Finance dividend-adjusted close (total return, USD). 300 deposits of $500
  ($150,000): the first on the first trading day of Nov 2001, the last on the first trading day of Oct 2026, valued at
  the last trading day of Oct 2026. Nov 2026 is a partial month and is dropped.
- **Cash** earns the **US** 3-month Treasury yield (FRED `DGS3MO`, daily; simple actual/365 interest using the rate
  on or before the previous close), not the Canadian rate used in the main study.
- **Dip sizes 5, 10, 15 and 20%.** (The main study used 5, 10, 20 and 30%, so the two runs are not like-for-like.)
  The all-time high is SPY's running maximum since its first Yahoo row (1993-01-29); it is not reset in 2001. Signal,
  next-day fill, 0.05% spread and the primary "threshold" rule are as in sections 1 and 3.
- **One 25-year path is a single draw**, so the run also scores every 10-year window that fits inside those 25 years
  (181 windows).
- **Checks.** For every result the fast engine is asserted equal to the day-by-day reference simulator (relative
  difference below 1e-9). The whole run is repeated on the S&P 500 total-return index `^SP500TR` itself (rows labelled
  `^SP500TR (cross-check)` in the CSV).
- **Data-quality caveat.** Section 2 explains why Yahoo's SPY history is avoided in the main study. It is used here
  because the run was asked to be SPY-only. Over Nov 2001 - Oct 2026 SPY's and the index's daily returns correlate at
  0.992 and differ by more than one percentage point on 15 days (largest: 2.9 points on 2008-10-13); the two
  drawdown-from-all-time-high paths never differ by more than 1.3 points; annualised total returns are 10.0% (SPY) and
  10.1% (index). The index cross-check reaches the same conclusion, with the dip-buyer's difference from DCA within
  0.4 percentage points of SPY's at every dip size.

| Dip | Ending value | vs monthly DCA | Months holding cash (of 300) | Purchases | 10-year windows where the dip-buyer wins | Median 10-year difference |
|---|---:|---:|---:|---:|---:|---:|
| Monthly DCA | $870,524 | | 0 | 300 | | |
| 5% | $868,214 | -0.3% | 135 | 186 | 29% | -0.8% |
| 10% | $851,700 | -2.2% | 183 | 133 | 8% | -3.7% |
| 15% | $835,980 | -4.0% | 209 | 101 | 18% | -6.1% |
| 20% | $824,830 | -5.2% | 232 | 75 | 20% | -9.5% |

### 10.2 SPY vs XIU: why was Canada different? (`scripts/why_canada.py`)

**Question.** In the SPY-only run the dip-buyer loses at every size, while in the main study XIU's 10% dip-buyer
wins in nearly every window. Does anything simple about the two markets explain that?

**Definitions** (dividend-adjusted closes, each market in its own currency):

- **Shared period:** 1999-10-04 (XIU's first day) to 2026-10-30. The all-time high is the running maximum from the
  start of this shared period for **both** markets. That differs from section 10.1 and the main study, which use each
  series' full history, so the SPY drawdown counts here are not interchangeable with those runs.
- **Share of months** below the high: month-end closes at least 10% (or 20%) below the all-time high.
- **Separate drawdown:** the stretch between one strictly-new all-time high and the next. It counts as a "10%
  drawdown" when its lowest close is at least 10% below the high that started it (same for 20%).
- **Recovery time:** months from the peak (or from the lowest close) to the next new high, averaged over finished
  drawdowns only (none was still open at the end).

**Results** (`results/why_canada.csv`):

| | SPY (US, USD) | XIU (Canada, CAD) |
|---|---:|---:|
| Annualised total return | 8.57% | 8.84% |
| Share of month-ends 10%+ below the high | 37.8% | 38.2% |
| Share of month-ends 20%+ below the high | 20.9% | 21.2% |
| Separate drawdowns of 10%+ | 8 | 12 |
| Separate drawdowns of 20%+ | 4 | 4 |
| Average months, peak to new high (10%+ drawdowns) | 24.1 | 17.7 |
| Average months, peak to new high (20%+ drawdowns) | 41.6 | 39.1 |
| Average months, lowest close to new high (10%+) | 15.3 | 12.2 |
| Worst drawdown | -55.2% | -52.0% |
| Times the close fell below the -10% / -20% line (re-crossings counted) | 61 / 26 | 64 / 36 |

**Window check** (`results/why_canada_windows.csv`, exploratory). For the 181 ten-year windows starting Nov 2001 to
Nov 2016 (the same calendar set for both markets; each market's cash earns its own country's 3-month T-bill) we
compared the 10% dip-buyer's result with how much of the window the market spent 10%+ below its high.

- The 10% dip-buyer's average result versus DCA was **-3.9% for SPY and +1.3% for XIU**, a gap of 5.2 points.
- Time spent 10%+ below the high (30.5% of days for SPY, 34.7% for XIU) accounts for **about 3%** of that gap
  (a regression of the result on time in dip plus a market indicator).
- The same variable points in opposite directions inside each market: more time in dips goes with a *better*
  dip-buyer result in SPY's windows (correlation +0.71) and a *worse* one in XIU's (-0.54).
- The number of separate 10%+ dips in the window (average 20.6 for SPY, 27.6 for XIU) accounts for about **28%** of
  the gap. **This was a second candidate tried after the first failed**, on overlapping windows from two markets
  and one era, so treat it as a lead, not a finding.

**Reading.** The aggregate measures are nearly identical across the two markets: the same share of time below the
high, the same number of 20%+ crashes, similar returns. The one clear difference is in shallow drawdowns: XIU has
eight between 10% and 16.4% (SPY has two), and seven of those healed in under 9 months (2.6 to 8.2; the eighth, in
2022-23, took 21). That also pulls XIU's *average* recovery time down (24 vs 18 months for 10%+ drawdowns; for 20%+
drawdowns it is 42 vs 39). At 18.8% or deeper SPY has six drawdowns and XIU four. **These measures do not explain
why XIU's dip-buyers did better than SPY's. Confidence that the question is answered: low.** Untested conjectures:
the timing of the crashes relative to deposits, XIU's sector mix, the Canadian versus US T-bill rate, and that two
markets over overlapping eras are simply two draws.

### 10.3 The newsletter charts (`scripts/newsletter_charts.py`)

Three charts, 1800 px wide, built from the saved results and the cached data without rerunning the main study. US
colour `#1f4e79`, Canada colour `#c8102e`. The script asserts that the fast engine and the day-by-day simulator that draws chart 1 agree on both ending
values (the published run ends at $870,524 and $824,830).

- `charts/chart_growth_spy.png`: the 25-year SPY path of section 10.1 at the 20% dip size, drawn from the day-by-day
  reference simulator. The script also writes the day-by-day series behind it (daily and
  month-end portfolio values, and the dip-buyer's 75 purchases) to `local_only/`, which is git-ignored.
  **They are deliberately not published**: a portfolio's daily value determines the underlying price series (SPY's
  daily returns can be rebuilt from it to within 1e-6), so publishing them would amount to publishing the Yahoo data.
  `scripts/check_no_raw_data.py` guards against this.
- `charts/chart_why_canada.png`: three rows of `results/why_canada.csv` (10.2).
- `charts/chart_fragility_xiu.png`: the 20-year-window win rate for XIU at each dip size, with idle cash earning the
  T-bill versus 0%. The numbers are the `tbill` and `zero` rows of `results/summary_xiu_cad.csv` (primary rule, 0.05%
  spread, 85 windows), the same ones as the "Cash earns 0%" row of the section 9 table.
