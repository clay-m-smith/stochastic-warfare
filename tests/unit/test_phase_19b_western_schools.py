"""Tests for Phase 19b — five Western doctrinal school classes.

Covers ClausewitzianSchool, ManeuveristSchool, AttritionSchool,
AirLandBattleSchool, and AirPowerSchool.  Each school is tested for
instantiation, YAML-driven hooks, conditional decision adjustments
under favorable/unfavorable/neutral scenarios, OODA multiplier, COA
weights, risk tolerance, and backward compatibility.
"""

from __future__ import annotations

import pytest

from stochastic_warfare.c2.ai.schools.base import DoctrinalSchool, SchoolDefinition
from stochastic_warfare.c2.ai.schools.clausewitzian import ClausewitzianSchool
from stochastic_warfare.c2.ai.schools.maneuverist import ManeuveristSchool
from stochastic_warfare.c2.ai.schools.attrition import AttritionSchool
from stochastic_warfare.c2.ai.schools.airland_battle import AirLandBattleSchool
from stochastic_warfare.c2.ai.schools.air_power import AirPowerSchool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NEUTRAL_ASSESSMENT = {
    "force_ratio": 1.0,
    "supply_level": 0.8,
    "morale_level": 0.8,
    "intel_quality": 0.5,
    "c2_effectiveness": 0.7,
}

_FAVORABLE_ASSESSMENT = {
    "force_ratio": 2.5,
    "supply_level": 0.9,
    "morale_level": 0.9,
    "intel_quality": 0.85,
    "c2_effectiveness": 0.9,
}

_UNFAVORABLE_ASSESSMENT = {
    "force_ratio": 0.6,
    "supply_level": 0.2,
    "morale_level": 0.3,
    "intel_quality": 0.3,
    "c2_effectiveness": 0.4,
}


def _make_definition(
    school_id: str = "test_school",
    display_name: str = "Test School",
    *,
    preferred_actions: dict[str, float] | None = None,
    avoided_actions: dict[str, float] | None = None,
    ooda_multiplier: float = 1.0,
    coa_score_weight_overrides: dict[str, float] | None = None,
    risk_tolerance: str | None = None,
    assessment_weight_overrides: dict[str, float] | None = None,
) -> SchoolDefinition:
    return SchoolDefinition(
        school_id=school_id,
        display_name=display_name,
        description="Test definition",
        preferred_actions=preferred_actions or {},
        avoided_actions=avoided_actions or {},
        ooda_multiplier=ooda_multiplier,
        coa_score_weight_overrides=coa_score_weight_overrides or {},
        risk_tolerance=risk_tolerance,
        assessment_weight_overrides=assessment_weight_overrides or {},
    )


# ===================================================================
# Clausewitzian School
# ===================================================================


