"""Tests for Phase 19a — Doctrinal school framework and engine hooks.

Covers SchoolDefinition pydantic model, DoctrinalSchool ABC defaults,
SchoolRegistry, SchoolLoader, assessment weight overrides, decision
school adjustments, opponent prediction, and CommanderPersonality school_id.
"""

from __future__ import annotations

import textwrap
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from tests.conftest import TS, make_rng

from stochastic_warfare.c2.ai.assessment import (
    SituationAssessor,
    predict_opponent_action_lanchester,
)
from stochastic_warfare.c2.ai.commander import CommanderPersonality
from stochastic_warfare.c2.ai.decisions import DecisionEngine
from stochastic_warfare.c2.ai.schools import SchoolLoader, SchoolRegistry
from stochastic_warfare.c2.ai.schools.base import DoctrinalSchool, SchoolDefinition
from stochastic_warfare.core.events import EventBus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bus() -> EventBus:
    return EventBus()


def _rng(seed: int = 42) -> np.random.Generator:
    return make_rng(seed)


def _make_definition(**overrides) -> SchoolDefinition:
    defaults = dict(
        school_id="test_school",
        display_name="Test School",
        description="A test school",
    )
    defaults.update(overrides)
    return SchoolDefinition(**defaults)


class _ConcreteSchool(DoctrinalSchool):
    """Concrete subclass for testing the ABC (which has no abstract methods)."""
    pass


def _make_school(**overrides) -> _ConcreteSchool:
    return _ConcreteSchool(_make_definition(**overrides))


def _make_assessor(seed: int = 42) -> SituationAssessor:
    return SituationAssessor(_bus(), _rng(seed))


def _make_decision_engine(seed: int = 42) -> DecisionEngine:
    return DecisionEngine(_bus(), _rng(seed))


def _baseline_assessment(assessor: SituationAssessor):
    """Standard assessment with mid-range inputs."""
    return assessor.assess(
        unit_id="u1",
        echelon=5,
        friendly_units=10,
        friendly_power=100.0,
        morale_level=0.7,
        supply_level=0.6,
        c2_effectiveness=0.7,
        contacts=5,
        enemy_power=100.0,
        ts=TS,
    )


# ===========================================================================
# SchoolDefinition (pydantic)
# ===========================================================================


class TestSchoolDefinition:
    def test_defaults(self):
        d = _make_definition()
        assert d.school_id == "test_school"
        assert d.ooda_multiplier == 1.0
        assert d.assessment_weight_overrides == {}
        assert d.preferred_actions == {}
        assert d.avoided_actions == {}
        assert d.risk_tolerance is None
        assert d.opponent_modeling_enabled is False
        assert d.opponent_modeling_weight == 0.0

    def test_override_values(self):
        d = _make_definition(
            ooda_multiplier=0.7,
            assessment_weight_overrides={"intel": 3.0},
            preferred_actions={"ATTACK": 0.15},
            avoided_actions={"WITHDRAW": 0.1},
            risk_tolerance="high",
            opponent_modeling_enabled=True,
            opponent_modeling_weight=0.8,
        )
        assert d.ooda_multiplier == 0.7
        assert d.assessment_weight_overrides["intel"] == 3.0
        assert d.preferred_actions["ATTACK"] == 0.15
        assert d.avoided_actions["WITHDRAW"] == 0.1
        assert d.risk_tolerance == "high"
        assert d.opponent_modeling_enabled is True
        assert d.opponent_modeling_weight == 0.8

    def test_yaml_roundtrip(self, tmp_path):
        import yaml

        data = {
            "school_id": "roundtrip",
            "display_name": "Roundtrip Test",
            "ooda_multiplier": 0.85,
            "assessment_weight_overrides": {"force_ratio": 2.0},
        }
        path = tmp_path / "roundtrip.yaml"
        path.write_text(yaml.dump(data))

        loaded = yaml.safe_load(path.read_text())
        defn = SchoolDefinition.model_validate(loaded)
        assert defn.school_id == "roundtrip"
        assert defn.ooda_multiplier == 0.85
        assert defn.assessment_weight_overrides == {"force_ratio": 2.0}

    def test_ooda_multiplier_must_be_positive(self):
        with pytest.raises(Exception):
            _make_definition(ooda_multiplier=0.0)


# ===========================================================================
# DoctrinalSchool ABC
# ===========================================================================


