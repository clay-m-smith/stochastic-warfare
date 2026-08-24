"""Lightweight orchestrator for engagement validation scenarios.

Wires existing simulation engines (detection, combat, morale) and runs
a tick loop against a :class:`HistoricalEngagement` definition.  Units
follow pre-scripted behavioral rules rather than AI-driven planning.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.combat.ammunition import AmmoLoader, WeaponLoader
from stochastic_warfare.combat.ballistics import BallisticsEngine
from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.engagement import EngagementEngine
from stochastic_warfare.combat.fratricide import FratricideEngine
from stochastic_warfare.combat.hit_probability import HitProbabilityEngine
from stochastic_warfare.combat.suppression import SuppressionEngine
from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.era import get_era_config
from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.detection.detection import DetectionEngine
from stochastic_warfare.detection.sensors import SensorLoader, SensorType
from stochastic_warfare.detection.signatures import SignatureLoader
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.entities.loader import UnitLoader
from stochastic_warfare.morale.config import build_morale_config
from stochastic_warfare.morale.runtime import MoraleRegistration, MoraleRuntime
from stochastic_warfare.morale.state import MoraleState
from stochastic_warfare.simulation.equipment_mappings import (
    EQUIPMENT_MAPPING_REGISTRY,
)
from stochastic_warfare.simulation.loadouts import (
    RuntimeLoadoutBuilder,
    WeaponAttachment,
)
from stochastic_warfare.terrain.procedural import build_terrain
from stochastic_warfare.legacy.validation.historical_data import (
    ForceDefinition,
    HistoricalEngagement,
)
from stochastic_warfare.validation.metrics import (
    SimulationResult,
    UnitFinalState,
)

logger = get_logger(__name__)

# Sensor types that bypass visual weather degradation (fog, sandstorm, etc.)
_WEATHER_BYPASS_TYPES: frozenset[SensorType] = frozenset({
    SensorType.THERMAL,
    SensorType.RADAR,
    SensorType.ESM,
})


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class ScenarioRunnerConfig(BaseModel):
    """Tunable parameters for the scenario runner."""

    master_seed: int = 42
    max_ticks: int = 10000  # safety limit
    data_dir: str = "data"  # root data directory


# ---------------------------------------------------------------------------
# Termination conditions
# ---------------------------------------------------------------------------


class TerminationCondition(Protocol):
    """Protocol for checking whether a scenario should end."""

    def check(
        self,
        clock: SimulationClock,
        units_by_side: dict[str, list[Unit]],
        event_log: list[Event],
    ) -> tuple[bool, str]: ...


class TimeLimitTermination:
    """Terminate after a fixed duration."""

    def __init__(self, max_duration_s: float) -> None:
        self._max = max_duration_s

    def check(
        self,
        clock: SimulationClock,
        units_by_side: dict[str, list[Unit]],
        event_log: list[Event],
    ) -> tuple[bool, str]:
        if clock.elapsed.total_seconds() >= self._max:
            return True, "time_limit"
        return False, ""


class ForceDestroyedTermination:
    """Terminate when a side loses a threshold fraction of units."""

    def __init__(self, threshold: float = 0.7) -> None:
        self._threshold = threshold

    def check(
        self,
        clock: SimulationClock,
        units_by_side: dict[str, list[Unit]],
        event_log: list[Event],
    ) -> tuple[bool, str]:
        for side, units in units_by_side.items():
            if not units:
                continue
            destroyed = sum(
                1 for u in units if u.status in (UnitStatus.DESTROYED, UnitStatus.SURRENDERED)
            )
            if destroyed / len(units) >= self._threshold:
                return True, f"force_destroyed_{side}"
        return False, ""


class MoraleCollapseTermination:
    """Terminate when a side's morale collectively collapses."""

    def __init__(self, threshold: float = 0.6) -> None:
        self._threshold = threshold

    def check(
        self,
        clock: SimulationClock,
        units_by_side: dict[str, list[Unit]],
        event_log: list[Event],
    ) -> tuple[bool, str]:
        for side, units in units_by_side.items():
            if not units:
                continue
            routed = sum(
                1
                for u in units
                if u.status in (UnitStatus.ROUTING, UnitStatus.SURRENDERED)
            )
            if routed / len(units) >= self._threshold:
                return True, f"morale_collapse_{side}"
        return False, ""


