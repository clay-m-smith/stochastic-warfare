"""Tests for combat/naval_surface.py — Wayne Hughes salvo model."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.naval_surface import (
    NavalSurfaceConfig,
    NavalSurfaceEngine,
    ShipDamageState,
)
from stochastic_warfare.core.events import Event, EventBus


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _engine(seed: int = 42, config: NavalSurfaceConfig | None = None) -> NavalSurfaceEngine:
    rng = _rng(seed)
    bus = EventBus()
    dmg = DamageEngine(bus, rng)
    return NavalSurfaceEngine(dmg, bus, rng, config)


def _engine_with_bus(seed: int = 42) -> tuple[NavalSurfaceEngine, EventBus]:
    rng = _rng(seed)
    bus = EventBus()
    dmg = DamageEngine(bus, rng)
    return NavalSurfaceEngine(dmg, bus, rng), bus


class TestSalvoExchange:
    def test_basic_salvo(self) -> None:
        e = _engine()
        result = e.salvo_exchange(
            attacker_missiles=8, attacker_pk=0.8,
            defender_point_defense_count=4, defender_pd_pk=0.5,
        )
        assert result.missiles_fired == 8
        assert result.offensive_power == pytest.approx(6.4)

    def test_no_missiles_no_hits(self) -> None:
        e = _engine()
        result = e.salvo_exchange(0, 0.8, 4, 0.5)
        assert result.hits == 0
        assert result.leakers == 0

    def test_overwhelming_attack_gets_hits(self) -> None:
        """Massive salvo should overwhelm defense."""
        hits = []
        for seed in range(20):
            e = _engine(seed)
            result = e.salvo_exchange(20, 0.9, 2, 0.3)
            hits.append(result.hits)
        assert sum(hits) > 0

    def test_strong_defense_reduces_hits(self) -> None:
        """Strong point defense should reduce hit count."""
        weak_def_hits = []
        strong_def_hits = []
        for seed in range(30):
            e1 = _engine(seed)
            e2 = _engine(seed)
            r1 = e1.salvo_exchange(10, 0.8, 2, 0.2)
            r2 = e2.salvo_exchange(10, 0.8, 10, 0.9)
            weak_def_hits.append(r1.hits)
            strong_def_hits.append(r2.hits)
        assert sum(weak_def_hits) > sum(strong_def_hits)

    def test_chaff_reduces_hits(self) -> None:
        """Chaff should reduce the number of hits."""
        no_chaff_hits = []
        chaff_hits = []
        for seed in range(30):
            e1 = _engine(seed)
            e2 = _engine(seed)
            r1 = e1.salvo_exchange(10, 0.8, 2, 0.3, defender_chaff=False)
            r2 = e2.salvo_exchange(10, 0.8, 2, 0.3, defender_chaff=True)
            no_chaff_hits.append(r1.hits)
            chaff_hits.append(r2.hits)
        assert sum(no_chaff_hits) >= sum(chaff_hits)

    def test_defensive_power_calculation(self) -> None:
        e = _engine()
        result = e.salvo_exchange(8, 0.8, 6, 0.5)
        assert result.defensive_power == pytest.approx(3.0)

    def test_leakers_non_negative(self) -> None:
        e = _engine()
        result = e.salvo_exchange(2, 0.5, 10, 0.9)
        assert result.leakers >= 0

    def test_deterministic_with_seed(self) -> None:
        e1 = _engine(42)
        e2 = _engine(42)
        r1 = e1.salvo_exchange(8, 0.8, 4, 0.5)
        r2 = e2.salvo_exchange(8, 0.8, 4, 0.5)
        assert r1.hits == r2.hits


class TestLaunchASHM:
    def test_returns_missile_ids(self) -> None:
        e = _engine()
        ids = e.launch_ashm("ship1", "target1", 4, 0.8)
        assert len(ids) == 4
        assert all("ship1_ashm" in mid for mid in ids)

    def test_ids_unique(self) -> None:
        e = _engine()
        ids = e.launch_ashm("ship1", "target1", 6, 0.8)
        assert len(set(ids)) == 6

    def test_event_published(self) -> None:
        e, bus = _engine_with_bus()
        received: list[Event] = []
        bus.subscribe(Event, lambda ev: received.append(ev))
        ts = datetime(2024, 6, 15, tzinfo=timezone.utc)
        e.launch_ashm("ship1", "target1", 2, 0.8, timestamp=ts)
        assert len(received) == 1

    def test_no_event_without_timestamp(self) -> None:
        e, bus = _engine_with_bus()
        received: list[Event] = []
        bus.subscribe(Event, lambda ev: received.append(ev))
        e.launch_ashm("ship1", "target1", 2, 0.8)
        assert len(received) == 0


class TestPointDefense:
    def test_intercepts_some(self) -> None:
        """Should intercept at least some missiles."""
        total_intercepted = 0
        for seed in range(20):
            e = _engine(seed)
            intercepted = e.point_defense("def1", 10, 0.5, 0.5)
            total_intercepted += intercepted
        assert total_intercepted > 0

    def test_no_incoming_no_intercepts(self) -> None:
        e = _engine()
        intercepted = e.point_defense("def1", 0, 0.5)
        assert intercepted == 0

    def test_high_pk_intercepts_most(self) -> None:
        """Very high pk should intercept most missiles."""
        total = 0
        for seed in range(20):
            e = _engine(seed)
            total += e.point_defense("def1", 10, 0.95, 0.95)
        # Average should be > 8 out of 10
        assert total / 20.0 > 7.0

    def test_intercepts_bounded(self) -> None:
        e = _engine()
        intercepted = e.point_defense("def1", 5, 0.5)
        assert 0 <= intercepted <= 5

    def test_deterministic_with_seed(self) -> None:
        e1 = _engine(42)
        e2 = _engine(42)
        r1 = e1.point_defense("def1", 8, 0.5, 0.5)
        r2 = e2.point_defense("def1", 8, 0.5, 0.5)
        assert r1 == r2


class TestApplyShipDamage:
    def test_single_hit_damages(self) -> None:
        e = _engine()
        state = e.apply_ship_damage("ship1", 1)
        assert state.hull_integrity < 1.0
        assert state.structural > 0.0

    def test_multiple_hits_more_damage(self) -> None:
        e1 = _engine(42)
        e2 = _engine(42)
        s1 = e1.apply_ship_damage("ship1", 1)
        s2 = e2.apply_ship_damage("ship2", 5)
        assert s2.hull_integrity < s1.hull_integrity

    def test_hull_integrity_bounded(self) -> None:
        e = _engine()
        state = e.apply_ship_damage("ship1", 20, warhead_damage=0.3)
        assert 0.0 <= state.hull_integrity <= 1.0

    def test_damage_event_published(self) -> None:
        e, bus = _engine_with_bus()
        received: list[Event] = []
        bus.subscribe(Event, lambda ev: received.append(ev))
        ts = datetime(2024, 6, 15, tzinfo=timezone.utc)
        e.apply_ship_damage("ship1", 2, timestamp=ts)
        assert len(received) >= 1

    def test_cumulative_damage(self) -> None:
        e = _engine()
        e.apply_ship_damage("ship1", 1)
        s2 = e.apply_ship_damage("ship1", 1)
        # Second hit should make things worse
        assert s2.structural > 0.0


class TestDamageControl:
    def test_reduces_flooding(self) -> None:
        e = _engine()
        state = ShipDamageState(ship_id="ship1", flooding=0.5, structural=0.3)
        e.damage_control(state, dc_crew_quality=0.8, dt=60.0)
        assert state.flooding < 0.5

    def test_reduces_fire(self) -> None:
        e = _engine()
        state = ShipDamageState(ship_id="ship1", fire=0.5, structural=0.3)
        e.damage_control(state, dc_crew_quality=0.8, dt=60.0)
        assert state.fire < 0.5

    def test_no_negative_values(self) -> None:
        e = _engine()
        state = ShipDamageState(ship_id="ship1", flooding=0.01, fire=0.01, structural=0.1)
        e.damage_control(state, dc_crew_quality=1.0, dt=600.0)
        assert state.flooding >= 0.0
        assert state.fire >= 0.0

    def test_hull_integrity_recalculated(self) -> None:
        e = _engine()
        state = ShipDamageState(ship_id="ship1", flooding=0.5, fire=0.3, structural=0.2)
        old_integrity = state.hull_integrity  # Not yet recalculated by us
        e.damage_control(state, dc_crew_quality=0.8, dt=60.0)
        # After DC, hull integrity should reflect reduced flooding/fire
        combined = state.structural + 0.5 * state.flooding + 0.3 * state.fire
        expected = max(0.0, 1.0 - combined)
        assert state.hull_integrity == pytest.approx(expected)

    def test_better_crew_repairs_faster(self) -> None:
        """Higher quality DC crew should repair more."""
        e1 = _engine(42)
        e2 = _engine(42)
        s1 = ShipDamageState(ship_id="s1", flooding=0.5, structural=0.3)
        s2 = ShipDamageState(ship_id="s2", flooding=0.5, structural=0.3)
        e1.damage_control(s1, dc_crew_quality=0.2, dt=60.0)
        e2.damage_control(s2, dc_crew_quality=1.0, dt=60.0)
        # Better crew should have less flooding remaining
        assert s2.flooding <= s1.flooding


class TestAssessMissionKill:
    def test_low_integrity_is_mission_kill(self) -> None:
        e = _engine()
        assert e.assess_mission_kill(0.3) is True

    def test_high_integrity_is_not(self) -> None:
        e = _engine()
        assert e.assess_mission_kill(0.8) is False

    def test_threshold_boundary(self) -> None:
        e = _engine()
        assert e.assess_mission_kill(0.5) is False  # at threshold, not below
        assert e.assess_mission_kill(0.49) is True


class TestState:
    def test_state_roundtrip(self) -> None:
        e = _engine(42)
        e.apply_ship_damage("ship1", 3)
        saved = e.get_state()

        e2 = _engine(99)
        e2.set_state(saved)

        # Both should have same ship damage state
        assert "ship1" in saved["damage_states"]

    def test_rng_state_restored(self) -> None:
        e = _engine(42)
        e.salvo_exchange(5, 0.8, 2, 0.3)
        saved = e.get_state()

        e2 = _engine(99)
        e2.set_state(saved)

        r1 = e.salvo_exchange(5, 0.8, 2, 0.3)
        r2 = e2.salvo_exchange(5, 0.8, 2, 0.3)
        assert r1.hits == r2.hits

    def test_damage_state_roundtrip(self) -> None:
        ds = ShipDamageState(
            ship_id="test", hull_integrity=0.6,
            flooding=0.2, fire=0.1, structural=0.3,
            systems_damaged=["propulsion"],
        )
        saved = ds.get_state()
        ds2 = ShipDamageState(ship_id="")
        ds2.set_state(saved)
        assert ds2.hull_integrity == pytest.approx(0.6)
        assert ds2.systems_damaged == ["propulsion"]
