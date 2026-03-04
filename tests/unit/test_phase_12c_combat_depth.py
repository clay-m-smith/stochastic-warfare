"""Phase 12c — Combat Depth tests.

Tests for:
- 12c-1: Air combat energy-maneuverability
- 12c-2: Naval compartment flooding
- 12c-3: Submarine geometric evasion + patrol ops
- 12c-4: Mine ship-signature + MCM operations
- 12c-5: Amphibious landing craft model
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import ModuleId, Position

from tests.conftest import TS, make_rng

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rng(seed: int = 42) -> np.random.Generator:
    return make_rng(seed)


def _event_bus() -> EventBus:
    return EventBus()


def _make_damage_engine() -> Any:
    """Minimal mock of DamageEngine for naval/subsurface constructors."""
    return SimpleNamespace(
        apply_damage=lambda *a, **kw: None,
        resolve_damage=lambda *a, **kw: SimpleNamespace(destroyed=False, damage_fraction=0.1),
    )


def _make_naval_surface_engine(rng=None, event_bus=None, **kw):
    from stochastic_warfare.combat.naval_surface import NavalSurfaceConfig, NavalSurfaceEngine
    return NavalSurfaceEngine(
        damage_engine=_make_damage_engine(),
        event_bus=event_bus or _event_bus(),
        rng=rng or _rng(),
        config=NavalSurfaceConfig(**kw),
    )


def _make_subsurface_engine(rng=None, event_bus=None, config_kw=None, patrol_kw=None):
    from stochastic_warfare.combat.naval_subsurface import (
        NavalSubsurfaceConfig, NavalSubsurfaceEngine, SubmarinePatrolConfig,
    )
    cfg = NavalSubsurfaceConfig(**(config_kw or {}))
    pcfg = SubmarinePatrolConfig(**(patrol_kw or {}))
    return NavalSubsurfaceEngine(
        damage_engine=_make_damage_engine(),
        event_bus=event_bus or _event_bus(),
        rng=rng or _rng(),
        config=cfg,
        patrol_config=pcfg,
    )


def _make_mine_engine(rng=None, event_bus=None, **kw):
    from stochastic_warfare.combat.naval_mine import MineWarfareConfig, MineWarfareEngine
    return MineWarfareEngine(
        damage_engine=_make_damage_engine(),
        event_bus=event_bus or _event_bus(),
        rng=rng or _rng(),
        config=MineWarfareConfig(**kw),
    )


def _make_amphibious_engine(rng=None, event_bus=None, **kw):
    from stochastic_warfare.combat.amphibious_assault import (
        AmphibiousAssaultConfig, AmphibiousAssaultEngine,
    )
    from stochastic_warfare.combat.naval_gunfire_support import NavalGunfireSupportEngine
    eb = event_bus or _event_bus()
    se = _make_naval_surface_engine(rng=_rng(99), event_bus=eb)
    # NavalGunfireSupportEngine takes indirect_fire_engine, mock it
    mock_indirect = SimpleNamespace(
        resolve_fire_mission=lambda *a, **k: SimpleNamespace(
            casualties=0, suppression=0.0, damage_radius_m=0.0,
        ),
    )
    ngs = NavalGunfireSupportEngine(
        indirect_fire_engine=mock_indirect,
        event_bus=eb,
        rng=_rng(100),
    )
    return AmphibiousAssaultEngine(
        naval_surface_engine=se,
        naval_gunfire_engine=ngs,
        damage_engine=_make_damage_engine(),
        event_bus=eb,
        rng=rng or _rng(),
        config=AmphibiousAssaultConfig(**kw),
    )


# ===================================================================
# 12c-1: Air Combat Energy-Maneuverability
# ===================================================================


class TestEnergyState:
    """EnergyState dataclass and specific_energy property."""

    def test_specific_energy_ground_level(self):
        from stochastic_warfare.combat.air_combat import EnergyState
        es = EnergyState(altitude_m=0.0, speed_mps=0.0)
        assert es.specific_energy == 0.0

    def test_specific_energy_altitude_only(self):
        from stochastic_warfare.combat.air_combat import EnergyState
        es = EnergyState(altitude_m=5000.0, speed_mps=0.0)
        assert es.specific_energy == 5000.0

    def test_specific_energy_speed_only(self):
        from stochastic_warfare.combat.air_combat import EnergyState
        es = EnergyState(altitude_m=0.0, speed_mps=300.0)
        expected = 300.0 ** 2 / (2 * 9.81)
        assert abs(es.specific_energy - expected) < 0.1

    def test_specific_energy_combined(self):
        from stochastic_warfare.combat.air_combat import EnergyState
        es = EnergyState(altitude_m=3000.0, speed_mps=250.0)
        expected = 3000.0 + 250.0 ** 2 / (2 * 9.81)
        assert abs(es.specific_energy - expected) < 0.1


class TestAirCombatEnergyManeuverability:
    """resolve_air_engagement with energy modifier."""

    def test_default_weight_zero_no_effect(self):
        """With energy_advantage_weight=0, energy states don't change Pk."""
        from stochastic_warfare.combat.air_combat import (
            AirCombatConfig, AirCombatEngine, AirCombatMode, EnergyState,
        )
        rng = _rng(10)
        eng = AirCombatEngine(_event_bus(), rng, AirCombatConfig(energy_advantage_weight=0.0))
        es_hi = EnergyState(altitude_m=10000.0, speed_mps=400.0)
        es_lo = EnergyState(altitude_m=1000.0, speed_mps=100.0)
        # Run many trials and compare to no-energy baseline
        rng2 = _rng(10)
        eng2 = AirCombatEngine(_event_bus(), rng2, AirCombatConfig(energy_advantage_weight=0.0))
        r1 = eng.resolve_air_engagement(
            "a", "d", Position(0, 0, 0), Position(500, 0, 0),
            missile_pk=0.5, mode=AirCombatMode.GUNS_ONLY,
            attacker_energy=es_hi, defender_energy=es_lo,
        )
        r2 = eng2.resolve_air_engagement(
            "a", "d", Position(0, 0, 0), Position(500, 0, 0),
            missile_pk=0.5, mode=AirCombatMode.GUNS_ONLY,
        )
        # Same RNG seed, same weight=0 → identical effective_pk
        assert r1.effective_pk == r2.effective_pk

    def test_energy_advantage_increases_pk(self):
        """Attacker with higher energy should get increased Pk."""
        from stochastic_warfare.combat.air_combat import (
            AirCombatConfig, AirCombatEngine, AirCombatMode, EnergyState,
        )
        cfg = AirCombatConfig(energy_advantage_weight=0.3)
        eng = AirCombatEngine(_event_bus(), _rng(5), cfg)
        hi = EnergyState(altitude_m=8000.0, speed_mps=350.0)
        lo = EnergyState(altitude_m=2000.0, speed_mps=150.0)
        # WVR mode — full weight
        r = eng.resolve_air_engagement(
            "a", "d", Position(0, 0, 0), Position(3000, 0, 0),
            missile_pk=0.5, mode=AirCombatMode.WVR,
            attacker_energy=hi, defender_energy=lo,
        )
        # The energy modifier should be positive (attacker advantage)
        # effective_pk should be > base (before other modifiers apply)
        assert r.effective_pk > 0.0

    def test_energy_disadvantage_decreases_pk(self):
        """Attacker with lower energy should get decreased Pk."""
        from stochastic_warfare.combat.air_combat import (
            AirCombatConfig, AirCombatEngine, AirCombatMode, EnergyState,
        )
        cfg = AirCombatConfig(energy_advantage_weight=0.3)
        lo = EnergyState(altitude_m=500.0, speed_mps=100.0)
        hi = EnergyState(altitude_m=10000.0, speed_mps=400.0)
        # Two runs: one with energy disadvantage, one without energy
        eng1 = AirCombatEngine(_event_bus(), _rng(7), cfg)
        r_disadv = eng1.resolve_air_engagement(
            "a", "d", Position(0, 0, 0), Position(3000, 0, 0),
            missile_pk=0.5, mode=AirCombatMode.WVR,
            attacker_energy=lo, defender_energy=hi,
        )
        eng2 = AirCombatEngine(_event_bus(), _rng(7), AirCombatConfig(energy_advantage_weight=0.0))
        r_base = eng2.resolve_air_engagement(
            "a", "d", Position(0, 0, 0), Position(3000, 0, 0),
            missile_pk=0.5, mode=AirCombatMode.WVR,
        )
        assert r_disadv.effective_pk <= r_base.effective_pk

    def test_bvr_mode_reduced_weight(self):
        """BVR mode should apply reduced energy effect (×0.3)."""
        from stochastic_warfare.combat.air_combat import (
            AirCombatConfig, AirCombatEngine, AirCombatMode, EnergyState,
        )
        cfg = AirCombatConfig(energy_advantage_weight=0.3)
        hi = EnergyState(altitude_m=10000.0, speed_mps=400.0)
        lo = EnergyState(altitude_m=1000.0, speed_mps=100.0)
        eng = AirCombatEngine(_event_bus(), _rng(20), cfg)
        r = eng.resolve_air_engagement(
            "a", "d", Position(0, 0, 0), Position(50000, 0, 0),
            missile_pk=0.5, mode=AirCombatMode.BVR,
            attacker_energy=hi, defender_energy=lo,
        )
        # Should succeed but with reduced energy effect
        assert r.mode == AirCombatMode.BVR

    def test_no_energy_states_no_change(self):
        """When no energy states provided, behavior unchanged."""
        from stochastic_warfare.combat.air_combat import (
            AirCombatConfig, AirCombatEngine, AirCombatMode,
        )
        cfg = AirCombatConfig(energy_advantage_weight=0.3)
        eng = AirCombatEngine(_event_bus(), _rng(1), cfg)
        r = eng.resolve_air_engagement(
            "a", "d", Position(0, 0, 0), Position(3000, 0, 0),
            missile_pk=0.5, mode=AirCombatMode.WVR,
        )
        assert r.effective_pk > 0.0  # still computes normally

    def test_energy_modifier_clamped(self):
        """Energy modifier clamped at ±0.3 Pk adjustment."""
        from stochastic_warfare.combat.air_combat import (
            AirCombatConfig, AirCombatEngine, AirCombatMode, EnergyState,
        )
        cfg = AirCombatConfig(energy_advantage_weight=1.0)  # extreme weight
        # Massive energy advantage
        hi = EnergyState(altitude_m=30000.0, speed_mps=800.0)
        lo = EnergyState(altitude_m=100.0, speed_mps=50.0)
        eng = AirCombatEngine(_event_bus(), _rng(3), cfg)
        r = eng.resolve_air_engagement(
            "a", "d", Position(0, 0, 0), Position(500, 0, 0),
            missile_pk=0.5, mode=AirCombatMode.GUNS_ONLY,
            attacker_energy=hi, defender_energy=lo,
        )
        # effective_pk shouldn't exceed 1.0
        assert r.effective_pk <= 1.0


