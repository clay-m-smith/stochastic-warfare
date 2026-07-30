"""Envelope check helpers for Block 11 golden-scenario regression tests.

A golden scenario defines an *outcome envelope* — a range of plausible Monte
Carlo results derived from historical sources — and its regression test
validates the engine's output against that envelope.  These helpers encode
the envelope format consistently across all four scenarios so that tests
stay readable and assertion logic is uniform.

Reference: ``docs/scenarios/calibration-template.md``
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Envelope checks — operate on the result dict shape emitted by
# ``run_scenario_batch`` (metric name → list[float], one float per iteration)
# ---------------------------------------------------------------------------


def check_winner_envelope(
    results: dict[str, list[float]],
    expected_winner: str,
    min_rate: float = 0.7,
) -> tuple[bool, str]:
    """Check that the expected winner wins in at least *min_rate* of runs.

    Looks up ``results["win_<expected_winner>"]`` — a 0/1 list per iteration.
    Returns ``(passed, diagnostic_message)``.
    """
    key = f"win_{expected_winner}"
    wins = results.get(key)
    if wins is None:
        return False, f"Missing metric {key!r} in results"
    if not wins:
        return False, f"Metric {key!r} is empty"
    rate = sum(wins) / len(wins)
    passed = rate >= min_rate
    msg = (
        f"Winner envelope: {expected_winner} won {rate:.0%} of {len(wins)} iterations "
        f"(target ≥{min_rate:.0%}) — {'PASS' if passed else 'FAIL'}"
    )
    return passed, msg


def check_duration_envelope(
    results: dict[str, list[float]],
    historical_s: float,
    tolerance: float = 0.5,
    tick_duration_s: float = 5.0,
) -> tuple[bool, str]:
    """Check that the average duration falls within ``historical_s ± tolerance × historical_s``.

    Reads ``results["ticks_executed"]`` and converts to seconds using *tick_duration_s*.
    Returns ``(passed, diagnostic_message)``.
    """
    ticks = results.get("ticks_executed")
    if ticks is None:
        return False, "Missing metric 'ticks_executed' in results"
    if not ticks:
        return False, "Metric 'ticks_executed' is empty"
    avg_s = (sum(ticks) / len(ticks)) * tick_duration_s
    lower = historical_s * (1.0 - tolerance)
    upper = historical_s * (1.0 + tolerance)
    passed = lower <= avg_s <= upper
    msg = (
        f"Duration envelope: avg {avg_s:.0f}s (historical {historical_s:.0f}s ±{tolerance:.0%}, "
        f"range [{lower:.0f}, {upper:.0f}]) — {'PASS' if passed else 'FAIL'}"
    )
    return passed, msg


def check_casualty_envelope(
    results: dict[str, list[float]],
    side: str,
    historical: float,
    tolerance: float = 0.4,
    max_override: float | None = None,
) -> tuple[bool, str]:
    """Check that per-side casualties fall within ``historical ± tolerance × historical``.

    For one-sided cases where the historical value is near zero, pass
    ``max_override`` as an absolute ceiling.  When *max_override* is set,
    asserts ``avg <= max_override`` instead of the ±tolerance band.

    Reads ``results["<side>_destroyed"]``.
    Returns ``(passed, diagnostic_message)``.
    """
    key = f"{side}_destroyed"
    destroyed = results.get(key)
    if destroyed is None:
        return False, f"Missing metric {key!r} in results"
    if not destroyed:
        return False, f"Metric {key!r} is empty"
    avg = sum(destroyed) / len(destroyed)

    if max_override is not None:
        passed = avg <= max_override
        msg = (
            f"Casualty envelope ({side}): avg {avg:.1f} destroyed (historical {historical:.0f}, "
            f"max {max_override:.0f}) — {'PASS' if passed else 'FAIL'}"
        )
        return passed, msg

    lower = max(0.0, historical * (1.0 - tolerance))
    upper = historical * (1.0 + tolerance)
    passed = lower <= avg <= upper
    msg = (
        f"Casualty envelope ({side}): avg {avg:.1f} destroyed (historical {historical:.0f} "
        f"±{tolerance:.0%}, range [{lower:.1f}, {upper:.1f}]) — {'PASS' if passed else 'FAIL'}"
    )
    return passed, msg


# ---------------------------------------------------------------------------
# Key-dynamic counters — require a full scenario run with event capture
# ---------------------------------------------------------------------------


def _capture_events(
    scenario_path: str | Path,
    seed: int,
    data_dir: str | Path,
    max_ticks: int,
) -> tuple[Any, ...]:
    """Run one production-owned session and return its recorded events."""
    # Lazy imports keep the assertion-only helpers importable in minimal
    # environments while runtime construction stays behind the typed boundary.
    from stochastic_warfare.simulation.runtime import (
        AnalysisVariant,
        SimulationRuntimeFactory,
    )

    variant_id = "event-capture"
    prepared = SimulationRuntimeFactory().prepare(
        Path(scenario_path),
        Path(data_dir),
        [AnalysisVariant(variant_id=variant_id)],
    )
    session = prepared.build(
        variant_id,
        seed=seed,
        max_ticks=max_ticks,
        record_events=True,
    )
    result = session.run_to_completion()
    if result.ticks_executed != session.context.clock.tick_count:
        raise RuntimeError("Runtime result tick count does not match the production clock")
    if result.duration_s != session.context.clock.elapsed.total_seconds():
        raise RuntimeError("Runtime result duration does not match the production clock")
    if result.victory_result.tick != result.ticks_executed:
        raise RuntimeError("Terminal victory tick does not match the runtime result")
    if session.recorder is None:
        raise RuntimeError("Recorded runtime session did not provide a recorder")
    return tuple(session.recorder.events)


def count_destructions_by_weapon(
    scenario_path: str | Path,
    weapon_id: str,
    seed: int,
    data_dir: str | Path,
    max_ticks: int = 5000,
) -> int:
    """Run a scenario once and count UnitDestroyedEvents attributed to *weapon_id*.

    Used by key-dynamic regression tests to assert that a specific weapon
    dominated destructions (e.g., Javelin at Debecka).  Separate from envelope
    checks because it needs a full run with a recorder, not a metric-only
    batch.
    """
    return sum(
        1
        for e in _capture_events(scenario_path, seed, data_dir, max_ticks)
        if e.event_type == "UnitDestroyedEvent" and e.data.get("weapon_id") == weapon_id
    )


def count_total_destructions(
    scenario_path: str | Path,
    side: str,
    seed: int,
    data_dir: str | Path,
    max_ticks: int = 5000,
) -> int:
    """Run a scenario once and count UnitDestroyedEvents for units on *side*.

    Companion to ``count_destructions_by_weapon`` — divide the former by
    the latter to assert a weapon's share of kills.
    """
    return sum(
        1
        for e in _capture_events(scenario_path, seed, data_dir, max_ticks)
        if e.event_type == "UnitDestroyedEvent" and e.data.get("side") == side
    )


def count_events_by_type(
    scenario_path: str | Path,
    event_type: str,
    seed: int,
    data_dir: str | Path,
    max_ticks: int = 5000,
) -> int:
    """Run a scenario once and count events of a given type.

    Useful for key-dynamic assertions like "at least N CAS engagements" or
    "at least M IED detonations per run".
    """
    return sum(1 for e in _capture_events(scenario_path, seed, data_dir, max_ticks) if e.event_type == event_type)
