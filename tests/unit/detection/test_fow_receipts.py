"""Focused indexed FOW receipt and cadence integration tests for Phase 118."""

from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
import gc
import math
from types import SimpleNamespace
import weakref

import numpy as np
import pytest

import stochastic_warfare.detection.fog_of_war as fog_of_war_module
from stochastic_warfare.core.indexed_rng import (
    FOWDecisionIdentity,
    FOWIndexedSideHandle,
    FOWTargetKind,
    IndexedFOWRNG,
    encode_fow_decision,
)
from stochastic_warfare.core.performance_receipts import FogOfWarCycleReceipt
from stochastic_warfare.core.types import Domain, ModuleId, Position
from stochastic_warfare.detection.cadence import (
    TacticalAttachmentIdentity,
    TacticalCadenceAttachment,
    TacticalCadenceScheduler,
)
from stochastic_warfare.detection.deception import Decoy, DeceptionEngine, DeceptionType
from stochastic_warfare.detection.detection import (
    DetectionDecisionStage,
    DetectionEngine,
    DetectionResult,
    DetectionScanIdentity,
    PreparedDetection,
)
from stochastic_warfare.detection.estimation import StateEstimator
from stochastic_warfare.detection.fog_of_war import (
    FogOfWarCadenceBinding,
    FogOfWarCycleOutcome,
    FogOfWarLodTier,
    FogOfWarManager,
    FogOfWarNativePhaseBinding,
    FogOfWarPublicationPlan,
    FogOfWarSensorBinding,
    SideWorldView,
)
from stochastic_warfare.detection.identification import IdentificationEngine
from stochastic_warfare.detection.intel_fusion import (
    FusionSubmissionOutcome,
    IntelFusionEngine,
    _PreparedSensorFusionCandidate,
)
from stochastic_warfare.detection.sensors import (
    SensorDefinition,
    SensorInstance,
    SensorType,
)
from stochastic_warfare.detection.signatures import SignatureProfile, VisualSignature
from stochastic_warfare.entities.base import Unit
from stochastic_warfare.entities.equipment import EquipmentCategory, EquipmentItem
from stochastic_warfare.simulation.loadouts import SensorModeledRole


class _MutableScanCountText(str):
    def __new__(cls, value: str) -> _MutableScanCountText:
        instance = super().__new__(cls, value)
        instance.hash_salt = 0
        return instance

    def __hash__(self) -> int:
        return str.__hash__(self) ^ self.hash_salt


def _sensor(
    *,
    sensor_id: str = "phase118-eye",
    maximum_range_m: float = 1_000.0,
) -> SensorInstance:
    return SensorInstance(
        SensorDefinition(
            sensor_id=sensor_id,
            sensor_type="VISUAL",
            display_name="Phase 118 Eye",
            max_range_m=maximum_range_m,
            detection_threshold=0.0,
            scan_interval_ticks=2,
        )
    )


def _signature() -> SignatureProfile:
    return SignatureProfile(
        profile_id="phase118-target-signature",
        unit_type="phase118-target",
        visual=VisualSignature(
            cross_section_m2=1_000.0,
            camouflage_factor=1.0,
        ),
    )


def _manager(
    *,
    seed: int = 118_100,
    identification: bool,
    complete_from_tick_zero: bool = True,
) -> FogOfWarManager:
    rng = np.random.Generator(np.random.PCG64(seed))
    estimator = StateEstimator(rng=rng)
    return FogOfWarManager(
        detection_engine=DetectionEngine(rng=rng),
        identification_engine=IdentificationEngine(rng) if identification else None,
        state_estimator=estimator,
        intel_fusion=IntelFusionEngine(state_estimator=estimator, rng=rng),
        deception_engine=DeceptionEngine(rng=rng),
        rng=rng,
        cadence_scheduler=TacticalCadenceScheduler(
            complete_from_tick_zero=complete_from_tick_zero,
        ),
    )


def _attachment_record(
    sensor: SensorInstance,
    *,
    source_equipment_index: int = 7,
) -> SimpleNamespace:
    return SimpleNamespace(
        sensor=sensor,
        source_equipment_index=source_equipment_index,
        sensor_id=sensor.sensor_id,
        modeled_role=SensorModeledRole.VISUAL_OBSERVATION,
    )


def _own_unit(
    sensor: SensorInstance,
    *,
    unit_id: str = "blue-observer",
    position: Position = Position(0.0, 0.0, 0.0),
) -> dict[str, object]:
    attachment = _attachment_record(sensor)
    return {
        "unit_id": unit_id,
        "position": position,
        "sensors": [sensor],
        "sensor_attachments": [attachment],
        "observer_height": 1.8,
        "observer_heading_deg": 0.0,
    }


def _target(
    target_id: str = "red-target",
    *,
    position: Position = Position(0.0, 0.0, 0.0),
) -> dict[str, object]:
    return {
        "unit_id": target_id,
        "position": position,
        "signature": _signature(),
        "unit": None,
        "target_height": 0.0,
        "concealment": 0.0,
        "posture": 0,
    }


def _attachment_identity(
    sensor: SensorInstance,
    *,
    unit_id: str = "blue-observer",
    side: str = "blue",
    source_equipment_index: int = 7,
) -> TacticalAttachmentIdentity:
    return TacticalAttachmentIdentity(
        reporting_side=side,
        observer_unit_id=unit_id,
        source_equipment_index=source_equipment_index,
        sensor_id=sensor.sensor_id,
        modeled_role=SensorModeledRole.VISUAL_OBSERVATION.value,
    )


def _begin_cycle(
    manager: FogOfWarManager,
    sensor: SensorInstance,
    *,
    tick: int,
    native_period: int = 1,
    lod_period: int = 1,
    operational: bool = True,
) -> tuple[object, object, object, object, object, TacticalAttachmentIdentity]:
    transaction = manager.begin_update_transaction(("blue",))
    identity = _attachment_identity(sensor)
    cadence_plan = manager.cadence.stage_interval(
        [
            TacticalCadenceAttachment(
                identity=identity,
                native_period=native_period,
                lod_period=lod_period,
                operational=operational,
            )
        ]
    )
    indexed = IndexedFOWRNG(118_200)
    allocation = indexed.begin_interval(
        module=ModuleId.DETECTION,
        engine_tick=tick,
        reporting_sides=("blue",),
    )
    handle = allocation.acquire_side("blue")
    return transaction, cadence_plan, indexed, allocation, handle, identity


def _live_fow_authority_state(manager: FogOfWarManager) -> dict[str, object]:
    world_view = manager.peek_world_view("blue")
    return {
        "world_view": None if world_view is None else copy.deepcopy(world_view.get_state()),
        "witnesses": manager.get_current_detection_witnesses("blue"),
        "supports": manager.get_observer_track_supports("blue"),
        "scan_counts": manager._detection.snapshot_scan_counts(),
        "fusion": manager.intel_fusion.get_state(),
        "cadence": (
            manager.cadence.committed_ordinal,
            manager.cadence.attachment_states,
            manager.cadence.phase_assignments,
        ),
        "rng": copy.deepcopy(manager._rng.bit_generator.state),
    }


def _run_cycle(
    manager: FogOfWarManager,
    sensor: SensorInstance,
    *,
    tick: int,
    targets: list[dict[str, object]],
    native_period: int = 1,
    lod_period: int = 1,
    detection_culling: bool = False,
    soa_selection: bool = False,
    decoys: list[Decoy] | None = None,
    interval_seconds: float = 5.0,
    time_origin_seconds: float = 0.0,
    observer_position: Position = Position(0.0, 0.0, 0.0),
) -> tuple[FogOfWarCycleOutcome, object]:
    transaction, plan, indexed, allocation, handle, identity = _begin_cycle(
        manager,
        sensor,
        tick=tick,
        native_period=native_period,
        lod_period=lod_period,
    )
    side_plan = manager.update_with_receipt(
        "blue",
        [_own_unit(sensor, position=observer_position)],
        targets,
        interval_seconds,
        transaction=transaction,
        cadence_plan=plan,
        indexed_rng=handle,
        lod_tiers={identity.observer: FogOfWarLodTier.ACTIVE},
        current_time=time_origin_seconds + (tick + 1) * interval_seconds,
        current_tick=tick,
        detection_culling=detection_culling,
        soa_selection=soa_selection,
        decoys=decoys,
    )
    publication = manager.prevalidate_update_transaction(
        transaction,
        (side_plan,),
    )
    record = indexed.commit_interval(allocation)
    manager.cadence.commit_interval(plan)
    manager.commit_update_transaction(publication)
    assert indexed.committed_interval_count == 1
    return side_plan.outcome, record


def _run_two_sensor_cycle(
    manager: FogOfWarManager,
    first_sensor: SensorInstance,
    second_sensor: SensorInstance,
    *,
    tick: int,
    targets: list[dict[str, object]],
    first_native_period: int,
    first_lod_period: int,
    reverse_scan_order: bool = False,
) -> tuple[FogOfWarCycleOutcome, object]:
    transaction = manager.begin_update_transaction(("blue",))
    identities = (
        _attachment_identity(first_sensor, source_equipment_index=7),
        _attachment_identity(second_sensor, source_equipment_index=8),
    )
    cadence_plan = manager.cadence.stage_interval(
        (
            TacticalCadenceAttachment(
                identity=identities[0],
                native_period=first_native_period,
                lod_period=first_lod_period,
                operational=True,
            ),
            TacticalCadenceAttachment(
                identity=identities[1],
                native_period=1,
                lod_period=1,
                operational=True,
            ),
        ),
    )
    indexed = IndexedFOWRNG(118_201)
    allocation = indexed.begin_interval(
        module=ModuleId.DETECTION,
        engine_tick=tick,
        reporting_sides=("blue",),
    )
    sensors = [first_sensor, second_sensor]
    attachments = [
        _attachment_record(first_sensor, source_equipment_index=7),
        _attachment_record(second_sensor, source_equipment_index=8),
    ]
    if reverse_scan_order:
        sensors.reverse()
        attachments.reverse()
    own_unit = {
        "unit_id": "blue-observer",
        "position": Position(0.0, 0.0, 0.0),
        "sensors": sensors,
        "sensor_attachments": attachments,
        "observer_height": 1.8,
        "observer_heading_deg": 0.0,
    }
    side_plan = manager.update_with_receipt(
        "blue",
        [own_unit],
        targets,
        5.0,
        transaction=transaction,
        cadence_plan=cadence_plan,
        indexed_rng=allocation.acquire_side("blue"),
        lod_tiers={identities[0].observer: FogOfWarLodTier.ACTIVE},
        current_time=(tick + 1) * 5.0,
        current_tick=tick,
        detection_culling=False,
    )
    publication = manager.prevalidate_update_transaction(
        transaction,
        (side_plan,),
    )
    record = indexed.commit_interval(allocation)
    manager.cadence.commit_interval(cadence_plan)
    manager.commit_update_transaction(publication)
    assert indexed.committed_interval_count == 1
    return side_plan.outcome, record


def _run_vectorized_culling_matrix(
    manager: FogOfWarManager,
) -> dict[str, object]:
    sensors = (
        _sensor(sensor_id="phase142-vector-a", maximum_range_m=100.0),
        _sensor(sensor_id="phase142-vector-b", maximum_range_m=25.0),
        _sensor(sensor_id="phase142-vector-zero", maximum_range_m=0.0),
    )
    observer_specs = (
        ("blue-observer-a", Position(0.0, 0.0, 0.0), sensors[0]),
        ("blue-observer-b", Position(1_000.0, 0.0, 0.0), sensors[1]),
        ("blue-observer-zero", Position(-1_000.0, 0.0, 0.0), sensors[2]),
    )
    identities = tuple(_attachment_identity(sensor, unit_id=unit_id) for unit_id, _position, sensor in observer_specs)
    transaction = manager.begin_update_transaction(("blue",))
    cadence = manager.cadence.stage_interval(
        tuple(
            TacticalCadenceAttachment(
                identity=identity,
                native_period=1,
                lod_period=1,
                operational=True,
            )
            for identity in identities
        ),
    )
    indexed = IndexedFOWRNG(142_055)
    allocation = indexed.begin_interval(
        module=ModuleId.DETECTION,
        engine_tick=0,
        reporting_sides=("blue",),
    )
    side_plan = manager.update_with_receipt(
        "blue",
        [_own_unit(sensor, unit_id=unit_id, position=position) for unit_id, position, sensor in observer_specs],
        [
            _target("b-out", position=Position(math.nextafter(1_025.0, math.inf), 0.0, 0.0)),
            _target("a-corner", position=Position(100.0, 100.0, 0.0)),
            _target("same-b", position=Position(1_000.0, 0.0, 0.0)),
            _target("a-out", position=Position(math.nextafter(100.0, math.inf), 0.0, 0.0)),
            _target("a-edge", position=Position(100.0, 0.0, 0.0)),
            _target("same-a", position=Position(0.0, 0.0, 0.0)),
            _target("same-a-duplicate", position=Position(0.0, 0.0, 0.0)),
            _target("b-edge", position=Position(1_025.0, 0.0, 0.0)),
            _target("a-inside", position=Position(math.nextafter(100.0, 0.0), 0.0, 0.0)),
        ],
        5.0,
        transaction=transaction,
        cadence_plan=cadence,
        indexed_rng=allocation.acquire_side("blue"),
        lod_tiers={identity.observer: FogOfWarLodTier.ACTIVE for identity in identities},
        current_time=5.0,
        current_tick=0,
        detection_culling=True,
    )
    publication = manager.prevalidate_update_transaction(
        transaction,
        (side_plan,),
    )
    record = indexed.commit_interval(allocation)
    manager.cadence.commit_interval(cadence)
    manager.commit_update_transaction(publication)
    outcome = side_plan.outcome
    state = manager.get_state()
    checkpoint = manager.capture_checkpoint_snapshot().state
    assert checkpoint == state
    return {
        "world_view": outcome.world_view.get_state(),
        "receipt": outcome.receipt,
        "witnesses": tuple(witness.get_state() for witness in outcome.witnesses),
        "supports": tuple(support.get_state() for support in outcome.observer_track_supports),
        "indexed_record": record,
        "state": state,
        "checkpoint": checkpoint,
    }


def test_prepared_detection_exposes_pre_rng_stage_without_consuming_rng() -> None:
    rng = np.random.Generator(np.random.PCG64(118_300))
    engine = DetectionEngine(rng=rng)
    sensor = _sensor(maximum_range_m=10.0)
    before = copy.deepcopy(rng.bit_generator.state)

    result = engine.prepare_detection(
        Position(0.0, 0.0, 0.0),
        Position(11.0, 0.0, 0.0),
        sensor,
        _signature(),
    )

    assert isinstance(result, DetectionResult)
    assert result.detected is False
    assert result.decision_stage is DetectionDecisionStage.PRE_RNG_ABOVE_MAX_RANGE
    assert rng.bit_generator.state == before


def test_prepared_detection_adjudicates_one_explicit_uniform() -> None:
    engine = DetectionEngine(rng=np.random.Generator(np.random.PCG64(118_301)))
    prepared = engine.prepare_detection(
        Position(0.0, 0.0, 0.0),
        Position(0.0, 0.0, 0.0),
        _sensor(),
        _signature(),
    )
    assert isinstance(prepared, PreparedDetection)

    result = prepared.adjudicate(0.5)

    assert result.detected is True
    assert result.decision_stage is DetectionDecisionStage.STOCHASTIC
    with pytest.raises(ValueError, match=r"in \[0, 1\)"):
        prepared.adjudicate(1.0)


def test_identification_explicit_uniform_does_not_advance_legacy_rng() -> None:
    rng = np.random.Generator(np.random.PCG64(118_302))
    engine = IdentificationEngine(rng)
    detection = DetectionResult(
        True,
        1.0,
        100.0,
        0.0,
        _sensor().sensor_type,
        0.0,
    )
    before = copy.deepcopy(rng.bit_generator.state)

    engine.classify_from_detection(
        detection,
        threshold_db=0.0,
        classification_uniform=0.5,
    )

    assert rng.bit_generator.state == before
    with pytest.raises(ValueError, match="either rng"):
        engine.classify_from_detection(
            detection,
            rng=rng,
            classification_uniform=0.5,
        )


@pytest.mark.parametrize(
    ("identification", "expected_mask", "expected_identification_lanes"),
    [(False, 1, 0), (True, 3, 1)],
)
def test_receipt_reconciles_indexed_detection_and_conditional_identification(
    identification: bool,
    expected_mask: int,
    expected_identification_lanes: int,
) -> None:
    manager = _manager(identification=identification)
    sensor = _sensor()

    outcome, record = _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[_target()],
    )

    receipt = outcome.receipt
    assert receipt.observers == 1
    assert receipt.targets == 1
    assert receipt.sensors == 1
    assert receipt.target_opportunities == 1
    assert receipt.selection.brute_force_cycles == 1
    assert receipt.selection.brute_force_admitted_targets == 1
    assert receipt.cadence.attachment_cycles == 1
    assert receipt.cadence.operational_attachment_cycles == 1
    assert receipt.cadence.native_ready == 1
    assert receipt.cadence.lod_ready == 1
    assert receipt.cadence.admitted == 1
    assert receipt.scan.operational_sensor_target_opportunities == 1
    assert receipt.detection.api_calls == 1
    assert receipt.detection.stochastic_draws == 1
    assert receipt.detection.successes == 1
    assert receipt.detection.published_witnesses == 1
    assert receipt.fusion.position_measurement_candidates == 1
    assert receipt.fusion.position_measurement_groups == 1
    assert receipt.fusion.correlated_candidates_elided == 0
    assert receipt.fusion.creations == 1
    assert receipt.indexed_rng.blocks == 1
    assert receipt.indexed_rng.detection_lanes == 1
    assert receipt.indexed_rng.identification_lanes == (expected_identification_lanes)
    assert receipt.indexed_rng.transcript_entries == 1
    assert receipt.lod_detection.active_attachments_admitted == 1
    assert len(record.entries) == 1
    assert record.entries[0].consumed_lane_mask == expected_mask


