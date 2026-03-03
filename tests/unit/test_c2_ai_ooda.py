"""Tests for the OODA loop engine (c2.ai.ooda).

Uses shared fixtures from conftest.py: rng, event_bus, sim_clock, rng_manager.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.c2.ai.ooda import OODAConfig, OODALoopEngine, OODAPhase
from stochastic_warfare.c2.events import OODALoopResetEvent, OODAPhaseChangeEvent
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.entities.organization.echelons import EchelonLevel

from tests.conftest import DEFAULT_SEED, TS, make_rng


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine(
    event_bus: EventBus,
    rng: np.random.Generator | None = None,
    config: OODAConfig | None = None,
) -> OODALoopEngine:
    """Create an OODALoopEngine with sane defaults."""
    return OODALoopEngine(
        event_bus=event_bus,
        rng=rng or make_rng(),
        config=config,
    )


def _capture_events(event_bus: EventBus, event_type: type) -> list:
    """Subscribe to *event_type* and return a mutable list of captured events."""
    captured: list = []
    event_bus.subscribe(event_type, captured.append)
    return captured


# ---------------------------------------------------------------------------
# OODAPhase enum
# ---------------------------------------------------------------------------


class TestOODAPhaseEnum:
    """OODAPhase enum values and ordering."""

    def test_observe_is_zero(self) -> None:
        assert OODAPhase.OBSERVE == 0

    def test_orient_is_one(self) -> None:
        assert OODAPhase.ORIENT == 1

    def test_decide_is_two(self) -> None:
        assert OODAPhase.DECIDE == 2

    def test_act_is_three(self) -> None:
        assert OODAPhase.ACT == 3

    def test_four_phases_total(self) -> None:
        assert len(OODAPhase) == 4


# ---------------------------------------------------------------------------
# OODAConfig
# ---------------------------------------------------------------------------


class TestOODAConfig:
    """OODAConfig defaults and custom values."""

    def test_defaults(self) -> None:
        cfg = OODAConfig()
        assert cfg.timing_sigma == 0.3
        assert cfg.degraded_mult == 1.5
        assert cfg.disrupted_mult == 3.0

    def test_default_durations_has_all_echelons(self) -> None:
        cfg = OODAConfig()
        expected_keys = {"PLATOON", "COMPANY", "BATTALION", "BRIGADE", "DIVISION", "CORPS"}
        assert set(cfg.base_durations_s.keys()) == expected_keys

    def test_default_durations_has_all_phases(self) -> None:
        cfg = OODAConfig()
        for echelon_durations in cfg.base_durations_s.values():
            assert set(echelon_durations.keys()) == {"OBSERVE", "ORIENT", "DECIDE", "ACT"}

    def test_custom_values(self) -> None:
        cfg = OODAConfig(timing_sigma=0.5, degraded_mult=2.0, disrupted_mult=4.0)
        assert cfg.timing_sigma == 0.5
        assert cfg.degraded_mult == 2.0
        assert cfg.disrupted_mult == 4.0

    def test_custom_durations(self) -> None:
        custom = {"PLATOON": {"OBSERVE": 10, "ORIENT": 20, "DECIDE": 15, "ACT": 10}}
        cfg = OODAConfig(base_durations_s=custom)
        assert cfg.base_durations_s["PLATOON"]["OBSERVE"] == 10


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    """register_commander creates state correctly."""

    def test_register_creates_state(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = OODALoopEngine(event_bus, rng)
        engine.register_commander("bn_1", EchelonLevel.BATTALION)
        assert engine.get_phase("bn_1") == OODAPhase.OBSERVE
        assert engine.get_cycle_count("bn_1") == 0

    def test_register_different_echelons(
        self, event_bus: EventBus, rng: np.random.Generator,
    ) -> None:
        engine = OODALoopEngine(event_bus, rng)
        engine.register_commander("plt_1", EchelonLevel.PLATOON)
        engine.register_commander("div_1", EchelonLevel.DIVISION)
        # Both start at OBSERVE
        assert engine.get_phase("plt_1") == OODAPhase.OBSERVE
        assert engine.get_phase("div_1") == OODAPhase.OBSERVE

    def test_register_timer_not_started(
        self, event_bus: EventBus, rng: np.random.Generator,
    ) -> None:
        engine = OODALoopEngine(event_bus, rng)
        engine.register_commander("co_1", EchelonLevel.COMPANY)
        # Update should not return anything for unstarted commanders
        result = engine.update(100.0)
        assert result == []


# ---------------------------------------------------------------------------
# compute_phase_duration
# ---------------------------------------------------------------------------


class TestComputePhaseDuration:
    """Phase duration calculation with modifiers and variation."""

    def test_basic_calculation(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = OODALoopEngine(event_bus, rng)
        duration = engine.compute_phase_duration(EchelonLevel.BATTALION, OODAPhase.ORIENT)
        # Base is 900s for battalion ORIENT, with log-normal variation
        assert duration > 0

    def test_staff_quality_reduces_duration(self, event_bus: EventBus) -> None:
        """Higher staff quality means shorter decision time."""
        rng1 = make_rng(100)
        rng2 = make_rng(100)
        engine1 = OODALoopEngine(event_bus, rng1)
        engine2 = OODALoopEngine(event_bus, rng2)
        d_normal = engine1.compute_phase_duration(
            EchelonLevel.BATTALION, OODAPhase.DECIDE, staff_quality=1.0,
        )
        d_high = engine2.compute_phase_duration(
            EchelonLevel.BATTALION, OODAPhase.DECIDE, staff_quality=2.0,
        )
        # Same RNG seed means same log-normal draw, so d_high = d_normal / 2
        assert d_high == pytest.approx(d_normal / 2.0, rel=1e-10)

    def test_c2_multiplier_increases_duration(self, event_bus: EventBus) -> None:
        """Degraded C2 makes OODA loop slower."""
        rng1 = make_rng(200)
        rng2 = make_rng(200)
        engine1 = OODALoopEngine(event_bus, rng1)
        engine2 = OODALoopEngine(event_bus, rng2)
        d_normal = engine1.compute_phase_duration(
            EchelonLevel.COMPANY, OODAPhase.OBSERVE, c2_multiplier=1.0,
        )
        d_degraded = engine2.compute_phase_duration(
            EchelonLevel.COMPANY, OODAPhase.OBSERVE, c2_multiplier=1.5,
        )
        assert d_degraded == pytest.approx(d_normal * 1.5, rel=1e-10)

    def test_personality_mult(self, event_bus: EventBus) -> None:
        """Personality multiplier scales duration."""
        rng1 = make_rng(300)
        rng2 = make_rng(300)
        engine1 = OODALoopEngine(event_bus, rng1)
        engine2 = OODALoopEngine(event_bus, rng2)
        d_normal = engine1.compute_phase_duration(
            EchelonLevel.BRIGADE, OODAPhase.ACT, personality_mult=1.0,
        )
        d_cautious = engine2.compute_phase_duration(
            EchelonLevel.BRIGADE, OODAPhase.ACT, personality_mult=1.3,
        )
        assert d_cautious == pytest.approx(d_normal * 1.3, rel=1e-10)

    def test_platoon_faster_than_division(self, event_bus: EventBus) -> None:
        """Platoon-level OODA should be faster than division-level on average."""
        durations_plt: list[float] = []
        durations_div: list[float] = []
        for seed in range(100):
            rng1 = make_rng(seed)
            rng2 = make_rng(seed)
            e1 = OODALoopEngine(event_bus, rng1)
            e2 = OODALoopEngine(event_bus, rng2)
            durations_plt.append(
                e1.compute_phase_duration(EchelonLevel.PLATOON, OODAPhase.ORIENT),
            )
            durations_div.append(
                e2.compute_phase_duration(EchelonLevel.DIVISION, OODAPhase.ORIENT),
            )
        assert np.mean(durations_plt) < np.mean(durations_div)

    def test_lognormal_variation(self, event_bus: EventBus) -> None:
        """Run 100 times and check that results have spread (not all identical)."""
        durations: list[float] = []
        for seed in range(100):
            engine = OODALoopEngine(event_bus, make_rng(seed))
            durations.append(
                engine.compute_phase_duration(EchelonLevel.BATTALION, OODAPhase.DECIDE),
            )
        arr = np.array(durations)
        # Mean should be near base (600s) but with log-normal bias slightly above
        assert arr.mean() > 300  # well above zero
        assert arr.mean() < 2000  # not wildly off
        # Coefficient of variation should reflect sigma=0.3 spread
        cv = arr.std() / arr.mean()
        assert cv > 0.1  # meaningful spread
        assert cv < 1.0  # not insane spread


# ---------------------------------------------------------------------------
# start_phase
# ---------------------------------------------------------------------------


class TestStartPhase:
    """start_phase sets timer and publishes event."""

    def test_sets_timer(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = OODALoopEngine(event_bus, rng)
        engine.register_commander("bn_1", EchelonLevel.BATTALION)
        engine.start_phase("bn_1", OODAPhase.OBSERVE, ts=TS)
        # Timer should now be positive (started)
        state = engine.get_state()
        timer = state["commanders"]["bn_1"]["phase_timer"]
        assert timer > 0

    def test_publishes_ooda_phase_change_event(
        self, event_bus: EventBus, rng: np.random.Generator,
    ) -> None:
        captured = _capture_events(event_bus, OODAPhaseChangeEvent)
        engine = OODALoopEngine(event_bus, rng)
        engine.register_commander("co_1", EchelonLevel.COMPANY)
        engine.start_phase("co_1", OODAPhase.ORIENT, ts=TS)

        assert len(captured) == 1
        evt = captured[0]
        assert evt.unit_id == "co_1"
        assert evt.old_phase == int(OODAPhase.OBSERVE)  # was at OBSERVE
        assert evt.new_phase == int(OODAPhase.ORIENT)
        assert evt.cycle_number == 0
        assert evt.source == ModuleId.C2
        assert evt.timestamp == TS

    def test_start_phase_with_modifiers(
        self, event_bus: EventBus,
    ) -> None:
        """start_phase applies staff_quality, c2_multiplier, and personality_mult."""
        rng1 = make_rng(500)
        rng2 = make_rng(500)
        engine1 = OODALoopEngine(event_bus, rng1)
        engine2 = OODALoopEngine(event_bus, rng2)

        engine1.register_commander("bn_1", EchelonLevel.BATTALION)
        engine2.register_commander("bn_2", EchelonLevel.BATTALION)

        # Compute expected duration with known RNG
        expected = engine1.compute_phase_duration(
            EchelonLevel.BATTALION, OODAPhase.DECIDE,
            staff_quality=0.8, c2_multiplier=1.5,
        )

        # Now start phase with same params (rng2 has same seed state as rng1 before compute)
        engine2.start_phase(
            "bn_2", OODAPhase.DECIDE,
            staff_quality=0.8, c2_multiplier=1.5, ts=TS,
        )

        state = engine2.get_state()
        actual = state["commanders"]["bn_2"]["phase_timer"]
        assert actual == pytest.approx(expected, rel=1e-10)


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


class TestUpdate:
    """update decrements timers and returns completions."""

    def test_decrements_timer(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = OODALoopEngine(event_bus, rng)
        engine.register_commander("bn_1", EchelonLevel.BATTALION)
        engine.start_phase("bn_1", OODAPhase.OBSERVE, ts=TS)

        initial_timer = engine.get_state()["commanders"]["bn_1"]["phase_timer"]
        engine.update(10.0)
        new_timer = engine.get_state()["commanders"]["bn_1"]["phase_timer"]
        assert new_timer == pytest.approx(initial_timer - 10.0)

    def test_returns_completed_phases(
        self, event_bus: EventBus, rng: np.random.Generator,
    ) -> None:
        engine = OODALoopEngine(event_bus, rng)
        engine.register_commander("plt_1", EchelonLevel.PLATOON)
        engine.start_phase("plt_1", OODAPhase.OBSERVE, ts=TS)

        # Use a very large dt to ensure completion
        result = engine.update(100_000.0)
        assert len(result) == 1
        assert result[0] == ("plt_1", OODAPhase.OBSERVE)

    def test_does_not_auto_advance(
        self, event_bus: EventBus, rng: np.random.Generator,
    ) -> None:
        engine = OODALoopEngine(event_bus, rng)
        engine.register_commander("bn_1", EchelonLevel.BATTALION)
        engine.start_phase("bn_1", OODAPhase.OBSERVE, ts=TS)

        # Complete the phase
        engine.update(100_000.0)

        # Phase should still be OBSERVE (not auto-advanced to ORIENT)
        assert engine.get_phase("bn_1") == OODAPhase.OBSERVE

    def test_multiple_commanders(
        self, event_bus: EventBus, rng: np.random.Generator,
    ) -> None:
        engine = OODALoopEngine(event_bus, rng)
        engine.register_commander("plt_1", EchelonLevel.PLATOON)
        engine.register_commander("div_1", EchelonLevel.DIVISION)

        engine.start_phase("plt_1", OODAPhase.OBSERVE, ts=TS)
        engine.start_phase("div_1", OODAPhase.OBSERVE, ts=TS)

        # Platoon OBSERVE base=30s. Division OBSERVE base=1800s.
        # With a moderate dt, platoon should complete but not division.
        # Use a dt that is certainly > max platoon duration but < min division duration.
        # Platoon base=30, even with log-normal sigma=0.3, 500s should cover it.
        # Division base=1800, even with favorable variation, 500s won't complete it.
        result = engine.update(500.0)
        unit_ids = [uid for uid, _ in result]
        assert "plt_1" in unit_ids
        # Division very unlikely to complete in 500s (base=1800)
        # but not guaranteed -- check state instead
        div_timer = engine.get_state()["commanders"]["div_1"]["phase_timer"]
        if "div_1" not in unit_ids:
            assert div_timer > 0

    def test_dt_larger_than_remaining(
        self, event_bus: EventBus, rng: np.random.Generator,
    ) -> None:
        """Overshooting dt still marks phase as completed."""
        engine = OODALoopEngine(event_bus, rng)
        engine.register_commander("plt_1", EchelonLevel.PLATOON)
        engine.start_phase("plt_1", OODAPhase.ACT, ts=TS)
        result = engine.update(1_000_000.0)
        assert ("plt_1", OODAPhase.ACT) in result

    def test_update_skips_unstarted(
        self, event_bus: EventBus, rng: np.random.Generator,
    ) -> None:
        """Commanders with timer=-1 (not started) are skipped."""
        engine = OODALoopEngine(event_bus, rng)
        engine.register_commander("bn_1", EchelonLevel.BATTALION)
        result = engine.update(1000.0)
        assert result == []


# ---------------------------------------------------------------------------
# get_phase / get_cycle_count
# ---------------------------------------------------------------------------


class TestQueries:
    """Query methods for phase and cycle count."""

    def test_get_phase_initial(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = OODALoopEngine(event_bus, rng)
        engine.register_commander("bn_1", EchelonLevel.BATTALION)
        assert engine.get_phase("bn_1") == OODAPhase.OBSERVE

    def test_get_cycle_count_starts_at_zero(
        self, event_bus: EventBus, rng: np.random.Generator,
    ) -> None:
        engine = OODALoopEngine(event_bus, rng)
        engine.register_commander("bn_1", EchelonLevel.BATTALION)
        assert engine.get_cycle_count("bn_1") == 0


# ---------------------------------------------------------------------------
# reset_loop
# ---------------------------------------------------------------------------


class TestResetLoop:
    """reset_loop resets to OBSERVE and increments cycle."""

    def test_resets_to_observe(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = OODALoopEngine(event_bus, rng)
        engine.register_commander("bn_1", EchelonLevel.BATTALION)
        engine.start_phase("bn_1", OODAPhase.DECIDE, ts=TS)
        engine.reset_loop("bn_1", "surprise_contact", ts=TS)
        assert engine.get_phase("bn_1") == OODAPhase.OBSERVE

    def test_increments_cycle_count(
        self, event_bus: EventBus, rng: np.random.Generator,
    ) -> None:
        engine = OODALoopEngine(event_bus, rng)
        engine.register_commander("bn_1", EchelonLevel.BATTALION)
        assert engine.get_cycle_count("bn_1") == 0
        engine.reset_loop("bn_1", "c2_disruption", ts=TS)
        assert engine.get_cycle_count("bn_1") == 1
        engine.reset_loop("bn_1", "frago_received", ts=TS)
        assert engine.get_cycle_count("bn_1") == 2

    def test_publishes_ooda_loop_reset_event(
        self, event_bus: EventBus, rng: np.random.Generator,
    ) -> None:
        captured = _capture_events(event_bus, OODALoopResetEvent)
        engine = OODALoopEngine(event_bus, rng)
        engine.register_commander("co_1", EchelonLevel.COMPANY)
        engine.reset_loop("co_1", "surprise_contact", ts=TS)

        assert len(captured) == 1
        evt = captured[0]
        assert evt.unit_id == "co_1"
        assert evt.cause == "surprise_contact"
        assert evt.cycle_number == 1
        assert evt.source == ModuleId.C2
        assert evt.timestamp == TS

    def test_reset_clears_timer(
        self, event_bus: EventBus, rng: np.random.Generator,
    ) -> None:
        engine = OODALoopEngine(event_bus, rng)
        engine.register_commander("bn_1", EchelonLevel.BATTALION)
        engine.start_phase("bn_1", OODAPhase.ORIENT, ts=TS)
        engine.reset_loop("bn_1", "c2_disruption", ts=TS)
        # Timer should be -1 (not started)
        state = engine.get_state()
        assert state["commanders"]["bn_1"]["phase_timer"] == -1.0


# ---------------------------------------------------------------------------
# advance_phase
# ---------------------------------------------------------------------------


class TestAdvancePhase:
    """advance_phase cycles through all 4 phases."""

    def test_observe_to_orient(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = OODALoopEngine(event_bus, rng)
        engine.register_commander("bn_1", EchelonLevel.BATTALION)
        result = engine.advance_phase("bn_1")
        assert result == OODAPhase.ORIENT

    def test_full_cycle(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = OODALoopEngine(event_bus, rng)
        engine.register_commander("bn_1", EchelonLevel.BATTALION)
        assert engine.advance_phase("bn_1") == OODAPhase.ORIENT
        assert engine.advance_phase("bn_1") == OODAPhase.DECIDE
        assert engine.advance_phase("bn_1") == OODAPhase.ACT
        assert engine.advance_phase("bn_1") == OODAPhase.OBSERVE  # wraps

    def test_wraps_from_act_to_observe(
        self, event_bus: EventBus, rng: np.random.Generator,
    ) -> None:
        engine = OODALoopEngine(event_bus, rng)
        engine.register_commander("bn_1", EchelonLevel.BATTALION)
        # Advance to ACT
        engine.advance_phase("bn_1")  # ORIENT
        engine.advance_phase("bn_1")  # DECIDE
        engine.advance_phase("bn_1")  # ACT
        # Now wrap
        result = engine.advance_phase("bn_1")
        assert result == OODAPhase.OBSERVE

    def test_increments_cycle_on_wrap(
        self, event_bus: EventBus, rng: np.random.Generator,
    ) -> None:
        engine = OODALoopEngine(event_bus, rng)
        engine.register_commander("bn_1", EchelonLevel.BATTALION)
        assert engine.get_cycle_count("bn_1") == 0
        # Advance through full cycle
        engine.advance_phase("bn_1")  # ORIENT
        engine.advance_phase("bn_1")  # DECIDE
        engine.advance_phase("bn_1")  # ACT
        assert engine.get_cycle_count("bn_1") == 0
        engine.advance_phase("bn_1")  # OBSERVE (wrap)
        assert engine.get_cycle_count("bn_1") == 1

    def test_advance_resets_timer(
        self, event_bus: EventBus, rng: np.random.Generator,
    ) -> None:
        """advance_phase sets timer to -1 so start_phase can be called."""
        engine = OODALoopEngine(event_bus, rng)
        engine.register_commander("bn_1", EchelonLevel.BATTALION)
        engine.start_phase("bn_1", OODAPhase.OBSERVE, ts=TS)
        engine.advance_phase("bn_1")
        state = engine.get_state()
        assert state["commanders"]["bn_1"]["phase_timer"] == -1.0


# ---------------------------------------------------------------------------
# Echelon mapping
# ---------------------------------------------------------------------------


class TestEchelonMapping:
    """Echelon levels map to correct config keys."""

    def test_squad_uses_platoon_durations(self, event_bus: EventBus) -> None:
        rng1 = make_rng(77)
        rng2 = make_rng(77)
        e1 = OODALoopEngine(event_bus, rng1)
        e2 = OODALoopEngine(event_bus, rng2)
        d_squad = e1.compute_phase_duration(EchelonLevel.SQUAD, OODAPhase.OBSERVE)
        d_platoon = e2.compute_phase_duration(EchelonLevel.PLATOON, OODAPhase.OBSERVE)
        # Same seed, same config key -> identical
        assert d_squad == pytest.approx(d_platoon, rel=1e-10)

    def test_regiment_uses_battalion_durations(self, event_bus: EventBus) -> None:
        rng1 = make_rng(88)
        rng2 = make_rng(88)
        e1 = OODALoopEngine(event_bus, rng1)
        e2 = OODALoopEngine(event_bus, rng2)
        d_regiment = e1.compute_phase_duration(EchelonLevel.REGIMENT, OODAPhase.DECIDE)
        d_battalion = e2.compute_phase_duration(EchelonLevel.BATTALION, OODAPhase.DECIDE)
        assert d_regiment == pytest.approx(d_battalion, rel=1e-10)

    def test_individual_uses_platoon(self, event_bus: EventBus) -> None:
        rng1 = make_rng(99)
        rng2 = make_rng(99)
        e1 = OODALoopEngine(event_bus, rng1)
        e2 = OODALoopEngine(event_bus, rng2)
        d_indiv = e1.compute_phase_duration(EchelonLevel.INDIVIDUAL, OODAPhase.ACT)
        d_platoon = e2.compute_phase_duration(EchelonLevel.PLATOON, OODAPhase.ACT)
        assert d_indiv == pytest.approx(d_platoon, rel=1e-10)


# ---------------------------------------------------------------------------
# State protocol (checkpoint/restore)
# ---------------------------------------------------------------------------


class TestStateProtocol:
    """get_state / set_state round-trip."""

    def test_round_trip(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = OODALoopEngine(event_bus, rng)
        engine.register_commander("bn_1", EchelonLevel.BATTALION)
        engine.register_commander("co_1", EchelonLevel.COMPANY)
        engine.start_phase("bn_1", OODAPhase.ORIENT, ts=TS)
        engine.update(50.0)
        engine.advance_phase("co_1")

        state = engine.get_state()

        # Create a new engine and restore
        engine2 = OODALoopEngine(event_bus, make_rng(999))
        engine2.set_state(state)

        assert engine2.get_phase("bn_1") == OODAPhase.ORIENT
        assert engine2.get_phase("co_1") == OODAPhase.ORIENT
        assert engine2.get_cycle_count("bn_1") == 0
        assert engine2.get_cycle_count("co_1") == 0

        # Timers should match
        s1 = engine.get_state()["commanders"]["bn_1"]
        s2 = engine2.get_state()["commanders"]["bn_1"]
        assert s2["phase_timer"] == pytest.approx(s1["phase_timer"])
        assert s2["phase_duration"] == pytest.approx(s1["phase_duration"])
        assert s2["echelon_level"] == s1["echelon_level"]

    def test_state_serializable(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """State dict contains only basic Python types (JSON-safe)."""
        engine = OODALoopEngine(event_bus, rng)
        engine.register_commander("bn_1", EchelonLevel.BATTALION)
        engine.start_phase("bn_1", OODAPhase.DECIDE, ts=TS)
        state = engine.get_state()

        # All values should be basic types
        for uid, sd in state["commanders"].items():
            assert isinstance(uid, str)
            assert isinstance(sd["phase"], int)
            assert isinstance(sd["phase_timer"], float)
            assert isinstance(sd["phase_duration"], float)
            assert isinstance(sd["cycle_count"], int)
            assert isinstance(sd["echelon_level"], int)


# ---------------------------------------------------------------------------
# Deterministic replay
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Same seed produces same durations."""

    def test_same_seed_same_durations(self, event_bus: EventBus) -> None:
        rng1 = make_rng(42)
        rng2 = make_rng(42)
        e1 = OODALoopEngine(event_bus, rng1)
        e2 = OODALoopEngine(event_bus, rng2)

        durations1 = [
            e1.compute_phase_duration(EchelonLevel.BATTALION, phase)
            for phase in OODAPhase
        ]
        durations2 = [
            e2.compute_phase_duration(EchelonLevel.BATTALION, phase)
            for phase in OODAPhase
        ]
        assert durations1 == durations2

    def test_different_seed_different_durations(self, event_bus: EventBus) -> None:
        rng1 = make_rng(42)
        rng2 = make_rng(99)
        e1 = OODALoopEngine(event_bus, rng1)
        e2 = OODALoopEngine(event_bus, rng2)

        d1 = e1.compute_phase_duration(EchelonLevel.BATTALION, OODAPhase.ORIENT)
        d2 = e2.compute_phase_duration(EchelonLevel.BATTALION, OODAPhase.ORIENT)
        assert d1 != d2


