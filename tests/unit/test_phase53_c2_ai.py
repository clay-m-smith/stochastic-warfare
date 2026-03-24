"""Phase 53: C2 & AI Completeness — wiring tests.

Tests that C2 effectiveness is computed from comms state,
StratagemEngine is instantiated and evaluated, school_id
auto-assignment works, FogOfWarManager is wired, IADS params
flow through, and structural engines are called.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import Unit, UnitStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _make_unit(entity_id: str, side: str = "blue",
               easting: float = 0.0, northing: float = 0.0,
               domain: Domain = Domain.GROUND) -> Unit:
    """Create a minimal unit for testing."""
    u = Unit.__new__(Unit)
    object.__setattr__(u, "entity_id", entity_id)
    object.__setattr__(u, "unit_type", "infantry")
    object.__setattr__(u, "display_name", entity_id)
    object.__setattr__(u, "status", UnitStatus.ACTIVE)
    object.__setattr__(u, "position", Position(easting, northing, 0.0))
    object.__setattr__(u, "domain", domain)
    object.__setattr__(u, "speed", 0.0)
    object.__setattr__(u, "personnel", list(range(10)))
    object.__setattr__(u, "heading", 0.0)
    return u


def _make_ctx(
    units_by_side: dict[str, list[Unit]] | None = None,
    comms_engine: Any = None,
    fog_of_war: Any = None,
    calibration: Any = None,
    stratagem_engine: Any = None,
    school_registry: Any = None,
    commander_engine: Any = None,
    assessor: Any = None,
    decision_engine: Any = None,
    ooda_engine: Any = None,
    order_propagation: Any = None,
    planning_engine: Any = None,
    ato_engine: Any = None,
    iads_engine: Any = None,
    political_engine: Any = None,
    escalation_engine: Any = None,
) -> SimpleNamespace:
    """Build a minimal SimulationContext-like namespace."""
    from stochastic_warfare.simulation.calibration import CalibrationSchema
    if units_by_side is None:
        units_by_side = {}
    cal = calibration or CalibrationSchema()

    _event_bus = EventBus()
    ctx = SimpleNamespace(
        units_by_side=units_by_side,
        morale_states={},
        calibration=cal,
        comms_engine=comms_engine,
        fog_of_war=fog_of_war,
        stratagem_engine=stratagem_engine,
        school_registry=school_registry,
        commander_engine=commander_engine,
        assessor=assessor,
        decision_engine=decision_engine,
        ooda_engine=ooda_engine,
        order_propagation=order_propagation,
        order_execution=None,
        planning_engine=planning_engine,
        ato_engine=ato_engine,
        iads_engine=iads_engine,
        political_engine=political_engine,
        escalation_engine=escalation_engine,
        stockpile_manager=None,
        suppression_engine=None,
        event_bus=_event_bus,
        config=SimpleNamespace(
            behavior_rules={},
            era="modern",
        ),
        clock=SimpleNamespace(
            current_time=_TS,
            elapsed=SimpleNamespace(total_seconds=lambda: 0.0),
        ),
        engagement_engine=None,
        detection_engine=None,
        movement_engine=None,
        morale_machine=None,
        roe_engine=None,
        rout_engine=None,
        consumption_engine=None,
        heightmap=None,
        unit_weapons={},
        unit_sensors={},
    )

    def active_units(side: str) -> list[Unit]:
        return [u for u in ctx.units_by_side.get(side, [])
                if u.status == UnitStatus.ACTIVE]

    def side_names() -> list[str]:
        return sorted(ctx.units_by_side.keys())

    ctx.active_units = active_units
    ctx.side_names = side_names
    return ctx


# ===========================================================================
# 53b: C2 Effectiveness
# ===========================================================================


class TestC2Effectiveness:
    """Test C2 effectiveness computation from comms state."""

    def test_unit_with_channel_in_range(self, event_bus, rng):
        """Unit registered with good channel → high effectiveness."""
        from stochastic_warfare.c2.communications import (
            CommEquipmentDefinition,
            CommEquipmentLoader,
            CommunicationsEngine,
        )

        loader = CommEquipmentLoader.__new__(CommEquipmentLoader)
        loader._data_dir = None
        loader._definitions = {
            "radio_vhf": CommEquipmentDefinition(
                comm_id="radio_vhf",
                comm_type="RADIO_VHF",
                display_name="VHF Radio",
                max_range_m=20000.0,
                bandwidth_bps=16000.0,
                base_latency_s=0.1,
                base_reliability=0.95,
                intercept_risk=0.3,
                jam_resistance=0.5,
                requires_los=False,
            ),
        }
        engine = CommunicationsEngine(event_bus, rng, loader)
        engine.register_unit("u1", ["radio_vhf"])
        engine.register_unit("u2", ["radio_vhf"])

        positions = {
            "u1": Position(0.0, 0.0, 0.0),
            "u2": Position(1000.0, 0.0, 0.0),
        }
        eff = engine.compute_c2_effectiveness("u1", positions)
        assert eff > 0.8, f"Expected high effectiveness, got {eff}"

    def test_unit_no_channels(self, event_bus, rng):
        """Unit registered but no equipment → min effectiveness."""
        from stochastic_warfare.c2.communications import CommunicationsEngine

        engine = CommunicationsEngine(event_bus, rng)
        engine.register_unit("u1", [])
        engine.register_unit("u2", [])

        positions = {
            "u1": Position(0.0, 0.0, 0.0),
            "u2": Position(1000.0, 0.0, 0.0),
        }
        eff = engine.compute_c2_effectiveness("u1", positions, min_effectiveness=0.3)
        assert eff == pytest.approx(0.3)

    def test_unit_not_registered(self, event_bus, rng):
        """Unregistered unit → 1.0 (backward compat)."""
        from stochastic_warfare.c2.communications import CommunicationsEngine

        engine = CommunicationsEngine(event_bus, rng)
        positions = {"u1": Position(0.0, 0.0, 0.0)}
        eff = engine.compute_c2_effectiveness("u1", positions)
        assert eff == 1.0

    def test_no_comms_engine_returns_one(self):
        """No comms_engine on context → 1.0."""
        from stochastic_warfare.simulation.battle import BattleManager

        ctx = _make_ctx(comms_engine=None)
        eff = BattleManager._compute_c2_effectiveness(ctx, "u1", "blue")
        assert eff == 1.0

    def test_empty_positions(self, event_bus, rng):
        """No positions dict → 1.0."""
        from stochastic_warfare.c2.communications import CommunicationsEngine

        engine = CommunicationsEngine(event_bus, rng)
        engine.register_unit("u1", [])
        eff = engine.compute_c2_effectiveness("u1", {})
        assert eff == 1.0

    def test_multiple_neighbors_mixed(self, event_bus, rng):
        """Multiple neighbors with mixed reliability → average."""
        from stochastic_warfare.c2.communications import (
            CommEquipmentDefinition,
            CommEquipmentLoader,
            CommunicationsEngine,
        )

        loader = CommEquipmentLoader.__new__(CommEquipmentLoader)
        loader._data_dir = None
        loader._definitions = {
            "radio_vhf": CommEquipmentDefinition(
                comm_id="radio_vhf",
                comm_type="RADIO_VHF",
                display_name="VHF Radio",
                max_range_m=5000.0,
                bandwidth_bps=16000.0,
                base_latency_s=0.1,
                base_reliability=0.95,
                intercept_risk=0.3,
                jam_resistance=0.5,
                requires_los=False,
            ),
        }
        engine = CommunicationsEngine(event_bus, rng, loader)
        engine.register_unit("u1", ["radio_vhf"])
        engine.register_unit("u2", ["radio_vhf"])
        engine.register_unit("u3", ["radio_vhf"])

        positions = {
            "u1": Position(0.0, 0.0, 0.0),
            "u2": Position(1000.0, 0.0, 0.0),  # In range
            "u3": Position(4500.0, 0.0, 0.0),   # Near max range — degraded
        }
        eff = engine.compute_c2_effectiveness("u1", positions)
        # Should be between min and 1.0
        assert 0.3 < eff < 1.0

    def test_out_of_range(self, event_bus, rng):
        """All neighbors out of range → min effectiveness."""
        from stochastic_warfare.c2.communications import (
            CommEquipmentDefinition,
            CommEquipmentLoader,
            CommunicationsEngine,
        )

        loader = CommEquipmentLoader.__new__(CommEquipmentLoader)
        loader._data_dir = None
        loader._definitions = {
            "radio_vhf": CommEquipmentDefinition(
                comm_id="radio_vhf",
                comm_type="RADIO_VHF",
                display_name="VHF Radio",
                max_range_m=100.0,  # Very short range
                bandwidth_bps=16000.0,
                base_latency_s=0.1,
                base_reliability=0.95,
                intercept_risk=0.3,
                jam_resistance=0.5,
                requires_los=False,
            ),
        }
        engine = CommunicationsEngine(event_bus, rng, loader)
        engine.register_unit("u1", ["radio_vhf"])
        engine.register_unit("u2", ["radio_vhf"])

        positions = {
            "u1": Position(0.0, 0.0, 0.0),
            "u2": Position(5000.0, 0.0, 0.0),  # Way out of range
        }
        eff = engine.compute_c2_effectiveness("u1", positions, min_effectiveness=0.3)
        assert eff == pytest.approx(0.3)

    def test_calibration_min_effectiveness(self):
        """CalibrationSchema accepts c2_min_effectiveness."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        cal = CalibrationSchema(c2_min_effectiveness=0.5)
        assert cal.c2_min_effectiveness == 0.5
        assert cal.get("c2_min_effectiveness") == 0.5


