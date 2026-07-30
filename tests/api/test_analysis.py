"""Tests for analysis endpoints (compare, sweep, tempo)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from httpx import ASGITransport, AsyncClient
import pytest
import yaml

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


def _assert_complete_batch(
    batch: dict,
    *,
    seeds: list[int],
) -> None:
    assert batch["seeds"] == seeds
    assert len(batch["source_fingerprint"]) == 64
    assert len(batch["config_fingerprint"]) == 64
    assert len(batch["data_revision"]) == 64
    assert batch["data_file_count"] > 0
    assert len(batch["catalog_revision"]) == 64
    assert len(batch["doctrine_catalog_fingerprint"]) == 64
    assert len(batch["loaded_roster_loadout_fingerprint"]) == 64
    assert batch["initial_unit_assignments"]
    assert len(batch["runs"]) == len(seeds)
    assert [run["seed"] for run in batch["runs"]] == seeds
    assert all(run["game_over"] is True for run in batch["runs"])
    for run in batch["runs"]:
        provenance = run["runtime_provenance"]
        assert len(provenance["data_revision"]) == 64
        assert len(provenance["catalog_revision"]) == 64
        assert len(provenance["doctrine_catalog_fingerprint"]) == 64
        assert len(provenance["doctrine_assignment_fingerprint"]) == 64
        assert (
            len(
                provenance["loaded_roster_loadout_fingerprint"],
            )
            == 64
        )
        assert (
            len(
                provenance["final_roster_loadout_fingerprint"],
            )
            == 64
        )


@pytest.mark.parametrize(
    "scenario",
    (
        "",
        " test_campaign",
        "test_campaign ",
        ".",
        "..",
        "../eras/napoleonic/scenarios/austerlitz",
        "test_campaign/scenario.yaml",
        r"..\eras\napoleonic\scenarios\austerlitz",
    ),
)
async def test_scenario_identifiers_are_strict_across_run_and_analysis_apis(
    client,
    app,
    scenario: str,
) -> None:
    requests = (
        (
            "/api/runs",
            {
                "scenario": scenario,
                "seed": 42,
                "max_ticks": 1,
            },
        ),
        (
            "/api/runs/batch",
            {
                "scenario": scenario,
                "num_iterations": 2,
                "base_seed": 42,
                "max_ticks": 1,
            },
        ),
        (
            "/api/analysis/compare",
            {
                "scenario": scenario,
                "num_iterations": 2,
                "max_ticks": 1,
            },
        ),
        (
            "/api/analysis/sweep",
            {
                "scenario": scenario,
                "parameter_name": "hit_probability_modifier",
                "values": [1.0, 2.0],
                "num_iterations": 2,
                "max_ticks": 1,
            },
        ),
        (
            "/api/analysis/doctrine-compare",
            {
                "scenario": scenario,
                "variants": [
                    {
                        "variant_id": "maneuverist",
                        "assignments": [
                            {
                                "side": "blue",
                                "school_id": "maneuverist",
                            },
                        ],
                    },
                    {
                        "variant_id": "attrition",
                        "assignments": [
                            {
                                "side": "blue",
                                "school_id": "attrition",
                            },
                        ],
                    },
                ],
                "num_iterations": 2,
                "max_ticks": 1,
            },
        ),
    )

    for endpoint, payload in requests:
        response = await client.post(
            endpoint,
            content=json.dumps(payload, allow_nan=True),
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 422, (
            endpoint,
            response.text,
        )
        assert "non-empty trimmed string" in response.text
    assert await app.state.db.count_runs() == 0
    assert app.state.run_manager._tasks == {}


async def test_compare_endpoint(client):
    resp = await client.post(
        "/api/analysis/compare",
        json={
            "scenario": "test_campaign",
            "overrides_a": {},
            "overrides_b": {"hit_probability_modifier": 2.0},
            "num_iterations": 3,
            "max_ticks": 20,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "label_a" in data
    assert "label_b" in data
    assert "metrics" in data
    assert data["seeds"] == [42, 43, 44]
    assert data["ordered_metrics"] == [
        "blue_destroyed",
        "red_destroyed",
    ]
    assert len(data["raw_a"]["blue_destroyed"]) == 3
    assert len(data["raw_b"]["blue_destroyed"]) == 3
    metric = data["metrics"][0]
    assert "raw_p_value" in metric
    assert "holm_adjusted_p_value" in metric
    assert "positive" in metric
    assert "negative" in metric
    assert "tied" in metric
    assert "u_statistic" not in metric
    assert "effect_size" not in metric


async def test_compare_exposes_complete_batches_and_outcome_effect(client):
    resp = await client.post(
        "/api/analysis/compare",
        json={
            "scenario": "test_campaign",
            "overrides_a": {"hit_probability_modifier": 0.0},
            "overrides_b": {"hit_probability_modifier": 10.0},
            "metrics": ["blue_destroyed", "red_destroyed"],
            "num_iterations": 3,
            "base_seed": 42,
            "max_ticks": 50,
        },
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["seeds"] == [42, 43, 44]
    assert any(data["raw_a"][metric] != data["raw_b"][metric] for metric in data["ordered_metrics"])
    _assert_complete_batch(data["batch_a"], seeds=[42, 43, 44])
    _assert_complete_batch(data["batch_b"], seeds=[42, 43, 44])
    assert data["batch_a"]["metric_vectors"] != (data["batch_b"]["metric_vectors"])


async def test_omitted_metrics_derive_exact_non_blue_red_side_ids(
    client,
) -> None:
    compare = await client.post(
        "/api/analysis/compare",
        json={
            "scenario": "austerlitz",
            "num_iterations": 2,
            "max_ticks": 1,
        },
    )
    sweep = await client.post(
        "/api/analysis/sweep",
        json={
            "scenario": "austerlitz",
            "parameter_name": "hit_probability_modifier",
            "values": [1.0],
            "num_iterations": 2,
            "max_ticks": 1,
        },
    )
    doctrine = await client.post(
        "/api/analysis/doctrine-compare",
        json={
            "scenario": "austerlitz",
            "variants": [
                {
                    "variant_id": "maneuverist",
                    "assignments": [
                        {
                            "side": "french",
                            "school_id": "maneuverist",
                        },
                    ],
                },
                {
                    "variant_id": "attrition",
                    "assignments": [
                        {
                            "side": "french",
                            "school_id": "attrition",
                        },
                    ],
                },
            ],
            "num_iterations": 2,
            "max_ticks": 1,
        },
    )

    expected = [
        "french_destroyed",
        "coalition_destroyed",
    ]
    for response in (compare, sweep, doctrine):
        assert response.status_code == 200, response.text
    assert compare.json()["ordered_metrics"] == expected
    assert sweep.json()["ordered_metrics"] == expected
    assert doctrine.json()["ordered_metrics"] == [
        *expected,
        "ticks_executed",
    ]


async def test_compare_not_found(client):
    resp = await client.post(
        "/api/analysis/compare",
        json={
            "scenario": "nonexistent_scenario",
            "num_iterations": 3,
            "max_ticks": 20,
        },
    )
    assert resp.status_code == 404


async def test_unexpected_analysis_runtime_failure_remains_http_500(
    app,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_unexpectedly(_config) -> None:
        raise RuntimeError("phase112 unexpected internal failure")

    monkeypatch.setattr(
        "stochastic_warfare.tools.comparison.run_comparison",
        fail_unexpectedly,
    )
    transport = ASGITransport(
        app=app,
        raise_app_exceptions=False,
    )
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as isolated_client:
        response = await isolated_client.post(
            "/api/analysis/compare",
            json={
                "scenario": "test_campaign",
                "num_iterations": 2,
                "max_ticks": 1,
            },
        )

    assert response.status_code == 500
    assert "phase112 unexpected internal failure" not in response.text


async def test_sweep_endpoint(client):
    resp = await client.post(
        "/api/analysis/sweep",
        json={
            "scenario": "test_campaign",
            "parameter_name": "hit_probability_modifier",
            "values": [0.5, 1.0, 2.0],
            "num_iterations": 2,
            "max_ticks": 20,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "parameter_name" in data
    assert "points" in data
    assert len(data["points"]) == 3
    assert data["seeds"] == [42, 43]
    assert data["ordered_metrics"] == [
        "blue_destroyed",
        "red_destroyed",
    ]
    assert all(len(metric["values"]) == 2 for point in data["points"] for metric in point["metric_results"])
    assert len(data["source_fingerprint"]) == 64


async def test_sweep_exposes_complete_batches_and_outcome_effect(client):
    resp = await client.post(
        "/api/analysis/sweep",
        json={
            "scenario": "test_campaign",
            "parameter_name": "hit_probability_modifier",
            "values": [0.0, 10.0],
            "metrics": ["blue_destroyed", "red_destroyed"],
            "num_iterations": 3,
            "base_seed": 42,
            "max_ticks": 50,
        },
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["seeds"] == [42, 43, 44]
    assert [point["parameter_value"] for point in data["points"]] == [
        0.0,
        10.0,
    ]
    for point in data["points"]:
        _assert_complete_batch(point["batch"], seeds=[42, 43, 44])
    vectors = [{metric["metric"]: metric["values"] for metric in point["metric_results"]} for point in data["points"]]
    assert any(vectors[0][metric] != vectors[1][metric] for metric in data["ordered_metrics"])


async def test_analysis_rejects_unknown_metrics_and_overrides(client):
    unknown_metric = await client.post(
        "/api/analysis/compare",
        json={
            "scenario": "test_campaign",
            "metrics": ["unsupported_metric"],
            "num_iterations": 2,
            "max_ticks": 1,
        },
    )
    assert unknown_metric.status_code == 422
    assert "unsupported_metric" in unknown_metric.text

    unknown_override = await client.post(
        "/api/analysis/sweep",
        json={
            "scenario": "test_campaign",
            "parameter_name": "not_a_calibration_field",
            "values": [1.0],
            "num_iterations": 2,
            "max_ticks": 1,
        },
    )
    assert unknown_override.status_code == 422
    assert "not_a_calibration_field" in unknown_override.text

    dead_sweep = await client.post(
        "/api/analysis/sweep",
        json={
            "scenario": "test_campaign",
            "parameter_name": "advance_speed",
            "values": [1.0, 999.0],
            "num_iterations": 2,
            "max_ticks": 1,
        },
    )
    assert dead_sweep.status_code == 422
    assert "advance_speed" in dead_sweep.text

    dead_compare = await client.post(
        "/api/analysis/compare",
        json={
            "scenario": "test_campaign",
            "overrides_a": {"advance_speed": 1.0},
            "overrides_b": {"advance_speed": 999.0},
            "num_iterations": 2,
            "max_ticks": 1,
        },
    )
    assert dead_compare.status_code == 422
    assert "advance_speed" in dead_compare.text

    malformed_label = await client.post(
        "/api/analysis/compare",
        json={
            "scenario": "test_campaign",
            "label_a": "",
            "num_iterations": 2,
            "max_ticks": 1,
        },
    )
    assert malformed_label.status_code == 422

    malformed_parameter = await client.post(
        "/api/analysis/sweep",
        json={
            "scenario": "test_campaign",
            "parameter_name": " ",
            "values": [1.0, 2.0],
            "num_iterations": 2,
            "max_ticks": 1,
        },
    )
    assert malformed_parameter.status_code == 422


async def test_nonfinite_calibration_is_http_422_for_every_request_boundary(
    client,
    app,
) -> None:
    requests = (
        (
            "/api/runs",
            {
                "scenario": "test_campaign",
                "seed": 42,
                "max_ticks": 1,
                "config_overrides": {
                    "hit_probability_modifier": float("nan"),
                },
            },
        ),
        (
            "/api/runs/batch",
            {
                "scenario": "test_campaign",
                "num_iterations": 2,
                "base_seed": 42,
                "max_ticks": 1,
                "config_overrides": {
                    "hit_probability_modifier": float("inf"),
                },
            },
        ),
        (
            "/api/analysis/compare",
            {
                "scenario": "test_campaign",
                "overrides_a": {
                    "hit_probability_modifier": float("-inf"),
                },
                "num_iterations": 2,
                "max_ticks": 1,
            },
        ),
        (
            "/api/analysis/doctrine-compare",
            {
                "scenario": "test_campaign",
                "variants": [
                    {
                        "variant_id": "maneuverist",
                        "assignments": [
                            {
                                "side": "blue",
                                "school_id": "maneuverist",
                            },
                        ],
                        "calibration_patch": {
                            "hit_probability_modifier": float("inf"),
                        },
                    },
                    {
                        "variant_id": "attrition",
                        "assignments": [
                            {
                                "side": "blue",
                                "school_id": "attrition",
                            },
                        ],
                        "calibration_patch": {
                            "hit_probability_modifier": float("inf"),
                        },
                    },
                ],
                "num_iterations": 2,
                "max_ticks": 1,
            },
        ),
    )

    for endpoint, payload in requests:
        response = await client.post(
            endpoint,
            content=json.dumps(payload, allow_nan=True),
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 422, (
            endpoint,
            response.text,
        )
        assert "finite" in response.text
    assert await app.state.db.count_runs() == 0
    assert app.state.run_manager._tasks == {}


async def test_duplicate_calibration_paths_are_http_422(
    client,
    app,
) -> None:
    payload = {
        "scenario": "test_campaign",
        "seed": 42,
        "max_ticks": 1,
        "config_overrides": {
            "morale": {"base_degrade_rate": 0.1},
            "morale_base_degrade_rate": 0.9,
        },
    }

    response = await client.post("/api/runs", json=payload)

    assert response.status_code == 422
    assert "duplicate semantic calibration path" in response.text
    assert await app.state.db.count_runs() == 0
    assert app.state.run_manager._tasks == {}


async def test_analysis_routes_map_real_missing_unit_input_to_422(
    client,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = Path("data/scenarios/test_campaign/scenario.yaml")
    config = yaml.safe_load(source.read_text(encoding="utf-8"))
    missing_type = "phase112_missing_unit_definition"
    config["sides"][0]["units"][0]["unit_type"] = missing_type
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        yaml.safe_dump(config),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "api.routers.analysis.resolve_scenario",
        lambda _name, _data_dir: scenario_path,
    )

    requests = [
        (
            "/api/analysis/compare",
            {
                "scenario": "missing-unit",
                "num_iterations": 2,
                "max_ticks": 1,
            },
        ),
        (
            "/api/analysis/sweep",
            {
                "scenario": "missing-unit",
                "parameter_name": "hit_probability_modifier",
                "values": [1.0, 2.0],
                "num_iterations": 2,
                "max_ticks": 1,
            },
        ),
        (
            "/api/analysis/doctrine-compare",
            {
                "scenario": "missing-unit",
                "variants": [
                    {
                        "variant_id": "maneuverist",
                        "assignments": [
                            {
                                "side": "blue",
                                "school_id": "maneuverist",
                            },
                        ],
                    },
                    {
                        "variant_id": "attrition",
                        "assignments": [
                            {
                                "side": "blue",
                                "school_id": "attrition",
                            },
                        ],
                    },
                ],
                "metrics": ["blue_destroyed"],
                "num_iterations": 2,
                "max_ticks": 1,
            },
        ),
    ]
    for endpoint, payload in requests:
        response = await client.post(endpoint, json=payload)
        assert response.status_code == 422, response.text
        assert missing_type in response.text


async def test_analysis_maps_unknown_scenario_references_to_422(
    client,
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
            "phase112_unknown_battery",
        ),
    )

    for scenario_name, config, expected in invalid_cases:
        scenario_path = tmp_path / f"{scenario_name}.yaml"
        scenario_path.write_text(
            yaml.safe_dump(config, sort_keys=False),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "api.routers.analysis.resolve_scenario",
            lambda _name, _data_dir, path=scenario_path: path,
        )
        requests = (
            (
                "/api/analysis/compare",
                {
                    "scenario": scenario_name,
                    "num_iterations": 2,
                    "max_ticks": 1,
                },
            ),
            (
                "/api/analysis/sweep",
                {
                    "scenario": scenario_name,
                    "parameter_name": "hit_probability_modifier",
                    "values": [1.0, 2.0],
                    "num_iterations": 2,
                    "max_ticks": 1,
                },
            ),
            (
                "/api/analysis/doctrine-compare",
                {
                    "scenario": scenario_name,
                    "variants": [
                        {
                            "variant_id": "maneuverist",
                            "assignments": [
                                {
                                    "side": "blue",
                                    "school_id": "maneuverist",
                                },
                            ],
                        },
                        {
                            "variant_id": "attrition",
                            "assignments": [
                                {
                                    "side": "blue",
                                    "school_id": "attrition",
                                },
                            ],
                        },
                    ],
                    "metrics": ["blue_destroyed"],
                    "num_iterations": 2,
                    "max_ticks": 1,
                },
            ),
        )
        for endpoint, payload in requests:
            response = await client.post(endpoint, json=payload)
            assert response.status_code == 422, (
                endpoint,
                response.text,
            )
            assert expected in response.text


async def test_sweep_not_found(client):
    resp = await client.post(
        "/api/analysis/sweep",
        json={
            "scenario": "nonexistent_scenario",
            "parameter_name": "hit_probability_modifier",
            "values": [1.0],
        },
    )
    assert resp.status_code == 404


async def test_doctrine_compare_uses_typed_policies_and_provenance(client):
    def request_payload(modifier: float) -> dict:
        return {
            "scenario": "test_campaign",
            "variants": [
                {
                    "variant_id": "maneuverist",
                    "calibration_patch": {
                        "hit_probability_modifier": modifier,
                    },
                    "assignments": [
                        {"side": "blue", "school_id": "maneuverist"},
                    ],
                },
                {
                    "variant_id": "attrition",
                    "calibration_patch": {
                        "hit_probability_modifier": modifier,
                    },
                    "assignments": [
                        {"side": "blue", "school_id": "attrition"},
                    ],
                },
            ],
            "metrics": ["blue_destroyed", "red_destroyed"],
            "num_iterations": 3,
            "base_seed": 42,
            "max_ticks": 50,
        }

    zero_response = await client.post(
        "/api/analysis/doctrine-compare",
        json=request_payload(0.0),
    )
    ten_response = await client.post(
        "/api/analysis/doctrine-compare",
        json=request_payload(10.0),
    )

    assert zero_response.status_code == 200, zero_response.text
    assert ten_response.status_code == 200, ten_response.text
    zero = zero_response.json()
    ten = ten_response.json()
    for data in (zero, ten):
        assert data["seeds"] == [42, 43, 44]
        assert data["ordered_metrics"] == [
            "blue_destroyed",
            "red_destroyed",
        ]
        assert [result["variant_id"] for result in data["results"]] == [
            "maneuverist",
            "attrition",
        ]
        for result in data["results"]:
            assert result["assignments"] == [
                {
                    "side": "blue",
                    "school_id": result["variant_id"],
                }
            ]
            assert all(len(metric["values"]) == 3 for metric in result["metrics"])
            batch = result["batch"]
            assert batch["seeds"] == [42, 43, 44]
            assert len(batch["source_fingerprint"]) == 64
            assert len(batch["config_fingerprint"]) == 64
            assert len(batch["data_revision"]) == 64
            for run in batch["runs"]:
                provenance = run["runtime_provenance"]
                assert len(provenance["catalog_revision"]) == 64
                assert (
                    len(
                        provenance["doctrine_catalog_fingerprint"],
                    )
                    == 64
                )
                assert (
                    len(
                        provenance["doctrine_assignment_fingerprint"],
                    )
                    == 64
                )
                assert (
                    len(
                        provenance["loaded_roster_loadout_fingerprint"],
                    )
                    == 64
                )
                assert (
                    len(
                        provenance["final_roster_loadout_fingerprint"],
                    )
                    == 64
                )

    zero_vectors = {
        result["variant_id"]: {metric["metric"]: metric["values"] for metric in result["metrics"]}
        for result in zero["results"]
    }
    ten_vectors = {
        result["variant_id"]: {metric["metric"]: metric["values"] for metric in result["metrics"]}
        for result in ten["results"]
    }
    assert any(zero_vectors[variant_id] != ten_vectors[variant_id] for variant_id in zero_vectors)


async def test_doctrine_compare_rejects_legacy_and_unknown_policies(client):
    legacy = await client.post(
        "/api/analysis/doctrine-compare",
        json={
            "scenario": "test_campaign",
            "side_to_vary": "blue",
            "schools": ["maneuverist", "attrition"],
            "num_iterations": 2,
        },
    )
    assert legacy.status_code == 422

    one_iteration = await client.post(
        "/api/analysis/doctrine-compare",
        json={
            "scenario": "test_campaign",
            "variants": [
                {
                    "variant_id": "maneuverist",
                    "assignments": [
                        {"side": "blue", "school_id": "maneuverist"},
                    ],
                },
                {
                    "variant_id": "attrition",
                    "assignments": [
                        {"side": "blue", "school_id": "attrition"},
                    ],
                },
            ],
            "num_iterations": 1,
        },
    )
    assert one_iteration.status_code == 422

    unknown_school = await client.post(
        "/api/analysis/doctrine-compare",
        json={
            "scenario": "test_campaign",
            "variants": [
                {
                    "variant_id": "unknown",
                    "assignments": [
                        {"side": "blue", "school_id": "not_a_school"},
                    ],
                },
                {
                    "variant_id": "attrition",
                    "assignments": [
                        {"side": "blue", "school_id": "attrition"},
                    ],
                },
            ],
            "num_iterations": 2,
            "max_ticks": 1,
        },
    )
    assert unknown_school.status_code == 422
    assert "not_a_school" in unknown_school.text

    mismatched_calibration = await client.post(
        "/api/analysis/doctrine-compare",
        json={
            "scenario": "test_campaign",
            "variants": [
                {
                    "variant_id": "maneuverist",
                    "assignments": [
                        {"side": "blue", "school_id": "maneuverist"},
                    ],
                    "calibration_patch": {
                        "hit_probability_modifier": 0.0,
                    },
                },
                {
                    "variant_id": "attrition",
                    "assignments": [
                        {"side": "blue", "school_id": "attrition"},
                    ],
                    "calibration_patch": {
                        "hit_probability_modifier": 10.0,
                    },
                },
            ],
            "num_iterations": 2,
            "max_ticks": 1,
        },
    )
    assert mismatched_calibration.status_code == 422
    assert "hold calibration patches identical" in (mismatched_calibration.text)

    identical_policies = await client.post(
        "/api/analysis/doctrine-compare",
        json={
            "scenario": "test_campaign",
            "variants": [
                {
                    "variant_id": "first",
                    "assignments": [
                        {
                            "side": "blue",
                            "school_id": "maneuverist",
                        },
                        {
                            "side": "red",
                            "school_id": "attrition",
                        },
                    ],
                },
                {
                    "variant_id": "second",
                    "assignments": [
                        {
                            "side": "red",
                            "school_id": "attrition",
                        },
                        {
                            "side": "blue",
                            "school_id": "maneuverist",
                        },
                    ],
                },
            ],
            "num_iterations": 2,
            "max_ticks": 1,
        },
    )
    assert identical_policies.status_code == 422
    assert "distinct assignment policies" in identical_policies.text


async def test_doctrine_compare_accepts_equivalent_calibration_aliases(
    client,
) -> None:
    response = await client.post(
        "/api/analysis/doctrine-compare",
        json={
            "scenario": "test_campaign",
            "variants": [
                {
                    "variant_id": "maneuverist",
                    "assignments": [
                        {
                            "side": "blue",
                            "school_id": "maneuverist",
                        },
                    ],
                    "calibration_patch": {
                        "morale_degrade_rate_modifier": 0.4,
                    },
                },
                {
                    "variant_id": "attrition",
                    "assignments": [
                        {
                            "side": "blue",
                            "school_id": "attrition",
                        },
                    ],
                    "calibration_patch": {
                        "morale": {
                            "degrade_rate_modifier": 0.4,
                        },
                    },
                },
            ],
            "num_iterations": 2,
            "base_seed": 42,
            "max_ticks": 1,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["seeds"] == [42, 43]


async def test_tempo_endpoint(client):
    # First submit and complete a run
    resp = await client.post(
        "/api/runs",
        json={
            "scenario": "test_campaign",
            "seed": 42,
            "max_ticks": 50,
        },
    )
    run_id = resp.json()["run_id"]

    for _ in range(60):
        resp = await client.get(f"/api/runs/{run_id}")
        if resp.json()["status"] == "completed":
            break
        await asyncio.sleep(0.5)
    else:
        pytest.fail("Run did not complete")

    resp = await client.get(f"/api/analysis/tempo/{run_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


async def test_tempo_not_found(client):
    resp = await client.get("/api/analysis/tempo/nonexistent_id")
    assert resp.status_code == 404


async def test_tempo_no_events(client):
    # Submit a run with 0 max_ticks to get no events
    resp = await client.post(
        "/api/runs",
        json={
            "scenario": "test_campaign",
            "seed": 42,
            "max_ticks": 1,
        },
    )
    run_id = resp.json()["run_id"]

    for _ in range(60):
        resp = await client.get(f"/api/runs/{run_id}")
        if resp.json()["status"] in ("completed", "failed"):
            break
        await asyncio.sleep(0.5)

    resp = await client.get(f"/api/analysis/tempo/{run_id}")
    # Either 200 with empty result or 409 if no events
    assert resp.status_code in (200, 409)
