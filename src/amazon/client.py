# src/amazon/client.py
"""Thin wrapper around python-amazon-sp-api.

Since 2 October 2023 the SP-API no longer requires AWS Sig V4 signing -
Amazon discards the signature and only checks the LWA access token. We
therefore pass empty AWS credentials and never read AWS_* from the env.
"""
from __future__ import annotations

import os
from functools import lru_cache

# Silence the library's startup donation banner.
os.environ.setdefault("ENV_DISABLE_DONATION_MSG", "1")

from sp_api.api import Feeds, Sellers  # noqa: E402
from sp_api.base import Marketplaces  # noqa: E402

from config.settings import settings  # noqa: E402


def _credentials() -> dict:
    return {
        "refresh_token": settings.lwa_refresh_token,
        "lwa_app_id": settings.lwa_client_id,
        "lwa_client_secret": settings.lwa_client_secret,
        # SP-API no longer validates these (Oct 2023). Pass empty strings so
        # the SDK skips its signing step instead of looking up AWS env vars.
        "aws_access_key": "",
        "aws_secret_key": "",
    }


def _marketplace() -> Marketplaces:
    # Spain marketplace id A1RKKUPIHCS9HS maps to Marketplaces.ES.
    return Marketplaces.ES


@lru_cache(maxsize=1)
def get_feeds_client() -> Feeds:
    return Feeds(credentials=_credentials(), marketplace=_marketplace())


@lru_cache(maxsize=1)
def get_sellers_client() -> Sellers:
    return Sellers(credentials=_credentials(), marketplace=_marketplace())
