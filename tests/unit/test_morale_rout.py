"""Tests for morale/rout.py — rout, rally, surrender, and cascade mechanics."""

from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError, replace
import math

import numpy as np
import pytest
from pydantic import ValidationError

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.morale.events import RallyEvent, RoutEvent, SurrenderEvent
from stochastic_warfare.morale.rout import (
    RallyPlan,
    RoutConfig,
    RoutCascadeCandidate,
    RoutEngine,
    RoutState,
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

    def test_custom(self) -> None:
        cfg = RoutConfig(rally_base_chance=0.3, cascade_radius_m=1000.0)
        assert cfg.rally_base_chance == 0.3
        assert cfg.cascade_radius_m == 1000.0

    def test_is_strict_and_immutable(self) -> None:
        with pytest.raises(ValidationError, match="extra_forbidden"):
            RoutConfig(unknown_option=True)
        with pytest.raises(ValidationError, match="extra_forbidden"):
            RoutConfig(surrender_threshold=0.6)

        cfg = RoutConfig()
        with pytest.raises(ValidationError, match="frozen_instance"):
            cfg.cascade_radius_m = 1.0


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
            if engine.plan_rally(
                "u1",
                nearby_friendly_count=5,
                leader_present=True,
            ).rallied:
                rallied = True
                break
        assert rallied

    def test_leader_helps_rally(self) -> None:
        """With leader, rally should succeed more often."""
        success_leader = 0
        success_no_leader = 0
        for seed in range(200):
            e1, _ = _engine(seed=seed)
            if e1.plan_rally(
                "u1",
                nearby_friendly_count=2,
                leader_present=True,
            ).rallied:
                success_leader += 1
            e2, _ = _engine(seed=seed)
            if e2.plan_rally(
                "u2",
                nearby_friendly_count=2,
                leader_present=False,
            ).rallied:
                success_no_leader += 1
        assert success_leader > success_no_leader

    def test_partial_compatibility_api_fails_before_rng_draw(self) -> None:
        engine, _ = _engine()
        before = copy.deepcopy(engine.rng.bit_generator.state)

        with pytest.raises(RuntimeError, match="MoraleRuntime.check_rally"):
            engine.check_rally(
                "u1",
                nearby_friendly_count=2,
                leader_present=True,
            )

        assert engine.rng.bit_generator.state == before

    def test_rally_plan_does_not_remove_active_rout(self) -> None:
        cfg = RoutConfig(rally_base_chance=0.99)
        engine, _ = _engine(config=cfg)
        engine.initiate_rout("u1", threat_direction_rad=0.0)
        assert "u1" in engine._active_routs
        plan = engine.plan_rally(
            "u1",
            nearby_friendly_count=5,
            leader_present=True,
        )
        assert isinstance(plan, RallyPlan)
        assert plan.rallied
        assert "u1" in engine._active_routs

    def test_rally_plan_publishes_no_event(self) -> None:
        cfg = RoutConfig(rally_base_chance=0.99)
        engine, bus = _engine(config=cfg)
        received: list[RallyEvent] = []
        bus.subscribe(RallyEvent, lambda e: received.append(e))
        plan = engine.plan_rally(
            "u1",
            nearby_friendly_count=5,
            leader_present=True,
        )
        assert plan.rallied_by == "leader"
        assert received == []


# ── process_surrender ────────────────────────────────────────────────


class TestProcessSurrender:
    def test_partial_api_fails_before_rng_route_or_event_mutation(self) -> None:
        engine, bus = _engine()
        engine.initiate_rout("u1", threat_direction_rad=0.0)
        before_rng = copy.deepcopy(engine.rng.bit_generator.state)
        before_routes = copy.deepcopy(engine._active_routs)
        received: list[SurrenderEvent] = []
        bus.subscribe(SurrenderEvent, lambda e: received.append(e))
        with pytest.raises(RuntimeError, match="authoritative morale"):
            engine.process_surrender(
                "u1",
                personnel_count=50,
                capturing_side="red",
            )
        assert engine.rng.bit_generator.state == before_rng
        assert engine._active_routs == before_routes
        assert received == []


# ── rout_cascade ─────────────────────────────────────────────────────


class TestRoutCascade:
    def test_plan_uses_lexicographic_candidate_order(self) -> None:
        cfg = RoutConfig(
            cascade_base_chance=1.0,
            cascade_shaken_susceptibility=2.0,
        )
        engine, _ = _engine(config=cfg)
        plan = engine.plan_cascade(
            "source",
            (
                RoutCascadeCandidate("z", 1, 10.0),
                RoutCascadeCandidate("a", 1, 10.0),
            ),
        )
        assert plan.selected_unit_ids == ("a", "z")

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

    def test_current_state_has_no_rng_mirror(self) -> None:
        engine, bus = _engine(seed=42)
        engine.initiate_rout("u1", threat_direction_rad=0.5)
        state = engine.get_state()
        assert set(state) == {"active_routs"}

    def test_restore_does_not_change_injected_rng(self) -> None:
        engine, _ = _engine(seed=42)
        before = engine.rng.bit_generator.state
        engine.set_state({"active_routs": {}})
        assert engine.rng.bit_generator.state == before

    def test_staged_routes_are_immutable_and_detached(self) -> None:
        engine, _ = _engine(seed=42)
        live = engine.initiate_rout("u1", threat_direction_rad=0.5)
        raw = engine.get_state()
        plan = engine.stage_state(raw)
        staged = plan.active_routs[0][1]
        planned_direction = staged.direction_rad

        with pytest.raises(FrozenInstanceError):
            staged.direction_rad = float("inf")

        raw["active_routs"]["u1"]["direction_rad"] = 0.0
        live.direction_rad = 1.0
        assert staged.direction_rad == planned_direction

    def test_commit_rejects_forged_duplicate_plan_atomically(self) -> None:
        engine, _ = _engine(seed=42)
        engine.initiate_rout("u1", threat_direction_rad=0.5)
        plan = engine.stage_state(engine.get_state())
        forged = replace(
            plan,
            active_routs=(plan.active_routs[0], plan.active_routs[0]),
        )
        routes = engine._active_routs
        rng = engine.rng
        before_state = copy.deepcopy(engine.get_state())
        before_rng = copy.deepcopy(rng.bit_generator.state)

        with pytest.raises(ValueError, match="canonical unique"):
            engine.commit_state(forged)

        assert engine._active_routs is routes
        assert engine.get_state() == before_state
        assert engine.rng is rng
        assert rng.bit_generator.state == before_rng

    def test_commit_rejects_forged_nonfinite_snapshot_atomically(self) -> None:
        engine, _ = _engine(seed=42)
        engine.initiate_rout("u1", threat_direction_rad=0.5)
        plan = engine.stage_state(engine.get_state())
        unit_id, snapshot = plan.active_routs[0]
        forged = replace(
            plan,
            active_routs=((unit_id, replace(snapshot, direction_rad=float("inf"))),),
        )
        routes = engine._active_routs
        rng = engine.rng
        before_state = copy.deepcopy(engine.get_state())
        before_rng = copy.deepcopy(rng.bit_generator.state)

        with pytest.raises(ValueError, match="finite"):
            engine.commit_state(forged)

        assert engine._active_routs is routes
        assert engine.get_state() == before_state
        assert engine.rng is rng
        assert rng.bit_generator.state == before_rng

    def test_commit_preserves_mapping_and_rng_identity(self) -> None:
        engine, _ = _engine(seed=42)
        engine.initiate_rout("u1", threat_direction_rad=0.5)
        plan = engine.stage_state(engine.get_state())
        routes = engine._active_routs
        rng = engine.rng
        before_rng = copy.deepcopy(rng.bit_generator.state)
        engine._active_routs["u1"].speed_factor = 99.0

        engine.commit_state(plan)

        assert engine._active_routs is routes
        assert engine._active_routs["u1"].speed_factor == pytest.approx(
            RoutConfig().rout_speed_factor,
        )
        assert engine.rng is rng
        assert rng.bit_generator.state == before_rng