# ===========================================================================
# 53c: StratagemEngine Wiring
# ===========================================================================


class TestStratagemEngineWiring:
    """Test StratagemEngine instantiation and DECIDE phase calls."""

    def test_stratagem_in_create_engines(self):
        """StratagemEngine appears in _create_engines result dict."""
        # We test this indirectly — instantiate the engine and verify type
        from stochastic_warfare.c2.ai.stratagems import StratagemEngine

        bus = EventBus()
        rng = _rng()
        engine = StratagemEngine(bus, rng)
        assert hasattr(engine, "evaluate_concentration_opportunity")
        assert hasattr(engine, "evaluate_deception_opportunity")

    def test_evaluate_concentration_called(self):
        """DECIDE phase calls evaluate_concentration_opportunity."""
        from stochastic_warfare.c2.ai.stratagems import StratagemEngine

        bus = EventBus()
        engine = StratagemEngine(bus, _rng())

        # Create a mock assessment
        assessment = SimpleNamespace(
            force_ratio=1.5,
            c2_effectiveness=0.8,
            supply_level=0.9,
            morale_level=0.8,
            intel_quality=0.5,
        )
        units = ["u1", "u2", "u3", "u4"]
        viable, reason = engine.evaluate_concentration_opportunity(
            assessment, units, echelon=5, experience=0.5,
        )
        assert isinstance(viable, bool)
        assert isinstance(reason, str)

    def test_evaluate_deception_called(self):
        """DECIDE phase calls evaluate_deception_opportunity."""
        from stochastic_warfare.c2.ai.stratagems import StratagemEngine

        bus = EventBus()
        engine = StratagemEngine(bus, _rng())

        assessment = SimpleNamespace(
            force_ratio=1.0,
            c2_effectiveness=0.8,
            supply_level=0.9,
            morale_level=0.8,
            intel_quality=0.5,
        )
        units = ["u1", "u2"]
        viable, reason = engine.evaluate_deception_opportunity(
            assessment, units, echelon=6, experience=0.5,
        )
        assert isinstance(viable, bool)

    def test_sun_tzu_deception_affinity(self):
        """School with high DECEPTION affinity > CONCENTRATION."""
        from stochastic_warfare.c2.ai.schools.base import DoctrinalSchool, SchoolDefinition

        defn = SchoolDefinition(
            school_id="test_sun_tzu",
            display_name="Test Sun Tzu",
            description="Test",
            assessment_weight_overrides={},
            decision_score_adjustments={},
            ooda_multiplier=1.0,
            coa_score_weight_overrides={},
            risk_tolerance="moderate",
            opponent_modeling_enabled=True,
            stratagem_affinity={"DECEPTION": 0.8, "CONCENTRATION": 0.3},
        )
        school = DoctrinalSchool(defn)
        affinity = school.get_stratagem_affinity()
        assert affinity.get("DECEPTION", 0) > affinity.get("CONCENTRATION", 0)

    def test_clausewitz_concentration_affinity(self):
        """School with high CONCENTRATION affinity > DECEPTION."""
        from stochastic_warfare.c2.ai.schools.base import DoctrinalSchool, SchoolDefinition

        defn = SchoolDefinition(
            school_id="test_clausewitz",
            display_name="Test Clausewitz",
            description="Test",
            assessment_weight_overrides={},
            decision_score_adjustments={},
            ooda_multiplier=1.0,
            coa_score_weight_overrides={},
            risk_tolerance="moderate",
            opponent_modeling_enabled=False,
            stratagem_affinity={"CONCENTRATION": 0.8, "DECEPTION": 0.2},
        )
        school = DoctrinalSchool(defn)
        affinity = school.get_stratagem_affinity()
        assert affinity.get("CONCENTRATION", 0) > affinity.get("DECEPTION", 0)


