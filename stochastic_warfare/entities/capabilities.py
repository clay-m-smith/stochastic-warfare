"""Combat power assessment from unit state."""

from __future__ import annotations

from typing import NamedTuple

from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.entities.equipment import EquipmentManager
from stochastic_warfare.entities.personnel import PersonnelManager


class CombatPowerFactors(NamedTuple):
    """Individual factors that compose combat power."""

    personnel_strength: float
    equipment_readiness: float
    training_level: float
    fatigue: float
    supply_state: float
    leadership: float


class CombatPowerAssessment(NamedTuple):
    """Result of assessing a unit's combat power."""

    raw_power: float
    effective_power: float
    readiness: float


class CombatPowerCalculator:
    """Assess unit combat power from personnel, equipment, and status."""

    def factors(
        self, unit: Unit, supply_state_override: float | None = None,
    ) -> CombatPowerFactors:
        """Break down the individual factors contributing to combat power.

        Parameters
        ----------
        supply_state_override:
            If provided, use this value (0-1) for the supply state factor
            instead of the default 1.0.  The simulation loop (Phase 9)
            queries the logistics ``StockpileManager.get_supply_state()``
            and passes the result here.
        """
        if not unit.personnel:
            personnel_strength = 0.0
        else:
            personnel_strength = (
                PersonnelManager.effective_count(unit.personnel) / len(unit.personnel)
            )

        equipment_readiness = EquipmentManager.operational_readiness(unit.equipment)
        training_level = PersonnelManager.crew_skill_average(unit.personnel) / 5.0
        fatigue = 1.0 - (
            sum(m.fatigue for m in unit.personnel) / max(len(unit.personnel), 1)
        )
        # Supply state from logistics StockpileManager (Phase 6)
        supply_state = supply_state_override if supply_state_override is not None else 1.0
        # Leadership from commander effectiveness
        from stochastic_warfare.entities.personnel import CrewRole

        leadership = PersonnelManager.role_effectiveness(
            unit.personnel, CrewRole.COMMANDER
        )
        if leadership == 0.0:
            leadership = 0.3  # leaderless penalty

        return CombatPowerFactors(
            personnel_strength=personnel_strength,
            equipment_readiness=equipment_readiness,
            training_level=training_level,
            fatigue=fatigue,
            supply_state=supply_state,
            leadership=leadership,
        )

    def assess(self, unit: Unit) -> CombatPowerAssessment:
        """Compute overall combat power for *unit*."""
        if unit.status in (UnitStatus.DESTROYED, UnitStatus.SURRENDERED):
            return CombatPowerAssessment(0.0, 0.0, 0.0)

        f = self.factors(unit)

        # Raw power: simple product of strength factors
        raw = f.personnel_strength * f.equipment_readiness
        # Effective power: modulated by training, fatigue, leadership
        effective = raw * f.training_level * f.fatigue * f.leadership
        # Readiness: geometric mean of key factors
        readiness = (f.personnel_strength * f.equipment_readiness * f.fatigue) ** (
            1.0 / 3.0
        )

        if unit.status == UnitStatus.ROUTING:
            effective *= 0.3

        return CombatPowerAssessment(
            raw_power=round(raw, 6),
            effective_power=round(effective, 6),
            readiness=round(readiness, 6),
        )

    def force_ratio(
        self, friendly: list[Unit], enemy: list[Unit]
    ) -> float:
        """Return friendly:enemy effective power ratio.

        Returns ``float('inf')`` if enemy power is zero.
        """
        f_power = sum(self.assess(u).effective_power for u in friendly)
        e_power = sum(self.assess(u).effective_power for u in enemy)
        if e_power == 0.0:
            return float("inf")
        return f_power / e_power
