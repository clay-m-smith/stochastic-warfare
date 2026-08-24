"""Typed transaction boundaries used by the tactical battle facade.

Request records freeze orchestration topology at construction while retaining
the identity of live :class:`Unit` domain objects.  Executors may mutate
simulation state only through those units or the explicit
:class:`BattleExecutorOwner` commands below.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol

import numpy as np
from numpy.typing import NDArray

from stochastic_warfare.entities.base import UnitStatus

if TYPE_CHECKING:
    from stochastic_warfare.c2.ai.assessment import SituationAssessor
    from stochastic_warfare.c2.ai.commander import CommanderEngine
    from stochastic_warfare.c2.ai.decisions import DecisionEngine
    from stochastic_warfare.c2.ai.assessment import SituationAssessment
    from stochastic_warfare.c2.ai.ooda import OODAPhase
    from stochastic_warfare.c2.ai.ooda import OODALoopEngine
    from stochastic_warfare.c2.ai.schools import SchoolRegistry
    from stochastic_warfare.c2.ai.schools.base import DoctrinalSchool
    from stochastic_warfare.c2.ai.stratagems import StratagemEngine
    from stochastic_warfare.c2.communications import CommunicationsEngine
    from stochastic_warfare.c2.orders.air_orders import ATOPlanningEngine
    from stochastic_warfare.c2.orders.propagation import OrderPropagationEngine
    from stochastic_warfare.c2.orders.propagation import PropagationResult
    from stochastic_warfare.c2.planning.process import PlanningProcessEngine
    from stochastic_warfare.c2.roe import RoeEngine
    from stochastic_warfare.cbrn.protection import ProtectionEngine
    from stochastic_warfare.combat.ammunition import AmmoDefinition, WeaponInstance
    from stochastic_warfare.combat.air_combat import AirCombatEngine
    from stochastic_warfare.combat.air_defense import AirDefenseEngine
    from stochastic_warfare.combat.air_ground import AirGroundEngine
    from stochastic_warfare.combat.archery import ArcheryEngine
    from stochastic_warfare.combat.barrage import BarrageEngine
    from stochastic_warfare.combat.damage import IncendiaryDamageEngine
    from stochastic_warfare.combat.directed_energy import DEWEngine
    from stochastic_warfare.combat.engagement import EngagementEngine
    from stochastic_warfare.combat.gas_warfare import GasWarfareEngine
    from stochastic_warfare.combat.indirect_fire import FireMissionResult, SalvoResult
    from stochastic_warfare.combat.indirect_fire import IndirectFireEngine
    from stochastic_warfare.combat.melee import MeleeEngine
    from stochastic_warfare.combat.missiles import MissileEngine
    from stochastic_warfare.combat.naval_gunfire_support import NavalGunfireSupportEngine
    from stochastic_warfare.combat.naval_gunnery import NavalGunneryEngine
    from stochastic_warfare.combat.naval_subsurface import NavalSubsurfaceEngine
    from stochastic_warfare.combat.naval_surface import NavalSurfaceEngine
    from stochastic_warfare.combat.suppression import UnitSuppressionState
    from stochastic_warfare.combat.suppression import SuppressionEngine
    from stochastic_warfare.combat.unconventional import UnconventionalWarfareEngine
    from stochastic_warfare.combat.volley_fire import VolleyFireEngine
    from stochastic_warfare.core.events import EventBus
    from stochastic_warfare.core.rng import RNGManager
    from stochastic_warfare.core.types import Position
    from stochastic_warfare.detection.detection import DetectionEngine
    from stochastic_warfare.detection.fog_of_war import FogOfWarManager
    from stochastic_warfare.detection.sensors import SensorInstance
    from stochastic_warfare.entities.base import Unit
    from stochastic_warfare.environment.conditions import ConditionsEngine
    from stochastic_warfare.environment.electromagnetic import EMEnvironment
    from stochastic_warfare.environment.obscurants import ObscurantsEngine
    from stochastic_warfare.environment.sea_state import SeaStateEngine
    from stochastic_warfare.environment.seasons import SeasonsEngine
    from stochastic_warfare.environment.time_of_day import TimeOfDayEngine
    from stochastic_warfare.environment.underwater_acoustics import (
        UnderwaterAcousticsEngine,
    )
    from stochastic_warfare.environment.weather import WeatherEngine
    from stochastic_warfare.ew.eccm import ECCMEngine
    from stochastic_warfare.ew.jamming import JammingEngine
    from stochastic_warfare.logistics.maintenance import MaintenanceEngine
    from stochastic_warfare.logistics.stockpile import StockpileManager
    from stochastic_warfare.morale.state import MoraleState
    from stochastic_warfare.morale.runtime import MoraleRuntime
    from stochastic_warfare.movement.cavalry import CavalryEngine
    from stochastic_warfare.movement.engine import MovementEngine
    from stochastic_warfare.movement.formation_ancient import AncientFormationEngine
    from stochastic_warfare.movement.formation_napoleonic import (
        NapoleonicFormationEngine,
    )
    from stochastic_warfare.simulation.battle import (
        BattleContext,
        BattleStatePlan,
        DeferredOODADecision,
        MovementCommitter,
        _EngagementIntent,
    )
    from stochastic_warfare.simulation.movement_diagnostics import MovementDiagnostics
    from stochastic_warfare.simulation.performance_flags import (
        EffectivePerformanceFlags,
        PerformanceReceiptDelta,
        PerformanceReceiptRestorePlan,
    )
    from stochastic_warfare.simulation.runtime_attachments import WeaponAttachment
    from stochastic_warfare.simulation.era_runtime import EraRuntimeContract
    from stochastic_warfare.simulation.loadouts import SensorAttachment
    from stochastic_warfare.simulation.tactical_targeting import (
        TacticalEngagementRevalidationOutcome,
        TacticalTargetingDecision,
        TacticalTargetingRuntime,
        TargetingDisposition,
    )
    from stochastic_warfare.simulation.loadouts import WeaponModeledRole
    from stochastic_warfare.space.constellations import SpaceEngine
    from stochastic_warfare.terrain.classification import TerrainClassification
    from stochastic_warfare.terrain.heightmap import Heightmap
    from stochastic_warfare.terrain.hydrography import HydrographyManager
    from stochastic_warfare.terrain.infrastructure import InfrastructureManager
    from stochastic_warfare.terrain.los import LOSEngine
    from stochastic_warfare.terrain.obstacles import ObstacleManager
    from stochastic_warfare.terrain.trenches import TrenchSystemEngine


type ReadonlyValue = (
    None
    | bool
    | int
    | float
    | str
    | tuple[ReadonlyValue, ...]
    | frozenset[ReadonlyValue]
    | Mapping[str, ReadonlyValue]
)
type CheckpointValue = (
    None
    | bool
    | int
    | float
    | str
    | tuple[CheckpointValue, ...]
    | Mapping[str, CheckpointValue]
)


class _FrozenCheckpointList(tuple[CheckpointValue, ...]):
    """Distinguish an immutable copied JSON list from an authored tuple."""

BattleRuntimeFailureHandler = Callable[[str, str, Exception], bool]
"""Decide whether a battle-runtime exception may use its degraded fallback."""


def _freeze_value(value: object) -> ReadonlyValue:
    """Recursively copy supported behavior-configuration values."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, ReadonlyValue] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError("read-only executor mappings require string keys")
            frozen[key] = _freeze_value(child)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(child) for child in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(
            _freeze_value(child) for child in value
        )
    raise TypeError(
        f"unsupported executor snapshot value: {type(value).__qualname__}",
    )


