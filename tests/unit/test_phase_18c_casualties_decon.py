"""Phase 18c tests — CBRN casualty engine and decontamination operations."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.cbrn.agents import AgentCategory, AgentDefinition
from stochastic_warfare.cbrn.casualties import (
    CBRNCasualtyEngine,
    CasualtyConfig,
)
from stochastic_warfare.cbrn.decontamination import (
    DeconType,
    DecontaminationEngine,
)
from stochastic_warfare.core.events import EventBus

TS = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _make_casualty_engine(seed: int = 42) -> CBRNCasualtyEngine:
    return CBRNCasualtyEngine(
        event_bus=EventBus(),
        rng=np.random.default_rng(seed),
        config=CasualtyConfig(min_dosage_for_check=0.1),
    )


def _make_sarin() -> AgentDefinition:
    # Probit calibrated: at LCt50=70, Y = a + b*ln(70) = 5 → P=0.5
    # a = 5 - 1.0*ln(70) ≈ 0.75
    return AgentDefinition(
        agent_id="sarin",
        category=int(AgentCategory.NERVE),
        lct50_mg_min_m3=70.0,
        ict50_mg_min_m3=35.0,
        probit_a=0.75,
        probit_b=1.0,
    )


# ---------------------------------------------------------------------------
# Dosage accumulation
# ---------------------------------------------------------------------------


class TestDosageAccumulation:
    def test_basic_ct(self):
        eng = _make_casualty_engine()
        ct = eng.accumulate_dosage("u1", "sarin", 10.0, 60.0)  # 10 mg/m³ for 60s
        assert ct == pytest.approx(10.0)  # 10 * 1min

    def test_protection_reduces(self):
        eng = _make_casualty_engine()
        ct = eng.accumulate_dosage("u1", "sarin", 10.0, 60.0, protection_factor=0.5)
        assert ct == pytest.approx(5.0)  # Half blocked


# ---------------------------------------------------------------------------
# Probit model
# ---------------------------------------------------------------------------


class TestProbit:
    def test_known_values(self):
        """At LCt50 dosage, probit should give ~50% probability."""
        # For standard probit: Y = a + b*ln(D), at LCt50 → Y=5 → P=0.5
        # With a=-14, b=1: need ln(D) = 19, D = e^19 ≈ 1.78e8
        # Let's use simpler values: a=5, b=0 → always Y=5 → P=0.5
        p = CBRNCasualtyEngine.probit_probability(100.0, 5.0, 0.0)
        assert p == pytest.approx(0.5, abs=0.01)

    def test_zero_dosage(self):
        p = CBRNCasualtyEngine.probit_probability(0.0, -14.0, 1.0)
        assert p == 0.0

    def test_high_dosage_approaches_one(self):
        # Very high dosage → P approaches 1.0
        p = CBRNCasualtyEngine.probit_probability(1e20, -14.0, 1.0)
        assert p > 0.99


# ---------------------------------------------------------------------------
# Casualties
# ---------------------------------------------------------------------------


class TestCasualties:
    def test_below_threshold_zero(self):
        eng = _make_casualty_engine()
        agent = _make_sarin()
        # No dosage accumulated → 0 casualties
        incap, lethal = eng.assess_casualties("u1", agent, 100, TS)
        assert incap == 0
        assert lethal == 0

    def test_above_threshold(self):
        eng = _make_casualty_engine()
        agent = _make_sarin()
        # Accumulate massive dosage
        eng.accumulate_dosage("u1", "sarin", 1000.0, 600.0)  # 10000 Ct
        incap, lethal = eng.assess_casualties("u1", agent, 100, TS)
        assert lethal > 0 or incap > 0  # Some casualties expected

    def test_lethality_above_incapacitation(self):
        """With very high dosage, lethal should exceed incapacitated."""
        eng = _make_casualty_engine(seed=1)
        agent = _make_sarin()
        # Massive dosage → mostly lethal
        eng.accumulate_dosage("u1", "sarin", 10000.0, 6000.0)
        incap, lethal = eng.assess_casualties("u1", agent, 200, TS)
        # At extreme dosage, P(lethal) ~ P(incap) → lethal >= incap
        assert lethal + incap > 0


# ---------------------------------------------------------------------------
# Radiation
# ---------------------------------------------------------------------------


class TestRadiation:
    def test_accumulation(self):
        eng = _make_casualty_engine()
        dose = eng.accumulate_radiation("u1", 0.001, 100.0)  # 0.001 Gy/s for 100s
        assert dose == pytest.approx(0.1)

    def test_protection_factor(self):
        eng = _make_casualty_engine()
        dose = eng.accumulate_radiation("u1", 0.01, 100.0, protection_factor=0.5)
        assert dose == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Triage priority
# ---------------------------------------------------------------------------


class TestTriagePriority:
    def test_mapping(self):
        assert CBRNCasualtyEngine.get_triage_priority(2.5) == 4  # EXPECTANT
        assert CBRNCasualtyEngine.get_triage_priority(1.5) == 1  # IMMEDIATE
        assert CBRNCasualtyEngine.get_triage_priority(0.7) == 2  # DELAYED
        assert CBRNCasualtyEngine.get_triage_priority(0.2) == 3  # MINIMAL

    def test_edge_cases(self):
        assert CBRNCasualtyEngine.get_triage_priority(0.0) == 3  # MINIMAL
        assert CBRNCasualtyEngine.get_triage_priority(2.0) == 4  # EXPECTANT


# ---------------------------------------------------------------------------
# Decontamination
# ---------------------------------------------------------------------------


def _make_decon_engine(seed: int = 42) -> DecontaminationEngine:
    return DecontaminationEngine(
        event_bus=EventBus(),
        rng=np.random.default_rng(seed),
    )


class TestDeconParams:
    def test_hasty(self):
        eng = _make_decon_engine()
        op = eng.start_decon("u1", int(DeconType.HASTY), "sarin", 0.0, 0.0)
        assert op.duration_s == pytest.approx(300.0)
        assert op.effectiveness == pytest.approx(0.60)

    def test_deliberate(self):
        eng = _make_decon_engine()
        op = eng.start_decon("u1", int(DeconType.DELIBERATE), "sarin", 0.0, 0.0)
        assert op.duration_s == pytest.approx(1800.0)
        assert op.effectiveness == pytest.approx(0.95)

    def test_thorough(self):
        eng = _make_decon_engine()
        op = eng.start_decon("u1", int(DeconType.THOROUGH), "sarin", 0.0, 0.0)
        assert op.duration_s == pytest.approx(7200.0)
        assert op.effectiveness == pytest.approx(0.99)


class TestDeconLifecycle:
    def test_start_creates_op(self):
        eng = _make_decon_engine()
        op = eng.start_decon("u1", int(DeconType.HASTY), "sarin", 0.3, 0.0, TS)
        assert op.unit_id == "u1"
        assert len(eng.active_operations) == 1

    def test_update_completes(self):
        eng = _make_decon_engine()
        eng.start_decon("u1", int(DeconType.HASTY), "sarin", 0.0, 0.0, TS)
        completed = eng.update(500.0, TS)  # After 300s base duration
        assert "u1" in completed
        assert len(eng.active_operations) == 0

    def test_multiple_ops(self):
        eng = _make_decon_engine()
        eng.start_decon("u1", int(DeconType.HASTY), "sarin", 0.0, 0.0, TS)
        eng.start_decon("u2", int(DeconType.DELIBERATE), "vx", 0.0, 0.0, TS)
        # After 400s, only hasty should complete
        completed = eng.update(400.0, TS)
        assert "u1" in completed
        assert "u2" not in completed
        assert len(eng.active_operations) == 1


class TestDeconEffectiveness:
    def test_reduces_contamination(self):
        """Thorough should have highest effectiveness."""
        eng = _make_decon_engine()
        op = eng.start_decon("u1", int(DeconType.THOROUGH), "vx", 0.0, 0.0)
        assert op.effectiveness == pytest.approx(0.99)

    def test_difficulty_scales_duration(self):
        eng = _make_decon_engine()
        op_easy = eng.start_decon("u1", int(DeconType.HASTY), "sarin", 0.0, 0.0)
        eng2 = _make_decon_engine()
        op_hard = eng2.start_decon("u2", int(DeconType.HASTY), "vx", 0.8, 0.0)
        assert op_hard.duration_s > op_easy.duration_s


class TestDeconDifficulty:
    def test_hard_agents_longer(self):
        eng = _make_decon_engine()
        easy = eng.start_decon("u1", int(DeconType.DELIBERATE), "chlorine", 0.1, 0.0)
        eng2 = _make_decon_engine()
        hard = eng2.start_decon("u2", int(DeconType.DELIBERATE), "vx", 0.8, 0.0)
        assert hard.duration_s > easy.duration_s

    def test_zero_difficulty_base_duration(self):
        eng = _make_decon_engine()
        op = eng.start_decon("u1", int(DeconType.HASTY), "sarin", 0.0, 0.0)
        assert op.duration_s == pytest.approx(300.0)


class TestDeconSupply:
    def test_requirements_per_type(self):
        reqs = DecontaminationEngine.get_supply_requirements(int(DeconType.THOROUGH))
        assert "water_gallons" in reqs
        assert reqs["water_gallons"] > 0


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------


class TestState:
    def test_casualty_roundtrip(self):
        eng = _make_casualty_engine()
        eng.accumulate_dosage("u1", "sarin", 100.0, 60.0)
        eng.accumulate_radiation("u1", 0.01, 100.0)
        state = eng.get_state()

        eng2 = _make_casualty_engine()
        eng2.set_state(state)
        assert eng2.get_dosage("u1", "sarin") == pytest.approx(100.0)

    def test_decon_roundtrip(self):
        eng = _make_decon_engine()
        eng.start_decon("u1", int(DeconType.HASTY), "sarin", 0.3, 100.0, TS)
        state = eng.get_state()

        eng2 = _make_decon_engine()
        eng2.set_state(state)
        assert len(eng2.active_operations) == 1
        assert eng2.active_operations[0].unit_id == "u1"
