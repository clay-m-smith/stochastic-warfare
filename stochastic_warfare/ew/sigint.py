"""Electronic Support (ES) — SIGINT engine.

Models signals intelligence collection: ELINT (radar parameter extraction),
COMINT (communications intercept), and traffic analysis. Provides intercept
probability, AOA/TDOA geolocation, and message traffic inference.

Key equations:
- Intercept probability: based on receiver sensitivity vs emitter power at range
- AOA geolocation: Cramér-Rao bound σ_θ ≈ λ / (2π·L·√SNR)
- TDOA geolocation: requires 3+ receivers, accuracy ∝ baseline / timing_precision
- Traffic analysis: Poisson message rate → unit activity inference
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from typing import Any, NamedTuple

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.ew.emitters import Emitter
from stochastic_warfare.ew.events import EmitterDetectedEvent, SIGINTReportEvent

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & types
# ---------------------------------------------------------------------------

_C = 299_792_458.0  # speed of light m/s


class SIGINTType(enum.IntEnum):
    """SIGINT collection type."""

    ELINT = 0
    COMINT = 1
    TRAFFIC_ANALYSIS = 2


# ---------------------------------------------------------------------------
# SIGINT Collector
# ---------------------------------------------------------------------------


@dataclass
class SIGINTCollector:
    """A SIGINT collection platform."""

    collector_id: str
    unit_id: str
    position: Position
    receiver_sensitivity_dbm: float  # minimum detectable signal
    frequency_range_ghz: tuple[float, float]  # (min, max)
    bandwidth_ghz: float
    df_accuracy_deg: float  # direction finding accuracy
    has_tdoa: bool = False
    side: str = "blue"
    aperture_m: float = 1.0  # antenna aperture for Cramér-Rao bound


# ---------------------------------------------------------------------------
# SIGINT Report
# ---------------------------------------------------------------------------


@dataclass
class SIGINTReport:
    """Result of a SIGINT collection attempt."""

    collector_id: str
    emitter_id: str
    sigint_type: SIGINTType
    intercept_successful: bool
    estimated_position: Position | None
    position_uncertainty_m: float
    estimated_frequency_ghz: float
    estimated_power_dbm: float
    traffic_level: float  # 0.0-1.0 inferred activity
    timestamp: Any = None


# ---------------------------------------------------------------------------
# SIGINT Engine
# ---------------------------------------------------------------------------


class SIGINTEngine:
    """SIGINT collection engine.

    Parameters
    ----------
    event_bus : EventBus
        For publishing SIGINT events.
    rng : np.random.Generator
        PRNG stream.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._collectors: dict[str, SIGINTCollector] = {}
        self._intercept_history: dict[str, list[float]] = {}  # emitter_id → timestamps

    # ------------------------------------------------------------------
    # Collector management
    # ------------------------------------------------------------------

    def register_collector(self, collector: SIGINTCollector) -> None:
        """Register a SIGINT collector."""
        self._collectors[collector.collector_id] = collector

    # ------------------------------------------------------------------
    # Intercept probability
    # ------------------------------------------------------------------

    def compute_intercept_probability(
        self, collector: SIGINTCollector, emitter: Emitter,
    ) -> float:
        """Compute probability of intercept.

        Based on received power vs receiver sensitivity, frequency overlap,
        and dwell time.
        """
        # Check frequency coverage
        f_lo, f_hi = collector.frequency_range_ghz
        if emitter.frequency_ghz < f_lo or emitter.frequency_ghz > f_hi:
            return 0.0

        # Compute received power (free-space path loss)
        rng_m = self._range_m(collector.position, emitter.position)
        if rng_m <= 0:
            rng_m = 1.0

        # Received power = P_tx + G_tx - FSPL
        freq_mhz = emitter.frequency_ghz * 1000.0
        range_km = rng_m / 1000.0
        if range_km <= 0 or freq_mhz <= 0:
            fspl = 0.0
        else:
            fspl = 20.0 * math.log10(range_km) + 20.0 * math.log10(freq_mhz) + 32.45

        received_power_dbm = emitter.power_dbm + emitter.antenna_gain_dbi - fspl

        # Intercept occurs when received > sensitivity
        excess_db = received_power_dbm - collector.receiver_sensitivity_dbm
        if excess_db < -20.0:
            return 0.0
        if excess_db > 20.0:
            return 1.0

        # Sigmoid mapping for intermediate values
        return 1.0 / (1.0 + 10.0 ** (-excess_db / 10.0))

    # ------------------------------------------------------------------
    # Geolocation
    # ------------------------------------------------------------------

    def geolocate_aoa(
        self, collector: SIGINTCollector, emitter: Emitter,
    ) -> tuple[Position, float]:
        """Estimate emitter position using Angle of Arrival (AOA).

        Returns (estimated_position, uncertainty_m).
        Uncertainty from Cramér-Rao bound: σ_θ ≈ λ / (2π·L·√SNR).
        """
        rng_m = self._range_m(collector.position, emitter.position)
        if rng_m <= 0:
            return emitter.position, 0.0

        # Compute bearing
        dx = emitter.position.easting - collector.position.easting
        dy = emitter.position.northing - collector.position.northing
        true_bearing_rad = math.atan2(dx, dy)

        # SNR at receiver
        freq_mhz = emitter.frequency_ghz * 1000.0
        range_km = rng_m / 1000.0
        if range_km > 0 and freq_mhz > 0:
            fspl = 20.0 * math.log10(range_km) + 20.0 * math.log10(freq_mhz) + 32.45
        else:
            fspl = 0.0
        received_dbm = emitter.power_dbm + emitter.antenna_gain_dbi - fspl
        snr_db = received_dbm - collector.receiver_sensitivity_dbm
        snr_linear = max(1.0, 10.0 ** (snr_db / 10.0))

        # Cramér-Rao bound for bearing accuracy
        wavelength = _C / (emitter.frequency_ghz * 1e9)
        aperture = max(collector.aperture_m, wavelength)
        sigma_theta_rad = wavelength / (2.0 * math.pi * aperture * math.sqrt(snr_linear))

        # Add noise to bearing estimate
        bearing_noise = float(self._rng.normal(0, sigma_theta_rad))
        est_bearing_rad = true_bearing_rad + bearing_noise

        # Project estimated position at estimated range
        # (AOA gives bearing only; range estimate is poor from single collector)
        # Use range with uncertainty
        range_uncertainty = rng_m * max(0.1, sigma_theta_rad)
        est_range = rng_m + float(self._rng.normal(0, range_uncertainty * 0.3))
        est_range = max(100.0, est_range)

        est_pos = Position(
            collector.position.easting + est_range * math.sin(est_bearing_rad),
            collector.position.northing + est_range * math.cos(est_bearing_rad),
            emitter.position.altitude,
        )

        # Position uncertainty: range * sigma_theta + range_uncertainty
        uncertainty_m = rng_m * sigma_theta_rad + range_uncertainty * 0.3
        return est_pos, uncertainty_m

    def geolocate_tdoa(
        self,
        collectors: list[SIGINTCollector],
        emitter: Emitter,
    ) -> tuple[Position | None, float]:
        """Estimate emitter position using Time Difference of Arrival (TDOA).

        Requires 3+ collectors. Accuracy depends on baseline length and
        timing precision.

        Returns (estimated_position, uncertainty_m) or (None, inf) if < 3 collectors.
        """
        if len(collectors) < 3:
            return None, float("inf")

        # Compute true ranges
        ranges = [self._range_m(c.position, emitter.position) for c in collectors]

        # TDOA accuracy depends on:
        # 1. Baseline length (distance between collectors)
        # 2. Timing precision (bandwidth of receiver)
        baselines = []
        for i in range(len(collectors)):
            for j in range(i + 1, len(collectors)):
                baselines.append(
                    self._range_m(collectors[i].position, collectors[j].position)
                )
        avg_baseline = sum(baselines) / len(baselines) if baselines else 1.0

        # Timing precision from bandwidth: σ_t ≈ 1/(2π·BW)
        avg_bw = sum(c.bandwidth_ghz for c in collectors) / len(collectors)
        timing_precision_s = 1.0 / (2.0 * math.pi * max(avg_bw * 1e9, 1.0))
        timing_error_m = timing_precision_s * _C

        # Position uncertainty ∝ timing_error * range / baseline
        avg_range = sum(ranges) / len(ranges)
        uncertainty_m = timing_error_m * avg_range / max(avg_baseline, 1.0)

        # Estimate position (centroid of collectors + correction)
        cx = sum(c.position.easting for c in collectors) / len(collectors)
        cy = sum(c.position.northing for c in collectors) / len(collectors)

        # Shift toward emitter using range differences
        # Simplified: weight each collector by inverse range
        total_weight = 0.0
        wx, wy = 0.0, 0.0
        for c, r in zip(collectors, ranges):
            w = 1.0 / max(r, 1.0)
            total_weight += w
            # Direction from collector to emitter
            dx = emitter.position.easting - c.position.easting
            dy = emitter.position.northing - c.position.northing
            dist = math.sqrt(dx * dx + dy * dy)
            if dist > 0:
                wx += w * (c.position.easting + dx / dist * r)
                wy += w * (c.position.northing + dy / dist * r)
            else:
                wx += w * c.position.easting
                wy += w * c.position.northing

        est_x = wx / total_weight if total_weight > 0 else cx
        est_y = wy / total_weight if total_weight > 0 else cy

        # Add noise
        est_x += float(self._rng.normal(0, uncertainty_m * 0.5))
        est_y += float(self._rng.normal(0, uncertainty_m * 0.5))

        est_pos = Position(est_x, est_y, emitter.position.altitude)
        return est_pos, uncertainty_m

    # ------------------------------------------------------------------
    # Traffic analysis
    # ------------------------------------------------------------------

    def analyze_traffic(
        self, collector: SIGINTCollector, intercept_history: list[float],
    ) -> dict[str, float]:
        """Analyze intercepted message traffic for activity patterns.

        Parameters
        ----------
        intercept_history : list[float]
            List of intercept timestamps (seconds).

        Returns
        -------
        dict with 'activity_level' (0-1), 'estimated_rate' (msgs/hr),
        'trend' (-1 to 1, negative=decreasing, positive=increasing).
        """
        if len(intercept_history) < 2:
            return {"activity_level": 0.0, "estimated_rate": 0.0, "trend": 0.0}

        # Message rate (messages per hour)
        sorted_times = sorted(intercept_history)
        duration_h = (sorted_times[-1] - sorted_times[0]) / 3600.0
        if duration_h <= 0:
            return {"activity_level": 0.0, "estimated_rate": 0.0, "trend": 0.0}

        rate = len(intercept_history) / duration_h

        # Activity level: sigmoid of rate (10 msgs/hr → 0.5, 100 → ~1.0)
        activity = 1.0 / (1.0 + math.exp(-(rate - 10.0) / 10.0))

        # Trend: compare first half vs second half rates
        mid = len(sorted_times) // 2
        if mid > 0:
            first_half_dur = max(sorted_times[mid] - sorted_times[0], 1.0)
            second_half_dur = max(sorted_times[-1] - sorted_times[mid], 1.0)
            first_rate = mid / first_half_dur
            second_rate = (len(sorted_times) - mid) / second_half_dur
            if first_rate > 0:
                trend = min(1.0, max(-1.0, (second_rate - first_rate) / first_rate))
            else:
                trend = 1.0 if second_rate > 0 else 0.0
        else:
            trend = 0.0

        return {
            "activity_level": min(1.0, activity),
            "estimated_rate": rate,
            "trend": trend,
        }

    # ------------------------------------------------------------------
    # High-level API
    # ------------------------------------------------------------------

    def attempt_intercept(
        self,
        collector: SIGINTCollector,
        target_emitter: Emitter,
        timestamp: Any = None,
    ) -> SIGINTReport:
        """Attempt to intercept an emitter's signals.

        Returns a SIGINTReport with intercept results.
        """
        prob = self.compute_intercept_probability(collector, target_emitter)
        roll = float(self._rng.random())
        success = roll < prob

        est_pos = None
        uncertainty = float("inf")
        if success:
            est_pos, uncertainty = self.geolocate_aoa(collector, target_emitter)

            # Publish events
            if timestamp is not None and est_pos is not None:
                self._event_bus.publish(EmitterDetectedEvent(
                    timestamp=timestamp, source=ModuleId.EW,
                    detector_id=collector.collector_id,
                    emitter_id=target_emitter.emitter_id,
                    estimated_position=est_pos,
                    uncertainty_m=uncertainty,
                    freq_ghz=target_emitter.frequency_ghz,
                    power_dbm=target_emitter.power_dbm,
                ))

                # Determine SIGINT type
                from stochastic_warfare.ew.emitters import EmitterType
                if target_emitter.emitter_type == EmitterType.RADAR:
                    intel_type = SIGINTType.ELINT
                elif target_emitter.emitter_type in (EmitterType.RADIO, EmitterType.DATA_LINK):
                    intel_type = SIGINTType.COMINT
                else:
                    intel_type = SIGINTType.ELINT

                self._event_bus.publish(SIGINTReportEvent(
                    timestamp=timestamp, source=ModuleId.EW,
                    collector_id=collector.collector_id,
                    emitter_id=target_emitter.emitter_id,
                    intel_type=int(intel_type),
                    confidence=min(1.0, prob),
                ))

        report = SIGINTReport(
            collector_id=collector.collector_id,
            emitter_id=target_emitter.emitter_id,
            sigint_type=SIGINTType.ELINT,
            intercept_successful=success,
            estimated_position=est_pos,
            position_uncertainty_m=uncertainty,
            estimated_frequency_ghz=target_emitter.frequency_ghz if success else 0.0,
            estimated_power_dbm=target_emitter.power_dbm if success else 0.0,
            traffic_level=0.0,
            timestamp=timestamp,
        )
        return report

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _range_m(a: Position, b: Position) -> float:
        dx = b.easting - a.easting
        dy = b.northing - a.northing
        dz = b.altitude - a.altitude
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        return {
            "rng_state": self._rng.bit_generator.state,
            "collectors": {
                cid: {
                    "collector_id": c.collector_id,
                    "unit_id": c.unit_id,
                    "position": tuple(c.position),
                    "receiver_sensitivity_dbm": c.receiver_sensitivity_dbm,
                    "frequency_range_ghz": list(c.frequency_range_ghz),
                    "bandwidth_ghz": c.bandwidth_ghz,
                    "df_accuracy_deg": c.df_accuracy_deg,
                    "has_tdoa": c.has_tdoa,
                    "side": c.side,
                    "aperture_m": c.aperture_m,
                }
                for cid, c in self._collectors.items()
            },
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]
        self._collectors.clear()
        for cid, cdata in state.get("collectors", {}).items():
            self._collectors[cid] = SIGINTCollector(
                collector_id=cdata["collector_id"],
                unit_id=cdata["unit_id"],
                position=Position(*cdata["position"]),
                receiver_sensitivity_dbm=cdata["receiver_sensitivity_dbm"],
                frequency_range_ghz=tuple(cdata["frequency_range_ghz"]),
                bandwidth_ghz=cdata["bandwidth_ghz"],
                df_accuracy_deg=cdata["df_accuracy_deg"],
                has_tdoa=cdata.get("has_tdoa", False),
                side=cdata.get("side", "blue"),
                aperture_m=cdata.get("aperture_m", 1.0),
            )