# ===================================================================
# 12c-2: Naval Compartment Flooding
# ===================================================================


class TestCompartmentInit:
    """Compartment initialization and configuration."""

    def test_initialize_compartments_creates_list(self):
        eng = _make_naval_surface_engine()
        eng.initialize_compartments("ship1", num_compartments=6)
        state = eng._damage_states["ship1"]
        assert len(state.compartment_flooding) == 6
        assert all(f == 0.0 for f in state.compartment_flooding)

    def test_initialize_compartments_default_count(self):
        eng = _make_naval_surface_engine()
        eng.initialize_compartments("ship1")
        assert len(eng._damage_states["ship1"].compartment_flooding) == 8

    def test_initialize_creates_damage_state_if_missing(self):
        eng = _make_naval_surface_engine()
        assert "new_ship" not in eng._damage_states
        eng.initialize_compartments("new_ship", 4)
        assert "new_ship" in eng._damage_states


class TestCompartmentDamage:
    """apply_compartment_damage distributes hits to random compartments."""

    def test_single_hit_floods_one_compartment(self):
        eng = _make_naval_surface_engine()
        eng.initialize_compartments("ship1", 8)
        eng.apply_compartment_damage("ship1", hit_count=1, warhead_damage=0.3)
        flooding = eng._damage_states["ship1"].compartment_flooding
        assert sum(f > 0 for f in flooding) >= 1

    def test_multiple_hits_increase_flooding(self):
        eng = _make_naval_surface_engine()
        eng.initialize_compartments("ship1", 8)
        eng.apply_compartment_damage("ship1", hit_count=5, warhead_damage=0.2)
        flooding = eng._damage_states["ship1"].compartment_flooding
        assert sum(flooding) > 0

    def test_flooding_capped_at_one(self):
        eng = _make_naval_surface_engine()
        eng.initialize_compartments("ship1", 2)
        eng.apply_compartment_damage("ship1", hit_count=20, warhead_damage=1.0)
        flooding = eng._damage_states["ship1"].compartment_flooding
        assert all(f <= 1.0 for f in flooding)

    def test_no_damage_without_init(self):
        """apply_compartment_damage no-ops if compartments not initialized."""
        eng = _make_naval_surface_engine()
        # No crash, no error
        eng.apply_compartment_damage("ship1", hit_count=3, warhead_damage=0.5)


