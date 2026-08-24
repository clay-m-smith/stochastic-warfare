"""Tests for the stateless Markov-chain morale selector."""

from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from stochastic_warfare.morale.state import (
    MoraleConfig,
    MoraleState,
    MoraleStateMachine,
)


def _machine(
    seed: int = 42,
    config: MoraleConfig | None = None,
) -> MoraleStateMachine:
    return MoraleStateMachine(np.random.default_rng(seed), config)


class TestMoraleStateEnum:
    def test_ordered_values(self) -> None:
        assert list(MoraleState) == [
            MoraleState.STEADY,
            MoraleState.SHAKEN,
            MoraleState.BROKEN,
            MoraleState.ROUTED,
            MoraleState.SURRENDERED,
        ]
        assert [int(state) for state in MoraleState] == list(range(5))


class TestMoraleConfig:
    def test_defaults_and_custom_values(self) -> None:
        defaults = MoraleConfig()
        assert defaults.base_degrade_rate > 0.0
        assert defaults.base_recover_rate > 0.0
        custom = MoraleConfig(casualty_weight=5.0, suppression_weight=3.0)
        assert custom.casualty_weight == 5.0
        assert custom.suppression_weight == 3.0

    def test_config_is_frozen_and_rejects_unknown_fields(self) -> None:
        config = MoraleConfig()
        with pytest.raises(ValidationError, match="frozen_instance"):
            config.use_continuous_time = True
        with pytest.raises(ValidationError, match="extra_forbidden"):
            MoraleConfig.model_validate({"unknown_morale_field": 1.0})


class TestTransitionMatrix:
    @pytest.mark.parametrize(
        "inputs",
        [
            (0.0, 0.0, False, 0.5, 1.0),
            (0.3, 0.5, True, 0.7, 0.8),
            (1.0, 1.0, False, 0.0, 0.0),
        ],
    )
    def test_rows_are_stochastic(
        self,
        inputs: tuple[float, float, bool, float, float],
    ) -> None:
        matrix = _machine().compute_transition_matrix(*inputs)
        assert matrix.shape == (5, 5)
        assert np.all(matrix >= 0.0)
        assert np.allclose(matrix.sum(axis=1), 1.0)

    def test_surrendered_is_absorbing(self) -> None:
        matrix = _machine().compute_transition_matrix(
            0.5,
            0.5,
            False,
            0.5,
            1.0,
        )
        assert matrix[4].tolist() == pytest.approx([0.0, 0.0, 0.0, 0.0, 1.0])

    def test_inputs_preserve_existing_semantics(self) -> None:
        machine = _machine()
        baseline = machine.compute_transition_matrix(0.0, 0.0, False, 0.5, 1.0)
        casualties = machine.compute_transition_matrix(0.8, 0.0, False, 0.5, 1.0)
        suppression = machine.compute_transition_matrix(0.0, 0.8, False, 0.5, 1.0)
        outnumbered = machine.compute_transition_matrix(0.0, 0.0, False, 0.5, 0.3)
        leader = machine.compute_transition_matrix(0.0, 0.0, True, 0.5, 1.0)
        cohesion = machine.compute_transition_matrix(0.0, 0.0, False, 0.9, 1.0)
        assert casualties[0, 1] > baseline[0, 1]
        assert suppression[0, 1] > baseline[0, 1]
        assert outnumbered[0, 1] > baseline[0, 1]
        assert leader[1, 0] > baseline[1, 0]
        assert cohesion[1, 0] > baseline[1, 0]


class TestSelectTransition:
    def test_consumes_one_draw_and_returns_typed_state(self) -> None:
        machine = _machine()
        expected_rng = np.random.default_rng(42)
        expected_rng.random()
        result = machine.select_transition(
            MoraleState.STEADY,
            0.0,
            0.0,
            True,
            0.8,
            2.0,
            dt=1.0,
        )
        assert isinstance(result, MoraleState)
        assert machine.rng.bit_generator.state == expected_rng.bit_generator.state

    def test_surrendered_remains_surrendered(self) -> None:
        assert _machine().select_transition(
            MoraleState.SURRENDERED,
            1.0,
            1.0,
            False,
            0.0,
            0.1,
            dt=1.0,
        ) is MoraleState.SURRENDERED

    def test_same_seed_is_deterministic(self) -> None:
        first = _machine(seed=123)
        second = _machine(seed=123)
        args = (MoraleState.SHAKEN, 0.3, 0.4, False, 0.5, 0.8)
        assert [first.select_transition(*args, dt=1.0) for _ in range(20)] == [
            second.select_transition(*args, dt=1.0)
            for _ in range(20)
        ]

    def test_rejects_invalid_dt_before_draw(self) -> None:
        machine = _machine()
        before = copy.deepcopy(machine.rng.bit_generator.state)
        with pytest.raises(ValueError, match="positive"):
            machine.select_transition(
                MoraleState.STEADY,
                0.0,
                0.0,
                True,
                1.0,
                1.0,
                dt=0.0,
            )
        assert machine.rng.bit_generator.state == before

    @pytest.mark.test_evidence("structural_only")
    def test_owns_no_semantic_or_checkpoint_state(self) -> None:
        machine = _machine()
        assert not hasattr(machine, "_unit_states")
        assert not hasattr(machine, "get_state")
        assert not hasattr(machine, "set_state")


class TestApplyMoraleEffects:
    def test_effects_decrease_monotonically(self) -> None:
        for key in ("accuracy_mult", "speed_mult"):
            values = [
                MoraleStateMachine.apply_morale_effects(state)[key]
                for state in MoraleState
            ]
            assert values == sorted(values, reverse=True)

    def test_expected_endpoints(self) -> None:
        steady = MoraleStateMachine.apply_morale_effects(MoraleState.STEADY)
        surrendered = MoraleStateMachine.apply_morale_effects(
            MoraleState.SURRENDERED,
        )
        assert steady == {
            "accuracy_mult": 1.0,
            "speed_mult": 1.0,
            "initiative_mult": 1.0,
        }
        assert surrendered == {
            "accuracy_mult": 0.0,
            "speed_mult": 0.0,
            "initiative_mult": 0.0,
        }


def test_morale_visualization_uses_current_stateless_selector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.visualize import combat_viz

    monkeypatch.setattr(combat_viz, "OUT_DIR", tmp_path)

    combat_viz.plot_morale_transitions(show=False)

    output = tmp_path / "morale_transitions.png"
    assert output.is_file()
    assert output.stat().st_size > 0
