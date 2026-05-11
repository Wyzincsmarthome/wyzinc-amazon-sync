# tests/test_visiotech_source.py
"""Unit tests for the Visiotech XLSX parser."""
from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from src.sources.visiotech import (
    COL_BRAND,
    COL_COST,
    COL_EAN,
    COL_SKU,
    COL_STOCK_BUCKET,
    COL_TITLE,
    STOCK_BUCKET_QTY,
    VisiotechSource,
)


def _make_xlsx(tmp_path: Path, rows: list[dict]) -> Path:
    """Create a minimal fixture XLSX matching Visiotech's positional layout."""
    wb = openpyxl.Workbook()
    sh = wb.active
    sh.title = "in"
    # Total 25 columns in the real file - we leave the unused ones empty.
    for r in rows:
        row = [None] * 25
        row[COL_SKU - 1] = r.get("sku")
        row[COL_STOCK_BUCKET - 1] = r.get("stock")
        row[COL_BRAND - 1] = r.get("brand")
        row[COL_TITLE - 1] = r.get("title")
        row[COL_COST - 1] = r.get("cost")
        row[COL_EAN - 1] = r.get("ean")
        sh.append(row)
    path = tmp_path / "visiotech.xlsx"
    wb.save(path)
    return path


def test_parses_a_normal_row(tmp_path):
    path = _make_xlsx(
        tmp_path,
        [{"sku": "AJ-001", "brand": "AJAX", "cost": 50.0, "stock": "high",
          "ean": "1234567890123", "title": "Test"}],
    )
    records = list(VisiotechSource(path=path, allowed_brands=["Ajax"]).fetch())
    assert len(records) == 1
    r = records[0]
    assert r.sku == "AJ-001"
    assert r.cost == 50.0
    assert r.stock == 10  # high
    assert r.ean == "1234567890123"
    assert r.brand == "AJAX"


@pytest.mark.parametrize(
    "stock_text,expected_qty",
    [("high", 10), ("medium", 5), ("low", 1), ("none", 0), ("HIGH", 10)],
)
def test_stock_bucket_mapping(tmp_path, stock_text, expected_qty):
    path = _make_xlsx(
        tmp_path,
        [{"sku": "X", "brand": "AJAX", "cost": 10.0, "stock": stock_text}],
    )
    records = list(VisiotechSource(path=path, allowed_brands=["Ajax"]).fetch())
    assert len(records) == 1
    assert records[0].stock == expected_qty


def test_brand_allowlist_filters(tmp_path):
    path = _make_xlsx(
        tmp_path,
        [
            {"sku": "A", "brand": "AJAX", "cost": 10.0, "stock": "high"},
            {"sku": "B", "brand": "HIKVISION", "cost": 10.0, "stock": "high"},
            {"sku": "C", "brand": "AQARA", "cost": 10.0, "stock": "high"},
        ],
    )
    records = list(
        VisiotechSource(path=path, allowed_brands=["Ajax", "Aqara"]).fetch()
    )
    assert [r.sku for r in records] == ["A", "C"]


def test_empty_allowlist_keeps_everything(tmp_path):
    path = _make_xlsx(
        tmp_path,
        [
            {"sku": "A", "brand": "AJAX", "cost": 10.0, "stock": "high"},
            {"sku": "B", "brand": "WHATEVER", "cost": 10.0, "stock": "high"},
        ],
    )
    records = list(VisiotechSource(path=path).fetch())
    assert {r.sku for r in records} == {"A", "B"}


def test_zero_or_missing_cost_is_skipped(tmp_path):
    path = _make_xlsx(
        tmp_path,
        [
            {"sku": "A", "brand": "AJAX", "cost": 0.0, "stock": "high"},
            {"sku": "B", "brand": "AJAX", "cost": None, "stock": "high"},
            {"sku": "C", "brand": "AJAX", "cost": 5.0, "stock": "high"},
        ],
    )
    records = list(VisiotechSource(path=path, allowed_brands=["Ajax"]).fetch())
    assert [r.sku for r in records] == ["C"]


def test_unknown_stock_bucket_is_skipped(tmp_path):
    path = _make_xlsx(
        tmp_path,
        [
            {"sku": "A", "brand": "AJAX", "cost": 10.0, "stock": "weird"},
            {"sku": "B", "brand": "AJAX", "cost": 10.0, "stock": "high"},
        ],
    )
    records = list(VisiotechSource(path=path, allowed_brands=["Ajax"]).fetch())
    assert [r.sku for r in records] == ["B"]


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        VisiotechSource(path="/tmp/does-not-exist.xlsx")


def test_bucket_constants():
    # Lock the agreed mapping so a careless edit would fail a test.
    assert STOCK_BUCKET_QTY == {"high": 10, "medium": 5, "low": 1, "none": 0}
