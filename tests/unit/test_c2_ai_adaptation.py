"""Tests for stochastic_warfare.c2.ai.adaptation -- plan adaptation engine."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from tests.conftest import DEFAULT_SEED, TS, make_rng

from stochastic_warfare.c2.ai.adaptation import (
    AdaptationAction,
    AdaptationConfig,
    AdaptationEngine,
    AdaptationTrigger,
)
from stochastic_warfare.c2.ai.assessment import AssessmentRating, SituationAssessment
from stochastic_warfare.c2.ai.commander import CommanderPersonality
from stochastic_warfare.c2.events import PlanAdaptedEvent
from stochastic_warfare.core.events import EventBus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_assessment(
    force_ratio: float = 1.5,
    overall: AssessmentRating = AssessmentRating.FAVORABLE,
    morale: float = 0.7,
    supply: float = 0.8,
    intel: float = 0.6,
    c2: float = 0.8,
    terrain_adv: float = 0.0,
    confidence: float = 0.7,
    opportunities: tuple[str, ...] = (),
    threats: tuple[str, ...] = (),
    unit_id: str = "unit_a",
) -> SituationAssessment:
    return SituationAssessment(
        unit_id=unit_id,
        timestamp=TS,
        force_ratio=force_ratio,
        force_ratio_rating=AssessmentRating.FAVORABLE,
        terrain_advantage=terrain_adv,
        terrain_rating=AssessmentRating.NEUTRAL,
        supply_level=supply,
        supply_rating=AssessmentRating.FAVORABLE,
        morale_level=morale,
        morale_rating=AssessmentRating.FAVORABLE,
        intel_quality=intel,
        intel_rating=AssessmentRating.FAVORABLE,
        environmental_rating=AssessmentRating.NEUTRAL,
        c2_effectiveness=c2,
        c2_rating=AssessmentRating.FAVORABLE,
        overall_rating=overall,
        confidence=confidence,
        opportunities=tuple(opportunities),
        threats=tuple(threats),
    )


def _make_personality(
    aggression: float = 0.5,
    caution: float = 0.5,
    flexibility: float = 0.5,
    initiative: float = 0.5,
    experience: float = 0.5,
    **kw: object,
) -> CommanderPersonality:
    return CommanderPersonality(
        profile_id="test",
        display_name="Test",
        description="Test",
        aggression=aggression,
        caution=caution,
        flexibility=flexibility,
        initiative=initiative,
        experience=experience,
        **kw,
    )


def _make_engine(
    event_bus: EventBus | None = None,
    rng: np.random.Generator | None = None,
    config: AdaptationConfig | None = None,
) -> AdaptationEngine:
    if event_bus is None:
        event_bus = EventBus()
    if rng is None:
        rng = make_rng()
    return AdaptationEngine(event_bus=event_bus, rng=rng, config=config)


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestAdaptationTrigger:
    def test_enum_values(self) -> None:
        assert AdaptationTrigger.CASUALTIES == 0
        assert AdaptationTrigger.FORCE_RATIO_CHANGE == 1
        assert AdaptationTrigger.SUPPLY_CRISIS == 2
        assert AdaptationTrigger.MORALE_BREAK == 3
        assert AdaptationTrigger.OPPORTUNITY == 4
        assert AdaptationTrigger.SURPRISE_CONTACT == 5
        assert AdaptationTrigger.C2_DISRUPTION == 6

    def test_enum_count(self) -> None:
        assert len(AdaptationTrigger) == 7


class TestAdaptationAction:
    def test_enum_values(self) -> None:
        assert AdaptationAction.CONTINUE == 0
        assert AdaptationAction.ADJUST_TEMPO == 1
        assert AdaptationAction.REPOSITION == 2
        assert AdaptationAction.REINFORCE == 3
        assert AdaptationAction.WITHDRAW == 4
        assert AdaptationAction.COUNTERATTACK == 5
        assert AdaptationAction.ISSUE_FRAGO == 6

    def test_enum_count(self) -> None:
        assert len(AdaptationAction) == 7


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestAdaptationConfig:
    def test_defaults(self) -> None:
        cfg = AdaptationConfig()
        assert cfg.casualty_threshold == 0.20
        assert cfg.force_ratio_change_threshold == 0.50
        assert cfg.supply_critical_threshold == 0.15
        assert cfg.morale_break_threshold == 0.25
        assert cfg.flexibility_weight == 0.3

    def test_custom_values(self) -> None:
        cfg = AdaptationConfig(
            casualty_threshold=0.10,
            supply_critical_threshold=0.30,
        )
        assert cfg.casualty_threshold == 0.10
        assert cfg.supply_critical_threshold == 0.30


# ---------------------------------------------------------------------------
# Casualty triggers
# ---------------------------------------------------------------------------


class TestCasualtyTrigger:
    def test_high_casualties_withdraw(self) -> None:
        """Extreme casualties (>0.4) always triggers WITHDRAW."""
        engine = _make_engine()
        current = _make_assessment()
        personality = _make_personality(aggression=0.3, caution=0.3, flexibility=0.0)
        action, trigger = engine.check_adaptation_needed(
            "unit_a", current, None, personality, "attack", 0.50, ts=TS,
        )
        assert trigger == AdaptationTrigger.CASUALTIES
        assert action == AdaptationAction.WITHDRAW

    def test_moderate_casualties_reposition(self) -> None:
        """Moderate casualties (>0.2, <=0.4) triggers REPOSITION."""
        engine = _make_engine()
        current = _make_assessment()
        personality = _make_personality(aggression=0.3, caution=0.3, flexibility=0.0)
        action, trigger = engine.check_adaptation_needed(
            "unit_a", current, None, personality, "attack", 0.25, ts=TS,
        )
        assert trigger == AdaptationTrigger.CASUALTIES
        assert action == AdaptationAction.REPOSITION

    def test_casualties_below_threshold_no_trigger(self) -> None:
        """Casualties below threshold: no trigger fires."""
        engine = _make_engine()
        current = _make_assessment()
        personality = _make_personality(flexibility=0.0)
        action, trigger = engine.check_adaptation_needed(
            "unit_a", current, None, personality, "attack", 0.10, ts=TS,
        )
        assert action == AdaptationAction.CONTINUE
        assert trigger is None

    def test_aggressive_personality_casualties_adjust_tempo(self) -> None:
        """Aggressive commander with moderate casualties -> ADJUST_TEMPO."""
        engine = _make_engine()
        current = _make_assessment()
        personality = _make_personality(aggression=0.8, caution=0.2, flexibility=0.0)
        action, trigger = engine.check_adaptation_needed(
            "unit_a", current, None, personality, "attack", 0.25, ts=TS,
        )
        assert trigger == AdaptationTrigger.CASUALTIES
        assert action == AdaptationAction.ADJUST_TEMPO

    def test_cautious_personality_casualties_withdraw(self) -> None:
        """Cautious commander with moderate casualties -> WITHDRAW."""
        engine = _make_engine()
        current = _make_assessment()
        personality = _make_personality(aggression=0.2, caution=0.8, flexibility=0.0)
        action, trigger = engine.check_adaptation_needed(
            "unit_a", current, None, personality, "attack", 0.25, ts=TS,
        )
        assert trigger == AdaptationTrigger.CASUALTIES
        assert action == AdaptationAction.WITHDRAW

    def test_extreme_casualties_always_withdraw(self) -> None:
        """Even aggressive commander withdraws at extreme casualties."""
        engine = _make_engine()
        current = _make_assessment()
        personality = _make_personality(aggression=0.9, caution=0.1, flexibility=0.0)
        action, trigger = engine.check_adaptation_needed(
            "unit_a", current, None, personality, "attack", 0.50, ts=TS,
        )
        assert trigger == AdaptationTrigger.CASUALTIES
        assert action == AdaptationAction.WITHDRAW


# ---------------------------------------------------------------------------
# Force ratio change triggers
# ---------------------------------------------------------------------------


class TestForceRatioChangeTrigger:
    def test_ratio_improved_counterattack(self) -> None:
        """Force ratio improves with aggressive commander -> COUNTERATTACK."""
        engine = _make_engine()
        previous = _make_assessment(force_ratio=1.0)
        current = _make_assessment(force_ratio=2.0)
        personality = _make_personality(aggression=0.8, caution=0.2, flexibility=0.0)
        action, trigger = engine.check_adaptation_needed(
            "unit_a", current, previous, personality, "defend", 0.0, ts=TS,
        )
        assert trigger == AdaptationTrigger.FORCE_RATIO_CHANGE
        assert action == AdaptationAction.COUNTERATTACK

    def test_ratio_improved_adjust_tempo(self) -> None:
        """Force ratio improves with moderate commander -> ADJUST_TEMPO."""
        engine = _make_engine()
        previous = _make_assessment(force_ratio=1.0)
        current = _make_assessment(force_ratio=2.0)
        personality = _make_personality(aggression=0.4, caution=0.4, flexibility=0.0)
        action, trigger = engine.check_adaptation_needed(
            "unit_a", current, previous, personality, "defend", 0.0, ts=TS,
        )
        assert trigger == AdaptationTrigger.FORCE_RATIO_CHANGE
        assert action == AdaptationAction.ADJUST_TEMPO

    def test_ratio_worsened_reposition(self) -> None:
        """Force ratio worsens with moderate commander -> REPOSITION."""
        engine = _make_engine()
        previous = _make_assessment(force_ratio=2.0)
        current = _make_assessment(force_ratio=0.8)
        personality = _make_personality(aggression=0.4, caution=0.4, flexibility=0.0)
        action, trigger = engine.check_adaptation_needed(
            "unit_a", current, previous, personality, "attack", 0.0, ts=TS,
        )
        assert trigger == AdaptationTrigger.FORCE_RATIO_CHANGE
        assert action == AdaptationAction.REPOSITION

    def test_ratio_worsened_cautious_withdraw(self) -> None:
        """Force ratio worsens with cautious commander -> WITHDRAW."""
        engine = _make_engine()
        previous = _make_assessment(force_ratio=2.0)
        current = _make_assessment(force_ratio=0.8)
        personality = _make_personality(aggression=0.2, caution=0.8, flexibility=0.0)
        action, trigger = engine.check_adaptation_needed(
            "unit_a", current, previous, personality, "attack", 0.0, ts=TS,
        )
        assert trigger == AdaptationTrigger.FORCE_RATIO_CHANGE
        assert action == AdaptationAction.WITHDRAW

    def test_ratio_unchanged_no_trigger(self) -> None:
        """Small force ratio change does not trigger."""
        engine = _make_engine()
        previous = _make_assessment(force_ratio=1.5)
        current = _make_assessment(force_ratio=1.6)
        personality = _make_personality(flexibility=0.0)
        action, trigger = engine.check_adaptation_needed(
            "unit_a", current, previous, personality, "defend", 0.0, ts=TS,
        )
        assert action == AdaptationAction.CONTINUE
        assert trigger is None


# ---------------------------------------------------------------------------
# Supply crisis trigger
# ---------------------------------------------------------------------------


class TestSupplyCrisisTrigger:
    def test_supply_crisis_reposition(self) -> None:
        """Low supply with moderate commander -> REPOSITION."""
        engine = _make_engine()
        current = _make_assessment(supply=0.10)
        personality = _make_personality(aggression=0.4, caution=0.4, flexibility=0.0)
        action, trigger = engine.check_adaptation_needed(
            "unit_a", current, None, personality, "attack", 0.0, ts=TS,
        )
        assert trigger == AdaptationTrigger.SUPPLY_CRISIS
        assert action == AdaptationAction.REPOSITION

    def test_supply_crisis_cautious_withdraw(self) -> None:
        """Low supply with cautious commander -> WITHDRAW."""
        engine = _make_engine()
        current = _make_assessment(supply=0.10)
        personality = _make_personality(aggression=0.2, caution=0.8, flexibility=0.0)
        action, trigger = engine.check_adaptation_needed(
            "unit_a", current, None, personality, "attack", 0.0, ts=TS,
        )
        assert trigger == AdaptationTrigger.SUPPLY_CRISIS
        assert action == AdaptationAction.WITHDRAW


# ---------------------------------------------------------------------------
# Morale break trigger
# ---------------------------------------------------------------------------


class TestMoraleBreakTrigger:
    def test_morale_break_withdraw(self) -> None:
        """Low morale -> WITHDRAW."""
        engine = _make_engine()
        current = _make_assessment(morale=0.15)
        personality = _make_personality(flexibility=0.0)
        action, trigger = engine.check_adaptation_needed(
            "unit_a", current, None, personality, "attack", 0.0, ts=TS,
        )
        assert trigger == AdaptationTrigger.MORALE_BREAK
        assert action == AdaptationAction.WITHDRAW


# ---------------------------------------------------------------------------
# Opportunity trigger
# ---------------------------------------------------------------------------


class TestOpportunityTrigger:
    def test_opportunity_aggressive_counterattack(self) -> None:
        """Situation improves to FAVORABLE with aggressive commander -> COUNTERATTACK."""
        engine = _make_engine()
        previous = _make_assessment(overall=AssessmentRating.NEUTRAL)
        current = _make_assessment(overall=AssessmentRating.FAVORABLE)
        personality = _make_personality(aggression=0.8, caution=0.2, flexibility=0.0)
        action, trigger = engine.check_adaptation_needed(
            "unit_a", current, previous, personality, "defend", 0.0, ts=TS,
        )
        assert trigger == AdaptationTrigger.OPPORTUNITY
        assert action == AdaptationAction.COUNTERATTACK

    def test_opportunity_moderate_adjust_tempo(self) -> None:
        """Situation improves with moderate commander -> ADJUST_TEMPO."""
        engine = _make_engine()
        previous = _make_assessment(overall=AssessmentRating.UNFAVORABLE)
        current = _make_assessment(overall=AssessmentRating.FAVORABLE)
        personality = _make_personality(aggression=0.4, caution=0.4, flexibility=0.0)
        action, trigger = engine.check_adaptation_needed(
            "unit_a", current, previous, personality, "defend", 0.0, ts=TS,
        )
        assert trigger == AdaptationTrigger.OPPORTUNITY
        assert action == AdaptationAction.ADJUST_TEMPO

    def test_no_opportunity_if_already_favorable(self) -> None:
        """No opportunity trigger if previous was already FAVORABLE."""
        engine = _make_engine()
        previous = _make_assessment(overall=AssessmentRating.FAVORABLE)
        current = _make_assessment(overall=AssessmentRating.VERY_FAVORABLE)
        personality = _make_personality(flexibility=0.0)
        action, trigger = engine.check_adaptation_needed(
            "unit_a", current, previous, personality, "defend", 0.0, ts=TS,
        )
        assert action == AdaptationAction.CONTINUE
        assert trigger is None


# ---------------------------------------------------------------------------
# Surprise contact trigger
# ---------------------------------------------------------------------------


class TestSurpriseContactTrigger:
    def test_surprise_contact_issue_frago(self) -> None:
        """Sudden unfavorable force ratio -> ISSUE_FRAGO.

        Use a high force_ratio_change_threshold so FORCE_RATIO_CHANGE
        does not fire first, allowing SURPRISE_CONTACT to trigger.
        """
        cfg = AdaptationConfig(force_ratio_change_threshold=5.0)
        engine = _make_engine(config=cfg)
        previous = _make_assessment(force_ratio=1.5)
        current = _make_assessment(force_ratio=0.3)
        personality = _make_personality(flexibility=0.0)
        action, trigger = engine.check_adaptation_needed(
            "unit_a", current, previous, personality, "move", 0.0, ts=TS,
        )
        assert trigger == AdaptationTrigger.SURPRISE_CONTACT
        assert action == AdaptationAction.ISSUE_FRAGO

    def test_surprise_contact_no_previous(self) -> None:
        """Bad force ratio with no previous -> SURPRISE_CONTACT."""
        engine = _make_engine()
        current = _make_assessment(force_ratio=0.3)
        personality = _make_personality(flexibility=0.0)
        action, trigger = engine.check_adaptation_needed(
            "unit_a", current, None, personality, "move", 0.0, ts=TS,
        )
        assert trigger == AdaptationTrigger.SURPRISE_CONTACT
        assert action == AdaptationAction.ISSUE_FRAGO


# ---------------------------------------------------------------------------
# No trigger
# ---------------------------------------------------------------------------


class TestNoTrigger:
    def test_stable_situation_continue(self) -> None:
        """Stable, healthy situation -> CONTINUE, None."""
        engine = _make_engine()
        current = _make_assessment(
            force_ratio=1.5, supply=0.8, morale=0.7,
            overall=AssessmentRating.FAVORABLE,
        )
        previous = _make_assessment(
            force_ratio=1.5, supply=0.8, morale=0.7,
            overall=AssessmentRating.FAVORABLE,
        )
        personality = _make_personality(flexibility=0.0)
        action, trigger = engine.check_adaptation_needed(
            "unit_a", current, previous, personality, "defend", 0.05, ts=TS,
        )
        assert action == AdaptationAction.CONTINUE
        assert trigger is None


# ---------------------------------------------------------------------------
# Flexibility modulation
# ---------------------------------------------------------------------------


class TestFlexibility:
    def test_flexible_modifies_response(self) -> None:
        """Very flexible commander may change the action (over many trials)."""
        actions_seen: set[AdaptationAction] = set()
        for seed in range(200):
            rng = make_rng(seed)
            engine = _make_engine(rng=rng)
            current = _make_assessment(supply=0.10)
            # Highly flexible, aggressive → may shift reposition→adjust_tempo
            personality = _make_personality(
                aggression=0.8, caution=0.2, flexibility=1.0,
            )
            action, trigger = engine.check_adaptation_needed(
                "unit_a", current, None, personality, "attack", 0.0, ts=TS,
            )
            assert trigger == AdaptationTrigger.SUPPLY_CRISIS
            actions_seen.add(action)
        # Should see at least 2 different actions due to flexibility roll
        assert len(actions_seen) >= 2

    def test_zero_flexibility_no_change(self) -> None:
        """Zero flexibility: action never changes from base."""
        for seed in range(50):
            rng = make_rng(seed)
            engine = _make_engine(rng=rng)
            current = _make_assessment(morale=0.15)
            personality = _make_personality(flexibility=0.0)
            action, _ = engine.check_adaptation_needed(
                "unit_a", current, None, personality, "attack", 0.0, ts=TS,
            )
            assert action == AdaptationAction.WITHDRAW


# ---------------------------------------------------------------------------
# No personality (None)
# ---------------------------------------------------------------------------


class TestNoPersonality:
    def test_none_personality_uses_defaults(self) -> None:
        """When personality is None, defaults (0.5/0.5/0.5) are used."""
        engine = _make_engine()
        current = _make_assessment(supply=0.10)
        action, trigger = engine.check_adaptation_needed(
            "unit_a", current, None, None, "attack", 0.0, ts=TS,
        )
        assert trigger == AdaptationTrigger.SUPPLY_CRISIS
        # Default caution=0.5 -> not > 0.6 -> REPOSITION
        assert action in (AdaptationAction.REPOSITION, AdaptationAction.ADJUST_TEMPO)


# ---------------------------------------------------------------------------
# Previous assessment stored
# ---------------------------------------------------------------------------


class TestPreviousAssessmentStorage:
    def test_previous_stored_for_next_call(self) -> None:
        """Engine stores current assessment as previous for future calls."""
        engine = _make_engine()
        first = _make_assessment(
            force_ratio=1.5, overall=AssessmentRating.NEUTRAL,
        )
        personality = _make_personality(flexibility=0.0)
        # First call: no trigger (no previous, healthy situation)
        engine.check_adaptation_needed(
            "unit_a", first, None, personality, "defend", 0.0, ts=TS,
        )

        # Second call: force ratio changed significantly
        second = _make_assessment(force_ratio=3.0)
        action, trigger = engine.check_adaptation_needed(
            "unit_a", second, None, personality, "defend", 0.0, ts=TS,
        )
        # |3.0 - 1.5| / 1.5 = 1.0 >= 0.5 threshold
        assert trigger == AdaptationTrigger.FORCE_RATIO_CHANGE


# ---------------------------------------------------------------------------
# Event publishing
# ---------------------------------------------------------------------------


class TestEventPublishing:
    def test_event_published_on_trigger(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        received: list[PlanAdaptedEvent] = []
        event_bus.subscribe(PlanAdaptedEvent, lambda e: received.append(e))

        engine = AdaptationEngine(event_bus=event_bus, rng=rng)
        current = _make_assessment(morale=0.15)
        personality = _make_personality(flexibility=0.0)
        engine.check_adaptation_needed(
            "unit_a", current, None, personality, "attack", 0.0, ts=TS,
        )

        assert len(received) == 1
        evt = received[0]
        assert evt.unit_id == "unit_a"
        assert evt.trigger == AdaptationTrigger.MORALE_BREAK.name
        assert evt.action == AdaptationAction.WITHDRAW.name

    def test_no_event_on_continue(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        received: list[PlanAdaptedEvent] = []
        event_bus.subscribe(PlanAdaptedEvent, lambda e: received.append(e))

        engine = AdaptationEngine(event_bus=event_bus, rng=rng)
        current = _make_assessment()
        personality = _make_personality(flexibility=0.0)
        engine.check_adaptation_needed(
            "unit_a", current, None, personality, "defend", 0.05, ts=TS,
        )

        assert len(received) == 0

    def test_frago_order_id_on_issue_frago(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        received: list[PlanAdaptedEvent] = []
        event_bus.subscribe(PlanAdaptedEvent, lambda e: received.append(e))

        engine = AdaptationEngine(event_bus=event_bus, rng=rng)
        current = _make_assessment(force_ratio=0.3)
        personality = _make_personality(flexibility=0.0)
        engine.check_adaptation_needed(
            "unit_a", current, None, personality, "move", 0.0, ts=TS,
        )

        assert len(received) == 1
        assert received[0].frago_order_id == "frago_unit_a"


# ---------------------------------------------------------------------------
# Multiple units tracked independently
# ---------------------------------------------------------------------------


class TestMultipleUnits:
    def test_independent_tracking(self) -> None:
        """Different units have independent previous assessments."""
        engine = _make_engine()
        personality = _make_personality(flexibility=0.0)

        # Unit A: healthy
        a_current = _make_assessment(force_ratio=1.5, unit_id="unit_a")
        a_action, a_trigger = engine.check_adaptation_needed(
            "unit_a", a_current, None, personality, "defend", 0.0, ts=TS,
        )
        assert a_action == AdaptationAction.CONTINUE

        # Unit B: supply crisis
        b_current = _make_assessment(supply=0.10, unit_id="unit_b")
        b_action, b_trigger = engine.check_adaptation_needed(
            "unit_b", b_current, None, personality, "defend", 0.0, ts=TS,
        )
        assert b_trigger == AdaptationTrigger.SUPPLY_CRISIS

        # Check unit A again: still CONTINUE (no supply crisis for A)
        a_action2, a_trigger2 = engine.check_adaptation_needed(
            "unit_a", a_current, None, personality, "defend", 0.0, ts=TS,
        )
        assert a_action2 == AdaptationAction.CONTINUE


# ---------------------------------------------------------------------------
# Deterministic replay
# ---------------------------------------------------------------------------


class TestDeterministicReplay:
    def test_same_seed_same_result(self) -> None:
        """Two engines with same seed produce identical outcomes."""
        for _ in range(10):
            e1 = _make_engine(rng=make_rng(DEFAULT_SEED))
            e2 = _make_engine(rng=make_rng(DEFAULT_SEED))
            current = _make_assessment(supply=0.10)
            personality = _make_personality(flexibility=0.8)

            a1, t1 = e1.check_adaptation_needed(
                "unit_a", current, None, personality, "attack", 0.0, ts=TS,
            )
            a2, t2 = e2.check_adaptation_needed(
                "unit_a", current, None, personality, "attack", 0.0, ts=TS,
            )
            assert a1 == a2
            assert t1 == t2


# ---------------------------------------------------------------------------
# State protocol
# ---------------------------------------------------------------------------


class TestStateProtocol:
    def test_get_set_state_roundtrip(self) -> None:
        engine = _make_engine()
        current = _make_assessment()
        personality = _make_personality(flexibility=0.0)
        engine.check_adaptation_needed(
            "unit_a", current, None, personality, "defend", 0.0, ts=TS,
        )

        state = engine.get_state()
        assert isinstance(state, dict)
        assert "previous_assessments" in state
        assert "unit_a" in state["previous_assessments"]

        # Restore into a new engine
        engine2 = _make_engine()
        engine2.set_state(state)
        state2 = engine2.get_state()
        assert state2["previous_assessments"].keys() == state["previous_assessments"].keys()

    def test_set_state_empty(self) -> None:
        engine = _make_engine()
        engine.set_state({})
        state = engine.get_state()
        assert state["previous_assessments"] == {}


# ---------------------------------------------------------------------------
# Custom config thresholds
# ---------------------------------------------------------------------------


class TestCustomConfig:
    def test_lower_casualty_threshold(self) -> None:
        """Lower threshold triggers on smaller casualties."""
        cfg = AdaptationConfig(casualty_threshold=0.10)
        engine = _make_engine(config=cfg)
        current = _make_assessment()
        personality = _make_personality(flexibility=0.0, aggression=0.3, caution=0.3)
        action, trigger = engine.check_adaptation_needed(
            "unit_a", current, None, personality, "attack", 0.12, ts=TS,
        )
        assert trigger == AdaptationTrigger.CASUALTIES

    def test_higher_casualty_threshold_no_trigger(self) -> None:
        """Higher threshold does not trigger on moderate casualties."""
        cfg = AdaptationConfig(casualty_threshold=0.40)
        engine = _make_engine(config=cfg)
        current = _make_assessment()
        personality = _make_personality(flexibility=0.0)
        action, trigger = engine.check_adaptation_needed(
            "unit_a", current, None, personality, "attack", 0.25, ts=TS,
        )
        assert action == AdaptationAction.CONTINUE
        assert trigger is None


# ---------------------------------------------------------------------------
# Combined crises
# ---------------------------------------------------------------------------


class TestCombinedCrises:
    def test_supply_and_morale_crisis(self) -> None:
        """When both supply and morale are critical, first trigger wins (casualties checked first, then supply)."""
        engine = _make_engine()
        current = _make_assessment(supply=0.10, morale=0.15)
        personality = _make_personality(flexibility=0.0)
        action, trigger = engine.check_adaptation_needed(
            "unit_a", current, None, personality, "attack", 0.0, ts=TS,
        )
        # Supply crisis is checked before morale break
        assert trigger == AdaptationTrigger.SUPPLY_CRISIS
