"""Victory condition evaluator for campaign simulations.

Evaluates five types of victory conditions — territory control, force
destruction, time expiration, morale collapse, and supply exhaustion —
and publishes events when objectives change hands or victory is declared.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any

from pydantic import BaseModel

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.morale.state import MoraleState
from stochastic_warfare.simulation.scenario import VictoryConditionConfig

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ObjectiveType(IntEnum):
    """Type of campaign objective."""

    TERRITORY = 0
    KEY_TERRAIN = 1
    INFRASTRUCTURE = 2


class VictoryConditionType(IntEnum):
    """Types of victory condition that can end a campaign."""

    TERRITORY_CONTROL = 0
    FORCE_DESTROYED = 1
    TIME_EXPIRED = 2
    MORALE_COLLAPSED = 3
    SUPPLY_EXHAUSTED = 4
    CEASEFIRE = 5
    ARMISTICE = 6


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VictoryDeclaredEvent(Event):
    """Published when a victory condition is satisfied."""

    winning_side: str
    condition_type: str
    message: str


@dataclass(frozen=True)
class ObjectiveControlChangedEvent(Event):
    """Published when an objective changes controlling side."""

    objective_id: str
    old_side: str
    new_side: str


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class VictoryEvaluatorConfig(BaseModel):
    """Tunable thresholds for victory evaluation."""

    force_destroyed_threshold: float = 0.7
    """Fraction of units destroyed/surrendered to trigger force_destroyed."""

    morale_collapse_threshold: float = 0.6
    """Fraction of units routed/surrendered to trigger morale_collapsed."""

    supply_exhaustion_threshold: float = 0.2
    """Average supply level below which supply_exhausted triggers."""

    attrition_ratio_threshold: float = 2.0
    """Kill ratio (enemy destroyed / own destroyed) above which attrition_ratio
    victory triggers.  E.g. 2.0 = side must inflict 2x the casualties it takes."""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ObjectiveState:
    """Mutable state of a single campaign objective."""

    objective_id: str
    position: Position
    radius_m: float
    controlling_side: str = ""
    contested: bool = False


@dataclass(frozen=True)
class VictoryResult:
    """Outcome of a single victory evaluation tick."""

    game_over: bool
    winning_side: str = ""
    condition_type: str = ""
    message: str = ""
    tick: int = 0


# ---------------------------------------------------------------------------
# Victory evaluator
# ---------------------------------------------------------------------------


class VictoryEvaluator:
    """Checks campaign victory conditions each tick.

    Parameters
    ----------
    objectives:
        List of :class:`ObjectiveState` objects defining the spatial
        objectives on the map.
    conditions:
        List of :class:`VictoryConditionConfig` describing which victory
        conditions are active and what side they apply to.
    event_bus:
        EventBus for publishing victory / objective-control events.
    config:
        Tunable thresholds.  Defaults are used when ``None``.
    max_duration_s:
        Maximum campaign duration in seconds (used by ``time_expired``
        condition).  Zero means no time limit.
    """

    def __init__(
        self,
        objectives: list[ObjectiveState],
        conditions: list[VictoryConditionConfig],
        event_bus: EventBus,
        config: VictoryEvaluatorConfig | None = None,
        max_duration_s: float = 0.0,
    ) -> None:
        self._objectives: dict[str, ObjectiveState] = {
            obj.objective_id: obj for obj in objectives
        }
        self._conditions = list(conditions)
        self._event_bus = event_bus
        self._config = config or VictoryEvaluatorConfig()
        self._max_duration_s = max_duration_s

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        clock: Any,
        units_by_side: dict[str, list[Unit]],
        morale_states: dict[str, Any],
        supply_states: dict[str, float],
    ) -> VictoryResult:
        """Check all victory conditions and return the first satisfied.

        Parameters
        ----------
        clock:
            :class:`SimulationClock` (needs ``.elapsed`` and ``.tick_count``).
        units_by_side:
            Mapping of side name to list of :class:`Unit`.
        morale_states:
            Mapping of unit_id to :class:`MoraleState` (or int).
        supply_states:
            Mapping of unit_id to supply level (0.0–1.0).

        Returns
        -------
        VictoryResult
            ``game_over=True`` with details when a condition is met,
            otherwise ``game_over=False``.
        """
        tick = clock.tick_count

        for cond in self._conditions:
            result = self._check_condition(
                cond, clock, units_by_side, morale_states, supply_states, tick,
            )
            if result.game_over:
                self._event_bus.publish(
                    VictoryDeclaredEvent(
                        timestamp=clock.current_time,
                        source=ModuleId.CORE,
                        winning_side=result.winning_side,
                        condition_type=result.condition_type,
                        message=result.message,
                    )
                )
                logger.info(
                    "Victory declared: %s wins via %s — %s",
                    result.winning_side,
                    result.condition_type,
                    result.message,
                )
                return result

        return VictoryResult(game_over=False, tick=tick)

    def update_objective_control(
        self,
        units_by_side: dict[str, list[Unit]],
    ) -> None:
        """Update which side controls each objective based on unit proximity.

        For each objective, counts *active* units from each side within
        the objective's radius.  If only one side has units present, that
        side gains control.  If multiple sides are present, the objective
        is marked *contested*.  If no units are present, the previous
        controlling side is retained.
        """
        now = datetime(2024, 1, 1, tzinfo=timezone.utc)  # fallback timestamp
        for obj in self._objectives.values():
            side_counts: dict[str, int] = {}
            for side, units in units_by_side.items():
                count = 0
                for u in units:
                    if u.status != UnitStatus.ACTIVE:
                        continue
                    dist = math.sqrt(
                        (u.position.easting - obj.position.easting) ** 2
                        + (u.position.northing - obj.position.northing) ** 2
                    )
                    if dist <= obj.radius_m:
                        count += 1
                if count > 0:
                    side_counts[side] = count

            if len(side_counts) == 0:
                # No units near objective — retain previous control
                continue
            elif len(side_counts) == 1:
                new_side = next(iter(side_counts))
                old_side = obj.controlling_side
                obj.contested = False
                if new_side != old_side:
                    obj.controlling_side = new_side
                    self._event_bus.publish(
                        ObjectiveControlChangedEvent(
                            timestamp=now,
                            source=ModuleId.CORE,
                            objective_id=obj.objective_id,
                            old_side=old_side,
                            new_side=new_side,
                        )
                    )
                    logger.info(
                        "Objective %s control: %s -> %s",
                        obj.objective_id,
                        old_side,
                        new_side,
                    )
            else:
                # Multiple sides present — contested
                obj.contested = True

    def get_objective_state(self, objective_id: str) -> ObjectiveState | None:
        """Return the :class:`ObjectiveState` for *objective_id*, or ``None``."""
        return self._objectives.get(objective_id)

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        """Capture evaluator state for checkpointing."""
        return {
            "objectives": {
                oid: {
                    "objective_id": obj.objective_id,
                    "position": tuple(obj.position),
                    "radius_m": obj.radius_m,
                    "controlling_side": obj.controlling_side,
                    "contested": obj.contested,
                }
                for oid, obj in self._objectives.items()
            },
        }

    def set_state(self, state: dict) -> None:
        """Restore evaluator state from a checkpoint dict."""
        for oid, obj_data in state["objectives"].items():
            obj = self._objectives.get(oid)
            if obj is not None:
                obj.controlling_side = obj_data["controlling_side"]
                obj.contested = obj_data["contested"]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_condition(
        self,
        cond: VictoryConditionConfig,
        clock: Any,
        units_by_side: dict[str, list[Unit]],
        morale_states: dict[str, Any],
        supply_states: dict[str, float],
        tick: int,
    ) -> VictoryResult:
        """Dispatch to the appropriate condition checker."""
        ctype = cond.type
        if ctype == "territory_control":
            return self._check_territory_control(cond, units_by_side, tick)
        elif ctype == "force_destroyed":
            return self._check_force_destroyed(cond, units_by_side, tick)
        elif ctype == "time_expired":
            return self._check_time_expired(cond, clock, tick)
        elif ctype == "morale_collapsed":
            return self._check_morale_collapsed(cond, units_by_side, morale_states, tick)
        elif ctype == "supply_exhausted":
            return self._check_supply_exhausted(cond, units_by_side, supply_states, tick)
        elif ctype == "ceasefire":
            return self._check_ceasefire(cond, tick)
        elif ctype == "armistice":
            return self._check_armistice(cond, tick)
        elif ctype == "attrition_ratio":
            return self._check_attrition_ratio(cond, units_by_side, tick)
        else:
            return VictoryResult(game_over=False, tick=tick)

    def _check_ceasefire(
        self,
        cond: VictoryConditionConfig,
        tick: int,
    ) -> VictoryResult:
        """Check if a ceasefire has been activated via war termination engine.

        This is a marker condition -- the war_termination_engine activates
        ceasefire through the engine tick loop.  Here we simply acknowledge
        that the scenario supports ceasefire-type victory.
        """
        return VictoryResult(game_over=False, tick=tick)

    def _check_armistice(
        self,
        cond: VictoryConditionConfig,
        tick: int,
    ) -> VictoryResult:
        """Check if an armistice has been reached.

        Like ceasefire, this is a marker condition type.  Armistice
        transitions are driven externally by the war termination engine.
        """
        return VictoryResult(game_over=False, tick=tick)

    def _check_territory_control(
        self,
        cond: VictoryConditionConfig,
        units_by_side: dict[str, list[Unit]],
        tick: int,
    ) -> VictoryResult:
        """Check if a side controls the required fraction of objectives."""
        if not self._objectives:
            return VictoryResult(game_over=False, tick=tick)

        threshold = cond.params.get("threshold", 1.0)
        side = cond.side

        total = len(self._objectives)
        controlled = sum(
            1
            for obj in self._objectives.values()
            if obj.controlling_side == side and not obj.contested
        )

        if total > 0 and controlled / total >= threshold:
            return VictoryResult(
                game_over=True,
                winning_side=side,
                condition_type="territory_control",
                message=f"{side} controls {controlled}/{total} objectives",
                tick=tick,
            )
        return VictoryResult(game_over=False, tick=tick)

    def _check_force_destroyed(
        self,
        cond: VictoryConditionConfig,
        units_by_side: dict[str, list[Unit]],
        tick: int,
    ) -> VictoryResult:
        """Check if any side has lost >= threshold fraction of its forces."""
        threshold = self._config.force_destroyed_threshold
        winning_side = cond.side

        for side, units in units_by_side.items():
            if not units:
                continue
            destroyed = sum(
                1 for u in units
                if u.status in (UnitStatus.DESTROYED, UnitStatus.SURRENDERED)
            )
            fraction = destroyed / len(units)
            if fraction >= threshold:
                # The *losing* side has been destroyed — winner is specified
                # side or the other side.
                if winning_side:
                    winner = winning_side
                else:
                    # Find the other side(s)
                    others = [s for s in units_by_side if s != side]
                    winner = others[0] if others else side
                return VictoryResult(
                    game_over=True,
                    winning_side=winner,
                    condition_type="force_destroyed",
                    message=(
                        f"{side} lost {destroyed}/{len(units)} "
                        f"({fraction:.0%}) units"
                    ),
                    tick=tick,
                )
        return VictoryResult(game_over=False, tick=tick)

    def _check_time_expired(
        self,
        cond: VictoryConditionConfig,
        clock: Any,
        tick: int,
    ) -> VictoryResult:
        """Check if the campaign duration has been exceeded."""
        max_s = cond.params.get("max_duration_s", self._max_duration_s)
        if max_s <= 0:
            return VictoryResult(game_over=False, tick=tick)

        elapsed_s = clock.elapsed.total_seconds()
        if elapsed_s >= max_s:
            winner = cond.side or "draw"
            return VictoryResult(
                game_over=True,
                winning_side=winner,
                condition_type="time_expired",
                message=f"Campaign duration {elapsed_s:.0f}s >= limit {max_s:.0f}s",
                tick=tick,
            )
        return VictoryResult(game_over=False, tick=tick)

    def _check_morale_collapsed(
        self,
        cond: VictoryConditionConfig,
        units_by_side: dict[str, list[Unit]],
        morale_states: dict[str, Any],
        tick: int,
    ) -> VictoryResult:
        """Check if any side's morale has collectively collapsed."""
        threshold = self._config.morale_collapse_threshold
        winning_side = cond.side

        for side, units in units_by_side.items():
            if not units:
                continue
            collapsed = 0
            for u in units:
                ms = morale_states.get(u.entity_id)
                if ms is None:
                    continue
                ms_val = ms if isinstance(ms, int) else int(ms)
                if ms_val >= MoraleState.ROUTED:
                    collapsed += 1
            fraction = collapsed / len(units)
            if fraction >= threshold:
                if winning_side:
                    winner = winning_side
                else:
                    others = [s for s in units_by_side if s != side]
                    winner = others[0] if others else side
                return VictoryResult(
                    game_over=True,
                    winning_side=winner,
                    condition_type="morale_collapsed",
                    message=(
                        f"{side} morale collapsed: {collapsed}/{len(units)} "
                        f"({fraction:.0%}) routed/surrendered"
                    ),
                    tick=tick,
                )
        return VictoryResult(game_over=False, tick=tick)

    def _check_supply_exhausted(
        self,
        cond: VictoryConditionConfig,
        units_by_side: dict[str, list[Unit]],
        supply_states: dict[str, float],
        tick: int,
    ) -> VictoryResult:
        """Check if any side's average supply has dropped below threshold."""
        threshold = self._config.supply_exhaustion_threshold
        winning_side = cond.side

        for side, units in units_by_side.items():
            if not units:
                continue
            levels: list[float] = []
            for u in units:
                level = supply_states.get(u.entity_id)
                if level is not None:
                    levels.append(level)
            if not levels:
                continue
            avg = sum(levels) / len(levels)
            if avg < threshold:
                if winning_side:
                    winner = winning_side
                else:
                    others = [s for s in units_by_side if s != side]
                    winner = others[0] if others else side
                return VictoryResult(
                    game_over=True,
                    winning_side=winner,
                    condition_type="supply_exhausted",
                    message=(
                        f"{side} supply exhausted: avg {avg:.2f} "
                        f"< threshold {threshold:.2f}"
                    ),
                    tick=tick,
                )
        return VictoryResult(game_over=False, tick=tick)

    def _check_attrition_ratio(
        self,
        cond: VictoryConditionConfig,
        units_by_side: dict[str, list[Unit]],
        tick: int,
    ) -> VictoryResult:
        """Check if any side has achieved a kill ratio above threshold.

        Kill ratio = enemies destroyed / own destroyed.  A side wins when
        its ratio exceeds ``attrition_ratio_threshold`` (default 2.0) AND
        it has destroyed at least 1 enemy unit.
        """
        threshold = cond.params.get(
            "threshold", self._config.attrition_ratio_threshold,
        )
        sides = list(units_by_side.keys())

        for side in sides:
            own_units = units_by_side[side]
            own_destroyed = sum(
                1 for u in own_units
                if u.status in (UnitStatus.DESTROYED, UnitStatus.SURRENDERED)
            )
            enemy_destroyed = 0
            for other_side, other_units in units_by_side.items():
                if other_side == side:
                    continue
                enemy_destroyed += sum(
                    1 for u in other_units
                    if u.status in (UnitStatus.DESTROYED, UnitStatus.SURRENDERED)
                )

            if enemy_destroyed == 0:
                continue
            ratio = enemy_destroyed / own_destroyed if own_destroyed > 0 else float("inf")

            if ratio >= threshold:
                return VictoryResult(
                    game_over=True,
                    winning_side=side,
                    condition_type="attrition_ratio",
                    message=(
                        f"{side} achieved {ratio:.1f}:1 kill ratio "
                        f"(destroyed {enemy_destroyed}, lost {own_destroyed})"
                    ),
                    tick=tick,
                )
        return VictoryResult(game_over=False, tick=tick)

    @staticmethod
    def evaluate_force_advantage(
        units_by_side: dict[str, list[Unit]],
        *,
        morale_states: dict[str, Any] | None = None,
        weights: dict[str, float] | None = None,
    ) -> VictoryResult:
        """Evaluate which side has the force advantage.

        Used as a fallback when time expires or max ticks reached.
        Computes a composite score from force ratio, morale, and
        casualty exchange (weighted by *weights*).  Defaults to
        force-ratio-only scoring for backward compatibility.
        """
        w = weights or {}
        w_force = w.get("force_ratio", 1.0)
        w_morale = w.get("morale_ratio", 0.0)
        w_casualty = w.get("casualty_exchange", 0.0)
        total_weight = w_force + w_morale + w_casualty
        if total_weight <= 0:
            total_weight = 1.0

        best_side = ""
        best_composite = -1.0
        sides_at_best = 0
        details: list[str] = []

        for side, units in units_by_side.items():
            total = len(units)
            if total == 0:
                continue
            # Phase 41b: quality-weighted survival
            weighted_active = sum(
                getattr(u, "training_level", 0.5)
                for u in units if u.status == UnitStatus.ACTIVE
            )
            weighted_total = sum(getattr(u, "training_level", 0.5) for u in units)
            if weighted_total <= 0:
                continue
            survival = weighted_active / weighted_total
            active = sum(1 for u in units if u.status == UnitStatus.ACTIVE)

            # Morale component
            morale_score = 1.0
            if morale_states and w_morale > 0:
                routed_count = sum(
                    1 for u in units
                    if morale_states.get(u.entity_id) is not None
                    and int(morale_states.get(u.entity_id, 0)) >= MoraleState.ROUTED
                )
                morale_score = 1.0 - (routed_count / total) if total > 0 else 0.0

            # Casualty exchange component (survival as proxy)
            casualty_score = survival

            # Composite score
            composite = (
                w_force * survival
                + w_morale * morale_score
                + w_casualty * casualty_score
            ) / total_weight

            details.append(f"{side}: {active}/{total} ({composite:.0%} composite)")

            if composite > best_composite:
                best_composite = composite
                best_side = side
                sides_at_best = 1
            elif composite == best_composite:
                sides_at_best += 1

        if sides_at_best != 1 or not best_side:
            return VictoryResult(
                game_over=True,
                winning_side="draw",
                condition_type="time_expired",
                message=f"Draw — {', '.join(details)}",
            )

        return VictoryResult(
            game_over=True,
            winning_side=best_side,
            condition_type="time_expired",
            message=f"{best_side} force advantage — {', '.join(details)}",
        )
