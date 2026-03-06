"""Tests for SQLite database layer."""

from __future__ import annotations

import pytest
import pytest_asyncio

from api.database import Database

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def db():
    """In-memory database for testing."""
    database = Database(":memory:")
    await database.initialize()
    yield database
    await database.close()


async def test_create_and_get_run(db):
    await db.create_run("run1", "test_scenario", "/path/to/scenario.yaml", 42, 1000)
    row = await db.get_run("run1")
    assert row is not None
    assert row["id"] == "run1"
    assert row["scenario_name"] == "test_scenario"
    assert row["seed"] == 42
    assert row["status"] == "pending"


async def test_get_nonexistent_run(db):
    row = await db.get_run("nonexistent")
    assert row is None


async def test_update_run_status(db):
    await db.create_run("run1", "test_scenario", "/path", 42, 1000)
    await db.update_run_status("run1", "running", started_at="2024-01-01T00:00:00Z")
    row = await db.get_run("run1")
    assert row["status"] == "running"
    assert row["started_at"] == "2024-01-01T00:00:00Z"


async def test_update_run_with_result(db):
    await db.create_run("run1", "test_scenario", "/path", 42, 1000)
    await db.update_run_status(
        "run1", "completed",
        completed_at="2024-01-01T00:01:00Z",
        result_json='{"ticks": 100}',
        events_json='[]',
        snapshots_json='[]',
    )
    row = await db.get_run("run1")
    assert row["status"] == "completed"
    assert row["result_json"] == '{"ticks": 100}'


async def test_update_run_with_error(db):
    await db.create_run("run1", "test_scenario", "/path", 42, 1000)
    await db.update_run_status("run1", "failed", error_message="Something went wrong")
    row = await db.get_run("run1")
    assert row["status"] == "failed"
    assert row["error_message"] == "Something went wrong"


async def test_list_runs(db):
    await db.create_run("run1", "scen_a", "/p1", 1, 100)
    await db.create_run("run2", "scen_b", "/p2", 2, 200)
    await db.create_run("run3", "scen_a", "/p3", 3, 300)
    rows = await db.list_runs()
    assert len(rows) == 3


async def test_list_runs_filter_scenario(db):
    await db.create_run("run1", "scen_a", "/p1", 1, 100)
    await db.create_run("run2", "scen_b", "/p2", 2, 200)
    rows = await db.list_runs(scenario="scen_a")
    assert len(rows) == 1
    assert rows[0]["scenario_name"] == "scen_a"


async def test_list_runs_filter_status(db):
    await db.create_run("run1", "scen", "/p", 1, 100)
    await db.create_run("run2", "scen", "/p", 2, 200)
    await db.update_run_status("run1", "completed")
    rows = await db.list_runs(status="completed")
    assert len(rows) == 1
    assert rows[0]["id"] == "run1"


async def test_list_runs_pagination(db):
    for i in range(5):
        await db.create_run(f"run{i}", "scen", "/p", i, 100)
    rows = await db.list_runs(limit=2, offset=0)
    assert len(rows) == 2
    rows2 = await db.list_runs(limit=2, offset=2)
    assert len(rows2) == 2


async def test_delete_run(db):
    await db.create_run("run1", "scen", "/p", 1, 100)
    deleted = await db.delete_run("run1")
    assert deleted is True
    row = await db.get_run("run1")
    assert row is None


async def test_delete_nonexistent_run(db):
    deleted = await db.delete_run("nonexistent")
    assert deleted is False


async def test_count_runs(db):
    assert await db.count_runs() == 0
    await db.create_run("run1", "scen", "/p", 1, 100)
    assert await db.count_runs() == 1


async def test_create_and_get_batch(db):
    await db.create_batch("batch1", "scen", "/p", 20, 42, 100)
    row = await db.get_batch("batch1")
    assert row is not None
    assert row["id"] == "batch1"
    assert row["num_iterations"] == 20
    assert row["status"] == "pending"


async def test_update_batch(db):
    await db.create_batch("batch1", "scen", "/p", 20, 42, 100)
    await db.update_batch("batch1", status="running", completed_iterations=5)
    row = await db.get_batch("batch1")
    assert row["status"] == "running"
    assert row["completed_iterations"] == 5


async def test_batch_with_metrics(db):
    await db.create_batch("batch1", "scen", "/p", 20, 42, 100)
    await db.update_batch(
        "batch1",
        status="completed",
        metrics_json='{"blue_destroyed": {"mean": 2.5}}',
    )
    row = await db.get_batch("batch1")
    assert row["metrics_json"] is not None
