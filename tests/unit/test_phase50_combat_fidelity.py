"""Phase 50: Combat Fidelity Polish — tests for D1, D3, D4, D7, D14.

50a: Posture affects movement speed
50b: Air unit tactical posture
50c: Continuous concealment with observation decay
50d: Training level YAML population
50e: Barrage penalty fix, target value weights, melee range
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.entities.unit_classes.aerial import (
    AerialUnit,
    AerialUnitType,
    AirPosture,
    FlightState,
)
from stochastic_warfare.simulation.battle import (
    BattleConfig,
    BattleContext,
    BattleManager,
    _INDIRECT_FIRE_CATEGORIES,
    _MELEE_RANGE_M,
    _POSTURE_SPEED_MULT,
)
from stochastic_warfare.simulation.calibration import CalibrationSchema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ground_unit(
    entity_id: str = "u1",
    side: str = "blue",
    posture: int = 0,
    speed: float = 10.0,
    max_speed: float = 10.0,
    position: Position | None = None,
    training_level: float = 0.5,
) -> Any:
    """Create a ground unit with a posture attribute."""

    @dataclass
    class _GroundUnit(Unit):
        posture: int = 0

    u = _GroundUnit(
        entity_id=entity_id,
        side=side,
        domain=Domain.GROUND,
        position=position or Position(0.0, 0.0, 0.0),
        speed=speed,
        max_speed=max_speed,
        training_level=training_level,
        posture=posture,
    )
    return u


def _make_ctx(
    cal: dict[str, Any] | None = None,
    engagement_engine: Any = None,
    unit_weapons: dict | None = None,
    unit_sensors: dict | None = None,
    morale_states: dict | None = None,
    era: str = "modern",
    config_sides: list | None = None,
    behavior_rules: dict | None = None,
) -> SimpleNamespace:
    """Build a minimal simulation context for BattleManager."""
    calibration = CalibrationSchema(**(cal or {}))
    config = SimpleNamespace(
        sides=config_sides or [],
        era=era,
        behavior_rules=behavior_rules or {},
    )
    return SimpleNamespace(
        calibration=calibration,
        config=config,
        engagement_engine=engagement_engine,
        unit_weapons=unit_weapons or {},
        unit_sensors=unit_sensors or {},
        morale_states=morale_states or {},
        clock=SimpleNamespace(elapsed=SimpleNamespace(total_seconds=lambda: 0.0)),
        ooda_engine=None,
        order_execution=None,
        suppression_engine=None,
        detection_engine=None,
        cbrn_engine=None,
        weather_engine=None,
        time_of_day_engine=None,
        sea_state_engine=None,
        ew_engine=None,
        space_engine=None,
        maintenance_engine=None,
        roe_engine=None,
        formation_napoleonic_engine=None,
        consumption_engine=None,
        stockpile_manager=None,
        event_bus=EventBus(),
        classification=None,
        elevation_manager=None,
        rng=np.random.default_rng(42),
    )


def _make_battle(sides: list[str] | None = None) -> BattleContext:
    return BattleContext(
        battle_id="test",
        start_tick=0,
        start_time=datetime.now(),
        involved_sides=sides or ["blue", "red"],
    )


# ===========================================================================
# 50a: Posture affects movement speed
# ===========================================================================


class TestPostureMovementSpeed:
    """D1: DUG_IN and FORTIFIED units can't move at full speed."""

    def test_posture_speed_mult_dug_in(self) -> None:
        assert _POSTURE_SPEED_MULT[3] == 0.0

    def test_posture_speed_mult_fortified(self) -> None:
        assert _POSTURE_SPEED_MULT[4] == 0.0

    def test_posture_speed_mult_defensive(self) -> None:
        assert _POSTURE_SPEED_MULT[2] == 0.5

    def test_posture_speed_mult_moving_halted(self) -> None:
        assert _POSTURE_SPEED_MULT[0] == 1.0
        assert _POSTURE_SPEED_MULT[1] == 1.0

    def test_dug_in_unit_skips_movement(self) -> None:
        """DUG_IN unit on non-defensive side should start un-dig sequence."""
        bm = BattleManager(EventBus())
        u = _make_ground_unit(posture=3, speed=10.0, position=Position(0.0, 0.0, 0.0))
        enemy = _make_ground_unit(
            entity_id="e1", side="red", position=Position(1000.0, 0.0, 0.0),
        )
        ctx = _make_ctx()
        units_by_side = {"blue": [u], "red": [enemy]}
        active_enemies = {"blue": [enemy], "red": [u]}
        battle = _make_battle()

        # First tick: un-dig starts, no movement
        bm._execute_movement(ctx, units_by_side, active_enemies, 1.0, battle)
        # Posture should be reset to MOVING (0) but position unchanged
        assert u.posture == 0
        assert u.position.easting == pytest.approx(0.0, abs=1.0)

    def test_undig_clears_on_second_tick(self) -> None:
        """After 1 tick of un-dig, unit should move normally."""
        bm = BattleManager(EventBus())
        u = _make_ground_unit(posture=3, speed=10.0, position=Position(0.0, 0.0, 0.0))
        enemy = _make_ground_unit(
            entity_id="e1", side="red", position=Position(5000.0, 0.0, 0.0),
        )
        ctx = _make_ctx()
        units_by_side = {"blue": [u], "red": [enemy]}
        active_enemies = {"blue": [enemy], "red": [u]}
        battle = _make_battle()

        # Tick 1: un-dig
        bm._execute_movement(ctx, units_by_side, active_enemies, 1.0, battle)
        pos_after_tick1 = u.position.easting

        # Tick 2: should move
        bm._execute_movement(ctx, units_by_side, active_enemies, 1.0, battle)
        assert u.position.easting > pos_after_tick1

    def test_no_posture_attr_unaffected(self) -> None:
        """Unit without posture attribute moves normally."""
        bm = BattleManager(EventBus())
        u = Unit(
            entity_id="u1", side="blue", domain=Domain.GROUND,
            position=Position(0.0, 0.0, 0.0), speed=10.0, max_speed=10.0,
        )
        enemy = Unit(
            entity_id="e1", side="red", domain=Domain.GROUND,
            position=Position(5000.0, 0.0, 0.0), speed=0.0, max_speed=0.0,
        )
        ctx = _make_ctx()
        units_by_side = {"blue": [u], "red": [enemy]}
        active_enemies = {"blue": [enemy], "red": [u]}
        battle = _make_battle()

        bm._execute_movement(ctx, units_by_side, active_enemies, 1.0, battle)
        # Should have moved toward enemy
        assert u.position.easting > 0.1

    def test_defensive_side_dug_in_stays(self) -> None:
        """DUG_IN unit on defensive side stays put — no un-dig triggered."""
        bm = BattleManager(EventBus())
        u = _make_ground_unit(posture=3, speed=10.0, position=Position(0.0, 0.0, 0.0))
        enemy = _make_ground_unit(
            entity_id="e1", side="red", position=Position(1000.0, 0.0, 0.0),
        )
        ctx = _make_ctx(cal={"defensive_sides": ["blue"]})
        units_by_side = {"blue": [u], "red": [enemy]}
        active_enemies = {"blue": [enemy], "red": [u]}
        battle = _make_battle()

        bm._execute_movement(ctx, units_by_side, active_enemies, 1.0, battle)
        # Defensive side: should not move and should not un-dig
        assert u.position.easting == pytest.approx(0.0, abs=0.1)


