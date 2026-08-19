"""rNPV engine for the Idorsia valuation.

Pure functions that take the assumption dicts from `assumptions.py` and
return revenue curves, per product risk adjusted NPVs, and aggregated
per share fair value. Nothing here reads from disk or writes files.

Convention: all cash figures in CHF millions, all years are integers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from . import assumptions as A


# ---------------------------------------------------------------------------
# Revenue and cash flow curves
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
        # 1) prelaunch → zero (dev costs are handled separately)
        if y < launch:
            sales[y] = 0.0
            continue

        # 2) if we have a hard historical / guidance figure, use it verbatim
        if y in historical:
            sales[y] = historical[y]
            continue

        # 3) ramp phase, linear from last anchor to peak
        if y <= peak_year:
            # Anchor = latest historical figure ≤ y (or 0 if none yet)
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

        # 4) plateau at peak until expiry
        if y <= expiry:
            sales[y] = peak
            continue

        # 5) patent cliff: -85 % in year expiry+1, then 30 % YoY decay
        years_post_cliff = y - expiry
        if years_post_cliff == 1:
            sales[y] = peak * 0.15
        else:
            sales[y] = sales[y - 1] * 0.70

    return sales.clip(lower=0.0)


def operating_cash_flow_curve(
    product: dict,
    valuation_year: int = 2026,
    horizon_year: int = 2050,
) -> pd.Series:
    """Sales × op_margin, minus J&J contingent royalty haircut on sales."""
    sales = revenue_curve(product, valuation_year, horizon_year)
    margin = product["op_margin"]
    jj = product.get("jj_royalty_haircut", 0.0)
    return sales * (margin - jj)


def development_cost_curve(
    product: dict,
    valuation_year: int = 2026,
) -> pd.Series:
    """Remaining prelaunch development spend, spread evenly across the
    years between `valuation_year` and `launch_year - 1`.

    For already marketed products this returns an empty Series.
    """
    launch = product["launch_year"]
    if launch <= valuation_year:
        return pd.Series(dtype=float)

    total_cost = A.DEV_COST_TO_FILING_CHF_M.get(product["phase"], 0.0)
    years = np.arange(valuation_year, launch)
    if len(years) == 0:
        return pd.Series(dtype=float)
    per_year = total_cost / len(years)
    return pd.Series(per_year, index=years, name=f"{product['name']} dev")


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
      - "mid_year"    → 1/(1+r)^(t - t0 + 0.5)   [textbook rNPV default]
      - "start_of_year" → 1/(1+r)^(t - t0)       [no discount on t0 CF]
      - "end_of_year" → 1/(1+r)^(t - t0 + 1)     [full year of discount on t0 CF]

    Mid year is the industry standard convention for rNPV, it assumes CF are
    received evenly through the year and applies half a year of discounting
    to the current year CF. Start of year inflates NPV by ~6 % vs mid year;
    end of year deflates it by ~6 %.
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
    pv_dev_costs: float            # Σ DevCost_t × df_t (deterministic)
    rnpv: float                    # pos × pv_operating_cf - pv_dev_costs


def product_rnpv(
    key: str,
    product: dict,
    valuation_year: int = 2026,
    horizon_year: int = 2050,
    discount_rate: float | None = None,
) -> ProductValuation:
    """Risk adjusted NPV of a single product.

    rNPV = PoS × Σ_t CF_t / (1+r)^t   -   Σ_t DevCost_t / (1+r)^t

    Dev costs are treated as deterministic (they are spent regardless of
    approval outcome), the standard rNPV convention.
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
# Aggregation → enterprise value → per share
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


def enterprise_value(
    products: dict[str, dict] | None = None,
    valuation_year: int = 2026,
    horizon_year: int = 2050,
    discount_rate: float | None = None,
    include_sarl_residual: bool = False,
) -> dict:
    """Bridge from product rNPVs to parent attributable EV.

    EV(parent) = Σ rNPV(product) + parent net cash + (SARL residual, if any)

    Parent net cash = op co+parent cash minus parent attributable debt (i.e.
    excludes the ring fenced SARL notes and the SARL new money facility).
    """
    valuations = all_product_rnpvs(products, valuation_year, horizon_year, discount_rate)
    sum_rnpv = sum(v.rnpv for v in valuations)
    net_cash = A.parent_net_cash_chf_m()
    sarl = A.SARL_RESIDUAL_VALUE_CHF_M if include_sarl_residual else 0.0
    ev = sum_rnpv + net_cash + sarl
    return {
        "products": valuations,
        "sum_rnpv_chf_m": sum_rnpv,
        "parent_net_cash_chf_m": net_cash,
        "sarl_residual_chf_m": sarl,
        "ev_chf_m": ev,
    }


def value_per_share(
    products: dict[str, dict] | None = None,
    valuation_year: int = 2026,
    horizon_year: int = 2050,
    discount_rate: float | None = None,
    shares_m: float | None = None,
    diluted: bool = False,
    include_sarl_residual: bool = False,
) -> dict:
    """Per share fair value in CHF, plus the full bridge."""
    if shares_m is None:
        shares_m = (
            A.POTENTIAL_SHARES_FULLY_DILUTED_M if diluted else A.SHARES_OUTSTANDING_M
        )
    bridge = enterprise_value(
        products=products,
        valuation_year=valuation_year,
        horizon_year=horizon_year,
        discount_rate=discount_rate,
        include_sarl_residual=include_sarl_residual,
    )
    v = bridge["ev_chf_m"] / shares_m
    bridge["shares_m"] = shares_m
    bridge["value_per_share_chf"] = v
    bridge["market_price_chf"] = A.SHARE_PRICE_CURRENT_CHF
    bridge["upside_pct"] = (v / A.SHARE_PRICE_CURRENT_CHF - 1.0) * 100.0
    return bridge


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

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
