"""Phase 27b: Engagement engine enhancements — burst fire, submunition scatter, multi-CM, TOT, CAS."""

from __future__ import annotations

import math

import numpy as np
import pytest

from tests.conftest import TS, make_rng
from stochastic_warfare.core.types import Position


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engagement_engine(rng=None, **kwargs):
    from stochastic_warfare.combat.ballistics import BallisticsEngine
    from stochastic_warfare.combat.damage import DamageEngine
    from stochastic_warfare.combat.engagement import EngagementConfig, EngagementEngine
    from stochastic_warfare.combat.fratricide import FratricideEngine
    from stochastic_warfare.combat.hit_probability import HitProbabilityEngine
    from stochastic_warfare.combat.suppression import SuppressionEngine
    from stochastic_warfare.core.events import EventBus

    rng = rng or make_rng()
    bus = EventBus()
    bal = BallisticsEngine(rng=rng)
    dmg = DamageEngine(event_bus=bus, rng=rng)
    hit = HitProbabilityEngine(bal, rng=rng)
    sup = SuppressionEngine(event_bus=bus, rng=rng)
    frat = FratricideEngine(event_bus=bus, rng=rng)
    cfg = EngagementConfig(**kwargs)
    return EngagementEngine(
        hit_engine=hit, damage_engine=dmg, suppression_engine=sup,
        fratricide_engine=frat, event_bus=bus, rng=rng, config=cfg,
    )


def _make_weapon_instance(burst_size=1, ammo_id="762_ball", ammo_count=100):
    from stochastic_warfare.combat.ammunition import WeaponDefinition, WeaponInstance

    defn = WeaponDefinition(
        weapon_id="test_rifle", display_name="Test Rifle",
        category="SMALL_ARMS", caliber_mm=7.62,
        muzzle_velocity_mps=850.0, max_range_m=800.0,
        rate_of_fire_rpm=600.0, burst_size=burst_size,
        base_accuracy_mrad=1.0, magazine_capacity=200,
        compatible_ammo=[ammo_id],
    )
    wi = WeaponInstance(definition=defn)
    wi.ammo_state.add(ammo_id, ammo_count)
    return wi


def _make_ammo_def(ammo_id="762_ball", **kwargs):
    from stochastic_warfare.combat.ammunition import AmmoDefinition

    defaults = dict(
        ammo_id=ammo_id, display_name="7.62mm Ball",
        ammo_type="AP", mass_kg=0.01, diameter_mm=7.62,
        penetration_mm_rha=10.0, penetration_reference_range_m=500.0,
        blast_radius_m=0.0, fragmentation_radius_m=0.0,
    )
    defaults.update(kwargs)
    return AmmoDefinition(**defaults)


def _make_dpicm_ammo(**kwargs):
    from stochastic_warfare.combat.ammunition import AmmoDefinition

    defaults = dict(
        ammo_id="dpicm_155", display_name="155mm DPICM",
        ammo_type="HE", mass_kg=40.0, diameter_mm=155.0,
        blast_radius_m=50.0, fragmentation_radius_m=80.0,
        submunition_count=72, submunition_lethal_radius_m=5.0,
        uxo_rate=0.05,
    )
    defaults.update(kwargs)
    return AmmoDefinition(**defaults)


def _make_damage_engine(rng=None, **kwargs):
    from stochastic_warfare.combat.damage import DamageConfig, DamageEngine
    from stochastic_warfare.core.events import EventBus

    rng = rng or make_rng()
    bus = EventBus()
    cfg = DamageConfig(**kwargs)
    return DamageEngine(event_bus=bus, rng=rng, config=cfg)


def _make_indirect_fire_engine(rng=None, **kwargs):
    from stochastic_warfare.combat.ballistics import BallisticsEngine
    from stochastic_warfare.combat.damage import DamageEngine
    from stochastic_warfare.combat.indirect_fire import IndirectFireConfig, IndirectFireEngine
    from stochastic_warfare.core.events import EventBus

    rng = rng or make_rng()
    bus = EventBus()
    bal = BallisticsEngine(rng=rng)
    dmg = DamageEngine(event_bus=bus, rng=rng)
    cfg = IndirectFireConfig(**kwargs)
    return IndirectFireEngine(
        ballistics=bal, damage_engine=dmg, event_bus=bus, rng=rng, config=cfg,
    )


