"""Attrition doctrinal school.

Exchange ratio optimisation, fire superiority, and deliberate
operations.  Favours attack when numerically superior and shifts to
defense and fire support when outnumbered, maximising the exchange
ratio in both cases.
"""

from __future__ import annotations

from stochastic_warfare.c2.ai.schools.base import DoctrinalSchool
from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


class AttritionSchool(DoctrinalSchool):
    """Exchange ratio optimisation with fire superiority focus.

    When force ratio is favorable (> 1.5), applies offensive bonus to
    ATTACK.  When unfavorable or equal, shifts to DEFEND and
    SUPPORT_BY_FIRE to maximise attrition efficiency.
    """

    def get_decision_score_adjustments(
        self,
        echelon: int,
        assessment_summary: dict,
    ) -> dict[str, float]:
        adjustments = super().get_decision_score_adjustments(echelon, assessment_summary)

        force_ratio = assessment_summary.get("force_ratio", 1.0)

        if force_ratio > 1.5:
            adjustments["ATTACK"] = adjustments.get("ATTACK", 0.0) + 0.1
        else:
            adjustments["DEFEND"] = adjustments.get("DEFEND", 0.0) + 0.15
            adjustments["SUPPORT_BY_FIRE"] = adjustments.get("SUPPORT_BY_FIRE", 0.0) + 0.1

        return adjustments
