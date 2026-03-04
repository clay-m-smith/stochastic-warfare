"""Electronic Protection (EP) — ECCM techniques.

Models frequency hopping, spread spectrum, sidelobe blanking, and adaptive
nulling as countermeasures to jamming. Each technique provides a J/S reduction
in dB that is subtracted from the jammer's effective J/S ratio.

Key equations:
- Frequency hopping: reduction = 10·log10(hop_bw / jammer_bw) when hop_bw > jammer_bw
- Spread spectrum: processing gain = 10·log10(B_spread / B_signal)
- Sidelobe blanking: ~sidelobe_ratio_db when jammer enters via sidelobes
- Adaptive nulling: ~null_depth_db toward jammer direction (limited by elements)
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.ew.events import ECCMActivatedEvent

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & configuration
# ---------------------------------------------------------------------------


class ECCMTechnique(enum.IntEnum):
    """ECCM technique classification."""

    FREQUENCY_HOP = 0
    SPREAD_SPECTRUM = 1
    SIDELOBE_BLANKING = 2
    ADAPTIVE_NULLING = 3


# ---------------------------------------------------------------------------
# ECCM Suite
# ---------------------------------------------------------------------------


@dataclass
class ECCMSuite:
    """ECCM capability suite for a radar or comms system."""

    suite_id: str
    unit_id: str
    techniques: list[ECCMTechnique] = field(default_factory=list)
    hop_bandwidth_ghz: float = 0.0
    hop_rate_hz: float = 0.0
    spread_bandwidth_ghz: float = 0.0
    signal_bandwidth_ghz: float = 0.001
    processing_gain_db: float = 0.0
    sidelobe_ratio_db: float = 25.0
    null_depth_db: float = 30.0
    num_elements: int = 1
    max_nulls: int = 1
    active: bool = True


# ---------------------------------------------------------------------------
# ECCM Engine
# ---------------------------------------------------------------------------


class ECCMEngine:
    """Electronic Protection engine computing jam reduction from ECCM.

    Parameters
    ----------
    event_bus : EventBus
        For publishing ECCM activation events.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._suites: dict[str, ECCMSuite] = {}

    # ------------------------------------------------------------------
    # Suite management
    # ------------------------------------------------------------------

    def register_suite(self, suite: ECCMSuite) -> None:
        """Register an ECCM suite."""
        self._suites[suite.suite_id] = suite

    def activate_suite(
        self, suite_id: str, timestamp: Any = None,
    ) -> None:
        """Activate an ECCM suite."""
        s = self._suites.get(suite_id)
        if s is None:
            return
        s.active = True
        if timestamp is not None and s.techniques:
            self._event_bus.publish(ECCMActivatedEvent(
                timestamp=timestamp, source=ModuleId.EW,
                unit_id=s.unit_id, technique=int(s.techniques[0]),
            ))

    def get_suite_for_unit(self, unit_id: str) -> ECCMSuite | None:
        """Return the ECCM suite for a unit, or None."""
        for s in self._suites.values():
            if s.unit_id == unit_id:
                return s
        return None

    # ------------------------------------------------------------------
    # Jam reduction computation
    # ------------------------------------------------------------------

    def compute_jam_reduction(
        self,
        suite: ECCMSuite,
        jammer_freq_ghz: float = 0.0,
        jammer_bw_ghz: float = 0.0,
        jammer_direction_deg: float | None = None,
        js_ratio_db: float = 0.0,
    ) -> float:
        """Compute total J/S reduction in dB from all active ECCM techniques.

        Parameters
        ----------
        suite : ECCMSuite
            The ECCM suite to evaluate.
        jammer_freq_ghz : float
            Jammer center frequency.
        jammer_bw_ghz : float
            Jammer bandwidth.
        jammer_direction_deg : float or None
            Bearing to jammer (for adaptive nulling).
        js_ratio_db : float
            Current J/S ratio (for sidelobe blanking threshold).

        Returns
        -------
        float
            Total reduction in dB (non-negative).
        """
        if not suite.active or not suite.techniques:
            return 0.0

        total_reduction = 0.0
        for technique in suite.techniques:
            if technique == ECCMTechnique.FREQUENCY_HOP:
                total_reduction += self._freq_hop_reduction(suite, jammer_bw_ghz)
            elif technique == ECCMTechnique.SPREAD_SPECTRUM:
                total_reduction += self._spread_spectrum_reduction(suite)
            elif technique == ECCMTechnique.SIDELOBE_BLANKING:
                total_reduction += self._sidelobe_blanking_reduction(suite, js_ratio_db)
            elif technique == ECCMTechnique.ADAPTIVE_NULLING:
                total_reduction += self._adaptive_nulling_reduction(suite, jammer_direction_deg)

        return max(0.0, total_reduction)

    # ------------------------------------------------------------------
    # Per-technique calculations
    # ------------------------------------------------------------------

    @staticmethod
    def _freq_hop_reduction(suite: ECCMSuite, jammer_bw_ghz: float) -> float:
        """Frequency hopping: reduction = 10·log10(hop_bw / jammer_bw).

        Only effective when hop bandwidth exceeds jammer bandwidth.
        """
        if suite.hop_bandwidth_ghz <= 0 or jammer_bw_ghz <= 0:
            return 0.0
        ratio = suite.hop_bandwidth_ghz / jammer_bw_ghz
        if ratio <= 1.0:
            return 0.0
        return 10.0 * math.log10(ratio)

    @staticmethod
    def _spread_spectrum_reduction(suite: ECCMSuite) -> float:
        """Spread spectrum: processing gain = 10·log10(B_spread / B_signal)."""
        if suite.spread_bandwidth_ghz <= 0 or suite.signal_bandwidth_ghz <= 0:
            return 0.0
        ratio = suite.spread_bandwidth_ghz / suite.signal_bandwidth_ghz
        if ratio <= 1.0:
            return 0.0
        return 10.0 * math.log10(ratio)

    @staticmethod
    def _sidelobe_blanking_reduction(suite: ECCMSuite, js_ratio_db: float) -> float:
        """Sidelobe blanking: effective when jammer enters via sidelobes.

        Assumes jammer is in sidelobes if J/S is above a threshold (strong
        jammer in sidelobes is distinguishable from mainlobe signal).
        Reduction equals the sidelobe ratio.
        """
        if suite.sidelobe_ratio_db <= 0:
            return 0.0
        # Sidelobe blanking is most effective when J/S is moderate
        # (too high = mainlobe, too low = no threat)
        if js_ratio_db > 0:
            return suite.sidelobe_ratio_db
        return 0.0

    @staticmethod
    def _adaptive_nulling_reduction(
        suite: ECCMSuite, jammer_direction_deg: float | None,
    ) -> float:
        """Adaptive nulling: steers antenna null toward jammer.

        Effectiveness depends on having a direction estimate and sufficient
        antenna elements. Limited by max_nulls (each null requires ~2 elements).
        """
        if jammer_direction_deg is None:
            return 0.0
        if suite.num_elements < 2:
            return 0.0
        # Null depth proportional to array capability
        max_possible_nulls = max(1, (suite.num_elements - 1) // 2)
        effective_nulls = min(suite.max_nulls, max_possible_nulls)
        if effective_nulls <= 0:
            return 0.0
        return suite.null_depth_db

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        return {
            "suites": {
                sid: {
                    "suite_id": s.suite_id,
                    "unit_id": s.unit_id,
                    "techniques": [int(t) for t in s.techniques],
                    "hop_bandwidth_ghz": s.hop_bandwidth_ghz,
                    "hop_rate_hz": s.hop_rate_hz,
                    "spread_bandwidth_ghz": s.spread_bandwidth_ghz,
                    "signal_bandwidth_ghz": s.signal_bandwidth_ghz,
                    "processing_gain_db": s.processing_gain_db,
                    "sidelobe_ratio_db": s.sidelobe_ratio_db,
                    "null_depth_db": s.null_depth_db,
                    "num_elements": s.num_elements,
                    "max_nulls": s.max_nulls,
                    "active": s.active,
                }
                for sid, s in self._suites.items()
            }
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._suites.clear()
        for sid, sdata in state.get("suites", {}).items():
            self._suites[sid] = ECCMSuite(
                suite_id=sdata["suite_id"],
                unit_id=sdata["unit_id"],
                techniques=[ECCMTechnique(t) for t in sdata["techniques"]],
                hop_bandwidth_ghz=sdata["hop_bandwidth_ghz"],
                hop_rate_hz=sdata["hop_rate_hz"],
                spread_bandwidth_ghz=sdata["spread_bandwidth_ghz"],
                signal_bandwidth_ghz=sdata.get("signal_bandwidth_ghz", 0.001),
                processing_gain_db=sdata["processing_gain_db"],
                sidelobe_ratio_db=sdata["sidelobe_ratio_db"],
                null_depth_db=sdata["null_depth_db"],
                num_elements=sdata["num_elements"],
                max_nulls=sdata["max_nulls"],
                active=sdata["active"],
            )
