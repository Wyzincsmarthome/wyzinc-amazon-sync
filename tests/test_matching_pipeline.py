# tests/test_matching_pipeline.py
"""Tests for the matching pipeline using stubbed SP-API callables."""
from __future__ import annotations

from src.core.models import ProductRecord
from src.matching.pipeline import match_one


def _rec(sku="A", ean="123", brand="AJAX", title="Ajax Hub 2") -> ProductRecord:
    return ProductRecord(sku=sku, cost=50.0, stock=10, ean=ean, brand=brand, title=title)


def test_listed_short_circuits():
    out = match_one(
        _rec(),
        is_listed=lambda s: True,
        search_by_ean=lambda e: (_ for _ in ()).throw(AssertionError("should not call")),
        search_by_keywords=lambda *a: (_ for _ in ()).throw(AssertionError("should not call")),
    )
    assert out.status == "listed"
    assert out.asin is None


def test_ean_match_wins_over_title():
    out = match_one(
        _rec(),
        is_listed=lambda s: False,
        search_by_ean=lambda e: [{"asin": "B0123", "title": "Ajax Hub 2"}],
        search_by_keywords=lambda *a: (_ for _ in ()).throw(AssertionError("should not call")),
    )
    assert out.status == "ean_match"
    assert out.asin == "B0123"
    assert out.matched_ean == "123"


def test_falls_back_to_title_when_ean_returns_nothing():
    candidates = [{"asin": "B0001", "title": "Ajax Hub 2 alarm panel", "brand": "Ajax"}]
    out = match_one(
        _rec(),
        is_listed=lambda s: False,
        search_by_ean=lambda e: [],
        search_by_keywords=lambda kw, br, n: candidates,
    )
    assert out.status == "needs_review"
    assert out.candidates[0]["asin"] == "B0001"
    assert out.candidates[0]["score"] > 0.5


def test_no_ean_no_title():
    out = match_one(
        ProductRecord(sku="X", cost=10, stock=5, ean=None, brand=None, title=None),
        is_listed=lambda s: False,
        search_by_ean=lambda e: [],
        search_by_keywords=lambda *a: [],
    )
    assert out.status == "no_match"


def test_title_match_with_no_results_yields_no_match():
    out = match_one(
        _rec(),
        is_listed=lambda s: False,
        search_by_ean=lambda e: [],
        search_by_keywords=lambda *a: [],
    )
    assert out.status == "no_match"


def test_exception_in_is_listed_is_swallowed():
    out = match_one(
        _rec(),
        is_listed=lambda s: (_ for _ in ()).throw(RuntimeError("boom")),
        search_by_ean=lambda e: [{"asin": "B0X"}],
        search_by_keywords=lambda *a: [],
    )
    # We should NOT crash; we move on to EAN.
    assert out.status == "ean_match"
    assert out.asin == "B0X"
