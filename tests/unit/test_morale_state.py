"""Tests for morale/state.py — Markov-chain morale state machine."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.morale.events import MoraleStateChangeEvent
from stochastic_warfare.morale.state import (
    MoraleConfig,
    MoraleState,
    MoraleStateMachine,
    UnitMoraleState,
)


# ── helpers ──────────────────────────────────────────────────────────


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _machine(seed: int = 42, config: MoraleConfig | None = None) -> tuple[MoraleStateMachine, EventBus]:
    bus = EventBus()
    return MoraleStateMachine(bus, _rng(seed), config), bus


# ── MoraleState enum ─────────────────────────────────────────────────


class TestMoraleStateEnum:
    def test_values(self) -> None:
        assert MoraleState.STEADY == 0
        assert MoraleState.SHAKEN == 1
        assert MoraleState.BROKEN == 2
        assert MoraleState.ROUTED == 3
        assert MoraleState.SURRENDERED == 4

    def test_count(self) -> None:
        assert len(MoraleState) == 5

    def test_ordering(self) -> None:
        assert MoraleState.STEADY < MoraleState.SHAKEN < MoraleState.BROKEN
        assert MoraleState.BROKEN < MoraleState.ROUTED < MoraleState.SURRENDERED


# ── MoraleConfig ─────────────────────────────────────────────────────


class TestMoraleConfig:
    def test_defaults(self) -> None:
        cfg = MoraleConfig()
        assert cfg.base_degrade_rate > 0
        assert cfg.base_recover_rate > 0
        assert cfg.casualty_weight > 0
        assert cfg.suppression_weight > 0

    def test_custom_values(self) -> None:
        cfg = MoraleConfig(casualty_weight=5.0, suppression_weight=3.0)
        assert cfg.casualty_weight == 5.0
        assert cfg.suppression_weight == 3.0


# ── UnitMoraleState ──────────────────────────────────────────────────


class TestUnitMoraleState:
    def test_defaults(self) -> None:
        ums = UnitMoraleState()
        assert ums.current_state == MoraleState.STEADY
        assert ums.transition_cooldown_s == 0.0

    def test_get_set_state(self) -> None:
        ums = UnitMoraleState(
            current_state=MoraleState.BROKEN,
            transition_cooldown_s=15.0,
            last_transition_time=100.0,
        )
        state = ums.get_state()
        assert state["current_state"] == 2

        ums2 = UnitMoraleState()
        ums2.set_state(state)
        assert ums2.current_state == MoraleState.BROKEN
        assert ums2.transition_cooldown_s == 15.0
        assert ums2.last_transition_time == 100.0


# ── Transition matrix ────────────────────────────────────────────────


class TestTransitionMatrix:
    def test_shape(self) -> None:
        machine, _ = _machine()
        matrix = machine.compute_transition_matrix(0.0, 0.0, False, 0.5, 1.0)
        assert matrix.shape == (5, 5)

    def test_row_stochastic(self) -> None:
        machine, _ = _machine()
        matrix = machine.compute_transition_matrix(0.3, 0.5, True, 0.7, 0.8)
        for i in range(5):
            assert matrix[i].sum() == pytest.approx(1.0)

    def test_nonnegative(self) -> None:
        machine, _ = _machine()
        matrix = machine.compute_transition_matrix(0.5, 0.8, False, 0.1, 0.3)
        assert np.all(matrix >= 0.0)

    def test_surrendered_absorbing(self) -> None:
        machine, _ = _machine()
        matrix = machine.compute_transition_matrix(0.5, 0.5, False, 0.5, 1.0)
        assert matrix[4, 4] == pytest.approx(1.0)
        for j in range(4):
            assert matrix[4, j] == pytest.approx(0.0)

    def test_steady_no_upward(self) -> None:
        """STEADY cannot recover further — no upward transition."""
        machine, _ = _machine()
        matrix = machine.compute_transition_matrix(0.0, 0.0, True, 1.0, 2.0)
        # Row 0 should not have transitions to states < 0 (there are none)
        # and should not have transitions to negative indices
        assert matrix[0].sum() == pytest.approx(1.0)

    def test_high_casualties_increase_degrade(self) -> None:
        machine, _ = _machine()
        m_low = machine.compute_transition_matrix(0.0, 0.0, False, 0.5, 1.0)
        m_high = machine.compute_transition_matrix(0.8, 0.0, False, 0.5, 1.0)
        # High casualties should increase probability of degrading from STEADY
        assert m_high[0, 1] > m_low[0, 1]

    def test_leadership_increases_recovery(self) -> None:
        machine, _ = _machine()
        m_no_leader = machine.compute_transition_matrix(0.0, 0.0, False, 0.5, 1.0)
        m_leader = machine.compute_transition_matrix(0.0, 0.0, True, 0.5, 1.0)
        # Leader should increase recovery probability from SHAKEN -> STEADY
        assert m_leader[1, 0] > m_no_leader[1, 0]

    def test_suppression_increases_degrade(self) -> None:
        machine, _ = _machine()
        m_low = machine.compute_transition_matrix(0.0, 0.0, False, 0.5, 1.0)
        m_high = machine.compute_transition_matrix(0.0, 0.8, False, 0.5, 1.0)
        assert m_high[0, 1] > m_low[0, 1]

    def test_outnumbered_increases_degrade(self) -> None:
        machine, _ = _machine()
        m_even = machine.compute_transition_matrix(0.0, 0.0, False, 0.5, 1.0)
        m_outnumbered = machine.compute_transition_matrix(0.0, 0.0, False, 0.5, 0.3)
        assert m_outnumbered[0, 1] > m_even[0, 1]

    def test_high_cohesion_helps_recovery(self) -> None:
        machine, _ = _machine()
        m_low_coh = machine.compute_transition_matrix(0.0, 0.0, False, 0.1, 1.0)
        m_high_coh = machine.compute_transition_matrix(0.0, 0.0, False, 0.9, 1.0)
        # SHAKEN->STEADY recovery should be higher with high cohesion
        assert m_high_coh[1, 0] > m_low_coh[1, 0]

    def test_extreme_conditions_still_valid(self) -> None:
        machine, _ = _machine()
        matrix = machine.compute_transition_matrix(1.0, 1.0, False, 0.0, 0.0)
        for i in range(5):
            assert matrix[i].sum() == pytest.approx(1.0)
        assert np.all(matrix >= 0.0)


# ── check_transition ─────────────────────────────────────────────────


class TestCheckTransition:
    def test_returns_morale_state(self) -> None:
        machine, _ = _machine()
        result = machine.check_transition("u1", 0.0, 0.0, True, 0.8, 2.0)
        assert isinstance(result, MoraleState)

    def test_surrendered_stays_surrendered(self) -> None:
        machine, _ = _machine()
        # Force unit into SURRENDERED state
        ums = machine._get_unit_state("u1")
        ums.current_state = MoraleState.SURRENDERED
        result = machine.check_transition("u1", 0.0, 0.0, True, 1.0, 5.0)
        assert result == MoraleState.SURRENDERED

    def test_deterministic_with_same_seed(self) -> None:
        m1, _ = _machine(seed=123)
        m2, _ = _machine(seed=123)
        results1 = [m1.check_transition("u1", 0.3, 0.4, False, 0.5, 0.8) for _ in range(20)]
        results2 = [m2.check_transition("u1", 0.3, 0.4, False, 0.5, 0.8) for _ in range(20)]
        assert results1 == results2

    def test_event_published_on_change(self) -> None:
        """Run multiple checks until a state change occurs and verify event."""
        received: list[MoraleStateChangeEvent] = []
        # Use high casualties to force a transition
        cfg = MoraleConfig(base_degrade_rate=0.8, casualty_weight=5.0)
        machine, bus = _machine(seed=42, config=cfg)
        bus.subscribe(MoraleStateChangeEvent, lambda e: received.append(e))

        # Many attempts with extreme conditions
        for _ in range(50):
            result = machine.check_transition("u1", 0.9, 0.9, False, 0.0, 0.1)
            if result != MoraleState.STEADY:
                break

        assert len(received) >= 1
        evt = received[0]
        assert evt.unit_id == "u1"
        assert evt.old_state == int(MoraleState.STEADY)

    def test_no_event_when_no_change(self) -> None:
        """When state doesn't change, no event should be published."""
        received: list[MoraleStateChangeEvent] = []
        # Very low degrade rate, high recovery — STEADY should stay STEADY
        cfg = MoraleConfig(base_degrade_rate=0.0, casualty_weight=0.0, suppression_weight=0.0)
        machine, bus = _machine(seed=42, config=cfg)
        bus.subscribe(MoraleStateChangeEvent, lambda e: received.append(e))
        machine.check_transition("u1", 0.0, 0.0, True, 1.0, 5.0)
        assert len(received) == 0

    def test_multiple_units_independent(self) -> None:
        machine, _ = _machine(seed=42)
        r1 = machine.check_transition("u1", 0.5, 0.5, False, 0.3, 0.5)
        r2 = machine.check_transition("u2", 0.0, 0.0, True, 0.9, 3.0)
        # Both should be valid states; they are independently tracked
        assert isinstance(r1, MoraleState)
        assert isinstance(r2, MoraleState)


