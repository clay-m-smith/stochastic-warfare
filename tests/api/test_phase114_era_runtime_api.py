"""Phase 114 API proof for effective era cadence and provenance."""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from typing import Any

import pytest

import stochastic_warfare.core.era as era_module
from api.database import Database
from api.run_manager import RunManager
from stochastic_warfare.core.era import EraConfig, register_era_config
from stochastic_warfare.simulation.scenario import CampaignScenarioConfig


pytestmark = [pytest.mark.api, pytest.mark.asyncio]

_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _ROOT / "data"
_SEED = 114
_MAX_TICKS = 2_000
_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


@pytest.fixture(autouse=True)
def _isolate_era_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        era_module,
        "_ERA_REGISTRY",
        copy.deepcopy(era_module._ERA_REGISTRY),
    )


def _scenario_config(era_id: str) -> CampaignScenarioConfig:
    """Return an inline scenario whose only variant input is the era ID."""
    return CampaignScenarioConfig.model_validate(
        {
            "name": "Phase 114 API era runtime",
            "date": "2024-01-01T00:00:00Z",
            # The 1,200-second authored duration makes the default frame
            # interval observably differ for 1s and 2s strategic contracts.
            "duration_hours": 1.0 / 3.0,
            "era": era_id,
            "tick_resolution": {
                "strategic_s": 13.0,
                "operational_s": 7.0,
                "tactical_s": 3.0,
            },
            "terrain": {
                "width_m": 50_000.0,
                "height_m": 2_000.0,
                "cell_size_m": 100.0,
                "terrain_type": "flat_desert",
            },
            "deployment": {"mode": "manual"},
            "sides": [
                {
                    "side": "blue",
                    "units": [
                        {
                            "unit_type": "m1a2",
                            "count": 1,
                            "position": [1_000.0, 1_000.0, 0.0],
                        },
                    ],
                },
                {
                    "side": "red",
                    "units": [
                        {
                            "unit_type": "t72m",
                            "count": 1,
                            "position": [41_000.0, 1_000.0, 0.0],
                        },
                    ],
                },
            ],
            "objectives": [],
            "victory_conditions": [
                {
                    "type": "time_expired",
                    "params": {"max_duration_s": 5.0},
                },
            ],
        },
    )


async def _wait_for_terminal_row(
    database: Database,
    run_id: str,
) -> dict[str, Any]:
    for _ in range(1_000):
        row = await database.get_run(run_id)
        assert row is not None
        if row["status"] in _TERMINAL_STATUSES:
            return row
        await asyncio.sleep(0.01)
    raise AssertionError(f"API run {run_id} did not reach terminal state")


async def test_api_result_exposes_effective_era_behavior_and_fingerprint(
    tmp_path: Path,
) -> None:
    one_second_era = "phase114-api-one-second"
    two_second_era = "phase114-api-two-second"
    register_era_config(
        one_second_era,
        EraConfig(tick_resolution_overrides={"strategic_s": 1.0}),
    )
    register_era_config(
        two_second_era,
        EraConfig(tick_resolution_overrides={"strategic_s": 2.0}),
    )
    one_second_config = _scenario_config(one_second_era)
    two_second_config = _scenario_config(two_second_era)
    one_second_payload = one_second_config.model_dump(mode="json")
    two_second_payload = two_second_config.model_dump(mode="json")
    assert one_second_payload.pop("era") == one_second_era
    assert two_second_payload.pop("era") == two_second_era
    assert one_second_payload == two_second_payload

    database = Database(str(tmp_path / "phase114-era-runtime.db"))
    await database.initialize()
    manager = RunManager(
        database,
        data_dir=str(_DATA_DIR),
        max_concurrent=2,
    )
    try:
        one_second_id = await manager.submit_config(
            "phase114-api-one-second",
            one_second_config,
            seed=_SEED,
            max_ticks=_MAX_TICKS,
        )
        two_second_id = await manager.submit_config(
            "phase114-api-two-second",
            two_second_config,
            seed=_SEED,
            max_ticks=_MAX_TICKS,
        )
        one_second_row, two_second_row = await asyncio.gather(
            _wait_for_terminal_row(database, one_second_id),
            _wait_for_terminal_row(database, two_second_id),
        )

        assert one_second_row["status"] == "completed"
        assert two_second_row["status"] == "completed"
        one_second_result = json.loads(one_second_row["result_json"])
        two_second_result = json.loads(two_second_row["result_json"])

        assert one_second_result["duration_s"] == 5.0
        assert one_second_result["ticks_executed"] == 5
        assert two_second_result["duration_s"] == 6.0
        assert two_second_result["ticks_executed"] == 3
        assert (
            one_second_result["config_fingerprint"]
            != two_second_result["config_fingerprint"]
        )

        one_second_frames = json.loads(one_second_row["frames_json"])
        two_second_frames = json.loads(two_second_row["frames_json"])
        # The default interval is derived from the effective strategic
        # cadence: 1,200 expected ticks gives interval 2, while 600 gives 1.
        assert [frame["tick"] for frame in one_second_frames] == [2, 4, 5]
        assert [frame["tick"] for frame in two_second_frames] == [1, 2, 3]
    finally:
        await manager.shutdown()
        await database.close()
