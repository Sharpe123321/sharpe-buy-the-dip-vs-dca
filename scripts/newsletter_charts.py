"""
Three newsletter charts (charts/chart_*.png, 1800 px wide) and the time-series CSVs behind chart 1.
Uses the cached data, the existing engine and the saved results; the main study is NOT rerun.
The day-by-day CSVs behind chart 1 are written to local_only/ (git-ignored), NOT to results/. A portfolio's
daily value determines the underlying price series (SPY's daily returns can be rebuilt from it), so publishing
them would amount to publishing Yahoo's data.

  chart_growth_spy.png       SPY, Nov 2001 - Oct 2026: monthly investor vs 20% dip-buyer vs cash put in
  chart_why_canada.png       SPY vs XIU: time below the high, number of 10%+ drawdowns, months to recover
  chart_fragility_xiu.png    XIU, 20-year windows: dip-buyer win rate with T-bill cash vs 0% cash

Run scripts/why_canada.py first (it writes results/why_canada.csv).  Style: white background, US #1f4e79,
Canada #c8102e, no gridlines, direct labels.  Where one market needs two lines (SPY monthly investor vs SPY dip-buyer)
the second line is a lighter tint of the same colour.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from dipdca.engine import Prepared, Strategy  # noqa: E402
from dipdca.reference import simulate  # noqa: E402
import spy_25y  # noqa: E402

RES, OUT, LOCAL = ROOT / "results", ROOT / "charts", ROOT / "local_only"
US, CA = "#1f4e79", "#c8102e"
US_TINT, US_BAND, CA_TINT = "#7aa3cc", "#d3e2f0", "#e8a7b0"
INK, SUB, GREY, SRC = "#111111", "#555555", "#8c8c8c", "#8a8a8a"
W_IN, DPI = 9.0, 200                                                   # 9 in x 200 dpi = 1800 px wide

plt.rcParams.update({"font.family": ["Segoe UI", "DejaVu Sans"], "axes.facecolor": "white", "figure.facecolor": "white",
                     "savefig.facecolor": "white", "axes.grid": False, "text.color": INK})


def frame(h_in: float, title: str, subtitle: str, source: str) -> plt.Figure:
    fig = plt.figure(figsize=(W_IN, h_in), dpi=DPI, facecolor="white")
    fig.text(0.045, 1 - 0.30 / h_in, title, ha="left", va="top", fontsize=16.5, fontweight="bold", color=INK)
    fig.text(0.045, 1 - 0.72 / h_in, subtitle, ha="left", va="top", fontsize=10.5, color=SUB)
    fig.text(0.045, 0.16 / h_in, chr(10).join(source) if isinstance(source, (list, tuple)) else source,
             ha="left", va="bottom", fontsize=7.3, color=SRC, linespacing=1.5)
    return fig


def axes(fig, h_in, left=0.075, right=0.80, top_in=1.25, bottom_in=0.62):
    return fig.add_axes([left, bottom_in / h_in, right - left, (h_in - top_in - bottom_in) / h_in])


def tidy(ax, keep_left=True):
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#bdbdbd")
    ax.tick_params(axis="both", length=0, labelsize=8.5, labelcolor=SUB)
    ax.grid(False)


# ------------------------------------------------------------------------------------------------ chart 1
def chart_growth_spy() -> dict:
    m = spy_25y.build("SPY", "adj_close")
    prep = Prepared(m, (0.20,), rules=("threshold",))
    N = 300
    s = len(prep.first) - N
    a, b = int(prep.first[s]), int(prep.last[s + N - 1])
    dca = simulate(m, Strategy("dca"), a, b, cash="tbill", cost=spy_25y.COST)
    dip = simulate(m, Strategy("dip", 0.20, "threshold"), a, b, cash="tbill", cost=spy_25y.COST)
    assert round(dca.final_value) == 870524 and round(dip.final_value) == 824830, (dca.final_value, dip.final_value)
    dates = pd.DatetimeIndex(m.dates[a:b + 1])

    # ---- exports: local only, never committed (see the module docstring)
    LOCAL.mkdir(exist_ok=True)
    runmax = np.maximum.accumulate(m.px)
    # SPY's own price is deliberately NOT exported (third-party data); the drawdown and portfolio series are ours.
    daily = pd.DataFrame({
        "date": dates, "spy_drawdown_from_all_time_high_pct": (m.px[a:b + 1] / runmax[a:b + 1] - 1) * 100,
        "total_contributed": dca.contributed, "monthly_investor_value": dca.value,
        "dip20_total_value": dip.value, "dip20_uninvested_cash": dip.cash, "dip20_invested_value": dip.value - dip.cash})
    daily.to_csv(LOCAL / "chart_growth_spy_timeseries.csv", index=False, float_format="%.4f")
    daily.groupby(daily["date"].dt.to_period("M")).tail(1).to_csv(LOCAL / "chart_growth_spy_timeseries_monthly.csv", index=False, float_format="%.4f")
    pd.DataFrame([{"date": pd.Timestamp(m.dates[i]).date(), "cash_invested_incl_interest": c, "shares_bought": sh}
                  for i, sh, c in dip.buys]).to_csv(LOCAL / "chart_growth_spy_dip20_purchases.csv", index=False, float_format="%.4f")

    # ---- chart
    h = 5.7
    gap = dca.final_value - dip.final_value
    fig = frame(h, f"Waiting for a 20% dip cost an SPY investor ${gap:,.0f} over 25 years",
                "$500 a month into SPY, Nov 2001 to Oct 2026; money not yet invested earns the US 3-month T-bill rate",
                ["Source: Yahoo Finance (SPY, dividend-adjusted), FRED (3-month Treasury yield), Sharpe analysis. 0.05% spread on every purchase.",
                 "The dip-buyer saves each $500 and invests all cash the day after SPY closes 20% or more below its all-time high."])
    ax = axes(fig, h, right=0.80, bottom_in=0.85)
    ax.fill_between(dates, dip.value - dip.cash, dip.value, color=US_BAND, lw=0, zorder=1)
    ax.plot(dates, dca.contributed, color=GREY, lw=1.2, zorder=3)
    ax.plot(dates, dip.value, color=US_TINT, lw=1.35, zorder=4)
    ax.plot(dates, dca.value, color=US, lw=1.35, zorder=5)
    top = float(dca.value.max()) * 1.10
    ax.set_ylim(0, top)
    ax.set_xlim(dates[0], dates[-1])
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: "$0" if v == 0 else f"${v / 1000:,.0f}k"))
    ax.set_yticks([0, 200_000, 400_000, 600_000, 800_000])
    ax.xaxis.set_major_locator(mdates.YearLocator(4, month=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    tidy(ax)
    xe = dates[-1] + pd.Timedelta(days=170)
    kw = dict(annotation_clip=False, fontsize=9.6, fontweight="bold", va="center")
    ax.annotate(f"Monthly investor\n${dca.final_value:,.0f}", xy=(dates[-1], dca.value[-1]), xytext=(xe, dca.value[-1] + top * 0.065),
                color=US, arrowprops=dict(arrowstyle="-", color=US, lw=0.8), **kw)
    ax.annotate(f"20% dip-buyer\n${dip.final_value:,.0f}", xy=(dates[-1], dip.value[-1]), xytext=(xe, dip.value[-1] - top * 0.085),
                color=US_TINT, arrowprops=dict(arrowstyle="-", color=US_TINT, lw=0.8), **kw)
    ax.annotate(f"Money put in\n${dca.contributed[-1]:,.0f}", xy=(dates[-1], dca.contributed[-1]), xytext=(xe, dca.contributed[-1]),
                color=GREY, arrowprops=dict(arrowstyle="-", color=GREY, lw=0.8), **{**kw, "fontweight": "normal"})
    k = int(np.argmax(dip.cash))
    ax.annotate(f"Shaded: the dip-buyer's uninvested cash\n(peaked at ${dip.cash[k]:,.0f} on {dates[k]:%b %Y}, {int(round(dip.months_in_cash))} of 300 months holding some)",
                xy=(dates[k], dip.value[k] - dip.cash[k] / 2), xytext=(pd.Timestamp("2005-06-01"), top * 0.62), color=SUB, fontsize=8.6,
                va="center", arrowprops=dict(arrowstyle="-", color="#9db7d1", lw=0.9))
    p = OUT / "chart_growth_spy.png"
    fig.savefig(p, dpi=DPI)
    plt.close(fig)
    return {"dca": dca.final_value, "dip": dip.final_value, "gap": gap, "peak_cash": float(dip.cash[k]), "peak_cash_date": str(dates[k].date()),
            "purchases": len(dip.buys), "months_in_cash": dip.months_in_cash}


# ------------------------------------------------------------------------------------------------ chart 2
def chart_why_canada() -> dict:
    w = pd.read_csv(RES / "why_canada.csv").set_index("market")
    us, ca = w.loc["SPY (US)"], w.loc["XIU (Canada)"]
    panels = [("Share of months spent 10%+\nbelow the all-time high", "pct_months_10pct_below_high", "{:.0f}%", 0, 50),
              ("Separate drawdowns of\n10% or more", "n_drawdowns_10pct", "{:.0f}", 0, 14),
              ("Average months from the peak\nto a new high (10%+ drawdowns)", "avg_months_peak_to_new_high_10pct", "{:.0f}", 0, 30)]
    h = 5.5
    d0, d1 = pd.Timestamp(us["start"]), pd.Timestamp(us["end"])
    fig = frame(h, "Same time below the high, but Canada had more separate dips",
                f"SPY (US, USD) and XIU (Canada, CAD), {d0:%b %Y} to {d1:%b %Y}, dividend-adjusted closes",
                ["Source: Yahoo Finance (SPY, XIU.TO), Sharpe analysis (results/why_canada.csv). A drawdown runs from an all-time high to the next one;",
                 "recovery is averaged over completed drawdowns only."])
    gap_x = 0.045
    width = (0.955 - gap_x - 2 * 0.055) / 3
    for i, (ttl, col, fmt, lo, hi) in enumerate(panels):
        left = gap_x + i * (width + 0.055)
        ax = fig.add_axes([left, 1.0 / h, width, (h - 1.25 - 1.0 - 0.35) / h])
        vals = [float(us[col]), float(ca[col])]
        ax.bar([0, 1], vals, width=0.62, color=[US, CA], zorder=3)
        for x, v in zip((0, 1), vals):
            ax.text(x, v + hi * 0.025, fmt.format(v), ha="center", va="bottom", fontsize=13, fontweight="bold", color=US if x == 0 else CA)
        ax.set_ylim(lo, hi)
        ax.set_xlim(-0.55, 1.55)
        ax.set_yticks([])
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["SPY\n(US)", "XIU\n(Canada)"], fontsize=9.5)
        for t, c in zip(ax.get_xticklabels(), (US, CA)):
            t.set_color(c)
            t.set_fontweight("bold")
        tidy(ax)
        ax.tick_params(axis="x", labelsize=9.5)
        ax.set_title(ttl, loc="left", fontsize=10, color=INK, pad=24, fontweight="bold", linespacing=1.25)
        if col == "avg_months_peak_to_new_high_10pct":      # XIU's shorter average comes from having many shallow dips
            ax.text(0.0, 1.02, f"For 20%+ drawdowns it is {us['avg_months_peak_to_new_high_20pct']:.0f} vs "
                               f"{ca['avg_months_peak_to_new_high_20pct']:.0f} months", transform=ax.transAxes, fontsize=8.2, color=SUB, va="bottom")
    p = OUT / "chart_why_canada.png"
    fig.savefig(p, dpi=DPI)
    plt.close(fig)
    return {"us": us.to_dict(), "ca": ca.to_dict()}


# ------------------------------------------------------------------------------------------------ chart 3
def chart_fragility_xiu() -> pd.DataFrame:
    s = pd.read_csv(RES / "summary_xiu_cad.csv")
    s = s[(s.horizon_years == 20) & (s.rule == "threshold") & (s.cost_mode == "spread_0.05pct")
          & (s.strategy.isin(["dip_5pct", "dip_10pct", "dip_20pct", "dip_30pct"]))]
    t = s[s.cash_mode == "tbill"].set_index("strategy")["pct_beats_monthly"]
    z = s[s.cash_mode == "zero"].set_index("strategy")["pct_beats_monthly"]
    order = ["dip_5pct", "dip_10pct", "dip_20pct", "dip_30pct"]
    labels = ["5% dip", "10% dip", "20% dip", "30% dip"]
    n = int(s.n_windows.iloc[0])
    h = 5.2
    fig = frame(h, "Without cash interest, Canada's 20% and 30% dip edge fades",
                f"XIU: share of 20-year windows ({n}) in which buying the dip beat investing every month, by dip size",
                ["Source: Yahoo Finance (XIU.TO), Bank of Canada (T-bill yield), Sharpe analysis (results/summary_xiu_cad.csv). 0.05% spread on every purchase.",
                 f"The {n} windows overlap and hold only about 1.4 independent 20-year periods."])
    ax = axes(fig, h, right=0.80, bottom_in=0.80)
    x = np.arange(4)
    wbar = 0.34
    ax.bar(x - wbar / 2 - 0.01, [t[k] for k in order], width=wbar, color=CA, zorder=3)
    ax.bar(x + wbar / 2 + 0.01, [z[k] for k in order], width=wbar, color=CA_TINT, zorder=3)
    for i, k in enumerate(order):
        ax.text(i - wbar / 2 - 0.01, t[k] + 2, f"{t[k]:.0f}%", ha="center", va="bottom", fontsize=10.5, fontweight="bold", color=CA)
        ax.text(i + wbar / 2 + 0.01, z[k] + 2, f"{z[k]:.0f}%", ha="center", va="bottom", fontsize=10.5, fontweight="bold", color="#b4727b")
    ax.axhline(50, color="#c9c9c9", lw=0.9, ls=(0, (4, 3)), zorder=1)
    ax.text(3.62, 51.5, "50%", ha="right", va="bottom", fontsize=8, color=GREY)
    ax.set_ylim(0, 112)
    ax.set_xlim(-0.6, 3.62)
    ax.set_yticks([])
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10)
    tidy(ax)
    ax.tick_params(axis="x", labelsize=10, labelcolor=INK)
    kw = dict(annotation_clip=False, fontsize=9.6, fontweight="bold", va="center")
    ax.annotate("Idle cash earns\nthe T-bill rate", xy=(3 - wbar / 2 - 0.01 + wbar / 2, t["dip_30pct"] * 0.55), xytext=(3.78, 62), color=CA,
                arrowprops=dict(arrowstyle="-", color=CA, lw=0.8), **kw)
    ax.annotate("Idle cash earns 0%", xy=(3.43, 4), xytext=(3.78, 18), color="#b4727b",
                arrowprops=dict(arrowstyle="-", color="#b4727b", lw=0.8), **kw)
    p = OUT / "chart_fragility_xiu.png"
    fig.savefig(p, dpi=DPI)
    plt.close(fig)
    return pd.DataFrame({"dip": labels, "tbill_cash_pct_windows_won": [t[k] for k in order], "zero_cash_pct_windows_won": [z[k] for k in order]})


def main() -> None:
    OUT.mkdir(exist_ok=True)
    info = chart_growth_spy()
    print("chart 1:", {k: (round(v, 2) if isinstance(v, float) else v) for k, v in info.items()})
    chart_why_canada()
    print("chart 2 written")
    print(chart_fragility_xiu().round(1).to_string(index=False))
    from PIL import Image
    for n in ("chart_growth_spy", "chart_why_canada", "chart_fragility_xiu"):
        print(n, Image.open(OUT / f"{n}.png").size)


if __name__ == "__main__":
    main()
