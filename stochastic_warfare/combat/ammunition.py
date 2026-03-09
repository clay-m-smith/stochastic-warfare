"""Weapon and ammunition data models, loaders, and runtime state.

Weapons and ammunition are defined in YAML files under ``data/weapons/``
and ``data/ammunition/`` respectively.  A weapon may fire multiple ammo
types (linked via ``compatible_ammo``).  :class:`WeaponInstance` wraps a
weapon definition with runtime ammo state and equipment condition.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.entities.equipment import EquipmentItem

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class WeaponCategory(enum.IntEnum):
    """Weapon system classification."""

    CANNON = 0
    MACHINE_GUN = 1
    HOWITZER = 2
    MORTAR = 3
    ROCKET_LAUNCHER = 4
    MISSILE_LAUNCHER = 5
    TORPEDO_TUBE = 6
    NAVAL_GUN = 7
    AAA = 8
    AIRCRAFT_GUN = 9
    MINE_LAYER = 10
    CIWS = 11
    DIRECTED_ENERGY = 12


class GuidanceType(enum.IntEnum):
    """Missile / guided munition guidance method."""

    NONE = 0
    INERTIAL = 1
    GPS = 2
    LASER = 3
    RADAR_ACTIVE = 4
    RADAR_SEMI = 5
    IR = 6
    WIRE = 7
    COMMAND = 8
    TERCOM = 9
    COMBINED = 10


class AmmoType(enum.IntEnum):
    """Ammunition functional classification."""

    AP = 0
    HE = 1
    HEAT = 2
    DPICM = 3
    SMOKE = 4
    ILLUMINATION = 5
    GUIDED = 6
    ROCKET = 7
    MISSILE = 8
    TORPEDO = 9
    CLUSTER = 10
    INCENDIARY_WEAPON = 11
    ANTI_PERSONNEL_MINE = 12
    EXPANDING = 13
    DIRECTED_ENERGY = 14


# ---------------------------------------------------------------------------
# Pydantic definitions
# ---------------------------------------------------------------------------


_CATEGORY_DEFAULT_DOMAINS: dict[int, set[str]] = {
    WeaponCategory.CANNON: {"GROUND"},
    WeaponCategory.MACHINE_GUN: {"GROUND", "AERIAL"},
    WeaponCategory.HOWITZER: {"GROUND"},
    WeaponCategory.MORTAR: {"GROUND"},
    WeaponCategory.ROCKET_LAUNCHER: {"GROUND"},
    WeaponCategory.MISSILE_LAUNCHER: {"GROUND", "AERIAL"},
    WeaponCategory.TORPEDO_TUBE: {"NAVAL", "SUBMARINE"},
    WeaponCategory.NAVAL_GUN: {"GROUND", "NAVAL"},
    WeaponCategory.AAA: {"AERIAL"},
    WeaponCategory.AIRCRAFT_GUN: {"GROUND", "AERIAL"},
    WeaponCategory.MINE_LAYER: {"GROUND", "NAVAL"},
    WeaponCategory.CIWS: {"AERIAL", "NAVAL"},
    WeaponCategory.DIRECTED_ENERGY: {"GROUND", "AERIAL", "NAVAL"},
}


class WeaponDefinition(BaseModel):
    """Weapon system specification loaded from YAML."""

    weapon_id: str
    display_name: str
    category: str  # WeaponCategory name
    caliber_mm: float

    # Ballistic parameters
    muzzle_velocity_mps: float = 0.0
    max_range_m: float = 0.0
    effective_range_m: float = 0.0  # 0 = compute as 80% of max_range_m
    min_range_m: float = 0.0
    rate_of_fire_rpm: float = 0.0
    burst_size: int = 1

    # Accuracy
    base_accuracy_mrad: float = 0.0  # unguided dispersion
    cep_m: float = 0.0  # guided CEP at reference range

    # Engagement envelope (primarily for AD / naval)
    min_engagement_altitude_m: float = 0.0
    max_engagement_altitude_m: float = 100000.0
    guidance: str = "NONE"  # GuidanceType name

    # Logistics
    magazine_capacity: int = 0
    reload_time_s: float = 0.0
    compatible_ammo: list[str] = []

    # Physical
    weight_kg: float = 0.0
    reliability: float = 0.95
    barrel_life_rounds: int = 0

    # Directed energy (Phase 28.5)
    beam_power_kw: float = 0.0
    beam_wavelength_nm: float = 0.0
    dwell_time_s: float = 0.0
    beam_divergence_mrad: float = 0.0

    # Deployment
    requires_deployed: bool = False
    traverse_deg: float = 360.0
    elevation_min_deg: float = -5.0
    elevation_max_deg: float = 85.0

    # Domain targeting (Phase 40d)
    target_domains: list[str] = []  # empty = infer from category

    def effective_target_domains(self) -> set[str]:
        """Return the set of domains this weapon can engage."""
        if self.target_domains:
            return set(self.target_domains)
        try:
            return _CATEGORY_DEFAULT_DOMAINS.get(
                self.parsed_category(), {"GROUND", "NAVAL"}
            )
        except (KeyError, ValueError):
            return {"GROUND", "NAVAL"}

    def parsed_category(self) -> WeaponCategory:
        """Return the enum value for this definition's category string."""
        return WeaponCategory[self.category.upper()]

    def get_effective_range(self) -> float:
        """Return effective engagement range. Defaults to 80% of max_range_m."""
        if self.effective_range_m > 0:
            return self.effective_range_m
        return self.max_range_m * 0.8

    def parsed_guidance(self) -> GuidanceType:
        """Return the enum value for this definition's guidance string."""
        return GuidanceType[self.guidance.upper()]


