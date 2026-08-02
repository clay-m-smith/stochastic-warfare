"""Phase 115 observer-local fog-of-war detection witness tests."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.detection.detection import (
    DetectionEngine,
    DetectionResult,
    DetectionScanIdentity,
)
from stochastic_warfare.detection.fog_of_war import FogOfWarManager
from stochastic_warfare.detection.identification import IdentificationEngine
from stochastic_warfare.detection.sensors import (
    SensorDefinition,
    SensorInstance,
    SensorLoader,
)
from stochastic_warfare.detection.signatures import (
    SignatureProfile,
    VisualSignature,
)
from stochastic_warfare.simulation.loadouts import SensorModeledRole
from stochastic_warfare.simulation.targeting_exposure import (
    PublicTrackExposure,
    SideFowTargetingExposure,
)


ROOT = Path(__file__).resolve().parents[2]
_HASHSEED_MARKER = "PHASE115_FOW_HASHSEED_RESULT="


@dataclass(frozen=True, slots=True)
class _Attachment:
    sensor: SensorInstance
    source_equipment_index: int
    modeled_role: SensorModeledRole

    @property
    def sensor_id(self) -> str:
        return self.sensor.sensor_id


def _sensor(sensor_id: str = "eye") -> SensorInstance:
    return SensorInstance(
        SensorDefinition(
            sensor_id=sensor_id,
            sensor_type="VISUAL",
            display_name=sensor_id,
            max_range_m=50_000.0,
            detection_threshold=-100.0,
        )
    )


def _signature() -> SignatureProfile:
    return SignatureProfile(
        profile_id="phase115-witness-target",
        unit_type="test",
        visual=VisualSignature(
            cross_section_m2=500.0,
            camouflage_factor=1.0,
        ),
    )


def _own(
    unit_id: str,
    attachment: _Attachment,
    *,
    x: float = 0.0,
    y: float = 0.0,
) -> dict[str, Any]:
    return {
        "unit_id": unit_id,
        "position": Position(x, y, 0.0),
        "sensors": (attachment.sensor,),
        "sensor_attachments": (attachment,),
        "observer_height": 2.5,
        "observer_heading_deg": 15.0,
    }


def _target(
    target_id: str,
    *,
    x: float = 100.0,
    y: float = 0.0,
    **overrides: Any,
) -> dict[str, Any]:
    target = {
        "unit_id": target_id,
        "position": Position(x, y, 0.0),
        "signature": _signature(),
        "unit": None,
        "target_height": 3.0,
        "concealment": 0.25,
        "posture": 2,
    }
    target.update(overrides)
    return target


def _manager(seed: int = 115) -> FogOfWarManager:
    return FogOfWarManager(rng=np.random.default_rng(seed))


def _successful_result(
    observer_pos: Position,
    target_pos: Position,
    sensor: SensorInstance,
    _target_signature: SignatureProfile,
    **_kwargs: Any,
) -> DetectionResult:
    dx = target_pos.easting - observer_pos.easting
    dy = target_pos.northing - observer_pos.northing
    return DetectionResult(
        True,
        0.75,
        8.5,
        math.hypot(dx, dy),
        sensor.sensor_type,
        math.degrees(math.atan2(dx, dy)) % 360.0,
    )


def test_success_witness_retains_observer_and_attachment_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager()
    attachment = _Attachment(
        sensor=_sensor("naval-director"),
        source_equipment_index=7,
        modeled_role=SensorModeledRole.NAVAL_VISUAL_DIRECTOR,
    )
    monkeypatch.setattr(
        manager._detection,
        "check_detection",
        _successful_result,
    )

    manager.update(
        "blue",
        [_own("observer-2", attachment)],
        [_target("target-9", x=300.0, y=400.0)],
        dt=5.0,
        current_time=125.0,
    )

    witnesses = manager.get_current_detection_witnesses("blue")
    assert len(witnesses) == 1
    witness = witnesses[0]
    assert witness.side == "blue"
    assert witness.observer_unit_id == "observer-2"
    assert witness.target_id == "target-9"
    assert witness.source_equipment_index == 7
    assert witness.sensor_id == "naval-director"
    assert witness.modeled_role == "naval_visual_director"
    assert witness.logical_time_s == 125.0
    assert witness.detected is True
    assert witness.probability == 0.75
    assert witness.snr_db == 8.5
    assert witness.range_m == 500.0
    assert witness.sensor_type == "VISUAL"
    assert witness.bearing_deg == pytest.approx(36.8698976458)


def test_side_local_rng_owns_detection_and_identification_draws(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parallel FOW classification cannot consume one shared RNG stream."""
    identification_rng = np.random.default_rng(91_500)
    manager = FogOfWarManager(
        identification_engine=IdentificationEngine(identification_rng),
        rng=np.random.default_rng(115),
    )
    attachment = _Attachment(
        sensor=_sensor("side-local-identification"),
        source_equipment_index=3,
        modeled_role=SensorModeledRole.VISUAL_OBSERVATION,
    )
    monkeypatch.setattr(
        manager._detection,
        "check_detection",
        _successful_result,
    )
    shared_before = copy.deepcopy(identification_rng.bit_generator.state)
    side_rng = np.random.default_rng(91_501)
    expected_side_rng = np.random.default_rng(91_501)
    expected_side_rng.random()

    manager.update(
        "blue",
        [_own("blue-observer", attachment)],
        [_target("red-target")],
        dt=5.0,
        current_time=25.0,
        rng=side_rng,
    )

    assert identification_rng.bit_generator.state == shared_before
    assert side_rng.bit_generator.state == expected_side_rng.bit_generator.state


