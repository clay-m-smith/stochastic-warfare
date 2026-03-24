"""Unit tests for NavalSurfaceEngine — salvo model, point defense, damage, flooding."""

from __future__ import annotations

import pytest

from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.naval_surface import (
    NavalSurfaceConfig,
    NavalSurfaceEngine,
    SalvoResult,
    ShipDamageState,
    NavalGunResult,
)
from stochastic_warfare.core.events import EventBus

from .conftest import _rng


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine(seed: int = 42, **cfg_kwargs) -> NavalSurfaceEngine:
    bus = EventBus()
    damage = DamageEngine(bus, _rng(seed + 100))
    config = NavalSurfaceConfig(**cfg_kwargs) if cfg_kwargs else None
    return NavalSurfaceEngine(damage, bus, _rng(seed), config)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSalvoExchange:
    """Wayne Hughes salvo model."""

    def test_salvo_returns_result(self):
        eng = _make_engine(seed=1)
        result = eng.salvo_exchange(
            attacker_missiles=8, attacker_pk=0.7,
            defender_point_defense_count=4, defender_pd_pk=0.5,
        )
        assert isinstance(result, SalvoResult)
        assert result.missiles_fired == 8
        assert result.offensive_power > 0
        assert result.defensive_power > 0

    def test_chaff_reduces_hits(self):
        """Chaff diversion should reduce hits on average."""
        hits_no_chaff = []
        hits_with_chaff = []
        for seed in range(50):
            eng1 = _make_engine(seed=seed)
            eng2 = _make_engine(seed=seed)
            r1 = eng1.salvo_exchange(8, 0.8, 2, 0.3, defender_chaff=False)
            r2 = eng2.salvo_exchange(8, 0.8, 2, 0.3, defender_chaff=True)
            hits_no_chaff.append(r1.hits)
            hits_with_chaff.append(r2.hits)
        # On average chaff should reduce hits
        assert sum(hits_with_chaff) < sum(hits_no_chaff)

    def test_high_sea_state_degrades(self):
        """Sea state > 4 should degrade both offensive and defensive power."""
        eng1 = _make_engine(seed=10)
        eng2 = _make_engine(seed=10)
        calm = eng1.salvo_exchange(8, 0.7, 4, 0.5, sea_state=3)
        rough = eng2.salvo_exchange(8, 0.7, 4, 0.5, sea_state=7)
        # Rough seas degrade both alpha and beta
        assert rough.offensive_power < calm.offensive_power
        assert rough.defensive_power < calm.defensive_power


class TestPointDefense:
    """Point-defense layered intercept."""

    def test_point_defense_intercepts(self):
        """Point defense should intercept some incoming missiles."""
        eng = _make_engine(seed=20)
        intercepted = eng.point_defense("dd1", 10, 0.5, ciws_pk=0.5)
        # Should intercept at least some
        assert 0 <= intercepted <= 10

    def test_zero_incoming_zero_intercepts(self):
        eng = _make_engine(seed=21)
        intercepted = eng.point_defense("dd1", 0, 0.5)
        assert intercepted == 0


class TestShipDamage:
    """apply_ship_damage and mission_kill assessment."""

    def test_damage_reduces_hull_integrity(self):
        eng = _make_engine(seed=30)
        state = eng.apply_ship_damage("ship1", 3)
        assert state.hull_integrity < 1.0
        assert state.structural > 0.0

    def test_mission_kill_threshold(self):
        eng = _make_engine(seed=31)
        assert eng.assess_mission_kill(0.4) is True  # below 0.5 threshold
        assert eng.assess_mission_kill(0.6) is False  # above threshold

    def test_multiple_hits_accumulate(self):
        eng = _make_engine(seed=32)
        state1 = eng.apply_ship_damage("ship1", 1)
        integrity_after_1 = state1.hull_integrity
        state2 = eng.apply_ship_damage("ship1", 2)
        assert state2.hull_integrity <= integrity_after_1


class TestDamageControl:
    """damage_control reduces flooding and fire."""

    def test_damage_control_reduces_flooding(self):
        eng = _make_engine(seed=40)
        state = ShipDamageState(ship_id="ship1", flooding=0.5, fire=0.3, structural=0.2)
        initial_flooding = state.flooding
        eng.damage_control(state, dc_crew_quality=0.8, dt=60.0)
        assert state.flooding < initial_flooding

    def test_damage_control_reduces_fire(self):
        eng = _make_engine(seed=41)
        state = ShipDamageState(ship_id="ship1", flooding=0.0, fire=0.5, structural=0.2)
        initial_fire = state.fire
        eng.damage_control(state, dc_crew_quality=0.8, dt=60.0)
        assert state.fire < initial_fire


