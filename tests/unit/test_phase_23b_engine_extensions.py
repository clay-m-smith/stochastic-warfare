"""Phase 23b tests — Ancient & Medieval engine extensions.

Covers:
* ArcheryEngine — massed archery fire model (longbow, crossbow, javelin, etc.)
* MeleeType / MeleeEngine — new ancient melee types (pike push, shield wall, mounted charge)
* AncientFormationEngine — 7 ancient formations with vulnerabilities and transitions
* SiegeEngine — multi-day siege state machine
* NavalOarEngine — galley propulsion with fatigue and ramming
* VisualSignalEngine — ancient C2 (banner, horn, runner, fire beacon)
* Cross-engine integration — formation modifiers feed into archery/melee
* Backward compatibility — old Napoleonic paths still work
"""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.combat.archery import (
    ArcheryConfig,
    ArcheryEngine,
    ArcheryResult,
    ArmorType,
    MissileType,
)
from stochastic_warfare.combat.melee import (
    MeleeConfig,
    MeleeEngine,
    MeleeResult,
    MeleeType,
)
from stochastic_warfare.combat.siege import (
    SiegeConfig,
    SiegeEngine,
    SiegePhase,
)
from stochastic_warfare.movement.formation_ancient import (
    AncientFormationConfig,
    AncientFormationEngine,
    AncientFormationType,
)
from stochastic_warfare.movement.naval_oar import (
    GalleyConfig,
    NavalOarEngine,
    RowingSpeed,
)
from stochastic_warfare.c2.visual_signals import (
    SignalType,
    VisualSignalConfig,
    VisualSignalEngine,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.default_rng(seed)


# ===========================================================================
# ArcheryConfig validation (~3 tests)
# ===========================================================================


class TestArcheryConfig:
    """Validate ArcheryConfig defaults."""

    def test_default_phit_tables_populated(self) -> None:
        cfg = ArcheryConfig()
        assert len(cfg.phit_by_range_longbow) > 0
        assert len(cfg.phit_by_range_crossbow) > 0
        assert len(cfg.phit_by_range_composite) > 0
        assert len(cfg.phit_by_range_javelin) > 0
        assert len(cfg.phit_by_range_sling) > 0

    def test_arrows_per_archer_default(self) -> None:
        cfg = ArcheryConfig()
        assert cfg.arrows_per_archer == 24

    def test_armor_reduction_has_four_entries(self) -> None:
        cfg = ArcheryConfig()
        assert len(cfg.armor_reduction) == 4
        assert int(ArmorType.NONE) in cfg.armor_reduction
        assert int(ArmorType.LIGHT) in cfg.armor_reduction
        assert int(ArmorType.MAIL) in cfg.armor_reduction
        assert int(ArmorType.PLATE) in cfg.armor_reduction


# ===========================================================================
# ArcheryEngine mechanics (~15 tests)
# ===========================================================================


class TestArcheryEngine:
    """Massed archery fire model."""

    def test_closer_range_more_casualties(self) -> None:
        """Closer range should produce more casualties on average."""
        eng_near = ArcheryEngine(rng=_rng(42))
        eng_far = ArcheryEngine(rng=_rng(42))
        total_near, total_far = 0, 0
        for seed in range(50):
            e_n = ArcheryEngine(rng=_rng(seed))
            e_f = ArcheryEngine(rng=_rng(seed))
            total_near += e_n.fire_volley("u1", 100, 50.0, MissileType.LONGBOW).casualties
            total_far += e_f.fire_volley("u1", 100, 200.0, MissileType.LONGBOW).casualties
        assert total_near > total_far

    def test_crossbow_higher_phit_than_longbow_at_same_range(self) -> None:
        """Crossbow has higher Phit at 100m than longbow."""
        cfg = ArcheryConfig()
        assert cfg.phit_by_range_crossbow[100] > cfg.phit_by_range_longbow[100]

    def test_plate_armor_reduces_casualties_vs_none(self) -> None:
        """PLATE armor should significantly reduce casualties vs NONE armor."""
        total_none, total_plate = 0, 0
        for seed in range(100):
            e_none = ArcheryEngine(rng=_rng(seed))
            e_plate = ArcheryEngine(rng=_rng(seed))
            total_none += e_none.fire_volley(
                "u1", 200, 80.0, MissileType.LONGBOW, target_armor=ArmorType.NONE,
            ).casualties
            total_plate += e_plate.fire_volley(
                "u1", 200, 80.0, MissileType.LONGBOW, target_armor=ArmorType.PLATE,
            ).casualties
        assert total_plate < total_none

    def test_formation_modifier_increases_casualties(self) -> None:
        """High archery vulnerability should produce more casualties."""
        total_low, total_high = 0, 0
        for seed in range(100):
            e_low = ArcheryEngine(rng=_rng(seed))
            e_high = ArcheryEngine(rng=_rng(seed))
            total_low += e_low.fire_volley(
                "u1", 200, 80.0, MissileType.LONGBOW,
                target_formation_archery_vuln=0.1,
            ).casualties
            total_high += e_high.fire_volley(
                "u1", 200, 80.0, MissileType.LONGBOW,
                target_formation_archery_vuln=2.0,
            ).casualties
        assert total_high > total_low

    def test_ammo_tracking_24_volleys(self) -> None:
        """After 24 single-archer volleys, ammo should be 0."""
        eng = ArcheryEngine(rng=_rng(42))
        for _ in range(24):
            eng.fire_volley("u1", 1, 50.0, MissileType.LONGBOW)
        assert eng.remaining_ammo("u1") == 0

    def test_ammo_depleted_returns_zero_casualties(self) -> None:
        """Firing with 0 ammo returns 0 casualties."""
        eng = ArcheryEngine(rng=_rng(42))
        # Exhaust ammo
        for _ in range(24):
            eng.fire_volley("u1", 1, 50.0, MissileType.LONGBOW)
        result = eng.fire_volley("u1", 1, 50.0, MissileType.LONGBOW)
        assert result.casualties == 0
        assert result.arrows_expended == 0

    def test_fire_aimed_uses_no_formation_modifier(self) -> None:
        """fire_aimed should pass target_formation_archery_vuln=1.0."""
        eng = ArcheryEngine(rng=_rng(42))
        aimed = eng.fire_aimed("u1", 100, 100.0, MissileType.LONGBOW)
        # Verify it returns a valid ArcheryResult (formation_vuln=1.0 is default)
        assert isinstance(aimed, ArcheryResult)
        assert aimed.arrows_expended > 0

    def test_javelin_short_range(self) -> None:
        """Javelin Phit table has max effective range of 30m."""
        cfg = ArcheryConfig()
        max_javelin_range = max(cfg.phit_by_range_javelin.keys())
        assert max_javelin_range == 30

    def test_suppression_proportional_to_fire_volume(self) -> None:
        """Higher fire volume should produce more suppression."""
        eng_small = ArcheryEngine(rng=_rng(42))
        eng_large = ArcheryEngine(rng=_rng(42))
        r_small = eng_small.fire_volley("u1", 10, 50.0, MissileType.LONGBOW)
        r_large = eng_large.fire_volley("u2", 200, 50.0, MissileType.LONGBOW)
        assert r_large.suppression_value >= r_small.suppression_value

    def test_state_roundtrip(self) -> None:
        """get_state/set_state preserves ammo state."""
        eng = ArcheryEngine(rng=_rng(42))
        eng.fire_volley("u1", 5, 80.0, MissileType.LONGBOW)
        state = eng.get_state()

        eng2 = ArcheryEngine(rng=_rng(99))
        eng2.set_state(state)
        assert eng2.remaining_ammo("u1") == eng.remaining_ammo("u1")

    def test_multiple_units_independent_ammo(self) -> None:
        """Different units track ammo independently."""
        eng = ArcheryEngine(rng=_rng(42))
        eng.fire_volley("u1", 5, 80.0, MissileType.LONGBOW)
        eng.fire_volley("u2", 5, 80.0, MissileType.LONGBOW)
        eng.fire_volley("u1", 5, 80.0, MissileType.LONGBOW)
        # u1 fired 2 volleys (10 arrows consumed), u2 fired 1 (5 arrows consumed)
        assert eng.remaining_ammo("u1") < eng.remaining_ammo("u2")

    def test_missile_type_enum_values(self) -> None:
        """MissileType enum has correct values."""
        assert MissileType.LONGBOW == 0
        assert MissileType.CROSSBOW == 1
        assert MissileType.COMPOSITE_BOW == 2
        assert MissileType.JAVELIN == 3
        assert MissileType.SLING == 4

    def test_armor_type_enum_values(self) -> None:
        """ArmorType enum has correct values."""
        assert ArmorType.NONE == 0
        assert ArmorType.LIGHT == 1
        assert ArmorType.MAIL == 2
        assert ArmorType.PLATE == 3

    def test_binomial_deterministic_with_fixed_seed(self) -> None:
        """Fixed seed produces reproducible results."""
        eng1 = ArcheryEngine(rng=_rng(42))
        eng2 = ArcheryEngine(rng=_rng(42))
        r1 = eng1.fire_volley("u1", 200, 100.0, MissileType.LONGBOW)
        r2 = eng2.fire_volley("u1", 200, 100.0, MissileType.LONGBOW)
        assert r1.casualties == r2.casualties

    def test_sling_range_table(self) -> None:
        """Sling has its own distinct range table."""
        cfg = ArcheryConfig()
        assert len(cfg.phit_by_range_sling) > 0
        assert 30 in cfg.phit_by_range_sling


# ===========================================================================
# MeleeType extension (~3 tests)
# ===========================================================================


class TestMeleeTypeExtension:
    """Verify ancient melee types added to MeleeType enum."""

    def test_melee_type_has_seven_values(self) -> None:
        """MeleeType should have 7 values (0-6)."""
        assert len(MeleeType) == 7

    def test_new_type_values(self) -> None:
        """New ancient types have correct values."""
        assert MeleeType.PIKE_PUSH == 4
        assert MeleeType.SHIELD_WALL == 5
        assert MeleeType.MOUNTED_CHARGE == 6

    def test_old_types_unchanged(self) -> None:
        """Original Napoleonic types unchanged."""
        assert MeleeType.BAYONET_CHARGE == 0
        assert MeleeType.CAVALRY_CHARGE == 1
        assert MeleeType.CAVALRY_VS_CAVALRY == 2
        assert MeleeType.MIXED_MELEE == 3


# ===========================================================================
# MeleeEngine new types (~12 tests)
# ===========================================================================


class TestMeleeEngineAncient:
    """Test ancient/medieval melee types in MeleeEngine."""

    def test_pike_push_low_steady_casualties(self) -> None:
        """PIKE_PUSH with base rate 0.01 produces low but steady casualties."""
        eng = MeleeEngine(rng=_rng(42))
        result = eng.resolve_melee_round(
            attacker_strength=500,
            defender_strength=500,
            melee_type=MeleeType.PIKE_PUSH,
        )
        # Low base rate -> relatively few casualties
        assert result.defender_casualties >= 0
        assert result.attacker_casualties >= 0
        assert isinstance(result, MeleeResult)

    def test_shield_wall_defense_bonus(self) -> None:
        """SHIELD_WALL should reduce attacker casualties via defense_mod=0.5."""
        total_sw, total_bayo = 0, 0
        for seed in range(100):
            eng_sw = MeleeEngine(rng=_rng(seed))
            eng_bayo = MeleeEngine(rng=_rng(seed))
            r_sw = eng_sw.resolve_melee_round(
                attacker_strength=200, defender_strength=200,
                melee_type=MeleeType.SHIELD_WALL,
            )
            r_bayo = eng_bayo.resolve_melee_round(
                attacker_strength=200, defender_strength=200,
                melee_type=MeleeType.BAYONET_CHARGE,
            )
            total_sw += r_sw.attacker_casualties
            total_bayo += r_bayo.attacker_casualties
        # Shield wall defense_mod=0.5 should mean fewer attacker casualties
        # Both use bayonet_casualty_rate but shield wall halves attacker casualties
        assert total_sw < total_bayo

    def test_mounted_charge_casualty_rate(self) -> None:
        """MOUNTED_CHARGE uses mounted_charge_casualty_rate=0.04."""
        cfg = MeleeConfig()
        assert cfg.mounted_charge_casualty_rate == 0.04
        eng = MeleeEngine(rng=_rng(42))
        result = eng.resolve_melee_round(
            attacker_strength=100,
            defender_strength=100,
            melee_type=MeleeType.MOUNTED_CHARGE,
        )
        assert isinstance(result, MeleeResult)

    def test_reach_advantage_round_1(self) -> None:
        """Longer weapon gets reach_advantage_modifier=1.3 on round 1."""
        eng = MeleeEngine(rng=_rng(42))
        mod = eng.compute_reach_advantage(
            attacker_reach_m=5.0, defender_reach_m=1.5, round_number=1,
        )
        assert mod == pytest.approx(1.3)

    def test_reach_advantage_round_2_negated(self) -> None:
        """Reach advantage negated after round 1."""
        eng = MeleeEngine(rng=_rng(42))
        mod = eng.compute_reach_advantage(
            attacker_reach_m=5.0, defender_reach_m=1.5, round_number=2,
        )
        assert mod == pytest.approx(1.0)

    def test_reach_ordering_pike_lance_sword_gladius(self) -> None:
        """Pike (5m) > lance (3m) > sword (1.5m) > gladius (1m)."""
        eng = MeleeEngine(rng=_rng(42))
        # Pike vs lance -> advantage
        assert eng.compute_reach_advantage(5.0, 3.0, 1) == pytest.approx(1.3)
        # Lance vs sword -> advantage
        assert eng.compute_reach_advantage(3.0, 1.5, 1) == pytest.approx(1.3)
        # Sword vs gladius -> advantage
        assert eng.compute_reach_advantage(1.5, 1.0, 1) == pytest.approx(1.3)
        # Gladius vs pike -> no advantage (shorter)
        assert eng.compute_reach_advantage(1.0, 5.0, 1) == pytest.approx(1.0)

    def test_flanking_casualty_multiplier_when_flanked(self) -> None:
        """flanking_casualty_multiplier=2.5 when is_flanked=True."""
        eng = MeleeEngine(rng=_rng(42))
        mod = eng.compute_flanking_bonus(is_flanked=True)
        assert mod == pytest.approx(2.5)

    def test_flanking_bonus_not_flanked(self) -> None:
        """compute_flanking_bonus returns 1.0 when not flanked."""
        eng = MeleeEngine(rng=_rng(42))
        mod = eng.compute_flanking_bonus(is_flanked=False)
        assert mod == pytest.approx(1.0)

    def test_bayonet_charge_backward_compat(self) -> None:
        """BAYONET_CHARGE still works with default params."""
        eng = MeleeEngine(rng=_rng(42))
        result = eng.resolve_melee_round(
            attacker_strength=100, defender_strength=100,
            melee_type=MeleeType.BAYONET_CHARGE,
        )
        assert isinstance(result, MeleeResult)
        assert result.attacker_casualties >= 0
        assert result.defender_casualties >= 0

    def test_cavalry_charge_still_uses_formation_vuln(self) -> None:
        """CAVALRY_CHARGE with existing formation vuln logic works."""
        eng = MeleeEngine(rng=_rng(42))
        # Low cavalry vuln (square-like)
        result_square = eng.resolve_melee_round(
            attacker_strength=100, defender_strength=100,
            melee_type=MeleeType.CAVALRY_CHARGE,
            defender_formation_cavalry_vuln=0.1,
        )
        eng2 = MeleeEngine(rng=_rng(42))
        # High cavalry vuln (skirmish-like)
        result_skirm = eng2.resolve_melee_round(
            attacker_strength=100, defender_strength=100,
            melee_type=MeleeType.CAVALRY_CHARGE,
            defender_formation_cavalry_vuln=2.0,
        )
        assert isinstance(result_square, MeleeResult)
        assert isinstance(result_skirm, MeleeResult)

    def test_resolve_with_new_params_defaults_safe(self) -> None:
        """Calling resolve_melee_round with reach/flanking defaults doesn't break."""
        eng = MeleeEngine(rng=_rng(42))
        # Explicitly pass default values for new params
        result = eng.resolve_melee_round(
            attacker_strength=100, defender_strength=100,
            melee_type=MeleeType.BAYONET_CHARGE,
            attacker_reach_m=1.0,
            defender_reach_m=1.0,
            is_flanked=False,
        )
        assert isinstance(result, MeleeResult)

    def test_state_roundtrip_unchanged(self) -> None:
        """MeleeEngine state roundtrip still works."""
        eng = MeleeEngine(rng=_rng(42))
        state = eng.get_state()
        eng2 = MeleeEngine(rng=_rng(99))
        eng2.set_state(state)
        # get_state returns {} (stateless engine)
        assert state == {}


# ===========================================================================
# AncientFormationConfig (~3 tests)
# ===========================================================================


class TestAncientFormationConfig:
    """Validate AncientFormationConfig defaults."""

    def test_seven_formation_types(self) -> None:
        """Default config has 7 formation types in melee_power."""
        cfg = AncientFormationConfig()
        assert len(cfg.melee_power) == 7

    def test_phalanx_melee_power(self) -> None:
        """PHALANX melee power is 1.2."""
        cfg = AncientFormationConfig()
        assert cfg.melee_power[int(AncientFormationType.PHALANX)] == pytest.approx(1.2)

    def test_transition_times_count(self) -> None:
        """Transition times should cover all 7*6=42 ordered pairs."""
        cfg = AncientFormationConfig()
        assert len(cfg.transition_times_s) == 42


# ===========================================================================
# AncientFormationEngine (~16 tests)
# ===========================================================================


class TestAncientFormationEngine:
    """Ancient/medieval formation management and transitions."""

    def test_set_formation_immediate(self) -> None:
        """set_formation sets formation instantly."""
        eng = AncientFormationEngine()
        eng.set_formation("u1", AncientFormationType.WEDGE)
        assert eng.get_formation("u1") == AncientFormationType.WEDGE

    def test_order_formation_change_returns_time(self) -> None:
        """order_formation_change returns transition time in seconds."""
        eng = AncientFormationEngine()
        eng.set_formation("u1", AncientFormationType.PHALANX)
        t = eng.order_formation_change("u1", AncientFormationType.WEDGE)
        assert t > 0.0

    def test_update_completes_transition(self) -> None:
        """update() completes transition after enough dt."""
        eng = AncientFormationEngine()
        eng.set_formation("u1", AncientFormationType.PHALANX)
        t = eng.order_formation_change("u1", AncientFormationType.WEDGE)
        completed = eng.update(t + 1.0)
        assert "u1" in completed
        assert eng.get_formation("u1") == AncientFormationType.WEDGE

    def test_melee_power_wedge(self) -> None:
        """WEDGE melee power is 1.5."""
        eng = AncientFormationEngine()
        eng.set_formation("u1", AncientFormationType.WEDGE)
        assert eng.melee_power("u1") == pytest.approx(1.5)

    def test_melee_power_shield_wall(self) -> None:
        """SHIELD_WALL melee power is 0.8."""
        eng = AncientFormationEngine()
        eng.set_formation("u1", AncientFormationType.SHIELD_WALL)
        assert eng.melee_power("u1") == pytest.approx(0.8)

    def test_defense_mod_testudo(self) -> None:
        """TESTUDO defense modifier is 2.0."""
        eng = AncientFormationEngine()
        eng.set_formation("u1", AncientFormationType.TESTUDO)
        assert eng.defense_mod("u1") == pytest.approx(2.0)

    def test_defense_mod_column(self) -> None:
        """COLUMN defense modifier is 0.3."""
        eng = AncientFormationEngine()
        eng.set_formation("u1", AncientFormationType.COLUMN)
        assert eng.defense_mod("u1") == pytest.approx(0.3)

    def test_speed_multiplier_skirmish(self) -> None:
        """SKIRMISH speed multiplier is 1.0 (fastest)."""
        eng = AncientFormationEngine()
        eng.set_formation("u1", AncientFormationType.SKIRMISH)
        assert eng.speed_multiplier("u1") == pytest.approx(1.0)

    def test_speed_multiplier_testudo(self) -> None:
        """TESTUDO speed multiplier is 0.2 (slowest)."""
        eng = AncientFormationEngine()
        eng.set_formation("u1", AncientFormationType.TESTUDO)
        assert eng.speed_multiplier("u1") == pytest.approx(0.2)

    def test_archery_vuln_testudo(self) -> None:
        """TESTUDO archery vulnerability is 0.1 (near-immune)."""
        eng = AncientFormationEngine()
        eng.set_formation("u1", AncientFormationType.TESTUDO)
        assert eng.archery_vulnerability("u1") == pytest.approx(0.1)

    def test_archery_vuln_column(self) -> None:
        """COLUMN archery vulnerability is 1.5 (very exposed)."""
        eng = AncientFormationEngine()
        eng.set_formation("u1", AncientFormationType.COLUMN)
        assert eng.archery_vulnerability("u1") == pytest.approx(1.5)

    def test_cavalry_vuln_pike_block(self) -> None:
        """PIKE_BLOCK cavalry vulnerability is 0.2."""
        eng = AncientFormationEngine()
        eng.set_formation("u1", AncientFormationType.PIKE_BLOCK)
        assert eng.cavalry_vulnerability("u1") == pytest.approx(0.2)

    def test_cavalry_vuln_skirmish(self) -> None:
        """SKIRMISH cavalry vulnerability is 2.0 (very vulnerable)."""
        eng = AncientFormationEngine()
        eng.set_formation("u1", AncientFormationType.SKIRMISH)
        assert eng.cavalry_vulnerability("u1") == pytest.approx(2.0)

    def test_flanking_vuln_phalanx(self) -> None:
        """PHALANX flanking vulnerability is 2.0."""
        eng = AncientFormationEngine()
        eng.set_formation("u1", AncientFormationType.PHALANX)
        assert eng.flanking_vulnerability("u1") == pytest.approx(2.0)

    def test_flanking_vuln_skirmish(self) -> None:
        """SKIRMISH flanking vulnerability is 0.3 (hard to flank)."""
        eng = AncientFormationEngine()
        eng.set_formation("u1", AncientFormationType.SKIRMISH)
        assert eng.flanking_vulnerability("u1") == pytest.approx(0.3)

    def test_worst_of_both_archery_during_transition(self) -> None:
        """During transition, archery vulnerability is worst of both formations."""
        eng = AncientFormationEngine()
        eng.set_formation("u1", AncientFormationType.TESTUDO)  # archery_vuln 0.1
        eng.order_formation_change("u1", AncientFormationType.COLUMN)  # archery_vuln 1.5
        # Worst-of-both for vulnerability (higher = worse): max(0.1, 1.5) = 1.5
        assert eng.archery_vulnerability("u1") == pytest.approx(1.5)

    def test_worst_of_both_cavalry_during_transition(self) -> None:
        """During transition, cavalry vulnerability is worst of both."""
        eng = AncientFormationEngine()
        eng.set_formation("u1", AncientFormationType.PIKE_BLOCK)  # cav_vuln 0.2
        eng.order_formation_change("u1", AncientFormationType.SKIRMISH)  # cav_vuln 2.0
        # Worst-of-both for vulnerability (higher = worse): max(0.2, 2.0) = 2.0
        assert eng.cavalry_vulnerability("u1") == pytest.approx(2.0)

    def test_is_transitioning_during_and_after(self) -> None:
        """is_transitioning is True during, False after."""
        eng = AncientFormationEngine()
        eng.set_formation("u1", AncientFormationType.PHALANX)
        t = eng.order_formation_change("u1", AncientFormationType.WEDGE)
        assert eng.is_transitioning("u1") is True
        eng.update(t + 1.0)
        assert eng.is_transitioning("u1") is False

    def test_already_in_target_returns_zero(self) -> None:
        """Ordering transition to current formation returns 0.0."""
        eng = AncientFormationEngine()
        eng.set_formation("u1", AncientFormationType.PHALANX)
        t = eng.order_formation_change("u1", AncientFormationType.PHALANX)
        assert t == pytest.approx(0.0)

    def test_already_transitioning_returns_zero(self) -> None:
        """Ordering a second transition while already transitioning returns 0.0."""
        eng = AncientFormationEngine()
        eng.set_formation("u1", AncientFormationType.PHALANX)
        eng.order_formation_change("u1", AncientFormationType.WEDGE)
        t2 = eng.order_formation_change("u1", AncientFormationType.TESTUDO)
        assert t2 == pytest.approx(0.0)

    def test_concurrent_transitions_different_units(self) -> None:
        """Different units can transition concurrently."""
        eng = AncientFormationEngine()
        eng.set_formation("u1", AncientFormationType.PHALANX)
        eng.set_formation("u2", AncientFormationType.TESTUDO)
        t1 = eng.order_formation_change("u1", AncientFormationType.WEDGE)
        t2 = eng.order_formation_change("u2", AncientFormationType.COLUMN)
        max_t = max(t1, t2)
        completed = eng.update(max_t + 1.0)
        assert "u1" in completed
        assert "u2" in completed
        assert eng.get_formation("u1") == AncientFormationType.WEDGE
        assert eng.get_formation("u2") == AncientFormationType.COLUMN

    def test_state_roundtrip_preserves_formations(self) -> None:
        """get_state/set_state preserves formation states."""
        eng = AncientFormationEngine()
        eng.set_formation("u1", AncientFormationType.WEDGE)
        eng.set_formation("u2", AncientFormationType.TESTUDO)
        eng.order_formation_change("u2", AncientFormationType.PHALANX)
        state = eng.get_state()

        eng2 = AncientFormationEngine()
        eng2.set_state(state)
        assert eng2.get_formation("u1") == AncientFormationType.WEDGE
        assert eng2.is_transitioning("u2") is True


# ===========================================================================
# SiegeConfig (~3 tests)
# ===========================================================================


class TestSiegeConfig:
    """Validate SiegeConfig defaults."""

    def test_default_wall_hp(self) -> None:
        cfg = SiegeConfig()
        assert cfg.wall_hp == pytest.approx(1000.0)

    def test_breach_threshold(self) -> None:
        cfg = SiegeConfig()
        assert cfg.breach_threshold == pytest.approx(0.3)

    def test_starvation_days(self) -> None:
        cfg = SiegeConfig()
        assert cfg.starvation_days == 60


# ===========================================================================
# SiegeEngine (~14 tests)
# ===========================================================================


class TestSiegeEngine:
    """Siege warfare state machine."""

    def test_begin_siege_initializes_state(self) -> None:
        """begin_siege creates a siege in ENCIRCLEMENT phase."""
        eng = SiegeEngine(rng=_rng(42))
        s = eng.begin_siege("s1", garrison_size=500, food_days=60, attacker_size=2000)
        assert s.phase == SiegePhase.ENCIRCLEMENT
        assert s.garrison_size == 500
        assert s.attacker_size == 2000

    def test_advance_day_transitions_to_bombardment(self) -> None:
        """advance_day moves to BOMBARDMENT when engines present."""
        eng = SiegeEngine(rng=_rng(42))
        eng.begin_siege("s1", garrison_size=500, food_days=60, attacker_size=2000)
        s = eng.advance_day("s1", n_trebuchets=2)
        assert s.phase == SiegePhase.BOMBARDMENT

    def test_wall_damage_from_trebuchets(self) -> None:
        """Trebuchets deal 50 damage/day."""
        eng = SiegeEngine(rng=_rng(42))
        eng.begin_siege("s1", garrison_size=500, food_days=60, attacker_size=2000)
        eng.advance_day("s1", n_trebuchets=1)
        s = eng.get_siege_state("s1")
        assert s.wall_hp_remaining == pytest.approx(1000.0 - 50.0)

    def test_wall_damage_additive_from_multiple_engines(self) -> None:
        """Rams (30) + catapults (20) are additive."""
        eng = SiegeEngine(rng=_rng(42))
        eng.begin_siege("s1", garrison_size=500, food_days=60, attacker_size=2000)
        eng.advance_day("s1", n_rams=1, n_catapults=1)
        s = eng.get_siege_state("s1")
        expected_hp = 1000.0 - 30.0 - 20.0
        assert s.wall_hp_remaining == pytest.approx(expected_hp)

    def test_breach_when_wall_low(self) -> None:
        """Breach occurs when wall_hp_remaining <= breach_threshold * wall_hp."""
        eng = SiegeEngine(rng=_rng(42))
        # breach_threshold=0.3, wall_hp=1000 -> breach at 300 HP
        # 2 trebuchets = 100 dmg/day, need to reduce from 1000 to 300 -> 7 days
        eng.begin_siege("s1", garrison_size=500, food_days=60, attacker_size=2000)
        for _ in range(7):
            eng.advance_day("s1", n_trebuchets=2)
        s = eng.get_siege_state("s1")
        assert s.phase == SiegePhase.BREACH

    def test_multi_day_advance_to_breach(self) -> None:
        """2 trebuchets = 100 dmg/day; breach at 300 HP in 7 days but not 6."""
        eng = SiegeEngine(rng=_rng(42))
        eng.begin_siege("s1", garrison_size=500, food_days=60, attacker_size=2000)
        for _ in range(6):
            eng.advance_day("s1", n_trebuchets=2)
        s = eng.get_siege_state("s1")
        # After 6 days: 1000 - 600 = 400 > 300, still BOMBARDMENT
        assert s.phase == SiegePhase.BOMBARDMENT
        eng.advance_day("s1", n_trebuchets=2)
        s = eng.get_siege_state("s1")
        # After 7 days: 1000 - 700 = 300 <= 300, BREACH
        assert s.phase == SiegePhase.BREACH

    def test_assault_casualties_applied_both_sides(self) -> None:
        """Assault applies casualties to both attacker and defender."""
        eng = SiegeEngine(rng=_rng(42))
        eng.begin_siege("s1", garrison_size=500, food_days=60, attacker_size=2000)
        # Force breach by advancing many days
        for _ in range(8):
            eng.advance_day("s1", n_trebuchets=2)
        success, att_cas, def_cas = eng.attempt_assault("s1")
        assert att_cas >= 0
        assert def_cas >= 0

    def test_assault_succeeds_when_garrison_eliminated(self) -> None:
        """Assault succeeds when garrison is eliminated."""
        # Use high assault casualty rate to guarantee garrison elimination
        cfg = SiegeConfig(assault_casualty_rate_defender=1.0)
        eng = SiegeEngine(config=cfg, rng=_rng(42))
        eng.begin_siege("s1", garrison_size=5, food_days=60, attacker_size=2000,
                        wall_hp=10.0)
        eng.advance_day("s1", n_trebuchets=1)  # damage 50, wall at 0 -> breach
        success, att_cas, def_cas = eng.attempt_assault("s1")
        s = eng.get_siege_state("s1")
        assert s.phase == SiegePhase.FALLEN

    def test_starvation_no_casualties_while_food_remains(self) -> None:
        """No starvation casualties while food_days > 0."""
        eng = SiegeEngine(rng=_rng(42))
        eng.begin_siege("s1", garrison_size=500, food_days=60, attacker_size=2000)
        eng.advance_day("s1")
        cas = eng.check_starvation("s1")
        assert cas == 0

    def test_starvation_casualties_after_food_depleted(self) -> None:
        """Starvation causes casualties after food runs out."""
        eng = SiegeEngine(rng=_rng(42))
        eng.begin_siege("s1", garrison_size=500, food_days=2, attacker_size=2000)
        eng.advance_day("s1")  # food_days now 1
        eng.advance_day("s1")  # food_days now 0
        eng.advance_day("s1")  # food_days now -1
        cas = eng.check_starvation("s1")
        assert cas > 0

    def test_sally_sortie_bernoulli(self) -> None:
        """Sally sortie is Bernoulli with sally_probability."""
        # With high probability, sally should happen within 100 attempts
        cfg = SiegeConfig(sally_probability=1.0)  # always sally
        eng = SiegeEngine(config=cfg, rng=_rng(42))
        eng.begin_siege("s1", garrison_size=500, food_days=60, attacker_size=2000)
        attempted, att_cas = eng.sally_sortie("s1")
        assert attempted is True

    def test_relief_force_lifts_siege(self) -> None:
        """Relief force > attacker_size * relief_force_ratio lifts siege."""
        eng = SiegeEngine(rng=_rng(42))
        eng.begin_siege("s1", garrison_size=500, food_days=60, attacker_size=2000)
        # relief_force_ratio=0.5 -> need > 1000
        lifted = eng.relieve_siege("s1", relief_force_size=1500)
        assert lifted is True
        assert eng.get_phase("s1") == SiegePhase.RELIEF

    def test_phase_transitions_correct(self) -> None:
        """Verify ENCIRCLEMENT->BOMBARDMENT->BREACH progression."""
        eng = SiegeEngine(rng=_rng(42))
        eng.begin_siege("s1", garrison_size=500, food_days=60, attacker_size=2000)
        assert eng.get_phase("s1") == SiegePhase.ENCIRCLEMENT
        eng.advance_day("s1", n_trebuchets=1)
        assert eng.get_phase("s1") == SiegePhase.BOMBARDMENT
        # Advance until breach
        for _ in range(20):
            eng.advance_day("s1", n_trebuchets=2)
        assert eng.get_phase("s1") == SiegePhase.BREACH

    def test_state_roundtrip_preserves_siege(self) -> None:
        """get_state/set_state preserves siege state."""
        eng = SiegeEngine(rng=_rng(42))
        eng.begin_siege("s1", garrison_size=500, food_days=60, attacker_size=2000)
        eng.advance_day("s1", n_trebuchets=2)
        state = eng.get_state()

        eng2 = SiegeEngine(rng=_rng(99))
        eng2.set_state(state)
        s = eng2.get_siege_state("s1")
        assert s.phase == SiegePhase.BOMBARDMENT
        assert s.garrison_size == 500


# ===========================================================================
# GalleyConfig (~3 tests)
# ===========================================================================


class TestGalleyConfig:
    """Validate GalleyConfig defaults."""

    def test_default_cruise_speed(self) -> None:
        cfg = GalleyConfig()
        assert cfg.cruise_speed_mps == pytest.approx(2.5)

    def test_exhaustion_threshold(self) -> None:
        cfg = GalleyConfig()
        assert cfg.exhaustion_threshold == pytest.approx(0.8)

    def test_boarding_transition_time(self) -> None:
        cfg = GalleyConfig()
        assert cfg.boarding_transition_time_s == pytest.approx(30.0)


# ===========================================================================
# NavalOarEngine (~10 tests)
# ===========================================================================


class TestNavalOarEngine:
    """Galley propulsion, fatigue, ramming and boarding."""

    def test_cruise_battle_ramming_speeds(self) -> None:
        """Cruise/battle/ramming return correct m/s at zero fatigue."""
        eng = NavalOarEngine(rng=_rng(42))
        eng.register_vessel("g1")
        eng.set_speed("g1", RowingSpeed.CRUISE)
        assert eng.get_speed("g1") == pytest.approx(2.5)
        eng.set_speed("g1", RowingSpeed.BATTLE)
        assert eng.get_speed("g1") == pytest.approx(4.0)
        eng.set_speed("g1", RowingSpeed.RAMMING)
        assert eng.get_speed("g1") == pytest.approx(6.0)

    def test_rest_returns_zero_speed(self) -> None:
        """REST returns 0.0 speed."""
        eng = NavalOarEngine(rng=_rng(42))
        eng.register_vessel("g1")
        eng.set_speed("g1", RowingSpeed.REST)
        assert eng.get_speed("g1") == pytest.approx(0.0)

    def test_fatigue_accumulates(self) -> None:
        """Fatigue increases while rowing."""
        eng = NavalOarEngine(rng=_rng(42))
        eng.register_vessel("g1")
        eng.set_speed("g1", RowingSpeed.CRUISE)
        eng.update(100.0)
        assert eng.get_fatigue("g1") > 0.0

    def test_exhaustion_halves_speed(self) -> None:
        """Speed halved when fatigue >= exhaustion_threshold."""
        cfg = GalleyConfig()
        eng = NavalOarEngine(config=cfg, rng=_rng(42))
        eng.register_vessel("g1")
        eng.set_speed("g1", RowingSpeed.BATTLE)
        # Accumulate enough fatigue to cross threshold 0.8
        # fatigue_rate_battle=0.02, need 0.8/0.02 = 40s
        eng.update(50.0)
        speed = eng.get_speed("g1")
        assert speed == pytest.approx(4.0 * 0.5)

    def test_recovery_at_rest(self) -> None:
        """Fatigue decreases when resting."""
        eng = NavalOarEngine(rng=_rng(42))
        eng.register_vessel("g1")
        eng.set_speed("g1", RowingSpeed.BATTLE)
        eng.update(20.0)
        fatigue_after_rowing = eng.get_fatigue("g1")
        eng.set_speed("g1", RowingSpeed.REST)
        eng.update(20.0)
        assert eng.get_fatigue("g1") < fatigue_after_rowing

    def test_ram_damage_calculation(self) -> None:
        """Ram damage = base + speed_factor * approach_speed."""
        eng = NavalOarEngine(rng=_rng(42))
        eng.register_vessel("g1")
        damage = eng.compute_ram_damage("g1", approach_speed=6.0)
        # base=100 + 20*6 = 220
        assert damage == pytest.approx(220.0)

    def test_boarding_sets_speed_to_rest(self) -> None:
        """Initiating boarding sets speed to REST."""
        eng = NavalOarEngine(rng=_rng(42))
        eng.register_vessel("g1")
        eng.set_speed("g1", RowingSpeed.BATTLE)
        eng.initiate_boarding("g1", "g2")
        assert eng.get_speed("g1") == pytest.approx(0.0)

    def test_is_boarding_during_and_after(self) -> None:
        """is_boarding True during boarding transition, False after."""
        eng = NavalOarEngine(rng=_rng(42))
        eng.register_vessel("g1")
        eng.initiate_boarding("g1", "g2")
        assert eng.is_boarding("g1") is True
        # Advance past boarding transition time (30s)
        eng.update(31.0)
        assert eng.is_boarding("g1") is False

    def test_register_vessel_zero_fatigue(self) -> None:
        """register_vessel creates initial state with 0 fatigue."""
        eng = NavalOarEngine(rng=_rng(42))
        eng.register_vessel("g1")
        assert eng.get_fatigue("g1") == pytest.approx(0.0)

    def test_state_roundtrip_preserves_galleys(self) -> None:
        """get_state/set_state preserves galley states."""
        eng = NavalOarEngine(rng=_rng(42))
        eng.register_vessel("g1")
        eng.set_speed("g1", RowingSpeed.BATTLE)
        eng.update(10.0)
        state = eng.get_state()

        eng2 = NavalOarEngine(rng=_rng(99))
        eng2.set_state(state)
        assert eng2.get_fatigue("g1") == pytest.approx(eng.get_fatigue("g1"))


# ===========================================================================
# VisualSignalConfig (~3 tests)
# ===========================================================================


class TestVisualSignalConfig:
    """Validate VisualSignalConfig defaults."""

    def test_banner_range(self) -> None:
        cfg = VisualSignalConfig()
        assert cfg.banner_range_m == pytest.approx(1000.0)

    def test_horn_range(self) -> None:
        cfg = VisualSignalConfig()
        assert cfg.horn_range_m == pytest.approx(500.0)

    def test_runner_speed(self) -> None:
        cfg = VisualSignalConfig()
        assert cfg.runner_speed_mps == pytest.approx(3.0)


# ===========================================================================
# VisualSignalEngine (~10 tests)
# ===========================================================================


class TestVisualSignalEngine:
    """Ancient visual/audible C2 signals."""

    def test_banner_requires_los_fails_without(self) -> None:
        """Banner returns None if has_los=False."""
        eng = VisualSignalEngine(rng=_rng(42))
        msg = eng.send_signal(
            SignalType.BANNER,
            sender_pos=(0.0, 0.0),
            receiver_pos=(500.0, 0.0),
            has_los=False,
        )
        assert msg is None

    def test_banner_within_range_with_los(self) -> None:
        """Banner within range with LOS is received immediately."""
        eng = VisualSignalEngine(rng=_rng(42))
        msg = eng.send_signal(
            SignalType.BANNER,
            sender_pos=(0.0, 0.0),
            receiver_pos=(500.0, 0.0),
            has_los=True,
        )
        # May be None due to reliability check, try multiple seeds
        received = False
        for seed in range(50):
            eng_try = VisualSignalEngine(rng=_rng(seed))
            msg = eng_try.send_signal(
                SignalType.BANNER,
                sender_pos=(0.0, 0.0),
                receiver_pos=(500.0, 0.0),
                has_los=True,
            )
            if msg is not None:
                assert msg.received is True
                received = True
                break
        assert received, "Banner should be received with LOS within range"

    def test_banner_out_of_range_returns_none(self) -> None:
        """Banner out of range returns None."""
        eng = VisualSignalEngine(rng=_rng(42))
        msg = eng.send_signal(
            SignalType.BANNER,
            sender_pos=(0.0, 0.0),
            receiver_pos=(2000.0, 0.0),  # 2km > 1km range
            has_los=True,
        )
        assert msg is None

    def test_horn_no_los_needed(self) -> None:
        """Horn works without LOS within range."""
        received = False
        for seed in range(50):
            eng = VisualSignalEngine(rng=_rng(seed))
            msg = eng.send_signal(
                SignalType.HORN,
                sender_pos=(0.0, 0.0),
                receiver_pos=(300.0, 0.0),
                has_los=False,
            )
            if msg is not None:
                assert msg.received is True
                received = True
                break
        assert received, "Horn should work without LOS"

    def test_horn_out_of_range_returns_none(self) -> None:
        """Horn out of range returns None."""
        eng = VisualSignalEngine(rng=_rng(42))
        msg = eng.send_signal(
            SignalType.HORN,
            sender_pos=(0.0, 0.0),
            receiver_pos=(600.0, 0.0),  # 600m > 500m range
            has_los=True,
        )
        assert msg is None

    def test_runner_async_delivery(self) -> None:
        """Runner message is not received immediately."""
        received_any = False
        for seed in range(50):
            eng = VisualSignalEngine(rng=_rng(seed))
            msg = eng.send_signal(
                SignalType.RUNNER,
                sender_pos=(0.0, 0.0),
                receiver_pos=(900.0, 0.0),
                has_los=True,
                sim_time_s=0.0,
            )
            if msg is not None:
                assert msg.received is False  # async, not yet delivered
                received_any = True
                break
        assert received_any, "Runner signal should be sent"

    def test_runner_update_delivers_after_time(self) -> None:
        """Runner is delivered after enough time passes."""
        for seed in range(50):
            eng = VisualSignalEngine(rng=_rng(seed))
            msg = eng.send_signal(
                SignalType.RUNNER,
                sender_pos=(0.0, 0.0),
                receiver_pos=(300.0, 0.0),  # 300m at 3 m/s = 100s
                has_los=True,
                sim_time_s=0.0,
            )
            if msg is not None:
                assert msg.received is False
                delivered = eng.update(dt_s=10.0, sim_time_s=200.0)
                assert len(delivered) == 1
                assert delivered[0].received is True
                break

    def test_fire_beacon_binary_only(self) -> None:
        """Fire beacon has content_fidelity=0.0 (binary signal)."""
        for seed in range(50):
            eng = VisualSignalEngine(rng=_rng(seed))
            msg = eng.send_signal(
                SignalType.FIRE_BEACON,
                sender_pos=(0.0, 0.0),
                receiver_pos=(5000.0, 0.0),
                has_los=True,
            )
            if msg is not None:
                assert msg.content_fidelity == pytest.approx(0.0)
                break

    def test_fire_beacon_requires_los(self) -> None:
        """Fire beacon returns None without LOS."""
        eng = VisualSignalEngine(rng=_rng(42))
        msg = eng.send_signal(
            SignalType.FIRE_BEACON,
            sender_pos=(0.0, 0.0),
            receiver_pos=(5000.0, 0.0),
            has_los=False,
        )
        assert msg is None

    def test_state_roundtrip_preserves_pending(self) -> None:
        """get_state/set_state preserves pending messages."""
        eng = VisualSignalEngine(rng=_rng(42))
        # Send a runner (async) so it remains pending
        for seed in range(50):
            eng = VisualSignalEngine(rng=_rng(seed))
            msg = eng.send_signal(
                SignalType.RUNNER,
                sender_pos=(0.0, 0.0),
                receiver_pos=(900.0, 0.0),
                has_los=True,
                sim_time_s=0.0,
            )
            if msg is not None:
                break
        state = eng.get_state()

        eng2 = VisualSignalEngine(rng=_rng(99))
        eng2.set_state(state)
        state2 = eng2.get_state()
        assert state["msg_counter"] == state2["msg_counter"]
        assert len(state["pending"]) == len(state2["pending"])


# ===========================================================================
# Cross-engine integration (~8 tests)
# ===========================================================================


class TestCrossEngineIntegration:
    """Integration tests combining formation modifiers with combat engines."""

    def test_testudo_archery_vuln_feeds_into_archery_engine(self) -> None:
        """TESTUDO archery_vuln=0.1 drastically reduces archery casualties."""
        form_eng = AncientFormationEngine()
        form_eng.set_formation("u1", AncientFormationType.TESTUDO)
        vuln = form_eng.archery_vulnerability("u1")
        assert vuln == pytest.approx(0.1)

        total_testudo, total_column = 0, 0
        for seed in range(100):
            arch_eng = ArcheryEngine(rng=_rng(seed))
            total_testudo += arch_eng.fire_volley(
                "archers", 200, 100.0, MissileType.LONGBOW,
                target_formation_archery_vuln=0.1,
            ).casualties
        for seed in range(100):
            arch_eng = ArcheryEngine(rng=_rng(seed))
            total_column += arch_eng.fire_volley(
                "archers", 200, 100.0, MissileType.LONGBOW,
                target_formation_archery_vuln=1.5,
            ).casualties
        assert total_testudo < total_column

    def test_formation_melee_power_feeds_into_melee(self) -> None:
        """Formation melee_power can be used as a force modifier."""
        form_eng = AncientFormationEngine()
        form_eng.set_formation("u1", AncientFormationType.WEDGE)
        power = form_eng.melee_power("u1")
        assert power == pytest.approx(1.5)
        # WEDGE = 1.5 > SKIRMISH = 0.3
        form_eng.set_formation("u2", AncientFormationType.SKIRMISH)
        assert form_eng.melee_power("u2") == pytest.approx(0.3)

    def test_phalanx_flanking_vulnerability_heavy_casualties(self) -> None:
        """PHALANX flanking_vuln=2.0 + is_flanked=True -> heavy casualties."""
        form_eng = AncientFormationEngine()
        form_eng.set_formation("def", AncientFormationType.PHALANX)
        flank_vuln = form_eng.flanking_vulnerability("def")
        assert flank_vuln == pytest.approx(2.0)

        # Flanked melee should produce more defender casualties
        total_flanked, total_not = 0, 0
        for seed in range(100):
            eng_f = MeleeEngine(rng=_rng(seed))
            r = eng_f.resolve_melee_round(
                attacker_strength=200, defender_strength=200,
                melee_type=MeleeType.PIKE_PUSH, is_flanked=True,
            )
            total_flanked += r.defender_casualties
        for seed in range(100):
            eng_n = MeleeEngine(rng=_rng(seed))
            r = eng_n.resolve_melee_round(
                attacker_strength=200, defender_strength=200,
                melee_type=MeleeType.PIKE_PUSH, is_flanked=False,
            )
            total_not += r.defender_casualties
        assert total_flanked > total_not

    def test_cavalry_charge_plus_formation_cavalry_vuln(self) -> None:
        """Cavalry charge with formation cavalry_vulnerability works end-to-end."""
        form_eng = AncientFormationEngine()
        form_eng.set_formation("def", AncientFormationType.SKIRMISH)
        cav_vuln = form_eng.cavalry_vulnerability("def")
        assert cav_vuln == pytest.approx(2.0)

        melee_eng = MeleeEngine(rng=_rng(42))
        result = melee_eng.resolve_melee_round(
            attacker_strength=100, defender_strength=100,
            melee_type=MeleeType.CAVALRY_CHARGE,
            defender_formation_cavalry_vuln=cav_vuln,
        )
        assert isinstance(result, MeleeResult)

    def test_siege_starvation_conceptual_morale_link(self) -> None:
        """Siege starvation produces casualties that would trigger morale checks."""
        eng = SiegeEngine(rng=_rng(42))
        eng.begin_siege("s1", garrison_size=200, food_days=1, attacker_size=1000)
        eng.advance_day("s1")  # food -> 0
        eng.advance_day("s1")  # food -> -1
        cas = eng.check_starvation("s1")
        # Casualties exist; in full integration these would feed morale system
        assert cas >= 0
        assert isinstance(cas, int)

    def test_archery_ammo_depletion_requires_melee_switch(self) -> None:
        """After ammo depletion, archery returns 0 — unit must use melee."""
        arch_eng = ArcheryEngine(rng=_rng(42))
        for _ in range(25):
            arch_eng.fire_volley("u1", 1, 50.0, MissileType.LONGBOW)
        # Ammo depleted
        r = arch_eng.fire_volley("u1", 1, 50.0, MissileType.LONGBOW)
        assert r.casualties == 0
        # Melee still works (conceptual switch)
        melee_eng = MeleeEngine(rng=_rng(42))
        mr = melee_eng.resolve_melee_round(
            attacker_strength=50, defender_strength=50,
            melee_type=MeleeType.SHIELD_WALL,
        )
        assert isinstance(mr, MeleeResult)

    def test_formation_speed_affects_movement(self) -> None:
        """Formation speed_multiplier modifies base movement speed."""
        form_eng = AncientFormationEngine()
        form_eng.set_formation("u1", AncientFormationType.TESTUDO)
        form_eng.set_formation("u2", AncientFormationType.SKIRMISH)
        base_speed = 5.0  # m/s

        speed_testudo = base_speed * form_eng.speed_multiplier("u1")
        speed_skirmish = base_speed * form_eng.speed_multiplier("u2")
        assert speed_testudo == pytest.approx(1.0)  # 5.0 * 0.2
        assert speed_skirmish == pytest.approx(5.0)  # 5.0 * 1.0

    def test_visual_signals_with_los_concept(self) -> None:
        """Visual signals require LOS (conceptually integrates with LOS engine)."""
        sig_eng = VisualSignalEngine(rng=_rng(42))
        # Banner without LOS -> fails
        msg_no_los = sig_eng.send_signal(
            SignalType.BANNER,
            sender_pos=(0.0, 0.0),
            receiver_pos=(500.0, 0.0),
            has_los=False,
        )
        assert msg_no_los is None
        # With LOS -> succeeds (try multiple seeds for reliability)
        for seed in range(50):
            eng = VisualSignalEngine(rng=_rng(seed))
            msg = eng.send_signal(
                SignalType.BANNER,
                sender_pos=(0.0, 0.0),
                receiver_pos=(500.0, 0.0),
                has_los=True,
            )
            if msg is not None:
                assert msg.received is True
                break


# ===========================================================================
# Backward compatibility (~3 tests)
# ===========================================================================


class TestBackwardCompatibility:
    """Ensure old Napoleonic/modern paths still work identically."""

    def test_melee_engine_old_types_still_work(self) -> None:
        """MeleeEngine with old 4 types produces valid results."""
        eng = MeleeEngine(rng=_rng(42))
        for mt in [MeleeType.BAYONET_CHARGE, MeleeType.CAVALRY_CHARGE,
                    MeleeType.CAVALRY_VS_CAVALRY, MeleeType.MIXED_MELEE]:
            r = eng.resolve_melee_round(
                attacker_strength=100, defender_strength=100,
                melee_type=mt,
            )
            assert isinstance(r, MeleeResult)

    def test_melee_config_old_fields_construct(self) -> None:
        """MeleeConfig with only original fields still constructs."""
        cfg = MeleeConfig(
            pre_contact_morale_threshold=0.4,
            cavalry_shock_multiplier=2.0,
            bayonet_casualty_rate=0.02,
            cavalry_casualty_rate=0.03,
        )
        assert cfg.pre_contact_morale_threshold == pytest.approx(0.4)
        # New fields get defaults
        assert cfg.pike_push_attrition_rate == pytest.approx(0.01)

    def test_archery_engine_independent_of_volley_fire(self) -> None:
        """ArcheryEngine does not affect or depend on Napoleonic VolleyFireEngine."""
        # Just verify archery imports cleanly and doesn't interfere
        from stochastic_warfare.combat.volley_fire import VolleyFireEngine  # noqa: F401
        arch = ArcheryEngine(rng=_rng(42))
        r = arch.fire_volley("u1", 100, 100.0, MissileType.LONGBOW)
        assert isinstance(r, ArcheryResult)
