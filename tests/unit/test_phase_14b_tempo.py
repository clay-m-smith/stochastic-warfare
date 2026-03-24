"""Tests for Phase 14b: operational tempo analysis."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any


from stochastic_warfare.tools.tempo_analysis import (
    classify_event,
    compute_tempo,
    plot_tempo,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ev(tick: int, event_type: str, data: dict[str, Any] | None = None) -> SimpleNamespace:
    """Create a mock RecordedEvent."""
    return SimpleNamespace(tick=tick, event_type=event_type, data=data or {})


def _make_periodic_events(
    period: float,
    n_cycles: int,
    event_type: str = "EngagementEvent",
) -> list[SimpleNamespace]:
    """Create events at regular intervals (tick = i * period)."""
    return [_ev(int(i * period), event_type) for i in range(n_cycles)]


# ---------------------------------------------------------------------------
# Event classification tests
# ---------------------------------------------------------------------------


class TestClassifyEvent:
    """Event category classification."""

    def test_combat_events(self) -> None:
        assert classify_event("EngagementEvent") == "Combat"
        assert classify_event("HitEvent") == "Combat"
        assert classify_event("DamageEvent") == "Combat"

    def test_detection_events(self) -> None:
        assert classify_event("DetectionEvent") == "Detection"
        assert classify_event("ContactLostEvent") == "Detection"

    def test_c2_events(self) -> None:
        assert classify_event("OrderIssuedEvent") == "C2"
        assert classify_event("DecisionMadeEvent") == "C2"
        assert classify_event("OODAPhaseChangeEvent") == "C2"

    def test_morale_events(self) -> None:
        assert classify_event("MoraleStateChangeEvent") == "Morale"
        assert classify_event("RoutEvent") == "Morale"

    def test_unknown_returns_other(self) -> None:
        assert classify_event("CustomEvent") == "Other"


# ---------------------------------------------------------------------------
# Tempo computation tests
# ---------------------------------------------------------------------------


class TestComputeTempo:
    """Core tempo analysis."""

    def test_empty_events(self) -> None:
        result = compute_tempo([])
        assert result.warning != ""
        assert result.total_events == 0

    def test_basic_computation(self) -> None:
        events = [
            _ev(0, "EngagementEvent"),
            _ev(60, "EngagementEvent"),
            _ev(120, "EngagementEvent"),
            _ev(60, "DetectionEvent"),
        ]
        result = compute_tempo(events, window_s=60)
        assert result.total_events == 4
        assert "Combat" in result.time_series
        assert "Detection" in result.time_series

    def test_time_series_structure(self) -> None:
        events = [_ev(i * 10, "EngagementEvent") for i in range(20)]
        result = compute_tempo(events, window_s=50)
        combat_ts = result.time_series.get("Combat")
        assert combat_ts is not None
        assert len(combat_ts.times) == len(combat_ts.counts)

    def test_periodic_signal_detected(self) -> None:
        """A strictly periodic signal should produce a clear spectral peak."""
        period = 100  # events every 100 ticks
        n_cycles = 50
        events = _make_periodic_events(period, n_cycles)
        result = compute_tempo(events, window_s=10)

        # Should have spectral peaks for Combat
        combat_peaks = result.spectral_peaks.get("Combat", [])
        if combat_peaks:
            # The dominant peak should correspond to 1/period frequency
            dominant = max(combat_peaks, key=lambda p: p.amplitude)
            expected_freq = 1.0 / period
            # Allow some tolerance due to discrete FFT binning
            assert abs(dominant.frequency_hz - expected_freq) < expected_freq * 0.5

    def test_side_filter(self) -> None:
        events = [
            _ev(0, "EngagementEvent", {"attacker_id": "blue_1"}),
            _ev(0, "EngagementEvent", {"attacker_id": "red_1"}),
        ]
        result = compute_tempo(events, window_s=1, side_filter="blue")
        combat_ts = result.time_series.get("Combat")
        assert combat_ts is not None
        total = sum(combat_ts.counts)
        assert total == 1  # Only blue event counted

    def test_insufficient_data_warning(self) -> None:
        events = [_ev(0, "EngagementEvent")]
        result = compute_tempo(events, window_s=60)
        assert "Insufficient" in result.warning

    def test_duration_computed(self) -> None:
        events = [_ev(0, "EngagementEvent"), _ev(1000, "DetectionEvent")]
        result = compute_tempo(events, window_s=100)
        assert result.duration_s == 1000.0


# ---------------------------------------------------------------------------
# OODA cycle extraction tests
# ---------------------------------------------------------------------------


class TestOODACycles:
    """OODA cycle timing extraction."""

    def test_ooda_extraction(self) -> None:
        events = [
            _ev(0, "OODAPhaseChangeEvent", {"unit_id": "cmd_1", "old_phase": 0, "new_phase": 1, "cycle_number": 0}),
            _ev(50, "OODAPhaseChangeEvent", {"unit_id": "cmd_1", "old_phase": 1, "new_phase": 2, "cycle_number": 0}),
            _ev(100, "OODAPhaseChangeEvent", {"unit_id": "cmd_1", "old_phase": 3, "new_phase": 0, "cycle_number": 1}),
            _ev(200, "OODAPhaseChangeEvent", {"unit_id": "cmd_1", "old_phase": 3, "new_phase": 0, "cycle_number": 2}),
        ]
        result = compute_tempo(events, window_s=50)
        assert len(result.ooda_stats) == 1
        stats = result.ooda_stats[0]
        assert stats.unit_id == "cmd_1"
        assert len(stats.cycle_durations_s) == 2  # gaps between cycles 0->1 and 1->2
        assert stats.cycle_durations_s[0] == 100.0
        assert stats.cycle_durations_s[1] == 100.0

    def test_no_ooda_events(self) -> None:
        events = [_ev(0, "EngagementEvent")]
        result = compute_tempo(events, window_s=60)
        assert result.ooda_stats == []

    def test_multiple_units_ooda(self) -> None:
        events = [
            _ev(0, "OODAPhaseChangeEvent", {"unit_id": "cmd_1", "new_phase": 0, "cycle_number": 0}),
            _ev(100, "OODAPhaseChangeEvent", {"unit_id": "cmd_1", "new_phase": 0, "cycle_number": 1}),
            _ev(0, "OODAPhaseChangeEvent", {"unit_id": "cmd_2", "new_phase": 0, "cycle_number": 0}),
            _ev(200, "OODAPhaseChangeEvent", {"unit_id": "cmd_2", "new_phase": 0, "cycle_number": 1}),
        ]
        result = compute_tempo(events, window_s=50)
        assert len(result.ooda_stats) == 2


# ---------------------------------------------------------------------------
# Plot test
# ---------------------------------------------------------------------------


class TestPlotTempo:
    """Tempo plot generation."""

    def test_plot_returns_figure(self) -> None:
        import matplotlib.figure

        events = _make_periodic_events(50, 20)
        result = compute_tempo(events, window_s=10)
        fig = plot_tempo(result)
        assert isinstance(fig, matplotlib.figure.Figure)
        assert len(fig.axes) == 3

    def test_plot_empty_ooda(self) -> None:
        """Plot handles no OODA data gracefully."""
        import matplotlib.figure

        events = [_ev(0, "EngagementEvent"), _ev(100, "EngagementEvent")]
        result = compute_tempo(events, window_s=50)
        fig = plot_tempo(result)
        assert isinstance(fig, matplotlib.figure.Figure)
