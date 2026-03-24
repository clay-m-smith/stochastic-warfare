"""Tests for stochastic_warfare.c2.ai.decisions -- echelon-specific decision logic."""

from __future__ import annotations


import numpy as np
import pytest

from tests.conftest import DEFAULT_SEED, TS, make_rng

from stochastic_warfare.c2.ai.assessment import AssessmentRating, SituationAssessment
from stochastic_warfare.c2.ai.commander import CommanderPersonality
from stochastic_warfare.c2.ai.decisions import (
    BrigadeDivAction,
    CompanyBnAction,
    CorpsAction,
    DecisionCategory,
    DecisionEngine,
    DecisionResult,
    IndividualAction,
    SmallUnitAction,
)
from stochastic_warfare.c2.ai.doctrine import DoctrineTemplate
from stochastic_warfare.c2.events import DecisionMadeEvent
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
    **kw: float,
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


def _make_doctrine(
    actions: list[str] | None = None,
    category: str = "OFFENSIVE",
) -> DoctrineTemplate:
    return DoctrineTemplate(
        doctrine_id="test_doctrine",
        display_name="Test",
        category=category,
        faction="generic",
        description="Test",
        min_echelon=0,
        max_echelon=13,
        applicable_domains=["LAND"],
        phases=["SHAPING", "DECISIVE"],
        force_ratios={"main": 0.6, "support": 0.4},
        actions=actions or ["attack", "defend", "delay", "withdraw", "support_by_fire"],
        priorities=["firepower"],
        risk_tolerance="moderate",
        tempo="moderate",
    )


def _make_engine(
    event_bus: EventBus | None = None,
    rng: np.random.Generator | None = None,
) -> DecisionEngine:
    if event_bus is None:
        event_bus = EventBus()
    if rng is None:
        rng = make_rng()
    return DecisionEngine(event_bus=event_bus, rng=rng)


# ---------------------------------------------------------------------------
# Enum value tests
# ---------------------------------------------------------------------------


class TestDecisionCategory:
    def test_enum_values(self) -> None:
        assert DecisionCategory.OFFENSIVE == 0
        assert DecisionCategory.DEFENSIVE == 1
        assert DecisionCategory.MOVEMENT == 2
        assert DecisionCategory.SUPPORT == 3
        assert DecisionCategory.C2 == 4

    def test_enum_count(self) -> None:
        assert len(DecisionCategory) == 5


class TestIndividualAction:
    def test_enum_values(self) -> None:
        assert IndividualAction.HOLD_POSITION == 0
        assert IndividualAction.ADVANCE == 1
        assert IndividualAction.RETREAT == 2
        assert IndividualAction.TAKE_COVER == 3
        assert IndividualAction.ENGAGE == 4
        assert IndividualAction.SEEK_COVER == 5

    def test_enum_count(self) -> None:
        assert len(IndividualAction) == 6


class TestSmallUnitAction:
    def test_enum_values(self) -> None:
        assert SmallUnitAction.ATTACK == 0
        assert SmallUnitAction.DEFEND == 1
        assert SmallUnitAction.BOUND_FORWARD == 2
        assert SmallUnitAction.WITHDRAW == 3
        assert SmallUnitAction.FLANK == 4
        assert SmallUnitAction.AMBUSH == 5
        assert SmallUnitAction.RECON == 6
        assert SmallUnitAction.SUPPORT_BY_FIRE == 7

    def test_enum_count(self) -> None:
        assert len(SmallUnitAction) == 8


class TestCompanyBnAction:
    def test_enum_values(self) -> None:
        assert CompanyBnAction.ATTACK == 0
        assert CompanyBnAction.DEFEND == 1
        assert CompanyBnAction.DELAY == 2
        assert CompanyBnAction.COUNTERATTACK == 3
        assert CompanyBnAction.BYPASS == 4
        assert CompanyBnAction.FIX == 5
        assert CompanyBnAction.ENVELOP == 6
        assert CompanyBnAction.WITHDRAW == 7
        assert CompanyBnAction.CONSOLIDATE == 8
        assert CompanyBnAction.RESERVE == 9

    def test_enum_count(self) -> None:
        assert len(CompanyBnAction) == 10


