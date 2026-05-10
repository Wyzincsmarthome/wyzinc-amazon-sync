# src/sources/visiotech.py
"""Visiotech supplier source.

Stub implementation: returns an empty catalog and logs a hint. Replace the
fetch() body once you have the real Visiotech API credentials and endpoint.
The expected shape per item is ProductRecord (see src/core/models.py).
"""
from __future__ import annotations

import logging
from typing import Iterable

from src.core.models import ProductRecord
from src.sources.base import CatalogSource

logger = logging.getLogger(__name__)


class VisiotechSource(CatalogSource):
    name = "visiotech"

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        allowed_brands: list[str] | None = None,
    ) -> None:
        self.base_url = base_url
        self.token = token
        self.allowed_brands = {b.lower() for b in (allowed_brands or [])}

    def fetch(self) -> Iterable[ProductRecord]:
        if not self.base_url or not self.token:
            logger.warning(
                "VisiotechSource not configured (missing base_url or token). "
                "Add credentials and implement the HTTP call. Returning empty catalog."
            )
            return iter([])
        # TODO: implement actual Visiotech HTTP integration.
        # Filter by self.allowed_brands when present.
        return iter([])