# ---------------------------------------------------------------------------
# Force builder
# ---------------------------------------------------------------------------


def build_forces(
    force_def: ForceDefinition,
    unit_loader: UnitLoader,
    rng: np.random.Generator,
    start_x: float = 0.0,
    start_y: float = 0.0,
    spacing_m: float = 50.0,
) -> list[Unit]:
    """Consume the typed production force-construction boundary."""
    from stochastic_warfare.simulation.force_builder import (
        InitialForcePlan,
        InitialUnitConfig,
        RuntimeForceBuilder,
    )

    plan = InitialForcePlan(
        side=force_def.side,
        units=tuple(
            InitialUnitConfig.model_validate(entry)
            for entry in force_def.units
        ),
        start_easting=start_x,
        start_northing=start_y,
        spacing_m=spacing_m,
    )
    return RuntimeForceBuilder(
        unit_loader=unit_loader,
        rng=rng,
    ).build_initial((plan,))[force_def.side]


# ---------------------------------------------------------------------------
# Behavior engine (pre-scripted)
# ---------------------------------------------------------------------------


def apply_behavior(
    units: list[Unit],
    behavior_rules: dict[str, Any],
    side: str,
    enemy_units: list[Unit],
    dt: float,
) -> None:
    """Apply pre-scripted movement and targeting behavior.

    Supported behavior rule keys:
    - ``advance_speed_mps``: Units advance toward enemy centroid at this speed
    - ``hold_position``: If true, units do not move
    - ``engagement_range_m``: Max range at which units try to engage
    """
    rules = behavior_rules.get(side, {})

    if rules.get("hold_position", False):
        for u in units:
            if u.status == UnitStatus.ACTIVE:
                object.__setattr__(u, "speed", 0.0)
        return

    advance_speed = rules.get("advance_speed_mps", 0.0)
    if advance_speed <= 0 or not enemy_units:
        return

    # Compute enemy centroid (caller provides pre-filtered active enemies)
    cx = sum(e.position.easting for e in enemy_units) / len(enemy_units)
    cy = sum(e.position.northing for e in enemy_units) / len(enemy_units)

    for u in units:
        if u.status != UnitStatus.ACTIVE:
            continue
        dx = cx - u.position.easting
        dy = cy - u.position.northing
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 1.0:
            continue

        move_dist = min(advance_speed * dt, dist)
        nx = u.position.easting + (dx / dist) * move_dist
        ny = u.position.northing + (dy / dist) * move_dist

        object.__setattr__(u, "position", Position(nx, ny, u.position.altitude))
        object.__setattr__(u, "speed", advance_speed)
        heading = math.atan2(dx, dy)  # bearing from north
        object.__setattr__(u, "heading", heading)


# ---------------------------------------------------------------------------
# Scenario Runner
# ---------------------------------------------------------------------------


