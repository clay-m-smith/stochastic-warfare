"""Phase 115 API privilege-scoped targeting/replay exposure tests."""

from __future__ import annotations

from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from api.routers.runs import _frame_from_storage, get_run_frames
from api.run_manager import RunManager
from api.schemas import SideFowPublicTrack
from stochastic_warfare.detection.fog_of_war import SideWorldView
from stochastic_warfare.simulation.targeting_exposure import (
    TargetingExposureScope,
)
from stochastic_warfare.simulation.tactical_targeting import (
    TacticalTargetingRuntime,
)
from stochastic_warfare.tools.replay import extract_replay_frames


pytestmark = pytest.mark.api


def _privileged_decision() -> dict[str, object]:
    return {
        "engine_tick": 7,
        "logical_time_s": 30.0,
        "battle_id": "battle-alpha",
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
        "observer_track_support": None,
    }


def _supported_privileged_decision() -> dict[str, object]:
    decision = deepcopy(_privileged_decision())
    decision.update(
        {
            "contact_source": "FOW_OBSERVER_TRACK_SUPPORT",
            "contact_sensor_id": "hidden-fire-control-radar",
            "contact_sensor_modeled_role": "fire_control_radar",
            "sensing_sensor_id": "hidden-fire-control-radar",
            "sensing_sensor_modeled_role": "fire_control_radar",
            "fire_control_source": "SENSOR_ATTACHMENT",
            "fire_control_sensor_source_equipment_index": 3,
            "fire_control_sensor_id": "hidden-fire-control-radar",
            "fire_control_sensor_modeled_role": "fire_control_radar",
            "observer_track_support": {
                "identity": {
                    "reporting_side": "blue",
                    "observer_unit_id": "blue-1",
                    "source_equipment_index": 3,
                    "sensor_id": "hidden-fire-control-radar",
                    "modeled_role": "fire_control_radar",
                    "target_id": "red-1",
                },
                "fusion_track_id": "fow-track-0042",
                "sensor_type": "RADAR",
                "observation_ordinal": 1,
                "observation_time_s": 25.0,
                "native_period": 2,
                "native_phase_residue": 1,
                "native_due_ordinal": 3,
                "position_m": [0.0, 500.0],
                "velocity_mps": [0.0, 0.0],
                "covariance": [
                    [100.0, 0.0, 0.0, 0.0],
                    [0.0, 100.0, 0.0, 0.0],
                    [0.0, 0.0, 100.0, 0.0],
                    [0.0, 0.0, 0.0, 100.0],
                ],
                "projection_ordinal": 2,
                "projection_time_s": 30.0,
            },
        },
    )
    return decision


