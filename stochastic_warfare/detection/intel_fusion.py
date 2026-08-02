"""Multi-source intelligence fusion.

Combines sensor detections, SIGINT, HUMINT, IMINT, and COMINT into a unified
track picture.  Each intel report is converted to a Kalman measurement and
fused via the :class:`StateEstimator`.  Source reliability scales measurement
noise (low reliability = high noise).
"""

from __future__ import annotations

import copy
import enum
import hashlib
import json
import math
import threading
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import Position
from stochastic_warfare.detection.detection import DetectionResult
from stochastic_warfare.detection.estimation import (
    StateEstimator,
    Track,
    TrackStatus,
)
from stochastic_warfare.detection.identification import ContactInfo, ContactLevel

if TYPE_CHECKING:
    from stochastic_warfare.space.isr import SpaceISRReport

logger = get_logger(__name__)

_FOW_TRACK_ID_PREFIX = "fow-track-"
_FOW_TRACK_ID_MIN_WIDTH = 4
_MIN_POSITION_UNCERTAINTY_M = 1.0

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class IntelSource(enum.IntEnum):
    SENSOR = 0
    SIGINT = 1
    HUMINT = 2
    IMINT = 3
    COMINT = 4


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class IntelReport:
    """Single intelligence observation from any source."""

    source: IntelSource
    timestamp: float
    reliability: float  # 0–1
    target_position: Position | None = None
    position_uncertainty_m: float = 1000.0
    target_type: str | None = None
    classification_confidence: float = 0.0
    source_unit_id: str | None = None


class SatellitePass(BaseModel):
    """Satellite overflight window."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    satellite_id: str
    constellation_id: str
    side: str
    start_time: float
    end_time: float
    coverage_center_x: float
    coverage_center_y: float
    coverage_radius_m: float
    resolution_m: float
    revisit_interval_s: float
    source_type: int = 3  # IMINT

    @field_validator(
        "satellite_id",
        "constellation_id",
        "side",
        mode="before",
    )
    @classmethod
    def _identifiers(cls, value: Any, info: Any) -> str:
        return _strict_identifier(value, info.field_name)

    @field_validator(
        "start_time",
        "end_time",
        "coverage_center_x",
        "coverage_center_y",
        "coverage_radius_m",
        "resolution_m",
        "revisit_interval_s",
        mode="before",
    )
    @classmethod
    def _finite_fields(cls, value: Any, info: Any) -> float:
        positive = info.field_name in {
            "coverage_radius_m",
            "resolution_m",
            "revisit_interval_s",
        }
        non_negative = info.field_name in {"start_time", "end_time"}
        return _strict_number(
            value,
            info.field_name,
            positive=positive,
            non_negative=non_negative,
        )

    @field_validator("source_type", mode="before")
    @classmethod
    def _source_type(cls, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value != 3:
            raise ValueError("SatellitePass source_type must be IMINT (3)")
        return value

    @model_validator(mode="after")
    def _time_order(self) -> SatellitePass:
        if self.start_time > self.end_time:
            raise ValueError("SatellitePass start_time must not exceed end_time")
        return self


def _strict_identifier(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be a non-empty trimmed string")
    return value


def _fow_track_ordinal(value: str) -> int | None:
    """Return a canonical side-local FOW track ordinal, if present."""
    suffix = value.removeprefix(_FOW_TRACK_ID_PREFIX)
    if (
        not value.startswith(_FOW_TRACK_ID_PREFIX)
        or not suffix.isascii()
        or not suffix.isdigit()
    ):
        return None
    ordinal = int(suffix)
    if (
        ordinal <= 0
        or suffix != f"{ordinal:0{_FOW_TRACK_ID_MIN_WIDTH}d}"
    ):
        return None
    return ordinal


def _format_fow_track_id(ordinal: int) -> str:
    """Format one target-independent ordinal inside a side-owned namespace."""
    if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal <= 0:
        raise ValueError("FOW track ordinal must be a positive integer")
    return f"{_FOW_TRACK_ID_PREFIX}{ordinal:0{_FOW_TRACK_ID_MIN_WIDTH}d}"


def validate_fow_track_id(value: Any, field_name: str = "FOW track_id") -> str:
    """Return one canonical opaque side-local FOW track identifier."""
    track_id = _strict_identifier(value, field_name)
    if _fow_track_ordinal(track_id) is None:
        raise ValueError(
            f"{field_name} must be a canonical opaque FOW ordinal track ID",
        )
    return track_id


def _strict_number(
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


class IntelDeliveryReceipt(BaseModel):
    """Immutable terminal acknowledgement for one applied imagery report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: int
    reporting_side: str
    target_side: str
    target_id: str
    satellite_id: str
    constellation_id: str
    sensor_type: str
    resolution_m: float
    position_sigma_m: float
    observed_position: Position
    observed_at_s: float
    available_at_s: float
    source: IntelSource
    resulting_track_id: str
    delivery_time_s: float
    report_sha256: str

    @field_validator("report_id", mode="before")
    @classmethod
    def _report_id(cls, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("report_id must be a positive integer")
        return value

    @field_validator(
        "reporting_side",
        "target_side",
        "target_id",
        "satellite_id",
        "constellation_id",
        "resulting_track_id",
        mode="before",
    )
    @classmethod
    def _identifiers(cls, value: Any, info: Any) -> str:
        return _strict_identifier(value, info.field_name)

    @field_validator("sensor_type", mode="before")
    @classmethod
    def _sensor_type(cls, value: Any) -> str:
        if value not in {"optical", "sar"}:
            raise ValueError("sensor_type must be optical or sar")
        return value

    @field_validator("report_sha256", mode="before")
    @classmethod
    def _digest(cls, value: Any) -> str:
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError("report_sha256 must be a lowercase SHA-256")
        return value

    @field_validator("resolution_m", "position_sigma_m", mode="before")
    @classmethod
    def _positive_numbers(cls, value: Any, info: Any) -> float:
        return _strict_number(value, info.field_name, positive=True)

    @field_validator(
        "observed_at_s",
        "available_at_s",
        "delivery_time_s",
        mode="before",
    )
    @classmethod
    def _times(cls, value: Any, info: Any) -> float:
        return _strict_number(value, info.field_name, non_negative=True)

    @field_validator("observed_position", mode="before")
    @classmethod
    def _position(cls, value: Any) -> Position:
        if isinstance(value, Position):
            components = tuple(value)
        elif isinstance(value, (list, tuple)) and len(value) == 3:
            components = tuple(value)
        else:
            raise ValueError(
                "observed_position must contain exactly three ENU numbers",
            )
        return Position(
            *(
                _strict_number(component, f"observed_position[{index}]")
                for index, component in enumerate(components)
            ),
        )

    @field_validator("source", mode="before")
    @classmethod
    def _imint_source(cls, value: Any) -> IntelSource:
        if value in {IntelSource.IMINT, int(IntelSource.IMINT), "IMINT"}:
            return IntelSource.IMINT
        raise ValueError("Space delivery receipt source must be IMINT")

    @model_validator(mode="after")
    def _temporal_contract(self) -> IntelDeliveryReceipt:
        if self.reporting_side == self.target_side:
            raise ValueError("receipt sides must differ")
        if not (
            self.observed_at_s
            <= self.available_at_s
            <= self.delivery_time_s
        ):
            raise ValueError("receipt times are not monotone")
        return self

    def report_state(self) -> dict[str, Any]:
        """Reconstruct the exact originating report representation."""
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
            "target_position": list(self.observed_position),
            "observed_at_s": self.observed_at_s,
            "available_at_s": self.available_at_s,
        }

    def to_state(self) -> dict[str, Any]:
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
            "observed_position": list(self.observed_position),
            "observed_at_s": self.observed_at_s,
            "available_at_s": self.available_at_s,
            "source": self.source.name,
            "resulting_track_id": self.resulting_track_id,
            "delivery_time_s": self.delivery_time_s,
            "report_sha256": self.report_sha256,
        }


