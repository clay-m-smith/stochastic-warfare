"""Phase 43 — Domain-Specific Resolution tests.

Tests for era-aware engagement routing (43a), indirect fire routing (43b),
and naval domain routing (43c).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.simulation.battle import (
    BattleConfig,
    BattleManager,
    _apply_aggregate_casualties,
    _apply_indirect_fire_result,
    _apply_melee_result,
    _get_formation_firepower,
    _infer_melee_type,
    _infer_missile_type,
    _route_naval_engagement,
    _MELEE_RANGE_M,
    _INDIRECT_FIRE_CATEGORIES,
)


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def rng():
    return np.random.default_rng(42)


def _make_unit(
    entity_id: str = "u1",
    side: str = "blue",
    domain: Domain = Domain.GROUND,
    personnel_count: int = 100,
    position: Position | None = None,
    speed: float = 0.0,
) -> Unit:
    """Create a minimal Unit for testing."""
    u = Unit.__new__(Unit)
    object.__setattr__(u, "entity_id", entity_id)
    object.__setattr__(u, "side", side)
    object.__setattr__(u, "domain", domain)
    object.__setattr__(u, "status", UnitStatus.ACTIVE)
    object.__setattr__(u, "position", position or Position(0.0, 0.0, 0.0))
    object.__setattr__(u, "speed", speed)
    object.__setattr__(u, "personnel", [MagicMock() for _ in range(personnel_count)])
    object.__setattr__(u, "posture", None)
    object.__setattr__(u, "training_level", 0.5)
    return u


def _make_wpn(
    weapon_id: str = "musket",
    category: str = "RIFLE",
    max_range_m: float = 300.0,
    rate_of_fire_rpm: float = 3.0,
    caliber_mm: float = 17.5,
    beam_power_kw: float = 0.0,
    min_range_m: float = 0.0,
) -> MagicMock:
    """Create a mock weapon instance."""
    definition = MagicMock()
    definition.weapon_id = weapon_id
    definition.category = category
    definition.max_range_m = max_range_m
    definition.rate_of_fire_rpm = rate_of_fire_rpm
    definition.caliber_mm = caliber_mm
    definition.beam_power_kw = beam_power_kw
    definition.min_range_m = min_range_m
    definition.requires_deployed = False
    definition.effective_target_domains.return_value = ["GROUND", "NAVAL"]
    definition.get_effective_range.return_value = max_range_m * 0.6

    def parsed_category():
        from stochastic_warfare.combat.ammunition import WeaponCategory
        return WeaponCategory[category.upper()]

    definition.parsed_category = parsed_category

    wpn_inst = MagicMock()
    wpn_inst.definition = definition
    wpn_inst.can_fire.return_value = True
    return wpn_inst


def _make_ammo(ammo_id: str = "ball") -> MagicMock:
    ammo = MagicMock()
    ammo.ammo_id = ammo_id
    return ammo


def _make_ctx(
    era: str = "modern",
    engagement_engine: Any = None,
    volley_fire_engine: Any = None,
    archery_engine: Any = None,
    melee_engine: Any = None,
    indirect_fire_engine: Any = None,
    naval_surface_engine: Any = None,
    naval_subsurface_engine: Any = None,
    naval_gunnery_engine: Any = None,
    naval_gunfire_support_engine: Any = None,
    suppression_engine: Any = None,
    formation_napoleonic_engine: Any = None,
    units: list[Unit] | None = None,
) -> SimpleNamespace:
    """Create a minimal simulation context for testing."""
    config = SimpleNamespace(
        era=era,
        sides=[
            SimpleNamespace(side="blue", experience_level=0.7),
            SimpleNamespace(side="red", experience_level=0.5),
        ],
        behavior_rules={},
    )
    clock = SimpleNamespace(elapsed=SimpleNamespace(total_seconds=lambda: 100.0))
    morale_states: dict[str, Any] = {}
    if units:
        for u in units:
            morale_states[u.entity_id] = 1  # STEADY

    ctx = SimpleNamespace(
        config=config,
        clock=clock,
        engagement_engine=engagement_engine or MagicMock(),
        volley_fire_engine=volley_fire_engine,
        archery_engine=archery_engine,
        melee_engine=melee_engine,
        indirect_fire_engine=indirect_fire_engine,
        naval_surface_engine=naval_surface_engine,
        naval_subsurface_engine=naval_subsurface_engine,
        naval_gunnery_engine=naval_gunnery_engine,
        naval_gunfire_support_engine=naval_gunfire_support_engine,
        suppression_engine=suppression_engine,
        formation_napoleonic_engine=formation_napoleonic_engine,
        detection_engine=None,
        roe_engine=None,
        dew_engine=None,
        unit_weapons={},
        unit_sensors={},
        morale_states=morale_states,
        calibration={},
        heightmap=None,
        classification=None,
        trench_engine=None,
        infrastructure_manager=None,
        obstacle_manager=None,
    )
    return ctx


# ===========================================================================
# 43a: Era-Aware Engagement Routing
# ===========================================================================


class TestVolleyFireRouting:
    """Test that Napoleonic/WW1 RIFLE weapons route to volley fire."""

    def test_napoleonic_musket_routes_to_volley_fire(self):
        vf = MagicMock()
        vf.fire_volley.return_value = SimpleNamespace(
            casualties=5, suppression_value=0.2, smoke_generated=0.1, ammo_consumed=100,
        )
        attacker = _make_unit("att", "blue", personnel_count=100)
        target = _make_unit("tgt", "red", personnel_count=200, position=Position(150.0, 0.0, 0.0))
        wpn = _make_wpn("brown_bess", "RIFLE", max_range_m=200.0)

        ctx = _make_ctx(era="napoleonic", volley_fire_engine=vf, units=[attacker, target])
        ctx.unit_weapons = {"att": [(wpn, [_make_ammo()])]}
        ctx.unit_sensors = {}
        ctx.units_by_side = {"blue": [attacker], "red": [target]}

        bm = BattleManager(MagicMock(), config=BattleConfig())
        pending = bm._execute_engagements(
            ctx,
            {"blue": [attacker]},
            {"blue": [target]},
            {"blue": np.array([[150.0, 0.0]])},
            dt=10.0,
            timestamp=datetime(2000, 1, 1),
        )

        vf.fire_volley.assert_called_once()
        call_kwargs = vf.fire_volley.call_args
        assert call_kwargs[1]["n_muskets"] == 100 or call_kwargs[0][0] == 100

    def test_napoleonic_cannon_routes_to_volley_fire(self):
        vf = MagicMock()
        vf.fire_volley.return_value = SimpleNamespace(
            casualties=3, suppression_value=0.3, smoke_generated=0.2, ammo_consumed=6,
        )
        attacker = _make_unit("att", "blue", personnel_count=6)
        target = _make_unit("tgt", "red", personnel_count=200, position=Position(500.0, 0.0, 0.0))
        wpn = _make_wpn("12pdr_cannon", "CANNON", max_range_m=1000.0)

        ctx = _make_ctx(era="napoleonic", volley_fire_engine=vf, units=[attacker, target])
        ctx.unit_weapons = {"att": [(wpn, [_make_ammo()])]}
        ctx.unit_sensors = {}
        ctx.units_by_side = {"blue": [attacker], "red": [target]}

        bm = BattleManager(MagicMock(), config=BattleConfig())
        bm._execute_engagements(
            ctx, {"blue": [attacker]}, {"blue": [target]},
            {"blue": np.array([[500.0, 0.0]])}, dt=10.0, timestamp=datetime(2000, 1, 1),
        )
        vf.fire_volley.assert_called_once()

    def test_ww1_rifle_routes_to_volley_fire(self):
        vf = MagicMock()
        vf.fire_volley.return_value = SimpleNamespace(
            casualties=8, suppression_value=0.3, smoke_generated=0.0, ammo_consumed=30,
        )
        attacker = _make_unit("att", "blue", personnel_count=30)
        target = _make_unit("tgt", "red", personnel_count=100, position=Position(200.0, 0.0, 0.0))
        wpn = _make_wpn("lee_enfield", "RIFLE", max_range_m=800.0)

        ctx = _make_ctx(era="ww1", volley_fire_engine=vf, units=[attacker, target])
        ctx.unit_weapons = {"att": [(wpn, [_make_ammo()])]}
        ctx.unit_sensors = {}
        ctx.units_by_side = {"blue": [attacker], "red": [target]}

        bm = BattleManager(MagicMock(), config=BattleConfig())
        bm._execute_engagements(
            ctx, {"blue": [attacker]}, {"blue": [target]},
            {"blue": np.array([[200.0, 0.0]])}, dt=10.0, timestamp=datetime(2000, 1, 1),
        )
        vf.fire_volley.assert_called_once()
        assert vf.fire_volley.call_args[1].get("is_rifle", vf.fire_volley.call_args[0][2] if len(vf.fire_volley.call_args[0]) > 2 else None) is True or \
               vf.fire_volley.call_args[1].get("is_rifle") is True

    def test_ww1_mg_uses_standard_engagement(self):
        """Machine guns in WW1 fall through to standard direct fire."""
        eng = MagicMock()
        eng.route_engagement.return_value = SimpleNamespace(
            engaged=True,
            hit_result=SimpleNamespace(hit=False),
            damage_result=None,
        )
        attacker = _make_unit("att", "blue", personnel_count=4)
        target = _make_unit("tgt", "red", personnel_count=100, position=Position(300.0, 0.0, 0.0))
        wpn = _make_wpn("maxim_mg", "MACHINE_GUN", max_range_m=2000.0)

        ctx = _make_ctx(era="ww1", engagement_engine=eng, units=[attacker, target])
        ctx.unit_weapons = {"att": [(wpn, [_make_ammo()])]}
        ctx.unit_sensors = {}
        ctx.units_by_side = {"blue": [attacker], "red": [target]}

        bm = BattleManager(MagicMock(), config=BattleConfig())
        bm._execute_engagements(
            ctx, {"blue": [attacker]}, {"blue": [target]},
            {"blue": np.array([[300.0, 0.0]])}, dt=10.0, timestamp=datetime(2000, 1, 1),
        )
        eng.route_engagement.assert_called_once()

    def test_modern_uses_standard_engagement(self):
        """Modern era always uses standard route_engagement()."""
        eng = MagicMock()
        eng.route_engagement.return_value = SimpleNamespace(
            engaged=True,
            hit_result=SimpleNamespace(hit=False),
            damage_result=None,
        )
        attacker = _make_unit("att", "blue", personnel_count=10)
        target = _make_unit("tgt", "red", personnel_count=10, position=Position(500.0, 0.0, 0.0))
        wpn = _make_wpn("m4_carbine", "RIFLE", max_range_m=600.0)

        ctx = _make_ctx(era="modern", engagement_engine=eng, units=[attacker, target])
        ctx.unit_weapons = {"att": [(wpn, [_make_ammo()])]}
        ctx.unit_sensors = {}
        ctx.units_by_side = {"blue": [attacker], "red": [target]}

        bm = BattleManager(MagicMock(), config=BattleConfig())
        bm._execute_engagements(
            ctx, {"blue": [attacker]}, {"blue": [target]},
            {"blue": np.array([[500.0, 0.0]])}, dt=10.0, timestamp=datetime(2000, 1, 1),
        )
        eng.route_engagement.assert_called_once()

    def test_ww2_uses_standard_engagement(self):
        """WW2 era uses standard route_engagement() for rifles."""
        eng = MagicMock()
        eng.route_engagement.return_value = SimpleNamespace(
            engaged=True,
            hit_result=SimpleNamespace(hit=False),
            damage_result=None,
        )
        attacker = _make_unit("att", "blue", personnel_count=10)
        target = _make_unit("tgt", "red", personnel_count=10, position=Position(300.0, 0.0, 0.0))
        wpn = _make_wpn("m1_garand", "RIFLE", max_range_m=500.0)

        ctx = _make_ctx(era="ww2", engagement_engine=eng, units=[attacker, target])
        ctx.unit_weapons = {"att": [(wpn, [_make_ammo()])]}
        ctx.unit_sensors = {}
        ctx.units_by_side = {"blue": [attacker], "red": [target]}

        bm = BattleManager(MagicMock(), config=BattleConfig())
        bm._execute_engagements(
            ctx, {"blue": [attacker]}, {"blue": [target]},
            {"blue": np.array([[300.0, 0.0]])}, dt=10.0, timestamp=datetime(2000, 1, 1),
        )
        eng.route_engagement.assert_called_once()

    def test_volley_fire_uses_personnel_count(self):
        vf = MagicMock()
        vf.fire_volley.return_value = SimpleNamespace(
            casualties=2, suppression_value=0.1, smoke_generated=0.0, ammo_consumed=50,
        )
        attacker = _make_unit("att", "blue", personnel_count=50)
        target = _make_unit("tgt", "red", personnel_count=100, position=Position(100.0, 0.0, 0.0))
        wpn = _make_wpn("charleville", "RIFLE", max_range_m=200.0)

        ctx = _make_ctx(era="napoleonic", volley_fire_engine=vf, units=[attacker, target])
        ctx.unit_weapons = {"att": [(wpn, [_make_ammo()])]}
        ctx.unit_sensors = {}
        ctx.units_by_side = {"blue": [attacker], "red": [target]}

        bm = BattleManager(MagicMock(), config=BattleConfig())
        bm._execute_engagements(
            ctx, {"blue": [attacker]}, {"blue": [target]},
            {"blue": np.array([[100.0, 0.0]])}, dt=10.0, timestamp=datetime(2000, 1, 1),
        )
        # Check n_muskets passed matches personnel count
        call_kw = vf.fire_volley.call_args[1]
        assert call_kw["n_muskets"] == 50

    def test_formation_firepower_fraction_read(self):
        """formation_napoleonic_engine queried for firepower fraction."""
        vf = MagicMock()
        vf.fire_volley.return_value = SimpleNamespace(
            casualties=2, suppression_value=0.1, smoke_generated=0.0, ammo_consumed=50,
        )
        form_eng = MagicMock()
        form_eng.get_firepower_fraction.return_value = 0.5

        attacker = _make_unit("att", "blue", personnel_count=50)
        target = _make_unit("tgt", "red", personnel_count=100, position=Position(100.0, 0.0, 0.0))
        wpn = _make_wpn("brown_bess", "RIFLE", max_range_m=200.0)

        ctx = _make_ctx(
            era="napoleonic",
            volley_fire_engine=vf,
            formation_napoleonic_engine=form_eng,
            units=[attacker, target],
        )
        ctx.unit_weapons = {"att": [(wpn, [_make_ammo()])]}
        ctx.unit_sensors = {}
        ctx.units_by_side = {"blue": [attacker], "red": [target]}

        bm = BattleManager(MagicMock(), config=BattleConfig())
        bm._execute_engagements(
            ctx, {"blue": [attacker]}, {"blue": [target]},
            {"blue": np.array([[100.0, 0.0]])}, dt=10.0, timestamp=datetime(2000, 1, 1),
        )
        form_eng.get_firepower_fraction.assert_called_once_with(attacker.entity_id)
        call_kw = vf.fire_volley.call_args[1]
        assert call_kw["formation_firepower_fraction"] == 0.5


class TestArcheryRouting:
    """Test that ancient RIFLE weapons route to archery engine."""

    def test_ancient_bow_routes_to_archery(self):
        ae = MagicMock()
        ae.fire_volley.return_value = SimpleNamespace(
            casualties=10, arrows_expended=100, suppression_value=0.1,
            armor_type_hit=None,
        )
        attacker = _make_unit("att", "blue", personnel_count=100)
        target = _make_unit("tgt", "red", personnel_count=200, position=Position(100.0, 0.0, 0.0))
        wpn = _make_wpn("english_longbow", "RIFLE", max_range_m=250.0)

        ctx = _make_ctx(era="ancient", archery_engine=ae, units=[attacker, target])
        ctx.unit_weapons = {"att": [(wpn, [_make_ammo()])]}
        ctx.unit_sensors = {}
        ctx.units_by_side = {"blue": [attacker], "red": [target]}

        bm = BattleManager(MagicMock(), config=BattleConfig())
        bm._execute_engagements(
            ctx, {"blue": [attacker]}, {"blue": [target]},
            {"blue": np.array([[100.0, 0.0]])}, dt=10.0, timestamp=datetime(2000, 1, 1),
        )
        ae.fire_volley.assert_called_once()
        call_kw = ae.fire_volley.call_args[1]
        assert call_kw["n_archers"] == 100
        assert call_kw["unit_id"] == "att"


class TestMeleeRouting:
    """Test that melee weapons route to melee engine."""

    def test_ancient_melee_routes_to_melee_engine(self):
        me = MagicMock()
        me.resolve_melee_round.return_value = SimpleNamespace(
            attacker_casualties=3, defender_casualties=8,
            attacker_morale_change=-0.1, defender_morale_change=-0.3,
            defender_routed=False, attacker_routed=False,
        )
        attacker = _make_unit("att", "blue", personnel_count=100)
        target = _make_unit("tgt", "red", personnel_count=80, position=Position(5.0, 0.0, 0.0))
        # max_range_m=0 so weapon selection doesn't filter by range
        wpn = _make_wpn("gladius", "MELEE", max_range_m=0)

        ctx = _make_ctx(era="ancient", melee_engine=me, units=[attacker, target])
        ctx.unit_weapons = {"att": [(wpn, [_make_ammo()])]}
        ctx.unit_sensors = {}
        ctx.units_by_side = {"blue": [attacker], "red": [target]}

        bm = BattleManager(MagicMock(), config=BattleConfig())
        bm._execute_engagements(
            ctx, {"blue": [attacker]}, {"blue": [target]},
            {"blue": np.array([[5.0, 0.0]])}, dt=10.0, timestamp=datetime(2000, 1, 1),
        )
        me.resolve_melee_round.assert_called_once()

    def test_napoleonic_melee_routes_correctly(self):
        me = MagicMock()
        me.resolve_melee_round.return_value = SimpleNamespace(
            attacker_casualties=5, defender_casualties=12,
            attacker_morale_change=-0.1, defender_morale_change=-0.4,
            defender_routed=False, attacker_routed=False,
        )
        attacker = _make_unit("att", "blue", personnel_count=60)
        target = _make_unit("tgt", "red", personnel_count=50, position=Position(8.0, 0.0, 0.0))
        wpn = _make_wpn("bayonet", "MELEE", max_range_m=0)

        ctx = _make_ctx(era="napoleonic", melee_engine=me, units=[attacker, target])
        ctx.unit_weapons = {"att": [(wpn, [_make_ammo()])]}
        ctx.unit_sensors = {}
        ctx.units_by_side = {"blue": [attacker], "red": [target]}

        bm = BattleManager(MagicMock(), config=BattleConfig())
        bm._execute_engagements(
            ctx, {"blue": [attacker]}, {"blue": [target]},
            {"blue": np.array([[8.0, 0.0]])}, dt=10.0, timestamp=datetime(2000, 1, 1),
        )
        me.resolve_melee_round.assert_called_once()

    def test_close_range_forces_melee(self):
        """Ranged weapon at melee range routes to melee engine."""
        me = MagicMock()
        me.resolve_melee_round.return_value = SimpleNamespace(
            attacker_casualties=2, defender_casualties=5,
            attacker_morale_change=-0.1, defender_morale_change=-0.2,
            defender_routed=False, attacker_routed=False,
        )
        attacker = _make_unit("att", "blue", personnel_count=30)
        # Position within _MELEE_RANGE_M (10m) but still within weapon range
        target = _make_unit("tgt", "red", personnel_count=30, position=Position(8.0, 0.0, 0.0))
        # Even though it's a RIFLE, range < _MELEE_RANGE_M → melee
        wpn = _make_wpn("brown_bess", "RIFLE", max_range_m=200.0)

        ctx = _make_ctx(era="napoleonic", melee_engine=me, units=[attacker, target])
        ctx.unit_weapons = {"att": [(wpn, [_make_ammo()])]}
        ctx.unit_sensors = {}
        ctx.units_by_side = {"blue": [attacker], "red": [target]}

        bm = BattleManager(MagicMock(), config=BattleConfig())
        bm._execute_engagements(
            ctx, {"blue": [attacker]}, {"blue": [target]},
            {"blue": np.array([[5.0, 0.0]])}, dt=10.0, timestamp=datetime(2000, 1, 1),
        )
        me.resolve_melee_round.assert_called_once()


# ===========================================================================
# 43a helper function tests
# ===========================================================================


class TestAggregateCasualties:
    """Test _apply_aggregate_casualties threshold mapping."""

    def test_high_casualties_destroy_unit(self):
        target = _make_unit("tgt", "red", personnel_count=100)
        pending: list[tuple[Unit, UnitStatus]] = []
        _apply_aggregate_casualties(60, target, pending, 0.5, 0.3)
        assert len(pending) == 1
        assert pending[0][1] == UnitStatus.DESTROYED

    def test_moderate_casualties_disable_unit(self):
        target = _make_unit("tgt", "red", personnel_count=100)
        pending: list[tuple[Unit, UnitStatus]] = []
        _apply_aggregate_casualties(35, target, pending, 0.5, 0.3)
        assert len(pending) == 1
        assert pending[0][1] == UnitStatus.DISABLED

    def test_light_casualties_no_status_change(self):
        target = _make_unit("tgt", "red", personnel_count=100)
        pending: list[tuple[Unit, UnitStatus]] = []
        _apply_aggregate_casualties(10, target, pending, 0.5, 0.3)
        assert len(pending) == 0

    def test_zero_casualties_ignored(self):
        target = _make_unit("tgt", "red", personnel_count=100)
        pending: list[tuple[Unit, UnitStatus]] = []
        _apply_aggregate_casualties(0, target, pending)
        assert len(pending) == 0


class TestMeleeResultApplication:
    """Test _apply_melee_result mapping."""

    def test_melee_result_applies_both_sides(self):
        attacker = _make_unit("att", "blue", personnel_count=100)
        defender = _make_unit("def", "red", personnel_count=50)
        mr = SimpleNamespace(
            attacker_casualties=35,  # 35% of 100
            defender_casualties=30,  # 60% of 50
            attacker_morale_change=-0.1,
            defender_morale_change=-0.3,
            defender_routed=False,
            attacker_routed=False,
        )
        pending: list[tuple[Unit, UnitStatus]] = []
        morale_states: dict[str, Any] = {}
        _apply_melee_result(mr, attacker, defender, pending, morale_states, 0.5, 0.3)
        statuses = {u.entity_id: s for u, s in pending}
        assert statuses["att"] == UnitStatus.DISABLED  # 35%
        assert statuses["def"] == UnitStatus.DESTROYED  # 60%

    def test_melee_rout_sets_morale_state(self):
        attacker = _make_unit("att", "blue", personnel_count=100)
        defender = _make_unit("def", "red", personnel_count=100)
        mr = SimpleNamespace(
            attacker_casualties=0, defender_casualties=5,
            attacker_morale_change=0, defender_morale_change=-0.5,
            defender_routed=True, attacker_routed=False,
        )
        pending: list[tuple[Unit, UnitStatus]] = []
        morale_states: dict[str, Any] = {}
        _apply_melee_result(mr, attacker, defender, pending, morale_states)
        assert morale_states["def"] == 3  # ROUTED
        assert defender.status == UnitStatus.ROUTING


class TestInferMeleeType:
    def test_cavalry_weapon(self):
        from stochastic_warfare.combat.melee import MeleeType
        wpn = _make_wpn("cavalry_saber", "MELEE")
        mt = _infer_melee_type(_make_unit(), wpn)
        assert mt == MeleeType.CAVALRY_CHARGE

    def test_bayonet_weapon(self):
        from stochastic_warfare.combat.melee import MeleeType
        wpn = _make_wpn("bayonet_charge", "MELEE")
        mt = _infer_melee_type(_make_unit(), wpn)
        assert mt == MeleeType.BAYONET_CHARGE

    def test_pike_weapon(self):
        from stochastic_warfare.combat.melee import MeleeType
        wpn = _make_wpn("pike_18ft", "MELEE")
        mt = _infer_melee_type(_make_unit(), wpn)
        assert mt == MeleeType.PIKE_PUSH

    def test_sword_weapon(self):
        from stochastic_warfare.combat.melee import MeleeType
        wpn = _make_wpn("gladius_sword", "MELEE")
        mt = _infer_melee_type(_make_unit(), wpn)
        assert mt == MeleeType.SHIELD_WALL

    def test_default_melee_type(self):
        from stochastic_warfare.combat.melee import MeleeType
        wpn = _make_wpn("unknown_weapon", "MELEE")
        mt = _infer_melee_type(_make_unit(), wpn)
        assert mt == MeleeType.BAYONET_CHARGE


class TestInferMissileType:
    def test_longbow(self):
        from stochastic_warfare.combat.archery import MissileType
        wpn = _make_wpn("english_longbow", "RIFLE")
        mt = _infer_missile_type(wpn)
        assert mt == MissileType.LONGBOW

    def test_crossbow(self):
        from stochastic_warfare.combat.archery import MissileType
        wpn = _make_wpn("heavy_crossbow", "RIFLE")
        mt = _infer_missile_type(wpn)
        assert mt == MissileType.CROSSBOW

    def test_javelin(self):
        from stochastic_warfare.combat.archery import MissileType
        wpn = _make_wpn("pilum_javelin", "RIFLE")
        mt = _infer_missile_type(wpn)
        assert mt == MissileType.JAVELIN


class TestGetFormationFirepower:
    def test_default_returns_1(self):
        ctx = SimpleNamespace(formation_napoleonic_engine=None)
        result = _get_formation_firepower(ctx, _make_unit())
        assert result == 1.0

    def test_engine_queried(self):
        eng = MagicMock()
        eng.get_firepower_fraction.return_value = 0.6
        ctx = SimpleNamespace(formation_napoleonic_engine=eng)
        u = _make_unit("u1")
        result = _get_formation_firepower(ctx, u)
        assert result == 0.6
        eng.get_firepower_fraction.assert_called_once_with("u1")


# ===========================================================================
# 43b: Indirect Fire Routing
# ===========================================================================


class TestIndirectFireRouting:
    """Test artillery/mortar weapons route to IndirectFireEngine."""

    def test_howitzer_routes_to_indirect_fire(self):
        ife = MagicMock()
        ife.fire_mission.return_value = SimpleNamespace(
            mission_type=None, rounds_fired=4, impacts=[], suppression_achieved=False,
            target_pos=Position(500.0, 0.0, 0.0),
        )
        attacker = _make_unit("att", "blue", personnel_count=4)
        target = _make_unit("tgt", "red", personnel_count=100, position=Position(500.0, 0.0, 0.0))
        wpn = _make_wpn("m109_howitzer", "HOWITZER", max_range_m=30000.0, rate_of_fire_rpm=4.0)

        ctx = _make_ctx(era="modern", indirect_fire_engine=ife, units=[attacker, target])
        ctx.unit_weapons = {"att": [(wpn, [_make_ammo()])]}
        ctx.unit_sensors = {}
        ctx.units_by_side = {"blue": [attacker], "red": [target]}

        bm = BattleManager(MagicMock(), config=BattleConfig())
        bm._execute_engagements(
            ctx, {"blue": [attacker]}, {"blue": [target]},
            {"blue": np.array([[500.0, 0.0]])}, dt=60.0, timestamp=datetime(2000, 1, 1),
        )
        ife.fire_mission.assert_called_once()

    def test_mortar_routes_to_indirect_fire(self):
        ife = MagicMock()
        ife.fire_mission.return_value = SimpleNamespace(
            mission_type=None, rounds_fired=6, impacts=[], suppression_achieved=True,
            target_pos=Position(1000.0, 0.0, 0.0),
        )
        attacker = _make_unit("att", "blue", personnel_count=3)
        target = _make_unit("tgt", "red", personnel_count=50, position=Position(1000.0, 0.0, 0.0))
        wpn = _make_wpn("m252_mortar", "MORTAR", max_range_m=5600.0, rate_of_fire_rpm=20.0)

        ctx = _make_ctx(era="modern", indirect_fire_engine=ife, units=[attacker, target])
        ctx.unit_weapons = {"att": [(wpn, [_make_ammo()])]}
        ctx.unit_sensors = {}
        ctx.units_by_side = {"blue": [attacker], "red": [target]}

        bm = BattleManager(MagicMock(), config=BattleConfig())
        bm._execute_engagements(
            ctx, {"blue": [attacker]}, {"blue": [target]},
            {"blue": np.array([[1000.0, 0.0]])}, dt=60.0, timestamp=datetime(2000, 1, 1),
        )
        ife.fire_mission.assert_called_once()

    def test_indirect_fire_casualties(self):
        """Impacts near target produce casualties."""
        target = _make_unit("tgt", "red", personnel_count=100, position=Position(100.0, 100.0, 0.0))
        fm_result = SimpleNamespace(
            impacts=[
                SimpleNamespace(position=Position(110.0, 100.0, 0.0)),  # 10m away
                SimpleNamespace(position=Position(105.0, 105.0, 0.0)),  # ~7m away
                SimpleNamespace(position=Position(130.0, 130.0, 0.0)),  # ~42m away
                SimpleNamespace(position=Position(200.0, 200.0, 0.0)),  # >50m away
            ],
            suppression_achieved=True,
        )
        pending: list[tuple[Unit, UnitStatus]] = []
        _apply_indirect_fire_result(fm_result, target, pending, 0.5, 0.3)
        # 3 hits within 50m → fraction = 3 * 0.15 = 0.45 → DISABLED (≥0.3, <0.5)
        assert len(pending) == 1
        assert pending[0][1] == UnitStatus.DISABLED

    def test_direct_fire_weapons_unchanged(self):
        """MACHINE_GUN still uses standard engagement, not indirect fire."""
        eng = MagicMock()
        eng.route_engagement.return_value = SimpleNamespace(
            engaged=True,
            hit_result=SimpleNamespace(hit=False),
            damage_result=None,
        )
        attacker = _make_unit("att", "blue", personnel_count=4)
        target = _make_unit("tgt", "red", personnel_count=50, position=Position(500.0, 0.0, 0.0))
        wpn = _make_wpn("m240", "MACHINE_GUN", max_range_m=1800.0)

        ctx = _make_ctx(era="modern", engagement_engine=eng, units=[attacker, target])
        ctx.unit_weapons = {"att": [(wpn, [_make_ammo()])]}
        ctx.unit_sensors = {}
        ctx.units_by_side = {"blue": [attacker], "red": [target]}

        bm = BattleManager(MagicMock(), config=BattleConfig())
        bm._execute_engagements(
            ctx, {"blue": [attacker]}, {"blue": [target]},
            {"blue": np.array([[500.0, 0.0]])}, dt=10.0, timestamp=datetime(2000, 1, 1),
        )
        eng.route_engagement.assert_called_once()


# ===========================================================================
# 43c: Naval Domain Routing
# ===========================================================================


class TestNavalRouting:
    """Test naval engagements route to specialized engines."""

    def test_torpedo_routes_to_subsurface_engine(self):
        nse = MagicMock()
        nse.torpedo_engagement.return_value = SimpleNamespace(
            torpedo_id="t1", hit=True, evaded=False, decoyed=False,
            malfunction=False, damage_fraction=0.7,
        )
        attacker = _make_unit("sub1", "blue", Domain.SUBMARINE, personnel_count=50)
        target = _make_unit("dd1", "red", Domain.NAVAL, personnel_count=200,
                           position=Position(2000.0, 0.0, 0.0))
        wpn = _make_wpn("torpedo_tube_533mm", "TORPEDO_TUBE", max_range_m=20000.0)

        ctx = _make_ctx(naval_subsurface_engine=nse, units=[attacker, target])
        ctx.calibration = {"visibility_m": 100000.0}
        ctx.unit_weapons = {"sub1": [(wpn, [_make_ammo()])]}
        ctx.unit_sensors = {}
        ctx.units_by_side = {"blue": [attacker], "red": [target]}

        bm = BattleManager(MagicMock(), config=BattleConfig())
        pending = bm._execute_engagements(
            ctx, {"blue": [attacker]}, {"blue": [target]},
            {"blue": np.array([[2000.0, 0.0]])}, dt=10.0, timestamp=datetime(2000, 1, 1),
        )
        nse.torpedo_engagement.assert_called_once()
        assert any(s == UnitStatus.DESTROYED for _, s in pending)

    def test_torpedo_miss_no_damage(self):
        nse = MagicMock()
        nse.torpedo_engagement.return_value = SimpleNamespace(
            torpedo_id="t1", hit=False, evaded=True, decoyed=False,
            malfunction=False, damage_fraction=0.0,
        )
        attacker = _make_unit("sub1", "blue", Domain.SUBMARINE, personnel_count=50)
        target = _make_unit("dd1", "red", Domain.NAVAL, personnel_count=200,
                           position=Position(2000.0, 0.0, 0.0))
        wpn = _make_wpn("torpedo_tube_533mm", "TORPEDO_TUBE", max_range_m=20000.0)

        ctx = _make_ctx(naval_subsurface_engine=nse, units=[attacker, target])
        ctx.calibration = {"visibility_m": 100000.0}
        ctx.unit_weapons = {"sub1": [(wpn, [_make_ammo()])]}
        ctx.unit_sensors = {}
        ctx.units_by_side = {"blue": [attacker], "red": [target]}

        bm = BattleManager(MagicMock(), config=BattleConfig())
        pending = bm._execute_engagements(
            ctx, {"blue": [attacker]}, {"blue": [target]},
            {"blue": np.array([[2000.0, 0.0]])}, dt=10.0, timestamp=datetime(2000, 1, 1),
        )
        assert len(pending) == 0

    def test_missile_routes_to_surface_engine(self):
        nse = MagicMock()
        nse.salvo_exchange.return_value = SimpleNamespace(
            missiles_fired=4, offensive_power=2.8,
            defensive_power=0.6, leakers=3, hits=2,
        )
        attacker = _make_unit("ddg1", "blue", Domain.NAVAL, personnel_count=300)
        target = _make_unit("ddg2", "red", Domain.NAVAL, personnel_count=250,
                           position=Position(50000.0, 0.0, 0.0))
        wpn = _make_wpn("harpoon_launcher", "MISSILE_LAUNCHER", max_range_m=130000.0, rate_of_fire_rpm=4.0)

        ctx = _make_ctx(naval_surface_engine=nse, units=[attacker, target])
        ctx.calibration = {"visibility_m": 200000.0}
        ctx.unit_weapons = {"ddg1": [(wpn, [_make_ammo()])]}
        ctx.unit_sensors = {}
        ctx.units_by_side = {"blue": [attacker], "red": [target]}

        bm = BattleManager(MagicMock(), config=BattleConfig())
        pending = bm._execute_engagements(
            ctx, {"blue": [attacker]}, {"blue": [target]},
            {"blue": np.array([[50000.0, 0.0]])}, dt=10.0, timestamp=datetime(2000, 1, 1),
        )
        nse.salvo_exchange.assert_called_once()
        assert any(s == UnitStatus.DESTROYED for _, s in pending)

    def test_naval_gun_routes_to_gunnery_engine(self):
        nge = MagicMock()
        nge.fire_salvo.return_value = {
            "hits": 2, "hit_probability": 0.1, "salvos_fired": 1,
            "straddle_achieved": True,
            "bracket": SimpleNamespace(
                target_id="ca2", bracket_width_m=100.0,
                salvos_fired=3, straddle_achieved=True, range_error_m=50.0,
            ),
        }
        attacker = _make_unit("bb1", "blue", Domain.NAVAL, personnel_count=1500)
        target = _make_unit("ca2", "red", Domain.NAVAL, personnel_count=800,
                           position=Position(15000.0, 0.0, 0.0))
        wpn = _make_wpn("14in_naval_gun", "NAVAL_GUN", max_range_m=35000.0, rate_of_fire_rpm=2.0)

        ctx = _make_ctx(naval_gunnery_engine=nge, units=[attacker, target])
        ctx.calibration = {"visibility_m": 100000.0}
        ctx.unit_weapons = {"bb1": [(wpn, [_make_ammo()])]}
        ctx.unit_sensors = {}
        ctx.units_by_side = {"blue": [attacker], "red": [target]}

        bm = BattleManager(MagicMock(), config=BattleConfig())
        pending = bm._execute_engagements(
            ctx, {"blue": [attacker]}, {"blue": [target]},
            {"blue": np.array([[15000.0, 0.0]])}, dt=10.0, timestamp=datetime(2000, 1, 1),
        )
        nge.fire_salvo.assert_called_once()
        assert any(s == UnitStatus.DISABLED for _, s in pending)

    def test_naval_routing_precedes_standard(self):
        """Naval engagement skips standard route_engagement()."""
        nse = MagicMock()
        nse.salvo_exchange.return_value = SimpleNamespace(
            missiles_fired=2, offensive_power=1.4,
            defensive_power=0.3, leakers=1, hits=1,
        )
        eng = MagicMock()  # Standard engagement engine

        attacker = _make_unit("ddg1", "blue", Domain.NAVAL, personnel_count=300)
        target = _make_unit("ddg2", "red", Domain.NAVAL, personnel_count=250,
                           position=Position(50000.0, 0.0, 0.0))
        wpn = _make_wpn("ashm_launcher", "MISSILE_LAUNCHER", max_range_m=200000.0, rate_of_fire_rpm=2.0)

        ctx = _make_ctx(
            naval_surface_engine=nse, engagement_engine=eng,
            units=[attacker, target],
        )
        ctx.calibration = {"visibility_m": 300000.0}
        ctx.unit_weapons = {"ddg1": [(wpn, [_make_ammo()])]}
        ctx.unit_sensors = {}
        ctx.units_by_side = {"blue": [attacker], "red": [target]}

        bm = BattleManager(MagicMock(), config=BattleConfig())
        bm._execute_engagements(
            ctx, {"blue": [attacker]}, {"blue": [target]},
            {"blue": np.array([[50000.0, 0.0]])}, dt=10.0, timestamp=datetime(2000, 1, 1),
        )
        nse.salvo_exchange.assert_called_once()
        eng.route_engagement.assert_not_called()

    def test_torpedo_hit_destroys_target(self):
        """damage_fraction >= 0.6 → DESTROYED."""
        wpn = _make_wpn("torp", "TORPEDO_TUBE", max_range_m=20000.0)
        ctx = SimpleNamespace(naval_subsurface_engine=MagicMock())
        ctx.naval_subsurface_engine.torpedo_engagement.return_value = SimpleNamespace(
            torpedo_id="t1", hit=True, evaded=False, decoyed=False,
            malfunction=False, damage_fraction=0.8,
        )
        attacker = _make_unit("sub", "blue", Domain.SUBMARINE)
        target = _make_unit("dd", "red", Domain.NAVAL)
        handled, status = _route_naval_engagement(ctx, attacker, target, wpn, 5000.0, 10.0, None)
        assert handled is True
        assert status == UnitStatus.DESTROYED

    def test_torpedo_hit_disables_target(self):
        """damage_fraction < 0.6 → DISABLED."""
        wpn = _make_wpn("torp", "TORPEDO_TUBE", max_range_m=20000.0)
        ctx = SimpleNamespace(naval_subsurface_engine=MagicMock())
        ctx.naval_subsurface_engine.torpedo_engagement.return_value = SimpleNamespace(
            torpedo_id="t1", hit=True, evaded=False, decoyed=False,
            malfunction=False, damage_fraction=0.4,
        )
        attacker = _make_unit("sub", "blue", Domain.SUBMARINE)
        target = _make_unit("dd", "red", Domain.NAVAL)
        handled, status = _route_naval_engagement(ctx, attacker, target, wpn, 5000.0, 10.0, None)
        assert handled is True
        assert status == UnitStatus.DISABLED

    def test_land_weapon_falls_through(self):
        """Non-naval weapon category returns (False, None) — fall through."""
        wpn = _make_wpn("m4", "RIFLE", max_range_m=600.0)
        ctx = SimpleNamespace(
            naval_subsurface_engine=None,
            naval_surface_engine=None,
            naval_gunnery_engine=None,
            naval_gunfire_support_engine=None,
        )
        attacker = _make_unit("inf", "blue", Domain.GROUND)
        target = _make_unit("dd", "red", Domain.NAVAL)
        handled, status = _route_naval_engagement(ctx, attacker, target, wpn, 500.0, 10.0, None)
        assert handled is False
        assert status is None


# ===========================================================================
# Scenario context wiring
# ===========================================================================


class TestScenarioContextFields:
    """Verify new engine fields exist on SimulationContext."""

    def test_indirect_fire_engine_field(self):
        from stochastic_warfare.simulation.scenario import SimulationContext
        import dataclasses
        field_names = [f.name for f in dataclasses.fields(SimulationContext)]
        assert "indirect_fire_engine" in field_names

    def test_naval_surface_engine_field(self):
        from stochastic_warfare.simulation.scenario import SimulationContext
        import dataclasses
        field_names = [f.name for f in dataclasses.fields(SimulationContext)]
        assert "naval_surface_engine" in field_names

    def test_naval_subsurface_engine_field(self):
        from stochastic_warfare.simulation.scenario import SimulationContext
        import dataclasses
        field_names = [f.name for f in dataclasses.fields(SimulationContext)]
        assert "naval_subsurface_engine" in field_names

    def test_naval_gunfire_support_engine_field(self):
        from stochastic_warfare.simulation.scenario import SimulationContext
        import dataclasses
        field_names = [f.name for f in dataclasses.fields(SimulationContext)]
        assert "naval_gunfire_support_engine" in field_names

    def test_mine_warfare_engine_field(self):
        from stochastic_warfare.simulation.scenario import SimulationContext
        import dataclasses
        field_names = [f.name for f in dataclasses.fields(SimulationContext)]
        assert "mine_warfare_engine" in field_names