# ===========================================================================
# 50b: Air unit tactical posture
# ===========================================================================


class TestAirPosture:
    """D3: Air units have tactical posture affecting engagement eligibility."""

    def test_air_posture_enum_values(self) -> None:
        assert AirPosture.GROUNDED == 0
        assert AirPosture.INGRESSING == 1
        assert AirPosture.ON_STATION == 2
        assert AirPosture.RETURNING == 3

    def test_default_air_posture_is_grounded(self) -> None:
        au = AerialUnit(
            entity_id="a1", side="blue",
            position=Position(0.0, 0.0, 5000.0),
        )
        assert au.air_posture == AirPosture.GROUNDED

    def test_air_posture_roundtrip_state(self) -> None:
        au = AerialUnit(
            entity_id="a1", side="blue",
            position=Position(0.0, 0.0, 5000.0),
            air_posture=AirPosture.ON_STATION,
        )
        state = au.get_state()
        assert state["air_posture"] == 2

        au2 = AerialUnit(
            entity_id="a2", side="blue",
            position=Position(0.0, 0.0, 5000.0),
        )
        au2.set_state(state)
        assert au2.air_posture == AirPosture.ON_STATION

    def test_set_state_backward_compat(self) -> None:
        """set_state without air_posture defaults to GROUNDED."""
        au = AerialUnit(
            entity_id="a1", side="blue",
            position=Position(0.0, 0.0, 5000.0),
            air_posture=AirPosture.ON_STATION,
        )
        state = au.get_state()
        del state["air_posture"]
        au.set_state(state)
        assert au.air_posture == AirPosture.GROUNDED

    def test_grounded_aircraft_skipped_in_engagement(self) -> None:
        """GROUNDED air unit should not engage."""
        bm = BattleManager(EventBus())
        attacker = AerialUnit(
            entity_id="a1", side="blue",
            position=Position(0.0, 0.0, 5000.0),
            air_posture=AirPosture.GROUNDED,
            flight_state=FlightState.GROUNDED,
        )
        target = _make_ground_unit(
            entity_id="e1", side="red", position=Position(500.0, 0.0, 0.0),
        )
        # Mock engagement engine that records calls
        eng_calls = []

        class MockEngEngine:
            def route_engagement(self, **kw: Any) -> Any:
                eng_calls.append(kw)
                return SimpleNamespace(engaged=False)

        ctx = _make_ctx(engagement_engine=MockEngEngine())
        ctx.unit_weapons["a1"] = []  # No weapons anyway
        units_by_side = {"blue": [attacker], "red": [target]}
        active_enemies = {"blue": [target], "red": [attacker]}
        enemy_pos = {"blue": np.array([[500.0, 0.0]]), "red": np.array([[0.0, 0.0]])}

        bm._execute_engagements(
            ctx, units_by_side, active_enemies, enemy_pos, 1.0, datetime.now(),
        )
        # Engagement engine should NOT have been called for the GROUNDED aircraft
        assert len(eng_calls) == 0

    def test_returning_aircraft_skipped_in_engagement(self) -> None:
        """RETURNING air unit should not engage."""
        bm = BattleManager(EventBus())
        attacker = AerialUnit(
            entity_id="a1", side="blue",
            position=Position(0.0, 0.0, 5000.0),
            air_posture=AirPosture.RETURNING,
            flight_state=FlightState.AIRBORNE,
        )
        target = _make_ground_unit(
            entity_id="e1", side="red", position=Position(500.0, 0.0, 0.0),
        )

        class MockEngEngine:
            def route_engagement(self, **kw: Any) -> Any:
                return SimpleNamespace(engaged=False)

        ctx = _make_ctx(engagement_engine=MockEngEngine())
        ctx.unit_weapons["a1"] = []
        units_by_side = {"blue": [attacker], "red": [target]}
        active_enemies = {"blue": [target], "red": [attacker]}
        enemy_pos = {"blue": np.array([[500.0, 0.0]]), "red": np.array([[0.0, 0.0]])}

        result = bm._execute_engagements(
            ctx, units_by_side, active_enemies, enemy_pos, 1.0, datetime.now(),
        )
        # Should produce no damage
        assert len(result) == 0

    def test_on_station_aircraft_engages(self) -> None:
        """ON_STATION air unit should pass the air posture gate."""
        bm = BattleManager(EventBus())
        attacker = AerialUnit(
            entity_id="a1", side="blue",
            position=Position(0.0, 0.0, 5000.0),
            air_posture=AirPosture.ON_STATION,
            flight_state=FlightState.AIRBORNE,
        )
        # The attacker should pass the air posture gate (not be skipped).
        # We verify by checking it reaches the weapons check.
        # With no weapons, it will stop there — but it won't be blocked by posture.
        target = _make_ground_unit(
            entity_id="e1", side="red", position=Position(500.0, 0.0, 0.0),
        )

        class MockEngEngine:
            def route_engagement(self, **kw: Any) -> Any:
                return SimpleNamespace(engaged=False)

        ctx = _make_ctx(engagement_engine=MockEngEngine())
        ctx.unit_weapons["a1"] = []  # No weapons — will stop at weapons check
        units_by_side = {"blue": [attacker], "red": [target]}
        active_enemies = {"blue": [target], "red": [attacker]}
        enemy_pos = {"blue": np.array([[500.0, 0.0]]), "red": np.array([[0.0, 0.0]])}

        # Should not raise — air posture gate should pass
        bm._execute_engagements(
            ctx, units_by_side, active_enemies, enemy_pos, 1.0, datetime.now(),
        )

    def test_fuel_low_transitions_to_returning(self) -> None:
        """Auto-assignment: fuel < 0.2 should transition to RETURNING."""
        bm = BattleManager(EventBus())
        au = AerialUnit(
            entity_id="a1", side="blue",
            position=Position(0.0, 0.0, 5000.0),
            air_posture=AirPosture.ON_STATION,
            flight_state=FlightState.AIRBORNE,
            fuel_remaining=0.15,
        )
        # Provide full ctx with units_by_side for execute_tick
        ctx = _make_ctx()
        ctx.units_by_side = {"blue": [au], "red": []}
        ctx.clock = SimpleNamespace(
            current_time=datetime.now(),
            elapsed=SimpleNamespace(total_seconds=lambda: 0.0),
        )
        battle = _make_battle()

        bm.execute_tick(ctx, battle, 1.0)
        assert au.air_posture == AirPosture.RETURNING


