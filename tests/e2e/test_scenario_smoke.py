"""E2E smoke test — run every scenario through the API to completion.

Validates that all 41 scenarios can be loaded, executed for 20 ticks,
and return a completed result without errors.

Run explicitly:
    uv run python -m pytest tests/e2e/ -m e2e --tb=short -q
"""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.config import ApiSettings
from api.database import Database
from api.main import create_app
from api.run_manager import RunManager

# Phase 55b: All legacy scenarios now load through CampaignScenarioConfig.
# The xfail set has been cleared — all scenarios have the required
# sides/terrain/date fields since Phase 30/47/49 migrations.
_LEGACY_FORMAT_SCENARIOS: frozenset[str] = frozenset()

ALL_SCENARIO_NAMES = [
    # Modern scenarios (27)
    "73_easting",
    "bekaa_valley_1982",
    "cbrn_chemical_defense",
    "cbrn_nuclear_tactical",
    "coin_campaign",
    "eastern_front_1943",
    "falklands_campaign",
    "falklands_goose_green",
    "falklands_naval",
    "falklands_san_carlos",
    "golan_campaign",
    "golan_heights",
    "gulf_war_ew_1991",
    "halabja_1988",
    "hybrid_gray_zone",
    "korean_peninsula",
    "space_asat_escalation",
    "space_gps_denial",
    "space_isr_gap",
    "srebrenica_1995",
    "suwalki_gap",
    "taiwan_strait",
    "test_campaign",
    "test_campaign_logistics",
    "test_campaign_multi",
    "test_campaign_reinforce",
    "test_scenario",
    # Era scenarios (14)
    "agincourt",
    "austerlitz",
    "cambrai",
    "cannae",
    "hastings",
    "jutland",
    "kursk",
    "midway",
    "normandy_bocage",
    "salamis",
    "somme_july1",
    "stalingrad",
    "trafalgar",
    "waterloo",
]


@pytest_asyncio.fixture
async def client():
    """Async HTTP client with in-memory DB for E2E tests."""
    from api.dependencies import get_settings

    settings = ApiSettings(db_path=":memory:", data_dir="data")
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings

    db = Database(settings.db_path)
    await db.initialize()
    app.state.db = db
    app.state.run_manager = RunManager(
        db,
        data_dir=settings.data_dir,
        max_concurrent=2,
        max_stored_events=1000,
        default_max_ticks=20,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    await db.close()


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.parametrize("scenario_name", ALL_SCENARIO_NAMES)
async def test_scenario_runs_to_completion(client: AsyncClient, scenario_name: str) -> None:
    """Submit a scenario and verify it completes within 20 ticks."""
    if scenario_name in _LEGACY_FORMAT_SCENARIOS:
        pytest.xfail(f"{scenario_name} uses legacy YAML format without campaign schema")

    resp = await client.post("/api/runs", json={
        "scenario": scenario_name,
        "seed": 42,
        "max_ticks": 20,
    })
    assert resp.status_code == 202, f"Submit failed for {scenario_name}: {resp.text}"
    run_id = resp.json()["run_id"]

    # Poll until complete (max 60s)
    data = None
    for _ in range(120):
        resp = await client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        if data["status"] in ("completed", "failed"):
            break
        await asyncio.sleep(0.5)

    assert data is not None, f"Never got status for {scenario_name}"
    assert data["status"] == "completed", (
        f"{scenario_name} failed: {data.get('error_message', 'unknown')}"
    )
    result = data.get("result")
    assert result is not None, f"{scenario_name} has no result"
    assert result.get("ticks_executed", 0) > 0, f"{scenario_name} executed 0 ticks"
