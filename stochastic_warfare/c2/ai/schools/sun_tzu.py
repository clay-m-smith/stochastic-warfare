"""Sun Tzu doctrinal school.

Intel-first, deception, indirect approach, and opponent modeling.  The
most complex school — overrides opponent prediction and score adjustment
hooks in addition to standard decision score adjustments.

Core principles:

* **Know the enemy, know yourself** — low intel triggers strong RECON
  preference.
* **Avoid strength, attack weakness** — penalizes frontal ATTACK when
  force ratio is unfavorable; favors FLANK.
* **All warfare is based on deception** — high stratagem affinity
  (configured via YAML).
* **Opponent modeling** — predicts opponent intent via Lanchester
  heuristics and adjusts own scores to exploit predicted posture.
"""

from __future__ import annotations

from stochastic_warfare.c2.ai.assessment import predict_opponent_action_lanchester
from stochastic_warfare.c2.ai.schools.base import DoctrinalSchool, SchoolDefinition
from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


class SunTzuSchool(DoctrinalSchool):
    """Intel-first, deception, indirect approach with opponent modeling.

    Overrides three hooks:

    * :meth:`get_decision_score_adjustments` — conditional logic for
      intel-driven RECON, force-ratio-gated ATTACK penalty, FLANK bonus.
    * :meth:`predict_opponent_action` — delegates to
      :func:`predict_opponent_action_lanchester`.
    * :meth:`adjust_scores_for_opponent` — applies counter-posture
      bonuses weighted by ``opponent_modeling_weight``.
    """

    def get_decision_score_adjustments(
        self,
        echelon: int,
        assessment_summary: dict,
    ) -> dict[str, float]:
        adjustments = super().get_decision_score_adjustments(echelon, assessment_summary)

        force_ratio = assessment_summary.get("force_ratio", 1.0)
        intel_quality = assessment_summary.get("intel_quality", 0.5)

        # Avoid strength — penalize frontal ATTACK when outnumbered
        if force_ratio < 1.5:
            adjustments["ATTACK"] = adjustments.get("ATTACK", 0.0) - 0.15

        # Low intel — strong preference for RECON
        if intel_quality < 0.3:
            adjustments["RECON"] = adjustments.get("RECON", 0.0) + 0.2

        # Indirect approach — always favor flanking
        adjustments["FLANK"] = adjustments.get("FLANK", 0.0) + 0.1

        return adjustments

    def predict_opponent_action(
        self,
        own_assessment: dict,
        opponent_power: float,
        opponent_morale: float,
        own_power: float,
    ) -> dict[str, float]:
        """Predict opponent action using Lanchester force-ratio heuristics."""
        return predict_opponent_action_lanchester(
            opponent_power=opponent_power,
            own_power=own_power,
            opponent_morale=opponent_morale,
        )

    def adjust_scores_for_opponent(
        self,
        own_scores: dict[str, float],
        opponent_prediction: dict[str, float],
    ) -> dict[str, float]:
        """Adjust own scores to exploit predicted opponent posture.

        Applies counter-posture bonuses scaled by
        ``opponent_modeling_weight`` from the school definition.
        """
        weight = self._definition.opponent_modeling_weight
        adjusted = dict(own_scores)

        p_attack = opponent_prediction.get("ATTACK", 0.0)
        p_defend = opponent_prediction.get("DEFEND", 0.0)
        p_withdraw = opponent_prediction.get("WITHDRAW", 0.0)

        # Counter-attack posture: ambush + flank
        if p_attack > 0.4:
            if "AMBUSH" in adjusted:
                adjusted["AMBUSH"] += 0.15 * weight
            if "FLANK" in adjusted:
                adjusted["FLANK"] += 0.1 * weight

        # Counter-defend posture: bypass + flank
        if p_defend > 0.4:
            if "BYPASS" in adjusted:
                adjusted["BYPASS"] += 0.15 * weight
            if "FLANK" in adjusted:
                adjusted["FLANK"] += 0.1 * weight

        # Counter-withdraw posture: pursue + exploit
        if p_withdraw > 0.4:
            if "PURSUE" in adjusted:
                adjusted["PURSUE"] += 0.15 * weight
            if "EXPLOIT" in adjusted:
                adjusted["EXPLOIT"] += 0.1 * weight

        return adjusted
