"""Phase 116 standalone fog-of-war contact-state integrity tests."""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pytest

from stochastic_warfare.core.indexed_rng import IndexedFOWRNG
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.detection.cadence import (
    TacticalAttachmentIdentity,
    TacticalCadenceAttachment,
)
from stochastic_warfare.detection.detection import DetectionResult
from stochastic_warfare.detection.fog_of_war import (
    DataLinkConfig,
    FogOfWarLodTier,
    FogOfWarManager,
)
from stochastic_warfare.detection.identification import IdentificationEngine
from stochastic_warfare.detection.intel_fusion import (
    IMINTTrackAssociation,
    IntelDeliveryReceipt,
    IntelSource,
    SatellitePass,
)
from stochastic_warfare.detection.sensors import SensorDefinition, SensorInstance
from stochastic_warfare.detection.signatures import (
    SignatureProfile,
    VisualSignature,
)
from stochastic_warfare.simulation.loadouts import SensorModeledRole


_CONTACT_KEYS = {
    "contact_id",
    "track",
    "contact_info",
    "first_detected_time",
    "last_sensor_contact_time",
    "reporting_sensors",
}
_CONTACT_INFO_KEYS = {
    "level",
    "domain_estimate",
    "type_estimate",
    "specific_estimate",
    "confidence",
}
_TRACK_KEYS = {
    "track_id",
    "side",
    "contact_info",
    "state",
    "status",
    "hits",
    "misses",
}
_TRACK_STATE_KEYS = {
    "position",
    "velocity",
    "covariance",
    "last_update_time",
}
_WITNESS_KEYS = {
    "side",
    "observer_unit_id",
    "target_id",
    "source_equipment_index",
    "sensor_id",
    "modeled_role",
    "logical_time_s",
    "detected",
    "probability",
    "snr_db",
    "range_m",
    "sensor_type",
    "bearing_deg",
}


@dataclass(frozen=True, slots=True)
class _SensorAttachment:
    sensor: SensorInstance
    source_equipment_index: int
    modeled_role: SensorModeledRole

    @property
    def sensor_id(self) -> str:
        return self.sensor.sensor_id


def _sensor(sensor_id: str) -> SensorInstance:
    return SensorInstance(
        SensorDefinition(
            sensor_id=sensor_id,
            sensor_type="VISUAL",
            display_name=sensor_id,
            max_range_m=50_000.0,
            detection_threshold=-100.0,
        ),
    )


def _signature() -> SignatureProfile:
    return SignatureProfile(
        profile_id="phase116-contact-target",
        unit_type="test",
        visual=VisualSignature(
            cross_section_m2=500.0,
            camouflage_factor=1.0,
        ),
    )


def _successful_detection(
    observer_position: Position,
    target_position: Position,
    sensor: SensorInstance,
    _target_signature: SignatureProfile,
    **_kwargs: Any,
) -> DetectionResult:
    dx = target_position.easting - observer_position.easting
    dy = target_position.northing - observer_position.northing
    return DetectionResult(
        detected=True,
        probability=0.75,
        snr_db=8.5,
        range_m=math.hypot(dx, dy),
        sensor_type=sensor.sensor_type,
        bearing_deg=math.degrees(math.atan2(dx, dy)) % 360.0,
        horizontal_range_m=math.hypot(dx, dy),
    )


def _manager(
    seed: int,
    *,
    data_link_config: DataLinkConfig | None = None,
    with_identification: bool = False,
) -> FogOfWarManager:
    rng = np.random.default_rng(seed)
    identification = IdentificationEngine(rng) if with_identification else None
    manager = FogOfWarManager(
        identification_engine=identification,
        data_link_config=data_link_config,
        rng=rng,
    )
    manager._detection.check_detection = _successful_detection
    return manager


def _add_contact(
    manager: FogOfWarManager,
    *,
    side: str,
    observer_id: str,
    target_id: str,
    sensor_id: str,
    current_time: float,
) -> None:
    sensor = _sensor(sensor_id)
    attachment = _SensorAttachment(
        sensor=sensor,
        source_equipment_index=2,
        modeled_role=SensorModeledRole.VISUAL_OBSERVATION,
    )
    identity = TacticalAttachmentIdentity(
        reporting_side=side,
        observer_unit_id=observer_id,
        source_equipment_index=attachment.source_equipment_index,
        sensor_id=sensor.sensor_id,
        modeled_role=attachment.modeled_role.value,
    )
    tick = manager.cadence.committed_ordinal
    transaction = manager.begin_update_transaction((side,))
    cadence = manager.cadence.stage_interval(
        (
            TacticalCadenceAttachment(
                identity=identity,
                native_period=1,
                lod_period=1,
                operational=True,
            ),
        ),
    )
    indexed = IndexedFOWRNG(116_052)
    allocation = indexed.begin_interval(
        module=ModuleId.DETECTION,
        engine_tick=tick,
        reporting_sides=(side,),
    )
    side_plan = manager.update_with_receipt(
        side,
        [
            {
                "unit_id": observer_id,
                "position": Position(0.0, 0.0, 0.0),
                "sensors": (sensor,),
                "sensor_attachments": (attachment,),
                "observer_height": 2.5,
                "observer_heading_deg": 0.0,
            },
        ],
        [
            {
                "unit_id": target_id,
                "position": Position(500.0, 0.0, 0.0),
                "signature": _signature(),
                "unit": None,
                "target_height": 3.0,
                "concealment": 0.0,
                "posture": 0,
            },
        ],
        dt=1.0,
        transaction=transaction,
        cadence_plan=cadence,
        indexed_rng=allocation.acquire_side(side),
        lod_tiers={identity.observer: FogOfWarLodTier.ACTIVE},
        current_time=current_time,
        current_tick=tick,
        detection_culling=False,
    )
    publication = manager.prevalidate_update_transaction(
        transaction,
        (side_plan,),
    )
    indexed.commit_interval(allocation)
    manager.cadence.commit_interval(cadence)
    manager.commit_update_transaction(publication)


def _populated_manager(
    seed: int = 116,
    *,
    side: str = "blue",
    observer_id: str = "blue-observer",
    target_id: str = "red-target",
    sensor_id: str = "blue-eye",
    current_time: float = 10.0,
) -> FogOfWarManager:
    manager = _manager(seed)
    _add_contact(
        manager,
        side=side,
        observer_id=observer_id,
        target_id=target_id,
        sensor_id=sensor_id,
        current_time=current_time,
    )
    return manager


def _valid_state() -> dict[str, Any]:
    return _populated_manager().get_state()


def _contact(state: dict[str, Any]) -> dict[str, Any]:
    return state["world_views"]["blue"]["contacts"]["red-target"]


def _witness(state: dict[str, Any]) -> dict[str, Any]:
    return state["current_detection_witnesses"]["blue"][0]


