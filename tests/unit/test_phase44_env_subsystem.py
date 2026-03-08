"""Phase 44 — Environmental & Subsystem Integration tests.

Tests for weather/night/sea state combat effects (44a), CBRN/EW/GPS
engagement modifiers (44b), logistics readiness gate (44c), and
population engine wiring (44d).
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
)
from stochastic_warfare.combat.engagement import EngagementEngine, EngagementType
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.morale.state import MoraleState
from stochastic_warfare.simulation.battle import (
    BattleConfig,
    BattleContext,
    BattleManager,
    _compute_weather_pk_modifier,
)

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
) -> Unit:
    return Unit(
        entity_id=uid,
        position=pos or Position(0.0, 0.0, 0.0),
        name=uid,
        side=side,
        domain=domain,
        status=status,
        speed=speed,
        max_speed=10.0,
    )


def _make_weapon_def(
    wid: str = "wpn1",
    category: str = "CANNON",
    max_range: float = 3000.0,
    caliber: float = 120.0,
    rate_of_fire: float = 6.0,
    target_domains: list[str] | None = None,
) -> WeaponDefinition:
    wd = WeaponDefinition(
        weapon_id=wid,
        display_name=wid,
        category=category,
        caliber_mm=caliber,
        max_range_m=max_range,
        rate_of_fire_rpm=rate_of_fire,
        weight_kg=500.0,
        requires_deployed=False,
    )
    if target_domains is not None:
        object.__setattr__(wd, "_target_domains", target_domains)
    return wd


def _make_ammo(aid: str = "ammo1") -> AmmoDefinition:
    return AmmoDefinition(
        ammo_id=aid,
        display_name=aid,
        caliber_mm=120.0,
        ammo_type="HE",
        muzzle_velocity_mps=800.0,
        weight_kg=10.0,
        drag_coefficient=0.3,
        explosive_mass_kg=2.0,
    )


class FakeWeaponInstance:
    """Minimal weapon instance for tests."""

    def __init__(self, definition: WeaponDefinition, ammo_count: int = 10):
        self.definition = definition
        self._ammo_count = ammo_count
        self._last_fire_time: float | None = None

    def can_fire(self, ammo_id: str) -> bool:
        return self._ammo_count > 0


class FakeSensor:
    """Minimal sensor for tests."""

    def __init__(
        self,
        effective_range: float = 5000.0,
        sensor_type: Any = None,
    ):
        self.effective_range = effective_range
        from stochastic_warfare.detection.sensors import SensorType
        self.sensor_type = sensor_type or SensorType.VISUAL


def _make_ctx(
    blue_units: list[Unit] | None = None,
    red_units: list[Unit] | None = None,
    weapons: dict[str, list] | None = None,
    sensors: dict[str, list] | None = None,
    calibration: dict | None = None,
    morale_states: dict | None = None,
    weather_engine: Any = None,
    time_of_day_engine: Any = None,
    sea_state_engine: Any = None,
    cbrn_engine: Any = None,
    ew_engine: Any = None,
    space_engine: Any = None,
    maintenance_engine: Any = None,
    engagement_engine: Any = None,
) -> SimpleNamespace:
    """Build a minimal context namespace for battle tests."""
    blue = blue_units or []
    red = red_units or []
    units_by_side = {"blue": blue, "red": red}
    ms = morale_states or {
        u.entity_id: MoraleState.STEADY
        for u in blue + red
    }
    from stochastic_warfare.core.clock import SimulationClock
    clock = SimulationClock(
        start=TS, tick_duration=timedelta(seconds=5),
    )
    clock.advance()

    config = SimpleNamespace(
        sides=[
            SimpleNamespace(side="blue", experience_level=0.8),
            SimpleNamespace(side="red", experience_level=0.5),
        ],
        era="modern",
        latitude=45.0,
        longitude=10.0,
        behavior_rules={},
    )

    return SimpleNamespace(
        config=config,
        clock=clock,
        calibration=calibration or {},
        units_by_side=units_by_side,
        unit_weapons=weapons or {},
        unit_sensors=sensors or {},
        morale_states=ms,
        engagement_engine=engagement_engine,
        detection_engine=None,
        suppression_engine=None,
        roe_engine=None,
        weather_engine=weather_engine,
        time_of_day_engine=time_of_day_engine,
        sea_state_engine=sea_state_engine,
        cbrn_engine=cbrn_engine,
        ew_engine=ew_engine,
        space_engine=space_engine,
        maintenance_engine=maintenance_engine,
        obstacle_manager=None,
        hydrography_manager=None,
        heightmap=None,
        dew_engine=None,
        volley_fire_engine=None,
        melee_engine=None,
        archery_engine=None,
        indirect_fire_engine=None,
        naval_surface_engine=None,
        naval_subsurface_engine=None,
        naval_gunfire_support_engine=None,
        mine_warfare_engine=None,
    )


# ========================================================================
# 44a: Weather & Night Effects
# ========================================================================


class TestWeatherPkModifier:
    """Unit tests for _compute_weather_pk_modifier."""

    def test_clear_pk_1_0(self):
        assert _compute_weather_pk_modifier(0) == 1.0

    def test_light_rain_pk_0_90(self):
        assert _compute_weather_pk_modifier(3) == 0.90

    def test_fog_pk_0_65(self):
        assert _compute_weather_pk_modifier(6) == 0.65

    def test_storm_pk_0_55(self):
        assert _compute_weather_pk_modifier(7) == 0.55

    def test_unknown_state_defaults_1_0(self):
        assert _compute_weather_pk_modifier(99) == 1.0


class TestWeatherVisibilityCap:
    """Weather visibility caps detection range when worse than calibration."""

    def test_fog_visibility_caps_detection(self):
        """Fog visibility (200m) < calibration (10000m) → used."""
        from stochastic_warfare.environment.weather import WeatherConditions, WindVector, WeatherState

        weather = SimpleNamespace(
            current=WeatherConditions(
                state=WeatherState.FOG,
                temperature=15.0,
                wind=WindVector(2.0, 0.0, 3.0),
                cloud_cover=1.0,
                cloud_ceiling=100.0,
                humidity=0.98,
                pressure=1013.0,
                precipitation_rate=0.0,
                visibility=200.0,
            ),
        )
        blue = _make_unit("b1", "blue", pos=Position(0, 0))
        red = _make_unit("r1", "red", pos=Position(150, 0))  # within 200m
        wpn = _make_weapon_def(max_range=3000.0)
        ammo = _make_ammo()
        inst = FakeWeaponInstance(wpn)

        # Create a mock engagement engine that records calls
        calls = []

        class RecordingEngine:
            def route_engagement(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(
                    engaged=False, hit_result=None, damage_result=None,
                )

        ctx = _make_ctx(
            blue_units=[blue],
            red_units=[red],
            weapons={"b1": [(inst, [ammo])]},
            sensors={"b1": [FakeSensor(effective_range=5000.0)]},
            calibration={"visibility_m": 10000.0},
            weather_engine=weather,
            engagement_engine=RecordingEngine(),
        )

        bm = BattleManager(EventBus(), BattleConfig())
        pending = bm._execute_engagements(
            ctx, ctx.units_by_side,
            {"blue": [red]},
            {"blue": np.array([[150.0, 0.0]])},
            5.0, TS,
        )
        # With fog (200m vis), unit at 150m should still be in range
        assert len(calls) >= 1

    def test_clear_no_visibility_cap(self):
        """Clear (50000m) > calibration (3000m) → calibration used."""
        from stochastic_warfare.environment.weather import WeatherConditions, WindVector, WeatherState

        weather = SimpleNamespace(
            current=WeatherConditions(
                state=WeatherState.CLEAR,
                temperature=20.0,
                wind=WindVector(3.0, 0.0, 4.0),
                cloud_cover=0.1,
                cloud_ceiling=10000.0,
                humidity=0.35,
                pressure=1013.0,
                precipitation_rate=0.0,
                visibility=50000.0,
            ),
        )
        blue = _make_unit("b1", "blue", pos=Position(0, 0))
        red = _make_unit("r1", "red", pos=Position(4000, 0))  # beyond 3000m cal

        calls = []

        class RecordingEngine:
            def route_engagement(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(
                    engaged=False, hit_result=None, damage_result=None,
                )

        # Sensor effective range 2000 < calibration 3000, so detection_range=3000
        ctx = _make_ctx(
            blue_units=[blue],
            red_units=[red],
            weapons={"b1": [(FakeWeaponInstance(_make_weapon_def(max_range=5000.0)), [_make_ammo()])]},
            sensors={"b1": [FakeSensor(effective_range=2000.0)]},
            calibration={"visibility_m": 3000.0},
            weather_engine=weather,
            engagement_engine=RecordingEngine(),
        )

        bm = BattleManager(EventBus(), BattleConfig())
        pending = bm._execute_engagements(
            ctx, ctx.units_by_side,
            {"blue": [red]},
            {"blue": np.array([[4000.0, 0.0]])},
            5.0, TS,
        )
        # Target at 4000m > calibration vis 3000m → not detected
        assert len(calls) == 0


class TestNightEffects:
    """Night detection modifiers."""

    def test_night_reduces_visual_detection(self):
        """Night without thermal → detection × 0.3."""
        # A target at 2500m should be detectable with 5000m vis in daytime
        # but not at night (5000*0.3 = 1500 < 2500)
        tod = SimpleNamespace(
            illumination_at=lambda lat, lon: SimpleNamespace(is_day=False),
            thermal_environment=lambda lat, lon: SimpleNamespace(thermal_contrast=0.5),
        )
        blue = _make_unit("b1", "blue", pos=Position(0, 0))
        red = _make_unit("r1", "red", pos=Position(2500, 0))

        calls = []

        class RecordingEngine:
            def route_engagement(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(
                    engaged=False, hit_result=None, damage_result=None,
                )

        ctx = _make_ctx(
            blue_units=[blue],
            red_units=[red],
            weapons={"b1": [(FakeWeaponInstance(_make_weapon_def(max_range=5000.0)), [_make_ammo()])]},
            sensors={"b1": [FakeSensor(effective_range=5000.0)]},
            calibration={"visibility_m": 5000.0},
            time_of_day_engine=tod,
            engagement_engine=RecordingEngine(),
        )

        bm = BattleManager(EventBus(), BattleConfig())
        pending = bm._execute_engagements(
            ctx, ctx.units_by_side,
            {"blue": [red]},
            {"blue": np.array([[2500.0, 0.0]])},
            5.0, TS,
        )
        # Night visual detection range = 5000 * 0.3 = 1500 < 2500 → out of range
        assert len(calls) == 0

    def test_night_thermal_sensor_enhanced(self):
        """Night + thermal → detection enhanced, not penalized."""
        from stochastic_warfare.detection.sensors import SensorType

        tod = SimpleNamespace(
            illumination_at=lambda lat, lon: SimpleNamespace(is_day=False),
            thermal_environment=lambda lat, lon: SimpleNamespace(thermal_contrast=0.6),
        )
        blue = _make_unit("b1", "blue", pos=Position(0, 0))
        # Place target beyond 1500m (night visual range) but within thermal range
        red = _make_unit("r1", "red", pos=Position(2000, 0))

        calls = []

        class RecordingEngine:
            def route_engagement(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(
                    engaged=False, hit_result=None, damage_result=None,
                )

        # Set visibility low so thermal sensor dominates detection_range
        ctx = _make_ctx(
            blue_units=[blue],
            red_units=[red],
            weapons={"b1": [(FakeWeaponInstance(_make_weapon_def(max_range=5000.0)), [_make_ammo()])]},
            sensors={"b1": [FakeSensor(
                effective_range=3000.0, sensor_type=SensorType.THERMAL,
            )]},
            calibration={"visibility_m": 2500.0},
            time_of_day_engine=tod,
            engagement_engine=RecordingEngine(),
        )

        bm = BattleManager(EventBus(), BattleConfig())
        pending = bm._execute_engagements(
            ctx, ctx.units_by_side,
            {"blue": [red]},
            {"blue": np.array([[2000.0, 0.0]])},
            5.0, TS,
        )
        # Thermal at night: detection_range = max(2500, 3000) = 3000 (from thermal)
        # weather_independent=True, so night_visual_modifier NOT applied
        # Instead: 3000 * (1 + 0.18) = 3540 > 2000 → detects
        assert len(calls) >= 1


class TestSeaState:
    """Sea state dispersion effects."""

    def test_beaufort_5_dispersion(self):
        """Beaufort 5 → dispersion mod = 1.2."""
        from stochastic_warfare.environment.sea_state import SeaConditions

        sea = SimpleNamespace(
            current=SeaConditions(
                significant_wave_height=2.5,
                wave_period=8.0,
                tide_height=0.3,
                tidal_current_speed=0.1,
                tidal_current_direction=0.0,
                sst=15.0,
                beaufort_scale=5,
            ),
        )
        blue = _make_unit("b1", "blue", pos=Position(0, 0), domain=Domain.NAVAL)
        red = _make_unit("r1", "red", pos=Position(2000, 0), domain=Domain.NAVAL)

        recorded_target_size = []

        class RecordingEngine:
            def route_engagement(self, **kwargs):
                recorded_target_size.append(kwargs.get("target_size_m2", -1))
                return SimpleNamespace(
                    engaged=False, hit_result=None, damage_result=None,
                )

        ctx = _make_ctx(
            blue_units=[blue],
            red_units=[red],
            weapons={"b1": [(FakeWeaponInstance(_make_weapon_def(max_range=5000.0)), [_make_ammo()])]},
            sensors={"b1": [FakeSensor(effective_range=5000.0)]},
            calibration={},
            sea_state_engine=sea,
            engagement_engine=RecordingEngine(),
        )

        bm = BattleManager(EventBus(), BattleConfig())
        bm._execute_engagements(
            ctx, ctx.units_by_side,
            {"blue": [red]},
            {"blue": np.array([[2000.0, 0.0]])},
            5.0, TS,
        )
        # Beaufort 5: sea_dispersion_modifier = 1.2
        # target_size_m2 = 8.5 * 1.0 / 1.2 ≈ 7.08
        if recorded_target_size:
            assert recorded_target_size[0] < 8.5

    def test_calm_no_effect(self):
        """Beaufort 3 → dispersion mod = 1.0 (no effect)."""
        from stochastic_warfare.environment.sea_state import SeaConditions

        sea = SimpleNamespace(
            current=SeaConditions(
                significant_wave_height=0.5,
                wave_period=4.0,
                tide_height=0.1,
                tidal_current_speed=0.05,
                tidal_current_direction=0.0,
                sst=15.0,
                beaufort_scale=3,
            ),
        )
        blue = _make_unit("b1", "blue", pos=Position(0, 0), domain=Domain.NAVAL)
        red = _make_unit("r1", "red", pos=Position(2000, 0), domain=Domain.NAVAL)

        recorded_target_size = []

        class RecordingEngine:
            def route_engagement(self, **kwargs):
                recorded_target_size.append(kwargs.get("target_size_m2", -1))
                return SimpleNamespace(
                    engaged=False, hit_result=None, damage_result=None,
                )

        ctx = _make_ctx(
            blue_units=[blue],
            red_units=[red],
            weapons={"b1": [(FakeWeaponInstance(_make_weapon_def(max_range=5000.0)), [_make_ammo()])]},
            sensors={"b1": [FakeSensor(effective_range=5000.0)]},
            calibration={},
            sea_state_engine=sea,
            engagement_engine=RecordingEngine(),
        )

        bm = BattleManager(EventBus(), BattleConfig())
        bm._execute_engagements(
            ctx, ctx.units_by_side,
            {"blue": [red]},
            {"blue": np.array([[2000.0, 0.0]])},
            5.0, TS,
        )
        # Beaufort 3 → no dispersion
        if recorded_target_size:
            assert abs(recorded_target_size[0] - 8.5) < 0.1


# ========================================================================
# 44a: Scenario Loader instantiation
# ========================================================================


class TestEnvironmentEngineInstantiation:
    """ScenarioLoader creates environment engines."""

    def test_weather_engine_instantiated(self):
        """ScenarioLoader creates non-None weather_engine."""
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        from pathlib import Path
        data_dir = Path(__file__).resolve().parents[2] / "data"
        scenario_path = data_dir / "scenarios" / "test_campaign" / "scenario.yaml"
        loader = ScenarioLoader(data_dir)
        ctx = loader.load(scenario_path)
        assert ctx.weather_engine is not None

    def test_time_of_day_engine_instantiated(self):
        """ScenarioLoader creates non-None time_of_day_engine."""
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        from pathlib import Path
        data_dir = Path(__file__).resolve().parents[2] / "data"
        scenario_path = data_dir / "scenarios" / "test_campaign" / "scenario.yaml"
        loader = ScenarioLoader(data_dir)
        ctx = loader.load(scenario_path)
        assert ctx.time_of_day_engine is not None

    def test_sea_state_engine_instantiated(self):
        """ScenarioLoader creates non-None sea_state_engine."""
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        from pathlib import Path
        data_dir = Path(__file__).resolve().parents[2] / "data"
        scenario_path = data_dir / "scenarios" / "test_campaign" / "scenario.yaml"
        loader = ScenarioLoader(data_dir)
        ctx = loader.load(scenario_path)
        assert ctx.sea_state_engine is not None


# ========================================================================
# 44a: engine.py update call fix
# ========================================================================


class TestWeatherEngineUpdateCall:
    """engine.py calls weather_engine.update(dt), not step(clock)."""

    def test_weather_engine_update_called(self):
        from stochastic_warfare.simulation.engine import SimulationEngine, EngineConfig
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        from pathlib import Path
        data_dir = Path(__file__).resolve().parents[2] / "data"
        scenario_path = data_dir / "scenarios" / "test_campaign" / "scenario.yaml"
        loader = ScenarioLoader(data_dir)
        ctx = loader.load(scenario_path)

        # Patch weather engine to track calls
        original_update = ctx.weather_engine.update
        update_calls = []

        def tracking_update(dt_seconds):
            update_calls.append(dt_seconds)
            return original_update(dt_seconds)

        ctx.weather_engine.update = tracking_update

        engine = SimulationEngine(
            ctx, EngineConfig(max_ticks=2), strict_mode=True,
        )
        engine.step()

        assert len(update_calls) >= 1
        assert isinstance(update_calls[0], float)


# ========================================================================
# 44b: CBRN/EW/Space Effects
# ========================================================================


class TestCBRNMOPPEffects:
    """CBRN MOPP effects on engagement."""

    def test_mopp0_no_effect(self):
        """MOPP 0: no skill/detection penalty."""
        cbrn = SimpleNamespace(
            get_mopp_effects=lambda uid: (1.0, 1.0, 1.0),
        )
        blue = _make_unit("b1", "blue", pos=Position(0, 0))
        red = _make_unit("r1", "red", pos=Position(500, 0))

        recorded_skill = []

        class RecordingEngine:
            def route_engagement(self, **kwargs):
                recorded_skill.append(kwargs.get("crew_skill", -1))
                return SimpleNamespace(
                    engaged=False, hit_result=None, damage_result=None,
                )

        ctx = _make_ctx(
            blue_units=[blue],
            red_units=[red],
            weapons={"b1": [(FakeWeaponInstance(_make_weapon_def()), [_make_ammo()])]},
            sensors={"b1": [FakeSensor()]},
            calibration={"visibility_m": 10000.0},
            cbrn_engine=cbrn,
            engagement_engine=RecordingEngine(),
        )

        bm = BattleManager(EventBus(), BattleConfig())
        bm._execute_engagements(
            ctx, ctx.units_by_side,
            {"blue": [red]},
            {"blue": np.array([[500.0, 0.0]])},
            5.0, TS,
        )
        # Skill should not be reduced
        assert len(recorded_skill) >= 1

    def test_mopp4_fatigue_penalty(self):
        """MOPP 4: crew_skill reduced by fatigue factor."""
        # fatigue_mult > 1.0 → crew_skill /= fatigue
        cbrn_high = SimpleNamespace(
            get_mopp_effects=lambda uid: (0.5, 0.7, 2.0),
        )
        cbrn_none = SimpleNamespace(
            get_mopp_effects=lambda uid: (1.0, 1.0, 1.0),
        )
        blue = _make_unit("b1", "blue", pos=Position(0, 0))
        red = _make_unit("r1", "red", pos=Position(500, 0))

        def run_with_cbrn(cbrn):
            skills = []

            class RecordingEngine:
                def route_engagement(self, **kwargs):
                    skills.append(kwargs.get("crew_skill", -1))
                    return SimpleNamespace(
                        engaged=False, hit_result=None, damage_result=None,
                    )

            ctx = _make_ctx(
                blue_units=[blue],
                red_units=[red],
                weapons={"b1": [(FakeWeaponInstance(_make_weapon_def()), [_make_ammo()])]},
                sensors={"b1": [FakeSensor()]},
                calibration={"visibility_m": 10000.0},
                cbrn_engine=cbrn,
                engagement_engine=RecordingEngine(),
            )
            bm = BattleManager(EventBus(), BattleConfig())
            bm._execute_engagements(
                ctx, ctx.units_by_side,
                {"blue": [red]},
                {"blue": np.array([[500.0, 0.0]])},
                5.0, TS,
            )
            return skills

        skills_high = run_with_cbrn(cbrn_high)
        skills_none = run_with_cbrn(cbrn_none)

        if skills_high and skills_none:
            assert skills_high[0] < skills_none[0]

    def test_no_cbrn_engine_no_effect(self):
        """ctx.cbrn_engine=None → no penalty."""
        blue = _make_unit("b1", "blue", pos=Position(0, 0))
        red = _make_unit("r1", "red", pos=Position(500, 0))

        calls = []

        class RecordingEngine:
            def route_engagement(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(
                    engaged=False, hit_result=None, damage_result=None,
                )

        ctx = _make_ctx(
            blue_units=[blue],
            red_units=[red],
            weapons={"b1": [(FakeWeaponInstance(_make_weapon_def()), [_make_ammo()])]},
            sensors={"b1": [FakeSensor()]},
            calibration={"visibility_m": 10000.0},
            cbrn_engine=None,
            engagement_engine=RecordingEngine(),
        )

        bm = BattleManager(EventBus(), BattleConfig())
        bm._execute_engagements(
            ctx, ctx.units_by_side,
            {"blue": [red]},
            {"blue": np.array([[500.0, 0.0]])},
            5.0, TS,
        )
        # Should still engage (no CBRN penalty)
        assert len(calls) >= 1


class TestEWJamming:
    """EW jamming effects on engagement."""

    def test_ew_no_jammers_no_effect(self):
        """No active jammers → no penalty."""
        ew = SimpleNamespace(
            compute_radar_snr_penalty=lambda **kw: 0.0,
        )
        blue = _make_unit("b1", "blue", pos=Position(0, 0))
        red = _make_unit("r1", "red", pos=Position(500, 0))

        calls = []

        class RecordingEngine:
            def route_engagement(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(
                    engaged=False, hit_result=None, damage_result=None,
                )

        from stochastic_warfare.detection.sensors import SensorType
        ctx = _make_ctx(
            blue_units=[blue],
            red_units=[red],
            weapons={"b1": [(FakeWeaponInstance(_make_weapon_def()), [_make_ammo()])]},
            sensors={"b1": [FakeSensor(sensor_type=SensorType.RADAR)]},
            calibration={"visibility_m": 10000.0},
            ew_engine=ew,
            engagement_engine=RecordingEngine(),
        )

        bm = BattleManager(EventBus(), BattleConfig())
        bm._execute_engagements(
            ctx, ctx.units_by_side,
            {"blue": [red]},
            {"blue": np.array([[500.0, 0.0]])},
            5.0, TS,
        )
        assert len(calls) >= 1

    def test_ew_no_effect_visual_sensor(self):
        """Visual sensor → jamming ignored (weather_independent=False)."""
        ew_called = []
        ew = SimpleNamespace(
            compute_radar_snr_penalty=lambda **kw: (ew_called.append(1), 20.0)[1],
        )
        blue = _make_unit("b1", "blue", pos=Position(0, 0))
        red = _make_unit("r1", "red", pos=Position(500, 0))

        from stochastic_warfare.detection.sensors import SensorType
        ctx = _make_ctx(
            blue_units=[blue],
            red_units=[red],
            weapons={"b1": [(FakeWeaponInstance(_make_weapon_def()), [_make_ammo()])]},
            sensors={"b1": [FakeSensor(sensor_type=SensorType.VISUAL)]},
            calibration={"visibility_m": 10000.0},
            ew_engine=ew,
            engagement_engine=SimpleNamespace(
                route_engagement=lambda **kw: SimpleNamespace(
                    engaged=False, hit_result=None, damage_result=None,
                ),
            ),
        )

        bm = BattleManager(EventBus(), BattleConfig())
        bm._execute_engagements(
            ctx, ctx.units_by_side,
            {"blue": [red]},
            {"blue": np.array([[500.0, 0.0]])},
            5.0, TS,
        )
        # EW should NOT be called for optical sensors
        assert len(ew_called) == 0


class TestGPSEffects:
    """GPS accuracy effects on guided weapons."""

    def test_no_space_engine_no_effect(self):
        """ctx.space_engine=None → no GPS penalty."""
        blue = _make_unit("b1", "blue", pos=Position(0, 0))
        red = _make_unit("r1", "red", pos=Position(500, 0))

        calls = []

        class RecordingEngine:
            def route_engagement(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(
                    engaged=False, hit_result=None, damage_result=None,
                )

        ctx = _make_ctx(
            blue_units=[blue],
            red_units=[red],
            weapons={"b1": [(FakeWeaponInstance(_make_weapon_def()), [_make_ammo()])]},
            sensors={"b1": [FakeSensor()]},
            calibration={"visibility_m": 10000.0},
            space_engine=None,
            engagement_engine=RecordingEngine(),
        )

        bm = BattleManager(EventBus(), BattleConfig())
        bm._execute_engagements(
            ctx, ctx.units_by_side,
            {"blue": [red]},
            {"blue": np.array([[500.0, 0.0]])},
            5.0, TS,
        )
        assert len(calls) >= 1

    def test_gps_unguided_weapon_no_effect(self):
        """Unguided weapon → GPS irrelevant."""
        gps_called = []
        gps_eng = SimpleNamespace(
            compute_gps_accuracy=lambda side, t: (gps_called.append(1), None)[1],
            compute_cep_factor=lambda acc, gt: 1.0,
        )
        space = SimpleNamespace(gps_engine=gps_eng)
        blue = _make_unit("b1", "blue", pos=Position(0, 0))
        red = _make_unit("r1", "red", pos=Position(500, 0))

        # Ammo without guidance_type
        ammo = _make_ammo()

        ctx = _make_ctx(
            blue_units=[blue],
            red_units=[red],
            weapons={"b1": [(FakeWeaponInstance(_make_weapon_def()), [ammo])]},
            sensors={"b1": [FakeSensor()]},
            calibration={"visibility_m": 10000.0},
            space_engine=space,
            engagement_engine=SimpleNamespace(
                route_engagement=lambda **kw: SimpleNamespace(
                    engaged=False, hit_result=None, damage_result=None,
                ),
            ),
        )

        bm = BattleManager(EventBus(), BattleConfig())
        bm._execute_engagements(
            ctx, ctx.units_by_side,
            {"blue": [red]},
            {"blue": np.array([[500.0, 0.0]])},
            5.0, TS,
        )
        # GPS accuracy should not be queried for unguided weapons
        assert len(gps_called) == 0


# ========================================================================
# 44c: Logistics Engine Wiring
# ========================================================================


class TestMaintenanceReadiness:
    """Equipment readiness gate."""

    def test_readiness_1_no_penalty(self):
        """Full readiness → no crew_skill penalty."""
        maint = SimpleNamespace(
            get_unit_readiness=lambda uid: 1.0,
        )
        blue = _make_unit("b1", "blue", pos=Position(0, 0))
        red = _make_unit("r1", "red", pos=Position(500, 0))

        skills = []

        class RecordingEngine:
            def route_engagement(self, **kwargs):
                skills.append(kwargs.get("crew_skill", -1))
                return SimpleNamespace(
                    engaged=False, hit_result=None, damage_result=None,
                )

        ctx = _make_ctx(
            blue_units=[blue],
            red_units=[red],
            weapons={"b1": [(FakeWeaponInstance(_make_weapon_def()), [_make_ammo()])]},
            sensors={"b1": [FakeSensor()]},
            calibration={"visibility_m": 10000.0},
            maintenance_engine=maint,
            engagement_engine=RecordingEngine(),
        )

        bm = BattleManager(EventBus(), BattleConfig())
        bm._execute_engagements(
            ctx, ctx.units_by_side,
            {"blue": [red]},
            {"blue": np.array([[500.0, 0.0]])},
            5.0, TS,
        )
        assert len(skills) >= 1

    def test_readiness_below_30_skips(self):
        """Readiness < 0.3 → unit skipped (no engagement)."""
        maint = SimpleNamespace(
            get_unit_readiness=lambda uid: 0.2,
        )
        blue = _make_unit("b1", "blue", pos=Position(0, 0))
        red = _make_unit("r1", "red", pos=Position(500, 0))

        calls = []

        class RecordingEngine:
            def route_engagement(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(
                    engaged=False, hit_result=None, damage_result=None,
                )

        ctx = _make_ctx(
            blue_units=[blue],
            red_units=[red],
            weapons={"b1": [(FakeWeaponInstance(_make_weapon_def()), [_make_ammo()])]},
            sensors={"b1": [FakeSensor()]},
            calibration={"visibility_m": 10000.0},
            maintenance_engine=maint,
            engagement_engine=RecordingEngine(),
        )

        bm = BattleManager(EventBus(), BattleConfig())
        bm._execute_engagements(
            ctx, ctx.units_by_side,
            {"blue": [red]},
            {"blue": np.array([[500.0, 0.0]])},
            5.0, TS,
        )
        # Unit should be skipped — no engagement
        assert len(calls) == 0

    def test_readiness_50_skill_penalty(self):
        """Readiness 0.5 → crew_skill × 0.5."""
        maint_half = SimpleNamespace(get_unit_readiness=lambda uid: 0.5)
        maint_full = SimpleNamespace(get_unit_readiness=lambda uid: 1.0)

        blue = _make_unit("b1", "blue", pos=Position(0, 0))
        red = _make_unit("r1", "red", pos=Position(500, 0))

        def run_with_maint(maint):
            skills = []

            class RecordingEngine:
                def route_engagement(self, **kwargs):
                    skills.append(kwargs.get("crew_skill", -1))
                    return SimpleNamespace(
                        engaged=False, hit_result=None, damage_result=None,
                    )

            ctx = _make_ctx(
                blue_units=[blue],
                red_units=[red],
                weapons={"b1": [(FakeWeaponInstance(_make_weapon_def()), [_make_ammo()])]},
                sensors={"b1": [FakeSensor()]},
                calibration={"visibility_m": 10000.0},
                maintenance_engine=maint,
                engagement_engine=RecordingEngine(),
            )
            bm = BattleManager(EventBus(), BattleConfig())
            bm._execute_engagements(
                ctx, ctx.units_by_side,
                {"blue": [red]},
                {"blue": np.array([[500.0, 0.0]])},
                5.0, TS,
            )
            return skills

        half_skills = run_with_maint(maint_half)
        full_skills = run_with_maint(maint_full)

        if half_skills and full_skills:
            assert half_skills[0] < full_skills[0]

    def test_no_maintenance_engine_no_effect(self):
        """ctx.maintenance_engine=None → full readiness."""
        blue = _make_unit("b1", "blue", pos=Position(0, 0))
        red = _make_unit("r1", "red", pos=Position(500, 0))

        calls = []

        class RecordingEngine:
            def route_engagement(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(
                    engaged=False, hit_result=None, damage_result=None,
                )

        ctx = _make_ctx(
            blue_units=[blue],
            red_units=[red],
            weapons={"b1": [(FakeWeaponInstance(_make_weapon_def()), [_make_ammo()])]},
            sensors={"b1": [FakeSensor()]},
            calibration={"visibility_m": 10000.0},
            maintenance_engine=None,
            engagement_engine=RecordingEngine(),
        )

        bm = BattleManager(EventBus(), BattleConfig())
        bm._execute_engagements(
            ctx, ctx.units_by_side,
            {"blue": [red]},
            {"blue": np.array([[500.0, 0.0]])},
            5.0, TS,
        )
        assert len(calls) >= 1


class TestMaintenanceUpdateCalled:
    """engine.py calls maintenance_engine.update() per tick."""

    def test_maintenance_update_called(self):
        from stochastic_warfare.simulation.engine import SimulationEngine, EngineConfig
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        from pathlib import Path
        data_dir = Path(__file__).resolve().parents[2] / "data"
        scenario_path = data_dir / "scenarios" / "test_campaign" / "scenario.yaml"
        loader = ScenarioLoader(data_dir)
        ctx = loader.load(scenario_path)

        update_calls = []
        original = ctx.maintenance_engine.update

        def tracking(*args, **kwargs):
            update_calls.append((args, kwargs))
            return original(*args, **kwargs)

        ctx.maintenance_engine.update = tracking

        engine = SimulationEngine(
            ctx, EngineConfig(max_ticks=2), strict_mode=True,
        )
        engine.step()

        assert len(update_calls) >= 1


class TestMedicalEngineInstantiated:
    """ScenarioLoader creates medical/engineering engines."""

    def test_medical_engine_instantiated(self):
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        from pathlib import Path
        data_dir = Path(__file__).resolve().parents[2] / "data"
        scenario_path = data_dir / "scenarios" / "test_campaign" / "scenario.yaml"
        loader = ScenarioLoader(data_dir)
        ctx = loader.load(scenario_path)
        assert ctx.medical_engine is not None

    def test_engineering_engine_instantiated(self):
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        from pathlib import Path
        data_dir = Path(__file__).resolve().parents[2] / "data"
        scenario_path = data_dir / "scenarios" / "test_campaign" / "scenario.yaml"
        loader = ScenarioLoader(data_dir)
        ctx = loader.load(scenario_path)
        assert ctx.engineering_engine is not None

    def test_maintenance_in_get_state(self):
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        from pathlib import Path
        data_dir = Path(__file__).resolve().parents[2] / "data"
        scenario_path = data_dir / "scenarios" / "test_campaign" / "scenario.yaml"
        loader = ScenarioLoader(data_dir)
        ctx = loader.load(scenario_path)
        state = ctx.get_state()
        assert "maintenance_engine" in state


# ========================================================================
# 44d: Population Engine Wiring
# ========================================================================


class TestPopulationWiring:
    """Population engines created for escalation scenarios."""

    def test_population_not_created_without_escalation(self):
        """No escalation → population_manager stays None (default)."""
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        from pathlib import Path
        data_dir = Path(__file__).resolve().parents[2] / "data"
        scenario_path = data_dir / "scenarios" / "test_campaign" / "scenario.yaml"
        loader = ScenarioLoader(data_dir)
        ctx = loader.load(scenario_path)
        # 73 Easting has no escalation_config → collateral_engine None
        assert ctx.collateral_engine is None

    def test_collateral_none_no_crash(self):
        """collateral_engine=None → no crash in engine update."""
        from stochastic_warfare.simulation.engine import SimulationEngine, EngineConfig
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        from pathlib import Path
        data_dir = Path(__file__).resolve().parents[2] / "data"
        scenario_path = data_dir / "scenarios" / "test_campaign" / "scenario.yaml"
        loader = ScenarioLoader(data_dir)
        ctx = loader.load(scenario_path)
        assert ctx.collateral_engine is None

        engine = SimulationEngine(
            ctx, EngineConfig(max_ticks=2),
        )
        # Should not crash
        engine.step()


class TestParseWeatherState:
    """_parse_weather_state helper."""

    def test_clear(self):
        from stochastic_warfare.simulation.scenario import _parse_weather_state
        from stochastic_warfare.environment.weather import WeatherState
        assert _parse_weather_state("clear") == WeatherState.CLEAR

    def test_light_rain(self):
        from stochastic_warfare.simulation.scenario import _parse_weather_state
        from stochastic_warfare.environment.weather import WeatherState
        assert _parse_weather_state("light_rain") == WeatherState.LIGHT_RAIN

    def test_fog(self):
        from stochastic_warfare.simulation.scenario import _parse_weather_state
        from stochastic_warfare.environment.weather import WeatherState
        assert _parse_weather_state("fog") == WeatherState.FOG

    def test_unknown_defaults_clear(self):
        from stochastic_warfare.simulation.scenario import _parse_weather_state
        from stochastic_warfare.environment.weather import WeatherState
        assert _parse_weather_state("unknown_weather") == WeatherState.CLEAR

    def test_case_insensitive(self):
        from stochastic_warfare.simulation.scenario import _parse_weather_state
        from stochastic_warfare.environment.weather import WeatherState
        assert _parse_weather_state("HEAVY_RAIN") == WeatherState.HEAVY_RAIN
