"""Tests for Phase 19c — Eastern/Historical doctrinal schools.

Covers SunTzuSchool (intel-first, deception, opponent modeling) and
DeepBattleSchool (echeloned assault, reserve management, deep strike).
"""

from __future__ import annotations

import pytest

from tests.conftest import TS, make_rng

from stochastic_warfare.c2.ai.assessment import predict_opponent_action_lanchester
from stochastic_warfare.c2.ai.schools.base import SchoolDefinition
from stochastic_warfare.c2.ai.schools.deep_battle import DeepBattleSchool
from stochastic_warfare.c2.ai.schools.sun_tzu import SunTzuSchool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sun_tzu_definition(**overrides) -> SchoolDefinition:
    defaults = dict(
        school_id="sun_tzu",
        display_name="Sun Tzu",
        description="Intel-first, deception, indirect approach",
        preferred_actions={"AMBUSH": 0.1},
        avoided_actions={"FRONTAL_ASSAULT": 0.1},
        ooda_multiplier=0.85,
        opponent_modeling_enabled=True,
        opponent_modeling_weight=0.8,
        stratagem_affinity={"DECEPTION": 0.3, "FEINT": 0.2},
    )
    defaults.update(overrides)
    return SchoolDefinition(**defaults)


def _deep_battle_definition(**overrides) -> SchoolDefinition:
    defaults = dict(
        school_id="deep_battle",
        display_name="Deep Battle",
        description="Echeloned assault, operational depth",
        preferred_actions={"ECHELON_ATTACK": 0.1},
        avoided_actions={},
        ooda_multiplier=1.1,
    )
    defaults.update(overrides)
    return SchoolDefinition(**defaults)


def _make_sun_tzu(**overrides) -> SunTzuSchool:
    return SunTzuSchool(_sun_tzu_definition(**overrides))


def _make_deep_battle(**overrides) -> DeepBattleSchool:
    return DeepBattleSchool(_deep_battle_definition(**overrides))


# ===========================================================================
# SunTzuSchool — Basic hooks
# ===========================================================================


class TestSunTzuBasic:
    def test_school_id(self):
        school = _make_sun_tzu()
        assert school.school_id == "sun_tzu"

    def test_display_name(self):
        school = _make_sun_tzu()
        assert school.display_name == "Sun Tzu"

    def test_ooda_multiplier(self):
        school = _make_sun_tzu()
        assert school.get_ooda_multiplier() == 0.85

    def test_stratagem_affinity(self):
        school = _make_sun_tzu()
        aff = school.get_stratagem_affinity()
        assert aff["DECEPTION"] == 0.3
        assert aff["FEINT"] == 0.2

    def test_preferred_actions_included(self):
        """YAML preferred_actions should appear in adjustments via super()."""
        school = _make_sun_tzu()
        adj = school.get_decision_score_adjustments(5, {"force_ratio": 2.0, "intel_quality": 0.8})
        assert adj.get("AMBUSH", 0.0) >= 0.1  # At least the YAML preferred bonus

    def test_avoided_actions_included(self):
        """YAML avoided_actions should appear as negative adjustments via super()."""
        school = _make_sun_tzu()
        adj = school.get_decision_score_adjustments(5, {"force_ratio": 2.0, "intel_quality": 0.8})
        assert adj.get("FRONTAL_ASSAULT", 0.0) <= -0.1


# ===========================================================================
# SunTzuSchool — Decision score adjustments
# ===========================================================================


class TestSunTzuDecisionScores:
    def test_attack_penalty_when_outnumbered(self):
        """ATTACK penalty when force_ratio < 1.5."""
        school = _make_sun_tzu()
        adj = school.get_decision_score_adjustments(5, {"force_ratio": 1.0, "intel_quality": 0.8})
        assert adj["ATTACK"] < 0  # Should be negative (penalty)

    def test_no_attack_penalty_when_superior(self):
        """No ATTACK penalty when force_ratio >= 1.5."""
        school = _make_sun_tzu(preferred_actions={}, avoided_actions={})
        adj = school.get_decision_score_adjustments(5, {"force_ratio": 1.5, "intel_quality": 0.8})
        assert adj.get("ATTACK", 0.0) == 0.0  # No penalty applied

    def test_recon_bonus_on_low_intel(self):
        """Low intel_quality (< 0.3) triggers RECON bonus."""
        school = _make_sun_tzu()
        adj = school.get_decision_score_adjustments(5, {"force_ratio": 2.0, "intel_quality": 0.1})
        assert adj.get("RECON", 0.0) >= 0.2

    def test_no_recon_bonus_on_high_intel(self):
        """No RECON bonus when intel_quality >= 0.3."""
        school = _make_sun_tzu(preferred_actions={}, avoided_actions={})
        adj = school.get_decision_score_adjustments(5, {"force_ratio": 2.0, "intel_quality": 0.5})
        assert adj.get("RECON", 0.0) == 0.0

    def test_flank_bonus_always_present(self):
        """FLANK bonus (+0.1) applied regardless of conditions."""
        school = _make_sun_tzu(preferred_actions={}, avoided_actions={})
        adj = school.get_decision_score_adjustments(5, {"force_ratio": 2.0, "intel_quality": 0.8})
        assert adj.get("FLANK", 0.0) == pytest.approx(0.1)


