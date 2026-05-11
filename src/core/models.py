# src/core/models.py
"""Shared data structures used across sources, pricing and Amazon feeds."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ProductRecord:
    """One product line coming out of a supplier source.

    sku        - The seller SKU on Amazon (must match what's in Seller Central).
    cost       - Supplier cost in EUR (net, before VAT).
    stock      - Real units available at the supplier right now.
    ean        - Optional barcode, used later for matching when creating items.
    brand      - Optional brand name (used to filter via blocklist/allowlist).
    title      - Optional product title (used only when creating new listings).
    raw        - Original payload from the source, kept for debugging.
    """

    sku: str
    cost: float
    stock: int
    ean: Optional[str] = None
    brand: Optional[str] = None
    title: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PriceStockUpdate:
    """A single update we want to push to Amazon for an existing SKU."""

    sku: str
    price: float
    quantity: int


@dataclass
class FeedResult:
    """Outcome of a JSON_LISTINGS_FEED submission."""

    feed_id: str
    processing_status: str  # e.g. DONE, FATAL, IN_PROGRESS
    accepted: int = 0
    rejected: int = 0
    issues: list[dict] = field(default_factory=list)
    raw_report: Optional[dict] = None
