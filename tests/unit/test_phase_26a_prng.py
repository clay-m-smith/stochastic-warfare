"""Phase 26a: PRNG discipline — rng required on all 23 engines, zero default_rng in source."""

from __future__ import annotations

import pathlib
import re

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

_RNG = np.random.default_rng(42)

SRC_ROOT = pathlib.Path(__file__).resolve().parents[2] / "stochastic_warfare"


# ---------------------------------------------------------------------------
# 1. Each engine must raise TypeError when constructed without rng=
# ---------------------------------------------------------------------------


class TestArcheryEngineRequiresRNG:
    def test_missing_rng_raises(self) -> None:
        from stochastic_warfare.combat.archery import ArcheryEngine
        with pytest.raises(TypeError, match="rng"):
            ArcheryEngine()


class TestBarrageEngineRequiresRNG:
    def test_missing_rng_raises(self) -> None:
        from stochastic_warfare.combat.barrage import BarrageEngine
        with pytest.raises(TypeError, match="rng"):
            BarrageEngine()


class TestGasWarfareEngineRequiresRNG:
    def test_missing_rng_raises(self) -> None:
        from stochastic_warfare.combat.gas_warfare import GasWarfareEngine
        with pytest.raises(TypeError, match="rng"):
            GasWarfareEngine()


class TestMeleeEngineRequiresRNG:
    def test_missing_rng_raises(self) -> None:
        from stochastic_warfare.combat.melee import MeleeEngine
        with pytest.raises(TypeError, match="rng"):
            MeleeEngine()


class TestNavalGunneryEngineRequiresRNG:
    def test_missing_rng_raises(self) -> None:
        from stochastic_warfare.combat.naval_gunnery import NavalGunneryEngine
        with pytest.raises(TypeError, match="rng"):
            NavalGunneryEngine()


class TestSiegeEngineRequiresRNG:
    def test_missing_rng_raises(self) -> None:
        from stochastic_warfare.combat.siege import SiegeEngine
        with pytest.raises(TypeError, match="rng"):
            SiegeEngine()


class TestStrategicBombingEngineRequiresRNG:
    def test_missing_rng_raises(self) -> None:
        from stochastic_warfare.combat.strategic_bombing import StrategicBombingEngine
        with pytest.raises(TypeError, match="rng"):
            StrategicBombingEngine()


class TestVolleyFireEngineRequiresRNG:
    def test_missing_rng_raises(self) -> None:
        from stochastic_warfare.combat.volley_fire import VolleyFireEngine
        with pytest.raises(TypeError, match="rng"):
            VolleyFireEngine()


class TestDeceptionEngineRequiresRNG:
    def test_missing_rng_raises(self) -> None:
        from stochastic_warfare.detection.deception import DeceptionEngine
        with pytest.raises(TypeError, match="rng"):
            DeceptionEngine()


class TestDetectionEngineRequiresRNG:
    def test_missing_rng_raises(self) -> None:
        from stochastic_warfare.detection.detection import DetectionEngine
        with pytest.raises(TypeError, match="rng"):
            DetectionEngine()


class TestStateEstimatorRequiresRNG:
    def test_missing_rng_raises(self) -> None:
        from stochastic_warfare.detection.estimation import StateEstimator
        with pytest.raises(TypeError, match="rng"):
            StateEstimator()


class TestFogOfWarManagerRequiresRNG:
    def test_missing_rng_raises(self) -> None:
        from stochastic_warfare.detection.fog_of_war import FogOfWarManager
        with pytest.raises(TypeError, match="rng"):
            FogOfWarManager()


class TestIntelFusionEngineRequiresRNG:
    def test_missing_rng_raises(self) -> None:
        from stochastic_warfare.detection.intel_fusion import IntelFusionEngine
        with pytest.raises(TypeError, match="rng"):
            IntelFusionEngine()


class TestSonarEngineRequiresRNG:
    def test_missing_rng_raises(self) -> None:
        from stochastic_warfare.detection.sonar import SonarEngine
        with pytest.raises(TypeError, match="rng"):
            SonarEngine()


class TestUnderwaterDetectionEngineRequiresRNG:
    def test_missing_rng_raises(self) -> None:
        from stochastic_warfare.detection.underwater_detection import UnderwaterDetectionEngine
        with pytest.raises(TypeError, match="rng"):
            UnderwaterDetectionEngine()


class TestCoordinationEngineRequiresRNG:
    def test_missing_rng_raises(self) -> None:
        from stochastic_warfare.c2.coordination import CoordinationEngine
        from stochastic_warfare.core.events import EventBus
        with pytest.raises(TypeError, match="rng"):
            CoordinationEngine(EventBus())


class TestCourierEngineRequiresRNG:
    def test_missing_rng_raises(self) -> None:
        from stochastic_warfare.c2.courier import CourierEngine
        with pytest.raises(TypeError, match="rng"):
            CourierEngine()


class TestVisualSignalEngineRequiresRNG:
    def test_missing_rng_raises(self) -> None:
        from stochastic_warfare.c2.visual_signals import VisualSignalEngine
        with pytest.raises(TypeError, match="rng"):
            VisualSignalEngine()


class TestCavalryEngineRequiresRNG:
    def test_missing_rng_raises(self) -> None:
        from stochastic_warfare.movement.cavalry import CavalryEngine
        with pytest.raises(TypeError, match="rng"):
            CavalryEngine()


class TestConvoyEngineRequiresRNG:
    def test_missing_rng_raises(self) -> None:
        from stochastic_warfare.movement.convoy import ConvoyEngine
        with pytest.raises(TypeError, match="rng"):
            ConvoyEngine()


class TestNavalOarEngineRequiresRNG:
    def test_missing_rng_raises(self) -> None:
        from stochastic_warfare.movement.naval_oar import NavalOarEngine
        with pytest.raises(TypeError, match="rng"):
            NavalOarEngine()


class TestForagingEngineRequiresRNG:
    def test_missing_rng_raises(self) -> None:
        from stochastic_warfare.logistics.foraging import ForagingEngine
        with pytest.raises(TypeError, match="rng"):
            ForagingEngine()


class TestAggregationEngineRequiresRNG:
    def test_missing_rng_raises(self) -> None:
        from stochastic_warfare.simulation.aggregation import AggregationEngine
        with pytest.raises(TypeError, match="rng"):
            AggregationEngine()


# ---------------------------------------------------------------------------
# 2. Source code scan — zero default_rng in stochastic_warfare/
# ---------------------------------------------------------------------------


class TestNoDefaultRNGInSource:
    def test_no_default_rng_in_source(self) -> None:
        """No source file under stochastic_warfare/ should contain default_rng."""
        pattern = re.compile(r"default_rng")
        violations: list[str] = []
        for py_file in sorted(SRC_ROOT.rglob("*.py")):
            text = py_file.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    violations.append(f"{py_file.relative_to(SRC_ROOT)}:{i}: {line.strip()}")
        assert violations == [], f"default_rng found in source:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# 3. Deterministic RNG injection
# ---------------------------------------------------------------------------


class TestDeterministicInjection:
    def test_same_seed_produces_same_result(self) -> None:
        """Two engines with same-seeded RNG produce identical output."""
        from stochastic_warfare.combat.volley_fire import VolleyFireConfig, VolleyFireEngine

        results = []
        for _ in range(2):
            rng = np.random.default_rng(999)
            eng = VolleyFireEngine(rng=rng)
            r = eng.fire_volley(n_muskets=100, range_m=100.0)
            results.append(r.casualties)
        assert results[0] == results[1]
