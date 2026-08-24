"""Tests for the campaign manager (simulation.campaign).

Uses shared fixtures from conftest.py.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.entities.loader import MissingUnitDefinitionError
import stochastic_warfare.simulation.campaign as campaign_module
from stochastic_warfare.simulation.battle import BattleManager
from stochastic_warfare.simulation.campaign import (
    CampaignConfig,
    CampaignManager,
    ReinforcementEntry,
)
from stochastic_warfare.simulation.force_builder import RuntimeForceBuilder
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
    force_builder: Any = None
    ooda_engine: Any = None
    consumption_engine: Any = None
    stockpile_manager: Any = None
    supply_network_engine: Any = None
    maintenance_engine: Any = None
    config: Any = None
    era_runtime_contract: Any = field(
        default_factory=lambda: SimpleNamespace(
            era=SimpleNamespace(value="modern"),
        ),
    )

    def __post_init__(self) -> None:
        if self.clock is None:
            self.clock = _MockClock()
        if self.rng_manager is None:
            self.rng_manager = RNGManager(DEFAULT_SEED)
        if self.force_builder is None and self.unit_loader is not None:
            self.force_builder = RuntimeForceBuilder(
                unit_loader=self.unit_loader,
                rng=self.rng_manager.get_stream(ModuleId.ENTITIES),
            )

    def active_units(self, side: str) -> list[Unit]:
        return [u for u in self.units_by_side.get(side, []) if u.status == UnitStatus.ACTIVE]


@pytest.fixture(autouse=True)
def _commit_campaign_test_units(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep manager unit tests focused on scheduling, not loadout wiring."""

    def commit(ctx: _MockCtx, units: list[Unit]) -> None:
        for unit in units:
            side = unit.side if isinstance(unit.side, str) else unit.side.value
            ctx.units_by_side.setdefault(side, []).append(unit)

    monkeypatch.setattr(campaign_module, "register_dynamic_units", commit)


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
            side="blue",
            arrival_time_s=3600,
            units=[ReinforcementUnitConfig(unit_type="m1a2", count=2)],
        )
        entry = ReinforcementEntry(config=cfg)
        assert entry.arrived is False

    def test_arrived_flag(self) -> None:
        cfg = ReinforcementConfig(
            side="red",
            arrival_time_s=0,
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
                side="blue",
                arrival_time_s=3600,
                units=[ReinforcementUnitConfig(unit_type="m1a2", count=2)],
            ),
        ]
        mgr.set_reinforcements(reinforcements)
        state = mgr.get_state()
        assert len(state["reinforcements"]) == 1

    def test_same_schedule_is_idempotent_without_resampling(
        self,
        event_bus: EventBus,
    ) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        reinforcements = [
            ReinforcementConfig(
                side="blue",
                arrival_time_s=3600,
                arrival_sigma=0.3,
                units=[ReinforcementUnitConfig(unit_type="m1a2")],
            ),
        ]
        mgr.set_reinforcements(reinforcements)
        actual_arrival = mgr._reinforcements[0].actual_arrival_time_s
        rng_state = rng.bit_generator.state

        mgr.set_reinforcements(reinforcements)

        assert mgr._reinforcements[0].actual_arrival_time_s == actual_arrival
        assert rng.bit_generator.state == rng_state

    def test_different_second_schedule_is_rejected(
        self,
        event_bus: EventBus,
    ) -> None:
        mgr = CampaignManager(event_bus, make_rng())
        mgr.set_reinforcements(
            [
                ReinforcementConfig(
                    side="blue",
                    arrival_time_s=3600,
                    units=[ReinforcementUnitConfig(unit_type="m1a2")],
                ),
            ]
        )

        with pytest.raises(
            ValueError,
            match="already initialized with different topology",
        ):
            mgr.set_reinforcements(
                [
                    ReinforcementConfig(
                        side="blue",
                        arrival_time_s=7200,
                        units=[ReinforcementUnitConfig(unit_type="m1a2")],
                    ),
                ]
            )

    def test_failed_schedule_sampling_restores_rng(
        self,
        event_bus: EventBus,
    ) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        before_rng = copy.deepcopy(rng.bit_generator.state)
        invalid_sample = ReinforcementConfig(
            side="blue",
            arrival_time_s=1.79e308,
            arrival_sigma=0.3,
            units=[ReinforcementUnitConfig(unit_type="m1a2")],
        )

        with pytest.raises(ValueError, match="non-finite"):
            mgr.set_reinforcements([invalid_sample])

        assert mgr._reinforcements == []
        assert mgr._schedule_signature is None
        assert rng.bit_generator.state == before_rng

    def test_reinforcements_not_arrived_before_time(self, event_bus: EventBus) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        mgr.set_reinforcements(
            [
                ReinforcementConfig(
                    side="blue",
                    arrival_time_s=7200,
                    units=[ReinforcementUnitConfig(unit_type="m1a2")],
                ),
            ]
        )
        ctx = _MockCtx(clock=_MockClock(elapsed=timedelta(seconds=3600)))
        new_units = mgr.check_reinforcements(ctx, 3600.0)
        assert len(new_units) == 0

    def test_reinforcements_arrive_at_time(self, event_bus: EventBus) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        mgr.set_reinforcements(
            [
                ReinforcementConfig(
                    side="blue",
                    arrival_time_s=3600,
                    units=[ReinforcementUnitConfig(unit_type="m1a2")],
                    position=[100, 200],
                ),
            ]
        )
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
        mgr.set_reinforcements(
            [
                ReinforcementConfig(
                    side="blue",
                    arrival_time_s=0,
                    units=[ReinforcementUnitConfig(unit_type="m1a2")],
                ),
            ]
        )
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
        mgr.set_reinforcements(
            [
                ReinforcementConfig(
                    side="blue",
                    arrival_time_s=100,
                    units=[ReinforcementUnitConfig(unit_type="m1a2", count=2)],
                ),
                ReinforcementConfig(
                    side="red",
                    arrival_time_s=200,
                    units=[ReinforcementUnitConfig(unit_type="m1a2", count=3)],
                ),
            ]
        )
        from stochastic_warfare.entities.loader import UnitLoader

        loader = UnitLoader(Path("data/units"))
        loader.load_all()
        ctx = _MockCtx(unit_loader=loader)
        units1 = mgr.check_reinforcements(ctx, 150.0)
        assert len(units1) == 2  # Only first batch
        units2 = mgr.check_reinforcements(ctx, 250.0)
        assert len(units2) == 3  # Second batch

    def test_no_loader_fails_and_remains_pending(
        self,
        event_bus: EventBus,
    ) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        mgr.set_reinforcements(
            [
                ReinforcementConfig(
                    side="blue",
                    arrival_time_s=0,
                    units=[ReinforcementUnitConfig(unit_type="m1a2")],
                ),
            ]
        )
        ctx = _MockCtx(unit_loader=None)
        with pytest.raises(RuntimeError, match="RuntimeForceBuilder"):
            mgr.check_reinforcements(ctx, 100.0)
        assert mgr._reinforcements[0].arrived is False

    def test_unknown_unit_type_fails_and_remains_pending(
        self,
        event_bus: EventBus,
    ) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        mgr.set_reinforcements(
            [
                ReinforcementConfig(
                    side="blue",
                    arrival_time_s=0,
                    units=[ReinforcementUnitConfig(unit_type="nonexistent_tank")],
                ),
            ]
        )
        from stochastic_warfare.entities.loader import UnitLoader

        loader = UnitLoader(Path("data/units"))
        loader.load_all()
        ctx = _MockCtx(unit_loader=loader)
        with pytest.raises(
            MissingUnitDefinitionError,
            match="nonexistent_tank",
        ):
            mgr.check_reinforcements(ctx, 100.0)
        assert mgr._reinforcements[0].arrived is False

    def test_failed_wave_restores_entities_rng(
        self,
        event_bus: EventBus,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mgr = CampaignManager(event_bus, make_rng())
        mgr.set_reinforcements(
            [
                ReinforcementConfig(
                    side="blue",
                    arrival_time_s=0,
                    units=[
                        ReinforcementUnitConfig(
                            unit_type="m1a2",
                            count=2,
                        ),
                    ],
                ),
            ]
        )
        from stochastic_warfare.entities.loader import UnitLoader

        loader = UnitLoader(Path("data/units"))
        loader.load_all()
        original_create = loader.create_unit
        calls = 0

        def fail_second(*args: Any, **kwargs: Any) -> Unit:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("injected unit construction failure")
            return original_create(*args, **kwargs)

        monkeypatch.setattr(loader, "create_unit", fail_second)
        ctx = _MockCtx(unit_loader=loader)
        entities_rng = ctx.rng_manager.get_stream(ModuleId.ENTITIES)
        before_rng = copy.deepcopy(entities_rng.bit_generator.state)

        with pytest.raises(
            RuntimeError,
            match="injected unit construction failure",
        ):
            mgr.check_reinforcements(ctx, 100.0)

        assert entities_rng.bit_generator.state == before_rng
        assert mgr._reinforcements[0].arrived is False
        assert ctx.units_by_side == {}

    def test_reinforcement_position_applied(self, event_bus: EventBus) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        mgr.set_reinforcements(
            [
                ReinforcementConfig(
                    side="blue",
                    arrival_time_s=0,
                    units=[ReinforcementUnitConfig(unit_type="m1a2")],
                    position=[500, 1000],
                ),
            ]
        )
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
        assert battles[0].start_time == ctx.clock.current_time

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

    @pytest.mark.test_evidence("invariant_only")
    def test_runs_without_error(self, event_bus: EventBus) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        ctx = _MockCtx(
            clock=_MockClock(elapsed=timedelta(seconds=3600)),
            units_by_side={"blue": [], "red": []},
        )
        mgr.update_strategic(ctx, dt=3600.0)  # Should not raise

    def test_reinforcement_check_is_owned_by_engine(
        self,
        event_bus: EventBus,
    ) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        mgr.set_reinforcements(
            [
                ReinforcementConfig(
                    side="blue",
                    arrival_time_s=100,
                    units=[ReinforcementUnitConfig(unit_type="m1a2")],
                ),
            ]
        )
        from stochastic_warfare.entities.loader import UnitLoader

        loader = UnitLoader(Path("data/units"))
        loader.load_all()
        ctx = _MockCtx(
            clock=_MockClock(elapsed=timedelta(seconds=200)),
            units_by_side={"blue": [], "red": []},
            unit_loader=loader,
        )
        mgr.update_strategic(ctx, dt=3600.0)
        assert ctx.units_by_side["blue"] == []
        assert mgr._reinforcements[0].arrived is False

        mgr.check_reinforcements(ctx, elapsed_s=200.0)
        assert len(ctx.units_by_side["blue"]) == 1


# ---------------------------------------------------------------------------
# Checkpoint / restore
# ---------------------------------------------------------------------------


class TestCheckpointRestore:
    """Campaign manager state persistence."""

    def test_get_state(self, event_bus: EventBus) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        mgr.set_reinforcements(
            [
                ReinforcementConfig(
                    side="blue",
                    arrival_time_s=100,
                    units=[ReinforcementUnitConfig(unit_type="m1a2")],
                ),
            ]
        )
        state = mgr.get_state()
        assert len(state["reinforcements"]) == 1
        assert state["reinforcements"][0]["arrived"] is False

    def test_set_state_restores(self, event_bus: EventBus) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        mgr.set_reinforcements(
            [
                ReinforcementConfig(
                    side="blue",
                    arrival_time_s=100,
                    units=[ReinforcementUnitConfig(unit_type="m1a2")],
                ),
            ]
        )
        state = mgr.get_state()
        state["reinforcements"][0]["arrived"] = True

        mgr2 = CampaignManager(event_bus, rng)
        mgr2.set_reinforcements(
            [
                ReinforcementConfig(
                    side="blue",
                    arrival_time_s=100,
                    units=[ReinforcementUnitConfig(unit_type="m1a2")],
                ),
            ]
        )
        mgr2.set_state(state)
        s2 = mgr2.get_state()
        assert s2["reinforcements"][0]["arrived"] is True

    def test_round_trip(self, event_bus: EventBus) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng)
        mgr.set_reinforcements(
            [
                ReinforcementConfig(
                    side="blue",
                    arrival_time_s=3600,
                    units=[ReinforcementUnitConfig(unit_type="m1a2")],
                ),
                ReinforcementConfig(
                    side="red",
                    arrival_time_s=7200,
                    units=[ReinforcementUnitConfig(unit_type="m1a2", count=3)],
                ),
            ]
        )
        state = mgr.get_state()
        mgr2 = CampaignManager(event_bus, rng)
        mgr2.set_reinforcements(
            [
                ReinforcementConfig(
                    side="blue",
                    arrival_time_s=3600,
                    units=[ReinforcementUnitConfig(unit_type="m1a2")],
                ),
                ReinforcementConfig(
                    side="red",
                    arrival_time_s=7200,
                    units=[ReinforcementUnitConfig(unit_type="m1a2", count=3)],
                ),
            ]
        )
        mgr2.set_state(state)
        assert len(mgr2.get_state()["reinforcements"]) == 2

    def test_set_state_topology_failure_is_atomic(
        self,
        event_bus: EventBus,
    ) -> None:
        reinforcements = [
            ReinforcementConfig(
                side="blue",
                arrival_time_s=3600,
                units=[ReinforcementUnitConfig(unit_type="m1a2")],
            ),
            ReinforcementConfig(
                side="red",
                arrival_time_s=7200,
                units=[ReinforcementUnitConfig(unit_type="m1a2")],
            ),
        ]
        mgr = CampaignManager(event_bus, make_rng())
        mgr.set_reinforcements(reinforcements)
        before = mgr.get_state()
        invalid = mgr.get_state()
        invalid["reinforcements"][0]["arrived"] = True
        invalid["reinforcements"][1]["config"]["side"] = "blue"

        with pytest.raises(
            ValueError,
            match="configuration differs",
        ):
            mgr.set_state(invalid)

        assert mgr.get_state() == before

    def test_arrived_constituent_may_be_stored_in_aggregate(
        self,
        event_bus: EventBus,
    ) -> None:
        mgr = CampaignManager(event_bus, make_rng())
        mgr.set_reinforcements(
            [
                ReinforcementConfig(
                    side="blue",
                    arrival_time_s=100.0,
                    units=[
                        ReinforcementUnitConfig(
                            unit_type="m1a2",
                        ),
                    ],
                ),
            ],
        )
        campaign_state = mgr.get_state()
        campaign_state["reinforcements"][0]["arrived"] = True
        context_state = {
            "units_by_side": {"blue": [], "red": []},
            "aggregation_engine": {
                "aggregates": {
                    "agg_0000": {
                        "snapshots": [
                            {
                                "original_side": "blue",
                                "unit_state": {
                                    "entity_id": ("reinforce_blue_0000_m1a2_0000"),
                                    "unit_type": "m1a2",
                                },
                            },
                        ],
                    },
                },
            },
        }

        mgr.validate_checkpoint_roster(
            campaign_state,
            context_state,
        )
        plan = mgr.stage_state(campaign_state)
        mgr.validate_checkpoint_roster(
            campaign_state,
            context_state,
            staged_plan=plan,
        )
        mgr.commit_state(plan)
        assert mgr.get_state()["reinforcements"][0]["arrived"] is True


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

    def test_disabled_maintenance_update_is_explicit_no_op(
        self,
        event_bus: EventBus,
    ) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng, CampaignConfig(enable_maintenance=False))
        ctx = _MockCtx(
            clock=_MockClock(),
            units_by_side={"blue": [], "red": []},
        )
        before = mgr.get_state()
        mgr.update_strategic(ctx, dt=3600.0)
        assert mgr.get_state() == before

    def test_disabled_supply_update_is_explicit_no_op(
        self,
        event_bus: EventBus,
    ) -> None:
        rng = make_rng()
        mgr = CampaignManager(event_bus, rng, CampaignConfig(enable_supply_network=False))
        ctx = _MockCtx(
            clock=_MockClock(),
            units_by_side={"blue": [], "red": []},
        )
        before = mgr.get_state()
        mgr.update_strategic(ctx, dt=3600.0)
        assert mgr.get_state() == before
