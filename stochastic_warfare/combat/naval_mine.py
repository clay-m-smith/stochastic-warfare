"""Mine warfare — laying, transit risk, triggering, sweeping.

Models mine types (contact, magnetic, acoustic, pressure, combination,
rising, smart), minefield laying, transit risk computation, individual
mine encounter resolution, and mine countermeasures (sweeping).
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.events import MineEvent
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position

logger = get_logger(__name__)


class MineType(enum.IntEnum):
    """Mine classification by trigger mechanism."""

    CONTACT = 0
    MAGNETIC = 1
    ACOUSTIC = 2
    PRESSURE = 3
    COMBINATION = 4
    RISING = 5
    SMART = 6


class MCMMode(enum.IntEnum):
    """Mine countermeasures operational mode."""

    SURFACE_SWEEP = 0
    BOTTOM_SEARCH = 1
    HUNTING = 2
    ROUTE_SURVEY = 3


class MineWarfareConfig(BaseModel):
    """Tunable parameters for mine warfare."""

    contact_trigger_radius_m: float = 5.0
    magnetic_trigger_radius_m: float = 50.0
    acoustic_trigger_radius_m: float = 100.0
    pressure_trigger_radius_m: float = 30.0
    rising_mine_speed_mps: float = 15.0
    smart_mine_selectivity: float = 0.8  # probability of classifying target correctly
    base_sweep_rate_m2_per_s: float = 500.0
    mine_damage_fraction: float = 0.25
    dud_rate: float = 0.05


@dataclass
class ShipMineSignature:
    """Ship signature profile for mine triggering.

    All signature values are normalized 0-1 unless otherwise noted.
    """

    acoustic_db: float = 0.5
    magnetic_tesla: float = 0.5
    pressure_kpa: float = 0.5
    displacement_tons: float = 5000.0


@dataclass
class Mine:
    """A single mine."""

    mine_id: str
    position: Position
    mine_type: MineType
    armed: bool = True
    detonated: bool = False

    def get_state(self) -> dict[str, Any]:
        return {
            "mine_id": self.mine_id,
            "position": tuple(self.position),
            "mine_type": int(self.mine_type),
            "armed": self.armed,
            "detonated": self.detonated,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self.mine_id = state["mine_id"]
        self.position = Position(*state["position"])
        self.mine_type = MineType(state["mine_type"])
        self.armed = state["armed"]
        self.detonated = state["detonated"]


@dataclass
class MineResult:
    """Outcome of a mine encounter."""

    mine_id: str
    triggered: bool
    detonated: bool
    dud: bool = False
    damage_fraction: float = 0.0


@dataclass
class SweepResult:
    """Outcome of a mine-sweeping operation."""

    mines_swept: int
    mines_neutralized: int
    area_cleared_m2: float
    sweep_time_s: float


@dataclass
class TransitRisk:
    """Risk assessment for transiting a mined area."""

    encounter_probability: float  # probability of encountering at least one mine
    expected_encounters: float  # expected number of mine encounters
    risk_level: str  # "low", "medium", "high", "extreme"


class MineWarfareEngine:
    """Mine warfare: laying, transit risk, encounter resolution, sweeping.

    Parameters
    ----------
    damage_engine:
        For resolving mine detonation damage.
    event_bus:
        For publishing mine events.
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
        config: MineWarfareConfig | None = None,
    ) -> None:
        self._damage = damage_engine
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or MineWarfareConfig()
        self._mine_counter: int = 0
        self._mines: list[Mine] = []

    def lay_mines(
        self,
        layer_id: str,
        positions: list[Position],
        mine_type: MineType,
        count_per_pos: int = 1,
        delivery_method: str = "surface",
        placement_accuracy_m: float = 0.0,
    ) -> list[Mine]:
        """Lay mines at specified positions.

        Parameters
        ----------
        layer_id:
            Entity ID of the mine-laying vessel/unit.
        positions:
            Positions at which to lay mines.
        mine_type:
            Type of mine to lay.
        count_per_pos:
            Number of mines per position.
        delivery_method:
            How mines are delivered (``"surface"``, ``"air"``, ``"submarine"``).
        placement_accuracy_m:
            When > 0, apply Gaussian scatter (standard deviation in meters)
            to each mine's position.
        """
        laid: list[Mine] = []

        for pos in positions:
            for _ in range(count_per_pos):
                self._mine_counter += 1
                if placement_accuracy_m > 0.0:
                    offset_e = self._rng.normal(0.0, placement_accuracy_m)
                    offset_n = self._rng.normal(0.0, placement_accuracy_m)
                    actual_pos = Position(
                        pos.easting + offset_e,
                        pos.northing + offset_n,
                        pos.altitude,
                    )
                else:
                    actual_pos = pos
                mine = Mine(
                    mine_id=f"{layer_id}_mine_{self._mine_counter}",
                    position=actual_pos,
                    mine_type=mine_type,
                )
                laid.append(mine)
                self._mines.append(mine)

        logger.debug(
            "Layer %s laid %d %s mines at %d positions via %s",
            layer_id, len(laid), mine_type.name, len(positions), delivery_method,
        )
        return laid

    def compute_transit_risk(
        self,
        route_length_m: float,
        mine_density: float,
        ship_signature: float,
    ) -> TransitRisk:
        """Compute risk of transiting through a mined area.

        Uses a Poisson encounter model: expected encounters =
        density * sweep_width * route_length, where sweep_width
        depends on ship signature.

        Parameters
        ----------
        route_length_m:
            Length of the transit route in meters.
        mine_density:
            Mines per square meter.
        ship_signature:
            Ship signature factor 0.0–1.0 (larger/louder = higher).
        """
        # Effective sweep width: how wide the ship "triggers" mines
        # Larger signature = wider detection by mines
        sweep_width_m = 20.0 + 80.0 * ship_signature  # 20–100m effective width

        expected = mine_density * sweep_width_m * route_length_m
        # P(at least one encounter) = 1 - exp(-expected)
        p_encounter = 1.0 - math.exp(-expected)

        if p_encounter < 0.1:
            level = "low"
        elif p_encounter < 0.4:
            level = "medium"
        elif p_encounter < 0.7:
            level = "high"
        else:
            level = "extreme"

        return TransitRisk(
            encounter_probability=p_encounter,
            expected_encounters=expected,
            risk_level=level,
        )

    def resolve_mine_encounter(
        self,
        ship_id: str,
        mine: Mine,
        ship_magnetic_sig: float,
        ship_acoustic_sig: float,
        timestamp: Any = None,
        ship_signature: ShipMineSignature | None = None,
    ) -> MineResult:
        """Resolve a ship's encounter with a mine.

        Parameters
        ----------
        ship_id:
            Entity ID of the ship.
        mine:
            The mine being encountered.
        ship_magnetic_sig:
            Ship's magnetic signature 0.0–1.0 (used when *ship_signature*
            is not provided).
        ship_acoustic_sig:
            Ship's acoustic signature 0.0–1.0 (used when *ship_signature*
            is not provided).
        timestamp:
            Simulation timestamp.
        ship_signature:
            Optional structured ship signature.  When provided, its fields
            override *ship_magnetic_sig* / *ship_acoustic_sig* and supply
            pressure / displacement data for PRESSURE and COMBINATION
            mine types.
        """
        if not mine.armed or mine.detonated:
            return MineResult(mine_id=mine.mine_id, triggered=False, detonated=False)

        cfg = self._config

        # Resolve effective signature values
        if ship_signature is not None:
            eff_magnetic = ship_signature.magnetic_tesla
            eff_acoustic = ship_signature.acoustic_db
            eff_pressure = ship_signature.pressure_kpa
            # Normalize displacement: 10 000 t → 1.0
            eff_displacement = min(1.0, ship_signature.displacement_tons / 10000.0)
        else:
            eff_magnetic = ship_magnetic_sig
            eff_acoustic = ship_acoustic_sig
            eff_pressure = 0.5 * (ship_magnetic_sig + ship_acoustic_sig)
            eff_displacement = 0.5

        # Trigger probability depends on mine type and ship signature
        if mine.mine_type == MineType.CONTACT:
            trigger_prob = 0.8  # Contact mines trigger on proximity
        elif mine.mine_type == MineType.MAGNETIC:
            trigger_prob = eff_magnetic * 0.9
        elif mine.mine_type == MineType.ACOUSTIC:
            trigger_prob = eff_acoustic * 0.85
        elif mine.mine_type == MineType.PRESSURE:
            # Pressure mines respond to hull pressure wave — use pressure
            # and displacement when available
            trigger_prob = 0.5 * (eff_pressure + eff_displacement)
        elif mine.mine_type == MineType.COMBINATION:
            # Requires multiple signatures — harder to false-trigger.
            # Incorporate pressure/displacement when structured sig provided.
            combined = eff_magnetic * eff_acoustic
            if ship_signature is not None:
                combined *= 0.5 * (eff_pressure + eff_displacement)
            trigger_prob = combined * 0.95
        elif mine.mine_type == MineType.RISING:
            trigger_prob = 0.7 * max(eff_magnetic, eff_acoustic)
        elif mine.mine_type == MineType.SMART:
            # Smart mines can classify targets; selectivity determines
            # whether they engage
            trigger_prob = cfg.smart_mine_selectivity * max(
                eff_magnetic, eff_acoustic,
            )
        else:
            trigger_prob = 0.5

        triggered = self._rng.random() < trigger_prob

        if not triggered:
            if timestamp is not None:
                self._event_bus.publish(MineEvent(
                    timestamp=timestamp, source=ModuleId.COMBAT,
                    mine_id=mine.mine_id, victim_id=ship_id,
                    mine_type=mine.mine_type.name, result="miss",
                ))
            return MineResult(
                mine_id=mine.mine_id, triggered=False, detonated=False,
            )

        # Check for dud
        dud = self._rng.random() < cfg.dud_rate
        if dud:
            mine.detonated = True  # Expended but did not detonate
            if timestamp is not None:
                self._event_bus.publish(MineEvent(
                    timestamp=timestamp, source=ModuleId.COMBAT,
                    mine_id=mine.mine_id, victim_id=ship_id,
                    mine_type=mine.mine_type.name, result="miss",
                ))
            return MineResult(
                mine_id=mine.mine_id, triggered=True, detonated=False, dud=True,
            )

        # Detonation — damage depends on mine type
        mine.detonated = True
        damage = cfg.mine_damage_fraction * (0.5 + 0.5 * self._rng.random())

        # Rising mines are particularly effective
        if mine.mine_type == MineType.RISING:
            damage *= 1.5
        # Smart mines optimize detonation point
        if mine.mine_type == MineType.SMART:
            damage *= 1.3

        damage = min(1.0, damage)

        if timestamp is not None:
            self._event_bus.publish(MineEvent(
                timestamp=timestamp, source=ModuleId.COMBAT,
                mine_id=mine.mine_id, victim_id=ship_id,
                mine_type=mine.mine_type.name, result="detonated",
            ))

        return MineResult(
            mine_id=mine.mine_id,
            triggered=True,
            detonated=True,
            damage_fraction=damage,
        )

    def sweep_mines(
        self,
        sweeper_id: str,
        area_m2: float,
        mine_type: MineType,
        sweep_rate: float | None = None,
        dt: float = 60.0,
        sweep_center: Position | None = None,
        sweep_radius_m: float = 0.0,
    ) -> SweepResult:
        """Simulate mine-sweeping operations over a time step.

        Parameters
        ----------
        sweeper_id:
            Entity ID of the mine sweeper.
        area_m2:
            Area to sweep in square meters.
        mine_type:
            Type of mines being swept.
        sweep_rate:
            Sweep rate in m^2/s (uses config default if not provided).
        dt:
            Time step in seconds.
        sweep_center:
            Optional geographic center for bounding the sweep.  When
            provided together with *sweep_radius_m* > 0, only mines
            within the circle are candidates.
        sweep_radius_m:
            Radius of the geographic bounding circle in meters.
        """
        if sweep_rate is None:
            sweep_rate = self._config.base_sweep_rate_m2_per_s

        # Type-specific sweep difficulty
        difficulty = {
            MineType.CONTACT: 1.0,
            MineType.MAGNETIC: 0.8,
            MineType.ACOUSTIC: 0.7,
            MineType.PRESSURE: 0.5,
            MineType.COMBINATION: 0.4,
            MineType.RISING: 0.6,
            MineType.SMART: 0.3,
        }
        type_factor = difficulty.get(mine_type, 0.5)

        effective_rate = sweep_rate * type_factor
        area_cleared = min(area_m2, effective_rate * dt)

        # Count mines in the swept area
        swept = 0
        neutralized = 0
        for mine in self._mines:
            if mine.mine_type == mine_type and mine.armed and not mine.detonated:
                # Geographic bounding — skip mines outside the sweep circle
                if sweep_center is not None and sweep_radius_m > 0.0:
                    dx = mine.position.easting - sweep_center.easting
                    dy = mine.position.northing - sweep_center.northing
                    if math.hypot(dx, dy) > sweep_radius_m:
                        continue
                # Stochastic: each mine has a chance of being found
                if self._rng.random() < type_factor:
                    swept += 1
                    # Neutralization success
                    if self._rng.random() < 0.9:
                        mine.armed = False
                        neutralized += 1

        logger.debug(
            "Sweeper %s: cleared %.0f m^2, found %d mines, neutralized %d",
            sweeper_id, area_cleared, swept, neutralized,
        )

        return SweepResult(
            mines_swept=swept,
            mines_neutralized=neutralized,
            area_cleared_m2=area_cleared,
            sweep_time_s=dt,
        )

    def update_mine_persistence(self, dt_hours: float) -> None:
        """Age all armed mines — batteries decay exponentially.

        Mines lose their armed status stochastically based on an
        exponential decay model with rate 0.001 per hour.

        Parameters
        ----------
        dt_hours:
            Elapsed time in hours.
        """
        decay_rate = 0.001  # per hour
        p_disarm = 1.0 - math.exp(-decay_rate * dt_hours)
        for mine in self._mines:
            if mine.armed and not mine.detonated:
                if self._rng.random() < p_disarm:
                    mine.armed = False

    def compute_minefield_density(
        self,
        area_center: Position,
        area_radius_m: float,
    ) -> float:
        """Count armed mines in a circular area and return density.

        Parameters
        ----------
        area_center:
            Center of the query area (ENU position).
        area_radius_m:
            Radius of the query area in meters.

        Returns
        -------
        float
            Armed mines per square meter within the circle.
        """
        if area_radius_m <= 0.0:
            return 0.0

        count = 0
        for mine in self._mines:
            if mine.armed and not mine.detonated:
                dx = mine.position.easting - area_center.easting
                dy = mine.position.northing - area_center.northing
                if math.hypot(dx, dy) <= area_radius_m:
                    count += 1

        area_m2 = math.pi * area_radius_m ** 2
        return count / area_m2

    def get_state(self) -> dict[str, Any]:
        return {
            "rng_state": self._rng.bit_generator.state,
            "mine_counter": self._mine_counter,
            "mines": [m.get_state() for m in self._mines],
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]
        self._mine_counter = state["mine_counter"]
        self._mines = []
        for ms in state["mines"]:
            m = Mine(
                mine_id="", position=Position(0, 0, 0),
                mine_type=MineType.CONTACT,
            )
            m.set_state(ms)
            self._mines.append(m)
