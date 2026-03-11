"""Integrated Air Defense System (IADS) model.

Phase 12f-1. Models IADS sectors with radar handoff chains,
SAM batteries, AAA, and command nodes. SEAD degrades specific
components; destroyed command nodes force SAMs to autonomous mode.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class IadsComponentType(enum.IntEnum):
    """Component types within an IADS sector."""

    EARLY_WARNING_RADAR = 0
    ACQUISITION_RADAR = 1
    SAM_BATTERY = 2
    AAA_POSITION = 3
    COMMAND_NODE = 4


@dataclass
class IadsSector:
    """An IADS sector with layered defenses."""

    sector_id: str
    center: Position
    radius_m: float
    early_warning_radars: list[str] = field(default_factory=list)
    acquisition_radars: list[str] = field(default_factory=list)
    sam_batteries: list[str] = field(default_factory=list)
    aaa_positions: list[str] = field(default_factory=list)
    command_node: str | None = None
    # Condition per component (component_id -> 0.0-1.0)
    component_health: dict[str, float] = field(default_factory=dict)


class IadsConfig(BaseModel):
    """IADS configuration."""

    ew_to_acq_handoff_s: float = 10.0
    """Handoff time from early warning to acquisition radar (seconds)."""
    acq_to_sam_handoff_s: float = 5.0
    """Handoff time from acquisition radar to SAM battery (seconds)."""
    autonomous_effectiveness_mult: float = 0.4
    """SAM effectiveness multiplier when operating without command node."""
    sead_degradation_rate: float = 0.3
    """Damage per SEAD strike to targeted component."""
    sead_effectiveness: float = 0.5
    """Suppression factor scaling SEAD damage impact."""
    sead_arm_effectiveness: float = 0.8
    """ARM missile Pk modifier for anti-radiation missile attacks."""


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class IadsEngine:
    """IADS sector management and engagement processing.

    Parameters
    ----------
    event_bus : EventBus
        For publishing events.
    rng : numpy.random.Generator
        Deterministic PRNG stream.
    config : IadsConfig | None
        Configuration.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: IadsConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or IadsConfig()
        self._sectors: dict[str, IadsSector] = {}

    def register_sector(self, sector: IadsSector) -> None:
        """Register an IADS sector."""
        # Initialize health for all components
        for cid in (sector.early_warning_radars + sector.acquisition_radars +
                    sector.sam_batteries + sector.aaa_positions):
            if cid not in sector.component_health:
                sector.component_health[cid] = 1.0
        if sector.command_node and sector.command_node not in sector.component_health:
            sector.component_health[sector.command_node] = 1.0
        self._sectors[sector.sector_id] = sector
        logger.debug("Registered IADS sector %s", sector.sector_id)

    def get_sector(self, sector_id: str) -> IadsSector:
        """Return a sector; raises ``KeyError`` if not found."""
        return self._sectors[sector_id]

    def process_air_track(
        self,
        sector_id: str,
        track_position: Position,
    ) -> dict[str, Any]:
        """Process an air track through the IADS radar handoff chain.

        Returns engagement assessment with timing and effectiveness.
        """
        sector = self._sectors[sector_id]
        cfg = self._config

        # Stage 1: Early warning detection
        ew_available = any(
            sector.component_health.get(r, 0.0) > 0.0
            for r in sector.early_warning_radars
        )

        # Stage 2: Acquisition radar lock
        acq_available = any(
            sector.component_health.get(r, 0.0) > 0.0
            for r in sector.acquisition_radars
        )

        # Stage 3: SAM engagement readiness
        sam_available = any(
            sector.component_health.get(s, 0.0) > 0.0
            for s in sector.sam_batteries
        )

        # Compute total handoff time
        total_handoff_s = 0.0
        if ew_available:
            total_handoff_s += cfg.ew_to_acq_handoff_s
        if acq_available:
            total_handoff_s += cfg.acq_to_sam_handoff_s

        # Without EW, SAMs get no pre-cueing (increased handoff time)
        if not ew_available and sam_available:
            total_handoff_s += cfg.ew_to_acq_handoff_s * 2.0  # penalty

        # Command node check
        cmd_health = 0.0
        if sector.command_node:
            cmd_health = sector.component_health.get(sector.command_node, 0.0)
        autonomous = cmd_health <= 0.0

        # Compute sector engagement effectiveness
        effectiveness = self.compute_sector_health(sector_id)
        if autonomous:
            effectiveness *= cfg.autonomous_effectiveness_mult

        return {
            "sector_id": sector_id,
            "ew_available": ew_available,
            "acq_available": acq_available,
            "sam_available": sam_available,
            "handoff_time_s": total_handoff_s,
            "autonomous": autonomous,
            "effectiveness": effectiveness,
        }

    def compute_sector_health(self, sector_id: str) -> float:
        """Compute sector health as compound of component availability.

        Health = radar_coverage × SAM_availability × command_connectivity.
        """
        sector = self._sectors[sector_id]

        # Radar coverage: fraction of operational radars
        all_radars = sector.early_warning_radars + sector.acquisition_radars
        if all_radars:
            radar_health = sum(
                sector.component_health.get(r, 0.0) for r in all_radars
            ) / len(all_radars)
        else:
            radar_health = 0.0

        # SAM availability
        if sector.sam_batteries:
            sam_health = sum(
                sector.component_health.get(s, 0.0) for s in sector.sam_batteries
            ) / len(sector.sam_batteries)
        else:
            sam_health = 0.0

        # Command connectivity
        if sector.command_node:
            cmd_health = sector.component_health.get(sector.command_node, 0.0)
        else:
            cmd_health = 0.5  # no command node = partial capability

        return radar_health * sam_health * max(cmd_health, 0.1)

    def apply_sead_damage(
        self,
        sector_id: str,
        component_id: str,
    ) -> float:
        """Apply SEAD damage to a specific IADS component.

        Phase 55c-3: ARM missiles use ``sead_arm_effectiveness`` for radar
        targets (early warning + acquisition radars).  Non-radar targets
        (SAM batteries, AAA) use ``sead_effectiveness`` as before.

        Returns the new health of the component.
        """
        sector = self._sectors[sector_id]
        old_health = sector.component_health.get(component_id, 1.0)
        # Phase 55c-3: use ARM effectiveness for radar targets
        is_radar = (
            component_id in sector.early_warning_radars
            or component_id in sector.acquisition_radars
        )
        effectiveness = (
            self._config.sead_arm_effectiveness if is_radar
            else self._config.sead_effectiveness
        )
        damage = self._config.sead_degradation_rate * effectiveness
        new_health = max(0.0, old_health - damage)
        # Add stochastic variation
        variation = self._rng.normal(0.0, 0.05)
        new_health = max(0.0, min(1.0, new_health + variation))
        sector.component_health[component_id] = new_health
        logger.info(
            "SEAD: sector %s component %s: %.2f -> %.2f",
            sector_id, component_id, old_health, new_health,
        )
        return new_health

    # -- State protocol --

    def get_state(self) -> dict:
        return {
            "sectors": {
                sid: {
                    "sector_id": s.sector_id,
                    "center": list(s.center),
                    "radius_m": s.radius_m,
                    "early_warning_radars": list(s.early_warning_radars),
                    "acquisition_radars": list(s.acquisition_radars),
                    "sam_batteries": list(s.sam_batteries),
                    "aaa_positions": list(s.aaa_positions),
                    "command_node": s.command_node,
                    "component_health": dict(s.component_health),
                }
                for sid, s in self._sectors.items()
            },
        }

    def set_state(self, state: dict) -> None:
        self._sectors.clear()
        for sid, sd in state["sectors"].items():
            sector = IadsSector(
                sector_id=sd["sector_id"],
                center=Position(*sd["center"]),
                radius_m=sd["radius_m"],
                early_warning_radars=sd["early_warning_radars"],
                acquisition_radars=sd["acquisition_radars"],
                sam_batteries=sd["sam_batteries"],
                aaa_positions=sd["aaa_positions"],
                command_node=sd.get("command_node"),
                component_health=sd.get("component_health", {}),
            )
            self._sectors[sid] = sector
