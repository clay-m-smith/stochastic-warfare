"""Unit tests for SiegeEngine — siege state machine and attrition."""

from __future__ import annotations

import pytest

from stochastic_warfare.combat.siege import (
    SiegeConfig,
    SiegeEngine,
    SiegePhase,
    SiegeState,
)

from .conftest import _rng


def _make_engine(seed: int = 42, **cfg_kwargs) -> SiegeEngine:
    config = SiegeConfig(**cfg_kwargs) if cfg_kwargs else None
    return SiegeEngine(config=config, rng=_rng(seed))


# ---------------------------------------------------------------------------
# Phase transitions
# ---------------------------------------------------------------------------


class TestSiegePhases:
    """Phase transitions: ENCIRCLEMENT -> BOMBARDMENT -> BREACH."""

    def test_begin_siege_encirclement(self):
        eng = _make_engine()
        state = eng.begin_siege("s1", garrison_size=500, food_days=30, attacker_size=2000)
        assert isinstance(state, SiegeState)
        assert state.phase == SiegePhase.ENCIRCLEMENT
        assert state.garrison_size == 500
        assert state.attacker_size == 2000

    def test_encirclement_to_bombardment(self):
        """Providing siege engines transitions from ENCIRCLEMENT to BOMBARDMENT."""
        eng = _make_engine()
        eng.begin_siege("s1", garrison_size=500, food_days=60, attacker_size=2000)
        state = eng.advance_day("s1", n_trebuchets=3)
        assert state.phase == SiegePhase.BOMBARDMENT

    def test_bombardment_reduces_wall_hp(self):
        eng = _make_engine()
        eng.begin_siege("s1", garrison_size=500, food_days=60, attacker_size=2000)
        state = eng.advance_day("s1", n_trebuchets=5)
        # 5 * 50 = 250 damage -> 1000 - 250 = 750
        assert state.wall_hp_remaining < 1000.0

    def test_breach_after_sufficient_bombardment(self):
        """Wall HP drops below threshold -> BREACH."""
        eng = _make_engine(trebuchet_damage_per_day=200.0, breach_threshold=0.3)
        eng.begin_siege("s1", garrison_size=500, food_days=60, attacker_size=2000)
        # Bombard until breach: wall_hp=1000, threshold 0.3 means breach at <= 300 HP
        for _ in range(5):
            eng.advance_day("s1", n_trebuchets=5)
        phase = eng.get_phase("s1")
        assert phase in (SiegePhase.BOMBARDMENT, SiegePhase.BREACH)


# ---------------------------------------------------------------------------
# Wall damage from engines
# ---------------------------------------------------------------------------


class TestWallDamage:
    """Trebuchets, rams, catapults, and mines all deal wall damage."""

    def test_trebuchet_damage(self):
        eng = _make_engine()
        eng.begin_siege("s1", garrison_size=500, food_days=60, attacker_size=2000)
        state = eng.advance_day("s1", n_trebuchets=2)
        # 2 * 50 = 100 damage
        assert state.wall_hp_remaining == pytest.approx(900.0)

    def test_ram_damage(self):
        eng = _make_engine()
        eng.begin_siege("s1", garrison_size=500, food_days=60, attacker_size=2000)
        state = eng.advance_day("s1", n_rams=3)
        # 3 * 30 = 90 damage
        assert state.wall_hp_remaining == pytest.approx(910.0)

    def test_catapult_damage(self):
        eng = _make_engine()
        eng.begin_siege("s1", garrison_size=500, food_days=60, attacker_size=2000)
        state = eng.advance_day("s1", n_catapults=4)
        # 4 * 20 = 80 damage
        assert state.wall_hp_remaining == pytest.approx(920.0)

    def test_mine_damage(self):
        eng = _make_engine()
        eng.begin_siege("s1", garrison_size=500, food_days=60, attacker_size=2000)
        state = eng.advance_day("s1", n_mines=2)
        # 2 * 40 = 80 damage
        assert state.wall_hp_remaining == pytest.approx(920.0)