def _fusion_track(state: dict[str, Any]) -> dict[str, Any]:
    return state["intel_fusion"]["tracks"]["blue"]["fow-track-0001"]


def _synchronize_contact_track(state: dict[str, Any]) -> None:
    state["intel_fusion"]["tracks"]["blue"]["fow-track-0001"] = (
        copy.deepcopy(_contact(state)["track"])
    )


def test_capture_rejects_state_equal_contact_track_outside_fusion_owner() -> None:
    manager = _populated_manager()
    expected = manager.get_state()
    contact = manager.get_world_view("blue").contacts["red-target"]
    fusion_track = manager._intel_fusion._tracks["blue"][contact.track.track_id]

    contact.track = copy.deepcopy(fusion_track)
    assert contact.track is not fusion_track
    assert contact.track.get_state() == fusion_track.get_state()
    with pytest.raises(ValueError, match="exact fusion-owned track"):
        manager.get_state()
    assert contact.track.get_state() == fusion_track.get_state()
    assert manager._intel_fusion.get_state() == expected["intel_fusion"]

    contact.track = fusion_track
    assert manager.get_state() == expected


def _assert_atomic_rejection(
    invalid: dict[str, Any],
    valid: dict[str, Any],
    *,
    checkpoint_elapsed_s: float = 10.0,
    authoritative_rng_state: dict[str, Any] | None = None,
    allow_legacy_state: bool = False,
) -> None:
    target = _populated_manager(
        9_116,
        side="red",
        observer_id="red-observer",
        target_id="blue-stale-target",
        sensor_id="red-eye",
        current_time=3.0,
    )
    before = target.get_state()

    with pytest.raises(ValueError):
        target.stage_state(
            invalid,
            checkpoint_elapsed_s=checkpoint_elapsed_s,
            authoritative_rng_state=authoritative_rng_state,
            allow_legacy_state=allow_legacy_state,
        )

    assert target.get_state() == before
    plan = target.stage_state(
        valid,
        checkpoint_elapsed_s=10.0,
    )
    target.commit_state(plan)
    assert target.get_state() == valid


def _assert_valid_restore(state: dict[str, Any], *, elapsed: float) -> None:
    target = _manager(8_116)
    plan = target.stage_state(state, checkpoint_elapsed_s=elapsed)
    target.commit_state(plan)
    assert target.get_state() == state


def test_current_state_has_exact_nested_envelope() -> None:
    state = _valid_state()

    assert set(state) == {
        "world_views",
        "current_detection_witnesses",
        "observer_track_supports",
        "rng_state",
        "intel_fusion",
        "scan_counts",
        "cadence",
    }
    assert state["observer_track_supports"] == []
    assert state["scan_counts"] == {
        'observer-v1:["blue","blue-observer",2,"blue-eye","red-target"]': 1,
    }
    cadence = state["cadence"]
    assert set(cadence) == {
        "schema_version",
        "committed_ordinal",
        "complete_from_tick_zero",
        "attachments",
        "native_phase_assignments",
        "native_phase_assignments_sha256",
    }
    assert cadence["schema_version"] == 2
    assert cadence["committed_ordinal"] == 1
    assert cadence["complete_from_tick_zero"] is True
    assert len(cadence["attachments"]) == 1
    assert len(cadence["native_phase_assignments"]) == 1
    assert list(state["world_views"]) == ["blue"]
    view = state["world_views"]["blue"]
    assert set(view) == {"side", "contacts", "last_update_time"}
    assert list(view["contacts"]) == ["red-target"]
    contact = _contact(state)
    assert set(contact) == _CONTACT_KEYS
    assert set(contact["contact_info"]) == _CONTACT_INFO_KEYS
    assert set(contact["track"]) == _TRACK_KEYS
    assert set(contact["track"]["contact_info"]) == _CONTACT_INFO_KEYS
    assert set(contact["track"]["state"]) == _TRACK_STATE_KEYS
    assert list(state["current_detection_witnesses"]) == ["blue"]
    assert len(state["current_detection_witnesses"]["blue"]) == 1
    assert set(_witness(state)) == _WITNESS_KEYS


def test_nonempty_state_restores_into_fresh_manager_with_fusion_alias() -> None:
    source = _populated_manager()
    source_state = source.get_state()
    source_track = source.get_contact("blue", "red-target").track
    target = _manager(99_116)

    target.set_state(source_state)

    assert target.get_state() == source_state
    restored = target.get_contact("blue", "red-target")
    assert restored is not None
    fusion_track = target.intel_fusion.get_tracks("blue")["fow-track-0001"]
    assert restored.track is fusion_track
    assert restored.track is not source_track
    assert target.get_current_detection_witnesses() == (
        source.get_current_detection_witnesses()
    )


def test_restore_plan_exposes_only_defensive_mutable_state() -> None:
    valid = _valid_state()
    target = _manager(116_004)
    plan = target.stage_state(valid, checkpoint_elapsed_s=10.0)

    plan.world_views["blue"].contacts.clear()
    plan.current_detection_witnesses.clear()
    plan.rng_state.clear()
    plan.intel_fusion["tracks"].clear()

    target.commit_state(plan)
    assert target.get_state() == valid
    contact = target.get_world_view("blue").contacts["red-target"]
    fusion_track = target._intel_fusion._tracks["blue"][
        contact.track.track_id
    ]
    assert contact.track is fusion_track


@pytest.mark.parametrize(
    "mutation",
    (
        "world_views",
        "detached_equal_contact_track",
        "witnesses",
        "witness_tuple_to_list",
        "reporting_sensors_list_to_tuple",
        "track_status_enum_to_int",
        "track_position_dtype",
        "ledger_ordered_list_to_tuple",
        "rng_state",
        "intel_fusion",
    ),
)
def test_mutated_restore_plan_rejects_without_mutation_and_allows_retry(
    mutation: str,
) -> None:
    valid = _valid_state()
    target = _manager(116_005)
    before = target.get_state()
    plan = target.stage_state(valid, checkpoint_elapsed_s=10.0)

    if mutation == "world_views":
        plan._world_views["blue"].contacts.clear()
    elif mutation == "detached_equal_contact_track":
        contact = plan._world_views["blue"].contacts["red-target"]
        contact.track = copy.deepcopy(contact.track)
    elif mutation == "witnesses":
        plan._current_detection_witnesses.clear()
    elif mutation == "witness_tuple_to_list":
        plan._current_detection_witnesses["blue"] = list(
            plan._current_detection_witnesses["blue"],
        )
    elif mutation == "reporting_sensors_list_to_tuple":
        contact = plan._world_views["blue"].contacts["red-target"]
        contact.reporting_sensors = tuple(contact.reporting_sensors)
    elif mutation == "track_status_enum_to_int":
        track = plan._intel_fusion["tracks"]["blue"][
            "fow-track-0001"
        ]
        track.status = int(track.status)
    elif mutation == "track_position_dtype":
        track = plan._intel_fusion["tracks"]["blue"][
            "fow-track-0001"
        ]
        track.state = track.state._replace(
            position=track.state.position.astype(np.float32),
        )
    elif mutation == "ledger_ordered_list_to_tuple":
        ledger = plan._intel_fusion["delivery_receipt_ledger"]
        ledger._ordered = tuple(ledger._ordered)
    elif mutation == "rng_state":
        plan._rng_state["state"]["state"] += 1
    else:
        plan._intel_fusion["tracks"]["blue"][
            "fow-track-0001"
        ].hits += 1

    with pytest.raises(ValueError, match="foreign or was mutated"):
        target.commit_state(plan)
    assert target.get_state() == before

    target.commit_state(
        target.stage_state(valid, checkpoint_elapsed_s=10.0),
    )
    assert target.get_state() == valid