class TestDoctrinalSchool:
    def test_instantiation(self):
        school = _make_school()
        assert school.school_id == "test_school"
        assert school.display_name == "Test School"

    def test_assessment_weight_overrides_returns_dict(self):
        school = _make_school(assessment_weight_overrides={"intel": 2.0})
        result = school.get_assessment_weight_overrides()
        assert isinstance(result, dict)
        assert result["intel"] == 2.0

    def test_decision_score_adjustments_default(self):
        school = _make_school(
            preferred_actions={"ATTACK": 0.15},
            avoided_actions={"WITHDRAW": 0.1},
        )
        adj = school.get_decision_score_adjustments(echelon=5, assessment_summary={})
        assert adj["ATTACK"] == pytest.approx(0.15)
        assert adj["WITHDRAW"] == pytest.approx(-0.1)

    def test_ooda_multiplier(self):
        school = _make_school(ooda_multiplier=0.7)
        assert school.get_ooda_multiplier() == 0.7

    def test_opponent_modeling_noop(self):
        school = _make_school()
        prediction = school.predict_opponent_action({}, 100, 0.5, 100)
        assert prediction == {}
        adjusted = school.adjust_scores_for_opponent({"ATTACK": 0.5}, {})
        assert adjusted == {"ATTACK": 0.5}


# ===========================================================================
# SchoolRegistry
# ===========================================================================


class TestSchoolRegistry:
    def test_register_and_get(self):
        reg = SchoolRegistry()
        school = _make_school(school_id="clausewitz")
        reg.register(school)
        assert reg.get("clausewitz") is school

    def test_get_missing_returns_none(self):
        reg = SchoolRegistry()
        assert reg.get("nonexistent") is None

    def test_all_schools(self):
        reg = SchoolRegistry()
        s1 = _make_school(school_id="a")
        s2 = _make_school(school_id="b")
        reg.register(s1)
        reg.register(s2)
        assert len(reg.all_schools()) == 2

    def test_assign_to_unit(self):
        reg = SchoolRegistry()
        school = _make_school(school_id="maneuver")
        reg.register(school)
        reg.assign_to_unit("unit_1", "maneuver")
        assert reg.get_for_unit("unit_1") is school

    def test_assign_to_unit_unknown_school_raises(self):
        reg = SchoolRegistry()
        with pytest.raises(KeyError):
            reg.assign_to_unit("unit_1", "nonexistent")

    def test_get_for_unit_unassigned_returns_none(self):
        reg = SchoolRegistry()
        assert reg.get_for_unit("unit_1") is None

    def test_state_roundtrip(self):
        reg = SchoolRegistry()
        school = _make_school(school_id="test")
        reg.register(school)
        reg.assign_to_unit("u1", "test")
        state = reg.get_state()
        assert "unit_assignments" in state
        assert state["unit_assignments"]["u1"] == "test"

        # Restore on a fresh registry (schools must be re-registered first)
        reg2 = SchoolRegistry()
        reg2.register(school)
        reg2.set_state(state)
        assert reg2.get_for_unit("u1") is school


# ===========================================================================
# SchoolLoader
# ===========================================================================


class TestSchoolLoader:
    def test_load_definition(self, tmp_path):
        import yaml

        data = {
            "school_id": "loader_test",
            "display_name": "Loader Test",
            "ooda_multiplier": 0.9,
        }
        path = tmp_path / "loader_test.yaml"
        path.write_text(yaml.dump(data))

        loader = SchoolLoader(data_dir=tmp_path)
        defn = loader.load_definition(path)
        assert defn.school_id == "loader_test"
        assert defn.ooda_multiplier == 0.9

    def test_load_all(self, tmp_path):
        import yaml

        for i in range(3):
            data = {"school_id": f"school_{i}", "display_name": f"School {i}"}
            (tmp_path / f"school_{i}.yaml").write_text(yaml.dump(data))

        loader = SchoolLoader(data_dir=tmp_path)
        result = loader.load_all()
        assert len(result) == 3
        assert sorted(loader.available_schools()) == ["school_0", "school_1", "school_2"]


# ===========================================================================
# Assessment weight overrides
# ===========================================================================


