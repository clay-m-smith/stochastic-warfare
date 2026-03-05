"""Supply disruption — interdiction, blockade, sabotage, degradation.

Receives disruption events and modifies supply network state.  No AI
targeting — this module enforces the *effects* of disruption.  Targeting
decisions belong to Phase 8 AI.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.logistics.events import (
    BlockadeEstablishedEvent,
    RouteDegradedEvent,
    RouteInterdictedEvent,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & types
# ---------------------------------------------------------------------------


@dataclass
class InterdictionZone:
    """An area under active supply interdiction."""

    zone_id: str
    position: Position
    radius_m: float
    intensity: float  # 0-1, probability modifier
    source: str  # air, artillery, SOF


@dataclass
class Blockade:
    """A naval blockade enforced over sea zones."""

    blockade_id: str
    sea_zone_ids: list[str]
    enforcing_unit_ids: list[str]
    effectiveness: float  # 0-1
    side: str


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class DisruptionConfig(BaseModel):
    """Tuning parameters for supply disruption."""

    interdiction_effectiveness: float = 0.5
    sabotage_base_probability: float = 0.05
    seasonal_degradation_rate: float = 0.01  # per hour in bad conditions
    blockade_effectiveness_per_ship: float = 0.15
    max_blockade_effectiveness: float = 0.9


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class DisruptionEngine:
    """Apply supply disruption effects to logistics systems.

    Parameters
    ----------
    event_bus : EventBus
        Publishes ``RouteInterdictedEvent``, ``RouteDegradedEvent``,
        ``BlockadeEstablishedEvent``.
    rng : numpy.random.Generator
        Deterministic PRNG stream.
    config : DisruptionConfig | None
        Tuning parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: DisruptionConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or DisruptionConfig()
        self._zones: dict[str, InterdictionZone] = {}
        self._blockades: dict[str, Blockade] = {}

    # -- Interdiction --

    def apply_interdiction(
        self,
        zone_id: str,
        position: Position,
        radius_m: float,
        intensity: float,
        source: str = "air",
        timestamp: datetime | None = None,
    ) -> InterdictionZone:
        """Create or update an interdiction zone."""
        zone = InterdictionZone(
            zone_id=zone_id,
            position=position,
            radius_m=radius_m,
            intensity=min(max(intensity, 0.0), 1.0),
            source=source,
        )
        self._zones[zone_id] = zone

        if timestamp is not None:
            self._event_bus.publish(RouteInterdictedEvent(
                timestamp=timestamp,
                source=ModuleId.LOGISTICS,
                route_id=zone_id,
                position=position,
                severity=intensity,
            ))

        logger.info(
            "Interdiction zone %s at %s (r=%.0fm, intensity=%.2f)",
            zone_id, position, radius_m, intensity,
        )
        return zone

    def apply_insurgent_sabotage(
        self,
        position: Position,
        intensity: float,
        cell_id: str,
        target_type: str,
        timestamp: datetime | None = None,
    ) -> InterdictionZone:
        """Create an interdiction zone from insurgent cell sabotage.

        Wires cell sabotage operations into existing disruption framework.
        """
        zone_id = f"insurgent_sabotage_{cell_id}_{target_type}"
        return self.apply_interdiction(
            zone_id=zone_id,
            position=position,
            radius_m=200.0,
            intensity=intensity,
            source="insurgent",
            timestamp=timestamp,
        )

    def remove_interdiction(self, zone_id: str) -> None:
        """Remove an interdiction zone."""
        self._zones.pop(zone_id, None)

    def check_transport_interdiction(
        self,
        position: Position,
    ) -> bool:
        """Check if a transport at *position* survives interdiction.

        Returns ``True`` if the transport survives, ``False`` if destroyed.
        """
        for zone in self._zones.values():
            dx = position.easting - zone.position.easting
            dy = position.northing - zone.position.northing
            dist = math.sqrt(dx * dx + dy * dy)
            if dist <= zone.radius_m:
                p_destroy = zone.intensity * self._config.interdiction_effectiveness
                if self._rng.random() < p_destroy:
                    return False  # destroyed
        return True  # survived

    # -- Blockade --

    def apply_blockade(
        self,
        blockade_id: str,
        sea_zone_ids: list[str],
        enforcing_unit_ids: list[str],
        side: str,
        timestamp: datetime | None = None,
    ) -> Blockade:
        """Establish a naval blockade."""
        cfg = self._config
        per_ship = cfg.blockade_effectiveness_per_ship
        effectiveness = min(
            len(enforcing_unit_ids) * per_ship,
            cfg.max_blockade_effectiveness,
        )
        blockade = Blockade(
            blockade_id=blockade_id,
            sea_zone_ids=list(sea_zone_ids),
            enforcing_unit_ids=list(enforcing_unit_ids),
            effectiveness=effectiveness,
            side=side,
        )
        self._blockades[blockade_id] = blockade

        if timestamp is not None:
            self._event_bus.publish(BlockadeEstablishedEvent(
                timestamp=timestamp,
                source=ModuleId.LOGISTICS,
                blockade_id=blockade_id,
                sea_zone_ids=tuple(sea_zone_ids),
                enforcing_side=side,
            ))

        logger.info(
            "Blockade %s established (effectiveness=%.2f)",
            blockade_id, effectiveness,
        )
        return blockade

    def remove_blockade(self, blockade_id: str) -> None:
        """Remove a blockade."""
        self._blockades.pop(blockade_id, None)

    def check_blockade(self, sea_zone_id: str) -> float:
        """Return the blockade effectiveness for a sea zone (0-1).

        Returns 0.0 if no blockade covers the zone.
        """
        max_eff = 0.0
        for blockade in self._blockades.values():
            if sea_zone_id in blockade.sea_zone_ids:
                max_eff = max(max_eff, blockade.effectiveness)
        return max_eff

    def check_sea_transit(self, sea_zone_id: str) -> bool:
        """Check if a sea transit through *sea_zone_id* succeeds.

        Returns ``True`` if the transit passes, ``False`` if intercepted.
        """
        eff = self.check_blockade(sea_zone_id)
        if eff <= 0.0:
            return True
        return bool(self._rng.random() >= eff)

    # -- Seasonal/sabotage degradation --

    def apply_seasonal_degradation(
        self,
        route_id: str,
        current_condition: float,
        dt_hours: float,
        ground_state: int = 0,
        timestamp: datetime | None = None,
    ) -> float:
        """Compute and return new route condition after seasonal degradation.

        Only applies in mud (2) or snow (3) ground states.
        """
        if ground_state < 2:
            return current_condition
        rate = self._config.seasonal_degradation_rate
        new_condition = max(0.0, current_condition - rate * dt_hours)

        if new_condition != current_condition and timestamp is not None:
            self._event_bus.publish(RouteDegradedEvent(
                timestamp=timestamp,
                source=ModuleId.LOGISTICS,
                route_id=route_id,
                old_condition=current_condition,
                new_condition=new_condition,
                cause="seasonal",
            ))

        return new_condition

    def check_sabotage(
        self,
        route_id: str,
        population_hostility: float = 0.0,
        timestamp: datetime | None = None,
    ) -> float:
        """Check for sabotage on a route.

        Returns damage amount (0.0 if no sabotage). Probability scales
        with population hostility.
        """
        prob = self._config.sabotage_base_probability * population_hostility
        if self._rng.random() < prob:
            damage = self._rng.uniform(0.05, 0.2)
            if timestamp is not None:
                self._event_bus.publish(RouteDegradedEvent(
                    timestamp=timestamp,
                    source=ModuleId.LOGISTICS,
                    route_id=route_id,
                    old_condition=1.0,
                    new_condition=1.0 - damage,
                    cause="sabotage",
                ))
            return damage
        return 0.0

    # -- Queries --

    def get_zone(self, zone_id: str) -> InterdictionZone:
        """Return an interdiction zone; raises ``KeyError`` if not found."""
        return self._zones[zone_id]

    def get_blockade(self, blockade_id: str) -> Blockade:
        """Return a blockade; raises ``KeyError`` if not found."""
        return self._blockades[blockade_id]

    def active_zones(self) -> list[InterdictionZone]:
        """Return all active interdiction zones."""
        return list(self._zones.values())

    def active_blockades(self) -> list[Blockade]:
        """Return all active blockades."""
        return list(self._blockades.values())

    # -- State protocol --

    def get_state(self) -> dict:
        """Serialize for checkpoint."""
        return {
            "zones": {
                zid: {
                    "zone_id": z.zone_id,
                    "position": list(z.position),
                    "radius_m": z.radius_m,
                    "intensity": z.intensity,
                    "source": z.source,
                }
                for zid, z in self._zones.items()
            },
            "blockades": {
                bid: {
                    "blockade_id": b.blockade_id,
                    "sea_zone_ids": b.sea_zone_ids,
                    "enforcing_unit_ids": b.enforcing_unit_ids,
                    "effectiveness": b.effectiveness,
                    "side": b.side,
                }
                for bid, b in self._blockades.items()
            },
        }

    def set_state(self, state: dict) -> None:
        """Restore from checkpoint."""
        self._zones.clear()
        for zid, zd in state["zones"].items():
            self._zones[zid] = InterdictionZone(
                zone_id=zd["zone_id"],
                position=Position(*zd["position"]),
                radius_m=zd["radius_m"],
                intensity=zd["intensity"],
                source=zd["source"],
            )
        self._blockades.clear()
        for bid, bd in state["blockades"].items():
            self._blockades[bid] = Blockade(
                blockade_id=bd["blockade_id"],
                sea_zone_ids=bd["sea_zone_ids"],
                enforcing_unit_ids=bd["enforcing_unit_ids"],
                effectiveness=bd["effectiveness"],
                side=bd["side"],
            )
