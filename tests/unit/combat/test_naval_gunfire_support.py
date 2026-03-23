"""Unit tests for NavalGunfireSupportEngine — shore bombardment and fire coordination."""

from __future__ import annotations

import math

import pytest

from stochastic_warfare.combat.ballistics import BallisticsEngine
from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.indirect_fire import IndirectFireEngine
from stochastic_warfare.combat.naval_gunfire_support import (
    BombardmentResult,
    NavalGunfireSupportConfig,
    NavalGunfireSupportEngine,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position

from .conftest import _rng


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ngfs_engine(
    seed: int = 42,
    **cfg_kwargs,
) -> NavalGunfireSupportEngine:
    bus = EventBus()
    rng = _rng(seed)
    ballistics = BallisticsEngine(_rng(seed + 1))
    damage = DamageEngine(bus, _rng(seed + 2))
    indirect = IndirectFireEngine(ballistics, damage, bus, _rng(seed + 3))
    config = NavalGunfireSupportConfig(**cfg_kwargs) if cfg_kwargs else None
    return NavalGunfireSupportEngine(indirect, bus, rng, config)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCEPRangeScaling:
    """CEP should grow with range via power-law scaling."""

    def test_longer_range_increases_error(self):
        """Bombardment at longer range should have a larger mean error."""
        eng_close = _make_ngfs_engine(seed=100)
        eng_far = _make_ngfs_engine(seed=100)

        ship_pos = Position(0.0, 0.0, 0.0)
        close_target = Position(10_000.0, 0.0, 0.0)  # 10 km
        far_target = Position(35_000.0, 0.0, 0.0)  # 35 km

        res_close = eng_close.shore_bombardment(
            "ship_1", ship_pos, close_target, round_count=50,
        )
        res_far = eng_far.shore_bombardment(
            "ship_1", ship_pos, far_target, round_count=50,
        )

        assert res_far.mean_error_m > res_close.mean_error_m

    def test_cep_exponent_applies(self):
        """A higher exponent should produce worse accuracy at range."""
        eng_low = _make_ngfs_engine(seed=200, range_cep_exponent=1.0)
        eng_high = _make_ngfs_engine(seed=200, range_cep_exponent=2.0)

        ship_pos = Position(0.0, 0.0, 0.0)
        target = Position(30_000.0, 0.0, 0.0)

        res_low = eng_low.shore_bombardment(
            "ship_1", ship_pos, target, round_count=50,
        )
        res_high = eng_high.shore_bombardment(
            "ship_1", ship_pos, target, round_count=50,
        )

        assert res_high.mean_error_m > res_low.mean_error_m


class TestSpotterReduction:
    """Forward observer should reduce CEP to 40% (default config)."""

    def test_spotter_reduces_mean_error(self):
        eng_no_spot = _make_ngfs_engine(seed=300)
        eng_spot = _make_ngfs_engine(seed=300)

        ship_pos = Position(0.0, 0.0, 0.0)
        target = Position(20_000.0, 0.0, 0.0)

        res_no = eng_no_spot.shore_bombardment(
            "ship_1", ship_pos, target, round_count=100, spotter_present=False,
        )
        res_yes = eng_spot.shore_bombardment(
            "ship_1", ship_pos, target, round_count=100, spotter_present=True,
        )

        # Spotter should produce substantially lower mean error
        assert res_yes.mean_error_m < res_no.mean_error_m * 0.7


class TestMaxRangeAbort:
    """Bombardment beyond max range should still fire but coordination should fail."""

    def test_fire_support_coordination_rejects_beyond_range(self):
        eng = _make_ngfs_engine(seed=400, max_range_m=30_000.0)
        ship_pos = Position(0.0, 0.0, 0.0)
        requester_pos = Position(40_000.0, 0.0, 0.0)
        target = Position(40_000.0, 500.0, 0.0)

        result = eng.fire_support_coordination(ship_pos, requester_pos, target)
        assert result is False

    def test_fire_support_coordination_accepts_within_range(self):
        eng = _make_ngfs_engine(seed=401)
        ship_pos = Position(0.0, 0.0, 0.0)
        requester_pos = Position(15_000.0, 0.0, 0.0)
        target = Position(15_000.0, 500.0, 0.0)

        result = eng.fire_support_coordination(ship_pos, requester_pos, target)
        assert result is True


class TestDeterminism:
    """Same seed should produce identical results."""

    def test_same_seed_same_results(self):
        ship_pos = Position(0.0, 0.0, 0.0)
        target = Position(20_000.0, 0.0, 0.0)

        eng1 = _make_ngfs_engine(seed=500)
        eng2 = _make_ngfs_engine(seed=500)

        res1 = eng1.shore_bombardment("ship_1", ship_pos, target, round_count=20)
        res2 = eng2.shore_bombardment("ship_1", ship_pos, target, round_count=20)

        assert res1.hits_in_lethal_radius == res2.hits_in_lethal_radius
        assert res1.mean_error_m == pytest.approx(res2.mean_error_m)


class TestStateRoundtrip:
    """get_state / set_state should preserve PRNG state."""

    def test_state_roundtrip(self):
        eng = _make_ngfs_engine(seed=600)
        ship_pos = Position(0.0, 0.0, 0.0)
        target = Position(15_000.0, 0.0, 0.0)

        # Advance RNG
        eng.shore_bombardment("ship_1", ship_pos, target, round_count=5)
        state = eng.get_state()

        # Continue
        res_a = eng.shore_bombardment("ship_1", ship_pos, target, round_count=10)

        # Restore and replay
        eng.set_state(state)
        res_b = eng.shore_bombardment("ship_1", ship_pos, target, round_count=10)

        assert res_a.mean_error_m == pytest.approx(res_b.mean_error_m)
        assert res_a.hits_in_lethal_radius == res_b.hits_in_lethal_radius
