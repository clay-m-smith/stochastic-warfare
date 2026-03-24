"""Naval logistics — UNREP, port ops, LOTS, sealift transit.

Underway replenishment (UNREP) requires calm seas.  Port operations have
throughput limits.  Logistics-Over-The-Shore (LOTS) is low-throughput
but doesn't need a port.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.logistics.events import (
    PortLoadingEvent,
    UnrepCompletedEvent,
    UnrepStartedEvent,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & types
# ---------------------------------------------------------------------------


class NavalSupplyOp(enum.IntEnum):
    """Naval logistics operation type."""

    UNREP = 0
    PORT_LOADING = 1
    PORT_UNLOADING = 2
    LOTS = 3
    SEALIFT_TRANSIT = 4


@dataclass
class NavalSupplyMission:
    """A single naval logistics operation."""

    mission_id: str
    op_type: NavalSupplyOp
    supply_ship_id: str | None
    receiving_unit_ids: list[str]
    port_id: str | None
    fuel_tons: float
    ammo_tons: float
    progress_fraction: float = 0.0
    status: str = "IN_PROGRESS"  # IN_PROGRESS, COMPLETED, CANCELLED


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class NavalLogisticsConfig(BaseModel):
    """Tuning parameters for naval logistics operations."""

    unrep_speed_knots: float = 12.0
    unrep_fuel_transfer_rate_tons_per_hour: float = 200.0
    unrep_ammo_transfer_rate_tons_per_hour: float = 50.0
    unrep_max_sea_state: int = 5
    port_throughput_tons_per_hour: float = 100.0
    lots_throughput_fraction: float = 0.1
    sealift_vulnerability: float = 0.2


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class NavalLogisticsEngine:
    """Manage naval supply operations.

    Parameters
    ----------
    event_bus : EventBus
        Publishes ``UnrepStartedEvent``, ``UnrepCompletedEvent``,
        ``PortLoadingEvent``.
    rng : numpy.random.Generator
        Deterministic PRNG stream.
    config : NavalLogisticsConfig | None
        Tuning parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: NavalLogisticsConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or NavalLogisticsConfig()
        self._missions: dict[str, NavalSupplyMission] = {}
        self._next_id: int = 0

    def start_unrep(
        self,
        supply_ship_id: str,
        receiving_unit_ids: list[str],
        fuel_tons: float,
        ammo_tons: float,
        sea_state: int = 3,
        timestamp: datetime | None = None,
    ) -> NavalSupplyMission | None:
        """Start an underway replenishment operation.

        Returns ``None`` if sea state is too high.
        """
        if sea_state > self._config.unrep_max_sea_state:
            logger.info(
                "UNREP cancelled: sea state %d exceeds max %d",
                sea_state, self._config.unrep_max_sea_state,
            )
            return None

        self._next_id += 1
        mission_id = f"unrep_{self._next_id}"
        mission = NavalSupplyMission(
            mission_id=mission_id,
            op_type=NavalSupplyOp.UNREP,
            supply_ship_id=supply_ship_id,
            receiving_unit_ids=list(receiving_unit_ids),
            port_id=None,
            fuel_tons=fuel_tons,
            ammo_tons=ammo_tons,
        )
        self._missions[mission_id] = mission

        if timestamp is not None:
            self._event_bus.publish(UnrepStartedEvent(
                timestamp=timestamp,
                source=ModuleId.LOGISTICS,
                supply_ship_id=supply_ship_id,
                receiving_unit_ids=tuple(receiving_unit_ids),
            ))

        return mission

    def start_port_ops(
        self,
        port_id: str,
        ship_ids: list[str],
        op_type: NavalSupplyOp,
        tons: float,
        timestamp: datetime | None = None,
    ) -> NavalSupplyMission:
        """Start a port loading/unloading operation."""
        self._next_id += 1
        mission_id = f"port_{self._next_id}"
        mission = NavalSupplyMission(
            mission_id=mission_id,
            op_type=op_type,
            supply_ship_id=None,
            receiving_unit_ids=list(ship_ids),
            port_id=port_id,
            fuel_tons=tons if op_type == NavalSupplyOp.PORT_LOADING else 0.0,
            ammo_tons=tons if op_type == NavalSupplyOp.PORT_UNLOADING else 0.0,
        )
        self._missions[mission_id] = mission

        if timestamp is not None:
            self._event_bus.publish(PortLoadingEvent(
                timestamp=timestamp,
                source=ModuleId.LOGISTICS,
                port_id=port_id,
                ship_ids=tuple(ship_ids),
                op_type=int(op_type),
                tons_transferred=tons,
            ))

        return mission

    def start_lots(
        self,
        beach_position: Position,
        ship_ids: list[str],
        tons: float,
        sea_state: int = 3,
        timestamp: datetime | None = None,
    ) -> NavalSupplyMission | None:
        """Start Logistics-Over-The-Shore operation.

        Returns ``None`` if sea state too high for beach operations.
        """
        if sea_state > 3:  # LOTS limited to sea state 3
            logger.info("LOTS cancelled: sea state %d too high", sea_state)
            return None

        self._next_id += 1
        mission_id = f"lots_{self._next_id}"
        mission = NavalSupplyMission(
            mission_id=mission_id,
            op_type=NavalSupplyOp.LOTS,
            supply_ship_id=None,
            receiving_unit_ids=list(ship_ids),
            port_id=None,
            fuel_tons=tons,
            ammo_tons=0.0,
        )
        self._missions[mission_id] = mission
        return mission

    def update(
        self,
        dt_hours: float,
        sea_state: int = 3,
        timestamp: datetime | None = None,
    ) -> list[NavalSupplyMission]:
        """Advance all naval supply operations.

        Returns list of completed missions.
        """
        cfg = self._config
        completed: list[NavalSupplyMission] = []

        for mission in list(self._missions.values()):
            if mission.status != "IN_PROGRESS":
                continue

            if mission.op_type == NavalSupplyOp.UNREP:
                # UNREP suspended if sea state too high
                if sea_state > cfg.unrep_max_sea_state:
                    continue
                total_tons = mission.fuel_tons + mission.ammo_tons
                if total_tons > 0:
                    fuel_rate = cfg.unrep_fuel_transfer_rate_tons_per_hour
                    ammo_rate = cfg.unrep_ammo_transfer_rate_tons_per_hour
                    # Time to complete based on larger component
                    fuel_time = mission.fuel_tons / max(fuel_rate, 0.01)
                    ammo_time = mission.ammo_tons / max(ammo_rate, 0.01)
                    total_time = max(fuel_time, ammo_time)
                    if total_time > 0:
                        mission.progress_fraction += dt_hours / total_time

            elif mission.op_type in (NavalSupplyOp.PORT_LOADING,
                                     NavalSupplyOp.PORT_UNLOADING):
                total_tons = mission.fuel_tons + mission.ammo_tons
                if total_tons > 0:
                    throughput = cfg.port_throughput_tons_per_hour
                    total_time = total_tons / throughput
                    if total_time > 0:
                        mission.progress_fraction += dt_hours / total_time

            elif mission.op_type == NavalSupplyOp.LOTS:
                total_tons = mission.fuel_tons + mission.ammo_tons
                if total_tons > 0:
                    throughput = cfg.port_throughput_tons_per_hour * cfg.lots_throughput_fraction
                    total_time = total_tons / max(throughput, 0.01)
                    if total_time > 0:
                        mission.progress_fraction += dt_hours / total_time

            mission.progress_fraction = min(mission.progress_fraction, 1.0)
            if mission.progress_fraction >= 1.0:
                mission.status = "COMPLETED"
                completed.append(mission)
                if mission.op_type == NavalSupplyOp.UNREP and timestamp is not None:
                    self._event_bus.publish(UnrepCompletedEvent(
                        timestamp=timestamp,
                        source=ModuleId.LOGISTICS,
                        supply_ship_id=mission.supply_ship_id or "",
                        receiving_unit_ids=tuple(mission.receiving_unit_ids),
                        fuel_transferred_tons=mission.fuel_tons,
                        ammo_transferred_tons=mission.ammo_tons,
                    ))

        return completed

    def get_mission(self, mission_id: str) -> NavalSupplyMission:
        """Return a mission; raises ``KeyError`` if not found."""
        return self._missions[mission_id]

    def active_missions(self) -> list[NavalSupplyMission]:
        """Return all in-progress missions."""
        return [m for m in self._missions.values() if m.status == "IN_PROGRESS"]

    # -- State protocol --

    def get_state(self) -> dict:
        """Serialize for checkpoint."""
        return {
            "next_id": self._next_id,
            "missions": {
                mid: {
                    "mission_id": m.mission_id,
                    "op_type": int(m.op_type),
                    "supply_ship_id": m.supply_ship_id,
                    "receiving_unit_ids": m.receiving_unit_ids,
                    "port_id": m.port_id,
                    "fuel_tons": m.fuel_tons,
                    "ammo_tons": m.ammo_tons,
                    "progress_fraction": m.progress_fraction,
                    "status": m.status,
                }
                for mid, m in self._missions.items()
            },
        }

    def set_state(self, state: dict) -> None:
        """Restore from checkpoint."""
        self._next_id = state.get("next_id", 0)
        self._missions.clear()
        for mid, md in state["missions"].items():
            self._missions[mid] = NavalSupplyMission(
                mission_id=md["mission_id"],
                op_type=NavalSupplyOp(md["op_type"]),
                supply_ship_id=md.get("supply_ship_id"),
                receiving_unit_ids=md.get("receiving_unit_ids", []),
                port_id=md.get("port_id"),
                fuel_tons=md["fuel_tons"],
                ammo_tons=md["ammo_tons"],
                progress_fraction=md["progress_fraction"],
                status=md["status"],
            )
