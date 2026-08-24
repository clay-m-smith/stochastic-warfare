"""Runtime-owned simulation context and atomic checkpoint transaction."""

from __future__ import annotations

import copy
import math
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from stochastic_warfare.c2.ai.commander import (
    CommanderAssignmentPlan,
)
from stochastic_warfare.core.clock import (
    SimulationClock,
)
from stochastic_warfare.core.era import EraConfig
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.detection.sensors import SensorInstance
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.morale.rout import RoutEngine
from stochastic_warfare.morale.runtime import (
    MoraleRuntime,
)
from stochastic_warfare.morale.state import MoraleState
from stochastic_warfare.simulation.aggregation import (
    AggregationConfig,
    AggregationEngine,
    unsupported_aggregation_owner_names,
)
from stochastic_warfare.simulation.calibration import (
    CalibrationSchema,
    ResolvedCalibration,
)
from stochastic_warfare.simulation.era_runtime import (
    EraExecutionHorizonSource,
    EraRuntimeContract,
    EraRuntimeSource,
)
from stochastic_warfare.simulation.force_builder import (
    RuntimeForceBuilder,
)
from stochastic_warfare.simulation.loadouts import (
    EquipmentResolution,
    RuntimeLoadoutBuilder,
    RuntimeLoadouts,
    SensorAttachment,
    WeaponAttachment,
)
from stochastic_warfare.simulation.movement_diagnostics import (
    MovementDiagnostics,
)
from stochastic_warfare.simulation.context_checkpoint import (
    _CONTEXT_STATE_ENGINE_NAMES,
    CapturedCheckpointOwnerState,
    CheckpointOwnerDisposition,
    ContextCheckpointOwnerBinding,
    ContextCheckpointSnapshot,
    LegacyCheckpointRestorePlan,
    _bind_context_checkpoint_owner,
    _capture_context_checkpoint_owner,
    _checkpoint_aggregate_morale_topology,
    _checkpoint_declares_empty_runtime_loadout,
    _checkpoint_has_active_routes,
    _configured_fog_of_war_enabled,
    _fog_cadence_restore_bindings,
    _fog_sensor_bindings,
    _json_values_equal,
    _commit_legacy_context_checkpoint_owner,
    _migrate_legacy_morale_runtime,
    _model_dump_json_compatible,
    _normalize_targeting_battle_memberships,
    _prospective_targeting_visibility_bound_m,
    _stage_checkpoint_unit,
    _stage_legacy_context_checkpoint_owner,
    _stage_runtime_instance_states,
    _targeting_interval_is_current,
    _targeting_visibility_bound_m,
    _validate_fow_targeting_bindings,
    _validate_movement_targeting_restore_bindings,
    _validate_runtime_loadout_object_bindings,
    _validate_targeting_live_bindings,
)
from stochastic_warfare.simulation.scenario_config import (
    CampaignScenarioConfig,
    DoctrineSideAssignment,
    _doctrine_policy_index,
    parse_scenario_start_time,
)
from stochastic_warfare.simulation.tactical_targeting import (
    DEFAULT_TARGETING_VISIBILITY_M,
    TacticalTargetingRestorePlan,
    TacticalTargetingRuntime,
)
from stochastic_warfare.terrain.heightmap import Heightmap

if TYPE_CHECKING:
    from stochastic_warfare.detection.fog_of_war import (
        FogOfWarRestorePlan,
    )


@dataclass(frozen=True)
class SimulationContextStatePlan:
    """Validated, owner-bound whole-context checkpoint plan."""

    owner_id: int
    state: dict[str, Any]
    allow_legacy_morale: bool
    targeting_battle_membership_items: tuple[tuple[str, tuple[str, ...]], ...] | None
    require_current_targeting_interval: bool
    fow_observer_unit_ids: frozenset[str] | None
    battle_lod_tier_items: tuple[tuple[str, int], ...] | None


