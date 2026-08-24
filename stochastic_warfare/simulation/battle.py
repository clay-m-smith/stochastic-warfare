"""Tactical battle manager — detection, engagement, and AI resolution.

Orchestrates the per-tick tactical loop for active engagements.
Evolves Phase 7's ``ScenarioRunner._run_tick()`` with AI commanders
replacing pre-scripted behavior and full C2/logistics integration.
No domain logic lives here — only sequencing and data routing.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import IntEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.c2.ai.assessment import SituationAssessment
from stochastic_warfare.c2.orders.propagation import (
    PropagationOverrides,
    PropagationResult,
)
from stochastic_warfare.combat.ammunition import (
    AmmoDefinition,
    WeaponCategory,
    WeaponInstance,
)
from stochastic_warfare.combat.suppression import UnitSuppressionState
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.clock import normalize_clock_duration_seconds
from stochastic_warfare.core.indexed_rng import (
    FOWIndexedAllocation,
    FOWIndexedCommitPlan,
)
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import Domain, ModuleId, Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.entities.events import UnitDestroyedEvent, UnitDisabledEvent
from stochastic_warfare.entities.unit_classes.ground import GroundUnitType
from stochastic_warfare.detection.estimation import TrackStatus
from stochastic_warfare.detection.cadence import (
    TacticalAttachmentIdentity,
    TacticalCadenceAttachment,
    TacticalCadenceCommitPlan,
    TacticalCadencePlan,
    TacticalObserverIdentity,
)
from stochastic_warfare.detection.fog_of_war import (
    FogOfWarCommitPlan,
    FogOfWarCycleOutcome,
    FogOfWarLodTier,
    FogOfWarUpdateTransaction,
    FogOfWarWitnessClearPlan,
    ObserverDetectionWitness,
    SideWorldView,
)
from stochastic_warfare.detection.identification import ContactLevel
from stochastic_warfare.detection.observer_support import (
    ObserverTrackSupportEvidence,
    ObserverTrackSupportState,
    observer_track_support_role_is_supported,
)
from stochastic_warfare.detection.sensors import SensorType
from stochastic_warfare.morale.runtime import MoraleRuntime, MoraleTransitionCause
from stochastic_warfare.morale.state import MoraleState

from typing import NamedTuple

from shapely import STRtree
from shapely.geometry import Point

from stochastic_warfare.simulation.calibration import CalibrationSchema
from stochastic_warfare.simulation.battle_executor_contracts import (
    BattleCheckpointExecutor,
    BattleCheckpointSnapshot,
    BattleCheckpointStageRequest,
    BattleClockView,
    BattleEngagementRuntime,
    BattleEngagementExecutor,
    BattleExecutorConfigView,
    BattleExecutorOwner,
    BattleIntervalView,
    BattleMovementRuntime,
    BattleMovementExecutor,
    BattleOODARuntime,
    BattleOODAExecutor,
    BattleRuntimeFailureHandler,
    BattleScenarioView,
    BattleTargetingRuntime,
    CheckpointValue,
    EngagementExecutionRequest,
    MovementExecutionRequest,
    OODACompletionRequest,
    OODAIntervalRequest,
    ReadonlyValue,
)
from stochastic_warfare.simulation.loadouts import (
    SensorAttachment,
    SensorModeledRole,
    SensorTargetingClass,
    WeaponAttachment,
    WeaponModeledRole,
    WeaponStandoffClass,
    allowed_shooter_domains_for_sensor_role,
    compatible_sensor_roles_for_weapon_role,
    required_domains_for_sensor_role,
    sensor_targeting_class,
    weapon_standoff_class,
)
from stochastic_warfare.simulation.movement_diagnostics import (
    MovementDiagnostics,
)
from stochastic_warfare.simulation.performance_flags import (
    DispatchReceipt,
    EffectivePerformanceFlags,
    FogOfWarCycleReceipt,
    LODMoraleReceipt,
    LODReceipt,
    PerformanceExecutionReceipt,
    PerformanceReceiptAccumulator,
    PerformanceReceiptDelta,
    PerformanceReceiptRestorePlan,
    PerformanceReceiptTransaction,
    SoAReceipt,
    resolve_cross_bound_runtime_performance_flags,
    resolve_supported_runtime_performance_flags,
)
from stochastic_warfare.simulation.tactical_targeting import (
    ContactSource,
    DEFAULT_TARGETING_VISIBILITY_M,
    EffectiveRangeBasis,
    EffectiveRangeEvidence,
    FireControlSource,
    SensorEnvironmentRangePolicy,
    TacticalEngagementRevalidationOutcome,
    TacticalTargetingDecision,
    TacticalTargetingPicture,
    TacticalTargetingPublicationPlan,
    TacticalTargetingRuntime,
    TargetingInterval,
    TargetingDisposition,
    saturating_range_power,
    saturating_range_product,
    sensor_environment_range_policy,
    sensor_environment_range_upper_bound_m,
    targeting_visibility_bound_m,
    targeting_altitude_range_factor,
    weapon_role_uses_tactical_direct_engagement,
)
from stochastic_warfare.simulation.unit_arrays import UnitArrays
from stochastic_warfare.terrain.los import LOSCacheCell, LOSCacheKey, LOSEngine

if TYPE_CHECKING:
    from stochastic_warfare.c2.ai.ooda import OODAPhase
    from stochastic_warfare.c2.ai.schools.base import DoctrinalSchool
    from stochastic_warfare.combat.indirect_fire import FireMissionResult, SalvoResult
    from stochastic_warfare.simulation.runtime_context import SimulationContext


class _ObserverModifiers(NamedTuple):
    """Pre-computed per-observer modifiers (Phase 86b).

    Batched once per attacker at tick start to avoid redundant engine
    queries when an attacker engages multiple targets.
    """

    mopp_detection: float = 1.0  # MOPP detection factor [0-1]
    mopp_fov_mod: float = 1.0  # MOPP FOV reduction [0-1]
    mopp_fatigue: float = 1.0  # MOPP fatigue divisor [1.0+]
    mopp_reload_mod: float = 1.0  # MOPP reload multiplier [1.0+]
    mopp_level: int = 0  # MOPP level [0-4]
    altitude_factor: float = 1.0  # Altitude sickness [0.5-1.0]
    readiness: float = 1.0  # Equipment readiness [0-1]


_DEFAULT_OBS_MODS = _ObserverModifiers()


@dataclass(frozen=True, slots=True)
class _TargetingContact:
    """Current shooter-local contact and sensing evidence."""

    source: ContactSource
    range_m: float
    sensor_attachment: SensorAttachment | None
    observer_track_support: ObserverTrackSupportEvidence | None = None


@dataclass(frozen=True, slots=True)
class _TargetingFireControl:
    """Current local fire-control evidence for one weapon attachment."""

    source: FireControlSource
    range_m: float
    sensor_attachment: SensorAttachment | None


@dataclass(frozen=True, slots=True)
class _TargetingResolution:
    """Typed runtime inputs for one not-yet-published targeting answer.

    Alternative contacts and weapons remain internal resolutions until the
    deterministic selectors choose one winner.  The winner is still built as
    a fully validated :class:`TacticalTargetingDecision` at publication.
    """

    contact: _TargetingContact
    weapon: WeaponAttachment | None
    ammunition: AmmoDefinition | None
    fire_control: _TargetingFireControl | None
    disposition: TargetingDisposition
    authorized_standoff_m: float = 0.0
    hold_authorized: bool = False
    engagement_solution_valid: bool = False


@dataclass(frozen=True, slots=True)
class _TargetingCandidate:
    """One target-specific resolution plus its exact selection evidence."""

    resolution: _TargetingResolution
    target: Unit
    target_score: float
    distance_m: float
    direct_visual_range_m: float


@dataclass(frozen=True, slots=True)
class _EngagementIntent:
    """One fully staged, still side-effect-free engagement candidate."""

    target: Unit
    attachment: WeaponAttachment
    ammunition: AmmoDefinition
    distance_m: float
    target_score: float
    weapon_fit_score: float
    targeting_decision: TacticalTargetingDecision | None = None


_TargetingEnvironment = tuple[
    float,
    float,
    float,
    float,
    float,
    float,
    float,
]


@dataclass(frozen=True, slots=True)
class _TargetingObservationSnapshot:
    """Exact not-yet-published observation evidence used by targeting."""

    fog_of_war_enabled: bool
    concealment_scores: Mapping[str, float]
    world_views: Mapping[str, SideWorldView]
    witnesses: Mapping[str, tuple[ObserverDetectionWitness, ...]]
    observer_track_supports: Mapping[
        str,
        tuple[ObserverTrackSupportState, ...],
    ]
    cadence_ordinal: int | None
    support_process_noise_std_mps2: float | None
    support_max_position_uncertainty_m: float | None

    def __post_init__(self) -> None:
        if any(
            type(supports) is not tuple or any(type(support) is not ObserverTrackSupportState for support in supports)
            for supports in self.observer_track_supports.values()
        ):
            raise ValueError(
                "targeting observer track supports must be immutable typed tuples",
            )
        if self.fog_of_war_enabled:
            if (
                type(self.cadence_ordinal) is not int
                or self.cadence_ordinal < 0
                or isinstance(self.support_process_noise_std_mps2, bool)
                or not isinstance(
                    self.support_process_noise_std_mps2,
                    (int, float),
                )
                or not math.isfinite(
                    float(self.support_process_noise_std_mps2),
                )
                or self.support_process_noise_std_mps2 < 0.0
                or isinstance(
                    self.support_max_position_uncertainty_m,
                    bool,
                )
                or not isinstance(
                    self.support_max_position_uncertainty_m,
                    (int, float),
                )
                or not math.isfinite(
                    float(self.support_max_position_uncertainty_m),
                )
                or self.support_max_position_uncertainty_m <= 0.0
            ):
                raise ValueError(
                    "FOW targeting support policy must be finite and current",
                )
        elif (
            self.observer_track_supports
            or self.cadence_ordinal is not None
            or self.support_process_noise_std_mps2 is not None
            or self.support_max_position_uncertainty_m is not None
        ):
            raise ValueError(
                "disabled FOW targeting cannot carry observer track support",
            )
        object.__setattr__(
            self,
            "concealment_scores",
            MappingProxyType(dict(self.concealment_scores)),
        )
        object.__setattr__(
            self,
            "world_views",
            MappingProxyType(dict(self.world_views)),
        )
        object.__setattr__(
            self,
            "witnesses",
            MappingProxyType(dict(self.witnesses)),
        )
        object.__setattr__(
            self,
            "observer_track_supports",
            MappingProxyType(dict(self.observer_track_supports)),
        )


@dataclass(slots=True)
class _TargetingIntervalEvidenceCache:
    """Derived evidence shared by immutable pre-movement pictures.

    The cache exists only while one prepared interval publishes all battle
    pictures.  Target environment is observer-independent, and terrain LOS
    follows the owning engine's directed cell-and-height cache identity.
    """

    environment_by_target: dict[str, _TargetingEnvironment] = field(
        default_factory=dict,
    )
    los_cell_by_unit: dict[str, LOSCacheCell] = field(default_factory=dict)
    los_by_identity: dict[LOSCacheKey, bool] = field(default_factory=dict)
    range_policy_by_observer: dict[
        str,
        SensorEnvironmentRangePolicy,
    ] = field(default_factory=dict)
    observer_range_modifier_by_observer: dict[str, float] = field(
        default_factory=dict,
    )
    observation: _TargetingObservationSnapshot | None = None


logger = get_logger(__name__)

_DEFERRED_OODA_SCHEMA_VERSION = 1


def _clock_duration_microseconds(value: object, *, field_name: str) -> int:
    """Return one validated simulation-clock duration as exact microseconds."""
    normalized = normalize_clock_duration_seconds(value, field_name=field_name)
    duration = timedelta(seconds=normalized)
    return (duration.days * 86_400 + duration.seconds) * 1_000_000 + duration.microseconds


def _resolve_cal_flat(ctx: Any) -> dict[str, Any]:
    """Get or build the flat calibration dict from *ctx*.

    Returns ``ctx.cal_flat`` when available (the fast path set up by
    :class:`ScenarioLoader`).  Falls back to building one on-the-fly
    for backward compatibility with tests that pass raw dicts or
    ``SimpleNamespace`` contexts.
    """
    flat = getattr(ctx, "cal_flat", None)
    if flat:
        return flat
    cal = getattr(ctx, "calibration", None)
    if cal is None:
        return {}
    if isinstance(cal, CalibrationSchema):
        sides = list(getattr(ctx, "units_by_side", {}).keys())
        return cal.to_flat_dict(sorted(sides) if sides else ["blue", "red"])
    if isinstance(cal, dict):
        return cal
    return {}


class UnitLodTier(IntEnum):
    """Level-of-detail tier for per-unit sensing cadence (Phase 85)."""

    ACTIVE = 0  # Native sensing cadence
    NEARBY = 1  # Reduced sensing cadence
    DISTANT = 2  # Minimal sensing cadence


@dataclass(frozen=True, slots=True)
class _LODClassificationPlan:
    """Immutable Battle-owned LOD publication for one observation interval."""

    lod_tiers: Mapping[str, int]
    pending_tiers: Mapping[str, int]
    pending_counts: Mapping[str, int]
    receipt: LODReceipt

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "lod_tiers",
            MappingProxyType(dict(self.lod_tiers)),
        )
        object.__setattr__(
            self,
            "pending_tiers",
            MappingProxyType(dict(self.pending_tiers)),
        )
        object.__setattr__(
            self,
            "pending_counts",
            MappingProxyType(dict(self.pending_counts)),
        )


@dataclass(frozen=True, slots=True)
class _StagedFOWObservation:
    """All owner-bound FOW plans retained until outer publication."""

    reporting_sides: tuple[str, ...]
    indexed_allocation: FOWIndexedAllocation
    indexed_commit: FOWIndexedCommitPlan
    cadence_plan: TacticalCadencePlan
    cadence_commit: TacticalCadenceCommitPlan
    transaction: FogOfWarUpdateTransaction
    fow_commit: FogOfWarCommitPlan
    outcomes: tuple[FogOfWarCycleOutcome, ...]
    signature_cache: Mapping[str, Any]
    observer_unit_ids: frozenset[str]
    witness_promoted_unit_ids: frozenset[str]
    expected_indexed_entries: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "signature_cache",
            MappingProxyType(dict(self.signature_cache)),
        )


@dataclass(frozen=True, slots=True)
class _BattleObservationPublication:
    """Fully materialized Battle-owned state for one observation interval."""

    signature_cache: dict[str, Any]
    concealment_scores: dict[str, float]
    lod_tiers: dict[str, int]
    lod_pending_tiers: dict[str, int]
    lod_pending_counts: dict[str, int]
    lod_promoted: set[str]
    fow_observer_unit_ids: frozenset[str]
    _prior_signature_cache: dict[str, Any]
    _prior_concealment_scores: dict[str, float]
    _prior_lod_tiers: dict[str, int]
    _prior_lod_pending_tiers: dict[str, int]
    _prior_lod_pending_counts: dict[str, int]
    _prior_lod_promoted: set[str]
    _prior_fow_observer_unit_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class _TacticalObservationPlan:
    """Single typed publication boundary spanning every observation owner."""

    engine_tick: int
    targeting_owner: TacticalTargetingRuntime
    targeting_publication: TacticalTargetingPublicationPlan
    battle_publication: _BattleObservationPublication
    fow_owner: Any | None
    rng_owner: Any | None
    fow: _StagedFOWObservation | None
    witness_clear: FogOfWarWitnessClearPlan | None
    _owner_token: object


# Sensor types that bypass visual weather degradation
_WEATHER_BYPASS_TYPES: frozenset[SensorType] = frozenset(
    {
        SensorType.THERMAL,
        SensorType.RADAR,
        SensorType.ESM,
    }
)

_FOW_DIRECT_VISUAL_ROLES: frozenset[SensorModeledRole] = frozenset(
    {
        SensorModeledRole.VISUAL_OBSERVATION,
        SensorModeledRole.NIGHT_VISION,
        SensorModeledRole.NAVAL_LOOKOUT,
        SensorModeledRole.AIRBORNE_LOW_LIGHT_OBSERVATION,
        SensorModeledRole.INDIVIDUAL_NIGHT_VISION,
    }
)

# Phase 44a: weather Pk modifier lookup (by WeatherState int value)
_WEATHER_PK_TABLE: dict[int, float] = {
    0: 1.00,  # CLEAR
    1: 1.00,  # PARTLY_CLOUDY
    2: 0.95,  # OVERCAST
    3: 0.90,  # LIGHT_RAIN
    4: 0.80,  # HEAVY_RAIN
    5: 0.85,  # SNOW
    6: 0.65,  # FOG
    7: 0.55,  # STORM
}


def _compute_weather_pk_modifier(weather_state: int) -> float:
    """Return hit probability modifier for the given weather state."""
    return _WEATHER_PK_TABLE.get(int(weather_state), 1.0)


# Phase 52a: twilight gradation lookup
_TWILIGHT_VISUAL_MODIFIER: dict[str | None, float] = {
    "civil": 0.8,
    "nautical": 0.5,
    "astronomical": 0.3,
    None: 0.2,  # full night
}


def _compute_night_modifiers(illum, night_thermal_floor: float = 0.8) -> tuple[float, float]:
    """Return (visual_modifier, thermal_modifier) from illumination.

    Day → (1.0, 1.0).  At night, visual degrades through twilight
    stages while thermal is barely affected (floor 0.8).
    """
    if illum.is_day:
        return 1.0, 1.0
    stage = getattr(illum, "twilight_stage", None)
    visual = _TWILIGHT_VISUAL_MODIFIER.get(stage, 0.2)
    thermal = max(night_thermal_floor, visual)
    return visual, thermal


def _weapon_supports_domain(definition: Any, domain: Domain) -> bool:
    """Return a typed weapon-domain decision with legacy-fixture support."""
    effective_domains = getattr(definition, "effective_target_domains", None)
    if callable(effective_domains):
        return domain.name in effective_domains()
    authored_domains = getattr(definition, "target_domains", None)
    if authored_domains:
        return domain.name in {str(authored_domain).upper() for authored_domain in authored_domains}
    return True


def _max_weapon_range_for_domain(
    attachments: Iterable[Any],
    target_domain: Domain | None,
) -> float:
    """Return the longest mapped range applicable to *target_domain*."""
    maximum = 0.0
    for attachment in attachments:
        weapon = getattr(attachment, "weapon", None)
        if weapon is None:
            weapon = attachment[0]
        if target_domain is not None and not _weapon_supports_domain(
            weapon.definition,
            target_domain,
        ):
            continue
        maximum = max(maximum, weapon.definition.max_range_m)
    return maximum


# Phase 52b: cross-wind accuracy penalty
def _compute_crosswind_penalty(
    wind_e: float,
    wind_n: float,
    att_e: float,
    att_n: float,
    tgt_e: float,
    tgt_n: float,
    scale: float = 0.03,
) -> float:
    """Return crew skill multiplier due to crosswind [0.7–1.0].

    *scale* is m/s → penalty fraction (default 0.03 → 10 m/s = 30%).
    """
    dx = tgt_e - att_e
    dy = tgt_n - att_n
    if dx == 0.0 and dy == 0.0:
        return 1.0
    heading = math.atan2(dx, dy)
    crosswind = abs(wind_e * math.cos(heading) - wind_n * math.sin(heading))
    return max(0.7, 1.0 - crosswind * scale)


# Phase 62a: WBGT and wind chill helpers for heat/cold casualties
def _compute_wbgt(temperature_c: float, humidity: float) -> float:
    """Simplified Wet Bulb Globe Temperature estimate.

    WBGT ≈ 0.7·T·√(humidity) + 0.3·T.  Threshold for heat stress ~28°C.
    """
    return 0.7 * temperature_c * math.sqrt(max(0.0, min(1.0, humidity))) + 0.3 * temperature_c


def _compute_wind_chill(temperature_c: float, wind_speed_mps: float) -> float:
    """NWS wind chill formula (valid for T ≤ 10°C, V ≥ 4.8 km/h).

    Returns wind chill temperature in °C.
    """
    v_kmh = wind_speed_mps * 3.6
    if temperature_c > 10.0 or v_kmh < 4.8:
        return temperature_c
    return 13.12 + 0.6215 * temperature_c - 11.37 * (v_kmh**0.16) + 0.3965 * temperature_c * (v_kmh**0.16)


# Phase 63a: unit signature lookup for FOW detection
def _get_unit_signature(
    ctx: Any,
    unit: Any,
    *,
    failure_handler: BattleRuntimeFailureHandler | None = None,
) -> Any:
    """Retrieve signature profile for a unit, or None if unavailable."""
    _sl = getattr(ctx, "sig_loader", None)
    if _sl is None:
        return None
    try:
        return _sl.get_profile(getattr(unit, "unit_type", ""))
    except (KeyError, AttributeError):
        return None
    except Exception as exc:
        if failure_handler is not None and not failure_handler(
            "detection.signatures",
            "get_profile",
            exc,
        ):
            raise
        return None


# Phase 52b: ITU-R P.838 rain attenuation for radar sensors
def _compute_rain_detection_factor(precip_rate_mmhr: float, range_km: float) -> float:
    """Return detection range multiplier due to rain [0.1–1.0].

    Uses ITU-R P.838 power law for X-band (~10 GHz): k~0.01, alpha~1.28.
    Radar range equation R^4: factor = 10^(-atten_dB / 40).
    """
    if precip_rate_mmhr <= 0 or range_km <= 0:
        return 1.0
    specific_atten = 0.01 * (precip_rate_mmhr**1.28)
    total_atten_db = specific_atten * range_km
    return max(0.1, 10.0 ** (-total_atten_db / 40.0))


# Phase 48a: configurable naval engagement defaults
class NavalEngagementConfig(BaseModel):
    """Default Pk / dimensions for naval engagement routing."""

    default_torpedo_pk: float = 0.4
    default_missile_pk: float = 0.7
    default_pd_count: int = 2
    default_pd_pk: float = 0.3
    default_target_length_m: float = 150.0
    default_target_beam_m: float = 20.0


# Phase 43a: melee range threshold (metres)
_MELEE_RANGE_M = 10.0

# Phase 50a: posture → movement speed multiplier
_POSTURE_SPEED_MULT: dict[int, float] = {
    0: 1.0,  # MOVING
    1: 1.0,  # HALTED
    2: 0.5,  # DEFENSIVE
    3: 0.0,  # DUG_IN
    4: 0.0,  # FORTIFIED
}

# Phase 51b: naval posture → movement speed multiplier
_NAVAL_POSTURE_SPEED_MULT: dict[int, float] = {
    0: 0.0,  # ANCHORED
    1: 1.0,  # UNDERWAY
    2: 1.2,  # TRANSIT
    3: 0.9,  # BATTLE_STATIONS
}

# Phase 56e: naval posture → target detection range multiplier
_NAVAL_POSTURE_DETECT_MULT: dict[int, float] = {
    0: 1.2,  # ANCHORED — easier to detect (stationary, no wake)
    1: 1.0,  # UNDERWAY — baseline
    2: 0.85,  # TRANSIT — reduced signature at speed
    3: 1.3,  # BATTLE_STATIONS — active radar/emissions increase signature
}


def _validated_targeting_sensor_range_m(
    *,
    sensor_type: SensorType,
    condition_adjusted_range_m: float,
    resolved_range_m: float,
    policy: SensorEnvironmentRangePolicy,
) -> float:
    """Fail closed when a production owner exceeds the total range policy."""
    resolved = float(resolved_range_m)
    if not math.isfinite(resolved) or resolved < 0.0:
        raise RuntimeError(
            "Targeting sensor resolver produced a non-finite or negative range",
        )
    try:
        upper_bound = sensor_environment_range_upper_bound_m(
            policy=policy,
            sensor_type=sensor_type,
            condition_adjusted_range_m=condition_adjusted_range_m,
        )
    except ValueError as exc:
        raise RuntimeError(
            "Targeting sensor has invalid condition-adjusted range evidence",
        ) from exc
    if resolved > upper_bound + 1e-9:
        raise RuntimeError(
            "Targeting sensor resolver exceeded the total environmental range bound",
        )
    return resolved


# Phase 43b: weapon categories that route to indirect fire
_INDIRECT_FIRE_CATEGORIES = frozenset({"HOWITZER", "MORTAR", "ARTILLERY"})
_INDIRECT_FIRE_ROLES = frozenset(
    {
        WeaponModeledRole.FIELD_ARTILLERY,
        WeaponModeledRole.MORTAR_FIRE,
        WeaponModeledRole.ROCKET_ARTILLERY,
    }
)
_AIR_DELIVERY_ROLES = frozenset({WeaponModeledRole.BOMB_DELIVERY})
_NAVAL_SUBSURFACE_ROLES = frozenset(
    {
        WeaponModeledRole.TORPEDO,
        WeaponModeledRole.ANTI_SUBMARINE,
    }
)


# ---------------------------------------------------------------------------
# Phase 64 helper — unit position lookup
# ---------------------------------------------------------------------------


def _get_unit_position(ctx: Any, unit_id: str) -> Position:
    """Return the position of a unit, or a default origin position."""
    for units in ctx.units_by_side.values():
        for u in units:
            if u.entity_id == unit_id and u.position is not None:
                return u.position
    return Position(0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# Phase 43 helpers — aggregate engagement routing
# ---------------------------------------------------------------------------


def _get_formation_firepower(
    ctx: Any,
    unit: Unit,
    *,
    failure_handler: BattleRuntimeFailureHandler | None = None,
) -> float:
    """Get formation firepower fraction for Napoleonic units."""
    engine = getattr(ctx, "formation_napoleonic_engine", None)
    if engine is not None:
        try:
            return engine.firepower_fraction(unit.entity_id)
        except Exception as exc:
            if failure_handler is not None and not failure_handler(
                "combat.napoleonic_formation",
                "firepower_fraction",
                exc,
            ):
                raise
            pass
    return 1.0  # Default: all muskets fire (LINE formation)


def _infer_melee_type(attacker: Unit, wpn_inst: Any) -> Any:
    """Infer MeleeType from unit/weapon characteristics."""
    from stochastic_warfare.combat.melee import MeleeType

    wpn_id = wpn_inst.definition.weapon_id.lower()
    if "cavalry" in wpn_id or "saber" in wpn_id or "lance" in wpn_id:
        return MeleeType.CAVALRY_CHARGE
    if "bayonet" in wpn_id:
        return MeleeType.BAYONET_CHARGE
    if "pike" in wpn_id or "spear" in wpn_id:
        return MeleeType.PIKE_PUSH
    if "sword" in wpn_id or "axe" in wpn_id or "gladius" in wpn_id:
        return MeleeType.SHIELD_WALL
    return MeleeType.BAYONET_CHARGE  # Default


def _infer_missile_type(wpn_inst: Any) -> Any:
    """Infer archery MissileType from weapon."""
    from stochastic_warfare.combat.archery import MissileType

    wpn_id = wpn_inst.definition.weapon_id.lower()
    if "longbow" in wpn_id:
        return MissileType.LONGBOW
    if "crossbow" in wpn_id:
        return MissileType.CROSSBOW
    if "composite" in wpn_id:
        return MissileType.COMPOSITE_BOW
    if "javelin" in wpn_id:
        return MissileType.JAVELIN
    if "sling" in wpn_id:
        return MissileType.SLING
    return MissileType.LONGBOW  # Default


def _apply_aggregate_casualties(
    casualties: int,
    target: Unit,
    pending_damage: list[tuple[Unit, UnitStatus, str]],
    destruction_threshold: float = 0.5,
    disable_threshold: float = 0.3,
    cumulative_tracker: dict[str, int] | None = None,
    *,
    event_bus: Any | None = None,
    attacker: Unit | None = None,
    wpn_inst: Any | None = None,
    best_range: float = 0.0,
) -> None:
    """Convert aggregate casualty count to pending unit status changes.

    When *cumulative_tracker* is provided, casualties are accumulated across
    ticks and thresholds are evaluated against the running total.  This is
    essential for aggregate models (volley fire, archery) where a single
    volley rarely exceeds the threshold on its own.

    When *event_bus* is provided, publishes ``EngagementEvent`` and
    ``DamageEvent`` so aggregate combat is visible to the recorder, UI, and
    evaluator.
    """
    if casualties <= 0:
        return

    _wpn_id = (
        getattr(
            getattr(wpn_inst, "definition", None),
            "weapon_id",
            "aggregate",
        )
        if wpn_inst
        else "aggregate"
    )

    # Publish engagement + damage events for aggregate models
    if event_bus is not None and attacker is not None:
        from stochastic_warfare.combat.events import DamageEvent, EngagementEvent

        event_bus.publish(
            EngagementEvent(
                timestamp=datetime.min,
                source=ModuleId.COMBAT,
                attacker_id=attacker.entity_id,
                target_id=target.entity_id,
                weapon_id=_wpn_id,
                ammo_type="aggregate",
                result="hit",
            )
        )
        event_bus.publish(
            DamageEvent(
                timestamp=datetime.min,
                source=ModuleId.COMBAT,
                target_id=target.entity_id,
                damage_amount=float(casualties),
                damage_type="aggregate_casualties",
                location="personnel",
            )
        )

    total = max(1, len(target.personnel))
    if cumulative_tracker is not None:
        cumulative_tracker[target.entity_id] = cumulative_tracker.get(target.entity_id, 0) + casualties
        fraction = cumulative_tracker[target.entity_id] / total
    else:
        fraction = casualties / total
    if fraction >= destruction_threshold:
        pending_damage.append((target, UnitStatus.DESTROYED, _wpn_id))
    elif fraction >= disable_threshold:
        pending_damage.append((target, UnitStatus.DISABLED, _wpn_id))


def _apply_melee_result(
    mr: Any,
    attacker: Unit,
    defender: Unit,
    pending_damage: list[tuple[Unit, UnitStatus, str]],
    morale_runtime: MoraleRuntime | None,
    destruction_threshold: float = 0.5,
    disable_threshold: float = 0.3,
    *,
    event_bus: Any | None = None,
    wpn_inst: Any | None = None,
    timestamp: datetime,
    current_time_s: float,
) -> None:
    """Convert melee result to damage entries for both sides."""
    if (mr.defender_routed or mr.attacker_routed) and morale_runtime is None:
        raise RuntimeError("Melee rout requires a morale runtime")
    _wpn_id = (
        getattr(
            getattr(wpn_inst, "definition", None),
            "weapon_id",
            "melee",
        )
        if wpn_inst
        else "melee"
    )

    # Publish engagement event for melee
    if event_bus is not None and (mr.defender_casualties > 0 or mr.attacker_casualties > 0):
        from stochastic_warfare.combat.events import EngagementEvent

        event_bus.publish(
            EngagementEvent(
                timestamp=timestamp,
                source=ModuleId.COMBAT,
                attacker_id=attacker.entity_id,
                target_id=defender.entity_id,
                weapon_id=_wpn_id,
                ammo_type="melee",
                result="hit",
            )
        )

    # Defender casualties
    if mr.defender_casualties > 0:
        if event_bus is not None:
            from stochastic_warfare.combat.events import DamageEvent

            event_bus.publish(
                DamageEvent(
                    timestamp=timestamp,
                    source=ModuleId.COMBAT,
                    target_id=defender.entity_id,
                    damage_amount=float(mr.defender_casualties),
                    damage_type="melee_casualties",
                    location="personnel",
                )
            )
        def_total = max(1, len(defender.personnel))
        frac = mr.defender_casualties / def_total
        if frac >= destruction_threshold:
            pending_damage.append((defender, UnitStatus.DESTROYED, _wpn_id))
        elif frac >= disable_threshold:
            pending_damage.append((defender, UnitStatus.DISABLED, _wpn_id))
    # Attacker casualties
    if mr.attacker_casualties > 0:
        if event_bus is not None:
            from stochastic_warfare.combat.events import DamageEvent

            event_bus.publish(
                DamageEvent(
                    timestamp=timestamp,
                    source=ModuleId.COMBAT,
                    target_id=attacker.entity_id,
                    damage_amount=float(mr.attacker_casualties),
                    damage_type="melee_casualties",
                    location="personnel",
                )
            )
        att_total = max(1, len(attacker.personnel))
        frac = mr.attacker_casualties / att_total
        if frac >= destruction_threshold:
            pending_damage.append((attacker, UnitStatus.DESTROYED, _wpn_id))
        elif frac >= disable_threshold:
            pending_damage.append((attacker, UnitStatus.DISABLED, _wpn_id))
    # Morale effects — rout
    if mr.defender_routed:
        assert morale_runtime is not None
        morale_runtime.force_transition(
            defender.entity_id,
            MoraleState.ROUTED,
            cause=MoraleTransitionCause.MELEE_ROUT,
            timestamp=timestamp,
            current_time_s=current_time_s,
        )
    if mr.attacker_routed:
        assert morale_runtime is not None
        morale_runtime.force_transition(
            attacker.entity_id,
            MoraleState.ROUTED,
            cause=MoraleTransitionCause.MELEE_ROUT,
            timestamp=timestamp,
            current_time_s=current_time_s,
        )


def _consume_routed_ammunition(
    ctx: Any,
    attacker: Unit,
    wpn_inst: Any,
    ammo_def: AmmoDefinition | None,
    *,
    quantity: int,
    timestamp: Any,
    current_time_s: float | None,
    cooldown_multiplier: float = 1.0,
) -> int:
    """Consume selected live ammunition immediately before a routed shot.

    Legacy direct helper tests do not pass an ammunition definition; those
    callers retain their historical engine-dispatch behavior without
    pretending that an untyped fixture has live ammunition. Production battle
    selection always supplies the exact selected definition.
    """
    requested = max(1, int(quantity))
    if not isinstance(ammo_def, AmmoDefinition) or not isinstance(wpn_inst, WeaponInstance):
        return requested

    ammo_id = ammo_def.ammo_id
    if current_time_s is not None and not wpn_inst.can_fire_timed(
        current_time_s,
        cooldown_multiplier=cooldown_multiplier,
    ):
        return 0
    available = wpn_inst.ammo_state.available(ammo_id)
    consumed = min(requested, available)
    if consumed <= 0 or not wpn_inst.fire(ammo_id, consumed):
        return 0
    if current_time_s is not None:
        wpn_inst.record_fire(current_time_s)

    event_bus = getattr(ctx, "event_bus", None)
    if event_bus is not None and timestamp is not None:
        from stochastic_warfare.combat.events import AmmoExpendedEvent

        event_bus.publish(
            AmmoExpendedEvent(
                timestamp=timestamp,
                source=ModuleId.COMBAT,
                unit_id=attacker.entity_id,
                ammo_type=ammo_id,
                quantity=consumed,
            )
        )
    return consumed


def _routed_shot_fired(
    wpn_inst: Any,
    ammo_id: str,
    ammunition_before: Any,
) -> bool:
    """Report whether a routed production attachment consumed live ammunition."""
    if not isinstance(wpn_inst, WeaponInstance):
        # Preserve legacy direct fixtures that predate runtime attachments.
        # ScenarioLoader production contexts always use WeaponInstance.
        return True
    return wpn_inst.ammo_state.available(ammo_id) < ammunition_before


def _routed_ammunition_ready(
    wpn_inst: Any,
    ammo_def: AmmoDefinition | None,
    current_time_s: float | None,
) -> bool:
    """Preflight a routed production round without mutating its magazine."""
    if not isinstance(ammo_def, AmmoDefinition) or not isinstance(wpn_inst, WeaponInstance):
        return True
    return (current_time_s is None or wpn_inst.can_fire_timed(current_time_s)) and wpn_inst.can_fire(ammo_def.ammo_id)


def _route_naval_engagement(
    ctx: Any,
    attacker: Unit,
    target: Unit,
    wpn_inst: Any,
    best_range: float,
    dt: float,
    timestamp: Any,
    naval_config: NavalEngagementConfig | None = None,
    force_ratio_mod: float = 1.0,
    vls_launches: dict[str, int] | None = None,
    ammo_def: AmmoDefinition | None = None,
    current_time_s: float | None = None,
    runtime_system_multiplier: int = 1,
    modeled_role: WeaponModeledRole | None = None,
) -> tuple[bool, UnitStatus | None]:
    """Route naval engagement to appropriate engine.

    Returns ``(handled, status)`` — *handled* is ``True`` when the weapon
    was processed by a naval engine (even on a miss), ``False`` when the
    weapon type is not naval-specific and should fall through.

    *force_ratio_mod* scales per-side Pk values (Dupuy CEV).
    """
    nc = naval_config or NavalEngagementConfig()
    represented_systems = max(1, int(runtime_system_multiplier))
    burst_per_system = max(
        1,
        int(getattr(wpn_inst.definition, "burst_size", 1)),
    )
    aggregate_salvo_size = burst_per_system * represented_systems
    wpn_cat_str = wpn_inst.definition.category.upper()

    # Torpedo
    if modeled_role is WeaponModeledRole.TORPEDO or (modeled_role is None and wpn_cat_str == "TORPEDO_TUBE"):
        engine = getattr(ctx, "naval_subsurface_engine", None)
        if engine is not None:
            torpedoes_fired = _consume_routed_ammunition(
                ctx,
                attacker,
                wpn_inst,
                ammo_def,
                quantity=represented_systems,
                timestamp=timestamp,
                current_time_s=current_time_s,
                cooldown_multiplier=represented_systems,
            )
            if torpedoes_fired == 0:
                return True, None
            results = tuple(
                engine.torpedo_engagement(
                    sub_id=attacker.entity_id,
                    target_id=target.entity_id,
                    torpedo_pk=min(
                        1.0,
                        nc.default_torpedo_pk * force_ratio_mod,
                    ),
                    range_m=best_range,
                    timestamp=timestamp,
                )
                for _ in range(torpedoes_fired)
            )
            hits = tuple(result for result in results if result.hit)
            _publish_naval_engagement_event(
                ctx,
                attacker,
                target,
                wpn_inst,
                timestamp,
                bool(hits),
                ammo_def,
            )
            if hits:
                cumulative_damage = min(
                    1.0,
                    sum(float(getattr(result, "damage_fraction", 0.0)) for result in hits),
                )
                status = UnitStatus.DESTROYED if cumulative_damage >= 0.6 else UnitStatus.DISABLED
                return True, status
            return True, None  # handled, miss

    # Phase 51a: depth charge routing
    if (modeled_role is WeaponModeledRole.ANTI_SUBMARINE and wpn_cat_str == "DEPTH_CHARGE") or (
        modeled_role is None and wpn_cat_str == "DEPTH_CHARGE"
    ):
        engine = getattr(ctx, "naval_subsurface_engine", None)
        if engine is not None:
            charges_dropped = _consume_routed_ammunition(
                ctx,
                attacker,
                wpn_inst,
                ammo_def,
                quantity=aggregate_salvo_size,
                timestamp=timestamp,
                current_time_s=current_time_s,
                cooldown_multiplier=represented_systems,
            )
            if charges_dropped == 0:
                return True, None
            result = engine.depth_charge_attack(
                ship_id=attacker.entity_id,
                target_id=target.entity_id,
                num_charges=charges_dropped,
                target_depth_m=getattr(target, "depth", 100.0),
                target_range_m=best_range,
                timestamp=timestamp,
            )
            _publish_naval_engagement_event(
                ctx,
                attacker,
                target,
                wpn_inst,
                timestamp,
                result.hits > 0,
                ammo_def,
            )
            if result.hits > 0:
                status = UnitStatus.DESTROYED if result.damage_fraction >= 0.6 else UnitStatus.DISABLED
                return True, status
            return True, None  # handled, miss

    # Phase 51a: ASROC — missile launcher targeting submarine
    if (
        (
            modeled_role is WeaponModeledRole.ANTI_SUBMARINE
            or (modeled_role is None and wpn_cat_str == "MISSILE_LAUNCHER")
        )
        and wpn_cat_str == "MISSILE_LAUNCHER"
        and target.domain == Domain.SUBMARINE
    ):
        subsurface = getattr(ctx, "naval_subsurface_engine", None)
        if subsurface is not None:
            if (
                _consume_routed_ammunition(
                    ctx,
                    attacker,
                    wpn_inst,
                    ammo_def,
                    quantity=1,
                    timestamp=timestamp,
                    current_time_s=current_time_s,
                )
                == 0
            ):
                return True, None
            result = subsurface.asroc_engagement(
                ship_id=attacker.entity_id,
                target_id=target.entity_id,
                range_m=best_range,
                target_depth_m=getattr(target, "depth", 100.0),
                timestamp=timestamp,
            )
            _publish_naval_engagement_event(
                ctx,
                attacker,
                target,
                wpn_inst,
                timestamp,
                bool(result.torpedo_hit),
                ammo_def,
            )
            if result.torpedo_hit:
                status = UnitStatus.DESTROYED if result.damage_fraction >= 0.6 else UnitStatus.DISABLED
                return True, status
            return True, None  # handled, miss

    # Missile (ASHM) — surface-to-surface salvo
    if wpn_cat_str == "MISSILE_LAUNCHER":
        # Phase 51a: VLS ammo tracking
        _mc_raw = getattr(wpn_inst.definition, "magazine_capacity", 0)
        try:
            mag_cap = int(_mc_raw) if _mc_raw else 0
        except (TypeError, ValueError):
            mag_cap = 0
        if mag_cap > 0:
            uid = attacker.entity_id
            launched = vls_launches.get(uid, 0) if vls_launches is not None else 0
            if launched >= mag_cap:
                logger.info("VLS exhausted: unit %s (%d/%d)", uid, launched, mag_cap)
                return True, None  # magazine exhausted
        engine = getattr(ctx, "naval_surface_engine", None)
        if engine is not None:
            requested_missiles = aggregate_salvo_size
            if mag_cap > 0:
                launched = vls_launches.get(attacker.entity_id, 0) if vls_launches is not None else 0
                requested_missiles = min(
                    requested_missiles,
                    max(0, mag_cap - launched),
                )
            missiles_fired = _consume_routed_ammunition(
                ctx,
                attacker,
                wpn_inst,
                ammo_def,
                quantity=requested_missiles,
                timestamp=timestamp,
                current_time_s=current_time_s,
                cooldown_multiplier=represented_systems,
            )
            if missiles_fired == 0:
                return True, None
            salvo = engine.salvo_exchange(
                attacker_missiles=missiles_fired,
                attacker_pk=min(1.0, nc.default_missile_pk * force_ratio_mod),
                defender_point_defense_count=nc.default_pd_count,
                defender_pd_pk=nc.default_pd_pk,
            )
            # Track VLS expenditure
            if mag_cap > 0 and vls_launches is not None:
                uid = attacker.entity_id
                vls_launches[uid] = vls_launches.get(uid, 0) + missiles_fired
            _publish_naval_engagement_event(
                ctx,
                attacker,
                target,
                wpn_inst,
                timestamp,
                salvo.hits > 0,
                ammo_def,
            )
            if salvo.hits > 0:
                status = UnitStatus.DESTROYED if salvo.hits >= 2 else UnitStatus.DISABLED
                return True, status
            return True, None  # handled, all intercepted

    # Naval gun
    if wpn_cat_str == "NAVAL_GUN":
        # Phase 100 gap 1 fix: shore bombardment (naval gun vs ground)
        # routes to naval_gunfire_support_engine when available; falls
        # through to ship-to-ship gunnery for naval targets.
        if target.domain == Domain.GROUND and attacker.domain in (Domain.NAVAL, Domain.SUBMARINE):
            ngse = getattr(ctx, "naval_gunfire_support_engine", None)
            if ngse is not None:
                rounds_fired = _consume_routed_ammunition(
                    ctx,
                    attacker,
                    wpn_inst,
                    ammo_def,
                    quantity=aggregate_salvo_size,
                    timestamp=timestamp,
                    current_time_s=current_time_s,
                    cooldown_multiplier=represented_systems,
                )
                if rounds_fired == 0:
                    return True, None
                bom_result = ngse.shore_bombardment(
                    ship_id=attacker.entity_id,
                    ship_pos=attacker.position,
                    target_pos=target.position,
                    round_count=rounds_fired,
                    timestamp=timestamp,
                )
                hit = bom_result.hits_in_lethal_radius > 0
                _publish_naval_engagement_event(
                    ctx,
                    attacker,
                    target,
                    wpn_inst,
                    timestamp,
                    hit,
                    ammo_def,
                )
                return (True, UnitStatus.DISABLED) if hit else (True, None)
            # No NGSE engine — fall through to direct-fire path so
            # shore bombardment still resolves via the standard pipeline.
            return False, None
        gunnery = getattr(ctx, "naval_gunnery_engine", None)
        if gunnery is not None:
            shells_fired = _consume_routed_ammunition(
                ctx,
                attacker,
                wpn_inst,
                ammo_def,
                quantity=represented_systems,
                timestamp=timestamp,
                current_time_s=current_time_s,
                cooldown_multiplier=represented_systems,
            )
            if shells_fired == 0:
                return True, None
            salvo = gunnery.fire_salvo(
                firer_id=attacker.entity_id,
                target_id=target.entity_id,
                range_m=best_range,
                target_length_m=nc.default_target_length_m,
                target_beam_m=nc.default_target_beam_m,
                num_guns=shells_fired,
            )
            hit = salvo.get("hits", 0) > 0
            _publish_naval_engagement_event(
                ctx,
                attacker,
                target,
                wpn_inst,
                timestamp,
                hit,
                ammo_def,
            )
            return (True, UnitStatus.DISABLED) if hit else (True, None)
        # Fallback: modern naval gun engagement
        ns_engine = getattr(ctx, "naval_surface_engine", None)
        if ns_engine is not None:
            rounds_fired = _consume_routed_ammunition(
                ctx,
                attacker,
                wpn_inst,
                ammo_def,
                quantity=aggregate_salvo_size,
                timestamp=timestamp,
                current_time_s=current_time_s,
                cooldown_multiplier=represented_systems,
            )
            if rounds_fired == 0:
                return True, None
            gun_result = ns_engine.naval_gun_engagement(
                ship_id=attacker.entity_id,
                target_id=target.entity_id,
                range_m=best_range,
                rounds_fired=rounds_fired,
                timestamp=timestamp,
            )
            hit = gun_result.hits > 0
            _publish_naval_engagement_event(
                ctx,
                attacker,
                target,
                wpn_inst,
                timestamp,
                hit,
                ammo_def,
            )
            return (True, UnitStatus.DISABLED) if hit else (True, None)

    # Shore bombardment for non-NAVAL_GUN platforms (e.g., CANNON
    # category battleship secondaries treated as NGFS).
    if (
        wpn_cat_str == "CANNON"
        and target.domain == Domain.GROUND
        and attacker.domain in (Domain.NAVAL, Domain.SUBMARINE)
    ):
        ngse = getattr(ctx, "naval_gunfire_support_engine", None)
        if ngse is not None:
            rounds_fired = _consume_routed_ammunition(
                ctx,
                attacker,
                wpn_inst,
                ammo_def,
                quantity=aggregate_salvo_size,
                timestamp=timestamp,
                current_time_s=current_time_s,
                cooldown_multiplier=represented_systems,
            )
            if rounds_fired == 0:
                return True, None
            bom_result = ngse.shore_bombardment(
                ship_id=attacker.entity_id,
                ship_pos=attacker.position,
                target_pos=target.position,
                round_count=rounds_fired,
                timestamp=timestamp,
            )
            hit = bom_result.hits_in_lethal_radius > 0
            _publish_naval_engagement_event(
                ctx,
                attacker,
                target,
                wpn_inst,
                timestamp,
                hit,
                ammo_def,
            )
            return (True, UnitStatus.DISABLED) if hit else (True, None)

    return False, None  # Not a naval-specific weapon, fall through


def _publish_naval_engagement_event(
    ctx: Any,
    attacker: Unit,
    target: Unit,
    wpn_inst: Any,
    timestamp: Any,
    hit: bool,
    ammo_def: AmmoDefinition | None = None,
) -> None:
    """Publish EngagementEvent for naval routing paths.

    Phase 100 gap fix: _route_naval_engagement previously swallowed
    engagements silently.  Without this event, naval gunfire (16"/50,
    5"/38) and naval missile salvos don't surface in Casualties-by-
    Weapon analytics or Engagement summaries.  Now emitted for all
    naval-routed engagements (hit or miss), with attacker/target/
    weapon/ammo/result fields matching the direct-fire EngagementEvent
    shape.
    """
    event_bus = getattr(ctx, "event_bus", None)
    if event_bus is None:
        return
    from stochastic_warfare.combat.events import EngagementEvent

    ammo_type = ammo_def.ammo_id if isinstance(ammo_def, AmmoDefinition) else ""
    if not ammo_type:
        try:
            compat = getattr(wpn_inst.definition, "compatible_ammo", []) or []
            if compat:
                ammo_type = str(compat[0])
        except (AttributeError, IndexError, TypeError):
            pass

    event_bus.publish(
        EngagementEvent(
            timestamp=timestamp or datetime.min,
            source=ModuleId.COMBAT,
            attacker_id=attacker.entity_id,
            target_id=target.entity_id,
            weapon_id=wpn_inst.definition.weapon_id,
            ammo_type=ammo_type,
            result="hit" if hit else "miss",
        )
    )


def _publish_air_engagement_event(
    ctx: Any,
    attacker: Unit,
    target: Unit,
    wpn_inst: Any,
    timestamp: Any,
    hit: bool,
    ammo_def: AmmoDefinition | None = None,
) -> None:
    """Publish generic EngagementEvent for air-routed engagements.

    Phase 103 gap fix: ``_route_air_engagement`` dispatches to sub-engines
    (air_combat / air_ground / air_defense) that emit ``AirEngagementEvent``
    — not ``EngagementEvent``.  The ``/analytics/engagements`` chart filters
    on ``EngagementEvent`` only, so air-routed weapon fires (AGM-65, AMRAAM,
    AIM-9, Hellfire from AERIAL attacker, SAM intercepts, etc.) are invisible
    in the Casualties-by-Weapon and Engagement-Summary charts even when they
    score kills (which surface via UnitDestroyedEvent / UnitDisabledEvent).

    This helper emits a unified ``EngagementEvent`` alongside the sub-engine's
    ``AirEngagementEvent`` so analytics queries return a complete picture.
    Both events are kept — ``AirEngagementEvent`` retains air-domain detail
    (BVR/WVR, pilot skill, energy state) while ``EngagementEvent`` gives the
    generic shape charts already consume.
    """
    event_bus = getattr(ctx, "event_bus", None)
    if event_bus is None:
        return
    from stochastic_warfare.combat.events import EngagementEvent

    ammo_type = ammo_def.ammo_id if isinstance(ammo_def, AmmoDefinition) else ""
    if not ammo_type:
        try:
            compat = getattr(wpn_inst.definition, "compatible_ammo", []) or []
            if compat:
                ammo_type = str(compat[0])
        except (AttributeError, IndexError, TypeError):
            pass
    event_bus.publish(
        EngagementEvent(
            timestamp=timestamp or datetime.min,
            source=ModuleId.COMBAT,
            attacker_id=attacker.entity_id,
            target_id=target.entity_id,
            weapon_id=wpn_inst.definition.weapon_id,
            ammo_type=ammo_type,
            result="hit" if hit else "miss",
        )
    )


def _route_air_engagement(
    ctx: Any,
    attacker: Unit,
    target: Unit,
    wpn_inst: Any,
    best_range: float,
    dt: float,
    timestamp: Any,
    force_ratio_mod: float = 1.0,
    ammo_def: AmmoDefinition | None = None,
    current_time_s: float | None = None,
    modeled_role: WeaponModeledRole | None = None,
    failure_handler: BattleRuntimeFailureHandler | None = None,
) -> tuple[bool, UnitStatus | None]:
    """Route air-domain engagement to the appropriate engine.

    Returns ``(handled, status)`` — same pattern as naval routing.

    Priority:
    - Both AERIAL → air_combat_engine (BVR/WVR)
    - Attacker AERIAL, target GROUND/NAVAL → air_ground_engine (CAS)
    - Target AERIAL, attacker non-AERIAL → air_defense_engine (SAM/AAA)
    """
    atk_air = attacker.domain == Domain.AERIAL
    tgt_air = target.domain == Domain.AERIAL
    wpn_cat = getattr(wpn_inst.definition, "category", "").upper()

    # Phase 62d: air combat environmental coupling
    cal_flat = _resolve_cal_flat(ctx)
    _ace = cal_flat.get("enable_air_combat_environment", False)

    # Phase 64c: ATO sortie gate — check available sorties before air engagement
    # Only gate when the ATO has a configured sortie limit (daily_sortie_limit > 0).
    # Without explicit limits, aircraft engage freely.
    _ato_64 = getattr(ctx, "ato_engine", None)
    if _ato_64 is not None and cal_flat.get("enable_c2_friction", False):
        _daily_limit = getattr(_ato_64, "_daily_sortie_limit", 0)
        if _daily_limit > 0:
            _sim_time = ctx.clock.elapsed.total_seconds() if hasattr(ctx.clock, "elapsed") else 0.0
            if _ato_64.get_available_sorties(_sim_time) <= 0:
                logger.debug("ATO: no sorties available, air engagement skipped")
                return (True, None)

    # Air-to-air: route missile engagements through air combat engine
    if atk_air and tgt_air and wpn_cat == "MISSILE_LAUNCHER":
        engine = getattr(ctx, "air_combat_engine", None)
        if engine is None:
            return False, None
        missile_pk = min(1.0, 0.5 * force_ratio_mod)
        pilot_skill = getattr(attacker, "training_level", 0.5)

        # Phase 62d: environmental modifiers for A2A
        _atk_energy = None
        _def_energy = None
        _effective_bvr_range_modifier = 1.0
        if _ace:
            # Icing penalty
            _cond = getattr(ctx, "conditions_facade", None)
            if _cond is not None:
                try:
                    _air_c = _cond.air(
                        attacker.position,
                        float(attacker.position.altitude or 0.0),
                        float(getattr(ctx.config, "latitude", 0.0)),
                        float(getattr(ctx.config, "longitude", 0.0)),
                    )
                    _icing = getattr(_air_c, "icing_risk", 0.0)
                    if _icing > 0.5:
                        missile_pk *= 1.0 - cal_flat.get("icing_maneuver_penalty", 0.15)
                except Exception as exc:
                    if failure_handler is not None and not failure_handler(
                        "environment.conditions",
                        "read_air_combat_icing",
                        exc,
                    ):
                        raise
                    pass

            # Density altitude → reduced thrust
            _wx_aa = getattr(ctx, "weather_engine", None)
            if _wx_aa is not None:
                try:
                    _alt_aa = getattr(attacker.position, "altitude", 0.0)
                    _rho = _wx_aa.atmospheric_density(_alt_aa)
                    _density_factor = min(1.0, _rho / 1.225)
                    missile_pk *= _density_factor
                except Exception as exc:
                    if failure_handler is not None and not failure_handler(
                        "environment.weather",
                        "compute_air_combat_density",
                        exc,
                    ):
                        raise
                    pass

            # Wind → BVR range modification
            if _wx_aa is not None:
                try:
                    _w_cur = _wx_aa.current.wind
                    _w_spd = _w_cur.speed
                    _w_dir = _w_cur.direction
                    # Wind component along attacker→target axis
                    _dx = target.position.easting - attacker.position.easting
                    _dy = target.position.northing - attacker.position.northing
                    _hdg = math.atan2(_dx, _dy)
                    _wind_along = _w_spd * math.cos(_w_dir - _hdg)
                    # Tailwind extends range, headwind reduces
                    _range_mod = 1.0 + _wind_along / cal_flat.get("wind_bvr_missile_speed_mps", 1000.0)
                    if not math.isfinite(_range_mod) or _range_mod <= 0.0:
                        raise ValueError("effective BVR range modifier must be finite and positive")
                    _effective_bvr_range_modifier = max(0.5, _range_mod)
                except Exception as exc:
                    if failure_handler is not None and not failure_handler(
                        "environment.weather",
                        "read_air_combat_wind",
                        exc,
                    ):
                        raise
                    pass

            # Altitude energy advantage
            from stochastic_warfare.combat.air_combat import EnergyState

            _atk_alt = getattr(attacker.position, "altitude", 0.0)
            _atk_spd = getattr(attacker, "speed", 250.0)
            _def_alt = getattr(target.position, "altitude", 0.0)
            _def_spd = getattr(target, "speed", 250.0)
            _atk_energy = EnergyState(altitude_m=_atk_alt, speed_mps=_atk_spd)
            _def_energy = EnergyState(altitude_m=_def_alt, speed_mps=_def_spd)

        if (
            _consume_routed_ammunition(
                ctx,
                attacker,
                wpn_inst,
                ammo_def,
                quantity=1,
                timestamp=timestamp,
                current_time_s=current_time_s,
            )
            == 0
        ):
            return True, None
        result = engine.resolve_air_engagement(
            attacker_id=attacker.entity_id,
            defender_id=target.entity_id,
            attacker_pos=attacker.position,
            defender_pos=target.position,
            missile_pk=missile_pk,
            pilot_skill=pilot_skill,
            timestamp=timestamp,
            attacker_energy=_atk_energy,
            defender_energy=_def_energy,
            effective_bvr_range_modifier=_effective_bvr_range_modifier,
        )
        _publish_air_engagement_event(
            ctx,
            attacker,
            target,
            wpn_inst,
            timestamp,
            bool(result.hit),
            ammo_def,
        )
        if result.hit:
            return True, UnitStatus.DESTROYED
        return True, None

    # Air-to-ground (CAS): route bombs and missiles through air-ground engine
    if (
        atk_air
        and not tgt_air
        and (
            modeled_role is WeaponModeledRole.BOMB_DELIVERY
            or (modeled_role is None and wpn_cat in ("BOMB", "GUIDED_BOMB", "MISSILE_LAUNCHER"))
            or (modeled_role is not WeaponModeledRole.BOMB_DELIVERY and wpn_cat == "MISSILE_LAUNCHER")
        )
    ):
        # Phase 62d: cloud ceiling gate — unguided weapons need visual delivery
        if _ace:
            _wx_cas = getattr(ctx, "weather_engine", None)
            if _wx_cas is not None:
                try:
                    _ceiling = getattr(_wx_cas.current, "cloud_ceiling", 10000.0)
                    _guidance = getattr(
                        getattr(wpn_inst, "definition", None),
                        "guidance_type",
                        getattr(
                            # check ammo guidance if weapon has no guidance_type
                            getattr(wpn_inst, "current_ammo", None),
                            "guidance_type",
                            "none",
                        ),
                    )
                    _pgm_types = ("gps", "laser", "radar", "combined", "gps_ins", "semi_active", "active")
                    _is_pgm = str(_guidance).lower() in _pgm_types
                    if _ceiling < cal_flat.get("cloud_ceiling_min_attack_m", 500.0) and not _is_pgm:
                        logger.debug(
                            "CAS aborted: cloud ceiling %.0fm < %.0fm (unguided)",
                            _ceiling,
                            cal_flat.get("cloud_ceiling_min_attack_m", 500.0),
                        )
                        return True, None  # mission aborted
                except Exception as exc:
                    if failure_handler is not None and not failure_handler(
                        "environment.weather",
                        "read_cas_cloud_ceiling",
                        exc,
                    ):
                        raise
                    pass

        engine = getattr(ctx, "air_ground_engine", None)
        if engine is None:
            return False, None
        if not _routed_ammunition_ready(
            wpn_inst,
            ammo_def,
            current_time_s,
        ):
            return True, None
        weapon_pk = min(1.0, 0.4 * force_ratio_mod)

        # Phase 62d: icing + density penalties on CAS Pk
        if _ace:
            _cond_cas = getattr(ctx, "conditions_facade", None)
            if _cond_cas is not None:
                try:
                    _air_cas = _cond_cas.air(
                        attacker.position,
                        float(attacker.position.altitude or 0.0),
                        float(getattr(ctx.config, "latitude", 0.0)),
                        float(getattr(ctx.config, "longitude", 0.0)),
                    )
                    _icing_cas = getattr(_air_cas, "icing_risk", 0.0)
                    if _icing_cas > 0.5:
                        weapon_pk *= 1.0 - cal_flat.get("icing_power_penalty", 0.10)
                except Exception as exc:
                    if failure_handler is not None and not failure_handler(
                        "environment.conditions",
                        "read_cas_icing",
                        exc,
                    ):
                        raise
                    pass
            _wx_cas2 = getattr(ctx, "weather_engine", None)
            if _wx_cas2 is not None:
                try:
                    _alt_cas = getattr(attacker.position, "altitude", 0.0)
                    _rho_cas = _wx_cas2.atmospheric_density(_alt_cas)
                    weapon_pk *= min(1.0, _rho_cas / 1.225)
                except Exception as exc:
                    if failure_handler is not None and not failure_handler(
                        "environment.weather",
                        "compute_cas_density",
                        exc,
                    ):
                        raise
                    pass

        result = engine.execute_cas(
            aircraft_id=attacker.entity_id,
            target_id=target.entity_id,
            aircraft_pos=attacker.position,
            target_pos=target.position,
            weapon_pk=weapon_pk,
            timestamp=timestamp,
        )
        if result.aborted:
            return True, None
        if (
            _consume_routed_ammunition(
                ctx,
                attacker,
                wpn_inst,
                ammo_def,
                quantity=1,
                timestamp=timestamp,
                current_time_s=current_time_s,
            )
            == 0
        ):
            return True, None
        _publish_air_engagement_event(
            ctx,
            attacker,
            target,
            wpn_inst,
            timestamp,
            bool(result.hit),
            ammo_def,
        )
        if result.hit:
            return True, UnitStatus.DISABLED
        return True, None

    # Ground/Naval-to-air (air defense): route SAM/missile weapons
    if (
        tgt_air
        and not atk_air
        and wpn_cat
        in (
            "MISSILE_LAUNCHER",
            "SAM",
        )
    ):
        engine = getattr(ctx, "air_defense_engine", None)
        if engine is None:
            return False, None
        interceptor_pk = min(1.0, 0.4 * force_ratio_mod)
        if (
            _consume_routed_ammunition(
                ctx,
                attacker,
                wpn_inst,
                ammo_def,
                quantity=1,
                timestamp=timestamp,
                current_time_s=current_time_s,
            )
            == 0
        ):
            return True, None
        result = engine.fire_interceptor(
            ad_id=attacker.entity_id,
            target_id=target.entity_id,
            interceptor_pk=interceptor_pk,
            range_m=best_range,
            timestamp=timestamp,
        )
        _publish_air_engagement_event(
            ctx,
            attacker,
            target,
            wpn_inst,
            timestamp,
            bool(result.hit),
            ammo_def,
        )
        if result.hit:
            return True, UnitStatus.DESTROYED
        return True, None

    return False, None  # Non-air weapon category, fall through to direct fire


def _apply_indirect_fire_result(
    fm_result: Any,
    target: Unit,
    pending_damage: list[tuple[Unit, UnitStatus, str]],
    destruction_threshold: float = 0.5,
    disable_threshold: float = 0.3,
    cumulative_tracker: dict[str, int] | None = None,
    terrain_modifier: float = 1.0,
    lethal_radius_m: float = 50.0,
    casualty_per_hit: float = 0.15,
    weapon_id: str = "",
) -> None:
    """Apply the public pure aggregate assessment to ordinary battle state.

    ``terrain_modifier`` scales the per-hit damage fraction — cover reduces
    effective indirect-fire lethality.
    ``lethal_radius_m`` overrides the default 50 m lethal radius — pass
    ``ammo_def.blast_radius_m`` when available.
    ``casualty_per_hit`` overrides the default 0.15 casualty fraction per
    impact within the lethal radius.
    """
    from stochastic_warfare.combat.indirect_fire import (
        ImpactPoint,
        assess_indirect_fire_impacts,
    )

    assessment_impacts = [
        ImpactPoint(
            position=impact.position,
            ammo_id=getattr(impact, "ammo_id", "__ordinary_indirect__"),
        )
        for impact in fm_result.impacts
    ]
    prior_hits = cumulative_tracker.get(target.entity_id, 0) if cumulative_tracker is not None else 0
    assessment = assess_indirect_fire_impacts(
        assessment_impacts,
        target.position,
        {impact.ammo_id: lethal_radius_m for impact in assessment_impacts},
        prior_near_impact_count=prior_hits,
        terrain_modifier=terrain_modifier,
        casualty_per_impact=casualty_per_hit,
        destruction_threshold=destruction_threshold,
        disable_threshold=disable_threshold,
    )
    if assessment.near_impact_count <= 0:
        return
    if cumulative_tracker is not None:
        cumulative_tracker[target.entity_id] = assessment.cumulative_near_impact_count
    if assessment.resulting_status is not None:
        pending_damage.append(
            (
                target,
                assessment.resulting_status,
                weapon_id,
            )
        )


# ---------------------------------------------------------------------------
# Aggregate-path suppression helper (Phase 47)
# ---------------------------------------------------------------------------


def _apply_aggregate_suppression(
    ctx: Any,
    target: Unit,
    wpn_inst: Any,
    range_m: float,
    dt: float,
    suppression_states: dict[str, Any],
) -> None:
    """Apply suppression from aggregate fire (volley, archery, indirect).

    Mirrors the suppression wiring in the direct-fire path so that older-era
    engagements also generate suppression effects on the target.
    """
    sup_eng = getattr(ctx, "suppression_engine", None)
    if sup_eng is None:
        return
    tid = target.entity_id
    if tid not in suppression_states:
        suppression_states[tid] = UnitSuppressionState()
    sup_eng.apply_fire_volume(
        state=suppression_states[tid],
        rounds_per_minute=wpn_inst.definition.rate_of_fire_rpm,
        caliber_mm=wpn_inst.definition.caliber_mm,
        range_m=range_m,
        duration_s=dt,
    )


# ---------------------------------------------------------------------------
# Target scoring (Phase 41c)
# ---------------------------------------------------------------------------


def _target_value(
    target: Unit,
    *,
    hq: float = 2.0,
    ad: float = 1.8,
    artillery: float = 1.5,
    armor: float = 1.3,
    default: float = 1.0,
) -> float:
    """Target type priority for threat-based selection."""
    # HQ is highest value
    st = getattr(target, "support_type", None)
    if st is not None:
        st_name = st.name if hasattr(st, "name") else str(st)
        if st_name == "HQ":
            return hq
    # Air defense enables air ops
    if hasattr(target, "ad_type"):
        return ad
    # Artillery/rocket and armor
    gt = getattr(target, "ground_type", None)
    if gt is not None:
        gt_name = gt.name if hasattr(gt, "name") else str(gt)
        if "ARTILLERY" in gt_name or "ROCKET" in gt_name:
            return artillery
        if gt_name == "ARMOR":
            return armor
    return default


# ---------------------------------------------------------------------------
# Movement helpers
# ---------------------------------------------------------------------------


def _should_hold_position(unit: Unit) -> bool:
    """Return True if the unit should not advance toward enemies.

    Emplaced systems (SAMs, deployed artillery) fight from their
    position rather than maneuvering toward the enemy.
    """
    # Air defense units are always emplaced
    try:
        from stochastic_warfare.entities.unit_classes.air_defense import AirDefenseUnit

        if isinstance(unit, AirDefenseUnit):
            return True
    except ImportError:
        pass
    return False


def _movement_target(
    unit_pos: Position,
    enemies: list[Unit],
    centroid_weight: float = 0.5,
    enemy_pos_arr: np.ndarray | None = None,
) -> tuple[float, float]:
    """Compute a blended movement target from centroid and nearest enemy.

    Returns a point that is a weighted average of the enemy centroid
    (general advance toward the line) and the nearest enemy (local
    threat response).  This produces natural "lines closing" behavior
    rather than all units collapsing onto a single point.

    Phase 70a: vectorized path when *enemy_pos_arr* (shape (m,2)) is provided.
    """
    if enemy_pos_arr is not None and enemy_pos_arr.shape[0] > 0:
        centroid = np.mean(enemy_pos_arr, axis=0)
        upos = np.array([unit_pos.easting, unit_pos.northing])
        diffs = enemy_pos_arr - upos
        nearest = enemy_pos_arr[int(np.argmin(np.sum(diffs * diffs, axis=1)))]
        w = centroid_weight
        return (
            float(centroid[0] * w + nearest[0] * (1 - w)),
            float(centroid[1] * w + nearest[1] * (1 - w)),
        )

    # Scalar fallback
    cx = sum(e.position.easting for e in enemies) / len(enemies)
    cy = sum(e.position.northing for e in enemies) / len(enemies)

    best_dist_sq = float("inf")
    nx, ny = cx, cy
    ux, uy = unit_pos.easting, unit_pos.northing
    for e in enemies:
        dx = e.position.easting - ux
        dy = e.position.northing - uy
        d2 = dx * dx + dy * dy
        if d2 < best_dist_sq:
            best_dist_sq = d2
            nx, ny = e.position.easting, e.position.northing

    w = centroid_weight
    return cx * w + nx * (1 - w), cy * w + ny * (1 - w)


def _nearest_enemy_dist(
    unit_pos: Position,
    enemies: list[Unit],
    enemy_pos_arr: np.ndarray | None = None,
) -> float:
    """Return distance to the closest enemy.

    Phase 70a: vectorized path when *enemy_pos_arr* (shape (m,2)) is provided.
    """
    return _nearest_enemy_index_and_dist(
        unit_pos,
        enemies,
        enemy_pos_arr,
    )[1]


def _nearest_enemy_index_and_dist(
    unit_pos: Position,
    enemies: list[Unit],
    enemy_pos_arr: np.ndarray | None = None,
) -> tuple[int | None, float]:
    """Return the stable source index and distance of the closest enemy."""
    if enemy_pos_arr is not None and enemy_pos_arr.shape[0] > 0:
        upos = np.array([unit_pos.easting, unit_pos.northing])
        diffs = enemy_pos_arr - upos
        distances_sq = np.sum(diffs * diffs, axis=1)
        nearest_index = int(np.argmin(distances_sq))
        return nearest_index, float(np.sqrt(distances_sq[nearest_index]))

    best = float("inf")
    best_index: int | None = None
    ux, uy = unit_pos.easting, unit_pos.northing
    for index, e in enumerate(enemies):
        dx = e.position.easting - ux
        dy = e.position.northing - uy
        d = math.sqrt(dx * dx + dy * dy)
        if d < best:
            best = d
            best_index = index
    return best_index, best


def usable_weapon_standoff_range(
    unit: Unit,
    ctx: Any,
    target_domain: Domain | None = None,
) -> float:
    """Return the range at which this unit should stop advancing.

    Uses 80% of the best *usable* weapon's max range so the unit parks
    comfortably within engagement distance.  Weapons with no ammo remaining
    or that cannot engage *target_domain* are ignored — a unit that has
    expended all applicable ranged ammo will close to melee range.  Units
    without applicable weapons (or with only melee) close fully.  Omitting
    *target_domain* preserves the unrestricted legacy-fixture query.
    """
    weapons = getattr(ctx, "unit_weapons", {}).get(unit.entity_id, [])
    best_range = 0.0
    for wpn_inst, ammo_defs in weapons:
        if target_domain is not None and not _weapon_supports_domain(
            wpn_inst.definition,
            target_domain,
        ):
            continue
        r = wpn_inst.definition.max_range_m
        if r <= 10:
            continue  # melee / point-blank — no standoff
        # Check that the weapon still has ammo
        has_ammo = False
        for ad in ammo_defs:
            if wpn_inst.can_fire(ad.ammo_id):
                has_ammo = True
                break
        if has_ammo and r > best_range:
            best_range = r
    return best_range * 0.8 if best_range > 10 else 0.0


def nearest_enemy_weapon_standoff(
    unit: Unit,
    ctx: Any,
    enemies: list[Unit],
    enemy_pos_arr: np.ndarray | None = None,
) -> tuple[int | None, float, float]:
    """Return nearest enemy index, distance, and exact usable standoff."""
    nearest_index, nearest_dist = _nearest_enemy_index_and_dist(
        unit.position,
        enemies,
        enemy_pos_arr=enemy_pos_arr,
    )
    if nearest_index is None:
        return None, nearest_dist, 0.0
    return (
        nearest_index,
        nearest_dist,
        usable_weapon_standoff_range(
            unit,
            ctx,
            target_domain=enemies[nearest_index].domain,
        ),
    )


MovementCommitter = Callable[[Unit, Position], Position]
"""Fault-detector seam for validating a manager's final position commit."""


def _default_movement_committer(
    unit: Unit,
    proposed_position: Position,
) -> Position:
    """Return the production manager's proposed final position unchanged."""
    del unit
    return proposed_position


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class BattleConfig(BaseModel):
    """Tuning parameters for the battle manager."""

    engagement_range_m: float = 10000.0
    morale_check_interval: int = 12
    destruction_threshold: float = 0.5
    disable_threshold: float = 0.3
    default_visibility_m: float = DEFAULT_TARGETING_VISIBILITY_M
    max_ticks_per_battle: int = 50000
    # Phase 13a-6: Auto-resolve
    auto_resolve_enabled: bool = False
    auto_resolve_max_units: int = 0  # battles with <= this many total units get auto-resolved
    # Phase 48b: configurable elevation caps
    elevation_advantage_cap: float = 0.3
    elevation_disadvantage_floor: float = -0.1
    # Phase 48b: configurable target value weights
    target_value_hq: float = 2.0
    target_value_ad: float = 1.8
    target_value_artillery: float = 1.5
    target_value_armor: float = 1.3
    target_value_default: float = 1.0
    # Phase 48a: naval engagement defaults
    naval_config: NavalEngagementConfig = NavalEngagementConfig()


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class BattleContext:
    """Tracks state for one active battle."""

    battle_id: str
    start_tick: int
    start_time: datetime
    involved_sides: list[str]
    active: bool = True
    ticks_executed: int = 0
    # Track which units are involved in this battle
    unit_ids: set[str] = field(default_factory=set)
    # Wave attack assignments: entity_id → wave number (0=immediate, N=delayed, -1=reserve)
    wave_assignments: dict[str, int] = field(default_factory=dict)
    # Elapsed battle time in seconds (incremented each tactical tick)
    battle_elapsed_s: float = 0.0


@dataclass(frozen=True)
class BattleResult:
    """Outcome of a resolved battle."""

    battle_id: str
    duration_ticks: int
    terminated_by: str
    units_destroyed: dict[str, int] = field(default_factory=dict)
    units_routing: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class AutoResolveResult:
    """Outcome of an auto-resolved battle."""

    battle_id: str
    winner: str
    side_losses: dict[str, float] = field(default_factory=dict)  # side -> loss fraction
    duration_s: float = 0.0


@dataclass(frozen=True)
class DeferredOODADecision:
    """One propagated DECIDE completion waiting on logical simulation time.

    ``propagation`` is retained even when the order was interpreted correctly.
    That makes the deferred owner complete: resuming from a checkpoint never
    needs to rerun propagation, consume another C2 draw, or infer whether an
    effect was already applied.
    """

    unit_id: str
    battle_id: str
    due_elapsed_s: float
    propagation: PropagationResult


@dataclass(frozen=True)
class BattleStatePlan:
    """Validated, owner-bound tactical checkpoint commit plan."""

    owner_id: int
    battles: dict[str, BattleContext]
    next_battle_id: int
    vls_launches: dict[str, int]
    ammo_expended: dict[str, int]
    pending_decisions: dict[str, float]
    deferred_battle_ids: dict[str, str]
    cached_assessments: dict[str, SituationAssessment]
    ticks_stationary: dict[str, int]
    suppression_states: dict[str, UnitSuppressionState]
    cumulative_casualties: dict[str, int]
    undigging: dict[str, bool]
    concealment_scores: dict[str, float]
    env_casualty_accum: dict[str, float]
    misinterpreted_orders: dict[str, PropagationResult]
    lod_tiers: dict[str, int]
    lod_pending_tiers: dict[str, int]
    lod_pending_counts: dict[str, int]
    lod_promoted: set[str]
    fow_observer_unit_ids: frozenset[str]
    performance_execution_receipt: PerformanceReceiptRestorePlan


class _BattleExecutorOwnerAdapter:
    """Expose deliberate manager operations to injected battle executors."""

    __slots__ = ("_manager",)

    def __init__(self, manager: BattleManager) -> None:
        self._manager = manager

    @property
    def config_view(self) -> BattleExecutorConfigView:
        config = self._manager._config
        return BattleExecutorConfigView(
            destruction_threshold=config.destruction_threshold,
            disable_threshold=config.disable_threshold,
            elevation_advantage_cap=config.elevation_advantage_cap,
            elevation_disadvantage_floor=config.elevation_disadvantage_floor,
        )

    @property
    def movement_diagnostics(self) -> MovementDiagnostics | None:
        return self._manager._movement_diagnostics

    @property
    def movement_committer(self) -> MovementCommitter:
        return self._manager._movement_committer

    def stage_performance_delta(
        self,
        contribution: PerformanceReceiptDelta,
    ) -> None:
        self._manager._stage_performance_delta(contribution)

    def suppress_runtime_failure(
        self,
        subsystem: str,
        operation: str,
        exception: Exception,
    ) -> bool:
        return self._manager._suppress_runtime_failure(
            subsystem,
            operation,
            exception,
        )

    def targeting_distance(self, shooter: Unit, target: Unit) -> float:
        return self._manager._targeting_distance(shooter, target)

    def lod_tier(self, unit_id: str) -> int:
        return self._manager._lod_tiers.get(unit_id, int(UnitLodTier.ACTIVE))

    def is_undigging(self, unit_id: str) -> bool:
        return unit_id in self._manager._undigging

    def begin_undigging(self, unit_id: str) -> None:
        self._manager._undigging[unit_id] = True

    def finish_undigging(self, unit_id: str) -> None:
        self._manager._undigging.pop(unit_id, None)

    def revalidate_tactical_engagement(
        self,
        runtime: BattleTargetingRuntime,
        attacker: Unit,
        target: Unit,
        decision: TacticalTargetingDecision,
        *,
        current_distance_m: float,
    ) -> tuple[TargetingDisposition, WeaponAttachment | None]:
        return self._manager._revalidate_tactical_engagement(
            runtime,
            attacker,
            target,
            decision,
            current_distance_m=current_distance_m,
        )

    def compute_terrain_modifiers(
        self,
        runtime: BattleTargetingRuntime,
        target_position: Position,
        attacker_position: Position,
        *,
        seasonal_vegetation: float,
    ) -> tuple[float, float, float]:
        config = self._manager._config
        return self._manager._compute_terrain_modifiers(
            runtime,
            target_position,
            attacker_position,
            elevation_cap=config.elevation_advantage_cap,
            elevation_floor=config.elevation_disadvantage_floor,
            seasonal_vegetation=seasonal_vegetation,
            failure_handler=self.suppress_runtime_failure,
        )

    def score_target(
        self,
        attacker: Unit,
        target: Unit,
        distance_m: float,
        attacker_weapons: Collection[WeaponAttachment],
        runtime: BattleEngagementRuntime,
    ) -> float:
        return self._manager._score_target(
            attacker,
            target,
            distance_m,
            list(attacker_weapons),
            runtime,
        )

    def stage_engagement_intent(
        self,
        *,
        runtime: BattleEngagementRuntime,
        attacker: Unit,
        target: Unit,
        attachments: Collection[WeaponAttachment],
        enable_ammo_gate: bool,
        targeting_decision: TacticalTargetingDecision | None = None,
    ) -> _EngagementIntent | None:
        return self._manager._stage_engagement_intent(
            ctx=runtime,
            attacker=attacker,
            target=target,
            attachments=attachments,
            enable_ammo_gate=enable_ammo_gate,
            targeting_decision=targeting_decision,
        )

    def stage_routed_intent(
        self,
        *,
        runtime: BattleEngagementRuntime,
        attacker: Unit,
        enemies: Collection[Unit],
        attachments: Collection[WeaponAttachment],
        visibility_m: float,
        target_selection_mode: str,
        enable_ammo_gate: bool,
        air_routing_enabled: bool,
    ) -> _EngagementIntent | None:
        return self._manager._stage_routed_intent(
            ctx=runtime,
            attacker=attacker,
            enemies=enemies,
            attachments=attachments,
            visibility_m=visibility_m,
            target_selection_mode=target_selection_mode,
            enable_ammo_gate=enable_ammo_gate,
            air_routing_enabled=air_routing_enabled,
        )

    def arbitrate_engagement_intents(
        self,
        intents: Collection[_EngagementIntent],
        *,
        target_selection_mode: str,
    ) -> _EngagementIntent | None:
        return self._manager._arbitrate_engagement_intents(
            intents,
            target_selection_mode=target_selection_mode,
        )

    def publish_tactical_revalidation(
        self,
        runtime: TacticalTargetingRuntime,
        decision: TacticalTargetingDecision,
        disposition: TargetingDisposition,
    ) -> TacticalEngagementRevalidationOutcome:
        return self._manager._publish_tactical_revalidation(
            runtime,
            decision,
            disposition,
        )

    def targeting_visibility_bound(
        self,
        runtime: BattleTargetingRuntime,
        *,
        calibration: Mapping[str, object] | None = None,
    ) -> float:
        return self._manager._targeting_visibility_bound(
            runtime,
            calibration=calibration,
        )

    def advance_ooda_completion(
        self,
        runtime: BattleOODARuntime,
        *,
        unit_id: str,
        school: DoctrinalSchool | None,
        tactical_mult: float,
        timestamp: datetime,
    ) -> None:
        self._manager._advance_ooda_completion(
            runtime,
            unit_id=unit_id,
            school=school,
            tactical_mult=tactical_mult,
            timestamp=timestamp,
        )

    def propagate_ooda_decision(
        self,
        runtime: BattleOODARuntime,
        *,
        unit_id: str,
        timestamp: datetime,
    ) -> PropagationResult | None:
        return self._manager._propagate_ooda_decision(
            runtime,
            unit_id=unit_id,
            timestamp=timestamp,
        )

    def deferred_decision(self, unit_id: str) -> DeferredOODADecision | None:
        return self._manager._deferred_decision(unit_id)

    def queue_deferred_decision(
        self,
        *,
        unit_id: str,
        battle: BattleIntervalView,
        logical_time_s: float,
        propagation: PropagationResult,
    ) -> DeferredOODADecision:
        return self._manager._queue_deferred_decision(
            unit_id=unit_id,
            battle=battle,
            logical_time_s=logical_time_s,
            propagation=propagation,
        )

    def bind_deferred_ooda_owner(
        self,
        *,
        unit_id: str,
        battle: BattleIntervalView,
    ) -> None:
        self._manager._bind_deferred_ooda_owner(
            unit_id=unit_id,
            battle=battle,
        )

    def pop_deferred_decision(self, unit_id: str) -> DeferredOODADecision | None:
        return self._manager._pop_deferred_decision(unit_id)

    def validate_deferred_ooda_state(self) -> None:
        pending = set(self._manager._pending_decisions)
        if not pending <= set(self._manager._deferred_battle_ids):
            raise RuntimeError("Deferred OODA decision ownership is incomplete")
        if set(self._manager._misinterpreted_orders) != pending:
            raise RuntimeError(
                "Current deferred-OODA state requires exactly one propagation "
                "record per pending decision",
            )

    def deferred_ooda_owner_items(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(self._manager._deferred_battle_ids.items()))

    def deferred_ooda_owner(self, unit_id: str) -> str | None:
        return self._manager._deferred_battle_ids.get(unit_id)

    def cached_assessment(self, unit_id: str) -> SituationAssessment | None:
        return self._manager._cached_assessments.get(unit_id)

    def cache_assessment(
        self,
        unit_id: str,
        assessment: SituationAssessment,
    ) -> None:
        self._manager._cached_assessments[unit_id] = assessment

    def find_unit_side(self, runtime: BattleOODARuntime, unit_id: str) -> str:
        return self._manager._find_unit_side(runtime, unit_id)

    def compute_c2_effectiveness(
        self,
        runtime: BattleOODARuntime,
        unit_id: str,
        side: str,
    ) -> float:
        return self._manager._compute_c2_effectiveness(
            runtime,
            unit_id,
            side,
            failure_handler=self.suppress_runtime_failure,
        )

    def get_unit_morale_level(
        self,
        runtime: BattleOODARuntime,
        unit_id: str,
    ) -> float:
        return self._manager._get_unit_morale_level(runtime, unit_id)

    def get_unit_supply_level(
        self,
        runtime: BattleOODARuntime,
        unit_id: str,
    ) -> float:
        return self._manager._get_unit_supply_level(
            runtime,
            unit_id,
            failure_handler=self.suppress_runtime_failure,
        )

    def build_assessment_summary(
        self,
        runtime: BattleOODARuntime,
        unit_id: str,
        assessment: SituationAssessment | None,
    ) -> dict[str, float]:
        return self._manager._build_assessment_summary(
            runtime,
            unit_id,
            assessment,
            failure_handler=self.suppress_runtime_failure,
        )

    def concealment_score(self, target_id: str, fallback: float) -> float:
        return self._manager._concealment_scores.get(target_id, fallback)

    def update_legacy_concealment(
        self,
        target_id: str,
        *,
        terrain_concealment: float,
        target_is_moving: bool,
        observation_decay: float,
    ) -> float:
        scores = self._manager._concealment_scores
        if target_id not in scores:
            scores[target_id] = terrain_concealment
        if target_is_moving:
            scores[target_id] = terrain_concealment * 0.5
        scores[target_id] = max(0.0, scores[target_id] - observation_decay)
        return scores[target_id]

    def ammunition_expenditure(
        self,
        key: str,
        *,
        fallback_key: str | None = None,
    ) -> int:
        fallback = (
            0
            if fallback_key is None
            else self._manager._ammo_expended.get(fallback_key, 0)
        )
        return self._manager._ammo_expended.get(key, fallback)

    def record_ammunition_expenditure(
        self,
        key: str,
        quantity: int,
        *,
        fallback_key: str | None = None,
    ) -> None:
        self._manager._ammo_expended[key] = (
            self.ammunition_expenditure(key, fallback_key=fallback_key)
            + quantity
        )

    def cumulative_casualties(self, unit_id: str) -> int:
        return self._manager._cumulative_casualties.get(unit_id, 0)

    def apply_aggregate_casualties(
        self,
        casualties: int,
        target: Unit,
        pending_damage: list[tuple[Unit, UnitStatus, str]],
        destruction_threshold: float,
        disable_threshold: float,
        *,
        event_bus: EventBus | None = None,
        attacker: Unit | None = None,
        weapon: WeaponInstance | None = None,
        best_range_m: float = 0.0,
    ) -> None:
        _apply_aggregate_casualties(
            casualties,
            target,
            pending_damage,
            destruction_threshold,
            disable_threshold,
            self._manager._cumulative_casualties,
            event_bus=event_bus,
            attacker=attacker,
            wpn_inst=weapon,
            best_range=best_range_m,
        )

    def apply_indirect_fire_result(
        self,
        result: FireMissionResult | SalvoResult,
        target: Unit,
        pending_damage: list[tuple[Unit, UnitStatus, str]],
        destruction_threshold: float,
        disable_threshold: float,
        terrain_modifier: float,
        *,
        lethal_radius_m: float,
        casualty_per_hit: float = 0.15,
        weapon_id: str,
    ) -> None:
        _apply_indirect_fire_result(
            result,
            target,
            pending_damage,
            destruction_threshold,
            disable_threshold,
            self._manager._cumulative_casualties,
            terrain_modifier,
            lethal_radius_m=lethal_radius_m,
            casualty_per_hit=casualty_per_hit,
            weapon_id=weapon_id,
        )

    def apply_aggregate_suppression(
        self,
        runtime: BattleEngagementRuntime,
        target: Unit,
        weapon: WeaponInstance,
        range_m: float,
        dt_seconds: float,
    ) -> None:
        _apply_aggregate_suppression(
            runtime,
            target,
            weapon,
            range_m,
            dt_seconds,
            self._manager._suppression_states,
        )

    def suppression_state(self, unit_id: str) -> UnitSuppressionState:
        return self._manager._suppression_states.setdefault(
            unit_id,
            UnitSuppressionState(),
        )

    def route_naval_engagement(
        self,
        runtime: BattleEngagementRuntime,
        attacker: Unit,
        target: Unit,
        weapon: WeaponInstance,
        range_m: float,
        dt_seconds: float,
        timestamp: datetime,
        *,
        force_ratio_modifier: float,
        ammunition: AmmoDefinition,
        current_time_s: float,
        runtime_system_multiplier: int,
        modeled_role: WeaponModeledRole | None,
    ) -> tuple[bool, UnitStatus | None]:
        return _route_naval_engagement(
            runtime,
            attacker,
            target,
            weapon,
            range_m,
            dt_seconds,
            timestamp,
            naval_config=self._manager._config.naval_config,
            force_ratio_mod=force_ratio_modifier,
            vls_launches=self._manager._vls_launches,
            ammo_def=ammunition,
            current_time_s=current_time_s,
            runtime_system_multiplier=runtime_system_multiplier,
            modeled_role=modeled_role,
        )

    def checkpoint_snapshot(self) -> BattleCheckpointSnapshot:
        manager = self._manager
        return BattleCheckpointSnapshot(
            battles={
                battle_id: BattleIntervalView.from_battle(battle)
                for battle_id, battle in manager._battles.items()
            },
            next_battle_id=manager._next_battle_id,
            vls_launches=manager._vls_launches,
            ammo_expended=manager._ammo_expended,
            pending_decisions=manager._pending_decisions,
            deferred_battle_ids=manager._deferred_battle_ids,
            cached_assessments=manager._cached_assessments,
            ticks_stationary=manager._ticks_stationary,
            suppression_states=manager._suppression_states,
            cumulative_casualties=manager._cumulative_casualties,
            undigging=manager._undigging,
            concealment_scores=manager._concealment_scores,
            env_casualty_accum=manager._env_casualty_accum,
            misinterpreted_orders=manager._misinterpreted_orders,
            lod_tiers=manager._lod_tiers,
            lod_pending_tiers=manager._lod_pending_tiers,
            lod_pending_counts=manager._lod_pending_counts,
            lod_promoted=manager._lod_promoted,
            fow_observer_unit_ids=manager._fow_observer_unit_ids,
        )

    @property
    def checkpoint_owner_id(self) -> int:
        return id(self._manager)

    @property
    def performance_effective_flags(self) -> EffectivePerformanceFlags:
        return self._manager._performance_receipts.effective_flags

    @property
    def performance_tactical_interval_microseconds(self) -> int:
        return self._manager._performance_receipts.tactical_interval_microseconds

    def checkpoint_performance_state(self) -> dict[str, object]:
        return self._manager._performance_receipts.checkpoint_state(
            self._manager,
        )

    def stage_performance_receipt_state(
        self,
        state: object,
    ) -> PerformanceReceiptRestorePlan:
        return self._manager._performance_receipts.stage_state(
            self._manager,
            state,
        )

    def apply_checkpoint_plan(self, plan: BattleStatePlan) -> None:
        self._manager._apply_checkpoint_plan(plan)


# ---------------------------------------------------------------------------
# Battle Manager
# ---------------------------------------------------------------------------


class BattleManager:
    """Manages tactical-level battle resolution.

    Orchestrates the full tactical loop per tick: detection → AI →
    orders → movement → engagement → morale → supply consumption.

    Parameters
    ----------
    event_bus : EventBus
        For publishing battle events.
    config : BattleConfig | None
        Tuning parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: BattleConfig | None = None,
        *,
        movement_diagnostics: MovementDiagnostics | None = None,
        movement_committer: MovementCommitter | None = None,
        effective_performance_flags: EffectivePerformanceFlags | None = None,
        tactical_interval_seconds: float = 5.0,
        ooda_executor: BattleOODAExecutor | None = None,
        movement_executor: BattleMovementExecutor | None = None,
        engagement_executor: BattleEngagementExecutor | None = None,
        checkpoint_executor: BattleCheckpointExecutor | None = None,
        failure_handler: BattleRuntimeFailureHandler | None = None,
    ) -> None:
        flags = resolve_supported_runtime_performance_flags(
            effective_performance_flags
            if effective_performance_flags is not None
            else EffectivePerformanceFlags(
                enable_detection_culling=True,
                enable_scan_scheduling=False,
                enable_lod=False,
                enable_soa=False,
                enable_parallel_detection=False,
            ),
        )
        tactical_interval_microseconds = _clock_duration_microseconds(
            tactical_interval_seconds,
            field_name="tactical_interval_seconds",
        )
        self._bus = event_bus
        self._config = config or BattleConfig()
        self._movement_diagnostics = movement_diagnostics
        # This callable cannot be selected by scenario data.  It exists only
        # to prove that diagnostics detect a broken final position commit.
        self._movement_committer = movement_committer or _default_movement_committer
        # A standalone manager is authoritative by default: without an
        # injected policy, no enabled-subsystem exception may use a fallback.
        self._failure_handler = failure_handler
        self._battles: dict[str, BattleContext] = {}
        self._next_battle_id = 0
        # OBSERVE output is consumed by a later DECIDE phase and therefore is
        # outcome-affecting checkpoint state rather than a transient cache.
        self._cached_assessments: dict[str, SituationAssessment] = {}
        # Phase 40b: posture tracking (ticks unit has been stationary)
        self._ticks_stationary: dict[str, int] = {}
        # Phase 40e: per-unit suppression state
        self._suppression_states: dict[str, UnitSuppressionState] = {}
        # Phase 47: cumulative aggregate casualties per unit — volley/archery
        # models produce few casualties per tick, so we must accumulate across
        # volleys and assess thresholds on the running total.
        self._cumulative_casualties: dict[str, int] = {}
        # Phase 50a: units transitioning from DUG_IN/FORTIFIED to MOVING
        self._undigging: dict[str, bool] = {}
        # Phase 50c: persistent concealment scores per target
        self._concealment_scores: dict[str, float] = {}
        # Phase 51a: VLS magazine tracking (entity_id → missiles launched)
        self._vls_launches: dict[str, int] = {}
        # Phase 62a: fractional environmental casualty accumulator
        self._env_casualty_accum: dict[str, float] = {}
        # Phase 68b: general ammo expenditure tracking (unit_id:weapon_name → rounds fired)
        self._ammo_expended: dict[str, int] = {}
        # Deferred OODA decisions retain both their logical due time and their
        # one-shot propagation result.  The two legacy-named maps remain the
        # on-wire checkpoint representation for format compatibility.
        self._pending_decisions: dict[str, float] = {}
        self._misinterpreted_orders: dict[str, PropagationResult] = {}
        # Internal-only ownership is reconstructed from active battle rosters
        # when format-118 state is restored.
        self._deferred_battle_ids: dict[str, str] = {}
        # Phase 70c: signature cache (unit_type → signature profile, immutable)
        self._signature_cache: dict[str, Any] = {}
        # Phase 85: LOD tier tracking
        self._lod_tiers: dict[str, int] = {}
        self._lod_pending_tiers: dict[str, int] = {}
        self._lod_pending_counts: dict[str, int] = {}
        self._lod_promoted: set[str] = set()
        self._fow_observer_unit_ids: frozenset[str] = frozenset()
        self._performance_receipts = PerformanceReceiptAccumulator(
            owner=self,
            effective_flags=flags,
            tactical_interval_microseconds=tactical_interval_microseconds,
        )
        self._performance_transaction: PerformanceReceiptTransaction | None = None
        self._tactical_observation_owner_token = object()
        self._active_tactical_observation_plan: _TacticalObservationPlan | None = None
        from stochastic_warfare.simulation.battle_ooda_executor import (
            DefaultBattleOODAExecutor,
        )
        from stochastic_warfare.simulation.battle_movement_executor import (
            DefaultBattleMovementExecutor,
        )
        from stochastic_warfare.simulation.battle_engagement_executor import (
            DefaultBattleEngagementExecutor,
        )
        from stochastic_warfare.simulation.battle_checkpoint_executor import (
            DefaultBattleCheckpointExecutor,
        )

        self._executor_owner: BattleExecutorOwner = _BattleExecutorOwnerAdapter(
            self,
        )
        self._ooda_executor = (
            DefaultBattleOODAExecutor()
            if ooda_executor is None
            else ooda_executor
        )
        self._movement_executor = (
            DefaultBattleMovementExecutor()
            if movement_executor is None
            else movement_executor
        )
        self._engagement_executor = (
            DefaultBattleEngagementExecutor()
            if engagement_executor is None
            else engagement_executor
        )
        self._checkpoint_executor = (
            DefaultBattleCheckpointExecutor()
            if checkpoint_executor is None
            else checkpoint_executor
        )

    def _suppress_runtime_failure(
        self,
        subsystem: str,
        operation: str,
        exception: Exception,
    ) -> bool:
        """Delegate degraded fallback authorization to the runtime owner."""
        if self._failure_handler is None:
            return False
        return self._failure_handler(subsystem, operation, exception)

    # ── Performance execution evidence ─────────────────────────────

    def begin_performance_interval(
        self,
        *,
        dt_seconds: float,
    ) -> PerformanceReceiptTransaction:
        """Begin the sole production receipt transaction for one interval."""
        interval_microseconds = _clock_duration_microseconds(
            dt_seconds,
            field_name="dt_seconds",
        )
        if interval_microseconds != self._performance_receipts.tactical_interval_microseconds:
            raise ValueError(
                "Performance-governed tactical interval disagrees with the bound runtime cadence",
            )
        transaction = self._performance_receipts.begin(self)
        self._performance_transaction = transaction
        try:
            self._performance_receipts.stage(
                self,
                transaction,
                PerformanceReceiptDelta(
                    tactical_intervals=1,
                    tactical_duration_microseconds=interval_microseconds,
                ),
            )
        except BaseException as exc:
            try:
                self._performance_receipts.poison(
                    self,
                    transaction,
                    reason=(f"initial performance receipt staging failed: {type(exc).__name__}"),
                )
            except BaseException:
                pass
            self._performance_transaction = None
            raise
        return transaction

    def _stage_performance_delta(
        self,
        contribution: PerformanceReceiptDelta,
    ) -> None:
        """Stage observational work for the active engine transaction."""
        transaction = self._performance_transaction
        if transaction is None:
            return
        self._performance_receipts.stage(
            self,
            transaction,
            contribution,
        )

    def stage_fow_cycle_receipt(
        self,
        receipt: FogOfWarCycleReceipt,
    ) -> None:
        """Stage one validated FOW side-cycle receipt."""
        transaction = self._performance_transaction
        if transaction is None:
            return
        self._performance_receipts.stage_fow_cycle(
            self,
            transaction,
            receipt,
        )

    def commit_performance_interval(
        self,
        transaction: PerformanceReceiptTransaction,
    ) -> PerformanceExecutionReceipt:
        """Commit a fully reconciled all-battle interval receipt."""
        if transaction is not self._performance_transaction:
            raise RuntimeError("Performance receipt transaction is not active")
        try:
            receipt = self._performance_receipts.commit(self, transaction)
        finally:
            self._performance_transaction = None
        return receipt

    def poison_performance_interval(
        self,
        transaction: PerformanceReceiptTransaction,
        *,
        reason: str,
    ) -> None:
        """Permanently reject evidence after a later interval failure."""
        if transaction is not self._performance_transaction:
            raise RuntimeError("Performance receipt transaction is not active")
        self._performance_receipts.poison(
            self,
            transaction,
            reason=reason,
        )
        self._performance_transaction = None

    def performance_execution_receipt(self) -> PerformanceExecutionReceipt:
        """Return the immutable committed production execution receipt."""
        return self._performance_receipts.receipt(self)

    def validate_performance_runtime(self, ctx: Any) -> None:
        """Cross-bind live calibration owners to the committed receipt flags."""
        runtime_config = getattr(ctx, "config", None)
        configured_calibration = getattr(
            runtime_config,
            "calibration_overrides",
            None,
        )
        calibration = getattr(ctx, "calibration", None)
        flat_calibration = _resolve_cal_flat(ctx)
        effective_flags = resolve_cross_bound_runtime_performance_flags(
            authored_configuration=(
                configured_calibration
                if configured_calibration is not None
                else calibration if calibration is not None else flat_calibration
            ),
            typed_calibration=(
                calibration if calibration is not None else flat_calibration
            ),
            flat_calibration=flat_calibration,
        )
        if effective_flags != self._performance_receipts.effective_flags:
            raise RuntimeError(
                "Live performance calibration diverged from the committed "
                "performance receipt flags",
            )

    # ── Engagement detection ────────────────────────────────────────

    def detect_engagement(
        self,
        units_by_side: dict[str, list[Unit]],
        engagement_range_m: float | None = None,
        *,
        timestamp: datetime,
    ) -> list[BattleContext]:
        """Detect new engagements based on proximity between opposing forces.

        Returns newly created :class:`BattleContext` instances for each
        detected engagement (forces within engagement range).
        """
        eng_range = engagement_range_m or self._config.engagement_range_m
        sides = list(units_by_side.keys())
        new_battles: list[BattleContext] = []

        for i, side_a in enumerate(sides):
            for side_b in sides[i + 1 :]:
                active_a = [u for u in units_by_side[side_a] if u.status == UnitStatus.ACTIVE]
                active_b = [u for u in units_by_side[side_b] if u.status == UnitStatus.ACTIVE]
                if not active_a or not active_b:
                    continue

                # Check if any pair is within engagement range
                min_dist = self._min_distance(active_a, active_b)
                if min_dist <= eng_range:
                    # Check if these sides already have an active battle
                    pair = frozenset({side_a, side_b})
                    already_active = any(
                        frozenset(b.involved_sides) == pair and b.active for b in self._battles.values()
                    )
                    if not already_active:
                        battle = BattleContext(
                            battle_id=f"battle_{self._next_battle_id:04d}",
                            start_tick=0,
                            start_time=timestamp,
                            involved_sides=[side_a, side_b],
                            unit_ids={u.entity_id for u in active_a + active_b},
                        )
                        self._next_battle_id += 1
                        self._battles[battle.battle_id] = battle
                        new_battles.append(battle)
                        logger.info(
                            "New battle detected: %s (%s vs %s), min distance %.0fm",
                            battle.battle_id,
                            side_a,
                            side_b,
                            min_dist,
                        )

        return new_battles

    # ── Tactical tick ───────────────────────────────────────────────

    def _stage_battle_observation_publication(
        self,
        *,
        lod_plan: _LODClassificationPlan,
        witness_promoted_unit_ids: frozenset[str],
        signature_cache: Mapping[str, Any],
        concealment_scores: Mapping[str, float],
        observer_unit_ids: frozenset[str],
    ) -> _BattleObservationPublication:
        """Materialize every Battle-owned observation container before commit."""
        promoted = self._validate_lod_publication(
            lod_plan,
            witness_promoted_unit_ids=witness_promoted_unit_ids,
        )
        lod_tiers = dict(lod_plan.lod_tiers)
        pending_tiers = dict(lod_plan.pending_tiers)
        pending_counts = dict(lod_plan.pending_counts)
        for unit_id in promoted:
            lod_tiers[unit_id] = UnitLodTier.ACTIVE
            pending_tiers.pop(unit_id, None)
            pending_counts.pop(unit_id, None)
        next_concealment = dict(self._concealment_scores)
        next_concealment.update(concealment_scores)
        return _BattleObservationPublication(
            signature_cache=dict(signature_cache),
            concealment_scores=next_concealment,
            lod_tiers=lod_tiers,
            lod_pending_tiers=pending_tiers,
            lod_pending_counts=pending_counts,
            lod_promoted=set(),
            fow_observer_unit_ids=observer_unit_ids,
            _prior_signature_cache=dict(self._signature_cache),
            _prior_concealment_scores=dict(self._concealment_scores),
            _prior_lod_tiers=dict(self._lod_tiers),
            _prior_lod_pending_tiers=dict(self._lod_pending_tiers),
            _prior_lod_pending_counts=dict(self._lod_pending_counts),
            _prior_lod_promoted=set(self._lod_promoted),
            _prior_fow_observer_unit_ids=self._fow_observer_unit_ids,
        )

    def _validate_tactical_observation_plan(
        self,
        plan: _TacticalObservationPlan,
    ) -> None:
        """Run all fallible cross-owner checks before the first state swap."""
        if type(plan) is not _TacticalObservationPlan:
            raise TypeError("plan must be a _TacticalObservationPlan")
        if (
            plan._owner_token is not self._tactical_observation_owner_token
            or self._active_tactical_observation_plan is not plan
        ):
            raise ValueError("tactical observation plan is foreign or stale")
        publication = plan.battle_publication
        if (
            self._signature_cache != publication._prior_signature_cache
            or self._concealment_scores != publication._prior_concealment_scores
            or self._lod_tiers != publication._prior_lod_tiers
            or self._lod_pending_tiers != publication._prior_lod_pending_tiers
            or self._lod_pending_counts != publication._prior_lod_pending_counts
            or self._lod_promoted != publication._prior_lod_promoted
            or self._fow_observer_unit_ids != publication._prior_fow_observer_unit_ids
        ):
            raise RuntimeError(
                "Battle observation state changed during isolated staging",
            )
        plan.targeting_owner.validate_publication_plan(
            plan.targeting_publication,
        )
        if plan.fow is not None:
            if plan.fow_owner is None or plan.rng_owner is None:
                raise RuntimeError("FOW observation plan is missing an owner")
            staged = plan.fow
            plan.rng_owner.validate_prepared_fow_detection_interval_commit(
                staged.indexed_commit,
            )
            plan.fow_owner.cadence.validate_prepared_interval_commit(
                staged.cadence_commit,
            )
            plan.fow_owner.validate_prepared_update_commit(
                staged.fow_commit,
            )
            record = staged.indexed_commit.record
            if (
                record.engine_tick != plan.engine_tick
                or record.reporting_sides != staged.reporting_sides
                or len(record.entries) != staged.expected_indexed_entries
            ):
                raise RuntimeError(
                    "Prepared indexed FOW record disagrees with staged side receipts",
                )
        elif plan.witness_clear is not None:
            if plan.fow_owner is None:
                raise RuntimeError("Witness-clear plan is missing its owner")
            plan.fow_owner.validate_prepared_witness_clear(
                plan.witness_clear,
            )

    def _commit_prevalidated_tactical_observation(
        self,
        plan: _TacticalObservationPlan,
    ) -> None:
        """Publish every prevalidated owner using only bounded state swaps."""
        if plan.fow is not None:
            staged = plan.fow
            plan.rng_owner._commit_prevalidated_fow_detection_interval(
                staged.indexed_commit,
            )
            plan.fow_owner.cadence._commit_prevalidated_interval(
                staged.cadence_commit,
            )
            plan.fow_owner._commit_prevalidated_update(staged.fow_commit)
        elif plan.witness_clear is not None:
            plan.fow_owner._commit_prevalidated_witness_clear(
                plan.witness_clear,
            )

        publication = plan.battle_publication
        self._signature_cache = publication.signature_cache
        self._concealment_scores = publication.concealment_scores
        self._lod_tiers = publication.lod_tiers
        self._lod_pending_tiers = publication.lod_pending_tiers
        self._lod_pending_counts = publication.lod_pending_counts
        self._lod_promoted = publication.lod_promoted
        self._fow_observer_unit_ids = publication.fow_observer_unit_ids
        plan.targeting_owner._commit_prevalidated_publication(
            plan.targeting_publication,
        )
        self._active_tactical_observation_plan = None

    @staticmethod
    def _abort_staged_fow_observation(ctx: Any, staged: _StagedFOWObservation) -> None:
        """Poison all incomplete FOW evidence owners without hiding failures."""
        fog_of_war = ctx.fog_of_war
        try:
            fog_of_war.abort_update_transaction(staged.transaction)
        except BaseException:
            pass
        try:
            fog_of_war.cadence.abort_interval(staged.cadence_plan)
        except BaseException:
            pass
        try:
            ctx.rng_manager.abort_fow_detection_interval(
                staged.indexed_allocation,
            )
        except BaseException:
            pass

    def prepare_tactical_interval(
        self,
        ctx: Any,
        battles: Iterable[BattleContext],
        dt: float,
    ) -> tuple[BattleContext, ...]:
        """Prepare one side-wide observation interval before battle pictures.

        Production contexts own one ``TacticalTargetingRuntime``.  This
        boundary advances target concealment once, performs the sole FOW
        update for the complete active roster, and only then publishes the
        immutable interval topology to that runtime.  A context without that
        owner may continue only with fog of war disabled; :meth:`execute_tick`
        rejects enabled FOW before mutating battle state.
        """
        self.validate_performance_runtime(ctx)
        targeting = getattr(ctx, "tactical_targeting", None)
        canonical_battles = tuple(
            sorted(
                (battle for battle in battles if battle.active),
                key=lambda battle: battle.battle_id,
            )
        )
        if targeting is None or not canonical_battles:
            return canonical_battles

        cal_flat = _resolve_cal_flat(ctx)
        logical_time_s = float(ctx.clock.elapsed.total_seconds())
        engine_tick = int(ctx.clock.tick_count)
        enable_fow = bool(cal_flat.get("enable_fog_of_war", False))
        reporting_side_count = len(ctx.units_by_side) if enable_fow else 0
        parallel_dispatch = bool(
            enable_fow and cal_flat.get("enable_parallel_detection", False) and reporting_side_count >= 2
        )
        self._stage_performance_delta(
            PerformanceReceiptDelta(
                dispatch=DispatchReceipt(
                    sequential_intervals=int(not parallel_dispatch),
                    sequential_side_updates=(0 if parallel_dispatch else reporting_side_count),
                    parallel_intervals=int(parallel_dispatch),
                    parallel_tasks_submitted=(reporting_side_count if parallel_dispatch else 0),
                    parallel_tasks_joined=(reporting_side_count if parallel_dispatch else 0),
                ),
            ),
        )
        # Reject a duplicate/regressing coordinator call before it can decay
        # concealment or consume another DETECTION draw.  The runtime repeats
        # this guard at publication so the invariant has one authoritative
        # owner even when callers bypass this production coordinator.
        targeting.validate_interval_advance(
            engine_tick=engine_tick,
            logical_time_s=logical_time_s,
        )

        active_enemies, enemy_pos_arrays = self._build_enemy_data(
            ctx.units_by_side,
        )
        lod_plan = self._stage_lod_tiers(
            ctx,
            ctx.units_by_side,
            enemy_pos_arrays,
            active_enemies=active_enemies,
        )
        # Concealment is target-owned mutable state.  Resolve it once for the
        # complete roster so neither observer iteration nor overlapping battle
        # membership decays the same target repeatedly in one interval.
        seasonal_vegetation = 0.0
        seasons_engine = getattr(ctx, "seasons_engine", None)
        if seasons_engine is not None and cal_flat.get("enable_seasonal_effects", False):
            seasonal_vegetation = float(
                seasons_engine.current.vegetation_density,
            )
        decay = float(cal_flat.get("observation_decay_rate", 0.05))
        staged_concealment: dict[str, float] = {}
        for unit in sorted(ctx.all_units(), key=lambda item: item.entity_id):
            if unit.status != UnitStatus.ACTIVE:
                continue
            _, _, terrain_concealment = self._compute_terrain_modifiers(
                ctx,
                unit.position,
                unit.position,
                elevation_cap=self._config.elevation_advantage_cap,
                elevation_floor=self._config.elevation_disadvantage_floor,
                seasonal_vegetation=seasonal_vegetation,
            )
            current = self._concealment_scores.get(
                unit.entity_id,
                terrain_concealment,
            )
            if unit.speed > 0.5:
                current = terrain_concealment * 0.5
            staged_concealment[unit.entity_id] = max(0.0, current - decay)
        if self._active_tactical_observation_plan is not None:
            raise RuntimeError("a tactical observation publication is already active")
        fog_of_war = getattr(ctx, "fog_of_war", None)
        staged_fow: _StagedFOWObservation | None = None
        witness_clear: FogOfWarWitnessClearPlan | None = None
        try:
            if enable_fow:
                if fog_of_war is None:
                    raise RuntimeError(
                        "Fog-of-war targeting is enabled without a FogOfWarManager",
                    )
                staged_fow = self._update_interval_fog_of_war(
                    ctx,
                    dt=dt,
                    engine_tick=engine_tick,
                    logical_time_s=logical_time_s,
                    cal_flat=cal_flat,
                    lod_plan=lod_plan,
                    concealment_scores=staged_concealment,
                )
                outcomes_by_side = dict(
                    zip(
                        staged_fow.reporting_sides,
                        staged_fow.outcomes,
                        strict=True,
                    ),
                )
                world_views = {side: outcome.world_view for side, outcome in outcomes_by_side.items()}
                witnesses = {side: outcome.witnesses for side, outcome in outcomes_by_side.items()}
                observer_track_supports = {
                    side: outcome.observer_track_supports for side, outcome in outcomes_by_side.items()
                }
                cadence_ordinal = staged_fow.cadence_plan.ordinal
                support_process_noise_std_mps2 = fog_of_war.observer_track_support_process_noise_std_mps2
                support_max_position_uncertainty_m = fog_of_war.observer_track_support_max_position_uncertainty_m
                signature_cache = staged_fow.signature_cache
                observer_unit_ids = staged_fow.observer_unit_ids
                witness_promoted_unit_ids = staged_fow.witness_promoted_unit_ids
            else:
                self._validate_lod_publication(lod_plan)
                self._stage_performance_delta(
                    PerformanceReceiptDelta(lod=lod_plan.receipt),
                )
                if fog_of_war is not None and hasattr(
                    fog_of_war,
                    "prepare_witness_clear",
                ):
                    witness_clear = fog_of_war.prepare_witness_clear()
                world_views = {}
                witnesses = {}
                observer_track_supports = {}
                cadence_ordinal = None
                support_process_noise_std_mps2 = None
                support_max_position_uncertainty_m = None
                signature_cache = self._signature_cache
                observer_unit_ids = frozenset()
                witness_promoted_unit_ids = frozenset()

            battle_publication = self._stage_battle_observation_publication(
                lod_plan=lod_plan,
                witness_promoted_unit_ids=witness_promoted_unit_ids,
                signature_cache=signature_cache,
                concealment_scores=staged_concealment,
                observer_unit_ids=observer_unit_ids,
            )
            observation = _TargetingObservationSnapshot(
                fog_of_war_enabled=enable_fow,
                concealment_scores=battle_publication.concealment_scores,
                world_views=world_views,
                witnesses=witnesses,
                observer_track_supports=observer_track_supports,
                cadence_ordinal=cadence_ordinal,
                support_process_noise_std_mps2=(support_process_noise_std_mps2),
                support_max_position_uncertainty_m=(support_max_position_uncertainty_m),
            )
            unit_sides = {unit.entity_id: side for side, units in sorted(ctx.units_by_side.items()) for unit in units}
            interval = targeting.stage_interval(
                engine_tick=engine_tick,
                logical_time_s=logical_time_s,
                fog_of_war_enabled=enable_fow,
                unit_sides=unit_sides,
                battle_memberships={battle.battle_id: tuple(sorted(battle.unit_ids)) for battle in canonical_battles},
            )
            # Resolve every picture from the same staged post-observation,
            # pre-movement snapshot without reading any newly committed owner.
            evidence_cache = _TargetingIntervalEvidenceCache(
                observation=observation,
            )
            pictures = tuple(
                self._resolve_targeting_picture(
                    ctx,
                    battle,
                    interval=interval,
                    evidence_cache=evidence_cache,
                )
                for battle in canonical_battles
            )
            targeting_publication = targeting.stage_publication(
                interval,
                pictures,
            )
            outer_plan = _TacticalObservationPlan(
                engine_tick=engine_tick,
                targeting_owner=targeting,
                targeting_publication=targeting_publication,
                battle_publication=battle_publication,
                fow_owner=fog_of_war,
                rng_owner=(ctx.rng_manager if staged_fow is not None else None),
                fow=staged_fow,
                witness_clear=witness_clear,
                _owner_token=self._tactical_observation_owner_token,
            )
            self._active_tactical_observation_plan = outer_plan
            self._validate_tactical_observation_plan(outer_plan)
        except BaseException:
            self._active_tactical_observation_plan = None
            if staged_fow is not None:
                self._abort_staged_fow_observation(ctx, staged_fow)
            if witness_clear is not None and fog_of_war is not None:
                try:
                    fog_of_war.abort_witness_clear(witness_clear)
                except BaseException:
                    pass
            raise

        self._commit_prevalidated_tactical_observation(outer_plan)
        return canonical_battles

    def _update_interval_fog_of_war(
        self,
        ctx: Any,
        *,
        dt: float,
        engine_tick: int,
        logical_time_s: float,
        cal_flat: Mapping[str, Any],
        lod_plan: _LODClassificationPlan,
        concealment_scores: Mapping[str, float],
    ) -> _StagedFOWObservation:
        """Prepare every FOW owner while leaving committed state untouched."""
        fog_of_war = ctx.fog_of_war
        visibility_m = self._targeting_visibility_bound(
            ctx,
            calibration=cal_flat,
        )

        latitude = float(getattr(ctx.config, "latitude", 0.0))
        longitude = float(getattr(ctx.config, "longitude", 0.0))
        illumination_lux = 100.0
        thermal_contrast = float(cal_flat.get("thermal_contrast", 1.0))
        time_of_day = getattr(ctx, "time_of_day_engine", None)
        if time_of_day is not None:
            illumination_lux = float(
                time_of_day.illumination_at(
                    latitude,
                    longitude,
                ).ambient_lux,
            )
            if cal_flat.get("enable_thermal_crossover", False):
                thermal_contrast *= float(
                    time_of_day.thermal_environment(
                        latitude,
                        longitude,
                    ).thermal_contrast,
                )

        ambient_noise_db = 70.0
        acoustics = getattr(ctx, "underwater_acoustics_engine", None)
        if acoustics is not None:
            ambient_noise_db = float(
                acoustics.conditions.ambient_noise_level,
            )

        atmospheric_attenuation = 0.01
        conditions = getattr(ctx, "conditions_facade", None)
        if cal_flat.get("enable_em_propagation", False):
            if conditions is None:
                raise RuntimeError(
                    "EM propagation is enabled without a ConditionsEngine",
                )
            raw_attenuation = conditions.electromagnetic().atmospheric_attenuation_db_per_km
            if (
                isinstance(raw_attenuation, bool)
                or not isinstance(raw_attenuation, (int, float))
                or not math.isfinite(float(raw_attenuation))
                or float(raw_attenuation) < 0.0
            ):
                raise RuntimeError(
                    "ConditionsEngine returned invalid EM attenuation",
                )
            atmospheric_attenuation = float(raw_attenuation)

        side_inputs: dict[
            str,
            tuple[list[dict[str, Any]], list[dict[str, Any]]],
        ] = {}
        side_lod_tiers: dict[
            str,
            dict[TacticalObserverIdentity, FogOfWarLodTier],
        ] = {}
        cadence_roster: list[TacticalCadenceAttachment] = []
        sensor_attachments = getattr(ctx, "unit_sensor_attachments", {})
        scan_scheduling = bool(
            cal_flat.get("enable_scan_scheduling", False),
        )
        lod_enabled = bool(cal_flat.get("enable_lod", False))
        nearby_period = int(cal_flat.get("lod_nearby_interval", 5))
        distant_period = int(cal_flat.get("lod_distant_interval", 20))
        staged_signatures = dict(self._signature_cache)
        reporting_sides = tuple(
            sorted(
                ctx.units_by_side,
                key=lambda value: value.encode("utf-8"),
            )
        )
        observer_unit_ids: set[str] = set()
        for side in reporting_sides:
            side_units = ctx.units_by_side[side]
            own_data: list[dict[str, Any]] = []
            tier_map: dict[
                TacticalObserverIdentity,
                FogOfWarLodTier,
            ] = {}
            for unit in sorted(
                side_units,
                key=lambda item: item.entity_id.encode("utf-8"),
            ):
                if unit.status is not UnitStatus.ACTIVE:
                    continue
                unit_id = unit.entity_id
                if unit_id in observer_unit_ids:
                    raise ValueError(
                        "Fog-of-war observer IDs must be globally unique",
                    )
                observer_unit_ids.add(unit_id)
                identity = TacticalObserverIdentity(
                    reporting_side=side,
                    observer_unit_id=unit_id,
                )
                if lod_enabled:
                    if unit_id not in lod_plan.lod_tiers:
                        raise ValueError(
                            "LOD plan does not cover an active FOW observer",
                        )
                    tier = UnitLodTier(lod_plan.lod_tiers[unit_id])
                else:
                    tier = UnitLodTier.ACTIVE
                fow_tier = FogOfWarLodTier[tier.name]
                tier_map[identity] = fow_tier
                attachments = sensor_attachments.get(unit_id, ())
                for attachment in attachments:
                    if type(attachment) is not SensorAttachment:
                        raise TypeError(
                            "Production FOW requires typed SensorAttachment loadouts",
                        )
                    native_period = attachment.sensor.definition.scan_interval_ticks if scan_scheduling else 1
                    lod_period = (
                        1
                        if not lod_enabled or tier is UnitLodTier.ACTIVE
                        else nearby_period
                        if tier is UnitLodTier.NEARBY
                        else distant_period
                    )
                    cadence_roster.append(
                        TacticalCadenceAttachment(
                            identity=TacticalAttachmentIdentity(
                                reporting_side=side,
                                observer_unit_id=unit_id,
                                source_equipment_index=(attachment.source_equipment_index),
                                sensor_id=attachment.sensor.sensor_id,
                                modeled_role=attachment.modeled_role.value,
                            ),
                            native_period=native_period,
                            lod_period=lod_period,
                            operational=attachment.sensor.operational,
                        )
                    )
                own_data.append(
                    {
                        "unit_id": unit.entity_id,
                        "position": unit.position,
                        "sensors": ctx.unit_sensors.get(unit.entity_id, ()),
                        "sensor_attachments": attachments,
                        "observer_height": 1.8,
                        "observer_heading_deg": (math.degrees(unit.heading) % 360.0),
                    }
                )
            enemy_data: list[dict[str, Any]] = []
            for other_side in reporting_sides:
                if other_side == side:
                    continue
                for enemy in sorted(
                    ctx.units_by_side[other_side],
                    key=lambda item: item.entity_id.encode("utf-8"),
                ):
                    if enemy.status is not UnitStatus.ACTIVE:
                        continue
                    unit_type = getattr(enemy, "unit_type", "")
                    if unit_type not in staged_signatures:
                        staged_signatures[unit_type] = _get_unit_signature(
                            ctx,
                            enemy,
                            failure_handler=self._suppress_runtime_failure,
                        )
                    posture = getattr(enemy, "posture", 0)
                    enemy_data.append(
                        {
                            "unit_id": enemy.entity_id,
                            "position": enemy.position,
                            "signature": staged_signatures[unit_type],
                            "unit": enemy,
                            "target_height": 0.0,
                            "concealment": concealment_scores.get(
                                enemy.entity_id,
                                0.0,
                            ),
                            "posture": int(posture) if posture is not None else 0,
                        }
                    )
            side_inputs[side] = (own_data, enemy_data)
            side_lod_tiers[side] = tier_map

        common_kwargs = {
            "dt": dt,
            "current_time": logical_time_s,
            "detection_culling": bool(
                cal_flat.get("enable_detection_culling", True),
            ),
            "soa_selection": bool(cal_flat.get("enable_soa", False)),
            "current_tick": engine_tick,
            "visibility_m": visibility_m,
            "illumination_lux": illumination_lux,
            "thermal_contrast": thermal_contrast,
            "ambient_noise_db": ambient_noise_db,
            "atmospheric_atten_db_per_km": atmospheric_attenuation,
        }
        cadence_plan = None
        indexed_allocation = None
        fow_transaction = None
        try:
            cadence_plan = fog_of_war.cadence.stage_interval(cadence_roster)
            indexed_allocation = ctx.rng_manager.begin_fow_detection_interval(
                engine_tick,
                reporting_sides,
            )
            side_handles = {side: indexed_allocation.acquire_side(side) for side in reporting_sides}
            fow_transaction = fog_of_war.begin_update_transaction(
                reporting_sides,
            )

            side_plans: dict[str, Any] = {}

            def stage_side(side: str) -> Any:
                own_data, enemy_data = side_inputs[side]
                return fog_of_war.update_with_receipt(
                    side=side,
                    own_units=own_data,
                    enemy_units=enemy_data,
                    transaction=fow_transaction,
                    cadence_plan=cadence_plan,
                    indexed_rng=side_handles[side],
                    lod_tiers=side_lod_tiers[side],
                    **common_kwargs,
                )

            if cal_flat.get("enable_parallel_detection", False) and len(reporting_sides) >= 2:
                errors: dict[str, BaseException] = {}
                with ThreadPoolExecutor(
                    max_workers=min(len(reporting_sides), 4),
                ) as pool:
                    futures = {side: pool.submit(stage_side, side) for side in reporting_sides}
                    # Await every submitted task even when one side fails, then
                    # surface the canonical first-side failure.
                    for side in reporting_sides:
                        try:
                            side_plans[side] = futures[side].result()
                        except BaseException as exc:
                            errors[side] = exc
                if errors:
                    raise errors[next(side for side in reporting_sides if side in errors)]
            else:
                for side in reporting_sides:
                    side_plans[side] = stage_side(side)

            publication = fog_of_war.prevalidate_update_transaction(
                fow_transaction,
                tuple(side_plans[side] for side in reporting_sides),
            )
            outcomes = publication.outcomes
            witnesses = tuple(witness for outcome in outcomes for witness in outcome.witnesses)
            promoted_observers = self._lod_witness_promotions(
                ctx,
                witnesses=witnesses,
                lod_tiers=lod_plan.lod_tiers,
            )
            promoted_unit_ids = self._validate_lod_publication(
                lod_plan,
                witness_promoted_unit_ids={observer.observer_unit_id for observer in promoted_observers},
            )
            cadence_plan = fog_of_war.cadence.stage_witness_promotions(
                cadence_plan,
                promoted_observers,
            )
            fog_of_war.cadence.validate_interval_plan(cadence_plan)

            expected_entries = 0
            for expected_side, outcome in zip(
                reporting_sides,
                outcomes,
                strict=True,
            ):
                receipt = outcome.receipt
                if receipt.reporting_side != expected_side or receipt.engine_tick != engine_tick:
                    raise RuntimeError(
                        "Staged FOW receipt owner/tick topology disagrees with the production interval",
                    )
                expected_entries += receipt.indexed_rng.transcript_entries
                self.stage_fow_cycle_receipt(receipt)
            self._stage_performance_delta(
                PerformanceReceiptDelta(lod=lod_plan.receipt),
            )

            indexed_commit = ctx.rng_manager.prepare_fow_detection_interval_commit(
                indexed_allocation,
            )
            cadence_commit = fog_of_war.cadence.prepare_interval_commit(
                cadence_plan,
            )
            fow_commit = fog_of_war.prepare_update_commit(publication)
            outcomes = fow_commit.outcomes
            indexed_record = indexed_commit.record
            if (
                indexed_record.engine_tick != engine_tick
                or indexed_record.reporting_sides != reporting_sides
                or len(indexed_record.entries) != expected_entries
            ):
                raise RuntimeError(
                    "Prepared indexed FOW record disagrees with staged side receipts",
                )
            ctx.rng_manager.validate_prepared_fow_detection_interval_commit(
                indexed_commit,
            )
            fog_of_war.cadence.validate_prepared_interval_commit(
                cadence_commit,
            )
            fog_of_war.validate_prepared_update_commit(fow_commit)
            return _StagedFOWObservation(
                reporting_sides=reporting_sides,
                indexed_allocation=indexed_allocation,
                indexed_commit=indexed_commit,
                cadence_plan=cadence_plan,
                cadence_commit=cadence_commit,
                transaction=fow_transaction,
                fow_commit=fow_commit,
                outcomes=outcomes,
                signature_cache=staged_signatures,
                observer_unit_ids=frozenset(observer_unit_ids),
                witness_promoted_unit_ids=promoted_unit_ids,
                expected_indexed_entries=expected_entries,
            )
        except BaseException:
            # Incomplete evidence is intentionally fail-closed.  Cleanup is
            # best-effort so the original production failure remains visible.
            if fow_transaction is not None:
                try:
                    fog_of_war.abort_update_transaction(fow_transaction)
                except BaseException:
                    pass
            if cadence_plan is not None:
                try:
                    fog_of_war.cadence.abort_interval(cadence_plan)
                except BaseException:
                    pass
            if indexed_allocation is not None:
                try:
                    ctx.rng_manager.abort_fow_detection_interval(
                        indexed_allocation,
                    )
                except BaseException:
                    pass
            raise

    def _lod_witness_promotions(
        self,
        ctx: Any,
        *,
        witnesses: Iterable[ObserverDetectionWitness],
        lod_tiers: Mapping[str, int],
    ) -> frozenset[TacticalObserverIdentity]:
        """Return exact next-interval promotions from staged FOW witnesses."""
        if not _resolve_cal_flat(ctx).get("enable_lod", False):
            return frozenset()
        promoted: set[TacticalObserverIdentity] = set()
        unit_index = {unit.entity_id: unit for units in ctx.units_by_side.values() for unit in units}
        unit_sides = {unit.entity_id: side for side, units in ctx.units_by_side.items() for unit in units}
        for witness in witnesses:
            observer_id = witness.observer_unit_id
            if not witness.detected or lod_tiers.get(observer_id, UnitLodTier.ACTIVE) == UnitLodTier.ACTIVE:
                continue
            observer = unit_index.get(observer_id)
            target = unit_index.get(witness.target_id)
            if observer is None or target is None:
                continue
            if unit_sides.get(observer_id) != witness.side:
                raise RuntimeError(
                    "Detection witness reporting side disagrees with the production observer roster",
                )
            max_weapon_range = _max_weapon_range_for_domain(
                ctx.unit_weapons.get(observer_id, ()),
                target.domain,
            )
            if max_weapon_range > 0.0 and float(witness.range_m) <= max_weapon_range * 2.0:
                promoted.add(
                    TacticalObserverIdentity(
                        reporting_side=witness.side,
                        observer_unit_id=observer_id,
                    )
                )
        return frozenset(promoted)

    @staticmethod
    def _targeting_distance(shooter: Unit, target: Unit) -> float:
        """Return exact pre-movement ENU slant distance."""
        return math.sqrt(
            (target.position.easting - shooter.position.easting) ** 2
            + (target.position.northing - shooter.position.northing) ** 2
            + (target.position.altitude - shooter.position.altitude) ** 2
        )

    @staticmethod
    def _targeting_los_visible(
        ctx: Any,
        shooter: Unit,
        target: Unit,
        *,
        required: bool,
        evidence_cache: _TargetingIntervalEvidenceCache | None = None,
    ) -> bool:
        """Return the production LOS answer when the modality requires it."""
        if not required:
            return True
        los_engine = getattr(ctx, "los_engine", None)
        if los_engine is None:
            return True

        cache_key: LOSCacheKey | None = None
        if evidence_cache is not None and isinstance(los_engine, LOSEngine):
            observer_cell = evidence_cache.los_cell_by_unit.get(
                shooter.entity_id,
            )
            if observer_cell is None:
                observer_cell = los_engine.cache_cell(shooter.position)
                evidence_cache.los_cell_by_unit[shooter.entity_id] = observer_cell
            target_cell = evidence_cache.los_cell_by_unit.get(
                target.entity_id,
            )
            if target_cell is None:
                target_cell = los_engine.cache_cell(target.position)
                evidence_cache.los_cell_by_unit[target.entity_id] = target_cell
            cache_key = los_engine.cache_key(
                observer_cell,
                target_cell,
                1.8,
                0.0,
            )
            cached = evidence_cache.los_by_identity.get(cache_key)
            if cached is not None:
                return cached

        result = los_engine.check_los(
            shooter.position,
            target.position,
            1.8,
            0.0,
        )
        visible = bool(result.visible)
        if evidence_cache is not None and cache_key is not None:
            evidence_cache.los_by_identity[cache_key] = visible
        return visible

    @staticmethod
    def _targeting_sensor_in_fov(
        shooter: Unit,
        target: Unit,
        attachment: SensorAttachment,
    ) -> bool:
        """Return whether an attachment's authored scan sector covers target."""
        definition = attachment.sensor.definition
        fov_deg = float(definition.fov_deg)
        if fov_deg >= 360.0:
            return True
        dx = target.position.easting - shooter.position.easting
        dy = target.position.northing - shooter.position.northing
        target_bearing = math.degrees(math.atan2(dx, dy)) % 360.0
        sensor_boresight = (
            math.degrees(float(getattr(shooter, "heading", 0.0) or 0.0)) + float(definition.boresight_offset_deg)
        ) % 360.0
        difference = abs(target_bearing - sensor_boresight)
        difference = min(difference, 360.0 - difference)
        return difference <= fov_deg / 2.0

    def _targeting_visibility_bound(
        self,
        ctx: Any,
        *,
        calibration: Mapping[str, object] | None = None,
    ) -> float:
        """Resolve the shared production visibility from exact live owners."""
        weather = getattr(ctx, "weather_engine", None)
        return targeting_visibility_bound_m(
            calibration=(_resolve_cal_flat(ctx) if calibration is None else calibration),
            default_visibility_m=self._config.default_visibility_m,
            weather_visibility_m=(weather.current.visibility if weather is not None else None),
        )

    def _targeting_environment(
        self,
        ctx: Any,
        shooter: Unit,
        target: Unit,
        *,
        evidence_cache: _TargetingIntervalEvidenceCache | None = None,
    ) -> _TargetingEnvironment:
        """Return current visual/thermal and obscurant targeting modifiers."""
        del shooter  # Environment varies by interval and target, not observer.
        if evidence_cache is not None:
            cached = evidence_cache.environment_by_target.get(
                target.entity_id,
            )
            if cached is not None:
                return cached
        cal_flat = _resolve_cal_flat(ctx)
        visibility_m = self._targeting_visibility_bound(
            ctx,
            calibration=cal_flat,
        )

        night_visual = 1.0
        nvg_visual = 1.0
        thermal_modifier = 1.0
        time_of_day = getattr(ctx, "time_of_day_engine", None)
        if time_of_day is not None:
            latitude = float(getattr(ctx.config, "latitude", 0.0))
            longitude = float(getattr(ctx.config, "longitude", 0.0))
            illumination = time_of_day.illumination_at(latitude, longitude)
            night_visual, night_thermal = _compute_night_modifiers(
                illumination,
                float(cal_flat.get("night_thermal_floor", 0.8)),
            )
            nvg_visual = night_visual
            if cal_flat.get("enable_nvg_detection", False) and night_visual < 1.0:
                nvg_effectiveness = float(
                    time_of_day.nvg_effectiveness(latitude, longitude),
                )
                nvg_visual += nvg_effectiveness * 0.5 * (1.0 - night_visual)
            if cal_flat.get("enable_thermal_crossover", False):
                thermal_modifier = saturating_range_product(
                    max(
                        0.0,
                        float(
                            time_of_day.thermal_environment(
                                latitude,
                                longitude,
                            ).thermal_contrast,
                        ),
                    ),
                    max(0.0, float(cal_flat.get("thermal_contrast", 1.0))),
                )
                if thermal_modifier < 0.5 and float(getattr(target, "speed", 0.0)) > 1.0:
                    thermal_modifier = max(thermal_modifier, 0.5)
            else:
                thermal_modifier = night_thermal

        opacity_visual = 0.0
        opacity_thermal = 0.0
        opacity_radar = 0.0
        obscurants = getattr(ctx, "obscurants_engine", None)
        if obscurants is not None and cal_flat.get("enable_obscurants", False):
            opacity = obscurants.opacity_at(target.position)
            opacity_visual = float(opacity.visual)
            opacity_thermal = float(opacity.thermal)
            opacity_radar = float(opacity.radar)
        environment = (
            visibility_m,
            night_visual,
            nvg_visual,
            thermal_modifier,
            opacity_visual,
            opacity_thermal,
            opacity_radar,
        )
        if evidence_cache is not None:
            evidence_cache.environment_by_target[target.entity_id] = environment
        return environment

    @staticmethod
    def _targeting_observer_range_modifier(
        ctx: Any,
        shooter: Unit,
        *,
        evidence_cache: _TargetingIntervalEvidenceCache | None = None,
    ) -> float:
        """Return the shared observer-side MOPP and altitude range factor."""
        if evidence_cache is not None and shooter.entity_id in evidence_cache.observer_range_modifier_by_observer:
            return evidence_cache.observer_range_modifier_by_observer[shooter.entity_id]
        cal_flat = _resolve_cal_flat(ctx)
        modifier = 1.0
        altitude_factor = targeting_altitude_range_factor(
            calibration=cal_flat,
            observer_altitude_m=float(shooter.position.altitude or 0.0),
            observer_acclimatized=getattr(
                shooter,
                "acclimatized",
                False,
            ),
        )
        cbrn = getattr(ctx, "cbrn_engine", None)
        mopp_level = 0
        if cbrn is not None:
            _state, detection_modifier, _fatigue = cbrn.get_mopp_effects(
                shooter.entity_id,
            )
            mopp_level = cbrn.get_mopp_level(shooter.entity_id)
            if (
                isinstance(detection_modifier, bool)
                or not isinstance(detection_modifier, (int, float))
                or not math.isfinite(float(detection_modifier))
                or float(detection_modifier) < 0.0
                or float(detection_modifier) > 1.0
            ):
                raise RuntimeError(
                    "CBRNEngine returned an invalid detection modifier",
                )
            if isinstance(mopp_level, bool) or not isinstance(mopp_level, int) or not 0 <= mopp_level <= 4:
                raise RuntimeError("CBRNEngine returned an invalid MOPP level")
            modifier = saturating_range_product(
                modifier,
                float(detection_modifier),
            )
        if cal_flat.get("enable_human_factors", False):
            if mopp_level > 0:
                full_reduction = float(
                    cal_flat.get("mopp_fov_reduction_4", 0.7),
                )
                level_fraction = min(4, mopp_level) / 4.0
                modifier = saturating_range_product(
                    modifier,
                    max(
                        0.0,
                        1.0 - level_fraction * (1.0 - full_reduction),
                    ),
                )
        modifier = saturating_range_product(modifier, altitude_factor)
        if evidence_cache is not None:
            evidence_cache.observer_range_modifier_by_observer[shooter.entity_id] = modifier
        return modifier

    @staticmethod
    def _targeting_sensor_range_policy(
        ctx: Any,
        shooter: Unit,
        *,
        evidence_cache: _TargetingIntervalEvidenceCache | None = None,
    ) -> SensorEnvironmentRangePolicy:
        """Build one immutable range policy per observer and interval."""
        if evidence_cache is not None:
            cached = evidence_cache.range_policy_by_observer.get(
                shooter.entity_id,
            )
            if cached is not None:
                return cached
        try:
            policy = sensor_environment_range_policy(
                calibration=_resolve_cal_flat(ctx),
                observer_domain=shooter.domain,
                observer_altitude_m=float(shooter.position.altitude or 0.0),
                observer_acclimatized=getattr(
                    shooter,
                    "acclimatized",
                    False,
                ),
            )
        except ValueError as exc:
            raise RuntimeError(
                "Targeting observer has invalid environmental range evidence",
            ) from exc
        if evidence_cache is not None:
            evidence_cache.range_policy_by_observer[shooter.entity_id] = policy
        return policy

    def _targeting_sensor_range(
        self,
        ctx: Any,
        shooter: Unit,
        target: Unit,
        attachment: SensorAttachment,
        *,
        environment: _TargetingEnvironment,
        range_policy: SensorEnvironmentRangePolicy,
        evidence_cache: _TargetingIntervalEvidenceCache | None = None,
    ) -> float:
        """Resolve one exact live attachment's current deterministic reach."""
        sensor = attachment.sensor
        if (
            not sensor.operational
            or shooter.domain
            not in allowed_shooter_domains_for_sensor_role(
                attachment.modeled_role,
            )
            or not sensor.supports_target_domain(target.domain)
            or target.domain not in required_domains_for_sensor_role(attachment.modeled_role)
            or not self._targeting_sensor_in_fov(shooter, target, attachment)
            or not self._targeting_los_visible(
                ctx,
                shooter,
                target,
                required=bool(sensor.definition.requires_los),
                evidence_cache=evidence_cache,
            )
        ):
            return 0.0

        (
            visibility_m,
            night_visual,
            nvg_visual,
            thermal_modifier,
            opacity_visual,
            opacity_thermal,
            opacity_radar,
        ) = environment
        effective_concealment = self._concealment_scores.get(
            target.entity_id,
            0.0,
        )
        visual_concealment = max(0.0, 1.0 - effective_concealment)
        nonvisual_concealment = max(
            0.0,
            1.0 - effective_concealment * 0.3,
        )
        sensor_range = float(sensor.effective_range)
        sensor_type = sensor.sensor_type
        if sensor_type is SensorType.ESM:
            # The deterministic non-FOW path has no target emission state.
            # FOW may still provide an ESM witness through DetectionEngine.
            return 0.0
        if sensor_type is SensorType.VISUAL:
            sensor_range = saturating_range_product(
                min(sensor_range, visibility_m),
                visual_concealment,
                max(0.0, night_visual),
                max(0.0, 1.0 - opacity_visual),
            )
        elif sensor_type is SensorType.NVG:
            sensor_range = saturating_range_product(
                min(sensor_range, visibility_m),
                visual_concealment,
                max(0.0, nvg_visual),
                max(0.0, 1.0 - opacity_visual),
            )
        elif sensor_type is SensorType.THERMAL:
            sensor_range = saturating_range_product(
                sensor_range,
                nonvisual_concealment,
                max(0.0, thermal_modifier),
                max(0.0, 1.0 - opacity_thermal),
            )
        elif sensor_type is SensorType.RADAR:
            sensor_range = saturating_range_product(
                sensor_range,
                nonvisual_concealment,
                max(0.0, 1.0 - opacity_radar),
            )
            cal_flat = _resolve_cal_flat(ctx)
            weather = getattr(ctx, "weather_engine", None)
            if weather is not None:
                rain = float(weather.current.precipitation_rate)
                if rain > 0.0:
                    rain_factor = saturating_range_power(
                        _compute_rain_detection_factor(
                            rain,
                            sensor_range / 1_000.0,
                        ),
                        float(cal_flat.get("rain_attenuation_factor", 1.0)),
                    )
                    sensor_range = saturating_range_product(
                        sensor_range,
                        rain_factor,
                    )
            conditions = getattr(ctx, "conditions_engine", None)
            if (
                conditions is not None
                and cal_flat.get("enable_em_propagation", False)
                and hasattr(conditions, "radar_horizon")
            ):
                antenna_height = (
                    max(10.0, shooter.position.altitude)
                    if shooter.domain is Domain.AERIAL
                    else 30.0
                    if shooter.domain in (Domain.NAVAL, Domain.SUBMARINE)
                    else 10.0
                )
                horizon_m = conditions.radar_horizon(antenna_height)
                horizon_m += conditions.radar_horizon(
                    max(0.0, target.position.altitude),
                )
                if self._targeting_distance(shooter, target) > horizon_m and target.position.altitude < 500.0:
                    return 0.0
                from stochastic_warfare.environment.electromagnetic import (
                    FrequencyBand,
                )

                propagation = conditions.propagation(
                    FrequencyBand.SHF,
                    self._targeting_distance(shooter, target) / 1_000.0,
                )
                if propagation.ducting_possible and shooter.domain in (Domain.NAVAL, Domain.SUBMARINE):
                    sensor_range = saturating_range_product(
                        sensor_range,
                        min(
                            2.0,
                            conditions.effective_earth_radius_factor() / (4.0 / 3.0),
                        ),
                    )
            conditions_facade = getattr(ctx, "conditions_facade", None)
            if conditions_facade is not None and cal_flat.get("enable_air_combat_environment", False):
                icing_risk = float(
                    conditions_facade.air(
                        shooter.position,
                        float(shooter.position.altitude or 0.0),
                        float(getattr(ctx.config, "latitude", 0.0)),
                        float(getattr(ctx.config, "longitude", 0.0)),
                    ).icing_risk
                )
                if icing_risk > 0.5:
                    icing_penalty_db = float(
                        cal_flat.get("icing_radar_penalty_db", 3.0),
                    )
                    sensor_range = saturating_range_product(
                        sensor_range,
                        saturating_range_power(
                            10.0,
                            -icing_penalty_db / 40.0,
                        ),
                    )
        elif sensor_type in {
            SensorType.ACTIVE_SONAR,
            SensorType.PASSIVE_SONAR,
            SensorType.PASSIVE_ACOUSTIC,
        }:
            cal_flat = _resolve_cal_flat(ctx)
            acoustics = getattr(ctx, "underwater_acoustics_engine", None)
            if acoustics is not None and cal_flat.get(
                "enable_acoustic_layers",
                False,
            ):
                conditions = acoustics.conditions
                observer_depth = float(getattr(shooter, "depth", 0.0))
                target_depth = float(getattr(target, "depth", 0.0))
                if (
                    conditions.thermocline_depth
                    and target_depth > conditions.thermocline_depth
                    and observer_depth <= conditions.thermocline_depth
                ):
                    sensor_range = saturating_range_product(sensor_range, 0.1)
                if conditions.surface_duct_depth:
                    if observer_depth < conditions.surface_duct_depth and target_depth < conditions.surface_duct_depth:
                        sensor_range = saturating_range_product(
                            sensor_range,
                            3.0,
                        )
                    elif (
                        observer_depth < conditions.surface_duct_depth and target_depth > conditions.surface_duct_depth
                    ):
                        sensor_range = saturating_range_product(
                            sensor_range,
                            0.06,
                        )
                distance_m = self._targeting_distance(shooter, target)
                convergence_zones = acoustics.convergence_zone_ranges(
                    observer_depth,
                )
                in_zone = any(abs(distance_m - zone_range) < 5_000.0 for zone_range in convergence_zones)
                if convergence_zones and distance_m > 30_000.0 and not in_zone:
                    sensor_range = saturating_range_product(sensor_range, 0.05)
                elif in_zone:
                    sensor_range = saturating_range_product(sensor_range, 2.0)

        posture = getattr(target, "naval_posture", None)
        if posture is not None:
            sensor_range = saturating_range_product(
                sensor_range,
                _NAVAL_POSTURE_DETECT_MULT.get(int(posture), 1.0),
            )

        sensor_range = saturating_range_product(
            sensor_range,
            self._targeting_observer_range_modifier(
                ctx,
                shooter,
                evidence_cache=evidence_cache,
            ),
        )
        if sensor_type in {SensorType.VISUAL, SensorType.NVG}:
            sensor_range = min(sensor_range, visibility_m)
        if not math.isfinite(sensor_range):
            raise RuntimeError(
                "Targeting sensor resolver produced a non-finite range",
            )
        return _validated_targeting_sensor_range_m(
            sensor_type=sensor_type,
            condition_adjusted_range_m=float(sensor.effective_range),
            resolved_range_m=max(0.0, sensor_range),
            policy=range_policy,
        )

    def _targeting_non_fow_contact_upper_bound_m(
        self,
        ctx: Any,
        shooter: Unit,
        target: Unit,
        *,
        visibility_bound_m: float,
        range_policy: SensorEnvironmentRangePolicy,
    ) -> float:
        """Return a conservative pre-LOS bound for a local observation.

        Every environmental, concealment, obscurant, condition, and LOS term
        in the exact resolver can only retain or reduce this bound.  It is
        therefore safe to reject a farther non-FOW target before querying
        target-local obscurants or terrain LOS.
        """
        upper_bound_m = visibility_bound_m if target.domain is not Domain.SUBMARINE else 0.0
        for attachment in getattr(
            ctx,
            "unit_sensor_attachments",
            {},
        ).get(shooter.entity_id, ()):
            sensor = attachment.sensor
            if (
                not sensor.operational
                or sensor.sensor_type is SensorType.ESM
                or shooter.domain
                not in allowed_shooter_domains_for_sensor_role(
                    attachment.modeled_role,
                )
                or not sensor.supports_target_domain(target.domain)
                or target.domain
                not in required_domains_for_sensor_role(
                    attachment.modeled_role,
                )
                or not self._targeting_sensor_in_fov(
                    shooter,
                    target,
                    attachment,
                )
            ):
                continue
            try:
                sensor_bound_m = sensor_environment_range_upper_bound_m(
                    policy=range_policy,
                    sensor_type=sensor.sensor_type,
                    condition_adjusted_range_m=float(
                        sensor.effective_range,
                    ),
                )
            except ValueError as exc:
                raise RuntimeError(
                    "Targeting sensor has invalid condition-adjusted range evidence",
                ) from exc
            upper_bound_m = max(upper_bound_m, sensor_bound_m)
        return upper_bound_m

    def _targeting_direct_visual_range(
        self,
        ctx: Any,
        shooter: Unit,
        target: Unit,
        *,
        environment: _TargetingEnvironment,
        evidence_cache: _TargetingIntervalEvidenceCache | None = None,
    ) -> float:
        """Return current unaided local visual reach without inventing a sensor."""
        if target.domain is Domain.SUBMARINE or not self._targeting_los_visible(
            ctx,
            shooter,
            target,
            required=True,
            evidence_cache=evidence_cache,
        ):
            return 0.0
        visibility_m, night_visual, _, _, opacity_visual, _, _ = environment
        observation = None if evidence_cache is None else evidence_cache.observation
        concealment_scores = self._concealment_scores if observation is None else observation.concealment_scores
        concealment = concealment_scores.get(target.entity_id, 0.0)
        reach = saturating_range_product(
            visibility_m,
            max(0.0, 1.0 - concealment),
            max(0.0, night_visual),
            max(0.0, 1.0 - opacity_visual),
        )
        posture = getattr(target, "naval_posture", None)
        if posture is not None:
            reach = saturating_range_product(
                reach,
                _NAVAL_POSTURE_DETECT_MULT.get(int(posture), 1.0),
            )
        reach = saturating_range_product(
            reach,
            self._targeting_observer_range_modifier(
                ctx,
                shooter,
                evidence_cache=evidence_cache,
            ),
        )
        if not math.isfinite(reach):
            raise RuntimeError(
                "Direct-visual targeting produced a non-finite range",
            )
        return max(0.0, min(reach, visibility_m))

    def _targeting_contacts(
        self,
        ctx: Any,
        shooter: Unit,
        target: Unit,
        *,
        distance_m: float,
        visibility_bound_m: float,
        direct_visual_range_m: float,
        sensor_ranges: Mapping[int, float],
        evidence_cache: _TargetingIntervalEvidenceCache | None = None,
    ) -> tuple[_TargetingContact, ...]:
        """Return every exact current local contact in canonical order."""
        cal_flat = _resolve_cal_flat(ctx)
        logical_time_s = float(ctx.clock.elapsed.total_seconds())
        attachments = getattr(ctx, "unit_sensor_attachments", {}).get(
            shooter.entity_id,
            (),
        )
        if not cal_flat.get("enable_fog_of_war", False):
            candidates: list[_TargetingContact] = []
            if direct_visual_range_m > 0.0 and distance_m <= direct_visual_range_m:
                candidates.append(
                    _TargetingContact(
                        source=ContactSource.NON_FOW_LOCAL_OBSERVATION,
                        range_m=direct_visual_range_m,
                        sensor_attachment=None,
                    )
                )
            for attachment in attachments:
                reach = sensor_ranges.get(
                    attachment.source_equipment_index,
                    0.0,
                )
                if reach > 0.0 and distance_m <= reach:
                    candidates.append(
                        _TargetingContact(
                            source=ContactSource.NON_FOW_LOCAL_OBSERVATION,
                            range_m=reach,
                            sensor_attachment=attachment,
                        )
                    )
            if not candidates:
                return ()
            return tuple(
                sorted(
                    candidates,
                    key=lambda candidate: (
                        -candidate.range_m,
                        candidate.sensor_attachment is None,
                        (
                            candidate.sensor_attachment.source_equipment_index
                            if candidate.sensor_attachment is not None
                            else -1
                        ),
                        (candidate.sensor_attachment.sensor_id if candidate.sensor_attachment is not None else ""),
                    ),
                )
            )

        observation = None if evidence_cache is None else evidence_cache.observation
        fog_of_war = getattr(ctx, "fog_of_war", None)
        if observation is not None:
            world_view = observation.world_views.get(shooter.side)
        elif fog_of_war is not None:
            world_view = fog_of_war.get_world_view(shooter.side)
        else:
            world_view = None
        if world_view is None:
            return ()
        contact_record = world_view.contacts.get(target.entity_id)
        if (
            contact_record is None
            or world_view.last_update_time != logical_time_s
            or contact_record.contact_info.level < ContactLevel.DETECTED
            or contact_record.track.status in {TrackStatus.STALE, TrackStatus.LOST}
        ):
            return ()
        attachment_by_identity = {
            (attachment.source_equipment_index, attachment.sensor_id): attachment for attachment in attachments
        }
        witnesses = (
            observation.witnesses.get(shooter.side, ())
            if observation is not None
            else fog_of_war.get_current_detection_witnesses(shooter.side)
        )
        candidates = []
        for witness in witnesses:
            if (
                witness.observer_unit_id != shooter.entity_id
                or witness.target_id != target.entity_id
                or witness.logical_time_s != logical_time_s
                or witness.side != shooter.side
                or contact_record.last_sensor_contact_time != logical_time_s
            ):
                continue
            attachment = attachment_by_identity.get(
                (
                    witness.source_equipment_index,
                    witness.sensor_id,
                )
            )
            if (
                attachment is None
                or attachment.modeled_role.value != witness.modeled_role
                or not attachment.sensor.operational
                or not attachment.sensor.supports_target_domain(target.domain)
                or not math.isclose(
                    float(witness.range_m),
                    distance_m,
                    rel_tol=1e-9,
                    abs_tol=1e-6,
                )
            ):
                continue
            if attachment.sensor.sensor_type in {SensorType.VISUAL, SensorType.NVG} and distance_m > visibility_bound_m:
                # DetectionEngine owns the stochastic observation draw, but
                # optical targeting authority is still hard-bounded by the
                # exact interval visibility committed with the decision.
                continue
            candidates.append(
                _TargetingContact(
                    source=ContactSource.FOW_OBSERVER_WITNESS,
                    # The witness check above proves the same observer-local
                    # measurement.  Canonicalize the immutable decision to the
                    # production distance so its duplicated contact/sensing
                    # evidence is exact, including a valid co-located 0 m target.
                    range_m=distance_m,
                    sensor_attachment=attachment,
                )
            )
        if candidates:
            return tuple(
                sorted(
                    candidates,
                    key=lambda candidate: (
                        candidate.sensor_attachment.source_equipment_index,
                        candidate.sensor_attachment.sensor_id,
                    ),
                )
            )

        if observation is not None:
            retained_supports = observation.observer_track_supports.get(
                shooter.side,
                (),
            )
            cadence_ordinal = observation.cadence_ordinal
            process_noise_std_mps2 = observation.support_process_noise_std_mps2
            max_position_uncertainty_m = observation.support_max_position_uncertainty_m
        elif fog_of_war is not None:
            retained_supports = fog_of_war.get_observer_track_supports(
                shooter.side,
            )
            committed_ordinal = fog_of_war.cadence.committed_ordinal
            cadence_ordinal = committed_ordinal - 1 if committed_ordinal > 0 else None
            process_noise_std_mps2 = fog_of_war.observer_track_support_process_noise_std_mps2
            max_position_uncertainty_m = fog_of_war.observer_track_support_max_position_uncertainty_m
        else:
            return ()
        if cadence_ordinal is None or process_noise_std_mps2 is None or max_position_uncertainty_m is None:
            return ()

        full_attachment_identity = {
            (
                attachment.source_equipment_index,
                attachment.sensor_id,
                attachment.modeled_role.value,
            ): attachment
            for attachment in attachments
        }
        support_candidates: list[_TargetingContact] = []
        for retained in retained_supports:
            identity = retained.identity
            attachment_identity = identity.attachment_identity
            if (
                attachment_identity.reporting_side != shooter.side
                or attachment_identity.observer_unit_id != shooter.entity_id
                or identity.target_id != target.entity_id
                or retained.fusion_track_id != contact_record.track.track_id
                or retained.observation_time_s >= logical_time_s
                or attachment_identity.sensor_id not in contact_record.reporting_sensors
            ):
                continue
            attachment = full_attachment_identity.get(
                (
                    attachment_identity.source_equipment_index,
                    attachment_identity.sensor_id,
                    attachment_identity.modeled_role,
                )
            )
            if (
                attachment is None
                or not attachment.sensor.operational
                or attachment.sensor.sensor_type is not retained.sensor_type
                or not observer_track_support_role_is_supported(
                    sensor_type=attachment.sensor.sensor_type,
                    modeled_role=attachment.modeled_role,
                )
                or shooter.domain
                not in allowed_shooter_domains_for_sensor_role(
                    attachment.modeled_role,
                )
                or target.domain
                not in required_domains_for_sensor_role(
                    attachment.modeled_role,
                )
                or not attachment.sensor.supports_target_domain(target.domain)
                or not self._targeting_los_visible(
                    ctx,
                    shooter,
                    target,
                    required=bool(attachment.sensor.definition.requires_los),
                    evidence_cache=evidence_cache,
                )
                or not self._targeting_sensor_in_fov(
                    shooter,
                    target,
                    attachment,
                )
            ):
                continue
            reach_m = sensor_ranges.get(
                attachment.source_equipment_index,
                0.0,
            )
            if reach_m <= 0.0 or distance_m > reach_m:
                continue
            try:
                evidence = retained.project(
                    projection_ordinal=cadence_ordinal,
                    projection_time_s=logical_time_s,
                    process_noise_std_mps2=process_noise_std_mps2,
                )
                within_limits = evidence.is_within_limits(
                    observer_easting_m=float(shooter.position.easting),
                    observer_northing_m=float(shooter.position.northing),
                    reach_m=reach_m,
                    max_position_uncertainty_m=(max_position_uncertainty_m),
                )
            except ValueError as exc:
                raise RuntimeError(
                    "FOW owner exposed unusable observer track support",
                ) from exc
            if not within_limits:
                continue
            support_candidates.append(
                _TargetingContact(
                    source=ContactSource.FOW_OBSERVER_TRACK_SUPPORT,
                    range_m=reach_m,
                    sensor_attachment=attachment,
                    observer_track_support=evidence,
                )
            )
        return tuple(
            sorted(
                support_candidates,
                key=lambda candidate: (
                    candidate.sensor_attachment.source_equipment_index,
                    candidate.sensor_attachment.sensor_id,
                ),
            )
        )

    def _targeting_fire_control(
        self,
        ctx: Any,
        shooter: Unit,
        target: Unit,
        weapon: WeaponAttachment,
        contact: _TargetingContact,
        *,
        distance_m: float,
        direct_visual_range_m: float,
        sensor_ranges: Mapping[int, float],
        evidence_cache: _TargetingIntervalEvidenceCache | None = None,
    ) -> tuple[_TargetingFireControl | None, TargetingDisposition]:
        """Resolve exact local fire control and its typed rejection."""
        standoff_class = weapon_standoff_class(weapon.modeled_role)
        fow_enabled = bool(
            _resolve_cal_flat(ctx).get("enable_fog_of_war", False),
        )
        direct_visual_permitted = standoff_class is WeaponStandoffClass.ORGANIC_DIRECT_AIM or weapon.modeled_role in {
            type(weapon.modeled_role).HAND_GRENADE,
            type(weapon.modeled_role).MELEE,
        }
        if fow_enabled:
            contact_sensor = contact.sensor_attachment
            direct_visual_permitted = (
                direct_visual_permitted
                and contact_sensor is not None
                and contact_sensor.modeled_role in _FOW_DIRECT_VISUAL_ROLES
            )
            direct_visual_range_m = min(
                direct_visual_range_m,
                contact.range_m,
            )
        if contact.source is ContactSource.FOW_OBSERVER_TRACK_SUPPORT:
            # Retained support belongs to one exact local fire-control radar.
            # It cannot authorize direct visual or a different live director.
            direct_visual_permitted = False
        candidates: list[_TargetingFireControl] = []
        rejections: list[tuple[int, int, str, TargetingDisposition]] = []
        if direct_visual_permitted and direct_visual_range_m > 0.0 and distance_m <= direct_visual_range_m:
            candidates.append(
                _TargetingFireControl(
                    source=FireControlSource.DIRECT_VISUAL,
                    range_m=direct_visual_range_m,
                    sensor_attachment=None,
                )
            )
        elif direct_visual_permitted:
            direct_los = self._targeting_los_visible(
                ctx,
                shooter,
                target,
                required=True,
                evidence_cache=evidence_cache,
            )
            rejections.append(
                (
                    3 if not direct_los else 6,
                    -1,
                    "",
                    (
                        TargetingDisposition.LINE_OF_SIGHT_BLOCKED
                        if not direct_los
                        else TargetingDisposition.VISIBILITY_LIMITED
                    ),
                )
            )

        globally_compatible = compatible_sensor_roles_for_weapon_role(
            weapon.modeled_role,
        )
        for attachment in getattr(
            ctx,
            "unit_sensor_attachments",
            {},
        ).get(shooter.entity_id, ()):
            if (
                contact.source is ContactSource.FOW_OBSERVER_TRACK_SUPPORT
                and attachment is not contact.sensor_attachment
            ):
                continue
            if (
                sensor_targeting_class(attachment.modeled_role) is not SensorTargetingClass.LOCAL_FIRE_CONTROL
                or attachment.modeled_role not in globally_compatible
                or weapon.source_equipment_index not in attachment.compatible_weapon_source_indexes
            ):
                continue
            rejection_identity = (
                attachment.source_equipment_index,
                attachment.sensor_id,
            )
            if not attachment.sensor.operational:
                rejections.append(
                    (
                        0,
                        *rejection_identity,
                        TargetingDisposition.FIRE_CONTROL_SENSOR_OFFLINE,
                    )
                )
                continue
            if shooter.domain not in allowed_shooter_domains_for_sensor_role(
                attachment.modeled_role,
            ):
                rejections.append(
                    (
                        1,
                        *rejection_identity,
                        TargetingDisposition.FIRE_CONTROL_SHOOTER_DOMAIN_UNSUPPORTED,
                    )
                )
                continue
            if target.domain not in required_domains_for_sensor_role(
                attachment.modeled_role,
            ) or not attachment.sensor.supports_target_domain(
                target.domain,
            ):
                rejections.append(
                    (
                        2,
                        *rejection_identity,
                        TargetingDisposition.FIRE_CONTROL_TARGET_DOMAIN_UNSUPPORTED,
                    )
                )
                continue
            if not self._targeting_los_visible(
                ctx,
                shooter,
                target,
                required=bool(attachment.sensor.definition.requires_los),
                evidence_cache=evidence_cache,
            ):
                rejections.append(
                    (
                        3,
                        *rejection_identity,
                        TargetingDisposition.LINE_OF_SIGHT_BLOCKED,
                    )
                )
                continue
            if not self._targeting_sensor_in_fov(
                shooter,
                target,
                attachment,
            ):
                rejections.append(
                    (
                        4,
                        *rejection_identity,
                        TargetingDisposition.OUTSIDE_SENSOR_FIELD_OF_VIEW,
                    )
                )
                continue
            reach = sensor_ranges.get(
                attachment.source_equipment_index,
                0.0,
            )
            if reach > 0.0 and distance_m <= reach:
                candidates.append(
                    _TargetingFireControl(
                        source=FireControlSource.SENSOR_ATTACHMENT,
                        range_m=reach,
                        sensor_attachment=attachment,
                    )
                )
            else:
                rejections.append(
                    (
                        5,
                        *rejection_identity,
                        TargetingDisposition.FIRE_CONTROL_RANGE_EXCEEDED,
                    )
                )
        if not candidates:
            if rejections:
                return None, min(rejections)[3]
            return None, TargetingDisposition.NO_COMPATIBLE_FIRE_CONTROL
        return min(
            candidates,
            key=lambda candidate: (
                -candidate.range_m,
                candidate.source is FireControlSource.DIRECT_VISUAL,
                (candidate.sensor_attachment.source_equipment_index if candidate.sensor_attachment is not None else -1),
                (candidate.sensor_attachment.sensor_id if candidate.sensor_attachment is not None else ""),
            ),
        ), TargetingDisposition.VALID_ENGAGEMENT_SOLUTION

    def _targeting_ammunition(
        self,
        ctx: Any,
        shooter: Unit,
        attachment: WeaponAttachment,
    ) -> AmmoDefinition | None:
        """Return first currently fireable ammunition under the live gate."""
        excluded_ammo_ids: set[str] = set()
        if _resolve_cal_flat(ctx).get("enable_ammo_gate", False):
            magazine_capacity = int(
                getattr(attachment.weapon.definition, "magazine_capacity", 0),
            )
            if magazine_capacity > 0:
                legacy_key = f"{shooter.entity_id}:{attachment.weapon.definition.weapon_id}"
                for ammunition in attachment.ammunition:
                    ammo_key = f"{legacy_key}:{ammunition.ammo_id}"
                    rounds_fired = self._ammo_expended.get(
                        ammo_key,
                        self._ammo_expended.get(legacy_key, 0),
                    )
                    if rounds_fired >= magazine_capacity:
                        excluded_ammo_ids.add(ammunition.ammo_id)
        return attachment.first_fireable_ammunition(
            excluded_ammo_ids=excluded_ammo_ids,
        )

    def _build_targeting_decision(
        self,
        *,
        ctx: Any,
        battle: BattleContext,
        shooter: Unit,
        target: Unit,
        ordinal: int,
        distance_m: float,
        direct_visual_range_m: float,
        contact: _TargetingContact,
        weapon: WeaponAttachment | None,
        ammunition: AmmoDefinition | None,
        fire_control: _TargetingFireControl | None,
        disposition: TargetingDisposition,
        authorized_standoff_m: float = 0.0,
        hold_authorized: bool = False,
        engagement_solution_valid: bool = False,
    ) -> TacticalTargetingDecision:
        """Construct one exact target-bearing typed decision."""
        cal_flat = _resolve_cal_flat(ctx)
        logical_time_s = float(ctx.clock.elapsed.total_seconds())
        visibility_bound_m = self._targeting_visibility_bound(
            ctx,
            calibration=cal_flat,
        )
        contact_sensor = contact.sensor_attachment
        fire_control_sensor = fire_control.sensor_attachment if fire_control is not None else None
        range_evidence = (
            EffectiveRangeEvidence.from_catalog(
                physical_max_range_m=float(
                    weapon.weapon.definition.max_range_m,
                ),
                authored_effective_range_m=float(
                    weapon.weapon.definition.effective_range_m,
                ),
            )
            if weapon is not None
            else None
        )
        shooter_side = shooter.side if isinstance(shooter.side, str) else shooter.side.value
        target_side = target.side if isinstance(target.side, str) else target.side.value
        return TacticalTargetingDecision(
            engine_tick=int(ctx.clock.tick_count),
            logical_time_s=logical_time_s,
            battle_id=battle.battle_id,
            ordinal=ordinal,
            shooter_id=shooter.entity_id,
            shooter_side=shooter_side,
            shooter_domain=shooter.domain,
            target_id=target.entity_id,
            target_side=target_side,
            target_domain=target.domain,
            distance_m=distance_m,
            weapon_id=(weapon.weapon.weapon_id if weapon is not None else None),
            weapon_source_equipment_index=(weapon.source_equipment_index if weapon is not None else None),
            weapon_modeled_role=(weapon.modeled_role if weapon is not None else None),
            ammunition_id=(ammunition.ammo_id if ammunition is not None else None),
            physical_max_range_m=(range_evidence.physical_max_range_m if range_evidence is not None else 0.0),
            predictive_effective_range_m=(
                range_evidence.predictive_effective_range_m if range_evidence is not None else 0.0
            ),
            effective_range_basis=(range_evidence.basis if range_evidence is not None else None),
            legacy_derived_reference_range_m=(
                range_evidence.legacy_derived_reference_range_m if range_evidence is not None else 0.0
            ),
            contact_source=contact.source,
            observing_unit_id=shooter.entity_id,
            contact_sensor_source_equipment_index=(
                contact_sensor.source_equipment_index if contact_sensor is not None else None
            ),
            contact_sensor_id=(contact_sensor.sensor_id if contact_sensor is not None else None),
            contact_sensor_modeled_role=(contact_sensor.modeled_role if contact_sensor is not None else None),
            contact_time_s=logical_time_s,
            contact_range_m=contact.range_m,
            visibility_bound_m=visibility_bound_m,
            sensing_sensor_source_equipment_index=(
                contact_sensor.source_equipment_index if contact_sensor is not None else None
            ),
            sensing_sensor_id=(contact_sensor.sensor_id if contact_sensor is not None else None),
            sensing_sensor_modeled_role=(contact_sensor.modeled_role if contact_sensor is not None else None),
            sensing_range_m=contact.range_m,
            fire_control_source=(fire_control.source if fire_control is not None else FireControlSource.NONE),
            fire_control_sensor_source_equipment_index=(
                fire_control_sensor.source_equipment_index if fire_control_sensor is not None else None
            ),
            fire_control_sensor_id=(fire_control_sensor.sensor_id if fire_control_sensor is not None else None),
            fire_control_sensor_modeled_role=(
                fire_control_sensor.modeled_role if fire_control_sensor is not None else None
            ),
            fire_control_range_m=(fire_control.range_m if fire_control is not None else 0.0),
            disposition=disposition,
            authorized_standoff_m=authorized_standoff_m,
            hold_authorized=hold_authorized,
            engagement_solution_valid=engagement_solution_valid,
            sensing_aware_standoff_enabled=bool(
                cal_flat.get("enable_sensing_aware_standoff", True),
            ),
            fog_of_war_enabled=bool(
                cal_flat.get("enable_fog_of_war", False),
            ),
            observer_track_support=contact.observer_track_support,
        )

    def _targeting_candidate_for_contact(
        self,
        *,
        ctx: Any,
        shooter: Unit,
        target: Unit,
        distance_m: float,
        direct_visual_range_m: float,
        contact: _TargetingContact,
        sensor_ranges: Mapping[int, float],
        evidence_cache: _TargetingIntervalEvidenceCache | None = None,
    ) -> _TargetingCandidate:
        """Resolve the best current direct solution for one known contact."""
        all_weapons = tuple(ctx.unit_weapons.get(shooter.entity_id, ()))
        direct_weapons = tuple(
            attachment
            for attachment in all_weapons
            if weapon_role_uses_tactical_direct_engagement(
                attachment.modeled_role,
            )
        )
        target_score = self._score_target(
            shooter,
            target,
            distance_m,
            list(direct_weapons),
            ctx,
        )
        if not direct_weapons:
            return _TargetingCandidate(
                resolution=_TargetingResolution(
                    contact=contact,
                    weapon=None,
                    ammunition=None,
                    fire_control=None,
                    disposition=(
                        TargetingDisposition.ROUTED_WEAPON_ROLE
                        if all_weapons
                        else TargetingDisposition.NO_USABLE_WEAPON
                    ),
                ),
                target=target,
                target_score=target_score,
                distance_m=distance_m,
                direct_visual_range_m=direct_visual_range_m,
            )

        indirect_fire = getattr(ctx, "indirect_fire_engine", None)
        usable: list[tuple[float, WeaponAttachment, AmmoDefinition]] = []
        rejected: list[
            tuple[
                int,
                WeaponAttachment,
                AmmoDefinition | None,
                TargetingDisposition,
            ]
        ] = []
        for attachment in sorted(
            direct_weapons,
            key=lambda item: (
                item.source_equipment_index,
                item.weapon.weapon_id,
            ),
        ):
            definition = attachment.weapon.definition
            if float(definition.max_range_m) <= 0.0:
                continue
            ammunition = self._targeting_ammunition(
                ctx,
                shooter,
                attachment,
            )
            if not attachment.weapon.operational:
                rejected.append(
                    (
                        0,
                        attachment,
                        ammunition,
                        TargetingDisposition.WEAPON_INOPERABLE,
                    )
                )
                continue
            if indirect_fire is not None and indirect_fire.is_attachment_reserved(
                shooter.entity_id,
                attachment.source_equipment_index,
                attachment.weapon.weapon_id,
            ):
                rejected.append(
                    (
                        1,
                        attachment,
                        ammunition,
                        TargetingDisposition.WEAPON_RESERVED,
                    )
                )
                continue
            if ammunition is None:
                rejected.append(
                    (
                        2,
                        attachment,
                        None,
                        TargetingDisposition.NO_FIREABLE_AMMUNITION,
                    )
                )
                continue
            if not _weapon_supports_domain(definition, target.domain):
                rejected.append(
                    (
                        3,
                        attachment,
                        ammunition,
                        TargetingDisposition.TARGET_DOMAIN_UNSUPPORTED,
                    )
                )
                continue
            fit_score = min(
                float(definition.max_range_m) / max(distance_m, 1.0),
                3.0,
            )
            usable.append((fit_score, attachment, ammunition))

        if not usable:
            if not rejected:
                return _TargetingCandidate(
                    resolution=_TargetingResolution(
                        contact=contact,
                        weapon=None,
                        ammunition=None,
                        fire_control=None,
                        disposition=TargetingDisposition.NO_USABLE_WEAPON,
                    ),
                    target=target,
                    target_score=target_score,
                    distance_m=distance_m,
                    direct_visual_range_m=direct_visual_range_m,
                )
            _, weapon, ammunition, disposition = min(
                rejected,
                key=lambda item: (
                    item[0],
                    item[1].source_equipment_index,
                    item[1].weapon.weapon_id,
                ),
            )
            return _TargetingCandidate(
                resolution=_TargetingResolution(
                    contact=contact,
                    weapon=weapon,
                    ammunition=ammunition,
                    fire_control=None,
                    disposition=disposition,
                ),
                target=target,
                target_score=target_score,
                distance_m=distance_m,
                direct_visual_range_m=direct_visual_range_m,
            )

        resolved: list[tuple[float, _TargetingResolution]] = []
        for fit_score, weapon, ammunition in usable:
            fire_control, fire_control_rejection = self._targeting_fire_control(
                ctx=ctx,
                shooter=shooter,
                target=target,
                weapon=weapon,
                contact=contact,
                distance_m=distance_m,
                direct_visual_range_m=direct_visual_range_m,
                sensor_ranges=sensor_ranges,
                evidence_cache=evidence_cache,
            )
            range_evidence = EffectiveRangeEvidence.from_catalog(
                physical_max_range_m=float(
                    weapon.weapon.definition.max_range_m,
                ),
                authored_effective_range_m=float(
                    weapon.weapon.definition.effective_range_m,
                ),
            )
            if distance_m > range_evidence.physical_max_range_m:
                disposition = TargetingDisposition.OUTSIDE_PHYSICAL_RANGE
                valid = False
                authorized_standoff_m = 0.0
                hold_authorized = False
            elif (
                range_evidence.basis is EffectiveRangeBasis.AUTHORED
                and distance_m > range_evidence.predictive_effective_range_m
            ):
                disposition = TargetingDisposition.OUTSIDE_EFFECTIVE_RANGE
                valid = False
                authorized_standoff_m = 0.0
                hold_authorized = False
            elif fire_control is None:
                disposition = fire_control_rejection
                valid = False
                authorized_standoff_m = 0.0
                hold_authorized = False
            else:
                valid = True
                enabled = bool(
                    _resolve_cal_flat(ctx).get(
                        "enable_sensing_aware_standoff",
                        True,
                    ),
                )
                standoff_class = weapon_standoff_class(weapon.modeled_role)
                if range_evidence.basis is not EffectiveRangeBasis.AUTHORED:
                    disposition = TargetingDisposition.EFFECTIVE_RANGE_UNKNOWN
                    authorized_standoff_m = 0.0
                    hold_authorized = False
                elif not enabled:
                    disposition = TargetingDisposition.STANDOFF_DISABLED
                    authorized_standoff_m = 0.0
                    hold_authorized = False
                elif standoff_class is WeaponStandoffClass.UNSUPPORTED:
                    disposition = TargetingDisposition.STANDOFF_NOT_SUPPORTED_FOR_ROLE
                    authorized_standoff_m = 0.0
                    hold_authorized = False
                else:
                    authorized_standoff_m = min(
                        range_evidence.physical_max_range_m,
                        range_evidence.predictive_effective_range_m,
                        contact.range_m,
                        fire_control.range_m,
                    )
                    hold_authorized = authorized_standoff_m > 0.0 and distance_m <= authorized_standoff_m
                    disposition = (
                        TargetingDisposition.VALID_STANDOFF_HOLD
                        if hold_authorized
                        else TargetingDisposition.VALID_ENGAGEMENT_SOLUTION
                    )
            resolved.append(
                (
                    fit_score,
                    _TargetingResolution(
                        contact=contact,
                        weapon=weapon,
                        ammunition=ammunition,
                        fire_control=fire_control,
                        disposition=disposition,
                        authorized_standoff_m=authorized_standoff_m,
                        hold_authorized=hold_authorized,
                        engagement_solution_valid=valid,
                    ),
                )
            )

        valid_resolved = [item for item in resolved if item[1].engagement_solution_valid]
        _, resolution = min(
            valid_resolved or resolved,
            key=lambda item: (
                -item[0],
                item[1].weapon.source_equipment_index,
                item[1].weapon.weapon.weapon_id,
                item[1].ammunition.ammo_id,
            ),
        )
        return _TargetingCandidate(
            resolution=resolution,
            target=target,
            target_score=target_score,
            distance_m=distance_m,
            direct_visual_range_m=direct_visual_range_m,
        )

    def _resolve_targeting_decision(
        self,
        *,
        ctx: Any,
        battle: BattleContext,
        shooter: Unit,
        ordinal: int,
        unit_index: Mapping[str, Unit],
        member_ids: Collection[str],
        evidence_cache: _TargetingIntervalEvidenceCache | None = None,
    ) -> TacticalTargetingDecision:
        """Resolve one shooter decision from exact current battle membership."""
        shooter_side = shooter.side if isinstance(shooter.side, str) else shooter.side.value
        targets = tuple(
            target
            for unit_id in sorted(member_ids)
            if (target := unit_index.get(unit_id)) is not None
            and target.status == UnitStatus.ACTIVE
            and (target.side if isinstance(target.side, str) else target.side.value) != shooter_side
        )
        if not targets:
            return self._empty_targeting_decision(
                ctx=ctx,
                battle=battle,
                shooter=shooter,
                ordinal=ordinal,
            )

        candidates: list[_TargetingCandidate] = []
        range_policy = self._targeting_sensor_range_policy(
            ctx,
            shooter,
            evidence_cache=evidence_cache,
        )
        calibration = _resolve_cal_flat(ctx)
        fog_of_war_enabled = bool(
            calibration.get("enable_fog_of_war", False),
        )
        visibility_bound_m = self._targeting_visibility_bound(
            ctx,
            calibration=calibration,
        )
        for target in targets:
            distance_m = self._targeting_distance(shooter, target)
            if not fog_of_war_enabled and distance_m > (
                self._targeting_non_fow_contact_upper_bound_m(
                    ctx,
                    shooter,
                    target,
                    visibility_bound_m=visibility_bound_m,
                    range_policy=range_policy,
                )
                + 1e-9
            ):
                continue
            environment = self._targeting_environment(
                ctx,
                shooter,
                target,
                evidence_cache=evidence_cache,
            )
            direct_visual_range_m = self._targeting_direct_visual_range(
                ctx,
                shooter,
                target,
                environment=environment,
                evidence_cache=evidence_cache,
            )
            sensor_ranges = {
                attachment.source_equipment_index: self._targeting_sensor_range(
                    ctx,
                    shooter,
                    target,
                    attachment,
                    environment=environment,
                    range_policy=range_policy,
                    evidence_cache=evidence_cache,
                )
                for attachment in getattr(
                    ctx,
                    "unit_sensor_attachments",
                    {},
                ).get(shooter.entity_id, ())
            }
            contacts = self._targeting_contacts(
                ctx,
                shooter,
                target,
                distance_m=distance_m,
                visibility_bound_m=environment[0],
                direct_visual_range_m=direct_visual_range_m,
                sensor_ranges=sensor_ranges,
                evidence_cache=evidence_cache,
            )
            for contact in contacts:
                candidates.append(
                    self._targeting_candidate_for_contact(
                        ctx=ctx,
                        shooter=shooter,
                        target=target,
                        distance_m=distance_m,
                        direct_visual_range_m=direct_visual_range_m,
                        contact=contact,
                        sensor_ranges=sensor_ranges,
                        evidence_cache=evidence_cache,
                    )
                )

        if not candidates:
            return self._empty_targeting_decision(
                ctx=ctx,
                battle=battle,
                shooter=shooter,
                ordinal=ordinal,
                disposition=TargetingDisposition.NO_CONTACT,
                visibility_bound_m=visibility_bound_m,
            )

        valid_candidates = [candidate for candidate in candidates if candidate.resolution.engagement_solution_valid]
        selectable = valid_candidates or candidates
        current_witness_candidates = [
            candidate
            for candidate in selectable
            if candidate.resolution.contact.source is ContactSource.FOW_OBSERVER_WITNESS
        ]
        if current_witness_candidates:
            selectable = current_witness_candidates
        mode = calibration.get(
            "target_selection_mode",
            "threat_scored",
        )

        def _target_identity(
            candidate: _TargetingCandidate,
        ) -> tuple[str, str]:
            raw_target_side = candidate.target.side
            target_side = raw_target_side if isinstance(raw_target_side, str) else raw_target_side.value
            return (
                target_side,
                candidate.target.entity_id,
            )

        def _solution_identity(
            candidate: _TargetingCandidate,
        ) -> tuple[int, str, int, str, str, int, str]:
            resolution = candidate.resolution
            contact_sensor = resolution.contact.sensor_attachment
            weapon = resolution.weapon
            fire_control = resolution.fire_control
            fire_control_sensor = fire_control.sensor_attachment if fire_control is not None else None
            return (
                weapon.source_equipment_index if weapon is not None else -1,
                weapon.weapon.weapon_id if weapon is not None else "",
                (contact_sensor.source_equipment_index if contact_sensor is not None else -1),
                contact_sensor.sensor_id if contact_sensor is not None else "",
                (fire_control.source.value if fire_control is not None else FireControlSource.NONE.value),
                (fire_control_sensor.source_equipment_index if fire_control_sensor is not None else -1),
                (fire_control_sensor.sensor_id if fire_control_sensor is not None else ""),
            )

        if mode in {"closest", "nearest"}:
            selected = min(
                selectable,
                key=lambda candidate: (
                    candidate.distance_m,
                    _target_identity(candidate),
                    _solution_identity(candidate),
                ),
            )
        else:
            selected = min(
                selectable,
                key=lambda candidate: (
                    -candidate.target_score,
                    _target_identity(candidate),
                    _solution_identity(candidate),
                ),
            )
        resolution = selected.resolution
        return self._build_targeting_decision(
            ctx=ctx,
            battle=battle,
            shooter=shooter,
            target=selected.target,
            ordinal=ordinal,
            distance_m=selected.distance_m,
            direct_visual_range_m=selected.direct_visual_range_m,
            contact=resolution.contact,
            weapon=resolution.weapon,
            ammunition=resolution.ammunition,
            fire_control=resolution.fire_control,
            disposition=resolution.disposition,
            authorized_standoff_m=resolution.authorized_standoff_m,
            hold_authorized=resolution.hold_authorized,
            engagement_solution_valid=(resolution.engagement_solution_valid),
        )

    def _empty_targeting_decision(
        self,
        *,
        ctx: Any,
        battle: BattleContext,
        shooter: Unit,
        ordinal: int,
        disposition: TargetingDisposition = TargetingDisposition.NO_TARGET,
        visibility_bound_m: float | None = None,
    ) -> TacticalTargetingDecision:
        """Return one fully explicit non-authorizing targeting decision."""
        cal_flat = _resolve_cal_flat(ctx)
        recorded_visibility_m = (
            self._targeting_visibility_bound(
                ctx,
                calibration=cal_flat,
            )
            if visibility_bound_m is None
            else visibility_bound_m
        )
        return TacticalTargetingDecision(
            engine_tick=int(ctx.clock.tick_count),
            logical_time_s=float(ctx.clock.elapsed.total_seconds()),
            battle_id=battle.battle_id,
            ordinal=ordinal,
            shooter_id=shooter.entity_id,
            shooter_side=(shooter.side if isinstance(shooter.side, str) else shooter.side.value),
            shooter_domain=shooter.domain,
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
            visibility_bound_m=recorded_visibility_m,
            sensing_sensor_source_equipment_index=None,
            sensing_sensor_id=None,
            sensing_sensor_modeled_role=None,
            sensing_range_m=0.0,
            fire_control_source=FireControlSource.NONE,
            fire_control_sensor_source_equipment_index=None,
            fire_control_sensor_id=None,
            fire_control_sensor_modeled_role=None,
            fire_control_range_m=0.0,
            disposition=disposition,
            authorized_standoff_m=0.0,
            hold_authorized=False,
            engagement_solution_valid=False,
            sensing_aware_standoff_enabled=bool(
                cal_flat.get("enable_sensing_aware_standoff", True),
            ),
            fog_of_war_enabled=bool(
                cal_flat.get("enable_fog_of_war", False),
            ),
        )

    def _resolve_targeting_picture(
        self,
        ctx: Any,
        battle: BattleContext,
        *,
        interval: TargetingInterval,
        evidence_cache: _TargetingIntervalEvidenceCache | None = None,
    ) -> TacticalTargetingPicture:
        """Resolve one complete picture without mutating its runtime owner."""
        try:
            declared_members = interval.battle_memberships[battle.battle_id]
        except KeyError as exc:
            raise RuntimeError(
                f"Battle {battle.battle_id!r} is absent from the prepared targeting interval",
            ) from exc

        unit_index = {unit.entity_id: unit for units in ctx.units_by_side.values() for unit in units}
        ordered_members = tuple(
            sorted(
                declared_members,
                key=lambda unit_id: (
                    interval.unit_sides[unit_id],
                    unit_id,
                ),
            )
        )
        decisions: list[TacticalTargetingDecision] = []
        for ordinal, unit_id in enumerate(ordered_members):
            shooter = unit_index.get(unit_id)
            if shooter is None:
                raise RuntimeError(
                    f"Prepared targeting member {unit_id!r} is absent from the runtime roster",
                )
            if shooter.status != UnitStatus.ACTIVE:
                decision = self._empty_targeting_decision(
                    ctx=ctx,
                    battle=battle,
                    shooter=shooter,
                    ordinal=ordinal,
                )
            else:
                decision = self._resolve_targeting_decision(
                    ctx=ctx,
                    battle=battle,
                    shooter=shooter,
                    ordinal=ordinal,
                    unit_index=unit_index,
                    member_ids=declared_members,
                    evidence_cache=evidence_cache,
                )
            decisions.append(decision)

        return TacticalTargetingPicture(
            engine_tick=interval.engine_tick,
            logical_time_s=interval.logical_time_s,
            battle_id=battle.battle_id,
            fog_of_war_enabled=interval.fog_of_war_enabled,
            decisions=tuple(decisions),
        )

    @staticmethod
    def _battle_clock_view(ctx: SimulationContext) -> BattleClockView:
        """Capture only the immutable logical-clock values executors read."""
        clock = ctx.clock
        elapsed = getattr(clock, "elapsed", timedelta())
        if not isinstance(elapsed, timedelta):
            elapsed = timedelta(seconds=float(elapsed.total_seconds()))
        return BattleClockView(
            current_time=getattr(clock, "current_time", datetime.min),
            elapsed=elapsed,
            tick_count=int(getattr(clock, "tick_count", 0)),
        )

    @staticmethod
    def _battle_scenario_view(ctx: SimulationContext) -> BattleScenarioView:
        """Capture the tactical scenario scalars without exposing config."""
        config = getattr(ctx, "config", None)
        return BattleScenarioView(
            latitude=float(getattr(config, "latitude", 0.0)),
            longitude=float(getattr(config, "longitude", 0.0)),
            behavior_rules=getattr(config, "behavior_rules", {}),
            side_experience_levels={
                side.side: float(getattr(side, "experience_level", 0.5))
                for side in getattr(config, "sides", ())
            },
        )

    @classmethod
    def _build_ooda_runtime(
        cls,
        ctx: SimulationContext,
    ) -> BattleOODARuntime:
        """Bind the exact owners available to the injected OODA executor."""
        return BattleOODARuntime(
            clock=cls._battle_clock_view(ctx),
            cal_flat=_resolve_cal_flat(ctx),
            units_by_side=ctx.units_by_side,
            rng_manager=getattr(ctx, "rng_manager", None),
            ooda_engine=getattr(ctx, "ooda_engine", None),
            school_registry=getattr(ctx, "school_registry", None),
            assessor=getattr(ctx, "assessor", None),
            decision_engine=getattr(ctx, "decision_engine", None),
            commander_engine=getattr(ctx, "commander_engine", None),
            planning_engine=getattr(ctx, "planning_engine", None),
            stratagem_engine=getattr(ctx, "stratagem_engine", None),
            fog_of_war=getattr(ctx, "fog_of_war", None),
            comms_engine=getattr(ctx, "comms_engine", None),
            cbrn_engine=getattr(ctx, "cbrn_engine", None),
            stockpile_manager=getattr(ctx, "stockpile_manager", None),
            order_propagation=getattr(ctx, "order_propagation", None),
            morale_states=getattr(ctx, "morale_states", {}),
        )

    @classmethod
    def _build_movement_runtime(
        cls,
        ctx: SimulationContext,
        units_by_side: Mapping[str, Sequence[Unit]],
    ) -> BattleMovementRuntime:
        """Bind targeting plus movement owners without unrelated context."""
        return BattleMovementRuntime(
            clock=cls._battle_clock_view(ctx),
            config=cls._battle_scenario_view(ctx),
            cal_flat=_resolve_cal_flat(ctx),
            units_by_side=getattr(ctx, "units_by_side", units_by_side),
            unit_weapons=getattr(ctx, "unit_weapons", {}),
            unit_sensor_attachments=getattr(ctx, "unit_sensor_attachments", {}),
            unit_sensors=getattr(ctx, "unit_sensors", {}),
            tactical_targeting=getattr(ctx, "tactical_targeting", None),
            targeting_default_visibility_m=getattr(
                ctx,
                "targeting_default_visibility_m",
                DEFAULT_TARGETING_VISIBILITY_M,
            ),
            weather_engine=getattr(ctx, "weather_engine", None),
            time_of_day_engine=getattr(ctx, "time_of_day_engine", None),
            seasons_engine=getattr(ctx, "seasons_engine", None),
            sea_state_engine=getattr(ctx, "sea_state_engine", None),
            obscurants_engine=getattr(ctx, "obscurants_engine", None),
            conditions_engine=getattr(ctx, "conditions_engine", None),
            conditions_facade=getattr(ctx, "conditions_facade", None),
            underwater_acoustics_engine=getattr(
                ctx,
                "underwater_acoustics_engine",
                None,
            ),
            cbrn_engine=getattr(ctx, "cbrn_engine", None),
            detection_engine=getattr(ctx, "detection_engine", None),
            fog_of_war=getattr(ctx, "fog_of_war", None),
            los_engine=getattr(ctx, "los_engine", None),
            classification=getattr(ctx, "classification", None),
            heightmap=getattr(ctx, "heightmap", None),
            trench_engine=getattr(ctx, "trench_engine", None),
            infrastructure_manager=getattr(ctx, "infrastructure_manager", None),
            obstacle_manager=getattr(ctx, "obstacle_manager", None),
            incendiary_engine=getattr(ctx, "incendiary_engine", None),
            indirect_fire_engine=getattr(ctx, "indirect_fire_engine", None),
            movement_diagnostics=getattr(ctx, "movement_diagnostics", None),
            movement_engine=getattr(ctx, "movement_engine", None),
            maintenance_engine=getattr(ctx, "maintenance_engine", None),
            hydrography_manager=getattr(ctx, "hydrography_manager", None),
            bridge_infrastructure=getattr(ctx, "infrastructure", None),
        )

    @classmethod
    def _build_engagement_runtime(
        cls,
        ctx: SimulationContext,
        units_by_side: Mapping[str, Sequence[Unit]],
    ) -> BattleEngagementRuntime:
        """Bind targeting plus engagement owners without unrelated context."""
        return BattleEngagementRuntime(
            clock=cls._battle_clock_view(ctx),
            config=cls._battle_scenario_view(ctx),
            cal_flat=_resolve_cal_flat(ctx),
            units_by_side=getattr(ctx, "units_by_side", units_by_side),
            unit_weapons=getattr(ctx, "unit_weapons", {}),
            unit_sensor_attachments=getattr(ctx, "unit_sensor_attachments", {}),
            unit_sensors=getattr(ctx, "unit_sensors", {}),
            tactical_targeting=getattr(ctx, "tactical_targeting", None),
            targeting_default_visibility_m=getattr(
                ctx,
                "targeting_default_visibility_m",
                DEFAULT_TARGETING_VISIBILITY_M,
            ),
            weather_engine=getattr(ctx, "weather_engine", None),
            time_of_day_engine=getattr(ctx, "time_of_day_engine", None),
            seasons_engine=getattr(ctx, "seasons_engine", None),
            sea_state_engine=getattr(ctx, "sea_state_engine", None),
            obscurants_engine=getattr(ctx, "obscurants_engine", None),
            conditions_engine=getattr(ctx, "conditions_engine", None),
            conditions_facade=getattr(ctx, "conditions_facade", None),
            underwater_acoustics_engine=getattr(
                ctx,
                "underwater_acoustics_engine",
                None,
            ),
            cbrn_engine=getattr(ctx, "cbrn_engine", None),
            detection_engine=getattr(ctx, "detection_engine", None),
            fog_of_war=getattr(ctx, "fog_of_war", None),
            los_engine=getattr(ctx, "los_engine", None),
            classification=getattr(ctx, "classification", None),
            heightmap=getattr(ctx, "heightmap", None),
            trench_engine=getattr(ctx, "trench_engine", None),
            infrastructure_manager=getattr(ctx, "infrastructure_manager", None),
            obstacle_manager=getattr(ctx, "obstacle_manager", None),
            incendiary_engine=getattr(ctx, "incendiary_engine", None),
            indirect_fire_engine=getattr(ctx, "indirect_fire_engine", None),
            rng_manager=getattr(ctx, "rng_manager", None),
            event_bus=getattr(ctx, "event_bus", None),
            engagement_engine=getattr(ctx, "engagement_engine", None),
            era_runtime_contract=getattr(ctx, "era_runtime_contract", None),
            morale_states=getattr(ctx, "morale_states", {}),
            morale_runtime=getattr(ctx, "morale_runtime", None),
            roe_engine=getattr(ctx, "roe_engine", None),
            maintenance_engine=getattr(ctx, "maintenance_engine", None),
            suppression_engine=getattr(ctx, "suppression_engine", None),
            ew_engine=getattr(ctx, "ew_engine", None),
            eccm_engine=getattr(ctx, "eccm_engine", None),
            space_engine=getattr(ctx, "space_engine", None),
            unconventional_engine=getattr(ctx, "unconventional_engine", None),
            population_engine=getattr(ctx, "population_engine", None),
            archery_engine=getattr(ctx, "archery_engine", None),
            ato_engine=getattr(ctx, "ato_engine", None),
            barrage_engine=getattr(ctx, "barrage_engine", None),
            cavalry_engine=getattr(ctx, "cavalry_engine", None),
            dew_engine=getattr(ctx, "dew_engine", None),
            formation_ancient_engine=getattr(ctx, "formation_ancient_engine", None),
            formation_napoleonic_engine=getattr(
                ctx,
                "formation_napoleonic_engine",
                None,
            ),
            gas_warfare_engine=getattr(ctx, "gas_warfare_engine", None),
            melee_engine=getattr(ctx, "melee_engine", None),
            missile_engine=getattr(ctx, "missile_engine", None),
            volley_fire_engine=getattr(ctx, "volley_fire_engine", None),
            air_combat_engine=getattr(ctx, "air_combat_engine", None),
            air_ground_engine=getattr(ctx, "air_ground_engine", None),
            air_defense_engine=getattr(ctx, "air_defense_engine", None),
            naval_gunnery_engine=getattr(ctx, "naval_gunnery_engine", None),
            naval_surface_engine=getattr(ctx, "naval_surface_engine", None),
            naval_subsurface_engine=getattr(ctx, "naval_subsurface_engine", None),
            naval_gunfire_support_engine=getattr(
                ctx,
                "naval_gunfire_support_engine",
                None,
            ),
        )

    def execute_ooda_interval(
        self,
        ctx: SimulationContext,
        battles: Collection[BattleContext],
        dt: float,
    ) -> None:
        """Advance and route OODA through the injected interval executor."""
        self._ooda_executor.execute_interval(
            self._executor_owner,
            OODAIntervalRequest(
                runtime=self._build_ooda_runtime(ctx),
                battles=tuple(
                    BattleIntervalView.from_battle(battle)
                    for battle in battles
                ),
                dt_seconds=dt,
            ),
        )

    def execute_tick(
        self,
        ctx: SimulationContext,
        battle: BattleContext,
        dt: float,
    ) -> None:
        """Execute one tactical tick for a battle.

        Sequences: detection → AI → orders → movement → engagement →
        morale → supply.  All domain logic delegated to engines in *ctx*.

        Parameters
        ----------
        ctx:
            SimulationContext with all engines and state.
        battle:
            Active battle to advance.
        dt:
            Tick duration in seconds.
        """
        self.validate_performance_runtime(ctx)
        if not battle.active:
            return

        cal_flat = _resolve_cal_flat(ctx)
        targeting_runtime = getattr(ctx, "tactical_targeting", None)
        if targeting_runtime is None and cal_flat.get(
            "enable_fog_of_war",
            False,
        ):
            raise RuntimeError(
                "Fog-of-war battle execution requires the receipt-bearing TacticalTargetingRuntime boundary",
            )
        if targeting_runtime is not None:
            if type(targeting_runtime) is not TacticalTargetingRuntime:
                raise RuntimeError(
                    "Battle execution requires an exact TacticalTargetingRuntime owner",
                )
            interval = targeting_runtime.prepared_interval
            picture = targeting_runtime.latest_picture(battle.battle_id)
            if (
                interval is None
                or interval.engine_tick != int(ctx.clock.tick_count)
                or interval.logical_time_s != float(ctx.clock.elapsed.total_seconds())
                or battle.battle_id not in interval.battle_ids
                or picture is None
                or picture.engine_tick != interval.engine_tick
                or picture.logical_time_s != interval.logical_time_s
            ):
                raise RuntimeError(
                    "Battle execution requires its complete prepublished targeting picture",
                )

        battle.ticks_executed += 1
        battle.battle_elapsed_s += dt
        units_by_side = ctx.units_by_side
        timestamp = ctx.clock.current_time

        # 1. Pre-build per-side active enemy lists and position arrays
        active_enemies, enemy_pos_arrays = self._build_enemy_data(units_by_side)

        # Phase 88: Build UnitArrays for SoA operations
        _unit_arrays: UnitArrays | None = None
        if cal_flat.get("enable_soa", False):
            _unit_arrays = UnitArrays.from_units(
                units_by_side,
                morale_states=getattr(ctx, "morale_states", None),
                unit_weapons=getattr(ctx, "unit_weapons", None),
            )
            # Override enemy_pos_arrays with SoA-derived versions
            enemy_pos_arrays = {side: _unit_arrays.get_enemy_positions(side) for side in units_by_side}
            self._stage_performance_delta(
                PerformanceReceiptDelta(
                    soa=SoAReceipt(
                        pre_movement_builds=1,
                        pre_movement_enemy_position_projections=len(
                            units_by_side,
                        ),
                    ),
                ),
            )

        # 1a. Phase 70b: entity_id → Unit index for O(1) lookups
        _unit_index: dict[str, Unit] = {}
        for _side_units_idx in units_by_side.values():
            for _u_idx in _side_units_idx:
                _unit_index[_u_idx.entity_id] = _u_idx

        # 1c. Phase 85/118: publish sensing-only LOD tiers when the typed
        # targeting coordinator did not already publish this interval.
        if getattr(ctx, "tactical_targeting", None) is None:
            self._classify_lod_tiers(
                ctx,
                units_by_side,
                enemy_pos_arrays,
                active_enemies=active_enemies,
            )

        # 3. Order execution update
        if ctx.order_execution is not None:
            ctx.order_execution.update(dt)

        # 3b. Apply behavior rules — set unit speeds from scenario YAML
        # (pre-scripted behavior for historical scenarios)
        behavior_rules = getattr(ctx.config, "behavior_rules", {})
        if behavior_rules:
            self._apply_behavior_rules(units_by_side, active_enemies, behavior_rules)

        # 3c. Decay suppression (Phase 40e)
        sup_engine = getattr(ctx, "suppression_engine", None)
        if sup_engine is not None:
            for state in self._suppression_states.values():
                sup_engine.update_suppression(state, dt)

        # 4. Movement — units with active movement orders
        # Record pre-movement positions for posture tracking (Phase 40b)
        pre_positions: dict[str, tuple[float, float]] = {}
        for side_units in units_by_side.values():
            for u in side_units:
                if u.status == UnitStatus.ACTIVE:
                    pre_positions[u.entity_id] = (u.position.easting, u.position.northing)

        self._execute_movement(
            ctx,
            units_by_side,
            active_enemies,
            dt,
            battle,
            behavior_rules,
            enemy_pos_arrays=enemy_pos_arrays,
        )

        # 4b. Update posture based on movement (Phase 40b)
        defensive_sides = set(cal_flat.get("defensive_sides", []))
        dig_in_ticks = cal_flat.get("dig_in_ticks", 30)
        for side_name, side_units in units_by_side.items():
            for u in side_units:
                if u.status != UnitStatus.ACTIVE:
                    continue
                if not hasattr(u, "posture"):
                    continue
                uid = u.entity_id
                pre = pre_positions.get(uid)
                if pre is None:
                    continue
                cur = (u.position.easting, u.position.northing)
                moved = abs(cur[0] - pre[0]) > 0.01 or abs(cur[1] - pre[1]) > 0.01
                if moved:
                    self._ticks_stationary[uid] = 0
                    object.__setattr__(u, "posture", type(u.posture)(0))  # MOVING
                else:
                    self._ticks_stationary[uid] = self._ticks_stationary.get(uid, 0) + 1
                    ticks = self._ticks_stationary[uid]
                    if side_name in defensive_sides:
                        if ticks > dig_in_ticks:
                            object.__setattr__(u, "posture", type(u.posture)(3))  # DUG_IN
                        else:
                            object.__setattr__(u, "posture", type(u.posture)(2))  # DEFENSIVE
                    else:
                        object.__setattr__(u, "posture", type(u.posture)(1))  # HALTED

        # 4c. Phase 50b: auto-assign air posture based on flight state / fuel
        for side_units in units_by_side.values():
            for u in side_units:
                if u.status != UnitStatus.ACTIVE:
                    continue
                ap = getattr(u, "air_posture", None)
                if ap is None:
                    continue
                from stochastic_warfare.entities.unit_classes.aerial import AirPosture

                fs = getattr(u, "flight_state", None)
                fuel = getattr(u, "fuel_remaining", 1.0)
                if fs is not None and int(fs) == 0:  # FlightState.GROUNDED
                    u.air_posture = AirPosture.GROUNDED
                elif fuel < 0.2:
                    u.air_posture = AirPosture.RETURNING
                elif int(ap) == 0:  # Was GROUNDED posture but operational
                    u.air_posture = AirPosture.ON_STATION

        # 4d. Phase 51b: auto-assign naval posture based on enemy proximity
        # Only for modern/ww2 eras — ancient/napoleonic oar-powered ships
        # don't have the modern battle stations speed concept.
        _era = ctx.era_runtime_contract.era.value
        if _era in ("modern", "ww2", "ww1"):
            for side_name, side_units in units_by_side.items():
                enemies = active_enemies.get(side_name, [])
                for u in side_units:
                    if u.status != UnitStatus.ACTIVE:
                        continue
                    np_attr = getattr(u, "naval_posture", None)
                    if np_attr is None:
                        continue
                    from stochastic_warfare.entities.unit_classes.naval import NavalPosture

                    if not enemies:
                        if int(np_attr) == 3:  # BATTLE_STATIONS → UNDERWAY
                            object.__setattr__(u, "naval_posture", NavalPosture.UNDERWAY)
                        continue
                    min_dist = _nearest_enemy_dist(
                        u.position,
                        enemies,
                        enemy_pos_arr=enemy_pos_arrays.get(side_name),
                    )
                    if min_dist < self._config.engagement_range_m * 2:
                        object.__setattr__(u, "naval_posture", NavalPosture.BATTLE_STATIONS)
                    elif int(np_attr) == 3:  # No longer in threat range
                        object.__setattr__(u, "naval_posture", NavalPosture.UNDERWAY)

        # 4e. Phase 51d: mine warfare — check moving naval units against minefields
        mine_engine = getattr(ctx, "mine_warfare_engine", None)
        pending_mine_damage: list[tuple[Unit, UnitStatus, str]] = []
        if mine_engine is not None and mine_engine._mines:
            dest_thresh_m = cal_flat.get(
                "destruction_threshold",
                self._config.destruction_threshold,
            )
            dis_thresh_m = cal_flat.get(
                "disable_threshold",
                self._config.disable_threshold,
            )
            for side_units in units_by_side.values():
                for u in side_units:
                    if u.status != UnitStatus.ACTIVE:
                        continue
                    if u.domain not in (Domain.NAVAL, Domain.SUBMARINE, Domain.AMPHIBIOUS):
                        continue
                    if u.speed < 0.1:
                        continue  # stationary — no mine trigger
                    for mine in list(mine_engine._mines):
                        if not mine.armed or mine.detonated:
                            continue
                        dx = u.position.easting - mine.position.easting
                        dy = u.position.northing - mine.position.northing
                        dist_m = math.sqrt(dx * dx + dy * dy)
                        _trigger_radii = {0: 5, 1: 50, 2: 100, 3: 30, 4: 80, 5: 100, 6: 120}
                        trigger_radius = _trigger_radii.get(int(mine.mine_type), 50)
                        if dist_m <= trigger_radius:
                            mr = mine_engine.resolve_mine_encounter(
                                ship_id=u.entity_id,
                                mine=mine,
                                ship_magnetic_sig=0.5,
                                ship_acoustic_sig=0.5,
                                timestamp=timestamp,
                            )
                            if mr.detonated and mr.damage_fraction > 0:
                                if mr.damage_fraction >= dest_thresh_m:
                                    pending_mine_damage.append((u, UnitStatus.DESTROYED, "mine"))
                                elif mr.damage_fraction >= dis_thresh_m:
                                    pending_mine_damage.append((u, UnitStatus.DISABLED, "mine"))

        # 4f. Phase 66a: IED encounters during ground movement
        _uw_eng = getattr(ctx, "unconventional_engine", None)
        if cal_flat.get("enable_unconventional_warfare", False) and _uw_eng is not None and _uw_eng._ieds:
            for _ied_id, _ied_data in list(_uw_eng._ieds.items()):
                if not _ied_data["active"]:
                    continue
                _ied_pos = _ied_data["position"]
                for side_units_ied in units_by_side.values():
                    for _u_ied in side_units_ied:
                        if _u_ied.status != UnitStatus.ACTIVE:
                            continue
                        if getattr(_u_ied, "domain", None) in (
                            Domain.NAVAL,
                            Domain.SUBMARINE,
                            Domain.AMPHIBIOUS,
                        ):
                            continue  # naval mines handled above
                        # Only units that moved this tick
                        _pre_ied = pre_positions.get(_u_ied.entity_id)
                        if _pre_ied is None:
                            continue
                        _cur_ied = (_u_ied.position.easting, _u_ied.position.northing)
                        if abs(_cur_ied[0] - _pre_ied[0]) < 0.01 and abs(_cur_ied[1] - _pre_ied[1]) < 0.01:
                            continue  # didn't move
                        _dx_ied = _u_ied.position.easting - _ied_pos.easting
                        _dy_ied = _u_ied.position.northing - _ied_pos.northing
                        _dist_ied = math.sqrt(_dx_ied * _dx_ied + _dy_ied * _dy_ied)
                        if _dist_ied > _ied_data["blast_radius_m"] * 2:
                            continue
                        # Check EW jamming for remote IEDs
                        if _ied_data["subtype"] == "remote":
                            _ew_eng_ied = getattr(ctx, "ew_engine", None)
                            _jammed = _uw_eng.check_ew_jamming(
                                _ied_id,
                                _ew_eng_ied is not None,
                                0.5,
                            )
                            if _jammed:
                                continue
                        # Detection roll — speed-based
                        _speed_ied = getattr(_u_ied, "current_speed_mps", getattr(_u_ied, "speed", 5.0))
                        _has_eng = "engineer" in getattr(_u_ied, "unit_type", "").lower()
                        if _uw_eng.check_ied_detection(_speed_ied, _has_eng, _u_ied.entity_id):
                            continue
                        # Detonation
                        _result_ied = _uw_eng.detonate_ied(_ied_id, _u_ied.entity_id, timestamp=timestamp)
                        logger.info(
                            "IED %s detonated on %s (blast=%.1fm)",
                            _ied_id,
                            _u_ied.entity_id,
                            _result_ied.blast_radius_m,
                        )
                        break  # one IED per tick per location

        # 4g. Phase 62a: Heat/cold environmental casualties
        if cal_flat.get("enable_human_factors", False):
            _wx62 = getattr(ctx, "weather_engine", None)
            if _wx62 is not None:
                try:
                    _cur62 = _wx62.current
                    _temp62 = _cur62.temperature
                    _humid62 = getattr(_cur62, "humidity", 0.5)
                    _wind62 = getattr(_cur62.wind, "speed", 0.0)
                    _wbgt = _compute_wbgt(_temp62, _humid62)
                    _wc = _compute_wind_chill(_temp62, _wind62)

                    for _su62 in units_by_side.values():
                        for _u62 in _su62:
                            if _u62.status != UnitStatus.ACTIVE:
                                continue
                            _uid62 = _u62.entity_id
                            _env_rate = 0.0

                            # Heat stress
                            if _wbgt > 28.0:
                                _hr = cal_flat.get("heat_casualty_base_rate", 0.02) * (_wbgt - 28.0) / 10.0
                                # MOPP multiplier: gear traps heat
                                _cbrn62 = getattr(ctx, "cbrn_engine", None)
                                _mopp62 = 0
                                if _cbrn62 is not None:
                                    _mopp62 = _cbrn62.get_mopp_level(_uid62)
                                _hr *= 1.0 + _mopp62 * 0.5
                                # Exertion: moving units generate more heat
                                _pre62 = pre_positions.get(_uid62)
                                if _pre62 is not None:
                                    _cur_pos62 = (_u62.position.easting, _u62.position.northing)
                                    if abs(_cur_pos62[0] - _pre62[0]) > 0.01 or abs(_cur_pos62[1] - _pre62[1]) > 0.01:
                                        _hr *= 1.5
                                _env_rate += _hr

                            # Cold injury
                            if _wc < -20.0:
                                _cr = cal_flat.get("cold_casualty_base_rate", 0.015) * (abs(_wc) - 20.0) / 20.0
                                _env_rate += _cr

                            if _env_rate > 0:
                                _frac = _env_rate * (dt / 3600.0)
                                self._env_casualty_accum[_uid62] = self._env_casualty_accum.get(_uid62, 0.0) + _frac
                                if self._env_casualty_accum[_uid62] >= 1.0:
                                    _cas = int(self._env_casualty_accum[_uid62])
                                    self._env_casualty_accum[_uid62] -= _cas
                                    _pers = _u62.personnel
                                    if _pers and len(_pers) > _cas:
                                        object.__setattr__(
                                            _u62,
                                            "personnel",
                                            _pers[:-_cas],
                                        )
                                        logger.debug(
                                            "Env casualty: %s lost %d personnel (heat/cold)",
                                            _uid62,
                                            _cas,
                                        )
                except Exception as exc:
                    if not self._suppress_runtime_failure(
                        "environment.weather",
                        "apply_environmental_casualties",
                        exc,
                    ):
                        raise
                    logger.debug("Phase 62a env casualty failed", exc_info=True)

        # 4g2. Phase 78c: environmental fatigue acceleration (heat/cold)
        if cal_flat.get("enable_environmental_fatigue", False):
            _fatigue_mgr_78 = getattr(ctx, "fatigue_manager", None)
            if _fatigue_mgr_78 is not None:
                _wx78 = getattr(ctx, "weather_engine", None)
                if _wx78 is not None:
                    try:
                        _cur78 = _wx78.current
                        _temp78 = _cur78.temperature
                        _humid78 = getattr(_cur78, "humidity", 0.5)
                        _wind78 = getattr(_cur78.wind, "speed", 0.0)
                        _wbgt78 = _compute_wbgt(_temp78, _humid78)
                        _wc78 = _compute_wind_chill(_temp78, _wind78)

                        _temp_stress78 = 0.0
                        if _wbgt78 > 28.0:
                            _temp_stress78 = (_wbgt78 - 28.0) / 10.0
                        elif _wc78 < -20.0:
                            _temp_stress78 = (-20.0 - _wc78) / 20.0

                        if _temp_stress78 > 0:
                            for _su_fat78 in units_by_side.values():
                                for _u_fat78 in _su_fat78:
                                    if _u_fat78.status == UnitStatus.ACTIVE:
                                        _fatigue_mgr_78.accumulate(
                                            _u_fat78.entity_id,
                                            dt / 3600.0,
                                            "march",
                                            temperature_stress=_temp_stress78,
                                        )
                    except Exception as exc:
                        if not self._suppress_runtime_failure(
                            "human_factors.fatigue",
                            "apply_environmental_fatigue",
                            exc,
                        ):
                            raise
                        logger.debug("Phase 78c env fatigue failed", exc_info=True)

        # 4h. Phase 71b: missile flight resolution — advance in-flight missiles
        _missile_eng_71 = getattr(ctx, "missile_engine", None)
        _enable_missile_routing_71 = cal_flat.get("enable_missile_routing", False)
        _pending_missile_damage: list[tuple[Unit, UnitStatus, str]] = []
        if _missile_eng_71 is not None and _enable_missile_routing_71:
            _gps_acc_71 = 5.0
            _space_eng_71 = getattr(ctx, "space_engine", None)
            if _space_eng_71 is not None:
                _gps_acc_71 = getattr(_space_eng_71, "get_gps_cep", lambda: 5.0)()

            # Phase 71c: missile defense intercept — check AD units
            _md_eng_71 = getattr(ctx, "missile_defense_engine", None)
            if _md_eng_71 is not None:
                for _m71 in list(_missile_eng_71.active_missiles):
                    if not _m71.active:
                        continue
                    # Find which side launched this missile, defenders are the other side
                    _launcher_side_71 = None
                    for _s71, _su71 in units_by_side.items():
                        for _u71 in _su71:
                            if _u71.entity_id == _m71.launcher_id:
                                _launcher_side_71 = _s71
                                break
                        if _launcher_side_71 is not None:
                            break
                    if _launcher_side_71 is None:
                        continue
                    for _ds71, _du71 in units_by_side.items():
                        if _ds71 == _launcher_side_71:
                            continue
                        for _ad71 in _du71:
                            if _ad71.status != UnitStatus.ACTIVE:
                                continue
                            # Check if unit has AD weapons
                            _has_ad = False
                            for _w71 in getattr(_ad71, "weapons", []):
                                _wcat71 = getattr(getattr(_w71, "definition", _w71), "category", "")
                                if _wcat71 in ("SAM", "CIWS", "MISSILE_LAUNCHER"):
                                    _has_ad = True
                                    break
                            if not _has_ad:
                                continue
                            _dx71 = _ad71.position.easting - _m71.current_pos.easting
                            _dy71 = _ad71.position.northing - _m71.current_pos.northing
                            _dist71 = math.sqrt(_dx71 * _dx71 + _dy71 * _dy71)
                            _ad_range_71 = getattr(_ad71, "max_engagement_range_m", 50000.0)
                            if _dist71 > _ad_range_71:
                                continue
                            _ad_pk_71 = 0.7  # base Pk for AD systems
                            from stochastic_warfare.combat.missiles import MissileType as _MT71

                            if _m71.flight_profile.missile_type in (
                                _MT71.CRUISE_SUBSONIC,
                                _MT71.CRUISE_SUPERSONIC,
                                _MT71.COASTAL_DEFENSE_SSM,
                            ):
                                _cmd_result = _md_eng_71.engage_cruise_missile(
                                    defender_pk=_ad_pk_71,
                                    missile_speed_mps=_m71.flight_profile.speed_mps,
                                    sea_skimming=_m71.flight_profile.cruise_altitude_m < 20.0,
                                    defender_id=_ad71.entity_id,
                                    missile_id=_m71.missile_id,
                                )
                                if _cmd_result.hit:
                                    _m71.active = False
                                    logger.info(
                                        "Missile %s intercepted by %s (cruise defense)",
                                        _m71.missile_id,
                                        _ad71.entity_id,
                                    )
                                    break
                            else:
                                _bmd_result = _md_eng_71.engage_ballistic_missile(
                                    defender_pks=[_ad_pk_71],
                                    missile_speed_mps=_m71.flight_profile.speed_mps,
                                    defender_id=_ad71.entity_id,
                                    missile_id=_m71.missile_id,
                                )
                                if _bmd_result.intercepted:
                                    _m71.active = False
                                    logger.info(
                                        "Missile %s intercepted by %s (BMD)",
                                        _m71.missile_id,
                                        _ad71.entity_id,
                                    )
                                    break

            # Advance missiles and resolve impacts
            _impacts_71 = _missile_eng_71.update_missiles_in_flight(dt, gps_accuracy_m=_gps_acc_71)
            _dest_thresh_71 = cal_flat.get("destruction_threshold", self._config.destruction_threshold)
            _dis_thresh_71 = cal_flat.get("disable_threshold", self._config.disable_threshold)
            for _impact_71 in _impacts_71:
                if not _impact_71.hit:
                    continue
                # Find nearest unit to impact position
                _best_unit_71: Unit | None = None
                _best_dist_71 = 100.0  # max 100m search radius
                for _su71b in units_by_side.values():
                    for _u71b in _su71b:
                        if _u71b.status != UnitStatus.ACTIVE:
                            continue
                        _dx71b = _u71b.position.easting - _impact_71.impact_pos.easting
                        _dy71b = _u71b.position.northing - _impact_71.impact_pos.northing
                        _d71b = math.sqrt(_dx71b * _dx71b + _dy71b * _dy71b)
                        if _d71b < _best_dist_71:
                            _best_dist_71 = _d71b
                            _best_unit_71 = _u71b
                if _best_unit_71 is not None:
                    _apply_aggregate_casualties(
                        max(
                            1,
                            int(
                                _impact_71.damage_fraction
                                * max(1, len(_best_unit_71.personnel) if _best_unit_71.personnel else 4)
                            ),
                        ),
                        _best_unit_71,
                        _pending_missile_damage,
                        _dest_thresh_71,
                        _dis_thresh_71,
                        self._cumulative_casualties,
                    )
                    logger.debug(
                        "Missile %s hit unit %s (dmg=%.2f)",
                        _impact_71.missile_id,
                        _best_unit_71.entity_id,
                        _impact_71.damage_fraction,
                    )

        # 4i. Phase 71d: carrier ops — CAP management and sortie rate
        _carrier_eng_71 = getattr(ctx, "carrier_ops_engine", None)
        _enable_carrier_ops_71 = cal_flat.get("enable_carrier_ops", False)
        if _carrier_eng_71 is not None and _enable_carrier_ops_71:
            # Update CAP stations
            try:
                _cap_updates_71 = _carrier_eng_71.update_cap_stations(dt)
                for _cap71 in _cap_updates_71:
                    if _cap71.relief_needed:
                        logger.debug("CAP station %s needs relief", _cap71.station_id)
            except Exception as exc:
                if not self._suppress_runtime_failure(
                    "operations.carrier",
                    "update_cap_stations",
                    exc,
                ):
                    raise
                logger.debug("CAP station update failed", exc_info=True)

            # Process carrier units
            _weather_eng_71 = getattr(ctx, "weather_engine", None)
            for _side_name_71, _side_units_71 in units_by_side.items():
                for _cu71 in _side_units_71:
                    _ut71 = getattr(_cu71, "unit_type", "")
                    if not ("carrier" in _ut71.lower() or "cv" in _ut71.lower()):
                        continue
                    if _cu71.status != UnitStatus.ACTIVE:
                        continue
                    # Sea state check — Beaufort > 7 suspends flight ops
                    _sea_state_71 = 0.0
                    if _weather_eng_71 is not None:
                        _sea_state_71 = getattr(
                            getattr(_weather_eng_71, "current", None),
                            "sea_state",
                            0.0,
                        )
                    if _sea_state_71 > 7.0:
                        logger.info(
                            "Carrier %s: flight ops suspended (Beaufort %.0f)",
                            _cu71.entity_id,
                            _sea_state_71,
                        )
                        continue
                    # Count aircraft assigned to this carrier
                    _ac_count_71 = 0
                    for _u71c in _side_units_71:
                        if (
                            getattr(_u71c, "parent_id", None) == _cu71.entity_id
                            and getattr(_u71c, "domain", None) == Domain.AERIAL
                        ):
                            _ac_count_71 += 1
                    from stochastic_warfare.combat.carrier_ops import DeckState

                    _sortie_rate_71 = _carrier_eng_71.compute_sortie_rate(
                        aircraft_available=_ac_count_71,
                        deck_crew_quality=getattr(_cu71, "training_level", 0.7),
                        weather_factor=max(0.0, 1.0 - _sea_state_71 * 0.1),
                        deck_state=DeckState.IDLE,
                    )
                    logger.debug(
                        "Carrier %s sortie rate: %.1f/hr (aircraft=%d)",
                        _cu71.entity_id,
                        _sortie_rate_71,
                        _ac_count_71,
                    )

        # 5. Rebuild enemy data after movement — position arrays from step 1
        #    are stale (captured pre-movement coordinates).  The Unit object
        #    references in active_enemies point to updated positions, but the
        #    numpy arrays are snapshots that must be refreshed.
        active_enemies, enemy_pos_arrays = self._build_enemy_data(units_by_side)

        # Phase 88: Rebuild UnitArrays after movement
        if _unit_arrays is not None:
            _unit_arrays = UnitArrays.from_units(
                units_by_side,
                morale_states=getattr(ctx, "morale_states", None),
                unit_weapons=getattr(ctx, "unit_weapons", None),
            )
            enemy_pos_arrays = {side: _unit_arrays.get_enemy_positions(side) for side in units_by_side}
            self._stage_performance_delta(
                PerformanceReceiptDelta(
                    soa=SoAReceipt(
                        post_movement_builds=1,
                        post_movement_enemy_position_projections=len(
                            units_by_side,
                        ),
                    ),
                ),
            )

        # 6. Engagement — detection + combat
        pending_damage = self._execute_engagements(
            ctx,
            units_by_side,
            active_enemies,
            enemy_pos_arrays,
            dt,
            timestamp,
            _unit_index=_unit_index,
            battle=battle,
        )
        # Include mine damage and missile impact damage
        pending_damage.extend(pending_mine_damage)
        pending_damage.extend(_pending_missile_damage)

        # 7. Apply deferred damage
        self._apply_deferred_damage(pending_damage, ctx.event_bus, timestamp)

        # 7a. Phase 85: instant promotion for damaged units
        if cal_flat.get("enable_lod", False):
            for _pd_entry in pending_damage:
                self._lod_promoted.add(_pd_entry[0].entity_id)

        # 7b. Phase 60b/68e: fire zone damage — apply burn damage to units
        _fz_cal = getattr(getattr(ctx, "config", None), "calibration_overrides", None)
        if _fz_cal is not None and _fz_cal.get("enable_fire_zones", False):
            _inc_eng_fz = getattr(ctx, "incendiary_engine", None)
            if (
                _inc_eng_fz is not None
                and _inc_eng_fz.has_active_fire_zones
            ):
                # Phase 70b: reuse _unit_index for O(1) lookup
                _unit_positions: dict[str, Position] = {
                    uid: u.position for uid, u in _unit_index.items() if u.status == UnitStatus.ACTIVE
                }
                _unit_lookup = _unit_index
                _fire_hits = _inc_eng_fz.units_in_fire(_unit_positions)
                _fire_damage_base = _fz_cal.get("fire_damage_per_tick", 0.01)
                _fire_pending: list[tuple[Unit, UnitStatus, str]] = []
                _fire_dest = _fz_cal.get("destruction_threshold", self._config.destruction_threshold)
                _fire_dis = _fz_cal.get("disable_threshold", self._config.disable_threshold)
                for _fu_id, _burn_rate in _fire_hits.items():
                    _fu_unit = _unit_lookup.get(_fu_id)
                    if _fu_unit is None:
                        continue
                    _fire_dmg = _fire_damage_base * _burn_rate
                    # Posture protection: DUG_IN halves fire damage
                    _fu_posture = getattr(_fu_unit, "posture", None)
                    if _fu_posture is not None and int(_fu_posture) >= 3:
                        _fire_dmg *= 0.5
                    _fire_cas = max(1, int(_fire_dmg * max(1, len(_fu_unit.personnel) if _fu_unit.personnel else 4)))
                    _apply_aggregate_casualties(
                        _fire_cas,
                        _fu_unit,
                        _fire_pending,
                        _fire_dest,
                        _fire_dis,
                        self._cumulative_casualties,
                    )
                    logger.debug("Unit %s fire damage: %.3f (burn_rate=%.3f)", _fu_id, _fire_dmg, _burn_rate)
                if _fire_pending:
                    self._apply_deferred_damage(_fire_pending, ctx.event_bus, timestamp)

        # 7c. Phase 69c: degrade active decoys each tick
        _fow_69c_tick = getattr(ctx, "fog_of_war", None)
        if _fow_69c_tick is not None and cal_flat.get("enable_fog_of_war", False):
            try:
                _fow_69c_tick.update_decoys(dt)
            except (AttributeError, TypeError) as exc:
                if not self._suppress_runtime_failure(
                    "detection.fog_of_war",
                    "update_decoys",
                    exc,
                ):
                    raise
                pass

        # 8. Morale checks
        if battle.ticks_executed % self._config.morale_check_interval == 0:
            self._execute_morale(
                ctx,
                units_by_side,
                active_enemies,
                timestamp,
            )

    # ── Battle termination ──────────────────────────────────────────

    def check_battle_termination(
        self,
        battle: BattleContext,
        units_by_side: dict[str, list[Unit]],
    ) -> bool:
        """Check if a battle should terminate.

        A battle ends when:
        - One side has no active units
        - Max ticks exceeded
        - All opposing forces are out of engagement range
        """
        if not battle.active:
            return True

        if battle.ticks_executed >= self._config.max_ticks_per_battle:
            battle.active = False
            return True

        for side in battle.involved_sides:
            units = units_by_side.get(side, [])
            active = [u for u in units if u.status == UnitStatus.ACTIVE]
            if not active:
                battle.active = False
                return True

        # Check if forces are still in range
        sides = battle.involved_sides
        if len(sides) >= 2:
            active_a = [u for u in units_by_side.get(sides[0], []) if u.status == UnitStatus.ACTIVE]
            active_b = [u for u in units_by_side.get(sides[1], []) if u.status == UnitStatus.ACTIVE]
            if active_a and active_b:
                min_dist = self._min_distance(active_a, active_b)
                if min_dist > self._config.engagement_range_m * 2.0:
                    battle.active = False
                    return True

        return False

    def resolve_battle(
        self,
        battle: BattleContext,
        units_by_side: dict[str, list[Unit]],
        *,
        ctx: Any | None = None,
    ) -> BattleResult:
        """Finalize a terminated battle and produce a result."""
        deferred_unit_ids = sorted(
            unit_id
            for unit_id, battle_id in self._deferred_battle_ids.items()
            if battle_id == battle.battle_id
        )
        if deferred_unit_ids:
            if ctx is None:
                raise RuntimeError(
                    "Resolving a battle with deferred OODA decisions requires "
                    "the simulation context",
                )
            if ctx.ooda_engine is None:
                raise RuntimeError(
                    "Deferred OODA decisions require an active OODA engine",
                )
            tactical_mult = ctx.ooda_engine.tactical_acceleration
            timestamp = ctx.clock.current_time
            for unit_id in deferred_unit_ids:
                was_propagated = unit_id in self._pending_decisions
                if was_propagated:
                    record = self._pop_deferred_decision(unit_id)
                else:
                    record = None
                    self._deferred_battle_ids.pop(unit_id, None)
                if was_propagated and record is None:
                    raise RuntimeError(
                        f"Deferred OODA decision {unit_id!r} disappeared during cancellation",
                    )
                planning_engine = getattr(ctx, "planning_engine", None)
                if planning_engine is not None:
                    planning_engine.cancel_planning(unit_id)
                school = (
                    ctx.school_registry.get_for_unit(unit_id)
                    if ctx.school_registry is not None
                    else None
                )
                self._advance_ooda_completion(
                    ctx,
                    unit_id=unit_id,
                    school=school,
                    tactical_mult=tactical_mult,
                    timestamp=timestamp,
                )
                logger.debug(
                    "Cancelled %s OODA decision for %s as battle %s resolved",
                    "propagated" if record is not None else "planning",
                    unit_id,
                    battle.battle_id,
                )
        battle.active = False
        destroyed: dict[str, int] = {}
        routing: dict[str, int] = {}

        for side in battle.involved_sides:
            units = units_by_side.get(side, [])
            destroyed[side] = sum(1 for u in units if u.status == UnitStatus.DESTROYED)
            routing[side] = sum(1 for u in units if u.status == UnitStatus.ROUTING)

        terminated_by = "force_destroyed"
        for side in battle.involved_sides:
            active = [u for u in units_by_side.get(side, []) if u.status == UnitStatus.ACTIVE]
            if not active:
                terminated_by = f"force_destroyed_{side}"
                break
        else:
            if battle.ticks_executed >= self._config.max_ticks_per_battle:
                terminated_by = "max_ticks"
            else:
                terminated_by = "disengaged"

        return BattleResult(
            battle_id=battle.battle_id,
            duration_ticks=battle.ticks_executed,
            terminated_by=terminated_by,
            units_destroyed=destroyed,
            units_routing=routing,
        )

    # ── Auto-resolve (Phase 13a-6) ──────────────────────────────────

    def auto_resolve(
        self,
        battle: BattleContext,
        units_by_side: dict[str, list[Unit]],
        rng: np.random.Generator,
        morale_states: Mapping[str, MoraleState] | None = None,
        supply_states: Mapping[str, float] | None = None,
    ) -> AutoResolveResult:
        """Auto-resolve a minor battle using simplified Lanchester attrition.

        Adapted from c2/planning/coa.py::wargame_coa.  Computes aggregate
        combat power per side, runs 10 steps of Lanchester attrition,
        and applies losses to individual units.

        Parameters
        ----------
        battle : BattleContext
            The battle to resolve.
        units_by_side : dict
            Current force disposition.
        rng : np.random.Generator
            PRNG stream for loss distribution.
        morale_states : Mapping[str, MoraleState] | None
            Per-unit morale states for morale factor.
        supply_states : Mapping[str, float] | None
            Per-unit supply levels for supply factor.
        """
        battle.active = False
        sides = battle.involved_sides
        if len(sides) < 2:
            return AutoResolveResult(
                battle_id=battle.battle_id,
                winner=sides[0] if sides else "",
            )

        # Compute per-side combat power
        side_power: dict[str, float] = {}
        side_units_active: dict[str, list[Unit]] = {}
        for side in sides:
            units = [u for u in units_by_side.get(side, []) if u.status == UnitStatus.ACTIVE]
            side_units_active[side] = units
            power = 0.0
            for u in units:
                personnel = len(u.personnel) if u.personnel else 4
                equipment = len(u.equipment) if u.equipment else 1
                power += personnel + equipment * 2.0
            side_power[side] = power

        # Apply morale and supply factors
        for side in sides:
            morale_factor = 1.0
            supply_factor = 1.0
            if morale_states:
                side_morale_vals = [morale_states.get(u.entity_id, MoraleState.STEADY) for u in side_units_active[side]]
                if side_morale_vals:
                    avg_morale = sum(int(m) for m in side_morale_vals) / len(side_morale_vals)
                    morale_factor = max(0.3, 1.0 - avg_morale * 0.15)
            if supply_states:
                side_supply = [supply_states.get(u.entity_id, 1.0) for u in side_units_active[side]]
                if side_supply:
                    avg_supply = sum(side_supply) / len(side_supply)
                    supply_factor = max(0.5, avg_supply)
            side_power[side] *= morale_factor * supply_factor

        # Lanchester attrition loop (10 steps, exponent 0.5)
        power = {s: float(side_power[s]) for s in sides}
        initial_power = {s: float(side_power[s]) for s in sides}
        exponent = 0.5
        steps = 10

        for _ in range(steps):
            if any(power[s] <= 0 for s in sides):
                break
            losses: dict[str, float] = {}
            for s in sides:
                enemy_sides = [o for o in sides if o != s]
                enemy_power = sum(power[o] for o in enemy_sides)
                own_power = max(power[s], 1e-10)
                loss_rate = 0.02 * (enemy_power**exponent / own_power**exponent)
                losses[s] = power[s] * loss_rate
            for s in sides:
                power[s] = max(0.0, power[s] - losses[s])

        # Compute loss fractions
        side_losses: dict[str, float] = {}
        for s in sides:
            if initial_power[s] > 0:
                side_losses[s] = 1.0 - power[s] / initial_power[s]
            else:
                side_losses[s] = 1.0

        # Determine winner (side with most remaining power)
        winner = max(sides, key=lambda s: power[s])

        # Apply losses to units
        for side in sides:
            loss_frac = side_losses[side]
            active = side_units_active[side]
            if not active:
                continue
            # Distribute losses randomly across active units
            num_to_destroy = int(round(loss_frac * len(active)))
            if num_to_destroy > 0:
                indices = list(range(len(active)))
                rng.shuffle(indices)
                for i in indices[:num_to_destroy]:
                    unit = active[i]
                    object.__setattr__(unit, "status", UnitStatus.DESTROYED)
                    self._bus.publish(
                        UnitDestroyedEvent(
                            timestamp=datetime.min,
                            source=ModuleId.COMBAT,
                            unit_id=unit.entity_id,
                            cause="auto_resolve",
                            side=unit.side,
                        )
                    )

        # Estimate duration (shorter for one-sided battles)
        power_ratio = max(power.values()) / max(sum(power.values()), 1e-10)
        duration_s = 3600.0 * (1.0 - power_ratio * 0.5)  # 30min to 1hr

        logger.info(
            "Auto-resolved %s: winner=%s, losses=%s",
            battle.battle_id,
            winner,
            {s: f"{l:.1%}" for s, l in side_losses.items()},
        )

        return AutoResolveResult(
            battle_id=battle.battle_id,
            winner=winner,
            side_losses=side_losses,
            duration_s=duration_s,
        )

    # ── State persistence ───────────────────────────────────────────

    @staticmethod
    def _assessment_state(
        assessment: SituationAssessment,
    ) -> dict[str, Any]:
        """Compatibility delegation for pre-extraction checkpoint callers."""
        from stochastic_warfare.simulation.battle_checkpoint_executor import (
            DefaultBattleCheckpointExecutor,
        )

        return DefaultBattleCheckpointExecutor._assessment_state(assessment)

    def _deferred_decision(
        self,
        unit_id: str,
    ) -> DeferredOODADecision | None:
        """Return the complete typed deferred record for ``unit_id``.

        Markerless checkpoint migration is handled during staging.  Live and
        current-schema state must already own the exact one-shot propagation
        result so a retry cannot silently repeat C2 work.
        """
        due_elapsed_s = self._pending_decisions.get(unit_id)
        if due_elapsed_s is None:
            return None
        battle_id = self._deferred_battle_ids.get(unit_id)
        if battle_id is None:
            raise RuntimeError(
                f"Deferred OODA decision {unit_id!r} has no battle owner",
            )
        propagation = self._misinterpreted_orders.get(unit_id)
        if propagation is None:
            raise RuntimeError(
                f"Deferred OODA decision {unit_id!r} has no propagation record",
            )
        return DeferredOODADecision(
            unit_id=unit_id,
            battle_id=battle_id,
            due_elapsed_s=due_elapsed_s,
            propagation=propagation,
        )

    def _queue_deferred_decision(
        self,
        *,
        unit_id: str,
        battle: BattleContext | BattleIntervalView,
        logical_time_s: float,
        propagation: PropagationResult,
    ) -> DeferredOODADecision:
        """Commit one complete one-shot decision delay without new RNG work."""
        if not math.isfinite(logical_time_s) or logical_time_s < 0.0:
            raise ValueError(
                "Deferred decision logical time must be finite and non-negative",
            )
        if not isinstance(propagation, PropagationResult) or not propagation.success:
            raise ValueError(
                "Only a successful typed propagation result may be deferred",
            )
        delay_s = float(propagation.total_delay_s)
        if not math.isfinite(delay_s) or delay_s <= 0.0:
            raise ValueError("Deferred decision delay must be finite and positive")
        # A timing misunderstanding extends the original delay once.  Encoding
        # that extension up front avoids a second, ambiguous queue transition
        # and makes checkpoint continuation exact.
        if (
            propagation.was_misinterpreted
            and propagation.misinterpretation_type == "timing"
        ):
            delay_s *= 2.0
        self._bind_deferred_ooda_owner(unit_id=unit_id, battle=battle)
        record = DeferredOODADecision(
            unit_id=unit_id,
            battle_id=battle.battle_id,
            due_elapsed_s=logical_time_s + delay_s,
            propagation=copy.deepcopy(propagation),
        )
        self._pending_decisions[unit_id] = record.due_elapsed_s
        self._misinterpreted_orders[unit_id] = record.propagation
        return record

    def _bind_deferred_ooda_owner(
        self,
        *,
        unit_id: str,
        battle: BattleContext | BattleIntervalView,
    ) -> None:
        """Bind an expired DECIDE completion to one active battle roster."""
        if not battle.active or unit_id not in battle.unit_ids:
            raise ValueError(
                "Deferred decision owner must be an active battle roster member",
            )
        active_owners = [
            candidate.battle_id
            for candidate in self._battles.values()
            if candidate.active and unit_id in candidate.unit_ids
        ]
        if active_owners and active_owners != [battle.battle_id]:
            raise RuntimeError(
                "Deferred decision owner disagrees with active battle topology: "
                f"unit={unit_id!r}, owners={active_owners!r}",
            )
        existing_owner = self._deferred_battle_ids.get(unit_id)
        if existing_owner is not None and existing_owner != battle.battle_id:
            raise RuntimeError(
                "OODA commander already owns a deferred decision: "
                f"unit={unit_id!r}, battle={existing_owner!r}",
            )
        self._deferred_battle_ids[unit_id] = battle.battle_id

    def _pop_deferred_decision(
        self,
        unit_id: str,
    ) -> DeferredOODADecision | None:
        """Atomically remove and return a complete deferred decision."""
        record = self._deferred_decision(unit_id)
        if record is None:
            return None
        self._pending_decisions.pop(unit_id, None)
        self._misinterpreted_orders.pop(unit_id, None)
        self._deferred_battle_ids.pop(unit_id, None)
        return record

    @property
    def deferred_ooda_decisions(self) -> tuple[DeferredOODADecision, ...]:
        """Expose the canonical deferred queue in deterministic identity order."""
        return tuple(
            record
            for unit_id in sorted(self._pending_decisions)
            if (record := self._deferred_decision(unit_id)) is not None
        )

    def get_state(self) -> dict[str, object]:
        """Capture state through the injected checkpoint executor."""
        return self._checkpoint_executor.get_state(self._executor_owner)

    def stage_state(
        self,
        state: Mapping[str, CheckpointValue],
        *,
        allow_legacy: bool = False,
        expected_unit_ids: set[str] | None = None,
        expected_sides: set[str] | None = None,
        required_assessment_ids: set[str] | None = None,
        checkpoint_time: datetime | None = None,
        checkpoint_elapsed_s: float | None = None,
        deferred_ooda_ids: set[str] | None = None,
    ) -> BattleStatePlan:
        """Validate state through the injected checkpoint executor."""
        return self._checkpoint_executor.stage_state(
            self._executor_owner,
            BattleCheckpointStageRequest(
                state=state,
                allow_legacy=allow_legacy,
                expected_unit_ids=expected_unit_ids,
                expected_sides=expected_sides,
                required_assessment_ids=required_assessment_ids,
                checkpoint_time=checkpoint_time,
                checkpoint_elapsed_s=checkpoint_elapsed_s,
                deferred_ooda_ids=deferred_ooda_ids,
            ),
        )

    def _apply_checkpoint_plan(self, plan: BattleStatePlan) -> None:
        """Commit a fully validated tactical checkpoint plan."""
        if plan.owner_id != id(self):
            raise ValueError(
                "Battle checkpoint plan belongs to another manager",
            )
        self._battles = copy.deepcopy(plan.battles)
        self._next_battle_id = plan.next_battle_id
        self._vls_launches = dict(plan.vls_launches)
        self._ammo_expended = dict(plan.ammo_expended)
        self._pending_decisions = dict(plan.pending_decisions)
        self._deferred_battle_ids = dict(plan.deferred_battle_ids)
        self._cached_assessments = dict(plan.cached_assessments)
        self._ticks_stationary = dict(plan.ticks_stationary)
        self._suppression_states = copy.deepcopy(
            plan.suppression_states,
        )
        self._cumulative_casualties = dict(
            plan.cumulative_casualties,
        )
        self._undigging = dict(plan.undigging)
        self._concealment_scores = dict(plan.concealment_scores)
        self._env_casualty_accum = dict(plan.env_casualty_accum)
        self._misinterpreted_orders = copy.deepcopy(
            plan.misinterpreted_orders,
        )
        self._lod_tiers = dict(plan.lod_tiers)
        self._lod_pending_tiers = dict(plan.lod_pending_tiers)
        self._lod_pending_counts = dict(plan.lod_pending_counts)
        self._lod_promoted = set(plan.lod_promoted)
        self._fow_observer_unit_ids = frozenset(
            plan.fow_observer_unit_ids,
        )
        self._performance_receipts.commit_state(
            self,
            plan.performance_execution_receipt,
        )

    def commit_state(self, plan: BattleStatePlan) -> None:
        """Commit state through the injected checkpoint executor."""
        self._checkpoint_executor.commit_state(
            self._executor_owner,
            plan,
        )

    def set_state(
        self,
        state: Mapping[str, CheckpointValue],
        *,
        allow_legacy: bool = False,
    ) -> None:
        """Restore state through the injected checkpoint executor."""
        self._checkpoint_executor.set_state(
            self._executor_owner,
            state,
            allow_legacy=allow_legacy,
        )

    @property
    def active_battles(self) -> list[BattleContext]:
        """Return all currently active battles."""
        return [battle for _, battle in sorted(self._battles.items()) if battle.active]

    # ── Private helpers ─────────────────────────────────────────────

    @staticmethod
    def _min_distance(units_a: list[Unit], units_b: list[Unit]) -> float:
        """Compute minimum distance between any pair of units."""
        if not units_a or not units_b:
            return float("inf")
        pos_a = np.array(
            [(u.position.easting, u.position.northing) for u in units_a],
            dtype=np.float64,
        )
        pos_b = np.array(
            [(u.position.easting, u.position.northing) for u in units_b],
            dtype=np.float64,
        )
        # Broadcast distance computation
        diffs = pos_a[:, np.newaxis, :] - pos_b[np.newaxis, :, :]
        dists = np.sqrt(np.sum(diffs * diffs, axis=2))
        return float(np.min(dists))

    def _stage_lod_tiers(
        self,
        ctx: Any,
        units_by_side: dict[str, list[Unit]],
        enemy_pos_arrays: dict[str, np.ndarray],
        *,
        active_enemies: dict[str, list[Unit]] | None = None,
    ) -> _LODClassificationPlan:
        """Stage LOD classification without mutating Battle-owned state."""
        cal_flat = _resolve_cal_flat(ctx)
        lod_tiers = dict(self._lod_tiers)
        pending_tiers = dict(self._lod_pending_tiers)
        pending_counts = dict(self._lod_pending_counts)
        promoted_unit_ids = frozenset(self._lod_promoted)
        if not cal_flat.get("enable_lod", False):
            active_units = {u.entity_id for su in units_by_side.values() for u in su if u.status == UnitStatus.ACTIVE}
            return _LODClassificationPlan(
                lod_tiers=lod_tiers,
                pending_tiers=pending_tiers,
                pending_counts=pending_counts,
                receipt=LODReceipt(
                    active_classifications=len(active_units),
                ),
            )

        hysteresis = cal_flat.get("lod_hysteresis_ticks", 3)
        classification_counts = {
            UnitLodTier.ACTIVE: 0,
            UnitLodTier.NEARBY: 0,
            UnitLodTier.DISTANT: 0,
        }

        for side_name, side_units in units_by_side.items():
            pos_arr = enemy_pos_arrays.get(side_name, np.empty((0, 2)))
            enemy_positions_by_domain: dict[Domain, np.ndarray] = {}
            if active_enemies is not None:
                positions: dict[Domain, list[tuple[float, float]]] = {}
                for enemy in active_enemies.get(side_name, ()):
                    positions.setdefault(enemy.domain, []).append(
                        (
                            enemy.position.easting,
                            enemy.position.northing,
                        )
                    )
                enemy_positions_by_domain = {
                    domain: np.asarray(points, dtype=np.float64) for domain, points in positions.items()
                }

            for u in side_units:
                if u.status != UnitStatus.ACTIVE:
                    continue
                uid = u.entity_id

                # 1. Compute raw tier from distance to nearest enemy
                if uid in promoted_unit_ids:
                    raw_tier = UnitLodTier.ACTIVE
                elif pos_arr.shape[0] == 0:
                    raw_tier = UnitLodTier.DISTANT
                elif active_enemies is not None:
                    # Phase 109: only a weapon/sensor whose live mapping
                    # permits a concrete enemy domain can promote update
                    # cadence. An air-search radar must not make an unrelated
                    # ground battle run at the nearby tier.
                    raw_tier = UnitLodTier.DISTANT
                    weapons = ctx.unit_weapons.get(uid, ())
                    sensors = ctx.unit_sensors.get(uid, ())
                    weapon_ranges = {
                        domain: max(
                            (
                                attachment[0].definition.max_range_m
                                for attachment in weapons
                                if _weapon_supports_domain(
                                    attachment[0].definition,
                                    domain,
                                )
                            ),
                            default=0.0,
                        )
                        for domain in enemy_positions_by_domain
                    }
                    sensor_ranges = {
                        domain: max(
                            (
                                sensor.effective_range
                                for sensor in sensors
                                if (
                                    sensor.operational
                                    and sensor.sensor_type is not SensorType.ESM
                                    and sensor.supports_target_domain(domain)
                                )
                            ),
                            default=0.0,
                        )
                        for domain in enemy_positions_by_domain
                    }
                    unit_position = np.asarray(
                        [u.position.easting, u.position.northing],
                        dtype=np.float64,
                    )
                    for domain, domain_positions in enemy_positions_by_domain.items():
                        offsets = domain_positions - unit_position
                        nearest_distance_sq = float(
                            np.min(
                                np.sum(offsets * offsets, axis=1),
                            )
                        )
                        active_threshold = max(
                            weapon_ranges[domain] * 2.0,
                            100.0,
                        )
                        nearby_threshold = max(
                            sensor_ranges[domain],
                            active_threshold,
                        )
                        if nearest_distance_sq <= active_threshold**2:
                            raw_tier = UnitLodTier.ACTIVE
                            break
                        if nearest_distance_sq <= nearby_threshold**2 and raw_tier is UnitLodTier.DISTANT:
                            raw_tier = UnitLodTier.NEARBY
                else:
                    upos = np.array([u.position.easting, u.position.northing])
                    diffs = pos_arr - upos
                    nearest_dist = float(np.sqrt(np.min(np.sum(diffs * diffs, axis=1))))

                    # Max weapon range for ACTIVE threshold
                    max_wpn = max(
                        (w[0].definition.max_range_m for w in ctx.unit_weapons.get(uid, [])),
                        default=0.0,
                    )
                    # Max sensor range for NEARBY threshold
                    max_sensor = max(
                        (s.effective_range for s in ctx.unit_sensors.get(uid, [])),
                        default=0.0,
                    )

                    active_thresh = max(max_wpn * 2.0, 100.0)
                    nearby_thresh = max(max_sensor, active_thresh)

                    if nearest_dist <= active_thresh:
                        raw_tier = UnitLodTier.ACTIVE
                    elif nearest_dist <= nearby_thresh:
                        raw_tier = UnitLodTier.NEARBY
                    else:
                        raw_tier = UnitLodTier.DISTANT

                # 2. Apply hysteresis (immediate promotion, delayed demotion)
                is_new = uid not in lod_tiers
                current = lod_tiers.get(uid, UnitLodTier.ACTIVE)
                if is_new:  # first classification — assign directly
                    final = raw_tier
                elif raw_tier < current:  # promotion (lower tier value = higher priority)
                    final = raw_tier
                    pending_tiers.pop(uid, None)
                    pending_counts.pop(uid, None)
                elif raw_tier > current:  # demotion
                    if pending_tiers.get(uid) == raw_tier:
                        count = pending_counts.get(uid, 0) + 1
                        pending_counts[uid] = count
                        final = raw_tier if count >= hysteresis else current
                        if count >= hysteresis:
                            pending_tiers.pop(uid, None)
                            pending_counts.pop(uid, None)
                    else:
                        pending_tiers[uid] = raw_tier
                        pending_counts[uid] = 1
                        final = current
                else:
                    final = raw_tier
                    pending_tiers.pop(uid, None)
                    pending_counts.pop(uid, None)

                lod_tiers[uid] = final
                classification_counts[UnitLodTier(final)] += 1

        return _LODClassificationPlan(
            lod_tiers=lod_tiers,
            pending_tiers=pending_tiers,
            pending_counts=pending_counts,
            receipt=LODReceipt(
                active_classifications=(classification_counts[UnitLodTier.ACTIVE]),
                nearby_classifications=(classification_counts[UnitLodTier.NEARBY]),
                distant_classifications=(classification_counts[UnitLodTier.DISTANT]),
            ),
        )

    @staticmethod
    def _validate_lod_publication(
        plan: _LODClassificationPlan,
        *,
        witness_promoted_unit_ids: Collection[str] = (),
    ) -> frozenset[str]:
        """Validate next-interval witness promotions without publication."""
        if type(plan) is not _LODClassificationPlan:
            raise TypeError("LOD classification plan has the wrong type")
        promoted = frozenset(witness_promoted_unit_ids)
        if any(type(unit_id) is not str or not unit_id or unit_id != unit_id.strip() for unit_id in promoted):
            raise ValueError(
                "Witness-promoted LOD unit IDs must be non-empty trimmed strings",
            )
        if not promoted <= set(plan.lod_tiers):
            raise ValueError(
                "Witness-promoted LOD units are absent from the staged classification",
            )
        return promoted

    def _commit_lod_tiers(
        self,
        plan: _LODClassificationPlan,
        *,
        witness_promoted_unit_ids: frozenset[str],
    ) -> None:
        """Publish one fully prevalidated Battle-owned LOD plan."""
        lod_tiers = dict(plan.lod_tiers)
        pending_tiers = dict(plan.pending_tiers)
        pending_counts = dict(plan.pending_counts)
        for unit_id in witness_promoted_unit_ids:
            lod_tiers[unit_id] = UnitLodTier.ACTIVE
            pending_tiers.pop(unit_id, None)
            pending_counts.pop(unit_id, None)
        self._lod_tiers = lod_tiers
        self._lod_pending_tiers = pending_tiers
        self._lod_pending_counts = pending_counts
        # Damage after observation may populate this set for the next staged
        # interval.  Witness promotions are already reflected in both the
        # Battle tier map and the scheduler's staged period mirror.
        self._lod_promoted = set()

    def _publish_lod_tiers(
        self,
        plan: _LODClassificationPlan,
        *,
        witness_promoted_unit_ids: Collection[str] = (),
    ) -> None:
        """Validate and publish the compatibility LOD boundary."""
        promoted = self._validate_lod_publication(
            plan,
            witness_promoted_unit_ids=witness_promoted_unit_ids,
        )
        self._stage_performance_delta(
            PerformanceReceiptDelta(lod=plan.receipt),
        )
        self._commit_lod_tiers(
            plan,
            witness_promoted_unit_ids=promoted,
        )

    def _classify_lod_tiers(
        self,
        ctx: Any,
        units_by_side: dict[str, list[Unit]],
        enemy_pos_arrays: dict[str, np.ndarray],
        *,
        active_enemies: dict[str, list[Unit]] | None = None,
    ) -> None:
        """Compatibility publication around the staged LOD authority."""
        plan = self._stage_lod_tiers(
            ctx,
            units_by_side,
            enemy_pos_arrays,
            active_enemies=active_enemies,
        )
        self._publish_lod_tiers(plan)

    @staticmethod
    def _build_enemy_data(
        units_by_side: dict[str, list[Unit]],
    ) -> tuple[dict[str, list[Unit]], dict[str, np.ndarray]]:
        """Pre-build per-side active enemy lists and position arrays."""
        active_enemies: dict[str, list[Unit]] = {}
        enemy_pos_arrays: dict[str, np.ndarray] = {}

        for side in units_by_side:
            enemies: list[Unit] = []
            for other_side, other_units in units_by_side.items():
                if other_side != side:
                    enemies.extend(u for u in other_units if u.status == UnitStatus.ACTIVE)
            active_enemies[side] = enemies
            if enemies:
                enemy_pos_arrays[side] = np.array(
                    [(e.position.easting, e.position.northing) for e in enemies],
                    dtype=np.float64,
                )
            else:
                enemy_pos_arrays[side] = np.empty((0, 2), dtype=np.float64)

        return active_enemies, enemy_pos_arrays

    def _advance_ooda_completion(
        self,
        ctx: BattleOODARuntime,
        *,
        unit_id: str,
        school: DoctrinalSchool | None,
        tactical_mult: float,
        timestamp: datetime,
    ) -> None:
        """Acknowledge one completion and start its next stochastic phase."""
        if ctx.ooda_engine is None:
            return
        effective_mult = tactical_mult
        if school is not None:
            effective_mult *= school.get_ooda_multiplier()
        if ctx.commander_engine is not None:
            effective_mult *= ctx.commander_engine.get_ooda_speed_multiplier(
                unit_id,
            )
        next_phase = ctx.ooda_engine.advance_phase(unit_id)
        ctx.ooda_engine.start_phase(
            unit_id,
            next_phase,
            tactical_mult=effective_mult,
            ts=timestamp,
        )
        self._deferred_battle_ids.pop(unit_id, None)

    def _propagate_ooda_decision(
        self,
        ctx: BattleOODARuntime,
        *,
        unit_id: str,
        timestamp: datetime,
    ) -> PropagationResult | None:
        """Run the one-shot propagation work for a new DECIDE completion."""
        propagation_engine = ctx.order_propagation
        if propagation_engine is None:
            return None
        calibration = ctx.cal_flat
        if not calibration.get("enable_c2_friction", False):
            logger.debug("Order propagation available for %s", unit_id)
            return None

        from stochastic_warfare.c2.orders.types import (
            Order,
            OrderPriority,
            OrderType,
        )

        order = Order(
            order_id=f"decide_{unit_id}_{timestamp}",
            issuer_id=unit_id,
            recipient_id=unit_id,
            timestamp=timestamp,
            order_type=OrderType.FRAGO,
            echelon_level=5,
            priority=OrderPriority.PRIORITY,
            mission_type=0,
        )
        sender_position = _get_unit_position(ctx, unit_id)
        side = self._find_unit_side(ctx, unit_id)
        c2_effectiveness = (
            self._compute_c2_effectiveness(
                ctx,
                unit_id,
                side,
                failure_handler=self._suppress_runtime_failure,
            )
            if side
            else 1.0
        )
        friction_scale = max(0.0, 1.0 - c2_effectiveness)
        overrides = PropagationOverrides(
            delay_sigma=(
                calibration.get("order_propagation_delay_sigma", 0.4)
                * friction_scale
            ),
            base_misinterpretation=(
                calibration.get("order_misinterpretation_base", 0.05)
                * friction_scale
            ),
        )
        try:
            result = propagation_engine.propagate_order(
                order,
                sender_position,
                sender_position,
                timestamp,
                overrides=overrides,
            )
        except Exception:
            logger.exception("Order propagation error for %s", unit_id)
            raise
        if not isinstance(result, PropagationResult):
            raise TypeError("Order propagation must return PropagationResult")
        return result

    def _process_ooda_completions(
        self,
        ctx: SimulationContext,
        completions: Collection[tuple[str, OODAPhase]],
        timestamp: datetime,
        *,
        battle: BattleContext | None = None,
        battle_tick: int | None = None,
    ) -> None:
        """Compatibility delegation to the injected OODA executor."""
        self._ooda_executor.process_completions(
            self._executor_owner,
            OODACompletionRequest(
                runtime=self._build_ooda_runtime(ctx),
                completions=tuple(completions),
                timestamp=timestamp,
                battle=(
                    None
                    if battle is None
                    else BattleIntervalView.from_battle(battle)
                ),
                battle_tick=battle_tick,
            ),
        )

    @staticmethod
    def _apply_behavior_rules(
        units_by_side: dict[str, list[Unit]],
        active_enemies: dict[str, list[Unit]],
        behavior_rules: dict[str, Any],
    ) -> None:
        """Set unit speeds from scenario behavior_rules (pre-scripted behavior).

        Mirrors :func:`~stochastic_warfare.legacy.validation.scenario_runner.apply_behavior`.
        For each side, reads ``advance_speed_mps`` or ``hold_position`` and
        sets ``speed`` on active units accordingly.
        """
        for side, units in units_by_side.items():
            rules = behavior_rules.get(side, {})
            if rules.get("hold_position", False):
                for u in units:
                    if u.status == UnitStatus.ACTIVE:
                        object.__setattr__(u, "speed", 0.0)
                continue

            advance_speed = rules.get("advance_speed_mps", 0.0)
            if advance_speed > 0:
                for u in units:
                    if u.status == UnitStatus.ACTIVE:
                        object.__setattr__(u, "speed", advance_speed)

    def _execute_movement(
        self,
        ctx: SimulationContext,
        units_by_side: Mapping[str, Sequence[Unit]],
        active_enemies: Mapping[str, Sequence[Unit]],
        dt: float,
        battle: BattleContext | None = None,
        behavior_rules: Mapping[str, ReadonlyValue] | None = None,
        enemy_pos_arrays: Mapping[str, np.ndarray] | None = None,
    ) -> None:
        """Compatibility delegation to the injected movement executor."""
        self._movement_executor.execute(
            self._executor_owner,
            MovementExecutionRequest(
                runtime=self._build_movement_runtime(ctx, units_by_side),
                units_by_side=units_by_side,
                active_enemies=active_enemies,
                dt_seconds=dt,
                battle=(
                    None
                    if battle is None
                    else BattleIntervalView.from_battle(battle)
                ),
                behavior_rules=behavior_rules,
                enemy_position_arrays=enemy_pos_arrays,
            ),
        )

    # ------------------------------------------------------------------
    # Phase 41a: Terrain combat modifiers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_terrain_modifiers(
        ctx: Any,
        target_pos: Position,
        attacker_pos: Position,
        *,
        elevation_cap: float = 0.3,
        elevation_floor: float = -0.1,
        seasonal_vegetation: float = 0.0,
        failure_handler: BattleRuntimeFailureHandler | None = None,
    ) -> tuple[float, float, float]:
        """Query terrain at positions and return (cover, elevation_mod, concealment).

        Returns defaults (0.0, 1.0, 0.0) when terrain managers are absent.
        """
        cover = 0.0
        elevation_mod = 1.0
        concealment = 0.0

        # 1. Terrain classification cover & concealment
        classification = getattr(ctx, "classification", None)
        if classification is not None:
            try:
                props = classification.properties_at(target_pos)
                cover = max(cover, props.cover)
                concealment = props.concealment
                # Phase 59b: seasonal vegetation concealment bonus
                if seasonal_vegetation > 0:
                    _lc_name = getattr(
                        getattr(props, "land_cover", None),
                        "name",
                        "",
                    )
                    if "FOREST" in _lc_name or "SHRUB" in _lc_name:
                        concealment = min(1.0, concealment + seasonal_vegetation * 0.3)
            except (IndexError, ValueError, AttributeError) as exc:
                if failure_handler is not None and not failure_handler(
                    "terrain.classification",
                    "resolve_seasonal_concealment",
                    exc,
                ):
                    raise
                pass

        # 2. Trench cover (WW1+)
        trench_engine = getattr(ctx, "trench_engine", None)
        if trench_engine is not None:
            try:
                tq = trench_engine.query_trench(target_pos.easting, target_pos.northing)
                if tq.in_trench:
                    cover = max(cover, tq.cover_value)
            except (IndexError, ValueError, AttributeError) as exc:
                if failure_handler is not None and not failure_handler(
                    "terrain.trenches",
                    "query_cover",
                    exc,
                ):
                    raise
                pass

        # 3. Building cover
        infra = getattr(ctx, "infrastructure_manager", None)
        if infra is not None:
            try:
                buildings = infra.buildings_at(target_pos)
                for b in buildings:
                    cover = max(cover, getattr(b, "cover_value", 0.0))
            except (IndexError, ValueError, AttributeError) as exc:
                if failure_handler is not None and not failure_handler(
                    "terrain.infrastructure",
                    "buildings_at",
                    exc,
                ):
                    raise
                pass

        # 4. Obstacle fortification cover
        obstacle_mgr = getattr(ctx, "obstacle_manager", None)
        if obstacle_mgr is not None:
            try:
                obstacles = obstacle_mgr.obstacles_at(target_pos)
                for obs in obstacles:
                    if hasattr(obs, "obstacle_type"):
                        ot_name = (
                            obs.obstacle_type.name if hasattr(obs.obstacle_type, "name") else str(obs.obstacle_type)
                        )
                        if ot_name == "FORTIFICATION":
                            cover = max(cover, 0.8)
            except (IndexError, ValueError, AttributeError) as exc:
                if failure_handler is not None and not failure_handler(
                    "terrain.obstacles",
                    "resolve_fortification_cover",
                    exc,
                ):
                    raise
                pass

        # 5. Elevation advantage
        heightmap = getattr(ctx, "heightmap", None)
        if heightmap is not None:
            try:
                att_elev = heightmap.elevation_at(attacker_pos)
                tgt_elev = heightmap.elevation_at(target_pos)
                delta = att_elev - tgt_elev
                # +10% per 33m height advantage, configurable cap/floor
                raw = delta / 330.0
                elevation_mod = 1.0 + max(elevation_floor, min(elevation_cap, raw))
            except (IndexError, ValueError) as exc:
                if failure_handler is not None and not failure_handler(
                    "terrain.heightmap",
                    "resolve_elevation_modifier",
                    exc,
                ):
                    raise
                pass

        # 6. Phase 69e: Burned zone concealment reduction
        _inc_eng_69e = getattr(ctx, "incendiary_engine", None)
        if _inc_eng_69e is not None:
            try:
                for _bz in _inc_eng_69e.get_burned_zones():
                    _dx = target_pos.easting - _bz.center.easting
                    _dy = target_pos.northing - _bz.center.northing
                    if _dx * _dx + _dy * _dy <= _bz.radius_m * _bz.radius_m:
                        concealment = max(0.0, concealment - _bz.concealment_reduction)
            except (AttributeError, TypeError) as exc:
                if failure_handler is not None and not failure_handler(
                    "combat.incendiary",
                    "resolve_burned_zone_concealment",
                    exc,
                ):
                    raise
                pass

        return cover, elevation_mod, concealment

    # ------------------------------------------------------------------
    # Phase 41c: Threat-based target scoring
    # ------------------------------------------------------------------

    def _score_target(
        self,
        attacker: Unit,
        target: Unit,
        distance: float,
        attacker_weapons: list,
        ctx: Any,
    ) -> float:
        """Compute threat-based target score. Higher = more attractive."""
        # Threat: target's ability to damage us
        target_weapons = ctx.unit_weapons.get(target.entity_id, [])
        target_max_range = _max_weapon_range_for_domain(
            target_weapons,
            getattr(attacker, "domain", None),
        )
        attacker_armor = getattr(attacker, "armor_front", 0.0)
        threat = min(5.0, max(0.1, target_max_range / max(1.0, attacker_armor * 10.0)))

        # Pk: our hit likelihood at this range
        best_wpn_range = _max_weapon_range_for_domain(
            attacker_weapons,
            getattr(target, "domain", None),
        )
        if best_wpn_range <= 0.0:
            best_wpn_range = 1_000.0
        pk = min(3.0, best_wpn_range / max(1.0, distance))

        # Value: target type priority (configurable weights)
        # Phase 50e: calibration can override BattleConfig target weights
        cfg = self._config
        cal_flat = _resolve_cal_flat(ctx)
        _tvw = cal_flat.get("target_value_weights")
        if _tvw is not None:
            value = _target_value(
                target,
                hq=_tvw.get("hq", cfg.target_value_hq),
                ad=_tvw.get("ad", cfg.target_value_ad),
                artillery=_tvw.get("artillery", cfg.target_value_artillery),
                armor=_tvw.get("armor", cfg.target_value_armor),
                default=_tvw.get("default", cfg.target_value_default),
            )
        else:
            value = _target_value(
                target,
                hq=cfg.target_value_hq,
                ad=cfg.target_value_ad,
                artillery=cfg.target_value_artillery,
                armor=cfg.target_value_armor,
                default=cfg.target_value_default,
            )

        # Distance penalty
        dist_pen = max(1.0, distance / max(1.0, best_wpn_range))

        return (threat * pk * value) / dist_pen

    def _intent_ammunition(
        self,
        *,
        ctx: Any,
        attacker: Unit,
        target: Unit,
        distance_m: float,
        attachment: WeaponAttachment,
        enable_ammo_gate: bool,
        targeting_decision: TacticalTargetingDecision | None = None,
    ) -> AmmoDefinition | None:
        """Preflight one production attachment without RNG or mutation."""
        weapon = attachment.weapon
        definition = weapon.definition
        indirect_fire = getattr(ctx, "indirect_fire_engine", None)
        if indirect_fire is not None and indirect_fire.is_attachment_reserved(
            attacker.entity_id,
            attachment.source_equipment_index,
            weapon.weapon_id,
        ):
            return None

        excluded_ammo_ids: set[str] = set()
        if enable_ammo_gate:
            magazine_capacity = getattr(definition, "magazine_capacity", 0)
            if magazine_capacity > 0:
                legacy_key = f"{attacker.entity_id}:{definition.weapon_id}"
                for ammunition in attachment.ammunition:
                    ammunition_key = f"{legacy_key}:{ammunition.ammo_id}"
                    rounds_fired = self._ammo_expended.get(
                        ammunition_key,
                        self._ammo_expended.get(legacy_key, 0),
                    )
                    if rounds_fired >= magazine_capacity:
                        excluded_ammo_ids.add(ammunition.ammo_id)

        if targeting_decision is not None:
            ammunition = next(
                (
                    candidate
                    for candidate in attachment.ammunition
                    if candidate.ammo_id == targeting_decision.ammunition_id
                    and candidate.ammo_id not in excluded_ammo_ids
                    and weapon.can_fire(candidate.ammo_id)
                ),
                None,
            )
        else:
            ammunition = attachment.first_fireable_ammunition(
                excluded_ammo_ids=excluded_ammo_ids,
            )
        if ammunition is None:
            return None
        if definition.max_range_m > 0 and distance_m > definition.max_range_m:
            return None
        if not _weapon_supports_domain(definition, target.domain):
            return None
        if attacker.speed > 0.5 and definition.requires_deployed:
            return None
        uses_indirect_owner = attachment.modeled_role in _INDIRECT_FIRE_ROLES

        traverse_deg = getattr(definition, "traverse_deg", 360.0)
        if (
            not uses_indirect_owner
            and isinstance(traverse_deg, (int, float))
            and 0 < traverse_deg < 360.0
            and attacker.domain is not Domain.AERIAL
            and getattr(attacker, "ground_type", None) is not GroundUnitType.LIGHT_INFANTRY
        ):
            target_bearing = math.atan2(
                target.position.easting - attacker.position.easting,
                target.position.northing - attacker.position.northing,
            )
            heading = getattr(attacker, "heading", 0.0) or 0.0
            bearing_difference = abs(target_bearing - heading)
            if bearing_difference > math.pi:
                bearing_difference = 2 * math.pi - bearing_difference
            if bearing_difference > math.radians(traverse_deg / 2):
                return None

        elevation_min = getattr(definition, "elevation_min_deg", -5.0)
        elevation_max = getattr(definition, "elevation_max_deg", 85.0)
        if (
            not uses_indirect_owner
            and distance_m > 0
            and definition.parsed_category() is not WeaponCategory.MISSILE_LAUNCHER
            and isinstance(elevation_min, (int, float))
            and isinstance(elevation_max, (int, float))
            and (elevation_min != -5.0 or elevation_max != 85.0)
        ):
            altitude_difference = getattr(target.position, "altitude", 0.0) - getattr(
                attacker.position, "altitude", 0.0
            )
            elevation_deg = math.degrees(
                math.atan2(altitude_difference, distance_m),
            )
            if elevation_deg < elevation_min or elevation_deg > elevation_max:
                return None

        seeker_fov = getattr(ammunition, "seeker_fov_deg", 0.0)
        if (
            not uses_indirect_owner
            and isinstance(seeker_fov, (int, float))
            and seeker_fov > 0
            and attacker.domain is not Domain.AERIAL
            and getattr(attacker, "ground_type", None) is not GroundUnitType.LIGHT_INFANTRY
        ):
            launch_bearing = math.atan2(
                target.position.easting - attacker.position.easting,
                target.position.northing - attacker.position.northing,
            )
            heading = getattr(attacker, "heading", 0.0) or 0.0
            seeker_difference = abs(launch_bearing - heading)
            if seeker_difference > math.pi:
                seeker_difference = 2 * math.pi - seeker_difference
            if seeker_difference > math.radians(seeker_fov / 2):
                return None
        return ammunition

    def _stage_engagement_intent(
        self,
        *,
        ctx: Any,
        attacker: Unit,
        target: Unit,
        attachments: Collection[WeaponAttachment],
        enable_ammo_gate: bool,
        targeting_decision: TacticalTargetingDecision | None = None,
    ) -> _EngagementIntent | None:
        """Choose one deterministic candidate without consuming resources."""
        distance_m = self._targeting_distance(attacker, target)
        choices: list[tuple[float, WeaponAttachment, AmmoDefinition]] = []
        for attachment in sorted(
            attachments,
            key=lambda item: (
                item.source_equipment_index,
                item.weapon.weapon_id,
            ),
        ):
            if targeting_decision is not None and (
                attachment.source_equipment_index != targeting_decision.weapon_source_equipment_index
                or attachment.weapon.weapon_id != targeting_decision.weapon_id
                or attachment.modeled_role is not targeting_decision.weapon_modeled_role
            ):
                continue
            ammunition = self._intent_ammunition(
                ctx=ctx,
                attacker=attacker,
                target=target,
                distance_m=distance_m,
                attachment=attachment,
                enable_ammo_gate=enable_ammo_gate,
                targeting_decision=targeting_decision,
            )
            if ammunition is None:
                continue
            maximum_range_m = float(attachment.weapon.definition.max_range_m)
            weapon_fit_score = min(maximum_range_m / max(distance_m, 1.0), 3.0) if maximum_range_m > 0 else 0.1
            choices.append((weapon_fit_score, attachment, ammunition))
        if not choices:
            return None
        weapon_fit_score, attachment, ammunition = min(
            choices,
            key=lambda item: (
                -item[0],
                item[1].source_equipment_index,
                item[1].weapon.weapon_id,
                item[2].ammo_id,
            ),
        )
        return _EngagementIntent(
            target=target,
            attachment=attachment,
            ammunition=ammunition,
            distance_m=distance_m,
            target_score=self._score_target(
                attacker,
                target,
                distance_m,
                list(attachments),
                ctx,
            ),
            weapon_fit_score=weapon_fit_score,
            targeting_decision=targeting_decision,
        )

    @staticmethod
    def _routed_owner_available(
        ctx: Any,
        role: WeaponModeledRole,
        *,
        air_routing_enabled: bool,
    ) -> bool:
        """Return whether the typed separate owner can accept an intent."""
        if role in _INDIRECT_FIRE_ROLES:
            return getattr(ctx, "indirect_fire_engine", None) is not None
        if role in _AIR_DELIVERY_ROLES:
            return air_routing_enabled and getattr(ctx, "air_ground_engine", None) is not None
        if role in _NAVAL_SUBSURFACE_ROLES:
            return getattr(ctx, "naval_subsurface_engine", None) is not None
        return False

    def _stage_routed_intent(
        self,
        *,
        ctx: Any,
        attacker: Unit,
        enemies: Collection[Unit],
        attachments: Collection[WeaponAttachment],
        visibility_m: float,
        target_selection_mode: str,
        enable_ammo_gate: bool,
        air_routing_enabled: bool,
    ) -> _EngagementIntent | None:
        """Stage the legacy separate-owner lane over its side-wide scope."""
        routed_attachments = tuple(
            attachment
            for attachment in attachments
            if self._routed_owner_available(
                ctx,
                attachment.modeled_role,
                air_routing_enabled=air_routing_enabled,
            )
        )
        if not routed_attachments:
            return None
        sensors = ctx.unit_sensors.get(attacker.entity_id, ())
        candidates: list[_EngagementIntent] = []
        for target in sorted(enemies, key=lambda item: item.entity_id):
            distance_m = self._targeting_distance(attacker, target)
            baseline_visible = target.domain is not Domain.SUBMARINE and distance_m <= visibility_m
            sensor_detectable = any(
                sensor.operational
                and sensor.sensor_type is not SensorType.ESM
                and sensor.supports_target_domain(target.domain)
                and distance_m <= sensor.effective_range
                for sensor in sensors
            )
            if not baseline_visible and not sensor_detectable:
                continue
            intent = self._stage_engagement_intent(
                ctx=ctx,
                attacker=attacker,
                target=target,
                attachments=routed_attachments,
                enable_ammo_gate=enable_ammo_gate,
            )
            if intent is not None:
                candidates.append(intent)
        if not candidates:
            return None
        if target_selection_mode in {"closest", "nearest"}:
            return min(
                candidates,
                key=lambda intent: (
                    intent.distance_m,
                    intent.target.entity_id,
                    -intent.weapon_fit_score,
                    intent.attachment.source_equipment_index,
                    intent.attachment.weapon.weapon_id,
                ),
            )
        return min(
            candidates,
            key=lambda intent: (
                -intent.target_score,
                intent.target.entity_id,
                -intent.weapon_fit_score,
                intent.attachment.source_equipment_index,
                intent.attachment.weapon.weapon_id,
            ),
        )

    @staticmethod
    def _arbitrate_engagement_intents(
        intents: Collection[_EngagementIntent],
        *,
        target_selection_mode: str,
    ) -> _EngagementIntent | None:
        """Commit one legacy-compatible winner before combat mutation."""
        if not intents:
            return None
        if target_selection_mode in {"closest", "nearest"}:
            return min(
                intents,
                key=lambda intent: (
                    intent.distance_m,
                    intent.target.entity_id,
                    -intent.weapon_fit_score,
                    intent.attachment.source_equipment_index,
                    intent.attachment.weapon.weapon_id,
                ),
            )
        return min(
            intents,
            key=lambda intent: (
                -intent.target_score,
                intent.target.entity_id,
                -intent.weapon_fit_score,
                intent.attachment.source_equipment_index,
                intent.attachment.weapon.weapon_id,
            ),
        )

    @staticmethod
    def _revalidate_observer_track_support(
        ctx: Any,
        attacker: Unit,
        target: Unit,
        sensing: SensorAttachment,
        decision: TacticalTargetingDecision,
        *,
        current_distance_m: float,
        live_sensing_range_m: float,
    ) -> TargetingDisposition | None:
        """Rebind one support-backed solution without another sensor draw."""
        if decision.contact_source is not ContactSource.FOW_OBSERVER_TRACK_SUPPORT:
            return None
        evidence = decision.observer_track_support
        fog_of_war = getattr(ctx, "fog_of_war", None)
        if evidence is None or fog_of_war is None:
            return TargetingDisposition.STALE_CONTACT
        if (
            sensing.sensor.sensor_type is not evidence.sensor_type
            or sensing.source_equipment_index != evidence.identity.attachment_identity.source_equipment_index
            or sensing.sensor_id != evidence.identity.attachment_identity.sensor_id
            or sensing.modeled_role.value != evidence.identity.attachment_identity.modeled_role
        ):
            return TargetingDisposition.CONTACT_SENSOR_UNAVAILABLE

        committed_ordinal = fog_of_war.cadence.committed_ordinal
        if committed_ordinal <= 0 or evidence.projection_ordinal != committed_ordinal - 1:
            return TargetingDisposition.STALE_CONTACT

        retained_matches = tuple(
            support
            for support in fog_of_war.get_observer_track_supports(
                decision.shooter_side,
            )
            if support.identity == evidence.identity
        )
        if len(retained_matches) != 1:
            return TargetingDisposition.STALE_CONTACT
        retained = retained_matches[0]
        try:
            projected = retained.project(
                projection_ordinal=evidence.projection_ordinal,
                projection_time_s=decision.logical_time_s,
                process_noise_std_mps2=(fog_of_war.observer_track_support_process_noise_std_mps2),
            )
        except ValueError:
            return TargetingDisposition.STALE_CONTACT
        if projected != evidence:
            return TargetingDisposition.STALE_CONTACT

        world_view = fog_of_war.peek_world_view(decision.shooter_side)
        contact = (
            None if world_view is None or decision.target_id is None else world_view.contacts.get(decision.target_id)
        )
        if (
            contact is None
            or world_view.last_update_time != decision.logical_time_s
            or contact.contact_info.level < ContactLevel.DETECTED
            or contact.track.status in {TrackStatus.STALE, TrackStatus.LOST}
            or contact.track.track_id != evidence.fusion_track_id
            or contact.last_sensor_contact_time > decision.logical_time_s
            or sensing.sensor_id not in contact.reporting_sensors
            or target.entity_id != evidence.identity.target_id
        ):
            return TargetingDisposition.STALE_CONTACT

        max_uncertainty_m = fog_of_war.observer_track_support_max_position_uncertainty_m
        if evidence.position_uncertainty_m >= max_uncertainty_m:
            return TargetingDisposition.STALE_CONTACT
        estimated_range_m = evidence.estimated_range_m(
            observer_easting_m=float(attacker.position.easting),
            observer_northing_m=float(attacker.position.northing),
        )
        if (
            current_distance_m > live_sensing_range_m
            or estimated_range_m + evidence.position_uncertainty_m > live_sensing_range_m
        ):
            return TargetingDisposition.CONTACT_RANGE_EXCEEDED
        return None

    def _revalidate_tactical_engagement(
        self,
        ctx: Any,
        attacker: Unit,
        target: Unit,
        decision: TacticalTargetingDecision,
        *,
        current_distance_m: float,
    ) -> tuple[TargetingDisposition, WeaponAttachment | None]:
        """Revalidate mutable facts for one exact published solution."""
        evidence_cache = _TargetingIntervalEvidenceCache()
        if target.status is not UnitStatus.ACTIVE or target.entity_id != decision.target_id:
            return TargetingDisposition.TARGET_INACTIVE, None
        target_side = target.side if isinstance(target.side, str) else target.side.value
        if target_side != decision.target_side or target_side == decision.shooter_side:
            return TargetingDisposition.TARGET_NOT_HOSTILE, None
        if target.domain is not decision.target_domain:
            return TargetingDisposition.TARGET_DOMAIN_UNSUPPORTED, None

        exact_weapons = tuple(
            attachment
            for attachment in ctx.unit_weapons.get(attacker.entity_id, ())
            if (
                isinstance(attachment, WeaponAttachment)
                and attachment.source_equipment_index == decision.weapon_source_equipment_index
                and attachment.weapon.weapon_id == decision.weapon_id
                and attachment.modeled_role is decision.weapon_modeled_role
            )
        )
        if len(exact_weapons) != 1:
            return TargetingDisposition.NO_USABLE_WEAPON, None
        weapon = exact_weapons[0]
        if not weapon.weapon.operational:
            return TargetingDisposition.WEAPON_INOPERABLE, weapon
        indirect_fire = getattr(ctx, "indirect_fire_engine", None)
        if indirect_fire is not None and indirect_fire.is_attachment_reserved(
            attacker.entity_id,
            weapon.source_equipment_index,
            weapon.weapon.weapon_id,
        ):
            return TargetingDisposition.WEAPON_RESERVED, weapon
        ammunition = self._targeting_ammunition(ctx, attacker, weapon)
        if ammunition is None or ammunition.ammo_id != decision.ammunition_id:
            return TargetingDisposition.NO_FIREABLE_AMMUNITION, weapon
        if not _weapon_supports_domain(weapon.weapon.definition, target.domain):
            return TargetingDisposition.TARGET_DOMAIN_UNSUPPORTED, weapon

        sensor_attachments = tuple(
            getattr(ctx, "unit_sensor_attachments", {}).get(
                attacker.entity_id,
                (),
            ),
        )
        environment = self._targeting_environment(
            ctx,
            attacker,
            target,
            evidence_cache=evidence_cache,
        )
        range_policy = self._targeting_sensor_range_policy(
            ctx,
            attacker,
            evidence_cache=evidence_cache,
        )
        sensing: SensorAttachment | None = None
        sensing_index = decision.sensing_sensor_source_equipment_index
        if sensing_index is not None:
            sensing_matches = tuple(
                attachment
                for attachment in sensor_attachments
                if (
                    attachment.source_equipment_index == sensing_index
                    and attachment.sensor_id == decision.sensing_sensor_id
                    and attachment.modeled_role is decision.sensing_sensor_modeled_role
                )
            )
            if len(sensing_matches) != 1:
                return TargetingDisposition.CONTACT_SENSOR_UNAVAILABLE, weapon
            sensing = sensing_matches[0]
            if not sensing.sensor.operational:
                return TargetingDisposition.CONTACT_SENSOR_OFFLINE, weapon
            if (
                attacker.domain
                not in allowed_shooter_domains_for_sensor_role(
                    sensing.modeled_role,
                )
                or target.domain not in required_domains_for_sensor_role(sensing.modeled_role)
                or not sensing.sensor.supports_target_domain(target.domain)
            ):
                return TargetingDisposition.CONTACT_SENSOR_WRONG_DOMAIN, weapon
            if not self._targeting_los_visible(
                ctx,
                attacker,
                target,
                required=bool(sensing.sensor.definition.requires_los),
                evidence_cache=evidence_cache,
            ):
                return TargetingDisposition.LINE_OF_SIGHT_BLOCKED, weapon
            if not self._targeting_sensor_in_fov(attacker, target, sensing):
                return TargetingDisposition.OUTSIDE_SENSOR_FIELD_OF_VIEW, weapon
            live_sensing_range_m = self._targeting_sensor_range(
                ctx,
                attacker,
                target,
                sensing,
                environment=environment,
                range_policy=range_policy,
                evidence_cache=evidence_cache,
            )
            if (
                sensing.sensor.sensor_type is SensorType.ESM
                and decision.contact_source is ContactSource.FOW_OBSERVER_WITNESS
            ):
                # The same-interval witness already proves a live emitter.
                # Revalidation must remain RNG-free, so bound that witness by
                # the attachment's current condition-dependent reach instead
                # of attempting a second probabilistic ESM detection.
                live_sensing_range_m = saturating_range_product(
                    float(sensing.sensor.effective_range),
                    self._targeting_observer_range_modifier(
                        ctx,
                        attacker,
                        evidence_cache=evidence_cache,
                    ),
                )
                live_sensing_range_m = _validated_targeting_sensor_range_m(
                    sensor_type=sensing.sensor.sensor_type,
                    condition_adjusted_range_m=float(
                        sensing.sensor.effective_range,
                    ),
                    resolved_range_m=live_sensing_range_m,
                    policy=range_policy,
                )
        elif not self._targeting_los_visible(
            ctx,
            attacker,
            target,
            required=True,
            evidence_cache=evidence_cache,
        ):
            return TargetingDisposition.LINE_OF_SIGHT_BLOCKED, weapon
        else:
            live_sensing_range_m = self._targeting_direct_visual_range(
                ctx,
                attacker,
                target,
                environment=environment,
                evidence_cache=evidence_cache,
            )

        if decision.contact_source is ContactSource.FOW_OBSERVER_TRACK_SUPPORT:
            if sensing is None:
                return TargetingDisposition.CONTACT_SENSOR_UNAVAILABLE, weapon
            support_rejection = self._revalidate_observer_track_support(
                ctx,
                attacker,
                target,
                sensing,
                decision,
                current_distance_m=current_distance_m,
                live_sensing_range_m=live_sensing_range_m,
            )
            if support_rejection is not None:
                return support_rejection, weapon

        if current_distance_m > decision.contact_range_m:
            return TargetingDisposition.CONTACT_RANGE_EXCEEDED, weapon
        if current_distance_m > min(
            decision.sensing_range_m,
            live_sensing_range_m,
        ):
            return TargetingDisposition.SENSING_RANGE_EXCEEDED, weapon
        if sensing_index is None and current_distance_m > decision.visibility_bound_m:
            return TargetingDisposition.VISIBILITY_LIMITED, weapon

        if decision.fire_control_source is FireControlSource.SENSOR_ATTACHMENT:
            fire_control_matches = tuple(
                attachment
                for attachment in sensor_attachments
                if (
                    attachment.source_equipment_index == decision.fire_control_sensor_source_equipment_index
                    and attachment.sensor_id == decision.fire_control_sensor_id
                    and attachment.modeled_role is decision.fire_control_sensor_modeled_role
                )
            )
            if len(fire_control_matches) != 1:
                return TargetingDisposition.NO_COMPATIBLE_FIRE_CONTROL, weapon
            fire_control = fire_control_matches[0]
            if not fire_control.sensor.operational:
                return TargetingDisposition.FIRE_CONTROL_SENSOR_OFFLINE, weapon
            if attacker.domain not in allowed_shooter_domains_for_sensor_role(
                fire_control.modeled_role,
            ):
                return (
                    TargetingDisposition.FIRE_CONTROL_SHOOTER_DOMAIN_UNSUPPORTED,
                    weapon,
                )
            if target.domain not in required_domains_for_sensor_role(
                fire_control.modeled_role,
            ) or not fire_control.sensor.supports_target_domain(target.domain):
                return (
                    TargetingDisposition.FIRE_CONTROL_TARGET_DOMAIN_UNSUPPORTED,
                    weapon,
                )
            if (
                weapon.source_equipment_index not in fire_control.compatible_weapon_source_indexes
                or weapon.modeled_role not in fire_control.compatible_weapon_roles
            ):
                return TargetingDisposition.NO_COMPATIBLE_FIRE_CONTROL, weapon
            if not self._targeting_los_visible(
                ctx,
                attacker,
                target,
                required=bool(fire_control.sensor.definition.requires_los),
                evidence_cache=evidence_cache,
            ):
                return TargetingDisposition.LINE_OF_SIGHT_BLOCKED, weapon
            if not self._targeting_sensor_in_fov(
                attacker,
                target,
                fire_control,
            ):
                return TargetingDisposition.OUTSIDE_SENSOR_FIELD_OF_VIEW, weapon
            live_fire_control_range_m = self._targeting_sensor_range(
                ctx,
                attacker,
                target,
                fire_control,
                environment=environment,
                range_policy=range_policy,
                evidence_cache=evidence_cache,
            )
        elif decision.fire_control_source is FireControlSource.DIRECT_VISUAL and not self._targeting_los_visible(
            ctx,
            attacker,
            target,
            required=True,
            evidence_cache=evidence_cache,
        ):
            return TargetingDisposition.LINE_OF_SIGHT_BLOCKED, weapon
        else:
            live_fire_control_range_m = self._targeting_direct_visual_range(
                ctx,
                attacker,
                target,
                environment=environment,
                evidence_cache=evidence_cache,
            )
        if current_distance_m > min(
            decision.fire_control_range_m,
            live_fire_control_range_m,
        ):
            return TargetingDisposition.FIRE_CONTROL_RANGE_EXCEEDED, weapon
        if current_distance_m > decision.physical_max_range_m:
            return TargetingDisposition.OUTSIDE_PHYSICAL_RANGE, weapon
        if (
            decision.effective_range_basis is EffectiveRangeBasis.AUTHORED
            and current_distance_m > decision.predictive_effective_range_m
        ):
            return TargetingDisposition.OUTSIDE_EFFECTIVE_RANGE, weapon
        return TargetingDisposition.VALID_ENGAGEMENT_SOLUTION, weapon

    @staticmethod
    def _publish_tactical_revalidation(
        runtime: Any,
        decision: TacticalTargetingDecision,
        disposition: TargetingDisposition,
    ) -> TacticalEngagementRevalidationOutcome:
        """Publish the exact post-movement result before later combat gates."""
        if (
            decision.target_id is None
            or decision.weapon_id is None
            or decision.weapon_source_equipment_index is None
            or decision.weapon_modeled_role is None
            or decision.ammunition_id is None
        ):
            raise RuntimeError(
                "Valid targeting decision lacks revalidation identity",
            )
        outcome = TacticalEngagementRevalidationOutcome(
            engine_tick=decision.engine_tick,
            logical_time_s=decision.logical_time_s,
            battle_id=decision.battle_id,
            shooter_id=decision.shooter_id,
            target_id=decision.target_id,
            weapon_id=decision.weapon_id,
            weapon_source_equipment_index=(decision.weapon_source_equipment_index),
            weapon_modeled_role=decision.weapon_modeled_role,
            ammunition_id=decision.ammunition_id,
            disposition=disposition,
            revalidation_passed=(disposition is TargetingDisposition.VALID_ENGAGEMENT_SOLUTION),
            fog_of_war_enabled=decision.fog_of_war_enabled,
        )
        return runtime.publish_engagement_revalidation(outcome)

    def _execute_engagements(
        self,
        ctx: SimulationContext,
        units_by_side: Mapping[str, Sequence[Unit]],
        active_enemies: Mapping[str, Sequence[Unit]],
        enemy_pos_arrays: Mapping[str, np.ndarray],
        dt: float,
        timestamp: datetime,
        _unit_index: Mapping[str, Unit] | None = None,
        battle: BattleContext | None = None,
    ) -> list[tuple[Unit, UnitStatus, str]]:
        """Compatibility delegation to the injected engagement executor."""
        return self._engagement_executor.execute(
            self._executor_owner,
            EngagementExecutionRequest(
                runtime=self._build_engagement_runtime(ctx, units_by_side),
                units_by_side=units_by_side,
                active_enemies=active_enemies,
                enemy_position_arrays=enemy_pos_arrays,
                dt_seconds=dt,
                timestamp=timestamp,
                unit_index=_unit_index,
                battle=(
                    None
                    if battle is None
                    else BattleIntervalView.from_battle(battle)
                ),
            ),
        )

    @staticmethod
    def _apply_deferred_damage(
        pending_damage: list[tuple[Unit, UnitStatus, str]] | list[tuple[Unit, UnitStatus]],
        event_bus: Any | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        """Apply deferred damage — worst outcome wins per unit."""
        applied: dict[str, UnitStatus] = {}
        for entry in pending_damage:
            target, new_status = entry[0], entry[1]
            prev = applied.get(target.entity_id)
            if prev is None or new_status.value > prev.value:
                applied[target.entity_id] = new_status

        ts = timestamp or datetime.min
        for entry in pending_damage:
            target, new_status = entry[0], entry[1]
            weapon_id = entry[2] if len(entry) >= 3 else ""
            if applied.get(target.entity_id) == new_status:
                object.__setattr__(target, "status", new_status)
                applied.pop(target.entity_id, None)
                if event_bus is not None:
                    if new_status == UnitStatus.DESTROYED:
                        event_bus.publish(
                            UnitDestroyedEvent(
                                timestamp=ts,
                                source=ModuleId.COMBAT,
                                unit_id=target.entity_id,
                                cause="combat_damage",
                                side=target.side,
                                weapon_id=weapon_id,
                            )
                        )
                    elif new_status == UnitStatus.DISABLED:
                        event_bus.publish(
                            UnitDisabledEvent(
                                timestamp=ts,
                                source=ModuleId.COMBAT,
                                unit_id=target.entity_id,
                                cause="combat_damage",
                                side=target.side,
                                weapon_id=weapon_id,
                            )
                        )

    def _execute_morale(
        self,
        ctx: Any,
        units_by_side: dict[str, list[Unit]],
        active_enemies: dict[str, list[Unit]],
        timestamp: datetime,
    ) -> None:
        """Run morale checks for all active/routing units."""
        morale_runtime = getattr(ctx, "morale_runtime", None)
        if morale_runtime is None:
            return

        cal_flat = _resolve_cal_flat(ctx)
        morale_degrade_mod = cal_flat.get("morale_degrade_rate_modifier", 1.0)
        rout_engine = morale_runtime.rout_engine
        current_time_s = ctx.clock.elapsed.total_seconds()
        morale_unit_cycles_processed = 0

        # Phase 56a: build per-side STRtree for rally + cascade (O(n log n))
        _side_trees: dict[str, tuple[STRtree, list[Unit]]] = {}
        if rout_engine is not None:
            for _sn, _su in units_by_side.items():
                _eligible = [u for u in _su if u.status in (UnitStatus.ACTIVE, UnitStatus.ROUTING)]
                if _eligible:
                    _pts = [Point(u.position.easting, u.position.northing) for u in _eligible]
                    _side_trees[_sn] = (STRtree(_pts), _eligible)

        # Phase 42c / 56a: rally check for routing units (STRtree)
        if rout_engine is not None:
            _rally_r = rout_engine.config.cascade_radius_m
            for side_name, side_units in units_by_side.items():
                tree_data = _side_trees.get(side_name)
                for u in side_units:
                    if u.status != UnitStatus.ROUTING:
                        continue
                    ms = ctx.morale_states.get(u.entity_id)
                    if ms is None or int(ms) != MoraleState.ROUTED:
                        continue
                    nearby_count = 0
                    leader_present = False
                    if tree_data is not None:
                        tree, eligible = tree_data
                        query_geom = Point(
                            u.position.easting,
                            u.position.northing,
                        ).buffer(_rally_r)
                        idxs = tree.query(query_geom)
                        for idx in idxs:
                            other = eligible[idx]
                            if other.entity_id == u.entity_id:
                                continue
                            if other.status != UnitStatus.ACTIVE:
                                continue
                            dx = other.position.easting - u.position.easting
                            dy = other.position.northing - u.position.northing
                            if math.sqrt(dx * dx + dy * dy) < _rally_r:
                                nearby_count += 1
                                st = getattr(other, "support_type", None)
                                if st is not None:
                                    st_name = st.name if hasattr(st, "name") else str(st)
                                    if st_name == "HQ":
                                        leader_present = True
                    morale_runtime.check_rally(
                        u.entity_id,
                        nearby_count,
                        leader_present,
                        timestamp=timestamp,
                        current_time_s=current_time_s,
                    )

        for side_name, side_units in units_by_side.items():
            total = len(side_units)
            destroyed = sum(1 for u in side_units if u.status in (UnitStatus.DESTROYED, UnitStatus.SURRENDERED))
            casualty_rate = destroyed / total if total > 0 else 0.0

            enemies = active_enemies.get(side_name, [])
            active_own = sum(1 for u in side_units if u.status == UnitStatus.ACTIVE)
            active_enemy = len(enemies)
            force_ratio = active_own / active_enemy if active_enemy > 0 else 10.0

            cohesion = cal_flat.get(f"{side_name}_cohesion", 0.7)

            for u in side_units:
                if u.status not in (UnitStatus.ACTIVE, UnitStatus.ROUTING):
                    continue

                # The runtime derives the first dt from scenario time zero;
                # logical zero therefore has no admissible stochastic check.
                if current_time_s <= 0.0:
                    continue

                # Rally, melee, or another forced transaction may already
                # have admitted this unit at the current logical time.  The
                # authoritative record, rather than local loop bookkeeping,
                # prevents a second same-tick stochastic admission even when
                # transition_cooldown_s is configured to zero.
                if morale_runtime.record_for(u.entity_id).last_check_time_s == current_time_s:
                    continue

                # Phase 40e: use actual suppression level
                sup_state = self._suppression_states.get(u.entity_id)
                suppression_level = sup_state.value if sup_state is not None else 0.0

                morale_unit_cycles_processed += 1
                morale_runtime.check_transition(
                    unit_id=u.entity_id,
                    casualty_rate=casualty_rate * morale_degrade_mod,
                    suppression_level=suppression_level,
                    leadership_present=True,
                    cohesion=cohesion,
                    force_ratio=force_ratio,
                    timestamp=timestamp,
                    current_time_s=current_time_s,
                )

        # Phase 42c / 56a: rout cascade — STRtree spatial query
        if rout_engine is not None:
            _cascade_r = rout_engine.config.cascade_radius_m
            newly_routed: list[tuple[str, Unit]] = []
            for side_name, side_units in units_by_side.items():
                for u in side_units:
                    if u.status == UnitStatus.ROUTING:
                        ms = ctx.morale_states.get(u.entity_id)
                        if ms is not None and int(ms) == MoraleState.ROUTED:
                            newly_routed.append((side_name, u))

            for side_name, routing_unit in newly_routed:
                distances: dict[str, float] = {}
                tree_data = _side_trees.get(side_name)
                if tree_data is not None:
                    tree, eligible = tree_data
                    query_geom = Point(
                        routing_unit.position.easting,
                        routing_unit.position.northing,
                    ).buffer(_cascade_r)
                    idxs = tree.query(query_geom)
                    for idx in idxs:
                        other = eligible[idx]
                        if other.entity_id == routing_unit.entity_id:
                            continue
                        if other.status not in (UnitStatus.ACTIVE, UnitStatus.ROUTING):
                            continue
                        dx = other.position.easting - routing_unit.position.easting
                        dy = other.position.northing - routing_unit.position.northing
                        dist = math.sqrt(dx * dx + dy * dy)
                        distances[other.entity_id] = dist

                morale_runtime.rout_cascade(
                    routing_unit.entity_id,
                    distances,
                    timestamp=timestamp,
                    current_time_s=current_time_s,
                )

        self._stage_performance_delta(
            PerformanceReceiptDelta(
                lod=LODReceipt(
                    morale=LODMoraleReceipt(
                        unit_cycles_processed=(morale_unit_cycles_processed),
                    ),
                ),
            ),
        )

    @staticmethod
    def _find_unit_side(ctx: BattleOODARuntime, unit_id: str) -> str:
        """Find which side a unit belongs to."""
        for side, units in ctx.units_by_side.items():
            if any(u.entity_id == unit_id for u in units):
                return side
        return ""

    @staticmethod
    def _compute_c2_effectiveness(
        ctx: BattleOODARuntime,
        unit_id: str,
        side: str,
        *,
        failure_handler: BattleRuntimeFailureHandler | None = None,
    ) -> float:
        """Compute C2 effectiveness from comms state. Returns 1.0 if unavailable."""
        comms = getattr(ctx, "comms_engine", None)
        if comms is None:
            return 1.0
        # Build position dict for the unit's side
        positions: dict[str, Position] = {}
        for u in ctx.active_units(side):
            if u.position is not None:
                positions[u.entity_id] = u.position
        if not positions:
            return 1.0
        cal_flat = _resolve_cal_flat(ctx)
        min_eff = cal_flat.get("c2_min_effectiveness", 0.3)
        try:
            eff = comms.compute_c2_effectiveness(
                unit_id,
                positions,
                min_effectiveness=min_eff,
            )
        except Exception as exc:
            if failure_handler is not None and not failure_handler(
                "c2.communications",
                "compute_c2_effectiveness",
                exc,
            ):
                raise
            eff = 1.0
        # Phase 62b: MOPP comms degradation
        if cal_flat.get("enable_human_factors", False):
            _cbrn_c2 = getattr(ctx, "cbrn_engine", None)
            if _cbrn_c2 is not None:
                _ml_c2 = _cbrn_c2.get_mopp_level(unit_id)
                if _ml_c2 > 0:
                    _cf = cal_flat.get("mopp_comms_factor_4", 0.5)
                    _sc = _ml_c2 / 4.0
                    _comms_mod = 1.0 - _sc * (1.0 - _cf)
                    eff *= _comms_mod
        return eff

    @staticmethod
    def _get_unit_morale_level(
        ctx: BattleOODARuntime,
        unit_id: str,
    ) -> float:
        """Derive morale level [0, 1] from morale state.

        STEADY=1.0, SHAKEN=0.75, BROKEN=0.5, ROUTED=0.25, SURRENDERED=0.0.
        """
        ms = ctx.morale_states.get(unit_id)
        if ms is None:
            return 0.7  # sensible default
        val = int(ms)
        return max(0.0, 1.0 - val * 0.25)

    @staticmethod
    def _get_unit_supply_level(
        ctx: BattleOODARuntime,
        unit_id: str,
        *,
        failure_handler: BattleRuntimeFailureHandler | None = None,
    ) -> float:
        """Query stockpile manager for supply state [0, 1]."""
        if ctx.stockpile_manager is None:
            return 1.0
        try:
            return ctx.stockpile_manager.get_supply_state(unit_id)
        except Exception as exc:
            if failure_handler is not None and not failure_handler(
                "logistics.stockpile",
                "get_supply_state",
                exc,
            ):
                raise
            return 1.0

    @staticmethod
    def _build_assessment_summary(
        ctx: BattleOODARuntime,
        unit_id: str,
        assessment: SituationAssessment | None,
        *,
        failure_handler: BattleRuntimeFailureHandler | None = None,
    ) -> dict[str, float]:
        """Build assessment summary dict from real or default data.

        Used by school decision adjustments and opponent modeling.
        """
        if assessment is not None:
            return {
                "force_ratio": getattr(assessment, "force_ratio", 1.0),
                "supply_level": getattr(assessment, "supply_level", 1.0),
                "morale_level": getattr(assessment, "morale_level", 0.7),
                "intel_quality": getattr(assessment, "intel_quality", 0.5),
                "c2_effectiveness": getattr(assessment, "c2_effectiveness", 1.0),
            }
        # Fallback: compute basic values
        side = ""
        for s, units in ctx.units_by_side.items():
            if any(u.entity_id == unit_id for u in units):
                side = s
                break
        friendly = len(ctx.active_units(side)) if side else 1
        enemies = sum(len(ctx.active_units(s)) for s in ctx.side_names() if s != side) if side else 1
        force_ratio = friendly / max(enemies, 1)
        return {
            "force_ratio": force_ratio,
            "supply_level": BattleManager._get_unit_supply_level(
                ctx,
                unit_id,
                failure_handler=failure_handler,
            ),
            "morale_level": BattleManager._get_unit_morale_level(ctx, unit_id),
            "intel_quality": 0.5,
            "c2_effectiveness": BattleManager._compute_c2_effectiveness(
                ctx,
                unit_id,
                side,
                failure_handler=failure_handler,
            ),
        }
