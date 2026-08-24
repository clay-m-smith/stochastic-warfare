"""Tests for logistics/disruption.py -- interdiction, blockade, sabotage."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.logistics.disruption import (
    DisruptionConfig,
    DisruptionEngine,
)
from stochastic_warfare.logistics.events import (
    BlockadeEstablishedEvent,
    RouteDegradedEvent,
    RouteInterdictedEvent,
)

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
_POS = Position(5000.0, 5000.0)


def _make_engine(
    seed: int = 42, config: DisruptionConfig | None = None,
) -> tuple[DisruptionEngine, EventBus]:
    bus = EventBus()
    rng = RNGManager(seed).get_stream(ModuleId.LOGISTICS)
    engine = DisruptionEngine(event_bus=bus, rng=rng, config=config)
    return engine, bus


# ---------------------------------------------------------------------------
# Interdiction
# ---------------------------------------------------------------------------


class TestInterdiction:
    def test_create_zone(self) -> None:
        engine, _ = _make_engine()
        zone = engine.apply_interdiction("z1", _POS, 1000.0, 0.8)
        assert zone.intensity == 0.8
        assert zone.radius_m == 1000.0

    def test_create_zone_publishes_event(self) -> None:
        engine, bus = _make_engine()
        events: list[Event] = []
        bus.subscribe(RouteInterdictedEvent, events.append)
        engine.apply_interdiction("z1", _POS, 1000.0, 0.8, timestamp=_TS)
        assert len(events) == 1

    def test_intensity_clamped(self) -> None:
        engine, _ = _make_engine()
        zone = engine.apply_interdiction("z1", _POS, 1000.0, 1.5)
        assert zone.intensity == 1.0
        zone2 = engine.apply_interdiction("z2", _POS, 1000.0, -0.5)
        assert zone2.intensity == 0.0

    def test_remove_zone(self) -> None:
        engine, _ = _make_engine()
        engine.apply_interdiction("z1", _POS, 1000.0, 0.8)
        engine.remove_interdiction("z1")
        assert len(engine.active_zones()) == 0

    def test_transport_survives_outside_zone(self) -> None:
        engine, _ = _make_engine()
        engine.apply_interdiction("z1", _POS, 100.0, 1.0)
        # Position far from zone
        result = engine.check_transport_interdiction(Position(0.0, 0.0))
        assert result is True  # survived

    def test_transport_destruction_probability(self) -> None:
        """Statistical test: high intensity → many destroyed."""
        destroyed = 0
        cfg = DisruptionConfig(interdiction_effectiveness=1.0)
        for seed in range(100):
            engine, _ = _make_engine(seed=seed, config=cfg)
            engine.apply_interdiction("z1", _POS, 10000.0, 1.0)
            if not engine.check_transport_interdiction(_POS):
                destroyed += 1
        # With effectiveness=1.0 and intensity=1.0, all should be destroyed
        assert destroyed == 100

    def test_low_intensity_fewer_destroyed(self) -> None:
        destroyed = 0
        cfg = DisruptionConfig(interdiction_effectiveness=0.5)
        for seed in range(200):
            engine, _ = _make_engine(seed=seed, config=cfg)
            engine.apply_interdiction("z1", _POS, 10000.0, 0.2)
            if not engine.check_transport_interdiction(_POS):
                destroyed += 1
        # p_destroy = 0.2 * 0.5 = 0.1 → expect ~20 out of 200
        assert 5 < destroyed < 40

    def test_get_zone(self) -> None:
        engine, _ = _make_engine()
        engine.apply_interdiction("z1", _POS, 1000.0, 0.5)
        zone = engine.get_zone("z1")
        assert zone.zone_id == "z1"

    def test_deterministic_interdiction(self) -> None:
        def run(seed: int) -> bool:
            engine, _ = _make_engine(seed=seed)
            engine.apply_interdiction("z1", _POS, 10000.0, 0.5)
            return engine.check_transport_interdiction(_POS)
        assert run(42) == run(42)


# ---------------------------------------------------------------------------
# Blockade
# ---------------------------------------------------------------------------


class TestBlockade:
    def test_create_blockade(self) -> None:
        engine, _ = _make_engine()
        blockade = engine.apply_blockade(
            "b1", ["zone_a", "zone_b"], ["ddg_1", "ddg_2", "ddg_3"], "blue",
        )
        assert blockade.effectiveness == pytest.approx(3 * 0.15)

    def test_blockade_capped(self) -> None:
        cfg = DisruptionConfig(
            blockade_effectiveness_per_ship=0.15,
            max_blockade_effectiveness=0.9,
        )
        engine, _ = _make_engine(config=cfg)
        blockade = engine.apply_blockade(
            "b1", ["zone_a"], ["d1", "d2", "d3", "d4", "d5", "d6", "d7"], "blue",
        )
        assert blockade.effectiveness == 0.9  # capped

    def test_blockade_publishes_event(self) -> None:
        engine, bus = _make_engine()
        events: list[Event] = []
        bus.subscribe(BlockadeEstablishedEvent, events.append)
        engine.apply_blockade("b1", ["zone_a"], ["ddg_1"], "blue", timestamp=_TS)
        assert len(events) == 1

    def test_remove_blockade(self) -> None:
        engine, _ = _make_engine()
        engine.apply_blockade("b1", ["zone_a"], ["ddg_1"], "blue")
        engine.remove_blockade("b1")
        assert len(engine.active_blockades()) == 0

    def test_check_blockade_effectiveness(self) -> None:
        engine, _ = _make_engine()
        engine.apply_blockade("b1", ["zone_a"], ["d1", "d2"], "blue")
        eff = engine.check_blockade("zone_a")
        assert eff == pytest.approx(2 * 0.15)

    def test_check_blockade_no_blockade(self) -> None:
        engine, _ = _make_engine()
        assert engine.check_blockade("zone_a") == 0.0

    def test_sea_transit_through_blockade(self) -> None:
        """Statistical test: blockade should intercept proportionally."""
        intercepted = 0
        for seed in range(200):
            engine, _ = _make_engine(seed=seed)
            engine.apply_blockade("b1", ["zone_a"], ["d1", "d2", "d3"], "blue")
            # effectiveness = 3 * 0.15 = 0.45
            if not engine.check_sea_transit("zone_a"):
                intercepted += 1
        # Expect ~45% intercepted (90 out of 200)
        assert 60 < intercepted < 120

    def test_sea_transit_no_blockade(self) -> None:
        engine, _ = _make_engine()
        assert engine.check_sea_transit("zone_a") is True


# ---------------------------------------------------------------------------
# Seasonal degradation
# ---------------------------------------------------------------------------


class TestSeasonalDegradation:
    def test_no_degradation_in_dry(self) -> None:
        engine, _ = _make_engine()
        new_cond = engine.apply_seasonal_degradation("r1", 1.0, 10.0, ground_state=0)
        assert new_cond == 1.0

    def test_degradation_in_mud(self) -> None:
        engine, _ = _make_engine()
        new_cond = engine.apply_seasonal_degradation("r1", 1.0, 10.0, ground_state=2)
        assert new_cond == pytest.approx(0.9)

    def test_degradation_publishes_event(self) -> None:
        engine, bus = _make_engine()
        events: list[Event] = []
        bus.subscribe(RouteDegradedEvent, events.append)
        engine.apply_seasonal_degradation("r1", 1.0, 5.0, ground_state=3, timestamp=_TS)
        assert len(events) == 1
        assert events[0].cause == "seasonal"

    def test_condition_floors_at_zero(self) -> None:
        engine, _ = _make_engine()
        new_cond = engine.apply_seasonal_degradation("r1", 0.05, 100.0, ground_state=2)
        assert new_cond == 0.0


# ---------------------------------------------------------------------------
# Sabotage
# ---------------------------------------------------------------------------


class TestSabotage:
    def test_sabotage_with_hostile_population(self) -> None:
        """Statistical test: hostile population causes some sabotage."""
        damages = 0
        cfg = DisruptionConfig(sabotage_base_probability=0.5)
        for seed in range(100):
            engine, _ = _make_engine(seed=seed, config=cfg)
            damage = engine.check_sabotage("r1", population_hostility=1.0)
            if damage > 0:
                damages += 1
        assert damages > 20  # with p=0.5 should be ~50

    def test_no_sabotage_without_hostility(self) -> None:
        engine, _ = _make_engine()
        damage = engine.check_sabotage("r1", population_hostility=0.0)
        assert damage == 0.0

    def test_sabotage_publishes_event(self) -> None:
        cfg = DisruptionConfig(sabotage_base_probability=1.0)
        engine, bus = _make_engine(config=cfg)
        events: list[Event] = []
        bus.subscribe(RouteDegradedEvent, events.append)
        engine.check_sabotage("r1", population_hostility=1.0, timestamp=_TS)
        assert len(events) == 1
        assert events[0].cause == "sabotage"


# ---------------------------------------------------------------------------
# State protocol
# ---------------------------------------------------------------------------


class TestStateProtocol:
    def test_state_round_trip(self) -> None:
        engine, _ = _make_engine()
        engine.apply_interdiction("z1", _POS, 1000.0, 0.7)
        engine.apply_blockade("b1", ["zone_a"], ["ddg_1"], "blue")

        state = engine.get_state()
        engine2, _ = _make_engine()
        engine2.set_state(state)
        assert engine2.get_state() == state

    def test_set_state_clears_previous(self) -> None:
        engine, _ = _make_engine()
        engine.apply_interdiction("z1", _POS, 1000.0, 0.5)
        engine.set_state({"zones": {}, "blockades": {}})
        assert len(engine.active_zones()) == 0
