"""Shared fixtures for API tests."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.config import ApiSettings
from api.main import create_app


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

    async with test_app.router.lifespan_context(test_app):
        yield test_app


@pytest_asyncio.fixture
async def client(app):
    """Async HTTP client for testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
