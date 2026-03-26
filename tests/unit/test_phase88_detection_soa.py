"""Phase 88b: SoA detection integration — vectorized range checks."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.core.types import Position


# ---------------------------------------------------------------------------
# Helpers — minimal FOW-like range filtering
# ---------------------------------------------------------------------------


def _vectorized_range_filter(
    obs_pos: Position,
    target_positions: np.ndarray,
    max_range: float,
) -> list[int]:
    """Phase 88b vectorized range check — matches fog_of_war.py logic."""
    if target_positions.shape[0] == 0:
        return []
    obs_arr = np.array([obs_pos.easting, obs_pos.northing])
    diffs = target_positions - obs_arr
    dists = np.sqrt(np.sum(diffs * diffs, axis=1))
    return list(np.where(dists <= max_range)[0])


def _scalar_range_filter(
    obs_pos: Position,
    targets: list[dict],
    max_range: float,
) -> list[int]:
    """Scalar fallback — iterate all targets."""
    result = []
    for i, t in enumerate(targets):
        tp = t["position"]
        dx = tp.easting - obs_pos.easting
        dy = tp.northing - obs_pos.northing
        if (dx * dx + dy * dy) ** 0.5 <= max_range:
            result.append(i)
    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestVectorizedRangeCheck:
    """Verify vectorized range check matches scalar per-target check."""

    def test_basic_parity(self):
        obs = Position(0.0, 0.0)
        targets = [
            {"position": Position(100, 0), "unit_id": "t1"},
            {"position": Position(500, 0), "unit_id": "t2"},
            {"position": Position(1500, 0), "unit_id": "t3"},
        ]
        tgt_pos = np.array(
            [(t["position"].easting, t["position"].northing) for t in targets],
            dtype=np.float64,
        )

        vec_result = _vectorized_range_filter(obs, tgt_pos, 1000.0)
        scalar_result = _scalar_range_filter(obs, targets, 1000.0)
        assert vec_result == scalar_result

    def test_all_out_of_range(self):
        obs = Position(0.0, 0.0)
        targets = [
            {"position": Position(5000, 5000), "unit_id": "t1"},
            {"position": Position(6000, 6000), "unit_id": "t2"},
        ]
        tgt_pos = np.array(
            [(t["position"].easting, t["position"].northing) for t in targets],
            dtype=np.float64,
        )

        vec_result = _vectorized_range_filter(obs, tgt_pos, 100.0)
        scalar_result = _scalar_range_filter(obs, targets, 100.0)
        assert vec_result == [] == scalar_result

    def test_all_in_range(self):
        obs = Position(0.0, 0.0)
        targets = [
            {"position": Position(10, 10), "unit_id": "t1"},
            {"position": Position(20, 20), "unit_id": "t2"},
        ]
        tgt_pos = np.array(
            [(t["position"].easting, t["position"].northing) for t in targets],
            dtype=np.float64,
        )

        vec_result = _vectorized_range_filter(obs, tgt_pos, 10000.0)
        assert len(vec_result) == 2

    def test_single_observer_single_target(self):
        obs = Position(100.0, 100.0)
        tgt = Position(103.0, 104.0)  # distance = 5.0
        tgt_pos = np.array([[tgt.easting, tgt.northing]], dtype=np.float64)

        result = _vectorized_range_filter(obs, tgt_pos, 5.0)
        assert result == [0]

        result = _vectorized_range_filter(obs, tgt_pos, 4.9)
        assert result == []

    def test_empty_targets(self):
        obs = Position(0.0, 0.0)
        tgt_pos = np.empty((0, 2), dtype=np.float64)
        result = _vectorized_range_filter(obs, tgt_pos, 1000.0)
        assert result == []


class TestFOWUnitArraysParam:
    """Verify FOW update accepts unit_arrays parameter."""

    def test_update_signature_accepts_unit_arrays(self):
        """FOW.update() must accept unit_arrays kwarg."""
        import inspect
        from stochastic_warfare.detection.fog_of_war import FogOfWarManager
        sig = inspect.signature(FogOfWarManager.update)
        assert "unit_arrays" in sig.parameters

    def test_battle_passes_unit_arrays_to_fow(self):
        """battle.py FOW update call includes unit_arrays."""
        import inspect
        from stochastic_warfare.simulation.battle import BattleManager
        src = inspect.getsource(BattleManager.execute_tick)
        assert "unit_arrays=_unit_arrays" in src