class _DeliveryReceiptLedger:
    """Ordered append ledger with an exact report-ID index and mutation epoch."""

    __slots__ = ("_by_report_id", "_ordered", "_revision")

    def __init__(
        self,
        receipts: Sequence[IntelDeliveryReceipt] = (),
        *,
        revision: int = 0,
    ) -> None:
        ordered = list(receipts)
        by_report_id: dict[int, IntelDeliveryReceipt] = {}
        for receipt in ordered:
            if not isinstance(receipt, IntelDeliveryReceipt):
                raise TypeError(
                    "Delivery receipt ledger entries must be "
                    "IntelDeliveryReceipt instances",
                )
            if receipt.report_id in by_report_id:
                raise ValueError(
                    f"Duplicate delivered report ID {receipt.report_id}",
                )
            by_report_id[receipt.report_id] = receipt
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise ValueError("Delivery receipt ledger revision must be non-negative")
        self._ordered = ordered
        self._by_report_id = by_report_id
        self._revision = revision

    @property
    def revision(self) -> int:
        """Monotonic in-runtime mutation epoch used by staged commit guards."""
        return self._revision

    @property
    def count(self) -> int:
        """Exact number of ordered persisted receipts."""
        return len(self._ordered)

    def get(self, report_id: int) -> IntelDeliveryReceipt | None:
        """Return one exact receipt without scanning the ordered ledger."""
        return self._by_report_id.get(report_id)

    def append(self, receipt: IntelDeliveryReceipt) -> None:
        """Append one new receipt and advance the mutation epoch."""
        if not isinstance(receipt, IntelDeliveryReceipt):
            raise TypeError(
                "Delivery receipt ledger entries must be "
                "IntelDeliveryReceipt instances",
            )
        if receipt.report_id in self._by_report_id:
            raise ValueError(
                f"Duplicate delivered report ID {receipt.report_id}",
            )
        self._ordered.append(receipt)
        self._by_report_id[receipt.report_id] = receipt
        self._revision += 1

    def __len__(self) -> int:
        return len(self._ordered)

    def __iter__(self) -> Iterator[IntelDeliveryReceipt]:
        return iter(self._ordered)

    def __getitem__(
        self,
        index: int | slice,
    ) -> IntelDeliveryReceipt | list[IntelDeliveryReceipt]:
        return self._ordered[index]

    def __setitem__(self, index: int, receipt: IntelDeliveryReceipt) -> None:
        """Keep the private index/revision exact under diagnostic mutation."""
        if not isinstance(receipt, IntelDeliveryReceipt):
            raise TypeError(
                "Delivery receipt ledger entries must be "
                "IntelDeliveryReceipt instances",
            )
        prior = self._ordered[index]
        indexed = self._by_report_id.get(receipt.report_id)
        if indexed is not None and indexed is not prior:
            raise ValueError(
                f"Duplicate delivered report ID {receipt.report_id}",
            )
        self._ordered[index] = receipt
        if prior.report_id != receipt.report_id:
            del self._by_report_id[prior.report_id]
        self._by_report_id[receipt.report_id] = receipt
        self._revision += 1


