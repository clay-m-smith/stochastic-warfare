"""Situation assessment -- the ORIENT phase of the OODA loop.

Integrates force ratios, terrain advantage, supply status, unit morale,
intelligence quality, environmental conditions, and C2 effectiveness into
a multi-factor situation assessment. Assessment quality degrades with
stale intel, poor C2, and low experience. All input data is passed as
parameters (DI pattern) -- no stored references to other engines.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.c2.events import SituationAssessedEvent
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AssessmentRating(enum.IntEnum):
    """Situation assessment rating, from worst to best."""

    VERY_UNFAVORABLE = 0
    UNFAVORABLE = 1
    NEUTRAL = 2
    FAVORABLE = 3
    VERY_FAVORABLE = 4


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SituationAssessment:
    """Immutable snapshot of a situation assessment."""

    unit_id: str
    timestamp: datetime
    force_ratio: float
    force_ratio_rating: AssessmentRating
    terrain_advantage: float
    terrain_rating: AssessmentRating
    supply_level: float
    supply_rating: AssessmentRating
    morale_level: float
    morale_rating: AssessmentRating
    intel_quality: float
    intel_rating: AssessmentRating
    environmental_rating: AssessmentRating
    c2_effectiveness: float
    c2_rating: AssessmentRating
    overall_rating: AssessmentRating
    confidence: float
    opportunities: tuple[str, ...]
    threats: tuple[str, ...]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class AssessmentConfig(BaseModel):
    """Configurable thresholds and weights for situation assessment.

    All threshold tuples are ascending: (VU/U boundary, U/N, N/F, F/VF).
    """

    force_ratio_thresholds: tuple[float, float, float, float] = (0.4, 0.8, 1.5, 3.0)
    terrain_thresholds: tuple[float, float, float, float] = (-0.5, -0.2, 0.2, 0.5)
    supply_thresholds: tuple[float, float, float, float] = (0.15, 0.3, 0.5, 0.8)
    morale_thresholds: tuple[float, float, float, float] = (0.2, 0.4, 0.6, 0.8)
    intel_thresholds: tuple[float, float, float, float] = (0.15, 0.35, 0.6, 0.8)
    env_thresholds: tuple[float, float, float, float] = (0.15, 0.3, 0.5, 0.8)
    c2_thresholds: tuple[float, float, float, float] = (0.2, 0.4, 0.6, 0.8)
    overall_thresholds: tuple[float, float, float, float] = (1.0, 1.75, 2.5, 3.25)

    weights: dict[str, float] = {
        "force_ratio": 0.30,
        "terrain": 0.10,
        "supply": 0.15,
        "morale": 0.15,
        "intel": 0.10,
        "environmental": 0.05,
        "c2": 0.15,
    }

    # Confidence formula weights
    confidence_intel_weight: float = 0.4
    confidence_c2_weight: float = 0.3
    confidence_experience_weight: float = 0.2
    confidence_staff_weight: float = 0.1

    # Opportunity thresholds
    opportunity_force_ratio: float = 2.0
    opportunity_terrain: float = 0.3
    opportunity_supply: float = 0.8
    opportunity_morale: float = 0.7

    # Threat thresholds
    threat_force_ratio: float = 0.5
    threat_supply: float = 0.2
    threat_morale: float = 0.3
    threat_c2: float = 0.3
    threat_weather: float = 0.7


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class SituationAssessor:
    """Computes multi-factor situation assessments.

    Parameters
    ----------
    event_bus : EventBus
        Bus for publishing :class:`SituationAssessedEvent`.
    rng : numpy.random.Generator
        Deterministic PRNG stream for confidence noise.
    config : AssessmentConfig | None
        Configurable thresholds and weights.  Defaults match prior
        hardcoded values for zero behavioral change.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: AssessmentConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or AssessmentConfig()

    # -- Public API ---------------------------------------------------------

    def assess(
        self,
        unit_id: str,
        echelon: int,
        friendly_units: int,
        friendly_power: float,
        morale_level: float,
        supply_level: float,
        c2_effectiveness: float,
        contacts: int,
        enemy_power: float,
        visibility_km: float = 10.0,
        illumination: float = 1.0,
        daylight_hours: float = 12.0,
        weather_severity: float = 0.0,
        terrain_advantage: float = 0.0,
        experience: float = 0.5,
        staff_quality: float = 0.5,
        ts: datetime | None = None,
        weight_overrides: dict[str, float] | None = None,
    ) -> SituationAssessment:
        """Compute a situation assessment for *unit_id*.

        All input data is passed as parameters (DI pattern).

        Parameters
        ----------
        unit_id : str
            The unit performing the assessment.
        echelon : int
            Echelon level of the assessing unit.
        friendly_units : int
            Count of friendly units in the area.
        friendly_power : float
            Aggregate friendly combat power.
        morale_level : float
            Average morale (0.0--1.0).
        supply_level : float
            Composite supply state (0.0--1.0).
        c2_effectiveness : float
            C2 effectiveness (0.0--1.0).
        contacts : int
            Number of confirmed enemy contacts.
        enemy_power : float
            Estimated enemy combat power.
        visibility_km : float
            Current visibility in kilometres.
        illumination : float
            Illumination level (0.0--1.0).
        daylight_hours : float
            Remaining daylight hours.
        weather_severity : float
            Weather severity (0.0--1.0; 0 = clear, 1 = extreme).
        terrain_advantage : float
            Terrain advantage (-1.0 enemy advantage to 1.0 friendly advantage).
        experience : float
            Commander experience (0.0--1.0).
        staff_quality : float
            Staff quality (0.0--1.0).
        ts : datetime | None
            Timestamp for the assessment.  Defaults to UTC now.
        weight_overrides : dict[str, float] | None
            Multipliers for assessment weight factors (e.g.
            ``{"intel": 3.0, "force_ratio": 0.5}``).  Applied
            multiplicatively to ``_WEIGHTS`` then re-normalized.
            ``None`` uses baseline weights.

        Returns
        -------
        SituationAssessment
            Frozen assessment snapshot.
        """
        if ts is None:
            ts = datetime.now(tz=timezone.utc)

        cfg = self._config

        # 1. Force ratio
        if enemy_power <= 0.0:
            force_ratio = float("inf")
        else:
            force_ratio = friendly_power / enemy_power
        force_ratio_rating = self._rate(force_ratio, cfg.force_ratio_thresholds)

        # 2. Terrain
        terrain_rating = self._rate(terrain_advantage, cfg.terrain_thresholds)

        # 3. Supply
        supply_rating = self._rate(supply_level, cfg.supply_thresholds)

        # 4. Morale
        morale_rating = self._rate(morale_level, cfg.morale_thresholds)

        # 5. Intel quality — derived from contact count.
        # Each confirmed contact adds 0.2 to quality, capped at 1.0.
        if enemy_power > 0.0 and contacts > 0:
            intel_quality = min(1.0, contacts * 0.2)
        elif contacts > 0:
            intel_quality = 1.0  # contacts exist but no estimated enemy power
        else:
            intel_quality = 0.0
        intel_rating = self._rate(intel_quality, cfg.intel_thresholds)

        # 6. Environmental
        env_score = (visibility_km / 10.0) * illumination * (1.0 - weather_severity * 0.5)
        env_score = max(0.0, min(1.0, env_score))
        environmental_rating = self._rate(env_score, cfg.env_thresholds)

        # 7. C2
        c2_rating = self._rate(c2_effectiveness, cfg.c2_thresholds)

        # 8. Overall — weighted average of all ratings (int values 0-4)
        ratings = {
            "force_ratio": force_ratio_rating,
            "terrain": terrain_rating,
            "supply": supply_rating,
            "morale": morale_rating,
            "intel": intel_rating,
            "environmental": environmental_rating,
            "c2": c2_rating,
        }
        # Apply weight overrides: multiply then re-normalize
        effective_weights = dict(cfg.weights)
        if weight_overrides:
            for key in effective_weights:
                if key in weight_overrides:
                    effective_weights[key] *= weight_overrides[key]
            w_sum = sum(effective_weights.values())
            if w_sum > 0:
                for key in effective_weights:
                    effective_weights[key] /= w_sum
        weighted_sum = sum(
            int(ratings[key]) * effective_weights[key] for key in effective_weights
        )
        overall_rating = self._rate(weighted_sum, cfg.overall_thresholds)

        # 9. Confidence
        raw_confidence = (
            intel_quality * cfg.confidence_intel_weight
            + c2_effectiveness * cfg.confidence_c2_weight
            + experience * cfg.confidence_experience_weight
            + staff_quality * cfg.confidence_staff_weight
        )
        noise_mult = 1.0 + float(self._rng.normal(0.0, 0.05))
        confidence = max(0.0, min(1.0, raw_confidence * noise_mult))

        # 10. Opportunities
        opportunities: list[str] = []
        if force_ratio > cfg.opportunity_force_ratio:
            opportunities.append("numerical_superiority")
        if terrain_advantage > cfg.opportunity_terrain:
            opportunities.append("terrain_advantage")
        if supply_level > cfg.opportunity_supply:
            opportunities.append("logistics_advantage")
        if morale_level > cfg.opportunity_morale:
            opportunities.append("high_morale")

        # 11. Threats
        threats: list[str] = []
        if force_ratio < cfg.threat_force_ratio:
            threats.append("outnumbered")
        if supply_level < cfg.threat_supply:
            threats.append("supply_critical")
        if morale_level < cfg.threat_morale:
            threats.append("morale_crisis")
        if c2_effectiveness < cfg.threat_c2:
            threats.append("c2_degraded")
        if weather_severity > cfg.threat_weather:
            threats.append("severe_weather")

        # Build the frozen assessment
        assessment = SituationAssessment(
            unit_id=unit_id,
            timestamp=ts,
            force_ratio=force_ratio,
            force_ratio_rating=force_ratio_rating,
            terrain_advantage=terrain_advantage,
            terrain_rating=terrain_rating,
            supply_level=supply_level,
            supply_rating=supply_rating,
            morale_level=morale_level,
            morale_rating=morale_rating,
            intel_quality=intel_quality,
            intel_rating=intel_rating,
            environmental_rating=environmental_rating,
            c2_effectiveness=c2_effectiveness,
            c2_rating=c2_rating,
            overall_rating=overall_rating,
            confidence=confidence,
            opportunities=tuple(opportunities),
            threats=tuple(threats),
        )

        # Publish event
        self._event_bus.publish(
            SituationAssessedEvent(
                timestamp=ts,
                source=ModuleId.C2,
                unit_id=unit_id,
                overall_rating=int(overall_rating),
                confidence=confidence,
            )
        )

        logger.debug(
            "Assessment for %s: overall=%s confidence=%.2f",
            unit_id,
            overall_rating.name,
            confidence,
        )

        return assessment

    # -- Rating helper ------------------------------------------------------

    @staticmethod
    def _rate(
        value: float,
        thresholds: tuple[float, float, float, float],
    ) -> AssessmentRating:
        """Map a numeric *value* to an :class:`AssessmentRating`.

        Parameters
        ----------
        value : float
            The value to classify.
        thresholds : tuple[float, float, float, float]
            Four ascending boundaries:
            ``(vu_u, u_n, n_f, f_vf)`` where:
            - value < vu_u → VERY_UNFAVORABLE
            - vu_u <= value < u_n → UNFAVORABLE
            - u_n <= value < n_f → NEUTRAL
            - n_f <= value < f_vf → FAVORABLE
            - value >= f_vf → VERY_FAVORABLE
        """
        vu_u, u_n, n_f, f_vf = thresholds
        if value >= f_vf:
            return AssessmentRating.VERY_FAVORABLE
        if value >= n_f:
            return AssessmentRating.FAVORABLE
        if value >= u_n:
            return AssessmentRating.NEUTRAL
        if value >= vu_u:
            return AssessmentRating.UNFAVORABLE
        return AssessmentRating.VERY_UNFAVORABLE

    # -- State protocol -----------------------------------------------------

    def get_state(self) -> dict:
        """Serialize for checkpoint/restore."""
        return {}

    def set_state(self, state: dict) -> None:
        """Restore from checkpoint."""
        pass


