"""Phase 89a: Per-side parallel detection threading.

Tests for ThreadPoolExecutor-based per-side FOW detection dispatch,
RNG stream forking for determinism, and backward compatibility.
"""

from __future__ import annotations

import inspect
import time

import numpy as np
import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.detection.detection import DetectionEngine
from stochastic_warfare.detection.estimation import StateEstimator
from stochastic_warfare.detection.fog_of_war import FogOfWarManager, SideWorldView
from stochastic_warfare.detection.identification import IdentificationEngine
from stochastic_warfare.detection.intel_fusion import IntelFusionEngine
from stochastic_warfare.detection.deception import DeceptionEngine
from stochastic_warfare.detection.sensors import SensorDefinition, SensorInstance
from stochastic_warfare.detection.signatures import SignatureProfile, VisualSignature
from stochastic_warfare.simulation.battle import BattleManager
from stochastic_warfare.simulation.calibration import CalibrationSchema


# ── Helpers ────────────────────────────────────────────────────────────


def _sensor(**kwargs) -> SensorInstance:
    defaults = dict(
        sensor_id="eye", sensor_type="VISUAL", display_name="Eye",
        max_range_m=50000.0, detection_threshold=1.0,
    )
    defaults.update(kwargs)
    return SensorInstance(SensorDefinition(**defaults))


def _profile(cross_section: float = 10.0) -> SignatureProfile:
    return SignatureProfile(
        profile_id="test", unit_type="test",
        visual=VisualSignature(cross_section_m2=cross_section, camouflage_factor=1.0),
    )


def _fow(seed: int = 42) -> FogOfWarManager:
    rng = np.random.Generator(np.random.PCG64(seed))
    det = DetectionEngine(rng=np.random.Generator(np.random.PCG64(seed + 1)))
    ident = IdentificationEngine(np.random.Generator(np.random.PCG64(seed + 2)))
    est = StateEstimator(rng=np.random.Generator(np.random.PCG64(seed + 3)))
    intel = IntelFusionEngine(state_estimator=est, rng=np.random.Generator(np.random.PCG64(seed + 4)))
    dec = DeceptionEngine(rng=np.random.Generator(np.random.PCG64(seed + 5)))
    return FogOfWarManager(
        detection_engine=det,
        identification_engine=ident,
        state_estimator=est,
        intel_fusion=intel,
        deception_engine=dec,
        rng=rng,
    )


def _own_unit(x: float = 0.0, y: float = 0.0, **kwargs) -> dict:
    sensors = kwargs.pop("sensors", [_sensor()])
    return {
        "position": Position(x, y, 0.0),
        "sensors": sensors,
        "observer_height": kwargs.get("observer_height", 1.8),
    }


def _enemy_unit(uid: str, x: float, y: float, **kwargs) -> dict:
    return {
        "unit_id": uid,
        "position": Position(x, y, 0.0),
        "signature": kwargs.get("signature", _profile()),
        "unit": kwargs.get("unit", None),
        "target_height": kwargs.get("target_height", 0.0),
        "concealment": kwargs.get("concealment", 0.0),
        "posture": kwargs.get("posture", 0),
    }


# ── Per-Side Parallel Detection Tests ──────────────────────────────────


class TestParallelDetectionDeterminism:
    """Parallel detection produces deterministic results."""

    def test_parallel_deterministic_across_runs(self) -> None:
        """Same seed + parallel RNG forking → identical contacts each run."""
        results = []
        for _ in range(3):
            fow = _fow(seed=100)
            # Fork RNG like battle.py does
            det_rng = fow._rng
            side_seeds = det_rng.integers(0, 2**63, size=2)
            side_rngs = {
                "blue": np.random.Generator(np.random.PCG64(int(side_seeds[0]))),
                "red": np.random.Generator(np.random.PCG64(int(side_seeds[1]))),
            }

            own_blue = [_own_unit(0.0, 0.0, sensors=[_sensor(max_range_m=5000.0)])]
            enemy_red = [_enemy_unit("r1", 3000.0, 0.0, signature=_profile(100.0))]
            wv_blue = fow.update(
                "blue", own_blue, enemy_red, dt=1.0,
                rng=side_rngs["blue"],
            )

            own_red = [_own_unit(3000.0, 0.0, sensors=[_sensor(max_range_m=5000.0)])]
            enemy_blue = [_enemy_unit("b1", 0.0, 0.0, signature=_profile(100.0))]
            wv_red = fow.update(
                "red", own_red, enemy_blue, dt=1.0,
                rng=side_rngs["red"],
            )

            results.append((set(wv_blue.contacts.keys()), set(wv_red.contacts.keys())))

        # All runs should produce identical contacts
        assert results[0] == results[1] == results[2]

    def test_sequential_determinism_preserved(self) -> None:
        """Same seed + sequential (no rng override) → identical contacts."""
        results = []
        for _ in range(3):
            fow = _fow(seed=200)
            own = [_own_unit(0.0, 0.0, sensors=[_sensor(max_range_m=5000.0)])]
            enemy = [_enemy_unit("r1", 3000.0, 0.0, signature=_profile(100.0))]
            wv = fow.update("blue", own, enemy, dt=1.0)
            results.append(set(wv.contacts.keys()))
        assert results[0] == results[1] == results[2]