class AmmoDefinition(BaseModel):
    """Ammunition specification loaded from YAML."""

    ammo_id: str
    display_name: str
    ammo_type: str  # AmmoType name

    # Physical
    mass_kg: float = 0.0
    diameter_mm: float = 0.0
    drag_coefficient: float = 0.3

    # Terminal effects
    penetration_mm_rha: float = 0.0
    penetration_reference_range_m: float = 0.0
    blast_radius_m: float = 0.0
    fragmentation_radius_m: float = 0.0
    explosive_fill_kg: float = 0.0
    """TNT-equivalent explosive fill in kg.  When > 0, used directly for
    Hopkinson-Cranz blast calculation.  When 0 (all legacy YAML), derived
    from blast_radius_m via calibration constant."""

    # Guidance (for guided munitions)
    guidance: str = "NONE"
    seeker_fov_deg: float = 0.0
    seeker_range_m: float = 0.0
    pk_at_reference: float = 0.0
    countermeasure_susceptibility: float = 0.0

    # Propulsion (for missiles/rockets)
    propulsion: str = "none"  # "none", "rocket", "turbojet", "ramjet"
    max_speed_mps: float = 0.0
    flight_time_s: float = 0.0
    cruise_altitude_m: float = 0.0
    terminal_maneuver: bool = False

    # Submunitions (DPICM, cluster)
    submunition_count: int = 0
    submunition_lethal_radius_m: float = 0.0

    # Cost
    unit_cost_factor: float = 1.0

    # Treaty compliance (Phase 24b)
    prohibited_under_treaties: list[str] = []
    compliance_check: bool = False
    uxo_rate: float = 0.0  # submunition failure rate

    def parsed_ammo_type(self) -> AmmoType:
        """Return the enum value for this definition's ammo_type string."""
        return AmmoType[self.ammo_type.upper()]

    def parsed_guidance(self) -> GuidanceType:
        """Return the enum value for this definition's guidance string."""
        return GuidanceType[self.guidance.upper()]


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


