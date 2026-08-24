"""Behavioral checkpoint-owner registration contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from types import SimpleNamespace

import pytest

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    SideConfig,
    SimulationContext,
    TerrainConfig,
)
from stochastic_warfare.simulation.tactical_targeting import (
    TacticalTargetingRuntime,
)


@dataclass
class _LegacyOwner:
    """Minimal clone-safe legacy checkpoint owner."""

    state: dict[str, Any] = field(default_factory=dict)

    def get_state(self) -> dict[str, Any]:
        return dict(self.state)

    def set_state(self, state: dict[str, Any]) -> None:
        self.state = dict(state)


def _context() -> SimulationContext:
    config = CampaignScenarioConfig(
        name="checkpoint owner registration test",
        date="2024-01-01T00:00:00Z",
        duration_hours=24.0,
        terrain=TerrainConfig(width_m=1_000, height_m=1_000),
        sides=(
            SideConfig(side="blue", units=[]),
            SideConfig(side="red", units=[]),
        ),
    )
    return SimulationContext(
        config=config,
        clock=SimulationClock(
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            tick_duration=timedelta(seconds=5),
        ),
        rng_manager=RNGManager(72),
        event_bus=EventBus(),
        tactical_targeting=TacticalTargetingRuntime(
            sensing_aware_standoff_enabled=(
                config.calibration_overrides.enable_sensing_aware_standoff
            ),
            unit_sides={},
        ),
        calibration=config.calibration_overrides,
    )


def test_capture_delegates_to_registered_checkpoint_owner() -> None:
    context = _context()
    owner_state = {"missiles_in_flight": [{"id": "m1", "pos": [0, 0]}]}
    context.missile_engine = SimpleNamespace(
        get_state=lambda: owner_state,
        set_state=lambda _state: None,
    )

    state = context.get_state()

    assert state["missile_engine"] == owner_state


def test_restore_delegates_to_registered_checkpoint_owner() -> None:
    context = _context()
    owner = _LegacyOwner()
    context.roe_engine = owner
    state = context.get_state()
    state["roe_engine"] = {"level": "WEAPONS_FREE"}

    context.set_state(state)

    assert owner.state == {"level": "WEAPONS_FREE"}


def test_registered_legacy_owner_without_restore_protocol_fails_closed() -> None:
    context = _context()
    context.comms_engine = SimpleNamespace(get_state=lambda: {})

    with pytest.raises(
        TypeError,
        match="classified legacy_clone.*lacks get_state/set_state",
    ):
        context.get_state()
