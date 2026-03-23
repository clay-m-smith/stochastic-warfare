"""Unit tests for NavalGunneryEngine — bracket fire and convergence."""

from __future__ import annotations

import pytest

from stochastic_warfare.combat.naval_gunnery import (
    BracketState,
    NavalGunneryConfig,
    NavalGunneryEngine,
)

from .conftest import _rng


def _make_engine(seed: int = 42, **cfg_kwargs) -> NavalGunneryEngine:
    config = NavalGunneryConfig(**cfg_kwargs) if cfg_kwargs else None
    return NavalGunneryEngine(config=config, rng=_rng(seed))


# ---------------------------------------------------------------------------
# Bracket management
# ---------------------------------------------------------------------------


class TestBracketManagement:
    """Bracket initialization and convergence."""

    def test_initial_bracket(self):
        eng = _make_engine()
        bracket = eng.get_bracket("ship_1", "target_1")
        assert isinstance(bracket, BracketState)
        assert bracket.bracket_width_m > 0
        assert bracket.straddle_achieved is False
        assert bracket.salvos_fired == 0

    def test_bracket_convergence(self):
        """Bracket narrows after successive updates."""
        eng = _make_engine()
        initial = eng.get_bracket("ship_1", "target_1")
        initial_width = initial.bracket_width_m
        for _ in range(5):
            eng.update_bracket("ship_1", "target_1")
        bracket = eng.get_bracket("ship_1", "target_1")
        assert bracket.bracket_width_m < initial_width
        assert bracket.salvos_fired == 5

    def test_straddle_achievement(self):
        """High fire control quality achieves straddle faster."""
        eng = _make_engine(straddle_width_m=500.0)
        eng.get_bracket("ship_1", "target_1")
        for _ in range(10):
            eng.update_bracket("ship_1", "target_1", fire_control_quality=1.0)
        bracket = eng.get_bracket("ship_1", "target_1")
        # With aggressive convergence, should achieve straddle
        assert bracket.straddle_achieved or bracket.bracket_width_m < 500.0


# ---------------------------------------------------------------------------
# Hit probability
# ---------------------------------------------------------------------------


class TestHitProbability:
    """Hit probability computation."""

    def test_straddle_bonus(self):
        """Straddle achieved gives higher hit probability."""
        eng = _make_engine()
        bracket_no = eng.get_bracket("s1", "t1")
        bracket_yes = eng.get_bracket("s2", "t2")
        bracket_yes.straddle_achieved = True
        pk_no = eng.compute_hit_probability(15000.0, 200.0, 25.0, bracket_no)
        pk_yes = eng.compute_hit_probability(15000.0, 200.0, 25.0, bracket_yes)
        assert pk_yes >= pk_no

    def test_target_area_scaling(self):
        """Larger target is easier to hit."""
        eng = _make_engine()
        bracket = eng.get_bracket("s1", "t1")
        bracket.straddle_achieved = True
        pk_small = eng.compute_hit_probability(15000.0, 100.0, 10.0, bracket)
        pk_large = eng.compute_hit_probability(15000.0, 300.0, 40.0, bracket)
        assert pk_large >= pk_small

    def test_zero_range_returns_zero(self):
        eng = _make_engine()
        bracket = eng.get_bracket("s1", "t1")
        pk = eng.compute_hit_probability(0.0, 200.0, 25.0, bracket)
        assert pk == pytest.approx(0.0)

    def test_more_guns_higher_probability(self):
        """More guns in salvo increases probability of at least one hit."""
        eng = _make_engine()
        bracket = eng.get_bracket("s1", "t1")
        bracket.straddle_achieved = True
        pk_1 = eng.compute_hit_probability(15000.0, 200.0, 25.0, bracket, num_guns=1)
        pk_8 = eng.compute_hit_probability(15000.0, 200.0, 25.0, bracket, num_guns=8)
        assert pk_8 >= pk_1


# ---------------------------------------------------------------------------
# Fire salvo
# ---------------------------------------------------------------------------


class TestFireSalvo:
    """Combined fire salvo."""

    def test_fire_salvo_returns_result(self):
        eng = _make_engine()
        result = eng.fire_salvo("s1", "t1", 15000.0, 200.0, 25.0, num_guns=8)
        assert isinstance(result, dict)
        assert "hits" in result
        assert "hit_probability" in result
        assert "bracket" in result
        assert "salvos_fired" in result

    def test_reset_clears_brackets(self):
        eng = _make_engine()
        eng.get_bracket("s1", "t1")
        eng.update_bracket("s1", "t1")
        eng.reset("s1")
        bracket = eng.get_bracket("s1", "t1")
        assert bracket.salvos_fired == 0

    def test_reset_all(self):
        eng = _make_engine()
        eng.get_bracket("s1", "t1")
        eng.get_bracket("s2", "t2")
        eng.reset()
        bracket = eng.get_bracket("s1", "t1")
        assert bracket.salvos_fired == 0


# ---------------------------------------------------------------------------
# State roundtrip
# ---------------------------------------------------------------------------


class TestNavalGunneryStateRoundtrip:
    """State persistence."""

    def test_state_roundtrip(self):
        eng = _make_engine(seed=55)
        eng.get_bracket("s1", "t1")
        eng.update_bracket("s1", "t1")
        state = eng.get_state()

        eng2 = _make_engine(seed=1)
        eng2.set_state(state)
        b = eng2.get_bracket("s1", "t1")
        assert b.salvos_fired > 0
