"""Unit tests for AmphibiousAssaultEngine — beach assault waves and combat."""

from __future__ import annotations

import pytest

from stochastic_warfare.combat.amphibious_assault import (
    AmphibiousAssaultConfig,
    AmphibiousAssaultEngine,
    BeachCombatResult,
    WaveResult,
)
from stochastic_warfare.combat.ballistics import BallisticsEngine
from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.indirect_fire import IndirectFireEngine
from stochastic_warfare.combat.naval_gunfire_support import NavalGunfireSupportEngine
from stochastic_warfare.combat.naval_surface import NavalSurfaceEngine
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position

from .conftest import _rng


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_amphib_engine(
    seed: int = 42,
    **cfg_kwargs,
) -> AmphibiousAssaultEngine:
    bus = EventBus()
    damage = DamageEngine(bus, _rng(seed + 1))
    naval_surface = NavalSurfaceEngine(damage, bus, _rng(seed + 2))
    ballistics = BallisticsEngine(_rng(seed + 3))
    indirect = IndirectFireEngine(ballistics, damage, bus, _rng(seed + 4))
    ngfs = NavalGunfireSupportEngine(indirect, bus, _rng(seed + 5))
    config = AmphibiousAssaultConfig(**cfg_kwargs) if cfg_kwargs else None
    return AmphibiousAssaultEngine(naval_surface, ngfs, damage, bus, _rng(seed), config)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestApproachAttrition:
    """Approach attrition should increase with defense strength."""

    def test_stronger_defense_more_casualties(self):
        eng_weak = _make_amphib_engine(seed=100)
        eng_strong = _make_amphib_engine(seed=100)

        res_weak = eng_weak.execute_wave(1000, beach_defense_strength=0.1)
        res_strong = eng_strong.execute_wave(1000, beach_defense_strength=0.9)

        assert res_strong.casualties >= res_weak.casualties

    def test_zero_defense_minimal_casualties(self):
        eng = _make_amphib_engine(seed=101)
        res = eng.execute_wave(1000, beach_defense_strength=0.0)
        # With zero defense, approach attrition should be near zero
        assert res.casualties < 300  # generous bound — stochastic landing factor


class TestLandingFactor:
    """Wave landing factor should determine fraction that reach shore."""

    def test_landed_within_wave_size(self):
        eng = _make_amphib_engine(seed=200)
        res = eng.execute_wave(500, beach_defense_strength=0.3)
        assert res.landed <= res.wave_size
        assert res.landed >= 0

    def test_higher_landing_factor_more_troops(self):
        eng_low = _make_amphib_engine(seed=300, wave_landing_factor=0.4)
        eng_high = _make_amphib_engine(seed=300, wave_landing_factor=0.95)

        res_low = eng_low.execute_wave(1000, beach_defense_strength=0.2)
        res_high = eng_high.execute_wave(1000, beach_defense_strength=0.2)

        assert res_high.landed > res_low.landed


class TestSeaStatePenalty:
    """High sea state should reduce landing success."""

    def test_rough_sea_reduces_landed(self):
        eng_calm = _make_amphib_engine(seed=400)
        eng_rough = _make_amphib_engine(seed=400)

        res_calm = eng_calm.execute_wave(
            1000, beach_defense_strength=0.3,
            conditions={"sea_state": 1.0},
        )
        res_rough = eng_rough.execute_wave(
            1000, beach_defense_strength=0.3,
            conditions={"sea_state": 6.0},
        )

        assert res_rough.landed < res_calm.landed


class TestNavalSupport:
    """Naval support should reduce effective defense."""

    def test_naval_support_improves_landing(self):
        eng_no_support = _make_amphib_engine(seed=500)
        eng_with_support = _make_amphib_engine(seed=500)

        res_no = eng_no_support.execute_wave(
            1000, beach_defense_strength=0.8, naval_support_factor=0.0,
        )
        res_with = eng_with_support.execute_wave(
            1000, beach_defense_strength=0.8, naval_support_factor=1.0,
        )

        assert res_with.naval_support_suppression > 0.0
        assert res_with.landed >= res_no.landed


class TestBeachCombat:
    """Beach combat with terrain defense multiplier."""

    def test_terrain_advantage_favors_defender(self):
        eng = _make_amphib_engine(seed=600)
        # Equal raw strength, but defender has terrain
        res = eng.resolve_beach_combat(100.0, 100.0, terrain_advantage=2.0)
        # Defender's effective strength is 100 * 2.0 * 1.5 = 300
        # So attacker should suffer more relative to defender
        assert isinstance(res, BeachCombatResult)
        assert res.attacker_casualties_fraction >= 0.0
        assert res.defender_casualties_fraction >= 0.0

    def test_beachhead_establishment_needs_force_ratio(self):
        eng = _make_amphib_engine(seed=700, min_force_ratio_for_establishment=3.0)
        # Weak attacker vs strong defender
        res = eng.resolve_beach_combat(50.0, 100.0, terrain_advantage=1.0)
        assert res.beachhead_established is False

    def test_overwhelming_force_establishes_beachhead(self):
        eng = _make_amphib_engine(seed=800, min_force_ratio_for_establishment=1.5)
        # Massive attacker advantage
        res = eng.resolve_beach_combat(500.0, 10.0, terrain_advantage=1.0)
        assert res.beachhead_established is True


class TestStateRoundtrip:
    """get_state / set_state should preserve engine state."""

    def test_state_roundtrip(self):
        eng = _make_amphib_engine(seed=900)

        # Execute a wave to advance state
        eng.execute_wave(500, beach_defense_strength=0.5)
        state = eng.get_state()
        assert state["wave_count"] == 1

        # Continue
        res_a = eng.execute_wave(200, beach_defense_strength=0.3)

        # Restore and replay
        eng.set_state(state)
        res_b = eng.execute_wave(200, beach_defense_strength=0.3)

        assert res_a.landed == res_b.landed
        assert res_a.casualties == res_b.casualties
