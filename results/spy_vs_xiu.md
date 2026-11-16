# Buy the dip vs monthly DCA: SPY and XIU side by side

Both rows of numbers come from files already in this folder; nothing was rerun to make this page.
SPY: `results/spy_25y.csv`. XIU: `results/headline_table.csv` (full detail in `results/summary_xiu_cad.csv`).

$500 a month. Idle cash earns a T-bill. 0.05% spread on every purchase. Buy-the-dip invests all its cash on the
trading day after the close is X% below the all-time high. "Diff" is the dip-buyer's ending value vs monthly DCA.

| Dip | SPY, last 25 years (one window, USD) | SPY, every 10-year window inside those 25 years (181 windows) | XIU, every 10-year window (205 windows, CAD) | XIU, every 20-year window (85 windows, CAD) |
|---:|---|---|---|---|
| 5% | **-0.3%** | beats DCA in 29%, median -0.8% | beats DCA in 15%, median -0.2% | beats DCA in 0%, median -0.3% |
| 10% | **-2.2%** | beats DCA in 8%, median -3.7% | beats DCA in **98%**, median **+1.1%** | beats DCA in **100%**, median **+1.2%** |
| 15% | **-4.0%** | beats DCA in 18%, median -6.1% | not run | not run |
| 20% | **-5.2%** | beats DCA in 20%, median -9.5% | beats DCA in 67%, median +1.4% | beats DCA in 84%, median +1.6% |
| 30% | not run | not run | beats DCA in 44%, median -1.4% | beats DCA in 59%, median +0.4% |

Months the dip-buyer held some uninvested cash:

| Dip | SPY, 25 years (of 300) | XIU, 10-year windows (average, of 120) | XIU, 20-year windows (average, of 240) |
|---:|---:|---:|---:|
| 5% | 135 | 48 | 98 |
| 10% | 183 | 68 | 139 |
| 15% | 209 | not run | not run |
| 20% | 232 | 97 | 193 |
| 30% | not run | 109 | 217 |

SPY 25-year dollars: $150,000 put in; monthly DCA ends at $870,524; the dip-buyer ends at $868,214 (5%), $851,700 (10%),
$835,980 (15%) and $824,830 (20%).

## The two runs are not like-for-like

| | SPY run | XIU run |
|---|---|---|
| Currency | USD | CAD |
| Cash rate | US 3-month Treasury bill (FRED DGS3MO) | Canadian 3-month T-bill (Bank of Canada; IMF series before 2001) |
| Period | Nov 2001 to Oct 2026 | Oct 1999 to Oct 2026 (first 10-year start Nov 1999) |
| What a "result" is | one 25-year window, plus 10-year windows inside it | every possible start month, at 10 and 20 years |
| Dip sizes | 5, 10, 15, 20% | 5, 10, 20, 30% (there is no 15% XIU result, and no 30% SPY result) |
| Total return series | SPY dividend-adjusted close | XIU dividend-adjusted close |

## What this does and does not show

- **The two point in opposite directions.** SPY's dip-buyers trail DCA at every size, while XIU's 10% and 20%
  dip-buyers finish slightly ahead in most windows. The S&P 500 converted to CAD in the main study behaves like SPY
  (10-year win rates of 12% / 12% / 22% / 28% at 5 / 10 / 20 / 30%), so the split looks like XIU versus the S&P 500,
  not USD versus CAD.
- **It is not just a different era.** SPY's 10-year windows start Nov 2001 to Nov 2016 and XIU's start Nov 1999 to Nov
  2016, so most of the calendar time is shared. Why XIU's dip-buyers did better was not tested.
- **The XIU edge is small and fragile.** The median gain at 10% is about +1%. In the main study it disappeared or
  reversed if idle cash earned 0% instead of the T-bill rate (20% dip: 84% of 20-year windows down to 21%), and it
  moved a lot with how dividends were counted and whether dips were read from price or total return
  (`METHODOLOGY.md` section 9).
- **Few independent periods.** The windows overlap almost completely. XIU holds about 2.7 independent 10-year and 1.4
  independent 20-year periods; SPY's 25 years hold about 2.5 independent decades. Read the percentages as "how many
  eras", not as probabilities.
- **No taxes, withholding tax or account types are modelled.** This is research, not investment advice.
