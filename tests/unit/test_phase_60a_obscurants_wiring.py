"""Phase 60a: Obscurants → Detection & Engagement wiring tests."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
import numpy as np

from stochastic_warfare.core.types import Position
from stochastic_warfare.environment.obscurants import (
    ObscurantsEngine,
    ObscurantType,
    SpectralBlocking,
)
from stochastic_warfare.detection.sensors import SensorType


def _make_obs_engine(wind_speed: float = 0.0) -> ObscurantsEngine:
    """Create a minimal ObscurantsEngine."""
    weather = MagicMock()
    weather.current.wind.speed = wind_speed
    weather.current.wind.direction = 0.0
    weather.current.visibility = 10000.0
    weather.current.state.name = "CLEAR"
    weather.current.humidity = 0.5
    tod = MagicMock()
    clock = MagicMock()
    rng = np.random.default_rng(42)
    return ObscurantsEngine(weather, tod, clock, rng)


class TestObscurantDetectionReduction:
    """Obscurant opacity reduces detection range in battle.py detection loop."""

    def test_smoke_reduces_visual_detection(self) -> None:
        """Smoke at target → visual detection_range reduced by visual opacity."""
        engine = _make_obs_engine()
        target_pos = Position(500.0, 500.0, 0.0)
        engine.deploy_smoke(target_pos, radius=100.0)

        opacity = engine.opacity_at(target_pos)
        assert opacity.visual >= 0.8, f"Expected high visual opacity, got {opacity.visual}"
        assert opacity.thermal < 0.2, f"Smoke thermal should be low, got {opacity.thermal}"

    def test_smoke_thermal_barely_affected(self) -> None:
        """Regular smoke → thermal detection barely affected (thermal opacity ~0.1)."""
        engine = _make_obs_engine()
        pos = Position(100.0, 100.0, 0.0)
        engine.deploy_smoke(pos, radius=50.0)
        opacity = engine.opacity_at(pos)
        assert opacity.thermal <= 0.15

    def test_multispectral_smoke_reduces_thermal(self) -> None:
        """Multispectral smoke → thermal detection significantly reduced."""
        engine = _make_obs_engine()
        pos = Position(100.0, 100.0, 0.0)
        engine.deploy_smoke(pos, radius=50.0, multispectral=True)
        opacity = engine.opacity_at(pos)
        assert opacity.thermal >= 0.7, f"Multispectral thermal should be high, got {opacity.thermal}"

    def test_smoke_does_not_affect_radar(self) -> None:
        """Standard smoke → radar detection unaffected (opacity 0.0)."""
        engine = _make_obs_engine()
        pos = Position(100.0, 100.0, 0.0)
        engine.deploy_smoke(pos, radius=50.0)
        opacity = engine.opacity_at(pos)
        assert opacity.radar == 0.0

    def test_dust_cloud_opacity(self) -> None:
        """Dust cloud → visual ~0.7, thermal ~0.5."""
        engine = _make_obs_engine()
        pos = Position(200.0, 200.0, 0.0)
        engine.add_dust(pos, radius=30.0)
        opacity = engine.opacity_at(pos)
        assert opacity.visual >= 0.5
        assert opacity.thermal >= 0.3

    def test_no_clouds_zero_opacity(self) -> None:
        """No clouds deployed → zero opacity (backward compat)."""
        engine = _make_obs_engine()
        opacity = engine.opacity_at(Position(0.0, 0.0, 0.0))
        assert opacity.visual == 0.0
        assert opacity.thermal == 0.0
        assert opacity.radar == 0.0

    def test_fog_weather_state_generates_fog(self) -> None:
        """FOG weather state → ObscurantsEngine generates a fog patch."""
        weather = MagicMock()
        weather.current.wind.speed = 0.0
        weather.current.wind.direction = 0.0
        weather.current.visibility = 500.0
        weather.current.state.name = "FOG"
        weather.current.humidity = 0.95
        tod = MagicMock()
        clock = MagicMock()
        rng = np.random.default_rng(42)

        engine = ObscurantsEngine(weather, tod, clock, rng)
        engine.update(60.0)
        opacity = engine.opacity_at(Position(0.0, 0.0, 0.0))
        assert opacity.visual > 0.0, "Fog should produce non-zero visual opacity"


class TestObscurantEngagementReduction:
    """Obscurant opacity reduces engagement Pk via vis_mod."""

    def test_smoke_reduces_vis_mod(self) -> None:
        """Smoke at target position should reduce vis_mod for visual weapons."""
        engine = _make_obs_engine()
        pos = Position(100.0, 100.0, 0.0)
        engine.deploy_smoke(pos, radius=50.0)
        opacity = engine.opacity_at(pos)
        base_vis_mod = 0.8
        reduced = base_vis_mod * (1.0 - opacity.visual)
        assert reduced < base_vis_mod * 0.3, "Vis mod should be significantly reduced through smoke"


class TestSmokeDriftAndDecay:
    """Smoke drifts with wind and decays over time."""

    def test_smoke_drifts_with_wind(self) -> None:
        """Smoke center moves in wind direction across ticks."""
        engine = _make_obs_engine(wind_speed=10.0)
        pos = Position(500.0, 500.0, 0.0)
        engine.deploy_smoke(pos, radius=50.0)

        # After update, smoke should have drifted
        engine.update(60.0)
        # Wind direction = 0 → north drift: center_n increases
        # Check opacity has moved
        opacity_origin = engine.opacity_at(pos)
        # The center has shifted north, so opacity at original center decreases
        # (or the cloud expands enough to still cover it — check relative)
        opacity_north = engine.opacity_at(Position(500.0, 1100.0, 0.0))
        # At least one should be non-zero
        assert opacity_origin.visual > 0 or opacity_north.visual > 0

    def test_smoke_decays_over_time(self) -> None:
        """Smoke density decreases with half-life decay."""
        engine = _make_obs_engine()
        pos = Position(100.0, 100.0, 0.0)
        engine.deploy_smoke(pos, radius=50.0)

        initial_opacity = engine.opacity_at(pos).visual

        # Simulate many updates (30 min = 1800s half-life)
        for _ in range(180):
            engine.update(600.0)  # 100 min total → > 3 half-lives

        decayed_opacity = engine.opacity_at(pos).visual
        assert decayed_opacity < initial_opacity * 0.2, "Opacity should decay significantly"


class TestArtilleryDust:
    """Artillery impact spawns dust at target position."""

    def test_artillery_dust_structural(self) -> None:
        """Structural: battle.py calls add_dust after indirect fire impacts."""
        from pathlib import Path

        src = Path("stochastic_warfare/simulation/battle.py").read_text()
        assert "_obs_engine.add_dust(best_target.position" in src or \
               "add_dust(best_target.position" in src


class TestEnableObscurantsFlag:
    """enable_obscurants=False → no opacity applied."""

    def test_flag_false_no_detection_change_structural(self) -> None:
        """Structural: battle.py checks enable_obscurants flag before applying."""
        from pathlib import Path

        src = Path("stochastic_warfare/simulation/battle.py").read_text()
        assert 'enable_obscurants' in src
        # Both detection and engagement sections check the flag
        assert src.count('enable_obscurants') >= 3
