"""Phase 64c: ATO management wiring tests."""

from __future__ import annotations

from datetime import datetime, timezone


from stochastic_warfare.c2.orders.air_orders import (
    ATOPlanningEngine,
    AircraftAvailability,
)
from stochastic_warfare.core.events import EventBus


class TestATORegistration:
    """ATO aircraft registration tests."""

    def test_air_units_registered(self):
        bus = EventBus()
        engine = ATOPlanningEngine(bus)
        engine.register_aircraft(AircraftAvailability(unit_id="f16_1"))
        engine.register_aircraft(AircraftAvailability(unit_id="f16_2"))
        assert engine.get_available_sorties() == 2

    def test_registration_idempotent(self):
        """Registering same aircraft twice doesn't duplicate."""
        bus = EventBus()
        engine = ATOPlanningEngine(bus)
        engine.register_aircraft(AircraftAvailability(unit_id="f16_1"))
        engine.register_aircraft(AircraftAvailability(unit_id="f16_1"))
        assert engine.get_available_sorties() == 1

    def test_non_capable_not_available(self):
        bus = EventBus()
        engine = ATOPlanningEngine(bus)
        engine.register_aircraft(AircraftAvailability(
            unit_id="f16_1", mission_capable=False,
        ))
        assert engine.get_available_sorties() == 0


class TestATOSortieLimit:
    """ATO sortie and turnaround tests."""

    def test_max_sorties_enforced(self):
        bus = EventBus()
        engine = ATOPlanningEngine(bus)
        engine.register_aircraft(AircraftAvailability(
            unit_id="f16_1", max_sorties_per_day=2, sorties_today=2,
        ))
        assert engine.get_available_sorties() == 0

    def test_turnaround_time_enforced(self):
        bus = EventBus()
        engine = ATOPlanningEngine(bus)
        engine.register_aircraft(AircraftAvailability(
            unit_id="f16_1",
            turnaround_time_s=7200.0,
            last_sortie_end_time_s=100.0,
        ))
        # At t=1000, still within turnaround
        assert engine.get_available_sorties(current_time_s=1000.0) == 0
        # At t=8000, past turnaround
        assert engine.get_available_sorties(current_time_s=8000.0) == 1

    def test_available_sorties_fresh_aircraft(self):
        bus = EventBus()
        engine = ATOPlanningEngine(bus)
        engine.register_aircraft(AircraftAvailability(unit_id="f16_1"))
        assert engine.get_available_sorties() == 1


class TestATOGeneration:
    """ATO generation and event tests."""

    def test_ato_generated_event_published(self):
        bus = EventBus()
        events = []
        from stochastic_warfare.c2.events import ATOGeneratedEvent
        bus.subscribe(ATOGeneratedEvent, lambda e: events.append(e))
        engine = ATOPlanningEngine(bus)
        engine.register_aircraft(AircraftAvailability(unit_id="f16_1"))
        engine.submit_request(mission_type="CAS")
        entries = engine.generate_ato(
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert len(events) == 1
        assert events[0].num_missions >= 1

    def test_generate_ato_empty_when_no_aircraft(self):
        bus = EventBus()
        engine = ATOPlanningEngine(bus)
        entries = engine.generate_ato()
        assert entries == []

    def test_air_engagement_gate_structural(self):
        """battle.py checks ato_engine in air engagement routing."""
        from pathlib import Path
        src = Path(__file__).resolve().parents[2] / "stochastic_warfare" / "simulation" / "battle.py"
        text = src.read_text(encoding="utf-8")
        assert "ato_engine" in text
        assert "get_available_sorties" in text
