# src/sources/csv_loader.py
"""Load products from a CSV or JSON file dropped in data/inputs/.

Expected CSV columns (case-insensitive headers):
    sku, cost, stock, ean (optional), brand (optional), title (optional)

Expected JSON: an array of objects with the same keys.
"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Iterable

from src.core.models import ProductRecord
from src.sources.base import CatalogSource

logger = logging.getLogger(__name__)


_REQUIRED = {"sku", "cost", "stock"}


class CsvJsonSource(CatalogSource):
    name = "csv"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"Input file not found: {self.path}")

    def fetch(self) -> Iterable[ProductRecord]:
        suffix = self.path.suffix.lower()
        if suffix == ".csv":
            yield from self._read_csv()
        elif suffix == ".json":
            yield from self._read_json()
        else:
            raise ValueError(f"Unsupported file type: {suffix}")

    def _read_csv(self) -> Iterable[ProductRecord]:
        with self.path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return
            headers = {h.lower().strip(): h for h in reader.fieldnames}
            missing = _REQUIRED - set(headers)
            if missing:
                raise ValueError(f"CSV missing required columns: {sorted(missing)}")
            for row_num, row in enumerate(reader, start=2):
                try:
                    yield _to_record({k: row[v] for k, v in headers.items()})
                except (ValueError, KeyError) as exc:
                    logger.warning("Skipping CSV row %d: %s", row_num, exc)

    def _read_json(self) -> Iterable[ProductRecord]:
        with self.path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, list):
            raise ValueError("JSON input must be an array of product objects")
        for idx, item in enumerate(payload):
            try:
                normalized = {k.lower(): v for k, v in item.items()}
                yield _to_record(normalized)
            except (ValueError, KeyError) as exc:
                logger.warning("Skipping JSON item %d: %s", idx, exc)


def _to_record(row: dict) -> ProductRecord:
    sku = str(row["sku"]).strip()
    if not sku:
        raise ValueError("empty SKU")
    return ProductRecord(
        sku=sku,
        cost=float(row["cost"]),
        stock=int(float(row["stock"])),
        ean=(str(row["ean"]).strip() or None) if row.get("ean") else None,
        brand=(str(row["brand"]).strip() or None) if row.get("brand") else None,
        title=(str(row["title"]).strip() or None) if row.get("title") else None,
        raw=dict(row),
    )
