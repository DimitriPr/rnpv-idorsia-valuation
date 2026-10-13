# Changelog

## v1.1 — 2026-10-13

External review found method errors, stale data, and page-to-page
inconsistencies in v1.0. This release addresses every item one-by-one
across five commits. The verdict section is deliberately left as a
`callout-warning` placeholder pending author validation of the new
numbers; a drafted replacement is attached below for review.

### One-line summary per correction

- **Phase-weighted development costs.** `development_cost_curve()` no
  longer treats Phase 3 / filing spend as certain. The current phase is
  spent in full between the valuation year and the readout year; each
  subsequent phase is weighted by the cumulative probability of reaching
  it. Per-product `readout_year` and `remaining_current_phase_cost_chf_m`
  were added. Lucerastat Phase 3 remaining cost overrides the DiMasi
  benchmark to reflect orphan-trial economics.
- **PoS single-sourced to BIO 2011-2020.** `POS_TRANSITIONS` replaces
  the v1.0 WSL label on numbers that actually combined BIO's
  filing→approval figure (90.6 %) with Biomedtracker's P3→approval
  (58.1 %). WSL (2019) corrigendum noted. BIO LOA from Phase 1 (7.9 %)
  matches the product of transitions.
- **Methodology PoS table generated from the code.** `methodology.qmd`
  pulls transitions and cumulative values via inline `{python}` chunks.
- **Central costs (unallocated G&A + upstream research).** New line
  in the equity bridge. G&A sourced to AR 2025 non-GAAP SG&A breakdown
  (71 M); upstream placeholder 25 M listed in TODO_DATA.md. Decay 10 %/
  year to floor 50 M by 2040, then proportional to weighted revenue to
  2050 with hard floor 10 M. PV ≈ CHF 504 M. Added to tornado via a
  ±50 % stress on the upstream component. Consistency check
  (year-1 modelled R&D 85 M + central 96 M = 181 M vs AR 2025 R&D+G&A
  163 M, +18 M overshoot) flagged in TODO_DATA.md.
- **QUVIVIQ op-margin trajectory.** Flat 30 % from 2026 replaced by a
  parameterised curve: 5 % at launch anchor (2026, Idorsia's commercial-
  profitability target year), interpolating linearly to 30 % at peak
  (2030). Backwards-compat kept via `product_margin_curve()`.
- **Per-share value floored at zero.** Limited liability. Raw negative
  value kept under `value_per_share_raw_chf` for display in notes.
- **Terminology: equity value, not enterprise value.** All code paths,
  figure titles and site text now say "equity value (parent)". A
  deprecated `enterprise_value()` shim and `ev_chf_m` key alias remain
  for backwards-compat during the transition.
- **J&J convertible if-converted test.** `apply_if_converted(bridge)`
  triggers when raw V/share > strike (CHF 11.51), removing CHF 335 M
  from parent debt and adding 29.1 M shares. Scenarios apply the test
  per scenario. Convertible described as a *cost* (dilution or cash
  repayment on 15 Jun 2027), never an upside.
- **"Three catalysts" claim corrected.** Index TL;DR, results TL;DR,
  notebook builder: now "two catalysts" (SARL residual + QUVIVIQ
  trajectory) plus "one refinancing event" (J&J convertible maturity
  2027).
- **Pharmakon term loan added.** CHF 150 M tranche 1 at op co, sourced
  to the 9/26 Jun 2026 Idorsia media releases and Goodwin advisory
  note. Added to `PARENT_ATTRIBUTABLE_DEBT_CHF_M`. SARL New Money
  Facility set to 0 (repaid in full from Pharmakon proceeds).
- **Single valuation date.** `VALUATION_DATE = "2026-06-30"`. H1 2026
  balance sheet not yet published; group cash and non-Pharmakon debt
  lines retained from YE 2025 as upper bounds, with a quantified H1
  2026 cash reconciliation (+150 Pharmakon, −105 facility, net +45
  less H1 burn) in TODO_DATA.md.
- **Share count updated to Q1 2026.** 250.7 → 254.0 M issued;
  313.7 → 317.1 M potential (incl. J&J convertible 29.1 M).
- **Live share price via yfinance.** `scripts/update_price.py` writes
  `data/market.json` from IDIA.SW latest close. Site loads the file;
  fallback placeholder keeps the pipeline functional offline. Current
  pin: CHF 4.22 as of 2026-10-13.
