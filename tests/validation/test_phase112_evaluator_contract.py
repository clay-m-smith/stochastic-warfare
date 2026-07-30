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
    assert cambrai["ticks_executed"] == 433
    assert cambrai["victory_side"] == "british"
    assert cambrai["victory_condition"] == "force_destroyed"
    assert cambrai["total_casualties"] == 2
    assert cambrai["engagement_events"] == 14
    assert cambrai["units_that_moved"] == 3
    assert cambrai["units_that_didnt_move"] == 7
    assert cambrai["total_events"] == 504
    assert cambrai["event_type_counts"] == {
        "DamageEvent": 12,
        "DecisionMadeEvent": 75,
        "EngagementEvent": 12,
        "MoraleStateChangeEvent": 6,
        "ObjectiveControlChangedEvent": 1,
        "OODAPhaseChangeEvent": 311,
        "SituationAssessedEvent": 84,
        "UnitDestroyedEvent": 2,
        "VictoryDeclaredEvent": 1,
    }
    c2_event_types = {
        "DecisionMadeEvent",
        "OODAPhaseChangeEvent",
        "SituationAssessedEvent",
    }
    assert (
        sum(count for event_type, count in cambrai["event_type_counts"].items() if event_type not in c2_event_types)
        == 34
    )
    assert cambrai["engagement_weapon_counts"] == {
        "lee_enfield": 12,
    }
    mark_ivs = [detail for detail in cambrai["unit_details"] if detail["unit_type"] == "mark_iv_tank"]
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
        assert detail["movement_disposition"] == "ENGINE_WEAPON_STANDOFF"

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
