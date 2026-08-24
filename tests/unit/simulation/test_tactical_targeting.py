"""Behavioral tests for the Phase 115 tactical-targeting boundary."""

from __future__ import annotations

import copy
import json
import math
import sys
from dataclasses import FrozenInstanceError, replace

import pytest

from stochastic_warfare.core.types import Domain
from stochastic_warfare.detection.sensors import SensorType
from stochastic_warfare.detection.fog_of_war import ObserverDetectionWitness
from stochastic_warfare.simulation.loadouts import (
    SensorModeledRole,
    WeaponModeledRole,
)
from stochastic_warfare.simulation.tactical_targeting import (
    ContactSource,
    EffectiveRangeBasis,
    EffectiveRangeEvidence,
    FireControlSource,
    ObserverDetectionWitnessView,
    TacticalEngagementRevalidationOutcome,
    TacticalTargetingDecision,
    TacticalTargetingPicture,
    TacticalTargetingRuntime,
    TargetingInterval,
    TargetingDisposition,
    fire_control_source_is_compatible,
    sensor_environment_range_policy,
    sensor_environment_range_upper_bound_m,
    targeting_decision_from_state,
    targeting_decision_to_state,
    targeting_altitude_range_factor,
    targeting_revalidation_outcome_from_state,
    targeting_revalidation_outcome_to_state,
    targeting_visibility_bound_m,
    weapon_role_uses_tactical_direct_engagement,
)


def _valid_decision(**overrides: object) -> TacticalTargetingDecision:
    values: dict[str, object] = {
        "engine_tick": 7,
        "logical_time_s": 30.0,
        "battle_id": "battle-alpha",
        "ordinal": 0,
        "shooter_id": "blue-1",
        "shooter_side": "blue",
        "shooter_domain": Domain.GROUND,
        "target_id": "red-1",
        "target_side": "red",
        "target_domain": Domain.GROUND,
        "distance_m": 500.0,
        "weapon_id": "direct-gun",
        "weapon_source_equipment_index": 2,
        "weapon_modeled_role": WeaponModeledRole.GROUND_DIRECT_FIRE,
        "ammunition_id": "direct-shell",
        "physical_max_range_m": 1_000.0,
        "predictive_effective_range_m": 800.0,
        "effective_range_basis": EffectiveRangeBasis.AUTHORED,
        "legacy_derived_reference_range_m": 800.0,
        "contact_source": ContactSource.NON_FOW_LOCAL_OBSERVATION,
        "observing_unit_id": "blue-1",
        "contact_sensor_source_equipment_index": None,
        "contact_sensor_id": None,
        "contact_sensor_modeled_role": None,
        "contact_time_s": 30.0,
        "contact_range_m": 1_000.0,
        "visibility_bound_m": 1_000.0,
        "sensing_sensor_source_equipment_index": None,
        "sensing_sensor_id": None,
        "sensing_sensor_modeled_role": None,
        "sensing_range_m": 1_000.0,
        "fire_control_source": FireControlSource.DIRECT_VISUAL,
        "fire_control_sensor_source_equipment_index": None,
        "fire_control_sensor_id": None,
        "fire_control_sensor_modeled_role": None,
        "fire_control_range_m": 1_000.0,
        "disposition": TargetingDisposition.VALID_STANDOFF_HOLD,
        "authorized_standoff_m": 800.0,
        "hold_authorized": True,
        "engagement_solution_valid": True,
        "sensing_aware_standoff_enabled": True,
        "fog_of_war_enabled": False,
        "consumable": True,
    }
    values.update(overrides)
    return TacticalTargetingDecision(**values)  # type: ignore[arg-type]


def _no_target_decision(
    *,
    shooter_id: str,
    shooter_side: str,
    ordinal: int,
    battle_id: str = "battle-alpha",
    engine_tick: int = 7,
    logical_time_s: float = 30.0,
    fog_of_war_enabled: bool = False,
) -> TacticalTargetingDecision:
    return TacticalTargetingDecision(
        engine_tick=engine_tick,
        logical_time_s=logical_time_s,
        battle_id=battle_id,
        ordinal=ordinal,
        shooter_id=shooter_id,
        shooter_side=shooter_side,
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
        fog_of_war_enabled=fog_of_war_enabled,
        consumable=True,
    )


def _picture(
    *,
    battle_id: str = "battle-alpha",
    engine_tick: int = 7,
    logical_time_s: float = 30.0,
    fog_of_war_enabled: bool = False,
) -> TacticalTargetingPicture:
    return TacticalTargetingPicture(
        engine_tick=engine_tick,
        logical_time_s=logical_time_s,
        battle_id=battle_id,
        fog_of_war_enabled=fog_of_war_enabled,
        decisions=(
            _no_target_decision(
                shooter_id="blue-1",
                shooter_side="blue",
                ordinal=0,
                battle_id=battle_id,
                engine_tick=engine_tick,
                logical_time_s=logical_time_s,
                fog_of_war_enabled=fog_of_war_enabled,
            ),
            _no_target_decision(
                shooter_id="red-1",
                shooter_side="red",
                ordinal=1,
                battle_id=battle_id,
                engine_tick=engine_tick,
                logical_time_s=logical_time_s,
                fog_of_war_enabled=fog_of_war_enabled,
            ),
        ),
    )