def test_foreign_restore_plan_rejects_without_mutation() -> None:
    valid = _valid_state()
    source = _manager(116_006)
    target = _manager(116_007)
    plan = source.stage_state(valid, checkpoint_elapsed_s=10.0)
    before = target.get_state()

    with pytest.raises(ValueError, match="foreign or was mutated"):
        target.commit_state(plan)

    assert target.get_state() == before


def test_in_place_restore_replaces_views_contacts_and_target_only_state() -> None:
    source = _populated_manager()
    source.get_world_view("green")
    source_state = source.get_state()
    target = _populated_manager(
        17,
        side="red",
        observer_id="red-observer",
        target_id="blue-stale-target",
        sensor_id="red-eye",
        current_time=3.0,
    )
    _add_contact(
        target,
        side="blue",
        observer_id="old-blue-observer",
        target_id="old-red-target",
        sensor_id="old-blue-eye",
        current_time=4.0,
    )
    target.get_world_view("target-only")

    target.set_state(source_state)

    assert target.get_state() == source_state
    assert target.peek_world_view("red") is None
    assert target.peek_world_view("target-only") is None
    assert target.peek_world_view("green") is not None
    assert target.peek_world_view("green").contacts == {}
    assert list(target.peek_world_view("blue").contacts) == ["red-target"]
    contact = target.get_contact("blue", "red-target")
    assert contact is not None
    assert contact.track is target.intel_fusion.get_tracks("blue")[
        "fow-track-0001"
    ]


def test_restore_replaces_current_witness_map_without_stale_sides() -> None:
    source = _populated_manager()
    _add_contact(
        source,
        side="green",
        observer_id="green-observer",
        target_id="red-second-target",
        sensor_id="green-eye",
        current_time=10.0,
    )
    source_state = source.get_state()
    target = _populated_manager(
        18,
        side="red",
        observer_id="red-observer",
        target_id="blue-stale-target",
        sensor_id="red-eye",
        current_time=3.0,
    )

    target.set_state(source_state)

    assert target.get_current_detection_witnesses() == (
        source.get_current_detection_witnesses()
    )
    assert target.get_current_detection_witnesses("red") == ()
    assert target.get_state()["current_detection_witnesses"] == (
        source_state["current_detection_witnesses"]
    )


@pytest.mark.test_evidence("helper_assertion")
@pytest.mark.parametrize(
    "mutation",
    (
        "envelope_missing",
        "envelope_extra",
        "world_views_not_mapping",
        "world_views_noncanonical",
        "witnesses_not_mapping",
        "view_missing",
        "view_extra",
        "contacts_not_mapping",
        "contacts_noncanonical",
        "contact_not_mapping",
        "contact_missing",
        "contact_extra",
        "contact_info_missing",
        "contact_info_extra",
        "track_missing",
        "track_extra",
        "track_state_missing",
        "track_state_extra",
        "witnesses_not_list",
        "witness_not_mapping",
        "witness_missing",
        "witness_extra",
    ),
)
def test_exact_key_and_container_topology_rejects_atomically(
    mutation: str,
) -> None:
    valid = _valid_state()
    invalid = copy.deepcopy(valid)
    if mutation == "envelope_missing":
        invalid.pop("current_detection_witnesses")
    elif mutation == "envelope_extra":
        invalid["unexpected"] = None
    elif mutation == "world_views_not_mapping":
        invalid["world_views"] = []
    elif mutation == "world_views_noncanonical":
        blue_view = invalid["world_views"].pop("blue")
        invalid["world_views"] = {
            "red": {
                "side": "red",
                "contacts": {},
                "last_update_time": 0.0,
            },
            "blue": blue_view,
        }
    elif mutation == "witnesses_not_mapping":
        invalid["current_detection_witnesses"] = []
    elif mutation == "view_missing":
        invalid["world_views"]["blue"].pop("last_update_time")
    elif mutation == "view_extra":
        invalid["world_views"]["blue"]["unexpected"] = None
    elif mutation == "contacts_not_mapping":
        invalid["world_views"]["blue"]["contacts"] = []
    elif mutation == "contacts_noncanonical":
        contacts = invalid["world_views"]["blue"]["contacts"]
        earlier = copy.deepcopy(contacts["red-target"])
        earlier["contact_id"] = "aaa-target"
        contacts["aaa-target"] = earlier
    elif mutation == "contact_not_mapping":
        invalid["world_views"]["blue"]["contacts"]["red-target"] = []
    elif mutation == "contact_missing":
        _contact(invalid).pop("first_detected_time")
    elif mutation == "contact_extra":
        _contact(invalid)["unexpected"] = None
    elif mutation == "contact_info_missing":
        _contact(invalid)["contact_info"].pop("confidence")
    elif mutation == "contact_info_extra":
        _contact(invalid)["contact_info"]["unexpected"] = None
    elif mutation == "track_missing":
        _contact(invalid)["track"].pop("hits")
    elif mutation == "track_extra":
        _contact(invalid)["track"]["unexpected"] = None
    elif mutation == "track_state_missing":
        _contact(invalid)["track"]["state"].pop("velocity")
    elif mutation == "track_state_extra":
        _contact(invalid)["track"]["state"]["unexpected"] = None
    elif mutation == "witnesses_not_list":
        invalid["current_detection_witnesses"]["blue"] = {}
    elif mutation == "witness_not_mapping":
        invalid["current_detection_witnesses"]["blue"][0] = []
    elif mutation == "witness_missing":
        _witness(invalid).pop("range_m")
    else:
        _witness(invalid)["unexpected"] = None

    _assert_atomic_rejection(invalid, valid)