- **Arbitrary 89 − 20 cash split removed.** Parent-attributable cash =
  group cash as an upper bound, status `placeholder`.
- **QUVIVIQ growth table.** Dynamic table showing +97 %, +120 %, +49 %
  guided replaces "~+50 % YoY historical". Narrative text updated.
- **DEA Schedule V (not full descheduling).** 11 Aug 2026 DEA proposal
  reclassifies DORAs from Schedule IV to Schedule V. Text updated across
  index, results and notebook; described as a modest commercial
  accelerator, not transformational.
- **All numbers inline Python.** `index.qmd` and `results.qmd` no
  longer carry hardcoded values (0.89, 4.35, 250.7, "two thirds").
  Every cited number comes from a Quarto `{python}` chunk against the
  model objects. `methodology.qmd` already converted in Lot 1.
- **Status field on every key input.** New `A.key_assumptions()` helper
  returns rows with `status ∈ {sourced, assumption, placeholder}`. The
  "Key assumptions and sources" table on results.qmd displays the
  column, so readers see at a glance which inputs are grounded.
- **Reconciled range made unique and dynamic.** `RANGE_LO = min`,
  `RANGE_HI = max` across the four scenarios (post-floor,
  post-if-converted). Reused on both the index and results pages.
  Current range CHF 0.00 – 2.75 / share.
- **Gap-covered fraction computed, not asserted.** `gap_covered_pct()`
  replaces the "roughly two thirds" claim. Under current numbers it
  evaluates to 0 % because the Base+SARL scenario is still below the
  zero floor.
- **Statements corrected / softened.** "Every number is sourced" →
  "Every input is either sourced or explicitly flagged as an
  assumption". "Constructed bottom-up" rewritten (triangulation vs
  comparables + disclosure, not patient × penetration × price). Ramp
  "5-7 years" dropped from methodology prose (specific durations
  shown per product). "Low end of blockbuster potential" rewritten
  (USD 1 bn blockbuster ~ CHF 850 M Idorsia-recognized, so CHF 600 M
  is mid-range specialty, not low-end blockbuster). Central costs
  and convertible treatment added to "What is NOT modelled" / Limitations.
- **Notebook 404 links fixed.** `(../results.qmd)` → `(../results.html)`;
  `(../src/assumptions.py)` → GitHub blob URL.
- **"Rebuild before deploying" note moved.** Removed from notebook.qmd,
  placed in the new README.md alongside the full local dev / rebuild
  pipeline.
- **"p.8459 of extracted text" dropped.** Removed by the Lot 1
  rewrite of `assumptions.py` (parent-attributable cash section).
- **Tests, pytest, CI.** 14 pytest cases: cumulative PoS = product of
  transitions, BIO LOA from Phase 1 ~ 7.9 %, current-phase remaining
  is certain, future phase cost weighted by cumulative transition
  probability, filing cost doubly weighted after Phase 3, marketed
  returns empty curve, total scheduled dev cost = sum of weighted
  phase costs, equity value = Σ rNPV + net cash + SARL − PV(central),
  central PV in [300, 800], per-share floor, floor flag tracking,
  if-converted no-trigger below strike, if-converted trigger +
  dilution above strike, strike = 335 / 29.1. All green.
- **CI updated.** `publish.yml` installs Python 3.12 + requirements.txt,
  runs pytest, then renders Quarto. Needed so inline `{python}` chunks
  execute during the Pages build.

### Before / after key figures

Base case (per share, floor applied):

| Metric | v1.0 | v1.1 | Δ |
|---|---:|---:|---:|
| Σ product rNPVs (CHF M) | +727 | +528 | −199 |
|   QUVIVIQ rNPV | +776 | +623 | −153 (margin ramp 5→30 vs flat 30) |
|   Lucerastat rNPV | +152 | +114 | −38  (BIO PoS 52.4 % vs 58.1 % + DiMasi dev costs) |
|   CCR6 rNPV | −61 | −58 | +3 |
|   CXCR7 rNPV | −64 | −73 | −9 |
|   CXCR3 rNPV | −77 | −78 | −1 |
| Parent net cash | −504 | −634 | −130 (Pharmakon +150 debt, cash upper bound restored +20) |
| PV central costs | — | +504 | +504 (new line) |
| Equity value (parent) | +223 | −611 | −834 |
| Value / share, raw | +0.89 | −2.40 | −3.29 |
| Value / share, floored | +0.89 | +0.00 | −0.89 |
| Market price (CHF) | 4.35 (2026-06-17) | 4.22 (2026-10-13) | yfinance refresh |