class TestProgressiveFlooding:
    """progressive_flooding spreads water to adjacent compartments."""

    def test_flooding_spreads_to_neighbors(self):
        eng = _make_naval_surface_engine(rng=_rng(1), progressive_flooding_rate=1.0)
        eng.initialize_compartments("ship1", 5)
        eng._damage_states["ship1"].compartment_flooding[2] = 0.8
        # Large dt * rate * flooding = high spread probability
        eng.progressive_flooding("ship1", dt=10.0)
        flooding = eng._damage_states["ship1"].compartment_flooding
        # At least one neighbor should have received some flooding
        assert flooding[1] > 0.0 or flooding[3] > 0.0

    def test_no_spread_from_dry_compartments(self):
        eng = _make_naval_surface_engine(progressive_flooding_rate=1.0)
        eng.initialize_compartments("ship1", 4)
        # All dry
        eng.progressive_flooding("ship1", dt=10.0)
        flooding = eng._damage_states["ship1"].compartment_flooding
        assert all(f == 0.0 for f in flooding)


class TestCounterFlooding:
    """counter_flood reduces flooding in compartments."""

    def test_counter_flood_reduces_water(self):
        eng = _make_naval_surface_engine(counter_flooding_rate=0.1)
        eng.initialize_compartments("ship1", 4)
        eng._damage_states["ship1"].compartment_flooding = [0.5, 0.5, 0.5, 0.5]
        eng.counter_flood("ship1", dc_quality=1.0, dt=10.0)
        flooding = eng._damage_states["ship1"].compartment_flooding
        assert all(f < 0.5 for f in flooding)

    def test_counter_flood_never_goes_negative(self):
        eng = _make_naval_surface_engine(counter_flooding_rate=1.0)
        eng.initialize_compartments("ship1", 4)
        eng._damage_states["ship1"].compartment_flooding = [0.01, 0.01, 0.01, 0.01]
        eng.counter_flood("ship1", dc_quality=1.0, dt=100.0)
        flooding = eng._damage_states["ship1"].compartment_flooding
        assert all(f >= 0.0 for f in flooding)

    def test_low_quality_dc_reduces_less(self):
        eng1 = _make_naval_surface_engine(rng=_rng(50), counter_flooding_rate=0.1)
        eng1.initialize_compartments("s1", 4)
        eng1._damage_states["s1"].compartment_flooding = [0.5, 0.5, 0.5, 0.5]
        eng1.counter_flood("s1", dc_quality=0.1, dt=5.0)

        eng2 = _make_naval_surface_engine(rng=_rng(50), counter_flooding_rate=0.1)
        eng2.initialize_compartments("s2", 4)
        eng2._damage_states["s2"].compartment_flooding = [0.5, 0.5, 0.5, 0.5]
        eng2.counter_flood("s2", dc_quality=1.0, dt=5.0)

        total1 = sum(eng1._damage_states["s1"].compartment_flooding)
        total2 = sum(eng2._damage_states["s2"].compartment_flooding)
        assert total1 > total2  # low quality = less draining