def _engagement_picture(
    *,
    battle_id: str = "battle-alpha",
    engine_tick: int = 7,
    logical_time_s: float = 30.0,
    fog_of_war_enabled: bool = False,
) -> TacticalTargetingPicture:
    decision_overrides: dict[str, object] = {
        "battle_id": battle_id,
        "engine_tick": engine_tick,
        "logical_time_s": logical_time_s,
        "contact_time_s": logical_time_s,
        "fog_of_war_enabled": fog_of_war_enabled,
    }
    if fog_of_war_enabled:
        decision_overrides.update(
            {
                "contact_source": ContactSource.FOW_OBSERVER_WITNESS,
                "contact_sensor_source_equipment_index": 3,
                "contact_sensor_id": "binocular",
                "contact_sensor_modeled_role": (SensorModeledRole.VISUAL_OBSERVATION),
                "contact_range_m": 500.0,
                "sensing_sensor_source_equipment_index": 3,
                "sensing_sensor_id": "binocular",
                "sensing_sensor_modeled_role": (SensorModeledRole.VISUAL_OBSERVATION),
                "sensing_range_m": 500.0,
                "authorized_standoff_m": 500.0,
            }
        )
    return TacticalTargetingPicture(
        engine_tick=engine_tick,
        logical_time_s=logical_time_s,
        battle_id=battle_id,
        fog_of_war_enabled=fog_of_war_enabled,
        decisions=(
            _valid_decision(**decision_overrides),
            _no_target_decision(
                shooter_id="red-1",
                shooter_side="red",
                ordinal=1,
                battle_id=battle_id,
                engine_tick=engine_tick,
                logical_time_s=logical_time_s,
                fog_of_war_enabled=fog_of_war_enabled,
            ),
        ),
    )


def _revalidation(
    decision: TacticalTargetingDecision,
    **overrides: object,
) -> TacticalEngagementRevalidationOutcome:
    values: dict[str, object] = {
        "engine_tick": decision.engine_tick,
        "logical_time_s": decision.logical_time_s,
        "battle_id": decision.battle_id,
        "shooter_id": decision.shooter_id,
        "target_id": decision.target_id,
        "weapon_id": decision.weapon_id,
        "weapon_source_equipment_index": (decision.weapon_source_equipment_index),
        "weapon_modeled_role": decision.weapon_modeled_role,
        "ammunition_id": decision.ammunition_id,
        "disposition": TargetingDisposition.VALID_ENGAGEMENT_SOLUTION,
        "revalidation_passed": True,
        "fog_of_war_enabled": decision.fog_of_war_enabled,
        "consumable": decision.consumable,
    }
    values.update(overrides)
    return TacticalEngagementRevalidationOutcome(  # type: ignore[arg-type]
        **values,
    )


def _runtime() -> TacticalTargetingRuntime:
    return TacticalTargetingRuntime(
        sensing_aware_standoff_enabled=True,
        unit_sides={"red-1": "red", "blue-1": "blue"},
    )


def _stage(
    runtime: TacticalTargetingRuntime,
    *,
    engine_tick: int = 7,
    logical_time_s: float = 30.0,
    fog_of_war_enabled: bool = False,
    battles: tuple[str, ...] = ("battle-alpha",),
) -> TargetingInterval:
    return runtime.stage_interval(
        engine_tick=engine_tick,
        logical_time_s=logical_time_s,
        fog_of_war_enabled=fog_of_war_enabled,
        unit_sides={"red-1": "red", "blue-1": "blue"},
        battle_memberships={battle_id: ("red-1", "blue-1") for battle_id in battles},
    )


def test_effective_range_evidence_never_promotes_legacy_fallback() -> None:
    authored = EffectiveRangeEvidence.from_catalog(
        physical_max_range_m=1_000.0,
        authored_effective_range_m=700.0,
    )
    legacy = EffectiveRangeEvidence.from_catalog(
        physical_max_range_m=1_000.0,
        authored_effective_range_m=None,
    )

    assert authored.basis is EffectiveRangeBasis.AUTHORED
    assert authored.predictive_effective_range_m == 700.0
    assert legacy.basis is (EffectiveRangeBasis.LEGACY_DERIVED_80_PERCENT_OF_MAX)
    assert legacy.predictive_effective_range_m == 0.0
    assert legacy.legacy_derived_reference_range_m == 800.0

    with pytest.raises(ValueError, match="diagnostic only"):
        replace(legacy, predictive_effective_range_m=800.0)
    with pytest.raises(ValueError, match="no greater than physical"):
        EffectiveRangeEvidence.from_catalog(
            physical_max_range_m=1_000.0,
            authored_effective_range_m=1_001.0,
        )


def test_total_fire_control_policy_rejects_search_and_wrong_director() -> None:
    assert fire_control_source_is_compatible(
        weapon_role=WeaponModeledRole.GROUND_DIRECT_FIRE,
        shooter_domain=Domain.GROUND,
        target_domain=Domain.GROUND,
        source=FireControlSource.DIRECT_VISUAL,
        sensor_role=None,
    )
    assert fire_control_source_is_compatible(
        weapon_role=WeaponModeledRole.HAND_GRENADE,
        shooter_domain=Domain.GROUND,
        target_domain=Domain.GROUND,
        source=FireControlSource.DIRECT_VISUAL,
        sensor_role=None,
    )
    assert not fire_control_source_is_compatible(
        weapon_role=WeaponModeledRole.NAVAL_GUNFIRE,
        shooter_domain=Domain.NAVAL,
        target_domain=Domain.NAVAL,
        source=FireControlSource.SENSOR_ATTACHMENT,
        sensor_role=SensorModeledRole.SHIP_SURFACE_SEARCH_RADAR,
    )
    assert fire_control_source_is_compatible(
        weapon_role=WeaponModeledRole.NAVAL_GUNFIRE,
        shooter_domain=Domain.NAVAL,
        target_domain=Domain.NAVAL,
        source=FireControlSource.SENSOR_ATTACHMENT,
        sensor_role=SensorModeledRole.NAVAL_VISUAL_DIRECTOR,
    )
    assert not weapon_role_uses_tactical_direct_engagement(
        WeaponModeledRole.FIELD_ARTILLERY,
    )


