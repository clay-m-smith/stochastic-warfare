"""Tests for the Block 11 envelope-check helpers.

Exercises the assertion-building helpers against synthetic result dicts —
no scenario loading or engine runs.  The event-capture helpers
(``count_destructions_by_weapon``, etc.) are smoke-tested with mocks to
verify they wire the recorder correctly; full integration is covered by
the scenario regression tests in Phases 99–102.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from stochastic_warfare.tools.envelope_check import (
    check_casualty_envelope,
    check_duration_envelope,
    check_winner_envelope,
)


# ---------------------------------------------------------------------------
# Winner envelope
# ---------------------------------------------------------------------------


class TestWinnerEnvelope:
    def test_pass_at_exactly_min_rate(self):
        results = {"win_blue": [1.0] * 7 + [0.0] * 3}  # 70%
        passed, msg = check_winner_envelope(results, "blue", min_rate=0.7)
        assert passed
        assert "PASS" in msg
        assert "70%" in msg

    def test_fail_below_min_rate(self):
        results = {"win_blue": [1.0] * 6 + [0.0] * 4}  # 60%
        passed, msg = check_winner_envelope(results, "blue", min_rate=0.7)
        assert not passed
        assert "FAIL" in msg

    def test_all_wins(self):
        results = {"win_red": [1.0] * 10}
        passed, msg = check_winner_envelope(results, "red", min_rate=0.7)
        assert passed

    def test_missing_metric(self):
        results = {"win_blue": [1.0, 1.0]}
        passed, msg = check_winner_envelope(results, "red")
        assert not passed
        assert "Missing" in msg

    def test_empty_metric(self):
        results = {"win_blue": []}
        passed, msg = check_winner_envelope(results, "blue")
        assert not passed
        assert "empty" in msg.lower()

    def test_custom_min_rate(self):
        results = {"win_blue": [1.0] * 5 + [0.0] * 5}  # 50%
        passed, _ = check_winner_envelope(results, "blue", min_rate=0.5)
        assert passed
        passed, _ = check_winner_envelope(results, "blue", min_rate=0.6)
        assert not passed


# ---------------------------------------------------------------------------
# Duration envelope
# ---------------------------------------------------------------------------


class TestDurationEnvelope:
    def test_pass_near_historical(self):
        # Historical = 3600s (1hr), tick_duration=5s → 720 ticks
        # Average of 720 ticks × 5s = 3600s, exactly on target
        results = {"ticks_executed": [720.0] * 10}
        passed, msg = check_duration_envelope(results, historical_s=3600.0)
        assert passed

    def test_pass_within_tolerance(self):
        # 50% tolerance on 3600s → range [1800s, 5400s]
        # 800 ticks × 5s = 4000s, inside range
        results = {"ticks_executed": [800.0] * 10}
        passed, msg = check_duration_envelope(results, historical_s=3600.0, tolerance=0.5)
        assert passed

    def test_fail_too_short(self):
        # 200 ticks × 5s = 1000s, below 1800s lower bound
        results = {"ticks_executed": [200.0] * 10}
        passed, _ = check_duration_envelope(results, historical_s=3600.0, tolerance=0.5)
        assert not passed

    def test_fail_too_long(self):
        # 2000 ticks × 5s = 10000s, above 5400s upper bound
        results = {"ticks_executed": [2000.0] * 10}
        passed, _ = check_duration_envelope(results, historical_s=3600.0, tolerance=0.5)
        assert not passed

    def test_custom_tick_duration(self):
        # 1s tick, 3600 ticks × 1s = 3600s
        results = {"ticks_executed": [3600.0] * 10}
        passed, _ = check_duration_envelope(
            results, historical_s=3600.0, tick_duration_s=1.0
        )
        assert passed

    def test_missing_metric(self):
        passed, msg = check_duration_envelope({}, historical_s=3600.0)
        assert not passed
        assert "Missing" in msg

    def test_mixed_iteration_values(self):
        # mean = 760 ticks × 5 = 3800s, within range
        results = {"ticks_executed": [500.0, 700.0, 900.0, 1000.0, 700.0]}
        passed, _ = check_duration_envelope(results, historical_s=3600.0, tolerance=0.5)
        assert passed


# ---------------------------------------------------------------------------
# Casualty envelope
# ---------------------------------------------------------------------------


class TestCasualtyEnvelope:
    def test_pass_at_historical(self):
        results = {"red_destroyed": [25.0] * 10}
        passed, msg = check_casualty_envelope(results, "red", historical=25.0)
        assert passed

    def test_pass_within_tolerance(self):
        # 40% tolerance on 25 → [15, 35]
        results = {"red_destroyed": [20.0] * 10}
        passed, _ = check_casualty_envelope(results, "red", historical=25.0, tolerance=0.4)
        assert passed

    def test_fail_below_envelope(self):
        results = {"red_destroyed": [10.0] * 10}
        passed, _ = check_casualty_envelope(results, "red", historical=25.0, tolerance=0.4)
        assert not passed

    def test_fail_above_envelope(self):
        results = {"red_destroyed": [40.0] * 10}
        passed, _ = check_casualty_envelope(results, "red", historical=25.0, tolerance=0.4)
        assert not passed

    def test_max_override_pass(self):
        # Historical near zero, max=3
        results = {"blue_destroyed": [0.0, 1.0, 2.0, 0.0, 1.0]}  # mean 0.8
        passed, _ = check_casualty_envelope(
            results, "blue", historical=0.0, max_override=3.0
        )
        assert passed

    def test_max_override_fail(self):
        results = {"blue_destroyed": [5.0, 6.0, 4.0]}  # mean 5.0
        passed, _ = check_casualty_envelope(
            results, "blue", historical=0.0, max_override=3.0
        )
        assert not passed

    def test_historical_zero_without_override(self):
        # With historical=0 and no max_override, only 0 passes
        results = {"blue_destroyed": [0.0] * 10}
        passed, _ = check_casualty_envelope(results, "blue", historical=0.0)
        assert passed

    def test_missing_metric(self):
        passed, msg = check_casualty_envelope({}, "red", historical=25.0)
        assert not passed
        assert "Missing" in msg

    def test_lower_bound_clamped_at_zero(self):
        # historical=5, tolerance=0.5 → lower = max(0, 2.5) = 2.5
        # but historical=1, tolerance=2.0 → lower = max(0, -1) = 0
        results = {"red_destroyed": [0.0] * 10}  # avg 0
        passed, _ = check_casualty_envelope(results, "red", historical=1.0, tolerance=2.0)
        assert passed  # 0 >= 0 (lower clamped)


# ---------------------------------------------------------------------------
# Smoke tests for event-capture helpers — verify they wire the recorder
# correctly without spinning up a real simulation
# ---------------------------------------------------------------------------


class TestCountDestructionsByWeapon:
    def test_counts_matching_events(self):
        """Mock recorder with a mix of events and confirm only weapon_id
        matches on UnitDestroyedEvent are counted."""
        from stochastic_warfare.tools.envelope_check import count_destructions_by_weapon

        fake_events = [
            _mk_event("UnitDestroyedEvent", weapon_id="javelin_clm"),
            _mk_event("UnitDestroyedEvent", weapon_id="javelin_clm"),
            _mk_event("UnitDestroyedEvent", weapon_id="m256_120mm"),
            _mk_event("UnitDisabledEvent", weapon_id="javelin_clm"),  # wrong type
            _mk_event("EngagementEvent", weapon_id="javelin_clm"),  # wrong type
        ]

        with patch_scenario_run(fake_events):
            n = count_destructions_by_weapon(
                "scenario.yaml", "javelin_clm", seed=42, data_dir="data"
            )
        assert n == 2

    def test_zero_if_no_matches(self):
        from stochastic_warfare.tools.envelope_check import count_destructions_by_weapon

        fake_events = [
            _mk_event("UnitDestroyedEvent", weapon_id="m256_120mm"),
        ]
        with patch_scenario_run(fake_events):
            n = count_destructions_by_weapon(
                "scenario.yaml", "javelin_clm", seed=42, data_dir="data"
            )
        assert n == 0


class TestCountTotalDestructions:
    def test_counts_matching_side(self):
        from stochastic_warfare.tools.envelope_check import count_total_destructions

        fake_events = [
            _mk_event("UnitDestroyedEvent", side="red"),
            _mk_event("UnitDestroyedEvent", side="red"),
            _mk_event("UnitDestroyedEvent", side="blue"),
            _mk_event("UnitDisabledEvent", side="red"),  # wrong type
        ]
        with patch_scenario_run(fake_events):
            n = count_total_destructions(
                "scenario.yaml", "red", seed=42, data_dir="data"
            )
        assert n == 2


class TestCountEventsByType:
    def test_counts_exact_type(self):
        from stochastic_warfare.tools.envelope_check import count_events_by_type

        fake_events = [
            _mk_event("EngagementEvent"),
            _mk_event("EngagementEvent"),
            _mk_event("DamageEvent"),
            _mk_event("UnitDestroyedEvent"),
        ]
        with patch_scenario_run(fake_events):
            n = count_events_by_type(
                "scenario.yaml", "EngagementEvent", seed=42, data_dir="data"
            )
        assert n == 2


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _mk_event(event_type: str, **data):
    """Build a fake RecordedEvent-shaped mock."""
    e = MagicMock()
    e.event_type = event_type
    e.data = data
    return e


def patch_scenario_run(fake_events):
    """Patch ScenarioLoader + SimulationEngine + SimulationRecorder to run
    a fake engine loop that terminates immediately with the provided events
    on the recorder.
    """
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        # Patch the lazy-imported modules inside envelope_check
        with (
            patch(
                "stochastic_warfare.simulation.engine.SimulationEngine"
            ) as EngineClass,
            patch(
                "stochastic_warfare.simulation.recorder.SimulationRecorder"
            ) as RecorderClass,
            patch("stochastic_warfare.simulation.scenario.ScenarioLoader") as LoaderClass,
            patch(
                "stochastic_warfare.simulation.victory.VictoryEvaluator"
            ) as _VictoryClass,
            patch(
                "stochastic_warfare.simulation.scenario.VictoryConditionConfig"
            ) as _VicCfgClass,
        ):
            # Loader returns a ctx with an event_bus
            fake_ctx = MagicMock()
            fake_ctx.event_bus = MagicMock()
            LoaderClass.return_value.load.return_value = fake_ctx

            # Recorder has the fake events
            recorder_instance = MagicMock()
            recorder_instance.events = fake_events
            RecorderClass.return_value = recorder_instance

            # Engine step() returns True immediately (game over)
            engine_instance = MagicMock()
            engine_instance.step.return_value = True
            EngineClass.return_value = engine_instance

            yield

    return _ctx()