def test_same_epoch_sensor_attachments_share_one_position_measurement_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(identification=True)
    first_sensor = _sensor(sensor_id="phase118-eye-a")
    second_sensor = _sensor(sensor_id="phase118-eye-b")

    def reject_public_batch_preparation(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("FOW accumulation called public batch preparation")

    monkeypatch.setattr(
        IntelFusionEngine,
        "_prepare_sensor_fusion_batch",
        reject_public_batch_preparation,
    )

    outcome, record = _run_two_sensor_cycle(
        manager,
        first_sensor,
        second_sensor,
        tick=0,
        targets=[_target()],
        first_native_period=1,
        first_lod_period=1,
    )

    contact = outcome.world_view.contacts["red-target"]
    assert len(record.entries) == 2
    assert len(outcome.witnesses) == 2
    assert contact.reporting_sensors == ["phase118-eye-a", "phase118-eye-b"]
    assert outcome.receipt.detection.successes == 2
    assert outcome.receipt.fusion.position_measurement_candidates == 2
    assert contact.track.hits == 1
    assert outcome.receipt.fusion.position_measurement_groups == 1
    assert outcome.receipt.fusion.correlated_candidates_elided == 1
    assert outcome.receipt.fusion.creations == 1
    assert outcome.receipt.fusion.updates == 0
    assert outcome.receipt.indexed_rng.identification_lanes == 2


def test_same_epoch_fusion_is_exact_under_attachment_scan_permutation() -> None:
    first_sensor = _sensor(sensor_id="phase118-eye-a")
    second_sensor = _sensor(sensor_id="phase118-eye-b")
    forward_manager = _manager(identification=True)
    reverse_manager = _manager(identification=True)

    forward = _run_two_sensor_cycle(
        forward_manager,
        first_sensor,
        second_sensor,
        tick=0,
        targets=[_target()],
        first_native_period=1,
        first_lod_period=1,
    )
    reverse = _run_two_sensor_cycle(
        reverse_manager,
        first_sensor,
        second_sensor,
        tick=0,
        targets=[_target()],
        first_native_period=1,
        first_lod_period=1,
        reverse_scan_order=True,
    )

    assert reverse[0].world_view.get_state() == forward[0].world_view.get_state()
    assert reverse[0].receipt == forward[0].receipt
    assert reverse[0].witnesses == forward[0].witnesses
    assert reverse[1] == forward[1]
    assert reverse_manager.get_state() == forward_manager.get_state()


def test_pre_rng_rejection_has_api_call_but_no_indexed_block() -> None:
    manager = _manager(identification=False)
    sensor = _sensor(maximum_range_m=10.0)

    outcome, record = _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[
            _target(position=Position(11.0, 0.0, 0.0)),
        ],
    )

    receipt = outcome.receipt
    assert receipt.detection.api_calls == 1
    assert receipt.detection.pre_rng_above_max_range_rejections == 1
    assert receipt.detection.stochastic_draws == 0
    assert receipt.indexed_rng.blocks == 0
    assert record.entries == ()


def test_fow_domain_rejection_precedes_above_range_exactly() -> None:
    manager = _manager(identification=False)
    sensor = SensorInstance(
        SensorDefinition(
            sensor_id="phase142-gate-order",
            sensor_type="VISUAL",
            display_name="Phase 142 gate order",
            max_range_m=99.0,
            detection_threshold=0.0,
            target_domains=[Domain.AERIAL.name],
        )
    )
    target_position = Position(100.0, 0.0, 0.0)
    target = _target(position=target_position)
    target["unit"] = Unit(
        entity_id="red-target",
        position=target_position,
        domain=Domain.GROUND,
    )

    outcome, record = _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[target],
    )

    assert outcome.receipt.detection.api_calls == 1
    assert outcome.receipt.detection.pre_rng_unsupported_domain_rejections == 1
    assert outcome.receipt.detection.pre_rng_above_max_range_rejections == 0
    assert outcome.receipt.detection.stochastic_draws == 0
    assert record.entries == ()


def test_fow_effective_range_equality_survives_but_next_float_rejects() -> None:
    manager = _manager(identification=False)
    sensor = _sensor(maximum_range_m=5.0)
    target_specs = (
        ("equal", Position(3.0, 4.0, 0.0)),
        ("above", Position(math.nextafter(5.0, math.inf), 0.0, 0.0)),
    )
    targets = []
    for target_id, position in target_specs:
        target = _target(target_id, position=position)
        target["unit"] = Unit(
            entity_id=target_id,
            position=position,
            domain=Domain.GROUND,
        )
        targets.append(target)

    outcome, record = _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=targets,
    )

    assert outcome.receipt.detection.api_calls == 2
    assert outcome.receipt.detection.pre_rng_above_max_range_rejections == 1
    assert outcome.receipt.detection.stochastic_draws == 1
    assert tuple(entry.decision_preimage for entry in record.entries) == tuple(
        encode_fow_decision(identity)
        for identity in (
            FOWDecisionIdentity(
                engine_tick=0,
                reporting_side="blue",
                observer_unit_id="blue-observer",
                source_equipment_index=7,
                sensor_id=sensor.sensor_id,
                modeled_role=SensorModeledRole.VISUAL_OBSERVATION.value,
                target_kind=FOWTargetKind.UNIT,
                target_id="equal",
            ),
        )
    )


@pytest.mark.parametrize(
    "drift",
    (
        "definition-domains",
        "definition-object",
        "equipment-condition",
        "supports-method",
        "target-domain",
    ),
)
def test_fow_detection_observes_live_input_drift(
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
) -> None:
    manager = _manager(identification=False)
    equipment = EquipmentItem(
        equipment_id="phase142-gate-equipment",
        name="Phase 142 gate equipment",
        category=EquipmentCategory.SENSOR,
        condition=0.5 if drift == "equipment-condition" else 1.0,
    )
    sensor = SensorInstance(
        SensorDefinition(
            sensor_id="phase142-live-gate",
            sensor_type="VISUAL",
            display_name="Phase 142 live gate",
            max_range_m=100.0 if drift == "equipment-condition" else 1_000.0,
            detection_threshold=0.0,
            target_domains=([Domain.AERIAL.name] if drift != "equipment-condition" else []),
        ),
        equipment,
    )
    target_position = Position(75.0, 0.0, 0.0) if drift == "equipment-condition" else Position(0.0, 0.0, 0.0)
    target_unit = Unit(
        entity_id="red-target",
        position=target_position,
        domain=Domain.GROUND,
    )
    targets = [
        _target("first", position=target_position),
        _target("second", position=target_position),
    ]
    if drift != "equipment-condition":
        for target in targets:
            target["unit"] = target_unit

    original_geometry = fog_of_war_module._detection_geometry
    geometry_calls = 0

    def mutate_before_second_gate(
        observer_position: Position,
        current_target_position: Position,
    ) -> object:
        nonlocal geometry_calls
        geometry_calls += 1
        if geometry_calls == 2:
            if drift == "definition-domains":
                sensor.definition.target_domains[:] = [Domain.GROUND.name]
            elif drift == "definition-object":
                sensor.definition = SensorDefinition(
                    sensor_id=sensor.sensor_id,
                    sensor_type="VISUAL",
                    display_name="Phase 142 replacement gate",
                    max_range_m=1_000.0,
                    detection_threshold=0.0,
                    target_domains=[Domain.GROUND.name],
                )
            elif drift == "equipment-condition":
                equipment.condition = 1.0
            elif drift == "supports-method":
                sensor.supports_target_domain = lambda _domain: True  # type: ignore[method-assign]
            else:
                target_unit.domain = Domain.AERIAL
        return original_geometry(observer_position, current_target_position)

    monkeypatch.setattr(
        fog_of_war_module,
        "_detection_geometry",
        mutate_before_second_gate,
    )

    outcome, record = _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=targets,
    )

    assert geometry_calls == 2
    assert outcome.receipt.detection.api_calls == 2
    assert outcome.receipt.detection.stochastic_draws == 1
    if drift == "equipment-condition":
        assert outcome.receipt.detection.pre_rng_above_max_range_rejections == 1
        assert outcome.receipt.detection.pre_rng_unsupported_domain_rejections == 0
    else:
        assert outcome.receipt.detection.pre_rng_unsupported_domain_rejections == 1
        assert outcome.receipt.detection.pre_rng_above_max_range_rejections == 0
    assert len(record.entries) == 1
    assert manager.capture_checkpoint_snapshot().state == manager.get_state()


@pytest.mark.parametrize(
    ("drift", "message"),
    (
        ("sensor-type", "has no production detection domain"),
        ("sensor-type-before-invalid-equipment", "has no production detection domain"),
        ("sensor-type-before-missing-definition", "has no production detection domain"),
        ("equipment-offline", "unreceipted stage"),
    ),
)
def test_fow_detection_live_drift_fails_atomically_in_gate_order(
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
    message: str,
) -> None:
    manager = _manager(identification=False)
    equipment = EquipmentItem(
        equipment_id="phase142-gate-failure",
        name="Phase 142 gate failure",
        category=EquipmentCategory.SENSOR,
    )
    sensor = SensorInstance(
        SensorDefinition(
            sensor_id="phase142-gate-failure",
            sensor_type="VISUAL",
            display_name="Phase 142 gate failure",
            max_range_m=1_000.0,
            detection_threshold=0.0,
            target_domains=[Domain.AERIAL.name],
        ),
        equipment,
    )
    target_position = Position(0.0, 0.0, 0.0)
    target_unit = Unit(
        entity_id="red-target",
        position=target_position,
        domain=Domain.GROUND,
    )
    targets = [
        _target("first", position=target_position),
        _target("second", position=target_position),
    ]
    for target in targets:
        target["unit"] = target_unit
    live_before = (
        manager.snapshot_side("blue"),
        copy.deepcopy(manager.intel_fusion.get_state()),
        manager.get_current_detection_witnesses(),
        manager.get_observer_track_supports(),
        copy.deepcopy(manager._rng.bit_generator.state),
    )
    transaction, cadence, indexed, allocation, handle, identity = _begin_cycle(
        manager,
        sensor,
        tick=0,
    )
    original_geometry = fog_of_war_module._detection_geometry
    geometry_calls = 0

    def mutate_before_second_gate(
        observer_position: Position,
        current_target_position: Position,
    ) -> object:
        nonlocal geometry_calls
        geometry_calls += 1
        if geometry_calls == 2:
            if drift.startswith("sensor-type"):
                sensor._sensor_type = SensorType.SEISMIC
                if drift == "sensor-type-before-invalid-equipment":
                    equipment.condition = "invalid"  # type: ignore[assignment]
                elif drift == "sensor-type-before-missing-definition":
                    del sensor.definition
            else:
                equipment.operational = False
        return original_geometry(observer_position, current_target_position)

    monkeypatch.setattr(
        fog_of_war_module,
        "_detection_geometry",
        mutate_before_second_gate,
    )

    with pytest.raises(ValueError, match=message):
        manager.update_with_receipt(
            "blue",
            [_own_unit(sensor)],
            targets,
            5.0,
            transaction=transaction,
            cadence_plan=cadence,
            indexed_rng=handle,
            lod_tiers={identity.observer: FogOfWarLodTier.ACTIVE},
            current_time=5.0,
            current_tick=0,
            detection_culling=False,
        )

    assert geometry_calls == 2
    assert manager._update_workspace is None
    assert (
        manager.snapshot_side("blue"),
        manager.intel_fusion.get_state(),
        manager.get_current_detection_witnesses(),
        manager.get_observer_track_supports(),
        manager._rng.bit_generator.state,
    ) == live_before
    assert indexed.committed_interval_count == 0
    assert indexed.committed_entry_count == 0
    indexed.abort_interval(allocation)
    manager.cadence.abort_interval(cadence)


def test_fow_detection_preserves_huge_equal_position_integer_semantics() -> None:
    coordinate = 10**1_000
    position = Position(coordinate, coordinate, coordinate)
    sensor = SensorInstance(
        SensorDefinition(
            sensor_id="phase142-huge-position",
            sensor_type="VISUAL",
            display_name="Phase 142 huge position",
            max_range_m=1_000.0,
            detection_threshold=0.0,
            target_domains=[Domain.AERIAL.name],
        )
    )
    target = _target(position=position)
    target["unit"] = Unit(
        entity_id="red-target",
        position=position,
        domain=Domain.GROUND,
    )

    outcome, record = _run_cycle(
        _manager(identification=False),
        sensor,
        tick=0,
        targets=[target],
        observer_position=position,
    )

    assert outcome.receipt.detection.api_calls == 1
    assert outcome.receipt.detection.pre_rng_unsupported_domain_rejections == 1
    assert outcome.receipt.detection.stochastic_draws == 0
    assert record.entries == ()


def test_fow_detection_preserves_huge_effective_range_semantics() -> None:
    definition = SensorDefinition(
        sensor_id="phase142-huge-range",
        sensor_type="VISUAL",
        display_name="Phase 142 huge range",
        max_range_m=1_000.0,
        detection_threshold=1_000_000.0,
        target_domains=[Domain.GROUND.name],
    )
    object.__setattr__(definition, "max_range_m", 10**1_000)
    sensor = SensorInstance(definition)
    target_position = Position(1.0, 0.0, 0.0)
    target = _target(position=target_position)
    target["unit"] = Unit(
        entity_id="red-target",
        position=target_position,
        domain=Domain.GROUND,
    )

    outcome, record = _run_cycle(
        _manager(identification=False),
        sensor,
        tick=0,
        targets=[target],
    )

    assert outcome.receipt.detection.api_calls == 1
    assert outcome.receipt.detection.pre_rng_above_max_range_rejections == 0
    assert outcome.receipt.detection.stochastic_draws == 1
    assert outcome.receipt.detection.successes == 0
    assert len(record.entries) == 1


def test_fow_detection_reads_custom_target_domain_once() -> None:
    class _ChangingDomainTarget(Unit):
        def __getattribute__(self, name: str) -> object:
            if name != "domain":
                return super().__getattribute__(name)
            accesses = object.__getattribute__(self, "accesses") + 1
            object.__setattr__(self, "accesses", accesses)
            return Domain.GROUND if accesses == 1 else Domain.AERIAL

    sensor = SensorInstance(
        SensorDefinition(
            sensor_id="phase142-one-domain-read",
            sensor_type="VISUAL",
            display_name="Phase 142 one domain read",
            max_range_m=1_000.0,
            detection_threshold=1_000_000.0,
            target_domains=[Domain.GROUND.name],
        )
    )
    target_position = Position(1.0, 0.0, 0.0)
    target_unit = _ChangingDomainTarget(
        entity_id="red-target",
        position=target_position,
        domain=Domain.GROUND,
    )
    target_unit.accesses = 0
    target = _target(position=target_position)
    target["unit"] = target_unit

    outcome, record = _run_cycle(
        _manager(identification=False),
        sensor,
        tick=0,
        targets=[target],
    )

    assert target_unit.accesses == 1
    assert outcome.receipt.detection.api_calls == 1
    assert outcome.receipt.detection.pre_rng_unsupported_domain_rejections == 0
    assert outcome.receipt.detection.stochastic_draws == 1
    assert outcome.receipt.detection.successes == 0
    assert len(record.entries) == 1


def test_culling_uses_conservative_closed_square_before_canonical_range_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(identification=False)
    sensor = _sensor(maximum_range_m=100.0)
    vectorized_box = fog_of_war_module.vectorized_box
    input_shapes: list[tuple[tuple[int, ...], ...]] = []

    def _record_vectorized_box(*bounds: np.ndarray) -> np.ndarray:
        input_shapes.append(tuple(np.asarray(bound).shape for bound in bounds))
        return vectorized_box(*bounds)

    monkeypatch.setattr(
        fog_of_war_module,
        "vectorized_box",
        _record_vectorized_box,
    )

    outcome, record = _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[
            _target(position=Position(100.0, 100.0, 0.0)),
        ],
        detection_culling=True,
    )

    receipt = outcome.receipt
    assert receipt.selection.strtree_builds == 1
    assert receipt.selection.strtree_queries == 1
    assert receipt.selection.strtree_admitted_targets == 1
    assert receipt.selection.strtree_pruned_targets == 0
    assert receipt.detection.api_calls == 1
    assert receipt.detection.pre_rng_above_max_range_rejections == 1
    assert record.entries == ()
    assert input_shapes == [((1,), (1,), (1,), (1,))]


def test_culling_prunes_target_outside_closed_square_without_api_call() -> None:
    manager = _manager(identification=False)
    sensor = _sensor(maximum_range_m=100.0)

    outcome, record = _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[
            _target(position=Position(101.0, 0.0, 0.0)),
        ],
        detection_culling=True,
    )

    receipt = outcome.receipt
    assert receipt.selection.strtree_admitted_targets == 0
    assert receipt.selection.strtree_pruned_targets == 1
    assert receipt.detection.api_calls == 0
    assert record.entries == ()


