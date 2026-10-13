"""Assumptions for the Idorsia rNPV model (v1.2).

All numbers carry a `status` field (sourced / assumption / placeholder) and,
when sourced, an inline `# source:` comment pointing to a public document.
Currency: CHF millions. Convention: cash inflows positive, outflows negative.

Primary source for v1.2:
  - Idorsia, Financial Report H1 2026 (publication 30 July 2026),
    local copy at data/raw/2026-6m-idorsia-financial-report.pdf
    (abbreviated below as H1 2026 Report, with page refs e.g. "H1 p.22").

Other sources:
  - Idorsia Annual Report 2025 (published 26 Feb 2026) ("AR 2025 p.X")
  - Idorsia Investor Presentation, June 2026 ("June 2026 pres. p.X")
  - BIO/Informa/QLS, "Clinical Development Success Rates 2011-2020" (2021)
  - DiMasi, Grabowski, Hansen (2016), *J Health Econ* 47:20-33

CRITICAL STRUCTURAL NOTE, read before touching PRODUCTS:
    Idorsia Ltd (SIX: IDIA) is the listed parent. In 2025 it transferred the
    rights to aprocitentan (TRYVIO/JERAYGO), selatogrel and cenerimod to
    Idorsia Investments SARL, which secures the SARL notes due 2048/2050.
    SARL notes A1/A2 benefit from a LIMITED and SUBORDINATED guarantee from
    Idorsia Ltd (H1 p.17, p.41): "non-recourse" is therefore inaccurate.

    Cash flows from those three assets service the SARL debt first; rights
    revert to the parent only after the SARL debt + interest are fully repaid.

    The model values, for the equity holder of IDIA:
      (1) QUVIVIQ (daridorexant), held at Idorsia Pharmaceuticals Ltd
      (2) The R&D pipeline (lucerastat + early stage), same op co
      (3) A residual / option value for the SARL reversion (base case = 0)
      (4) Net cash/debt at the parent + op co (excluding SARL notes), minus
          a PV of unallocated central costs (G&A + upstream research), minus
          a PV of the J&J residual royalty cash outflow (cap CHF 272 M).
"""

from __future__ import annotations

import json
import pathlib
from typing import Literal

Status = Literal["sourced", "assumption", "placeholder"]

ROOT = pathlib.Path(__file__).resolve().parent.parent


# =============================================================================
# 1. MARKET DATA
# =============================================================================
# source: AR 2025 "Key share data" p.8 (YE 2025 snapshot kept for historical ref)
SHARE_PRICE_YE2025_CHF = 4.26
MARKET_CAP_YE2025_CHF_M = 1_070

# source: H1 2026 Report, p.12 (shares issued 30 Jun 2026, after the J&J
# tranche-conversion of 7.4 M shares on 19 Jun 2026).
SHARES_ISSUED_M = 263.1

# Diluted share count components (shown explicitly in the per-share bridge).
# All sourced from H1 2026 Report unless noted.
SHARES_JJ_CONVERSION_M = 21.7                # H1 p.38-39: remaining J&J loan converts into 21.7 M shares at CHF 11.48
SHARES_WARRANTS_M = 10.85                    # H1 p.48: 10.85 M warrants at CHF 1.49, exercise cash CHF 16.2 M
SHARES_WARRANTS_STRIKE_CHF = 1.49
SHARES_WARRANTS_CASH_IN_CHF_M = 16.2         # 10.85 M * 1.49 = CHF 16.2 M cash into the parent on exercise
SHARES_WARRANTS_EXPIRY = "2027-06-02"
SHARES_UNVESTED_FREE_M = 9.5                 # H1 p.48: unvested free shares (not yet exercisable, but counted diluted)
SHARES_CB_2034_IFCONVERTED_M = 2.72          # H1 p.39: CB 2034 conversion = 16.5 M principal / CHF 6.00 strike
CB_2034_STRIKE_CHF = 6.00
SHARES_OPTIONS_M = 7.1                       # H1 p.48: 7.1 M options, weighted-avg strike CHF 10.97
SHARES_OPTIONS_STRIKE_CHF = 10.97

# Convenience: v1.0/v1.1-era aliases kept so legacy callers (and tests that
# haven't been updated) do not break. These are now DERIVED values.
SHARES_OUTSTANDING_M = SHARES_ISSUED_M        # basic (issued), 30 Jun 2026
POTENTIAL_SHARES_FULLY_DILUTED_M = (
    SHARES_ISSUED_M
    + SHARES_JJ_CONVERSION_M
    + SHARES_WARRANTS_M
    + SHARES_UNVESTED_FREE_M
    + SHARES_CB_2034_IFCONVERTED_M
    + SHARES_OPTIONS_M
)

