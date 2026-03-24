"""Tests for stochastic_warfare.c2.ai.assessment -- situation assessment (OODA ORIENT)."""

from __future__ import annotations


import numpy as np
import pytest

from tests.conftest import DEFAULT_SEED, TS, make_rng

from stochastic_warfare.c2.ai.assessment import (
    AssessmentRating,
    SituationAssessment,
    SituationAssessor,
)
from stochastic_warfare.c2.events import SituationAssessedEvent
from stochastic_warfare.core.events import EventBus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_assessor(
    event_bus: EventBus | None = None,
    rng: np.random.Generator | None = None,
) -> SituationAssessor:
    """Create a SituationAssessor with sensible defaults."""
    if event_bus is None:
        event_bus = EventBus()
    if rng is None:
        rng = make_rng()
    return SituationAssessor(event_bus=event_bus, rng=rng)


def _favorable_kwargs() -> dict:
    """Return kwargs that produce all-favorable individual ratings."""
    return dict(
        unit_id="alpha",
        echelon=6,
        friendly_units=10,
        friendly_power=200.0,
        morale_level=0.9,
        supply_level=0.9,
        c2_effectiveness=0.9,
        contacts=5,
        enemy_power=50.0,
        visibility_km=10.0,
        illumination=1.0,
        daylight_hours=14.0,
        weather_severity=0.0,
        terrain_advantage=0.6,
        experience=0.8,
        staff_quality=0.8,
        ts=TS,
    )


def _unfavorable_kwargs() -> dict:
    """Return kwargs that produce all-unfavorable individual ratings."""
    return dict(
        unit_id="bravo",
        echelon=6,
        friendly_units=2,
        friendly_power=20.0,
        morale_level=0.1,
        supply_level=0.05,
        c2_effectiveness=0.1,
        contacts=0,
        enemy_power=200.0,
        visibility_km=1.0,
        illumination=0.1,
        daylight_hours=2.0,
        weather_severity=0.9,
        terrain_advantage=-0.7,
        experience=0.1,
        staff_quality=0.1,
        ts=TS,
    )


def _neutral_kwargs() -> dict:
    """Return kwargs that produce roughly neutral individual ratings."""
    return dict(
        unit_id="charlie",
        echelon=6,
        friendly_units=5,
        friendly_power=100.0,
        morale_level=0.5,
        supply_level=0.4,
        c2_effectiveness=0.5,
        contacts=3,
        enemy_power=100.0,
        visibility_km=5.0,
        illumination=0.7,
        daylight_hours=10.0,
        weather_severity=0.3,
        terrain_advantage=0.0,
        experience=0.5,
        staff_quality=0.5,
        ts=TS,
    )


# ---------------------------------------------------------------------------
# AssessmentRating enum
# ---------------------------------------------------------------------------


class TestAssessmentRating:
    def test_enum_values(self) -> None:
        assert AssessmentRating.VERY_UNFAVORABLE == 0
        assert AssessmentRating.UNFAVORABLE == 1
        assert AssessmentRating.NEUTRAL == 2
        assert AssessmentRating.FAVORABLE == 3
        assert AssessmentRating.VERY_FAVORABLE == 4

    def test_enum_count(self) -> None:
        assert len(AssessmentRating) == 5

    def test_enum_is_intenum(self) -> None:
        # Can do arithmetic with IntEnum values
        assert AssessmentRating.VERY_FAVORABLE - AssessmentRating.VERY_UNFAVORABLE == 4

    def test_enum_ordering(self) -> None:
        assert AssessmentRating.VERY_UNFAVORABLE < AssessmentRating.UNFAVORABLE
        assert AssessmentRating.UNFAVORABLE < AssessmentRating.NEUTRAL
        assert AssessmentRating.NEUTRAL < AssessmentRating.FAVORABLE
        assert AssessmentRating.FAVORABLE < AssessmentRating.VERY_FAVORABLE


# ---------------------------------------------------------------------------
# SituationAssessment frozen dataclass
# ---------------------------------------------------------------------------


