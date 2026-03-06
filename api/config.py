"""API configuration via pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    """Server configuration, overridable via SW_API_* env vars."""

    host: str = "127.0.0.1"
    port: int = 8000
    db_path: str = "data/api_runs.db"
    max_concurrent_runs: int = 4
    cors_origins: list[str] = ["http://localhost:5173"]
    data_dir: str = "data"
    max_stored_events: int = 50_000
    default_max_ticks: int = 10_000

    model_config = SettingsConfigDict(env_prefix="SW_API_")
