"""Phase 17a tests — Orbital mechanics, constellations, SpaceConfig, SpaceEngine."""

from __future__ import annotations

import math

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.space.constellations import (
    ConstellationDefinition,
    ConstellationManager,
    ConstellationType,
    SpaceConfig,
    SpaceEngine,
)
from stochastic_warfare.space.events import (
    ConstellationDegradedEvent,
    GPSAccuracyChangedEvent,
    SatelliteOverpassEvent,
)
from stochastic_warfare.space.orbits import (
    MU_EARTH,
    R_EARTH,
    OrbitalElements,
    OrbitalMechanicsEngine,
    SatelliteState,
)

from tests.conftest import TS, make_rng


def _rng(seed: int = 42) -> np.random.Generator:
    return make_rng(seed)


def _bus() -> EventBus:
    return EventBus()


def _orbits() -> OrbitalMechanicsEngine:
    return OrbitalMechanicsEngine()


def _config(**kw) -> SpaceConfig:
    return SpaceConfig(enable_space=True, **kw)


def _gps_constellation(side: str = "blue") -> ConstellationDefinition:
    return ConstellationDefinition(
        constellation_id="gps_navstar",
        display_name="GPS NAVSTAR",
        constellation_type=int(ConstellationType.GPS),
        side=side,
        num_satellites=24,
        orbital_elements_template={
            "semi_major_axis_m": 26_559_700.0,
            "inclination_deg": 55.0,
        },
        plane_count=6,
        sats_per_plane=4,
    )


# ---------------------------------------------------------------------------
# TestOrbitalPeriod
# ---------------------------------------------------------------------------


class TestOrbitalPeriod:
    def test_leo_period(self) -> None:
        """LEO at ~400km altitude → ~92 min period."""
        eng = _orbits()
        a = R_EARTH + 400_000.0
        T = eng.orbital_period(a)
        assert 5400 < T < 5700  # ~92 min

    def test_meo_period(self) -> None:
        """GPS orbit at ~20200km → ~12 hr period."""
        eng = _orbits()
        a = 26_559_700.0  # GPS semi-major axis
        T = eng.orbital_period(a)
        assert 42000 < T < 44000  # ~12 hr

    def test_geo_period(self) -> None:
        """GEO at ~35786km → ~24 hr period."""
        eng = _orbits()
        a = 42_164_000.0  # GEO semi-major axis
        T = eng.orbital_period(a)
        assert 85000 < T < 87000  # ~23.93 hr sidereal day

    def test_known_value(self) -> None:
        """T = 2π√(a³/μ) for known values."""
        eng = _orbits()
        a = 7_000_000.0
        expected = 2.0 * math.pi * math.sqrt(a ** 3 / MU_EARTH)
        assert abs(eng.orbital_period(a) - expected) < 0.001


# ---------------------------------------------------------------------------
# TestKeplerSolver
# ---------------------------------------------------------------------------


class TestKeplerSolver:
    def test_circular_orbit(self) -> None:
        """e=0 → E=M."""
        eng = _orbits()
        M = 1.5
        E = eng.solve_kepler(M, 0.0)
        assert abs(E - M) < 1e-8

    def test_low_eccentricity(self) -> None:
        """e=0.01 converges quickly."""
        eng = _orbits()
        E = eng.solve_kepler(1.0, 0.01)
        # Verify: M = E - e*sin(E)
        M_check = E - 0.01 * math.sin(E)
        assert abs(M_check - 1.0) < 1e-8

    def test_high_eccentricity(self) -> None:
        """e=0.74 (Molniya) converges."""
        eng = _orbits()
        E = eng.solve_kepler(2.0, 0.74)
        M_check = E - 0.74 * math.sin(E)
        assert abs(M_check - 2.0) < 1e-8

    def test_convergence_zero_M(self) -> None:
        """M=0 → E=0 for any e."""
        eng = _orbits()
        E = eng.solve_kepler(0.0, 0.5)
        assert abs(E) < 1e-8


# ---------------------------------------------------------------------------
# TestJ2Precession
# ---------------------------------------------------------------------------


