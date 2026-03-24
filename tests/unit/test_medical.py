"""Tests for logistics/medical.py -- triage, treatment, overwhelm, RTD."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.logistics.events import (
    CasualtyTreatedEvent,
    ReturnToDutyEvent,
)
from stochastic_warfare.logistics.medical import (
    MedicalConfig,
    MedicalEngine,
    MedicalFacility,
    MedicalFacilityLoader,
    MedicalFacilityType,
    TriagePriority,
)

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
_POS = Position(1000.0, 2000.0)


def _make_engine(
    seed: int = 42, config: MedicalConfig | None = None,
) -> tuple[MedicalEngine, EventBus]:
    bus = EventBus()
    rng = RNGManager(seed).get_stream(ModuleId.LOGISTICS)
    engine = MedicalEngine(event_bus=bus, rng=rng, config=config)
    return engine, bus


def _make_facility(
    facility_id: str = "aid_1",
    capacity: int = 10,
) -> MedicalFacility:
    return MedicalFacility(
        facility_id=facility_id,
        facility_type=MedicalFacilityType.AID_STATION,
        position=_POS,
        capacity=capacity,
    )


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestEnums:
    def test_facility_types(self) -> None:
        assert MedicalFacilityType.POINT_OF_INJURY == 0
        assert MedicalFacilityType.REAR_HOSPITAL == 3

    def test_triage_priority(self) -> None:
        assert TriagePriority.IMMEDIATE == 0
        assert TriagePriority.EXPECTANT == 3

    def test_immediate_sorts_first(self) -> None:
        priorities = [
            TriagePriority.MINIMAL,
            TriagePriority.IMMEDIATE,
            TriagePriority.DELAYED,
        ]
        assert sorted(priorities) == [
            TriagePriority.IMMEDIATE,
            TriagePriority.DELAYED,
            TriagePriority.MINIMAL,
        ]


# ---------------------------------------------------------------------------
# Facility management
# ---------------------------------------------------------------------------


class TestFacilityManagement:
    def test_register_facility(self) -> None:
        engine, _ = _make_engine()
        fac = _make_facility()
        engine.register_facility(fac)
        assert engine.get_facility("aid_1") is fac

    def test_get_facility_missing_raises(self) -> None:
        engine, _ = _make_engine()
        with pytest.raises(KeyError):
            engine.get_facility("nonexistent")


# ---------------------------------------------------------------------------
# Casualty intake
# ---------------------------------------------------------------------------


class TestCasualtyIntake:
    def test_receive_casualty(self) -> None:
        engine, _ = _make_engine()
        engine.register_facility(_make_facility())
        rec = engine.receive_casualty("u1", "m1", severity=2, facility_id="aid_1")
        assert rec.triage_priority == TriagePriority.DELAYED
        assert rec.status == "AWAITING_TRIAGE"

    def test_minor_wound_minimal_priority(self) -> None:
        engine, _ = _make_engine()
        rec = engine.receive_casualty("u1", "m1", severity=1)
        assert rec.triage_priority == TriagePriority.MINIMAL

    def test_critical_immediate_priority(self) -> None:
        engine, _ = _make_engine()
        rec = engine.receive_casualty("u1", "m1", severity=3)
        assert rec.triage_priority == TriagePriority.IMMEDIATE

    def test_pending_casualties(self) -> None:
        engine, _ = _make_engine()
        engine.receive_casualty("u1", "m1", severity=1)
        engine.receive_casualty("u1", "m2", severity=2)
        assert engine.pending_casualties() == 2

    def test_facility_patient_count_incremented(self) -> None:
        engine, _ = _make_engine()
        fac = _make_facility()
        engine.register_facility(fac)
        engine.receive_casualty("u1", "m1", severity=2, facility_id="aid_1")
        assert fac.current_patients == 1


# ---------------------------------------------------------------------------
# Treatment cycle
# ---------------------------------------------------------------------------


class TestTreatment:
    def test_minor_wound_treated(self) -> None:
        cfg = MedicalConfig(treatment_hours_minor=1.0)
        engine, _ = _make_engine(config=cfg)
        engine.register_facility(_make_facility())
        engine.receive_casualty("u1", "m1", severity=1, facility_id="aid_1")
        engine.update(0.5)  # start treatment
        completed = engine.update(1.0)  # should finish
        assert len(completed) == 1
        assert completed[0].outcome is not None

    def test_serious_wound_takes_longer(self) -> None:
        cfg = MedicalConfig(treatment_hours_minor=1.0, treatment_hours_serious=8.0)
        engine, _ = _make_engine(config=cfg)
        engine.register_facility(_make_facility())
        engine.receive_casualty("u1", "m1", severity=2, facility_id="aid_1")
        engine.update(0.5)  # start treatment
        completed = engine.update(2.0)  # not enough time
        assert len(completed) == 0

    def test_treatment_publishes_event(self) -> None:
        cfg = MedicalConfig(treatment_hours_minor=0.5)
        engine, bus = _make_engine(config=cfg)
        events: list[Event] = []
        bus.subscribe(CasualtyTreatedEvent, events.append)
        engine.register_facility(_make_facility())
        engine.receive_casualty("u1", "m1", severity=1, facility_id="aid_1")
        engine.update(0.1, timestamp=_TS)  # start treatment
        engine.update(1.0, timestamp=_TS)  # complete
        assert len(events) == 1
        assert events[0].outcome in ("RTD", "PERMANENT_LOSS", "DIED_OF_WOUNDS")

    def test_rtd_published_for_returning(self) -> None:
        """Run many trials to verify RTD events are published."""
        rtd_count = 0
        for seed in range(50):
            cfg = MedicalConfig(
                treatment_hours_minor=0.1,
                rtd_probability_minor=0.9,  # very high
            )
            engine, bus = _make_engine(seed=seed, config=cfg)
            events: list[Event] = []
            bus.subscribe(ReturnToDutyEvent, events.append)
            engine.register_facility(_make_facility())
            engine.receive_casualty("u1", f"m{seed}", severity=1, facility_id="aid_1")
            engine.update(0.05, timestamp=_TS)
            engine.update(0.2, timestamp=_TS)
            rtd_count += len(events)
        assert rtd_count > 30  # most should RTD with 90% probability

    def test_facility_freed_after_treatment(self) -> None:
        cfg = MedicalConfig(treatment_hours_minor=0.5)
        engine, _ = _make_engine(config=cfg)
        fac = _make_facility()
        engine.register_facility(fac)
        engine.receive_casualty("u1", "m1", severity=1, facility_id="aid_1")
        engine.update(0.1)
        engine.update(1.0)
        assert fac.current_patients == 0

    def test_no_treatment_without_facility(self) -> None:
        cfg = MedicalConfig(treatment_hours_minor=0.5)
        engine, _ = _make_engine(config=cfg)
        engine.receive_casualty("u1", "m1", severity=1)  # no facility
        engine.update(0.1)
        engine.update(1.0)
        rec = engine.get_casualty("m1")
        assert rec.outcome is None  # never started treatment


# ---------------------------------------------------------------------------
# Overwhelm dynamics
# ---------------------------------------------------------------------------


class TestOverwhelm:
    def test_overwhelmed_slows_treatment(self) -> None:
        cfg = MedicalConfig(
            treatment_hours_minor=1.0,
            overwhelm_threshold=0.8,
            overwhelm_time_multiplier=2.0,
        )
        engine, _ = _make_engine(config=cfg)
        fac = _make_facility(capacity=2)  # tiny facility
        engine.register_facility(fac)
        # Fill to 100% utilization (2/2)
        engine.receive_casualty("u1", "m1", severity=1, facility_id="aid_1")
        engine.receive_casualty("u1", "m2", severity=1, facility_id="aid_1")
        engine.update(0.1)  # start treatments
        # With overwhelm, treatment takes 2h instead of 1h
        completed = engine.update(1.5)  # not enough for overwhelmed
        assert len(completed) == 0

    def test_overwhelm_reduces_rtd(self) -> None:
        """Statistical test: overwhelmed facilities return fewer to duty."""
        normal_rtd = 0
        overwhelm_rtd = 0

        for seed in range(100):
            cfg = MedicalConfig(
                treatment_hours_minor=0.1,
                rtd_probability_minor=0.9,
                overwhelm_threshold=0.5,
                overwhelm_rtd_penalty=0.2,
            )
            engine, bus = _make_engine(seed=seed, config=cfg)
            events: list[Event] = []
            bus.subscribe(ReturnToDutyEvent, events.append)
            engine.register_facility(_make_facility(capacity=100))
            engine.receive_casualty("u1", f"m{seed}", severity=1, facility_id="aid_1")
            engine.update(0.05, timestamp=_TS)
            engine.update(0.2, timestamp=_TS)
            normal_rtd += len(events)

        for seed in range(100):
            cfg = MedicalConfig(
                treatment_hours_minor=0.1,
                rtd_probability_minor=0.9,
                overwhelm_threshold=0.5,
                overwhelm_rtd_penalty=0.2,
            )
            engine, bus = _make_engine(seed=seed, config=cfg)
            events: list[Event] = []
            bus.subscribe(ReturnToDutyEvent, events.append)
            fac = _make_facility(capacity=1)  # overwhelmed at 1 patient
            engine.register_facility(fac)
            engine.receive_casualty("u1", f"m{seed}", severity=1, facility_id="aid_1")
            engine.update(0.05, timestamp=_TS)
            engine.update(0.2, timestamp=_TS)
            overwhelm_rtd += len(events)

        assert overwhelm_rtd < normal_rtd


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------


class TestMedicalFacilityLoader:
    def test_load_all(self) -> None:
        loader = MedicalFacilityLoader()
        loader.load_all()
        defn = loader.get_definition("AID_STATION")
        assert defn.default_capacity == 10

    def test_field_hospital(self) -> None:
        loader = MedicalFacilityLoader()
        loader.load_all()
        defn = loader.get_definition("FIELD_HOSPITAL")
        assert defn.default_capacity == 50


# ---------------------------------------------------------------------------
# Deterministic replay
# ---------------------------------------------------------------------------


class TestDeterministicReplay:
    def test_same_seed_same_outcomes(self) -> None:
        def run(seed: int) -> list[str]:
            cfg = MedicalConfig(treatment_hours_minor=0.1)
            engine, _ = _make_engine(seed=seed, config=cfg)
            engine.register_facility(_make_facility())
            for i in range(5):
                engine.receive_casualty("u1", f"m{i}", severity=1, facility_id="aid_1")
            engine.update(0.05)
            completed = engine.update(0.5)
            return [c.outcome for c in completed if c.outcome]
        assert run(42) == run(42)


# ---------------------------------------------------------------------------
# State protocol
# ---------------------------------------------------------------------------


class TestStateProtocol:
    def test_state_round_trip(self) -> None:
        engine, _ = _make_engine()
        engine.register_facility(_make_facility())
        engine.receive_casualty("u1", "m1", severity=2, facility_id="aid_1")
        engine.update(1.0)

        state = engine.get_state()
        engine2, _ = _make_engine()
        engine2.set_state(state)
        assert engine2.get_state() == state
