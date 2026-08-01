"""Phase 72a — Verify all engines are registered in SimulationContext checkpoint lists.

Tests ensure that the 22 previously missing engines are now included in both
get_state() and set_state() engine lists.
"""

from __future__ import annotations

import inspect

import pytest

from tests.conftest import bind_test_era_runtime


# ---------------------------------------------------------------------------
# 22 engines added in Phase 72a
# ---------------------------------------------------------------------------

PHASE_72A_ENGINES = [
    "engagement_engine",
    "suppression_engine",
    "air_combat_engine",
    "air_ground_engine",
    "air_defense_engine",
    "missile_engine",
    "missile_defense_engine",
    "naval_gunnery_engine",
    "convoy_engine",
    "strategic_bombing_engine",
    "time_of_day_engine",
    "seasons_engine",
    "obscurants_engine",
    "order_propagation",
    "assessor",
    "decision_engine",
    "adaptation_engine",
    "roe_engine",
    "rout_engine",
    "ew_engine",
    "consumption_engine",
    "supply_network_engine",
]

# Pre-existing engines (Phase 63c and earlier)
PRE_EXISTING_ENGINES = [
    "ooda_engine",
    "planning_engine",
    "order_execution",
    "stockpile_manager",
    "fog_of_war",
    "aggregation_engine",
    "space_engine",
    "cbrn_engine",
    "school_registry",
    "trench_engine",
    "barrage_engine",
    "gas_warfare_engine",
    "volley_fire_engine",
    "melee_engine",
    "cavalry_engine",
    "formation_napoleonic_engine",
    "courier_engine",
    "foraging_engine",
    "archery_engine",
    "siege_engine",
    "formation_ancient_engine",
    "naval_oar_engine",
    "visual_signals_engine",
    "escalation_engine",
    "political_engine",
    "consequence_engine",
    "unconventional_engine",
    "insurgency_engine",
    "sof_engine",
    "war_termination_engine",
    "incendiary_engine",
    "uxo_engine",
    "commander_engine",
    "eccm_engine",
    "sigint_engine",
    "ew_decoy_engine",
    "dew_engine",
    "indirect_fire_engine",
    "naval_surface_engine",
    "naval_subsurface_engine",
    "naval_gunfire_support_engine",
    "mine_warfare_engine",
    "disruption_engine",
    "maintenance_engine",
    "medical_engine",
    "engineering_engine",
    "collateral_engine",
    "weather_engine",
    "sea_state_engine",
    "stratagem_engine",
    "iads_engine",
    "ato_engine",
    "underwater_acoustics_engine",
    "carrier_ops_engine",
    "comms_engine",
    "detection_engine",
    "movement_engine",
    "conditions_engine",
]


def _get_source():
    """Read scenario.py source once."""
    import stochastic_warfare.simulation.scenario as mod
    return inspect.getsource(mod.SimulationContext.get_state), inspect.getsource(mod.SimulationContext.set_state)


@pytest.fixture(scope="module")
def source_pair():
    from stochastic_warfare.simulation.scenario import (
        _CONTEXT_STATE_ENGINE_NAMES,
        SimulationContext,
    )

    context = object.__new__(SimulationContext)
    sentinels = {
        name: object()
        for name in _CONTEXT_STATE_ENGINE_NAMES
    }
    for name, sentinel in sentinels.items():
        setattr(context, name, sentinel)

    get_source, set_source = _get_source()
    return {
        "declared_names": _CONTEXT_STATE_ENGINE_NAMES,
        "runtime_owners": dict(context._checkpoint_engines()),
        "sentinels": sentinels,
        "get_source": get_source,
        "set_source": set_source,
        "apply_source": inspect.getsource(SimulationContext._apply_state),
    }


