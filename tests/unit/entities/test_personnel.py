"""Tests for entities/personnel.py — crew members and personnel management."""

import numpy as np
import pytest

from stochastic_warfare.entities.personnel import (
    CrewMember,
    CrewRole,
    InjuryState,
    PersonnelManager,
    SkillLevel,
)


# ── CrewRole enum ────────────────────────────────────────────────────


class TestCrewRole:
    def test_basic_values(self) -> None:
        assert CrewRole.COMMANDER == 0
        assert CrewRole.GENERIC == 99

    def test_all_members_unique(self) -> None:
        values = [r.value for r in CrewRole]
        assert len(values) == len(set(values))


# ── InjuryState enum ────────────────────────────────────────────────


class TestInjuryState:
    def test_progression(self) -> None:
        assert InjuryState.HEALTHY < InjuryState.MINOR_WOUND
        assert InjuryState.MINOR_WOUND < InjuryState.SERIOUS_WOUND
        assert InjuryState.SERIOUS_WOUND < InjuryState.CRITICAL
        assert InjuryState.CRITICAL < InjuryState.KIA


# ── SkillLevel enum ─────────────────────────────────────────────────


class TestSkillLevel:
    def test_progression(self) -> None:
        assert SkillLevel.UNTRAINED < SkillLevel.BASIC < SkillLevel.ELITE

    def test_count(self) -> None:
        assert len(SkillLevel) == 6


# ── CrewMember ───────────────────────────────────────────────────────


class TestCrewMember:
    def test_creation(self) -> None:
        m = CrewMember("m1", CrewRole.GUNNER, SkillLevel.TRAINED, 0.5)
        assert m.member_id == "m1"
        assert m.role == CrewRole.GUNNER
        assert m.skill == SkillLevel.TRAINED
        assert m.experience == 0.5
        assert m.injury == InjuryState.HEALTHY
        assert m.fatigue == 0.0

    def test_is_effective_healthy(self) -> None:
        m = CrewMember("m1", CrewRole.DRIVER, SkillLevel.BASIC, 0.0)
        assert m.is_effective()

    def test_is_effective_minor_wound(self) -> None:
        m = CrewMember("m1", CrewRole.DRIVER, SkillLevel.BASIC, 0.0,
                       injury=InjuryState.MINOR_WOUND)
        assert m.is_effective()

    def test_not_effective_serious(self) -> None:
        m = CrewMember("m1", CrewRole.DRIVER, SkillLevel.BASIC, 0.0,
                       injury=InjuryState.SERIOUS_WOUND)
        assert not m.is_effective()

    def test_not_effective_kia(self) -> None:
        m = CrewMember("m1", CrewRole.DRIVER, SkillLevel.BASIC, 0.0,
                       injury=InjuryState.KIA)
        assert not m.is_effective()


class TestCrewMemberState:
    def test_get_state(self) -> None:
        m = CrewMember("m1", CrewRole.COMMANDER, SkillLevel.VETERAN, 0.7,
                       fatigue=0.3)
        state = m.get_state()
        assert state["member_id"] == "m1"
        assert state["role"] == int(CrewRole.COMMANDER)
        assert state["skill"] == int(SkillLevel.VETERAN)
        assert state["experience"] == 0.7
        assert state["fatigue"] == 0.3

    def test_roundtrip(self) -> None:
        original = CrewMember("m1", CrewRole.PILOT, SkillLevel.ELITE, 0.9,
                              injury=InjuryState.MINOR_WOUND, fatigue=0.5)
        state = original.get_state()
        restored = CrewMember("", CrewRole.GENERIC, SkillLevel.UNTRAINED, 0.0)
        restored.set_state(state)
        assert restored.member_id == original.member_id
        assert restored.role == original.role
        assert restored.skill == original.skill
        assert restored.experience == original.experience
        assert restored.injury == original.injury
        assert restored.fatigue == original.fatigue


# ── PersonnelManager ────────────────────────────────────────────────