def test_vectorized_culling_matches_scalar_order_state_rng_and_receipts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    strtree = fog_of_war_module.STRtree
    target_tree_builder = fog_of_war_module._build_fow_target_tree

    def _scalar_target_tree(targets: list[dict[str, object]]) -> object:
        return strtree(
            [
                fog_of_war_module.Point(
                    target["position"].easting,  # type: ignore[union-attr]
                    target["position"].northing,  # type: ignore[union-attr]
                )
                for target in targets
            ]
        )

    scalar_manager = _manager(seed=142_055, identification=True)
    monkeypatch.setattr(
        fog_of_war_module,
        "_build_fow_target_tree",
        _scalar_target_tree,
    )
    monkeypatch.setattr(
        scalar_manager,
        "_vectorized_strtree_candidate_indices",
        lambda _tree, _observers: None,
    )
    scalar = _run_vectorized_culling_matrix(scalar_manager)

    monkeypatch.setattr(
        fog_of_war_module,
        "_build_fow_target_tree",
        target_tree_builder,
    )
    vectorized_box = fog_of_war_module.vectorized_box
    vectorized_points = fog_of_war_module.vectorized_points
    box_bounds: list[tuple[np.ndarray, ...]] = []
    point_coordinates: list[tuple[np.ndarray, np.ndarray]] = []
    query_shapes: list[tuple[int, ...]] = []

    def _record_vectorized_box(*bounds: np.ndarray) -> np.ndarray:
        box_bounds.append(tuple(np.asarray(bound).copy() for bound in bounds))
        return vectorized_box(*bounds)

    def _record_vectorized_points(
        eastings: np.ndarray,
        northings: np.ndarray,
    ) -> np.ndarray:
        point_coordinates.append(
            (
                np.asarray(eastings).copy(),
                np.asarray(northings).copy(),
            )
        )
        return vectorized_points(eastings, northings)

    class _ReversePairSTRtree:
        def __init__(self, geometries: object) -> None:
            self._tree = strtree(geometries)

        def query(self, geometries: object) -> np.ndarray:
            query_shapes.append(np.asarray(geometries).shape)
            pairs = self._tree.query(geometries)
            assert pairs.ndim == 2
            return pairs[:, ::-1]

    monkeypatch.setattr(fog_of_war_module, "vectorized_box", _record_vectorized_box)
    monkeypatch.setattr(
        fog_of_war_module,
        "vectorized_points",
        _record_vectorized_points,
    )
    monkeypatch.setattr(fog_of_war_module, "STRtree", _ReversePairSTRtree)
    vectorized = _run_vectorized_culling_matrix(
        _manager(seed=142_055, identification=True),
    )

    assert vectorized == scalar
    assert len(point_coordinates) == 1
    assert tuple(coordinate.tolist() for coordinate in point_coordinates[0]) == (
        [
            math.nextafter(1_025.0, math.inf),
            100.0,
            1_000.0,
            math.nextafter(100.0, math.inf),
            100.0,
            0.0,
            0.0,
            1_025.0,
            math.nextafter(100.0, 0.0),
        ],
        [0.0, 100.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )
    assert query_shapes == [(2,)]
    assert len(box_bounds) == 1
    assert tuple(bound.tolist() for bound in box_bounds[0]) == (
        [-100.0, 975.0],
        [-100.0, -25.0],
        [100.0, 1_025.0],
        [100.0, 25.0],
    )
    receipt = vectorized["receipt"]
    assert isinstance(receipt, FogOfWarCycleReceipt)
    assert receipt.selection.strtree_builds == 1
    assert receipt.selection.strtree_queries == 3
    assert receipt.selection.strtree_admitted_targets == 7
    assert receipt.selection.strtree_pruned_targets == 20
    assert receipt.selection.selector_cycles == receipt.observers
    assert receipt.selection.admitted_targets + receipt.selection.pruned_targets == (receipt.target_opportunities)


def test_vectorized_culling_zero_range_and_empty_observers_do_not_build_boxes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _reject_vectorized_box(*_bounds: object) -> object:
        raise AssertionError("zero-range or empty observer selection built a box")

    monkeypatch.setattr(
        fog_of_war_module,
        "vectorized_box",
        _reject_vectorized_box,
    )
    zero_outcome, zero_record = _run_cycle(
        _manager(identification=False),
        _sensor(maximum_range_m=0.0),
        tick=0,
        targets=[_target()],
        detection_culling=True,
    )
    assert zero_outcome.receipt.selection.strtree_queries == 1
    assert zero_outcome.receipt.selection.strtree_admitted_targets == 0
    assert zero_outcome.receipt.selection.strtree_pruned_targets == 1
    assert zero_outcome.receipt.detection.api_calls == 0
    assert zero_record.entries == ()

    manager = _manager(identification=False)
    transaction = manager.begin_update_transaction(("blue",))
    cadence = manager.cadence.stage_interval(())
    indexed = IndexedFOWRNG(142_056)
    allocation = indexed.begin_interval(
        module=ModuleId.DETECTION,
        engine_tick=0,
        reporting_sides=("blue",),
    )
    plan = manager.update_with_receipt(
        "blue",
        [],
        [_target()],
        5.0,
        transaction=transaction,
        cadence_plan=cadence,
        indexed_rng=allocation.acquire_side("blue"),
        lod_tiers={},
        current_time=5.0,
        current_tick=0,
        detection_culling=True,
    )
    publication = manager.prevalidate_update_transaction(transaction, (plan,))
    record = indexed.commit_interval(allocation)
    manager.cadence.commit_interval(cadence)
    manager.commit_update_transaction(publication)
    receipt = plan.receipt
    assert receipt.observers == 0
    assert receipt.target_opportunities == 0
    assert receipt.selection.strtree_queries == 0
    assert receipt.selection.admitted_targets == 0
    assert receipt.selection.pruned_targets == 0
    assert record.entries == ()


def test_vectorized_target_points_use_scalar_fallback_for_every_anomaly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _CoordinateSubclass(float):
        pass

    scalar_point = fog_of_war_module.Point
    point_inputs: list[tuple[object, object]] = []

    def reject_vectorized_points(*_coordinates: object) -> object:
        raise AssertionError("nonordinary target used vectorized Point construction")

    def record_scalar_point(easting: object, northing: object) -> object:
        point_inputs.append((easting, northing))
        return scalar_point(easting, northing)

    monkeypatch.setattr(
        fog_of_war_module,
        "vectorized_points",
        reject_vectorized_points,
    )
    monkeypatch.setattr(fog_of_war_module, "Point", record_scalar_point)

    for position in (
        Position(_CoordinateSubclass(1.0), 0.0, 0.0),
        Position(float("nan"), 0.0, 0.0),
    ):
        point_inputs.clear()
        tree = fog_of_war_module._build_fow_target_tree(
            [{"position": position}],
        )
        assert len(tree.geometries) == 1
        assert len(point_inputs) == 1
        assert point_inputs[0][0] is position.easting
        assert point_inputs[0][1] is position.northing

    huge_position = Position(10**1_000, 0.0, 0.0)
    point_inputs.clear()
    with pytest.raises(OverflowError, match="too large to convert"):
        fog_of_war_module._build_fow_target_tree(
            [{"position": huge_position}],
        )
    assert len(point_inputs) == 1
    assert point_inputs[0][0] is huge_position.easting
    assert point_inputs[0][1] is huge_position.northing


def test_vectorized_culling_malformed_fallback_preserves_issue_order_and_atomicity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issued: list[FOWDecisionIdentity] = []
    issue = FOWIndexedSideHandle.issue

    def _record_issue(
        handle: FOWIndexedSideHandle,
        identity: FOWDecisionIdentity,
    ) -> object:
        issued.append(identity)
        return issue(handle, identity)

    monkeypatch.setattr(FOWIndexedSideHandle, "issue", _record_issue)

    def _attempt(*, force_scalar: bool) -> tuple[str, tuple[FOWDecisionIdentity, ...]]:
        manager = _manager(seed=142_057, identification=False)
        sensor = _sensor(maximum_range_m=100.0)
        identities = (
            _attachment_identity(sensor, unit_id="blue-valid"),
            _attachment_identity(sensor, unit_id="blue-malformed"),
        )
        before = (
            manager.snapshot_side("blue"),
            manager.intel_fusion.get_state(),
            manager.get_current_detection_witnesses(),
            copy.deepcopy(manager._rng.bit_generator.state),
        )
        transaction = manager.begin_update_transaction(("blue",))
        cadence = manager.cadence.stage_interval(
            tuple(
                TacticalCadenceAttachment(
                    identity=identity,
                    native_period=1,
                    lod_period=1,
                    operational=True,
                )
                for identity in identities
            ),
        )
        indexed = IndexedFOWRNG(142_057)
        allocation = indexed.begin_interval(
            module=ModuleId.DETECTION,
            engine_tick=0,
            reporting_sides=("blue",),
        )
        if force_scalar:
            monkeypatch.setattr(
                manager,
                "_vectorized_strtree_candidate_indices",
                lambda _tree, _observers: None,
            )
        start = len(issued)
        with pytest.raises(TypeError) as caught:
            manager.update_with_receipt(
                "blue",
                [
                    _own_unit(sensor, unit_id="blue-valid"),
                    _own_unit(
                        sensor,
                        unit_id="blue-malformed",
                        position=Position("invalid", 0.0, 0.0),
                    ),
                ],
                [_target()],
                5.0,
                transaction=transaction,
                cadence_plan=cadence,
                indexed_rng=allocation.acquire_side("blue"),
                lod_tiers={identity.observer: FogOfWarLodTier.ACTIVE for identity in identities},
                current_time=5.0,
                current_tick=0,
                detection_culling=True,
            )
        assert manager._update_workspace is None
        assert (
            manager.snapshot_side("blue"),
            manager.intel_fusion.get_state(),
            manager.get_current_detection_witnesses(),
            manager._rng.bit_generator.state,
        ) == before
        assert indexed.committed_interval_count == 0
        assert indexed.committed_entry_count == 0
        indexed.abort_interval(allocation)
        manager.cadence.abort_interval(cadence)
        return str(caught.value), tuple(issued[start:])

    scalar_error, scalar_issued = _attempt(force_scalar=True)

    def _reject_vectorized_box(*_bounds: object) -> object:
        raise AssertionError("malformed inputs reached the vectorized geometry path")

    monkeypatch.setattr(
        fog_of_war_module,
        "vectorized_box",
        _reject_vectorized_box,
    )
    vector_error, vector_issued = _attempt(force_scalar=False)

    assert vector_error == scalar_error
    assert vector_issued == scalar_issued
    assert tuple(identity.observer_unit_id for identity in vector_issued) == ("blue-valid",)


def test_deferred_attachment_is_a_scheduled_skip_not_a_target_opportunity() -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    first, _record = _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[_target()],
        native_period=2,
    )
    assert first.receipt.cadence.admitted == 1

    second, record = _run_cycle(
        manager,
        sensor,
        tick=1,
        targets=[_target()],
        native_period=2,
    )

    receipt = second.receipt
    assert receipt.target_opportunities == 1
    assert receipt.cadence.deferred_native == 1
    assert receipt.scan.scheduled_attachment_skips == 1
    assert receipt.scan.operational_sensor_target_opportunities == 0
    assert receipt.detection.api_calls == 0
    assert record.entries == ()


def test_deferred_attachment_never_evaluates_malformed_target_geometry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[],
        native_period=2,
    )

    def reject_geometry(*_args: object) -> object:
        raise AssertionError("deferred target geometry was evaluated")

    monkeypatch.setattr(
        fog_of_war_module,
        "_detection_geometry",
        reject_geometry,
    )
    deferred, record = _run_cycle(
        manager,
        sensor,
        tick=1,
        targets=[_target(position=Position("malformed", 0.0, 0.0))],
        native_period=2,
    )

    assert deferred.receipt.cadence.deferred_native == 1
    assert deferred.receipt.detection.api_calls == 0
    assert deferred.receipt.scan.operational_sensor_target_opportunities == 0
    assert record.entries == ()


def test_native_recovery_receipt_requires_same_admission_indexed_work() -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[_target()],
        native_period=2,
        lod_period=1,
    )
    deferred, _record = _run_cycle(
        manager,
        sensor,
        tick=1,
        targets=[_target()],
        native_period=2,
        lod_period=1,
    )
    assert deferred.receipt.cadence.deferred_native == 1

    recovered, record = _run_cycle(
        manager,
        sensor,
        tick=2,
        targets=[_target(), _target("red-target-2")],
        native_period=2,
        lod_period=1,
    )

    assert len(record.entries) == 2
    assert recovered.receipt.indexed_rng.blocks == 2
    assert recovered.receipt.cadence.lod_recoveries_by_period == ()
    assert len(recovered.receipt.cadence.native_recoveries_by_period) == 1
    bucket = recovered.receipt.cadence.native_recoveries_by_period[0]
    assert bucket.deferral_period == 2
    assert bucket.recovery_admissions == 1
    assert bucket.recovery_admissions_with_indexed_work == 1
    assert bucket.indexed_detection_blocks == 2


