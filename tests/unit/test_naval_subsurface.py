"""Tests for combat/naval_subsurface.py — submarine torpedo warfare."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.naval_subsurface import (
    EvasionResult,
    NavalSubsurfaceConfig,
    NavalSubsurfaceEngine,
    TorpedoResult,
)
from stochastic_warfare.core.events import Event, EventBus


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _engine(seed: int = 42, config: NavalSubsurfaceConfig | None = None) -> NavalSubsurfaceEngine:
    rng = _rng(seed)
    bus = EventBus()
    dmg = DamageEngine(bus, rng)
    return NavalSubsurfaceEngine(dmg, bus, rng, config)


def _engine_with_bus(seed: int = 42) -> tuple[NavalSubsurfaceEngine, EventBus]:
    rng = _rng(seed)
    bus = EventBus()
    dmg = DamageEngine(bus, rng)
    return NavalSubsurfaceEngine(dmg, bus, rng), bus


class TestTorpedoEngagement:
    def test_close_range_high_pk(self) -> None:
        """Close-range torpedo should have high probability of hitting."""
        hits = sum(
            1 for seed in range(50)
            if _engine(seed).torpedo_engagement("sub1", "tgt1", 0.9, 500.0).hit
        )
        assert hits > 25  # Should hit most of the time

    def test_long_range_lower_pk(self) -> None:
        """Long range should reduce hit probability."""
        close_hits = sum(
            1 for seed in range(50)
            if _engine(seed).torpedo_engagement("sub1", "tgt1", 0.8, 1000.0).hit
        )
        far_hits = sum(
            1 for seed in range(50)
            if _engine(seed).torpedo_engagement("sub1", "tgt1", 0.8, 40000.0).hit
        )
        assert close_hits > far_hits

    def test_wire_guided_bonus(self) -> None:
        """Wire guidance should improve hit probability."""
        unguided_hits = sum(
            1 for seed in range(50)
            if _engine(seed).torpedo_engagement("sub1", "tgt1", 0.5, 10000.0, wire_guided=False).hit
        )
        guided_hits = sum(
            1 for seed in range(50)
            if _engine(seed).torpedo_engagement("sub1", "tgt1", 0.5, 10000.0, wire_guided=True).hit
        )
        assert guided_hits >= unguided_hits

    def test_malfunction_possible(self) -> None:
        """Some torpedoes should malfunction."""
        malfunctions = sum(
            1 for seed in range(200)
            if _engine(seed).torpedo_engagement("sub1", "tgt1", 0.8, 5000.0).malfunction
        )
        assert malfunctions > 0

    def test_hit_causes_damage(self) -> None:
        """A torpedo hit should produce non-zero damage."""
        for seed in range(50):
            result = _engine(seed).torpedo_engagement("sub1", "tgt1", 0.95, 500.0)
            if result.hit:
                assert result.damage_fraction > 0
                break
        else:
            pytest.fail("No hits in 50 attempts at very high pk")

    def test_torpedo_id_generated(self) -> None:
        e = _engine()
        r = e.torpedo_engagement("sub1", "tgt1", 0.8, 5000.0)
        assert "sub1_torp" in r.torpedo_id

    def test_torpedo_ids_increment(self) -> None:
        e = _engine()
        r1 = e.torpedo_engagement("sub1", "tgt1", 0.8, 5000.0)
        r2 = e.torpedo_engagement("sub1", "tgt2", 0.8, 5000.0)
        assert r1.torpedo_id != r2.torpedo_id

    def test_thermocline_degrades_pk(self) -> None:
        """Thermocline should reduce hit probability."""
        no_therm_hits = sum(
            1 for seed in range(50)
            if _engine(seed).torpedo_engagement(
                "sub1", "tgt1", 0.7, 10000.0, conditions={},
            ).hit
        )
        therm_hits = sum(
            1 for seed in range(50)
            if _engine(seed).torpedo_engagement(
                "sub1", "tgt1", 0.7, 10000.0,
                conditions={"thermocline_depth_m": 100.0},
            ).hit
        )
        assert no_therm_hits >= therm_hits

    def test_event_published(self) -> None:
        e, bus = _engine_with_bus()
        received: list[Event] = []
        bus.subscribe(Event, lambda ev: received.append(ev))
        ts = datetime(2024, 6, 15, tzinfo=timezone.utc)
        e.torpedo_engagement("sub1", "tgt1", 0.8, 5000.0, timestamp=ts)
        assert len(received) >= 1

    def test_deterministic_with_seed(self) -> None:
        e1 = _engine(42)
        e2 = _engine(42)
        r1 = e1.torpedo_engagement("sub1", "tgt1", 0.7, 10000.0)
        r2 = e2.torpedo_engagement("sub1", "tgt1", 0.7, 10000.0)
        assert r1.hit == r2.hit
        assert r1.malfunction == r2.malfunction


class TestSubmarineLaunchedMissile:
    def test_shallow_depth_success(self) -> None:
        """Shallow depth should allow missile launch."""
        successes = sum(
            1 for seed in range(30)
            if _engine(seed).submarine_launched_missile("sub1", 10.0, "tlam")
        )
        assert successes > 20  # Very shallow = high success

    def test_too_deep_always_fails(self) -> None:
        """Depth exceeding limit should always fail."""
        e = _engine()
        assert e.submarine_launched_missile("sub1", 200.0, "tlam") is False

    def test_at_limit_depth(self) -> None:
        """At exactly the limit depth, some launches may succeed."""
        results = [
            _engine(seed).submarine_launched_missile("sub1", 50.0, "tlam")
            for seed in range(30)
        ]
        # Should have some successes and possibly some failures
        assert any(results)

    def test_deeper_launch_less_reliable(self) -> None:
        """Deeper launch should be less reliable than surface launch."""
        shallow = sum(
            1 for seed in range(50)
            if _engine(seed).submarine_launched_missile("sub1", 5.0, "tlam")
        )
        deep = sum(
            1 for seed in range(50)
            if _engine(seed).submarine_launched_missile("sub1", 45.0, "tlam")
        )
        assert shallow >= deep


class TestEvasionManeuver:
    def test_decoy_evasion(self) -> None:
        e = _engine()
        result = e.evasion_maneuver("sub1", 45.0, "decoy")
        assert result.evasion_type == "decoy"
        assert 0.0 <= result.effectiveness <= 1.0

    def test_depth_change_evasion(self) -> None:
        e = _engine()
        result = e.evasion_maneuver("sub1", 90.0, "depth_change")
        assert result.evasion_type == "depth_change"

    def test_knuckle_evasion(self) -> None:
        e = _engine()
        result = e.evasion_maneuver("sub1", 180.0, "knuckle")
        assert result.evasion_type == "knuckle"

    def test_unknown_evasion_type_low_effectiveness(self) -> None:
        e = _engine()
        result = e.evasion_maneuver("sub1", 0.0, "sprint")
        assert result.effectiveness <= 0.5  # Low base effectiveness


class TestCounterTorpedo:
    def test_counter_torpedo_sometimes_succeeds(self) -> None:
        successes = sum(
            1 for seed in range(50)
            if _engine(seed).counter_torpedo("ship1", 0.8, 0.5)
        )
        assert 0 < successes < 50

    def test_high_effectiveness_better(self) -> None:
        low_eff = sum(
            1 for seed in range(50)
            if _engine(seed).counter_torpedo("ship1", 0.8, 0.1)
        )
        high_eff = sum(
            1 for seed in range(50)
            if _engine(seed).counter_torpedo("ship1", 0.8, 0.9)
        )
        assert high_eff >= low_eff


class TestState:
    def test_state_roundtrip(self) -> None:
        e = _engine(42)
        e.torpedo_engagement("sub1", "tgt1", 0.8, 5000.0)
        saved = e.get_state()

        e2 = _engine(99)
        e2.set_state(saved)

        r1 = e.torpedo_engagement("sub1", "tgt2", 0.7, 8000.0)
        r2 = e2.torpedo_engagement("sub1", "tgt2", 0.7, 8000.0)
        assert r1.hit == r2.hit

    def test_torpedo_count_restored(self) -> None:
        e = _engine(42)
        e.torpedo_engagement("sub1", "tgt1", 0.8, 5000.0)
        e.torpedo_engagement("sub1", "tgt2", 0.8, 5000.0)
        saved = e.get_state()
        assert saved["torpedo_count"] == 2
