# src/jobs/sync_job.py
"""End-to-end sync: read a catalog source, compute prices, push to Amazon."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from config.settings import settings
from src.amazon.feeds import chunk_updates, submit_feed
from src.core.models import FeedResult, PriceStockUpdate, ProductRecord
from src.core.pricing import pricing_engine
from src.core.stock_mapping import advertised_quantity
from src.sources.base import CatalogSource
from src.sources.csv_loader import CsvJsonSource
from src.sources.visiotech import VisiotechSource

logger = logging.getLogger(__name__)


def _build_source(source_name: str, input_file: Optional[str]) -> CatalogSource:
    if source_name == "csv":
        if not input_file:
            raise ValueError("source=csv requires input_file")
        return CsvJsonSource(input_file)
    if source_name == "visiotech":
        path = input_file or settings.visiotech_file
        if not path:
            raise ValueError(
                "source=visiotech needs a file path. Set VISIOTECH_FILE in .env "
                "or pass --file to sync_now.py."
            )
        rules = settings.load_rules()
        allowed = rules.get("suppliers", {}).get("visiotech", {}).get("allowed_brands", [])
        return VisiotechSource(path=path, allowed_brands=allowed)
    raise ValueError(f"unknown source: {source_name}")


def _is_brand_blocked(brand: Optional[str]) -> bool:
    if not brand:
        return False
    return brand.lower() in settings.brand_blocklist_set


def build_updates(
    records: Iterable[ProductRecord],
    supplier: str,
) -> list[PriceStockUpdate]:
    """Apply pricing + stock-mapping rules to produce Amazon updates."""
    updates: list[PriceStockUpdate] = []
    skipped_blocked = 0
    skipped_invalid = 0
    for rec in records:
        if _is_brand_blocked(rec.brand):
            skipped_blocked += 1
            continue
        try:
            pricing = pricing_engine.calculate_price(cost=rec.cost)
        except ValueError as exc:
            logger.warning("Skipping %s: %s", rec.sku, exc)
            skipped_invalid += 1
            continue
        qty = advertised_quantity(rec.stock, supplier=supplier)
        updates.append(
            PriceStockUpdate(sku=rec.sku, price=pricing.final_price, quantity=qty)
        )
    logger.info(
        "Built %d updates (blocked=%d, invalid=%d)",
        len(updates),
        skipped_blocked,
        skipped_invalid,
    )
    return updates


def run_sync(
    source: str = "csv",
    input_file: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """Run a full sync. Returns a summary dict written to data/reports/.

    dry_run=True (or settings.simulate_mode) builds the feed and saves it locally
    without sending it to Amazon.
    """
    started_at = datetime.utcnow().isoformat() + "Z"
    cat = _build_source(source, input_file)
    records = list(cat.fetch())
    logger.info("Fetched %d records from source=%s", len(records), source)

    updates = build_updates(records, supplier=cat.name)

    summary: dict = {
        "started_at": started_at,
        "source": source,
        "input_file": input_file,
        "records_fetched": len(records),
        "updates_built": len(updates),
        "dry_run": dry_run or settings.simulate_mode,
        "feeds": [],
    }

    if not updates:
        summary["finished_at"] = datetime.utcnow().isoformat() + "Z"
        _write_report(summary)
        return summary

    batches = chunk_updates(updates)
    logger.info("Splitting into %d batch(es)", len(batches))

    if summary["dry_run"]:
        # Save what we WOULD send.
        out_dir = settings.data_dir / "reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        from src.amazon.feeds import build_feed_document  # local import for dry-run only

        for i, batch in enumerate(batches, start=1):
            doc = build_feed_document(batch)
            path = out_dir / f"dryrun_{started_at.replace(':', '-')}_batch_{i}.json"
            path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
            summary["feeds"].append({"batch": i, "size": len(batch), "saved": str(path)})
        summary["finished_at"] = datetime.utcnow().isoformat() + "Z"
        _write_report(summary)
        return summary

    # Real submission, one batch at a time.
    for i, batch in enumerate(batches, start=1):
        try:
            result: FeedResult = submit_feed(batch)
            summary["feeds"].append(
                {
                    "batch": i,
                    "size": len(batch),
                    "feed_id": result.feed_id,
                    "status": result.processing_status,
                    "accepted": result.accepted,
                    "rejected": result.rejected,
                    "issues": result.issues[:50],
                }
            )
        except Exception as exc:
            logger.exception("Batch %d failed", i)
            summary["feeds"].append({"batch": i, "size": len(batch), "error": str(exc)})

    summary["finished_at"] = datetime.utcnow().isoformat() + "Z"
    _write_report(summary)
    return summary


def _write_report(summary: dict) -> Path:
    out_dir = settings.data_dir / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = summary["started_at"].replace(":", "-")
    path = out_dir / f"sync_{stamp}.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Report written: %s", path)
    return path
