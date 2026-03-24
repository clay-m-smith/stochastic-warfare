"""Phase 17b tests — GPS dependency and navigation warfare."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.space.constellations import (
    ConstellationDefinition,
    ConstellationManager,
    ConstellationType,
    SpaceConfig,
)
from stochastic_warfare.space.gps import GPSEngine, GPSFixQuality, GPSState
from stochastic_warfare.space.orbits import OrbitalMechanicsEngine

from tests.conftest import make_rng, make_clock


def _rng(seed: int = 42) -> np.random.Generator:
    return make_rng(seed)


def _bus() -> EventBus:
    return EventBus()


def _config(**kw) -> SpaceConfig:
    return SpaceConfig(enable_space=True, theater_lat=33.0, theater_lon=35.0, **kw)


def _setup_gps(side: str = "blue", num_sats: int = 24):
    """Create a GPS engine with a full GPS constellation."""
    orbits = OrbitalMechanicsEngine()
    bus = _bus()
    rng = _rng()
    cfg = _config()
    cm = ConstellationManager(orbits, bus, rng, cfg)
    cdef = ConstellationDefinition(
        constellation_id="gps_navstar",
        constellation_type=int(ConstellationType.GPS),
        side=side,
        num_satellites=num_sats,
        orbital_elements_template={"semi_major_axis_m": 26_559_700.0, "inclination_deg": 55.0},
        plane_count=6,
        sats_per_plane=max(1, num_sats // 6),
    )
    cm.add_constellation(cdef)
    gps = GPSEngine(cm, cfg, bus, rng)
    return gps, cm


# ---------------------------------------------------------------------------
# TestDOPComputation
# ---------------------------------------------------------------------------


class TestDOPComputation:
    def test_24_sats_low_dop(self) -> None:
        """Full GPS constellation → low HDOP."""
        gps, cm = _setup_gps()
        hdop = gps._compute_hdop(24)
        assert hdop < 1.5

    def test_12_sats_moderate_dop(self) -> None:
        hdop = GPSEngine._compute_hdop(None, 12)
        assert 1.0 <= hdop <= 2.0

    def test_4_sats_high_dop(self) -> None:
        hdop = GPSEngine._compute_hdop(None, 4)
        assert hdop >= 3.0

    def test_3_sats_denied(self) -> None:
        """<4 sats → DOP = 99 (no fix)."""
        hdop = GPSEngine._compute_hdop(None, 3)
        assert hdop == 99.0

    def test_known_formula(self) -> None:
        """HDOP = max(1.0, 6.0 / max(visible - 3, 1)) for 8 sats."""
        hdop = GPSEngine._compute_hdop(None, 8)
        expected = max(1.0, 6.0 / max(8 - 3, 1))
        assert abs(hdop - expected) < 1e-6


# ---------------------------------------------------------------------------
# TestGPSAccuracy
# ---------------------------------------------------------------------------


class TestGPSAccuracy:
    def test_full_accuracy(self) -> None:
        """Full constellation → accuracy ≈ DOP × sigma_range."""
        gps, _ = _setup_gps()
        state = gps.compute_gps_accuracy("blue", 0.0)
        # With 24 sats, no actual visibility check needed (falls back to 24)
        assert state.position_accuracy_m < 10.0

    def test_no_constellation_defaults(self) -> None:
        """Side with no GPS constellation → assumes 24 sats (full GPS)."""
        gps, _ = _setup_gps("blue")
        state = gps.compute_gps_accuracy("red", 0.0)
        assert state.visible_count == 24

    def test_degraded_constellation(self) -> None:
        """Degrading constellation increases accuracy error."""
        gps, cm = _setup_gps()
        state_full = gps.compute_gps_accuracy("blue", 0.0)
        cm.degrade_constellation("gps_navstar", 12, "test")
        state_deg = gps.compute_gps_accuracy("blue", 0.0)
        # Fewer sats → higher DOP → worse accuracy (higher number)
        assert state_deg.position_accuracy_m >= state_full.position_accuracy_m

    def test_denied(self) -> None:
        """All sats destroyed → DENIED quality."""
        gps, cm = _setup_gps()
        cm.degrade_constellation("gps_navstar", 24, "test")
        state = gps.compute_gps_accuracy("blue", 0.0)
        assert state.fix_quality == int(GPSFixQuality.DENIED)


# ---------------------------------------------------------------------------
# TestINSDrift
# ---------------------------------------------------------------------------


class TestINSDrift:
    def test_zero_time(self) -> None:
        gps, _ = _setup_gps()
        drift = gps.compute_ins_drift(0.0)
        assert drift == pytest.approx(10.0)  # initial sigma

    def test_one_hour(self) -> None:
        gps, _ = _setup_gps()
        drift = gps.compute_ins_drift(3600.0)
        expected = 10.0 + 0.514 * 3600.0
        assert drift == pytest.approx(expected)

    def test_linear_growth(self) -> None:
        gps, _ = _setup_gps()
        d1 = gps.compute_ins_drift(1000.0)
        d2 = gps.compute_ins_drift(2000.0)
        # Linear: d2 - d1 ≈ drift_rate × 1000
        assert abs((d2 - d1) - 0.514 * 1000.0) < 0.01

    def test_rate_scaling(self) -> None:
        cfg = _config(ins_drift_rate_m_per_s=1.0)
        orbits = OrbitalMechanicsEngine()
        cm = ConstellationManager(orbits, _bus(), _rng(), cfg)
        gps = GPSEngine(cm, cfg, _bus(), _rng())
        drift = gps.compute_ins_drift(100.0)
        assert drift == pytest.approx(10.0 + 1.0 * 100.0)


# ---------------------------------------------------------------------------
# TestCEPFactor
# ---------------------------------------------------------------------------


class TestCEPFactor:
    def test_gps_guided_scales(self) -> None:
        gps, _ = _setup_gps()
        factor = gps.compute_cep_factor(50.0, "gps")
        assert factor == pytest.approx(10.0)  # 50/5 = 10

    def test_ins_only_floor(self) -> None:
        gps, _ = _setup_gps()
        factor = gps.compute_cep_factor(2.0, "gps")
        assert factor == 1.0  # min(1.0, 2/5) → max(1, 0.4) = 1.0

    def test_non_gps_unaffected(self) -> None:
        gps, _ = _setup_gps()
        factor = gps.compute_cep_factor(50.0, "inertial")
        assert factor == 1.0

    def test_denied_large_factor(self) -> None:
        gps, _ = _setup_gps()
        factor = gps.compute_cep_factor(99.0 * 3.0, "gps_ins")  # 297m / 5 = 59.4
        assert factor > 50.0


# ---------------------------------------------------------------------------
# TestFixQuality
# ---------------------------------------------------------------------------


class TestFixQuality:
    def test_full(self) -> None:
        gps, _ = _setup_gps()
        assert gps._classify_fix(24) == GPSFixQuality.FULL

    def test_marginal(self) -> None:
        gps, _ = _setup_gps()
        assert gps._classify_fix(6) == GPSFixQuality.MARGINAL

    def test_denied(self) -> None:
        gps, _ = _setup_gps()
        assert gps._classify_fix(2) == GPSFixQuality.DENIED


# ---------------------------------------------------------------------------
# TestEMIntegration
# ---------------------------------------------------------------------------


class TestEMIntegration:
    def test_set_constellation_accuracy(self) -> None:
        """EMEnvironment.set_constellation_accuracy changes gps_accuracy()."""
        from stochastic_warfare.environment.electromagnetic import EMEnvironment
        from stochastic_warfare.environment.weather import WeatherEngine

        clock = make_clock()
        from stochastic_warfare.environment.weather import WeatherConfig
        weather = WeatherEngine(WeatherConfig(), clock, _rng())
        em = EMEnvironment(weather, None, clock)

        # Default: constellation_accuracy_m = 0 → falls back to 5.0
        base = em.gps_accuracy()
        assert base >= 5.0

        em.set_constellation_accuracy(15.0)
        degraded = em.gps_accuracy()
        assert degraded >= 15.0

    def test_zero_falls_back(self) -> None:
        from stochastic_warfare.environment.electromagnetic import EMEnvironment
        from stochastic_warfare.environment.weather import WeatherEngine

        clock = make_clock()
        from stochastic_warfare.environment.weather import WeatherConfig
        weather = WeatherEngine(WeatherConfig(), clock, _rng())
        em = EMEnvironment(weather, None, clock)

        em.set_constellation_accuracy(0.0)
        # Should fall back to 5.0 base
        assert em.gps_accuracy() >= 5.0

    def test_stacks_with_ew(self) -> None:
        """Constellation accuracy + EW jamming degradation stack."""
        from stochastic_warfare.environment.electromagnetic import EMEnvironment
        from stochastic_warfare.environment.weather import WeatherEngine

        clock = make_clock()
        from stochastic_warfare.environment.weather import WeatherConfig
        weather = WeatherEngine(WeatherConfig(), clock, _rng())
        em = EMEnvironment(weather, None, clock)

        em.set_constellation_accuracy(10.0)
        em.set_gps_jam_degradation(5.0)
        # 10.0 + 5.0 = 15.0 (minimum)
        assert em.gps_accuracy() >= 15.0


# ---------------------------------------------------------------------------
# TestGPSState
# ---------------------------------------------------------------------------


class TestGPSState:
    def test_roundtrip(self) -> None:
        gps, _ = _setup_gps()
        gps.update(3600.0, 3600.0)
        state = gps.get_state()
        gps2, _ = _setup_gps()
        gps2.set_state(state)
        assert gps2.get_state() == state

    def test_model(self) -> None:
        s = GPSState(visible_count=12, hdop=2.0, position_accuracy_m=6.0, fix_quality=1)
        assert s.fix_quality == 1
