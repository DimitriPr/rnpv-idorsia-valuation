"""Assumptions for the Idorsia rNPV model.

All numbers are traceable to a public source cited inline with `# source:`.
Currency: CHF millions. Convention: cash inflows
positive, outflows negative.

This is the v0 compiled from:
  - Idorsia Annual Report 2025 (published Feb 26, 2026)
  - Idorsia Investor Company Presentation, June 2026
  - Wong, Siah & Lo (2019), *Biostatistics*, PoS benchmarks
  - Public press coverage of DORA class comparables (Belsomra, Dayvigo)
Local copies of the two Idorsia PDFs live in data/raw/.

CRITICAL STRUCTURAL NOTE, read before touching PRODUCTS:
    Idorsia Ltd (SIX: IDIA) is the listed parent. In 2025 it transferred the
    rights to aprocitentan (TRYVIO/JERAYGO), selatogrel and cenerimod to
    Idorsia Investments SARL, a ring fenced subsidiary that secures CHF 762 M
    of notes due 2048/2050 and a CHF 150 M new money facility. Cash flows
    from those three assets service the SARL debt first; rights only revert
    to the parent once the debt+interest are fully repaid.

    The model therefore values, for the equity holder of IDIA:
      (1) QUVIVIQ (daridorexant), held at Idorsia Pharmaceuticals Ltd
      (2) The R&D pipeline (lucerastat + early stage), same op co
      (3) A residual / option value for the SARL reversion, set to 0 in
          the base case (documented as upside in the note)
      (4) Net cash/debt at the parent + op co (excluding SARL debt, which
          is non recourse to IDIA equity holders in expectation)

    Treating aprocitentan naively as a parent owned asset would materially
    overvalue IDIA. See the writeup for how this is discussed.
"""

from __future__ import annotations

# =============================================================================
# 1. MARKET DATA
# =============================================================================
# source: Idorsia AR 2025, "Key share data" table, p.8
SHARE_PRICE_YE2025_CHF = 4.26
MARKET_CAP_YE2025_CHF_M = 1_070
SHARES_OUTSTANDING_M = 250.7                    # basic, issued common
# source: Idorsia AR 2025, "Share count" table, p.145
POTENTIAL_SHARES_FULLY_DILUTED_M = 313.7        # incl. equity derivatives + instruments

# source: Yahoo Finance / IDIA.SW mid-2026 quotes (range CHF 4.05-4.65 in Jun 2026).
# Reference price used for the "fair value vs market" chart. Update at run time.
SHARE_PRICE_CURRENT_CHF = 4.35                  # mid June 2026 midpoint
SHARE_PRICE_CURRENT_AS_OF = "2026-06-17"        # date of the quote used

# =============================================================================
# 2. BALANCE SHEET (Group consolidated, Dec 31, 2025)
# =============================================================================
# source: Idorsia AR 2025, "Liquidity" table, p.145
CASH_YE2025_CHF_M = 89.0                        # group consolidated cash & equivalents

# source: Idorsia AR 2025, "Indebtedness" table, p.145 (nominal amounts)
DEBT_CONVERTIBLE_LOAN_JJ_CHF_M = 335.0          # J&J convertible loan, matures Jun 2027, 29 M shares dilution
DEBT_NOTES_SARL_CHF_M = 762.0                   # ring fenced SARL notes, due 2048/2050, NON RECOURSE to parent
DEBT_CONVERTIBLE_BONDS_CHF_M = 49.0             # convertible bonds, mature 2034/2038
DEBT_NEW_MONEY_FACILITY_CHF_M = 78.0            # SARL new money facility (nominal drawn)
DEBT_OTHER_FINANCIAL_CHF_M = 189.0              # incl. IFRS 16 lease obligations, small bank facilities,
                                                # and the R-Bridge royalty monetization (CHF 27 M, Note 17 AR p.146-147);
                                                # R-Bridge is a small piece, not the dominant one

# For the model: debt attributable to parent equity holder (i.e. excludes
# ring fenced SARL debt that is serviced by SARL assets):
PARENT_ATTRIBUTABLE_DEBT_CHF_M = (
    DEBT_CONVERTIBLE_LOAN_JJ_CHF_M
    + DEBT_CONVERTIBLE_BONDS_CHF_M
    + DEBT_OTHER_FINANCIAL_CHF_M
)
# SARL debt (excluded from parent EV bridge in base case):
SARL_DEBT_CHF_M = DEBT_NOTES_SARL_CHF_M + DEBT_NEW_MONEY_FACILITY_CHF_M

