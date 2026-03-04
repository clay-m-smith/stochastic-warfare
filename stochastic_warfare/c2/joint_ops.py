"""Joint Task Force Command — inter-service coordination and coalition caveats.

Models the friction introduced when multiple service branches operate together
in a joint environment.  Cross-service communication incurs delay and
misinterpretation penalties; liaison officers mitigate these; coalition caveats
restrict specific nations from certain missions or areas.

Phase 12a-8.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ServiceBranch(enum.IntEnum):
    """Military service branches."""

    ARMY = 0
    NAVY = 1
    AIR_FORCE = 2
    MARINES = 3
    SPECIAL_OPERATIONS = 4


class ComponentCommand(enum.IntEnum):
    """Joint force component commands."""

    JFLCC = 0  # Joint Force Land Component Commander
    JFMCC = 1  # Joint Force Maritime Component Commander
    JFACC = 2  # Joint Force Air Component Commander
    JFSOCC = 3  # Joint Force Special Operations Component Commander


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class CoalitionCaveat(BaseModel):
    """Per-nation restrictions on operations."""

    nation: str
    restricted_mission_types: list[str] = []
    restricted_areas: list[str] = []
    max_risk_level: str = "HIGH"  # "LOW", "MODERATE", "HIGH", "EXTREME"


class JointOpsConfig(BaseModel):
    """Configuration for joint operations friction."""

    cross_service_delay_mult: float = 1.5
    cross_service_misinterpret_mult: float = 2.0
    liaison_reduction: float = 0.5
    """Fraction by which liaison officers reduce cross-service penalties."""


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class JointOpsEngine:
    """Models joint task force inter-service coordination.

    Parameters
    ----------
    config:
        Joint operations configuration.
    """

    def __init__(self, config: JointOpsConfig | None = None) -> None:
        self._config = config or JointOpsConfig()
        # unit_id → ServiceBranch
        self._unit_services: dict[str, ServiceBranch] = {}
        # unit_id → nation
        self._unit_nations: dict[str, str] = {}
        # (service_a, service_b) → liaison exists
        self._liaisons: set[tuple[int, int]] = set()
        # coalition caveats
        self._caveats: list[CoalitionCaveat] = []

    def register_unit(
        self,
        unit_id: str,
        service: ServiceBranch,
        nation: str = "US",
    ) -> None:
        """Register a unit with its service branch and nation."""
        self._unit_services[unit_id] = service
        self._unit_nations[unit_id] = nation

    def assign_liaison(
        self,
        service_a: ServiceBranch,
        service_b: ServiceBranch,
    ) -> None:
        """Assign a liaison officer between two services."""
        key = (min(int(service_a), int(service_b)),
               max(int(service_a), int(service_b)))
        self._liaisons.add(key)

    def has_liaison(
        self,
        service_a: ServiceBranch,
        service_b: ServiceBranch,
    ) -> bool:
        """Check if a liaison exists between two services."""
        key = (min(int(service_a), int(service_b)),
               max(int(service_a), int(service_b)))
        return key in self._liaisons

    def register_caveat(self, caveat: CoalitionCaveat) -> None:
        """Register a coalition caveat."""
        self._caveats.append(caveat)

    def get_coordination_modifiers(
        self,
        from_id: str,
        to_id: str,
    ) -> tuple[float, float]:
        """Get delay and misinterpretation multipliers between two units.

        Returns (delay_mult, misinterpret_mult).
        Same service = (1.0, 1.0); cross-service = higher values;
        liaison reduces by configured fraction.
        """
        from_svc = self._unit_services.get(from_id)
        to_svc = self._unit_services.get(to_id)

        if from_svc is None or to_svc is None:
            return 1.0, 1.0

        if from_svc == to_svc:
            return 1.0, 1.0

        cfg = self._config
        delay_mult = cfg.cross_service_delay_mult
        misinterpret_mult = cfg.cross_service_misinterpret_mult

        # Liaison reduces penalties
        if self.has_liaison(from_svc, to_svc):
            reduction = cfg.liaison_reduction
            delay_mult = 1.0 + (delay_mult - 1.0) * (1.0 - reduction)
            misinterpret_mult = 1.0 + (misinterpret_mult - 1.0) * (1.0 - reduction)

        return delay_mult, misinterpret_mult

    def check_caveat_compliance(
        self,
        unit_id: str,
        mission_type: str = "",
        area_id: str = "",
        risk_level: str = "MODERATE",
    ) -> tuple[bool, str]:
        """Check if a unit's nation allows the specified operation.

        Returns (compliant, reason).
        """
        nation = self._unit_nations.get(unit_id)
        if nation is None:
            return True, "no_nation_registered"

        risk_order = {"LOW": 0, "MODERATE": 1, "HIGH": 2, "EXTREME": 3}

        for caveat in self._caveats:
            if caveat.nation != nation:
                continue

            if mission_type and mission_type in caveat.restricted_mission_types:
                return False, f"mission_type_{mission_type}_restricted_for_{nation}"

            if area_id and area_id in caveat.restricted_areas:
                return False, f"area_{area_id}_restricted_for_{nation}"

            max_risk = risk_order.get(caveat.max_risk_level, 2)
            current_risk = risk_order.get(risk_level, 1)
            if current_risk > max_risk:
                return False, f"risk_level_{risk_level}_exceeds_{caveat.max_risk_level}_for_{nation}"

        return True, "compliant"

    # -- State protocol -----------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        return {
            "unit_services": {uid: int(svc) for uid, svc in self._unit_services.items()},
            "unit_nations": dict(self._unit_nations),
            "liaisons": [list(pair) for pair in sorted(self._liaisons)],
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._unit_services = {
            uid: ServiceBranch(svc) for uid, svc in state["unit_services"].items()
        }
        self._unit_nations = dict(state["unit_nations"])
        self._liaisons = {(pair[0], pair[1]) for pair in state["liaisons"]}
