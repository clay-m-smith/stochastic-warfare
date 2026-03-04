"""Battle narrative generation from simulation events.

Registry-based template system maps event types to human-readable
descriptions, producing a structured timeline of battle actions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class NarrativeEntry:
    """A single narrative line within a tick."""

    event_type: str
    text: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class NarrativeTick:
    """All narrative entries for a single simulation tick."""

    tick: int
    entries: list[NarrativeEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Formatter registry
# ---------------------------------------------------------------------------

_FORMATTERS: dict[str, Callable[[dict[str, Any]], str]] = {}


def register_formatter(event_type: str) -> Callable:
    """Decorator to register a formatter for an event type."""

    def decorator(fn: Callable[[dict[str, Any]], str]) -> Callable[[dict[str, Any]], str]:
        _FORMATTERS[event_type] = fn
        return fn

    return decorator


def get_formatter(event_type: str) -> Callable[[dict[str, Any]], str] | None:
    """Return the formatter for an event type, or None."""
    return _FORMATTERS.get(event_type)


def registered_event_types() -> list[str]:
    """Return all event types with registered formatters."""
    return sorted(_FORMATTERS.keys())


# ---------------------------------------------------------------------------
# Built-in formatters (~15 event types)
# ---------------------------------------------------------------------------


@register_formatter("EngagementEvent")
def _fmt_engagement(d: dict[str, Any]) -> str:
    result = d.get("result", "unknown")
    attacker = d.get("attacker_id", "?")
    target = d.get("target_id", "?")
    weapon = d.get("weapon_id", "?")
    ammo = d.get("ammo_type", "")
    ammo_str = f" ({ammo})" if ammo else ""
    return f"{attacker} engages {target} with {weapon}{ammo_str} — {result}"


@register_formatter("HitEvent")
def _fmt_hit(d: dict[str, Any]) -> str:
    target = d.get("target_id", "?")
    dmg_type = d.get("damage_type", "?")
    penetrated = d.get("penetrated", False)
    pen_str = "penetrating" if penetrated else "non-penetrating"
    return f"{target} hit — {dmg_type}, {pen_str}"


@register_formatter("DamageEvent")
def _fmt_damage(d: dict[str, Any]) -> str:
    target = d.get("target_id", "?")
    amount = d.get("damage_amount", 0)
    location = d.get("location", "?")
    return f"{target} takes {amount:.1f} damage to {location}"


@register_formatter("SuppressionEvent")
def _fmt_suppression(d: dict[str, Any]) -> str:
    target = d.get("target_id", "?")
    level = d.get("suppression_level", 0)
    return f"{target} suppressed to level {level}"


@register_formatter("FratricideEvent")
def _fmt_fratricide(d: dict[str, Any]) -> str:
    shooter = d.get("shooter_id", "?")
    victim = d.get("victim_id", "?")
    cause = d.get("cause", "?")
    return f"FRATRICIDE: {shooter} hits friendly {victim} ({cause})"


@register_formatter("DetectionEvent")
def _fmt_detection(d: dict[str, Any]) -> str:
    observer = d.get("observer_id", "?")
    target = d.get("target_id", "?")
    sensor = d.get("sensor_type", "?")
    rng = d.get("detection_range", 0)
    return f"{observer} detects {target} via {sensor} at {rng:.0f}m"


@register_formatter("ContactLostEvent")
def _fmt_contact_lost(d: dict[str, Any]) -> str:
    contact = d.get("contact_id", "?")
    side = d.get("side", "?")
    return f"{side} loses contact with {contact}"


@register_formatter("MoraleStateChangeEvent")
def _fmt_morale(d: dict[str, Any]) -> str:
    unit = d.get("unit_id", "?")
    old = d.get("old_state", "?")
    new = d.get("new_state", "?")
    return f"{unit} morale: {old} -> {new}"


@register_formatter("RoutEvent")
def _fmt_rout(d: dict[str, Any]) -> str:
    unit = d.get("unit_id", "?")
    return f"{unit} ROUTS and flees the battlefield"


@register_formatter("SurrenderEvent")
def _fmt_surrender(d: dict[str, Any]) -> str:
    unit = d.get("unit_id", "?")
    captor = d.get("capturing_side", "?")
    return f"{unit} SURRENDERS to {captor}"


@register_formatter("OrderIssuedEvent")
def _fmt_order_issued(d: dict[str, Any]) -> str:
    issuer = d.get("issuer_id", "?")
    recipient = d.get("recipient_id", "?")
    order_type = d.get("order_type", "?")
    return f"{issuer} issues {order_type} to {recipient}"


@register_formatter("OrderCompletedEvent")
def _fmt_order_completed(d: dict[str, Any]) -> str:
    unit = d.get("unit_id", "?")
    success = d.get("success", False)
    status = "completed" if success else "FAILED"
    return f"{unit} order {status}"


@register_formatter("DecisionMadeEvent")
def _fmt_decision(d: dict[str, Any]) -> str:
    unit = d.get("unit_id", "?")
    decision = d.get("decision_type", "?")
    confidence = d.get("confidence", 0)
    return f"{unit} decides to {decision} (confidence {confidence:.0%})"


@register_formatter("VictoryDeclaredEvent")
def _fmt_victory(d: dict[str, Any]) -> str:
    winner = d.get("winning_side", "?")
    condition = d.get("condition_type", "?")
    return f"VICTORY: {winner} wins by {condition}"


@register_formatter("OODAPhaseChangeEvent")
def _fmt_ooda(d: dict[str, Any]) -> str:
    unit = d.get("unit_id", "?")
    new_phase = d.get("new_phase", "?")
    cycle = d.get("cycle_number", "?")
    return f"{unit} OODA cycle {cycle}: enters phase {new_phase}"


def _generic_formatter(event_type: str, d: dict[str, Any]) -> str:
    """Fallback formatter for unregistered event types."""
    parts = [f"{event_type}:"]
    for k, v in sorted(d.items()):
        parts.append(f"  {k}={v}")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Narrative generation
# ---------------------------------------------------------------------------


def format_event(event_type: str, data: dict[str, Any]) -> str:
    """Format a single event using the registered formatter or generic fallback."""
    formatter = _FORMATTERS.get(event_type)
    if formatter is not None:
        return formatter(data)
    return _generic_formatter(event_type, data)


def generate_narrative(
    events: list[Any],
    *,
    side_filter: str | None = None,
    event_types: list[str] | None = None,
    max_ticks: int | None = None,
) -> list[NarrativeTick]:
    """Generate a structured narrative from recorded events.

    Parameters
    ----------
    events:
        List of ``RecordedEvent`` objects (from ``SimulationRecorder``).
    side_filter:
        If set, only include events mentioning this side in common fields.
    event_types:
        If set, only include these event type names.
    max_ticks:
        If set, limit output to this many ticks.

    Returns
    -------
    list[NarrativeTick]
        One entry per tick that has events, in tick order.
    """
    # Group events by tick
    tick_map: dict[int, list[Any]] = {}
    for ev in events:
        tick = ev.tick
        if max_ticks is not None and tick > max_ticks:
            continue
        if event_types and ev.event_type not in event_types:
            continue
        if side_filter and not _event_matches_side(ev, side_filter):
            continue
        tick_map.setdefault(tick, []).append(ev)

    # Build narrative ticks
    result: list[NarrativeTick] = []
    for tick in sorted(tick_map.keys()):
        entries: list[NarrativeEntry] = []
        for ev in tick_map[tick]:
            text = format_event(ev.event_type, ev.data)
            entries.append(NarrativeEntry(event_type=ev.event_type, text=text, data=ev.data))
        result.append(NarrativeTick(tick=tick, entries=entries))

    return result


def _event_matches_side(ev: Any, side: str) -> bool:
    """Check if an event is relevant to a given side."""
    data = ev.data
    for key in ("observer_side", "side", "capturing_side", "winning_side"):
        if data.get(key) == side:
            return True
    # Check unit/entity IDs that might contain side prefix
    for key in ("attacker_id", "target_id", "unit_id", "observer_id"):
        val = data.get(key, "")
        if isinstance(val, str) and val.startswith(f"{side}_"):
            return True
    return False


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

# Significant event types used for summary filtering
_SIGNIFICANT_TYPES = frozenset({
    "EngagementEvent",
    "DamageEvent",
    "FratricideEvent",
    "MoraleStateChangeEvent",
    "RoutEvent",
    "SurrenderEvent",
    "VictoryDeclaredEvent",
    "DecisionMadeEvent",
})


def format_narrative(
    ticks: list[NarrativeTick],
    *,
    style: str = "full",
) -> str:
    """Format narrative ticks as human-readable text.

    Parameters
    ----------
    ticks:
        Output from ``generate_narrative()``.
    style:
        ``"full"`` — every tick with all entries.
        ``"summary"`` — only significant event types.
        ``"timeline"`` — compact, one line per entry.
    """
    lines: list[str] = []

    for nt in ticks:
        entries = nt.entries
        if style == "summary":
            entries = [e for e in entries if e.event_type in _SIGNIFICANT_TYPES]
            if not entries:
                continue

        if style == "timeline":
            for entry in entries:
                lines.append(f"[T{nt.tick:>5}] {entry.text}")
        else:
            lines.append(f"--- Tick {nt.tick} ---")
            for entry in entries:
                lines.append(f"  {entry.text}")
            lines.append("")

    return "\n".join(lines)
