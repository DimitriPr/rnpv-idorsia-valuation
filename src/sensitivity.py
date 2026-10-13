"""Sensitivity analyses and figure generation for the Idorsia rNPV.

Computes:
  - Value/share heatmap over (discount rate) × (QUVIVIQ peak sales)
  - Tornado of the 6 dominant variables (±20 % / ±30 %)
  - Bear / Base / Bull scenarios

Generates PNGs into outputs/figures/ using a dark theme matched to the
site's Bloomberg green CSS.

All functions are pure w.r.t. the assumptions module, they mutate a
deepcopy of the products dict, not the module level dict.
"""

from __future__ import annotations

import copy
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import assumptions as A
from . import rnpv


# ---------------------------------------------------------------------------
# Styling, match the site's dark green Bloomberg theme
# ---------------------------------------------------------------------------
ACCENT = "#4a8b63"
ACCENT_DARK = "#2d5f3f"
ACCENT_BRIGHT = "#6fb289"
BG = "#0d0d0d"
BG_PANEL = "#141414"
FG = "#e0e0e0"
MUTED = "#888888"
NEG = "#c85454"
POS = "#4a8b63"

PHASE_PALETTE = {
    "marketed": "#6fb289",
    "filed":    "#4a8b63",
    "phase3":   "#3a7050",
    "phase2":   "#c9a24a",
    "phase1":   "#c85454",
}


def _apply_theme(ax: plt.Axes) -> None:
    ax.set_facecolor(BG_PANEL)
    for spine in ax.spines.values():
        spine.set_color(MUTED)
        spine.set_linewidth(0.5)
    ax.tick_params(colors=FG, labelsize=9)
    ax.xaxis.label.set_color(FG)
    ax.yaxis.label.set_color(FG)
    ax.title.set_color(FG)
    ax.grid(True, color=MUTED, alpha=0.15, linewidth=0.5)


def _new_fig(figsize=(9, 5)):
    fig, ax = plt.subplots(figsize=figsize, dpi=140)
    fig.patch.set_facecolor(BG)
    _apply_theme(ax)
    return fig, ax


FIG_DIR = Path(__file__).resolve().parent.parent / "outputs" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Utility: recompute value/share with product overrides
# ---------------------------------------------------------------------------

def _with_overrides(overrides: dict[str, dict]) -> dict[str, dict]:
    """Return a deep copied PRODUCTS dict with per product field overrides."""
    products = copy.deepcopy(A.PRODUCTS)
    for key, changes in overrides.items():
        if key not in products:
            continue
        products[key].update(changes)
    return products


def _value_per_share(
    product_overrides: dict[str, dict] | None = None,
    discount_rate: float | None = None,
    include_sarl_residual: bool = False,
    sarl_residual_chf_m: float | None = None,
    central_upstream_year_1_chf_m: float | None = None,
    floor_at_zero: bool = True,
) -> float:
    """Wrapper that returns just the per-share value (CHF)."""
    products = A.PRODUCTS if not product_overrides else _with_overrides(product_overrides)
    original_sarl = A.SARL_RESIDUAL_VALUE_CHF_M
    original_upstream = A.CENTRAL_COSTS_UPSTREAM_YEAR_1_CHF_M
    if sarl_residual_chf_m is not None:
        A.SARL_RESIDUAL_VALUE_CHF_M = sarl_residual_chf_m
    if central_upstream_year_1_chf_m is not None:
        A.CENTRAL_COSTS_UPSTREAM_YEAR_1_CHF_M = central_upstream_year_1_chf_m
    try:
        bridge = rnpv.value_per_share(
            products=products,
            discount_rate=discount_rate,
            include_sarl_residual=include_sarl_residual,
            floor_at_zero=floor_at_zero,
        )
        return bridge["value_per_share_chf"]
    finally:
        A.SARL_RESIDUAL_VALUE_CHF_M = original_sarl
        A.CENTRAL_COSTS_UPSTREAM_YEAR_1_CHF_M = original_upstream


# ---------------------------------------------------------------------------
# 1. Heatmap, discount rate × QUVIVIQ peak sales
# ---------------------------------------------------------------------------

