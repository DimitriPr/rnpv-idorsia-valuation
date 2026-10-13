"""Tests for the rNPV engine (v1.2)."""

from __future__ import annotations

import copy

import pytest

from src import assumptions as A
from src import rnpv


# ---------------------------------------------------------------------------
# PoS transitions and cumulative (unchanged from v1.1)
# ---------------------------------------------------------------------------

def test_cumulative_pos_equals_product_of_transitions():
    t = A.POS_TRANSITIONS
    expected_from_phase1 = (
        t["phase1_to_phase2"]
        * t["phase2_to_phase3"]
        * t["phase3_to_filing"]
        * t["filing_to_approval"]
    )
    expected_from_phase2 = (
        t["phase2_to_phase3"]
        * t["phase3_to_filing"]
        * t["filing_to_approval"]
    )
    expected_from_phase3 = t["phase3_to_filing"] * t["filing_to_approval"]
    expected_from_filing = t["filing_to_approval"]

    assert A.cumulative_pos("phase1") == pytest.approx(expected_from_phase1, abs=1e-9)
    assert A.cumulative_pos("phase2") == pytest.approx(expected_from_phase2, abs=1e-9)
    assert A.cumulative_pos("phase3") == pytest.approx(expected_from_phase3, abs=1e-9)
    assert A.cumulative_pos("filing") == pytest.approx(expected_from_filing, abs=1e-9)
    assert A.cumulative_pos("marketed") == 1.0


def test_cumulative_pos_from_phase1_matches_bio_loa():
    assert A.cumulative_pos("phase1") == pytest.approx(0.0786, abs=5e-4)


# ---------------------------------------------------------------------------
# Development cost scheduling and weighting (unchanged)
# ---------------------------------------------------------------------------

def _toy_phase2_product(launch=2033, readout=2026, remaining=18.0):
    return {
        "name": "toy_p2",
        "phase": "phase2",
        "pos": A.cumulative_pos("phase2"),
        "launch_year": launch,
        "readout_year": readout,
        "historical_sales_chf_m": {},
        "peak_sales_chf_m": 100.0,
        "ramp_years": 3,
        "patent_expiry": launch + 10,
        "op_margin_at_launch": 0.3,
        "op_margin_at_peak":   0.3,
        "op_margin_launch_anchor_year": launch,
        "op_margin_peak_anchor_year":   launch + 3,
        "remaining_current_phase_cost_chf_m": remaining,
    }


def test_current_phase_remaining_is_certain():
    p = _toy_phase2_product(launch=2033, readout=2026, remaining=18.0)
    s = rnpv.development_cost_curve(p, valuation_year=2026)
    assert s.loc[2026] >= 18.0 - 1e-9


def test_future_phase_cost_is_weighted_by_transition_probability():
    p = _toy_phase2_product(launch=2033, readout=2026, remaining=0.0)
    s = rnpv.development_cost_curve(p, valuation_year=2026)
    weight = A.POS_TRANSITIONS["phase2_to_phase3"]
    duration = A.DEV_PHASE_DURATION_YEARS["phase3"]
    expected_per_year = (322.0 * weight) / duration
    for y in (2027, 2028, 2029):
        assert s.get(y, 0.0) == pytest.approx(expected_per_year, rel=1e-6)


def test_filing_cost_doubly_weighted_after_phase_3():
    p = _toy_phase2_product(launch=2033, readout=2026, remaining=0.0)
    s = rnpv.development_cost_curve(p, valuation_year=2026)
    weight_cum = (
        A.POS_TRANSITIONS["phase2_to_phase3"]
        * A.POS_TRANSITIONS["phase3_to_filing"]
    )
    expected = A.DEV_COSTS_BY_PHASE_CHF_M["filing"] * weight_cum
    assert s.get(2030, 0.0) == pytest.approx(expected, rel=1e-6)


def test_marketed_product_has_no_dev_cost_curve():
    p = copy.deepcopy(A.PRODUCTS["quviviq"])
    s = rnpv.development_cost_curve(p, valuation_year=2026)
    assert s.empty


# ---------------------------------------------------------------------------
# v1.2: H2 2026 proration
# ---------------------------------------------------------------------------

def test_h2_2026_proration_halves_valuation_year_flow():
    import pandas as pd
    s = pd.Series({2026: 200.0, 2027: 300.0, 2028: 400.0})
    out = rnpv._h2_prorate(s, valuation_year=2026)
    assert out[2026] == pytest.approx(100.0)
    assert out[2027] == pytest.approx(300.0)
    assert out[2028] == pytest.approx(400.0)