@pytest.mark.test_evidence("helper_assertion")
@pytest.mark.parametrize(
    "mutation",
    (
        "side_key_bool",
        "side_key_whitespace",
        "view_side_mismatch",
        "contact_key_whitespace",
        "contact_id_mismatch",
        "first_time_bool",
        "last_time_nan",
        "view_time_bool",
        "track_status_bool",
        "hits_bool",
        "hits_zero",
        "misses_bool",
        "misses_negative",
        "reporting_sensors_tuple",
    ),
)
def test_strict_identity_and_scalar_types_reject_atomically(
    mutation: str,
) -> None:
    valid = _valid_state()
    invalid = copy.deepcopy(valid)
    if mutation in {"side_key_bool", "side_key_whitespace"}:
        view = invalid["world_views"].pop("blue")
        key: object = True if mutation == "side_key_bool" else " blue"
        view["side"] = key
        invalid["world_views"][key] = view
    elif mutation == "view_side_mismatch":
        invalid["world_views"]["blue"]["side"] = "red"
    elif mutation == "contact_key_whitespace":
        contact = invalid["world_views"]["blue"]["contacts"].pop(
            "red-target",
        )
        contact["contact_id"] = " red-target"
        invalid["world_views"]["blue"]["contacts"][" red-target"] = contact
    elif mutation == "contact_id_mismatch":
        _contact(invalid)["contact_id"] = "different-target"
    elif mutation == "first_time_bool":
        _contact(invalid)["first_detected_time"] = True
    elif mutation == "last_time_nan":
        _contact(invalid)["last_sensor_contact_time"] = math.nan
    elif mutation == "view_time_bool":
        invalid["world_views"]["blue"]["last_update_time"] = True
    elif mutation == "track_status_bool":
        _contact(invalid)["track"]["status"] = True
        _synchronize_contact_track(invalid)
    elif mutation == "hits_bool":
        _contact(invalid)["track"]["hits"] = True
        _synchronize_contact_track(invalid)
    elif mutation == "hits_zero":
        _contact(invalid)["track"]["hits"] = 0
        _synchronize_contact_track(invalid)
    elif mutation == "misses_bool":
        _contact(invalid)["track"]["misses"] = True
        _synchronize_contact_track(invalid)
    elif mutation == "misses_negative":
        _contact(invalid)["track"]["misses"] = -1
        _synchronize_contact_track(invalid)
    else:
        _contact(invalid)["reporting_sensors"] = ("blue-eye",)

    _assert_atomic_rejection(invalid, valid)


@pytest.mark.test_evidence("helper_assertion")
@pytest.mark.parametrize(
    "mutation",
    (
        "level_bool",
        "unknown_live_contact",
        "unknown_level",
        "confidence_bool",
        "confidence_nan",
        "confidence_negative",
        "confidence_above_one",
        "estimate_non_string",
        "detected_retains_domain",
        "classified_retains_specific",
        "blank_estimate",
        "nested_detected_retains_type",
    ),
)
def test_contact_info_corruption_rejects_atomically(mutation: str) -> None:
    valid = _valid_state()
    invalid = copy.deepcopy(valid)
    contact_info = _contact(invalid)["contact_info"]
    if mutation == "level_bool":
        contact_info["level"] = True
    elif mutation == "unknown_live_contact":
        contact_info["level"] = 0
    elif mutation == "unknown_level":
        contact_info["level"] = 99
    elif mutation == "confidence_bool":
        contact_info["confidence"] = True
    elif mutation == "confidence_nan":
        contact_info["confidence"] = math.nan
    elif mutation == "confidence_negative":
        contact_info["confidence"] = -0.01
    elif mutation == "confidence_above_one":
        contact_info["confidence"] = 1.01
    elif mutation == "estimate_non_string":
        contact_info["domain_estimate"] = 7
    elif mutation == "detected_retains_domain":
        contact_info["domain_estimate"] = "GROUND"
    elif mutation == "classified_retains_specific":
        contact_info.update(
            level=2,
            domain_estimate="GROUND",
            type_estimate="ARMOR",
            specific_estimate="T-72",
        )
    elif mutation == "blank_estimate":
        contact_info.update(
            level=2,
            domain_estimate=" ",
            type_estimate="ARMOR",
        )
    else:
        nested = _contact(invalid)["track"]["contact_info"]
        nested["type_estimate"] = "ARMOR"
        _synchronize_contact_track(invalid)

    _assert_atomic_rejection(invalid, valid)


@pytest.mark.test_evidence("helper_assertion")
@pytest.mark.parametrize(
    "mutation",
    (
        "position_not_list",
        "position_wrong_shape",
        "position_bool",
        "velocity_nan",
        "covariance_not_list",
        "covariance_wrong_shape",
        "covariance_bool",
        "covariance_negative_diagonal",
        "covariance_asymmetric",
        "covariance_indefinite",
        "track_time_nan",
    ),
)
def test_track_vector_and_covariance_corruption_rejects_atomically(
    mutation: str,
) -> None:
    valid = _valid_state()
    invalid = copy.deepcopy(valid)
    track_state = _contact(invalid)["track"]["state"]
    if mutation == "position_not_list":
        track_state["position"] = (500.0, 0.0)
    elif mutation == "position_wrong_shape":
        track_state["position"] = [500.0]
    elif mutation == "position_bool":
        track_state["position"][0] = True
    elif mutation == "velocity_nan":
        track_state["velocity"][1] = math.nan
    elif mutation == "covariance_not_list":
        track_state["covariance"] = np.eye(4)
    elif mutation == "covariance_wrong_shape":
        track_state["covariance"] = [[1.0, 0.0], [0.0, 1.0]]
    elif mutation == "covariance_bool":
        track_state["covariance"][0][0] = True
    elif mutation == "covariance_negative_diagonal":
        track_state["covariance"][0][0] = -1.0
    elif mutation == "covariance_asymmetric":
        track_state["covariance"] = np.eye(4).tolist()
        track_state["covariance"][0][1] = 1.0e-4
    elif mutation == "covariance_indefinite":
        track_state["covariance"] = np.eye(4).tolist()
        track_state["covariance"][0][1] = 2.0
        track_state["covariance"][1][0] = 2.0
    else:
        track_state["last_update_time"] = math.nan
    _synchronize_contact_track(invalid)

    _assert_atomic_rejection(invalid, valid)