class TestClausewitzianSchool:
    """ClausewitzianSchool — center-of-gravity targeting."""

    def test_instantiation(self):
        defn = _make_definition("clausewitzian", "Clausewitzian")
        school = ClausewitzianSchool(defn)
        assert isinstance(school, DoctrinalSchool)
        assert school.school_id == "clausewitzian"
        assert school.display_name == "Clausewitzian"

    def test_favorable_force_ratio_offensive_bonus(self):
        """Force ratio > 1.5 triggers ATTACK/MAIN_ATTACK/ENVELOP bonus."""
        school = ClausewitzianSchool(_make_definition())
        adj = school.get_decision_score_adjustments(7, _FAVORABLE_ASSESSMENT)
        assert adj.get("ATTACK", 0.0) == pytest.approx(0.15)
        assert adj.get("MAIN_ATTACK", 0.0) == pytest.approx(0.15)
        assert adj.get("ENVELOP", 0.0) == pytest.approx(0.15)

    def test_no_offensive_bonus_at_neutral(self):
        """Force ratio <= 1.5 should NOT trigger offensive bonus."""
        school = ClausewitzianSchool(_make_definition())
        adj = school.get_decision_score_adjustments(7, _NEUTRAL_ASSESSMENT)
        assert adj.get("ATTACK", 0.0) == pytest.approx(0.0)
        assert adj.get("MAIN_ATTACK", 0.0) == pytest.approx(0.0)

    def test_culmination_low_supply(self):
        """Supply < 0.3 triggers CONSOLIDATE and DEFEND bonus."""
        assessment = {**_NEUTRAL_ASSESSMENT, "supply_level": 0.2}
        school = ClausewitzianSchool(_make_definition())
        adj = school.get_decision_score_adjustments(7, assessment)
        assert adj.get("CONSOLIDATE", 0.0) == pytest.approx(0.15)
        assert adj.get("DEFEND", 0.0) == pytest.approx(0.1)

    def test_culmination_low_morale(self):
        """Morale < 0.4 triggers CONSOLIDATE and DEFEND bonus."""
        assessment = {**_NEUTRAL_ASSESSMENT, "morale_level": 0.3}
        school = ClausewitzianSchool(_make_definition())
        adj = school.get_decision_score_adjustments(7, assessment)
        assert adj.get("CONSOLIDATE", 0.0) == pytest.approx(0.15)
        assert adj.get("DEFEND", 0.0) == pytest.approx(0.1)

    def test_combined_offensive_and_culmination(self):
        """High force ratio + low supply produces both effects."""
        school = ClausewitzianSchool(_make_definition())
        adj = school.get_decision_score_adjustments(7, _UNFAVORABLE_ASSESSMENT)
        # force_ratio 0.6 <= 1.5: no offensive bonus
        assert adj.get("ATTACK", 0.0) == pytest.approx(0.0)
        # supply 0.2 < 0.3: culmination
        assert adj.get("CONSOLIDATE", 0.0) == pytest.approx(0.15)

    def test_yaml_preferred_actions_stacked(self):
        """YAML preferred_actions stack with conditional logic."""
        defn = _make_definition(preferred_actions={"ATTACK": 0.05})
        school = ClausewitzianSchool(defn)
        adj = school.get_decision_score_adjustments(7, _FAVORABLE_ASSESSMENT)
        # 0.05 (YAML) + 0.15 (conditional) = 0.20
        assert adj["ATTACK"] == pytest.approx(0.20)

    def test_yaml_avoided_actions_applied(self):
        """YAML avoided_actions produce negative adjustments."""
        defn = _make_definition(avoided_actions={"WITHDRAW": 0.1})
        school = ClausewitzianSchool(defn)
        adj = school.get_decision_score_adjustments(7, _NEUTRAL_ASSESSMENT)
        assert adj["WITHDRAW"] == pytest.approx(-0.1)

    def test_ooda_multiplier(self):
        defn = _make_definition(ooda_multiplier=0.9)
        school = ClausewitzianSchool(defn)
        assert school.get_ooda_multiplier() == pytest.approx(0.9)

    def test_assessment_weight_overrides(self):
        defn = _make_definition(assessment_weight_overrides={"force_ratio": 1.3})
        school = ClausewitzianSchool(defn)
        overrides = school.get_assessment_weight_overrides()
        assert overrides["force_ratio"] == pytest.approx(1.3)


# ===================================================================
# Maneuverist School
# ===================================================================


class TestManeuveristSchool:
    """ManeuveristSchool — tempo-driven maneuver (Boyd)."""

    def test_instantiation(self):
        defn = _make_definition("maneuverist", "Maneuverist")
        school = ManeuveristSchool(defn)
        assert isinstance(school, DoctrinalSchool)
        assert school.school_id == "maneuverist"

    def test_maneuver_bonuses_always_applied(self):
        """FLANK, BYPASS, EXPLOIT, PURSUE get +0.15 regardless of assessment."""
        school = ManeuveristSchool(_make_definition())
        adj = school.get_decision_score_adjustments(7, _NEUTRAL_ASSESSMENT)
        for action in ("FLANK", "BYPASS", "EXPLOIT", "PURSUE"):
            assert adj.get(action, 0.0) == pytest.approx(0.15), f"{action} missing"

    def test_attack_penalty_low_force_ratio(self):
        """ATTACK penalised when force_ratio < 2.0."""
        school = ManeuveristSchool(_make_definition())
        adj = school.get_decision_score_adjustments(7, _NEUTRAL_ASSESSMENT)
        assert adj.get("ATTACK", 0.0) == pytest.approx(-0.1)

    def test_no_attack_penalty_high_force_ratio(self):
        """ATTACK not penalised when force_ratio >= 2.0."""
        assessment = {**_NEUTRAL_ASSESSMENT, "force_ratio": 2.5}
        school = ManeuveristSchool(_make_definition())
        adj = school.get_decision_score_adjustments(7, assessment)
        assert adj.get("ATTACK", 0.0) == pytest.approx(0.0)

    def test_yaml_preferred_stacked(self):
        """YAML preferred adds to maneuver bonus."""
        defn = _make_definition(preferred_actions={"FLANK": 0.05})
        school = ManeuveristSchool(defn)
        adj = school.get_decision_score_adjustments(7, _NEUTRAL_ASSESSMENT)
        assert adj["FLANK"] == pytest.approx(0.20)

    def test_ooda_multiplier_fast(self):
        """Maneuverist typically has faster OODA."""
        defn = _make_definition(ooda_multiplier=0.75)
        school = ManeuveristSchool(defn)
        assert school.get_ooda_multiplier() == pytest.approx(0.75)

    def test_coa_weight_overrides(self):
        defn = _make_definition(coa_score_weight_overrides={"tempo": 1.5})
        school = ManeuveristSchool(defn)
        assert school.get_coa_score_weight_overrides()["tempo"] == pytest.approx(1.5)

    def test_risk_tolerance(self):
        defn = _make_definition(risk_tolerance="high")
        school = ManeuveristSchool(defn)
        assert school.get_risk_tolerance_override() == "high"


