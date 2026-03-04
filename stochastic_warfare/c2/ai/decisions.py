"""Decision logic -- echelon-appropriate tactical decisions.

Dispatches to echelon-specific decision functions that evaluate options
based on situation assessment, commander personality, and doctrine.
Each echelon level has different available actions and decision-making
style.  No global optimization -- locally reasonable decisions guided by
personality noise and weighted scoring.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from stochastic_warfare.c2.ai.assessment import AssessmentRating, SituationAssessment
from stochastic_warfare.c2.ai.commander import CommanderPersonality
from stochastic_warfare.c2.ai.doctrine import DoctrineTemplate
from stochastic_warfare.c2.events import DecisionMadeEvent
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DecisionCategory(enum.IntEnum):
    """High-level decision category."""

    OFFENSIVE = 0
    DEFENSIVE = 1
    MOVEMENT = 2
    SUPPORT = 3
    C2 = 4


class IndividualAction(enum.IntEnum):
    """Actions available to individual soldiers and fire teams."""

    HOLD_POSITION = 0
    ADVANCE = 1
    RETREAT = 2
    TAKE_COVER = 3
    ENGAGE = 4
    SEEK_COVER = 5


class SmallUnitAction(enum.IntEnum):
    """Actions available to squads and platoons."""

    ATTACK = 0
    DEFEND = 1
    BOUND_FORWARD = 2
    WITHDRAW = 3
    FLANK = 4
    AMBUSH = 5
    RECON = 6
    SUPPORT_BY_FIRE = 7


class CompanyBnAction(enum.IntEnum):
    """Actions available to companies and battalions."""

    ATTACK = 0
    DEFEND = 1
    DELAY = 2
    COUNTERATTACK = 3
    BYPASS = 4
    FIX = 5
    ENVELOP = 6
    WITHDRAW = 7
    CONSOLIDATE = 8
    RESERVE = 9


class BrigadeDivAction(enum.IntEnum):
    """Actions available to brigades and divisions."""

    ATTACK = 0
    DEFEND = 1
    DELAY = 2
    COUNTERATTACK = 3
    EXPLOIT = 4
    PURSUE = 5
    RETROGRADE = 6
    PASSAGE_OF_LINES = 7
    RELIEF_IN_PLACE = 8
    RESERVE = 9


class CorpsAction(enum.IntEnum):
    """Actions available to corps and above."""

    MAIN_ATTACK = 0
    SUPPORTING_ATTACK = 1
    DEFEND = 2
    DEEP_STRIKE = 3
    OPERATIONAL_MANEUVER = 4
    RESERVE = 5
    TRANSITION = 6


# ---------------------------------------------------------------------------
# Action → category mapping (module-level, hoisted)
# ---------------------------------------------------------------------------

_OFFENSIVE_NAMES: frozenset[str] = frozenset({
    "ADVANCE", "ENGAGE", "ATTACK", "COUNTERATTACK", "FLANK", "AMBUSH",
    "ENVELOP", "EXPLOIT", "PURSUE", "MAIN_ATTACK", "SUPPORTING_ATTACK",
    "DEEP_STRIKE", "OPERATIONAL_MANEUVER", "BOUND_FORWARD",
    "SUPPORT_BY_FIRE", "BYPASS", "FIX",
})

_DEFENSIVE_NAMES: frozenset[str] = frozenset({
    "HOLD_POSITION", "TAKE_COVER", "SEEK_COVER", "RETREAT", "DEFEND",
    "WITHDRAW", "DELAY", "RETROGRADE", "CONSOLIDATE", "RESERVE",
    "RELIEF_IN_PLACE",
})

_MOVEMENT_NAMES: frozenset[str] = frozenset({
    "PASSAGE_OF_LINES", "RECON",
})

_C2_NAMES: frozenset[str] = frozenset({
    "TRANSITION",
})


def _categorize_action(name: str) -> DecisionCategory:
    """Determine the :class:`DecisionCategory` for an action name."""
    if name in _OFFENSIVE_NAMES:
        return DecisionCategory.OFFENSIVE
    if name in _DEFENSIVE_NAMES:
        return DecisionCategory.DEFENSIVE
    if name in _MOVEMENT_NAMES:
        return DecisionCategory.MOVEMENT
    if name in _C2_NAMES:
        return DecisionCategory.C2
    return DecisionCategory.SUPPORT


# ---------------------------------------------------------------------------
# Echelon-specific action enum lookup
# ---------------------------------------------------------------------------

# EchelonLevel constants (avoid import cycle -- use raw ints)
_FIRE_TEAM = 1
_PLATOON = 4
_BATTALION = 6
_DIVISION = 9

_INDIVIDUAL_ENUM = IndividualAction
_SMALL_UNIT_ENUM = SmallUnitAction
_COMPANY_BN_ENUM = CompanyBnAction
_BRIGADE_DIV_ENUM = BrigadeDivAction
_CORPS_ENUM = CorpsAction


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DecisionResult:
    """Immutable snapshot of a decision."""

    unit_id: str
    echelon_level: int
    decision_category: DecisionCategory
    action: int  # enum value from echelon-specific enum
    action_name: str  # string name of the action
    confidence: float  # 0--1
    rationale: str  # brief explanation
    timestamp: datetime


# ---------------------------------------------------------------------------
# Default personality (balanced)
# ---------------------------------------------------------------------------

_DEFAULT_PERSONALITY = CommanderPersonality(
    profile_id="_default",
    display_name="Default",
    description="Balanced default personality",
    aggression=0.5,
    caution=0.5,
    flexibility=0.5,
    initiative=0.5,
    experience=0.5,
    stress_tolerance=0.5,
    decision_speed=0.5,
    risk_acceptance=0.5,
)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class DecisionEngine:
    """Echelon-dispatched decision engine.

    Parameters
    ----------
    event_bus : EventBus
        Bus for publishing :class:`DecisionMadeEvent`.
    rng : numpy.random.Generator
        Deterministic PRNG stream for decision noise.
    """

    def __init__(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._decision_count: int = 0

    # -- Public API ---------------------------------------------------------

    def decide(
        self,
        unit_id: str,
        echelon: int,
        assessment: SituationAssessment,
        personality: CommanderPersonality | None,
        doctrine: DoctrineTemplate | None,
        current_orders_mission: int | None = None,
        roe_level: int = 1,
        comms_available: bool = True,
        ts: datetime | None = None,
        school_adjustments: dict[str, float] | None = None,
    ) -> DecisionResult:
        """Produce an echelon-appropriate decision.

        Parameters
        ----------
        unit_id : str
            The deciding unit.
        echelon : int
            Echelon level (``EchelonLevel`` int value).
        assessment : SituationAssessment
            Current situation assessment.
        personality : CommanderPersonality | None
            Commander personality; uses balanced defaults when ``None``.
        doctrine : DoctrineTemplate | None
            Active doctrine; all actions allowed when ``None``.
        current_orders_mission : int | None
            Current mission type (enum value) for context, or ``None``.
        roe_level : int
            Rules of engagement level (``RoeLevel`` int value, default 1 = WEAPONS_TIGHT).
        comms_available : bool
            Whether C2 comms are currently functional.
        ts : datetime | None
            Timestamp; defaults to UTC now.
        school_adjustments : dict[str, float] | None
            Additive score adjustments from a doctrinal school.
            Applied after doctrine filtering and before noise.
            ``None`` means no school adjustments.

        Returns
        -------
        DecisionResult
            Frozen decision snapshot.
        """
        if ts is None:
            ts = datetime.now(tz=timezone.utc)

        p = personality if personality is not None else _DEFAULT_PERSONALITY

        if echelon <= _FIRE_TEAM:
            result = self._decide_individual(unit_id, assessment, p, roe_level, ts, school_adjustments)
        elif echelon <= _PLATOON:
            result = self._decide_small_unit(
                unit_id, assessment, p, doctrine, roe_level, current_orders_mission, ts, school_adjustments,
            )
        elif echelon <= _BATTALION:
            result = self._decide_company_bn(
                unit_id, assessment, p, doctrine, roe_level, ts, school_adjustments,
            )
        elif echelon <= _DIVISION:
            result = self._decide_brigade_div(
                unit_id, echelon, assessment, p, doctrine, roe_level, ts, school_adjustments,
            )
        else:
            result = self._decide_corps_plus(
                unit_id, assessment, p, doctrine, roe_level, ts, school_adjustments,
            )

        # Publish event
        self._event_bus.publish(
            DecisionMadeEvent(
                timestamp=ts,
                source=ModuleId.C2,
                unit_id=unit_id,
                decision_type=result.action_name,
                echelon_level=echelon,
                confidence=result.confidence,
            )
        )

        self._decision_count += 1

        logger.debug(
            "Decision for %s (echelon=%d): %s (confidence=%.2f)",
            unit_id,
            echelon,
            result.action_name,
            result.confidence,
        )

        return result

    # -- Individual / fire team ---------------------------------------------

    def _decide_individual(
        self,
        unit_id: str,
        assessment: SituationAssessment,
        personality: CommanderPersonality,
        roe_level: int,
        ts: datetime,
        school_adjustments: dict[str, float] | None = None,
    ) -> DecisionResult:
        scores: dict[str, float] = {}

        fr = assessment.force_ratio
        morale = assessment.morale_level
        supply = assessment.supply_level

        scores["HOLD_POSITION"] = 0.3
        scores["ADVANCE"] = (
            0.2
            + personality.aggression * 0.3
            + (0.2 if fr > 1.5 else 0.0)
        )
        scores["RETREAT"] = (
            0.1
            + personality.caution * 0.3
            + (0.3 if fr < 0.5 or morale < 0.3 else 0.0)
        )
        scores["TAKE_COVER"] = (
            0.2
            + personality.caution * 0.2
            + (0.2 if "severe_weather" in assessment.threats else 0.0)
        )
        scores["ENGAGE"] = (
            0.2
            + personality.aggression * 0.3
            + (0.3 if roe_level >= 2 and fr > 0.8 else 0.0)  # WEAPONS_FREE = 2
        )
        scores["SEEK_COVER"] = (
            0.1
            + (0.4 if supply < 0.2 or morale < 0.2 else 0.0)
        )

        # WEAPONS_HOLD blocks ENGAGE
        if roe_level == 0:  # WEAPONS_HOLD
            scores["ENGAGE"] = 0.0

        # Morale modifiers
        if morale > 0.7:
            scores["ADVANCE"] += 0.1
            scores["ENGAGE"] += 0.1
        if morale < 0.3:
            scores["RETREAT"] += 0.15
            scores["SEEK_COVER"] += 0.1

        return self._select_best(
            unit_id=unit_id,
            echelon_level=0,  # INDIVIDUAL range
            scores=scores,
            personality=personality,
            assessment=assessment,
            action_enum=_INDIVIDUAL_ENUM,
            doctrine=None,  # individual doesn't use doctrine
            ts=ts,
            school_adjustments=school_adjustments,
        )

    # -- Squad / platoon ----------------------------------------------------

    def _decide_small_unit(
        self,
        unit_id: str,
        assessment: SituationAssessment,
        personality: CommanderPersonality,
        doctrine: DoctrineTemplate | None,
        roe_level: int,
        current_orders_mission: int | None,
        ts: datetime,
        school_adjustments: dict[str, float] | None = None,
    ) -> DecisionResult:
        scores: dict[str, float] = {}

        fr = assessment.force_ratio
        morale = assessment.morale_level
        terrain = assessment.terrain_advantage
        intel = assessment.intel_quality
        overall = assessment.overall_rating

        scores["ATTACK"] = (
            personality.aggression * 0.4
            + (0.3 if fr > 1.5 else 0.0)
            + (0.2 if overall >= AssessmentRating.FAVORABLE else 0.0)
        )
        scores["DEFEND"] = (
            personality.caution * 0.3
            + (0.3 if terrain > 0.2 else 0.0)
            + (0.2 if fr < 1.0 else 0.0)
        )
        scores["BOUND_FORWARD"] = (
            0.2
            + (0.3 if current_orders_mission is not None else 0.0)
        )
        scores["WITHDRAW"] = (
            personality.caution * 0.2
            + (0.4 if fr < 0.4 or morale < 0.3 else 0.0)
        )
        scores["FLANK"] = (
            personality.aggression * 0.2
            + personality.flexibility * 0.2
            + (0.2 if terrain > 0.0 else 0.0)
        )
        scores["AMBUSH"] = (
            0.1
            + (0.3 if terrain > 0.3 and fr < 1.5 else 0.0)
        )
        scores["RECON"] = (
            0.15
            + (0.3 if intel < 0.3 else 0.0)
        )
        scores["SUPPORT_BY_FIRE"] = (
            0.15
            + (0.2 if "numerical_superiority" in assessment.opportunities else 0.0)
        )

        # ROE blocks offensive actions
        if roe_level == 0:  # WEAPONS_HOLD
            scores["ATTACK"] *= 0.2
            scores["AMBUSH"] *= 0.2

        # Morale modifiers
        if morale > 0.7:
            scores["ATTACK"] += 0.1
            scores["FLANK"] += 0.05
        if morale < 0.3:
            scores["WITHDRAW"] += 0.2
            scores["DEFEND"] += 0.1

        # Supply critical → conservative
        if assessment.supply_level < 0.2:
            scores["DEFEND"] += 0.2
            scores["WITHDRAW"] += 0.15
            scores["ATTACK"] *= 0.5

        return self._select_best(
            unit_id=unit_id,
            echelon_level=4,  # PLATOON range
            scores=scores,
            personality=personality,
            assessment=assessment,
            action_enum=_SMALL_UNIT_ENUM,
            doctrine=doctrine,
            ts=ts,
            school_adjustments=school_adjustments,
        )

    # -- Company / battalion ------------------------------------------------

    def _decide_company_bn(
        self,
        unit_id: str,
        assessment: SituationAssessment,
        personality: CommanderPersonality,
        doctrine: DoctrineTemplate | None,
        roe_level: int,
        ts: datetime,
        school_adjustments: dict[str, float] | None = None,
    ) -> DecisionResult:
        scores: dict[str, float] = {}

        fr = assessment.force_ratio
        morale = assessment.morale_level
        supply = assessment.supply_level
        c2 = assessment.c2_effectiveness
        terrain = assessment.terrain_advantage
        overall = assessment.overall_rating

        scores["ATTACK"] = (
            personality.aggression * 0.3
            + (0.3 if fr > 1.5 else 0.0)
            + (0.2 if overall >= AssessmentRating.FAVORABLE else 0.0)
        )
        scores["DEFEND"] = (
            personality.caution * 0.3
            + (0.3 if terrain > 0.2 else 0.0)
            + (0.2 if fr < 1.0 else 0.0)
        )
        scores["DELAY"] = (
            0.1
            + personality.caution * 0.2
            + (0.3 if fr < 0.6 else 0.0)
        )
        scores["COUNTERATTACK"] = (
            personality.aggression * 0.3
            + personality.initiative * 0.2
            + (0.2 if overall >= AssessmentRating.FAVORABLE else 0.0)
        )
        scores["BYPASS"] = (
            0.1
            + personality.flexibility * 0.2
            + (0.2 if terrain < -0.2 else 0.0)
        )
        scores["FIX"] = (
            0.15
            + (0.2 if 0.8 <= fr <= 1.5 else 0.0)
        )
        scores["ENVELOP"] = (
            personality.aggression * 0.2
            + personality.flexibility * 0.2
            + (0.2 if fr > 1.5 else 0.0)
        )
        scores["WITHDRAW"] = (
            personality.caution * 0.2
            + (0.4 if fr < 0.4 or morale < 0.3 else 0.0)
        )
        scores["CONSOLIDATE"] = (
            0.1
            + (0.3 if supply < 0.3 and overall >= AssessmentRating.NEUTRAL else 0.0)
        )
        scores["RESERVE"] = (
            0.1
            + (0.3 if 0.7 <= fr <= 1.3 else 0.0)
            + (0.1 if c2 > 0.7 else 0.0)
        )

        # ROE blocks offensive actions
        if roe_level == 0:  # WEAPONS_HOLD
            scores["ATTACK"] *= 0.2
            scores["COUNTERATTACK"] *= 0.2
            scores["ENVELOP"] *= 0.2

        # Morale modifiers
        if morale > 0.7:
            scores["ATTACK"] += 0.1
            scores["COUNTERATTACK"] += 0.1
        if morale < 0.3:
            scores["WITHDRAW"] += 0.2
            scores["DELAY"] += 0.15
            scores["DEFEND"] += 0.1

        # Supply critical → conservative
        if supply < 0.2:
            scores["DEFEND"] += 0.2
            scores["WITHDRAW"] += 0.15
            scores["CONSOLIDATE"] += 0.15
            scores["ATTACK"] *= 0.5
            scores["COUNTERATTACK"] *= 0.5

        # C2 modifiers
        if c2 < 0.3:
            scores["DEFEND"] += 0.15
            scores["RESERVE"] += 0.1

        return self._select_best(
            unit_id=unit_id,
            echelon_level=6,  # BATTALION range
            scores=scores,
            personality=personality,
            assessment=assessment,
            action_enum=_COMPANY_BN_ENUM,
            doctrine=doctrine,
            ts=ts,
            school_adjustments=school_adjustments,
        )

    # -- Brigade / division -------------------------------------------------

    def _decide_brigade_div(
        self,
        unit_id: str,
        echelon: int,
        assessment: SituationAssessment,
        personality: CommanderPersonality,
        doctrine: DoctrineTemplate | None,
        roe_level: int,
        ts: datetime,
        school_adjustments: dict[str, float] | None = None,
    ) -> DecisionResult:
        scores: dict[str, float] = {}

        fr = assessment.force_ratio
        morale = assessment.morale_level
        supply = assessment.supply_level
        c2 = assessment.c2_effectiveness
        terrain = assessment.terrain_advantage
        overall = assessment.overall_rating

        scores["ATTACK"] = (
            personality.aggression * 0.3
            + (0.3 if fr > 1.5 else 0.0)
            + (0.2 if overall >= AssessmentRating.FAVORABLE else 0.0)
        )
        scores["DEFEND"] = (
            personality.caution * 0.3
            + (0.3 if terrain > 0.2 else 0.0)
            + (0.2 if fr < 1.0 else 0.0)
        )
        scores["DELAY"] = (
            0.1
            + personality.caution * 0.2
            + (0.3 if fr < 0.6 else 0.0)
        )
        scores["COUNTERATTACK"] = (
            personality.aggression * 0.2
            + personality.initiative * 0.2
            + (0.2 if overall >= AssessmentRating.FAVORABLE else 0.0)
        )
        scores["EXPLOIT"] = (
            personality.aggression * 0.2
            + (0.4 if fr > 2.5 else 0.0)
            + (0.2 if overall >= AssessmentRating.VERY_FAVORABLE else 0.0)
        )
        scores["PURSUE"] = (
            personality.aggression * 0.2
            + (0.4 if fr > 3.0 else 0.0)
            + (0.1 if morale > 0.7 else 0.0)
        )
        scores["RETROGRADE"] = (
            personality.caution * 0.2
            + (0.4 if fr < 0.4 else 0.0)
            + (0.2 if morale < 0.3 else 0.0)
        )
        scores["PASSAGE_OF_LINES"] = (
            0.05
            + (0.2 if c2 > 0.7 else 0.0)
        )
        scores["RELIEF_IN_PLACE"] = (
            0.05
            + (0.2 if supply < 0.3 else 0.0)
            + (0.1 if morale < 0.4 else 0.0)
        )
        scores["RESERVE"] = (
            0.1
            + (0.2 if 0.7 <= fr <= 1.3 else 0.0)
        )

        # ROE blocks offensive actions
        if roe_level == 0:  # WEAPONS_HOLD
            scores["ATTACK"] *= 0.2
            scores["COUNTERATTACK"] *= 0.2
            scores["EXPLOIT"] *= 0.2
            scores["PURSUE"] *= 0.2

        # Morale modifiers
        if morale > 0.7:
            scores["ATTACK"] += 0.1
            scores["EXPLOIT"] += 0.1
            scores["PURSUE"] += 0.05
        if morale < 0.3:
            scores["RETROGRADE"] += 0.2
            scores["DELAY"] += 0.15
            scores["DEFEND"] += 0.1

        # Supply critical → conservative
        if supply < 0.2:
            scores["DEFEND"] += 0.2
            scores["RETROGRADE"] += 0.15
            scores["ATTACK"] *= 0.5
            scores["EXPLOIT"] *= 0.5

        return self._select_best(
            unit_id=unit_id,
            echelon_level=echelon,
            scores=scores,
            personality=personality,
            assessment=assessment,
            action_enum=_BRIGADE_DIV_ENUM,
            doctrine=doctrine,
            ts=ts,
            school_adjustments=school_adjustments,
        )

    # -- Corps and above ----------------------------------------------------

    def _decide_corps_plus(
        self,
        unit_id: str,
        assessment: SituationAssessment,
        personality: CommanderPersonality,
        doctrine: DoctrineTemplate | None,
        roe_level: int,
        ts: datetime,
        school_adjustments: dict[str, float] | None = None,
    ) -> DecisionResult:
        scores: dict[str, float] = {}

        fr = assessment.force_ratio
        morale = assessment.morale_level
        supply = assessment.supply_level
        c2 = assessment.c2_effectiveness
        intel = assessment.intel_quality
        overall = assessment.overall_rating

        scores["MAIN_ATTACK"] = (
            personality.aggression * 0.3
            + (0.3 if fr > 1.5 else 0.0)
            + (0.2 if overall >= AssessmentRating.FAVORABLE else 0.0)
        )
        scores["SUPPORTING_ATTACK"] = (
            0.15
            + personality.aggression * 0.15
            + (0.2 if fr > 1.2 else 0.0)
        )
        scores["DEFEND"] = (
            personality.caution * 0.3
            + (0.3 if fr < 1.0 else 0.0)
            + (0.2 if supply < 0.3 else 0.0)
        )
        scores["DEEP_STRIKE"] = (
            personality.aggression * 0.2
            + (0.3 if intel > 0.7 else 0.0)
            + (0.2 if c2 > 0.7 else 0.0)
        )
        scores["OPERATIONAL_MANEUVER"] = (
            personality.flexibility * 0.2
            + (0.2 if fr > 1.5 else 0.0)
            + (0.2 if c2 > 0.7 else 0.0)
        )
        scores["RESERVE"] = (
            0.1
            + (0.2 if 0.7 <= fr <= 1.3 else 0.0)
        )
        scores["TRANSITION"] = (
            0.05
            + (0.5 if overall >= AssessmentRating.VERY_FAVORABLE and fr > 3.0 else 0.0)
            + (0.15 if supply > 0.7 and morale > 0.7 else 0.0)
        )

        # ROE blocks offensive actions
        if roe_level == 0:  # WEAPONS_HOLD
            scores["MAIN_ATTACK"] *= 0.2
            scores["SUPPORTING_ATTACK"] *= 0.2
            scores["DEEP_STRIKE"] *= 0.2

        # Morale modifiers
        if morale > 0.7:
            scores["MAIN_ATTACK"] += 0.1
            scores["DEEP_STRIKE"] += 0.05
        if morale < 0.3:
            scores["DEFEND"] += 0.2
            scores["RESERVE"] += 0.1

        # Supply critical → conservative
        if supply < 0.2:
            scores["DEFEND"] += 0.2
            scores["RESERVE"] += 0.15
            scores["MAIN_ATTACK"] *= 0.5
            scores["DEEP_STRIKE"] *= 0.5

        return self._select_best(
            unit_id=unit_id,
            echelon_level=10,  # CORPS range
            scores=scores,
            personality=personality,
            assessment=assessment,
            action_enum=_CORPS_ENUM,
            doctrine=doctrine,
            ts=ts,
            school_adjustments=school_adjustments,
        )

    # -- Common selection logic ---------------------------------------------

    def _select_best(
        self,
        unit_id: str,
        echelon_level: int,
        scores: dict[str, float],
        personality: CommanderPersonality,
        assessment: SituationAssessment,
        action_enum: type[enum.IntEnum],
        doctrine: DoctrineTemplate | None,
        ts: datetime,
        school_adjustments: dict[str, float] | None = None,
    ) -> DecisionResult:
        """Apply doctrine filtering, school adjustments, noise, and select.

        Parameters
        ----------
        unit_id : str
            Unit making the decision.
        echelon_level : int
            Nominal echelon level for the result.
        scores : dict[str, float]
            Base scores per action name.
        personality : CommanderPersonality
            Active personality (never ``None`` here).
        assessment : SituationAssessment
            Current situation assessment.
        action_enum : type[enum.IntEnum]
            Echelon-specific action enum.
        doctrine : DoctrineTemplate | None
            Active doctrine for action filtering.
        ts : datetime
            Timestamp.
        school_adjustments : dict[str, float] | None
            Additive score adjustments from a doctrinal school.

        Returns
        -------
        DecisionResult
        """
        # 1. Doctrine filtering (fuzzy case-insensitive match)
        if doctrine is not None:
            doctrine_actions_lower = frozenset(a.lower() for a in doctrine.actions)
            filtered = {
                name: score
                for name, score in scores.items()
                if name.lower() in doctrine_actions_lower
            }
            # Don't filter to empty
            if filtered:
                scores = filtered

        # 1b. Apply school adjustments (after doctrine filtering, before noise)
        if school_adjustments:
            for action, adj in school_adjustments.items():
                if action in scores:
                    scores[action] += adj

        # 2. Add Gaussian noise: sigma = 0.1 * (1.0 - experience)
        sigma = 0.1 * (1.0 - personality.experience)
        noised: dict[str, float] = {}
        for key in sorted(scores):
            noise = float(self._rng.normal(0.0, sigma)) if sigma > 0.0 else 0.0
            noised[key] = scores[key] + noise

        # 3. Select action with highest noised score
        best_name = max(noised, key=lambda k: noised[k])
        best_enum_val = action_enum[best_name]

        # 4. Determine category
        category = _categorize_action(best_name)

        # 5. Compute confidence
        confidence = max(
            0.0,
            min(1.0, assessment.confidence * (0.5 + 0.5 * personality.experience)),
        )

        # 6. Build rationale
        rationale = (
            f"{best_name} selected (score={noised[best_name]:.2f}, "
            f"force_ratio={assessment.force_ratio:.1f}, "
            f"morale={assessment.morale_level:.1f}, "
            f"overall={assessment.overall_rating.name})"
        )

        return DecisionResult(
            unit_id=unit_id,
            echelon_level=echelon_level,
            decision_category=category,
            action=int(best_enum_val),
            action_name=best_name,
            confidence=confidence,
            rationale=rationale,
            timestamp=ts,
        )

    # -- State protocol -----------------------------------------------------

    def get_state(self) -> dict:
        """Serialize for checkpoint/restore."""
        return {
            "decision_count": self._decision_count,
        }

    def set_state(self, state: dict) -> None:
        """Restore from checkpoint."""
        self._decision_count = state.get("decision_count", 0)