class TestAssessmentWeightOverrides:
    def test_no_override_matches_baseline(self):
        a1 = _make_assessor(seed=100)
        a2 = _make_assessor(seed=100)
        r1 = a1.assess(
            unit_id="u1", echelon=5, friendly_units=10,
            friendly_power=100.0, morale_level=0.7, supply_level=0.6,
            c2_effectiveness=0.7, contacts=5, enemy_power=100.0, ts=TS,
        )
        r2 = a2.assess(
            unit_id="u1", echelon=5, friendly_units=10,
            friendly_power=100.0, morale_level=0.7, supply_level=0.6,
            c2_effectiveness=0.7, contacts=5, enemy_power=100.0, ts=TS,
            weight_overrides=None,
        )
        assert r1.overall_rating == r2.overall_rating

    def test_single_factor_override(self):
        """Boosting intel weight should change overall when intel differs."""
        assessor = _make_assessor(seed=100)
        # Low intel scenario
        r_base = assessor.assess(
            unit_id="u1", echelon=5, friendly_units=10,
            friendly_power=100.0, morale_level=0.7, supply_level=0.6,
            c2_effectiveness=0.7, contacts=0, enemy_power=100.0, ts=TS,
        )
        assessor2 = _make_assessor(seed=100)
        r_boosted = assessor2.assess(
            unit_id="u1", echelon=5, friendly_units=10,
            friendly_power=100.0, morale_level=0.7, supply_level=0.6,
            c2_effectiveness=0.7, contacts=0, enemy_power=100.0, ts=TS,
            weight_overrides={"intel": 5.0},
        )
        # With 0 contacts, intel is 0 (VERY_UNFAVORABLE).
        # Boosting intel weight should lower overall rating
        assert r_boosted.overall_rating <= r_base.overall_rating

    def test_multiple_overrides(self):
        assessor = _make_assessor(seed=100)
        result = assessor.assess(
            unit_id="u1", echelon=5, friendly_units=10,
            friendly_power=300.0, morale_level=0.7, supply_level=0.6,
            c2_effectiveness=0.7, contacts=5, enemy_power=100.0, ts=TS,
            weight_overrides={"force_ratio": 2.0, "intel": 0.5},
        )
        # Just verify it runs without error and returns valid assessment
        assert result.overall_rating >= 0

    def test_renormalization(self):
        """Weights should sum to 1.0 after override and renormalization."""
        assessor = _make_assessor(seed=100)
        # This should not crash — all weights multiplied by 2.0 then renormalized
        result = assessor.assess(
            unit_id="u1", echelon=5, friendly_units=10,
            friendly_power=100.0, morale_level=0.7, supply_level=0.6,
            c2_effectiveness=0.7, contacts=5, enemy_power=100.0, ts=TS,
            weight_overrides={"force_ratio": 2.0, "terrain": 2.0, "supply": 2.0,
                              "morale": 2.0, "intel": 2.0, "environmental": 2.0, "c2": 2.0},
        )
        # Uniform multiplier should give same result as no override
        assessor2 = _make_assessor(seed=100)
        r_base = assessor2.assess(
            unit_id="u1", echelon=5, friendly_units=10,
            friendly_power=100.0, morale_level=0.7, supply_level=0.6,
            c2_effectiveness=0.7, contacts=5, enemy_power=100.0, ts=TS,
        )
        assert result.overall_rating == r_base.overall_rating

    def test_zero_weight_factor(self):
        """Setting a weight to 0 should effectively remove that factor."""
        assessor = _make_assessor(seed=100)
        result = assessor.assess(
            unit_id="u1", echelon=5, friendly_units=10,
            friendly_power=10.0, morale_level=0.7, supply_level=0.6,
            c2_effectiveness=0.7, contacts=5, enemy_power=100.0, ts=TS,
            weight_overrides={"force_ratio": 0.0},  # Remove force ratio impact
        )
        # Terrible force ratio (0.1) should be ignored
        # Without force_ratio, other factors (morale, supply, c2 all decent) dominate
        assert result.overall_rating >= 1  # At least UNFAVORABLE (not VERY_UNFAVORABLE)


# ===========================================================================
# Decision school adjustments
# ===========================================================================