# Current share price: data/market.json populated by scripts/update_price.py
# (yfinance IDIA.SW latest close). Fallback placeholder keeps the model
# functional if the file is missing or stale.
_MARKET_FILE = ROOT / "data" / "market.json"


def _load_market_data() -> dict:
    if _MARKET_FILE.exists():
        try:
            with _MARKET_FILE.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "ticker": "IDIA.SW",
        "price_chf": 4.16,
        "as_of": "2026-10-13",
        "status": "placeholder",
        "source": "placeholder; run scripts/update_price.py to refresh",
    }


_MARKET_DATA = _load_market_data()
SHARE_PRICE_CURRENT_CHF: float = float(_MARKET_DATA["price_chf"])
SHARE_PRICE_CURRENT_AS_OF: str = str(_MARKET_DATA["as_of"])
SHARE_PRICE_STATUS: Status = _MARKET_DATA.get("status", "placeholder")


# =============================================================================
# 2. BALANCE SHEET at 30 June 2026
# =============================================================================
# ALL lines in this section are at 30 Jun 2026 unless otherwise noted.
# Primary source: H1 2026 Report. The v1.0/v1.1 practice of mixing YE 2025
# and Jun 2026 figures is now gone.
VALUATION_DATE = "2026-06-30"

# source: H1 p.22 (consolidated balance sheet, cash and equivalents)
CASH_30JUN2026_CHF_M = 88.7
# Backwards-compat alias (older callers):
CASH_YE2025_CHF_M = 89.0                     # YE 2025, kept for historical reporting

# ---------------------------------------------------------------------------
# J&J convertible loan (Cilag), post the 19 Jun 2026 tranche conversion.
# source: H1 Report p.38-39.
#   - Remaining nominal: CHF 250 M (down from 335 after 85 M converted).
#   - Convertible into 21.7 M IDIA shares at a strike of CHF 11.48.
#   - Matures 15 Jun 2027.
#   - At maturity Idorsia can settle in cash OR shares. The Pharmakon loan
#     covenant (p.44) FORBIDS cash repayment of a convertible loan.
#     => The remaining 250 M will be settled in shares. The convertible is
#     treated as 0 debt + a deterministic +21.7 M share issuance at CHF 11.48.
#     It is a "deferred equity issuance", not a cash outflow and not an upside.
# ---------------------------------------------------------------------------
JJ_CONVERTIBLE_PRINCIPAL_REMAINING_CHF_M = 250.0
JJ_CONVERTIBLE_STRIKE_CHF = 11.48
JJ_CONVERTIBLE_MATURITY = "2027-06-15"
# Legacy alias (apply_if_converted still exists and is reused for CB 2034)
JJ_CONVERTIBLE_PRINCIPAL_CHF_M = JJ_CONVERTIBLE_PRINCIPAL_REMAINING_CHF_M
JJ_CONVERTIBLE_SHARES_ON_CONVERSION_M = SHARES_JJ_CONVERSION_M

# ---------------------------------------------------------------------------
# Convertible bonds (CB), H1 p.39-40.
#   - CB 2034: CHF 16.5 M nominal, strike CHF 6.00 => 2.72 M shares if converted.
#   - CB 2038: CHF 32.8 M nominal, strike CHF 31.54.
#   - Treated as debt; CB 2034 if-converted test triggers when V/share > 6.00.
# ---------------------------------------------------------------------------
DEBT_CB_2034_CHF_M = 16.5
DEBT_CB_2038_CHF_M = 32.8
DEBT_CONVERTIBLE_BONDS_CHF_M = DEBT_CB_2034_CHF_M + DEBT_CB_2038_CHF_M  # 49.3 M total

# ---------------------------------------------------------------------------
# Pharmakon term loan (Idorsia Pharmaceuticals Ltd), H1 p.43-44.
#   - CHF 150 M nominal drawn 26 Jun 2026, 7 %, quarterly amortisation from
#     30 Sep 2029, final maturity 25 Jun 2031.
#   - Covenants: minimum liquidity, minimum revenue, obligation to strengthen
#     liquidity within an agreed timeframe (implies anticipated capital raise,
#     i.e. dilution not modelled).
# ---------------------------------------------------------------------------
DEBT_PHARMAKON_LOAN_CHF_M = 150.0
DEBT_PHARMAKON_RATE = 0.07
DEBT_PHARMAKON_MATURITY = "2031-06-25"

