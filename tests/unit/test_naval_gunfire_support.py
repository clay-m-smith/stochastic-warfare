"""Tests for combat/naval_gunfire_support.py — shore bombardment."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.combat.ballistics import BallisticsEngine
from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.indirect_fire import IndirectFireEngine
from stochastic_warfare.combat.naval_gunfire_support import (
    NavalGunfireSupportConfig,
    NavalGunfireSupportEngine,
)
from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.types import Position


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _engine(seed: int = 42, config: NavalGunfireSupportConfig | None = None) -> NavalGunfireSupportEngine:
    rng = _rng(seed)
    bus = EventBus()
    dmg = DamageEngine(bus, rng)
    bal = BallisticsEngine(rng)
    indirect = IndirectFireEngine(bal, dmg, bus, rng)
    return NavalGunfireSupportEngine(indirect, bus, rng, config)


def _engine_with_bus(seed: int = 42) -> tuple[NavalGunfireSupportEngine, EventBus]:
    rng = _rng(seed)
    bus = EventBus()
    dmg = DamageEngine(bus, rng)
    bal = BallisticsEngine(rng)
    indirect = IndirectFireEngine(bal, dmg, bus, rng)
    return NavalGunfireSupportEngine(indirect, bus, rng), bus


class TestShoreBombardment:
    def test_basic_bombardment(self) -> None:
        e = _engine()
        result = e.shore_bombardment(
            "ship1", Position(0, 0, 0), Position(0, 20000, 0),
            round_count=10,
        )
        assert result.rounds_fired == 10
        assert len(result.impacts) == 10

    def test_impacts_scatter_around_target(self) -> None:
        e = _engine()
        target = Position(5000.0, 15000.0, 0.0)
        result = e.shore_bombardment(
            "ship1", Position(0, 0, 0), target, round_count=30,
        )
        eastings = [p.easting for p in result.impacts]
        northings = [p.northing for p in result.impacts]
        mean_e = sum(eastings) / len(eastings)
        mean_n = sum(northings) / len(northings)
        # Should cluster around target
        assert abs(mean_e - target.easting) < 500.0
        assert abs(mean_n - target.northing) < 500.0

    def test_spotter_improves_accuracy(self) -> None:
        """Forward observer should dramatically reduce error."""
        e1 = _engine(42)
        e2 = _engine(42)
        target = Position(0, 20000, 0)
        no_spotter = e1.shore_bombardment(
            "ship1", Position(0, 0, 0), target,
            round_count=30, spotter_present=False,
        )
        spotter = e2.shore_bombardment(
            "ship1", Position(0, 0, 0), target,
            round_count=30, spotter_present=True,
        )
        assert spotter.mean_error_m < no_spotter.mean_error_m

    def test_range_degrades_accuracy(self) -> None:
        """Accuracy should degrade at longer range."""
        e1 = _engine(42)
        e2 = _engine(42)
        close = e1.shore_bombardment(
            "ship1", Position(0, 0, 0), Position(0, 10000, 0),
            round_count=30,
        )
        far = e2.shore_bombardment(
            "ship1", Position(0, 0, 0), Position(0, 35000, 0),
            round_count=30,
        )
        assert far.mean_error_m > close.mean_error_m

    def test_lethal_hits_counted(self) -> None:
        """Some rounds should land within lethal radius."""
        # Use a close range and many rounds for statistical certainty
        e = _engine()
        result = e.shore_bombardment(
            "ship1", Position(0, 0, 0), Position(0, 10000, 0),
            round_count=100, spotter_present=True,
        )
        assert result.hits_in_lethal_radius > 0

    def test_event_published(self) -> None:
        e, bus = _engine_with_bus()
        received: list[Event] = []
        bus.subscribe(Event, lambda ev: received.append(ev))
        ts = datetime(2024, 6, 15, tzinfo=timezone.utc)
        e.shore_bombardment(
            "ship1", Position(0, 0, 0), Position(0, 20000, 0),
            round_count=5, timestamp=ts,
        )
        assert len(received) >= 1

    def test_deterministic_with_seed(self) -> None:
        e1 = _engine(42)
        e2 = _engine(42)
        r1 = e1.shore_bombardment(
            "ship1", Position(0, 0, 0), Position(0, 20000, 0), round_count=5,
        )
        r2 = e2.shore_bombardment(
            "ship1", Position(0, 0, 0), Position(0, 20000, 0), round_count=5,
        )
        assert r1.hits_in_lethal_radius == r2.hits_in_lethal_radius
        assert r1.mean_error_m == pytest.approx(r2.mean_error_m)

    def test_custom_cep(self) -> None:
        """Custom CEP should change accuracy."""
        e1 = _engine(42)
        e2 = _engine(42)
        tight = e1.shore_bombardment(
            "ship1", Position(0, 0, 0), Position(0, 20000, 0),
            gun_cep_m=50.0, round_count=30,
        )
        wide = e2.shore_bombardment(
            "ship1", Position(0, 0, 0), Position(0, 20000, 0),
            gun_cep_m=500.0, round_count=30,
        )
        assert tight.mean_error_m < wide.mean_error_m


class TestFireSupportCoordination:
    def test_in_range_approved(self) -> None:
        e = _engine()
        ok = e.fire_support_coordination(
            Position(0, 0, 0), Position(0, 20000, 0), Position(0, 20100, 0),
        )
        assert ok is True

    def test_out_of_range_denied(self) -> None:
        e = _engine()
        ok = e.fire_support_coordination(
            Position(0, 0, 0), Position(0, 30000, 0), Position(0, 50000, 0),
        )
        assert ok is False

    def test_danger_close_denied(self) -> None:
        """Target too close to requesting unit should be denied."""
        e = _engine()
        ok = e.fire_support_coordination(
            Position(0, 0, 0),
            Position(0, 20000, 0),  # requester
            Position(0, 20010, 0),  # target very close to requester
        )
        assert ok is False

    def test_custom_max_range(self) -> None:
        e = _engine()
        ok = e.fire_support_coordination(
            Position(0, 0, 0), Position(0, 5000, 0), Position(0, 10000, 0),
            max_range_m=5000.0,
        )
        assert ok is False


class TestState:
    def test_state_roundtrip(self) -> None:
        e = _engine(42)
        e.shore_bombardment(
            "ship1", Position(0, 0, 0), Position(0, 20000, 0), round_count=5,
        )
        saved = e.get_state()

        e2 = _engine(99)
        e2.set_state(saved)

        r1 = e.shore_bombardment(
            "ship1", Position(0, 0, 0), Position(0, 20000, 0), round_count=5,
        )
        r2 = e2.shore_bombardment(
            "ship1", Position(0, 0, 0), Position(0, 20000, 0), round_count=5,
        )
        assert r1.mean_error_m == pytest.approx(r2.mean_error_m)
