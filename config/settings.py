# config/settings.py
"""
Centralized configuration management using Pydantic Settings.
All environment variables are validated and typed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Flask
    flask_env: Literal["development", "production"] = Field(default="production")
    secret_key: str = Field(default="change-me")
    port: int = Field(default=5000)

    # Amazon SP-API
    spapi_endpoint: str = Field(default="https://sellingpartnerapi-eu.amazon.com")
    marketplace_id: str = Field(default="A1RKKUPIHCS9HS")
    seller_id: str = Field(default="")
    aws_region: str = Field(default="eu-west-1")
    aws_access_key_id: str = Field(default="")
    aws_secret_access_key: str = Field(default="")
    lwa_client_id: str = Field(default="")
    lwa_client_secret: str = Field(default="")
    lwa_refresh_token: str = Field(default="")

    # Suprides API
    suprides_base_url: str = Field(default="https://www.suprides.pt")
    suprides_products_path: str = Field(default="/rest/V1/integration/products-list")
    suprides_bearer: str = Field(default="")
    suprides_user: str = Field(default="")
    suprides_password: str = Field(default="")
    suprides_limit: int = Field(default=250)

    # Storage
    storage_provider: Literal["local", "s3"] = Field(default="local")
    s3_bucket: str = Field(default="")
    s3_region: str = Field(default="eu-west-1")
    s3_prefix: str = Field(default="")

    # Features
    simulate_mode: bool = Field(default=True)
    brand_blocklist: str = Field(default="")

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")
    log_format: Literal["json", "text"] = Field(default="json")

    @field_validator("spapi_endpoint", "suprides_base_url")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        """Remove trailing slashes from URLs."""
        return v.rstrip("/")

    @field_validator("brand_blocklist")
    @classmethod
    def parse_blocklist(cls, v: str) -> str:
        """Normalize brand blocklist (kept as string, parsed on demand)."""
        return v.strip()

    @property
    def brand_blocklist_set(self) -> set[str]:
        """Parse blocklist into a set of lowercase brand names."""
        if not self.brand_blocklist:
            return set()
        return {b.strip().lower() for b in self.brand_blocklist.split(",") if b.strip()}

    @property
    def data_dir(self) -> Path:
        """Local data directory."""
        path = Path(__file__).parent.parent / "data"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def load_rules(self) -> dict:
        """Load business rules from rules.json."""
        rules_path = Path(__file__).parent / "rules.json"
        if not rules_path.exists():
            raise FileNotFoundError(f"Rules file not found: {rules_path}")
        with rules_path.open("r", encoding="utf-8") as f:
            return json.load(f)


# Global settings instance
settings = Settings()