Scenarios (per share, post-floor, post-if-converted):

| Scenario | v1.0 | v1.1 |
|---|---:|---:|
| Bear | −0.64 | 0.00 |
| Base | +0.89 | 0.00 |
| Base + SARL residual (CHF 400 M) | +2.48 | 0.00 |
| Bull (SARL residual CHF 600 M, rate 10 %, QUVIVIQ 1000 / Luc 700) | +6.65 | +2.75 |
| Reconciled range | 0.9 – 6.6 | 0.00 – 2.75 |

The large swing is driven by three structural changes compounding:
(1) PoS lower under BIO 2021 (Phase 2 cumulative 15.1 % vs 20.9 %;
Phase 3 cumulative 52.4 % vs 58.1 %); (2) QUVIVIQ margin ramp 5→30 %
replacing flat 30 % from 2026; (3) PV of central costs now deducted
(~CHF 504 M) where v1.0 had zero. The Pharmakon loan (CHF 150 M added
to parent debt) accounts for ~CHF 0.6 per share.

### Proposed verdict (awaiting author validation)

> *This section is a drafted replacement for the v1.0 verdict in
> results.qmd. It is NOT merged — the final text requires author
> sign-off before being substituted.*
>
> **The gap between the model and the market has widened, and so has
> the required set of assumptions behind the market price.**
>
> The v1.1 base case floors at CHF 0.00 / share (raw equity value
> −CHF 611 M). This is a hard lower bound under three jointly binding
> constraints: BIO 2011-2020 PoS transitions applied cleanly, QUVIVIQ
> margin ramping from the 2026 commercial-profitability target to a
> mid-range specialty 30 % at peak, and PV of unallocated central costs
> deducted from the equity bridge. The market at CHF 4.22 therefore
> embeds assumptions that, on a probability-weighted basis, span the
> full range of upside paths:
>
> - A **SARL residual** at least matching the CHF 400 M stressed in
>   scenarios (not sufficient on its own to clear the zero floor
>   under the current cost structure).
> - A QUVIVIQ trajectory **well above** the CHF 600 M base-case peak
>   (closer to the CHF 1,000 M Bull case) and a discount rate at the
>   low end of the biotech WACC range.
> - A clean **refinancing** of the CHF 335 M J&J convertible on
>   15 June 2027: either cash repayment (reducing the equity bridge
>   directly) or conversion if V/share exceeds CHF 11.51 (dilutive but
>   debt-eliminating; the if-converted scenario is already applied in
>   the Bull case and still prints CHF 2.75 / share).
>
> **The reconciled range CHF 0.00 – 2.75 / share** is the honest answer
> under the method as corrected; the market price sits noticeably
> *above* even the Bull. That is not a claim IDIA is overvalued 1.5×:
> it is a claim the market is pricing a combined scenario that is
> *outside* the parameter space our scenarios span (e.g. a QUVIVIQ peak
> above CHF 1,000 M, SARL residual above CHF 600 M, central cost
> normalisation faster than modelled, discount rate below 10 %).
>
> **My reconciled personal read**: at CHF 4.22, IDIA is priced for a
> genuinely bullish composite outcome where (a) the DEA Schedule V
> reclassification, pediatric programme and EU reimbursement all
> contribute to a QUVIVIQ ceiling well above the CHF 600 M used here;
> (b) SARL asset performance clears the ring-fenced debt materially
> ahead of maturity; (c) the Pharmakon loan does not need to be
> extended on worse terms; and (d) the J&J convertible either converts
> (dilution absorbed by rerating) or is refinanced on terms that do
> not tighten covenants. Each of these is probabilistic; none is
> binary. The investable thesis is a *conditional long on specific
> catalyst delivery* (CCR6 PoC Q4 2026, QUVIVIQ US run-rate exit 2026,
> SARL progress disclosures) with limited margin of safety at the
> current level under the base case.
>
> *Don't read any point estimate here as a price target.* Read the
> status column of each input, the four scenarios, and the gap-covered
> percentage. Every assumption is traceable; every scenario has an
> explicit narrative; every CHF of the gap between the model and the
> market can be tied to a specific bet or a specific placeholder.