@pytest.mark.parametrize(
    "role",
    (WeaponModeledRole.ANCIENT_PROJECTILE, WeaponModeledRole.MELEE),
)
def test_direct_visual_fire_control_accepts_exact_naval_role_profiles(
    role: WeaponModeledRole,
) -> None:
    assert fire_control_source_is_compatible(
        weapon_role=role,
        shooter_domain=Domain.NAVAL,
        target_domain=Domain.NAVAL,
        source=FireControlSource.DIRECT_VISUAL,
        sensor_role=None,
    )
    assert not fire_control_source_is_compatible(
        weapon_role=role,
        shooter_domain=Domain.NAVAL,
        target_domain=Domain.AERIAL,
        source=FireControlSource.DIRECT_VISUAL,
        sensor_role=None,
    )


def test_valid_authored_decision_is_immutable_and_consumable() -> None:
    decision = _valid_decision()

    assert decision.key == (7, "battle-alpha", "blue-1")
    assert decision.can_hold
    assert decision.can_engage
    with pytest.raises(FrozenInstanceError):
        decision.distance_m = 1.0  # type: ignore[misc]


def test_targeting_visibility_resolver_is_exact_shared_and_fail_closed() -> None:
    assert (
        targeting_visibility_bound_m(
            calibration={},
            default_visibility_m=2_000.0,
            weather_visibility_m=1_500.0,
        )
        == 1_500.0
    )
    assert (
        targeting_visibility_bound_m(
            calibration={"visibility_m": 1_250.0},
            default_visibility_m=2_000.0,
            weather_visibility_m=1_500.0,
        )
        == 1_250.0
    )
    for invalid in (True, -1.0, float("inf"), float("nan")):
        with pytest.raises(ValueError, match="finite and non-negative"):
            targeting_visibility_bound_m(
                calibration={"visibility_m": invalid},
                default_visibility_m=2_000.0,
                weather_visibility_m=None,
            )
    with pytest.raises(ValueError, match="finite and non-negative"):
        targeting_visibility_bound_m(
            calibration={},
            default_visibility_m=float("inf"),
            weather_visibility_m=None,
        )
    with pytest.raises(ValueError, match="finite and non-negative"):
        targeting_visibility_bound_m(
            calibration={},
            default_visibility_m=2_000.0,
            weather_visibility_m=-1.0,
        )


def test_targeting_altitude_range_factor_is_shared_finite_and_exact() -> None:
    calibration = {
        "enable_human_factors": True,
        "altitude_sickness_threshold_m": 2_500.0,
        "altitude_sickness_rate": 0.03,
    }
    assert targeting_altitude_range_factor(
        calibration=calibration,
        observer_altitude_m=3_500.0,
        observer_acclimatized=False,
    ) == pytest.approx(0.7)
    assert targeting_altitude_range_factor(
        calibration=calibration,
        observer_altitude_m=3_500.0,
        observer_acclimatized=True,
    ) == pytest.approx(0.85)
    assert targeting_altitude_range_factor(
        calibration={
            **calibration,
            "altitude_sickness_rate": -0.1,
        },
        observer_altitude_m=3_500.0,
        observer_acclimatized=False,
    ) == pytest.approx(2.0)
    assert math.isfinite(
        targeting_altitude_range_factor(
            calibration={
                **calibration,
                "altitude_sickness_threshold_m": -sys.float_info.max,
                "altitude_sickness_rate": -sys.float_info.max,
            },
            observer_altitude_m=sys.float_info.max,
            observer_acclimatized=False,
        )
    )


def test_sensor_environment_extension_policy_is_exact_total_and_bounded() -> None:
    expected = {
        SensorType.VISUAL: 1.3,
        SensorType.NVG: 1.3,
        SensorType.THERMAL: 1.3,
        SensorType.RADAR: 1.3,
        SensorType.PASSIVE_ACOUSTIC: 1.3,
        SensorType.ACTIVE_SONAR: 1.3,
        SensorType.PASSIVE_SONAR: 1.3,
        SensorType.ESM: 1.3,
        SensorType.SEISMIC: 1.3,
        SensorType.MAD: 1.3,
    }

    policy = sensor_environment_range_policy(
        calibration={},
        observer_domain=Domain.GROUND,
        observer_altitude_m=0.0,
        observer_acclimatized=False,
    )
    assert dict(policy.extension_factors) == expected
    assert set(policy.extension_factors) == set(SensorType)
    for sensor_type, factor in expected.items():
        assert sensor_environment_range_upper_bound_m(
            policy=policy,
            sensor_type=sensor_type,
            condition_adjusted_range_m=100.0,
        ) == pytest.approx(100.0 * factor)

    with pytest.raises(ValueError, match="condition_adjusted_range_m"):
        sensor_environment_range_upper_bound_m(
            policy=policy,
            sensor_type=SensorType.RADAR,
            condition_adjusted_range_m=float("nan"),
        )


def test_sensor_environment_policy_covers_schema_valid_range_extenders() -> None:
    policy = sensor_environment_range_policy(
        calibration={
            "thermal_contrast": 2.25,
            "night_thermal_floor": 1.75,
            "enable_thermal_crossover": True,
            "rain_attenuation_factor": -1.0,
            "enable_em_propagation": True,
            "enable_air_combat_environment": True,
            "icing_radar_penalty_db": -40.0,
            "enable_human_factors": True,
            "mopp_fov_reduction_4": 2.0,
            "altitude_sickness_threshold_m": 2_500.0,
            "altitude_sickness_rate": -0.1,
        },
        observer_domain=Domain.NAVAL,
        observer_altitude_m=3_500.0,
        observer_acclimatized=False,
    )

    assert policy.extension_factors[SensorType.THERMAL] == pytest.approx(
        1.3 * 2.0 * 2.0 * 2.25,
    )
    assert policy.extension_factors[SensorType.RADAR] == pytest.approx(
        1.3 * 2.0 * 2.0 * 2.0 * 10.0 * 10.0,
    )