def _make_howitzer_def(**kwargs):
    from stochastic_warfare.combat.ammunition import WeaponDefinition

    defaults = dict(
        weapon_id="m109", display_name="M109 Howitzer",
        category="ARTILLERY", caliber_mm=155.0,
        muzzle_velocity_mps=600.0, max_range_m=24000.0,
        rate_of_fire_rpm=4.0, base_accuracy_mrad=0.5,
        cep_m=100.0,
    )
    defaults.update(kwargs)
    return WeaponDefinition(**defaults)


def _make_he_ammo(**kwargs):
    from stochastic_warfare.combat.ammunition import AmmoDefinition

    defaults = dict(
        ammo_id="he_155", display_name="155mm HE",
        ammo_type="HE", mass_kg=40.0, diameter_mm=155.0,
        blast_radius_m=50.0, fragmentation_radius_m=80.0,
    )
    defaults.update(kwargs)
    return AmmoDefinition(**defaults)


def _make_air_combat_engine(rng=None, **kwargs):
    from stochastic_warfare.combat.air_combat import AirCombatConfig, AirCombatEngine
    from stochastic_warfare.core.events import EventBus

    rng = rng or make_rng()
    bus = EventBus()
    cfg = AirCombatConfig(**kwargs)
    return AirCombatEngine(event_bus=bus, rng=rng, config=cfg)


def _make_air_ground_engine(rng=None, **kwargs):
    from stochastic_warfare.combat.air_ground import AirGroundConfig, AirGroundEngine
    from stochastic_warfare.core.events import EventBus

    rng = rng or make_rng()
    bus = EventBus()
    cfg = AirGroundConfig(**kwargs)
    return AirGroundEngine(event_bus=bus, rng=rng, config=cfg)


# ---------------------------------------------------------------------------
# 1. Burst fire
# ---------------------------------------------------------------------------