# ---------------------------------------------------------------------------
# C2 degradation
# ---------------------------------------------------------------------------


class TestC2Degradation:
    """C2 multipliers scale OODA duration."""

    def test_degraded_multiplier(self, event_bus: EventBus) -> None:
        """C2 degraded multiplier makes phases take 1.5x longer."""
        cfg = OODAConfig()
        rng1 = make_rng(111)
        rng2 = make_rng(111)
        e1 = OODALoopEngine(event_bus, rng1, config=cfg)
        e2 = OODALoopEngine(event_bus, rng2, config=cfg)

        d_normal = e1.compute_phase_duration(
            EchelonLevel.BATTALION, OODAPhase.ORIENT, c2_multiplier=1.0,
        )
        d_degraded = e2.compute_phase_duration(
            EchelonLevel.BATTALION, OODAPhase.ORIENT, c2_multiplier=cfg.degraded_mult,
        )
        assert d_degraded == pytest.approx(d_normal * cfg.degraded_mult, rel=1e-10)

    def test_disrupted_multiplier(self, event_bus: EventBus) -> None:
        """C2 disrupted multiplier makes phases take 3x longer."""
        cfg = OODAConfig()
        rng1 = make_rng(222)
        rng2 = make_rng(222)
        e1 = OODALoopEngine(event_bus, rng1, config=cfg)
        e2 = OODALoopEngine(event_bus, rng2, config=cfg)

        d_normal = e1.compute_phase_duration(
            EchelonLevel.COMPANY, OODAPhase.DECIDE, c2_multiplier=1.0,
        )
        d_disrupted = e2.compute_phase_duration(
            EchelonLevel.COMPANY, OODAPhase.DECIDE, c2_multiplier=cfg.disrupted_mult,
        )
        assert d_disrupted == pytest.approx(d_normal * cfg.disrupted_mult, rel=1e-10)


