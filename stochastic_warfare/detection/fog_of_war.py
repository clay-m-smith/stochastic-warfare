"""Fog of War — per-side world view management.

The public-facing API for the detection layer.  Each side maintains an
independent :class:`SideWorldView` containing only what its sensors and
intelligence have revealed.  Undetected enemies do not appear.
"""

from __future__ import annotations

import copy
import enum
import hashlib
import json
import math
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, fields, is_dataclass, replace
from typing import Any, TypeAlias

import numpy as np
from shapely import STRtree, box as vectorized_box, points as vectorized_points
from shapely.geometry import Point, box

from pydantic import BaseModel

from stochastic_warfare.core.indexed_rng import (
    FOWDecisionIdentity,
    FOWIndexedSideHandle,
    FOWTargetKind,
)
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.performance_receipts import (
    FOWCadenceReceipt,
    FOWCadenceRecoveryPeriodReceipt,
    FOWDetectionReceipt,
    FOWFusionReceipt,
    FOWIndexedRNGReceipt,
    FOWScanReceipt,
    FOWSelectionReceipt,
    FogOfWarCycleReceipt,
    LODDetectionReceipt,
)
from stochastic_warfare.core.types import Position
from stochastic_warfare.detection.cadence import (
    TacticalAttachmentIdentity,
    TacticalCadenceDecision,
    TacticalCadenceDisposition,
    TacticalCadencePlan,
    TacticalCadenceRecoveryAxis,
    TacticalCadenceRestorePlan,
    TacticalCadenceScheduler,
    TacticalObserverIdentity,
)
from stochastic_warfare.detection.deception import (
    Decoy,
    DeceptionEngine,
    DeceptionType,
)
from stochastic_warfare.detection.detection import (
    DetectionDecisionStage,
    DetectionEngine,
    DetectionScanCountEntry,
    DetectionScanCountSnapshot,
    DetectionScanIdentity,
    PreparedDetection,
    _DetectionGeometry,
    _detection_geometry,
)
from stochastic_warfare.detection.estimation import (
    StateEstimator,
    Track,
    TrackStatus,
)
from stochastic_warfare.detection.identification import (
    ContactInfo,
    ContactLevel,
    IdentificationEngine,
)
from stochastic_warfare.detection.intel_fusion import (
    IntelFusionEngine,
    SensorFusionCandidate,
    _PreparedSensorFusionCandidate,
    _ValidatedSensorFusionCandidate,
    validate_fow_track_id,
)
from stochastic_warfare.detection.observer_support import (
    ObserverTrackSupportIdentity,
    ObserverTrackSupportState,
    observer_track_support_role_is_supported,
    observer_track_support_state_from_state,
    observer_track_support_state_to_state,
)
from stochastic_warfare.detection.sensor_roles import SensorModeledRole
from stochastic_warfare.detection.sensors import SensorInstance, SensorType
from stochastic_warfare.detection.signatures import SignatureProfile

logger = get_logger(__name__)


class UnsupportedLegacyFogOfWarUpdateError(RuntimeError):
    """Raised when a caller bypasses the receipt-bearing FOW transaction."""


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


def _require_witness_id(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be a non-empty trimmed string")


def _require_finite_witness_scalar(
    value: float,
    field_name: str,
    *,
    non_negative: bool = False,
) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or (non_negative and float(value) < 0.0)
    ):
        qualifier = "finite and non-negative" if non_negative else "finite"
        raise ValueError(f"{field_name} must be {qualifier}")


def _exact_receipt_value_matches(value: object, expected: object) -> bool:
    """Compare one bounded receipt graph without Python scalar aliases."""
    if type(value) is not type(expected):
        return False
    if isinstance(expected, BaseModel):
        try:
            return all(
                _exact_receipt_value_matches(
                    getattr(value, name),
                    getattr(expected, name),
                )
                for name in type(expected).model_fields
            )
        except AttributeError:
            return False
    if type(expected) in {tuple, list}:
        return len(value) == len(expected) and all(
            _exact_receipt_value_matches(item, expected_item)
            for item, expected_item in zip(value, expected, strict=True)
        )
    if type(expected) is dict:
        return len(value) == len(expected) and all(
            _exact_receipt_value_matches(key, expected_key) and _exact_receipt_value_matches(item, expected_item)
            for (key, item), (expected_key, expected_item) in zip(
                value.items(),
                expected.items(),
                strict=True,
            )
        )
    return value == expected


def _exact_fow_receipt_matches(
    value: object,
    expected: FogOfWarCycleReceipt,
) -> bool:
    """Return whether one public receipt exactly matches its private authority."""
    return type(value) is FogOfWarCycleReceipt and _exact_receipt_value_matches(
        value,
        expected,
    )