class TestBurstFire:
    def test_single_round_default(self) -> None:
        """burst_size=1 fires a single round."""
        eng = _make_engagement_engine(rng=make_rng(1), enable_burst_fire=True)
        wi = _make_weapon_instance(burst_size=1, ammo_count=50)
        ammo = _make_ammo_def()
        result = eng.execute_burst_engagement(
            "att", "tgt", Position(0, 0, 0), Position(200, 0, 0),
            wi, "762_ball", ammo, crew_skill=0.8,
        )
        assert result.rounds_fired == 1

    def test_burst_fires_n_rounds(self) -> None:
        eng = _make_engagement_engine(rng=make_rng(2), enable_burst_fire=True)
        wi = _make_weapon_instance(burst_size=5, ammo_count=50)
        ammo = _make_ammo_def()
        result = eng.execute_burst_engagement(
            "att", "tgt", Position(0, 0, 0), Position(200, 0, 0),
            wi, "762_ball", ammo, crew_skill=0.8,
        )
        assert result.rounds_fired == 5

    def test_ammo_consumed(self) -> None:
        eng = _make_engagement_engine(rng=make_rng(3), enable_burst_fire=True)
        wi = _make_weapon_instance(burst_size=5, ammo_count=50)
        ammo = _make_ammo_def()
        before = wi.ammo_state.available("762_ball")
        eng.execute_burst_engagement(
            "att", "tgt", Position(0, 0, 0), Position(200, 0, 0),
            wi, "762_ball", ammo,
        )
        after = wi.ammo_state.available("762_ball")
        assert before - after == 5

    def test_partial_burst(self) -> None:
        """If magazine < burst_size, fire what's available."""
        eng = _make_engagement_engine(rng=make_rng(4), enable_burst_fire=True)
        wi = _make_weapon_instance(burst_size=10, ammo_count=3)
        ammo = _make_ammo_def()
        result = eng.execute_burst_engagement(
            "att", "tgt", Position(0, 0, 0), Position(200, 0, 0),
            wi, "762_ball", ammo,
        )
        assert result.rounds_fired == 3

    def test_hits_bounded(self) -> None:
        eng = _make_engagement_engine(rng=make_rng(5), enable_burst_fire=True)
        wi = _make_weapon_instance(burst_size=10, ammo_count=50)
        ammo = _make_ammo_def()
        result = eng.execute_burst_engagement(
            "att", "tgt", Position(0, 0, 0), Position(100, 0, 0),
            wi, "762_ball", ammo, crew_skill=0.9,
        )
        assert 0 <= result.hits <= result.rounds_fired

    def test_damage_per_hit(self) -> None:
        eng = _make_engagement_engine(rng=make_rng(6), enable_burst_fire=True)
        wi = _make_weapon_instance(burst_size=10, ammo_count=50)
        ammo = _make_ammo_def()
        result = eng.execute_burst_engagement(
            "att", "tgt", Position(0, 0, 0), Position(100, 0, 0),
            wi, "762_ball", ammo, crew_skill=0.9,
        )
        assert len(result.damage_results) == result.hits

    def test_disabled_fires_single(self) -> None:
        """With enable_burst_fire=False, always fires 1 round regardless of burst_size."""
        eng = _make_engagement_engine(rng=make_rng(7), enable_burst_fire=False)
        wi = _make_weapon_instance(burst_size=5, ammo_count=50)
        ammo = _make_ammo_def()
        result = eng.execute_burst_engagement(
            "att", "tgt", Position(0, 0, 0), Position(200, 0, 0),
            wi, "762_ball", ammo,
        )
        assert result.rounds_fired == 1

    def test_max_burst_cap(self) -> None:
        eng = _make_engagement_engine(
            rng=make_rng(8), enable_burst_fire=True, max_burst_size=3,
        )
        wi = _make_weapon_instance(burst_size=10, ammo_count=50)
        ammo = _make_ammo_def()
        result = eng.execute_burst_engagement(
            "att", "tgt", Position(0, 0, 0), Position(200, 0, 0),
            wi, "762_ball", ammo,
        )
        assert result.rounds_fired == 3

    def test_result_fields(self) -> None:
        eng = _make_engagement_engine(rng=make_rng(9), enable_burst_fire=True)
        wi = _make_weapon_instance(burst_size=3, ammo_count=50)
        ammo = _make_ammo_def()
        result = eng.execute_burst_engagement(
            "att", "tgt", Position(0, 0, 0), Position(200, 0, 0),
            wi, "762_ball", ammo,
        )
        assert result.attacker_id == "att"
        assert result.target_id == "tgt"
        assert result.weapon_id == "test_rifle"
        assert result.range_m > 0

    def test_out_of_range(self) -> None:
        eng = _make_engagement_engine(rng=make_rng(10), enable_burst_fire=True)
        wi = _make_weapon_instance(burst_size=5, ammo_count=50)
        ammo = _make_ammo_def()
        result = eng.execute_burst_engagement(
            "att", "tgt", Position(0, 0, 0), Position(5000, 0, 0),
            wi, "762_ball", ammo,
        )
        assert result.engaged is False
        assert result.rounds_fired == 0

    def test_no_ammo(self) -> None:
        eng = _make_engagement_engine(rng=make_rng(11), enable_burst_fire=True)
        wi = _make_weapon_instance(burst_size=5, ammo_count=0)
        ammo = _make_ammo_def()
        result = eng.execute_burst_engagement(
            "att", "tgt", Position(0, 0, 0), Position(200, 0, 0),
            wi, "762_ball", ammo,
        )
        assert result.engaged is False
        assert result.rounds_fired == 0


# ---------------------------------------------------------------------------
# 2. Submunition scatter
# ---------------------------------------------------------------------------