# ---------------------------------------------------------------------------
# Other financial debt (H1 p.42), decomposed:
#   - Sale-and-leaseback: CHF 162 M, parent debt
#   - R-Bridge royalty monetization: CHF 24 M, serviced by VAMOROLONE royalties
#     which are NOT in the model. EXCLUDED from the parent bridge for
#     asset/liability consistency.
# Historical total line used in v1.1 was 189 M; v1.2 keeps only the 162 M
# sale-leaseback.
# ---------------------------------------------------------------------------
DEBT_SALE_LEASEBACK_CHF_M = 162.0
DEBT_RBRIDGE_CHF_M = 24.0                    # excluded from parent bridge
DEBT_OTHER_FINANCIAL_CHF_M = DEBT_SALE_LEASEBACK_CHF_M  # for parent bridge; R-Bridge excluded

# ---------------------------------------------------------------------------
# New Money Facility (Idorsia Luxembourg SARL, NOT Investments SARL).
#   - 78 M nominal drawn at YE 2025 (H1 p.16, p.43).
#   - 113 M of principal repaid on 25 Jun 2026 using Pharmakon proceeds.
#   - Zero at 30 Jun 2026. Not in the current bridge.
# ---------------------------------------------------------------------------
DEBT_NEW_MONEY_FACILITY_YE2025_CHF_M = 78.0
DEBT_NEW_MONEY_FACILITY_REPAID_CHF_M = 113.0
DEBT_NEW_MONEY_FACILITY_CHF_M = 0.0

# ---------------------------------------------------------------------------
# SARL notes (Idorsia Investments SARL), H1 p.17, p.41.
#   - A1 121 + A2 260 + B 394 = CHF 774 M nominal at 30 Jun 2026.
#   - Interest is PIK (capitalised): +CHF 16.2 M added on 17 Jul 2026.
#   - Notes A benefit from a LIMITED and SUBORDINATED guarantee from
#     Idorsia Ltd. "Non-recourse to IDIA shareholders" is inaccurate; the
#     exact phrase used in results.qmd and methodology.qmd is updated.
# ---------------------------------------------------------------------------
DEBT_NOTES_SARL_A1_CHF_M = 121.0
DEBT_NOTES_SARL_A2_CHF_M = 260.0
DEBT_NOTES_SARL_B_CHF_M = 394.0
DEBT_NOTES_SARL_CHF_M = (
    DEBT_NOTES_SARL_A1_CHF_M + DEBT_NOTES_SARL_A2_CHF_M + DEBT_NOTES_SARL_B_CHF_M
)
# Legacy alias used by legacy callers:
DEBT_CONVERTIBLE_LOAN_JJ_CHF_M = 0.0         # J&J is now 0 debt (settled in shares at maturity)

# ---------------------------------------------------------------------------
# Debt attributable to parent equity holder.
# Excludes:
#   - J&J convertible (becomes equity issuance via the mandatory share settlement)
#   - SARL notes (serviced by SARL assets; subordinated Idorsia Ltd guarantee is
#     NOT included in the base case, flagged in Limitations)
#   - R-Bridge monetization (serviced by vamorolone royalties not in the model)
#   - New Money Facility (repaid 25 Jun 2026)
# ---------------------------------------------------------------------------
PARENT_ATTRIBUTABLE_DEBT_CHF_M = (
    DEBT_PHARMAKON_LOAN_CHF_M
    + DEBT_CONVERTIBLE_BONDS_CHF_M
    + DEBT_SALE_LEASEBACK_CHF_M
)
# SARL debt kept separate (excluded from parent equity bridge):
SARL_DEBT_CHF_M = DEBT_NOTES_SARL_CHF_M + DEBT_NEW_MONEY_FACILITY_CHF_M

# Parent-attributable cash. The SARL-only cash sub-balance is still not
# cleanly disclosed, so group cash remains an upper bound. Kept at 30 Jun 2026.
PARENT_ATTRIBUTABLE_CASH_CHF_M = CASH_30JUN2026_CHF_M + SHARES_WARRANTS_CASH_IN_CHF_M
PARENT_ATTRIBUTABLE_CASH_STATUS: Status = "placeholder"


# =============================================================================
# 3. DISCOUNT RATE
# =============================================================================
DISCOUNT_RATE = 0.12
DISCOUNT_RATE_STATUS: Status = "assumption"


# =============================================================================
# 4. PROBABILITY OF SUCCESS: TRANSITIONS (BIO/Informa/QLS 2011-2020)
# =============================================================================
# source: BIO, Informa Pharma Intelligence, QLS Advisors, "Clinical Development
# Success Rates and Contributing Factors 2011-2020", 2021.
# https://www.bio.org/clinical-development-success-rates-and-contributing-factors-2011-2020
POS_TRANSITIONS = {
    "phase1_to_phase2":   0.520,
    "phase2_to_phase3":   0.289,
    "phase3_to_filing":   0.578,
    "filing_to_approval": 0.906,
}
# Cumulative LOA (likelihood of approval) from Phase 1 = 7.9 %
# = 0.520 * 0.289 * 0.578 * 0.906 = 0.0786.

