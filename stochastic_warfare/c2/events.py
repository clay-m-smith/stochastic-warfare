"""C2-layer events published on the EventBus.

Covers command status changes, succession, communications, order lifecycle,
ROE violations, coordination measures, and initiative actions.
"""

from __future__ import annotations

from dataclasses import dataclass

from stochastic_warfare.core.events import Event


# ---------------------------------------------------------------------------
# Command authority events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CommandStatusChangeEvent(Event):
    """Published when a unit's command status transitions."""

    unit_id: str
    old_status: int  # CommandStatus value
    new_status: int
    cause: str  # "commander_kia", "hq_destroyed", "comms_loss", "recovery"


@dataclass(frozen=True)
class SuccessionEvent(Event):
    """Published when command succession is triggered."""

    unit_id: str
    old_commander_id: str
    new_commander_id: str
    succession_delay_s: float


# ---------------------------------------------------------------------------
# Communications events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CommsLostEvent(Event):
    """Published when communication is lost between two units."""

    from_unit_id: str
    to_unit_id: str
    channel_type: int  # CommType value
    cause: str  # "jamming", "range", "equipment_failure", "emcon"


@dataclass(frozen=True)
class CommsRestoredEvent(Event):
    """Published when communication is restored between two units."""

    from_unit_id: str
    to_unit_id: str
    channel_type: int  # CommType value


@dataclass(frozen=True)
class EmconStateChangeEvent(Event):
    """Published when a unit changes its emission control state."""

    unit_id: str
    old_state: int  # EmconState value
    new_state: int


# ---------------------------------------------------------------------------
# Order lifecycle events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OrderIssuedEvent(Event):
    """Published when an order is issued."""

    order_id: str
    issuer_id: str
    recipient_id: str
    order_type: int  # OrderType value
    echelon_level: int  # EchelonLevel value


@dataclass(frozen=True)
class OrderReceivedEvent(Event):
    """Published when a unit receives an order."""

    order_id: str
    recipient_id: str
    delay_s: float
    degraded: bool


@dataclass(frozen=True)
class OrderMisunderstoodEvent(Event):
    """Published when an order is misinterpreted during propagation."""

    order_id: str
    recipient_id: str
    misinterpretation_type: str  # "position", "timing", "objective"


@dataclass(frozen=True)
class OrderCompletedEvent(Event):
    """Published when an order reaches terminal status."""

    order_id: str
    unit_id: str
    success: bool
    deviation_level: float  # 0.0 = perfect, 1.0 = completely off


# ---------------------------------------------------------------------------
# ROE events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoeViolationEvent(Event):
    """Published when a unit violates rules of engagement."""

    unit_id: str
    violation_type: str  # "unauthorized_engagement", "excessive_force", etc.
    severity: str  # "minor", "major", "critical"


@dataclass(frozen=True)
class RoeChangeEvent(Event):
    """Published when ROE level changes for a set of units."""

    affected_unit_ids: tuple[str, ...]
    old_roe_level: int  # RoeLevel value
    new_roe_level: int


# ---------------------------------------------------------------------------
# Coordination events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CoordinationViolationEvent(Event):
    """Published when a unit violates a coordination measure."""

    unit_id: str
    measure_type: str  # "FSCL", "NFA", "CFL", etc.
    measure_id: str


# ---------------------------------------------------------------------------
# Mission command events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InitiativeActionEvent(Event):
    """Published when a unit takes independent action."""

    unit_id: str
    action_type: str  # "engage", "withdraw", "reposition", etc.
    justification: str  # "commander_intent", "self_defense", "opportunity"
