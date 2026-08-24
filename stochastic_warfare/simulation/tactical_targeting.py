"""Typed, deterministic tactical targeting decisions and runtime state.

This module owns no detection, movement, or combat behavior.  It is the
RNG-free boundary that validates and publishes the immutable targeting answer
those production owners share for one tactical interval.
"""

from __future__ import annotations

import math
import sys
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field, replace
from enum import Enum
from types import MappingProxyType
from typing import Any, Protocol, TypeAlias, runtime_checkable

from stochastic_warfare.core.types import Domain
from stochastic_warfare.detection.observer_support import (
    ObserverTrackSupportEvidence,
    observer_track_support_evidence_from_state,
    observer_track_support_evidence_to_state,
)
from stochastic_warfare.detection.sensors import SensorType
from stochastic_warfare.simulation.loadouts import (
    SensorModeledRole,
    SensorTargetingClass,
    WeaponModeledRole,
    WeaponStandoffClass,
    allowed_shooter_domains_for_sensor_role,
    compatible_sensor_roles_for_weapon_role,
    required_domains_for_sensor_role,
    sensor_targeting_class,
    weapon_role_supports_target_domain,
    weapon_standoff_class,
)

LEGACY_EFFECTIVE_RANGE_FRACTION = 0.8
DecisionKey: TypeAlias = tuple[int, str, str]
_MAX_FINITE_RANGE_VALUE = sys.float_info.max


def saturating_range_product(*values: float) -> float:
    """Multiply finite non-negative range terms without producing infinity."""
    product = 1.0
    for index, value in enumerate(values):
        factor = _require_non_negative_number(
            value,
            label=f"range product factor {index}",
        )
        if product == 0.0 or factor == 0.0:
            return 0.0
        if product > _MAX_FINITE_RANGE_VALUE / factor:
            return _MAX_FINITE_RANGE_VALUE
        product *= factor
    return product


def saturating_range_power(base: float, exponent: float) -> float:
    """Raise a finite non-negative range factor without producing infinity."""
    normalized_base = _require_non_negative_number(
        base,
        label="range power base",
    )
    if isinstance(exponent, bool) or not isinstance(exponent, (int, float)) or not math.isfinite(float(exponent)):
        raise ValueError("range power exponent must be finite")
    normalized_exponent = float(exponent)
    if normalized_base == 0.0 and normalized_exponent < 0.0:
        raise ValueError("zero range power base cannot have a negative exponent")
    try:
        result = normalized_base**normalized_exponent
    except OverflowError:
        return _MAX_FINITE_RANGE_VALUE
    if math.isinf(result):
        return _MAX_FINITE_RANGE_VALUE
    if math.isnan(result) or result < 0.0:
        raise ValueError("range power result must be finite and non-negative")
    return result


class EffectiveRangeBasis(str, Enum):
    """Provenance of the weapon's predictive effective range."""

    AUTHORED = "AUTHORED"
    LEGACY_DERIVED_80_PERCENT_OF_MAX = "LEGACY_DERIVED_80_PERCENT_OF_MAX"


class ContactSource(str, Enum):
    """Authority that established the exact same-interval contact."""

    NONE = "NONE"
    NON_FOW_LOCAL_OBSERVATION = "NON_FOW_LOCAL_OBSERVATION"
    FOW_OBSERVER_WITNESS = "FOW_OBSERVER_WITNESS"
    FOW_OBSERVER_TRACK_SUPPORT = "FOW_OBSERVER_TRACK_SUPPORT"


class FireControlSource(str, Enum):
    """Local fire-control source selected for a weapon attachment."""

    NONE = "NONE"
    DIRECT_VISUAL = "DIRECT_VISUAL"
    SENSOR_ATTACHMENT = "SENSOR_ATTACHMENT"


class TargetingDisposition(str, Enum):
    """Exact targeting outcome or first non-authorizing gate."""

    VALID_STANDOFF_HOLD = "VALID_STANDOFF_HOLD"
    VALID_ENGAGEMENT_SOLUTION = "VALID_ENGAGEMENT_SOLUTION"
    EFFECTIVE_RANGE_UNKNOWN = "EFFECTIVE_RANGE_UNKNOWN"
    STANDOFF_DISABLED = "STANDOFF_DISABLED"
    STANDOFF_NOT_SUPPORTED_FOR_ROLE = "STANDOFF_NOT_SUPPORTED_FOR_ROLE"
    SHOOTER_INACTIVE = "SHOOTER_INACTIVE"
    NO_TARGET = "NO_TARGET"
    TARGET_INACTIVE = "TARGET_INACTIVE"
    TARGET_NOT_HOSTILE = "TARGET_NOT_HOSTILE"
    TARGET_NOT_IN_BATTLE = "TARGET_NOT_IN_BATTLE"
    NO_CONTACT = "NO_CONTACT"
    STALE_CONTACT = "STALE_CONTACT"
    CONTACT_OBSERVER_MISMATCH = "CONTACT_OBSERVER_MISMATCH"
    CONTACT_SENSOR_UNAVAILABLE = "CONTACT_SENSOR_UNAVAILABLE"
    CONTACT_SENSOR_OFFLINE = "CONTACT_SENSOR_OFFLINE"
    CONTACT_SENSOR_WRONG_DOMAIN = "CONTACT_SENSOR_WRONG_DOMAIN"
    CONTACT_RANGE_EXCEEDED = "CONTACT_RANGE_EXCEEDED"
    LINE_OF_SIGHT_BLOCKED = "LINE_OF_SIGHT_BLOCKED"
    OUTSIDE_SENSOR_FIELD_OF_VIEW = "OUTSIDE_SENSOR_FIELD_OF_VIEW"
    VISIBILITY_LIMITED = "VISIBILITY_LIMITED"
    SENSING_RANGE_EXCEEDED = "SENSING_RANGE_EXCEEDED"
    NO_USABLE_WEAPON = "NO_USABLE_WEAPON"
    WEAPON_INOPERABLE = "WEAPON_INOPERABLE"
    NO_FIREABLE_AMMUNITION = "NO_FIREABLE_AMMUNITION"
    WEAPON_RESERVED = "WEAPON_RESERVED"
    TARGET_DOMAIN_UNSUPPORTED = "TARGET_DOMAIN_UNSUPPORTED"
    UNSUPPORTED_WEAPON_ROLE = "UNSUPPORTED_WEAPON_ROLE"
    ROUTED_WEAPON_ROLE = "ROUTED_WEAPON_ROLE"
    NO_COMPATIBLE_FIRE_CONTROL = "NO_COMPATIBLE_FIRE_CONTROL"
    FIRE_CONTROL_SENSOR_OFFLINE = "FIRE_CONTROL_SENSOR_OFFLINE"
    FIRE_CONTROL_SHOOTER_DOMAIN_UNSUPPORTED = "FIRE_CONTROL_SHOOTER_DOMAIN_UNSUPPORTED"
    FIRE_CONTROL_TARGET_DOMAIN_UNSUPPORTED = "FIRE_CONTROL_TARGET_DOMAIN_UNSUPPORTED"
    FIRE_CONTROL_RANGE_EXCEEDED = "FIRE_CONTROL_RANGE_EXCEEDED"
    OUTSIDE_PHYSICAL_RANGE = "OUTSIDE_PHYSICAL_RANGE"
    OUTSIDE_EFFECTIVE_RANGE = "OUTSIDE_EFFECTIVE_RANGE"


_VALID_ENGAGEMENT_DISPOSITIONS = frozenset(
    {
        TargetingDisposition.VALID_STANDOFF_HOLD,
        TargetingDisposition.VALID_ENGAGEMENT_SOLUTION,
        TargetingDisposition.EFFECTIVE_RANGE_UNKNOWN,
        TargetingDisposition.STANDOFF_DISABLED,
        TargetingDisposition.STANDOFF_NOT_SUPPORTED_FOR_ROLE,
    }
)

_TARGETLESS_DISPOSITIONS = frozenset(
    {
        TargetingDisposition.NO_TARGET,
        TargetingDisposition.NO_CONTACT,
    }
)


def targeting_disposition_is_valid_engagement(
    disposition: object,
) -> bool:
    """Return whether the owner classifies a disposition as engageable."""
    return isinstance(disposition, TargetingDisposition) and disposition in _VALID_ENGAGEMENT_DISPOSITIONS


def targeting_disposition_is_targetless(disposition: object) -> bool:
    """Return whether the owner requires a targetless decision topology."""
    return isinstance(disposition, TargetingDisposition) and disposition in _TARGETLESS_DISPOSITIONS


_FOW_DIRECT_VISUAL_WITNESS_ROLES = frozenset(
    {
        SensorModeledRole.VISUAL_OBSERVATION,
        SensorModeledRole.NIGHT_VISION,
        SensorModeledRole.NAVAL_LOOKOUT,
        SensorModeledRole.AIRBORNE_LOW_LIGHT_OBSERVATION,
        SensorModeledRole.INDIVIDUAL_NIGHT_VISION,
    }
)

_CLOSE_DIRECT_ENGAGEMENT_ROLES = frozenset(
    {
        WeaponModeledRole.HAND_GRENADE,
        WeaponModeledRole.MELEE,
    }
)


@runtime_checkable
class ObserverDetectionWitnessView(Protocol):
    """Import-neutral view of one FOW observer detection witness."""

    side: str
    observer_unit_id: str
    target_id: str
    source_equipment_index: int
    sensor_id: str
    modeled_role: str
    logical_time_s: float
    detected: bool
    probability: float
    snr_db: float
    range_m: float
    sensor_type: str
    bearing_deg: float


