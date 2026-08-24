"""Public API proof for the Phase 118 performance support disposition."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
import pytest

from stochastic_warfare.simulation.performance_flags import (
    PERFORMANCE_FLAG_REGISTRY,
    PERFORMANCE_SEMANTIC_EVIDENCE_MANIFEST_SHA256,
    PERFORMANCE_SEMANTIC_EVIDENCE_PLAN_ID,
)


pytestmark = [pytest.mark.api, pytest.mark.asyncio]


async def test_performance_flag_support_projection_is_exact_and_canonical(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/meta/performance-flags")

    assert response.status_code == 200
    payload = response.json()
    assert [item["flag"] for item in payload] == [
        "enable_detection_culling",
        "enable_scan_scheduling",
        "enable_lod",
        "enable_soa",
        "enable_parallel_detection",
    ]
    assert [item["classification"] for item in payload] == [
        "semantics_preserving_execution_optimization",
        "model_fidelity_approximation",
        "model_fidelity_approximation",
        "semantics_preserving_execution_optimization",
        "semantics_preserving_execution_optimization",
    ]
    assert [item["support_disposition"] for item in payload] == [
        "supported_exact_validated",
        "unsupported_failed_semantic_validation",
        "unsupported_failed_semantic_validation",
        "supported_exact_validated",
        "supported_exact_validated",
    ]
    assert [item["retained_shard_status"] for item in payload] == [
        "PASS",
        "FAIL",
        "FAIL",
        "PASS",
        "PASS",
    ]
    assert len({item["flag"] for item in payload}) == len(payload) == 5

    expected_keys = {
        "flag",
        "classification",
        "support_disposition",
        "required_meaning",
        "evidence_plan_id",
        "evidence_manifest_artifact_sha256",
        "retained_shard_status",
    }
    for item, definition in zip(
        payload,
        PERFORMANCE_FLAG_REGISTRY.values(),
        strict=True,
    ):
        assert set(item) == expected_keys
        assert item["required_meaning"] == definition.required_meaning
        assert item["evidence_plan_id"] == PERFORMANCE_SEMANTIC_EVIDENCE_PLAN_ID
        assert item["evidence_manifest_artifact_sha256"] == PERFORMANCE_SEMANTIC_EVIDENCE_MANIFEST_SHA256


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    (
        ("enable_scan_scheduling", True),
        ("enable_lod", True),
        ("lod_nearby_interval", 6),
        ("lod_distant_interval", 21),
        ("lod_hysteresis_ticks", 4),
    ),
)
@pytest.mark.parametrize(
    ("endpoint", "payload"),
    (
        (
            "/api/runs",
            {
                "scenario": "test_campaign",
                "seed": 42,
                "max_ticks": 1,
                "config_overrides": {},
            },
        ),
        (
            "/api/analysis/compare",
            {
                "scenario": "test_campaign",
                "overrides_a": {},
                "overrides_b": {},
                "num_iterations": 2,
                "max_ticks": 1,
            },
        ),
        (
            "/api/analysis/sweep",
            {
                "scenario": "test_campaign",
                "parameter_name": "hit_probability_modifier",
                "values": [1.0],
                "num_iterations": 2,
                "max_ticks": 1,
            },
        ),
    ),
)
async def test_unsupported_performance_configuration_rejects_at_public_request_schema(
    client: AsyncClient,
    app: Any,
    field_name: str,
    invalid_value: bool | int,
    endpoint: str,
    payload: dict[str, object],
) -> None:
    request_payload = dict(payload)
    if endpoint == "/api/analysis/sweep":
        request_payload["parameter_name"] = field_name
        request_payload["values"] = [float(invalid_value)]
    else:
        override_key = "config_overrides" if endpoint == "/api/runs" else "overrides_b"
        request_payload[override_key] = {field_name: invalid_value}

    response = await client.post(endpoint, json=request_payload)

    assert response.status_code == 422
    assert field_name in response.text
    assert "unsupported" in response.text.lower()
    assert await app.state.db.count_runs() == 0
