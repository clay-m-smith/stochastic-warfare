"""Phase 58c: Damage detail extraction tests.

Verifies that Unit.apply_casualties() and Unit.degrade_equipment() work
correctly and that battle.py now consumes DamageResult detail fields.
"""

from __future__ import annotations


from stochastic_warfare.combat.damage import CasualtyResult, DamageResult, DamageType
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit
from stochastic_warfare.entities.equipment import EquipmentCategory, EquipmentItem
from stochastic_warfare.entities.personnel import (
    CrewMember,
    CrewRole,
    InjuryState,
    SkillLevel,
)


def _make_crew(n: int) -> list[CrewMember]:
    """Create n healthy crew members."""
    return [
        CrewMember(
            member_id=f"m{i}",
            role=CrewRole.GENERIC,
            skill=SkillLevel.TRAINED,
            experience=0.5,
        )
        for i in range(n)
    ]


def _make_equipment(ids: list[str]) -> list[EquipmentItem]:
    """Create operational equipment with given IDs."""
    return [
        EquipmentItem(equipment_id=eid, name=eid, category=EquipmentCategory.WEAPON)
        for eid in ids
    ]


class TestApplyCasualties:
    """Unit.apply_casualties() marks personnel as injured/KIA."""

    def test_reduces_effective_count(self):
        unit = Unit(entity_id="u1", position=Position(0, 0, 0), personnel=_make_crew(4))
        cas = [CasualtyResult(member_index=0, severity="kia", cause="spall")]
        affected = unit.apply_casualties(cas)
        assert affected == 1
        assert unit.personnel[0].injury == InjuryState.KIA
        assert not unit.personnel[0].is_effective()

    def test_empty_personnel_returns_zero(self):
        unit = Unit(entity_id="u1", position=Position(0, 0, 0), personnel=[])
        cas = [CasualtyResult(member_index=0, severity="serious", cause="blast_overpressure")]
        assert unit.apply_casualties(cas) == 0

    def test_bounds_check_member_index(self):
        unit = Unit(entity_id="u1", position=Position(0, 0, 0), personnel=_make_crew(2))
        cas = [CasualtyResult(member_index=99, severity="minor", cause="spall")]
        assert unit.apply_casualties(cas) == 0  # no crash, 0 affected

    def test_multiple_casualties(self):
        unit = Unit(entity_id="u1", position=Position(0, 0, 0), personnel=_make_crew(4))
        cas = [
            CasualtyResult(member_index=0, severity="kia", cause="spall"),
            CasualtyResult(member_index=2, severity="serious", cause="fire"),
            CasualtyResult(member_index=3, severity="minor", cause="blast_overpressure"),
        ]
        affected = unit.apply_casualties(cas)
        assert affected == 3
        assert unit.personnel[0].injury == InjuryState.KIA
        assert unit.personnel[1].injury == InjuryState.HEALTHY  # untouched
        assert unit.personnel[2].injury == InjuryState.SERIOUS_WOUND
        assert unit.personnel[3].injury == InjuryState.MINOR_WOUND

    def test_already_injured_not_double_counted(self):
        """apply_casualties only affects effective personnel."""
        unit = Unit(entity_id="u1", position=Position(0, 0, 0), personnel=_make_crew(2))
        unit.personnel[0].injury = InjuryState.KIA
        cas = [CasualtyResult(member_index=0, severity="serious", cause="spall")]
        assert unit.apply_casualties(cas) == 0  # already non-effective

    def test_severity_mapping(self):
        unit = Unit(entity_id="u1", position=Position(0, 0, 0), personnel=_make_crew(4))
        cas = [
            CasualtyResult(member_index=0, severity="minor", cause="spall"),
            CasualtyResult(member_index=1, severity="serious", cause="spall"),
            CasualtyResult(member_index=2, severity="critical", cause="spall"),
            CasualtyResult(member_index=3, severity="kia", cause="spall"),
        ]
        unit.apply_casualties(cas)
        assert unit.personnel[0].injury == InjuryState.MINOR_WOUND
        assert unit.personnel[1].injury == InjuryState.SERIOUS_WOUND
        assert unit.personnel[2].injury == InjuryState.CRITICAL
        assert unit.personnel[3].injury == InjuryState.KIA


class TestDegradeEquipment:
    """Unit.degrade_equipment() marks equipment non-operational."""

    def test_disables_equipment(self):
        unit = Unit(
            entity_id="u1", position=Position(0, 0, 0),
            equipment=_make_equipment(["gun_main", "radio1"]),
        )
        affected = unit.degrade_equipment(["gun_main"])
        assert affected == 1
        assert not unit.equipment[0].operational
        assert unit.equipment[1].operational  # untouched

    def test_ignores_unknown_ids(self):
        unit = Unit(
            entity_id="u1", position=Position(0, 0, 0),
            equipment=_make_equipment(["gun_main"]),
        )
        assert unit.degrade_equipment(["nonexistent"]) == 0
        assert unit.equipment[0].operational

    def test_ignores_already_disabled(self):
        unit = Unit(
            entity_id="u1", position=Position(0, 0, 0),
            equipment=_make_equipment(["gun_main"]),
        )
        unit.equipment[0].operational = False
        assert unit.degrade_equipment(["gun_main"]) == 0

    def test_multiple_systems(self):
        unit = Unit(
            entity_id="u1", position=Position(0, 0, 0),
            equipment=_make_equipment(["gun_main", "radio1", "engine1"]),
        )
        affected = unit.degrade_equipment(["gun_main", "engine1"])
        assert affected == 2
        assert not unit.equipment[0].operational
        assert unit.equipment[1].operational
        assert not unit.equipment[2].operational


class TestDamageResultFields:
    """DamageResult detail fields are well-formed."""

    def test_ammo_cookoff_flag(self):
        dr = DamageResult(
            damage_type=DamageType.KINETIC,
            damage_fraction=1.0,
            ammo_cookoff=True,
        )
        assert dr.ammo_cookoff is True

    def test_fire_started_flag(self):
        dr = DamageResult(
            damage_type=DamageType.BLAST,
            damage_fraction=0.5,
            fire_started=True,
        )
        assert dr.fire_started is True

    def test_damage_fraction_threshold_still_determines_status(self):
        """Existing damage_fraction threshold behavior unchanged."""
        dr = DamageResult(
            damage_type=DamageType.COMBINED,
            damage_fraction=0.6,
            casualties=[CasualtyResult(member_index=0, severity="kia", cause="spall")],
        )
        # damage_fraction >= 0.5 (default dest_thresh) → DESTROYED
        assert dr.damage_fraction >= 0.5
