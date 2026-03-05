"""Phase 24d — AI escalation logic tests.

Tests new commander personality fields, decision/adaptation/stratagem enum
extensions, and assessment helper functions for escalation awareness.
~50 tests covering commander traits, decision enums, adaptation triggers,
stratagem requirements, and desperation/consequence assessment helpers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.conftest import TS

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------

from stochastic_warfare.c2.ai.commander import (
    CommanderPersonality,
    CommanderProfileLoader,
)
from stochastic_warfare.c2.ai.decisions import (
    BrigadeDivAction,
    CorpsAction,
    DecisionCategory,
    _categorize_action,
    _OFFENSIVE_NAMES,
    _C2_NAMES,
)
from stochastic_warfare.c2.ai.adaptation import (
    AdaptationAction,
    AdaptationTrigger,
)
from stochastic_warfare.c2.ai.stratagems import (
    StratagemEngine,
    StratagemType,
    _STRATAGEM_REQUIREMENTS,
)
from stochastic_warfare.c2.ai.assessment import (
    compute_desperation_index,
    estimate_escalation_consequences,
)


# ===================================================================
# 1. Commander traits (~8 tests)
# ===================================================================


class TestCommanderTraits:
    """New personality fields with correct defaults and constraints."""

    def test_doctrine_violation_tolerance_default(self) -> None:
        p = CommanderPersonality(
            profile_id="t1",
            display_name="T",
            description="d",
            aggression=0.5,
            caution=0.5,
            flexibility=0.5,
            initiative=0.5,
            experience=0.5,
        )
        assert p.doctrine_violation_tolerance == pytest.approx(0.2)

    def test_collateral_tolerance_default(self) -> None:
        p = CommanderPersonality(
            profile_id="t2",
            display_name="T",
            description="d",
            aggression=0.5,
            caution=0.5,
            flexibility=0.5,
            initiative=0.5,
            experience=0.5,
        )
        assert p.collateral_tolerance == pytest.approx(0.3)

    def test_escalation_awareness_default(self) -> None:
        p = CommanderPersonality(
            profile_id="t3",
            display_name="T",
            description="d",
            aggression=0.5,
            caution=0.5,
            flexibility=0.5,
            initiative=0.5,
            experience=0.5,
        )
        assert p.escalation_awareness == pytest.approx(0.5)

    def test_fields_constrained_lower_bound(self) -> None:
        """Values below 0.0 should be rejected by pydantic."""
        with pytest.raises(Exception):
            CommanderPersonality(
                profile_id="bad",
                display_name="Bad",
                description="d",
                aggression=0.5,
                caution=0.5,
                flexibility=0.5,
                initiative=0.5,
                experience=0.5,
                doctrine_violation_tolerance=-0.1,
            )

    def test_fields_constrained_upper_bound(self) -> None:
        """Values above 1.0 should be rejected by pydantic."""
        with pytest.raises(Exception):
            CommanderPersonality(
                profile_id="bad",
                display_name="Bad",
                description="d",
                aggression=0.5,
                caution=0.5,
                flexibility=0.5,
                initiative=0.5,
                experience=0.5,
                collateral_tolerance=1.5,
            )

    def test_yaml_loading_with_new_fields(self) -> None:
        """Load a new profile YAML that includes the new fields."""
        loader = CommanderProfileLoader()
        data_dir = Path(__file__).resolve().parents[2] / "data" / "commander_profiles"
        profile = loader.load_definition(data_dir / "ruthless_authoritarian.yaml")
        assert profile.doctrine_violation_tolerance == pytest.approx(0.9)
        assert profile.collateral_tolerance == pytest.approx(0.8)
        assert profile.escalation_awareness == pytest.approx(0.2)

    def test_yaml_loading_without_new_fields_uses_defaults(self) -> None:
        """Load an existing profile YAML that lacks the new fields -- defaults apply."""
        loader = CommanderProfileLoader()
        data_dir = Path(__file__).resolve().parents[2] / "data" / "commander_profiles"
        profile = loader.load_definition(data_dir / "aggressive_armor.yaml")
        assert profile.doctrine_violation_tolerance == pytest.approx(0.2)
        assert profile.collateral_tolerance == pytest.approx(0.3)
        assert profile.escalation_awareness == pytest.approx(0.5)

    def test_extreme_values_profile_loads(self) -> None:
        """Profile with boundary values (0.0 and 1.0) loads correctly."""
        p = CommanderPersonality(
            profile_id="extreme",
            display_name="Extreme",
            description="Boundary test",
            aggression=1.0,
            caution=0.0,
            flexibility=1.0,
            initiative=0.0,
            experience=1.0,
            doctrine_violation_tolerance=1.0,
            collateral_tolerance=0.0,
            escalation_awareness=1.0,
        )
        assert p.doctrine_violation_tolerance == pytest.approx(1.0)
        assert p.collateral_tolerance == pytest.approx(0.0)
        assert p.escalation_awareness == pytest.approx(1.0)


# ===================================================================
# 2. Decision enums (~12 tests)
# ===================================================================


class TestDecisionEnums:
    """BrigadeDivAction and CorpsAction extended with escalation actions."""

    def test_brigade_employ_prohibited_weapon_value(self) -> None:
        assert BrigadeDivAction.EMPLOY_PROHIBITED_WEAPON == 10

    def test_brigade_authorize_escalation_value(self) -> None:
        assert BrigadeDivAction.AUTHORIZE_ESCALATION == 11

    def test_brigade_order_scorched_earth_value(self) -> None:
        assert BrigadeDivAction.ORDER_SCORCHED_EARTH == 12

    def test_corps_employ_chemical_value(self) -> None:
        assert CorpsAction.EMPLOY_CHEMICAL == 7

    def test_corps_authorize_nuclear_value(self) -> None:
        assert CorpsAction.AUTHORIZE_NUCLEAR == 8

    def test_employ_prohibited_weapon_in_offensive(self) -> None:
        assert "EMPLOY_PROHIBITED_WEAPON" in _OFFENSIVE_NAMES

    def test_employ_chemical_in_offensive(self) -> None:
        assert "EMPLOY_CHEMICAL" in _OFFENSIVE_NAMES

    def test_authorize_nuclear_in_offensive(self) -> None:
        assert "AUTHORIZE_NUCLEAR" in _OFFENSIVE_NAMES

    def test_authorize_escalation_in_c2(self) -> None:
        assert "AUTHORIZE_ESCALATION" in _C2_NAMES

    def test_order_scorched_earth_in_c2(self) -> None:
        assert "ORDER_SCORCHED_EARTH" in _C2_NAMES

    def test_existing_brigade_values_unchanged(self) -> None:
        assert BrigadeDivAction.ATTACK == 0
        assert BrigadeDivAction.DEFEND == 1
        assert BrigadeDivAction.RESERVE == 9

    def test_existing_corps_values_unchanged(self) -> None:
        assert CorpsAction.MAIN_ATTACK == 0
        assert CorpsAction.TRANSITION == 6

    def test_brigade_total_member_count(self) -> None:
        assert len(BrigadeDivAction) == 13

    def test_corps_total_member_count(self) -> None:
        assert len(CorpsAction) == 9

    def test_categorize_employ_prohibited_weapon(self) -> None:
        assert _categorize_action("EMPLOY_PROHIBITED_WEAPON") == DecisionCategory.OFFENSIVE

    def test_categorize_authorize_escalation(self) -> None:
        assert _categorize_action("AUTHORIZE_ESCALATION") == DecisionCategory.C2

    def test_categorize_order_scorched_earth(self) -> None:
        assert _categorize_action("ORDER_SCORCHED_EARTH") == DecisionCategory.C2


# ===================================================================
# 3. Adaptation triggers (~12 tests)
# ===================================================================


class TestAdaptationEnums:
    """AdaptationTrigger and AdaptationAction extended for escalation."""

    def test_military_stalemate_value(self) -> None:
        assert AdaptationTrigger.MILITARY_STALEMATE == 7

    def test_political_pressure_value(self) -> None:
        assert AdaptationTrigger.POLITICAL_PRESSURE == 8

    def test_escalate_force_value(self) -> None:
        assert AdaptationAction.ESCALATE_FORCE == 7

    def test_de_escalate_value(self) -> None:
        assert AdaptationAction.DE_ESCALATE == 8

    def test_existing_trigger_casualties_unchanged(self) -> None:
        assert AdaptationTrigger.CASUALTIES == 0

    def test_existing_trigger_c2_disruption_unchanged(self) -> None:
        assert AdaptationTrigger.C2_DISRUPTION == 6

    def test_existing_action_continue_unchanged(self) -> None:
        assert AdaptationAction.CONTINUE == 0

    def test_existing_action_issue_frago_unchanged(self) -> None:
        assert AdaptationAction.ISSUE_FRAGO == 6

    def test_trigger_total_member_count(self) -> None:
        assert len(AdaptationTrigger) == 9

    def test_action_total_member_count(self) -> None:
        assert len(AdaptationAction) == 9

    def test_military_stalemate_name(self) -> None:
        assert AdaptationTrigger.MILITARY_STALEMATE.name == "MILITARY_STALEMATE"

    def test_escalate_force_name(self) -> None:
        assert AdaptationAction.ESCALATE_FORCE.name == "ESCALATE_FORCE"


# ===================================================================
# 4. Stratagems (~10 tests)
# ===================================================================


class TestStratagemEnums:
    """StratagemType extended with unconventional warfare types."""

    def test_sabotage_campaign_value(self) -> None:
        assert StratagemType.SABOTAGE_CAMPAIGN == 6

    def test_terror_value(self) -> None:
        assert StratagemType.TERROR == 7

    def test_scorched_earth_value(self) -> None:
        assert StratagemType.SCORCHED_EARTH == 8

    def test_sabotage_requirements(self) -> None:
        req = _STRATAGEM_REQUIREMENTS[StratagemType.SABOTAGE_CAMPAIGN]
        assert req == (8, 0.5)

    def test_terror_requirements(self) -> None:
        req = _STRATAGEM_REQUIREMENTS[StratagemType.TERROR]
        assert req == (9, 0.3)

    def test_scorched_earth_requirements(self) -> None:
        req = _STRATAGEM_REQUIREMENTS[StratagemType.SCORCHED_EARTH]
        assert req == (8, 0.4)

    def test_sabotage_echelon_too_low(self, rng, event_bus) -> None:
        engine = StratagemEngine(event_bus, rng)
        # Echelon 7 (battalion+) is below 8 (brigade)
        assert engine.can_employ_stratagem(
            "u1", echelon=7, experience=0.9, stratagem_type=StratagemType.SABOTAGE_CAMPAIGN
        ) is False

    def test_sabotage_experience_too_low(self, rng, event_bus) -> None:
        engine = StratagemEngine(event_bus, rng)
        assert engine.can_employ_stratagem(
            "u1", echelon=8, experience=0.3, stratagem_type=StratagemType.SABOTAGE_CAMPAIGN
        ) is False

    def test_sabotage_meets_both(self, rng, event_bus) -> None:
        engine = StratagemEngine(event_bus, rng)
        assert engine.can_employ_stratagem(
            "u1", echelon=8, experience=0.5, stratagem_type=StratagemType.SABOTAGE_CAMPAIGN
        ) is True

    def test_terror_requires_division(self, rng, event_bus) -> None:
        engine = StratagemEngine(event_bus, rng)
        # Echelon 8 is below 9 (division)
        assert engine.can_employ_stratagem(
            "u1", echelon=8, experience=0.5, stratagem_type=StratagemType.TERROR
        ) is False
        # Echelon 9 is division
        assert engine.can_employ_stratagem(
            "u1", echelon=9, experience=0.5, stratagem_type=StratagemType.TERROR
        ) is True


# ===================================================================
# 5. Assessment helpers (~8 tests)
# ===================================================================


class TestDesperationIndex:
    """compute_desperation_index: weighted factor composite."""

    def test_casualty_factor_only(self) -> None:
        """100% casualties, all other factors zero."""
        result = compute_desperation_index(
            casualties_sustained=100,
            initial_strength=100,
            supply_state=1.0,
            avg_morale=1.0,
            stalemate_duration_s=0.0,
            domestic_pressure=0.0,
        )
        # Only casualty_weight (0.30) * 1.0 = 0.30
        assert result == pytest.approx(0.30, abs=1e-9)

    def test_supply_factor_only(self) -> None:
        """Supply at 0.0 (max desperation from supply)."""
        result = compute_desperation_index(
            casualties_sustained=0,
            initial_strength=100,
            supply_state=0.0,
            avg_morale=1.0,
            stalemate_duration_s=0.0,
            domestic_pressure=0.0,
        )
        assert result == pytest.approx(0.20, abs=1e-9)

    def test_morale_factor_only(self) -> None:
        """Morale at 0.0."""
        result = compute_desperation_index(
            casualties_sustained=0,
            initial_strength=100,
            supply_state=1.0,
            avg_morale=0.0,
            stalemate_duration_s=0.0,
            domestic_pressure=0.0,
        )
        assert result == pytest.approx(0.20, abs=1e-9)

    def test_stalemate_factor_only(self) -> None:
        """Full stalemate (259200s)."""
        result = compute_desperation_index(
            casualties_sustained=0,
            initial_strength=100,
            supply_state=1.0,
            avg_morale=1.0,
            stalemate_duration_s=259200.0,
            domestic_pressure=0.0,
        )
        assert result == pytest.approx(0.15, abs=1e-9)

    def test_political_factor_only(self) -> None:
        """Max domestic pressure."""
        result = compute_desperation_index(
            casualties_sustained=0,
            initial_strength=100,
            supply_state=1.0,
            avg_morale=1.0,
            stalemate_duration_s=0.0,
            domestic_pressure=1.0,
        )
        assert result == pytest.approx(0.15, abs=1e-9)

    def test_combined_computation(self) -> None:
        """All factors at 50%."""
        result = compute_desperation_index(
            casualties_sustained=50,
            initial_strength=100,
            supply_state=0.5,
            avg_morale=0.5,
            stalemate_duration_s=129600.0,  # half of normalize
            domestic_pressure=0.5,
        )
        # 0.30*0.5 + 0.20*0.5 + 0.20*0.5 + 0.15*0.5 + 0.15*0.5
        # = 0.15 + 0.10 + 0.10 + 0.075 + 0.075 = 0.50
        assert result == pytest.approx(0.50, abs=1e-9)

    def test_clamped_to_unit_range(self) -> None:
        """Extreme inputs produce result in [0,1]."""
        result = compute_desperation_index(
            casualties_sustained=1000,
            initial_strength=100,
            supply_state=0.0,
            avg_morale=0.0,
            stalemate_duration_s=1000000.0,
            domestic_pressure=5.0,
        )
        assert 0.0 <= result <= 1.0

    def test_zero_strength_no_division_error(self) -> None:
        """initial_strength=0 should not cause ZeroDivisionError."""
        result = compute_desperation_index(
            casualties_sustained=10,
            initial_strength=0,
            supply_state=1.0,
            avg_morale=1.0,
            stalemate_duration_s=0.0,
            domestic_pressure=0.0,
        )
        assert 0.0 <= result <= 1.0


class TestEscalationConsequences:
    """estimate_escalation_consequences: level * awareness."""

    def test_level_zero_returns_zero(self) -> None:
        assert estimate_escalation_consequences(0, 1.0) == pytest.approx(0.0)

    def test_level_ten_full_awareness(self) -> None:
        assert estimate_escalation_consequences(10, 1.0) == pytest.approx(1.0)

    def test_low_awareness_underestimates(self) -> None:
        """Low awareness should produce lower consequence estimate."""
        low = estimate_escalation_consequences(5, 0.2)
        high = estimate_escalation_consequences(5, 0.8)
        assert low < high

    def test_clamped_to_unit_range(self) -> None:
        """Even extreme inputs produce result in [0,1]."""
        result = estimate_escalation_consequences(20, 2.0)
        assert result <= 1.0

    def test_mid_level_mid_awareness(self) -> None:
        """Level 5, awareness 0.5 -> 0.5 * 0.1 * 5 = 0.25."""
        result = estimate_escalation_consequences(5, 0.5)
        assert result == pytest.approx(0.25, abs=1e-9)

    def test_zero_awareness_always_zero(self) -> None:
        """Zero awareness means always underestimates to 0."""
        assert estimate_escalation_consequences(10, 0.0) == pytest.approx(0.0)

    def test_level_one_full_awareness(self) -> None:
        """Level 1, awareness 1.0 -> 0.1."""
        assert estimate_escalation_consequences(1, 1.0) == pytest.approx(0.1)
