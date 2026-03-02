"""Active and passive sonar detection models.

Implements the sonar equation for both passive and active modes, including
convergence zone detection, towed array bearing ambiguity, and sonar-type
specific behaviors.
"""

from __future__ import annotations

import enum
import math
from typing import Any, NamedTuple

import numpy as np

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.detection.sensors import SensorInstance

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SonarMode(enum.IntEnum):
    ACTIVE = 0
    PASSIVE = 1


class SonarType(enum.IntEnum):
    HULL_MOUNTED = 0
    TOWED_ARRAY = 1
    SONOBUOY = 2
    DIPPING = 3


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


class SonarResult(NamedTuple):
    """Outcome of a sonar detection attempt."""

    detected: bool
    bearing_deg: float
    bearing_uncertainty_deg: float
    range_estimate: float  # -1 for passive (bearing-only)
    range_uncertainty: float
    signal_excess_db: float
    contact_strength: str  # "weak", "moderate", "strong"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _contact_strength(se: float) -> str:
    if se < 3.0:
        return "weak"
    elif se < 10.0:
        return "moderate"
    else:
        return "strong"


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class SonarEngine:
    """Sonar detection for surface ships and submarines.

    Parameters
    ----------
    acoustics_engine:
        An ``UnderwaterAcousticsEngine`` (or mock) providing
        ``.transmission_loss()``, ``.convergence_zone_ranges()``,
        ``.ambient_noise()``.
    conditions_engine:
        A ``ConditionsEngine`` (or mock) for acoustic conditions.
    rng:
        A ``numpy.random.Generator``.
    """

    def __init__(
        self,
        acoustics_engine: Any = None,
        conditions_engine: Any = None,
        rng: np.random.Generator | None = None,
    ) -> None:
        self._acoustics = acoustics_engine
        self._conditions = conditions_engine
        self._rng = rng or np.random.default_rng(0)

    # ------------------------------------------------------------------
    # Passive sonar
    # ------------------------------------------------------------------

    def passive_detection(
        self,
        sensor: SensorInstance,
        observer_depth: float,
        target_noise_db: float,
        target_depth: float,
        range_m: float,
        ambient_noise_db: float = 70.0,
        transmission_loss: float | None = None,
        sonar_type: SonarType = SonarType.HULL_MOUNTED,
    ) -> SonarResult:
        """Passive sonar detection using the sonar equation.

        SE = SL(target) - TL(range) - (NL - DI)
        Detection if SE > DT.
        """
        # Transmission loss
        if transmission_loss is not None:
            tl = transmission_loss
        elif self._acoustics is not None:
            tl = self._acoustics.transmission_loss(range_m, observer_depth, target_depth)
        else:
            # Simple model: spherical spreading + absorption
            tl = 20.0 * math.log10(max(range_m, 1.0)) + 0.001 * range_m / 1000.0

        di = sensor.definition.directivity_index_db
        dt = sensor.definition.detection_threshold

        se = target_noise_db - tl - (ambient_noise_db - di)

        detected = se > dt

        # Bearing estimate with uncertainty
        bearing = float(self._rng.uniform(0, 360))  # random true bearing placeholder
        bearing_unc = self._bearing_uncertainty(sonar_type)
        bearing += float(self._rng.normal(0, bearing_unc))
        bearing = bearing % 360.0

        return SonarResult(
            detected=detected,
            bearing_deg=bearing,
            bearing_uncertainty_deg=bearing_unc,
            range_estimate=-1.0,  # passive: bearing only
            range_uncertainty=-1.0,
            signal_excess_db=se,
            contact_strength=_contact_strength(se),
        )

    # ------------------------------------------------------------------
    # Active sonar
    # ------------------------------------------------------------------

    def active_detection(
        self,
        sensor: SensorInstance,
        observer_depth: float,
        target_rcs_db: float,
        target_depth: float,
        range_m: float,
        ambient_noise_db: float = 70.0,
        transmission_loss: float | None = None,
    ) -> SonarResult:
        """Active sonar detection using the active sonar equation.

        SE = SL(source) - 2*TL + TS - (NL - DI) - DT
        """
        # Source level
        sl = sensor.definition.source_level_db or 200.0

        # Two-way transmission loss
        if transmission_loss is not None:
            tl = transmission_loss
        elif self._acoustics is not None:
            tl = self._acoustics.transmission_loss(range_m, observer_depth, target_depth)
        else:
            tl = 20.0 * math.log10(max(range_m, 1.0)) + 0.001 * range_m / 1000.0

        two_way_tl = 2.0 * tl

        di = sensor.definition.directivity_index_db
        dt = sensor.definition.detection_threshold

        se = sl - two_way_tl + target_rcs_db - (ambient_noise_db - di) - dt

        detected = se > 0.0

        # Active provides range AND bearing
        range_unc = range_m * 0.05  # 5% range uncertainty
        bearing = float(self._rng.uniform(0, 360))
        bearing_unc = 2.0  # active has better bearing
        bearing += float(self._rng.normal(0, bearing_unc))
        bearing = bearing % 360.0

        range_est = range_m + float(self._rng.normal(0, range_unc))
        range_est = max(0.0, range_est)

        return SonarResult(
            detected=detected,
            bearing_deg=bearing,
            bearing_uncertainty_deg=bearing_unc,
            range_estimate=range_est,
            range_uncertainty=range_unc,
            signal_excess_db=se,
            contact_strength=_contact_strength(se),
        )

    # ------------------------------------------------------------------
    # Convergence zone check
    # ------------------------------------------------------------------

    @staticmethod
    def convergence_zone_check(
        range_m: float,
        cz_ranges: list[float] | None = None,
        cz_width: float = 5000.0,
    ) -> bool:
        """Return True if *range_m* falls within a convergence zone annulus.

        CZ occurs at multiples of ~55 km (deep water).  Each zone is an
        annulus of width *cz_width*.
        """
        if cz_ranges is None:
            # Default: first CZ at ~55 km, second at ~110 km
            cz_ranges = [55000.0, 110000.0]

        for cz_center in cz_ranges:
            if abs(range_m - cz_center) < cz_width / 2.0:
                return True
        return False

    # ------------------------------------------------------------------
    # Towed array bearing ambiguity
    # ------------------------------------------------------------------

    @staticmethod
    def towed_array_bearing(
        observer_heading_deg: float,
        true_bearing_deg: float,
    ) -> tuple[float, float]:
        """Return (left_bearing, right_bearing) for towed array.

        Towed arrays have left-right ambiguity: a signal at angle θ from
        the array axis is indistinguishable from 360° - θ.
        """
        # Relative bearing from array axis (stern of ship)
        array_axis = (observer_heading_deg + 180.0) % 360.0
        relative = (true_bearing_deg - array_axis) % 360.0

        # Mirror
        left = (array_axis + relative) % 360.0
        right = (array_axis - relative) % 360.0
        return (left, right)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _bearing_uncertainty(sonar_type: SonarType) -> float:
        """Return bearing uncertainty in degrees for the sonar type."""
        if sonar_type == SonarType.TOWED_ARRAY:
            return 1.0
        elif sonar_type == SonarType.HULL_MOUNTED:
            return 3.0
        elif sonar_type == SonarType.SONOBUOY:
            return 5.0
        elif sonar_type == SonarType.DIPPING:
            return 2.0
        return 5.0

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        return {"rng_state": self._rng.bit_generator.state}

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]
