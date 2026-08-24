"""Rout, rally, and cascade mechanics.

Handles units breaking and fleeing, rally attempts, and the contagion of
routing to nearby fragile units. The former partial surrender/POW API rejects
until a runtime-owned capture lifecycle is implemented under REM-033.
"""

from __future__ import annotations

import math
import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, NoReturn

import numpy as np
from pydantic import BaseModel, ConfigDict

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.morale.events import RoutEvent

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class RoutConfig(BaseModel):
    """Configurable parameters for rout and rally mechanics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rally_base_chance: float = 0.15
    """Base probability of a routing unit rallying per check."""

    rally_friendly_bonus: float = 0.05
    """Rally probability bonus per nearby friendly unit (up to 5)."""

    rally_leader_bonus: float = 0.20
    """Rally probability bonus when a leader is present."""

    cascade_radius_m: float = 500.0
    """Maximum distance (meters) at which a routing unit can trigger cascade."""

    cascade_base_chance: float = 0.10
    """Base probability that a nearby unit is affected by cascade."""

    cascade_shaken_susceptibility: float = 1.5
    """Multiplier on cascade chance for SHAKEN units."""

    cascade_broken_susceptibility: float = 2.5
    """Multiplier on cascade chance for BROKEN units."""

    rout_speed_factor: float = 1.5
    """Speed multiplier for routing units (flee at max speed)."""


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class RoutState:
    """Tracking data for a routing unit."""

    unit_id: str
    direction_rad: float
    """Direction of flight in radians (opposite to threat)."""

    speed_factor: float
    """Speed multiplier during rout."""

    def get_state(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "direction_rad": self.direction_rad,
            "speed_factor": self.speed_factor,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self.unit_id = state["unit_id"]
        self.direction_rad = state["direction_rad"]
        self.speed_factor = state["speed_factor"]


@dataclass(frozen=True, slots=True)
class RallyPlan:
    """Immutable result of one eligible rally evaluation."""

    unit_id: str
    rallied: bool
    rallied_by: str


@dataclass(frozen=True, slots=True)
class RoutCascadeCandidate:
    """One authoritative candidate snapshot for cascade planning."""

    unit_id: str
    morale_state: int
    distance_m: float


@dataclass(frozen=True, slots=True)
class RoutCascadePlan:
    """Immutable result of one routing source's cascade selection."""

    routing_unit_id: str
    selected_unit_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _RoutStateSnapshot:
    """Immutable scalar snapshot used by the staged restore boundary."""

    unit_id: str
    direction_rad: float
    speed_factor: float


@dataclass(frozen=True, slots=True)
class RoutEngineStatePlan:
    """Validated, owner-bound active-route restore plan."""

    owner_token: object
    active_routs: tuple[tuple[str, _RoutStateSnapshot], ...]


