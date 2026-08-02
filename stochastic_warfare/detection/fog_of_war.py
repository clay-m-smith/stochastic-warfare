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
from dataclasses import dataclass, field, fields, is_dataclass, replace
from typing import Any

import numpy as np
from shapely import STRtree
from shapely.geometry import Point

from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import Position
from stochastic_warfare.detection.deception import Decoy, DeceptionEngine
from stochastic_warfare.detection.detection import (
    DetectionEngine,
    DetectionScanIdentity,
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
    validate_fow_track_id,
)
from stochastic_warfare.detection.sensors import SensorInstance
from stochastic_warfare.detection.signatures import SignatureProfile

logger = get_logger(__name__)

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


@dataclass(frozen=True, slots=True)
class FogOfWarRestorePlan:
    """Owner-bound, fully validated fog/fusion publication plan."""

    _world_views: dict[str, SideWorldView] = field(repr=False)
    _current_detection_witnesses: dict[
        str,
        tuple[ObserverDetectionWitness, ...],
    ] = field(repr=False)
    _rng_state: dict[str, Any] = field(repr=False)
    _intel_fusion: dict[str, Any] = field(repr=False)
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
    def rng_state(self) -> dict[str, Any]:
        """Return a defensive copy of the staged DETECTION RNG mirror."""
        return copy.deepcopy(self._rng_state)

    @property
    def intel_fusion(self) -> dict[str, Any]:
        """Return a defensive copy of the staged fusion publication."""
        return copy.deepcopy(self._intel_fusion)


@dataclass(frozen=True, slots=True)
class _ObserverSensorScan:
    sensor: SensorInstance
    source_equipment_index: int | None = None
    modeled_role: str | None = None


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


