"""Spectrum management — frequency allocation, conflict detection, bandwidth overlap.

Tracks all frequency allocations across the battlespace and detects when
emitters share overlapping bandwidth (co-channel interference, jammer-on-target
overlap, etc.).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.environment.electromagnetic import FrequencyBand

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class FrequencyAllocation(BaseModel):
    """A single frequency allocation record."""

    emitter_id: str
    center_frequency_ghz: float
    bandwidth_ghz: float
    band: FrequencyBand


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Spectrum manager
# ---------------------------------------------------------------------------


class SpectrumManager:
    """Tracks frequency allocations and detects conflicts.

    Thread-safe for single-threaded simulation tick processing.
    """

    def __init__(self) -> None:
        self._allocations: dict[str, FrequencyAllocation] = {}

    # ------------------------------------------------------------------
    # Allocation management
    # ------------------------------------------------------------------

    def allocate(self, allocation: FrequencyAllocation) -> None:
        """Register a frequency allocation."""
        self._allocations[allocation.emitter_id] = allocation

    def deallocate(self, emitter_id: str) -> None:
        """Remove a frequency allocation."""
        self._allocations.pop(emitter_id, None)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_allocations_in_band(
        self, band: FrequencyBand
    ) -> list[FrequencyAllocation]:
        """Return all allocations in the given frequency band."""
        return [a for a in self._allocations.values() if a.band == band]

    def get_allocations_in_range(
        self, freq_min_ghz: float, freq_max_ghz: float
    ) -> list[FrequencyAllocation]:
        """Return allocations whose bandwidth overlaps [freq_min, freq_max]."""
        results: list[FrequencyAllocation] = []
        for a in self._allocations.values():
            a_lo = a.center_frequency_ghz - a.bandwidth_ghz / 2.0
            a_hi = a.center_frequency_ghz + a.bandwidth_ghz / 2.0
            if a_hi >= freq_min_ghz and a_lo <= freq_max_ghz:
                results.append(a)
        return results

    def check_conflict(
        self, allocation: FrequencyAllocation
    ) -> list[FrequencyAllocation]:
        """Return existing allocations that overlap with *allocation*."""
        conflicts: list[FrequencyAllocation] = []
        a_lo = allocation.center_frequency_ghz - allocation.bandwidth_ghz / 2.0
        a_hi = allocation.center_frequency_ghz + allocation.bandwidth_ghz / 2.0
        for existing in self._allocations.values():
            if existing.emitter_id == allocation.emitter_id:
                continue
            if self.bandwidth_overlap(
                allocation.center_frequency_ghz,
                allocation.bandwidth_ghz,
                existing.center_frequency_ghz,
                existing.bandwidth_ghz,
            ) > 0.0:
                conflicts.append(existing)
        return conflicts

    # ------------------------------------------------------------------
    # Bandwidth overlap
    # ------------------------------------------------------------------

    @staticmethod
    def bandwidth_overlap(
        f1: float, bw1: float, f2: float, bw2: float
    ) -> float:
        """Compute fractional bandwidth overlap between two allocations.

        Returns a value in [0.0, 1.0] representing the fraction of the
        smaller bandwidth that overlaps with the larger.
        """
        lo1 = f1 - bw1 / 2.0
        hi1 = f1 + bw1 / 2.0
        lo2 = f2 - bw2 / 2.0
        hi2 = f2 + bw2 / 2.0

        overlap_lo = max(lo1, lo2)
        overlap_hi = min(hi1, hi2)
        overlap = max(0.0, overlap_hi - overlap_lo)

        min_bw = min(bw1, bw2)
        if min_bw <= 0.0:
            return 0.0
        return min(1.0, overlap / min_bw)

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        return {
            "allocations": {
                eid: a.model_dump() for eid, a in self._allocations.items()
            }
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._allocations.clear()
        for eid, data in state.get("allocations", {}).items():
            self._allocations[eid] = FrequencyAllocation(**data)
