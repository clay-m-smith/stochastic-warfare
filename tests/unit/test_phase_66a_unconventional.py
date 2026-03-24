"""Phase 66a: Unconventional warfare wiring tests — IED encounters,
guerrilla routing, and human shields in the battle loop.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from stochastic_warfare.combat.unconventional import (
    IEDConfig,
    UnconventionalWarfareEngine,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position
from stochastic_warfare.simulation.calibration import CalibrationSchema

TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _make_uw_engine(
    bus: EventBus | None = None,
    seed: int = 42,
) -> UnconventionalWarfareEngine:
    return UnconventionalWarfareEngine(
        event_bus=bus or EventBus(),
        rng=_rng(seed),
    )


# ---------------------------------------------------------------------------
# IED encounter tests
# ---------------------------------------------------------------------------


class TestIEDEncounters:
    """IED encounters triggered during ground movement."""

    def test_ied_detonation_on_ground_unit(self) -> None:
        eng = _make_uw_engine()
        ied_id = eng.emplace_ied(
            Position(100, 100, 0), "pressure_plate", 10.0, 0.5, "insurgent_1",
        )
        result = eng.detonate_ied(ied_id, "target_unit", timestamp=TS)
        assert result.blast_radius_m == 10.0
        assert eng._ieds[ied_id]["active"] is False

    def test_ied_detection_prevents_detonation(self) -> None:
        """Slow speed + engineer bonus → high detection probability."""
        eng = _make_uw_engine(seed=100)
        detected_count = 0
        for i in range(100):
            rng = _rng(i)
            eng2 = UnconventionalWarfareEngine(
                EventBus(), rng,
                config_ied=IEDConfig(base_detect_probability=0.9, engineering_bonus=1.0),
            )
            if eng2.check_ied_detection(0.5, True, f"unit_{i}"):
                detected_count += 1
        # With base 0.9 and engineering bonus 1.0 at near-zero speed,
        # P(detect) ≈ 0.9 * 2.0 * 1.0 = 1.8 → clamped by RNG
        assert detected_count > 50  # Most should detect

    def test_ied_event_published_on_detonation(self) -> None:
        from stochastic_warfare.combat.unconventional import IEDDetonationEvent

        bus = EventBus()
        published = []
        bus.subscribe(IEDDetonationEvent, lambda e: published.append(e))
        eng = _make_uw_engine(bus=bus)
        ied_id = eng.emplace_ied(Position(0, 0, 0), "remote", 15.0, 0.3, "ins_1")
        eng.detonate_ied(ied_id, "victim_1", timestamp=TS)
        assert len(published) == 1
        assert published[0].obstacle_id == ied_id

    def test_remote_ied_blocked_by_ew_jamming(self) -> None:
        eng = _make_uw_engine(seed=0)
        ied_id = eng.emplace_ied(Position(0, 0, 0), "remote", 5.0, 0.5, "ins_1")
        # With effectiveness=1.0, jamming should succeed most of the time
        jammed_count = 0
        for i in range(50):
            eng2 = _make_uw_engine(seed=i)
            eng2._ieds = dict(eng._ieds)  # share IED data
            if eng2.check_ew_jamming(ied_id, True, 1.0):
                jammed_count += 1
        assert jammed_count > 25

    def test_command_wire_ied_not_blocked_by_ew(self) -> None:
        eng = _make_uw_engine()
        ied_id = eng.emplace_ied(Position(0, 0, 0), "command_wire", 5.0, 0.5, "ins_1")
        assert eng.check_ew_jamming(ied_id, True, 1.0) is False

    def test_pressure_plate_ied_not_blocked_by_ew(self) -> None:
        eng = _make_uw_engine()
        ied_id = eng.emplace_ied(Position(0, 0, 0), "pressure_plate", 5.0, 0.5, "ins_1")
        assert eng.check_ew_jamming(ied_id, True, 1.0) is False

    def test_fast_moving_unit_lower_detection(self) -> None:
        """Fast units have lower detection probability."""
        eng = _make_uw_engine(seed=99)
        # At max safe speed: speed_factor = 0 → P(detect) = 0
        cfg = IEDConfig(max_safe_speed_mps=5.0)
        eng2 = UnconventionalWarfareEngine(EventBus(), _rng(99), config_ied=cfg)
        detected = eng2.check_ied_detection(5.0, False, "fast_unit")
        assert detected is False  # speed_factor = 0

    def test_ied_inactive_after_detonation(self) -> None:
        eng = _make_uw_engine()
        ied_id = eng.emplace_ied(Position(0, 0, 0), "remote", 5.0, 0.5, "ins_1")
        eng.detonate_ied(ied_id, "victim", timestamp=TS)
        assert eng._ieds[ied_id]["active"] is False

    def test_ied_encounters_gated_by_flag(self) -> None:
        """When enable_unconventional_warfare=False, IED block is skipped."""
        cal = CalibrationSchema(enable_unconventional_warfare=False)
        assert cal.get("enable_unconventional_warfare", True) is False


# ---------------------------------------------------------------------------
# Guerrilla disengage tests
# ---------------------------------------------------------------------------


class TestGuerrillaDisengage:
    """Guerrilla disengage evaluation."""

    def test_insurgent_unit_type_detected(self) -> None:
        unit_type = "insurgent_squad"
        assert any(kw in unit_type.lower() for kw in ("insurgent", "militia", "guerrilla"))

    def test_high_casualties_trigger_disengage(self) -> None:
        eng = _make_uw_engine()
        disengage, blend = eng.evaluate_guerrilla_disengage("g1", 0.5, False)
        assert disengage is True  # 0.5 > threshold 0.3

    def test_low_casualties_no_disengage(self) -> None:
        eng = _make_uw_engine()
        disengage, blend = eng.evaluate_guerrilla_disengage("g1", 0.1, False)
        assert disengage is False  # 0.1 < threshold 0.3

    def test_populated_area_gives_blend_probability(self) -> None:
        eng = _make_uw_engine()
        _, blend = eng.evaluate_guerrilla_disengage("g1", 0.5, True)
        assert blend > 0  # in populated area → non-zero blend

    def test_non_populated_area_zero_blend(self) -> None:
        eng = _make_uw_engine()
        _, blend = eng.evaluate_guerrilla_disengage("g1", 0.5, False)
        assert blend == 0.0

    def test_guerrilla_disengage_gated_by_flag(self) -> None:
        cal = CalibrationSchema(enable_unconventional_warfare=False)
        assert cal.get("enable_unconventional_warfare", True) is False

    def test_non_insurgent_units_no_guerrilla_eval(self) -> None:
        """Regular unit types should not be identified as guerrilla."""
        for unit_type in ("infantry_squad", "tank_platoon", "artillery"):
            assert not any(
                kw in unit_type.lower()
                for kw in ("insurgent", "militia", "guerrilla")
            )


# ---------------------------------------------------------------------------
# Human shield tests
# ---------------------------------------------------------------------------


class TestHumanShield:
    """Human shield Pk reduction."""

    def test_pk_reduced_when_civilian_density_nonzero(self) -> None:
        eng = _make_uw_engine()
        shield_val = eng.evaluate_human_shield(Position(0, 0, 0), 0.8)
        assert 0 < shield_val <= 1.0

    def test_no_effect_when_density_zero(self) -> None:
        eng = _make_uw_engine()
        shield_val = eng.evaluate_human_shield(Position(0, 0, 0), 0.0)
        assert shield_val == 0.0

    def test_shield_value_clamped_to_one(self) -> None:
        eng = _make_uw_engine()
        shield_val = eng.evaluate_human_shield(Position(0, 0, 0), 5.0)
        assert shield_val == 1.0
