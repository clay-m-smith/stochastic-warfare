"""Order propagation engine — the heart of C2 friction.

Each echelon hop introduces:
- A planning/processing delay: ``base_time(echelon) + lognormal(μ, σ)``
- A probability of misinterpretation: ``P = base × (1 - staff_eff) × (1 - comms_quality)``
- Possible total failure if communications are unavailable

Multi-hop propagation accumulates delay and compounds misinterpretation risk.
FRAGO is faster than OPORD. FLASH priority reduces delay.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.c2.command import CommandEngine, CommandStatus
from stochastic_warfare.c2.communications import CommunicationsEngine
from stochastic_warfare.c2.events import (
    OrderIssuedEvent,
    OrderMisunderstoodEvent,
    OrderReceivedEvent,
)
from stochastic_warfare.c2.orders.types import (
    Order,
    OrderPriority,
    OrderType,
)
from stochastic_warfare.entities.organization.echelons import EchelonLevel

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Planning time lookup (base seconds per echelon)
# ---------------------------------------------------------------------------

_BASE_PLANNING_TIMES: dict[int, float] = {
    int(EchelonLevel.INDIVIDUAL): 0.5,
    int(EchelonLevel.FIRE_TEAM): 5.0,
    int(EchelonLevel.SQUAD): 60.0,
    int(EchelonLevel.SECTION): 300.0,
    int(EchelonLevel.PLATOON): 900.0,
    int(EchelonLevel.COMPANY): 3600.0,
    int(EchelonLevel.BATTALION): 7200.0,
    int(EchelonLevel.REGIMENT): 14400.0,
    int(EchelonLevel.BRIGADE): 43200.0,
    int(EchelonLevel.DIVISION): 86400.0,
    int(EchelonLevel.CORPS): 172800.0,
    int(EchelonLevel.ARMY): 345600.0,
    int(EchelonLevel.ARMY_GROUP): 432000.0,
    int(EchelonLevel.THEATER): 604800.0,
}


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class PropagationResult:
    """Result of an order propagation attempt."""

    success: bool
    total_delay_s: float
    was_misinterpreted: bool
    misinterpretation_type: str  # "" if none
    comms_quality: float  # 0.0–1.0, quality of the channel used
    degraded: bool  # True if sender C2 was degraded


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class PropagationConfig:
    """Tuning parameters for order propagation."""

    def __init__(
        self,
        delay_sigma: float = 0.4,  # Log-normal σ for delay variation
        base_misinterpretation: float = 0.05,  # 5% base misinterpretation
        frago_delay_mult: float = 0.33,  # FRAGO is 1/3 the delay of OPORD
        warno_delay_mult: float = 0.1,  # WARNO is very fast
        flash_delay_mult: float = 0.25,  # FLASH priority cuts delay to 25%
        immediate_delay_mult: float = 0.5,
        priority_delay_mult: float = 0.75,
    ) -> None:
        self.delay_sigma = delay_sigma
        self.base_misinterpretation = base_misinterpretation
        self.frago_delay_mult = frago_delay_mult
        self.warno_delay_mult = warno_delay_mult
        self.flash_delay_mult = flash_delay_mult
        self.immediate_delay_mult = immediate_delay_mult
        self.priority_delay_mult = priority_delay_mult


# Misinterpretation types
_MISINTERPRETATION_TYPES = ("position", "timing", "objective", "unit_designation")


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class OrderPropagationEngine:
    """Propagates orders through the chain of command with stochastic friction.

    Parameters
    ----------
    comms_engine : CommunicationsEngine
        For checking/using communication channels.
    command_engine : CommandEngine
        For checking command authority and effectiveness.
    event_bus : EventBus
        Publishes propagation events.
    rng : numpy.random.Generator
        Deterministic PRNG.
    config : PropagationConfig | None
        Tuning parameters.
    """

    def __init__(
        self,
        comms_engine: CommunicationsEngine,
        command_engine: CommandEngine,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: PropagationConfig | None = None,
    ) -> None:
        self._comms = comms_engine
        self._command = command_engine
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or PropagationConfig()

    def propagate_order(
        self,
        order: Order,
        sender_pos: Position,
        recipient_pos: Position,
        timestamp: datetime,
    ) -> PropagationResult:
        """Attempt to propagate an order from issuer to recipient.

        Returns a ``PropagationResult`` with delay, misinterpretation, and
        success status.
        """
        # Check if sender can issue the order (skip if no command engine)
        if self._command is not None:
            if not self._command.can_issue_order(order.issuer_id, order.recipient_id):
                logger.warning(
                    "Order %s: %s has no authority over %s",
                    order.order_id, order.issuer_id, order.recipient_id,
                )
                return PropagationResult(
                    success=False, total_delay_s=0.0,
                    was_misinterpreted=False, misinterpretation_type="",
                    comms_quality=0.0, degraded=False,
                )

        # Check comms availability
        comms_success, comms_latency = self._comms.send_message(
            order.issuer_id, order.recipient_id,
            sender_pos, recipient_pos,
            message_size_bits=2000,  # Typical short order
            timestamp=timestamp,
        )

        if not comms_success:
            return PropagationResult(
                success=False, total_delay_s=0.0,
                was_misinterpreted=False, misinterpretation_type="",
                comms_quality=0.0, degraded=False,
            )

        # Compute delay
        staff_eff = self._command.get_effectiveness(order.recipient_id) if self._command is not None else 1.0
        delay = self.compute_delay(order.echelon_level, staff_eff, order)

        # Check C2 degradation of sender
        sender_degraded = False
        if self._command is not None:
            sender_degraded = (
                self._command.get_status(order.issuer_id) != CommandStatus.FULLY_OPERATIONAL
            )

        # Compute comms quality (best channel reliability proxy)
        channel = self._comms.get_best_channel(
            order.issuer_id, order.recipient_id,
            sender_pos, recipient_pos,
        )
        comms_quality = channel.base_reliability if channel else 0.5

        # Check for misinterpretation
        misinterpret_prob = self.compute_misinterpretation_probability(
            order, staff_eff, comms_quality,
        )
        was_misinterpreted = bool(self._rng.random() < misinterpret_prob)
        misinterpret_type = ""
        if was_misinterpreted:
            misinterpret_type = str(
                self._rng.choice(_MISINTERPRETATION_TYPES)
            )
            self._event_bus.publish(OrderMisunderstoodEvent(
                timestamp=timestamp, source=ModuleId.C2,
                order_id=order.order_id,
                recipient_id=order.recipient_id,
                misinterpretation_type=misinterpret_type,
            ))

        total_delay = delay + comms_latency

        # Publish events
        self._event_bus.publish(OrderIssuedEvent(
            timestamp=timestamp, source=ModuleId.C2,
            order_id=order.order_id,
            issuer_id=order.issuer_id,
            recipient_id=order.recipient_id,
            order_type=int(order.order_type),
            echelon_level=order.echelon_level,
        ))
        self._event_bus.publish(OrderReceivedEvent(
            timestamp=timestamp, source=ModuleId.C2,
            order_id=order.order_id,
            recipient_id=order.recipient_id,
            delay_s=total_delay,
            degraded=sender_degraded or was_misinterpreted,
        ))

        return PropagationResult(
            success=True,
            total_delay_s=total_delay,
            was_misinterpreted=was_misinterpreted,
            misinterpretation_type=misinterpret_type,
            comms_quality=comms_quality,
            degraded=sender_degraded,
        )

    def compute_delay(
        self,
        echelon_level: int,
        staff_effectiveness: float,
        order: Order | None = None,
    ) -> float:
        """Compute processing delay for an order at a given echelon.

        delay = base_time(echelon) × type_mult × priority_mult × (2 - staff_eff) + lognormal
        """
        base = _BASE_PLANNING_TIMES.get(echelon_level, 3600.0)

        # Order type multiplier
        type_mult = 1.0
        if order is not None:
            if order.order_type == OrderType.FRAGO:
                type_mult = self._config.frago_delay_mult
            elif order.order_type == OrderType.WARNO:
                type_mult = self._config.warno_delay_mult

        # Priority multiplier
        priority_mult = 1.0
        if order is not None:
            if order.priority == OrderPriority.FLASH:
                priority_mult = self._config.flash_delay_mult
            elif order.priority == OrderPriority.IMMEDIATE:
                priority_mult = self._config.immediate_delay_mult
            elif order.priority == OrderPriority.PRIORITY:
                priority_mult = self._config.priority_delay_mult

        # Staff effectiveness: poor staff → longer delay
        # staff_eff=1.0 → mult=1.0; staff_eff=0.0 → mult=2.0
        staff_mult = 2.0 - max(0.0, min(1.0, staff_effectiveness))

        deterministic = base * type_mult * priority_mult * staff_mult

        # Stochastic component (log-normal variation)
        if deterministic > 0:
            variation = float(self._rng.lognormal(0, self._config.delay_sigma))
            return deterministic * variation
        return 0.0

    def compute_misinterpretation_probability(
        self,
        order: Order,
        staff_effectiveness: float,
        comms_quality: float,
    ) -> float:
        """Compute probability that an order is misinterpreted.

        P = base × (1 - staff_eff) × (1 - comms_quality)
        """
        base = self._config.base_misinterpretation
        staff_factor = 1.0 - max(0.0, min(1.0, staff_effectiveness))
        comms_factor = 1.0 - max(0.0, min(1.0, comms_quality))
        # Minimum risk even with perfect conditions
        return max(base * 0.1, base * (1.0 + staff_factor) * (1.0 + comms_factor))

    # -- State protocol (stateless engine, but conforms to interface) -------

    def get_state(self) -> dict:
        """Serialize (stateless — returns config only)."""
        return {
            "delay_sigma": self._config.delay_sigma,
            "base_misinterpretation": self._config.base_misinterpretation,
        }

    def set_state(self, state: dict) -> None:
        """Restore (stateless — restores config only)."""
        self._config.delay_sigma = state["delay_sigma"]
        self._config.base_misinterpretation = state["base_misinterpretation"]
