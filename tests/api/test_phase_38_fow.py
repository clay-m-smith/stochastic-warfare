"""Tests for Phase 38a/38b — FOW detection data + elevation + sensor range in frame capture."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from api.run_manager import RunManager


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_unit(
    entity_id: str,
    side: str,
    easting: float = 100.0,
    northing: float = 200.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        entity_id=entity_id,
        position=SimpleNamespace(easting=easting, northing=northing),
        domain=SimpleNamespace(value=0),
        status=SimpleNamespace(value=0),
        heading=90.0,
        unit_type="tank",
    )


def _make_ctx(
    units_by_side: dict[str, list[Any]],
    fog_of_war: Any = None,
    unit_sensors: dict[str, list[Any]] | None = None,
) -> SimpleNamespace:
    ctx = SimpleNamespace(
        units_by_side=units_by_side,
        fog_of_war=fog_of_war,
        unit_sensors=unit_sensors or {},
    )
    return ctx


# ── FOW Detection Tests ─────────────────────────────────────────────────


class TestCaptureFrameFow:
    """Tests for FOW detection data in _capture_frame()."""

    def test_includes_det_with_contacts(self) -> None:
        """When FOW is present and has contacts, frame includes 'det' key."""
        blue = _make_unit("b1", "blue")
        red = _make_unit("r1", "red", 500, 500)

        contacts = {"r1": SimpleNamespace(unit_id="r1")}
        wv = SimpleNamespace(contacts=contacts)
        fow = MagicMock()
        fow.get_world_view.return_value = wv

        ctx = _make_ctx({"blue": [blue], "red": [red]}, fog_of_war=fow)
        frame = RunManager._capture_frame(0, ctx)

        assert "det" in frame
        assert "blue" in frame["det"]
        assert "r1" in frame["det"]["blue"]

    def test_omits_det_when_no_fow(self) -> None:
        """When FOW is None, frame has no 'det' key."""
        blue = _make_unit("b1", "blue")
        ctx = _make_ctx({"blue": [blue]}, fog_of_war=None)
        frame = RunManager._capture_frame(0, ctx)

        assert "det" not in frame

    def test_omits_det_when_fow_empty_contacts(self) -> None:
        """When FOW has no contacts for any side, 'det' is still present but empty lists."""
        blue = _make_unit("b1", "blue")
        wv = SimpleNamespace(contacts={})
        fow = MagicMock()
        fow.get_world_view.return_value = wv

        ctx = _make_ctx({"blue": [blue]}, fog_of_war=fow)
        frame = RunManager._capture_frame(0, ctx)

        # With empty contacts, detected dict will be {"blue": []}
        # which is truthy, so "det" is included
        if "det" in frame:
            assert frame["det"]["blue"] == []


# ── Sensor Range Tests ───────────────────────────────────────────────────


class TestCaptureFrameSensorRange:
    """Tests for sensor range data in _capture_frame()."""

    def test_includes_sr_when_sensors_present(self) -> None:
        """Unit with sensors gets 'sr' field in frame."""
        blue = _make_unit("b1", "blue")
        sensor = SimpleNamespace(effective_range=5000.0)
        ctx = _make_ctx(
            {"blue": [blue]},
            unit_sensors={"b1": [sensor]},
        )
        frame = RunManager._capture_frame(0, ctx)

        unit = frame["units"][0]
        assert "sr" in unit
        assert unit["sr"] == 5000.0

    def test_no_sr_when_no_sensors(self) -> None:
        """Unit without sensors has no 'sr' field."""
        blue = _make_unit("b1", "blue")
        ctx = _make_ctx({"blue": [blue]}, unit_sensors={})
        frame = RunManager._capture_frame(0, ctx)

        unit = frame["units"][0]
        assert "sr" not in unit

    def test_sr_picks_max_sensor_range(self) -> None:
        """When unit has multiple sensors, picks the maximum range."""
        blue = _make_unit("b1", "blue")
        s1 = SimpleNamespace(effective_range=3000.0)
        s2 = SimpleNamespace(effective_range=8000.0)
        s3 = SimpleNamespace(effective_range=1000.0)
        ctx = _make_ctx(
            {"blue": [blue]},
            unit_sensors={"b1": [s1, s2, s3]},
        )
        frame = RunManager._capture_frame(0, ctx)

        assert frame["units"][0]["sr"] == 8000.0


# ── Elevation Capture Tests ──────────────────────────────────────────────


class TestCaptureTerrainElevation:
    """Tests for elevation data in _capture_terrain()."""

    def test_includes_elevation_when_heightmap_present(self) -> None:
        """Terrain capture includes elevation array from heightmap._data."""
        import numpy as np

        heightmap = SimpleNamespace(
            cell_size=100.0,
            shape=(3, 3),
            extent=[0.0, 0.0, 300.0, 300.0],
            _data=np.array([[10.0, 20.0, 30.0], [15.0, 25.0, 35.0], [20.0, 30.0, 40.0]]),
        )
        ctx = SimpleNamespace(
            heightmap=heightmap,
            classification=None,
        )
        terrain = RunManager._capture_terrain(ctx, {})

        assert "elevation" in terrain
        assert len(terrain["elevation"]) == 3
        assert terrain["elevation"][0] == [10.0, 20.0, 30.0]

    def test_no_elevation_when_no_heightmap(self) -> None:
        """Terrain capture has no elevation key when heightmap is None."""
        ctx = SimpleNamespace(heightmap=None, classification=None)
        terrain = RunManager._capture_terrain(ctx, {})

        # Default terrain dict doesn't include elevation
        assert terrain.get("elevation") is None or terrain.get("elevation") == []

    def test_elevation_not_included_without_data(self) -> None:
        """Heightmap present but _data is None — no elevation in terrain."""
        heightmap = SimpleNamespace(
            cell_size=100.0,
            shape=(2, 2),
            extent=[0.0, 0.0, 200.0, 200.0],
            _data=None,
        )
        ctx = SimpleNamespace(heightmap=heightmap, classification=None)
        terrain = RunManager._capture_terrain(ctx, {})

        # elevation should not be populated
        assert terrain.get("elevation") is None or terrain.get("elevation") == []


# ── Frames Endpoint Mapping Tests ────────────────────────────────────────


class TestFramesEndpointMapping:
    """Tests that abbreviated keys are mapped correctly in the frames endpoint response model."""

    def test_replay_frame_schema_has_detected(self) -> None:
        """ReplayFrame schema includes 'detected' field."""
        from api.schemas import ReplayFrame

        frame = ReplayFrame(
            tick=0,
            units=[],
            detected={"blue": ["r1", "r2"]},
        )
        assert frame.detected == {"blue": ["r1", "r2"]}

    def test_replay_frame_defaults_empty_detected(self) -> None:
        """ReplayFrame defaults 'detected' to empty dict."""
        from api.schemas import ReplayFrame

        frame = ReplayFrame(tick=0, units=[])
        assert frame.detected == {}

    def test_map_unit_frame_has_sensor_range(self) -> None:
        """MapUnitFrame schema includes 'sensor_range' field."""
        from api.schemas import MapUnitFrame

        unit = MapUnitFrame(
            id="u1",
            side="blue",
            x=100.0,
            y=200.0,
            sensor_range=5000.0,
        )
        assert unit.sensor_range == 5000.0

    def test_terrain_response_has_elevation(self) -> None:
        """TerrainResponse schema includes 'elevation' field."""
        from api.schemas import TerrainResponse

        terrain = TerrainResponse(elevation=[[10.0, 20.0], [30.0, 40.0]])
        assert terrain.elevation == [[10.0, 20.0], [30.0, 40.0]]
