#!/usr/bin/env python3
"""Show the first N SKUs that would be sent to Amazon, with computed prices.

Use this to pick a small set for the first real run.

Example:
    python scripts/list_candidates.py --file data/inputs/visiotech_connect.xlsx --limit 20
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings  # noqa: E402
from src.core.pricing import pricing_engine  # noqa: E402
from src.core.stock_mapping import advertised_quantity  # noqa: E402
from src.sources.visiotech import VisiotechSource  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=settings.visiotech_file or "data/inputs/visiotech_connect.xlsx")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--in-stock-only", action="store_true",
                        help="Only show SKUs with quantity > 0")
    args = parser.parse_args()

    rules = settings.load_rules()
    allowed = rules.get("suppliers", {}).get("visiotech", {}).get("allowed_brands", [])
    src = VisiotechSource(path=args.file, allowed_brands=allowed)

    print(f"{'SKU':<35} {'BRAND':<8} {'COST':>8} {'PRICE':>8} {'QTY':>4}  EAN")
    print("-" * 90)
    shown = 0
    for rec in src.fetch():
        if args.in_stock_only and rec.stock <= 0:
            continue
        try:
            p = pricing_engine.calculate_price(cost=rec.cost)
        except ValueError:
            continue
        qty = advertised_quantity(rec.stock, supplier="visiotech")
        print(f"{rec.sku:<35} {(rec.brand or ''):<8} "
              f"{rec.cost:>8.2f} {p.final_price:>8.2f} {qty:>4}  {rec.ean or ''}")
        shown += 1
        if shown >= args.limit:
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
