"""Phase 115 privilege and fog-of-war targeting exposure tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json

import numpy as np
import pytest

from stochastic_warfare.core.types import Domain
from stochastic_warfare.detection.cadence import TacticalAttachmentIdentity
from stochastic_warfare.detection.estimation import (
    Track,
    TrackState,
    TrackStatus,
)
from stochastic_warfare.detection.observer_support import (
    ObserverTrackSupportEvidence,
    ObserverTrackSupportIdentity,
)
from stochastic_warfare.detection.sensors import SensorType
from stochastic_warfare.detection.fog_of_war import (
    ContactRecord,
    FogOfWarManager,
    SideWorldView,
)
from stochastic_warfare.detection.identification import (
    ContactInfo,
    ContactLevel,
)
from stochastic_warfare.simulation.loadouts import (
    SensorModeledRole,
    WeaponModeledRole,
)
from stochastic_warfare.simulation.tactical_targeting import (
    ContactSource,
    EffectiveRangeBasis,
    FireControlSource,
    TacticalEngagementRevalidationOutcome,
    TacticalTargetingDecision,
    TacticalTargetingPicture,
    TacticalTargetingRuntime,
    TargetingDisposition,
)
from stochastic_warfare.simulation.targeting_exposure import (
    PrivilegedTargetingExposure,
    SideFowEngagementRevalidationExposure,
    SideFowTargetingDecisionExposure,
    SideFowTargetingExposure,
    TargetingExposureScope,
    capture_targeting_exposure,
    decode_stored_targeting_exposure,
    filter_side_unit_frames,
)


class _FogOfWarViewOwner:
    def __init__(self, views: dict[str, SideWorldView]) -> None:
        self._views = views

    def get_world_view(self, side: str) -> SideWorldView:
        return self._views[side]

    def peek_world_view(self, side: str) -> SideWorldView | None:
        return self._views.get(side)


def _targeted_blue_decision() -> TacticalTargetingDecision:
    return TacticalTargetingDecision(
        engine_tick=7,
        logical_time_s=30.0,
        battle_id="battle-alpha",
        ordinal=0,
        shooter_id="blue-1",
        shooter_side="blue",
        shooter_domain=Domain.GROUND,
        target_id="red-1",
        target_side="red",
        target_domain=Domain.GROUND,
        distance_m=500.0,
        weapon_id="direct-gun",
        weapon_source_equipment_index=2,
        weapon_modeled_role=WeaponModeledRole.GROUND_DIRECT_FIRE,
        ammunition_id="direct-shell",
        physical_max_range_m=1_000.0,
        predictive_effective_range_m=800.0,
        effective_range_basis=EffectiveRangeBasis.AUTHORED,
        legacy_derived_reference_range_m=800.0,
        contact_source=ContactSource.FOW_OBSERVER_WITNESS,
        observing_unit_id="blue-1",
        contact_sensor_source_equipment_index=3,
        contact_sensor_id="hidden-binocular-attachment",
        contact_sensor_modeled_role=SensorModeledRole.VISUAL_OBSERVATION,
        contact_time_s=30.0,
        contact_range_m=500.0,
        visibility_bound_m=1_000.0,
        sensing_sensor_source_equipment_index=3,
        sensing_sensor_id="hidden-binocular-attachment",
        sensing_sensor_modeled_role=SensorModeledRole.VISUAL_OBSERVATION,
        sensing_range_m=500.0,
        fire_control_source=FireControlSource.DIRECT_VISUAL,
        fire_control_sensor_source_equipment_index=None,
        fire_control_sensor_id=None,
        fire_control_sensor_modeled_role=None,
        fire_control_range_m=1_000.0,
        disposition=TargetingDisposition.VALID_STANDOFF_HOLD,
        authorized_standoff_m=500.0,
        hold_authorized=True,
        engagement_solution_valid=True,
        sensing_aware_standoff_enabled=True,
        fog_of_war_enabled=True,
        consumable=True,
    )


def _red_no_target_decision() -> TacticalTargetingDecision:
    return TacticalTargetingDecision(
        engine_tick=7,
        logical_time_s=30.0,
        battle_id="battle-alpha",
        ordinal=1,
        shooter_id="red-1",
        shooter_side="red",
        shooter_domain=Domain.GROUND,
        target_id=None,
        target_side=None,
        target_domain=None,
        distance_m=0.0,
        weapon_id=None,
        weapon_source_equipment_index=None,
        weapon_modeled_role=None,
        ammunition_id=None,
        physical_max_range_m=0.0,
        predictive_effective_range_m=0.0,
        effective_range_basis=None,
        legacy_derived_reference_range_m=0.0,
        contact_source=ContactSource.NONE,
        observing_unit_id=None,
        contact_sensor_source_equipment_index=None,
        contact_sensor_id=None,
        contact_sensor_modeled_role=None,
        contact_time_s=None,
        contact_range_m=0.0,
        visibility_bound_m=1_000.0,
        sensing_sensor_source_equipment_index=None,
        sensing_sensor_id=None,
        sensing_sensor_modeled_role=None,
        sensing_range_m=0.0,
        fire_control_source=FireControlSource.NONE,
        fire_control_sensor_source_equipment_index=None,
        fire_control_sensor_id=None,
        fire_control_sensor_modeled_role=None,
        fire_control_range_m=0.0,
        disposition=TargetingDisposition.NO_TARGET,
        authorized_standoff_m=0.0,
        hold_authorized=False,
        engagement_solution_valid=False,
        sensing_aware_standoff_enabled=True,
        fog_of_war_enabled=True,
        consumable=True,
    )


def _supported_blue_decision() -> TacticalTargetingDecision:
    support = ObserverTrackSupportEvidence(
        identity=ObserverTrackSupportIdentity(
            attachment_identity=TacticalAttachmentIdentity(
                reporting_side="blue",
                observer_unit_id="blue-1",
                source_equipment_index=3,
                sensor_id="hidden-fire-control-radar",
                modeled_role=SensorModeledRole.FIRE_CONTROL_RADAR.value,
            ),
            target_id="red-1",
        ),
        fusion_track_id="fow-track-0042",
        sensor_type=SensorType.RADAR,
        observation_ordinal=1,
        observation_time_s=25.0,
        native_period=2,
        native_phase_residue=1,
        native_due_ordinal=3,
        projection_ordinal=2,
        projection_time_s=30.0,
        position_m=(0.0, 500.0),
        velocity_mps=(0.0, 0.0),
        covariance=(
            (100.0, 0.0, 0.0, 0.0),
            (0.0, 100.0, 0.0, 0.0),
            (0.0, 0.0, 100.0, 0.0),
            (0.0, 0.0, 0.0, 100.0),
        ),
    )
    return replace(
        _targeted_blue_decision(),
        contact_source=ContactSource.FOW_OBSERVER_TRACK_SUPPORT,
        contact_sensor_id="hidden-fire-control-radar",
        contact_sensor_modeled_role=SensorModeledRole.FIRE_CONTROL_RADAR,
        contact_range_m=1_000.0,
        sensing_sensor_id="hidden-fire-control-radar",
        sensing_sensor_modeled_role=SensorModeledRole.FIRE_CONTROL_RADAR,
        sensing_range_m=1_000.0,
        fire_control_source=FireControlSource.SENSOR_ATTACHMENT,
        fire_control_sensor_source_equipment_index=3,
        fire_control_sensor_id="hidden-fire-control-radar",
        fire_control_sensor_modeled_role=SensorModeledRole.FIRE_CONTROL_RADAR,
        observer_track_support=support,
    )


def _runtime() -> TacticalTargetingRuntime:
    runtime = TacticalTargetingRuntime(
        sensing_aware_standoff_enabled=True,
        unit_sides={"blue-1": "blue", "red-1": "red"},
    )
    interval = runtime.stage_interval(
        engine_tick=7,
        logical_time_s=30.0,
        fog_of_war_enabled=True,
        unit_sides={"blue-1": "blue", "red-1": "red"},
        battle_memberships={
            "battle-alpha": ("blue-1", "red-1"),
        },
    )
    runtime.publish_interval(
        interval,
        (
            TacticalTargetingPicture(
                engine_tick=7,
                logical_time_s=30.0,
                battle_id="battle-alpha",
                fog_of_war_enabled=True,
                decisions=(
                    _targeted_blue_decision(),
                    _red_no_target_decision(),
                ),
            ),
        ),
    )
    runtime.publish_engagement_revalidation(
        TacticalEngagementRevalidationOutcome(
            engine_tick=7,
            logical_time_s=30.0,
            battle_id="battle-alpha",
            shooter_id="blue-1",
            target_id="red-1",
            weapon_id="direct-gun",
            weapon_source_equipment_index=2,
            weapon_modeled_role=WeaponModeledRole.GROUND_DIRECT_FIRE,
            ammunition_id="direct-shell",
            disposition=TargetingDisposition.VALID_ENGAGEMENT_SOLUTION,
            revalidation_passed=True,
            fog_of_war_enabled=True,
            consumable=True,
        ),
    )
    return runtime


def _blue_contact() -> ContactRecord:
    info = ContactInfo(
        level=ContactLevel.CLASSIFIED,
        domain_estimate="GROUND",
        type_estimate="armor",
        specific_estimate=None,
        confidence=0.75,
    )
    track = Track(
        track_id="fow-track-0042",
        side="blue",
        contact_info=info,
        state=TrackState(
            position=np.array([501.0, 2.0]),
            velocity=np.array([-1.0, 0.5]),
            covariance=np.diag([25.0, 16.0, 1.0, 1.0]),
            last_update_time=30.0,
        ),
        status=TrackStatus.CONFIRMED,
    )
    return ContactRecord(
        contact_id="red-1",
        track=track,
        contact_info=info,
        first_detected_time=20.0,
        last_sensor_contact_time=30.0,
        reporting_sensors=["hidden-binocular-attachment"],
    )


def _fog_owner(*, include_blue_contact: bool = True) -> _FogOfWarViewOwner:
    return _FogOfWarViewOwner(
        {
            "blue": SideWorldView(
                side="blue",
                contacts=({"red-1": _blue_contact()} if include_blue_contact else {}),
                last_update_time=30.0,
            ),
            "red": SideWorldView(side="red", last_update_time=30.0),
        }
    )


def test_privileged_and_side_snapshots_use_same_committed_decision() -> None:
    runtime = _runtime()
    bundle = capture_targeting_exposure(
        engine_tick=7,
        runtime=runtime,
        fog_of_war=_fog_owner(),
        fog_of_war_enabled=True,
        viewer_sides=("red", "blue"),
    )

    assert bundle.privileged.decisions[0] is (runtime.latest_pictures()[0].decisions[0])
    assert bundle.privileged.decisions[0].target_id == "red-1"
    blue = next(item for item in bundle.sides if item.viewer_side == "blue")
    assert blue.decisions[0].target_track_id == "fow-track-0042"
    assert blue.decisions[0].disposition is (bundle.privileged.decisions[0].disposition)
    assert blue.decisions[0].authorized_standoff_m == 500.0
    exact_outcome = bundle.privileged_engagement_revalidations.outcomes[0]
    assert exact_outcome is runtime.latest_engagement_revalidations()[0]
    assert exact_outcome.target_id == "red-1"
    assert exact_outcome.weapon_id == "direct-gun"
    assert blue.engagement_revalidations[0].target_track_id == "fow-track-0042"
    assert blue.engagement_revalidations[0].revalidation_passed
    assert blue.engagement_revalidations[0].disposition is (TargetingDisposition.VALID_ENGAGEMENT_SOLUTION)


def test_side_picture_ordinals_do_not_reveal_hidden_opposing_shooters() -> None:
    bundle = capture_targeting_exposure(
        engine_tick=7,
        runtime=_runtime(),
        fog_of_war=_fog_owner(),
        fog_of_war_enabled=True,
        viewer_sides=("blue", "red"),
    )

    exact_red = next(
        decision
        for decision in bundle.privileged.decisions
        if decision.shooter_side == "red"
    )
    public_red = next(side for side in bundle.sides if side.viewer_side == "red")
    assert exact_red.ordinal == 1
    assert public_red.decisions[0].ordinal == 0


def test_side_wire_omits_ground_truth_attachment_and_other_side_units() -> None:
    runtime = _runtime()
    bundle = capture_targeting_exposure(
        engine_tick=7,
        runtime=runtime,
        fog_of_war=_fog_owner(),
        fog_of_war_enabled=True,
        viewer_sides=("blue", "red"),
    )
    wire = bundle.to_wire(
        unit_frames=(
            {"id": "blue-1", "side": "blue", "x": 0.0, "y": 0.0},
            {"id": "red-1", "side": "red", "x": 500.0, "y": 0.0},
        ),
        fog_of_war_enabled=True,
    )
    blue = wire["side_fow"]["blue"]
    serialized = json.dumps(blue, sort_keys=True)

    assert wire["targeting_exposure_schema_version"] == 118
    assert wire["fog_of_war_enabled"] is True
    assert wire["side_fow_associations"] == {
        "blue": {"red-1": "fow-track-0042"},
        "red": {},
    }
    assert "side_fow_associations" not in blue
    assert blue["scope"] == TargetingExposureScope.SIDE_FOW.value
    assert [item["id"] for item in blue["units"]] == ["blue-1"]
    assert blue["tracks"][0]["track_id"] == "fow-track-0042"
    assert "red-1" not in serialized
    assert "direct-gun" not in serialized
    assert "hidden-binocular-attachment" not in serialized
    assert "source_equipment_index" not in serialized
    assert "target_id" not in serialized
    assert "target_side" not in serialized
    assert "weapon_id" not in serialized
    assert blue["targeting_outcomes"][0]["target_track_id"] == "fow-track-0042"
    assert blue["targeting_outcomes"][0]["revalidation_passed"] is True

    privileged = json.dumps(wire["targeting"], sort_keys=True)
    assert "red-1" in privileged
    assert "direct-gun" in privileged
    assert "hidden-binocular-attachment" in privileged
    privileged_outcome = wire["targeting_outcomes"][0]
    assert privileged_outcome["target_id"] == "red-1"
    assert privileged_outcome["weapon_id"] == "direct-gun"


def test_side_projection_accepts_support_only_for_its_exact_public_track() -> None:
    decision = _supported_blue_decision()
    public = SideFowTargetingDecisionExposure.from_decision(
        decision,
        viewer_side="blue",
        target_track_id="fow-track-0042",
        side_local_ordinal=0,
    )

    wire = public.to_wire()
    assert wire["contact_source"] == "FOW_OBSERVER_TRACK_SUPPORT"
    assert wire["contact_time_s"] == decision.logical_time_s
    serialized = json.dumps(wire, sort_keys=True)
    assert "observer_track_support" not in serialized
    assert "hidden-fire-control-radar" not in serialized
    assert "red-1" not in serialized

    with pytest.raises(
        ValueError,
        match="support disagrees with the public target track",
    ):
        SideFowTargetingDecisionExposure.from_decision(
            decision,
            viewer_side="blue",
            target_track_id="fow-track-0043",
            side_local_ordinal=0,
        )


def test_side_failed_revalidation_exposes_reason_without_exact_identity() -> None:
    failed = TacticalEngagementRevalidationOutcome(
        engine_tick=7,
        logical_time_s=30.0,
        battle_id="battle-alpha",
        shooter_id="blue-1",
        target_id="red-1",
        weapon_id="direct-gun",
        weapon_source_equipment_index=2,
        weapon_modeled_role=WeaponModeledRole.GROUND_DIRECT_FIRE,
        ammunition_id="direct-shell",
        disposition=TargetingDisposition.OUTSIDE_PHYSICAL_RANGE,
        revalidation_passed=False,
        fog_of_war_enabled=True,
        consumable=True,
    )
    public = SideFowEngagementRevalidationExposure.from_outcome(
        failed,
        decision=_targeted_blue_decision(),
        viewer_side="blue",
        target_track_id="fow-track-0042",
    )
    wire = public.to_wire()

    assert not wire["revalidation_passed"]
    assert wire["disposition"] == "OUTSIDE_PHYSICAL_RANGE"
    assert wire["target_track_id"] == "fow-track-0042"
    serialized = json.dumps(wire, sort_keys=True)
    assert "red-1" not in serialized
    assert "direct-gun" not in serialized
    assert "direct-shell" not in serialized
    assert "source_equipment_index" not in serialized


def test_side_snapshot_rejects_target_absent_from_current_world_view() -> None:
    with pytest.raises(ValueError, match="absent from the side world view"):
        capture_targeting_exposure(
            engine_tick=7,
            runtime=_runtime(),
            fog_of_war=_fog_owner(include_blue_contact=False),
            fog_of_war_enabled=True,
            viewer_sides=("blue", "red"),
        )


def test_side_snapshot_rejects_nonopaque_track_identifier() -> None:
    contact = _blue_contact()
    contact.track.track_id = "red-1"
    fog = _fog_owner()
    fog.get_world_view("blue").contacts["red-1"] = contact

    with pytest.raises(ValueError, match="opaque"):
        capture_targeting_exposure(
            engine_tick=7,
            runtime=_runtime(),
            fog_of_war=fog,
            fog_of_war_enabled=True,
            viewer_sides=("blue", "red"),
        )


def test_exposure_filters_bounded_history_to_requested_tick() -> None:
    bundle = capture_targeting_exposure(
        engine_tick=8,
        runtime=_runtime(),
        fog_of_war=None,
        fog_of_war_enabled=False,
        viewer_sides=("blue", "red"),
    )

    assert bundle.privileged.decisions == ()
    assert bundle.privileged_engagement_revalidations.outcomes == ()
    assert not bundle.side_fow_available
    assert bundle.sides == ()


@pytest.mark.parametrize("fog_of_war_enabled", (False, True))
def test_empty_current_capture_persists_explicit_fow_mode(
    fog_of_war_enabled: bool,
) -> None:
    runtime = TacticalTargetingRuntime(
        sensing_aware_standoff_enabled=True,
        unit_sides={"blue-1": "blue", "red-1": "red"},
    )
    unit_frames = (
        {"id": "blue-1", "side": "blue"},
        {"id": "red-1", "side": "red"},
    )
    bundle = capture_targeting_exposure(
        engine_tick=0,
        runtime=runtime,
        fog_of_war=(
            _fog_owner(include_blue_contact=False)
            if fog_of_war_enabled
            else None
        ),
        fog_of_war_enabled=fog_of_war_enabled,
        viewer_sides=("blue", "red"),
    )
    wire = {
        "tick": 0,
        "units": list(unit_frames),
        **bundle.to_wire(
            unit_frames=unit_frames,
            fog_of_war_enabled=fog_of_war_enabled,
        ),
    }

    assert wire["targeting_exposure_schema_version"] == 118
    assert wire["fog_of_war_enabled"] is fog_of_war_enabled
    assert wire["side_fow_available"] is fog_of_war_enabled
    expected_sides = {"blue", "red"} if fog_of_war_enabled else set()
    assert set(wire["side_fow"]) == expected_sides
    assert set(wire["side_fow_associations"]) == expected_sides
    decoded = decode_stored_targeting_exposure(
        engine_tick=0,
        stored_frame=wire,
    )
    assert decoded.bundle.side_fow_available is fog_of_war_enabled
    assert decoded.bundle.privileged.decisions == ()


def test_current_wire_rejects_fow_mode_availability_disagreement() -> None:
    bundle = capture_targeting_exposure(
        engine_tick=0,
        runtime=TacticalTargetingRuntime(
            sensing_aware_standoff_enabled=True,
            unit_sides={"blue-1": "blue"},
        ),
        fog_of_war=FogOfWarManager(rng=np.random.default_rng(118)),
        fog_of_war_enabled=True,
        viewer_sides=("blue",),
    )

    with pytest.raises(
        ValueError,
        match="frame FOW mode disagrees with SIDE_FOW availability",
    ):
        bundle.to_wire(
            unit_frames=({"id": "blue-1", "side": "blue"},),
            fog_of_war_enabled=False,
        )


def test_capture_rejects_fow_enablement_disagreement_with_decisions() -> None:
    with pytest.raises(
        ValueError,
        match="FOW enablement disagrees with the committed targeting interval",
    ):
        capture_targeting_exposure(
            engine_tick=7,
            runtime=_runtime(),
            fog_of_war=None,
            fog_of_war_enabled=False,
            viewer_sides=("blue", "red"),
        )


def test_exposure_read_does_not_create_missing_fog_world_views() -> None:
    runtime = TacticalTargetingRuntime(
        sensing_aware_standoff_enabled=True,
        unit_sides={"blue-1": "blue"},
    )
    fog = FogOfWarManager(rng=np.random.default_rng(115))
    before = fog.get_state()

    bundle = capture_targeting_exposure(
        engine_tick=0,
        runtime=runtime,
        fog_of_war=fog,
        fog_of_war_enabled=True,
        viewer_sides=("blue",),
    )

    assert bundle.sides[0].tracks == ()
    assert fog.peek_world_view("blue") is None
    assert fog.get_state() == before


def test_side_snapshot_requires_exact_registered_viewer_sides() -> None:
    with pytest.raises(
        ValueError,
        match="viewer sides must exactly match targeting registration",
    ):
        capture_targeting_exposure(
            engine_tick=7,
            runtime=_runtime(),
            fog_of_war=_fog_owner(),
            fog_of_war_enabled=True,
            viewer_sides=("blue",),
        )


def test_side_snapshot_codec_rejects_extra_ground_truth_field() -> None:
    bundle = capture_targeting_exposure(
        engine_tick=7,
        runtime=_runtime(),
        fog_of_war=_fog_owner(),
        fog_of_war_enabled=True,
        viewer_sides=("blue", "red"),
    )
    wire = bundle.to_wire(
        unit_frames=(
            {"id": "blue-1", "side": "blue"},
            {"id": "red-1", "side": "red"},
        ),
        fog_of_war_enabled=True,
    )["side_fow"]["blue"]
    restored = SideFowTargetingExposure.from_wire(engine_tick=7, value=wire)
    assert restored == bundle.sides[0]

    wire["targeting"][0]["target_id"] = "red-1"
    with pytest.raises(ValueError, match="invalid key topology"):
        SideFowTargetingExposure.from_wire(engine_tick=7, value=wire)

    clean_wire = bundle.to_wire(
        unit_frames=(
            {"id": "blue-1", "side": "blue"},
            {"id": "red-1", "side": "red"},
        ),
        fog_of_war_enabled=True,
    )["side_fow"]["blue"]
    clean_wire["targeting_outcomes"][0]["weapon_id"] = "direct-gun"
    with pytest.raises(ValueError, match="invalid key topology"):
        SideFowTargetingExposure.from_wire(engine_tick=7, value=clean_wire)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("status", "FRESH", "TrackStatus"),
        ("identification_level", "FULLY_KNOWN", "ContactLevel"),
    ),
)
def test_side_snapshot_rejects_unknown_public_track_enums(
    field: str,
    value: str,
    message: str,
) -> None:
    wire = capture_targeting_exposure(
        engine_tick=7,
        runtime=_runtime(),
        fog_of_war=_fog_owner(),
        fog_of_war_enabled=True,
        viewer_sides=("blue", "red"),
    ).to_wire(
        unit_frames=(
            {"id": "blue-1", "side": "blue"},
            {"id": "red-1", "side": "red"},
        ),
        fog_of_war_enabled=True,
    )["side_fow"]["blue"]
    wire["tracks"][0][field] = value

    with pytest.raises(ValueError, match=message):
        SideFowTargetingExposure.from_wire(engine_tick=7, value=wire)


@pytest.mark.parametrize(
    ("section", "field", "value", "message"),
    (
        (
            "targeting",
            "engagement_solution_valid",
            False,
            "engagement_solution_valid disagree",
        ),
        (
            "targeting_outcomes",
            "disposition",
            "OUTSIDE_PHYSICAL_RANGE",
            "passed SIDE_FOW revalidation",
        ),
        (
            "targeting_outcomes",
            "consumable",
            False,
            "association disagrees",
        ),
        (
            "targeting",
            "contact_source",
            "NON_FOW_LOCAL_OBSERVATION",
            "same-interval FOW authority",
        ),
        (
            "targeting",
            "contact_time_s",
            29.0,
            "same-interval FOW authority",
        ),
    ),
)
def test_side_snapshot_rejects_semantically_inconsistent_public_evidence(
    section: str,
    field: str,
    value: object,
    message: str,
) -> None:
    wire = capture_targeting_exposure(
        engine_tick=7,
        runtime=_runtime(),
        fog_of_war=_fog_owner(),
        fog_of_war_enabled=True,
        viewer_sides=("blue", "red"),
    ).to_wire(
        unit_frames=(
            {"id": "blue-1", "side": "blue"},
            {"id": "red-1", "side": "red"},
        ),
        fog_of_war_enabled=True,
    )["side_fow"]["blue"]
    wire[section][0][field] = value

    with pytest.raises(ValueError, match=message):
        SideFowTargetingExposure.from_wire(engine_tick=7, value=wire)


@pytest.mark.parametrize("corruption", ("logical_time", "ordinal"))
def test_privileged_flattened_picture_revalidates_group_coherence(
    corruption: str,
) -> None:
    first = _targeted_blue_decision()
    second = replace(
        first,
        shooter_id="blue-2",
        observing_unit_id="blue-2",
        ordinal=1,
    )
    if corruption == "logical_time":
        second = replace(second, logical_time_s=31.0, contact_time_s=31.0)
        message = "incoherent targeting interval"
    else:
        second = replace(second, ordinal=2)
        message = "noncanonical picture ordinal"

    with pytest.raises(ValueError, match=message):
        PrivilegedTargetingExposure(
            engine_tick=7,
            decisions=(first, second),
        )


@pytest.mark.parametrize("corruption", ("logical_time", "ordinal"))
def test_side_flattened_picture_revalidates_retained_ordinal_coherence(
    corruption: str,
) -> None:
    wire = capture_targeting_exposure(
        engine_tick=7,
        runtime=_runtime(),
        fog_of_war=_fog_owner(),
        fog_of_war_enabled=True,
        viewer_sides=("blue", "red"),
    ).to_wire(
        unit_frames=(
            {"id": "blue-1", "side": "blue"},
            {"id": "red-1", "side": "red"},
        ),
        fog_of_war_enabled=True,
    )["side_fow"]["blue"]
    second = deepcopy(wire["targeting"][0])
    second["shooter_id"] = "blue-2"
    second["ordinal"] = 1
    if corruption == "logical_time":
        second["logical_time_s"] = 31.0
        second["contact_time_s"] = 31.0
        message = "incoherent targeting interval"
    else:
        wire["targeting"][0]["ordinal"] = 2
        message = "ordinals are not canonical side-local ordinals"
    wire["targeting"].append(second)

    with pytest.raises(ValueError, match=message):
        SideFowTargetingExposure.from_wire(engine_tick=7, value=wire)


@pytest.mark.parametrize("corruption", ("logical_time", "fog_mode"))
def test_privileged_flattened_picture_requires_global_interval_coherence(
    corruption: str,
) -> None:
    first = _targeted_blue_decision()
    if corruption == "logical_time":
        second = replace(
            first,
            battle_id="battle-zulu",
            ordinal=0,
            logical_time_s=31.0,
            contact_time_s=31.0,
        )
    else:
        second = replace(
            _red_no_target_decision(),
            battle_id="battle-zulu",
            ordinal=0,
            fog_of_war_enabled=False,
        )

    with pytest.raises(ValueError, match="incoherent targeting interval"):
        PrivilegedTargetingExposure(
            engine_tick=7,
            decisions=(first, second),
        )


def test_unit_frame_filter_is_canonical_and_rejects_duplicates() -> None:
    frames = filter_side_unit_frames(
        (
            {"id": "blue-z", "side": "blue"},
            {"id": "red-a", "side": "red"},
            {"id": "blue-a", "side": "blue"},
        ),
        viewer_side="blue",
    )
    assert [item["id"] for item in frames] == ["blue-a", "blue-z"]

    with pytest.raises(ValueError, match="duplicate unit ID"):
        filter_side_unit_frames(
            (
                {"id": "same", "side": "blue"},
                {"id": "same", "side": "red"},
            ),
            viewer_side="blue",
        )