class ScenarioRunner:
    """Execute a historical engagement scenario and return metrics.

    Parameters
    ----------
    config:
        Runner configuration.
    data_dir:
        Root data directory (defaults to ``config.data_dir``).
    """

    def __init__(
        self,
        config: ScenarioRunnerConfig | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self._config = config or ScenarioRunnerConfig()
        self._data_dir = data_dir or Path(self._config.data_dir)

    def run(
        self,
        engagement: HistoricalEngagement,
        seed: int | None = None,
        termination_conditions: list[TerminationCondition] | None = None,
    ) -> SimulationResult:
        """Run one iteration of a scenario.

        Parameters
        ----------
        engagement:
            The historical engagement definition.
        seed:
            Master PRNG seed (overrides config).
        termination_conditions:
            Custom termination conditions (defaults to time limit + force destroyed).
        """
        master_seed = seed if seed is not None else self._config.master_seed

        # 1. Infrastructure
        rng_mgr = RNGManager(master_seed)
        bus = EventBus()
        event_log: list[Event] = []
        bus.subscribe(Event, lambda e: event_log.append(e))

        dt_s = engagement.tick_duration_seconds
        start_dt = _parse_start_time(engagement.date)
        clock = SimulationClock(
            start=start_dt,
            tick_duration=timedelta(seconds=dt_s),
        )

        # 2. Terrain
        terrain_rng = rng_mgr.get_stream(ModuleId.TERRAIN)
        build_terrain(engagement.terrain, terrain_rng)

        # 3. Load data
        unit_loader = UnitLoader(self._data_dir / "units")
        unit_loader.load_all()

        weapon_loader = WeaponLoader(self._data_dir / "weapons")
        weapon_loader.load_all()

        ammo_loader = AmmoLoader(self._data_dir / "ammunition")
        ammo_loader.load_all()

        sig_loader = SignatureLoader(self._data_dir / "signatures")
        sig_loader.load_all()

        sensor_loader = SensorLoader(self._data_dir / "sensors")
        sensor_loader.load_all()

        calibration = engagement.calibration_overrides
        reachable_unit_types = tuple(
            entry["unit_type"]
            for force in (engagement.blue_forces, engagement.red_forces)
            for entry in force.units
        )
        loadout_builder = RuntimeLoadoutBuilder(
            weapon_loader=weapon_loader,
            ammo_loader=ammo_loader,
            sensor_loader=sensor_loader,
            unit_definitions=unit_loader.definitions(),
            era_config=get_era_config("modern"),
            assignment_overrides=calibration.weapon_assignments,
            reachable_unit_types=reachable_unit_types,
            registry=EQUIPMENT_MAPPING_REGISTRY,
        )

        # 4. Forces and their production loadouts
        entities_rng = rng_mgr.get_stream(ModuleId.ENTITIES)
        blue_start_x = calibration.get("blue_start_x", 100.0)
        blue_start_y = calibration.get(
            "blue_start_y", engagement.terrain.height_m / 2,
        )
        red_start_x = calibration.get(
            "red_start_x", engagement.terrain.width_m - 100.0,
        )
        red_start_y = calibration.get(
            "red_start_y", engagement.terrain.height_m / 2,
        )
        blue_forces = build_forces(
            engagement.blue_forces,
            unit_loader,
            entities_rng,
            start_x=blue_start_x,
            start_y=blue_start_y,
        )
        red_forces = build_forces(
            engagement.red_forces,
            unit_loader,
            entities_rng,
            start_x=red_start_x,
            start_y=red_start_y,
        )
        runtime_loadouts = loadout_builder.build(blue_forces + red_forces)
        unit_weapons = runtime_loadouts.unit_weapons
        unit_sensors = runtime_loadouts.unit_sensors

        units_by_side: dict[str, list[Unit]] = {
            engagement.blue_forces.side: blue_forces,
            engagement.red_forces.side: red_forces,
        }

        # 5. Engine stack
        combat_rng = rng_mgr.get_stream(ModuleId.COMBAT)
        detection_rng = rng_mgr.get_stream(ModuleId.DETECTION)
        morale_rng = rng_mgr.get_stream(ModuleId.MORALE)

        bal = BallisticsEngine(combat_rng)
        hit_engine = HitProbabilityEngine(bal, combat_rng)
        dmg_engine = DamageEngine(bus, combat_rng)
        sup_engine = SuppressionEngine(bus, combat_rng)
        frat_engine = FratricideEngine(bus, combat_rng)
        eng_engine = EngagementEngine(
            hit_engine, dmg_engine, sup_engine, frat_engine, bus, combat_rng
        )

        DetectionEngine(
            rng=detection_rng,
            signature_loader=sig_loader,
            sensor_loader=sensor_loader,
        )

        morale_config = build_morale_config(
            engagement.calibration_overrides.morale,
        )
        morale_runtime = MoraleRuntime(bus, morale_rng, morale_config)
        all_units = blue_forces + red_forces
        morale_runtime.register_units(
            tuple(
                MoraleRegistration(u.entity_id, MoraleState.STEADY)
                for u in all_units
            ),
            {u.entity_id: u for u in all_units},
        )

        # 6. Termination
        if termination_conditions is None:
            max_duration = engagement.duration_hours * 3600.0
            termination_conditions = [
                TimeLimitTermination(max_duration),
                ForceDestroyedTermination(0.7),
                MoraleCollapseTermination(0.6),
            ]

        # Calibration overrides
        cal = calibration
        visibility_m = engagement.weather_conditions.get("visibility_m", 10000.0)
        hit_prob_mod = cal.get("hit_probability_modifier", 1.0)
        target_size_mod = cal.get("target_size_modifier", 1.0)
        morale_degrade_mod = cal.get("morale_degrade_rate_modifier", 1.0)
        blue_force_mod = cal.get("blue_force_ratio_modifier", 1.0)
        red_force_mod = cal.get("red_force_ratio_modifier", 1.0)
        blue_cohesion = cal.get("blue_cohesion", 0.7)
        red_cohesion = cal.get("red_cohesion", 0.7)
        morale_check_interval = int(cal.get("morale_check_interval", 1))
        destruction_threshold = cal.get("destruction_threshold", 0.5)
        disable_threshold = cal.get("disable_threshold", 0.3)

        # 7. Tick loop
        terminated_by = "max_ticks"
        ticks = 0
        for tick_num in range(self._config.max_ticks):
            clock.advance()
            ticks = tick_num + 1

            # Check termination
            done = False
            for cond in termination_conditions:
                should_stop, reason = cond.check(clock, units_by_side, event_log)
                if should_stop:
                    terminated_by = reason
                    done = True
                    break
            if done:
                break

            # Pre-build per-side active enemy lists and position arrays
            # once per tick (avoids O(n²) rebuild inside per-attacker loops)
            active_enemies_by_side: dict[str, list[Unit]] = {}
            enemy_pos_arrays: dict[str, np.ndarray] = {}
            for sn in units_by_side:
                enemies_list = [
                    u
                    for s, us in units_by_side.items()
                    if s != sn
                    for u in us
                    if u.status == UnitStatus.ACTIVE
                ]
                active_enemies_by_side[sn] = enemies_list
                if enemies_list:
                    enemy_pos_arrays[sn] = np.array(
                        [(e.position.easting, e.position.northing) for e in enemies_list],
                        dtype=np.float64,
                    )
                else:
                    enemy_pos_arrays[sn] = np.empty((0, 2), dtype=np.float64)

            # Pre-scripted behavior (movement)
            for side_name, side_units in units_by_side.items():
                apply_behavior(
                    side_units,
                    engagement.behavior_rules,
                    side_name,
                    active_enemies_by_side[side_name],
                    dt_s,
                )

            # Detection + engagement for each active unit.
            # Damage is deferred: both sides fire before any status changes,
            # giving simultaneous resolution within a tick.
            pending_damage: list[tuple[Unit, UnitStatus]] = []

            for side_name, side_units in units_by_side.items():
                enemies = active_enemies_by_side[side_name]
                pos_arr = enemy_pos_arrays[side_name]

                for attacker in side_units:
                    if attacker.status != UnitStatus.ACTIVE:
                        continue

                    weapons = unit_weapons.get(attacker.entity_id, [])
                    if not weapons:
                        continue

                    # Find closest enemy (vectorized distance computation)
                    if pos_arr.shape[0] == 0:
                        continue
                    att_pos = np.array(
                        [attacker.position.easting, attacker.position.northing]
                    )
                    diffs = pos_arr - att_pos
                    dists = np.sqrt(np.sum(diffs * diffs, axis=1))
                    best_idx = int(np.argmin(dists))
                    best_range = float(dists[best_idx])
                    best_target = enemies[best_idx]

                    # Simple detection check: can we see them?
                    detection_range = visibility_m
                    weather_independent = False
                    # Sensors extend detection range beyond weather visibility.
                    # Thermal and radar sensors are not degraded by visual
                    # weather conditions (fog, sandstorm, etc.)
                    sensors = unit_sensors.get(attacker.entity_id, [])
                    for sensor in sensors:
                        if sensor.effective_range > detection_range:
                            detection_range = sensor.effective_range
                            if sensor.sensor_type in _WEATHER_BYPASS_TYPES:
                                weather_independent = True

                    if best_range > detection_range:
                        continue

                    # Compute visibility modifier — thermal/radar sensors see
                    # through obscurants; only visual sensors are degraded
                    if weather_independent:
                        vis_mod = 1.0
                    elif best_range > 0:
                        vis_mod = min(visibility_m / best_range, 1.0)
                    else:
                        vis_mod = 1.0

                    # Engage with longest-range available weapon (ATGMs
                    # before guns at distance, guns before ATGMs close in).
                    # Weapons pre-sorted at setup time.
                    for attachment in weapons:
                        wpn_inst = attachment.weapon
                        ammo_def = attachment.first_fireable_ammunition()
                        if ammo_def is None:
                            continue
                        ammo_id = ammo_def.ammo_id

                        if wpn_inst.definition.max_range_m > 0 and best_range > wpn_inst.definition.max_range_m:
                            continue

                        # Determine target properties
                        target_armor = getattr(best_target, "armor_front", 0.0)
                        target_size = 8.5 * target_size_mod
                        crew_skill = engagement.blue_forces.experience_level if side_name == engagement.blue_forces.side else engagement.red_forces.experience_level
                        crew_count = len(best_target.personnel) if best_target.personnel else 4

                        result = eng_engine.execute_engagement(
                            attacker_id=attacker.entity_id,
                            target_id=best_target.entity_id,
                            shooter_pos=attacker.position,
                            target_pos=best_target.position,
                            weapon=wpn_inst,
                            ammo_id=ammo_id,
                            ammo_def=ammo_def,
                            crew_skill=crew_skill * hit_prob_mod,
                            target_size_m2=target_size,
                            target_armor_mm=target_armor,
                            crew_count=crew_count,
                            visibility=vis_mod,
                            timestamp=clock.current_time,
                        )

                        if result.engaged and result.hit_result and result.hit_result.hit:
                            if result.damage_result and result.damage_result.damage_fraction > 0:
                                if result.damage_result.damage_fraction >= destruction_threshold:
                                    pending_damage.append((best_target, UnitStatus.DESTROYED))
                                elif result.damage_result.damage_fraction >= disable_threshold:
                                    pending_damage.append((best_target, UnitStatus.DISABLED))

                        break  # One engagement per unit per tick

            # Apply deferred damage — worst outcome wins per unit
            applied: dict[str, UnitStatus] = {}
            for target, new_status in pending_damage:
                prev = applied.get(target.entity_id)
                if prev is None or new_status.value > prev.value:
                    applied[target.entity_id] = new_status
            for target, new_status in pending_damage:
                if applied.get(target.entity_id) == new_status:
                    object.__setattr__(target, "status", new_status)
                    applied.pop(target.entity_id, None)

            # Morale updates (only every N ticks to avoid unrealistic cascading)
            if tick_num % morale_check_interval != 0:
                continue  # skip this part of the tick loop; jump to next tick
            sim_timestamp = clock.current_time
            current_time_s = clock.elapsed.total_seconds()
            for side_name, side_units in units_by_side.items():
                total = len(side_units)
                destroyed = sum(
                    1 for u in side_units
                    if u.status in (UnitStatus.DESTROYED, UnitStatus.SURRENDERED)
                )
                casualty_rate = destroyed / total if total > 0 else 0.0

                # Reuse pre-built active enemy lists from earlier in the tick
                enemies = active_enemies_by_side[side_name]
                active_own = sum(1 for u in side_units if u.status == UnitStatus.ACTIVE)
                active_enemy = len(enemies)

                # Apply force ratio modifiers (combat power weighting)
                if side_name == engagement.blue_forces.side:
                    own_mod = blue_force_mod
                    enemy_mod = red_force_mod
                    cohesion = blue_cohesion
                else:
                    own_mod = red_force_mod
                    enemy_mod = blue_force_mod
                    cohesion = red_cohesion

                active_own_eff = active_own * own_mod
                active_enemy_eff = active_enemy * enemy_mod
                force_ratio = (
                    active_own_eff / active_enemy_eff
                    if active_enemy_eff > 0
                    else 10.0
                )

                for u in side_units:
                    if u.status not in (UnitStatus.ACTIVE, UnitStatus.ROUTING):
                        continue

                    morale_runtime.check_transition(
                        unit_id=u.entity_id,
                        casualty_rate=casualty_rate * morale_degrade_mod,
                        suppression_level=0.0,
                        leadership_present=True,
                        cohesion=cohesion,
                        force_ratio=force_ratio,
                        timestamp=sim_timestamp,
                        current_time_s=current_time_s,
                    )

        # 8. Build result
        units_final = self._build_final_states(
            all_units, morale_runtime.states, unit_weapons
        )

        return SimulationResult(
            seed=master_seed,
            ticks_executed=ticks,
            duration_simulated_s=ticks * dt_s,
            units_final=units_final,
            event_log=event_log,
            terminated_by=terminated_by,
        )

    # ── Private helpers ──────────────────────────────────────────────

    @staticmethod
    def _build_final_states(
        units: list[Unit],
        morale_map: Mapping[str, MoraleState],
        weapon_map: Mapping[str, tuple[WeaponAttachment, ...]],
    ) -> list[UnitFinalState]:
        """Convert unit objects to UnitFinalState for metrics."""
        states: list[UnitFinalState] = []
        for u in units:
            pers_initial = len(u.personnel) if u.personnel else 0
            pers_remaining = pers_initial if u.status == UnitStatus.ACTIVE else 0
            equip_total = len(u.equipment) if u.equipment else 0
            equip_destroyed = equip_total if u.status == UnitStatus.DESTROYED else 0

            ammo_exp: dict[str, int] = {}
            for attachment in weapon_map.get(u.entity_id, ()):
                wpn_inst = attachment.weapon
                ammo_exp.update(
                    {
                        aid: wpn_inst.definition.magazine_capacity - wpn_inst.ammo_state.available(aid)
                        for aid in wpn_inst.ammo_state.rounds_by_type
                    }
                )

            states.append(
                UnitFinalState(
                    entity_id=u.entity_id,
                    side=u.side if isinstance(u.side, str) else u.side.value,
                    unit_type=u.unit_type,
                    status=u.status.name,
                    personnel_remaining=pers_remaining,
                    personnel_initial=pers_initial,
                    equipment_destroyed=equip_destroyed,
                    equipment_total=equip_total,
                    morale_state=morale_map.get(u.entity_id, MoraleState.STEADY).name,
                    ammo_expended=ammo_exp,
                )
            )
        return states


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_start_time(date_str: str) -> datetime:
    """Parse an ISO date or datetime string into a UTC datetime."""
    if "T" in date_str:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    # Date only — assume 00:00 UTC
    parts = date_str.split("-")
    return datetime(
        int(parts[0]),
        int(parts[1]),
        int(parts[2]),
        tzinfo=timezone.utc,
    )