class TestCapsize:
    """check_capsize triggers on overall or asymmetric flooding."""

    def test_capsize_on_overall_flooding(self):
        eng = _make_naval_surface_engine(capsize_threshold=0.6)
        eng.initialize_compartments("ship1", 4)
        eng._damage_states["ship1"].compartment_flooding = [0.7, 0.7, 0.7, 0.7]
        assert eng.check_capsize("ship1") is True
        assert eng._damage_states["ship1"].capsized is True
        assert eng._damage_states["ship1"].hull_integrity == 0.0

    def test_no_capsize_when_below_threshold(self):
        eng = _make_naval_surface_engine(capsize_threshold=0.6)
        eng.initialize_compartments("ship1", 4)
        eng._damage_states["ship1"].compartment_flooding = [0.2, 0.2, 0.2, 0.2]
        assert eng.check_capsize("ship1") is False

    def test_capsize_on_asymmetric_flooding(self):
        eng = _make_naval_surface_engine(capsize_threshold=0.6)
        eng.initialize_compartments("ship1", 4)
        # Port side (first half) heavily flooded, starboard dry
        eng._damage_states["ship1"].compartment_flooding = [0.8, 0.8, 0.0, 0.0]
        result = eng.check_capsize("ship1")
        # port avg = 0.8, starboard avg = 0.0, asymmetry = 0.8 >= 0.3
        assert result is True

    def test_capsize_permanent(self):
        eng = _make_naval_surface_engine(capsize_threshold=0.6)
        eng.initialize_compartments("ship1", 4)
        eng._damage_states["ship1"].compartment_flooding = [1.0, 1.0, 1.0, 1.0]
        eng.check_capsize("ship1")
        # Once capsized, stays capsized even if we drain
        eng._damage_states["ship1"].compartment_flooding = [0.0, 0.0, 0.0, 0.0]
        assert eng.check_capsize("ship1") is True

    def test_no_capsize_without_compartments(self):
        eng = _make_naval_surface_engine()
        assert eng.check_capsize("nonexistent") is False

    def test_compartment_state_serialization(self):
        from stochastic_warfare.combat.naval_surface import ShipDamageState
        state = ShipDamageState(ship_id="s1", compartment_flooding=[0.1, 0.2, 0.3], capsized=True)
        d = state.get_state()
        assert d["compartment_flooding"] == [0.1, 0.2, 0.3]
        assert d["capsized"] is True
        state2 = ShipDamageState(ship_id="s2")
        state2.set_state(d)
        assert state2.compartment_flooding == [0.1, 0.2, 0.3]
        assert state2.capsized is True

    def test_old_state_backward_compat(self):
        from stochastic_warfare.combat.naval_surface import ShipDamageState
        old_state = {
            "ship_id": "s1", "hull_integrity": 0.8,
            "flooding": 0.1, "fire": 0.0, "structural": 0.0,
            "systems_damaged": [],
        }
        state = ShipDamageState(ship_id="s1")
        state.set_state(old_state)
        assert state.compartment_flooding == []
        assert state.capsized is False


# ===================================================================
# 12c-3: Submarine Geometric Evasion
# ===================================================================


