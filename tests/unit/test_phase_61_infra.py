"""Phase 61 infrastructure: CalibrationSchema maritime flags, engine instantiation, API smoke tests."""

from __future__ import annotations


from tests.conftest import make_clock, make_rng

from stochastic_warfare.simulation.calibration import CalibrationSchema
from stochastic_warfare.environment.weather import WeatherConfig, WeatherEngine
from stochastic_warfare.environment.astronomy import AstronomyEngine
from stochastic_warfare.environment.sea_state import SeaStateConfig, SeaStateEngine
from stochastic_warfare.environment.underwater_acoustics import (
    UnderwaterAcousticsEngine,
    AcousticConditions,
)
from stochastic_warfare.environment.electromagnetic import EMEnvironment
from stochastic_warfare.combat.carrier_ops import CarrierOpsEngine
from stochastic_warfare.core.events import EventBus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sea_state_engine() -> tuple[SeaStateEngine, WeatherEngine]:
    """Build a SeaStateEngine with all required dependencies."""
    clock = make_clock()
    rng = make_rng()
    weather = WeatherEngine(WeatherConfig(), clock, rng)
    astronomy = AstronomyEngine(clock)
    sea_state = SeaStateEngine(SeaStateConfig(), clock, astronomy, weather, rng)
    return sea_state, weather


# ---------------------------------------------------------------------------
# CalibrationSchema — new Phase 61 boolean flags
# ---------------------------------------------------------------------------


class TestCalibrationSchemaPhase61:
    """Three new maritime/acoustic/EM calibration flags accepted and default False."""

    def test_enable_sea_state_ops_default_false(self) -> None:
        cal = CalibrationSchema()
        assert cal.enable_sea_state_ops is False

    def test_enable_acoustic_layers_default_false(self) -> None:
        cal = CalibrationSchema()
        assert cal.enable_acoustic_layers is False

    def test_enable_em_propagation_default_false(self) -> None:
        cal = CalibrationSchema()
        assert cal.enable_em_propagation is False

    def test_backward_compat_no_new_flags_required(self) -> None:
        """CalibrationSchema() still works without specifying any Phase 61 flags."""
        cal = CalibrationSchema()
        # Should construct without error and retain pre-existing defaults
        assert cal.hit_probability_modifier == 1.0
        assert cal.enable_sea_state_ops is False
        assert cal.enable_acoustic_layers is False
        assert cal.enable_em_propagation is False


# ---------------------------------------------------------------------------
# UnderwaterAcousticsEngine
# ---------------------------------------------------------------------------


class TestUnderwaterAcousticsEngine:
    """UnderwaterAcousticsEngine instantiation, conditions, and update."""

    def test_instantiation(self) -> None:
        """Engine can be created with SeaStateEngine, clock, and rng."""
        sea_state, _ = _make_sea_state_engine()
        clock = make_clock()
        rng = make_rng()
        engine = UnderwaterAcousticsEngine(sea_state, clock, rng)
        assert engine is not None

    def test_conditions_returns_acoustic_conditions(self) -> None:
        """`.conditions` returns an AcousticConditions with expected fields."""
        sea_state, _ = _make_sea_state_engine()
        clock = make_clock()
        rng = make_rng()
        engine = UnderwaterAcousticsEngine(sea_state, clock, rng)

        cond = engine.conditions
        assert isinstance(cond, AcousticConditions)
        # thermocline_depth may be None (depends on SVP), but the field exists
        assert hasattr(cond, "thermocline_depth")
        assert isinstance(cond.ambient_noise_level, float)
        assert cond.ambient_noise_level > 0.0

    def test_update_runs_without_error(self) -> None:
        """`.update(dt)` accepts a float and does not raise."""
        sea_state, _ = _make_sea_state_engine()
        clock = make_clock()
        rng = make_rng()
        engine = UnderwaterAcousticsEngine(sea_state, clock, rng)
        engine.update(60.0)  # should not raise


# ---------------------------------------------------------------------------
# EMEnvironment
# ---------------------------------------------------------------------------


class TestEMEnvironmentRadarHorizon:
    """EMEnvironment.radar_horizon returns a positive distance."""

    def test_radar_horizon_positive(self) -> None:
        sea_state, weather = _make_sea_state_engine()
        clock = make_clock()
        em = EMEnvironment(weather, sea_state, clock)

        horizon_m = em.radar_horizon(antenna_height=30.0)
        assert isinstance(horizon_m, float)
        assert horizon_m > 0.0


# ---------------------------------------------------------------------------
# CarrierOpsEngine
# ---------------------------------------------------------------------------


class TestCarrierOpsEngineInstantiation:
    """CarrierOpsEngine can be created with event_bus and rng."""

    def test_instantiation(self) -> None:
        event_bus = EventBus()
        rng = make_rng()
        engine = CarrierOpsEngine(event_bus, rng)
        assert engine is not None
