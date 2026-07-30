"""Phase 65a: Space ISR fusion fix + early warning subscription tests."""

from __future__ import annotations

from datetime import datetime, timezone
import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _make_isr_engine():
    from stochastic_warfare.space.constellations import (
        ConstellationManager,
        SpaceConfig,
    )
    from stochastic_warfare.space.isr import SpaceISREngine
    from stochastic_warfare.space.orbits import OrbitalMechanicsEngine

    rng = np.random.Generator(np.random.PCG64(42))
    bus = EventBus()
    sc = SpaceConfig(theater_lat=0.0, theater_lon=0.0)
    orbits = OrbitalMechanicsEngine()
    cm = ConstellationManager(orbits, bus, rng, sc)
    return SpaceISREngine(cm, sc, bus, rng)


def _make_early_warning_engine(bus, rng, *, has_ew_constellation=True):
    from stochastic_warfare.space.constellations import (
        ConstellationDefinition,
        ConstellationManager,
        ConstellationType,
        SpaceConfig,
    )
    from stochastic_warfare.space.early_warning import EarlyWarningEngine
    from stochastic_warfare.space.orbits import OrbitalMechanicsEngine

    sc = SpaceConfig(theater_lat=0.0, theater_lon=0.0)
    orbits = OrbitalMechanicsEngine()
    cm = ConstellationManager(orbits, bus, rng, sc)

    if has_ew_constellation:
        # Register an early warning constellation for "blue"
        # GEO orbit: ~42164 km semi-major axis, 0 inclination
        cdef = ConstellationDefinition(
            constellation_id="ew_blue",
            side="blue",
            constellation_type=int(ConstellationType.EARLY_WARNING),
            num_satellites=3,
            plane_count=1,
            sats_per_plane=3,
            orbital_elements_template={
                "semi_major_axis_m": 42_164_000.0,
                "eccentricity": 0.0,
                "inclination_deg": 0.0,
                "raan_deg": 0.0,
                "arg_perigee_deg": 0.0,
                "true_anomaly_deg": 0.0,
            },
            detection_delay_s=45.0,
            detection_confidence=0.95,
        )
        cm.add_constellation(cdef)

    return EarlyWarningEngine(cm, sc, bus, rng)


# ---------------------------------------------------------------------------
# ISR report buffering
# ---------------------------------------------------------------------------


def _typed_report(report_id: int, target_id: str) -> object:
    from stochastic_warfare.space.isr import SpaceISRReport

    return SpaceISRReport(
        report_id=report_id,
        reporting_side="blue",
        target_side="red",
        target_id=target_id,
        satellite_id="sat-1",
        constellation_id="constellation-1",
        sensor_type="optical",
        resolution_m=0.5,
        position_sigma_m=2.0,
        target_position=Position(1000.0, 2000.0, 0.0),
        observed_at_s=100.0,
        available_at_s=400.0,
    )


def test_isr_report_serializes_typed_position() -> None:
    report = _typed_report(1, "tank_1")

    assert isinstance(report.target_position, Position)
    assert report.to_state()["target_position"] == [1000.0, 2000.0, 0.0]


def test_isr_queue_rejects_unacknowledged_clear() -> None:
    engine = _make_isr_engine()
    engine._report_queue.extend([
        _typed_report(1, "a"),
        _typed_report(2, "b"),
    ])

    first = engine.get_recent_reports(clear=False)
    assert len(first) == 2

    with pytest.raises(RuntimeError, match="successful delivery"):
        engine.get_recent_reports(clear=True)
    assert engine.get_recent_reports() == first


# ---------------------------------------------------------------------------
# _fuse_sigint bug fixes verification
# ---------------------------------------------------------------------------


@pytest.mark.structural
def test_fuse_sigint_uses_ctx_sigint_engine_not_ew():
    """engine.py must access sigint_engine from ctx, not from ew_engine."""
    from stochastic_warfare.simulation.engine import SimulationEngine
    import inspect

    source = inspect.getsource(SimulationEngine._fuse_sigint)
    # Bug fix 1: must use getattr(ctx, "sigint_engine"...) not getattr(ew, ...)
    assert 'getattr(ctx, "sigint_engine"' in source


@pytest.mark.structural
def test_fuse_sigint_uses_fog_of_war_intel_fusion():
    """engine.py must access fusion from fog_of_war.intel_fusion, not ctx.intel_fusion_engine."""
    from stochastic_warfare.simulation.engine import SimulationEngine
    import inspect

    source = inspect.getsource(SimulationEngine._fuse_sigint)
    assert "intel_fusion" in source
    assert "intel_fusion_engine" not in source


@pytest.mark.structural
def test_fuse_sigint_gated_by_enable_space_effects():
    """_fuse_sigint returns early when enable_space_effects is False."""
    from stochastic_warfare.simulation.engine import SimulationEngine
    import inspect

    source = inspect.getsource(SimulationEngine._fuse_sigint)
    assert "enable_space_effects" in source


@pytest.mark.structural
def test_fuse_sigint_does_not_consume_space_imint_queue() -> None:
    """Structural guard: EW fusion does not acknowledge Space IMINT."""
    from stochastic_warfare.simulation.engine import SimulationEngine
    import inspect

    source = inspect.getsource(SimulationEngine._fuse_sigint)
    assert "space_reports" not in source
    assert "isr_engine" not in source


# ---------------------------------------------------------------------------
# Early warning
# ---------------------------------------------------------------------------


def test_early_warning_detects_launch():
    bus = EventBus()
    rng = np.random.Generator(np.random.PCG64(42))
    ew = _make_early_warning_engine(bus, rng, has_ew_constellation=True)

    detected, delay = ew.check_launch_detection(
        1000.0, 2000.0, "blue", 100.0,
    )
    assert detected is True
    assert 0 < delay < 200  # delay_s = 45.0 for our constellation


def test_early_warning_publishes_event():
    bus = EventBus()
    rng = np.random.Generator(np.random.PCG64(42))
    ew = _make_early_warning_engine(bus, rng, has_ew_constellation=True)

    from stochastic_warfare.space.events import EarlyWarningDetectionEvent

    events = []
    bus.subscribe(EarlyWarningDetectionEvent, events.append)

    ew.check_launch_detection(1000.0, 2000.0, "blue", 100.0)
    assert len(events) == 1
    assert events[0].detection_delay_s == 45.0


def test_early_warning_no_constellation_returns_false():
    bus = EventBus()
    rng = np.random.Generator(np.random.PCG64(42))
    ew = _make_early_warning_engine(bus, rng, has_ew_constellation=False)

    detected, delay = ew.check_launch_detection(
        1000.0, 2000.0, "blue", 100.0,
    )
    assert detected is False
    assert delay == float("inf")


def test_handle_missile_launch_exists():
    """SimulationEngine has _handle_missile_launch method."""
    from stochastic_warfare.simulation.engine import SimulationEngine

    assert hasattr(SimulationEngine, "_handle_missile_launch")