class TestJ2Precession:
    def test_sun_synchronous(self) -> None:
        """Sun-synchronous orbit (~98° inclination) has positive RAAN drift."""
        eng = _orbits()
        elems = OrbitalElements(
            semi_major_axis_m=R_EARTH + 800_000.0,
            inclination_deg=98.0,
        )
        sat = SatelliteState("test", "c1", elems, current_raan_deg=0.0)
        eng.propagate(sat, 86400.0)  # 1 day
        # At 98°, cos(i) < 0, so RAAN drift is positive (prograde)
        assert sat.current_raan_deg > 0.0

    def test_equatorial_no_precession(self) -> None:
        """Equatorial orbit (i=0) has max RAAN drift (cos(0)=1, retrograde)."""
        eng = _orbits()
        elems = OrbitalElements(
            semi_major_axis_m=R_EARTH + 800_000.0,
            inclination_deg=0.01,  # near-equatorial
        )
        sat = SatelliteState("test", "c1", elems, current_raan_deg=180.0)
        eng.propagate(sat, 86400.0)
        # cos(0) ≈ 1 → large negative drift
        assert sat.current_raan_deg < 180.0

    def test_polar_no_precession(self) -> None:
        """Polar orbit (i=90°) has zero RAAN drift."""
        eng = _orbits()
        elems = OrbitalElements(
            semi_major_axis_m=R_EARTH + 800_000.0,
            inclination_deg=90.0,
        )
        sat = SatelliteState("test", "c1", elems, current_raan_deg=100.0)
        eng.propagate(sat, 86400.0)
        assert abs(sat.current_raan_deg - 100.0) < 0.001


# ---------------------------------------------------------------------------
# TestSubsatellitePoint
# ---------------------------------------------------------------------------


class TestSubsatellitePoint:
    def test_equatorial(self) -> None:
        """Equatorial orbit at ν=0 → lat near 0."""
        eng = _orbits()
        elems = OrbitalElements(
            semi_major_axis_m=R_EARTH + 400_000.0,
            inclination_deg=0.0,
        )
        sat = SatelliteState("test", "c1", elems, current_true_anomaly_deg=0.0)
        lat, lon = eng.subsatellite_point(sat, 0.0)
        assert abs(lat) < 0.1

    def test_polar_orbit(self) -> None:
        """Polar orbit can reach high latitudes."""
        eng = _orbits()
        elems = OrbitalElements(
            semi_major_axis_m=R_EARTH + 400_000.0,
            inclination_deg=90.0,
        )
        sat = SatelliteState("test", "c1", elems, current_true_anomaly_deg=90.0)
        lat, lon = eng.subsatellite_point(sat, 0.0)
        assert abs(lat) > 80.0  # near pole

    def test_earth_rotation(self) -> None:
        """Different sim_time_s → different longitudes."""
        eng = _orbits()
        elems = OrbitalElements(
            semi_major_axis_m=R_EARTH + 400_000.0,
            inclination_deg=0.0,
        )
        sat = SatelliteState("test", "c1", elems, current_true_anomaly_deg=0.0)
        _, lon1 = eng.subsatellite_point(sat, 0.0)
        _, lon2 = eng.subsatellite_point(sat, 3600.0)
        assert lon1 != lon2


# ---------------------------------------------------------------------------
# TestVisibility
# ---------------------------------------------------------------------------


class TestVisibility:
    def test_above_horizon(self) -> None:
        """A satellite directly overhead should be visible."""
        eng = _orbits()
        elems = OrbitalElements(
            semi_major_axis_m=R_EARTH + 400_000.0,
            inclination_deg=0.0,
        )
        sat = SatelliteState("test", "c1", elems, current_true_anomaly_deg=0.0)
        # Subsatellite point at t=0 is near equator at some lon
        sub_lat, sub_lon = eng.subsatellite_point(sat, 0.0)
        assert eng.is_visible_from(sat, sub_lat, sub_lon, 0.0, 5.0)

    def test_below_horizon(self) -> None:
        """A LEO satellite should not be visible from a far-away ground point."""
        eng = _orbits()
        elems = OrbitalElements(
            semi_major_axis_m=R_EARTH + 400_000.0,
            inclination_deg=0.0,
        )
        sat = SatelliteState("test", "c1", elems, current_true_anomaly_deg=0.0)
        # LEO at 400km has a horizon of ~2300km ground distance
        # Testing from 90° lat (pole) with equatorial sat should be invisible
        assert not eng.is_visible_from(sat, 80.0, 0.0, 0.0, 5.0)

    def test_inactive_not_visible(self) -> None:
        """Inactive satellite is never visible."""
        eng = _orbits()
        elems = OrbitalElements(semi_major_axis_m=R_EARTH + 400_000.0)
        sat = SatelliteState("test", "c1", elems, is_active=False)
        assert not eng.is_visible_from(sat, 0.0, 0.0, 0.0, 5.0)


