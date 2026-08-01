"""Phase 63c: checkpoint owner-registry completeness tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.morale.runtime import MoraleRuntime
from stochastic_warfare.morale.rout import RoutEngine
from stochastic_warfare.simulation.scenario import (
    _CONTEXT_STATE_ENGINE_NAMES,
    CampaignScenarioConfig,
    SideConfig,
    SimulationContext,
    TerrainConfig,
)


@dataclass
class _StateOwner:
    """Minimal deterministic owner used through the real context boundary."""

    value: int

    def get_state(self) -> dict[str, int]:
        return {"value": self.value}

    def set_state(self, state: dict[str, Any]) -> None:
        if (
            not isinstance(state, dict)
            or set(state) != {"value"}
            or isinstance(state["value"], bool)
            or not isinstance(state["value"], int)
        ):
            raise ValueError("invalid test owner state")
        self.value = state["value"]


def _context(*, with_morale_runtime: bool = False) -> SimulationContext:
    config = CampaignScenarioConfig(
        name="Phase 63c checkpoint registry",
        date="2024-01-01T00:00:00Z",
        duration_hours=1.0,
        terrain=TerrainConfig(width_m=1_000.0, height_m=1_000.0),
        sides=[
            SideConfig(side="blue", units=[]),
            SideConfig(side="red", units=[]),
        ],
    )
    rng_manager = RNGManager(63)
    event_bus = EventBus()
    morale_runtime = None
    rout_engine = None
    if with_morale_runtime:
        morale_rng = rng_manager.get_stream(ModuleId.MORALE)
        rout_engine = RoutEngine(event_bus, morale_rng)
        morale_runtime = MoraleRuntime(
            event_bus,
            morale_rng,
            rout_engine=rout_engine,
        )
    return SimulationContext(
        config=config,
        clock=SimulationClock(
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            tick_duration=timedelta(seconds=5),
        ),
        rng_manager=rng_manager,
        event_bus=event_bus,
        units_by_side={"blue": [], "red": []},
        morale_states={},
        morale_runtime=morale_runtime,
        rout_engine=rout_engine,
    )


class TestCheckpointEngineList:
    """Verify capture and restore consume one runtime-visible owner registry."""

    @pytest.mark.parametrize(
        "owner_name",
        (
            "comms_engine",
            "detection_engine",
            "movement_engine",
            "conditions_engine",
            "weather_engine",
        ),
    )
    def test_registered_owner_is_visible_to_capture(
        self,
        owner_name: str,
    ) -> None:
        context = _context()
        owner = _StateOwner(7)
        setattr(context, owner_name, owner)

        runtime_owners = dict(context._checkpoint_engines())

        assert runtime_owners[owner_name] is owner
        assert context.get_state()[owner_name] == {"value": 7}

    def test_morale_runtime_uses_the_explicit_owned_boundary(self) -> None:
        context = _context(with_morale_runtime=True)

        checkpoint = context.get_state()

        assert context.morale_runtime is not None
        assert checkpoint["morale_runtime"] == context.morale_runtime.get_state()
        assert "morale_runtime" not in dict(context._checkpoint_engines())

    @pytest.mark.parametrize(
        "owner_name",
        ("comms_engine", "detection_engine"),
    )
    def test_registered_generic_owner_round_trips_through_context(
        self,
        owner_name: str,
    ) -> None:
        context = _context()
        owner = _StateOwner(11)
        setattr(context, owner_name, owner)
        checkpoint = context.get_state()
        owner.value = 99

        context.set_state(checkpoint)

        assert owner.value == 11
        assert context.get_state() == checkpoint

    def test_owner_without_state_api_is_skipped_behaviorally(self) -> None:
        context = _context()
        context.comms_engine = object()

        checkpoint = context.get_state()

        assert "comms_engine" not in checkpoint
        context.set_state(checkpoint)
        assert "comms_engine" not in context.get_state()

    def test_registry_is_unique_and_is_the_runtime_iteration_order(self) -> None:
        context = _context()
        runtime_names = tuple(
            name
            for name, _ in context._checkpoint_engines()
        )

        assert runtime_names == _CONTEXT_STATE_ENGINE_NAMES
        assert len(runtime_names) == len(set(runtime_names))
        assert len(runtime_names) >= 48