@dataclass
class SimulationContext:
    """Shared state for an in-progress simulation run.

    Holds configuration, core infrastructure, domain engines, and forces.
    Passed to :class:`BattleManager` and :class:`CampaignManager` as the
    single context object for each tick.
    """

    config: CampaignScenarioConfig
    clock: SimulationClock
    rng_manager: RNGManager
    event_bus: EventBus

    # Terrain
    heightmap: Heightmap | None = None
    los_engine: Any = None
    classification: Any = None
    infrastructure_manager: Any = None
    bathymetry: Any = None
    obstacle_manager: Any = None
    hydrography_manager: Any = None
    population_manager: Any = None

    # Suppression (Phase 40e)
    suppression_engine: Any = None

    # Forces
    units_by_side: dict[str, list[Unit]] = field(default_factory=dict)
    unit_weapons: dict[str, tuple[WeaponAttachment, ...]] = field(
        default_factory=dict,
    )
    unit_sensor_attachments: dict[
        str,
        tuple[SensorAttachment, ...],
    ] = field(default_factory=dict)
    unit_sensors: dict[str, tuple[SensorInstance, ...]] = field(
        default_factory=dict,
    )
    equipment_resolutions: dict[
        str,
        tuple[EquipmentResolution, ...],
    ] = field(default_factory=dict)
    force_builder: RuntimeForceBuilder | None = None
    loadout_builder: RuntimeLoadoutBuilder | None = None
    morale_states: Mapping[str, MoraleState] = field(
        default_factory=dict,
        repr=False,
    )

    # Environment engines
    weather_engine: Any = None
    time_of_day_engine: Any = None
    seasons_engine: Any = None
    sea_state_engine: Any = None
    obscurants_engine: Any = None
    conditions_engine: Any = None  # Used by SpaceEngine — keep

    # Combat
    engagement_engine: Any = None

    # Detection
    detection_engine: Any = None
    fog_of_war: Any = None

    # Movement
    movement_engine: Any = None
    movement_diagnostics: MovementDiagnostics | None = None
    tactical_targeting: TacticalTargetingRuntime | None = None
    targeting_default_visibility_m: float = DEFAULT_TARGETING_VISIBILITY_M

    # Morale
    morale_runtime: MoraleRuntime | None = None

    # ROE (Phase 42a)
    roe_engine: Any = None

    # Rout (Phase 42c)
    rout_engine: RoutEngine | None = None

    # C2
    command_engine: Any = None
    comms_engine: Any = None
    order_propagation: Any = None
    order_execution: Any = None

    # AI
    ooda_engine: Any = None
    planning_engine: Any = None
    assessor: Any = None
    decision_engine: Any = None
    adaptation_engine: Any = None

    # Aggregation (Phase 13a-7)
    aggregation_engine: Any = None

    # Electronic Warfare (Phase 16)
    ew_engine: Any = None

    # Space & Satellite (Phase 17)
    space_engine: Any = None

    # CBRN (Phase 18)
    cbrn_engine: Any = None

    # Doctrinal AI Schools (Phase 19)
    school_registry: Any = None
    doctrine_side_assignments: tuple[
        DoctrineSideAssignment,
        ...,
    ] = ()

    # Commander (Phase 25)
    commander_engine: Any = None

    # EW sub-engines (Phase 25 wiring)
    eccm_engine: Any = None
    sigint_engine: Any = None
    ew_decoy_engine: Any = None

    # Era Framework (Phase 20)
    era_config: EraConfig | None = None
    era_runtime_contract: EraRuntimeContract | None = None

    # WW2 Engine Extensions (Phase 20b)
    naval_gunnery_engine: Any = None
    convoy_engine: Any = None
    strategic_bombing_engine: Any = None

    # WW1 Engine Extensions (Phase 21b)
    trench_engine: Any = None
    barrage_engine: Any = None
    gas_warfare_engine: Any = None

    # Napoleonic Engine Extensions (Phase 22b)
    volley_fire_engine: Any = None
    melee_engine: Any = None
    cavalry_engine: Any = None
    formation_napoleonic_engine: Any = None
    courier_engine: Any = None
    foraging_engine: Any = None

    # Ancient/Medieval Engine Extensions (Phase 23b)
    archery_engine: Any = None
    siege_engine: Any = None
    formation_ancient_engine: Any = None
    naval_oar_engine: Any = None
    visual_signals_engine: Any = None

    # Escalation & Unconventional (Phase 24)
    escalation_engine: Any = None
    political_engine: Any = None
    consequence_engine: Any = None
    unconventional_engine: Any = None
    insurgency_engine: Any = None
    sof_engine: Any = None
    war_termination_engine: Any = None
    incendiary_engine: Any = None
    uxo_engine: Any = None

    # Stratagems (Phase 53c)
    stratagem_engine: Any = None

    # IADS (Phase 53e)
    iads_engine: Any = None

    # ATO Planning (Phase 53d)
    ato_engine: Any = None

    # Air Combat Engines (Phase 58b)
    air_combat_engine: Any = None
    air_ground_engine: Any = None
    air_defense_engine: Any = None

    # Underwater Acoustics (Phase 61)
    underwater_acoustics_engine: Any = None

    # Carrier Ops (Phase 61)
    carrier_ops_engine: Any = None

    # Missile (Phase 63d)
    missile_engine: Any = None

    # Missile Defense (Phase 71c)
    missile_defense_engine: Any = None

    # Conditions facade (Phase 66b)
    conditions_facade: Any = None

    # Directed Energy (Phase 28.5)
    dew_engine: Any = None

    # Indirect Fire (Phase 43b)
    indirect_fire_engine: Any = None

    # Naval Engines (Phase 43c)
    naval_surface_engine: Any = None
    naval_subsurface_engine: Any = None
    naval_gunfire_support_engine: Any = None
    mine_warfare_engine: Any = None

    # Disruption (Phase 51d — blockade / interdiction)
    disruption_engine: Any = None

    # Logistics
    consumption_engine: Any = None
    stockpile_manager: Any = None
    supply_network_engine: Any = None
    logistics_runtime: Any = None
    maintenance_engine: Any = None
    medical_engine: Any = None
    engineering_engine: Any = None

    # Collateral (Phase 44d)
    collateral_engine: Any = None

    # Loaders (needed for reinforcements)
    unit_loader: Any = None
    weapon_loader: Any = None
    ammo_loader: Any = None
    sensor_loader: Any = None
    sig_loader: Any = None
    supply_item_loader: Any = None
    commander_profile_loader: Any = None

    # Calibration
    calibration: CalibrationSchema | dict[str, Any] = field(default_factory=CalibrationSchema)

    # Immutable O(1) runtime projection.  ``cal_flat`` remains a read-only
    # compatibility property below while consumers migrate to this owner.
    resolved_calibration: ResolvedCalibration | None = field(
        default=None,
        repr=False,
    )

    # Phase 101 — Fallujah urban scenario support
    scripted_events: list[Any] = field(default_factory=list)
    initial_ied_obstacle_ids: list[str] = field(default_factory=list)

    _morale_states_bound: bool = field(
        default=False,
        init=False,
        repr=False,
    )
    _era_config_identity_json: str = field(
        default="",
        init=False,
        repr=False,
    )
    _era_runtime_source_identity_json: str = field(
        default="",
        init=False,
        repr=False,
    )
    _era_execution_horizon_identity_json: str = field(
        default="",
        init=False,
        repr=False,
    )
    _era_runtime_bound: bool = field(
        default=False,
        init=False,
        repr=False,
    )
    _resolved_calibration_bound: bool = field(
        default=False,
        init=False,
        repr=False,
    )

    # ── Helpers ──────────────────────────────────────────────────────

    def __post_init__(self) -> None:
        """Bind stable era, calibration, and morale ownership graphs."""
        if isinstance(self.calibration, CalibrationSchema):
            typed_calibration = self.calibration
        elif isinstance(self.calibration, dict):
            typed_calibration = CalibrationSchema.model_validate(
                self.calibration,
            )
            object.__setattr__(self, "calibration", typed_calibration)
        else:
            raise TypeError(
                "calibration must be a CalibrationSchema or mapping",
            )
        calibration_sides = sorted(side.side for side in self.config.sides)
        expected_resolved_calibration = typed_calibration.resolve(
            calibration_sides,
        )
        if self.resolved_calibration is None:
            object.__setattr__(
                self,
                "resolved_calibration",
                expected_resolved_calibration,
            )
        elif type(self.resolved_calibration) is not ResolvedCalibration:
            raise TypeError(
                "resolved_calibration must be a ResolvedCalibration or None",
            )
        elif self.resolved_calibration != expected_resolved_calibration:
            raise ValueError(
                "resolved_calibration does not match the typed calibration and runtime sides",
            )
        if self.era_config is None:
            try:
                effective_era_config = EraConfig(era=self.config.era)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "A manually assembled context with a custom era ID must supply its captured EraConfig explicitly",
                ) from exc
        elif isinstance(self.era_config, EraConfig):
            effective_era_config = EraConfig.model_validate(
                self.era_config.model_dump(mode="python"),
                strict=True,
                extra="forbid",
            )
        else:
            raise TypeError("era_config must be an EraConfig or None")
        runtime_source = EraRuntimeSource(
            selected_registry_id=self.config.era,
            strategic_s=self.config.tick_resolution.strategic_s,
            operational_s=self.config.tick_resolution.operational_s,
            tactical_s=self.config.tick_resolution.tactical_s,
            tick_duration_seconds=self.config.tick_duration_seconds,
        )
        horizon_source = EraExecutionHorizonSource(
            date=self.config.date,
            duration_hours=self.config.duration_hours,
        )
        expected_era_contract = EraRuntimeContract.resolve(
            era_config=effective_era_config,
            **runtime_source.model_dump(mode="python"),
        )
        expected_era_contract.validate_execution_horizon(
            start=parse_scenario_start_time(horizon_source.date),
            duration_hours=horizon_source.duration_hours,
        )
        if self.era_runtime_contract is None:
            object.__setattr__(
                self,
                "era_runtime_contract",
                expected_era_contract,
            )
        elif not isinstance(
            self.era_runtime_contract,
            EraRuntimeContract,
        ):
            raise TypeError(
                "era_runtime_contract must be an EraRuntimeContract",
            )
        elif self.era_runtime_contract != expected_era_contract:
            raise ValueError(
                "era_runtime_contract does not match the context's scenario and captured era configuration",
            )
        object.__setattr__(
            self,
            "_era_config_identity_json",
            effective_era_config.model_dump_json(),
        )
        object.__setattr__(
            self,
            "_era_runtime_source_identity_json",
            runtime_source.model_dump_json(),
        )
        object.__setattr__(
            self,
            "_era_execution_horizon_identity_json",
            horizon_source.model_dump_json(),
        )

        initial_projection = dict(self.morale_states)
        if self.morale_runtime is None:
            if initial_projection:
                raise ValueError(
                    "A non-empty morale projection requires MoraleRuntime",
                )
            morale_view: Mapping[str, MoraleState] = MappingProxyType({})
        else:
            morale_view = self.morale_runtime.states
            if initial_projection and initial_projection != dict(morale_view):
                raise ValueError(
                    "Initial morale projection disagrees with MoraleRuntime",
                )
            authoritative_rng = self.rng_manager.get_stream(ModuleId.MORALE)
            if self.morale_runtime.rng is not authoritative_rng:
                raise ValueError(
                    "MoraleRuntime must use RNGManager's MORALE generator",
                )
            if self.rout_engine is not None and self.rout_engine.rng is not authoritative_rng:
                raise ValueError(
                    "RoutEngine must use RNGManager's MORALE generator",
                )
            if self.morale_runtime.rout_engine is not self.rout_engine:
                raise ValueError(
                    "MoraleRuntime and SimulationContext must share RoutEngine",
                )
        object.__setattr__(self, "morale_states", morale_view)
        self._validate_morale_bindings()
        self.validate_era_runtime_bindings()
        object.__setattr__(self, "_morale_states_bound", True)
        object.__setattr__(self, "_era_runtime_bound", True)
        object.__setattr__(self, "_resolved_calibration_bound", True)

    def __setattr__(self, name: str, value: Any) -> None:
        """Prevent replacement of bound runtime ownership graphs."""
        if name in {"morale_states", "morale_runtime", "rout_engine"} and getattr(self, "_morale_states_bound", False):
            raise AttributeError(
                f"{name} is a stable MoraleRuntime ownership binding",
            )
        if name in {"era_config", "era_runtime_contract"} and getattr(self, "_era_runtime_bound", False):
            raise AttributeError(
                f"{name} is a stable EraRuntimeContract ownership binding",
            )
        if name in {"calibration", "resolved_calibration", "cal_flat"} and getattr(
            self,
            "_resolved_calibration_bound",
            False,
        ):
            raise AttributeError(
                f"{name} is a stable ResolvedCalibration ownership binding",
            )
        object.__setattr__(self, name, value)

    @property
    def cal_flat(self) -> ResolvedCalibration:
        """Return the immutable compatibility view of runtime calibration."""
        resolved = self.resolved_calibration
        if type(resolved) is not ResolvedCalibration:
            raise RuntimeError("SimulationContext lacks ResolvedCalibration")
        return resolved

    def _captured_era_config(self) -> EraConfig:
        """Return the isolated era identity captured at construction."""
        return EraConfig.model_validate_json(
            self._era_config_identity_json,
            strict=True,
            extra="forbid",
        )

    def _captured_era_runtime_source(self) -> EraRuntimeSource:
        """Return the exact scenario-side inputs captured at construction."""
        return EraRuntimeSource.model_validate_json(
            self._era_runtime_source_identity_json,
            strict=True,
            extra="forbid",
        )

    def _captured_era_execution_horizon(
        self,
    ) -> EraExecutionHorizonSource:
        """Return exact scenario inputs bounding executable clock time."""
        return EraExecutionHorizonSource.model_validate_json(
            self._era_execution_horizon_identity_json,
            strict=True,
            extra="forbid",
        )

    def validate_era_runtime_bindings(self) -> None:
        """Fail closed when captured era behavior diverges from consumers."""
        contract = self.era_runtime_contract
        if not isinstance(contract, EraRuntimeContract):
            raise RuntimeError("SimulationContext lacks EraRuntimeContract")
        captured_era = self._captured_era_config()
        captured_source = self._captured_era_runtime_source()
        try:
            current_source = EraRuntimeSource(
                selected_registry_id=self.config.era,
                strategic_s=self.config.tick_resolution.strategic_s,
                operational_s=self.config.tick_resolution.operational_s,
                tactical_s=self.config.tick_resolution.tactical_s,
                tick_duration_seconds=self.config.tick_duration_seconds,
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise RuntimeError(
                "Scenario era runtime source is no longer valid",
            ) from exc
        if current_source != captured_source:
            raise RuntimeError(
                "Scenario era runtime source changed after runtime construction",
            )
        captured_horizon = self._captured_era_execution_horizon()
        try:
            current_horizon = EraExecutionHorizonSource.model_validate(
                {
                    "date": self.config.date,
                    "duration_hours": self.config.duration_hours,
                },
                strict=True,
                extra="forbid",
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise RuntimeError(
                "Scenario clock execution horizon is no longer valid",
            ) from exc
        if current_horizon != captured_horizon:
            raise RuntimeError(
                "Scenario clock execution horizon changed after runtime construction",
            )
        expected = EraRuntimeContract.resolve(
            era_config=captured_era,
            **captured_source.model_dump(mode="python"),
        )
        if contract != expected:
            raise RuntimeError(
                "Scenario, captured era configuration, and runtime contract have diverged",
            )
        if self.era_config is not None:
            try:
                current_era = EraConfig.model_validate(
                    self.era_config.model_dump(mode="python"),
                    strict=True,
                    extra="forbid",
                )
            except (AttributeError, TypeError, ValueError) as exc:
                raise RuntimeError(
                    "Captured era configuration is no longer valid",
                ) from exc
            if current_era != captured_era:
                raise RuntimeError(
                    "Captured era configuration changed after runtime construction",
                )
        if self.loadout_builder is not None and self.loadout_builder.era_config != captured_era:
            raise RuntimeError(
                "RuntimeLoadoutBuilder era gates diverge from the captured era configuration",
            )

        if self.medical_engine is not None:
            from stochastic_warfare.logistics.medical import MedicalConfig

            medical_config = getattr(self.medical_engine, "config", None)
            if not isinstance(medical_config, MedicalConfig) or any(
                getattr(medical_config, field_name) != getattr(contract, field_name)
                for field_name in (
                    "treatment_hours_minor",
                    "treatment_hours_serious",
                    "treatment_hours_critical",
                )
            ):
                raise RuntimeError(
                    "MedicalEngine configuration diverges from EraRuntimeContract",
                )
        if self.maintenance_engine is not None:
            from stochastic_warfare.logistics.maintenance import (
                MaintenanceConfig,
            )

            maintenance_config = getattr(
                self.maintenance_engine,
                "config",
                None,
            )
            if (
                not isinstance(maintenance_config, MaintenanceConfig)
                or maintenance_config.repair_time_hours != contract.repair_time_hours
            ):
                raise RuntimeError(
                    "MaintenanceEngine configuration diverges from EraRuntimeContract",
                )

    def _morale_roster(self) -> dict[str, Unit]:
        """Return the exact active roster, rejecting duplicate entity IDs."""
        roster: dict[str, Unit] = {}
        for unit in self.all_units():
            if unit.entity_id in roster:
                raise ValueError(
                    f"Duplicate runtime entity_id {unit.entity_id!r}",
                )
            roster[unit.entity_id] = unit
        return roster

    def _validate_loadout_bindings(self) -> None:
        """Require one atomic typed loadout projection for the full roster."""
        roster = self._morale_roster()
        roster_ids = set(roster)
        loadout_maps = {
            "unit_weapons": set(self.unit_weapons),
            "unit_sensor_attachments": set(self.unit_sensor_attachments),
            "unit_sensors": set(self.unit_sensors),
            "equipment_resolutions": set(self.equipment_resolutions),
        }
        if not roster_ids and not any(loadout_maps.values()):
            return
        for name, unit_ids in loadout_maps.items():
            if unit_ids != roster_ids:
                raise ValueError(
                    f"SimulationContext {name} topology disagrees with the "
                    "runtime roster: "
                    f"missing={sorted(roster_ids - unit_ids)!r}, "
                    f"extra={sorted(unit_ids - roster_ids)!r}",
                )
        validated = RuntimeLoadouts(
            unit_weapons=self.unit_weapons,
            unit_sensor_attachments=self.unit_sensor_attachments,
            equipment_resolutions=self.equipment_resolutions,
        )
        _validate_runtime_loadout_object_bindings(
            units=roster,
            loadouts=validated,
        )
        for unit_id in sorted(roster_ids):
            attachments = self.unit_sensor_attachments[unit_id]
            projection = self.unit_sensors[unit_id]
            if len(attachments) != len(projection) or any(
                attachment.sensor is not sensor for attachment, sensor in zip(attachments, projection)
            ):
                raise ValueError(
                    f"SimulationContext sensor projection for {unit_id!r} is detached from its typed attachments",
                )
            if any(
                validated_attachment is not attachment
                for validated_attachment, attachment in zip(
                    validated.unit_sensor_attachments[unit_id],
                    attachments,
                )
            ):
                raise ValueError(
                    f"SimulationContext sensor attachments for {unit_id!r} changed identity during validation",
                )

    def _validate_targeting_registration(
        self,
    ) -> TacticalTargetingRuntime | None:
        """Require targeting registration to equal the authoritative roster."""
        runtime = self.tactical_targeting
        if runtime is None:
            if self.all_units():
                raise RuntimeError(
                    "A non-empty production roster requires tactical targeting",
                )
            return None
        expected: dict[str, str] = {}
        for bucket_side, units in self.units_by_side.items():
            for unit in units:
                unit_side = unit.side if isinstance(unit.side, str) else unit.side.value
                if unit_side != bucket_side:
                    raise ValueError(
                        f"Tactical targeting roster bucket disagrees with unit side for {unit.entity_id!r}",
                    )
                if unit.entity_id in expected:
                    raise ValueError(
                        f"Tactical targeting roster contains duplicate entity_id {unit.entity_id!r}",
                    )
                expected[unit.entity_id] = unit_side
        if dict(runtime.registered_unit_sides) != dict(sorted(expected.items())):
            raise ValueError(
                "Tactical targeting registration disagrees with the runtime unit/side topology",
            )
        return runtime

    def _capture_targeting_checkpoint_snapshot(
        self,
        *,
        targeting_state: object | None,
        authoritative_detection_rng_state: object,
        authoritative_detection_scan_counts: object,
        observer_unit_ids: Collection[str] | None = None,
        lod_tiers: Mapping[str, int] | None = None,
    ) -> tuple[
        TacticalTargetingRestorePlan | None,
        object | None,
        FogOfWarRestorePlan | None,
    ]:
        """Stage one captured targeting/FOW graph and validate its bindings."""
        if (observer_unit_ids is None) != (lod_tiers is None):
            raise ValueError(
                "FOW observer and Battle LOD checkpoint sidecars must be supplied together",
            )
        runtime = self._validate_targeting_registration()
        if runtime is None:
            return None, None, None
        plan = runtime.stage_state(targeting_state)
        interval_is_current = _targeting_interval_is_current(
            plan=plan,
            clock_tick=self.clock.tick_count,
            logical_time_s=self.clock.elapsed.total_seconds(),
        )
        calibration = self.cal_flat
        roster = self._morale_roster()
        loadouts = RuntimeLoadouts(
            unit_weapons=self.unit_weapons,
            unit_sensor_attachments=self.unit_sensor_attachments,
            equipment_resolutions=self.equipment_resolutions,
        )
        _validate_targeting_live_bindings(
            plan=plan,
            units=roster,
            loadouts=loadouts,
            calibration=calibration,
            live_visibility_m=(
                _targeting_visibility_bound_m(
                    calibration=calibration,
                    weather_engine=self.weather_engine,
                    default_visibility_m=self.targeting_default_visibility_m,
                )
                if interval_is_current
                else None
            ),
        )
        expected_fog_of_war_enabled = _configured_fog_of_war_enabled(
            calibration,
        )
        if expected_fog_of_war_enabled and self.fog_of_war is None:
            raise ValueError(
                "enabled fog-of-war requires a live FogOfWarManager owner",
            )
        fog_plan: FogOfWarRestorePlan | None = None
        captured_fog_state: object | None = None
        if self.fog_of_war is not None:
            unit_sides = {
                unit_id: (unit.side if isinstance(unit.side, str) else unit.side.value)
                for unit_id, unit in roster.items()
            }
            satellite_topology = (
                {
                    satellite.satellite_id: (
                        satellite.side,
                        satellite.constellation_id,
                    )
                    for satellite in (self.space_engine.constellation_manager.all_satellites())
                }
                if self.space_engine is not None
                else {}
            )
            cadence_sensor_bindings = None
            cadence_bindings = None
            native_phase_bindings = None
            if observer_unit_ids is not None and lod_tiers is not None:
                (
                    cadence_sensor_bindings,
                    cadence_bindings,
                    native_phase_bindings,
                ) = _fog_cadence_restore_bindings(
                    observer_unit_ids=observer_unit_ids,
                    lod_tiers=lod_tiers,
                    calibration=calibration,
                    unit_sides=unit_sides,
                    loadouts=loadouts,
                )
            expected_sides = set(self.side_names())
            expected_sensor_bindings = _fog_sensor_bindings(
                unit_sides=unit_sides,
                loadouts=loadouts,
            )
            fog_snapshot = self.fog_of_war.capture_checkpoint_snapshot(
                expected_sides=expected_sides,
                expected_target_sides=unit_sides,
                satellite_topology=satellite_topology,
                checkpoint_elapsed_s=self.clock.elapsed.total_seconds(),
                authoritative_rng_state=authoritative_detection_rng_state,
                expected_sensor_bindings=expected_sensor_bindings,
                expected_cadence_sensor_bindings=(cadence_sensor_bindings),
                expected_cadence_bindings=cadence_bindings,
                expected_native_phase_bindings=native_phase_bindings,
                authoritative_detection_scan_counts=(authoritative_detection_scan_counts),
            )
            captured_fog_state = fog_snapshot.state
            fog_plan = fog_snapshot.plan
            _validate_fow_targeting_bindings(
                targeting_plan=plan,
                fog_plan=fog_plan,
                expected_fog_of_war_enabled=(expected_fog_of_war_enabled),
                units=roster,
                support_process_noise_std_mps2=(self.fog_of_war.observer_track_support_process_noise_std_mps2),
                support_max_position_uncertainty_m=(self.fog_of_war.observer_track_support_max_position_uncertainty_m),
            )
        return plan, captured_fog_state, fog_plan

    def _validate_targeting_bindings(self) -> None:
        """Require complete targeting state and live attachment bindings."""
        rng_state = self.rng_manager.get_state()
        detection_rng_state = (
            rng_state["streams"][ModuleId.DETECTION.value]
            if self.fog_of_war is not None or self.detection_engine is not None
            else None
        )
        self._capture_targeting_checkpoint_snapshot(
            targeting_state=(
                None
                if self.tactical_targeting is None
                else self.tactical_targeting.get_state()
            ),
            authoritative_detection_rng_state=detection_rng_state,
            authoritative_detection_scan_counts=(
                {}
                if self.detection_engine is None
                else self.detection_engine.get_scan_count_state()
            ),
        )

    def validate_fow_cadence_checkpoint_bindings(
        self,
        *,
        observer_unit_ids: Collection[str],
        lod_tiers: Mapping[str, int],
    ) -> None:
        """Bind captured FOW cadence to current loadouts and Battle tiers."""
        if self.fog_of_war is None:
            if observer_unit_ids:
                raise ValueError(
                    "FOW observers require a FogOfWarManager owner",
                )
            return
        rng_state = self.rng_manager.get_state()
        detection_rng_state = rng_state["streams"][ModuleId.DETECTION.value]
        self._capture_targeting_checkpoint_snapshot(
            targeting_state=(
                None
                if self.tactical_targeting is None
                else self.tactical_targeting.get_state()
            ),
            authoritative_detection_rng_state=detection_rng_state,
            authoritative_detection_scan_counts=(
                {}
                if self.detection_engine is None
                else self.detection_engine.get_scan_count_state()
            ),
            observer_unit_ids=observer_unit_ids,
            lod_tiers=lod_tiers,
        )

    def _validate_morale_bindings(
        self,
        *,
        require_runtime_for_roster: bool = False,
    ) -> None:
        """Fail closed when context, runtime, rout, RNG, or roster diverge."""
        roster = self._morale_roster()
        runtime = self.morale_runtime
        if runtime is None:
            if self.morale_states:
                raise ValueError(
                    "A null MoraleRuntime requires an empty morale view",
                )
            if require_runtime_for_roster and roster:
                raise RuntimeError(
                    "A non-empty roster requires MoraleRuntime ownership",
                )
            return

        if self.morale_states is not runtime.states:
            raise ValueError(
                "SimulationContext morale view is detached from MoraleRuntime",
            )
        authoritative_rng = self.rng_manager.get_stream(ModuleId.MORALE)
        if runtime.rng is not authoritative_rng:
            raise ValueError(
                "MoraleRuntime must use RNGManager's MORALE generator",
            )
        if runtime.rout_engine is not self.rout_engine:
            raise ValueError(
                "MoraleRuntime and SimulationContext must share RoutEngine",
            )
        runtime.validate_bindings(roster)

    def all_units(self) -> list[Unit]:
        """Return a flat list of all units across all sides."""
        result: list[Unit] = []
        for units in self.units_by_side.values():
            result.extend(units)
        return result

    def active_units(self, side: str) -> list[Unit]:
        """Return active units for *side*."""
        return [u for u in self.units_by_side.get(side, []) if u.status == UnitStatus.ACTIVE]

    def side_names(self) -> list[str]:
        """Return sorted side names."""
        return sorted(self.units_by_side.keys())

    # ── State persistence ────────────────────────────────────────────

    def _checkpoint_engines(self) -> tuple[tuple[str, Any], ...]:
        """Return the legacy name/owner compatibility projection."""
        return tuple((name, getattr(self, name)) for name in _CONTEXT_STATE_ENGINE_NAMES)

    def _checkpoint_owner_bindings(
        self,
    ) -> tuple[ContextCheckpointOwnerBinding, ...]:
        """Bind the ordered registry to explicit atomicity protocols."""
        return tuple(
            _bind_context_checkpoint_owner(name, getattr(self, name))
            for name in _CONTEXT_STATE_ENGINE_NAMES
        )

    def _validate_detection_checkpoint_owner(
        self,
        *,
        owner_state: object | None = None,
        rng_state: dict[str, Any] | None = None,
    ) -> None:
        """Require the exact RNG-bound detection owner before persistence."""
        owner = self.detection_engine
        if owner is None:
            if self.fog_of_war is not None:
                raise ValueError(
                    "FogOfWarManager requires a context DetectionEngine owner",
                )
            return
        from stochastic_warfare.detection.detection import DetectionEngine

        if type(owner) is not DetectionEngine:
            raise ValueError(
                "Checkpoint detection_engine must be an exact DetectionEngine",
            )
        authoritative_rng = self.rng_manager.get_stream(ModuleId.DETECTION)
        if rng_state is None:
            rng_state = self.rng_manager.get_state()
        authoritative_rng_state = rng_state["streams"][ModuleId.DETECTION.value]
        if getattr(owner, "_rng", None) is not authoritative_rng:
            raise ValueError(
                "DetectionEngine must use RNGManager's DETECTION generator",
            )
        if owner_state is None:
            owner_state = owner.get_state()
        if not isinstance(owner_state, dict):
            raise ValueError(
                "DetectionEngine checkpoint state must be a mapping",
            )
        if not _json_values_equal(
            owner_state.get("rng_state"),
            authoritative_rng_state,
        ):
            raise ValueError(
                "DetectionEngine RNG mirror disagrees with RNGManager DETECTION state",
            )
        if self.fog_of_war is not None:
            self.fog_of_war.validate_runtime_bindings(
                detection_engine=owner,
                authoritative_rng=authoritative_rng,
            )
            self.fog_of_war.validate_checkpoint_boundary()

    def _capture_checkpoint_snapshot(
        self,
        *,
        fow_observer_unit_ids: Collection[str] | None,
        battle_lod_tiers: Mapping[str, int] | None,
    ) -> ContextCheckpointSnapshot:
        """Capture each registered owner once and preflight that exact graph."""
        if (fow_observer_unit_ids is None) != (battle_lod_tiers is None):
            raise ValueError(
                "FOW observer and Battle LOD checkpoint sidecars must be supplied together",
            )
        bindings = self._checkpoint_owner_bindings()
        rng_state = self.rng_manager.get_state()
        captured_states = {
            binding.name: _capture_context_checkpoint_owner(binding)
            for binding in bindings
            if (
                binding.name != "fog_of_war"
                and binding.owner is not None
                and binding.disposition is not CheckpointOwnerDisposition.STATELESS
                and not (
                    binding.name in {"stockpile_manager", "supply_network_engine"}
                    and self.logistics_runtime is not None
                )
            )
        }
        detection_state = captured_states.get("detection_engine")
        detection_scan_counts = (
            detection_state.get("scan_counts", {})
            if isinstance(detection_state, dict)
            else {}
        )
        detection_rng_state = (
            rng_state["streams"][ModuleId.DETECTION.value]
            if self.fog_of_war is not None or self.detection_engine is not None
            else None
        )
        (
            targeting_plan,
            captured_fog_state,
            fog_plan,
        ) = self._capture_targeting_checkpoint_snapshot(
            targeting_state=captured_states.get("tactical_targeting"),
            authoritative_detection_rng_state=detection_rng_state,
            authoritative_detection_scan_counts=detection_scan_counts,
            observer_unit_ids=fow_observer_unit_ids,
            lod_tiers=battle_lod_tiers,
        )
        if self.fog_of_war is not None:
            if captured_fog_state is None:
                fog_snapshot = self.fog_of_war.capture_checkpoint_snapshot(
                    authoritative_rng_state=detection_rng_state,
                    authoritative_detection_scan_counts=(detection_scan_counts),
                )
                captured_fog_state = fog_snapshot.state
                fog_plan = fog_snapshot.plan
            captured_states["fog_of_war"] = captured_fog_state
        captured_owners = tuple(
            CapturedCheckpointOwnerState(
                binding=binding,
                state=captured_states[binding.name],
            )
            for binding in bindings
            if binding.name in captured_states
        )
        self._validate_morale_bindings(require_runtime_for_roster=True)
        self.validate_era_runtime_bindings()
        self._validate_detection_checkpoint_owner(
            owner_state=detection_state,
            rng_state=rng_state,
        )
        aggregation_state = captured_states.get("aggregation_engine")
        if isinstance(aggregation_state, dict) and aggregation_state.get("aggregates"):
            unsupported_aggregate_owners = unsupported_aggregation_owner_names(self)
            if unsupported_aggregate_owners:
                raise ValueError(
                    "REM-016: active aggregate checkpoint capture has "
                    "uncoordinated context state owners: "
                    f"{unsupported_aggregate_owners!r}",
                )
        return ContextCheckpointSnapshot(
            context_owner_id=id(self),
            rng_owner_id=id(self.rng_manager),
            rng_state=rng_state,
            owners=captured_owners,
            targeting_owner_id=(
                None
                if self.tactical_targeting is None
                else id(self.tactical_targeting)
            ),
            targeting_plan=targeting_plan,
            fog_owner_id=(
                None
                if self.fog_of_war is None
                else id(self.fog_of_war)
            ),
            fog_plan=fog_plan,
        )

    def checkpoint_state_keys(self) -> frozenset[str]:
        """Return the format-118 context key topology without capturing state."""
        keys = {
            "config",
            "era_runtime_contract",
            "doctrine_side_assignments",
            "clock",
            "rng",
            "units_by_side",
            "morale_runtime",
            "unit_weapon_states",
            "unit_sensor_states",
            "loadout_builder_fingerprint",
            "loadout_topology",
            "calibration",
            "targeting_default_visibility_m",
        }
        for binding in self._checkpoint_owner_bindings():
            if (
                binding.owner is not None
                and binding.disposition is not CheckpointOwnerDisposition.STATELESS
                and not (
                    binding.name in {"stockpile_manager", "supply_network_engine"}
                    and self.logistics_runtime is not None
                )
            ):
                keys.add(binding.name)
        if self.era_config is not None and hasattr(self.era_config, "model_dump"):
            keys.add("era_config")
        return frozenset(keys)

    def get_state(
        self,
        *,
        fow_observer_unit_ids: Collection[str] | None = None,
        battle_lod_tiers: Mapping[str, int] | None = None,
    ) -> dict[str, Any]:
        """Capture full simulation state for checkpointing."""
        self._validate_loadout_bindings()
        snapshot = self._capture_checkpoint_snapshot(
            fow_observer_unit_ids=fow_observer_unit_ids,
            battle_lod_tiers=battle_lod_tiers,
        )
        if (
            snapshot.context_owner_id != id(self)
            or snapshot.rng_owner_id != id(self.rng_manager)
            or snapshot.targeting_owner_id
            != (
                None
                if self.tactical_targeting is None
                else id(self.tactical_targeting)
            )
            or snapshot.fog_owner_id
            != (None if self.fog_of_war is None else id(self.fog_of_war))
            or any(
                captured.binding.owner
                is not getattr(self, captured.binding.name)
                for captured in snapshot.owners
            )
        ):
            raise RuntimeError(
                "Context checkpoint owner identity changed during capture",
            )
        state: dict[str, Any] = {
            "config": _model_dump_json_compatible(self.config),
            "era_runtime_contract": _model_dump_json_compatible(
                self.era_runtime_contract,
            ),
            "doctrine_side_assignments": [
                assignment.model_dump(mode="json") for assignment in self.doctrine_side_assignments
            ],
            "clock": self.clock.get_state(),
            "rng": snapshot.rng_state,
            "units_by_side": {side: [u.get_state() for u in units] for side, units in self.units_by_side.items()},
            "morale_runtime": (self.morale_runtime.get_state() if self.morale_runtime is not None else None),
            "unit_weapon_states": {
                uid: [weapon.get_state() for weapon, _ in weapons]
                for uid, weapons in getattr(self, "unit_weapons", {}).items()
            },
            "unit_sensor_states": {
                uid: [sensor.get_state() for sensor in sensors]
                for uid, sensors in getattr(self, "unit_sensors", {}).items()
            },
            "loadout_builder_fingerprint": (
                self.loadout_builder.fingerprint() if self.loadout_builder is not None else None
            ),
            "loadout_topology": {
                unit_id: [resolution.topology() for resolution in resolutions]
                for unit_id, resolutions in sorted(
                    self.equipment_resolutions.items(),
                )
            },
            "calibration": (
                self.calibration.model_dump()
                if isinstance(self.calibration, CalibrationSchema)
                else dict(self.calibration)
            ),
            "targeting_default_visibility_m": (self.targeting_default_visibility_m),
        }
        # Project the exact graph already used by preflight; never recapture a
        # mutable owner while encoding the checkpoint.
        for captured in snapshot.owners:
            state[captured.binding.name] = captured.state
        # Era config
        if self.era_config is not None and hasattr(self.era_config, "model_dump"):
            state["era_config"] = _model_dump_json_compatible(self.era_config)
        return state

    def stage_state(
        self,
        state: dict[str, Any],
        *,
        allow_legacy_morale: bool = False,
        targeting_battle_memberships: (Mapping[str, Collection[str]] | None) = None,
        require_current_targeting_interval: bool = False,
        fow_observer_unit_ids: Collection[str] | None = None,
        battle_lod_tiers: Mapping[str, int] | None = None,
    ) -> SimulationContextStatePlan:
        """Validate all context state without mutating the live runtime."""
        self._validate_morale_bindings(require_runtime_for_roster=True)
        if type(require_current_targeting_interval) is not bool:
            raise ValueError(
                "require_current_targeting_interval must be a boolean",
            )
        membership_items = _normalize_targeting_battle_memberships(
            targeting_battle_memberships,
        )
        if (fow_observer_unit_ids is None) != (battle_lod_tiers is None):
            raise ValueError(
                "FOW observer and Battle LOD checkpoint sidecars must be supplied together",
            )
        normalized_fow_observers = None if fow_observer_unit_ids is None else frozenset(fow_observer_unit_ids)
        normalized_lod_items = None if battle_lod_tiers is None else tuple(sorted(battle_lod_tiers.items()))
        staged_state = copy.deepcopy(state)
        self._apply_state(
            staged_state,
            allow_legacy_morale=allow_legacy_morale,
            targeting_battle_memberships=(None if membership_items is None else dict(membership_items)),
            require_current_targeting_interval=(require_current_targeting_interval),
            fow_observer_unit_ids=normalized_fow_observers,
            battle_lod_tiers=(None if normalized_lod_items is None else dict(normalized_lod_items)),
            commit=False,
        )
        return SimulationContextStatePlan(
            owner_id=id(self),
            state=staged_state,
            allow_legacy_morale=allow_legacy_morale,
            targeting_battle_membership_items=membership_items,
            require_current_targeting_interval=(require_current_targeting_interval),
            fow_observer_unit_ids=normalized_fow_observers,
            battle_lod_tier_items=normalized_lod_items,
        )

    def commit_state(self, plan: SimulationContextStatePlan) -> None:
        """Commit a whole-context plan after every owner has preflighted."""
        if plan.owner_id != id(self):
            raise ValueError(
                "Simulation-context checkpoint plan belongs to another runtime",
            )
        self._apply_state(
            plan.state,
            allow_legacy_morale=plan.allow_legacy_morale,
            targeting_battle_memberships=(
                None if plan.targeting_battle_membership_items is None else dict(plan.targeting_battle_membership_items)
            ),
            require_current_targeting_interval=(plan.require_current_targeting_interval),
            fow_observer_unit_ids=plan.fow_observer_unit_ids,
            battle_lod_tiers=(None if plan.battle_lod_tier_items is None else dict(plan.battle_lod_tier_items)),
            commit=True,
        )

    def set_state(
        self,
        state: dict[str, Any],
        *,
        allow_legacy_morale: bool = False,
        targeting_battle_memberships: (Mapping[str, Collection[str]] | None) = None,
        require_current_targeting_interval: bool = False,
        fow_observer_unit_ids: Collection[str] | None = None,
        battle_lod_tiers: Mapping[str, int] | None = None,
    ) -> None:
        """Validate and atomically restore simulation context state."""
        self.commit_state(
            self.stage_state(
                state,
                allow_legacy_morale=allow_legacy_morale,
                targeting_battle_memberships=(targeting_battle_memberships),
                require_current_targeting_interval=(require_current_targeting_interval),
                fow_observer_unit_ids=fow_observer_unit_ids,
                battle_lod_tiers=battle_lod_tiers,
            ),
        )

    def _apply_state(
        self,
        state: dict[str, Any],
        *,
        allow_legacy_morale: bool,
        targeting_battle_memberships: (Mapping[str, Collection[str]] | None),
        require_current_targeting_interval: bool,
        fow_observer_unit_ids: frozenset[str] | None,
        battle_lod_tiers: Mapping[str, int] | None,
        commit: bool,
    ) -> None:
        """Preflight context state and optionally commit it."""
        self._validate_detection_checkpoint_owner()
        if self.detection_engine is not None and "detection_engine" not in state and not allow_legacy_morale:
            raise ValueError("Checkpoint is missing DetectionEngine state")
        if self.detection_engine is None and "detection_engine" in state:
            raise ValueError(
                "Checkpoint contains detection state for a context without a DetectionEngine owner",
            )
        if allow_legacy_morale and "detection_engine" in state:
            raw_legacy_detection = state["detection_engine"]
            if not isinstance(raw_legacy_detection, dict):
                raise ValueError(
                    "Versionless DetectionEngine state must be a mapping",
                )
            if "rng_state" not in raw_legacy_detection:
                raise ValueError(
                    "Versionless DetectionEngine state is missing rng_state",
                )
            # Pre-118 scan identities cannot prove complete attachment-local
            # cadence history.  Migrate only the staged payload to the exact
            # empty modern mirror; the live owner remains untouched until the
            # whole context plan commits.
            state["detection_engine"] = {
                "rng_state": copy.deepcopy(
                    raw_legacy_detection["rng_state"],
                ),
                "scan_counts": {},
            }
        self.validate_era_runtime_bindings()
        if allow_legacy_morale and "morale_runtime" in state:
            raise ValueError(
                "Versionless checkpoints cannot contain format-113 morale_runtime state",
            )
        raw_era_runtime_contract = state.get("era_runtime_contract")
        if allow_legacy_morale:
            if "era_runtime_contract" in state:
                raise ValueError(
                    "Versionless checkpoints cannot contain format-114 era_runtime_contract state",
                )
            if self._captured_era_config().has_runtime_overrides:
                raise ValueError(
                    "Versionless checkpoints cannot restore a runtime with declared era overrides",
                )
        else:
            if raw_era_runtime_contract is None:
                raise ValueError(
                    "Checkpoint is missing era_runtime_contract",
                )
            try:
                checkpoint_era_contract = EraRuntimeContract.model_validate(
                    raw_era_runtime_contract,
                    extra="forbid",
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid checkpoint era runtime contract: {exc}",
                ) from exc
            if checkpoint_era_contract != self.era_runtime_contract:
                raise ValueError(
                    "Checkpoint era runtime contract does not match the target runtime",
                )
        if "config" in state:
            checkpoint_config = state["config"]
            comparable_config = checkpoint_config
            if allow_legacy_morale and isinstance(checkpoint_config, dict):
                comparable_config = copy.deepcopy(checkpoint_config)
                calibration = comparable_config.get(
                    "calibration_overrides",
                )
                morale = calibration.get("morale") if isinstance(calibration, dict) else None
                if isinstance(morale, dict) and "use_continuous_time" not in morale:
                    morale["use_continuous_time"] = False
            if not isinstance(checkpoint_config, dict) or not _json_values_equal(
                comparable_config,
                _model_dump_json_compatible(self.config),
            ):
                raise ValueError(
                    "Checkpoint configuration does not match the runtime configuration",
                )
        raw_doctrine_policy = state.get("doctrine_side_assignments")
        if raw_doctrine_policy is None:
            if self.doctrine_side_assignments and not allow_legacy_morale:
                raise ValueError(
                    "Checkpoint is missing runtime doctrine policy",
                )
        else:
            if not isinstance(raw_doctrine_policy, list):
                raise ValueError(
                    "Checkpoint doctrine_side_assignments must be a list",
                )
            try:
                checkpoint_policy = tuple(
                    DoctrineSideAssignment.model_validate(assignment) for assignment in raw_doctrine_policy
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid checkpoint doctrine policy: {exc}",
                ) from exc
            _doctrine_policy_index(checkpoint_policy)
            if checkpoint_policy != self.doctrine_side_assignments:
                raise ValueError(
                    "Checkpoint doctrine policy does not match the runtime",
                )

        if "era_config" in state:
            from stochastic_warfare.core.era import EraConfig

            raw_era_config = state["era_config"]
            try:
                checkpoint_era_config = EraConfig.model_validate(
                    raw_era_config,
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid checkpoint era configuration: {exc}",
                ) from exc
            if self.era_config is None or checkpoint_era_config != self.era_config:
                raise ValueError(
                    "Checkpoint effective era configuration or feature gates "
                    "(including disabled_modules) do not match the runtime",
                )

        if not allow_legacy_morale:
            expected_builder_fingerprint = (
                self.loadout_builder.fingerprint() if self.loadout_builder is not None else None
            )
            if state.get("loadout_builder_fingerprint") != expected_builder_fingerprint:
                raise ValueError(
                    "Checkpoint loadout-builder fingerprint does not match the runtime mapping/catalog envelope",
                )
            if not isinstance(state.get("loadout_topology"), dict):
                raise ValueError(
                    "Checkpoint loadout_topology must be a mapping",
                )

        clock_state = state["clock"]
        raw_rng_state = state["rng"]
        if allow_legacy_morale:
            if isinstance(raw_rng_state, dict) and "indexed_fow" in raw_rng_state:
                raise ValueError(
                    "Versionless checkpoints cannot contain format-118 indexed_fow state",
                )
            if type(raw_rng_state) is not dict:
                rng_state = raw_rng_state
            else:
                try:
                    legacy_rng = RNGManager(raw_rng_state["master_seed"])
                    legacy_rng.mark_indexed_fow_history_incomplete()
                    rng_state = copy.deepcopy(raw_rng_state)
                    rng_state["indexed_fow"] = legacy_rng.get_state()["indexed_fow"]
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(
                        f"Invalid versionless checkpoint RNG state: {exc}",
                    ) from exc
        else:
            rng_state = raw_rng_state
        expected_clock_fields = {
            "start",
            "current",
            "tick_duration_seconds",
            "tick_count",
        }
        if not isinstance(clock_state, dict) or set(clock_state) != expected_clock_fields:
            raise ValueError(
                "Checkpoint clock state has invalid key topology",
            )
        raw_tick_count = clock_state["tick_count"]
        if isinstance(raw_tick_count, bool) or not isinstance(raw_tick_count, int) or raw_tick_count < 0:
            raise ValueError(
                "Checkpoint clock tick_count must be a non-negative strict integer",
            )
        raw_tick_duration = clock_state["tick_duration_seconds"]
        if (
            isinstance(raw_tick_duration, bool)
            or not isinstance(raw_tick_duration, (int, float))
            or not math.isfinite(float(raw_tick_duration))
            or float(raw_tick_duration) <= 0.0
        ):
            raise ValueError(
                "Checkpoint clock tick_duration_seconds must be finite and positive",
            )
        try:
            staged_clock = copy.deepcopy(self.clock)
            staged_clock.set_state(clock_state)
            copy.deepcopy(self.rng_manager).set_state(rng_state)
            elapsed_seconds = staged_clock.elapsed.total_seconds()
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid checkpoint clock or RNG state: {exc}") from exc
        if (
            not math.isfinite(elapsed_seconds)
            or elapsed_seconds < 0.0
            or (raw_tick_count == 0 and elapsed_seconds != 0.0)
            or (raw_tick_count > 0 and elapsed_seconds <= 0.0)
        ):
            raise ValueError(
                "Checkpoint clock tick count and logical time are inconsistent",
            )
        horizon_source = self._captured_era_execution_horizon()
        expected_start = parse_scenario_start_time(horizon_source.date)
        if staged_clock.start_time != expected_start:
            raise ValueError(
                "Checkpoint clock start does not match the scenario start",
            )
        horizon_end = self.era_runtime_contract.execution_horizon_end(
            start=expected_start,
            duration_hours=horizon_source.duration_hours,
        )
        if staged_clock.current_time > horizon_end:
            raise ValueError(
                "Checkpoint clock current time exceeds the executable scenario horizon",
            )

        cal_data = state.get("calibration", {})
        if not isinstance(cal_data, dict):
            raise ValueError("Checkpoint calibration must be a mapping")
        staged_calibration = CalibrationSchema(**cal_data)
        current_calibration = (
            self.calibration
            if isinstance(self.calibration, CalibrationSchema)
            else CalibrationSchema.model_validate(self.calibration)
        )
        if staged_calibration != current_calibration:
            raise ValueError(
                "Checkpoint calibration does not match the validated runtime configuration",
            )
        has_targeting_default = "targeting_default_visibility_m" in state
        if not has_targeting_default and not allow_legacy_morale:
            raise ValueError(
                "Checkpoint is missing targeting_default_visibility_m",
            )
        checkpoint_targeting_default = _targeting_visibility_bound_m(
            calibration={},
            weather_engine=None,
            default_visibility_m=(
                state["targeting_default_visibility_m"] if has_targeting_default else DEFAULT_TARGETING_VISIBILITY_M
            ),
        )
        current_targeting_default = _targeting_visibility_bound_m(
            calibration={},
            weather_engine=None,
            default_visibility_m=self.targeting_default_visibility_m,
        )
        if checkpoint_targeting_default != current_targeting_default:
            raise ValueError(
                "Checkpoint targeting default visibility does not match the runtime battle configuration",
            )

        staged_units: dict[str, list[tuple[dict[str, Any], Unit]]] | None = None
        checkpoint_unit_ids: set[str] = set()
        checkpoint_equipment: dict[str, dict[str, dict[str, Any]]] | None = None

        if "units_by_side" in state:
            raw_forces = state["units_by_side"]
            if not isinstance(raw_forces, dict):
                raise ValueError("Checkpoint units_by_side must be a mapping")
            staged_units = {}
            seen_ids: set[str] = set()
            for side, raw_units in raw_forces.items():
                if not isinstance(side, str) or not isinstance(raw_units, list):
                    raise ValueError(
                        "Checkpoint force sides must map names to unit lists",
                    )
                staged_units[side] = []
                for raw_unit in raw_units:
                    staged = _stage_checkpoint_unit(raw_unit, side)
                    if staged.entity_id in seen_ids:
                        raise ValueError(
                            f"Duplicate checkpoint entity_id {staged.entity_id!r}",
                        )
                    seen_ids.add(staged.entity_id)
                    staged_units[side].append((raw_unit, staged))
            checkpoint_unit_ids = seen_ids
            checkpoint_equipment = {
                staged.entity_id: {
                    equipment_state["equipment_id"]: equipment_state for equipment_state in raw_unit["equipment"]
                }
                for staged_side in staged_units.values()
                for raw_unit, staged in staged_side
            }

        raw_aggregation_state = state.get("aggregation_engine")
        if allow_legacy_morale and isinstance(raw_aggregation_state, dict) and raw_aggregation_state.get("aggregates"):
            raise ValueError(
                "Versionless checkpoints with active aggregation cannot reconstruct complete morale records",
            )
        aggregate_morale_topology = _checkpoint_aggregate_morale_topology(
            raw_aggregation_state,
        )
        aggregate_constituents = aggregate_morale_topology.constituents
        if allow_legacy_morale and aggregate_constituents:
            raise ValueError(
                "Versionless checkpoints with active aggregation cannot reconstruct complete morale records",
            )
        if aggregate_constituents:
            if type(self.aggregation_engine) is not AggregationEngine:
                raise ValueError(
                    "Active aggregate checkpoint requires an exact AggregationEngine runtime owner",
                )
            raw_aggregation_config = raw_aggregation_state.get("config")
            if not isinstance(raw_aggregation_config, dict) or set(raw_aggregation_config) != set(
                AggregationConfig.model_fields,
            ):
                raise ValueError(
                    "Active aggregate checkpoint config has invalid key topology",
                )
            try:
                staged_aggregation_config = AggregationConfig.model_validate(
                    raw_aggregation_config,
                    strict=True,
                )
            except ValueError as exc:
                raise ValueError(
                    f"Active aggregate checkpoint config is invalid: {exc}",
                ) from exc
            if not staged_aggregation_config.enable_aggregation:
                raise ValueError(
                    "Active aggregate checkpoint requires enabled persisted aggregation configuration",
                )
            if not self.aggregation_engine.config.enable_aggregation:
                raise ValueError(
                    "Active aggregate checkpoint requires an enabled aggregation runtime owner",
                )
            if staged_aggregation_config != self.aggregation_engine.config:
                raise ValueError(
                    "Active aggregate checkpoint config does not match the runtime config",
                )
            unsupported_aggregate_owners = unsupported_aggregation_owner_names(self)
            if unsupported_aggregate_owners:
                raise ValueError(
                    "REM-016: active aggregate checkpoint restoration has "
                    "uncoordinated context state owners: "
                    f"{unsupported_aggregate_owners!r}",
                )

        raw_legacy_morale = state.get("morale_states")
        raw_legacy_machine = state.get("morale_machine")
        raw_morale_runtime = state.get("morale_runtime")
        raw_rout_state = state.get("rout_engine")
        staged_morale_plan: Any = None
        existing_by_id: dict[str, Unit] = {}
        for unit in self.all_units():
            if unit.entity_id in existing_by_id:
                raise ValueError(
                    f"Duplicate runtime entity_id {unit.entity_id!r}",
                )
            existing_by_id[unit.entity_id] = unit

        validated_staged_loadouts: RuntimeLoadouts | None = None
        if staged_units is None:
            checkpoint_unit_ids = set(existing_by_id)
            reusable_ids = set(existing_by_id)
        else:
            all_staged_units = [staged for staged_side in staged_units.values() for _, staged in staged_side]
            if not allow_legacy_morale and self.loadout_builder is not None:
                validated_staged_loadouts = self.loadout_builder.build(
                    all_staged_units,
                )

            reusable_ids: set[str] = set()
            for staged in all_staged_units:
                existing = existing_by_id.get(staged.entity_id)
                if existing is None:
                    continue
                if (
                    type(existing) is not type(staged)
                    or existing.unit_type != staged.unit_type
                    or existing.domain is not staged.domain
                ):
                    raise ValueError(
                        f"Checkpoint unit identity topology does not match the runtime for {staged.entity_id!r}",
                    )
                existing_equipment_ids = [equipment.equipment_id for equipment in existing.equipment]
                staged_equipment_ids = [equipment.equipment_id for equipment in staged.equipment]
                if staged_equipment_ids != existing_equipment_ids:
                    raise ValueError(
                        "Checkpoint equipment identity/order topology does not "
                        f"match the runtime for {staged.entity_id!r}",
                    )
                existing_binding_topology = [
                    (
                        equipment.equipment_id,
                        equipment.name,
                        equipment.category,
                    )
                    for equipment in existing.equipment
                ]
                staged_binding_topology = [
                    (
                        equipment.equipment_id,
                        equipment.name,
                        equipment.category,
                    )
                    for equipment in staged.equipment
                ]
                if staged_binding_topology != existing_binding_topology:
                    raise ValueError(
                        "Checkpoint equipment semantic binding topology does "
                        "not match the runtime for "
                        f"{staged.entity_id!r}",
                    )
                reusable_ids.add(staged.entity_id)

        if (
            (self.commander_engine is not None or self.school_registry is not None)
            and self.aggregation_engine is not None
            and self.aggregation_engine._config.enable_aggregation
        ):
            raise ValueError(
                "Commander/school checkpoint restoration with enabled force aggregation is unsupported",
            )

        staged_commander_plan: CommanderAssignmentPlan | None = None
        if self.commander_engine is not None:
            raw_commander_state = state.get("commander_engine")
            if raw_commander_state is None:
                if not allow_legacy_morale:
                    raise ValueError(
                        "Checkpoint is missing commander_engine state",
                    )
            elif not isinstance(raw_commander_state, Mapping):
                raise ValueError(
                    "Checkpoint commander_engine state must be a mapping",
                )
            else:
                try:
                    staged_commander_plan = self.commander_engine.stage_state(
                        raw_commander_state,
                        expected_unit_ids=checkpoint_unit_ids,
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(
                        f"Invalid checkpoint commander state: {exc}",
                    ) from exc
        elif "commander_engine" in state:
            raise ValueError(
                "Checkpoint contains commander state for a runtime without a commander engine",
            )

        staged_school_plan: Any = None
        if self.school_registry is not None:
            raw_school_state = state.get("school_registry")
            if raw_school_state is None:
                if not allow_legacy_morale:
                    raise ValueError(
                        "Checkpoint is missing school_registry state",
                    )
            elif not isinstance(raw_school_state, Mapping):
                raise ValueError(
                    "Checkpoint school_registry state must be a mapping",
                )
            else:
                try:
                    staged_school_plan = self.school_registry.stage_state(
                        raw_school_state,
                        expected_unit_ids=checkpoint_unit_ids,
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(
                        f"Invalid checkpoint school state: {exc}",
                    ) from exc
        elif "school_registry" in state:
            raise ValueError(
                "Checkpoint contains school state for a runtime without a school registry",
            )

        staged_ooda_plan: Any = None
        if self.commander_engine is not None:
            if self.ooda_engine is None:
                raise ValueError(
                    "Commander checkpoint runtime is missing its OODA engine",
                )
            raw_ooda_state = state.get("ooda_engine")
            if raw_ooda_state is None:
                if not allow_legacy_morale:
                    raise ValueError(
                        "Checkpoint is missing commander OODA state",
                    )
            elif not isinstance(raw_ooda_state, Mapping):
                raise ValueError(
                    "Checkpoint OODA state must be a mapping",
                )
            else:
                try:
                    staged_ooda_plan = self.ooda_engine.stage_state(
                        raw_ooda_state,
                        expected_unit_ids=checkpoint_unit_ids,
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(
                        f"Invalid checkpoint commander OODA state: {exc}",
                    ) from exc

        current_unit_weapons = getattr(self, "unit_weapons", {})
        current_unit_sensor_attachments = getattr(
            self,
            "unit_sensor_attachments",
            {},
        )
        current_unit_sensors = getattr(self, "unit_sensors", {})
        current_equipment_resolutions = getattr(
            self,
            "equipment_resolutions",
            {},
        )
        runtime_unit_weapons = dict(current_unit_weapons)
        runtime_unit_sensor_attachments = dict(
            current_unit_sensor_attachments,
        )
        runtime_unit_sensors = dict(current_unit_sensors)
        runtime_equipment_resolutions = dict(
            current_equipment_resolutions,
        )
        compatible_weapon_ids = set(reusable_ids)
        compatible_sensor_ids = set(reusable_ids)

        if staged_units is not None:
            reconstructed_units = [
                staged
                for staged_side in staged_units.values()
                for _, staged in staged_side
                if staged.entity_id not in reusable_ids
            ]
            can_rebuild_loadouts = self.loadout_builder is not None
            if reconstructed_units and can_rebuild_loadouts:
                rebuilt_loadouts = (
                    validated_staged_loadouts
                    if validated_staged_loadouts is not None
                    else self.loadout_builder.build(reconstructed_units)
                )
                reconstructed_ids = {unit.entity_id for unit in reconstructed_units}
                runtime_unit_weapons.update(
                    {
                        entity_id: attachments
                        for entity_id, attachments in rebuilt_loadouts.unit_weapons.items()
                        if entity_id in reconstructed_ids
                    }
                )
                runtime_unit_sensors.update(
                    {
                        entity_id: sensors
                        for entity_id, sensors in rebuilt_loadouts.unit_sensors.items()
                        if entity_id in reconstructed_ids
                    }
                )
                runtime_unit_sensor_attachments.update(
                    {
                        entity_id: attachments
                        for entity_id, attachments in rebuilt_loadouts.unit_sensor_attachments.items()
                        if entity_id in reconstructed_ids
                    }
                )
                runtime_equipment_resolutions.update(
                    {
                        entity_id: resolutions
                        for entity_id, resolutions in rebuilt_loadouts.equipment_resolutions.items()
                        if entity_id in reconstructed_ids
                    }
                )
                compatible_weapon_ids.update(reconstructed_ids)
                compatible_sensor_ids.update(reconstructed_ids)
            elif reconstructed_units:
                for staged in reconstructed_units:
                    entity_id = staged.entity_id
                    if not _checkpoint_declares_empty_runtime_loadout(
                        state,
                        unit_id=entity_id,
                    ):
                        continue
                    runtime_unit_weapons[entity_id] = ()
                    runtime_unit_sensor_attachments[entity_id] = ()
                    runtime_unit_sensors[entity_id] = ()
                    runtime_equipment_resolutions[entity_id] = ()
                    compatible_weapon_ids.add(entity_id)
                    compatible_sensor_ids.add(entity_id)

        if not allow_legacy_morale:
            topology_resolutions = (
                validated_staged_loadouts.equipment_resolutions
                if validated_staged_loadouts is not None
                else runtime_equipment_resolutions
            )
            runtime_topology = {
                entity_id: [
                    resolution.topology()
                    for resolution in topology_resolutions.get(
                        entity_id,
                        (),
                    )
                ]
                for entity_id in sorted(
                    set(topology_resolutions) & checkpoint_unit_ids,
                )
            }
            if not _json_values_equal(
                state["loadout_topology"],
                runtime_topology,
            ):
                raise ValueError(
                    "Checkpoint loadout resolution topology does not match the runtime builder output",
                )

        staged_weapon_states: list[tuple[Any, dict[str, Any]]] = []
        if "unit_weapon_states" in state:
            staged_weapon_states = _stage_runtime_instance_states(
                state["unit_weapon_states"],
                runtime_unit_weapons,
                checkpoint_unit_ids,
                compatible_weapon_ids,
                checkpoint_equipment,
                kind="weapon",
                allow_legacy_weapon_timestamp_omission=allow_legacy_morale,
            )

        staged_sensor_states: list[tuple[Any, dict[str, Any]]] = []
        if "unit_sensor_states" in state:
            staged_sensor_states = _stage_runtime_instance_states(
                state["unit_sensor_states"],
                runtime_unit_sensors,
                checkpoint_unit_ids,
                compatible_sensor_ids,
                checkpoint_equipment,
                kind="sensor",
            )

        prospective_units_by_side = (
            {side: [staged for _, staged in staged_side] for side, staged_side in staged_units.items()}
            if staged_units is not None
            else {side: list(units) for side, units in self.units_by_side.items()}
        )
        configured_sides = getattr(self.config, "sides", ())
        declared_side_order = tuple(side.side for side in configured_sides)
        declared_sides = set(declared_side_order)
        requires_exact_force_topology = any(
            component is not None
            for component in (
                self.fog_of_war,
                self.space_engine,
                self.movement_diagnostics,
            )
        )
        if requires_exact_force_topology and set(prospective_units_by_side) != declared_sides:
            raise ValueError(
                "Checkpoint unit-side topology does not match scenario sides",
            )
        expected_sides = declared_sides if requires_exact_force_topology else set(prospective_units_by_side)
        expected_target_sides = {
            unit.entity_id: side for side, units in prospective_units_by_side.items() for unit in units
        }
        prospective_live_units = (
            {
                staged.entity_id: (existing_by_id[staged.entity_id] if staged.entity_id in reusable_ids else staged)
                for staged_side in staged_units.values()
                for _, staged in staged_side
            }
            if staged_units is not None
            else dict(existing_by_id)
        )
        prospective_calibration = staged_calibration.resolve(
            self.cal_flat.sides,
        )
        if prospective_calibration != self.resolved_calibration:
            raise ValueError(
                "Checkpoint calibration resolution does not match the immutable runtime owner",
            )
        expected_fog_of_war_enabled = _configured_fog_of_war_enabled(
            prospective_calibration,
        )
        if expected_fog_of_war_enabled and self.fog_of_war is None:
            raise ValueError(
                "enabled fog-of-war requires a live FogOfWarManager owner",
            )
        try:
            prospective_loadouts = RuntimeLoadouts(
                unit_weapons={unit_id: runtime_unit_weapons[unit_id] for unit_id in sorted(checkpoint_unit_ids)},
                unit_sensor_attachments={
                    unit_id: runtime_unit_sensor_attachments[unit_id] for unit_id in sorted(checkpoint_unit_ids)
                },
                equipment_resolutions={
                    unit_id: runtime_equipment_resolutions[unit_id] for unit_id in sorted(checkpoint_unit_ids)
                },
            )
            _validate_runtime_loadout_object_bindings(
                units=prospective_live_units,
                loadouts=prospective_loadouts,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid checkpoint runtime loadout bindings: {exc}",
            ) from exc

        staged_targeting_plan: TacticalTargetingRestorePlan | None = None
        targeting_interval_is_current = False
        has_targeting_state = "tactical_targeting" in state
        raw_targeting_state = state.get("tactical_targeting")
        if self.tactical_targeting is None:
            if has_targeting_state:
                raise ValueError(
                    "Checkpoint contains targeting state for a context without a tactical-targeting owner",
                )
        elif not has_targeting_state:
            if not allow_legacy_morale:
                raise ValueError(
                    "Checkpoint is missing tactical_targeting state",
                )
            if (
                staged_clock.tick_count != 0
                or elapsed_seconds != 0.0
                or targeting_battle_memberships
                or require_current_targeting_interval
                or self.tactical_targeting.prepared_interval is not None
                or self.tactical_targeting.latest_pictures()
                or dict(self.tactical_targeting.registered_unit_sides) != dict(sorted(expected_target_sides.items()))
            ):
                raise ValueError(
                    "Versionless checkpoints may omit tactical targeting "
                    "only at pristine tick 0 with an unprepared matching "
                    "runtime topology",
                )
        else:
            try:
                staging_runtime = TacticalTargetingRuntime(
                    sensing_aware_standoff_enabled=(self.tactical_targeting.sensing_aware_standoff_enabled),
                    unit_sides=expected_target_sides,
                )
                prepared_state = (
                    raw_targeting_state.get("prepared_interval") if isinstance(raw_targeting_state, dict) else None
                )
                if prepared_state is None:
                    if targeting_battle_memberships or require_current_targeting_interval:
                        raise ValueError(
                            "unprepared targeting state disagrees with the checkpoint active-battle topology",
                        )
                    staged_targeting_plan = staging_runtime.stage_state(
                        raw_targeting_state,
                    )
                else:
                    staged_targeting_plan = staging_runtime.stage_state(
                        raw_targeting_state,
                        expected_unit_sides=(
                            expected_target_sides if targeting_battle_memberships is not None else None
                        ),
                        expected_battle_memberships=(
                            targeting_battle_memberships if targeting_battle_memberships is not None else None
                        ),
                        expected_engine_tick=(staged_clock.tick_count if require_current_targeting_interval else None),
                        expected_logical_time_s=(elapsed_seconds if require_current_targeting_interval else None),
                    )
                targeting_interval_is_current = _targeting_interval_is_current(
                    plan=staged_targeting_plan,
                    clock_tick=staged_clock.tick_count,
                    logical_time_s=elapsed_seconds,
                )
                _validate_targeting_live_bindings(
                    plan=staged_targeting_plan,
                    units=prospective_live_units,
                    loadouts=prospective_loadouts,
                    calibration=prospective_calibration,
                    live_visibility_m=(
                        _prospective_targeting_visibility_bound_m(
                            calibration=prospective_calibration,
                            weather_engine=self.weather_engine,
                            checkpoint_state=state,
                            default_visibility_m=(checkpoint_targeting_default),
                        )
                        if targeting_interval_is_current
                        else None
                    ),
                )
            except (AttributeError, KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid checkpoint tactical targeting state: {exc}",
                ) from exc
        prospective_morale_units = {
            unit.entity_id: unit for units in prospective_units_by_side.values() for unit in units
        }
        aggregate_ids = set(aggregate_constituents)
        archived_constituent_ids = {unit_id for unit_ids in aggregate_constituents.values() for unit_id in unit_ids}
        if (
            not aggregate_ids <= set(prospective_morale_units)
            or archived_constituent_ids & set(prospective_morale_units)
            or archived_constituent_ids & aggregate_ids
        ):
            raise ValueError(
                "Checkpoint aggregate proxies and archived constituents must be disjoint and match the active roster",
            )
        for aggregate_id in sorted(aggregate_ids):
            proxy = prospective_morale_units[aggregate_id]
            expected_side, expected_type, expected_position = aggregate_morale_topology.proxy_expectations[aggregate_id]
            proxy_side = proxy.side if isinstance(proxy.side, str) else proxy.side.value
            expected_domain = aggregate_morale_topology.proxy_domains[aggregate_id]
            if (
                type(proxy) is not Unit
                or proxy.equipment
                or proxy_side != expected_side
                or proxy.unit_type != expected_type
                or proxy.domain is not expected_domain
                or tuple(float(value) for value in proxy.position) != expected_position
            ):
                raise ValueError(
                    f"Checkpoint aggregate roster proxy disagrees with aggregation state for {aggregate_id!r}",
                )
            side_units = prospective_units_by_side.get(expected_side, [])
            retained_count = sum(unit.entity_id != aggregate_id for unit in side_units)
            original_indexes = aggregate_morale_topology.original_indexes[aggregate_id]
            proxy_indexes = [index for index, unit in enumerate(side_units) if unit.entity_id == aggregate_id]
            if proxy_indexes != [min(original_indexes)] or any(
                index >= retained_count + len(original_indexes) for index in original_indexes
            ):
                raise ValueError(
                    f"Checkpoint aggregate {aggregate_id!r} proxy/order cannot reconstruct the serialized side roster",
                )
        if self.morale_runtime is None:
            if prospective_morale_units:
                raise ValueError(
                    "A non-empty checkpoint roster requires MoraleRuntime",
                )
            if raw_morale_runtime is not None:
                raise ValueError(
                    "Checkpoint contains morale state for a context without MoraleRuntime",
                )
            if aggregate_constituents or _checkpoint_has_active_routes(
                state.get("rout_engine"),
            ):
                raise ValueError(
                    "A null morale runtime requires empty route and aggregation state",
                )
        else:
            if allow_legacy_morale:
                (
                    raw_morale_runtime,
                    raw_rout_state,
                ) = _migrate_legacy_morale_runtime(
                    context_morale=raw_legacy_morale,
                    machine_state=raw_legacy_machine,
                    units=prospective_morale_units,
                    side_initial={side.side: side.morale_initial for side in self.config.sides},
                    elapsed_time_s=elapsed_seconds,
                    continuous_time=(self.morale_runtime.config.use_continuous_time),
                    authoritative_rng_state=(rng_state["streams"][ModuleId.MORALE.value]),
                    rout_state=raw_rout_state,
                )
            if not isinstance(raw_morale_runtime, dict):
                raise ValueError(
                    "Checkpoint morale_runtime must be a mapping",
                )
            try:
                staged_morale_plan = self.morale_runtime.stage_state(
                    raw_morale_runtime,
                    expected_units=prospective_morale_units,
                    elapsed_time_s=elapsed_seconds,
                    aggregate_constituents=aggregate_constituents,
                    suspended_statuses=aggregate_morale_topology.statuses,
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid checkpoint morale runtime state: {exc}",
                ) from exc

        staged_rout_plan: Any = None
        if self.rout_engine is None:
            if state.get("rout_engine") is not None:
                raise ValueError(
                    "Checkpoint contains rout state for a context without RoutEngine",
                )
        else:
            if raw_rout_state is None:
                if not allow_legacy_morale:
                    raise ValueError("Checkpoint is missing RoutEngine state")
                raw_rout_state = {"active_routs": {}}
            routed_ids = (
                {
                    unit_id
                    for unit_id, record in staged_morale_plan.active_records
                    if record.current_state.name == "ROUTED"
                }
                if staged_morale_plan is not None
                else set()
            )
            try:
                staged_rout_plan = self.rout_engine.stage_state(
                    raw_rout_state,
                    expected_routing_unit_ids=routed_ids,
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid checkpoint RoutEngine state: {exc}",
                ) from exc

        staged_movement_plan: Any = None
        if self.movement_diagnostics is not None and "movement_diagnostics" in state:
            try:
                staged_movement_plan = self.movement_diagnostics.stage_state(
                    state["movement_diagnostics"],
                    expected_unit_sides=expected_target_sides,
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid checkpoint movement diagnostics state: {exc}",
                ) from exc
        elif self.movement_diagnostics is None and "movement_diagnostics" in state:
            raise ValueError(
                "Checkpoint contains movement diagnostics for a context without a movement-diagnostics owner",
            )
        if staged_movement_plan is not None and staged_targeting_plan is not None:
            _validate_movement_targeting_restore_bindings(
                movement_plan=staged_movement_plan,
                targeting_plan=staged_targeting_plan,
                units=prospective_live_units,
                loadouts=prospective_loadouts,
                calibration=prospective_calibration,
            )

        staged_obscurants_plan: Any = None
        if self.obscurants_engine is not None and "obscurants_engine" in state:
            try:
                staged_obscurants_plan = self.obscurants_engine.stage_state(
                    state["obscurants_engine"],
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid checkpoint obscurants state: {exc}",
                ) from exc
        elif self.obscurants_engine is None and "obscurants_engine" in state:
            raise ValueError(
                "Checkpoint contains obscurants state for a context without an obscurants engine",
            )

        staged_fog_plan: FogOfWarRestorePlan | None = None
        if self.fog_of_war is not None and "fog_of_war" in state:
            satellite_topology = (
                {
                    satellite.satellite_id: (
                        satellite.side,
                        satellite.constellation_id,
                    )
                    for satellite in (self.space_engine.constellation_manager.all_satellites())
                }
                if self.space_engine is not None
                else {}
            )
            try:
                full_fog_sensor_bindings = _fog_sensor_bindings(
                    unit_sides=expected_target_sides,
                    loadouts=prospective_loadouts,
                )
                cadence_sensor_bindings = None
                cadence_bindings = None
                native_phase_bindings = None
                if fow_observer_unit_ids is not None and battle_lod_tiers is not None:
                    (
                        cadence_sensor_bindings,
                        cadence_bindings,
                        native_phase_bindings,
                    ) = _fog_cadence_restore_bindings(
                        observer_unit_ids=fow_observer_unit_ids,
                        lod_tiers=battle_lod_tiers,
                        calibration=prospective_calibration,
                        unit_sides=expected_target_sides,
                        loadouts=prospective_loadouts,
                    )
                raw_detection_state = state.get("detection_engine")
                authoritative_scan_counts = (
                    raw_detection_state.get("scan_counts", {}) if isinstance(raw_detection_state, dict) else {}
                )
                staged_fog_plan = self.fog_of_war.stage_state(
                    state["fog_of_war"],
                    expected_sides=expected_sides,
                    expected_target_sides=expected_target_sides,
                    satellite_topology=satellite_topology,
                    checkpoint_elapsed_s=(staged_clock.elapsed.total_seconds()),
                    authoritative_rng_state=(rng_state["streams"][ModuleId.DETECTION.value]),
                    expected_sensor_bindings=full_fog_sensor_bindings,
                    expected_cadence_sensor_bindings=(cadence_sensor_bindings),
                    expected_cadence_bindings=cadence_bindings,
                    expected_native_phase_bindings=(native_phase_bindings),
                    authoritative_detection_scan_counts=(authoritative_scan_counts),
                    allow_legacy_state=allow_legacy_morale,
                )
                if staged_targeting_plan is not None:
                    _validate_fow_targeting_bindings(
                        targeting_plan=staged_targeting_plan,
                        fog_plan=staged_fog_plan,
                        expected_fog_of_war_enabled=(expected_fog_of_war_enabled),
                        units=prospective_live_units,
                        support_process_noise_std_mps2=(self.fog_of_war.observer_track_support_process_noise_std_mps2),
                        support_max_position_uncertainty_m=(
                            self.fog_of_war.observer_track_support_max_position_uncertainty_m
                        ),
                    )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid checkpoint fog/fusion state: {exc}",
                ) from exc
        elif self.fog_of_war is not None and not allow_legacy_morale:
            raise ValueError("Checkpoint is missing fog-of-war state")
        elif self.fog_of_war is None and "fog_of_war" in state:
            raise ValueError(
                "Checkpoint contains fog-of-war state for a context without a fog-of-war manager",
            )

        staged_logistics_plan: Any = None
        if self.logistics_runtime is not None and "logistics_runtime" in state:
            checkpoint_units = (
                {staged.entity_id: staged for staged_side in staged_units.values() for _, staged in staged_side}
                if staged_units is not None
                else existing_by_id
            )
            try:
                staged_logistics_plan = self.logistics_runtime.stage_state(
                    state["logistics_runtime"],
                    expected_units=checkpoint_units,
                    expected_elapsed_seconds=(staged_clock.elapsed.total_seconds()),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid checkpoint logistics runtime state: {exc}",
                ) from exc

        staged_space_plan: Any = None
        if self.space_engine is not None and "space_engine" in state:
            delivered_receipts = (
                tuple(staged_fog_plan.intel_fusion["delivery_receipts"]) if staged_fog_plan is not None else ()
            )
            try:
                staged_space_plan = self.space_engine.stage_state(
                    state["space_engine"],
                    expected_elapsed_s=(staged_clock.elapsed.total_seconds()),
                    expected_tick_count=staged_clock.tick_count,
                    expected_sides=tuple(sorted(expected_sides)),
                    expected_units_by_side=prospective_units_by_side,
                    delivered_receipts=delivered_receipts,
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid checkpoint space runtime state: {exc}",
                ) from exc
        elif self.space_engine is None and "space_engine" in state:
            raise ValueError(
                "Checkpoint contains space runtime state for a context without a space engine",
            )

        staged_indirect_fire_plan: Any = None
        if self.indirect_fire_engine is not None and "indirect_fire_engine" in state:
            prospective_units = (
                {staged.entity_id: staged for staged_side in staged_units.values() for _, staged in staged_side}
                if staged_units is not None
                else existing_by_id
            )
            raw_weapon_states = state.get("unit_weapon_states")
            if not isinstance(raw_weapon_states, dict):
                raise ValueError(
                    "Checkpoint with indirect-fire plans requires unit_weapon_states",
                )
            expected_resources: list[dict[str, Any]] = []
            for (
                unit_id,
                source_equipment_index,
                weapon_id,
            ) in self.indirect_fire_engine.planned_attachment_keys:
                attachments = runtime_unit_weapons.get(unit_id, ())
                matches = [
                    (index, attachment)
                    for index, attachment in enumerate(attachments)
                    if (
                        attachment.source_equipment_index == source_equipment_index
                        and attachment.weapon.weapon_id == weapon_id
                    )
                ]
                if len(matches) != 1:
                    raise ValueError(
                        "Checkpoint indirect-fire attachment topology "
                        f"mismatch for {(unit_id, source_equipment_index, weapon_id)!r}",
                    )
                attachment_index, _attachment = matches[0]
                saved_unit_weapons = raw_weapon_states.get(unit_id)
                if not isinstance(saved_unit_weapons, list) or attachment_index >= len(saved_unit_weapons):
                    raise ValueError(
                        f"Checkpoint indirect-fire weapon state is missing for {unit_id!r}",
                    )
                observation = self.indirect_fire_engine.canonical_resource_observation(
                    saved_unit_weapons[attachment_index],
                )
                expected_resources.append(
                    {
                        "unit_id": unit_id,
                        "source_equipment_index": source_equipment_index,
                        "weapon_id": weapon_id,
                        **observation,
                    }
                )
            try:
                staged_indirect_fire_plan = self.indirect_fire_engine.stage_state(
                    state["indirect_fire_engine"],
                    expected_elapsed_s=(staged_clock.elapsed.total_seconds()),
                    expected_combat_rng_state=(rng_state["streams"][ModuleId.COMBAT.value]),
                    expected_resource_observations=expected_resources,
                    expected_unit_statuses={unit_id: unit.status.name for unit_id, unit in prospective_units.items()},
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid checkpoint indirect-fire runtime state: {exc}",
                ) from exc
        elif self.indirect_fire_engine is None and "indirect_fire_engine" in state:
            raise ValueError(
                "Checkpoint contains indirect-fire state for a context without an indirect-fire engine",
            )

        # Explicit legacy owners retain isolated-clone preflight until their
        # classes adopt the atomic checkpoint protocol.  Every live owner is
        # classified before any context state can commit.
        legacy_engine_plans: dict[str, LegacyCheckpointRestorePlan] = {}
        for binding in self._checkpoint_owner_bindings():
            name = binding.name
            if binding.disposition is not CheckpointOwnerDisposition.LEGACY_CLONE:
                continue
            if name in {"stockpile_manager", "supply_network_engine"} and "logistics_runtime" in state:
                continue
            if binding.owner is None or name not in state:
                continue
            legacy_engine_plans[name] = _stage_legacy_context_checkpoint_owner(
                binding,
                state[name],
                event_bus=self.event_bus,
                authoritative_detection_rng_state=(rng_state["streams"][ModuleId.DETECTION.value]),
            )

        if not commit:
            return

        # Commit only after all context-owned checkpoint state validates.
        self.clock.set_state(clock_state)
        self.rng_manager.set_state(rng_state)

        if staged_units is not None:
            restored_by_side: dict[str, list[Unit]] = {}
            # Checkpoint JSON uses sorted object keys, but several production
            # loops intentionally process sides sequentially.  Reconstitute
            # the authored typed-config order so serialization cannot change
            # those outcome-affecting loops across a fresh restore.
            restored_side_order = (
                declared_side_order
                if (len(declared_side_order) == len(staged_units) and set(staged_units) == declared_sides)
                else tuple(staged_units)
            )
            for side in restored_side_order:
                staged_side = staged_units[side]
                restored_by_side[side] = []
                for raw_unit, staged in staged_side:
                    existing = existing_by_id.get(staged.entity_id)
                    if existing is not None and type(existing) is type(staged):
                        existing.set_state(raw_unit)
                        restored = existing
                    else:
                        restored = staged
                    restored_by_side[side].append(restored)

            self.units_by_side = restored_by_side
            if "unit_weapon_states" in state:
                self.unit_weapons = {
                    entity_id: (runtime_unit_weapons.get(entity_id, ()) if entity_id in compatible_weapon_ids else ())
                    for entity_id in state["unit_weapon_states"]
                }
            else:
                self.unit_weapons = {
                    entity_id: weapons
                    for entity_id, weapons in runtime_unit_weapons.items()
                    if entity_id in checkpoint_unit_ids
                }
            if "unit_sensor_states" in state:
                self.unit_sensor_attachments = {
                    entity_id: (
                        runtime_unit_sensor_attachments.get(entity_id, ()) if entity_id in compatible_sensor_ids else ()
                    )
                    for entity_id in state["unit_sensor_states"]
                }
                self.unit_sensors = {
                    entity_id: (runtime_unit_sensors.get(entity_id, ()) if entity_id in compatible_sensor_ids else ())
                    for entity_id in state["unit_sensor_states"]
                }
            else:
                self.unit_sensor_attachments = {
                    entity_id: attachments
                    for entity_id, attachments in runtime_unit_sensor_attachments.items()
                    if entity_id in checkpoint_unit_ids
                }
                self.unit_sensors = {
                    entity_id: sensors
                    for entity_id, sensors in runtime_unit_sensors.items()
                    if entity_id in checkpoint_unit_ids
                }
            self.equipment_resolutions = {
                entity_id: resolutions
                for entity_id, resolutions in runtime_equipment_resolutions.items()
                if entity_id in checkpoint_unit_ids
            }
            self._validate_loadout_bindings()

        if staged_morale_plan is not None:
            self.morale_runtime.commit_state(
                staged_morale_plan,
                units={unit.entity_id: unit for unit in self.all_units()},
                elapsed_time_s=elapsed_seconds,
                aggregate_constituents=aggregate_constituents,
                suspended_statuses=aggregate_morale_topology.statuses,
            )
        if staged_rout_plan is not None:
            self.rout_engine.commit_state(staged_rout_plan)

        for instance, saved_state in staged_weapon_states:
            instance.set_state(saved_state)
        for instance, saved_state in staged_sensor_states:
            instance.set_state(saved_state)
        if staged_targeting_plan is not None:
            self.tactical_targeting.commit_state(
                staged_targeting_plan,
            )
        if staged_indirect_fire_plan is not None:
            self.indirect_fire_engine.commit_state(
                staged_indirect_fire_plan,
            )
        if staged_logistics_plan is not None:
            self.logistics_runtime.commit_state(staged_logistics_plan)
        if staged_fog_plan is not None:
            self.fog_of_war.commit_state(staged_fog_plan)
        if staged_space_plan is not None:
            self.space_engine.commit_state(staged_space_plan)
        if staged_movement_plan is not None:
            self.movement_diagnostics.commit_state(staged_movement_plan)
        if staged_obscurants_plan is not None:
            self.obscurants_engine.commit_state(staged_obscurants_plan)
        if staged_commander_plan is not None:
            self.commander_engine.commit_state(staged_commander_plan)
        if staged_school_plan is not None:
            self.school_registry.commit_state(staged_school_plan)
        if staged_ooda_plan is not None:
            self.ooda_engine.commit_state(staged_ooda_plan)

        # Restore explicitly legacy owners in the same registry order used by
        # capture.  Every plan was staged before the first live owner mutated.
        for binding in self._checkpoint_owner_bindings():
            plan = legacy_engine_plans.get(binding.name)
            if plan is not None:
                _commit_legacy_context_checkpoint_owner(binding, plan)

        self._validate_morale_bindings(require_runtime_for_roster=True)
        # Targeting, FOW, cadence, RNG, and scan-count bindings were all
        # validated against the same staged plans before the first owner
        # committed.  Recapturing the now-live owners here would widen the
        # transaction and cannot add an atomicity guarantee.
