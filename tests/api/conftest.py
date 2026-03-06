"""Shared fixtures for API tests."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.config import ApiSettings
from api.database import Database
from api.main import create_app
from api.run_manager import RunManager


@pytest.fixture
def settings() -> ApiSettings:
    """Settings with in-memory DB and real data directory."""
    return ApiSettings(db_path=":memory:", data_dir="data")


@pytest_asyncio.fixture
async def app(settings: ApiSettings):
    """Create a test app with in-memory DB."""
    from api.dependencies import get_settings

    test_app = create_app(settings)

    # Override settings dependency
    test_app.dependency_overrides[get_settings] = lambda: settings

    # Manually run lifespan
    db = Database(settings.db_path)
    await db.initialize()
    test_app.state.db = db
    test_app.state.run_manager = RunManager(
        db,
        data_dir=settings.data_dir,
        max_concurrent=settings.max_concurrent_runs,
        max_stored_events=settings.max_stored_events,
        default_max_ticks=settings.default_max_ticks,
    )
    yield test_app
    await db.close()


@pytest_asyncio.fixture
async def client(app):
    """Async HTTP client for testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
