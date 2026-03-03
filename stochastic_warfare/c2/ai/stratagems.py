"""Stratagems -- tactical and operational deception and maneuver tricks.

Evaluates opportunities for stratagems: deception (feints, demonstrations),
concentration of force (Schwerpunkt), economy of force, and surprise.
Stratagems are opportunity-evaluated (checked when conditions are right),
not proactively planned in COA development. Echelon and experience gate
which stratagems are available.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from stochastic_warfare.c2.ai.assessment import SituationAssessment
from stochastic_warfare.c2.events import StratagemActivatedEvent
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class StratagemType(enum.IntEnum):
    """Categories of battlefield stratagems."""

    DECEPTION = 0
    CONCENTRATION = 1
    ECONOMY_OF_FORCE = 2
    SURPRISE = 3
    FEINT = 4
    DEMONSTRATION = 5


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StratagemPlan:
    """Immutable description of a planned stratagem."""

    stratagem_id: str
    stratagem_type: StratagemType
    description: str
    target_area: str
    units_involved: tuple[str, ...]
    estimated_effect: float  # 0--1 effectiveness estimate
    risk: float  # 0--1


# ---------------------------------------------------------------------------
# Requirements gate: (min_echelon, min_experience) per stratagem type
# ---------------------------------------------------------------------------

_STRATAGEM_REQUIREMENTS: dict[StratagemType, tuple[int, float]] = {
    StratagemType.DECEPTION: (6, 0.4),  # Battalion+, experience >= 0.4
    StratagemType.CONCENTRATION: (5, 0.3),  # Company+, experience >= 0.3
    StratagemType.ECONOMY_OF_FORCE: (6, 0.3),  # Battalion+
    StratagemType.SURPRISE: (4, 0.5),  # Platoon+, high experience
    StratagemType.FEINT: (5, 0.4),  # Company+
    StratagemType.DEMONSTRATION: (6, 0.3),  # Battalion+
}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class StratagemEngine:
    """Evaluates and activates battlefield stratagems.

    Parameters
    ----------
    event_bus : EventBus
        Bus for publishing :class:`StratagemActivatedEvent`.
    rng : numpy.random.Generator
        Deterministic PRNG stream for effect estimation.
    """

    def __init__(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._active_plans: dict[str, StratagemPlan] = {}

    # -- Eligibility --------------------------------------------------------

    def can_employ_stratagem(
        self,
        unit_id: str,
        echelon: int,
        experience: float,
        stratagem_type: StratagemType,
    ) -> bool:
        """Check whether a unit meets echelon and experience requirements.

        Parameters
        ----------
        unit_id : str
            The unit to check (logged on failure).
        echelon : int
            Echelon level of the unit.
        experience : float
            Commander experience (0.0--1.0).
        stratagem_type : StratagemType
            The stratagem to evaluate.

        Returns
        -------
        bool
            ``True`` if the unit can employ the stratagem.
        """
        req = _STRATAGEM_REQUIREMENTS[stratagem_type]
        min_echelon, min_exp = req
        if echelon < min_echelon:
            logger.debug(
                "Unit %s echelon %d below %d required for %s",
                unit_id,
                echelon,
                min_echelon,
                stratagem_type.name,
            )
            return False
        if experience < min_exp:
            logger.debug(
                "Unit %s experience %.2f below %.2f required for %s",
                unit_id,
                experience,
                min_exp,
                stratagem_type.name,
            )
            return False
        return True

    # -- Opportunity evaluation ---------------------------------------------

    def evaluate_deception_opportunity(
        self,
        assessment: SituationAssessment,
        unit_ids: list[str],
        echelon: int,
        experience: float,
    ) -> tuple[bool, str]:
        """Evaluate whether conditions favour a deception operation.

        Deception is most effective when force ratios are moderate (0.5--2.0)
        and C2 effectiveness is adequate (>0.5).

        Parameters
        ----------
        assessment : SituationAssessment
            Current situation assessment.
        unit_ids : list[str]
            Units potentially involved.
        echelon : int
            Echelon level.
        experience : float
            Commander experience.

        Returns
        -------
        tuple[bool, str]
            ``(viable, reason)`` — ``True`` with a description if deception
            is viable, ``False`` with an explanation otherwise.
        """
        # Gate: eligibility
        if not unit_ids:
            return False, "No units available for deception"
        if not self.can_employ_stratagem(unit_ids[0], echelon, experience, StratagemType.DECEPTION):
            if echelon < _STRATAGEM_REQUIREMENTS[StratagemType.DECEPTION][0]:
                return False, "Echelon too low for deception operations"
            return False, "Insufficient experience for deception operations"

        # Force ratio must be moderate — deception less useful in overwhelming situations
        ratio = assessment.force_ratio
        if ratio < 0.5 or ratio > 2.0:
            return False, f"Force ratio {ratio:.1f} outside viable range (0.5-2.0) for deception"

        # C2 must be adequate to coordinate deception
        if assessment.c2_effectiveness <= 0.5:
            return False, f"C2 effectiveness {assessment.c2_effectiveness:.2f} too low for deception coordination"

        return True, f"Force ratio of {ratio:.1f} favorable for deception operations"

    def evaluate_concentration_opportunity(
        self,
        assessment: SituationAssessment,
        unit_ids: list[str],
        echelon: int,
        experience: float,
    ) -> tuple[bool, str]:
        """Evaluate whether conditions favour concentration of force.

        Concentration requires 3+ units and a force ratio above 0.6.

        Parameters
        ----------
        assessment : SituationAssessment
            Current situation assessment.
        unit_ids : list[str]
            Units available for concentration.
        echelon : int
            Echelon level.
        experience : float
            Commander experience.

        Returns
        -------
        tuple[bool, str]
            ``(viable, reason)``.
        """
        if not unit_ids:
            return False, "No units available for concentration"
        if not self.can_employ_stratagem(unit_ids[0], echelon, experience, StratagemType.CONCENTRATION):
            if echelon < _STRATAGEM_REQUIREMENTS[StratagemType.CONCENTRATION][0]:
                return False, "Echelon too low for concentration"
            return False, "Insufficient experience for concentration"

        if len(unit_ids) < 3:
            return False, f"Only {len(unit_ids)} units available; need at least 3 for concentration"

        if assessment.force_ratio < 0.6:
            return False, f"Force ratio {assessment.force_ratio:.1f} too low for concentration (need >= 0.6)"

        return True, f"Concentration of {len(unit_ids)} units achievable at Schwerpunkt"

    # -- Planning -----------------------------------------------------------

    def plan_concentration(
        self,
        unit_ids: list[str],
        concentration_point: Position,
        economy_unit_ids: list[str],
    ) -> StratagemPlan:
        """Create a plan for concentrating forces at *concentration_point*.

        Parameters
        ----------
        unit_ids : list[str]
            Units that will concentrate.
        concentration_point : Position
            ENU position of the Schwerpunkt.
        economy_unit_ids : list[str]
            Units that will hold other sectors with economy of force.

        Returns
        -------
        StratagemPlan
            Frozen plan dataclass.
        """
        estimated_effect = min(1.0, len(unit_ids) / 5.0 * 0.8)
        economy_count = max(len(economy_unit_ids), 1)
        risk = min(1.0, 0.3 + 0.1 * (len(unit_ids) / economy_count))

        plan = StratagemPlan(
            stratagem_id=str(uuid.uuid4()),
            stratagem_type=StratagemType.CONCENTRATION,
            description=(
                f"Concentrate {len(unit_ids)} units at "
                f"({concentration_point.easting:.0f}, {concentration_point.northing:.0f}); "
                f"{len(economy_unit_ids)} units hold other sectors"
            ),
            target_area=f"({concentration_point.easting:.0f}, {concentration_point.northing:.0f})",
            units_involved=tuple(unit_ids + economy_unit_ids),
            estimated_effect=estimated_effect,
            risk=risk,
        )

        self._active_plans[plan.stratagem_id] = plan
        logger.debug(
            "Planned concentration at %s with %d units, effect=%.2f risk=%.2f",
            plan.target_area,
            len(unit_ids),
            estimated_effect,
            risk,
        )
        return plan

    def plan_deception(
        self,
        feint_unit_ids: list[str],
        target_area: str,
        main_unit_ids: list[str],
    ) -> StratagemPlan:
        """Create a plan for a feint/demonstration to fix enemy attention.

        Parameters
        ----------
        feint_unit_ids : list[str]
            Units performing the feint.
        target_area : str
            Description of the deception target area.
        main_unit_ids : list[str]
            Units performing the main effort.

        Returns
        -------
        StratagemPlan
            Frozen plan dataclass.
        """
        # Deception outcome is inherently uncertain
        estimated_effect = 0.3 + float(self._rng.random()) * 0.4
        main_count = max(len(main_unit_ids), 1)
        risk = min(1.0, 0.2 + 0.2 * (len(feint_unit_ids) / main_count))

        plan = StratagemPlan(
            stratagem_id=str(uuid.uuid4()),
            stratagem_type=StratagemType.DECEPTION,
            description=(
                f"Feint with {len(feint_unit_ids)} units at {target_area} "
                f"to fix enemy while {len(main_unit_ids)} units execute main effort"
            ),
            target_area=target_area,
            units_involved=tuple(feint_unit_ids + main_unit_ids),
            estimated_effect=estimated_effect,
            risk=risk,
        )

        self._active_plans[plan.stratagem_id] = plan
        logger.debug(
            "Planned deception at %s with %d feint + %d main units, effect=%.2f risk=%.2f",
            target_area,
            len(feint_unit_ids),
            len(main_unit_ids),
            estimated_effect,
            risk,
        )
        return plan

    # -- Activation ---------------------------------------------------------

    def activate_stratagem(
        self,
        unit_id: str,
        plan: StratagemPlan,
        ts: datetime | None = None,
    ) -> None:
        """Activate a stratagem, publishing :class:`StratagemActivatedEvent`.

        Parameters
        ----------
        unit_id : str
            The commanding unit activating the stratagem.
        plan : StratagemPlan
            The plan to activate.
        ts : datetime | None
            Event timestamp.  Defaults to UTC now.
        """
        if ts is None:
            ts = datetime.now(tz=timezone.utc)

        self._event_bus.publish(
            StratagemActivatedEvent(
                timestamp=ts,
                source=ModuleId.C2,
                unit_id=unit_id,
                stratagem_type=plan.stratagem_type.name,
                target_area=plan.target_area,
            )
        )

        logger.debug(
            "Activated %s stratagem for %s at %s",
            plan.stratagem_type.name,
            unit_id,
            plan.target_area,
        )

    # -- State protocol -----------------------------------------------------

    def get_state(self) -> dict:
        """Serialize for checkpoint/restore."""
        plans: dict[str, dict] = {}
        for sid, plan in self._active_plans.items():
            plans[sid] = {
                "stratagem_id": plan.stratagem_id,
                "stratagem_type": int(plan.stratagem_type),
                "description": plan.description,
                "target_area": plan.target_area,
                "units_involved": list(plan.units_involved),
                "estimated_effect": plan.estimated_effect,
                "risk": plan.risk,
            }
        return {"active_plans": plans}

    def set_state(self, state: dict) -> None:
        """Restore from checkpoint."""
        self._active_plans.clear()
        for sid, d in state.get("active_plans", {}).items():
            plan = StratagemPlan(
                stratagem_id=d["stratagem_id"],
                stratagem_type=StratagemType(d["stratagem_type"]),
                description=d["description"],
                target_area=d["target_area"],
                units_involved=tuple(d["units_involved"]),
                estimated_effect=d["estimated_effect"],
                risk=d["risk"],
            )
            self._active_plans[sid] = plan