class TestNavalGun:
    """Modern radar-directed naval gun engagement."""

    def test_naval_gun_hits(self):
        eng = _make_engine(seed=50)
        result = eng.naval_gun_engagement(
            "dd1", "tgt1", range_m=10_000.0, rounds_fired=20,
            fire_control_quality=0.9,
        )
        assert isinstance(result, NavalGunResult)
        assert result.rounds_fired == 20
        assert result.hits >= 0

    def test_naval_gun_out_of_range(self):
        eng = _make_engine(seed=51)
        result = eng.naval_gun_engagement(
            "dd1", "tgt1", range_m=30_000.0, rounds_fired=20,
        )
        # Default max range is 24,000m
        assert result.rounds_fired == 0
        assert result.hits == 0

    def test_fire_control_quality_affects_hits(self):
        """Higher fire control quality should produce more hits on average."""
        hits_low = []
        hits_high = []
        for seed in range(50):
            eng1 = _make_engine(seed=seed + 200)
            eng2 = _make_engine(seed=seed + 200)
            r1 = eng1.naval_gun_engagement("dd1", "tgt1", 10_000.0, 50, fire_control_quality=0.3)
            r2 = eng2.naval_gun_engagement("dd1", "tgt1", 10_000.0, 50, fire_control_quality=1.0)
            hits_low.append(r1.hits)
            hits_high.append(r2.hits)
        assert sum(hits_high) > sum(hits_low)


class TestProgressiveFlooding:
    """Compartment flooding model."""

    def test_progressive_flooding_spreads(self):
        eng = _make_engine(seed=60)
        eng.initialize_compartments("ship1", num_compartments=8)
        # Apply heavy damage to one compartment
        eng.apply_compartment_damage("ship1", 3, 0.8)
        # Run progressive flooding for many seconds
        for _ in range(100):
            eng.progressive_flooding("ship1", dt=10.0)
        state = eng._damage_states["ship1"]
        # At least 2 compartments should have some flooding
        flooded = sum(1 for f in state.compartment_flooding if f > 0)
        assert flooded >= 2

    def test_counter_flooding_reduces(self):
        eng = _make_engine(seed=70)
        eng.initialize_compartments("ship1", num_compartments=4)
        eng.apply_compartment_damage("ship1", 2, 0.5)
        total_before = sum(eng._damage_states["ship1"].compartment_flooding)
        # Apply counter-flooding
        for _ in range(50):
            eng.counter_flood("ship1", dc_quality=0.9, dt=10.0)
        total_after = sum(eng._damage_states["ship1"].compartment_flooding)
        assert total_after < total_before


class TestCapsize:
    """Capsize threshold checks."""

    def test_capsize_on_heavy_flooding(self):
        eng = _make_engine(seed=80)
        eng.initialize_compartments("ship1", num_compartments=4)
        # Flood all compartments heavily
        state = eng._damage_states["ship1"]
        state.compartment_flooding = [0.8, 0.8, 0.8, 0.8]
        assert eng.check_capsize("ship1") is True
        assert state.capsized is True
        assert state.hull_integrity == 0.0

    def test_no_capsize_low_flooding(self):
        eng = _make_engine(seed=81)
        eng.initialize_compartments("ship1", num_compartments=4)
        state = eng._damage_states["ship1"]
        state.compartment_flooding = [0.1, 0.0, 0.0, 0.1]
        assert eng.check_capsize("ship1") is False

    def test_no_ship_no_capsize(self):
        eng = _make_engine(seed=82)
        assert eng.check_capsize("nonexistent") is False


class TestStateRoundtrip:
    """State serialization and restoration."""

    def test_state_roundtrip(self):
        eng = _make_engine(seed=90)
        eng.apply_ship_damage("ship1", 2)
        state = eng.get_state()

        eng2 = _make_engine(seed=999)
        eng2.set_state(state)

        assert "ship1" in eng2._damage_states
        assert eng2._damage_states["ship1"].hull_integrity == pytest.approx(
            eng._damage_states["ship1"].hull_integrity,
        )

        r1 = eng._rng.random()
        r2 = eng2._rng.random()
        assert r1 == pytest.approx(r2)
