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


# ---------------------------------------------------------------------------
# AI events (Phase 8)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OODAPhaseChangeEvent(Event):
    """Published when a commander transitions OODA phases."""

    unit_id: str
    old_phase: int  # OODAPhase value
    new_phase: int
    cycle_number: int


@dataclass(frozen=True)
class OODALoopResetEvent(Event):
    """Published when an OODA loop is interrupted and restarted."""

    unit_id: str
    cause: str  # "surprise_contact", "c2_disruption", "frago_received"
    cycle_number: int


@dataclass(frozen=True)
class SituationAssessedEvent(Event):
    """Published when a commander completes a situation assessment."""

    unit_id: str
    overall_rating: int  # AssessmentRating value
    confidence: float  # 0.0–1.0


@dataclass(frozen=True)
class DecisionMadeEvent(Event):
    """Published when a commander reaches a decision."""

    unit_id: str
    decision_type: str  # action name
    echelon_level: int
    confidence: float


@dataclass(frozen=True)
class PlanAdaptedEvent(Event):
    """Published when a plan is adapted due to changing conditions."""

    unit_id: str
    trigger: str  # AdaptationTrigger name
    action: str  # AdaptationAction name
    frago_order_id: str  # order ID of the resulting FRAGO, or ""


@dataclass(frozen=True)
class StratagemActivatedEvent(Event):
    """Published when a stratagem is employed."""

    unit_id: str
    stratagem_type: str  # StratagemType name
    target_area: str  # description of target area


# ---------------------------------------------------------------------------
# Planning events (Phase 8)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanningStartedEvent(Event):
    """Published when a planning process begins."""

    unit_id: str
    planning_method: str  # PlanningMethod name
    echelon_level: int
    estimated_duration_s: float


@dataclass(frozen=True)
class PlanningCompletedEvent(Event):
    """Published when planning finishes and a COA is selected."""

    unit_id: str
    planning_method: str
    selected_coa_id: str
    duration_s: float
    num_coas_evaluated: int


@dataclass(frozen=True)
class MissionAnalysisCompleteEvent(Event):
    """Published when mission analysis phase is complete."""

    unit_id: str
    num_specified_tasks: int
    num_implied_tasks: int
    num_constraints: int


@dataclass(frozen=True)
class COASelectedEvent(Event):
    """Published when a COA is selected for execution."""

    unit_id: str
    coa_id: str
    score: float
    risk_level: str  # "LOW", "MODERATE", "HIGH", "EXTREME"


@dataclass(frozen=True)
class PhaseTransitionEvent(Event):
    """Published when an operational plan transitions phases."""

    unit_id: str
    plan_id: str
    old_phase: str  # OperationalPhaseType name
    new_phase: str
    trigger: str  # condition that caused the transition


@dataclass(frozen=True)
class EstimateUpdatedEvent(Event):
    """Published when running estimates are updated."""

    unit_id: str
    estimate_type: str  # EstimateType name
    supportability: float  # 0.0–1.0