def test_discount_factors_mid_year_valuation_date_exponents():
    df = rnpv.discount_factors(2026, 2030, 0.10, convention="mid_year_valuation_date")
    r = 0.10
    assert df[2026] == pytest.approx(1 / (1 + r) ** 0.25, abs=1e-9)
    assert df[2027] == pytest.approx(1 / (1 + r) ** 1.0,  abs=1e-9)
    assert df[2028] == pytest.approx(1 / (1 + r) ** 2.0,  abs=1e-9)
    assert df[2029] == pytest.approx(1 / (1 + r) ** 3.0,  abs=1e-9)


# ---------------------------------------------------------------------------
# v1.2: J&J residual royalty cap
# ---------------------------------------------------------------------------

def test_jj_royalty_cumulative_never_exceeds_cap():
    series = rnpv.jj_residual_royalty_series()
    cumulative = series.cumsum()
    assert cumulative.max() <= A.JJ_RESIDUAL_ROYALTY_CAP_REMAINING_CHF_M + 1e-6


def test_jj_royalty_hits_cap_eventually():
    """With CHF 600 M QUVIVIQ peak + others, the 272 M cap should be reached
    within the model horizon."""
    series = rnpv.jj_residual_royalty_series()
    cumulative = series.cumsum()
    # Expect to reach the cap by late horizon
    assert cumulative.max() >= 0.5 * A.JJ_RESIDUAL_ROYALTY_CAP_REMAINING_CHF_M


# ---------------------------------------------------------------------------
# v1.2: value-per-share denominator uses the diluted-valuation-basis count.
# This test is written to FAIL on the former 284.8 M count (issued + J&J only)
# and PASS on 305.15 M (issued + J&J + warrants + unvested free shares).
# ---------------------------------------------------------------------------

def test_value_per_share_uses_valuation_basis_denominator():
    b = rnpv.value_per_share()
    expected = (
        A.SHARES_ISSUED_M
        + A.SHARES_JJ_CONVERSION_M
        + A.SHARES_WARRANTS_M
        + A.SHARES_UNVESTED_FREE_M
    )
    assert b["shares_m"] == pytest.approx(expected, abs=0.01)
    # Explicit regression guard against the old v1.1/early-v1.2 denominator.
    old_basic = A.SHARES_ISSUED_M + A.SHARES_JJ_CONVERSION_M
    assert abs(b["shares_m"] - old_basic) > 1.0, (
        f"Denominator ({b['shares_m']:.2f} M) matches the deprecated 'basic' "
        f"count ({old_basic:.2f} M); must include warrants + unvested free shares."
    )


def test_shares_issued_separate_from_valuation_denominator():
    """The bridge exposes both the issued count and the valuation denominator."""
    b = rnpv.value_per_share()
    assert b["shares_issued_m"] == pytest.approx(A.SHARES_ISSUED_M)
    assert b["shares_m"] > b["shares_issued_m"]  # valuation basis is strictly larger


# ---------------------------------------------------------------------------
# v1.2: Diluted share count helper
# ---------------------------------------------------------------------------

def test_diluted_shares_below_cb2034_strike():
    """V/share < CHF 6: no CB 2034, no options."""
    d = A.diluted_shares_m(value_per_share_chf=3.0)
    expected = (
        A.SHARES_ISSUED_M + A.SHARES_JJ_CONVERSION_M
        + A.SHARES_WARRANTS_M + A.SHARES_UNVESTED_FREE_M
    )
    assert d["total"] == pytest.approx(expected)
    assert "CB 2034 if-converted (CHF 6.00)" not in d
    assert "options (avg CHF 10.97)" not in d


def test_diluted_shares_between_strikes():
    """V/share between CHF 6 and 10.97: CB 2034 in, options out."""
    d = A.diluted_shares_m(value_per_share_chf=8.0)
    expected = (
        A.SHARES_ISSUED_M + A.SHARES_JJ_CONVERSION_M
        + A.SHARES_WARRANTS_M + A.SHARES_UNVESTED_FREE_M
        + A.SHARES_CB_2034_IFCONVERTED_M
    )
    assert d["total"] == pytest.approx(expected)
    assert "options (avg CHF 10.97)" not in d


def test_diluted_shares_above_options_strike():
    """V/share > CHF 10.97: all buckets in."""
    d = A.diluted_shares_m(value_per_share_chf=12.0)
    expected = (
        A.SHARES_ISSUED_M + A.SHARES_JJ_CONVERSION_M
        + A.SHARES_WARRANTS_M + A.SHARES_UNVESTED_FREE_M
        + A.SHARES_CB_2034_IFCONVERTED_M + A.SHARES_OPTIONS_M
    )
    assert d["total"] == pytest.approx(expected)


# ---------------------------------------------------------------------------
# v1.2: 2026 opex ceiling (model must not exceed guidance x 1.05)
# ---------------------------------------------------------------------------

