"""Behavioral API execution-integrity tests for Phase 106."""

from __future__ import annotations

import asyncio
from collections import Counter
import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import api.main as api_main
import api.run_manager as run_manager_module
from api.config import ApiSettings
from api.database import Database
from api.main import create_app
from api.run_manager import RunManager
from stochastic_warfare.entities.base import UnitStatus
from stochastic_warfare.morale.state import MoraleState
from stochastic_warfare.simulation.scenario import ScenarioLoader
from stochastic_warfare.tools._run_helpers import AnalysisRunner

pytestmark = [pytest.mark.api, pytest.mark.asyncio]

SCENARIO_PATH = Path("data/scenarios/test_campaign/scenario.yaml")


def _without_config_identity(result: dict[str, Any]) -> dict[str, Any]:
    """Return behavioral output without the separately asserted config identity."""
    outcome = dict(result)
    outcome.pop("config_fingerprint")
    return outcome


async def _wait_for_terminal(
    client: AsyncClient,
    run_id: str,
) -> dict[str, Any]:
    for _ in range(400):
        response = await client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        detail = response.json()
        if detail["status"] in {"completed", "failed", "cancelled"}:
            return detail
        await asyncio.sleep(0.025)
    pytest.fail(f"Run {run_id} did not reach a terminal state")


async def _run_events(
    client: AsyncClient,
    run_id: str,
) -> list[dict[str, Any]]:
    response = await client.get(f"/api/runs/{run_id}/events?limit=50000")
    assert response.status_code == 200
    return response.json()["events"]


def _empty_result(seed: int = 106) -> dict[str, Any]:
    return {
        "summary": {
            "scenario": "phase-106-control",
            "seed": seed,
            "ticks_executed": 0,
            "duration_s": 0.0,
            "victory": {},
            "sides": {},
        },
        "events": [],
        "snapshots": [],
        "terrain": {},
        "frames": [],
    }


def _argument_cancel_event(args: tuple[Any, ...]) -> Any | None:
    for value in reversed(args):
        if hasattr(value, "is_set") and hasattr(value, "set"):
            return value
    return None


def _raise_worker_cancelled() -> None:
    error_type = getattr(
        run_manager_module,
        "RunCancelledError",
        RuntimeError,
    )
    raise error_type("Run cancelled by user")


async def test_loader_applies_sparse_calibration_patch_without_mutating_source() -> None:
    before = SCENARIO_PATH.read_bytes()
    loader = ScenarioLoader(Path("data"))

    ctx = loader.load(
        SCENARIO_PATH,
        seed=106,
        calibration_overrides={
            "hit_probability_modifier": 0.25,
            "morale": {"base_degrade_rate": 0.2},
            "side_overrides": {"blue": {"start_x": 2500.0}},
        },
    )

    calibration = ctx.config.calibration_overrides
    assert calibration.hit_probability_modifier == 0.25
    assert calibration.target_size_modifier == 1.0
    assert calibration.morale.base_degrade_rate == 0.2
    assert calibration.morale.base_recover_rate == 0.1
    assert calibration.side_overrides["blue"].start_x == 2500.0
    assert ctx.calibration == calibration
    assert ctx.cal_flat["hit_probability_modifier"] == 0.25
    assert ctx.cal_flat["blue_start_x"] == 2500.0

    second = loader.load(
        SCENARIO_PATH,
        seed=106,
        calibration_overrides={"hit_probability_modifier": 0.75},
    )
    assert second.calibration.hit_probability_modifier == 0.75
    assert second.calibration.side_overrides == {}
    assert ctx.calibration.hit_probability_modifier == 0.25
    assert SCENARIO_PATH.read_bytes() == before


