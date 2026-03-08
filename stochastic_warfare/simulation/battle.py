"""Tactical battle manager — detection, engagement, and AI resolution.

Orchestrates the per-tick tactical loop for active engagements.
Evolves Phase 7's ``ScenarioRunner._run_tick()`` with AI commanders
replacing pre-scripted behavior and full C2/logistics integration.
No domain logic lives here — only sequencing and data routing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.combat.ammunition import WeaponCategory
from stochastic_warfare.combat.engagement import EngagementType
from stochastic_warfare.combat.suppression import UnitSuppressionState
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.entities.events import UnitDestroyedEvent, UnitDisabledEvent
from stochastic_warfare.detection.sensors import SensorType
from stochastic_warfare.morale.state import MoraleState, _MORALE_EFFECTS

logger = get_logger(__name__)

# Sensor types that bypass visual weather degradation
_WEATHER_BYPASS_TYPES: frozenset[SensorType] = frozenset({
    SensorType.THERMAL,
    SensorType.RADAR,
    SensorType.ESM,
})


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
) -> tuple[float, float]:
    """Compute a blended movement target from centroid and nearest enemy.

    Returns a point that is a weighted average of the enemy centroid
    (general advance toward the line) and the nearest enemy (local
    threat response).  This produces natural "lines closing" behavior
    rather than all units collapsing onto a single point.
    """
    # Centroid
    cx = sum(e.position.easting for e in enemies) / len(enemies)
    cy = sum(e.position.northing for e in enemies) / len(enemies)

    # Nearest enemy
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

    # Blend
    w = centroid_weight
    return cx * w + nx * (1 - w), cy * w + ny * (1 - w)


def _nearest_enemy_dist(unit_pos: Position, enemies: list[Unit]) -> float:
    """Return distance to the closest enemy."""
    best = float("inf")
    ux, uy = unit_pos.easting, unit_pos.northing
    for e in enemies:
        dx = e.position.easting - ux
        dy = e.position.northing - uy
        d = math.sqrt(dx * dx + dy * dy)
        if d < best:
            best = d
    return best


def _standoff_range(unit: Unit, ctx: Any) -> float:
    """Return the range at which this unit should stop advancing.

    Uses 80% of the best *usable* weapon's max range so the unit parks
    comfortably within engagement distance.  Weapons with no ammo remaining
    are ignored — a unit that has expended all ranged ammo will close to
    melee range.  Units without weapons (or with only melee) close fully.
    """
    weapons = getattr(ctx, "unit_weapons", {}).get(unit.entity_id, [])
    best_range = 0.0
    for wpn_inst, ammo_defs in weapons:
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


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class BattleConfig(BaseModel):
    """Tuning parameters for the battle manager."""

    engagement_range_m: float = 10000.0
    morale_check_interval: int = 12
    destruction_threshold: float = 0.5
    disable_threshold: float = 0.3
    default_visibility_m: float = 10000.0
    max_ticks_per_battle: int = 50000
    # Phase 13a-6: Auto-resolve
    auto_resolve_enabled: bool = False
    auto_resolve_max_units: int = 0  # battles with <= this many total units get auto-resolved


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
    ) -> None:
        self._bus = event_bus
        self._config = config or BattleConfig()
        self._battles: dict[str, BattleContext] = {}
        self._next_battle_id = 0
        # Transient assessment cache — not checkpointed
        self._cached_assessments: dict[str, Any] = {}  # unit_id -> SituationAssessment
        # Phase 40b: posture tracking (ticks unit has been stationary)
        self._ticks_stationary: dict[str, int] = {}
        # Phase 40e: per-unit suppression state
        self._suppression_states: dict[str, UnitSuppressionState] = {}

    # ── Engagement detection ────────────────────────────────────────

    def detect_engagement(
        self,
        units_by_side: dict[str, list[Unit]],
        engagement_range_m: float | None = None,
    ) -> list[BattleContext]:
        """Detect new engagements based on proximity between opposing forces.

        Returns newly created :class:`BattleContext` instances for each
        detected engagement (forces within engagement range).
        """
        eng_range = engagement_range_m or self._config.engagement_range_m
        sides = list(units_by_side.keys())
        new_battles: list[BattleContext] = []

        for i, side_a in enumerate(sides):
            for side_b in sides[i + 1:]:
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
                        frozenset(b.involved_sides) == pair and b.active
                        for b in self._battles.values()
                    )
                    if not already_active:
                        battle = BattleContext(
                            battle_id=f"battle_{self._next_battle_id:04d}",
                            start_tick=0,
                            start_time=datetime.now(),
                            involved_sides=[side_a, side_b],
                            unit_ids={u.entity_id for u in active_a + active_b},
                        )
                        self._next_battle_id += 1
                        self._battles[battle.battle_id] = battle
                        new_battles.append(battle)
                        logger.info(
                            "New battle detected: %s (%s vs %s), min distance %.0fm",
                            battle.battle_id, side_a, side_b, min_dist,
                        )

        return new_battles

    # ── Tactical tick ───────────────────────────────────────────────

    def execute_tick(
        self,
        ctx: Any,  # SimulationContext
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
        if not battle.active:
            return

        battle.ticks_executed += 1
        battle.battle_elapsed_s += dt
        units_by_side = ctx.units_by_side
        cal = ctx.calibration
        timestamp = ctx.clock.current_time

        # 1. Pre-build per-side active enemy lists and position arrays
        active_enemies, enemy_pos_arrays = self._build_enemy_data(units_by_side)

        # 2. AI OODA loop update → completions trigger assess/decide
        if ctx.ooda_engine is not None:
            completions = ctx.ooda_engine.update(dt, ts=timestamp)
            self._process_ooda_completions(ctx, completions, timestamp)

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

        self._execute_movement(ctx, units_by_side, active_enemies, dt, battle, behavior_rules)

        # 4b. Update posture based on movement (Phase 40b)
        defensive_sides = set(cal.get("defensive_sides", []))
        dig_in_ticks = cal.get("dig_in_ticks", 30)
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

        # 5. Engagement — detection + combat
        pending_damage = self._execute_engagements(
            ctx, units_by_side, active_enemies, enemy_pos_arrays, dt, timestamp,
        )

        # 6. Apply deferred damage
        self._apply_deferred_damage(pending_damage, ctx.event_bus, timestamp)

        # 7. Morale checks
        if battle.ticks_executed % self._config.morale_check_interval == 0:
            self._execute_morale(ctx, units_by_side, active_enemies, timestamp)

        # 8. Supply consumption (combat rate)
        if ctx.consumption_engine is not None and ctx.stockpile_manager is not None:
            self._execute_supply_consumption(ctx, units_by_side, dt)

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

    def resolve_battle(self, battle: BattleContext, units_by_side: dict[str, list[Unit]]) -> BattleResult:
        """Finalize a terminated battle and produce a result."""
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
        morale_states: dict | None = None,
        supply_states: dict | None = None,
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
        morale_states : dict | None
            Per-unit morale states for morale factor.
        supply_states : dict | None
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
                from stochastic_warfare.morale.state import MoraleState

                side_morale_vals = [
                    morale_states.get(u.entity_id, MoraleState.STEADY)
                    for u in side_units_active[side]
                ]
                if side_morale_vals:
                    avg_morale = sum(int(m) for m in side_morale_vals) / len(side_morale_vals)
                    morale_factor = max(0.3, 1.0 - avg_morale * 0.15)
            if supply_states:
                side_supply = [
                    supply_states.get(u.entity_id, 1.0)
                    for u in side_units_active[side]
                ]
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
                    self._bus.publish(UnitDestroyedEvent(
                        timestamp=datetime.min,
                        source=ModuleId.COMBAT,
                        unit_id=unit.entity_id,
                        cause="auto_resolve",
                        side=unit.side,
                    ))

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

    def get_state(self) -> dict[str, Any]:
        """Capture battle manager state for checkpointing."""
        return {
            "battles": {
                bid: {
                    "battle_id": b.battle_id,
                    "start_tick": b.start_tick,
                    "start_time": b.start_time.isoformat(),
                    "involved_sides": b.involved_sides,
                    "active": b.active,
                    "ticks_executed": b.ticks_executed,
                    "unit_ids": list(b.unit_ids),
                    "wave_assignments": b.wave_assignments,
                    "battle_elapsed_s": b.battle_elapsed_s,
                }
                for bid, b in self._battles.items()
            },
            "next_battle_id": self._next_battle_id,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore battle manager state from checkpoint."""
        self._next_battle_id = state.get("next_battle_id", 0)
        self._battles.clear()
        self._cached_assessments.clear()
        for bid, bdata in state.get("battles", {}).items():
            self._battles[bid] = BattleContext(
                battle_id=bdata["battle_id"],
                start_tick=bdata["start_tick"],
                start_time=datetime.fromisoformat(bdata["start_time"]),
                involved_sides=bdata["involved_sides"],
                active=bdata["active"],
                ticks_executed=bdata["ticks_executed"],
                unit_ids=set(bdata.get("unit_ids", [])),
                wave_assignments=bdata.get("wave_assignments", {}),
                battle_elapsed_s=bdata.get("battle_elapsed_s", 0.0),
            )

    @property
    def active_battles(self) -> list[BattleContext]:
        """Return all currently active battles."""
        return [b for b in self._battles.values() if b.active]

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

    def _process_ooda_completions(
        self,
        ctx: Any,
        completions: list[tuple[str, Any]],
        timestamp: datetime,
    ) -> None:
        """Handle OODA phase completions — trigger assessment/decision.

        After processing each completion, advances the OODA loop to the
        next phase with tactical acceleration applied.
        """
        from stochastic_warfare.c2.ai.ooda import OODAPhase

        # Tactical acceleration multiplier (< 1 = faster decisions in battle)
        tactical_mult = 1.0
        if ctx.ooda_engine is not None:
            tactical_mult = ctx.ooda_engine.tactical_acceleration

        for unit_id, completed_phase in completions:
            # Look up doctrinal school for this unit
            school = None
            if ctx.school_registry is not None:
                school = ctx.school_registry.get_for_unit(unit_id)

            if completed_phase == OODAPhase.OBSERVE:
                # Run situation assessment with real data
                if ctx.assessor is not None:
                    side = self._find_unit_side(ctx, unit_id)
                    if side:
                        friendly = len(ctx.active_units(side))
                        enemies = sum(
                            len(ctx.active_units(s))
                            for s in ctx.side_names()
                            if s != side
                        )

                        # Real morale from state tracking
                        morale_level = self._get_unit_morale_level(ctx, unit_id)

                        # Real supply from stockpile manager
                        supply_level = self._get_unit_supply_level(ctx, unit_id)

                        # Get school weight overrides
                        weight_overrides = None
                        if school is not None:
                            weight_overrides = school.get_assessment_weight_overrides() or None
                        assessment = ctx.assessor.assess(
                            unit_id=unit_id,
                            echelon=5,
                            friendly_units=friendly,
                            friendly_power=float(friendly),
                            morale_level=morale_level,
                            supply_level=supply_level,
                            c2_effectiveness=1.0,
                            contacts=enemies,
                            enemy_power=float(enemies),
                            ts=timestamp,
                            weight_overrides=weight_overrides,
                        )
                        # Cache assessment for DECIDE phase
                        self._cached_assessments[unit_id] = assessment
            elif completed_phase == OODAPhase.DECIDE:
                # Run decision engine with real assessment + personality
                if ctx.decision_engine is not None:
                    # Retrieve cached assessment from OBSERVE phase
                    assessment = self._cached_assessments.get(unit_id)

                    # Get commander personality
                    personality = None
                    if ctx.commander_engine is not None:
                        personality = ctx.commander_engine.get_personality(unit_id)

                    # Build assessment summary from real data
                    assessment_summary = self._build_assessment_summary(
                        ctx, unit_id, assessment,
                    )

                    # Get school decision adjustments
                    school_adjustments = None
                    if school is not None:
                        school_adjustments = school.get_decision_score_adjustments(
                            echelon=5,
                            assessment_summary=assessment_summary,
                        )
                        # Apply opponent modeling if enabled
                        if school.definition.opponent_modeling_enabled:
                            side = self._find_unit_side(ctx, unit_id)
                            enemies = sum(
                                len(ctx.active_units(s))
                                for s in ctx.side_names()
                                if s != side
                            ) if side else 1
                            friendly = len(ctx.active_units(side)) if side else 1
                            opponent_prediction = school.predict_opponent_action(
                                own_assessment=assessment_summary,
                                opponent_power=float(enemies),
                                opponent_morale=assessment_summary.get("morale_level", 0.7),
                                own_power=float(friendly),
                            )
                            if opponent_prediction:
                                temp_scores = dict(school_adjustments)
                                adjusted = school.adjust_scores_for_opponent(
                                    temp_scores, opponent_prediction,
                                )
                                school_adjustments = adjusted
                    ctx.decision_engine.decide(
                        unit_id=unit_id,
                        echelon=5,
                        assessment=assessment,
                        personality=personality,
                        doctrine=None,
                        ts=timestamp,
                        school_adjustments=school_adjustments,
                    )

            # Advance to the next OODA phase and start its timer
            if ctx.ooda_engine is not None:
                # Fold school + commander OODA multipliers into tactical_mult
                effective_mult = tactical_mult
                if school is not None:
                    effective_mult *= school.get_ooda_multiplier()
                if ctx.commander_engine is not None:
                    effective_mult *= ctx.commander_engine.get_ooda_speed_multiplier(unit_id)
                next_phase = ctx.ooda_engine.advance_phase(unit_id)
                ctx.ooda_engine.start_phase(
                    unit_id,
                    next_phase,
                    tactical_mult=effective_mult,
                    ts=timestamp,
                )

    @staticmethod
    def _apply_behavior_rules(
        units_by_side: dict[str, list[Unit]],
        active_enemies: dict[str, list[Unit]],
        behavior_rules: dict[str, Any],
    ) -> None:
        """Set unit speeds from scenario behavior_rules (pre-scripted behavior).

        Mirrors :func:`~stochastic_warfare.validation.scenario_runner.apply_behavior`.
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
        ctx: Any,
        units_by_side: dict[str, list[Unit]],
        active_enemies: dict[str, list[Unit]],
        dt: float,
        battle: BattleContext | None = None,
        behavior_rules: dict[str, Any] | None = None,
    ) -> None:
        """Execute movement for all active units."""
        cal = ctx.calibration
        wave_interval = cal.get("wave_interval_s", 300.0)
        battle_elapsed = battle.battle_elapsed_s if battle is not None else 0.0
        wave_assignments = battle.wave_assignments if battle is not None else {}
        _rules = behavior_rules or {}

        # Sides that should hold position (defensive doctrine)
        defensive_sides = set(cal.get("defensive_sides", []))

        for side, units in units_by_side.items():
            enemies = active_enemies.get(side, [])
            if not enemies:
                continue

            # If behavior_rules explicitly say hold_position, skip this side
            side_rules = _rules.get(side, {})
            if side_rules.get("hold_position", False):
                continue

            # Defensive sides don't advance
            if side in defensive_sides:
                continue

            for u in units:
                if u.status != UnitStatus.ACTIVE:
                    continue

                # Emplaced / air-defense units hold position
                if _should_hold_position(u):
                    continue

                # Effective speed: use current speed (set by behavior_rules
                # or AI), fall back to max_speed for scenarios without rules
                effective_speed = u.speed if u.speed > 0 else u.max_speed
                if effective_speed <= 0:
                    continue

                # Wave gating: check if this unit's wave has been released
                wave = wave_assignments.get(u.entity_id, 0)
                if wave == -1:
                    continue  # Reserve — never moves
                if wave > 0 and battle_elapsed < wave * wave_interval:
                    continue  # Wave not yet released

                # Standoff: stop closing once within best weapon range
                # of the nearest enemy
                standoff = _standoff_range(u, ctx)
                nearest_dist = _nearest_enemy_dist(u.position, enemies)
                if nearest_dist <= standoff:
                    continue

                # Blend centroid + nearest enemy for movement target,
                # then add a perpendicular offset to maintain formation
                # spacing and prevent centroid collapse.
                tx, ty = _movement_target(u.position, enemies)
                dx = tx - u.position.easting
                dy = ty - u.position.northing
                dist = math.sqrt(dx * dx + dy * dy)
                if dist < 1.0:
                    continue

                # Perpendicular offset: preserve each unit's lateral
                # displacement relative to its own side's centroid.
                # This keeps units in a rough line rather than collapsing.
                own_units = [ou for ou in units
                             if ou.status == UnitStatus.ACTIVE]
                if len(own_units) > 1:
                    own_cx = sum(ou.position.easting for ou in own_units) / len(own_units)
                    own_cy = sum(ou.position.northing for ou in own_units) / len(own_units)
                    # Unit's lateral offset from its own centroid
                    lat_dx = u.position.easting - own_cx
                    lat_dy = u.position.northing - own_cy
                    # Project onto perpendicular of advance direction
                    # perp = (-dy, dx) / dist
                    perp_x, perp_y = -dy / dist, dx / dist
                    lat_proj = lat_dx * perp_x + lat_dy * perp_y
                    # Add lateral offset to target (preserves formation width)
                    tx += perp_x * lat_proj
                    ty += perp_y * lat_proj
                    # Recompute advance vector
                    dx = tx - u.position.easting
                    dy = ty - u.position.northing
                    dist = math.sqrt(dx * dx + dy * dy)
                    if dist < 1.0:
                        continue

                # MOPP speed factor (Phase 25c)
                mopp_speed_factor = 1.0
                cbrn = getattr(ctx, "cbrn_engine", None)
                if cbrn is not None:
                    mopp_levels = getattr(cbrn, "_mopp_levels", {})
                    mopp_level = mopp_levels.get(u.entity_id, 0)
                    if mopp_level > 0:
                        from stochastic_warfare.cbrn.protection import ProtectionEngine
                        mopp_speed_factor = ProtectionEngine.get_mopp_speed_factor(mopp_level)

                # Don't overshoot past standoff distance
                max_close = max(0.0, nearest_dist - standoff)
                move_dist = min(effective_speed * dt * mopp_speed_factor, dist, max_close)
                if move_dist <= 0:
                    continue
                nx = u.position.easting + (dx / dist) * move_dist
                ny = u.position.northing + (dy / dist) * move_dist
                object.__setattr__(u, "position", Position(nx, ny, u.position.altitude))

    def _execute_engagements(
        self,
        ctx: Any,
        units_by_side: dict[str, list[Unit]],
        active_enemies: dict[str, list[Unit]],
        enemy_pos_arrays: dict[str, np.ndarray],
        dt: float,
        timestamp: datetime,
    ) -> list[tuple[Unit, UnitStatus]]:
        """Run detection + engagement for all units. Returns deferred damage."""
        pending_damage: list[tuple[Unit, UnitStatus]] = []
        cal = ctx.calibration
        visibility_m = cal.get("visibility_m", self._config.default_visibility_m)
        hit_prob_mod = cal.get("hit_probability_modifier", 1.0)
        # Per-side target_size_modifier: look up target_size_modifier_{side}, fall back to uniform
        target_size_mod_default = cal.get("target_size_modifier", 1.0)

        if ctx.engagement_engine is None:
            return pending_damage

        for side_name, side_units in units_by_side.items():
            enemies = active_enemies.get(side_name, [])
            pos_arr = enemy_pos_arrays.get(side_name, np.empty((0, 2)))

            for attacker in side_units:
                if attacker.status != UnitStatus.ACTIVE:
                    continue

                # Phase 40f: morale gate — routed/surrendered units don't fire
                attacker_morale = ctx.morale_states.get(attacker.entity_id)
                if attacker_morale is not None:
                    ms = MoraleState(int(attacker_morale)) if not isinstance(attacker_morale, MoraleState) else attacker_morale
                    if ms in (MoraleState.ROUTED, MoraleState.SURRENDERED):
                        continue

                weapons = ctx.unit_weapons.get(attacker.entity_id, [])
                if not weapons or pos_arr.shape[0] == 0:
                    continue

                # Find closest enemy (vectorized)
                att_pos = np.array([attacker.position.easting, attacker.position.northing])
                diffs = pos_arr - att_pos
                dists = np.sqrt(np.sum(diffs * diffs, axis=1))
                best_idx = int(np.argmin(dists))
                best_range = float(dists[best_idx])
                best_target = enemies[best_idx]

                # Detection check
                detection_range = visibility_m
                weather_independent = False
                sensors = ctx.unit_sensors.get(attacker.entity_id, [])
                for sensor in sensors:
                    if sensor.effective_range > detection_range:
                        detection_range = sensor.effective_range
                        if sensor.sensor_type in _WEATHER_BYPASS_TYPES:
                            weather_independent = True

                if best_range > detection_range:
                    continue

                vis_mod = 1.0 if weather_independent else (min(visibility_m / best_range, 1.0) if best_range > 0 else 1.0)

                # Select best weapon for current range — prefer ranged weapons
                # at distance, melee weapons at close range.  Skip weapons
                # that are out of ammo or out of range.
                target_domain = best_target.domain.name
                selected_wpn = None
                selected_ammo_def = None
                selected_ammo_id = None
                best_wpn_score = -1.0
                for wpn_inst, ammo_defs in weapons:
                    if not ammo_defs:
                        continue
                    ammo_def = ammo_defs[0]
                    ammo_id = ammo_def.ammo_id
                    if not wpn_inst.can_fire(ammo_id):
                        continue
                    max_r = wpn_inst.definition.max_range_m
                    if max_r > 0 and best_range > max_r:
                        continue
                    # Phase 40d: domain filtering
                    if target_domain not in wpn_inst.definition.effective_target_domains():
                        continue
                    # Phase 40c: deployed weapons can't fire while moving
                    if attacker.speed > 0.5 and wpn_inst.definition.requires_deployed:
                        continue
                    # Score: prefer weapon whose max range best fits current
                    # distance.  Ranged weapons score higher when target is
                    # far; melee weapons score higher when target is very
                    # close (ratio > 1 means "within comfortable range").
                    if max_r > 0:
                        ratio = max_r / max(best_range, 1.0)
                        # Ideal ratio is ~1.5 (target well within range)
                        score = min(ratio, 3.0)
                    else:
                        score = 0.1  # fallback for weapons with 0 range
                    if score > best_wpn_score:
                        best_wpn_score = score
                        selected_wpn = wpn_inst
                        selected_ammo_def = ammo_def
                        selected_ammo_id = ammo_id

                if selected_wpn is None:
                    continue
                wpn_inst = selected_wpn
                ammo_def = selected_ammo_def
                ammo_id = selected_ammo_id

                target_armor = getattr(best_target, "armor_front", 0.0)
                crew_count = len(best_target.personnel) if best_target.personnel else 4

                # Find side config for crew skill
                side_cfg = None
                for sc in ctx.config.sides:
                    if sc.side == side_name:
                        side_cfg = sc
                        break

                # Phase 40f: morale accuracy modifier
                morale_accuracy_mod = 1.0
                if attacker_morale is not None:
                    ms = MoraleState(int(attacker_morale)) if not isinstance(attacker_morale, MoraleState) else attacker_morale
                    effects = _MORALE_EFFECTS.get(ms, {})
                    morale_accuracy_mod = effects.get("accuracy_mult", 1.0)

                crew_skill = (side_cfg.experience_level if side_cfg else 0.5) * hit_prob_mod * morale_accuracy_mod

                # Per-side target_size_modifier: use target's side
                target_side = self._find_unit_side(ctx, best_target.entity_id)
                target_size_mod = cal.get(
                    f"target_size_modifier_{target_side}",
                    target_size_mod_default,
                )

                # Current time for fire rate limiting
                current_time_s = ctx.clock.elapsed.total_seconds()

                # Determine engagement type — DEW weapons route through
                # Beer-Lambert / HPM models instead of ballistic physics
                engagement_type = EngagementType.DIRECT_FIRE
                try:
                    if wpn_inst.definition.parsed_category() == WeaponCategory.DIRECTED_ENERGY:
                        if wpn_inst.definition.beam_power_kw > 0:
                            engagement_type = EngagementType.DEW_LASER
                        else:
                            engagement_type = EngagementType.DEW_HPM
                except (KeyError, ValueError):
                    pass

                # Phase 40b: extract target posture
                target_posture_val = getattr(best_target, "posture", None)
                target_posture_str = target_posture_val.name if target_posture_val is not None else "MOVING"

                result = ctx.engagement_engine.route_engagement(
                    engagement_type=engagement_type,
                    attacker_id=attacker.entity_id,
                    target_id=best_target.entity_id,
                    attacker_pos=attacker.position,
                    target_pos=best_target.position,
                    weapon=wpn_inst,
                    ammo_id=ammo_id,
                    ammo_def=ammo_def,
                    dew_engine=getattr(ctx, 'dew_engine', None),
                    crew_skill=crew_skill,
                    target_size_m2=8.5 * target_size_mod,
                    target_armor_mm=target_armor,
                    shooter_speed_mps=attacker.speed,
                    target_posture=target_posture_str,
                    visibility=vis_mod,
                    timestamp=timestamp,
                    current_time_s=current_time_s,
                )

                # Phase 40e: apply fire volume to target suppression
                if result.engaged:
                    sup_eng = getattr(ctx, "suppression_engine", None)
                    if sup_eng is not None:
                        tid = best_target.entity_id
                        if tid not in self._suppression_states:
                            self._suppression_states[tid] = UnitSuppressionState()
                        sup_eng.apply_fire_volume(
                            state=self._suppression_states[tid],
                            rounds_per_minute=wpn_inst.definition.rate_of_fire_rpm,
                            caliber_mm=wpn_inst.definition.caliber_mm,
                            range_m=best_range,
                            duration_s=dt,
                        )

                if result.engaged and result.hit_result and result.hit_result.hit:
                    if engagement_type in (EngagementType.DEW_LASER, EngagementType.DEW_HPM):
                        # DEW hit = target destroyed (thermal/EMP kill)
                        pending_damage.append((best_target, UnitStatus.DESTROYED))
                    elif (result.damage_result
                            and result.damage_result.damage_fraction > 0):
                        if result.damage_result.damage_fraction >= self._config.destruction_threshold:
                            pending_damage.append((best_target, UnitStatus.DESTROYED))
                        elif result.damage_result.damage_fraction >= self._config.disable_threshold:
                            pending_damage.append((best_target, UnitStatus.DISABLED))

        return pending_damage

    @staticmethod
    def _apply_deferred_damage(
        pending_damage: list[tuple[Unit, UnitStatus]],
        event_bus: Any | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        """Apply deferred damage — worst outcome wins per unit."""
        applied: dict[str, UnitStatus] = {}
        for target, new_status in pending_damage:
            prev = applied.get(target.entity_id)
            if prev is None or new_status.value > prev.value:
                applied[target.entity_id] = new_status

        ts = timestamp or datetime.min
        for target, new_status in pending_damage:
            if applied.get(target.entity_id) == new_status:
                object.__setattr__(target, "status", new_status)
                applied.pop(target.entity_id, None)
                if event_bus is not None:
                    if new_status == UnitStatus.DESTROYED:
                        event_bus.publish(UnitDestroyedEvent(
                            timestamp=ts,
                            source=ModuleId.COMBAT,
                            unit_id=target.entity_id,
                            cause="combat_damage",
                            side=target.side,
                        ))
                    elif new_status == UnitStatus.DISABLED:
                        event_bus.publish(UnitDisabledEvent(
                            timestamp=ts,
                            source=ModuleId.COMBAT,
                            unit_id=target.entity_id,
                            cause="combat_damage",
                            side=target.side,
                        ))

    def _execute_morale(
        self,
        ctx: Any,
        units_by_side: dict[str, list[Unit]],
        active_enemies: dict[str, list[Unit]],
        timestamp: datetime,
    ) -> None:
        """Run morale checks for all active/routing units."""
        if ctx.morale_machine is None:
            return

        cal = ctx.calibration
        morale_degrade_mod = cal.get("morale_degrade_rate_modifier", 1.0)

        for side_name, side_units in units_by_side.items():
            total = len(side_units)
            destroyed = sum(
                1 for u in side_units
                if u.status in (UnitStatus.DESTROYED, UnitStatus.SURRENDERED)
            )
            casualty_rate = destroyed / total if total > 0 else 0.0

            enemies = active_enemies.get(side_name, [])
            active_own = sum(1 for u in side_units if u.status == UnitStatus.ACTIVE)
            active_enemy = len(enemies)
            force_ratio = active_own / active_enemy if active_enemy > 0 else 10.0

            cohesion = cal.get(f"{side_name}_cohesion", 0.7)

            for u in side_units:
                if u.status not in (UnitStatus.ACTIVE, UnitStatus.ROUTING):
                    continue

                # Phase 40e: use actual suppression level
                sup_state = self._suppression_states.get(u.entity_id)
                suppression_level = sup_state.value if sup_state is not None else 0.0

                new_morale = ctx.morale_machine.check_transition(
                    unit_id=u.entity_id,
                    casualty_rate=casualty_rate * morale_degrade_mod,
                    suppression_level=suppression_level,
                    leadership_present=True,
                    cohesion=cohesion,
                    force_ratio=force_ratio,
                    timestamp=timestamp,
                )
                ctx.morale_states[u.entity_id] = new_morale

                if new_morale == MoraleState.ROUTED:
                    object.__setattr__(u, "status", UnitStatus.ROUTING)
                elif new_morale == MoraleState.SURRENDERED:
                    object.__setattr__(u, "status", UnitStatus.SURRENDERED)

    def _execute_supply_consumption(
        self,
        ctx: Any,
        units_by_side: dict[str, list[Unit]],
        dt: float,
    ) -> None:
        """Consume supplies for active units during combat."""
        dt_hours = dt / 3600.0
        for side_units in units_by_side.values():
            for u in side_units:
                if u.status != UnitStatus.ACTIVE:
                    continue
                personnel = len(u.personnel) if u.personnel else 4
                equipment = len(u.equipment) if u.equipment else 1
                try:
                    result = ctx.consumption_engine.compute_consumption(
                        personnel_count=personnel,
                        equipment_count=equipment,
                        base_fuel_rate_per_hour=10.0,
                        activity=3,  # COMBAT
                        dt_hours=dt_hours,
                    )
                except Exception:
                    pass  # Non-critical — don't halt battle over supply math

    @staticmethod
    def _find_unit_side(ctx: Any, unit_id: str) -> str:
        """Find which side a unit belongs to."""
        for side, units in ctx.units_by_side.items():
            if any(u.entity_id == unit_id for u in units):
                return side
        return ""

    @staticmethod
    def _get_unit_morale_level(ctx: Any, unit_id: str) -> float:
        """Derive morale level [0, 1] from morale state.

        STEADY=1.0, SHAKEN=0.75, BROKEN=0.5, ROUTED=0.25, SURRENDERED=0.0.
        """
        ms = ctx.morale_states.get(unit_id)
        if ms is None:
            return 0.7  # sensible default
        val = int(ms)
        return max(0.0, 1.0 - val * 0.25)

    @staticmethod
    def _get_unit_supply_level(ctx: Any, unit_id: str) -> float:
        """Query stockpile manager for supply state [0, 1]."""
        if ctx.stockpile_manager is None:
            return 1.0
        if not hasattr(ctx.stockpile_manager, "get_supply_state"):
            return 1.0
        try:
            return ctx.stockpile_manager.get_supply_state(unit_id)
        except Exception:
            return 1.0

    @staticmethod
    def _build_assessment_summary(
        ctx: Any,
        unit_id: str,
        assessment: Any,
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
        enemies = sum(
            len(ctx.active_units(s))
            for s in ctx.side_names()
            if s != side
        ) if side else 1
        force_ratio = friendly / max(enemies, 1)
        return {
            "force_ratio": force_ratio,
            "supply_level": BattleManager._get_unit_supply_level(ctx, unit_id),
            "morale_level": BattleManager._get_unit_morale_level(ctx, unit_id),
            "intel_quality": 0.5,
            "c2_effectiveness": 1.0,
        }
