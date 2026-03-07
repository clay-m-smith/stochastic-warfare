"""Tests for config_overrides deep merge in RunManager (Phase 37a, Bug 1)."""

from __future__ import annotations

import pytest

from api.run_manager import RunManager


class TestApplyOverrides:
    """Unit tests for RunManager._apply_overrides static method."""

    def test_flat_scalar_override(self) -> None:
        base = {"name": "test", "seed": 42}
        RunManager._apply_overrides(base, {"seed": 99})
        assert base["seed"] == 99

    def test_nested_dict_merge(self) -> None:
        base = {"calibration": {"visibility_m": 5000, "hit_prob": 0.8}}
        RunManager._apply_overrides(base, {"calibration": {"visibility_m": 1000}})
        assert base["calibration"]["visibility_m"] == 1000
        assert base["calibration"]["hit_prob"] == 0.8

    def test_deeply_nested_merge(self) -> None:
        base = {"a": {"b": {"c": 1, "d": 2}}}
        RunManager._apply_overrides(base, {"a": {"b": {"c": 99}}})
        assert base["a"]["b"]["c"] == 99
        assert base["a"]["b"]["d"] == 2

    def test_list_replaced_not_merged(self) -> None:
        base = {"units": [1, 2, 3]}
        RunManager._apply_overrides(base, {"units": [4, 5]})
        assert base["units"] == [4, 5]

    def test_empty_overrides_noop(self) -> None:
        base = {"name": "test", "val": 42}
        original = dict(base)
        RunManager._apply_overrides(base, {})
        assert base == original

    def test_new_key_added(self) -> None:
        base = {"name": "test"}
        RunManager._apply_overrides(base, {"new_field": "value"})
        assert base["new_field"] == "value"

    def test_override_dict_replaces_scalar(self) -> None:
        base = {"field": "scalar"}
        RunManager._apply_overrides(base, {"field": {"nested": True}})
        assert base["field"] == {"nested": True}

    def test_override_scalar_replaces_dict(self) -> None:
        base = {"field": {"nested": True}}
        RunManager._apply_overrides(base, {"field": "scalar"})
        assert base["field"] == "scalar"
