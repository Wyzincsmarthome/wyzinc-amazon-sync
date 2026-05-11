# src/amazon/feeds.py
"""Build, submit and poll JSON_LISTINGS_FEED submissions.

This is the modern (post-Jul-2025) way to push bulk price + stock updates
to Amazon. XML-based feeds (POST_PRODUCT_PRICING_DATA, POST_INVENTORY_AVAILABILITY_DATA)
are no longer supported.

Flow (see Feeds API v2021-06-30):
    1. createFeedDocument        -> Amazon returns an upload URL + feedDocumentId
    2. PUT the JSON file to that URL
    3. createFeed                -> kicks off processing, returns feedId
    4. poll getFeed until status is DONE / CANCELLED / FATAL
    5. getFeedDocument(resultDocId) -> read processing report
"""
from __future__ import annotations

import json
import logging
import time
from typing import Iterable, Sequence

import requests

from config.settings import settings
from src.core.models import FeedResult, PriceStockUpdate

logger = logging.getLogger(__name__)


FEED_TYPE = "JSON_LISTINGS_FEED"
CONTENT_TYPE = "application/json; charset=UTF-8"

# Amazon caps a feed at 25 000 items (as of May 2025).
MAX_MESSAGES_PER_FEED = 25_000

# Terminal statuses returned by getFeed.
_TERMINAL_STATUSES = {"DONE", "CANCELLED", "FATAL"}


def build_feed_document(
    updates: Sequence[PriceStockUpdate],
    seller_id: str | None = None,
    marketplace_id: str | None = None,
) -> dict:
    """Build the JSON body for a JSON_LISTINGS_FEED (v2 schema).

    Each update becomes a PATCH message targeting two attributes:
    /attributes/purchasable_offer (price) and /attributes/fulfillment_availability
    (quantity). productType is set to PRODUCT, which is accepted for offer/inventory
    updates regardless of the item's real product type.
    """
    seller_id = seller_id or settings.seller_id
    marketplace_id = marketplace_id or settings.marketplace_id
    if not seller_id:
        raise ValueError("seller_id is required (set SELLER_ID in .env)")

    messages = []
    for idx, upd in enumerate(updates, start=1):
        messages.append(
            {
                "messageId": idx,
                "sku": upd.sku,
                "operationType": "PATCH",
                "productType": "PRODUCT",
                "patches": [
                    {
                        "op": "replace",
                        "path": "/attributes/purchasable_offer",
                        "value": [
                            {
                                "marketplace_id": marketplace_id,
                                "currency": "EUR",
                                "our_price": [
                                    {"schedule": [{"value_with_tax": round(upd.price, 2)}]}
                                ],
                            }
                        ],
                    },
                    {
                        "op": "replace",
                        "path": "/attributes/fulfillment_availability",
                        "value": [
                            {
                                "fulfillment_channel_code": "DEFAULT",
                                "quantity": int(upd.quantity),
                            }
                        ],
                    },
                ],
            }
        )

    return {
        "header": {
            "sellerId": seller_id,
            "version": "2.0",
            "issueLocale": "en_US",
        },
        "messages": messages,
    }


def chunk_updates(
    updates: Iterable[PriceStockUpdate],
    chunk_size: int = MAX_MESSAGES_PER_FEED,
) -> list[list[PriceStockUpdate]]:
    """Split a long list into Amazon-sized batches."""
    updates = list(updates)
    return [updates[i : i + chunk_size] for i in range(0, len(updates), chunk_size)]


def submit_feed(
    updates: Sequence[PriceStockUpdate],
    poll_interval_seconds: int = 30,
    poll_timeout_seconds: int = 30 * 60,
) -> FeedResult:
    """Submit a single feed and wait for the result.

    Raises if the feed reaches a terminal failure or the poll times out.
    """
    if not updates:
        raise ValueError("no updates to submit")
    if len(updates) > MAX_MESSAGES_PER_FEED:
        raise ValueError(
            f"feed exceeds Amazon limit ({len(updates)} > {MAX_MESSAGES_PER_FEED}); "
            "use chunk_updates() before calling submit_feed()"
        )

    # Imported lazily so unit tests can exercise the builder without the
    # SP-API SDK installed.
    from src.amazon.client import get_feeds_client

    feeds = get_feeds_client()
    payload = build_feed_document(updates)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    # 1. Reserve an upload slot.
    create_doc_resp = feeds.create_feed_document(content_type=CONTENT_TYPE)
    feed_document_id = create_doc_resp.payload["feedDocumentId"]
    upload_url = create_doc_resp.payload["url"]

    # 2. Upload the actual JSON body.
    put_resp = requests.put(upload_url, data=body, headers={"Content-Type": CONTENT_TYPE}, timeout=120)
    put_resp.raise_for_status()

    # 3. Kick off processing.
    create_feed_resp = feeds.create_feed(
        feedType=FEED_TYPE,
        marketplaceIds=[settings.marketplace_id],
        inputFeedDocumentId=feed_document_id,
    )
    feed_id = create_feed_resp.payload["feedId"]
    logger.info("Feed submitted feed_id=%s items=%d", feed_id, len(updates))

    # 4. Poll until terminal.
    deadline = time.time() + poll_timeout_seconds
    status = "IN_PROGRESS"
    result_document_id: str | None = None
    while time.time() < deadline:
        time.sleep(poll_interval_seconds)
        feed_info = feeds.get_feed(feed_id).payload
        status = feed_info.get("processingStatus", "IN_PROGRESS")
        logger.info("Feed %s status=%s", feed_id, status)
        if status in _TERMINAL_STATUSES:
            result_document_id = feed_info.get("resultFeedDocumentId")
            break
    else:
        raise TimeoutError(f"feed {feed_id} did not finish within {poll_timeout_seconds}s")

    # 5. Fetch the processing report (if any).
    report: dict | None = None
    accepted = rejected = 0
    issues: list[dict] = []
    if result_document_id:
        doc = feeds.get_feed_document(result_document_id).payload
        report_url = doc.get("url")
        if report_url:
            r = requests.get(report_url, timeout=60)
            r.raise_for_status()
            try:
                report = r.json()
            except ValueError:
                logger.warning("Feed %s result is not JSON, keeping raw text", feed_id)
                report = {"raw": r.text}
            accepted, rejected, issues = _summarise_report(report)

    return FeedResult(
        feed_id=feed_id,
        processing_status=status,
        accepted=accepted,
        rejected=rejected,
        issues=issues,
        raw_report=report,
    )


def _summarise_report(report: dict) -> tuple[int, int, list[dict]]:
    """Extract counts and issues from a JSON_LISTINGS_FEED processing report."""
    if not isinstance(report, dict):
        return 0, 0, []
    summary = report.get("summary", {})
    accepted = int(summary.get("messagesAccepted", 0) or 0)
    rejected = int(summary.get("messagesInvalid", 0) or 0)
    issues = []
    for issue in report.get("issues", []) or []:
        issues.append(
            {
                "messageId": issue.get("messageId"),
                "sku": issue.get("sku"),
                "code": issue.get("code"),
                "severity": issue.get("severity"),
                "message": issue.get("message"),
            }
        )
    return accepted, rejected, issues