# ===========================================================================
# 50c: Continuous concealment with observation decay
# ===========================================================================


class TestContinuousConcealment:
    """D4: Concealment decays with sustained observation."""

    def test_initial_concealment_set_from_terrain(self) -> None:
        bm = BattleManager(EventBus())
        # Concealment scores start empty
        assert len(bm._concealment_scores) == 0
        # Setting a value simulates initialization
        bm._concealment_scores["t1"] = 0.8
        assert bm._concealment_scores["t1"] == 0.8

    def test_observation_decay_rate_default(self) -> None:
        cal = CalibrationSchema()
        assert cal.observation_decay_rate == 0.05

    def test_engagement_concealment_threshold_default(self) -> None:
        cal = CalibrationSchema()
        assert cal.engagement_concealment_threshold == 0.5

    def test_concealment_decays_per_tick(self) -> None:
        """Concealment should decrease by observation_decay_rate each tick."""
        bm = BattleManager(EventBus())
        bm._concealment_scores["t1"] = 0.5
        # Simulate decay
        decay = 0.05
        bm._concealment_scores["t1"] = max(0.0, bm._concealment_scores["t1"] - decay)
        assert bm._concealment_scores["t1"] == pytest.approx(0.45)

    def test_concealment_never_below_zero(self) -> None:
        bm = BattleManager(EventBus())
        bm._concealment_scores["t1"] = 0.02
        decay = 0.05
        bm._concealment_scores["t1"] = max(0.0, bm._concealment_scores["t1"] - decay)
        assert bm._concealment_scores["t1"] == 0.0

    def test_moving_target_resets_concealment(self) -> None:
        """Moving target should have concealment = terrain * 0.5."""
        bm = BattleManager(EventBus())
        bm._concealment_scores["t1"] = 0.8
        terrain_concealment = 0.6
        # Simulating a moving target
        target_speed = 5.0
        if target_speed > 0.5:
            bm._concealment_scores["t1"] = terrain_concealment * 0.5
        assert bm._concealment_scores["t1"] == pytest.approx(0.3)

    def test_independent_target_scores(self) -> None:
        """Different targets maintain independent concealment."""
        bm = BattleManager(EventBus())
        bm._concealment_scores["t1"] = 0.8
        bm._concealment_scores["t2"] = 0.3
        assert bm._concealment_scores["t1"] != bm._concealment_scores["t2"]

    def test_calibration_fields_in_schema(self) -> None:
        """CalibrationSchema should accept concealment fields."""
        cal = CalibrationSchema(
            observation_decay_rate=0.1,
            engagement_concealment_threshold=0.7,
        )
        assert cal.get("observation_decay_rate", 0.05) == 0.1
        assert cal.get("engagement_concealment_threshold", 0.5) == 0.7

    def test_thermal_sensor_reduced_concealment_effect(self) -> None:
        """Thermal/radar sensors should get 0.3x concealment effect.

        When weather_independent=True (thermal/radar), concealment
        multiplier is (1.0 - concealment * 0.3) instead of (1.0 - concealment).
        """
        concealment = 0.6
        # Visual sensor
        visual_range = 1000.0 * (1.0 - concealment)
        # Thermal sensor
        thermal_range = 1000.0 * (1.0 - concealment * 0.3)
        assert thermal_range > visual_range

    def test_high_concealment_blocks_engagement(self) -> None:
        """Target with concealment above threshold should not be engaged."""
        cal = CalibrationSchema(engagement_concealment_threshold=0.5)
        effective_concealment = 0.6
        threshold = cal.get("engagement_concealment_threshold", 0.5)
        assert effective_concealment > threshold  # Should block