PHASE_ORDER = ["phase1", "phase2", "phase3", "filing"]


def cumulative_pos(phase: str) -> float:
    """Cumulative PoS from `phase` through to approval, product of transitions."""
    if phase == "marketed":
        return 1.0
    try:
        idx = PHASE_ORDER.index(phase)
    except ValueError:
        raise ValueError(f"Unknown phase: {phase}")
    p = 1.0
    for i in range(idx, len(PHASE_ORDER)):
        from_phase = PHASE_ORDER[i]
        to_phase = PHASE_ORDER[i + 1] if i + 1 < len(PHASE_ORDER) else "approval"
        p *= POS_TRANSITIONS[f"{from_phase}_to_{to_phase}"]
    return p


POS_CUMULATIVE_BY_PHASE = {
    "phase1":   cumulative_pos("phase1"),
    "phase2":   cumulative_pos("phase2"),
    "phase3":   cumulative_pos("phase3"),
    "filing":   cumulative_pos("filing"),
    "marketed": 1.0,
}


# =============================================================================
# 5. DEVELOPMENT COSTS BY PHASE (per compound entering phase, CHF 2026 M)
# =============================================================================
# source: DiMasi, Grabowski, Hansen (2016), *J Health Econ* 47:20-33, Table 1.
# Mean out-of-pocket cost per compound entering phase, in USD 2013:
#   Phase 1: 25.3, Phase 2: 58.6, Phase 3: 255.4 USD 2013 M.
# Conversion USD 2013 -> CHF 2026 (status: assumption):
#   * US CPI 2013 -> 2026 (projected): ~1.40x
#   * USD/CHF 2026 (mid): 0.90
#   * Combined factor: 1.26
DEV_COSTS_BY_PHASE_CHF_M = {
    "phase1":    32.0,
    "phase2":    74.0,
    "phase3":   322.0,
    "filing":    19.0,
}
DEV_COSTS_STATUS: Status = "assumption"
DEV_PHASE_DURATION_YEARS = {
    "phase1": 1,
    "phase2": 3,
    "phase3": 3,
    "filing": 1,
}


# =============================================================================
# 6. CENTRAL COSTS (unallocated G&A + upstream research), SOURCED on H1 2026
# =============================================================================
# source: H1 2026 Report p.6-7 (non-GAAP operating expense breakdown).
#   - G&A: CHF 27 M at H1 2026 => CHF 54 M / year run-rate (replaces 71 M from AR 2025).
#   - Upstream research (preclinical, biology, chemistry; p.7): CHF 17 M at H1
#     => CHF 34 M / year run-rate (replaces the CHF 25 M placeholder).
# Both are now `sourced`. Trajectory (unchanged from v1.1): decay 10 %/year
# until floor 50 M by 2040, then proportional to weighted revenue to 2050
# with hard floor 10 M.
#
# Consistency check: year-1 (2026 annualised) product dev costs + central
# costs ~ H1 2026 total non-GAAP R&D annualised; results.qmd shows the
# comparison. Overshoots indicate double-counting.
CENTRAL_COSTS_GA_YEAR_1_CHF_M = 54.0                 # sourced H1 p.6
CENTRAL_COSTS_UPSTREAM_YEAR_1_CHF_M = 34.0           # sourced H1 p.7
CENTRAL_COSTS_YEAR_1_CHF_M = (
    CENTRAL_COSTS_GA_YEAR_1_CHF_M + CENTRAL_COSTS_UPSTREAM_YEAR_1_CHF_M
)
CENTRAL_COSTS_DECAY = 0.10
CENTRAL_COSTS_FLOOR_CHF_M = 50.0
CENTRAL_COSTS_TAIL_FLOOR_CHF_M = 10.0
CENTRAL_COSTS_PLATEAU_END_YEAR = 2040
CENTRAL_COSTS_HORIZON_END_YEAR = 2050
CENTRAL_COSTS_STATUS_GA: Status = "sourced"
CENTRAL_COSTS_STATUS_UPSTREAM: Status = "sourced"


