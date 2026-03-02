"""Rules of Engagement engine.

Provides ROE levels (WEAPONS_HOLD, WEAPONS_TIGHT, WEAPONS_FREE),
target category classification, and engagement authorization checks.
Considers identification confidence and civilian proximity.

ROE rule structures and check functions only — ROE generation is
scenario data (Phase 8+).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.c2.events import RoeChangeEvent, RoeViolationEvent

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RoeLevel(enum.IntEnum):
    """Rules of engagement level."""

    WEAPONS_HOLD = 0   # Fire only in self-defense
    WEAPONS_TIGHT = 1  # Fire only at positively identified targets
    WEAPONS_FREE = 2   # Fire at any target not positively identified as friendly


class TargetCategory(enum.IntEnum):
    """Target categorization for ROE decisions."""

    MILITARY_COMBATANT = 0
    MILITARY_SUPPORT = 1
    DUAL_USE_INFRASTRUCTURE = 2
    CIVILIAN = 3
    PROTECTED_SITE = 4  # Hospitals, cultural sites
    UNKNOWN = 5


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoeAreaOverride:
    """Geographic area with a specific ROE override."""

    area_id: str
    center: Position
    radius_m: float
    roe_level: RoeLevel


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class RoeEngine:
    """Enforces Rules of Engagement.

    Parameters
    ----------
    event_bus : EventBus
        Publishes ``RoeViolationEvent`` and ``RoeChangeEvent``.
    default_level : RoeLevel
        Default ROE level for all units.
    """

    def __init__(
        self,
        event_bus: EventBus,
        default_level: RoeLevel = RoeLevel.WEAPONS_TIGHT,
    ) -> None:
        self._event_bus = event_bus
        self._default_level = default_level
        self._unit_levels: dict[str, RoeLevel] = {}
        self._area_overrides: list[RoeAreaOverride] = []
        self._civilian_proximity_threshold_m: float = 200.0
        self._min_confidence_for_tight: float = 0.7

    # -- Configuration ------------------------------------------------------

    def set_unit_roe(
        self,
        unit_id: str,
        level: RoeLevel,
        timestamp: datetime | None = None,
    ) -> None:
        """Set ROE level for a specific unit."""
        from datetime import timezone

        old = self._unit_levels.get(unit_id, self._default_level)
        self._unit_levels[unit_id] = level
        if old != level:
            ts = timestamp or datetime.now(tz=timezone.utc)
            self._event_bus.publish(RoeChangeEvent(
                timestamp=ts, source=ModuleId.C2,
                affected_unit_ids=(unit_id,),
                old_roe_level=int(old), new_roe_level=int(level),
            ))

    def set_area_override(self, override: RoeAreaOverride) -> None:
        """Add a geographic ROE override."""
        self._area_overrides.append(override)

    def get_roe_level(self, unit_id: str) -> RoeLevel:
        """Return the effective ROE level for a unit."""
        return self._unit_levels.get(unit_id, self._default_level)

    # -- Authorization check ------------------------------------------------

    def check_engagement_authorized(
        self,
        shooter_id: str,
        target_id: str,
        target_category: TargetCategory,
        id_confidence: float,
        civilian_proximity: float = float("inf"),
        target_position: Position | None = None,
        is_self_defense: bool = False,
        timestamp: datetime | None = None,
    ) -> tuple[bool, str]:
        """Check if an engagement is authorized under current ROE.

        Returns (authorized, reason).
        """
        from datetime import timezone
        import math

        ts = timestamp or datetime.now(tz=timezone.utc)

        # Get effective ROE (area override if applicable)
        roe = self.get_roe_level(shooter_id)
        if target_position is not None:
            for ov in self._area_overrides:
                dx = target_position.easting - ov.center.easting
                dy = target_position.northing - ov.center.northing
                dist = math.sqrt(dx * dx + dy * dy)
                if dist <= ov.radius_m:
                    roe = ov.roe_level
                    break

        # Protected targets are never valid
        if target_category == TargetCategory.PROTECTED_SITE:
            self._publish_violation(
                shooter_id, "protected_site_engagement", "critical", ts,
            )
            return False, "target_is_protected_site"

        # Civilian targets are never valid (even WEAPONS_FREE)
        if target_category == TargetCategory.CIVILIAN:
            self._publish_violation(
                shooter_id, "civilian_engagement", "critical", ts,
            )
            return False, "target_is_civilian"

        # Self-defense always authorized
        if is_self_defense:
            return True, "self_defense"

        # WEAPONS_HOLD: only self-defense
        if roe == RoeLevel.WEAPONS_HOLD:
            return False, "weapons_hold_no_self_defense"

        # WEAPONS_TIGHT: positive ID required
        if roe == RoeLevel.WEAPONS_TIGHT:
            if target_category == TargetCategory.UNKNOWN:
                return False, "target_not_identified"
            if id_confidence < self._min_confidence_for_tight:
                return False, "insufficient_confidence"

        # Civilian proximity check
        if civilian_proximity < self._civilian_proximity_threshold_m:
            if target_category != TargetCategory.MILITARY_COMBATANT:
                self._publish_violation(
                    shooter_id, "civilian_proximity", "major", ts,
                )
                return False, "civilian_proximity_too_close"

        # WEAPONS_FREE or TIGHT with positive ID
        return True, "authorized"

    def _publish_violation(
        self,
        unit_id: str,
        violation_type: str,
        severity: str,
        timestamp: datetime,
    ) -> None:
        self._event_bus.publish(RoeViolationEvent(
            timestamp=timestamp, source=ModuleId.C2,
            unit_id=unit_id,
            violation_type=violation_type,
            severity=severity,
        ))

    # -- State protocol -----------------------------------------------------

    def get_state(self) -> dict:
        return {
            "default_level": int(self._default_level),
            "unit_levels": {uid: int(lv) for uid, lv in self._unit_levels.items()},
            "area_overrides": [
                {
                    "area_id": ov.area_id,
                    "center": list(ov.center),
                    "radius_m": ov.radius_m,
                    "roe_level": int(ov.roe_level),
                }
                for ov in self._area_overrides
            ],
        }

    def set_state(self, state: dict) -> None:
        self._default_level = RoeLevel(state["default_level"])
        self._unit_levels = {
            uid: RoeLevel(lv) for uid, lv in state["unit_levels"].items()
        }
        self._area_overrides = [
            RoeAreaOverride(
                area_id=od["area_id"],
                center=Position(*od["center"]),
                radius_m=od["radius_m"],
                roe_level=RoeLevel(od["roe_level"]),
            )
            for od in state["area_overrides"]
        ]