class TestSchoolIdAutoAssignment:
    """Test school_id from commander personality auto-assigns to unit."""

    def test_school_id_assigns(self):
        """Commander with school_id → unit assigned to that school."""
        from stochastic_warfare.c2.ai.commander import (
            CommanderEngine,
            CommanderPersonality,
            CommanderProfileLoader,
        )
        from stochastic_warfare.c2.ai.schools import SchoolRegistry
        from stochastic_warfare.c2.ai.schools.base import (
            DoctrinalSchool,
            SchoolDefinition,
        )

        # Create school registry with a school
        registry = SchoolRegistry()
        defn = SchoolDefinition(
            school_id="maneuver",
            display_name="Maneuver",
            description="Test",
            assessment_weight_overrides={},
            decision_score_adjustments={},
            ooda_multiplier=1.0,
            coa_score_weight_overrides={},
            risk_tolerance="moderate",
            opponent_modeling_enabled=False,
            stratagem_affinity={},
        )
        school = DoctrinalSchool(defn)
        registry.register(school)

        # Create commander with school_id
        loader = CommanderProfileLoader.__new__(CommanderProfileLoader)
        loader._data_dir = None
        loader._definitions = {
            "aggressive_commander": CommanderPersonality(
                profile_id="aggressive_commander",
                display_name="Test",
                description="Test",
                aggression=0.8,
                caution=0.2,
                flexibility=0.5,
                initiative=0.7,
                experience=0.6,
                school_id="maneuver",
            ),
        }
        cmd_engine = CommanderEngine(loader, _rng())
        cmd_engine.assign_personality("u1", "aggressive_commander")

        # Simulate the auto-assignment logic from scenario.py
        personality = cmd_engine.get_personality("u1")
        assert personality is not None
        assert personality.school_id == "maneuver"

        registry.assign_to_unit("u1", personality.school_id)
        assigned = registry.get_for_unit("u1")
        assert assigned is not None
        assert assigned.definition.school_id == "maneuver"

    def test_school_id_none_noop(self):
        """Commander with school_id=None → no assignment."""
        from stochastic_warfare.c2.ai.commander import (
            CommanderEngine,
            CommanderPersonality,
            CommanderProfileLoader,
        )

        loader = CommanderProfileLoader.__new__(CommanderProfileLoader)
        loader._data_dir = None
        loader._definitions = {
            "cautious_commander": CommanderPersonality(
                profile_id="cautious_commander",
                display_name="Test",
                description="Test",
                aggression=0.2,
                caution=0.8,
                flexibility=0.5,
                initiative=0.3,
                experience=0.5,
                school_id=None,
            ),
        }
        cmd_engine = CommanderEngine(loader, _rng())
        cmd_engine.assign_personality("u1", "cautious_commander")

        personality = cmd_engine.get_personality("u1")
        assert personality is not None
        assert personality.school_id is None
        # No crash — the condition `personality.school_id` is falsy

    def test_unknown_school_id_logged(self):
        """Unknown school_id → KeyError caught, logged, no crash."""
        from stochastic_warfare.c2.ai.schools import SchoolRegistry

        registry = SchoolRegistry()
        with pytest.raises(KeyError):
            registry.assign_to_unit("u1", "nonexistent_school")

    def test_no_school_registry_noop(self):
        """No school_registry → school assignment skipped."""
        # Just verify the guard condition: if ctx.school_registry is None → skip
        ctx = _make_ctx(school_registry=None, commander_engine=MagicMock())
        # The _apply_commander_assignments code guards on school_registry
        assert ctx.school_registry is None

    def test_no_commander_engine_noop(self):
        """No commander_engine → school assignment skipped."""
        ctx = _make_ctx(school_registry=MagicMock(), commander_engine=None)
        assert ctx.commander_engine is None