# ===========================================================================
# SunTzuSchool — Opponent prediction
# ===========================================================================


class TestSunTzuOpponentPrediction:
    """Verify predict_opponent_action delegates to Lanchester heuristic."""

    def test_strong_opponent_predicts_attack(self):
        school = _make_sun_tzu()
        pred = school.predict_opponent_action({}, 300.0, 0.7, 100.0)
        assert pred["ATTACK"] > pred["DEFEND"]

    def test_weak_opponent_predicts_withdraw(self):
        school = _make_sun_tzu()
        pred = school.predict_opponent_action({}, 30.0, 0.7, 100.0)
        assert pred["WITHDRAW"] > pred["ATTACK"]

    def test_equal_forces_predicts_defend(self):
        school = _make_sun_tzu()
        pred = school.predict_opponent_action({}, 100.0, 0.7, 100.0)
        assert pred["DEFEND"] >= pred["ATTACK"]

    def test_probabilities_sum_to_one(self):
        school = _make_sun_tzu()
        pred = school.predict_opponent_action({}, 150.0, 0.5, 100.0)
        assert sum(pred.values()) == pytest.approx(1.0)

    def test_matches_standalone_function(self):
        """School prediction should match standalone Lanchester function."""
        school = _make_sun_tzu()
        school_pred = school.predict_opponent_action({}, 200.0, 0.6, 100.0)
        direct_pred = predict_opponent_action_lanchester(200.0, 100.0, 0.6)
        for key in ("ATTACK", "DEFEND", "WITHDRAW"):
            assert school_pred[key] == pytest.approx(direct_pred[key])


# ===========================================================================
# SunTzuSchool — Opponent-adjusted scores
# ===========================================================================


class TestSunTzuOpponentAdjusted:
    def test_counter_attack_boosts_ambush_and_flank(self):
        """When opponent predicted to ATTACK (prob > 0.4), bonus to AMBUSH and FLANK."""
        school = _make_sun_tzu(opponent_modeling_weight=1.0)
        scores = {"AMBUSH": 0.5, "FLANK": 0.3, "DEFEND": 0.4}
        prediction = {"ATTACK": 0.7, "DEFEND": 0.2, "WITHDRAW": 0.1}
        adjusted = school.adjust_scores_for_opponent(scores, prediction)
        assert adjusted["AMBUSH"] == pytest.approx(0.5 + 0.15)
        assert adjusted["FLANK"] == pytest.approx(0.3 + 0.1)
        assert adjusted["DEFEND"] == 0.4  # Unchanged

    def test_counter_defend_boosts_bypass_and_flank(self):
        """When opponent predicted to DEFEND (prob > 0.4), bonus to BYPASS and FLANK."""
        school = _make_sun_tzu(opponent_modeling_weight=1.0)
        scores = {"BYPASS": 0.3, "FLANK": 0.3, "ATTACK": 0.5}
        prediction = {"ATTACK": 0.1, "DEFEND": 0.7, "WITHDRAW": 0.2}
        adjusted = school.adjust_scores_for_opponent(scores, prediction)
        assert adjusted["BYPASS"] == pytest.approx(0.3 + 0.15)
        assert adjusted["FLANK"] == pytest.approx(0.3 + 0.1)
        assert adjusted["ATTACK"] == 0.5  # Unchanged

    def test_counter_withdraw_boosts_pursue_and_exploit(self):
        """When opponent predicted to WITHDRAW (prob > 0.4), bonus to PURSUE and EXPLOIT."""
        school = _make_sun_tzu(opponent_modeling_weight=1.0)
        scores = {"PURSUE": 0.2, "EXPLOIT": 0.3, "DEFEND": 0.4}
        prediction = {"ATTACK": 0.1, "DEFEND": 0.2, "WITHDRAW": 0.7}
        adjusted = school.adjust_scores_for_opponent(scores, prediction)
        assert adjusted["PURSUE"] == pytest.approx(0.2 + 0.15)
        assert adjusted["EXPLOIT"] == pytest.approx(0.3 + 0.1)
        assert adjusted["DEFEND"] == 0.4  # Unchanged

    def test_weight_scales_adjustments(self):
        """Opponent modeling weight of 0.5 should halve the bonuses."""
        school = _make_sun_tzu(opponent_modeling_weight=0.5)
        scores = {"AMBUSH": 0.5, "FLANK": 0.3}
        prediction = {"ATTACK": 0.7, "DEFEND": 0.2, "WITHDRAW": 0.1}
        adjusted = school.adjust_scores_for_opponent(scores, prediction)
        assert adjusted["AMBUSH"] == pytest.approx(0.5 + 0.15 * 0.5)
        assert adjusted["FLANK"] == pytest.approx(0.3 + 0.1 * 0.5)

    def test_missing_keys_not_added(self):
        """Only existing keys in own_scores are adjusted."""
        school = _make_sun_tzu(opponent_modeling_weight=1.0)
        scores = {"DEFEND": 0.5}  # No AMBUSH or FLANK
        prediction = {"ATTACK": 0.7, "DEFEND": 0.2, "WITHDRAW": 0.1}
        adjusted = school.adjust_scores_for_opponent(scores, prediction)
        assert "AMBUSH" not in adjusted
        assert "FLANK" not in adjusted
        assert adjusted["DEFEND"] == 0.5

    def test_no_adjustment_below_threshold(self):
        """No counter-posture bonus when no action exceeds 0.4 probability."""
        school = _make_sun_tzu(opponent_modeling_weight=1.0)
        scores = {"AMBUSH": 0.5, "BYPASS": 0.3, "PURSUE": 0.2}
        prediction = {"ATTACK": 0.35, "DEFEND": 0.35, "WITHDRAW": 0.3}
        adjusted = school.adjust_scores_for_opponent(scores, prediction)
        assert adjusted == scores