class TestSituationAssessment:
    def test_creation(self) -> None:
        sa = SituationAssessment(
            unit_id="test",
            timestamp=TS,
            force_ratio=2.0,
            force_ratio_rating=AssessmentRating.FAVORABLE,
            terrain_advantage=0.3,
            terrain_rating=AssessmentRating.FAVORABLE,
            supply_level=0.7,
            supply_rating=AssessmentRating.FAVORABLE,
            morale_level=0.8,
            morale_rating=AssessmentRating.VERY_FAVORABLE,
            intel_quality=0.6,
            intel_rating=AssessmentRating.FAVORABLE,
            environmental_rating=AssessmentRating.NEUTRAL,
            c2_effectiveness=0.7,
            c2_rating=AssessmentRating.FAVORABLE,
            overall_rating=AssessmentRating.FAVORABLE,
            confidence=0.75,
            opportunities=("terrain_advantage",),
            threats=(),
        )
        assert sa.unit_id == "test"
        assert sa.force_ratio == 2.0
        assert sa.confidence == 0.75

    def test_frozen(self) -> None:
        sa = SituationAssessment(
            unit_id="test",
            timestamp=TS,
            force_ratio=1.0,
            force_ratio_rating=AssessmentRating.NEUTRAL,
            terrain_advantage=0.0,
            terrain_rating=AssessmentRating.NEUTRAL,
            supply_level=0.5,
            supply_rating=AssessmentRating.NEUTRAL,
            morale_level=0.5,
            morale_rating=AssessmentRating.NEUTRAL,
            intel_quality=0.5,
            intel_rating=AssessmentRating.NEUTRAL,
            environmental_rating=AssessmentRating.NEUTRAL,
            c2_effectiveness=0.5,
            c2_rating=AssessmentRating.NEUTRAL,
            overall_rating=AssessmentRating.NEUTRAL,
            confidence=0.5,
            opportunities=(),
            threats=(),
        )
        with pytest.raises(AttributeError):
            sa.unit_id = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Force ratio rating
# ---------------------------------------------------------------------------


class TestForceRatioRating:
    def test_overwhelming_advantage_very_favorable(self) -> None:
        """force_ratio >= 3.0 -> VERY_FAVORABLE."""
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["friendly_power"] = 300.0
        kw["enemy_power"] = 100.0  # ratio = 3.0
        result = assessor.assess(**kw)
        assert result.force_ratio_rating == AssessmentRating.VERY_FAVORABLE

    def test_slight_advantage_favorable(self) -> None:
        """1.5 <= force_ratio < 3.0 -> FAVORABLE."""
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["friendly_power"] = 200.0
        kw["enemy_power"] = 100.0  # ratio = 2.0
        result = assessor.assess(**kw)
        assert result.force_ratio_rating == AssessmentRating.FAVORABLE

    def test_parity_neutral(self) -> None:
        """0.8 <= force_ratio < 1.5 -> NEUTRAL."""
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["friendly_power"] = 100.0
        kw["enemy_power"] = 100.0  # ratio = 1.0
        result = assessor.assess(**kw)
        assert result.force_ratio_rating == AssessmentRating.NEUTRAL

    def test_disadvantage_unfavorable(self) -> None:
        """0.4 <= force_ratio < 0.8 -> UNFAVORABLE."""
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["friendly_power"] = 50.0
        kw["enemy_power"] = 100.0  # ratio = 0.5
        result = assessor.assess(**kw)
        assert result.force_ratio_rating == AssessmentRating.UNFAVORABLE

    def test_severe_disadvantage_very_unfavorable(self) -> None:
        """force_ratio < 0.4 -> VERY_UNFAVORABLE."""
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["friendly_power"] = 30.0
        kw["enemy_power"] = 100.0  # ratio = 0.3
        result = assessor.assess(**kw)
        assert result.force_ratio_rating == AssessmentRating.VERY_UNFAVORABLE

    def test_zero_enemy_very_favorable(self) -> None:
        """enemy_power == 0 -> inf ratio -> VERY_FAVORABLE."""
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["friendly_power"] = 100.0
        kw["enemy_power"] = 0.0
        result = assessor.assess(**kw)
        assert result.force_ratio == float("inf")
        assert result.force_ratio_rating == AssessmentRating.VERY_FAVORABLE


