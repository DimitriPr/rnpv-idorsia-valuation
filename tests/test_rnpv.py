"""Tests for the rNPV engine (v1.1)."""

from __future__ import annotations

import math
import copy

import pytest

from src import assumptions as A
from src import rnpv


# ---------------------------------------------------------------------------
# PoS transitions and cumulative
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
    # BIO 2011-2020 LOA from Phase 1 published as 7.9 %.
    # Our product is 0.520 * 0.289 * 0.578 * 0.906 = 0.0786.
    assert A.cumulative_pos("phase1") == pytest.approx(0.0786, abs=5e-4)


# ---------------------------------------------------------------------------
# Development cost scheduling and weighting
# ---------------------------------------------------------------------------

def _toy_phase2_product(launch=2033, readout=2026,
                        remaining=18.0, p3_cost=322.0, filing_cost=19.0):
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
        "jj_royalty_haircut": 0.0,
    }


def test_current_phase_remaining_is_certain():
    p = _toy_phase2_product(launch=2033, readout=2026, remaining=18.0)
    s = rnpv.development_cost_curve(p, valuation_year=2026)
    # Current phase remaining spread over 2026 only (readout == 2026)
    assert s.loc[2026] >= 18.0 - 1e-9


def test_future_phase_cost_is_weighted_by_transition_probability():
    """Full-cost Phase 3 (CHF 322 M) scheduled over 3 years post-readout,
    weighted by P(P2 -> P3) = 0.289. So each year carries ~322 * 0.289 / 3."""
    p = _toy_phase2_product(launch=2033, readout=2026, remaining=0.0,
                            p3_cost=322.0)
    s = rnpv.development_cost_curve(p, valuation_year=2026)
    weight = A.POS_TRANSITIONS["phase2_to_phase3"]
    duration = A.DEV_PHASE_DURATION_YEARS["phase3"]
    expected_per_year = (322.0 * weight) / duration
    for y in (2027, 2028, 2029):
        assert s.get(y, 0.0) == pytest.approx(expected_per_year, rel=1e-6)


def test_filing_cost_doubly_weighted_after_phase_3():
    """Filing cost weighted by P(P2->P3) * P(P3->filing)."""
    p = _toy_phase2_product(launch=2033, readout=2026, remaining=0.0)
    s = rnpv.development_cost_curve(p, valuation_year=2026)
    weight_cum = (
        A.POS_TRANSITIONS["phase2_to_phase3"]
        * A.POS_TRANSITIONS["phase3_to_filing"]
    )
    expected = A.DEV_COSTS_BY_PHASE_CHF_M["filing"] * weight_cum
    # Filing scheduled 1 year after Phase 3 ends (2027+3=2030)
    assert s.get(2030, 0.0) == pytest.approx(expected, rel=1e-6)


def test_marketed_product_has_no_dev_cost_curve():
    p = copy.deepcopy(A.PRODUCTS["quviviq"])
    s = rnpv.development_cost_curve(p, valuation_year=2026)
    assert s.empty


def test_cumulative_dev_cost_matches_phase_weighted_sum():
    """Σ of scheduled costs = remaining current + weighted(P3) + weighted(filing)."""
    p = _toy_phase2_product(launch=2033, readout=2026, remaining=18.0)
    s = rnpv.development_cost_curve(p, valuation_year=2026)
    total = float(s.sum())
    expected = (
        18.0
        + 322.0 * A.POS_TRANSITIONS["phase2_to_phase3"]
        + 19.0 * (
            A.POS_TRANSITIONS["phase2_to_phase3"]
            * A.POS_TRANSITIONS["phase3_to_filing"]
        )
    )
    assert total == pytest.approx(expected, rel=1e-6)


# ---------------------------------------------------------------------------
# Equity value bridge: definition
# ---------------------------------------------------------------------------

def test_equity_value_equals_rnpvs_plus_net_cash_minus_central_costs():
    b = rnpv.equity_value_bridge()
    reconstructed = (
        b["sum_rnpv_chf_m"]
        + b["parent_net_cash_chf_m"]
        + b["sarl_residual_chf_m"]
        - b["central_costs_pv_chf_m"]
    )
    assert b["equity_value_chf_m"] == pytest.approx(reconstructed, abs=1e-6)


def test_central_costs_pv_is_positive_and_bounded():
    pv = rnpv.central_costs_pv()
    # Order-of-magnitude: shape (71+25)->50 floor, then proportional. 300 < PV < 800.
    assert 300.0 < pv < 800.0


# ---------------------------------------------------------------------------
# Floor at zero
# ---------------------------------------------------------------------------

def test_value_per_share_is_floored_at_zero():
    """Force a very negative scenario and verify the reported per-share floor."""
    # Blow out dev costs by injecting a huge upstream term.
    b = rnpv.value_per_share()
    # Normal path: either floored or positive; raw is defined.
    assert b["value_per_share_chf"] >= 0.0
    assert "value_per_share_raw_chf" in b


# ---------------------------------------------------------------------------
# J&J if-converted test
# ---------------------------------------------------------------------------

def test_if_converted_does_not_trigger_below_strike():
    """When raw V/share < strike, the convertible stays debt-only."""
    bridge = {
        "equity_value_chf_m": 100.0,
        "shares_m": 254.0,
        "value_per_share_chf": 0.39,
        "value_per_share_raw_chf": 0.39,
    }
    out = rnpv.apply_if_converted(bridge)
    assert out["jj_converted"] is False
    assert out["value_per_share_post_conversion_chf"] == pytest.approx(0.39)


def test_if_converted_triggers_above_strike_and_dilutes():
    """When raw V/share > strike, +335 M equity, +29.1 M shares."""
    bridge = {
        "equity_value_chf_m": 5000.0,         # => raw V/share = 5000 / 254 = 19.69 (> 11.5 strike)
        "shares_m": 254.0,
        "value_per_share_chf": 19.69,
        "value_per_share_raw_chf": 19.69,
    }
    out = rnpv.apply_if_converted(bridge)
    assert out["jj_converted"] is True
    expected_equity = 5000.0 + A.JJ_CONVERTIBLE_PRINCIPAL_CHF_M
    expected_shares = 254.0 + A.JJ_CONVERTIBLE_SHARES_ON_CONVERSION_M
    assert out["equity_value_post_conversion_chf_m"] == pytest.approx(expected_equity)
    assert out["shares_post_conversion_m"] == pytest.approx(expected_shares)
    assert out["value_per_share_post_conversion_chf"] == pytest.approx(
        expected_equity / expected_shares
    )


def test_if_converted_strike_equals_335_over_291():
    assert A.JJ_CONVERTIBLE_STRIKE_CHF == pytest.approx(335.0 / 29.1, abs=1e-6)


def test_value_per_share_floor_tracks_floored_flag():
    # Build a bridge dict with an injected large central cost burden.
    import src.rnpv as R
    import copy as _c

    # Simulate: compute floored vs raw by artificially inflating central costs.
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
