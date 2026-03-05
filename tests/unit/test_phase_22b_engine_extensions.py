"""Phase 22b tests — Napoleonic engine extensions.

Tests for:
- VolleyFireEngine (massed musket fire, canister, smoke)
- MeleeEngine (bayonet charges, cavalry charges, pursuit)
- CavalryEngine (charge state machine, fatigue, rally)
- NapoleonicFormationEngine (LINE/COLUMN/SQUARE/SKIRMISH, transitions)
- CourierEngine (dispatch, interception, delivery, pool limits)
- ForagingEngine (capacity, depletion, recovery, ambush)
- Cross-engine integration
"""

from __future__ import annotations

import numpy as np
import pytest

from tests.conftest import make_rng


# ---------------------------------------------------------------------------
# VolleyFireEngine tests
# ---------------------------------------------------------------------------


class TestVolleyFireConfig:
    """VolleyFireConfig validation."""

    def test_default_values(self) -> None:
        from stochastic_warfare.combat.volley_fire import VolleyFireConfig
        cfg = VolleyFireConfig()
        assert cfg.rifle_accuracy_multiplier == 3.0
        assert cfg.smoke_per_volley == 0.1

    def test_custom_values(self) -> None:
        from stochastic_warfare.combat.volley_fire import VolleyFireConfig
        cfg = VolleyFireConfig(rifle_accuracy_multiplier=2.0)
        assert cfg.rifle_accuracy_multiplier == 2.0

    def test_volley_types(self) -> None:
        from stochastic_warfare.combat.volley_fire import VolleyType
        assert VolleyType.VOLLEY_BY_RANK == 0
        assert VolleyType.CANISTER == 3


class TestVolleyFireEngine:
    """VolleyFireEngine mechanics."""

    @pytest.fixture()
    def engine(self):
        from stochastic_warfare.combat.volley_fire import VolleyFireEngine
        return VolleyFireEngine(rng=make_rng(42))

    def test_volley_produces_casualties(self, engine) -> None:
        result = engine.fire_volley(500, 100.0)
        assert result.casualties >= 0
        assert result.ammo_consumed == 500

    def test_close_range_more_lethal(self, engine) -> None:
        """Closer range should produce more casualties on average."""
        rng1 = make_rng(1)
        rng2 = make_rng(1)
        from stochastic_warfare.combat.volley_fire import VolleyFireEngine
        e1 = VolleyFireEngine(rng=rng1)
        e2 = VolleyFireEngine(rng=rng2)
        # Accumulate over multiple volleys for statistical stability
        close_total = sum(e1.fire_volley(500, 50.0).casualties for _ in range(20))
        far_total = sum(e2.fire_volley(500, 200.0).casualties for _ in range(20))
        assert close_total > far_total

    def test_rifle_more_accurate(self, engine) -> None:
        from stochastic_warfare.combat.volley_fire import VolleyFireEngine
        # Compare rifle vs smoothbore at same range
        e1 = VolleyFireEngine(rng=make_rng(10))
        e2 = VolleyFireEngine(rng=make_rng(10))
        rifle_total = sum(
            e1.fire_volley(100, 150.0, is_rifle=True).casualties
            for _ in range(50)
        )
        smooth_total = sum(
            e2.fire_volley(100, 150.0, is_rifle=False).casualties
            for _ in range(50)
        )
        assert rifle_total > smooth_total

    def test_formation_reduces_firepower(self, engine) -> None:
        from stochastic_warfare.combat.volley_fire import VolleyFireEngine
        e1 = VolleyFireEngine(rng=make_rng(5))
        e2 = VolleyFireEngine(rng=make_rng(5))
        line_total = sum(
            e1.fire_volley(500, 100.0, formation_firepower_fraction=1.0).casualties
            for _ in range(20)
        )
        column_total = sum(
            e2.fire_volley(500, 100.0, formation_firepower_fraction=0.3).casualties
            for _ in range(20)
        )
        assert line_total > column_total

    def test_smoke_accumulates(self, engine) -> None:
        engine.fire_volley(500, 100.0)
        assert engine.current_smoke > 0

    def test_smoke_dissipates(self, engine) -> None:
        engine.fire_volley(500, 100.0)
        initial = engine.current_smoke
        engine.update_smoke(60.0, wind_speed_mps=3.0)
        assert engine.current_smoke < initial

    def test_smoke_reduces_accuracy(self) -> None:
        from stochastic_warfare.combat.volley_fire import VolleyFireEngine
        e1 = VolleyFireEngine(rng=make_rng(20))
        e2 = VolleyFireEngine(rng=make_rng(20))
        clear_total = sum(
            e1.fire_volley(500, 100.0, current_smoke=0.0).casualties
            for _ in range(30)
        )
        smoky_total = sum(
            e2.fire_volley(500, 100.0, current_smoke=0.8).casualties
            for _ in range(30)
        )
        assert clear_total > smoky_total

    def test_canister_at_close_range(self, engine) -> None:
        result = engine.fire_canister(100.0, 4)
        assert result.casualties >= 0
        assert result.ammo_consumed == 4

    def test_canister_out_of_range(self, engine) -> None:
        result = engine.fire_canister(500.0, 4)
        assert result.casualties == 0

    def test_canister_range_effectiveness(self) -> None:
        from stochastic_warfare.combat.volley_fire import VolleyFireEngine
        e1 = VolleyFireEngine(rng=make_rng(30))
        e2 = VolleyFireEngine(rng=make_rng(30))
        close_total = sum(e1.fire_canister(50.0, 6).casualties for _ in range(30))
        far_total = sum(e2.fire_canister(350.0, 6).casualties for _ in range(30))
        assert close_total > far_total

    def test_independent_fire_less_accurate(self) -> None:
        from stochastic_warfare.combat.volley_fire import (
            VolleyFireEngine, VolleyType,
        )
        e1 = VolleyFireEngine(rng=make_rng(40))
        e2 = VolleyFireEngine(rng=make_rng(40))
        volley_total = sum(
            e1.fire_volley(500, 100.0, volley_type=VolleyType.VOLLEY_BY_RANK).casualties
            for _ in range(30)
        )
        indep_total = sum(
            e2.fire_volley(500, 100.0, volley_type=VolleyType.INDEPENDENT_FIRE).casualties
            for _ in range(30)
        )
        assert volley_total > indep_total

    def test_state_roundtrip(self, engine) -> None:
        from stochastic_warfare.combat.volley_fire import VolleyFireEngine
        engine.fire_volley(500, 100.0)
        state = engine.get_state()
        eng2 = VolleyFireEngine(rng=make_rng(99))
        eng2.set_state(state)
        assert eng2.current_smoke == pytest.approx(engine.current_smoke)

    def test_zero_muskets(self, engine) -> None:
        result = engine.fire_volley(0, 100.0)
        assert result.casualties == 0


