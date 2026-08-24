"""API configuration via pydantic-settings."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from stochastic_warfare.application_paths import ApplicationPaths


class ApiSettings(BaseSettings):
    """Server configuration, overridable via SW_API_* env vars."""

    host: str = "127.0.0.1"
    port: int = 8000
    db_path: str | None = None
    max_concurrent_runs: int = Field(default=4, ge=1)
    cors_origins: list[str] = ["http://localhost:5173"]
    data_dir: str | None = None
    frontend_dir: str | None = None
    artifact_dir: str | None = None
    max_stored_events: int = 50_000
    default_max_ticks: int = 10_000

    model_config = SettingsConfigDict(env_prefix="SW_API_")

    def application_paths(self) -> ApplicationPaths:
        """Resolve this exact API configuration through the path owner."""
        return ApplicationPaths.discover(
            catalog_root=self.data_dir,
            database_path=self.db_path,
            frontend_bundle=self.frontend_dir,
            artifact_root=self.artifact_dir,
        )