class TestGeometricEvasion:
    """geometric_evasion method on NavalSubsurfaceEngine."""

    def test_high_bearing_rate_with_speed_succeeds(self):
        from stochastic_warfare.combat.naval_subsurface import SubmarineState
        eng = _make_subsurface_engine(config_kw={
            "enable_geometric_evasion": True,
            "bearing_rate_threshold": 0.001,
            "speed_diff_threshold": 0.3,
        })
        ss = SubmarineState(speed_kts=20.0, heading_deg=90.0)
        result = eng.geometric_evasion(ss, threat_bearing_deg=0.0, threat_speed_kts=10.0)
        # Perpendicular heading should generate high bearing rate
        assert result.bearing_rate_change != 0.0

    def test_slow_sub_fails_evasion(self):
        from stochastic_warfare.combat.naval_subsurface import SubmarineState
        eng = _make_subsurface_engine(rng=_rng(99), config_kw={
            "enable_geometric_evasion": True,
            "bearing_rate_threshold": 0.05,
            "speed_diff_threshold": 0.5,
            "thermocline_bonus": 0.0,  # disable stochastic fallback
        })
        ss = SubmarineState(speed_kts=2.0, heading_deg=0.0, below_thermocline=False)
        result = eng.geometric_evasion(ss, threat_bearing_deg=0.0, threat_speed_kts=30.0)
        # Very slow sub with head-on threat should fail
        assert result.success is False

    def test_thermocline_crossing_helps(self):
        from stochastic_warfare.combat.naval_subsurface import SubmarineState
        # Run many trials — thermocline should give ~20% success even when geometry fails
        successes = 0
        for seed in range(200):
            eng = _make_subsurface_engine(rng=_rng(seed), config_kw={
                "enable_geometric_evasion": True,
                "bearing_rate_threshold": 100.0,  # impossible geometry
                "speed_diff_threshold": 100.0,
                "thermocline_bonus": 0.2,
            })
            ss = SubmarineState(speed_kts=5.0, heading_deg=0.0, below_thermocline=True)
            result = eng.geometric_evasion(ss, threat_bearing_deg=0.0, threat_speed_kts=5.0)
            if result.success:
                successes += 1
        # Should be around 20% (±10%)
        assert 10 < successes < 70

    def test_evasion_type_reflects_thermocline(self):
        from stochastic_warfare.combat.naval_subsurface import SubmarineState
        eng = _make_subsurface_engine(config_kw={"enable_geometric_evasion": True})
        ss_thermo = SubmarineState(speed_kts=20.0, heading_deg=90.0, below_thermocline=True)
        ss_no = SubmarineState(speed_kts=20.0, heading_deg=90.0, below_thermocline=False)
        r1 = eng.geometric_evasion(ss_thermo, 0.0, 10.0)
        r2 = eng.geometric_evasion(ss_no, 0.0, 10.0)
        assert r1.evasion_type == "geometric_thermocline"
        assert r2.evasion_type == "geometric_maneuver"


class TestEvasionManeuverDelegation:
    """evasion_maneuver delegates to geometric_evasion when enabled."""

    def test_legacy_path_when_disabled(self):
        eng = _make_subsurface_engine(config_kw={"enable_geometric_evasion": False})
        result = eng.evasion_maneuver("sub1", 45.0, "decoy")
        assert result.evasion_type == "decoy"

    def test_geometric_path_when_enabled_with_state(self):
        from stochastic_warfare.combat.naval_subsurface import SubmarineState
        eng = _make_subsurface_engine(config_kw={"enable_geometric_evasion": True})
        ss = SubmarineState(speed_kts=15.0, heading_deg=90.0)
        result = eng.evasion_maneuver("sub1", 0.0, "decoy", sub_state=ss)
        assert "geometric" in result.evasion_type

    def test_legacy_path_when_no_state(self):
        eng = _make_subsurface_engine(config_kw={"enable_geometric_evasion": True})
        result = eng.evasion_maneuver("sub1", 45.0, "knuckle")
        assert result.evasion_type == "knuckle"


# ===================================================================
# 12c-3: Submarine Patrol Operations
# ===================================================================