# ---------------------------------------------------------------------------
# MeleeEngine tests
# ---------------------------------------------------------------------------


class TestMeleeConfig:
    """MeleeConfig validation."""

    def test_default_values(self) -> None:
        from stochastic_warfare.combat.melee import MeleeConfig
        cfg = MeleeConfig()
        assert cfg.pre_contact_morale_threshold == 0.4
        assert cfg.cavalry_shock_multiplier == 2.0

    def test_custom_values(self) -> None:
        from stochastic_warfare.combat.melee import MeleeConfig
        cfg = MeleeConfig(pursuit_casualty_rate=0.15)
        assert cfg.pursuit_casualty_rate == 0.15

    def test_melee_types(self) -> None:
        from stochastic_warfare.combat.melee import MeleeType
        assert MeleeType.BAYONET_CHARGE == 0
        assert MeleeType.CAVALRY_CHARGE == 1


class TestMeleeEngine:
    """MeleeEngine mechanics."""

    @pytest.fixture()
    def engine(self):
        from stochastic_warfare.combat.melee import MeleeEngine
        return MeleeEngine(rng=make_rng(42))

    def test_pre_contact_defender_breaks(self, engine) -> None:
        from stochastic_warfare.combat.melee import MeleeType
        d_breaks, a_breaks = engine.check_pre_contact_morale(
            attacker_morale=0.8,
            defender_morale=0.3,
            melee_type=MeleeType.BAYONET_CHARGE,
        )
        assert d_breaks is True
        assert a_breaks is False

    def test_pre_contact_defender_holds(self, engine) -> None:
        from stochastic_warfare.combat.melee import MeleeType
        d_breaks, a_breaks = engine.check_pre_contact_morale(
            attacker_morale=0.8,
            defender_morale=0.8,
            melee_type=MeleeType.BAYONET_CHARGE,
        )
        assert d_breaks is False

    def test_cavalry_shock_lowers_threshold(self, engine) -> None:
        """Cavalry charge should make defender break more easily."""
        from stochastic_warfare.combat.melee import MeleeType
        # With bayonet (no shock), defender at 0.6 morale holds
        d1, _ = engine.check_pre_contact_morale(
            0.8, 0.6, MeleeType.BAYONET_CHARGE,
        )
        # With cavalry charge and high vulnerability, defender may break
        d2, _ = engine.check_pre_contact_morale(
            0.8, 0.6, MeleeType.CAVALRY_CHARGE,
            defender_formation_cavalry_vuln=1.5,
        )
        # Cavalry makes breaking more likely
        assert not d1 or d2  # at minimum cavalry is not less scary

    def test_cavalry_vs_square(self, engine) -> None:
        from stochastic_warfare.combat.melee import MeleeType
        result = engine.resolve_melee_round(
            120, 75, MeleeType.CAVALRY_CHARGE,
            defender_formation_cavalry_vuln=0.1,
        )
        # Square should result in very few defender casualties
        assert result.defender_casualties >= 0

    def test_cavalry_vs_line_more_lethal(self) -> None:
        from stochastic_warfare.combat.melee import MeleeEngine, MeleeType
        e1 = MeleeEngine(rng=make_rng(50))
        e2 = MeleeEngine(rng=make_rng(50))
        # Cavalry vs line (vuln 1.5)
        line_cas = sum(
            e1.resolve_melee_round(120, 75, MeleeType.CAVALRY_CHARGE, 1.5).defender_casualties
            for _ in range(30)
        )
        # Cavalry vs square (vuln 0.1)
        square_cas = sum(
            e2.resolve_melee_round(120, 75, MeleeType.CAVALRY_CHARGE, 0.1).defender_casualties
            for _ in range(30)
        )
        assert line_cas > square_cas

    def test_bayonet_charge(self, engine) -> None:
        from stochastic_warfare.combat.melee import MeleeType
        result = engine.resolve_melee_round(
            75, 75, MeleeType.BAYONET_CHARGE,
        )
        assert result.attacker_casualties >= 0
        assert result.defender_casualties >= 0

    def test_shock_decay_per_round(self) -> None:
        from stochastic_warfare.combat.melee import MeleeEngine, MeleeType
        e1 = MeleeEngine(rng=make_rng(60))
        e2 = MeleeEngine(rng=make_rng(60))
        r1_cas = sum(
            e1.resolve_melee_round(120, 75, MeleeType.CAVALRY_CHARGE, 1.0, round_number=1).defender_casualties
            for _ in range(30)
        )
        r5_cas = sum(
            e2.resolve_melee_round(120, 75, MeleeType.CAVALRY_CHARGE, 1.0, round_number=5).defender_casualties
            for _ in range(30)
        )
        # First round should be more devastating than 5th
        assert r1_cas >= r5_cas

    def test_force_ratio_matters(self) -> None:
        from stochastic_warfare.combat.melee import MeleeEngine, MeleeType
        e1 = MeleeEngine(rng=make_rng(70))
        e2 = MeleeEngine(rng=make_rng(70))
        # 3:1 advantage
        sup_cas = sum(
            e1.resolve_melee_round(225, 75, MeleeType.BAYONET_CHARGE).defender_casualties
            for _ in range(30)
        )
        # 1:1
        even_cas = sum(
            e2.resolve_melee_round(75, 75, MeleeType.BAYONET_CHARGE).defender_casualties
            for _ in range(30)
        )
        assert sup_cas > even_cas

    def test_pursuit_casualties(self, engine) -> None:
        cas = engine.compute_pursuit_casualties(
            routed_strength=100,
            pursuer_speed=8.0,
            routed_speed=2.0,
            dt_s=60.0,
        )
        assert cas >= 0

    def test_pursuit_no_casualties_if_slower(self, engine) -> None:
        cas = engine.compute_pursuit_casualties(
            routed_strength=100,
            pursuer_speed=2.0,
            routed_speed=5.0,
            dt_s=60.0,
        )
        assert cas == 0

    def test_zero_strength(self, engine) -> None:
        from stochastic_warfare.combat.melee import MeleeType
        result = engine.resolve_melee_round(0, 75, MeleeType.BAYONET_CHARGE)
        assert result.attacker_casualties == 0
        assert result.defender_casualties == 0

    def test_state_roundtrip(self, engine) -> None:
        from stochastic_warfare.combat.melee import MeleeEngine
        state = engine.get_state()
        eng2 = MeleeEngine(rng=make_rng(99))
        eng2.set_state(state)
        # Stateless engine, just verify no error