# ── apply_morale_effects ─────────────────────────────────────────────


class TestApplyMoraleEffects:
    def test_steady_full_effectiveness(self) -> None:
        effects = MoraleStateMachine.apply_morale_effects(MoraleState.STEADY)
        assert effects["accuracy_mult"] == 1.0
        assert effects["speed_mult"] == 1.0
        assert effects["initiative_mult"] == 1.0

    def test_shaken_reduced(self) -> None:
        effects = MoraleStateMachine.apply_morale_effects(MoraleState.SHAKEN)
        assert effects["accuracy_mult"] == pytest.approx(0.7)
        assert effects["speed_mult"] == pytest.approx(0.7)

    def test_broken_severely_reduced(self) -> None:
        effects = MoraleStateMachine.apply_morale_effects(MoraleState.BROKEN)
        assert effects["accuracy_mult"] == pytest.approx(0.3)
        assert effects["speed_mult"] == pytest.approx(0.3)

    def test_routed_minimal(self) -> None:
        effects = MoraleStateMachine.apply_morale_effects(MoraleState.ROUTED)
        assert effects["accuracy_mult"] == pytest.approx(0.1)
        assert effects["speed_mult"] == pytest.approx(0.1)
        assert effects["initiative_mult"] == pytest.approx(0.0)

    def test_surrendered_zero(self) -> None:
        effects = MoraleStateMachine.apply_morale_effects(MoraleState.SURRENDERED)
        assert effects["accuracy_mult"] == 0.0
        assert effects["speed_mult"] == 0.0
        assert effects["initiative_mult"] == 0.0

    def test_monotonic_decrease(self) -> None:
        """Effectiveness should decrease monotonically from STEADY to SURRENDERED."""
        for key in ("accuracy_mult", "speed_mult"):
            values = [
                MoraleStateMachine.apply_morale_effects(MoraleState(i))[key]
                for i in range(5)
            ]
            for i in range(len(values) - 1):
                assert values[i] >= values[i + 1]

    def test_returns_new_dict(self) -> None:
        """Should return a new dict each time, not a reference."""
        e1 = MoraleStateMachine.apply_morale_effects(MoraleState.STEADY)
        e2 = MoraleStateMachine.apply_morale_effects(MoraleState.STEADY)
        assert e1 is not e2


# ── State round-trip ─────────────────────────────────────────────────


class TestMoraleStateMachineState:
    def test_roundtrip(self) -> None:
        machine, bus = _machine(seed=42)
        machine.check_transition("u1", 0.5, 0.5, False, 0.3, 0.5)
        machine.check_transition("u2", 0.2, 0.1, True, 0.8, 1.5)
        state = machine.get_state()

        machine2, bus2 = _machine(seed=0)
        machine2.set_state(state)
        state2 = machine2.get_state()

        assert state["unit_states"].keys() == state2["unit_states"].keys()
        for uid in state["unit_states"]:
            assert state["unit_states"][uid]["current_state"] == state2["unit_states"][uid]["current_state"]

    def test_determinism_after_restore(self) -> None:
        machine, bus = _machine(seed=42)
        machine.check_transition("u1", 0.3, 0.3, False, 0.5, 1.0)
        state = machine.get_state()

        machine2, bus2 = _machine(seed=0)
        machine2.set_state(state)

        # Both machines should produce same results going forward
        r1 = machine.check_transition("u1", 0.4, 0.4, False, 0.4, 0.8)
        r2 = machine2.check_transition("u1", 0.4, 0.4, False, 0.4, 0.8)
        assert r1 == r2