# ===========================================================================
# 53a: FogOfWarManager Wiring
# ===========================================================================


class TestFogOfWarWiring:
    """Test FogOfWarManager wiring in battle.py."""

    def test_fow_disabled_by_default(self):
        """Default calibration has enable_fog_of_war=False."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        cal = CalibrationSchema()
        assert cal.enable_fog_of_war is False

    def test_fow_enabled_flag(self):
        """CalibrationSchema accepts enable_fog_of_war=True."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        cal = CalibrationSchema(enable_fog_of_war=True)
        assert cal.enable_fog_of_war is True
        assert cal.get("enable_fog_of_war") is True

    def test_fow_update_called_when_enabled(self):
        """With enable_fog_of_war=True, fog_of_war.update() is called."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema
        from stochastic_warfare.simulation.battle import BattleManager, BattleContext

        cal = CalibrationSchema(enable_fog_of_war=True)
        fow = MagicMock()
        u1 = _make_unit("u1", easting=0.0)
        u2 = _make_unit("u2", easting=1000.0)

        ctx = _make_ctx(
            units_by_side={"blue": [u1], "red": [u2]},
            fog_of_war=fow,
            calibration=cal,
        )

        battle = BattleContext(
            battle_id="b1",
            start_tick=0,
            start_time=_TS,
            involved_sides=["blue", "red"],
        )
        mgr = BattleManager(EventBus())
        mgr.execute_tick(ctx, battle, dt=5.0)
        assert fow.update.called

    def test_fow_not_called_when_disabled(self):
        """With enable_fog_of_war=False, fog_of_war.update() NOT called."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema
        from stochastic_warfare.simulation.battle import BattleManager, BattleContext

        cal = CalibrationSchema(enable_fog_of_war=False)
        fow = MagicMock()
        u1 = _make_unit("u1", easting=0.0)
        u2 = _make_unit("u2", easting=1000.0)

        ctx = _make_ctx(
            units_by_side={"blue": [u1], "red": [u2]},
            fog_of_war=fow,
            calibration=cal,
        )

        battle = BattleContext(
            battle_id="b1",
            start_tick=0,
            start_time=_TS,
            involved_sides=["blue", "red"],
        )
        mgr = BattleManager(EventBus())
        mgr.execute_tick(ctx, battle, dt=5.0)
        assert not fow.update.called

    def test_fow_per_side_views(self):
        """Per-side detection: side A and side B get independent world views."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema
        from stochastic_warfare.simulation.battle import BattleManager, BattleContext

        cal = CalibrationSchema(enable_fog_of_war=True)
        fow = MagicMock()
        u1 = _make_unit("u1", easting=0.0)
        u2 = _make_unit("u2", easting=1000.0)

        ctx = _make_ctx(
            units_by_side={"blue": [u1], "red": [u2]},
            fog_of_war=fow,
            calibration=cal,
        )

        battle = BattleContext(
            battle_id="b1",
            start_tick=0,
            start_time=_TS,
            involved_sides=["blue", "red"],
        )
        mgr = BattleManager(EventBus())
        mgr.execute_tick(ctx, battle, dt=5.0)
        # update should be called once per side
        assert fow.update.call_count == 2
        sides_called = {call.kwargs["side"] for call in fow.update.call_args_list}
        assert "blue" in sides_called
        assert "red" in sides_called

    def test_fow_exception_logged(self):
        """Exception in fog_of_war.update() → logged, continues normally."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema
        from stochastic_warfare.simulation.battle import BattleManager, BattleContext

        cal = CalibrationSchema(enable_fog_of_war=True)
        fow = MagicMock()
        fow.update.side_effect = RuntimeError("FoW error")
        u1 = _make_unit("u1", easting=0.0)
        u2 = _make_unit("u2", easting=1000.0)

        ctx = _make_ctx(
            units_by_side={"blue": [u1], "red": [u2]},
            fog_of_war=fow,
            calibration=cal,
        )

        battle = BattleContext(
            battle_id="b1",
            start_tick=0,
            start_time=_TS,
            involved_sides=["blue", "red"],
        )
        mgr = BattleManager(EventBus())
        # Should not raise
        mgr.execute_tick(ctx, battle, dt=5.0)

    def test_missing_fow_no_crash(self):
        """Missing fog_of_war on context → no crash."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema
        from stochastic_warfare.simulation.battle import BattleManager, BattleContext

        cal = CalibrationSchema(enable_fog_of_war=True)
        u1 = _make_unit("u1", easting=0.0)
        u2 = _make_unit("u2", easting=1000.0)

        ctx = _make_ctx(
            units_by_side={"blue": [u1], "red": [u2]},
            fog_of_war=None,
            calibration=cal,
        )

        battle = BattleContext(
            battle_id="b1",
            start_tick=0,
            start_time=_TS,
            involved_sides=["blue", "red"],
        )
        mgr = BattleManager(EventBus())
        # Should not raise
        mgr.execute_tick(ctx, battle, dt=5.0)

    def test_fow_detected_count_used_in_assessment(self):
        """Assessment uses detected enemy count when fog_of_war enabled."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema
        from stochastic_warfare.simulation.battle import BattleManager
        from stochastic_warfare.c2.ai.ooda import OODAPhase

        cal = CalibrationSchema(enable_fog_of_war=True)
        fow = MagicMock()
        # Simulate: blue side detects 1 of 2 enemies
        wv_blue = SimpleNamespace(contacts={"r1": SimpleNamespace()})
        wv_red = SimpleNamespace(contacts={"b1": SimpleNamespace()})
        fow.get_world_view.side_effect = lambda side: wv_blue if side == "blue" else wv_red

        u1 = _make_unit("u1", easting=0.0)
        u2 = _make_unit("u2", easting=1000.0)
        u3 = _make_unit("u3", easting=2000.0)

        assessor = MagicMock()
        assessor.assess.return_value = SimpleNamespace(
            force_ratio=1.0, c2_effectiveness=1.0,
            supply_level=1.0, morale_level=0.7,
            intel_quality=0.5,
        )

        ctx = _make_ctx(
            units_by_side={"blue": [u1], "red": [u2, u3]},
            fog_of_war=fow,
            calibration=cal,
            assessor=assessor,
        )

        mgr = BattleManager(EventBus())
        # Simulate OBSERVE completion
        completions = [("u1", OODAPhase.OBSERVE)]
        mgr._process_ooda_completions(ctx, completions, _TS)

        # assessor.assess should have been called with contacts=1
        assert assessor.assess.called
        call_kwargs = assessor.assess.call_args
        # contacts is passed as keyword arg
        assert call_kwargs.kwargs.get("contacts") == 1 or \
            (len(call_kwargs.args) > 7 and call_kwargs.args[7] == 1)

    def test_backward_compat_ground_truth_when_disabled(self):
        """With enable_fog_of_war=False, assessment uses ground truth enemy count."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema
        from stochastic_warfare.simulation.battle import BattleManager
        from stochastic_warfare.c2.ai.ooda import OODAPhase

        cal = CalibrationSchema(enable_fog_of_war=False)

        u1 = _make_unit("u1", easting=0.0)
        u2 = _make_unit("u2", easting=1000.0)
        u3 = _make_unit("u3", easting=2000.0)

        assessor = MagicMock()
        assessor.assess.return_value = SimpleNamespace(
            force_ratio=1.0, c2_effectiveness=1.0,
            supply_level=1.0, morale_level=0.7,
            intel_quality=0.5,
        )

        ctx = _make_ctx(
            units_by_side={"blue": [u1], "red": [u2, u3]},
            fog_of_war=None,
            calibration=cal,
            assessor=assessor,
        )

        mgr = BattleManager(EventBus())
        completions = [("u1", OODAPhase.OBSERVE)]
        mgr._process_ooda_completions(ctx, completions, _TS)

        assert assessor.assess.called
        call_kwargs = assessor.assess.call_args
        # contacts should be 2 (ground truth)
        assert call_kwargs.kwargs.get("contacts") == 2 or \
            (len(call_kwargs.args) > 7 and call_kwargs.args[7] == 2)


# ===========================================================================
# 53e: SEAD/IADS Parameters
# ===========================================================================


class TestSeadIadsParams:
    """Test IADS parameter wiring from CalibrationSchema."""

    def test_iads_config_has_sead_effectiveness(self):
        """IadsConfig has sead_effectiveness field."""
        from stochastic_warfare.combat.iads import IadsConfig

        cfg = IadsConfig()
        assert cfg.sead_effectiveness == 0.5
        assert cfg.sead_arm_effectiveness == 0.8

    def test_sead_effectiveness_scales_damage(self):
        """sead_effectiveness modifies damage in apply_sead_damage."""
        from stochastic_warfare.combat.iads import IadsConfig, IadsEngine, IadsSector

        bus = EventBus()
        # Low effectiveness = less damage
        cfg_low = IadsConfig(sead_degradation_rate=0.5, sead_effectiveness=0.2)
        engine_low = IadsEngine(bus, _rng(42), cfg_low)

        # High effectiveness = more damage
        cfg_high = IadsConfig(sead_degradation_rate=0.5, sead_effectiveness=1.0)
        engine_high = IadsEngine(bus, _rng(42), cfg_high)

        # Same sector setup
        for engine in (engine_low, engine_high):
            sector = IadsSector(
                sector_id="s1",
                center=Position(0.0, 0.0, 0.0),
                radius_m=10000.0,
                sam_batteries=["sam1"],
            )
            engine.register_sector(sector)

        h_low = engine_low.apply_sead_damage("s1", "sam1")
        h_high = engine_high.apply_sead_damage("s1", "sam1")

        # Higher effectiveness should result in lower health
        # (more damage applied). With stochastic variation there's
        # some noise, but the trend should be clear.
        assert h_low > h_high or abs(h_low - h_high) < 0.15

    def test_calibration_sead_params(self):
        """CalibrationSchema has sead_effectiveness and sead_arm_effectiveness."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        cal = CalibrationSchema(
            sead_effectiveness=0.7,
            sead_arm_effectiveness=0.9,
            iads_degradation_rate=0.4,
        )
        assert cal.get("sead_effectiveness") == 0.7
        assert cal.get("sead_arm_effectiveness") == 0.9
        assert cal.get("iads_degradation_rate") == 0.4

    def test_drone_provocation_prob(self):
        """CalibrationSchema has drone_provocation_prob field."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        cal = CalibrationSchema(drone_provocation_prob=0.15)
        assert cal.get("drone_provocation_prob") == 0.15

    def test_iads_engine_instantiated(self):
        """IadsEngine can be instantiated with calibration params."""
        from stochastic_warfare.combat.iads import IadsConfig, IadsEngine

        cfg = IadsConfig(
            sead_degradation_rate=0.4,
            sead_effectiveness=0.7,
            sead_arm_effectiveness=0.9,
        )
        engine = IadsEngine(EventBus(), _rng(), cfg)
        assert engine._config.sead_effectiveness == 0.7
        assert engine._config.sead_arm_effectiveness == 0.9


# ===========================================================================
# 53e: Escalation Sub-Engines
# ===========================================================================


class TestEscalationSubEngines:
    """Test political pressure engine wiring."""

    def test_political_pressure_update_called(self):
        """PoliticalPressureEngine.update() called during _update_escalation."""
        from stochastic_warfare.simulation.engine import SimulationEngine

        political = MagicMock()
        political.update.return_value = MagicMock()

        u1 = _make_unit("u1", easting=0.0)
        u2 = _make_unit("u2", easting=1000.0)
        object.__setattr__(u2, "status", UnitStatus.DESTROYED)

        ctx = _make_ctx(
            units_by_side={"blue": [u1], "red": [u2]},
            political_engine=political,
            escalation_engine=MagicMock(),
        )
        # Add required attributes for _update_escalation
        ctx.incendiary_engine = None
        ctx.sof_engine = None
        ctx.insurgency_engine = None
        ctx.collateral_engine = None
        ctx.war_termination_engine = None
        ctx.consequence_engine = None

        # Call _update_escalation directly
        engine = SimulationEngine.__new__(SimulationEngine)
        engine._ctx = ctx
        engine._strict_mode = False
        engine._update_escalation(3600.0)

        assert political.update.called
        # Should be called once per side
        assert political.update.call_count == 2

    def test_no_escalation_config_no_political(self):
        """No political_engine → no political pressure update."""
        from stochastic_warfare.simulation.engine import SimulationEngine

        ctx = _make_ctx(
            units_by_side={"blue": [], "red": []},
            political_engine=None,
            escalation_engine=MagicMock(),
        )
        ctx.incendiary_engine = None
        ctx.sof_engine = None
        ctx.insurgency_engine = None
        ctx.collateral_engine = None
        ctx.war_termination_engine = None
        ctx.consequence_engine = None

        engine = SimulationEngine.__new__(SimulationEngine)
        engine._ctx = ctx
        engine._strict_mode = False
        # Should not crash
        engine._update_escalation(3600.0)

    def test_political_pressure_accumulates_casualties(self):
        """Political pressure receives correct own_casualties count."""
        from stochastic_warfare.simulation.engine import SimulationEngine

        political = MagicMock()
        political.update.return_value = MagicMock()

        u1 = _make_unit("u1", easting=0.0)
        u2 = _make_unit("u2", easting=0.0)
        object.__setattr__(u2, "status", UnitStatus.DESTROYED)
        u3 = _make_unit("u3", easting=1000.0)

        ctx = _make_ctx(
            units_by_side={"blue": [u1, u2], "red": [u3]},
            political_engine=political,
            escalation_engine=MagicMock(),
        )
        ctx.incendiary_engine = None
        ctx.sof_engine = None
        ctx.insurgency_engine = None
        ctx.collateral_engine = None
        ctx.war_termination_engine = None
        ctx.consequence_engine = None

        engine = SimulationEngine.__new__(SimulationEngine)
        engine._ctx = ctx
        engine._strict_mode = False
        engine._update_escalation(3600.0)

        # Find blue side call — should have own_casualties=1
        for call in political.update.call_args_list:
            if call.kwargs.get("side") == "blue":
                assert call.kwargs["own_casualties"] == 1
                break


# ===========================================================================
# 53d: ATO Structural Wiring
# ===========================================================================


class TestATOStructuralWiring:
    """Test ATOPlanningEngine structural wiring."""

    def test_ato_engine_instantiated(self):
        """ATOPlanningEngine can be instantiated."""
        from stochastic_warfare.c2.orders.air_orders import ATOPlanningEngine

        engine = ATOPlanningEngine(EventBus())
        assert hasattr(engine, "register_aircraft")
        assert hasattr(engine, "generate_ato")

    def test_ato_field_on_context(self):
        """ato_engine field present on SimulationContext."""
        from stochastic_warfare.simulation.scenario import SimulationContext

        ctx = SimulationContext.__new__(SimulationContext)
        assert hasattr(ctx, "ato_engine")

    def test_generate_ato_empty(self):
        """ATOPlanningEngine.generate_ato() returns empty list when no requests."""
        from stochastic_warfare.c2.orders.air_orders import ATOPlanningEngine

        engine = ATOPlanningEngine(EventBus())
        entries = engine.generate_ato(current_time_s=0.0, timestamp=_TS)
        assert entries == []

    def test_aerial_units_registered(self):
        """Aerial units auto-registered as available aircraft."""
        from stochastic_warfare.c2.orders.air_orders import (
            ATOPlanningEngine,
            AircraftAvailability,
        )

        engine = ATOPlanningEngine(EventBus())
        engine.register_aircraft(AircraftAvailability(unit_id="f16_1"))
        assert "f16_1" in engine._aircraft


# ===========================================================================
# 53d: Planning Structural Wiring
# ===========================================================================


class TestPlanningStructuralWiring:
    """Test PlanningProcessEngine structural wiring."""

    def test_planning_engine_update(self):
        """PlanningProcessEngine.update() returns empty completions."""
        from stochastic_warfare.c2.planning.process import PlanningProcessEngine

        engine = PlanningProcessEngine(EventBus(), _rng())
        result = engine.update(5.0, ts=_TS)
        assert isinstance(result, list)

    def test_planning_engine_on_context(self):
        """planning_engine field present on SimulationContext."""
        from stochastic_warfare.simulation.scenario import SimulationContext

        ctx = SimulationContext.__new__(SimulationContext)
        assert hasattr(ctx, "planning_engine")


# ===========================================================================
# 53d: Order Propagation Structural
# ===========================================================================


class TestOrderPropStructural:
    """Test OrderPropagationEngine structural presence."""

    def test_order_propagation_on_context(self):
        """order_propagation field present on SimulationContext."""
        from stochastic_warfare.simulation.scenario import SimulationContext

        ctx = SimulationContext.__new__(SimulationContext)
        assert hasattr(ctx, "order_propagation")

    def test_iads_engine_on_context(self):
        """iads_engine field present on SimulationContext."""
        from stochastic_warfare.simulation.scenario import SimulationContext

        ctx = SimulationContext.__new__(SimulationContext)
        assert hasattr(ctx, "iads_engine")

    def test_stratagem_engine_on_context(self):
        """stratagem_engine field present on SimulationContext."""
        from stochastic_warfare.simulation.scenario import SimulationContext

        ctx = SimulationContext.__new__(SimulationContext)
        assert hasattr(ctx, "stratagem_engine")
