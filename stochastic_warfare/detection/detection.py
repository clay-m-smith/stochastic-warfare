"""Core detection engine — converts sensor + signature + environment into Pd.

All detection uses a unified signal-to-noise (SNR) framework.  Signal strength
depends on target signature and range.  Noise depends on environmental
conditions.  Detection probability Pd = f(SNR, threshold) via the
complementary error function.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any, NamedTuple, TypeAlias

import numpy as np
from pydantic import BaseModel
from scipy.special import erfc  # type: ignore[import-untyped]

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.numba_utils import optional_jit
from stochastic_warfare.core.types import Position
from stochastic_warfare.detection.sensors import (
    SensorInstance,
    SensorType,
    signature_domain_for_sensor_type,
)
from stochastic_warfare.detection.signatures import (
    SignatureDomain,
    SignatureProfile,
    SignatureResolver,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# JIT-compiled SNR kernels (Phase 87a)
# ---------------------------------------------------------------------------


@optional_jit
def _snr_visual_kernel(
    effective_signature: float,
    range_m: float,
    illumination_lux: float,
    visibility_m: float,
) -> float:
    """Pure-math visual SNR computation (JIT-compilable)."""
    if range_m <= 0.0:
        return 100.0
    vis = visibility_m if visibility_m > 1.0 else 1.0
    extinction = 3.0 / vis
    atm_loss = math.exp(-extinction * range_m)
    signal = effective_signature * illumination_lux * atm_loss
    noise = range_m * range_m * 1e-3
    if noise <= 0.0 or signal <= 0.0:
        return -100.0
    return 10.0 * math.log10(signal / noise)


@optional_jit
def _snr_thermal_kernel(
    effective_signature: float,
    range_m: float,
    thermal_contrast: float,
) -> float:
    """Pure-math thermal/IR SNR computation (JIT-compilable)."""
    if range_m <= 0.0:
        return 100.0
    ir_loss_db_per_km = 0.2
    ir_loss_linear = 10.0 ** (ir_loss_db_per_km * range_m / 1000.0 / 10.0)
    signal = effective_signature * thermal_contrast
    noise = range_m * range_m * ir_loss_linear * 1e-6
    if noise <= 0.0 or signal <= 0.0:
        return -100.0
    return 10.0 * math.log10(signal / noise)


@optional_jit
def _snr_radar_kernel(
    peak_power_w: float,
    antenna_gain_dbi: float,
    frequency_mhz: float,
    effective_rcs: float,
    range_m: float,
    atmospheric_atten_db_per_km: float,
) -> float:
    """Pure-math radar SNR computation (JIT-compilable).

    Uses the radar range equation:
    SNR = (Pt * Gt^2 * lam^2 * sigma) / ((4pi)^3 * R^4 * kTB) - atm_loss
    """
    if range_m <= 0.0:
        return 100.0
    c = 299_792_458.0
    four_pi_cubed = (4.0 * math.pi) ** 3
    kTB = 1.380649e-23 * 290.0 * 1e6

    wavelength = c / (frequency_mhz * 1e6)
    gt_linear = 10.0 ** (antenna_gain_dbi / 10.0)

    numerator = peak_power_w * gt_linear * gt_linear * wavelength * wavelength * effective_rcs
    denominator = four_pi_cubed * range_m**4 * kTB

    if denominator <= 0.0:
        return -100.0
    snr_linear = numerator / denominator
    if snr_linear <= 0.0:
        return -100.0

    snr_db = 10.0 * math.log10(snr_linear)
    atm_loss = atmospheric_atten_db_per_km * range_m / 1000.0
    return snr_db - atm_loss


@optional_jit
def _snr_acoustic_kernel(
    source_level_db: float,
    range_m: float,
    ambient_noise_db: float,
    directivity_index_db: float,
    transmission_loss_override: float,
) -> float:
    """Pure-math acoustic signal excess computation (JIT-compilable).

    SE = SL - TL - (NL - DI).
    Pass ``transmission_loss_override < 0`` to use the built-in TL model.
    """
    if range_m <= 0.0:
        return 100.0
    if transmission_loss_override >= 0.0:
        tl = transmission_loss_override
    else:
        r = range_m if range_m >= 1.0 else 1.0
        absorption = 0.001 * range_m / 1000.0
        tl = 20.0 * math.log10(r) + absorption
    return source_level_db - tl - (ambient_noise_db - directivity_index_db)


@optional_jit
def _detection_probability_kernel(snr_db: float, threshold_db: float) -> float:
    """Pure-math detection probability via erfc (JIT-compilable).

    Pd = 0.5 * erfc(-(SNR - threshold) / sqrt(2)), clamped to [0, 1].
    """
    sqrt_2 = 1.4142135623730951
    excess = snr_db - threshold_db
    pd = 0.5 * math.erfc(-excess / sqrt_2)
    return max(0.0, min(1.0, pd))


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class DetectionDecisionStage(str, Enum):
    """Exact terminal stage of one canonical detection API call."""

    PRE_RNG_SENSOR_OFFLINE = "pre_rng_sensor_offline"
    PRE_RNG_UNSUPPORTED_DOMAIN = "pre_rng_unsupported_domain"
    PRE_RNG_ABOVE_MAX_RANGE = "pre_rng_above_max_range"
    PRE_RNG_BELOW_MIN_RANGE = "pre_rng_below_min_range"
    PRE_RNG_OUTSIDE_FOV = "pre_rng_outside_fov"
    PRE_RNG_LOS = "pre_rng_los"
    PRE_RNG_NO_EMISSION = "pre_rng_no_emission"
    STOCHASTIC = "stochastic"


class DetectionResult(NamedTuple):
    """Outcome of a single sensor-vs-target detection check.

    ``range_m`` is the detector's 3-D slant range and remains the uncertainty
    input. ``horizontal_range_m`` is its horizontal ENU measurement component.
    ``None`` exists only for legacy/manual construction; successful fusion
    boundaries reject a result that lacks detector-emitted horizontal geometry.
    """

    detected: bool
    probability: float  # Pd
    snr_db: float
    range_m: float  # 3-D slant range
    sensor_type: SensorType
    bearing_deg: float
    decision_stage: DetectionDecisionStage = DetectionDecisionStage.STOCHASTIC
    horizontal_range_m: float | None = None  # Horizontal ENU measurement


@dataclass(frozen=True, slots=True)
class PreparedDetection:
    """One detection check with complete detector-emitted measurement geometry."""

    probability: float
    snr_db: float
    range_m: float  # 3-D slant range
    horizontal_range_m: float  # Horizontal ENU measurement
    sensor_type: SensorType
    bearing_deg: float

    def adjudicate(self, uniform: float) -> DetectionResult:
        """Apply one caller-owned binary64 uniform to this prepared check."""
        if (
            isinstance(uniform, bool)
            or not isinstance(uniform, (int, float))
            or not math.isfinite(float(uniform))
            or not 0.0 <= float(uniform) < 1.0
        ):
            raise ValueError("detection uniform must be finite in [0, 1)")
        return DetectionResult(
            detected=float(uniform) < self.probability,
            probability=self.probability,
            snr_db=self.snr_db,
            range_m=self.range_m,
            sensor_type=self.sensor_type,
            bearing_deg=self.bearing_deg,
            decision_stage=DetectionDecisionStage.STOCHASTIC,
            horizontal_range_m=self.horizontal_range_m,
        )


@dataclass(frozen=True, slots=True)
class DetectionScanIdentity:
    """Stable owner identity for one sensor attachment's dwell history.

    Fog-of-war scanning supplies the exact side, observer unit, and authored
    equipment index.  This prevents physically separate instances of the same
    catalog sensor from sharing integration gain.
    """

    side: str
    observer_unit_id: str
    source_equipment_index: int

    def __post_init__(self) -> None:
        for value, name in (
            (self.side, "side"),
            (self.observer_unit_id, "observer_unit_id"),
        ):
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError(
                    f"Detection scan identity {name} must be a non-empty trimmed string",
                )
        if (
            isinstance(self.source_equipment_index, bool)
            or not isinstance(self.source_equipment_index, int)
            or self.source_equipment_index < 0
        ):
            raise ValueError(
                "Detection scan identity source_equipment_index must be a non-negative integer",
            )


_LegacyScanCountKey: TypeAlias = tuple[str, str]
_ObserverScanCountKey: TypeAlias = tuple[str, str, int, str, str]
_ScanCountKey: TypeAlias = _LegacyScanCountKey | _ObserverScanCountKey
_OBSERVER_SCAN_STATE_PREFIX = "observer-v1:"


@dataclass(frozen=True, slots=True)
class DetectionScanCountEntry:
    """One immutable dwell counter with its exact production owner."""

    scan_identity: DetectionScanIdentity | None
    sensor_id: str
    target_id: str
    count: int

    def __post_init__(self) -> None:
        if self.scan_identity is not None and type(self.scan_identity) is not DetectionScanIdentity:
            raise TypeError("scan_identity must be a DetectionScanIdentity or None")
        for value, label in (
            (self.sensor_id, "sensor_id"),
            (self.target_id, "target_id"),
        ):
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError(
                    f"Detection scan-count {label} must be non-empty trimmed text",
                )
        if isinstance(self.count, bool) or not isinstance(self.count, int) or self.count <= 0:
            raise ValueError("Detection scan count must be a positive integer")

    def sort_key(self) -> tuple[int, bytes, bytes, int, bytes, bytes]:
        """Return one canonical bytewise key across legacy and FOW owners."""
        if self.scan_identity is None:
            return (
                0,
                b"",
                b"",
                0,
                self.sensor_id.encode("utf-8"),
                self.target_id.encode("utf-8"),
            )
        return (
            1,
            self.scan_identity.side.encode("utf-8"),
            self.scan_identity.observer_unit_id.encode("utf-8"),
            self.scan_identity.source_equipment_index,
            self.sensor_id.encode("utf-8"),
            self.target_id.encode("utf-8"),
        )


@dataclass(frozen=True, slots=True)
class DetectionScanCountSnapshot:
    """Owner-bound immutable scan-count snapshot without RNG state."""

    _entries: tuple[DetectionScanCountEntry, ...]
    _owner_token: object
    _fingerprint: str

    @property
    def entries(self) -> tuple[DetectionScanCountEntry, ...]:
        """Return the immutable canonical entry sequence."""
        return self._entries


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class DetectionConfig(BaseModel):
    """Tunable parameters for the detection engine."""

    default_scan_interval: float = 1.0  # seconds
    max_simultaneous_contacts: int = 100
    noise_std: float = 0.05  # stochastic variation on Pd
    enable_integration_gain: bool = True
    max_integration_gain_db: float = 6.0  # cap at 4 scans (+6 dB)
    max_integration_scans: int = 4


# ---------------------------------------------------------------------------
# Physics helpers
# ---------------------------------------------------------------------------

_BOLTZMANN_K = 1.380649e-23  # J/K
_C = 299_792_458.0  # m/s
_SQRT_2 = math.sqrt(2.0)
_FOUR_PI_CUBED = (4.0 * math.pi) ** 3
_BOLTZMANN_290_1E6 = _BOLTZMANN_K * 290.0 * 1e6


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _range_m(obs: Position, tgt: Position) -> float:
    dx = tgt.easting - obs.easting
    dy = tgt.northing - obs.northing
    dz = tgt.altitude - obs.altitude
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _horizontal_range_m(obs: Position, tgt: Position) -> float:
    dx = tgt.easting - obs.easting
    dy = tgt.northing - obs.northing
    return math.sqrt(dx * dx + dy * dy)


def _bearing_deg(obs: Position, tgt: Position) -> float:
    dx = tgt.easting - obs.easting
    dy = tgt.northing - obs.northing
    return math.degrees(math.atan2(dx, dy)) % 360.0


@dataclass(frozen=True, slots=True)
class _DetectionGeometry:
    """Exact detector geometry reusable across one FOW target opportunity."""

    range_m: float
    horizontal_range_m: float
    bearing_deg: float


def _detection_geometry(
    observer_pos: Position,
    target_pos: Position,
) -> _DetectionGeometry:
    """Compute geometry in the canonical public-detector evaluation order."""
    return _DetectionGeometry(
        range_m=_range_m(observer_pos, target_pos),
        horizontal_range_m=_horizontal_range_m(observer_pos, target_pos),
        bearing_deg=_bearing_deg(observer_pos, target_pos),
    )


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
        *,
        rng: np.random.Generator,
        config: DetectionConfig | None = None,
    ) -> None:
        self._los = los_checker
        self._conditions = conditions_engine
        self._em = em_environment
        self._sig_loader = signature_loader
        self._sensor_loader = sensor_loader
        self._rng = rng
        self._config = config or DetectionConfig()
        # Direct DetectionEngine callers retain the historical
        # (sensor_id, target_id) key.  Production FOW calls use the exact
        # (side, observer_id, equipment_index, sensor_id, target_id) identity.
        self._scan_counts: dict[_ScanCountKey, int] = {}
        self._scan_count_lock = threading.Lock()
        self._scan_count_snapshot_owner = object()

    def __getstate__(self) -> dict[str, Any]:
        """Exclude the process-local mutex from isolated checkpoint staging."""
        state = self.__dict__.copy()
        state.pop("_scan_count_lock", None)
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        """Restore a deepcopy with an independent scan-count mutex."""
        self.__dict__.update(state)
        self._scan_count_lock = threading.Lock()

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
        Delegates to JIT-compiled ``_snr_visual_kernel``.
        """
        return _snr_visual_kernel(effective_signature, range_m, illumination_lux, visibility_m)

    @staticmethod
    def compute_snr_thermal(
        sensor: SensorInstance,
        effective_signature: float,
        range_m: float,
        thermal_contrast: float = 1.0,
    ) -> float:
        """Compute thermal/IR SNR in dB.

        Delegates to JIT-compiled ``_snr_thermal_kernel``.
        """
        return _snr_thermal_kernel(effective_signature, range_m, thermal_contrast)

    @staticmethod
    def compute_snr_radar(
        sensor: SensorInstance,
        effective_rcs: float,
        range_m: float,
        atmospheric_atten_db_per_km: float = 0.01,
    ) -> float:
        """Compute radar SNR in dB using the radar range equation.

        Delegates to JIT-compiled ``_snr_radar_kernel``.
        """
        defn = sensor.definition
        pt = defn.peak_power_w or 1000.0
        gt_dbi = defn.antenna_gain_dbi or 0.0
        freq_mhz = defn.frequency_mhz or 3000.0
        return _snr_radar_kernel(pt, gt_dbi, freq_mhz, effective_rcs, range_m, atmospheric_atten_db_per_km)

    @staticmethod
    def compute_snr_acoustic(
        sensor: SensorInstance,
        source_level_db: float,
        range_m: float,
        ambient_noise_db: float = 70.0,
        transmission_loss: float | None = None,
    ) -> float:
        """Compute acoustic signal excess (SE) in dB.

        Delegates to JIT-compiled ``_snr_acoustic_kernel``.
        """
        tl_override = transmission_loss if transmission_loss is not None else -1.0
        return _snr_acoustic_kernel(
            source_level_db,
            range_m,
            ambient_noise_db,
            sensor.definition.directivity_index_db,
            tl_override,
        )

    # ------------------------------------------------------------------
    # Detection probability
    # ------------------------------------------------------------------

    @staticmethod
    def detection_probability(snr_db: float, threshold_db: float) -> float:
        """Compute Pd given SNR and detection threshold (both in dB).

        Delegates to JIT-compiled ``_detection_probability_kernel``.
        """
        return _detection_probability_kernel(snr_db, threshold_db)

    @staticmethod
    def false_alarm_probability(threshold_db: float) -> float:
        """Compute Pfa from a detection threshold.

        Pfa = 0.5 * erfc(threshold / sqrt(2))
        """
        pfa = float(0.5 * erfc(threshold_db / _SQRT_2))
        return _clamp(pfa, 0.0, 1.0)

    # ------------------------------------------------------------------
    # High-level API
    # ------------------------------------------------------------------

    def reset_scan_counts(self) -> None:
        """Clear all integration gain scan counters."""
        with self._scan_count_lock:
            self._scan_counts.clear()

    def _prepare_detection_core(
        self,
        observer_pos: Position,
        target_pos: Position,
        sensor: SensorInstance,
        target_sig: SignatureProfile,
        *,
        geometry: _DetectionGeometry,
        sensor_type: SensorType,
        signature_domain: SignatureDomain,
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
        observer_heading_deg: float = 0.0,
        target_id: str = "",
        scan_identity: DetectionScanIdentity | None = None,
        jam_snr_penalty_db: float = 0.0,
    ) -> DetectionDecisionStage | PreparedDetection:
        """Run the canonical deterministic gates and stochastic preparation."""
        rng_m = geometry.range_m

        # 1. Operational check
        if not sensor.operational:
            return DetectionDecisionStage.PRE_RNG_SENSOR_OFFLINE

        # 1b. Mapping-owned target-domain policy. Production fog-of-war scans
        # pass the concrete target unit, so an air-search radar cannot become
        # a surface-search capability merely because both consume RCS.
        if target_unit is not None:
            target_domain = getattr(target_unit, "domain", None)
            if target_domain is not None and not sensor.supports_target_domain(
                target_domain,
            ):
                return DetectionDecisionStage.PRE_RNG_UNSUPPORTED_DOMAIN

        # 2. Range check
        if rng_m > sensor.effective_range:
            return DetectionDecisionStage.PRE_RNG_ABOVE_MAX_RANGE
        horizontal_range_m = geometry.horizontal_range_m
        bearing = geometry.bearing_deg

        if rng_m < sensor.definition.min_range_m:
            return DetectionDecisionStage.PRE_RNG_BELOW_MIN_RANGE

        # 2b. FOV check
        fov = sensor.definition.fov_deg
        if fov < 360.0:
            boresight_offset = sensor.definition.boresight_offset_deg
            sensor_boresight = (observer_heading_deg + boresight_offset) % 360.0
            relative_bearing = (bearing - sensor_boresight) % 360.0
            # Normalize to [-180, 180]
            if relative_bearing > 180.0:
                relative_bearing -= 360.0
            if abs(relative_bearing) > fov / 2.0:
                return DetectionDecisionStage.PRE_RNG_OUTSIDE_FOV

        # 3. LOS check (for sensors that require it)
        if sensor.definition.requires_los and self._los is not None:
            los_result = self._los(
                observer_pos,
                target_pos,
                observer_height,
                target_height,
            )
            if not los_result.visible:
                return DetectionDecisionStage.PRE_RNG_LOS

        # 4. Compute SNR
        threshold = sensor.definition.detection_threshold
        if signature_domain is SignatureDomain.VISUAL:
            eff_sig = SignatureResolver.effective_visual(
                target_sig,
                target_unit,
                concealment=concealment,
                posture=posture,
            )
            snr = self.compute_snr_visual(
                sensor,
                eff_sig,
                rng_m,
                illumination_lux,
                visibility_m,
            )
        elif signature_domain is SignatureDomain.THERMAL:
            eff_sig = SignatureResolver.effective_thermal(
                target_sig,
                target_unit,
                thermal_contrast=thermal_contrast,
                posture=posture,
            )
            snr = self.compute_snr_thermal(
                sensor,
                eff_sig,
                rng_m,
                thermal_contrast,
            )
        elif signature_domain is SignatureDomain.RADAR:
            eff_rcs = SignatureResolver.effective_rcs(
                target_sig,
                target_unit,
                bearing,
            )
            snr = self.compute_snr_radar(
                sensor,
                eff_rcs,
                rng_m,
                atmospheric_atten_db_per_km,
            )
        elif signature_domain is SignatureDomain.ACOUSTIC:
            if sensor_type is SensorType.ACTIVE_SONAR:
                snr_source = sensor.definition.source_level_db or 200.0
                # Two-way TL for active sonar (handled in sonar module for detail)
            elif sensor_type in (
                SensorType.PASSIVE_ACOUSTIC,
                SensorType.PASSIVE_SONAR,
            ):
                snr_source = SignatureResolver.effective_acoustic(
                    target_sig,
                    target_unit,
                )
            else:  # pragma: no cover - domain function and dispatch stay paired
                raise ValueError(
                    f"SensorType {sensor_type.name} lacks an acoustic SNR implementation",
                )
            snr = self.compute_snr_acoustic(
                sensor,
                snr_source,
                rng_m,
                ambient_noise_db,
                transmission_loss,
            )
        elif signature_domain is SignatureDomain.ELECTROMAGNETIC and sensor_type is SensorType.ESM:
            em_power = SignatureResolver.effective_em(target_sig, target_unit)
            if em_power == float("-inf"):
                return DetectionDecisionStage.PRE_RNG_NO_EMISSION
            snr = em_power - 20.0 * math.log10(max(rng_m, 1.0))
        else:
            raise ValueError(
                f"SensorType {sensor_type.name} lacks a production SNR implementation",
            )

        # 4b. Jamming penalty (EW module)
        if jam_snr_penalty_db > 0.0:
            snr -= jam_snr_penalty_db

        # 5. Integration gain (dwell/scan accumulation)
        if target_id and self._config.enable_integration_gain:
            key: _ScanCountKey
            if scan_identity is None:
                # Compatibility for direct subsystem consumers.  FOW always
                # supplies an observer-local identity below its public update
                # boundary.
                key = (sensor.sensor_id, target_id)
            else:
                if not isinstance(scan_identity, DetectionScanIdentity):
                    raise TypeError(
                        "scan_identity must be a DetectionScanIdentity",
                    )
                key = (
                    scan_identity.side,
                    scan_identity.observer_unit_id,
                    scan_identity.source_equipment_index,
                    sensor.sensor_id,
                    target_id,
                )
            with self._scan_count_lock:
                raw_scans = self._scan_counts.get(key, 0) + 1
                self._scan_counts[key] = raw_scans
            n_scans = min(raw_scans, self._config.max_integration_scans)
            if n_scans > 1:
                gain_db = 5.0 * math.log10(n_scans)
                gain_db = min(gain_db, self._config.max_integration_gain_db)
                snr += gain_db

        # 6. Compute Pd
        pd = self.detection_probability(snr, threshold)

        return PreparedDetection(
            probability=pd,
            snr_db=snr,
            range_m=rng_m,
            horizontal_range_m=horizontal_range_m,
            sensor_type=sensor_type,
            bearing_deg=bearing,
        )

    def _prepare_fow_detection(
        self,
        observer_pos: Position,
        target_pos: Position,
        sensor: SensorInstance,
        target_sig: SignatureProfile,
        *,
        geometry: _DetectionGeometry,
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
        observer_heading_deg: float = 0.0,
        target_id: str = "",
        scan_identity: DetectionScanIdentity | None = None,
        jam_snr_penalty_db: float = 0.0,
    ) -> DetectionDecisionStage | PreparedDetection:
        """Prepare one trusted FOW check without materializing terminal results."""
        if type(geometry) is not _DetectionGeometry:
            raise TypeError("geometry must be an exact _DetectionGeometry")
        sensor_type = sensor.sensor_type
        signature_domain = signature_domain_for_sensor_type(sensor_type)
        return self._prepare_detection_core(
            observer_pos,
            target_pos,
            sensor,
            target_sig,
            geometry=geometry,
            sensor_type=sensor_type,
            signature_domain=signature_domain,
            target_unit=target_unit,
            observer_height=observer_height,
            target_height=target_height,
            concealment=concealment,
            posture=posture,
            illumination_lux=illumination_lux,
            visibility_m=visibility_m,
            thermal_contrast=thermal_contrast,
            ambient_noise_db=ambient_noise_db,
            atmospheric_atten_db_per_km=atmospheric_atten_db_per_km,
            transmission_loss=transmission_loss,
            observer_heading_deg=observer_heading_deg,
            target_id=target_id,
            scan_identity=scan_identity,
            jam_snr_penalty_db=jam_snr_penalty_db,
        )

    def prepare_detection(
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
        observer_heading_deg: float = 0.0,
        target_id: str = "",
        scan_identity: DetectionScanIdentity | None = None,
        jam_snr_penalty_db: float = 0.0,
    ) -> DetectionResult | PreparedDetection:
        """Run deterministic gates and physics up to the stochastic draw.

        Pre-RNG rejection returns a terminal :class:`DetectionResult` with its
        exact decision stage.  A stochastic opportunity returns a
        :class:`PreparedDetection`; its caller then supplies exactly one
        uniform through :meth:`PreparedDetection.adjudicate`.
        """
        geometry = _detection_geometry(observer_pos, target_pos)
        sensor_type = sensor.sensor_type
        signature_domain = signature_domain_for_sensor_type(sensor_type)
        prepared = self._prepare_detection_core(
            observer_pos,
            target_pos,
            sensor,
            target_sig,
            geometry=geometry,
            sensor_type=sensor_type,
            signature_domain=signature_domain,
            target_unit=target_unit,
            observer_height=observer_height,
            target_height=target_height,
            concealment=concealment,
            posture=posture,
            illumination_lux=illumination_lux,
            visibility_m=visibility_m,
            thermal_contrast=thermal_contrast,
            ambient_noise_db=ambient_noise_db,
            atmospheric_atten_db_per_km=atmospheric_atten_db_per_km,
            transmission_loss=transmission_loss,
            observer_heading_deg=observer_heading_deg,
            target_id=target_id,
            scan_identity=scan_identity,
            jam_snr_penalty_db=jam_snr_penalty_db,
        )
        if isinstance(prepared, PreparedDetection):
            return prepared
        return DetectionResult(
            False,
            0.0,
            -100.0,
            geometry.range_m,
            sensor_type,
            geometry.bearing_deg,
            prepared,
            geometry.horizontal_range_m,
        )

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
        observer_heading_deg: float = 0.0,
        target_id: str = "",
        scan_identity: DetectionScanIdentity | None = None,
        jam_snr_penalty_db: float = 0.0,
        rng: np.random.Generator | None = None,
    ) -> DetectionResult:
        """Run one complete compatibility detection check.

        Production fog-of-war uses :meth:`prepare_detection` and supplies an
        indexed Philox lane only after every pre-RNG gate passes.  Direct
        subsystem callers retain the injected DETECTION stream or may supply
        one explicit compatible generator.
        """
        prepared = self.prepare_detection(
            observer_pos,
            target_pos,
            sensor,
            target_sig,
            target_unit=target_unit,
            observer_height=observer_height,
            target_height=target_height,
            concealment=concealment,
            posture=posture,
            illumination_lux=illumination_lux,
            visibility_m=visibility_m,
            thermal_contrast=thermal_contrast,
            ambient_noise_db=ambient_noise_db,
            atmospheric_atten_db_per_km=atmospheric_atten_db_per_km,
            transmission_loss=transmission_loss,
            observer_heading_deg=observer_heading_deg,
            target_id=target_id,
            scan_identity=scan_identity,
            jam_snr_penalty_db=jam_snr_penalty_db,
        )
        if isinstance(prepared, DetectionResult):
            return prepared
        draw_rng = self._rng if rng is None else rng
        if not isinstance(draw_rng, np.random.Generator):
            raise TypeError("detection rng must be a numpy Generator")
        return prepared.adjudicate(float(draw_rng.random()))

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
                    observer_pos,
                    target_pos,
                    sensor,
                    target_sig,
                    target_unit=target_unit,
                    **kwargs,
                )
                results.append(result)
        return results

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    @staticmethod
    def _scan_count_state_key(key: _ScanCountKey) -> str:
        if len(key) == 2:
            return f"{key[0]}:{key[1]}"
        return _OBSERVER_SCAN_STATE_PREFIX + json.dumps(
            key,
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @staticmethod
    def _scan_count_key_from_state(key_str: str) -> _ScanCountKey:
        if key_str.startswith(_OBSERVER_SCAN_STATE_PREFIX):
            try:
                raw = json.loads(
                    key_str.removeprefix(_OBSERVER_SCAN_STATE_PREFIX),
                )
            except (json.JSONDecodeError, TypeError) as exc:
                raise ValueError(
                    "Observer scan-count state key is invalid",
                ) from exc
            if (
                not isinstance(raw, list)
                or len(raw) != 5
                or not all(isinstance(value, str) for value in (*raw[:2], *raw[3:]))
                or isinstance(raw[2], bool)
                or not isinstance(raw[2], int)
                or raw[2] < 0
            ):
                raise ValueError(
                    "Observer scan-count state key has invalid identity fields",
                )
            identity = DetectionScanIdentity(raw[0], raw[1], raw[2])
            sensor_id, target_id = raw[3], raw[4]
            if not sensor_id or not target_id:
                raise ValueError(
                    "Observer scan-count sensor and target IDs must be non-empty",
                )
            return (
                identity.side,
                identity.observer_unit_id,
                identity.source_equipment_index,
                sensor_id,
                target_id,
            )
        try:
            sensor_id, target_id = key_str.split(":", 1)
        except ValueError as exc:
            raise ValueError("Legacy scan-count state key is invalid") from exc
        if not sensor_id or not target_id:
            raise ValueError(
                "Legacy scan-count sensor and target IDs must be non-empty",
            )
        return (sensor_id, target_id)

    @staticmethod
    def _scan_count_entry(key: _ScanCountKey, count: int) -> DetectionScanCountEntry:
        if len(key) == 2:
            return DetectionScanCountEntry(
                scan_identity=None,
                sensor_id=key[0],
                target_id=key[1],
                count=count,
            )
        return DetectionScanCountEntry(
            scan_identity=DetectionScanIdentity(
                side=key[0],
                observer_unit_id=key[1],
                source_equipment_index=key[2],
            ),
            sensor_id=key[3],
            target_id=key[4],
            count=count,
        )

    @staticmethod
    def _scan_count_key(entry: DetectionScanCountEntry) -> _ScanCountKey:
        identity = entry.scan_identity
        if identity is None:
            return (entry.sensor_id, entry.target_id)
        return (
            identity.side,
            identity.observer_unit_id,
            identity.source_equipment_index,
            entry.sensor_id,
            entry.target_id,
        )

    @staticmethod
    def _scan_count_fingerprint(entries: tuple[DetectionScanCountEntry, ...]) -> str:
        payload = [
            {
                "scan_identity": (
                    None
                    if entry.scan_identity is None
                    else {
                        "side": entry.scan_identity.side,
                        "observer_unit_id": entry.scan_identity.observer_unit_id,
                        "source_equipment_index": entry.scan_identity.source_equipment_index,
                    }
                ),
                "sensor_id": entry.sensor_id,
                "target_id": entry.target_id,
                "count": entry.count,
            }
            for entry in entries
        ]
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def stage_scan_counts(
        self,
        entries: tuple[DetectionScanCountEntry, ...],
    ) -> DetectionScanCountSnapshot:
        """Validate canonical entries and return an owner-bound snapshot."""
        if type(entries) is not tuple:
            raise TypeError("Detection scan-count entries must be an immutable tuple")
        if any(type(entry) is not DetectionScanCountEntry for entry in entries):
            raise TypeError("Detection scan-count entries contain an invalid value")
        if entries != tuple(sorted(entries, key=DetectionScanCountEntry.sort_key)):
            raise ValueError("Detection scan-count entries are not canonically ordered")
        keys = tuple(self._scan_count_key(entry) for entry in entries)
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate detection scan-count identity")
        return DetectionScanCountSnapshot(
            _entries=entries,
            _owner_token=self._scan_count_snapshot_owner,
            _fingerprint=self._scan_count_fingerprint(entries),
        )

    @staticmethod
    def _prevalidated_scan_count_entry(
        key: _ScanCountKey,
        count: int,
    ) -> DetectionScanCountEntry:
        """Materialize one already-validated private counter without restaging."""
        scan_identity: DetectionScanIdentity | None = None
        if len(key) == 5:
            scan_identity = object.__new__(DetectionScanIdentity)
            object.__setattr__(scan_identity, "side", key[0])
            object.__setattr__(scan_identity, "observer_unit_id", key[1])
            object.__setattr__(
                scan_identity,
                "source_equipment_index",
                key[2],
            )
            sensor_id = key[3]
            target_id = key[4]
        else:
            sensor_id = key[0]
            target_id = key[1]
        entry = object.__new__(DetectionScanCountEntry)
        object.__setattr__(entry, "scan_identity", scan_identity)
        object.__setattr__(entry, "sensor_id", sensor_id)
        object.__setattr__(entry, "target_id", target_id)
        object.__setattr__(entry, "count", count)
        return entry

    @staticmethod
    def _raw_scan_count_is_exact_builtin(
        key: object,
        count: object,
    ) -> bool:
        """Return whether one validated raw counter has no mutable subclasses."""
        if type(key) is not tuple or type(count) is not int:
            return False
        if len(key) == 2:
            return type(key[0]) is str and type(key[1]) is str
        return (
            len(key) == 5
            and type(key[0]) is str
            and type(key[1]) is str
            and type(key[2]) is int
            and type(key[3]) is str
            and type(key[4]) is str
        )

    def _stage_fow_scan_count_values(
        self,
        values: dict[_ScanCountKey, int],
    ) -> DetectionScanCountSnapshot:
        """Build one canonical owner snapshot from manager-private raw values."""
        if type(values) is not dict:
            raise TypeError("FOW scan-count values must be an exact dict")
        entries: list[DetectionScanCountEntry] = []
        exact_builtin = True
        for key, count in values.items():
            self._validate_raw_scan_count(key, count)
            entries.append(self._prevalidated_scan_count_entry(key, count))
            exact_builtin = exact_builtin and self._raw_scan_count_is_exact_builtin(
                key,
                count,
            )
        if not exact_builtin:
            public_entries = tuple(
                sorted(
                    (self._scan_count_entry(key, count) for key, count in values.items()),
                    key=DetectionScanCountEntry.sort_key,
                )
            )
            return self.stage_scan_counts(public_entries)
        canonical_entries = tuple(
            sorted(entries, key=DetectionScanCountEntry.sort_key),
        )
        return DetectionScanCountSnapshot(
            _entries=canonical_entries,
            _owner_token=self._scan_count_snapshot_owner,
            _fingerprint=self._scan_count_fingerprint(canonical_entries),
        )

    def _validated_scan_counts(
        self,
        snapshot: DetectionScanCountSnapshot,
    ) -> dict[_ScanCountKey, int]:
        if type(snapshot) is not DetectionScanCountSnapshot:
            raise TypeError("snapshot must be a DetectionScanCountSnapshot")
        if snapshot._owner_token is not self._scan_count_snapshot_owner:
            raise ValueError("Detection scan-count snapshot belongs to another engine")
        restaged = self.stage_scan_counts(snapshot._entries)
        if snapshot._fingerprint != restaged._fingerprint:
            raise ValueError("Detection scan-count snapshot was mutated")
        return {self._scan_count_key(entry): entry.count for entry in snapshot._entries}

    @staticmethod
    def _validate_raw_scan_count(key: object, count: object) -> None:
        """Validate one internal dwell counter without materializing entries."""
        if type(key) is not tuple:
            raise ValueError(
                "Detection scan-count key must be an exact two- or five-item tuple",
            )
        key_length = len(key)
        if key_length != 2 and key_length != 5:
            raise ValueError(
                "Detection scan-count key must be an exact two- or five-item tuple",
            )
        identifier_indexes = (0, 1) if key_length == 2 else (0, 1, 3, 4)
        for index in identifier_indexes:
            value = key[index]
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError(
                    "Detection scan-count identifiers must be non-empty trimmed strings",
                )
            if type(value) is str and value.isascii():
                continue
            try:
                value.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise ValueError(
                    "Detection scan-count identifiers must be valid UTF-8",
                ) from exc
        if key_length == 5:
            source_equipment_index = key[2]
            if (
                isinstance(source_equipment_index, bool)
                or not isinstance(source_equipment_index, int)
                or source_equipment_index < 0
            ):
                raise ValueError(
                    "Detection scan-count source equipment index must be a non-negative integer",
                )
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise ValueError("Detection scan count must be a positive integer")

    def _snapshot_scan_count_values(self) -> dict[_ScanCountKey, int]:
        """Return a validated defensive copy of manager-private dwell counts."""
        with self._scan_count_lock:
            values = dict(self._scan_counts)
        for key, count in values.items():
            self._validate_raw_scan_count(key, count)
        return values

    def _live_scan_count_values_equal(
        self,
        expected: dict[_ScanCountKey, int],
    ) -> bool:
        """Compare validated live dwell counts with one private baseline."""
        if type(expected) is not dict:
            return False
        try:
            for key, count in expected.items():
                self._validate_raw_scan_count(key, count)
            with self._scan_count_lock:
                for key, count in self._scan_counts.items():
                    self._validate_raw_scan_count(key, count)
                return self._scan_counts == expected
        except ValueError:
            return False

    def snapshot_scan_counts(self) -> DetectionScanCountSnapshot:
        """Capture only dwell counters; never capture or advance RNG state."""
        with self._scan_count_lock:
            entries = tuple(
                sorted(
                    (self._scan_count_entry(key, count) for key, count in self._scan_counts.items()),
                    key=DetectionScanCountEntry.sort_key,
                )
            )
        return self.stage_scan_counts(entries)

    def fork_scan_counts(
        self,
        snapshot: DetectionScanCountSnapshot,
        *,
        rng: np.random.Generator,
    ) -> DetectionEngine:
        """Build an isolated engine at one staged dwell state."""
        if not isinstance(rng, np.random.Generator):
            raise TypeError("Detection staging RNG must be a numpy Generator")
        staged_counts = self._validated_scan_counts(snapshot)
        return self._fork_scan_count_values(staged_counts, rng=rng)

    def _fork_scan_count_values(
        self,
        staged_counts: dict[_ScanCountKey, int],
        *,
        rng: np.random.Generator,
    ) -> DetectionEngine:
        """Construct one isolated detection engine from owned counter values."""
        fork = DetectionEngine(
            los_checker=self._los,
            conditions_engine=self._conditions,
            em_environment=self._em,
            signature_loader=self._sig_loader,
            sensor_loader=self._sensor_loader,
            rng=rng,
            config=self._config.model_copy(deep=True),
        )
        with fork._scan_count_lock:
            fork._scan_counts = staged_counts
        return fork

    def commit_scan_counts(self, snapshot: DetectionScanCountSnapshot) -> None:
        """Publish one prevalidated dwell snapshot without touching RNG."""
        staged_counts = self._validated_scan_counts(snapshot)
        self._commit_prevalidated_scan_counts(staged_counts)

    def _commit_prevalidated_scan_counts(
        self,
        staged_counts: dict[_ScanCountKey, int],
    ) -> None:
        """Publish already-validated dwell counts with one locked swap."""
        with self._scan_count_lock:
            self._scan_counts = staged_counts

    def get_scan_count_state(self) -> dict[str, int]:
        """Return the canonical public checkpoint map without RNG state."""
        with self._scan_count_lock:
            return {
                state_key: count
                for state_key, count in sorted(
                    ((self._scan_count_state_key(key), count) for key, count in self._scan_counts.items()),
                )
            }

    def stage_scan_count_state(
        self,
        state: object,
    ) -> DetectionScanCountSnapshot:
        """Strictly stage the canonical public scan-count map."""
        if type(state) is not dict:
            raise ValueError("Detection scan-count state must be a mapping")
        if tuple(state) != tuple(sorted(state)):
            raise ValueError("Detection scan-count state is not canonically ordered")
        entries: list[DetectionScanCountEntry] = []
        staged_keys: set[_ScanCountKey] = set()
        for key_str, count in state.items():
            if type(key_str) is not str or not key_str:
                raise ValueError("Detection scan-count state key must be non-empty text")
            key = self._scan_count_key_from_state(key_str)
            if key_str != self._scan_count_state_key(key):
                raise ValueError(
                    "Detection scan-count state key is not canonically encoded",
                )
            if key in staged_keys:
                raise ValueError("Duplicate detection scan-count identity")
            staged_keys.add(key)
            if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
                raise ValueError("Detection scan count must be a positive integer")
            entries.append(self._scan_count_entry(key, count))
        return self.stage_scan_counts(
            tuple(sorted(entries, key=DetectionScanCountEntry.sort_key)),
        )

    def get_state(self) -> dict[str, Any]:
        return {
            "rng_state": copy.deepcopy(self._rng.bit_generator.state),
            "scan_counts": self.get_scan_count_state(),
        }

    def set_state(self, state: dict[str, Any]) -> None:
        if type(state) is not dict or set(state) != {"rng_state", "scan_counts"}:
            raise ValueError("Detection state has invalid key topology")
        scan_counts = self.stage_scan_count_state(state["scan_counts"])
        try:
            staged_rng = copy.deepcopy(self._rng)
            staged_rng.bit_generator.state = state["rng_state"]
        except (TypeError, ValueError) as exc:
            raise ValueError("Detection RNG state is invalid") from exc
        self.commit_scan_counts(scan_counts)
        self._rng.bit_generator.state = staged_rng.bit_generator.state