# For the model: cash attributable to parent equity holder.
# The AR shows CHF 32 m at holding co level (p.8459 of extracted text), so
# most consolidated cash sits at op co / SARL. Base case uses op co+parent cash,
# treating SARL cash as trapped:
PARENT_ATTRIBUTABLE_CASH_CHF_M = 89.0 - 20.0    # rough op co+parent share; refine when SARL only cash disclosed


# =============================================================================
# 3. DISCOUNT RATE + PoS BENCHMARKS
# =============================================================================
# source: standard biotech WACC range 11-13 % (methodology.qmd cites the range).
# Base case: 12 %. Sensitivity: 10 % / 14 %.
DISCOUNT_RATE = 0.12

# source: Wong, Siah & Lo (2019), *Biostatistics* 20(2), 273-286, overall,
# all indications, all sponsors phase to approval probabilities. Values here
# are the "phase of development → approval" figures (POA) that are the
# canonical rNPV inputs.
POS_BY_PHASE_WSL_2019 = {
    "phase1":   0.138,   # Phase 1 → approval
    "phase2":   0.209,   # Phase 2 → approval
    "phase3":   0.581,   # Phase 3 → approval
    "filed":    0.906,   # NDA/BLA → approval
    "marketed": 1.000,   # already commercial
}


# =============================================================================
# 4. DEVELOPMENT COSTS (remaining, prelaunch, not probability weighted)
# =============================================================================
# source: order of magnitude industry figures (Sertkaya et al. Clin Trials 2016;
# DiMasi et al. J Health Econ 2016). To be refined per Idorsia disclosure where
# available. Ranges below cover total remaining spend to filing.
DEV_COST_TO_FILING_CHF_M = {
    "phase1":   200.0,   # rough all in Phase 2+3+filing to launch
    "phase2":   150.0,   # remaining Phase 3 + filing
    "phase3":   100.0,   # remaining Phase 3 + filing
    "filed":     15.0,   # regulatory + launch prep
    "marketed":   0.0,
}


# =============================================================================
# 5. PRODUCTS, the pipeline
# =============================================================================
# Every product entry documents: phase, PoS override (if not the WSL benchmark),
# launch year, peak sales (CHF M), ramp years, patent expiry, operating margin,
# and the sources for each choice. Set `include=False` to exclude from base case.
#
# Convention: peak_sales_chf_m is Idorsia recognized net sales (NOT gross market
# value). For assets partnered / royalty only, this must be the royalty stream.

