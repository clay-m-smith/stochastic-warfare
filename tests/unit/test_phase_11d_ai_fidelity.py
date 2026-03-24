"""Tests for Phase 11d — AI Fidelity fixes.

1. Echelon hardcode fix: _decide_brigade_div passes actual echelon through.
2. OODA tactical acceleration: tactical_mult param shortens phase durations.

Uses shared fixtures from conftest.py.
"""

from __future__ import annotations


import numpy as np
import pytest

from stochastic_warfare.c2.ai.assessment import AssessmentRating, SituationAssessment
from stochastic_warfare.c2.ai.commander import CommanderPersonality
from stochastic_warfare.c2.ai.decisions import DecisionEngine
from stochastic_warfare.c2.ai.ooda import OODAConfig, OODALoopEngine, OODAPhase
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.entities.organization.echelons import EchelonLevel

from tests.conftest import TS, make_rng


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_assessment(
    force_ratio: float = 1.5,
    overall: AssessmentRating = AssessmentRating.FAVORABLE,
    morale: float = 0.7,
    supply: float = 0.8,
    c2: float = 0.8,
    terrain_adv: float = 0.0,
    confidence: float = 0.7,
) -> SituationAssessment:
    return SituationAssessment(
        unit_id="unit_a",
        timestamp=TS,
        force_ratio=force_ratio,
        force_ratio_rating=AssessmentRating.FAVORABLE,
        terrain_advantage=terrain_adv,
        terrain_rating=AssessmentRating.NEUTRAL,
        supply_level=supply,
        supply_rating=AssessmentRating.FAVORABLE,
        morale_level=morale,
        morale_rating=AssessmentRating.FAVORABLE,
        intel_quality=0.6,
        intel_rating=AssessmentRating.FAVORABLE,
        environmental_rating=AssessmentRating.NEUTRAL,
        c2_effectiveness=c2,
        c2_rating=AssessmentRating.FAVORABLE,
        overall_rating=overall,
        confidence=confidence,
        threats=(),
        opportunities=(),
    )


def _make_personality(**kwargs: float) -> CommanderPersonality:
    defaults = dict(
        profile_id="test",
        display_name="Test",
        description="test",
        aggression=0.5,
        caution=0.5,
        flexibility=0.5,
        initiative=0.5,
        experience=0.5,
        stress_tolerance=0.5,
        decision_speed=0.5,
        risk_acceptance=0.5,
    )
    defaults.update(kwargs)
    return CommanderPersonality(**defaults)


# ---------------------------------------------------------------------------
# Test 15: Echelon hardcode fix
# ---------------------------------------------------------------------------


