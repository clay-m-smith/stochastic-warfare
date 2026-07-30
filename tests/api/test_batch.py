"""Tests for batch/Monte Carlo execution."""

from __future__ import annotations

import asyncio

import pytest

from stochastic_warfare.tools._run_helpers import AnalysisRunner

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


async def test_submit_batch(client):
    resp = await client.post(
        "/api/runs/batch",
        json={
            "scenario": "test_campaign",
            "num_iterations": 3,
            "base_seed": 42,
            "max_ticks": 20,
        },
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "batch_id" in data
    assert data["status"] == "pending"


async def test_submit_batch_not_found(client):
    resp = await client.post(
        "/api/runs/batch",
        json={
            "scenario": "nonexistent_scenario",
            "num_iterations": 3,
            "base_seed": 42,
            "max_ticks": 20,
        },
    )
    assert resp.status_code == 404


async def test_unknown_metric_rejected_before_batch_publication(client, app):
    before_cursor = await app.state.db.conn.execute(
        "SELECT COUNT(*) FROM batches",
    )
    before_count = (await before_cursor.fetchone())[0]

    resp = await client.post(
        "/api/runs/batch",
        json={
            "scenario": "test_campaign",
            "num_iterations": 3,
            "base_seed": 42,
            "max_ticks": 20,
            "metrics": ["unsupported_phase112_metric"],
        },
    )

    assert resp.status_code == 422
    assert "unsupported_phase112_metric" in resp.json()["detail"]
    after_cursor = await app.state.db.conn.execute(
        "SELECT COUNT(*) FROM batches",
    )
    after_count = (await after_cursor.fetchone())[0]
    assert after_count == before_count
    assert app.state.run_manager._tasks == {}
    assert app.state.run_manager._progress_queues == {}
    assert app.state.run_manager._cancel_events == {}

    invalid_override = await client.post(
        "/api/runs/batch",
        json={
            "scenario": "test_campaign",
            "num_iterations": 3,
            "base_seed": 42,
            "max_ticks": 20,
            "config_overrides": {
                "hit_probability_modifier": "10.0",
            },
        },
    )
    assert invalid_override.status_code == 422
    oversized_seed = await client.post(
        "/api/runs/batch",
        json={
            "scenario": "test_campaign",
            "num_iterations": 3,
            "base_seed": 1 << 63,
            "max_ticks": 20,
        },
    )
    assert oversized_seed.status_code == 422
    final_cursor = await app.state.db.conn.execute(
        "SELECT COUNT(*) FROM batches",
    )
    final_count = (await final_cursor.fetchone())[0]
    assert final_count == before_count


async def test_batch_executes_one_full_authoritative_runner_call(
    client,
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[tuple[str, int, int, int]] = []
    original = AnalysisRunner.run_variant

    def recording_run(self, variant_id, **kwargs):
        calls.append(
            (
                variant_id,
                kwargs["num_iterations"],
                kwargs["base_seed"],
                kwargs["max_ticks"],
            )
        )
        return original(self, variant_id, **kwargs)

    monkeypatch.setattr(AnalysisRunner, "run_variant", recording_run)
    response = await client.post(
        "/api/runs/batch",
        json={
            "scenario": "test_campaign",
            "num_iterations": 3,
            "base_seed": 112,
            "max_ticks": 20,
        },
    )
    assert response.status_code == 202
    batch_id = response.json()["batch_id"]

    for _ in range(120):
        detail = await client.get(f"/api/runs/batch/{batch_id}")
        if detail.json()["status"] in ("completed", "failed"):
            break
        await asyncio.sleep(0.05)
    else:
        pytest.fail("Batch did not complete within timeout")

    payload = detail.json()
    assert payload["status"] == "completed", payload
    assert calls == [("batch", 3, 112, 20)]
    assert payload["provenance"]["seeds"] == [112, 113, 114]
    assert all(len(values) == 3 for values in payload["raw_metrics"].values())


async def test_failed_full_batch_never_persists_partial_metrics(
    client,
    app,
    monkeypatch: pytest.MonkeyPatch,
):
    def failing_run(self, variant_id, **kwargs):
        del self, variant_id
        kwargs["progress_callback"](
            1,
            kwargs["num_iterations"],
            kwargs["base_seed"],
        )
        raise RuntimeError("phase112 full-batch failure")

    monkeypatch.setattr(AnalysisRunner, "run_variant", failing_run)
    response = await client.post(
        "/api/runs/batch",
        json={
            "scenario": "test_campaign",
            "num_iterations": 3,
            "base_seed": 112,
            "max_ticks": 20,
        },
    )
    assert response.status_code == 202
    batch_id = response.json()["batch_id"]

    for _ in range(120):
        row = await app.state.db.get_batch(batch_id)
        assert row is not None
        if row["status"] == "failed":
            break
        await asyncio.sleep(0.05)
    else:
        pytest.fail("Failed batch did not reach durable terminal state")

    assert row["completed_iterations"] == 1
    assert row["metrics_json"] is None
    assert row["error_message"] == "phase112 full-batch failure"


async def test_submit_and_poll_batch(client):
    async def submit_and_wait(modifier: float) -> dict:
        response = await client.post(
            "/api/runs/batch",
            json={
                "scenario": "test_campaign",
                "num_iterations": 3,
                "base_seed": 42,
                "max_ticks": 50,
                "metrics": ["blue_destroyed", "red_destroyed"],
                "config_overrides": {
                    "hit_probability_modifier": modifier,
                },
            },
        )
        assert response.status_code == 202, response.text
        batch_id = response.json()["batch_id"]

        for _ in range(120):
            response = await client.get(
                f"/api/runs/batch/{batch_id}",
            )
            payload = response.json()
            if payload["status"] in ("completed", "failed"):
                return payload
            await asyncio.sleep(0.05)
        pytest.fail("Batch did not complete within timeout")

    zero = await submit_and_wait(0.0)
    ten = await submit_and_wait(10.0)

    for data in (zero, ten):
        assert data["status"] == "completed", data
        assert data["completed_iterations"] == 3
        assert data["base_seed"] == 42
        assert data["max_ticks"] == 50
        assert data["metrics"] is not None
        assert isinstance(data["metrics"], dict)
        assert data["ordered_metrics"] == [
            "blue_destroyed",
            "red_destroyed",
        ]
        assert all(len(values) == 3 for values in data["raw_metrics"].values())
        assert data["provenance"]["seeds"] == [42, 43, 44]
        assert len(data["provenance"]["source_fingerprint"]) == 64
        assert len(data["provenance"]["config_fingerprint"]) == 64
        assert len(data["provenance"]["runs"]) == 3

    assert zero["provenance"]["config_fingerprint"] != ten["provenance"]["config_fingerprint"]
    assert any(zero["raw_metrics"][metric] != ten["raw_metrics"][metric] for metric in zero["ordered_metrics"])


async def test_batch_metrics_have_stats(client):
    resp = await client.post(
        "/api/runs/batch",
        json={
            "scenario": "test_campaign",
            "num_iterations": 3,
            "base_seed": 42,
            "max_ticks": 20,
        },
    )
    batch_id = resp.json()["batch_id"]

    for _ in range(120):
        resp = await client.get(f"/api/runs/batch/{batch_id}")
        data = resp.json()
        if data["status"] in ("completed", "failed"):
            break
        await asyncio.sleep(0.5)

    if data["status"] == "completed" and data["metrics"]:
        for metric_name, stats in data["metrics"].items():
            assert "mean" in stats
            assert "std" in stats
            assert "min" in stats
            assert "max" in stats
            assert "n" in stats


async def test_get_batch_not_found(client):
    resp = await client.get("/api/runs/batch/nonexistent_id")
    assert resp.status_code == 404
