"""Clausewitzian doctrinal school.

Center-of-gravity targeting, decisive engagement, and Schwerpunkt
(main effort).  Emphasises concentration of force against the enemy's
center of gravity.  Includes culmination awareness — when supply or
morale are low, the school shifts toward consolidation and defense
rather than continued offensive action.
"""

from __future__ import annotations

from stochastic_warfare.c2.ai.schools.base import DoctrinalSchool
from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


class ClausewitzianSchool(DoctrinalSchool):
    """Center-of-gravity targeting with culmination awareness.

    When force ratio is favorable (> 1.5), applies offensive bonuses to
    ATTACK, MAIN_ATTACK, and ENVELOP.  When supply or morale are
    critically low, shifts toward CONSOLIDATE and DEFEND to avoid
    culmination.
    """

    def get_decision_score_adjustments(
        self,
        echelon: int,
        assessment_summary: dict,
    ) -> dict[str, float]:
        adjustments = super().get_decision_score_adjustments(echelon, assessment_summary)

        force_ratio = assessment_summary.get("force_ratio", 1.0)
        supply_level = assessment_summary.get("supply_level", 1.0)
        morale_level = assessment_summary.get("morale_level", 1.0)

        # Decisive engagement when force ratio is favorable
        if force_ratio > 1.5:
            for action in ("ATTACK", "MAIN_ATTACK", "ENVELOP"):
                adjustments[action] = adjustments.get(action, 0.0) + 0.15

        # Culmination awareness — avoid overextension
        if supply_level < 0.3 or morale_level < 0.4:
            adjustments["CONSOLIDATE"] = adjustments.get("CONSOLIDATE", 0.0) + 0.15
            adjustments["DEFEND"] = adjustments.get("DEFEND", 0.0) + 0.1

        return adjustments
