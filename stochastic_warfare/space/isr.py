"""Typed, delayed space-based imagery reporting.

Optical and SAR overpasses remain deterministic orbital observations.  A
scenario opts individual catalog constellations into imagery fusion; those
constellations produce immutable reports that are acknowledged only after an
owner-scoped intelligence-fusion transaction succeeds.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from heapq import merge
from typing import Any, Literal, Mapping, Sequence

import numpy as np
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.detection.intel_fusion import (
    IntelDeliveryReceipt,
    IntelFusionEngine,
)
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.space.constellations import (
    ConstellationManager,
    ConstellationType,
    SpaceConfig,
)
from stochastic_warfare.space.events import SatelliteOverpassEvent

logger = get_logger(__name__)

# Resolution thresholds — maximum ground resolution for each modeled size.
_RESOLUTION_THRESHOLD: dict[str, float] = {
    "vehicle": 0.5,
    "platoon": 2.0,
    "company": 5.0,
    "battalion": 15.0,
}


class SpaceISRIntegrityError(RuntimeError):
    """Base class for a fail-closed Space imagery integrity error."""


class UnsupportedISRTargetError(SpaceISRIntegrityError):
    """Raised when a report candidate is not a real loaded :class:`Unit`."""


class SpaceISRDeliveryError(SpaceISRIntegrityError):
    """Raised when an eligible report cannot be fused transactionally."""


def _identifier(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be a non-empty trimmed string")
    return value


def _finite_number(
    value: Any,
    field_name: str,
    *,
    positive: bool = False,
    non_negative: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{field_name} must be a finite number")
    if positive and normalized <= 0.0:
        raise ValueError(f"{field_name} must be positive")
    if non_negative and normalized < 0.0:
        raise ValueError(f"{field_name} must be non-negative")
    return normalized


class SpaceISRReport(BaseModel):
    """One immutable catalog-backed imagery observation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: int
    reporting_side: str
    target_side: str
    target_id: str
    satellite_id: str
    constellation_id: str
    sensor_type: Literal["optical", "sar"]
    resolution_m: float
    position_sigma_m: float
    target_position: Position
    observed_at_s: float
    available_at_s: float

    @field_validator("report_id", mode="before")
    @classmethod
    def _positive_report_id(cls, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("report_id must be a positive integer")
        return value

    @field_validator(
        "reporting_side",
        "target_side",
        "target_id",
        "satellite_id",
        "constellation_id",
        mode="before",
    )
    @classmethod
    def _identifiers(cls, value: Any, info: Any) -> str:
        return _identifier(value, info.field_name)

    @field_validator(
        "resolution_m",
        "position_sigma_m",
        mode="before",
    )
    @classmethod
    def _positive_numbers(cls, value: Any, info: Any) -> float:
        return _finite_number(value, info.field_name, positive=True)

    @field_validator(
        "observed_at_s",
        "available_at_s",
        mode="before",
    )
    @classmethod
    def _times(cls, value: Any, info: Any) -> float:
        return _finite_number(value, info.field_name, non_negative=True)

    @field_validator("target_position", mode="before")
    @classmethod
    def _position(cls, value: Any) -> Position:
        if isinstance(value, Position):
            values = tuple(value)
        elif isinstance(value, (list, tuple)) and len(value) == 3:
            values = tuple(value)
        else:
            raise ValueError(
                "target_position must contain exactly three ENU numbers",
            )
        return Position(
            *(_finite_number(component, f"target_position[{index}]") for index, component in enumerate(values)),
        )

    @model_validator(mode="after")
    def _valid_temporal_and_side_contract(self) -> SpaceISRReport:
        if self.reporting_side == self.target_side:
            raise ValueError("reporting_side and target_side must differ")
        if self.available_at_s < self.observed_at_s:
            raise ValueError("available_at_s may not precede observed_at_s")
        return self

    def to_state(self) -> dict[str, Any]:
        """Return the exact checkpoint/public representation."""
        return {
            "report_id": self.report_id,
            "reporting_side": self.reporting_side,
            "target_side": self.target_side,
            "target_id": self.target_id,
            "satellite_id": self.satellite_id,
            "constellation_id": self.constellation_id,
            "sensor_type": self.sensor_type,
            "resolution_m": self.resolution_m,
            "position_sigma_m": self.position_sigma_m,
            "target_position": list(self.target_position),
            "observed_at_s": self.observed_at_s,
            "available_at_s": self.available_at_s,
        }

    def canonical_without_id(self) -> tuple[Any, ...]:
        """Return the duplicate-detection tuple excluding acknowledgement ID."""
        return (
            self.reporting_side,
            self.target_side,
            self.target_id,
            self.satellite_id,
            self.constellation_id,
            self.sensor_type,
            self.resolution_m,
            self.position_sigma_m,
            tuple(self.target_position),
            self.observed_at_s,
            self.available_at_s,
        )

    def digest(self) -> str:
        """SHA-256 of the canonical complete serialized report."""
        payload = json.dumps(
            self.to_state(),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


def _queue_order(report: SpaceISRReport) -> tuple[Any, ...]:
    return (
        report.available_at_s,
        report.observed_at_s,
        report.reporting_side,
        report.constellation_id,
        report.satellite_id,
        report.target_id,
        report.report_id,
    )


def _same_epoch_order(report: SpaceISRReport) -> tuple[Any, ...]:
    return (
        report.constellation_id,
        report.satellite_id,
        report.report_id,
    )


@dataclass(frozen=True, slots=True)
class _ISRTargetSnapshot:
    """Validated target values frozen before a Space update mutates state."""

    entity_id: str
    side: str
    position: Position
    status: UnitStatus
    personnel_count: int


@dataclass(frozen=True, slots=True)
class SpaceISRUpdatePlan:
    """Immutable target/input preflight for one logical Space update."""

    dt_s: float
    sim_time_s: float
    cloud_cover: float
    sides: tuple[str, ...]
    targets_by_side: tuple[
        tuple[str, tuple[_ISRTargetSnapshot, ...]],
        ...,
    ]


class SpaceISREngine:
    """Space overpass, report queue, and transactional delivery owner."""

    def __init__(
        self,
        constellation_manager: ConstellationManager,
        config: SpaceConfig,
        event_bus: EventBus,
        rng: np.random.Generator,
        clock: Any = None,
        *,
        scenario_sides: Sequence[str] = (),
    ) -> None:
        sides = tuple(scenario_sides)
        if len(sides) != len(set(sides)):
            raise ValueError("scenario_sides must be unique")
        for side in sides:
            _identifier(side, "scenario_sides entry")
        self._cm = constellation_manager
        self._config = config
        self._event_bus = event_bus
        self._rng = rng
        self._clock = clock
        self._scenario_sides = sides
        self._last_overpass_time: dict[str, float] = {}
        self._last_reported_at: dict[tuple[str, str, str], float] = {}
        self._report_queue: deque[SpaceISRReport] = deque()
        self._next_report_sequence = 1

    def _timestamp(self) -> datetime:
        if self._clock is not None:
            return self._clock.current_time
        return datetime(2024, 1, 1, tzinfo=timezone.utc)

    def check_overpass(
        self,
        side: str,
        sim_time_s: float,
    ) -> list[SatelliteOverpassEvent]:
        """Publish one event per visible satellite after 60 s hysteresis."""
        _identifier(side, "side")
        normalized_time = _finite_number(
            sim_time_s,
            "sim_time_s",
            non_negative=True,
        )
        events: list[SatelliteOverpassEvent] = []
        isr_types = {
            ConstellationType.IMAGING_OPTICAL,
            ConstellationType.IMAGING_SAR,
            ConstellationType.SIGINT,
        }
        definitions = sorted(
            self._cm.get_constellations_by_side(side),
            key=lambda definition: definition.constellation_id,
        )
        for definition in definitions:
            if definition.constellation_type not in isr_types:
                continue
            visible = sorted(
                self._cm.visible_satellites(
                    definition.constellation_id,
                    self._config.theater_lat,
                    self._config.theater_lon,
                    normalized_time,
                    self._config.min_elevation_deg,
                ),
                key=lambda satellite: satellite.satellite_id,
            )
            for satellite in visible:
                last = self._last_overpass_time.get(
                    satellite.satellite_id,
                    -1.0e9,
                )
                if normalized_time - last < 60.0:
                    continue
                self._last_overpass_time[satellite.satellite_id] = normalized_time
                event = SatelliteOverpassEvent(
                    timestamp=self._timestamp(),
                    source=ModuleId.SPACE,
                    satellite_id=satellite.satellite_id,
                    constellation_id=definition.constellation_id,
                    side=side,
                    overpass_start=True,
                    coverage_center_x=self._config.theater_lat,
                    coverage_center_y=self._config.theater_lon,
                    coverage_radius_m=definition.sensor_swath_km * 500.0,
                    resolution_m=definition.sensor_resolution_m,
                )
                events.append(event)
                self._event_bus.publish(event)
        return events

    @staticmethod
    def _validate_target(
        target: Any,
        target_side: str,
    ) -> Unit:
        if not isinstance(target, Unit):
            raise UnsupportedISRTargetError(
                f"Space imagery targets must be repository Unit instances; got {type(target).__name__}",
            )
        try:
            _identifier(target.entity_id, "target entity_id")
            for index, component in enumerate(target.position):
                _finite_number(
                    component,
                    f"target {target.entity_id!r} position[{index}]",
                )
        except (TypeError, ValueError) as exc:
            raise UnsupportedISRTargetError(
                f"Target {target.entity_id!r} has invalid imagery state: {exc}",
            ) from exc
        if target.side != target_side:
            raise UnsupportedISRTargetError(
                f"Target {target.entity_id!r} side {target.side!r} does not match target_side {target_side!r}",
            )
        if not isinstance(target.position, Position):
            raise UnsupportedISRTargetError(
                f"Target {target.entity_id!r} has no finite Position",
            )
        if not isinstance(target.status, UnitStatus):
            raise UnsupportedISRTargetError(
                f"Target {target.entity_id!r} has invalid UnitStatus",
            )
        if not isinstance(target.personnel, list):
            raise UnsupportedISRTargetError(
                f"Target {target.entity_id!r} personnel must be a list",
            )
        return target

    @staticmethod
    def _estimate_unit_size(target: _ISRTargetSnapshot) -> str:
        strength = target.personnel_count
        if strength <= 4:
            return "vehicle"
        if strength <= 40:
            return "platoon"
        if strength <= 200:
            return "company"
        return "battalion"

    def _validate_target_batch(
        self,
        target_side: str,
        targets: Sequence[Unit],
    ) -> tuple[_ISRTargetSnapshot, ...]:
        if not isinstance(targets, Sequence) or isinstance(
            targets,
            (str, bytes),
        ):
            raise UnsupportedISRTargetError("targets must be a Unit sequence")
        validated_targets = tuple(self._validate_target(target, target_side) for target in targets)
        target_ids = [target.entity_id for target in validated_targets]
        if len(target_ids) != len(set(target_ids)):
            raise SpaceISRIntegrityError(
                f"Duplicate target IDs for side {target_side!r}",
            )
        return tuple(
            _ISRTargetSnapshot(
                entity_id=target.entity_id,
                side=target.side,
                position=Position(*target.position),
                status=target.status,
                personnel_count=len(target.personnel),
            )
            for target in validated_targets
        )

    def _build_isr_candidates(
        self,
        reporting_side: str,
        target_side: str,
        targets: Sequence[_ISRTargetSnapshot],
        sim_time_s: float,
        cloud_cover: float = 0.0,
        *,
        scenario_sides: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Validate and build report candidates without mutating runtime state."""
        normalized_time = _finite_number(
            sim_time_s,
            "sim_time_s",
            non_negative=True,
        )
        normalized_cloud = _finite_number(cloud_cover, "cloud_cover")
        if not 0.0 <= normalized_cloud <= 1.0:
            raise ValueError("cloud_cover must be in [0, 1]")
        sides = set(self._scenario_sides if scenario_sides is None else scenario_sides)
        if reporting_side not in sides or target_side not in sides:
            raise SpaceISRIntegrityError(
                "Space imagery sides must be exact loaded scenario IDs",
            )
        if reporting_side == target_side:
            raise SpaceISRIntegrityError(
                "Space imagery reporting and target sides must differ",
            )
        validated_targets = tuple(targets)
        if any(
            not isinstance(target, _ISRTargetSnapshot) or target.side != target_side for target in validated_targets
        ):
            raise SpaceISRIntegrityError(
                "Space imagery candidates require a validated owner-scoped target snapshot",
            )

        candidates: list[dict[str, Any]] = []
        seen_candidate_keys: set[tuple[str, str, str, float]] = set()
        for constellation_id in sorted(
            self._config.imint_fusion_constellation_ids,
        ):
            definition = self._cm.get_constellation(constellation_id)
            if definition is None:
                raise SpaceISRIntegrityError(
                    f"Unknown configured constellation {constellation_id!r}",
                )
            if definition.side != reporting_side:
                continue
            if definition.imint_position_sigma_m is None or definition.constellation_type not in {
                ConstellationType.IMAGING_OPTICAL,
                ConstellationType.IMAGING_SAR,
            }:
                raise SpaceISRIntegrityError(
                    f"Configured constellation {constellation_id!r} is not eligible for imagery fusion",
                )
            if (
                definition.sensor_type == "optical"
                and self._config.cloud_cover_blocks_optical
                and normalized_cloud > 0.7
            ):
                continue
            visible = sorted(
                self._cm.visible_satellites(
                    constellation_id,
                    self._config.theater_lat,
                    self._config.theater_lon,
                    normalized_time,
                    self._config.min_elevation_deg,
                ),
                key=lambda satellite: satellite.satellite_id,
            )
            for satellite in visible:
                for target in sorted(
                    validated_targets,
                    key=lambda unit: unit.entity_id,
                ):
                    if target.status is not UnitStatus.ACTIVE:
                        continue
                    threshold = _RESOLUTION_THRESHOLD[self._estimate_unit_size(target)]
                    if definition.sensor_resolution_m > threshold:
                        continue
                    cadence_key = (
                        reporting_side,
                        satellite.satellite_id,
                        target.entity_id,
                    )
                    if self._last_reported_at.get(cadence_key) == normalized_time:
                        continue
                    candidate_key = (
                        reporting_side,
                        satellite.satellite_id,
                        target.entity_id,
                        normalized_time,
                    )
                    if candidate_key in seen_candidate_keys:
                        raise SpaceISRIntegrityError(
                            "Duplicate Space imagery candidate in one update",
                        )
                    seen_candidate_keys.add(candidate_key)
                    candidates.append(
                        {
                            "reporting_side": reporting_side,
                            "target_side": target_side,
                            "target_id": target.entity_id,
                            "satellite_id": satellite.satellite_id,
                            "constellation_id": constellation_id,
                            "sensor_type": definition.sensor_type,
                            "resolution_m": (definition.sensor_resolution_m),
                            "position_sigma_m": (definition.imint_position_sigma_m),
                            "target_position": Position(*target.position),
                            "observed_at_s": normalized_time,
                            "available_at_s": (normalized_time + self._config.isr_processing_delay_s),
                        },
                    )
        return candidates

    def _selected_fusion_owner_sides(self) -> frozenset[str]:
        """Return exact owners for selected fusion constellations."""
        owners: set[str] = set()
        for constellation_id in self._config.imint_fusion_constellation_ids:
            definition = self._cm.get_constellation(constellation_id)
            if definition is None:
                raise SpaceISRIntegrityError(
                    f"Unknown configured constellation {constellation_id!r}",
                )
            owners.add(definition.side)
        return frozenset(owners)

    def _stage_isr_reports(
        self,
        candidates: Sequence[dict[str, Any]],
    ) -> tuple[tuple[SpaceISRReport, ...], int]:
        """Create a complete canonical typed batch without state mutation."""
        rng_before = copy.deepcopy(self._rng.bit_generator.state)
        reports: list[SpaceISRReport] = []
        next_sequence = self._next_report_sequence
        try:
            ordered_candidates = sorted(
                candidates,
                key=lambda candidate: (
                    candidate["reporting_side"],
                    candidate["constellation_id"],
                    candidate["satellite_id"],
                    candidate["target_id"],
                    candidate["target_side"],
                ),
            )
            semantic_keys: set[tuple[Any, ...]] = set()
            for candidate in ordered_candidates:
                semantic_key = (
                    candidate["reporting_side"],
                    candidate["target_side"],
                    candidate["target_id"],
                    candidate["satellite_id"],
                    candidate["constellation_id"],
                    candidate["sensor_type"],
                    candidate["resolution_m"],
                    candidate["position_sigma_m"],
                    tuple(candidate["target_position"]),
                    candidate["observed_at_s"],
                    candidate["available_at_s"],
                )
                if semantic_key in semantic_keys:
                    raise SpaceISRIntegrityError(
                        "Duplicate Space imagery candidate in one update",
                    )
                semantic_keys.add(semantic_key)
                reports.append(
                    SpaceISRReport(
                        report_id=next_sequence,
                        **candidate,
                    ),
                )
                next_sequence += 1
        except Exception:
            self._rng.bit_generator.state = rng_before
            raise
        return tuple(reports), next_sequence

    def _commit_isr_reports(
        self,
        reports: Sequence[SpaceISRReport],
        next_sequence: int,
    ) -> None:
        """Commit one previously staged report batch."""
        if reports:
            ordered_reports = sorted(reports, key=_queue_order)
            new_queue = deque(
                merge(
                    self._report_queue,
                    ordered_reports,
                    key=_queue_order,
                ),
            )
            new_last = dict(self._last_reported_at)
            for report in reports:
                new_last[
                    (
                        report.reporting_side,
                        report.satellite_id,
                        report.target_id,
                    )
                ] = report.observed_at_s
            self._report_queue = new_queue
            self._last_reported_at = new_last
            self._next_report_sequence = next_sequence

    def generate_isr_reports(
        self,
        reporting_side: str,
        target_side: str,
        targets: Sequence[Unit],
        sim_time_s: float,
        cloud_cover: float = 0.0,
    ) -> tuple[SpaceISRReport, ...]:
        """Atomically generate one canonical report batch."""
        fusion_owner_sides = self._selected_fusion_owner_sides()
        if self._config.imint_fusion_constellation_ids and reporting_side not in fusion_owner_sides:
            raise SpaceISRIntegrityError(
                f"Reporting side {reporting_side!r} does not own a selected imagery-fusion constellation",
            )
        validated_targets = self._validate_target_batch(
            target_side,
            targets,
        )
        candidates = self._build_isr_candidates(
            reporting_side,
            target_side,
            validated_targets,
            sim_time_s,
            cloud_cover,
        )
        reports, next_sequence = self._stage_isr_reports(candidates)
        self._commit_isr_reports(reports, next_sequence)
        return tuple(reports)

    def process_ready_reports(
        self,
        intel_fusion: IntelFusionEngine,
        sim_time_s: float,
    ) -> tuple[IntelDeliveryReceipt, ...]:
        """Deliver ready reports as ordered per-report transactions."""
        normalized_time = _finite_number(
            sim_time_s,
            "sim_time_s",
            non_negative=True,
        )
        receipts: list[IntelDeliveryReceipt] = []
        while self._report_queue and self._report_queue[0].available_at_s <= normalized_time:
            report = self._report_queue[0]
            try:
                plan = intel_fusion.prepare_imint_report(
                    report,
                    delivery_time_s=normalized_time,
                )
                receipt = intel_fusion.commit_imint_report(plan)
            except Exception as exc:
                raise SpaceISRDeliveryError(
                    f"Failed to deliver Space ISR report {report.report_id}: {exc}",
                ) from exc
            self._report_queue.popleft()
            receipts.append(receipt)
        try:
            intel_fusion.manage_imint_lifecycle(normalized_time)
        except SpaceISRIntegrityError:
            raise
        except Exception as exc:
            raise SpaceISRDeliveryError(
                "Failed to manage imagery-fusion lifecycle",
            ) from exc
        return tuple(receipts)

    def prepare_update(
        self,
        dt_s: float,
        sim_time_s: float,
        targets_by_side: Mapping[str, Sequence[Unit]] | None = None,
        cloud_cover: float = 0.0,
        *,
        intel_fusion: IntelFusionEngine | None = None,
    ) -> SpaceISRUpdatePlan:
        """Validate and freeze target inputs before any Space state changes."""
        normalized_dt = _finite_number(
            dt_s,
            "dt_s",
            non_negative=True,
        )
        normalized_time = _finite_number(
            sim_time_s,
            "sim_time_s",
            non_negative=True,
        )
        normalized_cloud = _finite_number(cloud_cover, "cloud_cover")
        if not 0.0 <= normalized_cloud <= 1.0:
            raise ValueError("cloud_cover must be in [0, 1]")
        if targets_by_side is None:
            targets_by_side = {}
        if not isinstance(targets_by_side, Mapping):
            raise UnsupportedISRTargetError(
                "targets_by_side must be a side-to-Unit mapping",
            )
        for side in targets_by_side:
            _identifier(side, "targets_by_side side")
        sides = tuple(sorted(targets_by_side))
        if self._scenario_sides and set(sides) != set(self._scenario_sides):
            raise SpaceISRIntegrityError(
                "Space imagery target sides do not match loaded scenario sides",
            )

        validated_targets: dict[str, tuple[_ISRTargetSnapshot, ...]] = {side: () for side in sides}
        if self._config.imint_fusion_constellation_ids:
            if intel_fusion is None:
                raise SpaceISRIntegrityError(
                    "Selected Space imagery fusion requires IntelFusionEngine",
                )
            validated_targets = {
                side: self._validate_target_batch(
                    side,
                    targets_by_side[side],
                )
                for side in sides
            }
            target_ids = [target.entity_id for side in sides for target in validated_targets[side]]
            if len(target_ids) != len(set(target_ids)):
                raise SpaceISRIntegrityError(
                    "Space imagery target IDs must be globally unique",
                )
        if intel_fusion is not None:
            try:
                intel_fusion.prepare_imint_lifecycle(normalized_time)
            except SpaceISRIntegrityError:
                raise
            except Exception as exc:
                raise SpaceISRDeliveryError(
                    "Failed to preflight imagery-fusion lifecycle",
                ) from exc
        return SpaceISRUpdatePlan(
            dt_s=normalized_dt,
            sim_time_s=normalized_time,
            cloud_cover=normalized_cloud,
            sides=sides,
            targets_by_side=tuple((side, validated_targets[side]) for side in sides),
        )

    def _apply_update(
        self,
        plan: SpaceISRUpdatePlan,
        *,
        intel_fusion: IntelFusionEngine | None = None,
    ) -> None:
        """Apply one type-checked target/input update plan."""
        normalized_time = plan.sim_time_s
        sides = plan.sides
        validated_targets = dict(plan.targets_by_side)

        reports: tuple[SpaceISRReport, ...] = ()
        next_sequence = self._next_report_sequence
        if self._config.imint_fusion_constellation_ids:
            if intel_fusion is None:
                raise SpaceISRIntegrityError(
                    "Selected Space imagery fusion requires IntelFusionEngine",
                )
            scenario_sides = self._scenario_sides or sides
            fusion_owner_sides = self._selected_fusion_owner_sides()
            candidates: list[dict[str, Any]] = []
            for reporting_side in sides:
                if reporting_side not in fusion_owner_sides:
                    continue
                for target_side in sides:
                    if target_side == reporting_side:
                        continue
                    candidates.extend(
                        self._build_isr_candidates(
                            reporting_side,
                            target_side,
                            validated_targets[target_side],
                            normalized_time,
                            plan.cloud_cover,
                            scenario_sides=scenario_sides,
                        ),
                    )
            reports, next_sequence = self._stage_isr_reports(candidates)

        overpass_events: list[SatelliteOverpassEvent] = []
        for side in sides:
            overpass_events.extend(
                self.check_overpass(side, normalized_time),
            )
        if not self._scenario_sides:
            self._scenario_sides = sides
        if self._config.imint_fusion_constellation_ids:
            self._commit_isr_reports(reports, next_sequence)
            from stochastic_warfare.detection.intel_fusion import SatellitePass

            selected = set(self._config.imint_fusion_constellation_ids)
            for event in sorted(
                (event for event in overpass_events if event.constellation_id in selected),
                key=lambda event: (
                    event.side,
                    event.constellation_id,
                    event.satellite_id,
                ),
            ):
                intel_fusion.add_satellite_pass(
                    event.side,
                    SatellitePass(
                        satellite_id=event.satellite_id,
                        constellation_id=event.constellation_id,
                        side=event.side,
                        start_time=normalized_time,
                        end_time=normalized_time + 60.0,
                        coverage_center_x=event.coverage_center_x,
                        coverage_center_y=event.coverage_center_y,
                        coverage_radius_m=event.coverage_radius_m,
                        resolution_m=event.resolution_m,
                        revisit_interval_s=60.0,
                    ),
                )
            self.process_ready_reports(intel_fusion, normalized_time)
        elif intel_fusion is not None:
            try:
                intel_fusion.manage_imint_lifecycle(normalized_time)
            except SpaceISRIntegrityError:
                raise
            except Exception as exc:
                raise SpaceISRDeliveryError(
                    "Failed to manage imagery-fusion lifecycle",
                ) from exc

    def apply_update(
        self,
        plan: SpaceISRUpdatePlan,
        *,
        intel_fusion: IntelFusionEngine | None = None,
    ) -> None:
        """Apply a validated plan and type unexpected ISR failures."""
        if not isinstance(plan, SpaceISRUpdatePlan):
            raise TypeError("plan must be a SpaceISRUpdatePlan")
        try:
            self._apply_update(plan, intel_fusion=intel_fusion)
        except SpaceISRIntegrityError:
            raise
        except Exception as exc:
            raise SpaceISRIntegrityError(
                "Unexpected Space ISR generation or fusion failure",
            ) from exc

    def update(
        self,
        dt_s: float,
        sim_time_s: float,
        targets_by_side: Mapping[str, Sequence[Unit]] | None = None,
        cloud_cover: float = 0.0,
        *,
        intel_fusion: IntelFusionEngine | None = None,
    ) -> None:
        """Preflight, then run report generation and fusion boundaries."""
        plan = self.prepare_update(
            dt_s,
            sim_time_s,
            targets_by_side,
            cloud_cover,
            intel_fusion=intel_fusion,
        )
        self.apply_update(plan, intel_fusion=intel_fusion)

    def get_recent_reports(
        self,
        *,
        clear: bool = False,
    ) -> tuple[SpaceISRReport, ...]:
        """Return queued reports without bypassing acknowledgement."""
        if clear:
            raise SpaceISRIntegrityError(
                "Space ISR reports may only be cleared by successful delivery",
            )
        return tuple(self._report_queue)

    def get_state(self) -> dict[str, Any]:
        return {
            "last_overpass_time": {
                satellite_id: value
                for satellite_id, value in sorted(
                    self._last_overpass_time.items(),
                )
            },
            "last_reported_at": [
                {
                    "reporting_side": key[0],
                    "satellite_id": key[1],
                    "target_id": key[2],
                    "observed_at_s": value,
                }
                for key, value in sorted(self._last_reported_at.items())
            ],
            "report_queue": [report.to_state() for report in self._report_queue],
            "next_report_sequence": self._next_report_sequence,
        }

    def stage_state(
        self,
        state: dict[str, Any],
        *,
        expected_elapsed_s: float | None = None,
        expected_sides: Sequence[str] | None = None,
        expected_units_by_side: Mapping[str, Sequence[Unit]] | None = None,
        delivered_receipts: Sequence[IntelDeliveryReceipt] = (),
    ) -> dict[str, Any]:
        """Validate the complete ISR snapshot without mutation."""
        if not isinstance(state, dict):
            raise ValueError("ISR state must be a mapping")
        expected_keys = {
            "last_overpass_time",
            "last_reported_at",
            "report_queue",
            "next_report_sequence",
        }
        if set(state) != expected_keys:
            raise ValueError(
                f"ISR state keys must be exactly {sorted(expected_keys)!r}",
            )
        elapsed = (
            None
            if expected_elapsed_s is None
            else _finite_number(
                expected_elapsed_s,
                "expected_elapsed_s",
                non_negative=True,
            )
        )
        sides = set(expected_sides or self._scenario_sides)
        if not sides:
            raise ValueError("ISR restore requires exact scenario sides")
        known_satellites = {satellite.satellite_id: satellite for satellite in self._cm.all_satellites()}
        known_constellations = {definition.constellation_id: definition for definition in self._cm.all_constellations()}

        raw_overpasses = state["last_overpass_time"]
        if not isinstance(raw_overpasses, dict):
            raise ValueError("ISR last_overpass_time must be a mapping")
        overpasses: dict[str, float] = {}
        for satellite_id, raw_time in raw_overpasses.items():
            _identifier(satellite_id, "last_overpass_time key")
            if satellite_id not in known_satellites:
                raise ValueError(
                    f"ISR overpass references unknown satellite {satellite_id!r}",
                )
            value = _finite_number(
                raw_time,
                f"last_overpass_time[{satellite_id!r}]",
                non_negative=True,
            )
            if elapsed is not None and value > elapsed:
                raise ValueError("ISR overpass time is after checkpoint time")
            overpasses[satellite_id] = value

        target_sides: dict[str, str] = {}
        if expected_units_by_side is not None:
            if set(expected_units_by_side) != sides:
                raise ValueError(
                    "ISR restore unit sides do not match scenario sides",
                )
            for side, units in expected_units_by_side.items():
                for unit in units:
                    validated = self._validate_target(unit, side)
                    if validated.entity_id in target_sides:
                        raise ValueError(
                            f"Duplicate unit ID {validated.entity_id!r} in ISR restore topology",
                        )
                    target_sides[validated.entity_id] = side

        raw_queue = state["report_queue"]
        if not isinstance(raw_queue, list):
            raise ValueError("ISR report_queue must be a list")
        queue: list[SpaceISRReport] = []
        report_ids: set[int] = set()
        report_tuples: set[tuple[Any, ...]] = set()
        for index, raw_report in enumerate(raw_queue):
            try:
                report = SpaceISRReport.model_validate(raw_report)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid ISR report_queue[{index}]: {exc}",
                ) from exc
            self._validate_restored_report(
                report,
                sides=sides,
                target_sides=target_sides,
                known_satellites=known_satellites,
                known_constellations=known_constellations,
                elapsed=elapsed,
            )
            if report.report_id in report_ids:
                raise ValueError(
                    f"Duplicate ISR report_id {report.report_id}",
                )
            canonical = report.canonical_without_id()
            if canonical in report_tuples:
                raise ValueError("Duplicate ISR report semantic tuple")
            report_ids.add(report.report_id)
            report_tuples.add(canonical)
            queue.append(report)
        if queue != sorted(queue, key=_queue_order):
            raise ValueError("ISR report_queue is not canonically ordered")

        raw_next = state["next_report_sequence"]
        if isinstance(raw_next, bool) or not isinstance(raw_next, int) or raw_next <= 0:
            raise ValueError(
                "ISR next_report_sequence must be a positive integer",
            )

        receipt_reports: list[SpaceISRReport] = []
        for index, receipt in enumerate(delivered_receipts):
            if not isinstance(receipt, IntelDeliveryReceipt):
                raise ValueError(
                    f"Delivered ISR receipt {index} must be an "
                    "IntelDeliveryReceipt instance",
                )
            try:
                receipt_report = SpaceISRReport.model_validate(
                    receipt.report_state(),
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid delivered ISR receipt {index}: {exc}",
                ) from exc
            self._validate_restored_report(
                receipt_report,
                sides=sides,
                target_sides=target_sides,
                known_satellites=known_satellites,
                known_constellations=known_constellations,
                elapsed=elapsed,
            )
            if receipt_report.report_id in report_ids:
                raise ValueError(
                    "Queued and delivered ISR report IDs must be disjoint",
                )
            if receipt_report.canonical_without_id() in report_tuples:
                raise ValueError(
                    "Queued and delivered ISR semantic tuples must be unique",
                )
            report_ids.add(receipt_report.report_id)
            report_tuples.add(receipt_report.canonical_without_id())
            receipt_reports.append(receipt_report)
        if report_ids != set(range(1, raw_next)):
            raise ValueError(
                "Queued and delivered report IDs must exactly cover every issued sequence",
            )
        latest_delivered: dict[tuple[str, str], SpaceISRReport] = {}
        for report in receipt_reports:
            key = (report.reporting_side, report.target_id)
            prior = latest_delivered.get(key)
            if prior is None or (
                report.observed_at_s,
                *_same_epoch_order(report),
            ) > (
                prior.observed_at_s,
                *_same_epoch_order(prior),
            ):
                latest_delivered[key] = report
        for report in queue:
            prior = latest_delivered.get(
                (report.reporting_side, report.target_id),
            )
            if prior is None:
                continue
            if report.observed_at_s < prior.observed_at_s:
                raise ValueError(
                    "Queued ISR report predates the latest delivered owner/target observation",
                )
            if report.observed_at_s == prior.observed_at_s and _same_epoch_order(report) <= _same_epoch_order(prior):
                raise ValueError(
                    "Queued same-epoch ISR report precedes the latest delivered canonical order",
                )

        raw_cadence = state["last_reported_at"]
        if not isinstance(raw_cadence, list):
            raise ValueError("ISR last_reported_at must be a list")
        cadence: dict[tuple[str, str, str], float] = {}
        cadence_keys = {
            "reporting_side",
            "satellite_id",
            "target_id",
            "observed_at_s",
        }
        for index, raw_entry in enumerate(raw_cadence):
            if not isinstance(raw_entry, dict) or set(raw_entry) != cadence_keys:
                raise ValueError(
                    f"ISR last_reported_at[{index}] has invalid keys",
                )
            key = (
                _identifier(
                    raw_entry["reporting_side"],
                    "last_reported_at reporting_side",
                ),
                _identifier(
                    raw_entry["satellite_id"],
                    "last_reported_at satellite_id",
                ),
                _identifier(
                    raw_entry["target_id"],
                    "last_reported_at target_id",
                ),
            )
            if key in cadence:
                raise ValueError("Duplicate ISR last_reported_at key")
            cadence[key] = _finite_number(
                raw_entry["observed_at_s"],
                "last_reported_at observed_at_s",
                non_negative=True,
            )
        if list(cadence) != sorted(cadence):
            raise ValueError("ISR last_reported_at is not canonically ordered")
        issued = [*queue, *receipt_reports]
        derived: dict[tuple[str, str, str], float] = {}
        for report in issued:
            key = (
                report.reporting_side,
                report.satellite_id,
                report.target_id,
            )
            derived[key] = max(
                report.observed_at_s,
                derived.get(key, -1.0),
            )
        if cadence != derived:
            raise ValueError(
                "ISR last_reported_at does not match issued reports",
            )

        return {
            "last_overpass_time": overpasses,
            "last_reported_at": cadence,
            "report_queue": queue,
            "next_report_sequence": raw_next,
        }

    def _validate_restored_report(
        self,
        report: SpaceISRReport,
        *,
        sides: set[str],
        target_sides: Mapping[str, str],
        known_satellites: Mapping[str, Any],
        known_constellations: Mapping[str, Any],
        elapsed: float | None,
    ) -> None:
        if report.reporting_side not in sides or report.target_side not in sides:
            raise ValueError("ISR report references unknown scenario side")
        satellite = known_satellites.get(report.satellite_id)
        definition = known_constellations.get(report.constellation_id)
        if satellite is None or definition is None:
            raise ValueError(
                "ISR report references unknown satellite or constellation",
            )
        if satellite.constellation_id != report.constellation_id:
            raise ValueError("ISR satellite/constellation reference mismatch")
        if satellite.side != report.reporting_side or definition.side != report.reporting_side:
            raise ValueError("ISR report constellation ownership mismatch")
        if report.constellation_id not in (self._config.imint_fusion_constellation_ids):
            raise ValueError(
                "ISR report uses an unselected fusion constellation",
            )
        expected_sensor = {
            ConstellationType.IMAGING_OPTICAL: "optical",
            ConstellationType.IMAGING_SAR: "sar",
        }.get(definition.constellation_type)
        if expected_sensor is None or report.sensor_type != expected_sensor:
            raise ValueError("ISR report uses a non-imaging sensor type")
        if (
            report.resolution_m != definition.sensor_resolution_m
            or report.position_sigma_m != definition.imint_position_sigma_m
        ):
            raise ValueError("ISR report disagrees with catalog sensor values")
        if report.available_at_s != (report.observed_at_s + self._config.isr_processing_delay_s):
            raise ValueError("ISR report availability disagrees with delay")
        if elapsed is not None and report.observed_at_s > elapsed:
            raise ValueError("ISR report observation is after checkpoint time")
        if target_sides:
            actual_side = target_sides.get(report.target_id)
            if actual_side != report.target_side:
                raise ValueError(
                    "ISR report target is absent or on the wrong side",
                )

    def commit_state(self, staged_state: dict[str, Any]) -> None:
        """Commit a non-throwing plan returned by :meth:`stage_state`."""
        self._last_overpass_time = dict(
            staged_state["last_overpass_time"],
        )
        self._last_reported_at = dict(staged_state["last_reported_at"])
        self._report_queue = deque(staged_state["report_queue"])
        self._next_report_sequence = staged_state["next_report_sequence"]

    def set_state(self, state: dict[str, Any]) -> None:
        """Validate and atomically restore standalone ISR state."""
        self.commit_state(self.stage_state(state))
