"""Phase 78b: Bridge capacity and ford crossing tests."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit
from stochastic_warfare.simulation.battle import BattleManager
from stochastic_warfare.simulation.movement_diagnostics import (
    MovementDiagnostics,
    MovementReason,
)
from tests.unit.simulation._battle_feature_harness import (
    make_context,
    make_unit as make_executor_unit,
)


# ---------------------------------------------------------------------------
# Unit weight_tons field
# ---------------------------------------------------------------------------


class TestUnitWeight:
    """Unit.weight_tons field tests."""

    def test_default_weight_is_zero(self):
        u = Unit(entity_id="inf1", position=Position(0, 0))
        assert u.weight_tons == 0.0

    def test_weight_in_get_state(self):
        u = Unit(entity_id="tank1", position=Position(0, 0), weight_tons=62.0)
        state = u.get_state()
        assert state["weight_tons"] == 62.0

    def test_weight_in_set_state(self):
        u = Unit(entity_id="tank1", position=Position(0, 0))
        state = u.get_state()
        state["weight_tons"] = 45.0
        u2 = Unit(entity_id="x", position=Position(0, 0))
        u2.set_state(state)
        assert u2.weight_tons == 45.0

    def test_weight_defaults_in_set_state_when_missing(self):
        """Legacy checkpoints without weight_tons should default to 0.0."""
        u = Unit(entity_id="inf1", position=Position(0, 0))
        state = u.get_state()
        del state["weight_tons"]
        u2 = Unit(entity_id="x", position=Position(0, 0))
        u2.set_state(state)
        assert u2.weight_tons == 0.0


# ---------------------------------------------------------------------------
# Bridge capacity enforcement
# ---------------------------------------------------------------------------


class TestProductionCrossingGates:
    """Bridge and ford decisions come from the production movement executor."""

    @staticmethod
    def _execute(
        *,
        weight_tons: float,
        unit_type: str = "test_vehicle",
        enabled: bool = True,
        bridge_capacity_tons: float | None = None,
        in_water: bool = False,
        has_ford: bool = False,
    ) -> tuple[Unit, MovementDiagnostics]:
        from stochastic_warfare.terrain.infrastructure import Bridge

        unit = make_executor_unit(
            "vehicle",
            "blue",
            0.0,
            max_speed=10.0,
        )
        object.__setattr__(unit, "weight_tons", weight_tons)
        object.__setattr__(unit, "unit_type", unit_type)
        enemy = make_executor_unit("enemy", "red", 1_000.0)
        context = make_context(
            {"blue": [unit], "red": [enemy]},
            unit_weapons={},
            calibration={"enable_bridge_capacity": enabled},
        )
        context.infrastructure = (
            None
            if bridge_capacity_tons is None
            else SimpleNamespace(
                bridges_near=lambda *_args: [
                    Bridge(
                        bridge_id="bridge",
                        position=(10.0, 0.0),
                        road_id="road",
                        capacity_tons=bridge_capacity_tons,
                    ),
                ],
            )
        )
        context.hydrography_manager = SimpleNamespace(
            is_in_water=lambda _position: in_water,
            ford_points_near=lambda *_args: (
                [Position(10.0, 0.0)] if has_ford else []
            ),
        )
        diagnostics = MovementDiagnostics({unit.entity_id: "blue"})
        manager = BattleManager(
            EventBus(),
            movement_diagnostics=diagnostics,
        )

        manager._execute_movement(
            context,
            {"blue": [unit]},
            {"blue": [enemy]},
            1.0,
            None,
            {},
            enemy_pos_arrays={"blue": np.array([[1_000.0, 0.0]])},
        )
        return unit, diagnostics

    @pytest.mark.parametrize(
        ("weight_tons", "unit_type", "capacity", "expected_easting", "reason"),
        [
            (62.0, "test_vehicle", 40.0, 0.0, MovementReason.RESOURCE_BLOCKED),
            (40.0, "test_vehicle", 40.0, 10.0, MovementReason.MOVED),
            (0.0, "infantry_squad", 10.0, 10.0, MovementReason.MOVED),
            (0.0, "m1a2_abrams", 40.0, 0.0, MovementReason.RESOURCE_BLOCKED),
        ],
    )
    def test_bridge_capacity_and_weight_default_boundaries_are_recorded(
        self,
        weight_tons: float,
        unit_type: str,
        capacity: float,
        expected_easting: float,
        reason: MovementReason,
    ) -> None:
        unit, diagnostics = self._execute(
            weight_tons=weight_tons,
            unit_type=unit_type,
            bridge_capacity_tons=capacity,
        )

        assert unit.position.easting == pytest.approx(expected_easting)
        assert diagnostics.get_unit(unit.entity_id).final_reason is reason

    @pytest.mark.parametrize(
        ("enabled", "has_ford", "expected_easting", "reason"),
        [
            (True, True, 3.0, MovementReason.MOVED),
            (True, False, 0.0, MovementReason.RESOURCE_BLOCKED),
            (False, False, 10.0, MovementReason.MOVED),
        ],
    )
    def test_ford_enabled_disabled_and_missing_boundaries_are_recorded(
        self,
        enabled: bool,
        has_ford: bool,
        expected_easting: float,
        reason: MovementReason,
    ) -> None:
        unit, diagnostics = self._execute(
            weight_tons=10.0,
            enabled=enabled,
            in_water=True,
            has_ford=has_ford,
        )

        assert unit.position.easting == pytest.approx(expected_easting)
        assert diagnostics.get_unit(unit.entity_id).final_reason is reason
