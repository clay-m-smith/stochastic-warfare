"""Underwater detection — sonar, MAD, wake, and periscope detection.

Integrates multiple detection methods for submarine hunting: passive/active
sonar, magnetic anomaly detection (MAD), and periscope detection.
"""

from __future__ import annotations

import enum
import math
from typing import Any, NamedTuple

import numpy as np

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import Position
from stochastic_warfare.detection.sensors import SensorInstance, SensorType
from stochastic_warfare.detection.sonar import SonarEngine, SonarType

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Enums and result types
# ---------------------------------------------------------------------------


class UnderwaterDetectionMethod(enum.IntEnum):
    SONAR_PASSIVE = 0
    SONAR_ACTIVE = 1
    MAD = 2
    WAKE_DETECTION = 3
    PERISCOPE_DETECTION = 4


class UnderwaterDetectionResult(NamedTuple):
    """Outcome of an underwater detection attempt."""

    detected: bool
    method: UnderwaterDetectionMethod
    position_estimate: Position
    uncertainty_m: float
    confidence: float


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class UnderwaterDetectionEngine:
    """Multi-method underwater detection for ASW operations.

    Parameters
    ----------
    sonar_engine:
        A :class:`SonarEngine` instance.
    conditions_engine:
        A conditions engine (or mock).
    rng:
        A ``numpy.random.Generator``.
    """

    def __init__(
        self,
        sonar_engine: SonarEngine | None = None,
        conditions_engine: Any = None,
        *,
        rng: np.random.Generator,
    ) -> None:
        self._sonar = sonar_engine
        self._conditions = conditions_engine
        self._rng = rng

    # ------------------------------------------------------------------
    # MAD detection
    # ------------------------------------------------------------------

    def mad_detection(
        self,
        observer_pos: Position,
        target_pos: Position,
        range_m: float,
    ) -> UnderwaterDetectionResult:
        """Magnetic anomaly detection — very short range (~500m).

        Pd drops exponentially: Pd = exp(-range / 200).
        """
        pd = math.exp(-range_m / 200.0)
        pd = max(0.0, min(1.0, pd))

        roll = float(self._rng.random())
        detected = roll < pd

        # MAD gives position estimate near observer (along track)
        uncertainty = range_m * 0.3  # 30% range uncertainty
        est_pos = Position(
            target_pos.easting + float(self._rng.normal(0, max(uncertainty, 1.0))),
            target_pos.northing + float(self._rng.normal(0, max(uncertainty, 1.0))),
            target_pos.altitude,
        )

        return UnderwaterDetectionResult(
            detected=detected,
            method=UnderwaterDetectionMethod.MAD,
            position_estimate=est_pos,
            uncertainty_m=uncertainty,
            confidence=pd if detected else 0.0,
        )

    # ------------------------------------------------------------------
    # Periscope detection
    # ------------------------------------------------------------------

    def periscope_detection(
        self,
        observer_pos: Position,
        target_pos: Position,
        target_depth: float,
        range_m: float,
        visibility_m: float = 10000.0,
    ) -> UnderwaterDetectionResult:
        """Detect a submarine's periscope (only if near surface).

        Only detectable if target_depth < 20m (periscope depth).
        Small RCS (~0.01 m²), tiny visual cross-section.
        """
        if target_depth > 20.0:
            return UnderwaterDetectionResult(
                detected=False,
                method=UnderwaterDetectionMethod.PERISCOPE_DETECTION,
                position_estimate=Position(0.0, 0.0, 0.0),
                uncertainty_m=float("inf"),
                confidence=0.0,
            )

        # Periscope visual: very small signature
        periscope_cross_section = 0.01  # m²
        # Simple visual detection model
        if range_m <= 0:
            pd = 1.0
        else:
            extinction = 3.0 / max(visibility_m, 1.0)
            atm = math.exp(-extinction * range_m)
            signal = periscope_cross_section * 100.0 * atm  # 100 lux baseline
            noise = range_m * range_m * 1e-3
            if noise <= 0 or signal <= 0:
                pd = 0.0
            else:
                snr_lin = signal / noise
                pd = max(0.0, min(1.0, snr_lin * 0.1))

        roll = float(self._rng.random())
        detected = roll < pd

        uncertainty = range_m * 0.1
        est_pos = Position(
            target_pos.easting + float(self._rng.normal(0, max(uncertainty, 1.0))),
            target_pos.northing + float(self._rng.normal(0, max(uncertainty, 1.0))),
            0.0,  # periscope is at surface
        )

        return UnderwaterDetectionResult(
            detected=detected,
            method=UnderwaterDetectionMethod.PERISCOPE_DETECTION,
            position_estimate=est_pos,
            uncertainty_m=uncertainty,
            confidence=pd if detected else 0.0,
        )

    # ------------------------------------------------------------------
    # Speed-noise tradeoff
    # ------------------------------------------------------------------

    @staticmethod
    def speed_noise_tradeoff(
        noise_signature_base: float,
        speed: float,
        quiet_speed: float = 5.0,
    ) -> float:
        """Return noise level: base + 20*log10(speed/quiet_speed).

        Uses the standard naval speed-noise curve from Phase 2.
        """
        if speed <= quiet_speed:
            return noise_signature_base
        return noise_signature_base + 20.0 * math.log10(speed / quiet_speed)

    # ------------------------------------------------------------------
    # Multi-method detection
    # ------------------------------------------------------------------

    def detect_submarine(
        self,
        observer_pos: Position,
        target_pos: Position,
        target_depth: float,
        target_speed: float,
        target_noise_db: float,
        range_m: float,
        observer_sensors: list[SensorInstance] | None = None,
        observer_depth: float = 0.0,
        ambient_noise_db: float = 70.0,
        is_aircraft: bool = False,
    ) -> list[UnderwaterDetectionResult]:
        """Run all applicable detection methods against a submarine.

        Returns a list of results, one per method attempted.
        """
        results: list[UnderwaterDetectionResult] = []

        # 1. Passive sonar (if equipped)
        if self._sonar is not None and observer_sensors:
            for sensor in observer_sensors:
                if sensor.sensor_type in (SensorType.PASSIVE_SONAR, SensorType.PASSIVE_ACOUSTIC):
                    if sensor.operational:
                        sonar_result = self._sonar.passive_detection(
                            sensor, observer_depth, target_noise_db,
                            target_depth, range_m, ambient_noise_db,
                        )
                        est_pos = Position(
                            target_pos.easting + float(self._rng.normal(0, 1000.0)),
                            target_pos.northing + float(self._rng.normal(0, 1000.0)),
                            target_pos.altitude,
                        )
                        results.append(UnderwaterDetectionResult(
                            detected=sonar_result.detected,
                            method=UnderwaterDetectionMethod.SONAR_PASSIVE,
                            position_estimate=est_pos,
                            uncertainty_m=5000.0,  # bearing-only: large uncertainty
                            confidence=max(0.0, min(1.0, sonar_result.signal_excess_db / 20.0)),
                        ))

        # 2. MAD (only if observer is aircraft and range < 500m)
        if is_aircraft and range_m < 500.0:
            results.append(self.mad_detection(observer_pos, target_pos, range_m))

        # 3. Periscope detection (if target near surface)
        if target_depth <= 20.0:
            results.append(self.periscope_detection(
                observer_pos, target_pos, target_depth, range_m,
            ))

        return results

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        return {"rng_state": self._rng.bit_generator.state}

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]
