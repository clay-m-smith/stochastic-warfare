"""Phase 12f — Strategic Air Campaigns & IADS tests.

Tests for:
- 12f-1: IADS model
- 12f-2: Air campaign management
- 12f-3: Strategic targeting
- 12f-4: Strategic infrastructure nodes
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import ModuleId, Position

from tests.conftest import TS, make_rng

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rng(seed: int = 42) -> np.random.Generator:
    return make_rng(seed)


def _event_bus() -> EventBus:
    return EventBus()


def _make_iads_sector(sector_id="sec1"):
    from stochastic_warfare.combat.iads import IadsSector
    return IadsSector(
        sector_id=sector_id,
        center=Position(0, 0, 0),
        radius_m=50000.0,
        early_warning_radars=["ew1", "ew2"],
        acquisition_radars=["acq1"],
        sam_batteries=["sam1", "sam2"],
        aaa_positions=["aaa1"],
        command_node="cmd1",
    )


# ===================================================================
# 12f-1: IADS Model
# ===================================================================


class TestIadsRegistration:
    """IADS sector registration and component health."""

    def test_register_sector(self):
        from stochastic_warfare.combat.iads import IadsEngine
        eng = IadsEngine(_event_bus(), _rng())
        eng.register_sector(_make_iads_sector())
        sector = eng.get_sector("sec1")
        assert len(sector.sam_batteries) == 2

    def test_components_initialized_healthy(self):
        from stochastic_warfare.combat.iads import IadsEngine
        eng = IadsEngine(_event_bus(), _rng())
        eng.register_sector(_make_iads_sector())
        sector = eng.get_sector("sec1")
        for cid in ["ew1", "ew2", "acq1", "sam1", "sam2", "aaa1", "cmd1"]:
            assert sector.component_health[cid] == 1.0

    def test_get_sector_raises_keyerror(self):
        from stochastic_warfare.combat.iads import IadsEngine
        eng = IadsEngine(_event_bus(), _rng())
        with pytest.raises(KeyError):
            eng.get_sector("nonexistent")


class TestIadsProcessAirTrack:
    """IADS radar handoff chain processing."""

    def test_healthy_sector_full_capability(self):
        from stochastic_warfare.combat.iads import IadsEngine
        eng = IadsEngine(_event_bus(), _rng())
        eng.register_sector(_make_iads_sector())
        result = eng.process_air_track("sec1", Position(10000, 10000, 5000))
        assert result["ew_available"] is True
        assert result["acq_available"] is True
        assert result["sam_available"] is True
        assert result["autonomous"] is False
        assert result["effectiveness"] > 0

    def test_destroyed_ew_increases_handoff(self):
        from stochastic_warfare.combat.iads import IadsConfig, IadsEngine
        cfg = IadsConfig(ew_to_acq_handoff_s=10.0, acq_to_sam_handoff_s=5.0)
        eng = IadsEngine(_event_bus(), _rng(), cfg)
        eng.register_sector(_make_iads_sector())
        # Destroy early warning
        sector = eng.get_sector("sec1")
        sector.component_health["ew1"] = 0.0
        sector.component_health["ew2"] = 0.0
        result = eng.process_air_track("sec1", Position(0, 0, 5000))
        assert result["ew_available"] is False
        # Should have penalty handoff time
        assert result["handoff_time_s"] > 15.0

    def test_destroyed_command_node_autonomous(self):
        from stochastic_warfare.combat.iads import IadsConfig, IadsEngine
        cfg = IadsConfig(autonomous_effectiveness_mult=0.4)
        eng = IadsEngine(_event_bus(), _rng(), cfg)
        eng.register_sector(_make_iads_sector())
        # Get baseline
        r_full = eng.process_air_track("sec1", Position(0, 0, 5000))
        # Destroy command node
        sector = eng.get_sector("sec1")
        sector.component_health["cmd1"] = 0.0
        r_auto = eng.process_air_track("sec1", Position(0, 0, 5000))
        assert r_auto["autonomous"] is True
        assert r_auto["effectiveness"] < r_full["effectiveness"]


class TestIadsSectorHealth:
    """compute_sector_health compound metric."""

    def test_fully_healthy_sector(self):
        from stochastic_warfare.combat.iads import IadsEngine
        eng = IadsEngine(_event_bus(), _rng())
        eng.register_sector(_make_iads_sector())
        health = eng.compute_sector_health("sec1")
        assert health > 0.5

    def test_all_destroyed_near_zero(self):
        from stochastic_warfare.combat.iads import IadsEngine
        eng = IadsEngine(_event_bus(), _rng())
        eng.register_sector(_make_iads_sector())
        sector = eng.get_sector("sec1")
        for cid in sector.component_health:
            sector.component_health[cid] = 0.0
        health = eng.compute_sector_health("sec1")
        assert health < 0.01


class TestIadsSead:
    """apply_sead_damage degrades components."""

    def test_sead_reduces_health(self):
        from stochastic_warfare.combat.iads import IadsEngine
        eng = IadsEngine(_event_bus(), _rng())
        eng.register_sector(_make_iads_sector())
        new_health = eng.apply_sead_damage("sec1", "sam1")
        assert new_health < 1.0

    def test_repeated_sead_destroys(self):
        from stochastic_warfare.combat.iads import IadsConfig, IadsEngine
        cfg = IadsConfig(sead_degradation_rate=0.5)
        eng = IadsEngine(_event_bus(), _rng(), cfg)
        eng.register_sector(_make_iads_sector())
        for _ in range(10):
            eng.apply_sead_damage("sec1", "ew1")
        sector = eng.get_sector("sec1")
        assert sector.component_health["ew1"] < 0.1

    def test_iads_state_serialization(self):
        from stochastic_warfare.combat.iads import IadsEngine
        eng = IadsEngine(_event_bus(), _rng())
        eng.register_sector(_make_iads_sector())
        eng.apply_sead_damage("sec1", "sam1")
        state = eng.get_state()
        eng2 = IadsEngine(_event_bus(), _rng())
        eng2.set_state(state)
        s2 = eng2.get_sector("sec1")
        assert s2.component_health["sam1"] < 1.0


# ===================================================================
# 12f-2: Air Campaign Management
# ===================================================================


class TestAirCampaignSortieCapacity:
    """compute_daily_sortie_capacity."""

    def test_basic_capacity(self):
        from stochastic_warfare.combat.air_campaign import AirCampaignEngine
        eng = AirCampaignEngine(_event_bus(), _rng())
        cap = eng.compute_daily_sortie_capacity(50, mission_capable_rate=1.0)
        assert cap > 0

    def test_zero_aircraft(self):
        from stochastic_warfare.combat.air_campaign import AirCampaignEngine
        eng = AirCampaignEngine(_event_bus(), _rng())
        assert eng.compute_daily_sortie_capacity(0) == 0

    def test_capped_at_max(self):
        from stochastic_warfare.combat.air_campaign import AirCampaignConfig, AirCampaignEngine
        cfg = AirCampaignConfig(max_sorties_per_day=50)
        eng = AirCampaignEngine(_event_bus(), _rng(), cfg)
        cap = eng.compute_daily_sortie_capacity(1000)
        assert cap <= 50


class TestPilotFatigue:
    """Pilot fatigue tracking and performance degradation."""

    def test_fatigue_increases(self):
        from stochastic_warfare.combat.air_campaign import AirCampaignEngine
        eng = AirCampaignEngine(_event_bus(), _rng())
        eng.register_pilot("p1")
        eng.update_pilot_fatigue("p1", missions_today=2)
        assert eng.get_pilot("p1").fatigue > 0

    def test_heavy_fatigue_reduces_performance(self):
        from stochastic_warfare.combat.air_campaign import AirCampaignConfig, AirCampaignEngine
        cfg = AirCampaignConfig(fatigue_per_mission=0.3, fatigue_performance_threshold=0.5)
        eng = AirCampaignEngine(_event_bus(), _rng(), cfg)
        eng.register_pilot("p1")
        perf = eng.update_pilot_fatigue("p1", missions_today=3)
        assert perf < 1.0  # 0.9 fatigue > 0.5 threshold

    def test_fatigue_recovery(self):
        from stochastic_warfare.combat.air_campaign import AirCampaignConfig, AirCampaignEngine
        cfg = AirCampaignConfig(fatigue_per_mission=0.2, fatigue_recovery_per_day=0.3)
        eng = AirCampaignEngine(_event_bus(), _rng(), cfg)
        eng.register_pilot("p1")
        eng.update_pilot_fatigue("p1", missions_today=2)
        initial_fatigue = eng.get_pilot("p1").fatigue
        eng.recover_fatigue()
        assert eng.get_pilot("p1").fatigue < initial_fatigue


class TestWeatherDay:
    """check_weather_day sortie cancellation."""

    def test_clear_weather_full_sorties(self):
        from stochastic_warfare.combat.air_campaign import AirCampaignEngine
        eng = AirCampaignEngine(_event_bus(), _rng())
        assert eng.check_weather_day(1.0) == 1.0

    def test_bad_weather_cancels(self):
        from stochastic_warfare.combat.air_campaign import AirCampaignEngine
        eng = AirCampaignEngine(_event_bus(), _rng())
        assert eng.check_weather_day(0.1) == 0.0

    def test_marginal_weather_partial(self):
        from stochastic_warfare.combat.air_campaign import AirCampaignEngine
        eng = AirCampaignEngine(_event_bus(), _rng())
        frac = eng.check_weather_day(0.6)
        assert 0.0 < frac < 1.0


class TestAttrition:
    """update_attrition fleet dynamics."""

    def test_losses_reduce_fleet(self):
        from stochastic_warfare.combat.air_campaign import AirCampaignEngine
        eng = AirCampaignEngine(_event_bus(), _rng())
        eng.set_fleet_size(100)
        result = eng.update_attrition(losses=10)
        assert result == 90

    def test_repairs_increase_fleet(self):
        from stochastic_warfare.combat.air_campaign import AirCampaignEngine
        eng = AirCampaignEngine(_event_bus(), _rng())
        eng.set_fleet_size(90)
        result = eng.update_attrition(losses=0, depot_repairs=5)
        assert result == 95

    def test_fleet_never_negative(self):
        from stochastic_warfare.combat.air_campaign import AirCampaignEngine
        eng = AirCampaignEngine(_event_bus(), _rng())
        eng.set_fleet_size(10)
        result = eng.update_attrition(losses=50)
        assert result == 0


class TestCampaignPhase:
    """Campaign phase management."""

    def test_default_phase(self):
        from stochastic_warfare.combat.air_campaign import AirCampaignEngine, CampaignPhase
        eng = AirCampaignEngine(_event_bus(), _rng())
        assert eng.current_phase == CampaignPhase.AIR_SUPERIORITY

    def test_set_phase(self):
        from stochastic_warfare.combat.air_campaign import AirCampaignEngine, CampaignPhase
        eng = AirCampaignEngine(_event_bus(), _rng())
        eng.set_phase(CampaignPhase.INTERDICTION)
        assert eng.current_phase == CampaignPhase.INTERDICTION

    def test_state_serialization(self):
        from stochastic_warfare.combat.air_campaign import AirCampaignEngine, CampaignPhase
        eng = AirCampaignEngine(_event_bus(), _rng())
        eng.set_fleet_size(80)
        eng.set_phase(CampaignPhase.SEAD)
        eng.register_pilot("p1")
        eng.update_pilot_fatigue("p1", 2)
        state = eng.get_state()
        eng2 = AirCampaignEngine(_event_bus(), _rng())
        eng2.set_state(state)
        assert eng2.current_phase == CampaignPhase.SEAD
        assert eng2._fleet_size == 80
        assert eng2.get_pilot("p1").fatigue > 0


# ===================================================================
# 12f-3: Strategic Targeting
# ===================================================================


class TestTPLGeneration:
    """generate_tpl target priority list."""

    def test_tpl_sorted_by_priority(self):
        from stochastic_warfare.combat.strategic_targeting import (
            StrategicTarget, StrategicTargetingEngine,
        )
        eng = StrategicTargetingEngine(_event_bus(), _rng())
        eng.register_target(StrategicTarget("t1", "bridge", Position(0, 0, 0)))
        eng.register_target(StrategicTarget("t2", "power_plant", Position(1000, 0, 0)))
        eng.register_target(StrategicTarget("t3", "depot", Position(2000, 0, 0)))
        tpl = eng.generate_tpl()
        # power_plant weight 2.5 > bridge 1.5 > depot 1.2
        assert tpl[0][0] == "t2"
        assert tpl[-1][0] == "t3"

    def test_destroyed_targets_excluded(self):
        from stochastic_warfare.combat.strategic_targeting import (
            StrategicTarget, StrategicTargetingEngine,
        )
        eng = StrategicTargetingEngine(_event_bus(), _rng())
        t1 = StrategicTarget("t1", "bridge", Position(0, 0, 0), health=0.0)
        t2 = StrategicTarget("t2", "factory", Position(1000, 0, 0))
        eng.register_target(t1)
        eng.register_target(t2)
        tpl = eng.generate_tpl()
        assert len(tpl) == 1
        assert tpl[0][0] == "t2"

    def test_commander_priorities_override(self):
        from stochastic_warfare.combat.strategic_targeting import (
            StrategicTarget, StrategicTargetingEngine,
        )
        eng = StrategicTargetingEngine(_event_bus(), _rng())
        eng.register_target(StrategicTarget("t1", "bridge", Position(0, 0, 0)))
        eng.register_target(StrategicTarget("t2", "power_plant", Position(1000, 0, 0)))
        # Override: bridge is now highest priority
        tpl = eng.generate_tpl(commander_priorities={"bridge": 10.0})
        assert tpl[0][0] == "t1"


class TestStrategicStrike:
    """apply_strike with cascading effects."""

    def test_strike_reduces_health(self):
        from stochastic_warfare.combat.strategic_targeting import (
            StrategicTarget, StrategicTargetingEngine,
        )
        eng = StrategicTargetingEngine(_event_bus(), _rng())
        eng.register_target(StrategicTarget("t1", "factory", Position(0, 0, 0)))
        eng.apply_strike("t1", damage=0.4)
        assert eng.get_target("t1").health == pytest.approx(0.6)

    def test_strike_cascades_to_infrastructure(self):
        from stochastic_warfare.combat.strategic_targeting import (
            StrategicTarget, StrategicTargetingEngine,
        )
        from stochastic_warfare.terrain.infrastructure import (
            Bridge, InfrastructureManager,
        )
        infra = InfrastructureManager(bridges=[Bridge(
            bridge_id="br1", position=(100, 200), road_id="r1",
        )])
        eng = StrategicTargetingEngine(_event_bus(), _rng())
        eng.register_target(StrategicTarget(
            "t1", "bridge", Position(100, 200, 0),
            infrastructure_id="br1",
        ))
        eng.apply_strike("t1", damage=0.5, infrastructure_manager=infra)
        assert infra.get_feature_condition("br1") < 1.0

    def test_effect_chain_triggered(self):
        from stochastic_warfare.combat.strategic_targeting import (
            StrategicTarget, StrategicTargetingEngine, TargetEffectChain,
        )
        eng = StrategicTargetingEngine(_event_bus(), _rng())
        eng.register_target(StrategicTarget("t1", "factory", Position(0, 0, 0)))
        eng.register_effect_chain(TargetEffectChain(
            target_type="factory", effect_type="production_reduced",
        ))
        effects = eng.apply_strike("t1", damage=0.6)
        assert len(effects) == 1
        assert effects[0]["effect_type"] == "production_reduced"


class TestBDA:
    """run_bda_cycle with overestimate bias."""

    def test_bda_returns_nonzero_for_damaged(self):
        from stochastic_warfare.combat.strategic_targeting import (
            StrategicTarget, StrategicTargetingEngine,
        )
        eng = StrategicTargetingEngine(_event_bus(), _rng())
        eng.register_target(StrategicTarget("t1", "bridge", Position(0, 0, 0), health=0.5))
        assessed = eng.run_bda_cycle("t1")
        assert assessed > 0.0

    def test_bda_overestimate_tendency(self):
        from stochastic_warfare.combat.strategic_targeting import (
            StrategicTarget, StrategicTargetingEngine,
        )
        # Run many BDA cycles and check average overestimates true damage
        assessments = []
        true_damage = 0.3
        for seed in range(100):
            eng = StrategicTargetingEngine(_event_bus(), _rng(seed))
            eng.register_target(StrategicTarget(
                "t1", "bridge", Position(0, 0, 0), health=1.0 - true_damage,
            ))
            assessments.append(eng.run_bda_cycle("t1"))
        mean_assessed = sum(assessments) / len(assessments)
        assert mean_assessed > true_damage  # overestimate bias

    def test_bda_zero_for_undamaged(self):
        from stochastic_warfare.combat.strategic_targeting import (
            StrategicTarget, StrategicTargetingEngine,
        )
        eng = StrategicTargetingEngine(_event_bus(), _rng())
        eng.register_target(StrategicTarget("t1", "bridge", Position(0, 0, 0), health=1.0))
        assert eng.run_bda_cycle("t1") == 0.0


class TestRegeneration:
    """update_regeneration repairs targets over time."""

    def test_damaged_target_repairs(self):
        from stochastic_warfare.combat.strategic_targeting import (
            StrategicTarget, StrategicTargetingEngine,
        )
        eng = StrategicTargetingEngine(_event_bus(), _rng())
        eng.register_target(StrategicTarget(
            "t1", "factory", Position(0, 0, 0), health=0.5, repair_rate=0.1,
        ))
        eng.update_regeneration(dt_hours=2.0)
        assert eng.get_target("t1").health == pytest.approx(0.7)

    def test_health_capped_at_one(self):
        from stochastic_warfare.combat.strategic_targeting import (
            StrategicTarget, StrategicTargetingEngine,
        )
        eng = StrategicTargetingEngine(_event_bus(), _rng())
        eng.register_target(StrategicTarget(
            "t1", "bridge", Position(0, 0, 0), health=0.9, repair_rate=0.5,
        ))
        eng.update_regeneration(dt_hours=10.0)
        assert eng.get_target("t1").health == 1.0

    def test_destroyed_target_does_not_repair(self):
        from stochastic_warfare.combat.strategic_targeting import (
            StrategicTarget, StrategicTargetingEngine,
        )
        eng = StrategicTargetingEngine(_event_bus(), _rng())
        eng.register_target(StrategicTarget(
            "t1", "bridge", Position(0, 0, 0), health=0.0, repair_rate=0.1,
        ))
        eng.update_regeneration(dt_hours=5.0)
        assert eng.get_target("t1").health == 0.0

    def test_strategic_targeting_state(self):
        from stochastic_warfare.combat.strategic_targeting import (
            StrategicTarget, StrategicTargetingEngine,
        )
        eng = StrategicTargetingEngine(_event_bus(), _rng())
        eng.register_target(StrategicTarget("t1", "factory", Position(100, 200, 0), health=0.6))
        state = eng.get_state()
        eng2 = StrategicTargetingEngine(_event_bus(), _rng())
        eng2.set_state(state)
        assert eng2.get_target("t1").health == 0.6


# ===================================================================
# 12f-4: Strategic Infrastructure Nodes
# ===================================================================


class TestInfrastructureNodes:
    """New infrastructure types and get_feature_condition."""

    def test_power_plant(self):
        from stochastic_warfare.terrain.infrastructure import InfrastructureManager, PowerPlant
        infra = InfrastructureManager(power_plants=[
            PowerPlant(plant_id="pp1", position=(0, 0)),
        ])
        assert infra.get_feature_condition("pp1") == 1.0
        infra.damage("pp1", 0.4)
        assert infra.get_feature_condition("pp1") == pytest.approx(0.6)

    def test_factory(self):
        from stochastic_warfare.terrain.infrastructure import Factory, InfrastructureManager
        infra = InfrastructureManager(factories=[
            Factory(factory_id="f1", position=(100, 200)),
        ])
        infra.damage("f1", 1.0)
        assert infra.get_feature_condition("f1") == 0.0
        infra.repair("f1", 0.3)
        assert infra.get_feature_condition("f1") == pytest.approx(0.3)

    def test_port(self):
        from stochastic_warfare.terrain.infrastructure import InfrastructureManager, Port
        infra = InfrastructureManager(ports=[
            Port(port_id="p1", position=(500, 500)),
        ])
        assert infra.get_feature_condition("p1") == 1.0

    def test_supply_depot(self):
        from stochastic_warfare.terrain.infrastructure import InfrastructureManager, SupplyDepot
        infra = InfrastructureManager(supply_depots=[
            SupplyDepot(depot_id="sd1", position=(300, 400)),
        ])
        infra.damage("sd1", 0.5)
        assert infra.get_feature_condition("sd1") == pytest.approx(0.5)

    def test_get_feature_condition_bridge(self):
        from stochastic_warfare.terrain.infrastructure import Bridge, InfrastructureManager
        infra = InfrastructureManager(bridges=[
            Bridge(bridge_id="br1", position=(0, 0), road_id="r1"),
        ])
        infra.damage("br1", 0.2)
        assert infra.get_feature_condition("br1") == pytest.approx(0.8)

    def test_get_feature_condition_unknown_raises(self):
        from stochastic_warfare.terrain.infrastructure import InfrastructureManager
        infra = InfrastructureManager()
        with pytest.raises(KeyError):
            infra.get_feature_condition("nonexistent")

    def test_health_state_enum(self):
        from stochastic_warfare.terrain.infrastructure import HealthState
        assert HealthState.OPERATIONAL == 0
        assert HealthState.DESTROYED == 2

    def test_state_includes_new_types(self):
        from stochastic_warfare.terrain.infrastructure import (
            Factory, InfrastructureManager, PowerPlant,
        )
        infra = InfrastructureManager(
            power_plants=[PowerPlant(plant_id="pp1", position=(0, 0))],
            factories=[Factory(factory_id="f1", position=(100, 100))],
        )
        infra.damage("pp1", 0.3)
        state = infra.get_state()
        assert "pp1" in state["conditions"]
        assert state["conditions"]["pp1"] == pytest.approx(0.7)