def test_execute_reuses_plan_identity_and_one_scan_identity_per_attachment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sensor = _sensor()
    targets = [_target(), _target("red-target-2")]
    control = _manager(identification=False)
    observed = _manager(identification=False)
    for manager in (control, observed):
        _run_cycle(
            manager,
            sensor,
            tick=0,
            targets=[_target()],
            native_period=2,
            lod_period=1,
        )
        deferred, deferred_record = _run_cycle(
            manager,
            sensor,
            tick=1,
            targets=[_target()],
            native_period=2,
            lod_period=1,
        )
        assert deferred.receipt.cadence.deferred_native == 1
        assert deferred_record.entries == ()

    control_outcome, control_record = _run_cycle(
        control,
        sensor,
        tick=2,
        targets=targets,
        native_period=2,
        lod_period=1,
    )
    transaction, cadence, indexed, allocation, handle, identity = _begin_cycle(
        observed,
        sensor,
        tick=2,
        native_period=2,
        lod_period=1,
    )
    assert len(cadence.decisions) == 1
    cadence_decision = cadence.decisions[0]
    assert cadence_decision.identity == identity
    assert cadence_decision.identity is not identity
    assert cadence_decision.recoveries

    original_scan_identity = fog_of_war_module.DetectionScanIdentity
    original_bound_scan = fog_of_war_module._BoundObserverSensorScan
    original_prepare_detection = DetectionEngine._prepare_fow_detection
    original_issue = FOWIndexedSideHandle.issue
    constructed_scan_identities: list[DetectionScanIdentity] = []
    bound_scans: list[fog_of_war_module._BoundObserverSensorScan] = []
    prepared_scan_identities: list[DetectionScanIdentity] = []
    prepared_geometries: list[object] = []
    issued_decision_identities: list[FOWDecisionIdentity] = []

    def reject_tactical_attachment_identity(
        *_args: object,
        **_kwargs: object,
    ) -> None:
        raise AssertionError("fog execution reconstructed an attachment identity")

    def observed_scan_identity(
        *args: object,
        **kwargs: object,
    ) -> DetectionScanIdentity:
        scan_identity = original_scan_identity(*args, **kwargs)
        constructed_scan_identities.append(scan_identity)
        return scan_identity

    def observed_bound_scan(
        *args: object,
        **kwargs: object,
    ) -> fog_of_war_module._BoundObserverSensorScan:
        bound_scan = original_bound_scan(*args, **kwargs)
        bound_scans.append(bound_scan)
        return bound_scan

    def observed_prepare_detection(
        engine: DetectionEngine,
        *args: object,
        **kwargs: object,
    ) -> DetectionDecisionStage | PreparedDetection:
        scan_identity = kwargs.get("scan_identity")
        assert type(scan_identity) is DetectionScanIdentity
        prepared_scan_identities.append(scan_identity)
        prepared_geometries.append(kwargs.get("geometry"))
        return original_prepare_detection(engine, *args, **kwargs)

    def reject_public_prepare(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("FOW execution called the public detection wrapper")

    def observed_issue(
        indexed_handle: FOWIndexedSideHandle,
        decision_identity: FOWDecisionIdentity,
    ) -> object:
        issued_decision_identities.append(decision_identity)
        return original_issue(indexed_handle, decision_identity)

    monkeypatch.setattr(
        fog_of_war_module,
        "TacticalAttachmentIdentity",
        reject_tactical_attachment_identity,
    )
    monkeypatch.setattr(
        fog_of_war_module,
        "DetectionScanIdentity",
        observed_scan_identity,
    )
    monkeypatch.setattr(
        fog_of_war_module,
        "_BoundObserverSensorScan",
        observed_bound_scan,
    )
    monkeypatch.setattr(
        DetectionEngine,
        "_prepare_fow_detection",
        observed_prepare_detection,
    )
    monkeypatch.setattr(
        DetectionEngine,
        "prepare_detection",
        reject_public_prepare,
    )
    monkeypatch.setattr(
        FOWIndexedSideHandle,
        "issue",
        observed_issue,
    )

    side_plan = observed.update_with_receipt(
        "blue",
        [_own_unit(sensor)],
        targets,
        5.0,
        transaction=transaction,
        cadence_plan=cadence,
        indexed_rng=handle,
        lod_tiers={identity.observer: FogOfWarLodTier.ACTIVE},
        current_time=15.0,
        current_tick=2,
        detection_culling=False,
    )
    publication = observed.prevalidate_update_transaction(
        transaction,
        (side_plan,),
    )
    record = indexed.commit_interval(allocation)
    observed.cadence.commit_interval(cadence)
    observed.commit_update_transaction(publication)
    outcome = side_plan.outcome

    assert len(bound_scans) == 1
    assert bound_scans[0].identity is cadence_decision.identity
    assert bound_scans[0].cadence_decision is cadence_decision
    assert len(constructed_scan_identities) == 1
    assert bound_scans[0].scan_identity is constructed_scan_identities[0]
    assert len(prepared_scan_identities) == 2
    assert all(scan_identity is constructed_scan_identities[0] for scan_identity in prepared_scan_identities)
    assert len(prepared_geometries) == 2
    assert all(type(geometry) is fog_of_war_module._DetectionGeometry for geometry in prepared_geometries)
    assert prepared_geometries[0] == prepared_geometries[1]
    assert prepared_geometries[0] is not prepared_geometries[1]
    assert len(issued_decision_identities) == 2
    for decision_identity in issued_decision_identities:
        assert (
            decision_identity.reporting_side,
            decision_identity.observer_unit_id,
            decision_identity.source_equipment_index,
            decision_identity.sensor_id,
            decision_identity.modeled_role,
        ) == (
            identity.reporting_side,
            identity.observer_unit_id,
            identity.source_equipment_index,
            identity.sensor_id,
            identity.modeled_role,
        )
    recovery = outcome.receipt.cadence.native_recoveries_by_period
    assert len(recovery) == 1
    assert recovery[0].recovery_admissions_with_indexed_work == 1
    assert recovery[0].indexed_detection_blocks == 2
    assert outcome.world_view.get_state() == control_outcome.world_view.get_state()
    assert outcome.receipt == control_outcome.receipt
    assert outcome.witnesses == control_outcome.witnesses
    assert record == control_record
    assert observed.get_state() == control.get_state()


def test_fow_reuses_one_geometry_for_all_admitted_target_attachments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_prepare = DetectionEngine._prepare_fow_detection
    geometries: list[object] = []

    def observed_prepare(
        engine: DetectionEngine,
        *args: object,
        **kwargs: object,
    ) -> DetectionDecisionStage | PreparedDetection:
        geometries.append(kwargs.get("geometry"))
        return original_prepare(engine, *args, **kwargs)

    monkeypatch.setattr(
        DetectionEngine,
        "_prepare_fow_detection",
        observed_prepare,
    )
    outcome, record = _run_two_sensor_cycle(
        _manager(identification=False),
        _sensor(sensor_id="geometry-a"),
        _sensor(sensor_id="geometry-b"),
        tick=0,
        targets=[_target()],
        first_native_period=1,
        first_lod_period=1,
    )

    assert len(geometries) == 2
    assert type(geometries[0]) is fog_of_war_module._DetectionGeometry
    assert geometries[0] is geometries[1]
    assert outcome.receipt.detection.api_calls == 2
    assert len(record.entries) == 2


@pytest.mark.parametrize(
    ("roster_mutation", "message"),
    (
        pytest.param(
            "duplicate",
            "duplicate sensor attachment identity",
            id="duplicate",
        ),
        pytest.param(
            "missing",
            "cadence plan must exactly cover",
            id="missing",
        ),
        pytest.param(
            "extra",
            "cadence plan must exactly cover",
            id="extra",
        ),
    ),
)
def test_roster_mismatch_rejects_before_indexed_issue(
    monkeypatch: pytest.MonkeyPatch,
    roster_mutation: str,
    message: str,
) -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    transaction, cadence, indexed, allocation, handle, identity = _begin_cycle(
        manager,
        sensor,
        tick=0,
    )
    own_unit = _own_unit(sensor)
    if roster_mutation == "duplicate":
        attachment = _attachment_record(sensor)
        own_unit["sensors"] = [sensor, sensor]
        own_unit["sensor_attachments"] = [attachment, attachment]
    elif roster_mutation == "missing":
        own_unit["sensors"] = []
        own_unit["sensor_attachments"] = []
    else:
        own_unit["sensors"] = [sensor, sensor]
        own_unit["sensor_attachments"] = [
            _attachment_record(sensor, source_equipment_index=7),
            _attachment_record(sensor, source_equipment_index=8),
        ]
    issue_calls = 0

    def unexpected_issue(
        _indexed_handle: FOWIndexedSideHandle,
        _decision_identity: FOWDecisionIdentity,
    ) -> None:
        nonlocal issue_calls
        issue_calls += 1
        raise AssertionError("roster rejection reached indexed RNG issue")

    monkeypatch.setattr(
        FOWIndexedSideHandle,
        "issue",
        unexpected_issue,
    )

    with pytest.raises(ValueError, match=message):
        manager.update_with_receipt(
            "blue",
            [own_unit],
            [_target()],
            5.0,
            transaction=transaction,
            cadence_plan=cadence,
            indexed_rng=handle,
            lod_tiers={identity.observer: FogOfWarLodTier.ACTIVE},
            current_time=5.0,
            current_tick=0,
            detection_culling=True,
        )

    assert issue_calls == 0
    assert indexed.committed_interval_count == 0
    assert indexed.committed_entry_count == 0
    assert manager._update_workspace is None
    assert manager.peek_world_view("blue") is None
    assert manager.intel_fusion.get_tracks("blue") == {}
    indexed.abort_interval(allocation)
    manager.cadence.abort_interval(cadence)


def test_both_axis_recovery_receipts_share_one_indexed_detection_block() -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[_target()],
        native_period=2,
        lod_period=2,
    )
    deferred, _record = _run_cycle(
        manager,
        sensor,
        tick=1,
        targets=[_target()],
        native_period=2,
        lod_period=2,
    )
    assert deferred.receipt.cadence.deferred_both == 1

    recovered, record = _run_cycle(
        manager,
        sensor,
        tick=2,
        targets=[_target()],
        native_period=2,
        lod_period=2,
    )

    assert len(record.entries) == 1
    assert recovered.receipt.indexed_rng.blocks == 1
    for buckets in (
        recovered.receipt.cadence.native_recoveries_by_period,
        recovered.receipt.cadence.lod_recoveries_by_period,
    ):
        assert len(buckets) == 1
        assert buckets[0].deferral_period == 2
        assert buckets[0].recovery_admissions == 1
        assert buckets[0].recovery_admissions_with_indexed_work == 1
        assert buckets[0].indexed_detection_blocks == 1


def test_recovery_pre_rng_rejection_does_not_invent_indexed_work() -> None:
    manager = _manager(identification=False)
    sensor = _sensor(maximum_range_m=10.0)
    distant_target = _target(position=Position(11.0, 0.0, 0.0))
    _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[distant_target],
        native_period=2,
        lod_period=1,
    )
    _run_cycle(
        manager,
        sensor,
        tick=1,
        targets=[distant_target],
        native_period=2,
        lod_period=1,
    )

    recovered, record = _run_cycle(
        manager,
        sensor,
        tick=2,
        targets=[distant_target],
        native_period=2,
        lod_period=1,
    )

    assert record.entries == ()
    assert recovered.receipt.detection.pre_rng_above_max_range_rejections == 1
    assert recovered.receipt.indexed_rng.blocks == 0
    bucket = recovered.receipt.cadence.native_recoveries_by_period[0]
    assert bucket.recovery_admissions == 1
    assert bucket.recovery_admissions_with_indexed_work == 0
    assert bucket.indexed_detection_blocks == 0


def test_unrelated_attachment_indexed_work_cannot_materialize_recovery() -> None:
    manager = _manager(identification=False)
    recovering_sensor = _sensor(
        sensor_id="phase118-short-eye",
        maximum_range_m=10.0,
    )
    working_sensor = _sensor(sensor_id="phase118-long-eye")
    distant_target = _target(position=Position(11.0, 0.0, 0.0))
    for tick in (0, 1):
        _run_two_sensor_cycle(
            manager,
            recovering_sensor,
            working_sensor,
            tick=tick,
            targets=[distant_target],
            first_native_period=2,
            first_lod_period=1,
        )

    recovered, record = _run_two_sensor_cycle(
        manager,
        recovering_sensor,
        working_sensor,
        tick=2,
        targets=[distant_target],
        first_native_period=2,
        first_lod_period=1,
    )

    assert len(record.entries) == 1
    assert record.entries[0].decision_preimage == encode_fow_decision(
        FOWDecisionIdentity(
            engine_tick=2,
            reporting_side="blue",
            observer_unit_id="blue-observer",
            source_equipment_index=8,
            sensor_id="phase118-long-eye",
            modeled_role=SensorModeledRole.VISUAL_OBSERVATION.value,
            target_kind=FOWTargetKind.UNIT,
            target_id="red-target",
        ),
    )
    assert recovered.receipt.indexed_rng.blocks == 1
    assert recovered.receipt.detection.pre_rng_above_max_range_rejections == 1
    bucket = recovered.receipt.cadence.native_recoveries_by_period[0]
    assert bucket.recovery_admissions == 1
    assert bucket.recovery_admissions_with_indexed_work == 0
    assert bucket.indexed_detection_blocks == 0


def test_aborted_recovery_plan_does_not_publish_staged_recovery_state() -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[_target()],
        native_period=2,
        lod_period=1,
    )
    _run_cycle(
        manager,
        sensor,
        tick=1,
        targets=[_target()],
        native_period=2,
        lod_period=1,
    )
    cadence_before = manager.cadence.attachment_states
    fog_before = manager.snapshot_side("blue")
    fusion_before = manager.intel_fusion.get_state()
    transaction, cadence_plan, indexed, allocation, handle, identity = _begin_cycle(
        manager,
        sensor,
        tick=2,
        native_period=2,
        lod_period=1,
    )

    side_plan = manager.update_with_receipt(
        "blue",
        [_own_unit(sensor)],
        [_target()],
        5.0,
        transaction=transaction,
        cadence_plan=cadence_plan,
        indexed_rng=handle,
        lod_tiers={identity.observer: FogOfWarLodTier.ACTIVE},
        current_time=15.0,
        current_tick=2,
        detection_culling=False,
    )
    bucket = side_plan.receipt.cadence.native_recoveries_by_period[0]
    assert bucket.recovery_admissions == 1

    indexed.abort_interval(allocation)
    manager.cadence.abort_interval(cadence_plan)
    manager.abort_update_transaction(transaction)

    assert manager.cadence.attachment_states == cadence_before
    assert manager.snapshot_side("blue") == fog_before
    assert manager.intel_fusion.get_state() == fusion_before


def test_admitted_zero_target_sweep_consumes_cadence_without_invented_work() -> None:
    manager = _manager(identification=False)
    sensor = _sensor()

    outcome, record = _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[],
    )

    receipt = outcome.receipt
    assert receipt.targets == 0
    assert receipt.target_opportunities == 0
    assert receipt.selection.brute_force_cycles == 1
    assert receipt.cadence.admitted == 1
    assert receipt.detection.api_calls == 0
    assert record.entries == ()
    state = manager.cadence.attachment_states[0]
    assert state.native_pending_ready is False
    assert state.lod_pending_ready is False


def test_fusion_outcome_counts_elapsed_prediction_and_update() -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    first, _first_record = _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[_target()],
    )
    assert first.receipt.fusion.creations == 1

    second, _second_record = _run_cycle(
        manager,
        sensor,
        tick=1,
        targets=[_target()],
    )

    assert second.receipt.fusion.predictions == 1
    assert second.receipt.fusion.predicted_microseconds == 5_000_000
    assert second.receipt.fusion.updates == 1
    assert second.receipt.fusion.replacements == 0


def test_failure_after_detached_prediction_discards_workspace_and_preserves_live_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    first, _first_record = _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[_target()],
    )
    assert first.receipt.fusion.creations == 1

    checkpoint = manager.capture_checkpoint_snapshot()
    checkpoint_state = copy.deepcopy(checkpoint.state)
    live_world_view = manager.peek_world_view("blue")
    assert live_world_view is not None
    world_view_before = copy.deepcopy(live_world_view.get_state())
    live_tracks_before = manager.intel_fusion.get_tracks("blue")
    assert live_tracks_before
    fusion_before = copy.deepcopy(manager.intel_fusion.get_state())
    scan_counts_before = copy.deepcopy(manager._detection.get_scan_count_state())
    witnesses_before = manager.get_current_detection_witnesses()
    supports_before = manager.get_observer_track_supports()
    rng_before = copy.deepcopy(manager._rng.bit_generator.state)

    transaction, cadence, indexed, allocation, handle, identity = _begin_cycle(
        manager,
        sensor,
        tick=1,
    )
    original_submit = IntelFusionEngine._submit_prevalidated_detached_sensor_fusion_with_outcome
    prediction_observed = False

    def fail_after_prediction(
        fusion: IntelFusionEngine,
        representative: _PreparedSensorFusionCandidate,
        *,
        candidate_count: int,
        contact_id: str | None,
    ) -> FusionSubmissionOutcome:
        nonlocal prediction_observed
        outcome = original_submit(
            fusion,
            representative,
            candidate_count=candidate_count,
            contact_id=contact_id,
        )
        assert outcome.predictions == 1
        prediction_observed = True
        raise RuntimeError("injected failure after detached prediction")

    monkeypatch.setattr(
        IntelFusionEngine,
        "_submit_prevalidated_detached_sensor_fusion_with_outcome",
        fail_after_prediction,
    )

    with pytest.raises(RuntimeError, match="after detached prediction"):
        manager.update_with_receipt(
            "blue",
            [_own_unit(sensor)],
            [_target()],
            5.0,
            transaction=transaction,
            cadence_plan=cadence,
            indexed_rng=handle,
            lod_tiers={identity.observer: FogOfWarLodTier.ACTIVE},
            current_time=10.0,
            current_tick=1,
            detection_culling=False,
        )
    assert prediction_observed is True

    indexed.abort_interval(allocation)
    manager.cadence.abort_interval(cadence)
    assert indexed.committed_interval_count == 0
    assert indexed.committed_entry_count == 0
    assert manager._update_workspace is None
    assert manager.peek_world_view("blue") is live_world_view
    assert live_world_view.get_state() == world_view_before
    live_tracks_after = manager.intel_fusion.get_tracks("blue")
    assert live_tracks_after.keys() == live_tracks_before.keys()
    assert all(live_tracks_after[track_id] is track for track_id, track in live_tracks_before.items())
    assert manager.intel_fusion.get_state() == fusion_before
    assert manager._detection.get_scan_count_state() == scan_counts_before
    assert manager.get_current_detection_witnesses() == witnesses_before
    assert manager.get_observer_track_supports() == supports_before
    assert manager._rng.bit_generator.state == rng_before
    assert checkpoint.state == checkpoint_state
    with pytest.raises(RuntimeError, match="poisoned interval"):
        manager.cadence.get_state()
    with pytest.raises(RuntimeError, match="poisoned update transaction"):
        manager.capture_checkpoint_snapshot()

    restored = _manager(seed=118_703, identification=False)
    restored.commit_state(restored.stage_state(checkpoint.state))
    assert restored.get_state() == checkpoint_state


def test_fusion_receipt_preserves_microsecond_clock_cadence() -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    first, _first_record = _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[_target()],
        interval_seconds=1e-6,
        time_origin_seconds=1.0,
    )
    assert first.receipt.fusion.creations == 1

    second, _second_record = _run_cycle(
        manager,
        sensor,
        tick=1,
        targets=[_target()],
        interval_seconds=1e-6,
        time_origin_seconds=1.0,
    )

    assert second.receipt.fusion.predictions == 1
    assert second.receipt.fusion.predicted_microseconds == 1
    assert second.receipt.fusion.updates == 1


def test_unit_and_decoy_use_distinct_exact_indexed_target_kinds() -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    decoy = Decoy(
        decoy_id="red-decoy",
        position=Position(0.0, 0.0, 0.0),
        deception_type=DeceptionType.DECOY_VISUAL,
        signature=_signature(),
        active=True,
    )

    outcome, record = _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[_target()],
        decoys=[decoy],
    )

    assert outcome.receipt.detection.stochastic_draws == 2
    expected_preimages = {
        encode_fow_decision(
            FOWDecisionIdentity(
                engine_tick=0,
                reporting_side="blue",
                observer_unit_id="blue-observer",
                source_equipment_index=7,
                sensor_id=sensor.sensor_id,
                modeled_role=SensorModeledRole.VISUAL_OBSERVATION.value,
                target_kind=kind,
                target_id=target_id,
            )
        )
        for kind, target_id in (
            (FOWTargetKind.UNIT, "red-target"),
            (FOWTargetKind.DECOY, "red-decoy"),
        )
    }
    assert {entry.decision_preimage for entry in record.entries} == (expected_preimages)


def test_fog_state_owns_strict_cadence_path_and_round_trips() -> None:
    source = _manager(identification=False)
    sensor = _sensor()
    _outcome, _record = _run_cycle(
        source,
        sensor,
        tick=0,
        targets=[],
    )
    state = source.get_state()

    assert state["cadence"] == source.cadence.get_state()
    assert state["cadence"]["committed_ordinal"] == 1
    target = _manager(seed=118_999, identification=False)
    target.set_state(copy.deepcopy(state))
    assert target.get_state() == state
    assert target.cadence.get_state() == source.cadence.get_state()


def test_fog_checkpoint_persists_scan_integration_and_continues_exactly() -> None:
    source = _manager(identification=False)
    sensor = _sensor()
    _first_outcome, _first_record = _run_cycle(
        source,
        sensor,
        tick=0,
        targets=[_target()],
    )
    state = source.get_state()

    assert list(state["scan_counts"].values()) == [1]
    target = _manager(seed=118_998, identification=False)
    target.set_state(copy.deepcopy(state))

    source_outcome, source_record = _run_cycle(
        source,
        sensor,
        tick=1,
        targets=[_target()],
    )
    target_outcome, target_record = _run_cycle(
        target,
        sensor,
        tick=1,
        targets=[_target()],
    )

    assert target_outcome.world_view.get_state() == source_outcome.world_view.get_state()
    assert target_outcome.receipt == source_outcome.receipt
    assert target_outcome.witnesses == source_outcome.witnesses
    assert target_record == source_record
    assert target.get_state() == source.get_state()
    assert list(target.get_state()["scan_counts"].values()) == [2]


@pytest.mark.parametrize(
    ("scan_counts", "message"),
    [
        ([], "must be a mapping"),
        ({"observer-v1:not-json": 1}, "state key is invalid"),
        ({"sensor:target": True}, "positive integer"),
        ({"sensor:target": 0}, "positive integer"),
        ({"": 1}, "non-empty text"),
    ],
)
def test_fog_checkpoint_rejects_malformed_scan_count_state(
    scan_counts: object,
    message: str,
) -> None:
    manager = _manager(identification=False)
    state = manager.get_state()
    state["scan_counts"] = scan_counts
    before = manager.get_state()

    with pytest.raises(ValueError, match=message):
        manager.stage_state(state)

    assert manager.get_state() == before


