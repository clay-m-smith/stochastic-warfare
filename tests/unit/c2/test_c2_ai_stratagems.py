"""Tests for stochastic_warfare.c2.ai.stratagems -- stratagem engine."""

from __future__ import annotations


import numpy as np
import pytest

from tests.conftest import DEFAULT_SEED, TS, make_rng

from stochastic_warfare.c2.ai.assessment import AssessmentRating, SituationAssessment
from stochastic_warfare.c2.ai.stratagems import (
    StratagemEngine,
    StratagemPlan,
    StratagemType,
    _STRATAGEM_REQUIREMENTS,
)
from stochastic_warfare.c2.events import StratagemActivatedEvent
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position


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


def _make_engine(
    event_bus: EventBus | None = None,
    rng: np.random.Generator | None = None,
) -> StratagemEngine:
    if event_bus is None:
        event_bus = EventBus()
    if rng is None:
        rng = make_rng()
    return StratagemEngine(event_bus=event_bus, rng=rng)


# ---------------------------------------------------------------------------
# StratagemType enum
# ---------------------------------------------------------------------------


class TestStratagemType:
    def test_enum_values(self) -> None:
        assert StratagemType.DECEPTION == 0
        assert StratagemType.CONCENTRATION == 1
        assert StratagemType.ECONOMY_OF_FORCE == 2
        assert StratagemType.SURPRISE == 3
        assert StratagemType.FEINT == 4
        assert StratagemType.DEMONSTRATION == 5

    def test_enum_count(self) -> None:
        assert len(StratagemType) == 9


# ---------------------------------------------------------------------------
# StratagemPlan
# ---------------------------------------------------------------------------


class TestStratagemPlan:
    def test_creation(self) -> None:
        plan = StratagemPlan(
            stratagem_id="sp_1",
            stratagem_type=StratagemType.DECEPTION,
            description="Feint attack",
            target_area="Hill 203",
            units_involved=("u1", "u2"),
            estimated_effect=0.5,
            risk=0.3,
        )
        assert plan.stratagem_id == "sp_1"
        assert plan.stratagem_type == StratagemType.DECEPTION
        assert plan.units_involved == ("u1", "u2")
        assert plan.estimated_effect == 0.5

    def test_frozen(self) -> None:
        plan = StratagemPlan(
            stratagem_id="sp_1",
            stratagem_type=StratagemType.CONCENTRATION,
            description="Concentrate",
            target_area="Valley",
            units_involved=("u1",),
            estimated_effect=0.4,
            risk=0.2,
        )
        with pytest.raises(AttributeError):
            plan.stratagem_id = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Requirements table
# ---------------------------------------------------------------------------


class TestRequirements:
    def test_all_types_have_requirements(self) -> None:
        for st in StratagemType:
            assert st in _STRATAGEM_REQUIREMENTS, f"Missing requirements for {st.name}"

    def test_requirements_are_tuples_of_int_float(self) -> None:
        for st, (echelon, exp) in _STRATAGEM_REQUIREMENTS.items():
            assert isinstance(echelon, int)
            assert isinstance(exp, float)
            assert echelon >= 0
            assert 0.0 <= exp <= 1.0


# ---------------------------------------------------------------------------
# can_employ_stratagem
# ---------------------------------------------------------------------------