@pytest.mark.test_evidence("helper_assertion")
@pytest.mark.parametrize(
    ("mutation", "checkpoint_elapsed_s"),
    (
        ("first_negative", 10.0),
        ("first_after_last", 10.0),
        ("sensor_time_disagrees_with_track", 10.0),
        ("track_after_view", 11.0),
        ("view_after_checkpoint", 10.0),
    ),
)
def test_contact_chronology_corruption_rejects_atomically(
    mutation: str,
    checkpoint_elapsed_s: float,
) -> None:
    valid = _valid_state()
    invalid = copy.deepcopy(valid)
    contact = _contact(invalid)
    if mutation == "first_negative":
        contact["first_detected_time"] = -0.01
    elif mutation == "first_after_last":
        contact["first_detected_time"] = 10.1
    elif mutation == "sensor_time_disagrees_with_track":
        contact["first_detected_time"] = 0.0
        contact["last_sensor_contact_time"] = 9.0
    elif mutation == "track_after_view":
        contact["last_sensor_contact_time"] = 11.0
        contact["track"]["state"]["last_update_time"] = 11.0
        _synchronize_contact_track(invalid)
    else:
        invalid["world_views"]["blue"]["last_update_time"] = 11.0
        _witness(invalid)["logical_time_s"] = 11.0

    _assert_atomic_rejection(
        invalid,
        valid,
        checkpoint_elapsed_s=checkpoint_elapsed_s,
    )


@pytest.mark.test_evidence("helper_assertion")
@pytest.mark.parametrize(
    "mutation",
    (
        "tentative_at_confirmation_threshold",
        "confirmed_below_confirmation_threshold",
        "confirmed_past_coast_timeout",
        "coasting_below_confirmation_threshold",
        "coasting_past_lost_timeout",
        "coasting_above_uncertainty_limit",
        "stale_contact",
        "lost_contact",
    ),
)
def test_track_lifecycle_corruption_rejects_atomically(mutation: str) -> None:
    valid = _valid_state()
    invalid = copy.deepcopy(valid)
    track = _contact(invalid)["track"]
    elapsed = 10.0
    if mutation == "tentative_at_confirmation_threshold":
        track["hits"] = 3
    elif mutation == "confirmed_below_confirmation_threshold":
        track["status"] = 1
        track["hits"] = 2
    elif mutation == "confirmed_past_coast_timeout":
        track["status"] = 1
        track["hits"] = 3
        invalid["world_views"]["blue"]["last_update_time"] = 311.0
        invalid["current_detection_witnesses"]["blue"] = []
        elapsed = 311.0
    elif mutation == "coasting_below_confirmation_threshold":
        track["status"] = 2
        track["hits"] = 2
    elif mutation == "coasting_past_lost_timeout":
        track["status"] = 2
        track["hits"] = 3
        invalid["world_views"]["blue"]["last_update_time"] = 611.0
        invalid["current_detection_witnesses"]["blue"] = []
        elapsed = 611.0
    elif mutation == "coasting_above_uncertainty_limit":
        track["status"] = 2
        track["hits"] = 3
        track["state"]["covariance"] = np.diag(
            [60_000_000.0, 60_000_000.0, 1.0, 1.0],
        ).tolist()
    elif mutation == "stale_contact":
        track["status"] = 3
    else:
        track["status"] = 4
    _synchronize_contact_track(invalid)

    _assert_atomic_rejection(
        invalid,
        valid,
        checkpoint_elapsed_s=elapsed,
    )


@pytest.mark.test_evidence("helper_assertion")
@pytest.mark.parametrize(
    "lifecycle",
    (
        "tentative_below_threshold",
        "confirmed_at_coast_boundary",
        "coasting_below_coast_timeout",
        "coasting_at_lost_boundary",
        "coasting_at_uncertainty_limit",
    ),
)
def test_reachable_lifecycle_boundaries_restore_exactly(lifecycle: str) -> None:
    state = _valid_state()
    track = _contact(state)["track"]
    elapsed = 10.0
    if lifecycle == "tentative_below_threshold":
        track["hits"] = 2
    elif lifecycle == "confirmed_at_coast_boundary":
        track["status"] = 1
        track["hits"] = 3
        state["world_views"]["blue"]["last_update_time"] = 310.0
        state["current_detection_witnesses"]["blue"] = []
        elapsed = 310.0
    elif lifecycle == "coasting_below_coast_timeout":
        track["status"] = 2
        track["hits"] = 3
    elif lifecycle == "coasting_at_lost_boundary":
        track["status"] = 2
        track["hits"] = 3
        state["world_views"]["blue"]["last_update_time"] = 610.0
        state["current_detection_witnesses"]["blue"] = []
        elapsed = 610.0
    else:
        track["status"] = 2
        track["hits"] = 3
        track["state"]["covariance"] = np.diag(
            [50_000_000.0, 50_000_000.0, 1.0, 1.0],
        ).tolist()
    _synchronize_contact_track(state)

    _assert_valid_restore(state, elapsed=elapsed)


@pytest.mark.test_evidence("helper_assertion")
@pytest.mark.parametrize(
    "mutation",
    (
        "missing",
        "empty",
        "whitespace",
        "duplicate",
        "non_string",
    ),
)
def test_reporting_sensor_corruption_rejects_atomically(mutation: str) -> None:
    valid = _valid_state()
    invalid = copy.deepcopy(valid)
    sensors = _contact(invalid)["reporting_sensors"]
    if mutation == "missing":
        sensors.clear()
    elif mutation == "empty":
        sensors[0] = ""
    elif mutation == "whitespace":
        sensors[0] = " blue-eye"
    elif mutation == "duplicate":
        sensors.append("blue-eye")
    else:
        sensors[0] = 116

    _assert_atomic_rejection(invalid, valid)


def test_reporting_sensor_first_report_order_is_preserved() -> None:
    state = _valid_state()
    _contact(state)["reporting_sensors"] = ["zulu-eye", "alpha-eye"]
    _witness(state)["sensor_id"] = "zulu-eye"

    target = _manager(7_116)
    target.set_state(state)

    assert target.get_contact("blue", "red-target").reporting_sensors == [
        "zulu-eye",
        "alpha-eye",
    ]
    assert target.get_state() == state