def test_fog_checkpoint_rejects_noncanonical_scan_count_state() -> None:
    manager = _manager(identification=False)
    state = manager.get_state()
    state["scan_counts"] = {
        "z-sensor:z-target": 1,
        "a-sensor:a-target": 1,
    }
    with pytest.raises(ValueError, match="not canonically ordered"):
        manager.stage_state(state)

    spaced = 'observer-v1:[ "blue", "blue-observer", 7, "phase118-eye", "red-target" ]'
    state["scan_counts"] = {spaced: 1}
    with pytest.raises(ValueError, match="not canonically encoded"):
        manager.stage_state(state)


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_fog_checkpoint_requires_exact_modern_scan_count_topology(
    mutation: str,
) -> None:
    manager = _manager(identification=False)
    state = manager.get_state()
    if mutation == "missing":
        del state["scan_counts"]
    else:
        state["unexpected"] = {}

    with pytest.raises(ValueError, match="invalid topology"):
        manager.stage_state(state)


def test_fog_checkpoint_rejects_detection_scan_mirror_disagreement() -> None:
    source = _manager(identification=False)
    sensor = _sensor()
    _outcome, _record = _run_cycle(
        source,
        sensor,
        tick=0,
        targets=[_target()],
    )
    state = source.get_state()
    target = _manager(identification=False)
    before = target.get_state()

    with pytest.raises(ValueError, match="disagree with DetectionEngine"):
        target.stage_state(
            state,
            authoritative_detection_scan_counts={},
        )

    assert target.get_state() == before
    plan = target.stage_state(
        state,
        authoritative_detection_scan_counts=state["scan_counts"],
    )
    target.commit_state(plan)
    assert target.get_state() == state


def test_fog_restore_rejects_foreign_and_tampered_scan_snapshots_atomically() -> None:
    source = _manager(identification=False)
    sensor = _sensor()
    _outcome, _record = _run_cycle(
        source,
        sensor,
        tick=0,
        targets=[_target()],
    )
    target = _manager(identification=False)
    before = target.get_state()

    foreign_plan = source.stage_state(source.get_state())
    with pytest.raises(ValueError, match="restore plan is foreign"):
        target.commit_state(foreign_plan)
    foreign_scan_counts = source._detection.snapshot_scan_counts()
    with pytest.raises(ValueError, match="belongs to another engine"):
        target._detection.commit_scan_counts(foreign_scan_counts)
    assert target.get_state() == before

    plan = target.stage_state(source.get_state())
    object.__setattr__(plan._scan_counts, "_fingerprint", "tampered")
    with pytest.raises(ValueError, match="snapshot was mutated"):
        target.commit_state(plan)
    assert target.get_state() == before