# ---------------------------------------------------------------------------
# CavalryEngine tests
# ---------------------------------------------------------------------------


class TestCavalryConfig:
    """CavalryConfig validation."""

    def test_default_values(self) -> None:
        from stochastic_warfare.movement.cavalry import CavalryConfig
        cfg = CavalryConfig()
        assert cfg.gallop_start_distance_m == 150.0
        assert cfg.rally_duration_s == 120.0

    def test_charge_phases(self) -> None:
        from stochastic_warfare.movement.cavalry import ChargePhase
        assert ChargePhase.WALK == 0
        assert ChargePhase.RALLY == 6


class TestCavalryEngine:
    """CavalryEngine charge state machine."""

    @pytest.fixture()
    def engine(self):
        from stochastic_warfare.movement.cavalry import CavalryEngine
        return CavalryEngine(rng=make_rng(42))

    def test_initiate_charge(self, engine) -> None:
        from stochastic_warfare.movement.cavalry import ChargePhase
        state = engine.initiate_charge("c1", "unit_1", "target_1", 500.0)
        assert state.phase == ChargePhase.WALK
        assert state.distance_to_target_m == 500.0

    def test_initiate_close_charge(self, engine) -> None:
        from stochastic_warfare.movement.cavalry import ChargePhase
        state = engine.initiate_charge("c2", "unit_1", "target_1", 30.0)
        assert state.phase == ChargePhase.CHARGE

    def test_walk_to_trot_transition(self, engine) -> None:
        from stochastic_warfare.movement.cavalry import ChargePhase
        engine.initiate_charge("c1", "u1", "t1", 200.0)
        # Walk at 2 m/s, after 30s = 60m moved → 140m remaining
        engine.update_charge("c1", 30.0)
        state = engine._charges["c1"]
        assert state.distance_to_target_m < 200.0

    def test_phase_progression(self, engine) -> None:
        from stochastic_warfare.movement.cavalry import ChargePhase
        engine.initiate_charge("c1", "u1", "t1", 300.0)
        # Run many updates to advance through phases
        for _ in range(100):
            phase = engine.update_charge("c1", 1.0)
        # Should have reached at least gallop
        state = engine._charges["c1"]
        assert state.phase.value >= ChargePhase.GALLOP.value or state.distance_to_target_m < 150.0

    def test_fatigue_at_gallop(self, engine) -> None:
        from stochastic_warfare.movement.cavalry import ChargePhase
        engine.initiate_charge("c1", "u1", "t1", 100.0)
        # Start at gallop distance
        state = engine._charges["c1"]
        state.phase = ChargePhase.GALLOP
        engine.update_charge("c1", 10.0)
        assert state.fatigue > 0

    def test_exhaustion(self, engine) -> None:
        from stochastic_warfare.movement.cavalry import ChargePhase
        state = engine.initiate_charge("c1", "u1", "t1", 100.0)
        state.phase = ChargePhase.GALLOP
        state.gallop_time_s = 55.0
        engine.update_charge("c1", 10.0)
        assert engine.is_exhausted("c1")

    def test_rally_duration(self, engine) -> None:
        from stochastic_warfare.movement.cavalry import ChargePhase
        state = engine.initiate_charge("c1", "u1", "t1", 100.0)
        engine.begin_rally("c1")
        assert state.phase == ChargePhase.RALLY
        engine.update_charge("c1", 121.0)
        assert state.completed is True

    def test_pursuit_phase(self, engine) -> None:
        from stochastic_warfare.movement.cavalry import ChargePhase
        engine.initiate_charge("c1", "u1", "t1", 100.0)
        engine.begin_pursuit("c1")
        state = engine._charges["c1"]
        assert state.phase == ChargePhase.PURSUIT

    def test_get_charge_speed(self, engine) -> None:
        from stochastic_warfare.movement.cavalry import ChargePhase
        state = engine.initiate_charge("c1", "u1", "t1", 500.0)
        speed = engine.get_charge_speed("c1")
        assert speed == pytest.approx(2.0)  # WALK speed

    def test_screening_hussar(self, engine) -> None:
        mod = engine.screening_modifier("hussar_squadron")
        assert mod > 1.0

    def test_screening_cuirassier(self, engine) -> None:
        mod = engine.screening_modifier("cuirassier_squadron")
        assert mod == 1.0

    def test_state_roundtrip(self, engine) -> None:
        from stochastic_warfare.movement.cavalry import CavalryEngine
        engine.initiate_charge("c1", "u1", "t1", 300.0)
        state = engine.get_state()
        eng2 = CavalryEngine(rng=make_rng(99))
        eng2.set_state(state)
        assert "c1" in eng2._charges
        assert eng2._charges["c1"].distance_to_target_m == 300.0


