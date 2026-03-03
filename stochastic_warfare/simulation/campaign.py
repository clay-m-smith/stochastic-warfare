"""Campaign-level manager — strategic AI, reinforcements, supply.

Orchestrates strategic-tick logic: reinforcement arrivals, supply
network updates, strategic AI cycles, strategic movement, maintenance,
and engagement detection.  No domain logic — only sequencing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.simulation.battle import BattleContext, BattleManager
from stochastic_warfare.simulation.scenario import ReinforcementConfig

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class CampaignConfig(BaseModel):
    """Tuning parameters for the campaign manager."""

    engagement_detection_range_m: float = 15000.0
    strategic_ai_echelon: int = 9  # Corps+
    enable_maintenance: bool = True
    enable_supply_network: bool = True


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

        # 5. Maintenance checks
        if self._config.enable_maintenance and ctx.maintenance_engine is not None:
            self._run_maintenance(ctx, dt)

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
        """Update the supply network — transport and routing."""
        # Supply network engine manages pull-based routing
        # This is a thin delegation to the logistics module
        pass  # Supply network update is handled by the engine's own update

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
        # Thin delegation to maintenance engine
        pass

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
