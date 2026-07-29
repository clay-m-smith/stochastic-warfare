"""Strict scenario configuration for the production logistics runtime."""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from stochastic_warfare.logistics.stockpile import DepotType
from stochastic_warfare.logistics.supply_classes import SupplyClass
from stochastic_warfare.logistics.supply_network import TransportMode


def _require_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    return normalized


def _require_nonempty(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
    return value


class SupplyQuantityConfig(BaseModel):
    """One catalog-backed, item-native supply quantity."""

    model_config = ConfigDict(extra="forbid")

    supply_class: str
    item_id: str
    quantity: float

    @field_validator("supply_class")
    @classmethod
    def _known_supply_class(cls, value: str) -> str:
        value = _require_nonempty(value, "supply_class")
        if value not in SupplyClass.__members__:
            raise ValueError(
                "supply_class must be an exact SupplyClass name; "
                f"got {value!r}",
            )
        return value

    @field_validator("item_id")
    @classmethod
    def _nonempty_item_id(cls, value: str) -> str:
        return _require_nonempty(value, "item_id")

    @field_validator("quantity", mode="before")
    @classmethod
    def _positive_quantity(cls, value: Any) -> float:
        normalized = _require_number(value, "quantity")
        if normalized <= 0.0:
            raise ValueError("quantity must be positive")
        return normalized

    @property
    def supply_class_value(self) -> int:
        """Return the integer ``SupplyClass`` value."""
        return int(SupplyClass[self.supply_class])


def _quantity_map(
    entries: list[SupplyQuantityConfig],
    field_name: str,
) -> dict[tuple[int, str], float]:
    result: dict[tuple[int, str], float] = {}
    for entry in entries:
        key = (entry.supply_class_value, entry.item_id)
        if key in result:
            raise ValueError(
                f"{field_name} contains duplicate supply item "
                f"{entry.supply_class}/{entry.item_id}",
            )
        result[key] = entry.quantity
    return result


class UnitLogisticsProfileConfig(BaseModel):
    """Initial, maximum, and idle supply quantities for one unit type."""

    model_config = ConfigDict(extra="forbid")

    side: str
    unit_type: str
    initial_inventory: list[SupplyQuantityConfig]
    maximum_inventory: list[SupplyQuantityConfig]
    idle_consumption_per_hour: list[SupplyQuantityConfig]

    @field_validator("side", "unit_type")
    @classmethod
    def _nonempty_identifiers(cls, value: str, info: Any) -> str:
        return _require_nonempty(value, info.field_name)

    @model_validator(mode="after")
    def _validate_inventory_contract(self) -> UnitLogisticsProfileConfig:
        initial = _quantity_map(self.initial_inventory, "initial_inventory")
        maximum = _quantity_map(self.maximum_inventory, "maximum_inventory")
        idle = _quantity_map(
            self.idle_consumption_per_hour,
            "idle_consumption_per_hour",
        )
        if not maximum:
            raise ValueError("maximum_inventory must contain at least one item")
        for key, quantity in initial.items():
            if key not in maximum:
                raise ValueError(
                    "initial_inventory items must also appear in "
                    "maximum_inventory",
                )
            if quantity > maximum[key]:
                raise ValueError(
                    "initial_inventory quantity must not exceed "
                    "maximum_inventory",
                )
        missing_idle = sorted(set(idle) - set(maximum))
        if missing_idle:
            raise ValueError(
                "idle_consumption_per_hour items must also appear in "
                f"maximum_inventory: {missing_idle!r}",
            )
        return self


class RouteTemplateConfig(BaseModel):
    """One explicit same-side direct depot-to-unit route template."""

    model_config = ConfigDict(extra="forbid")

    route_id: str
    side: str
    depot_id: str
    unit_types: list[str]
    transport_mode: str
    transport_speed_kph: float
    capacity_tons_per_hour: float
    condition: float = 1.0

    @field_validator("route_id", "side", "depot_id")
    @classmethod
    def _nonempty_identifiers(cls, value: str, info: Any) -> str:
        return _require_nonempty(value, info.field_name)

    @field_validator("unit_types")
    @classmethod
    def _valid_unit_types(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("unit_types must contain at least one unit type")
        normalized = [
            _require_nonempty(unit_type, "unit_types entry")
            for unit_type in value
        ]
        if len(normalized) != len(set(normalized)):
            raise ValueError("unit_types must not contain duplicates")
        return normalized

    @field_validator("transport_mode")
    @classmethod
    def _known_transport_mode(cls, value: str) -> str:
        value = _require_nonempty(value, "transport_mode")
        if value not in TransportMode.__members__:
            raise ValueError(
                "transport_mode must be an exact TransportMode name; "
                f"got {value!r}",
            )
        return value

    @field_validator(
        "transport_speed_kph",
        "capacity_tons_per_hour",
        mode="before",
    )
    @classmethod
    def _positive_rates(cls, value: Any, info: Any) -> float:
        normalized = _require_number(value, info.field_name)
        if normalized <= 0.0:
            raise ValueError(f"{info.field_name} must be positive")
        return normalized

    @field_validator("condition", mode="before")
    @classmethod
    def _valid_condition(cls, value: Any) -> float:
        normalized = _require_number(value, "condition")
        if not 0.0 <= normalized <= 1.0:
            raise ValueError("condition must be in [0, 1]")
        return normalized

    @property
    def transport_mode_value(self) -> TransportMode:
        """Return the configured transport mode enum."""
        return TransportMode[self.transport_mode]


class LogisticsConfig(BaseModel):
    """Opt-in logistics runtime configuration for a campaign."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    update_interval_seconds: float = 3600.0
    unit_profiles: list[UnitLogisticsProfileConfig] = Field(
        default_factory=list,
    )
    route_templates: list[RouteTemplateConfig] = Field(default_factory=list)

    @field_validator("enabled", mode="before")
    @classmethod
    def _strict_enabled(cls, value: Any) -> bool:
        if not isinstance(value, bool):
            raise ValueError("enabled must be boolean")
        return value

    @field_validator("update_interval_seconds", mode="before")
    @classmethod
    def _positive_interval(cls, value: Any) -> float:
        normalized = _require_number(value, "update_interval_seconds")
        if normalized <= 0.0:
            raise ValueError("update_interval_seconds must be positive")
        return normalized

    @model_validator(mode="after")
    def _unique_templates(self) -> LogisticsConfig:
        profile_keys = [
            (profile.side, profile.unit_type)
            for profile in self.unit_profiles
        ]
        if len(profile_keys) != len(set(profile_keys)):
            raise ValueError(
                "unit_profiles must be unique by (side, unit_type)",
            )
        route_ids = [route.route_id for route in self.route_templates]
        if len(route_ids) != len(set(route_ids)):
            raise ValueError("route_templates must have unique route_id values")
        return self


__all__ = [
    "LogisticsConfig",
    "RouteTemplateConfig",
    "SupplyQuantityConfig",
    "UnitLogisticsProfileConfig",
]
