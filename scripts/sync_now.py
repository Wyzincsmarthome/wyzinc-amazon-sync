#!/usr/bin/env python3
"""Run the sync job immediately (manual trigger).

Examples:
    python scripts/sync_now.py --source csv --file data/inputs/products.csv
    python scripts/sync_now.py --source visiotech
    python scripts/sync_now.py --source csv --file data/inputs/products.csv --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Allow running from project root: `python scripts/sync_now.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.jobs.sync_job import run_sync  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Trigger an Amazon sync now.")
    parser.add_argument("--source", choices=["csv", "visiotech"], default="csv")
    parser.add_argument("--file", help="Input CSV/JSON/XLSX path")
    parser.add_argument("--dry-run", action="store_true", help="Build feed but do not submit")
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Cap the number of SKUs sent (useful for first tests).",
    )
    parser.add_argument(
        "--sku", default=None,
        help="Comma-separated list of SKUs to restrict the sync to.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    only_skus = [s.strip() for s in args.sku.split(",")] if args.sku else None
    summary = run_sync(
        source=args.source,
        input_file=args.file,
        dry_run=args.dry_run,
        limit=args.limit,
        only_skus=only_skus,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
