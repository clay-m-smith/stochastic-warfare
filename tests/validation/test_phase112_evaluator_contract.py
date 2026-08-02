"""Fail-closed subprocess contract for the production scenario evaluator."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "evaluate_scenarios.py"
CAMBRAI_SCENARIO = ROOT / "data" / "eras" / "ww1" / "scenarios" / "cambrai" / "scenario.yaml"
REINFORCEMENT_SCENARIO = (
    ROOT
    / "data"
    / "scenarios"
    / "test_campaign_reinforce"
    / "scenario.yaml"
)


def _invoke(
    scenario_file: Path,
    output_file: Path,
    *,
    seed: int = 42,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--scenario-file",
            str(scenario_file),
            "--output",
            str(output_file),
            "--seed",
            str(seed),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_evaluator_process_rejects_error_and_preserves_cambrai_semantics(
    tmp_path: Path,
) -> None:
    """A load/run error must make the public process fail, never warn-success."""
    valid_output = tmp_path / "valid.json"
    valid = _invoke(CAMBRAI_SCENARIO, valid_output)
    assert valid.returncode == 0, valid.stderr + valid.stdout
    valid_payload = json.loads(
        valid_output.read_text(encoding="utf-8"),
    )
    assert len(valid_payload) == 1
    cambrai = valid_payload[0]
    assert cambrai["success"] is True
    assert "LOAD_OR_RUN_ERROR" not in cambrai["issues"]
    assert cambrai["ticks_executed"] == 156
    assert cambrai["victory_side"] == "british"
    assert cambrai["victory_condition"] == "force_destroyed"
    assert cambrai["total_casualties"] == 2
    assert cambrai["engagement_events"] == 0
    assert cambrai["units_that_moved"] == 7
    assert cambrai["units_that_didnt_move"] == 3
    assert cambrai["total_events"] == 190
    assert cambrai["event_type_counts"] == {
        "DecisionMadeEvent": 25,
        "MoraleStateChangeEvent": 23,
        "ObjectiveControlChangedEvent": 1,
        "OODAPhaseChangeEvent": 107,
        "RallyEvent": 1,
        "SituationAssessedEvent": 32,
        "VictoryDeclaredEvent": 1,
    }
    c2_event_types = {
        "DecisionMadeEvent",
        "OODAPhaseChangeEvent",
        "SituationAssessedEvent",
    }
    assert (
        sum(count for event_type, count in cambrai["event_type_counts"].items() if event_type not in c2_event_types)
        == 26
    )
    assert cambrai["engagement_weapon_counts"] == {}
    german_ids = {
        detail["entity_id"]
        for detail in cambrai["unit_details"]
        if detail["side"] == "german"
    }
    mark_ivs = [
        detail
        for detail in cambrai["unit_details"]
        if detail["unit_type"] == "mark_iv_tank"
    ]
    assert [detail["entity_id"] for detail in mark_ivs] == [
        "british_mark_iv_tank_0003",
        "british_mark_iv_tank_0004",
        "british_mark_iv_tank_0005",
        "british_mark_iv_tank_0006",
    ]
    for detail in mark_ivs:
        assert (
            cambrai["unit_combat_event_counts"].get(
                detail["entity_id"],
                {},
            )
            == {}
        )
        assert detail["movement_disposition"] == "MOVED"
        assert detail["distance_moved"] > 1_300.0
        assert detail["movement_reason_counts"]["MOVED"] == 156
        assert detail["movement_reason_counts"]["ENGINE_WEAPON_STANDOFF"] == 0
        final_order = detail["movement_final_order"]
        assert final_order["stage"] == "TACTICAL"
        assert detail["targeting_exposure_scope"] == "PRIVILEGED_ENGINE"
        assert detail["targeting_engine_tick"] == final_order["engine_tick"]
        assert detail["targeting_battle_id"] == final_order["battle_id"]
        assert detail["targeting_shooter_id"] == detail["entity_id"]
        assert detail["targeting_shooter_side"] == "british"
        assert detail["targeting_shooter_domain"] == "GROUND"
        assert detail["targeting_target_id"] in german_ids
        assert detail["targeting_target_side"] == "german"
        assert detail["targeting_target_domain"] == "GROUND"
        assert detail["targeting_weapon_id"] == "qf_6pdr_6cwt"
        assert detail["targeting_weapon_source_equipment_index"] == 0
        assert detail["targeting_weapon_modeled_role"] == (
            "ground_direct_fire"
        )
        assert detail["targeting_ammunition_id"] == "6pdr_hotchkiss_ap"
        assert detail["targeting_physical_max_range_m"] == 6_675.0
        assert detail["targeting_predictive_effective_range_m"] == 1_000.0
        assert detail["targeting_effective_range_basis"] == "AUTHORED"
        assert detail["targeting_legacy_derived_reference_range_m"] == (
            5_340.0
        )
        assert detail["targeting_distance_m"] > 1_000.0
        assert detail["targeting_contact_source"] == (
            "NON_FOW_LOCAL_OBSERVATION"
        )
        assert detail["targeting_observing_unit_id"] == detail["entity_id"]
        assert detail["targeting_contact_time_s"] == (
            detail["targeting_logical_time_s"]
        )
        assert detail["targeting_contact_sensor_source_equipment_index"] is None
        assert detail["targeting_contact_sensor_id"] is None
        assert detail["targeting_contact_sensor_modeled_role"] is None
        assert detail["targeting_sensing_sensor_source_equipment_index"] is None
        assert detail["targeting_sensing_sensor_id"] is None
        assert detail["targeting_sensing_sensor_modeled_role"] is None
        assert detail["targeting_contact_range_m"] >= (
            detail["targeting_distance_m"]
        )
        assert detail["targeting_sensing_range_m"] == (
            detail["targeting_contact_range_m"]
        )
        assert detail["targeting_fire_control_source"] == "DIRECT_VISUAL"
        assert detail["targeting_fire_control_sensor_source_equipment_index"] is None
        assert detail["targeting_fire_control_sensor_id"] is None
        assert detail["targeting_fire_control_sensor_modeled_role"] is None
        assert detail["targeting_fire_control_range_m"] == (
            detail["targeting_contact_range_m"]
        )
        assert detail["targeting_disposition"] == "OUTSIDE_EFFECTIVE_RANGE"
        # The old 80%-of-maximum value remains visible only as a labeled
        # diagnostic reference; it supplies no movement authorization.
        assert detail["targeting_legacy_derived_reference_range_m"] > (
            detail["targeting_predictive_effective_range_m"]
        )
        assert detail["targeting_authorized_standoff_m"] == 0.0
        assert detail["targeting_hold_authorized"] is False
        assert detail["targeting_engagement_solution_valid"] is False
        assert detail["targeting_sensing_aware_standoff_enabled"] is True
        assert detail["targeting_fog_of_war_enabled"] is False
        assert detail["targeting_consumable"] is True

    legacy_decisions = [
        detail
        for detail in cambrai["unit_details"]
        if detail["targeting_effective_range_basis"]
        == "LEGACY_DERIVED_80_PERCENT_OF_MAX"
    ]
    assert legacy_decisions
    for detail in legacy_decisions:
        assert detail["targeting_predictive_effective_range_m"] == 0.0
        assert detail["targeting_authorized_standoff_m"] == 0.0
        assert detail["targeting_hold_authorized"] is False
        assert detail["targeting_legacy_derived_reference_range_m"] == (
            0.8 * detail["targeting_physical_max_range_m"]
        )

    invalid_dir = tmp_path / "invalid"
    invalid_dir.mkdir()
    invalid_scenario = invalid_dir / "scenario.yaml"
    invalid_scenario.write_text(
        "name: Phase 112 evaluator invalid control\nsides: []\n",
        encoding="utf-8",
    )
    invalid_output = tmp_path / "invalid.json"
    invalid = _invoke(invalid_scenario, invalid_output)
    assert invalid.returncode == 1, invalid.stderr + invalid.stdout
    invalid_payload = json.loads(
        invalid_output.read_text(encoding="utf-8"),
    )
    assert len(invalid_payload) == 1
    assert invalid_payload[0]["success"] is False
    assert invalid_payload[0]["issues"] == ["LOAD_OR_RUN_ERROR"]


def test_evaluator_uses_every_constructed_unit_as_movement_denominator(
    tmp_path: Path,
) -> None:
    """Reinforcement movement counts must never be reported over the initial roster."""
    output = tmp_path / "reinforcement.json"
    completed = _invoke(
        REINFORCEMENT_SCENARIO,
        output,
        seed=112,
    )

    assert completed.returncode == 0, completed.stderr + completed.stdout
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert len(payload) == 1
    result = payload[0]
    assert result["success"] is True, result["error"]
    assert result["sides"] == {"blue": 2, "red": 4}
    assert result["initial_total"] == 6
    assert result["constructed_sides"] == {"blue": 6, "red": 7}
    assert result["constructed_total"] == 13
    assert len(result["unit_details"]) == 13
    assert (
        result["units_that_moved"] + result["units_that_didnt_move"]
        == result["constructed_total"]
    )
    assert (
        f"{result['units_that_moved']}/{result['constructed_total']}"
        in completed.stdout
    )
    assert (
        f"{result['units_that_didnt_move']}/{result['constructed_total']}"
        in completed.stdout
    )
    assert "13/6" not in completed.stdout