# ---------------------------------------------------------------------------
# TestConstellationSetup
# ---------------------------------------------------------------------------


class TestConstellationSetup:
    def test_gps_24_slot(self) -> None:
        """GPS constellation creates 24 satellites across 6 planes."""
        cm = ConstellationManager(_orbits(), _bus(), _rng())
        cm.add_constellation(_gps_constellation())
        assert cm.active_count("gps_navstar") == 24

    def test_distribute_planes(self) -> None:
        """Satellites are distributed across planes with correct RAAN spacing."""
        cm = ConstellationManager(_orbits(), _bus(), _rng())
        cm.add_constellation(_gps_constellation())
        sats = cm.all_satellites()
        raans = sorted({s.current_raan_deg for s in sats})
        assert len(raans) == 6  # 6 orbital planes
        # Check ~60° spacing
        for i in range(1, len(raans)):
            diff = raans[i] - raans[i - 1]
            assert abs(diff - 60.0) < 0.1

    def test_health_fraction(self) -> None:
        """health_fraction returns 1.0 for full constellation."""
        cm = ConstellationManager(_orbits(), _bus(), _rng())
        cm.add_constellation(_gps_constellation())
        assert cm.health_fraction("gps_navstar") == 1.0

    def test_degrade(self) -> None:
        """Degrade removes satellites and reduces active count."""
        cm = ConstellationManager(_orbits(), _bus(), _rng())
        cm.add_constellation(_gps_constellation())
        killed = cm.degrade_constellation("gps_navstar", 4, "asat_kinetic", TS)
        assert len(killed) == 4
        assert cm.active_count("gps_navstar") == 20
        assert cm.health_fraction("gps_navstar") == pytest.approx(20.0 / 24.0)


# ---------------------------------------------------------------------------
# TestConstellationQuery
# ---------------------------------------------------------------------------


class TestConstellationQuery:
    def test_visible_at_time(self) -> None:
        """At least some GPS sats are visible from any point at any time."""
        cfg = _config(theater_lat=33.0, theater_lon=35.0)
        cm = ConstellationManager(_orbits(), _bus(), _rng(), cfg)
        cm.add_constellation(_gps_constellation())
        # Propagate a bit
        cm.update(3600.0, 3600.0)
        visible = cm.visible_satellites("gps_navstar", 33.0, 35.0, 3600.0, 5.0)
        # GPS constellation should generally have 6-12 sats visible
        assert len(visible) >= 1

    def test_by_type(self) -> None:
        """get_constellations_by_type filters correctly."""
        cm = ConstellationManager(_orbits(), _bus(), _rng())
        cm.add_constellation(_gps_constellation())
        gps = cm.get_constellations_by_type(ConstellationType.GPS)
        assert len(gps) == 1
        assert gps[0].constellation_id == "gps_navstar"

    def test_by_side(self) -> None:
        """get_constellations_by_side filters correctly."""
        cm = ConstellationManager(_orbits(), _bus(), _rng())
        cm.add_constellation(_gps_constellation("blue"))
        blue = cm.get_constellations_by_side("blue")
        red = cm.get_constellations_by_side("red")
        assert len(blue) == 1
        assert len(red) == 0


# ---------------------------------------------------------------------------
# TestConstellationState
# ---------------------------------------------------------------------------


