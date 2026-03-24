"""Air Power doctrinal school (Warden).

Five Rings strategic targeting theory: leadership, organic essentials,
infrastructure, population, and fielded forces (inside-out).  At
higher echelons, strongly favours deep strike over ground maneuver.
At lower echelons, ground forces hold while air power delivers the
decisive effect.
"""

from __future__ import annotations

from stochastic_warfare.c2.ai.schools.base import DoctrinalSchool
from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


class AirPowerSchool(DoctrinalSchool):
    """Five Rings strategic targeting with air superiority prerequisite.

    Corps+ (>=10) strongly favours DEEP_STRIKE and penalises
    MAIN_ATTACK (ground decisive action de-emphasised).  Brigade/
    division (8-9) favours DEFEND and DELAY — ground forces hold
    terrain while air power achieves the strategic effect.
    """

    def get_decision_score_adjustments(
        self,
        echelon: int,
        assessment_summary: dict,
    ) -> dict[str, float]:
        adjustments = super().get_decision_score_adjustments(echelon, assessment_summary)

        # Corps+ echelon: air-centric deep strike
        if echelon >= 10:
            adjustments["DEEP_STRIKE"] = adjustments.get("DEEP_STRIKE", 0.0) + 0.25
            adjustments["MAIN_ATTACK"] = adjustments.get("MAIN_ATTACK", 0.0) - 0.15

        # Brigade/division echelon: ground holds
        if 8 <= echelon <= 9:
            adjustments["DEFEND"] = adjustments.get("DEFEND", 0.0) + 0.1
            adjustments["DELAY"] = adjustments.get("DELAY", 0.0) + 0.1

        return adjustments