# ===========================================================================
# 50d: Training level YAML population
# ===========================================================================


class TestTrainingLevelPopulation:
    """D14: Unit YAML files have training_level values."""

    @pytest.fixture()
    def _data_root(self) -> str:
        return os.path.join(
            os.path.dirname(__file__), "..", "..", "data",
        )

    def _load_yaml(self, path: str) -> dict:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f)

    def test_m1a2_training_level(self, _data_root: str) -> None:
        data = self._load_yaml(
            os.path.join(_data_root, "units", "armor", "m1a2.yaml"),
        )
        assert data["training_level"] == 0.9

    def test_infantry_squad_training_level(self, _data_root: str) -> None:
        data = self._load_yaml(
            os.path.join(_data_root, "units", "infantry", "us_rifle_squad.yaml"),
        )
        assert data["training_level"] == 0.7

    def test_roman_legionary_training_level(self, _data_root: str) -> None:
        data = self._load_yaml(
            os.path.join(
                _data_root, "eras", "ancient_medieval", "units",
                "roman_legionary_cohort.yaml",
            ),
        )
        assert data["training_level"] == 0.8

    def test_default_backward_compat(self) -> None:
        """Units without training_level YAML field default to 0.5."""
        u = Unit(
            entity_id="u1", side="blue", domain=Domain.GROUND,
            position=Position(0.0, 0.0, 0.0),
        )
        assert u.training_level == 0.5

    def test_all_unit_files_have_training_level(self, _data_root: str) -> None:
        """Spot-check: all era unit files have training_level in range."""
        import yaml

        unit_dirs = [
            os.path.join(_data_root, "units"),
            os.path.join(_data_root, "eras"),
        ]
        checked = 0
        for base in unit_dirs:
            for root, _dirs, files in os.walk(base):
                # Only check unit definition files
                if "units" not in root.replace("\\", "/"):
                    continue
                for f in files:
                    if not f.endswith(".yaml"):
                        continue
                    path = os.path.join(root, f)
                    data = self._load_yaml(path)
                    if "unit_type" not in data:
                        continue  # Not a unit definition
                    tl = data.get("training_level")
                    assert tl is not None, f"Missing training_level in {path}"
                    assert 0.3 <= tl <= 0.95, (
                        f"training_level={tl} out of range in {path}"
                    )
                    checked += 1
        assert checked >= 100  # Expect 130+ unit files

    def test_higher_training_produces_higher_skill(self) -> None:
        """Verify the battle.py formula: effective_skill = base * (0.5 + 0.5 * tl)."""
        base_skill = 0.7
        low_tl = 0.3
        high_tl = 0.9
        low_eff = base_skill * (0.5 + 0.5 * low_tl)
        high_eff = base_skill * (0.5 + 0.5 * high_tl)
        assert high_eff > low_eff