def test_update_for_side_clears_previous_witnesses() -> None:
    manager = _manager()
    attachment = _Attachment(
        sensor=_sensor(),
        source_equipment_index=1,
        modeled_role=SensorModeledRole.VISUAL_OBSERVATION,
    )

    manager.update(
        "blue",
        [_own("observer", attachment)],
        [_target("target", x=1.0)],
        dt=1.0,
        current_time=1.0,
    )
    assert len(manager.get_current_detection_witnesses("blue")) == 1

    manager.update(
        "blue",
        [_own("observer", attachment)],
        [],
        dt=1.0,
        current_time=2.0,
    )
    assert manager.get_current_detection_witnesses("blue") == ()


def test_failed_update_cannot_leave_previous_witness_current(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager()
    attachment = _Attachment(
        sensor=_sensor(),
        source_equipment_index=1,
        modeled_role=SensorModeledRole.VISUAL_OBSERVATION,
    )
    manager.update(
        "blue",
        [_own("observer", attachment)],
        [_target("target", x=1.0)],
        dt=1.0,
        current_time=1.0,
    )
    assert manager.get_current_detection_witnesses("blue")

    def fail_detection(*_args: Any, **_kwargs: Any) -> DetectionResult:
        raise RuntimeError("canonical detection failed")

    monkeypatch.setattr(
        manager._detection,
        "check_detection",
        fail_detection,
    )
    with pytest.raises(RuntimeError, match="canonical detection failed"):
        manager.update(
            "blue",
            [_own("observer", attachment)],
            [_target("target", x=1.0)],
            dt=1.0,
            current_time=2.0,
        )
    assert manager.get_current_detection_witnesses("blue") == ()


def test_detection_environment_and_target_identity_are_forwarded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager()
    attachment = _Attachment(
        sensor=_sensor(),
        source_equipment_index=3,
        modeled_role=SensorModeledRole.GROUND_VISUAL_SIGHT,
    )
    captured: list[dict[str, Any]] = []

    def capture_check(
        _observer_pos: Position,
        _target_pos: Position,
        sensor: SensorInstance,
        _target_signature: SignatureProfile,
        **kwargs: Any,
    ) -> DetectionResult:
        captured.append(kwargs)
        return DetectionResult(
            False,
            0.0,
            -20.0,
            50.0,
            sensor.sensor_type,
            90.0,
        )

    monkeypatch.setattr(manager._detection, "check_detection", capture_check)
    manager.update(
        "blue",
        [_own("observer", attachment)],
        [
            _target(
                "target",
                illumination_lux=4.0,
                thermal_contrast=0.35,
                transmission_loss=27.0,
                jam_snr_penalty_db=6.0,
            )
        ],
        dt=1.0,
        current_time=10.0,
        visibility_m=2_750.0,
        illumination_lux=100.0,
        thermal_contrast=1.0,
        ambient_noise_db=83.0,
        atmospheric_atten_db_per_km=0.18,
        transmission_loss=None,
        jam_snr_penalty_db=0.0,
    )

    assert len(captured) == 1
    forwarded = captured[0]
    assert forwarded["target_unit"] is None
    assert forwarded["observer_height"] == 2.5
    assert forwarded["target_height"] == 3.0
    assert forwarded["concealment"] == 0.25
    assert forwarded["posture"] == 2
    assert forwarded["observer_heading_deg"] == 15.0
    assert forwarded["target_id"] == "target"
    assert forwarded["scan_identity"] == DetectionScanIdentity(
        side="blue",
        observer_unit_id="observer",
        source_equipment_index=3,
    )
    assert forwarded["visibility_m"] == 2_750.0
    assert forwarded["illumination_lux"] == 4.0
    assert forwarded["thermal_contrast"] == 0.35
    assert forwarded["ambient_noise_db"] == 83.0
    assert forwarded["atmospheric_atten_db_per_km"] == 0.18
    assert forwarded["transmission_loss"] == 27.0
    assert forwarded["jam_snr_penalty_db"] == 6.0


def test_witness_emission_consumes_no_second_detection_draw() -> None:
    manager = _manager()
    attachment = _Attachment(
        sensor=_sensor(),
        source_equipment_index=0,
        modeled_role=SensorModeledRole.VISUAL_OBSERVATION,
    )
    detection_rng = np.random.Generator(np.random.PCG64(99115))
    expected_rng = np.random.Generator(np.random.PCG64(99115))
    expected_rng.random()

    manager.update(
        "blue",
        [_own("observer", attachment)],
        [_target("target", x=1.0)],
        dt=1.0,
        current_time=3.0,
        detection_culling=False,
        rng=detection_rng,
    )

    assert len(manager.get_current_detection_witnesses("blue")) == 1
    assert detection_rng.bit_generator.state == expected_rng.bit_generator.state


def test_parallel_side_updates_publish_canonical_witness_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager()
    monkeypatch.setattr(
        manager._detection,
        "check_detection",
        _successful_result,
    )
    blue_attachment = _Attachment(
        sensor=_sensor("blue-eye"),
        source_equipment_index=9,
        modeled_role=SensorModeledRole.VISUAL_OBSERVATION,
    )
    red_attachment = _Attachment(
        sensor=_sensor("red-eye"),
        source_equipment_index=2,
        modeled_role=SensorModeledRole.VISUAL_OBSERVATION,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (
            executor.submit(
                manager.update,
                "red",
                [_own("red-observer", red_attachment)],
                [_target("blue-target")],
                1.0,
                7.0,
            ),
            executor.submit(
                manager.update,
                "blue",
                [_own("blue-observer", blue_attachment)],
                [_target("red-target")],
                1.0,
                7.0,
            ),
        )
        for future in futures:
            future.result()

    witnesses = manager.get_current_detection_witnesses()
    assert [(witness.side, witness.observer_unit_id, witness.target_id) for witness in witnesses] == [
        ("blue", "blue-observer", "red-target"),
        ("red", "red-observer", "blue-target"),
    ]


def test_witnesses_and_contacts_restore_exactly_with_fusion_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager()
    attachment = _Attachment(
        sensor=_sensor(),
        source_equipment_index=4,
        modeled_role=SensorModeledRole.VISUAL_OBSERVATION,
    )
    monkeypatch.setattr(
        manager._detection,
        "check_detection",
        _successful_result,
    )
    manager.update(
        "blue",
        [_own("observer", attachment)],
        [_target("target")],
        dt=1.0,
        current_time=12.0,
    )
    expected_witnesses = manager.get_current_detection_witnesses("blue")
    assert expected_witnesses
    source_contact = manager.get_contact("blue", "target")
    assert source_contact is not None
    source_track = source_contact.track

    state = manager.get_state()
    assert set(state) == {
        "world_views",
        "current_detection_witnesses",
        "rng_state",
        "intel_fusion",
    }
    assert state["current_detection_witnesses"]["blue"] == [
        witness.get_state() for witness in expected_witnesses
    ]

    manager.set_state(state)
    assert manager.get_state() == state
    assert manager.get_current_detection_witnesses("blue") == expected_witnesses
    in_place_contact = manager.get_contact("blue", "target")
    assert in_place_contact is not None
    assert in_place_contact.track is manager.intel_fusion.get_tracks("blue")[
        in_place_contact.track.track_id
    ]
    assert in_place_contact.track is not source_track

    restored = _manager(seed=800)
    restored.set_state(state)
    assert restored.get_state() == state
    assert restored.get_current_detection_witnesses("blue") == expected_witnesses
    fresh_contact = restored.get_contact("blue", "target")
    assert fresh_contact is not None
    assert fresh_contact.track is restored.intel_fusion.get_tracks("blue")[
        fresh_contact.track.track_id
    ]


def test_legacy_sensor_projection_detects_without_fabricating_witness() -> None:
    manager = _manager()
    manager.update(
        "blue",
        [
            {
                "position": Position(0.0, 0.0, 0.0),
                "sensors": (_sensor(),),
            }
        ],
        [_target("target", x=1.0)],
        dt=1.0,
        current_time=1.0,
    )
    assert manager.get_current_detection_witnesses("blue") == ()


def test_witness_metadata_requires_typed_role() -> None:
    manager = _manager()

    @dataclass(frozen=True, slots=True)
    class InvalidAttachment:
        sensor: SensorInstance
        source_equipment_index: int
        modeled_role: str

    sensor = _sensor()
    with pytest.raises(TypeError, match="modeled_role must be a typed enum"):
        manager.update(
            "blue",
            [
                {
                    "unit_id": "observer",
                    "position": Position(0.0, 0.0, 0.0),
                    "sensors": (sensor,),
                    "sensor_attachments": (InvalidAttachment(sensor, 0, "visual_observation"),),
                }
            ],
            [_target("target")],
            dt=1.0,
            current_time=1.0,
        )
    assert manager.get_current_detection_witnesses("blue") == ()


def test_integration_gain_is_observer_attachment_local_and_roundtrips() -> None:
    """Repeated dwell belongs to an exact mounted sensor, not its catalog ID."""
    engine = DetectionEngine(rng=np.random.default_rng(115))
    sensor = _sensor("shared-catalog-eye")
    signature = _signature()
    observer = Position(0.0, 0.0, 0.0)
    target = Position(0.0, 100.0, 0.0)
    identities = (
        DetectionScanIdentity("blue", "blue-observer", 2),
        DetectionScanIdentity("green", "green-observer", 2),
    )

    results = []
    for identity in identities:
        results.append(
            engine.check_detection(
                observer,
                target,
                sensor,
                signature,
                target_id="shared-target",
                scan_identity=identity,
            )
        )
    for identity in identities:
        results.append(
            engine.check_detection(
                observer,
                target,
                sensor,
                signature,
                target_id="shared-target",
                scan_identity=identity,
            )
        )

    assert results[0].snr_db == results[1].snr_db
    assert results[2].snr_db == results[3].snr_db
    assert results[2].snr_db > results[0].snr_db
    assert engine._scan_counts == {
        (
            identity.side,
            identity.observer_unit_id,
            identity.source_equipment_index,
            sensor.sensor_id,
            "shared-target",
        ): 2
        for identity in identities
    }

    state = engine.get_state()
    assert list(state["scan_counts"]) == sorted(state["scan_counts"])
    restored = DetectionEngine(rng=np.random.default_rng(999))
    restored.set_state(state)
    assert restored.get_state() == state
    assert restored._scan_counts == engine._scan_counts

    # The production checkpoint validator stages legacy owners on a deepcopy.
    staged = copy.deepcopy(engine)
    assert staged.get_state() == engine.get_state()
    control_result = engine.check_detection(
        observer,
        target,
        sensor,
        signature,
        target_id="shared-target",
        scan_identity=identities[0],
    )
    restored_result = restored.check_detection(
        observer,
        target,
        sensor,
        signature,
        target_id="shared-target",
        scan_identity=identities[0],
    )
    assert restored_result == control_result
    assert restored.get_state() == engine.get_state()


def test_legacy_detection_scan_state_remains_readable() -> None:
    """Previously emitted two-component scan-count state still restores."""
    engine = DetectionEngine(rng=np.random.default_rng(115))
    rng_state = engine.get_state()["rng_state"]
    engine.set_state(
        {
            "rng_state": rng_state,
            "scan_counts": {"legacy-eye:legacy-target": 3},
        }
    )

    assert engine._scan_counts == {("legacy-eye", "legacy-target"): 3}
    assert engine.get_state()["scan_counts"] == {
        "legacy-eye:legacy-target": 3,
    }


def _catalog_binoculars() -> SensorInstance:
    loader = SensorLoader(ROOT / "data" / "eras" / "ww1" / "sensors")
    definition = loader.load_definition(
        ROOT / "data" / "eras" / "ww1" / "sensors" / "binoculars_ww1.yaml",
    )
    return SensorInstance(definition)


def _three_side_fow_probe(
    *,
    parallel: bool,
    submission_order: tuple[str, ...],
) -> dict[str, Any]:
    manager = _manager(seed=91_115)
    sides = ("blue", "green", "red")
    side_rngs = {side: np.random.Generator(np.random.PCG64(115_000 + index)) for index, side in enumerate(sides)}
    inputs: dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]]]] = {}
    for side in sides:
        sensor = _catalog_binoculars()
        attachment = _Attachment(
            sensor=sensor,
            source_equipment_index=4,
            modeled_role=SensorModeledRole.VISUAL_OBSERVATION,
        )
        own = {
            "unit_id": f"{side}-observer",
            "position": Position(0.0, 0.0, 0.0),
            "sensors": (sensor,),
            "sensor_attachments": (attachment,),
            "observer_height": 1.8,
            "observer_heading_deg": 0.0,
        }
        inputs[side] = (
            [own],
            [
                _target(
                    "shared-target",
                    x=0.0,
                    y=100.0,
                    concealment=0.0,
                    posture=0,
                )
            ],
        )

    def update(side: str) -> None:
        own_units, enemy_units = inputs[side]
        manager.update(
            side,
            own_units,
            enemy_units,
            dt=5.0,
            current_time=25.0,
            detection_culling=False,
            rng=side_rngs[side],
            illumination_lux=100.0,
            visibility_m=10_000.0,
        )

    if parallel:
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(update, side) for side in submission_order]
            for future in futures:
                future.result()
    else:
        for side in submission_order:
            update(side)

    witnesses = manager.get_current_detection_witnesses()
    assert [witness.side for witness in witnesses] == list(sides)
    assert all(witness.sensor_id == "binoculars_ww1" for witness in witnesses)
    assert all(witness.source_equipment_index == 4 for witness in witnesses)
    assert all(witness.target_id == "shared-target" for witness in witnesses)

    detection_state = manager._detection.get_state()
    assert len(detection_state["scan_counts"]) == 3
    assert set(detection_state["scan_counts"].values()) == {1}
    fow_state = manager.get_state()
    assert fow_state["intel_fusion"]["track_counter"] == 0
    assert manager._rng.bit_generator.state == (np.random.default_rng(91_115).bit_generator.state)
    for index, side in enumerate(sides):
        expected_rng = np.random.Generator(
            np.random.PCG64(115_000 + index),
        )
        expected_rng.random()
        assert side_rngs[side].bit_generator.state == expected_rng.bit_generator.state
    return {
        "world_views": {side: manager.get_world_view(side).get_state() for side in sides},
        "witnesses": [asdict(witness) for witness in witnesses],
        "detection_state": detection_state,
        "fow_state": fow_state,
        "side_rng_states": {side: side_rngs[side].bit_generator.state for side in sides},
    }


