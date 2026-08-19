"""Build notebooks/analysis.ipynb programmatically, then execute it.

Run from the repo root:
    python notebooks/_build_notebook.py

Produces notebooks/analysis.ipynb with all cells executed and outputs
committed, ready for `jupyter nbconvert --to html` (per pitfalls memory).
"""

from __future__ import annotations

import pathlib

import nbformat as nbf
from nbclient import NotebookClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
NB_PATH = ROOT / "notebooks" / "analysis.ipynb"

nb = nbf.v4.new_notebook()
nb.metadata = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"},
}
cells: list = []


def md(text: str) -> None:
    cells.append(nbf.v4.new_markdown_cell(text.strip("\n")))


def code(source: str) -> None:
    cells.append(nbf.v4.new_code_cell(source.strip("\n")))


# ---------------------------------------------------------------------------
# 0. Title
# ---------------------------------------------------------------------------
md("""
# Idorsia rNPV, working notebook

*A risk adjusted NPV of Idorsia's pipeline, product by product.*

This notebook is the reproducible workbook behind the site's
[Results](../results.qmd) page. Every number is traceable to a public
source in [`src/assumptions.py`](../src/assumptions.py). The narrative
version of the conclusions lives in `results.qmd`; this notebook is the
audit trail.

**Structure**

1. Idorsia at a glance, market data and 2025 financials
2. The structural puzzle, parent Ltd vs Idorsia Investments SARL
3. Assumptions, pipeline, PoS benchmarks, discount rate
4. Revenue projections
5. Product level rNPVs
6. Enterprise value bridge
7. Sensitivities
8. Scenarios, fair value vs market
9. Verdict and limitations
""")

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
code("""
%matplotlib inline
import sys, pathlib
ROOT = pathlib.Path.cwd().parent if pathlib.Path.cwd().name == "notebooks" else pathlib.Path.cwd()
sys.path.insert(0, str(ROOT))

import pandas as pd
from IPython.display import Image, display

from src import assumptions as A
from src import rnpv
from src import sensitivity as S

pd.set_option("display.float_format", lambda x: f"{x:,.2f}")
FIG_DIR = ROOT / "outputs" / "figures"
""")

# ---------------------------------------------------------------------------
# 1. Idorsia at a glance
# ---------------------------------------------------------------------------
md("""
## 1. Idorsia at a glance

Idorsia Ltd (SIX: IDIA) is a Swiss specialty biotech founded on the
scientific legacy of Actelion. It runs one commercial product
(**QUVIVIQ / daridorexant**, insomnia, approved US 2022, EU 2022) and
a clinical pipeline led by lucerastat (Phase 3, Fabry disease). A second
approved product, **TRYVIO / JERAYGO** (aprocitentan, resistant
hypertension), was **transferred in 2025 to a ring fenced subsidiary**
(Idorsia Investments SARL) to service CHF 762 M of restructured notes
we come back to this in §2.

Market and share data as of 31 Dec 2025:
""")

code("""
snapshot = pd.DataFrame({
    "Metric": [
        "Share price, close 31/12/25", "Shares outstanding", "Market cap 31/12/25",
        "Share price, mid June 2026", "Fully diluted potential shares",
    ],
    "Value": [
        f"CHF {A.SHARE_PRICE_YE2025_CHF:.2f}",
        f"{A.SHARES_OUTSTANDING_M:.1f} M",
        f"CHF {A.MARKET_CAP_YE2025_CHF_M:,.0f} M",
        f"CHF {A.SHARE_PRICE_CURRENT_CHF:.2f}  (as of {A.SHARE_PRICE_CURRENT_AS_OF})",
        f"{A.POTENTIAL_SHARES_FULLY_DILUTED_M:.1f} M",
    ],
})
snapshot
""")

md("""
Full year 2025 non GAAP (from the AR): net revenue CHF 214 M, operating
loss CHF 100 M, net loss CHF 118 M. QUVIVIQ sales more than doubled YoY
(2024 → 2025: CHF 61 M → 134 M). 2026 guidance is QUVIVIQ CHF 200 M,
non GAAP EBIT CHF –120 M, implying a materially narrower operating loss.
""")