# ===================================================================
# Attrition School
# ===================================================================


class TestAttritionSchool:
    """AttritionSchool — exchange ratio optimisation."""

    def test_instantiation(self):
        defn = _make_definition("attrition", "Attrition")
        school = AttritionSchool(defn)
        assert isinstance(school, DoctrinalSchool)
        assert school.school_id == "attrition"

    def test_favorable_force_ratio_attack(self):
        """Force ratio > 1.5 gives ATTACK bonus."""
        school = AttritionSchool(_make_definition())
        adj = school.get_decision_score_adjustments(7, _FAVORABLE_ASSESSMENT)
        assert adj.get("ATTACK", 0.0) == pytest.approx(0.1)
        # Should NOT have defensive bonuses
        assert adj.get("DEFEND", 0.0) == pytest.approx(0.0)

    def test_unfavorable_force_ratio_defense(self):
        """Force ratio <= 1.5 gives DEFEND and SUPPORT_BY_FIRE bonus."""
        school = AttritionSchool(_make_definition())
        adj = school.get_decision_score_adjustments(7, _NEUTRAL_ASSESSMENT)
        assert adj.get("DEFEND", 0.0) == pytest.approx(0.15)
        assert adj.get("SUPPORT_BY_FIRE", 0.0) == pytest.approx(0.1)
        # No ATTACK bonus
        assert adj.get("ATTACK", 0.0) == pytest.approx(0.0)

    def test_borderline_force_ratio(self):
        """Force ratio exactly 1.5 should trigger defensive path."""
        assessment = {**_NEUTRAL_ASSESSMENT, "force_ratio": 1.5}
        school = AttritionSchool(_make_definition())
        adj = school.get_decision_score_adjustments(7, assessment)
        assert adj.get("DEFEND", 0.0) == pytest.approx(0.15)

    def test_yaml_avoided_stacked(self):
        """YAML avoided_actions combine with conditional logic."""
        defn = _make_definition(avoided_actions={"BYPASS": 0.2})
        school = AttritionSchool(defn)
        adj = school.get_decision_score_adjustments(7, _NEUTRAL_ASSESSMENT)
        assert adj["BYPASS"] == pytest.approx(-0.2)

    def test_ooda_default(self):
        school = AttritionSchool(_make_definition())
        assert school.get_ooda_multiplier() == pytest.approx(1.0)


# ===================================================================
# AirLand Battle School
# ===================================================================


