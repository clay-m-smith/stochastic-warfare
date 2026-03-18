"""Phase 63c: Checkpoint State Completeness tests."""

import pytest

from stochastic_warfare.simulation.scenario import SimulationContext


def _read_scenario_source():
    """Read scenario.py source for structural checks."""
    import stochastic_warfare.simulation.scenario as mod
    return open(mod.__file__).read()


class TestCheckpointEngineList:
    """Verify get_state/set_state include previously missing engines."""

    def test_get_state_includes_comms_engine(self):
        src = _read_scenario_source()
        # Must appear in the get_state engine list
        assert '("comms_engine", self.comms_engine)' in src

    def test_get_state_includes_detection_engine(self):
        src = _read_scenario_source()
        assert '("detection_engine", self.detection_engine)' in src

    def test_get_state_includes_movement_engine(self):
        src = _read_scenario_source()
        assert '("movement_engine", self.movement_engine)' in src

    def test_get_state_includes_conditions_engine(self):
        src = _read_scenario_source()
        assert '("conditions_engine", self.conditions_engine)' in src

    def test_get_state_includes_weather_engine(self):
        """Pre-existing — verify not accidentally removed."""
        src = _read_scenario_source()
        assert '("weather_engine", self.weather_engine)' in src

    def test_get_state_includes_morale_machine(self):
        """Pre-existing — verify not accidentally removed."""
        src = _read_scenario_source()
        assert '("morale_machine", self.morale_machine)' in src

    def test_set_state_includes_comms_engine(self):
        """set_state engine list also has comms_engine."""
        src = _read_scenario_source()
        # Both get_state and set_state have separate engine lists
        # Verify comms_engine appears at least twice (once in each list)
        count = src.count('("comms_engine", self.comms_engine)')
        assert count >= 2, f"comms_engine appears {count} times, expected >=2"

    def test_set_state_includes_detection_engine(self):
        src = _read_scenario_source()
        count = src.count('("detection_engine", self.detection_engine)')
        assert count >= 2

    def test_engine_with_no_get_state_gracefully_skipped(self):
        """Engines without get_state are skipped (hasattr check)."""
        src = _read_scenario_source()
        assert 'hasattr(eng, "get_state")' in src
        assert 'hasattr(eng, "set_state")' in src

    def test_engine_count_regression_guard(self):
        """Total engine entries in get_state list is at minimum expected."""
        src = _read_scenario_source()
        # Count all entries of the pattern ("xxx", self.xxx) in get_state
        # The engines list starts after "Delegate to engines" comment
        import re
        # Find all engine tuples in get_state section
        matches = re.findall(r'\("(\w+)", self\.\1\)', src)
        # Should have at least 48 entries (original ~44 + 4 new)
        assert len(matches) >= 48, f"Only found {len(matches)} engine entries"
