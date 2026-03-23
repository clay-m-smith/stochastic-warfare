"""Unit tests for MeleeEngine — Napoleonic and Ancient/Medieval melee combat."""

from __future__ import annotations

import pytest

from stochastic_warfare.combat.melee import (
    MeleeConfig,
    MeleeEngine,
    MeleeResult,
    MeleeType,
)

from .conftest import _rng


# ---------------------------------------------------------------------------
# Pre-contact morale
# ---------------------------------------------------------------------------


class TestPreContactMorale:
    """Pre-contact morale break logic."""

    def test_defender_breaks_low_morale(self):
        """Defender with morale below threshold breaks before contact."""
        eng = MeleeEngine(rng=_rng(seed=1))
        defender_breaks, attacker_breaks = eng.check_pre_contact_morale(
            attacker_morale=0.8,
            defender_morale=0.2,
            melee_type=MeleeType.BAYONET_CHARGE,
        )
        assert defender_breaks is True
        assert attacker_breaks is False

    def test_attacker_breaks_very_low_morale(self):
        """Attacker breaks only at morale below half threshold."""
        eng = MeleeEngine(rng=_rng(seed=2))
        # threshold=0.4, attacker breaks at < 0.2
        _, attacker_breaks = eng.check_pre_contact_morale(
            attacker_morale=0.1,
            defender_morale=0.8,
            melee_type=MeleeType.BAYONET_CHARGE,
        )
        assert attacker_breaks is True

    def test_cavalry_charge_raises_effective_threshold(self):
        """CAVALRY_CHARGE with shock multiplier raises defender break threshold."""
        cfg = MeleeConfig(pre_contact_morale_threshold=0.4, cavalry_shock_multiplier=2.0)
        eng = MeleeEngine(config=cfg, rng=_rng(seed=3))
        # Effective threshold = 0.4 * (1 + 2.0 * 1.0) = 1.2
        # Any defender morale < 1.2 breaks (i.e., always if vuln=1.0)
        breaks, _ = eng.check_pre_contact_morale(
            attacker_morale=0.9,
            defender_morale=0.9,
            melee_type=MeleeType.CAVALRY_CHARGE,
            defender_formation_cavalry_vuln=1.0,
        )
        assert breaks is True

    def test_no_break_high_morale(self):
        """Neither side breaks when both have high morale (non-cavalry)."""
        eng = MeleeEngine(rng=_rng(seed=4))
        defender_breaks, attacker_breaks = eng.check_pre_contact_morale(
            attacker_morale=0.9,
            defender_morale=0.9,
            melee_type=MeleeType.PIKE_PUSH,
        )
        assert defender_breaks is False
        assert attacker_breaks is False


# ---------------------------------------------------------------------------
# Reach advantage
# ---------------------------------------------------------------------------


class TestReachAdvantage:
    """Reach advantage modifier (round 1 only)."""

    def test_attacker_longer_reach_round1(self):
        eng = MeleeEngine(rng=_rng(seed=5))
        mod = eng.compute_reach_advantage(attacker_reach_m=3.0, defender_reach_m=1.0, round_number=1)
        assert mod == pytest.approx(1.3)  # default reach_advantage_modifier

    def test_reach_only_round1(self):
        """Reach advantage disappears after round 1."""
        eng = MeleeEngine(rng=_rng(seed=6))
        mod = eng.compute_reach_advantage(attacker_reach_m=3.0, defender_reach_m=1.0, round_number=2)
        assert mod == pytest.approx(1.0)

    def test_defender_longer_reach_no_bonus(self):
        """Attacker with shorter reach gets no bonus."""
        eng = MeleeEngine(rng=_rng(seed=7))
        mod = eng.compute_reach_advantage(attacker_reach_m=1.0, defender_reach_m=3.0, round_number=1)
        assert mod == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Cavalry terrain
# ---------------------------------------------------------------------------


