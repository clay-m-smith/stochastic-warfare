"""Tests for morale/rout.py — rout, rally, surrender, and cascade mechanics."""

from __future__ import annotations

import math

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.morale.events import RallyEvent, RoutEvent, SurrenderEvent
from stochastic_warfare.morale.rout import (
    RoutConfig,
    RoutEngine,
    RoutState,
    SurrenderResult,
)


# ── helpers ──────────────────────────────────────────────────────────


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _engine(seed: int = 42, config: RoutConfig | None = None) -> tuple[RoutEngine, EventBus]:
    bus = EventBus()
    return RoutEngine(bus, _rng(seed), config), bus


# ── RoutConfig ───────────────────────────────────────────────────────


class TestRoutConfig:
    def test_defaults(self) -> None:
        cfg = RoutConfig()
        assert cfg.rally_base_chance > 0
        assert cfg.cascade_radius_m > 0
        assert cfg.surrender_threshold > 0

    def test_custom(self) -> None:
        cfg = RoutConfig(rally_base_chance=0.3, cascade_radius_m=1000.0)
        assert cfg.rally_base_chance == 0.3
        assert cfg.cascade_radius_m == 1000.0


# ── initiate_rout ────────────────────────────────────────────────────


class TestInitiateRout:
    def test_returns_rout_state(self) -> None:
        engine, _ = _engine()
        rs = engine.initiate_rout("u1", threat_direction_rad=0.0)
        assert isinstance(rs, RoutState)
        assert rs.unit_id == "u1"

    def test_flee_opposite_direction(self) -> None:
        engine, _ = _engine()
        rs = engine.initiate_rout("u1", threat_direction_rad=0.0)
        # Should flee roughly opposite (pi) — allow scatter
        assert abs(rs.direction_rad - math.pi) < 1.0

    def test_flee_direction_wrapped(self) -> None:
        """Direction should be normalized to [0, 2*pi)."""
        engine, _ = _engine()
        rs = engine.initiate_rout("u1", threat_direction_rad=5.0)
        assert 0.0 <= rs.direction_rad < 2.0 * math.pi

    def test_speed_factor(self) -> None:
        cfg = RoutConfig(rout_speed_factor=2.0)
        engine, _ = _engine(config=cfg)
        rs = engine.initiate_rout("u1", threat_direction_rad=0.0)
        assert rs.speed_factor == 2.0

    def test_event_published(self) -> None:
        engine, bus = _engine()
        received: list[RoutEvent] = []
        bus.subscribe(RoutEvent, lambda e: received.append(e))
        engine.initiate_rout("u1", threat_direction_rad=1.0)
        assert len(received) == 1
        assert received[0].unit_id == "u1"

    def test_tracked_internally(self) -> None:
        engine, _ = _engine()
        engine.initiate_rout("u1", threat_direction_rad=0.0)
        assert "u1" in engine._active_routs


# ── check_rally ──────────────────────────────────────────────────────


class TestCheckRally:
    def test_rally_possible(self) -> None:
        """With high rally chance, should eventually rally."""
        cfg = RoutConfig(rally_base_chance=0.8, rally_leader_bonus=0.15)
        engine, _ = _engine(config=cfg)
        engine.initiate_rout("u1", threat_direction_rad=0.0)
        rallied = False
        for _ in range(50):
            if engine.check_rally("u1", nearby_friendly_count=5, leader_present=True):
                rallied = True
                break
        assert rallied

    def test_leader_helps_rally(self) -> None:
        """With leader, rally should succeed more often."""
        success_leader = 0
        success_no_leader = 0
        for seed in range(200):
            e1, _ = _engine(seed=seed)
            if e1.check_rally("u1", nearby_friendly_count=2, leader_present=True):
                success_leader += 1
            e2, _ = _engine(seed=seed)
            if e2.check_rally("u2", nearby_friendly_count=2, leader_present=False):
                success_no_leader += 1
        assert success_leader > success_no_leader

    def test_rally_removes_active_rout(self) -> None:
        cfg = RoutConfig(rally_base_chance=0.99)
        engine, _ = _engine(config=cfg)
        engine.initiate_rout("u1", threat_direction_rad=0.0)
        assert "u1" in engine._active_routs
        engine.check_rally("u1", nearby_friendly_count=5, leader_present=True)
        assert "u1" not in engine._active_routs

    def test_rally_event_published(self) -> None:
        cfg = RoutConfig(rally_base_chance=0.99)
        engine, bus = _engine(config=cfg)
        received: list[RallyEvent] = []
        bus.subscribe(RallyEvent, lambda e: received.append(e))
        engine.check_rally("u1", nearby_friendly_count=5, leader_present=True)
        assert len(received) == 1
        assert received[0].rallied_by == "leader"


# ── process_surrender ────────────────────────────────────────────────