def _blue_public_track() -> dict[str, object]:
    return {
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


def _blue_public_decision() -> dict[str, object]:
    return {
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


def _supported_blue_public_decision() -> dict[str, object]:
    decision = deepcopy(_blue_public_decision())
    decision["contact_source"] = "FOW_OBSERVER_TRACK_SUPPORT"
    return decision


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


def _later_privileged_decision() -> dict[str, object]:
    decision = deepcopy(_privileged_decision())
    decision["battle_id"] = "battle-zulu"
    return decision


def _blue_public_outcome() -> dict[str, object]:
    return {
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


def _scoped_frame() -> dict[str, object]:
    blue_unit = {
        "id": "blue-1",
        "side": "blue",
        "x": 0.0,
        "y": 0.0,
        "d": 0,
        "s": 0,
        "h": 0.0,
        "t": "blue-tank",
    }
    red_unit = {
        "id": "red-1",
        "side": "red",
        "x": 500.0,
        "y": 0.0,
        "d": 0,
        "s": 0,
        "h": 180.0,
        "t": "red-tank",
    }
    return {
        "tick": 7,
        "targeting_exposure_schema_version": 118,
        "fog_of_war_enabled": True,
        "scope": "PRIVILEGED_ENGINE",
        "units": [blue_unit, red_unit],
        "det": {"blue": ["red-1"], "red": []},
        "targeting": [_privileged_decision()],
        "targeting_outcomes": [_privileged_outcome()],
        "side_fow_available": True,
        "side_fow_associations": {
            "blue": {"red-1": "fow-track-0042"},
            "red": {},
        },
        "side_fow": {
            "blue": {
                "scope": "SIDE_FOW",
                "viewer_side": "blue",
                "units": [dict(blue_unit)],
                "tracks": [_blue_public_track()],
                "targeting": [_blue_public_decision()],
                "targeting_outcomes": [_blue_public_outcome()],
            },
            "red": {
                "scope": "SIDE_FOW",
                "viewer_side": "red",
                "units": [dict(red_unit)],
                "tracks": [],
                "targeting": [],
                "targeting_outcomes": [],
            },
        },
    }


async def _store_frames(
    client: AsyncClient,
    run_id: str,
    frames: list[dict[str, object]],
) -> None:
    db = client._transport.app.state.db  # type: ignore[attr-defined]
    await db.create_run(run_id, "test", "path", 42, 100)
    await db.update_run_status(
        run_id,
        "completed",
        frames_json=json.dumps(frames),
        events_json="[]",
    )


def _capture_empty_production_frame(
    *,
    fog_of_war_enabled: bool,
) -> dict[str, object]:
    blue = SimpleNamespace(
        entity_id="blue-1",
        position=SimpleNamespace(easting=0.0, northing=0.0),
        domain=SimpleNamespace(value=0),
        status=SimpleNamespace(value=0),
        heading=0.0,
        unit_type="blue-unit",
    )
    red = SimpleNamespace(
        entity_id="red-1",
        position=SimpleNamespace(easting=500.0, northing=0.0),
        domain=SimpleNamespace(value=0),
        status=SimpleNamespace(value=0),
        heading=180.0,
        unit_type="red-unit",
    )
    views = {
        "blue": SideWorldView(side="blue"),
        "red": SideWorldView(side="red"),
    }
    fog = (
        SimpleNamespace(peek_world_view=lambda side: views[side])
        if fog_of_war_enabled
        else None
    )
    ctx = SimpleNamespace(
        units_by_side={"blue": [blue], "red": [red]},
        unit_sensors={},
        fog_of_war=fog,
        cal_flat={"enable_fog_of_war": fog_of_war_enabled},
        tactical_targeting=TacticalTargetingRuntime(
            sensing_aware_standoff_enabled=True,
            unit_sides={"blue-1": "blue", "red-1": "red"},
        ),
    )
    return RunManager._capture_frame(0, ctx)


@pytest.mark.asyncio
@pytest.mark.parametrize("fog_of_war_enabled", (False, True))
async def test_empty_production_capture_persists_through_api_and_replay(
    client: AsyncClient,
    fog_of_war_enabled: bool,
) -> None:
    frame = _capture_empty_production_frame(
        fog_of_war_enabled=fog_of_war_enabled,
    )
    run_id = f"empty_production_{fog_of_war_enabled}"
    await _store_frames(client, run_id, [frame])

    assert frame["targeting_exposure_schema_version"] == 118
    assert frame["fog_of_war_enabled"] is fog_of_war_enabled
    assert frame["side_fow_available"] is fog_of_war_enabled
    assert frame["targeting"] == []
    assert frame["targeting_outcomes"] == []
    expected_sides = {"blue", "red"} if fog_of_war_enabled else set()
    assert set(frame["side_fow"]) == expected_sides
    assert set(frame["side_fow_associations"]) == expected_sides

    privileged = await client.get(f"/api/runs/{run_id}/frames")
    assert privileged.status_code == 200, privileged.text
    assert privileged.json()["frames"][0]["targeting"] == []
    replay = extract_replay_frames(
        [frame],
        scope=TargetingExposureScope.PRIVILEGED_ENGINE,
    )
    assert replay[0].targeting == ()

    side = await client.get(
        f"/api/runs/{run_id}/frames?scope=SIDE_FOW&side=blue",
    )
    if fog_of_war_enabled:
        assert side.status_code == 200, side.text
        assert side.json()["frames"][0]["side_targeting"] == []
        side_replay = extract_replay_frames(
            [frame],
            scope=TargetingExposureScope.SIDE_FOW,
            viewer_side="blue",
        )
        assert side_replay[0].targeting == ()
    else:
        assert side.status_code == 409
        assert "explicitly privileged-only" in side.json()["detail"]
        with pytest.raises(ValueError, match="explicitly privileged-only"):
            extract_replay_frames(
                [frame],
                scope=TargetingExposureScope.SIDE_FOW,
                viewer_side="blue",
            )


def test_stored_projection_is_typed_and_scope_isolated() -> None:
    stored = _scoped_frame()

    privileged = _frame_from_storage(
        stored,
        scope=TargetingExposureScope.PRIVILEGED_ENGINE,
        side=None,
    )
    assert privileged.targeting[0].target_id == "red-1"
    assert privileged.targeting_outcomes[0].target_id == "red-1"
    assert privileged.targeting_outcomes[0].weapon_id == "direct-gun"
    assert privileged.targeting_outcomes[0].revalidation_passed
    assert {unit.id for unit in privileged.units} == {"blue-1", "red-1"}

    public = _frame_from_storage(
        stored,
        scope=TargetingExposureScope.SIDE_FOW,
        side="blue",
    )
    assert [unit.id for unit in public.units] == ["blue-1"]
    assert public.targeting == []
    assert public.side_targeting[0].target_track_id == "fow-track-0042"
    assert public.side_targeting_outcomes[0].target_track_id == "fow-track-0042"
    assert public.side_targeting_outcomes[0].revalidation_passed
    serialized = public.model_dump_json()
    assert "red-1" not in serialized
    assert "direct-gun" not in serialized
    assert "hidden-binocular-attachment" not in serialized


def test_stored_observer_support_is_lossless_only_in_privileged_scope() -> None:
    stored = _scoped_frame()
    exact = _supported_privileged_decision()
    stored["targeting"] = [exact]
    stored["side_fow"]["blue"]["targeting"] = [
        _supported_blue_public_decision(),
    ]

    privileged = _frame_from_storage(
        stored,
        scope=TargetingExposureScope.PRIVILEGED_ENGINE,
        side=None,
    )
    support = privileged.targeting[0].observer_track_support
    assert support is not None
    assert support.model_dump(mode="json") == exact["observer_track_support"]
    assert support.identity.observer_unit_id == "blue-1"
    assert support.identity.sensor_id == "hidden-fire-control-radar"
    assert support.identity.target_id == "red-1"
    assert support.fusion_track_id == "fow-track-0042"
    assert support.sensor_type == "RADAR"

    public = _frame_from_storage(
        stored,
        scope=TargetingExposureScope.SIDE_FOW,
        side="blue",
    )
    assert public.side_targeting[0].contact_source.value == (
        "FOW_OBSERVER_TRACK_SUPPORT"
    )
    serialized = public.model_dump_json()
    assert "observer_track_support" not in serialized
    assert "hidden-fire-control-radar" not in serialized
    assert '"covariance"' not in serialized
    assert "red-1" not in serialized


def test_pre118_witness_frame_migrates_only_at_stored_exposure_boundary() -> None:
    stored = _scoped_frame()
    legacy_decision = stored["targeting"][0]
    assert legacy_decision.pop("observer_track_support") is None
    del stored["targeting_exposure_schema_version"]
    del stored["fog_of_war_enabled"]

    privileged = _frame_from_storage(
        stored,
        scope=TargetingExposureScope.PRIVILEGED_ENGINE,
        side=None,
    )
    assert privileged.targeting[0].observer_track_support is None
    assert (
        privileged.model_dump(mode="json")["targeting"][0][
            "observer_track_support"
        ]
        is None
    )

    public = _frame_from_storage(
        stored,
        scope=TargetingExposureScope.SIDE_FOW,
        side="blue",
    )
    assert public.side_targeting[0].contact_source.value == (
        "FOW_OBSERVER_WITNESS"
    )


def test_versioned_frame_rejects_pre118_decision_topology() -> None:
    stored = _scoped_frame()
    assert stored["targeting"][0].pop("observer_track_support") is None

    with pytest.raises(
        ValueError,
        match="versioned targeting exposure requires current decision topology",
    ):
        _frame_from_storage(
            stored,
            scope=TargetingExposureScope.PRIVILEGED_ENGINE,
            side=None,
        )


def test_pre118_shape_cannot_claim_phase118_observer_support() -> None:
    stored = _scoped_frame()
    decision = stored["targeting"][0]
    assert decision.pop("observer_track_support") is None
    decision["contact_source"] = "FOW_OBSERVER_TRACK_SUPPORT"

    with pytest.raises(ValueError, match="requires typed support evidence"):
        _frame_from_storage(
            stored,
            scope=TargetingExposureScope.PRIVILEGED_ENGINE,
            side=None,
        )


def test_stored_exposure_rejects_mixed_pre118_and_current_decisions() -> None:
    stored = _scoped_frame()
    legacy_decision = _later_privileged_decision()
    assert legacy_decision.pop("observer_track_support") is None
    stored["targeting"] = [stored["targeting"][0], legacy_decision]

    with pytest.raises(
        ValueError,
        match="mixes pre-118 and current decision topology",
    ):
        _frame_from_storage(
            stored,
            scope=TargetingExposureScope.PRIVILEGED_ENGINE,
            side=None,
        )


def test_pre118_stored_exposure_rejects_any_second_missing_key() -> None:
    stored = _scoped_frame()
    legacy_decision = stored["targeting"][0]
    assert legacy_decision.pop("observer_track_support") is None
    legacy_decision.pop("weapon_id")

    with pytest.raises(ValueError, match="invalid key topology"):
        _frame_from_storage(
            stored,
            scope=TargetingExposureScope.PRIVILEGED_ENGINE,
            side=None,
        )


def test_stored_support_track_tamper_rejects_both_api_scopes_and_replay() -> None:
    stored = _scoped_frame()
    exact = _supported_privileged_decision()
    exact["observer_track_support"]["fusion_track_id"] = "fow-track-0043"
    stored["targeting"] = [exact]
    stored["side_fow"]["blue"]["targeting"] = [
        _supported_blue_public_decision(),
    ]

    for scope, side in (
        (TargetingExposureScope.PRIVILEGED_ENGINE, None),
        (TargetingExposureScope.SIDE_FOW, "blue"),
    ):
        with pytest.raises(
            ValueError,
            match="support disagrees with the public target track",
        ):
            _frame_from_storage(stored, scope=scope, side=side)

    with pytest.raises(
        ValueError,
        match="support disagrees with the public target track",
    ):
        extract_replay_frames(
            [stored],
            scope=TargetingExposureScope.PRIVILEGED_ENGINE,
        )


@pytest.mark.parametrize(
    ("scope", "side"),
    (
        (TargetingExposureScope.PRIVILEGED_ENGINE, None),
        (TargetingExposureScope.SIDE_FOW, "blue"),
    ),
)
def test_stored_privileged_only_frame_rejects_retained_side_envelopes(
    scope: TargetingExposureScope,
    side: str | None,
) -> None:
    stored = _scoped_frame()
    stored["targeting"] = []
    stored["targeting_outcomes"] = []
    stored["fog_of_war_enabled"] = False
    stored["side_fow_available"] = False
    stored["side_fow"]["blue"]["targeting"][0]["target_id"] = "red-1"

    with pytest.raises(ValueError, match="must contain empty SIDE_FOW envelopes"):
        _frame_from_storage(stored, scope=scope, side=side)


def test_stored_current_fow_frame_cannot_downgrade_availability() -> None:
    stored = _scoped_frame()
    stored["side_fow_available"] = False
    stored["side_fow"] = {}
    stored["side_fow_associations"] = {}

    with pytest.raises(
        ValueError,
        match="FOW mode disagrees with SIDE_FOW availability",
    ):
        _frame_from_storage(
            stored,
            scope=TargetingExposureScope.PRIVILEGED_ENGINE,
            side=None,
        )


def test_empty_current_frame_cannot_masquerade_as_legacy_privileged() -> None:
    stored = _scoped_frame()
    stored["targeting"] = []
    stored["targeting_outcomes"] = []
    for side_view in stored["side_fow"].values():
        side_view["targeting"] = []
        side_view["targeting_outcomes"] = []
    for key in (
        "targeting_exposure_schema_version",
        "fog_of_war_enabled",
        "scope",
        "side_fow_available",
        "side_fow",
        "side_fow_associations",
    ):
        del stored[key]

    with pytest.raises(
        ValueError,
        match="unversioned empty targeting exposure is unsupported",
    ):
        _frame_from_storage(
            stored,
            scope=TargetingExposureScope.PRIVILEGED_ENGINE,
            side=None,
        )
    with pytest.raises(
        ValueError,
        match="unversioned empty targeting exposure is unsupported",
    ):
        extract_replay_frames(
            [stored],
            scope=TargetingExposureScope.PRIVILEGED_ENGINE,
        )


def test_versioned_empty_current_frame_requires_complete_side_envelope() -> None:
    stored = _scoped_frame()
    stored["targeting"] = []
    stored["targeting_outcomes"] = []
    for key in (
        "side_fow_available",
        "side_fow",
        "side_fow_associations",
    ):
        del stored[key]

    with pytest.raises(
        ValueError,
        match="versioned targeting exposure requires the complete root envelope",
    ):
        _frame_from_storage(
            stored,
            scope=TargetingExposureScope.PRIVILEGED_ENGINE,
            side=None,
        )


def test_empty_current_fow_frame_cannot_downgrade_availability() -> None:
    stored = _scoped_frame()
    stored["targeting"] = []
    stored["targeting_outcomes"] = []
    stored["side_fow_available"] = False
    stored["side_fow"] = {}
    stored["side_fow_associations"] = {}

    for consumer in (
        lambda: _frame_from_storage(
            stored,
            scope=TargetingExposureScope.PRIVILEGED_ENGINE,
            side=None,
        ),
        lambda: extract_replay_frames(
            [stored],
            scope=TargetingExposureScope.PRIVILEGED_ENGINE,
        ),
        lambda: _frame_from_storage(
            stored,
            scope=TargetingExposureScope.SIDE_FOW,
            side="blue",
        ),
        lambda: extract_replay_frames(
            [stored],
            scope=TargetingExposureScope.SIDE_FOW,
            viewer_side="blue",
        ),
    ):
        with pytest.raises(
            ValueError,
            match="FOW mode disagrees with SIDE_FOW availability",
        ):
            consumer()


@pytest.mark.asyncio
async def test_api_rejects_empty_current_fow_availability_downgrade(
    client: AsyncClient,
) -> None:
    stored = _scoped_frame()
    stored["targeting"] = []
    stored["targeting_outcomes"] = []
    stored["side_fow_available"] = False
    stored["side_fow"] = {}
    stored["side_fow_associations"] = {}
    await _store_frames(client, "empty_fow_downgrade", [stored])

    for path in (
        "/api/runs/empty_fow_downgrade/frames",
        (
            "/api/runs/empty_fow_downgrade/frames"
            "?scope=SIDE_FOW&side=blue"
        ),
    ):
        response = await client.get(path)
        assert response.status_code == 409
        assert "FOW mode disagrees with SIDE_FOW availability" in (
            response.json()["detail"]
        )


@pytest.mark.asyncio
async def test_api_tick_range_rejects_malformed_stored_tick(
    client: AsyncClient,
) -> None:
    stored = _scoped_frame()
    stored["tick"] = "7"
    await _store_frames(client, "malformed_tick", [stored])

    response = await client.get(
        "/api/runs/malformed_tick/frames?start_tick=0&end_tick=10",
    )

    assert response.status_code == 409
    assert "engine_tick must be a non-negative integer" in (
        response.json()["detail"]
    )


def test_replay_rejects_malformed_tick_before_sorting() -> None:
    first = _scoped_frame()
    first["tick"] = "7"
    second = _scoped_frame()
    second["tick"] = 8

    with pytest.raises(
        ValueError,
        match="engine_tick must be a non-negative integer",
    ):
        extract_replay_frames([first, second])


def test_versioned_empty_privileged_only_frame_retains_explicit_mode() -> None:
    stored = _scoped_frame()
    stored["targeting"] = []
    stored["targeting_outcomes"] = []
    stored["fog_of_war_enabled"] = False
    stored["side_fow_available"] = False
    stored["side_fow"] = {}
    stored["side_fow_associations"] = {}

    frame = _frame_from_storage(
        stored,
        scope=TargetingExposureScope.PRIVILEGED_ENGINE,
        side=None,
    )

    assert frame.targeting == []
    assert frame.targeting_outcomes == []
    assert {unit.id for unit in frame.units} == {"blue-1", "red-1"}


@pytest.mark.parametrize("empty_interval", (False, True))
def test_current_frame_cannot_delete_its_format_marker(
    empty_interval: bool,
) -> None:
    stored = _scoped_frame()
    if empty_interval:
        stored["targeting"] = []
        stored["targeting_outcomes"] = []
        for side_view in stored["side_fow"].values():
            side_view["targeting"] = []
            side_view["targeting_outcomes"] = []
    del stored["targeting_exposure_schema_version"]

    with pytest.raises(
        ValueError,
        match="unversioned targeting exposure contains a current-only FOW mode",
    ):
        _frame_from_storage(
            stored,
            scope=TargetingExposureScope.PRIVILEGED_ENGINE,
            side=None,
        )


@pytest.mark.parametrize("invalid_mode", (0, 1, "true", None))
def test_current_stored_exposure_rejects_invalid_fow_mode(
    invalid_mode: object,
) -> None:
    stored = _scoped_frame()
    stored["fog_of_war_enabled"] = invalid_mode

    with pytest.raises(
        ValueError,
        match="stored targeting FOW mode must be a boolean",
    ):
        _frame_from_storage(
            stored,
            scope=TargetingExposureScope.PRIVILEGED_ENGINE,
            side=None,
        )


def test_current_stored_exposure_requires_explicit_fow_mode() -> None:
    stored = _scoped_frame()
    del stored["fog_of_war_enabled"]

    with pytest.raises(
        ValueError,
        match="versioned targeting exposure requires the complete root envelope",
    ):
        _frame_from_storage(
            stored,
            scope=TargetingExposureScope.PRIVILEGED_ENGINE,
            side=None,
        )


def test_current_privileged_only_mode_cannot_claim_side_availability() -> None:
    stored = _scoped_frame()
    stored["targeting"] = []
    stored["targeting_outcomes"] = []
    for side_view in stored["side_fow"].values():
        side_view["targeting"] = []
        side_view["targeting_outcomes"] = []
    stored["fog_of_war_enabled"] = False

    with pytest.raises(
        ValueError,
        match="FOW mode disagrees with SIDE_FOW availability",
    ):
        _frame_from_storage(
            stored,
            scope=TargetingExposureScope.PRIVILEGED_ENGINE,
            side=None,
        )


def test_unversioned_paired_empty_frame_preserves_exact_side_envelope() -> None:
    stored = _scoped_frame()
    stored["targeting"] = []
    stored["targeting_outcomes"] = []
    for side_view in stored["side_fow"].values():
        side_view["targeting"] = []
        side_view["targeting_outcomes"] = []
    del stored["targeting_exposure_schema_version"]
    del stored["fog_of_war_enabled"]

    privileged = _frame_from_storage(
        stored,
        scope=TargetingExposureScope.PRIVILEGED_ENGINE,
        side=None,
    )
    side = _frame_from_storage(
        stored,
        scope=TargetingExposureScope.SIDE_FOW,
        side="blue",
    )
    replay = extract_replay_frames(
        [stored],
        scope=TargetingExposureScope.SIDE_FOW,
        viewer_side="blue",
    )

    assert privileged.targeting == []
    assert side.side_targeting == []
    assert replay[0].targeting == ()


@pytest.mark.parametrize("invalid_version", (True, 117, 119, "118"))
def test_current_stored_exposure_rejects_invalid_schema_version(
    invalid_version: object,
) -> None:
    stored = _scoped_frame()
    stored["targeting_exposure_schema_version"] = invalid_version

    with pytest.raises(
        ValueError,
        match="targeting exposure schema version must be the strict integer 118",
    ):
        _frame_from_storage(
            stored,
            scope=TargetingExposureScope.PRIVILEGED_ENGINE,
            side=None,
        )


def test_legacy_privileged_frame_without_availability_retains_fow_evidence() -> None:
    stored = _scoped_frame()
    assert stored["targeting"][0].pop("observer_track_support") is None
    for key in (
        "targeting_exposure_schema_version",
        "fog_of_war_enabled",
        "scope",
        "side_fow_available",
        "side_fow",
        "side_fow_associations",
    ):
        del stored[key]

    privileged = _frame_from_storage(
        stored,
        scope=TargetingExposureScope.PRIVILEGED_ENGINE,
        side=None,
    )

    assert privileged.targeting[0].fog_of_war_enabled
    assert privileged.targeting[0].contact_source.value == "FOW_OBSERVER_WITNESS"


def test_current_decision_topology_cannot_omit_availability_envelope() -> None:
    stored = _scoped_frame()
    del stored["side_fow_available"]
    del stored["side_fow"]
    del stored["side_fow_associations"]

    with pytest.raises(
        ValueError,
        match="versioned targeting exposure requires the complete root envelope",
    ):
        _frame_from_storage(
            stored,
            scope=TargetingExposureScope.PRIVILEGED_ENGINE,
            side=None,
        )


@pytest.mark.parametrize(
    ("scope", "side"),
    (
        (TargetingExposureScope.PRIVILEGED_ENGINE, None),
        (TargetingExposureScope.SIDE_FOW, "blue"),
    ),
)
def test_stored_current_fow_frame_requires_every_root_roster_side(
    scope: TargetingExposureScope,
    side: str | None,
) -> None:
    stored = _scoped_frame()
    del stored["side_fow"]["red"]
    del stored["side_fow_associations"]["red"]

    with pytest.raises(ValueError, match="must exactly match the ROOT roster sides"):
        _frame_from_storage(stored, scope=scope, side=side)


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("missing_key", "invalid key topology"),
        ("extra_key", "invalid key topology"),
        ("unsupported_type", "seven supported radar roles"),
        ("unsupported_role", "seven supported radar roles"),
        ("invalid_ordinal", "exact next native deadline"),
        ("invalid_covariance", "negative diagonal"),
        ("identity_mismatch", "identity must match the decision exactly"),
    ],
)
def test_stored_support_semantic_tamper_fails_closed(
    case: str,
    expected: str,
) -> None:
    stored = _scoped_frame()
    exact = _supported_privileged_decision()
    support = exact["observer_track_support"]
    if case == "missing_key":
        support.pop("projection_time_s")
    elif case == "extra_key":
        support["unexpected"] = True
    elif case == "unsupported_type":
        support["sensor_type"] = "VISUAL"
    elif case == "unsupported_role":
        support["identity"]["modeled_role"] = "air_search_radar"
    elif case == "invalid_ordinal":
        support["native_due_ordinal"] = 4
    elif case == "invalid_covariance":
        support["covariance"][0][0] = -1.0
    else:
        support["identity"]["observer_unit_id"] = "blue-2"
    stored["targeting"] = [exact]
    stored["side_fow"]["blue"]["targeting"] = [
        _supported_blue_public_decision(),
    ]

    with pytest.raises(ValueError, match=expected):
        _frame_from_storage(
            stored,
            scope=TargetingExposureScope.PRIVILEGED_ENGINE,
            side=None,
        )


def test_stored_side_projection_rejects_payload_viewer_key_mismatch() -> None:
    stored = _scoped_frame()
    blue_view = stored["side_fow"]["blue"]
    blue_view["viewer_side"] = "red"
    blue_view["units"] = []
    blue_view["tracks"][0]["reporting_side"] = "red"
    blue_view["targeting"] = []
    blue_view["targeting_outcomes"] = []

    with pytest.raises(ValueError, match="viewer side disagrees with requested side"):
        _frame_from_storage(
            stored,
            scope=TargetingExposureScope.SIDE_FOW,
            side="blue",
        )


def test_stored_side_projection_rejects_same_side_track_rebinding() -> None:
    """An existing opaque track cannot be substituted for the exact target."""
    stored = _scoped_frame()
    red_two = dict(stored["units"][1])
    red_two["id"] = "red-2"
    stored["units"].append(red_two)
    public = stored["side_fow"]["blue"]
    second_track = deepcopy(public["tracks"][0])
    second_track["track_id"] = "fow-track-0043"
    public["tracks"].append(second_track)
    stored["side_fow_associations"]["blue"]["red-2"] = "fow-track-0043"
    public["targeting"][0]["target_track_id"] = "fow-track-0043"
    public["targeting_outcomes"][0]["target_track_id"] = "fow-track-0043"

    with pytest.raises(ValueError, match="decision track association disagrees"):
        _frame_from_storage(
            stored,
            scope=TargetingExposureScope.SIDE_FOW,
            side="blue",
        )


@pytest.mark.parametrize("corruption", ("standoff", "logical_time"))
def test_stored_side_projection_rejects_semantic_drift_from_privileged_evidence(
    corruption: str,
) -> None:
    """Internally coherent public fields remain a derived, exact projection."""
    stored = _scoped_frame()
    public = stored["side_fow"]["blue"]
    if corruption == "standoff":
        public["targeting"][0]["authorized_standoff_m"] = 400.0
    else:
        public["targeting"][0]["logical_time_s"] = 31.0
        public["targeting"][0]["contact_time_s"] = 31.0
        public["targeting_outcomes"][0]["logical_time_s"] = 31.0

    with pytest.raises(ValueError, match="semantic projection disagrees"):
        _frame_from_storage(
            stored,
            scope=TargetingExposureScope.SIDE_FOW,
            side="blue",
        )


def test_stored_side_projection_requires_privileged_associations() -> None:
    stored = _scoped_frame()
    del stored["side_fow_associations"]

    with pytest.raises(
        ValueError,
        match="versioned targeting exposure requires the complete root envelope",
    ):
        _frame_from_storage(
            stored,
            scope=TargetingExposureScope.SIDE_FOW,
            side="blue",
        )


def test_stored_privileged_outcome_must_match_exact_decision_identity() -> None:
    stored = _scoped_frame()
    stored["targeting_outcomes"][0]["weapon_id"] = "different-gun"

    with pytest.raises(ValueError, match="identity disagrees"):
        _frame_from_storage(
            stored,
            scope=TargetingExposureScope.PRIVILEGED_ENGINE,
            side=None,
        )


def test_stored_privileged_decisions_preserve_and_validate_canonical_order() -> None:
    stored = _scoped_frame()
    stored["targeting"] = [
        _later_privileged_decision(),
        _privileged_decision(),
    ]

    with pytest.raises(ValueError, match="canonical key order"):
        _frame_from_storage(
            stored,
            scope=TargetingExposureScope.PRIVILEGED_ENGINE,
            side=None,
        )


@pytest.mark.parametrize("identity", ("shooter", "target"))
def test_stored_privileged_identities_must_exist_in_root_roster(
    identity: str,
) -> None:
    stored = _scoped_frame()
    if identity == "shooter":
        stored["targeting"][0]["shooter_id"] = "invented-blue"
        stored["targeting"][0]["observing_unit_id"] = "invented-blue"
        stored["targeting_outcomes"][0]["shooter_id"] = "invented-blue"
    else:
        stored["targeting"][0]["target_id"] = "invented-red"
        stored["targeting_outcomes"][0]["target_id"] = "invented-red"

    with pytest.raises(ValueError, match=f"{identity} is absent from the ROOT roster"):
        _frame_from_storage(
            stored,
            scope=TargetingExposureScope.PRIVILEGED_ENGINE,
            side=None,
        )


def test_stored_privileged_side_must_match_root_roster() -> None:
    stored = _scoped_frame()
    stored["units"][0]["side"] = "red"

    with pytest.raises(ValueError, match="shooter side disagrees"):
        _frame_from_storage(
            stored,
            scope=TargetingExposureScope.PRIVILEGED_ENGINE,
            side=None,
        )


@pytest.mark.parametrize(
    ("corruption", "message"),
    (
        ("track_root_collision", "canonical opaque FOW ordinal track ID"),
        ("shooter_rebinding", "do not exactly match privileged decisions"),
        ("unit_rebinding", "does not match the viewer's ROOT roster"),
    ),
)
def test_stored_side_projection_binds_to_authoritative_root_roster(
    corruption: str,
    message: str,
) -> None:
    stored = _scoped_frame()
    public = stored["side_fow"]["blue"]
    if corruption == "track_root_collision":
        public["tracks"][0]["track_id"] = "red-1"
        public["targeting"][0]["target_track_id"] = "red-1"
        public["targeting_outcomes"][0]["target_track_id"] = "red-1"
    elif corruption == "shooter_rebinding":
        public["targeting"][0]["shooter_id"] = "red-1"
        public["targeting_outcomes"][0]["shooter_id"] = "red-1"
    else:
        public["units"][0]["id"] = "red-1"

    with pytest.raises(ValueError, match=message):
        _frame_from_storage(
            stored,
            scope=TargetingExposureScope.SIDE_FOW,
            side="blue",
        )


def test_frame_capture_requires_typed_targeting_runtime_owner() -> None:
    ctx = SimpleNamespace(units_by_side={}, cal_flat={}, fog_of_war=None)

    with pytest.raises(ValueError, match="TacticalTargetingRuntime owner"):
        RunManager._capture_frame(0, ctx)


def test_frame_capture_rejects_nonboolean_runtime_fow_mode() -> None:
    ctx = SimpleNamespace(
        units_by_side={},
        cal_flat={"enable_fog_of_war": 1},
        fog_of_war=None,
        tactical_targeting=TacticalTargetingRuntime(
            sensing_aware_standoff_enabled=True,
            unit_sides={},
        ),
    )

    with pytest.raises(
        ValueError,
        match="runtime enable_fog_of_war must be a boolean",
    ):
        RunManager._capture_frame(0, ctx)


def test_public_track_api_schema_exposes_exact_enum_contracts() -> None:
    schema = SideFowPublicTrack.model_json_schema()
    definitions = schema["$defs"]

    assert definitions["PublicTrackStatus"]["enum"] == [
        "TENTATIVE",
        "CONFIRMED",
        "COASTING",
        "STALE",
        "LOST",
    ]
    assert definitions["PublicIdentificationLevel"]["enum"] == [
        "UNKNOWN",
        "DETECTED",
        "CLASSIFIED",
        "IDENTIFIED",
    ]
    invalid = _blue_public_track()
    invalid["status"] = "FRESH"
    with pytest.raises(ValueError):
        SideFowPublicTrack.model_validate(invalid)

    nonopaque = _blue_public_track()
    nonopaque["track_id"] = "red-1"
    with pytest.raises(ValueError, match="canonical opaque FOW ordinal"):
        SideFowPublicTrack.model_validate(nonopaque)


@pytest.mark.asyncio
async def test_router_returns_paired_scopes_without_recomputation() -> None:
    class _Database:
        async def get_run(self, run_id: str) -> dict[str, object]:
            assert run_id == "stored"
            return {"frames_json": json.dumps([_scoped_frame()])}

    db = _Database()
    privileged = await get_run_frames(
        "stored",
        start_tick=None,
        end_tick=None,
        scope=TargetingExposureScope.PRIVILEGED_ENGINE,
        side=None,
        db=db,  # type: ignore[arg-type]
    )
    public = await get_run_frames(
        "stored",
        start_tick=None,
        end_tick=None,
        scope=TargetingExposureScope.SIDE_FOW,
        side="blue",
        db=db,  # type: ignore[arg-type]
    )

    assert privileged.frames[0].targeting[0].target_id == "red-1"
    assert privileged.frames[0].targeting_outcomes[0].weapon_id == "direct-gun"
    assert public.frames[0].targeting == []
    assert public.frames[0].targeting_outcomes == []
    assert [unit.id for unit in public.frames[0].units] == ["blue-1"]
    assert public.frames[0].tracks[0].track_id == "fow-track-0042"
    assert public.frames[0].side_targeting_outcomes[0].target_track_id == ("fow-track-0042")


@pytest.mark.asyncio
async def test_api_pairs_exact_privileged_and_bounded_side_views(
    client: AsyncClient,
) -> None:
    await _store_frames(client, "scoped_run", [_scoped_frame()])

    privileged_response = await client.get("/api/runs/scoped_run/frames")
    assert privileged_response.status_code == 200, privileged_response.text
    privileged = privileged_response.json()
    assert privileged["scope"] == "PRIVILEGED_ENGINE"
    assert privileged["viewer_side"] is None
    assert {unit["id"] for unit in privileged["frames"][0]["units"]} == {
        "blue-1",
        "red-1",
    }
    exact = privileged["frames"][0]["targeting"][0]
    assert exact["target_id"] == "red-1"
    assert exact["weapon_id"] == "direct-gun"
    assert exact["contact_sensor_id"] == "hidden-binocular-attachment"
    exact_outcome = privileged["frames"][0]["targeting_outcomes"][0]
    assert exact_outcome["target_id"] == "red-1"
    assert exact_outcome["weapon_id"] == "direct-gun"
    assert exact_outcome["revalidation_passed"] is True

    side_response = await client.get(
        "/api/runs/scoped_run/frames?scope=SIDE_FOW&side=blue",
    )
    assert side_response.status_code == 200, side_response.text
    side = side_response.json()
    assert side["scope"] == "SIDE_FOW"
    assert side["viewer_side"] == "blue"
    frame = side["frames"][0]
    assert [unit["id"] for unit in frame["units"]] == ["blue-1"]
    assert frame["detected"] == {"blue": ["fow-track-0042"]}
    assert frame["tracks"][0]["track_id"] == "fow-track-0042"
    assert frame["side_targeting"][0]["target_track_id"] == "fow-track-0042"
    assert frame["side_targeting_outcomes"][0]["target_track_id"] == ("fow-track-0042")
    assert frame["side_targeting_outcomes"][0]["revalidation_passed"] is True
    assert frame["targeting"] == []
    assert frame["targeting_outcomes"] == []

    serialized = json.dumps(side, sort_keys=True)
    assert "red-1" not in serialized
    assert "red-tank" not in serialized
    assert "direct-gun" not in serialized
    assert "hidden-binocular-attachment" not in serialized
    assert '"target_id"' not in serialized
    assert '"target_side"' not in serialized
    assert "source_equipment_index" not in serialized


@pytest.mark.asyncio
async def test_api_side_scope_never_derives_from_legacy_privileged_frame(
    client: AsyncClient,
) -> None:
    await _store_frames(
        client,
        "legacy_run",
        [
            {
                "tick": 1,
                "units": [
                    {"id": "blue-1", "side": "blue", "x": 0.0, "y": 0.0},
                    {"id": "red-1", "side": "red", "x": 1.0, "y": 0.0},
                ],
                "det": {"blue": ["red-1"]},
            }
        ],
    )

    privileged = await client.get("/api/runs/legacy_run/frames")
    assert privileged.status_code == 409
    assert "unversioned empty targeting exposure is unsupported" in (
        privileged.json()["detail"]
    )

    side = await client.get(
        "/api/runs/legacy_run/frames?scope=SIDE_FOW&side=blue",
    )
    assert side.status_code == 409
    assert "unversioned empty targeting exposure is unsupported" in (
        side.json()["detail"]
    )


@pytest.mark.asyncio
async def test_api_scope_parameters_fail_closed(client: AsyncClient) -> None:
    await _store_frames(client, "scope_run", [_scoped_frame()])

    missing_side = await client.get(
        "/api/runs/scope_run/frames?scope=SIDE_FOW",
    )
    assert missing_side.status_code == 422
    privileged_side = await client.get(
        "/api/runs/scope_run/frames?scope=PRIVILEGED_ENGINE&side=blue",
    )
    assert privileged_side.status_code == 422
    unknown_scope = await client.get(
        "/api/runs/scope_run/frames?scope=PUBLIC",
    )
    assert unknown_scope.status_code == 422