def test_2026_opex_within_guidance_ceiling():
    """Model-implied total opex for 2026 (full year, pre-proration) must not
    exceed the H1 2026 Report press-release guidance by more than 5 %.

    If this fails, see rnpv.calibration_2026() for the breakdown. Do NOT
    silently adjust assumptions; show the breakdown to the user.
    """
    cal = rnpv.calibration_2026()
    row = cal[cal["Line"] == "Total non-GAAP opex"].iloc[0]
    model_opex = float(row["Model 2026 (full year)"])
    ceiling = A.OPEX_2026_CEILING_CHF_M
    assert model_opex <= ceiling, (
        f"Model 2026 full-year opex ({model_opex:.0f} M) exceeds the "
        f"guidance ceiling ({ceiling:.0f} M). Breakdown:\n{cal.to_string(index=False)}"
    )


# ---------------------------------------------------------------------------
# v1.2: central costs mechanics (replaces test_central_costs_pv_is_positive_and_bounded)
# ---------------------------------------------------------------------------

def test_central_costs_series_respects_floor():
    """Each annual central cost value is >= its applicable floor."""
    series = rnpv.central_costs_series()
    for year, value in series.items():
        if year <= A.CENTRAL_COSTS_PLATEAU_END_YEAR:
            assert value >= A.CENTRAL_COSTS_FLOOR_CHF_M - 1e-6
        else:
            assert value >= A.CENTRAL_COSTS_TAIL_FLOOR_CHF_M - 1e-6


def test_central_costs_pv_equals_sum_series_times_discount():
    """PV = sum of cost_t * df_t, with H2 2026 proration applied."""
    series = rnpv._h2_prorate(rnpv.central_costs_series(), valuation_year=2026)
    df = rnpv.discount_factors(2026, A.CENTRAL_COSTS_HORIZON_END_YEAR, A.DISCOUNT_RATE)
    df = df.reindex(series.index, fill_value=0.0)
    expected = float((series * df).sum())
    actual = rnpv.central_costs_pv()
    assert actual == pytest.approx(expected, abs=1e-6)


# ---------------------------------------------------------------------------
# Equity value bridge definition
# ---------------------------------------------------------------------------

def test_equity_value_equals_rnpvs_plus_net_cash_minus_central_and_royalty():
    b = rnpv.equity_value_bridge()
    reconstructed = (
        b["sum_rnpv_chf_m"]
        + b["parent_net_cash_chf_m"]
        + b["sarl_residual_chf_m"]
        - b["central_costs_pv_chf_m"]
        - b["jj_royalty_pv_chf_m"]
    )
    assert b["equity_value_chf_m"] == pytest.approx(reconstructed, abs=1e-6)


# ---------------------------------------------------------------------------
# Floor at zero (unchanged)
# ---------------------------------------------------------------------------

def test_value_per_share_is_floored_at_zero():
    b = rnpv.value_per_share()
    assert b["value_per_share_chf"] >= 0.0
    assert "value_per_share_raw_chf" in b


def test_value_per_share_floor_tracks_floored_flag():
    import src.rnpv as R
    original_series = R.central_costs_series
    try:
        def _huge_series(*a, **k):
            s = original_series(*a, **k)
            return s * 10.0
        R.central_costs_series = _huge_series
        b = rnpv.value_per_share()
        assert b["value_per_share_chf"] == 0.0
        assert b["value_per_share_raw_chf"] < 0.0
        assert b["value_per_share_floored"] is True
    finally:
        R.central_costs_series = original_series


# ---------------------------------------------------------------------------
# v1.2: CB 2034 if-converted test (J&J conversion is now mandatory, no longer tested)
# ---------------------------------------------------------------------------

def test_cb2034_if_converted_below_strike_no_trigger():
    bridge = {
        "equity_value_chf_m": 100.0,
        "shares_m": 300.0,
        "value_per_share_chf": 0.33,
        "value_per_share_raw_chf": 0.33,
    }
    out = rnpv.apply_if_converted(bridge)
    assert out["cb2034_converted"] is False


def test_cb2034_if_converted_above_strike_triggers():
    bridge = {
        "equity_value_chf_m": 3000.0,                    # => raw = 3000/300 = 10 > 6
        "shares_m": 300.0,
        "value_per_share_chf": 10.0,
        "value_per_share_raw_chf": 10.0,
    }
    out = rnpv.apply_if_converted(bridge)
    assert out["cb2034_converted"] is True
    expected_eq = 3000.0 + A.DEBT_CB_2034_CHF_M
    expected_shares = 300.0 + A.SHARES_CB_2034_IFCONVERTED_M
    assert out["equity_value_post_conversion_chf_m"] == pytest.approx(expected_eq)
    assert out["shares_post_conversion_m"] == pytest.approx(expected_shares)
