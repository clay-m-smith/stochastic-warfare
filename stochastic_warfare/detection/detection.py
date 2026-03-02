"""Core detection engine — converts sensor + signature + environment into Pd.

All detection uses a unified signal-to-noise (SNR) framework.  Signal strength
depends on target signature and range.  Noise depends on environmental
conditions.  Detection probability Pd = f(SNR, threshold) via the
complementary error function.
"""

from __future__ import annotations

import math
from typing import Any, NamedTuple

import numpy as np
from pydantic import BaseModel
from scipy.special import erfc  # type: ignore[import-untyped]

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import Meters, Position
from stochastic_warfare.detection.sensors import SensorInstance, SensorType
from stochastic_warfare.detection.signatures import (
    SignatureProfile,
    SignatureResolver,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class DetectionResult(NamedTuple):
    """Outcome of a single sensor-vs-target detection check."""

    detected: bool
    probability: float  # Pd
    snr_db: float
    range_m: float
    sensor_type: SensorType
    bearing_deg: float


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class DetectionConfig(BaseModel):
    """Tunable parameters for the detection engine."""

    default_scan_interval: float = 1.0  # seconds
    max_simultaneous_contacts: int = 100
    noise_std: float = 0.05  # stochastic variation on Pd


# ---------------------------------------------------------------------------
# Physics helpers
# ---------------------------------------------------------------------------

_BOLTZMANN_K = 1.380649e-23  # J/K
_C = 299_792_458.0  # m/s


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _range_m(obs: Position, tgt: Position) -> float:
    dx = tgt.easting - obs.easting
    dy = tgt.northing - obs.northing
    dz = tgt.altitude - obs.altitude
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _bearing_deg(obs: Position, tgt: Position) -> float:
    dx = tgt.easting - obs.easting
    dy = tgt.northing - obs.northing
    return math.degrees(math.atan2(dx, dy)) % 360.0


# ---------------------------------------------------------------------------
# Detection engine
# ---------------------------------------------------------------------------


class DetectionEngine:
    """SNR-based detection probability computation for all sensor types.

    Parameters
    ----------
    los_checker:
        Callable(observer_pos, target_pos, obs_height, tgt_height) → result
        with a ``.visible`` attribute.  Typically ``LOSEngine.check_los``.
    conditions_engine:
        A :class:`ConditionsEngine` (or SimpleNamespace mock providing
        ``.land()`` / ``.electromagnetic()``).
    em_environment:
        An :class:`EMEnvironment` (or mock providing
        ``.radar_horizon()``, ``.free_space_path_loss()``,
        ``.atmospheric_attenuation()``).
    signature_loader:
        A :class:`SignatureLoader` for looking up profiles.
    sensor_loader:
        A :class:`SensorLoader` for looking up definitions.
    rng:
        A ``numpy.random.Generator`` from ``RNGManager.get_stream(DETECTION)``.
    config:
        Optional :class:`DetectionConfig`.
    """

    def __init__(
        self,
        los_checker: Any = None,
        conditions_engine: Any = None,
        em_environment: Any = None,
        signature_loader: Any = None,
        sensor_loader: Any = None,
        rng: np.random.Generator | None = None,
        config: DetectionConfig | None = None,
    ) -> None:
        self._los = los_checker
        self._conditions = conditions_engine
        self._em = em_environment
        self._sig_loader = signature_loader
        self._sensor_loader = sensor_loader
        self._rng = rng or np.random.default_rng(0)
        self._config = config or DetectionConfig()

    # ------------------------------------------------------------------
    # SNR computation per sensor type
    # ------------------------------------------------------------------

    @staticmethod
    def compute_snr_visual(
        sensor: SensorInstance,
        effective_signature: float,
        range_m: float,
        illumination_lux: float = 100.0,
        visibility_m: float = 10000.0,
    ) -> float:
        """Compute visual SNR in dB.

        SNR = (cross_section * illumination) / (range² * atmospheric_extinction)
        """
        if range_m <= 0:
            return 100.0
        # Atmospheric extinction: Beer-Lambert, visibility = range at which
        # transmission drops to 5%.  extinction coeff = 3.0 / visibility.
        extinction = 3.0 / max(visibility_m, 1.0)
        atm_loss = math.exp(-extinction * range_m)
        signal = effective_signature * illumination_lux * atm_loss
        noise = range_m * range_m * 1e-3  # scaling factor
        if noise <= 0 or signal <= 0:
            return -100.0
        return 10.0 * math.log10(signal / noise)

    @staticmethod
    def compute_snr_thermal(
        sensor: SensorInstance,
        effective_signature: float,
        range_m: float,
        thermal_contrast: float = 1.0,
    ) -> float:
        """Compute thermal/IR SNR in dB.

        SNR = heat_signature / (range² * IR_atmospheric_loss)
        """
        if range_m <= 0:
            return 100.0
        # IR atmospheric loss: roughly 0.2 dB/km at medium IR
        ir_loss_db_per_km = 0.2
        ir_loss_linear = 10.0 ** (ir_loss_db_per_km * range_m / 1000.0 / 10.0)
        signal = effective_signature * thermal_contrast
        noise = range_m * range_m * ir_loss_linear * 1e-6
        if noise <= 0 or signal <= 0:
            return -100.0
        return 10.0 * math.log10(signal / noise)

    @staticmethod
    def compute_snr_radar(
        sensor: SensorInstance,
        effective_rcs: float,
        range_m: float,
        atmospheric_atten_db_per_km: float = 0.01,
    ) -> float:
        """Compute radar SNR in dB using the radar range equation.

        SNR = (Pt * Gt² * λ² * σ) / ((4π)³ * R⁴ * k*T*B) - atmospheric_loss
        """
        defn = sensor.definition
        pt = defn.peak_power_w or 1000.0
        gt_dbi = defn.antenna_gain_dbi or 0.0
        freq_mhz = defn.frequency_mhz or 3000.0

        if range_m <= 0:
            return 100.0

        wavelength = _C / (freq_mhz * 1e6)
        gt_linear = 10.0 ** (gt_dbi / 10.0)

        numerator = pt * gt_linear * gt_linear * wavelength * wavelength * effective_rcs
        denominator = (4.0 * math.pi) ** 3 * range_m ** 4 * _BOLTZMANN_K * 290.0 * 1e6

        if denominator <= 0:
            return -100.0

        snr_linear = numerator / denominator
        if snr_linear <= 0:
            return -100.0

        snr_db = 10.0 * math.log10(snr_linear)

        # Atmospheric loss
        atm_loss = atmospheric_atten_db_per_km * range_m / 1000.0
        snr_db -= atm_loss

        return snr_db

    @staticmethod
    def compute_snr_acoustic(
        sensor: SensorInstance,
        source_level_db: float,
        range_m: float,
        ambient_noise_db: float = 70.0,
        transmission_loss: float | None = None,
    ) -> float:
        """Compute acoustic signal excess (SE) in dB.

        SE = SL - TL - (NL - DI)
        """
        if range_m <= 0:
            return 100.0

        # Transmission loss: spherical spreading + absorption
        if transmission_loss is not None:
            tl = transmission_loss
        else:
            # Simple model: 20*log10(R) + absorption
            absorption = 0.001 * range_m / 1000.0  # ~1 dB/km
            tl = 20.0 * math.log10(max(range_m, 1.0)) + absorption

        di = sensor.definition.directivity_index_db
        se = source_level_db - tl - (ambient_noise_db - di)
        return se

    # ------------------------------------------------------------------
    # Detection probability
    # ------------------------------------------------------------------

    @staticmethod
    def detection_probability(snr_db: float, threshold_db: float) -> float:
        """Compute Pd given SNR and detection threshold (both in dB).

        Uses the Gaussian model: Pd = 0.5 * erfc(-(SNR - threshold) / sqrt(2))
        Clamped to [0, 1].
        """
        excess = snr_db - threshold_db
        pd = float(0.5 * erfc(-excess / math.sqrt(2.0)))
        return _clamp(pd, 0.0, 1.0)

    @staticmethod
    def false_alarm_probability(threshold_db: float) -> float:
        """Compute Pfa from a detection threshold.

        Pfa = 0.5 * erfc(threshold / sqrt(2))
        """
        pfa = float(0.5 * erfc(threshold_db / math.sqrt(2.0)))
        return _clamp(pfa, 0.0, 1.0)

    # ------------------------------------------------------------------
    # High-level API
    # ------------------------------------------------------------------

    def check_detection(
        self,
        observer_pos: Position,
        target_pos: Position,
        sensor: SensorInstance,
        target_sig: SignatureProfile,
        target_unit: Any = None,
        observer_height: float = 1.8,
        target_height: float = 0.0,
        concealment: float = 0.0,
        posture: int = 0,
        illumination_lux: float = 100.0,
        visibility_m: float = 10000.0,
        thermal_contrast: float = 1.0,
        ambient_noise_db: float = 70.0,
        atmospheric_atten_db_per_km: float = 0.01,
        transmission_loss: float | None = None,
    ) -> DetectionResult:
        """Run a single sensor check against a target.

        Returns a :class:`DetectionResult` indicating whether detection
        occurred and the computed Pd / SNR.
        """
        rng_m = _range_m(observer_pos, target_pos)
        bearing = _bearing_deg(observer_pos, target_pos)
        st = sensor.sensor_type

        # 1. Operational check
        if not sensor.operational:
            return DetectionResult(False, 0.0, -100.0, rng_m, st, bearing)

        # 2. Range check
        if rng_m > sensor.effective_range:
            return DetectionResult(False, 0.0, -100.0, rng_m, st, bearing)
        if rng_m < sensor.definition.min_range_m:
            return DetectionResult(False, 0.0, -100.0, rng_m, st, bearing)

        # 3. LOS check (for sensors that require it)
        if sensor.definition.requires_los and self._los is not None:
            los_result = self._los(observer_pos, target_pos, observer_height, target_height)
            if not los_result.visible:
                return DetectionResult(False, 0.0, -100.0, rng_m, st, bearing)

        # 4. Compute SNR
        threshold = sensor.definition.detection_threshold
        if st in (SensorType.VISUAL, SensorType.NVG):
            eff_sig = SignatureResolver.effective_visual(
                target_sig, target_unit, concealment=concealment, posture=posture
            )
            snr = self.compute_snr_visual(sensor, eff_sig, rng_m, illumination_lux, visibility_m)
        elif st == SensorType.THERMAL:
            eff_sig = SignatureResolver.effective_thermal(
                target_sig, target_unit, thermal_contrast=thermal_contrast, posture=posture
            )
            snr = self.compute_snr_thermal(sensor, eff_sig, rng_m, thermal_contrast)
        elif st == SensorType.RADAR:
            eff_rcs = SignatureResolver.effective_rcs(target_sig, target_unit, bearing)
            snr = self.compute_snr_radar(sensor, eff_rcs, rng_m, atmospheric_atten_db_per_km)
        elif st in (SensorType.PASSIVE_ACOUSTIC, SensorType.PASSIVE_SONAR):
            sl = SignatureResolver.effective_acoustic(target_sig, target_unit)
            snr = self.compute_snr_acoustic(sensor, sl, rng_m, ambient_noise_db, transmission_loss)
        elif st == SensorType.ACTIVE_SONAR:
            sl = sensor.definition.source_level_db or 200.0
            # Two-way TL for active sonar (handled in sonar module for detail)
            snr = self.compute_snr_acoustic(sensor, sl, rng_m, ambient_noise_db, transmission_loss)
        elif st == SensorType.ESM:
            em_power = SignatureResolver.effective_em(target_sig, target_unit)
            if em_power == float("-inf"):
                return DetectionResult(False, 0.0, -100.0, rng_m, st, bearing)
            snr = em_power - 20.0 * math.log10(max(rng_m, 1.0))
        else:
            snr = -100.0

        # 5. Compute Pd
        pd = self.detection_probability(snr, threshold)

        # 6. Stochastic roll
        roll = float(self._rng.random())
        detected = roll < pd

        return DetectionResult(detected, pd, snr, rng_m, st, bearing)

    def scan_all_targets(
        self,
        observer_pos: Position,
        observer_sensors: list[SensorInstance],
        targets: list[tuple[Position, SignatureProfile, Any]],
        **kwargs: Any,
    ) -> list[DetectionResult]:
        """Scan all targets with all observer sensors.

        Parameters
        ----------
        targets:
            List of (position, signature_profile, unit_or_none) tuples.
        **kwargs:
            Passed through to :meth:`check_detection`.

        Returns list of :class:`DetectionResult` for each detection attempt.
        """
        results: list[DetectionResult] = []
        for sensor in observer_sensors:
            if not sensor.operational:
                continue
            for target_pos, target_sig, target_unit in targets:
                result = self.check_detection(
                    observer_pos, target_pos, sensor, target_sig,
                    target_unit=target_unit, **kwargs,
                )
                results.append(result)
        return results

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        return {
            "rng_state": self._rng.bit_generator.state,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]
