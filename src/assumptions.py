"""Assumptions for the Idorsia rNPV model.

All numbers are tagged with a `status` field (sourced / assumption / placeholder) and,
when sourced, with an inline `# source:` comment pointing to the public document.
Currency: CHF millions. Convention: cash inflows positive, outflows negative.

Sources:
  - Idorsia Annual Report 2025 (published Feb 26, 2026)
  - Idorsia Investor Company Presentation, June 2026
  - Idorsia Q1 2026 Financial Report (May 2026)
  - BIO/Informa/QLS, "Clinical Development Success Rates 2011-2020" (2021)
  - DiMasi, Grabowski, Hansen (2016), *J Health Econ* 47:20-33

Local copies of the two Idorsia PDFs live in data/raw/.

CRITICAL STRUCTURAL NOTE, read before touching PRODUCTS:
    Idorsia Ltd (SIX: IDIA) is the listed parent. In 2025 it transferred the
    rights to aprocitentan (TRYVIO/JERAYGO), selatogrel and cenerimod to
    Idorsia Investments SARL, a ring-fenced subsidiary that secures the SARL
    notes due 2048/2050. Cash flows from those three assets service the SARL
    debt first; rights revert to the parent only after the debt+interest are
    fully repaid.

    The model therefore values, for the equity holder of IDIA:
      (1) QUVIVIQ (daridorexant), held at Idorsia Pharmaceuticals Ltd
      (2) The R&D pipeline (lucerastat + early stage), same op co
      (3) A residual / option value for the SARL reversion, set to 0 in
          the base case (documented as upside)
      (4) Net cash/debt at the parent + op co (excluding SARL debt, which
          is non-recourse to IDIA equity holders in expectation), minus a
          present value of unallocated central costs (G&A + upstream research)
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
# source: Idorsia AR 2025, "Key share data" table, p.8
SHARE_PRICE_YE2025_CHF = 4.26
MARKET_CAP_YE2025_CHF_M = 1_070

# source: Idorsia Q1 2026 Financial Report, "Share count" (31 March 2026)
# https://www.idorsia.com/dam/jcr:2d9c0e6a-f46c-4817-a501-ee652f7cb17f/2026-3m-idorsia-financial-report.pdf
SHARES_OUTSTANDING_M = 254.0                   # basic, issued common (Q1 2026, 31 Mar 2026)
POTENTIAL_SHARES_FULLY_DILUTED_M = 317.1       # incl. J&J convertible (29.1 M) + equity instruments

# Current share price: pulled from data/market.json by scripts/update_price.py
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
        "price_chf": 4.35,
        "as_of": "2026-06-17",
        "status": "placeholder",
        "source": "mid-June 2026 placeholder; run scripts/update_price.py to refresh",
    }


_MARKET_DATA = _load_market_data()
SHARE_PRICE_CURRENT_CHF: float = float(_MARKET_DATA["price_chf"])
SHARE_PRICE_CURRENT_AS_OF: str = str(_MARKET_DATA["as_of"])
SHARE_PRICE_STATUS: Status = _MARKET_DATA.get("status", "placeholder")


# =============================================================================
# 2. BALANCE SHEET
# =============================================================================
# Target valuation date: 30 June 2026. As of the model build date the
# full H1 2026 release had not been published; group cash and most debt
# lines are still at YE 2025 book value, with the exception of items we
# have explicit disclosure for (Pharmakon loan, Q1 2026 share count,
# Pharmakon-driven New Money Facility payoff). Missing H1 2026 items are
# listed in TODO_DATA.md.
VALUATION_DATE = "2026-06-30"

# source: Idorsia AR 2025, "Liquidity" table, p.145
CASH_YE2025_CHF_M = 89.0                        # group consolidated cash & equivalents, YE 2025 (upper bound at 30 Jun 2026)

# source: Idorsia AR 2025, "Indebtedness" table, p.145 (nominal amounts)
DEBT_CONVERTIBLE_LOAN_JJ_CHF_M = 335.0          # J&J convertible loan, matures 15 Jun 2027, zero coupon
DEBT_NOTES_SARL_CHF_M = 762.0                   # ring-fenced SARL notes, due 2048/2050, NON-RECOURSE to parent
DEBT_CONVERTIBLE_BONDS_CHF_M = 49.0             # convertible bonds, mature 2034/2038
DEBT_OTHER_FINANCIAL_CHF_M = 189.0              # incl. IFRS 16 leases, R-Bridge royalty monetization (CHF 27 M)

# source: Idorsia media release 9 Jun 2026 and closing announcement 26 Jun 2026
# https://idorsia.com/media/news/news-archive/media-release-details?id=3703084
# Pharmakon senior secured term loan: up to CHF 250 M, 5 years, fixed 7 %.
# First tranche of CHF 150 M drawn at closing (26 Jun 2026) and used to repay
# in full the New Money Facility (CHF 105 M drawn). Borrower: Idorsia
# Pharmaceuticals Ltd (op co, parent-attributable, NOT SARL).
# https://goodwinlaw.com/en/news-and-events/news/2026/06/announcements-otherindustries-ip-goodwin-advises-pharmakon-advisors
DEBT_PHARMAKON_LOAN_CHF_M = 150.0               # tranche 1 drawn 26 Jun 2026 (parent-attributable)
DEBT_PHARMAKON_RATE = 0.07
DEBT_PHARMAKON_MATURITY = "2031-06-26"

# The SARL New Money Facility (CHF 150 M nominal, CHF 105 M drawn) was repaid
# in full on 26 Jun 2026 with Pharmakon proceeds. Zero drawn at the H1 2026
# valuation date.
DEBT_NEW_MONEY_FACILITY_CHF_M = 0.0

# Debt attributable to parent equity holder (excludes ring-fenced SARL notes,
# which are serviced by SARL assets):
PARENT_ATTRIBUTABLE_DEBT_CHF_M = (
    DEBT_CONVERTIBLE_LOAN_JJ_CHF_M
    + DEBT_CONVERTIBLE_BONDS_CHF_M
    + DEBT_OTHER_FINANCIAL_CHF_M
    + DEBT_PHARMAKON_LOAN_CHF_M
)
# SARL debt (excluded from parent equity bridge in base case):
SARL_DEBT_CHF_M = DEBT_NOTES_SARL_CHF_M + DEBT_NEW_MONEY_FACILITY_CHF_M

# Parent-attributable cash: Lot 3 removes the v1.0 arbitrary CHF 89 − 20
# split. The SARL-only cash sub-balance has never been disclosed, so we use
# group cash as an UPPER BOUND and flag the overestimate in TODO_DATA.md.
# Pending H1 2026 release, this will be re-anchored on the 30 Jun 2026
# balance sheet (which should also reflect the +150 Pharmakon drawdown
# minus the −105 New Money Facility repayment, net +45 at op co).
PARENT_ATTRIBUTABLE_CASH_CHF_M = CASH_YE2025_CHF_M  # upper bound, see TODO_DATA.md
PARENT_ATTRIBUTABLE_CASH_STATUS: Status = "placeholder"


# =============================================================================
# 3. DISCOUNT RATE
# =============================================================================
# source: standard biotech WACC range 11-13 % (methodology.qmd cites the range).
# Base case: 12 %. Sensitivity: 10 % / 14 %.
DISCOUNT_RATE = 0.12
DISCOUNT_RATE_STATUS: Status = "assumption"


# =============================================================================
# 4. PROBABILITY OF SUCCESS: TRANSITIONS (BIO/Informa/QLS 2011-2020)
# =============================================================================
# source: BIO, Informa Pharma Intelligence, QLS Advisors, "Clinical Development
# Success Rates and Contributing Factors 2011-2020", 2021.
# https://www.bio.org/clinical-development-success-rates-and-contributing-factors-2011-2020
# Values are the ALL-INDICATION phase-to-phase transition probabilities.
# These REPLACE the Wong, Siah & Lo (2019) values used in v1.0, which had
# incoherence: v1.0 mixed the 90.6 % NDA/BLA->approval figure from BIO/Informa
# with the 58.1 % Phase III->approval figure from Biomedtracker (2006-2015);
# WSL (2019) also published a corrigendum on columns Phase 2->3 and Phase 3->
# approval of its Table 1 (https://pmc.ncbi.nlm.nih.gov/articles/PMC6409416/).
POS_TRANSITIONS = {
    "phase1_to_phase2":   0.520,
    "phase2_to_phase3":   0.289,
    "phase3_to_filing":   0.578,
    "filing_to_approval": 0.906,
}
# Cumulative LOA (likelihood of approval) from Phase 1 = 7.9 % per the BIO
# report (same source), consistent with 0.520 * 0.289 * 0.578 * 0.906 = 0.0786.

PHASE_ORDER = ["phase1", "phase2", "phase3", "filing"]


def cumulative_pos(phase: str) -> float:
    """Cumulative PoS from `phase` through to approval, product of transitions.

    'marketed' -> 1.0 (already approved).
    """
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


# Convenience: cumulative PoS per phase, used e.g. for display in methodology.qmd
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
# Mean out-of-pocket cost per investigational compound entering phase, in USD 2013:
#   Phase 1:  25.3 USD 2013 M
#   Phase 2:  58.6 USD 2013 M
#   Phase 3: 255.4 USD 2013 M
# DiMasi does not break out approval/filing separately; we use USD 15 M as an
# industry rule of thumb (regulatory + launch prep).
#
# Conversion USD 2013 -> CHF 2026 (status: assumption, inflation + FX):
#   * US CPI inflation 2013 -> 2026 (projected): ~1.40x
#       (CPI 2013 = 232.957; 2026 est. = 325, ~2.5 % avg annual CPI 2013-2026)
#   * USD/CHF 2026 (midpoint): 0.90 (CHF trading ~0.90 USD mid-2026)
#   * Combined factor: 1.40 * 0.90 = 1.26
# These are benchmarks; actual Idorsia-scale burn is lower (see per-product
# remaining_current_phase_cost_chf_m, which uses Idorsia's historical burn).
DEV_COSTS_BY_PHASE_CHF_M = {
    "phase1":    32.0,     # 25.3 * 1.26 ≈ 31.9
    "phase2":    74.0,     # 58.6 * 1.26 ≈ 73.8
    "phase3":   322.0,     # 255.4 * 1.26 ≈ 321.8
    "filing":    19.0,     # 15.0 * 1.26 ≈ 18.9
}
DEV_COSTS_STATUS: Status = "assumption"
# Industry default durations by phase (years). Used to schedule weighted spend
# across years (status: assumption, rounded order-of-magnitude).
DEV_PHASE_DURATION_YEARS = {
    "phase1": 1,
    "phase2": 3,
    "phase3": 3,
    "filing": 1,
}


# =============================================================================
# 6. CENTRAL COSTS (unallocated G&A + upstream research)
# =============================================================================
# These are costs NOT captured in product-level `op_margin` and NOT captured in
# per-product dev costs:
#   - G&A (holding, corporate, finance): sourced from AR 2025 non-GAAP SG&A
#     breakdown (CHF 71 M general and administrative in 2025, vs CHF 144 M
#     commercial activities already loaded into product op_margin).
#   - Upstream research: placeholder for the portion of Idorsia's R&D spend
#     NOT attributable to the specific pipeline programs modelled in PRODUCTS.
#     The 2025 non-GAAP R&D line is CHF 92 M total; the bulk is clinical trial
#     spend on the modelled programs (captured via dev_cost_curve). We assume
#     ~27 % of total R&D is non-program-specific preclinical / platform work.
# Decay 10 %/year from year 1 to a floor of CHF 50 M by year ~8, then plateau
# at that floor to 2040, then scale with the model's weighted revenue series
# with a hard floor at CHF 10 M (a listed company retains minimal G&A even if
# business winds down). Horizon aligned on product cash flow horizon (2050).
#
# Consistency check: year-1 central costs + sum of year-1 product dev costs
# must be close to the AR 2025 R&D (CHF 92 M non-GAAP) + G&A (CHF 71 M), total
# CHF 163 M. Overshoots indicate double-counting.
#
# QUVIVIQ post-launch R&D (pediatric study, label extensions) is NOT currently
# modelled either here or in dev_cost_curve. See Limitations in results.qmd.
CENTRAL_COSTS_GA_YEAR_1_CHF_M = 71.0                 # sourced AR 2025 non-GAAP SG&A: General and administrative
CENTRAL_COSTS_UPSTREAM_YEAR_1_CHF_M = 25.0           # placeholder, see TODO_DATA.md
CENTRAL_COSTS_YEAR_1_CHF_M = (
    CENTRAL_COSTS_GA_YEAR_1_CHF_M + CENTRAL_COSTS_UPSTREAM_YEAR_1_CHF_M
)
CENTRAL_COSTS_DECAY = 0.10                           # 10 %/year decline until floor
CENTRAL_COSTS_FLOOR_CHF_M = 50.0                     # floor during 2026-2040 (plateau)
CENTRAL_COSTS_TAIL_FLOOR_CHF_M = 10.0                # hard floor during 2041-2050 (proportional phase)
CENTRAL_COSTS_PLATEAU_END_YEAR = 2040                # before this: fixed decay to 50; after: scale with revenue
CENTRAL_COSTS_HORIZON_END_YEAR = 2050                # aligned on product horizon
CENTRAL_COSTS_STATUS_GA: Status = "sourced"
CENTRAL_COSTS_STATUS_UPSTREAM: Status = "placeholder"


# =============================================================================
# 7. J&J CONVERTIBLE LOAN (for if-converted test)
# =============================================================================
# source: Idorsia media release 9 Jun 2026
# https://www.idorsia.com/media/news/news-archive/media-release-details?id=2619944
# CHF 335 M, zero coupon, matures 15 Jun 2027. Convertible into 29.1 M IDIA
# shares at a strike of approximately CHF 11.5 / share (CHF 335 M / 29.1 M).
#
# The conversion option is held by J&J. From the IDIA equity-holder's view
# this is strictly a cost: either (a) J&J converts (and we take 29.1 M of
# dilution if V/share > strike at maturity) or (b) J&J does not convert
# (and Idorsia must repay CHF 335 M in cash on 15 Jun 2027, a refinancing
# event). It is NEVER an upside. The if-converted test applies in scenarios
# where V/share exceeds the strike.
JJ_CONVERTIBLE_PRINCIPAL_CHF_M = 335.0
JJ_CONVERTIBLE_SHARES_ON_CONVERSION_M = 29.1
JJ_CONVERTIBLE_STRIKE_CHF = JJ_CONVERTIBLE_PRINCIPAL_CHF_M / JJ_CONVERTIBLE_SHARES_ON_CONVERSION_M  # ~CHF 11.51
JJ_CONVERTIBLE_MATURITY = "2027-06-15"


# =============================================================================
# 8. PRODUCTS, the pipeline
# =============================================================================
# Each entry documents: phase, PoS override (if not the BIO 2021 cumulative),
# launch year, readout_year (when the current-phase result gates next-phase
# spending), peak sales (CHF M), ramp years, patent expiry, operating margin
# at launch and at peak, remaining_current_phase_cost_chf_m (Idorsia-scale
# burn through readout, certain), optional per-phase cost overrides, and the
# sources for each choice. Set `include=False` to exclude from base case.
#
# Convention: peak_sales_chf_m is Idorsia-recognized net sales (NOT gross
# market value). For partnered / royalty-only assets, this must be the royalty
# stream.

PRODUCTS: dict[str, dict] = {
    # -------------------------------------------------------------------------
    "quviviq": {
        "name":            "QUVIVIQ (daridorexant)",
        "indication":      "chronic insomnia",
        "phase":           "marketed",
        "pos":             1.00,                            # source: approved FDA Jan 2022, EMA Apr 2022
        "launch_year":     2022,
        "readout_year":    2022,                            # already marketed
        # Historical Idorsia-recognized net sales, CHF M:
        #   2023: 31 / 2024: 61 (+97 %) / 2025: 134 (+120 %) / 2026 guidance: 200 (+49 %)
        # source: 2025 results release and June 2026 investor presentation p.4
        # https://www.biospace.com/press-releases/idorsia-reports-strong-2025-results-with-quviviq-sales-more-than-doubling-further-sales-growth-ahead-with-multiple-pipeline-catalysts-in-2026
        "historical_sales_chf_m": {2023: 31, 2024: 61, 2025: 134, 2026: 200},
        "peak_sales_chf_m": 600,
        # Rationale for CHF 600 M peak:
        #   - Belsomra plateaued at ~USD 300 M globally (Pharmaphorum, 2020).
        #   - GlobalData/ClinicalTrialsArena project DORA class in 7MM to reach
        #     USD 4.1 bn by 2032 (multiple DORAs sharing).
        #   - QUVIVIQ carries best-in-class positioning (daytime functioning
        #     benefit). DEA proposed 11 Aug 2026 to reclassify DORAs from
        #     Schedule IV to Schedule V (not full descheduling); see:
        #     https://www.marktpuls.ch/artikel/permalink/675639
        #   - 2026 guidance CHF 200 M; growth 2024->2025->2026: +120 %, +49 %.
        # CHF 600 M peak is a mid-range blockbuster trajectory (blockbuster
        # threshold = USD 1 bn global; CHF 600 M Idorsia-recognized ~ USD 700 M).
        "peak_sales_source": "Bottom-up bracket vs Belsomra/Dayvigo comps and GlobalData 7MM DORA forecast",
        "ramp_years":      8,                               # 2022 launch -> peak ~2030
        "patent_expiry":   2036,                            # US binding; EU 2037
        # Operating margin trajectory: 5 % in 2026 (first year of commercial
        # profitability per Idorsia's 2026 target) ramping linearly to 30 %
        # at peak (2030). source for 5 % 2026 anchor: Idorsia June 2026
        # investor presentation p.45 ("commercial profitability targeted in 2026").
        "op_margin_at_launch": 0.05,
        "op_margin_at_peak":   0.30,
        "op_margin_launch_anchor_year": 2026,               # year when op_margin_at_launch applies
        "op_margin_peak_anchor_year":   2030,
        # J&J contingent liability: 3-5% of net sales + 10% contract revenue,
        # up to CHF 277 m combined with SARL. Approximate as -4 % on peak sales.
        # source: June 2026 presentation p.46 footnote.
        "jj_royalty_haircut": 0.04,
        "remaining_current_phase_cost_chf_m": 0.0,
        "include": True,
    },
    # -------------------------------------------------------------------------
    "lucerastat": {
        "name":            "Lucerastat",
        "indication":      "Fabry disease (oral, all mutations)",
        "phase":           "phase3",
        "pos":             cumulative_pos("phase3"),         # 0.5237 (BIO 2021)
        "launch_year":     2031,
        "readout_year":    2028,                             # P3 primary endpoint ~2028, filing 2029
        "historical_sales_chf_m": {},
        "peak_sales_chf_m": 400,
        "peak_sales_source": "Company-cited $4 B market + Fabrazyme/Galafold comparables",
        "ramp_years":      4,
        "patent_expiry":   2042,
        "op_margin_at_launch": 0.35,
        "op_margin_at_peak":   0.35,
        "op_margin_launch_anchor_year": 2031,
        "op_margin_peak_anchor_year":   2035,
        "jj_royalty_haircut": 0.0,
        # Phase 3 registrational study launched Q3 2026; cost through readout
        # is CERTAIN. Orphan Fabry registrational trials run smaller than
        # DiMasi avg (~USD 255 M); Idorsia-scale estimate CHF 100 M remaining
        # Phase 3 + support. status: assumption, listed in TODO_DATA.md.
        "remaining_current_phase_cost_chf_m": 100.0,
        "phase3_cost_override_chf_m": None,                  # already current phase; no "future P3"
        "include": True,
    },
    # -------------------------------------------------------------------------
    "ccr6_antagonist": {
        "name":            "IDOR-1117-2520 (CCR6 antagonist)",
        "indication":      "psoriasis (PoC) -> Th17 immune disorders",
        "phase":           "phase2",
        "pos":             cumulative_pos("phase2"),         # 0.1513 (BIO 2021)
        "launch_year":     2033,                             # PoC 2026 -> Ph3 -> filing ~2031 -> launch 2033
        "readout_year":    2026,                             # Phase 2 PoC readout Q4 2026 (June 2026 pres. p.29)
        "historical_sales_chf_m": {},
        "peak_sales_chf_m": 300,
        "peak_sales_source": "PLACEHOLDER, Th17 immune disorder space, first-in-class oral; refine post PoC",
        "ramp_years":      5,
        "patent_expiry":   2046,                             # June 2026 pres. p.40
        "op_margin_at_launch": 0.30,
        "op_margin_at_peak":   0.30,
        "op_margin_launch_anchor_year": 2033,
        "op_margin_peak_anchor_year":   2037,
        "jj_royalty_haircut": 0.0,
        # Remaining Phase 2 cost through Q4 2026 readout: Idorsia historical
        # burn ~CHF 24 M/year on P2 PoC studies, 0.75 years remaining = CHF 18 M.
        # status: placeholder, see TODO_DATA.md.
        "remaining_current_phase_cost_chf_m": 18.0,
        "include": True,
    },
    # -------------------------------------------------------------------------
    "cxcr7_antagonist": {
        "name":            "ACT-1004-1239 (CXCR7 antagonist)",
        "indication":      "progressive multiple sclerosis",
        "phase":           "phase2",
        "pos":             cumulative_pos("phase2"),
        "launch_year":     2034,                             # PoC 2028 -> Ph3 -> launch ~2034
        "readout_year":    2028,                             # Q2 2028 readout (June 2026 pres. p.29)
        "historical_sales_chf_m": {},
        "peak_sales_chf_m": 400,
        "peak_sales_source": "PLACEHOLDER, progressive MS, first-in-class remyelination; refine post PoC",
        "ramp_years":      6,
        "patent_expiry":   2042,
        "op_margin_at_launch": 0.30,
        "op_margin_at_peak":   0.30,
        "op_margin_launch_anchor_year": 2034,
        "op_margin_peak_anchor_year":   2038,
        "jj_royalty_haircut": 0.0,
        # Burn ~CHF 24 M/year, 2 years remaining to Q2 2028 readout = CHF 48 M.
        "remaining_current_phase_cost_chf_m": 48.0,
        "include": True,
    },
    # -------------------------------------------------------------------------
    "cxcr3_antagonist": {
        "name":            "ACT-777991 (CXCR3 antagonist)",
        "indication":      "vitiligo (PoC)",
        "phase":           "phase2",
        "pos":             cumulative_pos("phase2"),
        "launch_year":     2033,
        "readout_year":    2027,                             # readout 2027 (June 2026 pres. p.29)
        "historical_sales_chf_m": {},
        "peak_sales_chf_m": 250,
        "peak_sales_source": "PLACEHOLDER, vitiligo (34 M diagnosed cases per June 2026 pres. p.42); refine post PoC",
        "ramp_years":      5,
        "patent_expiry":   2041,
        "op_margin_at_launch": 0.30,
        "op_margin_at_peak":   0.30,
        "op_margin_launch_anchor_year": 2033,
        "op_margin_peak_anchor_year":   2037,
        "jj_royalty_haircut": 0.0,
        # Burn ~CHF 24 M/year, 1.5 years remaining to 2027 readout = CHF 36 M.
        "remaining_current_phase_cost_chf_m": 36.0,
        "include": True,
    },
    # -------------------------------------------------------------------------
    "cdiff_vaccine": {
        "name":            "IDOR-1134-2831 (C. diff synthetic glycan vaccine)",
        "indication":      "C. difficile infection prevention",
        "phase":           "phase1",
        "pos":             cumulative_pos("phase1"),         # 0.0786 (BIO 2021)
        "launch_year":     2035,
        "readout_year":    2027,
        "historical_sales_chf_m": {},
        "peak_sales_chf_m": 200,
        "peak_sales_source": "PLACEHOLDER, assumed partnered; value to Idorsia = royalty/milestone stream",
        "ramp_years":      5,
        "patent_expiry":   2040,
        "op_margin_at_launch": 0.20,
        "op_margin_at_peak":   0.20,
        "op_margin_launch_anchor_year": 2035,
        "op_margin_peak_anchor_year":   2039,
        "jj_royalty_haircut": 0.0,
        "remaining_current_phase_cost_chf_m": 10.0,
        "include": False,                                    # partnership terms unknown
    },
    # -------------------------------------------------------------------------
    # SARL assets (aprocitentan / selatogrel / cenerimod), deliberately NOT
    # included in the base case per the structural note at the top of this file.
    # They are held at Idorsia Investments SARL and service the CHF 762 M
    # ring-fenced notes; residual value reverts to parent only after full debt
    # repayment. See methodology.qmd for how this is discussed.
}


# =============================================================================
# 9. SARL reversion, option-like residual claim (base case = 0)
# =============================================================================
# source: June 2026 presentation p.46, "Rights return to Idorsia once debt
# and interest are repaid delivering long-term value". Deep OTM option.
SARL_RESIDUAL_VALUE_CHF_M = 0.0


# =============================================================================
# 10. Convenience: net cash bridge for the parent equity holder
# =============================================================================
def parent_net_cash_chf_m() -> float:
    """Net cash attributable to parent equity holders (CHF M).

    Excludes ring-fenced SARL debt (non-recourse) and SARL cash (currently
    not separately disclosed; using group cash as upper bound, see
    TODO_DATA.md).
    """
    return PARENT_ATTRIBUTABLE_CASH_CHF_M - PARENT_ATTRIBUTABLE_DEBT_CHF_M
