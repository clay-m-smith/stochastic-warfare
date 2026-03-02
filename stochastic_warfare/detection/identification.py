"""Identification pipeline — detection → classification → identification.

Converts raw detection results into progressively more specific knowledge
about a contact.  Contact level advances with SNR: low SNR yields only
DETECTED, medium SNR yields CLASSIFIED (domain known), high SNR yields
IDENTIFIED (specific type known).  Multiple observations accumulate
confidence.
"""

from __future__ import annotations

import enum
import math
from typing import Any, NamedTuple

import numpy as np

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.detection.detection import DetectionResult

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Enums and types
# ---------------------------------------------------------------------------


class ContactLevel(enum.IntEnum):
    """Progressive identification levels."""

    UNKNOWN = 0
    DETECTED = 1
    CLASSIFIED = 2
    IDENTIFIED = 3


class ContactInfo(NamedTuple):
    """What is known about a contact at a point in time."""

    level: ContactLevel
    domain_estimate: str | None  # "GROUND", "AERIAL", "NAVAL", etc.
    type_estimate: str | None  # "ARMOR", "INFANTRY", etc.
    specific_estimate: str | None  # "m1a2", "t72", etc.
    confidence: float  # 0–1


# ---------------------------------------------------------------------------
# SNR thresholds for classification / identification
# ---------------------------------------------------------------------------

_CLASSIFY_MARGIN_DB: float = 3.0  # SNR must exceed threshold + this for CLASSIFIED
_IDENTIFY_MARGIN_DB: float = 10.0  # SNR must exceed threshold + this for IDENTIFIED

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class IdentificationEngine:
    """Converts detection results into contact information.

    Parameters
    ----------
    rng:
        A ``numpy.random.Generator`` for stochastic misclassification.
    """

    def __init__(self, rng: np.random.Generator) -> None:
        self._rng = rng

    # ------------------------------------------------------------------
    # Classification from detection
    # ------------------------------------------------------------------

    def classify_from_detection(
        self,
        detection: DetectionResult,
        target_unit: Any = None,
        threshold_db: float = 0.0,
    ) -> ContactInfo:
        """Derive contact info from a single detection result.

        Parameters
        ----------
        detection:
            The raw detection result.
        target_unit:
            If available, the actual target unit (used to derive ground-truth
            values that may be misclassified at low SNR).
        threshold_db:
            The sensor's detection threshold (used for margin computation).
        """
        snr = detection.snr_db
        excess = snr - threshold_db

        # Determine level based on SNR margin
        if excess >= _IDENTIFY_MARGIN_DB:
            level = ContactLevel.IDENTIFIED
        elif excess >= _CLASSIFY_MARGIN_DB:
            level = ContactLevel.CLASSIFIED
        else:
            level = ContactLevel.DETECTED

        # Derive estimates from target if available
        domain_est: str | None = None
        type_est: str | None = None
        specific_est: str | None = None

        if target_unit is not None:
            domain_val = getattr(target_unit, "domain", None)
            if domain_val is not None:
                domain_est = str(domain_val.name) if hasattr(domain_val, "name") else str(domain_val)

            unit_type = getattr(target_unit, "unit_type", None)
            if unit_type is not None:
                type_est = str(unit_type)
                specific_est = str(unit_type)

        # Apply misclassification at lower levels
        misclass_p = self.misclassification_probability(snr, threshold_db)
        if self._rng.random() < misclass_p:
            # Misclassified — degrade one level and null out specifics
            if level == ContactLevel.IDENTIFIED:
                level = ContactLevel.CLASSIFIED
                specific_est = None
            elif level == ContactLevel.CLASSIFIED:
                domain_est = "UNKNOWN"
                type_est = None

        # Confidence scales with SNR excess
        base_confidence = _clamp(0.3 + 0.07 * max(excess, 0.0), 0.0, 1.0)

        # Null out fields above the contact's level
        if level < ContactLevel.CLASSIFIED:
            domain_est = None
            type_est = None
            specific_est = None
        if level < ContactLevel.IDENTIFIED:
            specific_est = None

        return ContactInfo(
            level=level,
            domain_estimate=domain_est,
            type_estimate=type_est if level >= ContactLevel.CLASSIFIED else None,
            specific_estimate=specific_est,
            confidence=round(base_confidence, 4),
        )

    # ------------------------------------------------------------------
    # Contact update (multiple observations)
    # ------------------------------------------------------------------

    @staticmethod
    def update_contact(
        existing: ContactInfo,
        new_observation: ContactInfo,
    ) -> ContactInfo:
        """Merge a new observation into an existing contact.

        Level can only advance (never regress).  Confidence accumulates.
        """
        # Level: take the maximum
        level = max(existing.level, new_observation.level)

        # Domain/type: prefer the newer observation if it's at least as specific
        if new_observation.level >= existing.level:
            domain_est = new_observation.domain_estimate or existing.domain_estimate
            type_est = new_observation.type_estimate or existing.type_estimate
            specific_est = new_observation.specific_estimate or existing.specific_estimate
        else:
            domain_est = existing.domain_estimate
            type_est = existing.type_estimate
            specific_est = existing.specific_estimate

        # Confidence accumulates: 1 - (1-c1)*(1-c2)
        combined_conf = 1.0 - (1.0 - existing.confidence) * (1.0 - new_observation.confidence)
        combined_conf = _clamp(combined_conf, 0.0, 1.0)

        return ContactInfo(
            level=level,
            domain_estimate=domain_est,
            type_estimate=type_est,
            specific_estimate=specific_est,
            confidence=round(combined_conf, 4),
        )

    # ------------------------------------------------------------------
    # Misclassification
    # ------------------------------------------------------------------

    @staticmethod
    def misclassification_probability(snr_db: float, threshold_db: float = 0.0) -> float:
        """Probability of incorrect classification.

        Sigmoid centered at threshold + 6 dB, dropping as SNR increases.
        """
        midpoint = threshold_db + 6.0
        # Sigmoid: P = 1 / (1 + exp(k*(snr - midpoint)))
        k = 0.5
        return _clamp(1.0 / (1.0 + math.exp(k * (snr_db - midpoint))), 0.0, 1.0)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        return {"rng_state": self._rng.bit_generator.state}

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))
