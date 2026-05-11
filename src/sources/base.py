# src/sources/base.py
"""Common interface every supplier/source must implement."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from src.core.models import ProductRecord


class CatalogSource(ABC):
    """A source of products with cost and stock.

    Implementations: csv_loader.CsvJsonSource, visiotech.VisiotechSource, ...
    """

    name: str = "base"

    @abstractmethod
    def fetch(self) -> Iterable[ProductRecord]:
        """Return all available products as ProductRecord items."""
        raise NotImplementedError
