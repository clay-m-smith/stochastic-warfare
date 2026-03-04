"""Nuclear weapon effects engine.

Models nuclear detonation effects: blast overpressure (Hopkinson-Cranz scaling),
thermal radiation (inverse-square fluence), initial radiation (prompt gamma/neutron),
electromagnetic pulse (EMP), radioactive fallout (wind-driven plume via dispersal
engine), and crater formation.

Key physics:
- Blast: Hopkinson-Cranz scaled overpressure DP = K * (R / W^(1/3))^(-a)
- Thermal: Q = eta * W / (4 * pi * R^2), eta ~ 0.35 thermal partition
- Radiation: D = D0 * (W / W0) * exp(-R / lambda) / R^2
- EMP: Radius scales with yield^(1/3)
- Fallout: Wind-driven radiological plume via dispersal engine
- Crater: Radius ~ 12 * W^(1/3) meters for ground burst
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.cbrn.events import (
    EMPEvent,
    FalloutPlumeEvent,
    NuclearDetonationEvent,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Physical constants for nuclear effects
# ---------------------------------------------------------------------------

# Hopkinson-Cranz blast constants (calibrated to Glasstone & Dolan reference)
# K chosen so that a 20 kt weapon produces ~12 psi at ~2.6 km
_BLAST_K = 1.0e7  # Scaling constant (psi * m^2 / kt^(2/3))
_BLAST_EXPONENT = 2.0  # Decay exponent (inverse-square regime for blast wave)

# Thermal partition fraction (fraction of yield as thermal radiation)
_THERMAL_ETA = 0.35

# Thermal unit conversion: 1 kt = 4.184e12 joules
_KT_TO_JOULES = 4.184e12

# 1 cal/cm^2 = 41868 J/m^2
_CAL_CM2_TO_J_M2 = 41868.0

# Radiation constants
_RAD_D0 = 1.0e5  # Reference dose (rem) at 1m for 1 kt (calibrated)
_RAD_W0 = 1.0  # Reference yield (kt)
_RAD_LAMBDA = 200.0  # Attenuation length (meters) for prompt radiation

# EMP radius scaling factor (meters per kt^(1/3))
_EMP_RADIUS_FACTOR = 5000.0

# Crater radius scaling factor (meters per kt^(1/3))
_CRATER_RADIUS_FACTOR = 12.0

# Blast thresholds (psi)
_BLAST_LETHAL_PSI = 12.0
_BLAST_INJURY_PSI = 5.0
_BLAST_LIGHT_DAMAGE_PSI = 2.0

# Thermal thresholds (cal/cm^2)
_THERMAL_LETHAL_CAL = 12.0
_THERMAL_SEVERE_BURN_CAL = 6.0
_THERMAL_SECOND_DEGREE_CAL = 3.0

# Radiation thresholds (rem)
_RAD_LETHAL_REM = 600.0
_RAD_INJURY_REM = 200.0

# Fallout mass scaling (kg of radioactive debris per kt for ground burst)
_FALLOUT_MASS_PER_KT = 50.0


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class NuclearConfig(BaseModel):
    """Configuration for the nuclear effects engine."""

    emp_electronics_disable_prob: float = 0.95
    hardened_electronics_survive_prob: float = 0.8
    terrain_modification_enabled: bool = True


# ---------------------------------------------------------------------------
# Nuclear effects engine
# ---------------------------------------------------------------------------


class NuclearEffectsEngine:
    """Computes and applies nuclear weapon detonation effects.

    Orchestrates blast, thermal, radiation, EMP, fallout, and terrain
    modification for a nuclear detonation. All stochastic decisions
    (EMP electronics disable) use the injected RNG for deterministic replay.

    Parameters
    ----------
    event_bus:
        EventBus for publishing detonation/EMP/fallout events.
    rng:
        numpy Generator for stochastic effects (EMP survival rolls).
    dispersal_engine:
        Gaussian puff dispersal engine for fallout plume creation.
    config:
        Tunable parameters for the nuclear effects model.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        dispersal_engine: Any,
        config: NuclearConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._dispersal_engine = dispersal_engine
        self._config = config or NuclearConfig()
        self._detonation_count: int = 0

    # ------------------------------------------------------------------
    # Static physics calculations
    # ------------------------------------------------------------------

    @staticmethod
    def blast_overpressure_psi(range_m: float, yield_kt: float) -> float:
        """Compute peak overpressure at *range_m* from a *yield_kt* detonation.

        Uses Hopkinson-Cranz cube-root scaling::

            DP = K * (R / W^(1/3))^(-a)

        Parameters
        ----------
        range_m:
            Distance from ground zero in meters.  Clamped to >= 1.0.
        yield_kt:
            Weapon yield in kilotons TNT equivalent.

        Returns
        -------
        Peak overpressure in psi.
        """
        if yield_kt <= 0.0:
            return 0.0
        r = max(range_m, 1.0)
        scaled_range = r / (yield_kt ** (1.0 / 3.0))
        return _BLAST_K * scaled_range ** (-_BLAST_EXPONENT)

    @staticmethod
    def thermal_fluence_cal_cm2(range_m: float, yield_kt: float) -> float:
        """Compute thermal fluence at *range_m* from a *yield_kt* detonation.

        Uses inverse-square law with thermal partition fraction::

            Q = eta * W_joules / (4 * pi * R^2)  -> convert to cal/cm^2

        Parameters
        ----------
        range_m:
            Distance from ground zero in meters.  Clamped to >= 1.0.
        yield_kt:
            Weapon yield in kilotons TNT equivalent.

        Returns
        -------
        Thermal fluence in cal/cm^2.
        """
        if yield_kt <= 0.0:
            return 0.0
        r = max(range_m, 1.0)
        energy_j = _THERMAL_ETA * yield_kt * _KT_TO_JOULES
        fluence_j_m2 = energy_j / (4.0 * math.pi * r * r)
        return fluence_j_m2 / _CAL_CM2_TO_J_M2

    @staticmethod
    def initial_radiation_rem(range_m: float, yield_kt: float) -> float:
        """Compute initial (prompt) radiation dose at *range_m*.

        Combines inverse-square geometric spreading with exponential
        atmospheric attenuation::

            D = D0 * (W / W0) * exp(-R / lambda) / R^2

        Parameters
        ----------
        range_m:
            Distance from ground zero in meters.  Clamped to >= 1.0.
        yield_kt:
            Weapon yield in kilotons TNT equivalent.

        Returns
        -------
        Prompt radiation dose in rem.
        """
        if yield_kt <= 0.0:
            return 0.0
        r = max(range_m, 1.0)
        dose = _RAD_D0 * (yield_kt / _RAD_W0) * math.exp(-r / _RAD_LAMBDA) / (r * r)
        return dose

    @staticmethod
    def emp_radius_m(yield_kt: float) -> float:
        """Compute EMP effect radius in meters.

        Scales with the cube root of yield::

            R_emp = factor * W^(1/3)

        Parameters
        ----------
        yield_kt:
            Weapon yield in kilotons TNT equivalent.

        Returns
        -------
        EMP effect radius in meters.
        """
        if yield_kt <= 0.0:
            return 0.0
        return _EMP_RADIUS_FACTOR * (yield_kt ** (1.0 / 3.0))

    # ------------------------------------------------------------------
    # Casualty computation
    # ------------------------------------------------------------------

    def compute_blast_casualties(
        self,
        units: list[Any],
        detonation_pos: Position,
        yield_kt: float,
    ) -> dict[str, tuple[int, int, int]]:
        """Compute blast casualties for each unit based on overpressure zones.

        Overpressure thresholds:
        - >12 psi: lethal
        - >5 psi: injury
        - >2 psi: light damage

        Personnel are allocated to the highest applicable zone.

        Parameters
        ----------
        units:
            List of unit objects with entity_id, position, personnel_count.
        detonation_pos:
            Ground zero position.
        yield_kt:
            Weapon yield in kilotons.

        Returns
        -------
        Dict mapping entity_id to (killed, injured, light_damage_count).
        """
        results: dict[str, tuple[int, int, int]] = {}

        for unit in units:
            uid = unit.entity_id
            pos = unit.position
            dist = math.sqrt(
                (pos.easting - detonation_pos.easting) ** 2
                + (pos.northing - detonation_pos.northing) ** 2
            )
            overpressure = self.blast_overpressure_psi(dist, yield_kt)
            personnel = getattr(unit, "personnel_count", 10)

            if overpressure >= _BLAST_LETHAL_PSI:
                # All personnel killed
                killed = personnel
                injured = 0
                light = 0
            elif overpressure >= _BLAST_INJURY_PSI:
                # Fraction killed, rest injured
                kill_frac = (overpressure - _BLAST_INJURY_PSI) / (
                    _BLAST_LETHAL_PSI - _BLAST_INJURY_PSI
                )
                killed = int(personnel * kill_frac)
                injured = personnel - killed
                light = 0
            elif overpressure >= _BLAST_LIGHT_DAMAGE_PSI:
                # No killed, fraction injured, rest light damage
                killed = 0
                inj_frac = (overpressure - _BLAST_LIGHT_DAMAGE_PSI) / (
                    _BLAST_INJURY_PSI - _BLAST_LIGHT_DAMAGE_PSI
                )
                injured = int(personnel * inj_frac)
                light = personnel - injured
            else:
                killed = 0
                injured = 0
                light = 0

            results[uid] = (killed, injured, light)

        return results

    def compute_thermal_casualties(
        self,
        units: list[Any],
        detonation_pos: Position,
        yield_kt: float,
    ) -> dict[str, tuple[int, int]]:
        """Compute thermal burn casualties for each unit.

        Fluence thresholds:
        - >12 cal/cm^2: lethal burns
        - >6 cal/cm^2: severe (3rd degree) burns

        Parameters
        ----------
        units:
            List of unit objects with entity_id, position, personnel_count.
        detonation_pos:
            Ground zero position.
        yield_kt:
            Weapon yield in kilotons.

        Returns
        -------
        Dict mapping entity_id to (lethal_burns, severe_burns).
        """
        results: dict[str, tuple[int, int]] = {}

        for unit in units:
            uid = unit.entity_id
            pos = unit.position
            dist = math.sqrt(
                (pos.easting - detonation_pos.easting) ** 2
                + (pos.northing - detonation_pos.northing) ** 2
            )
            fluence = self.thermal_fluence_cal_cm2(dist, yield_kt)
            personnel = getattr(unit, "personnel_count", 10)

            if fluence >= _THERMAL_LETHAL_CAL:
                lethal = personnel
                severe = 0
            elif fluence >= _THERMAL_SEVERE_BURN_CAL:
                lethal_frac = (fluence - _THERMAL_SEVERE_BURN_CAL) / (
                    _THERMAL_LETHAL_CAL - _THERMAL_SEVERE_BURN_CAL
                )
                lethal = int(personnel * lethal_frac)
                severe = personnel - lethal
            elif fluence >= _THERMAL_SECOND_DEGREE_CAL:
                lethal = 0
                severe_frac = (fluence - _THERMAL_SECOND_DEGREE_CAL) / (
                    _THERMAL_SEVERE_BURN_CAL - _THERMAL_SECOND_DEGREE_CAL
                )
                severe = int(personnel * severe_frac)
            else:
                lethal = 0
                severe = 0

            results[uid] = (lethal, severe)

        return results

    # ------------------------------------------------------------------
    # EMP effects
    # ------------------------------------------------------------------

    def apply_emp(
        self,
        units: list[Any],
        detonation_pos: Position,
        yield_kt: float,
        timestamp: Any,
    ) -> list[str]:
        """Apply EMP effects to units within the EMP radius.

        Unshielded electronics are disabled with probability
        ``emp_electronics_disable_prob``.  Hardened electronics survive
        with probability ``hardened_electronics_survive_prob``.

        Parameters
        ----------
        units:
            List of unit objects.
        detonation_pos:
            Ground zero position.
        yield_kt:
            Weapon yield in kilotons.
        timestamp:
            Simulation timestamp for event publishing.

        Returns
        -------
        List of entity_ids of units whose electronics were affected.
        """
        emp_r = self.emp_radius_m(yield_kt)
        affected: list[str] = []

        for unit in units:
            pos = unit.position
            dist = math.sqrt(
                (pos.easting - detonation_pos.easting) ** 2
                + (pos.northing - detonation_pos.northing) ** 2
            )
            if dist > emp_r:
                continue

            is_hardened = getattr(unit, "hardened_electronics", False)

            if is_hardened:
                # Hardened electronics survive with configured probability
                roll = float(self._rng.random())
                if roll < self._config.hardened_electronics_survive_prob:
                    # Survived — not affected
                    continue
            else:
                # Unshielded electronics disabled with high probability
                roll = float(self._rng.random())
                if roll >= self._config.emp_electronics_disable_prob:
                    # Lucky — not affected
                    continue

            affected.append(unit.entity_id)

        return affected

    # ------------------------------------------------------------------
    # Fallout
    # ------------------------------------------------------------------

    def generate_fallout_plume(
        self,
        detonation_pos: Position,
        yield_kt: float,
        wind_speed: float,
        wind_direction: float,
        contamination_manager: Any,
        agent_registry: Any,
        timestamp: Any,
    ) -> str:
        """Generate a radioactive fallout plume for a ground burst.

        Creates a dispersal puff of nuclear_fallout agent via the dispersal
        engine.  The puff mass scales linearly with yield.

        Parameters
        ----------
        detonation_pos:
            Ground zero position.
        yield_kt:
            Weapon yield in kilotons.
        wind_speed:
            Wind speed in m/s.
        wind_direction:
            Wind direction in radians (direction wind blows TO).
        contamination_manager:
            Contamination grid manager (may be None).
        agent_registry:
            CBRN agent registry (may be None).
        timestamp:
            Simulation timestamp.

        Returns
        -------
        Puff ID of the created fallout plume.
        """
        fallout_mass_kg = _FALLOUT_MASS_PER_KT * yield_kt

        puff = self._dispersal_engine.create_puff(
            "nuclear_fallout",
            detonation_pos.easting,
            detonation_pos.northing,
            fallout_mass_kg,
            0.0,
        )

        puff_id = getattr(puff, "puff_id", str(puff))

        logger.info(
            "Generated fallout plume %s: yield=%.1f kt, mass=%.1f kg, "
            "wind=%.1f m/s @ %.2f rad",
            puff_id,
            yield_kt,
            fallout_mass_kg,
            wind_speed,
            wind_direction,
        )

        return puff_id

    # ------------------------------------------------------------------
    # Terrain modification
    # ------------------------------------------------------------------

    def modify_terrain(
        self,
        detonation_pos: Position,
        yield_kt: float,
        heightmap: Any,
        classification: Any,
    ) -> None:
        """Create a crater at ground zero for ground burst detonations.

        Crater radius scales as ``12 * W^(1/3)`` meters.  Elevation within
        the crater is depressed; land-cover is set to OPEN if the
        classification grid supports ``set_classification``.

        Parameters
        ----------
        detonation_pos:
            Ground zero position.
        yield_kt:
            Weapon yield in kilotons.
        heightmap:
            Heightmap grid object (may be None).
        classification:
            Terrain classification grid (may be None).
        """
        if not self._config.terrain_modification_enabled:
            return

        crater_radius = _CRATER_RADIUS_FACTOR * (yield_kt ** (1.0 / 3.0))
        crater_depth = crater_radius * 0.3  # Depth ~ 30% of radius

        # Modify heightmap if available
        if heightmap is not None:
            cell_size = getattr(heightmap, "cell_size", None)
            rows = getattr(heightmap, "rows", None)
            cols = getattr(heightmap, "cols", None)
            data = getattr(heightmap, "_data", None)
            origin_e = getattr(heightmap, "_config", None)

            if cell_size is not None and data is not None and origin_e is not None:
                config = origin_e
                origin_easting = getattr(config, "origin_easting", 0.0)
                origin_northing = getattr(config, "origin_northing", 0.0)

                # Determine affected grid cells
                cells_radius = int(math.ceil(crater_radius / cell_size))
                center_col = int(
                    (detonation_pos.easting - origin_easting) / cell_size
                )
                center_row = int(
                    (detonation_pos.northing - origin_northing) / cell_size
                )

                nrows, ncols = data.shape
                for dr in range(-cells_radius, cells_radius + 1):
                    for dc in range(-cells_radius, cells_radius + 1):
                        r = center_row + dr
                        c = center_col + dc
                        if 0 <= r < nrows and 0 <= c < ncols:
                            # Distance from center in meters
                            dist = math.sqrt(
                                (dr * cell_size) ** 2 + (dc * cell_size) ** 2
                            )
                            if dist <= crater_radius:
                                # Depression proportional to distance from center
                                depth_frac = 1.0 - (dist / crater_radius)
                                data[r, c] -= crater_depth * depth_frac

        # Modify classification if available and supports set_classification
        if classification is not None and hasattr(classification, "set_classification"):
            cell_size_cls = getattr(classification, "cell_size", None)
            if cell_size_cls is not None:
                cells_radius_cls = int(math.ceil(crater_radius / cell_size_cls))

                origin_e_cls = getattr(classification, "_config", None)
                if origin_e_cls is not None:
                    origin_easting_cls = getattr(origin_e_cls, "origin_easting", 0.0)
                    origin_northing_cls = getattr(
                        origin_e_cls, "origin_northing", 0.0
                    )
                    center_col_cls = int(
                        (detonation_pos.easting - origin_easting_cls) / cell_size_cls
                    )
                    center_row_cls = int(
                        (detonation_pos.northing - origin_northing_cls) / cell_size_cls
                    )
                    shape = getattr(classification, "shape", None)
                    if shape is not None:
                        nrows_cls, ncols_cls = shape
                        for dr in range(-cells_radius_cls, cells_radius_cls + 1):
                            for dc in range(-cells_radius_cls, cells_radius_cls + 1):
                                r = center_row_cls + dr
                                c = center_col_cls + dc
                                if 0 <= r < nrows_cls and 0 <= c < ncols_cls:
                                    dist = math.sqrt(
                                        (dr * cell_size_cls) ** 2
                                        + (dc * cell_size_cls) ** 2
                                    )
                                    if dist <= crater_radius:
                                        # Set to OPEN (bare ground after blast)
                                        classification.set_classification(r, c, 0)

        logger.info(
            "Crater created at (%.1f, %.1f): radius=%.1f m, depth=%.1f m",
            detonation_pos.easting,
            detonation_pos.northing,
            crater_radius,
            crater_depth,
        )

    # ------------------------------------------------------------------
    # Full detonation orchestration
    # ------------------------------------------------------------------

    def detonate(
        self,
        weapon_id: str,
        position: Position,
        yield_kt: float,
        airburst: bool,
        units_by_side: dict[str, list[Any]],
        weather_conditions: Any,
        contamination_manager: Any,
        agent_registry: Any,
        heightmap: Any,
        classification: Any,
        timestamp: Any,
    ) -> dict[str, Any]:
        """Orchestrate a full nuclear detonation with all effects.

        Sequence:
        1. Compute blast casualties for all units
        2. Compute thermal casualties for all units
        3. Apply EMP to all units
        4. Generate fallout plume (ground burst only)
        5. Modify terrain (ground burst only)
        6. Publish events (NuclearDetonationEvent, EMPEvent, FalloutPlumeEvent)

        Parameters
        ----------
        weapon_id:
            Identifier for this weapon/detonation.
        position:
            Ground zero position.
        yield_kt:
            Weapon yield in kilotons.
        airburst:
            True for airburst, False for ground burst.
        units_by_side:
            Dict mapping side name to list of units.
        weather_conditions:
            Weather object with wind_speed_m_s, wind_direction_rad.
        contamination_manager:
            Contamination grid manager (may be None).
        agent_registry:
            CBRN agent registry (may be None).
        heightmap:
            Heightmap grid object (may be None).
        classification:
            Terrain classification grid (may be None).
        timestamp:
            Simulation timestamp.

        Returns
        -------
        Summary dict with keys: weapon_id, position, yield_kt, airburst,
        blast_casualties, thermal_casualties, emp_affected, fallout_puff_id.
        """
        self._detonation_count += 1

        # Flatten all units across all sides
        all_units: list[Any] = []
        for side_units in units_by_side.values():
            all_units.extend(side_units)

        # 1. Blast casualties
        blast_results = self.compute_blast_casualties(all_units, position, yield_kt)

        # 2. Thermal casualties
        thermal_results = self.compute_thermal_casualties(
            all_units, position, yield_kt
        )

        # 3. EMP
        emp_affected = self.apply_emp(all_units, position, yield_kt, timestamp)

        # 4. Fallout (ground burst only)
        fallout_puff_id: str | None = None
        wind_speed = getattr(weather_conditions, "wind_speed_m_s", 5.0)
        wind_direction = getattr(weather_conditions, "wind_direction_rad", 0.0)

        if not airburst and self._dispersal_engine is not None:
            fallout_puff_id = self.generate_fallout_plume(
                position,
                yield_kt,
                wind_speed,
                wind_direction,
                contamination_manager,
                agent_registry,
                timestamp,
            )

        # 5. Terrain modification (ground burst only)
        if not airburst:
            self.modify_terrain(position, yield_kt, heightmap, classification)

        # 6. Publish events
        self._event_bus.publish(
            NuclearDetonationEvent(
                timestamp=timestamp,
                source=ModuleId.CBRN,
                weapon_id=weapon_id,
                position_easting=position.easting,
                position_northing=position.northing,
                yield_kt=yield_kt,
                airburst=airburst,
            )
        )

        emp_radius = self.emp_radius_m(yield_kt)
        self._event_bus.publish(
            EMPEvent(
                timestamp=timestamp,
                source=ModuleId.CBRN,
                center_easting=position.easting,
                center_northing=position.northing,
                radius_m=emp_radius,
                affected_unit_ids=tuple(emp_affected),
            )
        )

        if fallout_puff_id is not None:
            plume_length = wind_speed * 3600.0  # Estimated 1-hour plume extent
            self._event_bus.publish(
                FalloutPlumeEvent(
                    timestamp=timestamp,
                    source=ModuleId.CBRN,
                    detonation_id=weapon_id,
                    initial_center_easting=position.easting,
                    initial_center_northing=position.northing,
                    wind_direction_rad=wind_direction,
                    estimated_plume_length_m=plume_length,
                )
            )

        logger.info(
            "Nuclear detonation #%d: %s @ (%.0f, %.0f), %.1f kt, %s",
            self._detonation_count,
            weapon_id,
            position.easting,
            position.northing,
            yield_kt,
            "airburst" if airburst else "ground burst",
        )

        return {
            "weapon_id": weapon_id,
            "position": position,
            "yield_kt": yield_kt,
            "airburst": airburst,
            "blast_casualties": blast_results,
            "thermal_casualties": thermal_results,
            "emp_affected": emp_affected,
            "fallout_puff_id": fallout_puff_id,
        }

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        """Return serializable engine state for checkpoint/restore."""
        return {
            "detonation_count": self._detonation_count,
            "config": self._config.model_dump(),
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore engine state from a checkpoint."""
        self._detonation_count = state.get("detonation_count", 0)
        config_data = state.get("config")
        if config_data is not None:
            self._config = NuclearConfig(**config_data)
