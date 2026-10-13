# TODO_DATA - placeholders and unresolved data points

This file lists every input in the model that is not fully sourced to a public
document. It is the audit list that must shrink over time. Each entry gives the
field, the current placeholder value, where it is used, and what to look for.

Status values:
- `sourced` : traceable to a cited public document - not listed here.
- `assumption` : explicitly assumed with a documented rationale, not a specific
  disclosure. Listed here for visibility.
- `placeholder` : holding-pen value awaiting disclosure. Must be the first
  priority to resolve.

---

## placeholders (resolve first)

| Field | Current value | File | Resolve by |
|---|---|---|---|
| `PARENT_ATTRIBUTABLE_CASH_CHF_M` | CHF 89 M (= group cash YE 2025) | `src/assumptions.py` | H1 2026 report - the SARL-only cash sub-balance has never been disclosed cleanly. Current value is an upper bound; actual parent-attributable cash is lower. The v1.0 model used an arbitrary CHF 89 - 20 = 69 M split; v1.1 removes the arbitrary subtraction and flags the overestimate here. |
| `CASH_YE2025_CHF_M` and all `DEBT_*_CHF_M` lines (except Pharmakon, which is sourced to the 26 Jun 2026 closing media release) | YE 2025 book values | `src/assumptions.py` | Idorsia H1 2026 Half-Year Report (expected ~Jul-Aug 2026). Rebalance the full indebtedness table to 30 Jun 2026. Place the PDF in `data/raw/` and update inline `# source:` comments. The H1 2026 cash line should mechanically reflect, versus YE 2025: +CHF 150 M Pharmakon tranche 1 drawdown, -CHF 105 M New Money Facility repayment (net +CHF 45 M at op co), minus operating cash burn H1 2026. |
| `CENTRAL_COSTS_UPSTREAM_YEAR_1_CHF_M` | CHF 25 M (~27 % of AR 2025 non-GAAP R&D CHF 92 M) | `src/assumptions.py` | AR 2025 or H1 2026 program-by-program R&D disclosure (if ever broken out). Alternative: Idorsia-specific guidance distinguishing "pipeline" vs "platform" R&D. Must satisfy consistency check: year-1 central + sum of year-1 product dev costs ~ AR 2025 R&D + G&A (CHF 163 M). |
| `remaining_current_phase_cost_chf_m` for CCR6, CXCR3, CXCR7 (CHF 18 / 36 / 48 M) | burn rate CHF 24 M/year × years-to-readout | `src/assumptions.py` -> `PRODUCTS` | Idorsia program-level R&D disclosure, if ever published. The CHF 24 M/year burn is derived from Idorsia-scale historical burn, not from Idorsia's own disclosure. |
| `remaining_current_phase_cost_chf_m` for Lucerastat (CHF 100 M, flagged `assumption` not `placeholder`) | orphan Fabry registrational trial estimate | `src/assumptions.py` | Idorsia disclosure of the lucerastat registrational trial budget, if ever published. DiMasi 2016 Phase 3 average (CHF 322 M) is too high for orphan diseases; CHF 100 M is a defensible assumption. |
| `peak_sales_chf_m` for CCR6 (CHF 300), CXCR7 (CHF 400), CXCR3 (CHF 250) | first-in-class placeholder bracket | `src/assumptions.py` -> `PRODUCTS` | Post-PoC readouts (CCR6 Q4 2026, CXCR3 2027, CXCR7 Q2 2028) will materially change these. |
| `SHARE_PRICE_CURRENT_CHF` | CHF 4.35 (2026-06-17 midpoint) | `data/market.json` or placeholder in `src/assumptions.py` | Run `scripts/update_price.py` to pull the latest IDIA.SW close from yfinance. Build/CI should run this before `quarto render`. |

## assumptions (traceable but not sourced to Idorsia)

These are explicitly flagged in the code (`status: assumption`) and do not
need to be "resolved" in the sense that the placeholders do, but they are the
material judgment calls underpinning the model.

| Field | Value | File | Rationale |
|---|---|---|---|
| `DEV_COSTS_BY_PHASE_CHF_M` | P1=32, P2=74, P3=322, filing=19 CHF 2026 M | `src/assumptions.py` | DiMasi, Grabowski, Hansen (2016) USD 2013 figures × 1.26 (US CPI 1.40 + USD/CHF 0.90). Benchmark figures; Idorsia-scale burn is lower. |
| `POS_TRANSITIONS` | P1->P2 52.0 %, P2->P3 28.9 %, P3->NDA 57.8 %, NDA->approval 90.6 % | `src/assumptions.py` | BIO/Informa/QLS "Clinical Development Success Rates 2011-2020" (2021), all-indication transitions. Industry-standard. |
| `DISCOUNT_RATE` | 12 % | `src/assumptions.py` | Standard biotech WACC range 11-13 %. Stressed 10 %/14 % in sensitivity. |
| QUVIVIQ `op_margin_at_launch` | 5 % (2026) | `src/assumptions.py` -> `PRODUCTS.quviviq` | 2026 is Idorsia's targeted first year of QUVIVIQ commercial profitability (June 2026 pres. p.45). CHF 200 M sales × 5 % = CHF 10 M operating profit - just above breakeven, consistent with the "commercial profitability targeted" messaging. |
| QUVIVIQ `op_margin_at_peak` | 30 % (2030) | `src/assumptions.py` -> `PRODUCTS.quviviq` | Specialty biotech mature range 25-40 %; 30 % is mid-range. |
| Central costs decay 10 %/year, floor 50 M to 2040, proportional to weighted revenue 2041-2050 (floor 10 M) | PV ~ CHF 500 M | `src/assumptions.py` | No disclosed Idorsia G&A trajectory; shape chosen to reflect current cost-cutting through profitability inflection, then normalisation. See sensitivity +/-50 % on `CENTRAL_COSTS_UPSTREAM_YEAR_1_CHF_M`. |

## consistency checks

- **R&D consistency**: year-1 central costs + sum of year-1 product dev costs
  should approximate the 2025 AR non-GAAP R&D line (CHF 92 M) + G&A line
  (CHF 71 M) = CHF 163 M. If materially higher, there is double-counting
  between `dev_cost_curve` and `central_costs_series`.
- **QUVIVIQ post-launch R&D not modelled**: the pediatric programme, label
  extensions and life-cycle studies are not captured in either
  `dev_cost_curve` (which handles prelaunch spend only) or `central_costs`
  (which excludes program-specific). Flagged in results.qmd Limitations.
- **Upstream research deduction without future-pipeline-value**: the
  CHF 25 M/year upstream line represents the cost of generating future
  pipeline candidates, but we attribute no value to those unborn candidates.
  This biases the model downward. Flagged in Limitations.
