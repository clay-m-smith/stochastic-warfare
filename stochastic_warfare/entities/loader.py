"""YAML-driven unit definition loading and factory.

Each unit type is defined in a YAML file under ``data/units/<category>/``.
``UnitLoader`` validates definitions with pydantic and creates appropriate
``Unit`` subclass instances.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel, field_validator

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import Domain, Position, Side
from stochastic_warfare.entities.base import Unit
from stochastic_warfare.entities.equipment import EquipmentCategory, EquipmentItem
from stochastic_warfare.entities.personnel import CrewMember, CrewRole, SkillLevel
from stochastic_warfare.entities.unit_classes.aerial import (
    AerialUnit,
    AerialUnitType,
)
from stochastic_warfare.entities.unit_classes.air_defense import (
    ADUnitType,
    AirDefenseUnit,
)
from stochastic_warfare.entities.unit_classes.ground import GroundUnit, GroundUnitType
from stochastic_warfare.entities.unit_classes.naval import NavalUnit, NavalUnitType
from stochastic_warfare.entities.unit_classes.support import SupportUnit, SupportUnitType

logger = get_logger(__name__)

# ── Pydantic schema ──────────────────────────────────────────────────

_DOMAIN_MAP: dict[str, Domain] = {
    "ground": Domain.GROUND,
    "aerial": Domain.AERIAL,
    "naval": Domain.NAVAL,
    "submarine": Domain.SUBMARINE,
    "amphibious": Domain.AMPHIBIOUS,
}


class CrewEntry(BaseModel):
    """One or more crew members sharing a role."""

    role: str
    count: int = 1
    skill: str = "TRAINED"


class EquipmentEntry(BaseModel):
    """Equipment item definition from YAML."""

    name: str
    category: str
    weight_kg: float = 0.0
    reliability: float = 0.95
    temperature_range: list[float] | None = None
    weapon_ref: str | None = None  # References WeaponDefinition.weapon_id


class UnitDefinition(BaseModel):
    """Pydantic model validated from YAML unit files."""

    unit_type: str
    domain: str
    display_name: str
    max_speed: float
    crew: list[CrewEntry]
    equipment: list[EquipmentEntry]

    # Domain-specific optional fields
    ground_type: str | None = None
    aerial_type: str | None = None
    naval_type: str | None = None
    ad_type: str | None = None
    support_type: str | None = None

    # Ground
    armor_front: float = 0.0
    armor_side: float = 0.0
    armor_type: str = "RHA"

    # Aerial
    service_ceiling: float = 15000.0
    data_link_range: float | None = None

    # Naval
    draft: float = 0.0
    displacement: float = 0.0
    fuel_capacity: float = 0.0
    max_depth: float = 0.0
    noise_signature_base: float = 0.0

    # Air defense
    min_engagement_altitude: float = 0.0
    max_engagement_altitude: float = 0.0
    max_engagement_range: float = 0.0
    ready_missiles: int = 0
    reload_time: float = 0.0

    # Support
    cargo_capacity_tons: float = 0.0

    @field_validator("domain")
    @classmethod
    def _validate_domain(cls, v: str) -> str:
        if v.lower() not in _DOMAIN_MAP:
            raise ValueError(f"Unknown domain {v!r}")
        return v.lower()


# ── Helpers ──────────────────────────────────────────────────────────


def _parse_crew(
    entries: list[CrewEntry], rng: np.random.Generator
) -> list[CrewMember]:
    """Expand crew entries into individual CrewMember objects."""
    members: list[CrewMember] = []
    counter = 0
    for entry in entries:
        role = CrewRole[entry.role.upper()]
        skill = SkillLevel[entry.skill.upper()]
        for _ in range(entry.count):
            experience = float(rng.uniform(0.0, 0.3))
            members.append(
                CrewMember(
                    member_id=f"crew-{counter:04d}",
                    role=role,
                    skill=skill,
                    experience=round(experience, 4),
                )
            )
            counter += 1
    return members


def _parse_equipment(entries: list[EquipmentEntry]) -> list[EquipmentItem]:
    """Convert YAML equipment entries into EquipmentItem objects."""
    items: list[EquipmentItem] = []
    for i, entry in enumerate(entries):
        cat = EquipmentCategory[entry.category.upper()]
        temp = tuple(entry.temperature_range) if entry.temperature_range else (-40.0, 50.0)
        items.append(
            EquipmentItem(
                equipment_id=f"equip-{i:04d}",
                name=entry.name,
                category=cat,
                weight_kg=entry.weight_kg,
                reliability=entry.reliability,
                temperature_range=temp,
            )
        )
    return items


# ── Loader ───────────────────────────────────────────────────────────


class UnitLoader:
    """Load YAML unit definitions and create Unit instances.

    Parameters
    ----------
    data_dir:
        Root directory containing ``units/`` sub-folders.
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._definitions: dict[str, UnitDefinition] = {}

    def load_definition(self, path: Path) -> UnitDefinition:
        """Load and validate a single YAML unit definition."""
        import yaml

        with open(path) as f:
            raw = yaml.safe_load(f)
        defn = UnitDefinition.model_validate(raw)
        self._definitions[defn.unit_type] = defn
        return defn

    def load_all(self) -> None:
        """Recursively load all YAML files under *data_dir*."""
        for yaml_path in sorted(self._data_dir.rglob("*.yaml")):
            self.load_definition(yaml_path)
        logger.info("Loaded %d unit definitions", len(self._definitions))

    def available_types(self) -> list[str]:
        """Return sorted list of loaded unit type identifiers."""
        return sorted(self._definitions.keys())

    def get_definition(self, unit_type: str) -> UnitDefinition:
        """Return the definition for *unit_type*.

        Raises ``KeyError`` if not loaded.
        """
        return self._definitions[unit_type]

    def create_unit(
        self,
        unit_type: str,
        entity_id: str,
        position: Position,
        side: str,
        rng: np.random.Generator,
    ) -> Unit:
        """Instantiate a Unit subclass from a loaded definition."""
        defn = self._definitions[unit_type]
        personnel = _parse_crew(defn.crew, rng)
        equipment = _parse_equipment(defn.equipment)
        domain = _DOMAIN_MAP[defn.domain]

        common: dict[str, Any] = dict(
            entity_id=entity_id,
            position=position,
            name=defn.display_name,
            unit_type=defn.unit_type,
            side=side,
            domain=domain,
            max_speed=defn.max_speed,
            personnel=personnel,
            equipment=equipment,
        )

        if defn.ad_type is not None:
            return AirDefenseUnit(
                **common,
                ad_type=ADUnitType[defn.ad_type.upper()],
                min_engagement_altitude=defn.min_engagement_altitude,
                max_engagement_altitude=defn.max_engagement_altitude,
                max_engagement_range=defn.max_engagement_range,
                ready_missiles=defn.ready_missiles,
                reload_time=defn.reload_time,
            )

        if defn.support_type is not None:
            return SupportUnit(
                **common,
                support_type=SupportUnitType[defn.support_type.upper()],
                cargo_capacity_tons=defn.cargo_capacity_tons,
            )

        if domain == Domain.AERIAL:
            kwargs: dict[str, Any] = {}
            if defn.aerial_type is not None:
                kwargs["aerial_type"] = AerialUnitType[defn.aerial_type.upper()]
            kwargs["service_ceiling"] = defn.service_ceiling
            kwargs["data_link_range"] = defn.data_link_range
            return AerialUnit(**common, **kwargs)

        if domain in (Domain.NAVAL, Domain.SUBMARINE, Domain.AMPHIBIOUS):
            kwargs = {}
            if defn.naval_type is not None:
                kwargs["naval_type"] = NavalUnitType[defn.naval_type.upper()]
            kwargs["draft"] = defn.draft
            kwargs["displacement"] = defn.displacement
            kwargs["fuel_capacity"] = defn.fuel_capacity
            kwargs["max_depth"] = defn.max_depth
            kwargs["noise_signature_base"] = defn.noise_signature_base
            return NavalUnit(**common, **kwargs)

        # Default: ground
        kwargs = {}
        if defn.ground_type is not None:
            kwargs["ground_type"] = GroundUnitType[defn.ground_type.upper()]
        kwargs["armor_front"] = defn.armor_front
        kwargs["armor_side"] = defn.armor_side
        kwargs["armor_type"] = defn.armor_type
        return GroundUnit(**common, **kwargs)
