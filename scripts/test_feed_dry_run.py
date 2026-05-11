#!/usr/bin/env python3
"""Build the JSON_LISTINGS_FEED locally without contacting Amazon.

Useful for inspecting the exact payload that would be sent.

Example:
    python scripts/test_feed_dry_run.py --file data/inputs/products.csv
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.amazon.feeds import build_feed_document  # noqa: E402
from src.jobs.sync_job import build_updates  # noqa: E402
from src.sources.csv_loader import CsvJsonSource  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, help="Path to CSV or JSON input")
    parser.add_argument("--limit", type=int, default=5, help="How many items to preview")
    args = parser.parse_args()

    records = list(CsvJsonSource(args.file).fetch())
    updates = build_updates(records, supplier="csv")[: args.limit]
    feed = build_feed_document(updates)
    print(json.dumps(feed, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
