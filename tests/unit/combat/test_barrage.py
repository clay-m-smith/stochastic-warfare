"""Unit tests for BarrageEngine — WW1 creeping/standing barrage."""

from __future__ import annotations

import pytest

from stochastic_warfare.combat.barrage import (
    BarrageConfig,
    BarrageEngine,
    BarrageType,
    BarrageZone,
)

from .conftest import _rng


def _make_engine(seed: int = 42, **cfg_kwargs) -> BarrageEngine:
    config = BarrageConfig(**cfg_kwargs) if cfg_kwargs else None
    return BarrageEngine(config=config, rng=_rng(seed))


# ---------------------------------------------------------------------------
# Create barrage
# ---------------------------------------------------------------------------


class TestCreateBarrage:
    """Barrage creation — STANDING vs CREEPING."""

    def test_standing_barrage_no_advance(self):
        eng = _make_engine()
        zone = eng.create_barrage(
            "b1", BarrageType.STANDING, "BLUE",
            center_easting=1000.0, center_northing=2000.0,
            fire_density=100.0, duration_s=600.0,
        )
        assert isinstance(zone, BarrageZone)
        assert zone.barrage_id == "b1"
        assert zone.barrage_type == BarrageType.STANDING
        assert zone.advance_rate_mps == pytest.approx(0.0)
        assert zone.active is True

    def test_creeping_barrage_has_advance_rate(self):
        eng = _make_engine()
        zone = eng.create_barrage(
            "b2", BarrageType.CREEPING, "BLUE",
            center_easting=1000.0, center_northing=2000.0,
            fire_density=80.0, duration_s=1200.0,
        )
        # Default advance rate: 0.833 m/s
        assert zone.advance_rate_mps == pytest.approx(0.833)


# ---------------------------------------------------------------------------
# Update — advance, drift, and expiry
# ---------------------------------------------------------------------------


class TestBarrageUpdate:
    """Barrage update: advance, drift, and expiry."""

    def test_creeping_advance_moves_center(self):
        """Creeping barrage moves center northward (heading=0)."""
        eng = _make_engine()
        zone = eng.create_barrage(
            "b1", BarrageType.CREEPING, "BLUE",
            center_easting=0.0, center_northing=0.0,
            fire_density=100.0, duration_s=600.0,
        )
        initial_n = zone.center_northing
        eng.update(dt_s=60.0)
        # 60s * 0.833 m/s = ~50m northward
        assert zone.center_northing > initial_n

    def test_drift_accumulates(self):
        """Drift grows with updates."""
        eng = _make_engine(seed=10)
        eng.create_barrage(
            "b1", BarrageType.STANDING, "BLUE",
            center_easting=0.0, center_northing=0.0,
            fire_density=100.0, duration_s=6000.0,
        )
        eng.update(dt_s=300.0)
        zone = eng.active_barrages[0]
        # After 5 minutes, drift should be nonzero (stochastic)
        assert zone.drift_easting_m != 0.0 or zone.drift_northing_m != 0.0

    def test_observer_correction_reduces_drift(self):
        """Observer-corrected barrage has smaller drift than uncorrected."""
        eng1 = _make_engine(seed=10)
        eng1.create_barrage(
            "b1", BarrageType.STANDING, "BLUE",
            center_easting=0.0, center_northing=0.0,
            fire_density=100.0, duration_s=6000.0,
            has_observer=True, observer_quality=1.0,
        )
        eng2 = _make_engine(seed=10)
        eng2.create_barrage(
            "b1", BarrageType.STANDING, "BLUE",
            center_easting=0.0, center_northing=0.0,
            fire_density=100.0, duration_s=6000.0,
            has_observer=False,
        )
        eng1.update(dt_s=300.0)
        eng2.update(dt_s=300.0)
        drift_obs = abs(eng1.active_barrages[0].drift_easting_m)
        drift_no = abs(eng2.active_barrages[0].drift_easting_m)
        assert drift_obs <= drift_no

    def test_barrage_expires(self):
        """Barrage deactivates after duration."""
        eng = _make_engine()
        eng.create_barrage(
            "b1", BarrageType.STANDING, "BLUE",
            center_easting=0.0, center_northing=0.0,
            fire_density=100.0, duration_s=60.0,
        )
        eng.update(dt_s=120.0)
        assert len(eng.active_barrages) == 0