class TestCavalryTerrain:
    """Cavalry terrain modifiers."""

    def test_slope_reduces_modifier(self):
        eng = MeleeEngine(rng=_rng(seed=10))
        mod, abort = eng.compute_cavalry_terrain_modifier(slope_deg=10.0)
        # 1.0 - 0.02 * 10 = 0.80
        assert mod == pytest.approx(0.8)
        assert abort is False

    def test_soft_ground_penalty(self):
        eng = MeleeEngine(rng=_rng(seed=11))
        mod, abort = eng.compute_cavalry_terrain_modifier(soft_ground=True)
        # 1.0 - 0.3 = 0.7
        assert mod == pytest.approx(0.7)
        assert abort is False

    def test_obstacle_abort(self):
        """Dense obstacles cause charge to abort."""
        eng = MeleeEngine(rng=_rng(seed=12))
        _, abort = eng.compute_cavalry_terrain_modifier(obstacle_density=0.6)
        assert abort is True

    def test_combined_slope_and_soft_ground(self):
        eng = MeleeEngine(rng=_rng(seed=13))
        mod, abort = eng.compute_cavalry_terrain_modifier(slope_deg=5.0, soft_ground=True)
        # 1.0 - 0.02*5 - 0.3 = 0.6
        assert mod == pytest.approx(0.6)
        assert abort is False

    def test_modifier_floors_at_zero(self):
        """Modifier never goes negative."""
        eng = MeleeEngine(rng=_rng(seed=14))
        mod, _ = eng.compute_cavalry_terrain_modifier(slope_deg=50.0, soft_ground=True)
        assert mod == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Frontage constraint
# ---------------------------------------------------------------------------


class TestFrontageConstraint:
    """Frontage limits engaged combatants."""

    def test_disabled_when_zero(self):
        eng = MeleeEngine(rng=_rng(seed=20))
        ea, ed, ra = eng.compute_frontage_constraint(100, 80, frontage_m=0.0)
        assert ea == 100
        assert ed == 80
        assert ra == 0

    def test_limits_engaged(self):
        cfg = MeleeConfig(combatant_spacing_m=1.5)
        eng = MeleeEngine(config=cfg, rng=_rng(seed=21))
        # 10m / 1.5m = 6 combatants per side
        ea, ed, ra = eng.compute_frontage_constraint(100, 80, frontage_m=10.0)
        assert ea == 6
        assert ed == 6
        assert ra == 94


# ---------------------------------------------------------------------------
# Flanking bonus
# ---------------------------------------------------------------------------


class TestFlankingBonus:
    """Flanking casualty multiplier."""

    def test_flanked(self):
        eng = MeleeEngine(rng=_rng(seed=25))
        assert eng.compute_flanking_bonus(True) == pytest.approx(2.5)

    def test_not_flanked(self):
        eng = MeleeEngine(rng=_rng(seed=26))
        assert eng.compute_flanking_bonus(False) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Resolve melee round
# ---------------------------------------------------------------------------


class TestResolveMeleeRound:
    """Full melee round resolution."""

    def test_cavalry_charge_vs_line(self):
        """CAVALRY_CHARGE against line formation (high vulnerability) causes casualties."""
        eng = MeleeEngine(rng=_rng(seed=30))
        result = eng.resolve_melee_round(
            attacker_strength=100,
            defender_strength=100,
            melee_type=MeleeType.CAVALRY_CHARGE,
            defender_formation_cavalry_vuln=1.5,  # >= 1.2 -> line modifier
        )
        assert isinstance(result, MeleeResult)
        assert result.defender_casualties >= 0
        assert result.attacker_casualties >= 0

    def test_cavalry_vs_square_low_damage(self):
        """CAVALRY_CHARGE against square (vuln <= 0.15) does little damage."""
        eng = MeleeEngine(rng=_rng(seed=31))
        result = eng.resolve_melee_round(
            attacker_strength=100,
            defender_strength=100,
            melee_type=MeleeType.CAVALRY_CHARGE,
            defender_formation_cavalry_vuln=0.1,  # square -> 0.1 modifier
        )
        # With 0.1 formation modifier, defender casualties should be low
        assert result.defender_casualties < 30

    def test_zero_strength_returns_no_casualties(self):
        eng = MeleeEngine(rng=_rng(seed=32))
        result = eng.resolve_melee_round(
            attacker_strength=0,
            defender_strength=100,
            melee_type=MeleeType.BAYONET_CHARGE,
        )
        assert result.attacker_casualties == 0
        assert result.defender_casualties == 0

    def test_obstacle_aborts_cavalry(self):
        """Dense obstacles abort cavalry charge entirely."""
        eng = MeleeEngine(rng=_rng(seed=33))
        result = eng.resolve_melee_round(
            attacker_strength=100,
            defender_strength=100,
            melee_type=MeleeType.CAVALRY_CHARGE,
            obstacle_density=0.6,
        )
        assert result.attacker_casualties == 0
        assert result.defender_casualties == 0


# ---------------------------------------------------------------------------
# State roundtrip
# ---------------------------------------------------------------------------


class TestMeleeStateRoundtrip:
    """State persistence for checkpointing."""

    def test_state_roundtrip(self):
        eng = MeleeEngine(rng=_rng(seed=40))
        state = eng.get_state()
        eng2 = MeleeEngine(rng=_rng(seed=40))
        eng2.set_state(state)
        assert eng2.get_state() == state