def _thaw_checkpoint_value(value: CheckpointValue) -> object:
    """Return a fresh mutable JSON-shaped copy for strict checkpoint staging."""
    if isinstance(value, Mapping):
        return {
            key: _thaw_checkpoint_value(child)
            for key, child in value.items()
        }
    if isinstance(value, _FrozenCheckpointList):
        return [_thaw_checkpoint_value(child) for child in value]
    if isinstance(value, tuple):
        return tuple(_thaw_checkpoint_value(child) for child in value)
    return value


def _freeze_checkpoint_value(value: object) -> CheckpointValue:
    """Copy checkpoint values without normalizing invalid tuples to lists."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, CheckpointValue] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError("read-only executor mappings require string keys")
            frozen[key] = _freeze_checkpoint_value(child)
        return MappingProxyType(frozen)
    if isinstance(value, list):
        return _FrozenCheckpointList(
            _freeze_checkpoint_value(child) for child in value
        )
    if isinstance(value, tuple):
        return tuple(_freeze_checkpoint_value(child) for child in value)
    raise TypeError(
        f"unsupported executor checkpoint value: {type(value).__qualname__}",
    )


def _freeze_unit_mapping(
    value: Mapping[str, Sequence[Unit]],
) -> Mapping[str, tuple[Unit, ...]]:
    """Copy side topology while preserving each live unit's identity."""
    return MappingProxyType({side: tuple(units) for side, units in value.items()})


