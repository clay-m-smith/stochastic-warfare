"""Personnel modeling — crew members, skills, casualties, experience."""

from __future__ import annotations

import enum
from dataclasses import dataclass

import numpy as np

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


class CrewRole(enum.IntEnum):
    """Functional role within a crew or squad."""

    COMMANDER = 0
    GUNNER = 1
    DRIVER = 2
    LOADER = 3
    RIFLEMAN = 4
    RADIOMAN = 5
    MEDIC = 6
    ENGINEER = 7
    NAVIGATOR = 8
    PILOT = 9
    COPILOT = 10
    CREW_CHIEF = 11
    SENSOR_OPERATOR = 12
    GENERIC = 99


class InjuryState(enum.IntEnum):
    """Progressive injury severity."""

    HEALTHY = 0
    MINOR_WOUND = 1
    SERIOUS_WOUND = 2
    CRITICAL = 3
    KIA = 4


class SkillLevel(enum.IntEnum):
    """Training / proficiency tier."""

    UNTRAINED = 0
    BASIC = 1
    TRAINED = 2
    EXPERIENCED = 3
    VETERAN = 4
    ELITE = 5


# Weight each role contributes to overall unit effectiveness.
_ROLE_WEIGHTS: dict[CrewRole, float] = {
    CrewRole.COMMANDER: 1.5,
    CrewRole.GUNNER: 1.3,
    CrewRole.DRIVER: 1.0,
    CrewRole.LOADER: 0.8,
    CrewRole.RIFLEMAN: 1.0,
    CrewRole.RADIOMAN: 0.9,
    CrewRole.MEDIC: 0.7,
    CrewRole.ENGINEER: 0.9,
    CrewRole.NAVIGATOR: 0.8,
    CrewRole.PILOT: 1.5,
    CrewRole.COPILOT: 1.2,
    CrewRole.CREW_CHIEF: 1.1,
    CrewRole.SENSOR_OPERATOR: 1.1,
    CrewRole.GENERIC: 0.8,
}


@dataclass
class CrewMember:
    """Individual soldier / crew member."""

    member_id: str
    role: CrewRole
    skill: SkillLevel
    experience: float  # 0.0–1.0 continuous progression within skill tier
    injury: InjuryState = InjuryState.HEALTHY
    fatigue: float = 0.0  # 0.0–1.0

    def is_effective(self) -> bool:
        """Return True if this member can still perform duties."""
        return self.injury <= InjuryState.MINOR_WOUND

    def get_state(self) -> dict:
        return {
            "member_id": self.member_id,
            "role": int(self.role),
            "skill": int(self.skill),
            "experience": self.experience,
            "injury": int(self.injury),
            "fatigue": self.fatigue,
        }

    def set_state(self, state: dict) -> None:
        self.member_id = state["member_id"]
        self.role = CrewRole(state["role"])
        self.skill = SkillLevel(state["skill"])
        self.experience = state["experience"]
        self.injury = InjuryState(state["injury"])
        self.fatigue = state["fatigue"]


class PersonnelManager:
    """Utility for applying casualties, computing crew effectiveness."""

    @staticmethod
    def apply_casualty(
        personnel: list[CrewMember], member_id: str, injury: InjuryState
    ) -> None:
        """Apply *injury* to the crew member with *member_id*."""
        for m in personnel:
            if m.member_id == member_id:
                m.injury = injury
                return
        raise KeyError(f"No crew member with id {member_id!r}")

    @staticmethod
    def role_effectiveness(personnel: list[CrewMember], role: CrewRole) -> float:
        """Return 0.0–1.0 effectiveness for *role* based on crew state.

        If multiple members share a role, returns the best among them.
        If no member fills the role, returns 0.0.
        """
        best = 0.0
        for m in personnel:
            if m.role == role and m.is_effective():
                # Skill contribution: 0.2 .. 1.0
                skill_factor = 0.2 + 0.16 * int(m.skill)
                # Injury penalty
                injury_factor = 1.0 if m.injury == InjuryState.HEALTHY else 0.6
                # Fatigue penalty
                fatigue_factor = 1.0 - 0.4 * m.fatigue
                eff = skill_factor * injury_factor * fatigue_factor
                if eff > best:
                    best = eff
        return best

    @staticmethod
    def crew_skill_average(personnel: list[CrewMember]) -> float:
        """Return average skill level (0–5 scale) of effective crew."""
        effective = [m for m in personnel if m.is_effective()]
        if not effective:
            return 0.0
        return sum(int(m.skill) for m in effective) / len(effective)

    @staticmethod
    def experience_gain(
        member: CrewMember,
        combat_hours: float,
        rng: np.random.Generator,
    ) -> None:
        """Stochastic experience progression from combat exposure.

        Experience grows toward 1.0 within the current skill tier. When
        experience reaches 1.0, skill advances one tier and experience
        resets.
        """
        if member.skill >= SkillLevel.ELITE:
            return
        # Base gain rate decreases with skill level
        base_rate = 0.02 / (1.0 + int(member.skill))
        gain = base_rate * combat_hours * (1.0 + 0.2 * rng.standard_normal())
        gain = max(0.0, gain)
        member.experience = min(1.0, member.experience + gain)
        if member.experience >= 1.0 and member.skill < SkillLevel.ELITE:
            member.skill = SkillLevel(int(member.skill) + 1)
            member.experience = 0.0

    @staticmethod
    def effective_count(personnel: list[CrewMember]) -> int:
        """Return count of personnel who can still perform duties."""
        return sum(1 for m in personnel if m.is_effective())
