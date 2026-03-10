"""Multi-source intelligence fusion.

Combines sensor detections, SIGINT, HUMINT, IMINT, and COMINT into a unified
track picture.  Each intel report is converted to a Kalman measurement and
fused via the :class:`StateEstimator`.  Source reliability scales measurement
noise (low reliability = high noise).
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import Position
from stochastic_warfare.detection.detection import DetectionResult
from stochastic_warfare.detection.estimation import (
    StateEstimator,
    Track,
    TrackStatus,
)
from stochastic_warfare.detection.identification import ContactInfo, ContactLevel

logger = get_logger(__name__)

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

    start_time: float
    end_time: float
    coverage_center_x: float
    coverage_center_y: float
    coverage_radius_m: float
    resolution_m: float
    revisit_interval_s: float
    source_type: int = 3  # IMINT


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
    ua = max(a.position_uncertainty_m, 1.0)
    ub = max(b.position_uncertainty_m, 1.0)
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

    # ------------------------------------------------------------------
    # Intel report submission
    # ------------------------------------------------------------------

    def submit_report(
        self,
        side: str,
        report: IntelReport,
        contact_id: str | None = None,
    ) -> str | None:
        """Convert an intel report to a Kalman measurement and update/create track.

        Returns the track ID of the updated or created track, or None if
        the report has no position information.
        """
        if report.target_position is None:
            return None

        tracks = self._get_side_tracks(side)

        # Scale noise by reliability: low reliability = high noise
        reliability = max(report.reliability, 0.01)
        noise_scale = 1.0 / reliability
        unc = report.position_uncertainty_m * noise_scale
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

        # Try to associate with existing track
        if contact_id and contact_id in tracks:
            track = tracks[contact_id]
            self._estimator.update(track, meas, R, report.timestamp)
            return contact_id

        # Create new track
        self._track_counter += 1
        tid = f"track-{self._track_counter:04d}"
        track = self._estimator.create_track(
            tid, side, meas, R, ci, report.timestamp,
        )
        tracks[tid] = track
        return tid

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
            timestamp=0.0,
            reliability=min(1.0, detection.probability),
            target_position=Position(tgt_e, tgt_n, 0.0),
            position_uncertainty_m=detection.range_m * 0.05,  # 5% of range
            target_type=None,
            classification_confidence=contact_info.confidence,
            source_unit_id=None,
        )
        return self.submit_report(side, report, contact_id)

    # ------------------------------------------------------------------
    # Satellite coverage
    # ------------------------------------------------------------------

    def add_satellite_pass(self, side: str, sat_pass: SatellitePass) -> None:
        """Register a satellite pass for a side."""
        if side not in self._satellite_passes:
            self._satellite_passes[side] = []
        self._satellite_passes[side].append(sat_pass)

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
            "rng_state": self._rng.bit_generator.state,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._track_counter = state["track_counter"]
        self._rng.bit_generator.state = state["rng_state"]
        self._tracks = {}
        for side, side_tracks in state["tracks"].items():
            self._tracks[side] = {}
            for tid, ts in side_tracks.items():
                track = Track.__new__(Track)
                track.set_state(ts)
                self._tracks[side][tid] = track
