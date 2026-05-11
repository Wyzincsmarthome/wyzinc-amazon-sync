# src/core/stock_mapping.py
"""Translate the supplier's real stock count into the quantity we advertise on Amazon.

The mapping comes from config/rules.json (suppliers.<name>.stock_mapping) so it
can be tuned per supplier without code changes.
"""
from __future__ import annotations

from config.settings import settings


_DEFAULT_MAPPING = {"0": 0, "<2": 1, "<10": 5, ">10": 10}


def _load_mapping(supplier: str) -> dict[str, int]:
    rules = settings.load_rules()
    supplier_rules = rules.get("suppliers", {}).get(supplier, {})
    mapping = supplier_rules.get("stock_mapping")
    if not mapping:
        return _DEFAULT_MAPPING
    return {k: int(v) for k, v in mapping.items()}


def advertised_quantity(real_stock: int, supplier: str = "suprides") -> int:
    """Apply the supplier-specific stock mapping.

    Buckets supported in rules.json: "0", "<2", "<10", ">10".
    """
    mapping = _load_mapping(supplier)
    if real_stock <= 0:
        return mapping.get("0", 0)
    if real_stock < 2:
        return mapping.get("<2", 1)
    if real_stock < 10:
        return mapping.get("<10", 5)
    return mapping.get(">10", 10)
