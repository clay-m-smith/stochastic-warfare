"""Typed production boundary for deterministic runtime force construction."""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator

from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import Unit
from stochastic_warfare.entities.loader import (
    MissingUnitDefinitionError,
    UnitDefinition,
    UnitLoader,
    runtime_domain_for_definition,
)


def _finite_number(
    value: Any,
    *,
    field_name: str,
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"{field_name} must be a finite number")
    return float(value)


class UnitInstanceOverrides(BaseModel):
    """Strict, supported per-instance changes applied during construction."""

    model_config = ConfigDict(extra="forbid")

    training_level: float | None = None
    armor_front: float | None = None
    heading: float | None = None
    display_name: str | None = None

    @field_validator("training_level", mode="before")
    @classmethod
    def _valid_training_level(cls, value: Any) -> float | None:
        if value is None:
            return None
        normalized = _finite_number(value, field_name="training_level")
        if not 0.0 <= normalized <= 1.0:
            raise ValueError("training_level must be in [0, 1]")
        return normalized

    @field_validator("armor_front", mode="before")
    @classmethod
    def _valid_armor_front(cls, value: Any) -> float | None:
        if value is None:
            return None
        normalized = _finite_number(value, field_name="armor_front")
        if normalized < 0.0:
            raise ValueError("armor_front must be non-negative")
        return normalized

    @field_validator("heading", mode="before")
    @classmethod
    def _valid_heading(cls, value: Any) -> float | None:
        if value is None:
            return None
        return _finite_number(value, field_name="heading")

    @field_validator("display_name", mode="before")
    @classmethod
    def _valid_display_name(cls, value: Any) -> str | None:
        if value is None:
            return None
        if (
            not isinstance(value, str)
            or not value.strip()
            or value != value.strip()
        ):
            raise ValueError(
                "display_name must be a non-empty trimmed string",
            )
        return value

    def applied_values(self) -> dict[str, float | str]:
        """Return only explicitly authored, non-null override values."""
        return {
            key: value
            for key, value in self.model_dump(exclude_unset=True).items()
            if value is not None
        }


