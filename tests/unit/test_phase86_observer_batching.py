"""Tests for Phase 86b: Observer modifier batching."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from stochastic_warfare.simulation.battle import (
    _DEFAULT_OBS_MODS,
    _ObserverModifiers,
    _resolve_cal_flat,
)
from stochastic_warfare.simulation.calibration import CalibrationSchema


class TestObserverModifiers:
    """Tests for the _ObserverModifiers namedtuple."""

    def test_default_values(self) -> None:
        """Default instance has neutral modifier values."""
        obs = _DEFAULT_OBS_MODS
        assert obs.mopp_detection == 1.0
        assert obs.mopp_fov_mod == 1.0
        assert obs.mopp_fatigue == 1.0
        assert obs.mopp_reload_mod == 1.0
        assert obs.mopp_level == 0
        assert obs.altitude_factor == 1.0
        assert obs.readiness == 1.0

    def test_custom_values(self) -> None:
        """Custom observer modifiers store correctly."""
        obs = _ObserverModifiers(
            mopp_detection=0.6,
            mopp_fov_mod=0.8,
            mopp_fatigue=1.5,
            mopp_reload_mod=1.3,
            mopp_level=3,
            altitude_factor=0.7,
            readiness=0.85,
        )
        assert obs.mopp_detection == 0.6
        assert obs.mopp_level == 3
        assert obs.altitude_factor == 0.7
        assert obs.readiness == 0.85

    def test_is_namedtuple(self) -> None:
        """Observer modifiers are a lightweight NamedTuple."""
        obs = _ObserverModifiers()
        assert hasattr(obs, "_fields")
        assert len(obs._fields) == 7


class TestResolveCalFlat:
    """Tests for _resolve_cal_flat() helper."""

    def test_returns_existing_cal_flat(self) -> None:
        """When ctx.cal_flat is set, return it directly."""
        ctx = SimpleNamespace(cal_flat={"enable_lod": True})
        result = _resolve_cal_flat(ctx)
        assert result["enable_lod"] is True

    def test_builds_from_calibration_schema(self) -> None:
        """When cal_flat missing, builds from CalibrationSchema."""
        cal = CalibrationSchema(hit_probability_modifier=2.0)
        ctx = SimpleNamespace(
            calibration=cal,
            units_by_side={"blue": [], "red": []},
        )
        result = _resolve_cal_flat(ctx)
        assert result["hit_probability_modifier"] == 2.0

    def test_builds_from_dict_calibration(self) -> None:
        """When calibration is a plain dict, returns it."""
        ctx = SimpleNamespace(
            calibration={"enable_lod": True, "visibility_m": 5000},
        )
        result = _resolve_cal_flat(ctx)
        assert result["enable_lod"] is True
        assert result["visibility_m"] == 5000

    def test_returns_empty_dict_when_no_calibration(self) -> None:
        """When ctx has no calibration, returns empty dict."""
        ctx = SimpleNamespace()
        result = _resolve_cal_flat(ctx)
        assert result == {}

    def test_side_keys_generated_from_units_by_side(self) -> None:
        """Side-prefixed keys use actual side names from ctx."""
        cal = CalibrationSchema(hit_probability_modifier=1.5)
        ctx = SimpleNamespace(
            calibration=cal,
            units_by_side={"alpha": [], "bravo": []},
        )
        result = _resolve_cal_flat(ctx)
        assert result.get("alpha_hit_probability_modifier") == 1.5
        assert result.get("bravo_hit_probability_modifier") == 1.5
