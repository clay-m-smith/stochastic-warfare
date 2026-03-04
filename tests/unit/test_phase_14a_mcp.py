"""Tests for Phase 14a: serializers, result_store, and MCP tool functions."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import IntEnum
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.tools.serializers import (
    make_error,
    make_success,
    serialize,
    serialize_to_dict,
)
from stochastic_warfare.tools.result_store import ResultStore, StoredResult
from stochastic_warfare.tools.mcp_resources import (
    get_scenario_config,
    get_unit_definition,
    get_cached_result,
)


# ============================================================================
# Serializer tests
# ============================================================================


class _TestEnum(IntEnum):
    FOO = 0
    BAR = 1


@dataclass(frozen=True)
class _FakeResult:
    game_over: bool
    winning_side: str
    condition_type: str
    tick: int


class TestSerializers:
    """Serialization of simulation objects to JSON."""

    def test_numpy_int(self) -> None:
        result = serialize_to_dict(np.int64(42))
        assert result == 42
        assert isinstance(result, int)

    def test_numpy_float(self) -> None:
        result = serialize_to_dict(np.float64(3.14))
        assert abs(result - 3.14) < 1e-10
        assert isinstance(result, float)

    def test_numpy_bool(self) -> None:
        result = serialize_to_dict(np.bool_(True))
        assert result is True
        assert isinstance(result, bool)

    def test_numpy_array(self) -> None:
        arr = np.array([1.0, 2.0, 3.0])
        result = serialize_to_dict(arr)
        assert result == [1.0, 2.0, 3.0]

    def test_nan_becomes_none(self) -> None:
        result = serialize_to_dict(float("nan"))
        assert result is None

    def test_inf_becomes_string(self) -> None:
        result = serialize_to_dict(float("inf"))
        assert result == "Infinity"
        result_neg = serialize_to_dict(float("-inf"))
        assert result_neg == "-Infinity"

    def test_numpy_nan(self) -> None:
        result = serialize_to_dict(np.float64("nan"))
        assert result is None

    def test_numpy_inf(self) -> None:
        result = serialize_to_dict(np.float64("inf"))
        assert result == "Infinity"

    def test_datetime(self) -> None:
        dt = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        result = serialize_to_dict(dt)
        assert "2024-06-15" in result

    def test_enum(self) -> None:
        result = serialize_to_dict(_TestEnum.BAR)
        assert result == "BAR"

    def test_position(self) -> None:
        pos = Position(easting=100.0, northing=200.0, altitude=50.0)
        result = serialize_to_dict(pos)
        assert result == {"easting": 100.0, "northing": 200.0, "altitude": 50.0}

    def test_dataclass(self) -> None:
        vr = _FakeResult(game_over=True, winning_side="blue", condition_type="force_destroyed", tick=100)
        result = serialize_to_dict(vr)
        assert result["game_over"] is True
        assert result["winning_side"] == "blue"
        assert result["tick"] == 100

    def test_nested_dict(self) -> None:
        data = {"sides": {"blue": {"units": 4}}, "array": np.array([1, 2])}
        result = serialize_to_dict(data)
        assert result["sides"]["blue"]["units"] == 4
        assert result["array"] == [1, 2]

    def test_serialize_roundtrip_json(self) -> None:
        data = {"value": np.float64(1.5), "pos": Position(1.0, 2.0, 3.0)}
        json_str = serialize(data)
        parsed = json.loads(json_str)
        assert parsed["value"] == 1.5
        assert parsed["pos"]["easting"] == 1.0

    def test_set_serialization(self) -> None:
        result = serialize_to_dict({"c", "a", "b"})
        assert result == ["a", "b", "c"]

    def test_make_error(self) -> None:
        result = json.loads(make_error("ScenarioNotFound", "not found"))
        assert result["error"] is True
        assert result["error_type"] == "ScenarioNotFound"

    def test_make_success(self) -> None:
        result = json.loads(make_success({"count": 5}))
        assert result["count"] == 5


# ============================================================================
# ResultStore tests
# ============================================================================


def _make_stored(run_id: str = "abc123", scenario: str = "test") -> StoredResult:
    return StoredResult(
        run_id=run_id,
        scenario_name=scenario,
        seed=42,
        summary={"ticks": 10},
    )


class TestResultStore:
    """In-memory LRU result cache."""

    def test_store_and_get(self) -> None:
        store = ResultStore(max_size=5)
        sr = _make_stored("run1")
        store.store(sr)
        assert store.get("run1") is sr

    def test_get_missing_returns_none(self) -> None:
        store = ResultStore()
        assert store.get("nonexistent") is None

    def test_lru_eviction(self) -> None:
        store = ResultStore(max_size=3)
        for i in range(4):
            store.store(_make_stored(f"run{i}"))
        # run0 should be evicted
        assert store.get("run0") is None
        assert store.get("run1") is not None
        assert store.get("run3") is not None

    def test_latest(self) -> None:
        store = ResultStore()
        store.store(_make_stored("a"))
        store.store(_make_stored("b"))
        assert store.latest().run_id == "b"

    def test_latest_empty(self) -> None:
        store = ResultStore()
        assert store.latest() is None

    def test_list_runs(self) -> None:
        store = ResultStore()
        store.store(_make_stored("x"))
        store.store(_make_stored("y"))
        runs = store.list_runs()
        assert len(runs) == 2
        assert runs[0]["run_id"] == "y"  # newest first

    def test_clear(self) -> None:
        store = ResultStore()
        store.store(_make_stored("a"))
        store.clear()
        assert len(store) == 0

    def test_generate_id_unique(self) -> None:
        ids = {ResultStore.generate_id() for _ in range(100)}
        assert len(ids) == 100


# ============================================================================
# MCP tool function tests (direct async calls)
# ============================================================================


class TestMCPToolDirect:
    """Direct tests of MCP tool handler functions.

    These test the tool function logic without protocol-level testing.
    Uses mocks/SimpleNamespace to avoid full simulation startup.
    """

    def test_serializer_handles_victory_result(self) -> None:
        """VictoryResult-like object serializes correctly."""
        vr = _FakeResult(game_over=True, winning_side="blue", condition_type="time_expired", tick=50)
        result = serialize_to_dict(vr)
        assert result["game_over"] is True
        assert result["condition_type"] == "time_expired"

    def test_serializer_handles_unit_summary(self) -> None:
        """Unit summary dict with mixed types."""
        summary = {
            "side": "blue",
            "active": np.int32(4),
            "destroyed": np.int64(2),
            "supply": np.float64(0.85),
        }
        result = serialize_to_dict(summary)
        assert result["active"] == 4
        assert isinstance(result["active"], int)
        assert abs(result["supply"] - 0.85) < 1e-10

    def test_serializer_handles_mc_result_like(self) -> None:
        """Monte Carlo result-like structure."""
        mc = {
            "num_runs": 50,
            "metrics": {
                "exchange_ratio": {
                    "mean": np.float64(2.5),
                    "std": np.float64(0.8),
                    "percentile_5": np.float64(1.2),
                    "percentile_95": np.float64(4.1),
                }
            },
        }
        result = json.loads(serialize(mc))
        assert result["metrics"]["exchange_ratio"]["mean"] == 2.5

    def test_result_store_store_get_roundtrip(self) -> None:
        """Store a result and retrieve it."""
        store = ResultStore()
        sr = StoredResult(
            run_id="test1",
            scenario_name="73_easting",
            seed=42,
            summary={"victory": "blue"},
            recorder_events=[
                {"tick": 0, "event_type": "DetectionEvent"},
                {"tick": 1, "event_type": "EngagementEvent"},
            ],
        )
        store.store(sr)
        retrieved = store.get("test1")
        assert retrieved is not None
        assert len(retrieved.recorder_events) == 2

    def test_result_store_duplicate_update(self) -> None:
        """Storing same run_id moves to end."""
        store = ResultStore(max_size=3)
        store.store(_make_stored("a"))
        store.store(_make_stored("b"))
        store.store(_make_stored("a"))  # re-store a
        store.store(_make_stored("c"))
        store.store(_make_stored("d"))
        # b should be evicted (oldest after a was moved to end)
        assert store.get("b") is None
        assert store.get("a") is not None


# ============================================================================
# MCP resource tests
# ============================================================================


class TestMCPResources:
    """Tests for mcp_resources.py resource providers."""

    def test_get_scenario_config_valid(self) -> None:
        """Returns YAML content for existing scenario."""
        result = get_scenario_config("test_campaign")
        assert "name:" in result or "sides:" in result

    def test_get_scenario_config_missing(self) -> None:
        """Returns error JSON for nonexistent scenario."""
        result = get_scenario_config("nonexistent_scenario_xyz")
        parsed = json.loads(result)
        assert parsed["error"] is True

    def test_get_unit_definition_valid(self) -> None:
        """Returns YAML content for existing unit."""
        result = get_unit_definition("armor", "m1a2")
        assert "unit_type" in result or "display_name" in result

    def test_get_unit_definition_missing(self) -> None:
        """Returns error JSON for nonexistent unit."""
        result = get_unit_definition("ground", "nonexistent_unit_xyz")
        parsed = json.loads(result)
        assert parsed["error"] is True

    def test_get_cached_result_valid(self) -> None:
        """Returns cached result JSON."""
        store = ResultStore()
        sr = StoredResult(
            run_id="res_test",
            scenario_name="test",
            seed=42,
            summary={"victory": "blue", "ticks": 10},
        )
        store.store(sr)
        result = get_cached_result("res_test", store)
        parsed = json.loads(result)
        assert parsed["victory"] == "blue"

    def test_get_cached_result_missing(self) -> None:
        """Returns error JSON for nonexistent run."""
        store = ResultStore()
        result = get_cached_result("nonexistent_run", store)
        parsed = json.loads(result)
        assert parsed["error"] is True
