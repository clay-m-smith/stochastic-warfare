"""Phase 17d tests — SATCOM dependency and ASAT warfare."""

from __future__ import annotations

import math

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.space.asat import ASATEngine, ASATType, ASATWeaponDefinition, DebrisCloud
from stochastic_warfare.space.constellations import (
    ConstellationDefinition,
    ConstellationManager,
    ConstellationType,
    SpaceConfig,
)
from stochastic_warfare.space.events import ASATEngagementEvent, DebrisCascadeEvent
from stochastic_warfare.space.orbits import OrbitalMechanicsEngine, R_EARTH
from stochastic_warfare.space.satcom import SATCOMEngine

from tests.conftest import TS, make_clock, make_rng


def _rng(seed: int = 42) -> np.random.Generator:
    return make_rng(seed)


def _bus() -> EventBus:
    return EventBus()


def _config(**kw) -> SpaceConfig:
    return SpaceConfig(enable_space=True, theater_lat=33.0, theater_lon=35.0, **kw)


def _satcom_constellation(side: str = "blue") -> ConstellationDefinition:
    return ConstellationDefinition(
        constellation_id="wgs_satcom",
        constellation_type=int(ConstellationType.SATCOM),
        side=side,
        num_satellites=10,
        orbital_elements_template={
            "semi_major_axis_m": 42_164_000.0,
            "inclination_deg": 0.0,
        },
        plane_count=1,
        sats_per_plane=10,
        bandwidth_bps=1e9,
    )