PRODUCTS: dict[str, dict] = {
    # -------------------------------------------------------------------------
    "quviviq": {
        "name":            "QUVIVIQ (daridorexant)",
        "indication":      "chronic insomnia",
        "phase":           "marketed",
        "pos":             1.00,                    # source: approved FDA Jan 2022, EMA Apr 2022
        "launch_year":     2022,
        # Historical Idorsia led sales, CHF M:
        #   2023: 31 / 2024: 61 / 2025: 134   # source: June 2026 investor presentation p.4 (sales barchart);
        #                                     #         cross checked with AR 2025 p.146 (CHF 134 M net sales 2025)
        #   2026 guidance: 200                # source: June 2026 presentation p.45 (2026 financial guidance)
        "historical_sales_chf_m": {2023: 31, 2024: 61, 2025: 134, 2026: 200},
        # Peak sales, this is the single biggest lever. See discussion below.
        "peak_sales_chf_m": 600,
        # Rationale for CHF 600 M peak (~ USD 700 M):
        #   - Belsomra plateaued at ~USD 300 M globally (Pharmaphorum, 2020)
        #     despite first mover advantage, dragged by generic hypnotics.
        #   - GlobalData/ClinicalTrialsArena project DORA class in 7MM to reach
        #     USD 4.1 bn by 2032 (multiple DORAs sharing).
        #   - QUVIVIQ carries best in class positioning (unique daytime
        #     functioning benefit) + potential US descheduling catalyst.
        #   - 2026 guidance CHF 200 M with ~+50 % YoY implies durable growth
        #     toward CHF 500-700 M in ~2028-2030.
        # Base case sits at the low end of "blockbuster potential" (which
        # Idorsia messaging targets); stress upside to CHF 800-1000 M.
        "peak_sales_source": "Bottom up bracket vs Belsomra/Dayvigo comps and GlobalData 7MM DORA forecast",
        # ramp_years = 8 (peak 2030) reflects a realistic S curve growth from CHF 200 M in 2026
        # to CHF 600 M by 2030. Earlier v0 used ramp_years=6 (peak 2028) which implied 100%+50% YoY
        # aggressive vs the ~+50 % YoY seen in 2024→2025 and guided for 2025→2026. Kept explicit for
        # sensitivity: see methodology.qmd §Modelling conventions.
        "ramp_years":      8,                        # 2022 launch → peak ~2030
        # source: June 2026 presentation p.15, "US exclusivity to at least 2036, EU exclusivity to at least 2037"
        "patent_expiry":   2036,                     # US binding; EU one year later
        "op_margin":       0.30,                     # source: specialty biotech mature range 25-40%, methodology
        # J&J contingent liability: 3-5% of net sales + 10% contract revenue,
        # up to CHF 277 m combined with SARL. Approximate as -4 % on peak sales.
        # source: June 2026 presentation p.46 footnote.
        "jj_royalty_haircut": 0.04,
        "include": True,
    },
    # -------------------------------------------------------------------------
    "lucerastat": {
        "name":            "Lucerastat",
        "indication":      "Fabry disease (oral, all mutations)",
        "phase":           "phase3",
        # PoS: WSL Phase 3 → approval = 58.1 %. Rare disease / oral novel MoA
        # arguably +/-, but staying with the benchmark for the base case.
        "pos":             POS_BY_PHASE_WSL_2019["phase3"],
        # source: June 2026 presentation p.29, "regulatory pathway to
        # registration agreed with the FDA … supports a potential regulatory
        # filing as early as 2029". Filing 2029 → launch ~2030-2031.
        "launch_year":     2031,
        "historical_sales_chf_m": {},
        "peak_sales_chf_m": 400,
        # Rationale for CHF 400 M peak:
        #   - Company disclosure (June 2026 pres. p.30): Fabry population
        #     ~16 k → ~21 k by 2034, "representing a $4 Billion market"
        #     (addressable market, not achievable revenue).
        #   - Comparables: Fabrazyme (Sanofi ERT) peaked ~ USD 1.0 bn;
        #     Galafold (Amicus, oral chaperone) reached USD ~450 M.
        #   - Lucerastat is first oral for all mutation patients but faces
        #     entrenched ERTs. A 20-40 % share of a growing market = USD 400-800 M.
        #   - Base case picked at USD ~450 M ≈ CHF 400 M. Upside CHF 700 M.
        "peak_sales_source": "Company cited $4 B market + Fabrazyme/Galafold comparables",
        "ramp_years":      4,                        # orphan drugs ramp faster
        # Orphan drug exclusivity + composition of matter patents typically
        # provide ~10-14 y post launch. Placeholder to refine from patent search.
        "patent_expiry":   2042,
        "op_margin":       0.35,                     # orphan/oral → higher margin than mass market
        "jj_royalty_haircut": 0.0,                   # source: J&J contingent applies to QUVIVIQ + SARL assets only
        "include": True,
    },
    # -------------------------------------------------------------------------
    "ccr6_antagonist": {
        "name":            "IDOR-1117-2520 (CCR6 antagonist)",
        "indication":      "psoriasis (PoC) → Th17 immune disorders",
        "phase":           "phase2",
        # source: June 2026 presentation p.29, Phase 2 PoC fully enrolled, Q4 2026 readout.
        "pos":             POS_BY_PHASE_WSL_2019["phase2"],   # 20.9 %
        "launch_year":     2033,                     # PoC 2026 → Ph3 → filing ~2031 → launch ~2033
        "historical_sales_chf_m": {},
        # Peak sales: broad Th17 space (psoriasis alone worth $10+ bn but
        # crowded with biologics). First in class oral targeted alt could
        # take niche share. Very speculative, set at CHF 300 M placeholder.
        "peak_sales_chf_m": 300,
        "peak_sales_source": "PLACEHOLDER, Th17 immune disorder space, first in class oral; refine post PoC",
        "ramp_years":      5,
        # source: June 2026 presentation p.40, "Patent: up to April 2046 (inc. SPC/PTE)"
        "patent_expiry":   2046,
        "op_margin":       0.30,
        "jj_royalty_haircut": 0.0,
        "include": True,
    },
    # -------------------------------------------------------------------------
    "cxcr7_antagonist": {
        "name":            "ACT-1004-1239 (CXCR7 antagonist)",
        "indication":      "progressive multiple sclerosis",
        "phase":           "phase2",
        # source: June 2026 presentation p.29, Phase 2 PoC initiated Q1 2026, Q2 2028 readout.
        "pos":             POS_BY_PHASE_WSL_2019["phase2"],
        "launch_year":     2034,                     # PoC 2028 → Ph3 → launch ~2034
        "historical_sales_chf_m": {},
        # MS market huge; potential remyelination MoA would be paradigm shift.
        # Very early, placeholder.
        "peak_sales_chf_m": 400,
        "peak_sales_source": "PLACEHOLDER, progressive MS, first in class remyelination; refine post PoC",
        "ramp_years":      6,
        # source: June 2026 presentation p.41, "Patent: up to July 2042 (inc. SPC/PTE)"
        "patent_expiry":   2042,
        "op_margin":       0.30,
        "jj_royalty_haircut": 0.0,
        "include": True,
    },
    # -------------------------------------------------------------------------
    "cxcr3_antagonist": {
        "name":            "ACT-777991 (CXCR3 antagonist)",
        "indication":      "vitiligo (PoC)",
        "phase":           "phase2",
        # source: June 2026 presentation p.29, Phase 2 PoC initiation Q2 2026, readout 2027.
        "pos":             POS_BY_PHASE_WSL_2019["phase2"],
        "launch_year":     2033,
        "historical_sales_chf_m": {},
        "peak_sales_chf_m": 250,
        "peak_sales_source": "PLACEHOLDER, vitiligo (34 M diagnosed cases, per June 2026 pres. p.42); refine post PoC",
        "ramp_years":      5,
        # source: June 2026 presentation p.42, "Patent: up to Jan 2041 (inc. SPC/PTE)"
        "patent_expiry":   2041,
        "op_margin":       0.30,
        "jj_royalty_haircut": 0.0,
        "include": True,
    },
    # -------------------------------------------------------------------------
    "cdiff_vaccine": {
        "name":            "IDOR-1134-2831 (C. diff synthetic glycan vaccine)",
        "indication":      "C. difficile infection prevention",
        "phase":           "phase1",
        # Phase 1 complete, partnering discussions active. WSL Phase 1 → approval 13.8 %.
        "pos":             POS_BY_PHASE_WSL_2019["phase1"],
        "launch_year":     2035,
        "historical_sales_chf_m": {},
        "peak_sales_chf_m": 200,
        "peak_sales_source": "PLACEHOLDER, assumed partnered; value to Idorsia = royalty/milestone stream",
        "ramp_years":      5,
        "patent_expiry":   2040,
        "op_margin":       0.20,                     # if partnered: net royalty ~15-20 %
        "jj_royalty_haircut": 0.0,
        "include": False,                            # excluded from base case (partnership terms unknown)
    },
    # -------------------------------------------------------------------------
    # SARL assets (aprocitentan / selatogrel / cenerimod), deliberately NOT
    # included in the base case per the structural note at the top of this file.
    # They are held at Idorsia Investments SARL and service the CHF 762 M
    # ring fenced notes; residual value reverts to parent only after full debt
    # repayment. See methodology.qmd for how this is discussed.
    #
    # For sensitivity, a placeholder residual value contribution can be added
    # in rnpv.py (see SARL_RESIDUAL_VALUE_CHF_M below).
}


# =============================================================================
# 6. SARL reversion, option like residual claim (base case = 0)
# =============================================================================
# source: June 2026 presentation p.46, "Rights return to Idorsia once debt
# and interest are repaid delivering long term value". This is a deep out of the money option: it requires the SARL assets (mainly aprocitentan peak sales
# ambition $5 B, US exclusivity 2034) to service CHF 912 M of debt + interest
# over 20+ years. In the base case we set this to zero and flag it as upside.
SARL_RESIDUAL_VALUE_CHF_M = 0.0


# =============================================================================
# 7. Convenience: net cash bridge for the parent equity holder
# =============================================================================
def parent_net_cash_chf_m() -> float:
    """Net cash attributable to parent equity holders (CHF M).

    Excludes SARL debt (ring fenced, non recourse) and SARL cash (trapped).
    """
    return PARENT_ATTRIBUTABLE_CASH_CHF_M - PARENT_ATTRIBUTABLE_DEBT_CHF_M