class TestCanEmployStratagem:
    def test_battalion_high_experience_deception(self) -> None:
        """Battalion (6) with experience 0.5 can employ DECEPTION (req 6, 0.4)."""
        engine = _make_engine()
        assert engine.can_employ_stratagem("u1", echelon=6, experience=0.5, stratagem_type=StratagemType.DECEPTION)

    def test_platoon_cannot_deception(self) -> None:
        """Platoon (4) cannot employ DECEPTION (requires 6)."""
        engine = _make_engine()
        assert not engine.can_employ_stratagem("u1", echelon=4, experience=0.9, stratagem_type=StratagemType.DECEPTION)

    def test_low_experience_cannot(self) -> None:
        """Battalion with low experience cannot employ DECEPTION."""
        engine = _make_engine()
        assert not engine.can_employ_stratagem("u1", echelon=6, experience=0.2, stratagem_type=StratagemType.DECEPTION)

    def test_surprise_at_platoon_high_experience(self) -> None:
        """Platoon (4) with high experience can employ SURPRISE (req 4, 0.5)."""
        engine = _make_engine()
        assert engine.can_employ_stratagem("u1", echelon=4, experience=0.6, stratagem_type=StratagemType.SURPRISE)

    def test_concentration_at_company(self) -> None:
        """Company (5) with experience 0.4 can employ CONCENTRATION (req 5, 0.3)."""
        engine = _make_engine()
        assert engine.can_employ_stratagem("u1", echelon=5, experience=0.4, stratagem_type=StratagemType.CONCENTRATION)

    def test_echelon_gating_all_types(self) -> None:
        """Echelon 3 (squad) cannot employ any stratagem."""
        engine = _make_engine()
        for st in StratagemType:
            min_ech = _STRATAGEM_REQUIREMENTS[st][0]
            assert not engine.can_employ_stratagem(
                "u1", echelon=min_ech - 1, experience=1.0, stratagem_type=st,
            ), f"Should not employ {st.name} at echelon {min_ech - 1}"


# ---------------------------------------------------------------------------
# evaluate_deception_opportunity
# ---------------------------------------------------------------------------


class TestEvaluateDeception:
    def test_viable(self) -> None:
        """Good conditions -> deception viable."""
        engine = _make_engine()
        assessment = _make_assessment(force_ratio=1.2, c2=0.8)
        viable, reason = engine.evaluate_deception_opportunity(
            assessment, ["u1", "u2"], echelon=6, experience=0.5,
        )
        assert viable is True
        assert "1.2" in reason

    def test_force_ratio_too_extreme(self) -> None:
        """Force ratio > 2.0 -> deception not viable."""
        engine = _make_engine()
        assessment = _make_assessment(force_ratio=3.0, c2=0.8)
        viable, reason = engine.evaluate_deception_opportunity(
            assessment, ["u1", "u2"], echelon=6, experience=0.5,
        )
        assert viable is False
        assert "outside viable range" in reason

    def test_force_ratio_too_low(self) -> None:
        """Force ratio < 0.5 -> deception not viable."""
        engine = _make_engine()
        assessment = _make_assessment(force_ratio=0.3, c2=0.8)
        viable, reason = engine.evaluate_deception_opportunity(
            assessment, ["u1", "u2"], echelon=6, experience=0.5,
        )
        assert viable is False
        assert "outside viable range" in reason

    def test_c2_too_low(self) -> None:
        """Low C2 effectiveness -> not viable."""
        engine = _make_engine()
        assessment = _make_assessment(force_ratio=1.2, c2=0.3)
        viable, reason = engine.evaluate_deception_opportunity(
            assessment, ["u1", "u2"], echelon=6, experience=0.5,
        )
        assert viable is False
        assert "C2 effectiveness" in reason

    def test_echelon_too_low(self) -> None:
        """Platoon echelon -> not viable for deception."""
        engine = _make_engine()
        assessment = _make_assessment(force_ratio=1.2, c2=0.8)
        viable, reason = engine.evaluate_deception_opportunity(
            assessment, ["u1", "u2"], echelon=4, experience=0.5,
        )
        assert viable is False
        assert "Echelon too low" in reason


# ---------------------------------------------------------------------------
# evaluate_concentration_opportunity
# ---------------------------------------------------------------------------


class TestEvaluateConcentration:
    def test_viable(self) -> None:
        """Good conditions -> concentration viable."""
        engine = _make_engine()
        assessment = _make_assessment(force_ratio=1.0)
        viable, reason = engine.evaluate_concentration_opportunity(
            assessment, ["u1", "u2", "u3"], echelon=5, experience=0.4,
        )
        assert viable is True
        assert "3 units" in reason

    def test_too_few_units(self) -> None:
        """Only 2 units -> not viable."""
        engine = _make_engine()
        assessment = _make_assessment(force_ratio=1.0)
        viable, reason = engine.evaluate_concentration_opportunity(
            assessment, ["u1", "u2"], echelon=5, experience=0.4,
        )
        assert viable is False
        assert "at least 3" in reason

    def test_force_ratio_too_low(self) -> None:
        """Force ratio < 0.6 -> not viable."""
        engine = _make_engine()
        assessment = _make_assessment(force_ratio=0.4)
        viable, reason = engine.evaluate_concentration_opportunity(
            assessment, ["u1", "u2", "u3"], echelon=5, experience=0.4,
        )
        assert viable is False
        assert "too low" in reason

    def test_echelon_too_low(self) -> None:
        """Squad echelon -> not viable."""
        engine = _make_engine()
        assessment = _make_assessment(force_ratio=1.0)
        viable, reason = engine.evaluate_concentration_opportunity(
            assessment, ["u1", "u2", "u3"], echelon=3, experience=0.5,
        )
        assert viable is False
        assert "Echelon too low" in reason


