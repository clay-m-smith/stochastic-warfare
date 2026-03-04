"""Maneuverist doctrinal school (Boyd).

Tempo-driven OODA acceleration, bypass strongpoints, and exploit gaps.
Prioritises dislocation over destruction — flanking and bypassing rather
than frontal assault.  Penalises direct attack when force ratio is
unfavorable.
"""

from __future__ import annotations

from stochastic_warfare.c2.ai.schools.base import DoctrinalSchool, SchoolDefinition
from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


class ManeuveristSchool(DoctrinalSchool):
    """Tempo-driven maneuver warfare following Boyd's OODA theory.

    Always applies bonuses to FLANK, BYPASS, EXPLOIT, and PURSUE.
    Penalises ATTACK when force ratio is below 2.0 to discourage
    frontal assaults without overwhelming superiority.
    """

    def get_decision_score_adjustments(
        self,
        echelon: int,
        assessment_summary: dict,
    ) -> dict[str, float]:
        adjustments = super().get_decision_score_adjustments(echelon, assessment_summary)

        force_ratio = assessment_summary.get("force_ratio", 1.0)

        # Always favor maneuver actions
        for action in ("FLANK", "BYPASS", "EXPLOIT", "PURSUE"):
            adjustments[action] = adjustments.get(action, 0.0) + 0.15

        # Penalise frontal attack without decisive superiority
        if force_ratio < 2.0:
            adjustments["ATTACK"] = adjustments.get("ATTACK", 0.0) - 0.1

        return adjustments
