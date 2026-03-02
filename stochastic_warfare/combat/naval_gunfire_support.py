"""Shore bombardment from naval vessels.

Models naval gunfire support (NGFS) with accuracy degradation over range,
spotter-corrected fire, and fire support coordination line (FSCL) checks.
Delegates round dispersion to the indirect-fire engine pattern (CEP-based
Gaussian scatter).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.combat.events import ShoreBombardmentEvent
from stochastic_warfare.combat.indirect_fire import IndirectFireEngine
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position

logger = get_logger(__name__)


class NavalGunfireSupportConfig(BaseModel):
    """Tunable parameters for naval gunfire support."""

    base_cep_m: float = 200.0  # CEP at reference range
    reference_range_m: float = 20_000.0
    range_cep_exponent: float = 1.2  # CEP grows as (range/ref)^exponent
    spotter_cep_factor: float = 0.4  # spotter reduces CEP to 40%
    max_range_m: float = 40_000.0
    lethal_radius_m: float = 30.0  # radius within which a round is lethal


@dataclass
class BombardmentResult:
    """Result of a naval shore bombardment mission."""

    rounds_fired: int
    impacts: list[Position] = field(default_factory=list)
    hits_in_lethal_radius: int = 0
    mean_error_m: float = 0.0


class NavalGunfireSupportEngine:
    """Naval gunfire support engine for shore bombardment.

    Parameters
    ----------
    indirect_fire_engine:
        Indirect-fire engine for reuse of dispersion patterns.
    event_bus:
        For publishing bombardment events.
    rng:
        PRNG generator.
    config:
        Tunable parameters.
    """

    def __init__(
        self,
        indirect_fire_engine: IndirectFireEngine,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: NavalGunfireSupportConfig | None = None,
    ) -> None:
        self._indirect = indirect_fire_engine
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or NavalGunfireSupportConfig()

    def shore_bombardment(
        self,
        ship_id: str,
        ship_pos: Position,
        target_pos: Position,
        gun_cep_m: float | None = None,
        round_count: int = 10,
        spotter_present: bool = False,
        timestamp: Any = None,
    ) -> BombardmentResult:
        """Execute a shore bombardment mission.

        Accuracy degrades with range (power-law CEP growth).  A forward
        observer/spotter significantly improves accuracy.

        Parameters
        ----------
        ship_id:
            Entity ID of the firing ship.
        ship_pos:
            Ship position.
        target_pos:
            Target position on shore.
        gun_cep_m:
            Gun CEP at reference range (uses config default if None).
        round_count:
            Number of rounds to fire.
        spotter_present:
            Whether a forward observer is correcting fire.
        timestamp:
            Simulation timestamp.
        """
        cfg = self._config

        dx = target_pos.easting - ship_pos.easting
        dy = target_pos.northing - ship_pos.northing
        range_m = math.sqrt(dx * dx + dy * dy)

        if gun_cep_m is None:
            gun_cep_m = cfg.base_cep_m

        # CEP degrades with range
        range_ratio = range_m / cfg.reference_range_m if cfg.reference_range_m > 0 else 1.0
        effective_cep = gun_cep_m * (range_ratio ** cfg.range_cep_exponent)

        # Spotter correction
        if spotter_present:
            effective_cep *= cfg.spotter_cep_factor

        # Convert CEP to sigma
        sigma_m = effective_cep / 1.1774

        impacts: list[Position] = []
        errors: list[float] = []
        hits = 0

        for _ in range(round_count):
            offset_e = float(self._rng.normal(0.0, sigma_m))
            offset_n = float(self._rng.normal(0.0, sigma_m))
            impact = Position(
                target_pos.easting + offset_e,
                target_pos.northing + offset_n,
                target_pos.altitude,
            )
            impacts.append(impact)
            error = math.sqrt(offset_e * offset_e + offset_n * offset_n)
            errors.append(error)
            if error <= cfg.lethal_radius_m:
                hits += 1

        mean_error = sum(errors) / len(errors) if errors else 0.0

        if timestamp is not None:
            self._event_bus.publish(ShoreBombardmentEvent(
                timestamp=timestamp, source=ModuleId.COMBAT,
                ship_id=ship_id,
                target_pos=tuple(target_pos),
                round_count=round_count,
                hits_in_lethal_radius=hits,
            ))

        logger.debug(
            "NGFS %s: %d rounds, CEP=%.0fm, %d lethal hits, mean error=%.0fm",
            ship_id, round_count, effective_cep, hits, mean_error,
        )

        return BombardmentResult(
            rounds_fired=round_count,
            impacts=impacts,
            hits_in_lethal_radius=hits,
            mean_error_m=mean_error,
        )

    def fire_support_coordination(
        self,
        ship_pos: Position,
        requesting_pos: Position,
        target_pos: Position,
        max_range_m: float | None = None,
    ) -> bool:
        """Check whether fire support is feasible.

        Verifies range from ship to target, and that the target is not
        dangerously close to the requesting unit.

        Parameters
        ----------
        ship_pos:
            Ship position.
        requesting_pos:
            Position of the unit requesting fire support.
        target_pos:
            Target position.
        max_range_m:
            Maximum gun range (uses config default if None).
        """
        if max_range_m is None:
            max_range_m = self._config.max_range_m

        # Ship-to-target range check
        dx = target_pos.easting - ship_pos.easting
        dy = target_pos.northing - ship_pos.northing
        range_to_target = math.sqrt(dx * dx + dy * dy)

        if range_to_target > max_range_m:
            logger.debug("NGFS coordination: target out of range (%.0fm > %.0fm)",
                         range_to_target, max_range_m)
            return False

        # Safety check: target-to-requester distance (danger close)
        dx2 = target_pos.easting - requesting_pos.easting
        dy2 = target_pos.northing - requesting_pos.northing
        target_requester_dist = math.sqrt(dx2 * dx2 + dy2 * dy2)

        # Minimum safe distance depends on CEP — use 2x lethal radius
        min_safe = self._config.lethal_radius_m * 2.0
        if target_requester_dist < min_safe:
            logger.debug("NGFS coordination: danger close (%.0fm < %.0fm)",
                         target_requester_dist, min_safe)
            return False

        return True

    def get_state(self) -> dict[str, Any]:
        return {"rng_state": self._rng.bit_generator.state}

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]