# ---------------------------------------------------------------------------
# plan_concentration
# ---------------------------------------------------------------------------


class TestPlanConcentration:
    def test_creates_valid_plan(self) -> None:
        engine = _make_engine()
        plan = engine.plan_concentration(
            unit_ids=["u1", "u2", "u3"],
            concentration_point=Position(1000.0, 2000.0, 0.0),
            economy_unit_ids=["u4"],
        )
        assert isinstance(plan, StratagemPlan)
        assert plan.stratagem_type == StratagemType.CONCENTRATION
        assert "u1" in plan.units_involved
        assert "u4" in plan.units_involved
        assert len(plan.units_involved) == 4
        assert 0.0 <= plan.estimated_effect <= 1.0
        assert 0.0 <= plan.risk <= 1.0

    def test_estimated_effect_scales_with_units(self) -> None:
        engine = _make_engine()
        plan_small = engine.plan_concentration(
            ["u1", "u2"], Position(0, 0, 0), ["u3"],
        )
        plan_large = engine.plan_concentration(
            ["u1", "u2", "u3", "u4", "u5"], Position(0, 0, 0), ["u6"],
        )
        assert plan_large.estimated_effect > plan_small.estimated_effect

    def test_risk_increases_with_imbalance(self) -> None:
        """More concentration units vs economy units -> higher risk."""
        engine = _make_engine()
        plan_balanced = engine.plan_concentration(
            ["u1", "u2"], Position(0, 0, 0), ["u3", "u4"],
        )
        plan_imbalanced = engine.plan_concentration(
            ["u1", "u2", "u3", "u4"], Position(0, 0, 0), ["u5"],
        )
        assert plan_imbalanced.risk > plan_balanced.risk

    def test_target_area_from_position(self) -> None:
        engine = _make_engine()
        plan = engine.plan_concentration(
            ["u1"], Position(500.0, 750.0, 0.0), ["u2"],
        )
        assert "500" in plan.target_area
        assert "750" in plan.target_area


# ---------------------------------------------------------------------------
# plan_deception
# ---------------------------------------------------------------------------


class TestPlanDeception:
    def test_creates_valid_plan(self) -> None:
        engine = _make_engine()
        plan = engine.plan_deception(
            feint_unit_ids=["u1"],
            target_area="Hill 203",
            main_unit_ids=["u2", "u3"],
        )
        assert isinstance(plan, StratagemPlan)
        assert plan.stratagem_type == StratagemType.DECEPTION
        assert plan.target_area == "Hill 203"
        assert "u1" in plan.units_involved
        assert "u2" in plan.units_involved
        assert 0.0 <= plan.estimated_effect <= 1.0
        assert 0.0 <= plan.risk <= 1.0

    def test_effect_has_randomness(self) -> None:
        """Different seeds produce different estimated effects."""
        effects: set[float] = set()
        for seed in range(20):
            engine = _make_engine(rng=make_rng(seed))
            plan = engine.plan_deception(["u1"], "area", ["u2"])
            effects.add(round(plan.estimated_effect, 4))
        # Should see multiple distinct values
        assert len(effects) > 1

    def test_deterministic_with_same_seed(self) -> None:
        """Same seed -> same effect."""
        e1 = _make_engine(rng=make_rng(DEFAULT_SEED))
        e2 = _make_engine(rng=make_rng(DEFAULT_SEED))
        p1 = e1.plan_deception(["u1"], "area", ["u2"])
        p2 = e2.plan_deception(["u1"], "area", ["u2"])
        assert p1.estimated_effect == p2.estimated_effect

    def test_effect_within_range(self) -> None:
        """Effect should be in [0.3, 0.7]."""
        for seed in range(100):
            engine = _make_engine(rng=make_rng(seed))
            plan = engine.plan_deception(["u1"], "area", ["u2"])
            assert 0.3 <= plan.estimated_effect <= 0.7

    def test_risk_increases_with_feint_ratio(self) -> None:
        """More feint units relative to main -> higher risk."""
        engine = _make_engine()
        plan_small = engine.plan_deception(["u1"], "area", ["u2", "u3", "u4"])
        engine2 = _make_engine()
        plan_large = engine2.plan_deception(["u1", "u2", "u3"], "area", ["u4"])
        assert plan_large.risk > plan_small.risk