class TestProcessSurrender:
    def test_returns_surrender_result(self) -> None:
        engine, _ = _engine()
        result = engine.process_surrender("u1", personnel_count=100, capturing_side="red")
        assert isinstance(result, SurrenderResult)
        assert result.unit_id == "u1"

    def test_pow_count_reasonable(self) -> None:
        engine, _ = _engine()
        result = engine.process_surrender("u1", personnel_count=100, capturing_side="red")
        assert 1 <= result.pow_count <= 100

    def test_minimum_one_pow(self) -> None:
        engine, _ = _engine()
        result = engine.process_surrender("u1", personnel_count=1, capturing_side="blue")
        assert result.pow_count >= 1

    def test_event_published(self) -> None:
        engine, bus = _engine()
        received: list[SurrenderEvent] = []
        bus.subscribe(SurrenderEvent, lambda e: received.append(e))
        engine.process_surrender("u1", personnel_count=50, capturing_side="red")
        assert len(received) == 1
        assert received[0].capturing_side == "red"

    def test_removes_active_rout(self) -> None:
        engine, _ = _engine()
        engine.initiate_rout("u1", threat_direction_rad=0.0)
        engine.process_surrender("u1", personnel_count=50, capturing_side="red")
        assert "u1" not in engine._active_routs

    def test_surrender_result_get_state(self) -> None:
        result = SurrenderResult(unit_id="u1", pow_count=42)
        state = result.get_state()
        assert state["unit_id"] == "u1"
        assert state["pow_count"] == 42


# ── rout_cascade ─────────────────────────────────────────────────────


class TestRoutCascade:
    def test_no_cascade_far_away(self) -> None:
        engine, _ = _engine()
        cascaded = engine.rout_cascade(
            routing_unit_id="u1",
            adjacent_unit_morale_states={"u2": 1},  # SHAKEN
            distances_m={"u2": 1000.0},  # beyond 500m default radius
        )
        assert len(cascaded) == 0

    def test_cascade_possible_nearby(self) -> None:
        """With high cascade chance, nearby SHAKEN units should cascade."""
        cfg = RoutConfig(cascade_base_chance=0.9, cascade_shaken_susceptibility=5.0)
        engine, _ = _engine(config=cfg)
        cascaded = engine.rout_cascade(
            routing_unit_id="u1",
            adjacent_unit_morale_states={"u2": 1},
            distances_m={"u2": 100.0},
        )
        assert "u2" in cascaded

    def test_steady_units_immune(self) -> None:
        """STEADY (0) units should not be affected by cascade."""
        cfg = RoutConfig(cascade_base_chance=1.0)
        engine, _ = _engine(config=cfg)
        cascaded = engine.rout_cascade(
            routing_unit_id="u1",
            adjacent_unit_morale_states={"u2": 0},  # STEADY
            distances_m={"u2": 100.0},
        )
        assert len(cascaded) == 0

    def test_broken_more_susceptible(self) -> None:
        """BROKEN units should cascade more often than SHAKEN."""
        cascade_shaken = 0
        cascade_broken = 0
        for seed in range(200):
            e1, _ = _engine(seed=seed)
            if e1.rout_cascade("u1", {"u2": 1}, {"u2": 200.0}):
                cascade_shaken += 1
            e2, _ = _engine(seed=seed)
            if e2.rout_cascade("u1", {"u2": 2}, {"u2": 200.0}):
                cascade_broken += 1
        assert cascade_broken > cascade_shaken

    def test_excludes_self(self) -> None:
        cfg = RoutConfig(cascade_base_chance=1.0)
        engine, _ = _engine(config=cfg)
        cascaded = engine.rout_cascade(
            routing_unit_id="u1",
            adjacent_unit_morale_states={"u1": 2, "u2": 2},
            distances_m={"u1": 0.0, "u2": 100.0},
        )
        assert "u1" not in cascaded

    def test_multiple_units_cascade(self) -> None:
        cfg = RoutConfig(cascade_base_chance=0.99, cascade_shaken_susceptibility=10.0, cascade_broken_susceptibility=10.0)
        engine, _ = _engine(config=cfg)
        cascaded = engine.rout_cascade(
            routing_unit_id="u1",
            adjacent_unit_morale_states={"u2": 1, "u3": 2, "u4": 0},
            distances_m={"u2": 100.0, "u3": 200.0, "u4": 50.0},
        )
        assert "u2" in cascaded
        assert "u3" in cascaded
        assert "u4" not in cascaded  # STEADY is immune


# ── RoutState data ───────────────────────────────────────────────────


class TestRoutStateData:
    def test_get_set_state(self) -> None:
        rs = RoutState(unit_id="u1", direction_rad=1.5, speed_factor=1.5)
        state = rs.get_state()
        assert state["unit_id"] == "u1"
        assert state["direction_rad"] == pytest.approx(1.5)

        rs2 = RoutState(unit_id="", direction_rad=0.0, speed_factor=0.0)
        rs2.set_state(state)
        assert rs2.unit_id == "u1"
        assert rs2.speed_factor == 1.5


# ── State round-trip ─────────────────────────────────────────────────


class TestRoutEngineState:
    def test_roundtrip(self) -> None:
        engine, bus = _engine(seed=42)
        engine.initiate_rout("u1", threat_direction_rad=0.5)
        state = engine.get_state()

        engine2, bus2 = _engine(seed=0)
        engine2.set_state(state)

        assert "u1" in engine2._active_routs
        assert engine2._active_routs["u1"].unit_id == "u1"

    def test_determinism_after_restore(self) -> None:
        engine, bus = _engine(seed=42)
        engine.initiate_rout("u1", threat_direction_rad=0.5)
        state = engine.get_state()

        engine2, bus2 = _engine(seed=0)
        engine2.set_state(state)

        # Both should produce same cascade results
        morale_states = {"u2": 1, "u3": 2}
        dists = {"u2": 200.0, "u3": 300.0}
        c1 = engine.rout_cascade("u1", morale_states, dists)
        c2 = engine2.rout_cascade("u1", morale_states, dists)
        assert c1 == c2
