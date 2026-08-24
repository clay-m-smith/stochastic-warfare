"""Phase 68e: Fire zone damage enforcement tests.

Verifies that units in active fire zones take burn damage when
``enable_fire_zones=True`` and ``fire_damage_per_tick`` is set.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pytest

from stochastic_warfare.combat.damage import (
    IncendiaryConfig,
    IncendiaryDamageEngine,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import UnitStatus
from stochastic_warfare.entities.unit_classes.ground import (
    GroundUnit,
    Posture,
)
from stochastic_warfare.simulation.battle import (
    BattleContext,
    BattleManager,
    _apply_aggregate_casualties,
)
from stochastic_warfare.simulation.calibration import CalibrationSchema
from tests.unit.simulation._battle_feature_harness import make_context

TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _make_unit(entity_id: str = "inf1", position: Position | None = None) -> GroundUnit:
    pos = position or Position(100, 100, 0)
    u = GroundUnit(entity_id=entity_id, position=pos, max_speed=4.0)
    object.__setattr__(u, "status", UnitStatus.ACTIVE)
    object.__setattr__(u, "speed", 4.0)
    return u


class _NoMovementExecutor:
    def execute(self, _owner: Any, _request: Any) -> None:
        return None


class _NoEngagementExecutor:
    def execute(self, _owner: Any, _request: Any) -> list[Any]:
        return []


def _execute_fire_tick(
    *,
    enabled: bool,
    easting: float,
    posture: Posture = Posture.MOVING,
    create_zone: bool = True,
) -> tuple[BattleManager, GroundUnit]:
    unit = _make_unit(position=Position(easting, 0.0, 0.0))
    object.__setattr__(unit, "side", "blue")
    object.__setattr__(unit, "posture", posture)
    object.__setattr__(unit, "personnel", list(range(100)))
    engine = IncendiaryDamageEngine(
        np.random.default_rng(68),
        IncendiaryConfig(burn_damage_per_second=0.1),
    )
    if create_zone:
        engine.create_fire_zone(
            Position(0.0, 0.0, 0.0),
            radius_m=50.0,
            fuel_load=1.0,
            wind_speed_mps=0.0,
            wind_dir_rad=0.0,
            duration_s=60.0,
            timestamp=0.0,
        )
    calibration = {
        "enable_fire_zones": enabled,
        "fire_damage_per_tick": 1.0,
    }
    if posture is Posture.DUG_IN:
        calibration.update(
            {
                "defensive_sides": ["blue"],
                "dig_in_ticks": 0,
            },
        )
    context = make_context(
        {"blue": [unit], "red": []},
        unit_weapons={},
        calibration=calibration,
    )
    context.order_execution = None
    context.incendiary_engine = engine
    battle = BattleContext(
        battle_id="fire",
        start_tick=0,
        start_time=TS,
        involved_sides=["blue", "red"],
        unit_ids={unit.entity_id},
    )
    manager = BattleManager(
        EventBus(),
        movement_executor=_NoMovementExecutor(),
        engagement_executor=_NoEngagementExecutor(),
    )

    manager.execute_tick(context, battle, 5.0)
    return manager, unit


class TestFireZoneDamage:
    """Fire zone damage applied to units inside active zones."""

    @pytest.mark.parametrize(
        ("enabled", "easting", "posture", "create_zone", "casualties"),
        [
            (True, 0.0, Posture.MOVING, True, 10),
            (True, 50.0, Posture.MOVING, True, 10),
            (True, 50.000_000_1, Posture.MOVING, True, 0),
            (False, 0.0, Posture.MOVING, True, 0),
            (True, 0.0, Posture.DUG_IN, True, 5),
            (True, 0.0, Posture.MOVING, False, 0),
        ],
    )
    def test_production_tick_applies_enabled_disabled_and_closed_boundaries(
        self,
        enabled: bool,
        easting: float,
        posture: Posture,
        create_zone: bool,
        casualties: int,
    ) -> None:
        manager, unit = _execute_fire_tick(
            enabled=enabled,
            easting=easting,
            posture=posture,
            create_zone=create_zone,
        )

        assert manager.get_state()["cumulative_casualties"].get(
            unit.entity_id,
            0,
        ) == casualties

    def test_fire_casualties_survive_manager_checkpoint(self) -> None:
        manager, unit = _execute_fire_tick(enabled=True, easting=0.0)
        state = copy.deepcopy(manager.get_state())
        restored = BattleManager(EventBus())

        restored.set_state(copy.deepcopy(state))

        assert restored.get_state()["cumulative_casualties"] == {
            unit.entity_id: 10,
        }

    def test_fire_damage_per_tick_calibration(self):
        """CalibrationSchema accepts fire_damage_per_tick."""
        schema = CalibrationSchema(fire_damage_per_tick=0.05)
        assert schema.fire_damage_per_tick == 0.05

        default = CalibrationSchema()
        assert default.fire_damage_per_tick == 0.01

    def test_aggregate_casualties_from_fire(self):
        """Fire damage converts to aggregate casualties via _apply_aggregate_casualties."""
        unit = _make_unit()
        # Give unit 10 personnel so 1 casualty = 10% < threshold
        object.__setattr__(unit, "personnel", list(range(10)))  # mock personnel list

        pending: list[tuple] = []
        tracker: dict[str, int] = {}

        _apply_aggregate_casualties(
            casualties=1,
            target=unit,
            pending_damage=pending,
            destruction_threshold=0.5,
            disable_threshold=0.3,
            cumulative_tracker=tracker,
        )

        assert unit.entity_id in tracker
        assert tracker[unit.entity_id] == 1
        # 1 casualty on unit with 10 personnel = 10% < 30% disable threshold
        assert len(pending) == 0