# ===========================================================================
# DeepBattleSchool — Basic hooks
# ===========================================================================


class TestDeepBattleBasic:
    def test_school_id(self):
        school = _make_deep_battle()
        assert school.school_id == "deep_battle"

    def test_display_name(self):
        school = _make_deep_battle()
        assert school.display_name == "Deep Battle"

    def test_ooda_multiplier(self):
        school = _make_deep_battle()
        assert school.get_ooda_multiplier() == 1.1

    def test_preferred_actions_included(self):
        """YAML preferred_actions appear via super()."""
        school = _make_deep_battle()
        adj = school.get_decision_score_adjustments(5, {"force_ratio": 0.5})
        assert adj.get("ECHELON_ATTACK", 0.0) >= 0.1


# ===========================================================================
# DeepBattleSchool — Decision score adjustments
# ===========================================================================


class TestDeepBattleDecisionScores:
    def test_attack_and_exploit_on_high_force_ratio(self):
        """Force ratio > 2.0: bonus to ATTACK and EXPLOIT."""
        school = _make_deep_battle(preferred_actions={}, avoided_actions={})
        adj = school.get_decision_score_adjustments(5, {"force_ratio": 2.5})
        assert adj.get("ATTACK", 0.0) == pytest.approx(0.15)
        assert adj.get("EXPLOIT", 0.0) == pytest.approx(0.1)

    def test_reserve_on_moderate_force_ratio(self):
        """1.0 < force_ratio <= 2.0: bonus to RESERVE."""
        school = _make_deep_battle(preferred_actions={}, avoided_actions={})
        adj = school.get_decision_score_adjustments(5, {"force_ratio": 1.5})
        assert adj.get("RESERVE", 0.0) == pytest.approx(0.15)
        assert adj.get("ATTACK", 0.0) == 0.0  # Not high enough for attack bonus

    def test_no_bonus_when_outnumbered(self):
        """Force ratio <= 1.0: no offensive or reserve bonuses."""
        school = _make_deep_battle(preferred_actions={}, avoided_actions={})
        adj = school.get_decision_score_adjustments(5, {"force_ratio": 0.8})
        assert adj.get("ATTACK", 0.0) == 0.0
        assert adj.get("EXPLOIT", 0.0) == 0.0
        assert adj.get("RESERVE", 0.0) == 0.0

    def test_deep_strike_at_corps(self):
        """Corps+ (echelon >= 10): bonus to DEEP_STRIKE and OPERATIONAL_MANEUVER."""
        school = _make_deep_battle(preferred_actions={}, avoided_actions={})
        adj = school.get_decision_score_adjustments(10, {"force_ratio": 0.5})
        assert adj.get("DEEP_STRIKE", 0.0) == pytest.approx(0.2)
        assert adj.get("OPERATIONAL_MANEUVER", 0.0) == pytest.approx(0.15)

    def test_no_deep_strike_below_corps(self):
        """Below corps (echelon < 10): no deep strike bonuses."""
        school = _make_deep_battle(preferred_actions={}, avoided_actions={})
        adj = school.get_decision_score_adjustments(9, {"force_ratio": 0.5})
        assert adj.get("DEEP_STRIKE", 0.0) == 0.0
        assert adj.get("OPERATIONAL_MANEUVER", 0.0) == 0.0
