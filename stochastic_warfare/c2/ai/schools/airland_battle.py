"""AirLand Battle doctrinal school.

Simultaneous deep, close, and rear operations with sensor-to-shooter
integration and aggressive initiative.  Higher echelons (corps+) focus
on deep strikes and operational maneuver; lower echelons (brigade/
division) favour close combat and counterattack.  High intelligence
quality unlocks exploitation opportunities.
"""

from __future__ import annotations

from stochastic_warfare.c2.ai.schools.base import DoctrinalSchool
from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


class AirLandBattleSchool(DoctrinalSchool):
    """Simultaneous deep/close/rear operations with initiative.

    Echelon-dependent behavior: corps+ (>=10) emphasises deep strike
    and operational maneuver; brigade/division (8-9) emphasises close
    attack and counterattack.  High intel quality (>0.7) enables
    exploitation.
    """

    def get_decision_score_adjustments(
        self,
        echelon: int,
        assessment_summary: dict,
    ) -> dict[str, float]:
        adjustments = super().get_decision_score_adjustments(echelon, assessment_summary)

        intel_quality = assessment_summary.get("intel_quality", 0.5)

        # Corps+ echelon: deep operations
        if echelon >= 10:
            adjustments["DEEP_STRIKE"] = adjustments.get("DEEP_STRIKE", 0.0) + 0.2
            adjustments["OPERATIONAL_MANEUVER"] = (
                adjustments.get("OPERATIONAL_MANEUVER", 0.0) + 0.15
            )

        # Brigade/division echelon: close fight
        if 8 <= echelon <= 9:
            adjustments["ATTACK"] = adjustments.get("ATTACK", 0.0) + 0.1
            adjustments["COUNTERATTACK"] = adjustments.get("COUNTERATTACK", 0.0) + 0.15

        # Sensor-to-shooter: exploit when intel is excellent
        if intel_quality > 0.7:
            adjustments["EXPLOIT"] = adjustments.get("EXPLOIT", 0.0) + 0.15

        return adjustments
