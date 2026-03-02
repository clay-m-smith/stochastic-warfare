"""Mission command engine — subordinate initiative assessment.

Phase 5 scope: "Should I take independent action?" ONLY.
Phase 8 scope: "What should I do?" (AI/planning).

Models Auftragstaktik (mission-type orders) vs Befehlstaktik (detailed
orders) and the factors that drive a unit to take independent action:
comms availability, experience, C2 flexibility (SOF bonus), and
commander's intent.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.c2.events import InitiativeActionEvent

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class C2Style(enum.IntEnum):
    """Command and control doctrinal style."""

    AUFTRAGSTAKTIK = 0   # Mission-type: high subordinate initiative
    BEFEHLSTAKTIK = 1    # Detailed: low subordinate initiative
    HYBRID = 2           # Mix — most modern Western armies


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CommanderIntent:
    """Commander's intent — the "why" behind the order."""

    purpose: str       # "Destroy enemy reserve to prevent counterattack"
    key_tasks: tuple[str, ...]  # ("seize hill 305", "block route 1")
    end_state: str     # "Enemy unable to reinforce; friendly control of OBJ ALPHA"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class MissionCommandConfig:
    """Tuning parameters for initiative assessment."""

    def __init__(
        self,
        auftragstaktik_base_initiative: float = 0.7,
        befehlstaktik_base_initiative: float = 0.15,
        hybrid_base_initiative: float = 0.4,
        comms_loss_boost: float = 0.3,
        experience_weight: float = 0.2,
        c2_flexibility_weight: float = 0.15,
    ) -> None:
        self.auftragstaktik_base_initiative = auftragstaktik_base_initiative
        self.befehlstaktik_base_initiative = befehlstaktik_base_initiative
        self.hybrid_base_initiative = hybrid_base_initiative
        self.comms_loss_boost = comms_loss_boost
        self.experience_weight = experience_weight
        self.c2_flexibility_weight = c2_flexibility_weight


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class MissionCommandEngine:
    """Assesses whether a unit should take independent action.

    Parameters
    ----------
    event_bus : EventBus
        Publishes ``InitiativeActionEvent``.
    rng : numpy.random.Generator
        Deterministic PRNG.
    style : C2Style
        Doctrinal C2 style (side-wide).
    config : MissionCommandConfig | None
        Tuning parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        style: C2Style = C2Style.HYBRID,
        config: MissionCommandConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._style = style
        self._config = config or MissionCommandConfig()
        self._intents: dict[str, CommanderIntent] = {}

    # -- Intent management --------------------------------------------------

    def set_intent(self, unit_id: str, intent: CommanderIntent) -> None:
        """Set commander's intent for a unit."""
        self._intents[unit_id] = intent

    def get_intent(self, unit_id: str) -> CommanderIntent | None:
        """Return commander's intent, or None if not set."""
        return self._intents.get(unit_id)

    # -- Initiative assessment ----------------------------------------------

    def get_autonomy_level(
        self,
        unit_id: str,
        experience: float = 0.5,
        c2_flexibility: float = 0.5,
        comms_available: bool = True,
    ) -> float:
        """Return autonomy level (0.0–1.0) for a unit.

        Higher = more likely to take independent action.
        """
        cfg = self._config

        # Base from C2 style
        if self._style == C2Style.AUFTRAGSTAKTIK:
            base = cfg.auftragstaktik_base_initiative
        elif self._style == C2Style.BEFEHLSTAKTIK:
            base = cfg.befehlstaktik_base_initiative
        else:
            base = cfg.hybrid_base_initiative

        # Modifiers
        autonomy = base
        autonomy += cfg.experience_weight * max(0.0, min(1.0, experience))
        autonomy += cfg.c2_flexibility_weight * max(0.0, min(1.0, c2_flexibility))

        if not comms_available:
            autonomy += cfg.comms_loss_boost

        return max(0.0, min(1.0, autonomy))

    def should_take_initiative(
        self,
        unit_id: str,
        situation_urgency: float = 0.5,
        experience: float = 0.5,
        c2_flexibility: float = 0.5,
        comms_available: bool = True,
    ) -> bool:
        """Determine if a unit should take independent action.

        Uses a stochastic threshold: ``P(act) = autonomy × urgency``.
        """
        autonomy = self.get_autonomy_level(
            unit_id, experience, c2_flexibility, comms_available,
        )
        threshold = autonomy * max(0.0, min(1.0, situation_urgency))
        return bool(self._rng.random() < threshold)

    def publish_initiative(
        self,
        unit_id: str,
        action_type: str,
        justification: str,
        timestamp: datetime,
    ) -> None:
        """Publish an initiative action event."""
        self._event_bus.publish(InitiativeActionEvent(
            timestamp=timestamp, source=ModuleId.C2,
            unit_id=unit_id,
            action_type=action_type,
            justification=justification,
        ))

    # -- State protocol -----------------------------------------------------

    def get_state(self) -> dict:
        return {
            "style": int(self._style),
            "intents": {
                uid: {
                    "purpose": intent.purpose,
                    "key_tasks": list(intent.key_tasks),
                    "end_state": intent.end_state,
                }
                for uid, intent in self._intents.items()
            },
        }

    def set_state(self, state: dict) -> None:
        self._style = C2Style(state["style"])
        self._intents.clear()
        for uid, id in state["intents"].items():
            self._intents[uid] = CommanderIntent(
                purpose=id["purpose"],
                key_tasks=tuple(id["key_tasks"]),
                end_state=id["end_state"],
            )
