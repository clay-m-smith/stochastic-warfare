"""FastAPI dependency injection providers."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from fastapi import Request

from api.config import ApiSettings

if TYPE_CHECKING:
    from api.database import Database
    from api.run_manager import RunManager


@lru_cache(maxsize=1)
def get_settings() -> ApiSettings:
    """Return cached application settings."""
    return ApiSettings()


def get_db(request: Request) -> Database:
    """Retrieve the Database instance from app state."""
    return request.app.state.db


def get_run_manager(request: Request) -> RunManager:
    """Retrieve the RunManager instance from app state."""
    return request.app.state.run_manager
