"""Phase 85: LOD tier classification tests.

Validates that _classify_lod_tiers() assigns ACTIVE/NEARBY/DISTANT tiers
based on distance to nearest enemy, weapon/sensor ranges, and hysteresis.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import UnitStatus
from stochastic_warfare.simulation.battle import BattleManager, UnitLodTier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_unit(uid: str, easting: float, northing: float = 0.0) -> SimpleNamespace:
    """Lightweight unit mock."""
    return SimpleNamespace(
        entity_id=uid,
        position=Position(easting, northing, 0.0),
        status=UnitStatus.ACTIVE,
        side="blue",
    )


def _make_weapon(max_range_m: float) -> tuple:
    """Weapon tuple matching ctx.unit_weapons format: (instance, ammo_defs)."""
    defn = SimpleNamespace(max_range_m=max_range_m)
    inst = SimpleNamespace(definition=defn)
    return (inst, [])


def _make_sensor(effective_range: float) -> SimpleNamespace:
    return SimpleNamespace(effective_range=effective_range)


def _make_battle(ticks: int = 1) -> SimpleNamespace:
    return SimpleNamespace(ticks_executed=ticks)


def _make_ctx(
    cal: dict | None = None,
    unit_weapons: dict | None = None,
    unit_sensors: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        calibration=cal or {},
        unit_weapons=unit_weapons or {},
        unit_sensors=unit_sensors or {},
    )


def _make_bm() -> BattleManager:
    return BattleManager(event_bus=EventBus())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLodTierClassification:
    """Core _classify_lod_tiers() behavior."""

    def test_lod_disabled_returns_all_active(self):
        """enable_lod=False → all ACTIVE units in full_update."""
        bm = _make_bm()
        u1 = _make_unit("u1", 0.0)
        u2 = _make_unit("u2", 100_000.0)
        units_by_side = {"blue": [u1, u2]}
        enemy = np.array([[50_000.0, 0.0]])
        ctx = _make_ctx(cal={"enable_lod": False})
        result = bm._classify_lod_tiers(
            ctx, units_by_side, {"blue": enemy}, _make_battle(),
        )
        assert result == {"u1", "u2"}

    def test_unit_within_weapon_range_active(self):
        """Unit within 2x weapon range → ACTIVE tier."""
        bm = _make_bm()
        u = _make_unit("u1", 0.0)
        units_by_side = {"blue": [u]}
        # Enemy at 500m, weapon range 2000m → active_thresh = 4000m
        enemy = np.array([[500.0, 0.0]])
        ctx = _make_ctx(
            cal={"enable_lod": True},
            unit_weapons={"u1": [_make_weapon(2000.0)]},
            unit_sensors={"u1": [_make_sensor(10000.0)]},
        )
        result = bm._classify_lod_tiers(
            ctx, units_by_side, {"blue": enemy}, _make_battle(),
        )
        assert "u1" in result
        assert bm._lod_tiers["u1"] == UnitLodTier.ACTIVE

    def test_unit_at_sensor_range_nearby(self):
        """Unit beyond weapon but within sensor range → NEARBY."""
        bm = _make_bm()
        u = _make_unit("u1", 0.0)
        units_by_side = {"blue": [u]}
        # Enemy at 8000m; weapon 2000m (thresh=4000m), sensor 10000m
        enemy = np.array([[8000.0, 0.0]])
        ctx = _make_ctx(
            cal={"enable_lod": True},
            unit_weapons={"u1": [_make_weapon(2000.0)]},
            unit_sensors={"u1": [_make_sensor(10000.0)]},
        )
        result = bm._classify_lod_tiers(
            ctx, units_by_side, {"blue": enemy}, _make_battle(),
        )
        assert bm._lod_tiers["u1"] == UnitLodTier.NEARBY

    def test_unit_beyond_sensor_range_distant(self):
        """Unit beyond sensor range → DISTANT."""
        bm = _make_bm()
        u = _make_unit("u1", 0.0)
        units_by_side = {"blue": [u]}
        enemy = np.array([[50_000.0, 0.0]])
        ctx = _make_ctx(
            cal={"enable_lod": True},
            unit_weapons={"u1": [_make_weapon(2000.0)]},
            unit_sensors={"u1": [_make_sensor(10000.0)]},
        )
        result = bm._classify_lod_tiers(
            ctx, units_by_side, {"blue": enemy}, _make_battle(),
        )
        assert bm._lod_tiers["u1"] == UnitLodTier.DISTANT

    def test_distant_skipped_non_update_tick(self):
        """DISTANT unit on non-multiple tick not in full_update."""
        bm = _make_bm()
        u = _make_unit("u1", 0.0)
        units_by_side = {"blue": [u]}
        enemy = np.array([[50_000.0, 0.0]])
        ctx = _make_ctx(
            cal={"enable_lod": True, "lod_distant_interval": 20},
            unit_weapons={"u1": [_make_weapon(2000.0)]},
            unit_sensors={"u1": [_make_sensor(10000.0)]},
        )
        # Force DISTANT tier first
        bm._lod_tiers["u1"] = UnitLodTier.DISTANT
        result = bm._classify_lod_tiers(
            ctx, units_by_side, {"blue": enemy}, _make_battle(ticks=3),
        )
        assert "u1" not in result

    def test_distant_included_on_update_tick(self):
        """DISTANT unit on interval-multiple tick IS in full_update."""
        bm = _make_bm()
        u = _make_unit("u1", 0.0)
        units_by_side = {"blue": [u]}
        enemy = np.array([[50_000.0, 0.0]])
        ctx = _make_ctx(
            cal={"enable_lod": True, "lod_distant_interval": 20},
            unit_weapons={"u1": [_make_weapon(2000.0)]},
            unit_sensors={"u1": [_make_sensor(10000.0)]},
        )
        bm._lod_tiers["u1"] = UnitLodTier.DISTANT
        result = bm._classify_lod_tiers(
            ctx, units_by_side, {"blue": enemy}, _make_battle(ticks=20),
        )
        assert "u1" in result

    def test_nearby_interval_scheduling(self):
        """NEARBY units only in full_update on interval ticks."""
        bm = _make_bm()
        u = _make_unit("u1", 0.0)
        units_by_side = {"blue": [u]}
        enemy = np.array([[8000.0, 0.0]])
        ctx = _make_ctx(
            cal={"enable_lod": True, "lod_nearby_interval": 5},
            unit_weapons={"u1": [_make_weapon(2000.0)]},
            unit_sensors={"u1": [_make_sensor(10000.0)]},
        )
        bm._lod_tiers["u1"] = UnitLodTier.NEARBY
        # Tick 3 (not multiple of 5) → not in full_update
        result3 = bm._classify_lod_tiers(
            ctx, units_by_side, {"blue": enemy}, _make_battle(ticks=3),
        )
        assert "u1" not in result3
        # Tick 5 → in full_update
        result5 = bm._classify_lod_tiers(
            ctx, units_by_side, {"blue": enemy}, _make_battle(ticks=5),
        )
        assert "u1" in result5

    def test_hysteresis_prevents_demotion_flicker(self):
        """Tier demotion requires hysteresis_ticks consecutive ticks."""
        bm = _make_bm()
        u = _make_unit("u1", 0.0)
        units_by_side = {"blue": [u]}
        # Enemy far away → should demote to DISTANT, but hysteresis delays it
        enemy_far = np.array([[50_000.0, 0.0]])
        ctx = _make_ctx(
            cal={"enable_lod": True, "lod_hysteresis_ticks": 3},
            unit_weapons={"u1": [_make_weapon(2000.0)]},
            unit_sensors={"u1": [_make_sensor(10000.0)]},
        )
        # Start as ACTIVE
        bm._lod_tiers["u1"] = UnitLodTier.ACTIVE

        # Tick 1: propose demotion, still ACTIVE
        bm._classify_lod_tiers(ctx, units_by_side, {"blue": enemy_far}, _make_battle(1))
        assert bm._lod_tiers["u1"] == UnitLodTier.ACTIVE

        # Tick 2: still holding
        bm._classify_lod_tiers(ctx, units_by_side, {"blue": enemy_far}, _make_battle(2))
        assert bm._lod_tiers["u1"] == UnitLodTier.ACTIVE

        # Tick 3: hysteresis met → demoted
        bm._classify_lod_tiers(ctx, units_by_side, {"blue": enemy_far}, _make_battle(3))
        assert bm._lod_tiers["u1"] == UnitLodTier.DISTANT

    def test_promotion_is_immediate(self):
        """Tier promotion (toward ACTIVE) is instant, no hysteresis."""
        bm = _make_bm()
        u = _make_unit("u1", 0.0)
        units_by_side = {"blue": [u]}
        bm._lod_tiers["u1"] = UnitLodTier.DISTANT
        # Enemy moves close → within weapon range
        enemy_close = np.array([[500.0, 0.0]])
        ctx = _make_ctx(
            cal={"enable_lod": True},
            unit_weapons={"u1": [_make_weapon(2000.0)]},
            unit_sensors={"u1": [_make_sensor(10000.0)]},
        )
        result = bm._classify_lod_tiers(
            ctx, units_by_side, {"blue": enemy_close}, _make_battle(1),
        )
        assert bm._lod_tiers["u1"] == UnitLodTier.ACTIVE
        assert "u1" in result

    def test_damage_promotes_to_active(self):
        """Unit in _lod_promoted set → classified as ACTIVE."""
        bm = _make_bm()
        u = _make_unit("u1", 0.0)
        units_by_side = {"blue": [u]}
        enemy = np.array([[50_000.0, 0.0]])
        ctx = _make_ctx(
            cal={"enable_lod": True},
            unit_weapons={"u1": [_make_weapon(2000.0)]},
            unit_sensors={"u1": [_make_sensor(10000.0)]},
        )
        bm._lod_tiers["u1"] = UnitLodTier.DISTANT
        bm._lod_promoted.add("u1")
        result = bm._classify_lod_tiers(
            ctx, units_by_side, {"blue": enemy}, _make_battle(1),
        )
        assert bm._lod_tiers["u1"] == UnitLodTier.ACTIVE
        assert "u1" in result
        # Promoted set should be cleared
        assert len(bm._lod_promoted) == 0

    def test_no_enemies_all_distant(self):
        """Empty enemy arrays → all units DISTANT."""
        bm = _make_bm()
        u = _make_unit("u1", 0.0)
        units_by_side = {"blue": [u]}
        ctx = _make_ctx(
            cal={"enable_lod": True, "lod_distant_interval": 20},
            unit_weapons={"u1": [_make_weapon(2000.0)]},
            unit_sensors={"u1": [_make_sensor(10000.0)]},
        )
        bm._lod_tiers["u1"] = UnitLodTier.DISTANT
        result = bm._classify_lod_tiers(
            ctx, units_by_side, {"blue": np.empty((0, 2))}, _make_battle(3),
        )
        assert bm._lod_tiers["u1"] == UnitLodTier.DISTANT
        assert "u1" not in result  # tick 3 not multiple of 20

    def test_custom_intervals(self):
        """Custom lod_nearby_interval and lod_distant_interval respected."""
        bm = _make_bm()
        u_near = _make_unit("u_near", 0.0)
        u_far = _make_unit("u_far", 0.0)
        units_by_side = {"blue": [u_near, u_far]}
        enemy = np.array([[8000.0, 0.0]])
        enemy_far = np.array([[50_000.0, 0.0]])
        ctx = _make_ctx(
            cal={"enable_lod": True, "lod_nearby_interval": 3, "lod_distant_interval": 10},
            unit_weapons={
                "u_near": [_make_weapon(2000.0)],
                "u_far": [_make_weapon(2000.0)],
            },
            unit_sensors={
                "u_near": [_make_sensor(10000.0)],
                "u_far": [_make_sensor(10000.0)],
            },
        )
        bm._lod_tiers["u_near"] = UnitLodTier.NEARBY
        bm._lod_tiers["u_far"] = UnitLodTier.DISTANT
        # Tick 9: multiple of 3 but not 10
        result = bm._classify_lod_tiers(
            ctx, units_by_side, {"blue": enemy_far}, _make_battle(ticks=9),
        )
        assert "u_near" in result
        assert "u_far" not in result
        # Tick 10: multiple of both
        result10 = bm._classify_lod_tiers(
            ctx, units_by_side, {"blue": enemy_far}, _make_battle(ticks=10),
        )
        assert "u_far" in result10

    def test_lod_deterministic(self):
        """Same inputs produce identical tier assignments."""
        results = []
        for _ in range(2):
            bm = _make_bm()
            u = _make_unit("u1", 0.0)
            enemy = np.array([[8000.0, 0.0]])
            ctx = _make_ctx(
                cal={"enable_lod": True},
                unit_weapons={"u1": [_make_weapon(2000.0)]},
                unit_sensors={"u1": [_make_sensor(10000.0)]},
            )
            result = bm._classify_lod_tiers(
                ctx, {"blue": [u]}, {"blue": enemy}, _make_battle(5),
            )
            results.append((dict(bm._lod_tiers), result))
        assert results[0] == results[1]

    def test_lod_state_checkpoint(self):
        """get_state()/set_state() roundtrip preserves LOD dicts."""
        bm = _make_bm()
        bm._lod_tiers = {"u1": UnitLodTier.NEARBY, "u2": UnitLodTier.DISTANT}
        bm._lod_pending_tiers = {"u1": UnitLodTier.DISTANT}
        bm._lod_pending_counts = {"u1": 2}

        state = bm.get_state()
        assert "lod_tiers" in state
        assert state["lod_tiers"]["u1"] == UnitLodTier.NEARBY

        bm2 = _make_bm()
        bm2.set_state(state)
        assert bm2._lod_tiers == {"u1": int(UnitLodTier.NEARBY), "u2": int(UnitLodTier.DISTANT)}
        assert bm2._lod_pending_tiers == {"u1": int(UnitLodTier.DISTANT)}
        assert bm2._lod_pending_counts == {"u1": 2}
        assert bm2._lod_promoted == set()
