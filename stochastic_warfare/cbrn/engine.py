"""CBRN engine — top-level orchestrator.

Wraps all CBRN sub-engines (dispersal, contamination, protection, casualties,
decontamination, nuclear) into a single update loop.  Follows the
:class:`SpaceEngine` pattern from Phase 17.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.cbrn.agents import AgentRegistry
from stochastic_warfare.cbrn.casualties import CBRNCasualtyEngine
from stochastic_warfare.cbrn.contamination import ContaminationManager
from stochastic_warfare.cbrn.decontamination import DecontaminationEngine
from stochastic_warfare.cbrn.dispersal import DispersalEngine
from stochastic_warfare.cbrn.events import CBRNReleaseEvent, MOPPLevelChangedEvent
from stochastic_warfare.cbrn.nuclear import NuclearEffectsEngine
from stochastic_warfare.cbrn.protection import MOPPLevel, ProtectionEngine
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class CBRNConfig(BaseModel):
    """Top-level CBRN configuration."""

    enable_cbrn: bool = False
    update_interval_s: float = 10.0
    auto_mopp_response: bool = True
    fallback_wind_speed_mps: float = 2.0
    fallback_wind_direction_rad: float = 0.0
    fallback_cloud_cover: float = 0.5


# ---------------------------------------------------------------------------
# CBRN Engine
# ---------------------------------------------------------------------------


class CBRNEngine:
    """Top-level orchestrator wrapping all CBRN sub-engines."""

    def __init__(
        self,
        config: CBRNConfig,
        event_bus: EventBus,
        rng: np.random.Generator,
        agent_registry: AgentRegistry,
        dispersal_engine: DispersalEngine,
        contamination_manager: ContaminationManager,
        protection_engine: ProtectionEngine,
        casualty_engine: CBRNCasualtyEngine,
        decon_engine: DecontaminationEngine,
        nuclear_engine: NuclearEffectsEngine | None = None,
    ) -> None:
        self._config = config
        self._event_bus = event_bus
        self._rng = rng
        self._agent_registry = agent_registry
        self._dispersal = dispersal_engine
        self._contamination = contamination_manager
        self._protection = protection_engine
        self._casualty = casualty_engine
        self._decon = decon_engine
        self._nuclear = nuclear_engine

        # Per-unit MOPP levels
        self._mopp_levels: dict[str, int] = {}

    # ── Agent release ─────────────────────────────────────────────────

    def release_agent(
        self,
        agent_id: str,
        position: Position,
        quantity_kg: float,
        delivery_method: str,
        timestamp: Any = None,
    ) -> str:
        """Release a CBRN agent at a position.  Returns the puff ID."""
        agent_defn = self._agent_registry.get(agent_id)
        category = int(getattr(agent_defn, "category", 0)) if agent_defn else 0

        puff = self._dispersal.create_puff(
            agent_id, position.easting, position.northing, quantity_kg, 0.0,
        )

        if timestamp is not None:
            self._event_bus.publish(CBRNReleaseEvent(
                timestamp=timestamp,
                source=ModuleId.CBRN,
                release_id=puff.puff_id,
                agent_id=agent_id,
                agent_category=category,
                position_easting=position.easting,
                position_northing=position.northing,
                quantity_kg=quantity_kg,
                delivery_method=delivery_method,
            ))

        logger.info("CBRN release: %s %.1f kg at (%.0f, %.0f) via %s",
                     agent_id, quantity_kg, position.easting, position.northing,
                     delivery_method)
        return puff.puff_id

    # ── Nuclear detonation ────────────────────────────────────────────

    def detonate_nuclear(
        self,
        weapon_id: str,
        position: Position,
        yield_kt: float,
        airburst: bool,
        units_by_side: dict[str, list[Any]],
        weather_conditions: Any,
        heightmap: Any,
        classification: Any,
        timestamp: Any,
    ) -> dict[str, Any]:
        """Detonate a nuclear weapon.  Delegates to NuclearEffectsEngine."""
        if self._nuclear is None:
            return {}
        return self._nuclear.detonate(
            weapon_id, position, yield_kt, airburst,
            units_by_side, weather_conditions,
            self._contamination, self._agent_registry,
            heightmap, classification, timestamp,
        )

    # ── Tick update ───────────────────────────────────────────────────

    def update(
        self,
        dt_s: float,
        sim_time_s: float,
        units_by_side: dict[str, list[Any]],
        weather_conditions: Any = None,
        classification: Any = None,
        heightmap: Any = None,
        time_of_day: Any = None,
        timestamp: Any = None,
    ) -> None:
        """Full CBRN update cycle for one tick.

        1. Dispersal: advect puffs, compute ground deposition
        2. Contamination: decay, evaporation, washout
        3. For each unit: check position, accumulate dosage, assess casualties
        4. Decon: update active operations
        5. Auto-MOPP if configured
        """
        if not self._config.enable_cbrn:
            return

        wind_speed = self._config.fallback_wind_speed_mps
        wind_direction = self._config.fallback_wind_direction_rad
        if weather_conditions is not None:
            wind_speed = getattr(weather_conditions, "wind_speed_m_s", self._config.fallback_wind_speed_mps)
            wind_direction = getattr(weather_conditions, "wind_direction_rad", self._config.fallback_wind_direction_rad)

        cloud_cover = self._config.fallback_cloud_cover
        if weather_conditions is not None:
            cloud_cover = getattr(weather_conditions, "cloud_cover", self._config.fallback_cloud_cover)

        stability = self._dispersal.classify_stability(
            wind_speed,
            cloud_cover,
            getattr(time_of_day, "is_daytime", True) if time_of_day else True,
        )

        # 1. Advect puffs and deposit to contamination grid
        for puff in self._dispersal.puffs:
            self._dispersal.advect_puff(puff, dt_s, wind_speed, wind_direction)

            # Deposit concentration to contamination grid cells
            if self._contamination is not None:
                # Sample concentration at puff center → add to grid
                conc = self._dispersal.compute_concentration(
                    puff, puff.center_e, puff.center_n,
                    wind_speed, wind_direction, stability,
                )
                if conc > 0:
                    row, col = self._contamination.enu_to_grid(
                        Position(puff.center_e, puff.center_n, 0.0)
                    )
                    self._contamination.add_contamination(puff.agent_id, row, col, conc * dt_s / 60.0)

        # 2. Contamination decay
        if self._contamination is not None:
            self._contamination.update(
                dt_s, self._dispersal, weather_conditions, classification,
                heightmap, time_of_day, self._agent_registry, timestamp,
            )

        # 3. Unit exposure
        for side_units in units_by_side.values():
            for unit in side_units:
                uid = unit.entity_id
                pos = unit.position

                if self._contamination is None:
                    continue

                concentrations = self._contamination.total_concentration_at_pos(pos)
                if not concentrations:
                    continue

                mopp = self._mopp_levels.get(uid, 0)

                # Auto-MOPP: raise to MOPP_4 on detection
                if self._config.auto_mopp_response and mopp < 4 and concentrations:
                    old_mopp = mopp
                    mopp = 4
                    self._mopp_levels[uid] = mopp
                    if timestamp is not None:
                        self._event_bus.publish(MOPPLevelChangedEvent(
                            timestamp=timestamp,
                            source=ModuleId.CBRN,
                            unit_id=uid,
                            previous_level=old_mopp,
                            new_level=mopp,
                        ))

                for agent_id, conc in concentrations.items():
                    agent_defn = self._agent_registry.get(agent_id)
                    if agent_defn is None:
                        continue
                    prot_factor = self._protection.compute_protection_factor(
                        mopp, agent_defn.category,
                    )
                    self._casualty.accumulate_dosage(
                        uid, agent_id, conc, dt_s, prot_factor,
                    )
                    personnel = getattr(unit, "personnel_count", 10)
                    self._casualty.assess_casualties(
                        uid, agent_defn, personnel, timestamp,
                    )

        # 4. Decon operations
        self._decon.update(sim_time_s, timestamp)

        # 5. Puff cleanup — remove aged puffs
        self._dispersal.cleanup_aged_puffs()

    # ── MOPP effects query ────────────────────────────────────────────

    def get_mopp_level(self, unit_id: str) -> int:
        """Get current MOPP level for a unit."""
        return self._mopp_levels.get(unit_id, 0)

    def set_mopp_level(self, unit_id: str, level: int, timestamp: Any = None) -> None:
        """Set MOPP level for a unit."""
        old = self._mopp_levels.get(unit_id, 0)
        self._mopp_levels[unit_id] = level
        if old != level and timestamp is not None:
            self._event_bus.publish(MOPPLevelChangedEvent(
                timestamp=timestamp,
                source=ModuleId.CBRN,
                unit_id=unit_id,
                previous_level=old,
                new_level=level,
            ))

    def get_mopp_effects(self, unit_id: str) -> tuple[float, float, float]:
        """Return (speed_factor, detection_factor, fatigue_mult) for a unit."""
        mopp = self._mopp_levels.get(unit_id, 0)
        speed = self._protection.get_mopp_speed_factor(mopp)
        detection = self._protection.get_mopp_detection_factor(mopp)
        fatigue = self._protection.get_mopp_fatigue_multiplier(mopp)
        return speed, detection, fatigue

    # ── State persistence ────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        state: dict[str, Any] = {
            "mopp_levels": dict(self._mopp_levels),
        }
        for name, eng in [
            ("dispersal", self._dispersal),
            ("contamination", self._contamination),
            ("protection", self._protection),
            ("casualty", self._casualty),
            ("decon", self._decon),
            ("nuclear", self._nuclear),
        ]:
            if eng is not None and hasattr(eng, "get_state"):
                state[name] = eng.get_state()
        return state

    def set_state(self, state: dict[str, Any]) -> None:
        self._mopp_levels = state.get("mopp_levels", {})
        for name, eng in [
            ("dispersal", self._dispersal),
            ("contamination", self._contamination),
            ("protection", self._protection),
            ("casualty", self._casualty),
            ("decon", self._decon),
            ("nuclear", self._nuclear),
        ]:
            if eng is not None and name in state and hasattr(eng, "set_state"):
                eng.set_state(state[name])
