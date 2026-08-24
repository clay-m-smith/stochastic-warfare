"""Dynamic terrain and environmental behavior contracts."""

from __future__ import annotations

class TestLOSVegetation:
    """Verify LOSEngine has vegetation support."""

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

    def test_returns_false_without_classification(self):
        from stochastic_warfare.core.types import Position
        from stochastic_warfare.movement.engine import MovementEngine

        eng = MovementEngine()
        assert eng.is_on_ice(Position(0, 0), None) is False


class TestFatigueTemperatureStress:
    """Verify FatigueManager.accumulate accepts temperature_stress."""

    def test_parameter_accepted(self):
        from stochastic_warfare.movement.fatigue import FatigueManager

        fm = FatigueManager()
        fm.accumulate("u1", 1.0, "march", temperature_stress=0.5)
        stressed = fm.get_fatigue("u1")

        control = FatigueManager()
        control.accumulate("u1", 1.0, "march", temperature_stress=0.0)
        unstressed = control.get_fatigue("u1")
        assert stressed.physical > unstressed.physical
        assert stressed.mental > unstressed.mental