class TestApplyCasualty:
    def _make_crew(self) -> list[CrewMember]:
        return [
            CrewMember("c1", CrewRole.COMMANDER, SkillLevel.VETERAN, 0.8),
            CrewMember("c2", CrewRole.GUNNER, SkillLevel.TRAINED, 0.5),
            CrewMember("c3", CrewRole.DRIVER, SkillLevel.BASIC, 0.2),
        ]

    def test_apply_minor(self) -> None:
        crew = self._make_crew()
        PersonnelManager.apply_casualty(crew, "c2", InjuryState.MINOR_WOUND)
        assert crew[1].injury == InjuryState.MINOR_WOUND

    def test_apply_kia(self) -> None:
        crew = self._make_crew()
        PersonnelManager.apply_casualty(crew, "c1", InjuryState.KIA)
        assert crew[0].injury == InjuryState.KIA

    def test_unknown_member_raises(self) -> None:
        crew = self._make_crew()
        with pytest.raises(KeyError):
            PersonnelManager.apply_casualty(crew, "nonexistent", InjuryState.KIA)


class TestRoleEffectiveness:
    def test_healthy_veteran(self) -> None:
        crew = [CrewMember("c1", CrewRole.GUNNER, SkillLevel.VETERAN, 0.8)]
        eff = PersonnelManager.role_effectiveness(crew, CrewRole.GUNNER)
        assert 0.8 < eff <= 1.0

    def test_no_member_for_role(self) -> None:
        crew = [CrewMember("c1", CrewRole.DRIVER, SkillLevel.TRAINED, 0.5)]
        eff = PersonnelManager.role_effectiveness(crew, CrewRole.GUNNER)
        assert eff == 0.0

    def test_injured_reduces_effectiveness(self) -> None:
        crew_healthy = [CrewMember("c1", CrewRole.GUNNER, SkillLevel.TRAINED, 0.5)]
        crew_wounded = [CrewMember("c1", CrewRole.GUNNER, SkillLevel.TRAINED, 0.5,
                                   injury=InjuryState.MINOR_WOUND)]
        eff_h = PersonnelManager.role_effectiveness(crew_healthy, CrewRole.GUNNER)
        eff_w = PersonnelManager.role_effectiveness(crew_wounded, CrewRole.GUNNER)
        assert eff_w < eff_h

    def test_fatigued_reduces_effectiveness(self) -> None:
        crew_fresh = [CrewMember("c1", CrewRole.GUNNER, SkillLevel.TRAINED, 0.5)]
        crew_tired = [CrewMember("c1", CrewRole.GUNNER, SkillLevel.TRAINED, 0.5,
                                 fatigue=0.8)]
        eff_f = PersonnelManager.role_effectiveness(crew_fresh, CrewRole.GUNNER)
        eff_t = PersonnelManager.role_effectiveness(crew_tired, CrewRole.GUNNER)
        assert eff_t < eff_f

    def test_serious_wound_not_effective(self) -> None:
        crew = [CrewMember("c1", CrewRole.GUNNER, SkillLevel.ELITE, 1.0,
                           injury=InjuryState.SERIOUS_WOUND)]
        eff = PersonnelManager.role_effectiveness(crew, CrewRole.GUNNER)
        assert eff == 0.0

    def test_best_of_multiple(self) -> None:
        crew = [
            CrewMember("c1", CrewRole.GUNNER, SkillLevel.BASIC, 0.2),
            CrewMember("c2", CrewRole.GUNNER, SkillLevel.VETERAN, 0.9),
        ]
        eff = PersonnelManager.role_effectiveness(crew, CrewRole.GUNNER)
        # Should return the veteran's effectiveness
        single_vet = PersonnelManager.role_effectiveness(
            [crew[1]], CrewRole.GUNNER
        )
        assert eff == single_vet


class TestCrewSkillAverage:
    def test_homogeneous(self) -> None:
        crew = [
            CrewMember("c1", CrewRole.COMMANDER, SkillLevel.TRAINED, 0.5),
            CrewMember("c2", CrewRole.GUNNER, SkillLevel.TRAINED, 0.5),
        ]
        avg = PersonnelManager.crew_skill_average(crew)
        assert avg == float(SkillLevel.TRAINED)

    def test_mixed(self) -> None:
        crew = [
            CrewMember("c1", CrewRole.COMMANDER, SkillLevel.ELITE, 0.9),
            CrewMember("c2", CrewRole.GUNNER, SkillLevel.BASIC, 0.2),
        ]
        avg = PersonnelManager.crew_skill_average(crew)
        assert avg == (int(SkillLevel.ELITE) + int(SkillLevel.BASIC)) / 2

    def test_kia_excluded(self) -> None:
        crew = [
            CrewMember("c1", CrewRole.COMMANDER, SkillLevel.ELITE, 0.9),
            CrewMember("c2", CrewRole.GUNNER, SkillLevel.BASIC, 0.2,
                       injury=InjuryState.KIA),
        ]
        avg = PersonnelManager.crew_skill_average(crew)
        assert avg == float(SkillLevel.ELITE)

    def test_empty_crew(self) -> None:
        assert PersonnelManager.crew_skill_average([]) == 0.0


