"""Unconventional warfare mechanics -- IEDs, guerrilla, human shields.

Provides models for improvised explosive devices (emplacement, detection,
detonation, EW jamming), guerrilla attack/disengage decision logic, and
human-shield / civilian-proximity constraints for ROE evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IEDDetonationEvent(Event):
    """Published when an IED detonates."""

    obstacle_id: str
    target_unit_id: str
    blast_radius_m: float
    position: Position


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class IEDConfig(BaseModel):
    """Tuning parameters for IED mechanics."""

    base_detect_probability: float = 0.15
    engineering_bonus: float = 0.50
    max_safe_speed_mps: float = 5.0
    stress_spike: float = 0.3
    route_denial_radius_m: float = 100.0


class GuerrillaConfig(BaseModel):
    """Tuning parameters for guerrilla warfare mechanics."""

    disengage_threshold: float = 0.3
    blend_probability: float = 0.7
    ambush_terrain_bonus: float = 0.5
    local_superiority_threshold: float = 1.5


# ---------------------------------------------------------------------------
# Result data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IEDDetonationResult:
    """Result of an IED detonation."""

    blast_radius_m: float
    position: Position
    stress_spike: float
    route_denial: float


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class UnconventionalWarfareEngine:
    """IED emplacement/detection/detonation, guerrilla tactics, human shields.

    Parameters
    ----------
    event_bus : EventBus
        For publishing detonation events.
    rng : numpy.random.Generator
        Deterministic PRNG stream.
    config_ied : IEDConfig | None
        IED tuning parameters.
    config_guerrilla : GuerrillaConfig | None
        Guerrilla tuning parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config_ied: IEDConfig | None = None,
        config_guerrilla: GuerrillaConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._cfg_ied = config_ied or IEDConfig()
        self._cfg_guer = config_guerrilla or GuerrillaConfig()
        self._ieds: dict[str, dict] = {}
        self._next_id: int = 0

    # ------------------------------------------------------------------
    # IED methods
    # ------------------------------------------------------------------

    def emplace_ied(
        self,
        position: Position,
        subtype: str,
        blast_radius_m: float,
        concealment: float,
        emplaced_by: str,
        timestamp: datetime | None = None,
    ) -> str:
        """Emplace an IED at *position*.

        Parameters
        ----------
        position : Position
            Location in ENU metres.
        subtype : str
            One of ``command_wire``, ``pressure_plate``, ``remote``, ``vbied``.
        blast_radius_m : float
            Effective blast radius.
        concealment : float
            Concealment factor 0--1 (higher = harder to detect).
        emplaced_by : str
            Unit ID of the emplacing unit.
        timestamp : datetime | None
            Optional event timestamp.

        Returns
        -------
        str
            Unique obstacle ID.
        """
        self._next_id += 1
        obstacle_id = f"ied_{self._next_id}"
        self._ieds[obstacle_id] = {
            "position": position,
            "subtype": subtype,
            "blast_radius_m": blast_radius_m,
            "concealment": concealment,
            "emplaced_by": emplaced_by,
            "active": True,
        }
        logger.info(
            "IED emplaced: %s (%s) at (%0.1f, %0.1f) by %s",
            obstacle_id,
            subtype,
            position.easting,
            position.northing,
            emplaced_by,
        )
        return obstacle_id

    def check_ied_detection(
        self,
        unit_speed_mps: float,
        has_engineering: bool,
        unit_id: str,
    ) -> bool:
        """Roll for IED detection.

        Detection probability::

            P(detect) = base * (1 + eng_bonus if has_eng else 1)
                        * (1 - min(1, speed / max_safe_speed))

        Returns ``True`` if detected (the IED is spotted and avoided).
        """
        cfg = self._cfg_ied
        eng_mult = (1.0 + cfg.engineering_bonus) if has_engineering else 1.0
        speed_factor = 1.0 - min(1.0, unit_speed_mps / cfg.max_safe_speed_mps)
        prob = cfg.base_detect_probability * eng_mult * speed_factor
        detected = self._rng.random() < prob
        if detected:
            logger.debug("Unit %s detected IED (P=%.3f)", unit_id, prob)
        return detected

    def detonate_ied(
        self,
        obstacle_id: str,
        target_unit_id: str,
        timestamp: datetime | None = None,
    ) -> IEDDetonationResult:
        """Detonate an emplaced IED.

        Returns
        -------
        IEDDetonationResult
            Contains blast radius, position, stress spike, and route denial.

        Raises
        ------
        KeyError
            If *obstacle_id* is not known.
        """
        ied = self._ieds[obstacle_id]
        ied["active"] = False
        pos = ied["position"]
        result = IEDDetonationResult(
            blast_radius_m=ied["blast_radius_m"],
            position=pos,
            stress_spike=self._cfg_ied.stress_spike,
            route_denial=self._cfg_ied.route_denial_radius_m,
        )
        if timestamp is not None:
            self._event_bus.publish(
                IEDDetonationEvent(
                    timestamp=timestamp,
                    source=ModuleId.COMBAT,
                    obstacle_id=obstacle_id,
                    target_unit_id=target_unit_id,
                    blast_radius_m=ied["blast_radius_m"],
                    position=pos,
                )
            )
        logger.info(
            "IED %s detonated on %s (radius=%.1fm)",
            obstacle_id,
            target_unit_id,
            ied["blast_radius_m"],
        )
        return result

    def check_ew_jamming(
        self,
        obstacle_id: str,
        jammer_active: bool,
        jammer_effectiveness: float,
    ) -> bool:
        """Check if EW jamming blocks a remote-detonated IED.

        Command-wire and pressure-plate subtypes cannot be jammed.
        Returns ``True`` if the IED is jammed (detonation blocked).
        """
        ied = self._ieds[obstacle_id]
        subtype = ied["subtype"]
        if subtype in ("command_wire", "pressure_plate"):
            return False
        if not jammer_active:
            return False
        jammed = self._rng.random() < jammer_effectiveness
        if jammed:
            logger.debug("IED %s jammed by EW (eff=%.2f)", obstacle_id, jammer_effectiveness)
        return jammed

    # ------------------------------------------------------------------
    # Guerrilla methods
    # ------------------------------------------------------------------

    def evaluate_guerrilla_attack(
        self,
        guerrilla_unit_id: str,
        local_force_ratio: float,
        terrain_advantage: float,
    ) -> bool:
        """Decide whether a guerrilla unit should initiate an attack.

        Attack if::

            local_force_ratio >= threshold * (1.0 - terrain_advantage * bonus)

        Parameters
        ----------
        guerrilla_unit_id : str
            ID of the guerrilla unit.
        local_force_ratio : float
            Guerrilla-to-enemy force ratio in the local area.
        terrain_advantage : float
            Terrain advantage factor 0--1 (urban, jungle, mountain, etc.).

        Returns
        -------
        bool
            ``True`` if the attack should proceed.
        """
        cfg = self._cfg_guer
        required = cfg.local_superiority_threshold * (
            1.0 - terrain_advantage * cfg.ambush_terrain_bonus
        )
        should_attack = local_force_ratio >= required
        logger.debug(
            "Guerrilla %s attack eval: ratio=%.2f required=%.2f -> %s",
            guerrilla_unit_id,
            local_force_ratio,
            required,
            should_attack,
        )
        return should_attack

    def evaluate_guerrilla_disengage(
        self,
        guerrilla_unit_id: str,
        casualties_fraction: float,
        in_populated_area: bool,
    ) -> tuple[bool, float]:
        """Decide whether a guerrilla unit should disengage.

        Parameters
        ----------
        guerrilla_unit_id : str
            ID of the guerrilla unit.
        casualties_fraction : float
            Fraction of unit lost 0--1.
        in_populated_area : bool
            Whether the unit is in a populated area (can blend in).

        Returns
        -------
        tuple[bool, float]
            ``(should_disengage, blend_probability)``
        """
        cfg = self._cfg_guer
        should_disengage = casualties_fraction > cfg.disengage_threshold
        blend_prob = cfg.blend_probability if in_populated_area else 0.0
        logger.debug(
            "Guerrilla %s disengage eval: cas=%.2f thr=%.2f -> disengage=%s blend=%.2f",
            guerrilla_unit_id,
            casualties_fraction,
            cfg.disengage_threshold,
            should_disengage,
            blend_prob,
        )
        return should_disengage, blend_prob

    # ------------------------------------------------------------------
    # Human shields
    # ------------------------------------------------------------------

    def evaluate_human_shield(
        self,
        target_position: Position,
        civilian_density: float,
    ) -> float:
        """Evaluate civilian proximity value for ROE constraint.

        Parameters
        ----------
        target_position : Position
            Target location (unused in base model, included for future
            spatial lookup).
        civilian_density : float
            Civilian density 0--1 normalised.

        Returns
        -------
        float
            Civilian proximity value [0, 1].  Higher density produces a
            higher value which should cause ROE to restrict fire.
        """
        return min(1.0, max(0.0, civilian_density))

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        """Serialize for checkpoint."""
        return {
            "next_id": self._next_id,
            "ieds": {
                oid: {
                    "position": list(rec["position"]),
                    "subtype": rec["subtype"],
                    "blast_radius_m": rec["blast_radius_m"],
                    "concealment": rec["concealment"],
                    "emplaced_by": rec["emplaced_by"],
                    "active": rec["active"],
                }
                for oid, rec in self._ieds.items()
            },
        }

    def set_state(self, state: dict) -> None:
        """Restore from checkpoint."""
        self._next_id = state.get("next_id", 0)
        self._ieds.clear()
        for oid, rd in state["ieds"].items():
            self._ieds[oid] = {
                "position": Position(*rd["position"]),
                "subtype": rd["subtype"],
                "blast_radius_m": rd["blast_radius_m"],
                "concealment": rd["concealment"],
                "emplaced_by": rd["emplaced_by"],
                "active": rd["active"],
            }
