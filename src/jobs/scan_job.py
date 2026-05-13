# src/jobs/scan_job.py
"""Populate the local cache DB from the Visiotech XLSX and SP-API.

Two phases:

1. ingest_catalog(): read the XLSX, compute final price + advertised quantity,
   and upsert every Visiotech product into the local products table.

2. scan_matches(): for each product, check our seller account and run the
   matching pipeline against the Amazon catalog. This phase is throttled
   (it calls SP-API per SKU) and resumable - it skips SKUs that already
   have a status of 'listed', 'ean_match' or 'needs_review'.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Optional

from config.settings import settings
from src import db
from src.core.models import ProductRecord
from src.core.pricing import pricing_engine
from src.core.stock_mapping import advertised_quantity
from src.matching.pipeline import MatchOutcome, match_one, persist_outcome
from src.sources.visiotech import VisiotechSource

logger = logging.getLogger(__name__)

# Statuses we do not re-scan unless the user forces it.
_TERMINAL_STATUSES = {"listed", "ean_match", "needs_review", "approved", "created"}


def ingest_catalog(path: Optional[str] = None) -> dict:
    """Read XLSX and upsert all products into the DB. Fast, no API calls."""
    db.init()
    path = path or settings.visiotech_file
    if not path:
        raise ValueError("VISIOTECH_FILE not set and no path provided")

    rules = settings.load_rules()
    allowed = rules.get("suppliers", {}).get("visiotech", {}).get("allowed_brands", [])
    src = VisiotechSource(path=path, allowed_brands=allowed)

    now = datetime.utcnow().isoformat() + "Z"
    count = 0
    for rec in src.fetch():
        try:
            pricing = pricing_engine.calculate_price(cost=rec.cost)
        except ValueError as exc:
            logger.warning("Skipping %s: %s", rec.sku, exc)
            continue
        qty = advertised_quantity(rec.stock, supplier="visiotech")
        db.upsert_product(
            sku=rec.sku,
            ean=rec.ean,
            brand=rec.brand,
            title=rec.title,
            cost=rec.cost,
            final_price=pricing.final_price,
            quantity=qty,
            stock_bucket=(rec.raw or {}).get("stock_bucket"),
            updated_at=now,
        )
        count += 1
    logger.info("Ingested %d products from %s", count, path)
    return {"ingested": count, "source": path}


def scan_matches(
    only_unscanned: bool = True,
    limit: Optional[int] = None,
    progress_cb=None,
) -> dict:
    """Run the matching pipeline for products that don't have a terminal status.

    progress_cb(done, total) is called after each SKU - useful for UI updates.
    """
    db.init()
    # We import the SP-API helpers lazily so unit tests can patch them.
    from src.amazon.listings import is_listed
    from src.amazon.catalog import search_by_ean, search_by_keywords

    rows = db.list_products()
    todo = []
    for r in rows:
        status = r.get("status", "unscanned")
        if only_unscanned and status in _TERMINAL_STATUSES:
            continue
        todo.append(r)
    if limit:
        todo = todo[:limit]

    total = len(todo)
    summary = {"total": total, "listed": 0, "ean_match": 0, "needs_review": 0,
               "no_match": 0, "errors": 0}

    for i, r in enumerate(todo, start=1):
        rec = ProductRecord(
            sku=r["sku"], cost=r["cost"], stock=r["quantity"],
            ean=r["ean"], brand=r["brand"], title=r["title"],
        )
        try:
            outcome: MatchOutcome = match_one(
                rec=rec,
                is_listed=is_listed,
                search_by_ean=search_by_ean,
                search_by_keywords=lambda kw, br, n: search_by_keywords(kw, br, n),
            )
            persist_outcome(rec.sku, outcome)
            summary[outcome.status] = summary.get(outcome.status, 0) + 1
        except Exception as exc:
            logger.exception("scan failed for %s", rec.sku)
            db.set_match(sku=rec.sku, status="error", error_message=str(exc))
            summary["errors"] += 1
        if progress_cb:
            progress_cb(i, total)

    logger.info("scan_matches finished: %s", summary)
    return summary
