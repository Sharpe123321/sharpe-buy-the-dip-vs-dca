"""Markdown tables for README / METHODOLOGY, generated from the CSVs so the prose can never drift from the data."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
NAMES = {"dip_5pct": "5% dip", "dip_10pct": "10% dip", "dip_20pct": "20% dip", "dip_30pct": "30% dip",
         "perfect_timing": "Perfect timing (hypothetical)"}


def md(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---:" if i else ":---" for i in range(len(cols))) + "|"]
    out += ["| " + " | ".join(str(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join(out)


def headline(s: pd.DataFrame, asset: str, cash: str, cost: str, rule: str) -> pd.DataFrame:
    d = s[(s.asset == asset) & (s.cash_mode == cash) & (s.cost_mode == cost) & (s.rule.isin([rule, "hindsight"]))]
    rows = []
    for h in sorted(d.horizon_years.unique()):
        for key, label in NAMES.items():
            r = d[(d.horizon_years == h) & (d.strategy == key)]
            if r.empty:
                continue
            r = r.iloc[0]
            rows.append({"Horizon": f"{h} years", "Strategy": label, "Windows": int(r.n_windows),
                         "Beats monthly": f"{r.pct_beats_monthly:.0f}%", "Median diff": f"{r.median_diff_pct:+.1f}%",
                         "Worst": f"{r.worst_diff_pct:+.1f}%", "Best": f"{r.best_diff_pct:+.1f}%",
                         "Months in cash (avg)": f"{r.avg_months_in_cash:.0f} of {int(r.window_months)}"})
    return pd.DataFrame(rows)


def main() -> None:
    parts = []
    for fname, asset, title in (("summary_xiu_cad.csv", "XIU (TSX 60 ETF), CAD", "XIU (TSX 60 ETF), CAD"),
                                ("summary_sp500_cad.csv", "S&P 500, CAD", "S&P 500 converted to CAD")):
        s = pd.read_csv(RES / fname)
        parts.append(f"### {title}: primary settings (T-bill cash, 0.05% spread, buy when the close is X% below the high)\n")
        parts.append(md(headline(s, asset, "tbill", "spread_0.05pct", "threshold")))
        parts.append("")
        # sensitivity of the win rate to the cash assumption, the rule and the spread
        rows = []
        for h in sorted(s.horizon_years.unique()):
            for key in ("dip_5pct", "dip_10pct", "dip_20pct", "dip_30pct", "perfect_timing"):
                def pick(cash, cost, rule):
                    r = s[(s.horizon_years == h) & (s.strategy == key) & (s.cash_mode == cash) & (s.cost_mode == cost)
                          & (s.rule.isin([rule, "hindsight"]))]
                    return r.iloc[0]
                a, b = pick("tbill", "spread_0.05pct", "threshold"), pick("zero", "spread_0.05pct", "threshold")
                c, d = pick("tbill", "no_cost", "threshold"), pick("tbill", "spread_0.05pct", "until_ath")
                rows.append({"Horizon": f"{h}y", "Strategy": NAMES[key], "Primary": f"{a.pct_beats_monthly:.0f}%",
                             "Cash earns 0%": f"{b.pct_beats_monthly:.0f}%", "No spread": f"{c.pct_beats_monthly:.0f}%",
                             "Stay-invested rule": "n/a" if key == "perfect_timing" else f"{d.pct_beats_monthly:.0f}%",
                             "Median diff primary": f"{a.median_diff_pct:+.1f}%", "Median diff, 0% cash": f"{b.median_diff_pct:+.1f}%"})
        parts.append(f"#### {title}: how the win rate moves with the assumptions\n")
        parts.append(md(pd.DataFrame(rows)))
        parts.append("")
    (RES / "tables.md").write_text("\n".join(parts) + "\n", encoding="utf-8")
    print("wrote results/tables.md")


if __name__ == "__main__":
    main()
