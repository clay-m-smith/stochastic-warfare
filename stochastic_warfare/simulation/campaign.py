"""Campaign-level manager — strategic AI, reinforcements, supply.

Orchestrates strategic-tick logic: reinforcement arrivals, supply
network updates, strategic AI cycles, strategic movement, maintenance,
and engagement detection.  No domain logic — only sequencing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.simulation.battle import (
    BattleContext, BattleManager,
    _movement_target, _should_hold_position,
)
from stochastic_warfare.simulation.scenario import ReinforcementConfig

logger = get_logger(__name__)


@dataclass(frozen=True)
class ReinforcementArrivedEvent(Event):
    """Published when reinforcement units arrive."""

    side: str = ""
    unit_count: int = 0
    unit_types: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class CampaignConfig(BaseModel):
    """Tuning parameters for the campaign manager."""

    engagement_detection_range_m: float = 15000.0
    strategic_ai_echelon: int = 9  # Corps+
    enable_maintenance: bool = True
    enable_supply_network: bool = True
    enable_strategic_movement: bool = True
    strategic_speed_fraction: float = 0.3
    defensive_sides: list[str] = []
    """Fraction of max_speed used during strategic march toward enemies."""


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ReinforcementEntry:
    """Tracks a scheduled reinforcement."""

    config: ReinforcementConfig
    arrived: bool = False
    actual_arrival_time_s: float = 0.0  # computed at setup (may differ from config)


# ---------------------------------------------------------------------------
# Campaign manager
# ---------------------------------------------------------------------------


class CampaignManager:
    """Manages campaign-level logic for strategic ticks.

    Parameters
    ----------
    event_bus : EventBus
        For publishing campaign events.
    rng : numpy.random.Generator
        Deterministic PRNG stream.
    config : CampaignConfig | None
        Tuning parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: CampaignConfig | None = None,
    ) -> None:
        self._bus = event_bus
        self._rng = rng
        self._config = config or CampaignConfig()
        self._reinforcements: list[ReinforcementEntry] = []

    def set_reinforcements(self, reinforcements: list[ReinforcementConfig]) -> None:
        """Initialize the reinforcement schedule.

        When a reinforcement has ``arrival_sigma > 0``, the actual arrival
        time is sampled from a log-normal distribution centered on the
        configured ``arrival_time_s``. Otherwise it matches exactly.
        """
        self._reinforcements = []
        for r in reinforcements:
            sigma = getattr(r, "arrival_sigma", 0.0)
            if sigma > 0:
                actual = r.arrival_time_s * float(self._rng.lognormal(0, sigma))
            else:
                actual = r.arrival_time_s
            self._reinforcements.append(
                ReinforcementEntry(config=r, actual_arrival_time_s=actual)
            )

    # ── Strategic tick ──────────────────────────────────────────────

    def update_strategic(
        self,
        ctx: Any,  # SimulationContext
        dt: float,
    ) -> None:
        """Execute one strategic tick.

        Sequences: reinforcements → supply → strategic AI → movement →
        maintenance → engagement detection.

        Parameters
        ----------
        ctx:
            SimulationContext with all engines and state.
        dt:
            Tick duration in seconds.
        """
        elapsed_s = ctx.clock.elapsed.total_seconds()
        timestamp = ctx.clock.current_time

        # 1. Check reinforcement schedule
        new_units = self.check_reinforcements(ctx, elapsed_s)
        for unit in new_units:
            side = unit.side if isinstance(unit.side, str) else unit.side.value
            if side in ctx.units_by_side:
                ctx.units_by_side[side].append(unit)
            else:
                ctx.units_by_side[side] = [unit]

        # 2. Supply network update
        if self._config.enable_supply_network and ctx.supply_network_engine is not None:
            self._update_supply_network(ctx, dt)

        # 3. Strategic AI OODA cycles (corps/theater commanders)
        if ctx.ooda_engine is not None:
            ctx.ooda_engine.update(dt, ts=timestamp)

        # 4. Idle/march supply consumption
        if ctx.consumption_engine is not None and ctx.stockpile_manager is not None:
            self._consume_idle_supplies(ctx, dt)

        # 5. Strategic movement — march toward nearest enemy
        if self._config.enable_strategic_movement:
            self._execute_strategic_movement(ctx, dt)

        # 6. Maintenance checks
        if self._config.enable_maintenance and ctx.maintenance_engine is not None:
            self._run_maintenance(ctx, dt)

        # 7. Phase 54: era-specific strategic engine updates
        era = getattr(ctx.config, "era", "modern")
        if era == "ww2":
            # Phase 54a: convoy updates
            convoy_eng = getattr(ctx, "convoy_engine", None)
            if convoy_eng is not None:
                try:
                    for cid in list(getattr(convoy_eng, "_convoys", {}).keys()):
                        convoy_eng.update_convoy(cid, dt)
                except Exception:
                    logger.debug("Convoy update failed", exc_info=True)

            # Phase 54a: strategic bombing target regeneration
            sb_eng = getattr(ctx, "strategic_bombing_engine", None)
            if sb_eng is not None:
                try:
                    sb_eng.apply_target_regeneration(dt)
                except Exception:
                    logger.debug("Strategic bombing regeneration failed", exc_info=True)

        elif era == "napoleonic":
            # Phase 54c: foraging zone recovery
            foraging_eng = getattr(ctx, "foraging_engine", None)
            if foraging_eng is not None:
                try:
                    dt_days = dt / 86400.0
                    foraging_eng.update_recovery(dt_days)
                except Exception:
                    logger.debug("Foraging recovery failed", exc_info=True)

        elif era == "ancient_medieval":
            # Phase 54d: siege advancement
            siege_eng = getattr(ctx, "siege_engine", None)
            if siege_eng is not None:
                try:
                    for sid in list(getattr(siege_eng, "_sieges", {}).keys()):
                        siege_eng.advance_day(sid)
                        siege_eng.check_starvation(sid)
                        # Phase 66b: assault and sally wiring
                        _siege_state = getattr(siege_eng, "_sieges", {}).get(sid)
                        if _siege_state is not None:
                            _phase = _siege_state.phase
                            from stochastic_warfare.combat.siege import SiegePhase
                            if _phase == SiegePhase.BREACH:
                                siege_eng.attempt_assault(sid)
                            siege_eng.sally_sortie(sid)
                except Exception:
                    logger.debug("Siege advance failed", exc_info=True)

    # ── Strategic movement ───────────────────────────────────────────

    def _execute_strategic_movement(
        self,
        ctx: Any,
        dt: float,
    ) -> None:
        """Move units toward nearest enemy at strategic march speed.

        During strategic resolution, units advance toward the closest
        opposing force at a fraction of their max speed (configured by
        ``strategic_speed_fraction``).  This models operational-level
        maneuver to contact.
        """
        import math

        units_by_side = ctx.units_by_side
        sides = list(units_by_side.keys())
        speed_frac = self._config.strategic_speed_fraction

        # Sides that should hold position (from config or scenario calibration)
        defensive = set(self._config.defensive_sides)
        cal_defensive = getattr(ctx, "calibration", {}).get("defensive_sides", [])
        if cal_defensive:
            defensive.update(cal_defensive)

        for side in sides:
            if side in defensive:
                continue

            active_own = [u for u in units_by_side[side]
                          if u.status == UnitStatus.ACTIVE]
            if not active_own:
                continue

            # Build enemy position list across all opposing sides
            enemies: list[Unit] = []
            for other_side in sides:
                if other_side != side:
                    enemies.extend(
                        u for u in units_by_side[other_side]
                        if u.status == UnitStatus.ACTIVE
                    )
            if not enemies:
                continue

            for u in active_own:
                # Emplaced / air-defense units hold position
                if _should_hold_position(u):
                    continue

                effective_speed = u.max_speed * speed_frac
                if effective_speed <= 0:
                    continue

                # Blend centroid + nearest enemy for movement target
                tx, ty = _movement_target(u.position, enemies)
                dx = tx - u.position.easting
                dy = ty - u.position.northing
                dist = math.sqrt(dx * dx + dy * dy)
                if dist < 1.0:
                    continue

                # Perpendicular offset to maintain formation spacing
                if len(active_own) > 1:
                    own_cx = sum(ou.position.easting for ou in active_own) / len(active_own)
                    own_cy = sum(ou.position.northing for ou in active_own) / len(active_own)
                    lat_dx = u.position.easting - own_cx
                    lat_dy = u.position.northing - own_cy
                    perp_x, perp_y = -dy / dist, dx / dist
                    lat_proj = lat_dx * perp_x + lat_dy * perp_y
                    tx += perp_x * lat_proj
                    ty += perp_y * lat_proj
                    dx = tx - u.position.easting
                    dy = ty - u.position.northing
                    dist = math.sqrt(dx * dx + dy * dy)
                    if dist < 1.0:
                        continue

                move_dist = min(effective_speed * dt, dist)
                scale = move_dist / dist
                new_e = u.position.easting + dx * scale
                new_n = u.position.northing + dy * scale
                object.__setattr__(
                    u, "position",
                    Position(easting=new_e, northing=new_n,
                             altitude=u.position.altitude),
                )

    # ── Reinforcements ──────────────────────────────────────────────

    def check_reinforcements(
        self,
        ctx: Any,
        elapsed_s: float,
    ) -> list[Unit]:
        """Check reinforcement schedule and spawn arriving units.

        Returns newly created units (already positioned).
        """
        new_units: list[Unit] = []

        for entry in self._reinforcements:
            if entry.arrived:
                continue
            if elapsed_s >= entry.actual_arrival_time_s:
                entry.arrived = True
                units = self._spawn_reinforcements(ctx, entry.config)
                new_units.extend(units)
                logger.info(
                    "Reinforcements arrived: %d units for %s at t=%.0fs",
                    len(units), entry.config.side, elapsed_s,
                )
                clock = getattr(ctx, "clock", None)
                ts = clock.current_time if clock is not None else datetime.min
                self._bus.publish(ReinforcementArrivedEvent(
                    timestamp=ts,
                    source=ModuleId.CORE,
                    side=entry.config.side,
                    unit_count=len(units),
                    unit_types=tuple(u.unit_type for u in units),
                ))

        return new_units

    def _spawn_reinforcements(
        self,
        ctx: Any,
        config: ReinforcementConfig,
    ) -> list[Unit]:
        """Create units from a reinforcement config."""
        units: list[Unit] = []
        if ctx.unit_loader is None:
            return units

        entities_rng = ctx.rng_manager.get_stream(ModuleId.ENTITIES)
        spawn_x = config.position[0] if len(config.position) > 0 else 0.0
        spawn_y = config.position[1] if len(config.position) > 1 else 0.0

        unit_idx = 0
        for unit_cfg in config.units:
            for i in range(unit_cfg.count):
                eid = f"reinforce_{config.side}_{unit_cfg.unit_type}_{unit_idx:04d}"
                offset_y = unit_idx * 50.0
                pos = Position(spawn_x, spawn_y + offset_y, 0.0)
                try:
                    unit = ctx.unit_loader.create_unit(
                        unit_type=unit_cfg.unit_type,
                        entity_id=eid,
                        position=pos,
                        side=config.side,
                        rng=entities_rng,
                    )
                    # Apply overrides
                    for key, val in unit_cfg.overrides.items():
                        if hasattr(unit, key):
                            object.__setattr__(unit, key, val)
                    units.append(unit)
                except KeyError:
                    logger.warning(
                        "Reinforcement unit type %r not found", unit_cfg.unit_type,
                    )
                unit_idx += 1

        return units

    # ── Supply network ──────────────────────────────────────────────

    def _update_supply_network(self, ctx: Any, dt: float) -> None:
        """Update the supply network — transport and routing.

        Phase 51d/56g: queries active blockades via DisruptionEngine for
        sea-zone interdiction and degrades SEA transport routes.
        """
        disruption = getattr(ctx, "disruption_engine", None)
        supply_net = getattr(ctx, "supply_network_engine", None)
        if disruption is not None:
            for blockade in disruption.active_blockades():
                max_eff = 0.0
                for zone_id in blockade.sea_zone_ids:
                    eff = disruption.check_blockade(zone_id)
                    max_eff = max(max_eff, eff)
                    if eff > 0:
                        logger.debug(
                            "Blockade %s zone %s eff=%.2f",
                            blockade.blockade_id, zone_id, eff,
                        )
                # Phase 56g: degrade SEA transport routes by blockade effectiveness
                if max_eff > 0 and supply_net is not None:
                    from stochastic_warfare.logistics.supply_network import TransportMode
                    for _rid in list(supply_net._routes):
                        _route = supply_net._routes[_rid]
                        if _route.transport_mode == TransportMode.SEA:
                            _penalty = max(0.01, 1.0 - max_eff)
                            supply_net.update_route_condition(
                                _rid, _route.condition * _penalty,
                            )
                    logger.debug("Blockade eff=%.2f degraded SEA routes", max_eff)

    def _consume_idle_supplies(self, ctx: Any, dt: float) -> None:
        """Consume supplies at idle/march rate during strategic ticks."""
        dt_hours = dt / 3600.0
        for side_units in ctx.units_by_side.values():
            for u in side_units:
                if u.status != UnitStatus.ACTIVE:
                    continue
                personnel = len(u.personnel) if u.personnel else 4
                equipment = len(u.equipment) if u.equipment else 1
                activity = 2 if u.speed > 0 else 0  # MARCH or IDLE
                try:
                    ctx.consumption_engine.compute_consumption(
                        personnel_count=personnel,
                        equipment_count=equipment,
                        base_fuel_rate_per_hour=10.0,
                        activity=activity,
                        dt_hours=dt_hours,
                    )
                except Exception:
                    pass

    # ── Maintenance ─────────────────────────────────────────────────

    def _run_maintenance(self, ctx: Any, dt: float) -> None:
        """Run maintenance/breakdown checks during strategic ticks."""
        maint = getattr(ctx, "maintenance_engine", None)
        if maint is None:
            return
        dt_hours = dt / 3600.0
        temp_c = 20.0
        try:
            if getattr(ctx, "weather_engine", None) is not None:
                temp_c = ctx.weather_engine.current.temperature
        except Exception:
            pass
        try:
            maint.update(
                dt_hours=dt_hours, temperature_c=temp_c,
                timestamp=ctx.clock.current_time,
            )
            maint.complete_repairs(
                dt_hours=dt_hours, timestamp=ctx.clock.current_time,
            )
        except Exception:
            logger.debug("Maintenance update failed", exc_info=True)

    # ── Engagement detection ────────────────────────────────────────

    def detect_engagements(
        self,
        ctx: Any,
        battle_manager: BattleManager,
    ) -> list[BattleContext]:
        """Detect new engagements using the battle manager."""
        return battle_manager.detect_engagement(
            ctx.units_by_side,
            engagement_range_m=self._config.engagement_detection_range_m,
        )

    # ── State persistence ───────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        """Capture campaign manager state."""
        return {
            "reinforcements": [
                {
                    "arrived": e.arrived,
                    "side": e.config.side,
                    "arrival_time_s": e.config.arrival_time_s,
                    "actual_arrival_time_s": e.actual_arrival_time_s,
                }
                for e in self._reinforcements
            ],
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore campaign manager state."""
        for i, rdata in enumerate(state.get("reinforcements", [])):
            if i < len(self._reinforcements):
                self._reinforcements[i].arrived = rdata.get("arrived", False)
                if "actual_arrival_time_s" in rdata:
                    self._reinforcements[i].actual_arrival_time_s = rdata["actual_arrival_time_s"]
