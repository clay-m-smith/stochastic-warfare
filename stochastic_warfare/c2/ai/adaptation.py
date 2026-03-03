"""Plan adaptation -- detecting and responding to changed conditions.

Monitors battlefield conditions against thresholds and triggers plan
adjustments when significant changes occur: heavy casualties, dramatic
force ratio shift, supply crisis, or morale collapse. Flexible commanders
adapt more readily; rigid commanders persist with existing plans.
"""

from __future__ import annotations

import enum
from dataclasses import asdict
from datetime import datetime, timezone

import numpy as np
from pydantic import BaseModel, Field

from stochastic_warfare.c2.ai.assessment import AssessmentRating, SituationAssessment
from stochastic_warfare.c2.ai.commander import CommanderPersonality
from stochastic_warfare.c2.events import PlanAdaptedEvent
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AdaptationTrigger(enum.IntEnum):
    """Reason for plan adaptation."""

    CASUALTIES = 0
    FORCE_RATIO_CHANGE = 1
    SUPPLY_CRISIS = 2
    MORALE_BREAK = 3
    OPPORTUNITY = 4
    SURPRISE_CONTACT = 5
    C2_DISRUPTION = 6


class AdaptationAction(enum.IntEnum):
    """Action taken in response to an adaptation trigger."""

    CONTINUE = 0
    ADJUST_TEMPO = 1
    REPOSITION = 2
    REINFORCE = 3
    WITHDRAW = 4
    COUNTERATTACK = 5
    ISSUE_FRAGO = 6


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class AdaptationConfig(BaseModel):
    """Tuning parameters for plan adaptation."""

    casualty_threshold: float = Field(default=0.20, ge=0.0, le=1.0)
    """Fraction of casualties that triggers an adaptation check."""

    force_ratio_change_threshold: float = Field(default=0.50, ge=0.0)
    """Proportional change in force ratio that triggers adaptation."""

    supply_critical_threshold: float = Field(default=0.15, ge=0.0, le=1.0)
    """Supply level below which a crisis is declared."""

    morale_break_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
    """Morale level below which a morale break is declared."""

    flexibility_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    """How much commander flexibility affects adaptation probability."""


# ---------------------------------------------------------------------------
# Default personality values for when no personality is assigned
# ---------------------------------------------------------------------------