def heatmap_rate_vs_quviviq_peak(
    rates: np.ndarray | None = None,
    peaks: np.ndarray | None = None,
) -> pd.DataFrame:
    if rates is None:
        rates = np.arange(0.09, 0.15 + 1e-9, 0.01)
    if peaks is None:
        peaks = np.arange(400, 1101, 100)
    values = np.zeros((len(peaks), len(rates)))
    for i, peak in enumerate(peaks):
        for j, r in enumerate(rates):
            values[i, j] = _value_per_share(
                product_overrides={"quviviq": {"peak_sales_chf_m": float(peak)}},
                discount_rate=float(r),
            )
    return pd.DataFrame(values, index=peaks, columns=np.round(rates, 3))


def plot_heatmap(df: pd.DataFrame, out: Path = FIG_DIR / "sensitivity_heatmap.png") -> Path:
    fig, ax = _new_fig(figsize=(8, 5.5))
    im = ax.imshow(
        df.values,
        aspect="auto",
        cmap="RdYlGn",
        origin="lower",
        extent=[
            df.columns.min() - 0.005,
            df.columns.max() + 0.005,
            df.index.min() - 50,
            df.index.max() + 50,
        ],
        vmin=0,
        vmax=max(df.values.max(), A.SHARE_PRICE_CURRENT_CHF * 1.5),
    )
    # Annotate
    for i, peak in enumerate(df.index):
        for j, rate in enumerate(df.columns):
            ax.text(
                rate,
                peak,
                f"{df.iloc[i, j]:.2f}",
                ha="center",
                va="center",
                color="black" if df.iloc[i, j] > 2.0 else "white",
                fontsize=8,
            )
    ax.set_xlabel("Discount rate")
    ax.set_ylabel("QUVIVIQ peak sales (CHF M)")
    ax.set_title("Value / share (CHF), QUVIVIQ peak × discount rate",
                 fontsize=11, fontweight="semibold", pad=14)
    ax.axhline(A.PRODUCTS["quviviq"]["peak_sales_chf_m"], color=FG, linestyle="--", linewidth=0.7, alpha=0.6)
    ax.axvline(A.DISCOUNT_RATE, color=FG, linestyle="--", linewidth=0.7, alpha=0.6)
    cbar = fig.colorbar(im, ax=ax)
    cbar.ax.tick_params(colors=FG, labelsize=8)
    cbar.set_label("CHF / share", color=FG, fontsize=9)
    fig.tight_layout()
    fig.savefig(out, facecolor=BG, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# 2. Tornado chart, variables ranked by impact
# ---------------------------------------------------------------------------

def tornado_data() -> pd.DataFrame:
    """Return a DataFrame with columns (variable, low, high, base) where low/high
    are the per share values at the low/high stress case."""
    base = _value_per_share()
    rows: list[dict] = []

    def _row(label: str, low_val: float, high_val: float):
        rows.append({
            "variable": label,
            "low": low_val,
            "high": high_val,
            "base": base,
            "swing": abs(high_val - low_val),
        })

    # a) QUVIVIQ peak sales ±30 %
    peak = A.PRODUCTS["quviviq"]["peak_sales_chf_m"]
    _row(
        f"QUVIVIQ peak sales (±30 %)",
        _value_per_share({"quviviq": {"peak_sales_chf_m": peak * 0.7}}),
        _value_per_share({"quviviq": {"peak_sales_chf_m": peak * 1.3}}),
    )
    # b) Lucerastat peak sales ±30 %
    lp = A.PRODUCTS["lucerastat"]["peak_sales_chf_m"]
    _row(
        "Lucerastat peak sales (±30 %)",
        _value_per_share({"lucerastat": {"peak_sales_chf_m": lp * 0.7}}),
        _value_per_share({"lucerastat": {"peak_sales_chf_m": lp * 1.3}}),
    )
    # c) Discount rate 10 % → 14 %
    _row(
        "Discount rate (10 % vs 14 %)",
        _value_per_share(discount_rate=0.14),
        _value_per_share(discount_rate=0.10),
    )
    # d) QUVIVIQ op margin at peak ±5 pp
    m_peak = A.PRODUCTS["quviviq"]["op_margin_at_peak"]
    _row(
        "QUVIVIQ op margin at peak (±5 pp)",
        _value_per_share({"quviviq": {"op_margin_at_peak": m_peak - 0.05}}),
        _value_per_share({"quviviq": {"op_margin_at_peak": m_peak + 0.05}}),
    )
    # e) Lucerastat PoS ±20 %
    lpos = A.PRODUCTS["lucerastat"]["pos"]
    _row(
        "Lucerastat PoS (±20 %)",
        _value_per_share({"lucerastat": {"pos": lpos * 0.8}}),
        _value_per_share({"lucerastat": {"pos": lpos * 1.2}}),
    )
    # f) SARL residual value (0 → 400 M CHF)
    _row(
        "SARL residual (0 vs CHF 400 M)",
        _value_per_share(sarl_residual_chf_m=0.0, include_sarl_residual=True),
        _value_per_share(sarl_residual_chf_m=400.0, include_sarl_residual=True),
    )
    # g) Central costs upstream (±50 %) — placeholder sensitivity
    u = A.CENTRAL_COSTS_UPSTREAM_YEAR_1_CHF_M
    _row(
        "Central costs: upstream R&D (±50 %)",
        _value_per_share(central_upstream_year_1_chf_m=u * 1.5),  # higher cost = lower value
        _value_per_share(central_upstream_year_1_chf_m=u * 0.5),
    )
    df = pd.DataFrame(rows).sort_values("swing", ascending=True).reset_index(drop=True)
    return df


def plot_tornado(df: pd.DataFrame, out: Path = FIG_DIR / "tornado.png") -> Path:
    fig, ax = _new_fig(figsize=(9, 5))
    base = df["base"].iloc[0]
    y = np.arange(len(df))
    ax.barh(
        y,
        df["low"] - base,
        left=base,
        color=NEG,
        alpha=0.85,
        label="Low case",
    )
    ax.barh(
        y,
        df["high"] - base,
        left=base,
        color=POS,
        alpha=0.85,
        label="High case",
    )
    ax.axvline(base, color=FG, linewidth=1.0)
    ax.axvline(A.SHARE_PRICE_CURRENT_CHF, color=ACCENT_BRIGHT, linestyle="--", linewidth=0.9,
               label=f"Market (CHF {A.SHARE_PRICE_CURRENT_CHF:.2f})")
    ax.set_yticks(y)
    ax.set_yticklabels(df["variable"], color=FG)
    ax.set_xlabel("Value / share (CHF)")
    ax.set_title(
        f"Tornado, base case CHF {base:.2f}/share",
        fontsize=11, fontweight="semibold", pad=14,
    )
    ax.legend(facecolor=BG_PANEL, edgecolor=MUTED, labelcolor=FG, fontsize=9, loc="lower right")
    for i, r in df.iterrows():
        ax.text(r["low"], i, f" {r['low']:.2f}", va="center", ha="right", color=NEG, fontsize=8)
        ax.text(r["high"], i, f" {r['high']:.2f}", va="center", ha="left", color=POS, fontsize=8)
    fig.tight_layout()
    fig.savefig(out, facecolor=BG, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# 3. Revenue curves
# ---------------------------------------------------------------------------

REVENUE_COLORS = [
    "#6fb289",   # QUVIVIQ, bright green
    "#4a8fbf",   # Lucerastat, steel blue
    "#c9a24a",   # CCR6, amber
    "#b06fc9",   # CXCR7, violet
    "#d97a4a",   # CXCR3, orange
    "#c85454",   # placeholder for 6th
]


def plot_revenue_curves(out: Path = FIG_DIR / "revenue_curves.png") -> Path:
    fig, ax = _new_fig(figsize=(9, 5))
    df = rnpv.revenue_table()
    for (col, series), color in zip(df.items(), REVENUE_COLORS):
        p = A.PRODUCTS[col]
        ax.plot(series.index, series.values, label=p["name"], color=color, linewidth=1.8)
    ax.set_xlabel("Year")
    ax.set_ylabel("Annual net sales (CHF M)")
    ax.set_title("Revenue projections, ramp, plateau, patent cliff",
                 fontsize=11, fontweight="semibold", pad=14)
    ax.legend(facecolor=BG_PANEL, edgecolor=MUTED, labelcolor=FG, fontsize=9, loc="upper right")
    fig.tight_layout()
    fig.savefig(out, facecolor=BG, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# 4. Pipeline overview, rNPV contribution per product
# ---------------------------------------------------------------------------

_SHORT_NAME = {
    "QUVIVIQ (daridorexant)":            "QUVIVIQ",
    "Lucerastat":                        "Lucerastat",
    "IDOR-1117-2520 (CCR6 antagonist)":  "CCR6 antagonist",
    "ACT-1004-1239 (CXCR7 antagonist)":  "CXCR7 antagonist",
    "ACT-777991 (CXCR3 antagonist)":     "CXCR3 antagonist",
    "IDOR-1134-2831 (C. diff synthetic glycan vaccine)": "C. diff vaccine",
}


def plot_pipeline_overview(out: Path = FIG_DIR / "pipeline_overview.png") -> Path:
    bridge = rnpv.value_per_share()
    df = pd.DataFrame([{
        "product": _SHORT_NAME.get(v.name, v.name),
        "phase": v.phase,
        "pos": v.pos,
        "rnpv": v.rnpv,
    } for v in bridge["products"]]).sort_values("rnpv")

    fig, ax = _new_fig(figsize=(9, 4.5))
    colors = [PHASE_PALETTE.get(p, ACCENT) for p in df["phase"]]
    y = np.arange(len(df))
    ax.barh(y, df["rnpv"], color=colors, alpha=0.9)
    ax.axvline(0, color=FG, linewidth=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(df["product"], color=FG)
    ax.set_xlabel("rNPV contribution (CHF M)")
    ax.set_title("Pipeline valuation, rNPV per product (base case)",
                 fontsize=11, fontweight="semibold", pad=14)

    xmax = max(df["rnpv"].max() * 1.35, 100.0)
    xmin = min(df["rnpv"].min() * 1.5, -100.0)
    ax.set_xlim(xmin, xmax)
    pad = xmax * 0.012

    # All labels sit to the RIGHT of each bar (in positive x-space for negative
    # bars, and past the bar's tip for positive bars). This keeps them clear of
    # the y-axis product names, which sit in the negative x-space margin.
    for i, r in df.reset_index(drop=True).iterrows():
        anchor_x = r["rnpv"] + pad if r["rnpv"] >= 0 else pad
        ax.text(
            anchor_x, i,
            f"{r['rnpv']:+,.0f} M CHF   (PoS {r['pos']:.0%})",
            va="center", ha="left", color=FG, fontsize=9,
        )
    fig.tight_layout()
    fig.savefig(out, facecolor=BG, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# 5. Waterfall, cash + rNPVs → EV → value/share
# ---------------------------------------------------------------------------

def plot_waterfall(out: Path = FIG_DIR / "waterfall_ev.png") -> Path:
    bridge = rnpv.value_per_share()
    steps = []
    steps.append(("Parent net cash", bridge["parent_net_cash_chf_m"]))
    for v in bridge["products"]:
        steps.append((v.name.split(" (")[0], v.rnpv))
    steps.append(("SARL residual", bridge["sarl_residual_chf_m"]))
    steps.append(("− PV central costs", -bridge["central_costs_pv_chf_m"]))
    steps.append(("Equity value (parent)", bridge["equity_value_chf_m"]))

    labels = [s[0] for s in steps]
    values = [s[1] for s in steps]

    fig, ax = _new_fig(figsize=(10, 5))
    cumulative = 0.0
    for i, (lab, val) in enumerate(zip(labels, values)):
        if lab == "Equity value (parent)":
            ax.bar(i, val, color=ACCENT_BRIGHT if val >= 0 else NEG, alpha=0.95)
            ax.text(i, val, f" {val:,.0f}", ha="center", va="bottom" if val >= 0 else "top", color=FG, fontsize=9)
        else:
            color = POS if val >= 0 else NEG
            ax.bar(i, val, bottom=cumulative, color=color, alpha=0.85)
            ax.text(
                i,
                cumulative + val,
                f" {val:,.0f}",
                ha="center",
                va="bottom" if val >= 0 else "top",
                color=FG,
                fontsize=8,
            )
            cumulative += val
    ax.axhline(0, color=FG, linewidth=0.6)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=25, ha="right", color=FG, fontsize=9)
    ax.set_ylabel("CHF M")
    _per_share_label = (
        f"CHF {bridge['value_per_share_chf']:.2f}/share"
        f" (floored; raw {bridge['value_per_share_raw_chf']:.2f})"
        if bridge.get("value_per_share_floored")
        else f"CHF {bridge['value_per_share_chf']:.2f}/share"
    )
    ax.set_title(
        f"Bridge to parent equity value, CHF {bridge['equity_value_chf_m']:,.0f} M "
        f"→ {_per_share_label}",
        fontsize=11, fontweight="semibold", pad=14,
    )
    fig.tight_layout()
    fig.savefig(out, facecolor=BG, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# 6. Fair value vs market, the punchline
# ---------------------------------------------------------------------------

def scenarios() -> pd.DataFrame:
    rows = [
        ("Bear",
         {"quviviq": {"peak_sales_chf_m": 400},
          "lucerastat": {"peak_sales_chf_m": 250}},
         0.14, False, 0.0),
        ("Base",
         {},
         A.DISCOUNT_RATE, False, 0.0),
        ("Base + SARL residual",
         {},
         A.DISCOUNT_RATE, True, 400.0),
        ("Bull",
         {"quviviq": {"peak_sales_chf_m": 1000},
          "lucerastat": {"peak_sales_chf_m": 700}},
         0.10, True, 600.0),
    ]
    data = []
    for name, ov, r, sarl_on, sarl_val in rows:
        v = _value_per_share(
            product_overrides=ov,
            discount_rate=r,
            include_sarl_residual=sarl_on,
            sarl_residual_chf_m=sarl_val,
        )
        data.append({"scenario": name, "value_per_share": v})
    return pd.DataFrame(data)


def plot_fair_value_vs_market(out: Path = FIG_DIR / "fair_value_vs_market.png") -> Path:
    df = scenarios()
    fig, ax = _new_fig(figsize=(9, 4.5))
    colors = [NEG, ACCENT_DARK, ACCENT, ACCENT_BRIGHT]
    x = np.arange(len(df))
    ax.bar(x, df["value_per_share"], color=colors, alpha=0.9)
    ax.axhline(A.SHARE_PRICE_CURRENT_CHF, color=FG, linestyle="--", linewidth=1.0,
               label=f"Market (CHF {A.SHARE_PRICE_CURRENT_CHF:.2f})")
    ax.set_xticks(x)
    ax.set_xticklabels(df["scenario"], color=FG, fontsize=9)
    ax.set_ylabel("Value / share (CHF)")
    ax.set_title("Fair value scenarios vs current market price",
                 fontsize=11, fontweight="semibold", pad=14)
    for xi, val in zip(x, df["value_per_share"]):
        ax.text(xi, val, f"CHF {val:.2f}", ha="center", va="bottom", color=FG, fontsize=9)
    ax.legend(facecolor=BG_PANEL, edgecolor=MUTED, labelcolor=FG, fontsize=9, loc="upper left")
    fig.tight_layout()
    fig.savefig(out, facecolor=BG, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------

def generate_all() -> dict[str, Path]:
    outputs: dict[str, Path] = {}
    outputs["pipeline_overview"]   = plot_pipeline_overview()
    outputs["revenue_curves"]      = plot_revenue_curves()
    outputs["waterfall_ev"]        = plot_waterfall()
    outputs["sensitivity_heatmap"] = plot_heatmap(heatmap_rate_vs_quviviq_peak())
    outputs["tornado"]             = plot_tornado(tornado_data())
    outputs["fair_value_vs_market"]= plot_fair_value_vs_market()
    return outputs
