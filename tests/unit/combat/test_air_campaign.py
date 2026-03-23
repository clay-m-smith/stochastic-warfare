"""Unit tests for AirCampaignEngine — sortie capacity, pilot fatigue, weather, attrition."""

from __future__ import annotations

import pytest

from stochastic_warfare.combat.air_campaign import (
    AirCampaignConfig,
    AirCampaignEngine,
    CampaignPhase,
    PilotState,
)
from stochastic_warfare.core.events import EventBus

from .conftest import _rng


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_campaign_engine(seed: int = 42, **cfg_kwargs) -> AirCampaignEngine:
    bus = EventBus()
    config = AirCampaignConfig(**cfg_kwargs) if cfg_kwargs else None
    return AirCampaignEngine(bus, _rng(seed), config)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFleetAndPhase:
    """Fleet size and campaign phase management."""

    def test_set_fleet_size(self):
        eng = _make_campaign_engine(seed=100)
        eng.set_fleet_size(200)
        state = eng.get_state()
        assert state["fleet_size"] == 200

    def test_set_and_get_phase(self):
        eng = _make_campaign_engine(seed=101)
        eng.set_phase(CampaignPhase.INTERDICTION)
        assert eng.current_phase == CampaignPhase.INTERDICTION

    def test_initial_phase_is_air_superiority(self):
        eng = _make_campaign_engine(seed=102)
        assert eng.current_phase == CampaignPhase.AIR_SUPERIORITY


class TestPilotFatigue:
    """Pilot fatigue accumulation and performance degradation."""

    def test_register_pilot(self):
        eng = _make_campaign_engine(seed=200)
        eng.register_pilot("ace_1")
        pilot = eng.get_pilot("ace_1")
        assert pilot.fatigue == pytest.approx(0.0)
        assert pilot.performance_modifier == pytest.approx(1.0)

    def test_fatigue_accumulates(self):
        eng = _make_campaign_engine(seed=201, fatigue_per_mission=0.15)
        eng.register_pilot("p1")

        eng.update_pilot_fatigue("p1", missions_today=2)
        pilot = eng.get_pilot("p1")
        assert pilot.fatigue == pytest.approx(0.3)
        assert pilot.cumulative_missions == 2

    def test_fatigue_performance_degradation(self):
        """Performance should degrade when fatigue exceeds threshold."""
        eng = _make_campaign_engine(
            seed=202,
            fatigue_per_mission=0.2,
            fatigue_performance_threshold=0.5,
        )
        eng.register_pilot("p1")

        # 4 missions * 0.2 = 0.8 fatigue (> 0.5 threshold)
        perf = eng.update_pilot_fatigue("p1", missions_today=4)
        assert perf < 1.0
        pilot = eng.get_pilot("p1")
        assert pilot.performance_modifier < 1.0

    def test_below_threshold_full_performance(self):
        eng = _make_campaign_engine(
            seed=203,
            fatigue_per_mission=0.1,
            fatigue_performance_threshold=0.5,
        )
        eng.register_pilot("p1")

        perf = eng.update_pilot_fatigue("p1", missions_today=2)
        assert perf == pytest.approx(1.0)


class TestFatigueRecovery:
    """Daily fatigue recovery should restore pilot performance."""

    def test_recovery_reduces_fatigue(self):
        eng = _make_campaign_engine(
            seed=300,
            fatigue_per_mission=0.15,
            fatigue_recovery_per_day=0.4,
        )
        eng.register_pilot("p1")

        eng.update_pilot_fatigue("p1", missions_today=3)
        fatigue_before = eng.get_pilot("p1").fatigue
        assert fatigue_before == pytest.approx(0.45)

        eng.recover_fatigue()
        fatigue_after = eng.get_pilot("p1").fatigue
        assert fatigue_after == pytest.approx(0.05)
        assert eng.get_pilot("p1").missions_today == 0

    def test_recovery_floors_at_zero(self):
        eng = _make_campaign_engine(
            seed=301,
            fatigue_per_mission=0.1,
            fatigue_recovery_per_day=0.5,
        )
        eng.register_pilot("p1")
        eng.update_pilot_fatigue("p1", missions_today=1)
        eng.recover_fatigue()
        assert eng.get_pilot("p1").fatigue == pytest.approx(0.0)


class TestSortieCapacity:
    """Daily sortie capacity depends on mission-capable rate and maintenance."""

    def test_sortie_capacity_basic(self):
        eng = _make_campaign_engine(
            seed=400,
            max_sorties_per_day=100,
            maintenance_unavailable_fraction=0.15,
        )
        # 50 aircraft * 0.85 MCR * 0.85 (1 - 0.15 maint) * 2 sorties = ~72
        capacity = eng.compute_daily_sortie_capacity(50, mission_capable_rate=0.85)
        assert capacity > 0
        assert capacity <= 100

    def test_capacity_capped_by_max(self):
        eng = _make_campaign_engine(seed=401, max_sorties_per_day=50)
        # Many aircraft, but capped at 50
        capacity = eng.compute_daily_sortie_capacity(500, mission_capable_rate=0.95)
        assert capacity <= 50


class TestWeatherDay:
    """Weather quality should gate sortie availability."""

    def test_bad_weather_cancels_all(self):
        eng = _make_campaign_engine(seed=500, weather_cancellation_threshold=0.3)
        sortie_fraction = eng.check_weather_day(0.1)
        assert sortie_fraction == pytest.approx(0.0)

    def test_perfect_weather_full_sorties(self):
        eng = _make_campaign_engine(seed=501, weather_cancellation_threshold=0.3)
        sortie_fraction = eng.check_weather_day(1.0)
        assert sortie_fraction == pytest.approx(1.0)

    def test_marginal_weather_partial(self):
        eng = _make_campaign_engine(seed=502, weather_cancellation_threshold=0.3)
        sortie_fraction = eng.check_weather_day(0.65)
        assert 0.0 < sortie_fraction < 1.0


class TestAttrition:
    """Fleet attrition and regeneration tracking."""

    def test_losses_reduce_fleet(self):
        eng = _make_campaign_engine(seed=600)
        eng.set_fleet_size(100)
        remaining = eng.update_attrition(losses=10)
        assert remaining == 90

    def test_depot_repairs_and_production(self):
        eng = _make_campaign_engine(seed=601)
        eng.set_fleet_size(80)
        remaining = eng.update_attrition(losses=5, depot_repairs=3, production=2)
        assert remaining == 80  # 80 - 5 + 3 + 2

    def test_fleet_floors_at_zero(self):
        eng = _make_campaign_engine(seed=602)
        eng.set_fleet_size(5)
        remaining = eng.update_attrition(losses=20)
        assert remaining == 0


class TestStateRoundtrip:
    """get_state / set_state should preserve fleet, phase, and pilot data."""

    def test_state_roundtrip(self):
        eng = _make_campaign_engine(seed=700)
        eng.set_fleet_size(150)
        eng.set_phase(CampaignPhase.CAS)
        eng.register_pilot("p1")
        eng.update_pilot_fatigue("p1", missions_today=2)
        eng.update_attrition(losses=10)

        state = eng.get_state()

        eng2 = _make_campaign_engine(seed=999)
        eng2.set_state(state)

        assert eng2.current_phase == CampaignPhase.CAS
        assert eng2.get_state()["fleet_size"] == 140
        assert eng2.get_pilot("p1").cumulative_missions == 2
        assert eng2.get_state()["losses"] == 10
