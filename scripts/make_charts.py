"""
Three charts (charts/*.png) from the results CSVs and the engine.

  1_headline_pct_beating_monthly.png   % of rolling windows where buy-the-dip beats monthly DCA, by dip threshold
  2_example_20y_window.png             one 20-year XIU window (the MEDIAN one for the 20% rule - not cherry-picked)
  3_months_in_cash.png                 average months the dip-buyer sits in cash, by threshold

Colour: the validated categorical order blue / orange / aqua = 10 / 20 / 30-year horizons (and blue / orange =
monthly DCA / buy-the-dip in the example chart).  Aqua is under 3:1 on the light surface, so every bar carries
its value as visible text.  Hatched bars always mean "hypothetical: needs hindsight".
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
from matplotlib.patches import Patch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dipdca import assets  # noqa: E402
from dipdca.engine import Prepared, Strategy, running_max_and_drawdown, value_window, window_starts  # noqa: E402
from dipdca.reference import simulate  # noqa: E402

RES, OUT = ROOT / "results", ROOT / "charts"

SURFACE, INK, INK2, MUTED, GRID, BASE = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
HCOL = {10: BLUE, 20: ORANGE, 30: AQUA}
ZONE = "#fbe6dc"                                                      # pale orange: 'dip rule is on'

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 10.5, "axes.facecolor": SURFACE, "figure.facecolor": SURFACE,
    "savefig.facecolor": SURFACE, "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.edgecolor": BASE, "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "axes.grid": True, "axes.axisbelow": True, "grid.color": GRID, "grid.linewidth": 0.8, "hatch.linewidth": 1.4,
})
THR = [("dip_5pct", "5%"), ("dip_10pct", "10%"), ("dip_20pct", "20%"), ("dip_30pct", "30%"), ("perfect_timing", "Perfect\ntiming*")]
PANELS = [("XIU (TSX 60 ETF), CAD", "XIU (TSX 60 ETF)  ·  Oct 1999 – {end}"),
          ("S&P 500, CAD", "S&P 500 converted to CAD  ·  1988 – {end}")]
FOOT = ("Cash earns the Canadian 3-month T-bill rate; 0.05% spread per purchase; dividends reinvested; fills at the next trading day's close.\n"
        "*Perfect timing buys at the exact bottom between all-time highs. It needs hindsight - a hypothetical, not a strategy.\n"
        "Sources: Yahoo Finance (XIU.TO, ^SP500TR), Bank of Canada (T-bill yield), FRED (CAD per USD). Code and method: METHODOLOGY.md")


def _end_year(d: pd.DataFrame) -> int:
    """Calendar year in which the data ends: the latest window start plus its length."""
    return int(max(int(str(r.last_start)[:4]) + int(r.horizon_years) for r in d.itertuples()))


def _cash_note(head: pd.DataFrame) -> str:
    v = float(head[head.asset.str.startswith("XIU") & (head.horizon_years == 10) & (head.strategy == "dip_30pct")]["avg_months_in_cash"].iloc[0])
    return (f"A 10-year window is 120 months, so {v:.0f} on XIU's 30% bar (10 years) means cash was on hand about "
            f"{v / 12:.0f} months in 10.")


def _grouped(ax, df, value, horizons, fmt, ylim, ref=None):
    """Grouped bars: x = threshold groups, one bar per horizon.  Hatched = hypothetical."""
    n = len(horizons)
    w = 0.78 / 3                                                       # slot width is fixed so bars match across panels
    for g, (key, _) in enumerate(THR):
        for k, h in enumerate(horizons):
            row = df[(df.horizon_years == h) & (df.strategy == key)]
            if row.empty:
                continue
            v = float(row[value].iloc[0])
            x = g + (k - (n - 1) / 2) * w + (1.0 if key == "perfect_timing" else 0.0) * 0.18
            hyp = key == "perfect_timing"
            ax.bar(x, v, width=w * 0.9, color=HCOL[h], edgecolor=SURFACE if hyp else "none", hatch="////" if hyp else None,
                   linewidth=0, zorder=3)
            ax.text(x, v + ylim * 0.012, fmt(v), ha="center", va="bottom", fontsize=9.2, color=INK2, zorder=4)
    ax.set_xticks([g + (0.18 if key == "perfect_timing" else 0) for g, (key, _) in enumerate(THR)])
    ax.set_xticklabels([lab for _, lab in THR])
    ax.axvline(3.55, color=BASE, lw=1.0, ls=(0, (2, 3)), zorder=2)
    ax.set_ylim(0, ylim)
    ax.set_xlim(-0.6, 4.7)
    ax.tick_params(axis="both", length=0)
    ax.grid(axis="x", visible=False)
    if ref is not None:
        ax.axhline(ref, color=MUTED, lw=1.1, ls=(0, (4, 3)), zorder=2)


def _legend(fig, horizons_by_len, win_months=False):
    items = []
    for h in (10, 20, 30):
        lab = f"{h}-year windows" + (f" ({12 * h} months)" if win_months else "")
        items.append(Patch(facecolor=HCOL[h], label=lab))
    items.append(Patch(facecolor="#bdbcb5", edgecolor=SURFACE, hatch="////", label="hypothetical (needs hindsight)"))
    fig.legend(handles=items, loc="upper center", bbox_to_anchor=(0.5, 0.885), ncol=4, frameon=False, fontsize=10.2,
               handlelength=1.4, columnspacing=1.8, labelcolor=INK2)


def _header(fig, title, sub):
    fig.text(0.045, 0.965, title, fontsize=16.5, fontweight="bold", va="top", color=INK)
    fig.text(0.045, 0.918, sub, fontsize=11, va="top", color=INK2)


def _indep_note(df):
    parts = []
    for name, _ in PANELS:
        d = df[(df.asset == name) & (df.strategy == "dip_10pct")].sort_values("horizon_years")
        short = "XIU" if name.startswith("XIU") else "S&P 500"
        parts.append(f"{short}: " + " / ".join(f"{r.approx_independent_windows:.1f}" for r in d.itertuples())
                     + " (" + "/".join(str(int(h)) for h in d.horizon_years) + "y)")
    return ("Windows overlap almost completely. Independent, non-overlapping periods in the data: " + ";  ".join(parts)
            + ". Read bars as 'how many eras', not as probabilities.")


def chart1(head: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(12.6, 7.1), sharey=True, gridspec_kw={"wspace": 0.05, "left": 0.045, "right": 0.985,
                                                                                    "top": 0.80, "bottom": 0.215})
    for ax, (name, ttl) in zip(axes, PANELS):
        d = head[head.asset == name]
        _grouped(ax, d, "pct_beats_monthly", sorted(d.horizon_years.unique()), lambda v: f"{v:.0f}%", 108, ref=50)
        ax.set_title(ttl.format(end=_end_year(d)), loc="left", fontsize=11.5, color=INK, pad=10, fontweight="semibold")
        ax.set_yticks([0, 25, 50, 75, 100])
        ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
        ax.set_xlabel("Buy when the index is this far below its all-time high", fontsize=10, labelpad=8)
    axes[0].text(4.68, 51.5, "50% = coin flip", ha="right", va="bottom", fontsize=9, color=MUTED)
    _header(fig, "Does buying the dip beat investing $500 every month? It depends on the market.",
            "Share of rolling windows in which the dip-buyer ends with MORE money than monthly DCA")
    _legend(fig, None)
    fig.text(0.045, 0.012, FOOT + "\n" + _indep_note(head), fontsize=8.1, color=MUTED, va="bottom", linespacing=1.45)
    p = OUT / "1_headline_pct_beating_monthly.png"
    fig.savefig(p, dpi=160)
    plt.close(fig)
    return p


def chart3(head: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(12.6, 7.1), sharey=True, gridspec_kw={"wspace": 0.05, "left": 0.045, "right": 0.985,
                                                                                    "top": 0.80, "bottom": 0.215})
    for ax, (name, ttl) in zip(axes, PANELS):
        d = head[head.asset == name]
        _grouped(ax, d, "avg_months_in_cash", sorted(d.horizon_years.unique()), lambda v: f"{v:.0f}", 305)
        ax.set_title(ttl.format(end=_end_year(d)), loc="left", fontsize=11.5, color=INK, pad=10, fontweight="semibold")
        ax.set_yticks([0, 60, 120, 180, 240, 300])
        ax.set_xlabel("Buy when the index is this far below its all-time high", fontsize=10, labelpad=8)
    axes[0].set_ylabel("Average months holding any uninvested cash", fontsize=10)
    _header(fig, "How long the dip-buyer sits in cash waiting",
            "Average number of months, per window, in which some cash was not yet invested (monthly DCA: always 0)")
    _legend(fig, None, win_months=True)
    fig.text(0.045, 0.012, FOOT + "\n" + _cash_note(head),
             fontsize=8.1, color=MUTED, va="bottom", linespacing=1.45)
    p = OUT / "3_months_in_cash.png"
    fig.savefig(p, dpi=160)
    plt.close(fig)
    return p


def chart2() -> tuple[Path, dict]:
    m = assets.xiu_cad()
    prep = Prepared(m, (0.20,))
    H, N, thr = 20, 240, 0.20
    st = Strategy("dip", thr, "threshold")
    starts = window_starts(len(prep.first), N)
    diff = np.array([value_window(prep, st, int(s), N, cash="tbill", cost=0.0005).final_value
                     / value_window(prep, Strategy("dca"), int(s), N, cash="tbill", cost=0.0005).final_value - 1 for s in starts])
    pick = int(starts[int(np.argmin(np.abs(diff - np.median(diff))))])           # the MEDIAN window, not a flattering one
    a, b = int(prep.first[pick]), int(prep.last[pick + N - 1])
    dca = simulate(m, Strategy("dca"), a, b, cash="tbill", cost=0.0005)
    dip = simulate(m, st, a, b, cash="tbill", cost=0.0005)
    dates = pd.DatetimeIndex(m.dates[a:b + 1])
    dd = running_max_and_drawdown(m.sig)[1][a:b + 1] * 100
    on = dd <= -thr * 100

    fig, axes = plt.subplots(4, 1, figsize=(11.8, 11.2), sharex=True,
                             gridspec_kw={"height_ratios": [3.0, 1.35, 1.25, 1.25], "hspace": 0.13,
                                          "left": 0.085, "right": 0.865, "top": 0.855, "bottom": 0.095})
    ax0, axr, ax1, ax2 = axes

    def shade(ax):
        i = 0
        while i < len(on):
            if on[i]:
                j = i
                while j + 1 < len(on) and on[j + 1]:
                    j += 1
                ax.axvspan(dates[i], dates[j], color=ZONE, lw=0, zorder=1)
                i = j + 1
            else:
                i += 1

    for ax in axes:
        shade(ax)
        ax.tick_params(length=0)
    money = lambda v, _: f"${v / 1000:,.0f}k"                                     # noqa: E731
    ax0.plot(dates, dca.contributed, color=MUTED, lw=1.4, ls=(0, (4, 3)), zorder=3)
    ax0.plot(dates, dca.value, color=BLUE, lw=2.0, zorder=4)
    ax0.plot(dates, dip.value, color=ORANGE, lw=2.0, zorder=5)
    ax0.yaxis.set_major_formatter(plt.FuncFormatter(money))
    ax0.set_ylabel("Portfolio value (CAD)")
    top = max(dca.value.max(), dip.value.max())
    ax0.set_ylim(0, top * 1.06)
    xe = dates[-1] + pd.Timedelta(days=150)
    ar = dict(arrowstyle="-", lw=0.9, shrinkA=0, shrinkB=2)
    ax0.annotate(f"Buy the dip\nends at ${dip.value[-1]:,.0f}", xy=(dates[-1], dip.value[-1]), xytext=(xe, dip.value[-1] + top * 0.10),
                 color=INK, fontsize=9.6, va="center", fontweight="semibold", annotation_clip=False,
                 arrowprops={**ar, "color": ORANGE})
    ax0.annotate(f"Monthly DCA\nends at ${dca.value[-1]:,.0f}", xy=(dates[-1], dca.value[-1]), xytext=(xe, dca.value[-1] - top * 0.10),
                 color=INK, fontsize=9.6, va="center", fontweight="semibold", annotation_clip=False,
                 arrowprops={**ar, "color": BLUE})
    ax0.text(xe, dca.contributed[-1], f"Cash put in\n${dca.contributed[-1]:,.0f}", color=MUTED, fontsize=9.2, va="center")
    rel = (dip.value / np.where(dca.value > 0, dca.value, np.nan) - 1) * 100
    axr.axhline(0, color=BASE, lw=1.2, zorder=2)
    axr.plot(dates, rel, color=ORANGE, lw=1.8, zorder=4)
    axr.set_ylabel("Dip-buyer's value\nvs DCA")
    axr.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: "0%" if abs(v) < 0.5 else f"{v:+.0f}%"))
    lo, hi = np.nanmin(rel), np.nanmax(rel)
    axr.set_ylim(min(lo * 1.15, -2), max(hi * 1.15, 2))
    ax1.fill_between(dates, dip.cash, color=ORANGE, alpha=0.38, lw=0, zorder=3)
    ax1.plot(dates, dip.cash, color=ORANGE, lw=1.6, zorder=4)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(money))
    ax1.set_ylabel("Dip-buyer's\nuninvested cash")
    ax1.set_ylim(0, max(1, dip.cash.max()) * 1.12)
    ax2.plot(dates, dd, color=INK2, lw=1.4, zorder=4)
    ax2.axhline(-thr * 100, color=ORANGE, lw=1.3, ls=(0, (4, 3)), zorder=3)
    ax2.text(pd.Timestamp("2019-06-01"), -thr * 100 - 2.0, "buy trigger: 20% below the high", color=INK2, fontsize=9, va="top", ha="right")
    ax2.set_ylabel("XIU below its\nall-time high")
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax2.set_ylim(min(dd.min() * 1.1, -45), 4)
    ax2.xaxis.set_major_locator(mdates.YearLocator(2))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax2.set_xlim(dates[0], dates[-1] + pd.Timedelta(days=5))
    for ax in axes:
        ax.grid(axis="x", visible=False)
    s0 = dates[0].strftime("%b %Y")
    s1 = dates[-1].strftime("%b %Y")
    diff_pct = (dip.final_value / dca.final_value - 1) * 100
    fig.text(0.085, 0.972, f"One 20-year window: $500 a month into XIU, {s0} to {s1}", fontsize=16, fontweight="bold", va="top")
    fig.text(0.085, 0.941, f"This is the MEDIAN window for the 20% rule (not a hand-picked one): the dip-buyer ends {diff_pct:+.1f}% vs monthly DCA.",
             fontsize=10.8, color=INK2, va="top")
    items = [plt.Line2D([0], [0], color=BLUE, lw=2.2, label="Monthly DCA: buy $500 on the first trading day"),
             plt.Line2D([0], [0], color=ORANGE, lw=2.2, label="Buy the dip: save cash, invest it all when 20% below the high"),
             plt.Line2D([0], [0], color=MUTED, lw=1.6, ls=(0, (4, 3)), label="Total cash put in"),
             Patch(facecolor=ZONE, label="Index 20%+ below its high (dip rule 'on')")]
    fig.legend(handles=items, loc="upper left", bbox_to_anchor=(0.075, 0.905), ncol=2, frameon=False, fontsize=9.8, labelcolor=INK2,
               columnspacing=1.6, handlelength=1.8)
    fig.text(0.085, 0.012, "Cash earns the Canadian 3-month T-bill rate; 0.05% spread per purchase; dividends reinvested; fills at the next trading day's close.\n"
                           "A window is one start month. Other start months give different answers: see results/by_start_year.csv.\n"
                           "Sources: Yahoo Finance (XIU.TO), Bank of Canada (T-bill yield). Code and method: METHODOLOGY.md",
             fontsize=8.1, color=MUTED, va="bottom", linespacing=1.45)
    p = OUT / "2_example_20y_window.png"
    fig.savefig(p, dpi=160)
    plt.close(fig)
    return p, {"start": s0, "end": s1, "diff_pct": diff_pct, "dca_final": dca.final_value, "dip_final": dip.final_value,
               "dip_buys": len(dip.buys), "peak_cash": float(dip.cash.max())}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    head = pd.read_csv(RES / "headline_table.csv")
    p1 = chart1(head)
    p2, info = chart2()
    p3 = chart3(head)
    print("wrote", p1.name, p2.name, p3.name)
    print("example window:", info)


if __name__ == "__main__":
    main()
