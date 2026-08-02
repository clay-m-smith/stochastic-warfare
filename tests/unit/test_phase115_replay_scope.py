"""Phase 115 replay privilege-scope regression tests."""

from __future__ import annotations

from copy import deepcopy

import pytest

from stochastic_warfare.simulation.targeting_exposure import (
    TargetingExposureScope,
)
from stochastic_warfare.tools.replay import extract_replay_frames


def _privileged_decision(*, battle_id: str) -> dict[str, object]:
    return {
        "engine_tick": 7,
        "logical_time_s": 30.0,
        "battle_id": battle_id,
        "ordinal": 0,
        "shooter_id": "blue-1",
        "shooter_side": "blue",
        "shooter_domain": "GROUND",
        "target_id": "red-1",
        "target_side": "red",
        "target_domain": "GROUND",
        "distance_m": 500.0,
        "weapon_id": "direct-gun",
        "weapon_source_equipment_index": 2,
        "weapon_modeled_role": "ground_direct_fire",
        "ammunition_id": "direct-shell",
        "physical_max_range_m": 1_000.0,
        "predictive_effective_range_m": 800.0,
        "effective_range_basis": "AUTHORED",
        "legacy_derived_reference_range_m": 800.0,
        "contact_source": "FOW_OBSERVER_WITNESS",
        "observing_unit_id": "blue-1",
        "contact_sensor_source_equipment_index": 3,
        "contact_sensor_id": "hidden-binocular-attachment",
        "contact_sensor_modeled_role": "visual_observation",
        "contact_time_s": 30.0,
        "contact_range_m": 500.0,
        "visibility_bound_m": 1_000.0,
        "sensing_sensor_source_equipment_index": 3,
        "sensing_sensor_id": "hidden-binocular-attachment",
        "sensing_sensor_modeled_role": "visual_observation",
        "sensing_range_m": 500.0,
        "fire_control_source": "DIRECT_VISUAL",
        "fire_control_sensor_source_equipment_index": None,
        "fire_control_sensor_id": None,
        "fire_control_sensor_modeled_role": None,
        "fire_control_range_m": 1_000.0,
        "disposition": "VALID_STANDOFF_HOLD",
        "authorized_standoff_m": 500.0,
        "hold_authorized": True,
        "engagement_solution_valid": True,
        "sensing_aware_standoff_enabled": True,
        "fog_of_war_enabled": True,
        "consumable": True,
    }


def _privileged_outcome() -> dict[str, object]:
    return {
        "engine_tick": 7,
        "logical_time_s": 30.0,
        "battle_id": "battle-alpha",
        "shooter_id": "blue-1",
        "target_id": "red-1",
        "weapon_id": "direct-gun",
        "weapon_source_equipment_index": 2,
        "weapon_modeled_role": "ground_direct_fire",
        "ammunition_id": "direct-shell",
        "disposition": "VALID_ENGAGEMENT_SOLUTION",
        "revalidation_passed": True,
        "fog_of_war_enabled": True,
        "consumable": True,
    }


def _side_snapshot() -> dict[str, object]:
    blue = {"id": "blue-1", "side": "blue", "x": 0.0, "y": 1.0, "s": 0}
    red = {"id": "red-1", "side": "red", "x": 500.0, "y": 1.0, "s": 0}
    return {
        "tick": 7,
        "scope": "PRIVILEGED_ENGINE",
        "units": [blue, red],
        "targeting": [_privileged_decision(battle_id="battle-alpha")],
        "targeting_outcomes": [_privileged_outcome()],
        "side_fow_available": True,
        "side_fow_associations": {
            "blue": {"red-1": "fow-track-0042"},
        },
        "side_fow": {
            "blue": {
                "scope": "SIDE_FOW",
                "viewer_side": "blue",
                "units": [blue],
                "tracks": [
                    {
                        "track_id": "fow-track-0042",
                        "reporting_side": "blue",
                        "easting_m": 501.0,
                        "northing_m": 2.0,
                        "velocity_east_mps": -1.0,
                        "velocity_north_mps": 0.5,
                        "position_uncertainty_m": 6.4,
                        "status": "CONFIRMED",
                        "identification_level": "CLASSIFIED",
                        "domain_estimate": "GROUND",
                        "type_estimate": "armor",
                        "specific_estimate": None,
                        "confidence": 0.75,
                        "first_detected_time_s": 20.0,
                        "last_sensor_contact_time_s": 30.0,
                    }
                ],
                "targeting": [
                    {
                        "engine_tick": 7,
                        "logical_time_s": 30.0,
                        "battle_id": "battle-alpha",
                        "ordinal": 0,
                        "shooter_id": "blue-1",
                        "viewer_side": "blue",
                        "target_track_id": "fow-track-0042",
                        "disposition": "VALID_STANDOFF_HOLD",
                        "contact_source": "FOW_OBSERVER_WITNESS",
                        "contact_time_s": 30.0,
                        "authorized_standoff_m": 500.0,
                        "hold_authorized": True,
                        "engagement_solution_valid": True,
                        "sensing_aware_standoff_enabled": True,
                        "fog_of_war_enabled": True,
                        "consumable": True,
                    }
                ],
                "targeting_outcomes": [
                    {
                        "engine_tick": 7,
                        "logical_time_s": 30.0,
                        "battle_id": "battle-alpha",
                        "shooter_id": "blue-1",
                        "viewer_side": "blue",
                        "target_track_id": "fow-track-0042",
                        "disposition": "VALID_ENGAGEMENT_SOLUTION",
                        "revalidation_passed": True,
                        "fog_of_war_enabled": True,
                        "consumable": True,
                    }
                ],
            },
        },
    }