class TestSubmunitionScatter:
    def test_dpicm_scatters(self) -> None:
        eng = _make_damage_engine(rng=make_rng(42))
        ammo = _make_dpicm_ammo(submunition_lethal_radius_m=40.0)
        targets = {"tgt1": Position(0, 0, 0)}
        results = eng.resolve_submunition_damage(
            ammo, Position(0, 0, 0), targets,
        )
        # With 72 submunitions scattered around (0,0) and 40m lethal radius, some should hit
        assert "tgt1" in results
        assert results["tgt1"].damage_fraction > 0

    def test_distant_targets_unharmed(self) -> None:
        eng = _make_damage_engine(rng=make_rng(50))
        ammo = _make_dpicm_ammo()
        targets = {"far": Position(5000, 5000, 0)}
        results = eng.resolve_submunition_damage(
            ammo, Position(0, 0, 0), targets,
        )
        # Very far target should not be hit
        assert "far" not in results or results["far"].damage_fraction == 0.0

    def test_lethal_radius(self) -> None:
        """Submunitions only damage targets within lethal radius."""
        eng = _make_damage_engine(rng=make_rng(60))
        ammo = _make_dpicm_ammo(submunition_lethal_radius_m=1.0)
        # Place target at edge of scatter
        targets = {"edge": Position(200, 200, 0)}
        results = eng.resolve_submunition_damage(
            ammo, Position(0, 0, 0), targets,
        )
        # Very tight lethal radius + distance = unlikely hit
        assert "edge" not in results or results["edge"].damage_fraction < 0.5

    def test_uxo_created(self) -> None:
        from stochastic_warfare.combat.damage import UXOEngine

        rng = make_rng(70)
        eng = _make_damage_engine(rng=rng)
        uxo = UXOEngine(rng=make_rng(71))
        ammo = _make_dpicm_ammo(uxo_rate=0.1)
        eng.resolve_submunition_damage(
            ammo, Position(0, 0, 0), {}, uxo_engine=uxo, timestamp=100.0,
        )
        assert len(uxo.get_fields()) == 1

    def test_no_submunitions_empty(self) -> None:
        eng = _make_damage_engine(rng=make_rng(80))
        ammo = _make_ammo_def()  # no submunitions
        results = eng.resolve_submunition_damage(
            ammo, Position(0, 0, 0), {"tgt": Position(0, 0, 0)},
        )
        assert len(results) == 0

    def test_sigma_config(self) -> None:
        """Different scatter sigma should change hit patterns."""
        hits_tight = 0
        hits_wide = 0
        for seed in range(50):
            eng_tight = _make_damage_engine(
                rng=make_rng(seed), submunition_scatter_sigma_fraction=0.1,
            )
            eng_wide = _make_damage_engine(
                rng=make_rng(seed), submunition_scatter_sigma_fraction=2.0,
            )
            ammo = _make_dpicm_ammo()
            targets = {"tgt": Position(0, 0, 0)}
            r_tight = eng_tight.resolve_submunition_damage(ammo, Position(0, 0, 0), targets)
            r_wide = eng_wide.resolve_submunition_damage(ammo, Position(0, 0, 0), targets)
            if "tgt" in r_tight:
                hits_tight += 1
            if "tgt" in r_wide:
                hits_wide += 1
        # Tighter scatter should hit more at the center
        assert hits_tight >= hits_wide

    def test_multiple_targets(self) -> None:
        eng = _make_damage_engine(rng=make_rng(90))
        ammo = _make_dpicm_ammo(submunition_count=200)
        targets = {
            "a": Position(0, 0, 0),
            "b": Position(10, 10, 0),
            "c": Position(20, 20, 0),
        }
        results = eng.resolve_submunition_damage(ammo, Position(10, 10, 0), targets)
        # Center target most likely hit
        assert "b" in results

    def test_zero_uxo_rate_no_field(self) -> None:
        from stochastic_warfare.combat.damage import UXOEngine

        rng = make_rng(100)
        eng = _make_damage_engine(rng=rng)
        uxo = UXOEngine(rng=make_rng(101))
        ammo = _make_dpicm_ammo(uxo_rate=0.0)
        eng.resolve_submunition_damage(
            ammo, Position(0, 0, 0), {}, uxo_engine=uxo, timestamp=100.0,
        )
        assert len(uxo.get_fields()) == 0

    def test_damage_accumulates(self) -> None:
        """Multiple submunitions hitting same target accumulate damage."""
        eng = _make_damage_engine(rng=make_rng(110))
        ammo = _make_dpicm_ammo(
            submunition_count=500, submunition_lethal_radius_m=50.0,
        )
        targets = {"tgt": Position(0, 0, 0)}
        results = eng.resolve_submunition_damage(ammo, Position(0, 0, 0), targets)
        assert "tgt" in results
        # Many hits should accumulate to near 1.0
        assert results["tgt"].damage_fraction > 0.3


