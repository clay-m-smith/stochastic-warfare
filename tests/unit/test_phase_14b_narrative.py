"""Tests for Phase 14b: narrative generation."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from stochastic_warfare.tools.narrative import (
    NarrativeEntry,
    NarrativeTick,
    _SIGNIFICANT_TYPES,
    format_event,
    format_narrative,
    generate_narrative,
    get_formatter,
    register_formatter,
    registered_event_types,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ev(tick: int, event_type: str, data: dict[str, Any] | None = None) -> SimpleNamespace:
    """Create a mock RecordedEvent."""
    return SimpleNamespace(
        tick=tick,
        event_type=event_type,
        data=data or {},
    )


# ---------------------------------------------------------------------------
# Formatter registry tests
# ---------------------------------------------------------------------------


class TestFormatterRegistry:
    """Formatter registration and lookup."""

    def test_engagement_formatter_registered(self) -> None:
        assert get_formatter("EngagementEvent") is not None

    def test_all_built_in_formatters(self) -> None:
        expected = {
            "EngagementEvent",
            "HitEvent",
            "DamageEvent",
            "SuppressionEvent",
            "FratricideEvent",
            "DetectionEvent",
            "ContactLostEvent",
            "MoraleStateChangeEvent",
            "RoutEvent",
            "SurrenderEvent",
            "OrderIssuedEvent",
            "OrderCompletedEvent",
            "DecisionMadeEvent",
            "VictoryDeclaredEvent",
            "OODAPhaseChangeEvent",
        }
        registered = set(registered_event_types())
        assert expected.issubset(registered)

    def test_unregistered_returns_none(self) -> None:
        assert get_formatter("NoSuchEvent") is None


# ---------------------------------------------------------------------------
# Individual formatter tests
# ---------------------------------------------------------------------------


class TestFormatters:
    """Each built-in formatter produces a string."""

    def test_engagement(self) -> None:
        text = format_event(
            "EngagementEvent",
            {"attacker_id": "blue_1", "target_id": "red_1", "weapon_id": "M256", "ammo_type": "APFSDS", "result": "hit"},
        )
        assert "blue_1" in text
        assert "red_1" in text
        assert "hit" in text

    def test_hit(self) -> None:
        text = format_event("HitEvent", {"target_id": "red_1", "damage_type": "KINETIC", "penetrated": True})
        assert "penetrating" in text

    def test_damage(self) -> None:
        text = format_event("DamageEvent", {"target_id": "red_1", "damage_amount": 0.6, "location": "turret"})
        assert "0.6" in text
        assert "turret" in text

    def test_suppression(self) -> None:
        text = format_event("SuppressionEvent", {"target_id": "red_2", "suppression_level": 2})
        assert "level 2" in text

    def test_fratricide(self) -> None:
        text = format_event("FratricideEvent", {"shooter_id": "blue_2", "victim_id": "blue_3", "cause": "misidentification"})
        assert "FRATRICIDE" in text

    def test_detection(self) -> None:
        text = format_event("DetectionEvent", {"observer_id": "blue_1", "target_id": "red_1", "sensor_type": "THERMAL", "detection_range": 3200})
        assert "3200" in text

    def test_contact_lost(self) -> None:
        text = format_event("ContactLostEvent", {"contact_id": "track_001", "side": "blue"})
        assert "loses contact" in text

    def test_morale(self) -> None:
        text = format_event("MoraleStateChangeEvent", {"unit_id": "red_1", "old_state": 0, "new_state": 1})
        assert "0" in text and "1" in text

    def test_rout(self) -> None:
        text = format_event("RoutEvent", {"unit_id": "red_2"})
        assert "ROUTS" in text

    def test_surrender(self) -> None:
        text = format_event("SurrenderEvent", {"unit_id": "red_3", "capturing_side": "blue"})
        assert "SURRENDERS" in text

    def test_order_issued(self) -> None:
        text = format_event("OrderIssuedEvent", {"issuer_id": "cmd_1", "recipient_id": "plt_1", "order_type": "ATTACK"})
        assert "ATTACK" in text

    def test_order_completed(self) -> None:
        text = format_event("OrderCompletedEvent", {"unit_id": "plt_1", "success": True})
        assert "completed" in text

    def test_decision(self) -> None:
        text = format_event("DecisionMadeEvent", {"unit_id": "cmd_1", "decision_type": "ATTACK", "confidence": 0.8})
        assert "ATTACK" in text
        assert "80%" in text

    def test_victory(self) -> None:
        text = format_event("VictoryDeclaredEvent", {"winning_side": "blue", "condition_type": "force_destroyed"})
        assert "VICTORY" in text

    def test_ooda(self) -> None:
        text = format_event("OODAPhaseChangeEvent", {"unit_id": "cmd_1", "new_phase": 2, "cycle_number": 3})
        assert "cycle 3" in text

    def test_generic_fallback(self) -> None:
        text = format_event("UnknownEvent", {"foo": "bar", "baz": 42})
        assert "UnknownEvent" in text
        assert "foo=bar" in text


# ---------------------------------------------------------------------------
# Narrative generation tests
# ---------------------------------------------------------------------------


class TestGenerateNarrative:
    """Narrative generation from event lists."""

    def test_basic_generation(self) -> None:
        events = [
            _ev(0, "DetectionEvent", {"observer_id": "b1", "target_id": "r1", "sensor_type": "VISUAL", "detection_range": 500}),
            _ev(1, "EngagementEvent", {"attacker_id": "b1", "target_id": "r1", "weapon_id": "M4", "result": "hit"}),
        ]
        ticks = generate_narrative(events)
        assert len(ticks) == 2
        assert ticks[0].tick == 0
        assert ticks[1].tick == 1
        assert len(ticks[0].entries) == 1

    def test_multiple_events_per_tick(self) -> None:
        events = [
            _ev(5, "EngagementEvent", {"attacker_id": "b1", "target_id": "r1", "weapon_id": "M4", "result": "hit"}),
            _ev(5, "HitEvent", {"target_id": "r1", "damage_type": "KINETIC", "penetrated": True}),
            _ev(5, "DamageEvent", {"target_id": "r1", "damage_amount": 0.5, "location": "hull"}),
        ]
        ticks = generate_narrative(events)
        assert len(ticks) == 1
        assert len(ticks[0].entries) == 3

    def test_event_type_filter(self) -> None:
        events = [
            _ev(0, "DetectionEvent", {"observer_id": "b1", "target_id": "r1", "sensor_type": "V", "detection_range": 100}),
            _ev(1, "EngagementEvent", {"attacker_id": "b1", "target_id": "r1", "weapon_id": "X", "result": "miss"}),
        ]
        ticks = generate_narrative(events, event_types=["EngagementEvent"])
        assert len(ticks) == 1
        assert ticks[0].entries[0].event_type == "EngagementEvent"

    def test_side_filter(self) -> None:
        events = [
            _ev(0, "EngagementEvent", {"attacker_id": "blue_1", "target_id": "red_1", "weapon_id": "X", "result": "hit"}),
            _ev(1, "EngagementEvent", {"attacker_id": "red_1", "target_id": "blue_1", "weapon_id": "Y", "result": "miss"}),
        ]
        ticks = generate_narrative(events, side_filter="blue")
        # Both events reference blue — blue_1 as attacker or target
        assert len(ticks) == 2

    def test_max_ticks_limit(self) -> None:
        events = [_ev(i, "DetectionEvent", {"observer_id": "b1", "target_id": "r1", "sensor_type": "V", "detection_range": 100}) for i in range(10)]
        ticks = generate_narrative(events, max_ticks=5)
        assert all(t.tick <= 5 for t in ticks)

    def test_empty_events(self) -> None:
        ticks = generate_narrative([])
        assert ticks == []


# ---------------------------------------------------------------------------
# Output formatting tests
# ---------------------------------------------------------------------------


class TestFormatNarrative:
    """format_narrative style modes."""

    def _sample_ticks(self) -> list[NarrativeTick]:
        return [
            NarrativeTick(
                tick=0,
                entries=[
                    NarrativeEntry(event_type="DetectionEvent", text="Observer detects target"),
                ],
            ),
            NarrativeTick(
                tick=1,
                entries=[
                    NarrativeEntry(event_type="EngagementEvent", text="Unit attacks"),
                    NarrativeEntry(event_type="DamageEvent", text="Target damaged"),
                ],
            ),
        ]

    def test_full_style(self) -> None:
        text = format_narrative(self._sample_ticks(), style="full")
        assert "--- Tick 0 ---" in text
        assert "--- Tick 1 ---" in text
        assert "Observer detects" in text

    def test_summary_style_filters(self) -> None:
        text = format_narrative(self._sample_ticks(), style="summary")
        # DetectionEvent is NOT in _SIGNIFICANT_TYPES
        assert "Observer detects" not in text
        # EngagementEvent and DamageEvent ARE significant
        assert "Unit attacks" in text

    def test_timeline_style(self) -> None:
        text = format_narrative(self._sample_ticks(), style="timeline")
        assert "[T    0]" in text
        assert "[T    1]" in text
        assert "---" not in text