@pytest.mark.test_evidence("helper_assertion")
@pytest.mark.parametrize(
    "mutation",
    (
        "missing_fusion_track",
        "detached_contact_track_state",
        "contact_track_id_mismatch",
        "contact_track_side_mismatch",
        "duplicate_contact_track_owner",
        "noncanonical_ordinary_track",
        "missing_fow_counter",
        "ahead_fow_counter",
        "unowned_live_fow_track",
    ),
)
def test_fusion_association_corruption_rejects_atomically(
    mutation: str,
) -> None:
    valid = _valid_state()
    invalid = copy.deepcopy(valid)
    if mutation == "missing_fusion_track":
        invalid["intel_fusion"]["tracks"]["blue"].clear()
    elif mutation == "detached_contact_track_state":
        _contact(invalid)["track"]["state"]["position"][0] += 1.0
    elif mutation == "contact_track_id_mismatch":
        _contact(invalid)["track"]["track_id"] = "fow-track-0002"
    elif mutation == "contact_track_side_mismatch":
        _contact(invalid)["track"]["side"] = "red"
    elif mutation == "duplicate_contact_track_owner":
        duplicate = copy.deepcopy(_contact(invalid))
        duplicate["contact_id"] = "second-red-target"
        invalid["world_views"]["blue"]["contacts"][
            "second-red-target"
        ] = duplicate
    elif mutation == "noncanonical_ordinary_track":
        contact_track = _contact(invalid)["track"]
        contact_track["track_id"] = "track-0001"
        fusion = invalid["intel_fusion"]
        fusion["tracks"]["blue"] = {
            "track-0001": copy.deepcopy(contact_track),
        }
        fusion["track_counter"] = 1
        fusion["fow_track_counters"].pop("blue")
    elif mutation == "missing_fow_counter":
        invalid["intel_fusion"]["fow_track_counters"].pop("blue")
    elif mutation == "ahead_fow_counter":
        invalid["intel_fusion"]["fow_track_counters"]["blue"] = 9
    else:
        second = copy.deepcopy(_fusion_track(invalid))
        second["track_id"] = "fow-track-0002"
        invalid["intel_fusion"]["tracks"]["blue"][
            "fow-track-0002"
        ] = second
        invalid["intel_fusion"]["fow_track_counters"]["blue"] = 2

    _assert_atomic_rejection(invalid, valid)


@pytest.mark.test_evidence("helper_assertion")
@pytest.mark.parametrize(
    "mutation",
    (
        "side_map_mismatch",
        "side_map_noncanonical",
        "side_mismatch",
        "side_wrong_type",
        "observer_empty",
        "observer_wrong_type",
        "target_whitespace",
        "target_wrong_type",
        "source_index_bool",
        "source_index_negative",
        "source_index_wrong_type",
        "sensor_empty",
        "sensor_wrong_type",
        "role_empty",
        "role_wrong_type",
        "detected_false",
        "detected_integer",
        "logical_time_bool",
        "logical_time_negative",
        "logical_time_wrong_type",
        "logical_time_view_mismatch",
        "probability_bool",
        "probability_nan",
        "probability_negative",
        "probability_above_one",
        "probability_wrong_type",
        "snr_bool",
        "snr_nan",
        "range_bool",
        "range_nan",
        "range_negative",
        "sensor_type_empty",
        "sensor_type_wrong_type",
        "bearing_bool",
        "bearing_nan",
        "bearing_negative",
        "bearing_360",
        "duplicate_identity",
        "noncanonical_order",
        "missing_contact",
        "missing_reporting_sensor",
    ),
)
def test_current_witness_corruption_rejects_atomically(mutation: str) -> None:
    valid = _valid_state()
    invalid = copy.deepcopy(valid)
    witness = _witness(invalid)
    if mutation == "side_map_mismatch":
        values = invalid["current_detection_witnesses"].pop("blue")
        invalid["current_detection_witnesses"]["red"] = values
    elif mutation == "side_map_noncanonical":
        values = invalid["current_detection_witnesses"].pop("blue")
        invalid["current_detection_witnesses"] = {
            "red": [],
            "blue": values,
        }
    elif mutation == "side_mismatch":
        witness["side"] = "red"
    elif mutation == "side_wrong_type":
        witness["side"] = 7
    elif mutation == "observer_empty":
        witness["observer_unit_id"] = ""
    elif mutation == "observer_wrong_type":
        witness["observer_unit_id"] = 7
    elif mutation == "target_whitespace":
        witness["target_id"] = " red-target"
    elif mutation == "target_wrong_type":
        witness["target_id"] = 7
    elif mutation == "source_index_bool":
        witness["source_equipment_index"] = True
    elif mutation == "source_index_negative":
        witness["source_equipment_index"] = -1
    elif mutation == "source_index_wrong_type":
        witness["source_equipment_index"] = "0"
    elif mutation == "sensor_empty":
        witness["sensor_id"] = ""
    elif mutation == "sensor_wrong_type":
        witness["sensor_id"] = 7
    elif mutation == "role_empty":
        witness["modeled_role"] = ""
    elif mutation == "role_wrong_type":
        witness["modeled_role"] = 7
    elif mutation == "detected_false":
        witness["detected"] = False
    elif mutation == "detected_integer":
        witness["detected"] = 1
    elif mutation == "logical_time_bool":
        witness["logical_time_s"] = True
    elif mutation == "logical_time_negative":
        witness["logical_time_s"] = -1.0
    elif mutation == "logical_time_wrong_type":
        witness["logical_time_s"] = "10.0"
    elif mutation == "logical_time_view_mismatch":
        witness["logical_time_s"] = 9.0
    elif mutation == "probability_bool":
        witness["probability"] = True
    elif mutation == "probability_nan":
        witness["probability"] = math.nan
    elif mutation == "probability_negative":
        witness["probability"] = -0.01
    elif mutation == "probability_above_one":
        witness["probability"] = 1.01
    elif mutation == "probability_wrong_type":
        witness["probability"] = "0.75"
    elif mutation == "snr_bool":
        witness["snr_db"] = True
    elif mutation == "snr_nan":
        witness["snr_db"] = math.nan
    elif mutation == "range_bool":
        witness["range_m"] = True
    elif mutation == "range_nan":
        witness["range_m"] = math.nan
    elif mutation == "range_negative":
        witness["range_m"] = -1.0
    elif mutation == "sensor_type_empty":
        witness["sensor_type"] = ""
    elif mutation == "sensor_type_wrong_type":
        witness["sensor_type"] = 7
    elif mutation == "bearing_bool":
        witness["bearing_deg"] = True
    elif mutation == "bearing_nan":
        witness["bearing_deg"] = math.nan
    elif mutation == "bearing_negative":
        witness["bearing_deg"] = -0.01
    elif mutation == "bearing_360":
        witness["bearing_deg"] = 360.0
    elif mutation == "duplicate_identity":
        invalid["current_detection_witnesses"]["blue"].append(
            copy.deepcopy(witness),
        )
    elif mutation == "noncanonical_order":
        earlier = copy.deepcopy(witness)
        earlier["observer_unit_id"] = "aaa-observer"
        invalid["current_detection_witnesses"]["blue"].append(earlier)
    elif mutation == "missing_contact":
        witness["target_id"] = "missing-red-target"
    else:
        witness["sensor_id"] = "unreported-eye"

    _assert_atomic_rejection(invalid, valid)


@pytest.mark.test_evidence("helper_assertion")
@pytest.mark.parametrize(
    "mutation",
    (
        "rng_not_mapping",
        "fusion_rng_not_mapping",
        "manager_fusion_mirror_disagreement",
    ),
)
def test_serialized_rng_corruption_rejects_atomically(mutation: str) -> None:
    valid = _valid_state()
    invalid = copy.deepcopy(valid)
    if mutation == "rng_not_mapping":
        invalid["rng_state"] = []
    elif mutation == "fusion_rng_not_mapping":
        invalid["intel_fusion"]["rng_state"] = []
    else:
        invalid["intel_fusion"]["rng_state"] = copy.deepcopy(
            np.random.default_rng(116_999).bit_generator.state,
        )

    _assert_atomic_rejection(invalid, valid)


