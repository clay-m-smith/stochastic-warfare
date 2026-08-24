"""Focused contracts for Phase 118 observer track support."""

from __future__ import annotations

import copy
import json
import math
from dataclasses import FrozenInstanceError, replace

import numpy as np
import pytest

from stochastic_warfare.core.types import Domain
from stochastic_warfare.detection.cadence import TacticalAttachmentIdentity
from stochastic_warfare.detection.estimation import (
    EstimationConfig,
    StateEstimator,
    Track,
    TrackState,
)
from stochastic_warfare.detection.identification import ContactInfo, ContactLevel
from stochastic_warfare.detection.observer_support import (
    OBSERVER_TRACK_SUPPORT_RADAR_ROLES,
    ObserverTrackSupportEvidence,
    ObserverTrackSupportIdentity,
    ObserverTrackSupportState,
    observer_track_support_evidence_from_state,
    observer_track_support_evidence_to_state,
    observer_track_support_role_is_supported,
    observer_track_support_state_from_state,
    observer_track_support_state_to_state,
)
from stochastic_warfare.detection.sensors import SensorType
from stochastic_warfare.simulation.loadouts import (
    SensorModeledRole,
    WeaponModeledRole,
)
from stochastic_warfare.simulation.tactical_targeting import (
    ContactSource,
    EffectiveRangeBasis,
    FireControlSource,
    TacticalTargetingDecision,
    TargetingDisposition,
    targeting_decision_from_state,
    targeting_decision_to_state,
)

_COVARIANCE = (
    (4.0, 0.0, 0.0, 0.0),
    (0.0, 4.0, 0.0, 0.0),
    (0.0, 0.0, 4.0, 0.0),
    (0.0, 0.0, 0.0, 4.0),
)
_SUPPORTED_ROLES = frozenset(
    {
        SensorModeledRole.AIRBORNE_FIRE_CONTROL_RADAR,
        SensorModeledRole.AIRBORNE_GROUND_FIRE_CONTROL_RADAR,
        SensorModeledRole.AIRBORNE_MULTI_DOMAIN_FIRE_CONTROL_RADAR,
        SensorModeledRole.FIRE_CONTROL_RADAR,
        SensorModeledRole.GROUND_AIR_DEFENSE_FIRE_CONTROL_RADAR,
        SensorModeledRole.NAVAL_FIRE_CONTROL_RADAR,
        SensorModeledRole.NAVAL_AIR_DEFENSE_FIRE_CONTROL_RADAR,
    }
)


def _identity(
    *,
    source_equipment_index: int = 3,
    modeled_role: SensorModeledRole = SensorModeledRole.FIRE_CONTROL_RADAR,
    reporting_side: str = "blue",
    observer_unit_id: str = "blue-1",
    target_id: str = "red-1",
) -> ObserverTrackSupportIdentity:
    return ObserverTrackSupportIdentity(
        attachment_identity=TacticalAttachmentIdentity(
            reporting_side=reporting_side,
            observer_unit_id=observer_unit_id,
            source_equipment_index=source_equipment_index,
            sensor_id="fire-control-radar",
            modeled_role=modeled_role.value,
        ),
        target_id=target_id,
    )


def _support_state(**overrides: object) -> ObserverTrackSupportState:
    values: dict[str, object] = {
        "identity": _identity(),
        "fusion_track_id": "fow-track-00000001",
        "sensor_type": SensorType.RADAR,
        "observation_ordinal": 2,
        "observation_time_s": 10.0,
        "native_period": 4,
        "native_phase_residue": 2,
        "native_due_ordinal": 6,
        "position_m": (100.0, 200.0),
        "velocity_mps": (10.0, -5.0),
        "covariance": _COVARIANCE,
    }
    values.update(overrides)
    return ObserverTrackSupportState(**values)  # type: ignore[arg-type]