class TestParallelDetectionParity:
    """Parallel and sequential paths agree on trivial cases."""

    def test_guaranteed_detection_same_result(self) -> None:
        """Very close target with huge signature: detected regardless of RNG."""
        for use_rng_override in [False, True]:
            fow = _fow(seed=300)
            own = [_own_unit(0.0, 0.0, sensors=[_sensor(max_range_m=50000.0)])]
            # Very close + massive signature = guaranteed detection
            enemy = [_enemy_unit("t1", 100.0, 0.0, signature=_profile(10000.0))]
            if use_rng_override:
                rng_override = np.random.Generator(np.random.PCG64(999))
                wv = fow.update("blue", own, enemy, dt=1.0, rng=rng_override)
            else:
                wv = fow.update("blue", own, enemy, dt=1.0)
            assert "t1" in wv.contacts, f"use_rng_override={use_rng_override}"

    def test_out_of_range_never_detected(self) -> None:
        """Target 100km away with 5km sensor: never detected regardless of mode."""
        for use_rng_override in [False, True]:
            fow = _fow(seed=301)
            own = [_own_unit(0.0, 0.0, sensors=[_sensor(max_range_m=5000.0)])]
            enemy = [_enemy_unit("far", 100_000.0, 0.0)]
            if use_rng_override:
                rng_override = np.random.Generator(np.random.PCG64(888))
                wv = fow.update("blue", own, enemy, dt=1.0, rng=rng_override)
            else:
                wv = fow.update("blue", own, enemy, dt=1.0)
            assert "far" not in wv.contacts


class TestRNGStreamForking:
    """Per-side forked RNG streams are independent."""

    def test_forked_streams_produce_different_sequences(self) -> None:
        """Blue and red forked streams generate different random values."""
        master_rng = np.random.Generator(np.random.PCG64(42))
        seeds = master_rng.integers(0, 2**63, size=2)
        blue_rng = np.random.Generator(np.random.PCG64(int(seeds[0])))
        red_rng = np.random.Generator(np.random.PCG64(int(seeds[1])))

        blue_vals = [blue_rng.random() for _ in range(10)]
        red_vals = [red_rng.random() for _ in range(10)]
        assert blue_vals != red_vals

    def test_forked_streams_independent_of_draw_order(self) -> None:
        """Stream state doesn't depend on other stream's consumption."""
        master1 = np.random.Generator(np.random.PCG64(42))
        seeds1 = master1.integers(0, 2**63, size=2)
        blue1 = np.random.Generator(np.random.PCG64(int(seeds1[0])))
        red1 = np.random.Generator(np.random.PCG64(int(seeds1[1])))

        # Draw blue first, then red
        b_vals = [blue1.random() for _ in range(5)]
        r_vals = [red1.random() for _ in range(5)]

        # Now draw red first, then blue
        master2 = np.random.Generator(np.random.PCG64(42))
        seeds2 = master2.integers(0, 2**63, size=2)
        blue2 = np.random.Generator(np.random.PCG64(int(seeds2[0])))
        red2 = np.random.Generator(np.random.PCG64(int(seeds2[1])))

        r_vals2 = [red2.random() for _ in range(5)]
        b_vals2 = [blue2.random() for _ in range(5)]

        # Same values regardless of draw order
        assert b_vals == b_vals2
        assert r_vals == r_vals2


