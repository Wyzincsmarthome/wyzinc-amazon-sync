# src/amazon/listings.py
"""Listings Items API helpers: check if a SKU exists and create new listings."""
from __future__ import annotations

import logging
import time
from typing import Optional

from sp_api.base.exceptions import SellingApiException

from config.settings import settings

logger = logging.getLogger(__name__)

_THROTTLE_SECONDS = 0.25  # get/put are 5 rps each; stay safe.


def is_listed(sku: str) -> bool:
    """Return True if this SKU is already on our Seller Central account."""
    from src.amazon.client import get_listings_client

    if not settings.seller_id:
        raise ValueError("SELLER_ID is not configured")
    client = get_listings_client()
    time.sleep(_THROTTLE_SECONDS)
    try:
        resp = client.get_listings_item(
            sellerId=settings.seller_id,
            sku=sku,
            marketplaceIds=[settings.marketplace_id],
        )
        return bool(resp.payload)
    except SellingApiException as exc:
        # SDK raises on 404. Anything else we re-raise so callers see real issues.
        msg = str(exc).lower()
        if "not found" in msg or "404" in msg or "no listings" in msg:
            return False
        raise


def create_listing_for_asin(
    sku: str,
    asin: str,
    price: float,
    quantity: int,
    condition: str = "new_new",
) -> dict:
    """Create a listing on our account against an existing Amazon ASIN.

    We use the minimal PRODUCT type and merchant_suggested_asin to attach
    the offer to the existing catalog entry instead of creating a new one.
    Returns the SDK response payload (includes submissionId and any issues).
    """
    from src.amazon.client import get_listings_client

    if not settings.seller_id:
        raise ValueError("SELLER_ID is not configured")

    body = {
        "productType": "PRODUCT",
        "requirements": "LISTING_OFFER_ONLY",
        "attributes": {
            "merchant_suggested_asin": [
                {"value": asin, "marketplace_id": settings.marketplace_id}
            ],
            "condition_type": [
                {"value": condition, "marketplace_id": settings.marketplace_id}
            ],
            "purchasable_offer": [
                {
                    "marketplace_id": settings.marketplace_id,
                    "currency": "EUR",
                    "our_price": [
                        {"schedule": [{"value_with_tax": round(float(price), 2)}]}
                    ],
                }
            ],
            "fulfillment_availability": [
                {
                    "fulfillment_channel_code": "DEFAULT",
                    "quantity": int(quantity),
                }
            ],
        },
    }

    client = get_listings_client()
    time.sleep(_THROTTLE_SECONDS)
    resp = client.put_listings_item(
        sellerId=settings.seller_id,
        sku=sku,
        marketplaceIds=[settings.marketplace_id],
        body=body,
    )
    return resp.payload or {}
