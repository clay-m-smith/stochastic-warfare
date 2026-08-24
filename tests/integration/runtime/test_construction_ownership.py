"""Phase 112 production construction ownership proofs."""

from __future__ import annotations

import builtins
from pathlib import Path
from typing import Any

import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.simulation.scenario import ScenarioLoader


ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
EASTING_PATH = DATA_DIR / "scenarios" / "73_easting" / "scenario.yaml"


def test_scenario_loader_owns_terrain_and_morale_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A production load must not reach into the diagnostic runner."""
    original_import = builtins.__import__

    def guarded_import(
        name: str,
        globals: dict[str, Any] | None = None,
        locals: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == "stochastic_warfare.legacy.validation.scenario_runner":
            raise AssertionError(
                "production construction imported the diagnostic runner",
            )
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    context = ScenarioLoader(DATA_DIR).load(EASTING_PATH, seed=42)

    assert context.heightmap is not None
    assert context.heightmap.shape == (80, 120)
    assert context.heightmap.elevation_at(Position(25.0, 25.0)) == 200.0
    assert context.morale_runtime is not None
    assert context.morale_runtime.config.base_degrade_rate == pytest.approx(
        0.015,
    )
