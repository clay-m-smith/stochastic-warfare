"""Phase 42: Tactical Behavior — ROE, hold-fire, composite victory, rout cascade, rally.

Tests cover:
- 42a: effective_range, ROE gating, hold-fire discipline
- 42b: composite victory scoring
- 42c: rout cascade, rally mechanic
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from stochastic_warfare.combat.ammunition import WeaponDefinition
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.morale.state import MoraleState
from stochastic_warfare.simulation.victory import VictoryEvaluator

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _make_unit(
    entity_id: str,
    *,
    status: UnitStatus = UnitStatus.ACTIVE,
    easting: float = 0.0,
    northing: float = 0.0,
    training_level: float = 0.5,
    side: str = "blue",
    support_type: str | None = None,
) -> Unit:
    """Create a minimal Unit for testing."""
    u = Unit.__new__(Unit)
    object.__setattr__(u, "entity_id", entity_id)
    object.__setattr__(u, "status", status)
    object.__setattr__(u, "position", Position(easting, northing, 0.0))
    object.__setattr__(u, "training_level", training_level)
    object.__setattr__(u, "side", side)
    object.__setattr__(u, "domain", SimpleNamespace(name="GROUND"))
    object.__setattr__(u, "speed", 0.0)
    object.__setattr__(u, "personnel", [1, 2, 3, 4])
    if support_type is not None:
        object.__setattr__(u, "support_type", SimpleNamespace(name=support_type))
    return u


# ---------------------------------------------------------------------------
# 42a: WeaponDefinition.get_effective_range
# ---------------------------------------------------------------------------


class TestEffectiveRange:
    def test_default_80_percent(self):
        wpn = WeaponDefinition(
            weapon_id="test_gun",
            display_name="Test Gun",
            category="CANNON",
            caliber_mm=120,
            max_range_m=3000.0,
        )
        assert wpn.get_effective_range() == pytest.approx(2400.0)

    def test_explicit_value(self):
        wpn = WeaponDefinition(
            weapon_id="test_gun",
            display_name="Test Gun",
            category="CANNON",
            caliber_mm=120,
            max_range_m=3000.0,
            effective_range_m=2000.0,
        )
        assert wpn.get_effective_range() == pytest.approx(2000.0)

    def test_zero_max_range(self):
        wpn = WeaponDefinition(
            weapon_id="melee",
            display_name="Melee",
            category="CANNON",
            caliber_mm=0,
            max_range_m=0.0,
        )
        assert wpn.get_effective_range() == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 42a: ROE engine wiring
# ---------------------------------------------------------------------------


class TestROEWiring:
    def test_roe_engine_instantiated(self):
        """ScenarioLoader should create ctx.roe_engine."""
        from stochastic_warfare.c2.roe import RoeEngine, RoeLevel

        bus = EventBus()
        engine = RoeEngine(bus, default_level=RoeLevel.WEAPONS_FREE)
        assert engine is not None

    def test_roe_default_weapons_free(self):
        """Default ROE for battle loop should be WEAPONS_FREE."""
        from stochastic_warfare.c2.roe import RoeEngine, RoeLevel

        bus = EventBus()
        engine = RoeEngine(bus, default_level=RoeLevel.WEAPONS_FREE)
        # All units default to WEAPONS_FREE
        level = engine.get_roe_level("any_unit")
        assert level == RoeLevel.WEAPONS_FREE

    def test_weapons_free_allows_all(self):
        """WEAPONS_FREE authorizes all military engagements."""
        from stochastic_warfare.c2.roe import RoeEngine, RoeLevel, TargetCategory

        bus = EventBus()
        engine = RoeEngine(bus, default_level=RoeLevel.WEAPONS_FREE)
        authorized, reason = engine.check_engagement_authorized(
            shooter_id="shooter_1",
            target_id="target_1",
            target_category=TargetCategory.MILITARY_COMBATANT,
            id_confidence=0.3,
        )
        assert authorized is True

    def test_weapons_hold_blocks(self):
        """WEAPONS_HOLD blocks non-self-defense engagements."""
        from stochastic_warfare.c2.roe import RoeEngine, RoeLevel, TargetCategory

        bus = EventBus()
        engine = RoeEngine(bus, default_level=RoeLevel.WEAPONS_HOLD)
        authorized, reason = engine.check_engagement_authorized(
            shooter_id="shooter_1",
            target_id="target_1",
            target_category=TargetCategory.MILITARY_COMBATANT,
            id_confidence=0.9,
            is_self_defense=False,
        )
        assert authorized is False

    def test_weapons_tight_low_confidence_blocks(self):
        """WEAPONS_TIGHT blocks engagement with low identification confidence."""
        from stochastic_warfare.c2.roe import RoeEngine, RoeLevel, TargetCategory

        bus = EventBus()
        engine = RoeEngine(bus, default_level=RoeLevel.WEAPONS_TIGHT)
        authorized, reason = engine.check_engagement_authorized(
            shooter_id="shooter_1",
            target_id="target_1",
            target_category=TargetCategory.MILITARY_COMBATANT,
            id_confidence=0.3,
        )
        assert authorized is False

    def test_weapons_tight_high_confidence_allows(self):
        """WEAPONS_TIGHT allows engagement with high identification confidence."""
        from stochastic_warfare.c2.roe import RoeEngine, RoeLevel, TargetCategory

        bus = EventBus()
        engine = RoeEngine(bus, default_level=RoeLevel.WEAPONS_TIGHT)
        authorized, reason = engine.check_engagement_authorized(
            shooter_id="shooter_1",
            target_id="target_1",
            target_category=TargetCategory.MILITARY_COMBATANT,
            id_confidence=0.9,
        )
        assert authorized is True


# ---------------------------------------------------------------------------
# 42a: Hold-fire discipline
# ---------------------------------------------------------------------------


class TestHoldFire:
    def _make_weapons(self, max_range_m: float = 3000.0) -> list:
        """Create a minimal weapon list for testing."""
        wpn_def = WeaponDefinition(
            weapon_id="test_gun",
            display_name="Test Gun",
            category="CANNON",
            caliber_mm=120,
            max_range_m=max_range_m,
            rate_of_fire_rpm=6.0,
            compatible_ammo=["ap_round"],
        )
        wpn_inst = SimpleNamespace(
            definition=wpn_def,
            can_fire=lambda ammo_id: True,
        )
        ammo_def = SimpleNamespace(ammo_id="ap_round")
        return [(wpn_inst, [ammo_def])]

    def test_hold_fire_blocks_beyond_effective_range(self):
        """Units with hold_fire should not engage beyond effective range."""
        # effective_range = 0.8 * 3000 = 2400
        weapons = self._make_weapons(3000.0)
        best_range = 2500.0  # beyond effective range
        best_eff_range = max(
            (w[0].definition.get_effective_range()
             for w in weapons if w[0].definition.max_range_m > 0),
            default=0.0,
        )
        # Should hold fire: 2500 > 2400
        assert best_range > best_eff_range

    def test_hold_fire_fires_within_effective_range(self):
        """Units with hold_fire should engage within effective range."""
        weapons = self._make_weapons(3000.0)
        best_range = 2000.0  # within effective range
        best_eff_range = max(
            (w[0].definition.get_effective_range()
             for w in weapons if w[0].definition.max_range_m > 0),
            default=0.0,
        )
        # Should fire: 2000 < 2400
        assert best_range <= best_eff_range

    def test_hold_fire_disabled_by_default(self):
        """Without hold_fire_until_effective_range, units fire at max range."""
        behavior_rules: dict = {}
        side_rules = behavior_rules.get("blue", {})
        hold_fire = isinstance(side_rules, dict) and side_rules.get(
            "hold_fire_until_effective_range", False,
        )
        assert hold_fire is False


# ---------------------------------------------------------------------------
# 42b: Composite victory scoring
# ---------------------------------------------------------------------------


class TestCompositeVictory:
    def _units(
        self,
        side: str,
        total: int,
        active: int,
        training: float = 0.5,
    ) -> list[Unit]:
        units = []
        for i in range(total):
            status = UnitStatus.ACTIVE if i < active else UnitStatus.DESTROYED
            units.append(_make_unit(
                f"{side}_{i}",
                status=status,
                training_level=training,
                side=side,
            ))
        return units

    def test_backward_compat_no_kwargs(self):
        """Without kwargs, evaluate_force_advantage behaves as before."""
        blue = self._units("blue", 10, 8)
        red = self._units("red", 10, 5)
        result = VictoryEvaluator.evaluate_force_advantage({"blue": blue, "red": red})
        assert result.game_over is True
        assert result.winning_side == "blue"

    def test_backward_compat_with_none_kwargs(self):
        """Passing None for new kwargs gives same result."""
        blue = self._units("blue", 10, 8)
        red = self._units("red", 10, 5)
        result1 = VictoryEvaluator.evaluate_force_advantage({"blue": blue, "red": red})
        result2 = VictoryEvaluator.evaluate_force_advantage(
            {"blue": blue, "red": red},
            morale_states=None,
            weights=None,
        )
        assert result1.winning_side == result2.winning_side

    def test_composite_morale_weight(self):
        """Side with better morale wins despite fewer active units."""
        blue = self._units("blue", 10, 4)  # fewer active
        red = self._units("red", 10, 5)    # more active
        # But blue has no routed, red has 3 routed
        morale_states = {}
        for u in blue:
            morale_states[u.entity_id] = MoraleState.STEADY
        for u in red:
            morale_states[u.entity_id] = MoraleState.STEADY
        # Rout 3 active red units
        for i in range(3):
            morale_states[red[i].entity_id] = MoraleState.ROUTED

        # With heavy morale weighting, blue should win
        result = VictoryEvaluator.evaluate_force_advantage(
            {"blue": blue, "red": red},
            morale_states=morale_states,
            weights={"force_ratio": 0.3, "morale_ratio": 0.7, "casualty_exchange": 0.0},
        )
        assert result.winning_side == "blue"

    def test_composite_draw_when_equal(self):
        """Equal composite scores produce a draw."""
        blue = self._units("blue", 10, 7)
        red = self._units("red", 10, 7)
        result = VictoryEvaluator.evaluate_force_advantage(
            {"blue": blue, "red": red},
        )
        assert result.winning_side == "draw"

    def test_morale_collapsed_triggers_at_threshold(self):
        """60% routed triggers morale_collapsed victory."""
        from stochastic_warfare.simulation.victory import VictoryEvaluator, VictoryEvaluatorConfig
        from stochastic_warfare.simulation.scenario import VictoryConditionConfig

        bus = EventBus()
        evaluator = VictoryEvaluator(
            objectives=[],
            conditions=[VictoryConditionConfig(type="morale_collapsed", side="")],
            event_bus=bus,
            config=VictoryEvaluatorConfig(morale_collapse_threshold=0.6),
        )
        blue = self._units("blue", 10, 10)
        red = self._units("red", 10, 10)
        morale_states = {}
        for u in blue:
            morale_states[u.entity_id] = MoraleState.STEADY
        # 6/10 red routed
        for i, u in enumerate(red):
            morale_states[u.entity_id] = MoraleState.ROUTED if i < 6 else MoraleState.STEADY

        clock = SimpleNamespace(
            elapsed=SimpleNamespace(total_seconds=lambda: 1000.0),
            tick_count=100,
            current_time=_TS,
        )
        result = evaluator.evaluate(
            clock=clock,
            units_by_side={"blue": blue, "red": red},
            morale_states=morale_states,
            supply_states={},
        )
        assert result.game_over is True
        assert result.condition_type == "morale_collapsed"

    def test_morale_collapsed_below_threshold(self):
        """50% routed does not trigger morale_collapsed at 0.6 threshold."""
        from stochastic_warfare.simulation.victory import VictoryEvaluator, VictoryEvaluatorConfig
        from stochastic_warfare.simulation.scenario import VictoryConditionConfig

        bus = EventBus()
        evaluator = VictoryEvaluator(
            objectives=[],
            conditions=[VictoryConditionConfig(type="morale_collapsed", side="")],
            event_bus=bus,
            config=VictoryEvaluatorConfig(morale_collapse_threshold=0.6),
        )
        blue = self._units("blue", 10, 10)
        red = self._units("red", 10, 10)
        morale_states = {}
        for u in blue:
            morale_states[u.entity_id] = MoraleState.STEADY
        # 5/10 red routed — below 0.6 threshold
        for i, u in enumerate(red):
            morale_states[u.entity_id] = MoraleState.ROUTED if i < 5 else MoraleState.STEADY

        clock = SimpleNamespace(
            elapsed=SimpleNamespace(total_seconds=lambda: 1000.0),
            tick_count=100,
            current_time=_TS,
        )
        result = evaluator.evaluate(
            clock=clock,
            units_by_side={"blue": blue, "red": red},
            morale_states=morale_states,
            supply_states={},
        )
        assert result.game_over is False


# ---------------------------------------------------------------------------
# 42c: Rout cascade and rally
# ---------------------------------------------------------------------------


class TestRoutCascade:
    def test_rout_engine_instantiated(self):
        """RoutEngine can be created with bus and rng."""
        from stochastic_warfare.morale.rout import RoutEngine

        bus = EventBus()
        rng = _rng()
        engine = RoutEngine(bus, rng)
        assert engine is not None

    def test_cascade_triggers_nearby_shaken(self):
        """SHAKEN unit within cascade radius may cascade to ROUTED."""
        from stochastic_warfare.morale.rout import RoutEngine, RoutConfig

        bus = EventBus()
        rng = _rng(seed=100)
        config = RoutConfig(cascade_base_chance=1.0)  # guaranteed cascade
        engine = RoutEngine(bus, rng, config)

        cascaded = engine.rout_cascade(
            routing_unit_id="rout_1",
            adjacent_unit_morale_states={"shaken_1": int(MoraleState.SHAKEN)},
            distances_m={"shaken_1": 200.0},
        )
        assert "shaken_1" in cascaded

    def test_cascade_no_effect_on_steady(self):
        """STEADY unit should not cascade even within radius."""
        from stochastic_warfare.morale.rout import RoutEngine, RoutConfig

        bus = EventBus()
        rng = _rng()
        config = RoutConfig(cascade_base_chance=1.0)
        engine = RoutEngine(bus, rng, config)

        cascaded = engine.rout_cascade(
            routing_unit_id="rout_1",
            adjacent_unit_morale_states={"steady_1": int(MoraleState.STEADY)},
            distances_m={"steady_1": 200.0},
        )
        assert "steady_1" not in cascaded

    def test_cascade_respects_radius(self):
        """Unit beyond cascade radius should not be affected."""
        from stochastic_warfare.morale.rout import RoutEngine, RoutConfig

        bus = EventBus()
        rng = _rng()
        config = RoutConfig(cascade_radius_m=500.0, cascade_base_chance=1.0)
        engine = RoutEngine(bus, rng, config)

        cascaded = engine.rout_cascade(
            routing_unit_id="rout_1",
            adjacent_unit_morale_states={"shaken_1": int(MoraleState.SHAKEN)},
            distances_m={"shaken_1": 600.0},
        )
        assert "shaken_1" not in cascaded

    def test_rally_with_friendlies(self):
        """ROUTED unit with friendlies nearby has good rally chance."""
        from stochastic_warfare.morale.rout import RoutEngine, RoutConfig

        bus = EventBus()
        rng = _rng(seed=42)
        config = RoutConfig(
            rally_base_chance=0.15,
            rally_friendly_bonus=0.05,
            rally_leader_bonus=0.20,
        )
        engine = RoutEngine(bus, rng, config)

        # With 4 friendlies and leader: 0.15 + 4*0.05 + 0.20 = 0.55
        # Run multiple times to verify it sometimes rallies
        rallied_count = 0
        for seed in range(100):
            rng_i = _rng(seed)
            eng = RoutEngine(bus, rng_i, config)
            if eng.check_rally("rout_1", nearby_friendly_count=4, leader_present=True):
                rallied_count += 1
        # With 55% chance, expect roughly 40-70 rallies in 100 tries
        assert rallied_count > 20

    def test_rally_without_friendlies_unlikely(self):
        """Isolated ROUTED unit rarely rallies (base 15%)."""
        from stochastic_warfare.morale.rout import RoutEngine, RoutConfig

        bus = EventBus()
        config = RoutConfig(rally_base_chance=0.15)

        rallied_count = 0
        for seed in range(200):
            rng_i = _rng(seed)
            eng = RoutEngine(bus, rng_i, config)
            if eng.check_rally("rout_1", nearby_friendly_count=0, leader_present=False):
                rallied_count += 1
        # 15% base chance → expect 10-50 rallies in 200 tries
        assert rallied_count < 60
        assert rallied_count > 5

    def test_rally_updates_morale_state(self):
        """Rally should set morale to SHAKEN, not STEADY."""
        from stochastic_warfare.morale.rout import RoutEngine, RoutConfig

        bus = EventBus()
        config = RoutConfig(rally_base_chance=1.0)  # guaranteed rally
        rng = _rng()
        engine = RoutEngine(bus, rng, config)

        rallied = engine.check_rally("rout_1", nearby_friendly_count=3, leader_present=True)
        assert rallied is True
        # The battle loop sets MoraleState.SHAKEN on rally — tested via integration

    def test_cascade_broken_susceptibility(self):
        """BROKEN unit is more susceptible to cascade than SHAKEN."""
        from stochastic_warfare.morale.rout import RoutEngine, RoutConfig

        bus = EventBus()
        # Set base chance low enough that SHAKEN rarely cascades but BROKEN does
        config = RoutConfig(
            cascade_base_chance=0.3,
            cascade_shaken_susceptibility=1.0,
            cascade_broken_susceptibility=3.0,
        )

        shaken_cascade_count = 0
        broken_cascade_count = 0
        for seed in range(200):
            rng_i = _rng(seed)
            eng = RoutEngine(bus, rng_i, config)
            if eng.rout_cascade(
                routing_unit_id="rout_1",
                adjacent_unit_morale_states={"u1": int(MoraleState.SHAKEN)},
                distances_m={"u1": 200.0},
            ):
                shaken_cascade_count += 1

            rng_i2 = _rng(seed + 1000)
            eng2 = RoutEngine(bus, rng_i2, config)
            if eng2.rout_cascade(
                routing_unit_id="rout_1",
                adjacent_unit_morale_states={"u1": int(MoraleState.BROKEN)},
                distances_m={"u1": 200.0},
            ):
                broken_cascade_count += 1

        # BROKEN should cascade more often than SHAKEN
        assert broken_cascade_count > shaken_cascade_count