def test_three_side_catalog_sensor_parallel_matches_sequential_exactly() -> None:
    """Thread scheduling cannot reassign dwell gain, witnesses, or track IDs."""
    canonical_order = ("blue", "green", "red")
    expected = _three_side_fow_probe(
        parallel=False,
        submission_order=canonical_order,
    )
    repeated = [
        _three_side_fow_probe(
            parallel=True,
            submission_order=order,
        )
        for order in (
            canonical_order,
            tuple(reversed(canonical_order)),
            ("green", "red", "blue"),
        )
    ]

    assert repeated == [expected, expected, expected]
    track_ids_by_side = {
        side: [contact_state["track"]["track_id"] for contact_state in world_view_state["contacts"].values()]
        for side, world_view_state in expected["world_views"].items()
    }
    assert track_ids_by_side == {
        "blue": ["fow-track-0001"],
        "green": ["fow-track-0001"],
        "red": ["fow-track-0001"],
    }
    assert expected["fow_state"]["intel_fusion"]["fow_track_counters"] == {
        "blue": 1,
        "green": 1,
        "red": 1,
    }

    restored = _manager(seed=1)
    restored.set_state(expected["fow_state"])
    restored_state = restored.get_state()
    assert restored_state == expected["fow_state"]
    assert restored_state["world_views"] == expected["world_views"]
    assert [
        asdict(witness)
        for witness in restored.get_current_detection_witnesses()
    ] == expected["witnesses"]
    for side in canonical_order:
        fusion_tracks = restored.intel_fusion.get_tracks(side)
        for contact in restored.get_world_view(side).contacts.values():
            assert contact.track is fusion_tracks[contact.track.track_id]