# ---------------------------------------------------------------------------
# 2. The structural puzzle
# ---------------------------------------------------------------------------
md("""
## 2. The structural puzzle, parent vs SARL

This is the single point on which naïve valuations of Idorsia go wrong.

In May 2025 Idorsia transferred the rights to **aprocitentan (TRYVIO /
JERAYGO)**, **selatogrel** and **cenerimod** to a newly created
subsidiary, **Idorsia Investments SARL**. That SARL secures CHF 762 M of
notes maturing 2048/2050 plus a CHF 150 M new money facility. Rights only
revert to the parent (Idorsia Ltd, SIX listed) *after* the SARL debt +
interest are fully repaid.

For an equity holder of IDIA, this means:

- **What the parent captures directly**: QUVIVIQ + the R&D pipeline
  (lucerastat, CCR6, CXCR7, CXCR3, C. diff vaccine).
- **What the parent captures conditionally**: the SARL residual once the
  ring fenced debt is retired. Deep out of the money option, set to 0 in
  the base case, stressed to CHF 400-600 M in scenarios.

The parent attributable debt / cash bridge is therefore:
""")

code("""
bs = pd.DataFrame({
    "Item": [
        "Group cash & equivalents (31/12/25)",
        "  of which attributable to op co + parent (approx)",
        "Convertible loan (J&J, matures 2027)",
        "Convertible bonds (mature 2034/2038)",
        "Other financial debt (incl. R-Bridge)",
        "SARL notes (2048/2050), ring fenced",
        "SARL new money facility, ring fenced",
        "Parent attributable net cash (used in bridge)",
    ],
    "CHF M": [
        A.CASH_YE2025_CHF_M,
        A.PARENT_ATTRIBUTABLE_CASH_CHF_M,
        -A.DEBT_CONVERTIBLE_LOAN_JJ_CHF_M,
        -A.DEBT_CONVERTIBLE_BONDS_CHF_M,
        -A.DEBT_OTHER_FINANCIAL_CHF_M,
        -A.DEBT_NOTES_SARL_CHF_M,
        -A.DEBT_NEW_MONEY_FACILITY_CHF_M,
        A.parent_net_cash_chf_m(),
    ],
})
bs
""")

md("""
The J&J convertible loan (CHF 335 M, matures June 2027) has a conversion
strike of CHF ~11.55 / share (335 M ÷ 29 M shares), well out of the money
at the current price of CHF ~4.35, so we treat it as pure debt in the base
case. If IDIA rerates toward the strike this becomes an equity dilution
event; sensitivity discussed in §7.
""")

# ---------------------------------------------------------------------------
# 3. Assumptions
# ---------------------------------------------------------------------------
md("""
## 3. Assumptions

**Discount rate.** 12 % (biotech WACC range 11-13 %; stress at 10 %/14 %).

**PoS benchmarks**, Wong, Siah & Lo (2019, *Biostatistics* 20(2):273-286).
Phase to approval probabilities used for pipeline products:
""")

code("""
pos = pd.DataFrame(A.POS_BY_PHASE_WSL_2019.items(),
                   columns=["Phase", "PoS to approval"])
pos
""")

md("""
**Pipeline**, six products; the three SARL assets (aprocitentan,
selatogrel, cenerimod) are excluded by design (see §2). Each product's
peak sales, ramp, patent expiry and operating margin are documented with
sources in `src/assumptions.py`.
""")

code("""
def _phase_label(p):
    return p["phase"]

pipeline = pd.DataFrame([{
    "Product": p["name"],
    "Indication": p["indication"],
    "Phase": _phase_label(p),
    "PoS": p["pos"],
    "Launch": p["launch_year"],
    "Peak sales (CHF M)": p["peak_sales_chf_m"],
    "Ramp (yrs)": p["ramp_years"],
    "Patent expiry": p["patent_expiry"],
    "Op margin": p["op_margin"],
    "Included in base": p.get("include", True),
} for k, p in A.PRODUCTS.items()])
pipeline
""")

md("""
Two hypotheses carry most of the equity story and should be stressed
aggressively (§7 does that):

- **QUVIVIQ peak sales (CHF 600 M base)**. Belsomra plateaued at
  ~USD 300 M globally; GlobalData projects the 7MM DORA class to reach
  USD 4.1 bn by 2032 (multi drug). QUVIVIQ carries best in class daytime
  functioning + potential US descheduling upside. Base case is
  intentionally at the low end of "blockbuster potential".
- **Lucerastat peak sales (CHF 400 M base)**. Fabry market addressable
  ~USD 4 bn per Idorsia disclosure; comparables Fabrazyme peaked at
  ~USD 1 bn, Galafold at ~USD 450 M.
""")

