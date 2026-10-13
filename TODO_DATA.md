# TODO_DATA - placeholders and unresolved data points

This file lists every input in the model that is not fully sourced to a public
document. It is the audit list that must shrink over time. Each entry gives the
field, the current placeholder value, where it is used, and what to look for.

Status values:

- `sourced` : traceable to a cited public document, not listed here.
- `assumption` : explicitly assumed with a documented rationale, not a specific
  disclosure. Listed here for visibility.
- `placeholder` : holding-pen value awaiting disclosure. Must be the first
  priority to resolve.

Last update: v1.2 (post H1 2026 Report integration).

---

## v1.2 updates (resolved since v1.1)

- `CASH_30JUN2026_CHF_M`, `DEBT_PHARMAKON_LOAN_CHF_M`, `DEBT_CB_2034_CHF_M`,
  `DEBT_CB_2038_CHF_M`, `DEBT_SALE_LEASEBACK_CHF_M`,
  `DEBT_NOTES_SARL_A1/A2/B_CHF_M`, `SHARES_ISSUED_M`, `SHARES_JJ_CONVERSION_M`,
  `SHARES_WARRANTS_M`, `SHARES_UNVESTED_FREE_M`, `SHARES_OPTIONS_M`,
  `SHARES_CB_2034_IFCONVERTED_M`: all sourced to H1 2026 Report (publication
  30 Jul 2026). Local copy at `data/raw/2026-6m-idorsia-financial-report.pdf`.
- `CENTRAL_COSTS_GA_YEAR_1_CHF_M` (CHF 54 M) and
  `CENTRAL_COSTS_UPSTREAM_YEAR_1_CHF_M` (CHF 34 M): now sourced on the H1
  2026 non-GAAP operating expense breakdown (H1 p.6 and p.7).
- QUVIVIQ `op_margin_at_launch` (contribution margin, 9 % at 2026):
  sourced on the H1 2026 non-GAAP income statement as (97 - 19 - 69)/97
  (H1 p.3 / p.6).
- `JJ_RESIDUAL_ROYALTY_CAP_REMAINING_CHF_M` (CHF 272 M): sourced to the H1
  2026 Report, note 4, p.32.
- Semantic change: `op_margin_*` fields are now CONTRIBUTION margins
  ((sales - COGS - Selling) / sales), NOT EBIT margins. G&A and R&D are
  deducted ONCE elsewhere (central costs, dev costs). This resolves the
  v1.1 double-counting flagged below.

## placeholders (resolve first)

| Field | Current value | File | Resolve by |
|---|---|---|---|
| `PARENT_ATTRIBUTABLE_CASH_CHF_M` | CHF 88.7 M group cash + 16.2 M warrant proceeds (upper bound) | `src/assumptions.py` | The SARL-only cash sub-balance has never been disclosed cleanly. Group cash is an upper bound; parent-attributable cash is lower. Would need a line item like "SARL cash segregation" in the H1 or AR report. |
| `peak_sales_chf_m` for CCR6 (CHF 300), CXCR7 (CHF 400), CXCR3 (CHF 250) | first-in-class placeholder bracket | `src/assumptions.py` -> `PRODUCTS` | Post-PoC readouts (CCR6 Q4 2026, CXCR3 2027, CXCR7 Q2 2028) will materially change these. |
| `SHARE_PRICE_CURRENT_CHF` | pulled from `data/market.json` via `scripts/update_price.py` | `data/market.json` | Run the script before each deploy. The CI pipeline refreshes it on build; local dev loop should run it manually. |

## assumptions (traceable but not sourced to Idorsia)

These are explicitly flagged in the code (`status: assumption`) and do not
need to be "resolved" in the sense placeholders do, but they are the material
judgment calls underpinning the model.

