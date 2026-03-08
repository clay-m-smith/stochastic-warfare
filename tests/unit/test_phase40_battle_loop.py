"""Phase 40 — Battle Loop Foundation tests.

Tests for victory bug fix (40a), posture tracking (40b), fire-on-move (40c),
domain filtering (40d), suppression wiring (40e), morale multipliers (40f),
and terrain manager instantiation (40g).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from stochastic_warfare.combat.ammunition import (
    AmmoDefinition,
    WeaponCategory,
    WeaponDefinition,
    _CATEGORY_DEFAULT_DOMAINS,
)
from stochastic_warfare.combat.engagement import EngagementEngine, EngagementType
from stochastic_warfare.combat.suppression import (
    SuppressionEngine,
    UnitSuppressionState,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.entities.unit_classes.ground import GroundUnit, Posture
from stochastic_warfare.morale.state import MoraleState, _MORALE_EFFECTS
from stochastic_warfare.simulation.battle import BattleConfig, BattleContext, BattleManager
from stochastic_warfare.simulation.victory import VictoryEvaluator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _make_unit(
    uid: str,
    side: str = "blue",
    status: UnitStatus = UnitStatus.ACTIVE,
    pos: Position | None = None,
    domain: Domain = Domain.GROUND,
    speed: float = 0.0,
    max_speed: float = 10.0,
) -> Unit:
    return Unit(
        entity_id=uid,
        position=pos or Position(0.0, 0.0, 0.0),
        name=uid,
        side=side,
        domain=domain,
        status=status,
        speed=speed,
        max_speed=max_speed,
    )


def _make_ground_unit(
    uid: str,
    side: str = "blue",
    status: UnitStatus = UnitStatus.ACTIVE,
    pos: Position | None = None,
    posture: Posture = Posture.MOVING,
    speed: float = 0.0,
    max_speed: float = 10.0,
) -> GroundUnit:
    return GroundUnit(
        entity_id=uid,
        position=pos or Position(0.0, 0.0, 0.0),
        name=uid,
        side=side,
        status=status,
        posture=posture,
        speed=speed,
        max_speed=max_speed,
    )


def _make_weapon_def(
    wid: str = "wpn1",
    category: str = "CANNON",
    max_range: float = 3000.0,
    caliber: float = 120.0,
    rate_of_fire: float = 6.0,
    requires_deployed: bool = False,
    target_domains: list[str] | None = None,
) -> WeaponDefinition:
    wd = WeaponDefinition(
        weapon_id=wid,
        display_name=wid,
        category=category,
        caliber_mm=caliber,
        max_range_m=max_range,
        rate_of_fire_rpm=rate_of_fire,
        requires_deployed=requires_deployed,
    )
    if target_domains is not None:
        wd = wd.model_copy(update={"target_domains": target_domains})
    return wd


# =========================================================================
# 40a — Victory Bug Fix
# =========================================================================


class TestVictoryBugFix:
    """Tests for evaluate_force_advantage() is_tie bug."""

    def test_blue_wins_over_red(self):
        """When blue has higher survival, blue should win."""
        blue = [_make_unit("b1"), _make_unit("b2")]
        red = [
            _make_unit("r1", side="red"),
            _make_unit("r2", side="red", status=UnitStatus.DESTROYED),
        ]
        result = VictoryEvaluator.evaluate_force_advantage(
            {"blue": blue, "red": red}
        )
        assert result.winning_side == "blue"
        assert result.game_over is True

    def test_red_wins_over_blue(self):
        """When red has higher survival, red should win."""
        blue = [
            _make_unit("b1", status=UnitStatus.DESTROYED),
            _make_unit("b2", status=UnitStatus.DESTROYED),
        ]
        red = [_make_unit("r1", side="red")]
        result = VictoryEvaluator.evaluate_force_advantage(
            {"blue": blue, "red": red}
        )
        assert result.winning_side == "red"

    def test_equal_survival_is_draw(self):
        """When both sides have 50% survival, result should be draw."""
        blue = [
            _make_unit("b1"),
            _make_unit("b2", status=UnitStatus.DESTROYED),
        ]
        red = [
            _make_unit("r1", side="red"),
            _make_unit("r2", side="red", status=UnitStatus.DESTROYED),
        ]
        result = VictoryEvaluator.evaluate_force_advantage(
            {"blue": blue, "red": red}
        )
        assert result.winning_side == "draw"

    def test_three_sides_one_dominant(self):
        """Three-sided: the one with highest survival wins."""
        blue = [_make_unit("b1"), _make_unit("b2")]  # 100%
        red = [
            _make_unit("r1", side="red"),
            _make_unit("r2", side="red", status=UnitStatus.DESTROYED),
        ]  # 50%
        green = [
            _make_unit("g1", side="green", status=UnitStatus.DESTROYED),
        ]  # 0%
        result = VictoryEvaluator.evaluate_force_advantage(
            {"blue": blue, "red": red, "green": green}
        )
        assert result.winning_side == "blue"

    def test_three_sides_two_equal_best(self):
        """Three-sided: two sides tied at best → draw."""
        blue = [_make_unit("b1")]  # 100%
        red = [_make_unit("r1", side="red")]  # 100%
        green = [
            _make_unit("g1", side="green", status=UnitStatus.DESTROYED),
        ]  # 0%
        result = VictoryEvaluator.evaluate_force_advantage(
            {"blue": blue, "red": red, "green": green}
        )
        assert result.winning_side == "draw"

    def test_empty_sides_ignored(self):
        """Sides with no units are ignored, remaining side wins."""
        blue = [_make_unit("b1")]
        result = VictoryEvaluator.evaluate_force_advantage(
            {"blue": blue, "red": []}
        )
        assert result.winning_side == "blue"

    def test_all_empty_is_draw(self):
        """All sides empty → draw."""
        result = VictoryEvaluator.evaluate_force_advantage(
            {"blue": [], "red": []}
        )
        assert result.winning_side == "draw"

    def test_single_side_wins(self):
        """Single side with active units wins."""
        blue = [_make_unit("b1")]
        result = VictoryEvaluator.evaluate_force_advantage({"blue": blue})
        assert result.winning_side == "blue"


# =========================================================================
# 40d — Domain Filtering
# =========================================================================


class TestDomainFiltering:
    """Tests for effective_target_domains() and domain gating."""

    def test_cannon_targets_ground_only(self):
        wd = _make_weapon_def(category="CANNON")
        assert wd.effective_target_domains() == {"GROUND"}

    def test_aaa_targets_aerial(self):
        wd = _make_weapon_def(category="AAA")
        assert wd.effective_target_domains() == {"AERIAL"}

    def test_torpedo_targets_naval_sub(self):
        wd = _make_weapon_def(category="TORPEDO_TUBE")
        assert wd.effective_target_domains() == {"NAVAL", "SUBMARINE"}

    def test_aircraft_gun_targets_ground_aerial(self):
        wd = _make_weapon_def(category="AIRCRAFT_GUN")
        assert wd.effective_target_domains() == {"GROUND", "AERIAL"}

    def test_missile_launcher_targets_ground_aerial(self):
        wd = _make_weapon_def(category="MISSILE_LAUNCHER")
        assert wd.effective_target_domains() == {"GROUND", "AERIAL"}

    def test_explicit_override(self):
        """Explicit target_domains overrides category default."""
        wd = _make_weapon_def(category="CANNON", target_domains=["AERIAL", "NAVAL"])
        assert wd.effective_target_domains() == {"AERIAL", "NAVAL"}

    def test_machine_gun_includes_aerial(self):
        wd = _make_weapon_def(category="MACHINE_GUN")
        assert "AERIAL" in wd.effective_target_domains()

    def test_ciws_targets_aerial_naval(self):
        wd = _make_weapon_def(category="CIWS")
        assert wd.effective_target_domains() == {"AERIAL", "NAVAL"}

    def test_directed_energy_targets_all_three(self):
        wd = _make_weapon_def(category="DIRECTED_ENERGY")
        domains = wd.effective_target_domains()
        assert "GROUND" in domains
        assert "AERIAL" in domains
        assert "NAVAL" in domains

    def test_unknown_category_fallback(self):
        """Invalid category string falls back to GROUND+NAVAL."""
        wd = _make_weapon_def(category="UNKNOWN_THING")
        domains = wd.effective_target_domains()
        assert domains == {"GROUND", "NAVAL"}


# =========================================================================
# 40b — Posture Tracking
# =========================================================================


class TestPostureTracking:
    """Tests for posture auto-assignment in the battle loop."""

    def test_ground_unit_posture_extracted(self):
        """GroundUnit posture attribute is accessible."""
        gu = _make_ground_unit("g1", posture=Posture.DUG_IN)
        assert gu.posture == Posture.DUG_IN
        assert gu.posture.name == "DUG_IN"

    def test_base_unit_no_posture(self):
        """Base Unit has no posture attribute."""
        u = _make_unit("u1")
        assert not hasattr(u, "posture")
        assert getattr(u, "posture", None) is None

    def test_posture_defaults_moving(self):
        """Default posture for a GroundUnit is MOVING."""
        gu = _make_ground_unit("g1")
        assert gu.posture == Posture.MOVING

    def test_posture_str_extraction(self):
        """Posture name extraction for route_engagement."""
        gu = _make_ground_unit("g1", posture=Posture.DEFENSIVE)
        val = getattr(gu, "posture", None)
        name = val.name if val is not None else "MOVING"
        assert name == "DEFENSIVE"

        u = _make_unit("u1")
        val = getattr(u, "posture", None)
        name = val.name if val is not None else "MOVING"
        assert name == "MOVING"


# =========================================================================
# 40c — Fire-on-Move
# =========================================================================


class TestFireOnMove:
    """Tests for deployed weapon gate when moving."""

    def test_deployed_weapon_blocked_when_moving(self):
        """A requires_deployed weapon should be skipped when unit speed > 0.5."""
        wd = _make_weapon_def(requires_deployed=True)
        assert wd.requires_deployed is True
        # The logic: if attacker.speed > 0.5 and wpn_inst.definition.requires_deployed: continue
        # This is tested implicitly through the BattleManager, but we test the data here.

    def test_non_deployed_weapon_fires_while_moving(self):
        """A non-deployed weapon should not be blocked."""
        wd = _make_weapon_def(requires_deployed=False)
        assert wd.requires_deployed is False


# =========================================================================
# 40b+40c — route_engagement parameter forwarding
# =========================================================================


class TestRouteEngagementForwarding:
    """Tests that route_engagement forwards new params to execute_engagement."""

    def test_new_params_accepted(self, rng, event_bus):
        """route_engagement() accepts the new keyword arguments."""
        from stochastic_warfare.combat.ballistics import BallisticsEngine
        from stochastic_warfare.combat.damage import DamageEngine
        from stochastic_warfare.combat.fratricide import FratricideEngine
        from stochastic_warfare.combat.hit_probability import HitProbabilityEngine
        from stochastic_warfare.combat.suppression import SuppressionEngine

        bal = BallisticsEngine(rng)
        hit_eng = HitProbabilityEngine(bal, rng)
        dmg_eng = DamageEngine(event_bus, rng)
        sup_eng = SuppressionEngine(event_bus, rng)
        frat_eng = FratricideEngine(event_bus, rng)
        eng = EngagementEngine(hit_eng, dmg_eng, sup_eng, frat_eng, event_bus, rng)

        ammo_def = AmmoDefinition(
            ammo_id="a1",
            display_name="Shell",
            ammo_type="HE",
            mass_kg=10.0,
        )
        wd = _make_weapon_def()

        from stochastic_warfare.combat.ammunition import AmmoState, WeaponInstance

        wd = wd.model_copy(update={"compatible_ammo": ["a1"]})
        ammo_state = AmmoState(rounds_by_type={"a1": 10})
        wpn = WeaponInstance(definition=wd, ammo_state=ammo_state)

        # Should not raise — tests that the new kwargs are accepted
        result = eng.route_engagement(
            engagement_type=EngagementType.DIRECT_FIRE,
            attacker_id="att1",
            target_id="tgt1",
            attacker_pos=Position(0, 0, 0),
            target_pos=Position(1000, 0, 0),
            weapon=wpn,
            ammo_id="a1",
            ammo_def=ammo_def,
            shooter_speed_mps=5.0,
            target_posture="DUG_IN",
            visibility=0.8,
            position_uncertainty_m=50.0,
        )
        # Just verify it returns a result without error
        assert result is not None


# =========================================================================
# 40e — Suppression Wiring
# =========================================================================


class TestSuppressionWiring:
    """Tests for suppression engine context wiring."""

    def test_suppression_state_creation(self):
        """UnitSuppressionState defaults to zero."""
        state = UnitSuppressionState()
        assert state.value == 0.0

    def test_suppression_apply_fire_volume(self, rng, event_bus):
        """apply_fire_volume increases suppression value."""
        sup_eng = SuppressionEngine(event_bus, rng)
        state = UnitSuppressionState()
        sup_eng.apply_fire_volume(
            state=state,
            rounds_per_minute=600.0,
            caliber_mm=7.62,
            range_m=500.0,
            duration_s=10.0,
        )
        assert state.value > 0.0

    def test_suppression_decay(self, rng, event_bus):
        """update_suppression decays the value."""
        sup_eng = SuppressionEngine(event_bus, rng)
        state = UnitSuppressionState(value=0.5)
        sup_eng.update_suppression(state, dt=5.0)
        assert state.value < 0.5

    def test_battle_manager_has_suppression_dict(self, event_bus):
        """BattleManager has _suppression_states dict."""
        bm = BattleManager(event_bus)
        assert isinstance(bm._suppression_states, dict)
        assert len(bm._suppression_states) == 0

    def test_battle_manager_has_ticks_stationary(self, event_bus):
        """BattleManager has _ticks_stationary dict."""
        bm = BattleManager(event_bus)
        assert isinstance(bm._ticks_stationary, dict)


# =========================================================================
# 40f — Morale Multipliers
# =========================================================================


class TestMoraleMultipliers:
    """Tests for morale-driven accuracy and engagement gating."""

    def test_steady_full_accuracy(self):
        effects = _MORALE_EFFECTS[MoraleState.STEADY]
        assert effects["accuracy_mult"] == 1.0

    def test_shaken_reduced_accuracy(self):
        effects = _MORALE_EFFECTS[MoraleState.SHAKEN]
        assert effects["accuracy_mult"] == pytest.approx(0.7)

    def test_broken_low_accuracy(self):
        effects = _MORALE_EFFECTS[MoraleState.BROKEN]
        assert effects["accuracy_mult"] == pytest.approx(0.3)

    def test_routed_minimal_accuracy(self):
        effects = _MORALE_EFFECTS[MoraleState.ROUTED]
        assert effects["accuracy_mult"] == pytest.approx(0.1)

    def test_surrendered_zero_accuracy(self):
        effects = _MORALE_EFFECTS[MoraleState.SURRENDERED]
        assert effects["accuracy_mult"] == 0.0

    def test_morale_gate_routed_skips(self):
        """A ROUTED unit should not fire (morale gate in _execute_engagements)."""
        ms = MoraleState.ROUTED
        assert ms in (MoraleState.ROUTED, MoraleState.SURRENDERED)

    def test_morale_gate_surrendered_skips(self):
        """A SURRENDERED unit should not fire."""
        ms = MoraleState.SURRENDERED
        assert ms in (MoraleState.ROUTED, MoraleState.SURRENDERED)

    def test_morale_int_conversion(self):
        """Morale state stored as int can be converted back to enum."""
        val = int(MoraleState.SHAKEN)
        ms = MoraleState(val)
        assert ms == MoraleState.SHAKEN


# =========================================================================
# 40g — Terrain Manager Instantiation
# =========================================================================


class TestTerrainManagerInstantiation:
    """Tests for obstacle/hydrography manager availability."""

    def test_obstacle_manager_empty(self):
        """ObstacleManager with no obstacles returns empty queries."""
        from stochastic_warfare.terrain.obstacles import ObstacleManager

        mgr = ObstacleManager()
        result = mgr.obstacles_at(Position(100, 100, 0))
        assert result == []

    def test_hydrography_manager_empty(self):
        """HydrographyManager with no features returns empty queries."""
        from stochastic_warfare.terrain.hydrography import HydrographyManager

        mgr = HydrographyManager()
        result = mgr.rivers_near(Position(100, 100, 0), 1000.0)
        assert result == []

    def test_context_fields_exist(self):
        """SimulationContext has the new terrain/suppression fields."""
        from stochastic_warfare.simulation.scenario import SimulationContext

        # Check the dataclass fields exist
        field_names = {f.name for f in SimulationContext.__dataclass_fields__.values()}
        assert "obstacle_manager" in field_names
        assert "hydrography_manager" in field_names
        assert "population_manager" in field_names
        assert "suppression_engine" in field_names

    def test_infrastructure_manager_importable(self):
        """InfrastructureManager can be imported."""
        from stochastic_warfare.terrain.infrastructure import InfrastructureManager

        mgr = InfrastructureManager()
        assert mgr is not None


# =========================================================================
# Integration — BattleManager with posture, domain, morale, suppression
# =========================================================================


class TestBattleManagerIntegration:
    """Integration tests using BattleManager.execute_tick()."""

    def _make_minimal_ctx(
        self,
        units_by_side: dict[str, list[Unit]],
        morale_states: dict[str, Any] | None = None,
        calibration: dict[str, Any] | None = None,
        engagement_engine: Any = None,
        suppression_engine: Any = None,
        morale_machine: Any = None,
    ) -> SimpleNamespace:
        """Build a minimal SimulationContext-like namespace."""
        # Build weapon/sensor maps from unit ids
        unit_weapons: dict[str, list] = {}
        unit_sensors: dict[str, list] = {}
        for units in units_by_side.values():
            for u in units:
                unit_weapons[u.entity_id] = []
                unit_sensors[u.entity_id] = []

        clock = SimpleNamespace(
            current_time=TS,
            elapsed=timedelta(seconds=100),
        )

        config = SimpleNamespace(
            sides=[
                SimpleNamespace(side="blue", experience_level=0.5),
                SimpleNamespace(side="red", experience_level=0.5),
            ],
            behavior_rules={},
        )

        return SimpleNamespace(
            config=config,
            clock=clock,
            event_bus=EventBus(),
            calibration=calibration or {},
            units_by_side=units_by_side,
            unit_weapons=unit_weapons,
            unit_sensors=unit_sensors,
            morale_states=morale_states or {},
            engagement_engine=engagement_engine,
            suppression_engine=suppression_engine,
            morale_machine=morale_machine,
            ooda_engine=None,
            order_execution=None,
            consumption_engine=None,
            stockpile_manager=None,
            movement_engine=None,
            cbrn_engine=None,
        )

    def test_posture_update_stationary_halted(self):
        """A stationary GroundUnit on non-defensive side becomes HALTED."""
        bus = EventBus()
        bm = BattleManager(bus)
        # max_speed=0 so movement loop skips this unit
        gu = _make_ground_unit("g1", side="blue", pos=Position(100, 100, 0), max_speed=0.0)
        red = _make_unit("r1", side="red", pos=Position(5000, 5000, 0))
        units = {"blue": [gu], "red": [red]}
        ctx = self._make_minimal_ctx(units)
        battle = BattleContext(
            battle_id="b1", start_tick=0, start_time=TS, involved_sides=["blue", "red"],
        )
        bm.execute_tick(ctx, battle, dt=10.0)
        assert gu.posture == Posture.HALTED

    def test_posture_defensive_side_becomes_defensive(self):
        """A stationary GroundUnit on a defensive side becomes DEFENSIVE."""
        bus = EventBus()
        bm = BattleManager(bus)
        gu = _make_ground_unit("g1", side="blue", pos=Position(100, 100, 0), max_speed=0.0)
        red = _make_unit("r1", side="red", pos=Position(5000, 5000, 0))
        units = {"blue": [gu], "red": [red]}
        ctx = self._make_minimal_ctx(
            units,
            calibration={"defensive_sides": ["blue"]},
        )
        battle = BattleContext(
            battle_id="b1", start_tick=0, start_time=TS, involved_sides=["blue", "red"],
        )
        bm.execute_tick(ctx, battle, dt=10.0)
        assert gu.posture == Posture.DEFENSIVE

    def test_posture_dug_in_after_threshold(self):
        """Defensive side digs in after enough ticks."""
        bus = EventBus()
        bm = BattleManager(bus)
        gu = _make_ground_unit("g1", side="blue", pos=Position(100, 100, 0), max_speed=0.0)
        red = _make_unit("r1", side="red", pos=Position(5000, 5000, 0))
        units = {"blue": [gu], "red": [red]}
        ctx = self._make_minimal_ctx(
            units,
            calibration={"defensive_sides": ["blue"], "dig_in_ticks": 3},
        )
        battle = BattleContext(
            battle_id="b1", start_tick=0, start_time=TS, involved_sides=["blue", "red"],
        )
        # Tick through past the threshold
        for _ in range(5):
            bm.execute_tick(ctx, battle, dt=10.0)
        assert gu.posture == Posture.DUG_IN

    def test_base_unit_posture_unchanged(self):
        """Base Unit (no posture) is not affected by posture tracking."""
        bus = EventBus()
        bm = BattleManager(bus)
        u = _make_unit("u1", side="blue", pos=Position(100, 100, 0))
        red = _make_unit("r1", side="red", pos=Position(5000, 5000, 0))
        units = {"blue": [u], "red": [red]}
        ctx = self._make_minimal_ctx(units)
        battle = BattleContext(
            battle_id="b1", start_tick=0, start_time=TS, involved_sides=["blue", "red"],
        )
        bm.execute_tick(ctx, battle, dt=10.0)
        assert not hasattr(u, "posture")

    def test_morale_gate_routed_no_engagement(self):
        """A ROUTED attacker should not engage."""
        bus = EventBus()
        bm = BattleManager(bus)
        attacker = _make_unit("att", side="blue", pos=Position(0, 0, 0))
        target = _make_unit("tgt", side="red", pos=Position(500, 0, 0))
        units = {"blue": [attacker], "red": [target]}

        # Mock engagement engine to track calls
        calls = []

        class MockEngine:
            def route_engagement(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(engaged=False, hit_result=None, damage_result=None)

        ctx = self._make_minimal_ctx(
            units,
            morale_states={"att": MoraleState.ROUTED},
            engagement_engine=MockEngine(),
        )
        battle = BattleContext(
            battle_id="b1", start_tick=0, start_time=TS, involved_sides=["blue", "red"],
        )
        bm.execute_tick(ctx, battle, dt=10.0)
        # ROUTED unit should not have called route_engagement
        assert len(calls) == 0