class TestBrigadeDivAction:
    def test_enum_values(self) -> None:
        assert BrigadeDivAction.ATTACK == 0
        assert BrigadeDivAction.DEFEND == 1
        assert BrigadeDivAction.DELAY == 2
        assert BrigadeDivAction.COUNTERATTACK == 3
        assert BrigadeDivAction.EXPLOIT == 4
        assert BrigadeDivAction.PURSUE == 5
        assert BrigadeDivAction.RETROGRADE == 6
        assert BrigadeDivAction.PASSAGE_OF_LINES == 7
        assert BrigadeDivAction.RELIEF_IN_PLACE == 8
        assert BrigadeDivAction.RESERVE == 9

    def test_enum_count(self) -> None:
        assert len(BrigadeDivAction) == 13


class TestCorpsAction:
    def test_enum_values(self) -> None:
        assert CorpsAction.MAIN_ATTACK == 0
        assert CorpsAction.SUPPORTING_ATTACK == 1
        assert CorpsAction.DEFEND == 2
        assert CorpsAction.DEEP_STRIKE == 3
        assert CorpsAction.OPERATIONAL_MANEUVER == 4
        assert CorpsAction.RESERVE == 5
        assert CorpsAction.TRANSITION == 6

    def test_enum_count(self) -> None:
        assert len(CorpsAction) == 9


# ---------------------------------------------------------------------------
# DecisionResult dataclass
# ---------------------------------------------------------------------------


class TestDecisionResult:
    def test_creation(self) -> None:
        dr = DecisionResult(
            unit_id="alpha",
            echelon_level=4,
            decision_category=DecisionCategory.OFFENSIVE,
            action=0,
            action_name="ATTACK",
            confidence=0.8,
            rationale="test rationale",
            timestamp=TS,
        )
        assert dr.unit_id == "alpha"
        assert dr.echelon_level == 4
        assert dr.decision_category == DecisionCategory.OFFENSIVE
        assert dr.action == 0
        assert dr.action_name == "ATTACK"
        assert dr.confidence == 0.8
        assert dr.rationale == "test rationale"
        assert dr.timestamp == TS

    def test_frozen(self) -> None:
        dr = DecisionResult(
            unit_id="alpha",
            echelon_level=4,
            decision_category=DecisionCategory.OFFENSIVE,
            action=0,
            action_name="ATTACK",
            confidence=0.8,
            rationale="test",
            timestamp=TS,
        )
        with pytest.raises(AttributeError):
            dr.unit_id = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Echelon dispatch
# ---------------------------------------------------------------------------


