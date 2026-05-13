# src/jobs/create_job.py
"""Create Amazon listings for SKUs that the user has approved."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterable

from src import db
from src.amazon.listings import create_listing_for_asin

logger = logging.getLogger(__name__)


def approve(sku: str, asin: str) -> None:
    """Mark a SKU as approved and lock in the ASIN we'll list against."""
    p = db.get_match(sku) or {}
    db.set_match(
        sku=sku,
        status="approved",
        asin=asin,
        matched_ean=p.get("matched_ean"),
        matched_title=p.get("matched_title"),
        confidence=p.get("confidence"),
    )


def skip(sku: str) -> None:
    db.set_match(sku=sku, status="skipped")


def send_approved(only_skus: Iterable[str] | None = None) -> dict:
    """For every approved SKU, call putListingsItem against the chosen ASIN."""
    approved = db.list_by_status(["approved"])
    if only_skus is not None:
        wanted = set(only_skus)
        approved = [r for r in approved if r["sku"] in wanted]

    created = 0
    failed = 0
    issues: list[dict] = []
    for r in approved:
        sku = r["sku"]
        asin = r["asin"]
        price = r["final_price"]
        qty = r["quantity"]
        if not asin:
            db.set_match(sku=sku, status="failed", error_message="missing ASIN")
            failed += 1
            continue
        try:
            payload = create_listing_for_asin(sku=sku, asin=asin, price=price, quantity=qty)
            sub_id = payload.get("submissionId") if isinstance(payload, dict) else None
            db.set_match(
                sku=sku,
                status="created",
                asin=asin,
                feed_id=sub_id,
            )
            created += 1
        except Exception as exc:
            logger.exception("Create failed for %s", sku)
            db.set_match(sku=sku, status="failed", asin=asin, error_message=str(exc))
            issues.append({"sku": sku, "error": str(exc)})
            failed += 1

    return {
        "attempted": len(approved),
        "created": created,
        "failed": failed,
        "issues": issues,
        "finished_at": datetime.utcnow().isoformat() + "Z",
    }
