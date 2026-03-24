"""Equipment maintenance — Poisson breakdown, repair cycles, spare parts.

Breakdown probability: ``P(fail in dt) = 1 - exp(-dt / MTBF(condition))``.
Deferred maintenance decreases effective MTBF.  Environmental stress adds
a multiplier.  Repair consumes Class IX spare parts.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.logistics.events import (
    EquipmentBreakdownEvent,
    MaintenanceCompletedEvent,
    MaintenanceStartedEvent,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & types
# ---------------------------------------------------------------------------


class MaintenanceStatus(enum.IntEnum):
    """Equipment maintenance state."""

    OPERATIONAL = 0
    MAINTENANCE_DUE = 1
    UNDER_REPAIR = 2
    AWAITING_PARTS = 3
    DEADLINE = 4  # non-operational, awaiting higher-level repair


@dataclass
class MaintenanceRecord:
    """Per-equipment maintenance state."""

    unit_id: str
    equipment_id: str
    status: MaintenanceStatus = MaintenanceStatus.OPERATIONAL
    hours_since_maintenance: float = 0.0
    maintenance_due_hours: float = 500.0
    repair_start_time: float | None = None
    estimated_repair_hours: float = 0.0
    repair_elapsed: float = 0.0
    condition: float = 1.0  # 0-1


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class MaintenanceConfig(BaseModel):
    """Tuning parameters for maintenance engine.

    Sources:
    - MIL-HDBK-217F "Reliability Prediction of Electronic Equipment" (1991):
      MTBF 200-1000h for military ground vehicles; 500h is mid-range.
    - Temperature thresholds: MIL-STD-810G Method 501.5 / 502.5 — extreme
      heat >45°C and extreme cold <-20°C degrade reliability ~1.5×.
    - Deferred maintenance: FM 4-30.31 "Recovery and Battle Damage
      Assessment" — deferred maintenance doubles failure rate.
    """

    base_mtbf_hours: float = 500.0
    """Mid-range military vehicle MTBF (MIL-HDBK-217F: 200-1000h)."""
    deferred_maintenance_multiplier: float = 2.0
    """Failure rate multiplier when maintenance overdue (FM 4-30.31)."""
    repair_time_hours: float = 4.0
    spare_parts_per_repair: float = 1.0
    environmental_stress_multiplier: float = 1.5
    """Reliability degradation under extreme temperature (MIL-STD-810G)."""
    environmental_stress_threshold_c: float = 45.0
    """Heat stress threshold in °C (MIL-STD-810G Method 501.5)."""
    cold_stress_threshold_c: float = -20.0
    """Cold stress threshold in °C (MIL-STD-810G Method 502.5)."""
    maintenance_due_fraction: float = 0.9
    condition_restored_after_repair: float = 0.95

    use_weibull: bool = False
    """When True, use Weibull hazard function instead of exponential.
    k=1.0 is mathematically identical to exponential (current default).
    Typical military equipment: k=1.2-1.8 (MIL-HDBK-217F, Annex B)."""
    weibull_shape_k: float = 1.0
    """Weibull shape parameter.  k<1: decreasing failure rate (infant
    mortality).  k=1: constant (exponential).  k>1: increasing failure
    rate (wear-out) — typical for mechanical military equipment."""


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class MaintenanceEngine:
    """Manage equipment maintenance cycles and stochastic breakdowns.

    Parameters
    ----------
    event_bus : EventBus
        Publishes ``EquipmentBreakdownEvent``, ``MaintenanceStartedEvent``,
        ``MaintenanceCompletedEvent``.
    rng : numpy.random.Generator
        Deterministic PRNG stream.
    config : MaintenanceConfig | None
        Tuning parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: MaintenanceConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or MaintenanceConfig()
        self._records: dict[str, dict[str, MaintenanceRecord]] = {}  # unit_id -> {eq_id -> record}
        self._sim_time: float = 0.0
        # Phase 56c: per-subsystem Weibull shapes
        self._subsystem_shapes: dict[str, float] = {}

    def set_subsystem_shapes(self, shapes: dict[str, float]) -> None:
        """Set per-subsystem Weibull shape parameters.

        Keys are subsystem categories (e.g. ``"engine"``, ``"transmission"``,
        ``"electronics"``).  Equipment IDs are categorized by prefix.
        """
        self._subsystem_shapes = dict(shapes)

    def _get_subsystem_shape(self, eq_id: str) -> float:
        """Return Weibull shape k for an equipment ID based on prefix."""
        if not self._subsystem_shapes:
            return self._config.weibull_shape_k
        eq_lower = eq_id.lower()
        _PREFIX_MAP = {
            "engine_": "engine",
            "trans_": "transmission",
            "elec_": "electronics",
            "radar_": "electronics",
            "radio_": "electronics",
            "optic_": "optics",
            "track_": "drivetrain",
            "wheel_": "drivetrain",
            "turret_": "turret",
            "weapon_": "weapon",
        }
        for prefix, category in _PREFIX_MAP.items():
            if eq_lower.startswith(prefix):
                return self._subsystem_shapes.get(
                    category, self._config.weibull_shape_k,
                )
        return self._config.weibull_shape_k

    def register_equipment(
        self,
        unit_id: str,
        equipment_ids: list[str],
        mtbf_hours: float | None = None,
    ) -> None:
        """Register equipment items for maintenance tracking."""
        mtbf = mtbf_hours or self._config.base_mtbf_hours
        records: dict[str, MaintenanceRecord] = {}
        for eq_id in equipment_ids:
            records[eq_id] = MaintenanceRecord(
                unit_id=unit_id,
                equipment_id=eq_id,
                maintenance_due_hours=mtbf * self._config.maintenance_due_fraction,
            )
        self._records[unit_id] = records
        logger.debug(
            "Registered %d equipment for unit %s (MTBF %.0f hrs)",
            len(equipment_ids), unit_id, mtbf,
        )

    def update(
        self,
        dt_hours: float,
        temperature_c: float = 20.0,
        timestamp: datetime | None = None,
    ) -> list[tuple[str, str]]:
        """Advance maintenance timers and check for breakdowns.

        Returns list of ``(unit_id, equipment_id)`` that broke down.
        """
        self._sim_time += dt_hours
        breakdowns: list[tuple[str, str]] = []

        for unit_id, records in self._records.items():
            for eq_id, rec in records.items():
                if rec.status in (MaintenanceStatus.UNDER_REPAIR,
                                  MaintenanceStatus.AWAITING_PARTS,
                                  MaintenanceStatus.DEADLINE):
                    continue

                # Accumulate operating hours
                rec.hours_since_maintenance += dt_hours

                # Check if maintenance is due
                if (rec.status == MaintenanceStatus.OPERATIONAL
                        and rec.hours_since_maintenance >= rec.maintenance_due_hours):
                    rec.status = MaintenanceStatus.MAINTENANCE_DUE

                # Compute effective MTBF
                mtbf = self._config.base_mtbf_hours
                if rec.status == MaintenanceStatus.MAINTENANCE_DUE:
                    mtbf /= self._config.deferred_maintenance_multiplier

                # Environmental stress
                if (temperature_c >= self._config.environmental_stress_threshold_c
                        or temperature_c <= self._config.cold_stress_threshold_c):
                    mtbf /= self._config.environmental_stress_multiplier

                # Breakdown check: exponential or Weibull
                if mtbf > 0:
                    k = self._get_subsystem_shape(eq_id)
                    if self._config.use_weibull and k != 1.0:
                        # Weibull hazard: h(t) = (k/η)(t/η)^(k-1)
                        # P(fail in dt) = 1 - exp(-h(t) * dt)
                        t = max(rec.hours_since_maintenance, dt_hours)
                        eta = mtbf  # scale parameter = MTBF when k=1
                        hazard = (k / eta) * (t / eta) ** (k - 1.0)
                        p_fail = 1.0 - math.exp(-hazard * dt_hours)
                    else:
                        # Exponential (constant failure rate)
                        p_fail = 1.0 - math.exp(-dt_hours / mtbf)
                    if self._rng.random() < p_fail:
                        rec.status = MaintenanceStatus.AWAITING_PARTS
                        rec.condition = 0.0
                        breakdowns.append((unit_id, eq_id))
                        if timestamp is not None:
                            self._event_bus.publish(EquipmentBreakdownEvent(
                                timestamp=timestamp,
                                source=ModuleId.LOGISTICS,
                                unit_id=unit_id,
                                equipment_id=eq_id,
                            ))
                        logger.info(
                            "Equipment %s/%s broke down (MTBF=%.0f, P=%.4f)",
                            unit_id, eq_id, mtbf, p_fail,
                        )

        return breakdowns

    def start_repair(
        self,
        unit_id: str,
        equipment_id: str,
        spare_parts_available: float = 0.0,
        timestamp: datetime | None = None,
    ) -> bool:
        """Attempt to start repair on an equipment item.

        Returns ``True`` if repair started, ``False`` if insufficient parts.
        """
        rec = self._records[unit_id][equipment_id]
        if rec.status not in (MaintenanceStatus.AWAITING_PARTS,
                               MaintenanceStatus.MAINTENANCE_DUE):
            return False

        if spare_parts_available < self._config.spare_parts_per_repair:
            return False

        rec.status = MaintenanceStatus.UNDER_REPAIR
        rec.repair_start_time = self._sim_time
        rec.estimated_repair_hours = self._config.repair_time_hours
        rec.repair_elapsed = 0.0

        if timestamp is not None:
            self._event_bus.publish(MaintenanceStartedEvent(
                timestamp=timestamp,
                source=ModuleId.LOGISTICS,
                unit_id=unit_id,
                equipment_id=equipment_id,
                estimated_hours=rec.estimated_repair_hours,
            ))
        return True

    def complete_repairs(
        self,
        dt_hours: float,
        timestamp: datetime | None = None,
    ) -> list[tuple[str, str]]:
        """Advance repair timers.  Return ``(unit_id, eq_id)`` of completed repairs."""
        completed: list[tuple[str, str]] = []
        for unit_id, records in self._records.items():
            for eq_id, rec in records.items():
                if rec.status != MaintenanceStatus.UNDER_REPAIR:
                    continue
                rec.repair_elapsed += dt_hours
                if rec.repair_elapsed >= rec.estimated_repair_hours:
                    rec.status = MaintenanceStatus.OPERATIONAL
                    rec.hours_since_maintenance = 0.0
                    rec.condition = self._config.condition_restored_after_repair
                    completed.append((unit_id, eq_id))
                    if timestamp is not None:
                        self._event_bus.publish(MaintenanceCompletedEvent(
                            timestamp=timestamp,
                            source=ModuleId.LOGISTICS,
                            unit_id=unit_id,
                            equipment_id=eq_id,
                            condition_restored=rec.condition,
                        ))
                    logger.info("Repair completed: %s/%s", unit_id, eq_id)
        return completed

    def get_record(self, unit_id: str, equipment_id: str) -> MaintenanceRecord:
        """Return a maintenance record; raises ``KeyError`` if not found."""
        return self._records[unit_id][equipment_id]

    def get_unit_readiness(self, unit_id: str) -> float:
        """Return fraction of equipment operational (0-1)."""
        records = self._records.get(unit_id)
        if not records:
            return 1.0
        operational = sum(
            1 for r in records.values()
            if r.status == MaintenanceStatus.OPERATIONAL
        )
        return operational / len(records)

    # -- State protocol --

    def get_state(self) -> dict:
        """Serialize for checkpoint."""
        return {
            "sim_time": self._sim_time,
            "records": {
                uid: {
                    eq_id: {
                        "unit_id": r.unit_id,
                        "equipment_id": r.equipment_id,
                        "status": int(r.status),
                        "hours_since_maintenance": r.hours_since_maintenance,
                        "maintenance_due_hours": r.maintenance_due_hours,
                        "repair_start_time": r.repair_start_time,
                        "estimated_repair_hours": r.estimated_repair_hours,
                        "repair_elapsed": r.repair_elapsed,
                        "condition": r.condition,
                    }
                    for eq_id, r in records.items()
                }
                for uid, records in self._records.items()
            },
        }

    def set_state(self, state: dict) -> None:
        """Restore from checkpoint."""
        self._sim_time = state.get("sim_time", 0.0)
        self._records.clear()
        for uid, records_data in state["records"].items():
            records: dict[str, MaintenanceRecord] = {}
            for eq_id, rd in records_data.items():
                records[eq_id] = MaintenanceRecord(
                    unit_id=rd["unit_id"],
                    equipment_id=rd["equipment_id"],
                    status=MaintenanceStatus(rd["status"]),
                    hours_since_maintenance=rd["hours_since_maintenance"],
                    maintenance_due_hours=rd["maintenance_due_hours"],
                    repair_start_time=rd.get("repair_start_time"),
                    estimated_repair_hours=rd["estimated_repair_hours"],
                    repair_elapsed=rd.get("repair_elapsed", 0.0),
                    condition=rd["condition"],
                )
            self._records[uid] = records