def _freeze_position_arrays(
    value: Mapping[str, NDArray[np.float64]] | None,
) -> Mapping[str, NDArray[np.float64]] | None:
    """Isolate arrays and reject mutation through an injected executor."""
    if value is None:
        return None
    frozen: dict[str, NDArray[np.float64]] = {}
    for side, array in value.items():
        if not isinstance(array, np.ndarray):
            raise TypeError("enemy position snapshots must be numpy arrays")
        copied = np.array(array, dtype=np.float64, copy=True)
        copied.setflags(write=False)
        frozen[side] = copied
    return MappingProxyType(frozen)


def _copy_readonly_mapping(
    value: Mapping[str, ReadonlyValue] | Mapping[str, object],
) -> Mapping[str, object]:
    """Detach one mapping without retaining its mutable source container."""
    return MappingProxyType(dict(value))


def _deepcopy_readonly_mapping(
    value: Mapping[str, object],
) -> Mapping[str, object]:
    """Detach a mapping and every mutable domain value it contains."""
    return MappingProxyType(copy.deepcopy(dict(value)))


@dataclass(frozen=True, slots=True)
class BattleIntervalView:
    """Immutable battle identity and interval fields visible to executors."""

    battle_id: str
    start_tick: int
    start_time: datetime
    involved_sides: tuple[str, ...]
    active: bool
    ticks_executed: int
    unit_ids: frozenset[str]
    wave_assignments: Mapping[str, int]
    battle_elapsed_s: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "involved_sides", tuple(self.involved_sides))
        object.__setattr__(self, "unit_ids", frozenset(self.unit_ids))
        object.__setattr__(
            self,
            "wave_assignments",
            MappingProxyType(dict(self.wave_assignments)),
        )

    @classmethod
    def from_battle(cls, battle: BattleContext) -> BattleIntervalView:
        """Snapshot one live battle without retaining its mutable containers."""
        return cls(
            battle_id=battle.battle_id,
            start_tick=battle.start_tick,
            start_time=battle.start_time,
            involved_sides=tuple(battle.involved_sides),
            active=battle.active,
            ticks_executed=battle.ticks_executed,
            unit_ids=frozenset(battle.unit_ids),
            wave_assignments=battle.wave_assignments,
            battle_elapsed_s=battle.battle_elapsed_s,
        )


@dataclass(frozen=True, slots=True)
class BattleExecutorConfigView:
    """Scalar battle configuration needed by the hot-path executors."""

    destruction_threshold: float
    disable_threshold: float
    elevation_advantage_cap: float
    elevation_disadvantage_floor: float


@dataclass(frozen=True, slots=True)
class BattleClockView:
    """Read-only logical-clock values needed during one executor call."""

    current_time: datetime
    elapsed: timedelta
    tick_count: int


@dataclass(frozen=True, slots=True)
class BattleScenarioView:
    """Frozen scenario scalars used by tactical targeting and engagement."""

    latitude: float
    longitude: float
    behavior_rules: Mapping[str, ReadonlyValue]
    side_experience_levels: Mapping[str, float]

    def __post_init__(self) -> None:
        frozen_rules = _freeze_value(self.behavior_rules)
        if not isinstance(frozen_rules, Mapping):
            raise TypeError("battle behavior_rules must be a mapping")
        object.__setattr__(self, "behavior_rules", frozen_rules)
        object.__setattr__(
            self,
            "side_experience_levels",
            MappingProxyType(dict(self.side_experience_levels)),
        )


@dataclass(frozen=True, slots=True)
class BattleExecutionRuntime:
    """Common frozen values visible to one tactical executor transaction."""

    clock: BattleClockView
    cal_flat: Mapping[str, ReadonlyValue]
    units_by_side: Mapping[str, Sequence[Unit]]

    def __post_init__(self) -> None:
        frozen_calibration = _freeze_value(self.cal_flat)
        if not isinstance(frozen_calibration, Mapping):
            raise TypeError("battle calibration must be a mapping")
        object.__setattr__(self, "cal_flat", frozen_calibration)
        object.__setattr__(
            self,
            "units_by_side",
            _freeze_unit_mapping(self.units_by_side),
        )

    def active_units(self, side: str) -> tuple[Unit, ...]:
        """Return active live units for one side in preserved roster order."""
        return tuple(
            unit
            for unit in self.units_by_side.get(side, ())
            if unit.status is UnitStatus.ACTIVE
        )

    def side_names(self) -> tuple[str, ...]:
        """Return canonical side names without exposing the source mapping."""
        return tuple(sorted(self.units_by_side))

    def all_units(self) -> tuple[Unit, ...]:
        """Return live units in preserved side and roster order."""
        return tuple(
            unit
            for side_units in self.units_by_side.values()
            for unit in side_units
        )