# ---------------------------------------------------------------------------
# 4. Revenue projections
# ---------------------------------------------------------------------------
md("""
## 4. Revenue projections

Ramp → plateau → patent cliff, per product. Historical sales figures
(2023-2026) are hard anchored to the AR and to management guidance; the
model interpolates linearly to the peak year.
""")

code("""
S.plot_revenue_curves()
display(Image(str(FIG_DIR / "revenue_curves.png"), width=900))
""")

code("""
rev = rnpv.revenue_table()
rev.loc[[2026, 2028, 2030, 2032, 2035, 2037, 2040]].round(0)
""")

md("""
Notes on shape choices:

- QUVIVIQ ramp from CHF 200 M (2026 guidance) to CHF 600 M peak by 2030
  a linear 200 → 300 → 400 → 500 → 600 sequence, consistent with the
  ~+50 % YoY growth Idorsia has delivered and guides. An earlier v0
  used a 6-year ramp (peak 2028) but that implied 100 %+50 % YoY
  aggressive without a specific US descheduling catalyst.
- Lucerastat starts in 2031 (post-2029 filing target) with a 4-year ramp,
  consistent with orphan drug launch dynamics.
- Patent cliffs use a –85 % drop the year after expiry, decaying 30 %/yr
  thereafter, standard rNPV convention.
""")

# ---------------------------------------------------------------------------
# 5. Product level rNPVs
# ---------------------------------------------------------------------------
md("""
## 5. Product level rNPVs

For each product: rNPV = PoS × PV(operating cash flow) − PV(remaining
development costs).
""")

code("""
bridge = rnpv.value_per_share()
summary = rnpv.valuation_summary(bridge)
summary
""")

code("""
S.plot_pipeline_overview()
display(Image(str(FIG_DIR / "pipeline_overview.png"), width=900))
""")

md("""
Read: **QUVIVIQ dominates** at +CHF 776 M. Lucerastat adds +152 M after
PoS weighting and development costs. The three early stage clinical
candidates all print **negative rNPV** at current assumptions, their
Phase 2 PoS (21 %) applied to CHF 250-400 M peak sales guesses doesn't
cover the remaining prelaunch development spend.

Interpretation: this is not a claim that these programs should be shelved
it means our peak sales placeholders (CHF 250-400 M for a first in class
oral in psoriasis / MS / vitiligo) are almost certainly too low relative
to the ceilings those markets support. The base case is deliberately
conservative here; a positive PoC readout at Q4 2026 (CCR6) would justify
reanchoring peak sales upward.
""")

# ---------------------------------------------------------------------------
# 6. Enterprise value bridge
# ---------------------------------------------------------------------------
md("""
## 6. Enterprise value bridge, from cash to CHF / share
""")

code("""
S.plot_waterfall()
display(Image(str(FIG_DIR / "waterfall_ev.png"), width=1000))
""")

code("""
print(f"Sum of product rNPVs        : CHF {bridge['sum_rnpv_chf_m']:>8,.0f} M")
print(f"+ Parent net cash            : CHF {bridge['parent_net_cash_chf_m']:>8,.0f} M")
print(f"+ SARL residual (base = 0)   : CHF {bridge['sarl_residual_chf_m']:>8,.0f} M")
print(f"= Enterprise value (parent)  : CHF {bridge['ev_chf_m']:>8,.0f} M")
print(f"÷ Shares outstanding         :     {bridge['shares_m']:>8,.1f} M")
print(f"= Fair value / share         : CHF {bridge['value_per_share_chf']:>8,.2f}")
print(f"vs market price              : CHF {bridge['market_price_chf']:>8,.2f}")
print(f"Implied upside / (downside)  :     {bridge['upside_pct']:>+7,.1f} %")
""")

# ---------------------------------------------------------------------------
# 7. Sensitivities
# ---------------------------------------------------------------------------
md("""
## 7. Sensitivities

### Heatmap, value/share vs QUVIVIQ peak sales × discount rate
""")

code("""
S.plot_heatmap(S.heatmap_rate_vs_quviviq_peak())
display(Image(str(FIG_DIR / "sensitivity_heatmap.png"), width=900))
""")