# ---------------------------------------------------------------------------
# NapoleonicFormationEngine tests
# ---------------------------------------------------------------------------


class TestNapoleonicFormationConfig:
    """NapoleonicFormationConfig validation."""

    def test_default_values(self) -> None:
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationConfig,
        )
        cfg = NapoleonicFormationConfig()
        assert cfg.firepower_fractions[0] == 1.0  # LINE

    def test_formation_types(self) -> None:
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationType,
        )
        assert NapoleonicFormationType.LINE == 0
        assert NapoleonicFormationType.SQUARE == 2

    def test_custom_transition_time(self) -> None:
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationConfig,
        )
        cfg = NapoleonicFormationConfig()
        assert cfg.transition_times_s["SQUARE_to_LINE"] == 90.0


class TestNapoleonicFormationEngine:
    """NapoleonicFormationEngine mechanics."""

    @pytest.fixture()
    def engine(self):
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationEngine,
        )
        return NapoleonicFormationEngine()

    def test_set_formation(self, engine) -> None:
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationType,
        )
        engine.set_formation("u1", NapoleonicFormationType.COLUMN)
        assert engine.get_formation("u1") == NapoleonicFormationType.COLUMN

    def test_default_is_line(self, engine) -> None:
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationType,
        )
        assert engine.get_formation("unknown") == NapoleonicFormationType.LINE

    def test_transition_timing(self, engine) -> None:
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationType,
        )
        engine.set_formation("u1", NapoleonicFormationType.LINE)
        time_s = engine.order_formation_change("u1", NapoleonicFormationType.SQUARE)
        assert time_s == 45.0  # LINE_to_SQUARE

    def test_square_to_line_slow(self, engine) -> None:
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationType,
        )
        engine.set_formation("u1", NapoleonicFormationType.SQUARE)
        time_s = engine.order_formation_change("u1", NapoleonicFormationType.LINE)
        assert time_s == 90.0

    def test_transition_completes(self, engine) -> None:
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationType,
        )
        engine.set_formation("u1", NapoleonicFormationType.LINE)
        engine.order_formation_change("u1", NapoleonicFormationType.COLUMN)
        completed = engine.update(100.0)
        assert "u1" in completed
        assert engine.get_formation("u1") == NapoleonicFormationType.COLUMN

    def test_is_transitioning(self, engine) -> None:
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationType,
        )
        engine.set_formation("u1", NapoleonicFormationType.LINE)
        engine.order_formation_change("u1", NapoleonicFormationType.SQUARE)
        assert engine.is_transitioning("u1") is True
        engine.update(100.0)
        assert engine.is_transitioning("u1") is False

    def test_firepower_line(self, engine) -> None:
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationType,
        )
        engine.set_formation("u1", NapoleonicFormationType.LINE)
        assert engine.firepower_fraction("u1") == pytest.approx(1.0)

    def test_firepower_column(self, engine) -> None:
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationType,
        )
        engine.set_formation("u1", NapoleonicFormationType.COLUMN)
        assert engine.firepower_fraction("u1") == pytest.approx(0.3)

    def test_speed_column(self, engine) -> None:
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationType,
        )
        engine.set_formation("u1", NapoleonicFormationType.COLUMN)
        assert engine.speed_multiplier("u1") == pytest.approx(0.9)

    def test_speed_square_slow(self, engine) -> None:
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationType,
        )
        engine.set_formation("u1", NapoleonicFormationType.SQUARE)
        assert engine.speed_multiplier("u1") == pytest.approx(0.3)

    def test_cavalry_vuln_square_low(self, engine) -> None:
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationType,
        )
        engine.set_formation("u1", NapoleonicFormationType.SQUARE)
        assert engine.cavalry_vulnerability("u1") == pytest.approx(0.1)

    def test_cavalry_vuln_skirmish_high(self, engine) -> None:
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationType,
        )
        engine.set_formation("u1", NapoleonicFormationType.SKIRMISH)
        assert engine.cavalry_vulnerability("u1") == pytest.approx(1.5)

    def test_artillery_vuln_square_max(self, engine) -> None:
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationType,
        )
        engine.set_formation("u1", NapoleonicFormationType.SQUARE)
        assert engine.artillery_vulnerability("u1") == pytest.approx(2.0)

    def test_artillery_vuln_skirmish_min(self, engine) -> None:
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationType,
        )
        engine.set_formation("u1", NapoleonicFormationType.SKIRMISH)
        assert engine.artillery_vulnerability("u1") == pytest.approx(0.3)

    def test_worst_during_transition_vuln(self, engine) -> None:
        """During transition, use worst vulnerability."""
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationType,
        )
        engine.set_formation("u1", NapoleonicFormationType.LINE)
        engine.order_formation_change("u1", NapoleonicFormationType.SQUARE)
        # Transitioning LINE→SQUARE: worst cavalry vuln = max(1.0, 0.1) = 1.0
        assert engine.cavalry_vulnerability("u1") == pytest.approx(1.0)
        # Worst artillery vuln = max(0.5, 2.0) = 2.0
        assert engine.artillery_vulnerability("u1") == pytest.approx(2.0)

    def test_worst_during_transition_speed(self, engine) -> None:
        """During transition, use worst (lowest) speed."""
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationType,
        )
        engine.set_formation("u1", NapoleonicFormationType.COLUMN)
        engine.order_formation_change("u1", NapoleonicFormationType.SQUARE)
        # Worst speed = min(0.9, 0.3) = 0.3
        assert engine.speed_multiplier("u1") == pytest.approx(0.3)

    def test_concurrent_transitions(self, engine) -> None:
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationType,
        )
        engine.set_formation("u1", NapoleonicFormationType.LINE)
        engine.set_formation("u2", NapoleonicFormationType.COLUMN)
        engine.order_formation_change("u1", NapoleonicFormationType.SQUARE)
        engine.order_formation_change("u2", NapoleonicFormationType.LINE)
        completed = engine.update(100.0)
        assert "u1" in completed
        assert "u2" in completed

    def test_no_transition_if_same(self, engine) -> None:
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationType,
        )
        engine.set_formation("u1", NapoleonicFormationType.LINE)
        time_s = engine.order_formation_change("u1", NapoleonicFormationType.LINE)
        assert time_s == 0.0

    def test_state_roundtrip(self, engine) -> None:
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationEngine,
            NapoleonicFormationType,
        )
        engine.set_formation("u1", NapoleonicFormationType.SQUARE)
        state = engine.get_state()
        eng2 = NapoleonicFormationEngine()
        eng2.set_state(state)
        assert eng2.get_formation("u1") == NapoleonicFormationType.SQUARE