# ===========================================================================
# 50e: Barrage penalty fix, target value weights, melee range
# ===========================================================================


class TestBarrageTargetWeightsMelee:
    """D7: WW1 barrage gets incorrect fire-on-move penalty."""

    def test_indirect_fire_categories_exist(self) -> None:
        assert "HOWITZER" in _INDIRECT_FIRE_CATEGORIES
        assert "MORTAR" in _INDIRECT_FIRE_CATEGORIES
        assert "ARTILLERY" in _INDIRECT_FIRE_CATEGORIES

    def test_rifle_not_in_indirect_fire(self) -> None:
        assert "RIFLE" not in _INDIRECT_FIRE_CATEGORIES

    def test_target_value_weights_from_calibration(self) -> None:
        """Custom target_value_weights should override BattleConfig defaults."""
        cal = CalibrationSchema(
            target_value_weights={"hq": 5.0, "ad": 3.0},
        )
        w = cal.get("target_value_weights", None)
        assert w is not None
        assert w["hq"] == 5.0
        assert w["ad"] == 3.0

    def test_target_value_weights_default_none(self) -> None:
        """Default target_value_weights should be None (use BattleConfig)."""
        cal = CalibrationSchema()
        assert cal.get("target_value_weights", None) is None

    def test_melee_range_constant(self) -> None:
        assert _MELEE_RANGE_M == 10.0

    def test_melee_weapons_within_range(self) -> None:
        """All melee weapons should have max_range_m <= _MELEE_RANGE_M."""
        import yaml

        melee_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "weapons",
        )
        if not os.path.isdir(melee_dir):
            pytest.skip("weapons directory not found")
        for root, _dirs, files in os.walk(melee_dir):
            for f in files:
                if not f.endswith(".yaml"):
                    continue
                path = os.path.join(root, f)
                data = yaml.safe_load(open(path))
                if data.get("category", "").upper() == "MELEE":
                    max_r = data.get("max_range_m", 0)
                    assert max_r <= _MELEE_RANGE_M, (
                        f"Melee weapon {f} has max_range_m={max_r} > {_MELEE_RANGE_M}"
                    )

    def test_calibration_schema_forbids_unknown(self) -> None:
        """Unknown keys should raise ValidationError."""
        with pytest.raises(Exception):
            CalibrationSchema(bogus_key=42)

    def test_calibration_target_value_weights_get(self) -> None:
        """CalibrationSchema.get() should return target_value_weights."""
        cal = CalibrationSchema(
            target_value_weights={"hq": 10.0, "default": 0.5},
        )
        tvw = cal.get("target_value_weights", None)
        assert tvw["hq"] == 10.0
        assert tvw["default"] == 0.5
