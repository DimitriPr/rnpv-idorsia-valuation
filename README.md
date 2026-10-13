# rNPV Valuation - Idorsia (SIX: IDIA)

Risk-adjusted NPV valuation of Idorsia Ltd (SIX: IDIA), a Swiss specialty
biotech. The pipeline is valued product by product, with BIO 2011-2020
phase-weighted probabilities of success and phase-weighted development
costs. Parent-attributable equity value excludes the ring-fenced
Idorsia Investments SARL and deducts the present value of unallocated
central costs.

Published as a static Quarto site at
<https://dimitripr.github.io/rnpv-idorsia-valuation/>.

## Layout

- `src/` - the rNPV engine (`rnpv.py`), assumptions (`assumptions.py`),
  and sensitivity / figure generation (`sensitivity.py`).
- `tests/` - pytest cases covering PoS cumulative, phase-weighted dev
  cost scheduling, equity-value definition, floor, and if-converted test.
- `notebooks/_build_notebook.py` - programmatic builder for the
  interactive notebook; produces `notebooks/analysis.ipynb`.
- `outputs/figures/` - PNG figures consumed by the site.
- `data/` - `market.json` (yfinance quote cache) + raw source PDFs.
- `scripts/update_price.py` - pulls the latest IDIA.SW close from
  yfinance into `data/market.json`.
- `*.qmd` - Quarto pages: `index`, `methodology`, `results`, `notebook`,
  `about`. Every narrative number flows through an inline
  `` `{python}` `` chunk - no hardcoded values.
- `TODO_DATA.md` - list of inputs still awaiting disclosure
  (placeholders) or marked as explicit assumptions.

## Local dev / rebuild before deploying

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Refresh the share price (optional, writes data/market.json)
python scripts/update_price.py

# 3. Rebuild the executed notebook
python notebooks/_build_notebook.py
python -m jupyter nbconvert --to html notebooks/analysis.ipynb

# 4. Regenerate figures
python -c "from src import sensitivity as S; S.generate_all()"

# 5. Run the test suite
python -m pytest tests/ -q

# 6. Render the site
quarto render
```

CI (`.github/workflows/publish.yml`) runs steps 1, 5, 6 automatically on
push to `main` and deploys the rendered site to the `gh-pages` branch.
The `data/market.json` file is checked in so the site always has a
valid quote even if `update_price.py` has not been run on CI.

## Methodology

See [methodology.qmd](methodology.qmd) or the published site. In short:

- Revenue per product = ramp -> peak -> plateau -> patent cliff.
- Cash flow = revenue × (op margin curve - contingent royalties).
- rNPV = PoS × Σ discounted CF - Σ phase-weighted dev costs.
- PoS = product of BIO 2011-2020 transitions (P1->P2 52 %, P2->P3 29 %,
  P3->filing 58 %, filing->approval 91 %).
- Equity value = Σ rNPV + parent net cash + SARL residual - PV(central
  costs); per-share value floored at zero (limited liability).
- J&J convertible: pure debt in base case; if-converted test
  (+29.1 M shares, -CHF 335 M debt) triggers in scenarios where
  V/share > CHF 11.5 strike.

## Status

v1.1 (released 2026-10-13). See [CHANGELOG.md](CHANGELOG.md) for the
line-by-line diff vs v1.0 and the before/after key figures.

## Disclaimer

This is a personal research project (portfolio piece), not investment
advice. All inputs are public. No position held or recommended.