@pytest.mark.test_evidence("helper_assertion")
def test_authoritative_rng_disagreement_rejects_atomically() -> None:
    valid = _valid_state()
    authoritative = copy.deepcopy(
        np.random.default_rng(116_998).bit_generator.state,
    )

    _assert_atomic_rejection(
        copy.deepcopy(valid),
        valid,
        authoritative_rng_state=authoritative,
    )


@pytest.mark.parametrize(
    "owner",
    (
        "fow",
        "detection",
        "fow_estimator",
        "fusion",
        "fusion_estimator",
        "deception",
        "identification",
    ),
)
def test_capture_and_standalone_restore_reject_detached_rng_owner(
    owner: str,
) -> None:
    valid_state = _valid_state()
    manager = _manager(116, with_identification=True)
    authoritative_rng = manager._rng
    detection_engine = manager._detection
    manager.validate_runtime_bindings(
        detection_engine=detection_engine,
        authoritative_rng=authoritative_rng,
    )
    detached_rng = np.random.default_rng(116_997)
    if owner == "fow":
        manager._rng = detached_rng
    elif owner == "detection":
        manager._detection._rng = detached_rng
    elif owner == "fow_estimator":
        manager._estimator._rng = detached_rng
    elif owner == "fusion":
        manager._intel_fusion._rng = detached_rng
    elif owner == "fusion_estimator":
        manager._intel_fusion._estimator._rng = detached_rng
    elif owner == "deception":
        manager._deception._rng = detached_rng
    else:
        manager._identification._rng = detached_rng

    world_before = copy.deepcopy(manager._world_views)
    fusion_before = copy.deepcopy(manager._intel_fusion.get_state())
    witnesses_before = manager.get_current_detection_witnesses()
    with pytest.raises(ValueError):
        manager.validate_runtime_bindings(
            detection_engine=detection_engine,
            authoritative_rng=authoritative_rng,
        )
    with pytest.raises(ValueError):
        manager.get_state()
    with pytest.raises(ValueError):
        manager.set_state(valid_state)

    assert manager._world_views == world_before
    assert manager._intel_fusion.get_state() == fusion_before
    assert manager.get_current_detection_witnesses() == witnesses_before


def test_restore_preflight_rejects_detached_target_rng_before_mutation() -> None:
    valid = _valid_state()
    target = _populated_manager(
        116_996,
        side="red",
        observer_id="red-observer",
        target_id="blue-stale-target",
        sensor_id="red-eye",
        current_time=3.0,
    )
    authoritative_rng = target._rng
    detection_engine = target._detection
    target._intel_fusion._estimator._rng = np.random.default_rng(116_995)
    world_before = {
        side: view.get_state()
        for side, view in target._world_views.items()
    }
    fusion_before = target._intel_fusion.get_state()
    witnesses_before = target.get_current_detection_witnesses()

    with pytest.raises(ValueError):
        target.validate_runtime_bindings(
            detection_engine=detection_engine,
            authoritative_rng=authoritative_rng,
        )

    assert {
        side: view.get_state()
        for side, view in target._world_views.items()
    } == world_before
    assert target._intel_fusion.get_state() == fusion_before
    assert target.get_current_detection_witnesses() == witnesses_before

    target._intel_fusion._estimator._rng = authoritative_rng
    target.validate_runtime_bindings(
        detection_engine=detection_engine,
        authoritative_rng=authoritative_rng,
    )
    target.set_state(valid)
    assert target.get_state() == valid


def test_two_key_legacy_empty_state_remains_bounded_and_supported() -> None:
    source = _manager(116)
    source.get_world_view("blue")
    current = source.get_state()
    legacy = {
        "world_views": copy.deepcopy(current["world_views"]),
        "rng_state": copy.deepcopy(current["rng_state"]),
    }
    target = _manager(116_001)

    target.set_state(legacy)

    restored = target.get_state()
    assert restored["world_views"] == legacy["world_views"]
    assert restored["current_detection_witnesses"] == {}
    assert restored["intel_fusion"]["tracks"] == {}
    assert restored["rng_state"] == legacy["rng_state"]


@pytest.mark.parametrize(
    "retained_topology",
    (
        "tracks",
        "empty_track_namespace",
        "track_counter",
        "fow_track_counters",
        "satellite_passes",
        "delivery_receipts",
        "imint_target_tracks",
    ),
)
def test_two_key_legacy_rejects_target_only_fusion_topology_atomically(
    retained_topology: str,
) -> None:
    source = _manager(116)
    source.get_world_view("blue")
    current = source.get_state()
    legacy = {
        "world_views": copy.deepcopy(current["world_views"]),
        "rng_state": copy.deepcopy(current["rng_state"]),
    }
    target = (
        _populated_manager(
            116_780,
            side="red",
            observer_id="red-observer",
            target_id="blue-stale-target",
            sensor_id="red-eye",
            current_time=3.0,
        )
        if retained_topology == "tracks"
        else _manager(116_780)
    )
    fusion = target._intel_fusion
    if retained_topology == "empty_track_namespace":
        fusion.get_tracks("red")
    elif retained_topology == "track_counter":
        fusion._track_counter = 1
    elif retained_topology == "fow_track_counters":
        fusion._fow_track_counters = {"blue": 1}
    elif retained_topology == "satellite_passes":
        fusion.add_satellite_pass(
            "blue",
            SatellitePass(
                satellite_id="sat-1",
                constellation_id="imint-1",
                side="blue",
                start_time=0.0,
                end_time=600.0,
                coverage_center_x=5_000.0,
                coverage_center_y=5_000.0,
                coverage_radius_m=50_000.0,
                resolution_m=1.0,
                revisit_interval_s=3_600.0,
            ),
        )
    elif retained_topology == "delivery_receipts":
        fusion._delivery_receipts.append(
            IntelDeliveryReceipt(
                report_id=1,
                reporting_side="blue",
                target_side="red",
                target_id="red-target",
                satellite_id="sat-1",
                constellation_id="imint-1",
                sensor_type="optical",
                resolution_m=1.0,
                position_sigma_m=1.0,
                observed_position=Position(1.0, 2.0, 0.0),
                observed_at_s=1.0,
                available_at_s=2.0,
                source=IntelSource.IMINT,
                resulting_track_id="track-0001",
                delivery_time_s=3.0,
                report_sha256="0" * 64,
            ),
        )
    elif retained_topology == "imint_target_tracks":
        fusion._imint_target_tracks = {
            "blue": {
                "red-target": IMINTTrackAssociation(
                    reporting_side="blue",
                    target_side="red",
                    target_id="red-target",
                    track_id="track-0001",
                    last_observed_at_s=1.0,
                    last_received_at_s=2.0,
                    last_report_id=1,
                ),
            },
        }

    world_before = {
        side: view.get_state()
        for side, view in target._world_views.items()
    }
    fusion_before = copy.deepcopy(fusion.get_state())
    witnesses_before = target.get_current_detection_witnesses()
    with pytest.raises(ValueError, match="pristine target fusion topology"):
        target.set_state(legacy)
    assert {
        side: view.get_state()
        for side, view in target._world_views.items()
    } == world_before
    assert fusion.get_state() == fusion_before
    assert target.get_current_detection_witnesses() == witnesses_before

    empty_fusion_state = _manager(116_781)._intel_fusion.get_state()
    fusion.set_state(empty_fusion_state)
    target.set_state(legacy)
    restored = target.get_state()
    assert restored["world_views"] == legacy["world_views"]
    assert restored["current_detection_witnesses"] == {}
    assert restored["intel_fusion"]["tracks"] == {}


