"""YAML-driven unit definition loading and factory.

Each unit type is defined in a YAML file under ``data/units/<category>/``.
``UnitLoader`` validates definitions with pydantic and creates appropriate
``Unit`` subclass instances.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.strict_yaml import load_yaml_unique
from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import Unit
from stochastic_warfare.entities.equipment import EquipmentCategory, EquipmentItem
from stochastic_warfare.entities.personnel import CrewMember, CrewRole, SkillLevel
from stochastic_warfare.entities.unit_classes.aerial import (
    AerialUnit,
    AerialUnitType,
    AirPosture,
    FlightState,
)
from stochastic_warfare.entities.unit_classes.air_defense import (
    ADUnitType,
    AirDefenseUnit,
)
from stochastic_warfare.entities.unit_classes.ground import GroundUnit, GroundUnitType
from stochastic_warfare.entities.unit_classes.naval import NavalPosture, NavalUnit, NavalUnitType
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

    model_config = ConfigDict(extra="forbid")

    role: str
    count: int = 1
    skill: str = "TRAINED"

    @field_validator("role", mode="before")
    @classmethod
    def _validate_role(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                "crew role must be a non-empty CrewRole name; "
                f"got {value!r}; allowed={sorted(CrewRole.__members__)!r}",
            )
        normalized = value.strip().upper()
        if normalized == "CREW":
            normalized = "GENERIC"
        if normalized not in CrewRole.__members__:
            raise ValueError(
                f"unknown crew role {value!r}; "
                f"allowed={sorted([*CrewRole.__members__, 'CREW'])!r}",
            )
        return normalized

    @field_validator("skill", mode="before")
    @classmethod
    def _validate_skill(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                "crew skill must be a non-empty SkillLevel name; "
                f"got {value!r}; allowed={sorted(SkillLevel.__members__)!r}",
            )
        normalized = value.strip().upper()
        if normalized not in SkillLevel.__members__:
            raise ValueError(
                f"unknown crew skill {value!r}; "
                f"allowed={sorted(SkillLevel.__members__)!r}",
            )
        return normalized


class EquipmentEntry(BaseModel):
    """Equipment item definition from YAML."""

    model_config = ConfigDict(extra="forbid")

    name: str
    category: str
    weight_kg: float = 0.0
    reliability: float = 0.95
    temperature_range: list[float] | None = None

    @field_validator("category", mode="before")
    @classmethod
    def _validate_category(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                "equipment category must be a non-empty EquipmentCategory "
                f"name; got {value!r}; "
                f"allowed={sorted(EquipmentCategory.__members__)!r}",
            )
        normalized = value.strip().upper()
        if normalized not in EquipmentCategory.__members__:
            raise ValueError(
                f"unknown equipment category {value!r}; "
                f"allowed={sorted(EquipmentCategory.__members__)!r}",
            )
        return normalized


class SensorPolicy(str, enum.Enum):
    """Whether a unit definition requires a runtime detection attachment."""

    REQUIRED = "required"
    INTENTIONALLY_NONE = "intentionally_none"


class UnitDefinition(BaseModel):
    """Pydantic model validated from YAML unit files."""

    model_config = ConfigDict(extra="forbid")

    unit_type: str
    domain: str
    display_name: str
    max_speed: float
    crew: list[CrewEntry]
    equipment: list[EquipmentEntry]
    sensor_policy: SensorPolicy = SensorPolicy.REQUIRED
    sensor_policy_reason: str | None = None

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
    training_level: float = 0.5

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

    @model_validator(mode="after")
    def _validate_sensor_policy(self) -> UnitDefinition:
        """Require an explicit, internally consistent sensor disposition."""
        sensor_entries = [
            entry
            for entry in self.equipment
            if entry.category.upper() == "SENSOR"
        ]
        if self.sensor_policy is SensorPolicy.REQUIRED:
            if not sensor_entries:
                raise ValueError(
                    "sensor_policy='required' needs at least one SENSOR "
                    "equipment entry",
                )
            if self.sensor_policy_reason is not None:
                raise ValueError(
                    "sensor_policy_reason is only valid for "
                    "sensor_policy='intentionally_none'",
                )
            return self

        reason = (
            self.sensor_policy_reason.strip()
            if self.sensor_policy_reason is not None
            else ""
        )
        if not reason:
            raise ValueError(
                "sensor_policy='intentionally_none' needs a non-empty "
                "sensor_policy_reason",
            )
        if sensor_entries:
            raise ValueError(
                "sensor_policy='intentionally_none' forbids SENSOR "
                "equipment entries",
            )
        self.sensor_policy_reason = reason
        return self

    @field_validator(
        "ground_type",
        "aerial_type",
        "naval_type",
        "ad_type",
        "support_type",
        mode="before",
    )
    @classmethod
    def _validate_subtype(cls, value: Any, info: Any) -> str | None:
        if value is None:
            return None
        enum_by_field: dict[str, type[enum.Enum]] = {
            "ground_type": GroundUnitType,
            "aerial_type": AerialUnitType,
            "naval_type": NavalUnitType,
            "ad_type": ADUnitType,
            "support_type": SupportUnitType,
        }
        enum_type = enum_by_field[info.field_name]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"{info.field_name} must be a non-empty {enum_type.__name__} "
                f"name; got {value!r}; "
                f"allowed={sorted(enum_type.__members__)!r}",
            )
        normalized = value.strip().upper()
        if normalized not in enum_type.__members__:
            raise ValueError(
                f"unknown {info.field_name} {value!r}; "
                f"allowed={sorted(enum_type.__members__)!r}",
            )
        return normalized

    @model_validator(mode="after")
    def _validate_domain_subtypes(self) -> UnitDefinition:
        if self.ad_type is not None and self.support_type is not None:
            raise ValueError(
                "unit definition cannot select both ad_type and support_type",
            )
        if (
            (self.ad_type is not None or self.support_type is not None)
            and self.domain != "ground"
        ):
            raise ValueError(
                "air-defense and support unit definitions must use "
                "domain='ground'",
            )

        selected_fields: set[str]
        if self.ad_type is not None:
            selected_fields = {"ground_type", "ad_type"}
        elif self.support_type is not None:
            selected_fields = {"ground_type", "support_type"}
        elif self.domain == "ground":
            selected_fields = {"ground_type"}
        elif self.domain == "aerial":
            selected_fields = {"aerial_type"}
        else:
            selected_fields = {"naval_type"}

        required_field = (
            "ad_type"
            if self.ad_type is not None
            else (
                "support_type"
                if self.support_type is not None
                else (
                    "ground_type"
                    if self.domain == "ground"
                    else (
                        "aerial_type"
                        if self.domain == "aerial"
                        else "naval_type"
                    )
                )
            )
        )
        if getattr(self, required_field) is None:
            raise ValueError(
                f"domain {self.domain!r} requires {required_field}",
            )

        populated = {
            field_name
            for field_name in (
                "ground_type",
                "aerial_type",
                "naval_type",
                "ad_type",
                "support_type",
            )
            if getattr(self, field_name) is not None
        }
        incompatible = sorted(populated - selected_fields)
        if incompatible:
            raise ValueError(
                f"domain {self.domain!r} has incompatible subtype fields "
                f"{incompatible!r}",
            )
        return self


def runtime_domain_for_definition(definition: UnitDefinition) -> Domain:
    """Return the domain the production unit subclass will publish."""
    authored_domain = _DOMAIN_MAP[definition.domain]
    if definition.ad_type is not None or definition.support_type is not None:
        return Domain.GROUND
    if authored_domain is Domain.AERIAL:
        return Domain.AERIAL
    if authored_domain in (
        Domain.NAVAL,
        Domain.SUBMARINE,
        Domain.AMPHIBIOUS,
    ):
        naval_type = (
            NavalUnitType[definition.naval_type.upper()]
            if definition.naval_type is not None
            else NavalUnitType.DESTROYER
        )
        if naval_type in (
            NavalUnitType.SSN,
            NavalUnitType.SSBN,
            NavalUnitType.SSK,
        ):
            return Domain.SUBMARINE
        if naval_type in (
            NavalUnitType.LHD,
            NavalUnitType.LPD,
            NavalUnitType.LST,
            NavalUnitType.LANDING_CRAFT,
        ):
            return Domain.AMPHIBIOUS
        return Domain.NAVAL
    return Domain.GROUND


# ── Helpers ──────────────────────────────────────────────────────────


def _parse_crew(
    entries: list[CrewEntry], rng: np.random.Generator
) -> list[CrewMember]:
    """Expand crew entries into individual CrewMember objects."""
    members: list[CrewMember] = []
    counter = 0
    for entry in entries:
        role_name = entry.role.upper()
        if role_name == "CREW":
            role_name = "GENERIC"
        role = CrewRole[role_name]
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


class MissingUnitDefinitionError(LookupError):
    """Raised when a requested unit type has no loaded definition."""


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
        try:
            with open(path, encoding="utf-8") as definition_file:
                raw = load_yaml_unique(definition_file)
            defn = UnitDefinition.model_validate(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid unit definition {path}: {exc}",
            ) from exc
        if defn.unit_type in self._definitions:
            raise ValueError(
                f"Duplicate unit_type {defn.unit_type!r} while loading {path}",
            )
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

    def definitions(self) -> Mapping[str, UnitDefinition]:
        """Return a read-only snapshot of the effective unit definitions."""
        return MappingProxyType(dict(self._definitions))

    def get_definition(self, unit_type: str) -> UnitDefinition:
        """Return the definition for *unit_type*.

        Raises :class:`MissingUnitDefinitionError` if not loaded.
        """
        try:
            return self._definitions[unit_type]
        except KeyError as exc:
            raise MissingUnitDefinitionError(
                f"Unit definition {unit_type!r} is not loaded",
            ) from exc

    def create_unit(
        self,
        unit_type: str,
        entity_id: str,
        position: Position,
        side: str,
        rng: np.random.Generator,
    ) -> Unit:
        """Instantiate a Unit subclass from a loaded definition."""
        defn = self.get_definition(unit_type)
        personnel = _parse_crew(defn.crew, rng)
        equipment = _parse_equipment(defn.equipment)
        domain = runtime_domain_for_definition(defn)

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
            training_level=defn.training_level,
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
            # Phase 50b: scenarios assume aircraft are operational on spawn
            kwargs["flight_state"] = FlightState.AIRBORNE
            kwargs["air_posture"] = AirPosture.ON_STATION
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
            # Phase 51b: naval units spawn UNDERWAY by default
            kwargs["naval_posture"] = NavalPosture.UNDERWAY
            return NavalUnit(**common, **kwargs)

        # Default: ground
        kwargs = {}
        if defn.ground_type is not None:
            kwargs["ground_type"] = GroundUnitType[defn.ground_type.upper()]
        kwargs["armor_front"] = defn.armor_front
        kwargs["armor_side"] = defn.armor_side
        kwargs["armor_type"] = defn.armor_type
        return GroundUnit(**common, **kwargs)
