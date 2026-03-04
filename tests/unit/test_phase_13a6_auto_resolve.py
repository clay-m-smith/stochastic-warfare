"""Phase 13a-6: Auto-resolve for minor battles."""

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.simulation.battle import (
    AutoResolveResult,
    BattleConfig,
    BattleContext,
    BattleManager,
)

from datetime import datetime


def _make_unit(entity_id: str, side: str, pos: Position = Position(0, 0)) -> Unit:
    return Unit(entity_id=entity_id, position=pos, side=side, unit_type="infantry")


def _make_units(side: str, n: int, pos: Position = Position(0, 0)) -> list[Unit]:
    return [_make_unit(f"{side}_{i}", side, pos) for i in range(n)]


def _make_battle(sides: list[str] = None) -> BattleContext:
    sides = sides or ["blue", "red"]
    return BattleContext(
        battle_id="test_battle",
        start_tick=0,
        start_time=datetime.now(),
        involved_sides=sides,
    )


class TestAutoResolve:
    def test_auto_resolve_returns_result(self):
        mgr = BattleManager(EventBus())
        battle = _make_battle()
        blue = _make_units("blue", 5)
        red = _make_units("red", 3)
        units = {"blue": blue, "red": red}
        rng = np.random.default_rng(42)

        result = mgr.auto_resolve(battle, units, rng)
        assert isinstance(result, AutoResolveResult)
        assert result.battle_id == "test_battle"
        assert result.winner in ("blue", "red")

    def test_auto_resolve_marks_battle_inactive(self):
        mgr = BattleManager(EventBus())
        battle = _make_battle()
        assert battle.active
        blue = _make_units("blue", 5)
        red = _make_units("red", 3)
        mgr.auto_resolve(battle, {"blue": blue, "red": red}, np.random.default_rng(42))
        assert not battle.active

    def test_stronger_side_wins(self):
        """Side with more units should win consistently."""
        wins = {"blue": 0, "red": 0}
        for seed in range(20):
            mgr = BattleManager(EventBus())
            battle = _make_battle()
            blue = _make_units("blue", 10)
            red = _make_units("red", 3)
            result = mgr.auto_resolve(
                battle, {"blue": blue, "red": red}, np.random.default_rng(seed)
            )
            wins[result.winner] += 1
        assert wins["blue"] > wins["red"]

    def test_losses_applied_to_units(self):
        mgr = BattleManager(EventBus())
        battle = _make_battle()
        blue = _make_units("blue", 10)
        red = _make_units("red", 10)
        mgr.auto_resolve(
            battle, {"blue": blue, "red": red}, np.random.default_rng(42)
        )
        # Some units should be destroyed
        blue_destroyed = sum(1 for u in blue if u.status == UnitStatus.DESTROYED)
        red_destroyed = sum(1 for u in red if u.status == UnitStatus.DESTROYED)
        assert blue_destroyed + red_destroyed > 0

    def test_loss_fractions_in_result(self):
        mgr = BattleManager(EventBus())
        battle = _make_battle()
        blue = _make_units("blue", 10)
        red = _make_units("red", 10)
        result = mgr.auto_resolve(
            battle, {"blue": blue, "red": red}, np.random.default_rng(42)
        )
        assert "blue" in result.side_losses
        assert "red" in result.side_losses
        assert 0.0 <= result.side_losses["blue"] <= 1.0
        assert 0.0 <= result.side_losses["red"] <= 1.0

    def test_duration_positive(self):
        mgr = BattleManager(EventBus())
        battle = _make_battle()
        blue = _make_units("blue", 5)
        red = _make_units("red", 5)
        result = mgr.auto_resolve(
            battle, {"blue": blue, "red": red}, np.random.default_rng(42)
        )
        assert result.duration_s > 0

    def test_deterministic_with_same_seed(self):
        """Same seed should produce identical results."""
        results = []
        for _ in range(2):
            mgr = BattleManager(EventBus())
            battle = _make_battle()
            blue = _make_units("blue", 8)
            red = _make_units("red", 6)
            result = mgr.auto_resolve(
                battle, {"blue": blue, "red": red}, np.random.default_rng(42)
            )
            results.append(result)
        assert results[0].winner == results[1].winner
        assert results[0].side_losses == pytest.approx(results[1].side_losses)

    def test_config_disabled_by_default(self):
        """Auto-resolve should be disabled by default."""
        config = BattleConfig()
        assert config.auto_resolve_enabled is False
        assert config.auto_resolve_max_units == 0

    def test_single_side_battle(self):
        """Single-side battle returns that side as winner."""
        mgr = BattleManager(EventBus())
        battle = BattleContext(
            battle_id="one_sided",
            start_tick=0,
            start_time=datetime.now(),
            involved_sides=["blue"],
        )
        blue = _make_units("blue", 5)
        result = mgr.auto_resolve(
            battle, {"blue": blue}, np.random.default_rng(42)
        )
        assert result.winner == "blue"

    def test_empty_side_loses(self):
        """Side with no active units should lose."""
        mgr = BattleManager(EventBus())
        battle = _make_battle()
        blue = _make_units("blue", 5)
        red: list[Unit] = []
        result = mgr.auto_resolve(
            battle, {"blue": blue, "red": red}, np.random.default_rng(42)
        )
        assert result.winner == "blue"

    def test_morale_affects_outcome(self):
        """Low morale should weaken a side."""
        from stochastic_warfare.morale.state import MoraleState

        mgr = BattleManager(EventBus())
        battle1 = _make_battle()
        blue = _make_units("blue", 10)
        red = _make_units("red", 10)
        # Blue has steady morale, red has broken morale
        morale = {}
        for u in blue:
            morale[u.entity_id] = MoraleState.STEADY
        for u in red:
            morale[u.entity_id] = MoraleState.BROKEN

        result = mgr.auto_resolve(
            battle1, {"blue": blue, "red": red},
            np.random.default_rng(42), morale_states=morale,
        )
        # Blue should have an advantage
        assert result.side_losses["blue"] < result.side_losses["red"]

    def test_prng_isolation(self):
        """Auto-resolve should not affect other PRNG streams."""
        rng1 = np.random.default_rng(42)
        rng2 = np.random.default_rng(42)

        # Use rng1 for auto-resolve
        mgr = BattleManager(EventBus())
        battle = _make_battle()
        blue = _make_units("blue", 5)
        red = _make_units("red", 5)
        mgr.auto_resolve(battle, {"blue": blue, "red": red}, rng1)

        # rng1 state should differ from rng2 (it was consumed)
        val1 = rng1.random()
        val2 = rng2.random()
        # They should NOT be equal (rng1 was advanced by auto_resolve)
        assert val1 != val2

    def test_all_units_can_be_destroyed(self):
        """If one side is vastly outnumbered, all units may be destroyed."""
        mgr = BattleManager(EventBus())
        battle = _make_battle()
        blue = _make_units("blue", 20)
        red = _make_units("red", 1)
        mgr.auto_resolve(
            battle, {"blue": blue, "red": red}, np.random.default_rng(42)
        )
        red_active = sum(1 for u in red if u.status == UnitStatus.ACTIVE)
        # The single red unit should likely be destroyed
        assert red_active == 0

    def test_supply_affects_outcome(self):
        """Low supply should weaken a side."""
        mgr = BattleManager(EventBus())
        battle = _make_battle()
        blue = _make_units("blue", 10)
        red = _make_units("red", 10)
        supply = {}
        for u in blue:
            supply[u.entity_id] = 1.0
        for u in red:
            supply[u.entity_id] = 0.2  # Very low supply

        result = mgr.auto_resolve(
            battle, {"blue": blue, "red": red},
            np.random.default_rng(42), supply_states=supply,
        )
        assert result.side_losses["blue"] < result.side_losses["red"]

    def test_no_units_no_crash(self):
        """Empty units_by_side should not crash."""
        mgr = BattleManager(EventBus())
        battle = _make_battle()
        result = mgr.auto_resolve(
            battle, {"blue": [], "red": []}, np.random.default_rng(42)
        )
        assert isinstance(result, AutoResolveResult)

    def test_destroyed_units_excluded(self):
        """Already-destroyed units should not count in combat power."""
        mgr = BattleManager(EventBus())
        battle = _make_battle()
        blue = _make_units("blue", 10)
        red = _make_units("red", 10)
        # Destroy half of red before auto-resolve
        for u in red[:5]:
            object.__setattr__(u, "status", UnitStatus.DESTROYED)
        result = mgr.auto_resolve(
            battle, {"blue": blue, "red": red}, np.random.default_rng(42)
        )
        assert result.winner == "blue"

    def test_auto_resolve_vs_normal_battle_backward_compat(self):
        """With auto_resolve disabled, BattleManager behaves as before."""
        config = BattleConfig(auto_resolve_enabled=False)
        mgr = BattleManager(EventBus(), config)
        # detect_engagement should still work
        blue = _make_units("blue", 5, Position(0, 0))
        red = _make_units("red", 5, Position(100, 0))
        new_battles = mgr.detect_engagement({"blue": blue, "red": red})
        assert len(new_battles) > 0
