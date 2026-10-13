"""rNPV engine for the Idorsia valuation.

Pure functions that take the assumption dicts from `assumptions.py` and
return revenue curves, per-product risk-adjusted NPVs, central costs, and
aggregated per-share fair value. Nothing here reads from disk or writes
files.

Convention: all cash figures in CHF millions, all years are integers.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import assumptions as A


# ---------------------------------------------------------------------------
# Revenue and operating-margin curves
# ---------------------------------------------------------------------------

def revenue_curve(
    product: dict,
    valuation_year: int = 2026,
    horizon_year: int = 2050,
) -> pd.Series:
    """Annual sales projection for a single product, CHF millions.

    Shape: prelaunch = 0, ramp = linear from last known year sales (or 0)
    to `peak_sales_chf_m` by `launch_year + ramp_years`, then flat plateau
    to `patent_expiry`, then a -85 % cliff in the year after expiry with
    30 % annual decay thereafter.
    """
    years = np.arange(valuation_year, horizon_year + 1)
    sales = pd.Series(0.0, index=years, name=product["name"])

    launch = product["launch_year"]
    peak = product["peak_sales_chf_m"]
    ramp_years = product["ramp_years"]
    peak_year = launch + ramp_years
    expiry = product["patent_expiry"]

    historical = product.get("historical_sales_chf_m", {}) or {}

    for y in years:
        if y < launch:
            sales[y] = 0.0
            continue

        if y in historical:
            sales[y] = historical[y]
            continue

        if y <= peak_year:
            anchor_year = max(
                [ay for ay in historical.keys() if ay < y] + [launch - 1],
                default=launch - 1,
            )
            anchor_val = historical.get(anchor_year, 0.0)
            if peak_year == anchor_year:
                sales[y] = peak
            else:
                sales[y] = anchor_val + (peak - anchor_val) * (
                    (y - anchor_year) / (peak_year - anchor_year)
                )
            continue

        if y <= expiry:
            sales[y] = peak
            continue

        years_post_cliff = y - expiry
        if years_post_cliff == 1:
            sales[y] = peak * 0.15
        else:
            sales[y] = sales[y - 1] * 0.70

    return sales.clip(lower=0.0)


def product_margin_curve(
    product: dict,
    valuation_year: int = 2026,
    horizon_year: int = 2050,
) -> pd.Series:
    """Per-year operating margin for a single product.

    Interpolates linearly from `op_margin_at_launch` at
    `op_margin_launch_anchor_year` to `op_margin_at_peak` at
    `op_margin_peak_anchor_year`, then holds at the peak margin.

    Backwards-compatibility: if a product dict only has the old
    scalar `op_margin` key, the margin is flat at that value.
    """
    years = np.arange(valuation_year, horizon_year + 1)
    if "op_margin_at_launch" in product and "op_margin_at_peak" in product:
        m_lo = float(product["op_margin_at_launch"])
        m_hi = float(product["op_margin_at_peak"])
        y_lo = int(product.get("op_margin_launch_anchor_year", product["launch_year"]))
        y_hi = int(product.get("op_margin_peak_anchor_year", product["launch_year"] + product["ramp_years"]))
    else:
        flat = float(product.get("op_margin", 0.0))
        return pd.Series(flat, index=years, name=f"{product['name']} margin")

    span = max(1, y_hi - y_lo)
    out = pd.Series(0.0, index=years, name=f"{product['name']} margin")
    for y in years:
        if y <= y_lo:
            out[y] = m_lo
        elif y >= y_hi:
            out[y] = m_hi
        else:
            out[y] = m_lo + (m_hi - m_lo) * (y - y_lo) / span
    return out


def operating_cash_flow_curve(
    product: dict,
    valuation_year: int = 2026,
    horizon_year: int = 2050,
) -> pd.Series:
    """Sales x (margin curve) minus J&J contingent royalty haircut on sales."""
    sales = revenue_curve(product, valuation_year, horizon_year)
    margin = product_margin_curve(product, valuation_year, horizon_year)
    jj = float(product.get("jj_royalty_haircut", 0.0))
    return sales * (margin - jj)


# ---------------------------------------------------------------------------
# Development costs: phase-weighted, scheduled after readouts
# ---------------------------------------------------------------------------

def development_cost_curve(
    product: dict,
    valuation_year: int = 2026,
) -> pd.Series:
    """Remaining prelaunch development spend, scheduled by phase.

    rNPV convention revised from v1.0:
      - Current-phase remaining cost is CERTAIN (spread 1-to-1 over years
        up to `readout_year`).
      - Each subsequent phase cost is weighted by the CUMULATIVE probability
        of reaching that phase (product of BIO 2021 transitions). Spending
        on a next phase does not start until after the current phase readout.
      - Phase 3 / filing costs can be overridden per-product via
        `phase3_cost_override_chf_m` / `filing_cost_override_chf_m`.

    For `marketed` products this returns an empty Series.
    """
    phase = product["phase"]
    if phase == "marketed":
        return pd.Series(dtype=float)

    launch = int(product["launch_year"])
    if launch <= valuation_year:
        return pd.Series(dtype=float)

    readout = int(product.get("readout_year", valuation_year))
    readout = max(readout, valuation_year)

    schedule: dict[int, float] = {}

    # 1) Current-phase remaining (CERTAIN)
    cur_cost = float(product.get("remaining_current_phase_cost_chf_m", 0.0))
    cur_phase_years = [y for y in range(valuation_year, min(readout, launch - 1) + 1)]
    if cur_phase_years and cur_cost > 0.0:
        per_year = cur_cost / len(cur_phase_years)
        for y in cur_phase_years:
            schedule[y] = schedule.get(y, 0.0) + per_year

    # 2) Subsequent phases, weighted by cumulative transition probability
    phase_idx = A.PHASE_ORDER.index(phase)
    cumulative_prob = 1.0
    next_phase_start = readout + 1

    for i in range(phase_idx, len(A.PHASE_ORDER)):
        from_phase = A.PHASE_ORDER[i]
        if i + 1 < len(A.PHASE_ORDER):
            to_phase = A.PHASE_ORDER[i + 1]
        else:
            # last transition is filing -> approval; no further cost to spend
            break

        trans_prob = A.POS_TRANSITIONS[f"{from_phase}_to_{to_phase}"]
        cumulative_prob *= trans_prob

        full_cost = A.DEV_COSTS_BY_PHASE_CHF_M.get(to_phase, 0.0)
        ov_key = f"{to_phase}_cost_override_chf_m"
        if ov_key in product and product[ov_key] is not None:
            full_cost = float(product[ov_key])
        if full_cost <= 0.0:
            # advance scheduling cursor by the phase's default duration anyway
            next_phase_start += A.DEV_PHASE_DURATION_YEARS.get(to_phase, 1)
            continue

        weighted_cost = full_cost * cumulative_prob
        duration = A.DEV_PHASE_DURATION_YEARS.get(to_phase, 1)

        phase_years = [
            y for y in range(next_phase_start, next_phase_start + duration)
            if y < launch
        ]
        if not phase_years:
            # Phase would start at or after launch; squeeze into the last
            # prelaunch year rather than drop the cost.
            phase_years = [launch - 1]

        per_year = weighted_cost / len(phase_years)
        for y in phase_years:
            schedule[y] = schedule.get(y, 0.0) + per_year

        next_phase_start += duration

    if not schedule:
        return pd.Series(dtype=float)
    s = pd.Series(schedule).sort_index()
    s.name = f"{product['name']} dev"
    return s


# ---------------------------------------------------------------------------
# Central costs (unallocated G&A + upstream research)
# ---------------------------------------------------------------------------

def _weighted_revenue_series(
    products: dict[str, dict] | None,
    valuation_year: int,
    horizon_year: int,
) -> pd.Series:
    """PoS-weighted revenue, summed across included products. Used to scale
    central costs beyond `CENTRAL_COSTS_PLATEAU_END_YEAR`."""
    products = products if products is not None else A.PRODUCTS
    years = np.arange(valuation_year, horizon_year + 1)
    out = pd.Series(0.0, index=years)
    for p in products.values():
        if not p.get("include", True):
            continue
        pos = float(p["pos"])
        sales = revenue_curve(p, valuation_year, horizon_year)
        out = out.add(pos * sales, fill_value=0.0)
    return out


def central_costs_series(
    products: dict[str, dict] | None = None,
    valuation_year: int = 2026,
    horizon_year: int | None = None,
    ga_year_1: float | None = None,
    upstream_year_1: float | None = None,
) -> pd.Series:
    """Annual CHF M series of unallocated central costs (G&A + upstream R&D).

    Shape:
      * Years [valuation, PLATEAU_END]: start at `(ga + upstream)`, decline
        10 %/year until the floor CHF 50 M, then plateau at the floor.
      * Years [PLATEAU_END+1, HORIZON]: proportional to the model's PoS-
        weighted revenue (scaled from the plateau year), with a hard floor
        at CHF 10 M.
    """
    ga_1 = A.CENTRAL_COSTS_GA_YEAR_1_CHF_M if ga_year_1 is None else float(ga_year_1)
    up_1 = A.CENTRAL_COSTS_UPSTREAM_YEAR_1_CHF_M if upstream_year_1 is None else float(upstream_year_1)
    year_1 = ga_1 + up_1
    horizon = A.CENTRAL_COSTS_HORIZON_END_YEAR if horizon_year is None else horizon_year
    plateau_end = A.CENTRAL_COSTS_PLATEAU_END_YEAR

    years = np.arange(valuation_year, horizon + 1)
    series = pd.Series(0.0, index=years, name="central_costs")

    # Decay to floor over 2026 -> plateau_end
    v = year_1
    for y in range(valuation_year, plateau_end + 1):
        v_use = max(v, A.CENTRAL_COSTS_FLOOR_CHF_M)
        series[y] = v_use
        v = v * (1.0 - A.CENTRAL_COSTS_DECAY)

    # Proportional to weighted revenue beyond plateau_end
    weighted_rev = _weighted_revenue_series(products, valuation_year, horizon)
    anchor_cost = series.get(plateau_end, A.CENTRAL_COSTS_FLOOR_CHF_M)
    anchor_rev = float(weighted_rev.get(plateau_end, 0.0))
    if anchor_rev > 0:
        ratio = anchor_cost / anchor_rev
    else:
        ratio = 0.0

    for y in range(plateau_end + 1, horizon + 1):
        if y in weighted_rev.index:
            raw = ratio * float(weighted_rev[y])
            series[y] = max(raw, A.CENTRAL_COSTS_TAIL_FLOOR_CHF_M)

    return series


def central_costs_pv(
    products: dict[str, dict] | None = None,
    valuation_year: int = 2026,
    horizon_year: int | None = None,
    discount_rate: float | None = None,
    ga_year_1: float | None = None,
    upstream_year_1: float | None = None,
) -> float:
    """Present value of the central-cost series at `discount_rate`, mid-year."""
    horizon = A.CENTRAL_COSTS_HORIZON_END_YEAR if horizon_year is None else horizon_year
    r = A.DISCOUNT_RATE if discount_rate is None else discount_rate
    series = central_costs_series(
        products, valuation_year, horizon, ga_year_1, upstream_year_1,
    )
    df = discount_factors(valuation_year, horizon, r)
    df = df.reindex(series.index, fill_value=0.0)
    return float((series * df).sum())


# ---------------------------------------------------------------------------
# Discounting and rNPV per product
# ---------------------------------------------------------------------------

def discount_factors(
    valuation_year: int,
    horizon_year: int,
    rate: float,
    convention: str = "mid_year",
) -> pd.Series:
    """Discount factors for each year t in [valuation_year, horizon_year].

    convention:
      - "mid_year"      -> 1/(1+r)^(t - t0 + 0.5)   [textbook rNPV default]
      - "start_of_year" -> 1/(1+r)^(t - t0)         [no discount on t0 CF]
      - "end_of_year"   -> 1/(1+r)^(t - t0 + 1)     [full year of discount on t0 CF]
    """
    years = np.arange(valuation_year, horizon_year + 1)
    if convention == "mid_year":
        offset = 0.5
    elif convention == "start_of_year":
        offset = 0.0
    elif convention == "end_of_year":
        offset = 1.0
    else:
        raise ValueError(f"Unknown discount convention: {convention}")
    return pd.Series(
        1.0 / (1.0 + rate) ** (years - valuation_year + offset),
        index=years,
        name="dcf",
    )


@dataclass(frozen=True)
class ProductValuation:
    key: str
    name: str
    phase: str
    pos: float
    pv_operating_cf: float         # Σ CF_t × df_t (before PoS)
    pv_dev_costs: float            # Σ DevCost_t × df_t (phase-weighted)
    rnpv: float                    # pos × pv_operating_cf - pv_dev_costs


def product_rnpv(
    key: str,
    product: dict,
    valuation_year: int = 2026,
    horizon_year: int = 2050,
    discount_rate: float | None = None,
) -> ProductValuation:
    """Risk-adjusted NPV of a single product.

    rNPV = PoS × Σ_t CF_t × df_t  -  Σ_t DevCost_t × df_t

    DevCost_t is phase-weighted and scheduled by `development_cost_curve`:
    the current phase is CERTAIN, future phases are weighted by cumulative
    transition probability.
    """
    r = A.DISCOUNT_RATE if discount_rate is None else discount_rate
    df = discount_factors(valuation_year, horizon_year, r)

    ocf = operating_cash_flow_curve(product, valuation_year, horizon_year)
    dev = development_cost_curve(product, valuation_year)

    pv_ocf = float((ocf * df).sum())
    pv_dev = float((dev * df.reindex(dev.index, fill_value=0.0)).sum())

    pos = product["pos"]
    rnpv = pos * pv_ocf - pv_dev
    return ProductValuation(
        key=key,
        name=product["name"],
        phase=product["phase"],
        pos=pos,
        pv_operating_cf=pv_ocf,
        pv_dev_costs=pv_dev,
        rnpv=rnpv,
    )


# ---------------------------------------------------------------------------
# Aggregation -> equity value -> per share
# ---------------------------------------------------------------------------

def all_product_rnpvs(
    products: dict[str, dict] | None = None,
    valuation_year: int = 2026,
    horizon_year: int = 2050,
    discount_rate: float | None = None,
) -> list[ProductValuation]:
    """rNPV for every included product."""
    products = products if products is not None else A.PRODUCTS
    return [
        product_rnpv(k, p, valuation_year, horizon_year, discount_rate)
        for k, p in products.items()
        if p.get("include", True)
    ]


def equity_value_bridge(
    products: dict[str, dict] | None = None,
    valuation_year: int = 2026,
    horizon_year: int = 2050,
    discount_rate: float | None = None,
    include_sarl_residual: bool = False,
    include_central_costs: bool = True,
) -> dict:
    """Bridge from product rNPVs to parent-attributable equity value.

    EQUITY_VALUE(parent) = Σ rNPV(product) + parent net cash
                           + (SARL residual, if any)
                           - PV(central costs)
    """
    valuations = all_product_rnpvs(products, valuation_year, horizon_year, discount_rate)
    sum_rnpv = sum(v.rnpv for v in valuations)
    net_cash = A.parent_net_cash_chf_m()
    sarl = A.SARL_RESIDUAL_VALUE_CHF_M if include_sarl_residual else 0.0
    central_pv = (
        central_costs_pv(products, valuation_year, horizon_year, discount_rate)
        if include_central_costs else 0.0
    )
    equity_value = sum_rnpv + net_cash + sarl - central_pv
    return {
        "products": valuations,
        "sum_rnpv_chf_m": sum_rnpv,
        "parent_net_cash_chf_m": net_cash,
        "sarl_residual_chf_m": sarl,
        "central_costs_pv_chf_m": central_pv,
        "equity_value_chf_m": equity_value,
    }


# Backwards-compatibility alias (deprecated, kept so stale notebooks/plots
# don't break during the transition to equity_value_bridge).
def enterprise_value(*args, **kwargs) -> dict:
    bridge = equity_value_bridge(*args, **kwargs)
    bridge["ev_chf_m"] = bridge["equity_value_chf_m"]
    return bridge


def value_per_share(
    products: dict[str, dict] | None = None,
    valuation_year: int = 2026,
    horizon_year: int = 2050,
    discount_rate: float | None = None,
    shares_m: float | None = None,
    diluted: bool = False,
    include_sarl_residual: bool = False,
    include_central_costs: bool = True,
    floor_at_zero: bool = True,
) -> dict:
    """Per-share fair value in CHF, plus the full bridge.

    `floor_at_zero=True` enforces limited liability: the reported
    `value_per_share_chf` is max(0, raw). The raw (potentially negative)
    value is kept under `value_per_share_raw_chf` for display in notes.
    """
    if shares_m is None:
        shares_m = (
            A.POTENTIAL_SHARES_FULLY_DILUTED_M if diluted else A.SHARES_OUTSTANDING_M
        )
    bridge = equity_value_bridge(
        products=products,
        valuation_year=valuation_year,
        horizon_year=horizon_year,
        discount_rate=discount_rate,
        include_sarl_residual=include_sarl_residual,
        include_central_costs=include_central_costs,
    )
    raw = bridge["equity_value_chf_m"] / shares_m
    floored = max(0.0, raw) if floor_at_zero else raw
    bridge["shares_m"] = shares_m
    bridge["value_per_share_raw_chf"] = raw
    bridge["value_per_share_chf"] = floored
    bridge["value_per_share_floored"] = (raw < 0.0 and floor_at_zero)
    bridge["market_price_chf"] = A.SHARE_PRICE_CURRENT_CHF
    bridge["market_price_as_of"] = A.SHARE_PRICE_CURRENT_AS_OF
    denom = A.SHARE_PRICE_CURRENT_CHF if A.SHARE_PRICE_CURRENT_CHF > 0 else float("nan")
    bridge["upside_pct"] = (floored / denom - 1.0) * 100.0
    # Backwards-compat alias
    bridge["ev_chf_m"] = bridge["equity_value_chf_m"]
    return bridge


# ---------------------------------------------------------------------------
# J&J convertible: if-converted test
# ---------------------------------------------------------------------------

def apply_if_converted(
    bridge: dict,
    strike_chf: float | None = None,
    converted_shares_m: float | None = None,
    principal_chf_m: float | None = None,
) -> dict:
    """If V/share > strike, treat the J&J convertible as converted.

    Modifies a bridge dict (as returned by `value_per_share`) by removing the
    CHF 335 M principal from parent debt (so equity value goes UP by that
    amount) and adding 29.1 M shares (so per-share goes DOWN with dilution).

    The option belongs to J&J, so this is a cost to the equity holder — it
    is never an upside. We toggle it on only when V/share exceeds strike,
    representing J&J's rational conversion decision.

    Returns a new dict with the post-conversion equity value, share count,
    and per-share value exposed under `_post_conversion_` keys, and a
    `jj_converted` flag indicating whether the test triggered.
    """
    strike = A.JJ_CONVERTIBLE_STRIKE_CHF if strike_chf is None else float(strike_chf)
    conv_shares = (
        A.JJ_CONVERTIBLE_SHARES_ON_CONVERSION_M if converted_shares_m is None
        else float(converted_shares_m)
    )
    principal = (
        A.JJ_CONVERTIBLE_PRINCIPAL_CHF_M if principal_chf_m is None
        else float(principal_chf_m)
    )

    out = dict(bridge)
    out["jj_strike_chf"] = strike

    v_pre = bridge.get("value_per_share_chf", 0.0)
    # Use the raw (pre-floor) value for the conversion trigger: J&J will
    # convert iff the underlying asset value per share exceeds the strike,
    # regardless of the limited-liability display floor.
    v_raw = bridge.get("value_per_share_raw_chf", v_pre)
    triggered = v_raw > strike

    out["jj_converted"] = triggered
    if not triggered:
        out["value_per_share_post_conversion_chf"] = v_pre
        return out

    new_equity = bridge["equity_value_chf_m"] + principal
    new_shares = bridge["shares_m"] + conv_shares
    new_raw = new_equity / new_shares
    new_floored = max(0.0, new_raw)
    out["equity_value_post_conversion_chf_m"] = new_equity
    out["shares_post_conversion_m"] = new_shares
    out["value_per_share_post_conversion_raw_chf"] = new_raw
    out["value_per_share_post_conversion_chf"] = new_floored
    return out


# ---------------------------------------------------------------------------
# Helpers for display
# ---------------------------------------------------------------------------

def gap_covered_pct(scenario_v: float, base_v: float, market_v: float) -> float:
    """Fraction of the base->market gap covered by a given scenario, in %."""
    denom = (market_v - base_v)
    if abs(denom) < 1e-9:
        return float("nan")
    return 100.0 * (scenario_v - base_v) / denom


def revenue_table(
    products: dict[str, dict] | None = None,
    valuation_year: int = 2026,
    horizon_year: int = 2050,
) -> pd.DataFrame:
    """Wide DataFrame: rows = year, columns = product, values = sales CHF M."""
    products = products if products is not None else A.PRODUCTS
    cols = {
        k: revenue_curve(p, valuation_year, horizon_year)
        for k, p in products.items()
        if p.get("include", True)
    }
    return pd.DataFrame(cols)


def valuation_summary(bridge: dict) -> pd.DataFrame:
    """One line per product summary DataFrame."""
    rows = []
    for v in bridge["products"]:
        rows.append(
            {
                "product": v.name,
                "phase": v.phase,
                "pos": v.pos,
                "pv_operating_cf_chf_m": v.pv_operating_cf,
                "pv_dev_costs_chf_m": v.pv_dev_costs,
                "rnpv_chf_m": v.rnpv,
            }
        )
    return pd.DataFrame(rows)