def _gated_motion_replacement_probe(
    *,
    parallel: bool,
    submission_order: tuple[str, ...],
) -> dict[str, Any]:
    """Exercise replacement through the production FogOfWarManager boundary."""
    manager = _manager(seed=115_109)
    manager._detection.check_detection = _successful_result
    attachments = {
        side: _Attachment(
            sensor=_sensor(f"{side}-moving-eye"),
            source_equipment_index=2,
            modeled_role=SensorModeledRole.VISUAL_OBSERVATION,
        )
        for side in ("blue", "red")
    }

    for step, target_x_m in enumerate((0.0, 100.0, 0.0, 100.0), start=1):

        def update(side: str) -> None:
            manager.update(
                side,
                [_own(f"{side}-observer", attachments[side])],
                [_target(f"{side}-moving-target", x=target_x_m)],
                dt=1.0,
                current_time=float(step),
                current_tick=step,
                detection_culling=False,
            )

        if parallel:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(update, side) for side in submission_order]
                for future in futures:
                    future.result()
        else:
            for side in submission_order:
                update(side)

        expected_track_id = f"fow-track-{step:04d}"
        for side in ("blue", "red"):
            contacts = manager.get_world_view(side).contacts
            tracks = manager._intel_fusion.get_tracks(side)
            assert tuple(contacts) == (f"{side}-moving-target",)
            assert tuple(tracks) == (expected_track_id,)
            assert contacts[f"{side}-moving-target"].track is tracks[expected_track_id]

    state = manager.get_state()
    assert state["intel_fusion"]["fow_track_counters"] == {
        "blue": 4,
        "red": 4,
    }
    return state


