# src/matching/pipeline.py
"""Find each Visiotech SKU on Amazon.

For one SKU the steps are, in order:

1. is_listed(sku) -> True  => status='listed' (nothing more to do)
2. search_by_ean(ean)      -> 1 hit  => status='ean_match' on that ASIN
                              0/many => fall through
3. search_by_keywords(title, brand) -> store hits as candidates
                                       => status='needs_review' (or no_match)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable, Optional

from src import db
from src.core.models import ProductRecord

logger = logging.getLogger(__name__)


@dataclass
class MatchOutcome:
    status: str
    asin: Optional[str] = None
    matched_ean: Optional[str] = None
    matched_title: Optional[str] = None
    confidence: Optional[float] = None
    candidates: Optional[list[dict]] = None


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def match_one(
    rec: ProductRecord,
    is_listed: Callable[[str], bool],
    search_by_ean: Callable[[str], list[dict]],
    search_by_keywords: Callable[[str, Optional[str], int], list[dict]],
    title_candidates: int = 5,
) -> MatchOutcome:
    """Pure function: takes the catalog lookups as callables for easy testing."""
    # 1. already listed?
    try:
        if is_listed(rec.sku):
            return MatchOutcome(status="listed")
    except Exception as exc:
        logger.warning("is_listed(%s) failed: %s", rec.sku, exc)

    # 2. EAN search
    if rec.ean:
        try:
            hits = search_by_ean(rec.ean)
        except Exception as exc:
            logger.warning("search_by_ean(%s) failed: %s", rec.ean, exc)
            hits = []
        if hits:
            top = hits[0]
            return MatchOutcome(
                status="ean_match",
                asin=top.get("asin"),
                matched_ean=rec.ean,
                matched_title=top.get("title"),
                confidence=1.0,
            )

    # 3. title search
    if rec.title:
        try:
            hits = search_by_keywords(rec.title, rec.brand, title_candidates)
        except Exception as exc:
            logger.warning("search_by_keywords(%s) failed: %s", rec.sku, exc)
            hits = []
        scored = []
        for h in hits:
            h = dict(h)
            h["score"] = _similarity(rec.title, h.get("title") or "")
            scored.append(h)
        scored.sort(key=lambda x: x["score"], reverse=True)
        if scored:
            return MatchOutcome(status="needs_review", candidates=scored)

    return MatchOutcome(status="no_match")


def persist_outcome(sku: str, outcome: MatchOutcome) -> None:
    db.set_match(
        sku=sku,
        status=outcome.status,
        asin=outcome.asin,
        matched_ean=outcome.matched_ean,
        matched_title=outcome.matched_title,
        confidence=outcome.confidence,
    )
    if outcome.candidates is not None:
        db.replace_candidates(sku, outcome.candidates)