class TestEchelonHardcodeFix:
    """Verify _decide_brigade_div passes actual echelon, not hardcoded 9."""

    def test_brigade_returns_echelon_8(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = DecisionEngine(event_bus, rng)
        assessment = _make_assessment()
        result = engine.decide(
            unit_id="bde_1",
            echelon=EchelonLevel.BRIGADE,
            assessment=assessment,
            personality=None,
            doctrine=None,
            ts=TS,
        )
        assert result.echelon_level == EchelonLevel.BRIGADE

    def test_division_returns_echelon_9(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = DecisionEngine(event_bus, rng)
        assessment = _make_assessment()
        result = engine.decide(
            unit_id="div_1",
            echelon=EchelonLevel.DIVISION,
            assessment=assessment,
            personality=None,
            doctrine=None,
            ts=TS,
        )
        assert result.echelon_level == EchelonLevel.DIVISION

    def test_brigade_echelon_differs_from_division(
        self, event_bus: EventBus, rng: np.random.Generator,
    ) -> None:
        engine = DecisionEngine(event_bus, rng)
        assessment = _make_assessment()
        bde = engine.decide("bde_1", EchelonLevel.BRIGADE, assessment, None, None, ts=TS)
        # Need fresh RNG for independent result
        engine2 = DecisionEngine(event_bus, make_rng())
        div = engine2.decide("div_1", EchelonLevel.DIVISION, assessment, None, None, ts=TS)
        assert bde.echelon_level == 8
        assert div.echelon_level == 9
        assert bde.echelon_level != div.echelon_level


# ---------------------------------------------------------------------------
# Test 14: OODA tactical acceleration
# ---------------------------------------------------------------------------


class TestOODATacticalAcceleration:
    """Verify tactical_mult parameter accelerates OODA phase durations."""

    def test_tactical_mult_shortens_duration(self, event_bus: EventBus) -> None:
        """tactical_mult < 1 produces shorter durations than 1.0."""
        # Use same seed for both to compare apples-to-apples
        engine_normal = OODALoopEngine(event_bus, make_rng(99), OODAConfig(timing_sigma=0.0))
        engine_fast = OODALoopEngine(event_bus, make_rng(99), OODAConfig(timing_sigma=0.0))

        dur_normal = engine_normal.compute_phase_duration(
            EchelonLevel.BATTALION, OODAPhase.OBSERVE, tactical_mult=1.0,
        )
        dur_fast = engine_fast.compute_phase_duration(
            EchelonLevel.BATTALION, OODAPhase.OBSERVE, tactical_mult=0.5,
        )
        assert dur_fast == pytest.approx(dur_normal * 0.5, rel=1e-9)

    def test_default_tactical_mult_no_change(self, event_bus: EventBus) -> None:
        """Default tactical_mult=1.0 preserves baseline duration."""
        config = OODAConfig(timing_sigma=0.0)
        engine = OODALoopEngine(event_bus, make_rng(42), config)
        base = config.base_durations_s["BATTALION"]["OBSERVE"]
        dur = engine.compute_phase_duration(
            EchelonLevel.BATTALION, OODAPhase.OBSERVE, tactical_mult=1.0,
        )
        assert dur == pytest.approx(base, rel=1e-9)

    def test_tactical_mult_stacks_with_personality(self, event_bus: EventBus) -> None:
        """tactical_mult stacks multiplicatively with personality_mult."""
        config = OODAConfig(timing_sigma=0.0)
        engine = OODALoopEngine(event_bus, make_rng(42), config)
        base = config.base_durations_s["BATTALION"]["OBSERVE"]
        dur = engine.compute_phase_duration(
            EchelonLevel.BATTALION, OODAPhase.OBSERVE,
            personality_mult=2.0, tactical_mult=0.5,
        )
        # 2.0 * 0.5 = 1.0 → should equal base
        assert dur == pytest.approx(base, rel=1e-9)

    def test_start_phase_accepts_tactical_mult(self, event_bus: EventBus) -> None:
        """start_phase uses tactical_mult to compute shorter timers."""
        config = OODAConfig(timing_sigma=0.0, tactical_acceleration=0.5)
        engine = OODALoopEngine(event_bus, make_rng(42), config)
        engine.register_commander("cmd_1", EchelonLevel.BATTALION)

        engine.start_phase(
            "cmd_1", OODAPhase.OBSERVE,
            tactical_mult=config.tactical_acceleration, ts=TS,
        )

        # The timer should be base * 0.5
        base = config.base_durations_s["BATTALION"]["OBSERVE"]
        state = engine.get_state()
        timer = state["commanders"]["cmd_1"]["phase_timer"]
        assert timer == pytest.approx(base * 0.5, rel=1e-9)

    def test_config_tactical_acceleration_default(self) -> None:
        """OODAConfig has tactical_acceleration=0.5 by default."""
        config = OODAConfig()
        assert config.tactical_acceleration == 0.5

    def test_tactical_acceleration_backward_compatible(self, event_bus: EventBus) -> None:
        """Without tactical_mult, behavior is unchanged (mult=1.0)."""
        config = OODAConfig(timing_sigma=0.0)
        engine = OODALoopEngine(event_bus, make_rng(42), config)
        engine.register_commander("cmd_1", EchelonLevel.BATTALION)

        # start_phase without tactical_mult should use default 1.0
        engine.start_phase("cmd_1", OODAPhase.OBSERVE, ts=TS)

        base = config.base_durations_s["BATTALION"]["OBSERVE"]
        state = engine.get_state()
        timer = state["commanders"]["cmd_1"]["phase_timer"]
        assert timer == pytest.approx(base, rel=1e-9)