@pytest.mark.parametrize(
    "calibration",
    (
        {"rain_attenuation_factor": -400.0},
        {
            "enable_air_combat_environment": True,
            "icing_radar_penalty_db": -40_000.0,
        },
        {
            "enable_thermal_crossover": True,
            "thermal_contrast": 1.0e308,
            "enable_human_factors": True,
            "mopp_fov_reduction_4": 1.0e308,
        },
    ),
)
def test_sensor_environment_policy_saturates_schema_valid_extenders(
    calibration: dict[str, object],
) -> None:
    policy = sensor_environment_range_policy(
        calibration=calibration,
        observer_domain=Domain.GROUND,
        observer_altitude_m=0.0,
        observer_acclimatized=False,
    )

    assert sys.float_info.max in policy.extension_factors.values()
    saturated_types = tuple(
        sensor_type for sensor_type, factor in policy.extension_factors.items() if factor == sys.float_info.max
    )
    assert saturated_types
    for sensor_type in saturated_types:
        assert (
            sensor_environment_range_upper_bound_m(
                policy=policy,
                sensor_type=sensor_type,
                condition_adjusted_range_m=1_000.0,
            )
            == sys.float_info.max
        )
        assert (
            sensor_environment_range_upper_bound_m(
                policy=policy,
                sensor_type=sensor_type,
                condition_adjusted_range_m=0.0,
            )
            == 0.0
        )