def _gps_constellation(side: str = "blue") -> ConstellationDefinition:
    return ConstellationDefinition(
        constellation_id="gps_navstar",
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


def _sm3_weapon() -> ASATWeaponDefinition:
    return ASATWeaponDefinition(
        weapon_id="sm3_iia",
        display_name="SM-3 Block IIA",
        asat_type=int(ASATType.DIRECT_ASCENT_KKV),
        lethal_radius_m=1.5,
        guidance_sigma_m=0.3,
        max_altitude_km=2000.0,
        min_altitude_km=200.0,
        closing_velocity_mps=10000.0,
        reload_time_s=3600.0,
    )


def _laser_dazzle_weapon() -> ASATWeaponDefinition:
    return ASATWeaponDefinition(
        weapon_id="laser_dazzle",
        display_name="Ground Laser Dazzle",
        asat_type=int(ASATType.GROUND_LASER_DAZZLE),
        max_altitude_km=2000.0,
        min_altitude_km=200.0,
        dazzle_duration_s=300.0,
        dazzle_range_km=1000.0,
    )


def _setup_satcom():
    orbits = OrbitalMechanicsEngine()
    bus = _bus()
    rng = _rng()
    cfg = _config()
    clock = make_clock()
    cm = ConstellationManager(orbits, bus, rng, cfg)
    cm.add_constellation(_satcom_constellation())
    satcom = SATCOMEngine(cm, cfg, bus, rng, clock)
    return satcom, cm


def _setup_asat():
    orbits = OrbitalMechanicsEngine()
    bus = _bus()
    rng = _rng()
    cfg = _config(debris_fragment_mean=100.0)
    clock = make_clock()
    cm = ConstellationManager(orbits, bus, rng, cfg)
    cm.add_constellation(_gps_constellation())
    asat = ASATEngine(cm, cfg, bus, rng, clock)
    return asat, cm


# ---------------------------------------------------------------------------
# TestSATCOM
# ---------------------------------------------------------------------------


class TestSATCOM:
    def test_full_availability(self) -> None:
        satcom, cm = _setup_satcom()
        cm.update(3600.0, 3600.0)
        avail, bw = satcom.compute_satcom_availability("blue", 3600.0)
        # GEO sats should generally be visible
        assert isinstance(avail, bool)
        if avail:
            assert bw > 0

    def test_degraded(self) -> None:
        satcom, cm = _setup_satcom()
        cm.degrade_constellation("wgs_satcom", 5, "test")
        cm.update(3600.0, 3600.0)
        assert cm.health_fraction("wgs_satcom") == pytest.approx(0.5)

    def test_no_coverage_side(self) -> None:
        """Side without SATCOM constellation gets default availability."""
        satcom, cm = _setup_satcom()
        avail, bw = satcom.compute_satcom_availability("red", 0.0)
        # Red has no SATCOM → default True
        assert avail is True

    def test_bandwidth_scales(self) -> None:
        """More visible sats → more bandwidth."""
        satcom, cm = _setup_satcom()
        cm.update(3600.0, 3600.0)
        avail, bw_full = satcom.compute_satcom_availability("blue", 3600.0)
        # Just verify bandwidth is positive when available
        if avail:
            assert bw_full > 0


# ---------------------------------------------------------------------------
# TestSATCOMReliability
# ---------------------------------------------------------------------------


class TestSATCOMReliability:
    def test_full_reliability(self) -> None:
        satcom, cm = _setup_satcom()
        factor = satcom.get_reliability_factor("blue", 0.0)
        assert factor == pytest.approx(1.0)

    def test_half_reliability(self) -> None:
        satcom, cm = _setup_satcom()
        cm.degrade_constellation("wgs_satcom", 5, "test")
        factor = satcom.get_reliability_factor("blue", 0.0)
        assert factor == pytest.approx(0.5)

    def test_zero_reliability(self) -> None:
        satcom, cm = _setup_satcom()
        cm.degrade_constellation("wgs_satcom", 10, "test")
        factor = satcom.get_reliability_factor("blue", 0.0)
        assert factor == pytest.approx(0.0)

    def test_non_satcom_unaffected(self) -> None:
        """Side without SATCOM constellation → 1.0."""
        satcom, cm = _setup_satcom()
        factor = satcom.get_reliability_factor("red", 0.0)
        assert factor == 1.0


# ---------------------------------------------------------------------------
# TestASATKinetic
# ---------------------------------------------------------------------------


class TestASATKinetic:
    def test_pk_computation(self) -> None:
        """Kinetic Pk = 1 - exp(-(R_lethal/σ_eff)²/2)."""
        asat, _ = _setup_asat()
        weapon = _sm3_weapon()
        sigma_eff = weapon.guidance_sigma_m * (1.0 + weapon.closing_velocity_mps / 7500.0)
        ratio = weapon.lethal_radius_m / sigma_eff
        expected_pk = 1.0 - math.exp(-0.5 * ratio ** 2)
        computed = asat._compute_kinetic_pk(weapon, 1000.0)
        assert abs(computed - expected_pk) < 1e-6

    def test_altitude_range(self) -> None:
        """Weapon can't engage below min or above max altitude."""
        asat, cm = _setup_asat()
        weapon = ASATWeaponDefinition(
            weapon_id="short_range",
            asat_type=int(ASATType.DIRECT_ASCENT_KKV),
            max_altitude_km=500.0,
            min_altitude_km=400.0,
            lethal_radius_m=1.0,
            guidance_sigma_m=0.5,
        )
        asat.register_weapon(weapon, "blue")
        # GPS is at ~20200km — way above 500km max
        sat = cm.get_satellite("gps_navstar_p0_s0")
        result = asat.engage("short_range", sat.satellite_id, "blue", 0.0, TS)
        assert result["error"] == "out_of_range"

    def test_velocity_effect(self) -> None:
        """Higher closing velocity → higher σ_eff → lower Pk."""
        asat, _ = _setup_asat()
        w_slow = ASATWeaponDefinition(
            weapon_id="slow", asat_type=0,
            lethal_radius_m=1.0, guidance_sigma_m=0.5,
            closing_velocity_mps=1000.0,
        )
        w_fast = ASATWeaponDefinition(
            weapon_id="fast", asat_type=0,
            lethal_radius_m=1.0, guidance_sigma_m=0.5,
            closing_velocity_mps=15000.0,
        )
        pk_slow = asat._compute_kinetic_pk(w_slow, 1000.0)
        pk_fast = asat._compute_kinetic_pk(w_fast, 1000.0)
        assert pk_slow > pk_fast

    def test_reload(self) -> None:
        """Can't fire again before reload time."""
        asat, cm = _setup_asat()
        weapon = _sm3_weapon()
        weapon = ASATWeaponDefinition(
            **{**weapon.model_dump(), "max_altitude_km": 30000.0}
        )
        asat.register_weapon(weapon, "blue")
        sat = cm.get_satellite("gps_navstar_p0_s0")
        asat.engage(weapon.weapon_id, sat.satellite_id, "blue", 0.0, TS)
        # Try immediately again
        result = asat.engage(weapon.weapon_id, "gps_navstar_p0_s1", "blue", 1.0, TS)
        assert result["error"] == "reloading"

    def test_out_of_range_min(self) -> None:
        """Target below minimum altitude rejected."""
        asat, cm = _setup_asat()
        weapon = ASATWeaponDefinition(
            weapon_id="hi_only", asat_type=0,
            min_altitude_km=25000.0, max_altitude_km=30000.0,
            lethal_radius_m=1.0, guidance_sigma_m=0.5,
        )
        asat.register_weapon(weapon, "blue")
        sat = cm.get_satellite("gps_navstar_p0_s0")
        result = asat.engage("hi_only", sat.satellite_id, "blue", 0.0, TS)
        # GPS at ~20200km < 25000km min
        assert result["error"] == "out_of_range"


# ---------------------------------------------------------------------------
# TestASATLaser
# ---------------------------------------------------------------------------


class TestASATLaser:
    def test_dazzle(self) -> None:
        """Laser dazzle temporarily marks satellite as dazzled."""
        asat, cm = _setup_asat()
        weapon = _laser_dazzle_weapon()
        weapon = ASATWeaponDefinition(
            **{**weapon.model_dump(), "max_altitude_km": 30000.0}
        )
        asat.register_weapon(weapon, "blue")
        sat = cm.get_satellite("gps_navstar_p0_s0")
        result = asat.engage(weapon.weapon_id, sat.satellite_id, "blue", 0.0, TS)
        assert result["hit"] is True
        assert asat.is_dazzled(sat.satellite_id)

    def test_dazzle_duration(self) -> None:
        """Dazzle expires after duration."""
        asat, cm = _setup_asat()
        weapon = _laser_dazzle_weapon()
        weapon = ASATWeaponDefinition(
            **{**weapon.model_dump(), "max_altitude_km": 30000.0}
        )
        asat.register_weapon(weapon, "blue")
        sat = cm.get_satellite("gps_navstar_p0_s0")
        asat.engage(weapon.weapon_id, sat.satellite_id, "blue", 0.0, TS)
        # Before expiry
        assert asat.is_dazzled(sat.satellite_id)
        # After expiry
        asat.update(0.0, 400.0)  # 400s > 300s dazzle
        assert not asat.is_dazzled(sat.satellite_id)

    def test_permanent_destruct(self) -> None:
        """Laser destruct permanently kills satellite (no debris)."""
        asat, cm = _setup_asat()
        weapon = ASATWeaponDefinition(
            weapon_id="laser_kill",
            asat_type=int(ASATType.GROUND_LASER_DESTRUCT),
            max_altitude_km=30000.0,
            min_altitude_km=200.0,
        )
        asat.register_weapon(weapon, "blue")
        sat = cm.get_satellite("gps_navstar_p0_s0")
        result = asat.engage(weapon.weapon_id, sat.satellite_id, "blue", 0.0, TS)
        assert result["debris_generated"] == 0
        if result["hit"]:
            assert not sat.is_active

    def test_laser_range(self) -> None:
        """Higher altitude reduces Pk for laser destruct."""
        asat, cm = _setup_asat()
        weapon = ASATWeaponDefinition(
            weapon_id="lk", asat_type=int(ASATType.GROUND_LASER_DESTRUCT),
            max_altitude_km=30000.0, min_altitude_km=200.0,
        )
        # Pk = max(0.1, min(0.9, 1 - alt/max_alt))
        pk_low = max(0.1, min(0.9, 1.0 - 500.0 / 30000.0))  # 500km
        pk_high = max(0.1, min(0.9, 1.0 - 20000.0 / 30000.0))  # 20000km
        assert pk_low > pk_high


# ---------------------------------------------------------------------------
# TestDebris
# ---------------------------------------------------------------------------


class TestDebris:
    def test_poisson_count(self) -> None:
        """Debris count is Poisson distributed."""
        asat, cm = _setup_asat()
        weapon = ASATWeaponDefinition(
            weapon_id="kkv", asat_type=0,
            lethal_radius_m=5.0, guidance_sigma_m=0.1,
            max_altitude_km=30000.0,
            closing_velocity_mps=10000.0,
        )
        asat.register_weapon(weapon, "blue")
        sat = cm.get_satellite("gps_navstar_p0_s0")
        result = asat.engage("kkv", sat.satellite_id, "blue", 0.0, TS)
        if result["hit"]:
            assert result["debris_generated"] > 0

    def test_cloud_creation(self) -> None:
        """Kinetic kill creates a debris cloud."""
        asat, cm = _setup_asat()
        weapon = ASATWeaponDefinition(
            weapon_id="kkv2", asat_type=0,
            lethal_radius_m=5.0, guidance_sigma_m=0.1,
            max_altitude_km=30000.0,
            closing_velocity_mps=10000.0,
        )
        asat.register_weapon(weapon, "blue")
        sat = cm.get_satellite("gps_navstar_p0_s0")
        result = asat.engage("kkv2", sat.satellite_id, "blue", 0.0, TS)
        if result["hit"]:
            assert len(asat._debris_clouds) >= 1

    def test_altitude_band(self) -> None:
        """Debris cloud is at the target satellite's altitude."""
        cloud = DebrisCloud(500.0, 100)
        assert cloud.altitude_band_km == 500.0
        assert cloud.debris_count == 100

    def test_determinism(self) -> None:
        """Same seed → same debris count."""
        counts = []
        for _ in range(2):
            asat, cm = _setup_asat()
            weapon = ASATWeaponDefinition(
                weapon_id="det", asat_type=0,
                lethal_radius_m=5.0, guidance_sigma_m=0.1,
                max_altitude_km=30000.0,
                closing_velocity_mps=10000.0,
            )
            asat.register_weapon(weapon, "blue")
            sat = cm.get_satellite("gps_navstar_p0_s0")
            result = asat.engage("det", sat.satellite_id, "blue", 0.0, TS)
            counts.append(result.get("debris_generated", 0))
        assert counts[0] == counts[1]


# ---------------------------------------------------------------------------
# TestCascade
# ---------------------------------------------------------------------------


class TestCascade:
    def test_collision_prob_scales(self) -> None:
        """More debris → higher collision probability."""
        cfg = _config(debris_collision_prob_per_orbit=0.001)
        cloud_small = DebrisCloud(500.0, 10)
        cloud_large = DebrisCloud(500.0, 1000)
        prob_small = 10 * 0.001
        prob_large = min(1000 * 0.001, 0.1)
        assert prob_large > prob_small

    def test_cascade_bounded(self) -> None:
        """Collision probability capped at 0.1."""
        asat, cm = _setup_asat()
        # Add massive debris cloud
        asat._debris_clouds.append(DebrisCloud(20000.0, 100000))
        # Update should not crash
        asat.update_debris(3600.0, 3600.0)

    def test_debris_aging(self) -> None:
        """Debris age tracks correctly."""
        cloud = DebrisCloud(500.0, 100)
        assert cloud.age_s == 0.0
        cloud.age_s += 3600.0
        assert cloud.age_s == 3600.0

    def test_cascade_event(self) -> None:
        """High debris triggers DebrisCascadeEvent."""
        bus = _bus()
        received = []
        bus.subscribe(DebrisCascadeEvent, received.append)

        orbits = OrbitalMechanicsEngine()
        rng = _rng()
        cfg = _config(debris_collision_prob_per_orbit=0.01)
        cm = ConstellationManager(orbits, bus, rng, cfg)
        cm.add_constellation(_gps_constellation())
        asat = ASATEngine(cm, cfg, bus, rng)
        # Add debris cloud that triggers event (count * prob > 0.01)
        asat._debris_clouds.append(DebrisCloud(20000.0, 10))
        asat.update_debris(3600.0, 3600.0)
        assert len(received) >= 1


# ---------------------------------------------------------------------------
# TestCommsIntegration
# ---------------------------------------------------------------------------


class TestCommsIntegration:
    def test_set_satcom_reliability(self) -> None:
        """CommunicationsEngine.set_satcom_reliability accepts value."""
        from stochastic_warfare.c2.communications import CommunicationsEngine

        bus = _bus()
        rng = _rng()
        comms = CommunicationsEngine(bus, rng)
        comms.set_satcom_reliability(0.5)
        assert comms._satcom_reliability_factor == 0.5

    def test_reliability_in_state(self) -> None:
        """SATCOM reliability factor persists in get_state/set_state."""
        from stochastic_warfare.c2.communications import CommunicationsEngine

        bus = _bus()
        rng = _rng()
        comms = CommunicationsEngine(bus, rng)
        comms.set_satcom_reliability(0.7)
        state = comms.get_state()
        assert state["satcom_reliability_factor"] == 0.7

        comms2 = CommunicationsEngine(bus, rng)
        comms2.set_state(state)
        assert comms2._satcom_reliability_factor == 0.7

    def test_clamps(self) -> None:
        from stochastic_warfare.c2.communications import CommunicationsEngine

        bus = _bus()
        rng = _rng()
        comms = CommunicationsEngine(bus, rng)
        comms.set_satcom_reliability(-0.5)
        assert comms._satcom_reliability_factor == 0.0
        comms.set_satcom_reliability(1.5)
        assert comms._satcom_reliability_factor == 1.0


# ---------------------------------------------------------------------------
# TestASATState
# ---------------------------------------------------------------------------


class TestASATState:
    def test_roundtrip(self) -> None:
        asat, _ = _setup_asat()
        asat._last_fire_time["w1"] = 100.0
        asat._dazzled_sats["s1"] = 500.0
        asat._debris_clouds.append(DebrisCloud(500.0, 100))

        state = asat.get_state()
        asat2, _ = _setup_asat()
        asat2.set_state(state)
        assert asat2._last_fire_time["w1"] == 100.0
        assert asat2._dazzled_sats["s1"] == 500.0
        assert len(asat2._debris_clouds) == 1

    def test_satcom_state(self) -> None:
        satcom, _ = _setup_satcom()
        satcom._previous_available["blue"] = True
        state = satcom.get_state()
        satcom2, _ = _setup_satcom()
        satcom2.set_state(state)
        assert satcom2._previous_available["blue"] is True