@dataclass(frozen=True, slots=True)
class BattleTargetingRuntime(BattleExecutionRuntime):
    """Exact live owners needed for RNG-free targeting revalidation."""

    config: BattleScenarioView
    unit_weapons: Mapping[str, Sequence[WeaponAttachment]]
    unit_sensor_attachments: Mapping[str, Sequence[SensorAttachment]]
    unit_sensors: Mapping[str, Sequence[SensorInstance]]
    tactical_targeting: TacticalTargetingRuntime | None
    targeting_default_visibility_m: float
    weather_engine: WeatherEngine | None
    time_of_day_engine: TimeOfDayEngine | None
    seasons_engine: SeasonsEngine | None
    sea_state_engine: SeaStateEngine | None
    obscurants_engine: ObscurantsEngine | None
    conditions_engine: EMEnvironment | None
    conditions_facade: ConditionsEngine | None
    underwater_acoustics_engine: UnderwaterAcousticsEngine | None
    cbrn_engine: ProtectionEngine | None
    detection_engine: DetectionEngine | None
    fog_of_war: FogOfWarManager | None
    los_engine: LOSEngine | None
    classification: TerrainClassification | None
    heightmap: Heightmap | None
    trench_engine: TrenchSystemEngine | None
    infrastructure_manager: InfrastructureManager | None
    obstacle_manager: ObstacleManager | None
    incendiary_engine: IncendiaryDamageEngine | None
    indirect_fire_engine: IndirectFireEngine | None

    def __post_init__(self) -> None:
        BattleExecutionRuntime.__post_init__(self)
        object.__setattr__(
            self,
            "unit_weapons",
            MappingProxyType(
                {
                    unit_id: tuple(attachments)
                    for unit_id, attachments in self.unit_weapons.items()
                },
            ),
        )
        object.__setattr__(
            self,
            "unit_sensor_attachments",
            MappingProxyType(
                {
                    unit_id: tuple(attachments)
                    for unit_id, attachments in self.unit_sensor_attachments.items()
                },
            ),
        )
        object.__setattr__(
            self,
            "unit_sensors",
            MappingProxyType(
                {
                    unit_id: tuple(sensors)
                    for unit_id, sensors in self.unit_sensors.items()
                },
            ),
        )


@dataclass(frozen=True, slots=True)
class BattleOODARuntime(BattleExecutionRuntime):
    """Least-privilege mutable owners used by the OODA executor."""

    rng_manager: RNGManager | None
    ooda_engine: OODALoopEngine | None
    school_registry: SchoolRegistry | None
    assessor: SituationAssessor | None
    decision_engine: DecisionEngine | None
    commander_engine: CommanderEngine | None
    planning_engine: PlanningProcessEngine | None
    stratagem_engine: StratagemEngine | None
    fog_of_war: FogOfWarManager | None
    comms_engine: CommunicationsEngine | None
    cbrn_engine: ProtectionEngine | None
    stockpile_manager: StockpileManager | None
    order_propagation: OrderPropagationEngine | None
    morale_states: Mapping[str, MoraleState]

    def __post_init__(self) -> None:
        BattleExecutionRuntime.__post_init__(self)
        object.__setattr__(
            self,
            "morale_states",
            MappingProxyType(dict(self.morale_states)),
        )


@dataclass(frozen=True, slots=True)
class BattleMovementRuntime(BattleTargetingRuntime):
    """Least-privilege mutable owners used by the movement executor."""

    movement_diagnostics: MovementDiagnostics | None
    movement_engine: MovementEngine | None
    maintenance_engine: MaintenanceEngine | None
    hydrography_manager: HydrographyManager | None
    bridge_infrastructure: InfrastructureManager | None


