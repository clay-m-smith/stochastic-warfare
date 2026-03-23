"""Unit tests for UnconventionalWarfareEngine — IED, guerrilla, human shields."""

from __future__ import annotations

import pytest

from stochastic_warfare.combat.unconventional import (
    GuerrillaConfig,
    IEDConfig,
    IEDDetonationResult,
    UnconventionalWarfareEngine,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position

from .conftest import _rng


def _make_engine(seed: int = 42, **ied_kwargs) -> UnconventionalWarfareEngine:
    ied_config = IEDConfig(**ied_kwargs) if ied_kwargs else None
    return UnconventionalWarfareEngine(EventBus(), _rng(seed), config_ied=ied_config)


# ---------------------------------------------------------------------------
# IED emplacement
# ---------------------------------------------------------------------------


class TestIEDEmplacement:
    """IED emplacement creates unique obstacle IDs."""

    def test_emplace_ied(self):
        eng = _make_engine()
        ied_id = eng.emplace_ied(
            position=Position(100, 200, 0),
            subtype="roadside",
            blast_radius_m=15.0,
            concealment=0.8,
            emplaced_by="insurgent_1",
        )
        assert isinstance(ied_id, str)
        assert len(ied_id) > 0

    def test_multiple_ieds_unique_ids(self):
        eng = _make_engine()
        id1 = eng.emplace_ied(Position(0, 0, 0), "roadside", 10.0, 0.5, "ins")
        id2 = eng.emplace_ied(Position(100, 0, 0), "pressure_plate", 5.0, 0.9, "ins")
        assert id1 != id2


# ---------------------------------------------------------------------------
# IED detection
# ---------------------------------------------------------------------------


class TestIEDDetection:
    """Speed-tradeoff and engineering bonus for IED detection."""

    def test_speed_tradeoff(self):
        """Slower movement = higher detection probability."""
        detect_slow = 0
        detect_fast = 0
        for i in range(100):
            eng = UnconventionalWarfareEngine(EventBus(), _rng(i))
            eng.emplace_ied(Position(0, 0, 0), "roadside", 10.0, 0.5, "ins")
            if eng.check_ied_detection(unit_speed_mps=1.0, has_engineering=False, unit_id="u1"):
                detect_slow += 1
            eng2 = UnconventionalWarfareEngine(EventBus(), _rng(i + 1000))
            eng2.emplace_ied(Position(0, 0, 0), "roadside", 10.0, 0.5, "ins")
            if eng2.check_ied_detection(unit_speed_mps=15.0, has_engineering=False, unit_id="u1"):
                detect_fast += 1
        assert detect_slow >= detect_fast

    def test_engineering_bonus(self):
        """Engineering units detect better."""
        detect_eng = 0
        detect_no = 0
        for i in range(100):
            eng = UnconventionalWarfareEngine(EventBus(), _rng(i))
            eng.emplace_ied(Position(0, 0, 0), "roadside", 10.0, 0.5, "ins")
            if eng.check_ied_detection(unit_speed_mps=3.0, has_engineering=True, unit_id="u1"):
                detect_eng += 1
            eng2 = UnconventionalWarfareEngine(EventBus(), _rng(i))
            eng2.emplace_ied(Position(0, 0, 0), "roadside", 10.0, 0.5, "ins")
            if eng2.check_ied_detection(unit_speed_mps=3.0, has_engineering=False, unit_id="u1"):
                detect_no += 1
        assert detect_eng >= detect_no

    def test_max_speed_zero_detection(self):
        """At max_safe_speed, speed_factor = 0 -> effective P = 0."""
        eng = _make_engine(base_detect_probability=0.5, max_safe_speed_mps=5.0)
        eng.emplace_ied(Position(0, 0, 0), "roadside", 10.0, 0.5, "ins")
        # At speed=5.0 (equal to max_safe_speed), speed_factor = 1 - 5/5 = 0
        detected = eng.check_ied_detection(unit_speed_mps=5.0, has_engineering=False, unit_id="u1")
        assert detected is False


# ---------------------------------------------------------------------------
# IED detonation
# ---------------------------------------------------------------------------


class TestIEDDetonation:
    """IED detonation returns blast details."""

    def test_detonate_ied(self):
        eng = _make_engine()
        ied_id = eng.emplace_ied(Position(50, 100, 0), "roadside", 15.0, 0.5, "ins")
        result = eng.detonate_ied(ied_id, "target_unit")
        assert isinstance(result, IEDDetonationResult)
        assert result.blast_radius_m == 15.0
        assert result.stress_spike > 0.0


# ---------------------------------------------------------------------------
# EW jamming
# ---------------------------------------------------------------------------


class TestEWJamming:
    """EW jamming of remote-detonated IEDs."""

    def test_ew_jamming_blocks_remote(self):
        """Remote (non command_wire/pressure_plate) IEDs can be jammed."""
        eng = _make_engine()
        ied_id = eng.emplace_ied(Position(0, 0, 0), "remote", 10.0, 0.5, "ins")
        # With 100% effectiveness, should always jam
        jammed = eng.check_ew_jamming(ied_id, jammer_active=True, jammer_effectiveness=1.0)
        assert jammed is True

    def test_command_wire_cannot_be_jammed(self):
        eng = _make_engine()
        ied_id = eng.emplace_ied(Position(0, 0, 0), "command_wire", 10.0, 0.5, "ins")
        jammed = eng.check_ew_jamming(ied_id, jammer_active=True, jammer_effectiveness=1.0)
        assert jammed is False

    def test_pressure_plate_cannot_be_jammed(self):
        eng = _make_engine()
        ied_id = eng.emplace_ied(Position(0, 0, 0), "pressure_plate", 10.0, 0.5, "ins")
        jammed = eng.check_ew_jamming(ied_id, jammer_active=True, jammer_effectiveness=1.0)
        assert jammed is False


# ---------------------------------------------------------------------------
# Guerrilla disengage
# ---------------------------------------------------------------------------


class TestGuerrillaDisengage:
    """Guerrilla disengage threshold and blend probability."""

    def test_disengage_above_threshold(self):
        eng = UnconventionalWarfareEngine(
            EventBus(), _rng(42),
            config_guerrilla=GuerrillaConfig(disengage_threshold=0.3),
        )
        disengage, blend_prob = eng.evaluate_guerrilla_disengage(
            "g1", casualties_fraction=0.5, in_populated_area=True,
        )
        assert disengage is True
        assert blend_prob > 0.0

    def test_no_disengage_below_threshold(self):
        eng = UnconventionalWarfareEngine(
            EventBus(), _rng(42),
            config_guerrilla=GuerrillaConfig(disengage_threshold=0.3),
        )
        disengage, blend_prob = eng.evaluate_guerrilla_disengage(
            "g1", casualties_fraction=0.1, in_populated_area=False,
        )
        assert disengage is False
        assert blend_prob == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Human shield
# ---------------------------------------------------------------------------


class TestHumanShield:
    """Human shield Pk reduction."""

    def test_high_civilian_density(self):
        eng = _make_engine()
        reduction = eng.evaluate_human_shield(Position(0, 0, 0), civilian_density=0.8)
        assert reduction == pytest.approx(0.8)

    def test_zero_civilian_density(self):
        eng = _make_engine()
        reduction = eng.evaluate_human_shield(Position(0, 0, 0), civilian_density=0.0)
        assert reduction == pytest.approx(0.0)

    def test_clamps_to_one(self):
        eng = _make_engine()
        reduction = eng.evaluate_human_shield(Position(0, 0, 0), civilian_density=1.5)
        assert reduction == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# State roundtrip
# ---------------------------------------------------------------------------


class TestUnconventionalStateRoundtrip:
    """State persistence."""

    def test_state_roundtrip(self):
        eng = _make_engine(seed=55)
        eng.emplace_ied(Position(10, 20, 0), "roadside", 10.0, 0.6, "ins")
        state = eng.get_state()

        eng2 = _make_engine(seed=1)
        eng2.set_state(state)
        assert eng2._next_id == eng._next_id
        assert len(eng2._ieds) == 1