# ---------------------------------------------------------------------------
# 3. Multi-spectral CM stacking
# ---------------------------------------------------------------------------


class TestMultiSpectralCM:
    def test_single_matches_old(self) -> None:
        """Single CM type should match old behavior."""
        eng = _make_air_combat_engine(rng=make_rng(1))
        red = eng.apply_countermeasures_multi("RADAR", ["chaff"])
        assert 0 < red < 1.0

    def test_chaff_flare_stacks(self) -> None:
        eng = _make_air_combat_engine(rng=make_rng(2))
        single = eng.apply_countermeasures_multi("IR", ["flare"])
        combined = eng.apply_countermeasures_multi("IR", ["flare", "dircm"])
        assert combined >= single

    def test_dircm_ir(self) -> None:
        eng = _make_air_combat_engine(rng=make_rng(3), dircm_effectiveness=0.8)
        red = eng.apply_countermeasures_multi("IR", ["dircm"])
        assert red > 0

    def test_mismatch_minimal(self) -> None:
        """Chaff against IR seeker should give minimal reduction."""
        eng = _make_air_combat_engine(rng=make_rng(4))
        red = eng.apply_countermeasures_multi("IR", ["chaff"])
        assert red < 0.2

    def test_combined_formula(self) -> None:
        """Combined = 1 - product(1 - individual)."""
        eng = _make_air_combat_engine(rng=make_rng(5))
        r1 = eng.apply_countermeasures_multi("RADAR", ["chaff"])
        r2 = eng.apply_countermeasures_multi("RADAR", ["chaff", "chaff"])
        # Two chaff: combined = 1 - (1-r1)^2
        expected = 1.0 - (1.0 - r1) ** 2
        assert abs(r2 - expected) < 0.01

    def test_empty_list(self) -> None:
        eng = _make_air_combat_engine(rng=make_rng(6))
        red = eng.apply_countermeasures_multi("RADAR", [])
        assert red == 0.0


# ---------------------------------------------------------------------------
# 4. TOT synchronization
# ---------------------------------------------------------------------------