def _validated_route_snapshot(
    unit_id: object,
    direction_rad: object,
    speed_factor: object,
) -> _RoutStateSnapshot:
    """Return one canonical immutable route snapshot or fail closed."""
    if not isinstance(unit_id, str) or not unit_id:
        raise ValueError("Active-route IDs must be non-empty strings")
    for value, label in (
        (direction_rad, "direction_rad"),
        (speed_factor, "speed_factor"),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise ValueError(
                f"Active route {unit_id!r} {label} must be finite",
            )
    direction = float(direction_rad)
    speed = float(speed_factor)
    if direction < 0.0 or direction >= 2.0 * math.pi:
        raise ValueError(
            f"Active route {unit_id!r} direction must be in [0, 2*pi)",
        )
    if speed <= 0.0:
        raise ValueError(
            f"Active route {unit_id!r} speed_factor must be positive",
        )
    return _RoutStateSnapshot(unit_id, direction, speed)


# ---------------------------------------------------------------------------
# Rout engine
# ---------------------------------------------------------------------------


class RoutEngine:
    """Handles rout initiation, rally selection, and cascade selection.

    Parameters
    ----------
    event_bus:
        EventBus for publishing direction-bearing rout events.
    rng:
        A ``numpy.random.Generator``.
    config:
        Rout configuration parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: RoutConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or RoutConfig()
        self._active_routs: dict[str, RoutState] = {}
        self._state_owner_token = object()

    @property
    def rng(self) -> np.random.Generator:
        """Return the injected authoritative MORALE generator."""
        return self._rng

    @property
    def config(self) -> RoutConfig:
        """Return the effective rout configuration."""
        return self._config

    def initiate_rout(
        self,
        unit_id: str,
        threat_direction_rad: float,
    ) -> RoutState:
        """Begin a rout — the unit flees opposite the threat direction.

        Parameters
        ----------
        unit_id:
            Identifier of the routing unit.
        threat_direction_rad:
            Direction from which the threat comes (radians).

        Returns
        -------
        RoutState
            The rout tracking data.
        """
        cfg = self._config

        # Flee opposite to threat with some random scatter
        scatter = self._rng.normal(0.0, 0.2)  # ~11 degrees scatter
        flee_direction = threat_direction_rad + math.pi + scatter
        # Normalize to [0, 2*pi)
        flee_direction = flee_direction % (2.0 * math.pi)

        rout_state = RoutState(
            unit_id=unit_id,
            direction_rad=flee_direction,
            speed_factor=cfg.rout_speed_factor,
        )
        self._active_routs[unit_id] = rout_state

        logger.info(
            "Unit %s routing — flee direction %.2f rad, speed factor %.1f",
            unit_id, flee_direction, cfg.rout_speed_factor,
        )

        self._event_bus.publish(RoutEvent(
            timestamp=datetime.now(tz=timezone.utc),
            source=ModuleId.MORALE,
            unit_id=unit_id,
            direction=flee_direction,
        ))

        return rout_state

    def plan_rally(
        self,
        unit_id: str,
        nearby_friendly_count: int,
        leader_present: bool,
    ) -> RallyPlan:
        """Consume one draw and return a side-effect-free rally plan.

        Parameters
        ----------
        unit_id:
            Identifier of the routing unit.
        nearby_friendly_count:
            Number of friendly units nearby.
        leader_present:
            Whether a leader is present to rally the unit.

        Returns
        -------
        RallyPlan
            Immutable selection result. Semantic commit and events belong to
            :class:`~stochastic_warfare.morale.runtime.MoraleRuntime`.
        """
        if not isinstance(unit_id, str) or not unit_id:
            raise ValueError("Rally unit_id must be a non-empty string")
        if (
            isinstance(nearby_friendly_count, bool)
            or not isinstance(nearby_friendly_count, int)
            or nearby_friendly_count < 0
        ):
            raise ValueError(
                "nearby_friendly_count must be a non-negative integer",
            )
        if not isinstance(leader_present, bool):
            raise TypeError("leader_present must be a boolean")
        cfg = self._config

        rally_chance = cfg.rally_base_chance
        rally_chance += cfg.rally_friendly_bonus * min(nearby_friendly_count, 5)
        if leader_present:
            rally_chance += cfg.rally_leader_bonus
        rally_chance = min(rally_chance, 0.95)

        roll = self._rng.random()
        rallied = roll < rally_chance
        return RallyPlan(
            unit_id=unit_id,
            rallied=rallied,
            rallied_by="leader" if leader_present and rallied else "",
        )

    def check_rally(
        self,
        unit_id: str,
        nearby_friendly_count: int,
        leader_present: bool,
    ) -> bool:
        """Reject the former partial semantic API explicitly.

        Call :meth:`plan_rally` for side-effect-free selection or
        :meth:`MoraleRuntime.check_rally
        <stochastic_warfare.morale.runtime.MoraleRuntime.check_rally>` for the
        authoritative state/status/route/event transaction.
        """
        raise RuntimeError(
            "RoutEngine.check_rally cannot commit authoritative morale; use "
            "MoraleRuntime.check_rally or RoutEngine.plan_rally",
        )

    def process_surrender(
        self,
        unit_id: str,
        personnel_count: int,
        capturing_side: str,
    ) -> NoReturn:
        """Reject the former partial surrender/POW semantic API.

        A rout owner cannot commit the authoritative morale record or bound
        unit status, and the production runtime has no typed captor/POW
        lifecycle.  Stochastic ``SURRENDERED`` transitions are coordinated by
        :class:`~stochastic_warfare.morale.runtime.MoraleRuntime`; REM-033 owns
        the missing capture and prisoner-processing boundary.
        """
        raise RuntimeError(
            "RoutEngine.process_surrender cannot commit authoritative morale; "
            "SURRENDERED transitions belong to MoraleRuntime and POW capture "
            "is unsupported until REM-033",
        )

    def plan_cascade(
        self,
        routing_unit_id: str,
        candidates: Sequence[RoutCascadeCandidate],
    ) -> RoutCascadePlan:
        """Consume prescribed draws and return a side-effect-free batch plan.

        Parameters
        ----------
        routing_unit_id:
            The unit that is routing (source of cascade).
        candidates:
            Complete authoritative candidate snapshot. Candidate IDs are
            validated for uniqueness, then processed lexicographically.

        Returns
        -------
        RoutCascadePlan
            Selected IDs in canonical candidate order.
        """
        if not isinstance(routing_unit_id, str) or not routing_unit_id:
            raise ValueError(
                "Cascade routing_unit_id must be a non-empty string",
            )
        staged: list[RoutCascadeCandidate] = []
        seen: set[str] = set()
        for candidate in candidates:
            if not isinstance(candidate, RoutCascadeCandidate):
                raise TypeError(
                    "Cascade candidates must be RoutCascadeCandidate values",
                )
            if not candidate.unit_id:
                raise ValueError("Cascade candidate IDs must be non-empty")
            if candidate.unit_id in seen:
                raise ValueError(
                    f"Duplicate cascade candidate {candidate.unit_id!r}",
                )
            if (
                isinstance(candidate.morale_state, bool)
                or not isinstance(candidate.morale_state, int)
            ):
                raise ValueError(
                    "Cascade candidate morale_state must be an integer",
                )
            if (
                isinstance(candidate.distance_m, bool)
                or not isinstance(candidate.distance_m, (int, float))
                or not math.isfinite(float(candidate.distance_m))
                or float(candidate.distance_m) < 0.0
            ):
                raise ValueError(
                    "Cascade candidate distance must be finite and non-negative",
                )
            seen.add(candidate.unit_id)
            staged.append(candidate)

        cfg = self._config
        cascaded: list[str] = []

        for candidate in sorted(staged, key=lambda item: item.unit_id):
            uid = candidate.unit_id
            morale_state = candidate.morale_state
            if uid == routing_unit_id:
                continue

            distance = float(candidate.distance_m)
            if distance > cfg.cascade_radius_m:
                continue

            # Only SHAKEN (1) and BROKEN (2) units are susceptible
            if morale_state == 1:
                susceptibility = cfg.cascade_shaken_susceptibility
            elif morale_state == 2:
                susceptibility = cfg.cascade_broken_susceptibility
            else:
                continue

            # Distance attenuation
            distance_factor = 1.0 - (distance / cfg.cascade_radius_m)
            cascade_prob = cfg.cascade_base_chance * susceptibility * distance_factor

            roll = self._rng.random()
            if roll < cascade_prob:
                cascaded.append(uid)
                logger.debug(
                    "Cascade: unit %s triggered rout in unit %s (prob=%.3f)",
                    routing_unit_id, uid, cascade_prob,
                )

        return RoutCascadePlan(
            routing_unit_id=routing_unit_id,
            selected_unit_ids=tuple(cascaded),
        )

    def rout_cascade(
        self,
        routing_unit_id: str,
        adjacent_unit_morale_states: Mapping[str, int],
        distances_m: Mapping[str, float],
    ) -> list[str]:
        """Compatibility selector returning the side-effect-free plan IDs."""
        candidates = tuple(
            RoutCascadeCandidate(
                unit_id=uid,
                morale_state=morale_state,
                distance_m=distances_m.get(uid, float("inf")),
            )
            for uid, morale_state in adjacent_unit_morale_states.items()
        )
        return list(
            self.plan_cascade(
                routing_unit_id,
                candidates,
            ).selected_unit_ids,
        )

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        return {
            "active_routs": {
                uid: rs.get_state()
                for uid, rs in sorted(self._active_routs.items())
            },
        }

    def stage_state(
        self,
        state: Mapping[str, Any],
        *,
        expected_routing_unit_ids: set[str] | None = None,
    ) -> RoutEngineStatePlan:
        """Validate active-route state without mutating routes or RNG."""
        if not isinstance(state, Mapping) or set(state) != {"active_routs"}:
            raise ValueError(
                "RoutEngine state must contain exactly active_routs",
            )
        raw_routs = state["active_routs"]
        if not isinstance(raw_routs, Mapping):
            raise ValueError("active_routs must be a mapping")
        staged: list[tuple[str, _RoutStateSnapshot]] = []
        for uid in sorted(raw_routs):
            if not isinstance(uid, str) or not uid:
                raise ValueError("Active-route IDs must be non-empty strings")
            raw_route = raw_routs[uid]
            if not isinstance(raw_route, Mapping):
                raise ValueError(f"Active route {uid!r} must be a mapping")
            if set(raw_route) != {"unit_id", "direction_rad", "speed_factor"}:
                raise ValueError(f"Active route {uid!r} has invalid fields")
            if raw_route["unit_id"] != uid:
                raise ValueError(f"Active route key/payload disagree for {uid!r}")
            staged.append((
                uid,
                _validated_route_snapshot(
                    uid,
                    raw_route["direction_rad"],
                    raw_route["speed_factor"],
                ),
            ))
        staged_ids = {uid for uid, _ in staged}
        if (
            expected_routing_unit_ids is not None
            and not staged_ids <= expected_routing_unit_ids
        ):
            raise ValueError(
                "Active routes contain units without authoritative routed state: "
                f"{sorted(staged_ids - expected_routing_unit_ids)!r}",
            )
        return RoutEngineStatePlan(
            owner_token=self._state_owner_token,
            active_routs=tuple(staged),
        )

    def commit_state(self, plan: RoutEngineStatePlan) -> None:
        """Commit a validated route plan in place without touching RNG."""
        if not isinstance(plan, RoutEngineStatePlan):
            raise TypeError("plan must be a RoutEngineStatePlan")
        if plan.owner_token is not self._state_owner_token:
            raise ValueError("RoutEngine state plan belongs to another runtime")
        if not isinstance(plan.active_routs, tuple) or any(
            not isinstance(entry, tuple) or len(entry) != 2
            for entry in plan.active_routs
        ):
            raise ValueError(
                "RoutEngine state plan requires canonical unique routes",
            )
        route_ids = tuple(uid for uid, _route in plan.active_routs)
        if route_ids != tuple(sorted(set(route_ids))):
            raise ValueError(
                "RoutEngine state plan requires canonical unique routes",
            )
        staged: list[tuple[str, _RoutStateSnapshot]] = []
        for uid, route in plan.active_routs:
            if not isinstance(route, _RoutStateSnapshot) or route.unit_id != uid:
                raise ValueError(
                    "RoutEngine state plan requires canonical unique routes",
                )
            staged.append((
                uid,
                _validated_route_snapshot(
                    uid,
                    route.direction_rad,
                    route.speed_factor,
                ),
            ))
        replacement = {
            uid: RoutState(
                unit_id=route.unit_id,
                direction_rad=route.direction_rad,
                speed_factor=route.speed_factor,
            )
            for uid, route in staged
        }
        self._active_routs.clear()
        self._active_routs.update(replacement)

    def set_state(
        self,
        state: Mapping[str, Any],
        *,
        expected_routing_unit_ids: set[str] | None = None,
    ) -> None:
        """Validate and restore active routes in place without touching RNG."""
        self.commit_state(
            self.stage_state(
                state,
                expected_routing_unit_ids=expected_routing_unit_ids,
            ),
        )

    def _active_rout_snapshot(self, unit_id: str) -> RoutState | None:
        route = self._active_routs.get(unit_id)
        return copy.deepcopy(route) if route is not None else None

    def _remove_active_rout(self, unit_id: str) -> None:
        self._active_routs.pop(unit_id, None)

    def _restore_active_rout(
        self,
        unit_id: str,
        route: RoutState | None,
    ) -> None:
        if route is None:
            self._active_routs.pop(unit_id, None)
        else:
            self._active_routs[unit_id] = copy.deepcopy(route)