@dataclass(frozen=True, slots=True)
class BattleEngagementRuntime(BattleTargetingRuntime):
    """Least-privilege mutable owners used by the engagement executor."""

    rng_manager: RNGManager | None
    event_bus: EventBus | None
    engagement_engine: EngagementEngine | None
    era_runtime_contract: EraRuntimeContract | None
    morale_states: Mapping[str, MoraleState]
    morale_runtime: MoraleRuntime | None
    roe_engine: RoeEngine | None
    maintenance_engine: MaintenanceEngine | None
    suppression_engine: SuppressionEngine | None
    ew_engine: JammingEngine | None
    eccm_engine: ECCMEngine | None
    space_engine: SpaceEngine | None
    unconventional_engine: UnconventionalWarfareEngine | None
    population_engine: PopulationDensityOwner | None
    archery_engine: ArcheryEngine | None
    ato_engine: ATOPlanningEngine | None
    barrage_engine: BarrageEngine | None
    cavalry_engine: CavalryEngine | None
    dew_engine: DEWEngine | None
    formation_ancient_engine: AncientFormationEngine | None
    formation_napoleonic_engine: NapoleonicFormationEngine | None
    gas_warfare_engine: GasWarfareEngine | None
    melee_engine: MeleeEngine | None
    missile_engine: MissileEngine | None
    volley_fire_engine: VolleyFireEngine | None
    air_combat_engine: AirCombatEngine | None
    air_ground_engine: AirGroundEngine | None
    air_defense_engine: AirDefenseEngine | None
    naval_gunnery_engine: NavalGunneryEngine | None
    naval_surface_engine: NavalSurfaceEngine | None
    naval_subsurface_engine: NavalSubsurfaceEngine | None
    naval_gunfire_support_engine: NavalGunfireSupportEngine | None

    def __post_init__(self) -> None:
        BattleTargetingRuntime.__post_init__(self)
        object.__setattr__(
            self,
            "morale_states",
            MappingProxyType(dict(self.morale_states)),
        )


class PopulationDensityOwner(Protocol):
    """Narrow optional population query used by guerrilla disengagement."""

    def get_density_at(self, position: Position) -> float: ...


@dataclass(frozen=True, slots=True)
class OODAIntervalRequest:
    """Immutable inputs for one global tactical OODA interval."""

    runtime: BattleOODARuntime
    battles: tuple[BattleIntervalView, ...]
    dt_seconds: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "battles", tuple(self.battles))


@dataclass(frozen=True, slots=True)
class OODACompletionRequest:
    """Immutable inputs for ordered OODA completion processing."""

    runtime: BattleOODARuntime
    completions: tuple[tuple[str, OODAPhase], ...]
    timestamp: datetime
    battle: BattleIntervalView | None
    battle_tick: int | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "completions",
            tuple((unit_id, phase) for unit_id, phase in self.completions),
        )


@dataclass(frozen=True, slots=True)
class MovementExecutionRequest:
    """Immutable routing inputs for one battle movement transaction."""

    runtime: BattleMovementRuntime
    units_by_side: Mapping[str, Sequence[Unit]]
    active_enemies: Mapping[str, Sequence[Unit]]
    dt_seconds: float
    battle: BattleIntervalView | None
    behavior_rules: Mapping[str, ReadonlyValue] | None
    enemy_position_arrays: Mapping[str, NDArray[np.float64]] | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "units_by_side", _freeze_unit_mapping(self.units_by_side))
        object.__setattr__(self, "active_enemies", _freeze_unit_mapping(self.active_enemies))
        if self.behavior_rules is not None:
            frozen_rules = _freeze_value(self.behavior_rules)
            if not isinstance(frozen_rules, Mapping):
                raise TypeError("behavior_rules must be a mapping")
            object.__setattr__(self, "behavior_rules", frozen_rules)
        object.__setattr__(
            self,
            "enemy_position_arrays",
            _freeze_position_arrays(self.enemy_position_arrays),
        )


@dataclass(frozen=True, slots=True)
class EngagementExecutionRequest:
    """Immutable routing inputs for one ordered engagement transaction."""

    runtime: BattleEngagementRuntime
    units_by_side: Mapping[str, Sequence[Unit]]
    active_enemies: Mapping[str, Sequence[Unit]]
    enemy_position_arrays: Mapping[str, NDArray[np.float64]]
    dt_seconds: float
    timestamp: datetime
    unit_index: Mapping[str, Unit] | None
    battle: BattleIntervalView | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "units_by_side", _freeze_unit_mapping(self.units_by_side))
        object.__setattr__(self, "active_enemies", _freeze_unit_mapping(self.active_enemies))
        frozen_arrays = _freeze_position_arrays(self.enemy_position_arrays)
        if frozen_arrays is None:
            raise TypeError("engagement enemy position arrays are required")
        object.__setattr__(self, "enemy_position_arrays", frozen_arrays)
        if self.unit_index is not None:
            object.__setattr__(
                self,
                "unit_index",
                MappingProxyType(dict(self.unit_index)),
            )