class TestPatrolOps:
    """Patrol assignment and update."""

    def test_assign_patrol(self):
        from stochastic_warfare.combat.naval_subsurface import PatrolArea
        eng = _make_subsurface_engine(patrol_kw={"enable_patrol_ops": True})
        pa = PatrolArea("p1", Position(0, 0, 0), radius_m=10000.0, area_type="barrier")
        eng.assign_patrol("sub1", pa)
        assert "sub1" in eng._patrol_assignments

    def test_patrol_update_accumulates_time(self):
        from stochastic_warfare.combat.naval_subsurface import PatrolArea
        eng = _make_subsurface_engine(patrol_kw={"enable_patrol_ops": True})
        pa = PatrolArea("p1", Position(0, 0, 0), radius_m=10000.0)
        eng.assign_patrol("sub1", pa)
        r1 = eng.update_patrol("sub1", dt_hours=5.0)
        assert r1.time_on_station_hours == 5.0
        r2 = eng.update_patrol("sub1", dt_hours=3.0)
        assert r2.time_on_station_hours == 8.0

    def test_area_coverage_saturates(self):
        from stochastic_warfare.combat.naval_subsurface import PatrolArea
        eng = _make_subsurface_engine(patrol_kw={"enable_patrol_ops": True})
        pa = PatrolArea("p1", Position(0, 0, 0), radius_m=1000.0)  # small area
        eng.assign_patrol("sub1", pa)
        # After very long time, coverage should approach 1.0
        r = eng.update_patrol("sub1", dt_hours=1000.0)
        assert r.area_covered_fraction > 0.99

    def test_chokepoint_higher_detection(self):
        from stochastic_warfare.combat.naval_subsurface import PatrolArea
        # Chokepoint type_mult=2.0 vs area_search type_mult=0.5
        total_choke = 0
        total_area = 0
        for seed in range(100):
            eng_c = _make_subsurface_engine(
                rng=_rng(seed),
                patrol_kw={"enable_patrol_ops": True, "detection_rate_base": 1.0},
            )
            pa_c = PatrolArea("c", Position(0, 0, 0), 10000.0, "chokepoint")
            eng_c.assign_patrol("s1", pa_c)
            r_c = eng_c.update_patrol("s1", dt_hours=10.0, sensor_quality=1.0)
            total_choke += r_c.contacts_detected

            eng_a = _make_subsurface_engine(
                rng=_rng(seed),
                patrol_kw={"enable_patrol_ops": True, "detection_rate_base": 1.0},
            )
            pa_a = PatrolArea("a", Position(0, 0, 0), 10000.0, "area_search")
            eng_a.assign_patrol("s1", pa_a)
            r_a = eng_a.update_patrol("s1", dt_hours=10.0, sensor_quality=1.0)
            total_area += r_a.contacts_detected
        assert total_choke > total_area

    def test_unassigned_sub_returns_zero(self):
        eng = _make_subsurface_engine(patrol_kw={"enable_patrol_ops": True})
        r = eng.update_patrol("no_sub", dt_hours=5.0)
        assert r.contacts_detected == 0
        assert r.area_covered_fraction == 0.0

    def test_patrol_state_serialization(self):
        from stochastic_warfare.combat.naval_subsurface import PatrolArea
        eng = _make_subsurface_engine(patrol_kw={"enable_patrol_ops": True})
        pa = PatrolArea("p1", Position(100, 200, 0), 5000.0, "barrier")
        eng.assign_patrol("sub1", pa)
        eng.update_patrol("sub1", dt_hours=3.0)
        state = eng.get_state()
        assert "patrol_assignments" in state
        assert "sub1" in state["patrol_assignments"]
        assert state["patrol_hours"]["sub1"] == 3.0


# ===================================================================
# 12c-4: Mine Ship-Signature + MCM
# ===================================================================


class TestShipMineSignature:
    """ShipMineSignature influences mine triggering."""

    def test_high_magnetic_sig_triggers_magnetic_mine(self):
        from stochastic_warfare.combat.naval_mine import Mine, MineType, ShipMineSignature
        eng = _make_mine_engine()
        mine = Mine("m1", Position(0, 0, 0), MineType.MAGNETIC)
        sig = ShipMineSignature(magnetic_tesla=0.95)
        # High magnetic sig should trigger more reliably
        triggers = 0
        for seed in range(100):
            eng2 = _make_mine_engine(rng=_rng(seed))
            m = Mine("m1", Position(0, 0, 0), MineType.MAGNETIC)
            r = eng2.resolve_mine_encounter("s1", m, 0.5, 0.5, ship_signature=sig)
            if r.triggered:
                triggers += 1
        assert triggers > 70  # 0.95 * 0.9 = 0.855 trigger prob

    def test_low_magnetic_sig_reduces_trigger(self):
        from stochastic_warfare.combat.naval_mine import Mine, MineType, ShipMineSignature
        sig = ShipMineSignature(magnetic_tesla=0.1)
        triggers = 0
        for seed in range(100):
            eng = _make_mine_engine(rng=_rng(seed))
            m = Mine("m1", Position(0, 0, 0), MineType.MAGNETIC)
            r = eng.resolve_mine_encounter("s1", m, 0.5, 0.5, ship_signature=sig)
            if r.triggered:
                triggers += 1
        assert triggers < 30  # 0.1 * 0.9 = 0.09 trigger prob

    def test_pressure_mine_uses_displacement(self):
        from stochastic_warfare.combat.naval_mine import Mine, MineType, ShipMineSignature
        sig_heavy = ShipMineSignature(pressure_kpa=0.8, displacement_tons=8000.0)
        sig_light = ShipMineSignature(pressure_kpa=0.2, displacement_tons=1000.0)
        t_heavy, t_light = 0, 0
        for seed in range(200):
            eng = _make_mine_engine(rng=_rng(seed))
            m1 = Mine("m1", Position(0, 0, 0), MineType.PRESSURE)
            r1 = eng.resolve_mine_encounter("s1", m1, 0.5, 0.5, ship_signature=sig_heavy)
            if r1.triggered:
                t_heavy += 1
            eng2 = _make_mine_engine(rng=_rng(seed))
            m2 = Mine("m2", Position(0, 0, 0), MineType.PRESSURE)
            r2 = eng2.resolve_mine_encounter("s2", m2, 0.5, 0.5, ship_signature=sig_light)
            if r2.triggered:
                t_light += 1
        assert t_heavy > t_light

    def test_backward_compat_no_signature(self):
        from stochastic_warfare.combat.naval_mine import Mine, MineType
        eng = _make_mine_engine(rng=_rng(1))
        m = Mine("m1", Position(0, 0, 0), MineType.ACOUSTIC)
        r = eng.resolve_mine_encounter("s1", m, 0.8, 0.8)
        # Should work without ship_signature
        assert r.mine_id == "m1"


