"""Doctrinal school base class and definition model.

Schools are Strategy-pattern objects that produce modifier dicts consumed
by existing AI engines via optional parameters.  Each school represents a
distinct warfare philosophy (Clausewitz, Sun Tzu, Boyd, etc.) and modifies
assessment weights, decision scores, OODA timing, COA evaluation, and
stratagem affinity.

Schools do NOT wrap or subclass engines — they produce data that callers
inject.  This follows the same DI pattern as ``mopp_speed_factor``
(Phase 18), ``fuel_available`` (Phase 11c), and ``jam_snr_penalty_db``
(Phase 16).
"""

from __future__ import annotations

from abc import ABC

from pydantic import BaseModel, Field

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Pydantic definition model (YAML-loaded)
# ---------------------------------------------------------------------------


class SchoolDefinition(BaseModel):
    """Data-driven doctrinal school specification loaded from YAML."""

    school_id: str
    display_name: str
    description: str = ""
    assessment_weight_overrides: dict[str, float] = {}
    preferred_actions: dict[str, float] = {}
    avoided_actions: dict[str, float] = {}
    ooda_multiplier: float = Field(default=1.0, gt=0.0)
    coa_score_weight_overrides: dict[str, float] = {}
    risk_tolerance: str | None = None
    stratagem_affinity: dict[str, float] = {}
    opponent_modeling_enabled: bool = False
    opponent_modeling_weight: float = Field(default=0.0, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------


class DoctrinalSchool(ABC):
    """Strategy-pattern base for doctrinal schools.

    Schools produce modifier dicts, not side effects.  All hooks have
    default implementations driven by the YAML :class:`SchoolDefinition`.
    Subclasses override hooks to add conditional logic (e.g. Clausewitzian
    culmination awareness, Sun Tzu opponent modeling).

    Parameters
    ----------
    definition : SchoolDefinition
        YAML-loaded school parameters.
    """

    def __init__(self, definition: SchoolDefinition) -> None:
        self._definition = definition

    @property
    def school_id(self) -> str:
        """Unique school identifier."""
        return self._definition.school_id

    @property
    def display_name(self) -> str:
        """Human-readable name."""
        return self._definition.display_name

    @property
    def definition(self) -> SchoolDefinition:
        """Access the underlying YAML-loaded definition."""
        return self._definition

    # -- Hooks (default implementations from YAML data) ---------------------

    def get_assessment_weight_overrides(self) -> dict[str, float]:
        """Return multipliers for assessment weight factors.

        Keys match ``_WEIGHTS`` in ``assessment.py``: ``force_ratio``,
        ``terrain``, ``supply``, ``morale``, ``intel``, ``environmental``,
        ``c2``.  Values are multipliers (1.0 = no change).
        """
        return dict(self._definition.assessment_weight_overrides)

    def get_decision_score_adjustments(
        self,
        echelon: int,
        assessment_summary: dict,
    ) -> dict[str, float]:
        """Return additive adjustments to decision action scores.

        Default: combines ``preferred_actions`` (bonus) and
        ``avoided_actions`` (penalty) from YAML.  Subclasses override
        for conditional logic.

        Parameters
        ----------
        echelon : int
            Echelon level of the deciding unit.
        assessment_summary : dict
            Summary dict with keys: ``force_ratio``, ``supply_level``,
            ``morale_level``, ``intel_quality``, ``c2_effectiveness``.

        Returns
        -------
        dict[str, float]
            Action name -> additive score adjustment.
        """
        adjustments: dict[str, float] = {}
        for action, bonus in self._definition.preferred_actions.items():
            adjustments[action] = adjustments.get(action, 0.0) + bonus
        for action, penalty in self._definition.avoided_actions.items():
            adjustments[action] = adjustments.get(action, 0.0) - penalty
        return adjustments

    def get_ooda_multiplier(self) -> float:
        """Return OODA cycle speed multiplier (<1 = faster, >1 = slower)."""
        return self._definition.ooda_multiplier

    def get_coa_score_weight_overrides(self) -> dict[str, float]:
        """Return overrides for COA scoring weights.

        Keys: ``mission``, ``preservation``, ``tempo``, ``simplicity``.
        """
        return dict(self._definition.coa_score_weight_overrides)

    def get_risk_tolerance_override(self) -> str | None:
        """Return risk tolerance override (``low``/``moderate``/``high``)."""
        return self._definition.risk_tolerance

    def get_stratagem_affinity(self) -> dict[str, float]:
        """Return stratagem type probability bonuses."""
        return dict(self._definition.stratagem_affinity)

    # -- Opponent modeling (default: no-op) ---------------------------------

    def predict_opponent_action(
        self,
        own_assessment: dict,
        opponent_power: float,
        opponent_morale: float,
        own_power: float,
    ) -> dict[str, float]:
        """Predict opponent's likely action distribution.

        Default implementation returns empty dict (no prediction).
        Sun Tzu overrides this.
        """
        return {}

    def adjust_scores_for_opponent(
        self,
        own_scores: dict[str, float],
        opponent_prediction: dict[str, float],
    ) -> dict[str, float]:
        """Adjust own decision scores based on opponent prediction.

        Default implementation returns scores unchanged.
        Sun Tzu overrides this.
        """
        return dict(own_scores)