def test_gated_moving_contacts_are_bounded_and_parallel_deterministic() -> None:
    expected = _gated_motion_replacement_probe(
        parallel=False,
        submission_order=("blue", "red"),
    )
    assert (
        _gated_motion_replacement_probe(
            parallel=True,
            submission_order=("blue", "red"),
        )
        == expected
    )
    assert (
        _gated_motion_replacement_probe(
            parallel=True,
            submission_order=("red", "blue"),
        )
        == expected
    )


def test_failed_gated_replacement_retains_current_contact_atomically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(seed=115_110)
    monkeypatch.setattr(
        manager._detection,
        "check_detection",
        _successful_result,
    )
    attachment = _Attachment(
        sensor=_sensor("atomic-moving-eye"),
        source_equipment_index=2,
        modeled_role=SensorModeledRole.VISUAL_OBSERVATION,
    )
    manager.update(
        "blue",
        [_own("blue-observer", attachment)],
        [_target("moving-target", x=0.0)],
        dt=1.0,
        current_time=1.0,
        current_tick=1,
        detection_culling=False,
    )
    world_view = manager.get_world_view("blue")
    current_contact = world_view.contacts["moving-target"]
    current_track = current_contact.track
    fusion_before = manager._intel_fusion.get_state()

    def fail_track_creation(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("injected replacement failure")

    monkeypatch.setattr(
        manager._intel_fusion._estimator,
        "create_track",
        fail_track_creation,
    )
    with pytest.raises(RuntimeError, match="injected replacement failure"):
        manager.update(
            "blue",
            [_own("blue-observer", attachment)],
            [_target("moving-target", x=100.0)],
            dt=1.0,
            current_time=2.0,
            current_tick=2,
            detection_culling=False,
        )

    assert world_view.contacts["moving-target"] is current_contact
    assert current_contact.track is current_track
    assert current_track.track_id == "fow-track-0001"
    assert manager._intel_fusion.get_state() == fusion_before


@pytest.mark.parametrize(
    ("mutation", "error_match"),
    (
        ("missing_counter", "counter is missing"),
        ("counter_behind", "counter precedes an issued track"),
        ("noncanonical_id", "unsupported track ID"),
    ),
)
def test_fow_ordinal_track_restore_validation_rejects_corruption_atomically(
    mutation: str,
    error_match: str,
) -> None:
    state = _three_side_fow_probe(
        parallel=False,
        submission_order=("blue", "green", "red"),
    )["fow_state"]
    invalid = copy.deepcopy(state)
    fusion = invalid["intel_fusion"]
    if mutation == "missing_counter":
        del fusion["fow_track_counters"]["blue"]
    elif mutation == "counter_behind":
        track = fusion["tracks"]["blue"].pop("fow-track-0001")
        track["track_id"] = "fow-track-0002"
        fusion["tracks"]["blue"]["fow-track-0002"] = track
    else:
        track = fusion["tracks"]["blue"].pop("fow-track-0001")
        track["track_id"] = "fow-track-blue-target"
        fusion["tracks"]["blue"]["fow-track-blue-target"] = track

    target = _manager(seed=1_115)
    before = target.get_state()
    with pytest.raises(ValueError, match=error_match):
        target.set_state(invalid)
    assert target.get_state() == before


def test_fow_track_ordinals_are_side_local_and_continue_after_restore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(seed=115)
    monkeypatch.setattr(
        manager._detection,
        "check_detection",
        _successful_result,
    )
    attachment = _Attachment(
        sensor=_sensor("ordinal-eye"),
        source_equipment_index=3,
        modeled_role=SensorModeledRole.VISUAL_OBSERVATION,
    )
    manager.update(
        "blue",
        [_own("blue-observer", attachment)],
        [_target("classified-alpha"), _target("classified-bravo", x=200.0)],
        dt=1.0,
        current_time=1.0,
        current_tick=1,
        detection_culling=False,
    )
    manager.update(
        "red",
        [_own("red-observer", attachment)],
        [_target("classified-charlie")],
        dt=1.0,
        current_time=1.0,
        current_tick=1,
        detection_culling=False,
    )

    assert {
        target_id: contact.track.track_id for target_id, contact in manager.get_world_view("blue").contacts.items()
    } == {
        "classified-alpha": "fow-track-0001",
        "classified-bravo": "fow-track-0002",
    }
    assert manager.get_world_view("red").contacts["classified-charlie"].track.track_id == "fow-track-0001"

    restored = _manager(seed=999)
    restored.set_state(manager.get_state())
    monkeypatch.setattr(
        restored._detection,
        "check_detection",
        _successful_result,
    )
    restored.update(
        "blue",
        [_own("blue-observer", attachment)],
        [_target("classified-delta")],
        dt=1.0,
        current_time=2.0,
        current_tick=2,
        detection_culling=False,
    )
    assert restored.get_world_view("blue").contacts["classified-delta"].track.track_id == "fow-track-0003"
    assert restored.get_state()["intel_fusion"]["fow_track_counters"] == {
        "blue": 3,
        "red": 1,
    }


def test_first_public_track_id_is_independent_of_raw_target_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_target_ids = (
        "ground-truth-target-alpha-9137",
        "ground-truth-target-bravo-4286",
    )

    def capture(raw_target_id: str) -> tuple[str, str]:
        manager = _manager(seed=115)
        monkeypatch.setattr(
            manager._detection,
            "check_detection",
            _successful_result,
        )
        attachment = _Attachment(
            sensor=_sensor("public-ordinal-eye"),
            source_equipment_index=1,
            modeled_role=SensorModeledRole.VISUAL_OBSERVATION,
        )
        manager.update(
            "blue",
            [_own("blue-observer", attachment)],
            [_target(raw_target_id)],
            dt=1.0,
            current_time=1.0,
            current_tick=1,
            detection_culling=False,
        )
        public_track = PublicTrackExposure.from_contact(
            manager.get_world_view("blue").contacts[raw_target_id],
            reporting_side="blue",
        )
        payload = SideFowTargetingExposure(
            engine_tick=1,
            viewer_side="blue",
            tracks=(public_track,),
            decisions=(),
        ).to_wire()
        return public_track.track_id, json.dumps(payload, sort_keys=True)

    captures = tuple(capture(target_id) for target_id in raw_target_ids)
    assert [track_id for track_id, _payload in captures] == [
        "fow-track-0001",
        "fow-track-0001",
    ]
    for _track_id, payload in captures:
        assert all(raw_target_id not in payload for raw_target_id in raw_target_ids)


def _hashseed_probe_result() -> dict[str, str]:
    result = _three_side_fow_probe(
        parallel=True,
        submission_order=("red", "blue", "green"),
    )
    encoded = json.dumps(
        result,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {"phase115_fow_sha256": hashlib.sha256(encoded).hexdigest()}


def test_three_side_fow_output_is_independent_of_python_hash_seed() -> None:
    results: list[dict[str, str]] = []
    for hash_seed in ("1", "987654"):
        environment = os.environ.copy()
        environment["PYTHONHASHSEED"] = hash_seed
        environment["PHASE115_FOW_HASHSEED_PROBE"] = "1"
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve())],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            check=True,
            text=True,
        )
        result_line = next(line for line in completed.stdout.splitlines() if line.startswith(_HASHSEED_MARKER))
        results.append(json.loads(result_line.removeprefix(_HASHSEED_MARKER)))

    assert results[1] == results[0]


if (
    __name__ == "__main__"
    and os.environ.get(
        "PHASE115_FOW_HASHSEED_PROBE",
    )
    == "1"
):
    print(
        _HASHSEED_MARKER + json.dumps(_hashseed_probe_result(), sort_keys=True),
    )
