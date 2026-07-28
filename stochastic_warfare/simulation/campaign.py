"""Campaign-level manager — strategic AI, reinforcements, supply.

Orchestrates strategic-tick logic: reinforcement arrivals, supply
network updates, strategic AI cycles, strategic movement, maintenance,
and engagement detection.  No domain logic — only sequencing.
"""

from __future__ import annotations

import copy
import math
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
from stochastic_warfare.simulation.scenario import (
    ReinforcementConfig,
    ReinforcementUnitConfig,
    _json_values_equal,
    register_dynamic_units,
)

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
    wave_ordinal: int = 0
    arrived: bool = False
    actual_arrival_time_s: float = 0.0  # computed at setup (may differ from config)
    legacy_ids: bool = False


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
        self._schedule_signature: list[dict[str, Any]] | None = None

    def set_reinforcements(self, reinforcements: list[ReinforcementConfig]) -> None:
        """Initialize the reinforcement schedule.

        When a reinforcement has ``arrival_sigma > 0``, the actual arrival
        time is sampled from a log-normal distribution centered on the
        configured ``arrival_time_s``. Otherwise it matches exactly.  A
        manager's schedule is immutable after initialization; setting the
        same schedule again is an idempotent no-op that does not resample
        stochastic arrival times.
        """
        validated = [
            ReinforcementConfig.model_validate(
                reinforcement.model_dump(mode="python"),
            )
            for reinforcement in reinforcements
        ]
        signature = [
            reinforcement.model_dump(mode="json")
            for reinforcement in validated
        ]
        if self._schedule_signature is not None:
            if signature == self._schedule_signature:
                return
            raise ValueError(
                "Reinforcement schedule is already initialized with "
                "different topology",
            )

        rng_state = copy.deepcopy(self._rng.bit_generator.state)
        staged: list[ReinforcementEntry] = []
        try:
            for wave_ordinal, reinforcement in enumerate(validated):
                config = reinforcement.model_copy(deep=True)
                r = config
                sigma = getattr(r, "arrival_sigma", 0.0)
                if sigma > 0:
                    actual = (
                        r.arrival_time_s
                        * float(self._rng.lognormal(0, sigma))
                    )
                else:
                    actual = r.arrival_time_s
                if not math.isfinite(actual) or actual < 0.0:
                    raise ValueError(
                        "Reinforcement arrival sampling produced a non-finite "
                        f"time at wave {wave_ordinal}",
                    )
                staged.append(
                    ReinforcementEntry(
                        config=r,
                        wave_ordinal=wave_ordinal,
                        actual_arrival_time_s=actual,
                    )
                )
        except Exception:
            self._rng.bit_generator.state = rng_state
            raise
        self._reinforcements = staged
        self._schedule_signature = copy.deepcopy(signature)

    # ── Strategic tick ──────────────────────────────────────────────

    def update_strategic(
        self,
        ctx: Any,  # SimulationContext
        dt: float,
    ) -> None:
        """Execute one strategic tick.

        Sequences: supply → strategic AI → movement → maintenance →
        engagement detection. Reinforcements are checked by
        :class:`SimulationEngine` before resolution-specific work.

        Parameters
        ----------
        ctx:
            SimulationContext with all engines and state.
        dt:
            Tick duration in seconds.
        """
        timestamp = ctx.clock.current_time

        # 1. Supply network update
        if self._config.enable_supply_network and ctx.supply_network_engine is not None:
            self._update_supply_network(ctx, dt)

        # 2. Strategic AI OODA cycles (corps/theater commanders)
        if ctx.ooda_engine is not None:
            ctx.ooda_engine.update(dt, ts=timestamp)

        # 3. Idle/march supply consumption
        if ctx.consumption_engine is not None and ctx.stockpile_manager is not None:
            self._consume_idle_supplies(ctx, dt)

        # 4. Strategic movement — march toward nearest enemy
        if self._config.enable_strategic_movement:
            self._execute_strategic_movement(ctx, dt)

        # 5. Maintenance checks
        if self._config.enable_maintenance and ctx.maintenance_engine is not None:
            self._run_maintenance(ctx, dt)

        # 6. Phase 54: era-specific strategic engine updates
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
                clock = getattr(ctx, "clock", None)
                if clock is None:
                    raise RuntimeError(
                        "Reinforcement arrival requires a simulation clock",
                    )
                timestamp = clock.current_time
                entities_rng = ctx.rng_manager.get_stream(
                    ModuleId.ENTITIES,
                )
                rng_state = copy.deepcopy(
                    entities_rng.bit_generator.state,
                )
                try:
                    units = self._spawn_reinforcements(
                        ctx,
                        entry,
                        entities_rng,
                    )
                    register_dynamic_units(ctx, units)
                except Exception:
                    entities_rng.bit_generator.state = rng_state
                    raise

                entry.legacy_ids = False
                entry.arrived = True
                new_units.extend(units)
                logger.info(
                    "Reinforcements arrived: %d units for %s at t=%.0fs",
                    len(units), entry.config.side, elapsed_s,
                )
                self._bus.publish(ReinforcementArrivedEvent(
                    timestamp=timestamp,
                    source=ModuleId.CORE,
                    side=entry.config.side,
                    unit_count=len(units),
                    unit_types=tuple(u.unit_type for u in units),
                ))

        return new_units

    def _spawn_reinforcements(
        self,
        ctx: Any,
        entry: ReinforcementEntry,
        entities_rng: np.random.Generator,
    ) -> list[Unit]:
        """Stage every unit in one reinforcement wave."""
        units: list[Unit] = []
        if ctx.unit_loader is None:
            raise RuntimeError(
                "Cannot create reinforcements without a unit loader",
            )

        config = entry.config
        spawn_x = config.position[0] if len(config.position) > 0 else 0.0
        spawn_y = config.position[1] if len(config.position) > 1 else 0.0
        spawn_z = config.position[2] if len(config.position) > 2 else 0.0

        for unit_idx, eid, unit_cfg in self._reinforcement_unit_specs(entry):
            if unit_cfg.overrides:
                raise ValueError(
                    "reinforcement unit overrides are not supported",
                )
            offset_y = unit_idx * 50.0
            pos = Position(spawn_x, spawn_y + offset_y, spawn_z)
            unit = ctx.unit_loader.create_unit(
                unit_type=unit_cfg.unit_type,
                entity_id=eid,
                position=pos,
                side=config.side,
                rng=entities_rng,
            )
            units.append(unit)

        return units

    @staticmethod
    def _reinforcement_unit_specs(
        entry: ReinforcementEntry,
        *,
        legacy_ids: bool = False,
    ) -> list[tuple[int, str, ReinforcementUnitConfig]]:
        """Return stable unit identities for one configured wave."""
        specs: list[tuple[int, str, ReinforcementUnitConfig]] = []
        unit_idx = 0
        for unit_config in entry.config.units:
            for _ in range(unit_config.count):
                if legacy_ids:
                    entity_id = (
                        f"reinforce_{entry.config.side}_"
                        f"{unit_config.unit_type}_{unit_idx:04d}"
                    )
                else:
                    entity_id = (
                        f"reinforce_{entry.config.side}_"
                        f"{entry.wave_ordinal:04d}_"
                        f"{unit_config.unit_type}_{unit_idx:04d}"
                    )
                specs.append((unit_idx, entity_id, unit_config))
                unit_idx += 1
        return specs

    # ── Scripted events (Phase 101) ─────────────────────────────────

    def check_scripted_events(
        self,
        ctx: Any,
        elapsed_s: float,
    ) -> int:
        """Fire scripted events whose time has elapsed (Phase 101).

        Looks up ``ctx.scripted_events`` (list of ``ScriptedEventConfig``)
        and a ``ctx._fired_scripted_events`` set of indices used as
        once-only gating. Returns the number of events fired this call.

        Honest semantics: each handler invokes real engine APIs
        (IED detonation, fire-zone creation, unit teleport, casualty
        application). No magic kills or forced victory.
        """
        events = getattr(ctx, "scripted_events", None)
        if not events:
            return 0
        fired_set = getattr(ctx, "_fired_scripted_events", None)
        if fired_set is None:
            fired_set = set()
            ctx._fired_scripted_events = fired_set
        fired_count = 0
        for idx, ev in enumerate(events):
            if idx in fired_set:
                continue
            if elapsed_s < ev.time_s:
                continue
            try:
                self._dispatch_scripted_event(ctx, ev, idx)
                fired_set.add(idx)
                fired_count += 1
                logger.info(
                    "Scripted event fired: idx=%d type=%s t=%.0fs",
                    idx, ev.event_type, elapsed_s,
                )
            except Exception:
                logger.warning(
                    "Scripted event %d (%s) failed", idx, ev.event_type, exc_info=True,
                )
                fired_set.add(idx)  # don't retry failed events
        return fired_count

    def _dispatch_scripted_event(
        self,
        ctx: Any,
        ev: Any,  # ScriptedEventConfig
        idx: int,
    ) -> None:
        """Dispatch one scripted event to its handler."""
        etype = ev.event_type
        params = ev.params or {}
        clock = getattr(ctx, "clock", None)
        ts = clock.current_time if clock is not None else datetime.min

        if etype == "hbied_detonation":
            uw_eng = getattr(ctx, "unconventional_engine", None)
            if uw_eng is None:
                return
            obstacle_id = params.get("obstacle_id")
            # Support index-based lookup: obstacle_index -> initial_ied_obstacle_ids[i]
            if obstacle_id is None:
                oi = params.get("obstacle_index")
                ids = getattr(ctx, "initial_ied_obstacle_ids", [])
                if oi is not None and 0 <= oi < len(ids):
                    obstacle_id = ids[oi]
            target_unit_id = params.get("target_unit_id", "")
            if obstacle_id:
                uw_eng.detonate_ied(obstacle_id, target_unit_id, timestamp=ts)

        elif etype == "wp_fire_zone":
            inc_eng = getattr(ctx, "incendiary_engine", None)
            if inc_eng is None:
                return
            center = params.get("center", [0.0, 0.0])
            radius_m = float(params.get("radius_m", 50.0))
            fuel_load = float(params.get("fuel_load", 0.6))
            duration_s = float(params.get("duration_s", 1800.0))
            pos = Position(float(center[0]), float(center[1]), 0.0)
            _weather = getattr(ctx, "weather_engine", None)
            _ws, _wd = 0.0, 0.0
            if _weather is not None:
                try:
                    _ws = _weather.current.wind.speed
                    _wd = _weather.current.wind.direction
                except Exception:
                    pass
            inc_eng.create_fire_zone(
                position=pos,
                radius_m=radius_m,
                fuel_load=fuel_load,
                wind_speed_mps=_ws,
                wind_dir_rad=_wd,
                duration_s=duration_s,
                timestamp=ctx.clock.elapsed.total_seconds(),
            )

        elif etype == "unit_teleport":
            unit_id = params.get("unit_id", "")
            target = params.get("position", [0.0, 0.0])
            unit = self._find_unit(ctx, unit_id)
            if unit is None:
                return
            new_pos = Position(float(target[0]), float(target[1]), unit.position.altitude)
            object.__setattr__(unit, "position", new_pos)

        elif etype == "casualty_pulse":
            unit_id = params.get("unit_id", "")
            casualties = int(params.get("casualties", 1))
            unit = self._find_unit(ctx, unit_id)
            if unit is None or not unit.personnel:
                return
            # Remove up to N personnel from the back of the roster
            for _ in range(min(casualties, len(unit.personnel))):
                try:
                    unit.personnel.pop()
                except Exception:
                    break

    def _find_unit(self, ctx: Any, unit_id: str) -> Unit | None:
        if not unit_id:
            return None
        for units in ctx.units_by_side.values():
            for u in units:
                if u.entity_id == unit_id:
                    return u
        return None

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
            timestamp=ctx.clock.current_time,
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
                    "wave_ordinal": e.wave_ordinal,
                    "config": e.config.model_dump(mode="json"),
                    **({"legacy_ids": True} if e.legacy_ids else {}),
                }
                for e in self._reinforcements
            ],
        }

    def _stage_state(
        self,
        state: dict[str, Any],
        *,
        allow_legacy: bool = False,
    ) -> list[tuple[ReinforcementEntry, bool, float, bool]]:
        """Validate checkpoint state and return a non-mutating commit plan."""
        raw_reinforcements = state.get("reinforcements", [])
        if not isinstance(raw_reinforcements, list):
            raise ValueError("Checkpoint reinforcements must be a list")
        if len(raw_reinforcements) != len(self._reinforcements):
            raise ValueError(
                "Incompatible reinforcement schedule topology: checkpoint "
                f"has {len(raw_reinforcements)} waves, runtime has "
                f"{len(self._reinforcements)}",
            )

        staged: list[tuple[ReinforcementEntry, bool, float, bool]] = []
        for entry, rdata in zip(
            self._reinforcements,
            raw_reinforcements,
            strict=True,
        ):
            if not isinstance(rdata, dict):
                raise ValueError(
                    "Checkpoint reinforcement entries must be mappings",
                )
            has_ordinal = "wave_ordinal" in rdata
            has_config = "config" in rdata
            if has_ordinal != has_config:
                raise ValueError(
                    "Checkpoint reinforcement topology must contain both "
                    "wave_ordinal and config, or neither for a legacy entry",
                )
            is_legacy_shape = not has_ordinal
            if is_legacy_shape:
                if not allow_legacy:
                    raise ValueError(
                        "Legacy reinforcement checkpoint entries require a "
                        "versionless engine checkpoint",
                    )
                if (
                    rdata.get("side") != entry.config.side
                    or rdata.get("arrival_time_s")
                    != entry.config.arrival_time_s
                ):
                    raise ValueError(
                        "Incompatible legacy reinforcement schedule topology "
                        f"at wave {entry.wave_ordinal}",
                    )
            else:
                raw_ordinal = rdata["wave_ordinal"]
                if (
                    isinstance(raw_ordinal, bool)
                    or not isinstance(raw_ordinal, int)
                    or raw_ordinal != entry.wave_ordinal
                ):
                    raise ValueError(
                        "Incompatible reinforcement schedule topology at wave "
                        f"{entry.wave_ordinal}: checkpoint ordinal is "
                        f"{raw_ordinal!r}",
                    )
                expected_config = entry.config.model_dump(mode="json")
                if not _json_values_equal(rdata["config"], expected_config):
                    raise ValueError(
                        "Incompatible reinforcement schedule topology at wave "
                        f"{entry.wave_ordinal}: configuration differs",
                    )
                if (
                    rdata.get("side") != entry.config.side
                    or not _json_values_equal(
                        rdata.get("arrival_time_s"),
                        entry.config.arrival_time_s,
                    )
                ):
                    raise ValueError(
                        "Incompatible reinforcement schedule topology at wave "
                        f"{entry.wave_ordinal}: side or arrival time differs",
                    )

            legacy_ids = rdata.get("legacy_ids", False)
            if not isinstance(legacy_ids, bool):
                raise ValueError(
                    "Checkpoint reinforcement legacy_ids flag must be boolean "
                    f"at wave {entry.wave_ordinal}",
                )
            if is_legacy_shape:
                if "legacy_ids" in rdata and not legacy_ids:
                    raise ValueError(
                        "Legacy reinforcement checkpoint entries must use "
                        "legacy IDs",
                    )
                legacy_ids = True
            arrived = rdata.get("arrived")
            if not isinstance(arrived, bool):
                raise ValueError(
                    "Checkpoint reinforcement arrived flag must be boolean "
                    f"at wave {entry.wave_ordinal}",
                )
            actual_arrival = rdata.get("actual_arrival_time_s")
            if (
                isinstance(actual_arrival, bool)
                or not isinstance(actual_arrival, (int, float))
                or not math.isfinite(float(actual_arrival))
                or float(actual_arrival) < 0.0
            ):
                raise ValueError(
                    "Checkpoint reinforcement actual_arrival_time_s must be "
                    f"a finite non-negative number at wave {entry.wave_ordinal}",
                )
            staged.append(
                (entry, arrived, float(actual_arrival), legacy_ids),
            )

        return staged

    def validate_checkpoint_roster(
        self,
        state: dict[str, Any],
        context_state: dict[str, Any],
        *,
        allow_legacy: bool = False,
    ) -> None:
        """Cross-check arrival flags against the checkpoint force roster."""
        staged = self._stage_state(state, allow_legacy=allow_legacy)
        raw_forces = context_state.get("units_by_side")
        if not isinstance(raw_forces, dict):
            raise ValueError(
                "Checkpoint context units_by_side must be a mapping",
            )

        unit_topology: dict[str, tuple[str, str]] = {}
        for side, raw_units in raw_forces.items():
            if not isinstance(side, str) or not isinstance(raw_units, list):
                raise ValueError(
                    "Checkpoint force sides must map names to unit lists",
                )
            for raw_unit in raw_units:
                if not isinstance(raw_unit, dict):
                    raise ValueError(
                        "Checkpoint force entries must be mappings",
                    )
                entity_id = raw_unit.get("entity_id")
                if not isinstance(entity_id, str):
                    raise ValueError(
                        "Checkpoint force entity_id values must be strings",
                    )
                unit_type = raw_unit.get("unit_type")
                if not isinstance(unit_type, str):
                    raise ValueError(
                        "Checkpoint force unit_type values must be strings",
                    )
                if entity_id in unit_topology:
                    raise ValueError(
                        f"Duplicate checkpoint entity_id {entity_id!r}",
                    )
                unit_topology[entity_id] = (side, unit_type)

        raw_aggregation = context_state.get("aggregation_engine")
        if raw_aggregation is not None:
            if not isinstance(raw_aggregation, dict):
                raise ValueError(
                    "Checkpoint aggregation_engine must be a mapping",
                )
            raw_aggregates = raw_aggregation.get("aggregates", {})
            if not isinstance(raw_aggregates, dict):
                raise ValueError(
                    "Checkpoint aggregation_engine.aggregates must be a "
                    "mapping",
                )
            for raw_aggregate in raw_aggregates.values():
                if not isinstance(raw_aggregate, dict):
                    raise ValueError(
                        "Checkpoint aggregate entries must be mappings",
                    )
                raw_snapshots = raw_aggregate.get("snapshots", [])
                if not isinstance(raw_snapshots, list):
                    raise ValueError(
                        "Checkpoint aggregate snapshots must be a list",
                    )
                for raw_snapshot in raw_snapshots:
                    if not isinstance(raw_snapshot, dict):
                        raise ValueError(
                            "Checkpoint aggregate snapshots must be mappings",
                        )
                    raw_unit = raw_snapshot.get("unit_state")
                    if not isinstance(raw_unit, dict):
                        raise ValueError(
                            "Checkpoint aggregate unit_state must be a mapping",
                        )
                    entity_id = raw_unit.get("entity_id")
                    unit_type = raw_unit.get("unit_type")
                    side = raw_snapshot.get(
                        "original_side",
                        raw_unit.get("side"),
                    )
                    if not all(
                        isinstance(value, str)
                        for value in (entity_id, unit_type, side)
                    ):
                        raise ValueError(
                            "Checkpoint aggregate constituent identity fields "
                            "must be strings",
                        )
                    if entity_id in unit_topology:
                        raise ValueError(
                            f"Duplicate checkpoint entity_id {entity_id!r}",
                        )
                    unit_topology[entity_id] = (side, unit_type)

        expected_presence: dict[str, tuple[str, str, bool, int]] = {}
        for entry, arrived, _, legacy_ids in staged:
            for _, entity_id, unit_config in self._reinforcement_unit_specs(
                entry,
                legacy_ids=legacy_ids,
            ):
                prior = expected_presence.get(entity_id)
                must_be_present = arrived or (
                    prior is not None and prior[2]
                )
                expected_presence[entity_id] = (
                    entry.config.side,
                    unit_config.unit_type,
                    must_be_present,
                    entry.wave_ordinal,
                )

        for entity_id, (
            expected_side,
            expected_type,
            must_be_present,
            wave_ordinal,
        ) in expected_presence.items():
            actual_topology = unit_topology.get(entity_id)
            if must_be_present and actual_topology != (
                expected_side,
                expected_type,
            ):
                raise ValueError(
                    "Checkpoint reinforcement arrival flag or unit topology "
                    "disagrees with force roster at wave "
                    f"{wave_ordinal}: {entity_id!r} must be present as "
                    f"{expected_side!r}/{expected_type!r}",
                )
            if not must_be_present and actual_topology is not None:
                raise ValueError(
                    "Checkpoint reinforcement arrival flag disagrees "
                    f"with force roster at wave {wave_ordinal}: "
                    f"{entity_id!r} is present before arrival",
                )

    def set_state(
        self,
        state: dict[str, Any],
        *,
        allow_legacy: bool = False,
    ) -> None:
        """Validate and atomically restore campaign manager state."""
        staged = self._stage_state(state, allow_legacy=allow_legacy)
        for entry, arrived, actual_arrival, legacy_ids in staged:
            entry.arrived = arrived
            entry.actual_arrival_time_s = actual_arrival
            entry.legacy_ids = legacy_ids
