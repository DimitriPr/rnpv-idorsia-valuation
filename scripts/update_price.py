"""Pull the latest IDIA.SW close from yfinance and write data/market.json.

Run from the repo root:
    python scripts/update_price.py

The site reads data/market.json for the current share price and the as-of
date. Everything else in the pipeline (figures, tables, inline Quarto
chunks) consumes this one source. Re-run before each `quarto render` /
deploy to pin the quote.

Status flag written to the JSON:
  - "sourced": fetched from yfinance successfully.
  - "placeholder": fallback (no network, API error, empty response).
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "market.json"
PLACEHOLDER = {
    "ticker": "IDIA.SW",
    "price_chf": 4.35,
    "as_of": "2026-06-17",
    "status": "placeholder",
    "source": "mid-June 2026 placeholder; yfinance unavailable",
}


def fetch_latest() -> dict:
    try:
        import yfinance as yf
    except ImportError:
        return PLACEHOLDER | {"source": "placeholder: yfinance not installed"}

    try:
        t = yf.Ticker("IDIA.SW")
        hist = t.history(period="5d")
    except Exception as exc:  # noqa: BLE001  - any yfinance / network failure
        return PLACEHOLDER | {"source": f"placeholder: yfinance error ({exc})"}

    if hist.empty:
        return PLACEHOLDER | {"source": "placeholder: yfinance returned empty history"}

    last = hist["Close"].dropna().iloc[-1]
    as_of = hist.index[-1].date().isoformat()
    return {
        "ticker": "IDIA.SW",
        "price_chf": round(float(last), 4),
        "as_of": as_of,
        "status": "sourced",
        "source": "yfinance IDIA.SW latest close",
    }


def main() -> int:
    data = fetch_latest()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print(f"[update_price] wrote {OUT.relative_to(ROOT)}: "
          f"CHF {data['price_chf']} as of {data['as_of']} ({data['status']})")
    return 0 if data["status"] == "sourced" else 2


if __name__ == "__main__":
    sys.exit(main())
