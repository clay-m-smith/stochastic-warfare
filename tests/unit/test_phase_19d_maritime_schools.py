"""Tests for Phase 19d -- Maritime doctrinal schools (Mahanian and Corbettian).

Covers MahanianSchool (fleet concentration, decisive battle) and
CorbettianSchool (fleet-in-being, sea denial, selective engagement).
"""

from __future__ import annotations

import pytest

from tests.conftest import TS, make_rng

from stochastic_warfare.c2.ai.schools.base import SchoolDefinition
from stochastic_warfare.c2.ai.schools.maritime import CorbettianSchool, MahanianSchool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mahanian_def(**overrides) -> SchoolDefinition:
    defaults = dict(
        school_id="mahanian",
        display_name="Mahanian",
        description="Fleet concentration, decisive naval battle",
        ooda_multiplier=0.95,
        risk_tolerance="high",
        assessment_weight_overrides={"force_ratio": 1.5},
    )
    defaults.update(overrides)
    return SchoolDefinition(**defaults)


def _corbettian_def(**overrides) -> SchoolDefinition:
    defaults = dict(
        school_id="corbettian",
        display_name="Corbettian",
        description="Fleet-in-being, sea denial, selective engagement",
        ooda_multiplier=1.1,
        risk_tolerance="low",
        assessment_weight_overrides={"intel": 1.3},
    )
    defaults.update(overrides)
    return SchoolDefinition(**defaults)


def _make_mahanian(**overrides) -> MahanianSchool:
    return MahanianSchool(_mahanian_def(**overrides))


def _make_corbettian(**overrides) -> CorbettianSchool:
    return CorbettianSchool(_corbettian_def(**overrides))


def _assessment(force_ratio: float = 1.0, **kw) -> dict:
    """Build a minimal assessment_summary dict."""
    base = {
        "force_ratio": force_ratio,
        "supply_level": 0.7,
        "morale_level": 0.7,
        "intel_quality": 0.6,
        "c2_effectiveness": 0.8,
    }
    base.update(kw)
    return base


# ===========================================================================
# MahanianSchool
# ===========================================================================


class TestMahanianSchool:
    def test_instantiation(self):
        school = _make_mahanian()
        assert school.school_id == "mahanian"
        assert school.display_name == "Mahanian"

    def test_attack_preference_at_favorable_ratio(self):
        """When force_ratio > 1.0, ATTACK and MAIN_ATTACK get +0.15 bonus."""
        school = _make_mahanian()
        adj = school.get_decision_score_adjustments(5, _assessment(force_ratio=1.5))
        assert adj.get("ATTACK", 0.0) >= 0.15
        assert adj.get("MAIN_ATTACK", 0.0) >= 0.15

    def test_no_attack_bonus_at_parity(self):
        """When force_ratio == 1.0 (not > 1.0), no offensive bonus applied."""
        school = _make_mahanian()
        adj = school.get_decision_score_adjustments(5, _assessment(force_ratio=1.0))
        # No preferred_actions in default def, so ATTACK should not have a bonus
        assert adj.get("ATTACK", 0.0) == pytest.approx(0.0)
        assert adj.get("MAIN_ATTACK", 0.0) == pytest.approx(0.0)

    def test_avoids_dispersal_bypass_penalized(self):
        """BYPASS always gets a -0.1 penalty regardless of force ratio."""
        school = _make_mahanian()
        # Even at unfavorable ratio
        adj_unfav = school.get_decision_score_adjustments(5, _assessment(force_ratio=0.5))
        assert adj_unfav["BYPASS"] == pytest.approx(-0.1)
        # Also at favorable ratio
        adj_fav = school.get_decision_score_adjustments(5, _assessment(force_ratio=2.0))
        assert adj_fav["BYPASS"] == pytest.approx(-0.1)

    def test_high_risk_tolerance(self):
        """Mahanian school has high risk tolerance (seek decisive battle)."""
        school = _make_mahanian()
        assert school.get_risk_tolerance_override() == "high"

    def test_ooda_multiplier(self):
        """Mahanian OODA multiplier slightly faster (0.95) -- aggressive tempo."""
        school = _make_mahanian()
        assert school.get_ooda_multiplier() == pytest.approx(0.95)

    def test_assessment_weights(self):
        """Mahanian school emphasizes force_ratio in assessment."""
        school = _make_mahanian()
        weights = school.get_assessment_weight_overrides()
        assert weights["force_ratio"] == 1.5

    def test_backward_compat_yaml_preferred_actions(self):
        """YAML preferred_actions are still applied via super()."""
        school = _make_mahanian(preferred_actions={"ENVELOP": 0.2})
        adj = school.get_decision_score_adjustments(5, _assessment(force_ratio=0.8))
        # Should include the YAML bonus even when conditional logic doesn't fire
        assert adj.get("ENVELOP", 0.0) == pytest.approx(0.2)


# ===========================================================================
# CorbettianSchool
# ===========================================================================


class TestCorbettianSchool:
    def test_instantiation(self):
        school = _make_corbettian()
        assert school.school_id == "corbettian"
        assert school.display_name == "Corbettian"

    def test_avoids_decisive_engagement_unfavorable(self):
        """When force_ratio < 2.5, ATTACK is penalized by -0.15."""
        school = _make_corbettian()
        adj = school.get_decision_score_adjustments(5, _assessment(force_ratio=1.0))
        assert adj.get("ATTACK", 0.0) <= -0.15

    def test_sea_denial_defend_bonus(self):
        """When force_ratio < 2.5, DEFEND and DELAY get bonuses."""
        school = _make_corbettian()
        adj = school.get_decision_score_adjustments(5, _assessment(force_ratio=1.5))
        assert adj.get("DEFEND", 0.0) >= 0.1
        assert adj.get("DELAY", 0.0) >= 0.1

    def test_attacks_when_overwhelming(self):
        """When force_ratio >= 2.5, ATTACK gets +0.1 (selective engagement)."""
        school = _make_corbettian()
        adj = school.get_decision_score_adjustments(5, _assessment(force_ratio=3.0))
        assert adj.get("ATTACK", 0.0) >= 0.1
        # DEFEND and DELAY should NOT have bonuses at overwhelming ratio
        assert adj.get("DEFEND", 0.0) == pytest.approx(0.0)
        assert adj.get("DELAY", 0.0) == pytest.approx(0.0)

    def test_low_risk_tolerance(self):
        """Corbettian school has low risk tolerance (preserve the fleet)."""
        school = _make_corbettian()
        assert school.get_risk_tolerance_override() == "low"

    def test_ooda_multiplier(self):
        """Corbettian OODA multiplier slightly slower (1.1) -- deliberate."""
        school = _make_corbettian()
        assert school.get_ooda_multiplier() == pytest.approx(1.1)

    def test_backward_compat_yaml_avoided_actions(self):
        """YAML avoided_actions are still applied via super()."""
        school = _make_corbettian(avoided_actions={"WITHDRAW": 0.05})
        adj = school.get_decision_score_adjustments(5, _assessment(force_ratio=3.0))
        # At overwhelming ratio, only ATTACK bonus applies from conditional logic
        # But YAML avoided_actions should still subtract
        assert adj.get("WITHDRAW", 0.0) == pytest.approx(-0.05)
