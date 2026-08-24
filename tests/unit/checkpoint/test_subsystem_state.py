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
from stochastic_warfare.detection.detection import DetectionEngine
from stochastic_warfare.morale.runtime import MoraleRuntime
from stochastic_warfare.morale.rout import RoutEngine
from stochastic_warfare.simulation.context_checkpoint import (
    CheckpointOwnerDisposition,
    _LEGACY_CONTEXT_CHECKPOINT_OWNER_NAMES,
    _STATELESS_CONTEXT_CHECKPOINT_OWNER_NAMES,
    _TYPED_CONTEXT_CHECKPOINT_OWNER_NAMES,
)
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

    def test_registered_stateless_owner_is_explicitly_not_captured(self) -> None:
        context = _context()
        context.movement_engine = object()

        assert "movement_engine" not in context.get_state()

    def test_morale_runtime_uses_the_explicit_owned_boundary(self) -> None:
        context = _context(with_morale_runtime=True)

        checkpoint = context.get_state()

        assert context.morale_runtime is not None
        assert checkpoint["morale_runtime"] == context.morale_runtime.get_state()
        assert "morale_runtime" not in dict(context._checkpoint_engines())

    @pytest.mark.parametrize(
        "owner_name",
        ("comms_engine",),
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

    def test_detection_owner_is_not_a_generic_checkpoint_proxy(self) -> None:
        context = _context()
        context.detection_engine = _StateOwner(11)

        with pytest.raises(ValueError, match="exact DetectionEngine"):
            context.get_state()

    def test_exact_detection_owner_round_trips_with_rng_manager(self) -> None:
        context = _context()
        detection_rng = context.rng_manager.get_stream(ModuleId.DETECTION)
        context.detection_engine = DetectionEngine(rng=detection_rng)
        checkpoint = context.get_state()
        detection_rng.random()

        context.set_state(checkpoint)

        assert context.get_state() == checkpoint

    def test_legacy_owner_without_state_api_fails_closed(self) -> None:
        context = _context()
        context.comms_engine = object()

        with pytest.raises(
            TypeError,
            match="classified legacy_clone.*lacks get_state/set_state",
        ):
            context.get_state()

    def test_registry_is_unique_and_is_the_runtime_iteration_order(self) -> None:
        context = _context()
        runtime_names = tuple(
            name
            for name, _ in context._checkpoint_engines()
        )

        assert runtime_names == _CONTEXT_STATE_ENGINE_NAMES
        assert len(runtime_names) == len(set(runtime_names))
        assert len(runtime_names) >= 48

    @pytest.mark.test_evidence("structural_only")
    def test_every_registered_owner_has_one_explicit_disposition(self) -> None:
        classified = (
            set(_LEGACY_CONTEXT_CHECKPOINT_OWNER_NAMES)
            | _STATELESS_CONTEXT_CHECKPOINT_OWNER_NAMES
            | _TYPED_CONTEXT_CHECKPOINT_OWNER_NAMES
        )

        assert classified == set(_CONTEXT_STATE_ENGINE_NAMES)
        assert not (
            set(_LEGACY_CONTEXT_CHECKPOINT_OWNER_NAMES)
            & _TYPED_CONTEXT_CHECKPOINT_OWNER_NAMES
        )
        context = _context()
        dispositions = {
            binding.name: binding.disposition
            for binding in context._checkpoint_owner_bindings()
        }
        assert dispositions["movement_engine"] is CheckpointOwnerDisposition.STATELESS
        assert dispositions["ooda_engine"] is CheckpointOwnerDisposition.TYPED_ATOMIC
        assert dispositions["comms_engine"] is CheckpointOwnerDisposition.LEGACY_CLONE

    def test_invalid_later_legacy_owner_leaves_all_live_owners_unchanged(
        self,
    ) -> None:
        context = _context()
        first = _StateOwner(11)
        later = _StateOwner(22)
        context.comms_engine = first
        context.roe_engine = later
        checkpoint = context.get_state()
        first.value = 101
        later.value = 202
        checkpoint["roe_engine"] = {"value": True}

        with pytest.raises(ValueError, match="Invalid checkpoint roe_engine"):
            context.set_state(checkpoint)

        assert first.value == 101
        assert later.value == 202
