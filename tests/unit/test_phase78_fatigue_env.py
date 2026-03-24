"""Phase 78c: Environmental fatigue acceleration tests."""

from __future__ import annotations

import pytest

from stochastic_warfare.movement.fatigue import FatigueConfig, FatigueManager, FatigueState


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTemperatureStress:
    """FatigueManager.accumulate with temperature_stress parameter."""

    def test_high_temperature_stress_increases_fatigue(self):
        """Positive temperature_stress should increase fatigue rate."""
        fm_base = FatigueManager()
        fm_hot = FatigueManager()

        s_base = fm_base.accumulate("u1", 1.0, "march", temperature_stress=0.0)
        s_hot = fm_hot.accumulate("u1", 1.0, "march", temperature_stress=0.7)

        assert s_hot.physical > s_base.physical

    def test_zero_temperature_stress_no_effect(self):
        """temperature_stress=0.0 should have no effect on fatigue."""
        fm1 = FatigueManager()
        fm2 = FatigueManager()

        s1 = fm1.accumulate("u1", 1.0, "march")
        s2 = fm2.accumulate("u1", 1.0, "march", temperature_stress=0.0)

        assert s1.physical == pytest.approx(s2.physical)
        assert s1.mental == pytest.approx(s2.mental)

    def test_temperature_stress_additive_with_altitude(self):
        """Temperature stress and altitude penalty should both apply."""
        fm = FatigueManager()

        # Both altitude and temperature stress
        s = fm.accumulate("u1", 1.0, "march", altitude=3000.0, temperature_stress=0.5)

        # Compare to altitude-only
        fm2 = FatigueManager()
        s2 = fm2.accumulate("u1", 1.0, "march", altitude=3000.0, temperature_stress=0.0)

        assert s.physical > s2.physical

    def test_cold_stress_increases_fatigue(self):
        """Cold stress (positive temperature_stress from cold) increases fatigue."""
        fm = FatigueManager()
        # temperature_stress is always positive — caller computes it from cold/heat
        s = fm.accumulate("u1", 1.0, "march", temperature_stress=1.0)

        fm_base = FatigueManager()
        s_base = fm_base.accumulate("u1", 1.0, "march")

        # temperature_stress=1.0 → rate *= 2.0 → double physical fatigue
        assert s.physical == pytest.approx(s_base.physical * 2.0)

    def test_fatigued_unit_has_reduced_speed(self):
        """Fatigued unit should have speed_modifier < 1.0."""
        fm = FatigueManager()
        # Accumulate significant fatigue
        fm.accumulate("u1", 10.0, "march", temperature_stress=0.5)
        mod = fm.speed_modifier("u1")
        assert mod < 1.0

    def test_fatigued_unit_has_reduced_accuracy(self):
        """Fatigued unit should have accuracy_modifier < 1.0."""
        fm = FatigueManager()
        fm.accumulate("u1", 10.0, "combat", temperature_stress=0.5)
        mod = fm.accuracy_modifier("u1")
        assert mod < 1.0