class TestAirLandBattleSchool:
    """AirLandBattleSchool — simultaneous deep/close/rear."""

    def test_instantiation(self):
        defn = _make_definition("airland_battle", "AirLand Battle")
        school = AirLandBattleSchool(defn)
        assert isinstance(school, DoctrinalSchool)
        assert school.school_id == "airland_battle"

    def test_corps_echelon_deep_strike(self):
        """Echelon >= 10 triggers DEEP_STRIKE and OPERATIONAL_MANEUVER."""
        school = AirLandBattleSchool(_make_definition())
        adj = school.get_decision_score_adjustments(10, _NEUTRAL_ASSESSMENT)
        assert adj.get("DEEP_STRIKE", 0.0) == pytest.approx(0.2)
        assert adj.get("OPERATIONAL_MANEUVER", 0.0) == pytest.approx(0.15)

    def test_brigade_echelon_close_fight(self):
        """Echelon 8-9 triggers ATTACK and COUNTERATTACK."""
        school = AirLandBattleSchool(_make_definition())
        adj = school.get_decision_score_adjustments(8, _NEUTRAL_ASSESSMENT)
        assert adj.get("ATTACK", 0.0) == pytest.approx(0.1)
        assert adj.get("COUNTERATTACK", 0.0) == pytest.approx(0.15)

    def test_division_echelon_close_fight(self):
        """Echelon 9 also in brigade/div range."""
        school = AirLandBattleSchool(_make_definition())
        adj = school.get_decision_score_adjustments(9, _NEUTRAL_ASSESSMENT)
        assert adj.get("ATTACK", 0.0) == pytest.approx(0.1)
        assert adj.get("COUNTERATTACK", 0.0) == pytest.approx(0.15)

    def test_high_intel_exploit(self):
        """Intel quality > 0.7 enables EXPLOIT bonus."""
        school = AirLandBattleSchool(_make_definition())
        adj = school.get_decision_score_adjustments(7, _FAVORABLE_ASSESSMENT)
        assert adj.get("EXPLOIT", 0.0) == pytest.approx(0.15)

    def test_low_intel_no_exploit(self):
        """Intel quality <= 0.7 does not produce EXPLOIT bonus."""
        school = AirLandBattleSchool(_make_definition())
        adj = school.get_decision_score_adjustments(7, _NEUTRAL_ASSESSMENT)
        assert adj.get("EXPLOIT", 0.0) == pytest.approx(0.0)

    def test_corps_with_high_intel_combined(self):
        """Corps echelon + high intel produces both deep strike and exploit."""
        school = AirLandBattleSchool(_make_definition())
        adj = school.get_decision_score_adjustments(11, _FAVORABLE_ASSESSMENT)
        assert adj.get("DEEP_STRIKE", 0.0) == pytest.approx(0.2)
        assert adj.get("EXPLOIT", 0.0) == pytest.approx(0.15)

    def test_platoon_echelon_no_bonuses(self):
        """Echelon < 8 with low intel produces no conditional adjustments."""
        school = AirLandBattleSchool(_make_definition())
        adj = school.get_decision_score_adjustments(5, _NEUTRAL_ASSESSMENT)
        assert adj.get("DEEP_STRIKE", 0.0) == pytest.approx(0.0)
        assert adj.get("ATTACK", 0.0) == pytest.approx(0.0)
        assert adj.get("EXPLOIT", 0.0) == pytest.approx(0.0)

    def test_yaml_preferred_stacked(self):
        defn = _make_definition(preferred_actions={"DEEP_STRIKE": 0.05})
        school = AirLandBattleSchool(defn)
        adj = school.get_decision_score_adjustments(10, _NEUTRAL_ASSESSMENT)
        # 0.05 (YAML) + 0.2 (conditional) = 0.25
        assert adj["DEEP_STRIKE"] == pytest.approx(0.25)


# ===================================================================
# Air Power School
# ===================================================================


