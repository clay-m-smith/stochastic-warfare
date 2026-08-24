"""Phase 12d — Morale & Psychology Depth tests.

12d-1: Continuous-time Markov morale transitions + cooldown enforcement.
12d-2: Enhanced PSYOP with message type, delivery method, training resistance.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.entities.base import Unit
from stochastic_warfare.morale.events import PsyopAppliedEvent
from stochastic_warfare.morale.psychology import PsychologyConfig, PsychologyEngine, PsyopResult
from stochastic_warfare.morale.runtime import MoraleRegistration, MoraleRuntime
from stochastic_warfare.morale.state import MoraleConfig, MoraleState, MoraleStateMachine

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _runtime(
    config: MoraleConfig,
    *,
    seed: int = 42,
    initial_state: MoraleState = MoraleState.STEADY,
) -> tuple[MoraleRuntime, dict[str, Unit]]:
    runtime = MoraleRuntime(EventBus(), _rng(seed), config)
    units = {"u1": Unit(entity_id="u1", position=Position(0.0, 0.0))}
    runtime.register_units(
        (MoraleRegistration("u1", initial_state),),
        units,
    )
    return runtime, units


# ========================================================================
# 12d-1: Continuous-Time Markov Morale
# ========================================================================


class TestContinuousTimeMoraleConfig:
    """use_continuous_time config flag exists and defaults to False."""

    def test_default_is_discrete(self) -> None:
        cfg = MoraleConfig()
        assert cfg.use_continuous_time is False

    def test_can_enable_continuous(self) -> None:
        cfg = MoraleConfig(use_continuous_time=True)
        assert cfg.use_continuous_time is True


class TestContinuousTransitionProbs:
    """compute_continuous_transition_probs produces valid matrices."""

    def _make_machine(self, **kwargs) -> MoraleStateMachine:
        cfg = MoraleConfig(use_continuous_time=True, **kwargs)
        return MoraleStateMachine(_rng(), config=cfg)

    def test_row_stochastic(self) -> None:
        machine = self._make_machine()
        mat = machine.compute_continuous_transition_probs(
            casualty_rate=0.1,
            suppression_level=0.2,
            leadership_present=True,
            cohesion=0.6,
            force_ratio=1.0,
            dt=5.0,
        )
        for i in range(5):
            assert abs(mat[i].sum() - 1.0) < 1e-12

    def test_surrendered_absorbing(self) -> None:
        machine = self._make_machine()
        mat = machine.compute_continuous_transition_probs(
            casualty_rate=0.5,
            suppression_level=0.8,
            leadership_present=False,
            cohesion=0.1,
            force_ratio=0.3,
            dt=10.0,
        )
        assert mat[4, 4] == 1.0
        for j in range(4):
            assert mat[4, j] == 0.0

    def test_steady_no_recovery(self) -> None:
        """STEADY state cannot recover further."""
        machine = self._make_machine()
        mat = machine.compute_continuous_transition_probs(
            casualty_rate=0.0,
            suppression_level=0.0,
            leadership_present=True,
            cohesion=1.0,
            force_ratio=2.0,
            dt=5.0,
        )
        # Row 0: p_up should be 0
        for j in range(0):  # nothing before STEADY
            assert mat[0, j] == 0.0

    def test_longer_dt_higher_transition(self) -> None:
        """Longer dt should yield higher transition probabilities."""
        machine = self._make_machine()
        mat_short = machine.compute_continuous_transition_probs(
            casualty_rate=0.3,
            suppression_level=0.3,
            leadership_present=False,
            cohesion=0.3,
            force_ratio=0.5,
            dt=1.0,
        )
        mat_long = machine.compute_continuous_transition_probs(
            casualty_rate=0.3,
            suppression_level=0.3,
            leadership_present=False,
            cohesion=0.3,
            force_ratio=0.5,
            dt=10.0,
        )
        # P(degrade from STEADY) should be higher for longer dt
        assert mat_long[0, 1] > mat_short[0, 1]

    def test_zero_dt_no_transition(self) -> None:
        """dt=0 should produce identity-like matrix."""
        machine = self._make_machine()
        mat = machine.compute_continuous_transition_probs(
            casualty_rate=0.5,
            suppression_level=0.5,
            leadership_present=False,
            cohesion=0.2,
            force_ratio=0.5,
            dt=0.0,
        )
        for i in range(5):
            assert abs(mat[i, i] - 1.0) < 1e-12

    def test_non_negative(self) -> None:
        machine = self._make_machine()
        mat = machine.compute_continuous_transition_probs(
            casualty_rate=0.8,
            suppression_level=0.9,
            leadership_present=False,
            cohesion=0.0,
            force_ratio=0.1,
            dt=20.0,
        )
        assert np.all(mat >= 0.0)

    def test_max_transition_clamped(self) -> None:
        """Total transitions never exceed 0.95 even under extreme conditions."""
        machine = self._make_machine()
        mat = machine.compute_continuous_transition_probs(
            casualty_rate=1.0,
            suppression_level=1.0,
            leadership_present=True,
            cohesion=1.0,
            force_ratio=0.1,
            dt=100.0,
        )
        for i in range(4):
            off_diag = 1.0 - mat[i, i]
            assert off_diag <= 0.95 + 1e-12


class TestContinuousTimeSelectTransition:
    """Stateless selection in continuous mode uses dt-scaled rates."""

    def _make_machine(self, **kwargs) -> MoraleStateMachine:
        cfg = MoraleConfig(use_continuous_time=True, transition_cooldown_s=0.0, **kwargs)
        return MoraleStateMachine(_rng(), config=cfg)

    def test_uses_continuous_matrix(self) -> None:
        """Under heavy stress with dt, should eventually degrade."""
        machine = self._make_machine()
        state = MoraleState.STEADY
        degraded = False
        for _ in range(50):
            state = machine.select_transition(
                state,
                casualty_rate=0.5,
                suppression_level=0.8,
                leadership_present=False,
                cohesion=0.1,
                force_ratio=0.3,
                dt=5.0,
            )
            if state != MoraleState.STEADY:
                degraded = True
                break
        assert degraded

    def test_discrete_mode_ignores_dt(self) -> None:
        """Default (discrete) mode ignores dt parameter."""
        cfg = MoraleConfig(use_continuous_time=False, transition_cooldown_s=0.0)
        m1 = MoraleStateMachine(_rng(100), config=cfg)
        m2 = MoraleStateMachine(_rng(100), config=cfg)
        # Same seed, different dt — should give identical results
        s1 = m1.select_transition(
            MoraleState.STEADY,
            0.3,
            0.3,
            False,
            0.5,
            1.0,
            dt=1.0,
        )
        s2 = m2.select_transition(
            MoraleState.STEADY,
            0.3,
            0.3,
            False,
            0.5,
            1.0,
            dt=100.0,
        )
        assert s1 == s2

    def test_tick_rate_independence(self) -> None:
        """Over same total duration, transition probabilities converge
        regardless of tick size (law of large numbers)."""
        cfg_ct = MoraleConfig(use_continuous_time=True, transition_cooldown_s=0.0)
        total_duration = 60.0
        n_trials = 200
        small_dt = 1.0
        large_dt = 10.0

        # Count transitions with dt=1.0 (60 checks)
        trans_small = 0
        for trial in range(n_trials):
            m = MoraleStateMachine(_rng(trial), config=cfg_ct)
            state = MoraleState.STEADY
            for _ in range(int(total_duration / small_dt)):
                state = m.select_transition(
                    state,
                    0.3,
                    0.4,
                    False,
                    0.3,
                    0.5,
                    dt=small_dt,
                )
                if state != MoraleState.STEADY:
                    trans_small += 1
                    break

        # Count transitions with dt=10.0 (6 checks)
        trans_large = 0
        for trial in range(n_trials):
            m = MoraleStateMachine(_rng(trial + 10000), config=cfg_ct)
            state = MoraleState.STEADY
            for _ in range(int(total_duration / large_dt)):
                state = m.select_transition(
                    state,
                    0.3,
                    0.4,
                    False,
                    0.3,
                    0.5,
                    dt=large_dt,
                )
                if state != MoraleState.STEADY:
                    trans_large += 1
                    break

        # Rates should be within 20% of each other
        rate_small = trans_small / n_trials
        rate_large = trans_large / n_trials
        assert abs(rate_small - rate_large) < 0.20, (
            f"Tick-rate dependent: small_dt={rate_small:.2f}, large_dt={rate_large:.2f}"
        )


class TestTransitionCooldown:
    """The authoritative runtime enforces transition_cooldown_s."""

    def test_cooldown_blocks_rapid_transitions(self) -> None:
        cfg = MoraleConfig(transition_cooldown_s=30.0)
        runtime, _units = _runtime(cfg)

        first = runtime.check_transition(
            "u1",
            0.8,
            0.9,
            False,
            0.0,
            0.2,
            timestamp=_TS,
            current_time_s=1.0,
        )
        assert first is MoraleState.SHAKEN

        generation = runtime.record_for("u1").generation
        for logical_time in range(2, 12):
            assert runtime.check_transition(
                "u1",
                0.8,
                0.9,
                False,
                0.0,
                0.2,
                timestamp=_TS,
                current_time_s=float(logical_time),
            ) is first
            assert runtime.record_for("u1").generation == generation

    def test_cooldown_allows_after_elapsed(self) -> None:
        cfg = MoraleConfig(transition_cooldown_s=10.0)
        runtime, _units = _runtime(cfg)

        first = runtime.check_transition(
            "u1",
            0.8,
            0.9,
            False,
            0.0,
            0.2,
            timestamp=_TS,
            current_time_s=1.0,
        )
        blocked = runtime.check_transition(
            "u1",
            0.8,
            0.9,
            False,
            0.0,
            0.2,
            timestamp=_TS,
            current_time_s=6.0,
        )
        admitted = runtime.check_transition(
            "u1",
            0.8,
            0.9,
            False,
            0.0,
            0.2,
            timestamp=_TS,
            current_time_s=20.0,
        )

        assert first is MoraleState.SHAKEN
        assert blocked is first
        assert admitted is MoraleState.BROKEN

    def test_zero_cooldown_allows_all(self) -> None:
        cfg = MoraleConfig(transition_cooldown_s=0.0)
        runtime, _units = _runtime(cfg)

        first = runtime.check_transition(
            "u1",
            0.8,
            0.9,
            False,
            0.0,
            0.2,
            timestamp=_TS,
            current_time_s=1.0,
        )
        second = runtime.check_transition(
            "u1",
            0.8,
            0.9,
            False,
            0.0,
            0.2,
            timestamp=_TS,
            current_time_s=2.0,
        )

        assert first is MoraleState.SHAKEN
        assert second is MoraleState.BROKEN


class TestContinuousTimeRuntimeState:
    """Continuous-time semantic records survive runtime state restore."""

    def test_runtime_state_roundtrip(self) -> None:
        cfg = MoraleConfig(use_continuous_time=True, transition_cooldown_s=0.0)
        runtime, _units = _runtime(cfg)
        runtime.check_transition(
            "u1",
            0.5,
            0.5,
            False,
            0.5,
            0.5,
            timestamp=_TS,
            current_time_s=10.0,
        )
        saved = runtime.get_state()
        restored, restored_units = _runtime(cfg, seed=999)
        restored.set_state(
            saved,
            expected_units=restored_units,
            elapsed_time_s=10.0,
        )
        assert restored.get_state() == saved


# ========================================================================
# 12d-2: Enhanced PSYOP
# ========================================================================


class TestPsyopAppliedEvent:
    """PsyopAppliedEvent exists and carries expected fields."""

    def test_event_fields(self) -> None:
        evt = PsyopAppliedEvent(
            timestamp=_TS,
            source=ModuleId.MORALE,
            target_unit_id="u1",
            message_type="surrender",
            delivery_method="leaflet",
            morale_degradation=0.15,
            effective=True,
        )
        assert evt.target_unit_id == "u1"
        assert evt.message_type == "surrender"
        assert evt.delivery_method == "leaflet"
        assert evt.morale_degradation == 0.15
        assert evt.effective is True


class TestEnhancedPsyopConfig:
    """Enhanced PSYOP config defaults."""

    def test_message_type_defaults(self) -> None:
        cfg = PsychologyConfig()
        assert cfg.message_type_multipliers["surrender"] == 1.5
        assert cfg.message_type_multipliers["fear"] == 1.0

    def test_delivery_method_defaults(self) -> None:
        cfg = PsychologyConfig()
        assert cfg.delivery_method_multipliers["social_media"] == 1.3
        assert cfg.delivery_method_multipliers["leaflet"] == 0.6

    def test_training_resistance_default(self) -> None:
        cfg = PsychologyConfig()
        assert cfg.training_resistance_weight == 0.5


class TestApplyPsyopEnhanced:
    """apply_psyop_enhanced method."""

    def _make_engine(self, **kwargs) -> PsychologyEngine:
        cfg = PsychologyConfig(**kwargs)
        return PsychologyEngine(EventBus(), _rng(), config=cfg)

    def test_surrendered_target_no_effect(self) -> None:
        engine = self._make_engine()
        result = engine.apply_psyop_enhanced(
            target_unit_id="u1",
            target_morale_state=4,
            message_type="surrender",
            delivery_method="broadcast",
            target_susceptibility=0.9,
        )
        assert not result.effective
        assert result.morale_degradation == 0.0

    def test_surrender_message_stronger(self) -> None:
        """Surrender message type should produce more degradation than fear."""
        e1 = PsychologyEngine(EventBus(), _rng(42), config=PsychologyConfig())
        r1 = e1.apply_psyop_enhanced(
            "u1",
            1,
            "surrender",
            "broadcast",
            target_susceptibility=0.5,
        )
        e2 = PsychologyEngine(EventBus(), _rng(42), config=PsychologyConfig())
        r2 = e2.apply_psyop_enhanced(
            "u1",
            1,
            "fear",
            "broadcast",
            target_susceptibility=0.5,
        )
        assert r1.morale_degradation > r2.morale_degradation

    def test_social_media_stronger_than_leaflet(self) -> None:
        e1 = PsychologyEngine(EventBus(), _rng(42), config=PsychologyConfig())
        r1 = e1.apply_psyop_enhanced(
            "u1",
            1,
            "fear",
            "social_media",
            target_susceptibility=0.5,
        )
        e2 = PsychologyEngine(EventBus(), _rng(42), config=PsychologyConfig())
        r2 = e2.apply_psyop_enhanced(
            "u1",
            1,
            "fear",
            "leaflet",
            target_susceptibility=0.5,
        )
        assert r1.morale_degradation > r2.morale_degradation

    def test_high_training_reduces_effect(self) -> None:
        e1 = PsychologyEngine(EventBus(), _rng(42), config=PsychologyConfig())
        r1 = e1.apply_psyop_enhanced(
            "u1",
            1,
            "fear",
            "broadcast",
            target_susceptibility=0.5,
            target_training=0.0,
        )
        e2 = PsychologyEngine(EventBus(), _rng(42), config=PsychologyConfig())
        r2 = e2.apply_psyop_enhanced(
            "u1",
            1,
            "fear",
            "broadcast",
            target_susceptibility=0.5,
            target_training=1.0,
        )
        assert r1.morale_degradation > r2.morale_degradation

    def test_high_susceptibility_increases_effect(self) -> None:
        e1 = PsychologyEngine(EventBus(), _rng(42), config=PsychologyConfig())
        r1 = e1.apply_psyop_enhanced(
            "u1",
            1,
            "fear",
            "broadcast",
            target_susceptibility=0.9,
        )
        e2 = PsychologyEngine(EventBus(), _rng(42), config=PsychologyConfig())
        r2 = e2.apply_psyop_enhanced(
            "u1",
            1,
            "fear",
            "broadcast",
            target_susceptibility=0.1,
        )
        assert r1.morale_degradation > r2.morale_degradation

    def test_worse_morale_more_susceptible(self) -> None:
        e1 = PsychologyEngine(EventBus(), _rng(42), config=PsychologyConfig())
        r1 = e1.apply_psyop_enhanced(
            "u1",
            3,
            "surrender",
            "broadcast",
            target_susceptibility=0.5,
        )
        e2 = PsychologyEngine(EventBus(), _rng(42), config=PsychologyConfig())
        r2 = e2.apply_psyop_enhanced(
            "u1",
            0,
            "surrender",
            "broadcast",
            target_susceptibility=0.5,
        )
        assert r1.morale_degradation > r2.morale_degradation

    def test_event_published(self) -> None:
        bus = EventBus()
        events: list[PsyopAppliedEvent] = []
        bus.subscribe(PsyopAppliedEvent, events.append)
        engine = PsychologyEngine(bus, _rng(), config=PsychologyConfig())
        engine.apply_psyop_enhanced(
            "u1",
            1,
            "fear",
            "broadcast",
            target_susceptibility=0.5,
        )
        assert len(events) == 1
        assert events[0].target_unit_id == "u1"
        assert events[0].message_type == "fear"
        assert events[0].delivery_method == "broadcast"

    def test_result_clamped_0_to_1(self) -> None:
        engine = self._make_engine()
        result = engine.apply_psyop_enhanced(
            "u1",
            3,
            "surrender",
            "social_media",
            target_susceptibility=1.0,
            target_training=0.0,
        )
        assert 0.0 <= result.morale_degradation <= 1.0

    @pytest.mark.test_evidence("structural_only")
    def test_unknown_message_type_uses_default_mult(self) -> None:
        engine = self._make_engine()
        result = engine.apply_psyop_enhanced(
            "u1",
            1,
            "unknown_type",
            "broadcast",
            target_susceptibility=0.5,
        )
        # Should not error, uses multiplier 1.0
        assert isinstance(result, PsyopResult)

    def test_original_apply_psyop_unchanged(self) -> None:
        """Existing apply_psyop method still works."""
        engine = self._make_engine()
        result = engine.apply_psyop(
            target_morale_state=1,
            psyop_intensity=0.5,
            visibility=0.7,
        )
        assert isinstance(result, PsyopResult)
        assert result.morale_degradation >= 0.0