@dataclass(frozen=True, slots=True)
class BattleCheckpointSnapshot:
    """Detached immutable view of manager-owned checkpoint fields."""

    battles: Mapping[str, BattleIntervalView]
    next_battle_id: int
    vls_launches: Mapping[str, int]
    ammo_expended: Mapping[str, int]
    pending_decisions: Mapping[str, float]
    deferred_battle_ids: Mapping[str, str]
    cached_assessments: Mapping[str, SituationAssessment]
    ticks_stationary: Mapping[str, int]
    suppression_states: Mapping[str, UnitSuppressionState]
    cumulative_casualties: Mapping[str, int]
    undigging: Mapping[str, bool]
    concealment_scores: Mapping[str, float]
    env_casualty_accum: Mapping[str, float]
    misinterpreted_orders: Mapping[str, PropagationResult]
    lod_tiers: Mapping[str, int]
    lod_pending_tiers: Mapping[str, int]
    lod_pending_counts: Mapping[str, int]
    lod_promoted: Collection[str]
    fow_observer_unit_ids: Collection[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "battles", _copy_readonly_mapping(self.battles))
        object.__setattr__(
            self,
            "vls_launches",
            _copy_readonly_mapping(self.vls_launches),
        )
        object.__setattr__(
            self,
            "ammo_expended",
            _copy_readonly_mapping(self.ammo_expended),
        )
        object.__setattr__(
            self,
            "pending_decisions",
            _copy_readonly_mapping(self.pending_decisions),
        )
        object.__setattr__(
            self,
            "deferred_battle_ids",
            _copy_readonly_mapping(self.deferred_battle_ids),
        )
        object.__setattr__(
            self,
            "cached_assessments",
            _deepcopy_readonly_mapping(self.cached_assessments),
        )
        object.__setattr__(
            self,
            "ticks_stationary",
            _copy_readonly_mapping(self.ticks_stationary),
        )
        object.__setattr__(
            self,
            "suppression_states",
            _deepcopy_readonly_mapping(self.suppression_states),
        )
        object.__setattr__(
            self,
            "cumulative_casualties",
            _copy_readonly_mapping(self.cumulative_casualties),
        )
        object.__setattr__(self, "undigging", _copy_readonly_mapping(self.undigging))
        object.__setattr__(
            self,
            "concealment_scores",
            _copy_readonly_mapping(self.concealment_scores),
        )
        object.__setattr__(
            self,
            "env_casualty_accum",
            _copy_readonly_mapping(self.env_casualty_accum),
        )
        object.__setattr__(
            self,
            "misinterpreted_orders",
            _deepcopy_readonly_mapping(self.misinterpreted_orders),
        )
        object.__setattr__(self, "lod_tiers", _copy_readonly_mapping(self.lod_tiers))
        object.__setattr__(
            self,
            "lod_pending_tiers",
            _copy_readonly_mapping(self.lod_pending_tiers),
        )
        object.__setattr__(
            self,
            "lod_pending_counts",
            _copy_readonly_mapping(self.lod_pending_counts),
        )
        object.__setattr__(self, "lod_promoted", frozenset(self.lod_promoted))
        object.__setattr__(
            self,
            "fow_observer_unit_ids",
            frozenset(self.fow_observer_unit_ids),
        )


