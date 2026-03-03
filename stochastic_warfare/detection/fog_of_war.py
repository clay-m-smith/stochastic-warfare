"""Fog of War — per-side world view management.

The public-facing API for the detection layer.  Each side maintains an
independent :class:`SideWorldView` containing only what its sensors and
intelligence have revealed.  Undetected enemies do not appear.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import Position
from stochastic_warfare.detection.deception import Decoy, DeceptionEngine
from stochastic_warfare.detection.detection import DetectionEngine, DetectionResult
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
from stochastic_warfare.detection.intel_fusion import IntelFusionEngine
from stochastic_warfare.detection.sensors import SensorInstance, SensorSuite
from stochastic_warfare.detection.signatures import SignatureProfile

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


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
        rng: np.random.Generator | None = None,
    ) -> None:
        self._detection = detection_engine or DetectionEngine()
        self._identification = identification_engine
        self._estimator = state_estimator or StateEstimator()
        self._intel_fusion = intel_fusion or IntelFusionEngine(self._estimator)
        self._deception = deception_engine or DeceptionEngine()
        self._rng = rng or np.random.default_rng(0)
        self._world_views: dict[str, SideWorldView] = {}

    # ------------------------------------------------------------------
    # World view access
    # ------------------------------------------------------------------

    def get_world_view(self, side: str) -> SideWorldView:
        """Return the world view for *side*, creating if needed."""
        if side not in self._world_views:
            self._world_views[side] = SideWorldView(side=side)
        return self._world_views[side]

    def get_contact(self, side: str, contact_id: str) -> ContactRecord | None:
        """Return a specific contact record, or None."""
        wv = self._world_views.get(side)
        if wv is None:
            return None
        return wv.contacts.get(contact_id)

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
    ) -> SideWorldView:
        """Run one detection cycle for *side*.

        Parameters
        ----------
        own_units:
            List of dicts with keys: position, sensors, observer_height.
        enemy_units:
            List of dicts with keys: unit_id, position, signature, unit,
            target_height, concealment, posture.
        dt:
            Time step in seconds.
        current_time:
            Current simulation time.
        decoys:
            Active enemy decoys.

        Returns the updated :class:`SideWorldView`.
        """
        wv = self.get_world_view(side)
        wv.last_update_time = current_time

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

        # For each own unit's sensors, scan each target
        for own in own_units:
            obs_pos = own["position"]
            sensors = own.get("sensors", [])
            obs_height = own.get("observer_height", 1.8)

            for target in all_targets:
                tgt_id = target["unit_id"]
                tgt_pos = target["position"]
                tgt_sig = target["signature"]
                tgt_unit = target.get("unit")
                tgt_height = target.get("target_height", 0.0)
                concealment = target.get("concealment", 0.0)
                posture = target.get("posture", 0)

                for sensor in sensors:
                    if not sensor.operational:
                        continue

                    result = self._detection.check_detection(
                        obs_pos, tgt_pos, sensor, tgt_sig,
                        target_unit=tgt_unit,
                        observer_height=obs_height,
                        target_height=tgt_height,
                        concealment=concealment,
                        posture=posture,
                    )

                    if result.detected:
                        # Classify
                        ci = ContactInfo(ContactLevel.DETECTED, None, None, None, 0.3)
                        if self._identification is not None:
                            ci = self._identification.classify_from_detection(
                                result, tgt_unit,
                                threshold_db=sensor.definition.detection_threshold,
                            )

                        # Feed to intel fusion
                        existing_tid = tgt_id if tgt_id in wv.contacts else None

                        tid = self._intel_fusion.submit_sensor_detection(
                            side, result, ci, obs_pos, contact_id=existing_tid,
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
                                    cr.last_sensor_contact_time = current_time
                                    if sensor.sensor_id not in cr.reporting_sensors:
                                        cr.reporting_sensors.append(sensor.sensor_id)
                                else:
                                    wv.contacts[tgt_id] = ContactRecord(
                                        contact_id=tgt_id,
                                        track=track,
                                        contact_info=ci,
                                        first_detected_time=current_time,
                                        last_sensor_contact_time=current_time,
                                        reporting_sensors=[sensor.sensor_id],
                                    )

        # Manage track lifecycle
        tracks = self._intel_fusion.get_tracks(side)
        to_delete = self._estimator.manage_tracks(tracks, current_time)
        for tid in to_delete:
            # Find and remove associated contact
            for cid in list(wv.contacts.keys()):
                if wv.contacts[cid].track.track_id == tid:
                    del wv.contacts[cid]
                    break

        return wv

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
            "rng_state": self._rng.bit_generator.state,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]
        # World views are reconstructed via update cycles; just store time
        for side, wv_state in state["world_views"].items():
            wv = self.get_world_view(side)
            wv.last_update_time = wv_state["last_update_time"]
