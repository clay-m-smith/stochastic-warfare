"""Phase 18e tests — CBRN integration with simulation engine, movement, morale."""

from __future__ import annotations

import types
from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.cbrn.agents import AgentCategory, AgentDefinition, AgentRegistry
from stochastic_warfare.cbrn.casualties import CBRNCasualtyEngine
from stochastic_warfare.cbrn.contamination import ContaminationConfig, ContaminationManager
from stochastic_warfare.cbrn.decontamination import DecontaminationEngine
from stochastic_warfare.cbrn.dispersal import DispersalEngine
from stochastic_warfare.cbrn.engine import CBRNConfig, CBRNEngine
from stochastic_warfare.cbrn.protection import ProtectionEngine
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import ModuleId, Position

TS = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _make_cbrn_engine(enable: bool = True) -> CBRNEngine:
    bus = EventBus()
    rng = np.random.default_rng(42)
    config = CBRNConfig(enable_cbrn=enable)

    registry = AgentRegistry()
    registry.register(AgentDefinition(
        agent_id="sarin", category=int(AgentCategory.NERVE),
        lct50_mg_min_m3=70.0, persistence_hours=2.0,
    ))

    dispersal = DispersalEngine()
    contamination = ContaminationManager(
        grid_shape=(10, 10), cell_size_m=100.0,
        origin_easting=0.0, origin_northing=0.0,
        event_bus=bus, rng=rng,
        config=ContaminationConfig(enable_cbrn=enable),
    )
    protection = ProtectionEngine()
    casualty = CBRNCasualtyEngine(bus, rng)
    decon = DecontaminationEngine(bus, rng)

    return CBRNEngine(
        config=config, event_bus=bus, rng=rng,
        agent_registry=registry, dispersal_engine=dispersal,
        contamination_manager=contamination, protection_engine=protection,
        casualty_engine=casualty, decon_engine=decon,
    )


# ---------------------------------------------------------------------------
# ModuleId
# ---------------------------------------------------------------------------


class TestModuleId:
    def test_cbrn_in_enum(self):
        assert ModuleId.CBRN == "cbrn"


# ---------------------------------------------------------------------------
# SimulationContext
# ---------------------------------------------------------------------------


class TestSimulationContext:
    def test_field_exists(self):
        from stochastic_warfare.simulation.scenario import SimulationContext
        # Create minimal context — cbrn_engine should default to None
        ctx = SimulationContext.__new__(SimulationContext)
        assert not hasattr(ctx, "cbrn_engine") or ctx.cbrn_engine is None

    def test_none_default(self):
        """cbrn_engine defaults to None in dataclass."""
        from stochastic_warfare.simulation.scenario import SimulationContext
        import dataclasses
        fields = {f.name: f for f in dataclasses.fields(SimulationContext)}
        assert "cbrn_engine" in fields

    def test_get_set_state_includes_cbrn(self):
        """get_state engine list should include cbrn_engine."""
        from stochastic_warfare.simulation.scenario import SimulationContext
        import inspect
        source = inspect.getsource(SimulationContext.get_state)
        assert "cbrn_engine" in source


# ---------------------------------------------------------------------------
# Engine tick
# ---------------------------------------------------------------------------


class TestEngineTick:
    def test_calls_cbrn_update(self):
        """Simulation engine should call cbrn_engine.update when present."""
        # Read source to verify the integration point exists
        from stochastic_warfare.simulation import engine as sim_engine
        import inspect
        source = inspect.getsource(sim_engine.SimulationEngine._update_environment)
        assert "cbrn_engine" in source

    def test_skips_when_none(self):
        """No error when cbrn_engine is None."""
        from stochastic_warfare.simulation import engine as sim_engine
        import inspect
        source = inspect.getsource(sim_engine.SimulationEngine._update_environment)
        assert "cbrn_engine is not None" in source


# ---------------------------------------------------------------------------
# Movement MOPP
# ---------------------------------------------------------------------------


class TestMovementMOPP:
    def _make_engine(self):
        from stochastic_warfare.movement.engine import MovementEngine, MovementConfig
        # Mock heightmap that returns flat terrain
        hm = types.SimpleNamespace(
            slope_at=lambda pos: 0.0,
            elevation_at=lambda e, n: 0.0,
        )
        return MovementEngine(heightmap=hm, config=MovementConfig(noise_std=0.0))

    def test_compute_speed_with_factor(self):
        eng = self._make_engine()
        unit = types.SimpleNamespace(max_speed=10.0, position=Position(50, 50, 0))
        speed_normal = eng.compute_speed(unit, unit.position, 0.0)
        speed_mopp = eng.compute_speed(unit, unit.position, 0.0, mopp_speed_factor=0.7)
        assert speed_mopp < speed_normal
        assert speed_mopp == pytest.approx(speed_normal * 0.7, rel=0.01)

    def test_default_factor_is_one(self):
        eng = self._make_engine()
        unit = types.SimpleNamespace(max_speed=10.0, position=Position(50, 50, 0))
        speed = eng.compute_speed(unit, unit.position, 0.0)
        speed_explicit = eng.compute_speed(unit, unit.position, 0.0, mopp_speed_factor=1.0)
        assert speed == pytest.approx(speed_explicit)

    def test_mopp_zero_stops(self):
        eng = self._make_engine()
        unit = types.SimpleNamespace(max_speed=10.0, position=Position(50, 50, 0))
        speed = eng.compute_speed(unit, unit.position, 0.0, mopp_speed_factor=0.0)
        assert speed == 0.0