def _exact_fow_receipt_tuple_matches(
    value: object,
    expected: tuple[FogOfWarCycleReceipt, ...],
) -> bool:
    """Return whether one bounded public receipt tuple is type-exact."""
    return (
        type(value) is tuple
        and len(value) == len(expected)
        and all(
            _exact_fow_receipt_matches(receipt, authoritative)
            for receipt, authoritative in zip(value, expected, strict=True)
        )
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class ObserverDetectionWitness:
    """One successful canonical observer/sensor detection check.

    Witnesses are bounded current-update integration evidence, not general
    fog-of-war contact history.  Checkpoints persist only the current cache so
    they can retain exact observer and attachment identity that the side-wide
    contact record cannot represent.
    """

    side: str
    observer_unit_id: str
    target_id: str
    source_equipment_index: int
    sensor_id: str
    modeled_role: str
    logical_time_s: float
    detected: bool
    probability: float
    snr_db: float
    range_m: float
    sensor_type: str
    bearing_deg: float

    def __post_init__(self) -> None:
        _require_witness_id(self.side, "witness side")
        _require_witness_id(
            self.observer_unit_id,
            "witness observer_unit_id",
        )
        _require_witness_id(self.target_id, "witness target_id")
        _require_witness_id(self.sensor_id, "witness sensor_id")
        _require_witness_id(self.modeled_role, "witness modeled_role")
        _require_witness_id(self.sensor_type, "witness sensor_type")
        if (
            isinstance(self.source_equipment_index, bool)
            or not isinstance(self.source_equipment_index, int)
            or self.source_equipment_index < 0
        ):
            raise ValueError(
                "witness source_equipment_index must be a non-negative int",
            )
        if self.detected is not True:
            raise ValueError("a detection witness must represent success")
        _require_finite_witness_scalar(
            self.logical_time_s,
            "witness logical_time_s",
            non_negative=True,
        )
        _require_finite_witness_scalar(
            self.probability,
            "witness probability",
            non_negative=True,
        )
        if self.probability > 1.0:
            raise ValueError("witness probability must be at most 1.0")
        _require_finite_witness_scalar(self.snr_db, "witness snr_db")
        _require_finite_witness_scalar(
            self.range_m,
            "witness range_m",
            non_negative=True,
        )
        _require_finite_witness_scalar(
            self.bearing_deg,
            "witness bearing_deg",
            non_negative=True,
        )
        if self.bearing_deg >= 360.0:
            raise ValueError("witness bearing_deg must be less than 360")

    def get_state(self) -> dict[str, Any]:
        """Return the exact scalar checkpoint representation."""
        return {
            "side": self.side,
            "observer_unit_id": self.observer_unit_id,
            "target_id": self.target_id,
            "source_equipment_index": self.source_equipment_index,
            "sensor_id": self.sensor_id,
            "modeled_role": self.modeled_role,
            "logical_time_s": self.logical_time_s,
            "detected": self.detected,
            "probability": self.probability,
            "snr_db": self.snr_db,
            "range_m": self.range_m,
            "sensor_type": self.sensor_type,
            "bearing_deg": self.bearing_deg,
        }

    def __deepcopy__(
        self,
        memo: dict[int, Any],
    ) -> ObserverDetectionWitness:
        """Detach this frozen scalar leaf without generic reconstruction."""
        prior = memo.get(id(self))
        if prior is not None:
            return prior
        detached = object.__new__(ObserverDetectionWitness)
        memo[id(self)] = detached
        side = self.side
        object.__setattr__(
            detached,
            "side",
            side if type(side) is str else copy.deepcopy(side, memo),
        )
        observer_unit_id = self.observer_unit_id
        object.__setattr__(
            detached,
            "observer_unit_id",
            (observer_unit_id if type(observer_unit_id) is str else copy.deepcopy(observer_unit_id, memo)),
        )
        target_id = self.target_id
        object.__setattr__(
            detached,
            "target_id",
            target_id if type(target_id) is str else copy.deepcopy(target_id, memo),
        )
        source_equipment_index = self.source_equipment_index
        object.__setattr__(
            detached,
            "source_equipment_index",
            (
                source_equipment_index
                if type(source_equipment_index) is int
                else copy.deepcopy(source_equipment_index, memo)
            ),
        )
        sensor_id = self.sensor_id
        object.__setattr__(
            detached,
            "sensor_id",
            sensor_id if type(sensor_id) is str else copy.deepcopy(sensor_id, memo),
        )
        modeled_role = self.modeled_role
        object.__setattr__(
            detached,
            "modeled_role",
            modeled_role if type(modeled_role) is str else copy.deepcopy(modeled_role, memo),
        )
        logical_time_s = self.logical_time_s
        object.__setattr__(
            detached,
            "logical_time_s",
            (logical_time_s if type(logical_time_s) in (int, float) else copy.deepcopy(logical_time_s, memo)),
        )
        detected = self.detected
        object.__setattr__(
            detached,
            "detected",
            detected if type(detected) is bool else copy.deepcopy(detected, memo),
        )
        probability = self.probability
        object.__setattr__(
            detached,
            "probability",
            (probability if type(probability) in (int, float) else copy.deepcopy(probability, memo)),
        )
        snr_db = self.snr_db
        object.__setattr__(
            detached,
            "snr_db",
            snr_db if type(snr_db) in (int, float) else copy.deepcopy(snr_db, memo),
        )
        range_m = self.range_m
        object.__setattr__(
            detached,
            "range_m",
            range_m if type(range_m) in (int, float) else copy.deepcopy(range_m, memo),
        )
        sensor_type = self.sensor_type
        object.__setattr__(
            detached,
            "sensor_type",
            sensor_type if type(sensor_type) is str else copy.deepcopy(sensor_type, memo),
        )
        bearing_deg = self.bearing_deg
        object.__setattr__(
            detached,
            "bearing_deg",
            (bearing_deg if type(bearing_deg) in (int, float) else copy.deepcopy(bearing_deg, memo)),
        )
        return detached


@dataclass(frozen=True, slots=True, kw_only=True)
class FogOfWarSensorBinding:
    """Typed production sensor identity used during checkpoint preflight."""

    unit_id: str
    side: str
    source_equipment_index: int
    sensor_id: str
    modeled_role: str
    sensor_type: str

    def __post_init__(self) -> None:
        _require_witness_id(self.unit_id, "sensor binding unit_id")
        _require_witness_id(self.side, "sensor binding side")
        _require_witness_id(self.sensor_id, "sensor binding sensor_id")
        _require_witness_id(
            self.modeled_role,
            "sensor binding modeled_role",
        )
        _require_witness_id(self.sensor_type, "sensor binding sensor_type")
        if (
            isinstance(self.source_equipment_index, bool)
            or not isinstance(self.source_equipment_index, int)
            or self.source_equipment_index < 0
        ):
            raise ValueError(
                "sensor binding source_equipment_index must be a non-negative integer",
            )

    @property
    def cadence_identity(self) -> TacticalAttachmentIdentity:
        """Project the exact runtime attachment identity."""
        return TacticalAttachmentIdentity(
            reporting_side=self.side,
            observer_unit_id=self.unit_id,
            source_equipment_index=self.source_equipment_index,
            sensor_id=self.sensor_id,
            modeled_role=self.modeled_role,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class FogOfWarCadenceBinding:
    """Context-owned expected periods for one runtime sensor attachment."""

    identity: TacticalAttachmentIdentity
    native_period: int
    current_lod_period: int

    def __post_init__(self) -> None:
        if type(self.identity) is not TacticalAttachmentIdentity:
            raise TypeError("cadence binding identity must be a TacticalAttachmentIdentity")
        for value, label in (
            (self.native_period, "native_period"),
            (self.current_lod_period, "current_lod_period"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"cadence binding {label} must be a positive integer")


@dataclass(frozen=True, slots=True, kw_only=True)
class FogOfWarNativePhaseBinding:
    """Context-owned native cadence binding for an active or retired sensor."""

    identity: TacticalAttachmentIdentity
    native_period: int

    def __post_init__(self) -> None:
        if type(self.identity) is not TacticalAttachmentIdentity:
            raise TypeError(
                "native phase binding identity must be a TacticalAttachmentIdentity",
            )
        if isinstance(self.native_period, bool) or not isinstance(self.native_period, int) or self.native_period <= 0:
            raise ValueError(
                "native phase binding native_period must be a positive integer",
            )


@dataclass(frozen=True, slots=True)
class FogOfWarRestorePlan:
    """Owner-bound, fully validated fog/fusion publication plan."""

    _world_views: dict[str, SideWorldView] = field(repr=False)
    _current_detection_witnesses: dict[
        str,
        tuple[ObserverDetectionWitness, ...],
    ] = field(repr=False)
    _observer_track_supports: tuple[ObserverTrackSupportState, ...] = field(
        repr=False,
    )
    _rng_state: dict[str, Any] = field(repr=False)
    _intel_fusion: dict[str, Any] = field(repr=False)
    _scan_counts: DetectionScanCountSnapshot = field(repr=False)
    _cadence_state: dict[str, Any] = field(repr=False)
    _cadence_plan: TacticalCadenceRestorePlan = field(repr=False)
    _owner_token: object = field(repr=False, compare=False)
    _structure_fingerprint: str = field(repr=False)
    _fingerprint: str = field(repr=False)

    @property
    def world_views(self) -> dict[str, SideWorldView]:
        """Return a defensive copy of the staged ordinary-contact views."""
        return copy.deepcopy(self._world_views)

    @property
    def current_detection_witnesses(
        self,
    ) -> dict[str, tuple[ObserverDetectionWitness, ...]]:
        """Return a defensive copy of the staged bounded witnesses."""
        return copy.deepcopy(self._current_detection_witnesses)

    @property
    def observer_track_supports(
        self,
    ) -> tuple[ObserverTrackSupportState, ...]:
        """Return a defensive canonical observer-support publication."""
        return copy.deepcopy(self._observer_track_supports)

    @property
    def rng_state(self) -> dict[str, Any]:
        """Return a defensive copy of the staged DETECTION RNG mirror."""
        return copy.deepcopy(self._rng_state)

    @property
    def intel_fusion(self) -> dict[str, Any]:
        """Return a defensive copy of the staged fusion publication."""
        return copy.deepcopy(self._intel_fusion)

    @property
    def scan_counts(self) -> tuple[DetectionScanCountEntry, ...]:
        """Return the immutable staged dwell-counter entries."""
        return self._scan_counts.entries

    @property
    def cadence_state(self) -> dict[str, Any]:
        """Return a defensive copy of the staged cadence publication."""
        return copy.deepcopy(self._cadence_state)


@dataclass(frozen=True, slots=True)
class FogOfWarCheckpointSnapshot:
    """One canonical FOW payload and the plan that validated that payload."""

    _state: dict[str, Any] = field(repr=False)
    plan: FogOfWarRestorePlan

    @property
    def state(self) -> dict[str, Any]:
        """Return a defensive copy of the validated canonical payload."""
        return copy.deepcopy(self._state)


@dataclass(frozen=True, slots=True)
class _ObserverSensorScan:
    sensor: SensorInstance
    source_equipment_index: int | None = None
    modeled_role: str | None = None


_TacticalAttachmentKey: TypeAlias = tuple[str, str, int, str, str]
_TACTICAL_ATTACHMENT_U64_MAX = (1 << 64) - 1


def _validated_tactical_attachment_key(
    *,
    reporting_side: str,
    observer_unit_id: str,
    source_equipment_index: int,
    sensor_id: str,
    modeled_role: str,
) -> _TacticalAttachmentKey:
    """Validate one live attachment key without constructing its model."""
    for value, field_name in (
        (reporting_side, "reporting_side"),
        (observer_unit_id, "observer_unit_id"),
        (sensor_id, "sensor_id"),
        (modeled_role, "modeled_role"),
    ):
        if type(value) is not str or not value or value != value.strip():
            raise ValueError(
                f"fog-of-war attachment {field_name} must be non-empty trimmed text",
            )
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError(
                f"fog-of-war attachment {field_name} must be valid UTF-8",
            ) from exc
    if type(source_equipment_index) is not int or not 0 <= source_equipment_index <= _TACTICAL_ATTACHMENT_U64_MAX:
        raise ValueError(
            "fog-of-war attachment source_equipment_index must be an unsigned 64-bit integer",
        )
    return (
        reporting_side,
        observer_unit_id,
        source_equipment_index,
        sensor_id,
        modeled_role,
    )


def _tactical_attachment_key(
    identity: TacticalAttachmentIdentity,
) -> _TacticalAttachmentKey:
    """Return the exact scalar identity key without allocating a new model."""
    return (
        identity.reporting_side,
        identity.observer_unit_id,
        identity.source_equipment_index,
        identity.sensor_id,
        identity.modeled_role,
    )


@dataclass(frozen=True, slots=True)
class _BoundObserverSensorScan:
    """One live scan bound to its cadence-owned attachment identity."""

    scan: _ObserverSensorScan
    attachment_key: _TacticalAttachmentKey
    identity: TacticalAttachmentIdentity
    cadence_decision: TacticalCadenceDecision
    scan_identity: DetectionScanIdentity


def _build_fow_target_tree(
    targets: list[dict[str, Any]],
) -> STRtree:
    """Vectorize exact finite 2-D points, retaining the scalar anomaly path."""

    def scalar_tree() -> STRtree:
        return STRtree(
            [
                Point(
                    target["position"].easting,
                    target["position"].northing,
                )
                for target in targets
            ]
        )

    eastings: list[float] = []
    northings: list[float] = []
    for target in targets:
        position = target["position"]
        if type(position) is not Position:
            return scalar_tree()
        raw_easting = position.easting
        raw_northing = position.northing
        if type(raw_easting) not in (int, float) or type(raw_northing) not in (
            int,
            float,
        ):
            return scalar_tree()
        try:
            easting = float(raw_easting)
            northing = float(raw_northing)
        except (OverflowError, TypeError, ValueError):
            return scalar_tree()
        if not math.isfinite(easting) or not math.isfinite(northing):
            return scalar_tree()
        eastings.append(easting)
        northings.append(northing)
    return STRtree(
        vectorized_points(
            np.asarray(eastings, dtype=np.float64),
            np.asarray(northings, dtype=np.float64),
        )
    )


_StagedObserver: TypeAlias = tuple[
    dict[str, Any],
    str,
    TacticalObserverIdentity,
    tuple[_BoundObserverSensorScan, ...],
]


@dataclass(frozen=True, slots=True)
class _ObserverTrackSupportCandidate:
    """Successful radar measurement awaiting its final fusion generation."""

    identity: ObserverTrackSupportIdentity
    sensor_type: SensorType
    cadence_decision: TacticalCadenceDecision
    range_m: float
    probability: float
    observation_time_s: float


@dataclass(slots=True)
class _FOWFusionAccumulator:
    """Owner-private reduction plus complete downstream observation ledger."""

    candidate_count: int
    representative_key: tuple[float, bytes]
    representative: _ValidatedSensorFusionCandidate
    candidate_ledger: dict[bytes, SensorFusionCandidate]

    @classmethod
    def from_candidate(
        cls,
        validated: _ValidatedSensorFusionCandidate,
        candidate: SensorFusionCandidate,
        issued_preimage: bytes,
    ) -> _FOWFusionAccumulator:
        cls._validate_candidate_binding(
            validated,
            candidate,
            issued_preimage,
        )
        return cls(
            candidate_count=1,
            representative_key=(
                validated.effective_variance_m2,
                issued_preimage,
            ),
            representative=validated,
            candidate_ledger={issued_preimage: candidate},
        )

    def accumulate(
        self,
        validated: _ValidatedSensorFusionCandidate,
        candidate: SensorFusionCandidate,
        issued_preimage: bytes,
    ) -> None:
        """Count one unique candidate and retain its canonical minimum."""
        self._validate_candidate_binding(
            validated,
            candidate,
            issued_preimage,
        )
        if validated.group_key != self.representative.group_key:
            raise ValueError(
                "prevalidated FOW candidates disagree on their exact group",
            )
        if issued_preimage in self.candidate_ledger:
            raise ValueError(
                "prevalidated FOW fusion group contains a duplicate preimage",
            )
        candidate_key = (
            validated.effective_variance_m2,
            issued_preimage,
        )
        self.candidate_ledger[issued_preimage] = candidate
        self.candidate_count += 1
        if candidate_key < self.representative_key:
            self.representative_key = candidate_key
            self.representative = validated

    @staticmethod
    def _validate_candidate_binding(
        validated: _ValidatedSensorFusionCandidate,
        candidate: SensorFusionCandidate,
        issued_preimage: bytes,
    ) -> None:
        if (
            type(validated) is not _ValidatedSensorFusionCandidate
            or type(candidate) is not SensorFusionCandidate
            or type(issued_preimage) is not bytes
            or not issued_preimage
            or validated.identity is not candidate.identity
            or validated.encoded_identity != issued_preimage
            or type(validated.effective_variance_m2) is not float
            or not math.isfinite(validated.effective_variance_m2)
            or validated.effective_variance_m2 <= 0.0
        ):
            raise ValueError(
                "prevalidated FOW candidate binding is inconsistent",
            )


@dataclass
class ContactRecord:
    """What one side believes about an enemy contact."""

    contact_id: str
    track: Track
    contact_info: ContactInfo
    first_detected_time: float
    last_sensor_contact_time: float
    reporting_sensors: list[str] = field(default_factory=list)

    def get_state(self) -> dict[str, Any]:
        return {
            "contact_id": self.contact_id,
            "track": self.track.get_state(),
            "contact_info": {
                "level": int(self.contact_info.level),
                "domain_estimate": self.contact_info.domain_estimate,
                "type_estimate": self.contact_info.type_estimate,
                "specific_estimate": self.contact_info.specific_estimate,
                "confidence": self.contact_info.confidence,
            },
            "first_detected_time": self.first_detected_time,
            "last_sensor_contact_time": self.last_sensor_contact_time,
            "reporting_sensors": list(self.reporting_sensors),
        }


@dataclass
class SideWorldView:
    """One side's complete picture of the world."""

    side: str
    contacts: dict[str, ContactRecord] = field(default_factory=dict)
    last_update_time: float = 0.0

    def get_state(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "contacts": {cid: cr.get_state() for cid, cr in sorted(self.contacts.items())},
            "last_update_time": self.last_update_time,
        }


class FogOfWarLodTier(str, enum.Enum):
    """Dependency-safe LOD tier supplied by the BattleManager authority."""

    ACTIVE = "ACTIVE"
    NEARBY = "NEARBY"
    DISTANT = "DISTANT"


@dataclass(frozen=True, slots=True)
class FogOfWarCycleOutcome:
    """One successful side update and its reconciled execution receipt."""

    world_view: SideWorldView
    receipt: FogOfWarCycleReceipt
    witnesses: tuple[ObserverDetectionWitness, ...] = ()
    observer_track_supports: tuple[ObserverTrackSupportState, ...] = ()


@dataclass(frozen=True, slots=True)
class FogOfWarContactIdentity:
    """Stable public identity for one observed side contact."""

    target_id: str
    track_id: str


@dataclass(frozen=True, slots=True)
class FogOfWarSideSnapshot:
    """Non-mutating bounded public observation of one reporting side."""

    reporting_side: str
    present: bool
    identities: tuple[FogOfWarContactIdentity, ...]


class _DefensiveMappingPreview(dict[Any, Any]):
    """Lazy detached mapping view for an opaque update handle.

    The authoritative transaction graph stays in the manager-private
    workspace.  Reads materialize a defensive snapshot; writes detach a local
    diagnostic shadow and can therefore never reach that workspace.
    """

    __slots__ = ("__detached", "__mutated", "__snapshotter")
    _MISSING = object()

    def __init__(self, snapshotter: Callable[[], dict[Any, Any]]) -> None:
        super().__init__()
        self.__snapshotter: Callable[[], dict[Any, Any]] | None = snapshotter
        self.__detached: dict[Any, Any] | None = None
        self.__mutated = False

    @property
    def pristine(self) -> bool:
        """Return whether a top-level diagnostic write was attempted."""
        return not self.__mutated

    def retire(self) -> None:
        """Sever the callback and discard any private diagnostic shadow."""
        self.__detached = None
        self.__snapshotter = None

    def _snapshot(self) -> dict[Any, Any]:
        snapshotter = self.__snapshotter
        if snapshotter is None:
            raise RuntimeError("fog-of-war diagnostic preview is stale")
        return snapshotter()

    def _read(self) -> dict[Any, Any]:
        detached = self.__detached
        return self._snapshot() if detached is None else detached

    def _write(self) -> dict[Any, Any]:
        self.__mutated = True
        if self.__detached is None:
            self.__detached = self._snapshot()
        return self.__detached

    def __getitem__(self, key: Any) -> Any:
        return self._read()[key]

    def __setitem__(self, key: Any, value: Any) -> None:
        self._write()[key] = copy.deepcopy(value)

    def __delitem__(self, key: Any) -> None:
        del self._write()[key]

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self._read())

    def __len__(self) -> int:
        return len(self._read())

    def __contains__(self, key: object) -> bool:
        return key in self._read()

    def __repr__(self) -> str:
        return repr(self._read())

    def __eq__(self, other: object) -> bool:
        return self._read() == other

    def __copy__(self) -> dict[Any, Any]:
        return self._read().copy()

    def __deepcopy__(self, memo: dict[int, Any]) -> dict[Any, Any]:
        snapshot = copy.deepcopy(self._read(), memo)
        memo[id(self)] = snapshot
        return snapshot

    def get(self, key: Any, default: Any = None) -> Any:
        return self._read().get(key, default)

    def keys(self):  # type: ignore[no-untyped-def]
        return self._read().keys()

    def items(self):  # type: ignore[no-untyped-def]
        return self._read().items()

    def values(self):  # type: ignore[no-untyped-def]
        return self._read().values()

    def copy(self) -> dict[Any, Any]:
        return self._read().copy()

    def clear(self) -> None:
        self.__mutated = True
        self.__detached = {}

    def pop(self, key: Any, default: Any = _MISSING) -> Any:
        writable = self._write()
        if default is self._MISSING:
            return writable.pop(key)
        return writable.pop(key, default)

    def popitem(self) -> tuple[Any, Any]:
        return self._write().popitem()

    def setdefault(self, key: Any, default: Any = None) -> Any:
        return self._write().setdefault(key, copy.deepcopy(default))

    def update(self, *args: Any, **kwargs: Any) -> None:
        values = dict(*args, **kwargs)
        self._write().update(copy.deepcopy(values))

    def __ior__(self, other: Mapping[Any, Any]):
        self.update(other)
        return self

    def __or__(self, other: Mapping[Any, Any]):
        if not isinstance(other, Mapping):
            return NotImplemented
        merged = self._read().copy()
        merged.update(other)
        return merged

    def __ror__(self, other: Mapping[Any, Any]):
        if not isinstance(other, Mapping):
            return NotImplemented
        merged = dict(other)
        merged.update(self._read())
        return merged


class _DefensiveWorldViewPreview:
    """Lazy detached preview preserving the useful ``SideWorldView`` surface."""

    __slots__ = ("__side", "__snapshotter")

    def __init__(
        self,
        side: str,
        snapshotter: Callable[[], SideWorldView],
    ) -> None:
        self.__side = side
        self.__snapshotter: Callable[[], SideWorldView] | None = snapshotter

    def retire(self) -> None:
        """Sever the callback once the opaque handle becomes stale."""
        self.__snapshotter = None

    def _snapshot(self) -> SideWorldView:
        snapshotter = self.__snapshotter
        if snapshotter is None:
            raise RuntimeError("fog-of-war diagnostic preview is stale")
        return snapshotter()

    @property
    def side(self) -> str:
        return self.__side

    @property
    def contacts(self) -> dict[str, ContactRecord]:
        return self._snapshot().contacts

    @property
    def last_update_time(self) -> float:
        return self._snapshot().last_update_time

    def get_state(self) -> dict[str, Any]:
        return self._snapshot().get_state()

    def __copy__(self) -> SideWorldView:
        return self._snapshot()

    def __deepcopy__(self, memo: dict[int, Any]) -> SideWorldView:
        snapshot = self._snapshot()
        memo[id(self)] = snapshot
        return snapshot


@dataclass(frozen=True, slots=True)
class FogOfWarUpdateTransaction:
    """Owner-bound immutable baseline for one complete side union."""

    reporting_sides: tuple[str, ...]
    _world_views: dict[str, SideWorldView] = field(repr=False)
    _current_detection_witnesses: dict[
        str,
        tuple[ObserverDetectionWitness, ...],
    ] = field(repr=False)
    _observer_track_supports: tuple[ObserverTrackSupportState, ...] = field(
        repr=False,
    )
    _rng_state: dict[str, Any] = field(repr=False)
    _intel_fusion: dict[str, Any] = field(repr=False)
    _scan_counts: _DefensiveMappingPreview = field(repr=False)
    _owner_token: object = field(repr=False, compare=False)
    _generation: int = field(repr=False, compare=False)
    _fingerprint: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class _FogOfWarFusionSideDelta:
    """One reporting side's isolated fusion mutation set."""

    reporting_side: str
    track_counter: int
    fow_track_counter: int | None
    tracks: dict[str, Track] = field(repr=False)


@dataclass(frozen=True, slots=True)
class FogOfWarSidePlan:
    """One isolated, owner-bound reporting-side update plan."""

    reporting_side: str
    receipt: FogOfWarCycleReceipt
    _world_view: SideWorldView | _DefensiveWorldViewPreview = field(repr=False)
    _current_detection_witnesses: tuple[
        ObserverDetectionWitness,
        ...,
    ] = field(repr=False)
    _observer_track_supports: tuple[ObserverTrackSupportState, ...] = field(
        repr=False,
    )
    _fusion_delta: _FogOfWarFusionSideDelta = field(repr=False)
    _scan_count_entries: tuple[DetectionScanCountEntry, ...] = field(repr=False)
    _transaction: FogOfWarUpdateTransaction = field(repr=False, compare=False)
    _owner_token: object = field(repr=False, compare=False)
    _generation: int = field(repr=False, compare=False)
    _outcome_source: _FogOfWarOutcomeSource = field(repr=False, compare=False)
    _fingerprint: str = field(repr=False)

    @property
    def outcome(self) -> FogOfWarCycleOutcome:
        """Return a defensive preview of the staged side publication."""
        return self._outcome_source.side_outcome(self.reporting_side)


@dataclass(frozen=True, slots=True)
class FogOfWarPublicationPlan:
    """Prevalidated complete-side publication with no outer-owner commits."""

    reporting_sides: tuple[str, ...]
    receipts: tuple[FogOfWarCycleReceipt, ...]
    _world_views: dict[str, SideWorldView] = field(repr=False)
    _current_detection_witnesses: dict[
        str,
        tuple[ObserverDetectionWitness, ...],
    ] = field(repr=False)
    _observer_track_supports: tuple[ObserverTrackSupportState, ...] = field(
        repr=False,
    )
    _intel_fusion: dict[str, Any] = field(repr=False)
    _scan_counts: DetectionScanCountSnapshot = field(repr=False)
    _transaction: FogOfWarUpdateTransaction = field(repr=False, compare=False)
    _owner_token: object = field(repr=False, compare=False)
    _generation: int = field(repr=False, compare=False)
    _outcome_source: _FogOfWarOutcomeSource = field(repr=False, compare=False)
    _fingerprint: str = field(repr=False)

    @property
    def witnesses(self) -> tuple[ObserverDetectionWitness, ...]:
        """Return immutable witnesses in canonical reporting-side order."""
        return self._outcome_source.witnesses(self.reporting_sides)

    @property
    def outcomes(self) -> tuple[FogOfWarCycleOutcome, ...]:
        """Return defensive side outcomes in canonical reporting-side order."""
        return self._outcome_source.outcomes(self.reporting_sides)


@dataclass(frozen=True, slots=True)
class FogOfWarCommitPlan:
    """Fully materialized publication ready for an outer atomic commit."""

    reporting_sides: tuple[str, ...]
    receipts: tuple[FogOfWarCycleReceipt, ...]
    _publication: FogOfWarPublicationPlan = field(repr=False, compare=False)
    _owner_token: object = field(repr=False, compare=False)
    _generation: int = field(repr=False, compare=False)
    _outcome_source: _FogOfWarOutcomeSource = field(repr=False, compare=False)

    @property
    def outcomes(self) -> tuple[FogOfWarCycleOutcome, ...]:
        """Return defensive outcomes from the exact commit-ready state."""
        return self._outcome_source.outcomes(self.reporting_sides)


@dataclass(frozen=True, slots=True)
class _FOWScanCountValuesBinding:
    """Private exact-object seal for one validated raw counter mapping."""

    keys: tuple[tuple[Any, ...], ...]
    counts: tuple[int, ...]
    exact_builtin: bool


@dataclass(slots=True)
class _FogOfWarCommitPayload:
    """Manager-private publication payload never exposed through a plan."""

    world_views: dict[str, SideWorldView]
    current_detection_witnesses: dict[
        str,
        tuple[ObserverDetectionWitness, ...],
    ]
    observer_track_supports: tuple[ObserverTrackSupportState, ...]
    observer_track_support_map: dict[
        ObserverTrackSupportIdentity,
        ObserverTrackSupportState,
    ]
    receipts: tuple[FogOfWarCycleReceipt, ...]
    rng_state: dict[str, Any]
    intel_fusion: dict[str, Any]
    scan_counts: DetectionScanCountSnapshot
    scan_count_values: dict[Any, int]
    scan_count_values_binding: _FOWScanCountValuesBinding
    fingerprint: str


@dataclass(slots=True)
class _FogOfWarSideWorkspace:
    """Manager-private authoritative result of one side-local update."""

    plan: FogOfWarSidePlan
    receipt: FogOfWarCycleReceipt
    world_view: SideWorldView
    current_detection_witnesses: tuple[ObserverDetectionWitness, ...]
    observer_track_supports: tuple[ObserverTrackSupportState, ...]
    fusion_delta: _FogOfWarFusionSideDelta
    scan_count_values: dict[Any, int]
    handle_bindings: tuple[object, ...]


@dataclass(slots=True, weakref_slot=True)
class _FogOfWarUpdateWorkspace:
    """Single-use authoritative graph for one complete FOW update."""

    generation: int
    reporting_sides: tuple[str, ...]
    world_views: dict[str, SideWorldView]
    current_detection_witnesses: dict[
        str,
        tuple[ObserverDetectionWitness, ...],
    ]
    observer_track_supports: tuple[ObserverTrackSupportState, ...]
    rng_state: dict[str, Any]
    intel_fusion: dict[str, Any]
    baseline_scan_count_values: dict[Any, int]
    start_live_fingerprint: str
    cadence_binding: tuple[TacticalCadencePlan, object, str] | None = None
    transaction: FogOfWarUpdateTransaction | None = None
    transaction_bindings: tuple[object, ...] = ()
    side_workspaces: dict[str, _FogOfWarSideWorkspace] = field(default_factory=dict)
    publication_scan_count_values: dict[Any, int] | None = None
    publication_scan_count_values_binding: _FOWScanCountValuesBinding | None = None
    prepared_scan_count_values_binding_fields: tuple[object, object, bool] | None = None
    publication: FogOfWarPublicationPlan | None = None
    publication_bindings: tuple[object, ...] = ()
    commit_plan: FogOfWarCommitPlan | None = None
    commit_bindings: tuple[object, ...] = ()
    outcome_source: _FogOfWarOutcomeSource | None = None


class _FogOfWarOutcomeSource:
    """Read-only defensive outcome projection over a private workspace."""

    __slots__ = ("__frozen_outcomes", "__workspace")

    def __init__(self, workspace: _FogOfWarUpdateWorkspace) -> None:
        self.__workspace: _FogOfWarUpdateWorkspace | None = workspace
        self.__frozen_outcomes: dict[str, FogOfWarCycleOutcome] | None = None

    def retire(self) -> None:
        """Release an unfrozen workspace when its transaction aborts."""
        self.__workspace = None

    @staticmethod
    def _workspace_outcome(
        workspace: _FogOfWarUpdateWorkspace,
        side: str,
    ) -> FogOfWarCycleOutcome:
        record = workspace.side_workspaces[side]
        return FogOfWarCycleOutcome(
            world_view=record.world_view,
            receipt=record.receipt,
            witnesses=record.current_detection_witnesses,
            observer_track_supports=record.observer_track_supports,
        )

    @staticmethod
    def _defensive_outcome(
        outcome: FogOfWarCycleOutcome,
    ) -> FogOfWarCycleOutcome:
        """Detach every public outcome value from authoritative state."""
        return copy.deepcopy(outcome)

    def freeze(self, reporting_sides: tuple[str, ...]) -> None:
        """Detach one stable outcome snapshot before the workspace moves live."""
        if self.__frozen_outcomes is not None:
            return
        workspace = self.__workspace
        if workspace is None:  # pragma: no cover - private lifecycle invariant
            raise RuntimeError("fog-of-war outcome workspace is unavailable")
        frozen_outcomes = {
            side: self._defensive_outcome(
                self._workspace_outcome(workspace, side),
            )
            for side in reporting_sides
        }
        self.__frozen_outcomes = frozen_outcomes
        self.__workspace = None

    def side_outcome(self, side: str) -> FogOfWarCycleOutcome:
        frozen_outcomes = self.__frozen_outcomes
        if frozen_outcomes is not None:
            return self._defensive_outcome(frozen_outcomes[side])
        workspace = self.__workspace
        if workspace is None:  # pragma: no cover - private lifecycle invariant
            raise RuntimeError("fog-of-war outcome workspace is unavailable")
        return self._defensive_outcome(
            self._workspace_outcome(workspace, side),
        )

    def witnesses(
        self,
        reporting_sides: tuple[str, ...],
    ) -> tuple[ObserverDetectionWitness, ...]:
        frozen_outcomes = self.__frozen_outcomes
        if frozen_outcomes is not None:
            return copy.deepcopy(
                tuple(witness for side in reporting_sides for witness in frozen_outcomes[side].witnesses),
            )
        workspace = self.__workspace
        if workspace is None:  # pragma: no cover - private lifecycle invariant
            raise RuntimeError("fog-of-war outcome workspace is unavailable")
        return copy.deepcopy(
            tuple(
                witness for side in reporting_sides for witness in workspace.current_detection_witnesses.get(side, ())
            ),
        )

    def outcomes(
        self,
        reporting_sides: tuple[str, ...],
    ) -> tuple[FogOfWarCycleOutcome, ...]:
        return tuple(self.side_outcome(side) for side in reporting_sides)


@dataclass(frozen=True, slots=True)
class FogOfWarWitnessClearPlan:
    """Owner-bound disabled-FOW witness clear staged without mutation."""

    _baseline: dict[str, tuple[ObserverDetectionWitness, ...]] = field(
        repr=False,
    )
    _observer_track_supports: tuple[ObserverTrackSupportState, ...] = field(
        repr=False,
    )
    _owner_token: object = field(repr=False, compare=False)
    _fingerprint: str = field(repr=False)


_CONTACT_INFO_KEYS = {
    "level",
    "domain_estimate",
    "type_estimate",
    "specific_estimate",
    "confidence",
}
_CONTACT_STATE_KEYS = {
    "contact_id",
    "track",
    "contact_info",
    "first_detected_time",
    "last_sensor_contact_time",
    "reporting_sensors",
}
_TRACK_STATE_KEYS = {
    "track_id",
    "side",
    "contact_info",
    "state",
    "status",
    "hits",
    "misses",
}
_WITNESS_STATE_KEYS = {
    "side",
    "observer_unit_id",
    "target_id",
    "source_equipment_index",
    "sensor_id",
    "modeled_role",
    "logical_time_s",
    "detected",
    "probability",
    "snr_db",
    "range_m",
    "sensor_type",
    "bearing_deg",
}


def _strict_finite_number(
    value: Any,
    field_name: str,
    *,
    non_negative: bool = False,
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or (non_negative and float(value) < 0.0)
    ):
        qualifier = "finite and non-negative" if non_negative else "finite"
        raise ValueError(f"{field_name} must be {qualifier}")
    return float(value)


def _stage_contact_info(
    raw: Any,
    *,
    field_name: str,
    allow_unknown: bool,
) -> ContactInfo:
    if not isinstance(raw, dict) or set(raw) != _CONTACT_INFO_KEYS:
        raise ValueError(f"{field_name} has invalid keys")
    raw_level = raw["level"]
    if isinstance(raw_level, bool) or not isinstance(raw_level, int):
        raise ValueError(f"{field_name} level must be an integer enum")
    try:
        level = ContactLevel(raw_level)
    except ValueError as exc:
        raise ValueError(f"{field_name} level is unknown") from exc
    if not allow_unknown and level is ContactLevel.UNKNOWN:
        raise ValueError(f"{field_name} level cannot be UNKNOWN")
    estimates: dict[str, str | None] = {}
    for name in (
        "domain_estimate",
        "type_estimate",
        "specific_estimate",
    ):
        value = raw[name]
        if value is not None and (not isinstance(value, str) or not value or value != value.strip()):
            raise ValueError(
                f"{field_name} {name} must be null or a non-empty trimmed string",
            )
        estimates[name] = value
    if level < ContactLevel.CLASSIFIED and any(estimates.values()):
        raise ValueError(
            f"{field_name} estimates exceed the contact level",
        )
    if level < ContactLevel.IDENTIFIED and estimates["specific_estimate"] is not None:
        raise ValueError(
            f"{field_name} specific estimate requires IDENTIFIED level",
        )
    confidence = _strict_finite_number(
        raw["confidence"],
        f"{field_name} confidence",
        non_negative=True,
    )
    if confidence > 1.0:
        raise ValueError(f"{field_name} confidence must be in [0, 1]")
    return ContactInfo(
        level=level,
        domain_estimate=estimates["domain_estimate"],
        type_estimate=estimates["type_estimate"],
        specific_estimate=estimates["specific_estimate"],
        confidence=confidence,
    )


def _stage_witness(raw: Any, *, side: str) -> ObserverDetectionWitness:
    if not isinstance(raw, dict) or set(raw) != _WITNESS_STATE_KEYS:
        raise ValueError("Fog-of-war detection witness has invalid keys")
    try:
        witness = ObserverDetectionWitness(
            side=raw["side"],
            observer_unit_id=raw["observer_unit_id"],
            target_id=raw["target_id"],
            source_equipment_index=raw["source_equipment_index"],
            sensor_id=raw["sensor_id"],
            modeled_role=raw["modeled_role"],
            logical_time_s=raw["logical_time_s"],
            detected=raw["detected"],
            probability=raw["probability"],
            snr_db=raw["snr_db"],
            range_m=raw["range_m"],
            sensor_type=raw["sensor_type"],
            bearing_deg=raw["bearing_deg"],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid fog-of-war detection witness: {exc}") from exc
    if witness.side != side:
        raise ValueError(
            "Fog-of-war witness side disagrees with its owner map",
        )
    return witness


def _fusion_plan_payload(fusion: dict[str, Any]) -> dict[str, Any]:
    ledger = fusion["delivery_receipt_ledger"]
    fusion_tracks = fusion["tracks"]
    return {
        "tracks": {
            side: {track_id: track.get_state() for track_id, track in sorted(side_tracks.items())}
            for side, side_tracks in sorted(fusion_tracks.items())
        },
        "track_counter": fusion["track_counter"],
        "fow_track_counters": dict(fusion["fow_track_counters"]),
        "rng_state": copy.deepcopy(fusion["rng_state"]),
        "satellite_passes": {
            side: [satellite_pass.model_dump(mode="json") for satellite_pass in passes]
            for side, passes in sorted(
                fusion["satellite_passes"].items(),
            )
        },
        "delivery_receipts": [receipt.to_state() for receipt in fusion["delivery_receipts"]],
        "delivery_receipt_ledger": {
            "ordered": [receipt.to_state() for receipt in ledger],
            "by_report_id": {
                str(report_id): receipt.to_state()
                for report_id, receipt in sorted(
                    ledger._by_report_id.items(),
                )
            },
            "revision": ledger.revision,
        },
        "imint_target_tracks": {
            side: {
                target_id: association.model_dump(mode="json")
                for target_id, association in sorted(
                    associations.items(),
                )
            }
            for side, associations in sorted(
                fusion["imint_target_tracks"].items(),
            )
        },
    }


def _restore_plan_payload(plan: FogOfWarRestorePlan) -> dict[str, Any]:
    fusion = plan._intel_fusion
    fusion_tracks = fusion["tracks"]
    return {
        "world_views": {side: world_view.get_state() for side, world_view in sorted(plan._world_views.items())},
        "contact_fusion_aliases": {
            side: {
                contact_id: (
                    fusion_tracks.get(side, {}).get(
                        contact.track.track_id,
                    )
                    is contact.track
                )
                for contact_id, contact in sorted(
                    world_view.contacts.items(),
                )
            }
            for side, world_view in sorted(plan._world_views.items())
        },
        "current_detection_witnesses": {
            side: [witness.get_state() for witness in witnesses]
            for side, witnesses in sorted(
                plan._current_detection_witnesses.items(),
            )
        },
        "observer_track_supports": [
            observer_track_support_state_to_state(support) for support in plan._observer_track_supports
        ],
        "rng_state": plan._rng_state,
        "scan_counts": _scan_count_payload(plan._scan_counts),
        "cadence": plan._cadence_state,
        "cadence_plan": {
            "schema_version": plan._cadence_plan.schema_version,
            "committed_ordinal": plan._cadence_plan.committed_ordinal,
            "complete_from_tick_zero": plan._cadence_plan.complete_from_tick_zero,
            "attachments": [state.get_state() for state in plan._cadence_plan.attachment_states],
            "native_phase_assignments": [assignment.get_state() for assignment in plan._cadence_plan.phase_assignments],
            "native_phase_assignments_sha256": (plan._cadence_plan.phase_assignments_sha256),
        },
        "intel_fusion": _fusion_plan_payload(fusion),
    }


def _scan_count_payload(
    snapshot: DetectionScanCountSnapshot,
) -> list[dict[str, Any]]:
    return _scan_count_entries_payload(snapshot.entries)


def _scan_count_entries_payload(
    entries: tuple[DetectionScanCountEntry, ...],
) -> list[dict[str, Any]]:
    return [
        {
            "scan_identity": (
                None
                if entry.scan_identity is None
                else {
                    "side": entry.scan_identity.side,
                    "observer_unit_id": entry.scan_identity.observer_unit_id,
                    "source_equipment_index": (entry.scan_identity.source_equipment_index),
                }
            ),
            "sensor_id": entry.sensor_id,
            "target_id": entry.target_id,
            "count": entry.count,
        }
        for entry in entries
    ]


def _validated_observer_track_support_tuple(
    value: object,
    *,
    field_name: str,
) -> tuple[ObserverTrackSupportState, ...]:
    """Reject content-equivalent structural mutation of owner publications."""
    if type(value) is not tuple or any(type(support) is not ObserverTrackSupportState for support in value):
        raise ValueError(
            f"{field_name} must be an exact ObserverTrackSupportState tuple",
        )
    supports = value
    if supports != tuple(
        sorted(
            supports,
            key=lambda support: support.identity.sort_key(),
        ),
    ):
        raise ValueError(f"{field_name} must be canonically ordered")
    identities = tuple(support.identity for support in supports)
    if len(identities) != len(set(identities)):
        raise ValueError(f"{field_name} contains duplicate identities")
    return supports


def _update_plan_payload(
    *,
    reporting_sides: tuple[str, ...],
    world_views: dict[str, SideWorldView],
    current_detection_witnesses: dict[
        str,
        tuple[ObserverDetectionWitness, ...],
    ],
    observer_track_supports: tuple[ObserverTrackSupportState, ...],
    rng_state: dict[str, Any],
    intel_fusion: dict[str, Any],
    scan_counts: DetectionScanCountSnapshot | None,
    receipts: tuple[FogOfWarCycleReceipt, ...] = (),
) -> dict[str, Any]:
    observer_track_supports = _validated_observer_track_support_tuple(
        observer_track_supports,
        field_name="fog-of-war update observer supports",
    )
    fusion_tracks = intel_fusion["tracks"]
    payload = {
        "reporting_sides": list(reporting_sides),
        "world_views": {side: world_view.get_state() for side, world_view in sorted(world_views.items())},
        "contact_fusion_aliases": {
            side: {
                contact_id: (fusion_tracks.get(side, {}).get(contact.track.track_id) is contact.track)
                for contact_id, contact in sorted(world_view.contacts.items())
            }
            for side, world_view in sorted(world_views.items())
        },
        "current_detection_witnesses": {
            side: [witness.get_state() for witness in witnesses]
            for side, witnesses in sorted(current_detection_witnesses.items())
        },
        "observer_track_supports": [
            observer_track_support_state_to_state(support) for support in observer_track_supports
        ],
        "rng_state": rng_state,
        "intel_fusion": _fusion_plan_payload(intel_fusion),
        "receipts": [receipt.to_state() for receipt in receipts],
    }
    if scan_counts is not None:
        payload["scan_counts"] = _scan_count_payload(scan_counts)
    return payload


def _update_plan_fingerprint(**kwargs: Any) -> str:
    encoded = json.dumps(
        _update_plan_payload(**kwargs),
        allow_nan=False,
        default=_restore_plan_json_default,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_payload_fingerprint(value: Any) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        default=_restore_plan_json_default,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _restore_plan_type_name(value: Any) -> str:
    value_type = type(value)
    return f"{value_type.__module__}.{value_type.__qualname__}"


def _restore_plan_structure(
    value: Any,
    *,
    references: dict[int, int],
) -> Any:
    """Describe exact staged types and aliases without normalizing values."""
    type_name = _restore_plan_type_name(value)
    if value is None or type(value) in {bool, bytes, float, int, str}:
        return ["scalar", type_name]
    if type(value) is object:
        return ["opaque-owner-token", type_name]
    if isinstance(value, enum.Enum):
        return ["enum", type_name]
    if isinstance(value, np.generic):
        return ["numpy-scalar", type_name, value.dtype.str]

    identity = id(value)
    prior_reference = references.get(identity)
    if prior_reference is not None:
        return ["alias", prior_reference]
    references[identity] = len(references)

    if isinstance(value, np.ndarray):
        return [
            "ndarray",
            type_name,
            value.dtype.str,
            list(value.shape),
            list(value.strides),
            bool(value.flags.c_contiguous),
            bool(value.flags.f_contiguous),
            bool(value.flags.owndata),
            bool(value.flags.writeable),
            bool(value.flags.aligned),
        ]
    if isinstance(value, dict):
        return [
            "mapping",
            type_name,
            [
                [
                    _restore_plan_structure(
                        key,
                        references=references,
                    ),
                    _restore_plan_structure(
                        item,
                        references=references,
                    ),
                ]
                for key, item in value.items()
            ],
        ]
    if isinstance(value, BaseModel):
        return [
            "pydantic-model",
            type_name,
            [
                [
                    name,
                    _restore_plan_structure(
                        getattr(value, name),
                        references=references,
                    ),
                ]
                for name in type(value).model_fields
            ],
        ]
    if is_dataclass(value):
        return [
            "dataclass",
            type_name,
            [
                [
                    data_field.name,
                    _restore_plan_structure(
                        getattr(value, data_field.name),
                        references=references,
                    ),
                ]
                for data_field in fields(value)
            ],
        ]
    if isinstance(value, tuple) and hasattr(value, "_fields"):
        return [
            "named-tuple",
            type_name,
            [
                _restore_plan_structure(
                    item,
                    references=references,
                )
                for item in value
            ],
        ]
    if isinstance(value, (list, tuple)):
        return [
            "sequence",
            type_name,
            [
                _restore_plan_structure(
                    item,
                    references=references,
                )
                for item in value
            ],
        ]
    if hasattr(value, "__dict__"):
        return [
            "object",
            type_name,
            [
                [
                    name,
                    _restore_plan_structure(
                        item,
                        references=references,
                    ),
                ]
                for name, item in vars(value).items()
            ],
        ]

    slot_names: list[str] = []
    for value_type in type(value).__mro__:
        declared_slots = value_type.__dict__.get("__slots__", ())
        if isinstance(declared_slots, str):
            declared_slots = (declared_slots,)
        slot_names.extend(name for name in declared_slots if name not in {"__dict__", "__weakref__"})
    if slot_names:
        return [
            "slotted-object",
            type_name,
            [
                [
                    name,
                    _restore_plan_structure(
                        getattr(value, name),
                        references=references,
                    ),
                ]
                for name in slot_names
                if hasattr(value, name)
            ],
        ]
    raise TypeError(
        f"Unsupported fog-of-war restore-plan structure {type_name}",
    )


def _restore_plan_structure_fingerprint(
    plan: FogOfWarRestorePlan,
) -> str:
    references: dict[int, int] = {}
    structure = [
        _restore_plan_structure(
            value,
            references=references,
        )
        for value in (
            plan._world_views,
            plan._current_detection_witnesses,
            plan._observer_track_supports,
            plan._rng_state,
            plan._intel_fusion,
            plan._scan_counts,
            plan._cadence_state,
            plan._cadence_plan,
        )
    ]
    encoded = json.dumps(
        structure,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _restore_plan_json_default(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    raise TypeError(
        f"Unsupported fog-of-war restore-plan value {type(value).__name__}",
    )


def _restore_plan_fingerprint(plan: FogOfWarRestorePlan) -> str:
    encoded = json.dumps(
        _restore_plan_payload(plan),
        allow_nan=False,
        default=_restore_plan_json_default,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


# ---------------------------------------------------------------------------
# 12a-7: Data Link / COP configuration
# ---------------------------------------------------------------------------


class DataLinkConfig(BaseModel):
    """Configuration for network-centric COP sharing."""

    enable_cop_sharing: bool = False
    track_degradation_per_hop: float = 0.1
    """Confidence degradation per data link hop (0.0–1.0)."""
    max_track_age_s: float = 60.0
    """Maximum age of a track before it is dropped from COP sharing."""


# ---------------------------------------------------------------------------
# Fog of War Manager
# ---------------------------------------------------------------------------


class FogOfWarManager:
    """Per-side world-view manager — the fog of war.

    Parameters
    ----------
    detection_engine:
        The :class:`DetectionEngine` for sensor checks.
    identification_engine:
        The :class:`IdentificationEngine` for classification.
    state_estimator:
        The :class:`StateEstimator` for Kalman filtering.
    intel_fusion:
        The :class:`IntelFusionEngine` for multi-source fusion.
    deception_engine:
        The :class:`DeceptionEngine` for decoy management.
    rng:
        A ``numpy.random.Generator``.
    """

    def __init__(
        self,
        detection_engine: DetectionEngine | None = None,
        identification_engine: IdentificationEngine | None = None,
        state_estimator: StateEstimator | None = None,
        intel_fusion: IntelFusionEngine | None = None,
        deception_engine: DeceptionEngine | None = None,
        *,
        rng: np.random.Generator,
        data_link_config: DataLinkConfig | None = None,
        cadence_scheduler: TacticalCadenceScheduler | None = None,
    ) -> None:
        self._detection = detection_engine or DetectionEngine(rng=rng)
        self._identification = identification_engine
        self._estimator = state_estimator or StateEstimator(rng=rng)
        self._intel_fusion = intel_fusion or IntelFusionEngine(rng=rng)
        self._deception = deception_engine or DeceptionEngine(rng=rng)
        self._rng = rng
        self._cadence = cadence_scheduler or TacticalCadenceScheduler()
        self._plan_owner_token = object()
        self._update_owner_token = object()
        self._update_generation = 0
        self._active_update_transaction: FogOfWarUpdateTransaction | None = None
        self._update_workspace: _FogOfWarUpdateWorkspace | None = None
        self._active_publication_plan: FogOfWarPublicationPlan | None = None
        self._prepared_update_commit: FogOfWarCommitPlan | None = None
        self._prepared_update_payload: _FogOfWarCommitPayload | None = None
        self._active_witness_clear: FogOfWarWitnessClearPlan | None = None
        self._update_in_progress_sides: set[str] = set()
        self._issued_side_plans: dict[str, FogOfWarSidePlan] = {}
        self._update_transaction_poisoned = False
        self._update_transaction_lock = threading.RLock()
        self._world_views: dict[str, SideWorldView] = {}
        # 12a-7: COP sharing
        self._dl_config = data_link_config or DataLinkConfig()
        # network_name → list of unit_ids
        self._data_link_networks: dict[str, list[str]] = {}
        # unit_id → set of network names
        self._unit_networks: dict[str, set[str]] = {}
        # Successful checks from the most recent update for each side.  This
        # bounded cache is checkpointed for exact continuation and protected
        # because Phase 89 may update sides in parallel.  Each published tuple
        # is canonically ordered.
        self._current_detection_witnesses: dict[
            str,
            tuple[ObserverDetectionWitness, ...],
        ] = {}
        self._observer_track_supports: dict[
            ObserverTrackSupportIdentity,
            ObserverTrackSupportState,
        ] = {}
        self._witness_lock = threading.Lock()

    @property
    def intel_fusion(self) -> IntelFusionEngine:
        """Expose intel fusion engine for SIGINT/ISR track injection."""
        return self._intel_fusion

    @property
    def cadence(self) -> TacticalCadenceScheduler:
        """Expose the manager-owned complete-roster cadence authority."""
        return self._cadence

    @property
    def observer_track_support_process_noise_std_mps2(self) -> float:
        """Return the production estimator noise used for support projection."""
        return float(self._estimator.config.process_noise_std)

    @property
    def observer_track_support_max_position_uncertainty_m(self) -> float:
        """Return the production estimator uncertainty rejection boundary."""
        return float(self._estimator.config.max_covariance_m)

    # ------------------------------------------------------------------
    # World view access
    # ------------------------------------------------------------------

    def get_world_view(self, side: str) -> SideWorldView:
        """Return the world view for *side*, creating if needed."""
        if side not in self._world_views:
            self._world_views[side] = SideWorldView(side=side)
        return self._world_views[side]

    def peek_world_view(self, side: str) -> SideWorldView | None:
        """Return an existing world view without creating simulation state."""
        return self._world_views.get(side)

    def snapshot_side(self, side: str) -> FogOfWarSideSnapshot:
        """Observe stable contact identities without create-on-read mutation."""
        _require_witness_id(side, "fog-of-war snapshot side")
        world_view = self._world_views.get(side)
        if world_view is None:
            return FogOfWarSideSnapshot(
                reporting_side=side,
                present=False,
                identities=(),
            )
        return FogOfWarSideSnapshot(
            reporting_side=side,
            present=True,
            identities=tuple(
                FogOfWarContactIdentity(
                    target_id=target_id,
                    track_id=contact.track.track_id,
                )
                for target_id, contact in sorted(
                    world_view.contacts.items(),
                    key=lambda item: item[0].encode("utf-8"),
                )
            ),
        )

    def get_contact(self, side: str, contact_id: str) -> ContactRecord | None:
        """Return a specific contact record, or None."""
        wv = self._world_views.get(side)
        if wv is None:
            return None
        return wv.contacts.get(contact_id)

    def get_current_detection_witnesses(
        self,
        side: str | None = None,
    ) -> tuple[ObserverDetectionWitness, ...]:
        """Return an immutable snapshot of current-update detection witnesses.

        Passing a side returns only that side's latest update.  Omitting it
        returns the canonical union across all most-recently updated sides.
        Checkpoints persist this bounded cache; the next side update replaces
        that side's tuple rather than extending a detection history.
        """
        return copy.deepcopy(
            self._current_detection_witnesses_for_owner(side),
        )

    def _current_detection_witnesses_for_owner(
        self,
        side: str | None = None,
    ) -> tuple[ObserverDetectionWitness, ...]:
        """Return exact live witnesses for trusted manager-internal use."""
        with self._witness_lock:
            if side is not None:
                return self._current_detection_witnesses.get(side, ())
            witnesses = [
                witness for side_witnesses in self._current_detection_witnesses.values() for witness in side_witnesses
            ]
        return tuple(sorted(witnesses, key=self._witness_sort_key))

    def get_observer_track_supports(
        self,
        side: str | None = None,
    ) -> tuple[ObserverTrackSupportState, ...]:
        """Return canonical observer-owned support, optionally for one side."""
        return copy.deepcopy(
            self._observer_track_supports_for_owner(side),
        )

    def _observer_track_supports_for_owner(
        self,
        side: str | None = None,
    ) -> tuple[ObserverTrackSupportState, ...]:
        """Return exact live support for trusted manager-internal use."""
        if side is not None:
            _require_witness_id(side, "observer track support side")
        with self._witness_lock:
            supports = tuple(self._observer_track_supports.values())
        if side is not None:
            supports = tuple(
                support for support in supports if support.identity.attachment_identity.reporting_side == side
            )
        return tuple(
            sorted(
                supports,
                key=lambda support: support.identity.sort_key(),
            )
        )

    def clear_current_detection_witnesses(
        self,
        side: str | None = None,
    ) -> None:
        """Clear bounded current witness evidence for one side or all sides."""
        with self._witness_lock:
            if side is None:
                self._current_detection_witnesses.clear()
            else:
                self._current_detection_witnesses.pop(side, None)

    @staticmethod
    def _witness_clear_fingerprint(
        witnesses: Mapping[str, tuple[ObserverDetectionWitness, ...]],
        observer_track_supports: tuple[ObserverTrackSupportState, ...],
    ) -> str:
        observer_track_supports = _validated_observer_track_support_tuple(
            observer_track_supports,
            field_name="fog-of-war witness-clear observer supports",
        )
        return _canonical_payload_fingerprint(
            {
                "current_detection_witnesses": {
                    side: [witness.get_state() for witness in side_witnesses]
                    for side, side_witnesses in sorted(witnesses.items())
                },
                "observer_track_supports": [
                    observer_track_support_state_to_state(support) for support in observer_track_supports
                ],
            },
        )

    def prepare_witness_clear(self) -> FogOfWarWitnessClearPlan:
        """Stage a disabled-FOW witness clear without changing live state."""
        with self._update_transaction_lock:
            if self._update_transaction_poisoned:
                raise RuntimeError("fog-of-war update transaction owner is poisoned")
            if self._active_update_transaction is not None:
                raise RuntimeError(
                    "cannot stage witness clear during a fog-of-war update",
                )
            if self._active_witness_clear is not None:
                raise RuntimeError("a fog-of-war witness clear is already active")
            with self._witness_lock:
                baseline, supports = copy.deepcopy(
                    (
                        self._current_detection_witnesses,
                        tuple(
                            sorted(
                                self._observer_track_supports.values(),
                                key=lambda support: support.identity.sort_key(),
                            )
                        ),
                    ),
                )
            plan = FogOfWarWitnessClearPlan(
                _baseline=baseline,
                _observer_track_supports=supports,
                _owner_token=self._update_owner_token,
                _fingerprint=self._witness_clear_fingerprint(
                    baseline,
                    supports,
                ),
            )
            self._active_witness_clear = plan
            return plan

    def validate_prepared_witness_clear(
        self,
        plan: FogOfWarWitnessClearPlan,
    ) -> None:
        """Reject foreign, stale, mutated, or concurrently changed clears."""
        if type(plan) is not FogOfWarWitnessClearPlan:
            raise TypeError("plan must be a FogOfWarWitnessClearPlan")
        with self._update_transaction_lock:
            if plan._owner_token is not self._update_owner_token or self._active_witness_clear is not plan:
                raise ValueError("fog-of-war witness clear is foreign or stale")
            if self._active_update_transaction is not None:
                raise RuntimeError(
                    "cannot commit witness clear during a fog-of-war update",
                )
            if (
                self._witness_clear_fingerprint(
                    plan._baseline,
                    plan._observer_track_supports,
                )
                != plan._fingerprint
            ):
                raise ValueError("fog-of-war witness clear was mutated")
            with self._witness_lock:
                live_fingerprint = self._witness_clear_fingerprint(
                    self._current_detection_witnesses,
                    tuple(
                        sorted(
                            self._observer_track_supports.values(),
                            key=lambda support: support.identity.sort_key(),
                        )
                    ),
                )
            if live_fingerprint != plan._fingerprint:
                raise RuntimeError(
                    "fog-of-war witnesses changed before prepared clear",
                )

    def _commit_prevalidated_witness_clear(
        self,
        plan: FogOfWarWitnessClearPlan,
    ) -> None:
        """Publish a prevalidated witness clear with one bounded swap."""
        with self._update_transaction_lock, self._witness_lock:
            self._current_detection_witnesses = {}
            self._observer_track_supports = {}
            self._active_witness_clear = None

    def commit_prepared_witness_clear(
        self,
        plan: FogOfWarWitnessClearPlan,
    ) -> None:
        """Validate and publish a standalone disabled-FOW witness clear."""
        self.validate_prepared_witness_clear(plan)
        self._commit_prevalidated_witness_clear(plan)

    def abort_witness_clear(self, plan: FogOfWarWitnessClearPlan) -> None:
        """Discard one active disabled-FOW witness clear plan."""
        if type(plan) is not FogOfWarWitnessClearPlan:
            raise TypeError("plan must be a FogOfWarWitnessClearPlan")
        with self._update_transaction_lock:
            if plan._owner_token is not self._update_owner_token or self._active_witness_clear is not plan:
                raise ValueError("fog-of-war witness clear is foreign or stale")
            self._active_witness_clear = None

    @staticmethod
    def _witness_sort_key(
        witness: ObserverDetectionWitness,
    ) -> tuple[str, str, str, int, str, str]:
        return (
            witness.side,
            witness.observer_unit_id,
            witness.target_id,
            witness.source_equipment_index,
            witness.sensor_id,
            witness.modeled_role,
        )

    @staticmethod
    def _observer_sensor_scans(
        own: dict[str, Any],
    ) -> tuple[_ObserverSensorScan, ...]:
        """Resolve typed attachments or the compatibility sensor projection."""
        attachments = own.get("sensor_attachments")
        if attachments is None:
            return tuple(_ObserverSensorScan(sensor=sensor) for sensor in own.get("sensors", ()))

        scans: list[_ObserverSensorScan] = []
        identities: set[tuple[int, str]] = set()
        for attachment in attachments:
            sensor = getattr(attachment, "sensor", None)
            if not isinstance(sensor, SensorInstance):
                raise TypeError(
                    "sensor attachment must expose a SensorInstance as sensor",
                )
            source_index = getattr(
                attachment,
                "source_equipment_index",
                None,
            )
            if isinstance(source_index, bool) or not isinstance(source_index, int) or source_index < 0:
                raise ValueError(
                    "sensor attachment source_equipment_index must be a non-negative int",
                )
            modeled_role = getattr(attachment, "modeled_role", None)
            if not isinstance(modeled_role, enum.Enum):
                raise TypeError(
                    "sensor attachment modeled_role must be a typed enum",
                )
            role_value = modeled_role.value
            _require_witness_id(role_value, "sensor attachment modeled_role")
            attachment_sensor_id = getattr(
                attachment,
                "sensor_id",
                sensor.sensor_id,
            )
            if attachment_sensor_id != sensor.sensor_id:
                raise ValueError(
                    "sensor attachment sensor_id disagrees with its live sensor",
                )
            identity = (source_index, sensor.sensor_id)
            if identity in identities:
                raise ValueError(
                    f"duplicate sensor attachment identity {identity!r} for one observer",
                )
            identities.add(identity)
            scans.append(
                _ObserverSensorScan(
                    sensor=sensor,
                    source_equipment_index=source_index,
                    modeled_role=role_value,
                ),
            )

        if "sensors" in own:
            compatibility_sensors = tuple(own["sensors"])
            attachment_sensors = tuple(scan.sensor for scan in scans)
            if len(compatibility_sensors) != len(attachment_sensors) or any(
                projected is not attached
                for projected, attached in zip(
                    compatibility_sensors,
                    attachment_sensors,
                )
            ):
                raise ValueError(
                    "own-unit sensors must be the exact sensor_attachments projection",
                )
        return tuple(scans)

    @staticmethod
    def _vectorized_strtree_candidate_indices(
        target_tree: STRtree,
        staged_observers: list[_StagedObserver],
    ) -> tuple[tuple[int, ...], ...] | None:
        """Batch the ordinary finite broad phase without changing its order.

        A ``None`` result keeps malformed or non-standard spatial inputs on
        the scalar compatibility path, where their established exception and
        indexed-RNG ordering remains unchanged.
        """
        candidate_indices: list[list[int]] = [[] for _ in staged_observers]
        active_observer_indices: list[int] = []
        minimum_eastings: list[float] = []
        minimum_northings: list[float] = []
        maximum_eastings: list[float] = []
        maximum_northings: list[float] = []

        def finite_float(value: object) -> float | None:
            if isinstance(value, bool) or not isinstance(
                value,
                (int, float),
            ):
                return None
            try:
                normalized = float(value)
            except (OverflowError, TypeError, ValueError):
                return None
            return normalized if math.isfinite(normalized) else None

        for observer_index, (own, _, _, sensor_scans) in enumerate(
            staged_observers,
        ):
            observer_position = own.get("position")
            if type(observer_position) is not Position:
                return None
            easting = finite_float(observer_position.easting)
            northing = finite_float(observer_position.northing)
            if easting is None or northing is None:
                return None
            try:
                maximum_range = max(
                    (
                        bound_scan.scan.sensor.effective_range
                        for bound_scan in sensor_scans
                        if bound_scan.scan.sensor.operational
                    ),
                    default=0.0,
                )
            except (AttributeError, OverflowError, TypeError, ValueError):
                return None
            reach = finite_float(maximum_range)
            if reach is None:
                return None
            if reach <= 0.0:
                continue
            bounds = (
                easting - reach,
                northing - reach,
                easting + reach,
                northing + reach,
            )
            if not all(math.isfinite(value) for value in bounds):
                return None
            active_observer_indices.append(observer_index)
            minimum_eastings.append(bounds[0])
            minimum_northings.append(bounds[1])
            maximum_eastings.append(bounds[2])
            maximum_northings.append(bounds[3])

        if not active_observer_indices:
            return tuple(tuple() for _ in staged_observers)

        query_boxes = vectorized_box(
            np.asarray(minimum_eastings, dtype=np.float64),
            np.asarray(minimum_northings, dtype=np.float64),
            np.asarray(maximum_eastings, dtype=np.float64),
            np.asarray(maximum_northings, dtype=np.float64),
        )
        query_pairs = target_tree.query(query_boxes)
        for active_index, target_index in zip(
            query_pairs[0],
            query_pairs[1],
            strict=True,
        ):
            observer_index = active_observer_indices[int(active_index)]
            candidate_indices[observer_index].append(int(target_index))
        return tuple(tuple(sorted(indices)) for indices in candidate_indices)

    # ------------------------------------------------------------------
    # Phase 69c: Deception passthrough API
    # ------------------------------------------------------------------

    def deploy_decoy(
        self,
        position: Position,
        deception_type: DeceptionType | int = 4,
        effectiveness: float = 1.0,
        signature: "SignatureProfile | None" = None,
    ) -> Decoy:
        """Deploy a decoy via the internal deception engine."""
        if isinstance(deception_type, int):
            deception_type = DeceptionType(deception_type)
        return self._deception.deploy_decoy(
            position,
            deception_type,
            effectiveness,
            signature,
        )

    def get_active_decoys(self) -> list[Decoy]:
        """Return all currently active decoys."""
        return self._deception.active_decoys()

    def update_decoys(self, dt: float) -> None:
        """Degrade all active decoys over time."""
        self._deception.update_decoys(dt)

    # ------------------------------------------------------------------
    # Phase 118: isolated complete-side update transaction
    # ------------------------------------------------------------------

    @staticmethod
    def _canonical_reporting_sides(
        reporting_sides: tuple[str, ...],
    ) -> tuple[str, ...]:
        if type(reporting_sides) is not tuple or not reporting_sides:
            raise ValueError("reporting_sides must be a non-empty immutable tuple")
        for side in reporting_sides:
            _require_witness_id(side, "reporting side")
        if len(set(reporting_sides)) != len(reporting_sides):
            raise ValueError("reporting_sides contains a duplicate")
        if reporting_sides != tuple(sorted(reporting_sides, key=lambda side: side.encode("utf-8"))):
            raise ValueError("reporting_sides must be in ascending UTF-8 byte order")
        return reporting_sides

    @staticmethod
    def _validate_update_aliases(
        world_views: dict[str, SideWorldView],
        intel_fusion: dict[str, Any],
    ) -> None:
        tracks = intel_fusion["tracks"]
        for side, world_view in world_views.items():
            for contact in world_view.contacts.values():
                if tracks.get(side, {}).get(contact.track.track_id) is not contact.track:
                    raise ValueError(
                        "staged fog-of-war contact must alias its fusion-owned track",
                    )

    def _validate_fusion_side_delta(
        self,
        delta: _FogOfWarFusionSideDelta,
        *,
        expected_side: str,
    ) -> None:
        """Validate private side-local fusion topology without restaging tracks."""
        if type(delta) is not _FogOfWarFusionSideDelta:
            raise TypeError("fusion delta must be a _FogOfWarFusionSideDelta")
        if delta.reporting_side != expected_side:
            raise ValueError("fusion delta reporting side is inconsistent")
        if type(delta.track_counter) is not int or delta.track_counter < 0:
            raise ValueError("fusion delta track counter must be a non-negative integer")
        if delta.fow_track_counter is not None and (
            type(delta.fow_track_counter) is not int or delta.fow_track_counter <= 0
        ):
            raise ValueError("fusion delta FOW track counter must be positive")
        if type(delta.tracks) is not dict:
            raise TypeError("fusion delta tracks must be a mapping")

        fow_ordinals: set[int] = set()
        for track_id, track in sorted(delta.tracks.items()):
            if type(track_id) is not str or not track_id:
                raise ValueError("fusion delta track ID must be non-empty text")
            if type(track) is not Track:
                raise TypeError("fusion delta contains a non-Track value")
            if track.track_id != track_id or track.side != expected_side:
                raise ValueError(
                    "fusion delta track topology disagrees with its owner",
                )
            if track_id.startswith("track-") and track_id[6:].isdigit():
                sequence = int(track_id[6:])
                if sequence <= 0 or sequence > delta.track_counter:
                    raise ValueError(
                        "fusion delta automatic track exceeds the global track counter",
                    )
                continue
            validated = validate_fow_track_id(track_id, "fusion delta FOW track ID")
            fow_ordinals.add(int(validated.rsplit("-", maxsplit=1)[1]))

        if fow_ordinals:
            if delta.fow_track_counter != max(fow_ordinals):
                raise ValueError(
                    "fusion delta FOW track counter disagrees with issued tracks",
                )
        elif delta.fow_track_counter is not None:
            raise ValueError("fusion delta FOW track counter has no issued tracks")

    def _stage_live_update_baseline(
        self,
        reporting_sides: tuple[str, ...],
    ) -> tuple[
        dict[str, SideWorldView],
        dict[str, tuple[ObserverDetectionWitness, ...]],
        tuple[ObserverTrackSupportState, ...],
        dict[str, Any],
        dict[str, Any],
        dict[Any, int],
    ]:
        self.validate_internal_bindings()
        self.validate_live_contact_bindings()
        rng_state = copy.deepcopy(self._rng.bit_generator.state)
        with self._intel_fusion._track_lock:
            fusion_state = self._intel_fusion.get_state()
            intel_fusion = self._intel_fusion.stage_state(
                fusion_state,
                authoritative_rng_state=rng_state,
            )
            world_view_copy_memo = self._world_view_copy_memo(
                intel_fusion,
            )
            world_views = copy.deepcopy(
                self._world_views,
                world_view_copy_memo,
            )
        with self._witness_lock:
            witnesses = self._copy_detection_witness_map(
                self._current_detection_witnesses,
            )
            observer_track_supports = tuple(
                sorted(
                    self._observer_track_supports.values(),
                    key=lambda support: support.identity.sort_key(),
                )
            )
        scan_count_values = self._detection._snapshot_scan_count_values()
        if self._rng.bit_generator.state != rng_state:
            raise RuntimeError("fog-of-war baseline staging advanced conventional RNG")
        self._validate_update_aliases(world_views, intel_fusion)
        return (
            world_views,
            witnesses,
            observer_track_supports,
            rng_state,
            intel_fusion,
            scan_count_values,
        )

    def _world_view_copy_memo(
        self,
        intel_fusion: dict[str, Any],
    ) -> dict[int, Track]:
        """Bind live contact tracks to their already-detached staged copies."""
        staged_tracks = intel_fusion.get("tracks")
        if type(staged_tracks) is not dict:
            raise ValueError("staged fog-of-war fusion tracks are invalid")
        memo: dict[int, Track] = {}
        for side, world_view in self._world_views.items():
            if world_view.side != side:
                raise ValueError(
                    "fog-of-war world-view owner changed during staging",
                )
            live_side_tracks = self._intel_fusion._tracks.get(side, {})
            staged_side_tracks = staged_tracks.get(side, {})
            if type(staged_side_tracks) is not dict:
                raise ValueError(
                    "staged fog-of-war fusion side tracks are invalid",
                )
            for contact in world_view.contacts.values():
                live_track = live_side_tracks.get(contact.track.track_id)
                staged_track = staged_side_tracks.get(contact.track.track_id)
                if (
                    live_track is not contact.track
                    or type(staged_track) is not Track
                    or staged_track.track_id != contact.track.track_id
                    or staged_track.side != side
                    or staged_track.get_state() != live_track.get_state()
                ):
                    raise ValueError(
                        "fog-of-war contact cannot bind to its staged fusion track",
                    )
                prior = memo.get(id(live_track))
                if prior is not None and prior is not staged_track:
                    raise ValueError(
                        "fog-of-war live track maps to multiple staged tracks",
                    )
                memo[id(live_track)] = staged_track
        return memo

    @staticmethod
    def _copy_detection_witness_map(
        witnesses: dict[str, tuple[ObserverDetectionWitness, ...]],
    ) -> dict[str, tuple[ObserverDetectionWitness, ...]]:
        """Detach frozen scalar-only witnesses without recursive graph work."""
        memo: dict[int, Any] = {}
        return {
            copy.deepcopy(side, memo): tuple(copy.deepcopy(witness, memo) for witness in side_witnesses)
            for side, side_witnesses in witnesses.items()
        }

    def _bind_update_cadence_plan(
        self,
        workspace: _FogOfWarUpdateWorkspace,
        cadence_plan: TacticalCadencePlan,
    ) -> None:
        """Bind one active cadence authority for all isolated side workers."""
        binding = self._cadence._active_interval_binding_for_owner(
            cadence_plan,
        )
        with self._update_transaction_lock:
            if self._update_workspace is not workspace:
                raise ValueError("fog-of-war update transaction workspace is stale")
            if workspace.cadence_binding is None:
                workspace.cadence_binding = binding
            elif workspace.cadence_binding is not binding:
                raise ValueError(
                    "fog-of-war update cadence plan is foreign or stale",
                )

    @staticmethod
    def _workspace_mapping_preview(
        workspace: _FogOfWarUpdateWorkspace,
        field_name: str,
    ) -> _DefensiveMappingPreview:
        return _DefensiveMappingPreview(
            lambda: copy.deepcopy(getattr(workspace, field_name)),
        )

    @staticmethod
    def _scan_count_values_binding(
        values: dict[Any, int],
    ) -> _FOWScanCountValuesBinding:
        """Bind raw mapping order and exact key objects after canonical staging."""
        if type(values) is not dict:
            raise ValueError("fog-of-war scan-count values have invalid topology")
        return _FOWScanCountValuesBinding(
            keys=tuple(values),
            counts=tuple(values.values()),
            exact_builtin=all(
                DetectionEngine._raw_scan_count_is_exact_builtin(key, count) for key, count in values.items()
            ),
        )

    @staticmethod
    def _validate_scan_count_values_binding(
        values: dict[Any, int],
        binding: _FOWScanCountValuesBinding,
        *,
        field_name: str,
    ) -> None:
        """Reject raw counter replacement without rebuilding public entries."""
        if (
            type(values) is not dict
            or type(binding) is not _FOWScanCountValuesBinding
            or len(values) != len(binding.keys)
            or len(values) != len(binding.counts)
        ):
            raise ValueError(f"{field_name} scan counts changed")
        for (current_key, current_count), expected_key, expected_count in zip(
            values.items(),
            binding.keys,
            binding.counts,
            strict=True,
        ):
            if (
                current_key is not expected_key
                or type(current_count) is not type(expected_count)
                or current_count != expected_count
                or not DetectionEngine._raw_scan_count_is_exact_builtin(
                    current_key,
                    current_count,
                )
            ):
                raise ValueError(f"{field_name} scan counts changed")

    def _validate_scan_count_snapshot_values(
        self,
        snapshot: DetectionScanCountSnapshot,
        values: dict[Any, int],
        *,
        field_name: str,
        verify_snapshot_fingerprint: bool,
    ) -> None:
        """Require one canonical snapshot to describe exact raw count values."""
        if type(snapshot) is not DetectionScanCountSnapshot or type(values) is not dict:
            raise ValueError(f"{field_name} scan counts have invalid private topology")
        try:
            for key, count in values.items():
                self._detection._validate_raw_scan_count(key, count)
            entries = snapshot.entries
            fingerprint_changed = verify_snapshot_fingerprint and (
                self._detection._scan_count_fingerprint(entries) != snapshot._fingerprint
            )
            if fingerprint_changed or len(entries) != len(values):
                raise ValueError
            missing = object()
            for entry in entries:
                count = values.get(
                    self._detection._scan_count_key(entry),
                    missing,
                )
                if count is missing or type(count) is not type(entry.count) or count != entry.count:
                    raise ValueError
        except (AttributeError, TypeError, UnicodeError, ValueError) as exc:
            raise ValueError(f"{field_name} scan counts changed") from exc

    @staticmethod
    def _validate_mapping_preview(
        value: object,
        expected: _DefensiveMappingPreview,
        *,
        field_name: str,
    ) -> None:
        if type(value) is not _DefensiveMappingPreview or value is not expected:
            raise ValueError(f"{field_name} handle binding was mutated")
        if not expected.pristine:
            raise ValueError(f"{field_name} diagnostic preview was mutated")

    @staticmethod
    def _retire_update_previews(
        workspace: _FogOfWarUpdateWorkspace,
    ) -> None:
        """Sever every lazy diagnostic callback before workspace release."""
        outcome_source = workspace.outcome_source
        if outcome_source is not None:
            outcome_source.retire()
        transaction_bindings = workspace.transaction_bindings
        for index in (1, 2, 4, 5, 6):
            preview = transaction_bindings[index]
            if type(preview) is _DefensiveMappingPreview:
                preview.retire()
        for side_workspace in workspace.side_workspaces.values():
            bindings = side_workspace.handle_bindings
            world_view_preview = bindings[1]
            tracks_preview = bindings[5]
            if type(world_view_preview) is _DefensiveWorldViewPreview:
                world_view_preview.retire()
            if type(tracks_preview) is _DefensiveMappingPreview:
                tracks_preview.retire()
        publication_bindings = workspace.publication_bindings
        if publication_bindings:
            for index in (3, 4, 6):
                preview = publication_bindings[index]
                if type(preview) is _DefensiveMappingPreview:
                    preview.retire()

    def begin_update_transaction(
        self,
        reporting_sides: tuple[str, ...],
    ) -> FogOfWarUpdateTransaction:
        """Capture an immutable baseline before any outer FOW owner stages."""
        sides = self._canonical_reporting_sides(reporting_sides)
        with self._update_transaction_lock:
            if self._update_transaction_poisoned:
                raise RuntimeError("fog-of-war update transaction owner is poisoned")
            if self._active_update_transaction is not None:
                raise RuntimeError("a fog-of-war update transaction is already active")
            if self._active_witness_clear is not None:
                raise RuntimeError("a fog-of-war witness clear is already active")
            (
                world_views,
                witnesses,
                observer_track_supports,
                rng_state,
                intel_fusion,
                scan_count_values,
            ) = self._stage_live_update_baseline(sides)
            self._update_generation += 1
            generation = self._update_generation
            workspace = _FogOfWarUpdateWorkspace(
                generation=generation,
                reporting_sides=sides,
                world_views=world_views,
                current_detection_witnesses=witnesses,
                observer_track_supports=observer_track_supports,
                rng_state=rng_state,
                intel_fusion=intel_fusion,
                baseline_scan_count_values=scan_count_values,
                start_live_fingerprint=_update_plan_fingerprint(
                    reporting_sides=sides,
                    world_views=world_views,
                    current_detection_witnesses=witnesses,
                    observer_track_supports=observer_track_supports,
                    rng_state=rng_state,
                    intel_fusion=intel_fusion,
                    scan_counts=None,
                ),
            )
            outcome_source = _FogOfWarOutcomeSource(workspace)
            workspace.outcome_source = outcome_source
            world_views_preview = self._workspace_mapping_preview(
                workspace,
                "world_views",
            )
            witnesses_preview = self._workspace_mapping_preview(
                workspace,
                "current_detection_witnesses",
            )
            supports_preview = copy.deepcopy(observer_track_supports)
            rng_preview = self._workspace_mapping_preview(workspace, "rng_state")
            fusion_preview = self._workspace_mapping_preview(
                workspace,
                "intel_fusion",
            )
            scan_counts_preview = self._workspace_mapping_preview(
                workspace,
                "baseline_scan_count_values",
            )
            handle_seal = f"fog-of-war-update:{generation}"
            transaction = FogOfWarUpdateTransaction(
                reporting_sides=sides,
                _world_views=world_views_preview,
                _current_detection_witnesses=witnesses_preview,
                _observer_track_supports=supports_preview,
                _rng_state=rng_preview,
                _intel_fusion=fusion_preview,
                _scan_counts=scan_counts_preview,
                _owner_token=self._update_owner_token,
                _generation=generation,
                _fingerprint=handle_seal,
            )
            workspace.transaction = transaction
            workspace.transaction_bindings = (
                sides,
                world_views_preview,
                witnesses_preview,
                supports_preview,
                rng_preview,
                fusion_preview,
                scan_counts_preview,
                handle_seal,
            )
            self._active_update_transaction = transaction
            self._update_workspace = workspace
            self._active_publication_plan = None
            self._prepared_update_commit = None
            self._prepared_update_payload = None
            self._update_in_progress_sides.clear()
            self._issued_side_plans.clear()
            return transaction

    def _validate_update_transaction(
        self,
        transaction: FogOfWarUpdateTransaction,
    ) -> _FogOfWarUpdateWorkspace:
        if type(transaction) is not FogOfWarUpdateTransaction:
            raise TypeError("transaction must be a FogOfWarUpdateTransaction")
        if transaction._owner_token is not self._update_owner_token:
            raise ValueError("fog-of-war update transaction belongs to another manager")
        if self._active_update_transaction is not transaction:
            raise ValueError("fog-of-war update transaction is stale or inactive")
        workspace = self._update_workspace
        if workspace is None or workspace.transaction is not transaction:
            raise ValueError("fog-of-war update transaction workspace is stale")
        (
            reporting_sides,
            world_views_preview,
            witnesses_preview,
            supports_preview,
            rng_preview,
            fusion_preview,
            scan_counts_preview,
            handle_seal,
        ) = workspace.transaction_bindings
        if (
            transaction.reporting_sides is not reporting_sides
            or type(transaction._generation) is not int
            or transaction._generation is not workspace.generation
            or transaction._fingerprint is not handle_seal
        ):
            raise ValueError("fog-of-war update transaction metadata was mutated")
        self._validate_mapping_preview(
            transaction._world_views,
            world_views_preview,
            field_name="fog-of-war transaction world views",
        )
        self._validate_mapping_preview(
            transaction._current_detection_witnesses,
            witnesses_preview,
            field_name="fog-of-war transaction witnesses",
        )
        if (
            type(transaction._observer_track_supports) is not tuple
            or transaction._observer_track_supports is not supports_preview
        ):
            raise ValueError(
                "fog-of-war transaction observer supports must be an exact ObserverTrackSupportState tuple",
            )
        self._validate_mapping_preview(
            transaction._rng_state,
            rng_preview,
            field_name="fog-of-war transaction RNG state",
        )
        self._validate_mapping_preview(
            transaction._intel_fusion,
            fusion_preview,
            field_name="fog-of-war transaction fusion state",
        )
        self._validate_mapping_preview(
            transaction._scan_counts,
            scan_counts_preview,
            field_name="fog-of-war transaction scan counts",
        )
        return workspace

    def _claim_update_side(
        self,
        transaction: FogOfWarUpdateTransaction,
        side: str,
    ) -> _FogOfWarUpdateWorkspace:
        with self._update_transaction_lock:
            workspace = self._validate_update_transaction(transaction)
            if self._update_transaction_poisoned:
                raise RuntimeError("fog-of-war update transaction owner is poisoned")
            if side not in transaction.reporting_sides:
                raise ValueError("reporting side is absent from the update transaction")
            if side in self._update_in_progress_sides or side in self._issued_side_plans:
                raise ValueError("reporting side was already staged in this transaction")
            self._update_in_progress_sides.add(side)
            return workspace

    def _register_side_plan(
        self,
        workspace: _FogOfWarUpdateWorkspace,
        side_workspace: _FogOfWarSideWorkspace,
    ) -> None:
        with self._update_transaction_lock:
            plan = side_workspace.plan
            transaction = plan._transaction
            expected_side = side_workspace.handle_bindings[-1]
            if (
                transaction._owner_token is not self._update_owner_token
                or self._active_update_transaction is not transaction
                or self._update_workspace is not workspace
                or type(plan._generation) is not int
                or plan._generation is not workspace.generation
                or type(plan.reporting_side) is not str
                or plan.reporting_side is not expected_side
            ):
                raise ValueError("fog-of-war side plan transaction is foreign or stale")
            if plan.reporting_side not in self._update_in_progress_sides:
                raise ValueError("fog-of-war side plan has no active staging claim")
            self._update_in_progress_sides.remove(plan.reporting_side)
            workspace.world_views[plan.reporting_side] = side_workspace.world_view
            workspace.intel_fusion["tracks"][plan.reporting_side] = side_workspace.fusion_delta.tracks
            self._issued_side_plans[plan.reporting_side] = plan
            workspace.side_workspaces[plan.reporting_side] = side_workspace

    def _poison_update_transaction(
        self,
        transaction: FogOfWarUpdateTransaction,
    ) -> None:
        with self._update_transaction_lock:
            if transaction._owner_token is not self._update_owner_token:
                raise ValueError("fog-of-war update transaction belongs to another manager")
            workspace = self._update_workspace
            if (
                self._active_update_transaction is not transaction
                or workspace is None
                or workspace.transaction is not transaction
            ):
                if (
                    self._update_transaction_poisoned
                    and self._active_update_transaction is None
                    and workspace is None
                    and type(transaction._generation) is int
                    and transaction._generation is self._update_generation
                ):
                    return
                raise ValueError("fog-of-war update transaction is stale or inactive")
            self._retire_update_previews(workspace)
            self._active_update_transaction = None
            self._update_workspace = None
            self._active_publication_plan = None
            self._prepared_update_commit = None
            self._prepared_update_payload = None
            self._update_in_progress_sides.clear()
            self._issued_side_plans.clear()
            self._update_transaction_poisoned = True

    def abort_update_transaction(
        self,
        transaction: FogOfWarUpdateTransaction,
    ) -> None:
        """Discard isolated plans and poison incomplete evidence capture."""
        if type(transaction) is not FogOfWarUpdateTransaction:
            raise TypeError("transaction must be a FogOfWarUpdateTransaction")
        self._poison_update_transaction(transaction)

    # ------------------------------------------------------------------
    # Update cycle
    # ------------------------------------------------------------------

    def update_with_receipt(
        self,
        side: str,
        own_units: list[dict[str, Any]],
        enemy_units: list[dict[str, Any]],
        dt: float,
        *,
        transaction: FogOfWarUpdateTransaction,
        cadence_plan: TacticalCadencePlan,
        indexed_rng: FOWIndexedSideHandle,
        lod_tiers: Mapping[TacticalObserverIdentity, FogOfWarLodTier],
        current_time: float = 0.0,
        decoys: list[Decoy] | None = None,
        detection_culling: bool = True,
        soa_selection: bool = False,
        current_tick: int = 0,
        visibility_m: float = 10000.0,
        illumination_lux: float = 100.0,
        thermal_contrast: float = 1.0,
        ambient_noise_db: float = 70.0,
        atmospheric_atten_db_per_km: float = 0.01,
        transmission_loss: float | None = None,
        jam_snr_penalty_db: float = 0.0,
    ) -> FogOfWarSidePlan:
        """Stage one reporting side against an isolated transaction baseline."""
        _require_witness_id(side, "fog-of-war side")
        workspace = self._claim_update_side(transaction, side)
        try:
            self._bind_update_cadence_plan(workspace, cadence_plan)
            staging_rng = copy.deepcopy(self._rng)
            staging_rng.bit_generator.state = copy.deepcopy(workspace.rng_state)
            world_view = workspace.world_views.setdefault(
                side,
                SideWorldView(side=side),
            )
            world_views = {side: world_view}
            side_tracks = workspace.intel_fusion["tracks"].setdefault(side, {})
            side_fow_counter = workspace.intel_fusion["fow_track_counters"].get(
                side,
            )
            fusion_delta = _FogOfWarFusionSideDelta(
                reporting_side=side,
                track_counter=workspace.intel_fusion["track_counter"],
                fow_track_counter=side_fow_counter,
                tracks=side_tracks,
            )
            estimator = StateEstimator(
                rng=staging_rng,
                config=self._estimator.config.model_copy(deep=True),
            )
            fusion = IntelFusionEngine(
                state_estimator=estimator,
                rng=staging_rng,
            )
            fusion._track_counter = fusion_delta.track_counter
            fusion._tracks = {side: side_tracks}
            fusion._fow_track_counters = {} if side_fow_counter is None else {side: side_fow_counter}
            side_scan_count_values = {
                key: count
                for key, count in workspace.baseline_scan_count_values.items()
                if len(key) == 5 and key[0] == side
            }
            detection = self._detection._fork_scan_count_values(
                side_scan_count_values,
                rng=staging_rng,
            )
            staging = FogOfWarManager(
                detection_engine=detection,
                identification_engine=(IdentificationEngine(staging_rng) if self._identification is not None else None),
                state_estimator=estimator,
                intel_fusion=fusion,
                deception_engine=DeceptionEngine(rng=staging_rng),
                rng=staging_rng,
            )
            staging._world_views = world_views
            with staging._witness_lock:
                side_witnesses = workspace.current_detection_witnesses.get(side)
                staging._current_detection_witnesses = {} if side_witnesses is None else {side: side_witnesses}
                staging._observer_track_supports = {
                    support.identity: support
                    for support in workspace.observer_track_supports
                    if support.identity.attachment_identity.reporting_side == side
                }
            staging.validate_live_contact_bindings()

            outcome = staging._execute_update_with_receipt(
                side,
                own_units,
                enemy_units,
                dt,
                cadence_plan=cadence_plan,
                indexed_rng=indexed_rng,
                lod_tiers=lod_tiers,
                current_time=current_time,
                decoys=decoys,
                detection_culling=detection_culling,
                soa_selection=soa_selection,
                current_tick=current_tick,
                visibility_m=visibility_m,
                illumination_lux=illumination_lux,
                thermal_contrast=thermal_contrast,
                ambient_noise_db=ambient_noise_db,
                atmospheric_atten_db_per_km=(atmospheric_atten_db_per_km),
                transmission_loss=transmission_loss,
                jam_snr_penalty_db=jam_snr_penalty_db,
            )
            if staging_rng.bit_generator.state != workspace.rng_state:
                raise RuntimeError(
                    "receipt-bearing fog-of-war advanced conventional RNG",
                )
            if (
                set(fusion._tracks) != {side}
                or not set(fusion._fow_track_counters) <= {side}
                or fusion._track_counter != fusion_delta.track_counter
                or fusion._satellite_passes
                or fusion._delivery_receipts.count
                or fusion._imint_target_tracks
            ):
                raise RuntimeError(
                    "receipt-bearing fog-of-war escaped its side-local fusion boundary",
                )
            post_fusion_delta = _FogOfWarFusionSideDelta(
                reporting_side=side,
                track_counter=fusion._track_counter,
                fow_track_counter=fusion._fow_track_counters.get(side),
                tracks=fusion._tracks[side],
            )
            world_view = outcome.world_view
            witnesses = staging._current_detection_witnesses_for_owner(side)
            observer_track_supports = staging._observer_track_supports_for_owner(
                side,
            )
            with staging._detection._scan_count_lock:
                scan_count_values = dict(staging._detection._scan_counts)
            if any(
                type(key) is not tuple or len(key) != 5 or key[0] != side or type(count) is not int or count <= 0
                for key, count in scan_count_values.items()
            ):
                raise RuntimeError(
                    "receipt-bearing fog-of-war produced a foreign-side scan count",
                )
            authoritative_receipt = outcome.receipt
            (
                public_receipt,
                public_witnesses,
                public_supports,
            ) = copy.deepcopy(
                (
                    authoritative_receipt,
                    witnesses,
                    observer_track_supports,
                ),
            )
            public_scan_count_entries: tuple[DetectionScanCountEntry, ...] = ()
            tracks_preview = _DefensiveMappingPreview(
                lambda: copy.deepcopy(
                    workspace.intel_fusion["tracks"].get(side, {}),
                ),
            )
            public_fusion_delta = _FogOfWarFusionSideDelta(
                reporting_side=side,
                track_counter=post_fusion_delta.track_counter,
                fow_track_counter=post_fusion_delta.fow_track_counter,
                tracks=tracks_preview,
            )
            world_view_preview = _DefensiveWorldViewPreview(
                side,
                lambda: copy.deepcopy(workspace.world_views[side]),
            )
            outcome_source = workspace.outcome_source
            if outcome_source is None:  # pragma: no cover - private construction
                raise RuntimeError("fog-of-war outcome source is unavailable")
            handle_seal = f"fog-of-war-side:{workspace.generation}:{side}"
            plan = FogOfWarSidePlan(
                reporting_side=side,
                receipt=public_receipt,
                _world_view=world_view_preview,
                _current_detection_witnesses=public_witnesses,
                _observer_track_supports=public_supports,
                _fusion_delta=public_fusion_delta,
                _scan_count_entries=public_scan_count_entries,
                _transaction=transaction,
                _owner_token=self._update_owner_token,
                _generation=workspace.generation,
                _outcome_source=outcome_source,
                _fingerprint=handle_seal,
            )
            side_workspace = _FogOfWarSideWorkspace(
                plan=plan,
                receipt=authoritative_receipt,
                world_view=world_view,
                current_detection_witnesses=witnesses,
                observer_track_supports=observer_track_supports,
                fusion_delta=post_fusion_delta,
                scan_count_values=scan_count_values,
                handle_bindings=(
                    public_receipt,
                    world_view_preview,
                    public_witnesses,
                    public_supports,
                    public_fusion_delta,
                    tracks_preview,
                    public_scan_count_entries,
                    transaction,
                    outcome_source,
                    handle_seal,
                    side,
                ),
            )
            self._validate_side_workspace(workspace, side_workspace)
            self._register_side_plan(workspace, side_workspace)
            return plan
        except BaseException:
            self._poison_update_transaction(transaction)
            raise

    def _execute_update_with_receipt(
        self,
        side: str,
        own_units: list[dict[str, Any]],
        enemy_units: list[dict[str, Any]],
        dt: float,
        *,
        cadence_plan: TacticalCadencePlan,
        indexed_rng: FOWIndexedSideHandle,
        lod_tiers: Mapping[TacticalObserverIdentity, FogOfWarLodTier],
        current_time: float = 0.0,
        decoys: list[Decoy] | None = None,
        detection_culling: bool = True,
        soa_selection: bool = False,
        current_tick: int = 0,
        visibility_m: float = 10000.0,
        illumination_lux: float = 100.0,
        thermal_contrast: float = 1.0,
        ambient_noise_db: float = 70.0,
        atmospheric_atten_db_per_km: float = 0.01,
        transmission_loss: float | None = None,
        jam_snr_penalty_db: float = 0.0,
    ) -> FogOfWarCycleOutcome:
        """Execute one side against an isolated staging manager.

        This private helper mutates only the staging graph created by
        :meth:`update_with_receipt`.  A successful call completes its indexed
        side handle but never commits cadence or the indexed transcript.
        """
        _require_witness_id(side, "fog-of-war side")
        _require_finite_witness_scalar(
            current_time,
            "fog-of-war logical time",
            non_negative=True,
        )
        _require_finite_witness_scalar(
            dt,
            "fog-of-war interval duration",
            non_negative=True,
        )
        if type(current_tick) is not int or current_tick < 0:
            raise ValueError("fog-of-war current_tick must be a non-negative integer")
        if type(cadence_plan) is not TacticalCadencePlan:
            raise TypeError("cadence_plan must be a TacticalCadencePlan")
        if type(indexed_rng) is not FOWIndexedSideHandle:
            raise TypeError("indexed_rng must be a FOWIndexedSideHandle")
        if indexed_rng.reporting_side != side:
            raise ValueError("indexed RNG side disagrees with fog-of-war side")
        if indexed_rng.engine_tick != current_tick:
            raise ValueError("indexed RNG tick disagrees with fog-of-war tick")
        if not isinstance(lod_tiers, Mapping):
            raise TypeError("lod_tiers must be a mapping")
        if type(detection_culling) is not bool:
            raise TypeError("detection_culling must be a strict boolean")
        if type(soa_selection) is not bool:
            raise TypeError("soa_selection must be a strict boolean")

        logical_time_s = float(current_time)
        unbound_observers: list[
            tuple[
                dict[str, Any],
                str,
                TacticalObserverIdentity,
                tuple[_ObserverSensorScan, ...],
                tuple[_TacticalAttachmentKey, ...],
            ]
        ] = []
        roster_attachment_keys: set[_TacticalAttachmentKey] = set()
        observer_identities: set[TacticalObserverIdentity] = set()
        for observer_index, own in enumerate(own_units):
            observer_unit_id = own.get("unit_id")
            _require_witness_id(
                observer_unit_id,
                f"fog-of-war own_units[{observer_index}] unit_id",
            )
            observer_identity = TacticalObserverIdentity(
                reporting_side=side,
                observer_unit_id=observer_unit_id,
            )
            if observer_identity in observer_identities:
                raise ValueError("fog-of-war side roster contains a duplicate observer")
            observer_identities.add(observer_identity)
            scans = self._observer_sensor_scans(own)
            attachment_keys: list[_TacticalAttachmentKey] = []
            for scan in scans:
                if scan.source_equipment_index is None or scan.modeled_role is None:
                    raise ValueError(
                        "receipt-bearing fog-of-war requires typed sensor attachments",
                    )
                attachment_key = _validated_tactical_attachment_key(
                    reporting_side=observer_identity.reporting_side,
                    observer_unit_id=observer_identity.observer_unit_id,
                    source_equipment_index=scan.source_equipment_index,
                    sensor_id=scan.sensor.sensor_id,
                    modeled_role=scan.modeled_role,
                )
                if attachment_key in roster_attachment_keys:
                    raise ValueError(
                        "fog-of-war side roster contains a duplicate attachment identity",
                    )
                roster_attachment_keys.add(attachment_key)
                attachment_keys.append(attachment_key)
            unbound_observers.append(
                (
                    own,
                    observer_unit_id,
                    observer_identity,
                    scans,
                    tuple(attachment_keys),
                ),
            )

        tier_map: dict[TacticalObserverIdentity, FogOfWarLodTier] = {}
        for observer, tier in lod_tiers.items():
            if type(observer) is not TacticalObserverIdentity:
                raise ValueError("lod_tiers contains an invalid observer identity")
            if observer.reporting_side != side:
                raise ValueError("lod_tiers contains another reporting side")
            if type(tier) is not FogOfWarLodTier:
                raise ValueError("lod_tiers contains an invalid LOD tier")
            tier_map[observer] = tier
        if set(tier_map) != observer_identities:
            raise ValueError("lod_tiers must exactly cover the reporting-side observer roster")

        side_decisions: dict[
            _TacticalAttachmentKey,
            TacticalCadenceDecision,
        ] = {}
        for decision in cadence_plan.decisions:
            identity = decision.identity
            if identity.reporting_side != side:
                continue
            attachment_key = _tactical_attachment_key(identity)
            if attachment_key in side_decisions:
                raise ValueError(
                    "cadence plan contains duplicate side attachment identities",
                )
            side_decisions[attachment_key] = decision
        if set(side_decisions) != roster_attachment_keys:
            raise ValueError(
                "cadence plan must exactly cover the reporting-side attachment roster",
            )

        staged_observers: list[_StagedObserver] = []
        for own, observer_unit_id, observer_identity, scans, attachment_keys in unbound_observers:
            bound_scans: list[_BoundObserverSensorScan] = []
            for scan, attachment_key in zip(
                scans,
                attachment_keys,
                strict=True,
            ):
                cadence_decision = side_decisions[attachment_key]
                identity = cadence_decision.identity
                bound_scans.append(
                    _BoundObserverSensorScan(
                        scan=scan,
                        attachment_key=attachment_key,
                        identity=identity,
                        cadence_decision=cadence_decision,
                        scan_identity=DetectionScanIdentity(
                            side=identity.reporting_side,
                            observer_unit_id=identity.observer_unit_id,
                            source_equipment_index=(identity.source_equipment_index),
                        ),
                    ),
                )
            staged_observers.append(
                (
                    own,
                    observer_unit_id,
                    observer_identity,
                    tuple(bound_scans),
                ),
            )

        all_targets: list[dict[str, Any]] = []
        target_ids: set[str] = set()
        for target_index, target in enumerate(enemy_units):
            if not isinstance(target, dict):
                raise TypeError(
                    f"enemy_units[{target_index}] must be a mapping",
                )
            target_copy = dict(target)
            target_id = target_copy.get("unit_id")
            _require_witness_id(
                target_id,
                f"fog-of-war enemy_units[{target_index}] unit_id",
            )
            if target_id in target_ids:
                raise ValueError("fog-of-war target roster contains a duplicate ID")
            target_ids.add(target_id)
            target_copy["_fow_target_kind"] = FOWTargetKind.UNIT
            all_targets.append(target_copy)
        if decoys:
            for decoy in decoys:
                if not decoy.active:
                    continue
                _require_witness_id(decoy.decoy_id, "fog-of-war decoy ID")
                if decoy.decoy_id in target_ids:
                    raise ValueError("fog-of-war target and decoy IDs overlap")
                target_ids.add(decoy.decoy_id)
                all_targets.append(
                    {
                        "unit_id": decoy.decoy_id,
                        "position": decoy.position,
                        "signature": decoy.signature,
                        "unit": None,
                        "target_height": 0.0,
                        "concealment": 0.0,
                        "posture": 0,
                        "_fow_target_kind": FOWTargetKind.DECOY,
                    }
                )

        target_tree: STRtree | None = None
        if detection_culling and all_targets:
            target_tree = _build_fow_target_tree(all_targets)
        target_positions: np.ndarray | None = None
        if not detection_culling and soa_selection and all_targets:
            target_positions = np.asarray(
                [
                    (
                        target["position"].easting,
                        target["position"].northing,
                    )
                    for target in all_targets
                ],
                dtype=np.float64,
            )

        selection_counts = {
            "strtree_builds": int(target_tree is not None),
            "strtree_queries": 0,
            "strtree_admitted_targets": 0,
            "strtree_pruned_targets": 0,
            "soa_vector_builds": int(target_positions is not None),
            "soa_vector_queries": 0,
            "soa_vector_admitted_targets": 0,
            "soa_vector_pruned_targets": 0,
            "brute_force_cycles": 0,
            "brute_force_admitted_targets": 0,
        }
        cadence_counts = {
            "attachment_cycles": 0,
            "operational_attachment_cycles": 0,
            "native_ready": 0,
            "lod_ready": 0,
            "admitted": 0,
            "deferred_native": 0,
            "deferred_lod": 0,
            "deferred_both": 0,
            "offline": 0,
        }
        recovery_admission_counts: dict[
            tuple[TacticalCadenceRecoveryAxis, int],
            int,
        ] = {}
        recovery_work_identities: dict[
            tuple[TacticalCadenceRecoveryAxis, int],
            set[TacticalAttachmentIdentity],
        ] = {}
        recovery_indexed_blocks: dict[
            tuple[TacticalCadenceRecoveryAxis, int],
            int,
        ] = {}
        detection_counts = {
            "api_calls": 0,
            "pre_rng_unsupported_domain_rejections": 0,
            "pre_rng_above_max_range_rejections": 0,
            "pre_rng_below_min_range_rejections": 0,
            "pre_rng_outside_fov_rejections": 0,
            "pre_rng_los_rejections": 0,
            "pre_rng_no_emission_rejections": 0,
            "stochastic_draws": 0,
            "successes": 0,
            "published_witnesses": 0,
        }
        fusion_counts = {
            "position_measurement_candidates": 0,
            "position_measurement_groups": 0,
            "correlated_candidates_elided": 0,
            "predictions": 0,
            "predicted_microseconds": 0,
            "creations": 0,
            "updates": 0,
            "replacements": 0,
        }
        lod_counts = {
            "active_attachments_admitted": 0,
            "active_attachments_deferred": 0,
            "nearby_attachments_admitted": 0,
            "nearby_attachments_deferred": 0,
            "distant_attachments_admitted": 0,
            "distant_attachments_deferred": 0,
        }
        stage_fields = {
            DetectionDecisionStage.PRE_RNG_UNSUPPORTED_DOMAIN: ("pre_rng_unsupported_domain_rejections"),
            DetectionDecisionStage.PRE_RNG_ABOVE_MAX_RANGE: ("pre_rng_above_max_range_rejections"),
            DetectionDecisionStage.PRE_RNG_BELOW_MIN_RANGE: ("pre_rng_below_min_range_rejections"),
            DetectionDecisionStage.PRE_RNG_OUTSIDE_FOV: ("pre_rng_outside_fov_rejections"),
            DetectionDecisionStage.PRE_RNG_LOS: "pre_rng_los_rejections",
            DetectionDecisionStage.PRE_RNG_NO_EMISSION: ("pre_rng_no_emission_rejections"),
        }

        self.clear_current_detection_witnesses(side)
        staged_witnesses: list[ObserverDetectionWitness] = []
        staged_fusion_groups: dict[
            tuple[int, str, int, str, float],
            _FOWFusionAccumulator,
        ] = {}
        staged_support_candidates: dict[
            FOWDecisionIdentity,
            _ObserverTrackSupportCandidate,
        ] = {}
        staged_support_identities: dict[
            _TacticalAttachmentKey,
            TacticalAttachmentIdentity,
        ] = {}
        world_view = self.get_world_view(side)
        world_view.last_update_time = logical_time_s

        attachment_contexts: dict[
            _TacticalAttachmentKey,
            tuple[_BoundObserverSensorScan, Position],
        ] = {}
        for own, _observer_unit_id, _observer_identity, sensor_scans in staged_observers:
            observer_position = own["position"]
            for bound_scan in sensor_scans:
                attachment_contexts[bound_scan.attachment_key] = (
                    bound_scan,
                    observer_position,
                )
        unit_targets = {
            target["unit_id"]: target for target in all_targets if target["_fow_target_kind"] is FOWTargetKind.UNIT
        }
        side_tracks = self._intel_fusion.get_tracks(side)
        retained_supports: dict[
            ObserverTrackSupportIdentity,
            ObserverTrackSupportState,
        ] = {}
        for support in self._observer_track_supports_for_owner(side):
            attachment_identity = support.identity.attachment_identity
            attachment_key = _tactical_attachment_key(attachment_identity)
            attachment_context = attachment_contexts.get(attachment_key)
            target = unit_targets.get(support.identity.target_id)
            decision = side_decisions.get(attachment_key)
            contact = world_view.contacts.get(support.identity.target_id)
            if (
                attachment_context is None
                or target is None
                or decision is None
                or contact is None
                or support.native_period <= 1
                or not decision.operational
                or decision.native_ready
                or decision.disposition
                not in {
                    TacticalCadenceDisposition.DEFERRED_NATIVE,
                    TacticalCadenceDisposition.DEFERRED_BOTH,
                }
                or decision.native_period != support.native_period
                or decision.native_phase_residue != support.native_phase_residue
                or not support.observation_ordinal < cadence_plan.ordinal < support.native_due_ordinal
                or contact.track.track_id != support.fusion_track_id
                or side_tracks.get(support.fusion_track_id) is not contact.track
                or contact.track.status in {TrackStatus.STALE, TrackStatus.LOST}
                or attachment_identity.sensor_id not in contact.reporting_sensors
            ):
                continue
            bound_scan, observer_position = attachment_context
            scan = bound_scan.scan
            target_unit = target.get("unit")
            target_domain = getattr(target_unit, "domain", None)
            try:
                modeled_role = SensorModeledRole(
                    bound_scan.identity.modeled_role,
                )
                cadence_state = cadence_plan.state_for(
                    bound_scan.identity,
                )
                supported = observer_track_support_role_is_supported(
                    sensor_type=scan.sensor.sensor_type,
                    modeled_role=modeled_role,
                )
                domain_supported = target_domain is not None and scan.sensor.supports_target_domain(target_domain)
                projected = support.project(
                    projection_ordinal=cadence_plan.ordinal,
                    projection_time_s=logical_time_s,
                    process_noise_std_mps2=(self.observer_track_support_process_noise_std_mps2),
                )
                within_limits = projected.is_within_limits(
                    observer_easting_m=float(observer_position.easting),
                    observer_northing_m=float(observer_position.northing),
                    reach_m=float(scan.sensor.effective_range),
                    max_position_uncertainty_m=(self.observer_track_support_max_position_uncertainty_m),
                )
            except (TypeError, ValueError):
                continue
            if (
                scan.sensor.operational
                and scan.sensor.sensor_type is support.sensor_type
                and supported
                and domain_supported
                and within_limits
                and cadence_state.native_next_due == support.native_due_ordinal
            ):
                retained_supports[support.identity] = support
        with self._witness_lock:
            self._observer_track_supports = retained_supports

        vectorized_candidate_indices = (
            None
            if target_tree is None
            else self._vectorized_strtree_candidate_indices(
                target_tree,
                staged_observers,
            )
        )
        for observer_index, (
            own,
            observer_unit_id,
            observer_identity,
            sensor_scans,
        ) in enumerate(staged_observers):
            tier = tier_map[observer_identity]
            operational_sensors: list[SensorInstance] = []
            for bound_scan in sensor_scans:
                scan = bound_scan.scan
                cadence_decision = bound_scan.cadence_decision
                if cadence_decision.operational is not scan.sensor.operational:
                    raise ValueError(
                        "cadence decision operational state disagrees with its live sensor",
                    )
                cadence_counts["attachment_cycles"] += 1
                cadence_counts["native_ready"] += int(cadence_decision.native_ready)
                cadence_counts["lod_ready"] += int(cadence_decision.lod_ready)
                for recovery in cadence_decision.recoveries:
                    if recovery.admission_ordinal != cadence_plan.ordinal:
                        raise ValueError(
                            "cadence recovery admission ordinal disagrees with its plan",
                        )
                    recovery_key = recovery.axis, recovery.deferral_period
                    recovery_admission_counts[recovery_key] = recovery_admission_counts.get(recovery_key, 0) + 1
                if cadence_decision.operational:
                    operational_sensors.append(scan.sensor)
                    cadence_counts["operational_attachment_cycles"] += 1
                    if cadence_decision.admitted:
                        cadence_counts["admitted"] += 1
                        lod_key = f"{tier.value.lower()}_attachments_admitted"
                    else:
                        if cadence_decision.disposition is (TacticalCadenceDisposition.DEFERRED_NATIVE):
                            cadence_counts["deferred_native"] += 1
                        elif cadence_decision.disposition is (TacticalCadenceDisposition.DEFERRED_LOD):
                            cadence_counts["deferred_lod"] += 1
                        elif cadence_decision.disposition is (TacticalCadenceDisposition.DEFERRED_BOTH):
                            cadence_counts["deferred_both"] += 1
                        else:
                            raise ValueError(
                                "operational cadence decision has invalid disposition",
                            )
                        lod_key = f"{tier.value.lower()}_attachments_deferred"
                    lod_counts[lod_key] += 1
                else:
                    if cadence_decision.disposition is not (TacticalCadenceDisposition.OFFLINE):
                        raise ValueError(
                            "offline cadence decision has invalid disposition",
                        )
                    cadence_counts["offline"] += 1

            target_count = len(all_targets)
            maximum_range = max(
                (sensor.effective_range for sensor in operational_sensors),
                default=0.0,
            )
            observer_position = own["position"]
            if target_tree is not None:
                selection_counts["strtree_queries"] += 1
                if maximum_range > 0.0:
                    if vectorized_candidate_indices is None:
                        candidate_indices = tuple(
                            sorted(
                                int(index)
                                for index in target_tree.query(
                                    box(
                                        observer_position.easting - maximum_range,
                                        observer_position.northing - maximum_range,
                                        observer_position.easting + maximum_range,
                                        observer_position.northing + maximum_range,
                                    )
                                )
                            )
                        )
                    else:
                        candidate_indices = vectorized_candidate_indices[observer_index]
                    scan_targets = [all_targets[index] for index in candidate_indices]
                else:
                    scan_targets = []
                selection_counts["strtree_admitted_targets"] += len(scan_targets)
                selection_counts["strtree_pruned_targets"] += target_count - len(scan_targets)
            elif target_positions is not None:
                selection_counts["soa_vector_queries"] += 1
                if maximum_range > 0.0:
                    observer_array = np.asarray(
                        [observer_position.easting, observer_position.northing],
                        dtype=np.float64,
                    )
                    offsets = target_positions - observer_array
                    distances = np.sqrt(np.sum(offsets * offsets, axis=1))
                    admitted_indices = np.where(distances <= maximum_range)[0]
                    scan_targets = [all_targets[int(index)] for index in admitted_indices]
                else:
                    scan_targets = []
                selection_counts["soa_vector_admitted_targets"] += len(scan_targets)
                selection_counts["soa_vector_pruned_targets"] += target_count - len(scan_targets)
            else:
                selection_counts["brute_force_cycles"] += 1
                selection_counts["brute_force_admitted_targets"] += target_count
                scan_targets = all_targets

            observer_height = own.get("observer_height", 1.8)
            observer_heading = own.get("observer_heading_deg", 0.0)
            for target in scan_targets:
                target_id = target["unit_id"]
                target_position = target["position"]
                target_signature = target["signature"]
                target_unit = target.get("unit")
                geometry: _DetectionGeometry | None = None
                for bound_scan in sensor_scans:
                    scan = bound_scan.scan
                    identity = bound_scan.identity
                    cadence_decision = bound_scan.cadence_decision
                    if not cadence_decision.admitted:
                        continue
                    detection_counts["api_calls"] += 1
                    if geometry is None:
                        target_height = target.get("target_height", 0.0)
                        target_concealment = target.get("concealment", 0.0)
                        target_posture = target.get("posture", 0)
                        target_illumination = target.get(
                            "illumination_lux",
                            illumination_lux,
                        )
                        target_visibility = target.get(
                            "visibility_m",
                            visibility_m,
                        )
                        target_thermal_contrast = target.get(
                            "thermal_contrast",
                            thermal_contrast,
                        )
                        target_ambient_noise = target.get(
                            "ambient_noise_db",
                            ambient_noise_db,
                        )
                        target_atmospheric_attenuation = target.get(
                            "atmospheric_atten_db_per_km",
                            atmospheric_atten_db_per_km,
                        )
                        target_transmission_loss = target.get(
                            "transmission_loss",
                            transmission_loss,
                        )
                        target_jam_penalty = target.get(
                            "jam_snr_penalty_db",
                            jam_snr_penalty_db,
                        )
                        geometry = _detection_geometry(
                            observer_position,
                            target_position,
                        )
                    prepared = self._detection._prepare_fow_detection(
                        observer_position,
                        target_position,
                        scan.sensor,
                        target_signature,
                        geometry=geometry,
                        target_unit=target_unit,
                        observer_height=observer_height,
                        target_height=target_height,
                        concealment=target_concealment,
                        posture=target_posture,
                        illumination_lux=target_illumination,
                        visibility_m=target_visibility,
                        thermal_contrast=target_thermal_contrast,
                        ambient_noise_db=target_ambient_noise,
                        atmospheric_atten_db_per_km=(target_atmospheric_attenuation),
                        transmission_loss=target_transmission_loss,
                        observer_heading_deg=observer_heading,
                        target_id=target_id,
                        scan_identity=bound_scan.scan_identity,
                        jam_snr_penalty_db=target_jam_penalty,
                    )
                    indexed_decision = None
                    decision_identity: FOWDecisionIdentity | None = None
                    if isinstance(prepared, DetectionDecisionStage):
                        stage_field = stage_fields.get(prepared)
                        if stage_field is None:
                            raise ValueError(
                                "admitted operational detection returned an unreceipted stage",
                            )
                        detection_counts[stage_field] += 1
                        continue
                    elif isinstance(prepared, PreparedDetection):
                        decision_identity = FOWDecisionIdentity(
                            engine_tick=current_tick,
                            reporting_side=side,
                            observer_unit_id=observer_unit_id,
                            source_equipment_index=(identity.source_equipment_index),
                            sensor_id=identity.sensor_id,
                            modeled_role=identity.modeled_role,
                            target_kind=target["_fow_target_kind"],
                            target_id=target_id,
                        )
                        indexed_decision = indexed_rng.issue(
                            decision_identity,
                        )
                        result = prepared.adjudicate(
                            indexed_decision.detection_uniform(
                                probability=prepared.probability,
                            ),
                        )
                        if result.detected is not indexed_decision.detection_succeeded:
                            raise RuntimeError(
                                "indexed detection adjudication disagrees with the production result",
                            )
                        detection_counts["stochastic_draws"] += 1
                        for recovery in cadence_decision.recoveries:
                            recovery_key = recovery.axis, recovery.deferral_period
                            recovery_indexed_blocks[recovery_key] = recovery_indexed_blocks.get(recovery_key, 0) + 1
                            recovery_work_identities.setdefault(
                                recovery_key,
                                set(),
                            ).add(identity)
                    else:  # pragma: no cover - closed private preparation union
                        raise TypeError("detection preparation returned an invalid type")

                    if not result.detected:
                        continue
                    if decision_identity is None:
                        raise ValueError(
                            "successful detection lacks its indexed decision identity",
                        )
                    if indexed_decision is None:  # pragma: no cover - paired construction
                        raise RuntimeError(
                            "successful detection lost its indexed decision handle",
                        )
                    detection_counts["successes"] += 1
                    staged_witnesses.append(
                        ObserverDetectionWitness(
                            side=side,
                            observer_unit_id=observer_unit_id,
                            target_id=target_id,
                            source_equipment_index=identity.source_equipment_index,
                            sensor_id=identity.sensor_id,
                            modeled_role=identity.modeled_role,
                            logical_time_s=logical_time_s,
                            detected=True,
                            probability=float(result.probability),
                            snr_db=float(result.snr_db),
                            range_m=float(result.range_m),
                            sensor_type=result.sensor_type.name,
                            bearing_deg=float(result.bearing_deg),
                        )
                    )
                    contact_info = ContactInfo(
                        ContactLevel.DETECTED,
                        None,
                        None,
                        None,
                        0.3,
                    )
                    if self._identification is not None:
                        if indexed_decision is None:  # pragma: no cover - identity guard above
                            raise RuntimeError(
                                "successful indexed detection lost its decision handle",
                            )
                        contact_info = self._identification.classify_from_detection(
                            result,
                            target_unit,
                            threshold_db=(scan.sensor.definition.detection_threshold),
                            classification_uniform=(
                                indexed_decision.identification_uniform(
                                    detection_succeeded=True,
                                )
                            ),
                        )

                    fusion_candidate = SensorFusionCandidate(
                        identity=decision_identity,
                        detection=result,
                        contact_info=contact_info,
                        observer_position=observer_position,
                        observation_time_s=logical_time_s,
                    )
                    issued_preimage = indexed_decision._issued_preimage(
                        decision_identity,
                    )
                    validated_candidate = self._intel_fusion._validate_prevalidated_fow_candidate(
                        fusion_candidate,
                        decision_preimage=issued_preimage,
                    )
                    fusion_key = validated_candidate.group_key
                    accumulator = staged_fusion_groups.get(fusion_key)
                    if accumulator is None:
                        staged_fusion_groups[fusion_key] = _FOWFusionAccumulator.from_candidate(
                            validated_candidate,
                            fusion_candidate,
                            issued_preimage,
                        )
                    else:
                        accumulator.accumulate(
                            validated_candidate,
                            fusion_candidate,
                            issued_preimage,
                        )
                    if target["_fow_target_kind"] is FOWTargetKind.UNIT and cadence_decision.native_period > 1:
                        try:
                            modeled_role = SensorModeledRole(
                                identity.modeled_role,
                            )
                            supports_track = observer_track_support_role_is_supported(
                                sensor_type=result.sensor_type,
                                modeled_role=modeled_role,
                            )
                        except ValueError:
                            supports_track = False
                        if supports_track:
                            support_attachment_identity = staged_support_identities.get(
                                bound_scan.attachment_key,
                            )
                            if support_attachment_identity is None:
                                support_attachment_identity = TacticalAttachmentIdentity(
                                    reporting_side=identity.reporting_side,
                                    observer_unit_id=(identity.observer_unit_id),
                                    source_equipment_index=(identity.source_equipment_index),
                                    sensor_id=identity.sensor_id,
                                    modeled_role=identity.modeled_role,
                                )
                                staged_support_identities[bound_scan.attachment_key] = support_attachment_identity
                            staged_support_candidates[decision_identity] = _ObserverTrackSupportCandidate(
                                identity=ObserverTrackSupportIdentity(
                                    attachment_identity=(support_attachment_identity),
                                    target_id=target_id,
                                ),
                                sensor_type=result.sensor_type,
                                cadence_decision=cadence_decision,
                                range_m=float(result.range_m),
                                probability=float(result.probability),
                                observation_time_s=logical_time_s,
                            )

        canonical_fusion_keys = sorted(
            staged_fusion_groups,
            key=lambda key: (
                key[0],
                key[1].encode("utf-8"),
                key[2],
                key[3].encode("utf-8"),
                key[4],
            ),
        )
        for fusion_key in canonical_fusion_keys:
            accumulator = staged_fusion_groups[fusion_key]
            representative_candidate = accumulator.candidate_ledger.get(
                accumulator.representative_key[1],
            )
            if (
                accumulator.candidate_count != len(accumulator.candidate_ledger)
                or representative_candidate is None
                or representative_candidate.identity is not accumulator.representative.identity
            ):
                raise RuntimeError(
                    "prevalidated FOW fusion accumulator is inconsistent",
                )
            candidates = tuple(
                candidate
                for _preimage, candidate in sorted(
                    accumulator.candidate_ledger.items(),
                )
            )
            prepared_representative = self._intel_fusion._materialize_validated_sensor_fusion_candidate(
                accumulator.representative,
            )
            if (
                type(prepared_representative) is not _PreparedSensorFusionCandidate
                or prepared_representative.group_key != fusion_key
                or (
                    prepared_representative.effective_variance_m2,
                    prepared_representative.encoded_identity,
                )
                != accumulator.representative_key
            ):
                raise RuntimeError(
                    "prevalidated FOW representative changed during materialization",
                )
            target_id = fusion_key[3]
            existing_contact = world_view.contacts.get(target_id)
            fusion_outcome = self._intel_fusion._submit_prevalidated_detached_sensor_fusion_with_outcome(
                prepared_representative,
                candidate_count=accumulator.candidate_count,
                contact_id=(None if existing_contact is None else existing_contact.track.track_id),
            )
            fusion_counts["position_measurement_candidates"] += fusion_outcome.position_measurement_candidates
            fusion_counts["position_measurement_groups"] += fusion_outcome.position_measurement_groups
            fusion_counts["correlated_candidates_elided"] += fusion_outcome.correlated_candidates_elided
            fusion_counts["predictions"] += fusion_outcome.predictions
            fusion_counts["predicted_microseconds"] += fusion_outcome.prediction_microseconds
            fusion_counts["creations"] += fusion_outcome.creations
            fusion_counts["updates"] += fusion_outcome.updates
            fusion_counts["replacements"] += fusion_outcome.replacements
            track_id = fusion_outcome.track_id
            if track_id is None:
                raise ValueError(
                    "successful fusion candidate group did not produce a track",
                )
            track = self._intel_fusion.get_tracks(side).get(track_id)
            if track is None:
                raise ValueError("fusion outcome references a missing track")

            for support_identity, support in tuple(
                retained_supports.items(),
            ):
                if support_identity.target_id == target_id and support.fusion_track_id != track_id:
                    del retained_supports[support_identity]
            for candidate in candidates:
                support_candidate = staged_support_candidates.get(
                    candidate.identity,
                )
                if support_candidate is None:
                    continue
                cadence_decision = support_candidate.cadence_decision
                period = cadence_decision.native_period
                phase = cadence_decision.native_phase_residue
                phase_delta = (phase - cadence_plan.ordinal % period) % period
                if phase_delta == 0:
                    phase_delta = period
                native_due_ordinal = cadence_plan.ordinal + phase_delta
                cadence_state = cadence_plan.state_for(
                    support_candidate.identity.attachment_identity,
                )
                if cadence_state.native_next_due != native_due_ordinal:
                    raise ValueError(
                        "observer support deadline disagrees with cadence state",
                    )
                position_sigma_m = max(
                    0.05 * support_candidate.range_m,
                    1.0,
                ) / max(support_candidate.probability, 0.01)
                position_variance = position_sigma_m * position_sigma_m
                horizontal_range_m = candidate.detection.horizontal_range_m
                if horizontal_range_m is None:
                    raise ValueError(
                        "observer support detection lacks detector-emitted horizontal_range_m",
                    )
                bearing_rad = math.radians(candidate.detection.bearing_deg)
                support = ObserverTrackSupportState(
                    identity=support_candidate.identity,
                    fusion_track_id=track_id,
                    sensor_type=support_candidate.sensor_type,
                    observation_ordinal=cadence_plan.ordinal,
                    observation_time_s=(support_candidate.observation_time_s),
                    native_period=period,
                    native_phase_residue=phase,
                    native_due_ordinal=native_due_ordinal,
                    position_m=(
                        float(candidate.observer_position.easting + horizontal_range_m * math.sin(bearing_rad)),
                        float(candidate.observer_position.northing + horizontal_range_m * math.cos(bearing_rad)),
                    ),
                    velocity_mps=(0.0, 0.0),
                    covariance=(
                        (position_variance, 0.0, 0.0, 0.0),
                        (0.0, position_variance, 0.0, 0.0),
                        (0.0, 0.0, 100.0, 0.0),
                        (0.0, 0.0, 0.0, 100.0),
                    ),
                )
                retained_supports[support.identity] = support

            if existing_contact is None:
                contact = ContactRecord(
                    contact_id=target_id,
                    track=track,
                    contact_info=candidates[0].contact_info,
                    first_detected_time=fusion_key[4],
                    last_sensor_contact_time=fusion_key[4],
                )
                observations = candidates[1:]
            else:
                contact = existing_contact
                contact.track = track
                observations = candidates
            merged_contact_info = contact.contact_info
            for candidate in observations:
                merged_contact_info = (
                    IdentificationEngine.update_contact(
                        merged_contact_info,
                        candidate.contact_info,
                    )
                    if self._identification is not None
                    else candidate.contact_info
                )
            contact.contact_info = merged_contact_info
            contact.last_sensor_contact_time = fusion_key[4]
            for candidate in candidates:
                sensor_id = candidate.identity.sensor_id
                if sensor_id not in contact.reporting_sensors:
                    contact.reporting_sensors.append(sensor_id)
            world_view.contacts[target_id] = contact

        tracks = self._intel_fusion.get_tracks(side)
        for track_id in self._estimator.manage_tracks(tracks, logical_time_s):
            for contact_id in list(world_view.contacts):
                if world_view.contacts[contact_id].track.track_id == track_id:
                    del world_view.contacts[contact_id]
                    break

        for support_identity, support in tuple(retained_supports.items()):
            contact = world_view.contacts.get(support_identity.target_id)
            if (
                contact is None
                or contact.track.track_id != support.fusion_track_id
                or tracks.get(support.fusion_track_id) is not contact.track
                or contact.track.status in {TrackStatus.STALE, TrackStatus.LOST}
            ):
                del retained_supports[support_identity]

        published_witnesses = tuple(sorted(staged_witnesses, key=self._witness_sort_key))
        detection_counts["published_witnesses"] = len(published_witnesses)
        indexed_entries = indexed_rng.complete()
        identification_lanes = sum(int(entry.consumed_lane_mask == 3) for entry in indexed_entries)
        if len(indexed_entries) != detection_counts["stochastic_draws"]:
            raise ValueError("indexed entry count disagrees with stochastic draws")

        def recovery_period_receipts(
            axis: TacticalCadenceRecoveryAxis,
        ) -> tuple[FOWCadenceRecoveryPeriodReceipt, ...]:
            periods = sorted(period for recovery_axis, period in recovery_admission_counts if recovery_axis is axis)
            return tuple(
                FOWCadenceRecoveryPeriodReceipt(
                    deferral_period=period,
                    recovery_admissions=recovery_admission_counts[(axis, period)],
                    recovery_admissions_with_indexed_work=len(
                        recovery_work_identities.get((axis, period), set()),
                    ),
                    indexed_detection_blocks=recovery_indexed_blocks.get(
                        (axis, period),
                        0,
                    ),
                )
                for period in periods
            )

        cadence_receipt = FOWCadenceReceipt(
            **cadence_counts,
            native_recoveries_by_period=recovery_period_receipts(
                TacticalCadenceRecoveryAxis.NATIVE,
            ),
            lod_recoveries_by_period=recovery_period_receipts(
                TacticalCadenceRecoveryAxis.LOD,
            ),
        )
        receipt = FogOfWarCycleReceipt(
            reporting_side=side,
            engine_tick=current_tick,
            observers=len(staged_observers),
            targets=len(all_targets),
            sensors=len(roster_attachment_keys),
            target_opportunities=(len(staged_observers) * len(all_targets)),
            selection=FOWSelectionReceipt(**selection_counts),
            scan=FOWScanReceipt(
                operational_sensor_target_opportunities=(detection_counts["api_calls"]),
                scheduled_attachment_skips=cadence_receipt.deferred,
            ),
            cadence=cadence_receipt,
            detection=FOWDetectionReceipt(**detection_counts),
            fusion=FOWFusionReceipt(**fusion_counts),
            indexed_rng=FOWIndexedRNGReceipt(
                blocks=len(indexed_entries),
                detection_lanes=len(indexed_entries),
                identification_lanes=identification_lanes,
                transcript_entries=len(indexed_entries),
            ),
            lod_detection=LODDetectionReceipt(**lod_counts),
        )
        published_supports = tuple(
            sorted(
                retained_supports.values(),
                key=lambda support: support.identity.sort_key(),
            )
        )
        with self._witness_lock:
            self._current_detection_witnesses[side] = published_witnesses
            self._observer_track_supports = {support.identity: support for support in published_supports}
        return FogOfWarCycleOutcome(
            world_view=world_view,
            receipt=receipt,
            witnesses=published_witnesses,
            observer_track_supports=published_supports,
        )

    def _validate_side_workspace(
        self,
        workspace: _FogOfWarUpdateWorkspace,
        side_workspace: _FogOfWarSideWorkspace,
    ) -> None:
        side = side_workspace.plan.reporting_side
        receipt = side_workspace.receipt
        world_view = side_workspace.world_view
        witnesses = side_workspace.current_detection_witnesses
        supports = side_workspace.observer_track_supports
        fusion_delta = side_workspace.fusion_delta
        if (
            receipt.reporting_side != side
            or world_view.side != side
            or any(witness.side != side for witness in witnesses)
            or any(support.identity.attachment_identity.reporting_side != side for support in supports)
        ):
            raise ValueError("fog-of-war side workspace owner topology is inconsistent")
        support_identities = tuple(support.identity for support in supports)
        if len(set(support_identities)) != len(support_identities) or supports != tuple(
            sorted(
                supports,
                key=lambda support: support.identity.sort_key(),
            )
        ):
            raise ValueError(
                "fog-of-war side workspace observer supports are not canonical",
            )
        self._validate_fusion_side_delta(
            fusion_delta,
            expected_side=side,
        )
        self._validate_update_aliases(
            {side: world_view},
            {"tracks": {side: fusion_delta.tracks}},
        )

        if fusion_delta.track_counter != workspace.intel_fusion["track_counter"]:
            raise ValueError("fog-of-war side workspace changed the global fusion track counter")
        baseline_counter = workspace.intel_fusion["fow_track_counters"].get(
            side,
        )
        staged_counter = fusion_delta.fow_track_counter
        if staged_counter is None and baseline_counter is not None:
            raise ValueError("fog-of-war side workspace removed its issued track counter")
        if baseline_counter is not None and staged_counter is not None and staged_counter < baseline_counter:
            raise ValueError("fog-of-war side workspace rewound its track counter")

        baseline_counts = {
            key: count
            for key, count in workspace.baseline_scan_count_values.items()
            if len(key) == 5 and key[0] == side
        }
        staged_counts = side_workspace.scan_count_values
        if any(
            type(key) is not tuple or len(key) != 5 or key[0] != side or type(count) is not int or count <= 0
            for key, count in staged_counts.items()
        ):
            raise ValueError("fog-of-war side workspace contains a foreign scan count")
        for key, baseline_count in baseline_counts.items():
            staged_count = staged_counts.get(key)
            if staged_count is None:
                raise ValueError("fog-of-war side workspace removed a scan count")
            if staged_count < baseline_count:
                raise ValueError("fog-of-war side workspace rewound a scan count")

    def _validate_side_plan(
        self,
        transaction: FogOfWarUpdateTransaction,
        plan: FogOfWarSidePlan,
    ) -> _FogOfWarSideWorkspace:
        if type(plan) is not FogOfWarSidePlan:
            raise TypeError("side_plans contains an invalid plan")
        workspace = self._update_workspace
        if workspace is None or workspace.transaction is not transaction:
            raise ValueError("fog-of-war side plan workspace is stale")
        if type(plan.reporting_side) is not str:
            raise ValueError("fog-of-war side plan metadata was mutated")
        side_workspace = workspace.side_workspaces.get(plan.reporting_side)
        if (
            plan._owner_token is not self._update_owner_token
            or plan._transaction is not transaction
            or self._issued_side_plans.get(plan.reporting_side) is not plan
            or side_workspace is None
            or side_workspace.plan is not plan
            or type(plan._generation) is not int
            or plan._generation is not workspace.generation
        ):
            raise ValueError("fog-of-war side plan is foreign or stale")
        (
            public_receipt,
            world_view_preview,
            public_witnesses,
            public_supports,
            public_fusion_delta,
            tracks_preview,
            public_scan_count_entries,
            expected_transaction,
            outcome_source,
            handle_seal,
            expected_reporting_side,
        ) = side_workspace.handle_bindings
        if (
            plan.reporting_side is not expected_reporting_side
            or plan.receipt is not public_receipt
            or not _exact_fow_receipt_matches(
                plan.receipt,
                side_workspace.receipt,
            )
            or plan._world_view is not world_view_preview
            or plan._current_detection_witnesses is not public_witnesses
            or plan._fusion_delta is not public_fusion_delta
            or plan._scan_count_entries is not public_scan_count_entries
            or plan._transaction is not expected_transaction
            or plan._outcome_source is not outcome_source
            or plan._fingerprint is not handle_seal
        ):
            raise ValueError("fog-of-war side plan metadata was mutated")
        if type(plan._current_detection_witnesses) is not tuple or type(plan._scan_count_entries) is not tuple:
            raise ValueError("fog-of-war side plan diagnostic tuple shape was mutated")
        if type(plan._observer_track_supports) is not tuple or plan._observer_track_supports is not public_supports:
            raise ValueError(
                "fog-of-war side plan observer supports must be an exact ObserverTrackSupportState tuple",
            )
        if (
            type(plan._fusion_delta) is not _FogOfWarFusionSideDelta
            or plan._fusion_delta.reporting_side is not expected_reporting_side
            or plan._fusion_delta.track_counter is not side_workspace.fusion_delta.track_counter
            or plan._fusion_delta.fow_track_counter is not side_workspace.fusion_delta.fow_track_counter
        ):
            raise ValueError("fog-of-war side plan fusion metadata was mutated")
        self._validate_mapping_preview(
            plan._fusion_delta.tracks,
            tracks_preview,
            field_name="fog-of-war side fusion tracks",
        )
        return side_workspace

    def _live_update_fingerprint(
        self,
        reporting_sides: tuple[str, ...],
    ) -> str:
        self.validate_internal_bindings()
        self.validate_live_contact_bindings()
        rng_state = copy.deepcopy(self._rng.bit_generator.state)
        with self._intel_fusion._track_lock, self._witness_lock:
            ledger = self._intel_fusion._delivery_receipts
            staged_ledger = type(ledger)(
                tuple(ledger),
                revision=ledger.revision + 1,
            )
            intel_fusion = {
                "tracks": self._intel_fusion._tracks,
                "track_counter": self._intel_fusion._track_counter,
                "fow_track_counters": self._intel_fusion._fow_track_counters,
                "rng_state": rng_state,
                "satellite_passes": self._intel_fusion._satellite_passes,
                "delivery_receipts": staged_ledger,
                "delivery_receipt_ledger": staged_ledger,
                "imint_target_tracks": self._intel_fusion._imint_target_tracks,
            }
            return _update_plan_fingerprint(
                reporting_sides=reporting_sides,
                world_views=self._world_views,
                current_detection_witnesses=self._current_detection_witnesses,
                observer_track_supports=tuple(
                    sorted(
                        self._observer_track_supports.values(),
                        key=lambda support: support.identity.sort_key(),
                    )
                ),
                rng_state=rng_state,
                intel_fusion=intel_fusion,
                scan_counts=None,
            )

    def prevalidate_update_transaction(
        self,
        transaction: FogOfWarUpdateTransaction,
        side_plans: tuple[FogOfWarSidePlan, ...],
    ) -> FogOfWarPublicationPlan:
        """Validate and merge the exact canonical side union without publication."""
        if type(side_plans) is not tuple:
            raise TypeError("side_plans must be an immutable tuple")
        with self._update_transaction_lock:
            workspace = self._validate_update_transaction(transaction)
            if self._active_publication_plan is not None:
                raise RuntimeError("fog-of-war transaction was already prevalidated")
            if self._update_in_progress_sides:
                raise RuntimeError("fog-of-war side staging is still in progress")
            if tuple(plan.reporting_side for plan in side_plans) != workspace.reporting_sides:
                raise ValueError("side_plans must be the exact canonical reporting-side union")
            if set(self._issued_side_plans) != set(workspace.reporting_sides):
                raise ValueError("fog-of-war transaction is missing a reporting-side plan")
            side_workspaces = tuple(self._validate_side_plan(transaction, plan) for plan in side_plans)

            supports_by_identity = {support.identity: support for support in workspace.observer_track_supports}
            merged_scan_count_values = dict(workspace.baseline_scan_count_values)
            for side_workspace in side_workspaces:
                side = side_workspace.plan.reporting_side
                fusion_delta = side_workspace.fusion_delta
                if fusion_delta.fow_track_counter is not None:
                    workspace.intel_fusion["fow_track_counters"][side] = fusion_delta.fow_track_counter
                else:
                    workspace.intel_fusion["fow_track_counters"].pop(side, None)
                workspace.current_detection_witnesses[side] = side_workspace.current_detection_witnesses
                supports_by_identity = {
                    identity: support
                    for identity, support in supports_by_identity.items()
                    if identity.attachment_identity.reporting_side != side
                }
                for support in side_workspace.observer_track_supports:
                    if support.identity in supports_by_identity:
                        raise ValueError(
                            "fog-of-war publication observer support identity overlaps",
                        )
                    supports_by_identity[support.identity] = support
                for key in tuple(merged_scan_count_values):
                    if len(key) == 5 and key[0] == side:
                        del merged_scan_count_values[key]
                merged_scan_count_values.update(side_workspace.scan_count_values)

            workspace.world_views = {side: workspace.world_views[side] for side in sorted(workspace.world_views)}
            workspace.current_detection_witnesses = {
                side: workspace.current_detection_witnesses[side]
                for side in sorted(workspace.current_detection_witnesses)
            }
            workspace.intel_fusion["tracks"] = {
                side: workspace.intel_fusion["tracks"][side] for side in sorted(workspace.intel_fusion["tracks"])
            }
            workspace.intel_fusion["fow_track_counters"] = {
                side: workspace.intel_fusion["fow_track_counters"][side]
                for side in sorted(workspace.intel_fusion["fow_track_counters"])
            }
            scan_counts = self._detection._stage_fow_scan_count_values(
                merged_scan_count_values,
            )
            scan_count_values_binding = self._scan_count_values_binding(
                merged_scan_count_values,
            )
            observer_track_supports = tuple(
                sorted(
                    supports_by_identity.values(),
                    key=lambda support: support.identity.sort_key(),
                )
            )
            workspace.observer_track_supports = observer_track_supports
            workspace.publication_scan_count_values = merged_scan_count_values
            workspace.publication_scan_count_values_binding = scan_count_values_binding
            self._validate_update_aliases(
                workspace.world_views,
                workspace.intel_fusion,
            )
            authoritative_receipts = tuple(side_workspace.receipt for side_workspace in side_workspaces)
            public_receipts = tuple(side_workspace.plan.receipt for side_workspace in side_workspaces)
            world_views_preview = self._workspace_mapping_preview(
                workspace,
                "world_views",
            )
            witnesses_preview = self._workspace_mapping_preview(
                workspace,
                "current_detection_witnesses",
            )
            supports_preview = copy.deepcopy(observer_track_supports)
            fusion_preview = self._workspace_mapping_preview(
                workspace,
                "intel_fusion",
            )
            outcome_source = workspace.outcome_source
            if outcome_source is None:  # pragma: no cover - private construction
                raise RuntimeError("fog-of-war outcome source is unavailable")
            handle_seal = f"fog-of-war-publication:{workspace.generation}"
            publication = FogOfWarPublicationPlan(
                reporting_sides=workspace.reporting_sides,
                receipts=public_receipts,
                _world_views=world_views_preview,
                _current_detection_witnesses=witnesses_preview,
                _observer_track_supports=supports_preview,
                _intel_fusion=fusion_preview,
                _scan_counts=scan_counts,
                _transaction=transaction,
                _owner_token=self._update_owner_token,
                _generation=workspace.generation,
                _outcome_source=outcome_source,
                _fingerprint=handle_seal,
            )
            workspace.publication = publication
            workspace.publication_bindings = (
                workspace.reporting_sides,
                public_receipts,
                authoritative_receipts,
                world_views_preview,
                witnesses_preview,
                supports_preview,
                fusion_preview,
                scan_counts,
                scan_counts._entries,
                scan_counts._owner_token,
                scan_counts._fingerprint,
                transaction,
                outcome_source,
                handle_seal,
            )
            self._active_publication_plan = publication
            return publication

    def _validate_publication_plan(
        self,
        workspace: _FogOfWarUpdateWorkspace,
        publication: FogOfWarPublicationPlan,
    ) -> None:
        if type(publication) is not FogOfWarPublicationPlan:
            raise TypeError("publication must be a FogOfWarPublicationPlan")
        if (
            publication._owner_token is not self._update_owner_token
            or self._active_publication_plan is not publication
            or workspace.publication is not publication
            or type(publication._generation) is not int
            or publication._generation is not workspace.generation
        ):
            raise ValueError("fog-of-war publication is foreign or stale")
        (
            reporting_sides,
            public_receipts,
            authoritative_receipts,
            world_views_preview,
            witnesses_preview,
            supports_preview,
            fusion_preview,
            scan_counts,
            scan_entries,
            scan_owner,
            scan_fingerprint,
            transaction,
            outcome_source,
            handle_seal,
        ) = workspace.publication_bindings
        if (
            publication.reporting_sides is not reporting_sides
            or publication.receipts is not public_receipts
            or not _exact_fow_receipt_tuple_matches(
                publication.receipts,
                authoritative_receipts,
            )
            or publication._transaction is not transaction
            or publication._outcome_source is not outcome_source
            or publication._fingerprint is not handle_seal
        ):
            raise ValueError("fog-of-war publication metadata was mutated")
        self._validate_mapping_preview(
            publication._world_views,
            world_views_preview,
            field_name="fog-of-war publication world views",
        )
        self._validate_mapping_preview(
            publication._current_detection_witnesses,
            witnesses_preview,
            field_name="fog-of-war publication witnesses",
        )
        if (
            type(publication._observer_track_supports) is not tuple
            or publication._observer_track_supports is not supports_preview
        ):
            raise ValueError(
                "fog-of-war publication observer supports must be an exact ObserverTrackSupportState tuple",
            )
        self._validate_mapping_preview(
            publication._intel_fusion,
            fusion_preview,
            field_name="fog-of-war publication fusion state",
        )
        if (
            type(publication._scan_counts) is not DetectionScanCountSnapshot
            or publication._scan_counts is not scan_counts
            or publication._scan_counts._entries is not scan_entries
            or publication._scan_counts._owner_token is not scan_owner
            or publication._scan_counts._fingerprint is not scan_fingerprint
        ):
            raise ValueError("fog-of-war publication scan-count metadata was mutated")

    @staticmethod
    def _prepare_observer_track_support_map(
        supports: tuple[ObserverTrackSupportState, ...],
    ) -> dict[ObserverTrackSupportIdentity, ObserverTrackSupportState]:
        """Materialize the authoritative support index before publication."""
        return {support.identity: support for support in supports}

    @staticmethod
    def _validate_observer_track_support_map(
        supports: tuple[ObserverTrackSupportState, ...],
        support_map: object,
    ) -> None:
        """Bind one prepared support index to its sealed canonical tuple."""
        if type(support_map) is not dict:
            raise ValueError(
                "fog-of-war commit payload observer support map changed",
            )
        items = tuple(support_map.items())
        if len(items) != len(supports) or any(
            key is not support.identity or value is not support
            for (key, value), support in zip(
                items,
                supports,
                strict=True,
            )
        ):
            raise ValueError(
                "fog-of-war commit payload observer support map changed",
            )

    @staticmethod
    def _commit_payload_fingerprint(
        payload: _FogOfWarCommitPayload,
        reporting_sides: tuple[str, ...],
    ) -> str:
        return _update_plan_fingerprint(
            reporting_sides=reporting_sides,
            world_views=payload.world_views,
            current_detection_witnesses=(payload.current_detection_witnesses),
            observer_track_supports=payload.observer_track_supports,
            rng_state=payload.rng_state,
            intel_fusion=payload.intel_fusion,
            scan_counts=payload.scan_counts,
            receipts=payload.receipts,
        )

    def prepare_update_commit(
        self,
        publication: FogOfWarPublicationPlan,
    ) -> FogOfWarCommitPlan:
        """Materialize and validate a publication without changing live state."""
        if type(publication) is not FogOfWarPublicationPlan:
            raise TypeError("publication must be a FogOfWarPublicationPlan")
        with self._update_transaction_lock:
            transaction = publication._transaction
            workspace = self._validate_update_transaction(transaction)
            self._validate_publication_plan(workspace, publication)
            if self._prepared_update_commit is not None:
                raise RuntimeError("fog-of-war publication commit was already prepared")
            scan_count_values = workspace.publication_scan_count_values
            scan_count_values_binding = workspace.publication_scan_count_values_binding
            if (
                scan_count_values is None or scan_count_values_binding is None
            ):  # pragma: no cover - private precondition
                raise RuntimeError("fog-of-war publication scan counts are unavailable")
            scan_counts = publication._scan_counts
            self._validate_scan_count_snapshot_values(
                scan_counts,
                scan_count_values,
                field_name="fog-of-war publication",
                verify_snapshot_fingerprint=True,
            )
            if type(scan_count_values_binding.exact_builtin) is not bool:
                raise ValueError("fog-of-war scan-count binding flag changed")
            if scan_count_values_binding.exact_builtin:
                self._validate_scan_count_values_binding(
                    scan_count_values,
                    scan_count_values_binding,
                    field_name="fog-of-war publication",
                )
            observer_track_supports = _validated_observer_track_support_tuple(
                workspace.observer_track_supports,
                field_name="fog-of-war workspace observer supports",
            )
            observer_track_support_map = self._prepare_observer_track_support_map(
                observer_track_supports,
            )
            self._validate_observer_track_support_map(
                observer_track_supports,
                observer_track_support_map,
            )
            prepared_fusion = self._intel_fusion._prepare_commit_state(
                workspace.intel_fusion,
            )
            self._validate_update_aliases(
                workspace.world_views,
                prepared_fusion,
            )
            if self._rng.bit_generator.state != workspace.rng_state:
                raise RuntimeError("fog-of-war preparation changed conventional RNG")

            authoritative_receipts = tuple(
                workspace.side_workspaces[side].receipt for side in workspace.reporting_sides
            )
            public_receipts = publication.receipts
            outcome_source = workspace.outcome_source
            if outcome_source is None:  # pragma: no cover - private construction
                raise RuntimeError("fog-of-war outcome source is unavailable")
            outcome_source.freeze(workspace.reporting_sides)
            plan = FogOfWarCommitPlan(
                reporting_sides=workspace.reporting_sides,
                receipts=public_receipts,
                _publication=publication,
                _owner_token=self._update_owner_token,
                _generation=workspace.generation,
                _outcome_source=outcome_source,
            )
            payload = _FogOfWarCommitPayload(
                world_views=workspace.world_views,
                current_detection_witnesses=(workspace.current_detection_witnesses),
                observer_track_supports=observer_track_supports,
                observer_track_support_map=observer_track_support_map,
                receipts=authoritative_receipts,
                rng_state=workspace.rng_state,
                intel_fusion=prepared_fusion,
                scan_counts=scan_counts,
                scan_count_values=scan_count_values,
                scan_count_values_binding=scan_count_values_binding,
                fingerprint="",
            )
            payload.fingerprint = self._commit_payload_fingerprint(
                payload,
                workspace.reporting_sides,
            )
            workspace.commit_plan = plan
            workspace.prepared_scan_count_values_binding_fields = (
                scan_count_values_binding.keys,
                scan_count_values_binding.counts,
                scan_count_values_binding.exact_builtin,
            )
            workspace.commit_bindings = (
                workspace.reporting_sides,
                public_receipts,
                authoritative_receipts,
                publication,
                outcome_source,
                observer_track_support_map,
            )
            self._prepared_update_commit = plan
            self._prepared_update_payload = payload
            return plan

    def validate_prepared_update_commit(
        self,
        plan: FogOfWarCommitPlan,
    ) -> None:
        """Revalidate every fallible invariant before an outer owner commits."""
        with self._update_transaction_lock:
            workspace = self._validated_prepared_workspace(plan)
            payload = self._prepared_update_payload
            if payload is None:
                raise ValueError("fog-of-war commit payload is stale")
            publication = workspace.publication
            scan_count_values_binding = payload.scan_count_values_binding
            binding_fields = workspace.prepared_scan_count_values_binding_fields
            if (
                publication is None
                or payload.scan_counts is not publication._scan_counts
                or payload.scan_count_values is not workspace.publication_scan_count_values
                or scan_count_values_binding is not workspace.publication_scan_count_values_binding
                or binding_fields is None
                or scan_count_values_binding.keys is not binding_fields[0]
                or scan_count_values_binding.counts is not binding_fields[1]
                or scan_count_values_binding.exact_builtin is not binding_fields[2]
            ):
                raise ValueError("fog-of-war commit payload scan counts are stale")
            if scan_count_values_binding.exact_builtin:
                self._validate_scan_count_values_binding(
                    payload.scan_count_values,
                    scan_count_values_binding,
                    field_name="fog-of-war commit payload",
                )
            else:
                self._validate_scan_count_snapshot_values(
                    payload.scan_counts,
                    payload.scan_count_values,
                    field_name="fog-of-war commit payload",
                    verify_snapshot_fingerprint=True,
                )
            self._validate_observer_track_support_map(
                payload.observer_track_supports,
                payload.observer_track_support_map,
            )
            if (
                self._commit_payload_fingerprint(
                    payload,
                    workspace.reporting_sides,
                )
                != payload.fingerprint
            ):
                raise ValueError("fog-of-war commit payload was mutated")
            self._validate_update_aliases(
                payload.world_views,
                payload.intel_fusion,
            )
            if not self._detection._live_scan_count_values_equal(
                workspace.baseline_scan_count_values,
            ):
                raise RuntimeError(
                    "live fog-of-war scan counts changed before publication",
                )
            if self._live_update_fingerprint(workspace.reporting_sides) != workspace.start_live_fingerprint:
                raise RuntimeError("live fog-of-war state changed before publication")
            if payload.rng_state != workspace.rng_state or self._rng.bit_generator.state != workspace.rng_state:
                raise RuntimeError("fog-of-war preparation changed conventional RNG")

    def _validated_prepared_workspace(
        self,
        plan: FogOfWarCommitPlan,
    ) -> _FogOfWarUpdateWorkspace:
        """Return the workspace for one exact active prepared plan."""
        if type(plan) is not FogOfWarCommitPlan:
            raise TypeError("plan must be a FogOfWarCommitPlan")
        workspace = self._update_workspace
        if workspace is None or workspace.commit_plan is not plan:
            raise ValueError("fog-of-war commit plan is foreign or stale")
        transaction = workspace.transaction
        publication = workspace.publication
        if (
            transaction is None
            or publication is None
            or plan._publication is not publication
            or plan._owner_token is not self._update_owner_token
            or self._prepared_update_commit is not plan
            or self._active_publication_plan is not publication
            or type(plan._generation) is not int
            or plan._generation is not workspace.generation
        ):
            raise ValueError("fog-of-war commit plan is foreign or stale")
        self._validate_update_transaction(transaction)
        self._validate_publication_plan(workspace, publication)
        (
            reporting_sides,
            public_receipts,
            authoritative_receipts,
            expected_publication,
            outcome_source,
            expected_support_map,
        ) = workspace.commit_bindings
        payload = self._prepared_update_payload
        if (
            plan.reporting_sides is not reporting_sides
            or plan.receipts is not public_receipts
            or not _exact_fow_receipt_tuple_matches(
                plan.receipts,
                authoritative_receipts,
            )
            or plan._publication is not expected_publication
            or plan._outcome_source is not outcome_source
            or payload is None
            or payload.observer_track_support_map is not expected_support_map
        ):
            raise ValueError("fog-of-war commit plan metadata was mutated")
        return workspace

    def _prepared_outcomes_for_owner(
        self,
        plan: FogOfWarCommitPlan,
    ) -> tuple[FogOfWarCycleOutcome, ...]:
        """Return ephemeral read-only outcomes over the pending live graph.

        This manager-private projection is valid only while ``plan`` is the
        active prepared commit.  Its world views alias the authoritative
        payload and must not be mutated or retained beyond the outer commit.
        Immutable receipts, witnesses, and support records are safely shared.
        """
        with self._update_transaction_lock:
            workspace = self._validated_prepared_workspace(plan)
            payload = self._prepared_update_payload
            (
                _reporting_sides,
                _public_receipts,
                authoritative_receipts,
                _publication,
                _outcome_source,
                _support_map,
            ) = workspace.commit_bindings
            if (
                payload is None
                or payload.world_views is not workspace.world_views
                or payload.current_detection_witnesses is not workspace.current_detection_witnesses
                or payload.observer_track_supports is not workspace.observer_track_supports
                or payload.receipts is not authoritative_receipts
            ):
                raise ValueError("fog-of-war commit payload is stale")
            return tuple(
                _FogOfWarOutcomeSource._workspace_outcome(workspace, side) for side in workspace.reporting_sides
            )

    def _commit_prevalidated_update(
        self,
        plan: FogOfWarCommitPlan,
    ) -> None:
        """Publish a fully validated update using only bounded state swaps."""
        with self._update_transaction_lock:
            workspace = self._update_workspace
            if (
                workspace is None or workspace.commit_plan is not plan or self._prepared_update_commit is not plan
            ):  # pragma: no cover - private precondition
                raise RuntimeError("fog-of-war commit workspace is unavailable")
            payload = self._prepared_update_payload
            if payload is None:  # pragma: no cover - private precondition
                raise RuntimeError("fog-of-war commit payload is unavailable")
            self._retire_update_previews(workspace)
            self._detection._commit_prevalidated_scan_counts(
                payload.scan_count_values,
            )
            self._intel_fusion._commit_prevalidated_fow_state(
                payload.intel_fusion,
            )
            self._world_views = payload.world_views
            with self._witness_lock:
                self._current_detection_witnesses = payload.current_detection_witnesses
                self._observer_track_supports = payload.observer_track_support_map
            self._active_update_transaction = None
            self._update_workspace = None
            self._active_publication_plan = None
            self._prepared_update_commit = None
            self._prepared_update_payload = None
            self._update_in_progress_sides.clear()
            self._issued_side_plans.clear()

    def commit_prepared_update(
        self,
        plan: FogOfWarCommitPlan,
    ) -> None:
        """Validate and publish one standalone commit-ready update."""
        self.validate_prepared_update_commit(plan)
        self._commit_prevalidated_update(plan)

    def commit_update_transaction(
        self,
        publication: FogOfWarPublicationPlan,
    ) -> None:
        """Compatibility wrapper for standalone prevalidated publication."""
        self.commit_prepared_update(self.prepare_update_commit(publication))

    def update(
        self,
        side: str,
        own_units: list[dict[str, Any]],
        enemy_units: list[dict[str, Any]],
        dt: float,
        current_time: float = 0.0,
        decoys: list[Decoy] | None = None,
        detection_culling: bool = True,
        scan_scheduling: bool = False,
        current_tick: int = 0,
        unit_arrays: Any | None = None,
        rng: np.random.Generator | None = None,
        visibility_m: float = 10000.0,
        illumination_lux: float = 100.0,
        thermal_contrast: float = 1.0,
        ambient_noise_db: float = 70.0,
        atmospheric_atten_db_per_km: float = 0.01,
        transmission_loss: float | None = None,
        jam_snr_penalty_db: float = 0.0,
    ) -> SideWorldView:
        """Reject the owner-incomplete legacy update boundary.

        The retained signature gives callers a deterministic migration error;
        it cannot supply the complete-side transaction, cadence plan, indexed
        RNG allocation, receipt, or atomic outer commit required by the
        supported update path.
        """
        raise UnsupportedLegacyFogOfWarUpdateError(
            "FogOfWarManager.update() is unsupported because it cannot carry "
            "the receipt-bearing complete-side transaction. Production callers "
            "must use BattleManager.prepare_tactical_interval(); direct "
            "integrations must use begin_update_transaction(), "
            "update_with_receipt(), prevalidate_update_transaction(), "
            "commit_update_transaction(), and the typed cadence/indexed-RNG "
            "commit owners.",
        )

    # ------------------------------------------------------------------
    # 12a-7: COP sharing via data links
    # ------------------------------------------------------------------

    def set_data_link_networks(
        self,
        networks: dict[str, list[str]],
    ) -> None:
        """Register data link network memberships.

        Parameters
        ----------
        networks:
            Dict of network_name → list of unit_ids.
            E.g. {"link16": ["unit_a", "unit_b"], "fbcb2": ["unit_c", "unit_d"]}
        """
        self._data_link_networks = {k: list(v) for k, v in networks.items()}
        self._unit_networks.clear()
        for net_name, members in self._data_link_networks.items():
            for uid in members:
                if uid not in self._unit_networks:
                    self._unit_networks[uid] = set()
                self._unit_networks[uid].add(net_name)

    def share_cop(
        self,
        side: str,
        unit_contacts: dict[str, dict[str, ContactRecord]],
        current_time: float = 0.0,
    ) -> None:
        """Share contacts laterally among data-linked units on the same side.

        Parameters
        ----------
        unit_contacts:
            Dict of unit_id → {contact_id: ContactRecord} for units on this side.
        current_time:
            Current simulation time for track age filtering.
        """
        if not self._dl_config.enable_cop_sharing:
            return

        wv = self.get_world_view(side)
        max_age = self._dl_config.max_track_age_s
        degradation = self._dl_config.track_degradation_per_hop

        # For each network, share contacts among members
        for net_name, members in self._data_link_networks.items():
            # Collect all contacts from members of this network
            shared_contacts: dict[str, tuple[ContactRecord, str]] = {}
            for uid in members:
                if uid not in unit_contacts:
                    continue
                for cid, cr in unit_contacts[uid].items():
                    # Check track age
                    age = current_time - cr.last_sensor_contact_time
                    if age > max_age:
                        continue
                    if cid not in shared_contacts:
                        shared_contacts[cid] = (cr, uid)

            # Distribute shared contacts to all network members' world view
            for cid, (cr, source_uid) in shared_contacts.items():
                if cid not in wv.contacts:
                    # Add with degraded confidence
                    degraded_info = ContactInfo(
                        level=cr.contact_info.level,
                        domain_estimate=cr.contact_info.domain_estimate,
                        type_estimate=cr.contact_info.type_estimate,
                        specific_estimate=cr.contact_info.specific_estimate,
                        confidence=max(0.1, cr.contact_info.confidence - degradation),
                    )
                    wv.contacts[cid] = ContactRecord(
                        contact_id=cid,
                        track=cr.track,
                        contact_info=degraded_info,
                        first_detected_time=cr.first_detected_time,
                        last_sensor_contact_time=cr.last_sensor_contact_time,
                        reporting_sensors=list(cr.reporting_sensors),
                    )

    # ------------------------------------------------------------------
    # Ground truth comparison
    # ------------------------------------------------------------------

    @staticmethod
    def ground_truth_comparison(
        world_view: SideWorldView,
        actual_positions: dict[str, Position],
    ) -> dict[str, Any]:
        """Compare belief state to ground truth for validation.

        Returns dict with position errors, false tracks, missed units.
        """
        detected_ids = set(world_view.contacts.keys())
        actual_ids = set(actual_positions.keys())

        correct_detections = detected_ids & actual_ids
        false_tracks = detected_ids - actual_ids
        missed_units = actual_ids - detected_ids

        position_errors: dict[str, float] = {}
        for cid in correct_detections:
            cr = world_view.contacts[cid]
            actual = actual_positions[cid]
            est_x, est_y = cr.track.state.position
            dx = est_x - actual.easting
            dy = est_y - actual.northing
            position_errors[cid] = float(np.sqrt(dx * dx + dy * dy))

        return {
            "correct_detections": len(correct_detections),
            "false_tracks": len(false_tracks),
            "missed_units": len(missed_units),
            "position_errors": position_errors,
            "total_contacts": len(detected_ids),
            "total_actual": len(actual_ids),
        }

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def validate_checkpoint_boundary(self) -> None:
        """Reject live state omitted from the Phase 116 envelope."""
        with self._update_transaction_lock:
            if self._active_update_transaction is not None:
                raise RuntimeError(
                    "fog-of-war checkpoint is unavailable during an active update transaction",
                )
            if self._active_witness_clear is not None:
                raise RuntimeError(
                    "fog-of-war checkpoint is unavailable during an active witness clear",
                )
            if self._update_transaction_poisoned:
                raise RuntimeError(
                    "fog-of-war checkpoint is unavailable after a poisoned update transaction",
                )
        decoys = getattr(self._deception, "_decoys", None)
        decoy_counter = getattr(self._deception, "_decoy_counter", None)
        if decoys != {} or decoy_counter != 0:
            raise ValueError(
                "Fog-of-war checkpointing with retained deception state is unsupported (REM-046)",
            )
        if (
            self._dl_config.model_dump(mode="python") != DataLinkConfig().model_dump(mode="python")
            or self._data_link_networks
            or self._unit_networks
        ):
            raise ValueError(
                "Fog-of-war checkpointing with custom or populated COP/data-link state is unsupported (REM-036)",
            )

    def validate_runtime_bindings(
        self,
        *,
        detection_engine: DetectionEngine,
        authoritative_rng: np.random.Generator,
    ) -> None:
        """Require the exact production detection owner and RNG topology."""
        if self._detection is not detection_engine:
            raise ValueError(
                "FogOfWarManager must use the context DetectionEngine owner",
            )
        if self._rng is not authoritative_rng:
            raise ValueError(
                "FogOfWarManager must use RNGManager's DETECTION generator",
            )
        self.validate_internal_bindings()

    def validate_internal_bindings(self) -> None:
        """Require every standalone FOW child to share its owner RNG."""
        rng_owners: list[tuple[str, Any]] = [
            ("DetectionEngine", self._detection),
            ("FogOfWarManager StateEstimator", self._estimator),
            ("IntelFusionEngine", self._intel_fusion),
            ("IntelFusionEngine StateEstimator", self._intel_fusion._estimator),
            ("DeceptionEngine", self._deception),
        ]
        if self._identification is not None:
            rng_owners.append(("IdentificationEngine", self._identification))
        for label, owner in rng_owners:
            if getattr(owner, "_rng", None) is not self._rng:
                raise ValueError(
                    f"{label} must share FogOfWarManager's RNG",
                )

    def validate_live_contact_bindings(self) -> None:
        """Require every ordinary contact to alias its fusion-owned track."""
        for side, world_view in self._world_views.items():
            fusion_tracks = self._intel_fusion._tracks.get(side, {})
            for contact in world_view.contacts.values():
                if fusion_tracks.get(contact.track.track_id) is not contact.track:
                    raise ValueError(
                        "Fog-of-war contact must alias its exact fusion-owned track",
                    )
        with self._witness_lock:
            supports = tuple(self._observer_track_supports.items())
        for identity, support in supports:
            attachment_identity = identity.attachment_identity
            world_view = self._world_views.get(
                attachment_identity.reporting_side,
            )
            contact = None if world_view is None else world_view.contacts.get(identity.target_id)
            if (
                identity != support.identity
                or contact is None
                or contact.track.track_id != support.fusion_track_id
                or self._intel_fusion._tracks.get(
                    attachment_identity.reporting_side,
                    {},
                ).get(support.fusion_track_id)
                is not contact.track
            ):
                raise ValueError(
                    "Fog-of-war observer track support must bind its exact live fusion contact",
                )

    def _capture_checkpoint_state(self) -> dict[str, Any]:
        """Serialize the live owner once without independently restaging it."""
        self.validate_checkpoint_boundary()
        self.validate_live_contact_bindings()
        with self._witness_lock:
            witnesses = {
                side: [witness.get_state() for witness in side_witnesses]
                for side, side_witnesses in sorted(
                    self._current_detection_witnesses.items(),
                )
            }
            observer_track_supports = [
                observer_track_support_state_to_state(support)
                for support in sorted(
                    self._observer_track_supports.values(),
                    key=lambda support: support.identity.sort_key(),
                )
            ]
        state = {
            "world_views": {side: wv.get_state() for side, wv in sorted(self._world_views.items())},
            "current_detection_witnesses": witnesses,
            "observer_track_supports": observer_track_supports,
            "rng_state": copy.deepcopy(self._rng.bit_generator.state),
            "intel_fusion": self._intel_fusion.get_state(),
            "scan_counts": self._detection.get_scan_count_state(),
            "cadence": self._cadence.get_state(),
        }
        return state

    def capture_checkpoint_snapshot(
        self,
        *,
        expected_sides: set[str] | None = None,
        expected_target_sides: dict[str, str] | None = None,
        satellite_topology: dict[str, tuple[str, str]] | None = None,
        checkpoint_elapsed_s: float | None = None,
        authoritative_rng_state: dict[str, Any] | None = None,
        authoritative_detection_scan_counts: object | None = None,
        expected_sensor_bindings: (tuple[FogOfWarSensorBinding, ...] | None) = None,
        expected_cadence_sensor_bindings: (tuple[FogOfWarSensorBinding, ...] | None) = None,
        expected_cadence_bindings: (tuple[FogOfWarCadenceBinding, ...] | None) = None,
        expected_native_phase_bindings: (tuple[FogOfWarNativePhaseBinding, ...] | None) = None,
    ) -> FogOfWarCheckpointSnapshot:
        """Capture once and return the exact owner-bound validation plan."""
        state = self._capture_checkpoint_state()
        plan = self.stage_state(
            state,
            expected_sides=expected_sides,
            expected_target_sides=expected_target_sides,
            satellite_topology=satellite_topology,
            checkpoint_elapsed_s=checkpoint_elapsed_s,
            authoritative_rng_state=authoritative_rng_state,
            authoritative_detection_scan_counts=(authoritative_detection_scan_counts),
            expected_sensor_bindings=expected_sensor_bindings,
            expected_cadence_sensor_bindings=(expected_cadence_sensor_bindings),
            expected_cadence_bindings=expected_cadence_bindings,
            expected_native_phase_bindings=(expected_native_phase_bindings),
        )
        return FogOfWarCheckpointSnapshot(_state=state, plan=plan)

    def get_state(self) -> dict[str, Any]:
        """Capture and validate canonical FOW state for compatibility callers."""
        return self.capture_checkpoint_snapshot().state

    def validate_cadence_restore_bindings(
        self,
        plan: FogOfWarRestorePlan,
        *,
        expected_sensor_bindings: tuple[FogOfWarSensorBinding, ...],
        expected_cadence_sensor_bindings: tuple[
            FogOfWarSensorBinding,
            ...,
        ],
        expected_cadence_bindings: tuple[FogOfWarCadenceBinding, ...],
        expected_native_phase_bindings: tuple[
            FogOfWarNativePhaseBinding,
            ...,
        ],
    ) -> None:
        """Bind staged cadence identity and periods to runtime/Battle owners."""
        if type(plan) is not FogOfWarRestorePlan or plan._owner_token is not self._plan_owner_token:
            raise ValueError("fog-of-war restore plan is foreign")
        if _restore_plan_fingerprint(plan) != plan._fingerprint:
            raise ValueError("fog-of-war restore plan was mutated")
        if type(expected_sensor_bindings) is not tuple:
            raise TypeError("expected_sensor_bindings must be an immutable tuple")
        if type(expected_cadence_sensor_bindings) is not tuple:
            raise TypeError(
                "expected_cadence_sensor_bindings must be an immutable tuple",
            )
        if type(expected_cadence_bindings) is not tuple:
            raise TypeError("expected_cadence_bindings must be an immutable tuple")
        if type(expected_native_phase_bindings) is not tuple:
            raise TypeError(
                "expected_native_phase_bindings must be an immutable tuple",
            )
        if any(type(binding) is not FogOfWarSensorBinding for binding in expected_sensor_bindings):
            raise TypeError("expected_sensor_bindings contains an invalid binding")
        if any(type(binding) is not FogOfWarSensorBinding for binding in expected_cadence_sensor_bindings):
            raise TypeError(
                "expected_cadence_sensor_bindings contains an invalid binding",
            )
        if any(type(binding) is not FogOfWarCadenceBinding for binding in expected_cadence_bindings):
            raise TypeError("expected_cadence_bindings contains an invalid binding")
        if any(type(binding) is not FogOfWarNativePhaseBinding for binding in expected_native_phase_bindings):
            raise TypeError(
                "expected_native_phase_bindings contains an invalid binding",
            )

        sensor_identities = tuple(binding.cadence_identity for binding in expected_sensor_bindings)
        cadence_sensor_identities = tuple(binding.cadence_identity for binding in expected_cadence_sensor_bindings)
        cadence_identities = tuple(binding.identity for binding in expected_cadence_bindings)
        native_phase_identities = tuple(binding.identity for binding in expected_native_phase_bindings)
        expected_order = tuple(sorted(cadence_identities, key=TacticalAttachmentIdentity.sort_key))
        expected_native_phase_order = tuple(
            sorted(
                native_phase_identities,
                key=TacticalAttachmentIdentity.sort_key,
            )
        )
        if cadence_identities != expected_order:
            raise ValueError("expected cadence bindings are not canonically ordered")
        if native_phase_identities != expected_native_phase_order:
            raise ValueError(
                "expected native phase bindings are not canonically ordered",
            )
        if len(set(sensor_identities)) != len(sensor_identities):
            raise ValueError("expected sensor bindings contain duplicate cadence identities")
        if len(set(cadence_sensor_identities)) != len(cadence_sensor_identities):
            raise ValueError(
                "expected cadence sensor bindings contain duplicate identities",
            )
        if len(set(cadence_identities)) != len(cadence_identities):
            raise ValueError("expected cadence bindings contain duplicate identities")
        if len(set(native_phase_identities)) != len(native_phase_identities):
            raise ValueError(
                "expected native phase bindings contain duplicate identities",
            )
        if not set(cadence_sensor_identities) <= set(sensor_identities):
            raise ValueError(
                "cadence sensor bindings are absent from the full checkpoint roster",
            )
        if set(cadence_sensor_identities) != set(cadence_identities):
            raise ValueError(
                "cadence sensor and cadence-period attachment rosters disagree",
            )
        if set(native_phase_identities) != set(sensor_identities):
            raise ValueError(
                "native phase bindings must cover the complete runtime sensor roster",
            )

        cadence_plan = plan._cadence_plan
        attachment_states = cadence_plan.attachment_states
        assignments = cadence_plan.phase_assignments
        assignment_identities = tuple(assignment.identity for assignment in assignments)
        if not set(assignment_identities) <= set(native_phase_identities):
            raise ValueError(
                "checkpoint native phase registry contains identities absent from runtime loadouts",
            )
        native_phase_by_identity = {binding.identity: binding for binding in expected_native_phase_bindings}
        for assignment in assignments:
            expected = native_phase_by_identity[assignment.identity]
            if assignment.native_period != expected.native_period:
                raise ValueError(
                    "checkpoint native phase period disagrees with runtime configuration",
                )
        if cadence_plan.committed_ordinal == 0:
            if attachment_states or assignments:
                raise ValueError(
                    "uncommitted cadence cannot retain attachment or assignment state",
                )
            return
        staged_identities = tuple(state.identity for state in attachment_states)
        if staged_identities != cadence_identities:
            raise ValueError("checkpoint cadence roster disagrees with runtime attachments")
        expected_by_identity = {binding.identity: binding for binding in expected_cadence_bindings}
        for state in attachment_states:
            expected = expected_by_identity[state.identity]
            if state.native_period != expected.native_period:
                raise ValueError("checkpoint native cadence period disagrees with runtime configuration")
            if state.current_lod_period != expected.current_lod_period:
                raise ValueError("checkpoint LOD cadence period disagrees with Battle tier state")

    def stage_state(
        self,
        state: dict[str, Any],
        *,
        expected_sides: set[str] | None = None,
        expected_target_sides: dict[str, str] | None = None,
        satellite_topology: dict[str, tuple[str, str]] | None = None,
        checkpoint_elapsed_s: float | None = None,
        authoritative_rng_state: dict[str, Any] | None = None,
        authoritative_detection_scan_counts: object | None = None,
        expected_sensor_bindings: (tuple[FogOfWarSensorBinding, ...] | None) = None,
        expected_cadence_sensor_bindings: (tuple[FogOfWarSensorBinding, ...] | None) = None,
        expected_cadence_bindings: (tuple[FogOfWarCadenceBinding, ...] | None) = None,
        expected_native_phase_bindings: (tuple[FogOfWarNativePhaseBinding, ...] | None) = None,
        allow_legacy_state: bool = False,
    ) -> FogOfWarRestorePlan:
        """Validate fog/fusion state without mutating the live manager."""
        self.validate_checkpoint_boundary()
        self.validate_internal_bindings()
        if type(allow_legacy_state) is not bool:
            raise ValueError("allow_legacy_state must be a boolean")
        if not isinstance(state, dict):
            raise ValueError("Fog-of-war state must be a mapping")
        modern_keys = {
            "world_views",
            "current_detection_witnesses",
            "observer_track_supports",
            "rng_state",
            "intel_fusion",
            "scan_counts",
            "cadence",
        }
        legacy_key_sets = (
            {
                "world_views",
                "rng_state",
                "intel_fusion",
            },
            {
                "world_views",
                "current_detection_witnesses",
                "rng_state",
                "intel_fusion",
            },
        )
        if allow_legacy_state and "cadence" in state:
            raise ValueError(
                "Versionless fog-of-war state cannot supply modern cadence state",
            )
        valid_topology = (not allow_legacy_state and set(state) == modern_keys) or (
            allow_legacy_state and set(state) in legacy_key_sets
        )
        if not valid_topology:
            raise ValueError(
                "Fog-of-war state keys have invalid topology",
            )
        if "cadence" in state:
            cadence_state = copy.deepcopy(state["cadence"])
        else:
            cadence_state = TacticalCadenceScheduler(
                complete_from_tick_zero=False,
            ).get_state()
        cadence_plan = self._cadence.stage_state(cadence_state)
        scan_count_state = state.get("scan_counts", {})
        scan_counts = self._detection.stage_scan_count_state(
            scan_count_state,
        )
        if authoritative_detection_scan_counts is not None:
            authoritative_scan_counts = self._detection.stage_scan_count_state(
                authoritative_detection_scan_counts,
            )
            if scan_counts.entries != authoritative_scan_counts.entries:
                raise ValueError(
                    "Fog-of-war scan counts disagree with DetectionEngine state",
                )
        elapsed: float | None = None
        if checkpoint_elapsed_s is not None:
            if (
                isinstance(checkpoint_elapsed_s, bool)
                or not isinstance(checkpoint_elapsed_s, (int, float))
                or not math.isfinite(float(checkpoint_elapsed_s))
                or float(checkpoint_elapsed_s) < 0.0
            ):
                raise ValueError(
                    "Fog-of-war checkpoint time must be finite and non-negative",
                )
            elapsed = float(checkpoint_elapsed_s)

        rng_state = copy.deepcopy(state["rng_state"])
        if not isinstance(rng_state, dict):
            raise ValueError("Fog-of-war rng_state must be a mapping")
        try:
            staged_rng = copy.deepcopy(self._rng)
            staged_rng.bit_generator.state = rng_state
        except (TypeError, ValueError) as exc:
            raise ValueError("Fog-of-war rng_state is invalid") from exc
        if authoritative_rng_state is not None and rng_state != authoritative_rng_state:
            raise ValueError(
                "Fog-of-war RNG mirror disagrees with RNGManager DETECTION state",
            )

        fusion_plan = self._intel_fusion.stage_state(
            state["intel_fusion"],
            expected_sides=expected_sides,
            expected_target_sides=expected_target_sides,
            satellite_topology=satellite_topology,
            checkpoint_elapsed_s=elapsed,
            authoritative_rng_state=authoritative_rng_state,
        )
        if fusion_plan["rng_state"] != rng_state:
            raise ValueError(
                "Fog-of-war and IntelFusion RNG mirrors disagree",
            )

        bindings_by_unit: (
            dict[
                str,
                dict[tuple[int, str, str], FogOfWarSensorBinding],
            ]
            | None
        ) = None
        sensor_ids_by_side: dict[str, set[str]] = {}
        if expected_sensor_bindings is not None:
            if not isinstance(expected_sensor_bindings, tuple):
                raise ValueError(
                    "expected_sensor_bindings must be an immutable tuple",
                )
            bindings_by_unit = {}
            for binding in expected_sensor_bindings:
                if not isinstance(binding, FogOfWarSensorBinding):
                    raise ValueError(
                        "expected_sensor_bindings contains an invalid binding",
                    )
                if expected_target_sides is None or (expected_target_sides.get(binding.unit_id) != binding.side):
                    raise ValueError(
                        "Sensor binding disagrees with the staged roster side",
                    )
                identity = (
                    binding.source_equipment_index,
                    binding.sensor_id,
                    binding.modeled_role,
                )
                unit_bindings = bindings_by_unit.setdefault(
                    binding.unit_id,
                    {},
                )
                if identity in unit_bindings:
                    raise ValueError(
                        "Duplicate expected fog-of-war sensor binding",
                    )
                unit_bindings[identity] = binding
                sensor_ids_by_side.setdefault(binding.side, set()).add(
                    binding.sensor_id,
                )

        raw_world_views = state["world_views"]
        if not isinstance(raw_world_views, dict):
            raise ValueError("Fog-of-war world_views must be a mapping")
        if tuple(raw_world_views) != tuple(sorted(raw_world_views)):
            raise ValueError("Fog-of-war world views are not canonically ordered")
        world_views: dict[str, SideWorldView] = {}
        referenced_fow_tracks: dict[str, set[str]] = {}
        view_keys = {"side", "contacts", "last_update_time"}
        for side, raw_view in raw_world_views.items():
            if not isinstance(side, str) or not side or side != side.strip():
                raise ValueError(
                    "Fog-of-war side keys must be non-empty trimmed strings",
                )
            if expected_sides is not None and side not in expected_sides:
                raise ValueError(f"Unknown fog-of-war side {side!r}")
            if not isinstance(raw_view, dict) or set(raw_view) != view_keys:
                raise ValueError(
                    f"Fog-of-war view {side!r} has invalid keys",
                )
            if raw_view["side"] != side:
                raise ValueError(
                    "Fog-of-war view map key disagrees with serialized side",
                )
            if not isinstance(raw_view["contacts"], dict):
                raise ValueError(
                    f"Fog-of-war contacts for {side!r} must be a mapping",
                )
            raw_contacts = raw_view["contacts"]
            if tuple(raw_contacts) != tuple(sorted(raw_contacts)):
                raise ValueError(
                    f"Fog-of-war contacts for {side!r} are not canonical",
                )
            last_update = raw_view["last_update_time"]
            if (
                isinstance(last_update, bool)
                or not isinstance(last_update, (int, float))
                or not math.isfinite(float(last_update))
                or float(last_update) < 0.0
            ):
                raise ValueError(
                    "Fog-of-war last_update_time must be finite and non-negative",
                )
            normalized_time = float(last_update)
            if elapsed is not None and normalized_time > elapsed:
                raise ValueError(
                    "Fog-of-war update time is after checkpoint time",
                )
            contacts: dict[str, ContactRecord] = {}
            referenced_track_ids: set[str] = set()
            for contact_id, raw_contact in raw_contacts.items():
                _require_witness_id(contact_id, "fog-of-war contact map key")
                if not isinstance(raw_contact, dict) or set(raw_contact) != _CONTACT_STATE_KEYS:
                    raise ValueError(
                        f"Fog-of-war contact {contact_id!r} has invalid keys",
                    )
                if raw_contact["contact_id"] != contact_id:
                    raise ValueError(
                        "Fog-of-war contact key disagrees with contact_id",
                    )
                if expected_target_sides is not None:
                    target_side = expected_target_sides.get(contact_id)
                    if target_side is None:
                        raise ValueError(
                            "Fog-of-war contact target is absent from the staged roster",
                        )
                    if target_side == side:
                        raise ValueError(
                            "Fog-of-war ordinary contact target must be hostile",
                        )

                raw_track = raw_contact["track"]
                if not isinstance(raw_track, dict) or set(raw_track) != _TRACK_STATE_KEYS:
                    raise ValueError(
                        "Fog-of-war contact track has invalid keys",
                    )
                track_id = validate_fow_track_id(raw_track["track_id"])
                if track_id in referenced_track_ids:
                    raise ValueError(
                        "Fog-of-war contacts share one fusion track",
                    )
                referenced_track_ids.add(track_id)
                track = fusion_plan["tracks"].get(side, {}).get(track_id)
                if track is None:
                    raise ValueError(
                        "Fog-of-war contact references a missing side-owned fusion track",
                    )
                if raw_track != track.get_state():
                    raise ValueError(
                        "Fog-of-war contact track disagrees with fusion state",
                    )
                if track.side != side:
                    raise ValueError(
                        "Fog-of-war contact track has the wrong owner",
                    )
                _stage_contact_info(
                    raw_track["contact_info"],
                    field_name="Fog-of-war track contact_info",
                    allow_unknown=False,
                )

                covariance = np.asarray(
                    track.state.covariance,
                    dtype=np.float64,
                )
                if np.any(np.diag(covariance) < 0.0):
                    raise ValueError(
                        "Fog-of-war track covariance has a negative diagonal",
                    )
                if not np.allclose(
                    covariance,
                    covariance.T,
                    rtol=1e-12,
                    atol=1e-9,
                ):
                    raise ValueError(
                        "Fog-of-war track covariance is not symmetric",
                    )
                symmetric_covariance = (covariance + covariance.T) * 0.5
                eigenvalues = np.linalg.eigvalsh(symmetric_covariance)
                eigen_tolerance = -1e-10 * max(
                    1.0,
                    float(np.max(np.abs(covariance))),
                )
                if float(np.min(eigenvalues)) < eigen_tolerance:
                    raise ValueError(
                        "Fog-of-war track covariance is not positive semidefinite",
                    )

                contact_info = _stage_contact_info(
                    raw_contact["contact_info"],
                    field_name="Fog-of-war contact_info",
                    allow_unknown=False,
                )
                first_detected = _strict_finite_number(
                    raw_contact["first_detected_time"],
                    "Fog-of-war first_detected_time",
                    non_negative=True,
                )
                last_sensor_contact = _strict_finite_number(
                    raw_contact["last_sensor_contact_time"],
                    "Fog-of-war last_sensor_contact_time",
                    non_negative=True,
                )
                if not (first_detected <= last_sensor_contact == track.state.last_update_time <= normalized_time):
                    raise ValueError(
                        "Fog-of-war contact chronology is inconsistent",
                    )

                reporting_sensors = raw_contact["reporting_sensors"]
                if not isinstance(reporting_sensors, list):
                    raise ValueError(
                        "Fog-of-war reporting_sensors must be a list",
                    )
                if not reporting_sensors:
                    raise ValueError(
                        "Fog-of-war reporting sensor provenance cannot be empty",
                    )
                normalized_sensors: list[str] = []
                for sensor_id in reporting_sensors:
                    _require_witness_id(
                        sensor_id,
                        "Fog-of-war reporting sensor ID",
                    )
                    if sensor_id in normalized_sensors:
                        raise ValueError(
                            "Fog-of-war reporting_sensors contains duplicates",
                        )
                    if bindings_by_unit is not None and sensor_id not in sensor_ids_by_side.get(side, set()):
                        raise ValueError(
                            "Fog-of-war reporting sensor does not resolve to a reporting-side staged attachment",
                        )
                    normalized_sensors.append(sensor_id)

                age_s = normalized_time - last_sensor_contact
                config = self._estimator.config
                if track.status is TrackStatus.TENTATIVE:
                    if track.hits >= config.confirmation_threshold:
                        raise ValueError(
                            "Fog-of-war TENTATIVE track has confirmed hit history",
                        )
                elif track.status is TrackStatus.CONFIRMED:
                    if track.hits < config.confirmation_threshold or age_s > config.coast_timeout_s:
                        raise ValueError(
                            "Fog-of-war CONFIRMED track disagrees with its hit history or age",
                        )
                elif track.status is TrackStatus.COASTING:
                    if (
                        track.hits < config.confirmation_threshold
                        or age_s > config.lost_timeout_s
                        or track.position_uncertainty > config.max_covariance_m
                    ):
                        raise ValueError(
                            "Fog-of-war COASTING track disagrees with its lifecycle bounds",
                        )
                else:
                    raise ValueError(
                        "Fog-of-war ordinary contact cannot be STALE or LOST",
                    )

                contacts[contact_id] = ContactRecord(
                    contact_id=contact_id,
                    track=track,
                    contact_info=contact_info,
                    first_detected_time=first_detected,
                    last_sensor_contact_time=last_sensor_contact,
                    reporting_sensors=normalized_sensors,
                )
            world_views[side] = SideWorldView(
                side=side,
                contacts=contacts,
                last_update_time=normalized_time,
            )
            referenced_fow_tracks[side] = referenced_track_ids

        for side, side_tracks in fusion_plan["tracks"].items():
            referenced = referenced_fow_tracks.get(side, set())
            for track_id, track in side_tracks.items():
                if (
                    track_id.startswith("fow-track-")
                    and track_id not in referenced
                    and track.status is not TrackStatus.LOST
                ):
                    raise ValueError(
                        "Live fusion FOW track has no ordinary contact owner",
                    )

        raw_witness_map = state.get("current_detection_witnesses", {})
        if not isinstance(raw_witness_map, dict):
            raise ValueError(
                "Fog-of-war current_detection_witnesses must be a mapping",
            )
        if tuple(raw_witness_map) != tuple(sorted(raw_witness_map)):
            raise ValueError(
                "Fog-of-war witness side map is not canonically ordered",
            )
        witnesses: dict[str, tuple[ObserverDetectionWitness, ...]] = {}
        for side, raw_witnesses in raw_witness_map.items():
            _require_witness_id(side, "fog-of-war witness side")
            if expected_sides is not None and side not in expected_sides:
                raise ValueError(f"Unknown fog-of-war witness side {side!r}")
            world_view = world_views.get(side)
            if world_view is None:
                raise ValueError(
                    "Fog-of-war witness side has no staged world view",
                )
            if not isinstance(raw_witnesses, list):
                raise ValueError(
                    "Fog-of-war side witnesses must be a list",
                )
            staged_witnesses = tuple(_stage_witness(raw, side=side) for raw in raw_witnesses)
            if staged_witnesses != tuple(
                sorted(staged_witnesses, key=self._witness_sort_key),
            ):
                raise ValueError(
                    "Fog-of-war detection witnesses are not canonically ordered",
                )
            witness_identities = [self._witness_sort_key(witness) for witness in staged_witnesses]
            if len(witness_identities) != len(set(witness_identities)):
                raise ValueError(
                    "Fog-of-war detection witnesses contain duplicates",
                )
            for witness in staged_witnesses:
                contact = world_view.contacts.get(witness.target_id)
                if contact is None:
                    raise ValueError(
                        "Fog-of-war witness target has no staged contact",
                    )
                if (
                    witness.logical_time_s != world_view.last_update_time
                    or witness.logical_time_s != contact.last_sensor_contact_time
                    or (elapsed is not None and witness.logical_time_s > elapsed)
                ):
                    raise ValueError(
                        "Fog-of-war witness chronology disagrees with its current contact",
                    )
                if witness.sensor_id not in contact.reporting_sensors:
                    raise ValueError(
                        "Fog-of-war witness sensor is absent from contact provenance",
                    )
                if expected_target_sides is not None:
                    if expected_target_sides.get(witness.observer_unit_id) != side:
                        raise ValueError(
                            "Fog-of-war witness observer is absent or on the wrong side",
                        )
                    target_side = expected_target_sides.get(witness.target_id)
                    if target_side is None or target_side == side:
                        raise ValueError(
                            "Fog-of-war witness target is absent or friendly",
                        )
                if bindings_by_unit is not None:
                    identity = (
                        witness.source_equipment_index,
                        witness.sensor_id,
                        witness.modeled_role,
                    )
                    binding = bindings_by_unit.get(
                        witness.observer_unit_id,
                        {},
                    ).get(identity)
                    if binding is None:
                        raise ValueError(
                            "Fog-of-war witness does not resolve to one exact observer sensor attachment",
                        )
                    if binding.sensor_type != witness.sensor_type:
                        raise ValueError(
                            "Fog-of-war witness sensor type disagrees with the staged attachment",
                        )
            witnesses[side] = staged_witnesses

        raw_observer_track_supports = state.get(
            "observer_track_supports",
            [],
        )
        if not isinstance(raw_observer_track_supports, list):
            raise ValueError(
                "Fog-of-war observer_track_supports must be a list",
            )
        try:
            observer_track_supports = tuple(
                observer_track_support_state_from_state(raw) for raw in raw_observer_track_supports
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid fog-of-war observer track support: {exc}",
            ) from exc
        if observer_track_supports != tuple(
            sorted(
                observer_track_supports,
                key=lambda support: support.identity.sort_key(),
            )
        ):
            raise ValueError(
                "Fog-of-war observer track supports are not canonically ordered",
            )
        support_identities = tuple(support.identity for support in observer_track_supports)
        if len(set(support_identities)) != len(support_identities):
            raise ValueError(
                "Fog-of-war observer track supports contain duplicates",
            )
        cadence_states = {cadence_state.identity: cadence_state for cadence_state in cadence_plan.attachment_states}
        for support in observer_track_supports:
            identity = support.identity
            attachment_identity = identity.attachment_identity
            side = attachment_identity.reporting_side
            world_view = world_views.get(side)
            contact = None if world_view is None else world_view.contacts.get(identity.target_id)
            cadence_attachment = cadence_states.get(attachment_identity)
            if (
                support.native_period <= 1
                or world_view is None
                or contact is None
                or contact.track.track_id != support.fusion_track_id
                or fusion_plan["tracks"]
                .get(side, {})
                .get(
                    support.fusion_track_id,
                )
                is not contact.track
                or contact.track.status in {TrackStatus.STALE, TrackStatus.LOST}
                or attachment_identity.sensor_id not in contact.reporting_sensors
                or support.observation_time_s > contact.last_sensor_contact_time
                or support.observation_time_s > world_view.last_update_time
                or (elapsed is not None and support.observation_time_s > elapsed)
                or cadence_attachment is None
                or cadence_attachment.native_period != support.native_period
                or cadence_attachment.native_phase_residue != support.native_phase_residue
                or cadence_attachment.native_next_due != support.native_due_ordinal
                or cadence_attachment.last_admission_ordinal != support.observation_ordinal
                or not support.observation_ordinal < cadence_plan.committed_ordinal <= support.native_due_ordinal
            ):
                raise ValueError(
                    "Fog-of-war observer track support is not bound to active contact, track, and cadence state",
                )
            if expected_sides is not None and side not in expected_sides:
                raise ValueError(
                    "Fog-of-war observer track support has an unknown side",
                )
            if expected_target_sides is not None:
                if expected_target_sides.get(
                    attachment_identity.observer_unit_id,
                ) != side or expected_target_sides.get(identity.target_id) in {None, side}:
                    raise ValueError(
                        "Fog-of-war observer track support must bind a live hostile target",
                    )
            if bindings_by_unit is not None:
                binding = bindings_by_unit.get(
                    attachment_identity.observer_unit_id,
                    {},
                ).get(
                    (
                        attachment_identity.source_equipment_index,
                        attachment_identity.sensor_id,
                        attachment_identity.modeled_role,
                    ),
                )
                if binding is None or binding.side != side or binding.sensor_type != support.sensor_type.name:
                    raise ValueError(
                        "Fog-of-war observer track support does not resolve to its exact radar attachment",
                    )

        plan = FogOfWarRestorePlan(
            _world_views=world_views,
            _current_detection_witnesses=witnesses,
            _observer_track_supports=observer_track_supports,
            _rng_state=rng_state,
            _intel_fusion=fusion_plan,
            _scan_counts=scan_counts,
            _cadence_state=cadence_state,
            _cadence_plan=cadence_plan,
            _owner_token=self._plan_owner_token,
            _structure_fingerprint="",
            _fingerprint="",
        )
        plan = replace(
            plan,
            _structure_fingerprint=(_restore_plan_structure_fingerprint(plan)),
        )
        final_plan = replace(
            plan,
            _fingerprint=_restore_plan_fingerprint(plan),
        )
        cadence_binding_inputs = (
            expected_cadence_sensor_bindings,
            expected_cadence_bindings,
            expected_native_phase_bindings,
        )
        if any(value is None for value in cadence_binding_inputs) and any(
            value is not None for value in cadence_binding_inputs
        ):
            raise ValueError(
                "cadence sensor, period, and native phase bindings must be supplied together",
            )
        if expected_cadence_bindings is not None:
            if (
                expected_sensor_bindings is None
                or expected_cadence_sensor_bindings is None
                or expected_native_phase_bindings is None
            ):
                raise ValueError(
                    "expected cadence bindings require full and cadence sensor bindings",
                )
            self.validate_cadence_restore_bindings(
                final_plan,
                expected_sensor_bindings=expected_sensor_bindings,
                expected_cadence_sensor_bindings=(expected_cadence_sensor_bindings),
                expected_cadence_bindings=expected_cadence_bindings,
                expected_native_phase_bindings=(expected_native_phase_bindings),
            )
        return final_plan

    def commit_state(self, staged_state: FogOfWarRestorePlan) -> None:
        """Commit a non-throwing fog/fusion restore plan."""
        if type(staged_state) is not FogOfWarRestorePlan:
            raise TypeError("plan must be a fog-of-war restore plan")
        if (
            staged_state._owner_token is not self._plan_owner_token
            or type(staged_state._structure_fingerprint) is not str
            or type(staged_state._fingerprint) is not str
        ):
            raise ValueError(
                "Fog-of-war restore plan is foreign or was mutated",
            )
        try:
            structure_fingerprint = _restore_plan_structure_fingerprint(staged_state)
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                "Fog-of-war restore plan is foreign or was mutated",
            ) from exc
        if staged_state._structure_fingerprint != structure_fingerprint:
            raise ValueError(
                "Fog-of-war restore plan is foreign or was mutated",
            )
        scan_count_values = self._detection._validated_scan_counts(
            staged_state._scan_counts,
        )
        try:
            (
                world_views,
                current_detection_witnesses,
                observer_track_supports,
                rng_state,
                intel_fusion,
                cadence_state,
            ) = copy.deepcopy(
                (
                    staged_state._world_views,
                    staged_state._current_detection_witnesses,
                    staged_state._observer_track_supports,
                    staged_state._rng_state,
                    staged_state._intel_fusion,
                    staged_state._cadence_state,
                ),
            )
            cadence_plan = staged_state._cadence_plan
            scan_counts = staged_state._scan_counts
            publication = replace(
                staged_state,
                _world_views=world_views,
                _current_detection_witnesses=(current_detection_witnesses),
                _observer_track_supports=observer_track_supports,
                _rng_state=rng_state,
                _intel_fusion=intel_fusion,
                _scan_counts=scan_counts,
                _cadence_state=cadence_state,
                _cadence_plan=cadence_plan,
            )
            publication_structure_fingerprint = _restore_plan_structure_fingerprint(publication)
            fingerprint = _restore_plan_fingerprint(publication)
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                "Fog-of-war restore plan is foreign or was mutated",
            ) from exc
        if (
            staged_state._structure_fingerprint != publication_structure_fingerprint
            or staged_state._fingerprint != fingerprint
        ):
            raise ValueError(
                "Fog-of-war restore plan is foreign or was mutated",
            )

        prepared_fusion = self._intel_fusion._prepare_commit_state(
            intel_fusion,
        )
        prepared_cadence = self._cadence._prepare_restore_commit(
            cadence_plan,
        )
        prepared_supports = self._prepare_observer_track_support_map(
            observer_track_supports,
        )
        self._validate_observer_track_support_map(
            observer_track_supports,
            prepared_supports,
        )

        # Every fallible validation, detachment, and container construction is
        # complete.  The shared RNG assignment is the final validated setter;
        # the remaining private commits publish by bounded swaps only.
        self._rng.bit_generator.state = rng_state
        self._detection._commit_prevalidated_scan_counts(
            scan_count_values,
        )
        self._intel_fusion._commit_prevalidated_fow_state(
            prepared_fusion,
        )
        self._cadence._commit_prevalidated_restore(
            prepared_cadence,
        )
        self._world_views = world_views
        with self._witness_lock:
            self._current_detection_witnesses = current_detection_witnesses
            self._observer_track_supports = prepared_supports

    def set_state(self, state: dict[str, Any]) -> None:
        """Validate and atomically restore standalone fog/fusion state."""
        if isinstance(state, dict) and set(state) == {
            "world_views",
            "rng_state",
        }:
            # Explicit versionless migration: historical fog state contained
            # no fusion payload.  A fresh legacy runtime therefore retains an
            # empty fusion topology while sharing the restored DETECTION RNG.
            legacy_fusion = self._intel_fusion.get_state()
            pristine_fusion_topology = {
                "tracks": {},
                "track_counter": 0,
                "fow_track_counters": {},
                "satellite_passes": {},
                "delivery_receipts": [],
                "imint_target_tracks": [],
            }
            if any(legacy_fusion[key] != expected for key, expected in pristine_fusion_topology.items()):
                raise ValueError(
                    "Historical two-key fog state requires a pristine target fusion topology",
                )
            legacy_fusion["rng_state"] = copy.deepcopy(state["rng_state"])
            state = {
                **state,
                "intel_fusion": legacy_fusion,
            }
        allow_legacy_state = isinstance(state, dict) and set(state) in (
            {"world_views", "rng_state", "intel_fusion"},
            {
                "world_views",
                "current_detection_witnesses",
                "rng_state",
                "intel_fusion",
            },
        )
        self.commit_state(
            self.stage_state(
                state,
                allow_legacy_state=allow_legacy_state,
            ),
        )
