# src/amazon/catalog.py
"""Search the Amazon catalog by EAN or keywords.

Wraps SP-API CatalogItems v2022-04-01 search_catalog_items.
Returns lightweight dicts so the UI never sees raw SDK objects.
"""
from __future__ import annotations

import logging
import time
from typing import Iterable, Optional

from config.settings import settings

logger = logging.getLogger(__name__)

_THROTTLE_SECONDS = 0.6  # CatalogItems search has 2 rps; stay well under that.


def _normalize_item(item: dict) -> dict:
    """Pick the fields we care about from a CatalogItems search hit."""
    asin = item.get("asin")
    summaries = item.get("summaries") or []
    summary = summaries[0] if summaries else {}
    images = item.get("images") or []
    image_list = images[0].get("images") if images else []
    image_url = image_list[0]["link"] if image_list else None

    identifiers = item.get("identifiers") or []
    eans: list[str] = []
    for marketplace_ids in identifiers:
        for ident in marketplace_ids.get("identifiers", []):
            if ident.get("identifierType") in ("EAN", "GTIN", "UPC"):
                eans.append(str(ident["identifier"]))

    return {
        "asin": asin,
        "title": summary.get("itemName"),
        "brand": summary.get("brand"),
        "image_url": image_url,
        "eans": eans,
    }


def search_by_ean(ean: str) -> list[dict]:
    """Look up an EAN in the Amazon catalog. Returns 0+ hits."""
    from src.amazon.client import get_catalog_client

    if not ean:
        return []
    client = get_catalog_client()
    time.sleep(_THROTTLE_SECONDS)
    resp = client.search_catalog_items(
        marketplaceIds=[settings.marketplace_id],
        identifiers=ean,
        identifiersType="EAN",
        includedData=["identifiers", "summaries", "images"],
    )
    items = (resp.payload or {}).get("items") or []
    return [_normalize_item(i) for i in items]


def search_by_keywords(keywords: str, brand: Optional[str] = None, limit: int = 10) -> list[dict]:
    """Title/keyword search, optionally narrowed by brand."""
    from src.amazon.client import get_catalog_client

    if not keywords:
        return []
    client = get_catalog_client()
    time.sleep(_THROTTLE_SECONDS)
    kwargs = dict(
        marketplaceIds=[settings.marketplace_id],
        keywords=keywords,
        includedData=["identifiers", "summaries", "images"],
        pageSize=limit,
    )
    if brand:
        kwargs["brandNames"] = brand
    resp = client.search_catalog_items(**kwargs)
    items = (resp.payload or {}).get("items") or []
    return [_normalize_item(i) for i in items]
