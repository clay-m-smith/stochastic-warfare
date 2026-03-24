"""Medical system — triage, treatment, evacuation, return to duty.

M/M/c priority queue: IMMEDIATE > DELAYED > MINIMAL > EXPECTANT.
When utilization exceeds overwhelm threshold, treatment times increase
and RTD probability decreases.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.logistics.events import (
    CasualtyTreatedEvent,
    ReturnToDutyEvent,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class MedicalFacilityType(enum.IntEnum):
    """Echelons of medical care."""

    POINT_OF_INJURY = 0
    AID_STATION = 1
    FIELD_HOSPITAL = 2
    REAR_HOSPITAL = 3


class TriagePriority(enum.IntEnum):
    """Triage categories (lower value = higher priority)."""

    IMMEDIATE = 0  # T1
    DELAYED = 1  # T2
    MINIMAL = 2  # T3
    EXPECTANT = 3  # T4


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class MedicalFacility:
    """A medical treatment facility."""

    facility_id: str
    facility_type: MedicalFacilityType
    position: Position
    capacity: int
    current_patients: int = 0
    side: str = "blue"


@dataclass
class CasualtyRecord:
    """Track a single casualty through the medical system."""

    unit_id: str
    member_id: str
    severity: int  # InjuryState value
    facility_id: str | None = None
    triage_priority: TriagePriority = TriagePriority.DELAYED
    treatment_start: float | None = None
    estimated_completion: float | None = None
    outcome: str | None = None  # RTD, PERMANENT_LOSS, DIED_OF_WOUNDS
    status: str = "AWAITING_TRIAGE"  # AWAITING_TRIAGE, IN_TREATMENT, TREATED, EVACUATING


# Severity → TriagePriority mapping
_SEVERITY_TO_TRIAGE: dict[int, TriagePriority] = {
    1: TriagePriority.MINIMAL,  # MINOR_WOUND
    2: TriagePriority.DELAYED,  # SERIOUS_WOUND
    3: TriagePriority.IMMEDIATE,  # CRITICAL
}


# ---------------------------------------------------------------------------
# YAML-loaded facility definitions
# ---------------------------------------------------------------------------


class MedicalFacilityDefinition(BaseModel):
    """Medical facility specification loaded from YAML."""

    facility_type: str
    display_name: str
    default_capacity: int
    treatment_hours_minor: float = 2.0
    treatment_hours_serious: float = 8.0
    treatment_hours_critical: float = 24.0


class MedicalFacilityLoader:
    """Load ``MedicalFacilityDefinition`` from YAML files."""

    def __init__(self, data_dir=None) -> None:
        from pathlib import Path

        if data_dir is None:
            data_dir = (
                Path(__file__).resolve().parents[2]
                / "data"
                / "logistics"
                / "medical_facilities"
            )
        self._data_dir = data_dir
        self._definitions: dict[str, MedicalFacilityDefinition] = {}

    def load_definition(self, path) -> MedicalFacilityDefinition:
        import yaml

        with open(path) as f:
            data = yaml.safe_load(f)
        defn = MedicalFacilityDefinition.model_validate(data)
        self._definitions[defn.facility_type] = defn
        return defn

    def load_all(self) -> None:

        for path in sorted(self._data_dir.rglob("*.yaml")):
            self.load_definition(path)
        logger.info("Loaded %d medical facility definitions", len(self._definitions))

    def get_definition(self, facility_type: str) -> MedicalFacilityDefinition:
        return self._definitions[facility_type]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class MedicalConfig(BaseModel):
    """Tuning parameters for medical engine."""

    evacuation_speed_mps: float = 5.0
    triage_time_hours: float = 0.083  # ~5 minutes
    treatment_hours_minor: float = 2.0
    treatment_hours_serious: float = 8.0
    treatment_hours_critical: float = 24.0
    rtd_probability_minor: float = 0.9
    rtd_probability_serious: float = 0.4
    rtd_probability_critical: float = 0.1
    overwhelm_threshold: float = 0.8
    overwhelm_time_multiplier: float = 2.0
    overwhelm_rtd_penalty: float = 0.5  # multiply RTD probability by this

    # 12b-4: Erlang service time
    erlang_shape_k: int = 1
    """Erlang shape parameter k. k=1 = exponential (MVP default).
    k>1 = more predictable treatment times (sum of k exponentials)."""


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class MedicalEngine:
    """Process casualties through triage, treatment, and disposition.

    Parameters
    ----------
    event_bus : EventBus
        Publishes ``CasualtyTreatedEvent``, ``ReturnToDutyEvent``,
        ``CasualtyEvacuatedEvent``.
    rng : numpy.random.Generator
        Deterministic PRNG stream.
    config : MedicalConfig | None
        Tuning parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: MedicalConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or MedicalConfig()
        self._facilities: dict[str, MedicalFacility] = {}
        self._casualties: dict[str, CasualtyRecord] = {}  # keyed by member_id
        self._sim_time: float = 0.0

    def register_facility(self, facility: MedicalFacility) -> None:
        """Register a medical facility."""
        self._facilities[facility.facility_id] = facility

    def get_facility(self, facility_id: str) -> MedicalFacility:
        """Return a facility; raises ``KeyError`` if not found."""
        return self._facilities[facility_id]

    def receive_casualty(
        self,
        unit_id: str,
        member_id: str,
        severity: int,
        facility_id: str | None = None,
    ) -> CasualtyRecord:
        """Receive a new casualty into the medical system."""
        triage = _SEVERITY_TO_TRIAGE.get(severity, TriagePriority.EXPECTANT)
        record = CasualtyRecord(
            unit_id=unit_id,
            member_id=member_id,
            severity=severity,
            facility_id=facility_id,
            triage_priority=triage,
        )
        self._casualties[member_id] = record

        if facility_id and facility_id in self._facilities:
            self._facilities[facility_id].current_patients += 1

        logger.debug(
            "Casualty %s/%s received (severity=%d, priority=%s)",
            unit_id, member_id, severity, triage.name,
        )
        return record

    def update(
        self,
        dt_hours: float,
        timestamp: datetime | None = None,
    ) -> list[CasualtyRecord]:
        """Process treatments and advance the medical system.

        Returns list of casualties whose treatment completed this step.
        """
        self._sim_time += dt_hours
        cfg = self._config
        completed: list[CasualtyRecord] = []

        # Sort casualties by triage priority (IMMEDIATE first)
        sorted_casualties = sorted(
            self._casualties.values(),
            key=lambda c: (c.triage_priority, c.member_id),
        )

        for record in sorted_casualties:
            if record.outcome is not None:
                continue

            # Start treatment if awaiting
            if record.status == "AWAITING_TRIAGE" and record.facility_id:
                record.status = "IN_TREATMENT"
                record.treatment_start = self._sim_time
                treatment_time = self._get_treatment_time(record)
                # Check overwhelm
                facility = self._facilities.get(record.facility_id)
                if facility:
                    utilization = facility.current_patients / max(facility.capacity, 1)
                    if utilization > cfg.overwhelm_threshold:
                        treatment_time *= cfg.overwhelm_time_multiplier
                record.estimated_completion = self._sim_time + treatment_time

            # Check if treatment is complete
            if (record.status == "IN_TREATMENT"
                    and record.estimated_completion is not None
                    and self._sim_time >= record.estimated_completion):
                self._resolve_outcome(record, timestamp)
                completed.append(record)

        return completed

    def _get_treatment_time(self, record: CasualtyRecord) -> float:
        """Return treatment time based on severity.

        When ``erlang_shape_k > 1``, treatment time is drawn from a Gamma
        distribution with shape k and the same mean, producing less variable
        but still stochastic durations.
        """
        cfg = self._config
        if record.severity <= 1:
            mean = cfg.treatment_hours_minor
        elif record.severity == 2:
            mean = cfg.treatment_hours_serious
        else:
            mean = cfg.treatment_hours_critical

        k = cfg.erlang_shape_k
        if k > 1:
            # Gamma(k, mean/k) has mean = mean, variance = mean²/k
            return float(self._rng.gamma(k, mean / k))
        return mean

    def _resolve_outcome(
        self, record: CasualtyRecord, timestamp: datetime | None,
    ) -> None:
        """Determine treatment outcome (RTD, permanent loss, DOW)."""
        cfg = self._config
        if record.severity <= 1:
            rtd_prob = cfg.rtd_probability_minor
        elif record.severity == 2:
            rtd_prob = cfg.rtd_probability_serious
        else:
            rtd_prob = cfg.rtd_probability_critical

        # Check overwhelm penalty
        if record.facility_id:
            facility = self._facilities.get(record.facility_id)
            if facility:
                utilization = facility.current_patients / max(facility.capacity, 1)
                if utilization > cfg.overwhelm_threshold:
                    rtd_prob *= cfg.overwhelm_rtd_penalty

        if self._rng.random() < rtd_prob:
            record.outcome = "RTD"
            record.status = "TREATED"
            if timestamp is not None:
                self._event_bus.publish(ReturnToDutyEvent(
                    timestamp=timestamp,
                    source=ModuleId.LOGISTICS,
                    unit_id=record.unit_id,
                    member_id=record.member_id,
                ))
        elif record.severity >= 3 and self._rng.random() < 0.3:
            record.outcome = "DIED_OF_WOUNDS"
            record.status = "TREATED"
        else:
            record.outcome = "PERMANENT_LOSS"
            record.status = "TREATED"

        if timestamp is not None:
            self._event_bus.publish(CasualtyTreatedEvent(
                timestamp=timestamp,
                source=ModuleId.LOGISTICS,
                unit_id=record.unit_id,
                member_id=record.member_id,
                outcome=record.outcome,
            ))

        # Free facility capacity
        if record.facility_id and record.facility_id in self._facilities:
            self._facilities[record.facility_id].current_patients = max(
                0, self._facilities[record.facility_id].current_patients - 1,
            )

    def get_casualty(self, member_id: str) -> CasualtyRecord:
        """Return a casualty record; raises ``KeyError`` if not found."""
        return self._casualties[member_id]

    def pending_casualties(self) -> int:
        """Return count of casualties awaiting or in treatment."""
        return sum(
            1 for c in self._casualties.values()
            if c.outcome is None
        )

    # -- State protocol --

    def get_state(self) -> dict:
        """Serialize for checkpoint."""
        return {
            "sim_time": self._sim_time,
            "facilities": {
                fid: {
                    "facility_id": f.facility_id,
                    "facility_type": int(f.facility_type),
                    "position": list(f.position),
                    "capacity": f.capacity,
                    "current_patients": f.current_patients,
                    "side": f.side,
                }
                for fid, f in self._facilities.items()
            },
            "casualties": {
                mid: {
                    "unit_id": c.unit_id,
                    "member_id": c.member_id,
                    "severity": c.severity,
                    "facility_id": c.facility_id,
                    "triage_priority": int(c.triage_priority),
                    "treatment_start": c.treatment_start,
                    "estimated_completion": c.estimated_completion,
                    "outcome": c.outcome,
                    "status": c.status,
                }
                for mid, c in self._casualties.items()
            },
        }

    def set_state(self, state: dict) -> None:
        """Restore from checkpoint."""
        self._sim_time = state.get("sim_time", 0.0)
        self._facilities.clear()
        for fid, fd in state["facilities"].items():
            self._facilities[fid] = MedicalFacility(
                facility_id=fd["facility_id"],
                facility_type=MedicalFacilityType(fd["facility_type"]),
                position=Position(*fd["position"]),
                capacity=fd["capacity"],
                current_patients=fd["current_patients"],
                side=fd.get("side", "blue"),
            )
        self._casualties.clear()
        for mid, cd in state["casualties"].items():
            self._casualties[mid] = CasualtyRecord(
                unit_id=cd["unit_id"],
                member_id=cd["member_id"],
                severity=cd["severity"],
                facility_id=cd.get("facility_id"),
                triage_priority=TriagePriority(cd["triage_priority"]),
                treatment_start=cd.get("treatment_start"),
                estimated_completion=cd.get("estimated_completion"),
                outcome=cd.get("outcome"),
                status=cd.get("status", "AWAITING_TRIAGE"),
            )