class WeaponLoader:
    """Load and cache :class:`WeaponDefinition` instances from YAML files."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._definitions: dict[str, WeaponDefinition] = {}

    def load_definition(self, path: Path) -> WeaponDefinition:
        """Load and validate a single YAML weapon definition."""
        import yaml

        with open(path) as f:
            raw = yaml.safe_load(f)
        defn = WeaponDefinition.model_validate(raw)
        self._definitions[defn.weapon_id] = defn
        return defn

    def load_all(self) -> None:
        """Recursively load all ``*.yaml`` files under *data_dir*."""
        for yaml_path in sorted(self._data_dir.rglob("*.yaml")):
            self.load_definition(yaml_path)
        logger.info("Loaded %d weapon definitions", len(self._definitions))

    def get_definition(self, weapon_id: str) -> WeaponDefinition:
        """Return a loaded definition.  Raises ``KeyError`` if not found."""
        return self._definitions[weapon_id]

    def available_weapons(self) -> list[str]:
        """Return sorted list of loaded weapon identifiers."""
        return sorted(self._definitions.keys())


class AmmoLoader:
    """Load and cache :class:`AmmoDefinition` instances from YAML files."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._definitions: dict[str, AmmoDefinition] = {}

    def load_definition(self, path: Path) -> AmmoDefinition:
        """Load and validate a single YAML ammo definition."""
        import yaml

        with open(path) as f:
            raw = yaml.safe_load(f)
        defn = AmmoDefinition.model_validate(raw)
        self._definitions[defn.ammo_id] = defn
        return defn

    def load_all(self) -> None:
        """Recursively load all ``*.yaml`` files under *data_dir*."""
        for yaml_path in sorted(self._data_dir.rglob("*.yaml")):
            self.load_definition(yaml_path)
        logger.info("Loaded %d ammo definitions", len(self._definitions))

    def get_definition(self, ammo_id: str) -> AmmoDefinition:
        """Return a loaded definition.  Raises ``KeyError`` if not found."""
        return self._definitions[ammo_id]

    def available_ammo(self) -> list[str]:
        """Return sorted list of loaded ammo identifiers."""
        return sorted(self._definitions.keys())


# ---------------------------------------------------------------------------
# Runtime state
# ---------------------------------------------------------------------------


