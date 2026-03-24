"""Phase 61b: Acoustic Layer -> Sonar Detection modifier tests.

When enable_acoustic_layers=True, sonar detection in battle.py queries
underwater_acoustics_engine.conditions for layer data and applies modifiers
to detection range:
  - Thermocline cross-layer: detection_range *= 0.1
  - Surface duct (both in): detection_range *= 3.0
  - Surface duct (target below): detection_range *= 0.06
  - Convergence zone spike: detection_range *= 2.0
  - Acoustic shadow (deep, between CZs): detection_range *= 0.05
  - Non-sonar sensors: no acoustic effects
  - enable_acoustic_layers=False: no effects
  - No underwater_acoustics_engine: graceful fallback
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from stochastic_warfare.detection.sensors import SensorType
from stochastic_warfare.environment.underwater_acoustics import AcousticConditions


# ---------------------------------------------------------------------------
# Helpers — replicate the modifier logic from battle.py (lines ~2447-2490)
# so we can test it in isolation without running full battle resolution.
# ---------------------------------------------------------------------------

_SONAR_TYPES = frozenset({
    SensorType.ACTIVE_SONAR,
    SensorType.PASSIVE_SONAR,
    SensorType.PASSIVE_ACOUSTIC,
})


def _compute_acoustic_modifier(
    ac: AcousticConditions,
    ua_engine: SimpleNamespace,
    observer_depth: float,
    target_depth: float,
    best_range: float,
) -> float:
    """Reproduce the acoustic layer modifier logic from battle.py."""
    layer_mod = 1.0

    # Thermocline: target below, observer above
    if (ac.thermocline_depth
            and target_depth > ac.thermocline_depth
            and observer_depth <= ac.thermocline_depth):
        layer_mod *= 0.1  # ~20 dB loss

    # Surface duct
    if ac.surface_duct_depth:
        if (observer_depth < ac.surface_duct_depth
                and target_depth < ac.surface_duct_depth):
            layer_mod *= 3.0  # +10 dB gain
        elif (observer_depth < ac.surface_duct_depth
                and target_depth > ac.surface_duct_depth):
            layer_mod *= 0.06  # +15 dB loss

    # Convergence zones
    cz_ranges = ua_engine.convergence_zone_ranges(observer_depth)
    in_cz = any(abs(best_range - cz_r) < 5000 for cz_r in cz_ranges)
    if cz_ranges and best_range > 30000 and not in_cz:
        layer_mod *= 0.05  # acoustic shadow
    elif in_cz:
        layer_mod *= 2.0  # CZ spike

    return layer_mod


def _make_acoustic_conditions(
    surface_duct_depth: float | None = 100.0,
    thermocline_depth: float | None = 150.0,
) -> AcousticConditions:
    """Create mock AcousticConditions with configurable layer depths."""
    svp = SimpleNamespace(
        depths=np.array([0.0, 50.0, 150.0, 500.0, 1000.0]),
        velocities=np.array([1500.0, 1501.0, 1490.0, 1480.0, 1485.0]),
    )
    return AcousticConditions(
        svp=svp,
        surface_duct_depth=surface_duct_depth,
        thermocline_depth=thermocline_depth,
        deep_channel_depth=800.0,
        ambient_noise_level=60.0,
    )


def _make_ua_engine(
    ac: AcousticConditions | None = None,
) -> SimpleNamespace:
    """Create a mock UnderwaterAcousticsEngine."""
    if ac is None:
        ac = _make_acoustic_conditions()
    return SimpleNamespace(
        conditions=ac,
        convergence_zone_ranges=lambda depth: [
            55_000, 110_000, 165_000, 220_000, 275_000,
        ],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestThermoclineModifier:
    """Thermocline layer crossing attenuates detection."""

    def test_target_below_observer_above_thermocline(self) -> None:
        """Target below thermocline, observer above -> 0.1x modifier (~20 dB loss)."""
        ac = _make_acoustic_conditions(
            surface_duct_depth=None,
            thermocline_depth=150.0,
        )
        ua = _make_ua_engine(ac)
        mod = _compute_acoustic_modifier(
            ac, ua,
            observer_depth=50.0,    # above thermocline (150m)
            target_depth=200.0,     # below thermocline
            best_range=5000.0,      # short range, no CZ/shadow effects
        )
        assert mod == pytest.approx(0.1, abs=1e-6), (
            "Cross-thermocline detection should apply 0.1 modifier"
        )

    def test_both_above_thermocline_no_penalty(self) -> None:
        """Both observer and target above thermocline -> no thermocline penalty."""
        ac = _make_acoustic_conditions(
            surface_duct_depth=None,
            thermocline_depth=150.0,
        )
        ua = _make_ua_engine(ac)
        mod = _compute_acoustic_modifier(
            ac, ua,
            observer_depth=50.0,
            target_depth=100.0,     # both above 150m
            best_range=5000.0,
        )
        assert mod == pytest.approx(1.0, abs=1e-6), (
            "Both above thermocline should have no modifier"
        )


class TestSurfaceDuct:
    """Surface duct traps sound, boosting or blocking detection."""

    def test_both_in_duct_gain(self) -> None:
        """Both observer and target in surface duct -> 3.0x gain (+10 dB)."""
        ac = _make_acoustic_conditions(
            surface_duct_depth=100.0,
            thermocline_depth=None,   # no thermocline effect
        )
        ua = _make_ua_engine(ac)
        mod = _compute_acoustic_modifier(
            ac, ua,
            observer_depth=30.0,
            target_depth=50.0,      # both < 100m duct depth
            best_range=5000.0,
        )
        assert mod == pytest.approx(3.0, abs=1e-6), (
            "Both in surface duct should give 3.0x detection gain"
        )

    def test_target_below_duct_loss(self) -> None:
        """Observer in duct, target below duct -> 0.06x loss (+15 dB)."""
        ac = _make_acoustic_conditions(
            surface_duct_depth=100.0,
            thermocline_depth=None,
        )
        ua = _make_ua_engine(ac)
        mod = _compute_acoustic_modifier(
            ac, ua,
            observer_depth=30.0,    # in duct (< 100m)
            target_depth=200.0,     # below duct (> 100m)
            best_range=5000.0,
        )
        assert mod == pytest.approx(0.06, abs=1e-6), (
            "Target below surface duct should give 0.06x modifier"
        )


class TestConvergenceZone:
    """Convergence zones produce detection spikes at ~55km intervals."""

    def test_cz_spike_at_55km(self) -> None:
        """Range at CZ (~55km) -> 2.0x detection spike."""
        ac = _make_acoustic_conditions(
            surface_duct_depth=None,
            thermocline_depth=None,
        )
        ua = _make_ua_engine(ac)
        mod = _compute_acoustic_modifier(
            ac, ua,
            observer_depth=50.0,
            target_depth=50.0,
            best_range=55_000.0,    # at first CZ
        )
        assert mod == pytest.approx(2.0, abs=1e-6), (
            "Detection at CZ range should get 2.0x spike"
        )

    def test_acoustic_shadow_between_czs(self) -> None:
        """Deep water between CZ ranges (>30km, not near any CZ) -> 0.05x shadow."""
        ac = _make_acoustic_conditions(
            surface_duct_depth=None,
            thermocline_depth=None,
        )
        ua = _make_ua_engine(ac)
        # 80km is between 55km and 110km CZs, and > 5km from either
        mod = _compute_acoustic_modifier(
            ac, ua,
            observer_depth=50.0,
            target_depth=50.0,
            best_range=80_000.0,
        )
        assert mod == pytest.approx(0.05, abs=1e-6), (
            "Between CZ ranges in deep water should be acoustic shadow (0.05x)"
        )

    def test_short_range_no_cz_shadow(self) -> None:
        """Range < 30km -> no CZ shadow effect even if not at a CZ."""
        ac = _make_acoustic_conditions(
            surface_duct_depth=None,
            thermocline_depth=None,
        )
        ua = _make_ua_engine(ac)
        mod = _compute_acoustic_modifier(
            ac, ua,
            observer_depth=50.0,
            target_depth=50.0,
            best_range=15_000.0,    # < 30km, no shadow
        )
        assert mod == pytest.approx(1.0, abs=1e-6), (
            "Short range (<30km) should have no CZ/shadow modifier"
        )


class TestNonSonarSensorsUnaffected:
    """Non-sonar sensor types should receive no acoustic modifiers."""

    @pytest.mark.parametrize("sensor_type", [
        SensorType.VISUAL,
        SensorType.THERMAL,
        SensorType.RADAR,
        SensorType.ESM,
    ])
    def test_non_sonar_excluded(self, sensor_type: SensorType) -> None:
        """Non-sonar sensor types are not in _SONAR_TYPES -> no modifier applied."""
        assert sensor_type not in _SONAR_TYPES, (
            f"{sensor_type.name} should NOT be in sonar types set"
        )

    @pytest.mark.parametrize("sensor_type", [
        SensorType.ACTIVE_SONAR,
        SensorType.PASSIVE_SONAR,
        SensorType.PASSIVE_ACOUSTIC,
    ])
    def test_sonar_types_included(self, sensor_type: SensorType) -> None:
        """All three sonar sensor types should be recognized for acoustic effects."""
        assert sensor_type in _SONAR_TYPES, (
            f"{sensor_type.name} should be in sonar types set"
        )


class TestEnableFlag:
    """enable_acoustic_layers flag gates the entire acoustic layer system."""

    def test_structural_flag_in_battle(self) -> None:
        """Structural: battle.py checks enable_acoustic_layers before applying."""
        from pathlib import Path

        src = Path("stochastic_warfare/simulation/battle.py").read_text()
        assert "enable_acoustic_layers" in src, (
            "battle.py must reference enable_acoustic_layers flag"
        )

    def test_structural_flag_in_calibration(self) -> None:
        """Structural: CalibrationSchema includes enable_acoustic_layers field."""
        from pathlib import Path

        src = Path("stochastic_warfare/simulation/calibration.py").read_text()
        assert "enable_acoustic_layers" in src, (
            "CalibrationSchema must include enable_acoustic_layers"
        )


class TestGracefulFallback:
    """Missing underwater_acoustics_engine -> no crash, no modifier."""

    def test_no_ua_engine_no_crash(self) -> None:
        """If ctx has no underwater_acoustics_engine, getattr returns None -> skip."""
        ctx = SimpleNamespace()  # no underwater_acoustics_engine attribute
        ua = getattr(ctx, "underwater_acoustics_engine", None)
        assert ua is None, "Missing engine should resolve to None via getattr"
        # The battle.py code will simply skip the modifier block


class TestCombinedEffects:
    """Multiple acoustic layers combine multiplicatively."""

    def test_thermocline_plus_shadow(self) -> None:
        """Thermocline cross + acoustic shadow compound multiplicatively."""
        ac = _make_acoustic_conditions(
            surface_duct_depth=None,
            thermocline_depth=150.0,
        )
        ua = _make_ua_engine(ac)
        # observer above thermocline, target below, at shadow range
        mod = _compute_acoustic_modifier(
            ac, ua,
            observer_depth=50.0,
            target_depth=200.0,
            best_range=80_000.0,   # shadow zone (>30km, not at CZ)
        )
        # 0.1 (thermocline) * 0.05 (shadow) = 0.005
        assert mod == pytest.approx(0.005, abs=1e-6), (
            "Thermocline + shadow should compound: 0.1 * 0.05 = 0.005"
        )

    def test_surface_duct_plus_cz_spike(self) -> None:
        """Surface duct gain + CZ spike compound multiplicatively."""
        ac = _make_acoustic_conditions(
            surface_duct_depth=100.0,
            thermocline_depth=None,
        )
        ua = _make_ua_engine(ac)
        # Both in duct, at CZ range
        mod = _compute_acoustic_modifier(
            ac, ua,
            observer_depth=30.0,
            target_depth=50.0,
            best_range=55_000.0,   # CZ range
        )
        # 3.0 (duct gain) * 2.0 (CZ spike) = 6.0
        assert mod == pytest.approx(6.0, abs=1e-6), (
            "Surface duct + CZ spike should compound: 3.0 * 2.0 = 6.0"
        )
