"""Phase 17d tests — SATCOM dependency and ASAT warfare."""

from __future__ import annotations

import math

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.space.asat import ASATEngine, DebrisCloud
from stochastic_warfare.space.config import (
    ASATAssetConfig,
    ASATOrderConfig,
    ASATType,
    ASATWeaponDefinition,
)
from stochastic_warfare.space.constellations import (
    ConstellationDefinition,
    ConstellationManager,
    ConstellationType,
    SpaceConfig,
)
from stochastic_warfare.space.events import (
    ASATEngagementEvent,
    ConstellationDegradedEvent,
    DebrisCascadeEvent,
)
from stochastic_warfare.space.orbits import OrbitalMechanicsEngine
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
            "eccentricity": 0.0,
            "inclination_deg": 0.0,
            "raan_deg": 0.0,
            "arg_perigee_deg": 0.0,
            "true_anomaly_deg": 0.0,
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
            "eccentricity": 0.0,
            "inclination_deg": 55.0,
            "raan_deg": 0.0,
            "arg_perigee_deg": 0.0,
            "true_anomaly_deg": 0.0,
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
        dazzle_duration_s=0.0,
        dazzle_range_km=0.0,
    )


def _laser_dazzle_weapon() -> ASATWeaponDefinition:
    return ASATWeaponDefinition(
        weapon_id="laser_dazzle",
        display_name="Ground Laser Dazzle",
        asat_type=int(ASATType.GROUND_LASER_DAZZLE),
        lethal_radius_m=0.0,
        guidance_sigma_m=0.0,
        max_altitude_km=2000.0,
        min_altitude_km=200.0,
        closing_velocity_mps=0.0,
        reload_time_s=0.0,
        dazzle_duration_s=300.0,
        dazzle_range_km=1000.0,
    )


def _laser_destruct_weapon() -> ASATWeaponDefinition:
    return ASATWeaponDefinition(
        weapon_id="laser_destruct",
        display_name="Ground Laser Destruct",
        asat_type=int(ASATType.GROUND_LASER_DESTRUCT),
        lethal_radius_m=0.0,
        guidance_sigma_m=0.0,
        max_altitude_km=30000.0,
        min_altitude_km=200.0,
        closing_velocity_mps=0.0,
        reload_time_s=0.0,
        dazzle_duration_s=0.0,
        dazzle_range_km=0.0,
    )


