# src/db.py
"""Tiny SQLite layer for the local dashboard.

Three tables:

products
    One row per Visiotech SKU we have parsed. Holds cost, advertised
    quantity, EAN, brand, title and the computed Amazon price.

matches
    The outcome of looking each SKU up against the seller's account and
    the Amazon catalog. status is one of:
        listed       - SKU already exists in our Seller Central
        ean_match    - found ASIN in Amazon catalog with matching EAN
        needs_review - has candidates from a title search, needs manual pick
        no_match     - nothing useful found
        approved     - user approved creation, queued to send
        created      - listing successfully created on Amazon
        failed       - send to Amazon failed (see error_message)

match_candidates
    For needs_review status, the ASIN candidates returned by a title
    search. The user picks one and we move the match to approved.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from config.settings import settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    sku           TEXT PRIMARY KEY,
    ean           TEXT,
    brand         TEXT,
    title         TEXT,
    cost          REAL NOT NULL,
    final_price   REAL NOT NULL,
    quantity      INTEGER NOT NULL,
    stock_bucket  TEXT,
    updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_products_ean ON products(ean);

CREATE TABLE IF NOT EXISTS matches (
    sku             TEXT PRIMARY KEY,
    status          TEXT NOT NULL,
    asin            TEXT,
    matched_ean     TEXT,
    matched_title   TEXT,
    confidence      REAL,
    error_message   TEXT,
    feed_id         TEXT,
    updated_at      TEXT NOT NULL,
    FOREIGN KEY (sku) REFERENCES products(sku)
);

CREATE INDEX IF NOT EXISTS ix_matches_status ON matches(status);

CREATE TABLE IF NOT EXISTS match_candidates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sku         TEXT NOT NULL,
    asin        TEXT NOT NULL,
    title       TEXT,
    brand       TEXT,
    image_url   TEXT,
    score       REAL,
    FOREIGN KEY (sku) REFERENCES products(sku)
);

CREATE INDEX IF NOT EXISTS ix_candidates_sku ON match_candidates(sku);
"""


def _db_path() -> Path:
    path = settings.data_dir / "cache.db"
    return path


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(_db_path(), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def init() -> None:
    """Create tables if they don't exist."""
    with connect() as conn:
        conn.executescript(SCHEMA)


# --- products -----------------------------------------------------------------

def upsert_product(
    sku: str,
    ean: Optional[str],
    brand: Optional[str],
    title: Optional[str],
    cost: float,
    final_price: float,
    quantity: int,
    stock_bucket: Optional[str],
    updated_at: str,
) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO products
                (sku, ean, brand, title, cost, final_price, quantity, stock_bucket, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(sku) DO UPDATE SET
                    ean=excluded.ean, brand=excluded.brand, title=excluded.title,
                    cost=excluded.cost, final_price=excluded.final_price,
                    quantity=excluded.quantity, stock_bucket=excluded.stock_bucket,
                    updated_at=excluded.updated_at""",
            (sku, ean, brand, title, cost, final_price, quantity, stock_bucket, updated_at),
        )


def list_products(status_filter: Optional[str] = None, search: Optional[str] = None) -> list[dict]:
    """Join products + matches for the dashboard."""
    sql = """SELECT p.sku, p.ean, p.brand, p.title, p.cost, p.final_price,
                    p.quantity, p.stock_bucket,
                    COALESCE(m.status, 'unscanned') AS status,
                    m.asin, m.matched_ean, m.matched_title, m.confidence,
                    m.error_message, m.feed_id
             FROM products p
             LEFT JOIN matches m ON m.sku = p.sku"""
    where = []
    params: list = []
    if status_filter and status_filter != "all":
        where.append("COALESCE(m.status,'unscanned') = ?")
        params.append(status_filter)
    if search:
        where.append("(p.sku LIKE ? OR p.ean LIKE ? OR p.title LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like, like])
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY p.sku"
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def status_counts() -> dict[str, int]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT COALESCE(m.status,'unscanned') AS s, COUNT(*) AS c
               FROM products p LEFT JOIN matches m ON m.sku = p.sku
               GROUP BY s"""
        ).fetchall()
    return {r["s"]: r["c"] for r in rows}


# --- matches ------------------------------------------------------------------

def set_match(
    sku: str,
    status: str,
    asin: Optional[str] = None,
    matched_ean: Optional[str] = None,
    matched_title: Optional[str] = None,
    confidence: Optional[float] = None,
    error_message: Optional[str] = None,
    feed_id: Optional[str] = None,
    updated_at: Optional[str] = None,
) -> None:
    from datetime import datetime
    updated_at = updated_at or datetime.utcnow().isoformat() + "Z"
    with connect() as conn:
        conn.execute(
            """INSERT INTO matches
                (sku, status, asin, matched_ean, matched_title, confidence,
                 error_message, feed_id, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(sku) DO UPDATE SET
                    status=excluded.status, asin=excluded.asin,
                    matched_ean=excluded.matched_ean, matched_title=excluded.matched_title,
                    confidence=excluded.confidence, error_message=excluded.error_message,
                    feed_id=excluded.feed_id, updated_at=excluded.updated_at""",
            (sku, status, asin, matched_ean, matched_title, confidence,
             error_message, feed_id, updated_at),
        )


def get_match(sku: str) -> Optional[dict]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM matches WHERE sku = ?", (sku,)).fetchone()
        return dict(row) if row else None


def list_by_status(statuses: list[str]) -> list[dict]:
    if not statuses:
        return []
    placeholders = ",".join("?" * len(statuses))
    sql = (
        f"SELECT p.*, m.status, m.asin, m.matched_ean FROM products p "
        f"JOIN matches m ON m.sku = p.sku WHERE m.status IN ({placeholders})"
    )
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, statuses).fetchall()]


# --- candidates ---------------------------------------------------------------

def replace_candidates(sku: str, candidates: list[dict]) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM match_candidates WHERE sku = ?", (sku,))
        for c in candidates:
            conn.execute(
                """INSERT INTO match_candidates (sku, asin, title, brand, image_url, score)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (sku, c["asin"], c.get("title"), c.get("brand"),
                 c.get("image_url"), c.get("score")),
            )


def get_candidates(sku: str) -> list[dict]:
    with connect() as conn:
        return [
            dict(r) for r in conn.execute(
                "SELECT * FROM match_candidates WHERE sku = ? ORDER BY score DESC", (sku,)
            ).fetchall()
        ]
