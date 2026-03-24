"""Tests for c2/coordination.py — fire support coordination measures."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.c2.coordination import (
    CoordinationEngine,
    CoordinationMeasure,
    CoordinationMeasureType,
    FireType,
)
from stochastic_warfare.c2.events import CoordinationViolationEvent
from stochastic_warfare.core.types import Position

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


class TestCoordinationEnums:
    """Coordination enums."""

    def test_measure_type_values(self) -> None:
        assert CoordinationMeasureType.FSCL == 0
        assert CoordinationMeasureType.MISSILE_FLIGHT_CORRIDOR == 7
        assert len(CoordinationMeasureType) == 8

    def test_fire_type_values(self) -> None:
        assert FireType.DIRECT == 0
        assert FireType.MISSILE == 4
        assert len(FireType) == 5


class TestNFA:
    """No Fire Area — blocks all fires."""

    def test_nfa_blocks_fire(self) -> None:
        bus = EventBus()
        coord = CoordinationEngine(bus, rng=np.random.default_rng(0))
        coord.add_measure(CoordinationMeasure(
            measure_id="nfa1",
            measure_type=CoordinationMeasureType.NFA,
            center=Position(1000, 2000),
            radius_m=500.0,
        ))
        cleared, reason = coord.check_fire_clearance(
            "arty1", Position(1000, 2000), FireType.INDIRECT, _TS,
        )
        assert cleared is False
        assert "nfa" in reason

    def test_nfa_publishes_violation(self) -> None:
        bus = EventBus()
        coord = CoordinationEngine(bus, rng=np.random.default_rng(0))
        coord.add_measure(CoordinationMeasure(
            measure_id="nfa1",
            measure_type=CoordinationMeasureType.NFA,
            center=Position(1000, 2000),
            radius_m=500.0,
        ))
        events: list[CoordinationViolationEvent] = []
        bus.subscribe(CoordinationViolationEvent, events.append)
        coord.check_fire_clearance(
            "arty1", Position(1000, 2000), FireType.INDIRECT, _TS,
        )
        assert len(events) == 1
        assert events[0].measure_type == "NFA"

    def test_outside_nfa_cleared(self) -> None:
        bus = EventBus()
        coord = CoordinationEngine(bus, rng=np.random.default_rng(0))
        coord.add_measure(CoordinationMeasure(
            measure_id="nfa1",
            measure_type=CoordinationMeasureType.NFA,
            center=Position(1000, 2000),
            radius_m=500.0,
        ))
        cleared, reason = coord.check_fire_clearance(
            "arty1", Position(5000, 5000), FireType.INDIRECT, _TS,
        )
        assert cleared is True


class TestRFA:
    """Restrictive Fire Area — requires coordination."""

    def test_rfa_requires_coordination(self) -> None:
        bus = EventBus()
        coord = CoordinationEngine(bus, rng=np.random.default_rng(0))
        coord.add_measure(CoordinationMeasure(
            measure_id="rfa1",
            measure_type=CoordinationMeasureType.RFA,
            center=Position(1000, 2000),
            radius_m=500.0,
            requires_coordination_with="bn1",
        ))
        cleared, reason = coord.check_fire_clearance(
            "arty1", Position(1000, 2000), FireType.INDIRECT, _TS,
        )
        assert cleared is False
        assert "coordination" in reason


class TestFFA:
    """Free Fire Area — all fires cleared."""

    def test_ffa_clears_fire(self) -> None:
        bus = EventBus()
        coord = CoordinationEngine(bus, rng=np.random.default_rng(0))
        coord.add_measure(CoordinationMeasure(
            measure_id="ffa1",
            measure_type=CoordinationMeasureType.FFA,
            center=Position(1000, 2000),
            radius_m=500.0,
        ))
        cleared, reason = coord.check_fire_clearance(
            "arty1", Position(1000, 2000), FireType.INDIRECT, _TS,
        )
        assert cleared is True
        assert reason == "free_fire_area"


class TestFSCL:
    """Fire Support Coordination Line."""

    def test_set_and_query_fscl(self) -> None:
        bus = EventBus()
        coord = CoordinationEngine(bus, rng=np.random.default_rng(0))
        coord.set_fscl(Position(0, 5000), Position(10000, 5000))
        assert coord.get_fscl() is not None

    def test_beyond_fscl(self) -> None:
        bus = EventBus()
        coord = CoordinationEngine(bus, rng=np.random.default_rng(0))
        coord.set_fscl(Position(0, 5000), Position(10000, 5000))
        assert coord.is_beyond_fscl(Position(5000, 6000)) is True

    def test_short_of_fscl(self) -> None:
        bus = EventBus()
        coord = CoordinationEngine(bus, rng=np.random.default_rng(0))
        coord.set_fscl(Position(0, 5000), Position(10000, 5000))
        assert coord.is_beyond_fscl(Position(5000, 4000)) is False

    def test_air_short_of_fscl_requires_coordination(self) -> None:
        bus = EventBus()
        coord = CoordinationEngine(bus, rng=np.random.default_rng(0))
        coord.set_fscl(Position(0, 5000), Position(10000, 5000))
        cleared, reason = coord.check_fire_clearance(
            "cas_flight", Position(5000, 4000), FireType.AIR_DELIVERED, _TS,
        )
        assert cleared is False
        assert "fscl" in reason

    def test_direct_fire_short_of_fscl_ok(self) -> None:
        bus = EventBus()
        coord = CoordinationEngine(bus, rng=np.random.default_rng(0))
        coord.set_fscl(Position(0, 5000), Position(10000, 5000))
        cleared, reason = coord.check_fire_clearance(
            "tank1", Position(5000, 4000), FireType.DIRECT, _TS,
        )
        assert cleared is True


class TestBoundary:
    """Boundary crossing check."""

    def test_boundary_crossing_detected(self) -> None:
        bus = EventBus()
        coord = CoordinationEngine(bus, rng=np.random.default_rng(0))
        coord.add_measure(CoordinationMeasure(
            measure_id="bdy1",
            measure_type=CoordinationMeasureType.BOUNDARY,
            center=Position(0, 0),
            radius_m=0,
            line_start=Position(0, 0),
            line_end=Position(0, 10000),
        ))
        events: list[CoordinationViolationEvent] = []
        bus.subscribe(CoordinationViolationEvent, events.append)
        cleared, reason = coord.check_movement_clearance(
            "plt1", Position(-100, 5000), Position(100, 5000), _TS,
        )
        assert cleared is False
        assert "boundary" in reason
        assert len(events) == 1

    def test_no_boundary_crossing_cleared(self) -> None:
        bus = EventBus()
        coord = CoordinationEngine(bus, rng=np.random.default_rng(0))
        coord.add_measure(CoordinationMeasure(
            measure_id="bdy1",
            measure_type=CoordinationMeasureType.BOUNDARY,
            center=Position(0, 0),
            radius_m=0,
            line_start=Position(0, 0),
            line_end=Position(0, 10000),
        ))
        cleared, reason = coord.check_movement_clearance(
            "plt1", Position(100, 5000), Position(200, 5000), _TS,
        )
        assert cleared is True

    def test_movement_into_nfa_blocked(self) -> None:
        bus = EventBus()
        coord = CoordinationEngine(bus, rng=np.random.default_rng(0))
        coord.add_measure(CoordinationMeasure(
            measure_id="nfa1",
            measure_type=CoordinationMeasureType.NFA,
            center=Position(1000, 2000),
            radius_m=500.0,
        ))
        cleared, reason = coord.check_movement_clearance(
            "plt1", Position(0, 0), Position(1000, 2000), _TS,
        )
        assert cleared is False


class TestMeasureManagement:
    """Add/remove measures."""

    def test_remove_measure(self) -> None:
        bus = EventBus()
        coord = CoordinationEngine(bus, rng=np.random.default_rng(0))
        coord.add_measure(CoordinationMeasure(
            measure_id="nfa1",
            measure_type=CoordinationMeasureType.NFA,
            center=Position(1000, 2000), radius_m=500.0,
        ))
        coord.remove_measure("nfa1")
        cleared, reason = coord.check_fire_clearance(
            "arty1", Position(1000, 2000), FireType.INDIRECT, _TS,
        )
        assert cleared is True


class TestCoordinationState:
    """State protocol."""

    def test_state_round_trip(self) -> None:
        bus = EventBus()
        coord = CoordinationEngine(bus, rng=np.random.default_rng(0))
        coord.add_measure(CoordinationMeasure(
            measure_id="nfa1",
            measure_type=CoordinationMeasureType.NFA,
            center=Position(1000, 2000), radius_m=500.0,
        ))
        coord.set_fscl(Position(0, 5000), Position(10000, 5000))
        state = coord.get_state()
        coord2 = CoordinationEngine(bus, rng=np.random.default_rng(0))
        coord2.set_state(state)
        assert coord2.get_state() == state
