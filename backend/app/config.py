"""
DataMind Backend — Configuration Module

Loads all settings from environment variables with validation.
"""

from __future__ import annotations

from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # --- Snowflake ---
    snowflake_account: str = ""
    snowflake_user: str = ""
    snowflake_password: str = ""
    snowflake_warehouse: str = ""
    snowflake_database: str = ""
    snowflake_schema: str = "PUBLIC"
    snowflake_role: Optional[str] = None

    # --- Gemma ---
    gemma_provider: str = "ollama"
    gemma_model: str = "gemma3:4b"
    gemma_api_base: str = "http://localhost:11434"
    gemma_timeout: int = 120

    # --- Backend ---
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    # --- Query Safety ---
    max_result_rows: int = 1000
    query_timeout_seconds: int = 30
    allowed_databases: str = ""
    allowed_schemas: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_database_list(self) -> list[str]:
        if self.allowed_databases:
            return [d.strip().upper() for d in self.allowed_databases.split(",") if d.strip()]
        return [self.snowflake_database.upper()] if self.snowflake_database else []

    @property
    def allowed_schema_list(self) -> list[str]:
        if self.allowed_schemas:
            return [s.strip().upper() for s in self.allowed_schemas.split(",") if s.strip()]
        return [self.snowflake_schema.upper()] if self.snowflake_schema else []

    @property
    def snowflake_configured(self) -> bool:
        return bool(self.snowflake_account and self.snowflake_user and self.snowflake_password)

    @property
    def gemma_configured(self) -> bool:
        return bool(self.gemma_api_base and self.gemma_model)


# Singleton
_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
