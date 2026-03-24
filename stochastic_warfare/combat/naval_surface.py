"""Wayne Hughes salvo model for naval surface warfare.

Implements the offensive/defensive power exchange from Wayne Hughes'
*Fleet Tactics*, including ASHM launch, point-defense/CIWS layered
intercept, ship damage (flooding, fire, structural), damage control,
and mission-kill assessment.
"""

from __future__ import annotations

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
    enable_compartment_model: bool = False
    num_compartments_default: int = 8
    capsize_threshold: float = 0.6
    progressive_flooding_rate: float = 0.02  # per second per damaged bulkhead
    counter_flooding_rate: float = 0.01  # per second
    # Modern naval gun (Phase 27c)
    naval_gun_base_pk_per_round: float = 0.03
    naval_gun_fire_control_bonus: float = 1.5
    naval_gun_max_range_m: float = 24_000.0
    naval_gun_rate_of_fire_rpm: float = 20.0
    naval_gun_damage_per_hit: float = 0.05


@dataclass
class CompartmentConfig:
    """Per-ship compartment configuration for the flooding model."""

    num_compartments: int = 8
    capsize_threshold: float = 0.6
    progressive_flooding_rate: float = 0.02
    counter_flooding_rate: float = 0.01


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
    compartment_flooding: list[float] = field(default_factory=list)
    capsized: bool = False

    def get_state(self) -> dict[str, Any]:
        return {
            "ship_id": self.ship_id,
            "hull_integrity": self.hull_integrity,
            "flooding": self.flooding,
            "fire": self.fire,
            "structural": self.structural,
            "systems_damaged": list(self.systems_damaged),
            "compartment_flooding": list(self.compartment_flooding),
            "capsized": self.capsized,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self.ship_id = state["ship_id"]
        self.hull_integrity = state["hull_integrity"]
        self.flooding = state["flooding"]
        self.fire = state["fire"]
        self.structural = state["structural"]
        self.systems_damaged = list(state["systems_damaged"])
        self.compartment_flooding = list(state.get("compartment_flooding", []))
        self.capsized = state.get("capsized", False)


@dataclass
class NavalGunResult:
    """Outcome of a modern naval gun engagement."""

    ship_id: str
    target_id: str
    rounds_fired: int
    hits: int
    damage_per_hit: float
    total_damage: float
    range_m: float


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

    # ------------------------------------------------------------------
    # Compartment flooding model (Phase 12c-2)
    # ------------------------------------------------------------------

    def initialize_compartments(
        self,
        ship_id: str,
        num_compartments: int = 8,
    ) -> None:
        """Initialize compartment flooding array for a ship.

        Creates a zero-filled flooding list in the ship's damage state.
        If no damage state exists yet one is created.

        Parameters
        ----------
        ship_id:
            Entity ID of the ship.
        num_compartments:
            Number of watertight compartments (default 8).
        """
        if ship_id not in self._damage_states:
            self._damage_states[ship_id] = ShipDamageState(ship_id=ship_id)
        self._damage_states[ship_id].compartment_flooding = [0.0] * num_compartments
        logger.debug(
            "Initialized %d compartments for %s", num_compartments, ship_id,
        )

    def apply_compartment_damage(
        self,
        ship_id: str,
        hit_count: int,
        warhead_damage: float,
    ) -> None:
        """Apply warhead hits to random compartments.

        Each hit selects a random compartment and increases its flooding
        level by a fraction of the warhead damage (with stochastic
        variation).  Only operates when compartments are initialized.

        Parameters
        ----------
        ship_id:
            Entity ID of the ship.
        hit_count:
            Number of hits to distribute across compartments.
        warhead_damage:
            Base warhead damage fraction (0.0-1.0).
        """
        if ship_id not in self._damage_states:
            return
        state = self._damage_states[ship_id]
        if not state.compartment_flooding:
            return

        n = len(state.compartment_flooding)
        for _ in range(hit_count):
            idx = int(self._rng.integers(0, n))
            # Each hit floods between 50-100% of warhead_damage in that compartment
            flood_amount = warhead_damage * (0.5 + 0.5 * self._rng.random())
            state.compartment_flooding[idx] = min(
                1.0, state.compartment_flooding[idx] + flood_amount,
            )
        logger.debug(
            "Compartment damage to %s: %d hits (wd=%.2f), flooding=%s",
            ship_id, hit_count, warhead_damage, state.compartment_flooding,
        )

    def progressive_flooding(self, ship_id: str, dt: float) -> None:
        """Spread flooding through damaged bulkheads over time.

        For each compartment with flooding > 0, there is a probability
        per time step that adjacent compartments begin flooding.  The
        probability is proportional to the flooding level in the source
        compartment and the configured progressive flooding rate.

        Parameters
        ----------
        ship_id:
            Entity ID of the ship.
        dt:
            Time step in seconds.
        """
        if ship_id not in self._damage_states:
            return
        state = self._damage_states[ship_id]
        if not state.compartment_flooding:
            return

        n = len(state.compartment_flooding)
        rate = self._config.progressive_flooding_rate

        # Snapshot current levels so spreading is computed from pre-step state
        current = list(state.compartment_flooding)
        for i in range(n):
            if current[i] <= 0.0:
                continue
            # Probability of breaching each adjacent bulkhead this step
            p_spread = min(1.0, current[i] * rate * dt)
            for adj in (i - 1, i + 1):
                if 0 <= adj < n:
                    if self._rng.random() < p_spread:
                        spread_amount = current[i] * rate * dt
                        state.compartment_flooding[adj] = min(
                            1.0, state.compartment_flooding[adj] + spread_amount,
                        )

    def counter_flood(
        self,
        ship_id: str,
        dc_quality: float,
        dt: float,
    ) -> None:
        """Apply counter-flooding to reduce water in all compartments.

        Crew damage-control quality modulates how fast pumps and
        counter-flooding measures can drain compartments.

        Parameters
        ----------
        ship_id:
            Entity ID of the ship.
        dc_quality:
            Crew damage-control quality 0.0-1.0.
        dt:
            Time step in seconds.
        """
        if ship_id not in self._damage_states:
            return
        state = self._damage_states[ship_id]
        if not state.compartment_flooding:
            return

        rate = self._config.counter_flooding_rate * dc_quality
        for i in range(len(state.compartment_flooding)):
            if state.compartment_flooding[i] > 0.0:
                reduction = rate * dt * (0.5 + 0.5 * self._rng.random())
                state.compartment_flooding[i] = max(
                    0.0, state.compartment_flooding[i] - reduction,
                )

    def check_capsize(self, ship_id: str) -> bool:
        """Check whether a ship has capsized due to flooding.

        Capsize occurs when total flooding exceeds the capsize threshold
        **or** when asymmetric flooding (large port/starboard imbalance)
        exceeds half the threshold.  A capsized ship is permanently lost.

        Parameters
        ----------
        ship_id:
            Entity ID of the ship.

        Returns
        -------
        bool
            True if the ship has capsized.
        """
        if ship_id not in self._damage_states:
            return False
        state = self._damage_states[ship_id]
        if state.capsized:
            return True
        if not state.compartment_flooding:
            return False

        n = len(state.compartment_flooding)
        total = sum(state.compartment_flooding)
        avg_per_compartment = total / n

        # Overall flooding check
        if avg_per_compartment >= self._config.capsize_threshold:
            state.capsized = True
            state.hull_integrity = 0.0
            logger.info(
                "Ship %s capsized: average flooding %.2f >= threshold %.2f",
                ship_id, avg_per_compartment, self._config.capsize_threshold,
            )
            return True

        # Asymmetry check: compare port-side (first half) vs starboard (second half)
        mid = n // 2
        port_flood = sum(state.compartment_flooding[:mid]) / max(mid, 1)
        starboard_flood = sum(state.compartment_flooding[mid:]) / max(n - mid, 1)
        asymmetry = abs(port_flood - starboard_flood)
        if asymmetry >= self._config.capsize_threshold * 0.5:
            state.capsized = True
            state.hull_integrity = 0.0
            logger.info(
                "Ship %s capsized from asymmetry: port=%.2f starboard=%.2f "
                "(asymmetry %.2f >= %.2f)",
                ship_id, port_flood, starboard_flood,
                asymmetry, self._config.capsize_threshold * 0.5,
            )
            return True

        return False

    def naval_gun_engagement(
        self,
        ship_id: str,
        target_id: str,
        range_m: float,
        rounds_fired: int,
        fire_control_quality: float = 0.8,
        target_size_m2: float = 2000.0,
        sea_state: int = 3,
        timestamp: Any = None,
    ) -> NavalGunResult:
        """Modern radar-directed naval gun engagement.

        Pk per round = base * FC_bonus * range_factor * sea_state_factor.
        Each round resolved as independent Bernoulli trial.
        """
        cfg = self._config

        # Range factor: linear degradation
        if range_m > cfg.naval_gun_max_range_m:
            return NavalGunResult(
                ship_id=ship_id, target_id=target_id,
                rounds_fired=0, hits=0,
                damage_per_hit=cfg.naval_gun_damage_per_hit,
                total_damage=0.0, range_m=range_m,
            )
        range_factor = max(0.2, 1.0 - 0.8 * (range_m / cfg.naval_gun_max_range_m))

        # Sea state factor: degrades accuracy above state 4
        sea_factor = max(0.3, 1.0 - 0.15 * max(0, sea_state - 3))

        # Size factor: larger targets easier to hit
        size_factor = min(2.0, (target_size_m2 / 1000.0) ** 0.25)

        pk_per_round = (
            cfg.naval_gun_base_pk_per_round
            * cfg.naval_gun_fire_control_bonus
            * fire_control_quality
            * range_factor
            * sea_factor
            * size_factor
        )
        pk_per_round = max(0.001, min(0.5, pk_per_round))

        hits = int(self._rng.binomial(rounds_fired, pk_per_round))
        total_damage = hits * cfg.naval_gun_damage_per_hit

        if timestamp is not None and hits > 0:
            self._event_bus.publish(NavalEngagementEvent(
                timestamp=timestamp, source=ModuleId.COMBAT,
                attacker_id=ship_id, target_id=target_id,
                weapon_type="NAVAL_GUN",
            ))

        return NavalGunResult(
            ship_id=ship_id, target_id=target_id,
            rounds_fired=rounds_fired, hits=hits,
            damage_per_hit=cfg.naval_gun_damage_per_hit,
            total_damage=total_damage, range_m=range_m,
        )

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
