"""Phase 78: Structural verification tests."""

from __future__ import annotations



class TestCalibrationFields:
    """Verify CalibrationSchema defines all Phase 78 fields."""

    def test_enable_ice_crossing_field(self):
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        cal = CalibrationSchema()
        assert cal.enable_ice_crossing is False
        assert cal.get("enable_ice_crossing", True) is False

    def test_enable_bridge_capacity_field(self):
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        cal = CalibrationSchema()
        assert cal.enable_bridge_capacity is False
        assert cal.get("enable_bridge_capacity", True) is False

    def test_enable_environmental_fatigue_field(self):
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        cal = CalibrationSchema()
        assert cal.enable_environmental_fatigue is False
        assert cal.get("enable_environmental_fatigue", True) is False


class TestBattleGates:
    """Verify battle.py contains the Phase 78 enable_* gates."""

    def _read_battle_source(self) -> str:
        import inspect

        from stochastic_warfare.simulation import battle
        return inspect.getsource(battle)

    def test_ice_crossing_gate(self):
        src = self._read_battle_source()
        assert "enable_ice_crossing" in src

    def test_bridge_capacity_gate(self):
        src = self._read_battle_source()
        assert "enable_bridge_capacity" in src

    def test_environmental_fatigue_gate(self):
        src = self._read_battle_source()
        assert "enable_environmental_fatigue" in src

    def test_fire_spread_in_engine(self):
        """Verify engine.py calls spread_fire."""
        import inspect

        from stochastic_warfare.simulation import engine
        src = inspect.getsource(engine)
        assert "spread_fire" in src

    def test_vegetation_density_in_engine(self):
        """Verify engine.py calls set_vegetation_density."""
        import inspect

        from stochastic_warfare.simulation import engine
        src = inspect.getsource(engine)
        assert "set_vegetation_density" in src


class TestLOSVegetation:
    """Verify LOSEngine has vegetation support."""

    def test_los_engine_accepts_classification(self):
        """LOSEngine should accept classification parameter."""
        import numpy as np

        from stochastic_warfare.terrain.heightmap import Heightmap, HeightmapConfig
        from stochastic_warfare.terrain.los import LOSEngine

        cfg = HeightmapConfig(origin_easting=0.0, origin_northing=0.0, cell_size=10.0)
        hm = Heightmap(np.zeros((5, 5)), cfg)
        los = LOSEngine(hm, classification=None)
        assert hasattr(los, "_classification")
        assert los._classification is None

    def test_set_vegetation_density(self):
        """LOSEngine.set_vegetation_density should clamp 0-1."""
        import numpy as np

        from stochastic_warfare.terrain.heightmap import Heightmap, HeightmapConfig
        from stochastic_warfare.terrain.los import LOSEngine

        cfg = HeightmapConfig(origin_easting=0.0, origin_northing=0.0, cell_size=10.0)
        hm = Heightmap(np.zeros((5, 5)), cfg)
        los = LOSEngine(hm)
        los.set_vegetation_density(0.5)
        assert los._vegetation_density == 0.5
        los.set_vegetation_density(-0.5)
        assert los._vegetation_density == 0.0
        los.set_vegetation_density(1.5)
        assert los._vegetation_density == 1.0


class TestMovementEngineIceOnIce:
    """Verify MovementEngine has is_on_ice method."""

    def test_method_exists(self):
        from stochastic_warfare.movement.engine import MovementEngine

        assert hasattr(MovementEngine, "is_on_ice")

    def test_returns_false_without_classification(self):
        from stochastic_warfare.movement.engine import MovementEngine
        from stochastic_warfare.core.types import Position

        eng = MovementEngine()
        assert eng.is_on_ice(Position(0, 0), None) is False


class TestFatigueTemperatureStress:
    """Verify FatigueManager.accumulate accepts temperature_stress."""

    def test_parameter_accepted(self):
        from stochastic_warfare.movement.fatigue import FatigueManager

        fm = FatigueManager()
        # Should not raise
        fm.accumulate("u1", 1.0, "march", temperature_stress=0.5)


class TestIncendiarySpreadFire:
    """Verify IncendiaryDamageEngine has spread_fire method."""

    def test_method_exists(self):
        from stochastic_warfare.combat.damage import IncendiaryDamageEngine

        assert hasattr(IncendiaryDamageEngine, "spread_fire")


class TestUnitWeightField:
    """Verify Unit has weight_tons field."""

    def test_weight_field(self):
        from stochastic_warfare.core.types import Position
        from stochastic_warfare.entities.base import Unit

        u = Unit(entity_id="x", position=Position(0, 0))
        assert hasattr(u, "weight_tons")
        assert u.weight_tons == 0.0