class TestConstellationState:
    def test_roundtrip(self) -> None:
        """get_state/set_state roundtrip preserves satellite states."""
        cm = ConstellationManager(_orbits(), _bus(), _rng())
        cm.add_constellation(_gps_constellation())
        cm.degrade_constellation("gps_navstar", 2, "test")
        state = cm.get_state()

        cm2 = ConstellationManager(_orbits(), _bus(), _rng())
        cm2.add_constellation(_gps_constellation())
        cm2.set_state(state)
        assert cm2.active_count("gps_navstar") == 22

    def test_propagation_determinism(self) -> None:
        """Two identical managers produce same state after propagation."""
        cm1 = ConstellationManager(_orbits(), _bus(), _rng(99))
        cm1.add_constellation(_gps_constellation())
        cm1.update(3600.0, 3600.0)

        cm2 = ConstellationManager(_orbits(), _bus(), _rng(99))
        cm2.add_constellation(_gps_constellation())
        cm2.update(3600.0, 3600.0)

        s1 = cm1.get_state()
        s2 = cm2.get_state()
        for sid in s1["satellites"]:
            assert abs(s1["satellites"][sid]["true_anomaly_deg"]
                       - s2["satellites"][sid]["true_anomaly_deg"]) < 1e-6

    def test_get_satellite(self) -> None:
        """get_satellite returns specific satellite by ID."""
        cm = ConstellationManager(_orbits(), _bus(), _rng())
        cm.add_constellation(_gps_constellation())
        sat = cm.get_satellite("gps_navstar_p0_s0")
        assert sat is not None
        assert sat.constellation_id == "gps_navstar"


# ---------------------------------------------------------------------------
# TestSpaceConfig
# ---------------------------------------------------------------------------


class TestSpaceConfig:
    def test_defaults(self) -> None:
        cfg = SpaceConfig()
        assert cfg.enable_space is False
        assert cfg.gps_sigma_range_m == 3.0
        assert cfg.update_interval_s == 3600.0

    def test_enable_flag(self) -> None:
        cfg = SpaceConfig(enable_space=True)
        assert cfg.enable_space is True

    def test_model_dump(self) -> None:
        cfg = SpaceConfig(enable_space=True, theater_lat=33.0)
        d = cfg.model_dump()
        restored = SpaceConfig.model_validate(d)
        assert restored.theater_lat == 33.0


# ---------------------------------------------------------------------------
# TestEvents
# ---------------------------------------------------------------------------


class TestEvents:
    def test_creation(self) -> None:
        evt = GPSAccuracyChangedEvent(
            timestamp=TS, source=ModuleId.SPACE,
            side="blue", previous_accuracy_m=3.6,
            new_accuracy_m=12.0, visible_satellites=12, dop=2.0,
        )
        assert evt.side == "blue"

    def test_eventbus_publish(self) -> None:
        bus = _bus()
        received = []
        bus.subscribe(ConstellationDegradedEvent, received.append)
        bus.publish(ConstellationDegradedEvent(
            timestamp=TS, source=ModuleId.SPACE,
            constellation_id="gps", previous_count=24, new_count=20, cause="test",
        ))
        assert len(received) == 1

    def test_frozen(self) -> None:
        evt = SatelliteOverpassEvent(
            timestamp=TS, source=ModuleId.SPACE,
            satellite_id="s1", constellation_id="c1", side="blue",
            overpass_start=True, coverage_center_x=0.0, coverage_center_y=0.0,
            coverage_radius_m=100.0, resolution_m=1.0,
        )
        with pytest.raises(AttributeError):
            evt.satellite_id = "s2"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestSpaceEngine
# ---------------------------------------------------------------------------


class TestSpaceEngine:
    def test_update_delegates(self) -> None:
        """SpaceEngine.update propagates constellations."""
        cfg = _config()
        cm = ConstellationManager(_orbits(), _bus(), _rng(), cfg)
        cm.add_constellation(_gps_constellation())
        se = SpaceEngine(cfg, cm)
        # Should not raise
        se.update(3600.0, 3600.0)

    def test_state_roundtrip(self) -> None:
        cfg = _config()
        cm = ConstellationManager(_orbits(), _bus(), _rng(), cfg)
        cm.add_constellation(_gps_constellation())
        se = SpaceEngine(cfg, cm)
        se.update(3600.0, 3600.0)
        state = se.get_state()
        assert "constellation_manager" in state
