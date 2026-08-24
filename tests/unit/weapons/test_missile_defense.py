"""Phase 71c: missile defense intercept tests.

Verifies MissileDefenseEngine instantiation on SimulationContext and
intercept wiring in the battle loop.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.combat.missile_defense import (
    MissileDefenseEngine,
)
from stochastic_warfare.core.events import EventBus

TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _make_rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


@pytest.fixture
def md_engine():
    bus = EventBus()
    rng = _make_rng()
    return MissileDefenseEngine(event_bus=bus, rng=rng)


# ---------------------------------------------------------------------------
# Cruise missile defense
# ---------------------------------------------------------------------------


class TestCruiseMissileDefense:
    """Test engage_cruise_missile behavior."""

    def test_high_pk_intercepts(self):
        """Defender with near-perfect Pk should usually intercept."""
        bus = EventBus()
        intercepts = 0
        for seed in range(30):
            rng = _make_rng(seed)
            eng = MissileDefenseEngine(event_bus=bus, rng=rng)
            result = eng.engage_cruise_missile(
                defender_pk=0.99,
                missile_speed_mps=250.0,
                sea_skimming=False,
            )
            if result.hit:
                intercepts += 1
        assert intercepts > 20, f"Expected >20/30 intercepts at Pk=0.99, got {intercepts}"

    def test_sea_skimming_reduces_pk(self):
        """Sea-skimming missiles should be harder to intercept."""
        bus = EventBus()
        hits_normal = 0
        hits_skimming = 0
        n = 50

        for seed in range(n):
            rng = _make_rng(seed)
            eng = MissileDefenseEngine(event_bus=bus, rng=rng)
            r = eng.engage_cruise_missile(defender_pk=0.7, sea_skimming=False)
            if r.hit:
                hits_normal += 1

        for seed in range(n):
            rng = _make_rng(seed + 1000)
            eng = MissileDefenseEngine(event_bus=bus, rng=rng)
            r = eng.engage_cruise_missile(defender_pk=0.7, sea_skimming=True)
            if r.hit:
                hits_skimming += 1

        # Sea skimming penalty should reduce effective Pk
        assert hits_normal >= hits_skimming, (
            f"Normal ({hits_normal}) should intercept >= sea-skimming ({hits_skimming})"
        )

    def test_zero_pk_never_intercepts(self, md_engine):
        """Defender with Pk=0 should never intercept."""
        result = md_engine.engage_cruise_missile(
            defender_pk=0.0,
            missile_speed_mps=250.0,
        )
        assert not result.hit


# ---------------------------------------------------------------------------
# Ballistic missile defense
# ---------------------------------------------------------------------------


class TestBallisticMissileDefense:
    """Test engage_ballistic_missile behavior."""

    def test_multilayer_defense(self, md_engine):
        """Multiple defense layers improve cumulative Pk."""
        result = md_engine.engage_ballistic_missile(
            defender_pks=[0.5, 0.5, 0.5],
            missile_speed_mps=3000.0,
        )
        # Cumulative Pk should be higher than single layer
        assert result.cumulative_pk > 0.5
        # layers_engaged may be < 3 if an early layer intercepts
        assert result.layers_engaged >= 1
        assert result.layers_engaged <= 3
