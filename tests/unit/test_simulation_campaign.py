"""Tests for the campaign manager (simulation.campaign).

Uses shared fixtures from conftest.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.simulation.battle import BattleManager
from stochastic_warfare.simulation.campaign import (
    CampaignConfig,
    CampaignManager,
    ReinforcementEntry,
)
from stochastic_warfare.simulation.scenario import (
    ReinforcementConfig,
    ReinforcementUnitConfig,
)

from tests.conftest import DEFAULT_SEED, TS, make_rng


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_unit(eid: str, pos: Position, side: str = "blue") -> Unit:
    u = Unit(entity_id=eid, position=pos)
    object.__setattr__(u, "side", side)
    return u


@dataclass
class _MockClock:
    elapsed: timedelta = timedelta(0)
    current_time: datetime = TS


@dataclass
class _MockCtx:
    """Minimal mock of SimulationContext for campaign tests."""

    clock: Any = None
    units_by_side: dict[str, list[Unit]] = field(default_factory=dict)
    rng_manager: Any = None
    unit_loader: Any = None
    ooda_engine: Any = None
    consumption_engine: Any = None
    stockpile_manager: Any = None
    supply_network_engine: Any = None
    maintenance_engine: Any = None
    config: Any = None

    def __post_init__(self) -> None:
        if self.clock is None:
            self.clock = _MockClock()
        if self.rng_manager is None:
            self.rng_manager = RNGManager(DEFAULT_SEED)

    def active_units(self, side: str) -> list[Unit]:
        return [u for u in self.units_by_side.get(side, []) if u.status == UnitStatus.ACTIVE]


# ---------------------------------------------------------------------------
# CampaignConfig
# ---------------------------------------------------------------------------


class TestCampaignConfig:
    """CampaignConfig pydantic model."""

    def test_defaults(self) -> None:
        c = CampaignConfig()
        assert c.engagement_detection_range_m == 15000.0
        assert c.strategic_ai_echelon == 9

    def test_custom_values(self) -> None:
        c = CampaignConfig(engagement_detection_range_m=20000, enable_maintenance=False)
        assert c.engagement_detection_range_m == 20000.0
        assert c.enable_maintenance is False


# ---------------------------------------------------------------------------
# ReinforcementEntry
# ---------------------------------------------------------------------------


class TestReinforcementEntry:
    """ReinforcementEntry dataclass."""

    def test_creation(self) -> None:
        cfg = ReinforcementConfig(
            side="blue", arrival_time_s=3600,
            units=[ReinforcementUnitConfig(unit_type="m1a2", count=2)],
        )
        entry = ReinforcementEntry(config=cfg)
        assert entry.arrived is False

    def test_arrived_flag(self) -> None:
        cfg = ReinforcementConfig(
            side="red", arrival_time_s=0,
            units=[ReinforcementUnitConfig(unit_type="m1a2")],
        )
        entry = ReinforcementEntry(config=cfg, arrived=True)
        assert entry.arrived is True


# ---------------------------------------------------------------------------
# Reinforcement schedule
# ---------------------------------------------------------------------------


class TestReinforcements:
    """CampaignManager reinforcement handling."""

    def test_set_reinforcements(self, event_bus: EventBus) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        reinforcements = [
            ReinforcementConfig(
                side="blue", arrival_time_s=3600,
                units=[ReinforcementUnitConfig(unit_type="m1a2", count=2)],
            ),
        ]
        mgr.set_reinforcements(reinforcements)
        state = mgr.get_state()
        assert len(state["reinforcements"]) == 1

    def test_reinforcements_not_arrived_before_time(self, event_bus: EventBus) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        mgr.set_reinforcements([
            ReinforcementConfig(
                side="blue", arrival_time_s=7200,
                units=[ReinforcementUnitConfig(unit_type="m1a2")],
            ),
        ])
        ctx = _MockCtx(clock=_MockClock(elapsed=timedelta(seconds=3600)))
        new_units = mgr.check_reinforcements(ctx, 3600.0)
        assert len(new_units) == 0

    def test_reinforcements_arrive_at_time(self, event_bus: EventBus) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        mgr.set_reinforcements([
            ReinforcementConfig(
                side="blue", arrival_time_s=3600,
                units=[ReinforcementUnitConfig(unit_type="m1a2")],
                position=[100, 200],
            ),
        ])
        # Need a real unit loader for spawning
        from stochastic_warfare.entities.loader import UnitLoader
        loader = UnitLoader(Path("data/units"))
        loader.load_all()
        ctx = _MockCtx(
            clock=_MockClock(elapsed=timedelta(seconds=3600)),
            unit_loader=loader,
        )
        new_units = mgr.check_reinforcements(ctx, 3600.0)
        assert len(new_units) == 1
        assert new_units[0].position.easting == 100.0

    def test_reinforcements_dont_re_arrive(self, event_bus: EventBus) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        mgr.set_reinforcements([
            ReinforcementConfig(
                side="blue", arrival_time_s=0,
                units=[ReinforcementUnitConfig(unit_type="m1a2")],
            ),
        ])
        from stochastic_warfare.entities.loader import UnitLoader
        loader = UnitLoader(Path("data/units"))
        loader.load_all()
        ctx = _MockCtx(unit_loader=loader)
        units1 = mgr.check_reinforcements(ctx, 100.0)
        units2 = mgr.check_reinforcements(ctx, 200.0)
        assert len(units1) == 1
        assert len(units2) == 0  # Already arrived

    def test_multiple_reinforcements(self, event_bus: EventBus) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        mgr.set_reinforcements([
            ReinforcementConfig(
                side="blue", arrival_time_s=100,
                units=[ReinforcementUnitConfig(unit_type="m1a2", count=2)],
            ),
            ReinforcementConfig(
                side="red", arrival_time_s=200,
                units=[ReinforcementUnitConfig(unit_type="m1a2", count=3)],
            ),
        ])
        from stochastic_warfare.entities.loader import UnitLoader
        loader = UnitLoader(Path("data/units"))
        loader.load_all()
        ctx = _MockCtx(unit_loader=loader)
        units1 = mgr.check_reinforcements(ctx, 150.0)
        assert len(units1) == 2  # Only first batch
        units2 = mgr.check_reinforcements(ctx, 250.0)
        assert len(units2) == 3  # Second batch

    def test_no_loader_returns_empty(self, event_bus: EventBus) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        mgr.set_reinforcements([
            ReinforcementConfig(
                side="blue", arrival_time_s=0,
                units=[ReinforcementUnitConfig(unit_type="m1a2")],
            ),
        ])
        ctx = _MockCtx(unit_loader=None)
        units = mgr.check_reinforcements(ctx, 100.0)
        assert len(units) == 0

    def test_unknown_unit_type_skipped(self, event_bus: EventBus) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        mgr.set_reinforcements([
            ReinforcementConfig(
                side="blue", arrival_time_s=0,
                units=[ReinforcementUnitConfig(unit_type="nonexistent_tank")],
            ),
        ])
        from stochastic_warfare.entities.loader import UnitLoader
        loader = UnitLoader(Path("data/units"))
        loader.load_all()
        ctx = _MockCtx(unit_loader=loader)
        units = mgr.check_reinforcements(ctx, 100.0)
        assert len(units) == 0  # Skipped unknown type

    def test_reinforcement_position_applied(self, event_bus: EventBus) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        mgr.set_reinforcements([
            ReinforcementConfig(
                side="blue", arrival_time_s=0,
                units=[ReinforcementUnitConfig(unit_type="m1a2")],
                position=[500, 1000],
            ),
        ])
        from stochastic_warfare.entities.loader import UnitLoader
        loader = UnitLoader(Path("data/units"))
        loader.load_all()
        ctx = _MockCtx(unit_loader=loader)
        units = mgr.check_reinforcements(ctx, 100.0)
        assert units[0].position.easting == 500.0
        assert units[0].position.northing == 1000.0


# ---------------------------------------------------------------------------
# Engagement detection delegation
# ---------------------------------------------------------------------------


class TestEngagementDetection:
    """CampaignManager.detect_engagements."""

    def test_delegates_to_battle_manager(self, event_bus: EventBus) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        battle_mgr = BattleManager(event_bus)
        blue = [_make_unit("b1", Position(0, 0, 0), "blue")]
        red = [_make_unit("r1", Position(1000, 0, 0), "red")]
        ctx = _MockCtx(units_by_side={"blue": blue, "red": red})
        battles = mgr.detect_engagements(ctx, battle_mgr)
        assert len(battles) == 1

    def test_uses_config_range(self, event_bus: EventBus) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng, CampaignConfig(engagement_detection_range_m=100))
        battle_mgr = BattleManager(event_bus)
        blue = [_make_unit("b1", Position(0, 0, 0), "blue")]
        red = [_make_unit("r1", Position(5000, 0, 0), "red")]
        ctx = _MockCtx(units_by_side={"blue": blue, "red": red})
        battles = mgr.detect_engagements(ctx, battle_mgr)
        assert len(battles) == 0

    def test_no_units_no_battles(self, event_bus: EventBus) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        battle_mgr = BattleManager(event_bus)
        ctx = _MockCtx(units_by_side={"blue": [], "red": []})
        battles = mgr.detect_engagements(ctx, battle_mgr)
        assert len(battles) == 0


# ---------------------------------------------------------------------------
# Strategic update
# ---------------------------------------------------------------------------


class TestStrategicUpdate:
    """CampaignManager.update_strategic."""

    def test_runs_without_error(self, event_bus: EventBus) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        ctx = _MockCtx(
            clock=_MockClock(elapsed=timedelta(seconds=3600)),
            units_by_side={"blue": [], "red": []},
        )
        mgr.update_strategic(ctx, dt=3600.0)  # Should not raise

    def test_spawns_arriving_reinforcements(self, event_bus: EventBus) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        mgr.set_reinforcements([
            ReinforcementConfig(
                side="blue", arrival_time_s=100,
                units=[ReinforcementUnitConfig(unit_type="m1a2")],
            ),
        ])
        from stochastic_warfare.entities.loader import UnitLoader
        loader = UnitLoader(Path("data/units"))
        loader.load_all()
        ctx = _MockCtx(
            clock=_MockClock(elapsed=timedelta(seconds=200)),
            units_by_side={"blue": [], "red": []},
            unit_loader=loader,
        )
        mgr.update_strategic(ctx, dt=3600.0)
        assert len(ctx.units_by_side["blue"]) == 1


# ---------------------------------------------------------------------------
# Checkpoint / restore
# ---------------------------------------------------------------------------


class TestCheckpointRestore:
    """Campaign manager state persistence."""

    def test_get_state(self, event_bus: EventBus) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        mgr.set_reinforcements([
            ReinforcementConfig(
                side="blue", arrival_time_s=100,
                units=[ReinforcementUnitConfig(unit_type="m1a2")],
            ),
        ])
        state = mgr.get_state()
        assert len(state["reinforcements"]) == 1
        assert state["reinforcements"][0]["arrived"] is False

    def test_set_state_restores(self, event_bus: EventBus) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        mgr.set_reinforcements([
            ReinforcementConfig(
                side="blue", arrival_time_s=100,
                units=[ReinforcementUnitConfig(unit_type="m1a2")],
            ),
        ])
        state = mgr.get_state()
        state["reinforcements"][0]["arrived"] = True

        mgr2 = CampaignManager(event_bus, rng)
        mgr2.set_reinforcements([
            ReinforcementConfig(
                side="blue", arrival_time_s=100,
                units=[ReinforcementUnitConfig(unit_type="m1a2")],
            ),
        ])
        mgr2.set_state(state)
        s2 = mgr2.get_state()
        assert s2["reinforcements"][0]["arrived"] is True

    def test_round_trip(self, event_bus: EventBus) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        mgr.set_reinforcements([
            ReinforcementConfig(
                side="blue", arrival_time_s=3600,
                units=[ReinforcementUnitConfig(unit_type="m1a2")],
            ),
            ReinforcementConfig(
                side="red", arrival_time_s=7200,
                units=[ReinforcementUnitConfig(unit_type="m1a2", count=3)],
            ),
        ])
        state = mgr.get_state()
        mgr2 = CampaignManager(event_bus, rng)
        mgr2.set_reinforcements([
            ReinforcementConfig(
                side="blue", arrival_time_s=3600,
                units=[ReinforcementUnitConfig(unit_type="m1a2")],
            ),
            ReinforcementConfig(
                side="red", arrival_time_s=7200,
                units=[ReinforcementUnitConfig(unit_type="m1a2", count=3)],
            ),
        ])
        mgr2.set_state(state)
        assert len(mgr2.get_state()["reinforcements"]) == 2


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and error conditions."""

    def test_empty_reinforcement_schedule(self, event_bus: EventBus) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        mgr.set_reinforcements([])
        ctx = _MockCtx()
        units = mgr.check_reinforcements(ctx, 100.0)
        assert units == []

    def test_disabled_maintenance(self, event_bus: EventBus) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng, CampaignConfig(enable_maintenance=False))
        ctx = _MockCtx(
            clock=_MockClock(),
            units_by_side={"blue": [], "red": []},
        )
        mgr.update_strategic(ctx, dt=3600.0)  # Should not raise

    def test_disabled_supply_network(self, event_bus: EventBus) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng, CampaignConfig(enable_supply_network=False))
        ctx = _MockCtx(
            clock=_MockClock(),
            units_by_side={"blue": [], "red": []},
        )
        mgr.update_strategic(ctx, dt=3600.0)  # Should not raise
