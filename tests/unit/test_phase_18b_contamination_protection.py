"""Phase 18b tests — Contamination manager and MOPP protection engine."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.cbrn.agents import AgentCategory, AgentDefinition
from stochastic_warfare.cbrn.contamination import ContaminationConfig, ContaminationManager
from stochastic_warfare.cbrn.protection import ProtectionConfig, ProtectionEngine
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position

TS = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _make_manager(
    rows: int = 10,
    cols: int = 10,
    cell_size: float = 100.0,
    config: ContaminationConfig | None = None,
) -> ContaminationManager:
    return ContaminationManager(
        grid_shape=(rows, cols),
        cell_size_m=cell_size,
        origin_easting=0.0,
        origin_northing=0.0,
        event_bus=EventBus(),
        rng=np.random.default_rng(42),
        config=config,
    )


def _make_agent(
    agent_id: str = "sarin",
    persistence_hours: float = 2.0,
    evaporation_rate: float = 0.01,
    rain_washout: float = 0.1,
    soil_absorption: dict | None = None,
) -> AgentDefinition:
    return AgentDefinition(
        agent_id=agent_id,
        category=int(AgentCategory.NERVE),
        persistence_hours=persistence_hours,
        evaporation_rate_per_c=evaporation_rate,
        rain_washout_rate=rain_washout,
        soil_absorption=soil_absorption or {},
    )


# ---------------------------------------------------------------------------
# Contamination — add & query
# ---------------------------------------------------------------------------


class TestContaminationAdd:
    def test_add_and_query(self):
        mgr = _make_manager()
        mgr.add_contamination("sarin", 5, 5, 10.0)
        assert mgr.concentration_at("sarin", 5, 5) == pytest.approx(10.0)

    def test_grid_mapping(self):
        mgr = _make_manager(cell_size=100.0)
        pos = Position(550.0, 350.0, 0.0)
        row, col = mgr.enu_to_grid(pos)
        assert row == 3
        assert col == 5

    def test_lazy_allocation(self):
        mgr = _make_manager()
        # No grid allocated yet
        assert mgr.concentration_at("vx", 0, 0) == 0.0
        # Allocate on first add
        mgr.add_contamination("vx", 0, 0, 5.0)
        assert mgr.concentration_at("vx", 0, 0) == pytest.approx(5.0)

    def test_multi_agent(self):
        mgr = _make_manager()
        mgr.add_contamination("sarin", 3, 3, 10.0)
        mgr.add_contamination("vx", 3, 3, 20.0)
        assert mgr.concentration_at("sarin", 3, 3) == pytest.approx(10.0)
        assert mgr.concentration_at("vx", 3, 3) == pytest.approx(20.0)

    def test_additive(self):
        mgr = _make_manager()
        mgr.add_contamination("sarin", 2, 2, 5.0)
        mgr.add_contamination("sarin", 2, 2, 3.0)
        assert mgr.concentration_at("sarin", 2, 2) == pytest.approx(8.0)


# ---------------------------------------------------------------------------
# Ground deposit
# ---------------------------------------------------------------------------


class TestGroundDeposit:
    def test_add_ground(self):
        mgr = _make_manager()
        mgr.add_ground_deposit("vx", 1, 1, 50.0)
        assert mgr.ground_deposit_at("vx", 1, 1) == pytest.approx(50.0)

    def test_persist_separate(self):
        mgr = _make_manager()
        mgr.add_contamination("vx", 1, 1, 10.0)
        mgr.add_ground_deposit("vx", 1, 1, 50.0)
        assert mgr.concentration_at("vx", 1, 1) == pytest.approx(10.0)
        assert mgr.ground_deposit_at("vx", 1, 1) == pytest.approx(50.0)

    def test_query_empty(self):
        mgr = _make_manager()
        assert mgr.ground_deposit_at("none", 0, 0) == 0.0


# ---------------------------------------------------------------------------
# Decay
# ---------------------------------------------------------------------------


class TestDecay:
    def test_exponential_half_life(self):
        mgr = _make_manager()
        agent = _make_agent(persistence_hours=1.0, evaporation_rate=0.0)
        mgr.add_contamination("sarin", 5, 5, 100.0)
        # Decay for 1 hour → should be ~50
        mgr.apply_decay("sarin", agent, dt_s=3600.0, temperature_c=15.0)
        assert mgr.concentration_at("sarin", 5, 5) == pytest.approx(50.0, rel=0.01)

    def test_two_half_lives(self):
        mgr = _make_manager()
        agent = _make_agent(persistence_hours=1.0, evaporation_rate=0.0)
        mgr.add_contamination("sarin", 5, 5, 100.0)
        mgr.apply_decay("sarin", agent, dt_s=7200.0, temperature_c=15.0)
        assert mgr.concentration_at("sarin", 5, 5) == pytest.approx(25.0, rel=0.01)


# ---------------------------------------------------------------------------
# Evaporation
# ---------------------------------------------------------------------------


class TestEvaporation:
    def test_temperature_dependent(self):
        mgr = _make_manager()
        agent = _make_agent(persistence_hours=1e6, evaporation_rate=0.02)
        mgr.add_contamination("sarin", 5, 5, 100.0)
        # 30°C, 15°C excess → factor = 1 - 0.02*15*1 = 0.7 after 1 hour
        mgr.apply_decay("sarin", agent, dt_s=3600.0, temperature_c=30.0)
        assert mgr.concentration_at("sarin", 5, 5) == pytest.approx(70.0, rel=0.05)

    def test_cold_slow(self):
        mgr = _make_manager()
        agent = _make_agent(persistence_hours=1e6, evaporation_rate=0.02)
        mgr.add_contamination("sarin", 5, 5, 100.0)
        # 10°C, below 15°C → no evaporation
        mgr.apply_decay("sarin", agent, dt_s=3600.0, temperature_c=10.0)
        assert mgr.concentration_at("sarin", 5, 5) == pytest.approx(100.0, rel=0.01)


# ---------------------------------------------------------------------------
# Rain washout
# ---------------------------------------------------------------------------


class TestRainWashout:
    def test_precipitation_removes(self):
        mgr = _make_manager()
        agent = _make_agent(persistence_hours=1e6, evaporation_rate=0.0, rain_washout=0.2)
        mgr.add_contamination("sarin", 5, 5, 100.0)
        # 5 mm/hr rain for 1 hour → factor = 1 - 0.2*5*1 = 0.0
        mgr.apply_decay("sarin", agent, dt_s=3600.0, temperature_c=15.0,
                         precipitation_rate_mm_hr=5.0)
        assert mgr.concentration_at("sarin", 5, 5) == 0.0

    def test_no_rain_no_change(self):
        mgr = _make_manager()
        agent = _make_agent(persistence_hours=1e6, evaporation_rate=0.0, rain_washout=0.2)
        mgr.add_contamination("sarin", 5, 5, 100.0)
        mgr.apply_decay("sarin", agent, dt_s=3600.0, temperature_c=15.0,
                         precipitation_rate_mm_hr=0.0)
        assert mgr.concentration_at("sarin", 5, 5) == pytest.approx(100.0, rel=0.01)


# ---------------------------------------------------------------------------
# Soil absorption
# ---------------------------------------------------------------------------


class TestSoilAbsorption:
    def test_sandy_absorbs(self):
        mgr = _make_manager()
        agent = _make_agent(persistence_hours=1e6, evaporation_rate=0.0,
                            soil_absorption={"sandy": 0.5})
        mgr.add_contamination("sarin", 5, 5, 100.0)
        mgr.apply_decay("sarin", agent, dt_s=3600.0, temperature_c=15.0, soil_type="sandy")
        # 50% per hour transferred to ground
        assert mgr.concentration_at("sarin", 5, 5) < 100.0
        assert mgr.ground_deposit_at("sarin", 5, 5) > 0.0

    def test_clay_absorbs_less(self):
        mgr = _make_manager()
        agent = _make_agent(persistence_hours=1e6, evaporation_rate=0.0,
                            soil_absorption={"clay": 0.1, "sandy": 0.5})
        mgr.add_contamination("sarin", 5, 5, 100.0)
        mgr.apply_decay("sarin", agent, dt_s=3600.0, temperature_c=15.0, soil_type="clay")
        remaining_clay = mgr.concentration_at("sarin", 5, 5)

        mgr2 = _make_manager()
        mgr2.add_contamination("sarin", 5, 5, 100.0)
        mgr2.apply_decay("sarin", agent, dt_s=3600.0, temperature_c=15.0, soil_type="sandy")
        remaining_sandy = mgr2.concentration_at("sarin", 5, 5)

        assert remaining_clay > remaining_sandy

    def test_unknown_soil_no_absorption(self):
        mgr = _make_manager()
        agent = _make_agent(persistence_hours=1e6, evaporation_rate=0.0,
                            soil_absorption={"sandy": 0.5})
        mgr.add_contamination("sarin", 5, 5, 100.0)
        mgr.apply_decay("sarin", agent, dt_s=3600.0, temperature_c=15.0, soil_type="rock")
        assert mgr.concentration_at("sarin", 5, 5) == pytest.approx(100.0, rel=0.01)


# ---------------------------------------------------------------------------
# is_contaminated
# ---------------------------------------------------------------------------


class TestIsContaminated:
    def test_above_threshold(self):
        mgr = _make_manager()
        mgr.add_contamination("sarin", 5, 5, 1.0)
        assert mgr.is_contaminated(Position(550.0, 550.0, 0.0))

    def test_below_threshold(self):
        mgr = _make_manager(config=ContaminationConfig(min_concentration_mg_m3=0.001))
        mgr.add_contamination("sarin", 5, 5, 0.0001)
        assert not mgr.is_contaminated(Position(550.0, 550.0, 0.0))


# ---------------------------------------------------------------------------
# contaminated_cells
# ---------------------------------------------------------------------------


class TestContaminatedCells:
    def test_enumerate(self):
        mgr = _make_manager()
        mgr.add_contamination("sarin", 2, 3, 10.0)
        mgr.add_contamination("sarin", 4, 5, 20.0)
        cells = mgr.contaminated_cells("sarin")
        assert (2, 3) in cells
        assert (4, 5) in cells
        assert len(cells) == 2

    def test_empty_when_clear(self):
        mgr = _make_manager()
        assert mgr.contaminated_cells("sarin") == []


# ---------------------------------------------------------------------------
# MOPP speed factor
# ---------------------------------------------------------------------------


class TestMOPPSpeed:
    def test_table_values(self):
        pe = ProtectionEngine()
        assert pe.get_mopp_speed_factor(0) == 1.0
        assert pe.get_mopp_speed_factor(4) == 0.70

    def test_mopp_0_no_penalty(self):
        pe = ProtectionEngine()
        assert pe.get_mopp_speed_factor(0) == 1.0


# ---------------------------------------------------------------------------
# MOPP detection factor
# ---------------------------------------------------------------------------


class TestMOPPDetection:
    def test_table_values(self):
        pe = ProtectionEngine()
        assert pe.get_mopp_detection_factor(1) == 1.0
        assert pe.get_mopp_detection_factor(4) == 0.70

    def test_ordering(self):
        pe = ProtectionEngine()
        assert pe.get_mopp_detection_factor(2) > pe.get_mopp_detection_factor(4)


# ---------------------------------------------------------------------------
# MOPP fatigue
# ---------------------------------------------------------------------------


class TestMOPPFatigue:
    def test_base_values(self):
        pe = ProtectionEngine()
        assert pe.get_mopp_fatigue_multiplier(0) == 1.0
        assert pe.get_mopp_fatigue_multiplier(4) == 1.6

    def test_heat_stress_above_threshold(self):
        pe = ProtectionEngine(ProtectionConfig(heat_stress_threshold_c=30.0,
                                                heat_stress_fatigue_bonus=0.3))
        # 40°C → 10°C excess → bonus = 0.3 * 1.0 = 0.3
        fatigue = pe.get_mopp_fatigue_multiplier(4, temperature_c=40.0)
        assert fatigue > 1.6

    def test_heat_stress_below_threshold(self):
        pe = ProtectionEngine()
        fatigue = pe.get_mopp_fatigue_multiplier(4, temperature_c=25.0)
        assert fatigue == pytest.approx(1.6)


# ---------------------------------------------------------------------------
# Protection factor
# ---------------------------------------------------------------------------


class TestProtectionFactor:
    def test_full_protection_at_threshold(self):
        pe = ProtectionEngine()
        # Nerve requires MOPP 4 for full protection
        pf = pe.compute_protection_factor(4, int(AgentCategory.NERVE))
        assert pf == pytest.approx(1.0)

    def test_zero_at_mopp_0(self):
        pe = ProtectionEngine()
        pf = pe.compute_protection_factor(0, int(AgentCategory.NERVE))
        assert pf == 0.0


class TestProtectionDegradation:
    def test_wears_over_time(self):
        pe = ProtectionEngine(ProtectionConfig(protection_degradation_per_hour=0.05))
        fresh = pe.compute_protection_factor(4, int(AgentCategory.NERVE), equipment_age_hours=0.0)
        aged = pe.compute_protection_factor(4, int(AgentCategory.NERVE), equipment_age_hours=10.0)
        assert aged < fresh


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------


class TestState:
    def test_contamination_roundtrip(self):
        mgr = _make_manager()
        mgr.add_contamination("sarin", 5, 5, 42.0)
        state = mgr.get_state()

        mgr2 = _make_manager()
        mgr2.set_state(state)
        assert mgr2.concentration_at("sarin", 5, 5) == pytest.approx(42.0)