# ---------------------------------------------------------------------------
# Compute effects
# ---------------------------------------------------------------------------


class TestBarrageEffects:
    """Effects at positions inside/outside the barrage."""

    def test_effects_inside_zone(self):
        eng = _make_engine()
        eng.create_barrage(
            "b1", BarrageType.STANDING, "BLUE",
            center_easting=0.0, center_northing=0.0,
            width_m=500.0, depth_m=200.0,
            fire_density=200.0, duration_s=3600.0,
        )
        effects = eng.compute_effects(0.0, 0.0)
        assert effects["suppression_p"] > 0.0
        assert effects["casualty_p"] > 0.0

    def test_effects_outside_zone(self):
        eng = _make_engine()
        eng.create_barrage(
            "b1", BarrageType.STANDING, "BLUE",
            center_easting=0.0, center_northing=0.0,
            width_m=500.0, depth_m=200.0,
            fire_density=200.0, duration_s=3600.0,
        )
        effects = eng.compute_effects(5000.0, 5000.0)
        assert effects["suppression_p"] == pytest.approx(0.0)
        assert effects["casualty_p"] == pytest.approx(0.0)

    def test_dugout_protection(self):
        """Dugout reduces casualty probability but not suppression."""
        eng = _make_engine()
        eng.create_barrage(
            "b1", BarrageType.STANDING, "BLUE",
            center_easting=0.0, center_northing=0.0,
            width_m=500.0, depth_m=200.0,
            fire_density=200.0, duration_s=3600.0,
        )
        exposed = eng.compute_effects(0.0, 0.0, in_dugout=False)
        dugout = eng.compute_effects(0.0, 0.0, in_dugout=True)
        # Same suppression
        assert dugout["suppression_p"] == pytest.approx(exposed["suppression_p"])
        # Reduced casualties
        assert dugout["casualty_p"] < exposed["casualty_p"]


# ---------------------------------------------------------------------------
# Friendly fire
# ---------------------------------------------------------------------------


class TestFriendlyFire:
    """Friendly fire risk for units near own barrage."""

    def test_friendly_in_zone_has_risk(self):
        eng = _make_engine()
        eng.create_barrage(
            "b1", BarrageType.STANDING, "BLUE",
            center_easting=100.0, center_northing=100.0,
        )
        risk = eng.check_friendly_fire(100.0, 100.0, "BLUE")
        assert risk > 0.0

    def test_enemy_no_friendly_fire(self):
        """Enemy units near own barrage have no friendly fire risk."""
        eng = _make_engine()
        eng.create_barrage(
            "b1", BarrageType.STANDING, "BLUE",
            center_easting=100.0, center_northing=100.0,
        )
        risk = eng.check_friendly_fire(100.0, 100.0, "RED")
        assert risk == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Active barrages property
# ---------------------------------------------------------------------------


class TestActiveBarrages:
    """active_barrages property."""

    def test_returns_only_active(self):
        eng = _make_engine()
        eng.create_barrage(
            "b1", BarrageType.STANDING, "BLUE", 0.0, 0.0,
            duration_s=60.0,
        )
        eng.create_barrage(
            "b2", BarrageType.STANDING, "RED", 100.0, 100.0,
            duration_s=60.0,
        )
        assert len(eng.active_barrages) == 2
        eng.update(dt_s=120.0)  # expires both
        assert len(eng.active_barrages) == 0


# ---------------------------------------------------------------------------
# State roundtrip
# ---------------------------------------------------------------------------


class TestBarrageStateRoundtrip:
    """State persistence."""

    def test_state_roundtrip(self):
        eng = _make_engine(seed=55)
        eng.create_barrage(
            "b1", BarrageType.STANDING, "BLUE",
            center_easting=100.0, center_northing=200.0,
            fire_density=50.0, duration_s=300.0,
            has_observer=True, observer_quality=0.8,
        )
        state = eng.get_state()
        eng2 = _make_engine(seed=1)
        eng2.set_state(state)
        assert len(eng2.active_barrages) == 1
        restored = eng2.active_barrages[0]
        assert restored.barrage_id == "b1"
        assert restored.has_observer is True
        assert restored.observer_quality == pytest.approx(0.8)