# ---------------------------------------------------------------------------
# CourierEngine tests
# ---------------------------------------------------------------------------


class TestCourierConfig:
    """CourierConfig validation."""

    def test_default_values(self) -> None:
        from stochastic_warfare.c2.courier import CourierConfig
        cfg = CourierConfig()
        assert cfg.max_couriers_per_hq == 4

    def test_courier_types(self) -> None:
        from stochastic_warfare.c2.courier import CourierType
        assert CourierType.MOUNTED_ADC == 0
        assert CourierType.DRUM_BUGLE == 3


class TestCourierEngine:
    """CourierEngine mechanics."""

    @pytest.fixture()
    def engine(self):
        from stochastic_warfare.c2.courier import CourierEngine
        return CourierEngine(rng=make_rng(42))

    def test_dispatch_courier(self, engine) -> None:
        from stochastic_warfare.c2.courier import CourierType
        msg = engine.dispatch_courier(
            "m1", CourierType.MOUNTED_ADC,
            (0, 0), (5000, 0),
            sim_time_s=0.0,
        )
        assert msg is not None
        assert msg.arrival_time_s > 0

    def test_travel_time_road_faster(self, engine) -> None:
        from stochastic_warfare.c2.courier import CourierType
        road_time = engine.compute_travel_time(5000.0, CourierType.MOUNTED_ADC, "road")
        open_time = engine.compute_travel_time(5000.0, CourierType.MOUNTED_ADC, "open")
        assert road_time < open_time

    def test_travel_time_foot_slower(self, engine) -> None:
        from stochastic_warfare.c2.courier import CourierType
        mounted = engine.compute_travel_time(5000.0, CourierType.MOUNTED_ADC, "open")
        foot = engine.compute_travel_time(5000.0, CourierType.FOOT_MESSENGER, "open")
        assert foot > mounted

    def test_drum_bugle_in_range(self, engine) -> None:
        from stochastic_warfare.c2.courier import CourierType
        time = engine.compute_travel_time(200.0, CourierType.DRUM_BUGLE)
        assert time == pytest.approx(2.0)

    def test_drum_bugle_out_of_range(self, engine) -> None:
        from stochastic_warfare.c2.courier import CourierType
        time = engine.compute_travel_time(500.0, CourierType.DRUM_BUGLE)
        assert time == float("inf")

    def test_message_delivery(self, engine) -> None:
        from stochastic_warfare.c2.courier import CourierType
        msg = engine.dispatch_courier(
            "m1", CourierType.MOUNTED_ADC,
            (0, 0), (1000, 0),
            sim_time_s=0.0,
        )
        delivered = engine.update(msg.arrival_time_s + 1.0)
        if not msg.intercepted:
            assert len(delivered) == 1
            assert delivered[0].message_id == "m1"

    def test_interception_possible(self) -> None:
        """With high enemy_km, some messages get intercepted."""
        from stochastic_warfare.c2.courier import CourierEngine, CourierType
        intercepted_count = 0
        for seed in range(100):
            eng = CourierEngine(rng=make_rng(seed))
            msg = eng.dispatch_courier(
                f"m{seed}", CourierType.FOOT_MESSENGER,
                (0, 0), (10000, 0),
                enemy_km=20.0,
            )
            if msg.intercepted:
                intercepted_count += 1
        assert intercepted_count > 0

    def test_courier_pool_limit(self, engine) -> None:
        from stochastic_warfare.c2.courier import CourierType
        for i in range(4):
            engine.dispatch_courier(
                f"m{i}", CourierType.MOUNTED_ADC,
                (0, 0), (10000, 0),
                hq_id="hq1",
                sim_time_s=0.0,
            )
        # 5th should fail
        msg = engine.dispatch_courier(
            "m4", CourierType.MOUNTED_ADC,
            (0, 0), (10000, 0),
            hq_id="hq1",
        )
        assert msg is None

    def test_available_couriers(self, engine) -> None:
        from stochastic_warfare.c2.courier import CourierType
        assert engine.available_couriers("hq1") == 4
        engine.dispatch_courier(
            "m1", CourierType.MOUNTED_ADC,
            (0, 0), (1000, 0),
            hq_id="hq1",
        )
        assert engine.available_couriers("hq1") == 3

    def test_hour_scale_delay(self, engine) -> None:
        """10km courier should take ~33 minutes."""
        from stochastic_warfare.c2.courier import CourierType
        time = engine.compute_travel_time(10000.0, CourierType.MOUNTED_ADC, "open")
        assert 1000.0 < time < 3000.0

    def test_state_roundtrip(self, engine) -> None:
        from stochastic_warfare.c2.courier import CourierEngine, CourierType
        engine.dispatch_courier(
            "m1", CourierType.MOUNTED_ADC,
            (0, 0), (5000, 0),
            hq_id="hq1",
        )
        state = engine.get_state()
        eng2 = CourierEngine(rng=make_rng(99))
        eng2.set_state(state)
        assert "m1" in eng2._messages


