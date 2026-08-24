"""Inline API rejection proof for retired Phase 118 model controls.

The former observer-support production acceptance test enabled scan scheduling
and LOD together.  Those controls failed the retained semantic evaluation and
are now unsupported production inputs; lower-level observer-support behavior
remains covered without presenting either control as deployable.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
import pytest


pytestmark = [pytest.mark.api, pytest.mark.asyncio]


def _inline_config(retired_flag: str) -> dict[str, object]:
    return {
        "name": "Phase 118 retired-control rejection",
        "date": "2025-01-01",
        "duration_hours": 1.0,
        "terrain": {
            "width_m": 5_000,
            "height_m": 5_000,
            "cell_size_m": 100,
        },
        "sides": [
            {
                "side": "blue",
                "units": [{"unit_type": "m1a2", "count": 1}],
            },
            {
                "side": "red",
                "units": [{"unit_type": "t72m", "count": 1}],
            },
        ],
        "calibration_overrides": {
            "enable_scan_scheduling": retired_flag == "enable_scan_scheduling",
            "enable_lod": retired_flag == "enable_lod",
        },
    }


@pytest.mark.parametrize(
    "retired_flag",
    ("enable_scan_scheduling", "enable_lod"),
)
async def test_inline_run_rejects_retired_control_without_persisting(
    client: AsyncClient,
    app: Any,
    retired_flag: str,
) -> None:
    before_count = await app.state.db.count_runs()

    response = await client.post(
        "/api/runs/from-config",
        json={
            "config": _inline_config(retired_flag),
            "seed": 118,
            "max_ticks": 1,
        },
    )

    assert response.status_code == 422
    assert retired_flag in response.text
    assert "unsupported" in response.text.lower()
    assert await app.state.db.count_runs() == before_count