md("""
To reach the current market price (CHF 4.35 / share) requires QUVIVIQ
peak sales of CHF ≈1,000-1,100 M *and* a discount rate of 9-10 %
i.e. both variables at their optimistic ends simultaneously. That is not
implausible if descheduling in the US, label enhancement on daytime
functioning, and pediatric approval all land favourably; but each is a
separate probabilistic event.

### Tornado, variables ranked by impact on value/share
""")

code("""
S.plot_tornado(S.tornado_data())
display(Image(str(FIG_DIR / "tornado.png"), width=900))
""")

md("""
QUVIVIQ peak sales dominate, followed by the SARL residual assumption
(0 vs CHF 400 M) and the QUVIVIQ operating margin. Discount rate is a
mid tier lever. No single variable at its ±30 % / ±20 % stress level
reaches the market price on its own; the market is pricing several
positive assumptions at once.
""")

# ---------------------------------------------------------------------------
# 8. Scenarios
# ---------------------------------------------------------------------------
md("""
## 8. Scenarios, fair value vs market
""")

code("""
S.plot_fair_value_vs_market()
display(Image(str(FIG_DIR / "fair_value_vs_market.png"), width=900))
""")

code("""
S.scenarios()
""")

md("""
- **Bear** (QUVIVIQ peak 400 M, lucerastat 250 M, discount 14 %):
  CHF –0.64 / share. Effectively equity negative, implies existing
  operating debt swamps the parent owned asset value.
- **Base** (assumptions as documented): CHF 0.89 / share.
- **Base + SARL residual 400 M**: CHF 2.48 / share. Adding a modest
  probability adjusted claim on the SARL notes' eventual repayment moves
  the model roughly two thirds of the way to the market price.
- **Bull** (QUVIVIQ 1,000 M, lucerastat 700 M, SARL residual 600 M,
  discount 10 %): CHF 6.65 / share. The market price sits neatly between
  Base+SARL and Bull.
""")

# ---------------------------------------------------------------------------
# 9. Verdict + limitations
# ---------------------------------------------------------------------------
md("""
## 9. Verdict and limitations

**Verdict.** The base case, using mid year discounting, industry standard
PoS benchmarks and conservative peak sales estimates for the parent owned
assets, values IDIA at CHF ~0.9 / share against a market of CHF ~4.35.
The ~80 % apparent gap is not a claim that IDIA is overvalued by 5×, it
is a claim that the market is pricing in three catalysts that the base
case deliberately excludes: (1) a non trivial residual value for the SARL
assets, (2) a QUVIVIQ trajectory north of CHF 600 M peak, and (3) implicit
optionality on the J&J convertible conversion.

Depending on how much probability one assigns to those three catalysts,
the reconciled fair value can be anywhere in the CHF 0.9 – 6.6 range.
A "Base + SARL residual" scenario at CHF 2.48 / share is a defensible
midpoint; a full bull scenario at CHF 6.6 requires several things to
line up simultaneously.

**Limitations.**

- rNPV is an order of magnitude tool. All figures here are constrained by
  the quality of the peak sales, PoS and discount rate inputs.
- Peak sales estimates for the three Phase 2 candidates are placeholders
  and drive their negative rNPVs; a positive PoC readout (CCR6 in Q4 2026)
  would materially reshape those numbers.
- We treat the J&J convertible as pure debt because the strike is well
  out of the money; on rerating this becomes an equity dilution event
  that reduces per share value at the same enterprise value.
- Working capital and capex are netted to zero. Tax is proxied by the
  EBIT margin. Product outcomes are assumed independent (no portfolio
  correlation).
- The SARL cash flow priorities (30 % of aprocitentan proceeds + 10 %
  each of selatogrel and cenerimod to J&J contingent liability) are
  approximated but not fully modelled, this is a known refinement.

Don't read the point estimate as a price target. Read the sourcing and
the scenarios. Every input is traceable, every scenario has an explicit
narrative, and every gap between the model and the market can be tied
to a specific assumption.
""")

# ---------------------------------------------------------------------------
# Finalise: assemble, execute, save
# ---------------------------------------------------------------------------
nb.cells = cells
print(f"[build] assembled {len(cells)} cells; executing …")
client = NotebookClient(
    nb,
    timeout=180,
    kernel_name="python3",
    resources={"metadata": {"path": str(ROOT / "notebooks")}},
)
client.execute()
NB_PATH.parent.mkdir(parents=True, exist_ok=True)
with NB_PATH.open("w", encoding="utf-8") as f:
    nbf.write(nb, f)
print(f"[build] wrote {NB_PATH}")