def _restore_plan_payload(plan: FogOfWarRestorePlan) -> dict[str, Any]:
    fusion = plan._intel_fusion
    ledger = fusion["delivery_receipt_ledger"]
    fusion_tracks = fusion["tracks"]
    return {
        "world_views": {
            side: world_view.get_state()
            for side, world_view in sorted(plan._world_views.items())
        },
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
        "rng_state": plan._rng_state,
        "intel_fusion": {
            "tracks": {
                side: {
                    track_id: track.get_state()
                    for track_id, track in sorted(side_tracks.items())
                }
                for side, side_tracks in sorted(fusion_tracks.items())
            },
            "track_counter": fusion["track_counter"],
            "fow_track_counters": fusion["fow_track_counters"],
            "rng_state": fusion["rng_state"],
            "satellite_passes": {
                side: [
                    satellite_pass.model_dump(mode="json")
                    for satellite_pass in passes
                ]
                for side, passes in sorted(
                    fusion["satellite_passes"].items(),
                )
            },
            "delivery_receipts": [
                receipt.to_state()
                for receipt in fusion["delivery_receipts"]
            ],
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
        },
    }


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
        slot_names.extend(
            name
            for name in declared_slots
            if name not in {"__dict__", "__weakref__"}
        )
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
        "Unsupported fog-of-war restore-plan structure "
        f"{type_name}",
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
            plan._rng_state,
            plan._intel_fusion,
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
    ) -> None:
        self._detection = detection_engine or DetectionEngine(rng=rng)
        self._identification = identification_engine
        self._estimator = state_estimator or StateEstimator(rng=rng)
        self._intel_fusion = intel_fusion or IntelFusionEngine(rng=rng)
        self._deception = deception_engine or DeceptionEngine(rng=rng)
        self._rng = rng
        self._plan_owner_token = object()
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
        self._witness_lock = threading.Lock()

    @property
    def intel_fusion(self) -> IntelFusionEngine:
        """Expose intel fusion engine for SIGINT/ISR track injection."""
        return self._intel_fusion

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
        with self._witness_lock:
            if side is not None:
                return self._current_detection_witnesses.get(side, ())
            witnesses = [
                witness for side_witnesses in self._current_detection_witnesses.values() for witness in side_witnesses
            ]
        return tuple(sorted(witnesses, key=self._witness_sort_key))

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

    # ------------------------------------------------------------------
    # Phase 69c: Deception passthrough API
    # ------------------------------------------------------------------

    def deploy_decoy(
        self,
        position: Position,
        deception_type: "DeceptionType | int" = 4,
        effectiveness: float = 1.0,
        signature: "SignatureProfile | None" = None,
    ) -> Decoy:
        """Deploy a decoy via the internal deception engine."""
        from stochastic_warfare.detection.deception import DeceptionType

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
    # Update cycle
    # ------------------------------------------------------------------

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
        """Run one detection cycle for *side*.

        Parameters
        ----------
        own_units:
            List of dicts with keys: position, sensors, observer_height, and
            observer_heading_deg.
        enemy_units:
            List of dicts with keys: unit_id, position, signature, unit,
            target_height, concealment, posture.
        dt:
            Time step in seconds.
        current_time:
            Current simulation time.
        decoys:
            Active enemy decoys.
        detection_culling:
            Use STRtree spatial index to skip out-of-range targets.
        scan_scheduling:
            Respect per-sensor ``scan_interval_ticks`` scheduling.
        current_tick:
            Current simulation tick (for scan scheduling).
        visibility_m, illumination_lux, thermal_contrast, ambient_noise_db,
        atmospheric_atten_db_per_km, transmission_loss,
        jam_snr_penalty_db:
            Current detection-environment inputs forwarded to the canonical
            :class:`DetectionEngine` check.  A target mapping may override an
            input when propagation or concealment is target-specific.

        Returns the updated :class:`SideWorldView`.
        """
        _require_witness_id(side, "fog-of-war side")
        # Never allow a prior update's success to survive a failed or empty
        # current update.  New witnesses publish only after the full scan and
        # track-lifecycle work succeeds.
        self.clear_current_detection_witnesses(side)
        _require_finite_witness_scalar(
            current_time,
            "fog-of-war logical time",
            non_negative=True,
        )
        logical_time_s = float(current_time)
        staged_witnesses: list[ObserverDetectionWitness] = []
        wv = self.get_world_view(side)
        wv.last_update_time = logical_time_s

        # Build list of scannable targets (enemy units + decoys)
        all_targets = list(enemy_units)
        if decoys:
            for decoy in decoys:
                if decoy.active:
                    all_targets.append(
                        {
                            "unit_id": decoy.decoy_id,
                            "position": decoy.position,
                            "signature": decoy.signature,
                            "unit": None,
                            "target_height": 0.0,
                            "concealment": 0.0,
                            "posture": 0,
                        }
                    )

        # Phase 88: Pre-build target position array for vectorized ops
        _target_pos_arr: np.ndarray | None = None
        if unit_arrays is not None and len(all_targets) > 0:
            _target_pos_arr = np.array(
                [(t["position"].easting, t["position"].northing) for t in all_targets],
                dtype=np.float64,
            )

        # Phase 84a: Build spatial index for range-limited detection
        _target_tree = None
        _target_points = None
        if detection_culling and len(all_targets) > 1:
            _target_points = [Point(t["position"].easting, t["position"].northing) for t in all_targets]
            _target_tree = STRtree(_target_points)

        # For each own unit's sensors, scan each target
        for observer_index, own in enumerate(own_units):
            obs_pos = own["position"]
            sensor_scans = self._observer_sensor_scans(own)
            sensors = tuple(scan.sensor for scan in sensor_scans)
            obs_height = own.get("observer_height", 1.8)
            obs_heading_deg = own.get("observer_heading_deg", 0.0)
            observer_unit_id = own.get("unit_id")
            has_typed_attachments = any(scan.source_equipment_index is not None for scan in sensor_scans)
            if has_typed_attachments:
                _require_witness_id(
                    observer_unit_id,
                    "observer unit_id",
                )
            elif observer_unit_id is None:
                # Legacy sensor projections have no authored equipment
                # identity.  Their canonical input position is the only
                # available observer-local compatibility identity.
                observer_unit_id = f"__legacy_fow_observer_index__:{observer_index}"
            else:
                _require_witness_id(observer_unit_id, "observer unit_id")

            # Phase 84a: determine targets in range via spatial index
            if _target_tree is not None:
                _op_sensors = [s for s in sensors if s.operational]
                _max_range = max(
                    (s.effective_range for s in _op_sensors),
                    default=0.0,
                )
                if _max_range > 0:
                    _obs_pt = Point(obs_pos.easting, obs_pos.northing)
                    _cand_idxs = sorted(
                        _target_tree.query(_obs_pt.buffer(_max_range)),
                    )
                    _scan_targets = [all_targets[i] for i in _cand_idxs]
                else:
                    _scan_targets = []
            elif _target_pos_arr is not None and _target_pos_arr.shape[0] > 0:
                # Phase 88b: vectorized range check via numpy
                _op_sensors = [s for s in sensors if s.operational]
                _max_range = max(
                    (s.effective_range for s in _op_sensors),
                    default=0.0,
                )
                if _max_range > 0:
                    _obs_arr = np.array([obs_pos.easting, obs_pos.northing])
                    _diffs = _target_pos_arr - _obs_arr
                    _dists = np.sqrt(np.sum(_diffs * _diffs, axis=1))
                    _in_range = np.where(_dists <= _max_range)[0]
                    _scan_targets = [all_targets[i] for i in _in_range]
                else:
                    _scan_targets = []
            else:
                _scan_targets = all_targets

            for target in _scan_targets:
                tgt_id = target["unit_id"]
                tgt_pos = target["position"]
                tgt_sig = target["signature"]
                tgt_unit = target.get("unit")
                tgt_height = target.get("target_height", 0.0)
                concealment = target.get("concealment", 0.0)
                posture = target.get("posture", 0)

                for sensor_index, scan in enumerate(sensor_scans):
                    sensor = scan.sensor
                    scan_source_index = (
                        scan.source_equipment_index if scan.source_equipment_index is not None else sensor_index
                    )
                    if not sensor.operational:
                        continue

                    # Phase 84b: scan scheduling — skip sensor on off-ticks
                    if scan_scheduling and sensor.definition.scan_interval_ticks > 1:
                        _interval = sensor.definition.scan_interval_ticks
                        _offset = sum(ord(c) for c in sensor.definition.sensor_id) % _interval
                        if (current_tick + _offset) % _interval != 0:
                            continue

                    result = self._detection.check_detection(
                        obs_pos,
                        tgt_pos,
                        sensor,
                        tgt_sig,
                        target_unit=tgt_unit,
                        observer_height=obs_height,
                        target_height=tgt_height,
                        concealment=concealment,
                        posture=posture,
                        illumination_lux=target.get(
                            "illumination_lux",
                            illumination_lux,
                        ),
                        visibility_m=target.get("visibility_m", visibility_m),
                        thermal_contrast=target.get(
                            "thermal_contrast",
                            thermal_contrast,
                        ),
                        ambient_noise_db=target.get(
                            "ambient_noise_db",
                            ambient_noise_db,
                        ),
                        atmospheric_atten_db_per_km=target.get(
                            "atmospheric_atten_db_per_km",
                            atmospheric_atten_db_per_km,
                        ),
                        transmission_loss=target.get(
                            "transmission_loss",
                            transmission_loss,
                        ),
                        observer_heading_deg=obs_heading_deg,
                        target_id=tgt_id,
                        scan_identity=DetectionScanIdentity(
                            side=side,
                            observer_unit_id=observer_unit_id,
                            source_equipment_index=scan_source_index,
                        ),
                        jam_snr_penalty_db=target.get(
                            "jam_snr_penalty_db",
                            jam_snr_penalty_db,
                        ),
                        rng=rng,
                    )

                    if result.detected:
                        if scan.source_equipment_index is not None:
                            staged_witnesses.append(
                                ObserverDetectionWitness(
                                    side=side,
                                    observer_unit_id=observer_unit_id,
                                    target_id=tgt_id,
                                    source_equipment_index=(scan.source_equipment_index),
                                    sensor_id=sensor.sensor_id,
                                    modeled_role=scan.modeled_role,
                                    logical_time_s=logical_time_s,
                                    detected=result.detected,
                                    probability=float(result.probability),
                                    snr_db=float(result.snr_db),
                                    range_m=float(result.range_m),
                                    sensor_type=result.sensor_type.name,
                                    bearing_deg=float(result.bearing_deg),
                                ),
                            )
                        # Classify
                        ci = ContactInfo(ContactLevel.DETECTED, None, None, None, 0.3)
                        if self._identification is not None:
                            ci = self._identification.classify_from_detection(
                                result,
                                tgt_unit,
                                threshold_db=sensor.definition.detection_threshold,
                                rng=rng,
                            )

                        # Feed to intel fusion.  The internal target-keyed
                        # contact retains an already issued side-local public
                        # track; new contacts receive the next opaque ordinal.
                        existing_track_id = wv.contacts[tgt_id].track.track_id if tgt_id in wv.contacts else None

                        tid = self._intel_fusion.submit_sensor_detection(
                            side,
                            result,
                            ci,
                            obs_pos,
                            contact_id=existing_track_id,
                            allocate_fow_track=True,
                            observation_time_s=logical_time_s,
                        )

                        if tid is not None:
                            # Update or create contact record
                            tracks = self._intel_fusion.get_tracks(side)
                            if tid in tracks:
                                track = tracks[tid]
                                if tgt_id in wv.contacts:
                                    cr = wv.contacts[tgt_id]
                                    cr.track = track
                                    cr.contact_info = (
                                        IdentificationEngine.update_contact(
                                            cr.contact_info,
                                            ci,
                                        )
                                        if self._identification
                                        else ci
                                    )
                                    cr.last_sensor_contact_time = logical_time_s
                                    if sensor.sensor_id not in cr.reporting_sensors:
                                        cr.reporting_sensors.append(sensor.sensor_id)
                                else:
                                    wv.contacts[tgt_id] = ContactRecord(
                                        contact_id=tgt_id,
                                        track=track,
                                        contact_info=ci,
                                        first_detected_time=logical_time_s,
                                        last_sensor_contact_time=logical_time_s,
                                        reporting_sensors=[sensor.sensor_id],
                                    )

        # Manage track lifecycle
        tracks = self._intel_fusion.get_tracks(side)
        to_delete = self._estimator.manage_tracks(tracks, logical_time_s)
        for tid in to_delete:
            # Find and remove associated contact
            for cid in list(wv.contacts.keys()):
                if wv.contacts[cid].track.track_id == tid:
                    del wv.contacts[cid]
                    break

        published_witnesses = tuple(
            sorted(
                staged_witnesses,
                key=self._witness_sort_key,
            )
        )
        with self._witness_lock:
            self._current_detection_witnesses[side] = published_witnesses

        return wv

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

    def get_state(self) -> dict[str, Any]:
        self.validate_checkpoint_boundary()
        self.validate_live_contact_bindings()
        with self._witness_lock:
            witnesses = {
                side: [witness.get_state() for witness in side_witnesses]
                for side, side_witnesses in sorted(
                    self._current_detection_witnesses.items(),
                )
            }
        state = {
            "world_views": {side: wv.get_state() for side, wv in sorted(self._world_views.items())},
            "current_detection_witnesses": witnesses,
            "rng_state": copy.deepcopy(self._rng.bit_generator.state),
            "intel_fusion": self._intel_fusion.get_state(),
        }
        # Capture must fail closed on malformed live topology too.  Production
        # context capture follows with the stronger roster/loadout preflight.
        self.stage_state(state)
        return state

    def stage_state(
        self,
        state: dict[str, Any],
        *,
        expected_sides: set[str] | None = None,
        expected_target_sides: dict[str, str] | None = None,
        satellite_topology: dict[str, tuple[str, str]] | None = None,
        checkpoint_elapsed_s: float | None = None,
        authoritative_rng_state: dict[str, Any] | None = None,
        expected_sensor_bindings: (tuple[FogOfWarSensorBinding, ...] | None) = None,
        allow_legacy_state: bool = False,
    ) -> FogOfWarRestorePlan:
        """Validate fog/fusion state without mutating the live manager."""
        self.validate_checkpoint_boundary()
        self.validate_internal_bindings()
        if type(allow_legacy_state) is not bool:
            raise ValueError("allow_legacy_state must be a boolean")
        if not isinstance(state, dict):
            raise ValueError("Fog-of-war state must be a mapping")
        expected_keys = (
            {"world_views", "rng_state", "intel_fusion"}
            if allow_legacy_state
            else {
                "world_views",
                "current_detection_witnesses",
                "rng_state",
                "intel_fusion",
            }
        )
        if set(state) != expected_keys:
            raise ValueError(
                f"Fog-of-war state keys must be exactly {sorted(expected_keys)!r}",
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
            if allow_legacy_state and raw_contacts:
                raise ValueError(
                    "Versionless fog-of-war state cannot restore nonempty ordinary contacts",
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

        if allow_legacy_state and (
            fusion_plan["fow_track_counters"]
            or any(
                track_id.startswith("fow-track-")
                for side_tracks in fusion_plan["tracks"].values()
                for track_id in side_tracks
            )
        ):
            raise ValueError(
                "Versionless fog-of-war state cannot restore FOW track history",
            )

        raw_witness_map = state.get("current_detection_witnesses", {})
        if not isinstance(raw_witness_map, dict):
            raise ValueError(
                "Fog-of-war current_detection_witnesses must be a mapping",
            )
        if allow_legacy_state and raw_witness_map:
            raise ValueError(
                "Versionless fog-of-war state cannot restore detection witnesses",
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

        plan = FogOfWarRestorePlan(
            _world_views=world_views,
            _current_detection_witnesses=witnesses,
            _rng_state=rng_state,
            _intel_fusion=fusion_plan,
            _owner_token=self._plan_owner_token,
            _structure_fingerprint="",
            _fingerprint="",
        )
        plan = replace(
            plan,
            _structure_fingerprint=(
                _restore_plan_structure_fingerprint(plan)
            ),
        )
        return replace(
            plan,
            _fingerprint=_restore_plan_fingerprint(plan),
        )

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
            structure_fingerprint = (
                _restore_plan_structure_fingerprint(staged_state)
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                "Fog-of-war restore plan is foreign or was mutated",
            ) from exc
        if staged_state._structure_fingerprint != structure_fingerprint:
            raise ValueError(
                "Fog-of-war restore plan is foreign or was mutated",
            )
        try:
            (
                world_views,
                current_detection_witnesses,
                rng_state,
                intel_fusion,
            ) = copy.deepcopy(
                (
                    staged_state._world_views,
                    staged_state._current_detection_witnesses,
                    staged_state._rng_state,
                    staged_state._intel_fusion,
                ),
            )
            publication = replace(
                staged_state,
                _world_views=world_views,
                _current_detection_witnesses=(
                    current_detection_witnesses
                ),
                _rng_state=rng_state,
                _intel_fusion=intel_fusion,
            )
            publication_structure_fingerprint = (
                _restore_plan_structure_fingerprint(publication)
            )
            fingerprint = _restore_plan_fingerprint(publication)
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                "Fog-of-war restore plan is foreign or was mutated",
            ) from exc
        if (
            staged_state._structure_fingerprint
            != publication_structure_fingerprint
            or staged_state._fingerprint != fingerprint
        ):
            raise ValueError(
                "Fog-of-war restore plan is foreign or was mutated",
            )
        self._intel_fusion.commit_state(intel_fusion)
        self._world_views = dict(world_views)
        self._rng.bit_generator.state = rng_state
        with self._witness_lock:
            self._current_detection_witnesses = {
                side: side_witnesses
                for side, side_witnesses in (
                    current_detection_witnesses.items()
                )
            }

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
            if any(
                legacy_fusion[key] != expected
                for key, expected in pristine_fusion_topology.items()
            ):
                raise ValueError(
                    "Historical two-key fog state requires a pristine target "
                    "fusion topology",
                )
            legacy_fusion["rng_state"] = copy.deepcopy(state["rng_state"])
            state = {
                **state,
                "intel_fusion": legacy_fusion,
            }
        allow_legacy_state = isinstance(state, dict) and set(state) == {
            "world_views",
            "rng_state",
            "intel_fusion",
        }
        self.commit_state(
            self.stage_state(
                state,
                allow_legacy_state=allow_legacy_state,
            ),
        )
