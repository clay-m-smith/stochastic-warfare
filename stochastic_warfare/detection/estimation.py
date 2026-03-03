"""Kalman-filter state estimation for tracked contacts.

Each side maintains a :class:`Track` per observed contact with a 4-state
(x, y, vx, vy) Kalman filter.  The prediction step grows uncertainty;
the update step fuses measurements.  Tracks transition through
TENTATIVE → CONFIRMED → COASTING → LOST based on hit/miss counts and
time since last update.
"""

from __future__ import annotations

import enum
from typing import Any, NamedTuple

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.detection.identification import ContactInfo, ContactLevel

logger = get_logger(__name__)

# Pre-allocated constant matrices for Kalman filter
_H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=np.float64)
_EYE4 = np.eye(4, dtype=np.float64)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class TrackState(NamedTuple):
    """Kalman filter state for a tracked contact."""

    position: np.ndarray  # [x, y]
    velocity: np.ndarray  # [vx, vy]
    covariance: np.ndarray  # 4×4
    last_update_time: float


class TrackStatus(enum.IntEnum):
    TENTATIVE = 0
    CONFIRMED = 1
    COASTING = 2
    LOST = 3


# ---------------------------------------------------------------------------
# Track
# ---------------------------------------------------------------------------


class Track:
    """Single tracked contact with Kalman filter state."""

    def __init__(
        self,
        track_id: str,
        side: str,
        contact_info: ContactInfo,
        state: TrackState,
        status: TrackStatus = TrackStatus.TENTATIVE,
    ) -> None:
        self.track_id = track_id
        self.side = side
        self.contact_info = contact_info
        self.state = state
        self.status = status
        self.hits: int = 1
        self.misses: int = 0

    @property
    def position_uncertainty(self) -> float:
        """RMS position uncertainty from covariance diagonal."""
        px = self.state.covariance[0, 0]
        py = self.state.covariance[1, 1]
        return float(np.sqrt(px + py))

    def get_state(self) -> dict[str, Any]:
        return {
            "track_id": self.track_id,
            "side": self.side,
            "contact_info": {
                "level": int(self.contact_info.level),
                "domain_estimate": self.contact_info.domain_estimate,
                "type_estimate": self.contact_info.type_estimate,
                "specific_estimate": self.contact_info.specific_estimate,
                "confidence": self.contact_info.confidence,
            },
            "state": {
                "position": self.state.position.tolist(),
                "velocity": self.state.velocity.tolist(),
                "covariance": self.state.covariance.tolist(),
                "last_update_time": self.state.last_update_time,
            },
            "status": int(self.status),
            "hits": self.hits,
            "misses": self.misses,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self.track_id = state["track_id"]
        self.side = state["side"]
        ci = state["contact_info"]
        self.contact_info = ContactInfo(
            level=ContactLevel(ci["level"]),
            domain_estimate=ci["domain_estimate"],
            type_estimate=ci["type_estimate"],
            specific_estimate=ci["specific_estimate"],
            confidence=ci["confidence"],
        )
        ts = state["state"]
        self.state = TrackState(
            position=np.array(ts["position"]),
            velocity=np.array(ts["velocity"]),
            covariance=np.array(ts["covariance"]),
            last_update_time=ts["last_update_time"],
        )
        self.status = TrackStatus(state["status"])
        self.hits = state["hits"]
        self.misses = state["misses"]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class EstimationConfig(BaseModel):
    """Tunable parameters for the state estimator."""

    process_noise_std: float = 5.0  # m/s² acceleration noise
    confirmation_threshold: int = 3  # hits before CONFIRMED
    coast_timeout_s: float = 300.0  # seconds before COASTING → LOST
    lost_timeout_s: float = 600.0  # seconds before track deleted
    max_covariance_m: float = 10000.0  # max position uncertainty before LOST


# ---------------------------------------------------------------------------
# State estimator
# ---------------------------------------------------------------------------


class StateEstimator:
    """Kalman-filter state estimator for tracked contacts.

    Parameters
    ----------
    rng:
        A ``numpy.random.Generator`` for process noise.
    config:
        Optional :class:`EstimationConfig`.
    """

    def __init__(
        self,
        rng: np.random.Generator | None = None,
        config: EstimationConfig | None = None,
    ) -> None:
        self._rng = rng or np.random.default_rng(0)
        self._config = config or EstimationConfig()

    # ------------------------------------------------------------------
    # Kalman predict
    # ------------------------------------------------------------------

    def predict(self, track: Track, dt: float) -> None:
        """Kalman prediction step — project state forward by *dt* seconds.

        State transition: x_pred = F @ x
        Covariance:       P_pred = F @ P @ F^T + Q
        """
        q = self._config.process_noise_std

        # State vector [x, y, vx, vy]
        x = np.concatenate([track.state.position, track.state.velocity])
        P = track.state.covariance.copy()

        # Transition matrix
        F = np.array([
            [1, 0, dt, 0],
            [0, 1, 0, dt],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ])

        # Process noise (acceleration noise)
        dt2 = dt * dt
        dt3 = dt2 * dt / 2.0
        dt4 = dt2 * dt2 / 4.0
        Q = q * q * np.array([
            [dt4, 0, dt3, 0],
            [0, dt4, 0, dt3],
            [dt3, 0, dt2, 0],
            [0, dt3, 0, dt2],
        ])

        x_pred = F @ x
        P_pred = F @ P @ F.T + Q

        track.state = TrackState(
            position=x_pred[:2],
            velocity=x_pred[2:],
            covariance=P_pred,
            last_update_time=track.state.last_update_time,
        )

    # ------------------------------------------------------------------
    # Kalman update
    # ------------------------------------------------------------------

    def update(
        self,
        track: Track,
        measurement: np.ndarray,
        measurement_noise: np.ndarray,
        time: float,
    ) -> None:
        """Kalman update step — fuse a position measurement.

        measurement: [x, y] observed position
        measurement_noise: 2×2 noise covariance (R)
        """
        x = np.concatenate([track.state.position, track.state.velocity])
        P = track.state.covariance
        R = measurement_noise

        # Innovation
        y = measurement - _H @ x

        # Innovation covariance
        S = _H @ P @ _H.T + R

        # Kalman gain
        K = P @ _H.T @ np.linalg.inv(S)

        # Updated state
        x_new = x + K @ y
        P_new = (_EYE4 - K @ _H) @ P

        track.state = TrackState(
            position=x_new[:2],
            velocity=x_new[2:],
            covariance=P_new,
            last_update_time=time,
        )
        track.hits += 1

    # ------------------------------------------------------------------
    # Track creation
    # ------------------------------------------------------------------

    def create_track(
        self,
        track_id: str,
        side: str,
        measurement: np.ndarray,
        measurement_noise: np.ndarray,
        contact_info: ContactInfo,
        time: float,
    ) -> Track:
        """Create a new tentative track from a first measurement."""
        position = measurement.copy()
        velocity = np.zeros(2)
        covariance = np.zeros((4, 4))
        covariance[:2, :2] = measurement_noise
        covariance[2, 2] = 100.0  # initial velocity uncertainty (m/s)²
        covariance[3, 3] = 100.0

        state = TrackState(
            position=position,
            velocity=velocity,
            covariance=covariance,
            last_update_time=time,
        )

        return Track(
            track_id=track_id,
            side=side,
            contact_info=contact_info,
            state=state,
            status=TrackStatus.TENTATIVE,
        )

    # ------------------------------------------------------------------
    # Track lifecycle management
    # ------------------------------------------------------------------

    def manage_tracks(
        self,
        tracks: dict[str, Track],
        current_time: float,
    ) -> list[str]:
        """Update track statuses and return IDs of tracks to delete.

        - TENTATIVE → CONFIRMED if hits >= threshold
        - CONFIRMED → COASTING if time since update > coast_timeout
        - COASTING → LOST if time > lost_timeout or covariance too large
        """
        to_delete: list[str] = []
        cfg = self._config

        for tid, track in sorted(tracks.items()):
            dt = current_time - track.state.last_update_time

            # Promotion
            if track.status == TrackStatus.TENTATIVE:
                if track.hits >= cfg.confirmation_threshold:
                    track.status = TrackStatus.CONFIRMED

            # Coasting
            if track.status == TrackStatus.CONFIRMED:
                if dt > cfg.coast_timeout_s:
                    track.status = TrackStatus.COASTING

            # Loss
            if track.status == TrackStatus.COASTING:
                if dt > cfg.lost_timeout_s or track.position_uncertainty > cfg.max_covariance_m:
                    track.status = TrackStatus.LOST

            # Delete lost tracks
            if track.status == TrackStatus.LOST:
                to_delete.append(tid)

        return to_delete

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        return {"rng_state": self._rng.bit_generator.state}

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]