def test_replay_uses_precomputed_side_units_and_opaque_tracks() -> None:
    frame = extract_replay_frames(
        [_side_snapshot()],
        scope=TargetingExposureScope.SIDE_FOW,
        viewer_side="blue",
    )[0]

    assert frame.scope is TargetingExposureScope.SIDE_FOW
    assert frame.viewer_side == "blue"
    assert [unit.unit_id for unit in frame.units] == ["blue-1"]
    assert frame.units[0].x == 0.0
    assert [track.track_id for track in frame.tracks] == ["fow-track-0042"]
    assert frame.tracks[0].easting_m == 501.0
    assert frame.targeting[0].target_track_id == "fow-track-0042"
    assert frame.targeting_outcomes[0].target_track_id == "fow-track-0042"
    assert frame.targeting_outcomes[0].revalidation_passed
    assert frame.engagements == []


def test_side_replay_rejects_payload_viewer_mismatched_to_requested_key() -> None:
    snapshot = _side_snapshot()
    blue_view = snapshot["side_fow"]["blue"]
    blue_view["viewer_side"] = "red"
    blue_view["units"] = []
    blue_view["tracks"][0]["reporting_side"] = "red"
    blue_view["targeting"] = []
    blue_view["targeting_outcomes"] = []
    snapshot["units"] = [snapshot["units"][0]]

    with pytest.raises(ValueError, match="viewer side disagrees with requested side"):
        extract_replay_frames(
            [snapshot],
            scope=TargetingExposureScope.SIDE_FOW,
            viewer_side="blue",
        )


def test_side_replay_rejects_same_side_track_rebinding() -> None:
    snapshot = _side_snapshot()
    red_two = dict(snapshot["units"][1])
    red_two["id"] = "red-2"
    snapshot["units"].append(red_two)
    public = snapshot["side_fow"]["blue"]
    second_track = deepcopy(public["tracks"][0])
    second_track["track_id"] = "fow-track-0043"
    public["tracks"].append(second_track)
    snapshot["side_fow_associations"]["blue"]["red-2"] = "fow-track-0043"
    public["targeting"][0]["target_track_id"] = "fow-track-0043"
    public["targeting_outcomes"][0]["target_track_id"] = "fow-track-0043"

    with pytest.raises(ValueError, match="decision track association disagrees"):
        extract_replay_frames(
            [snapshot],
            scope=TargetingExposureScope.SIDE_FOW,
            viewer_side="blue",
        )


def test_replay_marks_legacy_frames_privileged_and_refuses_side_derivation() -> None:
    legacy = {
        "tick": 1,
        "units": [
            {
                "unit_id": "blue-1",
                "side": "blue",
                "position": {"easting": 0.0, "northing": 0.0},
                "active": True,
            },
            {
                "unit_id": "red-1",
                "side": "red",
                "position": {"easting": 1.0, "northing": 0.0},
                "active": True,
            },
        ],
    }

    privileged = extract_replay_frames([legacy])
    assert privileged[0].scope is TargetingExposureScope.PRIVILEGED_ENGINE
    assert {unit.unit_id for unit in privileged[0].units} == {
        "blue-1",
        "red-1",
    }

    with pytest.raises(ValueError, match="explicitly privileged-only"):
        extract_replay_frames(
            [legacy],
            scope=TargetingExposureScope.SIDE_FOW,
            viewer_side="blue",
        )


def test_side_replay_rejects_privileged_engagement_events() -> None:
    with pytest.raises(ValueError, match="privileged engagement events"):
        extract_replay_frames(
            [_side_snapshot()],
            [{"tick": 7, "attacker_x": 0.0, "target_x": 500.0}],
            scope=TargetingExposureScope.SIDE_FOW,
            viewer_side="blue",
        )


def test_privileged_replay_rejects_reversed_stored_decision_order() -> None:
    snapshot = _side_snapshot()
    snapshot["targeting"] = [
        _privileged_decision(battle_id="battle-zulu"),
        _privileged_decision(battle_id="battle-alpha"),
    ]

    with pytest.raises(ValueError, match="canonical key order"):
        extract_replay_frames([snapshot])


def test_privileged_replay_rejects_target_absent_from_root_roster() -> None:
    snapshot = _side_snapshot()
    decision = deepcopy(_privileged_decision(battle_id="battle-alpha"))
    decision["target_id"] = "invented-red"
    snapshot["targeting"] = [decision]
    snapshot["targeting_outcomes"][0]["target_id"] = "invented-red"

    with pytest.raises(ValueError, match="target is absent from the ROOT roster"):
        extract_replay_frames([snapshot])