@pytest.mark.structural
class TestStructuralRegistration:
    """Structural diagnostics for the runtime-owned checkpoint registry."""

    @pytest.mark.parametrize("engine_name", PHASE_72A_ENGINES)
    def test_engine_in_get_state(self, source_pair, engine_name):
        """Each Phase 72a owner resolves through the capture registry."""
        assert engine_name in source_pair["declared_names"]
        assert (
            source_pair["runtime_owners"][engine_name]
            is source_pair["sentinels"][engine_name]
        )
        assert "self._checkpoint_engines()" in source_pair["get_source"]

    @pytest.mark.parametrize("engine_name", PHASE_72A_ENGINES)
    def test_engine_in_set_state(self, source_pair, engine_name):
        """Each Phase 72a owner resolves through the staged restore registry."""
        assert engine_name in source_pair["declared_names"]
        assert (
            source_pair["runtime_owners"][engine_name]
            is source_pair["sentinels"][engine_name]
        )
        assert "self._checkpoint_engines()" in source_pair["apply_source"]
        assert "self.stage_state(" in source_pair["set_source"]
        assert "self.commit_state(" in source_pair["set_source"]

    def test_total_engine_count_get_state(self, source_pair):
        """Capture consumes one unique registry with at least 79 owners."""
        declared = source_pair["declared_names"]
        assert tuple(source_pair["runtime_owners"]) == declared
        assert len(declared) == len(set(declared))
        assert len(declared) >= 79

    def test_total_engine_count_set_state(self, source_pair):
        """Restore consumes the same complete runtime owner registry."""
        declared = source_pair["declared_names"]
        expected = set(PRE_EXISTING_ENGINES + PHASE_72A_ENGINES)
        assert expected <= set(declared)
        assert len(declared) >= 79
        assert "self._checkpoint_engines()" in source_pair["apply_source"]

    @pytest.mark.parametrize("engine_name", PRE_EXISTING_ENGINES)
    def test_preexisting_engines_still_present(self, source_pair, engine_name):
        """Pre-existing owners remain in the runtime-owned registry."""
        assert engine_name in source_pair["declared_names"]
        assert (
            source_pair["runtime_owners"][engine_name]
            is source_pair["sentinels"][engine_name]
        )

    def test_morale_runtime_uses_its_explicit_checkpoint_boundary(
        self,
        source_pair,
    ):
        """Morale has one typed owner and is not duplicated in the registry."""
        assert "morale_machine" not in source_pair["declared_names"]
        assert "morale_runtime" not in source_pair["declared_names"]
        assert '"morale_runtime": (' in source_pair["get_source"]
        assert "self.morale_runtime.get_state()" in source_pair["get_source"]


class TestBehavioralRegistration:
    """Behavioral tests using mock engines."""

    def _make_mock_ctx(self):
        """Create a minimal mock SimulationContext for behavioral tests."""
        from datetime import datetime, timedelta, timezone
        from types import SimpleNamespace

        from stochastic_warfare.core.clock import SimulationClock
        from stochastic_warfare.core.events import EventBus
        from stochastic_warfare.core.rng import RNGManager
        from stochastic_warfare.simulation.scenario import SimulationContext
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        ctx = object.__new__(SimulationContext)
        ctx.clock = SimulationClock(
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            tick_duration=timedelta(seconds=5),
        )
        ctx.rng_manager = RNGManager(72)
        ctx.event_bus = EventBus()
        ctx.calibration = CalibrationSchema()
        ctx.era_config = None
        ctx.config = SimpleNamespace(
            date="2024-01-01",
            duration_hours=24.0,
            era="modern",
            tick_resolution=SimpleNamespace(
                strategic_s=3600.0,
                operational_s=300.0,
                tactical_s=5.0,
            ),
            tick_duration_seconds=None,
            model_dump=lambda: {},
        )
        ctx.units_by_side = {}
        ctx.morale_states = {}
        ctx.equipment_resolutions = {}

        all_engines = PRE_EXISTING_ENGINES + PHASE_72A_ENGINES
        for eng in all_engines:
            setattr(ctx, eng, None)
        return bind_test_era_runtime(ctx)

    def test_get_state_includes_mock_engine(self):
        """SimulationContext.get_state() calls get_state on registered engines."""
        from types import SimpleNamespace

        ctx = self._make_mock_ctx()
        mock_state = {"missiles_in_flight": [{"id": "m1", "pos": [0, 0]}]}
        ctx.missile_engine = SimpleNamespace(get_state=lambda: mock_state)

        state = ctx.get_state()
        assert "missile_engine" in state
        assert state["missile_engine"] == mock_state

    def test_set_state_restores_mock_engine(self):
        """SimulationContext.set_state() calls set_state on registered engines."""
        from types import SimpleNamespace

        ctx = self._make_mock_ctx()

        restored = {}
        mock_eng = SimpleNamespace(
            set_state=lambda s: restored.update(s),
        )
        ctx.roe_engine = mock_eng

        state = ctx.get_state()
        state["roe_engine"] = {"level": "WEAPONS_FREE"}
        ctx.set_state(state)
        assert restored == {"level": "WEAPONS_FREE"}