class TestTOTSync:
    def test_correct_fire_times(self) -> None:
        eng = _make_indirect_fire_engine(rng=make_rng(1))
        weapon = _make_howitzer_def()
        ammo = _make_he_ammo()
        batteries = {
            "bat_a": Position(0, 0, 0),
            "bat_b": Position(5000, 0, 0),
        }
        plan = eng.compute_tot_plan(
            Position(10000, 0, 0), batteries, weapon, ammo, 1000.0,
        )
        assert "bat_a" in plan.fire_times
        assert "bat_b" in plan.fire_times
        # Both should fire before impact time
        assert plan.fire_times["bat_a"] < plan.impact_time_s
        assert plan.fire_times["bat_b"] < plan.impact_time_s

    def test_closer_fires_later(self) -> None:
        """Closer battery has shorter ToF so fires later."""
        eng = _make_indirect_fire_engine(rng=make_rng(2), tot_time_of_flight_variation_s=0.0)
        weapon = _make_howitzer_def()
        ammo = _make_he_ammo()
        batteries = {
            "far": Position(0, 0, 0),
            "close": Position(9000, 0, 0),
        }
        plan = eng.compute_tot_plan(
            Position(10000, 0, 0), batteries, weapon, ammo, 1000.0,
        )
        # Close battery fires later (shorter ToF)
        assert plan.fire_times["close"] > plan.fire_times["far"]

    def test_jitter(self) -> None:
        """Non-zero variation adds jitter to ToF."""
        results_a = []
        results_b = []
        for seed in range(20):
            eng = _make_indirect_fire_engine(
                rng=make_rng(seed), tot_time_of_flight_variation_s=5.0,
            )
            weapon = _make_howitzer_def()
            ammo = _make_he_ammo()
            plan = eng.compute_tot_plan(
                Position(10000, 0, 0), {"bat": Position(0, 0, 0)},
                weapon, ammo, 1000.0,
            )
            results_a.append(plan.fire_times["bat"])
        # Fire times should vary
        assert max(results_a) - min(results_a) > 1.0

    def test_execute_fires_ready(self) -> None:
        eng = _make_indirect_fire_engine(rng=make_rng(3))
        weapon = _make_howitzer_def()
        ammo = _make_he_ammo()
        batteries = {"bat_a": Position(0, 0, 0)}
        plan = eng.compute_tot_plan(
            Position(10000, 0, 0), batteries, weapon, ammo, 1000.0,
        )
        # Execute at impact_time (all batteries should have fired)
        results = eng.execute_tot_mission(
            plan, {"bat_a": weapon}, ammo, 5, plan.impact_time_s,
        )
        assert len(results) == 1
        assert results[0].rounds_fired == 5

    def test_execute_before_fire_time(self) -> None:
        eng = _make_indirect_fire_engine(rng=make_rng(4))
        weapon = _make_howitzer_def()
        ammo = _make_he_ammo()
        batteries = {"bat_a": Position(0, 0, 0)}
        plan = eng.compute_tot_plan(
            Position(10000, 0, 0), batteries, weapon, ammo, 1000.0,
        )
        # Execute way before fire time — nothing fires
        results = eng.execute_tot_mission(
            plan, {"bat_a": weapon}, ammo, 5, -1000.0,
        )
        assert len(results) == 0

    def test_single_battery(self) -> None:
        eng = _make_indirect_fire_engine(rng=make_rng(5))
        weapon = _make_howitzer_def()
        ammo = _make_he_ammo()
        plan = eng.compute_tot_plan(
            Position(10000, 0, 0), {"solo": Position(0, 0, 0)},
            weapon, ammo, 500.0,
        )
        assert len(plan.batteries) == 1
        assert "solo" in plan.fire_times

    def test_max_battery_limit(self) -> None:
        eng = _make_indirect_fire_engine(rng=make_rng(6), tot_max_batteries=3)
        weapon = _make_howitzer_def()
        ammo = _make_he_ammo()
        batteries = {f"bat_{i}": Position(i * 1000, 0, 0) for i in range(10)}
        plan = eng.compute_tot_plan(
            Position(20000, 0, 0), batteries, weapon, ammo, 2000.0,
        )
        assert len(plan.batteries) == 3

    def test_all_batteries_fire(self) -> None:
        eng = _make_indirect_fire_engine(rng=make_rng(7))
        weapon = _make_howitzer_def()
        ammo = _make_he_ammo()
        batteries = {
            "a": Position(0, 0, 0),
            "b": Position(5000, 0, 0),
            "c": Position(8000, 0, 0),
        }
        plan = eng.compute_tot_plan(
            Position(15000, 0, 0), batteries, weapon, ammo, 2000.0,
        )
        weapons_map = {bid: weapon for bid in batteries}
        results = eng.execute_tot_mission(
            plan, weapons_map, ammo, 3, plan.impact_time_s,
        )
        assert len(results) == 3

    def test_tot_config_defaults(self) -> None:
        from stochastic_warfare.combat.indirect_fire import IndirectFireConfig

        cfg = IndirectFireConfig()
        assert cfg.tot_max_batteries == 6
        assert cfg.tot_time_of_flight_variation_s == 2.0

    def test_plan_fields(self) -> None:
        eng = _make_indirect_fire_engine(rng=make_rng(8))
        weapon = _make_howitzer_def()
        ammo = _make_he_ammo()
        plan = eng.compute_tot_plan(
            Position(10000, 0, 0), {"bat": Position(0, 0, 0)},
            weapon, ammo, 1000.0,
        )
        assert plan.target_pos == Position(10000, 0, 0)
        assert plan.impact_time_s == 1000.0
        assert "bat" in plan.time_of_flight