# =============================================================================
# 7. J&J RESIDUAL ROYALTY (post-SARL carve-out)
# =============================================================================
# source: H1 2026 Report Note 4, p.32.
# Janssen collects a low-to-mid single-digit royalty on NET SALES of ALL
# Idorsia products, until the cumulative royalty paid reaches a cap. Remaining
# cap at 30 Jun 2026: CHF 272 M.
#
# Modelling:
#   - rate 4 % of net sales (status: assumption; the disclosure says
#     "low-to-mid single digit")
#   - cap CHF 272 M remaining (status: sourced)
#   - applied to the AGGREGATE PoS-weighted sales stream across all products
#     in the model; stops at the cap
JJ_RESIDUAL_ROYALTY_RATE = 0.04              # assumption
JJ_RESIDUAL_ROYALTY_RATE_STATUS: Status = "assumption"
JJ_RESIDUAL_ROYALTY_CAP_REMAINING_CHF_M = 272.0
JJ_RESIDUAL_ROYALTY_CAP_STATUS: Status = "sourced"


# =============================================================================
# 8. PRODUCTS, the pipeline (contribution-margin convention)
# =============================================================================
# v1.2 semantics: `op_margin_at_launch` / `op_margin_at_peak` now represent
# the CONTRIBUTION MARGIN = (sales - COGS - Selling) / sales, NOT the EBIT
# margin. G&A and R&D are deducted ONCE elsewhere (central costs; dev costs).
#
# Convention: peak_sales_chf_m is Idorsia-recognised net sales (NOT gross
# market value).
#
# 2026 development spend calibration (see calibration_2026):
#   The sum of per-product development curves in 2026 is calibrated to the
#   2026 non-GAAP guidance decomposition (CHF 60 M dev = 330 total - 39 COGS
#   - 143 selling - 54 G&A - 34 upstream research). Lucerastat Phase 3 remains
#   anchored on the DiMasi orphan Phase 3 estimate (CHF 100 M); the three
#   Phase 2 PoC programs (CCR6, CXCR3, CXCR7) are calibrated downward from
#   DiMasi Phase 2 averages because the public disclosure (H1 p.7) attributes
#   the 2026 clinical dev to the late-stage daridorexant and lucerastat
#   programs. QUVIVIQ lifecycle R&D (pediatric 2024-2026, dosage optimisation)
#   is NOT modelled as a separate product and is implicitly covered by this
#   calibrated 2026 total.