def test_three_key_legacy_empty_state_requires_explicit_bounded_route() -> None:
    current = _manager(116).get_state()
    legacy = {
        "world_views": copy.deepcopy(current["world_views"]),
        "rng_state": copy.deepcopy(current["rng_state"]),
        "intel_fusion": copy.deepcopy(current["intel_fusion"]),
    }
    target = _manager(116_002)

    with pytest.raises(ValueError):
        target.stage_state(legacy)

    plan = target.stage_state(legacy, allow_legacy_state=True)
    target.commit_state(plan)
    restored = target.get_state()
    assert restored["world_views"] == {}
    assert restored["current_detection_witnesses"] == {}
    assert restored["intel_fusion"] == legacy["intel_fusion"]


def test_three_key_legacy_restores_fusion_only_history_as_incomplete() -> None:
    """The explicit legacy route preserves coherent fusion-only history."""
    current = _valid_state()
    legacy = {
        "world_views": copy.deepcopy(current["world_views"]),
        "rng_state": copy.deepcopy(current["rng_state"]),
        "intel_fusion": copy.deepcopy(current["intel_fusion"]),
    }
    legacy["world_views"]["blue"]["contacts"].clear()
    _fusion_track(legacy)["status"] = 4
    target = _populated_manager(
        116_004,
        side="red",
        observer_id="red-observer",
        target_id="blue-target",
        sensor_id="red-eye",
        current_time=3.0,
    )
    target.set_state(legacy)

    restored = target.get_state()
    assert restored["world_views"] == legacy["world_views"]
    assert restored["current_detection_witnesses"] == {}
    assert restored["intel_fusion"] == legacy["intel_fusion"]
    assert restored["scan_counts"] == {}
    assert restored["cadence"]["complete_from_tick_zero"] is False


def test_two_key_legacy_state_cannot_acquire_nonempty_contact_semantics() -> None:
    valid = _valid_state()
    legacy = {
        "world_views": copy.deepcopy(valid["world_views"]),
        "rng_state": copy.deepcopy(valid["rng_state"]),
    }
    target = _manager(116_003)
    before = target.get_state()

    with pytest.raises(ValueError):
        target.set_state(legacy)

    assert target.get_state() == before


def test_three_key_legacy_restores_coherent_contact_semantics_as_incomplete() -> None:
    valid = _valid_state()
    legacy = {
        "world_views": copy.deepcopy(valid["world_views"]),
        "rng_state": copy.deepcopy(valid["rng_state"]),
        "intel_fusion": copy.deepcopy(valid["intel_fusion"]),
    }
    target = _manager(116_003)

    target.set_state(legacy)

    restored = target.get_state()
    assert restored["world_views"] == legacy["world_views"]
    assert restored["current_detection_witnesses"] == {}
    assert restored["intel_fusion"] == legacy["intel_fusion"]
    assert restored["scan_counts"] == {}
    assert restored["cadence"]["complete_from_tick_zero"] is False
    contact = target.get_contact("blue", "red-target")
    assert contact is not None
    assert contact.track is target.intel_fusion.get_tracks("blue")[contact.track.track_id]


@pytest.mark.parametrize(
    "deception_state",
    ("active", "inactive", "counter_only"),
)
def test_capture_rejects_omitted_deception_state(
    deception_state: str,
) -> None:
    manager = _manager(116)
    decoy = manager.deploy_decoy(Position(10.0, 20.0, 0.0))
    if deception_state == "inactive":
        manager.update_decoys(1_000.0)
        assert decoy.active is False
    elif deception_state == "counter_only":
        manager._deception.remove_decoy(decoy.decoy_id)
        assert manager.get_active_decoys() == []

    with pytest.raises(ValueError):
        manager.get_state()


@pytest.mark.parametrize("cop_state", ("custom_config", "network_maps"))
def test_capture_rejects_omitted_cop_state(cop_state: str) -> None:
    if cop_state == "custom_config":
        manager = _manager(
            116,
            data_link_config=DataLinkConfig(enable_cop_sharing=True),
        )
    else:
        manager = _manager(116)
        manager.set_data_link_networks(
            {"link16": ["blue-observer", "blue-wingman"]},
        )

    with pytest.raises(ValueError):
        manager.get_state()


@pytest.mark.parametrize(
    "omitted_target_state",
    ("active_decoy", "counter_only", "custom_cop", "cop_networks"),
)
def test_restore_rejects_nonpristine_omitted_target_state_before_mutation(
    omitted_target_state: str,
) -> None:
    valid = _valid_state()
    if omitted_target_state == "custom_cop":
        target = _manager(
            116_994,
            data_link_config=DataLinkConfig(enable_cop_sharing=True),
        )
    else:
        target = _manager(116_994)
    if omitted_target_state in {"active_decoy", "counter_only"}:
        decoy = target.deploy_decoy(Position(10.0, 20.0, 0.0))
        if omitted_target_state == "counter_only":
            target._deception.remove_decoy(decoy.decoy_id)
    elif omitted_target_state == "cop_networks":
        target.set_data_link_networks({"link16": ["blue-observer"]})
    deception_before = copy.deepcopy(target._deception.get_state())
    config_before = target._dl_config.model_dump(mode="python")
    networks_before = copy.deepcopy(target._data_link_networks)
    memberships_before = copy.deepcopy(target._unit_networks)

    with pytest.raises(ValueError):
        target.set_state(valid)

    assert target._deception.get_state() == deception_before
    assert target._dl_config.model_dump(mode="python") == config_before
    assert target._data_link_networks == networks_before
    assert target._unit_networks == memberships_before