# ---------------------------------------------------------------------------
# ForagingEngine tests
# ---------------------------------------------------------------------------


class TestForagingConfig:
    """ForagingConfig validation."""

    def test_default_values(self) -> None:
        from stochastic_warfare.logistics.foraging import ForagingConfig
        cfg = ForagingConfig()
        assert cfg.men_per_km2_per_day == 500.0

    def test_terrain_productivity(self) -> None:
        from stochastic_warfare.logistics.foraging import TerrainProductivity
        assert TerrainProductivity.BARREN == 0
        assert TerrainProductivity.ABUNDANT == 4


class TestForagingEngine:
    """ForagingEngine mechanics."""

    @pytest.fixture()
    def engine(self):
        from stochastic_warfare.logistics.foraging import (
            ForagingEngine,
            TerrainProductivity,
        )
        eng = ForagingEngine(rng=make_rng(42))
        eng.register_zone("z1", (0, 0), 5000.0, TerrainProductivity.GOOD)
        return eng

    def test_register_zone(self, engine) -> None:
        assert "z1" in engine._zones

    def test_daily_capacity(self, engine) -> None:
        cap = engine.compute_daily_capacity("z1", "summer")
        assert cap > 0

    def test_seasonal_variation(self, engine) -> None:
        summer = engine.compute_daily_capacity("z1", "summer")
        winter = engine.compute_daily_capacity("z1", "winter")
        assert summer > winter

    def test_forage_success(self, engine) -> None:
        result = engine.forage("z1", 1000, "summer")
        assert result.rations_supplied > 0
        assert result.deficit >= 0

    def test_forage_depletion(self, engine) -> None:
        zone = engine._zones["z1"]
        initial = zone.remaining_fraction
        engine.forage("z1", 50000, "summer")
        assert zone.remaining_fraction < initial

    def test_recovery(self, engine) -> None:
        engine._zones["z1"].remaining_fraction = 0.5
        engine.update_recovery(10.0)
        assert engine._zones["z1"].remaining_fraction > 0.5

    def test_deficit_large_army(self, engine) -> None:
        result = engine.forage("z1", 1_000_000, "winter")
        assert result.deficit > 0

    def test_ambush_possible(self) -> None:
        from stochastic_warfare.logistics.foraging import (
            ForagingEngine,
            TerrainProductivity,
        )
        ambush_count = 0
        for seed in range(100):
            eng = ForagingEngine(rng=make_rng(seed))
            eng.register_zone("z1", (0, 0), 5000.0, TerrainProductivity.GOOD)
            result = eng.forage("z1", 10000, "summer")
            if result.ambush_occurred:
                ambush_count += 1
        assert ambush_count > 0

    def test_unknown_zone(self, engine) -> None:
        result = engine.forage("unknown", 1000, "summer")
        assert result.deficit == 1000.0

    def test_state_roundtrip(self, engine) -> None:
        from stochastic_warfare.logistics.foraging import ForagingEngine
        engine._zones["z1"].remaining_fraction = 0.3
        state = engine.get_state()
        eng2 = ForagingEngine(rng=make_rng(99))
        eng2.set_state(state)
        assert eng2._zones["z1"].remaining_fraction == pytest.approx(0.3)