@dataclass(frozen=True, slots=True)
class BattleCheckpointStageRequest:
    """Immutable, detached inputs governing one checkpoint validation."""

    state: Mapping[str, CheckpointValue]
    allow_legacy: bool
    expected_unit_ids: Collection[str] | None
    expected_sides: Collection[str] | None
    required_assessment_ids: Collection[str] | None
    checkpoint_time: datetime | None
    checkpoint_elapsed_s: float | None
    deferred_ooda_ids: Collection[str] | None

    def __post_init__(self) -> None:
        frozen_state = _freeze_checkpoint_value(self.state)
        if not isinstance(frozen_state, Mapping):
            raise TypeError("checkpoint state must be a mapping")
        object.__setattr__(self, "state", frozen_state)
        if self.expected_unit_ids is not None:
            object.__setattr__(
                self,
                "expected_unit_ids",
                frozenset(self.expected_unit_ids),
            )
        if self.expected_sides is not None:
            object.__setattr__(
                self,
                "expected_sides",
                frozenset(self.expected_sides),
            )
        if self.required_assessment_ids is not None:
            object.__setattr__(
                self,
                "required_assessment_ids",
                frozenset(self.required_assessment_ids),
            )
        if self.deferred_ooda_ids is not None:
            if not isinstance(self.deferred_ooda_ids, (set, frozenset)):
                raise ValueError(
                    "deferred_ooda_ids must be a set when provided",
                )
            object.__setattr__(
                self,
                "deferred_ooda_ids",
                frozenset(self.deferred_ooda_ids),
            )

    def detached_state(self) -> dict[str, object]:
        """Return a fresh mutable copy for the canonical validator."""
        return {
            key: _thaw_checkpoint_value(value)
            for key, value in self.state.items()
        }


class BattleExecutorOwner(Protocol):
    """Explicit manager-owned operations available to tactical executors."""

    @property
    def config_view(self) -> BattleExecutorConfigView: ...

    @property
    def movement_diagnostics(self) -> MovementDiagnostics | None: ...

    @property
    def movement_committer(self) -> MovementCommitter: ...

    def stage_performance_delta(self, contribution: PerformanceReceiptDelta) -> None: ...

    def suppress_runtime_failure(
        self,
        subsystem: str,
        operation: str,
        exception: Exception,
    ) -> bool: ...

    def lod_tier(self, unit_id: str) -> int: ...

    def is_undigging(self, unit_id: str) -> bool: ...

    def begin_undigging(self, unit_id: str) -> None: ...

    def finish_undigging(self, unit_id: str) -> None: ...

    def targeting_distance(self, shooter: Unit, target: Unit) -> float: ...

    def revalidate_tactical_engagement(
        self,
        runtime: BattleTargetingRuntime,
        attacker: Unit,
        target: Unit,
        decision: TacticalTargetingDecision,
        *,
        current_distance_m: float,
    ) -> tuple[TargetingDisposition, WeaponAttachment | None]: ...

    def compute_terrain_modifiers(
        self,
        runtime: BattleTargetingRuntime,
        target_position: Position,
        attacker_position: Position,
        *,
        seasonal_vegetation: float,
    ) -> tuple[float, float, float]: ...

    def score_target(
        self,
        attacker: Unit,
        target: Unit,
        distance_m: float,
        attacker_weapons: Collection[WeaponAttachment],
        runtime: BattleEngagementRuntime,
    ) -> float: ...

    def stage_engagement_intent(
        self,
        *,
        runtime: BattleEngagementRuntime,
        attacker: Unit,
        target: Unit,
        attachments: Collection[WeaponAttachment],
        enable_ammo_gate: bool,
        targeting_decision: TacticalTargetingDecision | None = None,
    ) -> _EngagementIntent | None: ...

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
    ) -> _EngagementIntent | None: ...

    def arbitrate_engagement_intents(
        self,
        intents: Collection[_EngagementIntent],
        *,
        target_selection_mode: str,
    ) -> _EngagementIntent | None: ...

    def publish_tactical_revalidation(
        self,
        runtime: TacticalTargetingRuntime,
        decision: TacticalTargetingDecision,
        disposition: TargetingDisposition,
    ) -> TacticalEngagementRevalidationOutcome: ...

    def targeting_visibility_bound(
        self,
        runtime: BattleTargetingRuntime,
        *,
        calibration: Mapping[str, object] | None = None,
    ) -> float: ...

    def find_unit_side(self, runtime: BattleOODARuntime, unit_id: str) -> str: ...

    def compute_c2_effectiveness(
        self,
        runtime: BattleOODARuntime,
        unit_id: str,
        side: str,
    ) -> float: ...

    def get_unit_morale_level(self, runtime: BattleOODARuntime, unit_id: str) -> float: ...

    def get_unit_supply_level(self, runtime: BattleOODARuntime, unit_id: str) -> float: ...

    def build_assessment_summary(
        self,
        runtime: BattleOODARuntime,
        unit_id: str,
        assessment: SituationAssessment | None,
    ) -> dict[str, float]: ...

    def cached_assessment(self, unit_id: str) -> SituationAssessment | None: ...

    def cache_assessment(self, unit_id: str, assessment: SituationAssessment) -> None: ...

    def validate_deferred_ooda_state(self) -> None: ...

    def deferred_ooda_owner_items(self) -> tuple[tuple[str, str], ...]: ...

    def deferred_ooda_owner(self, unit_id: str) -> str | None: ...

    def advance_ooda_completion(
        self,
        runtime: BattleOODARuntime,
        *,
        unit_id: str,
        school: DoctrinalSchool | None,
        tactical_mult: float,
        timestamp: datetime,
    ) -> None: ...

    def propagate_ooda_decision(
        self,
        runtime: BattleOODARuntime,
        *,
        unit_id: str,
        timestamp: datetime,
    ) -> PropagationResult | None: ...

    def deferred_decision(self, unit_id: str) -> DeferredOODADecision | None: ...

    def queue_deferred_decision(
        self,
        *,
        unit_id: str,
        battle: BattleIntervalView,
        logical_time_s: float,
        propagation: PropagationResult,
    ) -> DeferredOODADecision: ...

    def bind_deferred_ooda_owner(
        self,
        *,
        unit_id: str,
        battle: BattleIntervalView,
    ) -> None: ...

    def pop_deferred_decision(self, unit_id: str) -> DeferredOODADecision | None: ...

    def concealment_score(self, target_id: str, fallback: float) -> float: ...

    def update_legacy_concealment(
        self,
        target_id: str,
        *,
        terrain_concealment: float,
        target_is_moving: bool,
        observation_decay: float,
    ) -> float: ...

    def ammunition_expenditure(self, key: str, *, fallback_key: str | None = None) -> int: ...

    def record_ammunition_expenditure(
        self,
        key: str,
        quantity: int,
        *,
        fallback_key: str | None = None,
    ) -> None: ...

    def cumulative_casualties(self, unit_id: str) -> int: ...

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
    ) -> None: ...

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
    ) -> None: ...

    def apply_aggregate_suppression(
        self,
        runtime: BattleEngagementRuntime,
        target: Unit,
        weapon: WeaponInstance,
        range_m: float,
        dt_seconds: float,
    ) -> None: ...

    def suppression_state(self, unit_id: str) -> UnitSuppressionState: ...

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
    ) -> tuple[bool, UnitStatus | None]: ...

    def checkpoint_snapshot(self) -> BattleCheckpointSnapshot: ...

    @property
    def checkpoint_owner_id(self) -> int: ...

    @property
    def performance_effective_flags(self) -> EffectivePerformanceFlags: ...

    @property
    def performance_tactical_interval_microseconds(self) -> int: ...

    def checkpoint_performance_state(self) -> dict[str, object]: ...

    def stage_performance_receipt_state(
        self,
        state: object,
    ) -> PerformanceReceiptRestorePlan: ...

    def apply_checkpoint_plan(self, plan: BattleStatePlan) -> None: ...