@pytest.mark.parametrize(
    "failing_owner",
    ("detection", "fusion", "cadence"),
)
def test_fog_restore_preparation_failure_preserves_every_live_owner(
    monkeypatch: pytest.MonkeyPatch,
    failing_owner: str,
) -> None:
    source = _manager(seed=118_710, identification=False)
    target = _manager(seed=118_711, identification=False)
    sensor = _sensor()
    _run_cycle(source, sensor, tick=0, targets=[_target()])
    _run_cycle(target, sensor, tick=0, targets=[_target()])
    plan = target.stage_state(source.get_state())
    state_before = target.get_state()
    checkpoint_before = target.capture_checkpoint_snapshot().state
    live_bindings = (
        target._detection._scan_counts,
        target._intel_fusion._tracks,
        target._intel_fusion._fow_track_counters,
        target.cadence._states,
        target.cadence._phase_assignments,
        target._world_views,
        target._current_detection_witnesses,
        target._observer_track_supports,
    )

    def fail_preparation(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError(f"injected {failing_owner} restore preparation failure")

    if failing_owner == "detection":
        monkeypatch.setattr(
            DetectionEngine,
            "_validated_scan_counts",
            fail_preparation,
        )
    elif failing_owner == "fusion":
        monkeypatch.setattr(
            IntelFusionEngine,
            "_prepare_commit_state",
            staticmethod(fail_preparation),
        )
    else:
        monkeypatch.setattr(
            TacticalCadenceScheduler,
            "_prepare_restore_commit",
            fail_preparation,
        )

    with pytest.raises(
        RuntimeError,
        match=rf"injected {failing_owner} restore preparation failure",
    ):
        target.commit_state(plan)

    monkeypatch.undo()
    assert target.get_state() == state_before
    assert target.capture_checkpoint_snapshot().state == checkpoint_before
    assert all(
        current is previous
        for current, previous in zip(
            (
                target._detection._scan_counts,
                target._intel_fusion._tracks,
                target._intel_fusion._fow_track_counters,
                target.cadence._states,
                target.cadence._phase_assignments,
                target._world_views,
                target._current_detection_witnesses,
                target._observer_track_supports,
            ),
            live_bindings,
            strict=True,
        )
    )


def test_fog_checkpoint_rejects_active_and_poisoned_cadence_transaction() -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    transaction, plan, _indexed, _allocation, _handle, _identity_value = _begin_cycle(
        manager,
        sensor,
        tick=0,
    )

    with pytest.raises(RuntimeError, match="active update transaction"):
        manager.get_state()
    assert manager._update_workspace is not None
    manager.abort_update_transaction(transaction)
    manager.cadence.abort_interval(plan)
    assert manager._update_workspace is None
    with pytest.raises(RuntimeError, match="poisoned update transaction"):
        manager.get_state()


def test_fow_scan_counts_build_one_publication_snapshot_and_reuse_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    legacy_key = ("legacy-sensor", "legacy-target")
    observer_key = (
        "blue",
        "blue-observer",
        7,
        sensor.sensor_id,
        "red-target",
    )
    manager._detection._scan_counts = {legacy_key: 2}
    original_private_stage = DetectionEngine._stage_fow_scan_count_values
    staged_calls: list[tuple[object, object]] = []

    def reject_public_snapshot(_engine: DetectionEngine) -> object:
        raise AssertionError("FOW transaction used the public scan-count snapshot path")

    def reject_public_stage(
        _engine: DetectionEngine,
        _entries: object,
    ) -> object:
        raise AssertionError("FOW transaction used public scan-count staging")

    def record_private_stage(
        engine: DetectionEngine,
        values: object,
    ) -> object:
        snapshot = original_private_stage(engine, values)  # type: ignore[arg-type]
        staged_calls.append((values, snapshot))
        return snapshot

    monkeypatch.setattr(
        DetectionEngine,
        "snapshot_scan_counts",
        reject_public_snapshot,
    )
    monkeypatch.setattr(
        DetectionEngine,
        "stage_scan_counts",
        reject_public_stage,
    )
    monkeypatch.setattr(
        DetectionEngine,
        "_stage_fow_scan_count_values",
        record_private_stage,
    )

    transaction, cadence, indexed, allocation, handle, identity = _begin_cycle(
        manager,
        sensor,
        tick=0,
    )
    side_plan = manager.update_with_receipt(
        "blue",
        [_own_unit(sensor)],
        [_target()],
        5.0,
        transaction=transaction,
        cadence_plan=cadence,
        indexed_rng=handle,
        lod_tiers={identity.observer: FogOfWarLodTier.ACTIVE},
        current_time=5.0,
        current_tick=0,
        detection_culling=False,
    )
    publication = manager.prevalidate_update_transaction(
        transaction,
        (side_plan,),
    )

    assert len(staged_calls) == 1
    staged_values, staged_snapshot = staged_calls[0]
    assert publication._scan_counts is staged_snapshot
    prepared = manager.prepare_update_commit(publication)
    workspace = manager._update_workspace
    payload = manager._prepared_update_payload
    assert workspace is not None
    assert payload is not None
    assert staged_values is workspace.publication_scan_count_values
    assert payload.scan_counts is publication._scan_counts
    assert payload.scan_count_values is workspace.publication_scan_count_values
    assert payload.scan_count_values_binding is workspace.publication_scan_count_values_binding
    assert payload.scan_count_values_binding.keys == tuple(payload.scan_count_values)
    assert all(
        bound_key is current_key
        for bound_key, current_key in zip(
            payload.scan_count_values_binding.keys,
            payload.scan_count_values,
            strict=True,
        )
    )
    assert payload.scan_count_values == {legacy_key: 2, observer_key: 1}
    assert len(staged_calls) == 1
    manager.validate_prepared_update_commit(prepared)

    indexed.commit_interval(allocation)
    manager.cadence.commit_interval(cadence)
    manager.commit_prepared_update(prepared)

    assert manager._detection._snapshot_scan_count_values() == {
        legacy_key: 2,
        observer_key: 1,
    }
    assert len(staged_calls) == 1
    monkeypatch.undo()
    assert manager.capture_checkpoint_snapshot().state == manager.get_state()
    assert len(staged_calls) == 1


def test_fow_mutable_raw_scan_count_key_rejects_after_prepare_without_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    mutable_sensor_id = _MutableScanCountText("legacy-sensor")
    legacy_key = (mutable_sensor_id, "legacy-target")
    manager._detection._scan_counts = {legacy_key: 1}
    world_view_before = manager.snapshot_side("blue")
    fusion_before = copy.deepcopy(manager.intel_fusion.get_state())
    witnesses_before = manager.get_current_detection_witnesses()
    supports_before = manager.get_observer_track_supports()
    rng_before = copy.deepcopy(manager._rng.bit_generator.state)
    cadence_states_before = manager.cadence.attachment_states
    cadence_ordinal_before = manager.cadence.committed_ordinal
    original_public_stage = DetectionEngine.stage_scan_counts
    original_full_validation = FogOfWarManager._validate_scan_count_snapshot_values
    public_stage_calls: list[tuple[object, ...]] = []
    full_validation_fields: list[str] = []

    def record_public_stage(
        engine: DetectionEngine,
        entries: tuple[object, ...],
    ) -> object:
        public_stage_calls.append(entries)
        return original_public_stage(engine, entries)  # type: ignore[arg-type]

    def record_full_validation(
        fow: FogOfWarManager,
        snapshot: object,
        values: object,
        *,
        field_name: str,
        verify_snapshot_fingerprint: bool,
    ) -> None:
        full_validation_fields.append(field_name)
        original_full_validation(
            fow,
            snapshot,  # type: ignore[arg-type]
            values,  # type: ignore[arg-type]
            field_name=field_name,
            verify_snapshot_fingerprint=verify_snapshot_fingerprint,
        )

    monkeypatch.setattr(
        DetectionEngine,
        "stage_scan_counts",
        record_public_stage,
    )
    monkeypatch.setattr(
        FogOfWarManager,
        "_validate_scan_count_snapshot_values",
        record_full_validation,
    )

    transaction, cadence, indexed, allocation, handle, identity = _begin_cycle(
        manager,
        sensor,
        tick=0,
    )
    side_plan = manager.update_with_receipt(
        "blue",
        [_own_unit(sensor)],
        [_target()],
        5.0,
        transaction=transaction,
        cadence_plan=cadence,
        indexed_rng=handle,
        lod_tiers={identity.observer: FogOfWarLodTier.ACTIVE},
        current_time=5.0,
        current_tick=0,
        detection_culling=False,
    )
    publication = manager.prevalidate_update_transaction(
        transaction,
        (side_plan,),
    )
    prepared = manager.prepare_update_commit(publication)
    payload = manager._prepared_update_payload
    assert payload is not None
    assert payload.scan_count_values_binding.exact_builtin is False
    legacy_entry = next(entry for entry in publication._scan_counts.entries if entry.scan_identity is None)
    assert legacy_entry.sensor_id is mutable_sensor_id
    assert next(iter(payload.scan_count_values))[0] is mutable_sensor_id
    assert len(public_stage_calls) == 1
    assert full_validation_fields == ["fog-of-war publication"]

    mutable_sensor_id.hash_salt = 1
    with pytest.raises(
        ValueError,
        match="fog-of-war commit payload scan counts changed",
    ):
        manager.validate_prepared_update_commit(prepared)

    assert full_validation_fields == [
        "fog-of-war publication",
        "fog-of-war commit payload",
    ]
    assert len(public_stage_calls) == 1
    assert manager.snapshot_side("blue") == world_view_before
    assert manager.intel_fusion.get_state() == fusion_before
    assert manager.get_current_detection_witnesses() == witnesses_before
    assert manager.get_observer_track_supports() == supports_before
    assert manager._rng.bit_generator.state == rng_before
    assert manager.cadence.attachment_states == cadence_states_before
    assert manager.cadence.committed_ordinal == cadence_ordinal_before
    assert indexed.committed_interval_count == 0
    assert indexed.committed_entry_count == 0

    mutable_sensor_id.hash_salt = 0
    assert manager._detection._scan_counts == {legacy_key: 1}
    indexed.abort_interval(allocation)
    manager.cadence.abort_interval(cadence)
    manager.abort_update_transaction(transaction)
    assert manager._update_workspace is None


@pytest.mark.parametrize(
    "invalid_key",
    (
        ("legacy\ud800", "target"),
        ("blue", "observer", 7, "sensor", "target\ud800"),
    ),
)
def test_fow_rejects_non_utf8_raw_scan_counts_before_transaction_publication(
    invalid_key: tuple[object, ...],
) -> None:
    manager = _manager(identification=False)
    manager._detection._scan_counts = {invalid_key: 1}  # type: ignore[dict-item]
    live_before = (
        manager.snapshot_side("blue"),
        copy.deepcopy(manager.intel_fusion.get_state()),
        manager.get_current_detection_witnesses(),
        manager.get_observer_track_supports(),
        copy.deepcopy(manager._rng.bit_generator.state),
        manager.cadence.committed_ordinal,
    )
    raw_counts_before = dict(manager._detection._scan_counts)

    with pytest.raises(ValueError, match="valid UTF-8"):
        manager.begin_update_transaction(("blue",))

    assert manager._update_workspace is None
    assert manager._active_update_transaction is None
    assert manager._update_generation == 0
    assert manager._detection._scan_counts == raw_counts_before
    assert (
        manager.snapshot_side("blue"),
        manager.intel_fusion.get_state(),
        manager.get_current_detection_witnesses(),
        manager.get_observer_track_supports(),
        manager._rng.bit_generator.state,
        manager.cadence.committed_ordinal,
    ) == live_before


@pytest.mark.parametrize(
    ("tamper_target", "expected_error", "message"),
    (
        (
            "publication-count-bool",
            ValueError,
            "fog-of-war publication scan counts changed",
        ),
        (
            "publication-owner",
            ValueError,
            "fog-of-war publication scan-count metadata was mutated",
        ),
        (
            "publication-entry-tuple",
            ValueError,
            "fog-of-war publication scan-count metadata was mutated",
        ),
        (
            "publication-utf8",
            ValueError,
            "fog-of-war publication scan counts changed",
        ),
        (
            "payload-count-bool",
            ValueError,
            "fog-of-war commit payload scan counts changed",
        ),
        (
            "payload-utf8",
            ValueError,
            "fog-of-war commit payload scan counts changed",
        ),
        (
            "payload-topology",
            ValueError,
            "fog-of-war commit payload scan counts changed",
        ),
        (
            "payload-binding-fields",
            ValueError,
            "fog-of-war commit payload scan counts are stale",
        ),
        (
            "live-count-bool",
            RuntimeError,
            "live fog-of-war scan counts changed before publication",
        ),
    ),
)
def test_fow_raw_scan_count_tamper_rejects_without_publication(
    tamper_target: str,
    expected_error: type[Exception],
    message: str,
) -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    legacy_key = ("legacy-sensor", "legacy-target")
    baseline_scan_counts = {legacy_key: 1}
    manager._detection._scan_counts = dict(baseline_scan_counts)
    world_view_before = manager.snapshot_side("blue")
    fusion_before = copy.deepcopy(manager.intel_fusion.get_state())
    witnesses_before = manager.get_current_detection_witnesses()
    supports_before = manager.get_observer_track_supports()
    rng_before = copy.deepcopy(manager._rng.bit_generator.state)
    cadence_states_before = manager.cadence.attachment_states
    cadence_ordinal_before = manager.cadence.committed_ordinal
    transaction, cadence, indexed, allocation, handle, identity = _begin_cycle(
        manager,
        sensor,
        tick=0,
    )
    side_plan = manager.update_with_receipt(
        "blue",
        [_own_unit(sensor)],
        [_target()],
        5.0,
        transaction=transaction,
        cadence_plan=cadence,
        indexed_rng=handle,
        lod_tiers={identity.observer: FogOfWarLodTier.ACTIVE},
        current_time=5.0,
        current_tick=0,
        detection_culling=False,
    )
    publication = manager.prevalidate_update_transaction(
        transaction,
        (side_plan,),
    )

    if tamper_target.startswith("publication"):
        legacy_entry = next(entry for entry in publication._scan_counts.entries if entry.scan_identity is None)
        assert legacy_entry.count == 1
        if tamper_target == "publication-count-bool":
            object.__setattr__(legacy_entry, "count", True)
        elif tamper_target == "publication-owner":
            object.__setattr__(
                publication._scan_counts,
                "_owner_token",
                object(),
            )
        elif tamper_target == "publication-entry-tuple":
            replacement_entries = tuple(list(publication._scan_counts._entries))
            assert replacement_entries == publication._scan_counts._entries
            assert replacement_entries is not publication._scan_counts._entries
            object.__setattr__(
                publication._scan_counts,
                "_entries",
                replacement_entries,
            )
        else:
            object.__setattr__(legacy_entry, "sensor_id", "legacy\ud800")
        with pytest.raises(expected_error, match=message):
            manager.prepare_update_commit(publication)
    else:
        prepared = manager.prepare_update_commit(publication)
        payload = manager._prepared_update_payload
        assert payload is not None
        if tamper_target == "payload-count-bool":
            payload.scan_count_values[legacy_key] = True
        elif tamper_target == "payload-utf8":
            payload.scan_count_values[("legacy\ud800", "legacy-target")] = 1
        elif tamper_target == "payload-topology":
            del payload.scan_count_values[legacy_key]
        elif tamper_target == "payload-binding-fields":
            binding = payload.scan_count_values_binding
            replacement_keys = tuple(tuple(list(key)) for key in binding.keys)
            replacement_counts = tuple(list(binding.counts))
            assert replacement_keys == binding.keys
            assert replacement_keys is not binding.keys
            assert replacement_counts == binding.counts
            assert replacement_counts is not binding.counts
            assert all(
                replacement is not original
                for replacement, original in zip(
                    replacement_keys,
                    binding.keys,
                    strict=True,
                )
            )
            payload.scan_count_values.clear()
            payload.scan_count_values.update(
                zip(replacement_keys, replacement_counts, strict=True),
            )
            object.__setattr__(binding, "keys", replacement_keys)
            object.__setattr__(binding, "counts", replacement_counts)
            manager._validate_scan_count_values_binding(
                payload.scan_count_values,
                binding,
                field_name="unsealed matching tamper control",
            )
        else:
            manager._detection._scan_counts[legacy_key] = True
        with pytest.raises(expected_error, match=message):
            manager.validate_prepared_update_commit(prepared)

    assert manager.snapshot_side("blue") == world_view_before
    assert manager.intel_fusion.get_state() == fusion_before
    assert manager.get_current_detection_witnesses() == witnesses_before
    assert manager.get_observer_track_supports() == supports_before
    assert manager._rng.bit_generator.state == rng_before
    assert manager.cadence.attachment_states == cadence_states_before
    assert manager.cadence.committed_ordinal == cadence_ordinal_before
    assert indexed.committed_interval_count == 0
    assert indexed.committed_entry_count == 0
    expected_live_scan_counts = {legacy_key: True} if tamper_target == "live-count-bool" else baseline_scan_counts
    assert manager._detection._scan_counts == expected_live_scan_counts

    manager._detection._scan_counts = dict(baseline_scan_counts)
    indexed.abort_interval(allocation)
    manager.cadence.abort_interval(cadence)
    manager.abort_update_transaction(transaction)
    assert manager._update_workspace is None


def _run_two_side_transaction(
    *,
    parallel: bool,
) -> tuple[
    dict[str, object],
    object,
    tuple[object, ...],
    tuple[object, ...],
    tuple[object, ...],
]:
    manager = _manager(identification=False)
    sensor = _sensor()
    expected_scan_counts = {
        ("legacy-sensor", "legacy-target"): 9,
        (
            "blue",
            "blue-observer",
            7,
            sensor.sensor_id,
            "red-target",
        ): 3,
        (
            "red",
            "red-observer",
            7,
            sensor.sensor_id,
            "blue-target",
        ): 5,
    }
    manager._detection._scan_counts = {
        ("legacy-sensor", "legacy-target"): 9,
        (
            "blue",
            "blue-observer",
            7,
            sensor.sensor_id,
            "red-target",
        ): 2,
        (
            "red",
            "red-observer",
            7,
            sensor.sensor_id,
            "blue-target",
        ): 4,
    }
    transaction = manager.begin_update_transaction(("blue", "red"))
    identities = {
        "blue": _attachment_identity(sensor),
        "red": _attachment_identity(
            sensor,
            unit_id="red-observer",
            side="red",
        ),
    }
    cadence_plan = manager.cadence.stage_interval(
        [
            TacticalCadenceAttachment(
                identity=identities[side],
                native_period=1,
                lod_period=1,
                operational=True,
            )
            for side in ("blue", "red")
        ]
    )
    indexed = IndexedFOWRNG(118_700)
    allocation = indexed.begin_interval(
        module=ModuleId.DETECTION,
        engine_tick=0,
        reporting_sides=("blue", "red"),
    )
    handles = {side: allocation.acquire_side(side) for side in ("blue", "red")}
    side_inputs = {
        "blue": (
            [_own_unit(sensor)],
            [
                _target(),
                _target(
                    "red-terminal-range",
                    position=Position(1_000.0, 1_000.0, 0.0),
                ),
            ],
        ),
        "red": (
            [_own_unit(sensor, unit_id="red-observer")],
            [
                _target("blue-target"),
                _target(
                    "blue-terminal-range",
                    position=Position(1_000.0, 1_000.0, 0.0),
                ),
            ],
        ),
    }

    def stage(side: str) -> object:
        own_units, enemy_units = side_inputs[side]
        return manager.update_with_receipt(
            side,
            own_units,
            enemy_units,
            5.0,
            transaction=transaction,
            cadence_plan=cadence_plan,
            indexed_rng=handles[side],
            lod_tiers={
                identities[side].observer: FogOfWarLodTier.ACTIVE,
            },
            current_time=5.0,
            current_tick=0,
            detection_culling=True,
        )

    if parallel:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {side: executor.submit(stage, side) for side in ("blue", "red")}
            plans = {side: futures[side].result() for side in ("blue", "red")}
    else:
        plans = {side: stage(side) for side in ("blue", "red")}

    publication = manager.prevalidate_update_transaction(
        transaction,
        tuple(plans[side] for side in ("blue", "red")),
    )
    record = indexed.commit_interval(allocation)
    manager.cadence.commit_interval(cadence_plan)
    manager.commit_update_transaction(publication)
    assert manager._detection._snapshot_scan_count_values() == expected_scan_counts
    state = manager.get_state()
    assert manager.capture_checkpoint_snapshot().state == state
    outcome_projections: list[object] = []
    for side in ("blue", "red"):
        outcome = plans[side].outcome
        assert outcome.world_view.side == side
        assert all(contact.track.side == side for contact in outcome.world_view.contacts.values())
        outcome_projections.append(
            (
                outcome.world_view.get_state(),
                outcome.receipt,
                tuple(witness.get_state() for witness in outcome.witnesses),
                tuple(support.get_state() for support in outcome.observer_track_supports),
            ),
        )
    return (
        state,
        record,
        tuple(plans[side].receipt for side in ("blue", "red")),
        tuple(manager.snapshot_side(side) for side in ("blue", "red")),
        tuple(outcome_projections),
    )


def test_side_plans_are_isolated_and_serial_threaded_publication_is_exact() -> None:
    sequential = _run_two_side_transaction(parallel=False)
    threaded = _run_two_side_transaction(parallel=True)

    assert threaded == sequential
    assert all(
        receipt.selection.strtree_queries == receipt.observers == 1
        and receipt.selection.strtree_admitted_targets == 2
        and receipt.selection.strtree_pruned_targets == 0
        and receipt.detection.api_calls == 2
        and receipt.detection.pre_rng_above_max_range_rejections == 1
        and receipt.detection.stochastic_draws == 1
        for receipt in sequential[2]
    )


def test_side_staging_never_copies_or_mutates_foreign_side_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, _record, _receipts, _snapshots, _outcomes = _run_two_side_transaction(
        parallel=False,
    )
    manager = _manager(seed=118_702, identification=False)
    manager.set_state(copy.deepcopy(state))
    sensor = _sensor()
    red_world_view = manager.peek_world_view("red")
    assert red_world_view is not None
    red_tracks = manager.intel_fusion.get_tracks("red")
    assert red_tracks
    red_world_view_state = red_world_view.get_state()
    red_track_states = {track_id: track.get_state() for track_id, track in red_tracks.items()}
    transaction = manager.begin_update_transaction(("blue", "red"))
    identities = {
        "blue": _attachment_identity(sensor),
        "red": _attachment_identity(
            sensor,
            unit_id="red-observer",
            side="red",
        ),
    }
    cadence_plan = manager.cadence.stage_interval(
        [
            TacticalCadenceAttachment(
                identity=identities[side],
                native_period=1,
                lod_period=1,
                operational=True,
            )
            for side in ("blue", "red")
        ]
    )
    indexed = IndexedFOWRNG(118_702)
    allocation = indexed.begin_interval(
        module=ModuleId.DETECTION,
        engine_tick=1,
        reporting_sides=("blue", "red"),
    )
    handle = allocation.acquire_side("blue")
    original_deepcopy = copy.deepcopy
    copied_object_ids: set[int] = set()

    def observed_deepcopy(value: object, *args: object, **kwargs: object) -> object:
        copied_object_ids.add(id(value))
        return original_deepcopy(value, *args, **kwargs)

    monkeypatch.setattr(fog_of_war_module.copy, "deepcopy", observed_deepcopy)
    side_plan = manager.update_with_receipt(
        "blue",
        [_own_unit(sensor)],
        [_target()],
        5.0,
        transaction=transaction,
        cadence_plan=cadence_plan,
        indexed_rng=handle,
        lod_tiers={identities["blue"].observer: FogOfWarLodTier.ACTIVE},
        current_time=10.0,
        current_tick=1,
        detection_culling=False,
    )

    assert all(contact.track.side == "blue" for contact in side_plan.outcome.world_view.contacts.values())
    assert id(red_world_view) not in copied_object_ids
    assert not copied_object_ids.intersection(map(id, red_tracks.values()))
    assert red_world_view.get_state() == red_world_view_state
    assert {track_id: track.get_state() for track_id, track in red_tracks.items()} == red_track_states
    assert manager.snapshot_side("red").identities == _snapshots[1].identities

    indexed.abort_interval(allocation)
    manager.cadence.abort_interval(cadence_plan)
    manager.abort_update_transaction(transaction)
    assert manager._update_workspace is None


def test_update_baseline_uses_one_detached_fusion_track_graph() -> None:
    manager = _manager(seed=142_058, identification=False)
    _run_cycle(
        manager,
        _sensor(),
        tick=0,
        targets=[_target()],
    )
    checkpoint = manager.capture_checkpoint_snapshot().state
    live_world_view = manager.peek_world_view("blue")
    assert live_world_view is not None
    live_contact = live_world_view.contacts["red-target"]
    live_track = live_contact.track
    assert manager.intel_fusion.get_tracks("blue")[live_track.track_id] is live_track
    live_witness = manager._current_detection_witnesses["blue"][0]

    transaction = manager.begin_update_transaction(("blue",))
    workspace = manager._update_workspace
    assert workspace is not None
    staged_world_view = workspace.world_views["blue"]
    staged_contact = staged_world_view.contacts["red-target"]
    staged_track = workspace.intel_fusion["tracks"]["blue"][live_track.track_id]

    assert staged_world_view is not live_world_view
    assert staged_contact is not live_contact
    assert staged_contact.reporting_sensors is not live_contact.reporting_sensors
    assert staged_contact.track is staged_track
    assert staged_track is not live_track
    assert staged_track.get_state() == live_track.get_state()
    assert staged_track.contact_info is not live_track.contact_info
    assert staged_track.state is not live_track.state
    assert not np.shares_memory(staged_track.state.position, live_track.state.position)
    assert not np.shares_memory(staged_track.state.velocity, live_track.state.velocity)
    assert not np.shares_memory(staged_track.state.covariance, live_track.state.covariance)
    staged_witness = workspace.current_detection_witnesses["blue"][0]
    assert staged_witness is not live_witness
    assert staged_witness.get_state() == live_witness.get_state()

    staged_contact.reporting_sensors.append("staged-only")
    staged_track.hits += 1
    staged_track.state.position[0] += 100.0
    staged_track.state.velocity[0] += 10.0
    staged_track.state.covariance[0, 0] += 1.0
    object.__setattr__(
        staged_witness,
        "probability",
        staged_witness.probability / 2.0,
    )
    assert live_world_view.get_state() == checkpoint["world_views"]["blue"]
    assert manager.intel_fusion.get_tracks("blue")[live_track.track_id] is live_track
    assert live_witness.get_state() == checkpoint["current_detection_witnesses"]["blue"][0]

    manager.abort_update_transaction(transaction)
    assert manager._update_workspace is None
    with pytest.raises(
        RuntimeError,
        match="checkpoint is unavailable after a poisoned update transaction",
    ):
        manager.capture_checkpoint_snapshot()
    restored = _manager(seed=142_058, identification=False)
    restored.commit_state(restored.stage_state(copy.deepcopy(checkpoint)))
    assert restored.capture_checkpoint_snapshot().state == checkpoint


def test_detection_witness_deepcopy_preserves_memo_without_live_aliases() -> None:
    manager = _manager(seed=142_060, identification=False)
    _run_cycle(
        manager,
        _sensor(),
        tick=0,
        targets=[_target()],
    )
    live_witness = manager._current_detection_witnesses["blue"][0]
    expected = live_witness.get_state()

    repeated = copy.deepcopy((live_witness, live_witness))
    assert type(repeated[0]) is type(live_witness)
    assert repeated[0].get_state() == expected
    assert repeated[0] is repeated[1]
    assert repeated[0] is not live_witness
    copied_map = manager._copy_detection_witness_map(
        {"blue": (live_witness, live_witness)},
    )
    assert copied_map["blue"][0] is copied_map["blue"][1]
    assert copied_map["blue"][0] is not live_witness

    public_witness = manager.get_current_detection_witnesses("blue")[0]
    transaction = manager.begin_update_transaction(("blue",))
    workspace = manager._update_workspace
    assert workspace is not None
    workspace_witness = workspace.current_detection_witnesses["blue"][0]
    assert public_witness.get_state() == workspace_witness.get_state() == expected
    assert len({id(live_witness), id(public_witness), id(workspace_witness)}) == 3

    object.__setattr__(public_witness, "probability", 0.25)
    object.__setattr__(workspace_witness, "probability", 0.75)
    assert public_witness.probability == 0.25
    assert workspace_witness.probability == 0.75
    assert live_witness.get_state() == expected

    manager.abort_update_transaction(transaction)
    assert manager._update_workspace is None


def test_detection_witness_deepcopy_detaches_subclasses_and_raw_tamper() -> None:
    class MutableText(str):
        metadata: list[str]

    class MutableInteger(int):
        metadata: list[str]

    class MutableFloat(float):
        metadata: list[str]

    shared_text = MutableText("blue")
    shared_text.metadata = ["source-text"]
    mutable_index = MutableInteger(7)
    mutable_index.metadata = ["source-index"]
    shared_number = MutableFloat(0.5)
    shared_number.metadata = ["source-number"]
    source = fog_of_war_module.ObserverDetectionWitness(
        side=shared_text,
        observer_unit_id=shared_text,
        target_id="red-target",
        source_equipment_index=mutable_index,
        sensor_id="sensor",
        modeled_role="visual_observation",
        logical_time_s=shared_number,
        detected=True,
        probability=shared_number,
        snr_db=1.0,
        range_m=10.0,
        sensor_type="VISUAL",
        bearing_deg=0.0,
    )

    detached = copy.deepcopy(source)

    assert detached is not source
    assert type(detached) is fog_of_war_module.ObserverDetectionWitness
    assert detached.get_state() == source.get_state()
    assert detached.side is detached.observer_unit_id
    assert detached.side is not shared_text
    assert detached.source_equipment_index is not mutable_index
    assert detached.logical_time_s is detached.probability
    assert detached.logical_time_s is not shared_number
    assert detached.side.metadata is not shared_text.metadata
    assert detached.source_equipment_index.metadata is not mutable_index.metadata
    assert detached.logical_time_s.metadata is not shared_number.metadata

    copied_map = fog_of_war_module.FogOfWarManager._copy_detection_witness_map(
        {shared_text: (source,)},
    )
    detached_side = next(iter(copied_map))
    mapped_witness = copied_map[detached_side][0]
    assert detached_side is mapped_witness.side
    assert detached_side is not shared_text
    assert detached_side.metadata is not shared_text.metadata
    detached_side.metadata.append("map-only")
    assert shared_text.metadata == ["source-text"]

    detached.side.metadata.append("detached-only")
    detached.source_equipment_index.metadata.append("detached-only")
    detached.logical_time_s.metadata.append("detached-only")
    assert shared_text.metadata == ["source-text"]
    assert mutable_index.metadata == ["source-index"]
    assert shared_number.metadata == ["source-number"]

    cyclic_tamper: list[object] = []
    cyclic_tamper.append(cyclic_tamper)
    object.__setattr__(source, "sensor_id", cyclic_tamper)
    tampered_copy = copy.deepcopy(source)
    assert tampered_copy.sensor_id is not cyclic_tamper
    assert tampered_copy.sensor_id[0] is tampered_copy.sensor_id


def test_update_baseline_rejects_a_mismatched_staged_fusion_track_atomically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(seed=142_059, identification=False)
    _run_cycle(
        manager,
        _sensor(),
        tick=0,
        targets=[_target()],
    )
    checkpoint = manager.capture_checkpoint_snapshot().state
    generation = manager._update_generation
    original_stage_state = IntelFusionEngine.stage_state

    def mismatched_stage_state(
        engine: IntelFusionEngine,
        state: object,
        **kwargs: object,
    ) -> dict[str, object]:
        assert isinstance(state, dict)
        staged = original_stage_state(engine, state, **kwargs)
        tracks = staged["tracks"]
        assert isinstance(tracks, dict)
        side_tracks = tracks["blue"]
        assert isinstance(side_tracks, dict)
        staged_track = next(iter(side_tracks.values()))
        staged_track.hits += 1
        return staged

    monkeypatch.setattr(
        IntelFusionEngine,
        "stage_state",
        mismatched_stage_state,
    )

    with pytest.raises(
        ValueError,
        match="contact cannot bind to its staged fusion track",
    ):
        manager.begin_update_transaction(("blue",))

    monkeypatch.undo()
    assert manager._update_workspace is None
    assert manager._active_update_transaction is None
    assert manager._update_generation == generation
    assert manager.capture_checkpoint_snapshot().state == checkpoint


def test_update_transaction_binds_one_exact_active_cadence_plan() -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    transaction, cadence, indexed, allocation, _handle, _identity_value = _begin_cycle(
        manager,
        sensor,
        tick=0,
    )
    workspace = manager._update_workspace
    assert workspace is not None
    binding = manager.cadence._active_interval_binding_for_owner(cadence)

    manager._bind_update_cadence_plan(workspace, cadence)
    manager._bind_update_cadence_plan(workspace, cadence)
    assert workspace.cadence_binding is binding

    replacement = manager.cadence.stage_witness_promotions(cadence, ())
    replacement_binding = manager.cadence._active_interval_binding_for_owner(replacement)
    assert replacement_binding is not binding
    with pytest.raises(ValueError, match="cadence plan is foreign or stale"):
        manager._bind_update_cadence_plan(workspace, replacement)
    assert workspace.cadence_binding is binding

    indexed.abort_interval(allocation)
    manager.cadence.abort_interval(replacement)
    manager.abort_update_transaction(transaction)
    assert manager._update_workspace is None


def test_public_previews_and_retained_outcomes_are_defensive_and_generation_scoped() -> None:
    control = _manager(identification=False)
    control_outcome, control_record = _run_cycle(
        control,
        _sensor(),
        tick=0,
        targets=[_target()],
    )
    control_state = control.get_state()

    manager = _manager(identification=False)
    sensor = _sensor()
    transaction, cadence, indexed, allocation, handle, identity = _begin_cycle(
        manager,
        sensor,
        tick=0,
    )
    scan_counts_preview = transaction._scan_counts
    diagnostic_scan_counts = scan_counts_preview.copy()
    diagnostic_scan_counts[("diagnostic-sensor", "diagnostic-target")] = 1
    assert scan_counts_preview.copy() == {}
    side_plan = manager.update_with_receipt(
        "blue",
        [_own_unit(sensor)],
        [_target()],
        5.0,
        transaction=transaction,
        cadence_plan=cadence,
        indexed_rng=handle,
        lod_tiers={identity.observer: FogOfWarLodTier.ACTIVE},
        current_time=5.0,
        current_tick=0,
        detection_culling=False,
    )
    expected_world_view = side_plan.outcome.world_view.get_state()
    assert expected_world_view["contacts"]
    side_preview = side_plan.outcome
    side_preview.world_view.contacts.clear()
    assert side_plan.outcome.world_view.get_state() == expected_world_view

    publication = manager.prevalidate_update_transaction(
        transaction,
        (side_plan,),
    )
    publication_preview = publication.outcomes[0]
    publication_preview.world_view.contacts.clear()
    diagnostic_world_view = publication._world_views["blue"]
    diagnostic_world_view.contacts.clear()
    assert publication._world_views["blue"].get_state() == expected_world_view
    assert publication.outcomes[0].world_view.get_state() == expected_world_view

    prepared = manager.prepare_update_commit(publication)
    workspace = manager._update_workspace
    payload = manager._prepared_update_payload
    assert workspace is not None
    assert payload is not None
    side_workspace = workspace.side_workspaces["blue"]
    workspace_reference = weakref.ref(workspace)
    owner_outcome = manager._prepared_outcomes_for_owner(prepared)[0]
    assert payload.world_views is workspace.world_views
    assert payload.receipts[0] is side_workspace.receipt
    assert owner_outcome.world_view is payload.world_views["blue"]
    assert owner_outcome.receipt is side_workspace.receipt
    assert owner_outcome.witnesses[0] is side_workspace.current_detection_witnesses[0]
    assert side_plan.receipt is not side_workspace.receipt
    assert side_plan._current_detection_witnesses[0] is not side_workspace.current_detection_witnesses[0]
    assert publication.receipts[0] is side_plan.receipt
    assert prepared.receipts is publication.receipts
    assert side_plan.outcome.world_view is not owner_outcome.world_view
    assert side_plan.outcome.receipt is not owner_outcome.receipt
    assert side_plan.outcome.witnesses[0] is not owner_outcome.witnesses[0]
    assert publication.outcomes[0].world_view is not owner_outcome.world_view
    assert prepared.outcomes[0].world_view is not owner_outcome.world_view

    prepared_preview = prepared.outcomes[0]
    prepared_preview.world_view.contacts.clear()
    assert prepared.outcomes[0].world_view.get_state() == expected_world_view

    record = indexed.commit_interval(allocation)
    manager.cadence.commit_interval(cadence)
    manager.commit_prepared_update(prepared)
    committed = manager.get_state()

    for mapping_preview in (
        transaction._world_views,
        transaction._current_detection_witnesses,
        transaction._rng_state,
        transaction._intel_fusion,
        scan_counts_preview,
        publication._world_views,
        publication._current_detection_witnesses,
        publication._intel_fusion,
        side_plan._fusion_delta.tracks,
    ):
        with pytest.raises(
            RuntimeError,
            match="fog-of-war diagnostic preview is stale",
        ):
            len(mapping_preview)
    with pytest.raises(
        RuntimeError,
        match="fog-of-war diagnostic preview is stale",
    ):
        side_plan._world_view.get_state()

    del workspace
    gc.collect()
    assert workspace_reference() is None

    retained_outcomes = (
        side_plan.outcome,
        publication.outcomes[0],
        prepared.outcomes[0],
    )
    live_witnesses = manager.get_current_detection_witnesses("blue")
    expected_witnesses = tuple(witness.get_state() for witness in live_witnesses)
    expected_receipt = control_outcome.receipt
    for retained in retained_outcomes:
        assert retained.world_view.get_state() == expected_world_view
        assert retained.receipt is not side_workspace.receipt
        assert all(
            retained_witness is not live_witness
            for retained_witness, live_witness in zip(
                retained.witnesses,
                live_witnesses,
                strict=True,
            )
        )
        retained.world_view.contacts.clear()
        object.__setattr__(
            retained.receipt,
            "engine_tick",
            retained.receipt.engine_tick + 100,
        )
        object.__setattr__(
            retained.witnesses[0],
            "sensor_id",
            "mutated-retained-witness",
        )

    object.__setattr__(
        side_plan.receipt,
        "engine_tick",
        side_plan.receipt.engine_tick + 200,
    )
    object.__setattr__(
        side_plan._current_detection_witnesses[0],
        "sensor_id",
        "mutated-diagnostic-witness",
    )
    publication_witnesses = publication.witnesses
    object.__setattr__(
        publication_witnesses[0],
        "sensor_id",
        "mutated-publication-witness",
    )

    assert manager.get_state() == committed
    assert committed == control_state
    assert record == control_record
    assert side_plan.outcome.world_view.get_state() == control_outcome.world_view.get_state()
    assert side_plan.outcome.receipt == expected_receipt
    assert tuple(witness.get_state() for witness in side_plan.outcome.witnesses) == expected_witnesses
    assert tuple(witness.get_state() for witness in publication.witnesses) == expected_witnesses
    assert indexed.committed_interval_count == 1

    retained_outcomes = (
        side_plan.outcome,
        publication.outcomes[0],
        prepared.outcomes[0],
    )
    live_world_view = manager.peek_world_view("blue")
    assert live_world_view is not None
    live_contact = live_world_view.contacts["red-target"]
    live_track = live_contact.track
    assert manager.intel_fusion.get_tracks("blue")[live_track.track_id] is live_track

    def mutable_world_view_ids(world_view: SideWorldView) -> set[int]:
        contact = world_view.contacts["red-target"]
        track = contact.track
        return {
            id(world_view),
            id(world_view.contacts),
            id(contact),
            id(contact.reporting_sensors),
            id(track),
            id(track.contact_info),
            id(track.state),
            id(track.state.position),
            id(track.state.velocity),
            id(track.state.covariance),
        }

    live_graph_ids = mutable_world_view_ids(live_world_view)
    for retained in retained_outcomes:
        assert mutable_world_view_ids(retained.world_view).isdisjoint(live_graph_ids)

    live_world_view.last_update_time += 1.0
    live_contact.reporting_sensors.append("live-only")
    live_track.hits += 1
    live_track.state.position[0] += 100.0
    live_track.state.velocity[0] += 10.0
    live_track.state.covariance[0, 0] += 1.0
    for retained in (
        side_plan.outcome,
        publication.outcomes[0],
        prepared.outcomes[0],
    ):
        assert retained.world_view.get_state() == expected_world_view
    with pytest.raises(ValueError, match="foreign or stale"):
        manager._prepared_outcomes_for_owner(prepared)

    next_transaction = manager.begin_update_transaction(("blue",))
    assert next_transaction._generation != transaction._generation
    with pytest.raises(ValueError, match="stale or inactive"):
        manager.prevalidate_update_transaction(transaction, (side_plan,))
    with pytest.raises(ValueError, match="stale or inactive"):
        manager.prepare_update_commit(publication)
    with pytest.raises(ValueError, match="foreign or stale"):
        manager.validate_prepared_update_commit(prepared)
    manager.abort_update_transaction(next_transaction)
    assert manager._update_workspace is None


def test_abort_retires_private_previews_and_releases_workspace() -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    transaction, cadence, indexed, allocation, handle, identity = _begin_cycle(
        manager,
        sensor,
        tick=0,
    )
    side_plan = manager.update_with_receipt(
        "blue",
        [_own_unit(sensor)],
        [_target()],
        5.0,
        transaction=transaction,
        cadence_plan=cadence,
        indexed_rng=handle,
        lod_tiers={identity.observer: FogOfWarLodTier.ACTIVE},
        current_time=5.0,
        current_tick=0,
        detection_culling=False,
    )
    expected_outcome = side_plan.outcome
    workspace = manager._update_workspace
    assert workspace is not None
    workspace_reference = weakref.ref(workspace)

    manager.abort_update_transaction(transaction)
    manager.cadence.abort_interval(cadence)
    indexed.abort_interval(allocation)

    assert expected_outcome.world_view.contacts
    assert manager._update_workspace is None
    for mapping_preview in (
        transaction._world_views,
        transaction._current_detection_witnesses,
        transaction._rng_state,
        transaction._intel_fusion,
        side_plan._fusion_delta.tracks,
    ):
        with pytest.raises(
            RuntimeError,
            match="fog-of-war diagnostic preview is stale",
        ):
            len(mapping_preview)
    with pytest.raises(
        RuntimeError,
        match="fog-of-war diagnostic preview is stale",
    ):
        side_plan._world_view.get_state()
    with pytest.raises(RuntimeError, match="outcome workspace is unavailable"):
        side_plan.outcome

    del workspace
    gc.collect()
    assert workspace_reference() is None


def test_update_handle_rejection_precedes_full_graph_fingerprinting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    transaction, cadence, indexed, allocation, handle, identity = _begin_cycle(
        manager,
        sensor,
        tick=0,
    )
    original_fingerprint = fog_of_war_module._update_plan_fingerprint
    fingerprint_calls = 0

    def observed_fingerprint(*args: object, **kwargs: object) -> str:
        nonlocal fingerprint_calls
        fingerprint_calls += 1
        return original_fingerprint(*args, **kwargs)

    monkeypatch.setattr(
        fog_of_war_module,
        "_update_plan_fingerprint",
        observed_fingerprint,
    )

    original_owner = transaction._owner_token
    object.__setattr__(transaction, "_owner_token", object())
    calls_before_rejection = fingerprint_calls
    with pytest.raises(ValueError, match="belongs to another manager"):
        manager.prevalidate_update_transaction(transaction, ())
    assert fingerprint_calls == calls_before_rejection
    object.__setattr__(transaction, "_owner_token", original_owner)

    original_generation = transaction._generation
    object.__setattr__(transaction, "_generation", original_generation + 1)
    calls_before_rejection = fingerprint_calls
    with pytest.raises(ValueError, match="metadata was mutated"):
        manager.prevalidate_update_transaction(transaction, ())
    assert fingerprint_calls == calls_before_rejection
    object.__setattr__(transaction, "_generation", original_generation)

    side_plan = manager.update_with_receipt(
        "blue",
        [_own_unit(sensor)],
        [_target()],
        5.0,
        transaction=transaction,
        cadence_plan=cadence,
        indexed_rng=handle,
        lod_tiers={identity.observer: FogOfWarLodTier.ACTIVE},
        current_time=5.0,
        current_tick=0,
        detection_culling=False,
    )
    original_generation = side_plan._generation
    object.__setattr__(side_plan, "_generation", original_generation + 1)
    calls_before_rejection = fingerprint_calls
    with pytest.raises(ValueError, match="foreign or stale"):
        manager.prevalidate_update_transaction(transaction, (side_plan,))
    assert fingerprint_calls == calls_before_rejection
    object.__setattr__(side_plan, "_generation", original_generation)

    original_engine_tick = side_plan.receipt.engine_tick
    object.__setattr__(
        side_plan.receipt,
        "engine_tick",
        original_engine_tick + 1,
    )
    calls_before_rejection = fingerprint_calls
    with pytest.raises(ValueError, match="metadata was mutated"):
        manager.prevalidate_update_transaction(transaction, (side_plan,))
    assert fingerprint_calls == calls_before_rejection
    object.__setattr__(
        side_plan.receipt,
        "engine_tick",
        original_engine_tick,
    )

    publication = manager.prevalidate_update_transaction(
        transaction,
        (side_plan,),
    )
    original_sides = publication.reporting_sides
    mutated_sides = tuple(list(original_sides))
    assert mutated_sides is not original_sides
    object.__setattr__(publication, "reporting_sides", mutated_sides)
    calls_before_rejection = fingerprint_calls
    with pytest.raises(ValueError, match="metadata was mutated"):
        manager.prepare_update_commit(publication)
    assert fingerprint_calls == calls_before_rejection
    object.__setattr__(publication, "reporting_sides", original_sides)

    prepared = manager.prepare_update_commit(publication)
    assert prepared.receipts[0] is publication.receipts[0] is side_plan.receipt
    object.__setattr__(
        prepared.receipts[0],
        "engine_tick",
        original_engine_tick + 1,
    )
    calls_before_rejection = fingerprint_calls
    with pytest.raises(ValueError, match="publication metadata was mutated"):
        manager.validate_prepared_update_commit(prepared)
    assert fingerprint_calls == calls_before_rejection
    object.__setattr__(
        prepared.receipts[0],
        "engine_tick",
        original_engine_tick,
    )
    original_generation = prepared._generation
    object.__setattr__(prepared, "_generation", original_generation + 1)
    calls_before_rejection = fingerprint_calls
    with pytest.raises(ValueError, match="foreign or stale"):
        manager.validate_prepared_update_commit(prepared)
    assert fingerprint_calls == calls_before_rejection
    object.__setattr__(prepared, "_generation", original_generation)

    indexed.abort_interval(allocation)
    manager.cadence.abort_interval(cadence)
    manager.abort_update_transaction(transaction)
    assert manager._update_workspace is None


def test_update_handles_reject_scalar_aliases_and_equal_binding_substitutions() -> None:
    class _ReportingSideAlias(str):
        pass

    class _ReceiptIntegerAlias(int):
        pass

    def equal_distinct_text(value: str) -> str:
        replacement = (" " + value)[1:]
        assert replacement == value
        assert replacement is not value
        return replacement

    manager = _manager(identification=False)
    baseline_state = _live_fow_authority_state(manager)
    sensor = _sensor()
    transaction, cadence, indexed, allocation, handle, identity = _begin_cycle(
        manager,
        sensor,
        tick=1,
    )

    original_generation = transaction._generation
    assert original_generation == 1
    object.__setattr__(transaction, "_generation", True)
    with pytest.raises(ValueError, match="metadata was mutated"):
        manager.prevalidate_update_transaction(transaction, ())
    object.__setattr__(transaction, "_generation", original_generation)

    original_seal = transaction._fingerprint
    object.__setattr__(
        transaction,
        "_fingerprint",
        equal_distinct_text(original_seal),
    )
    with pytest.raises(ValueError, match="metadata was mutated"):
        manager.prevalidate_update_transaction(transaction, ())
    object.__setattr__(transaction, "_fingerprint", original_seal)

    side_plan = manager.update_with_receipt(
        "blue",
        [_own_unit(sensor)],
        [_target()],
        5.0,
        transaction=transaction,
        cadence_plan=cadence,
        indexed_rng=handle,
        lod_tiers={identity.observer: FogOfWarLodTier.ACTIVE},
        current_time=10.0,
        current_tick=1,
        detection_culling=False,
    )
    workspace = manager._update_workspace
    assert workspace is not None
    side_workspace = workspace.side_workspaces["blue"]
    authoritative_receipt = side_workspace.receipt

    original_side = side_plan.reporting_side
    object.__setattr__(
        side_plan,
        "reporting_side",
        _ReportingSideAlias(original_side),
    )
    with pytest.raises(ValueError, match="metadata was mutated"):
        manager.prevalidate_update_transaction(transaction, (side_plan,))
    object.__setattr__(side_plan, "reporting_side", original_side)

    original_generation = side_plan._generation
    object.__setattr__(side_plan, "_generation", True)
    with pytest.raises(ValueError, match="foreign or stale"):
        manager.prevalidate_update_transaction(transaction, (side_plan,))
    object.__setattr__(side_plan, "_generation", original_generation)

    original_observers = side_plan.receipt.observers
    assert original_observers == 1
    for alias in (True, _ReceiptIntegerAlias(original_observers)):
        object.__setattr__(side_plan.receipt, "observers", alias)
        assert side_plan.receipt == authoritative_receipt
        with pytest.raises(ValueError, match="metadata was mutated"):
            manager.prevalidate_update_transaction(transaction, (side_plan,))
        object.__setattr__(side_plan.receipt, "observers", original_observers)

    original_track_counter = side_plan._fusion_delta.track_counter
    assert original_track_counter == 0
    object.__setattr__(side_plan._fusion_delta, "track_counter", False)
    with pytest.raises(ValueError, match="fusion metadata was mutated"):
        manager.prevalidate_update_transaction(transaction, (side_plan,))
    object.__setattr__(
        side_plan._fusion_delta,
        "track_counter",
        original_track_counter,
    )

    original_seal = side_plan._fingerprint
    object.__setattr__(
        side_plan,
        "_fingerprint",
        equal_distinct_text(original_seal),
    )
    with pytest.raises(ValueError, match="metadata was mutated"):
        manager.prevalidate_update_transaction(transaction, (side_plan,))
    object.__setattr__(side_plan, "_fingerprint", original_seal)

    publication = manager.prevalidate_update_transaction(
        transaction,
        (side_plan,),
    )
    original_generation = publication._generation
    object.__setattr__(publication, "_generation", True)
    with pytest.raises(ValueError, match="foreign or stale"):
        manager.prepare_update_commit(publication)
    object.__setattr__(publication, "_generation", original_generation)

    original_seal = publication._fingerprint
    object.__setattr__(
        publication,
        "_fingerprint",
        equal_distinct_text(original_seal),
    )
    with pytest.raises(ValueError, match="metadata was mutated"):
        manager.prepare_update_commit(publication)
    object.__setattr__(publication, "_fingerprint", original_seal)

    object.__setattr__(side_plan.receipt, "observers", True)
    assert publication.receipts[0] == authoritative_receipt
    with pytest.raises(ValueError, match="metadata was mutated"):
        manager.prepare_update_commit(publication)
    object.__setattr__(side_plan.receipt, "observers", original_observers)

    scan_counts = publication._scan_counts
    original_scan_seal = scan_counts._fingerprint
    object.__setattr__(
        scan_counts,
        "_fingerprint",
        equal_distinct_text(original_scan_seal),
    )
    with pytest.raises(ValueError, match="scan-count metadata was mutated"):
        manager.prepare_update_commit(publication)
    object.__setattr__(scan_counts, "_fingerprint", original_scan_seal)

    prepared = manager.prepare_update_commit(publication)
    original_generation = prepared._generation
    object.__setattr__(prepared, "_generation", True)
    with pytest.raises(ValueError, match="foreign or stale"):
        manager.validate_prepared_update_commit(prepared)
    object.__setattr__(prepared, "_generation", original_generation)

    original_sides = prepared.reporting_sides
    replacement_sides = tuple(list(original_sides))
    assert replacement_sides == original_sides
    assert replacement_sides is not original_sides
    object.__setattr__(prepared, "reporting_sides", replacement_sides)
    with pytest.raises(ValueError, match="commit plan metadata was mutated"):
        manager.validate_prepared_update_commit(prepared)
    object.__setattr__(prepared, "reporting_sides", original_sides)

    original_receipts = prepared.receipts
    replacement_receipts = tuple(list(original_receipts))
    assert replacement_receipts == original_receipts
    assert replacement_receipts is not original_receipts
    object.__setattr__(prepared, "receipts", replacement_receipts)
    with pytest.raises(ValueError, match="commit plan metadata was mutated"):
        manager.validate_prepared_update_commit(prepared)
    object.__setattr__(prepared, "receipts", original_receipts)

    indexed.abort_interval(allocation)
    manager.cadence.abort_interval(cadence)
    manager.abort_update_transaction(transaction)
    assert manager._update_workspace is None
    assert _live_fow_authority_state(manager) == baseline_state


def test_update_handle_receipt_seal_rejects_nested_recovery_scalar_aliases() -> None:
    class _RecoveryIntegerAlias(int):
        pass

    manager = _manager(identification=False)
    sensor = _sensor()
    for tick in (0, 1):
        _run_cycle(
            manager,
            sensor,
            tick=tick,
            targets=[_target()],
            native_period=2,
            lod_period=1,
        )
    baseline_state = _live_fow_authority_state(manager)
    transaction, cadence, indexed, allocation, handle, identity = _begin_cycle(
        manager,
        sensor,
        tick=2,
        native_period=2,
        lod_period=1,
    )
    side_plan = manager.update_with_receipt(
        "blue",
        [_own_unit(sensor)],
        [_target()],
        5.0,
        transaction=transaction,
        cadence_plan=cadence,
        indexed_rng=handle,
        lod_tiers={identity.observer: FogOfWarLodTier.ACTIVE},
        current_time=15.0,
        current_tick=2,
        detection_culling=False,
    )
    workspace = manager._update_workspace
    assert workspace is not None
    authoritative_receipt = workspace.side_workspaces["blue"].receipt
    public_bucket = side_plan.receipt.cadence.native_recoveries_by_period[0]
    authoritative_bucket = authoritative_receipt.cadence.native_recoveries_by_period[0]
    original_admissions = public_bucket.recovery_admissions
    assert original_admissions == authoritative_bucket.recovery_admissions == 1

    for alias in (True, _RecoveryIntegerAlias(original_admissions)):
        object.__setattr__(public_bucket, "recovery_admissions", alias)
        assert side_plan.receipt == authoritative_receipt
        with pytest.raises(ValueError, match="metadata was mutated"):
            manager.prevalidate_update_transaction(transaction, (side_plan,))
        object.__setattr__(
            public_bucket,
            "recovery_admissions",
            original_admissions,
        )

    publication = manager.prevalidate_update_transaction(
        transaction,
        (side_plan,),
    )
    object.__setattr__(public_bucket, "recovery_admissions", True)
    with pytest.raises(ValueError, match="metadata was mutated"):
        manager.prepare_update_commit(publication)
    object.__setattr__(
        public_bucket,
        "recovery_admissions",
        original_admissions,
    )

    prepared = manager.prepare_update_commit(publication)
    object.__setattr__(public_bucket, "recovery_admissions", True)
    with pytest.raises(ValueError, match="publication metadata was mutated"):
        manager.validate_prepared_update_commit(prepared)
    object.__setattr__(
        public_bucket,
        "recovery_admissions",
        original_admissions,
    )

    indexed.abort_interval(allocation)
    manager.cadence.abort_interval(cadence)
    manager.abort_update_transaction(transaction)
    assert manager._update_workspace is None
    assert _live_fow_authority_state(manager) == baseline_state


def test_publication_witness_extraction_does_not_copy_world_view_outcomes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Immutable staged evidence is readable without outcome materialization."""
    manager = _manager(identification=False)
    sensor = _sensor()
    transaction, cadence, indexed, allocation, handle, identity = _begin_cycle(
        manager,
        sensor,
        tick=0,
    )
    side_plan = manager.update_with_receipt(
        "blue",
        [_own_unit(sensor)],
        [_target()],
        5.0,
        transaction=transaction,
        cadence_plan=cadence,
        indexed_rng=handle,
        lod_tiers={identity.observer: FogOfWarLodTier.ACTIVE},
        current_time=5.0,
        current_tick=0,
        detection_culling=False,
    )
    publication = manager.prevalidate_update_transaction(
        transaction,
        (side_plan,),
    )
    assert isinstance(publication, FogOfWarPublicationPlan)
    expected_witnesses = side_plan.outcome.witnesses
    assert expected_witnesses
    original_deepcopy = copy.deepcopy

    def _reject_world_view_copy(
        value: object,
        *args: object,
        **kwargs: object,
    ) -> object:
        if isinstance(value, SideWorldView):
            raise AssertionError("publication evidence copied a side world view")
        return original_deepcopy(value, *args, **kwargs)

    monkeypatch.setattr(
        fog_of_war_module.copy,
        "deepcopy",
        _reject_world_view_copy,
    )

    assert publication.witnesses == expected_witnesses
    assert publication.receipts == (side_plan.receipt,)

    indexed.abort_interval(allocation)
    manager.cadence.abort_interval(cadence)
    manager.abort_update_transaction(transaction)


def test_later_side_failure_leaves_public_fog_and_fusion_unpublished() -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    before_fog = manager.get_state()
    before_fusion = manager.intel_fusion.get_state()
    before_snapshots = tuple(manager.snapshot_side(side) for side in ("blue", "red"))
    transaction = manager.begin_update_transaction(("blue", "red"))
    identities = {
        "blue": _attachment_identity(sensor),
        "red": _attachment_identity(
            sensor,
            unit_id="red-observer",
            side="red",
        ),
    }
    cadence_plan = manager.cadence.stage_interval(
        [
            TacticalCadenceAttachment(
                identity=identities[side],
                native_period=1,
                lod_period=1,
                operational=True,
            )
            for side in ("blue", "red")
        ]
    )
    indexed = IndexedFOWRNG(118_701)
    allocation = indexed.begin_interval(
        module=ModuleId.DETECTION,
        engine_tick=0,
        reporting_sides=("blue", "red"),
    )
    blue_handle = allocation.acquire_side("blue")
    red_handle = allocation.acquire_side("red")
    blue_plan = manager.update_with_receipt(
        "blue",
        [_own_unit(sensor)],
        [_target()],
        5.0,
        transaction=transaction,
        cadence_plan=cadence_plan,
        indexed_rng=blue_handle,
        lod_tiers={identities["blue"].observer: FogOfWarLodTier.ACTIVE},
        current_time=5.0,
        current_tick=0,
        detection_culling=False,
    )
    assert blue_plan.outcome.witnesses
    assert manager.snapshot_side("blue").present is False
    assert manager.get_current_detection_witnesses("blue") == ()
    assert manager.intel_fusion.get_state() == before_fusion

    with pytest.raises(ValueError, match="duplicate ID"):
        manager.update_with_receipt(
            "red",
            [_own_unit(sensor, unit_id="red-observer")],
            [_target("duplicate"), _target("duplicate")],
            5.0,
            transaction=transaction,
            cadence_plan=cadence_plan,
            indexed_rng=red_handle,
            lod_tiers={
                identities["red"].observer: FogOfWarLodTier.ACTIVE,
            },
            current_time=5.0,
            current_tick=0,
            detection_culling=False,
        )
    indexed.abort_interval(allocation)
    manager.cadence.abort_interval(cadence_plan)

    assert manager._update_workspace is None
    assert tuple(manager.snapshot_side(side) for side in ("blue", "red")) == before_snapshots
    assert manager.intel_fusion.get_state() == before_fusion
    with pytest.raises(RuntimeError, match="poisoned update transaction"):
        manager.get_state()
    assert before_fog["world_views"] == {}


def test_soa_selection_receipts_the_actual_side_vector_build() -> None:
    manager = _manager(identification=False)
    outcome, _record = _run_cycle(
        manager,
        _sensor(),
        tick=0,
        targets=[_target()],
        soa_selection=True,
    )

    assert outcome.receipt.selection.soa_vector_builds == 1
    assert outcome.receipt.selection.soa_vector_queries == 1
    assert outcome.receipt.selection.soa_vector_admitted_targets == 1
    assert outcome.receipt.selection.brute_force_cycles == 0


def test_snapshot_side_is_immutable_ordered_and_non_creating() -> None:
    manager = _manager(identification=False)
    before = manager.get_state()

    absent = manager.snapshot_side("blue")

    assert absent.reporting_side == "blue"
    assert absent.present is False
    assert absent.identities == ()
    assert manager.get_state() == before

    outcome, _record = _run_cycle(
        manager,
        _sensor(),
        tick=0,
        targets=[_target("z-target"), _target("a-target")],
    )
    snapshot = manager.snapshot_side("blue")
    assert outcome.witnesses == manager.get_current_detection_witnesses("blue")
    assert tuple(identity.target_id for identity in snapshot.identities) == (
        "a-target",
        "z-target",
    )


def test_legacy_fog_restore_rejects_mixed_modern_cadence_state() -> None:
    manager = _manager(identification=False)
    modern = manager.get_state()

    with pytest.raises(ValueError, match="cannot supply modern cadence"):
        manager.stage_state(modern, allow_legacy_state=True)


def test_legacy_fog_restore_rejects_mixed_modern_scan_count_state() -> None:
    manager = _manager(identification=False)
    mixed = manager.get_state()
    del mixed["cadence"]

    with pytest.raises(ValueError, match="invalid topology"):
        manager.stage_state(mixed, allow_legacy_state=True)


def test_legacy_four_key_fog_restore_preserves_contacts_tracks_and_witnesses() -> None:
    source = _manager(identification=False)
    sensor = _sensor()
    _outcome, _record = _run_cycle(
        source,
        sensor,
        tick=0,
        targets=[_target()],
    )
    source_state = source.get_state()
    legacy_state = copy.deepcopy(source_state)
    del legacy_state["cadence"]
    del legacy_state["scan_counts"]
    del legacy_state["observer_track_supports"]
    target = _manager(
        identification=False,
        complete_from_tick_zero=False,
    )
    binding = FogOfWarSensorBinding(
        unit_id="blue-observer",
        side="blue",
        source_equipment_index=7,
        sensor_id=sensor.sensor_id,
        modeled_role=SensorModeledRole.VISUAL_OBSERVATION.value,
        sensor_type=sensor.sensor_type.name,
    )

    plan = target.stage_state(
        legacy_state,
        expected_sides={"blue"},
        expected_target_sides={
            "blue-observer": "blue",
            "red-target": "red",
        },
        expected_sensor_bindings=(binding,),
        allow_legacy_state=True,
    )
    target.commit_state(plan)
    restored = target.get_state()

    assert restored["world_views"] == source_state["world_views"]
    assert restored["current_detection_witnesses"] == source_state["current_detection_witnesses"]
    assert restored["intel_fusion"] == source_state["intel_fusion"]
    assert restored["scan_counts"] == {}
    assert (
        restored["cadence"]
        == TacticalCadenceScheduler(
            complete_from_tick_zero=False,
        ).get_state()
    )


def test_cadence_completeness_promotion_rejects_during_fog_stage() -> None:
    source = _manager(identification=False)
    target = _manager(
        identification=False,
        complete_from_tick_zero=False,
    )
    state = source.get_state()
    before_fusion = target.intel_fusion.get_state()

    with pytest.raises(ValueError, match="completeness cannot be promoted"):
        target.stage_state(state)

    assert target.intel_fusion.get_state() == before_fusion
    assert target.snapshot_side("blue").present is False


def test_cadence_restore_binding_requires_exact_runtime_roster_and_periods() -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    _outcome, _record = _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[],
    )
    sensor_binding = FogOfWarSensorBinding(
        unit_id="blue-observer",
        side="blue",
        source_equipment_index=7,
        sensor_id=sensor.sensor_id,
        modeled_role=SensorModeledRole.VISUAL_OBSERVATION.value,
        sensor_type=sensor.sensor_type.name,
    )
    cadence_binding = FogOfWarCadenceBinding(
        identity=sensor_binding.cadence_identity,
        native_period=1,
        current_lod_period=1,
    )
    unused_roster_binding = FogOfWarSensorBinding(
        unit_id="blue-unused",
        side="blue",
        source_equipment_index=8,
        sensor_id=sensor.sensor_id,
        modeled_role=SensorModeledRole.VISUAL_OBSERVATION.value,
        sensor_type=sensor.sensor_type.name,
    )
    full_sensor_bindings = (sensor_binding, unused_roster_binding)
    native_phase_bindings = tuple(
        FogOfWarNativePhaseBinding(
            identity=binding.cadence_identity,
            native_period=1,
        )
        for binding in full_sensor_bindings
    )
    plan = manager.stage_state(
        manager.get_state(),
        expected_sides={"blue"},
        expected_target_sides={
            "blue-observer": "blue",
            "blue-unused": "blue",
        },
        expected_sensor_bindings=full_sensor_bindings,
        expected_cadence_sensor_bindings=(sensor_binding,),
        expected_cadence_bindings=(cadence_binding,),
        expected_native_phase_bindings=native_phase_bindings,
    )
    manager.validate_cadence_restore_bindings(
        plan,
        expected_sensor_bindings=full_sensor_bindings,
        expected_cadence_sensor_bindings=(sensor_binding,),
        expected_cadence_bindings=(cadence_binding,),
        expected_native_phase_bindings=native_phase_bindings,
    )

    wrong_lod = FogOfWarCadenceBinding(
        identity=sensor_binding.cadence_identity,
        native_period=1,
        current_lod_period=5,
    )
    with pytest.raises(ValueError, match="LOD cadence period"):
        manager.validate_cadence_restore_bindings(
            plan,
            expected_sensor_bindings=full_sensor_bindings,
            expected_cadence_sensor_bindings=(sensor_binding,),
            expected_cadence_bindings=(wrong_lod,),
            expected_native_phase_bindings=native_phase_bindings,
        )

    wrong_native_period = (
        FogOfWarNativePhaseBinding(
            identity=sensor_binding.cadence_identity,
            native_period=2,
        ),
        native_phase_bindings[1],
    )
    with pytest.raises(
        ValueError,
        match="native phase period disagrees",
    ):
        manager.validate_cadence_restore_bindings(
            plan,
            expected_sensor_bindings=full_sensor_bindings,
            expected_cadence_sensor_bindings=(sensor_binding,),
            expected_cadence_bindings=(cadence_binding,),
            expected_native_phase_bindings=wrong_native_period,
        )

    with pytest.raises(ValueError, match="complete runtime sensor roster"):
        manager.validate_cadence_restore_bindings(
            plan,
            expected_sensor_bindings=full_sensor_bindings,
            expected_cadence_sensor_bindings=(sensor_binding,),
            expected_cadence_bindings=(cadence_binding,),
            expected_native_phase_bindings=(native_phase_bindings[0],),
        )
