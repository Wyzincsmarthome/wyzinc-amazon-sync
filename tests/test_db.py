# tests/test_db.py
"""SQLite layer smoke tests using a temp DB."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _tmp_db(tmp_path, monkeypatch):
    """Redirect settings.data_dir so cache.db lands in tmp_path."""
    from config import settings as settings_module

    class FakeProp:
        def __get__(self, obj, objtype=None):
            return tmp_path

    monkeypatch.setattr(type(settings_module.settings), "data_dir", FakeProp())
    # also ensure module-level singleton uses it
    monkeypatch.setattr(settings_module.settings.__class__, "data_dir", FakeProp())
    yield


def test_init_creates_tables():
    from src import db

    db.init()
    with db.connect() as c:
        tables = {r["name"] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    assert {"products", "matches", "match_candidates"}.issubset(tables)


def test_upsert_and_list():
    from src import db

    db.init()
    db.upsert_product("SKU-1", "1234567890123", "AJAX", "Test", 50.0, 89.99, 10, "high",
                      datetime.utcnow().isoformat() + "Z")
    rows = db.list_products()
    assert len(rows) == 1
    assert rows[0]["sku"] == "SKU-1"
    assert rows[0]["final_price"] == 89.99
    assert rows[0]["status"] == "unscanned"


def test_set_match_and_status_counts():
    from src import db

    db.init()
    now = datetime.utcnow().isoformat() + "Z"
    db.upsert_product("A", "1", "AJAX", "x", 10, 20, 10, "high", now)
    db.upsert_product("B", "2", "AJAX", "y", 10, 20, 10, "high", now)
    db.set_match("A", "ean_match", asin="B001")
    counts = db.status_counts()
    assert counts.get("ean_match") == 1
    assert counts.get("unscanned") == 1


def test_replace_candidates():
    from src import db

    db.init()
    now = datetime.utcnow().isoformat() + "Z"
    db.upsert_product("A", None, "AJAX", "x", 10, 20, 10, "high", now)
    db.replace_candidates("A", [
        {"asin": "B1", "title": "t1", "brand": "AJAX", "image_url": None, "score": 0.9},
        {"asin": "B2", "title": "t2", "brand": "AJAX", "image_url": None, "score": 0.7},
    ])
    cands = db.get_candidates("A")
    assert [c["asin"] for c in cands] == ["B1", "B2"]


def test_list_by_status_filters():
    from src import db

    db.init()
    now = datetime.utcnow().isoformat() + "Z"
    db.upsert_product("A", None, "AJAX", "x", 10, 20, 10, "high", now)
    db.upsert_product("B", None, "AJAX", "y", 10, 20, 10, "high", now)
    db.set_match("A", "approved", asin="B001")
    db.set_match("B", "needs_review")
    rows = db.list_by_status(["approved"])
    assert [r["sku"] for r in rows] == ["A"]
