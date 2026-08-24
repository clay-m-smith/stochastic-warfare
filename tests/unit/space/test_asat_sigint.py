"""Phase 65b: ASAT & SIGINT wiring tests."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position
from stochastic_warfare.ew.emitters import Emitter, EmitterType, WaveformType
from stochastic_warfare.ew.sigint import SIGINTCollector, SIGINTEngine
from stochastic_warfare.space.asat import ASATEngine
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
from stochastic_warfare.space.events import ASATEngagementEvent
from stochastic_warfare.space.orbits import OrbitalMechanicsEngine, R_EARTH

from tests.conftest import TS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sigint(seed=42):
    rng = np.random.Generator(np.random.PCG64(seed))
    bus = EventBus()
    return SIGINTEngine(bus, rng), bus, rng


def _make_collector(side="blue", pos=None):
    return SIGINTCollector(
        collector_id="sig_blue_1",
        unit_id="unit_blue_ew",
        position=pos or Position(0, 0, 0),
        receiver_sensitivity_dbm=-80.0,
        frequency_range_ghz=(2.0, 18.0),
        bandwidth_ghz=2.0,
        df_accuracy_deg=2.0,
        has_tdoa=False,
        side=side,
        aperture_m=2.0,
    )


def _make_emitter(pos=None, power_dbm=50.0):
    return Emitter(
        emitter_id="jammer_red_1",
        unit_id="unit_red_jam",
        emitter_type=EmitterType.JAMMER,
        position=pos or Position(5000, 0, 0),
        frequency_ghz=10.0,
        bandwidth_ghz=0.5,
        power_dbm=power_dbm,
        antenna_gain_dbi=10.0,
        waveform=WaveformType.CW,
        active=True,
        side="red",
    )


# ---------------------------------------------------------------------------
# SIGINT collector registration
# ---------------------------------------------------------------------------


def test_sigint_collector_registration():
    engine, _, _ = _make_sigint()
    collector = _make_collector()
    engine.register_collector(collector)
    assert collector.collector_id in engine._collectors


# ---------------------------------------------------------------------------
# SIGINT intercept
# ---------------------------------------------------------------------------


def test_sigint_intercept_nearby_high_power():
    """Nearby high-power emitter should be intercepted."""
    engine, _, _ = _make_sigint()
    collector = _make_collector(pos=Position(0, 0, 0))
    emitter = _make_emitter(pos=Position(1000, 0, 0), power_dbm=60.0)

    # High power + short range → near-certain intercept
    prob = engine.compute_intercept_probability(collector, emitter)
    assert prob > 0.8


def test_sigint_intercept_far_weak():
    """Far, weak emitter should not be intercepted."""
    engine, _, _ = _make_sigint()
    collector = _make_collector(pos=Position(0, 0, 0))
    emitter = _make_emitter(pos=Position(500_000, 0, 0), power_dbm=-10.0)

    prob = engine.compute_intercept_probability(collector, emitter)
    assert prob < 0.1


def test_sigint_reports_buffered_on_success():
    """Successful intercepts are buffered in _recent_reports."""
    engine, bus, _ = _make_sigint()
    collector = _make_collector(pos=Position(0, 0, 0))
    emitter = _make_emitter(pos=Position(100, 0, 0), power_dbm=70.0)

    report = engine.attempt_intercept(collector, emitter, timestamp=100.0)
    assert report.intercept_successful is True
    reports = engine.get_recent_reports()
    assert len(reports) >= 1
    assert reports[0].emitter_id == "jammer_red_1"


def test_sigint_collector_position_updated_from_unit():
    """Collector position should be updatable (used by engine.py per-tick)."""
    collector = _make_collector(pos=Position(0, 0, 0))
    new_pos = Position(5000, 3000, 0)
    collector.position = new_pos
    assert collector.position.easting == 5000


# ---------------------------------------------------------------------------
# ASAT
# ---------------------------------------------------------------------------


def _asat_weapon(
    *,
    weapon_id: str = "da_kkv_1",
    reload_time_s: float = 3600.0,
) -> ASATWeaponDefinition:
    return ASATWeaponDefinition(
        weapon_id=weapon_id,
        display_name=weapon_id,
        asat_type=int(ASATType.DIRECT_ASCENT_KKV),
        lethal_radius_m=2.0,
        guidance_sigma_m=0.5,
        max_altitude_km=2000.0,
        min_altitude_km=100.0,
        closing_velocity_mps=10000.0,
        reload_time_s=reload_time_s,
        dazzle_duration_s=0.0,
        dazzle_range_km=0.0,
    )


def _make_asat_engine(
    *,
    weapon: ASATWeaponDefinition | None = None,
    target_ids: tuple[str, ...] = ("target_leo_p0_s0",),
    execute_times_s: tuple[float, ...] = (100.0,),
    rounds_available: int | None = None,
    enable_asat: bool = True,
    include_weapon_definition: bool = True,
):
    weapon = weapon or _asat_weapon()
    if len(execute_times_s) != len(target_ids):
        raise ValueError("one execution time is required for each target")
    asset = ASATAssetConfig(
        asset_id="blue_da_asset_1",
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
    rng = np.random.Generator(np.random.PCG64(42))
    bus = EventBus()
    sc = SpaceConfig(
        enable_space=True,
        constellation_ids=["target_leo"],
        enable_asat=enable_asat,
        asat_assets=[asset],
        asat_orders=orders,
    )
    orbits = OrbitalMechanicsEngine()
    cm = ConstellationManager(orbits, bus, rng, sc)

    # Add a target constellation — LEO at 500 km
    cdef = ConstellationDefinition(
        constellation_id="target_leo",
        side="red",
        constellation_type=int(ConstellationType.IMAGING_OPTICAL),
        num_satellites=3,
        plane_count=1,
        sats_per_plane=3,
        orbital_elements_template={
            "semi_major_axis_m": R_EARTH + 500_000.0,
            "eccentricity": 0.0,
            "inclination_deg": 98.0,
            "raan_deg": 0.0,
            "arg_perigee_deg": 0.0,
            "true_anomaly_deg": 0.0,
        },
    )
    cm.add_constellation(cdef)

    definitions = (
        {weapon.weapon_id: weapon}
        if include_weapon_definition
        else {}
    )
    engine = ASATEngine(
        cm,
        sc,
        bus,
        rng,
        weapon_definitions=definitions,
        assets=sc.asat_assets,
        orders=sc.asat_orders,
        configuration_fingerprint="d" * 64,
    )
    return engine, cm, bus


def test_asat_executes_configured_exact_target_order():
    engine, cm, bus = _make_asat_engine()
    received: list[ASATEngagementEvent] = []
    bus.subscribe(ASATEngagementEvent, received.append)
    target = cm.get_satellite("target_leo_p0_s0")
    assert target is not None and target.is_active

    results = engine.execute_due_orders(100.0, TS)

    assert len(results) == 1
    result = results[0]
    assert result["order_id"] == "order_0"
    assert result["asset_id"] == "blue_da_asset_1"
    assert result["weapon_id"] == "da_kkv_1"
    assert result["attacker_side"] == "blue"
    assert result["target_satellite_id"] == target.satellite_id
    assert result["scheduled_time_s"] == 100.0
    assert result["execution_time_s"] == 100.0
    assert result["launched"] is True
    assert result["hit"] is True
    assert result["outcome"] == "hit"
    assert result["reason"] == ""
    assert result["pk"] == pytest.approx(1.0 - np.exp(-8.0))
    assert result["debris_generated"] > 0
    assert result["rounds_remaining"] == 0
    assert not target.is_active
    assert len(received) == 1
    assert received[0].order_id == result["order_id"]
    assert received[0].target_satellite_id == target.satellite_id


def test_asat_unknown_weapon_fails_topology_construction():
    with pytest.raises(ValueError, match="references unknown weapon"):
        _make_asat_engine(include_weapon_definition=False)


def test_asat_reload_rejects_second_configured_order():
    engine, _, _ = _make_asat_engine(
        weapon=_asat_weapon(weapon_id="kkv_2", reload_time_s=3600.0),
        target_ids=("target_leo_p0_s0", "target_leo_p0_s1"),
        execute_times_s=(100.0, 101.0),
        rounds_available=2,
    )
    first = engine.execute_due_orders(100.0, TS)[0]
    second = engine.execute_due_orders(101.0, TS)[0]

    assert first["launched"] is True
    assert first["rounds_remaining"] == 1
    assert second["launched"] is False
    assert second["hit"] is False
    assert second["outcome"] == "rejected"
    assert second["reason"] == "asset_reloading"
    assert second["rounds_remaining"] == 1


def test_asat_disabled_preserves_pending_order_and_target():
    engine, cm, bus = _make_asat_engine(enable_asat=False)
    received: list[ASATEngagementEvent] = []
    bus.subscribe(ASATEngagementEvent, received.append)
    target = cm.get_satellite("target_leo_p0_s0")
    assert target is not None
    state_before = engine.get_state()

    assert engine.execute_due_orders(100.0, TS) == []
    assert engine.get_state() == state_before
    assert target.is_active
    assert received == []
