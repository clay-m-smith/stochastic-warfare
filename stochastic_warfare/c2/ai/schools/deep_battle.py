"""Deep Battle doctrinal school.

Echeloned assault, operational-depth strikes, and reserve management
following Tukhachevsky's theory of successive operations.

Core principles:

* **Simultaneous echeloned assault** — when force ratio is highly
  favorable (> 2.0), press the attack and exploit breakthroughs.
* **Reserve management** — at moderate superiority (1.0--2.0), hold
  reserves for commitment at the decisive point.
* **Operational depth** — at corps and above, favor deep strikes and
  operational maneuver to disrupt the enemy rear.
"""

from __future__ import annotations

from stochastic_warfare.c2.ai.schools.base import DoctrinalSchool, SchoolDefinition
from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


class DeepBattleSchool(DoctrinalSchool):
    """Echeloned assault with operational-depth strikes and reserve management.

    Overrides :meth:`get_decision_score_adjustments` for:

    * Force-ratio-driven offensive push (> 2.0) or reserve hold (1.0--2.0).
    * Corps+ echelon deep strike and operational maneuver bonuses.
    """

    def get_decision_score_adjustments(
        self,
        echelon: int,
        assessment_summary: dict,
    ) -> dict[str, float]:
        adjustments = super().get_decision_score_adjustments(echelon, assessment_summary)

        force_ratio = assessment_summary.get("force_ratio", 1.0)

        # Overwhelming superiority — press the attack and exploit
        if force_ratio > 2.0:
            adjustments["ATTACK"] = adjustments.get("ATTACK", 0.0) + 0.15
            adjustments["EXPLOIT"] = adjustments.get("EXPLOIT", 0.0) + 0.1
        # Moderate superiority — hold reserves
        elif force_ratio > 1.0:
            adjustments["RESERVE"] = adjustments.get("RESERVE", 0.0) + 0.15

        # Operational depth — deep strikes at corps+ (echelon >= 10)
        if echelon >= 10:
            adjustments["DEEP_STRIKE"] = adjustments.get("DEEP_STRIKE", 0.0) + 0.2
            adjustments["OPERATIONAL_MANEUVER"] = (
                adjustments.get("OPERATIONAL_MANEUVER", 0.0) + 0.15
            )

        return adjustments