class TestExperienceGain:
    def test_gain_is_positive(self) -> None:
        rng = np.random.Generator(np.random.PCG64(42))
        m = CrewMember("c1", CrewRole.GUNNER, SkillLevel.BASIC, 0.0)
        PersonnelManager.experience_gain(m, 10.0, rng)
        assert m.experience > 0.0

    def test_gain_deterministic(self) -> None:
        m1 = CrewMember("c1", CrewRole.GUNNER, SkillLevel.BASIC, 0.0)
        m2 = CrewMember("c1", CrewRole.GUNNER, SkillLevel.BASIC, 0.0)
        rng1 = np.random.Generator(np.random.PCG64(42))
        rng2 = np.random.Generator(np.random.PCG64(42))
        PersonnelManager.experience_gain(m1, 10.0, rng1)
        PersonnelManager.experience_gain(m2, 10.0, rng2)
        assert m1.experience == m2.experience

    def test_skill_advancement(self) -> None:
        rng = np.random.Generator(np.random.PCG64(42))
        m = CrewMember("c1", CrewRole.GUNNER, SkillLevel.BASIC, 0.99)
        # Push experience over 1.0 to trigger advancement
        PersonnelManager.experience_gain(m, 100.0, rng)
        assert m.skill >= SkillLevel.TRAINED

    def test_elite_no_further_gain(self) -> None:
        rng = np.random.Generator(np.random.PCG64(42))
        m = CrewMember("c1", CrewRole.GUNNER, SkillLevel.ELITE, 0.5)
        PersonnelManager.experience_gain(m, 100.0, rng)
        assert m.skill == SkillLevel.ELITE
        assert m.experience == 0.5  # unchanged

    def test_higher_skill_slower_gain(self) -> None:
        rng1 = np.random.Generator(np.random.PCG64(99))
        rng2 = np.random.Generator(np.random.PCG64(99))
        m_basic = CrewMember("c1", CrewRole.GUNNER, SkillLevel.BASIC, 0.0)
        m_vet = CrewMember("c2", CrewRole.GUNNER, SkillLevel.VETERAN, 0.0)
        PersonnelManager.experience_gain(m_basic, 10.0, rng1)
        PersonnelManager.experience_gain(m_vet, 10.0, rng2)
        assert m_basic.experience > m_vet.experience


class TestEffectiveCount:
    def test_all_healthy(self) -> None:
        crew = [
            CrewMember("c1", CrewRole.COMMANDER, SkillLevel.TRAINED, 0.5),
            CrewMember("c2", CrewRole.GUNNER, SkillLevel.TRAINED, 0.5),
            CrewMember("c3", CrewRole.DRIVER, SkillLevel.BASIC, 0.2),
        ]
        assert PersonnelManager.effective_count(crew) == 3

    def test_one_kia(self) -> None:
        crew = [
            CrewMember("c1", CrewRole.COMMANDER, SkillLevel.TRAINED, 0.5),
            CrewMember("c2", CrewRole.GUNNER, SkillLevel.TRAINED, 0.5,
                       injury=InjuryState.KIA),
        ]
        assert PersonnelManager.effective_count(crew) == 1

    def test_minor_wound_still_effective(self) -> None:
        crew = [
            CrewMember("c1", CrewRole.COMMANDER, SkillLevel.TRAINED, 0.5,
                       injury=InjuryState.MINOR_WOUND),
        ]
        assert PersonnelManager.effective_count(crew) == 1

    def test_empty_crew(self) -> None:
        assert PersonnelManager.effective_count([]) == 0