async def test_api_override_changes_outcome_and_is_deterministic(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    before = SCENARIO_PATH.read_bytes()
    requests: dict[str, dict[str, Any] | None] = {
        "omitted": None,
        "empty": {},
        "free": {"roe_level": "WEAPONS_FREE"},
        "hold_a": {"roe_level": "WEAPONS_HOLD"},
        "hold_b": {"roe_level": "WEAPONS_HOLD"},
        "closest": {"target_selection_mode": "closest"},
        "nearest": {"target_selection_mode": "nearest"},
    }
    run_ids: dict[str, str] = {}

    for label, overrides in requests.items():
        payload: dict[str, Any] = {
            "scenario": "test_campaign",
            "seed": 42,
            "max_ticks": 100,
        }
        if overrides is not None:
            payload["config_overrides"] = overrides
        response = await client.post("/api/runs", json=payload)
        assert response.status_code == 202
        run_ids[label] = response.json()["run_id"]

    details_list = await asyncio.gather(
        *(_wait_for_terminal(client, run_id) for run_id in run_ids.values()),
    )
    details = dict(zip(run_ids, details_list, strict=True))
    events_list = await asyncio.gather(
        *(_run_events(client, run_id) for run_id in run_ids.values()),
    )
    events = dict(zip(run_ids, events_list, strict=True))
    db: Database = app.state.db
    optional_rows = {label: await db.get_run(run_id) for label, run_id in run_ids.items()}
    rows = {label: row for label, row in optional_rows.items() if row is not None}

    assert all(detail["status"] == "completed" for detail in details.values())
    assert rows.keys() == optional_rows.keys()
    assert details["omitted"]["result"] == details["empty"]["result"]
    assert _without_config_identity(details["omitted"]["result"]) == _without_config_identity(
        details["free"]["result"],
    )
    assert details["omitted"]["result"]["config_fingerprint"] != details["free"]["result"]["config_fingerprint"]
    assert events["omitted"] == events["empty"] == events["free"]
    assert details["hold_a"]["result"] == details["hold_b"]["result"]
    assert events["hold_a"] == events["hold_b"]
    assert _without_config_identity(details["closest"]["result"]) == _without_config_identity(
        details["nearest"]["result"],
    )
    assert details["closest"]["result"]["config_fingerprint"] != details["nearest"]["result"]["config_fingerprint"]
    assert events["closest"] == events["nearest"]
    assert rows["omitted"]["result_json"] == rows["empty"]["result_json"]
    assert _without_config_identity(json.loads(rows["omitted"]["result_json"])) == (
        _without_config_identity(json.loads(rows["free"]["result_json"]))
    )
    assert rows["hold_a"]["result_json"] == rows["hold_b"]["result_json"]
    assert _without_config_identity(json.loads(rows["closest"]["result_json"])) == (
        _without_config_identity(json.loads(rows["nearest"]["result_json"]))
    )
    for payload_field in (
        "events_json",
        "snapshots_json",
        "terrain_json",
        "frames_json",
    ):
        assert rows["omitted"][payload_field] == rows["empty"][payload_field]
        assert rows["omitted"][payload_field] == rows["free"][payload_field]
        assert rows["hold_a"][payload_field] == rows["hold_b"][payload_field]
        assert rows["closest"][payload_field] == rows["nearest"][payload_field]

    free_engagements = [event for event in events["free"] if event["event_type"] == "EngagementEvent"]
    hold_engagements = [event for event in events["hold_a"] if event["event_type"] == "EngagementEvent"]
    assert free_engagements
    assert hold_engagements == []
    assert sum(side["disabled"] for side in details["free"]["result"]["sides"].values()) > 0
    # Removing the prohibited legacy-derived maximum-range hold keeps these
    # close opposing rosters at tactical five-second resolution, so the
    # authored 7,200-second reinforcement is correctly still pending.
    assert details["hold_a"]["result"]["ticks_executed"] == 100
    assert details["hold_a"]["result"]["duration_s"] == 500.0
    assert all(
        event["event_type"] != "ReinforcementArrivedEvent"
        for event in events["hold_a"]
    )
    assert details["hold_a"]["result"]["sides"] == {
        "blue": {"total": 4, "active": 2, "disabled": 0, "destroyed": 0},
        "red": {"total": 6, "active": 6, "disabled": 0, "destroyed": 0},
    }
    hold_morale_events = [
        event
        for event in events["hold_a"]
        if event["event_type"] == "MoraleStateChangeEvent"
    ]
    assert len(hold_morale_events) == 19
    assert Counter(
        event["data"]["cause"] for event in hold_morale_events
    ) == Counter({"stochastic": 17, "rout_cascade": 1, "rally": 1})
    final_hold_frame = json.loads(rows["hold_a"]["frames_json"])[-1]
    final_blue_morale = {
        unit["id"]: (unit["s"], unit["mo"])
        for unit in final_hold_frame["units"]
        if unit["side"] == "blue"
    }
    assert final_blue_morale == {
        "blue_m1a2_0000": (
            UnitStatus.ACTIVE.value,
            MoraleState.STEADY.value,
        ),
        "blue_m1a2_0001": (
            UnitStatus.ACTIVE.value,
            MoraleState.STEADY.value,
        ),
        "blue_m1a2_0002": (
            UnitStatus.ROUTING.value,
            MoraleState.ROUTED.value,
        ),
        "blue_m1a2_0003": (
            UnitStatus.ROUTING.value,
            MoraleState.ROUTED.value,
        ),
    }
    assert details["free"]["config_overrides"] == {
        "roe_level": "WEAPONS_FREE",
    }
    assert details["hold_a"]["config_overrides"] == {
        "roe_level": "WEAPONS_HOLD",
    }
    assert SCENARIO_PATH.read_bytes() == before


@pytest.mark.parametrize(
    "overrides",
    [
        {"hit_probability_modifer": 0.5},
        {"calibration_overrides": {"roe_level": "WEAPONS_HOLD"}},
        {"roe_level": "INVALID"},
        {"hit_probability_modifier": "not-a-number"},
        {"hit_probability_modifier": "0.5"},
        {"hit_probability_modifier": True},
        {"target_selection_mode": "unsupported"},
        {"advance_speed": 5.0},
        {"side_overrides": {"green": {"start_x": 1000.0}}},
        {"defensive_sides": ["green"]},
    ],
)
async def test_invalid_override_rejected_before_row_or_task(
    client: AsyncClient,
    app: FastAPI,
    overrides: dict[str, Any],
) -> None:
    response = await client.post(
        "/api/runs",
        json={
            "scenario": "test_campaign",
            "max_ticks": 1,
            "config_overrides": overrides,
        },
    )
    if response.status_code != 422:
        await app.state.run_manager.shutdown(timeout=1.0)

    assert response.status_code == 422
    assert await app.state.db.count_runs() == 0
    assert app.state.run_manager._tasks == {}


async def test_lifespan_uses_factory_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = ApiSettings(
        db_path=str(tmp_path / "factory.db"),
        data_dir=str(tmp_path / "factory-data"),
        max_concurrent_runs=2,
    )
    app = create_app(settings)

    def unexpected_global_settings() -> ApiSettings:
        raise AssertionError("lifespan ignored create_app(settings)")

    monkeypatch.setattr(
        api_main,
        "get_default_settings",
        unexpected_global_settings,
    )

    async with app.router.lifespan_context(app):
        assert app.state.db._db_path == settings.db_path
        assert app.state.run_manager._data_dir == Path(settings.data_dir)
        assert app.state.run_manager._semaphore._value == 2
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as test_client:
            response = await test_client.post(
                "/api/runs",
                json={"scenario": "test_campaign", "max_ticks": 1},
            )
        assert response.status_code == 404
        assert await app.state.db.count_runs() == 0
        assert app.state.run_manager._tasks == {}

    assert app.state.db._conn is None


async def test_exceptional_lifespan_exit_still_closes_owned_resources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = ApiSettings(
        db_path=str(tmp_path / "exception.db"),
        data_dir="data",
    )
    monkeypatch.setattr(api_main, "get_default_settings", lambda: settings)
    app = create_app(settings)
    db: Database | None = None
    mgr: RunManager | None = None

    with pytest.raises(RuntimeError, match="phase-106 lifespan failure"):
        async with app.router.lifespan_context(app):
            db = app.state.db
            mgr = app.state.run_manager
            raise RuntimeError("phase-106 lifespan failure")

    assert db is not None
    assert mgr is not None
    db_was_closed = db._conn is None
    if not db_was_closed:
        await db.close()
    assert db_was_closed
    assert getattr(mgr, "_closed", False)


async def test_startup_failure_closes_database_and_rejects_zero_workers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = ApiSettings(
        db_path=str(tmp_path / "startup-failure.db"),
        data_dir="data",
    )
    captured: dict[str, Database] = {}

    class FailingRunManager:
        def __init__(self, db: Database, **kwargs: Any) -> None:
            captured["db"] = db
            raise RuntimeError("phase-106 manager construction failure")

    monkeypatch.setattr(
        run_manager_module,
        "RunManager",
        FailingRunManager,
    )
    app = create_app(settings)

    with pytest.raises(
        RuntimeError,
        match="phase-106 manager construction failure",
    ):
        async with app.router.lifespan_context(app):
            pytest.fail("lifespan unexpectedly started")

    assert captured["db"]._conn is None
    with pytest.raises(ValueError):
        ApiSettings(max_concurrent_runs=0)
    with pytest.raises(ValueError):
        RunManager(
            Database(":memory:"),
            data_dir="data",
            max_concurrent=0,
        )


async def test_immediate_lifespan_teardown_persists_cancelled_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = ApiSettings(
        db_path=str(tmp_path / "teardown.db"),
        data_dir="data",
    )
    monkeypatch.setattr(api_main, "get_default_settings", lambda: settings)
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        mgr: RunManager = app.state.run_manager
        started = threading.Event()

        def cooperative_worker(run_id: str, *args: Any) -> dict[str, Any]:
            started.set()
            cancel_event = _argument_cancel_event(args)
            while cancel_event is None or not cancel_event.is_set():
                time.sleep(0.001)
            _raise_worker_cancelled()

        monkeypatch.setattr(mgr, "_run_sync", cooperative_worker)
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as test_client:
            response = await test_client.post(
                "/api/runs",
                json={
                    "scenario": "test_campaign",
                    "seed": 106,
                    "max_ticks": 1_000_000,
                },
            )
            assert response.status_code == 202
            run_id = response.json()["run_id"]
            assert await asyncio.to_thread(started.wait, 2.0)

    assert mgr._tasks == {}
    assert app.state.db._conn is None

    verification_db = Database(settings.db_path)
    await verification_db.initialize()
    try:
        row = await verification_db.get_run(run_id)
        assert row is not None
        assert row["status"] == "cancelled"
        assert row["completed_at"] is not None
    finally:
        await verification_db.close()


async def test_immediate_lifespan_teardown_persists_cancelled_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = ApiSettings(
        db_path=str(tmp_path / "batch-teardown.db"),
        data_dir="data",
    )
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        mgr: RunManager = app.state.run_manager
        started = threading.Event()

        def cooperative_batch(
            runner: AnalysisRunner,
            variant_id: str,
            **kwargs: Any,
        ) -> None:
            del runner, variant_id
            started.set()
            while True:
                kwargs["cancellation_check"]()
                time.sleep(0.001)

        monkeypatch.setattr(
            AnalysisRunner,
            "run_variant",
            cooperative_batch,
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as test_client:
            response = await test_client.post(
                "/api/runs/batch",
                json={
                    "scenario": "test_campaign",
                    "num_iterations": 2,
                    "base_seed": 106,
                    "max_ticks": 1_000_000,
                },
            )
            assert response.status_code == 202
            batch_id = response.json()["batch_id"]
            queue = mgr.subscribe(batch_id)
            assert queue is not None
            for index in range(queue.maxsize):
                queue.put_nowait({"queued": index})
            assert await asyncio.to_thread(started.wait, 2.0)

    assert mgr._tasks == {}
    assert app.state.db._conn is None
    queued_messages = []
    while not queue.empty():
        queued_messages.append(queue.get_nowait())
    assert queued_messages[-1] is None

    verification_db = Database(settings.db_path)
    await verification_db.initialize()
    try:
        row = await verification_db.get_batch(batch_id)
        assert row is not None
        assert row["status"] == "cancelled"
        assert row["completed_at"] is not None
        assert row["metrics_json"] is None
    finally:
        await verification_db.close()


async def test_shutdown_waits_for_worker_after_grace_threshold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = Database(str(tmp_path / "grace.db"))
    await db.initialize()
    mgr = RunManager(db, data_dir="data")
    started = threading.Event()
    release = threading.Event()

    def controlled_worker(run_id: str, *args: Any) -> dict[str, Any]:
        cancel_event = _argument_cancel_event(args)
        started.set()
        while not ((cancel_event is not None and cancel_event.is_set()) or release.is_set()):
            time.sleep(0.001)
        if cancel_event is not None and cancel_event.is_set():
            release.wait(2.0)
            _raise_worker_cancelled()
        release.wait(2.0)
        return _empty_result()

    monkeypatch.setattr(mgr, "_run_sync", controlled_worker)
    run_id = await mgr.submit(
        "test_campaign",
        str(SCENARIO_PATH),
        106,
        1_000_000,
    )
    assert await asyncio.to_thread(started.wait, 2.0)

    shutdown_task = asyncio.create_task(mgr.shutdown(timeout=0.0))
    try:
        await asyncio.sleep(0.05)
        assert not shutdown_task.done()
    finally:
        release.set()
        await asyncio.wait_for(shutdown_task, timeout=2.0)

    row = await db.get_run(run_id)
    assert row is not None
    assert row["status"] == "cancelled"
    assert mgr._tasks == {}
    await db.close()


async def test_shutdown_cancellation_waits_for_worker_and_terminal_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = Database(str(tmp_path / "cancelled-shutdown.db"))
    await db.initialize()
    mgr = RunManager(db, data_dir="data")
    started = threading.Event()
    release = threading.Event()

    def controlled_worker(run_id: str, *args: Any) -> dict[str, Any]:
        cancel_event = _argument_cancel_event(args)
        started.set()
        while cancel_event is None or not cancel_event.is_set():
            time.sleep(0.001)
        release.wait(2.0)
        _raise_worker_cancelled()

    monkeypatch.setattr(mgr, "_run_sync", controlled_worker)
    run_id = await mgr.submit(
        "test_campaign",
        str(SCENARIO_PATH),
        106,
        1_000_000,
    )
    assert await asyncio.to_thread(started.wait, 2.0)

    shutdown_task = asyncio.create_task(mgr.shutdown(timeout=0.0))
    await asyncio.sleep(0.05)
    shutdown_task.cancel()
    await asyncio.sleep(0.05)
    try:
        assert not shutdown_task.done()
        assert run_id in mgr._tasks
        assert db._conn is not None
    finally:
        release.set()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(shutdown_task, timeout=2.0)

    row = await db.get_run(run_id)
    assert row is not None
    assert row["status"] == "cancelled"
    assert mgr._tasks == {}
    await db.close()


async def test_execution_failure_is_persisted_and_fully_cleaned_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = Database(str(tmp_path / "failure.db"))
    await db.initialize()
    mgr = RunManager(db, data_dir="data")
    release = threading.Event()

    def failing_worker(run_id: str, *args: Any) -> dict[str, Any]:
        release.wait(2.0)
        raise RuntimeError("phase-106 controlled failure")

    monkeypatch.setattr(mgr, "_run_sync", failing_worker)
    run_id = await mgr.submit(
        "test_campaign",
        str(SCENARIO_PATH),
        106,
        1,
    )
    task = mgr._tasks[run_id]
    queue = mgr.subscribe(run_id)
    assert queue is not None
    for index in range(queue.maxsize):
        queue.put_nowait({"queued": index})
    release.set()
    await asyncio.wait_for(task, timeout=2.0)

    row = await db.get_run(run_id)
    assert row is not None
    assert row["status"] == "failed"
    assert row["completed_at"] is not None
    assert row["error_message"] == "phase-106 controlled failure"
    assert row["result_json"] is None
    queued_messages = []
    while not queue.empty():
        queued_messages.append(queue.get_nowait())
    assert queued_messages[-1] is None
    assert run_id not in mgr._tasks
    assert run_id not in mgr._cancel_events
    assert run_id not in mgr._progress_queues

    await mgr.shutdown()
    await db.close()


async def test_unpersistable_background_exception_is_retrieved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    db = Database(str(tmp_path / "task-exception.db"))
    await db.initialize()
    mgr = RunManager(db, data_dir="data")
    original_update = db.update_run_status

    async def fail_terminal_update(
        run_id: str,
        status: str,
        **fields: Any,
    ) -> None:
        if status == "running":
            await original_update(run_id, status, **fields)
            return
        raise RuntimeError("phase-106 terminal persistence failure")

    monkeypatch.setattr(db, "update_run_status", fail_terminal_update)
    monkeypatch.setattr(
        mgr,
        "_run_sync",
        lambda *args: _empty_result(),
    )

    run_id = await mgr.submit(
        "test_campaign",
        str(SCENARIO_PATH),
        106,
        1,
    )
    task = mgr._tasks[run_id]
    while not task.done():
        await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert "Background task ended with an exception" in caplog.text
    assert "phase-106 terminal persistence failure" in caplog.text
    assert mgr._tasks == {}

    await mgr.shutdown()
    await db.close()


async def test_submission_after_shutdown_is_rejected_without_row(
    tmp_path: Path,
) -> None:
    db = Database(str(tmp_path / "closed-manager.db"))
    await db.initialize()
    mgr = RunManager(db, data_dir="data")
    await mgr.shutdown()

    try:
        with pytest.raises(RuntimeError, match="shut"):
            await mgr.submit(
                "test_campaign",
                str(SCENARIO_PATH),
                106,
                1,
            )
    finally:
        await mgr.shutdown()

    assert await db.count_runs() == 0
    assert mgr._tasks == {}
    await db.close()


async def test_active_delete_cancels_and_awaits_worker(
    client: AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mgr: RunManager = app.state.run_manager
    started = threading.Event()
    release = threading.Event()

    def controlled_worker(run_id: str, *args: Any) -> dict[str, Any]:
        cancel_event = _argument_cancel_event(args)
        started.set()
        while not ((cancel_event is not None and cancel_event.is_set()) or release.is_set()):
            time.sleep(0.001)
        if cancel_event is not None and cancel_event.is_set():
            release.wait(2.0)
            _raise_worker_cancelled()
        return _empty_result()

    monkeypatch.setattr(mgr, "_run_sync", controlled_worker)
    response = await client.post(
        "/api/runs",
        json={
            "scenario": "test_campaign",
            "seed": 106,
            "max_ticks": 1_000_000,
        },
    )
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    assert await asyncio.to_thread(started.wait, 2.0)

    delete_task = asyncio.create_task(client.delete(f"/api/runs/{run_id}"))
    try:
        await asyncio.sleep(0.05)
        assert not delete_task.done()
    finally:
        release.set()
        delete_response = await asyncio.wait_for(delete_task, timeout=2.0)
        await mgr.shutdown(timeout=1.0)

    assert delete_response.status_code == 204
    assert run_id not in mgr._tasks
    assert (await client.get(f"/api/runs/{run_id}")).status_code == 404


async def test_missing_status_target_is_not_silently_ignored(
    tmp_path: Path,
) -> None:
    db = Database(str(tmp_path / "missing-row.db"))
    await db.initialize()
    try:
        await db.create_run(
            "real-run",
            "test_campaign",
            str(SCENARIO_PATH),
            106,
            1,
        )
        run_updates = await asyncio.gather(
            db.update_run_status("missing-run", "completed"),
            db.update_run_status("real-run", "running"),
            return_exceptions=True,
        )
        assert isinstance(run_updates[0], KeyError)
        assert run_updates[1] is None
        real_run = await db.get_run("real-run")
        assert real_run is not None
        assert real_run["status"] == "running"

        await db.create_batch(
            "real-batch",
            "test_campaign",
            str(SCENARIO_PATH),
            2,
            106,
            1,
        )
        batch_updates = await asyncio.gather(
            db.update_batch("missing-batch", status="completed"),
            db.update_batch("real-batch", status="running"),
            return_exceptions=True,
        )
        assert isinstance(batch_updates[0], KeyError)
        assert batch_updates[1] is None
        real_batch = await db.get_batch("real-batch")
        assert real_batch is not None
        assert real_batch["status"] == "running"
    finally:
        await db.close()