# ---------------------------------------------------------------------------
# 5. CAS designation
# ---------------------------------------------------------------------------


class TestCASDesignation:
    def test_no_jtac_no_bonus(self) -> None:
        eng = _make_air_ground_engine(rng=make_rng(1))
        result = eng.compute_cas_designation(jtac_present=False)
        assert result.accuracy_bonus == 0.0

    def test_jtac_increases_bonus(self) -> None:
        eng = _make_air_ground_engine(rng=make_rng(2))
        result = eng.compute_cas_designation(jtac_present=True, elapsed_since_contact_s=60.0)
        assert result.accuracy_bonus > 0

    def test_laser_bonus(self) -> None:
        eng = _make_air_ground_engine(rng=make_rng(3))
        r_no_laser = eng.compute_cas_designation(
            jtac_present=True, laser_designator=False, elapsed_since_contact_s=60.0,
        )
        r_laser = eng.compute_cas_designation(
            jtac_present=True, laser_designator=True, elapsed_since_contact_s=60.0,
        )
        assert r_laser.accuracy_bonus >= r_no_laser.accuracy_bonus

    def test_delay_enforced(self) -> None:
        """Before designation delay, no bonus."""
        eng = _make_air_ground_engine(
            rng=make_rng(4), jtac_designation_delay_s=30.0,
        )
        result = eng.compute_cas_designation(
            jtac_present=True, elapsed_since_contact_s=5.0,
        )
        assert result.accuracy_bonus == 0.0

    def test_talk_on_ramp(self) -> None:
        """Bonus ramps up with time (talk-on latency)."""
        eng = _make_air_ground_engine(rng=make_rng(5))
        r_early = eng.compute_cas_designation(
            jtac_present=True, elapsed_since_contact_s=20.0,
        )
        r_late = eng.compute_cas_designation(
            jtac_present=True, elapsed_since_contact_s=120.0,
        )
        assert r_late.accuracy_bonus >= r_early.accuracy_bonus

    def test_comm_quality(self) -> None:
        eng = _make_air_ground_engine(rng=make_rng(6))
        r_good = eng.compute_cas_designation(
            jtac_present=True, elapsed_since_contact_s=60.0, comm_quality=1.0,
        )
        r_poor = eng.compute_cas_designation(
            jtac_present=True, elapsed_since_contact_s=60.0, comm_quality=0.2,
        )
        assert r_good.accuracy_bonus >= r_poor.accuracy_bonus

    def test_result_fields(self) -> None:
        eng = _make_air_ground_engine(rng=make_rng(7))
        result = eng.compute_cas_designation(
            jtac_present=True, laser_designator=True, elapsed_since_contact_s=60.0,
        )
        assert hasattr(result, "accuracy_bonus")
        assert hasattr(result, "designation_delay_s")


# ---------------------------------------------------------------------------
# 6. Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompat27b:
    def test_engagement_config_defaults(self) -> None:
        from stochastic_warfare.combat.engagement import EngagementConfig

        cfg = EngagementConfig()
        assert cfg.enable_burst_fire is False
        assert cfg.max_burst_size == 10

    def test_damage_config_defaults(self) -> None:
        from stochastic_warfare.combat.damage import DamageConfig

        cfg = DamageConfig()
        assert cfg.enable_submunition_scatter is False
        assert cfg.submunition_scatter_sigma_fraction == 0.7

    def test_indirect_fire_config_defaults(self) -> None:
        from stochastic_warfare.combat.indirect_fire import IndirectFireConfig

        cfg = IndirectFireConfig()
        assert cfg.tot_max_batteries == 6
        assert cfg.tot_time_of_flight_variation_s == 2.0

    def test_air_combat_config_defaults(self) -> None:
        from stochastic_warfare.combat.air_combat import AirCombatConfig

        cfg = AirCombatConfig()
        assert cfg.dircm_effectiveness == 0.5