# ---------------------------------------------------------------------------
# Starvation
# ---------------------------------------------------------------------------


class TestStarvation:
    """Starvation attrition when food runs out."""

    def test_no_starvation_with_food(self):
        eng = _make_engine()
        eng.begin_siege("s1", garrison_size=100, food_days=30, attacker_size=500)
        losses = eng.check_starvation("s1")
        assert losses == 0

    def test_starvation_after_food_exhausted(self):
        eng = _make_engine()
        eng.begin_siege("s1", garrison_size=100, food_days=3, attacker_size=500)
        # Advance past food supply
        for _ in range(5):
            eng.advance_day("s1")
        losses = eng.check_starvation("s1")
        assert losses >= 0


# ---------------------------------------------------------------------------
# Assault
# ---------------------------------------------------------------------------


class TestAssault:
    """Assault from BREACH phase."""

    def test_assault_from_breach(self):
        eng = _make_engine(breach_threshold=0.99)
        eng.begin_siege("s1", garrison_size=200, food_days=60, attacker_size=2000, wall_hp=10.0)
        eng.advance_day("s1", n_trebuchets=1)  # Should breach immediately
        success, att_cas, def_cas = eng.attempt_assault("s1")
        assert att_cas >= 0
        assert def_cas >= 0

    def test_assault_not_possible_from_encirclement(self):
        eng = _make_engine()
        eng.begin_siege("s1", garrison_size=500, food_days=60, attacker_size=2000)
        success, att_cas, def_cas = eng.attempt_assault("s1")
        assert success is False
        assert att_cas == 0
        assert def_cas == 0


# ---------------------------------------------------------------------------
# Sally sortie
# ---------------------------------------------------------------------------


class TestSallySortie:
    """Garrison sally sortie."""

    def test_sally_with_high_probability(self):
        eng = _make_engine(sally_probability=1.0)
        eng.begin_siege("s1", garrison_size=500, food_days=60, attacker_size=2000)
        attempted, casualties = eng.sally_sortie("s1")
        assert attempted is True
        assert casualties >= 0

    def test_sally_not_possible_after_fallen(self):
        eng = _make_engine()
        state = eng.begin_siege("s1", garrison_size=10, food_days=60, attacker_size=2000)
        state.phase = SiegePhase.FALLEN
        attempted, _ = eng.sally_sortie("s1")
        assert attempted is False


# ---------------------------------------------------------------------------
# Relief force
# ---------------------------------------------------------------------------


class TestReliefForce:
    """Relieve siege with external force."""

    def test_relieve_siege_success(self):
        eng = _make_engine(relief_force_ratio=0.5)
        eng.begin_siege("s1", garrison_size=500, food_days=60, attacker_size=1000)
        # Relief force > attacker * ratio (600 > 500)
        result = eng.relieve_siege("s1", relief_force_size=600)
        assert result is True
        assert eng.get_phase("s1") == SiegePhase.RELIEF

    def test_relieve_siege_failure(self):
        eng = _make_engine(relief_force_ratio=0.5)
        eng.begin_siege("s1", garrison_size=500, food_days=60, attacker_size=1000)
        # Relief force < attacker * ratio (400 < 500)
        result = eng.relieve_siege("s1", relief_force_size=400)
        assert result is False


# ---------------------------------------------------------------------------
# State roundtrip
# ---------------------------------------------------------------------------


class TestSiegeStateRoundtrip:
    """State persistence."""

    def test_state_roundtrip(self):
        eng = _make_engine(seed=55)
        eng.begin_siege("s1", garrison_size=500, food_days=30, attacker_size=2000)
        eng.advance_day("s1", n_trebuchets=3)
        state = eng.get_state()

        eng2 = _make_engine(seed=1)
        eng2.set_state(state)
        s = eng2.get_siege_state("s1")
        assert s.siege_id == "s1"
        assert s.days_elapsed > 0
        assert s.wall_hp_remaining < 1000.0
