# results/

Every number in the top-level [README](../README.md) and [METHODOLOGY](../METHODOLOGY.md) comes from a file here. All
of it is **derived output** computed by the scripts in [`../scripts/`](../scripts/); no third-party price data, index
levels or interest rates are stored, and neither are day-by-day portfolio values (from which prices could be
recovered).

**Common definitions.** "Diff" or `diff_pct` is the strategy's ending value divided by monthly DCA's ending value, minus
one, in percent (positive means the dip-buyer or perfect timer finished ahead). `pct_beats_monthly` is the share of
windows in which that difference is strictly positive. A *window* is one start month, held for 10, 20 or 30 years.
`months_in_cash` is the number of months in which the portfolio held any uninvested cash. Dollar amounts are nominal, in
the asset's currency (CAD for the main study, USD for the SPY-only run). `strategy` is `dip_5pct` etc. (buy when the
close is that far below the all-time high), `perfect_timing` (hindsight hypothetical) or `monthly_dca`.

## Main study (Canada and the S&P 500 in CAD)

| File | What it is | Produced by |
|---|---|---|
| [`headline_table.csv`](headline_table.csv) | One row per asset, horizon and strategy at the **primary settings** (T-bill cash, 0.05% spread, threshold rule). The numbers in README chart 1 and the main table. | `run_study.py` |
| [`summary_xiu_cad.csv`](summary_xiu_cad.csv), [`summary_sp500_cad.csv`](summary_sp500_cad.csv) | The same columns for **every** variant: `cash_mode` (`tbill` or `zero`), `cost_mode` (with or without the 0.05% spread) and `rule` (`threshold` or the "stay-invested" variant). | `run_study.py` |
| [`by_start_year.csv`](by_start_year.csv) | Win rate and median difference grouped by the year the window starts, showing how era-dependent the result is. | `run_study.py` |
| [`sensitivity.csv`](sensitivity.csv) | The same summary under each sensitivity (dips read from price only, own dividend reinvestment, deposit joins the fill, dips read from the USD index). Feeds METHODOLOGY section 9. | `run_study.py` |
| [`tables.md`](tables.md) | The summary tables in Markdown, as used in the docs. | `make_tables.py` |

Columns shared by `headline_table`, `summary_*` and `sensitivity`: `n_windows`; `approx_independent_windows` (months of
data divided by months in the window, so how many non-overlapping periods the data really holds); `first_start`,
`last_start`; `pct_beats_monthly`; `median_diff_pct`, `worst_diff_pct`, `best_diff_pct`, `mean_diff_pct`;
`avg_months_in_cash`, `median_months_in_cash`; `pct_windows_ending_with_cash` (share of windows where the strategy still
held uninvested cash at the end); `window_months`; `median_dca_final` (median ending value of monthly DCA).

## Data audit and sanity check

| File | What it is | Produced by |
|---|---|---|
| [`data_audit.md`](data_audit.md), [`data_audit_checks.csv`](data_audit_checks.csv) | The 39 data-quality checks (`series`, `check`, `status` = PASS / WARN / FAIL / INFO, `detail`). | `audit_data.py` |
| [`sanity_check_maggiulli.csv`](sanity_check_maggiulli.csv) | The attempt to reproduce Maggiulli's perfect-timing result on US data, one row per `variant` (daily or monthly data, nominal or real, month-end or monthly-average prices, bottom definition). Not reproduced; see METHODOLOGY section 6. | `sanity_check.py` |
| [`sanity_check_by_start_year.csv`](sanity_check_by_start_year.csv) | Share of 40-year windows in which perfect timing beats DCA, by start year (`start_year`, `windows`, `pct_perfect_timing_beats_dca`, `median_diff_pct`). | `sanity_check.py` |

## SPY-only run and the Canada comparison

| File | What it is | Produced by |
|---|---|---|
| [`spy_25y.csv`](spy_25y.csv) | SPY, Nov 2001 to Oct 2026, $500 a month. One row per strategy: `final_value`, `diff_vs_dca_pct`, `final_cash`, `months_in_cash`, `n_purchases`, and the rolling 10-year results (`rolling10y_pct_beating_dca`, `rolling10y_median_diff_pct`). Rows labelled `^SP500TR (cross-check)` repeat the run on the index itself. | `spy_25y.py` |
| [`spy_vs_xiu.md`](spy_vs_xiu.md) | The SPY-only and XIU results side by side, with the ways the two runs differ. | written from the two files above |
| [`why_canada.csv`](why_canada.csv) | One row per market (SPY, XIU) over their shared period: annualised return, share of time 10%+ / 20%+ below the all-time high, number of separate 10%+ / 20%+ drawdowns, months to recover. Feeds chart 5. | `why_canada.py` |
| [`why_canada_windows.csv`](why_canada_windows.csv) | One row per 10-year window (181 per market): `pct_days_10pct_below_high_in_window`, `n_separate_10pct_dips_in_window`, `dip10_vs_dca_pct`. The exploratory window check in METHODOLOGY section 10.2. | `why_canada.py` |

## What is deliberately not here

Files from which a provider's price series can be rebuilt are **not published**, because Yahoo's data is for personal use only.
They are written to the git-ignored `local_only/` folder when you run the scripts:

- the day-by-day series behind chart 4 (daily and month-end portfolio values of the monthly investor and the 20% dip-buyer, and the
  dip-buyer's 75 purchases): SPY's daily returns can be rebuilt from them to within 1e-6 (`newsletter_charts.py`);
- `windows_primary.csv`, one row per window with `final_value`, `monthly_dca_final`, `diff_pct`, `months_in_cash`, `final_cash`:
  consecutive windows' ending values reproduce month-end returns (XIU: correlation 0.998) (`run_study.py`).

The numbers from these that are published are the aggregates: `headline_table.csv`, `summary_*.csv`, `by_start_year.csv`,
`sensitivity.csv` and `spy_25y.csv`. `scripts/check_no_raw_data.py` blocks these file names from being committed.