# ---------------------------------------------------------------------------
# Full cycle timing integration
# ---------------------------------------------------------------------------


class TestFullCycle:
    """End-to-end OODA loop cycle with timer completion."""

    def test_full_ooda_cycle(self, event_bus: EventBus) -> None:
        """Walk a commander through a complete OBSERVE-ORIENT-DECIDE-ACT cycle."""
        phase_events = _capture_events(event_bus, OODAPhaseChangeEvent)
        rng = make_rng(42)
        engine = OODALoopEngine(event_bus, rng)
        engine.register_commander("bn_1", EchelonLevel.BATTALION)

        total_time = 0.0
        for expected_phase in OODAPhase:
            engine.start_phase("bn_1", expected_phase, ts=TS)
            assert engine.get_phase("bn_1") == expected_phase

            # Get the timer and step past it
            timer = engine.get_state()["commanders"]["bn_1"]["phase_timer"]
            total_time += timer
            result = engine.update(timer + 1.0)
            assert ("bn_1", expected_phase) in result

            # Advance to next (orchestrator's job)
            if expected_phase != OODAPhase.ACT:
                new_phase = engine.advance_phase("bn_1")
                assert new_phase == OODAPhase(int(expected_phase) + 1)

        # Should have completed all 4 phases
        assert len(phase_events) == 4
        assert total_time > 0
        # Cycle count should still be 0 (advance from ACT would make it 1,
        # but we stopped after ACT completed)
        assert engine.get_cycle_count("bn_1") == 0

    def test_multiple_cycles(self, event_bus: EventBus) -> None:
        """Run two full OODA cycles and verify cycle count increments."""
        rng = make_rng(42)
        engine = OODALoopEngine(event_bus, rng)
        engine.register_commander("co_1", EchelonLevel.COMPANY)

        for cycle in range(2):
            for phase in OODAPhase:
                engine.start_phase("co_1", phase, ts=TS)
                timer = engine.get_state()["commanders"]["co_1"]["phase_timer"]
                engine.update(timer + 1.0)
                engine.advance_phase("co_1")

        assert engine.get_cycle_count("co_1") == 2
