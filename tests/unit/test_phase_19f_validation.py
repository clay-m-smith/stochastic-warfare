"""Tests for Phase 19f -- YAML data files for 9 doctrinal schools.

Covers YAML loading, school behavior differences, determinism,
backward compatibility, opponent modeling end-to-end, and school
comparison via COA weight distributions.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stochastic_warfare.c2.ai.schools import SchoolLoader, SchoolRegistry
from stochastic_warfare.c2.ai.schools.base import DoctrinalSchool, SchoolDefinition
from stochastic_warfare.c2.ai.schools.clausewitzian import ClausewitzianSchool
from stochastic_warfare.c2.ai.schools.maneuverist import ManeuveristSchool
from stochastic_warfare.c2.ai.schools.attrition import AttritionSchool
from stochastic_warfare.c2.ai.schools.airland_battle import AirLandBattleSchool
from stochastic_warfare.c2.ai.schools.air_power import AirPowerSchool
from stochastic_warfare.c2.ai.schools.sun_tzu import SunTzuSchool
from stochastic_warfare.c2.ai.schools.deep_battle import DeepBattleSchool
from stochastic_warfare.c2.ai.schools.maritime import MahanianSchool, CorbettianSchool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Path to real data/schools/ YAML files
_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "schools"

# Mapping from school_id -> concrete subclass
_SCHOOL_CLASSES: dict[str, type[DoctrinalSchool]] = {
    "clausewitzian": ClausewitzianSchool,
    "maneuverist": ManeuveristSchool,
    "attrition": AttritionSchool,
    "airland_battle": AirLandBattleSchool,
    "air_power": AirPowerSchool,
    "sun_tzu": SunTzuSchool,
    "deep_battle": DeepBattleSchool,
    "maritime_mahanian": MahanianSchool,
    "maritime_corbettian": CorbettianSchool,
}

ALL_SCHOOL_IDS = list(_SCHOOL_CLASSES.keys())


def _load_school(school_id: str) -> DoctrinalSchool:
    """Load a school from its YAML file and instantiate the correct subclass."""
    loader = SchoolLoader(data_dir=_DATA_DIR)
    defn = loader.load_definition(_DATA_DIR / f"{school_id}.yaml")
    cls = _SCHOOL_CLASSES[defn.school_id]
    return cls(defn)


def _make_assessment_summary(
    force_ratio: float = 1.0,
    supply_level: float = 0.7,
    morale_level: float = 0.7,
    intel_quality: float = 0.5,
    c2_effectiveness: float = 0.7,
) -> dict:
    """Build a standard assessment summary dict."""
    return {
        "force_ratio": force_ratio,
        "supply_level": supply_level,
        "morale_level": morale_level,
        "intel_quality": intel_quality,
        "c2_effectiveness": c2_effectiveness,
    }


# ===========================================================================
# TestYAMLLoading -- 9 tests via parametrize
# ===========================================================================


class TestYAMLLoading:
    """Verify each of the 9 YAML files loads correctly via SchoolLoader."""

    @pytest.mark.parametrize("school_id", ALL_SCHOOL_IDS)
    def test_load_school_yaml(self, school_id: str):
        """Load YAML file and verify school_id matches."""
        loader = SchoolLoader(data_dir=_DATA_DIR)
        defn = loader.load_definition(_DATA_DIR / f"{school_id}.yaml")
        assert defn.school_id == school_id
        assert isinstance(defn, SchoolDefinition)
        assert defn.display_name  # not empty
        assert defn.ooda_multiplier > 0


# ===========================================================================
# TestSchoolBehaviorDifferences -- 8 tests
# ===========================================================================


class TestSchoolBehaviorDifferences:
    """Verify that different schools produce meaningfully different outputs."""

    def test_clausewitzian_attack_bonus_at_high_force_ratio(self):
        """Clausewitzian gives ATTACK bonus when force ratio > 1.5."""
        school = _load_school("clausewitzian")
        assessment = _make_assessment_summary(force_ratio=2.0)
        adj = school.get_decision_score_adjustments(echelon=5, assessment_summary=assessment)
        # ClausewitzianSchool adds +0.15 to ATTACK at force_ratio > 1.5
        # plus +0.1 from YAML preferred_actions
        assert adj.get("ATTACK", 0.0) > 0.2

    def test_sun_tzu_penalizes_attack_when_outnumbered(self):
        """Sun Tzu penalizes frontal ATTACK when force ratio < 1.5."""
        school = _load_school("sun_tzu")
        assessment = _make_assessment_summary(force_ratio=1.0)
        adj = school.get_decision_score_adjustments(echelon=5, assessment_summary=assessment)
        # SunTzuSchool: -0.15 when force_ratio < 1.5
        assert adj.get("ATTACK", 0.0) < 0.0

    def test_clausewitzian_vs_sun_tzu_attack_at_high_ratio(self):
        """At high force ratio, Clausewitzian gives higher ATTACK bonus than Sun Tzu."""
        claus = _load_school("clausewitzian")
        sun = _load_school("sun_tzu")
        assessment = _make_assessment_summary(force_ratio=2.0)
        adj_claus = claus.get_decision_score_adjustments(echelon=5, assessment_summary=assessment)
        adj_sun = sun.get_decision_score_adjustments(echelon=5, assessment_summary=assessment)
        # Clausewitzian: YAML +0.1 + conditional +0.15 = 0.25
        # Sun Tzu: no penalty (force_ratio >= 1.5), no ATTACK bonus
        assert adj_claus.get("ATTACK", 0.0) > adj_sun.get("ATTACK", 0.0)

    def test_maneuverist_vs_attrition_ooda_speed(self):
        """Maneuverist has faster OODA (0.7) than Attrition (1.2)."""
        maneuver = _load_school("maneuverist")
        attrit = _load_school("attrition")
        assert maneuver.get_ooda_multiplier() == pytest.approx(0.7)
        assert attrit.get_ooda_multiplier() == pytest.approx(1.2)
        assert maneuver.get_ooda_multiplier() < attrit.get_ooda_multiplier()

    def test_mahanian_attack_bonus_at_favorable_ratio(self):
        """Mahanian gives ATTACK bonus when force ratio > 1.0."""
        mahan = _load_school("maritime_mahanian")
        assessment = _make_assessment_summary(force_ratio=1.5)
        adj = mahan.get_decision_score_adjustments(echelon=5, assessment_summary=assessment)
        # MahanianSchool: YAML +0.1 + conditional +0.15 at force_ratio > 1.0
        assert adj.get("ATTACK", 0.0) > 0.2

    def test_corbettian_defend_bonus_at_moderate_ratio(self):
        """Corbettian gives DEFEND bonus when force ratio < 2.5."""
        corbett = _load_school("maritime_corbettian")
        assessment = _make_assessment_summary(force_ratio=1.5)
        adj = corbett.get_decision_score_adjustments(echelon=5, assessment_summary=assessment)
        # CorbettianSchool: YAML +0.1 + conditional +0.1 at force_ratio < 2.5
        assert adj.get("DEFEND", 0.0) > 0.15

    def test_airland_counterattack_at_brigade(self):
        """AirLand Battle has COUNTERATTACK preference at brigade echelon (8-9)."""
        airland = _load_school("airland_battle")
        assessment = _make_assessment_summary()
        adj = airland.get_decision_score_adjustments(echelon=8, assessment_summary=assessment)
        # AirLandBattleSchool: YAML +0.05 + conditional +0.15 at echelon 8-9
        assert adj.get("COUNTERATTACK", 0.0) > 0.15

    def test_air_power_deep_strike_at_corps(self):
        """Air Power has DEEP_STRIKE preference at corps+ echelon (>=10)."""
        air_pwr = _load_school("air_power")
        assessment = _make_assessment_summary()
        adj = air_pwr.get_decision_score_adjustments(echelon=10, assessment_summary=assessment)
        # AirPowerSchool: +0.25 at echelon >= 10
        assert adj.get("DEEP_STRIKE", 0.0) >= 0.25


# ===========================================================================
# TestDeterminism -- 2 tests
# ===========================================================================


class TestDeterminism:
    """Verify same YAML produces identical school definitions."""

    def test_same_yaml_same_definition(self):
        """Loading the same YAML twice produces identical definitions."""
        loader1 = SchoolLoader(data_dir=_DATA_DIR)
        defn1 = loader1.load_definition(_DATA_DIR / "clausewitzian.yaml")
        loader2 = SchoolLoader(data_dir=_DATA_DIR)
        defn2 = loader2.load_definition(_DATA_DIR / "clausewitzian.yaml")
        assert defn1.model_dump() == defn2.model_dump()

    def test_same_yaml_same_adjustments(self):
        """Same school produces identical adjustments with same inputs."""
        school1 = _load_school("maneuverist")
        school2 = _load_school("maneuverist")
        assessment = _make_assessment_summary(force_ratio=1.5)
        adj1 = school1.get_decision_score_adjustments(echelon=5, assessment_summary=assessment)
        adj2 = school2.get_decision_score_adjustments(echelon=5, assessment_summary=assessment)
        assert adj1 == adj2


# ===========================================================================
# TestBackwardCompat -- 2 tests
# ===========================================================================


class TestBackwardCompat:
    """Verify no school assigned produces baseline behavior."""

    def test_no_school_registry_returns_none(self):
        """Unit with no school assignment gets None from registry."""
        reg = SchoolRegistry()
        assert reg.get_for_unit("unit_1") is None

    def test_no_school_no_adjustments(self):
        """Base DoctrinalSchool with empty YAML produces neutral adjustments."""

        class _NullSchool(DoctrinalSchool):
            pass

        defn = SchoolDefinition(
            school_id="null",
            display_name="Null",
        )
        school = _NullSchool(defn)
        assessment = _make_assessment_summary()
        adj = school.get_decision_score_adjustments(echelon=5, assessment_summary=assessment)
        # No preferred or avoided actions -> empty adjustments
        assert adj == {}
        assert school.get_ooda_multiplier() == 1.0
        assert school.get_assessment_weight_overrides() == {}
        assert school.get_coa_score_weight_overrides() == {}
        assert school.get_risk_tolerance_override() is None
        assert school.get_stratagem_affinity() == {}


# ===========================================================================
# TestOpponentModelingEndToEnd -- 2 tests
# ===========================================================================


class TestOpponentModelingEndToEnd:
    """Verify Sun Tzu opponent modeling produces different predictions."""

    def test_sun_tzu_predicts_attack_when_opponent_strong(self):
        """When opponent has high power, Sun Tzu predicts ATTACK."""
        school = _load_school("sun_tzu")
        prediction = school.predict_opponent_action(
            own_assessment={},
            opponent_power=300.0,
            opponent_morale=0.7,
            own_power=100.0,
        )
        assert prediction["ATTACK"] > prediction["DEFEND"]
        assert prediction["ATTACK"] > prediction["WITHDRAW"]

    def test_sun_tzu_predicts_withdraw_when_opponent_weak(self):
        """When opponent is weak and demoralized, Sun Tzu predicts WITHDRAW."""
        school = _load_school("sun_tzu")
        prediction = school.predict_opponent_action(
            own_assessment={},
            opponent_power=30.0,
            opponent_morale=0.2,
            own_power=100.0,
        )
        assert prediction["WITHDRAW"] > prediction["ATTACK"]
        assert prediction["WITHDRAW"] > prediction["DEFEND"]


# ===========================================================================
# TestSchoolComparison -- 2 tests
# ===========================================================================


class TestSchoolComparison:
    """Verify different schools produce different COA weight distributions."""

    def test_maneuverist_vs_attrition_coa_weights(self):
        """Maneuverist emphasizes tempo, Attrition emphasizes preservation."""
        maneuver = _load_school("maneuverist")
        attrit = _load_school("attrition")
        man_coa = maneuver.get_coa_score_weight_overrides()
        att_coa = attrit.get_coa_score_weight_overrides()
        # Maneuverist has tempo=0.35
        assert man_coa.get("tempo", 0.0) == pytest.approx(0.35)
        # Attrition has preservation=0.35
        assert att_coa.get("preservation", 0.0) == pytest.approx(0.35)
        # They emphasize different things
        assert man_coa != att_coa

    def test_all_schools_have_distinct_definitions(self):
        """All 9 schools produce different definition dumps."""
        loader = SchoolLoader(data_dir=_DATA_DIR)
        definitions = loader.load_all()
        # Check we loaded all 9
        assert len(definitions) == 9
        # Each should have a unique school_id
        ids = [d.school_id for d in definitions]
        assert len(set(ids)) == 9
        # At least some pairs should differ in their configurations
        dumps = [d.model_dump() for d in definitions]
        # No two identical definitions
        for i in range(len(dumps)):
            for j in range(i + 1, len(dumps)):
                assert dumps[i] != dumps[j], (
                    f"Schools {ids[i]} and {ids[j]} have identical definitions"
                )