PRODUCTS: dict[str, dict] = {
    # -------------------------------------------------------------------------
    "quviviq": {
        "name":            "QUVIVIQ (daridorexant)",
        "indication":      "chronic insomnia",
        "phase":           "marketed",
        "pos":             1.00,
        "launch_year":     2022,
        "readout_year":    2022,
        "historical_sales_chf_m": {2023: 31, 2024: 61, 2025: 134, 2026: 200},
        "peak_sales_chf_m": 600,
        "peak_sales_source": "Bracket vs Belsomra/Dayvigo comps + GlobalData 7MM DORA class forecast",
        "ramp_years":      8,
        "patent_expiry":   2036,
        # Contribution margin trajectory.
        # 2026 (anchor): H1 2026 actuals (H1 p.3, p.6) =>
        #   sales 97, COGS 19, Selling 69, contribution 9, margin ~9 %.
        #   Note: group Selling (69 M) is attributed entirely to QUVIVIQ
        #   because TRYVIO only generated CHF 0.3 M of sales at H1 2026
        #   (H1 p.53); the attribution choice is documented here.
        # 2030 (peak): 55 % contribution margin (COGS 12-20 %, Selling 25-30 %
        #   at maturity). Status: assumption.
        # Linear interpolation 2026 -> 2030; held at 55 % post-patent-cliff.
        "op_margin_at_launch": 0.09,          # sourced via H1 2026 actuals
        "op_margin_at_peak":   0.55,          # assumption
        "op_margin_launch_anchor_year": 2026,
        "op_margin_peak_anchor_year":   2030,
        "remaining_current_phase_cost_chf_m": 0.0,
        "include": True,
    },
    # -------------------------------------------------------------------------
    "lucerastat": {
        "name":            "Lucerastat",
        "indication":      "Fabry disease (oral, all mutations)",
        "phase":           "phase3",
        "pos":             cumulative_pos("phase3"),
        "launch_year":     2031,
        "readout_year":    2028,
        "historical_sales_chf_m": {},
        "peak_sales_chf_m": 400,
        "peak_sales_source": "Company-cited $4 B market + Fabrazyme/Galafold comparables",
        "ramp_years":      4,
        "patent_expiry":   2042,
        # Orphan Fabry oral: small specialty force (lower Selling %), slightly
        # higher COGS vs small molecules (API complexity).
        "op_margin_at_launch": 0.25,          # assumption
        "op_margin_at_peak":   0.65,          # assumption (orphan, small sales force)
        "op_margin_launch_anchor_year": 2031,
        "op_margin_peak_anchor_year":   2035,
        "remaining_current_phase_cost_chf_m": 100.0,
        "phase3_cost_override_chf_m": None,
        "include": True,
    },
    # -------------------------------------------------------------------------
    "ccr6_antagonist": {
        "name":            "IDOR-1117-2520 (CCR6 antagonist)",
        "indication":      "psoriasis (PoC) -> Th17 immune disorders",
        "phase":           "phase2",
        "pos":             cumulative_pos("phase2"),
        "launch_year":     2033,
        "readout_year":    2026,
        "historical_sales_chf_m": {},
        "peak_sales_chf_m": 300,
        "peak_sales_source": "PLACEHOLDER, Th17 immune disorder space, first-in-class oral; refine post PoC",
        "ramp_years":      5,
        "patent_expiry":   2046,
        "op_margin_at_launch": 0.15,          # assumption (early commercial)
        "op_margin_at_peak":   0.55,          # assumption
        "op_margin_launch_anchor_year": 2033,
        "op_margin_peak_anchor_year":   2037,
        # Phase 2 PoC/PoM trial, calibrated to 2026 guidance (H1 p.7 cites late-stage
        # daridorexant + lucerastat as the main 2026 clinical dev spend). DiMasi Phase 2
        # averages apply to full programs, not single-indication PoCs.
        "remaining_current_phase_cost_chf_m": 10.0,
        "remaining_phase_cost_status": "calibrated_to_2026_guidance",
        "include": True,
    },
    # -------------------------------------------------------------------------
    "cxcr7_antagonist": {
        "name":            "ACT-1004-1239 (CXCR7 antagonist)",
        "indication":      "progressive multiple sclerosis",
        "phase":           "phase2",
        "pos":             cumulative_pos("phase2"),
        "launch_year":     2034,
        "readout_year":    2028,
        "historical_sales_chf_m": {},
        "peak_sales_chf_m": 400,
        "peak_sales_source": "PLACEHOLDER, progressive MS, first-in-class remyelination; refine post PoC",
        "ramp_years":      6,
        "patent_expiry":   2042,
        "op_margin_at_launch": 0.15,
        "op_margin_at_peak":   0.55,
        "op_margin_launch_anchor_year": 2034,
        "op_margin_peak_anchor_year":   2038,
        # Phase 2 PoC/PoM trial calibrated to 2026 guidance (see CCR6 note above).
        "remaining_current_phase_cost_chf_m": 24.0,
        "remaining_phase_cost_status": "calibrated_to_2026_guidance",
        "include": True,
    },
    # -------------------------------------------------------------------------
    "cxcr3_antagonist": {
        "name":            "ACT-777991 (CXCR3 antagonist)",
        "indication":      "vitiligo (PoC)",
        "phase":           "phase2",
        "pos":             cumulative_pos("phase2"),
        "launch_year":     2033,
        "readout_year":    2027,
        "historical_sales_chf_m": {},
        "peak_sales_chf_m": 250,
        "peak_sales_source": "PLACEHOLDER, vitiligo (34 M diagnosed cases); refine post PoC",
        "ramp_years":      5,
        "patent_expiry":   2041,
        "op_margin_at_launch": 0.15,
        "op_margin_at_peak":   0.55,
        "op_margin_launch_anchor_year": 2033,
        "op_margin_peak_anchor_year":   2037,
        # Phase 2 PoC/PoM trial calibrated to 2026 guidance (see CCR6 note above).
        "remaining_current_phase_cost_chf_m": 18.0,
        "remaining_phase_cost_status": "calibrated_to_2026_guidance",
        "include": True,
    },
    # -------------------------------------------------------------------------
    "cdiff_vaccine": {
        "name":            "IDOR-1134-2831 (C. diff synthetic glycan vaccine)",
        "indication":      "C. difficile infection prevention",
        "phase":           "phase1",
        "pos":             cumulative_pos("phase1"),
        "launch_year":     2035,
        "readout_year":    2027,
        "historical_sales_chf_m": {},
        "peak_sales_chf_m": 200,
        "peak_sales_source": "PLACEHOLDER, assumed partnered; value to Idorsia = royalty/milestone stream",
        "ramp_years":      5,
        "patent_expiry":   2040,
        "op_margin_at_launch": 0.15,
        "op_margin_at_peak":   0.40,          # lower if partnered (royalty net)
        "op_margin_launch_anchor_year": 2035,
        "op_margin_peak_anchor_year":   2039,
        "remaining_current_phase_cost_chf_m": 10.0,
        "include": False,
    },
}


