"""rNPV engine for the Idorsia valuation (v1.2).

Pure functions. Convention changes vs v1.1:
  * Valuation date is 30 June 2026, not 1 Jan 2026.
    - 2026 CF is prorated to H2 only (x 0.5) and discounted at exponent 0.25.
    - Year t >= 2027 CF is discounted at exponent (t - 2026) (standard
      mid-year distance from 30 Jun 2026).
  * `op_margin_*` fields are now CONTRIBUTION MARGIN = (sales - COGS - Selling) / sales.
    G&A and R&D are deducted ONCE elsewhere (central costs, dev costs).
  * J&J royalty is modelled centrally on the aggregate PoS-weighted sales
    stream with a CHF 272 M cumulative cap (removes per-product
    jj_royalty_haircut).

All cash figures in CHF millions, all years are integers.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import assumptions as A


# ---------------------------------------------------------------------------
# Revenue, margin and operating cash flow
# ---------------------------------------------------------------------------

def revenue_curve(
    product: dict,
    valuation_year: int = 2026,
    horizon_year: int = 2050,
) -> pd.Series:
    """Annual gross-sales projection for a single product (CHF M).

    The curve is NOT prorated to H2 2026 here — proration is applied once,
    in `_h2_prorate`, so operating cash flow, dev costs and central costs
    all share the same stub logic.
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
    """Per-year CONTRIBUTION margin for a single product.

    Interpolates linearly from `op_margin_at_launch` at
    `op_margin_launch_anchor_year` to `op_margin_at_peak` at
    `op_margin_peak_anchor_year`, then holds at the peak margin.

    Backwards-compat: a scalar `op_margin` key still produces a flat curve.
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
    """Sales x contribution-margin (no royalty haircut; J&J royalty is now
    modelled centrally, see `jj_residual_royalty_series`)."""
    sales = revenue_curve(product, valuation_year, horizon_year)
    margin = product_margin_curve(product, valuation_year, horizon_year)
    return sales * margin


# ---------------------------------------------------------------------------
# H2 2026 proration (shared by all cash-flow curves)
# ---------------------------------------------------------------------------

def _h2_prorate(series: pd.Series, valuation_year: int = 2026) -> pd.Series:
    """Multiply the valuation-year value by 0.5 (H2 2026 stub).

    All years after `valuation_year` are left untouched. The matching
    discount factor is 0.25 for the stub year, 1.0+(t-2027) for later years
    (see `discount_factors`).
    """
    out = series.copy()
    if valuation_year in out.index:
        out[valuation_year] = out[valuation_year] * 0.5
    return out


# ---------------------------------------------------------------------------
# Development costs: phase-weighted, scheduled after readouts
# ---------------------------------------------------------------------------

def development_cost_curve(
    product: dict,
    valuation_year: int = 2026,
) -> pd.Series:
    """Prelaunch dev spend. Current phase CERTAIN, future phases weighted
    by cumulative PoS. Years are integers; `_h2_prorate` is applied by
    callers that discount."""
    phase = product["phase"]
    if phase == "marketed":
        return pd.Series(dtype=float)

    launch = int(product["launch_year"])
    if launch <= valuation_year:
        return pd.Series(dtype=float)

    readout = int(product.get("readout_year", valuation_year))
    readout = max(readout, valuation_year)

    schedule: dict[int, float] = {}

    cur_cost = float(product.get("remaining_current_phase_cost_chf_m", 0.0))
    cur_phase_years = [y for y in range(valuation_year, min(readout, launch - 1) + 1)]
    if cur_phase_years and cur_cost > 0.0:
        per_year = cur_cost / len(cur_phase_years)
        for y in cur_phase_years:
            schedule[y] = schedule.get(y, 0.0) + per_year

    phase_idx = A.PHASE_ORDER.index(phase)
    cumulative_prob = 1.0
    next_phase_start = readout + 1

    for i in range(phase_idx, len(A.PHASE_ORDER)):
        from_phase = A.PHASE_ORDER[i]
        if i + 1 < len(A.PHASE_ORDER):
            to_phase = A.PHASE_ORDER[i + 1]
        else:
            break

        trans_prob = A.POS_TRANSITIONS[f"{from_phase}_to_{to_phase}"]
        cumulative_prob *= trans_prob

        full_cost = A.DEV_COSTS_BY_PHASE_CHF_M.get(to_phase, 0.0)
        ov_key = f"{to_phase}_cost_override_chf_m"
        if ov_key in product and product[ov_key] is not None:
            full_cost = float(product[ov_key])
        if full_cost <= 0.0:
            next_phase_start += A.DEV_PHASE_DURATION_YEARS.get(to_phase, 1)
            continue

        weighted_cost = full_cost * cumulative_prob
        duration = A.DEV_PHASE_DURATION_YEARS.get(to_phase, 1)

        phase_years = [
            y for y in range(next_phase_start, next_phase_start + duration)
            if y < launch
        ]
        if not phase_years:
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
# Central costs
# ---------------------------------------------------------------------------

def _weighted_revenue_series(
    products: dict[str, dict] | None,
    valuation_year: int,
    horizon_year: int,
) -> pd.Series:
    """PoS-weighted revenue summed across included products."""
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
    """Annual CHF M of unallocated central costs (G&A + upstream R&D)."""
    ga_1 = A.CENTRAL_COSTS_GA_YEAR_1_CHF_M if ga_year_1 is None else float(ga_year_1)
    up_1 = A.CENTRAL_COSTS_UPSTREAM_YEAR_1_CHF_M if upstream_year_1 is None else float(upstream_year_1)
    year_1 = ga_1 + up_1
    horizon = A.CENTRAL_COSTS_HORIZON_END_YEAR if horizon_year is None else horizon_year
    plateau_end = A.CENTRAL_COSTS_PLATEAU_END_YEAR

    years = np.arange(valuation_year, horizon + 1)
    series = pd.Series(0.0, index=years, name="central_costs")

    v = year_1
    for y in range(valuation_year, plateau_end + 1):
        v_use = max(v, A.CENTRAL_COSTS_FLOOR_CHF_M)
        series[y] = v_use
        v = v * (1.0 - A.CENTRAL_COSTS_DECAY)

    weighted_rev = _weighted_revenue_series(products, valuation_year, horizon)
    anchor_cost = series.get(plateau_end, A.CENTRAL_COSTS_FLOOR_CHF_M)
    anchor_rev = float(weighted_rev.get(plateau_end, 0.0))
    ratio = (anchor_cost / anchor_rev) if anchor_rev > 0 else 0.0

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
    """PV of the central-cost series. Applies the H2 2026 stub proration."""
    horizon = A.CENTRAL_COSTS_HORIZON_END_YEAR if horizon_year is None else horizon_year
    r = A.DISCOUNT_RATE if discount_rate is None else discount_rate
    series = _h2_prorate(
        central_costs_series(products, valuation_year, horizon, ga_year_1, upstream_year_1),
        valuation_year,
    )
    df = discount_factors(valuation_year, horizon, r)
    df = df.reindex(series.index, fill_value=0.0)
    return float((series * df).sum())


# ---------------------------------------------------------------------------
# J&J residual royalty (post-SARL, central, cumulative-capped)
# ---------------------------------------------------------------------------

def jj_residual_royalty_series(
    products: dict[str, dict] | None = None,
    valuation_year: int = 2026,
    horizon_year: int = 2050,
) -> pd.Series:
    """Annual J&J royalty cash outflow (CHF M), applied on the aggregate
    PoS-weighted sales stream, capped at `JJ_RESIDUAL_ROYALTY_CAP_REMAINING_CHF_M`
    cumulatively."""
    weighted_rev = _h2_prorate(
        _weighted_revenue_series(products, valuation_year, horizon_year),
        valuation_year,
    )
    rate = A.JJ_RESIDUAL_ROYALTY_RATE
    cap_remaining = A.JJ_RESIDUAL_ROYALTY_CAP_REMAINING_CHF_M
    out = pd.Series(0.0, index=weighted_rev.index, name="jj_royalty")
    for y in weighted_rev.index:
        raw = float(weighted_rev[y]) * rate
        pay = min(raw, cap_remaining)
        out[y] = pay
        cap_remaining -= pay
        if cap_remaining <= 0:
            break
    return out


def jj_residual_royalty_pv(
    products: dict[str, dict] | None = None,
    valuation_year: int = 2026,
    horizon_year: int = 2050,
    discount_rate: float | None = None,
) -> float:
    r = A.DISCOUNT_RATE if discount_rate is None else discount_rate
    series = jj_residual_royalty_series(products, valuation_year, horizon_year)
    df = discount_factors(valuation_year, horizon_year, r)
    df = df.reindex(series.index, fill_value=0.0)
    return float((series * df).sum())


# ---------------------------------------------------------------------------
# Discounting
# ---------------------------------------------------------------------------

def discount_factors(
    valuation_year: int,
    horizon_year: int,
    rate: float,
    convention: str = "mid_year_valuation_date",
) -> pd.Series:
    """Discount factors for year t in [valuation_year, horizon_year].

    convention:
      - "mid_year_valuation_date" (default, v1.2):
            valuation date is mid-year (30 Jun) of `valuation_year`.
            year  valuation_year  -> exponent 0.25 (H2 stub midpoint)
            year  valuation_year+1 -> exponent 1.0
            year  valuation_year+n -> exponent n
      - "mid_year"                 : textbook rNPV default, offset 0.5
      - "start_of_year"            : offset 0.0
      - "end_of_year"              : offset 1.0
    """
    years = np.arange(valuation_year, horizon_year + 1)

    if convention == "mid_year_valuation_date":
        exponents = np.where(
            years == valuation_year,
            0.25,
            years - valuation_year,
        )
    else:
        if convention == "mid_year":
            offset = 0.5
        elif convention == "start_of_year":
            offset = 0.0
        elif convention == "end_of_year":
            offset = 1.0
        else:
            raise ValueError(f"Unknown discount convention: {convention}")
        exponents = (years - valuation_year + offset).astype(float)

    return pd.Series(1.0 / (1.0 + rate) ** exponents, index=years, name="dcf")


# ---------------------------------------------------------------------------
# Product rNPV
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProductValuation:
    key: str
    name: str
    phase: str
    pos: float
    pv_operating_cf: float
    pv_dev_costs: float
    rnpv: float


def product_rnpv(
    key: str,
    product: dict,
    valuation_year: int = 2026,
    horizon_year: int = 2050,
    discount_rate: float | None = None,
) -> ProductValuation:
    """Risk-adjusted NPV. Contribution-margin convention, H2 2026 proration."""
    r = A.DISCOUNT_RATE if discount_rate is None else discount_rate
    df = discount_factors(valuation_year, horizon_year, r)

    ocf = _h2_prorate(
        operating_cash_flow_curve(product, valuation_year, horizon_year),
        valuation_year,
    )
    dev = _h2_prorate(
        development_cost_curve(product, valuation_year),
        valuation_year,
    )

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


def all_product_rnpvs(
    products: dict[str, dict] | None = None,
    valuation_year: int = 2026,
    horizon_year: int = 2050,
    discount_rate: float | None = None,
) -> list[ProductValuation]:
    products = products if products is not None else A.PRODUCTS
    return [
        product_rnpv(k, p, valuation_year, horizon_year, discount_rate)
        for k, p in products.items()
        if p.get("include", True)
    ]


# ---------------------------------------------------------------------------
# Equity value bridge and per-share
# ---------------------------------------------------------------------------

def equity_value_bridge(
    products: dict[str, dict] | None = None,
    valuation_year: int = 2026,
    horizon_year: int = 2050,
    discount_rate: float | None = None,
    include_sarl_residual: bool = False,
    include_central_costs: bool = True,
) -> dict:
    """Bridge from product rNPVs to parent-attributable equity value.

    EquityValue(parent) = Sum rNPV(product) + parent net cash
                          + (SARL residual, if included)
                          - PV(central costs)
                          - PV(J&J residual royalty)
    """
    valuations = all_product_rnpvs(products, valuation_year, horizon_year, discount_rate)
    sum_rnpv = sum(v.rnpv for v in valuations)
    net_cash = A.parent_net_cash_chf_m()
    sarl = A.SARL_RESIDUAL_VALUE_CHF_M if include_sarl_residual else 0.0
    central_pv = (
        central_costs_pv(products, valuation_year, horizon_year, discount_rate)
        if include_central_costs else 0.0
    )
    jj_royalty_pv = jj_residual_royalty_pv(
        products, valuation_year, horizon_year, discount_rate,
    )
    equity_value = sum_rnpv + net_cash + sarl - central_pv - jj_royalty_pv
    return {
        "products": valuations,
        "sum_rnpv_chf_m": sum_rnpv,
        "parent_net_cash_chf_m": net_cash,
        "sarl_residual_chf_m": sarl,
        "central_costs_pv_chf_m": central_pv,
        "jj_royalty_pv_chf_m": jj_royalty_pv,
        "equity_value_chf_m": equity_value,
    }


# Backwards-compatibility alias
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
    diluted: bool = False,            # kept for backwards compat; no-op in v1.2
    include_sarl_residual: bool = False,
    include_central_costs: bool = True,
    floor_at_zero: bool = True,
) -> dict:
    """Per-share fair value in CHF, plus the full bridge.

    v1.2 denominator convention: the "valuation-basis diluted" share count,
      issued + J&J (mandatory) + warrants + unvested free shares
      = 263.1 + 21.7 + 10.85 + 9.5
      = 305.15 M shares.
    CB 2034 (+2.72 M) is applied by `apply_if_converted` when V/share > CHF 6.
    Options (7.1 M at CHF 10.97) are informational, NOT added to the valuation
    denominator (deliberate conservatism; strike well above base case).
    """
    bridge = equity_value_bridge(
        products=products,
        valuation_year=valuation_year,
        horizon_year=horizon_year,
        discount_rate=discount_rate,
        include_sarl_residual=include_sarl_residual,
        include_central_costs=include_central_costs,
    )

    if shares_m is not None:
        shares = float(shares_m)
    else:
        # Valuation-basis diluted share count.
        shares = (
            A.SHARES_ISSUED_M
            + A.SHARES_JJ_CONVERSION_M
            + A.SHARES_WARRANTS_M
            + A.SHARES_UNVESTED_FREE_M
        )

    raw = bridge["equity_value_chf_m"] / shares
    floored = max(0.0, raw) if floor_at_zero else raw
    bridge["shares_m"] = shares
    bridge["shares_issued_m"] = A.SHARES_ISSUED_M
    bridge["value_per_share_raw_chf"] = raw
    bridge["value_per_share_chf"] = floored
    bridge["value_per_share_floored"] = (raw < 0.0 and floor_at_zero)
    bridge["market_price_chf"] = A.SHARE_PRICE_CURRENT_CHF
    bridge["market_price_as_of"] = A.SHARE_PRICE_CURRENT_AS_OF
    denom = A.SHARE_PRICE_CURRENT_CHF if A.SHARE_PRICE_CURRENT_CHF > 0 else float("nan")
    bridge["upside_pct"] = (floored / denom - 1.0) * 100.0
    bridge["ev_chf_m"] = bridge["equity_value_chf_m"]
    return bridge


# ---------------------------------------------------------------------------
# If-converted test (now used for CB 2034 only; J&J is mandatory in base)
# ---------------------------------------------------------------------------

def apply_if_converted(
    bridge: dict,
    strike_chf: float | None = None,
    converted_shares_m: float | None = None,
    principal_chf_m: float | None = None,
) -> dict:
    """CB 2034 if-converted: if V/share > strike, remove principal from debt
    and add converted_shares_m to the diluted count.

    Defaults: CHF 6.00 strike, 2.72 M shares, CHF 16.5 M principal (CB 2034).
    """
    strike = A.CB_2034_STRIKE_CHF if strike_chf is None else float(strike_chf)
    conv_shares = A.SHARES_CB_2034_IFCONVERTED_M if converted_shares_m is None else float(converted_shares_m)
    principal = A.DEBT_CB_2034_CHF_M if principal_chf_m is None else float(principal_chf_m)

    out = dict(bridge)
    out["cb2034_strike_chf"] = strike

    v_raw = bridge.get("value_per_share_raw_chf", bridge.get("value_per_share_chf", 0.0))
    triggered = v_raw > strike
    out["cb2034_converted"] = triggered
    if not triggered:
        out["value_per_share_post_conversion_chf"] = bridge.get("value_per_share_chf", 0.0)
        return out

    new_equity = bridge["equity_value_chf_m"] + principal
    new_shares = bridge["shares_m"] + conv_shares
    new_raw = new_equity / new_shares
    new_floored = max(0.0, new_raw)
    out["equity_value_post_conversion_chf_m"] = new_equity
    out["shares_post_conversion_m"] = new_shares
    out["value_per_share_post_conversion_raw_chf"] = new_raw
    out["value_per_share_post_conversion_chf"] = new_floored
    # Legacy alias used by sensitivity.scenarios()
    out["jj_converted"] = triggered
    return out


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def gap_covered_pct(scenario_v: float, base_v: float, market_v: float) -> float:
    denom = (market_v - base_v)
    if abs(denom) < 1e-9:
        return float("nan")
    return 100.0 * (scenario_v - base_v) / denom


def revenue_table(
    products: dict[str, dict] | None = None,
    valuation_year: int = 2026,
    horizon_year: int = 2050,
) -> pd.DataFrame:
    products = products if products is not None else A.PRODUCTS
    cols = {
        k: revenue_curve(p, valuation_year, horizon_year)
        for k, p in products.items()
        if p.get("include", True)
    }
    return pd.DataFrame(cols)


def valuation_summary(bridge: dict) -> pd.DataFrame:
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


# ---------------------------------------------------------------------------
# 2026 calibration (per the v1.2 prompt): line-by-line opex vs guidance.
# ---------------------------------------------------------------------------

def calibration_2026(
    products: dict[str, dict] | None = None,
) -> pd.DataFrame:
    """Three columns:
      - Model (full-year 2026, PRE H2 proration): internal consistency.
      - Actual H1 2026 x 2 (from H1_2026_ACTUALS_CHF_M, non-GAAP).
      - Guidance 2026 (press release 30 Jul 2026).

    H1 x 2 is the H1 2026 non-GAAP income statement doubled; it understates
    the full-year because Q4 selling scales with QUVIVIQ ramp, but the opex
    total (CHF 320 M) sits BELOW the full-year guidance ceiling (CHF 330 M),
    so Idorsia is on track with its guidance at H1 2026.
    """
    products = products if products is not None else A.PRODUCTS
    quviviq = products["quviviq"]

    # Model full-year 2026 (pre-H2 proration): COGS + Selling allocation from
    # QUVIVIQ 2026 sales at 2026 contribution margin.
    sales_qv = float(quviviq["historical_sales_chf_m"].get(2026, 0.0))
    cm_2026 = float(quviviq["op_margin_at_launch"])
    total_cogs_sell = sales_qv * (1.0 - cm_2026)
    # Split COGS vs Selling using H1 2026 actual ratios (19/88 vs 69/88).
    h1 = A.H1_2026_ACTUALS_CHF_M
    cogs_ratio = h1["cogs"] / max(h1["cogs"] + h1["selling"], 1e-9)
    model_cogs = total_cogs_sell * cogs_ratio
    model_selling = total_cogs_sell * (1.0 - cogs_ratio)
    model_ga = A.CENTRAL_COSTS_GA_YEAR_1_CHF_M
    model_research = A.CENTRAL_COSTS_UPSTREAM_YEAR_1_CHF_M
    # Development: sum full-year dev cost for each product
    model_dev = 0.0
    for p in products.values():
        if not p.get("include", True):
            continue
        dev = development_cost_curve(p, valuation_year=2026)
        if 2026 in dev.index:
            model_dev += float(dev[2026])
    model_total_opex = model_cogs + model_selling + model_ga + model_research + model_dev
    # Model excludes contract revenue by design.
    model_op_result = sales_qv - model_total_opex

    # H1 2026 x 2 (figures from H1 p.3/p.6/p.7).
    h1x2_cogs = h1["cogs"] * 2
    h1x2_selling = h1["selling"] * 2
    h1x2_ga = h1["general_admin"] * 2
    h1x2_research = h1["research"] * 2
    h1x2_dev = h1["development"] * 2
    h1x2_total = h1x2_cogs + h1x2_selling + h1x2_ga + h1x2_research + h1x2_dev
    h1x2_sales = h1["sales_quviviq"] * 2
    h1x2_contract = h1["contract_revenue"] * 2
    # H1 op result is reported directly; x 2 avoids re-deriving it.
    h1x2_op = h1["operating_result"] * 2

    # Guidance
    g = A.GUIDANCE_2026
    g_sales = g["sales_quviviq_chf_m"]
    g_total = g["opex_total_nongaap_chf_m"]
    g_op = -g["operating_loss_nongaap_chf_m"]  # negative

    rows = [
        ("QUVIVIQ net sales",             sales_qv,       h1x2_sales,    g_sales),
        ("Contract revenue (not modelled)", None,         h1x2_contract, None),
        ("Cost of sales",                 model_cogs,     h1x2_cogs,     None),
        ("Selling",                       model_selling,  h1x2_selling,  None),
        ("General and admin",             model_ga,       h1x2_ga,       None),
        ("Research (upstream)",           model_research, h1x2_research, None),
        ("Development",                   model_dev,      h1x2_dev,      None),
        ("Total non-GAAP opex",           model_total_opex, h1x2_total,  g_total),
        ("Non-GAAP op result",            model_op_result, h1x2_op,      g_op),
    ]
    df = pd.DataFrame(rows, columns=["Line", "Model 2026 (full year)", "Actual H1 x 2", "Guidance 2026"])
    return df
