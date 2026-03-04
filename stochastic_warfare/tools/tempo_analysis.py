"""Operational tempo analysis via FFT spectral decomposition.

Bins simulation events by time window, performs spectral analysis to find
dominant periodicities, and extracts OODA cycle timing statistics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy import fft as scipy_fft

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Event category classification
# ---------------------------------------------------------------------------

_CATEGORY_MAP: dict[str, str] = {
    # Combat
    "EngagementEvent": "Combat",
    "HitEvent": "Combat",
    "DamageEvent": "Combat",
    "SuppressionEvent": "Combat",
    "FratricideEvent": "Combat",
    "MissileLaunchEvent": "Combat",
    "MissileInterceptEvent": "Combat",
    "NavalEngagementEvent": "Combat",
    "AirEngagementEvent": "Combat",
    "TorpedoEvent": "Combat",
    "MineEvent": "Combat",
    # Detection
    "DetectionEvent": "Detection",
    "ClassificationEvent": "Detection",
    "IdentificationEvent": "Detection",
    "ContactLostEvent": "Detection",
    "SubmarineContactEvent": "Detection",
    # C2 / Orders
    "OrderIssuedEvent": "C2",
    "OrderReceivedEvent": "C2",
    "OrderCompletedEvent": "C2",
    "DecisionMadeEvent": "C2",
    "OODAPhaseChangeEvent": "C2",
    "PlanningStartedEvent": "C2",
    "PlanningCompletedEvent": "C2",
    "CommandStatusChangeEvent": "C2",
    # Morale
    "MoraleStateChangeEvent": "Morale",
    "RoutEvent": "Morale",
    "SurrenderEvent": "Morale",
    "RallyEvent": "Morale",
    "StressChangeEvent": "Morale",
    "CohesionChangeEvent": "Morale",
    # Movement
    "MovementEvent": "Movement",
    "FormationChangeEvent": "Movement",
}

CATEGORIES = ("Combat", "Detection", "C2", "Morale", "Movement")


def classify_event(event_type: str) -> str:
    """Return the category for an event type, or 'Other'."""
    return _CATEGORY_MAP.get(event_type, "Other")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class TempoTimeSeries:
    """Event frequency time series for one category."""

    category: str
    times: list[float] = field(default_factory=list)
    counts: list[int] = field(default_factory=list)


@dataclass
class SpectralPeak:
    """A dominant frequency found by FFT."""

    frequency_hz: float
    period_s: float
    amplitude: float


@dataclass
class OODACycleStats:
    """OODA cycle timing statistics for one side/unit."""

    unit_id: str
    cycle_durations_s: list[float] = field(default_factory=list)
    mean_s: float = 0.0
    median_s: float = 0.0
    std_s: float = 0.0


@dataclass
class TempoResult:
    """Complete tempo analysis result."""

    time_series: dict[str, TempoTimeSeries] = field(default_factory=dict)
    spectral_peaks: dict[str, list[SpectralPeak]] = field(default_factory=dict)
    ooda_stats: list[OODACycleStats] = field(default_factory=list)
    window_s: float = 60.0
    total_events: int = 0
    duration_s: float = 0.0
    warning: str = ""


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------


def _bin_events(
    events: list[Any],
    window_s: float,
    side_filter: str | None = None,
) -> tuple[dict[str, list[int]], float]:
    """Bin events by time window and category.

    Returns (category -> count array, total_duration_s).
    """
    if not events:
        return {}, 0.0

    # Extract tick timestamps from events
    ticks = [ev.tick for ev in events]
    min_tick = min(ticks)
    max_tick = max(ticks)

    # Use tick as time proxy (multiply by assumed dt if needed)
    # For now use tick index directly — the caller provides tick_duration_s
    duration = float(max_tick - min_tick)
    if duration <= 0:
        duration = 1.0

    n_bins = max(1, int(duration / window_s) + 1)

    category_bins: dict[str, list[int]] = {cat: [0] * n_bins for cat in CATEGORIES}

    for ev in events:
        if side_filter and not _event_on_side(ev, side_filter):
            continue
        cat = classify_event(ev.event_type)
        if cat in category_bins:
            bin_idx = min(int((ev.tick - min_tick) / window_s), n_bins - 1)
            category_bins[cat][bin_idx] += 1

    return category_bins, duration


def _event_on_side(ev: Any, side: str) -> bool:
    """Check if event relates to a specific side."""
    data = ev.data
    for key in ("observer_side", "side", "winning_side", "capturing_side"):
        if data.get(key) == side:
            return True
    for key in ("unit_id", "attacker_id", "observer_id"):
        val = data.get(key, "")
        if isinstance(val, str) and val.startswith(f"{side}_"):
            return True
    return False


def _fft_peaks(
    counts: list[int],
    window_s: float,
    max_peaks: int = 5,
) -> list[SpectralPeak]:
    """Find dominant spectral peaks in a binned count series."""
    n = len(counts)
    if n < 4:
        return []

    signal = np.array(counts, dtype=float)
    signal -= signal.mean()  # remove DC

    spectrum = scipy_fft.rfft(signal)
    amplitudes = np.abs(spectrum)
    freqs = scipy_fft.rfftfreq(n, d=window_s)

    # Skip DC component (index 0)
    if len(amplitudes) > 1:
        amplitudes[0] = 0.0

    # Find top peaks
    if len(amplitudes) <= 1:
        return []

    indices = np.argsort(amplitudes)[::-1][:max_peaks]
    peaks: list[SpectralPeak] = []
    for idx in indices:
        amp = float(amplitudes[idx])
        if amp < 1e-10:
            continue
        freq = float(freqs[idx])
        period = 1.0 / freq if freq > 0 else float("inf")
        peaks.append(SpectralPeak(frequency_hz=freq, period_s=period, amplitude=amp))

    return peaks


def _extract_ooda_cycles(events: list[Any]) -> list[OODACycleStats]:
    """Extract OODA cycle timing from OODAPhaseChangeEvent sequences.

    A cycle boundary is detected when ``cycle_number`` increments.
    """
    # Group by unit_id
    unit_events: dict[str, list[tuple[int, int]]] = {}  # unit -> [(tick, cycle_number)]
    for ev in events:
        if ev.event_type != "OODAPhaseChangeEvent":
            continue
        uid = ev.data.get("unit_id", "")
        cycle = ev.data.get("cycle_number", 0)
        unit_events.setdefault(uid, []).append((ev.tick, cycle))

    results: list[OODACycleStats] = []
    for uid, timeline in sorted(unit_events.items()):
        if len(timeline) < 2:
            continue

        # Sort by tick
        timeline.sort(key=lambda x: x[0])

        # Find cycle start ticks (first event of each new cycle_number)
        cycle_starts: dict[int, int] = {}  # cycle_number -> first_tick
        for tick, cycle_num in timeline:
            if cycle_num not in cycle_starts:
                cycle_starts[cycle_num] = tick

        # Compute durations between consecutive cycles
        sorted_cycles = sorted(cycle_starts.items())
        durations: list[float] = []
        for i in range(1, len(sorted_cycles)):
            dt = float(sorted_cycles[i][1] - sorted_cycles[i - 1][1])
            if dt > 0:
                durations.append(dt)

        if not durations:
            continue

        arr = np.array(durations)
        results.append(
            OODACycleStats(
                unit_id=uid,
                cycle_durations_s=durations,
                mean_s=float(np.mean(arr)),
                median_s=float(np.median(arr)),
                std_s=float(np.std(arr)),
            )
        )

    return results


def compute_tempo(
    events: list[Any],
    *,
    window_s: float = 60.0,
    side_filter: str | None = None,
) -> TempoResult:
    """Compute operational tempo analysis from recorded events.

    Parameters
    ----------
    events:
        List of ``RecordedEvent`` objects.
    window_s:
        Time window for binning events (seconds / tick units).
    side_filter:
        If set, only count events for this side.

    Returns
    -------
    TempoResult
        Time series, spectral peaks, and OODA cycle statistics.
    """
    if not events:
        return TempoResult(warning="No events provided")

    category_bins, duration = _bin_events(events, window_s, side_filter)

    # Build time series
    time_series: dict[str, TempoTimeSeries] = {}
    for cat, counts in category_bins.items():
        times = [i * window_s for i in range(len(counts))]
        time_series[cat] = TempoTimeSeries(category=cat, times=times, counts=counts)

    # Spectral analysis per category
    spectral_peaks: dict[str, list[SpectralPeak]] = {}
    for cat, counts in category_bins.items():
        peaks = _fft_peaks(counts, window_s)
        if peaks:
            spectral_peaks[cat] = peaks

    # OODA cycle extraction
    ooda_stats = _extract_ooda_cycles(events)

    total = sum(sum(c) for c in category_bins.values())
    warning = ""
    if total < 10:
        warning = "Insufficient data for reliable spectral analysis"

    return TempoResult(
        time_series=time_series,
        spectral_peaks=spectral_peaks,
        ooda_stats=ooda_stats,
        window_s=window_s,
        total_events=total,
        duration_s=duration,
        warning=warning,
    )


# ---------------------------------------------------------------------------
# Plotting (requires matplotlib)
# ---------------------------------------------------------------------------


def plot_tempo(result: TempoResult) -> Any:
    """Create a 3-panel tempo figure.

    Panel 1: Event rate time series by category.
    Panel 2: FFT spectrum (amplitude vs frequency).
    Panel 3: OODA cycle duration boxplot.

    Returns ``matplotlib.figure.Figure``.
    """
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(3, 1, figsize=(12, 10))

    # Panel 1: Time series
    ax1 = axes[0]
    for cat, ts in result.time_series.items():
        if any(c > 0 for c in ts.counts):
            ax1.plot(ts.times, ts.counts, label=cat, alpha=0.8)
    ax1.set_xlabel("Time (s)")
    ax1.set_ylabel("Events per window")
    ax1.set_title("Operational Tempo — Event Rate")
    ax1.legend(loc="upper right", fontsize=8)

    # Panel 2: FFT spectrum
    ax2 = axes[1]
    for cat, peaks in result.spectral_peaks.items():
        if peaks:
            freqs = [p.frequency_hz for p in peaks]
            amps = [p.amplitude for p in peaks]
            ax2.stem(freqs, amps, label=cat, basefmt=" ")
    ax2.set_xlabel("Frequency (Hz)")
    ax2.set_ylabel("Amplitude")
    ax2.set_title("Spectral Analysis — Dominant Periodicities")
    if result.spectral_peaks:
        ax2.legend(loc="upper right", fontsize=8)

    # Panel 3: OODA boxplot
    ax3 = axes[2]
    if result.ooda_stats:
        data = [s.cycle_durations_s for s in result.ooda_stats]
        labels = [s.unit_id for s in result.ooda_stats]
        ax3.boxplot(data, labels=labels)
        ax3.set_ylabel("Cycle Duration (s)")
        ax3.set_title("OODA Cycle Duration Distribution")
        if len(labels) > 5:
            ax3.tick_params(axis="x", rotation=45)
    else:
        ax3.text(0.5, 0.5, "No OODA data available", transform=ax3.transAxes, ha="center")
        ax3.set_title("OODA Cycle Duration Distribution")

    fig.tight_layout()
    plt.close(fig)
    return fig
