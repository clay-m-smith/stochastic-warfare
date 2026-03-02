"""Tests for combat/amphibious_assault.py — beach assault mechanics."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.combat.amphibious_assault import (
    AmphibiousAssaultConfig,
    AmphibiousAssaultEngine,
    AssaultPhase,
    BeachCombatResult,
    WaveResult,
)
from stochastic_warfare.combat.ballistics import BallisticsEngine
from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.indirect_fire import IndirectFireEngine
from stochastic_warfare.combat.naval_gunfire_support import NavalGunfireSupportEngine
from stochastic_warfare.combat.naval_surface import NavalSurfaceEngine
from stochastic_warfare.core.events import Event, EventBus


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _engine(seed: int = 42, config: AmphibiousAssaultConfig | None = None) -> AmphibiousAssaultEngine:
    rng = _rng(seed)
    bus = EventBus()
    dmg = DamageEngine(bus, rng)
    bal = BallisticsEngine(rng)
    indirect = IndirectFireEngine(bal, dmg, bus, rng)
    naval_surface = NavalSurfaceEngine(dmg, bus, rng)
    naval_gunfire = NavalGunfireSupportEngine(indirect, bus, rng)
    return AmphibiousAssaultEngine(naval_surface, naval_gunfire, dmg, bus, rng, config)


def _engine_with_bus(seed: int = 42) -> tuple[AmphibiousAssaultEngine, EventBus]:
    rng = _rng(seed)
    bus = EventBus()
    dmg = DamageEngine(bus, rng)
    bal = BallisticsEngine(rng)
    indirect = IndirectFireEngine(bal, dmg, bus, rng)
    naval_surface = NavalSurfaceEngine(dmg, bus, rng)
    naval_gunfire = NavalGunfireSupportEngine(indirect, bus, rng)
    return AmphibiousAssaultEngine(naval_surface, naval_gunfire, dmg, bus, rng), bus


class TestExecuteWave:
    def test_basic_wave(self) -> None:
        e = _engine()
        result = e.execute_wave(100, beach_defense_strength=0.3)
        assert result.wave_size == 100
        assert result.landed > 0
        assert result.casualties >= 0
        assert result.landed + result.casualties <= 100

    def test_no_defense_high_landing(self) -> None:
        """No defense should land most troops."""
        total_landed = 0
        for seed in range(20):
            result = _engine(seed).execute_wave(100, beach_defense_strength=0.0)
            total_landed += result.landed
        # With no defense, average should be high
        assert total_landed / 20.0 > 60

    def test_strong_defense_more_casualties(self) -> None:
        """Stronger defense should cause more casualties."""
        weak_cas = sum(
            _engine(seed).execute_wave(100, beach_defense_strength=0.1).casualties
            for seed in range(20)
        )
        strong_cas = sum(
            _engine(seed).execute_wave(100, beach_defense_strength=0.9).casualties
            for seed in range(20)
        )
        assert strong_cas > weak_cas

    def test_naval_support_reduces_casualties(self) -> None:
        """Naval fire support should reduce casualties."""
        no_support = sum(
            _engine(seed).execute_wave(100, 0.5, naval_support_factor=0.0).casualties
            for seed in range(20)
        )
        with_support = sum(
            _engine(seed).execute_wave(100, 0.5, naval_support_factor=0.9).casualties
            for seed in range(20)
        )
        assert with_support <= no_support

    def test_high_sea_state_penalty(self) -> None:
        """High sea state should reduce landing success."""
        calm = sum(
            _engine(seed).execute_wave(100, 0.3, conditions={"sea_state": 1.0}).landed
            for seed in range(20)
        )
        rough = sum(
            _engine(seed).execute_wave(100, 0.3, conditions={"sea_state": 6.0}).landed
            for seed in range(20)
        )
        assert calm > rough

    def test_first_wave_is_initial(self) -> None:
        e = _engine()
        result = e.execute_wave(50, 0.3)
        assert result.phase == AssaultPhase.INITIAL_WAVE

    def test_second_wave_is_buildup(self) -> None:
        e = _engine()
        e.execute_wave(50, 0.3)
        result = e.execute_wave(50, 0.3)
        assert result.phase == AssaultPhase.BUILDUP

    def test_landed_non_negative(self) -> None:
        for seed in range(30):
            result = _engine(seed).execute_wave(100, 0.9)
            assert result.landed >= 0

    def test_casualties_non_negative(self) -> None:
        for seed in range(30):
            result = _engine(seed).execute_wave(100, 0.5)
            assert result.casualties >= 0

    def test_event_published(self) -> None:
        e, bus = _engine_with_bus()
        received: list[Event] = []
        bus.subscribe(Event, lambda ev: received.append(ev))
        ts = datetime(2024, 6, 15, tzinfo=timezone.utc)
        e.execute_wave(50, 0.3, timestamp=ts)
        assert len(received) >= 1

    def test_deterministic_with_seed(self) -> None:
        e1 = _engine(42)
        e2 = _engine(42)
        r1 = e1.execute_wave(100, 0.5)
        r2 = e2.execute_wave(100, 0.5)
        assert r1.landed == r2.landed
        assert r1.casualties == r2.casualties


class TestResolveBeachCombat:
    def test_superior_force_wins(self) -> None:
        """Attacker with clear superiority should establish beachhead."""
        established = sum(
            1 for seed in range(20)
            if _engine(seed).resolve_beach_combat(100.0, 20.0).beachhead_established
        )
        assert established > 10

    def test_inferior_force_fails(self) -> None:
        """Inferior attacker should usually fail to establish beachhead."""
        established = sum(
            1 for seed in range(20)
            if _engine(seed).resolve_beach_combat(20.0, 100.0).beachhead_established
        )
        assert established < 5

    def test_terrain_advantage_helps_defender(self) -> None:
        """Higher terrain advantage should help the defender."""
        no_adv = sum(
            1 for seed in range(30)
            if _engine(seed).resolve_beach_combat(60.0, 40.0, terrain_advantage=1.0).beachhead_established
        )
        high_adv = sum(
            1 for seed in range(30)
            if _engine(seed).resolve_beach_combat(60.0, 40.0, terrain_advantage=2.0).beachhead_established
        )
        assert no_adv >= high_adv

    def test_both_sides_take_casualties(self) -> None:
        e = _engine()
        result = e.resolve_beach_combat(100.0, 100.0)
        assert result.attacker_casualties_fraction > 0
        assert result.defender_casualties_fraction > 0

    def test_strength_remaining_positive(self) -> None:
        for seed in range(20):
            result = _engine(seed).resolve_beach_combat(50.0, 50.0)
            assert result.attacker_strength_remaining >= 0
            assert result.defender_strength_remaining >= 0

    def test_casualties_bounded(self) -> None:
        for seed in range(20):
            result = _engine(seed).resolve_beach_combat(100.0, 100.0)
            assert 0.0 <= result.attacker_casualties_fraction <= 1.0
            assert 0.0 <= result.defender_casualties_fraction <= 1.0

    def test_zero_defender_always_established(self) -> None:
        for seed in range(10):
            result = _engine(seed).resolve_beach_combat(100.0, 0.0)
            assert result.beachhead_established is True

    def test_deterministic_with_seed(self) -> None:
        e1 = _engine(42)
        e2 = _engine(42)
        r1 = e1.resolve_beach_combat(80.0, 40.0)
        r2 = e2.resolve_beach_combat(80.0, 40.0)
        assert r1.attacker_casualties_fraction == pytest.approx(r2.attacker_casualties_fraction)
        assert r1.beachhead_established == r2.beachhead_established


class TestAssaultPhase:
    def test_enum_values(self) -> None:
        assert AssaultPhase.APPROACH == 0
        assert AssaultPhase.ESTABLISHED == 3


class TestState:
    def test_state_roundtrip(self) -> None:
        e = _engine(42)
        e.execute_wave(100, 0.5)
        saved = e.get_state()

        e2 = _engine(99)
        e2.set_state(saved)

        r1 = e.execute_wave(50, 0.3)
        r2 = e2.execute_wave(50, 0.3)
        assert r1.landed == r2.landed

    def test_wave_count_restored(self) -> None:
        e = _engine(42)
        e.execute_wave(50, 0.3)
        e.execute_wave(50, 0.3)
        saved = e.get_state()
        assert saved["wave_count"] == 2
