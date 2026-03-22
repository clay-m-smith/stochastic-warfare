"""Phase 69a — ATO sortie consumption tests."""

from __future__ import annotations

import pytest

from stochastic_warfare.c2.orders.air_orders import (
    AircraftAvailability,
    ATOPlanningEngine,
)
from stochastic_warfare.core.events import EventBus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def ato(bus: EventBus) -> ATOPlanningEngine:
    return ATOPlanningEngine(bus)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRecordSortie:
    """Phase 69a: record_sortie() increments sorties_today."""

    def test_record_sortie_increments(self, ato: ATOPlanningEngine):
        ac = AircraftAvailability(unit_id="f16_1")
        ato.register_aircraft(ac)
        assert ac.sorties_today == 0

        result = ato.record_sortie("f16_1", 1000.0)
        assert result is True
        assert ac.sorties_today == 1
        assert ac.last_sortie_end_time_s == 1000.0

    def test_sortie_limit_blocks_availability(self, ato: ATOPlanningEngine):
        """After max_sorties_per_day, get_available_sorties returns 0."""
        ac = AircraftAvailability(unit_id="f16_1", max_sorties_per_day=2)
        ato.register_aircraft(ac)

        ato.record_sortie("f16_1", 100.0)
        assert ato.get_available_sorties(100.0) == 0  # turnaround blocks
        # After turnaround
        assert ato.get_available_sorties(100.0 + 7201.0) == 1  # available again

        ato.record_sortie("f16_1", 8000.0)
        # Now at max — blocked even after turnaround
        assert ato.get_available_sorties(8000.0 + 7201.0) == 0

    def test_turnaround_blocks_next_sortie(self, ato: ATOPlanningEngine):
        """Sortie blocked until turnaround_time_s elapses."""
        ac = AircraftAvailability(unit_id="f16_1", turnaround_time_s=3600.0)
        ato.register_aircraft(ac)
        ato.record_sortie("f16_1", 500.0)

        assert ato.get_available_sorties(500.0) == 0  # too soon
        assert ato.get_available_sorties(4099.0) == 0  # still within turnaround
        assert ato.get_available_sorties(4100.0) == 1  # turnaround elapsed (3600 = 3600)

    def test_unregistered_unit_returns_false(self, ato: ATOPlanningEngine):
        assert ato.record_sortie("nonexistent", 0.0) is False


class TestResetDailySorties:
    """Phase 69a: reset_daily_sorties() resets all aircraft."""

    def test_reset_clears_sortie_count(self, ato: ATOPlanningEngine):
        ac1 = AircraftAvailability(unit_id="f16_1")
        ac2 = AircraftAvailability(unit_id="f16_2")
        ato.register_aircraft(ac1)
        ato.register_aircraft(ac2)
        ato.record_sortie("f16_1", 100.0)
        ato.record_sortie("f16_2", 200.0)

        count = ato.reset_daily_sorties(90000.0)
        assert count == 2
        assert ac1.sorties_today == 0
        assert ac2.sorties_today == 0

    def test_reset_no_op_when_no_sorties(self, ato: ATOPlanningEngine):
        ac = AircraftAvailability(unit_id="f16_1")
        ato.register_aircraft(ac)
        count = ato.reset_daily_sorties(90000.0)
        assert count == 0


class TestATOCheckpoint:
    """Phase 69a: get_state()/set_state() round-trip."""

    def test_round_trip(self, bus: EventBus):
        ato1 = ATOPlanningEngine(bus)
        ac = AircraftAvailability(unit_id="f16_1", max_sorties_per_day=3)
        ato1.register_aircraft(ac)
        ato1.record_sortie("f16_1", 500.0)

        state = ato1.get_state()

        ato2 = ATOPlanningEngine(bus)
        ato2.set_state(state)
        assert ato2.get_available_sorties(500.0) == 0  # turnaround blocks
        # After turnaround, 1 sortie used out of 3
        avail = ato2.get_available_sorties(500.0 + 7201.0)
        assert avail == 1  # 1 sortie used, max=3, 2 remaining but only 1 aircraft