_DEFAULT_AGGRESSION = 0.5
_DEFAULT_CAUTION = 0.5
_DEFAULT_FLEXIBILITY = 0.5


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class AdaptationEngine:
    """Detects changed conditions and recommends plan adaptations.

    Parameters
    ----------
    event_bus : EventBus
        Bus for publishing :class:`PlanAdaptedEvent`.
    rng : numpy.random.Generator
        Deterministic PRNG stream for flexibility checks.
    config : AdaptationConfig | None
        Tuning parameters.  Uses defaults when ``None``.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: AdaptationConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or AdaptationConfig()
        self._previous_assessments: dict[str, SituationAssessment] = {}

    # -- Public API ---------------------------------------------------------

    def check_adaptation_needed(
        self,
        unit_id: str,
        current: SituationAssessment,
        previous: SituationAssessment | None,
        personality: CommanderPersonality | None,
        current_action: str,
        casualties_fraction: float,
        ts: datetime | None = None,
    ) -> tuple[AdaptationAction, AdaptationTrigger | None]:
        """Check whether the current situation warrants plan adaptation.

        Triggers are evaluated in priority order.  The first trigger that
        fires determines the recommended action.

        Parameters
        ----------
        unit_id : str
            The unit being evaluated.
        current : SituationAssessment
            Latest assessment for the unit.
        previous : SituationAssessment | None
            Previous assessment (if any).  When ``None``, the engine's
            internally stored previous assessment for *unit_id* is used.
        personality : CommanderPersonality | None
            Commander personality.  When ``None``, default trait values
            (0.5 for aggression, caution, flexibility) are used.
        current_action : str
            Label describing the unit's current activity.
        casualties_fraction : float
            Fraction of the unit that has become casualties (0.0--1.0).
        ts : datetime | None
            Timestamp for the event.  Defaults to UTC now.

        Returns
        -------
        tuple[AdaptationAction, AdaptationTrigger | None]
            Recommended action and the trigger that fired, or
            ``(CONTINUE, None)`` if no adaptation is needed.
        """
        if ts is None:
            ts = datetime.now(tz=timezone.utc)

        # Use internally stored previous if caller didn't supply one
        if previous is None:
            previous = self._previous_assessments.get(unit_id)

        # Extract personality traits (use defaults if None)
        aggression = personality.aggression if personality else _DEFAULT_AGGRESSION
        caution = personality.caution if personality else _DEFAULT_CAUTION
        flexibility = personality.flexibility if personality else _DEFAULT_FLEXIBILITY

        cfg = self._config
        action: AdaptationAction | None = None
        trigger: AdaptationTrigger | None = None

        # 1. CASUALTIES
        if casualties_fraction >= cfg.casualty_threshold:
            trigger = AdaptationTrigger.CASUALTIES
            if casualties_fraction > 0.4:
                action = AdaptationAction.WITHDRAW
            else:
                action = AdaptationAction.REPOSITION
            # Personality modulation
            if aggression > 0.6 and action != AdaptationAction.WITHDRAW:
                action = AdaptationAction.ADJUST_TEMPO
            elif caution > 0.6 and action == AdaptationAction.REPOSITION:
                action = AdaptationAction.WITHDRAW

        # 2. FORCE_RATIO_CHANGE
        if action is None and previous is not None:
            prev_ratio = previous.force_ratio
            cur_ratio = current.force_ratio
            denom = max(prev_ratio, 0.01)
            change = abs(cur_ratio - prev_ratio) / denom
            if change >= cfg.force_ratio_change_threshold:
                trigger = AdaptationTrigger.FORCE_RATIO_CHANGE
                if cur_ratio > prev_ratio:
                    # Ratio improved
                    if aggression > 0.6:
                        action = AdaptationAction.COUNTERATTACK
                    else:
                        action = AdaptationAction.ADJUST_TEMPO
                else:
                    # Ratio worsened
                    if caution > 0.6:
                        action = AdaptationAction.WITHDRAW
                    else:
                        action = AdaptationAction.REPOSITION

        # 3. SUPPLY_CRISIS
        if action is None and current.supply_level < cfg.supply_critical_threshold:
            trigger = AdaptationTrigger.SUPPLY_CRISIS
            if caution > 0.6:
                action = AdaptationAction.WITHDRAW
            else:
                action = AdaptationAction.REPOSITION

        # 4. MORALE_BREAK
        if action is None and current.morale_level < cfg.morale_break_threshold:
            trigger = AdaptationTrigger.MORALE_BREAK
            if caution > 0.6:
                action = AdaptationAction.WITHDRAW
            else:
                action = AdaptationAction.WITHDRAW  # morale break defaults to withdraw

        # 5. OPPORTUNITY
        if (
            action is None
            and current.overall_rating >= AssessmentRating.FAVORABLE
            and previous is not None
            and previous.overall_rating < AssessmentRating.FAVORABLE
        ):
            trigger = AdaptationTrigger.OPPORTUNITY
            if aggression > 0.6:
                action = AdaptationAction.COUNTERATTACK
            else:
                action = AdaptationAction.ADJUST_TEMPO

        # 6. SURPRISE_CONTACT
        if (
            action is None
            and current.force_ratio < 0.5
            and (previous is None or previous.force_ratio >= 1.0)
        ):
            trigger = AdaptationTrigger.SURPRISE_CONTACT
            action = AdaptationAction.ISSUE_FRAGO

        # No trigger fired
        if action is None:
            # Store current for next call
            self._previous_assessments[unit_id] = current
            return AdaptationAction.CONTINUE, None

        # Flexibility check: consider alternative action
        flex_roll = float(self._rng.random())
        if flex_roll < flexibility * cfg.flexibility_weight:
            action = self._flex_alternative(action, aggression, caution)

        # Store current as previous for next call
        self._previous_assessments[unit_id] = current

        # Publish event
        self._event_bus.publish(
            PlanAdaptedEvent(
                timestamp=ts,
                source=ModuleId.C2,
                unit_id=unit_id,
                trigger=trigger.name,
                action=action.name,
                frago_order_id="" if action != AdaptationAction.ISSUE_FRAGO else f"frago_{unit_id}",
            )
        )

        logger.debug(
            "Adaptation for %s: trigger=%s action=%s",
            unit_id,
            trigger.name,
            action.name,
        )

        return action, trigger

    # -- Flexibility helper -------------------------------------------------

    @staticmethod
    def _flex_alternative(
        base_action: AdaptationAction,
        aggression: float,
        caution: float,
    ) -> AdaptationAction:
        """Shift the base action one step toward the commander's personality.

        Aggressive commanders shift toward more aggressive alternatives;
        cautious commanders shift toward more conservative alternatives.
        """
        if aggression > caution:
            # More aggressive alternative
            alternatives = {
                AdaptationAction.WITHDRAW: AdaptationAction.REPOSITION,
                AdaptationAction.REPOSITION: AdaptationAction.ADJUST_TEMPO,
                AdaptationAction.ADJUST_TEMPO: AdaptationAction.COUNTERATTACK,
                AdaptationAction.REINFORCE: AdaptationAction.COUNTERATTACK,
            }
        else:
            # More conservative alternative
            alternatives = {
                AdaptationAction.COUNTERATTACK: AdaptationAction.ADJUST_TEMPO,
                AdaptationAction.ADJUST_TEMPO: AdaptationAction.REPOSITION,
                AdaptationAction.REPOSITION: AdaptationAction.WITHDRAW,
                AdaptationAction.REINFORCE: AdaptationAction.REPOSITION,
            }
        return alternatives.get(base_action, base_action)

    # -- State protocol -----------------------------------------------------

    def get_state(self) -> dict:
        """Serialize for checkpoint/restore."""
        prev: dict[str, dict] = {}
        for uid, sa in self._previous_assessments.items():
            d = asdict(sa)
            # Convert datetime to ISO string for serialization
            d["timestamp"] = d["timestamp"].isoformat()
            # Convert enum values to ints
            for key in (
                "force_ratio_rating",
                "terrain_rating",
                "supply_rating",
                "morale_rating",
                "intel_rating",
                "environmental_rating",
                "c2_rating",
                "overall_rating",
            ):
                d[key] = int(d[key])
            prev[uid] = d
        return {"previous_assessments": prev}

    def set_state(self, state: dict) -> None:
        """Restore from checkpoint."""
        self._previous_assessments.clear()
        for uid, d in state.get("previous_assessments", {}).items():
            d = dict(d)  # copy
            d["timestamp"] = datetime.fromisoformat(d["timestamp"])
            for key in (
                "force_ratio_rating",
                "terrain_rating",
                "supply_rating",
                "morale_rating",
                "intel_rating",
                "environmental_rating",
                "c2_rating",
                "overall_rating",
            ):
                d[key] = AssessmentRating(d[key])
            # Ensure tuples
            d["opportunities"] = tuple(d.get("opportunities", ()))
            d["threats"] = tuple(d.get("threats", ()))
            self._previous_assessments[uid] = SituationAssessment(**d)
