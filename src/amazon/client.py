# src/amazon/client.py
"""Thin wrapper around python-amazon-sp-api.

Centralises credentials and marketplace selection so the rest of the code can
just import the helpers it needs.
"""
from __future__ import annotations

from functools import lru_cache

from sp_api.api import Feeds, Sellers
from sp_api.base import Marketplaces

from config.settings import settings


def _credentials() -> dict:
    return {
        "refresh_token": settings.lwa_refresh_token,
        "lwa_app_id": settings.lwa_client_id,
        "lwa_client_secret": settings.lwa_client_secret,
        "aws_access_key": settings.aws_access_key_id,
        "aws_secret_key": settings.aws_secret_access_key,
    }


def _marketplace() -> Marketplaces:
    # Spain = ES. The library exposes Marketplaces.ES which maps to A1RKKUPIHCS9HS.
    return Marketplaces.ES


@lru_cache(maxsize=1)
def get_feeds_client() -> Feeds:
    return Feeds(credentials=_credentials(), marketplace=_marketplace())


@lru_cache(maxsize=1)
def get_sellers_client() -> Sellers:
    return Sellers(credentials=_credentials(), marketplace=_marketplace())