class IMINTTrackAssociation(BaseModel):
    """Persisted one-track-per-owner/target imagery association."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reporting_side: str
    target_side: str
    target_id: str
    track_id: str
    last_observed_at_s: float
    last_received_at_s: float
    last_report_id: int

    @field_validator(
        "reporting_side",
        "target_side",
        "target_id",
        "track_id",
        mode="before",
    )
    @classmethod
    def _identifiers(cls, value: Any, info: Any) -> str:
        return _strict_identifier(value, info.field_name)

    @field_validator(
        "last_observed_at_s",
        "last_received_at_s",
        mode="before",
    )
    @classmethod
    def _times(cls, value: Any, info: Any) -> float:
        return _strict_number(value, info.field_name, non_negative=True)

    @field_validator("last_report_id", mode="before")
    @classmethod
    def _report_id(cls, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("last_report_id must be a positive integer")
        return value

    @model_validator(mode="after")
    def _valid_association(self) -> IMINTTrackAssociation:
        if self.reporting_side == self.target_side:
            raise ValueError("association sides must differ")
        if self.last_received_at_s < self.last_observed_at_s:
            raise ValueError("association receipt may not precede observation")
        return self


@dataclass(frozen=True, slots=True)
class IMINTDeliveryPlan:
    """Opaque, preflighted mutation set for one imagery delivery."""

    receipt: IntelDeliveryReceipt
    _owner: object = field(repr=False, compare=False)
    _expected_track_counter: int = field(repr=False)
    _expected_receipt_revision: int = field(repr=False)
    _expected_receipt_count: int = field(repr=False)
    _expected_rng_state: dict[str, Any] = field(repr=False, compare=False)
    _expected_track: Track | None = field(repr=False, compare=False)
    _expected_track_state: dict[str, Any] | None = field(
        repr=False,
        compare=False,
    )
    _expected_association: IMINTTrackAssociation | None = field(
        repr=False,
        compare=False,
    )
    _expected_association_state: dict[str, Any] | None = field(
        repr=False,
        compare=False,
    )
    _staged_track: Track = field(repr=False, compare=False)
    _staged_association: IMINTTrackAssociation = field(repr=False)
    _staged_track_counter: int = field(repr=False)
    _staged_rng_state: dict[str, Any] = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class IMINTLifecyclePlan:
    """Fully validated non-throwing imagery lifecycle transition batch."""

    transitions: tuple[tuple[Track, TrackStatus], ...]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


def _position_distance(a: Position, b: Position) -> float:
    """Euclidean distance between two positions (2D)."""
    dx = a.easting - b.easting
    dy = a.northing - b.northing
    return math.sqrt(dx * dx + dy * dy)


def _fuse_two_reports(a: IntelReport, b: IntelReport) -> IntelReport:
    """Inverse-variance weighted fusion of two SIGINT reports.

    Fused uncertainty: 1 / sqrt(1/σ_a² + 1/σ_b²)  — always less than
    either individual uncertainty.
    """
    assert a.target_position is not None and b.target_position is not None
    ua = max(a.position_uncertainty_m, _MIN_POSITION_UNCERTAINTY_M)
    ub = max(b.position_uncertainty_m, _MIN_POSITION_UNCERTAINTY_M)
    wa = 1.0 / (ua * ua)
    wb = 1.0 / (ub * ub)
    total_w = wa + wb
    fused_e = (a.target_position.easting * wa + b.target_position.easting * wb) / total_w
    fused_n = (a.target_position.northing * wa + b.target_position.northing * wb) / total_w
    fused_alt = (a.target_position.altitude + b.target_position.altitude) / 2.0
    fused_unc = 1.0 / math.sqrt(total_w)
    return IntelReport(
        source=IntelSource.SIGINT,
        timestamp=max(a.timestamp, b.timestamp),
        reliability=max(a.reliability, b.reliability),
        target_position=Position(fused_e, fused_n, fused_alt),
        position_uncertainty_m=fused_unc,
        target_type=a.target_type or b.target_type,
        classification_confidence=max(
            a.classification_confidence, b.classification_confidence,
        ),
        source_unit_id=a.source_unit_id or b.source_unit_id,
    )


class IntelFusionEngine:
    """Multi-source intelligence fusion engine.

    Parameters
    ----------
    state_estimator:
        A :class:`StateEstimator` for track management.
    rng:
        A ``numpy.random.Generator``.
    """

    def __init__(
        self,
        state_estimator: StateEstimator | None = None,
        *,
        rng: np.random.Generator,
    ) -> None:
        self._estimator = state_estimator or StateEstimator(rng=rng)
        self._rng = rng
        self._tracks: dict[str, dict[str, Track]] = {}  # side → {track_id: Track}
        self._satellite_passes: dict[str, list[SatellitePass]] = {}  # side → passes
        self._track_counter: int = 0
        # FOW IDs are intentionally side-local.  They reveal neither the
        # target ID nor scan inputs, and independent side updates cannot race
        # on a shared public identifier sequence.
        self._fow_track_counters: dict[str, int] = {}
        self._track_lock = threading.RLock()
        self._delivery_receipts = _DeliveryReceiptLedger()
        self._imint_target_tracks: dict[
            str,
            dict[str, IMINTTrackAssociation],
        ] = {}

    # ------------------------------------------------------------------
    # Track access
    # ------------------------------------------------------------------

    def _get_side_tracks(self, side: str) -> dict[str, Track]:
        if side not in self._tracks:
            self._tracks[side] = {}
        return self._tracks[side]

    def get_tracks(self, side: str) -> dict[str, Track]:
        """Return all tracks for a side."""
        return dict(self._get_side_tracks(side))

    def get_actionable_tracks(self, side: str) -> dict[str, Track]:
        """Return tracks eligible for ordinary operational consumption."""
        return {
            track_id: track
            for track_id, track in self._get_side_tracks(side).items()
            if track.status is not TrackStatus.STALE
        }

    @property
    def delivery_receipts(self) -> tuple[IntelDeliveryReceipt, ...]:
        """Immutable ordered Space imagery delivery evidence."""
        return tuple(self._delivery_receipts)

    @property
    def imint_target_tracks(
        self,
    ) -> dict[str, dict[str, IMINTTrackAssociation]]:
        """Return a copy of the persisted owner/target associations."""
        return {
            side: dict(associations)
            for side, associations in self._imint_target_tracks.items()
        }

    # ------------------------------------------------------------------
    # Intel report submission
    # ------------------------------------------------------------------

    def submit_report(
        self,
        side: str,
        report: IntelReport,
        contact_id: str | None = None,
        *,
        allocate_fow_track: bool = False,
    ) -> str | None:
        """Convert an intel report to a Kalman measurement and update/create track.

        Returns the track ID of the updated or created track, or None if
        the report has no position information.
        """
        with self._track_lock:
            return self._submit_report_locked(
                side,
                report,
                contact_id,
                allocate_fow_track=allocate_fow_track,
            )

    def _submit_report_locked(
        self,
        side: str,
        report: IntelReport,
        contact_id: str | None,
        *,
        allocate_fow_track: bool,
    ) -> str | None:
        """Submit one report while holding the fusion track lock."""
        if type(allocate_fow_track) is not bool:
            raise TypeError("allocate_fow_track must be a boolean")
        if report.target_position is None:
            return None

        tracks = self._get_side_tracks(side)

        # Scale noise by reliability: low reliability = high noise.  A
        # strictly positive measurement covariance is a fusion invariant;
        # zero variance would claim perfect knowledge and makes a repeated
        # exact observation's innovation covariance singular.
        reliability = _strict_number(
            report.reliability,
            "intel report reliability",
            non_negative=True,
        )
        if reliability > 1.0:
            raise ValueError("intel report reliability must not exceed 1.0")
        position_uncertainty_m = _strict_number(
            report.position_uncertainty_m,
            "intel report position uncertainty",
            positive=True,
        )
        reliability = max(reliability, 0.01)
        noise_scale = 1.0 / reliability
        unc = position_uncertainty_m * noise_scale
        R = np.diag([unc * unc, unc * unc])
        meas = np.array([
            report.target_position.easting,
            report.target_position.northing,
        ])

        # Contact info from report
        level = ContactLevel.DETECTED
        if report.classification_confidence > 0.7:
            level = ContactLevel.CLASSIFIED
        if report.classification_confidence > 0.9:
            level = ContactLevel.IDENTIFIED
        ci = ContactInfo(
            level=level,
            domain_estimate=None,
            type_estimate=report.target_type,
            specific_estimate=report.target_type if level == ContactLevel.IDENTIFIED else None,
            confidence=report.classification_confidence,
        )

        # Try to associate with existing track.  A rejected FOW association
        # is replaced under this same lock; retain its identity until the
        # replacement has been constructed and installed successfully.
        replaced_fow_track_id: str | None = None
        if contact_id and contact_id in tracks:
            track = tracks[contact_id]
            accepted = self._estimator.update(
                track,
                meas,
                R,
                report.timestamp,
            )
            if accepted or not allocate_fow_track:
                return contact_id
            replaced_fow_track_id = contact_id
            # A gated FOW measurement is a distinct observation rather than
            # permission to leave a current contact bound to a stale estimate.
            # The one-hit predecessor cannot enter the ordinary confirmed ->
            # coasting -> lost lifecycle, so the replacement transaction owns
            # its removal instead of retaining unreachable fusion state.

        # Create a new track.  FOW uses an independent ordinal namespace for
        # each reporting side, so parallel side scheduling cannot reassign
        # public identifiers and the identifier contains no target material.
        if allocate_fow_track:
            next_fow_ordinal = self._fow_track_counters.get(side, 0) + 1
            tid = _format_fow_track_id(next_fow_ordinal)
            if tid in tracks:
                raise ValueError(
                    f"Fusion FOW track ID {tid!r} is already issued for {side!r}",
                )
            next_track_counter = self._track_counter
        else:
            next_track_counter = self._track_counter + 1
            next_fow_ordinal = None
            tid = f"track-{next_track_counter:04d}"
        track = self._estimator.create_track(
            tid, side, meas, R, ci, report.timestamp,
        )
        tracks[tid] = track
        self._track_counter = next_track_counter
        if next_fow_ordinal is not None:
            self._fow_track_counters[side] = next_fow_ordinal
        if replaced_fow_track_id is not None:
            del tracks[replaced_fow_track_id]
        return tid

    def _imint_status(
        self,
        *,
        hits: int,
        age_s: float,
    ) -> TrackStatus:
        config = self._estimator.config
        if age_s <= config.coast_timeout_s:
            if hits >= config.confirmation_threshold:
                return TrackStatus.CONFIRMED
            return TrackStatus.TENTATIVE
        if age_s <= config.lost_timeout_s:
            return TrackStatus.COASTING
        return TrackStatus.STALE

    def prepare_imint_report(
        self,
        report: SpaceISRReport,
        *,
        delivery_time_s: float,
    ) -> IMINTDeliveryPlan:
        """Stage one typed Space report without mutating live fusion state."""
        from stochastic_warfare.space.isr import SpaceISRReport

        if not isinstance(report, SpaceISRReport):
            raise TypeError("prepare_imint_report requires SpaceISRReport")
        delivery_time = _strict_number(
            delivery_time_s,
            "delivery_time_s",
            non_negative=True,
        )
        if delivery_time < report.available_at_s:
            raise ValueError("Space imagery report is not yet available")
        if self._delivery_receipts.get(report.report_id) is not None:
            raise ValueError(
                f"Space imagery report {report.report_id} is already delivered",
            )

        owner_associations = self._imint_target_tracks.get(
            report.reporting_side,
            {},
        )
        association = owner_associations.get(report.target_id)
        if association is not None:
            if report.observed_at_s < association.last_observed_at_s:
                raise ValueError(
                    "Space imagery observation predates its associated track",
                )
            if report.observed_at_s == association.last_observed_at_s:
                prior_receipt = self._delivery_receipts.get(
                    association.last_report_id,
                )
                if prior_receipt is None:
                    raise ValueError(
                        "IMINT association references a missing receipt",
                    )
                if (
                    report.constellation_id,
                    report.satellite_id,
                    report.report_id,
                ) <= (
                    prior_receipt.constellation_id,
                    prior_receipt.satellite_id,
                    prior_receipt.report_id,
                ):
                    raise ValueError(
                        "Same-epoch Space imagery is not in canonical order",
                    )

        rng_before = copy.deepcopy(self._rng.bit_generator.state)
        staged_rng = copy.deepcopy(self._rng)
        staged_estimator = StateEstimator(
            rng=staged_rng,
            config=self._estimator.config.model_copy(deep=True),
        )
        measurement = np.array(
            [
                report.target_position.easting,
                report.target_position.northing,
            ],
            dtype=np.float64,
        )
        variance = report.position_sigma_m**2
        measurement_noise = np.diag([variance, variance])
        expected_track: Track | None = None
        staged_counter = self._track_counter
        if association is None:
            staged_counter += 1
            track_id = f"track-{staged_counter:04d}"
            if any(
                track_id in side_tracks
                for side_tracks in self._tracks.values()
            ):
                raise ValueError(
                    "IMINT track counter would reuse an existing track ID",
                )
            contact_info = ContactInfo(
                level=ContactLevel.DETECTED,
                domain_estimate=None,
                type_estimate=None,
                specific_estimate=None,
                confidence=0.0,
            )
            staged_track = staged_estimator.create_track(
                track_id,
                report.reporting_side,
                measurement,
                measurement_noise,
                contact_info,
                report.observed_at_s,
            )
        else:
            track_id = association.track_id
            expected_track = self._tracks.get(
                report.reporting_side,
                {},
            ).get(track_id)
            if expected_track is None:
                raise ValueError(
                    "IMINT association references a missing track",
                )
            staged_track = copy.deepcopy(expected_track)
            prediction_dt = (
                report.observed_at_s
                - staged_track.state.last_update_time
            )
            if prediction_dt < 0.0:
                raise ValueError(
                    "Space imagery observation predates track state",
                )
            if prediction_dt > 0.0:
                staged_estimator.predict(staged_track, prediction_dt)
            if not staged_estimator.update(
                staged_track,
                measurement,
                measurement_noise,
                report.observed_at_s,
            ):
                raise ValueError(
                    "Space imagery measurement failed estimator gating",
                )

        staged_track.status = self._imint_status(
            hits=staged_track.hits,
            age_s=delivery_time - report.observed_at_s,
        )
        receipt = IntelDeliveryReceipt(
            report_id=report.report_id,
            reporting_side=report.reporting_side,
            target_side=report.target_side,
            target_id=report.target_id,
            satellite_id=report.satellite_id,
            constellation_id=report.constellation_id,
            sensor_type=report.sensor_type,
            resolution_m=report.resolution_m,
            position_sigma_m=report.position_sigma_m,
            observed_position=report.target_position,
            observed_at_s=report.observed_at_s,
            available_at_s=report.available_at_s,
            source=IntelSource.IMINT,
            resulting_track_id=track_id,
            delivery_time_s=delivery_time,
            report_sha256=report.digest(),
        )
        staged_association = IMINTTrackAssociation(
            reporting_side=report.reporting_side,
            target_side=report.target_side,
            target_id=report.target_id,
            track_id=track_id,
            last_observed_at_s=report.observed_at_s,
            last_received_at_s=delivery_time,
            last_report_id=report.report_id,
        )
        return IMINTDeliveryPlan(
            receipt=receipt,
            _owner=self,
            _expected_track_counter=self._track_counter,
            _expected_receipt_revision=self._delivery_receipts.revision,
            _expected_receipt_count=self._delivery_receipts.count,
            _expected_rng_state=rng_before,
            _expected_track=expected_track,
            _expected_track_state=(
                copy.deepcopy(expected_track.get_state())
                if expected_track is not None
                else None
            ),
            _expected_association=association,
            _expected_association_state=(
                association.model_dump(mode="json")
                if association is not None
                else None
            ),
            _staged_track=staged_track,
            _staged_association=staged_association,
            _staged_track_counter=staged_counter,
            _staged_rng_state=copy.deepcopy(
                staged_rng.bit_generator.state,
            ),
        )

    def commit_imint_report(
        self,
        plan: IMINTDeliveryPlan,
    ) -> IntelDeliveryReceipt:
        """Commit one current, owner-issued delivery plan without re-estimation."""
        if not isinstance(plan, IMINTDeliveryPlan) or plan._owner is not self:
            raise TypeError(
                "commit_imint_report requires a plan from this engine",
            )
        receipt = plan.receipt
        current_association = self._imint_target_tracks.get(
            receipt.reporting_side,
            {},
        ).get(receipt.target_id)
        current_track = self._tracks.get(
            receipt.reporting_side,
            {},
        ).get(receipt.resulting_track_id)
        if (
            self._track_counter != plan._expected_track_counter
            or self._delivery_receipts.revision
            != plan._expected_receipt_revision
            or self._delivery_receipts.count
            != plan._expected_receipt_count
            or current_association is not plan._expected_association
            or current_track is not plan._expected_track
            or (
                current_association.model_dump(mode="json")
                if current_association is not None
                else None
            )
            != plan._expected_association_state
            or (
                current_track.get_state()
                if current_track is not None
                else None
            )
            != plan._expected_track_state
            or self._rng.bit_generator.state
            != plan._expected_rng_state
            or self._delivery_receipts.get(receipt.report_id) is not None
        ):
            raise RuntimeError(
                "IMINT delivery plan is stale against live fusion state",
            )

        self._rng.bit_generator.state = plan._staged_rng_state
        self._track_counter = plan._staged_track_counter
        self._tracks.setdefault(receipt.reporting_side, {})[
            receipt.resulting_track_id
        ] = plan._staged_track
        self._delivery_receipts.append(receipt)
        self._imint_target_tracks.setdefault(
            receipt.reporting_side,
            {},
        )[receipt.target_id] = plan._staged_association
        return receipt

    def submit_imint_report(
        self,
        report: SpaceISRReport,
        *,
        delivery_time_s: float,
    ) -> IntelDeliveryReceipt:
        """Prepare and commit one typed owner-scoped imagery transaction."""
        plan = self.prepare_imint_report(
            report,
            delivery_time_s=delivery_time_s,
        )
        return self.commit_imint_report(plan)

    def prepare_imint_lifecycle(
        self,
        current_time_s: float,
    ) -> IMINTLifecyclePlan:
        """Validate and stage every imagery track's age-derived status."""
        current_time = _strict_number(
            current_time_s,
            "current_time_s",
            non_negative=True,
        )
        transitions: list[tuple[Track, TrackStatus]] = []
        associated_track_ids: set[str] = set()
        for side in sorted(self._imint_target_tracks):
            for target_id in sorted(self._imint_target_tracks[side]):
                association = self._imint_target_tracks[side][target_id]
                if (
                    association.reporting_side != side
                    or association.target_id != target_id
                ):
                    raise ValueError(
                        "IMINT lifecycle association key disagrees with "
                        "its identity",
                    )
                if association.track_id in associated_track_ids:
                    raise ValueError(
                        "IMINT lifecycle associations share one track",
                    )
                associated_track_ids.add(association.track_id)
                if current_time < association.last_observed_at_s:
                    raise ValueError(
                        "IMINT lifecycle time predates an observation",
                    )
                track = self._tracks.get(side, {}).get(
                    association.track_id,
                )
                if track is None:
                    raise ValueError(
                        "IMINT lifecycle association has no track",
                    )
                if track.side != side:
                    raise ValueError(
                        "IMINT lifecycle track has the wrong owner",
                    )
                transitions.append((
                    track,
                    self._imint_status(
                        hits=track.hits,
                        age_s=current_time - association.last_observed_at_s,
                    ),
                ))
        return IMINTLifecyclePlan(transitions=tuple(transitions))

    @staticmethod
    def commit_imint_lifecycle(plan: IMINTLifecyclePlan) -> None:
        """Commit a plan returned by :meth:`prepare_imint_lifecycle`."""
        if not isinstance(plan, IMINTLifecyclePlan):
            raise TypeError("plan must be an IMINTLifecyclePlan")
        for track, status in plan.transitions:
            track.status = status

    def manage_imint_lifecycle(self, current_time_s: float) -> None:
        """Atomically recompute persisted imagery tracks' derived status."""
        self.commit_imint_lifecycle(
            self.prepare_imint_lifecycle(current_time_s),
        )

    # ------------------------------------------------------------------
    # Sensor detection submission
    # ------------------------------------------------------------------

    def submit_sensor_detection(
        self,
        side: str,
        detection: DetectionResult,
        contact_info: ContactInfo,
        observer_pos: Position,
        contact_id: str | None = None,
        *,
        allocate_fow_track: bool = False,
        observation_time_s: float = 0.0,
    ) -> str | None:
        """Create an IntelReport from a sensor detection and submit it."""
        if not detection.detected:
            return None

        # Estimate target position from observer + bearing + range
        bearing_rad = math.radians(detection.bearing_deg)
        tgt_e = observer_pos.easting + detection.range_m * math.sin(bearing_rad)
        tgt_n = observer_pos.northing + detection.range_m * math.cos(bearing_rad)

        report = IntelReport(
            source=IntelSource.SENSOR,
            timestamp=_strict_number(
                observation_time_s,
                "observation_time_s",
                non_negative=True,
            ),
            reliability=min(1.0, detection.probability),
            target_position=Position(tgt_e, tgt_n, 0.0),
            position_uncertainty_m=max(
                detection.range_m * 0.05,
                _MIN_POSITION_UNCERTAINTY_M,
            ),
            target_type=None,
            classification_confidence=contact_info.confidence,
            source_unit_id=None,
        )
        return self.submit_report(
            side,
            report,
            contact_id,
            allocate_fow_track=allocate_fow_track,
        )

    # ------------------------------------------------------------------
    # Satellite coverage
    # ------------------------------------------------------------------

    def add_satellite_pass(self, side: str, sat_pass: SatellitePass) -> None:
        """Register a satellite pass for a side."""
        _strict_identifier(side, "satellite pass side")
        if not isinstance(sat_pass, SatellitePass):
            raise TypeError("sat_pass must be a SatellitePass")
        if sat_pass.side != side:
            raise ValueError("SatellitePass side disagrees with owner map")
        passes = self._satellite_passes.setdefault(side, [])
        if sat_pass in passes:
            return
        passes.append(sat_pass)
        passes.sort(
            key=lambda item: (
                item.start_time,
                item.constellation_id,
                item.satellite_id,
                item.end_time,
                item.coverage_center_x,
                item.coverage_center_y,
                item.coverage_radius_m,
                item.resolution_m,
                item.revisit_interval_s,
            ),
        )

    def check_satellite_coverage(
        self,
        side: str,
        target_x: float,
        target_y: float,
        time: float,
    ) -> bool:
        """Return True if any satellite pass covers this position at this time."""
        passes = self._satellite_passes.get(side, [])
        for sp in passes:
            if sp.start_time <= time <= sp.end_time:
                dx = target_x - sp.coverage_center_x
                dy = target_y - sp.coverage_center_y
                dist = math.sqrt(dx * dx + dy * dy)
                if dist <= sp.coverage_radius_m:
                    return True
        return False

    # ------------------------------------------------------------------
    # SIGINT report generation
    # ------------------------------------------------------------------

    def generate_sigint_report(
        self,
        emitter_pos: Position,
        emitter_power_dbm: float,
        time: float,
    ) -> IntelReport:
        """Generate a SIGINT report from an intercepted emission.

        Direction-finding accuracy depends on emitter power.
        """
        # Higher power = better direction finding, lower uncertainty
        uncertainty = max(500.0, 5000.0 - emitter_power_dbm * 50.0)
        # Add noise to position
        noisy_pos = Position(
            emitter_pos.easting + float(self._rng.normal(0, uncertainty)),
            emitter_pos.northing + float(self._rng.normal(0, uncertainty)),
            emitter_pos.altitude,
        )
        return IntelReport(
            source=IntelSource.SIGINT,
            timestamp=time,
            reliability=0.7,
            target_position=noisy_pos,
            position_uncertainty_m=uncertainty,
        )

    # ------------------------------------------------------------------
    # Phase 52d: Space + EW SIGINT fusion
    # ------------------------------------------------------------------

    def fuse_sigint_tracks(
        self,
        side: str,
        space_reports: list[IntelReport],
        ew_reports: list[IntelReport],
        association_radius_mult: float = 2.0,
    ) -> list[str]:
        """Fuse space-based and EW SIGINT reports into unified tracks.

        Association criterion: two detections are candidates when their
        distance < max(unc_a, unc_b) * *association_radius_mult*.
        Fused position uses inverse-variance weighted average, giving
        better accuracy than either individual source.

        Returns list of track IDs created or updated.
        """
        fused_ids: list[str] = []
        used_ew: set[int] = set()

        for sp in space_reports:
            if sp.target_position is None:
                continue
            best_ew: tuple[int, IntelReport] | None = None
            best_dist = float("inf")
            for i, ew in enumerate(ew_reports):
                if i in used_ew or ew.target_position is None:
                    continue
                dist = _position_distance(
                    sp.target_position, ew.target_position,
                )
                threshold = (
                    max(sp.position_uncertainty_m, ew.position_uncertainty_m)
                    * association_radius_mult
                )
                if dist < threshold and dist < best_dist:
                    best_ew = (i, ew)
                    best_dist = dist
            if best_ew is not None:
                idx, ew = best_ew
                used_ew.add(idx)
                fused_report = _fuse_two_reports(sp, ew)
                tid = self.submit_report(side, fused_report)
                if tid:
                    fused_ids.append(tid)
            else:
                tid = self.submit_report(side, sp)
                if tid:
                    fused_ids.append(tid)

        # Submit unmatched EW reports
        for i, ew in enumerate(ew_reports):
            if i not in used_ew:
                tid = self.submit_report(side, ew)
                if tid:
                    fused_ids.append(tid)

        return fused_ids

    # ------------------------------------------------------------------
    # Multi-source fusion
    # ------------------------------------------------------------------

    def fuse_reports(
        self,
        side: str,
        reports: list[IntelReport],
    ) -> list[str]:
        """Fuse multiple reports into the track picture for *side*.

        Returns list of track IDs that were updated or created.
        """
        track_ids: list[str] = []
        for report in reports:
            tid = self.submit_report(side, report)
            if tid is not None:
                track_ids.append(tid)
        return track_ids

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        tracks_state: dict[str, dict[str, Any]] = {}
        for side, side_tracks in sorted(self._tracks.items()):
            tracks_state[side] = {
                tid: track.get_state() for tid, track in sorted(side_tracks.items())
            }
        return {
            "tracks": tracks_state,
            "track_counter": self._track_counter,
            "fow_track_counters": {
                side: counter
                for side, counter in sorted(self._fow_track_counters.items())
            },
            "rng_state": copy.deepcopy(self._rng.bit_generator.state),
            "satellite_passes": {
                side: [
                    satellite_pass.model_dump(mode="json")
                    for satellite_pass in passes
                ]
                for side, passes in sorted(self._satellite_passes.items())
            },
            "delivery_receipts": [
                receipt.to_state()
                for receipt in self._delivery_receipts
            ],
            "imint_target_tracks": [
                association.model_dump(mode="json")
                for side in sorted(self._imint_target_tracks)
                for _, association in sorted(
                    self._imint_target_tracks[side].items(),
                )
            ],
        }

    @staticmethod
    def _stage_track(
        raw: Any,
        *,
        map_side: str,
        map_track_id: str,
        checkpoint_elapsed_s: float | None,
    ) -> Track:
        if not isinstance(raw, dict):
            raise ValueError("Fusion track state must be a mapping")
        expected = {
            "track_id",
            "side",
            "contact_info",
            "state",
            "status",
            "hits",
            "misses",
        }
        if set(raw) != expected:
            raise ValueError(
                f"Fusion track keys must be exactly {sorted(expected)!r}",
            )
        track_id = _strict_identifier(raw["track_id"], "track_id")
        side = _strict_identifier(raw["side"], "track side")
        if track_id != map_track_id or side != map_side:
            raise ValueError("Fusion map key disagrees with track identity")
        contact = raw["contact_info"]
        contact_keys = {
            "level",
            "domain_estimate",
            "type_estimate",
            "specific_estimate",
            "confidence",
        }
        if not isinstance(contact, dict) or set(contact) != contact_keys:
            raise ValueError("Fusion contact_info has invalid keys")
        level = contact["level"]
        if isinstance(level, bool) or not isinstance(level, int):
            raise ValueError("Fusion contact level must be an integer enum")
        try:
            ContactLevel(level)
        except ValueError as exc:
            raise ValueError("Fusion contact level is unknown") from exc
        confidence = _strict_number(
            contact["confidence"],
            "Fusion contact confidence",
        )
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("Fusion contact confidence must be in [0, 1]")
        for field_name in (
            "domain_estimate",
            "type_estimate",
            "specific_estimate",
        ):
            if contact[field_name] is not None and not isinstance(
                contact[field_name],
                str,
            ):
                raise ValueError(
                    f"Fusion contact {field_name} must be string or null",
                )

        track_state = raw["state"]
        state_keys = {
            "position",
            "velocity",
            "covariance",
            "last_update_time",
        }
        if not isinstance(track_state, dict) or set(track_state) != state_keys:
            raise ValueError("Fusion estimator state has invalid keys")
        position = track_state["position"]
        velocity = track_state["velocity"]
        covariance = track_state["covariance"]
        if not isinstance(position, list) or len(position) != 2:
            raise ValueError("Fusion track position must have length two")
        if not isinstance(velocity, list) or len(velocity) != 2:
            raise ValueError("Fusion track velocity must have length two")
        if (
            not isinstance(covariance, list)
            or len(covariance) != 4
            or any(
                not isinstance(row, list) or len(row) != 4
                for row in covariance
            )
        ):
            raise ValueError("Fusion track covariance must be 4-by-4")
        normalized_position = [
            _strict_number(value, f"track position[{index}]")
            for index, value in enumerate(position)
        ]
        normalized_velocity = [
            _strict_number(value, f"track velocity[{index}]")
            for index, value in enumerate(velocity)
        ]
        normalized_covariance = [
            [
                _strict_number(
                    value,
                    f"track covariance[{row_index}][{column_index}]",
                )
                for column_index, value in enumerate(row)
            ]
            for row_index, row in enumerate(covariance)
        ]
        last_update = _strict_number(
            track_state["last_update_time"],
            "track last_update_time",
            non_negative=True,
        )
        if (
            checkpoint_elapsed_s is not None
            and last_update > checkpoint_elapsed_s
        ):
            raise ValueError("Fusion track update is after checkpoint time")
        status = raw["status"]
        if isinstance(status, bool) or not isinstance(status, int):
            raise ValueError("Fusion track status must be an integer enum")
        try:
            TrackStatus(status)
        except ValueError as exc:
            raise ValueError("Fusion track status is unknown") from exc
        hits = raw["hits"]
        misses = raw["misses"]
        if (
            isinstance(hits, bool)
            or not isinstance(hits, int)
            or hits <= 0
            or isinstance(misses, bool)
            or not isinstance(misses, int)
            or misses < 0
        ):
            raise ValueError(
                "Fusion track hits/misses must be valid integers",
            )
        normalized = copy.deepcopy(raw)
        normalized["contact_info"]["confidence"] = confidence
        normalized["state"] = {
            "position": normalized_position,
            "velocity": normalized_velocity,
            "covariance": normalized_covariance,
            "last_update_time": last_update,
        }
        track = Track.__new__(Track)
        track.set_state(normalized)
        return track

    def stage_state(
        self,
        state: dict[str, Any],
        *,
        expected_sides: set[str] | None = None,
        expected_target_sides: dict[str, str] | None = None,
        satellite_topology: dict[str, tuple[str, str]] | None = None,
        checkpoint_elapsed_s: float | None = None,
        authoritative_rng_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Validate complete fusion state without mutating the engine."""
        if not isinstance(state, dict):
            raise ValueError("Intel fusion state must be a mapping")
        expected_keys = {
            "tracks",
            "track_counter",
            "fow_track_counters",
            "rng_state",
            "satellite_passes",
            "delivery_receipts",
            "imint_target_tracks",
        }
        if set(state) != expected_keys:
            raise ValueError(
                "Intel fusion state keys must be exactly "
                f"{sorted(expected_keys)!r}",
            )
        elapsed = (
            None
            if checkpoint_elapsed_s is None
            else _strict_number(
                checkpoint_elapsed_s,
                "checkpoint_elapsed_s",
                non_negative=True,
            )
        )
        raw_counter = state["track_counter"]
        if (
            isinstance(raw_counter, bool)
            or not isinstance(raw_counter, int)
            or raw_counter < 0
        ):
            raise ValueError(
                "Intel fusion track_counter must be non-negative integer",
            )
        raw_fow_counters = state["fow_track_counters"]
        if not isinstance(raw_fow_counters, dict):
            raise ValueError("Intel fusion fow_track_counters must be a mapping")
        fow_track_counters: dict[str, int] = {}
        for raw_side, raw_fow_counter in raw_fow_counters.items():
            side = _strict_identifier(raw_side, "FOW track-counter side")
            if expected_sides is not None and side not in expected_sides:
                raise ValueError(f"Unknown FOW track-counter side {side!r}")
            if (
                isinstance(raw_fow_counter, bool)
                or not isinstance(raw_fow_counter, int)
                or raw_fow_counter <= 0
            ):
                raise ValueError(
                    "Intel fusion FOW track counter must be a positive integer",
                )
            fow_track_counters[side] = raw_fow_counter
        raw_tracks = state["tracks"]
        if not isinstance(raw_tracks, dict):
            raise ValueError("Intel fusion tracks must be a mapping")
        tracks: dict[str, dict[str, Track]] = {}
        automatic_track_ids: set[str] = set()
        fow_ordinals_by_side: dict[str, set[int]] = {}
        for side, side_tracks in raw_tracks.items():
            side = _strict_identifier(side, "fusion side")
            if expected_sides is not None and side not in expected_sides:
                raise ValueError(f"Unknown fusion side {side!r}")
            if not isinstance(side_tracks, dict):
                raise ValueError("Fusion side tracks must be a mapping")
            tracks[side] = {}
            fow_ordinals_by_side[side] = set()
            for track_id, raw_track in side_tracks.items():
                _strict_identifier(track_id, "fusion track map key")
                track = self._stage_track(
                    raw_track,
                    map_side=side,
                    map_track_id=track_id,
                    checkpoint_elapsed_s=elapsed,
                )
                tracks[side][track_id] = track
                if track_id.startswith("track-") and track_id[6:].isdigit():
                    if track_id in automatic_track_ids:
                        raise ValueError(
                            f"Duplicate fusion track ID {track_id!r}",
                        )
                    automatic_track_ids.add(track_id)
                    continue
                fow_ordinal = _fow_track_ordinal(track_id)
                if fow_ordinal is None:
                    raise ValueError("Intel fusion contains an unsupported track ID")
                fow_ordinals_by_side[side].add(fow_ordinal)
        expected_track_ids = {
            f"track-{sequence:04d}"
            for sequence in range(1, raw_counter + 1)
        }
        if automatic_track_ids != expected_track_ids:
            raise ValueError(
                "Intel fusion track_counter disagrees with issued track IDs",
            )
        if not set(fow_track_counters) <= set(tracks):
            raise ValueError(
                "Intel fusion FOW track counter has no side track namespace",
            )
        for side, ordinals in fow_ordinals_by_side.items():
            if not ordinals:
                if side in fow_track_counters:
                    raise ValueError(
                        "Intel fusion FOW track counter has no issued tracks",
                    )
                continue
            counter = fow_track_counters.get(side)
            if counter is None:
                raise ValueError(
                    f"Intel fusion FOW track counter is missing for side {side!r}",
                )
            if max(ordinals) > counter:
                raise ValueError(
                    "Intel fusion FOW track counter precedes an issued track",
                )
            if max(ordinals) < counter:
                raise ValueError(
                    "Intel fusion FOW track counter disagrees with issued tracks",
                )

        rng_state = copy.deepcopy(state["rng_state"])
        if not isinstance(rng_state, dict):
            raise ValueError("Intel fusion rng_state must be a mapping")
        try:
            staged_rng = copy.deepcopy(self._rng)
            staged_rng.bit_generator.state = rng_state
        except (TypeError, ValueError) as exc:
            raise ValueError("Intel fusion rng_state is invalid") from exc
        if (
            authoritative_rng_state is not None
            and rng_state != authoritative_rng_state
        ):
            raise ValueError(
                "Intel fusion RNG mirror disagrees with RNGManager DETECTION "
                "state",
            )

        raw_passes = state["satellite_passes"]
        if not isinstance(raw_passes, dict):
            raise ValueError("satellite_passes must be a side mapping")
        satellite_passes: dict[str, list[SatellitePass]] = {}
        for side, values in raw_passes.items():
            side = _strict_identifier(side, "satellite pass side")
            if expected_sides is not None and side not in expected_sides:
                raise ValueError(f"Unknown satellite-pass side {side!r}")
            if not isinstance(values, list):
                raise ValueError("satellite pass entries must be a list")
            passes: list[SatellitePass] = []
            for index, value in enumerate(values):
                try:
                    satellite_pass = SatellitePass.model_validate(value)
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"Invalid satellite pass {side}[{index}]: {exc}",
                    ) from exc
                if (
                    elapsed is not None
                    and satellite_pass.start_time > elapsed
                ):
                    raise ValueError(
                        "Satellite pass starts after checkpoint time",
                    )
                if satellite_pass.side != side:
                    raise ValueError(
                        "Satellite pass side disagrees with owner map",
                    )
                if satellite_topology is not None and (
                    satellite_topology.get(satellite_pass.satellite_id)
                    != (
                        satellite_pass.side,
                        satellite_pass.constellation_id,
                    )
                ):
                    raise ValueError(
                        "Satellite pass references unknown or mismatched "
                        "Space topology",
                    )
                passes.append(satellite_pass)
            order = lambda item: (
                item.start_time,
                item.constellation_id,
                item.satellite_id,
                item.end_time,
                item.coverage_center_x,
                item.coverage_center_y,
                item.coverage_radius_m,
                item.resolution_m,
                item.revisit_interval_s,
            )
            if passes != sorted(passes, key=order):
                raise ValueError("Satellite passes are not canonically ordered")
            satellite_passes[side] = passes

        raw_receipts = state["delivery_receipts"]
        if not isinstance(raw_receipts, list):
            raise ValueError("delivery_receipts must be a list")
        receipts: list[IntelDeliveryReceipt] = []
        report_ids: set[int] = set()
        from stochastic_warfare.space.isr import SpaceISRReport

        for index, raw_receipt in enumerate(raw_receipts):
            try:
                receipt = IntelDeliveryReceipt.model_validate(raw_receipt)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid delivery_receipts[{index}]: {exc}",
                ) from exc
            if receipt.report_id in report_ids:
                raise ValueError(
                    f"Duplicate delivered report ID {receipt.report_id}",
                )
            if elapsed is not None and receipt.delivery_time_s > elapsed:
                raise ValueError("Receipt delivery is after checkpoint time")
            if expected_sides is not None and (
                receipt.reporting_side not in expected_sides
                or receipt.target_side not in expected_sides
            ):
                raise ValueError("Receipt references an unknown scenario side")
            if expected_target_sides is not None and (
                expected_target_sides.get(receipt.target_id)
                != receipt.target_side
            ):
                raise ValueError(
                    "Receipt target is absent or on the wrong side",
                )
            report = SpaceISRReport.model_validate(receipt.report_state())
            if report.digest() != receipt.report_sha256:
                raise ValueError("Receipt report digest does not recompute")
            report_ids.add(receipt.report_id)
            receipts.append(receipt)
        receipt_order = lambda item: (
            item.delivery_time_s,
            item.observed_at_s,
            item.reporting_side,
            item.constellation_id,
            item.satellite_id,
            item.target_id,
            item.report_id,
        )
        if receipts != sorted(receipts, key=receipt_order):
            raise ValueError("Delivery receipts are not canonically ordered")

        raw_associations = state["imint_target_tracks"]
        if not isinstance(raw_associations, list):
            raise ValueError("imint_target_tracks must be a list")
        associations: dict[str, dict[str, IMINTTrackAssociation]] = {}
        for index, raw_association in enumerate(raw_associations):
            try:
                association = IMINTTrackAssociation.model_validate(
                    raw_association,
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid imint_target_tracks[{index}]: {exc}",
                ) from exc
            if expected_sides is not None and (
                association.reporting_side not in expected_sides
                or association.target_side not in expected_sides
            ):
                raise ValueError(
                    "IMINT association references an unknown scenario side",
                )
            side_associations = associations.setdefault(
                association.reporting_side,
                {},
            )
            if association.target_id in side_associations:
                raise ValueError("Duplicate IMINT owner/target association")
            side_associations[association.target_id] = association
        flattened = [
            association
            for side in sorted(associations)
            for _, association in sorted(associations[side].items())
        ]
        if len(flattened) != len(raw_associations):
            raise ValueError("Duplicate IMINT association")
        if [
            association.model_dump(mode="json")
            for association in flattened
        ] != raw_associations:
            raise ValueError("IMINT associations are not canonically ordered")
        associated_track_ids: set[str] = set()
        for association in flattened:
            if association.track_id in associated_track_ids:
                raise ValueError(
                    "Multiple IMINT associations reference the same track",
                )
            associated_track_ids.add(association.track_id)

        receipts_by_owner_target: dict[
            tuple[str, str],
            list[IntelDeliveryReceipt],
        ] = {}
        for receipt in receipts:
            receipts_by_owner_target.setdefault(
                (receipt.reporting_side, receipt.target_id),
                [],
            ).append(receipt)
        for side, side_associations in associations.items():
            for target_id, association in side_associations.items():
                track = tracks.get(side, {}).get(association.track_id)
                if track is None:
                    raise ValueError(
                        "IMINT association references a missing owner track",
                    )
                matching = receipts_by_owner_target.get(
                    (side, target_id),
                    [],
                )
                if not matching:
                    raise ValueError(
                        "IMINT association has no delivery receipt",
                    )
                latest = max(
                    matching,
                    key=lambda receipt: (
                        receipt.observed_at_s,
                        receipt.constellation_id,
                        receipt.satellite_id,
                        receipt.report_id,
                    ),
                )
                if (
                    association.last_report_id != latest.report_id
                    or association.last_observed_at_s
                    != latest.observed_at_s
                    or association.last_received_at_s
                    != latest.delivery_time_s
                    or association.track_id != latest.resulting_track_id
                    or association.target_side != latest.target_side
                ):
                    raise ValueError(
                        "IMINT association disagrees with its latest receipt",
                    )
                if track.state.last_update_time != (
                    association.last_observed_at_s
                ):
                    raise ValueError(
                        "IMINT track epoch disagrees with association",
                    )
                if elapsed is not None:
                    expected_status = self._imint_status(
                        hits=track.hits,
                        age_s=elapsed - association.last_observed_at_s,
                    )
                    if track.status is not expected_status:
                        raise ValueError(
                            "IMINT track status disagrees with checkpoint age",
                        )
                if (
                    track.contact_info.level is not ContactLevel.DETECTED
                    or track.contact_info.type_estimate is not None
                    or track.contact_info.specific_estimate is not None
                    or track.contact_info.confidence != 0.0
                ):
                    raise ValueError(
                        "IMINT track contact classification is invalid",
                    )
        for receipt in receipts:
            association = associations.get(
                receipt.reporting_side,
                {},
            ).get(receipt.target_id)
            if association is None:
                raise ValueError(
                    "Space imagery receipt has no target association",
                )
            if receipt.resulting_track_id != association.track_id:
                raise ValueError(
                    "Space imagery receipt points to the wrong track",
                )
        for side_tracks in tracks.values():
            for track in side_tracks.values():
                if (
                    track.status is TrackStatus.STALE
                    and track.track_id not in associated_track_ids
                ):
                    raise ValueError(
                        "Fusion STALE track has no unique IMINT association",
                    )

        delivery_receipt_ledger = _DeliveryReceiptLedger(
            receipts,
            revision=self._delivery_receipts.revision + 1,
        )
        return {
            "tracks": tracks,
            "track_counter": raw_counter,
            "fow_track_counters": fow_track_counters,
            "rng_state": rng_state,
            "satellite_passes": satellite_passes,
            "delivery_receipts": receipts,
            "delivery_receipt_ledger": delivery_receipt_ledger,
            "imint_target_tracks": associations,
        }

    def commit_state(self, staged_state: dict[str, Any]) -> None:
        """Commit a non-throwing staged fusion snapshot."""
        self._track_counter = staged_state["track_counter"]
        self._fow_track_counters = dict(staged_state["fow_track_counters"])
        self._rng.bit_generator.state = staged_state["rng_state"]
        self._tracks = {
            side: dict(side_tracks)
            for side, side_tracks in staged_state["tracks"].items()
        }
        self._satellite_passes = {
            side: list(passes)
            for side, passes in staged_state["satellite_passes"].items()
        }
        self._delivery_receipts = staged_state["delivery_receipt_ledger"]
        self._imint_target_tracks = {
            side: dict(associations)
            for side, associations in staged_state[
                "imint_target_tracks"
            ].items()
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Validate and atomically restore standalone fusion state."""
        self.commit_state(self.stage_state(state))
