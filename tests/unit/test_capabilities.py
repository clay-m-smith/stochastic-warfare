"""Tests for entities/capabilities.py — combat power assessment."""

import pytest

from stochastic_warfare.core.types import Domain, Position, Side
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.entities.capabilities import (
    CombatPowerAssessment,
    CombatPowerCalculator,
    CombatPowerFactors,
)
from stochastic_warfare.entities.equipment import EquipmentCategory, EquipmentItem
from stochastic_warfare.entities.personnel import (
    CrewMember,
    CrewRole,
    InjuryState,
    SkillLevel,
)


def _make_full_unit(
    status: UnitStatus = UnitStatus.ACTIVE,
    skill: SkillLevel = SkillLevel.TRAINED,
    injury: InjuryState = InjuryState.HEALTHY,
    fatigue: float = 0.0,
    equip_operational: bool = True,
) -> Unit:
    """Helper to create a unit with 4 crew and 3 equipment items."""
    crew = [
        CrewMember("c0", CrewRole.COMMANDER, skill, 0.5, injury, fatigue),
        CrewMember("c1", CrewRole.GUNNER, skill, 0.5, injury, fatigue),
        CrewMember("c2", CrewRole.DRIVER, skill, 0.3, injury, fatigue),
        CrewMember("c3", CrewRole.LOADER, skill, 0.2, injury, fatigue),
    ]
    gear = [
        EquipmentItem("e0", "Gun", EquipmentCategory.WEAPON, operational=equip_operational),
        EquipmentItem("e1", "Engine", EquipmentCategory.PROPULSION, operational=equip_operational),
        EquipmentItem("e2", "Radio", EquipmentCategory.COMMUNICATION, operational=True),
    ]
    return Unit(
        entity_id="u1", position=Position(0.0, 0.0),
        name="Test", unit_type="test", side=Side.BLUE,
        status=status, personnel=crew, equipment=gear,
    )


class TestCombatPowerFactors:
    def test_full_strength(self) -> None:
        calc = CombatPowerCalculator()
        u = _make_full_unit()
        f = calc.factors(u)
        assert f.personnel_strength == 1.0
        assert f.equipment_readiness == 1.0
        assert f.fatigue == 1.0

    def test_half_casualties(self) -> None:
        calc = CombatPowerCalculator()
        u = _make_full_unit()
        u.personnel[0].injury = InjuryState.KIA
        u.personnel[1].injury = InjuryState.CRITICAL
        f = calc.factors(u)
        assert f.personnel_strength == 0.5

    def test_equipment_broken(self) -> None:
        calc = CombatPowerCalculator()
        u = _make_full_unit(equip_operational=False)
        f = calc.factors(u)
        # Only the radio (index 2) is operational
        assert f.equipment_readiness == pytest.approx(1.0 / 3.0, abs=0.01)

    def test_fatigue_reduces(self) -> None:
        calc = CombatPowerCalculator()
        u = _make_full_unit(fatigue=0.8)
        f = calc.factors(u)
        assert f.fatigue < 1.0

    def test_training_scales(self) -> None:
        calc = CombatPowerCalculator()
        u_basic = _make_full_unit(skill=SkillLevel.BASIC)
        u_elite = _make_full_unit(skill=SkillLevel.ELITE)
        f_basic = calc.factors(u_basic)
        f_elite = calc.factors(u_elite)
        assert f_elite.training_level > f_basic.training_level


class TestCombatPowerAssessment:
    def test_full_unit(self) -> None:
        calc = CombatPowerCalculator()
        u = _make_full_unit()
        a = calc.assess(u)
        assert a.raw_power > 0
        assert a.effective_power > 0
        assert a.readiness > 0

    def test_destroyed_unit(self) -> None:
        calc = CombatPowerCalculator()
        u = _make_full_unit(status=UnitStatus.DESTROYED)
        a = calc.assess(u)
        assert a.raw_power == 0.0
        assert a.effective_power == 0.0
        assert a.readiness == 0.0

    def test_surrendered_unit(self) -> None:
        calc = CombatPowerCalculator()
        u = _make_full_unit(status=UnitStatus.SURRENDERED)
        a = calc.assess(u)
        assert a.effective_power == 0.0

    def test_routing_penalty(self) -> None:
        calc = CombatPowerCalculator()
        u_active = _make_full_unit()
        u_routing = _make_full_unit(status=UnitStatus.ROUTING)
        a_active = calc.assess(u_active)
        a_routing = calc.assess(u_routing)
        assert a_routing.effective_power < a_active.effective_power

    def test_degraded_unit_lower_power(self) -> None:
        calc = CombatPowerCalculator()
        u_full = _make_full_unit()
        u_degraded = _make_full_unit(fatigue=0.8, equip_operational=False)
        a_full = calc.assess(u_full)
        a_degraded = calc.assess(u_degraded)
        assert a_degraded.effective_power < a_full.effective_power

    def test_no_personnel(self) -> None:
        calc = CombatPowerCalculator()
        u = Unit(entity_id="u1", position=Position(0.0, 0.0))
        a = calc.assess(u)
        assert a.raw_power == 0.0


class TestForceRatio:
    def test_equal_forces(self) -> None:
        calc = CombatPowerCalculator()
        f = [_make_full_unit()]
        e = [_make_full_unit()]
        ratio = calc.force_ratio(f, e)
        assert ratio == pytest.approx(1.0)

    def test_two_to_one(self) -> None:
        calc = CombatPowerCalculator()
        f = [_make_full_unit(), _make_full_unit()]
        e = [_make_full_unit()]
        ratio = calc.force_ratio(f, e)
        assert ratio == pytest.approx(2.0)

    def test_no_enemy(self) -> None:
        calc = CombatPowerCalculator()
        f = [_make_full_unit()]
        ratio = calc.force_ratio(f, [])
        assert ratio == float("inf")

    def test_no_friendly(self) -> None:
        calc = CombatPowerCalculator()
        e = [_make_full_unit()]
        ratio = calc.force_ratio([], e)
        assert ratio == 0.0

    def test_degraded_enemy(self) -> None:
        calc = CombatPowerCalculator()
        f = [_make_full_unit()]
        e = [_make_full_unit(fatigue=0.9, equip_operational=False)]
        ratio = calc.force_ratio(f, e)
        assert ratio > 1.0
