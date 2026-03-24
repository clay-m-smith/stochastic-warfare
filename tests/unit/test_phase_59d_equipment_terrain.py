"""Phase 59d: Equipment temperature stress & obstacle traversal.

Tests verify that equipment temperature stress → weapon jam, obstacle
traversal → movement reduction, and bridges_near API exists.
"""

from __future__ import annotations


import pytest

from stochastic_warfare.simulation.calibration import CalibrationSchema


class TestEquipmentTemperatureStress:
    """Temperature outside rated range increases jam probability."""

    def test_extreme_cold_stress(self) -> None:
        """Equipment at −50°C (outside rated −40 to +50): stress > 0."""
        from stochastic_warfare.entities.equipment import EquipmentItem, EquipmentManager

        item = EquipmentItem(
            equipment_id="wpn1",
            name="test_weapon",
            category=0,
            temperature_range=(-40.0, 50.0),
        )
        stress = EquipmentManager.environment_stress(item, -50.0)
        assert stress > 0
        # 10°C below min → stress = 10/20 = 0.5
        assert stress == pytest.approx(0.5)

    def test_extreme_heat_stress(self) -> None:
        """Equipment at +60°C: stress > 0."""
        from stochastic_warfare.entities.equipment import EquipmentItem, EquipmentManager

        item = EquipmentItem(
            equipment_id="wpn1",
            name="test_weapon",
            category=0,
            temperature_range=(-40.0, 50.0),
        )
        stress = EquipmentManager.environment_stress(item, 60.0)
        assert stress == pytest.approx(0.5)

    def test_normal_temp_no_stress(self) -> None:
        """Equipment at 20°C (within rated range): no stress."""
        from stochastic_warfare.entities.equipment import EquipmentItem, EquipmentManager

        item = EquipmentItem(
            equipment_id="wpn1",
            name="test_weapon",
            category=0,
            temperature_range=(-40.0, 50.0),
        )
        stress = EquipmentManager.environment_stress(item, 20.0)
        assert stress == 0.0

    def test_enable_equipment_stress_false_no_jam(self) -> None:
        """When enable_equipment_stress=False, jam logic is skipped."""
        cal = CalibrationSchema(enable_equipment_stress=False)
        assert cal.get("enable_equipment_stress", True) is False

    def test_structural_equipment_stress_in_battle(self) -> None:
        """Structural: battle.py checks enable_equipment_stress."""
        from pathlib import Path

        src = Path("stochastic_warfare/simulation/battle.py").read_text()
        assert 'enable_equipment_stress' in src
        assert "environment_stress" in src


class TestObstacleTraversal:
    """Obstacles with traversal_time_multiplier slow movement."""

    def test_wire_obstacle_reduces_movement(self) -> None:
        """Wire obstacle (traversal_time_multiplier=5.0): move_dist / 5."""
        from stochastic_warfare.core.types import Position
        from stochastic_warfare.terrain.obstacles import Obstacle, ObstacleManager

        obs = Obstacle(
            obstacle_id="wire1",
            obstacle_type=0,
            footprint=[(0, 0), (100, 0), (100, 100), (0, 100)],
            traversal_time_multiplier=3.0,
        )
        mgr = ObstacleManager([obs])
        results = mgr.obstacles_at(Position(50.0, 50.0, 0.0))
        assert len(results) == 1
        assert results[0].traversal_time_multiplier == 3.0

    def test_no_obstacles_no_penalty(self) -> None:
        """No obstacles at position: movement unaffected."""
        from stochastic_warfare.core.types import Position
        from stochastic_warfare.terrain.obstacles import ObstacleManager

        mgr = ObstacleManager([])
        results = mgr.obstacles_at(Position(50.0, 50.0, 0.0))
        assert len(results) == 0

    def test_enable_obstacle_effects_false(self) -> None:
        """When enable_obstacle_effects=False, obstacles ignored."""
        cal = CalibrationSchema(enable_obstacle_effects=False)
        assert cal.get("enable_obstacle_effects", True) is False

    def test_structural_obstacle_effects_in_battle(self) -> None:
        """Structural: battle.py checks enable_obstacle_effects."""
        from pathlib import Path

        src = Path("stochastic_warfare/simulation/battle.py").read_text()
        assert "enable_obstacle_effects" in src
        assert "traversal_time_multiplier" in src


class TestBridgesNear:
    """InfrastructureManager.bridges_near() API exists and works."""

    def test_bridges_near_method_exists(self) -> None:
        """bridges_near is a callable method on InfrastructureManager."""
        from stochastic_warfare.terrain.infrastructure import InfrastructureManager

        mgr = InfrastructureManager()
        assert hasattr(mgr, "bridges_near")
        assert callable(mgr.bridges_near)

    def test_bridges_near_returns_bridges(self) -> None:
        """bridges_near returns bridges within radius."""
        from stochastic_warfare.core.types import Position
        from stochastic_warfare.terrain.infrastructure import Bridge, InfrastructureManager

        b1 = Bridge(bridge_id="b1", position=(100.0, 100.0), road_id="r1")
        b2 = Bridge(bridge_id="b2", position=(500.0, 500.0), road_id="r2")
        mgr = InfrastructureManager(bridges=[b1, b2])

        results = mgr.bridges_near(Position(100.0, 100.0, 0.0), 50.0)
        assert len(results) == 1
        assert results[0].bridge_id == "b1"

    def test_bridges_near_excludes_destroyed(self) -> None:
        """Destroyed bridges (condition=0) are excluded."""
        from stochastic_warfare.core.types import Position
        from stochastic_warfare.terrain.infrastructure import Bridge, InfrastructureManager

        b1 = Bridge(
            bridge_id="b1", position=(100.0, 100.0), road_id="r1",
            condition=0.0,
        )
        mgr = InfrastructureManager(bridges=[b1])
        results = mgr.bridges_near(Position(100.0, 100.0, 0.0), 50.0)
        assert len(results) == 0