# ---------------------------------------------------------------------------
# Opponent prediction (standalone, used by Sun Tzu school)
# ---------------------------------------------------------------------------


def predict_opponent_action_lanchester(
    opponent_power: float,
    own_power: float,
    opponent_morale: float,
) -> dict[str, float]:
    """Predict opponent action distribution using force-ratio heuristics.

    Simple one-step prediction: if opponent has superiority they likely
    attack; if outnumbered they likely defend or withdraw.

    Parameters
    ----------
    opponent_power : float
        Estimated opponent combat power.
    own_power : float
        Own combat power.
    opponent_morale : float
        Estimated opponent morale (0.0--1.0).

    Returns
    -------
    dict[str, float]
        Probability distribution over ``ATTACK``, ``DEFEND``, ``WITHDRAW``.
    """
    if own_power <= 0:
        return {"ATTACK": 0.8, "DEFEND": 0.15, "WITHDRAW": 0.05}

    ratio = opponent_power / own_power  # opponent's force ratio

    if ratio > 2.0:
        p_attack = 0.7
        p_defend = 0.2
        p_withdraw = 0.1
    elif ratio > 1.2:
        p_attack = 0.5
        p_defend = 0.35
        p_withdraw = 0.15
    elif ratio > 0.8:
        p_attack = 0.3
        p_defend = 0.5
        p_withdraw = 0.2
    elif ratio > 0.5:
        p_attack = 0.15
        p_defend = 0.45
        p_withdraw = 0.4
    else:
        p_attack = 0.05
        p_defend = 0.25
        p_withdraw = 0.7

    # Low morale shifts toward withdraw
    if opponent_morale < 0.3:
        shift = 0.2
        p_attack = max(0.0, p_attack - shift)
        p_withdraw = min(1.0, p_withdraw + shift)

    # Re-normalize
    total = p_attack + p_defend + p_withdraw
    return {
        "ATTACK": p_attack / total,
        "DEFEND": p_defend / total,
        "WITHDRAW": p_withdraw / total,
    }