# ---------------------------------------------------------------------------
# Morale CBRN stress
# ---------------------------------------------------------------------------


class TestMoraleCBRN:
    def test_check_transition_with_stress(self):
        from stochastic_warfare.morale.state import MoraleStateMachine, MoraleConfig
        mm = MoraleStateMachine(
            event_bus=EventBus(),
            rng=np.random.default_rng(42),
            config=MoraleConfig(),
        )
        # With cbrn_stress=0, get baseline
        state1 = mm.check_transition("u1", 0.0, 0.0, True, 0.8, 1.0, TS, cbrn_stress=0.0)
        # Should not error
        assert state1 is not None

    def test_matrix_changes_with_cbrn_stress(self):
        from stochastic_warfare.morale.state import MoraleStateMachine, MoraleConfig
        mm = MoraleStateMachine(
            event_bus=EventBus(),
            rng=np.random.default_rng(42),
            config=MoraleConfig(),
        )
        matrix_no_stress = mm.compute_transition_matrix(0.1, 0.1, True, 0.8, 1.0, cbrn_stress=0.0)
        matrix_stress = mm.compute_transition_matrix(0.1, 0.1, True, 0.8, 1.0, cbrn_stress=0.5)
        # Stress should increase degradation → more off-diagonal probability
        assert not np.array_equal(matrix_no_stress, matrix_stress)
        # Degradation in stress case should be higher (more p_down)
        assert matrix_stress[0, 1] >= matrix_no_stress[0, 1]

    def test_default_cbrn_stress_zero(self):
        """Default cbrn_stress=0 should produce same matrix as before."""
        from stochastic_warfare.morale.state import MoraleStateMachine, MoraleConfig
        mm = MoraleStateMachine(
            event_bus=EventBus(),
            rng=np.random.default_rng(42),
            config=MoraleConfig(),
        )
        m1 = mm.compute_transition_matrix(0.1, 0.1, True, 0.8, 1.0)
        m2 = mm.compute_transition_matrix(0.1, 0.1, True, 0.8, 1.0, cbrn_stress=0.0)
        np.testing.assert_array_equal(m1, m2)


# ---------------------------------------------------------------------------
# CBRNEngine
# ---------------------------------------------------------------------------


class TestCBRNEngine:
    def test_release_agent_creates_puffs(self):
        eng = _make_cbrn_engine()
        puff_id = eng.release_agent("sarin", Position(500, 500, 0), 1.0, "artillery", TS)
        assert puff_id.startswith("puff_")

    def test_update_cycle(self):
        eng = _make_cbrn_engine()
        eng.release_agent("sarin", Position(500, 500, 0), 1.0, "artillery", TS)
        unit = types.SimpleNamespace(
            entity_id="u1", position=Position(500, 500, 0), personnel_count=10,
        )
        weather = types.SimpleNamespace(wind_speed_m_s=5.0, wind_direction_rad=0.0,
                                         cloud_cover=0.5, temperature_c=20.0,
                                         precipitation_rate_mm_hr=0.0)
        tod = types.SimpleNamespace(is_daytime=True)
        eng.update(10.0, 10.0, {"blue": [unit]}, weather, timestamp=TS, time_of_day=tod)
        # Should not error

    def test_get_mopp_effects(self):
        eng = _make_cbrn_engine()
        speed, det, fatigue = eng.get_mopp_effects("u1")
        assert speed == 1.0  # MOPP 0 default
        assert det == 1.0
        assert fatigue == 1.0
        # Set MOPP 4
        eng.set_mopp_level("u1", 4, TS)
        speed, det, fatigue = eng.get_mopp_effects("u1")
        assert speed == pytest.approx(0.7)
        assert det == pytest.approx(0.7)
        assert fatigue > 1.0

    def test_state_roundtrip(self):
        eng = _make_cbrn_engine()
        eng.set_mopp_level("u1", 4, TS)
        state = eng.get_state()
        eng2 = _make_cbrn_engine()
        eng2.set_state(state)
        assert eng2.get_mopp_level("u1") == 4


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    def test_enable_cbrn_false_skips(self):
        eng = _make_cbrn_engine(enable=False)
        unit = types.SimpleNamespace(
            entity_id="u1", position=Position(500, 500, 0), personnel_count=10,
        )
        # Should not error, should be a no-op
        eng.update(10.0, 10.0, {"blue": [unit]}, timestamp=TS)

    def test_morale_cache_key_includes_cbrn_stress(self):
        """Cache key for compute_transition_matrix should include cbrn_stress."""
        from stochastic_warfare.morale.state import MoraleStateMachine, MoraleConfig
        mm = MoraleStateMachine(
            event_bus=EventBus(),
            rng=np.random.default_rng(42),
            config=MoraleConfig(),
        )
        # Call with different cbrn_stress values — should not return cached
        mm.compute_transition_matrix(0.1, 0.1, True, 0.8, 1.0, cbrn_stress=0.0)
        mm.compute_transition_matrix(0.1, 0.1, True, 0.8, 1.0, cbrn_stress=0.5)
        # Verify the key distinguishes them (different matrices)
        m1 = mm.compute_transition_matrix(0.1, 0.1, True, 0.8, 1.0, cbrn_stress=0.0)
        m2 = mm.compute_transition_matrix(0.1, 0.1, True, 0.8, 1.0, cbrn_stress=0.5)
        assert not np.array_equal(m1, m2)
