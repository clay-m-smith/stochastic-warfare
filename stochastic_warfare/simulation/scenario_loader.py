"""Production scenario loader and runtime wiring helpers."""

from __future__ import annotations

import copy
import math
from collections.abc import Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from stochastic_warfare.combat.indirect_fire_config import (
    ResolvedTimeOnTargetMission,
)
from stochastic_warfare.c2.ai.commander import (
    CommanderAssignmentPlan,
    CommanderEngine,
    CommanderProfileLoader,
    CommanderScenarioConfig,
)
from stochastic_warfare.core.clock import (
    SimulationClock,
)
from stochastic_warfare.core.era import EraConfig, get_era_config
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.entities.base import Unit
from stochastic_warfare.logistics.config import (
    SupplyQuantityConfig,
)
from stochastic_warfare.morale.rout import RoutConfig, RoutEngine
from stochastic_warfare.morale.runtime import (
    MoraleRegistration,
    MoraleRuntime,
)
from stochastic_warfare.simulation.calibration import CalibrationSchema
from stochastic_warfare.simulation.deployment import (
    DeploymentMode,
    FormationTemplateLoader,
    deploy_units,
    check_side_separation,
)
from stochastic_warfare.simulation.equipment_mappings import (
    EQUIPMENT_MAPPING_REGISTRY,
)
from stochastic_warfare.simulation.era_runtime import (
    EraRuntimeContract,
)
from stochastic_warfare.simulation.force_builder import (
    InitialForcePlan,
    RuntimeForceBuilder,
)
from stochastic_warfare.simulation.loadouts import (
    RuntimeLoadoutBuilder,
    RuntimeLoadouts,
)
from stochastic_warfare.simulation.movement_diagnostics import (
    MovementDiagnostics,
)
from stochastic_warfare.simulation.context_checkpoint import (
    _CheckpointAggregateMoraleTopology,
    _checkpoint_aggregate_morale_topology,
    _initial_morale_for_units,
    _initial_status_for_morale,
)
from stochastic_warfare.simulation.runtime_context import SimulationContext
from stochastic_warfare.simulation.scenario_config import (
    CampaignScenarioConfig,
    DoctrineSideAssignment,
    ScenarioReferenceError,
    TerrainConfig,
    _doctrine_policy_index,
    load_campaign_scenario_config,
    parse_scenario_start_time,
)
from stochastic_warfare.simulation.tactical_targeting import (
    TacticalTargetingRuntime,
)
from stochastic_warfare.terrain.heightmap import Heightmap

logger = get_logger(__name__)


def _initialize_commander_ooda(
    *,
    commander_engine: CommanderEngine,
    ooda_engine: Any,
    school_registry: Any,
    assignments: tuple[tuple[str, str], ...],
    c2_rng: np.random.Generator,
    timestamp: datetime,
) -> None:
    """Register and start exact commander OODA state transactionally."""
    from stochastic_warfare.c2.ai.ooda import OODAPhase
    from stochastic_warfare.entities.organization.echelons import (
        EchelonLevel,
    )

    ooda_before = ooda_engine.get_state()
    c2_rng_before = copy.deepcopy(c2_rng.bit_generator.state)
    try:
        for unit_id, _profile_id in sorted(assignments):
            ooda_engine.register_commander(
                unit_id,
                int(EchelonLevel.COMPANY),
            )
            school_multiplier = 1.0
            if school_registry is not None:
                school = school_registry.get_for_unit(unit_id)
                if school is not None:
                    school_multiplier = school.get_ooda_multiplier()
            ooda_engine.start_phase(
                unit_id,
                OODAPhase.OBSERVE,
                personality_mult=(commander_engine.get_ooda_speed_multiplier(unit_id)),
                tactical_mult=(ooda_engine.tactical_acceleration * school_multiplier),
                ts=timestamp,
                publish_event=False,
            )
    except Exception:
        ooda_engine.set_state(ooda_before)
        c2_rng.bit_generator.state = c2_rng_before
        raise


def _prepare_runtime_school_plan(
    *,
    config: CampaignScenarioConfig,
    commander_engine: CommanderEngine | None,
    commander_assignments: tuple[tuple[str, str], ...],
    school_registry: Any,
    unit_sides: Mapping[str, str],
    doctrine_side_assignments: tuple[DoctrineSideAssignment, ...],
) -> Any:
    """Stage profile, exact-unit, then highest-precedence side policy."""
    school_assignments: dict[str, str] = {}
    if commander_engine is not None:
        school_assignments.update(
            {
                unit_id: personality.school_id
                for unit_id, profile_id in commander_assignments
                if (personality := commander_engine.get_profile_definition(profile_id)).school_id is not None
            }
        )

    exact_assignments = config.school_config.unit_assignments if config.school_config is not None else {}
    if not isinstance(exact_assignments, Mapping):
        raise ValueError(
            "school_config.unit_assignments must be a mapping",
        )
    school_assignments.update(
        {unit_id: exact_assignments[unit_id] for unit_id in unit_sides if unit_id in exact_assignments}
    )

    side_policy = _doctrine_policy_index(doctrine_side_assignments)
    school_assignments.update(
        {unit_id: side_policy[side] for unit_id, side in unit_sides.items() if side in side_policy}
    )
    if not school_assignments:
        return None
    if school_registry is None:
        raise ValueError(
            "Runtime school assignments require a loaded school registry",
        )
    return school_registry.prepare_assignments(
        school_assignments,
        expected_unit_ids=set(unit_sides),
    )


def register_dynamic_units(
    ctx: SimulationContext,
    units: list[Unit],
) -> None:
    """Atomically register fully constructed units and their runtime state.

    Loadouts and side-derived morale are staged before any context-owned
    mapping changes.  A failed wave therefore remains retryable and cannot
    leave partial roster, loadout, or morale state behind.
    """
    if not units:
        return

    unit_ids = [unit.entity_id for unit in units]
    if any(not unit_id for unit_id in unit_ids):
        raise ValueError("Dynamic units require non-empty entity IDs")
    if len(unit_ids) != len(set(unit_ids)):
        raise ValueError(
            f"Dynamic unit wave contains duplicate entity IDs: {unit_ids!r}",
        )

    existing_ids = {unit.entity_id for unit in ctx.all_units()}
    collisions = sorted(existing_ids & set(unit_ids))
    if collisions:
        raise ValueError(
            f"Dynamic unit IDs already exist in the scenario: {collisions!r}",
        )

    unknown_sides = sorted(
        {unit.side if isinstance(unit.side, str) else unit.side.value for unit in units} - set(ctx.units_by_side)
    )
    if unknown_sides:
        raise ValueError(
            f"Dynamic units reference unknown sides: {unknown_sides!r}",
        )

    if ctx.loadout_builder is None:
        raise RuntimeError(
            "Dynamic units require the scenario's RuntimeLoadoutBuilder",
        )
    incoming_loadouts = ctx.loadout_builder.build(units)
    incoming_weapons = incoming_loadouts.unit_weapons
    incoming_sensor_attachments = incoming_loadouts.unit_sensor_attachments
    incoming_sensors = incoming_loadouts.unit_sensors
    incoming_resolutions = incoming_loadouts.equipment_resolutions
    incoming_ids = set(unit_ids)
    if set(incoming_weapons) != incoming_ids:
        raise ValueError("Dynamic weapon loadout topology is incomplete")
    if set(incoming_sensors) != incoming_ids:
        raise ValueError("Dynamic sensor loadout topology is incomplete")
    if set(incoming_sensor_attachments) != incoming_ids:
        raise ValueError(
            "Dynamic sensor-attachment topology is incomplete",
        )

    incoming_morale = _initial_morale_for_units(ctx.config, units)
    incoming_statuses = {
        unit.entity_id: _initial_status_for_morale(
            incoming_morale[unit.entity_id],
        )
        for unit in units
    }
    if set(ctx.unit_weapons) & incoming_ids:
        raise ValueError("Dynamic weapon loadout IDs already exist")
    if set(ctx.unit_sensors) & incoming_ids:
        raise ValueError("Dynamic sensor loadout IDs already exist")
    if set(ctx.unit_sensor_attachments) & incoming_ids:
        raise ValueError(
            "Dynamic sensor-attachment IDs already exist",
        )
    if set(ctx.equipment_resolutions) & incoming_ids:
        raise ValueError("Dynamic equipment-resolution IDs already exist")
    if set(ctx.morale_states) & incoming_ids:
        raise ValueError("Dynamic morale IDs already exist")
    if ctx.morale_runtime is None:
        raise RuntimeError("Dynamic units require a morale runtime")
    if ctx.tactical_targeting is None:
        raise RuntimeError("Dynamic units require tactical targeting ownership")

    commander_plan: CommanderAssignmentPlan | None = None
    school_plan: Any = None
    if ctx.commander_engine is not None:
        if ctx.ooda_engine is None:
            raise RuntimeError(
                "Dynamic commander assignments require an OODA engine",
            )
        existing_commander_ids = set(
            ctx.commander_engine.assignments(),
        )
        if existing_commander_ids != existing_ids:
            raise ValueError(
                "Commander assignment topology does not match the current runtime roster",
            )
        existing_ooda_ids = set(
            ctx.ooda_engine.get_state()["commanders"],
        )
        if existing_ooda_ids != existing_ids:
            raise ValueError(
                "OODA commander topology does not match the current runtime roster",
            )
        side_profiles = {side.side: side.commander_profile for side in ctx.config.sides}
        commander_overrides = ctx.config.commander_config.assignments if ctx.config.commander_config is not None else {}
        incoming_assignments = {
            unit.entity_id: commander_overrides.get(
                unit.entity_id,
                side_profiles[(unit.side if isinstance(unit.side, str) else unit.side.value)],
            )
            for unit in units
        }
        commander_plan = ctx.commander_engine.prepare_assignments(
            incoming_assignments,
            expected_unit_ids=incoming_ids,
            require_complete=True,
        )
    school_plan = _prepare_runtime_school_plan(
        config=ctx.config,
        commander_engine=ctx.commander_engine,
        commander_assignments=(commander_plan.assignments if commander_plan is not None else ()),
        school_registry=ctx.school_registry,
        unit_sides={unit.entity_id: (unit.side if isinstance(unit.side, str) else unit.side.value) for unit in units},
        doctrine_side_assignments=ctx.doctrine_side_assignments,
    )

    logistics_plan = None
    logistics_before = None
    if ctx.logistics_runtime is not None:
        elapsed_seconds = ctx.clock.elapsed.total_seconds()
        logistics_plan = ctx.logistics_runtime.prepare_unit_registration(
            units,
            eligible_from_seconds=elapsed_seconds,
        )
        logistics_before = ctx.logistics_runtime.get_state()

    staged_units_by_side = {side: list(side_units) for side, side_units in ctx.units_by_side.items()}
    for unit in units:
        side = unit.side if isinstance(unit.side, str) else unit.side.value
        staged_units_by_side[side].append(unit)
    staged_weapons = dict(ctx.unit_weapons)
    staged_weapons.update(incoming_weapons)
    staged_sensor_attachments = dict(ctx.unit_sensor_attachments)
    staged_sensor_attachments.update(incoming_sensor_attachments)
    staged_resolutions = dict(ctx.equipment_resolutions)
    staged_resolutions.update(incoming_resolutions)
    staged_loadouts = RuntimeLoadouts(
        unit_weapons=staged_weapons,
        unit_sensor_attachments=staged_sensor_attachments,
        equipment_resolutions=staged_resolutions,
    )
    morale_before = ctx.morale_runtime.get_state()
    commander_before = ctx.commander_engine.get_state() if ctx.commander_engine is not None else None
    school_before = ctx.school_registry.get_state() if ctx.school_registry is not None else None
    ooda_before = ctx.ooda_engine.get_state() if ctx.commander_engine is not None else None
    movement_before = (
        ctx.movement_diagnostics.stage_state(
            ctx.movement_diagnostics.get_state(),
            expected_unit_sides={
                unit.entity_id: (unit.side if isinstance(unit.side, str) else unit.side.value)
                for unit in ctx.all_units()
            },
        )
        if ctx.movement_diagnostics is not None
        else None
    )
    targeting_before = ctx.tactical_targeting.stage_state(
        ctx.tactical_targeting.get_state(),
    )
    c2_rng = ctx.rng_manager.get_stream(ModuleId.C2)
    c2_rng_before = copy.deepcopy(c2_rng.bit_generator.state)
    incoming_status_before = tuple((unit, unit.status) for unit in units)

    # Every component has validated the complete batch before the first
    # commit. Roll back all component-owned state if an unexpected commit
    # failure occurs so the reinforcement wave remains retryable.
    try:
        if logistics_plan is not None:
            ctx.logistics_runtime.commit_unit_registration(logistics_plan)
        for unit in units:
            unit.status = incoming_statuses[unit.entity_id]
        ctx.morale_runtime.register_units(
            tuple(
                MoraleRegistration(
                    unit_id=unit.entity_id,
                    initial_state=incoming_morale[unit.entity_id],
                )
                for unit in units
            ),
            {unit.entity_id: unit for unit in units},
        )
        if commander_plan is not None:
            ctx.commander_engine.commit_assignments(commander_plan)
        if school_plan is not None:
            ctx.school_registry.commit_assignments(school_plan)
        if commander_plan is not None:
            _initialize_commander_ooda(
                commander_engine=ctx.commander_engine,
                ooda_engine=ctx.ooda_engine,
                school_registry=ctx.school_registry,
                assignments=commander_plan.assignments,
                c2_rng=c2_rng,
                timestamp=ctx.clock.current_time,
            )
        if ctx.movement_diagnostics is not None:
            ctx.movement_diagnostics.register_units({unit.entity_id: unit.side for unit in units})
        ctx.tactical_targeting.register_units(
            {unit.entity_id: (unit.side if isinstance(unit.side, str) else unit.side.value) for unit in units}
        )
    except Exception:
        for unit, status in incoming_status_before:
            unit.status = status
        if logistics_before is not None:
            ctx.logistics_runtime.set_state(
                logistics_before,
                expected_units={unit.entity_id: unit for unit in ctx.all_units()},
            )
        rollback_aggregate_topology = (
            _checkpoint_aggregate_morale_topology(
                ctx.aggregation_engine.get_state(),
            )
            if ctx.aggregation_engine is not None
            else _CheckpointAggregateMoraleTopology({}, {}, {})
        )
        ctx.morale_runtime.set_state(
            morale_before,
            expected_units={unit.entity_id: unit for unit in ctx.all_units()},
            elapsed_time_s=ctx.clock.elapsed.total_seconds(),
            aggregate_constituents=rollback_aggregate_topology.constituents,
            suspended_statuses=rollback_aggregate_topology.statuses,
        )
        if commander_before is not None:
            ctx.commander_engine.set_state(commander_before)
        if school_before is not None:
            ctx.school_registry.set_state(school_before)
        if ooda_before is not None:
            ctx.ooda_engine.set_state(ooda_before)
        if movement_before is not None:
            ctx.movement_diagnostics.commit_state(movement_before)
        ctx.tactical_targeting.commit_state(targeting_before)
        c2_rng.bit_generator.state = c2_rng_before
        raise
    ctx.units_by_side = staged_units_by_side
    ctx.unit_weapons = dict(staged_loadouts.unit_weapons)
    ctx.unit_sensor_attachments = dict(
        staged_loadouts.unit_sensor_attachments,
    )
    ctx.unit_sensors = dict(staged_loadouts.unit_sensors)
    ctx.equipment_resolutions = dict(
        staged_loadouts.equipment_resolutions,
    )
    ctx._validate_loadout_bindings()
    ctx._validate_targeting_bindings()