# ---------------------------------------------------------------------------
# activate_stratagem
# ---------------------------------------------------------------------------


class TestActivateStratagem:
    def test_publishes_event(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        received: list[StratagemActivatedEvent] = []
        event_bus.subscribe(StratagemActivatedEvent, lambda e: received.append(e))

        engine = StratagemEngine(event_bus=event_bus, rng=rng)
        plan = StratagemPlan(
            stratagem_id="sp_1",
            stratagem_type=StratagemType.DECEPTION,
            description="Feint",
            target_area="Hill 203",
            units_involved=("u1",),
            estimated_effect=0.5,
            risk=0.3,
        )
        engine.activate_stratagem("cmd_1", plan, ts=TS)

        assert len(received) == 1
        evt = received[0]
        assert evt.unit_id == "cmd_1"
        assert evt.stratagem_type == "DECEPTION"
        assert evt.target_area == "Hill 203"

    def test_event_correct_fields(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        received: list[StratagemActivatedEvent] = []
        event_bus.subscribe(StratagemActivatedEvent, lambda e: received.append(e))

        engine = StratagemEngine(event_bus=event_bus, rng=rng)
        plan = StratagemPlan(
            stratagem_id="sp_2",
            stratagem_type=StratagemType.CONCENTRATION,
            description="Mass at point",
            target_area="(1000, 2000)",
            units_involved=("u1", "u2"),
            estimated_effect=0.6,
            risk=0.4,
        )
        engine.activate_stratagem("cmd_2", plan, ts=TS)

        evt = received[0]
        assert evt.timestamp == TS
        assert evt.stratagem_type == "CONCENTRATION"
        assert evt.target_area == "(1000, 2000)"


# ---------------------------------------------------------------------------
# Multiple stratagems don't interfere
# ---------------------------------------------------------------------------


class TestMultipleStratagems:
    def test_multiple_plans_independent(self) -> None:
        """Creating multiple plans does not interfere."""
        engine = _make_engine()
        plan1 = engine.plan_concentration(
            ["u1", "u2"], Position(0, 0, 0), ["u3"],
        )
        plan2 = engine.plan_deception(["u4"], "Hill", ["u5", "u6"])
        assert plan1.stratagem_id != plan2.stratagem_id
        assert plan1.stratagem_type != plan2.stratagem_type


# ---------------------------------------------------------------------------
# State protocol
# ---------------------------------------------------------------------------


class TestStateProtocol:
    def test_get_set_state_roundtrip(self) -> None:
        engine = _make_engine()
        plan = engine.plan_concentration(
            ["u1", "u2"], Position(100, 200, 0), ["u3"],
        )

        state = engine.get_state()
        assert isinstance(state, dict)
        assert "active_plans" in state
        assert plan.stratagem_id in state["active_plans"]

        # Restore into a new engine
        engine2 = _make_engine()
        engine2.set_state(state)
        state2 = engine2.get_state()
        assert state2["active_plans"].keys() == state["active_plans"].keys()

    def test_set_state_empty(self) -> None:
        engine = _make_engine()
        engine.set_state({})
        state = engine.get_state()
        assert state["active_plans"] == {}

    def test_restored_plan_matches_original(self) -> None:
        engine = _make_engine()
        plan = engine.plan_deception(["u1"], "area", ["u2"])

        state = engine.get_state()
        engine2 = _make_engine()
        engine2.set_state(state)

        state2 = engine2.get_state()
        restored = state2["active_plans"][plan.stratagem_id]
        assert restored["stratagem_type"] == int(StratagemType.DECEPTION)
        assert restored["target_area"] == "area"
        assert restored["estimated_effect"] == plan.estimated_effect