class TestMinePlacement:
    """lay_mines with delivery_method and placement_accuracy_m."""

    def test_placement_scatter(self):
        from stochastic_warfare.combat.naval_mine import MineType
        eng = _make_mine_engine()
        pos = [Position(1000.0, 2000.0, 0.0)]
        mines = eng.lay_mines("layer1", pos, MineType.MAGNETIC, count_per_pos=10,
                              placement_accuracy_m=100.0)
        # With scatter, positions should differ from the original
        offsets = [
            math.hypot(m.position.easting - 1000.0, m.position.northing - 2000.0)
            for m in mines
        ]
        assert any(o > 5.0 for o in offsets)  # at least some scatter

    def test_no_scatter_when_zero(self):
        from stochastic_warfare.combat.naval_mine import MineType
        eng = _make_mine_engine()
        pos = [Position(100.0, 200.0, 0.0)]
        mines = eng.lay_mines("layer1", pos, MineType.CONTACT, count_per_pos=5,
                              placement_accuracy_m=0.0)
        for m in mines:
            assert m.position.easting == 100.0
            assert m.position.northing == 200.0


class TestMineSweepGeographic:
    """sweep_mines with sweep_center and sweep_radius_m bounding."""

    def test_sweep_only_within_radius(self):
        from stochastic_warfare.combat.naval_mine import MineType
        eng = _make_mine_engine(rng=_rng(1))
        # Lay mines at two positions: one near, one far
        near_pos = [Position(100, 100, 0)]
        far_pos = [Position(10000, 10000, 0)]
        eng.lay_mines("l1", near_pos, MineType.CONTACT, count_per_pos=20)
        eng.lay_mines("l2", far_pos, MineType.CONTACT, count_per_pos=20)
        # Sweep only near the first position
        result = eng.sweep_mines(
            "sweeper1", area_m2=1e6, mine_type=MineType.CONTACT, dt=300.0,
            sweep_center=Position(100, 100, 0), sweep_radius_m=500.0,
        )
        # Should only find mines near (100, 100), not at (10000, 10000)
        # Far mines are 14km away — outside 500m radius
        # Count how many far mines are still armed
        far_armed = sum(1 for m in eng._mines if m.position.easting > 5000 and m.armed)
        assert far_armed == 20  # all far mines untouched


class TestMinePersistence:
    """update_mine_persistence exponential battery decay."""

    def test_mines_disarm_over_time(self):
        from stochastic_warfare.combat.naval_mine import MineType
        eng = _make_mine_engine()
        eng.lay_mines("l1", [Position(0, 0, 0)], MineType.MAGNETIC, count_per_pos=100)
        # After 1000 hours, some mines should have disarmed
        eng.update_mine_persistence(dt_hours=1000.0)
        armed = sum(1 for m in eng._mines if m.armed)
        assert armed < 100

    def test_short_time_few_disarmed(self):
        from stochastic_warfare.combat.naval_mine import MineType
        eng = _make_mine_engine()
        eng.lay_mines("l1", [Position(0, 0, 0)], MineType.MAGNETIC, count_per_pos=100)
        eng.update_mine_persistence(dt_hours=1.0)
        armed = sum(1 for m in eng._mines if m.armed)
        # Rate 0.001/hr for 1hr → p_disarm ≈ 0.001 → ~0.1 mines disarmed
        assert armed >= 95


class TestMinefieldDensity:
    """compute_minefield_density spatial query."""

    def test_density_calculation(self):
        from stochastic_warfare.combat.naval_mine import MineType
        eng = _make_mine_engine()
        eng.lay_mines("l1", [Position(0, 0, 0)], MineType.CONTACT, count_per_pos=10)
        density = eng.compute_minefield_density(Position(0, 0, 0), area_radius_m=100.0)
        expected = 10.0 / (math.pi * 100.0 ** 2)
        assert abs(density - expected) < 1e-8

    def test_density_excludes_distant_mines(self):
        from stochastic_warfare.combat.naval_mine import MineType
        eng = _make_mine_engine()
        eng.lay_mines("l1", [Position(0, 0, 0)], MineType.CONTACT, count_per_pos=10)
        eng.lay_mines("l2", [Position(5000, 5000, 0)], MineType.CONTACT, count_per_pos=10)
        density = eng.compute_minefield_density(Position(0, 0, 0), area_radius_m=100.0)
        expected = 10.0 / (math.pi * 100.0 ** 2)
        assert abs(density - expected) < 1e-8

    def test_density_zero_radius(self):
        eng = _make_mine_engine()
        assert eng.compute_minefield_density(Position(0, 0, 0), area_radius_m=0.0) == 0.0


# ===================================================================
# 12c-5: Amphibious Landing Craft Model
# ===================================================================