def _evidence(**overrides: object) -> ObserverTrackSupportEvidence:
    state = _support_state()
    values: dict[str, object] = {
        "identity": state.identity,
        "fusion_track_id": state.fusion_track_id,
        "sensor_type": state.sensor_type,
        "observation_ordinal": state.observation_ordinal,
        "observation_time_s": state.observation_time_s,
        "native_period": state.native_period,
        "native_phase_residue": state.native_phase_residue,
        "native_due_ordinal": state.native_due_ordinal,
        "projection_ordinal": 3,
        "projection_time_s": 12.0,
        "position_m": (120.0, 190.0),
        "velocity_mps": (10.0, -5.0),
        "covariance": (
            (36.0, 0.0, 24.0, 0.0),
            (0.0, 36.0, 0.0, 24.0),
            (24.0, 0.0, 20.0, 0.0),
            (0.0, 24.0, 0.0, 20.0),
        ),
    }
    values.update(overrides)
    return ObserverTrackSupportEvidence(**values)  # type: ignore[arg-type]


def _support_decision(**overrides: object) -> TacticalTargetingDecision:
    values: dict[str, object] = {
        "engine_tick": 8,
        "logical_time_s": 12.0,
        "battle_id": "battle-alpha",
        "ordinal": 0,
        "shooter_id": "blue-1",
        "shooter_side": "blue",
        "shooter_domain": Domain.GROUND,
        "target_id": "red-1",
        "target_side": "red",
        "target_domain": Domain.GROUND,
        "distance_m": 200.0,
        "weapon_id": "direct-gun",
        "weapon_source_equipment_index": 2,
        "weapon_modeled_role": WeaponModeledRole.GROUND_DIRECT_FIRE,
        "ammunition_id": "direct-shell",
        "physical_max_range_m": 1_000.0,
        "predictive_effective_range_m": 800.0,
        "effective_range_basis": EffectiveRangeBasis.AUTHORED,
        "legacy_derived_reference_range_m": 800.0,
        "contact_source": ContactSource.FOW_OBSERVER_TRACK_SUPPORT,
        "observing_unit_id": "blue-1",
        "contact_sensor_source_equipment_index": 3,
        "contact_sensor_id": "fire-control-radar",
        "contact_sensor_modeled_role": SensorModeledRole.FIRE_CONTROL_RADAR,
        "contact_time_s": 12.0,
        "contact_range_m": 1_000.0,
        "visibility_bound_m": 1_000.0,
        "sensing_sensor_source_equipment_index": 3,
        "sensing_sensor_id": "fire-control-radar",
        "sensing_sensor_modeled_role": SensorModeledRole.FIRE_CONTROL_RADAR,
        "sensing_range_m": 1_000.0,
        "fire_control_source": FireControlSource.SENSOR_ATTACHMENT,
        "fire_control_sensor_source_equipment_index": 3,
        "fire_control_sensor_id": "fire-control-radar",
        "fire_control_sensor_modeled_role": SensorModeledRole.FIRE_CONTROL_RADAR,
        "fire_control_range_m": 1_000.0,
        "disposition": TargetingDisposition.VALID_STANDOFF_HOLD,
        "authorized_standoff_m": 800.0,
        "hold_authorized": True,
        "engagement_solution_valid": True,
        "sensing_aware_standoff_enabled": True,
        "fog_of_war_enabled": True,
        "observer_track_support": _evidence(),
    }
    values.update(overrides)
    return TacticalTargetingDecision(**values)  # type: ignore[arg-type]


def test_phase118_declares_exact_closed_radar_support_policy() -> None:
    assert ContactSource.FOW_OBSERVER_TRACK_SUPPORT.value == ("FOW_OBSERVER_TRACK_SUPPORT")
    assert OBSERVER_TRACK_SUPPORT_RADAR_ROLES == _SUPPORTED_ROLES
    for role in SensorModeledRole:
        assert observer_track_support_role_is_supported(
            sensor_type=SensorType.RADAR,
            modeled_role=role,
        ) is (role in _SUPPORTED_ROLES)
    for role in _SUPPORTED_ROLES:
        for sensor_type in SensorType:
            if sensor_type is not SensorType.RADAR:
                assert not observer_track_support_role_is_supported(
                    sensor_type=sensor_type,
                    modeled_role=role,
                )


def test_support_identity_is_exact_non_overwriting_and_immutable() -> None:
    first = _identity(source_equipment_index=3)
    second = _identity(source_equipment_index=4)

    assert first.key == (
        "blue",
        "blue-1",
        3,
        "fire-control-radar",
        "fire_control_radar",
        "red-1",
    )
    assert first.key != second.key
    assert first.sort_key() < second.sort_key()
    with pytest.raises(FrozenInstanceError):
        first.target_id = "red-2"  # type: ignore[misc]


