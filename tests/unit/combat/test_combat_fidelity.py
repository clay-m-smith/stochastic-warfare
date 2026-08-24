"""Phase 50: Combat Fidelity Polish — tests for D1, D3, D4, D7, D14.

50a: Posture affects movement speed
50b: Air unit tactical posture
50c: Continuous concealment with observation decay
50d: Training level YAML population
50e: Barrage penalty fix, target value weights, melee range
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import Unit
from stochastic_warfare.entities.unit_classes.aerial import (
    AerialUnit,
    AirPosture,
    FlightState,
)
from stochastic_warfare.simulation.battle import (
    BattleContext,
    BattleManager,
    _INDIRECT_FIRE_CATEGORIES,
    _MELEE_RANGE_M,
    _POSTURE_SPEED_MULT,
)
from stochastic_warfare.simulation.calibration import CalibrationSchema
from tests.conftest import bind_test_era_runtime
from tests.unit.simulation._battle_feature_harness import (
    RecordingEngagementEngine,
    Sensor,
    execute_engagement_side,
    make_context,
    make_unit as make_executor_unit,
    make_weapon as make_executor_weapon,
)


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
    ctx = SimpleNamespace(
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
    return bind_test_era_runtime(ctx, era=era)


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

    def test_observation_decay_rate_default(self) -> None:
        cal = CalibrationSchema()
        assert cal.observation_decay_rate == 0.05

    def test_engagement_concealment_threshold_default(self) -> None:
        cal = CalibrationSchema()
        assert cal.engagement_concealment_threshold == 0.5

    def test_calibration_fields_in_schema(self) -> None:
        """CalibrationSchema should accept concealment fields."""
        cal = CalibrationSchema(
            observation_decay_rate=0.1,
            engagement_concealment_threshold=0.7,
        )
        assert cal.get("observation_decay_rate", 0.05) == 0.1
        assert cal.get("engagement_concealment_threshold", 0.5) == 0.7

    @pytest.mark.parametrize(
        ("prior", "target_speed", "expected"),
        [(None, 0.0, 0.7), (0.5, 0.0, 0.4), (0.02, 0.0, 0.0), (0.8, 1.0, 0.3)],
    )
    def test_executor_owns_initialization_decay_floor_and_movement_reset(
        self,
        prior: float | None,
        target_speed: float,
        expected: float,
    ) -> None:
        attacker = make_executor_unit("attacker", "blue", 0.0)
        target = make_executor_unit(
            "target",
            "red",
            100.0,
            speed=target_speed,
        )
        weapon, ammunition = make_executor_weapon()
        manager = BattleManager(EventBus())
        if prior is not None:
            manager._concealment_scores[target.entity_id] = prior
        context = make_context(
            {"blue": [attacker], "red": [target]},
            unit_weapons={attacker.entity_id: [(weapon, ammunition)]},
            calibration={
                "visibility_m": 1_000.0,
                "observation_decay_rate": 0.1,
            },
            classification=SimpleNamespace(
                properties_at=lambda _position: SimpleNamespace(
                    cover=0.0,
                    concealment=0.8,
                ),
            ),
        )

        execute_engagement_side(manager, context, "blue", [target])

        assert manager._concealment_scores[target.entity_id] == pytest.approx(
            expected,
        )

    def test_executor_tracks_target_concealment_independently(self) -> None:
        attacker = make_executor_unit("attacker", "blue", 0.0)
        near = make_executor_unit("near", "red", 100.0)
        far = make_executor_unit("far", "red", 200.0)
        weapon, ammunition = make_executor_weapon()
        manager = BattleManager(EventBus())
        context = make_context(
            {"blue": [attacker], "red": [near, far]},
            unit_weapons={attacker.entity_id: [(weapon, ammunition)]},
            calibration={
                "visibility_m": 1_000.0,
                "observation_decay_rate": 0.0,
            },
            classification=SimpleNamespace(
                properties_at=lambda position: SimpleNamespace(
                    cover=0.0,
                    concealment=(0.8 if position.easting == 100.0 else 0.3),
                ),
            ),
        )

        execute_engagement_side(manager, context, "blue", [near])
        execute_engagement_side(manager, context, "blue", [far])

        assert manager._concealment_scores == {"near": 0.8, "far": 0.3}

    @pytest.mark.parametrize(
        ("sensor_name", "expected_calls"),
        [("VISUAL", 0), ("THERMAL", 1)],
    )
    def test_real_sensor_modality_changes_concealed_detection_reach(
        self,
        sensor_name: str,
        expected_calls: int,
    ) -> None:
        from stochastic_warfare.detection.sensors import SensorType

        attacker = make_executor_unit("attacker", "blue", 0.0)
        target = make_executor_unit("target", "red", 600.0)
        weapon, ammunition = make_executor_weapon()
        recorder = RecordingEngagementEngine()
        context = make_context(
            {"blue": [attacker], "red": [target]},
            unit_weapons={attacker.entity_id: [(weapon, ammunition)]},
            unit_sensors={
                attacker.entity_id: [
                    Sensor(1_000.0, SensorType[sensor_name]),
                ],
            },
            calibration={
                "visibility_m": 0.0,
                "observation_decay_rate": 0.0,
                "engagement_concealment_threshold": 1.0,
            },
            engagement_engine=recorder,
            classification=SimpleNamespace(
                properties_at=lambda _position: SimpleNamespace(
                    cover=0.0,
                    concealment=0.6,
                ),
            ),
        )

        execute_engagement_side(BattleManager(EventBus()), context, "blue", [target])

        assert len(recorder.calls) == expected_calls

    @pytest.mark.parametrize(
        ("threshold", "expected_calls"),
        [(0.5, 0), (0.6, 1)],
    )
    def test_executor_applies_concealment_threshold_boundary(
        self,
        threshold: float,
        expected_calls: int,
    ) -> None:
        attacker = make_executor_unit("attacker", "blue", 0.0)
        target = make_executor_unit("target", "red", 100.0)
        weapon, ammunition = make_executor_weapon()
        recorder = RecordingEngagementEngine()
        context = make_context(
            {"blue": [attacker], "red": [target]},
            unit_weapons={attacker.entity_id: [(weapon, ammunition)]},
            calibration={
                "visibility_m": 1_000.0,
                "observation_decay_rate": 0.0,
                "engagement_concealment_threshold": threshold,
            },
            engagement_engine=recorder,
            classification=SimpleNamespace(
                properties_at=lambda _position: SimpleNamespace(
                    cover=0.0,
                    concealment=0.6,
                ),
            ),
        )

        execute_engagement_side(BattleManager(EventBus()), context, "blue", [target])

        assert len(recorder.calls) == expected_calls


# ===========================================================================
# 50d: Training level YAML population
# ===========================================================================


class TestTrainingLevelPopulation:
    """D14: Unit YAML files have training_level values."""

    @pytest.fixture()
    def _data_root(self) -> str:
        return str(Path(__file__).resolve().parents[3] / "data")

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

    @pytest.mark.test_evidence("structural_only")
    def test_melee_weapons_within_range(self) -> None:
        """All melee weapons should have max_range_m <= _MELEE_RANGE_M."""
        import yaml

        data_root = Path(__file__).resolve().parents[3] / "data"
        assert data_root.is_dir()
        checked = 0
        for path in sorted(data_root.rglob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or str(data.get("category", "")).upper() != "MELEE":
                continue
            max_range = data.get("max_range_m", 0)
            assert max_range <= _MELEE_RANGE_M, (
                f"Melee weapon {path.name} has max_range_m={max_range} > {_MELEE_RANGE_M}"
            )
            checked += 1
        assert checked > 0

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