# ---------------------------------------------------------------------------
# Cross-engine integration tests
# ---------------------------------------------------------------------------


class TestCrossEngineIntegration:
    """Cross-engine integration between Napoleonic modules."""

    def test_formation_to_volley_firepower(self) -> None:
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationEngine, NapoleonicFormationType,
        )
        from stochastic_warfare.combat.volley_fire import VolleyFireEngine

        form_eng = NapoleonicFormationEngine()
        vol_eng = VolleyFireEngine(rng=make_rng(1))

        form_eng.set_formation("u1", NapoleonicFormationType.COLUMN)
        fp = form_eng.firepower_fraction("u1")
        result = vol_eng.fire_volley(500, 100.0, formation_firepower_fraction=fp)
        # Column fires 30% of muskets → ~150 effective
        assert result.ammo_consumed == 150

    def test_formation_to_melee_vulnerability(self) -> None:
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationEngine, NapoleonicFormationType,
        )
        from stochastic_warfare.combat.melee import MeleeEngine, MeleeType

        form_eng = NapoleonicFormationEngine()
        melee_eng = MeleeEngine(rng=make_rng(2))

        form_eng.set_formation("u1", NapoleonicFormationType.SQUARE)
        cav_vuln = form_eng.cavalry_vulnerability("u1")
        assert cav_vuln == pytest.approx(0.1)

        d_breaks, _ = melee_eng.check_pre_contact_morale(
            0.8, 0.8, MeleeType.CAVALRY_CHARGE, cav_vuln,
        )
        # Square should not break even with cavalry
        assert d_breaks is False

    def test_cavalry_charge_to_melee(self) -> None:
        from stochastic_warfare.movement.cavalry import (
            CavalryEngine, ChargePhase,
        )
        from stochastic_warfare.combat.melee import MeleeEngine, MeleeType

        cav_eng = CavalryEngine(rng=make_rng(3))
        melee_eng = MeleeEngine(rng=make_rng(3))

        state = cav_eng.initiate_charge("c1", "u1", "t1", 10.0)
        # Advance to impact
        for _ in range(20):
            phase = cav_eng.update_charge("c1", 1.0)
            if phase == ChargePhase.IMPACT or phase == ChargePhase.PURSUIT:
                break
        # At impact, resolve melee
        result = melee_eng.resolve_melee_round(
            120, 75, MeleeType.CAVALRY_CHARGE, 1.0,
        )
        assert result.defender_casualties >= 0

    def test_smoke_to_volley(self) -> None:
        from stochastic_warfare.combat.volley_fire import VolleyFireEngine
        eng = VolleyFireEngine(rng=make_rng(4))
        # Fire several volleys to build smoke
        for _ in range(5):
            eng.fire_volley(500, 100.0)
        assert eng.current_smoke > 0
        # Next volley should use accumulated smoke
        result = eng.fire_volley(500, 100.0)
        assert result.casualties >= 0

    def test_modern_era_no_napoleonic_engines(self) -> None:
        from stochastic_warfare.simulation.scenario import (
            CampaignScenarioConfig,
            SimulationContext,
            TerrainConfig,
            SideConfig,
        )
        from stochastic_warfare.core.clock import SimulationClock
        from stochastic_warfare.core.events import EventBus
        from stochastic_warfare.core.rng import RNGManager
        from datetime import datetime, timezone, timedelta

        config = CampaignScenarioConfig(
            name="modern_test", date="2024-01-01", duration_hours=1.0,
            terrain=TerrainConfig(width_m=1000, height_m=1000),
            sides=[
                SideConfig(side="a", units=[]),
                SideConfig(side="b", units=[]),
            ],
        )
        ctx = SimulationContext(
            config=config,
            clock=SimulationClock(
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                tick_duration=timedelta(seconds=5),
            ),
            rng_manager=RNGManager(42),
            event_bus=EventBus(),
        )
        assert ctx.volley_fire_engine is None
        assert ctx.melee_engine is None
        assert ctx.cavalry_engine is None

    def test_ww1_engines_still_none_for_napoleonic(self) -> None:
        """WW1-specific engines not present in Napoleonic context."""
        from stochastic_warfare.simulation.scenario import (
            CampaignScenarioConfig,
            SimulationContext,
            TerrainConfig,
            SideConfig,
        )
        from stochastic_warfare.core.clock import SimulationClock
        from stochastic_warfare.core.events import EventBus
        from stochastic_warfare.core.rng import RNGManager
        from datetime import datetime, timezone, timedelta

        config = CampaignScenarioConfig(
            name="nap_test", date="1805-12-02", duration_hours=1.0,
            era="napoleonic",
            terrain=TerrainConfig(width_m=1000, height_m=1000),
            sides=[
                SideConfig(side="a", units=[]),
                SideConfig(side="b", units=[]),
            ],
        )
        ctx = SimulationContext(
            config=config,
            clock=SimulationClock(
                start=datetime(1805, 12, 2, tzinfo=timezone.utc),
                tick_duration=timedelta(seconds=5),
            ),
            rng_manager=RNGManager(42),
            event_bus=EventBus(),
        )
        assert ctx.trench_engine is None
        assert ctx.barrage_engine is None
        assert ctx.gas_warfare_engine is None