def test_support_projection_is_deterministic_rng_free_and_conservative() -> None:
    state = _support_state()

    first = state.project(
        projection_ordinal=3,
        projection_time_s=12.0,
        process_noise_std_mps2=2.0,
    )
    second = state.project(
        projection_ordinal=3,
        projection_time_s=12.0,
        process_noise_std_mps2=2.0,
    )

    assert first == second == _evidence()
    assert first.position_m == (120.0, 190.0)
    assert first.velocity_mps == (10.0, -5.0)
    assert first.position_uncertainty_m == pytest.approx(math.sqrt(72.0))
    assert first.is_within_limits(
        observer_easting_m=0.0,
        observer_northing_m=0.0,
        reach_m=250.0,
        max_position_uncertainty_m=10_000.0,
    )
    assert not first.is_within_limits(
        observer_easting_m=0.0,
        observer_northing_m=0.0,
        reach_m=230.0,
        max_position_uncertainty_m=10_000.0,
    )


def test_support_projection_matches_the_production_estimator_process_model() -> None:
    state = _support_state()
    projected = state.project(
        projection_ordinal=3,
        projection_time_s=12.0,
        process_noise_std_mps2=2.0,
    )
    track = Track(
        state.fusion_track_id,
        state.identity.attachment_identity.reporting_side,
        ContactInfo(ContactLevel.DETECTED, None, None, None, 1.0),
        TrackState(
            position=np.asarray(state.position_m, dtype=np.float64),
            velocity=np.asarray(state.velocity_mps, dtype=np.float64),
            covariance=np.asarray(state.covariance, dtype=np.float64),
            last_update_time=state.observation_time_s,
        ),
    )
    estimator = StateEstimator(
        rng=np.random.Generator(np.random.PCG64(118)),
        config=EstimationConfig(process_noise_std=2.0),
    )

    estimator.predict(track, dt=2.0)

    np.testing.assert_array_equal(track.state.position, projected.position_m)
    np.testing.assert_array_equal(track.state.velocity, projected.velocity_mps)
    np.testing.assert_array_equal(track.state.covariance, projected.covariance)