# ---------------------------------------------------------------------------
# Desperation & escalation helpers (standalone, used by Phase 24d)
# ---------------------------------------------------------------------------


def compute_desperation_index(
    casualties_sustained: int,
    initial_strength: int,
    supply_state: float,
    avg_morale: float,
    stalemate_duration_s: float,
    domestic_pressure: float,
    casualty_weight: float = 0.30,
    supply_weight: float = 0.20,
    morale_weight: float = 0.20,
    stalemate_weight: float = 0.15,
    political_weight: float = 0.15,
    stalemate_normalize_s: float = 259200.0,
) -> float:
    """Compute desperation index as weighted factor composite.

    Same formula as escalation.ladder.EscalationLadder.compute_desperation
    but accessible from assessment context without importing escalation.
    """
    cas = min(1.0, max(0.0, casualties_sustained / max(initial_strength, 1)))
    sup = min(1.0, max(0.0, 1.0 - supply_state))
    mor = min(1.0, max(0.0, 1.0 - avg_morale))
    sta = min(1.0, max(0.0, stalemate_duration_s / stalemate_normalize_s))
    pol = min(1.0, max(0.0, domestic_pressure))
    return min(1.0, max(0.0,
        casualty_weight * cas
        + supply_weight * sup
        + morale_weight * mor
        + stalemate_weight * sta
        + political_weight * pol
    ))


def estimate_escalation_consequences(
    escalation_level: int,
    escalation_awareness: float,
) -> float:
    """Estimate consequence cost of being at given escalation level.

    Returns 0-1. High awareness -> accurate estimate -> inhibits escalation.
    Low awareness -> underestimates consequences.
    """
    raw_cost = escalation_level * 0.1  # 0.0 for level 0, 1.0 for level 10
    return min(1.0, raw_cost * escalation_awareness)
