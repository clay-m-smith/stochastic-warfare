"""Phase 72a — Verify all engines are registered in SimulationContext checkpoint lists.

Tests ensure that the 22 previously missing engines are now included in both
get_state() and set_state() engine lists.
"""

from __future__ import annotations

import inspect

import pytest


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
    "morale_machine",
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
    return _get_source()


class TestStructuralRegistration:
    """Structural tests that verify engine names appear in source code."""

    @pytest.mark.parametrize("engine_name", PHASE_72A_ENGINES)
    def test_engine_in_get_state(self, source_pair, engine_name):
        """Each Phase 72a engine appears in get_state."""
        get_src, _ = source_pair
        assert f'"{engine_name}"' in get_src, (
            f"{engine_name} missing from SimulationContext.get_state()"
        )

    @pytest.mark.parametrize("engine_name", PHASE_72A_ENGINES)
    def test_engine_in_set_state(self, source_pair, engine_name):
        """Each Phase 72a engine appears in set_state."""
        _, set_src = source_pair
        assert f'"{engine_name}"' in set_src, (
            f"{engine_name} missing from SimulationContext.set_state()"
        )

    def test_total_engine_count_get_state(self, source_pair):
        """get_state engine list has >= 79 entries (57 pre-existing + 22 new)."""
        get_src, _ = source_pair
        # Count tuples in the engines list — each entry is ("name", self.xxx)
        count = get_src.count("self.")
        # Each engine entry has at least one self.X reference
        assert count >= 79, f"Expected >= 79 engine refs in get_state, got {count}"

    def test_total_engine_count_set_state(self, source_pair):
        """set_state engine list has >= 79 entries."""
        _, set_src = source_pair
        count = set_src.count("self.")
        assert count >= 79, f"Expected >= 79 engine refs in set_state, got {count}"

    @pytest.mark.parametrize("engine_name", PRE_EXISTING_ENGINES)
    def test_preexisting_engines_still_present(self, source_pair, engine_name):
        """Pre-existing engines remain in get_state (regression)."""
        get_src, _ = source_pair
        assert f'"{engine_name}"' in get_src, (
            f"Pre-existing engine {engine_name} removed from get_state!"
        )


class TestBehavioralRegistration:
    """Behavioral tests using mock engines."""

    def _make_mock_ctx(self):
        """Create a minimal mock SimulationContext for behavioral tests."""
        from types import SimpleNamespace
        from stochastic_warfare.simulation.scenario import SimulationContext
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        ctx = object.__new__(SimulationContext)
        ctx.clock = SimpleNamespace(
            get_state=lambda: {"t": 0},
            set_state=lambda s: None,
        )
        ctx.rng_manager = SimpleNamespace(
            get_state=lambda: {"s": 0},
            set_state=lambda s: None,
        )
        ctx.calibration = CalibrationSchema()
        ctx.era_config = None
        ctx.config = SimpleNamespace(model_dump=lambda: {})
        ctx.units_by_side = {}
        ctx.morale_states = {}

        all_engines = PRE_EXISTING_ENGINES + PHASE_72A_ENGINES
        for eng in all_engines:
            setattr(ctx, eng, None)
        return ctx

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

        state = {
            "clock": {"t": 0},
            "rng": {"s": 0},
            "calibration": {},
            "roe_engine": {"level": "WEAPONS_FREE"},
        }
        ctx.set_state(state)
        assert restored == {"level": "WEAPONS_FREE"}
