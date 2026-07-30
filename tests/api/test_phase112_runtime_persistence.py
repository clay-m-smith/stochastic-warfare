"""Durable HTTP publication proofs for the Phase 112 runtime boundary."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
import yaml

from api.config import ApiSettings
from api.database import Database
from api.main import create_app
from stochastic_warfare.tools._run_helpers import AnalysisRunner


pytestmark = [pytest.mark.api, pytest.mark.asyncio]


async def _wait_for_status(
    client: AsyncClient,
    path: str,
    statuses: set[str],
) -> dict:
    for _ in range(200):
        response = await client.get(path)
        assert response.status_code == 200, response.text
        payload = response.json()
        if payload["status"] in statuses:
            return payload
        await asyncio.sleep(0.025)
    pytest.fail(f"{path} did not reach {sorted(statuses)!r}")


def _assert_runtime_provenance(provenance: dict) -> None:
    code_revision = provenance["code_revision"]
    assert len(code_revision["commit"]) == 40
    assert isinstance(code_revision["dirty"], bool)
    assert len(code_revision["worktree_fingerprint"]) == 64
    assert len(provenance["data_revision"]) == 64
    assert provenance["data_file_count"] > 0
    assert len(provenance["catalog_revision"]) == 64
    assert len(provenance["doctrine_catalog_fingerprint"]) == 64
    assert len(provenance["doctrine_assignment_fingerprint"]) == 64
    assert len(provenance["loaded_roster_loadout_fingerprint"]) == 64
    assert len(provenance["final_roster_loadout_fingerprint"]) == 64
    assert provenance["initial_unit_assignments"]


async def test_legacy_completed_batch_cannot_publish_unverified_statistics(
    client: AsyncClient,
    app,
) -> None:
    await app.state.db.create_batch(
        "legacy-batch",
        "test_campaign",
        "data/scenarios/test_campaign/scenario.yaml",
        2,
        42,
        1,
    )
    await app.state.db.update_batch(
        "legacy-batch",
        status="completed",
        completed_iterations=2,
        metrics_json=json.dumps(
            {"blue_destroyed": {"mean": 2.5}},
        ),
    )

    response = await client.get("/api/runs/batch/legacy-batch")

    assert response.status_code == 409
    assert "raw-vector and provenance evidence" in response.text


async def test_accepted_cancellation_prevents_completion_publication(
    client: AsyncClient,
    app,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accepted run and batch cancellation owns the terminal publication."""
    manager = app.state.run_manager
    publication_boundaries: asyncio.Queue[asyncio.Event] = asyncio.Queue()
    original_await_worker = manager._await_worker

    async def pause_after_worker(
        worker_future,
        cancel_event,
    ):
        result = await original_await_worker(worker_future, cancel_event)
        release_publication = asyncio.Event()
        await publication_boundaries.put(release_publication)
        await release_publication.wait()
        return result

    def completed_worker(*_args, **_kwargs) -> dict:
        return {
            "summary": {"forbidden_completed_result": True},
            "events": [{"forbidden_completed_event": True}],
            "snapshots": [{"forbidden_completed_snapshot": True}],
            "terrain": {"forbidden_completed_terrain": True},
            "frames": [{"forbidden_completed_frame": True}],
        }

    monkeypatch.setattr(manager, "_await_worker", pause_after_worker)
    monkeypatch.setattr(manager, "_run_sync", completed_worker)

    submitted = await client.post(
        "/api/runs",
        json={
            "scenario": "test_campaign",
            "seed": 112,
            "max_ticks": 1,
        },
    )
    assert submitted.status_code == 202, submitted.text
    run_id = submitted.json()["run_id"]
    run_publication = await asyncio.wait_for(
        publication_boundaries.get(),
        timeout=2.0,
    )
    task = manager._tasks[run_id]

    assert await manager.cancel(run_id) is True
    run_publication.set()
    await asyncio.wait_for(asyncio.shield(task), timeout=2.0)

    row = await app.state.db.get_run(run_id)
    assert row is not None
    assert row["status"] == "cancelled"
    assert row["completed_at"] is not None
    for field in (
        "result_json",
        "events_json",
        "snapshots_json",
        "terrain_json",
        "frames_json",
    ):
        assert row[field] is None
    detail = await client.get(f"/api/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "cancelled"
    assert detail.json()["result"] is None

    submitted_batch = await client.post(
        "/api/runs/batch",
        json={
            "scenario": "test_campaign",
            "num_iterations": 1,
            "base_seed": 112,
            "max_ticks": 1,
        },
    )
    assert submitted_batch.status_code == 202, submitted_batch.text
    batch_id = submitted_batch.json()["batch_id"]
    batch_publication = await asyncio.wait_for(
        publication_boundaries.get(),
        timeout=2.0,
    )
    batch_task = manager._tasks[batch_id]

    assert await manager.cancel(batch_id) is True
    batch_publication.set()
    await asyncio.wait_for(asyncio.shield(batch_task), timeout=2.0)

    batch_row = await app.state.db.get_batch(batch_id)
    assert batch_row is not None
    assert batch_row["status"] == "cancelled"
    assert batch_row["completed_at"] is not None
    assert batch_row["metrics_json"] is None
    batch_detail = await client.get(f"/api/runs/batch/{batch_id}")
    assert batch_detail.status_code == 200
    assert batch_detail.json()["status"] == "cancelled"
    assert batch_detail.json()["metrics"] is None
    assert batch_detail.json()["raw_metrics"] is None
    assert batch_detail.json()["provenance"] is None


async def test_completed_batch_rejects_inconsistent_durable_evidence(
    client: AsyncClient,
    app,
) -> None:
    submitted = await client.post(
        "/api/runs/batch",
        json={
            "scenario": "test_campaign",
            "num_iterations": 2,
            "base_seed": 0,
            "max_ticks": 1,
        },
    )
    assert submitted.status_code == 202
    batch_id = submitted.json()["batch_id"]
    detail = await _wait_for_status(
        client,
        f"/api/runs/batch/{batch_id}",
        {"completed", "failed"},
    )
    assert detail["status"] == "completed", detail
    row = await app.state.db.get_batch(batch_id)
    assert row is not None
    valid_payload = json.loads(row["metrics_json"])

    corrupt_payloads = []
    partial = json.loads(json.dumps(valid_payload))
    partial["raw_metrics"][partial["ordered_metrics"][0]].pop()
    corrupt_payloads.append(partial)

    inconsistent_statistics = json.loads(json.dumps(valid_payload))
    metric = inconsistent_statistics["ordered_metrics"][0]
    inconsistent_statistics["statistics"][metric]["mean"] += 1.0
    corrupt_payloads.append(inconsistent_statistics)

    incomplete_provenance = json.loads(json.dumps(valid_payload))
    incomplete_provenance["provenance"]["seeds"].pop()
    corrupt_payloads.append(incomplete_provenance)

    boolean_provenance_seed = json.loads(json.dumps(valid_payload))
    boolean_provenance_seed["provenance"]["seeds"][0] = False
    corrupt_payloads.append(boolean_provenance_seed)

    boolean_run_seed = json.loads(json.dumps(valid_payload))
    boolean_run_seed["provenance"]["runs"][0]["seed"] = False
    corrupt_payloads.append(boolean_run_seed)

    unsupported_metric = json.loads(json.dumps(valid_payload))
    original_metric = unsupported_metric["ordered_metrics"][0]
    fabricated_metric = "phase112_fabricated_authoritative_zero"
    unsupported_metric["ordered_metrics"][0] = fabricated_metric
    unsupported_metric["provenance"]["ordered_metrics"][0] = (
        fabricated_metric
    )
    unsupported_metric["raw_metrics"] = {
        (
            fabricated_metric
            if metric == original_metric
            else metric
        ): values
        for metric, values in unsupported_metric["raw_metrics"].items()
    }
    unsupported_metric["statistics"] = {
        (
            fabricated_metric
            if metric == original_metric
            else metric
        ): statistics
        for metric, statistics in unsupported_metric[
            "statistics"
        ].items()
    }
    corrupt_payloads.append(unsupported_metric)

    impossible_assignments = json.loads(json.dumps(valid_payload))
    provenance = impossible_assignments["provenance"]
    initial_assignment = provenance["initial_unit_assignments"][0]
    provenance["initial_unit_assignments"] = [initial_assignment]
    for run in provenance["runs"]:
        run["runtime_provenance"]["initial_unit_assignments"] = [
            initial_assignment,
        ]
    corrupt_payloads.append(impossible_assignments)

    reused_arrival = json.loads(json.dumps(valid_payload))
    initial_assignment = reused_arrival["provenance"][
        "initial_unit_assignments"
    ][0]
    for run in reused_arrival["provenance"]["runs"]:
        run["runtime_provenance"]["arriving_unit_assignments"] = [
            {
                **initial_assignment,
                "side": "phase112_alien_side",
            },
        ]
    corrupt_payloads.append(reused_arrival)

    excessive_ticks = json.loads(json.dumps(valid_payload))
    for run in excessive_ticks["provenance"]["runs"]:
        run["ticks_executed"] = 999
    corrupt_payloads.append(excessive_ticks)

    negative_duration = json.loads(json.dumps(valid_payload))
    for run in negative_duration["provenance"]["runs"]:
        run["duration_s"] = -1.0
    corrupt_payloads.append(negative_duration)

    alien_winner = json.loads(json.dumps(valid_payload))
    for run in alien_winner["provenance"]["runs"]:
        run["winning_side"] = "phase112_alien_side"
    corrupt_payloads.append(alien_winner)

    invented_condition = json.loads(json.dumps(valid_payload))
    for run in invented_condition["provenance"]["runs"]:
        run["condition_type"] = "phase112_invented_condition"
    corrupt_payloads.append(invented_condition)

    impossible_count = json.loads(json.dumps(valid_payload))
    count_metric = impossible_count["ordered_metrics"][0]
    impossible_count["raw_metrics"][count_metric] = [999.5, 999.5]
    impossible_count["statistics"][count_metric] = {
        "mean": 999.5,
        "median": 999.5,
        "std": 0.0,
        "min": 999.5,
        "max": 999.5,
        "p5": 999.5,
        "p95": 999.5,
        "n": 2,
    }
    corrupt_payloads.append(impossible_count)

    oversized_number = json.loads(json.dumps(valid_payload))
    oversized_number["raw_metrics"][
        oversized_number["ordered_metrics"][0]
    ][0] = 10**309
    corrupt_payloads.append(oversized_number)

    for corrupt in corrupt_payloads:
        await app.state.db.update_batch(
            batch_id,
            metrics_json=json.dumps(corrupt, allow_nan=False),
        )
        rejected = await client.get(f"/api/runs/batch/{batch_id}")
        assert rejected.status_code == 409, rejected.text

    await app.state.db.update_batch(
        batch_id,
        metrics_json=json.dumps(valid_payload, allow_nan=False),
    )
    restored = await client.get(f"/api/runs/batch/{batch_id}")
    assert restored.status_code == 200, restored.text


async def test_invalid_rosters_are_rejected_before_run_or_batch_persistence(
    client: AsyncClient,
    app,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    invalid_config = yaml.safe_load(
        Path(
            "data/scenarios/test_campaign/scenario.yaml",
        ).read_text(encoding="utf-8"),
    )
    invalid_config["sides"][0]["units"][0]["unit_type"] = (
        "phase112_missing_unit_definition"
    )
    invalid_path = tmp_path / "invalid-roster.yaml"
    invalid_path.write_text(
        yaml.safe_dump(invalid_config, sort_keys=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "api.routers.runs.resolve_scenario",
        lambda _name, _data_dir: invalid_path,
    )

    before_runs = await app.state.db.count_runs()
    before_batches_cursor = await app.state.db.conn.execute(
        "SELECT COUNT(*) FROM batches",
    )
    before_batches = (await before_batches_cursor.fetchone())[0]

    file_run = await client.post(
        "/api/runs",
        json={
            "scenario": "invalid-roster",
            "seed": 42,
            "max_ticks": 1,
        },
    )
    inline_run = await client.post(
        "/api/runs/from-config",
        json={
            "config": invalid_config,
            "seed": 42,
            "max_ticks": 1,
        },
    )
    batch = await client.post(
        "/api/runs/batch",
        json={
            "scenario": "invalid-roster",
            "num_iterations": 2,
            "base_seed": 42,
            "max_ticks": 1,
        },
    )

    for response in (file_run, inline_run, batch):
        assert response.status_code == 422, response.text
        assert "phase112_missing_unit_definition" in response.text
    assert await app.state.db.count_runs() == before_runs
    after_batches_cursor = await app.state.db.conn.execute(
        "SELECT COUNT(*) FROM batches",
    )
    assert (await after_batches_cursor.fetchone())[0] == before_batches
    assert app.state.run_manager._tasks == {}
    assert app.state.run_manager._progress_queues == {}
    assert app.state.run_manager._cancel_events == {}


async def test_invalid_scenario_references_are_http_422_before_persistence(
    client: AsyncClient,
    app,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_path = Path(
        "data/scenarios/test_campaign/scenario.yaml",
    )
    unknown_profile = yaml.safe_load(
        source_path.read_text(encoding="utf-8"),
    )
    unknown_profile["sides"][0]["commander_profile"] = (
        "phase112_unknown_commander"
    )
    unknown_school = yaml.safe_load(
        source_path.read_text(encoding="utf-8"),
    )
    unknown_school["school_config"] = {
        "unit_assignments": {
            "blue_m1a2_0000": "phase112_unknown_school",
        },
    }
    unknown_reinforcement = yaml.safe_load(
        source_path.read_text(encoding="utf-8"),
    )
    unknown_reinforcement["reinforcements"][0]["units"][0][
        "unit_type"
    ] = "phase112_unknown_reinforcement"
    unknown_time_on_target_battery = yaml.safe_load(
        Path(
            "data/scenarios/time_on_target_validation/scenario.yaml",
        ).read_text(encoding="utf-8"),
    )
    unknown_time_on_target_battery["indirect_fire"][
        "time_on_target_missions"
    ][0]["batteries"][0]["unit_id"] = "phase112_unknown_battery"
    invalid_cases = (
        (
            "unknown-commander",
            unknown_profile,
            "phase112_unknown_commander",
        ),
        (
            "unknown-school",
            unknown_school,
            "phase112_unknown_school",
        ),
        (
            "unknown-reinforcement",
            unknown_reinforcement,
            "phase112_unknown_reinforcement",
        ),
        (
            "unknown-time-on-target-battery",
            unknown_time_on_target_battery,
            (
                "mission 'blue_validation_tot' references unknown battery "
                "unit(s) ['phase112_unknown_battery']"
            ),
        ),
    )

    before_runs = await app.state.db.count_runs()
    before_batches_cursor = await app.state.db.conn.execute(
        "SELECT COUNT(*) FROM batches",
    )
    before_batches = (await before_batches_cursor.fetchone())[0]

    for scenario_name, config, expected in invalid_cases:
        scenario_path = tmp_path / f"{scenario_name}.yaml"
        scenario_path.write_text(
            yaml.safe_dump(config, sort_keys=False),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "api.routers.runs.resolve_scenario",
            lambda _name, _data_dir, path=scenario_path: path,
        )
        file_run = await client.post(
            "/api/runs",
            json={
                "scenario": scenario_name,
                "seed": 42,
                "max_ticks": 1,
            },
        )
        inline = await client.post(
            "/api/runs/from-config",
            json={
                "config": config,
                "seed": 42,
                "max_ticks": 1,
            },
        )
        batch = await client.post(
            "/api/runs/batch",
            json={
                "scenario": scenario_name,
                "num_iterations": 2,
                "base_seed": 42,
                "max_ticks": 1,
            },
        )
        for response in (file_run, inline, batch):
            assert response.status_code == 422, response.text
            if scenario_name == "unknown-time-on-target-battery":
                assert response.json() == {"detail": expected}
            else:
                assert expected in response.text

    assert await app.state.db.count_runs() == before_runs
    after_batches_cursor = await app.state.db.conn.execute(
        "SELECT COUNT(*) FROM batches",
    )
    assert (await after_batches_cursor.fetchone())[0] == before_batches
    assert app.state.run_manager._tasks == {}
    assert app.state.run_manager._progress_queues == {}
    assert app.state.run_manager._cancel_events == {}


async def test_run_and_batch_survive_database_reopen_with_full_evidence(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "phase112-runtime.db"
    settings = ApiSettings(
        db_path=str(database_path),
        data_dir="data",
    )
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            run_response = await client.post(
                "/api/runs",
                json={
                    "scenario": "test_campaign",
                    "seed": 42,
                    "max_ticks": 50,
                },
            )
            assert run_response.status_code == 202
            run_id = run_response.json()["run_id"]
            run_detail = await _wait_for_status(
                client,
                f"/api/runs/{run_id}",
                {"completed", "failed"},
            )
            assert run_detail["status"] == "completed", run_detail

            batch_response = await client.post(
                "/api/runs/batch",
                json={
                    "scenario": "test_campaign",
                    "num_iterations": 2,
                    "base_seed": 42,
                    "max_ticks": 50,
                },
            )
            assert batch_response.status_code == 202
            batch_id = batch_response.json()["batch_id"]
            batch_detail = await _wait_for_status(
                client,
                f"/api/runs/batch/{batch_id}",
                {"completed", "failed"},
            )
            assert batch_detail["status"] == "completed", batch_detail

            inline_config = yaml.safe_load(
                Path(
                    "data/scenarios/test_campaign/scenario.yaml",
                ).read_text(encoding="utf-8"),
            )
            inline_response = await client.post(
                "/api/runs/from-config",
                json={
                    "config": inline_config,
                    "seed": 43,
                    "max_ticks": 50,
                },
            )
            assert inline_response.status_code == 202
            inline_id = inline_response.json()["run_id"]
            inline_detail = await _wait_for_status(
                client,
                f"/api/runs/{inline_id}",
                {"completed", "failed"},
            )
            assert inline_detail["status"] == "completed", inline_detail
            assert inline_detail["scenario_path"] == "<inline-config>"

    reopened = Database(str(database_path))
    await reopened.initialize()
    try:
        run_row = await reopened.get_run(run_id)
        inline_row = await reopened.get_run(inline_id)
        batch_row = await reopened.get_batch(batch_id)
    finally:
        await reopened.close()

    assert run_row is not None
    assert run_row["status"] == "completed"
    run_result = json.loads(run_row["result_json"])
    assert run_result["ticks_executed"] == 50
    assert run_result["victory"]["winning_side"]
    assert run_result["authored_roster"] == run_result["loaded_roster"]
    assert run_detail["result"] == run_result
    _assert_runtime_provenance(run_result["provenance"])

    assert inline_row is not None
    assert inline_row["status"] == "completed"
    inline_result = json.loads(inline_row["result_json"])
    assert len(inline_result["source_fingerprint"]) == 64
    assert len(inline_result["config_fingerprint"]) == 64
    assert inline_result["authored_roster"] == inline_result["loaded_roster"]
    _assert_runtime_provenance(inline_result["provenance"])

    assert batch_row is not None
    assert batch_row["status"] == "completed"
    assert batch_row["completed_iterations"] == 2
    batch_result = json.loads(batch_row["metrics_json"])
    assert batch_detail["raw_metrics"] == batch_result["raw_metrics"]
    assert batch_detail["metrics"] == batch_result["statistics"]
    assert batch_detail["provenance"] == batch_result["provenance"]
    assert batch_result["ordered_metrics"] == [
        "blue_active",
        "blue_destroyed",
        "red_active",
        "red_destroyed",
    ]
    assert all(len(values) == 2 for values in batch_result["raw_metrics"].values())
    assert any(
        value < initial
        for metric, initial in (("blue_active", 4), ("red_active", 6))
        for value in batch_result["raw_metrics"][metric]
    )
    for metric, values in batch_result["raw_metrics"].items():
        statistics = batch_result["statistics"][metric]
        assert statistics["n"] == 2
        assert statistics["mean"] == pytest.approx(sum(values) / 2)

    provenance = batch_result["provenance"]
    assert provenance["seeds"] == [42, 43]
    assert len(provenance["source_fingerprint"]) == 64
    assert len(provenance["config_fingerprint"]) == 64
    assert len(provenance["data_revision"]) == 64
    assert len(provenance["catalog_revision"]) == 64
    assert len(provenance["doctrine_catalog_fingerprint"]) == 64
    assert len(provenance["loaded_roster_loadout_fingerprint"]) == 64
    assert provenance["initial_unit_assignments"]
    assert len(provenance["runs"]) == 2
    for run in provenance["runs"]:
        assert run["game_over"] is True
        _assert_runtime_provenance(run["runtime_provenance"])


async def test_iteration_two_failure_survives_reopen_without_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "phase112-failure.db"
    settings = ApiSettings(
        db_path=str(database_path),
        data_dir="data",
    )
    app = create_app(settings)

    def fail_on_second_iteration(self, variant_id, **kwargs):
        del self, variant_id
        kwargs["progress_callback"](
            1,
            kwargs["num_iterations"],
            kwargs["base_seed"],
        )
        raise RuntimeError("phase112 iteration 2 failure")

    monkeypatch.setattr(
        AnalysisRunner,
        "run_variant",
        fail_on_second_iteration,
    )
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/runs/batch",
                json={
                    "scenario": "test_campaign",
                    "num_iterations": 3,
                    "base_seed": 42,
                    "max_ticks": 50,
                },
            )
            assert response.status_code == 202
            batch_id = response.json()["batch_id"]
            detail = await _wait_for_status(
                client,
                f"/api/runs/batch/{batch_id}",
                {"failed"},
            )
            assert detail["raw_metrics"] is None
            assert detail["provenance"] is None

    reopened = Database(str(database_path))
    await reopened.initialize()
    try:
        row = await reopened.get_batch(batch_id)
    finally:
        await reopened.close()

    assert row is not None
    assert row["status"] == "failed"
    assert row["completed_iterations"] == 1
    assert row["metrics_json"] is None
    assert row["error_message"] == "phase112 iteration 2 failure"
