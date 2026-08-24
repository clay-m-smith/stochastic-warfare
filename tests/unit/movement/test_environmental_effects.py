"""Production movement proofs for environmental speed and dust effects."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from tests.conftest import make_clock

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import Unit
from stochastic_warfare.environment.obscurants import ObscurantType, ObscurantsEngine
from stochastic_warfare.environment.seasons import (
    GroundState,
    SeasonalConditions,
)
from stochastic_warfare.simulation.battle import BattleContext, BattleManager


def _unit(
    entity_id: str,
    *,
    side: str,
    domain: Domain,
    speed_mps: float,
    max_speed_mps: float,
    easting_m: float = 0.0,
) -> Unit:
    return Unit(
        entity_id=entity_id,
        side=side,
        domain=domain,
        position=Position(easting_m, 0.0, 0.0),
        speed=speed_mps,
        max_speed=max_speed_mps,
    )


def _conditions(
    *,
    ground_state: GroundState = GroundState.DRY,
    mud_depth_m: float = 0.0,
    snow_depth_m: float = 0.0,
    trafficability: float = 1.0,
) -> SeasonalConditions:
    return SeasonalConditions(
        ground_state=ground_state,
        snow_depth=snow_depth_m,
        mud_depth=mud_depth_m,
        vegetation_density=0.0,
        vegetation_moisture=0.0,
        sea_ice_thickness=0.0,
        wildfire_risk=0.0,
        ground_trafficability=trafficability,
        daylight_hours=12.0,
    )


def _obscurants() -> ObscurantsEngine:
    return ObscurantsEngine(
        SimpleNamespace(),
        SimpleNamespace(),
        SimpleNamespace(),
        np.random.Generator(np.random.PCG64(42)),
    )


def _context(
    *,
    calibration: dict[str, object],
    seasons: SeasonalConditions | None = None,
    sea: object | None = None,
    obscurants: ObscurantsEngine | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        calibration=calibration,
        cal_flat=calibration,
        clock=make_clock(),
        config=SimpleNamespace(behavior_rules={}),
        movement_diagnostics=None,
        tactical_targeting=None,
        event_bus=EventBus(),
        unit_weapons={},
        seasons_engine=(
            SimpleNamespace(current=seasons) if seasons is not None else None
        ),
        sea_state_engine=(SimpleNamespace(current=sea) if sea is not None else None),
        obscurants_engine=obscurants,
    )


def _move(unit: Unit, context: SimpleNamespace) -> float:
    enemy = _unit(
        "enemy",
        side="red",
        domain=unit.domain,
        speed_mps=0.0,
        max_speed_mps=0.0,
        easting_m=10_000.0,
    )
    battle = BattleContext(
        battle_id="environmental-movement",
        start_tick=0,
        start_time=datetime(2026, 8, 22, tzinfo=timezone.utc),
        involved_sides=["blue", "red"],
    )
    BattleManager(EventBus())._execute_movement(
        context,
        {"blue": [unit]},
        {"blue": [enemy]},
        dt=1.0,
        battle=battle,
    )
    return unit.position.easting


@pytest.mark.parametrize(
    ("speed_mps", "max_speed_mps"),
    [
        pytest.param(20.0, 20.0, id="wheeled"),
        pytest.param(10.0, 10.0, id="tracked"),
        pytest.param(4.0, 4.0, id="foot"),
    ],
)
def test_seasonal_adverse_ground_slows_each_real_movement_class(
    speed_mps: float,
    max_speed_mps: float,
) -> None:
    adverse = _move(
        _unit(
            "adverse",
            side="blue",
            domain=Domain.GROUND,
            speed_mps=speed_mps,
            max_speed_mps=max_speed_mps,
        ),
        _context(
            calibration={"enable_seasonal_effects": True},
            seasons=_conditions(
                ground_state=GroundState.SATURATED,
                mud_depth_m=0.2,
                snow_depth_m=0.1,
                trafficability=0.5,
            ),
        ),
    )
    disabled = _move(
        _unit(
            "disabled",
            side="blue",
            domain=Domain.GROUND,
            speed_mps=speed_mps,
            max_speed_mps=max_speed_mps,
        ),
        _context(
            calibration={"enable_seasonal_effects": False},
            seasons=_conditions(
                ground_state=GroundState.SATURATED,
                mud_depth_m=0.2,
                snow_depth_m=0.1,
                trafficability=0.5,
            ),
        ),
    )
    dry = _move(
        _unit(
            "dry",
            side="blue",
            domain=Domain.GROUND,
            speed_mps=speed_mps,
            max_speed_mps=max_speed_mps,
        ),
        _context(
            calibration={"enable_seasonal_effects": True},
            seasons=_conditions(),
        ),
    )

    assert 0.0 < adverse < disabled
    assert disabled == pytest.approx(dry)


def test_heavy_seas_slow_small_craft_but_not_large_or_disabled_vessels() -> None:
    sea = SimpleNamespace(
        beaufort_scale=5,
        tidal_current_speed=0.0,
        tidal_current_direction=0.0,
    )

    def distance(*, displacement_tons: float, max_speed_mps: float, enabled: bool) -> float:
        vessel = _unit(
            f"vessel-{displacement_tons}-{enabled}",
            side="blue",
            domain=Domain.NAVAL,
            speed_mps=max_speed_mps,
            max_speed_mps=max_speed_mps,
        )
        object.__setattr__(vessel, "displacement_tons", displacement_tons)
        return _move(
            vessel,
            _context(
                calibration={"enable_sea_state_ops": enabled},
                sea=sea,
            ),
        )

    small_enabled = distance(
        displacement_tons=500.0,
        max_speed_mps=12.0,
        enabled=True,
    )
    small_disabled = distance(
        displacement_tons=500.0,
        max_speed_mps=12.0,
        enabled=False,
    )
    large_enabled = distance(
        displacement_tons=5_000.0,
        max_speed_mps=20.0,
        enabled=True,
    )
    large_disabled = distance(
        displacement_tons=5_000.0,
        max_speed_mps=20.0,
        enabled=False,
    )

    assert 0.0 < small_enabled < small_disabled
    assert large_enabled == pytest.approx(large_disabled)


@pytest.mark.parametrize(
    ("enabled", "ground_state", "expected_clouds"),
    [
        pytest.param(True, GroundState.DRY, 1, id="enabled-dry"),
        pytest.param(True, GroundState.WET, 0, id="enabled-wet"),
        pytest.param(False, GroundState.DRY, 0, id="disabled-dry"),
    ],
)
def test_vehicle_movement_creates_real_dust_only_when_enabled_and_dry(
    enabled: bool,
    ground_state: GroundState,
    expected_clouds: int,
) -> None:
    obscurants = _obscurants()
    distance = _move(
        _unit(
            "vehicle",
            side="blue",
            domain=Domain.GROUND,
            speed_mps=10.0,
            max_speed_mps=10.0,
        ),
        _context(
            calibration={"enable_obscurants": enabled},
            seasons=_conditions(ground_state=ground_state),
            obscurants=obscurants,
        ),
    )
    clouds = obscurants.get_state()["clouds"]

    assert distance > 5.0
    assert len(clouds) == expected_clouds
    if clouds:
        assert clouds[0]["cloud_type"] == int(ObscurantType.DUST)
        assert clouds[0]["center_e"] == pytest.approx(distance)
