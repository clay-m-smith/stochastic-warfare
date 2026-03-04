"""Maritime doctrinal schools -- Mahanian and Corbettian.

Two complementary naval warfare philosophies:

- **Mahanian** (Alfred Thayer Mahan): Fleet concentration, decisive naval
  battle, command of the sea.  Favors massing forces for a single decisive
  engagement and penalizes dispersal (BYPASS).  Maps to aggressive surface
  fleet doctrine.

- **Corbettian** (Julian Corbett): Fleet-in-being, sea denial, selective
  engagement.  Avoids decisive battle unless overwhelmingly superior.
  Favors DEFEND and DELAY to preserve the fleet as a threat-in-being.
"""

from __future__ import annotations

from stochastic_warfare.c2.ai.schools.base import DoctrinalSchool, SchoolDefinition
from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


class MahanianSchool(DoctrinalSchool):
    """Fleet concentration and decisive naval battle (Mahan).

    When force ratio is favorable (> 1.0), applies offensive bonuses to
    ATTACK and MAIN_ATTACK to seek decisive engagement.  Always penalizes
    BYPASS to discourage dispersal of the fleet.
    """

    def get_decision_score_adjustments(
        self,
        echelon: int,
        assessment_summary: dict,
    ) -> dict[str, float]:
        adjustments = super().get_decision_score_adjustments(echelon, assessment_summary)

        force_ratio = assessment_summary.get("force_ratio", 1.0)

        # Seek decisive engagement when force ratio is favorable
        if force_ratio > 1.0:
            for action in ("ATTACK", "MAIN_ATTACK"):
                adjustments[action] = adjustments.get(action, 0.0) + 0.15

        # Always penalize dispersal -- concentration is paramount
        adjustments["BYPASS"] = adjustments.get("BYPASS", 0.0) - 0.1

        return adjustments


class CorbettianSchool(DoctrinalSchool):
    """Fleet-in-being and sea denial (Corbett).

    When force ratio is below the overwhelming threshold (2.5), penalizes
    ATTACK and favors DEFEND and DELAY to preserve the fleet.  Only applies
    an offensive bonus when force ratio is overwhelming (>= 2.5), reflecting
    Corbett's principle of selective engagement.
    """

    def get_decision_score_adjustments(
        self,
        echelon: int,
        assessment_summary: dict,
    ) -> dict[str, float]:
        adjustments = super().get_decision_score_adjustments(echelon, assessment_summary)

        force_ratio = assessment_summary.get("force_ratio", 1.0)

        if force_ratio >= 2.5:
            # Only attack when overwhelming -- selective engagement
            adjustments["ATTACK"] = adjustments.get("ATTACK", 0.0) + 0.1
        else:
            # Fleet-in-being -- avoid decisive battle, favor sea denial
            adjustments["ATTACK"] = adjustments.get("ATTACK", 0.0) - 0.15
            adjustments["DEFEND"] = adjustments.get("DEFEND", 0.0) + 0.1
            adjustments["DELAY"] = adjustments.get("DELAY", 0.0) + 0.1

        return adjustments