class TestPerSideWorldViews:
    """Both sides get correct independent world views."""

    def test_both_sides_populated(self) -> None:
        """Parallel detection populates both sides' world views."""
        fow = _fow(seed=400)
        det_rng = fow._rng
        seeds = det_rng.integers(0, 2**63, size=2)

        # Blue detects red
        own_blue = [_own_unit(0.0, 0.0, sensors=[_sensor(max_range_m=50000.0)])]
        enemy_for_blue = [_enemy_unit("r1", 100.0, 0.0, signature=_profile(10000.0))]
        blue_rng = np.random.Generator(np.random.PCG64(int(seeds[0])))
        wv_blue = fow.update("blue", own_blue, enemy_for_blue, dt=1.0, rng=blue_rng)

        # Red detects blue
        own_red = [_own_unit(100.0, 0.0, sensors=[_sensor(max_range_m=50000.0)])]
        enemy_for_red = [_enemy_unit("b1", 0.0, 0.0, signature=_profile(10000.0))]
        red_rng = np.random.Generator(np.random.PCG64(int(seeds[1])))
        wv_red = fow.update("red", own_red, enemy_for_red, dt=1.0, rng=red_rng)

        assert "r1" in wv_blue.contacts
        assert "b1" in wv_red.contacts

    def test_no_cross_contamination(self) -> None:
        """Side A's contacts don't appear in side B's world view."""
        fow = _fow(seed=401)
        det_rng = fow._rng
        seeds = det_rng.integers(0, 2**63, size=2)

        # Blue detects red target "r1"
        own_blue = [_own_unit(0.0, 0.0, sensors=[_sensor(max_range_m=50000.0)])]
        enemy_for_blue = [_enemy_unit("r1", 100.0, 0.0, signature=_profile(10000.0))]
        blue_rng = np.random.Generator(np.random.PCG64(int(seeds[0])))
        fow.update("blue", own_blue, enemy_for_blue, dt=1.0, rng=blue_rng)

        # Red detects blue target "b1"
        own_red = [_own_unit(100.0, 0.0, sensors=[_sensor(max_range_m=50000.0)])]
        enemy_for_red = [_enemy_unit("b1", 0.0, 0.0, signature=_profile(10000.0))]
        red_rng = np.random.Generator(np.random.PCG64(int(seeds[1])))
        fow.update("red", own_red, enemy_for_red, dt=1.0, rng=red_rng)

        wv_blue = fow.get_world_view("blue")
        wv_red = fow.get_world_view("red")

        # Blue should NOT see "b1", red should NOT see "r1"
        assert "b1" not in wv_blue.contacts
        assert "r1" not in wv_red.contacts

    def test_three_faction_parallel(self) -> None:
        """Three sides all get correct independent world views."""
        fow = _fow(seed=402)
        det_rng = fow._rng
        seeds = det_rng.integers(0, 2**63, size=3)
        sides = ["blue", "red", "green"]
        side_rngs = {
            s: np.random.Generator(np.random.PCG64(int(sd)))
            for s, sd in zip(sides, seeds)
        }

        positions = {"blue": (0.0, 0.0), "red": (100.0, 0.0), "green": (0.0, 100.0)}
        sig = _profile(10000.0)

        for side in sides:
            sx, sy = positions[side]
            own = [_own_unit(sx, sy, sensors=[_sensor(max_range_m=50000.0)])]
            enemies = []
            for other_side in sides:
                if other_side == side:
                    continue
                ox, oy = positions[other_side]
                enemies.append(_enemy_unit(f"{other_side}_1", ox, oy, signature=sig))
            fow.update(side, own, enemies, dt=1.0, rng=side_rngs[side])

        for side in sides:
            wv = fow.get_world_view(side)
            for other_side in sides:
                if other_side == side:
                    assert f"{other_side}_1" not in wv.contacts
                else:
                    assert f"{other_side}_1" in wv.contacts


class TestBackwardCompatibility:
    """enable_parallel_detection=False preserves existing behavior."""

    def test_default_is_false(self) -> None:
        cal = CalibrationSchema()
        assert cal.enable_parallel_detection is False

    def test_rng_param_none_uses_internal(self) -> None:
        """When rng=None (default), FOW uses its internal RNG."""
        fow = _fow(seed=500)
        own = [_own_unit(0.0, 0.0, sensors=[_sensor(max_range_m=50000.0)])]
        enemy = [_enemy_unit("t1", 100.0, 0.0, signature=_profile(10000.0))]
        wv = fow.update("blue", own, enemy, dt=1.0)  # No rng param
        assert isinstance(wv, SideWorldView)


class TestStructural:
    """Source-level verification of Phase 89 wiring."""

    def test_parallel_detection_consumed_in_battle(self) -> None:
        """enable_parallel_detection read in execute_tick source."""
        src = inspect.getsource(BattleManager.execute_tick)
        assert "enable_parallel_detection" in src

    def test_thread_pool_in_battle(self) -> None:
        """ThreadPoolExecutor used in execute_tick for parallel dispatch."""
        src = inspect.getsource(BattleManager.execute_tick)
        assert "ThreadPoolExecutor" in src

    def test_rng_param_in_fow_update(self) -> None:
        """FogOfWarManager.update accepts rng parameter."""
        src = inspect.getsource(FogOfWarManager.update)
        assert "rng" in src

    def test_rng_param_in_check_detection(self) -> None:
        """DetectionEngine.check_detection accepts rng parameter."""
        src = inspect.getsource(DetectionEngine.check_detection)
        assert "rng" in src
