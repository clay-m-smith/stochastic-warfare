"""Phase 65 Step 0: Infrastructure tests — CalibrationSchema, ISR buffer, FOW property."""

from __future__ import annotations


import numpy as np
import pytest

from stochastic_warfare.simulation.calibration import CalibrationSchema


# ---------------------------------------------------------------------------
# CalibrationSchema
# ---------------------------------------------------------------------------


def test_enable_space_effects_defaults_false():
    cal = CalibrationSchema()
    assert cal.enable_space_effects is False


def test_enable_space_effects_accepts_true():
    cal = CalibrationSchema(enable_space_effects=True)
    assert cal.enable_space_effects is True


def test_enable_space_effects_via_get():
    cal = CalibrationSchema(enable_space_effects=True)
    assert cal.get("enable_space_effects", False) is True


@pytest.mark.test_evidence("structural_only")
def test_backward_compat_no_regressions():
    """Phase 64 fields still present after Phase 65 additions."""
    cal = CalibrationSchema()
    assert hasattr(cal, "planning_available_time_s")
    assert hasattr(cal, "stratagem_concentration_bonus")
    assert hasattr(cal, "order_propagation_delay_sigma")
    assert hasattr(cal, "enable_c2_friction")


# ---------------------------------------------------------------------------
# SpaceISREngine report buffer
# ---------------------------------------------------------------------------


def _make_isr_engine(
    *,
    scenario_sides: tuple[str, ...] = (),
):
    """Create a SpaceISREngine with minimal deps."""
    from stochastic_warfare.core.events import EventBus
    from stochastic_warfare.space.constellations import (
        ConstellationManager,
        SpaceConfig,
    )
    from stochastic_warfare.space.isr import SpaceISREngine
    from stochastic_warfare.space.orbits import OrbitalMechanicsEngine

    rng = np.random.Generator(np.random.PCG64(42))
    bus = EventBus()
    sc = SpaceConfig()
    orbits = OrbitalMechanicsEngine()
    cm = ConstellationManager(orbits, bus, rng, sc)
    return SpaceISREngine(
        cm,
        sc,
        bus,
        rng,
        scenario_sides=scenario_sides,
    )


@pytest.mark.test_evidence("structural_only")
def test_isr_has_get_recent_reports():
    engine = _make_isr_engine()
    assert hasattr(engine, "get_recent_reports")
    assert callable(engine.get_recent_reports)


def test_isr_get_recent_reports_returns_typed_queue_view():
    engine = _make_isr_engine()

    reports = engine.get_recent_reports()

    assert reports == ()
    assert isinstance(reports, tuple)


def test_isr_get_recent_reports_clear_false_preserves():
    engine = _make_isr_engine()

    first = engine.get_recent_reports(clear=False)
    second = engine.get_recent_reports(clear=False)

    assert first == second == ()
    with pytest.raises(
        RuntimeError,
        match="successful delivery",
    ):
        engine.get_recent_reports(clear=True)


def test_isr_state_uses_typed_queue_schema_and_round_trips():
    scenario_sides = ("blue", "red")
    engine = _make_isr_engine(scenario_sides=scenario_sides)
    state = engine.get_state()
    assert set(state) == {
        "last_overpass_time",
        "last_reported_at",
        "report_queue",
        "next_report_sequence",
    }
    assert state["report_queue"] == []

    engine2 = _make_isr_engine(scenario_sides=scenario_sides)
    engine2.set_state(state)
    assert engine2.get_state() == state


# ---------------------------------------------------------------------------
# FogOfWarManager.intel_fusion property
# ---------------------------------------------------------------------------


def test_fow_has_intel_fusion_property():
    from stochastic_warfare.detection.fog_of_war import FogOfWarManager

    rng = np.random.Generator(np.random.PCG64(42))
    fow = FogOfWarManager(rng=rng)
    assert fow.intel_fusion is not None
    # Should be the same object as internal _intel_fusion
    assert fow.intel_fusion is fow._intel_fusion
