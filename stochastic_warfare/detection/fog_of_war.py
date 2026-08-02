"""Fog of War — per-side world view management.

The public-facing API for the detection layer.  Each side maintains an
independent :class:`SideWorldView` containing only what its sensors and
intelligence have revealed.  Undetected enemies do not appear.
"""

from __future__ import annotations

import copy
import enum
import math
import threading
from dataclasses import dataclass, field
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
)
from stochastic_warfare.detection.identification import (
    ContactInfo,
    ContactLevel,
    IdentificationEngine,
)
from stochastic_warfare.detection.intel_fusion import IntelFusionEngine
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

    Witnesses are current-update integration evidence, not durable fog-of-war
    contacts.  They deliberately retain exact observer and attachment identity
    that the side-wide contact record cannot represent.
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
            "contacts": {
                cid: cr.get_state() for cid, cr in sorted(self.contacts.items())
            },
            "last_update_time": self.last_update_time,
        }


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
        self._world_views: dict[str, SideWorldView] = {}
        # 12a-7: COP sharing
        self._dl_config = data_link_config or DataLinkConfig()
        # network_name → list of unit_ids
        self._data_link_networks: dict[str, list[str]] = {}
        # unit_id → set of network names
        self._unit_networks: dict[str, set[str]] = {}
        # Successful checks from the most recent update for each side.  This
        # non-durable cache is protected because Phase 89 may update sides in
        # parallel.  Each published tuple is canonically ordered.
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
        These values are intentionally absent from :meth:`get_state`.
        """
        with self._witness_lock:
            if side is not None:
                return self._current_detection_witnesses.get(side, ())
            witnesses = [
                witness
                for side_witnesses in self._current_detection_witnesses.values()
                for witness in side_witnesses
            ]
        return tuple(sorted(witnesses, key=self._witness_sort_key))

    def clear_current_detection_witnesses(
        self,
        side: str | None = None,
    ) -> None:
        """Clear non-durable witness evidence for one side or all sides."""
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
            return tuple(
                _ObserverSensorScan(sensor=sensor)
                for sensor in own.get("sensors", ())
            )

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
            if (
                isinstance(source_index, bool)
                or not isinstance(source_index, int)
                or source_index < 0
            ):
                raise ValueError(
                    "sensor attachment source_equipment_index must be a "
                    "non-negative int",
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
                    "duplicate sensor attachment identity "
                    f"{identity!r} for one observer",
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
                    "own-unit sensors must be the exact sensor_attachments "
                    "projection",
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
            position, deception_type, effectiveness, signature,
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
                    all_targets.append({
                        "unit_id": decoy.decoy_id,
                        "position": decoy.position,
                        "signature": decoy.signature,
                        "unit": None,
                        "target_height": 0.0,
                        "concealment": 0.0,
                        "posture": 0,
                    })

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
            _target_points = [
                Point(t["position"].easting, t["position"].northing)
                for t in all_targets
            ]
            _target_tree = STRtree(_target_points)

        # For each own unit's sensors, scan each target
        for observer_index, own in enumerate(own_units):
            obs_pos = own["position"]
            sensor_scans = self._observer_sensor_scans(own)
            sensors = tuple(scan.sensor for scan in sensor_scans)
            obs_height = own.get("observer_height", 1.8)
            obs_heading_deg = own.get("observer_heading_deg", 0.0)
            observer_unit_id = own.get("unit_id")
            has_typed_attachments = any(
                scan.source_equipment_index is not None
                for scan in sensor_scans
            )
            if has_typed_attachments:
                _require_witness_id(
                    observer_unit_id,
                    "observer unit_id",
                )
            elif observer_unit_id is None:
                # Legacy sensor projections have no authored equipment
                # identity.  Their canonical input position is the only
                # available observer-local compatibility identity.
                observer_unit_id = (
                    f"__legacy_fow_observer_index__:{observer_index}"
                )
            else:
                _require_witness_id(observer_unit_id, "observer unit_id")

            # Phase 84a: determine targets in range via spatial index
            if _target_tree is not None:
                _op_sensors = [s for s in sensors if s.operational]
                _max_range = max(
                    (s.effective_range for s in _op_sensors), default=0.0,
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
                    (s.effective_range for s in _op_sensors), default=0.0,
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
                        scan.source_equipment_index
                        if scan.source_equipment_index is not None
                        else sensor_index
                    )
                    if not sensor.operational:
                        continue

                    # Phase 84b: scan scheduling — skip sensor on off-ticks
                    if scan_scheduling and sensor.definition.scan_interval_ticks > 1:
                        _interval = sensor.definition.scan_interval_ticks
                        _offset = (
                            sum(ord(c) for c in sensor.definition.sensor_id)
                            % _interval
                        )
                        if (current_tick + _offset) % _interval != 0:
                            continue

                    result = self._detection.check_detection(
                        obs_pos, tgt_pos, sensor, tgt_sig,
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
                                    source_equipment_index=(
                                        scan.source_equipment_index
                                    ),
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
                                result, tgt_unit,
                                threshold_db=sensor.definition.detection_threshold,
                                rng=rng,
                            )

                        # Feed to intel fusion.  The internal target-keyed
                        # contact retains an already issued side-local public
                        # track; new contacts receive the next opaque ordinal.
                        existing_track_id = (
                            wv.contacts[tgt_id].track.track_id
                            if tgt_id in wv.contacts
                            else None
                        )

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
                                    cr.contact_info = IdentificationEngine.update_contact(
                                        cr.contact_info, ci,
                                    ) if self._identification else ci
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

        published_witnesses = tuple(sorted(
            staged_witnesses,
            key=self._witness_sort_key,
        ))
        with self._witness_lock:
            self._current_detection_witnesses[side] = published_witnesses

        return wv

    # ------------------------------------------------------------------
    # 12a-7: COP sharing via data links
    # ------------------------------------------------------------------

    def set_data_link_networks(
        self, networks: dict[str, list[str]],
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

    def get_state(self) -> dict[str, Any]:
        return {
            "world_views": {
                side: wv.get_state() for side, wv in sorted(self._world_views.items())
            },
            "rng_state": copy.deepcopy(self._rng.bit_generator.state),
            "intel_fusion": self._intel_fusion.get_state(),
        }

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
        """Validate fog/fusion state without mutating the live manager."""
        if not isinstance(state, dict):
            raise ValueError("Fog-of-war state must be a mapping")
        expected_keys = {"world_views", "rng_state", "intel_fusion"}
        if set(state) != expected_keys:
            raise ValueError(
                "Fog-of-war state keys must be exactly "
                f"{sorted(expected_keys)!r}",
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
                    "Fog-of-war checkpoint time must be finite and "
                    "non-negative",
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
        if (
            authoritative_rng_state is not None
            and rng_state != authoritative_rng_state
        ):
            raise ValueError(
                "Fog-of-war RNG mirror disagrees with RNGManager DETECTION "
                "state",
            )

        raw_world_views = state["world_views"]
        if not isinstance(raw_world_views, dict):
            raise ValueError("Fog-of-war world_views must be a mapping")
        world_views: dict[str, dict[str, Any]] = {}
        view_keys = {"side", "contacts", "last_update_time"}
        for side, raw_view in raw_world_views.items():
            if (
                not isinstance(side, str)
                or not side
                or side != side.strip()
            ):
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
            last_update = raw_view["last_update_time"]
            if (
                isinstance(last_update, bool)
                or not isinstance(last_update, (int, float))
                or not math.isfinite(float(last_update))
                or float(last_update) < 0.0
            ):
                raise ValueError(
                    "Fog-of-war last_update_time must be finite and "
                    "non-negative",
                )
            normalized_time = float(last_update)
            if elapsed is not None and normalized_time > elapsed:
                raise ValueError(
                    "Fog-of-war update time is after checkpoint time",
                )
            world_views[side] = {
                "side": side,
                "contacts": copy.deepcopy(raw_view["contacts"]),
                "last_update_time": normalized_time,
            }

        fusion_plan = self._intel_fusion.stage_state(
            state["intel_fusion"],
            expected_sides=expected_sides,
            expected_target_sides=expected_target_sides,
            satellite_topology=satellite_topology,
            checkpoint_elapsed_s=elapsed,
            authoritative_rng_state=authoritative_rng_state,
        )
        if (
            authoritative_rng_state is not None
            and fusion_plan["rng_state"] != rng_state
        ):
            raise ValueError(
                "Fog-of-war and IntelFusion RNG mirrors disagree",
            )
        return {
            "world_views": world_views,
            "rng_state": rng_state,
            "intel_fusion": fusion_plan,
        }

    def commit_state(self, staged_state: dict[str, Any]) -> None:
        """Commit a non-throwing fog/fusion restore plan."""
        self._rng.bit_generator.state = staged_state["rng_state"]
        self._intel_fusion.commit_state(staged_state["intel_fusion"])
        # REM-029 owns non-empty ordinary contact restoration.  Preserve the
        # established boundary while restoring exact logical update times.
        for side, world_view_state in staged_state["world_views"].items():
            world_view = self.get_world_view(side)
            world_view.last_update_time = world_view_state["last_update_time"]
        # Witnesses are same-update evidence, never restored contact state.
        self.clear_current_detection_witnesses()

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
            legacy_fusion["rng_state"] = copy.deepcopy(state["rng_state"])
            state = {
                **state,
                "intel_fusion": legacy_fusion,
            }
        self.commit_state(self.stage_state(state))