class TestEchelonDispatch:
    def test_individual_dispatches_to_individual_action(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = DecisionEngine(event_bus=event_bus, rng=rng)
        result = engine.decide(
            "u1", echelon=0, assessment=_make_assessment(),
            personality=_make_personality(), doctrine=None, ts=TS,
        )
        # action_name must be a valid IndividualAction name
        assert result.action_name in [a.name for a in IndividualAction]

    def test_fire_team_dispatches_to_individual_action(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = DecisionEngine(event_bus=event_bus, rng=rng)
        result = engine.decide(
            "u1", echelon=1, assessment=_make_assessment(),
            personality=_make_personality(), doctrine=None, ts=TS,
        )
        assert result.action_name in [a.name for a in IndividualAction]

    def test_squad_dispatches_to_small_unit_action(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = DecisionEngine(event_bus=event_bus, rng=rng)
        result = engine.decide(
            "u1", echelon=2, assessment=_make_assessment(),
            personality=_make_personality(), doctrine=None, ts=TS,
        )
        assert result.action_name in [a.name for a in SmallUnitAction]

    def test_platoon_dispatches_to_small_unit_action(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = DecisionEngine(event_bus=event_bus, rng=rng)
        result = engine.decide(
            "u1", echelon=4, assessment=_make_assessment(),
            personality=_make_personality(), doctrine=None, ts=TS,
        )
        assert result.action_name in [a.name for a in SmallUnitAction]

    def test_company_dispatches_to_company_bn_action(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = DecisionEngine(event_bus=event_bus, rng=rng)
        result = engine.decide(
            "u1", echelon=5, assessment=_make_assessment(),
            personality=_make_personality(), doctrine=None, ts=TS,
        )
        assert result.action_name in [a.name for a in CompanyBnAction]

    def test_battalion_dispatches_to_company_bn_action(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = DecisionEngine(event_bus=event_bus, rng=rng)
        result = engine.decide(
            "u1", echelon=6, assessment=_make_assessment(),
            personality=_make_personality(), doctrine=None, ts=TS,
        )
        assert result.action_name in [a.name for a in CompanyBnAction]

    def test_brigade_dispatches_to_brigade_div_action(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = DecisionEngine(event_bus=event_bus, rng=rng)
        result = engine.decide(
            "u1", echelon=8, assessment=_make_assessment(),
            personality=_make_personality(), doctrine=None, ts=TS,
        )
        assert result.action_name in [a.name for a in BrigadeDivAction]

    def test_corps_dispatches_to_corps_action(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = DecisionEngine(event_bus=event_bus, rng=rng)
        result = engine.decide(
            "u1", echelon=10, assessment=_make_assessment(),
            personality=_make_personality(), doctrine=None, ts=TS,
        )
        assert result.action_name in [a.name for a in CorpsAction]

    def test_theater_dispatches_to_corps_action(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = DecisionEngine(event_bus=event_bus, rng=rng)
        result = engine.decide(
            "u1", echelon=13, assessment=_make_assessment(),
            personality=_make_personality(), doctrine=None, ts=TS,
        )
        assert result.action_name in [a.name for a in CorpsAction]


# ---------------------------------------------------------------------------
# Individual decisions
# ---------------------------------------------------------------------------


class TestIndividualDecisions:
    def test_favorable_conditions_advance_or_engage(self) -> None:
        """Strong force ratio + high aggression → ADVANCE or ENGAGE."""
        engine = _make_engine(rng=make_rng(42))
        assessment = _make_assessment(
            force_ratio=3.0, overall=AssessmentRating.VERY_FAVORABLE,
            morale=0.9, supply=0.9,
        )
        personality = _make_personality(aggression=0.9, caution=0.1, experience=0.9)
        result = engine.decide(
            "u1", echelon=0, assessment=assessment,
            personality=personality, doctrine=None, roe_level=2, ts=TS,
        )
        assert result.action_name in ("ADVANCE", "ENGAGE")

    def test_unfavorable_conditions_retreat_or_seek_cover(self) -> None:
        """Weak force ratio + low morale → RETREAT or SEEK_COVER."""
        engine = _make_engine(rng=make_rng(42))
        assessment = _make_assessment(
            force_ratio=0.3, overall=AssessmentRating.VERY_UNFAVORABLE,
            morale=0.15, supply=0.1,
        )
        personality = _make_personality(aggression=0.1, caution=0.9, experience=0.5)
        result = engine.decide(
            "u1", echelon=0, assessment=assessment,
            personality=personality, doctrine=None, ts=TS,
        )
        assert result.action_name in ("RETREAT", "SEEK_COVER")

    def test_weapons_hold_blocks_engage(self) -> None:
        """WEAPONS_HOLD sets ENGAGE score to 0."""
        # Run multiple seeds; ENGAGE should never win at WEAPONS_HOLD
        for seed in range(20):
            engine = _make_engine(rng=make_rng(seed))
            assessment = _make_assessment(
                force_ratio=5.0, overall=AssessmentRating.VERY_FAVORABLE,
                morale=0.9, supply=0.9,
            )
            personality = _make_personality(aggression=0.9, experience=0.9)
            result = engine.decide(
                "u1", echelon=0, assessment=assessment,
                personality=personality, doctrine=None, roe_level=0, ts=TS,
            )
            assert result.action_name != "ENGAGE"


# ---------------------------------------------------------------------------
# Small unit decisions
# ---------------------------------------------------------------------------


class TestSmallUnitDecisions:
    def test_strong_force_ratio_attack(self) -> None:
        """High force ratio + aggressive → ATTACK."""
        engine = _make_engine(rng=make_rng(42))
        assessment = _make_assessment(
            force_ratio=3.0, overall=AssessmentRating.VERY_FAVORABLE,
            morale=0.9, supply=0.9,
        )
        personality = _make_personality(aggression=0.9, caution=0.1, experience=0.9)
        result = engine.decide(
            "u1", echelon=4, assessment=assessment,
            personality=personality, doctrine=None, ts=TS,
        )
        assert result.action_name in ("ATTACK", "FLANK", "SUPPORT_BY_FIRE")

    def test_weak_force_ratio_withdraw_or_defend(self) -> None:
        """Weak force ratio → WITHDRAW or DEFEND."""
        engine = _make_engine(rng=make_rng(42))
        assessment = _make_assessment(
            force_ratio=0.3, overall=AssessmentRating.VERY_UNFAVORABLE,
            morale=0.2, supply=0.3,
        )
        personality = _make_personality(aggression=0.1, caution=0.9, experience=0.5)
        result = engine.decide(
            "u1", echelon=4, assessment=assessment,
            personality=personality, doctrine=None, ts=TS,
        )
        assert result.action_name in ("WITHDRAW", "DEFEND")

    def test_good_terrain_ambush(self) -> None:
        """Good terrain + weaker force → AMBUSH opportunity."""
        # Run many seeds; AMBUSH should appear at least once
        ambush_count = 0
        for seed in range(30):
            engine = _make_engine(rng=make_rng(seed))
            assessment = _make_assessment(
                force_ratio=1.0, overall=AssessmentRating.NEUTRAL,
                morale=0.6, terrain_adv=0.5,
            )
            personality = _make_personality(aggression=0.3, caution=0.6, experience=0.3)
            result = engine.decide(
                "u1", echelon=4, assessment=assessment,
                personality=personality, doctrine=None, ts=TS,
            )
            if result.action_name == "AMBUSH":
                ambush_count += 1
        assert ambush_count > 0, "AMBUSH should appear at least once in 30 trials"

    def test_poor_intel_recon(self) -> None:
        """Very poor intel quality → RECON."""
        recon_count = 0
        for seed in range(30):
            engine = _make_engine(rng=make_rng(seed))
            assessment = _make_assessment(
                force_ratio=1.0, overall=AssessmentRating.NEUTRAL,
                morale=0.6, intel=0.1, supply=0.6,
            )
            personality = _make_personality(aggression=0.2, caution=0.5, experience=0.3)
            result = engine.decide(
                "u1", echelon=4, assessment=assessment,
                personality=personality, doctrine=None, ts=TS,
            )
            if result.action_name == "RECON":
                recon_count += 1
        assert recon_count > 0, "RECON should appear at least once in 30 trials with poor intel"


# ---------------------------------------------------------------------------
# Company/battalion decisions
# ---------------------------------------------------------------------------


class TestCompanyBnDecisions:
    def test_favorable_attack_or_counterattack(self) -> None:
        """Favorable conditions → ATTACK or COUNTERATTACK."""
        engine = _make_engine(rng=make_rng(42))
        assessment = _make_assessment(
            force_ratio=2.5, overall=AssessmentRating.VERY_FAVORABLE,
            morale=0.9, supply=0.9, c2=0.9,
        )
        personality = _make_personality(aggression=0.9, caution=0.1, initiative=0.8, experience=0.9)
        result = engine.decide(
            "u1", echelon=6, assessment=assessment,
            personality=personality, doctrine=None, ts=TS,
        )
        assert result.action_name in ("ATTACK", "COUNTERATTACK", "ENVELOP")

    def test_unfavorable_delay_or_withdraw(self) -> None:
        """Unfavorable conditions → DELAY or WITHDRAW."""
        engine = _make_engine(rng=make_rng(42))
        assessment = _make_assessment(
            force_ratio=0.3, overall=AssessmentRating.VERY_UNFAVORABLE,
            morale=0.2, supply=0.3,
        )
        personality = _make_personality(aggression=0.1, caution=0.9, experience=0.5)
        result = engine.decide(
            "u1", echelon=6, assessment=assessment,
            personality=personality, doctrine=None, ts=TS,
        )
        assert result.action_name in ("DELAY", "WITHDRAW", "DEFEND")

    def test_ambiguous_defend_or_reserve(self) -> None:
        """Ambiguous situation with parity → DEFEND or RESERVE."""
        engine = _make_engine(rng=make_rng(42))
        assessment = _make_assessment(
            force_ratio=1.0, overall=AssessmentRating.NEUTRAL,
            morale=0.5, supply=0.5, c2=0.8, terrain_adv=0.3,
        )
        personality = _make_personality(aggression=0.3, caution=0.6, experience=0.5)
        result = engine.decide(
            "u1", echelon=6, assessment=assessment,
            personality=personality, doctrine=None, ts=TS,
        )
        assert result.action_name in ("DEFEND", "RESERVE", "FIX", "DELAY")


# ---------------------------------------------------------------------------
# Brigade/division decisions
# ---------------------------------------------------------------------------


class TestBrigadeDivDecisions:
    def test_favorable_exploit_or_pursue(self) -> None:
        """Overwhelmingly favorable → EXPLOIT or PURSUE."""
        engine = _make_engine(rng=make_rng(42))
        assessment = _make_assessment(
            force_ratio=4.0, overall=AssessmentRating.VERY_FAVORABLE,
            morale=0.9, supply=0.9,
        )
        personality = _make_personality(aggression=0.9, caution=0.1, experience=0.9)
        result = engine.decide(
            "u1", echelon=9, assessment=assessment,
            personality=personality, doctrine=None, ts=TS,
        )
        assert result.action_name in ("ATTACK", "EXPLOIT", "PURSUE", "COUNTERATTACK")

    def test_unfavorable_retrograde(self) -> None:
        """Severely unfavorable → RETROGRADE."""
        engine = _make_engine(rng=make_rng(42))
        assessment = _make_assessment(
            force_ratio=0.25, overall=AssessmentRating.VERY_UNFAVORABLE,
            morale=0.15, supply=0.1,
        )
        personality = _make_personality(aggression=0.1, caution=0.9, experience=0.5)
        result = engine.decide(
            "u1", echelon=9, assessment=assessment,
            personality=personality, doctrine=None, ts=TS,
        )
        assert result.action_name in ("RETROGRADE", "DELAY", "DEFEND")


# ---------------------------------------------------------------------------
# Corps+ decisions
# ---------------------------------------------------------------------------


class TestCorpsPlusDecisions:
    def test_good_intel_deep_strike(self) -> None:
        """Good intel + good C2 → DEEP_STRIKE possible."""
        deep_strike_count = 0
        for seed in range(30):
            engine = _make_engine(rng=make_rng(seed))
            assessment = _make_assessment(
                force_ratio=1.5, overall=AssessmentRating.FAVORABLE,
                morale=0.7, supply=0.7, intel=0.9, c2=0.9,
            )
            personality = _make_personality(aggression=0.7, caution=0.2, experience=0.5)
            result = engine.decide(
                "u1", echelon=10, assessment=assessment,
                personality=personality, doctrine=None, ts=TS,
            )
            if result.action_name == "DEEP_STRIKE":
                deep_strike_count += 1
        assert deep_strike_count > 0, "DEEP_STRIKE should appear at least once in 30 trials"

    def test_objectives_near_complete_transition(self) -> None:
        """Very favorable + high force ratio → TRANSITION possible."""
        transition_count = 0
        for seed in range(30):
            engine = _make_engine(rng=make_rng(seed))
            assessment = _make_assessment(
                force_ratio=5.0, overall=AssessmentRating.VERY_FAVORABLE,
                morale=0.9, supply=0.9, intel=0.8, c2=0.9,
            )
            personality = _make_personality(aggression=0.2, caution=0.5, experience=0.9)
            result = engine.decide(
                "u1", echelon=10, assessment=assessment,
                personality=personality, doctrine=None, ts=TS,
            )
            if result.action_name == "TRANSITION":
                transition_count += 1
        assert transition_count > 0, "TRANSITION should appear at least once in 30 trials"


# ---------------------------------------------------------------------------
# Personality effects
# ---------------------------------------------------------------------------


class TestPersonalityEffects:
    def test_aggressive_biases_toward_offensive(self) -> None:
        """Highly aggressive commander favors offensive actions."""
        offensive_count = 0
        for seed in range(30):
            engine = _make_engine(rng=make_rng(seed))
            assessment = _make_assessment(
                force_ratio=1.5, overall=AssessmentRating.FAVORABLE,
            )
            personality = _make_personality(aggression=0.95, caution=0.05, experience=0.8)
            result = engine.decide(
                "u1", echelon=4, assessment=assessment,
                personality=personality, doctrine=None, ts=TS,
            )
            if result.decision_category == DecisionCategory.OFFENSIVE:
                offensive_count += 1
        assert offensive_count > 15, f"Aggressive commander should pick offensive >50% (got {offensive_count}/30)"

    def test_cautious_biases_toward_defensive(self) -> None:
        """Highly cautious commander favors defensive actions."""
        defensive_count = 0
        for seed in range(30):
            engine = _make_engine(rng=make_rng(seed))
            assessment = _make_assessment(
                force_ratio=0.8, overall=AssessmentRating.NEUTRAL,
            )
            personality = _make_personality(aggression=0.05, caution=0.95, experience=0.8)
            result = engine.decide(
                "u1", echelon=4, assessment=assessment,
                personality=personality, doctrine=None, ts=TS,
            )
            if result.decision_category == DecisionCategory.DEFENSIVE:
                defensive_count += 1
        assert defensive_count > 15, f"Cautious commander should pick defensive >50% (got {defensive_count}/30)"

    def test_flexible_personality_more_varied(self) -> None:
        """Flexible commander produces more action variety."""
        actions_flexible: set[str] = set()
        actions_rigid: set[str] = set()
        for seed in range(50):
            engine_flex = _make_engine(rng=make_rng(seed))
            engine_rigid = _make_engine(rng=make_rng(seed + 1000))
            assessment = _make_assessment(
                force_ratio=1.2, overall=AssessmentRating.NEUTRAL,
            )
            p_flex = _make_personality(flexibility=0.95, experience=0.2)
            p_rigid = _make_personality(flexibility=0.05, experience=0.2)
            r_flex = engine_flex.decide(
                "u1", echelon=4, assessment=assessment,
                personality=p_flex, doctrine=None, ts=TS,
            )
            r_rigid = engine_rigid.decide(
                "u1", echelon=4, assessment=assessment,
                personality=p_rigid, doctrine=None, ts=TS,
            )
            actions_flexible.add(r_flex.action_name)
            actions_rigid.add(r_rigid.action_name)
        # Flexible personality should produce at least as many distinct actions
        assert len(actions_flexible) >= len(actions_rigid)


# ---------------------------------------------------------------------------
# Doctrine filtering
# ---------------------------------------------------------------------------


class TestDoctrineFiltering:
    def test_doctrine_constrains_actions(self) -> None:
        """Only actions in doctrine.actions should be chosen."""
        doctrine = _make_doctrine(actions=["attack", "defend"])
        for seed in range(20):
            engine = _make_engine(rng=make_rng(seed))
            assessment = _make_assessment()
            personality = _make_personality(experience=0.8)
            result = engine.decide(
                "u1", echelon=4, assessment=assessment,
                personality=personality, doctrine=doctrine, ts=TS,
            )
            assert result.action_name in ("ATTACK", "DEFEND")

    def test_doctrine_filtering_doesnt_empty_set(self) -> None:
        """If no doctrine actions match, all actions remain available."""
        doctrine = _make_doctrine(actions=["nonexistent_action"])
        engine = _make_engine(rng=make_rng(42))
        assessment = _make_assessment()
        personality = _make_personality()
        result = engine.decide(
            "u1", echelon=4, assessment=assessment,
            personality=personality, doctrine=doctrine, ts=TS,
        )
        # Should still produce a valid action (not crash)
        assert result.action_name in [a.name for a in SmallUnitAction]


# ---------------------------------------------------------------------------
# None personality and doctrine
# ---------------------------------------------------------------------------


class TestNoneInputs:
    def test_no_personality_uses_defaults(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """None personality should not raise and uses balanced defaults."""
        engine = DecisionEngine(event_bus=event_bus, rng=rng)
        result = engine.decide(
            "u1", echelon=4, assessment=_make_assessment(),
            personality=None, doctrine=None, ts=TS,
        )
        assert isinstance(result, DecisionResult)
        assert result.confidence > 0.0

    def test_no_doctrine_allows_all_actions(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """None doctrine should not filter any actions."""
        engine = DecisionEngine(event_bus=event_bus, rng=rng)
        result = engine.decide(
            "u1", echelon=4, assessment=_make_assessment(),
            personality=_make_personality(), doctrine=None, ts=TS,
        )
        assert isinstance(result, DecisionResult)


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------


class TestConfidence:
    def test_correlates_with_assessment_confidence(self) -> None:
        """Higher assessment confidence → higher decision confidence."""
        engine_high = _make_engine(rng=make_rng(42))
        engine_low = _make_engine(rng=make_rng(42))

        high_conf = _make_assessment(confidence=0.95)
        low_conf = _make_assessment(confidence=0.2)

        personality = _make_personality(experience=0.5)
        r_high = engine_high.decide(
            "u1", echelon=4, assessment=high_conf,
            personality=personality, doctrine=None, ts=TS,
        )
        r_low = engine_low.decide(
            "u2", echelon=4, assessment=low_conf,
            personality=personality, doctrine=None, ts=TS,
        )
        assert r_high.confidence > r_low.confidence

    def test_higher_experience_higher_confidence(self) -> None:
        """Experienced commander → higher confidence."""
        engine_exp = _make_engine(rng=make_rng(42))
        engine_novice = _make_engine(rng=make_rng(42))

        assessment = _make_assessment(confidence=0.7)
        p_exp = _make_personality(experience=0.95)
        p_novice = _make_personality(experience=0.1)

        r_exp = engine_exp.decide(
            "u1", echelon=4, assessment=assessment,
            personality=p_exp, doctrine=None, ts=TS,
        )
        r_novice = engine_novice.decide(
            "u2", echelon=4, assessment=assessment,
            personality=p_novice, doctrine=None, ts=TS,
        )
        assert r_exp.confidence > r_novice.confidence


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_seed_same_result(self) -> None:
        """Two engines with same seed produce identical decisions."""
        for _ in range(5):
            e1 = _make_engine(rng=make_rng(DEFAULT_SEED))
            e2 = _make_engine(rng=make_rng(DEFAULT_SEED))
            assessment = _make_assessment()
            personality = _make_personality()
            r1 = e1.decide(
                "u1", echelon=4, assessment=assessment,
                personality=personality, doctrine=None, ts=TS,
            )
            r2 = e2.decide(
                "u1", echelon=4, assessment=assessment,
                personality=personality, doctrine=None, ts=TS,
            )
            assert r1.action_name == r2.action_name
            assert r1.confidence == r2.confidence

    def test_different_seeds_different_results(self) -> None:
        """Different seeds produce at least one different decision across 20 trials."""
        results: set[str] = set()
        for seed in range(20):
            engine = _make_engine(rng=make_rng(seed))
            assessment = _make_assessment(
                force_ratio=1.2, overall=AssessmentRating.NEUTRAL,
            )
            personality = _make_personality(experience=0.2)
            result = engine.decide(
                "u1", echelon=4, assessment=assessment,
                personality=personality, doctrine=None, ts=TS,
            )
            results.add(result.action_name)
        assert len(results) > 1, "20 different seeds should produce at least 2 distinct decisions"


# ---------------------------------------------------------------------------
# Event publishing
# ---------------------------------------------------------------------------


class TestEventPublishing:
    def test_decision_made_event_published(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        received: list[DecisionMadeEvent] = []
        event_bus.subscribe(DecisionMadeEvent, lambda e: received.append(e))

        engine = DecisionEngine(event_bus=event_bus, rng=rng)
        result = engine.decide(
            "u1", echelon=4, assessment=_make_assessment(),
            personality=_make_personality(), doctrine=None, ts=TS,
        )

        assert len(received) == 1
        evt = received[0]
        assert evt.unit_id == "u1"
        assert evt.decision_type == result.action_name
        assert evt.echelon_level == 4
        assert evt.confidence == result.confidence
        assert evt.timestamp == TS


# ---------------------------------------------------------------------------
# Rationale
# ---------------------------------------------------------------------------


class TestRationale:
    def test_rationale_non_empty(self) -> None:
        engine = _make_engine()
        result = engine.decide(
            "u1", echelon=4, assessment=_make_assessment(),
            personality=_make_personality(), doctrine=None, ts=TS,
        )
        assert len(result.rationale) > 0
        assert result.action_name in result.rationale


# ---------------------------------------------------------------------------
# Multiple decisions
# ---------------------------------------------------------------------------


class TestMultipleDecisions:
    def test_sequential_decisions_independent(self) -> None:
        """Multiple decisions for different units don't interfere."""
        engine = _make_engine()

        favorable = _make_assessment(
            force_ratio=3.0, overall=AssessmentRating.VERY_FAVORABLE,
            morale=0.9,
        )
        unfavorable = _make_assessment(
            force_ratio=0.3, overall=AssessmentRating.VERY_UNFAVORABLE,
            morale=0.2, supply=0.1,
        )

        personality_agg = _make_personality(aggression=0.9, caution=0.1, experience=0.9)
        personality_caut = _make_personality(aggression=0.1, caution=0.9, experience=0.5)

        r1 = engine.decide(
            "u1", echelon=4, assessment=favorable,
            personality=personality_agg, doctrine=None, ts=TS,
        )
        r2 = engine.decide(
            "u2", echelon=4, assessment=unfavorable,
            personality=personality_caut, doctrine=None, ts=TS,
        )

        assert r1.unit_id == "u1"
        assert r2.unit_id == "u2"
        # First should be offensive, second defensive
        assert r1.decision_category == DecisionCategory.OFFENSIVE
        assert r2.decision_category == DecisionCategory.DEFENSIVE


# ---------------------------------------------------------------------------
# State protocol
# ---------------------------------------------------------------------------


class TestStateProtocol:
    def test_get_set_state_roundtrip(self) -> None:
        engine = _make_engine()
        # Make a decision to increment counter
        engine.decide(
            "u1", echelon=4, assessment=_make_assessment(),
            personality=_make_personality(), doctrine=None, ts=TS,
        )
        state = engine.get_state()
        assert isinstance(state, dict)
        assert state["decision_count"] == 1

        # Restore into a new engine
        engine2 = _make_engine()
        engine2.set_state(state)
        state2 = engine2.get_state()
        assert state2["decision_count"] == 1


# ---------------------------------------------------------------------------
# ROE affects all echelons
# ---------------------------------------------------------------------------


class TestRoeAllEchelons:
    def test_roe_weapons_hold_reduces_offensive_individual(self) -> None:
        """WEAPONS_HOLD at individual level blocks ENGAGE."""
        for seed in range(20):
            engine = _make_engine(rng=make_rng(seed))
            assessment = _make_assessment(force_ratio=3.0, morale=0.9)
            personality = _make_personality(aggression=0.8, experience=0.9)
            result = engine.decide(
                "u1", echelon=0, assessment=assessment,
                personality=personality, doctrine=None, roe_level=0, ts=TS,
            )
            assert result.action_name != "ENGAGE"

    def test_roe_weapons_hold_reduces_offensive_small_unit(self) -> None:
        """WEAPONS_HOLD at small unit level penalizes ATTACK."""
        attack_count_hold = 0
        attack_count_free = 0
        for seed in range(30):
            assessment = _make_assessment(force_ratio=1.5, morale=0.7)
            personality = _make_personality(aggression=0.6, experience=0.8)

            e_hold = _make_engine(rng=make_rng(seed))
            r_hold = e_hold.decide(
                "u1", echelon=4, assessment=assessment,
                personality=personality, doctrine=None, roe_level=0, ts=TS,
            )
            e_free = _make_engine(rng=make_rng(seed))
            r_free = e_free.decide(
                "u1", echelon=4, assessment=assessment,
                personality=personality, doctrine=None, roe_level=2, ts=TS,
            )
            if r_hold.action_name == "ATTACK":
                attack_count_hold += 1
            if r_free.action_name == "ATTACK":
                attack_count_free += 1
        assert attack_count_hold <= attack_count_free


# ---------------------------------------------------------------------------
# Morale effects
# ---------------------------------------------------------------------------


class TestMoraleEffects:
    def test_high_morale_increases_offensive(self) -> None:
        """High morale should bias toward offensive actions."""
        offensive_high = 0
        offensive_low = 0
        for seed in range(30):
            high_morale = _make_assessment(morale=0.9, force_ratio=1.2, overall=AssessmentRating.NEUTRAL)
            low_morale = _make_assessment(morale=0.15, force_ratio=1.2, overall=AssessmentRating.NEUTRAL)
            personality = _make_personality(aggression=0.5, caution=0.5, experience=0.5)

            e_high = _make_engine(rng=make_rng(seed))
            r_high = e_high.decide(
                "u1", echelon=4, assessment=high_morale,
                personality=personality, doctrine=None, ts=TS,
            )
            e_low = _make_engine(rng=make_rng(seed))
            r_low = e_low.decide(
                "u2", echelon=4, assessment=low_morale,
                personality=personality, doctrine=None, ts=TS,
            )
            if r_high.decision_category == DecisionCategory.OFFENSIVE:
                offensive_high += 1
            if r_low.decision_category == DecisionCategory.OFFENSIVE:
                offensive_low += 1
        assert offensive_high >= offensive_low

    def test_low_morale_increases_defensive(self) -> None:
        """Low morale should bias toward defensive actions."""
        defensive_count = 0
        for seed in range(30):
            assessment = _make_assessment(
                morale=0.15, force_ratio=0.5,
                overall=AssessmentRating.UNFAVORABLE, supply=0.3,
            )
            personality = _make_personality(experience=0.5)
            engine = _make_engine(rng=make_rng(seed))
            result = engine.decide(
                "u1", echelon=4, assessment=assessment,
                personality=personality, doctrine=None, ts=TS,
            )
            if result.decision_category == DecisionCategory.DEFENSIVE:
                defensive_count += 1
        assert defensive_count > 15, f"Low morale should yield defensive >50% (got {defensive_count}/30)"


# ---------------------------------------------------------------------------
# Supply effects
# ---------------------------------------------------------------------------


class TestSupplyEffects:
    def test_supply_critical_conservative(self) -> None:
        """Critical supply → conservative (defensive) decisions."""
        defensive_count = 0
        for seed in range(30):
            assessment = _make_assessment(
                supply=0.1, force_ratio=1.0,
                overall=AssessmentRating.NEUTRAL, morale=0.5,
            )
            personality = _make_personality(experience=0.5)
            engine = _make_engine(rng=make_rng(seed))
            result = engine.decide(
                "u1", echelon=6, assessment=assessment,
                personality=personality, doctrine=None, ts=TS,
            )
            if result.decision_category == DecisionCategory.DEFENSIVE:
                defensive_count += 1
        assert defensive_count > 10, f"Supply critical should increase defensive choices (got {defensive_count}/30)"