class TestAirPowerSchool:
    """AirPowerSchool — Five Rings strategic targeting (Warden)."""

    def test_instantiation(self):
        defn = _make_definition("air_power", "Air Power")
        school = AirPowerSchool(defn)
        assert isinstance(school, DoctrinalSchool)
        assert school.school_id == "air_power"

    def test_corps_deep_strike_bonus(self):
        """Echelon >= 10 gives strong DEEP_STRIKE bonus."""
        school = AirPowerSchool(_make_definition())
        adj = school.get_decision_score_adjustments(10, _NEUTRAL_ASSESSMENT)
        assert adj.get("DEEP_STRIKE", 0.0) == pytest.approx(0.25)

    def test_corps_main_attack_penalty(self):
        """Echelon >= 10 penalises MAIN_ATTACK."""
        school = AirPowerSchool(_make_definition())
        adj = school.get_decision_score_adjustments(10, _NEUTRAL_ASSESSMENT)
        assert adj.get("MAIN_ATTACK", 0.0) == pytest.approx(-0.15)

    def test_brigade_defend_and_delay(self):
        """Echelon 8-9 gives DEFEND and DELAY bonus."""
        school = AirPowerSchool(_make_definition())
        adj = school.get_decision_score_adjustments(8, _NEUTRAL_ASSESSMENT)
        assert adj.get("DEFEND", 0.0) == pytest.approx(0.1)
        assert adj.get("DELAY", 0.0) == pytest.approx(0.1)

    def test_division_defend_and_delay(self):
        """Echelon 9 also in brigade/div range."""
        school = AirPowerSchool(_make_definition())
        adj = school.get_decision_score_adjustments(9, _NEUTRAL_ASSESSMENT)
        assert adj.get("DEFEND", 0.0) == pytest.approx(0.1)
        assert adj.get("DELAY", 0.0) == pytest.approx(0.1)

    def test_platoon_echelon_no_bonuses(self):
        """Low echelon produces no conditional adjustments."""
        school = AirPowerSchool(_make_definition())
        adj = school.get_decision_score_adjustments(5, _NEUTRAL_ASSESSMENT)
        assert adj.get("DEEP_STRIKE", 0.0) == pytest.approx(0.0)
        assert adj.get("DEFEND", 0.0) == pytest.approx(0.0)
        assert adj.get("DELAY", 0.0) == pytest.approx(0.0)

    def test_yaml_avoided_stacked(self):
        """YAML avoided_actions stack with conditional penalty."""
        defn = _make_definition(avoided_actions={"MAIN_ATTACK": 0.05})
        school = AirPowerSchool(defn)
        adj = school.get_decision_score_adjustments(10, _NEUTRAL_ASSESSMENT)
        # -0.05 (YAML) + -0.15 (conditional) = -0.20
        assert adj["MAIN_ATTACK"] == pytest.approx(-0.20)


# ===================================================================
# Cross-cutting / backward compatibility
# ===================================================================


class TestBackwardCompatibility:
    """Backward compatibility and default behavior."""

    @pytest.mark.parametrize(
        "cls",
        [ClausewitzianSchool, ManeuveristSchool, AttritionSchool, AirLandBattleSchool, AirPowerSchool],
    )
    def test_empty_definition_no_error(self, cls):
        """All schools instantiate with a minimal definition."""
        defn = _make_definition()
        school = cls(defn)
        adj = school.get_decision_score_adjustments(7, _NEUTRAL_ASSESSMENT)
        assert isinstance(adj, dict)

    @pytest.mark.parametrize(
        "cls",
        [ClausewitzianSchool, ManeuveristSchool, AttritionSchool, AirLandBattleSchool, AirPowerSchool],
    )
    def test_empty_assessment_no_error(self, cls):
        """Missing assessment keys fall back to defaults without crashing."""
        defn = _make_definition()
        school = cls(defn)
        adj = school.get_decision_score_adjustments(7, {})
        assert isinstance(adj, dict)

    @pytest.mark.parametrize(
        "cls",
        [ClausewitzianSchool, ManeuveristSchool, AttritionSchool, AirLandBattleSchool, AirPowerSchool],
    )
    def test_definition_property_accessible(self, cls):
        defn = _make_definition()
        school = cls(defn)
        assert school.definition is defn

    @pytest.mark.parametrize(
        "cls",
        [ClausewitzianSchool, ManeuveristSchool, AttritionSchool, AirLandBattleSchool, AirPowerSchool],
    )
    def test_stratagem_affinity_from_yaml(self, cls):
        defn = _make_definition()
        defn_with_strat = SchoolDefinition(
            school_id="test",
            display_name="Test",
            stratagem_affinity={"DECEPTION": 0.3},
        )
        school = cls(defn_with_strat)
        assert school.get_stratagem_affinity() == {"DECEPTION": 0.3}

    @pytest.mark.parametrize(
        "cls",
        [ClausewitzianSchool, ManeuveristSchool, AttritionSchool, AirLandBattleSchool, AirPowerSchool],
    )
    def test_opponent_modeling_default_empty(self, cls):
        """Default opponent modeling returns empty dict."""
        defn = _make_definition()
        school = cls(defn)
        pred = school.predict_opponent_action({}, 100.0, 0.8, 100.0)
        assert pred == {}