@dataclass
class MissileState:
    """Individual missile tracked in a launcher."""

    missile_id: str
    ammo_id: str
    status: str = "ready"  # "ready", "launched", "expended"
    ready_time: float = 0.0  # sim time when ready after reload

    def get_state(self) -> dict[str, Any]:
        return {
            "missile_id": self.missile_id,
            "ammo_id": self.ammo_id,
            "status": self.status,
            "ready_time": self.ready_time,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self.missile_id = state["missile_id"]
        self.ammo_id = state["ammo_id"]
        self.status = state["status"]
        self.ready_time = state["ready_time"]


@dataclass
class AmmoState:
    """Per-weapon ammunition tracking."""

    rounds_by_type: dict[str, int] = field(default_factory=dict)
    missiles: list[MissileState] = field(default_factory=list)
    total_rounds_fired: int = 0

    def consume(self, ammo_id: str, count: int = 1) -> bool:
        """Consume *count* rounds of *ammo_id*.  Returns False if insufficient."""
        available = self.rounds_by_type.get(ammo_id, 0)
        if available < count:
            return False
        self.rounds_by_type[ammo_id] = available - count
        self.total_rounds_fired += count
        return True

    def add(self, ammo_id: str, count: int) -> None:
        """Add *count* rounds of *ammo_id* (resupply)."""
        self.rounds_by_type[ammo_id] = self.rounds_by_type.get(ammo_id, 0) + count

    def available(self, ammo_id: str) -> int:
        """Return available rounds of *ammo_id*."""
        return self.rounds_by_type.get(ammo_id, 0)

    def launch_missile(self, missile_id: str) -> bool:
        """Mark a missile as launched.  Returns False if not ready."""
        for m in self.missiles:
            if m.missile_id == missile_id and m.status == "ready":
                m.status = "launched"
                return True
        return False

    def ready_missile_count(self, ammo_id: str | None = None) -> int:
        """Count of missiles in ready state, optionally filtered by ammo_id."""
        return sum(
            1 for m in self.missiles
            if m.status == "ready" and (ammo_id is None or m.ammo_id == ammo_id)
        )

    def get_state(self) -> dict[str, Any]:
        return {
            "rounds_by_type": dict(self.rounds_by_type),
            "missiles": [m.get_state() for m in self.missiles],
            "total_rounds_fired": self.total_rounds_fired,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self.rounds_by_type = dict(state["rounds_by_type"])
        self.total_rounds_fired = state["total_rounds_fired"]
        self.missiles = []
        for ms in state["missiles"]:
            m = MissileState(missile_id="", ammo_id="")
            m.set_state(ms)
            self.missiles.append(m)


class WeaponInstance:
    """Runtime weapon on a specific unit — wraps definition + ammo + equipment.

    Parameters
    ----------
    definition:
        The weapon's YAML-loaded specification.
    ammo_state:
        Per-weapon ammunition tracking.
    equipment:
        Optional link to an :class:`EquipmentItem` for condition tracking.
    """

    def __init__(
        self,
        definition: WeaponDefinition,
        ammo_state: AmmoState | None = None,
        equipment: EquipmentItem | None = None,
    ) -> None:
        self.definition = definition
        self.ammo_state = ammo_state or AmmoState()
        self.equipment = equipment
        self._rounds_since_maintenance: int = 0
        # Fire rate limiting: cooldown computed from rate_of_fire_rpm
        self._last_fire_time_s: float = float("-inf")
        if definition.rate_of_fire_rpm > 0:
            self._cooldown_s: float = 60.0 / definition.rate_of_fire_rpm
        else:
            self._cooldown_s: float = 0.0

    @property
    def weapon_id(self) -> str:
        return self.definition.weapon_id

    @property
    def operational(self) -> bool:
        """True if the weapon is functional."""
        if self.equipment is None:
            return True
        return self.equipment.operational and self.equipment.condition > 0.0

    @property
    def condition(self) -> float:
        """Weapon condition 0.0–1.0 incorporating barrel wear."""
        base = self.equipment.condition if self.equipment else 1.0
        if self.definition.barrel_life_rounds > 0:
            wear = 1.0 - (
                self._rounds_since_maintenance / self.definition.barrel_life_rounds
            )
            wear = max(0.0, wear)
            return base * wear
        return base

    def can_fire(self, ammo_id: str) -> bool:
        """Check if weapon can fire the given ammo type (ammo + operational)."""
        if not self.operational:
            return False
        if ammo_id not in self.definition.compatible_ammo:
            return False
        return self.ammo_state.available(ammo_id) > 0

    def can_fire_timed(self, current_time_s: float) -> bool:
        """Check if enough time has elapsed since last fire (rate-of-fire limit).

        Parameters
        ----------
        current_time_s : float
            Current simulation time in seconds.

        Returns ``True`` if the cooldown has elapsed or the weapon has no ROF limit.
        """
        if self._cooldown_s <= 0:
            return True
        return (current_time_s - self._last_fire_time_s) >= self._cooldown_s

    def record_fire(self, current_time_s: float) -> None:
        """Record the time of a successful fire for cooldown tracking."""
        self._last_fire_time_s = current_time_s

    def fire(self, ammo_id: str, count: int = 1) -> bool:
        """Attempt to fire.  Returns True on success, False if unable."""
        if not self.can_fire(ammo_id):
            return False
        if not self.ammo_state.consume(ammo_id, count):
            return False
        self._rounds_since_maintenance += count
        return True

    def reload(self, ammo_id: str, count: int) -> None:
        """Add ammunition (resupply)."""
        self.ammo_state.add(ammo_id, count)

    def get_state(self) -> dict[str, Any]:
        return {
            "weapon_id": self.definition.weapon_id,
            "ammo_state": self.ammo_state.get_state(),
            "rounds_since_maintenance": self._rounds_since_maintenance,
            "equipment_condition": (
                self.equipment.condition if self.equipment else 1.0
            ),
            "equipment_operational": (
                self.equipment.operational if self.equipment else True
            ),
            "last_fire_time_s": self._last_fire_time_s,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self.ammo_state.set_state(state["ammo_state"])
        self._rounds_since_maintenance = state["rounds_since_maintenance"]
        if self.equipment is not None:
            self.equipment.condition = state["equipment_condition"]
            self.equipment.operational = state["equipment_operational"]
        self._last_fire_time_s = state.get("last_fire_time_s", float("-inf"))