class InitialUnitConfig(BaseModel):
    """One exact unit-type group in an initial scenario force."""

    model_config = ConfigDict(extra="forbid")

    unit_type: str
    count: int = 1
    position: tuple[float, ...] | None = None
    overrides: UnitInstanceOverrides = Field(
        default_factory=UnitInstanceOverrides,
    )

    @field_validator("unit_type", mode="before")
    @classmethod
    def _valid_unit_type(cls, value: Any) -> str:
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
        ):
            raise ValueError("unit_type must be a non-empty trimmed string")
        return value

    @field_validator("count", mode="before")
    @classmethod
    def _valid_count(cls, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("count must be a positive non-boolean integer")
        return value

    @field_validator("position", mode="before")
    @classmethod
    def _valid_position(cls, value: Any) -> tuple[float, ...] | None:
        if value is None:
            return None
        if not isinstance(value, (list, tuple)) or len(value) not in (2, 3):
            raise ValueError(
                "position must contain two or three finite coordinates",
            )
        coordinates = tuple(
            _finite_number(coordinate, field_name="position coordinate")
            for coordinate in value
        )
        return coordinates

    def __getitem__(self, key: str) -> Any:
        """Provide read compatibility for legacy schema-inspection callers."""
        if key not in type(self).model_fields:
            raise KeyError(key)
        value = getattr(self, key)
        if key == "overrides":
            return value.model_dump(exclude_unset=True)
        return value

    def get(self, key: str, default: Any = None) -> Any:
        """Provide typed-model access for legacy read-only callers."""
        try:
            return self[key]
        except KeyError:
            return default


@dataclass(frozen=True)
class InitialForcePlan:
    """Resolved placement inputs for one side's initial force."""

    side: str
    units: tuple[InitialUnitConfig, ...]
    start_easting: float
    start_northing: float
    spacing_m: float


@dataclass(frozen=True)
class RuntimeUnitSpec:
    """One preflighted identity and placement request."""

    entity_id: str
    unit_type: str
    side: str
    position: Position
    overrides: UnitInstanceOverrides = field(
        default_factory=UnitInstanceOverrides,
    )
    manually_positioned: bool = False


class RuntimeForceBuildError(ValueError):
    """Raised when a validated runtime force cannot be constructed exactly."""


class RuntimeForceBuilder:
    """Construct exact production rosters from typed plans and one RNG stream."""

    def __init__(
        self,
        *,
        unit_loader: UnitLoader,
        rng: np.random.Generator,
    ) -> None:
        self._unit_loader = unit_loader
        self._rng = rng

    @staticmethod
    def initial_specs(
        plans: tuple[InitialForcePlan, ...],
    ) -> tuple[RuntimeUnitSpec, ...]:
        """Resolve deterministic IDs and placements without consuming RNG."""
        if not isinstance(plans, tuple) or any(
            not isinstance(plan, InitialForcePlan)
            for plan in plans
        ):
            raise RuntimeForceBuildError(
                "initial force plans must be a tuple of InitialForcePlan values",
            )
        side_names = [plan.side for plan in plans]
        if any(
            not isinstance(side, str)
            or not side
            or side != side.strip()
            for side in side_names
        ):
            raise RuntimeForceBuildError(
                "initial force sides must be non-empty trimmed strings",
            )
        if len(side_names) != len(set(side_names)):
            raise RuntimeForceBuildError(
                f"initial force contains duplicate sides: {side_names!r}",
            )

        specs: list[RuntimeUnitSpec] = []
        for plan in plans:
            if (
                not isinstance(plan.units, tuple)
                or not plan.units
                or any(
                    not isinstance(entry, InitialUnitConfig)
                    for entry in plan.units
                )
            ):
                raise RuntimeForceBuildError(
                    f"initial force side {plan.side!r} requires a non-empty "
                    "tuple of InitialUnitConfig values",
                )
            for entry in plan.units:
                try:
                    InitialUnitConfig.model_validate(
                        entry.model_dump(mode="python"),
                        strict=True,
                    )
                except ValueError as exc:
                    raise RuntimeForceBuildError(
                        f"initial force side {plan.side!r} contains a "
                        f"mutated invalid unit entry: {exc}",
                    ) from exc
            for field_name, value in (
                ("start_easting", plan.start_easting),
                ("start_northing", plan.start_northing),
                ("spacing_m", plan.spacing_m),
            ):
                try:
                    normalized = _finite_number(
                        value,
                        field_name=f"initial force {field_name}",
                    )
                except ValueError as exc:
                    raise RuntimeForceBuildError(str(exc)) from exc
                if field_name == "spacing_m" and normalized < 0.0:
                    raise RuntimeForceBuildError(
                        "initial force spacing_m must be non-negative",
                    )
            total_units = sum(entry.count for entry in plan.units)
            unit_index = 0
            for entry in plan.units:
                for _ in range(entry.count):
                    entity_id = (
                        f"{plan.side}_{entry.unit_type}_{unit_index:04d}"
                    )
                    if entry.position is None:
                        offset_northing = (
                            unit_index - total_units / 2
                        ) * plan.spacing_m
                        position = Position(
                            plan.start_easting,
                            plan.start_northing + offset_northing,
                            0.0,
                        )
                        manually_positioned = False
                    else:
                        position = Position(
                            entry.position[0],
                            entry.position[1],
                            (
                                entry.position[2]
                                if len(entry.position) == 3
                                else 0.0
                            ),
                        )
                        manually_positioned = True
                    specs.append(
                        RuntimeUnitSpec(
                            entity_id=entity_id,
                            unit_type=entry.unit_type,
                            side=plan.side,
                            position=position,
                            overrides=entry.overrides,
                            manually_positioned=manually_positioned,
                        ),
                    )
                    unit_index += 1

        entity_ids = [spec.entity_id for spec in specs]
        if len(entity_ids) != len(set(entity_ids)):
            raise RuntimeForceBuildError(
                f"initial force produced duplicate IDs: {entity_ids!r}",
            )
        return tuple(specs)

    @classmethod
    def initial_entity_ids(
        cls,
        plans: tuple[InitialForcePlan, ...],
    ) -> tuple[str, ...]:
        """Return the exact initial identity topology without construction."""
        return tuple(spec.entity_id for spec in cls.initial_specs(plans))

    def build_initial(
        self,
        plans: tuple[InitialForcePlan, ...],
    ) -> dict[str, list[Unit]]:
        """Build every side exactly, restoring ENTITIES RNG on failure."""
        specs = self.initial_specs(plans)
        constructed = self.build_units(specs)
        result = {plan.side: [] for plan in plans}
        for unit in constructed:
            result[unit.side].append(unit)
        expected_counts = {
            plan.side: sum(entry.count for entry in plan.units)
            for plan in plans
        }
        actual_counts = {
            side: len(units)
            for side, units in result.items()
        }
        if actual_counts != expected_counts:
            raise RuntimeForceBuildError(
                "runtime roster cardinality differs from the typed plan: "
                f"expected={expected_counts!r}, actual={actual_counts!r}",
            )
        return result

    def build_units(
        self,
        specs: tuple[RuntimeUnitSpec, ...],
    ) -> list[Unit]:
        """Preflight and construct one exact unit batch atomically."""
        self._preflight(specs)
        rng_state = copy.deepcopy(self._rng.bit_generator.state)
        units: list[Unit] = []
        try:
            for spec in specs:
                unit = self._unit_loader.create_unit(
                    unit_type=spec.unit_type,
                    entity_id=spec.entity_id,
                    position=spec.position,
                    side=spec.side,
                    rng=self._rng,
                )
                self._apply_overrides(unit, spec.overrides)
                if spec.manually_positioned:
                    object.__setattr__(
                        unit,
                        "_manually_positioned",
                        True,
                    )
                units.append(unit)
        except Exception as exc:
            self._rng.bit_generator.state = rng_state
            exc.add_note(
                "Runtime force construction failed for "
                f"{spec.entity_id!r} ({spec.unit_type!r})",
            )
            raise
        if len(units) != len(specs):
            self._rng.bit_generator.state = rng_state
            raise RuntimeForceBuildError(
                f"Runtime force builder produced {len(units)} of "
                f"{len(specs)} requested units",
            )
        return units

    def _preflight(self, specs: tuple[RuntimeUnitSpec, ...]) -> None:
        if not isinstance(specs, tuple) or any(
            not isinstance(spec, RuntimeUnitSpec)
            for spec in specs
        ):
            raise RuntimeForceBuildError(
                "runtime unit specs must be a tuple of RuntimeUnitSpec values",
            )
        entity_ids = [spec.entity_id for spec in specs]
        if any(
            not isinstance(entity_id, str)
            or not entity_id
            or entity_id != entity_id.strip()
            for entity_id in entity_ids
        ):
            raise RuntimeForceBuildError(
                "runtime unit IDs must be non-empty trimmed strings",
            )
        if len(entity_ids) != len(set(entity_ids)):
            raise RuntimeForceBuildError(
                f"runtime unit batch contains duplicate IDs: {entity_ids!r}",
            )
        for spec in specs:
            if (
                not isinstance(spec.unit_type, str)
                or not spec.unit_type
                or spec.unit_type != spec.unit_type.strip()
            ):
                raise RuntimeForceBuildError(
                    f"runtime unit {spec.entity_id!r} has an invalid unit_type",
                )
            if (
                not isinstance(spec.side, str)
                or not spec.side
                or spec.side != spec.side.strip()
            ):
                raise RuntimeForceBuildError(
                    f"runtime unit {spec.entity_id!r} has an invalid side",
                )
            if not isinstance(spec.position, Position):
                raise RuntimeForceBuildError(
                    f"runtime unit {spec.entity_id!r} position must be a Position",
                )
            for index, coordinate in enumerate(spec.position):
                try:
                    _finite_number(
                        coordinate,
                        field_name=(
                            f"runtime unit {spec.entity_id!r} "
                            f"position[{index}]"
                        ),
                    )
                except ValueError as exc:
                    raise RuntimeForceBuildError(str(exc)) from exc
            if not isinstance(spec.overrides, UnitInstanceOverrides):
                raise RuntimeForceBuildError(
                    f"runtime unit {spec.entity_id!r} overrides must be "
                    "UnitInstanceOverrides",
                )
            try:
                UnitInstanceOverrides.model_validate(
                    spec.overrides.model_dump(mode="python"),
                    strict=True,
                )
            except ValueError as exc:
                raise RuntimeForceBuildError(
                    f"runtime unit {spec.entity_id!r} contains mutated "
                    f"invalid overrides: {exc}",
                ) from exc
            if not isinstance(spec.manually_positioned, bool):
                raise RuntimeForceBuildError(
                    f"runtime unit {spec.entity_id!r} manually_positioned "
                    "must be boolean",
                )
            try:
                definition = self._unit_loader.get_definition(
                    spec.unit_type,
                )
            except MissingUnitDefinitionError as exc:
                raise MissingUnitDefinitionError(
                    f"Runtime unit {spec.entity_id!r} references missing "
                    f"definition {spec.unit_type!r}",
                ) from exc
            self._validate_override_compatibility(
                definition,
                spec.overrides,
            )

    @staticmethod
    def _validate_override_compatibility(
        definition: UnitDefinition,
        overrides: UnitInstanceOverrides,
    ) -> None:
        if (
            overrides.armor_front is not None
            and (
                runtime_domain_for_definition(definition) is not Domain.GROUND
                or definition.ad_type is not None
                or definition.support_type is not None
            )
        ):
            raise RuntimeForceBuildError(
                f"Unit {definition.unit_type!r} is incompatible with "
                "armor_front override",
            )

    @staticmethod
    def _apply_overrides(
        unit: Unit,
        overrides: UnitInstanceOverrides,
    ) -> None:
        for field_name, value in overrides.applied_values().items():
            runtime_field = (
                "name" if field_name == "display_name" else field_name
            )
            object.__setattr__(unit, runtime_field, value)
