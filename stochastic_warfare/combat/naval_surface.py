"""Wayne Hughes salvo model for naval surface warfare.

Implements the offensive/defensive power exchange from Wayne Hughes'
*Fleet Tactics*, including ASHM launch, point-defense/CIWS layered
intercept, ship damage (flooding, fire, structural), damage control,
and mission-kill assessment.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.events import NavalEngagementEvent, ShipDamageEvent
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId

logger = get_logger(__name__)


class NavalSurfaceConfig(BaseModel):
    """Tunable parameters for naval surface combat."""

    point_defense_pk: float = 0.3
    ciws_range_m: float = 1500.0
    ciws_pk: float = 0.5
    warhead_base_damage: float = 0.15
    damage_control_rate: float = 0.02  # fraction of damage repaired per second
    mission_kill_threshold: float = 0.5  # hull_integrity below this is mission kill
    chaff_effectiveness: float = 0.25  # fraction of missiles seduced by chaff
    fire_spread_probability: float = 0.1
    flooding_spread_probability: float = 0.15


@dataclass
class SalvoResult:
    """Outcome of a salvo exchange (offensive alpha vs defensive beta)."""

    missiles_fired: int
    offensive_power: float
    defensive_power: float
    leakers: int
    hits: int


@dataclass
class ShipDamageState:
    """Tracks cumulative damage to a ship."""

    ship_id: str
    hull_integrity: float = 1.0  # 1.0 = undamaged, 0.0 = sunk
    flooding: float = 0.0  # 0.0–1.0
    fire: float = 0.0  # 0.0–1.0
    structural: float = 0.0  # 0.0–1.0
    systems_damaged: list[str] = field(default_factory=list)

    def get_state(self) -> dict[str, Any]:
        return {
            "ship_id": self.ship_id,
            "hull_integrity": self.hull_integrity,
            "flooding": self.flooding,
            "fire": self.fire,
            "structural": self.structural,
            "systems_damaged": list(self.systems_damaged),
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self.ship_id = state["ship_id"]
        self.hull_integrity = state["hull_integrity"]
        self.flooding = state["flooding"]
        self.fire = state["fire"]
        self.structural = state["structural"]
        self.systems_damaged = list(state["systems_damaged"])


class NavalSurfaceEngine:
    """Wayne Hughes salvo model for surface engagements.

    Parameters
    ----------
    damage_engine:
        For resolving warhead damage.
    event_bus:
        For publishing naval engagement events.
    rng:
        PRNG generator.
    config:
        Tunable parameters.
    """

    def __init__(
        self,
        damage_engine: DamageEngine,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: NavalSurfaceConfig | None = None,
    ) -> None:
        self._damage = damage_engine
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or NavalSurfaceConfig()
        self._damage_states: dict[str, ShipDamageState] = {}

    def salvo_exchange(
        self,
        attacker_missiles: int,
        attacker_pk: float,
        defender_point_defense_count: int,
        defender_pd_pk: float,
        defender_chaff: bool = False,
        sea_state: int = 3,
    ) -> SalvoResult:
        """Compute a salvo exchange using the Hughes salvo model.

        Offensive power alpha = missiles * pk.
        Defensive power beta = point_defense_count * pd_pk.
        Leakers = max(0, alpha - beta), adjusted for chaff.

        Parameters
        ----------
        attacker_missiles:
            Number of ASHMs launched.
        attacker_pk:
            Probability of kill per missile (seeker quality).
        defender_point_defense_count:
            Number of point-defense engagements available.
        defender_pd_pk:
            Kill probability per point-defense engagement.
        defender_chaff:
            Whether the defender deploys chaff/decoys.
        sea_state:
            Sea state 0--9 (>4 degrades missile seekers and PD accuracy).
        """
        # Offensive power: expected hitting missiles
        alpha = attacker_missiles * attacker_pk

        # Chaff seduces a fraction before point defense engages
        if defender_chaff:
            chaff_seduced = alpha * self._config.chaff_effectiveness
            alpha = max(0.0, alpha - chaff_seduced)

        # Defensive power
        beta = defender_point_defense_count * defender_pd_pk

        # Sea state penalty: high seas degrade PD accuracy and missile seekers
        if sea_state > 4:
            sea_penalty = max(0.5, 1.0 - 0.1 * (sea_state - 4))
            beta *= sea_penalty  # PD less effective in rough seas
            alpha *= sea_penalty  # Missile seekers also degraded

        # Leakers (stochastic)
        expected_leakers = max(0.0, alpha - beta)
        # Realize with binomial draw: each surviving missile has pk of hitting
        surviving = max(0, attacker_missiles - int(round(beta / max(attacker_pk, 0.01))))
        if surviving > 0 and attacker_pk > 0:
            hits = int(self._rng.binomial(surviving, min(attacker_pk, 1.0)))
        else:
            hits = 0

        # If chaff is active, some hits are seduced
        if defender_chaff and hits > 0:
            chaff_saves = int(self._rng.binomial(hits, self._config.chaff_effectiveness))
            hits = max(0, hits - chaff_saves)

        leakers = max(0, int(round(expected_leakers)))

        return SalvoResult(
            missiles_fired=attacker_missiles,
            offensive_power=alpha,
            defensive_power=beta,
            leakers=leakers,
            hits=hits,
        )

    def launch_ashm(
        self,
        shooter_id: str,
        target_id: str,
        missile_count: int,
        missile_pk: float,
        timestamp: Any = None,
    ) -> list[str]:
        """Launch anti-ship missiles. Returns missile IDs.

        Parameters
        ----------
        shooter_id:
            Entity ID of the attacking ship.
        target_id:
            Entity ID of the target ship.
        missile_count:
            Number of missiles to fire.
        missile_pk:
            Kill probability per missile.
        timestamp:
            Simulation timestamp for events.
        """
        missile_ids = [f"{shooter_id}_ashm_{i}" for i in range(missile_count)]

        if timestamp is not None:
            self._event_bus.publish(NavalEngagementEvent(
                timestamp=timestamp, source=ModuleId.COMBAT,
                attacker_id=shooter_id, target_id=target_id,
                weapon_type="ASHM",
            ))

        logger.debug(
            "Launched %d ASHMs from %s at %s (pk=%.2f)",
            missile_count, shooter_id, target_id, missile_pk,
        )
        return missile_ids

    def point_defense(
        self,
        defender_id: str,
        incoming_count: int,
        pd_pk: float,
        ciws_pk: float | None = None,
    ) -> int:
        """Resolve point-defense engagements. Returns number intercepted.

        Two-layer defense: SAM/SeaRAM point defense then CIWS for leakers.

        Parameters
        ----------
        defender_id:
            Entity ID of the defending ship.
        incoming_count:
            Number of incoming missiles.
        pd_pk:
            Kill probability for the outer point-defense layer.
        ciws_pk:
            Kill probability for CIWS (inner layer). Uses config default
            if not provided.
        """
        if ciws_pk is None:
            ciws_pk = self._config.ciws_pk

        # Outer layer: point defense
        pd_intercepts = int(self._rng.binomial(incoming_count, min(pd_pk, 1.0)))
        remaining = incoming_count - pd_intercepts

        # Inner layer: CIWS
        ciws_intercepts = 0
        if remaining > 0:
            ciws_intercepts = int(self._rng.binomial(remaining, min(ciws_pk, 1.0)))

        total_intercepted = pd_intercepts + ciws_intercepts
        logger.debug(
            "Point defense %s: %d incoming, %d intercepted (PD=%d, CIWS=%d)",
            defender_id, incoming_count, total_intercepted,
            pd_intercepts, ciws_intercepts,
        )
        return total_intercepted

    def apply_ship_damage(
        self,
        ship_id: str,
        hit_count: int,
        warhead_damage: float | None = None,
        timestamp: Any = None,
    ) -> ShipDamageState:
        """Apply missile hit damage to a ship.

        Parameters
        ----------
        ship_id:
            Entity ID of the ship.
        hit_count:
            Number of missile hits.
        warhead_damage:
            Damage per warhead hit (0.0–1.0 hull fraction). Uses config
            default if not provided.
        timestamp:
            Simulation timestamp for events.
        """
        if warhead_damage is None:
            warhead_damage = self._config.warhead_base_damage

        if ship_id not in self._damage_states:
            self._damage_states[ship_id] = ShipDamageState(ship_id=ship_id)

        state = self._damage_states[ship_id]

        for _ in range(hit_count):
            # Structural damage
            structural_hit = warhead_damage * (0.5 + 0.5 * self._rng.random())
            state.structural = min(1.0, state.structural + structural_hit)

            # Flooding (probabilistic)
            if self._rng.random() < self._config.flooding_spread_probability:
                flood_amount = warhead_damage * 0.5 * self._rng.random()
                state.flooding = min(1.0, state.flooding + flood_amount)

            # Fire (probabilistic)
            if self._rng.random() < self._config.fire_spread_probability:
                fire_amount = warhead_damage * 0.4 * self._rng.random()
                state.fire = min(1.0, state.fire + fire_amount)

            # System damage
            systems = ["propulsion", "weapons", "sensors", "communications", "navigation"]
            if self._rng.random() < 0.4:
                damaged_sys = systems[int(self._rng.integers(0, len(systems)))]
                if damaged_sys not in state.systems_damaged:
                    state.systems_damaged.append(damaged_sys)

        # Hull integrity = 1 - combined damage effects
        combined = state.structural + 0.5 * state.flooding + 0.3 * state.fire
        state.hull_integrity = max(0.0, 1.0 - combined)

        if timestamp is not None:
            self._event_bus.publish(ShipDamageEvent(
                timestamp=timestamp, source=ModuleId.COMBAT,
                ship_id=ship_id, damage_type="missile",
                severity=1.0 - state.hull_integrity,
                system_affected=",".join(state.systems_damaged) or "none",
            ))

        return state

    def damage_control(
        self,
        damage_state: ShipDamageState,
        dc_crew_quality: float,
        dt: float,
    ) -> None:
        """Apply damage control to reduce flooding and fire over time.

        Parameters
        ----------
        damage_state:
            Current damage state to modify in place.
        dc_crew_quality:
            Crew damage-control quality 0.0–1.0 (affects repair rate).
        dt:
            Time step in seconds.
        """
        rate = self._config.damage_control_rate * dc_crew_quality

        # Fight flooding
        if damage_state.flooding > 0:
            repair = rate * dt * (0.5 + 0.5 * self._rng.random())
            damage_state.flooding = max(0.0, damage_state.flooding - repair)

        # Fight fire
        if damage_state.fire > 0:
            repair = rate * dt * (0.5 + 0.5 * self._rng.random())
            damage_state.fire = max(0.0, damage_state.fire - repair)

        # Recalculate hull integrity
        combined = damage_state.structural + 0.5 * damage_state.flooding + 0.3 * damage_state.fire
        damage_state.hull_integrity = max(0.0, 1.0 - combined)

    def assess_mission_kill(self, hull_integrity: float) -> bool:
        """Assess whether a ship has suffered a mission kill.

        Parameters
        ----------
        hull_integrity:
            Current hull integrity 0.0–1.0.
        """
        return hull_integrity < self._config.mission_kill_threshold

    def get_state(self) -> dict[str, Any]:
        return {
            "rng_state": self._rng.bit_generator.state,
            "damage_states": {
                sid: ds.get_state()
                for sid, ds in self._damage_states.items()
            },
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]
        self._damage_states = {}
        for sid, ds_dict in state["damage_states"].items():
            ds = ShipDamageState(ship_id=sid)
            ds.set_state(ds_dict)
            self._damage_states[sid] = ds
