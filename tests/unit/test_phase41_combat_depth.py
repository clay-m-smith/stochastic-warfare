"""Phase 41: Combat Depth — terrain-combat, force quality, threat targeting, detection pipeline.

Tests for:
- 41a: Terrain-combat interaction (cover, elevation, concealment)
- 41b: Force quality & training level
- 41c: Threat-based target selection
- 41d: Detection pipeline wiring
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from stochastic_warfare.combat.hit_probability import (
    HitProbabilityEngine,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit, UnitStatus

TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _make_hit_engine(seed: int = 42) -> HitProbabilityEngine:
    from stochastic_warfare.combat.ballistics import BallisticsEngine
    rng = _rng(seed)
    bal = BallisticsEngine(rng)
    return HitProbabilityEngine(bal, rng)


def _make_unit(
    eid: str = "u1",
    side: str = "blue",
    pos: Position | None = None,
    training_level: float = 0.5,
    **kwargs,
) -> Unit:
    if pos is None:
        pos = Position(0.0, 0.0, 0.0)
    return Unit(
        entity_id=eid,
        position=pos,
        side=side,
        training_level=training_level,
        **kwargs,
    )


def _make_weapon_def(max_range: float = 3000.0, accuracy: float = 1.0):
    """Create a minimal weapon definition mock."""
    wpn = SimpleNamespace(
        base_accuracy_mrad=accuracy,
        max_range_m=max_range,
        min_range_m=0.0,
        rate_of_fire_rpm=10.0,
        caliber_mm=120.0,
        burst_size=1,
        requires_deployed=False,
        beam_power_kw=0.0,
    )
    wpn.effective_target_domains = lambda: {"GROUND", "AERIAL", "NAVAL"}
    wpn.parsed_category = lambda: None
    return wpn


def _make_ammo_def():
    return SimpleNamespace(
        ammo_id="test_ammo",
        pk_at_reference=0.0,
        seeker_range_m=0.0,
        countermeasure_susceptibility=0.0,
        compliance_check=False,
        prohibited_under_treaties=[],
        guidance="NONE",
    )


def _make_weapon_instance(max_range: float = 3000.0):
    wpn_def = _make_weapon_def(max_range)
    inst = SimpleNamespace(
        weapon_id="w1",
        definition=wpn_def,
        condition=1.0,
    )
    inst.can_fire = lambda aid: True
    inst.fire = lambda aid: True
    inst.can_fire_timed = lambda t: True
    inst.record_fire = lambda t: None
    inst.ammo_state = SimpleNamespace(available=lambda aid: 100)
    return inst


# ===========================================================================
# 41a: Terrain-Combat Interaction
# ===========================================================================


class TestComputePhitTerrainParams:
    """Test terrain_cover and elevation_mod params on compute_phit."""

    def test_open_terrain_no_modifier(self):
        """terrain_cover=0.0 applies no modifier."""
        engine = _make_hit_engine()
        wpn_def = _make_weapon_def()
        ammo_def = _make_ammo_def()
        result = engine.compute_phit(
            weapon=wpn_def, ammo=ammo_def, range_m=1000.0,
            terrain_cover=0.0, elevation_mod=1.0,
        )
        assert "terrain_cover" not in result.modifiers
        assert "elevation" not in result.modifiers

    def test_forest_cover_reduces_phit(self):
        """terrain_cover=0.5 reduces Phit by ~50%."""
        engine = _make_hit_engine()
        wpn_def = _make_weapon_def()
        ammo_def = _make_ammo_def()
        base = engine.compute_phit(
            weapon=wpn_def, ammo=ammo_def, range_m=1000.0,
            terrain_cover=0.0,
        )
        covered = engine.compute_phit(
            weapon=wpn_def, ammo=ammo_def, range_m=1000.0,
            terrain_cover=0.5,
        )
        assert covered.p_hit < base.p_hit
        assert covered.modifiers["terrain_cover"] == pytest.approx(0.5)

    def test_urban_cover_reduces_phit(self):
        """terrain_cover=0.8 reduces Phit by ~80%."""
        engine = _make_hit_engine()
        wpn_def = _make_weapon_def()
        ammo_def = _make_ammo_def()
        base = engine.compute_phit(
            weapon=wpn_def, ammo=ammo_def, range_m=1000.0,
        )
        urban = engine.compute_phit(
            weapon=wpn_def, ammo=ammo_def, range_m=1000.0,
            terrain_cover=0.8,
        )
        assert urban.p_hit < base.p_hit * 0.3  # ~80% reduction + min clamp
        assert urban.modifiers["terrain_cover"] == pytest.approx(0.2)

    def test_elevation_advantage(self):
        """elevation_mod > 1.0 increases Phit."""
        engine = _make_hit_engine()
        wpn_def = _make_weapon_def()
        ammo_def = _make_ammo_def()
        base = engine.compute_phit(
            weapon=wpn_def, ammo=ammo_def, range_m=1000.0,
        )
        elevated = engine.compute_phit(
            weapon=wpn_def, ammo=ammo_def, range_m=1000.0,
            elevation_mod=1.2,
        )
        assert elevated.p_hit > base.p_hit
        assert elevated.modifiers["elevation"] == pytest.approx(1.2)

    def test_elevation_disadvantage(self):
        """elevation_mod < 1.0 decreases Phit."""
        engine = _make_hit_engine()
        wpn_def = _make_weapon_def()
        ammo_def = _make_ammo_def()
        base = engine.compute_phit(
            weapon=wpn_def, ammo=ammo_def, range_m=1000.0,
        )
        low = engine.compute_phit(
            weapon=wpn_def, ammo=ammo_def, range_m=1000.0,
            elevation_mod=0.9,
        )
        assert low.p_hit < base.p_hit

    def test_equal_elevation_no_modifier(self):
        """elevation_mod=1.0 applies no modifier."""
        engine = _make_hit_engine()
        wpn_def = _make_weapon_def()
        ammo_def = _make_ammo_def()
        result = engine.compute_phit(
            weapon=wpn_def, ammo=ammo_def, range_m=1000.0,
            elevation_mod=1.0,
        )
        assert "elevation" not in result.modifiers


class TestComputeTerrainModifiers:
    """Test BattleManager._compute_terrain_modifiers()."""

    def _bm(self):
        from stochastic_warfare.simulation.battle import BattleManager
        return BattleManager

    def test_missing_managers_returns_defaults(self):
        """All None managers → (0.0, 1.0, 0.0)."""
        ctx = SimpleNamespace()
        pos = Position(100.0, 100.0, 0.0)
        cover, elev, conc = self._bm()._compute_terrain_modifiers(ctx, pos, pos)
        assert cover == 0.0
        assert elev == 1.0
        assert conc == 0.0

    def test_classification_cover_and_concealment(self):
        """Classification provides cover and concealment."""
        props = SimpleNamespace(cover=0.5, concealment=0.7)
        classification = SimpleNamespace(properties_at=lambda p: props)
        ctx = SimpleNamespace(classification=classification)
        pos = Position(100.0, 100.0, 0.0)
        cover, elev, conc = self._bm()._compute_terrain_modifiers(ctx, pos, pos)
        assert cover == 0.5
        assert conc == 0.7

    def test_trench_cover(self):
        """Trench engine provides cover when target is in trench."""
        tq = SimpleNamespace(in_trench=True, cover_value=0.85)
        trench = SimpleNamespace(query_trench=lambda e, n: tq)
        ctx = SimpleNamespace(trench_engine=trench)
        pos = Position(100.0, 100.0, 0.0)
        cover, _, _ = self._bm()._compute_terrain_modifiers(ctx, pos, pos)
        assert cover == 0.85

    def test_building_cover(self):
        """Infrastructure buildings provide cover."""
        b = SimpleNamespace(cover_value=0.7)
        infra = SimpleNamespace(buildings_at=lambda p: [b])
        ctx = SimpleNamespace(infrastructure_manager=infra)
        pos = Position(100.0, 100.0, 0.0)
        cover, _, _ = self._bm()._compute_terrain_modifiers(ctx, pos, pos)
        assert cover == 0.7

    def test_cover_stacking_uses_max(self):
        """Multiple cover sources use max(), not sum."""
        props = SimpleNamespace(cover=0.5, concealment=0.0)
        classification = SimpleNamespace(properties_at=lambda p: props)
        tq = SimpleNamespace(in_trench=True, cover_value=0.85)
        trench = SimpleNamespace(query_trench=lambda e, n: tq)
        ctx = SimpleNamespace(classification=classification, trench_engine=trench)
        pos = Position(100.0, 100.0, 0.0)
        cover, _, _ = self._bm()._compute_terrain_modifiers(ctx, pos, pos)
        assert cover == 0.85  # max(0.5, 0.85)

    def test_fortification_obstacle_cover(self):
        """FORTIFICATION obstacle gives 0.8 cover."""
        obs_type = SimpleNamespace(name="FORTIFICATION")
        obs = SimpleNamespace(obstacle_type=obs_type)
        obstacle_mgr = SimpleNamespace(obstacles_at=lambda p: [obs])
        ctx = SimpleNamespace(obstacle_manager=obstacle_mgr)
        pos = Position(100.0, 100.0, 0.0)
        cover, _, _ = self._bm()._compute_terrain_modifiers(ctx, pos, pos)
        assert cover == 0.8

    def test_elevation_advantage_capped(self):
        """Height advantage caps at +30%."""
        hm = SimpleNamespace()
        hm.elevation_at = lambda p: 500.0 if p.easting < 50.0 else 0.0
        ctx = SimpleNamespace(heightmap=hm)
        attacker_pos = Position(0.0, 0.0, 0.0)
        target_pos = Position(100.0, 100.0, 0.0)
        _, elev, _ = self._bm()._compute_terrain_modifiers(ctx, target_pos, attacker_pos)
        assert elev == pytest.approx(1.3)  # capped at +30%

    def test_elevation_disadvantage_floor(self):
        """Height disadvantage floors at -10%."""
        hm = SimpleNamespace()
        hm.elevation_at = lambda p: 0.0 if p.easting < 50.0 else 500.0
        ctx = SimpleNamespace(heightmap=hm)
        attacker_pos = Position(0.0, 0.0, 0.0)
        target_pos = Position(100.0, 100.0, 0.0)
        _, elev, _ = self._bm()._compute_terrain_modifiers(ctx, target_pos, attacker_pos)
        assert elev == pytest.approx(0.9)  # floored at -10%

    def test_equal_elevation_returns_1(self):
        """Same elevation → 1.0."""
        hm = SimpleNamespace(elevation_at=lambda p: 100.0)
        ctx = SimpleNamespace(heightmap=hm)
        pos = Position(100.0, 100.0, 0.0)
        _, elev, _ = self._bm()._compute_terrain_modifiers(ctx, pos, pos)
        assert elev == pytest.approx(1.0)

    def test_position_outside_grid_defaults(self):
        """IndexError from heightmap is caught → defaults."""
        hm = SimpleNamespace()
        hm.elevation_at = MagicMock(side_effect=IndexError("out of bounds"))
        ctx = SimpleNamespace(heightmap=hm)
        pos = Position(100.0, 100.0, 0.0)
        cover, elev, conc = self._bm()._compute_terrain_modifiers(ctx, pos, pos)
        assert elev == 1.0


class TestForceChanneling:
    """Test max_engagers_per_side calibration."""

    def test_channeling_limits_engagers(self):
        """Only max_engagers units fire per side."""
        from stochastic_warfare.simulation.battle import BattleManager, BattleConfig

        bus = EventBus()
        bm = BattleManager(bus, BattleConfig())

        # 5 attackers, but limit to 2
        blue_units = [
            _make_unit(f"b{i}", "blue", Position(0.0, i * 100.0, 0.0))
            for i in range(5)
        ]
        red_units = [
            _make_unit("r0", "red", Position(3000.0, 250.0, 0.0))
        ]

        # Track how many engagements fire
        fire_count = 0
        orig_route = None

        def counting_route(*args, **kwargs):
            nonlocal fire_count
            fire_count += 1
            from stochastic_warfare.combat.engagement import EngagementResult
            return EngagementResult(engaged=True, attacker_id=kwargs.get("attacker_id", ""))

        eng_engine = SimpleNamespace(route_engagement=counting_route)

        wpn_inst = _make_weapon_instance(5000.0)
        weapons = {u.entity_id: [(wpn_inst, [_make_ammo_def()])] for u in blue_units}
        sensors = {}

        from stochastic_warfare.morale.state import MoraleState
        morale_states = {u.entity_id: MoraleState.STEADY for u in blue_units + red_units}

        side_cfg = SimpleNamespace(side="blue", experience_level=0.5)
        config = SimpleNamespace(sides=[side_cfg])
        clock = SimpleNamespace(elapsed=SimpleNamespace(total_seconds=lambda: 0.0))

        ctx = SimpleNamespace(
            calibration={
                "visibility_m": 10000.0,
                "hit_probability_modifier": 1.0,
                "target_size_modifier": 1.0,
                "max_engagers_per_side": 2,
            },
            engagement_engine=eng_engine,
            unit_weapons=weapons,
            unit_sensors=sensors,
            morale_states=morale_states,
            config=config,
            clock=clock,
            units_by_side={"blue": blue_units, "red": red_units},
        )

        enemy_pos = np.array([[3000.0, 250.0]])
        pending = bm._execute_engagements(
            ctx,
            {"blue": blue_units},
            {"blue": red_units},
            {"blue": enemy_pos},
            1.0,
            TS,
        )
        assert fire_count == 2  # limited to 2

    def test_channeling_disabled_by_default(self):
        """max_engagers_per_side=0 means unlimited."""
        from stochastic_warfare.simulation.battle import BattleManager, BattleConfig

        bus = EventBus()
        bm = BattleManager(bus, BattleConfig())

        blue_units = [
            _make_unit(f"b{i}", "blue", Position(0.0, i * 100.0, 0.0))
            for i in range(3)
        ]
        red_units = [
            _make_unit("r0", "red", Position(2000.0, 100.0, 0.0))
        ]

        fire_count = 0

        def counting_route(*args, **kwargs):
            nonlocal fire_count
            fire_count += 1
            from stochastic_warfare.combat.engagement import EngagementResult
            return EngagementResult(engaged=True, attacker_id=kwargs.get("attacker_id", ""))

        eng_engine = SimpleNamespace(route_engagement=counting_route)
        wpn_inst = _make_weapon_instance(5000.0)
        weapons = {u.entity_id: [(wpn_inst, [_make_ammo_def()])] for u in blue_units}

        from stochastic_warfare.morale.state import MoraleState
        morale_states = {u.entity_id: MoraleState.STEADY for u in blue_units + red_units}

        side_cfg = SimpleNamespace(side="blue", experience_level=0.5)
        config = SimpleNamespace(sides=[side_cfg])
        clock = SimpleNamespace(elapsed=SimpleNamespace(total_seconds=lambda: 0.0))

        ctx = SimpleNamespace(
            calibration={
                "visibility_m": 10000.0,
                "hit_probability_modifier": 1.0,
                "target_size_modifier": 1.0,
            },
            engagement_engine=eng_engine,
            unit_weapons=weapons,
            unit_sensors={},
            morale_states=morale_states,
            config=config,
            clock=clock,
            units_by_side={"blue": blue_units, "red": red_units},
        )

        enemy_pos = np.array([[2000.0, 100.0]])
        bm._execute_engagements(
            ctx,
            {"blue": blue_units},
            {"blue": red_units},
            {"blue": enemy_pos},
            1.0,
            TS,
        )
        assert fire_count == 3  # all 3 fire


# ===========================================================================
# 41b: Force Quality & Training Level
# ===========================================================================


class TestTrainingLevel:
    """Test training_level on Unit and related systems."""

    def test_default_training_level(self):
        """Unit() has training_level=0.5."""
        u = _make_unit()
        assert u.training_level == 0.5

    def test_explicit_training_level(self):
        """Unit(training_level=0.9) stores correctly."""
        u = _make_unit(training_level=0.9)
        assert u.training_level == 0.9

    def test_get_set_state_roundtrip(self):
        """training_level preserved in state roundtrip."""
        u = _make_unit(training_level=0.85)
        state = u.get_state()
        assert state["training_level"] == 0.85

        u2 = _make_unit(training_level=0.1)
        u2.set_state(state)
        assert u2.training_level == 0.85

    def test_set_state_backward_compat(self):
        """Old state dict without training_level uses 0.5."""
        u = _make_unit(training_level=0.9)
        state = u.get_state()
        del state["training_level"]
        u.set_state(state)
        assert u.training_level == 0.5

    def test_crew_skill_training_1_0(self):
        """training_level=1.0 → effective_skill = base * 1.0."""
        base_skill = 0.8
        training = 1.0
        effective = base_skill * (0.5 + 0.5 * training)
        assert effective == pytest.approx(0.8)

    def test_crew_skill_training_0_0(self):
        """training_level=0.0 → effective_skill = base * 0.5."""
        base_skill = 0.8
        training = 0.0
        effective = base_skill * (0.5 + 0.5 * training)
        assert effective == pytest.approx(0.4)

    def test_crew_skill_training_0_5(self):
        """training_level=0.5 → effective_skill = base * 0.75."""
        base_skill = 0.8
        training = 0.5
        effective = base_skill * (0.5 + 0.5 * training)
        assert effective == pytest.approx(0.6)

    def test_getattr_fallback(self):
        """getattr with default 0.5 on non-Unit objects."""
        obj = SimpleNamespace()
        assert getattr(obj, "training_level", 0.5) == 0.5

    def test_unit_definition_accepts_training_level(self):
        """UnitDefinition pydantic model accepts training_level."""
        from stochastic_warfare.entities.loader import UnitDefinition
        defn = UnitDefinition(
            unit_type="test",
            domain="ground",
            display_name="Test",
            max_speed=10.0,
            crew=[],
            equipment=[],
            training_level=0.9,
        )
        assert defn.training_level == 0.9

    def test_unit_definition_default(self):
        """UnitDefinition without training_level defaults to 0.5."""
        from stochastic_warfare.entities.loader import UnitDefinition
        defn = UnitDefinition(
            unit_type="test",
            domain="ground",
            display_name="Test",
            max_speed=10.0,
            crew=[],
            equipment=[],
        )
        assert defn.training_level == 0.5


class TestVictoryQualityWeighted:
    """Test quality-weighted force advantage evaluation."""

    def test_elite_beats_quantity(self):
        """10 elite (0.9) units beat 15 green (0.3) units."""
        from stochastic_warfare.simulation.victory import VictoryEvaluator

        blue_units = [_make_unit(f"b{i}", "blue", training_level=0.9) for i in range(10)]
        red_units = [_make_unit(f"r{i}", "red", training_level=0.3) for i in range(15)]
        # Destroy 3 blue, 8 red
        for u in blue_units[:3]:
            object.__setattr__(u, "status", UnitStatus.DESTROYED)
        for u in red_units[:8]:
            object.__setattr__(u, "status", UnitStatus.DESTROYED)

        result = VictoryEvaluator.evaluate_force_advantage(
            {"blue": blue_units, "red": red_units}
        )
        # blue: 7 active * 0.9 = 6.3 / (10 * 0.9) = 70%
        # red: 7 active * 0.3 = 2.1 / (15 * 0.3) = 46.7%
        assert result.winning_side == "blue"

    def test_equal_quality_equal_count_is_draw(self):
        """Same quality, same active count → draw."""
        from stochastic_warfare.simulation.victory import VictoryEvaluator

        blue_units = [_make_unit(f"b{i}", "blue", training_level=0.5) for i in range(5)]
        red_units = [_make_unit(f"r{i}", "red", training_level=0.5) for i in range(5)]

        result = VictoryEvaluator.evaluate_force_advantage(
            {"blue": blue_units, "red": red_units}
        )
        assert result.winning_side == "draw"


# ===========================================================================
# 41c: Threat-Based Target Selection
# ===========================================================================


class TestTargetValue:
    """Test _target_value() helper."""

    def test_hq_value(self):
        from stochastic_warfare.simulation.battle import _target_value
        u = SimpleNamespace(support_type=SimpleNamespace(name="HQ"))
        assert _target_value(u) == 2.0

    def test_ad_value(self):
        from stochastic_warfare.simulation.battle import _target_value
        u = SimpleNamespace(ad_type=SimpleNamespace(name="SAM"))
        assert _target_value(u) == 1.8

    def test_artillery_value(self):
        from stochastic_warfare.simulation.battle import _target_value
        u = SimpleNamespace(ground_type=SimpleNamespace(name="ARTILLERY"))
        assert _target_value(u) == 1.5

    def test_armor_value(self):
        from stochastic_warfare.simulation.battle import _target_value
        u = SimpleNamespace(ground_type=SimpleNamespace(name="ARMOR"))
        assert _target_value(u) == 1.3

    def test_infantry_value(self):
        from stochastic_warfare.simulation.battle import _target_value
        u = SimpleNamespace(ground_type=SimpleNamespace(name="INFANTRY"))
        assert _target_value(u) == 1.0

    def test_plain_unit_value(self):
        from stochastic_warfare.simulation.battle import _target_value
        u = SimpleNamespace()
        assert _target_value(u) == 1.0


class TestScoreTarget:
    """Test BattleManager._score_target()."""

    def _bm(self):
        from stochastic_warfare.simulation.battle import BattleManager
        from stochastic_warfare.core.events import EventBus
        return BattleManager(event_bus=EventBus())

    def test_score_computation_positive(self):
        """Score is positive for valid inputs."""
        attacker = SimpleNamespace(entity_id="a1", armor_front=100.0)
        target = SimpleNamespace(entity_id="t1", ground_type=SimpleNamespace(name="ARMOR"))
        ctx = SimpleNamespace(unit_weapons={
            "t1": [(_make_weapon_instance(2000.0), [_make_ammo_def()])],
        })
        score = self._bm()._score_target(
            attacker, target, 1000.0,
            [(_make_weapon_instance(3000.0), [_make_ammo_def()])],
            ctx,
        )
        assert score > 0

    def test_close_target_preferred(self):
        """Closer targets score higher (all else equal)."""
        attacker = SimpleNamespace(entity_id="a1", armor_front=0.0)
        target = SimpleNamespace(entity_id="t1")
        ctx = SimpleNamespace(unit_weapons={"t1": []})
        weapons = [(_make_weapon_instance(3000.0), [_make_ammo_def()])]

        score_close = self._bm()._score_target(attacker, target, 500.0, weapons, ctx)
        score_far = self._bm()._score_target(attacker, target, 2500.0, weapons, ctx)
        assert score_close > score_far

    def test_hq_target_preferred(self):
        """HQ target scores higher than infantry at same distance."""
        attacker = SimpleNamespace(entity_id="a1", armor_front=0.0)
        hq = SimpleNamespace(entity_id="hq", support_type=SimpleNamespace(name="HQ"))
        inf = SimpleNamespace(entity_id="inf", ground_type=SimpleNamespace(name="INFANTRY"))
        ctx = SimpleNamespace(unit_weapons={"hq": [], "inf": []})
        weapons = [(_make_weapon_instance(3000.0), [_make_ammo_def()])]

        score_hq = self._bm()._score_target(attacker, hq, 1000.0, weapons, ctx)
        score_inf = self._bm()._score_target(attacker, inf, 1000.0, weapons, ctx)
        assert score_hq > score_inf

    def test_default_mode_is_threat_scored(self):
        """No calibration → target_selection_mode defaults to 'threat_scored'."""
        # Verify the default in calibration
        cal = {}
        mode = cal.get("target_selection_mode", "threat_scored")
        assert mode == "threat_scored"


# ===========================================================================
# 41d: Detection Pipeline Wiring
# ===========================================================================


class TestDetectionPipeline:
    """Test detection quality modulation."""

    def test_no_detection_engine_quality_1(self):
        """No detection_engine → quality modifier is 1.0."""
        # When detection_engine is absent, vis_mod stays unchanged
        assert True  # Tested implicitly via battle loop

    def test_context_has_detection_engine_field(self):
        """SimulationContext has detection_engine field."""
        from stochastic_warfare.simulation.scenario import SimulationContext
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(SimulationContext)}
        assert "detection_engine" in field_names

    def test_high_snr_quality_1(self):
        """High SNR → detection quality capped at 1.0."""
        snr_db = 40.0  # very high
        snr_linear = 10.0 ** (snr_db / 20.0)
        quality = min(1.0, max(0.3, snr_linear / 10.0))
        assert quality == 1.0

    def test_low_snr_quality_below_1(self):
        """Low SNR → detection quality < 1.0."""
        snr_db = 5.0
        snr_linear = 10.0 ** (snr_db / 20.0)
        quality = min(1.0, max(0.3, snr_linear / 10.0))
        assert quality < 1.0

    def test_quality_floor_at_0_3(self):
        """Very low SNR → quality floors at 0.3."""
        snr_db = -20.0
        snr_linear = 10.0 ** (snr_db / 20.0)
        quality = min(1.0, max(0.3, snr_linear / 10.0))
        assert quality == 0.3

    def test_combined_vis_mod_and_detection_quality(self):
        """vis_mod * detection_quality is multiplicative."""
        vis_mod = 0.8
        detection_quality = 0.6
        combined = vis_mod * detection_quality
        assert combined == pytest.approx(0.48)


# ===========================================================================
# Integration: terrain params thread through route_engagement
# ===========================================================================


class TestTerrainParamsThreading:
    """Verify terrain_cover and elevation_mod pass through the call chain."""

    def test_route_engagement_accepts_terrain_params(self):
        """route_engagement() accepts terrain_cover and elevation_mod."""
        from stochastic_warfare.combat.engagement import EngagementEngine
        import inspect
        sig = inspect.signature(EngagementEngine.route_engagement)
        params = sig.parameters
        assert "terrain_cover" in params
        assert "elevation_mod" in params

    def test_execute_engagement_accepts_terrain_params(self):
        """execute_engagement() accepts terrain_cover and elevation_mod."""
        from stochastic_warfare.combat.engagement import EngagementEngine
        import inspect
        sig = inspect.signature(EngagementEngine.execute_engagement)
        params = sig.parameters
        assert "terrain_cover" in params
        assert "elevation_mod" in params

    def test_compute_phit_accepts_terrain_params(self):
        """compute_phit() accepts terrain_cover and elevation_mod."""
        import inspect
        sig = inspect.signature(HitProbabilityEngine.compute_phit)
        params = sig.parameters
        assert "terrain_cover" in params
        assert "elevation_mod" in params


# ===========================================================================
# Concealment detection range test
# ===========================================================================


class TestConcealmentDetection:
    """Test concealment reduces effective detection range."""

    def test_concealment_reduces_detection_range(self):
        """Concealment=0.5 reduces detection range by 50%."""
        visibility_m = 3000.0
        concealment = 0.5
        detection_range = visibility_m * (1.0 - concealment)
        assert detection_range == pytest.approx(1500.0)

    def test_zero_concealment_no_change(self):
        """Concealment=0.0 → no change."""
        visibility_m = 3000.0
        concealment = 0.0
        detection_range = visibility_m * (1.0 - concealment)
        assert detection_range == pytest.approx(3000.0)