def _require_identifier(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(
            f"{label} must be a non-empty, trimmed, case-sensitive string",
        )
    return value


def _require_optional_identifier(value: object, *, label: str) -> str | None:
    if value is None:
        return None
    return _require_identifier(value, label=label)


def _require_non_negative_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _require_optional_index(value: object, *, label: str) -> int | None:
    if value is None:
        return None
    return _require_non_negative_int(value, label=label)


def _require_non_negative_number(value: object, *, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise ValueError(f"{label} must be finite and non-negative")
    return float(value)


def _require_bool(value: object, *, label: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{label} must be a boolean")
    return value


def _require_enum(value: object, enum_type: type[Enum], *, label: str) -> Any:
    if not isinstance(value, enum_type):
        raise ValueError(f"{label} must be a {enum_type.__name__}")
    return value


def _parse_enum(value: object, enum_type: type[Enum], *, label: str) -> Any:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string enum value")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ValueError(f"{label} has unknown value {value!r}") from exc


def _parse_domain(value: object, *, label: str) -> Domain:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a Domain name")
    try:
        return Domain[value]
    except KeyError as exc:
        raise ValueError(f"{label} has unknown Domain name {value!r}") from exc


def _require_optional_group(
    values: tuple[object | None, ...],
    *,
    label: str,
) -> bool:
    present = tuple(value is not None for value in values)
    if any(present) and not all(present):
        raise ValueError(f"{label} identity must be wholly present or absent")
    return all(present)


DEFAULT_TARGETING_VISIBILITY_M = 10_000.0

_TARGET_SIGNATURE_RANGE_EXTENSION = 1.3
_RADAR_DUCT_RANGE_EXTENSION = 2.0
_ACOUSTIC_LAYER_RANGE_EXTENSION = 6.0


def _policy_number(
    calibration: Mapping[str, object],
    key: str,
    default: float,
) -> float:
    value = calibration.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"calibration {key!r} must be a finite number")
    return float(value)


def _policy_bool(
    calibration: Mapping[str, object],
    key: str,
    default: bool,
) -> bool:
    value = calibration.get(key, default)
    if type(value) is not bool:
        raise ValueError(f"calibration {key!r} must be a boolean")
    return value


def targeting_visibility_bound_m(
    *,
    calibration: Mapping[str, object],
    default_visibility_m: float,
    weather_visibility_m: object | None,
) -> float:
    """Resolve the exact finite visibility shared by production and restore."""
    if not isinstance(calibration, Mapping):
        raise ValueError("calibration must be a mapping")
    default_visibility = _require_non_negative_number(
        default_visibility_m,
        label="targeting default visibility",
    )
    configured = calibration.get("visibility_m")
    resolved = (
        default_visibility
        if configured is None
        else _require_non_negative_number(
            configured,
            label="targeting configured visibility",
        )
    )
    if weather_visibility_m is not None:
        resolved = min(
            resolved,
            _require_non_negative_number(
                weather_visibility_m,
                label="targeting weather visibility",
            ),
        )
    return resolved


def targeting_altitude_range_factor(
    *,
    calibration: Mapping[str, object],
    observer_altitude_m: float,
    observer_acclimatized: bool,
) -> float:
    """Return the shared finite live altitude-sickness range factor."""
    if not isinstance(calibration, Mapping):
        raise ValueError("calibration must be a mapping")
    if (
        isinstance(observer_altitude_m, bool)
        or not isinstance(observer_altitude_m, (int, float))
        or not math.isfinite(float(observer_altitude_m))
    ):
        raise ValueError("observer_altitude_m must be finite")
    altitude = float(observer_altitude_m)
    acclimatized = _require_bool(
        observer_acclimatized,
        label="observer_acclimatized",
    )
    if not _policy_bool(calibration, "enable_human_factors", False):
        return 1.0
    threshold_m = _policy_number(
        calibration,
        "altitude_sickness_threshold_m",
        2_500.0,
    )
    if altitude <= threshold_m:
        return 1.0
    rate = _policy_number(
        calibration,
        "altitude_sickness_rate",
        0.03,
    )
    altitude_delta = (altitude - threshold_m) / 100.0
    if math.isinf(altitude_delta):
        altitude_delta = _MAX_FINITE_RANGE_VALUE
    if rate < 0.0:
        extension = saturating_range_product(-rate, altitude_delta)
        factor = _MAX_FINITE_RANGE_VALUE if extension >= _MAX_FINITE_RANGE_VALUE - 1.0 else 1.0 + extension
    else:
        penalty = saturating_range_product(rate, altitude_delta)
        factor = max(0.5, 1.0 - penalty)
    if acclimatized:
        factor = 1.0 - (1.0 - factor) * 0.5
    return _require_non_negative_number(
        factor,
        label="targeting altitude range factor",
    )


@dataclass(frozen=True, slots=True)
class SensorEnvironmentRangePolicy:
    """Exact-total environmental range ceiling for one live observer.

    The immutable mapping is built from the same accepted calibration and
    observer state used by the production resolver.  Restore therefore never
    invents a smaller fixed ceiling than a schema-valid production run can
    reach.  Finite overflow-scale inputs saturate at the largest finite float;
    non-finite input and production evidence still fail closed.
    """

    extension_factors: Mapping[SensorType, float]

    def __post_init__(self) -> None:
        factors = dict(self.extension_factors)
        if set(factors) != set(SensorType):
            raise ValueError(
                "sensor environmental range-extension policy is not exact-total",
            )
        if any(
            isinstance(factor, bool)
            or not isinstance(factor, (int, float))
            or not math.isfinite(float(factor))
            or float(factor) < 1.0
            for factor in factors.values()
        ):
            raise ValueError(
                "sensor environmental range-extension factors must be finite and at least one",
            )
        object.__setattr__(
            self,
            "extension_factors",
            MappingProxyType({sensor_type: float(factors[sensor_type]) for sensor_type in SensorType}),
        )


def sensor_environment_range_policy(
    *,
    calibration: Mapping[str, object],
    observer_domain: Domain,
    observer_altitude_m: float,
    observer_acclimatized: bool,
) -> SensorEnvironmentRangePolicy:
    """Build the shared production/restore range policy for an observer."""
    if not isinstance(calibration, Mapping):
        raise ValueError("calibration must be a mapping")
    _require_enum(observer_domain, Domain, label="observer_domain")
    if _policy_bool(calibration, "enable_thermal_crossover", False):
        thermal_extension = max(
            1.0,
            _policy_number(calibration, "thermal_contrast", 1.0),
        )
    else:
        thermal_extension = max(
            1.0,
            _policy_number(calibration, "night_thermal_floor", 0.8),
        )

    rain_exponent = _policy_number(
        calibration,
        "rain_attenuation_factor",
        1.0,
    )
    rain_extension = 1.0 if rain_exponent >= 0.0 else saturating_range_power(0.1, rain_exponent)
    icing_extension = 1.0
    if _policy_bool(
        calibration,
        "enable_air_combat_environment",
        False,
    ):
        icing_penalty_db = _policy_number(
            calibration,
            "icing_radar_penalty_db",
            3.0,
        )
        icing_extension = max(
            1.0,
            saturating_range_power(10.0, -icing_penalty_db / 40.0),
        )

    altitude_extension = targeting_altitude_range_factor(
        calibration=calibration,
        observer_altitude_m=observer_altitude_m,
        observer_acclimatized=observer_acclimatized,
    )
    observer_extension = 1.0
    if _policy_bool(calibration, "enable_human_factors", False):
        observer_extension = saturating_range_product(
            observer_extension,
            max(
                1.0,
                _policy_number(calibration, "mopp_fov_reduction_4", 0.7),
            ),
        )
    observer_extension = saturating_range_product(
        observer_extension,
        max(1.0, altitude_extension),
    )

    shared_extension = saturating_range_product(
        _TARGET_SIGNATURE_RANGE_EXTENSION,
        observer_extension,
    )
    radar_duct_extension = (
        _RADAR_DUCT_RANGE_EXTENSION
        if (
            _policy_bool(calibration, "enable_em_propagation", False)
            and observer_domain in {Domain.NAVAL, Domain.SUBMARINE}
        )
        else 1.0
    )
    acoustic_extension = (
        _ACOUSTIC_LAYER_RANGE_EXTENSION if _policy_bool(calibration, "enable_acoustic_layers", False) else 1.0
    )
    factors = {
        SensorType.VISUAL: shared_extension,
        SensorType.THERMAL: saturating_range_product(
            shared_extension,
            thermal_extension,
        ),
        SensorType.RADAR: saturating_range_product(
            shared_extension,
            radar_duct_extension,
            rain_extension,
            icing_extension,
        ),
        SensorType.PASSIVE_ACOUSTIC: saturating_range_product(
            shared_extension,
            acoustic_extension,
        ),
        SensorType.ACTIVE_SONAR: saturating_range_product(
            shared_extension,
            acoustic_extension,
        ),
        SensorType.PASSIVE_SONAR: saturating_range_product(
            shared_extension,
            acoustic_extension,
        ),
        SensorType.ESM: shared_extension,
        SensorType.SEISMIC: shared_extension,
        SensorType.MAD: shared_extension,
        SensorType.NVG: shared_extension,
    }
    return SensorEnvironmentRangePolicy(factors)


def sensor_environment_range_upper_bound_m(
    *,
    policy: SensorEnvironmentRangePolicy,
    sensor_type: SensorType,
    condition_adjusted_range_m: float,
) -> float:
    """Return the total production/restore ceiling for one live sensor.

    The policy covers every multiplicative range extension in the tactical
    production resolver: target naval posture, calibration-aware observer and
    thermal effects, radar weather/ducting, and the combined sonar
    surface-duct/convergence-zone path.
    """
    if not isinstance(policy, SensorEnvironmentRangePolicy):
        raise ValueError("policy must be a SensorEnvironmentRangePolicy")
    if not isinstance(sensor_type, SensorType):
        raise ValueError("sensor_type must be a SensorType")
    live_range = _require_non_negative_number(
        condition_adjusted_range_m,
        label="condition_adjusted_range_m",
    )
    return saturating_range_product(
        live_range,
        policy.extension_factors[sensor_type],
    )


@dataclass(frozen=True, slots=True)
class EffectiveRangeEvidence:
    """Catalog effective-range value with its exact provenance."""

    physical_max_range_m: float
    predictive_effective_range_m: float
    basis: EffectiveRangeBasis
    legacy_derived_reference_range_m: float

    def __post_init__(self) -> None:
        physical = _require_non_negative_number(
            self.physical_max_range_m,
            label="physical_max_range_m",
        )
        if physical <= 0.0:
            raise ValueError("physical_max_range_m must be positive")
        predictive = _require_non_negative_number(
            self.predictive_effective_range_m,
            label="predictive_effective_range_m",
        )
        legacy = _require_non_negative_number(
            self.legacy_derived_reference_range_m,
            label="legacy_derived_reference_range_m",
        )
        _require_enum(self.basis, EffectiveRangeBasis, label="basis")
        expected_legacy = physical * LEGACY_EFFECTIVE_RANGE_FRACTION
        if not math.isclose(legacy, expected_legacy, rel_tol=1e-12, abs_tol=1e-9):
            raise ValueError(
                "legacy_derived_reference_range_m must equal 80 percent of physical_max_range_m",
            )
        if self.basis is EffectiveRangeBasis.AUTHORED:
            if predictive <= 0.0 or predictive > physical:
                raise ValueError(
                    "authored predictive effective range must be positive and no greater than physical maximum",
                )
        elif predictive != 0.0:
            raise ValueError(
                "legacy-derived effective range is diagnostic only and the predictive range must be zero",
            )
        object.__setattr__(self, "physical_max_range_m", physical)
        object.__setattr__(self, "predictive_effective_range_m", predictive)
        object.__setattr__(self, "legacy_derived_reference_range_m", legacy)

    @classmethod
    def from_catalog(
        cls,
        *,
        physical_max_range_m: float,
        authored_effective_range_m: float | None,
    ) -> EffectiveRangeEvidence:
        """Classify one catalog range without promoting the legacy fallback."""
        physical = _require_non_negative_number(
            physical_max_range_m,
            label="physical_max_range_m",
        )
        if physical <= 0.0:
            raise ValueError("physical_max_range_m must be positive")
        authored = (
            0.0
            if authored_effective_range_m is None
            else _require_non_negative_number(
                authored_effective_range_m,
                label="authored_effective_range_m",
            )
        )
        basis = EffectiveRangeBasis.AUTHORED if authored > 0.0 else EffectiveRangeBasis.LEGACY_DERIVED_80_PERCENT_OF_MAX
        return cls(
            physical_max_range_m=physical,
            predictive_effective_range_m=(authored if authored > 0.0 else 0.0),
            basis=basis,
            legacy_derived_reference_range_m=(physical * LEGACY_EFFECTIVE_RANGE_FRACTION),
        )


def fire_control_source_is_compatible(
    *,
    weapon_role: WeaponModeledRole,
    shooter_domain: Domain,
    target_domain: Domain,
    source: FireControlSource,
    sensor_role: SensorModeledRole | None,
) -> bool:
    """Return whether the total role/domain policy admits fire control."""
    _require_enum(weapon_role, WeaponModeledRole, label="weapon_role")
    _require_enum(shooter_domain, Domain, label="shooter_domain")
    _require_enum(target_domain, Domain, label="target_domain")
    _require_enum(source, FireControlSource, label="source")
    if not weapon_role_supports_target_domain(
        weapon_role,
        target_domain,
    ):
        return False
    standoff_class = weapon_standoff_class(weapon_role)
    if source is FireControlSource.NONE:
        return False
    if source is FireControlSource.DIRECT_VISUAL:
        return sensor_role is None and (
            standoff_class is WeaponStandoffClass.ORGANIC_DIRECT_AIM or weapon_role in _CLOSE_DIRECT_ENGAGEMENT_ROLES
        )
    if not isinstance(sensor_role, SensorModeledRole):
        return False
    return (
        sensor_targeting_class(sensor_role) is SensorTargetingClass.LOCAL_FIRE_CONTROL
        and shooter_domain in allowed_shooter_domains_for_sensor_role(sensor_role)
        and target_domain in required_domains_for_sensor_role(sensor_role)
        and sensor_role in compatible_sensor_roles_for_weapon_role(weapon_role)
    )


def weapon_role_uses_tactical_direct_engagement(
    weapon_role: WeaponModeledRole,
) -> bool:
    """Return whether Phase 115 owns this role's direct engagement gate."""
    _require_enum(weapon_role, WeaponModeledRole, label="weapon_role")
    return (
        weapon_standoff_class(weapon_role) is not WeaponStandoffClass.UNSUPPORTED
        or weapon_role in _CLOSE_DIRECT_ENGAGEMENT_ROLES
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class TacticalTargetingDecision:
    """One immutable shooter answer shared by movement and engagement."""

    engine_tick: int
    logical_time_s: float
    battle_id: str
    ordinal: int
    shooter_id: str
    shooter_side: str
    shooter_domain: Domain
    target_id: str | None
    target_side: str | None
    target_domain: Domain | None
    distance_m: float
    weapon_id: str | None
    weapon_source_equipment_index: int | None
    weapon_modeled_role: WeaponModeledRole | None
    ammunition_id: str | None
    physical_max_range_m: float
    predictive_effective_range_m: float
    effective_range_basis: EffectiveRangeBasis | None
    legacy_derived_reference_range_m: float
    contact_source: ContactSource
    observing_unit_id: str | None
    contact_sensor_source_equipment_index: int | None
    contact_sensor_id: str | None
    contact_sensor_modeled_role: SensorModeledRole | None
    contact_time_s: float | None
    contact_range_m: float
    visibility_bound_m: float
    sensing_sensor_source_equipment_index: int | None
    sensing_sensor_id: str | None
    sensing_sensor_modeled_role: SensorModeledRole | None
    sensing_range_m: float
    fire_control_source: FireControlSource
    fire_control_sensor_source_equipment_index: int | None
    fire_control_sensor_id: str | None
    fire_control_sensor_modeled_role: SensorModeledRole | None
    fire_control_range_m: float
    disposition: TargetingDisposition
    authorized_standoff_m: float
    hold_authorized: bool
    engagement_solution_valid: bool
    sensing_aware_standoff_enabled: bool
    fog_of_war_enabled: bool
    consumable: bool = True
    observer_track_support: ObserverTrackSupportEvidence | None = None

    def __post_init__(self) -> None:
        self._validate_identity_and_scalars()
        self._validate_target_and_weapon()
        self._validate_contact_and_sensing()
        self._validate_fire_control()
        self._validate_outcome()

    @property
    def key(self) -> DecisionKey:
        """Return the non-overwriting runtime identity."""
        return (self.engine_tick, self.battle_id, self.shooter_id)

    @property
    def can_hold(self) -> bool:
        """Return whether a live consumer may apply automatic standoff."""
        return self.consumable and self.hold_authorized

    @property
    def can_engage(self) -> bool:
        """Return whether a live consumer may use the targeting solution."""
        return self.consumable and self.engagement_solution_valid

    def as_historical(self) -> TacticalTargetingDecision:
        """Return the same evidence barred from live movement or fire."""
        if not self.consumable:
            return self
        return replace(self, consumable=False)

    def _validate_identity_and_scalars(self) -> None:
        _require_non_negative_int(self.engine_tick, label="engine_tick")
        _require_non_negative_int(self.ordinal, label="ordinal")
        logical_time = _require_non_negative_number(
            self.logical_time_s,
            label="logical_time_s",
        )
        _require_identifier(self.battle_id, label="battle_id")
        _require_identifier(self.shooter_id, label="shooter_id")
        _require_identifier(self.shooter_side, label="shooter_side")
        _require_enum(self.shooter_domain, Domain, label="shooter_domain")
        for name in (
            "distance_m",
            "physical_max_range_m",
            "predictive_effective_range_m",
            "legacy_derived_reference_range_m",
            "contact_range_m",
            "visibility_bound_m",
            "sensing_range_m",
            "fire_control_range_m",
            "authorized_standoff_m",
        ):
            object.__setattr__(
                self,
                name,
                _require_non_negative_number(
                    getattr(self, name),
                    label=name,
                ),
            )
        object.__setattr__(self, "logical_time_s", logical_time)
        _require_bool(self.hold_authorized, label="hold_authorized")
        _require_bool(
            self.engagement_solution_valid,
            label="engagement_solution_valid",
        )
        _require_bool(
            self.sensing_aware_standoff_enabled,
            label="sensing_aware_standoff_enabled",
        )
        _require_bool(self.fog_of_war_enabled, label="fog_of_war_enabled")
        _require_bool(self.consumable, label="consumable")
        _require_enum(self.contact_source, ContactSource, label="contact_source")
        _require_enum(
            self.fire_control_source,
            FireControlSource,
            label="fire_control_source",
        )
        _require_enum(
            self.disposition,
            TargetingDisposition,
            label="disposition",
        )

    def _validate_target_and_weapon(self) -> None:
        target_id = _require_optional_identifier(
            self.target_id,
            label="target_id",
        )
        target_side = _require_optional_identifier(
            self.target_side,
            label="target_side",
        )
        if target_id is None:
            if target_side is not None or self.target_domain is not None:
                raise ValueError("target identity must be wholly present or absent")
            if self.distance_m != 0.0:
                raise ValueError("a targetless decision must have zero distance")
        else:
            if target_side is None or not isinstance(self.target_domain, Domain):
                raise ValueError("target identity must be wholly present or absent")
            if target_id == self.shooter_id:
                raise ValueError("a shooter cannot target itself")
            if target_side == self.shooter_side:
                raise ValueError("a tactical target must be hostile")

        weapon_id = _require_optional_identifier(
            self.weapon_id,
            label="weapon_id",
        )
        weapon_index = _require_optional_index(
            self.weapon_source_equipment_index,
            label="weapon_source_equipment_index",
        )
        ammunition_id = _require_optional_identifier(
            self.ammunition_id,
            label="ammunition_id",
        )
        if weapon_id is None:
            if (
                weapon_index is not None
                or self.weapon_modeled_role is not None
                or ammunition_id is not None
                or self.effective_range_basis is not None
                or self.physical_max_range_m != 0.0
                or self.predictive_effective_range_m != 0.0
                or self.legacy_derived_reference_range_m != 0.0
            ):
                raise ValueError("weapon evidence must be wholly absent")
            return
        if weapon_index is None or not isinstance(
            self.weapon_modeled_role,
            WeaponModeledRole,
        ):
            raise ValueError("selected weapon identity is incomplete")
        if not isinstance(self.effective_range_basis, EffectiveRangeBasis):
            raise ValueError("selected weapon effective-range basis is missing")
        EffectiveRangeEvidence(
            physical_max_range_m=self.physical_max_range_m,
            predictive_effective_range_m=self.predictive_effective_range_m,
            basis=self.effective_range_basis,
            legacy_derived_reference_range_m=(self.legacy_derived_reference_range_m),
        )

    def _validate_contact_and_sensing(self) -> None:
        support = self.observer_track_support
        if support is not None and type(support) is not ObserverTrackSupportEvidence:
            raise ValueError(
                "observer_track_support must be an ObserverTrackSupportEvidence",
            )
        observer = _require_optional_identifier(
            self.observing_unit_id,
            label="observing_unit_id",
        )
        contact_index = _require_optional_index(
            self.contact_sensor_source_equipment_index,
            label="contact_sensor_source_equipment_index",
        )
        contact_sensor_id = _require_optional_identifier(
            self.contact_sensor_id,
            label="contact_sensor_id",
        )
        contact_sensor_present = _require_optional_group(
            (
                contact_index,
                contact_sensor_id,
                self.contact_sensor_modeled_role,
            ),
            label="contact sensor",
        )
        if contact_sensor_present and not isinstance(
            self.contact_sensor_modeled_role,
            SensorModeledRole,
        ):
            raise ValueError("contact sensor modeled role is invalid")
        if self.contact_source is ContactSource.NONE:
            if (
                observer is not None
                or contact_sensor_present
                or self.contact_time_s is not None
                or self.contact_range_m != 0.0
                or support is not None
            ):
                raise ValueError("a no-contact decision cannot carry contact evidence")
            if self.target_id is not None:
                raise ValueError(
                    "a no-contact decision cannot expose a ground-truth target",
                )
        else:
            if observer is None or self.contact_time_s is None:
                raise ValueError("current contact requires observer and logical time")
            contact_time = _require_non_negative_number(
                self.contact_time_s,
                label="contact_time_s",
            )
            object.__setattr__(self, "contact_time_s", contact_time)
            if contact_time != self.logical_time_s:
                raise ValueError("contact evidence must be from the same interval")
            if observer != self.shooter_id:
                raise ValueError("offboard contact cannot supply local targeting")
            if self.target_id is None:
                raise ValueError("current contact requires a target")
            if self.contact_source is ContactSource.FOW_OBSERVER_WITNESS:
                if support is not None:
                    raise ValueError(
                        "FOW witness cannot carry observer track support evidence",
                    )
                if self.contact_range_m != self.distance_m:
                    raise ValueError(
                        "FOW witness range must equal the exact target distance",
                    )
            elif self.contact_source is ContactSource.FOW_OBSERVER_TRACK_SUPPORT:
                if support is None:
                    raise ValueError(
                        "FOW observer track support requires typed support evidence",
                    )
                if not contact_sensor_present:
                    raise ValueError(
                        "FOW observer track support requires an exact attachment",
                    )
                attachment = support.identity.attachment_identity
                if (
                    attachment.reporting_side != self.shooter_side
                    or attachment.observer_unit_id != observer
                    or support.identity.target_id != self.target_id
                    or attachment.source_equipment_index != contact_index
                    or attachment.sensor_id != contact_sensor_id
                    or attachment.modeled_role != self.contact_sensor_modeled_role.value
                ):
                    raise ValueError(
                        "FOW observer track support identity must match the decision exactly",
                    )
                if support.projection_time_s != self.logical_time_s:
                    raise ValueError(
                        "FOW observer track support projection must match logical time",
                    )
                if support.observation_time_s >= support.projection_time_s:
                    raise ValueError(
                        "FOW observer track support observation must precede its projection",
                    )
                if self.contact_range_m < self.distance_m:
                    raise ValueError(
                        "supported local contact cannot be shorter than the target distance",
                    )
            elif support is not None:
                raise ValueError(
                    "observer track support evidence requires its distinct contact source",
                )
            elif self.contact_range_m < self.distance_m:
                raise ValueError(
                    "current local contact cannot be shorter than the target distance",
                )
            if self.contact_source is ContactSource.FOW_OBSERVER_WITNESS and not contact_sensor_present:
                raise ValueError("FOW contact requires an exact observer witness")
        if self.fog_of_war_enabled:
            if self.contact_source is ContactSource.NON_FOW_LOCAL_OBSERVATION:
                raise ValueError("non-FOW contact cannot appear in a FOW decision")
        elif self.contact_source in {
            ContactSource.FOW_OBSERVER_WITNESS,
            ContactSource.FOW_OBSERVER_TRACK_SUPPORT,
        }:
            raise ValueError("FOW contact cannot appear when FOW is disabled")

        sensing_index = _require_optional_index(
            self.sensing_sensor_source_equipment_index,
            label="sensing_sensor_source_equipment_index",
        )
        sensing_sensor_id = _require_optional_identifier(
            self.sensing_sensor_id,
            label="sensing_sensor_id",
        )
        sensing_sensor_present = _require_optional_group(
            (
                sensing_index,
                sensing_sensor_id,
                self.sensing_sensor_modeled_role,
            ),
            label="sensing sensor",
        )
        if sensing_sensor_present and not isinstance(
            self.sensing_sensor_modeled_role,
            SensorModeledRole,
        ):
            raise ValueError("sensing sensor modeled role is invalid")
        contact_identity = (
            contact_index,
            contact_sensor_id,
            self.contact_sensor_modeled_role,
        )
        sensing_identity = (
            sensing_index,
            sensing_sensor_id,
            self.sensing_sensor_modeled_role,
        )
        if contact_identity != sensing_identity:
            raise ValueError(
                "contact and sensing attachment identity must match exactly",
            )
        if self.contact_range_m != self.sensing_range_m:
            raise ValueError("contact and sensing ranges must match exactly")
        if (
            self.contact_source is not ContactSource.NONE
            and not contact_sensor_present
            and self.contact_range_m > self.visibility_bound_m
        ):
            raise ValueError(
                "attachment-free contact exceeds the optical visibility bound",
            )

    def _validate_fire_control(self) -> None:
        control_index = _require_optional_index(
            self.fire_control_sensor_source_equipment_index,
            label="fire_control_sensor_source_equipment_index",
        )
        control_sensor_id = _require_optional_identifier(
            self.fire_control_sensor_id,
            label="fire_control_sensor_id",
        )
        control_sensor_present = _require_optional_group(
            (
                control_index,
                control_sensor_id,
                self.fire_control_sensor_modeled_role,
            ),
            label="fire-control sensor",
        )
        if control_sensor_present and not isinstance(
            self.fire_control_sensor_modeled_role,
            SensorModeledRole,
        ):
            raise ValueError("fire-control sensor modeled role is invalid")
        if self.fire_control_source is FireControlSource.NONE:
            if control_sensor_present or self.fire_control_range_m != 0.0:
                raise ValueError("absent fire control cannot carry source evidence")
        elif self.fire_control_source is FireControlSource.DIRECT_VISUAL:
            if control_sensor_present:
                raise ValueError("DIRECT_VISUAL is not a catalog sensor attachment")
            if self.fire_control_range_m > self.visibility_bound_m:
                raise ValueError(
                    "DIRECT_VISUAL range exceeds the optical visibility bound",
                )
        elif not control_sensor_present:
            raise ValueError("sensor fire control requires exact attachment identity")
        if self.contact_source is ContactSource.FOW_OBSERVER_TRACK_SUPPORT:
            if self.fire_control_source is not FireControlSource.SENSOR_ATTACHMENT:
                raise ValueError(
                    "FOW observer track support requires sensor-attachment fire control",
                )
            contact_identity = (
                self.contact_sensor_source_equipment_index,
                self.contact_sensor_id,
                self.contact_sensor_modeled_role,
            )
            control_identity = (
                control_index,
                control_sensor_id,
                self.fire_control_sensor_modeled_role,
            )
            if control_identity != contact_identity:
                raise ValueError(
                    "FOW observer track support requires the same fire-control attachment",
                )

    def _validate_outcome(self) -> None:
        valid_disposition = self.disposition in _VALID_ENGAGEMENT_DISPOSITIONS
        if self.engagement_solution_valid != valid_disposition:
            raise ValueError(
                "disposition and engagement_solution_valid disagree",
            )
        if self.disposition in _TARGETLESS_DISPOSITIONS:
            if self.target_id is not None:
                raise ValueError("targetless disposition cannot expose a target")
        elif self.target_id is None:
            raise ValueError("selected-target disposition requires a target")

        if not self.engagement_solution_valid:
            if self.authorized_standoff_m != 0.0 or self.hold_authorized:
                raise ValueError(
                    "an invalid engagement solution cannot authorize standoff",
                )
            return

        if (
            self.target_id is None
            or self.weapon_id is None
            or self.weapon_modeled_role is None
            or self.ammunition_id is None
            or self.contact_source is ContactSource.NONE
            or self.fire_control_source is FireControlSource.NONE
        ):
            raise ValueError("valid engagement solution is missing required evidence")
        if not weapon_role_uses_tactical_direct_engagement(
            self.weapon_modeled_role,
        ):
            raise ValueError("routed weapon role cannot be a direct solution")
        assert self.target_domain is not None
        for label, sensor_role in (
            ("contact", self.contact_sensor_modeled_role),
            ("sensing", self.sensing_sensor_modeled_role),
        ):
            if sensor_role is not None and (
                self.shooter_domain not in allowed_shooter_domains_for_sensor_role(sensor_role)
                or self.target_domain not in required_domains_for_sensor_role(sensor_role)
            ):
                raise ValueError(
                    f"{label} sensor role is incompatible with shooter or target domain",
                )
        if not fire_control_source_is_compatible(
            weapon_role=self.weapon_modeled_role,
            shooter_domain=self.shooter_domain,
            target_domain=self.target_domain,
            source=self.fire_control_source,
            sensor_role=self.fire_control_sensor_modeled_role,
        ):
            raise ValueError("fire-control source is incompatible with weapon role")
        if (
            self.distance_m > self.physical_max_range_m
            or self.distance_m > self.contact_range_m
            or self.distance_m > self.sensing_range_m
            or self.distance_m > self.fire_control_range_m
        ):
            raise ValueError("valid engagement solution exceeds a live range bound")
        if self.fire_control_source is FireControlSource.DIRECT_VISUAL and self.distance_m > self.visibility_bound_m:
            raise ValueError("DIRECT_VISUAL exceeds the optical visibility bound")
        if (
            self.fog_of_war_enabled
            and self.fire_control_source is FireControlSource.DIRECT_VISUAL
            and self.contact_sensor_modeled_role not in _FOW_DIRECT_VISUAL_WITNESS_ROLES
        ):
            raise ValueError(
                "FOW DIRECT_VISUAL requires a current visual witness",
            )
        if self.effective_range_basis is EffectiveRangeBasis.AUTHORED:
            if self.distance_m > self.predictive_effective_range_m:
                raise ValueError("valid solution exceeds authored effective range")
        elif self.disposition is not TargetingDisposition.EFFECTIVE_RANGE_UNKNOWN:
            raise ValueError(
                "legacy-derived weapon solution must expose EFFECTIVE_RANGE_UNKNOWN",
            )

        standoff_class = weapon_standoff_class(self.weapon_modeled_role)
        if self.effective_range_basis is not EffectiveRangeBasis.AUTHORED:
            if self.authorized_standoff_m != 0.0:
                raise ValueError("legacy-derived range cannot authorize standoff")
        elif not self.sensing_aware_standoff_enabled:
            if self.disposition is not TargetingDisposition.STANDOFF_DISABLED or self.authorized_standoff_m != 0.0:
                raise ValueError("disabled standoff must expose zero authorization")
        elif standoff_class is WeaponStandoffClass.UNSUPPORTED:
            if (
                self.disposition is not TargetingDisposition.STANDOFF_NOT_SUPPORTED_FOR_ROLE
                or self.authorized_standoff_m != 0.0
            ):
                raise ValueError("unsupported standoff role must authorize zero hold")
        elif self.authorized_standoff_m > min(
            self.physical_max_range_m,
            self.predictive_effective_range_m,
            self.contact_range_m,
            self.sensing_range_m,
            self.fire_control_range_m,
        ):
            raise ValueError("authorized standoff exceeds a live limiting range")

        expected_hold = (
            self.sensing_aware_standoff_enabled
            and self.effective_range_basis is EffectiveRangeBasis.AUTHORED
            and standoff_class is not WeaponStandoffClass.UNSUPPORTED
            and self.authorized_standoff_m > 0.0
            and self.distance_m <= self.authorized_standoff_m
        )
        if self.hold_authorized != expected_hold:
            raise ValueError("hold_authorized disagrees with the limiting ranges")
        if self.hold_authorized:
            if self.disposition is not TargetingDisposition.VALID_STANDOFF_HOLD:
                raise ValueError("authorized hold requires VALID_STANDOFF_HOLD")
        elif self.disposition is TargetingDisposition.VALID_STANDOFF_HOLD:
            raise ValueError("VALID_STANDOFF_HOLD requires an authorized hold")


@dataclass(frozen=True, slots=True, kw_only=True)
class TacticalEngagementRevalidationOutcome:
    """Immutable result of consuming one decision after tactical movement.

    This record answers only whether the exact targeting solution remained
    valid after movement.  It deliberately does not claim that later ROE,
    morale, cooldown, hit, or damage gates committed a shot.
    """

    engine_tick: int
    logical_time_s: float
    battle_id: str
    shooter_id: str
    target_id: str
    weapon_id: str
    weapon_source_equipment_index: int
    weapon_modeled_role: WeaponModeledRole
    ammunition_id: str
    disposition: TargetingDisposition
    revalidation_passed: bool
    fog_of_war_enabled: bool
    consumable: bool = True

    def __post_init__(self) -> None:
        _require_non_negative_int(
            self.engine_tick,
            label="revalidation engine_tick",
        )
        logical_time = _require_non_negative_number(
            self.logical_time_s,
            label="revalidation logical_time_s",
        )
        _require_identifier(self.battle_id, label="revalidation battle_id")
        _require_identifier(self.shooter_id, label="revalidation shooter_id")
        _require_identifier(self.target_id, label="revalidation target_id")
        _require_identifier(self.weapon_id, label="revalidation weapon_id")
        _require_non_negative_int(
            self.weapon_source_equipment_index,
            label="revalidation weapon_source_equipment_index",
        )
        _require_enum(
            self.weapon_modeled_role,
            WeaponModeledRole,
            label="revalidation weapon_modeled_role",
        )
        _require_identifier(
            self.ammunition_id,
            label="revalidation ammunition_id",
        )
        _require_enum(
            self.disposition,
            TargetingDisposition,
            label="revalidation disposition",
        )
        passed = _require_bool(
            self.revalidation_passed,
            label="revalidation_passed",
        )
        _require_bool(
            self.fog_of_war_enabled,
            label="revalidation fog_of_war_enabled",
        )
        _require_bool(self.consumable, label="revalidation consumable")
        if passed:
            if self.disposition is not (TargetingDisposition.VALID_ENGAGEMENT_SOLUTION):
                raise ValueError(
                    "a passed targeting revalidation must expose VALID_ENGAGEMENT_SOLUTION",
                )
        elif self.disposition in _VALID_ENGAGEMENT_DISPOSITIONS:
            raise ValueError(
                "a failed targeting revalidation requires a rejection disposition",
            )
        object.__setattr__(self, "logical_time_s", logical_time)

    @property
    def key(self) -> DecisionKey:
        """Return the exact published-decision identity."""
        return (self.engine_tick, self.battle_id, self.shooter_id)

    def as_historical(self) -> TacticalEngagementRevalidationOutcome:
        """Return the same evidence barred from live consumption."""
        if not self.consumable:
            return self
        return replace(self, consumable=False)


def _validate_revalidation_against_decision(
    outcome: TacticalEngagementRevalidationOutcome,
    decision: TacticalTargetingDecision,
) -> None:
    """Require one outcome to identify one exact engagement decision."""
    if not isinstance(outcome, TacticalEngagementRevalidationOutcome):
        raise ValueError(
            "outcome must be a TacticalEngagementRevalidationOutcome",
        )
    if not isinstance(decision, TacticalTargetingDecision):
        raise ValueError("decision must be a TacticalTargetingDecision")
    if outcome.key != decision.key:
        raise ValueError("revalidation key disagrees with targeting decision")
    if outcome.logical_time_s != decision.logical_time_s:
        raise ValueError(
            "revalidation logical time disagrees with targeting decision",
        )
    if outcome.fog_of_war_enabled is not decision.fog_of_war_enabled:
        raise ValueError("revalidation FOW mode disagrees with targeting decision")
    if outcome.consumable is not decision.consumable:
        raise ValueError(
            "revalidation consumability disagrees with targeting decision",
        )
    if not decision.engagement_solution_valid:
        raise ValueError("revalidation requires a valid engagement solution")
    expected_identity = (
        decision.target_id,
        decision.weapon_id,
        decision.weapon_source_equipment_index,
        decision.weapon_modeled_role,
        decision.ammunition_id,
    )
    if None in expected_identity:
        raise ValueError("engagement decision lacks exact revalidation identity")
    if (
        outcome.target_id,
        outcome.weapon_id,
        outcome.weapon_source_equipment_index,
        outcome.weapon_modeled_role,
        outcome.ammunition_id,
    ) != expected_identity:
        raise ValueError(
            "revalidation target, weapon, or ammunition disagrees with decision",
        )


@dataclass(frozen=True, slots=True)
class TacticalTargetingPicture:
    """Immutable targeting decisions for one battle in one interval."""

    engine_tick: int
    logical_time_s: float
    battle_id: str
    fog_of_war_enabled: bool
    decisions: tuple[TacticalTargetingDecision, ...]
    _by_shooter: Mapping[str, TacticalTargetingDecision] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        _require_non_negative_int(self.engine_tick, label="picture engine_tick")
        logical_time = _require_non_negative_number(
            self.logical_time_s,
            label="picture logical_time_s",
        )
        _require_identifier(self.battle_id, label="picture battle_id")
        _require_bool(
            self.fog_of_war_enabled,
            label="picture fog_of_war_enabled",
        )
        if not isinstance(self.decisions, tuple):
            raise ValueError("picture decisions must be an immutable tuple")
        expected_order = tuple(
            sorted(
                self.decisions,
                key=lambda decision: (
                    decision.shooter_side,
                    decision.shooter_id,
                ),
            )
        )
        if self.decisions != expected_order:
            raise ValueError("picture decisions are not in canonical shooter order")
        by_shooter: dict[str, TacticalTargetingDecision] = {}
        for ordinal, decision in enumerate(self.decisions):
            if (
                decision.engine_tick != self.engine_tick
                or decision.logical_time_s != logical_time
                or decision.battle_id != self.battle_id
                or decision.fog_of_war_enabled != self.fog_of_war_enabled
            ):
                raise ValueError("picture contains a cross-interval decision")
            if decision.ordinal != ordinal:
                raise ValueError("picture decision ordinal is not canonical")
            if decision.shooter_id in by_shooter:
                raise ValueError("picture contains a duplicate shooter decision")
            by_shooter[decision.shooter_id] = decision
        object.__setattr__(self, "logical_time_s", logical_time)
        object.__setattr__(self, "_by_shooter", MappingProxyType(by_shooter))

    def decision_for(self, shooter_id: str) -> TacticalTargetingDecision | None:
        """Return the exact shooter decision without recomputation."""
        _require_identifier(shooter_id, label="shooter_id")
        return self._by_shooter.get(shooter_id)


@dataclass(frozen=True, slots=True)
class TargetingInterval:
    """Canonical prepared topology for one engine tactical interval."""

    engine_tick: int
    logical_time_s: float
    fog_of_war_enabled: bool
    unit_side_items: tuple[tuple[str, str], ...]
    battle_membership_items: tuple[tuple[str, tuple[str, ...]], ...]
    _unit_sides: Mapping[str, str] = field(
        init=False,
        repr=False,
        compare=False,
    )
    _battle_memberships: Mapping[str, tuple[str, ...]] = field(
        init=False,
        repr=False,
        compare=False,
    )
    _battle_ids: tuple[str, ...] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        """Cache immutable indexes once for every interval consumer."""
        unit_sides = dict(self.unit_side_items)
        battle_memberships = dict(self.battle_membership_items)
        if len(unit_sides) != len(self.unit_side_items):
            raise ValueError("targeting interval contains duplicate unit IDs")
        if len(battle_memberships) != len(self.battle_membership_items):
            raise ValueError("targeting interval contains duplicate battle IDs")
        object.__setattr__(
            self,
            "_unit_sides",
            MappingProxyType(unit_sides),
        )
        object.__setattr__(
            self,
            "_battle_memberships",
            MappingProxyType(battle_memberships),
        )
        object.__setattr__(
            self,
            "_battle_ids",
            tuple(battle_memberships),
        )

    @property
    def unit_sides(self) -> Mapping[str, str]:
        """Return immutable registered unit-side topology."""
        return self._unit_sides

    @property
    def battle_memberships(self) -> Mapping[str, tuple[str, ...]]:
        """Return immutable canonical battle membership."""
        return self._battle_memberships

    @property
    def battle_ids(self) -> tuple[str, ...]:
        """Return canonical active battle order."""
        return self._battle_ids


@dataclass(frozen=True, slots=True)
class TacticalTargetingRestorePlan:
    """Validated state that can be committed without further failure."""

    registered_unit_side_items: tuple[tuple[str, str], ...]
    prepared_interval: TargetingInterval | None
    published_battle_ids: tuple[str, ...]
    latest_pictures: tuple[TacticalTargetingPicture, ...]
    latest_engagement_revalidations: tuple[
        TacticalEngagementRevalidationOutcome,
        ...,
    ]


@dataclass(frozen=True, slots=True)
class _TacticalTargetingSnapshot:
    """One immutable runtime publication swapped by a single assignment."""

    registered_unit_sides: Mapping[str, str]
    prepared_interval: TargetingInterval | None
    published_battle_ids: tuple[str, ...]
    latest_pictures: Mapping[str, TacticalTargetingPicture]
    latest_engagement_revalidations: Mapping[
        DecisionKey,
        TacticalEngagementRevalidationOutcome,
    ]


@dataclass(frozen=True, slots=True)
class TacticalTargetingPublicationPlan:
    """Owner-bound, fully validated interval publication snapshot."""

    pictures: tuple[TacticalTargetingPicture, ...]
    _snapshot: _TacticalTargetingSnapshot
    _prior_snapshot: _TacticalTargetingSnapshot
    _owner_token: object


class TacticalTargetingRuntime:
    """Simulation-owned publisher for bounded, same-interval decisions."""

    _STATE_KEYS = frozenset(
        {
            "sensing_aware_standoff_enabled",
            "registered_unit_sides",
            "prepared_interval",
            "published_battle_ids",
            "latest_pictures",
            "latest_engagement_revalidations",
        }
    )

    def __init__(
        self,
        *,
        sensing_aware_standoff_enabled: bool,
        unit_sides: Mapping[str, str] | None = None,
    ) -> None:
        self._sensing_aware_standoff_enabled = _require_bool(
            sensing_aware_standoff_enabled,
            label="sensing_aware_standoff_enabled",
        )
        self._publication_owner_token = object()
        self._snapshot = _TacticalTargetingSnapshot(
            registered_unit_sides=MappingProxyType(
                _normalize_unit_sides(
                    {} if unit_sides is None else unit_sides,
                ),
            ),
            prepared_interval=None,
            published_battle_ids=(),
            latest_pictures=MappingProxyType({}),
            latest_engagement_revalidations=MappingProxyType({}),
        )

    @property
    def sensing_aware_standoff_enabled(self) -> bool:
        """Return immutable calibration enablement."""
        return self._sensing_aware_standoff_enabled

    @property
    def prepared_interval(self) -> TargetingInterval | None:
        """Return the current immutable interval topology."""
        return self._snapshot.prepared_interval

    @property
    def registered_unit_sides(self) -> Mapping[str, str]:
        """Return the exact immutable force topology known to the runtime."""
        return self._snapshot.registered_unit_sides

    def register_units(self, unit_sides: Mapping[str, str]) -> None:
        """Atomically register reinforcement identities and invalidate history.

        Dynamic registration happens outside a prepared tactical interval.  A
        genuine topology change clears the prior prepared/picture state so no
        decision built against an older roster can remain consumable.
        """
        additions = _normalize_unit_sides(unit_sides)
        registered = self._snapshot.registered_unit_sides
        staged = dict(registered)
        for unit_id, side in additions.items():
            previous_side = staged.get(unit_id)
            if previous_side is not None and previous_side != side:
                raise ValueError(
                    f"registered targeting unit {unit_id!r} changed side",
                )
            staged[unit_id] = side
        if staged == dict(registered):
            return
        self._snapshot = _TacticalTargetingSnapshot(
            registered_unit_sides=MappingProxyType(
                dict(sorted(staged.items())),
            ),
            prepared_interval=None,
            published_battle_ids=(),
            latest_pictures=MappingProxyType({}),
            latest_engagement_revalidations=MappingProxyType({}),
        )

    def replace_registered_units(
        self,
        *,
        expected_current: Mapping[str, str],
        replacement: Mapping[str, str],
    ) -> None:
        """Compare-and-replace the exact topology and invalidate history.

        Aggregation and disaggregation remove as well as add identities, so
        their roster transaction cannot use the additive reinforcement API.
        Both maps are validated before comparing the expected topology with
        the live owner.  Stale transactions reject without mutation.  A
        genuine replacement invalidates every interval-bound picture and
        revalidation.
        """
        expected = _normalize_unit_sides(expected_current)
        normalized_replacement = _normalize_unit_sides(replacement)
        if expected != dict(self._snapshot.registered_unit_sides):
            raise ValueError(
                "registered targeting topology changed before replacement",
            )
        if normalized_replacement == expected:
            return
        self._snapshot = _TacticalTargetingSnapshot(
            registered_unit_sides=MappingProxyType(normalized_replacement),
            prepared_interval=None,
            published_battle_ids=(),
            latest_pictures=MappingProxyType({}),
            latest_engagement_revalidations=MappingProxyType({}),
        )

    def validate_interval_advance(
        self,
        *,
        engine_tick: int,
        logical_time_s: float,
    ) -> None:
        """Reject a repeated or regressing interval without mutating state."""
        next_tick = _require_non_negative_int(
            engine_tick,
            label="targeting interval engine_tick",
        )
        next_time = _require_non_negative_number(
            logical_time_s,
            label="targeting interval logical_time_s",
        )
        previous = self._snapshot.prepared_interval
        if previous is None:
            return
        if next_tick <= previous.engine_tick:
            raise ValueError(
                "targeting interval must advance to a strictly newer tick",
            )
        if next_time < previous.logical_time_s:
            raise ValueError("targeting logical time cannot move backwards")

    def stage_interval(
        self,
        *,
        engine_tick: int,
        logical_time_s: float,
        fog_of_war_enabled: bool,
        unit_sides: Mapping[str, str],
        battle_memberships: Mapping[str, Collection[str]],
    ) -> TargetingInterval:
        """Validate and return a newer interval without mutating runtime state."""
        self.validate_interval_advance(
            engine_tick=engine_tick,
            logical_time_s=logical_time_s,
        )
        interval = _build_interval(
            engine_tick=engine_tick,
            logical_time_s=logical_time_s,
            fog_of_war_enabled=fog_of_war_enabled,
            unit_sides=unit_sides,
            battle_memberships=battle_memberships,
        )
        if interval.unit_sides != self._snapshot.registered_unit_sides:
            raise ValueError(
                "prepared targeting unit topology must equal registered topology",
            )
        return interval

    def _validate_picture_for_interval(
        self,
        picture: TacticalTargetingPicture,
        *,
        interval: TargetingInterval,
        expected_battle_id: str,
    ) -> None:
        """Validate one picture against an immutable staged interval."""
        if not isinstance(picture, TacticalTargetingPicture):
            raise ValueError("picture must be a TacticalTargetingPicture")
        if picture.battle_id != expected_battle_id:
            raise ValueError(
                "battle pictures must publish in canonical battle-ID order",
            )
        if (
            picture.engine_tick != interval.engine_tick
            or picture.logical_time_s != interval.logical_time_s
            or picture.fog_of_war_enabled != interval.fog_of_war_enabled
        ):
            raise ValueError("picture does not match the prepared interval")
        members = interval.battle_memberships[picture.battle_id]
        if {decision.shooter_id for decision in picture.decisions} != set(members):
            raise ValueError(
                "picture must contain exactly one decision per battle member",
            )
        sides = interval.unit_sides
        for decision in picture.decisions:
            if decision.shooter_side != sides[decision.shooter_id]:
                raise ValueError("decision shooter side disagrees with topology")
            if decision.sensing_aware_standoff_enabled is not self._sensing_aware_standoff_enabled:
                raise ValueError("decision standoff enablement disagrees with runtime")
            if not decision.consumable:
                raise ValueError("new targeting pictures must be consumable")
            if decision.target_id is not None:
                if decision.target_id not in members or decision.target_side != sides[decision.target_id]:
                    raise ValueError(
                        "decision target is outside exact battle topology",
                    )

    def stage_publication(
        self,
        interval: TargetingInterval,
        pictures: tuple[TacticalTargetingPicture, ...],
    ) -> TacticalTargetingPublicationPlan:
        """Validate a complete picture set without publishing it."""
        if not isinstance(interval, TargetingInterval):
            raise ValueError("interval must be a TargetingInterval")
        if not isinstance(pictures, tuple):
            raise ValueError("interval pictures must be an immutable tuple")
        try:
            canonical_interval = _build_interval(
                engine_tick=interval.engine_tick,
                logical_time_s=interval.logical_time_s,
                fog_of_war_enabled=interval.fog_of_war_enabled,
                unit_sides=dict(interval.unit_side_items),
                battle_memberships=dict(
                    interval.battle_membership_items,
                ),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("published targeting interval is invalid") from exc
        if interval != canonical_interval:
            raise ValueError(
                "published targeting interval is not a canonical interval",
            )
        self.validate_interval_advance(
            engine_tick=interval.engine_tick,
            logical_time_s=interval.logical_time_s,
        )
        if interval.unit_sides != self._snapshot.registered_unit_sides:
            raise ValueError(
                "published targeting unit topology must equal registered topology",
            )
        if len(pictures) != len(interval.battle_ids):
            raise ValueError(
                "complete interval publication requires one picture per battle",
            )
        for expected_battle_id, picture in zip(interval.battle_ids, pictures):
            self._validate_picture_for_interval(
                picture,
                interval=interval,
                expected_battle_id=expected_battle_id,
            )

        staged_pictures = {picture.battle_id: picture for picture in pictures}
        snapshot = _TacticalTargetingSnapshot(
            registered_unit_sides=self._snapshot.registered_unit_sides,
            prepared_interval=interval,
            published_battle_ids=interval.battle_ids,
            latest_pictures=MappingProxyType(staged_pictures),
            latest_engagement_revalidations=MappingProxyType({}),
        )
        return TacticalTargetingPublicationPlan(
            pictures=pictures,
            _snapshot=snapshot,
            _prior_snapshot=self._snapshot,
            _owner_token=self._publication_owner_token,
        )

    def validate_publication_plan(
        self,
        plan: TacticalTargetingPublicationPlan,
    ) -> None:
        """Reject a foreign or stale plan before an outer commit begins."""
        if type(plan) is not TacticalTargetingPublicationPlan:
            raise ValueError(
                "plan must be a TacticalTargetingPublicationPlan",
            )
        if plan._owner_token is not self._publication_owner_token:
            raise ValueError(
                "targeting publication plan belongs to another runtime",
            )
        if plan._prior_snapshot is not self._snapshot:
            raise ValueError("targeting publication plan is stale")

    def _commit_prevalidated_publication(
        self,
        plan: TacticalTargetingPublicationPlan,
    ) -> tuple[TacticalTargetingPicture, ...]:
        """Publish a prevalidated snapshot with one non-throwing assignment."""
        self._snapshot = plan._snapshot
        return plan.pictures

    def commit_publication(
        self,
        plan: TacticalTargetingPublicationPlan,
    ) -> tuple[TacticalTargetingPicture, ...]:
        """Validate and commit a staged interval publication."""
        self.validate_publication_plan(plan)
        return self._commit_prevalidated_publication(plan)

    def publish_interval(
        self,
        interval: TargetingInterval,
        pictures: tuple[TacticalTargetingPicture, ...],
    ) -> tuple[TacticalTargetingPicture, ...]:
        """Compatibility boundary that stages and commits one interval."""
        return self.commit_publication(
            self.stage_publication(interval, pictures),
        )

    def latest_picture(
        self,
        battle_id: str,
    ) -> TacticalTargetingPicture | None:
        """Return the bounded latest picture for a battle."""
        _require_identifier(battle_id, label="battle_id")
        return self._snapshot.latest_pictures.get(battle_id)

    def latest_pictures(self) -> tuple[TacticalTargetingPicture, ...]:
        """Return latest pictures in canonical battle-ID order."""
        pictures = self._snapshot.latest_pictures
        return tuple(pictures[battle_id] for battle_id in sorted(pictures))

    def decision_for(
        self,
        *,
        engine_tick: int,
        battle_id: str,
        shooter_id: str,
        require_consumable: bool = True,
    ) -> TacticalTargetingDecision | None:
        """Return one exact published decision without reconstructing it."""
        _require_non_negative_int(engine_tick, label="engine_tick")
        _require_identifier(battle_id, label="battle_id")
        _require_identifier(shooter_id, label="shooter_id")
        _require_bool(require_consumable, label="require_consumable")
        picture = self._snapshot.latest_pictures.get(battle_id)
        if picture is None or picture.engine_tick != engine_tick:
            return None
        decision = picture.decision_for(shooter_id)
        if decision is None or (require_consumable and not decision.consumable):
            return None
        return decision

    def publish_engagement_revalidation(
        self,
        outcome: TacticalEngagementRevalidationOutcome,
    ) -> TacticalEngagementRevalidationOutcome:
        """Publish one post-movement result for an exact live decision."""
        if not isinstance(outcome, TacticalEngagementRevalidationOutcome):
            raise ValueError(
                "outcome must be a TacticalEngagementRevalidationOutcome",
            )
        snapshot = self._snapshot
        interval = snapshot.prepared_interval
        if interval is None:
            raise ValueError("targeting interval has not been prepared")
        if (
            outcome.engine_tick != interval.engine_tick
            or outcome.logical_time_s != interval.logical_time_s
            or outcome.fog_of_war_enabled is not interval.fog_of_war_enabled
        ):
            raise ValueError(
                "revalidation does not match the prepared interval",
            )
        if outcome.battle_id not in snapshot.published_battle_ids:
            raise ValueError(
                "revalidation requires a current published battle picture",
            )
        picture = snapshot.latest_pictures.get(outcome.battle_id)
        decision = (
            None
            if picture is None or picture.engine_tick != outcome.engine_tick
            else picture.decision_for(outcome.shooter_id)
        )
        if decision is None:
            raise ValueError(
                "revalidation does not identify a current published decision",
            )
        if not outcome.consumable or not decision.consumable:
            raise ValueError("new targeting revalidations must be consumable")
        _validate_revalidation_against_decision(outcome, decision)
        if outcome.key in snapshot.latest_engagement_revalidations:
            raise ValueError("duplicate targeting revalidation key")
        staged = dict(snapshot.latest_engagement_revalidations)
        staged[outcome.key] = outcome
        self._snapshot = _TacticalTargetingSnapshot(
            registered_unit_sides=snapshot.registered_unit_sides,
            prepared_interval=interval,
            published_battle_ids=snapshot.published_battle_ids,
            latest_pictures=snapshot.latest_pictures,
            latest_engagement_revalidations=MappingProxyType(staged),
        )
        return outcome

    def engagement_revalidation_for(
        self,
        *,
        engine_tick: int,
        battle_id: str,
        shooter_id: str,
        require_consumable: bool = True,
    ) -> TacticalEngagementRevalidationOutcome | None:
        """Return one exact post-movement result without reconstructing it."""
        key = (
            _require_non_negative_int(engine_tick, label="engine_tick"),
            _require_identifier(battle_id, label="battle_id"),
            _require_identifier(shooter_id, label="shooter_id"),
        )
        _require_bool(require_consumable, label="require_consumable")
        outcome = self._snapshot.latest_engagement_revalidations.get(key)
        if outcome is None or (require_consumable and not outcome.consumable):
            return None
        return outcome

    def latest_engagement_revalidations(
        self,
    ) -> tuple[TacticalEngagementRevalidationOutcome, ...]:
        """Return bounded outcomes in canonical exact-key order."""
        outcomes = self._snapshot.latest_engagement_revalidations
        return tuple(outcomes[key] for key in sorted(outcomes))

    def get_state(self) -> dict[str, Any]:
        """Return exact scalar/enum/ID-only targeting state."""
        snapshot = self._snapshot
        return {
            "sensing_aware_standoff_enabled": (self._sensing_aware_standoff_enabled),
            "registered_unit_sides": [
                {"unit_id": unit_id, "side": side} for unit_id, side in snapshot.registered_unit_sides.items()
            ],
            "prepared_interval": _interval_to_state(snapshot.prepared_interval),
            "published_battle_ids": list(snapshot.published_battle_ids),
            "latest_pictures": [
                _picture_to_state(snapshot.latest_pictures[battle_id]) for battle_id in sorted(snapshot.latest_pictures)
            ],
            "latest_engagement_revalidations": [
                _revalidation_outcome_to_state(
                    snapshot.latest_engagement_revalidations[key],
                )
                for key in sorted(snapshot.latest_engagement_revalidations)
            ],
        }

    def stage_state(
        self,
        state: object,
        *,
        expected_unit_sides: Mapping[str, str] | None = None,
        expected_battle_memberships: Mapping[str, Collection[str]] | None = None,
        expected_engine_tick: int | None = None,
        expected_logical_time_s: float | None = None,
    ) -> TacticalTargetingRestorePlan:
        """Validate checkpoint state without mutating the live runtime."""
        if not isinstance(state, dict) or set(state) != self._STATE_KEYS:
            raise ValueError("targeting state has invalid key topology")
        enabled = _require_bool(
            state["sensing_aware_standoff_enabled"],
            label="state sensing_aware_standoff_enabled",
        )
        if enabled is not self._sensing_aware_standoff_enabled:
            raise ValueError("targeting checkpoint enablement mismatch")
        registered_sides = _unit_sides_from_state(
            state["registered_unit_sides"],
            label="registered_unit_sides",
        )
        if registered_sides != self._snapshot.registered_unit_sides:
            raise ValueError("targeting checkpoint registered roster mismatch")
        raw_interval = state["prepared_interval"]
        interval = None if raw_interval is None else _interval_from_state(raw_interval)
        published = _published_battle_ids_from_state(
            state["published_battle_ids"],
        )
        raw_pictures = state["latest_pictures"]
        if not isinstance(raw_pictures, list):
            raise ValueError("targeting latest_pictures must be a list")
        pictures = tuple(
            _picture_from_state(
                value,
                label=f"latest_pictures[{index}]",
            )
            for index, value in enumerate(raw_pictures)
        )
        if tuple(picture.battle_id for picture in pictures) != tuple(sorted(picture.battle_id for picture in pictures)):
            raise ValueError("targeting latest pictures are not canonical")
        if len({picture.battle_id for picture in pictures}) != len(pictures):
            raise ValueError("targeting state contains duplicate battle pictures")
        raw_revalidations = state["latest_engagement_revalidations"]
        if not isinstance(raw_revalidations, list):
            raise ValueError(
                "targeting latest_engagement_revalidations must be a list",
            )
        revalidations = tuple(
            _revalidation_outcome_from_state(
                value,
                label=f"latest_engagement_revalidations[{index}]",
            )
            for index, value in enumerate(raw_revalidations)
        )
        if tuple(outcome.key for outcome in revalidations) != tuple(sorted(outcome.key for outcome in revalidations)):
            raise ValueError(
                "targeting engagement revalidations are not canonical",
            )
        if len({outcome.key for outcome in revalidations}) != len(revalidations):
            raise ValueError(
                "targeting state contains duplicate engagement revalidations",
            )
        if interval is None:
            if published or pictures or revalidations:
                raise ValueError(
                    "unprepared targeting state cannot contain targeting evidence",
                )
            if expected_engine_tick is not None or expected_logical_time_s is not None:
                raise ValueError("expected interval time requires a prepared interval")
            if expected_battle_memberships is not None:
                raise ValueError("expected battles require a prepared interval")
            if expected_unit_sides is not None and registered_sides != (_normalize_unit_sides(expected_unit_sides)):
                raise ValueError("registered targeting topology mismatch")
            return TacticalTargetingRestorePlan(
                registered_unit_side_items=tuple(registered_sides.items()),
                prepared_interval=None,
                published_battle_ids=(),
                latest_pictures=(),
                latest_engagement_revalidations=(),
            )

        if interval.unit_sides != registered_sides:
            raise ValueError(
                "prepared targeting topology disagrees with registered roster",
            )

        if expected_engine_tick is not None and interval.engine_tick != (
            _require_non_negative_int(
                expected_engine_tick,
                label="expected_engine_tick",
            )
        ):
            raise ValueError("targeting checkpoint engine tick mismatch")
        if expected_logical_time_s is not None and interval.logical_time_s != (
            _require_non_negative_number(
                expected_logical_time_s,
                label="expected_logical_time_s",
            )
        ):
            raise ValueError("targeting checkpoint logical time mismatch")
        if (expected_unit_sides is None) != (expected_battle_memberships is None):
            raise ValueError(
                "expected targeting unit and battle topology must be supplied together",
            )
        if expected_unit_sides is not None:
            expected = _build_interval(
                engine_tick=interval.engine_tick,
                logical_time_s=interval.logical_time_s,
                fog_of_war_enabled=interval.fog_of_war_enabled,
                unit_sides=expected_unit_sides,
                battle_memberships=expected_battle_memberships,
            )
            if (
                interval.unit_side_items != expected.unit_side_items
                or interval.battle_membership_items != expected.battle_membership_items
            ):
                raise ValueError("targeting checkpoint topology mismatch")

        if published != interval.battle_ids:
            raise ValueError(
                "published battle IDs must equal the complete interval",
            )
        if tuple(picture.battle_id for picture in pictures) != (interval.battle_ids):
            raise ValueError(
                "targeting pictures must equal the complete interval",
            )
        picture_by_battle = {picture.battle_id: picture for picture in pictures}
        sides = interval.unit_sides
        memberships = interval.battle_memberships
        staged_pictures: list[TacticalTargetingPicture] = []
        for picture in pictures:
            members = memberships.get(picture.battle_id)
            if members is None:
                raise ValueError("targeting picture references an unknown battle")
            if (
                picture.engine_tick != interval.engine_tick
                or picture.logical_time_s != interval.logical_time_s
                or picture.fog_of_war_enabled != interval.fog_of_war_enabled
            ):
                raise ValueError(
                    "targeting picture does not match the complete interval",
                )
            if {decision.shooter_id for decision in picture.decisions} != set(members):
                raise ValueError("targeting picture shooter topology mismatch")
            restored_decisions: list[TacticalTargetingDecision] = []
            for decision in picture.decisions:
                if decision.shooter_side != sides[decision.shooter_id]:
                    raise ValueError("restored shooter side topology mismatch")
                if not decision.consumable:
                    raise ValueError(
                        "targeting decisions must restore exactly consumable",
                    )
                if decision.sensing_aware_standoff_enabled is not self._sensing_aware_standoff_enabled:
                    raise ValueError("restored decision enablement mismatch")
                if decision.target_id is not None and (
                    decision.target_id not in members or decision.target_side != sides[decision.target_id]
                ):
                    raise ValueError("restored target topology mismatch")
                restored_decisions.append(decision)
            staged_pictures.append(
                replace(
                    picture,
                    decisions=tuple(restored_decisions),
                )
            )
        staged_revalidations: list[TacticalEngagementRevalidationOutcome] = []
        for outcome in revalidations:
            picture = picture_by_battle.get(outcome.battle_id)
            decision = (
                None
                if picture is None or picture.engine_tick != outcome.engine_tick
                else picture.decision_for(outcome.shooter_id)
            )
            if decision is None:
                raise ValueError(
                    "targeting revalidation lacks its exact bounded picture",
                )
            if not outcome.consumable:
                raise ValueError(
                    "targeting revalidations must restore exactly consumable",
                )
            _validate_revalidation_against_decision(outcome, decision)
            staged_revalidations.append(outcome)
        return TacticalTargetingRestorePlan(
            registered_unit_side_items=tuple(registered_sides.items()),
            prepared_interval=interval,
            published_battle_ids=published,
            latest_pictures=tuple(staged_pictures),
            latest_engagement_revalidations=tuple(staged_revalidations),
        )

    def commit_state(self, plan: TacticalTargetingRestorePlan) -> None:
        """Commit a previously validated restore plan atomically."""
        if not isinstance(plan, TacticalTargetingRestorePlan):
            raise ValueError("plan must be a TacticalTargetingRestorePlan")
        self._snapshot = _TacticalTargetingSnapshot(
            registered_unit_sides=MappingProxyType(
                dict(plan.registered_unit_side_items),
            ),
            prepared_interval=plan.prepared_interval,
            published_battle_ids=plan.published_battle_ids,
            latest_pictures=MappingProxyType({picture.battle_id: picture for picture in plan.latest_pictures}),
            latest_engagement_revalidations=MappingProxyType(
                {outcome.key: outcome for outcome in plan.latest_engagement_revalidations}
            ),
        )

    def set_state(
        self,
        state: object,
        *,
        expected_unit_sides: Mapping[str, str] | None = None,
        expected_battle_memberships: Mapping[str, Collection[str]] | None = None,
        expected_engine_tick: int | None = None,
        expected_logical_time_s: float | None = None,
    ) -> None:
        """Validate and restore targeting state in one public operation."""
        self.commit_state(
            self.stage_state(
                state,
                expected_unit_sides=expected_unit_sides,
                expected_battle_memberships=expected_battle_memberships,
                expected_engine_tick=expected_engine_tick,
                expected_logical_time_s=expected_logical_time_s,
            )
        )


def _normalize_unit_sides(unit_sides: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(unit_sides, Mapping):
        raise ValueError("unit_sides must be a mapping")
    side_items = tuple(
        sorted(
            (
                _require_identifier(unit_id, label="unit_id"),
                _require_identifier(side, label=f"side for {unit_id!r}"),
            )
            for unit_id, side in unit_sides.items()
        )
    )
    normalized = dict(side_items)
    if len(normalized) != len(side_items):
        raise ValueError("unit_sides contains duplicate unit IDs")
    return normalized


def _build_interval(
    *,
    engine_tick: int,
    logical_time_s: float,
    fog_of_war_enabled: bool,
    unit_sides: Mapping[str, str],
    battle_memberships: Mapping[str, Collection[str]],
) -> TargetingInterval:
    tick = _require_non_negative_int(engine_tick, label="engine_tick")
    elapsed = _require_non_negative_number(
        logical_time_s,
        label="logical_time_s",
    )
    fow_enabled = _require_bool(
        fog_of_war_enabled,
        label="fog_of_war_enabled",
    )
    normalized_sides = _normalize_unit_sides(unit_sides)
    side_items = tuple(normalized_sides.items())
    if not isinstance(battle_memberships, Mapping):
        raise ValueError("battle_memberships must be a mapping")
    memberships: list[tuple[str, tuple[str, ...]]] = []
    for raw_battle_id, raw_members in battle_memberships.items():
        battle_id = _require_identifier(raw_battle_id, label="battle_id")
        if isinstance(raw_members, (str, bytes)) or not isinstance(
            raw_members,
            Collection,
        ):
            raise ValueError(f"battle {battle_id!r} membership must be a collection")
        member_values = tuple(
            _require_identifier(
                member,
                label=f"battle {battle_id!r} member",
            )
            for member in raw_members
        )
        if len(set(member_values)) != len(member_values):
            raise ValueError(f"battle {battle_id!r} contains duplicate members")
        if any(member not in normalized_sides for member in member_values):
            raise ValueError(f"battle {battle_id!r} contains an unregistered unit")
        canonical_members = tuple(sorted(member_values))
        memberships.append((battle_id, canonical_members))
    membership_items = tuple(sorted(memberships))
    if len({battle_id for battle_id, _members in membership_items}) != len(membership_items):
        raise ValueError("battle_memberships contains duplicate battle IDs")
    return TargetingInterval(
        engine_tick=tick,
        logical_time_s=elapsed,
        fog_of_war_enabled=fow_enabled,
        unit_side_items=side_items,
        battle_membership_items=membership_items,
    )


_INTERVAL_KEYS = frozenset(
    {
        "engine_tick",
        "logical_time_s",
        "fog_of_war_enabled",
        "unit_sides",
        "battle_memberships",
    }
)
_UNIT_SIDE_KEYS = frozenset({"unit_id", "side"})
_BATTLE_MEMBERSHIP_KEYS = frozenset({"battle_id", "unit_ids"})


def _interval_to_state(interval: TargetingInterval | None) -> dict[str, Any] | None:
    if interval is None:
        return None
    return {
        "engine_tick": interval.engine_tick,
        "logical_time_s": interval.logical_time_s,
        "fog_of_war_enabled": interval.fog_of_war_enabled,
        "unit_sides": [{"unit_id": unit_id, "side": side} for unit_id, side in interval.unit_side_items],
        "battle_memberships": [
            {"battle_id": battle_id, "unit_ids": list(unit_ids)}
            for battle_id, unit_ids in interval.battle_membership_items
        ],
    }


def _unit_sides_from_state(
    value: object,
    *,
    label: str,
) -> Mapping[str, str]:
    if not isinstance(value, list):
        raise ValueError(f"targeting {label} must be a list")
    side_items: list[tuple[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != _UNIT_SIDE_KEYS:
            raise ValueError(f"targeting {label}[{index}] is malformed")
        side_items.append(
            (
                _require_identifier(item["unit_id"], label="state unit_id"),
                _require_identifier(item["side"], label="state unit side"),
            )
        )
    if tuple(side_items) != tuple(sorted(side_items)):
        raise ValueError(f"targeting {label} is not canonical")
    normalized = _normalize_unit_sides(dict(side_items))
    if len(normalized) != len(side_items):
        raise ValueError(f"targeting {label} contains duplicate unit IDs")
    return MappingProxyType(normalized)


def _interval_from_state(value: object) -> TargetingInterval:
    if not isinstance(value, dict) or set(value) != _INTERVAL_KEYS:
        raise ValueError("targeting prepared interval has invalid key topology")
    normalized_sides = _unit_sides_from_state(
        value["unit_sides"],
        label="unit_sides",
    )
    side_items = tuple(normalized_sides.items())
    raw_battles = value["battle_memberships"]
    if not isinstance(raw_battles, list):
        raise ValueError("targeting battle_memberships must be a list")
    battle_mapping: dict[str, tuple[str, ...]] = {}
    battle_order: list[str] = []
    for index, item in enumerate(raw_battles):
        if not isinstance(item, dict) or set(item) != _BATTLE_MEMBERSHIP_KEYS:
            raise ValueError(f"targeting battle_memberships[{index}] is malformed")
        battle_id = _require_identifier(item["battle_id"], label="state battle_id")
        raw_ids = item["unit_ids"]
        if not isinstance(raw_ids, list):
            raise ValueError("targeting battle unit_ids must be a list")
        if battle_id in battle_mapping:
            raise ValueError("targeting state contains duplicate battle IDs")
        battle_mapping[battle_id] = tuple(raw_ids)
        battle_order.append(battle_id)
    interval = _build_interval(
        engine_tick=value["engine_tick"],
        logical_time_s=value["logical_time_s"],
        fog_of_war_enabled=value["fog_of_war_enabled"],
        unit_sides=normalized_sides,
        battle_memberships=battle_mapping,
    )
    if tuple(battle_order) != interval.battle_ids:
        raise ValueError("targeting battle memberships are not canonical")
    if side_items != interval.unit_side_items or any(
        tuple(item["unit_ids"]) != interval.battle_memberships[item["battle_id"]] for item in raw_battles
    ):
        raise ValueError("targeting interval topology ordering is not canonical")
    return interval


def targeting_checkpoint_interval_from_state(
    state: object,
) -> TargetingInterval | None:
    """Extract canonical typed interval metadata from targeting state."""
    if not isinstance(state, dict) or set(state) != TacticalTargetingRuntime._STATE_KEYS:
        raise ValueError("targeting state has invalid key topology")
    raw_interval = state["prepared_interval"]
    return None if raw_interval is None else _interval_from_state(raw_interval)


_PICTURE_KEYS = frozenset(
    {
        "engine_tick",
        "logical_time_s",
        "battle_id",
        "fog_of_war_enabled",
        "decisions",
    }
)


def _picture_to_state(picture: TacticalTargetingPicture) -> dict[str, Any]:
    return {
        "engine_tick": picture.engine_tick,
        "logical_time_s": picture.logical_time_s,
        "battle_id": picture.battle_id,
        "fog_of_war_enabled": picture.fog_of_war_enabled,
        "decisions": [_decision_to_state(decision) for decision in picture.decisions],
    }


def _picture_from_state(value: object, *, label: str) -> TacticalTargetingPicture:
    if not isinstance(value, dict) or set(value) != _PICTURE_KEYS:
        raise ValueError(f"{label} has invalid key topology")
    raw_decisions = value["decisions"]
    if not isinstance(raw_decisions, list):
        raise ValueError(f"{label}.decisions must be a list")
    return TacticalTargetingPicture(
        engine_tick=value["engine_tick"],
        logical_time_s=value["logical_time_s"],
        battle_id=value["battle_id"],
        fog_of_war_enabled=value["fog_of_war_enabled"],
        decisions=tuple(
            _decision_from_state(
                item,
                label=f"{label}.decisions[{index}]",
            )
            for index, item in enumerate(raw_decisions)
        ),
    )


_DECISION_KEYS = frozenset(
    {
        "engine_tick",
        "logical_time_s",
        "battle_id",
        "ordinal",
        "shooter_id",
        "shooter_side",
        "shooter_domain",
        "target_id",
        "target_side",
        "target_domain",
        "distance_m",
        "weapon_id",
        "weapon_source_equipment_index",
        "weapon_modeled_role",
        "ammunition_id",
        "physical_max_range_m",
        "predictive_effective_range_m",
        "effective_range_basis",
        "legacy_derived_reference_range_m",
        "contact_source",
        "observing_unit_id",
        "contact_sensor_source_equipment_index",
        "contact_sensor_id",
        "contact_sensor_modeled_role",
        "contact_time_s",
        "contact_range_m",
        "visibility_bound_m",
        "sensing_sensor_source_equipment_index",
        "sensing_sensor_id",
        "sensing_sensor_modeled_role",
        "sensing_range_m",
        "fire_control_source",
        "fire_control_sensor_source_equipment_index",
        "fire_control_sensor_id",
        "fire_control_sensor_modeled_role",
        "fire_control_range_m",
        "disposition",
        "authorized_standoff_m",
        "hold_authorized",
        "engagement_solution_valid",
        "sensing_aware_standoff_enabled",
        "fog_of_war_enabled",
        "consumable",
        "observer_track_support",
    }
)


def _optional_enum_value(value: Enum | None) -> str | None:
    return None if value is None else str(value.value)


def _decision_to_state(decision: TacticalTargetingDecision) -> dict[str, Any]:
    return {
        "engine_tick": decision.engine_tick,
        "logical_time_s": decision.logical_time_s,
        "battle_id": decision.battle_id,
        "ordinal": decision.ordinal,
        "shooter_id": decision.shooter_id,
        "shooter_side": decision.shooter_side,
        "shooter_domain": decision.shooter_domain.name,
        "target_id": decision.target_id,
        "target_side": decision.target_side,
        "target_domain": (None if decision.target_domain is None else decision.target_domain.name),
        "distance_m": decision.distance_m,
        "weapon_id": decision.weapon_id,
        "weapon_source_equipment_index": (decision.weapon_source_equipment_index),
        "weapon_modeled_role": _optional_enum_value(
            decision.weapon_modeled_role,
        ),
        "ammunition_id": decision.ammunition_id,
        "physical_max_range_m": decision.physical_max_range_m,
        "predictive_effective_range_m": (decision.predictive_effective_range_m),
        "effective_range_basis": _optional_enum_value(
            decision.effective_range_basis,
        ),
        "legacy_derived_reference_range_m": (decision.legacy_derived_reference_range_m),
        "contact_source": decision.contact_source.value,
        "observing_unit_id": decision.observing_unit_id,
        "contact_sensor_source_equipment_index": (decision.contact_sensor_source_equipment_index),
        "contact_sensor_id": decision.contact_sensor_id,
        "contact_sensor_modeled_role": _optional_enum_value(
            decision.contact_sensor_modeled_role,
        ),
        "contact_time_s": decision.contact_time_s,
        "contact_range_m": decision.contact_range_m,
        "visibility_bound_m": decision.visibility_bound_m,
        "sensing_sensor_source_equipment_index": (decision.sensing_sensor_source_equipment_index),
        "sensing_sensor_id": decision.sensing_sensor_id,
        "sensing_sensor_modeled_role": _optional_enum_value(
            decision.sensing_sensor_modeled_role,
        ),
        "sensing_range_m": decision.sensing_range_m,
        "fire_control_source": decision.fire_control_source.value,
        "fire_control_sensor_source_equipment_index": (decision.fire_control_sensor_source_equipment_index),
        "fire_control_sensor_id": decision.fire_control_sensor_id,
        "fire_control_sensor_modeled_role": _optional_enum_value(
            decision.fire_control_sensor_modeled_role,
        ),
        "fire_control_range_m": decision.fire_control_range_m,
        "disposition": decision.disposition.value,
        "authorized_standoff_m": decision.authorized_standoff_m,
        "hold_authorized": decision.hold_authorized,
        "engagement_solution_valid": decision.engagement_solution_valid,
        "sensing_aware_standoff_enabled": (decision.sensing_aware_standoff_enabled),
        "fog_of_war_enabled": decision.fog_of_war_enabled,
        "consumable": decision.consumable,
        "observer_track_support": (
            None
            if decision.observer_track_support is None
            else observer_track_support_evidence_to_state(
                decision.observer_track_support,
            )
        ),
    }


def targeting_decision_to_state(
    decision: TacticalTargetingDecision,
) -> dict[str, Any]:
    """Return the lossless scalar/enum/ID state for one decision."""
    if not isinstance(decision, TacticalTargetingDecision):
        raise ValueError("decision must be a TacticalTargetingDecision")
    return _decision_to_state(decision)


def _optional_enum_from_state(
    value: object,
    enum_type: type[Enum],
    *,
    label: str,
) -> Any:
    return None if value is None else _parse_enum(value, enum_type, label=label)


def _decision_from_state(
    value: object,
    *,
    label: str,
) -> TacticalTargetingDecision:
    if not isinstance(value, dict) or set(value) != _DECISION_KEYS:
        raise ValueError(f"{label} has invalid key topology")
    target_domain = (
        None
        if value["target_domain"] is None
        else _parse_domain(value["target_domain"], label=f"{label}.target_domain")
    )
    return TacticalTargetingDecision(
        engine_tick=value["engine_tick"],
        logical_time_s=value["logical_time_s"],
        battle_id=value["battle_id"],
        ordinal=value["ordinal"],
        shooter_id=value["shooter_id"],
        shooter_side=value["shooter_side"],
        shooter_domain=_parse_domain(
            value["shooter_domain"],
            label=f"{label}.shooter_domain",
        ),
        target_id=value["target_id"],
        target_side=value["target_side"],
        target_domain=target_domain,
        distance_m=value["distance_m"],
        weapon_id=value["weapon_id"],
        weapon_source_equipment_index=value["weapon_source_equipment_index"],
        weapon_modeled_role=_optional_enum_from_state(
            value["weapon_modeled_role"],
            WeaponModeledRole,
            label=f"{label}.weapon_modeled_role",
        ),
        ammunition_id=value["ammunition_id"],
        physical_max_range_m=value["physical_max_range_m"],
        predictive_effective_range_m=value["predictive_effective_range_m"],
        effective_range_basis=_optional_enum_from_state(
            value["effective_range_basis"],
            EffectiveRangeBasis,
            label=f"{label}.effective_range_basis",
        ),
        legacy_derived_reference_range_m=(value["legacy_derived_reference_range_m"]),
        contact_source=_parse_enum(
            value["contact_source"],
            ContactSource,
            label=f"{label}.contact_source",
        ),
        observing_unit_id=value["observing_unit_id"],
        contact_sensor_source_equipment_index=(value["contact_sensor_source_equipment_index"]),
        contact_sensor_id=value["contact_sensor_id"],
        contact_sensor_modeled_role=_optional_enum_from_state(
            value["contact_sensor_modeled_role"],
            SensorModeledRole,
            label=f"{label}.contact_sensor_modeled_role",
        ),
        contact_time_s=value["contact_time_s"],
        contact_range_m=value["contact_range_m"],
        visibility_bound_m=value["visibility_bound_m"],
        sensing_sensor_source_equipment_index=(value["sensing_sensor_source_equipment_index"]),
        sensing_sensor_id=value["sensing_sensor_id"],
        sensing_sensor_modeled_role=_optional_enum_from_state(
            value["sensing_sensor_modeled_role"],
            SensorModeledRole,
            label=f"{label}.sensing_sensor_modeled_role",
        ),
        sensing_range_m=value["sensing_range_m"],
        fire_control_source=_parse_enum(
            value["fire_control_source"],
            FireControlSource,
            label=f"{label}.fire_control_source",
        ),
        fire_control_sensor_source_equipment_index=(value["fire_control_sensor_source_equipment_index"]),
        fire_control_sensor_id=value["fire_control_sensor_id"],
        fire_control_sensor_modeled_role=_optional_enum_from_state(
            value["fire_control_sensor_modeled_role"],
            SensorModeledRole,
            label=f"{label}.fire_control_sensor_modeled_role",
        ),
        fire_control_range_m=value["fire_control_range_m"],
        disposition=_parse_enum(
            value["disposition"],
            TargetingDisposition,
            label=f"{label}.disposition",
        ),
        authorized_standoff_m=value["authorized_standoff_m"],
        hold_authorized=value["hold_authorized"],
        engagement_solution_valid=value["engagement_solution_valid"],
        sensing_aware_standoff_enabled=(value["sensing_aware_standoff_enabled"]),
        fog_of_war_enabled=value["fog_of_war_enabled"],
        consumable=value["consumable"],
        observer_track_support=(
            None
            if value["observer_track_support"] is None
            else observer_track_support_evidence_from_state(
                value["observer_track_support"],
            )
        ),
    )


def targeting_decision_from_state(
    state: object,
) -> TacticalTargetingDecision:
    """Validate and restore one lossless targeting-decision state."""
    return _decision_from_state(state, label="targeting decision")


_REVALIDATION_OUTCOME_KEYS = frozenset(
    {
        "engine_tick",
        "logical_time_s",
        "battle_id",
        "shooter_id",
        "target_id",
        "weapon_id",
        "weapon_source_equipment_index",
        "weapon_modeled_role",
        "ammunition_id",
        "disposition",
        "revalidation_passed",
        "fog_of_war_enabled",
        "consumable",
    }
)


def _revalidation_outcome_to_state(
    outcome: TacticalEngagementRevalidationOutcome,
) -> dict[str, Any]:
    return {
        "engine_tick": outcome.engine_tick,
        "logical_time_s": outcome.logical_time_s,
        "battle_id": outcome.battle_id,
        "shooter_id": outcome.shooter_id,
        "target_id": outcome.target_id,
        "weapon_id": outcome.weapon_id,
        "weapon_source_equipment_index": (outcome.weapon_source_equipment_index),
        "weapon_modeled_role": outcome.weapon_modeled_role.value,
        "ammunition_id": outcome.ammunition_id,
        "disposition": outcome.disposition.value,
        "revalidation_passed": outcome.revalidation_passed,
        "fog_of_war_enabled": outcome.fog_of_war_enabled,
        "consumable": outcome.consumable,
    }


def targeting_revalidation_outcome_to_state(
    outcome: TacticalEngagementRevalidationOutcome,
) -> dict[str, Any]:
    """Return JSON-safe lossless state for one revalidation outcome."""
    if not isinstance(outcome, TacticalEngagementRevalidationOutcome):
        raise ValueError(
            "outcome must be a TacticalEngagementRevalidationOutcome",
        )
    return _revalidation_outcome_to_state(outcome)


def _revalidation_outcome_from_state(
    value: object,
    *,
    label: str,
) -> TacticalEngagementRevalidationOutcome:
    if not isinstance(value, dict) or set(value) != _REVALIDATION_OUTCOME_KEYS:
        raise ValueError(f"{label} has invalid key topology")
    return TacticalEngagementRevalidationOutcome(
        engine_tick=value["engine_tick"],
        logical_time_s=value["logical_time_s"],
        battle_id=value["battle_id"],
        shooter_id=value["shooter_id"],
        target_id=value["target_id"],
        weapon_id=value["weapon_id"],
        weapon_source_equipment_index=(value["weapon_source_equipment_index"]),
        weapon_modeled_role=_parse_enum(
            value["weapon_modeled_role"],
            WeaponModeledRole,
            label=f"{label}.weapon_modeled_role",
        ),
        ammunition_id=value["ammunition_id"],
        disposition=_parse_enum(
            value["disposition"],
            TargetingDisposition,
            label=f"{label}.disposition",
        ),
        revalidation_passed=value["revalidation_passed"],
        fog_of_war_enabled=value["fog_of_war_enabled"],
        consumable=value["consumable"],
    )


def targeting_revalidation_outcome_from_state(
    state: object,
) -> TacticalEngagementRevalidationOutcome:
    """Validate and restore one lossless revalidation-outcome state."""
    return _revalidation_outcome_from_state(
        state,
        label="targeting revalidation outcome",
    )


def _published_battle_ids_from_state(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("published_battle_ids must be a list")
    published = tuple(_require_identifier(item, label="published battle ID") for item in value)
    if len(set(published)) != len(published):
        raise ValueError("published_battle_ids contains duplicates")
    return published


__all__ = [
    "ContactSource",
    "DEFAULT_TARGETING_VISIBILITY_M",
    "DecisionKey",
    "EffectiveRangeBasis",
    "EffectiveRangeEvidence",
    "FireControlSource",
    "LEGACY_EFFECTIVE_RANGE_FRACTION",
    "ObserverDetectionWitnessView",
    "SensorEnvironmentRangePolicy",
    "SensorTargetingClass",
    "TacticalEngagementRevalidationOutcome",
    "TacticalTargetingDecision",
    "TacticalTargetingPicture",
    "TacticalTargetingPublicationPlan",
    "TacticalTargetingRestorePlan",
    "TacticalTargetingRuntime",
    "TargetingDisposition",
    "TargetingInterval",
    "WeaponStandoffClass",
    "allowed_shooter_domains_for_sensor_role",
    "compatible_sensor_roles_for_weapon_role",
    "fire_control_source_is_compatible",
    "saturating_range_power",
    "saturating_range_product",
    "sensor_environment_range_policy",
    "sensor_environment_range_upper_bound_m",
    "sensor_targeting_class",
    "targeting_decision_from_state",
    "targeting_decision_to_state",
    "targeting_disposition_is_targetless",
    "targeting_disposition_is_valid_engagement",
    "targeting_checkpoint_interval_from_state",
    "targeting_altitude_range_factor",
    "targeting_revalidation_outcome_from_state",
    "targeting_revalidation_outcome_to_state",
    "targeting_visibility_bound_m",
    "weapon_standoff_class",
    "weapon_role_uses_tactical_direct_engagement",
]