class BattleOODAExecutor(Protocol):
    """Advance global OODA state and process ordered completions."""

    def execute_interval(self, owner: BattleExecutorOwner, request: OODAIntervalRequest) -> None: ...

    def process_completions(self, owner: BattleExecutorOwner, request: OODACompletionRequest) -> None: ...


class BattleMovementExecutor(Protocol):
    """Execute ordered movement work for one battle."""

    def execute(self, owner: BattleExecutorOwner, request: MovementExecutionRequest) -> None: ...


class BattleEngagementExecutor(Protocol):
    """Stage and resolve ordered engagements for one battle."""

    def execute(
        self,
        owner: BattleExecutorOwner,
        request: EngagementExecutionRequest,
    ) -> list[tuple[Unit, UnitStatus, str]]: ...


class BattleCheckpointExecutor(Protocol):
    """Capture, validate, and atomically commit battle checkpoints."""

    def get_state(self, owner: BattleExecutorOwner) -> dict[str, object]: ...

    def stage_state(
        self,
        owner: BattleExecutorOwner,
        request: BattleCheckpointStageRequest,
    ) -> BattleStatePlan: ...

    def commit_state(self, owner: BattleExecutorOwner, plan: BattleStatePlan) -> None: ...

    def set_state(
        self,
        owner: BattleExecutorOwner,
        state: Mapping[str, CheckpointValue],
        *,
        allow_legacy: bool = False,
    ) -> None: ...