def test_unaided_contact_and_fire_control_cannot_exceed_visibility() -> None:
    with pytest.raises(
        ValueError,
        match="attachment-free contact exceeds the optical visibility bound",
    ):
        replace(
            _valid_decision(),
            contact_range_m=1_001.0,
            sensing_range_m=1_001.0,
        )

    with pytest.raises(
        ValueError,
        match="DIRECT_VISUAL range exceeds the optical visibility bound",
    ):
        replace(_valid_decision(), fire_control_range_m=1_001.0)


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        (
            {
                "sensing_sensor_source_equipment_index": 3,
                "sensing_sensor_id": "binocular",
                "sensing_sensor_modeled_role": (SensorModeledRole.VISUAL_OBSERVATION),
            },
            "contact and sensing attachment identity must match",
        ),
        (
            {
                "contact_sensor_source_equipment_index": 3,
                "contact_sensor_id": "binocular",
                "contact_sensor_modeled_role": (SensorModeledRole.VISUAL_OBSERVATION),
                "sensing_sensor_source_equipment_index": 4,
                "sensing_sensor_id": "second-real-attachment",
                "sensing_sensor_modeled_role": (SensorModeledRole.THERMAL_TARGETING),
            },
            "contact and sensing attachment identity must match",
        ),
        (
            {"sensing_range_m": 999.0},
            "contact and sensing ranges must match exactly",
        ),
        (
            {"contact_range_m": 400.0, "sensing_range_m": 400.0},
            "current local contact cannot be shorter than the target distance",
        ),
    ),
)
def test_contact_and_sensing_are_one_exact_immutable_observation(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _valid_decision(**changes)


def test_zero_range_fow_witness_is_valid_only_for_a_colocated_target() -> None:
    decision = _valid_decision(
        distance_m=0.0,
        contact_source=ContactSource.FOW_OBSERVER_WITNESS,
        contact_sensor_source_equipment_index=3,
        contact_sensor_id="binocular",
        contact_sensor_modeled_role=SensorModeledRole.VISUAL_OBSERVATION,
        contact_range_m=0.0,
        sensing_sensor_source_equipment_index=3,
        sensing_sensor_id="binocular",
        sensing_sensor_modeled_role=SensorModeledRole.VISUAL_OBSERVATION,
        sensing_range_m=0.0,
        disposition=TargetingDisposition.VALID_ENGAGEMENT_SOLUTION,
        authorized_standoff_m=0.0,
        hold_authorized=False,
        fog_of_war_enabled=True,
    )

    assert decision.distance_m == decision.contact_range_m == 0.0
    assert decision.can_engage
    assert not decision.can_hold
    with pytest.raises(
        ValueError,
        match="FOW witness range must equal the exact target distance",
    ):
        replace(
            decision,
            contact_range_m=1.0,
            sensing_range_m=1.0,
        )


def test_targetless_decision_rejects_injected_sensing_evidence() -> None:
    with pytest.raises(
        ValueError,
        match="contact and sensing attachment identity must match",
    ):
        replace(
            _no_target_decision(
                shooter_id="blue-1",
                shooter_side="blue",
                ordinal=0,
            ),
            sensing_sensor_source_equipment_index=3,
            sensing_sensor_id="binocular",
            sensing_sensor_modeled_role=SensorModeledRole.VISUAL_OBSERVATION,
            sensing_range_m=1.0,
        )


def test_public_decision_codec_is_json_safe_and_exactly_lossless() -> None:
    decision = _valid_decision()

    state = targeting_decision_to_state(decision)
    json.dumps(state)

    assert targeting_decision_from_state(copy.deepcopy(state)) == decision


def test_public_decision_codec_rejects_wrong_type_and_corrupt_topology() -> None:
    with pytest.raises(ValueError, match="TacticalTargetingDecision"):
        targeting_decision_to_state(None)  # type: ignore[arg-type]

    corrupt = targeting_decision_to_state(_valid_decision())
    corrupt["unexpected"] = True
    with pytest.raises(ValueError, match="invalid key topology"):
        targeting_decision_from_state(corrupt)


def test_revalidation_outcome_is_immutable_typed_and_json_lossless() -> None:
    outcome = _revalidation(_valid_decision())

    assert outcome.key == (7, "battle-alpha", "blue-1")
    assert outcome.revalidation_passed
    state = targeting_revalidation_outcome_to_state(outcome)
    json.dumps(state)
    assert (
        targeting_revalidation_outcome_from_state(
            copy.deepcopy(state),
        )
        == outcome
    )
    with pytest.raises(FrozenInstanceError):
        outcome.revalidation_passed = False  # type: ignore[misc]
    with pytest.raises(ValueError, match="rejection disposition"):
        replace(outcome, revalidation_passed=False)
    with pytest.raises(ValueError, match="VALID_ENGAGEMENT_SOLUTION"):
        replace(
            outcome,
            disposition=TargetingDisposition.OUTSIDE_PHYSICAL_RANGE,
        )

    failed = replace(
        outcome,
        disposition=TargetingDisposition.OUTSIDE_PHYSICAL_RANGE,
        revalidation_passed=False,
    )
    assert not failed.revalidation_passed
    assert failed.disposition is TargetingDisposition.OUTSIDE_PHYSICAL_RANGE


def test_no_contact_decision_does_not_leak_ground_truth_target() -> None:
    no_contact = replace(
        _no_target_decision(
            shooter_id="blue-1",
            shooter_side="blue",
            ordinal=0,
        ),
        disposition=TargetingDisposition.NO_CONTACT,
    )
    assert no_contact.target_id is None

    with pytest.raises(ValueError, match="ground-truth target"):
        _valid_decision(
            contact_source=ContactSource.NONE,
            observing_unit_id=None,
            contact_time_s=None,
            contact_range_m=0.0,
            fire_control_source=FireControlSource.NONE,
            fire_control_range_m=0.0,
            disposition=TargetingDisposition.NO_CONTACT,
            authorized_standoff_m=0.0,
            hold_authorized=False,
            engagement_solution_valid=False,
        )


def test_legacy_effective_range_allows_engagement_but_never_hold() -> None:
    decision = _valid_decision(
        predictive_effective_range_m=0.0,
        effective_range_basis=(EffectiveRangeBasis.LEGACY_DERIVED_80_PERCENT_OF_MAX),
        disposition=TargetingDisposition.EFFECTIVE_RANGE_UNKNOWN,
        authorized_standoff_m=0.0,
        hold_authorized=False,
    )

    assert decision.engagement_solution_valid
    assert decision.can_engage
    assert not decision.can_hold
    with pytest.raises(ValueError, match="cannot authorize standoff"):
        replace(decision, authorized_standoff_m=800.0, hold_authorized=True)


def test_disabled_standoff_preserves_valid_engagement_only() -> None:
    decision = _valid_decision(
        sensing_aware_standoff_enabled=False,
        disposition=TargetingDisposition.STANDOFF_DISABLED,
        authorized_standoff_m=0.0,
        hold_authorized=False,
    )

    assert decision.can_engage
    assert not decision.can_hold
    assert decision.authorized_standoff_m == 0.0

    legacy = _valid_decision(
        sensing_aware_standoff_enabled=False,
        predictive_effective_range_m=0.0,
        effective_range_basis=(EffectiveRangeBasis.LEGACY_DERIVED_80_PERCENT_OF_MAX),
        disposition=TargetingDisposition.EFFECTIVE_RANGE_UNKNOWN,
        authorized_standoff_m=0.0,
        hold_authorized=False,
    )
    assert legacy.can_engage
    assert not legacy.can_hold


@pytest.mark.parametrize(
    ("role", "physical_range", "effective_range", "distance"),
    [
        (WeaponModeledRole.HAND_GRENADE, 30.0, 20.0, 10.0),
        (WeaponModeledRole.MELEE, 3.0, 2.0, 1.0),
    ],
)
def test_close_roles_keep_direct_engagement_with_zero_standoff(
    role: WeaponModeledRole,
    physical_range: float,
    effective_range: float,
    distance: float,
) -> None:
    decision = _valid_decision(
        weapon_modeled_role=role,
        physical_max_range_m=physical_range,
        predictive_effective_range_m=effective_range,
        legacy_derived_reference_range_m=physical_range * 0.8,
        distance_m=distance,
        contact_range_m=physical_range,
        visibility_bound_m=physical_range,
        sensing_range_m=physical_range,
        fire_control_range_m=physical_range,
        disposition=TargetingDisposition.STANDOFF_NOT_SUPPORTED_FOR_ROLE,
        authorized_standoff_m=0.0,
        hold_authorized=False,
    )

    assert decision.can_engage
    assert not decision.can_hold


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"distance_m": float("nan")}, "finite and non-negative"),
        ({"authorized_standoff_m": 801.0}, "exceeds a live limiting range"),
        ({"contact_time_s": 29.0}, "same interval"),
        ({"ammunition_id": None}, "missing required evidence"),
        ({"target_side": "blue"}, "must be hostile"),
    ],
)
def test_decision_rejects_nonfinite_cross_interval_and_impossible_evidence(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _valid_decision(**changes)


def test_search_sensor_cannot_be_promoted_to_fire_control() -> None:
    with pytest.raises(ValueError, match="incompatible with weapon role"):
        _valid_decision(
            fire_control_source=FireControlSource.SENSOR_ATTACHMENT,
            fire_control_sensor_source_equipment_index=4,
            fire_control_sensor_id="surface-search",
            fire_control_sensor_modeled_role=(SensorModeledRole.SHIP_SURFACE_SEARCH_RADAR),
        )


def test_fow_direct_visual_requires_current_visual_witness() -> None:
    fow = _valid_decision(
        fog_of_war_enabled=True,
        contact_source=ContactSource.FOW_OBSERVER_WITNESS,
        contact_sensor_source_equipment_index=3,
        contact_sensor_id="binocular",
        contact_sensor_modeled_role=SensorModeledRole.VISUAL_OBSERVATION,
        contact_range_m=500.0,
        sensing_sensor_source_equipment_index=3,
        sensing_sensor_id="binocular",
        sensing_sensor_modeled_role=SensorModeledRole.VISUAL_OBSERVATION,
        sensing_range_m=500.0,
        authorized_standoff_m=500.0,
    )
    assert fow.can_hold

    with pytest.raises(ValueError, match="current visual witness"):
        replace(
            fow,
            contact_sensor_modeled_role=SensorModeledRole.ELECTRONIC_SUPPORT,
            sensing_sensor_modeled_role=SensorModeledRole.ELECTRONIC_SUPPORT,
        )


@pytest.mark.test_evidence("behavioral_oracle")
def test_fow_witness_implements_import_neutral_targeting_protocol() -> None:
    witness = ObserverDetectionWitness(
        side="blue",
        observer_unit_id="blue-1",
        target_id="red-1",
        source_equipment_index=3,
        sensor_id="binocular",
        modeled_role="visual_observation",
        logical_time_s=30.0,
        detected=True,
        probability=0.8,
        snr_db=10.0,
        range_m=500.0,
        sensor_type="VISUAL",
        bearing_deg=90.0,
    )

    assert isinstance(witness, ObserverDetectionWitnessView)


def test_picture_rejects_noncanonical_order_and_wrong_ordinal() -> None:
    blue = _no_target_decision(
        shooter_id="blue-1",
        shooter_side="blue",
        ordinal=0,
    )
    red = _no_target_decision(
        shooter_id="red-1",
        shooter_side="red",
        ordinal=1,
    )

    with pytest.raises(ValueError, match="canonical shooter order"):
        TacticalTargetingPicture(
            engine_tick=7,
            logical_time_s=30.0,
            battle_id="battle-alpha",
            fog_of_war_enabled=False,
            decisions=(red, blue),
        )
    with pytest.raises(ValueError, match="ordinal"):
        TacticalTargetingPicture(
            engine_tick=7,
            logical_time_s=30.0,
            battle_id="battle-alpha",
            fog_of_war_enabled=False,
            decisions=(replace(blue, ordinal=1), red),
        )


def test_runtime_guards_interval_and_publishes_atomically_in_battle_order() -> None:
    runtime = _runtime()
    interval = _stage(runtime, battles=("battle-zulu", "battle-alpha"))

    assert runtime.prepared_interval is None
    assert interval.battle_ids == (
        "battle-alpha",
        "battle-zulu",
    )
    with pytest.raises(ValueError, match="canonical battle-ID order"):
        runtime.publish_interval(
            interval,
            (
                _picture(battle_id="battle-zulu"),
                _picture(battle_id="battle-alpha"),
            ),
        )
    assert runtime.latest_pictures() == ()

    alpha = _picture(battle_id="battle-alpha")
    zulu = _picture(battle_id="battle-zulu")
    runtime.publish_interval(interval, (alpha, zulu))
    assert runtime.latest_pictures() == (alpha, zulu)
    assert (
        runtime.decision_for(
            engine_tick=7,
            battle_id="battle-alpha",
            shooter_id="blue-1",
        )
        is alpha.decisions[0]
    )

    before_repeated_interval = runtime.get_state()
    with pytest.raises(ValueError, match="strictly newer tick"):
        _stage(runtime)
    assert runtime.get_state() == before_repeated_interval

    with pytest.raises(ValueError, match="cannot move backwards"):
        runtime.validate_interval_advance(
            engine_tick=8,
            logical_time_s=29.0,
        )
    assert runtime.get_state() == before_repeated_interval


def test_runtime_publishes_complete_interval_set_in_one_state_swap() -> None:
    runtime = _runtime()
    before = runtime.get_state()
    interval = runtime.stage_interval(
        engine_tick=7,
        logical_time_s=30.0,
        fog_of_war_enabled=False,
        unit_sides={"red-1": "red", "blue-1": "blue"},
        battle_memberships={
            "battle-zulu": ("red-1", "blue-1"),
            "battle-alpha": ("red-1", "blue-1"),
        },
    )
    alpha = _picture(battle_id="battle-alpha")
    zulu = _picture(battle_id="battle-zulu")

    assert runtime.get_state() == before
    with pytest.raises(ValueError, match="one picture per battle"):
        runtime.publish_interval(interval, (alpha,))
    assert runtime.get_state() == before
    with pytest.raises(ValueError, match="canonical battle-ID order"):
        runtime.publish_interval(interval, (zulu, alpha))
    assert runtime.get_state() == before

    forged = TargetingInterval(
        engine_tick=7,
        logical_time_s=30.0,
        fog_of_war_enabled=False,
        unit_side_items=(("red-1", "red"), ("blue-1", "blue")),
        battle_membership_items=(
            ("battle-zulu", ("red-1", "blue-1")),
            ("battle-alpha", ("red-1", "blue-1")),
        ),
    )
    with pytest.raises(ValueError, match="canonical interval"):
        runtime.publish_interval(forged, (zulu, alpha))
    assert runtime.get_state() == before

    assert runtime.publish_interval(interval, (alpha, zulu)) == (alpha, zulu)
    assert runtime.prepared_interval is interval
    assert runtime.latest_pictures() == (alpha, zulu)
    assert runtime.get_state()["published_battle_ids"] == [
        "battle-alpha",
        "battle-zulu",
    ]


def test_runtime_publishes_only_an_exact_live_revalidation_atomically() -> None:
    runtime = _runtime()
    picture = _engagement_picture()
    outcome = _revalidation(picture.decisions[0])

    with pytest.raises(ValueError, match="has not been prepared"):
        runtime.publish_engagement_revalidation(outcome)
    interval = _stage(runtime)
    with pytest.raises(ValueError, match="has not been prepared"):
        runtime.publish_engagement_revalidation(outcome)
    runtime.publish_interval(interval, (picture,))

    invalid_outcomes = (
        replace(outcome, target_id="red-other"),
        replace(outcome, weapon_id="other-weapon"),
        replace(outcome, ammunition_id="other-ammunition"),
        replace(outcome, engine_tick=8),
        replace(outcome, logical_time_s=31.0),
        replace(outcome, fog_of_war_enabled=True),
    )
    for invalid in invalid_outcomes:
        before = runtime.get_state()
        with pytest.raises(ValueError):
            runtime.publish_engagement_revalidation(invalid)
        assert runtime.get_state() == before

    assert runtime.publish_engagement_revalidation(outcome) is outcome
    assert (
        runtime.engagement_revalidation_for(
            engine_tick=7,
            battle_id="battle-alpha",
            shooter_id="blue-1",
        )
        is outcome
    )
    before_duplicate = runtime.get_state()
    with pytest.raises(ValueError, match="duplicate"):
        runtime.publish_engagement_revalidation(outcome)
    assert runtime.get_state() == before_duplicate


def test_revalidation_ledger_is_bounded_and_canonically_ordered() -> None:
    runtime = _runtime()
    interval = _stage(
        runtime,
        battles=("battle-zulu", "battle-alpha"),
    )
    alpha = _engagement_picture(battle_id="battle-alpha")
    zulu = _engagement_picture(battle_id="battle-zulu")
    runtime.publish_interval(interval, (alpha, zulu))
    alpha_outcome = runtime.publish_engagement_revalidation(
        _revalidation(alpha.decisions[0]),
    )
    zulu_outcome = runtime.publish_engagement_revalidation(
        _revalidation(zulu.decisions[0]),
    )

    assert runtime.latest_engagement_revalidations() == (
        alpha_outcome,
        zulu_outcome,
    )

    next_interval = _stage(
        runtime,
        engine_tick=8,
        logical_time_s=40.0,
        battles=("battle-zulu", "battle-alpha"),
    )
    next_alpha = _engagement_picture(
        battle_id="battle-alpha",
        engine_tick=8,
        logical_time_s=40.0,
    )
    next_zulu = _engagement_picture(
        battle_id="battle-zulu",
        engine_tick=8,
        logical_time_s=40.0,
    )
    runtime.publish_interval(next_interval, (next_alpha, next_zulu))
    assert runtime.latest_engagement_revalidations() == ()
    assert (
        runtime.engagement_revalidation_for(
            engine_tick=7,
            battle_id="battle-alpha",
            shooter_id="blue-1",
        )
        is None
    )
    assert (
        runtime.engagement_revalidation_for(
            engine_tick=7,
            battle_id="battle-zulu",
            shooter_id="blue-1",
        )
        is None
    )


def test_runtime_bounds_latest_picture_and_never_returns_stale_tick() -> None:
    runtime = _runtime()
    interval = _stage(runtime)
    runtime.publish_interval(interval, (_picture(),))

    next_interval = _stage(runtime, engine_tick=8, logical_time_s=40.0)
    assert (
        runtime.decision_for(
            engine_tick=8,
            battle_id="battle-alpha",
            shooter_id="blue-1",
        )
        is None
    )
    runtime.publish_interval(
        next_interval,
        (_picture(engine_tick=8, logical_time_s=40.0),),
    )

    assert len(runtime.latest_pictures()) == 1
    assert runtime.latest_pictures()[0].engine_tick == 8
    assert (
        runtime.decision_for(
            engine_tick=7,
            battle_id="battle-alpha",
            shooter_id="blue-1",
        )
        is None
    )


def test_registration_is_persisted_at_tick_zero_and_invalidates_old_picture() -> None:
    runtime = _runtime()
    tick_zero = runtime.get_state()

    assert tick_zero["prepared_interval"] is None
    assert tick_zero["registered_unit_sides"] == [
        {"unit_id": "blue-1", "side": "blue"},
        {"unit_id": "red-1", "side": "red"},
    ]
    interval = _stage(runtime)
    runtime.publish_interval(interval, (_picture(),))
    runtime.register_units({"blue-reinforcement": "blue"})

    assert runtime.prepared_interval is None
    assert runtime.latest_pictures() == ()
    assert runtime.registered_unit_sides["blue-reinforcement"] == "blue"
    before = runtime.get_state()
    with pytest.raises(ValueError, match="changed side"):
        runtime.register_units({"blue-reinforcement": "red"})
    assert runtime.get_state() == before


def test_registration_replacement_is_atomic_and_noop_preserves_history() -> None:
    runtime = _runtime()
    interval = _stage(runtime)
    picture = _picture()
    runtime.publish_interval(interval, (picture,))
    before = runtime.get_state()

    current = {"red-1": "red", "blue-1": "blue"}
    runtime.replace_registered_units(
        expected_current=current,
        replacement=current,
    )
    assert runtime.get_state() == before
    assert runtime.prepared_interval is interval
    assert runtime.latest_pictures() == (picture,)
    assert runtime.latest_pictures()[0] is picture

    with pytest.raises(ValueError, match="non-empty"):
        runtime.replace_registered_units(
            expected_current=current,
            replacement={"blue-1": ""},
        )
    assert runtime.get_state() == before

    with pytest.raises(ValueError, match="changed before replacement"):
        runtime.replace_registered_units(
            expected_current={"blue-1": "blue"},
            replacement={"aggregate": "blue"},
        )
    assert runtime.get_state() == before


def test_registration_replacement_clears_history_and_plan_restores_it() -> None:
    runtime = _runtime()
    interval = _stage(runtime)
    runtime.publish_interval(interval, (_picture(),))
    before = runtime.get_state()
    rollback = runtime.stage_state(copy.deepcopy(before))

    runtime.replace_registered_units(
        expected_current={"blue-1": "blue", "red-1": "red"},
        replacement={"aggregate": "blue"},
    )

    assert dict(runtime.registered_unit_sides) == {"aggregate": "blue"}
    assert runtime.prepared_interval is None
    assert runtime.latest_pictures() == ()

    runtime.commit_state(rollback)
    assert runtime.get_state() == before


def test_staged_interval_reuses_immutable_topology_indexes() -> None:
    runtime = _runtime()
    interval = _stage(runtime)

    assert interval.unit_sides is interval.unit_sides
    assert interval.battle_memberships is interval.battle_memberships
    assert interval.battle_ids is interval.battle_ids
    with pytest.raises(TypeError):
        interval.unit_sides["blue-1"] = "red"  # type: ignore[index]


def test_non_fow_state_round_trip_is_exact_and_json_scalar_only() -> None:
    runtime = _runtime()
    interval = _stage(runtime)
    picture = _engagement_picture()
    runtime.publish_interval(interval, (picture,))
    live_outcome = runtime.publish_engagement_revalidation(
        _revalidation(picture.decisions[0]),
    )
    state = runtime.get_state()
    json.dumps(state)

    restored = _runtime()
    restored.set_state(
        copy.deepcopy(state),
        expected_unit_sides={"blue-1": "blue", "red-1": "red"},
        expected_battle_memberships={
            "battle-alpha": ("blue-1", "red-1"),
        },
        expected_engine_tick=7,
        expected_logical_time_s=30.0,
    )

    assert restored.get_state() == state
    decision = restored.decision_for(
        engine_tick=7,
        battle_id="battle-alpha",
        shooter_id="blue-1",
    )
    assert decision is not None and decision.consumable
    assert (
        restored.engagement_revalidation_for(
            engine_tick=7,
            battle_id="battle-alpha",
            shooter_id="blue-1",
        )
        == live_outcome
    )


def test_restored_fow_solution_and_revalidation_remain_consumable() -> None:
    runtime = _runtime()
    interval = _stage(runtime, fog_of_war_enabled=True)
    live = _valid_decision(
        fog_of_war_enabled=True,
        contact_source=ContactSource.FOW_OBSERVER_WITNESS,
        contact_sensor_source_equipment_index=3,
        contact_sensor_id="binocular",
        contact_sensor_modeled_role=SensorModeledRole.VISUAL_OBSERVATION,
        contact_range_m=500.0,
        sensing_sensor_source_equipment_index=3,
        sensing_sensor_id="binocular",
        sensing_sensor_modeled_role=SensorModeledRole.VISUAL_OBSERVATION,
        sensing_range_m=500.0,
        authorized_standoff_m=500.0,
    )
    picture = TacticalTargetingPicture(
        engine_tick=7,
        logical_time_s=30.0,
        battle_id="battle-alpha",
        fog_of_war_enabled=True,
        decisions=(
            live,
            _no_target_decision(
                shooter_id="red-1",
                shooter_side="red",
                ordinal=1,
                fog_of_war_enabled=True,
            ),
        ),
    )
    runtime.publish_interval(interval, (picture,))
    live_outcome = runtime.publish_engagement_revalidation(
        _revalidation(live),
    )

    restored = _runtime()
    restored.set_state(runtime.get_state())

    restored_decision = restored.decision_for(
        engine_tick=7,
        battle_id="battle-alpha",
        shooter_id="blue-1",
    )
    assert restored_decision == live
    assert restored_decision.consumable
    assert restored_decision.can_hold
    assert restored_decision.can_engage
    assert (
        restored.engagement_revalidation_for(
            engine_tick=7,
            battle_id="battle-alpha",
            shooter_id="blue-1",
        )
        == live_outcome
    )


def test_corrupt_cross_decision_revalidation_state_rejects_atomically() -> None:
    runtime = _runtime()
    interval = _stage(runtime)
    picture = _engagement_picture()
    runtime.publish_interval(interval, (picture,))
    runtime.publish_engagement_revalidation(_revalidation(picture.decisions[0]))
    before = runtime.get_state()

    cross_decision = copy.deepcopy(before)
    cross_decision["latest_engagement_revalidations"][0]["ammunition_id"] = "other-ammunition"
    with pytest.raises(ValueError, match="disagrees with decision"):
        runtime.set_state(cross_decision)
    assert runtime.get_state() == before

    duplicate = copy.deepcopy(before)
    duplicate["latest_engagement_revalidations"].append(
        copy.deepcopy(duplicate["latest_engagement_revalidations"][0]),
    )
    with pytest.raises(ValueError, match="duplicate engagement"):
        runtime.set_state(duplicate)
    assert runtime.get_state() == before

    corrupt_topology = copy.deepcopy(before)
    corrupt_topology["latest_engagement_revalidations"][0]["unexpected"] = True
    with pytest.raises(ValueError, match="invalid key topology"):
        runtime.set_state(corrupt_topology)
    assert runtime.get_state() == before


def test_corrupt_state_rejects_without_mutating_runtime() -> None:
    runtime = _runtime()
    interval = _stage(runtime)
    runtime.publish_interval(interval, (_picture(),))
    before = runtime.get_state()

    incomplete = copy.deepcopy(before)
    incomplete["published_battle_ids"] = []
    incomplete["latest_pictures"] = []
    with pytest.raises(ValueError, match="complete interval"):
        runtime.stage_state(incomplete)
    assert runtime.get_state() == before

    corrupt = copy.deepcopy(before)
    corrupt["latest_pictures"][0]["decisions"][0]["distance_m"] = float("nan")

    with pytest.raises(ValueError, match="finite and non-negative"):
        runtime.set_state(corrupt)
    assert runtime.get_state() == before

    wrong_roster = _runtime()
    wrong_roster.register_units({"blue-2": "blue"})
    with pytest.raises(ValueError, match="registered roster mismatch"):
        wrong_roster.stage_state(before)
