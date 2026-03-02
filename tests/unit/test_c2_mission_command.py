"""Tests for c2/mission_command.py — subordinate initiative."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.c2.events import InitiativeActionEvent
from stochastic_warfare.c2.mission_command import (
    C2Style,
    CommanderIntent,
    MissionCommandConfig,
    MissionCommandEngine,
)

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _make_engine(
    seed: int = 42,
    style: C2Style = C2Style.HYBRID,
    config: MissionCommandConfig | None = None,
) -> tuple[MissionCommandEngine, EventBus]:
    bus = EventBus()
    rng = RNGManager(seed).get_stream(ModuleId.C2)
    return MissionCommandEngine(bus, rng, style, config), bus


class TestC2StyleEnum:
    """C2 doctrinal style."""

    def test_values(self) -> None:
        assert C2Style.AUFTRAGSTAKTIK == 0
        assert C2Style.BEFEHLSTAKTIK == 1
        assert C2Style.HYBRID == 2
        assert len(C2Style) == 3


class TestCommanderIntent:
    """CommanderIntent frozen dataclass."""

    def test_create_intent(self) -> None:
        intent = CommanderIntent(
            purpose="Destroy enemy reserve",
            key_tasks=("seize hill 305", "block route 1"),
            end_state="Enemy unable to reinforce",
        )
        assert intent.purpose == "Destroy enemy reserve"
        assert len(intent.key_tasks) == 2

    def test_intent_is_frozen(self) -> None:
        intent = CommanderIntent("a", ("b",), "c")
        with pytest.raises(AttributeError):
            intent.purpose = "x"  # type: ignore[misc]


class TestAutonomyLevel:
    """Autonomy level calculation."""

    def test_auftragstaktik_high_initiative(self) -> None:
        eng, bus = _make_engine(style=C2Style.AUFTRAGSTAKTIK)
        level = eng.get_autonomy_level("plt1")
        assert level > 0.6

    def test_befehlstaktik_low_initiative(self) -> None:
        eng, bus = _make_engine(style=C2Style.BEFEHLSTAKTIK)
        level = eng.get_autonomy_level("plt1")
        assert level < 0.5

    def test_hybrid_between(self) -> None:
        eng_a, _ = _make_engine(style=C2Style.AUFTRAGSTAKTIK)
        eng_b, _ = _make_engine(style=C2Style.BEFEHLSTAKTIK)
        eng_h, _ = _make_engine(style=C2Style.HYBRID)
        level_a = eng_a.get_autonomy_level("plt1")
        level_b = eng_b.get_autonomy_level("plt1")
        level_h = eng_h.get_autonomy_level("plt1")
        assert level_b < level_h < level_a

    def test_comms_loss_boosts_initiative(self) -> None:
        eng, bus = _make_engine()
        with_comms = eng.get_autonomy_level("plt1", comms_available=True)
        without_comms = eng.get_autonomy_level("plt1", comms_available=False)
        assert without_comms > with_comms

    def test_experience_increases_initiative(self) -> None:
        eng, bus = _make_engine()
        low_exp = eng.get_autonomy_level("plt1", experience=0.1)
        high_exp = eng.get_autonomy_level("plt1", experience=0.9)
        assert high_exp > low_exp

    def test_c2_flexibility_bonus(self) -> None:
        eng, bus = _make_engine()
        low_flex = eng.get_autonomy_level("plt1", c2_flexibility=0.0)
        high_flex = eng.get_autonomy_level("plt1", c2_flexibility=1.0)
        assert high_flex > low_flex

    def test_autonomy_capped_at_1(self) -> None:
        eng, bus = _make_engine(style=C2Style.AUFTRAGSTAKTIK)
        level = eng.get_autonomy_level(
            "plt1", experience=1.0, c2_flexibility=1.0, comms_available=False,
        )
        assert level <= 1.0


class TestShouldTakeInitiative:
    """Stochastic initiative decision."""

    def test_high_urgency_and_autonomy_likely(self) -> None:
        eng, bus = _make_engine(seed=42, style=C2Style.AUFTRAGSTAKTIK)
        # Run many trials — expect mostly True
        results = [
            eng.should_take_initiative(
                "plt1", situation_urgency=0.9, experience=0.9,
                c2_flexibility=0.9, comms_available=False,
            )
            for _ in range(50)
        ]
        assert sum(results) > 25

    def test_low_urgency_befehlstaktik_unlikely(self) -> None:
        eng, bus = _make_engine(seed=42, style=C2Style.BEFEHLSTAKTIK)
        results = [
            eng.should_take_initiative(
                "plt1", situation_urgency=0.1, experience=0.1,
            )
            for _ in range(50)
        ]
        assert sum(results) < 10


class TestInitiativeEvent:
    """InitiativeActionEvent publication."""

    def test_publish_initiative(self) -> None:
        eng, bus = _make_engine()
        events: list[InitiativeActionEvent] = []
        bus.subscribe(InitiativeActionEvent, events.append)
        eng.publish_initiative("plt1", "engage", "self_defense", _TS)
        assert len(events) == 1
        assert events[0].unit_id == "plt1"
        assert events[0].action_type == "engage"
        assert events[0].justification == "self_defense"


class TestIntentManagement:
    """Commander's intent storage."""

    def test_set_and_get_intent(self) -> None:
        eng, bus = _make_engine()
        intent = CommanderIntent("destroy", ("seize",), "end_state")
        eng.set_intent("bn1", intent)
        assert eng.get_intent("bn1") == intent

    def test_no_intent_returns_none(self) -> None:
        eng, bus = _make_engine()
        assert eng.get_intent("unknown") is None


class TestMissionCommandState:
    """State protocol."""

    def test_state_round_trip(self) -> None:
        eng, bus = _make_engine(style=C2Style.AUFTRAGSTAKTIK)
        eng.set_intent("bn1", CommanderIntent("a", ("b", "c"), "d"))
        state = eng.get_state()
        eng2, bus2 = _make_engine()
        eng2.set_state(state)
        assert eng2.get_state() == state
        assert eng2._style == C2Style.AUFTRAGSTAKTIK


class TestDeterministicReplay:
    """Deterministic replay."""

    def test_deterministic_initiative(self) -> None:
        def run(seed: int) -> list[bool]:
            eng, bus = _make_engine(seed=seed)
            return [
                eng.should_take_initiative("plt1", 0.5, 0.5, 0.5, True)
                for _ in range(20)
            ]
        assert run(99) == run(99)