def _parse_weather_state(precip: str) -> int:
    """Map scenario precipitation string to WeatherState int."""
    from stochastic_warfare.environment.weather import WeatherState

    _MAP = {
        "clear": WeatherState.CLEAR,
        "partly_cloudy": WeatherState.PARTLY_CLOUDY,
        "overcast": WeatherState.OVERCAST,
        "light_rain": WeatherState.LIGHT_RAIN,
        "heavy_rain": WeatherState.HEAVY_RAIN,
        "snow": WeatherState.SNOW,
        "fog": WeatherState.FOG,
        "storm": WeatherState.STORM,
    }
    return _MAP.get(precip.lower(), WeatherState.CLEAR)


# ---------------------------------------------------------------------------
# Scenario loader
# ---------------------------------------------------------------------------


class ScenarioLoader:
    """Load a campaign scenario from YAML and wire all domain engines.

    Parameters
    ----------
    data_dir:
        Root data directory containing ``units/``, ``weapons/``, etc.
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = Path(data_dir)

    def load(
        self,
        scenario_path: Path,
        seed: int = 42,
        *,
        calibration_overrides: Mapping[str, Any] | CalibrationSchema | None = None,
        scenario_config: CampaignScenarioConfig | None = None,
        doctrine_side_assignments: tuple[
            DoctrineSideAssignment,
            ...,
        ]
        | None = None,
        era_config: EraConfig | None = None,
        era_runtime_contract: EraRuntimeContract | None = None,
    ) -> SimulationContext:
        """Load a campaign scenario and create a fully-wired context.

        Parameters
        ----------
        scenario_path:
            Path to the campaign scenario YAML file.
        seed:
            Master PRNG seed for deterministic replay.
        calibration_overrides:
            Sparse ``CalibrationSchema`` overlay applied without mutating the
            source scenario.
        scenario_config:
            Prevalidated effective configuration supplied by an orchestrator.
        doctrine_side_assignments:
            Highest-precedence typed per-side school policy supplied by the
            runtime factory. It is not written into scenario YAML.
        era_config:
            Isolated era configuration captured by the runtime factory. It
            must be paired with ``era_runtime_contract``. Direct loads omit
            both values and resolve the registry at this boundary.
        era_runtime_contract:
            Frozen effective behavior captured by the runtime factory.
        """
        # 1. Parse config
        if scenario_config is not None and calibration_overrides is not None:
            raise ValueError(
                "scenario_config and calibration_overrides are mutually exclusive",
            )
        if scenario_config is None:
            config = load_campaign_scenario_config(
                scenario_path,
                calibration_overrides,
            )
        else:
            config = CampaignScenarioConfig.model_validate(
                scenario_config.model_dump(mode="python"),
                strict=True,
                extra="forbid",
            )
        provided_era_config = era_config is not None
        provided_era_contract = era_runtime_contract is not None
        if provided_era_config != provided_era_contract:
            raise ValueError(
                "era_config and era_runtime_contract must be supplied together",
            )
        if era_config is None:
            resolved_era_config = get_era_config(config.era)
            resolved_era_contract = EraRuntimeContract.resolve(
                selected_registry_id=config.era,
                era_config=resolved_era_config,
                strategic_s=config.tick_resolution.strategic_s,
                operational_s=config.tick_resolution.operational_s,
                tactical_s=config.tick_resolution.tactical_s,
                tick_duration_seconds=config.tick_duration_seconds,
            )
        else:
            if not isinstance(era_config, EraConfig):
                raise TypeError("era_config must be an EraConfig")
            if not isinstance(era_runtime_contract, EraRuntimeContract):
                raise TypeError(
                    "era_runtime_contract must be an EraRuntimeContract",
                )
            resolved_era_config = EraConfig.model_validate(
                era_config.model_dump(mode="python"),
                strict=True,
                extra="forbid",
            )
            resolved_era_contract = EraRuntimeContract.model_validate(
                era_runtime_contract.model_dump(mode="python"),
                strict=True,
                extra="forbid",
            )
            if resolved_era_contract.selected_registry_id != config.era:
                raise ValueError(
                    f"Prepared era contract registry identity does not match scenario era {config.era!r}",
                )
            expected_era_contract = EraRuntimeContract.resolve(
                selected_registry_id=config.era,
                era_config=resolved_era_config,
                strategic_s=config.tick_resolution.strategic_s,
                operational_s=config.tick_resolution.operational_s,
                tactical_s=config.tick_resolution.tactical_s,
                tick_duration_seconds=config.tick_duration_seconds,
            )
            if resolved_era_contract != expected_era_contract:
                raise ValueError(
                    "Prepared era runtime contract does not match its captured scenario and era configuration",
                )
        era_config = resolved_era_config
        era_runtime_contract = resolved_era_contract
        start_dt = parse_scenario_start_time(config.date)
        era_runtime_contract.validate_execution_horizon(
            start=start_dt,
            duration_hours=config.duration_hours,
        )
        doctrine_policy = tuple(doctrine_side_assignments or ())
        if any(not isinstance(assignment, DoctrineSideAssignment) for assignment in doctrine_policy):
            raise TypeError(
                "doctrine_side_assignments must contain only DoctrineSideAssignment values",
            )
        doctrine_index = _doctrine_policy_index(doctrine_policy)
        known_sides = {side.side for side in config.sides}
        unknown_doctrine_sides = sorted(
            set(doctrine_index) - known_sides,
        )
        if unknown_doctrine_sides:
            raise ScenarioReferenceError(
                f"Doctrine policy references unknown scenario sides: {unknown_doctrine_sides!r}",
            )
        logger.info("Loaded campaign %r from %s", config.name, scenario_path)

        # 2. Core infrastructure
        rng_mgr = RNGManager(seed)
        bus = EventBus()
        # The engine detects initial force proximity and picks the right
        # starting resolution (strategic vs tactical), so we always
        # initialize the clock at strategic pace here.
        clock = SimulationClock(
            start=start_dt,
            tick_duration=timedelta(
                seconds=era_runtime_contract.strategic_s,
            ),
        )

        # 3. Terrain
        self._real_terrain_ctx = None
        heightmap = self._build_terrain(config.terrain, rng_mgr, config)

        # 4. Load YAML data (era-aware)
        loaders = self._create_loaders(era=era_config.era.value)
        self._validate_reinforcement_unit_types(config, loaders["unit_loader"])
        self._validate_logistics_catalog(
            config,
            loaders["supply_item_loader"],
        )
        initial_force_plans = self._initial_force_plans(config)
        initial_unit_ids = set(
            RuntimeForceBuilder.initial_entity_ids(initial_force_plans),
        )
        planned_unit_sides = self._planned_unit_sides(
            config,
            initial_force_plans,
        )
        commander_engine, initial_commander_plan = self._prepare_commander_engine(
            config,
            loaders["commander_profile_loader"],
            rng_mgr.get_stream(ModuleId.C2),
            initial_unit_ids=initial_unit_ids,
            planned_unit_sides=planned_unit_sides,
            schools_enabled=(config.school_config is not None or bool(doctrine_policy)),
        )
        self._validate_school_assignments(
            config,
            planned_unit_sides=planned_unit_sides,
            doctrine_side_assignments=doctrine_policy,
        )
        reachable_unit_types = tuple(entry.unit_type for side in config.sides for entry in side.units) + tuple(
            unit.unit_type for wave in config.reinforcements for unit in wave.units
        )
        loadout_builder = RuntimeLoadoutBuilder(
            weapon_loader=loaders["weapon_loader"],
            ammo_loader=loaders["ammo_loader"],
            sensor_loader=loaders["sensor_loader"],
            unit_definitions=loaders["unit_loader"].definitions(),
            era_config=era_config,
            assignment_overrides=(config.calibration_overrides.weapon_assignments),
            reachable_unit_types=reachable_unit_types,
            registry=EQUIPMENT_MAPPING_REGISTRY,
        )

        # 5. Build forces
        entities_rng = rng_mgr.get_stream(ModuleId.ENTITIES)
        force_builder = RuntimeForceBuilder(
            unit_loader=loaders["unit_loader"],
            rng=entities_rng,
        )
        entities_rng_before = copy.deepcopy(
            entities_rng.bit_generator.state,
        )
        try:
            units_by_side, runtime_loadouts = self._build_all_forces(
                config,
                initial_force_plans,
                force_builder,
                entities_rng,
                loadout_builder,
            )
        except Exception:
            entities_rng.bit_generator.state = entities_rng_before
            raise
        from stochastic_warfare.simulation.time_on_target import (
            TimeOnTargetMissionResolver,
        )

        time_on_target_missions = TimeOnTargetMissionResolver.resolve(
            config.indirect_fire,
            units_by_side=units_by_side,
            runtime_loadouts=runtime_loadouts,
            terrain=heightmap,
            duration_hours=config.duration_hours,
            tick_duration_seconds=config.tick_duration_seconds,
        )

        # 6. Morale state tracking
        all_units = [unit for side_units in units_by_side.values() for unit in side_units]
        morale_states = _initial_morale_for_units(config, all_units)

        # 7. Create domain engines (era-gated)
        engines = self._create_engines(
            rng_mgr,
            bus,
            heightmap,
            loaders,
            config,
            clock,
            units_by_side,
            era_config=era_config,
            era_runtime_contract=era_runtime_contract,
            doctrine_side_assignments=doctrine_policy,
            time_on_target_missions=time_on_target_missions,
        )
        if commander_engine is not None:
            if initial_commander_plan is None:
                raise RuntimeError(
                    "Commander engine was created without an assignment plan",
                )
            engines["commander_engine"] = commander_engine
            commander_engine.commit_assignments(
                initial_commander_plan,
                replace=True,
            )
        initial_school_plan = _prepare_runtime_school_plan(
            config=config,
            commander_engine=commander_engine,
            commander_assignments=(initial_commander_plan.assignments if initial_commander_plan is not None else ()),
            school_registry=engines.get("school_registry"),
            unit_sides={unit_id: planned_unit_sides[unit_id] for unit_id in initial_unit_ids},
            doctrine_side_assignments=doctrine_policy,
        )
        if initial_school_plan is not None:
            engines["school_registry"].commit_assignments(
                initial_school_plan,
            )
        if commander_engine is not None:
            ooda_engine = engines.get("ooda_engine")
            if ooda_engine is None:
                raise RuntimeError(
                    "Commander engine was created without an OODA engine",
                )
            _initialize_commander_ooda(
                commander_engine=commander_engine,
                ooda_engine=ooda_engine,
                school_registry=engines.get("school_registry"),
                assignments=initial_commander_plan.assignments,
                c2_rng=rng_mgr.get_stream(ModuleId.C2),
                timestamp=clock.current_time,
            )

        morale_runtime = engines.get("morale_runtime")
        if morale_runtime is None:
            raise RuntimeError(
                "Scenario loader did not create a morale runtime",
            )
        for unit in all_units:
            unit.status = _initial_status_for_morale(
                morale_states[unit.entity_id],
            )
        morale_runtime.register_units(
            tuple(
                MoraleRegistration(
                    unit_id=unit.entity_id,
                    initial_state=morale_states[unit.entity_id],
                )
                for unit in all_units
            ),
            {unit.entity_id: unit for unit in all_units},
        )

        # 8. Assemble context
        real_ctx = self._real_terrain_ctx
        movement_diagnostics = MovementDiagnostics({unit.entity_id: unit.side for unit in all_units})
        tactical_targeting = TacticalTargetingRuntime(
            sensing_aware_standoff_enabled=(config.calibration_overrides.enable_sensing_aware_standoff),
            unit_sides={unit.entity_id: unit.side for unit in all_units},
        )
        ctx = SimulationContext(
            config=config,
            clock=clock,
            rng_manager=rng_mgr,
            event_bus=bus,
            heightmap=heightmap,
            classification=real_ctx.classification if real_ctx else None,
            infrastructure_manager=real_ctx.infrastructure if real_ctx else None,
            bathymetry=real_ctx.bathymetry if real_ctx else None,
            units_by_side=units_by_side,
            unit_weapons=dict(runtime_loadouts.unit_weapons),
            unit_sensor_attachments=dict(
                runtime_loadouts.unit_sensor_attachments,
            ),
            unit_sensors=dict(runtime_loadouts.unit_sensors),
            equipment_resolutions=dict(
                runtime_loadouts.equipment_resolutions,
            ),
            force_builder=force_builder,
            loadout_builder=loadout_builder,
            movement_diagnostics=movement_diagnostics,
            tactical_targeting=tactical_targeting,
            doctrine_side_assignments=doctrine_policy,
            calibration=config.calibration_overrides,
            era_config=era_config,
            era_runtime_contract=era_runtime_contract,
            **engines,
            **loaders,
        )
        ctx._validate_loadout_bindings()
        ctx._validate_targeting_bindings()

        # Phase 104: warn if deployment boxes are too close or overlap
        if config.deployment.mode.value != "legacy":
            check_side_separation(
                config.deployment.blue_box,
                config.deployment.red_box,
                config.deployment.min_side_separation_m,
            )

        # 10. Pre-emplaced IEDs / HBIEDs (Phase 101)
        self._emplace_initial_ieds(ctx, config)

        # 11. Scripted events — stash on context for campaign manager (Phase 101)
        ctx.scripted_events = list(config.scripted_events)

        return ctx

    # ── Private helpers ──────────────────────────────────────────────

    def _emplace_initial_ieds(
        self,
        ctx: SimulationContext,
        config: CampaignScenarioConfig,
    ) -> None:
        """Emplace pre-prepared IEDs / HBIEDs (Phase 101).

        Used for urban scenarios where insurgents have pre-wired the
        battlespace before coalition forces arrive (e.g. Fallujah 2004).
        Each entry calls ``unconventional_engine.emplace_ied`` and the
        returned obstacle IDs are registered on the context in order so
        scripted events can reference them by index.
        """
        if not config.initial_ieds:
            return
        uw_eng = getattr(ctx, "unconventional_engine", None)
        if uw_eng is None:
            logger.warning(
                "initial_ieds configured but unconventional_engine is None — skipping",
            )
            return
        from stochastic_warfare.core.types import Position

        obstacle_ids: list[str] = []
        for idx, ied in enumerate(config.initial_ieds):
            pos = Position(easting=ied.position[0], northing=ied.position[1], altitude=0.0)
            obs_id = uw_eng.emplace_ied(
                position=pos,
                subtype=ied.subtype,
                blast_radius_m=ied.blast_radius_m,
                concealment=ied.concealment,
                emplaced_by=ied.emplaced_by or f"pre_emplaced_{idx}",
                timestamp=ctx.clock.current_time,
            )
            obstacle_ids.append(obs_id)
        ctx.initial_ied_obstacle_ids = obstacle_ids
        logger.info("Emplaced %d pre-prepared IEDs/HBIEDs", len(obstacle_ids))

    @staticmethod
    def _initial_force_plans(
        config: CampaignScenarioConfig,
    ) -> tuple[InitialForcePlan, ...]:
        """Resolve typed initial placement inputs without consuming RNG."""
        plans: list[InitialForcePlan] = []
        calibration = config.calibration_overrides
        for side_index, side_config in enumerate(config.sides):
            prefix = side_config.side
            default_easting = 100.0 if side_index == 0 else config.terrain.width_m - 100.0
            default_northing = config.terrain.height_m / 2
            start_easting = calibration.get(
                f"{prefix}_start_x",
                default_easting,
            )
            start_northing = calibration.get(
                f"{prefix}_start_y",
                default_northing,
            )
            spacing = calibration.get(
                f"{prefix}_formation_spacing_m",
                calibration.get("formation_spacing_m", 50.0),
            )
            plans.append(
                InitialForcePlan(
                    side=side_config.side,
                    units=tuple(side_config.units),
                    start_easting=float(start_easting),
                    start_northing=float(start_northing),
                    spacing_m=float(spacing),
                ),
            )
        return tuple(plans)

    @staticmethod
    def _planned_unit_sides(
        config: CampaignScenarioConfig,
        initial_plans: tuple[InitialForcePlan, ...],
    ) -> dict[str, str]:
        """Return exact initial and future reinforcement identity topology."""
        planned = {spec.entity_id: spec.side for spec in RuntimeForceBuilder.initial_specs(initial_plans)}
        for wave_ordinal, reinforcement in enumerate(
            config.reinforcements,
        ):
            unit_index = 0
            for unit_config in reinforcement.units:
                for _ in range(unit_config.count):
                    entity_id = (
                        f"reinforce_{reinforcement.side}_{wave_ordinal:04d}_{unit_config.unit_type}_{unit_index:04d}"
                    )
                    if entity_id in planned:
                        raise ValueError(
                            f"Duplicate planned unit ID {entity_id!r}",
                        )
                    planned[entity_id] = reinforcement.side
                    unit_index += 1
        return planned

    def _validate_school_assignments(
        self,
        config: CampaignScenarioConfig,
        *,
        planned_unit_sides: Mapping[str, str],
        doctrine_side_assignments: tuple[
            DoctrineSideAssignment,
            ...,
        ],
    ) -> None:
        """Validate exact-unit and analysis school references pre-runtime."""
        raw_exact = config.school_config.unit_assignments if config.school_config is not None else {}
        if not isinstance(raw_exact, Mapping):
            raise ScenarioReferenceError(
                "school_config.unit_assignments must be a mapping",
            )
        exact_assignments: dict[str, str] = {}
        for unit_id, school_id in raw_exact.items():
            if not isinstance(unit_id, str) or not unit_id or unit_id != unit_id.strip():
                raise ScenarioReferenceError(
                    "School assignment unit IDs must be non-empty trimmed strings",
                )
            if not isinstance(school_id, str) or not school_id or school_id != school_id.strip():
                raise ScenarioReferenceError(
                    "School assignment school IDs must be non-empty trimmed strings",
                )
            exact_assignments[unit_id] = school_id
        unknown_units = sorted(
            set(exact_assignments) - set(planned_unit_sides),
        )
        if unknown_units:
            raise ScenarioReferenceError(
                f"School assignments reference unknown initial or future unit IDs: {unknown_units!r}",
            )

        referenced_schools = set(exact_assignments.values()) | {
            assignment.school_id for assignment in doctrine_side_assignments
        }
        if not referenced_schools:
            return
        from stochastic_warfare.c2.ai.schools import SchoolLoader

        school_loader = SchoolLoader(self._data_dir / "schools")
        school_loader.load_all()
        missing_schools = sorted(
            referenced_schools - set(school_loader.available_schools()),
        )
        if missing_schools:
            raise ScenarioReferenceError(
                f"Runtime assignments reference unknown doctrinal schools: {missing_schools!r}",
            )

    def _prepare_commander_engine(
        self,
        config: CampaignScenarioConfig,
        profile_loader: CommanderProfileLoader,
        c2_rng: np.random.Generator,
        *,
        initial_unit_ids: set[str],
        planned_unit_sides: Mapping[str, str],
        schools_enabled: bool,
    ) -> tuple[
        CommanderEngine | None,
        CommanderAssignmentPlan | None,
    ]:
        """Validate commander authority before any unit construction."""
        side_profiles = {side.side: side.commander_profile for side in config.sides if side.commander_profile}
        if not side_profiles:
            return None, None

        for side, profile_id in sorted(side_profiles.items()):
            try:
                profile_loader.get_definition(profile_id)
            except KeyError as exc:
                raise ScenarioReferenceError(
                    f"Side {side!r} references unknown commander_profile {profile_id!r}",
                ) from exc

        commander_config = config.commander_config if config.commander_config is not None else CommanderScenarioConfig()
        planned_ids = set(planned_unit_sides)
        unknown_assignment_ids = sorted(
            set(commander_config.assignments) - planned_ids,
        )
        if unknown_assignment_ids:
            raise ScenarioReferenceError(
                f"Commander assignments reference unknown initial or future unit IDs: {unknown_assignment_ids!r}",
            )
        for unit_id, profile_id in sorted(
            commander_config.assignments.items(),
        ):
            try:
                profile_loader.get_definition(profile_id)
            except KeyError as exc:
                raise ScenarioReferenceError(
                    f"Commander assignment for {unit_id!r} references unknown profile {profile_id!r}",
                ) from exc

        referenced_profile_ids = set(side_profiles.values()) | set(
            commander_config.assignments.values(),
        )
        referenced_school_ids = {
            definition.school_id
            for profile_id in referenced_profile_ids
            if (definition := profile_loader.get_definition(profile_id)).school_id is not None
        }
        if referenced_school_ids:
            if not schools_enabled:
                raise ScenarioReferenceError(
                    "Commander profiles reference doctrinal schools but no runtime school registry is enabled",
                )
            from stochastic_warfare.c2.ai.schools import SchoolLoader

            school_loader = SchoolLoader(self._data_dir / "schools")
            school_loader.load_all()
            missing_schools = sorted(
                referenced_school_ids - set(school_loader.available_schools()),
            )
            if missing_schools:
                raise ScenarioReferenceError(
                    f"Commander profiles reference unknown doctrinal schools: {missing_schools!r}",
                )

        initial_assignments = {
            unit_id: side_profiles[planned_unit_sides[unit_id]] for unit_id in sorted(initial_unit_ids)
        }
        initial_assignments.update(
            {
                unit_id: profile_id
                for unit_id, profile_id in commander_config.assignments.items()
                if unit_id in initial_unit_ids
            }
        )
        engine = CommanderEngine(
            profile_loader,
            c2_rng,
            commander_config.engine_config(),
        )
        plan = engine.prepare_assignments(
            initial_assignments,
            expected_unit_ids=initial_unit_ids,
            require_complete=True,
        )
        return engine, plan

    def _build_terrain(
        self,
        spec: TerrainConfig,
        rng_mgr: RNGManager,
        config: CampaignScenarioConfig | None = None,
    ) -> Heightmap:
        """Build heightmap from terrain specification."""
        if spec.terrain_source == "real":
            return self._build_real_terrain(spec, config)

        from stochastic_warfare.terrain.procedural import build_terrain

        terrain_rng = rng_mgr.get_stream(ModuleId.TERRAIN)
        return build_terrain(spec, terrain_rng)

    def _build_real_terrain(
        self,
        spec: TerrainConfig,
        config: CampaignScenarioConfig | None = None,
    ) -> Heightmap:
        """Build terrain from real-world geospatial data."""
        from stochastic_warfare.terrain.data_pipeline import (
            BoundingBox,
            TerrainDataConfig,
            load_real_terrain,
        )
        from stochastic_warfare.coordinates.transforms import ScenarioProjection

        lat = config.latitude if config else 0.0
        lon = config.longitude if config else 0.0
        projection = ScenarioProjection(lat, lon)

        # Compute bbox from lat/lon + width/height
        meters_per_deg_lat = 111_320.0
        meters_per_deg_lon = 111_320.0 * math.cos(math.radians(lat))
        half_h = (spec.height_m / 2) / meters_per_deg_lat
        half_w = (spec.width_m / 2) / meters_per_deg_lon

        bbox = BoundingBox(
            south=lat - half_h,
            west=lon - half_w,
            north=lat + half_h,
            east=lon + half_w,
        )
        tdc = TerrainDataConfig(
            bbox=bbox,
            cell_size_m=spec.cell_size_m,
            data_dir=spec.data_dir,
            cache_dir=spec.cache_dir,
        )

        ctx = load_real_terrain(tdc, projection)

        # Stash extra layers for the SimulationContext to pick up
        self._real_terrain_ctx = ctx
        return ctx.heightmap

    def _create_loaders(self, era: str = "modern") -> dict[str, Any]:
        """Create and initialize all YAML data loaders.

        When *era* is not ``"modern"``, also loads YAML definitions from
        ``data/eras/{era}/`` — era-specific files add to (not replace)
        the base data set.
        """
        from stochastic_warfare.entities.loader import load_effective_unit_loader
        from stochastic_warfare.combat.ammunition import AmmoLoader, WeaponLoader
        from stochastic_warfare.detection.signatures import SignatureLoader
        from stochastic_warfare.detection.sensors import SensorLoader
        from stochastic_warfare.logistics.supply_classes import SupplyItemLoader

        unit_loader = load_effective_unit_loader(self._data_dir, era)

        weapon_loader = WeaponLoader(self._data_dir / "weapons")
        weapon_loader.load_all()

        ammo_loader = AmmoLoader(self._data_dir / "ammunition")
        ammo_loader.load_all()

        sig_loader = SignatureLoader(self._data_dir / "signatures")
        sig_loader.load_all()

        sensor_loader = SensorLoader(self._data_dir / "sensors")
        sensor_loader.load_all()

        supply_item_loader = SupplyItemLoader(
            self._data_dir / "logistics" / "supply_items",
        )
        supply_item_loader.load_all()

        commander_profile_loader = CommanderProfileLoader(
            self._data_dir / "commander_profiles",
        )
        commander_catalogs = [self._data_dir / "commander_profiles"]
        if era != "modern":
            commander_catalogs.append(
                self._data_dir / "eras" / era / "commanders",
            )
        commander_profile_loader.load_directories(commander_catalogs)

        # Load era-specific data on top of base data
        if era != "modern":
            era_dir = self._data_dir / "eras" / era
            if era_dir.is_dir():
                era_weapons = era_dir / "weapons"
                if era_weapons.is_dir():
                    era_weapon_loader = WeaponLoader(era_weapons)
                    era_weapon_loader.load_all()
                    weapon_loader._definitions.update(era_weapon_loader._definitions)

                era_ammo = era_dir / "ammunition"
                if era_ammo.is_dir():
                    era_ammo_loader = AmmoLoader(era_ammo)
                    era_ammo_loader.load_all()
                    ammo_loader._definitions.update(era_ammo_loader._definitions)

                era_sigs = era_dir / "signatures"
                if era_sigs.is_dir():
                    era_sig_loader = SignatureLoader(era_sigs)
                    era_sig_loader.load_all()
                    sig_loader._profiles.update(era_sig_loader._profiles)

                era_sensors = era_dir / "sensors"
                if era_sensors.is_dir():
                    era_sensor_loader = SensorLoader(era_sensors)
                    era_sensor_loader.load_all()
                    sensor_loader._definitions.update(era_sensor_loader._definitions)

                logger.info("Loaded era-specific data from %s", era_dir)

        return {
            "unit_loader": unit_loader,
            "weapon_loader": weapon_loader,
            "ammo_loader": ammo_loader,
            "sig_loader": sig_loader,
            "sensor_loader": sensor_loader,
            "supply_item_loader": supply_item_loader,
            "commander_profile_loader": commander_profile_loader,
        }

    @staticmethod
    def _validate_reinforcement_unit_types(
        config: CampaignScenarioConfig,
        unit_loader: Any,
    ) -> None:
        """Reject unresolved reinforcement definitions during scenario load."""
        available = set(unit_loader.available_types())
        unknown = [
            (wave_index, unit_config.unit_type)
            for wave_index, wave in enumerate(config.reinforcements)
            for unit_config in wave.units
            if unit_config.unit_type not in available
        ]
        if unknown:
            details = ", ".join(f"wave {wave_index}: {unit_type!r}" for wave_index, unit_type in unknown)
            raise ScenarioReferenceError(
                f"Reinforcement schedule references unknown unit types ({details})",
            )

    @staticmethod
    def _validate_logistics_catalog(
        config: CampaignScenarioConfig,
        supply_item_loader: Any,
    ) -> None:
        """Validate configured logistics items and depot mass before RNG use."""

        def definition_for(
            entry: SupplyQuantityConfig,
            location: str,
        ) -> Any:
            try:
                definition = supply_item_loader.get_definition(entry.item_id)
            except KeyError as exc:
                raise ScenarioReferenceError(
                    f"{location} references unknown supply item {entry.item_id!r}",
                ) from exc
            if definition.supply_class != entry.supply_class:
                raise ScenarioReferenceError(
                    f"{location} declares {entry.supply_class} for "
                    f"{entry.item_id!r}, but the catalog declares "
                    f"{definition.supply_class}",
                )
            if (
                isinstance(definition.weight_per_unit_kg, bool)
                or not math.isfinite(definition.weight_per_unit_kg)
                or definition.weight_per_unit_kg <= 0.0
            ):
                raise RuntimeError(
                    f"Catalog item {entry.item_id!r} has invalid weight_per_unit_kg",
                )
            return definition

        for profile in config.logistics.unit_profiles:
            for field_name in (
                "initial_inventory",
                "maximum_inventory",
                "idle_consumption_per_hour",
            ):
                entries = getattr(profile, field_name)
                for entry in entries:
                    definition_for(
                        entry,
                        f"profile {profile.side}/{profile.unit_type} {field_name}",
                    )

        for side in config.sides:
            for depot in side.depots:
                total_kg = 0.0
                for entry in depot.initial_inventory or []:
                    definition = definition_for(
                        entry,
                        f"depot {depot.depot_id} initial_inventory",
                    )
                    total_kg += entry.quantity * definition.weight_per_unit_kg
                if total_kg > depot.capacity_tons * 1000.0 + 1e-9:
                    raise ScenarioReferenceError(
                        f"depot {depot.depot_id!r} initial inventory weighs "
                        f"{total_kg / 1000.0:.6g} tons and exceeds "
                        f"capacity_tons={depot.capacity_tons:.6g}",
                    )

    def _build_all_forces(
        self,
        config: CampaignScenarioConfig,
        plans: tuple[InitialForcePlan, ...],
        force_builder: RuntimeForceBuilder,
        entities_rng: np.random.Generator,
        loadout_builder: RuntimeLoadoutBuilder,
    ) -> tuple[dict[str, list[Unit]], RuntimeLoadouts]:
        """Build the exact typed roster, then attach runtime loadouts."""
        units_by_side = force_builder.build_initial(plans)
        for plan in plans:
            units = units_by_side[plan.side]
            # Phase 104: apply configured deployment mode (legacy preserves
            # the line-abreast positions assigned by RuntimeForceBuilder).
            # Per-unit `_manually_positioned` flag skips auto-deployment.
            if config.deployment.mode.value != "legacy":
                template = None
                if config.deployment.mode == DeploymentMode.DOCTRINAL:
                    template_id = (
                        config.deployment.blue_template if plan.side == "blue" else config.deployment.red_template
                    )
                    if template_id is not None:
                        template_loader = FormationTemplateLoader(
                            self._data_dir / "formations",
                        )
                        template_loader.load_all()
                        template = template_loader.get(template_id)
                        if template is None:
                            raise ScenarioReferenceError(
                                f"Formation template {template_id!r} "
                                f"referenced by side {plan.side!r} is unknown; "
                                f"available={template_loader.available()!r}",
                            )
                deploy_units(
                    units=units,
                    side=plan.side,
                    config=config.deployment,
                    legacy_start_x=plan.start_easting,
                    legacy_start_y=plan.start_northing,
                    legacy_spacing_m=plan.spacing_m,
                    template=template,
                    rng=entities_rng,
                )

        # Assign weapons and sensors
        all_units = [u for us in units_by_side.values() for u in us]
        runtime_loadouts = loadout_builder.build(all_units)

        return units_by_side, runtime_loadouts

    def _create_engines(
        self,
        rng_mgr: RNGManager,
        bus: EventBus,
        heightmap: Heightmap,
        loaders: dict[str, Any],
        config: CampaignScenarioConfig,
        clock: SimulationClock | None = None,
        units_by_side: dict[str, list] | None = None,
        *,
        era_config: EraConfig,
        era_runtime_contract: EraRuntimeContract,
        doctrine_side_assignments: tuple[
            DoctrineSideAssignment,
            ...,
        ] = (),
        time_on_target_missions: tuple[ResolvedTimeOnTargetMission, ...] = (),
    ) -> dict[str, Any]:
        """Create all domain engine instances."""
        combat_rng = rng_mgr.get_stream(ModuleId.COMBAT)
        detection_rng = rng_mgr.get_stream(ModuleId.DETECTION)
        morale_rng = rng_mgr.get_stream(ModuleId.MORALE)
        movement_rng = rng_mgr.get_stream(ModuleId.MOVEMENT)
        c2_rng = rng_mgr.get_stream(ModuleId.C2)
        logistics_rng = rng_mgr.get_stream(ModuleId.LOGISTICS)

        # Combat stack
        from stochastic_warfare.combat.ballistics import BallisticsEngine
        from stochastic_warfare.combat.hit_probability import HitProbabilityEngine
        from stochastic_warfare.combat.damage import DamageEngine
        from stochastic_warfare.combat.suppression import SuppressionEngine
        from stochastic_warfare.combat.fratricide import FratricideEngine
        from stochastic_warfare.combat.engagement import EngagementEngine

        bal = BallisticsEngine(combat_rng)
        hit_engine = HitProbabilityEngine(bal, combat_rng)
        cal = config.calibration_overrides
        dmg_engine = DamageEngine(
            bus,
            combat_rng,
            posture_blast_overrides=cal.get("posture_blast_protection") if cal else None,
            posture_frag_overrides=cal.get("posture_frag_protection") if cal else None,
        )
        sup_engine = SuppressionEngine(bus, combat_rng)
        frat_engine = FratricideEngine(bus, combat_rng)
        engagement_engine = EngagementEngine(
            hit_engine,
            dmg_engine,
            sup_engine,
            frat_engine,
            bus,
            combat_rng,
        )

        # Missile engine (Phase 63d)
        from stochastic_warfare.combat.missiles import MissileEngine

        missile_engine = MissileEngine(dmg_engine, bus, combat_rng)

        # Missile defense engine (Phase 71c)
        from stochastic_warfare.combat.missile_defense import MissileDefenseEngine

        missile_defense_engine = MissileDefenseEngine(
            event_bus=bus,
            rng=combat_rng,
        )

        # Indirect fire (Phase 43b)
        from stochastic_warfare.combat.indirect_fire import IndirectFireEngine

        indirect_fire_engine = IndirectFireEngine(
            bal,
            dmg_engine,
            bus,
            combat_rng,
            time_on_target_enabled=(config.indirect_fire.enable_time_on_target),
            time_on_target_missions=time_on_target_missions,
            destruction_threshold=cal.get(
                "destruction_threshold",
                0.5,
            ),
            disable_threshold=cal.get(
                "disable_threshold",
                0.3,
            ),
        )

        # Naval engines (Phase 43c)
        from stochastic_warfare.combat.naval_surface import NavalSurfaceEngine
        from stochastic_warfare.combat.naval_subsurface import NavalSubsurfaceEngine
        from stochastic_warfare.combat.naval_gunfire_support import NavalGunfireSupportEngine
        from stochastic_warfare.combat.naval_mine import MineWarfareEngine

        naval_surface_engine = NavalSurfaceEngine(dmg_engine, bus, combat_rng)
        naval_subsurface_engine = NavalSubsurfaceEngine(dmg_engine, bus, combat_rng)
        naval_gunfire_support_engine = NavalGunfireSupportEngine(
            indirect_fire_engine,
            bus,
            combat_rng,
        )
        mine_warfare_engine = MineWarfareEngine(dmg_engine, bus, combat_rng)

        # Air combat engines (Phase 58b) — only when enable_air_routing is set
        air_combat_engine = None
        air_ground_engine = None
        air_defense_engine = None
        if cal and cal.get("enable_air_routing", False):
            from stochastic_warfare.combat.air_combat import AirCombatEngine
            from stochastic_warfare.combat.air_ground import AirGroundEngine
            from stochastic_warfare.combat.air_defense import AirDefenseEngine

            air_combat_engine = AirCombatEngine(bus, combat_rng)
            air_ground_engine = AirGroundEngine(bus, combat_rng)
            air_defense_engine = AirDefenseEngine(bus, combat_rng)

        # Disruption engine (Phase 51d — blockade / interdiction)
        from stochastic_warfare.logistics.disruption import DisruptionEngine

        disruption_engine = DisruptionEngine(bus, logistics_rng)

        # LOS engine (built from heightmap, cached per tick)
        from stochastic_warfare.terrain.los import LOSEngine

        los_engine = LOSEngine(heightmap)

        # Detection
        from stochastic_warfare.detection.detection import DetectionEngine
        from stochastic_warfare.detection.fog_of_war import FogOfWarManager

        det_engine = DetectionEngine(
            los_checker=los_engine.check_los,
            rng=detection_rng,
            signature_loader=loaders["sig_loader"],
            sensor_loader=loaders["sensor_loader"],
        )
        fog_of_war = FogOfWarManager(
            detection_engine=det_engine,
            rng=detection_rng,
        )

        # Morale
        from stochastic_warfare.morale.config import build_morale_config

        cal = config.calibration_overrides
        morale_config = build_morale_config(cal.morale)

        # ROE (Phase 42a)
        from stochastic_warfare.c2.roe import RoeEngine, RoeLevel

        roe_engine = RoeEngine(bus, default_level=RoeLevel.WEAPONS_FREE)

        # Rout (Phase 42c / Phase 55 per-scenario config)
        _rout_cfg_kwargs: dict[str, float] = {}
        for _rout_field in ("cascade_radius_m", "cascade_base_chance", "cascade_shaken_susceptibility"):
            _rout_val = cal.get(f"rout_{_rout_field}")
            if _rout_val is not None:
                _rout_cfg_kwargs[_rout_field] = _rout_val
        rout_engine = RoutEngine(
            bus,
            morale_rng,
            config=RoutConfig(**_rout_cfg_kwargs) if _rout_cfg_kwargs else None,
        )
        morale_runtime = MoraleRuntime(
            bus,
            morale_rng,
            morale_config,
            rout_engine=rout_engine,
        )

        # Movement
        from stochastic_warfare.movement.engine import MovementEngine

        movement_engine = MovementEngine(
            heightmap=heightmap,
            rng=movement_rng,
        )

        # C2
        from stochastic_warfare.c2.communications import CommunicationsEngine
        from stochastic_warfare.c2.orders.propagation import OrderPropagationEngine
        from stochastic_warfare.c2.orders.execution import OrderExecutionEngine

        comms_engine = CommunicationsEngine(bus, c2_rng)

        # Phase 69d: Command hierarchy enforcement
        _command_engine_69d = None
        if cal.get("enable_command_hierarchy", False) and units_by_side:
            from stochastic_warfare.entities.organization.hierarchy import HierarchyTree
            from stochastic_warfare.entities.organization.task_org import TaskOrgManager
            from stochastic_warfare.entities.organization.echelons import EchelonLevel
            from stochastic_warfare.c2.command import CommandEngine, CommandConfig

            _hierarchy = HierarchyTree()
            # Build virtual HQ per side + add each unit as child
            for _side_key, _side_units in units_by_side.items():
                _hq_id = f"{_side_key}_hq"
                _hierarchy.add_unit(_hq_id, EchelonLevel.DIVISION, side=_side_key)
                for _u in _side_units:
                    try:
                        _hierarchy.add_unit(
                            _u.entity_id,
                            EchelonLevel.COMPANY,
                            parent_id=_hq_id,
                            side=_side_key,
                        )
                    except (ValueError, KeyError):
                        pass  # duplicate or missing parent — skip
            _task_org = TaskOrgManager(_hierarchy)
            _command_engine_69d = CommandEngine(
                _hierarchy,
                _task_org,
                {},
                bus,
                c2_rng,
                CommandConfig(),
            )
            logger.info("Command hierarchy built with %d units", sum(len(u) for u in units_by_side.values()))

        order_propagation = OrderPropagationEngine(
            comms_engine=comms_engine,
            command_engine=_command_engine_69d,
            event_bus=bus,
            rng=c2_rng,
        )
        order_execution = OrderExecutionEngine(
            propagation_engine=order_propagation,
            event_bus=bus,
            rng=c2_rng,
        )

        # AI
        from stochastic_warfare.c2.ai.ooda import OODALoopEngine
        from stochastic_warfare.c2.planning.process import PlanningProcessEngine
        from stochastic_warfare.c2.ai.assessment import SituationAssessor
        from stochastic_warfare.c2.ai.decisions import DecisionEngine
        from stochastic_warfare.c2.ai.adaptation import AdaptationEngine

        ooda_engine = OODALoopEngine(bus, c2_rng)
        planning_engine = PlanningProcessEngine(bus, c2_rng)
        assessor = SituationAssessor(bus, c2_rng)
        decision_engine = DecisionEngine(bus, c2_rng)
        adaptation_engine = AdaptationEngine(bus, c2_rng)

        # Phase 53c: Stratagem engine
        from stochastic_warfare.c2.ai.stratagems import StratagemEngine

        stratagem_engine = StratagemEngine(bus, c2_rng)

        # Phase 53d: ATO planning engine
        from stochastic_warfare.c2.orders.air_orders import ATOPlanningEngine

        ato_engine = ATOPlanningEngine(bus)

        # Phase 53e: IADS engine
        from stochastic_warfare.combat.iads import IadsEngine, IadsConfig

        iads_cfg = IadsConfig()
        _cal = config.calibration_overrides
        if _cal is not None:
            _iads_rate = _cal.get("iads_degradation_rate", None) if hasattr(_cal, "get") else None
            if _iads_rate is not None:
                iads_cfg = IadsConfig(sead_degradation_rate=_iads_rate)
            _sead_eff = _cal.get("sead_effectiveness", None) if hasattr(_cal, "get") else None
            if _sead_eff is not None:
                iads_cfg.sead_effectiveness = _sead_eff
            _sead_arm = _cal.get("sead_arm_effectiveness", None) if hasattr(_cal, "get") else None
            if _sead_arm is not None:
                iads_cfg.sead_arm_effectiveness = _sead_arm
        iads_engine = IadsEngine(bus, combat_rng, iads_cfg)

        # Logistics
        from stochastic_warfare.logistics.consumption import ConsumptionEngine
        from stochastic_warfare.logistics.stockpile import StockpileManager
        from stochastic_warfare.logistics.supply_network import SupplyNetworkEngine
        from stochastic_warfare.logistics.maintenance import (
            MaintenanceConfig,
            MaintenanceEngine,
        )

        consumption_engine = ConsumptionEngine(bus, logistics_rng)
        stockpile_manager = StockpileManager(
            bus,
            logistics_rng,
            loader=loaders["supply_item_loader"],
        )
        supply_network_engine = SupplyNetworkEngine(bus, logistics_rng)
        from stochastic_warfare.logistics.runtime import LogisticsRuntime

        logistics_runtime = LogisticsRuntime(
            config=config.logistics,
            stockpile_manager=stockpile_manager,
            supply_network_engine=supply_network_engine,
            supply_item_loader=loaders["supply_item_loader"],
            disruption_engine=disruption_engine,
        )
        logistics_runtime.initialize(
            {side.side: side.depots for side in config.sides},
            [unit for side in sorted(units_by_side or {}) for unit in (units_by_side or {})[side]],
        )
        # Phase 56c: per-subsystem Weibull shapes from calibration
        _cal = config.calibration_overrides
        _weibull = _cal.get("subsystem_weibull_shapes", {}) if hasattr(_cal, "get") else {}
        maintenance_config = era_runtime_contract.maintenance_config()
        if _weibull:
            maintenance_config = MaintenanceConfig.model_validate(
                {
                    **maintenance_config.model_dump(mode="python"),
                    "use_weibull": True,
                },
            )
        maintenance_engine = MaintenanceEngine(
            bus,
            logistics_rng,
            config=maintenance_config,
        )
        if _weibull:
            maintenance_engine.set_subsystem_shapes(_weibull)

        # Aggregation (Phase 13a-7)
        from stochastic_warfare.simulation.aggregation import (
            AggregationConfig,
            AggregationEngine,
        )

        agg_config = AggregationConfig()
        aggregation_engine = AggregationEngine(
            config=agg_config,
            rng=rng_mgr.get_stream(ModuleId.CORE),
            event_bus=bus,
        )

        # Terrain managers (Phase 40g)
        from stochastic_warfare.terrain.obstacles import ObstacleManager
        from stochastic_warfare.terrain.hydrography import HydrographyManager

        obstacle_mgr = ObstacleManager()
        hydro_mgr = HydrographyManager()

        # Phase 44a: Environment engines
        weather_engine = None
        time_of_day_engine = None
        sea_state_engine = None
        seasons_engine = None
        underwater_acoustics_engine = None
        conditions_engine = None

        if clock is not None:
            from stochastic_warfare.environment.weather import (
                WeatherConfig,
                WeatherEngine,
            )
            from stochastic_warfare.environment.astronomy import AstronomyEngine
            from stochastic_warfare.environment.time_of_day import TimeOfDayEngine
            from stochastic_warfare.environment.sea_state import (
                SeaStateConfig,
                SeaStateEngine,
            )

            env_rng = rng_mgr.get_stream(ModuleId.ENVIRONMENT)
            wc = config.weather_conditions
            weather_cfg = WeatherConfig(
                latitude=config.latitude,
                initial_state=_parse_weather_state(
                    wc.get("precipitation", "clear"),
                ),
                initial_temperature=wc.get("temperature_c", 20.0),
            )
            weather_engine = WeatherEngine(weather_cfg, clock, env_rng)
            astronomy_engine = AstronomyEngine(clock)
            time_of_day_engine = TimeOfDayEngine(
                astronomy_engine,
                weather_engine,
                clock,
            )
            sea_state_rng = rng_mgr.get_stream(ModuleId.ENVIRONMENT)
            sea_state_engine = SeaStateEngine(
                SeaStateConfig(),
                clock,
                astronomy_engine,
                weather_engine,
                sea_state_rng,
            )

            # Phase 59: SeasonsEngine instantiation
            from stochastic_warfare.environment.seasons import SeasonsConfig, SeasonsEngine

            seasons_engine = SeasonsEngine(
                SeasonsConfig(latitude=config.latitude),
                clock,
                weather_engine,
                astronomy_engine,
            )

            # Phase 60: ObscurantsEngine instantiation
            from stochastic_warfare.environment.obscurants import ObscurantsEngine

            obs_rng = rng_mgr.get_stream(ModuleId.ENVIRONMENT)
            obscurants_engine = ObscurantsEngine(
                weather_engine,
                time_of_day_engine,
                clock,
                obs_rng,
            )

            # Phase 61: UnderwaterAcousticsEngine instantiation
            from stochastic_warfare.environment.underwater_acoustics import UnderwaterAcousticsEngine

            ua_rng = rng_mgr.get_stream(ModuleId.ENVIRONMENT)
            underwater_acoustics_engine = UnderwaterAcousticsEngine(
                sea_state_engine,
                clock,
                ua_rng,
            )

            # Phase 61: EMEnvironment instantiation (conditions_engine)
            from stochastic_warfare.environment.electromagnetic import EMEnvironment

            conditions_engine = EMEnvironment(
                weather_engine,
                sea_state_engine,
                clock,
            )

            # Phase 66b: ConditionsEngine facade — composites all env sub-engines
            from stochastic_warfare.environment.conditions import ConditionsEngine as _CondFacade

            conditions_facade = _CondFacade(
                weather=weather_engine,
                time_of_day=time_of_day_engine,
                seasons=seasons_engine,
                obscurants=obscurants_engine,
                sea_state=sea_state_engine,
                acoustics=underwater_acoustics_engine,
                em=conditions_engine,
            )

            # Merge weather visibility into calibration if not already set
            cal = config.calibration_overrides
            if "visibility_m" in wc:
                from stochastic_warfare.simulation.calibration import CalibrationSchema

                if isinstance(cal, CalibrationSchema):
                    if cal.visibility_m is None:
                        cal.visibility_m = wc["visibility_m"]
                elif "visibility_m" not in cal:
                    cal["visibility_m"] = wc["visibility_m"]

        # Phase 44c / 56c: Medical & engineering engines (era-aware)
        from stochastic_warfare.logistics.medical import MedicalEngine
        from stochastic_warfare.logistics.engineering import (
            EngineeringConfig,
            EngineeringEngine,
        )

        medical_engine = MedicalEngine(
            bus,
            logistics_rng,
            config=era_runtime_contract.medical_config(),
        )
        engineering_engine = EngineeringEngine(
            bus,
            logistics_rng,
            config=EngineeringConfig(),
        )

        # Phase 61: CarrierOpsEngine instantiation
        from stochastic_warfare.combat.carrier_ops import CarrierOpsEngine

        carrier_ops_rng = rng_mgr.get_stream(ModuleId.COMBAT)
        carrier_ops_engine = CarrierOpsEngine(
            event_bus=bus,
            rng=carrier_ops_rng,
        )

        # Phase 61c: wire EM environment to comms engine
        if conditions_engine is not None:
            comms_engine.set_em_environment(conditions_engine)

        result = {
            "los_engine": los_engine,
            "engagement_engine": engagement_engine,
            "missile_engine": missile_engine,
            "missile_defense_engine": missile_defense_engine,
            "detection_engine": det_engine,
            "fog_of_war": fog_of_war,
            "morale_runtime": morale_runtime,
            "roe_engine": roe_engine,
            "rout_engine": rout_engine,
            "movement_engine": movement_engine,
            "comms_engine": comms_engine,
            "order_propagation": order_propagation,
            "order_execution": order_execution,
            "ooda_engine": ooda_engine,
            "planning_engine": planning_engine,
            "assessor": assessor,
            "decision_engine": decision_engine,
            "adaptation_engine": adaptation_engine,
            "consumption_engine": consumption_engine,
            "stockpile_manager": stockpile_manager,
            "supply_network_engine": supply_network_engine,
            "logistics_runtime": logistics_runtime,
            "maintenance_engine": maintenance_engine,
            "aggregation_engine": aggregation_engine,
            "suppression_engine": sup_engine,
            "indirect_fire_engine": indirect_fire_engine,
            "naval_surface_engine": naval_surface_engine,
            "naval_subsurface_engine": naval_subsurface_engine,
            "naval_gunfire_support_engine": naval_gunfire_support_engine,
            "mine_warfare_engine": mine_warfare_engine,
            "air_combat_engine": air_combat_engine,
            "air_ground_engine": air_ground_engine,
            "air_defense_engine": air_defense_engine,
            "disruption_engine": disruption_engine,
            "obstacle_manager": obstacle_mgr,
            "hydrography_manager": hydro_mgr,
            "weather_engine": weather_engine,
            "time_of_day_engine": time_of_day_engine,
            "sea_state_engine": sea_state_engine,
            "seasons_engine": seasons_engine,
            "obscurants_engine": obscurants_engine,
            "underwater_acoustics_engine": underwater_acoustics_engine,
            "conditions_engine": conditions_engine,
            "conditions_facade": locals().get("conditions_facade"),
            "carrier_ops_engine": carrier_ops_engine,
            "medical_engine": medical_engine,
            "engineering_engine": engineering_engine,
            "stratagem_engine": stratagem_engine,
            "ato_engine": ato_engine,
            "iads_engine": iads_engine,
            "command_engine": _command_engine_69d,
        }

        # ── Optional engine wiring (Phase 25) ────────────────────────
        result.update(
            self._create_optional_engines(
                rng_mgr,
                bus,
                config,
                c2_rng,
                era_config,
                clock,
                doctrine_side_assignments=doctrine_side_assignments,
            ),
        )
        return result

    def _create_optional_engines(
        self,
        rng_mgr: RNGManager,
        bus: EventBus,
        config: CampaignScenarioConfig,
        c2_rng: np.random.Generator,
        era_config: EraConfig,
        clock: SimulationClock | None = None,
        *,
        doctrine_side_assignments: tuple[
            DoctrineSideAssignment,
            ...,
        ] = (),
    ) -> dict[str, Any]:
        """Create optional domain engines from explicit flags and era gates."""
        disabled = set(era_config.disabled_modules)
        result: dict[str, Any] = {}

        # 1. EW engines
        ew_enabled = self._optional_suite_enabled(
            config.ew_config,
            enable_field="enable_ew",
            config_field="ew_config",
        )
        if ew_enabled and "ew" in disabled:
            raise ScenarioReferenceError(
                "Era feature 'ew' is disabled but ew_config.enable_ew is true",
            )
        if ew_enabled:
            result.update(self._create_ew_engines(rng_mgr, bus, config.ew_config))

        # 2. Space engines
        space_enabled = config.space_config is not None and config.space_config.enable_space
        if space_enabled and "space" in disabled:
            raise ScenarioReferenceError(
                "Era feature 'space' is disabled but space_config.enable_space is true",
            )
        if space_enabled:
            result.update(
                self._create_space_engines(
                    rng_mgr,
                    bus,
                    config,
                    gps_enabled="gps" not in disabled,
                    clock=clock,
                ),
            )

        # 3. CBRN engines
        cbrn_enabled = self._optional_suite_enabled(
            config.cbrn_config,
            enable_field="enable_cbrn",
            config_field="cbrn_config",
        )
        if cbrn_enabled and "cbrn" in disabled:
            raise ScenarioReferenceError(
                "Era feature 'cbrn' is disabled but cbrn_config.enable_cbrn is true",
            )
        if cbrn_enabled:
            result.update(self._create_cbrn_engines(rng_mgr, bus, config))

        # 4. Schools
        if config.school_config is not None or doctrine_side_assignments:
            school_config = config.school_config.model_dump(mode="python") if config.school_config is not None else {}
            # Exact per-unit assignments are committed with profile-derived
            # and analysis assignments in one precedence-ordered plan.
            school_config["unit_assignments"] = {}
            result.update(self._create_school_engines(school_config))

        # 5. Commander
        # Production commander construction is preflighted in ``load()``
        # before the first ENTITIES draw and injected into the engine map
        # after this optional-suite factory returns.

        # 6. Escalation
        if config.escalation_config is not None:
            result.update(self._create_escalation_engines(rng_mgr, bus, config.escalation_config))

            # Phase 44d: Population engines for escalation scenarios
            from stochastic_warfare.population.civilians import CivilianManager
            from stochastic_warfare.population.collateral import CollateralEngine

            pop_rng = rng_mgr.get_stream(ModuleId.POPULATION)
            result["population_manager"] = CivilianManager(bus, pop_rng)
            result["collateral_engine"] = CollateralEngine(bus)
        else:
            # Phase 101 — unconventional_engine is needed for initial_ieds /
            # urban scenarios even without a full escalation_config.  Lightweight
            # engines (bus + rng only) so zero cost when unused.
            if config.initial_ieds:
                from stochastic_warfare.combat.unconventional import (
                    UnconventionalWarfareEngine,
                )
                from stochastic_warfare.combat.damage import IncendiaryDamageEngine

                combat_rng = rng_mgr.get_stream(ModuleId.COMBAT)
                result["unconventional_engine"] = UnconventionalWarfareEngine(
                    bus,
                    combat_rng,
                )
                if "incendiary_engine" not in result:
                    result["incendiary_engine"] = IncendiaryDamageEngine(combat_rng)

        # 7. Era engines
        if era_config.era.value != "modern":
            result.update(
                self._create_era_engines(rng_mgr, bus, era_config),
            )

        # 8. DEW engines
        if config.dew_config is not None:
            result.update(self._create_dew_engine(rng_mgr, bus, config.dew_config))

        return result

    @staticmethod
    def _optional_suite_enabled(
        config_block: dict[str, Any] | None,
        *,
        enable_field: str,
        config_field: str,
    ) -> bool:
        """Return an optional suite's explicit, validated enable flag."""
        if config_block is None:
            return False
        enabled = config_block.get(enable_field, False)
        if not isinstance(enabled, bool):
            raise ValueError(
                f"{config_field}.{enable_field} must be a boolean",
            )
        return enabled

    def _create_ew_engines(
        self,
        rng_mgr: RNGManager,
        bus: EventBus,
        ew_cfg: dict[str, Any],
    ) -> dict[str, Any]:
        """Create EW sub-engines from ew_config."""
        ew_rng = rng_mgr.get_stream(ModuleId.EW)

        from stochastic_warfare.ew.jamming import JammingConfig, JammingEngine
        from stochastic_warfare.ew.eccm import ECCMEngine
        from stochastic_warfare.ew.sigint import SIGINTEngine
        from stochastic_warfare.ew.decoys_ew import EWDecoyEngine

        jam_config = JammingConfig.model_validate(ew_cfg)
        ew_engine = JammingEngine(bus, ew_rng, jam_config)
        eccm_engine = ECCMEngine(bus)
        sigint_engine = SIGINTEngine(bus, ew_rng)
        ew_decoy_engine = EWDecoyEngine(bus, ew_rng)

        # Phase 65b: Load SIGINT collectors from scenario ew_config
        from stochastic_warfare.ew.sigint import SIGINTCollector

        for side_key in ("blue_sigint_collectors", "red_sigint_collectors"):
            for coll_data in ew_cfg.get(side_key, []):
                side = "blue" if "blue" in side_key else "red"
                collector = SIGINTCollector(
                    collector_id=coll_data["collector_id"],
                    unit_id=coll_data.get("unit_id", coll_data["collector_id"]),
                    position=Position(0.0, 0.0, 0.0),
                    receiver_sensitivity_dbm=coll_data["receiver_sensitivity_dbm"],
                    frequency_range_ghz=tuple(coll_data["frequency_range_ghz"]),
                    bandwidth_ghz=coll_data["bandwidth_ghz"],
                    df_accuracy_deg=coll_data["df_accuracy_deg"],
                    has_tdoa=coll_data.get("has_tdoa", False),
                    side=side,
                    aperture_m=coll_data.get("aperture_m", 1.0),
                )
                sigint_engine.register_collector(collector)

        # Phase 65c: Load ECCM suites from scenario ew_config
        from stochastic_warfare.ew.eccm import ECCMSuite, ECCMTechnique

        for side_key in ("blue_eccm_suites", "red_eccm_suites"):
            for suite_data in ew_cfg.get(side_key, []):
                suite = ECCMSuite(
                    suite_id=suite_data["suite_id"],
                    unit_id=suite_data.get("unit_id", suite_data["suite_id"]),
                    techniques=[ECCMTechnique(t) for t in suite_data.get("techniques", [])],
                    hop_bandwidth_ghz=suite_data.get("hop_bandwidth_ghz", 0.0),
                    hop_rate_hz=suite_data.get("hop_rate_hz", 0.0),
                    spread_bandwidth_ghz=suite_data.get("spread_bandwidth_ghz", 0.0),
                    signal_bandwidth_ghz=suite_data.get("signal_bandwidth_ghz", 0.001),
                    processing_gain_db=suite_data.get("processing_gain_db", 0.0),
                    sidelobe_ratio_db=suite_data.get("sidelobe_ratio_db", 25.0),
                    null_depth_db=suite_data.get("null_depth_db", 30.0),
                    num_elements=suite_data.get("num_elements", 1),
                    max_nulls=suite_data.get("max_nulls", 1),
                )
                eccm_engine.register_suite(suite)

        logger.info("Created EW engines (jamming, ECCM, SIGINT, decoys)")
        return {
            "ew_engine": ew_engine,
            "eccm_engine": eccm_engine,
            "sigint_engine": sigint_engine,
            "ew_decoy_engine": ew_decoy_engine,
        }

    def _create_space_engines(
        self,
        rng_mgr: RNGManager,
        bus: EventBus,
        config: CampaignScenarioConfig,
        *,
        gps_enabled: bool = True,
        clock: SimulationClock | None = None,
    ) -> dict[str, Any]:
        """Strictly resolve catalogs and create the space-domain runtime."""
        if config.space_config is None:
            raise ValueError(
                "Cannot create space engines without space_config",
            )
        space_rng = rng_mgr.get_stream(ModuleId.SPACE)

        from stochastic_warfare.space.constellations import (
            ConstellationManager,
            SpaceEngine,
        )
        from stochastic_warfare.space.catalog import SpaceCatalog
        from stochastic_warfare.space.orbits import OrbitalMechanicsEngine
        from stochastic_warfare.space.gps import GPSEngine
        from stochastic_warfare.space.isr import SpaceISREngine
        from stochastic_warfare.space.early_warning import EarlyWarningEngine
        from stochastic_warfare.space.satcom import SATCOMEngine
        from stochastic_warfare.space.asat import ASATEngine

        sc = config.space_config
        catalog = SpaceCatalog.load(self._data_dir)
        resolved = catalog.resolve(
            sc,
            scenario_sides={side.side for side in config.sides},
        )
        orbits = OrbitalMechanicsEngine()
        constellation = ConstellationManager(orbits, bus, space_rng, sc)
        for definition in resolved.constellations:
            constellation.add_constellation(definition)

        gps = GPSEngine(constellation, sc, bus, space_rng, clock=clock) if gps_enabled else None
        isr = SpaceISREngine(
            constellation,
            sc,
            bus,
            space_rng,
            clock=clock,
            scenario_sides=tuple(side.side for side in config.sides),
        )
        ew_sat = EarlyWarningEngine(
            constellation,
            sc,
            bus,
            space_rng,
            clock=clock,
        )
        satcom = SATCOMEngine(
            constellation,
            sc,
            bus,
            space_rng,
            clock=clock,
        )
        asat = ASATEngine(
            constellation,
            sc,
            bus,
            space_rng,
            clock=clock,
            weapon_definitions=resolved.weapon_definitions,
            assets=resolved.assets,
            orders=resolved.orders,
            configuration_fingerprint=resolved.fingerprint,
        )

        space_engine = SpaceEngine(
            config=sc,
            constellation_manager=constellation,
            gps_engine=gps,
            isr_engine=isr,
            early_warning_engine=ew_sat,
            satcom_engine=satcom,
            asat_engine=asat,
            catalog_fingerprint=resolved.fingerprint,
        )

        logger.info(
            "Created space engines (%sGPS, ISR, EW, SATCOM, ASAT): "
            "%d constellations, %d satellites, %d ASAT assets, %d orders",
            "" if gps_enabled else "no ",
            len(resolved.constellations),
            len(constellation.all_satellites()),
            len(resolved.assets),
            len(resolved.orders),
        )
        return {"space_engine": space_engine}

    def _create_cbrn_engines(
        self,
        rng_mgr: RNGManager,
        bus: EventBus,
        config: CampaignScenarioConfig,
    ) -> dict[str, Any]:
        """Create CBRN engines from cbrn_config."""
        cbrn_rng = rng_mgr.get_stream(ModuleId.CBRN)
        cbrn_cfg = config.cbrn_config

        from stochastic_warfare.cbrn.agents import AgentRegistry
        from stochastic_warfare.cbrn.dispersal import DispersalEngine
        from stochastic_warfare.cbrn.contamination import ContaminationManager
        from stochastic_warfare.cbrn.protection import ProtectionEngine
        from stochastic_warfare.cbrn.casualties import CBRNCasualtyEngine
        from stochastic_warfare.cbrn.decontamination import DecontaminationEngine
        from stochastic_warfare.cbrn.nuclear import NuclearEffectsEngine
        from stochastic_warfare.cbrn.engine import CBRNConfig, CBRNEngine

        agent_registry = AgentRegistry()
        dispersal = DispersalEngine()

        # Grid from terrain config
        rows = max(1, int(config.terrain.height_m / config.terrain.cell_size_m))
        cols = max(1, int(config.terrain.width_m / config.terrain.cell_size_m))
        contamination = ContaminationManager(
            grid_shape=(rows, cols),
            cell_size_m=config.terrain.cell_size_m,
            origin_easting=0.0,
            origin_northing=0.0,
            event_bus=bus,
            rng=cbrn_rng,
        )
        protection = ProtectionEngine()
        casualty = CBRNCasualtyEngine(bus, cbrn_rng)
        decon = DecontaminationEngine(bus, cbrn_rng)
        nuclear = NuclearEffectsEngine(bus, cbrn_rng, dispersal)

        cbrn_config_obj = CBRNConfig.model_validate(cbrn_cfg)
        cbrn_engine = CBRNEngine(
            config=cbrn_config_obj,
            event_bus=bus,
            rng=cbrn_rng,
            agent_registry=agent_registry,
            dispersal_engine=dispersal,
            contamination_manager=contamination,
            protection_engine=protection,
            casualty_engine=casualty,
            decon_engine=decon,
            nuclear_engine=nuclear,
        )

        logger.info("Created CBRN engines")
        return {"cbrn_engine": cbrn_engine}

    def _create_school_engines(
        self,
        school_cfg: dict[str, Any],
    ) -> dict[str, Any]:
        """Create doctrinal school registry from school_config."""
        from stochastic_warfare.c2.ai.schools import (
            SchoolLoader,
            SchoolRegistry,
            create_school,
        )

        loader = SchoolLoader(self._data_dir / "schools")
        definitions = loader.load_all()

        registry = SchoolRegistry()
        for defn in definitions:
            school = create_school(defn)
            registry.register(school)

        # Apply unit assignments
        unit_assignments = school_cfg.get("unit_assignments", {})
        for unit_id, school_id in unit_assignments.items():
            registry.assign_to_unit(unit_id, school_id)

        logger.info(
            "Created school registry with %d schools, %d assignments",
            len(definitions),
            len(unit_assignments),
        )
        return {"school_registry": registry}

    def _create_commander_engine(
        self,
        c2_rng: np.random.Generator,
        commander_cfg: CommanderScenarioConfig | Mapping[str, Any],
        *,
        era: str = "modern",
    ) -> dict[str, Any]:
        """Create an isolated commander engine for focused consumers."""
        loader = CommanderProfileLoader(self._data_dir / "commander_profiles")
        catalogs = [self._data_dir / "commander_profiles"]
        if era != "modern":
            catalogs.append(
                self._data_dir / "eras" / era / "commanders",
            )
        loader.load_directories(catalogs)
        config = (
            commander_cfg
            if isinstance(commander_cfg, CommanderScenarioConfig)
            else CommanderScenarioConfig.model_validate(commander_cfg)
        )
        engine = CommanderEngine(loader, c2_rng, config.engine_config())

        logger.info("Created commander engine")
        return {"commander_engine": engine}

    def _create_escalation_engines(
        self,
        rng_mgr: RNGManager,
        bus: EventBus,
        esc_cfg: dict[str, Any],
    ) -> dict[str, Any]:
        """Create escalation and unconventional warfare engines."""
        esc_rng = rng_mgr.get_stream(ModuleId.ESCALATION)
        combat_rng = rng_mgr.get_stream(ModuleId.COMBAT)

        from stochastic_warfare.escalation.ladder import EscalationLadder
        from stochastic_warfare.escalation.political import PoliticalPressureEngine
        from stochastic_warfare.escalation.consequences import ConsequenceEngine
        from stochastic_warfare.escalation.war_termination import WarTerminationEngine
        from stochastic_warfare.combat.unconventional import UnconventionalWarfareEngine
        from stochastic_warfare.c2.ai.sof_ops import SOFOpsEngine
        from stochastic_warfare.population.insurgency import InsurgencyEngine
        from stochastic_warfare.combat.damage import IncendiaryDamageEngine, UXOEngine

        escalation_engine = EscalationLadder(bus, esc_rng)
        political_engine = PoliticalPressureEngine(bus)
        consequence_engine = ConsequenceEngine(bus, esc_rng)
        war_termination_engine = WarTerminationEngine(bus)
        unconventional_engine = UnconventionalWarfareEngine(bus, combat_rng)
        sof_engine = SOFOpsEngine(bus, combat_rng)
        insurgency_engine = InsurgencyEngine(bus, esc_rng)
        incendiary_engine = IncendiaryDamageEngine(combat_rng)
        uxo_engine = UXOEngine(combat_rng)

        logger.info("Created escalation and unconventional engines")
        return {
            "escalation_engine": escalation_engine,
            "political_engine": political_engine,
            "consequence_engine": consequence_engine,
            "war_termination_engine": war_termination_engine,
            "unconventional_engine": unconventional_engine,
            "sof_engine": sof_engine,
            "insurgency_engine": insurgency_engine,
            "incendiary_engine": incendiary_engine,
            "uxo_engine": uxo_engine,
        }

    def _create_era_engines(
        self,
        rng_mgr: RNGManager,
        bus: EventBus,
        era_config: EraConfig,
    ) -> dict[str, Any]:
        """Create era-specific engines from the captured typed era."""
        era = era_config.era.value
        result: dict[str, Any] = {}
        combat_rng = rng_mgr.get_stream(ModuleId.COMBAT)
        movement_rng = rng_mgr.get_stream(ModuleId.MOVEMENT)
        c2_rng = rng_mgr.get_stream(ModuleId.C2)
        logistics_rng = rng_mgr.get_stream(ModuleId.LOGISTICS)

        if era == "ww2":
            from stochastic_warfare.combat.naval_gunnery import NavalGunneryEngine
            from stochastic_warfare.movement.convoy import ConvoyEngine
            from stochastic_warfare.combat.strategic_bombing import StrategicBombingEngine

            result["naval_gunnery_engine"] = NavalGunneryEngine(rng=combat_rng)
            result["convoy_engine"] = ConvoyEngine(rng=movement_rng)
            result["strategic_bombing_engine"] = StrategicBombingEngine(rng=combat_rng)
            logger.info("Created WW2 era engines")

        elif era == "ww1":
            from stochastic_warfare.terrain.trenches import TrenchSystemEngine
            from stochastic_warfare.combat.barrage import BarrageEngine
            from stochastic_warfare.combat.gas_warfare import GasWarfareEngine
            from stochastic_warfare.combat.volley_fire import VolleyFireEngine
            from stochastic_warfare.combat.melee import MeleeEngine

            result["trench_engine"] = TrenchSystemEngine()
            result["barrage_engine"] = BarrageEngine(rng=combat_rng)
            result["gas_warfare_engine"] = GasWarfareEngine(rng=combat_rng)
            result["volley_fire_engine"] = VolleyFireEngine(rng=combat_rng)
            result["melee_engine"] = MeleeEngine(rng=combat_rng)
            logger.info("Created WW1 era engines")

        elif era == "napoleonic":
            from stochastic_warfare.combat.volley_fire import VolleyFireEngine
            from stochastic_warfare.combat.melee import MeleeEngine
            from stochastic_warfare.movement.cavalry import CavalryEngine
            from stochastic_warfare.movement.formation_napoleonic import NapoleonicFormationEngine
            from stochastic_warfare.c2.courier import CourierEngine
            from stochastic_warfare.logistics.foraging import ForagingEngine

            result["volley_fire_engine"] = VolleyFireEngine(rng=combat_rng)
            result["melee_engine"] = MeleeEngine(rng=combat_rng)
            result["cavalry_engine"] = CavalryEngine(rng=movement_rng)
            result["formation_napoleonic_engine"] = NapoleonicFormationEngine()
            result["courier_engine"] = CourierEngine(rng=c2_rng)
            result["foraging_engine"] = ForagingEngine(rng=logistics_rng)
            logger.info("Created Napoleonic era engines")

        elif era == "ancient_medieval":
            from stochastic_warfare.combat.archery import ArcheryEngine
            from stochastic_warfare.combat.melee import MeleeEngine
            from stochastic_warfare.combat.siege import SiegeEngine
            from stochastic_warfare.movement.formation_ancient import AncientFormationEngine
            from stochastic_warfare.movement.naval_oar import NavalOarEngine
            from stochastic_warfare.c2.visual_signals import VisualSignalEngine

            result["archery_engine"] = ArcheryEngine(rng=combat_rng)
            result["melee_engine"] = MeleeEngine(rng=combat_rng)
            result["siege_engine"] = SiegeEngine(rng=combat_rng)
            result["formation_ancient_engine"] = AncientFormationEngine()
            result["naval_oar_engine"] = NavalOarEngine(rng=movement_rng)
            result["visual_signals_engine"] = VisualSignalEngine(rng=c2_rng)
            logger.info("Created Ancient/Medieval era engines")

        return result

    def _create_dew_engine(
        self,
        rng_mgr: RNGManager,
        bus: EventBus,
        dew_cfg: dict[str, Any],
    ) -> dict[str, Any]:
        """Create directed energy weapon engine from dew_config."""
        combat_rng = rng_mgr.get_stream(ModuleId.COMBAT)

        from stochastic_warfare.combat.directed_energy import DEWConfig, DEWEngine

        config = DEWConfig.model_validate(dew_cfg)
        dew_engine = DEWEngine(bus, combat_rng, config)

        logger.info("Created DEW engine")
        return {"dew_engine": dew_engine}