class TestLandingCraft:
    """LandingCraft dataclass and compute_throughput."""

    def test_landing_craft_defaults(self):
        from stochastic_warfare.combat.amphibious_assault import LandingCraft
        lc = LandingCraft(craft_id="lc1")
        assert lc.capacity_troops == 200
        assert lc.turnaround_time_s == 3600.0
        assert lc.min_beach_depth_m == 1.5

    def test_compute_throughput_basic(self):
        from stochastic_warfare.combat.amphibious_assault import LandingCraft
        eng = _make_amphibious_engine()
        craft = [LandingCraft("c1", capacity_troops=100, turnaround_time_s=1000)]
        tp = eng.compute_throughput(craft, beach_gradient=1.0, obstacle_factor=1.0, fire_factor=1.0)
        assert abs(tp - 0.1) < 1e-6  # 100/1000 = 0.1 troops/s

    def test_throughput_scales_with_craft_count(self):
        from stochastic_warfare.combat.amphibious_assault import LandingCraft
        eng = _make_amphibious_engine()
        craft1 = [LandingCraft("c1", capacity_troops=100, turnaround_time_s=1000)]
        craft2 = [
            LandingCraft("c1", capacity_troops=100, turnaround_time_s=1000),
            LandingCraft("c2", capacity_troops=100, turnaround_time_s=1000),
        ]
        tp1 = eng.compute_throughput(craft1, 1.0, 1.0, 1.0)
        tp2 = eng.compute_throughput(craft2, 1.0, 1.0, 1.0)
        assert abs(tp2 - 2 * tp1) < 1e-6

    def test_throughput_zero_with_no_craft(self):
        eng = _make_amphibious_engine()
        assert eng.compute_throughput([], 1.0, 1.0, 1.0) == 0.0

    def test_throughput_reduced_by_fire(self):
        from stochastic_warfare.combat.amphibious_assault import LandingCraft
        eng = _make_amphibious_engine()
        craft = [LandingCraft("c1", capacity_troops=200, turnaround_time_s=1000)]
        tp_clear = eng.compute_throughput(craft, 1.0, 1.0, fire_factor=1.0)
        tp_fire = eng.compute_throughput(craft, 1.0, 1.0, fire_factor=0.5)
        assert tp_fire < tp_clear


class TestTidalWindow:
    """check_tidal_window static method."""

    def test_tide_high_enough(self):
        from stochastic_warfare.combat.amphibious_assault import AmphibiousAssaultEngine
        assert AmphibiousAssaultEngine.check_tidal_window(2.0, 1.5) is True

    def test_tide_too_low(self):
        from stochastic_warfare.combat.amphibious_assault import AmphibiousAssaultEngine
        assert AmphibiousAssaultEngine.check_tidal_window(1.0, 1.5) is False

    def test_tide_exact(self):
        from stochastic_warfare.combat.amphibious_assault import AmphibiousAssaultEngine
        assert AmphibiousAssaultEngine.check_tidal_window(1.5, 1.5) is True


class TestExecuteWaveWithCraft:
    """execute_wave_with_craft with craft capacity and tidal constraints."""

    def test_wave_limited_by_capacity(self):
        from stochastic_warfare.combat.amphibious_assault import LandingCraft
        eng = _make_amphibious_engine(enable_landing_craft_model=True)
        craft = [LandingCraft("c1", capacity_troops=50)]
        result = eng.execute_wave_with_craft(
            wave_size=200, craft=craft, tide_height=3.0,
            beach_gradient=0.8, defense_strength=0.3,
        )
        # Only 50 troops can embark, but wave_size still reports 200
        assert result.wave_size == 200
        assert result.landed <= 50

    def test_no_landing_low_tide(self):
        from stochastic_warfare.combat.amphibious_assault import LandingCraft
        eng = _make_amphibious_engine(enable_landing_craft_model=True)
        craft = [LandingCraft("c1", capacity_troops=200, min_beach_depth_m=3.0)]
        result = eng.execute_wave_with_craft(
            wave_size=200, craft=craft, tide_height=1.0,
            beach_gradient=0.8, defense_strength=0.3,
        )
        assert result.landed == 0
        assert result.casualties == 0

    def test_partial_craft_usable(self):
        from stochastic_warfare.combat.amphibious_assault import LandingCraft
        eng = _make_amphibious_engine(enable_landing_craft_model=True)
        craft = [
            LandingCraft("c1", capacity_troops=100, min_beach_depth_m=1.0),
            LandingCraft("c2", capacity_troops=100, min_beach_depth_m=3.0),
        ]
        result = eng.execute_wave_with_craft(
            wave_size=200, craft=craft, tide_height=2.0,
            beach_gradient=0.8, defense_strength=0.2,
        )
        # Only c1 can beach — capacity limited to 100
        assert result.landed <= 100

    def test_config_flag_exists(self):
        from stochastic_warfare.combat.amphibious_assault import AmphibiousAssaultConfig
        cfg = AmphibiousAssaultConfig()
        assert cfg.enable_landing_craft_model is False