def test_period_one_support_has_no_coasting_interval() -> None:
    support = _support_state(
        observation_ordinal=2,
        native_period=1,
        native_phase_residue=0,
        native_due_ordinal=3,
    )

    with pytest.raises(ValueError, match="before native due"):
        support.project(
            projection_ordinal=3,
            projection_time_s=12.0,
            process_noise_std_mps2=2.0,
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"sensor_type": SensorType.THERMAL}, "seven supported radar roles"),
        (
            {"identity": _identity(modeled_role=SensorModeledRole.AIR_SEARCH_RADAR)},
            "seven supported radar roles",
        ),
        ({"native_due_ordinal": 7}, "exact next native deadline"),
        ({"observation_ordinal": True}, "unsigned 64-bit"),
        ({"position_m": (float("nan"), 0.0)}, "finite number"),
        (
            {
                "covariance": (
                    (4.0, 1.0, 0.0, 0.0),
                    (0.0, 4.0, 0.0, 0.0),
                    (0.0, 0.0, 4.0, 0.0),
                    (0.0, 0.0, 0.0, 4.0),
                )
            },
            "symmetric",
        ),
        (
            {
                "covariance": (
                    (1.0, 2.0, 0.0, 0.0),
                    (2.0, 1.0, 0.0, 0.0),
                    (0.0, 0.0, 1.0, 0.0),
                    (0.0, 0.0, 0.0, 1.0),
                )
            },
            "positive semidefinite",
        ),
    ],
)
def test_support_state_rejects_invalid_policy_chronology_and_covariance(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _support_state(**changes)


def test_support_state_and_evidence_codecs_are_strict_json_and_lossless() -> None:
    state = _support_state()
    evidence = _evidence()

    state_payload = observer_track_support_state_to_state(state)
    evidence_payload = observer_track_support_evidence_to_state(evidence)
    json.dumps(state_payload)
    json.dumps(evidence_payload)

    assert observer_track_support_state_from_state(copy.deepcopy(state_payload)) == state
    assert observer_track_support_evidence_from_state(copy.deepcopy(evidence_payload)) == evidence

    state_payload["unexpected"] = True
    with pytest.raises(ValueError, match="invalid key topology"):
        observer_track_support_state_from_state(state_payload)
    evidence_payload["identity"]["unexpected"] = True
    with pytest.raises(ValueError, match="invalid key topology"):
        observer_track_support_evidence_from_state(evidence_payload)


def test_support_backed_decision_is_distinct_typed_and_json_lossless() -> None:
    decision = _support_decision()

    assert decision.can_hold
    assert decision.contact_source is ContactSource.FOW_OBSERVER_TRACK_SUPPORT
    assert decision.observer_track_support == _evidence()
    payload = targeting_decision_to_state(decision)
    json.dumps(payload)
    assert targeting_decision_from_state(copy.deepcopy(payload)) == decision

    ordinary_payload = targeting_decision_to_state(
        replace(
            decision,
            contact_source=ContactSource.FOW_OBSERVER_WITNESS,
            contact_range_m=decision.distance_m,
            sensing_range_m=decision.distance_m,
            authorized_standoff_m=decision.distance_m,
            observer_track_support=None,
        )
    )
    assert ordinary_payload["observer_track_support"] is None


def test_support_backed_decision_codec_rejects_corrupt_topology() -> None:
    missing = targeting_decision_to_state(_support_decision())
    del missing["observer_track_support"]
    with pytest.raises(ValueError, match="invalid key topology"):
        targeting_decision_from_state(missing)

    nested = targeting_decision_to_state(_support_decision())
    nested["observer_track_support"]["unexpected"] = True
    with pytest.raises(ValueError, match="invalid key topology"):
        targeting_decision_from_state(nested)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"observer_track_support": None}, "requires typed support evidence"),
        (
            {
                "observer_track_support": _evidence(
                    identity=_identity(reporting_side="green"),
                )
            },
            "identity must match",
        ),
        (
            {
                "observer_track_support": _evidence(
                    identity=_identity(observer_unit_id="blue-2"),
                )
            },
            "identity must match",
        ),
        (
            {
                "observer_track_support": _evidence(
                    identity=_identity(target_id="red-2"),
                )
            },
            "identity must match",
        ),
        (
            {
                "observer_track_support": _evidence(
                    identity=_identity(source_equipment_index=4),
                )
            },
            "identity must match",
        ),
        (
            {"observer_track_support": _evidence(projection_time_s=11.0)},
            "projection must match logical time",
        ),
        (
            {
                "observer_track_support": _evidence(observation_time_s=12.0),
            },
            "observation must precede",
        ),
        ({"fog_of_war_enabled": False}, "FOW contact cannot appear"),
        (
            {
                "contact_source": ContactSource.FOW_OBSERVER_WITNESS,
            },
            "witness cannot carry observer track support",
        ),
        (
            {
                "contact_source": ContactSource.NON_FOW_LOCAL_OBSERVATION,
                "fog_of_war_enabled": False,
            },
            "requires its distinct contact source",
        ),
    ],
)
def test_support_backed_decision_requires_exact_bound_evidence(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _support_decision(**changes)


def test_support_backed_decision_requires_same_attachment_fire_control() -> None:
    assert _support_decision().can_engage

    with pytest.raises(ValueError, match="sensor-attachment fire control"):
        _support_decision(
            fire_control_source=FireControlSource.DIRECT_VISUAL,
            fire_control_sensor_source_equipment_index=None,
            fire_control_sensor_id=None,
            fire_control_sensor_modeled_role=None,
        )
    with pytest.raises(ValueError, match="same fire-control attachment"):
        _support_decision(fire_control_sensor_source_equipment_index=4)


def test_current_witness_cross_interval_rejection_remains_unchanged() -> None:
    decision = _support_decision()
    with pytest.raises(ValueError, match="same interval"):
        replace(
            decision,
            contact_source=ContactSource.FOW_OBSERVER_WITNESS,
            contact_time_s=11.0,
            contact_range_m=decision.distance_m,
            sensing_range_m=decision.distance_m,
            authorized_standoff_m=decision.distance_m,
            observer_track_support=None,
        )
