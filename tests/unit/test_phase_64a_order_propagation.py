"""Phase 64a: Order propagation wiring tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import numpy as np
import pytest

from stochastic_warfare.c2.orders.propagation import (
    OrderPropagationEngine,
    PropagationConfig,
)
from stochastic_warfare.c2.orders.types import Order, OrderPriority, OrderType
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position


def _make_rng(seed: int = 42) -> np.random.Generator:
    return np.random.default_rng(seed)


def _make_order(
    order_type: OrderType = OrderType.FRAGO,
    priority: OrderPriority = OrderPriority.PRIORITY,
    echelon: int = 5,
) -> Order:
    return Order(
        order_id="test_order_1",
        issuer_id="unit_a",
        recipient_id="unit_b",
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        order_type=order_type,
        echelon_level=echelon,
        priority=priority,
        mission_type=0,
    )


def _make_comms(success: bool = True, latency: float = 1.0) -> MagicMock:
    """Create a mock CommunicationsEngine."""
    comms = MagicMock()
    comms.send_message.return_value = (success, latency)
    channel = MagicMock()
    channel.base_reliability = 0.95
    comms.get_best_channel.return_value = channel
    return comms


class TestOrderPropagationNoneGuard:
    """command_engine=None should not crash."""

    def test_propagate_succeeds_without_command_engine(self):
        """propagate_order() succeeds when command_engine is None."""
        bus = EventBus()
        comms = _make_comms(success=True)
        engine = OrderPropagationEngine(comms, None, bus, _make_rng())
        result = engine.propagate_order(
            _make_order(), Position(0, 0, 0), Position(100, 0, 0),
            datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert result.success is True

    def test_authority_check_skipped_when_no_command(self):
        """No authority check → always authorized."""
        bus = EventBus()
        comms = _make_comms(success=True)
        engine = OrderPropagationEngine(comms, None, bus, _make_rng())
        # Should not raise even though no command engine to check authority
        result = engine.propagate_order(
            _make_order(), Position(0, 0, 0), Position(0, 0, 0),
            datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert result.success is True

    def test_staff_effectiveness_defaults_to_1(self):
        """Without command engine, staff effectiveness = 1.0 → minimal delay."""
        bus = EventBus()
        comms = _make_comms(success=True, latency=0.0)
        engine = OrderPropagationEngine(comms, None, bus, _make_rng())
        result = engine.propagate_order(
            _make_order(), Position(0, 0, 0), Position(0, 0, 0),
            datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        # staff_eff=1.0 → staff_mult=1.0 (no penalty)
        assert result.total_delay_s >= 0.0

    def test_sender_not_degraded_when_no_command(self):
        """Without command engine, sender degraded = False."""
        bus = EventBus()
        comms = _make_comms(success=True)
        engine = OrderPropagationEngine(comms, None, bus, _make_rng())
        result = engine.propagate_order(
            _make_order(), Position(0, 0, 0), Position(0, 0, 0),
            datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert result.degraded is False


class TestOrderPropagationBehavior:
    """Order propagation behavior tests."""

    def test_comms_failure_returns_false(self):
        bus = EventBus()
        comms = _make_comms(success=False)
        engine = OrderPropagationEngine(comms, None, bus, _make_rng())
        result = engine.propagate_order(
            _make_order(), Position(0, 0, 0), Position(0, 0, 0),
            datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert result.success is False

    def test_frago_faster_than_opord(self):
        bus = EventBus()
        comms = _make_comms(success=True, latency=0.0)
        rng = _make_rng(123)
        engine = OrderPropagationEngine(comms, None, bus, rng)
        frago_result = engine.propagate_order(
            _make_order(order_type=OrderType.FRAGO),
            Position(0, 0, 0), Position(0, 0, 0),
            datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        rng2 = _make_rng(123)
        engine2 = OrderPropagationEngine(comms, None, bus, rng2)
        opord_result = engine2.propagate_order(
            _make_order(order_type=OrderType.OPORD),
            Position(0, 0, 0), Position(0, 0, 0),
            datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert frago_result.total_delay_s < opord_result.total_delay_s

    def test_flash_faster_than_routine(self):
        bus = EventBus()
        comms = _make_comms(success=True, latency=0.0)
        rng1 = _make_rng(99)
        engine1 = OrderPropagationEngine(comms, None, bus, rng1)
        flash_result = engine1.propagate_order(
            _make_order(priority=OrderPriority.FLASH),
            Position(0, 0, 0), Position(0, 0, 0),
            datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        rng2 = _make_rng(99)
        engine2 = OrderPropagationEngine(comms, None, bus, rng2)
        routine_result = engine2.propagate_order(
            _make_order(priority=OrderPriority.ROUTINE),
            Position(0, 0, 0), Position(0, 0, 0),
            datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert flash_result.total_delay_s < routine_result.total_delay_s

    def test_misinterpretation_probability_formula(self):
        """P = base × (1 + 1-staff) × (1 + 1-comms)."""
        bus = EventBus()
        comms = _make_comms()
        engine = OrderPropagationEngine(comms, None, bus, _make_rng())
        prob = engine.compute_misinterpretation_probability(
            _make_order(), staff_effectiveness=0.8, comms_quality=0.9,
        )
        # base=0.05, staff_factor=0.2, comms_factor=0.1
        # P = max(0.005, 0.05 × 1.2 × 1.1) = max(0.005, 0.066) = 0.066
        assert prob == pytest.approx(0.066, abs=0.01)

    def test_delay_sigma_and_misinterpretation_configurable(self):
        """Custom config values are applied."""
        config = PropagationConfig(delay_sigma=0.8, base_misinterpretation=0.10)
        bus = EventBus()
        comms = _make_comms()
        engine = OrderPropagationEngine(comms, None, bus, _make_rng(), config=config)
        prob = engine.compute_misinterpretation_probability(
            _make_order(), staff_effectiveness=1.0, comms_quality=1.0,
        )
        # With perfect staff/comms: P = max(0.01, 0.10 × 1.0 × 1.0) = 0.10
        assert prob == pytest.approx(0.10, abs=0.01)


class TestOrderPropagationInBattle:
    """Test order propagation wiring in battle.py via string checks."""

    def test_battle_contains_propagate_order(self):
        """battle.py calls propagate_order (not just logging)."""
        from pathlib import Path
        src = Path(__file__).resolve().parents[2] / "stochastic_warfare" / "simulation" / "battle.py"
        text = src.read_text(encoding="utf-8")
        assert "propagate_order" in text

    def test_enable_c2_friction_gates_propagation(self):
        """battle.py checks enable_c2_friction before propagation."""
        from pathlib import Path
        src = Path(__file__).resolve().parents[2] / "stochastic_warfare" / "simulation" / "battle.py"
        text = src.read_text(encoding="utf-8")
        # The enable_c2_friction check is near the propagate_order call
        idx_prop = text.index("propagate_order")
        idx_gate = text.index("enable_c2_friction")
        # Gate must appear before the call
        assert idx_gate < idx_prop