# =============================================================================
# 9. SARL reversion
# =============================================================================
SARL_RESIDUAL_VALUE_CHF_M = 0.0


# =============================================================================
# 10. 2026 ACTUALS (H1 x 2, non-GAAP) and GUIDANCE 2026 — used by the
# calibration table in results.qmd and the notebook.
# source: H1 2026 Report p.3, p.6-7; press release 30 Jul 2026 for guidance.
# =============================================================================
H1_2026_ACTUALS_CHF_M = {
    "sales_quviviq":        97.0,     # H1 p.3
    "sales_tryvio":          0.3,     # H1 p.53 (SARL; separate line)
    "contract_revenue":      8.0,     # H1 p.3 (collaboration / contract income, not modelled)
    "cogs":                 19.0,     # H1 p.3 / p.6
    "selling":              69.0,     # H1 p.6
    "general_admin":        27.0,     # H1 p.6
    "research":             17.0,     # H1 p.7 (preclinical / biology / chemistry)
    "development":          28.0,     # H1 p.7 (clinical development; late-stage daridorexant + lucerastat)
    "total_expenses":      160.0,     # H1 p.6 (= 19 + 69 + 27 + 17 + 28)
    "operating_result":    -54.0,     # H1 p.6 (non-GAAP, sourced; = revenue - 160)
}
GUIDANCE_2026 = {
    "opex_total_nongaap_chf_m":  330.0,
    "operating_loss_nongaap_chf_m": 120.0,
    "sales_quviviq_chf_m":       200.0,
    "source": "Idorsia press release, 30 July 2026",
}
# Pytest test cap (opex ceiling): 330 * 1.05 = 346.5 M
OPEX_2026_CEILING_CHF_M = GUIDANCE_2026["opex_total_nongaap_chf_m"] * 1.05


# =============================================================================
# 11. Convenience: net cash bridge for the parent equity holder
# =============================================================================
def parent_net_cash_chf_m() -> float:
    """Net cash attributable to parent equity holders (CHF M).

    Includes warrant cash-in (assumed exercised, since strike CHF 1.49 is
    well below any plausible V/share). Excludes SARL cash (not disclosed
    separately; group cash is an upper bound).
    """
    return PARENT_ATTRIBUTABLE_CASH_CHF_M - PARENT_ATTRIBUTABLE_DEBT_CHF_M


# =============================================================================
# 12. DILUTED SHARE COUNT (dynamic on V/share for options and CB 2034)
# =============================================================================
def diluted_shares_m(value_per_share_chf: float | None = None) -> dict:
    """Return the diluted share count detail (and total) given a V/share.

    V/share drives two conditional buckets:
      - CB 2034 converts if V/share > CHF 6.00 (adds 2.72 M shares).
      - Options are in-the-money if V/share > CHF 10.97 (adds 7.1 M shares).

    If V/share is None, use the current market price.
    """
    v = SHARE_PRICE_CURRENT_CHF if value_per_share_chf is None else float(value_per_share_chf)
    buckets = {
        "issued (30 Jun 2026)":     SHARES_ISSUED_M,
        "J&J loan settlement":      SHARES_JJ_CONVERSION_M,     # mandatory
        "warrants (CHF 1.49)":      SHARES_WARRANTS_M,          # always in-money
        "unvested free shares":     SHARES_UNVESTED_FREE_M,
    }
    if v > CB_2034_STRIKE_CHF:
        buckets["CB 2034 if-converted (CHF 6.00)"] = SHARES_CB_2034_IFCONVERTED_M
    if v > SHARES_OPTIONS_STRIKE_CHF:
        buckets["options (avg CHF 10.97)"] = SHARES_OPTIONS_M
    buckets["total"] = sum(buckets.values())
    return buckets