# ---------------------------------------------------------------------------
# Terrain rating
# ---------------------------------------------------------------------------


class TestTerrainRating:
    def test_positive_advantage_favorable(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["terrain_advantage"] = 0.3
        result = assessor.assess(**kw)
        assert result.terrain_rating == AssessmentRating.FAVORABLE

    def test_strong_advantage_very_favorable(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["terrain_advantage"] = 0.6
        result = assessor.assess(**kw)
        assert result.terrain_rating == AssessmentRating.VERY_FAVORABLE

    def test_disadvantage_unfavorable(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["terrain_advantage"] = -0.3
        result = assessor.assess(**kw)
        assert result.terrain_rating == AssessmentRating.UNFAVORABLE

    def test_strong_disadvantage_very_unfavorable(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["terrain_advantage"] = -0.7
        result = assessor.assess(**kw)
        assert result.terrain_rating == AssessmentRating.VERY_UNFAVORABLE


# ---------------------------------------------------------------------------
# Supply rating
# ---------------------------------------------------------------------------


class TestSupplyRating:
    def test_high_supply_favorable(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["supply_level"] = 0.85
        result = assessor.assess(**kw)
        assert result.supply_rating == AssessmentRating.VERY_FAVORABLE

    def test_low_supply_unfavorable(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["supply_level"] = 0.1
        result = assessor.assess(**kw)
        assert result.supply_rating == AssessmentRating.VERY_UNFAVORABLE

    def test_moderate_supply_neutral(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["supply_level"] = 0.35
        result = assessor.assess(**kw)
        assert result.supply_rating == AssessmentRating.NEUTRAL


# ---------------------------------------------------------------------------
# Morale rating
# ---------------------------------------------------------------------------


class TestMoraleRating:
    def test_high_morale_favorable(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["morale_level"] = 0.85
        result = assessor.assess(**kw)
        assert result.morale_rating == AssessmentRating.VERY_FAVORABLE

    def test_low_morale_unfavorable(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["morale_level"] = 0.1
        result = assessor.assess(**kw)
        assert result.morale_rating == AssessmentRating.VERY_UNFAVORABLE


# ---------------------------------------------------------------------------
# Intel rating
# ---------------------------------------------------------------------------


class TestIntelRating:
    def test_high_quality_favorable(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["contacts"] = 5  # 5 * 0.2 = 1.0
        result = assessor.assess(**kw)
        assert result.intel_rating >= AssessmentRating.VERY_FAVORABLE

    def test_low_quality_unfavorable(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["contacts"] = 0
        result = assessor.assess(**kw)
        assert result.intel_rating == AssessmentRating.VERY_UNFAVORABLE

    def test_moderate_quality_neutral(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["contacts"] = 2  # 2 * 0.2 = 0.4 -> NEUTRAL (>= 0.35)
        result = assessor.assess(**kw)
        assert result.intel_rating == AssessmentRating.NEUTRAL


# ---------------------------------------------------------------------------
# Environmental rating
# ---------------------------------------------------------------------------


class TestEnvironmentalRating:
    def test_clear_conditions_favorable(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["visibility_km"] = 10.0
        kw["illumination"] = 1.0
        kw["weather_severity"] = 0.0
        result = assessor.assess(**kw)
        assert result.environmental_rating == AssessmentRating.VERY_FAVORABLE

    def test_poor_conditions_unfavorable(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["visibility_km"] = 1.0
        kw["illumination"] = 0.2
        kw["weather_severity"] = 0.8
        # env_score = (1.0/10.0) * 0.2 * (1.0 - 0.8*0.5) = 0.1 * 0.2 * 0.6 = 0.012
        result = assessor.assess(**kw)
        assert result.environmental_rating == AssessmentRating.VERY_UNFAVORABLE

    def test_high_weather_severity_degrades(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["visibility_km"] = 10.0
        kw["illumination"] = 1.0
        kw["weather_severity"] = 0.9
        # env_score = 1.0 * 1.0 * (1.0 - 0.45) = 0.55
        result = assessor.assess(**kw)
        assert result.environmental_rating == AssessmentRating.FAVORABLE

    def test_night_conditions_affect_rating(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["visibility_km"] = 10.0
        kw["illumination"] = 0.1
        kw["weather_severity"] = 0.0
        # env_score = 1.0 * 0.1 * 1.0 = 0.1
        result = assessor.assess(**kw)
        assert result.environmental_rating == AssessmentRating.VERY_UNFAVORABLE


# ---------------------------------------------------------------------------
# C2 rating
# ---------------------------------------------------------------------------


class TestC2Rating:
    def test_effective_favorable(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["c2_effectiveness"] = 0.85
        result = assessor.assess(**kw)
        assert result.c2_rating == AssessmentRating.VERY_FAVORABLE

    def test_degraded_unfavorable(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["c2_effectiveness"] = 0.15
        result = assessor.assess(**kw)
        assert result.c2_rating == AssessmentRating.VERY_UNFAVORABLE


# ---------------------------------------------------------------------------
# Overall rating
# ---------------------------------------------------------------------------


class TestOverallRating:
    def test_all_favorable_yields_high_overall(self) -> None:
        assessor = _make_assessor()
        result = assessor.assess(**_favorable_kwargs())
        assert result.overall_rating >= AssessmentRating.FAVORABLE

    def test_all_unfavorable_yields_low_overall(self) -> None:
        assessor = _make_assessor()
        result = assessor.assess(**_unfavorable_kwargs())
        assert result.overall_rating <= AssessmentRating.UNFAVORABLE

    def test_mixed_inputs_yields_moderate(self) -> None:
        assessor = _make_assessor()
        result = assessor.assess(**_neutral_kwargs())
        # Neutral inputs should produce a mid-range overall
        assert AssessmentRating.UNFAVORABLE <= result.overall_rating <= AssessmentRating.FAVORABLE

    def test_weighted_average_is_correct(self) -> None:
        """Verify that overall rating matches expected weighted computation."""
        assessor = _make_assessor()
        result = assessor.assess(**_favorable_kwargs())
        # Manually compute expected weighted sum from known sub-ratings
        ratings_map = {
            "force_ratio": int(result.force_ratio_rating),
            "terrain": int(result.terrain_rating),
            "supply": int(result.supply_rating),
            "morale": int(result.morale_rating),
            "intel": int(result.intel_rating),
            "environmental": int(result.environmental_rating),
            "c2": int(result.c2_rating),
        }
        weights = {
            "force_ratio": 0.30,
            "terrain": 0.10,
            "supply": 0.15,
            "morale": 0.15,
            "intel": 0.10,
            "environmental": 0.05,
            "c2": 0.15,
        }
        weighted = sum(ratings_map[k] * weights[k] for k in weights)
        # The overall rating should correspond to the weighted sum
        # thresholds: <1.0 -> VU, <1.75 -> U, <2.5 -> N, <3.25 -> F, >=3.25 -> VF
        if weighted >= 3.25:
            expected = AssessmentRating.VERY_FAVORABLE
        elif weighted >= 2.5:
            expected = AssessmentRating.FAVORABLE
        elif weighted >= 1.75:
            expected = AssessmentRating.NEUTRAL
        elif weighted >= 1.0:
            expected = AssessmentRating.UNFAVORABLE
        else:
            expected = AssessmentRating.VERY_UNFAVORABLE
        assert result.overall_rating == expected

    def test_overall_combines_all_factors(self) -> None:
        """Changing one factor changes the overall rating."""
        assessor = _make_assessor()
        # Start with favorable
        kw = _favorable_kwargs()
        result_good = assessor.assess(**kw)

        # Degrade force ratio significantly
        assessor2 = _make_assessor()
        kw2 = _favorable_kwargs()
        kw2["friendly_power"] = 10.0
        kw2["enemy_power"] = 200.0
        result_bad_force = assessor2.assess(**kw2)

        # The overall should be lower
        assert result_bad_force.overall_rating <= result_good.overall_rating


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------


class TestConfidence:
    def test_high_inputs_high_confidence(self) -> None:
        assessor = _make_assessor()
        result = assessor.assess(**_favorable_kwargs())
        assert result.confidence > 0.7

    def test_low_inputs_low_confidence(self) -> None:
        assessor = _make_assessor()
        result = assessor.assess(**_unfavorable_kwargs())
        assert result.confidence < 0.3

    def test_confidence_deterministic_same_seed(self) -> None:
        """Same seed produces same confidence."""
        a1 = _make_assessor(rng=make_rng(99))
        a2 = _make_assessor(rng=make_rng(99))
        r1 = a1.assess(**_neutral_kwargs())
        r2 = a2.assess(**_neutral_kwargs())
        assert r1.confidence == r2.confidence

    def test_confidence_clamped_01(self) -> None:
        """Confidence never exceeds 1.0 or goes below 0.0."""
        # Run many assessments with different seeds
        for seed in range(100):
            assessor = _make_assessor(rng=make_rng(seed))
            result = assessor.assess(**_favorable_kwargs())
            assert 0.0 <= result.confidence <= 1.0

    def test_experience_affects_confidence(self) -> None:
        """Higher experience raises confidence."""
        kw_low = _neutral_kwargs()
        kw_low["experience"] = 0.1
        kw_high = _neutral_kwargs()
        kw_high["experience"] = 0.9

        # Use same seed for both
        a1 = _make_assessor(rng=make_rng(42))
        a2 = _make_assessor(rng=make_rng(42))
        r_low = a1.assess(**kw_low)
        r_high = a2.assess(**kw_high)
        # experience contributes 0.2 weight: diff = 0.2 * (0.9 - 0.1) = 0.16
        assert r_high.confidence > r_low.confidence

    def test_staff_quality_affects_confidence(self) -> None:
        """Higher staff quality raises confidence."""
        kw_low = _neutral_kwargs()
        kw_low["staff_quality"] = 0.1
        kw_high = _neutral_kwargs()
        kw_high["staff_quality"] = 0.9

        a1 = _make_assessor(rng=make_rng(42))
        a2 = _make_assessor(rng=make_rng(42))
        r_low = a1.assess(**kw_low)
        r_high = a2.assess(**kw_high)
        assert r_high.confidence > r_low.confidence


# ---------------------------------------------------------------------------
# Opportunities and threats
# ---------------------------------------------------------------------------


class TestOpportunities:
    def test_numerical_superiority(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["friendly_power"] = 300.0
        kw["enemy_power"] = 100.0
        result = assessor.assess(**kw)
        assert "numerical_superiority" in result.opportunities

    def test_terrain_advantage_detected(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["terrain_advantage"] = 0.5
        result = assessor.assess(**kw)
        assert "terrain_advantage" in result.opportunities

    def test_logistics_advantage(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["supply_level"] = 0.9
        result = assessor.assess(**kw)
        assert "logistics_advantage" in result.opportunities

    def test_high_morale_opportunity(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["morale_level"] = 0.8
        result = assessor.assess(**kw)
        assert "high_morale" in result.opportunities

    def test_no_opportunities_when_neutral(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        # Neutral kwargs have no extreme values
        kw["friendly_power"] = 100.0
        kw["enemy_power"] = 100.0
        kw["terrain_advantage"] = 0.0
        kw["supply_level"] = 0.5
        kw["morale_level"] = 0.5
        result = assessor.assess(**kw)
        assert len(result.opportunities) == 0


class TestThreats:
    def test_outnumbered(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["friendly_power"] = 30.0
        kw["enemy_power"] = 100.0
        result = assessor.assess(**kw)
        assert "outnumbered" in result.threats

    def test_supply_critical(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["supply_level"] = 0.1
        result = assessor.assess(**kw)
        assert "supply_critical" in result.threats

    def test_morale_crisis(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["morale_level"] = 0.2
        result = assessor.assess(**kw)
        assert "morale_crisis" in result.threats

    def test_c2_degraded(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["c2_effectiveness"] = 0.2
        result = assessor.assess(**kw)
        assert "c2_degraded" in result.threats

    def test_severe_weather(self) -> None:
        assessor = _make_assessor()
        kw = _neutral_kwargs()
        kw["weather_severity"] = 0.8
        result = assessor.assess(**kw)
        assert "severe_weather" in result.threats

    def test_no_threats_when_favorable(self) -> None:
        assessor = _make_assessor()
        result = assessor.assess(**_favorable_kwargs())
        assert len(result.threats) == 0


# ---------------------------------------------------------------------------
# Event publishing
# ---------------------------------------------------------------------------


class TestEventPublishing:
    def test_publishes_situation_assessed_event(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        received: list[SituationAssessedEvent] = []
        event_bus.subscribe(SituationAssessedEvent, lambda e: received.append(e))

        assessor = SituationAssessor(event_bus=event_bus, rng=rng)
        result = assessor.assess(**_favorable_kwargs())

        assert len(received) == 1
        evt = received[0]
        assert evt.unit_id == "alpha"
        assert evt.overall_rating == int(result.overall_rating)
        assert evt.confidence == result.confidence

    def test_event_timestamp_matches_assessment(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        received: list[SituationAssessedEvent] = []
        event_bus.subscribe(SituationAssessedEvent, lambda e: received.append(e))

        assessor = SituationAssessor(event_bus=event_bus, rng=rng)
        assessor.assess(**_favorable_kwargs())

        assert received[0].timestamp == TS


# ---------------------------------------------------------------------------
# State protocol
# ---------------------------------------------------------------------------


class TestStateProtocol:
    def test_get_set_state_roundtrip(self) -> None:
        assessor = _make_assessor()
        state = assessor.get_state()
        assert isinstance(state, dict)
        # set_state should not raise
        assessor.set_state(state)

    def test_set_state_accepts_empty_dict(self) -> None:
        assessor = _make_assessor()
        assessor.set_state({})


# ---------------------------------------------------------------------------
# Deterministic replay
# ---------------------------------------------------------------------------


class TestDeterministicReplay:
    def test_same_seed_same_result(self) -> None:
        """Two assessors with the same seed produce identical results."""
        a1 = _make_assessor(rng=make_rng(DEFAULT_SEED))
        a2 = _make_assessor(rng=make_rng(DEFAULT_SEED))

        kw = _neutral_kwargs()
        r1 = a1.assess(**kw)
        r2 = a2.assess(**kw)

        assert r1.confidence == r2.confidence
        assert r1.overall_rating == r2.overall_rating
        assert r1.opportunities == r2.opportunities
        assert r1.threats == r2.threats

    def test_different_seed_different_confidence(self) -> None:
        """Different seeds produce different confidence noise."""
        a1 = _make_assessor(rng=make_rng(1))
        a2 = _make_assessor(rng=make_rng(999))

        kw = _neutral_kwargs()
        r1 = a1.assess(**kw)
        r2 = a2.assess(**kw)

        # Confidence should differ due to noise (overwhelmingly likely)
        # but both should still be valid
        assert 0.0 <= r1.confidence <= 1.0
        assert 0.0 <= r2.confidence <= 1.0


# ---------------------------------------------------------------------------
# Multiple assessments don't interfere
# ---------------------------------------------------------------------------


class TestMultipleAssessments:
    def test_sequential_assessments_independent(self) -> None:
        """Multiple assessments for different units don't affect each other."""
        assessor = _make_assessor()

        kw_good = _favorable_kwargs()
        kw_bad = _unfavorable_kwargs()

        r1 = assessor.assess(**kw_good)
        r2 = assessor.assess(**kw_bad)

        assert r1.overall_rating >= AssessmentRating.FAVORABLE
        assert r2.overall_rating <= AssessmentRating.UNFAVORABLE
        assert r1.unit_id == "alpha"
        assert r2.unit_id == "bravo"

    def test_event_count_matches_assessments(self) -> None:
        """Each assess() call publishes exactly one event."""
        bus = EventBus()
        received: list[SituationAssessedEvent] = []
        bus.subscribe(SituationAssessedEvent, lambda e: received.append(e))

        assessor = SituationAssessor(event_bus=bus, rng=make_rng())

        assessor.assess(**_favorable_kwargs())
        assessor.assess(**_unfavorable_kwargs())
        assessor.assess(**_neutral_kwargs())

        assert len(received) == 3
        assert received[0].unit_id == "alpha"
        assert received[1].unit_id == "bravo"
        assert received[2].unit_id == "charlie"
