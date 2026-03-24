"""Phase 65b: ASAT & SIGINT wiring tests."""

from __future__ import annotations


import numpy as np

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position
from stochastic_warfare.ew.emitters import Emitter, EmitterType, WaveformType
from stochastic_warfare.ew.sigint import SIGINTCollector, SIGINTEngine


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
# SIGINT intercept gating
# ---------------------------------------------------------------------------


def test_sigint_skipped_when_space_effects_disabled():
    """_run_sigint_intercepts is gated by enable_space_effects."""
    from stochastic_warfare.simulation.engine import SimulationEngine
    import inspect

    source = inspect.getsource(SimulationEngine._run_sigint_intercepts)
    assert "enable_space_effects" in source


# ---------------------------------------------------------------------------
# ASAT
# ---------------------------------------------------------------------------


def _make_asat_engine():
    from stochastic_warfare.space.asat import ASATEngine
    from stochastic_warfare.space.constellations import (
        ConstellationDefinition,
        ConstellationManager,
        ConstellationType,
        SpaceConfig,
    )
    from stochastic_warfare.space.orbits import OrbitalMechanicsEngine, R_EARTH

    rng = np.random.Generator(np.random.PCG64(42))
    bus = EventBus()
    sc = SpaceConfig()
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
        },
    )
    cm.add_constellation(cdef)

    engine = ASATEngine(cm, sc, bus, rng)
    return engine, cm, bus


def test_asat_engage_with_registered_weapon():
    engine, cm, bus = _make_asat_engine()
    from stochastic_warfare.space.asat import ASATWeaponDefinition

    weapon = ASATWeaponDefinition(
        weapon_id="da_kkv_1",
        asat_type=0,  # DIRECT_ASCENT_KKV
        lethal_radius_m=2.0,
        guidance_sigma_m=0.5,
        max_altitude_km=2000,
        min_altitude_km=100,
    )
    engine.register_weapon(weapon, "blue")

    # Get a target satellite
    sats = cm.all_satellites()
    assert len(sats) > 0
    target = sats[0]

    result = engine.engage("da_kkv_1", target.satellite_id, "blue", 100.0)
    # Should return a valid result dict
    assert "hit" in result
    assert "pk" in result
    assert "debris_generated" in result


def test_asat_unknown_weapon():
    engine, _, _ = _make_asat_engine()
    result = engine.engage("nonexistent", "sat_1", "blue", 100.0)
    assert result["hit"] is False
    assert result.get("error") == "unknown_weapon"


def test_asat_reload_prevents_reengagement():
    engine, cm, _ = _make_asat_engine()
    from stochastic_warfare.space.asat import ASATWeaponDefinition

    weapon = ASATWeaponDefinition(
        weapon_id="kkv_2",
        asat_type=0,
        lethal_radius_m=2.0,
        guidance_sigma_m=0.5,
        reload_time_s=3600.0,
    )
    engine.register_weapon(weapon, "blue")

    sats = cm.all_satellites()
    target = sats[0]

    engine.engage("kkv_2", target.satellite_id, "blue", 100.0)
    result2 = engine.engage("kkv_2", target.satellite_id, "blue", 101.0)
    assert result2.get("error") == "reloading"


def test_asat_structural_placeholder_in_engine():
    """SimulationEngine has _attempt_asat_engagements method."""
    from stochastic_warfare.simulation.engine import SimulationEngine

    assert hasattr(SimulationEngine, "_attempt_asat_engagements")
