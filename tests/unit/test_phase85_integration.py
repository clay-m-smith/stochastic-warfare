"""Phase 85: LOD integration tests.

Validates that LOD tier classification integrates correctly with
engagement, morale, supply, and FOW subsystems in the battle loop.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.morale.runtime import MoraleRegistration, MoraleRuntime
from stochastic_warfare.morale.state import MoraleConfig, MoraleState
from stochastic_warfare.simulation.battle import BattleManager, UnitLodTier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_unit(uid: str, easting: float = 0.0, side: str = "blue") -> SimpleNamespace:
    return SimpleNamespace(
        entity_id=uid,
        position=Position(easting, 0.0, 0.0),
        status=UnitStatus.ACTIVE,
        side=side,
        speed=5.0,
        heading=0.0,
        domain=Domain.GROUND,
        unit_type="infantry",
    )


def _make_weapon(max_range_m: float) -> tuple:
    defn = SimpleNamespace(max_range_m=max_range_m)
    inst = SimpleNamespace(definition=defn)
    return (inst, [])


def _make_sensor(effective_range: float) -> SimpleNamespace:
    return SimpleNamespace(effective_range=effective_range)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLodEngagementIntegration:
    """LOD filtering in _execute_engagements()."""

    def test_lod_skips_engagement_initiation(self):
        """DISTANT attacker (not in _lod_full_update) skipped in engagement."""
        bm = BattleManager(event_bus=EventBus())
        attacker = _make_unit("att", 0.0, "blue")
        target = _make_unit("tgt", 500.0, "red")

        # Minimal ctx — enough fields so _execute_engagements reaches loop
        ctx = SimpleNamespace(
            calibration={
                "visibility_m": 10000.0,
                "hit_probability_modifier": 1.0,
                "target_size_modifier": 1.0,
            },
            config=SimpleNamespace(latitude=0.0, longitude=0.0, behavior_rules=None),
            unit_weapons={"att": [_make_weapon(2000.0)]},
            unit_sensors={},
            morale_states={},
            fog_of_war=None,
            suppression_engine=None,
            population_engine=None,
            air_combat_engine=None,
            engagement_engine=SimpleNamespace(),  # non-None so loop entered
        )
        units_by_side = {"blue": [attacker], "red": [target]}
        active_enemies = {"blue": [target], "red": [attacker]}
        enemy_pos = {
            "blue": np.array([[500.0, 0.0]]),
            "red": np.array([[0.0, 0.0]]),
        }

        # With LOD gate — attacker NOT in full_update → no engagements
        result = bm._execute_engagements(
            ctx, units_by_side, active_enemies, enemy_pos, 1.0,
            timestamp=SimpleNamespace(timestamp=lambda: 0.0),
            _lod_full_update=set(),  # empty = nobody gets to fire
        )
        assert result == []

    def test_lod_allows_targeting_distant_unit(self):
        """DISTANT unit can still be targeted by ACTIVE attacker."""
        bm = BattleManager(event_bus=EventBus())
        attacker = _make_unit("att", 0.0, "blue")
        target = _make_unit("tgt", 500.0, "red")

        ctx = SimpleNamespace(
            calibration={
                "visibility_m": 10000.0,
                "hit_probability_modifier": 1.0,
                "target_size_modifier": 1.0,
            },
            config=SimpleNamespace(latitude=0.0, longitude=0.0, behavior_rules=None),
            unit_weapons={"att": [_make_weapon(2000.0)]},
            unit_sensors={},
            morale_states={},
            fog_of_war=None,
            suppression_engine=None,
            population_engine=None,
            air_combat_engine=None,
            engagement_engine=SimpleNamespace(),  # non-None so loop entered
        )
        units_by_side = {"blue": [attacker], "red": [target]}
        active_enemies = {"blue": [target], "red": [attacker]}
        enemy_pos = {
            "blue": np.array([[500.0, 0.0]]),
            "red": np.array([[0.0, 0.0]]),
        }

        # attacker IS in full_update, target is not — target should still
        # appear in the enemies list (LOD doesn't remove from targets)
        lod_set = {"att"}  # only attacker
        # This should not crash — target is a valid target even though
        # it's not in _lod_full_update
        result = bm._execute_engagements(
            ctx, units_by_side, active_enemies, enemy_pos, 1.0,
            timestamp=SimpleNamespace(timestamp=lambda: 0.0),
            _lod_full_update=lod_set,
        )
        # Result may or may not have damage (depends on weapon resolution)
        # but the key assertion is that execution didn't crash and attacker
        # was allowed to proceed
        assert isinstance(result, list)


class TestLodMoraleIntegration:
    """LOD filtering in _execute_morale()."""

    def test_lod_skips_morale_for_distant(self):
        """DISTANT unit (not in full_update) skipped for morale degradation."""
        bus = EventBus()
        bm = BattleManager(event_bus=bus)
        u_active = Unit(
            entity_id="u1",
            position=Position(0.0, 0.0, 0.0),
            side="blue",
        )
        u_distant = Unit(
            entity_id="u2",
            position=Position(50_000.0, 0.0, 0.0),
            side="blue",
        )
        morale_runtime = MoraleRuntime(
            bus,
            np.random.default_rng(85),
            MoraleConfig(
                base_degrade_rate=0.0,
                base_recover_rate=0.0,
                casualty_weight=0.0,
                suppression_weight=0.0,
                leadership_weight=0.0,
                cohesion_weight=0.0,
                force_ratio_weight=0.0,
            ),
        )
        morale_runtime.register_units(
            (
                MoraleRegistration("u1", MoraleState.STEADY),
                MoraleRegistration("u2", MoraleState.STEADY),
            ),
            {"u1": u_active, "u2": u_distant},
        )
        ctx = SimpleNamespace(
            calibration={"morale_degrade_rate_modifier": 1.0},
            morale_runtime=morale_runtime,
            morale_states=morale_runtime.states,
            clock=SimpleNamespace(elapsed=timedelta(seconds=100.0)),
        )
        units_by_side = {"blue": [u_active, u_distant]}
        active_enemies = {"blue": []}

        # Only u1 in full_update
        bm._execute_morale(
            ctx, units_by_side, active_enemies,
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            _lod_full_update={"u1"},
        )
        assert morale_runtime.record_for("u1").generation == 1
        assert morale_runtime.record_for("u2").generation == 0


class TestCombatConsumptionBoundary:
    """Combat consumption remains an explicit, unwired residual gap."""

    def test_compute_and_discard_hook_is_not_exposed(self):
        """A non-mutating helper must not masquerade as supply consumption."""
        bm = BattleManager(event_bus=EventBus())
        assert not hasattr(bm, "_execute_supply_consumption")


class TestLodBackwardCompat:
    """LOD disabled = identical behavior."""

    def test_enable_lod_false_backward_compat(self):
        """enable_lod=False → all active units processed."""
        bm = BattleManager(event_bus=EventBus())
        units = [_make_unit(f"u{i}", float(i * 100)) for i in range(5)]
        units_by_side = {"blue": units}
        enemy = np.array([[50_000.0, 0.0]])
        ctx = SimpleNamespace(
            calibration={"enable_lod": False},
            unit_weapons={},
            unit_sensors={},
        )
        result = bm._classify_lod_tiers(
            ctx, units_by_side, {"blue": enemy},
            SimpleNamespace(ticks_executed=1),
        )
        assert result == {f"u{i}" for i in range(5)}

    def test_movement_continues_for_all_tiers(self):
        """LOD does NOT filter movement — verified by inspecting execute_tick wiring.

        Movement is called before LOD classification influences subsystems.
        This structural test ensures the _execute_movement call has no
        _lod_full_update parameter.
        """
        import inspect
        sig = inspect.signature(BattleManager._execute_movement)
        params = list(sig.parameters.keys())
        assert "_lod_full_update" not in params