class TestDecisionSchoolAdjustments:
    def _make_assessment(self):
        assessor = _make_assessor(seed=100)
        return assessor.assess(
            unit_id="u1", echelon=5, friendly_units=10,
            friendly_power=100.0, morale_level=0.7, supply_level=0.6,
            c2_effectiveness=0.7, contacts=5, enemy_power=100.0, ts=TS,
        )

    def test_no_adjustments_matches_baseline(self):
        eng1 = _make_decision_engine(seed=200)
        eng2 = _make_decision_engine(seed=200)
        assessment = self._make_assessment()
        r1 = eng1.decide("u1", 5, assessment, None, None, ts=TS)
        r2 = eng2.decide("u1", 5, assessment, None, None, ts=TS, school_adjustments=None)
        assert r1.action_name == r2.action_name

    def test_positive_bonus_favors_action(self):
        """Large positive bonus should make that action likely."""
        eng = _make_decision_engine(seed=200)
        assessment = self._make_assessment()
        # Give DEFEND a huge bonus
        result = eng.decide(
            "u1", 6, assessment, None, None, ts=TS,
            school_adjustments={"DEFEND": 5.0},
        )
        assert result.action_name == "DEFEND"

    def test_negative_penalty_disfavors_action(self):
        """Large negative penalty on normally-chosen action should change outcome."""
        # First find baseline action
        eng1 = _make_decision_engine(seed=300)
        assessment = self._make_assessment()
        baseline = eng1.decide("u1", 6, assessment, None, None, ts=TS)

        # Now penalize that action heavily
        eng2 = _make_decision_engine(seed=300)
        result = eng2.decide(
            "u1", 6, assessment, None, None, ts=TS,
            school_adjustments={baseline.action_name: -10.0},
        )
        assert result.action_name != baseline.action_name

    def test_adjustments_only_apply_to_existing_actions(self):
        """Adjustments for non-existent actions should be silently ignored."""
        eng = _make_decision_engine(seed=200)
        assessment = self._make_assessment()
        # NONEXISTENT_ACTION shouldn't cause errors
        result = eng.decide(
            "u1", 6, assessment, None, None, ts=TS,
            school_adjustments={"NONEXISTENT_ACTION": 5.0},
        )
        assert result.action_name  # Some valid action selected

    def test_combined_with_personality(self):
        """School adjustments work alongside personality noise."""
        personality = CommanderPersonality(
            profile_id="aggressive",
            display_name="Aggressive",
            description="Aggressive commander",
            aggression=0.9,
            caution=0.1,
            flexibility=0.5,
            initiative=0.8,
            experience=0.9,  # Low noise
        )
        eng = _make_decision_engine(seed=200)
        assessment = self._make_assessment()
        result = eng.decide(
            "u1", 6, assessment, personality, None, ts=TS,
            school_adjustments={"DEFEND": 5.0},
        )
        # Despite aggressive personality, huge DEFEND bonus should dominate
        assert result.action_name == "DEFEND"


# ===========================================================================
# Opponent prediction
# ===========================================================================


class TestPredictOpponent:
    def test_high_ratio_favors_attack(self):
        """When opponent has high force ratio, predict ATTACK."""
        result = predict_opponent_action_lanchester(
            opponent_power=300.0, own_power=100.0, opponent_morale=0.7,
        )
        assert result["ATTACK"] > result["DEFEND"]
        assert result["ATTACK"] > result["WITHDRAW"]

    def test_low_ratio_favors_withdraw(self):
        """When opponent is outnumbered, predict WITHDRAW."""
        result = predict_opponent_action_lanchester(
            opponent_power=30.0, own_power=100.0, opponent_morale=0.7,
        )
        assert result["WITHDRAW"] > result["ATTACK"]

    def test_low_morale_shifts_toward_withdraw(self):
        result = predict_opponent_action_lanchester(
            opponent_power=100.0, own_power=100.0, opponent_morale=0.2,
        )
        result_high_morale = predict_opponent_action_lanchester(
            opponent_power=100.0, own_power=100.0, opponent_morale=0.7,
        )
        assert result["WITHDRAW"] > result_high_morale["WITHDRAW"]

    def test_probabilities_sum_to_one(self):
        result = predict_opponent_action_lanchester(150.0, 100.0, 0.5)
        total = sum(result.values())
        assert total == pytest.approx(1.0)

    def test_own_power_zero(self):
        result = predict_opponent_action_lanchester(100.0, 0.0, 0.5)
        assert result["ATTACK"] > 0.5  # Opponent should almost certainly attack


# ===========================================================================
# CommanderPersonality school_id
# ===========================================================================


class TestCommanderSchoolId:
    def test_default_none(self):
        p = CommanderPersonality(
            profile_id="test",
            display_name="Test",
            description="Test",
            aggression=0.5,
            caution=0.5,
            flexibility=0.5,
            initiative=0.5,
            experience=0.5,
        )
        assert p.school_id is None

    def test_assigned_value(self):
        p = CommanderPersonality(
            profile_id="test",
            display_name="Test",
            description="Test",
            aggression=0.5,
            caution=0.5,
            flexibility=0.5,
            initiative=0.5,
            experience=0.5,
            school_id="clausewitzian",
        )
        assert p.school_id == "clausewitzian"