| Field | Value | File | Rationale |
|---|---|---|---|
| `DEV_COSTS_BY_PHASE_CHF_M` | P1=32, P2=74, P3=322, filing=19 CHF 2026 M | `src/assumptions.py` | DiMasi, Grabowski, Hansen (2016) USD 2013 figures x 1.26 (US CPI 1.40 + USD/CHF 0.90). Benchmark figures; Idorsia-scale burn is lower, see calibration below. |
| `POS_TRANSITIONS` | P1->P2 52.0 %, P2->P3 28.9 %, P3->NDA 57.8 %, NDA->approval 90.6 % | `src/assumptions.py` | BIO/Informa/QLS "Clinical Development Success Rates 2011-2020" (2021), all-indication transitions. Industry-standard. |
| `DISCOUNT_RATE` | 12 % | `src/assumptions.py` | Standard biotech WACC range 11-13 %. Stressed 10 % / 14 % in sensitivity. |
| QUVIVIQ `op_margin_at_peak` | 55 % contribution (2030) | `src/assumptions.py` -> `PRODUCTS.quviviq` | COGS 12-20 % + Selling 25-30 % at steady state; implies specialty-biotech EBIT margin around 30 % after G&A and R&D. Stressed +/-10 pp in tornado. |
| Lucerastat contribution margin trajectory (25 % launch, 65 % peak) | orphan small sales force, higher COGS | `src/assumptions.py` -> `PRODUCTS.lucerastat` | Stressed +/-10 pp in tornado. |
| `remaining_current_phase_cost_chf_m` for CCR6 / CXCR7 / CXCR3 (CHF 10 / 24 / 18 M) | calibrated to 2026 guidance decomposition | `src/assumptions.py` -> `PRODUCTS` | Status `calibrated_to_2026_guidance`. The 2026 non-GAAP guidance decomposition implies dev CHF 60 M (= 330 total - 39 COGS - 143 selling - 54 G&A - 34 upstream research); scaled Phase 2 PoC remaining costs so the model matches. Lucerastat Phase 3 remains anchored on orphan registrational trial estimate (CHF 100 M). |
| `JJ_RESIDUAL_ROYALTY_RATE` | 4 % of net sales | `src/assumptions.py` | H1 Report discloses "low-to-mid single digit"; 4 % sits mid-range. Cap (CHF 272 M remaining) is sourced. |
| Central costs trajectory | decay 10 % / year, floor 50 M to 2040, proportional to weighted revenue 2041-2050 (floor 10 M) | `src/assumptions.py` | No disclosed trajectory; shape reflects current cost-cutting through profitability inflection, then normalisation. Stressed +/-25 % on the total (G&A + upstream) in tornado. |

## consistency checks

- **2026 opex ceiling**: the sum of modelled per-product 2026 development
  spend plus central costs plus COGS plus Selling should sit at or below
  the full-year non-GAAP guidance ceiling (CHF 330 M x 1.05). The pytest
  case `test_2026_opex_within_guidance_ceiling` enforces this; the
  `calibration_2026` function in `src/rnpv.py` prints the full breakdown.
- **J&J royalty cap**: cumulative J&J royalty paid out through the horizon
  must never exceed CHF 272 M. Enforced by
  `test_jj_royalty_cumulative_never_exceeds_cap`.
- **QUVIVIQ lifecycle R&D** (pediatric, label extensions, dosage
  optimisation): not modelled as a separate product. The 2026 development
  total is calibrated to implicitly cover it. Not projected beyond 2026.
  Flagged in Limitations.
- **Upstream research deduction without future-pipeline-value**: the
  CHF 34 M / year upstream line represents the cost of generating future
  pipeline candidates, but we attribute no value to those unborn
  candidates. Downward bias. Flagged in Limitations.
- **Pharmakon covenant-driven equity raise**: not in the share count. The
  covenant package includes an obligation to strengthen liquidity within
  an agreed timeframe (H1 p.44); the implied dilution is not modelled.
- **SARL note A1 / A2 limited guarantee** from Idorsia Ltd: excluded from
  the base case bridge; flagged in Limitations.
