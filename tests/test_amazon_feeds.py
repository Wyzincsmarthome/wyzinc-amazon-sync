# tests/test_amazon_feeds.py
"""Unit tests for the JSON_LISTINGS_FEED builder and the sync transformation."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("SELLER_ID", "TESTSELLER")
os.environ.setdefault("MARKETPLACE_ID", "A1RKKUPIHCS9HS")

from src.amazon.feeds import (  # noqa: E402
    MAX_MESSAGES_PER_FEED,
    build_feed_document,
    chunk_updates,
)
from src.core.models import PriceStockUpdate, ProductRecord  # noqa: E402
from src.jobs.sync_job import build_updates  # noqa: E402


def test_build_feed_document_header():
    updates = [PriceStockUpdate(sku="SKU-1", price=19.99, quantity=5)]
    feed = build_feed_document(updates, seller_id="ABC", marketplace_id="A1RKKUPIHCS9HS")

    assert feed["header"]["sellerId"] == "ABC"
    assert feed["header"]["version"] == "2.0"
    assert len(feed["messages"]) == 1


def test_build_feed_document_message_shape():
    updates = [PriceStockUpdate(sku="SKU-1", price=19.99, quantity=5)]
    feed = build_feed_document(updates, seller_id="ABC", marketplace_id="A1RKKUPIHCS9HS")
    msg = feed["messages"][0]

    assert msg["sku"] == "SKU-1"
    assert msg["operationType"] == "PATCH"
    assert msg["productType"] == "PRODUCT"
    assert len(msg["patches"]) == 2

    price_patch = msg["patches"][0]
    assert price_patch["path"] == "/attributes/purchasable_offer"
    value = price_patch["value"][0]
    assert value["currency"] == "EUR"
    assert value["marketplace_id"] == "A1RKKUPIHCS9HS"
    assert value["our_price"][0]["schedule"][0]["value_with_tax"] == 19.99

    stock_patch = msg["patches"][1]
    assert stock_patch["path"] == "/attributes/fulfillment_availability"
    assert stock_patch["value"][0]["fulfillment_channel_code"] == "DEFAULT"
    assert stock_patch["value"][0]["quantity"] == 5


def test_build_feed_document_requires_seller_id(monkeypatch):
    from config import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "seller_id", "")
    with pytest.raises(ValueError, match="seller_id is required"):
        build_feed_document([PriceStockUpdate("X", 1.0, 1)], seller_id="")


def test_chunk_updates_respects_amazon_limit():
    updates = [PriceStockUpdate(f"SKU-{i}", 10.0, 1) for i in range(MAX_MESSAGES_PER_FEED + 5)]
    batches = chunk_updates(updates)
    assert len(batches) == 2
    assert len(batches[0]) == MAX_MESSAGES_PER_FEED
    assert len(batches[1]) == 5


def test_build_updates_skips_blocked_brand(monkeypatch):
    from config import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "brand_blocklist", "Apple")
    records = [
        ProductRecord(sku="A", cost=10.0, stock=5, brand="Apple"),
        ProductRecord(sku="B", cost=10.0, stock=5, brand="Ajax"),
    ]
    updates = build_updates(records, supplier="suprides")
    assert [u.sku for u in updates] == ["B"]


def test_build_updates_applies_stock_mapping():
    records = [
        ProductRecord(sku="ZERO", cost=10.0, stock=0),
        ProductRecord(sku="LOW", cost=10.0, stock=1),
        ProductRecord(sku="MID", cost=10.0, stock=5),
        ProductRecord(sku="HIGH", cost=10.0, stock=50),
    ]
    updates = {u.sku: u.quantity for u in build_updates(records, supplier="suprides")}
    assert updates["ZERO"] == 0
    assert updates["LOW"] == 1
    assert updates["MID"] == 5
    assert updates["HIGH"] == 10


def test_build_updates_skips_invalid_cost():
    records = [
        ProductRecord(sku="OK", cost=10.0, stock=5),
        ProductRecord(sku="BAD", cost=0.0, stock=5),
    ]
    updates = build_updates(records, supplier="suprides")
    assert [u.sku for u in updates] == ["OK"]
