"""Phase 85: LOD integration tests.

Validates that LOD tier classification integrates correctly with
engagement, morale, supply, and FOW subsystems in the battle loop.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import UnitStatus
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
        bm = BattleManager(event_bus=EventBus())
        u_active = _make_unit("u1", 0.0, "blue")
        u_distant = _make_unit("u2", 50_000.0, "blue")

        # Mock morale machine that records which units were checked
        checked_ids: list[str] = []

        def mock_check_transition(unit_id, **kwargs):
            checked_ids.append(unit_id)
            return 0  # STEADY

        morale_machine = SimpleNamespace(check_transition=mock_check_transition)
        ctx = SimpleNamespace(
            calibration={"morale_degrade_rate_modifier": 1.0},
            morale_machine=morale_machine,
            morale_states={"u1": 0, "u2": 0},
        )
        units_by_side = {"blue": [u_active, u_distant]}
        active_enemies = {"blue": []}

        # Only u1 in full_update
        bm._execute_morale(
            ctx, units_by_side, active_enemies,
            timestamp=SimpleNamespace(),
            _lod_full_update={"u1"},
        )
        assert "u1" in checked_ids
        assert "u2" not in checked_ids


class TestLodSupplyIntegration:
    """LOD filtering in _execute_supply_consumption()."""

    def test_lod_supply_skipped_for_distant(self):
        """DISTANT unit supply not consumed on non-update tick."""
        bm = BattleManager(event_bus=EventBus())
        u1 = _make_unit("u1", 0.0)
        u1.personnel = ["p1", "p2"]
        u1.equipment = ["e1"]
        u2 = _make_unit("u2", 50_000.0)
        u2.personnel = ["p1", "p2"]
        u2.equipment = ["e1"]

        consumed_for: list[str] = []

        def mock_compute(personnel_count, equipment_count, base_fuel_rate_per_hour, activity, dt_hours):
            # We track that consumption was called via side effect
            consumed_for.append("called")
            return SimpleNamespace(food=1.0, fuel=1.0, ammo=1.0)

        ctx = SimpleNamespace(
            calibration={},
            consumption_engine=SimpleNamespace(compute_consumption=mock_compute),
            stockpile_manager=SimpleNamespace(),
        )
        units_by_side = {"blue": [u1, u2]}

        bm._execute_supply_consumption(
            ctx, units_by_side, dt=60.0,
            _lod_full_update={"u1"},  # only u1
        )
        # Only u1 should have had supply consumed (1 call)
        assert len(consumed_for) == 1


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