# =============================================================================
# 13. Programmatic display of key assumptions (used by results.qmd)
# =============================================================================
def key_assumptions() -> list[dict]:
    """Return the key inputs that dominate the valuation."""
    quviviq = PRODUCTS["quviviq"]
    lucerastat = PRODUCTS["lucerastat"]
    return [
        {
            "input": "Valuation date",
            "value": VALUATION_DATE,
            "status": "sourced",
            "source": "H1 2026 Report (30 Jun 2026 balance sheet)",
        },
        {
            "input": "Discount rate (mid-year, from 30 Jun 2026)",
            "value": f"{DISCOUNT_RATE:.0%}",
            "status": DISCOUNT_RATE_STATUS,
            "source": "Biotech WACC 11-13 %",
        },
        {
            "input": "PoS transitions set",
            "value": "BIO 2011-2020",
            "status": "sourced",
            "source": "BIO/Informa/QLS 2021",
        },
        {
            "input": "QUVIVIQ peak sales",
            "value": f"CHF {quviviq['peak_sales_chf_m']:.0f} M",
            "status": "assumption",
            "source": "Belsomra/Dayvigo comps + GlobalData 7MM DORA",
        },
        {
            "input": "QUVIVIQ contribution margin at launch (2026)",
            "value": f"{quviviq['op_margin_at_launch']:.0%}",
            "status": "sourced",
            "source": "H1 2026 Report p.3, p.6 (97-19-69)/97",
        },
        {
            "input": "QUVIVIQ contribution margin at peak (2030)",
            "value": f"{quviviq['op_margin_at_peak']:.0%}",
            "status": "assumption",
            "source": "COGS 12-20 % + Selling 25-30 % at maturity",
        },
        {
            "input": "Lucerastat peak sales",
            "value": f"CHF {lucerastat['peak_sales_chf_m']:.0f} M",
            "status": "assumption",
            "source": "Fabrazyme/Galafold comparables",
        },
        {
            "input": "Lucerastat Phase 3 remaining cost",
            "value": f"CHF {lucerastat['remaining_current_phase_cost_chf_m']:.0f} M",
            "status": "assumption",
            "source": "Orphan Fabry registrational trial estimate",
        },
        {
            "input": "Group cash (30 Jun 2026, upper bound)",
            "value": f"CHF {CASH_30JUN2026_CHF_M:.1f} M",
            "status": "sourced",
            "source": "H1 2026 Report p.22",
        },
        {
            "input": "Pharmakon term loan",
            "value": f"CHF {DEBT_PHARMAKON_LOAN_CHF_M:.0f} M, 7 %, mat. 25 Jun 2031",
            "status": "sourced",
            "source": "H1 2026 Report p.43-44",
        },
        {
            "input": "Convertible bonds (CB 2034 + CB 2038)",
            "value": f"CHF {DEBT_CONVERTIBLE_BONDS_CHF_M:.1f} M",
            "status": "sourced",
            "source": "H1 2026 Report p.39-40",
        },
        {
            "input": "Sale-and-leaseback debt",
            "value": f"CHF {DEBT_SALE_LEASEBACK_CHF_M:.0f} M",
            "status": "sourced",
            "source": "H1 2026 Report p.42",
        },
        {
            "input": "J&J convertible loan (settlement in shares, no debt)",
            "value": f"CHF {JJ_CONVERTIBLE_PRINCIPAL_REMAINING_CHF_M:.0f} M -> {SHARES_JJ_CONVERSION_M:.1f} M shares @ CHF {JJ_CONVERTIBLE_STRIKE_CHF:.2f}",
            "status": "sourced",
            "source": "H1 2026 Report p.38-39, 44 (Pharmakon covenant forbids cash repayment)",
        },
        {
            "input": "J&J residual royalty (all products)",
            "value": f"{JJ_RESIDUAL_ROYALTY_RATE:.0%} of net sales, cap CHF {JJ_RESIDUAL_ROYALTY_CAP_REMAINING_CHF_M:.0f} M remaining",
            "status": f"rate {JJ_RESIDUAL_ROYALTY_RATE_STATUS} / cap {JJ_RESIDUAL_ROYALTY_CAP_STATUS}",
            "source": "H1 2026 Report note 4, p.32",
        },
        {
            "input": "Central costs: G&A year 1",
            "value": f"CHF {CENTRAL_COSTS_GA_YEAR_1_CHF_M:.0f} M/year",
            "status": CENTRAL_COSTS_STATUS_GA,
            "source": "H1 2026 Report p.6 (H1 CHF 27 M x 2)",
        },
        {
            "input": "Central costs: upstream research year 1",
            "value": f"CHF {CENTRAL_COSTS_UPSTREAM_YEAR_1_CHF_M:.0f} M/year",
            "status": CENTRAL_COSTS_STATUS_UPSTREAM,
            "source": "H1 2026 Report p.7 (H1 CHF 17 M x 2, preclinical/biology/chemistry)",
        },
        {
            "input": "Shares issued (30 Jun 2026)",
            "value": f"{SHARES_ISSUED_M:.1f} M",
            "status": "sourced",
            "source": "H1 2026 Report p.12",
        },
        {
            "input": "Current share price",
            "value": f"CHF {SHARE_PRICE_CURRENT_CHF:.2f} ({SHARE_PRICE_CURRENT_AS_OF})",
            "status": SHARE_PRICE_STATUS,
            "source": "yfinance IDIA.SW via scripts/update_price.py",
        },
    ]
