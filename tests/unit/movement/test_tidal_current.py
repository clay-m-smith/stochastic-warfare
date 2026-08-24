"""Production movement tests for sea-state tidal projection."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from tests.conftest import make_clock

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.simulation.battle import BattleContext, BattleManager
from stochastic_warfare.simulation.calibration import CalibrationSchema


def _naval_unit(
    entity_id: str,
    *,
    easting: float = 0.0,
    northing: float = 0.0,
) -> Unit:
    unit = Unit(
        entity_id=entity_id,
        side="blue",
        domain=Domain.NAVAL,
        position=Position(easting, northing, 0.0),
        speed=10.0,
        max_speed=20.0,
    )
    object.__setattr__(unit, "status", UnitStatus.ACTIVE)
    return unit


def _enemy(
    entity_id: str,
    *,
    easting: float = 10_000.0,
    northing: float = 0.0,
) -> Unit:
    unit = Unit(
        entity_id=entity_id,
        side="red",
        domain=Domain.NAVAL,
        position=Position(easting, northing, 0.0),
        speed=0.0,
        max_speed=0.0,
    )
    object.__setattr__(unit, "status", UnitStatus.ACTIVE)
    return unit


def _context(*, enabled: bool, current_speed: float, current_direction: float):
    calibration = CalibrationSchema(
        enable_sea_state_ops=enabled,
        formation_spacing_m=0.0,
    )
    sea = SimpleNamespace(
        beaufort_scale=0,
        tidal_current_speed=current_speed,
        tidal_current_direction=current_direction,
    )
    return SimpleNamespace(
        calibration=calibration,
        cal_flat=calibration.model_dump(mode="python"),
        clock=make_clock(),
        config=SimpleNamespace(
            calibration_overrides=calibration,
            behavior_rules={},
        ),
        sea_state_engine=SimpleNamespace(current=sea),
        movement_diagnostics=None,
        tactical_targeting=None,
        event_bus=EventBus(),
    )


def _battle() -> BattleContext:
    return BattleContext(
        battle_id="tidal-current",
        start_tick=0,
        start_time=datetime(2026, 8, 22, tzinfo=timezone.utc),
        involved_sides=["blue", "red"],
    )


def _move(
    units: list[Unit],
    enemies: list[Unit],
    *,
    enabled: bool,
    current_speed: float,
    current_direction: float,
) -> None:
    manager = BattleManager(EventBus())
    manager._execute_movement(
        _context(
            enabled=enabled,
            current_speed=current_speed,
            current_direction=current_direction,
        ),
        {"blue": units},
        {"blue": enemies},
        dt=1.0,
        battle=_battle(),
    )


@pytest.mark.parametrize(
    ("direction", "expected_distance"),
    [
        pytest.param(math.pi / 2.0, 12.0, id="aligned"),
        pytest.param(-math.pi / 2.0, 8.0, id="opposed"),
        pytest.param(0.0, 10.0, id="cross-current"),
    ],
)
def test_tidal_projection_uses_current_units_resolved_heading(
    direction: float,
    expected_distance: float,
) -> None:
    vessel = _naval_unit("vessel")
    _move(
        [vessel],
        [_enemy("enemy")],
        enabled=True,
        current_speed=2.0,
        current_direction=direction,
    )

    assert vessel.position.easting == pytest.approx(expected_distance)
    assert vessel.position.northing == pytest.approx(0.0)


def test_tidal_projection_is_independent_for_first_and_later_vessels() -> None:
    eastbound = _naval_unit("vessel-a", easting=-1_000.0)
    northbound = _naval_unit("vessel-b", northing=-1_000.0)

    _move(
        [eastbound, northbound],
        [_enemy("enemy", easting=0.0)],
        enabled=True,
        current_speed=2.0,
        current_direction=0.0,
    )

    assert eastbound.position.easting == pytest.approx(-990.0)
    assert eastbound.position.northing == pytest.approx(0.0)
    assert northbound.position.easting == pytest.approx(0.0)
    assert northbound.position.northing == pytest.approx(-988.0)


def test_disabled_sea_state_does_not_apply_tidal_projection() -> None:
    vessel = _naval_unit("vessel")
    _move(
        [vessel],
        [_enemy("enemy")],
        enabled=False,
        current_speed=2.0,
        current_direction=math.pi / 2.0,
    )

    assert vessel.position.easting == pytest.approx(10.0)
