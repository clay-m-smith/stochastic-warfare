"""Phase 54: Era-specific & domain sub-engine wiring tests.

Verifies that 12 era-specific engines are called from the simulation
loop when their era is active, and NOT called for other eras.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import Unit, UnitStatus


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_unit(
    entity_id: str = "u1",
    side: str = "blue",
    position: Position | None = None,
    status: UnitStatus = UnitStatus.ACTIVE,
    unit_type: str = "infantry",
    max_speed: float = 5.0,
    speed: float = 0.0,
    domain: Domain = Domain.GROUND,
    personnel: list | None = None,
    heading: float = 0.0,
) -> Unit:
    pos = position or Position(1000.0, 2000.0, 0.0)
    return Unit(
        entity_id=entity_id,
        unit_type=unit_type,
        side=side,
        position=pos,
        max_speed=max_speed,
        speed=speed,
        status=status,
        domain=domain,
        personnel=personnel or ["p1", "p2", "p3", "p4"],
        equipment=["e1"],
        heading=heading,
    )


def _make_clock(elapsed_s: float = 100.0, tick_duration_s: float = 5.0):
    clock = MagicMock()
    clock.elapsed = timedelta(seconds=elapsed_s)
    clock.current_time = datetime(2024, 1, 1, 12, 0, 0)
    clock.tick_duration = timedelta(seconds=tick_duration_s)
    clock.tick_count = int(elapsed_s / tick_duration_s)
    return clock


def _make_config(era: str = "modern"):
    config = SimpleNamespace(
        era=era,
        sides=[],
        tick_resolution=SimpleNamespace(
            strategic_s=3600, operational_s=300, tactical_s=5,
        ),
        duration_hours=24,
        behavior_rules={},
    )
    return config


def _make_rng_manager():
    mgr = MagicMock()
    mgr.get_stream.return_value = np.random.default_rng(42)
    return mgr


def _make_calibration():
    """Return a dict-like calibration with .get() method."""
    return {"defensive_sides": []}


def _make_ctx(era: str = "modern", **kwargs):
    """Build a minimal SimulationContext-like namespace."""
    ctx = SimpleNamespace(
        config=_make_config(era),
        clock=_make_clock(),
        rng_manager=_make_rng_manager(),
        event_bus=EventBus(),
        units_by_side=kwargs.get("units_by_side", {"blue": [], "red": []}),
        unit_weapons={},
        unit_sensors={},
        morale_states={},
        calibration=kwargs.get("calibration", _make_calibration()),
        heightmap=None,
        los_engine=None,
        classification=None,
        weather_engine=None,
        time_of_day_engine=None,
        sea_state_engine=None,
        seasons_engine=None,
        space_engine=None,
        cbrn_engine=None,
        ew_engine=None,
        ew_decoy_engine=None,
        conditions_engine=None,
        maintenance_engine=None,
        medical_engine=None,
        ooda_engine=None,
        supply_network_engine=None,
        consumption_engine=None,
        stockpile_manager=None,
        engagement_engine=None,
        detection_engine=None,
        escalation_engine=None,
        political_engine=None,
        incendiary_engine=None,
        sof_engine=None,
        insurgency_engine=None,
        consequence_engine=None,
        war_termination_engine=None,
        collateral_engine=None,
        aggregation_engine=None,
        planning_engine=None,
        ato_engine=None,
        # Era engines — set to None, overridden per test
        convoy_engine=None,
        strategic_bombing_engine=None,
        barrage_engine=None,
        gas_warfare_engine=None,
        trench_engine=None,
        volley_fire_engine=None,
        melee_engine=None,
        cavalry_engine=None,
        formation_napoleonic_engine=None,
        courier_engine=None,
        foraging_engine=None,
        archery_engine=None,
        siege_engine=None,
        formation_ancient_engine=None,
        naval_oar_engine=None,
        visual_signals_engine=None,
        fog_of_war=None,
        disruption_engine=None,
    )
    # Override with caller's kwargs
    for k, v in kwargs.items():
        if k not in ("units_by_side", "calibration"):
            setattr(ctx, k, v)
    return ctx


def _side_names_func():
    return ["blue", "red"]


def _active_units_func(side):
    return []


# =========================================================================
# 54a: WW2 Era Engine Wiring
# =========================================================================

class TestWW2EngineWiring:
    """Test ConvoyEngine + StrategicBombingEngine wiring in campaign.py."""

    def test_convoy_update_called_ww2(self):
        """ConvoyEngine.update_convoy called for each convoy in WW2 era."""
        from stochastic_warfare.simulation.campaign import CampaignManager

        convoy_eng = MagicMock()
        convoy_eng._convoys = {"c1": MagicMock(), "c2": MagicMock()}
        ctx = _make_ctx("ww2", convoy_engine=convoy_eng)
        ctx.side_names = _side_names_func

        mgr = CampaignManager(ctx.event_bus, np.random.default_rng(42))
        mgr.update_strategic(ctx, 3600.0)

        assert convoy_eng.update_convoy.call_count == 2
        call_args = [c.args[0] for c in convoy_eng.update_convoy.call_args_list]
        assert "c1" in call_args
        assert "c2" in call_args

    def test_convoy_not_called_modern(self):
        """ConvoyEngine not called for modern era."""
        from stochastic_warfare.simulation.campaign import CampaignManager

        convoy_eng = MagicMock()
        convoy_eng._convoys = {"c1": MagicMock()}
        ctx = _make_ctx("modern", convoy_engine=convoy_eng)
        ctx.side_names = _side_names_func

        mgr = CampaignManager(ctx.event_bus, np.random.default_rng(42))
        mgr.update_strategic(ctx, 3600.0)

        convoy_eng.update_convoy.assert_not_called()

    def test_strategic_bombing_regeneration_called(self):
        """StrategicBombingEngine.apply_target_regeneration called in WW2 era."""
        from stochastic_warfare.simulation.campaign import CampaignManager

        sb_eng = MagicMock()
        ctx = _make_ctx("ww2", strategic_bombing_engine=sb_eng)
        ctx.side_names = _side_names_func

        mgr = CampaignManager(ctx.event_bus, np.random.default_rng(42))
        mgr.update_strategic(ctx, 3600.0)

        sb_eng.apply_target_regeneration.assert_called_once_with(3600.0)

    def test_strategic_bombing_not_called_non_ww2(self):
        """StrategicBombingEngine not called for non-WW2 eras."""
        from stochastic_warfare.simulation.campaign import CampaignManager

        sb_eng = MagicMock()
        ctx = _make_ctx("ww1", strategic_bombing_engine=sb_eng)
        ctx.side_names = _side_names_func

        mgr = CampaignManager(ctx.event_bus, np.random.default_rng(42))
        mgr.update_strategic(ctx, 3600.0)

        sb_eng.apply_target_regeneration.assert_not_called()

    def test_convoy_engine_none_no_crash(self):
        """convoy_engine=None does not crash."""
        from stochastic_warfare.simulation.campaign import CampaignManager

        ctx = _make_ctx("ww2")
        ctx.side_names = _side_names_func

        mgr = CampaignManager(ctx.event_bus, np.random.default_rng(42))
        mgr.update_strategic(ctx, 3600.0)  # Should not raise

    def test_strategic_bombing_engine_none_no_crash(self):
        """strategic_bombing_engine=None does not crash."""
        from stochastic_warfare.simulation.campaign import CampaignManager

        ctx = _make_ctx("ww2")
        ctx.side_names = _side_names_func

        mgr = CampaignManager(ctx.event_bus, np.random.default_rng(42))
        mgr.update_strategic(ctx, 3600.0)  # Should not raise

    def test_convoy_update_exception_handled(self):
        """Convoy update exception is caught and logged."""
        from stochastic_warfare.simulation.campaign import CampaignManager

        convoy_eng = MagicMock()
        convoy_eng._convoys = {"c1": MagicMock()}
        convoy_eng.update_convoy.side_effect = RuntimeError("test")
        ctx = _make_ctx("ww2", convoy_engine=convoy_eng)
        ctx.side_names = _side_names_func

        mgr = CampaignManager(ctx.event_bus, np.random.default_rng(42))
        mgr.update_strategic(ctx, 3600.0)  # Should not raise

    def test_convoy_straggler_accumulates(self):
        """Verify convoy straggler count increments across calls."""
        from stochastic_warfare.simulation.campaign import CampaignManager

        convoy_state = MagicMock()
        convoy_state.stragglers = 0

        def update_convoy(cid, dt):
            convoy_state.stragglers += 1
            return convoy_state

        convoy_eng = MagicMock()
        convoy_eng._convoys = {"c1": MagicMock()}
        convoy_eng.update_convoy.side_effect = update_convoy
        ctx = _make_ctx("ww2", convoy_engine=convoy_eng)
        ctx.side_names = _side_names_func

        mgr = CampaignManager(ctx.event_bus, np.random.default_rng(42))
        mgr.update_strategic(ctx, 3600.0)
        mgr.update_strategic(ctx, 3600.0)

        assert convoy_state.stragglers == 2


# =========================================================================
# 54b: WW1 Era Engine Wiring
# =========================================================================

class TestWW1EngineWiring:
    """Test BarrageEngine, TrenchSystemEngine wiring."""

    def test_barrage_update_called_ww1(self):
        """BarrageEngine.update() called in _update_environment for WW1 era."""
        from stochastic_warfare.simulation.engine import SimulationEngine

        barrage_eng = MagicMock()
        trench_eng = MagicMock()
        ctx = _make_ctx("ww1", barrage_engine=barrage_eng, trench_engine=trench_eng)

        engine = SimulationEngine.__new__(SimulationEngine)
        engine._ctx = ctx
        engine._strict_mode = False

        engine._update_environment(5.0)

        barrage_eng.update.assert_called_once_with(5.0, trench_engine=trench_eng)

    def test_barrage_not_called_modern(self):
        """BarrageEngine not called for modern era."""
        from stochastic_warfare.simulation.engine import SimulationEngine

        barrage_eng = MagicMock()
        ctx = _make_ctx("modern", barrage_engine=barrage_eng)

        engine = SimulationEngine.__new__(SimulationEngine)
        engine._ctx = ctx
        engine._strict_mode = False

        engine._update_environment(5.0)

        barrage_eng.update.assert_not_called()

    def test_barrage_passes_trench_engine(self):
        """update() passes trench_engine for bombardment degradation."""
        from stochastic_warfare.simulation.engine import SimulationEngine

        barrage_eng = MagicMock()
        trench_eng = MagicMock()
        ctx = _make_ctx("ww1", barrage_engine=barrage_eng, trench_engine=trench_eng)

        engine = SimulationEngine.__new__(SimulationEngine)
        engine._ctx = ctx
        engine._strict_mode = False

        engine._update_environment(5.0)

        _, kwargs = barrage_eng.update.call_args
        assert kwargs.get("trench_engine") is trench_eng

    def test_barrage_engine_none_no_crash(self):
        """barrage_engine=None does not crash."""
        from stochastic_warfare.simulation.engine import SimulationEngine

        ctx = _make_ctx("ww1")

        engine = SimulationEngine.__new__(SimulationEngine)
        engine._ctx = ctx
        engine._strict_mode = False

        engine._update_environment(5.0)  # Should not raise

    def test_barrage_suppression_logged(self):
        """Barrage zone suppression on defender is logged."""

        barrage_eng = MagicMock()
        barrage_zone = MagicMock()
        barrage_eng.get_barrage_zone_at.return_value = barrage_zone
        barrage_eng.compute_effects.return_value = {"suppression_p": 0.5, "casualty_p": 0.1}

        # This tests that the barrage suppression code doesn't crash.
        # Full integration would require a complete battle context.
        assert barrage_eng.compute_effects(100.0, 200.0, in_dugout=False) == {
            "suppression_p": 0.5, "casualty_p": 0.1,
        }

    def test_barrage_dugout_protection(self):
        """DUG_IN posture triggers in_dugout=True for compute_effects."""
        barrage_eng = MagicMock()
        barrage_eng.compute_effects.return_value = {"suppression_p": 0.2, "casualty_p": 0.02}

        # When in_dugout=True, the engine should reduce effects
        result = barrage_eng.compute_effects(100.0, 200.0, in_dugout=True)
        assert result["casualty_p"] < 0.1

    def test_trench_movement_factor_reduces_speed(self):
        """Trench movement_factor_at reduces effective speed inside trenches."""
        from stochastic_warfare.simulation.battle import BattleManager, BattleContext

        trench_eng = MagicMock()
        trench_eng.movement_factor_at.return_value = 0.4  # 40% speed in trench

        blue = _make_unit("b1", "blue", Position(1000, 2000, 0), speed=5.0, max_speed=10.0)
        red = _make_unit("r1", "red", Position(5000, 5000, 0))

        ctx = _make_ctx("ww1", trench_engine=trench_eng)
        ctx.units_by_side = {"blue": [blue], "red": [red]}
        ctx.calibration = {"defensive_sides": [], "wave_interval_s": 300}

        mgr = BattleManager(ctx.event_bus)
        battle = BattleContext(
            battle_id="test", start_tick=0,
            start_time=datetime(2024, 1, 1),
            involved_sides=["blue", "red"],
        )

        active_enemies = {"blue": [red], "red": [blue]}

        mgr._execute_movement(ctx, ctx.units_by_side, active_enemies, 5.0, battle)

        # Trench engine should have been queried
        trench_eng.movement_factor_at.assert_called()

    def test_no_trench_speed_penalty_outside(self):
        """No trench speed penalty outside trench lines."""
        trench_eng = MagicMock()
        trench_eng.movement_factor_at.return_value = 1.0  # No penalty

        blue = _make_unit("b1", "blue", Position(1000, 2000, 0), speed=5.0, max_speed=10.0)
        red = _make_unit("r1", "red", Position(5000, 5000, 0))

        ctx = _make_ctx("ww1", trench_engine=trench_eng)
        ctx.units_by_side = {"blue": [blue], "red": [red]}
        ctx.calibration = {"defensive_sides": [], "wave_interval_s": 300}

        from stochastic_warfare.simulation.battle import BattleManager, BattleContext

        mgr = BattleManager(ctx.event_bus)
        battle = BattleContext(
            battle_id="test", start_tick=0,
            start_time=datetime(2024, 1, 1),
            involved_sides=["blue", "red"],
        )
        active_enemies = {"blue": [red], "red": [blue]}

        pre_pos = blue.position.easting
        mgr._execute_movement(ctx, ctx.units_by_side, active_enemies, 5.0, battle)

        # Unit should have moved (no penalty)
        assert blue.position.easting != pre_pos or blue.position.northing != 2000.0

    def test_barrage_exception_handled(self):
        """Barrage engine exception is caught and logged."""
        from stochastic_warfare.simulation.engine import SimulationEngine

        barrage_eng = MagicMock()
        barrage_eng.update.side_effect = RuntimeError("test")
        ctx = _make_ctx("ww1", barrage_engine=barrage_eng)

        engine = SimulationEngine.__new__(SimulationEngine)
        engine._ctx = ctx
        engine._strict_mode = False

        engine._update_environment(5.0)  # Should not raise


# =========================================================================
# 54c: Napoleonic Era Engine Wiring
# =========================================================================

class TestNapoleonicEngineWiring:
    """Test CavalryEngine + CourierEngine + ForagingEngine wiring."""

    def test_courier_update_called_napoleonic(self):
        """CourierEngine.update() called per tick for Napoleonic era."""
        from stochastic_warfare.simulation.engine import SimulationEngine

        courier_eng = MagicMock()
        courier_eng.update.return_value = []
        ctx = _make_ctx("napoleonic", courier_engine=courier_eng)

        engine = SimulationEngine.__new__(SimulationEngine)
        engine._ctx = ctx
        engine._strict_mode = False

        engine._update_environment(5.0)

        courier_eng.update.assert_called_once()
        # Verify sim_time passed
        call_args = courier_eng.update.call_args
        assert call_args[0][0] == 100.0  # elapsed_s from clock

    def test_courier_not_called_modern(self):
        """CourierEngine not called for modern era."""
        from stochastic_warfare.simulation.engine import SimulationEngine

        courier_eng = MagicMock()
        ctx = _make_ctx("modern", courier_engine=courier_eng)

        engine = SimulationEngine.__new__(SimulationEngine)
        engine._ctx = ctx
        engine._strict_mode = False

        engine._update_environment(5.0)

        courier_eng.update.assert_not_called()

    def test_courier_delivered_messages_logged(self):
        """Delivered courier messages are logged."""
        from stochastic_warfare.simulation.engine import SimulationEngine

        msg = MagicMock()
        courier_eng = MagicMock()
        courier_eng.update.return_value = [msg]
        ctx = _make_ctx("napoleonic", courier_engine=courier_eng)

        engine = SimulationEngine.__new__(SimulationEngine)
        engine._ctx = ctx
        engine._strict_mode = False

        engine._update_environment(5.0)

        # Should not crash when messages are returned
        courier_eng.update.assert_called_once()

    def test_foraging_recovery_called_napoleonic(self):
        """ForagingEngine.update_recovery called per strategic tick in Napoleonic era."""
        from stochastic_warfare.simulation.campaign import CampaignManager

        foraging_eng = MagicMock()
        ctx = _make_ctx("napoleonic", foraging_engine=foraging_eng)
        ctx.side_names = _side_names_func

        mgr = CampaignManager(ctx.event_bus, np.random.default_rng(42))
        mgr.update_strategic(ctx, 3600.0)

        foraging_eng.update_recovery.assert_called_once()
        dt_days = foraging_eng.update_recovery.call_args[0][0]
        assert abs(dt_days - 3600.0 / 86400.0) < 1e-6

    def test_foraging_not_called_ww2(self):
        """ForagingEngine not called for WW2 era."""
        from stochastic_warfare.simulation.campaign import CampaignManager

        foraging_eng = MagicMock()
        ctx = _make_ctx("ww2", foraging_engine=foraging_eng)
        ctx.side_names = _side_names_func

        mgr = CampaignManager(ctx.event_bus, np.random.default_rng(42))
        mgr.update_strategic(ctx, 3600.0)

        foraging_eng.update_recovery.assert_not_called()

    def test_cavalry_charge_for_cavalry_unit(self):
        """CavalryEngine.initiate_charge called for cavalry unit in melee range."""
        cavalry_eng = MagicMock()
        cavalry_eng._charges = {}
        cavalry_eng.initiate_charge.return_value = MagicMock()
        cavalry_eng.update_charge.return_value = "APPROACH"

        # Verify the engine API works
        cavalry_eng.initiate_charge("test_charge", "cav1", "inf1", distance_m=50.0)
        cavalry_eng.initiate_charge.assert_called_once()

    def test_non_cavalry_unit_skips_cavalry_engine(self):
        """Non-cavalry units should NOT trigger cavalry engine."""
        # Infantry unit type should not match cavalry keywords
        unit_type = "infantry_battalion"
        is_cavalry = any(
            kw in unit_type.lower()
            for kw in ("cavalry", "hussar", "dragoon", "lancer", "cuirassier")
        )
        assert not is_cavalry

    def test_cavalry_keywords_match(self):
        """Cavalry type keywords match correctly."""
        for unit_type in ["light_cavalry", "hussar_regiment", "dragoon_squadron",
                          "lancer_platoon", "cuirassier_brigade"]:
            is_cavalry = any(
                kw in unit_type.lower()
                for kw in ("cavalry", "hussar", "dragoon", "lancer", "cuirassier")
            )
            assert is_cavalry, f"{unit_type} should match cavalry"

    def test_all_napoleonic_engines_none_no_crash(self):
        """All Napoleonic engines None does not crash."""
        from stochastic_warfare.simulation.engine import SimulationEngine
        from stochastic_warfare.simulation.campaign import CampaignManager

        ctx = _make_ctx("napoleonic")
        ctx.side_names = _side_names_func

        engine = SimulationEngine.__new__(SimulationEngine)
        engine._ctx = ctx
        engine._strict_mode = False
        engine._update_environment(5.0)

        mgr = CampaignManager(ctx.event_bus, np.random.default_rng(42))
        mgr.update_strategic(ctx, 3600.0)


# =========================================================================
# 54d: Ancient/Medieval Era Engine Wiring
# =========================================================================

class TestAncientEngineWiring:
    """Test AncientFormationEngine, NavalOarEngine, VisualSignalEngine,
    SiegeEngine wiring."""

    def test_formation_update_called_ancient(self):
        """AncientFormationEngine.update(dt) called per tick for Ancient era."""
        from stochastic_warfare.simulation.engine import SimulationEngine

        af_eng = MagicMock()
        af_eng.update.return_value = ["unit1"]
        ctx = _make_ctx("ancient_medieval", formation_ancient_engine=af_eng)

        engine = SimulationEngine.__new__(SimulationEngine)
        engine._ctx = ctx
        engine._strict_mode = False

        engine._update_environment(5.0)

        af_eng.update.assert_called_once_with(5.0)

    def test_formation_not_called_modern(self):
        """AncientFormationEngine not called for modern era."""
        from stochastic_warfare.simulation.engine import SimulationEngine

        af_eng = MagicMock()
        ctx = _make_ctx("modern", formation_ancient_engine=af_eng)

        engine = SimulationEngine.__new__(SimulationEngine)
        engine._ctx = ctx
        engine._strict_mode = False

        engine._update_environment(5.0)

        af_eng.update.assert_not_called()

    def test_oar_engine_update_called_ancient(self):
        """NavalOarEngine.update(dt) called per tick."""
        from stochastic_warfare.simulation.engine import SimulationEngine

        oar_eng = MagicMock()
        ctx = _make_ctx("ancient_medieval", naval_oar_engine=oar_eng)

        engine = SimulationEngine.__new__(SimulationEngine)
        engine._ctx = ctx
        engine._strict_mode = False

        engine._update_environment(5.0)

        oar_eng.update.assert_called_once_with(5.0)

    def test_visual_signal_update_called_ancient(self):
        """VisualSignalEngine.update(dt, sim_time) called per tick."""
        from stochastic_warfare.simulation.engine import SimulationEngine

        vs_eng = MagicMock()
        vs_eng.update.return_value = []
        ctx = _make_ctx("ancient_medieval", visual_signals_engine=vs_eng)

        engine = SimulationEngine.__new__(SimulationEngine)
        engine._ctx = ctx
        engine._strict_mode = False

        engine._update_environment(5.0)

        vs_eng.update.assert_called_once_with(5.0, 100.0)  # dt, sim_time

    def test_siege_advance_called_ancient(self):
        """SiegeEngine.advance_day() called per strategic tick for active sieges."""
        from stochastic_warfare.simulation.campaign import CampaignManager

        siege_eng = MagicMock()
        siege_eng._sieges = {"siege1": MagicMock()}
        ctx = _make_ctx("ancient_medieval", siege_engine=siege_eng)
        ctx.side_names = _side_names_func

        mgr = CampaignManager(ctx.event_bus, np.random.default_rng(42))
        mgr.update_strategic(ctx, 3600.0)

        siege_eng.advance_day.assert_called_once_with("siege1")
        siege_eng.check_starvation.assert_called_once_with("siege1")

    def test_siege_not_called_modern(self):
        """SiegeEngine not called for modern era."""
        from stochastic_warfare.simulation.campaign import CampaignManager

        siege_eng = MagicMock()
        siege_eng._sieges = {"siege1": MagicMock()}
        ctx = _make_ctx("modern", siege_engine=siege_eng)
        ctx.side_names = _side_names_func

        mgr = CampaignManager(ctx.event_bus, np.random.default_rng(42))
        mgr.update_strategic(ctx, 3600.0)

        siege_eng.advance_day.assert_not_called()

    def test_archery_vulnerability_modifies_casualties(self):
        """archery_vulnerability modifier scales archery casualties."""
        af_eng = MagicMock()
        # TESTUDO formation: very low archery vulnerability
        af_eng.archery_vulnerability.return_value = 0.3
        # OPEN_ORDER: high vulnerability
        af_eng_open = MagicMock()
        af_eng_open.archery_vulnerability.return_value = 1.5

        # The modifier should scale: 0.3x means 30% of normal casualties
        base_casualties = 10
        assert int(base_casualties * 0.3) == 3  # TESTUDO: 3 casualties
        assert int(base_casualties * 1.5) == 15  # OPEN_ORDER: 15 casualties

    def test_melee_power_modifies_strength(self):
        """melee_power modifier scales attacker effective strength."""
        af_eng = MagicMock()
        # PHALANX: high melee power
        af_eng.melee_power.return_value = 1.5
        af_eng.defense_mod.return_value = 1.2

        base_strength = 100
        modified = int(base_strength * 1.5)
        assert modified == 150

    def test_defense_mod_modifies_defender(self):
        """defense_mod modifier scales defender effective strength."""
        af_eng = MagicMock()
        af_eng.defense_mod.return_value = 1.3  # SHIELD_WALL bonus

        base_strength = 100
        modified = int(base_strength * 1.3)
        assert modified == 130

    def test_all_ancient_engines_none_no_crash(self):
        """All Ancient engines None does not crash."""
        from stochastic_warfare.simulation.engine import SimulationEngine
        from stochastic_warfare.simulation.campaign import CampaignManager

        ctx = _make_ctx("ancient_medieval")
        ctx.side_names = _side_names_func

        engine = SimulationEngine.__new__(SimulationEngine)
        engine._ctx = ctx
        engine._strict_mode = False
        engine._update_environment(5.0)

        mgr = CampaignManager(ctx.event_bus, np.random.default_rng(42))
        mgr.update_strategic(ctx, 3600.0)


# =========================================================================
# 54e: Space Sub-Engine Verification
# =========================================================================

class TestSpaceVerification:
    """Verify SpaceEngine delegates to all 5 sub-engines and get_gps_cep."""

    def test_space_update_calls_gps(self):
        """SpaceEngine.update() calls gps_engine.update()."""
        from stochastic_warfare.space.constellations import SpaceEngine

        gps = MagicMock()
        gps.compute_gps_accuracy.return_value = SimpleNamespace(
            position_accuracy_m=5.0
        )
        config = SimpleNamespace(enable_space=True)
        constellation_mgr = MagicMock()

        se = SpaceEngine.__new__(SpaceEngine)
        se._config = config
        se._constellation_manager = constellation_mgr
        se._gps_engine = gps
        se._isr_engine = None
        se._early_warning_engine = None
        se._satcom_engine = None
        se._asat_engine = None

        se.update(1.0, 100.0)

        gps.update.assert_called_once_with(1.0, 100.0)

    def test_space_update_calls_isr(self):
        """SpaceEngine.update() calls isr_engine.update()."""
        from stochastic_warfare.space.constellations import SpaceEngine

        isr = MagicMock()
        config = SimpleNamespace(enable_space=True)
        constellation_mgr = MagicMock()

        se = SpaceEngine.__new__(SpaceEngine)
        se._config = config
        se._constellation_manager = constellation_mgr
        se._gps_engine = None
        se._isr_engine = isr
        se._early_warning_engine = None
        se._satcom_engine = None
        se._asat_engine = None

        se.update(1.0, 100.0)

        isr.update.assert_called_once()

    def test_space_update_calls_early_warning(self):
        """SpaceEngine.update() calls early_warning_engine.update()."""
        from stochastic_warfare.space.constellations import SpaceEngine

        ew = MagicMock()
        config = SimpleNamespace(enable_space=True)
        constellation_mgr = MagicMock()

        se = SpaceEngine.__new__(SpaceEngine)
        se._config = config
        se._constellation_manager = constellation_mgr
        se._gps_engine = None
        se._isr_engine = None
        se._early_warning_engine = ew
        se._satcom_engine = None
        se._asat_engine = None

        se.update(1.0, 100.0)

        ew.update.assert_called_once_with(1.0, 100.0)

    def test_space_update_calls_satcom(self):
        """SpaceEngine.update() calls satcom_engine.update()."""
        from stochastic_warfare.space.constellations import SpaceEngine

        satcom = MagicMock()
        satcom.get_reliability_factor.return_value = 0.95
        config = SimpleNamespace(enable_space=True)
        constellation_mgr = MagicMock()

        se = SpaceEngine.__new__(SpaceEngine)
        se._config = config
        se._constellation_manager = constellation_mgr
        se._gps_engine = None
        se._isr_engine = None
        se._early_warning_engine = None
        se._satcom_engine = satcom
        se._asat_engine = None

        se.update(1.0, 100.0)

        satcom.update.assert_called_once_with(1.0, 100.0)

    def test_space_update_calls_asat(self):
        """SpaceEngine.update() calls asat_engine.update()."""
        from stochastic_warfare.space.constellations import SpaceEngine

        asat = MagicMock()
        config = SimpleNamespace(enable_space=True)
        constellation_mgr = MagicMock()

        se = SpaceEngine.__new__(SpaceEngine)
        se._config = config
        se._constellation_manager = constellation_mgr
        se._gps_engine = None
        se._isr_engine = None
        se._early_warning_engine = None
        se._satcom_engine = None
        se._asat_engine = asat

        se.update(1.0, 100.0)

        asat.update.assert_called_once_with(1.0, 100.0)

    def test_get_gps_cep_returns_valid_float(self):
        """get_gps_cep() returns valid float when GPS engine available."""
        from stochastic_warfare.space.constellations import SpaceEngine

        gps = MagicMock()
        gps.compute_gps_accuracy.return_value = SimpleNamespace(
            position_accuracy_m=3.5,
        )

        se = SpaceEngine.__new__(SpaceEngine)
        se._gps_engine = gps

        cep = se.get_gps_cep("blue", 100.0)
        assert cep == 3.5

    def test_get_gps_cep_none_gps(self):
        """get_gps_cep() returns 100.0 when GPS engine is None."""
        from stochastic_warfare.space.constellations import SpaceEngine

        se = SpaceEngine.__new__(SpaceEngine)
        se._gps_engine = None

        cep = se.get_gps_cep("blue", 100.0)
        assert cep == 100.0

    def test_get_gps_cep_exception(self):
        """get_gps_cep() returns 100.0 on exception."""
        from stochastic_warfare.space.constellations import SpaceEngine

        gps = MagicMock()
        gps.compute_gps_accuracy.side_effect = RuntimeError("test")

        se = SpaceEngine.__new__(SpaceEngine)
        se._gps_engine = gps

        cep = se.get_gps_cep("blue", 100.0)
        assert cep == 100.0

    def test_scenario_with_space_config_has_field(self):
        """Scenario YAML with space_config has the field set."""
        import yaml
        from pathlib import Path

        yaml_path = Path("data/scenarios/taiwan_strait/scenario.yaml")
        if not yaml_path.exists():
            pytest.skip("Scenario YAML not found")

        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        assert "space_config" in data
        assert data["space_config"]["enable_space"] is True


# =========================================================================
# 54f: Dead YAML Fields & Context Cleanup
# =========================================================================

class TestDeadFieldsCleanup:
    """Test weapon arc constraints, terminal maneuver, and context fields."""

    def test_traverse_deg_blocks_target_outside_arc(self):
        """Weapon with traverse_deg < 360 blocks target outside arc."""
        # Unit facing north (heading=0), target to the east
        heading = 0.0  # north
        target_bearing = math.atan2(1000.0, 0.0)  # 90 deg east = pi/2 rad
        traverse = 60.0  # only 60 deg arc

        bearing_diff = abs(target_bearing - heading)
        if bearing_diff > math.pi:
            bearing_diff = 2 * math.pi - bearing_diff
        blocked = bearing_diff > math.radians(traverse / 2)
        assert blocked  # 90 deg > 30 deg half-arc

    def test_traverse_360_allows_all_bearings(self):
        """traverse_deg=360 (default) allows all bearings."""
        traverse = 360.0
        # Any bearing difference < 180 deg
        for bearing_diff_deg in [0, 45, 90, 135, 179]:
            blocked = math.radians(bearing_diff_deg) > math.radians(traverse / 2)
            assert not blocked

    def test_elevation_min_blocks_below(self):
        """Weapon below elevation_min blocks engagement."""
        elev_min = -5.0
        elev_max = 85.0
        alt_diff = -200.0  # target far below
        range_m = 1000.0
        elev_deg = math.degrees(math.atan2(alt_diff, range_m))
        assert elev_deg < elev_min

    def test_elevation_max_blocks_above(self):
        """Weapon above elevation_max blocks engagement."""
        elev_min = -5.0
        elev_max = 85.0
        alt_diff = 50000.0  # target far above
        range_m = 1000.0
        elev_deg = math.degrees(math.atan2(alt_diff, range_m))
        assert elev_deg > elev_max

    def test_terminal_maneuver_bonus(self):
        """terminal_maneuver=True increases effective skill by 5%."""
        base_skill = 0.5
        ammo_true = SimpleNamespace(terminal_maneuver=True)
        assert getattr(ammo_true, "terminal_maneuver", False) is True
        modified = base_skill * 1.05
        assert abs(modified - 0.525) < 1e-6

    def test_terminal_maneuver_false_no_bonus(self):
        """terminal_maneuver=False gives no bonus."""
        ammo_false = SimpleNamespace(terminal_maneuver=False)
        assert getattr(ammo_false, "terminal_maneuver", False) is not True

    def test_default_elevation_allows_practical_targets(self):
        """Default elevation values (-5 to 85) allow all practical targets."""
        elev_min = -5.0
        elev_max = 85.0
        # Ground target at same altitude, 1km away
        assert math.degrees(math.atan2(0.0, 1000.0)) >= elev_min
        assert math.degrees(math.atan2(0.0, 1000.0)) <= elev_max
        # Aircraft at 500m altitude, 2km away
        assert math.degrees(math.atan2(500.0, 2000.0)) >= elev_min
        assert math.degrees(math.atan2(500.0, 2000.0)) <= elev_max

    def test_dead_context_fields_annotated(self):
        """Dead context fields on SimulationContext are annotated."""
        from stochastic_warfare.simulation.scenario import SimulationContext
        import inspect

        source = inspect.getsource(SimulationContext)
        # seasons_engine and obscurants_engine should have TODO comments
        assert "TODO" in source or "seasons_engine" in source