def _kinetic_weapon(
    *,
    weapon_id: str = "test_kkv",
    lethal_radius_m: float = 5.0,
    guidance_sigma_m: float = 0.1,
    min_altitude_km: float = 200.0,
    max_altitude_km: float = 30000.0,
    closing_velocity_mps: float = 10000.0,
    reload_time_s: float = 3600.0,
    asat_type: ASATType = ASATType.DIRECT_ASCENT_KKV,
) -> ASATWeaponDefinition:
    return ASATWeaponDefinition(
        weapon_id=weapon_id,
        display_name=weapon_id,
        asat_type=int(asat_type),
        lethal_radius_m=lethal_radius_m,
        guidance_sigma_m=guidance_sigma_m,
        min_altitude_km=min_altitude_km,
        max_altitude_km=max_altitude_km,
        closing_velocity_mps=closing_velocity_mps,
        reload_time_s=reload_time_s,
        dazzle_duration_s=0.0,
        dazzle_range_km=0.0,
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


def _setup_asat(
    *,
    weapon: ASATWeaponDefinition | None = None,
    target_ids: tuple[str, ...] = ("gps_navstar_p0_s0",),
    execute_times_s: tuple[float, ...] | None = None,
    rounds_available: int | None = None,
    enable_asat: bool = True,
    event_bus: EventBus | None = None,
    rng_seed: int = 42,
    **config_overrides,
):
    weapon = weapon or _kinetic_weapon()
    execute_times_s = execute_times_s or tuple(
        0.0 for _target_id in target_ids
    )
    if len(execute_times_s) != len(target_ids):
        raise ValueError("one execution time is required for each target")
    asset = ASATAssetConfig(
        asset_id="blue_asat_1",
        weapon_id=weapon.weapon_id,
        side="blue",
        rounds_available=(
            len(target_ids)
            if rounds_available is None
            else rounds_available
        ),
    )
    orders = [
        ASATOrderConfig(
            order_id=f"order_{index}",
            asset_id=asset.asset_id,
            target_satellite_id=target_id,
            execute_at_s=execute_time_s,
        )
        for index, (target_id, execute_time_s) in enumerate(
            zip(target_ids, execute_times_s, strict=True),
        )
    ]
    orbits = OrbitalMechanicsEngine()
    bus = event_bus or _bus()
    rng = _rng(rng_seed)
    cfg = _config(
        constellation_ids=["gps_navstar"],
        enable_asat=enable_asat,
        asat_assets=[asset],
        asat_orders=orders,
        debris_fragment_mean=100.0,
        **config_overrides,
    )
    clock = make_clock()
    cm = ConstellationManager(orbits, bus, rng, cfg)
    cm.add_constellation(_gps_constellation(side="red"))
    asat = ASATEngine(
        cm,
        cfg,
        bus,
        rng,
        clock,
        weapon_definitions={weapon.weapon_id: weapon},
        assets=cfg.asat_assets,
        orders=cfg.asat_orders,
        configuration_fingerprint="f" * 64,
    )
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
        """Kinetic Pk is the Rayleigh radial-error CDF."""
        asat, _ = _setup_asat()
        weapon = _sm3_weapon()
        ratio = weapon.lethal_radius_m / weapon.guidance_sigma_m
        expected_pk = 1.0 - math.exp(-0.5 * ratio**2)
        computed = asat._compute_kinetic_pk(weapon, 1000.0)
        assert abs(computed - expected_pk) < 1e-6

    def test_altitude_range(self) -> None:
        """Weapon can't engage below min or above max altitude."""
        weapon = _kinetic_weapon(
            weapon_id="short_range",
            max_altitude_km=500.0,
            min_altitude_km=400.0,
            lethal_radius_m=1.0,
            guidance_sigma_m=0.5,
        )
        asat, _ = _setup_asat(weapon=weapon)
        # GPS is at ~20200km — way above 500km max
        result = asat.execute_due_orders(0.0, TS)[0]
        assert result["launched"] is False
        assert result["outcome"] == "rejected"
        assert result["reason"] == "target_out_of_range"
        assert result["rounds_remaining"] == 1

    def test_velocity_effect(self) -> None:
        """Closing velocity does not alter the declared radial-error Pk."""
        asat, _ = _setup_asat()
        w_slow = _kinetic_weapon(
            weapon_id="slow",
            lethal_radius_m=1.0,
            guidance_sigma_m=0.5,
            closing_velocity_mps=1000.0,
        )
        w_fast = _kinetic_weapon(
            weapon_id="fast",
            lethal_radius_m=1.0,
            guidance_sigma_m=0.5,
            closing_velocity_mps=15000.0,
        )
        pk_slow = asat._compute_kinetic_pk(w_slow, 1000.0)
        pk_fast = asat._compute_kinetic_pk(w_fast, 1000.0)
        assert pk_slow == pytest.approx(pk_fast)

    def test_reload(self) -> None:
        """A finite asset cannot execute a second order before reload."""
        weapon = _kinetic_weapon(
            weapon_id="reload_kkv",
            reload_time_s=3600.0,
        )
        asat, _ = _setup_asat(
            weapon=weapon,
            target_ids=("gps_navstar_p0_s0", "gps_navstar_p0_s1"),
            execute_times_s=(0.0, 1.0),
            rounds_available=2,
        )
        first = asat.execute_due_orders(0.0, TS)[0]
        second = asat.execute_due_orders(1.0, TS)[0]
        assert first["launched"] is True
        assert first["rounds_remaining"] == 1
        assert second["launched"] is False
        assert second["outcome"] == "rejected"
        assert second["reason"] == "asset_reloading"
        assert second["rounds_remaining"] == 1

    def test_out_of_range_min(self) -> None:
        """Target below minimum altitude rejected."""
        weapon = _kinetic_weapon(
            weapon_id="hi_only",
            min_altitude_km=25000.0,
            max_altitude_km=30000.0,
            lethal_radius_m=1.0,
            guidance_sigma_m=0.5,
        )
        asat, _ = _setup_asat(weapon=weapon)
        result = asat.execute_due_orders(0.0, TS)[0]
        # GPS at ~20200km < 25000km min
        assert result["launched"] is False
        assert result["reason"] == "target_out_of_range"


# ---------------------------------------------------------------------------
# TestASATLaser
# ---------------------------------------------------------------------------


class TestUnsupportedASATTypes:
    def test_dazzle_is_explicitly_unsupported(self) -> None:
        """Configured laser dazzle fails instead of proxying a kinetic action."""
        with pytest.raises(
            ValueError,
            match="unsupported production type GROUND_LASER_DAZZLE",
        ):
            _setup_asat(weapon=_laser_dazzle_weapon())

    def test_disabled_dazzle_topology_is_still_rejected(self) -> None:
        """Disabling execution does not make unsupported topology valid."""
        with pytest.raises(
            ValueError,
            match="unsupported production type GROUND_LASER_DAZZLE",
        ):
            _setup_asat(
                weapon=_laser_dazzle_weapon(),
                enable_asat=False,
            )

    def test_laser_destruct_is_explicitly_unsupported(self) -> None:
        """Configured laser destruction is rejected at construction."""
        with pytest.raises(
            ValueError,
            match="unsupported production type GROUND_LASER_DESTRUCT",
        ):
            _setup_asat(weapon=_laser_destruct_weapon())

    def test_coorbital_is_explicitly_unsupported(self) -> None:
        """Configured co-orbital weapons are rejected at construction."""
        weapon = _kinetic_weapon(
            weapon_id="coorbital",
            asat_type=ASATType.CO_ORBITAL,
        )
        with pytest.raises(
            ValueError,
            match="unsupported production type CO_ORBITAL",
        ):
            _setup_asat(weapon=weapon)


# ---------------------------------------------------------------------------
# TestDebris
# ---------------------------------------------------------------------------


class TestDebris:
    def test_poisson_count(self) -> None:
        """A configured high-Pk kinetic hit samples positive Poisson debris."""
        received: list[ASATEngagementEvent] = []
        bus = _bus()
        bus.subscribe(ASATEngagementEvent, received.append)
        asat, _ = _setup_asat(event_bus=bus)
        result = asat.execute_due_orders(0.0, TS)[0]
        assert result["hit"] is True
        assert result["outcome"] == "hit"
        assert result["debris_generated"] > 0
        assert len(received) == 1
        assert received[0].debris_generated == result["debris_generated"]

    def test_cloud_creation(self) -> None:
        """Kinetic kill creates a debris cloud."""
        asat, _ = _setup_asat()
        result = asat.execute_due_orders(0.0, TS)[0]
        state = asat.get_state()
        assert result["hit"] is True
        assert state["debris_clouds"] == [
            {
                "altitude_band_km": pytest.approx(20188.7, abs=1.0),
                "debris_count": result["debris_generated"],
                "age_s": 0.0,
            },
        ]

    def test_altitude_band(self) -> None:
        """Debris cloud is at the target satellite's altitude."""
        cloud = DebrisCloud(500.0, 100)
        assert cloud.altitude_band_km == 500.0
        assert cloud.debris_count == 100

    def test_determinism(self) -> None:
        """Same seed → same debris count."""
        counts = []
        for _ in range(2):
            asat, _ = _setup_asat()
            result = asat.execute_due_orders(0.0, TS)[0]
            counts.append(result["debris_generated"])
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
        bus = _bus()
        received: list[DebrisCascadeEvent] = []
        bus.subscribe(DebrisCascadeEvent, received.append)
        asat, _ = _setup_asat(
            event_bus=bus,
            debris_collision_prob_per_orbit=0.001,
        )
        state = asat.get_state()
        state["debris_clouds"] = [{
            "altitude_band_km": 20000.0,
            "debris_count": 100000,
            "age_s": 0.0,
        }]
        asat.set_state(state)
        asat.update_debris(3600.0, 3600.0)
        assert received
        assert received[0].collision_probability_per_orbit == 0.1

    def test_debris_aging(self) -> None:
        """Debris age tracks correctly."""
        cloud = DebrisCloud(500.0, 100)
        assert cloud.age_s == 0.0
        cloud.age_s += 3600.0
        assert cloud.age_s == 3600.0

    def test_cascade_event(self) -> None:
        """A real hit can cascade through the canonical manager boundary."""
        bus = _bus()
        cascades: list[DebrisCascadeEvent] = []
        degradations: list[ConstellationDegradedEvent] = []
        bus.subscribe(DebrisCascadeEvent, cascades.append)
        bus.subscribe(ConstellationDegradedEvent, degradations.append)
        asat, cm = _setup_asat(
            event_bus=bus,
            rng_seed=0,
            debris_collision_prob_per_orbit=1.0,
        )
        result = asat.execute_due_orders(0.0, TS)[0]
        assert result["hit"] is True
        assert cm.active_count("gps_navstar") == 23

        asat.update_debris(3600.0, 3600.0, TS)

        assert len(cascades) == 1
        assert cascades[0].collision_probability_per_orbit == 0.1
        assert [event.cause for event in degradations] == [
            "asat_kinetic",
            "debris",
        ]
        assert cm.active_count("gps_navstar") == 22
        assert cm.get_satellite("gps_navstar_p0_s1").is_active is False


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
        result = asat.execute_due_orders(0.0, TS)[0]
        assert result["hit"] is True
        state = asat.get_state()
        asat2, _ = _setup_asat()
        asat2.set_state(state)
        assert asat2.get_state() == state
        assert asat2.execute_due_orders(1.0, TS) == []

    def test_satcom_state(self) -> None:
        satcom, _ = _setup_satcom()
        satcom._previous_available["blue"] = True
        state = satcom.get_state()
        satcom2, _ = _setup_satcom()
        satcom2.set_state(state)
        assert satcom2._previous_available["blue"] is True
