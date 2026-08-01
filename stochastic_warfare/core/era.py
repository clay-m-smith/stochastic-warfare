"""Era framework — era definitions, configuration, and pre-defined presets.

Each era specifies which engine subsystems are active, which sensor types
are available, and any physics or tick-resolution overrides.  The engine
core is era-agnostic; eras are primarily **data packages** plus targeted
engine gating.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Mapping

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_serializer,
    model_validator,
)

from stochastic_warfare.core.clock import normalize_clock_duration_seconds


# ---------------------------------------------------------------------------
# Era enum
# ---------------------------------------------------------------------------


class Era(str, Enum):
    """Historical era identifier."""

    MODERN = "modern"
    WW2 = "ww2"
    WW1 = "ww1"
    NAPOLEONIC = "napoleonic"
    ANCIENT_MEDIEVAL = "ancient_medieval"


# ---------------------------------------------------------------------------
# Era configuration
# ---------------------------------------------------------------------------

EraFeature = Literal[
    "ew",
    "space",
    "cbrn",
    "gps",
    "thermal_sights",
    "data_links",
    "pgm",
]


PositiveFiniteFloat = Annotated[
    float,
    Field(strict=True, gt=0.0, allow_inf_nan=False),
]


class _SparseOverrides(BaseModel):
    """Strict immutable declaration whose JSON form contains authored fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="before")
    @classmethod
    def _reject_explicit_null(cls, value: object) -> object:
        if isinstance(value, Mapping):
            null_fields = sorted(
                str(field_name)
                for field_name, field_value in value.items()
                if field_value is None
            )
            if null_fields:
                raise ValueError(
                    "override declarations may not be null: "
                    + ", ".join(null_fields),
                )
        return value

    @model_serializer(mode="plain")
    def _serialize_sparse(self) -> dict[str, float]:
        return {
            field_name: field_value
            for field_name in type(self).model_fields
            if (field_value := getattr(self, field_name)) is not None
        }

    @property
    def is_empty(self) -> bool:
        """Return whether no override value was authored."""
        return not self.model_dump(mode="python")


class EraPhysicsOverrides(_SparseOverrides):
    """Supported sparse era overlays for runtime-owned engine settings."""

    treatment_hours_minor: PositiveFiniteFloat | None = None
    treatment_hours_serious: PositiveFiniteFloat | None = None
    treatment_hours_critical: PositiveFiniteFloat | None = None
    repair_time_hours: PositiveFiniteFloat | None = None

    @field_validator(
        "treatment_hours_minor",
        "treatment_hours_serious",
        "treatment_hours_critical",
        "repair_time_hours",
        mode="before",
    )
    @classmethod
    def _strict_float(
        cls,
        value: object,
        info: object,
    ) -> object:
        if value is not None and type(value) is not float:
            raise ValueError(
                f"{getattr(info, 'field_name')} must be a strict float",
            )
        return value


class EraTickResolutionOverrides(_SparseOverrides):
    """Supported sparse era overlays for simulation resolution durations."""

    strategic_s: PositiveFiniteFloat | None = None
    operational_s: PositiveFiniteFloat | None = None
    tactical_s: PositiveFiniteFloat | None = None

    @field_validator(
        "strategic_s",
        "operational_s",
        "tactical_s",
        mode="before",
    )
    @classmethod
    def _strict_float(
        cls,
        value: object,
        info: object,
    ) -> object:
        if value is not None and type(value) is not float:
            raise ValueError(
                f"{getattr(info, 'field_name')} must be a strict float",
            )
        return value

    @field_validator(
        "strategic_s",
        "operational_s",
        "tactical_s",
    )
    @classmethod
    def _clock_representable(
        cls,
        value: float | None,
        info: object,
    ) -> float | None:
        if value is None:
            return None
        return normalize_clock_duration_seconds(
            value,
            field_name=getattr(info, "field_name"),
        )


class EraConfig(BaseModel):
    """Configuration describing which subsystems and capabilities are
    available in a given era.

    Parameters
    ----------
    era:
        Which era this config represents.
    disabled_modules:
        Set of module keys that are disabled for this era.
        Known keys: ``"ew"``, ``"space"``, ``"cbrn"``, ``"gps"``,
        ``"thermal_sights"``, ``"data_links"``, ``"pgm"``.
    available_sensor_types:
        If non-empty, only these sensor types are allowed.  Empty set
        means all sensor types are available (modern default).
    physics_overrides:
        Supported sparse runtime-engine parameter overrides for this era.
    tick_resolution_overrides:
        Supported sparse tick-duration overrides.
    """

    model_config = ConfigDict(extra="forbid")

    era: Era = Era.MODERN
    disabled_modules: set[EraFeature] = Field(default_factory=set)
    available_sensor_types: set[str] = Field(default_factory=set)
    physics_overrides: EraPhysicsOverrides = Field(
        default_factory=EraPhysicsOverrides,
    )
    tick_resolution_overrides: EraTickResolutionOverrides = Field(
        default_factory=EraTickResolutionOverrides,
    )

    def feature_enabled(self, feature: EraFeature) -> bool:
        """Return whether an era permits one declared runtime feature."""
        return feature not in self.disabled_modules

    @property
    def has_runtime_overrides(self) -> bool:
        """Return whether this era declares any production runtime overlay."""
        return not (
            self.physics_overrides.is_empty
            and self.tick_resolution_overrides.is_empty
        )

    @property
    def has_tick_resolution_overrides(self) -> bool:
        """Return whether this era declares a tick-resolution overlay."""
        return not self.tick_resolution_overrides.is_empty

    @field_serializer(
        "disabled_modules",
        "available_sensor_types",
        when_used="json",
    )
    def _serialize_sets(self, values: set[str]) -> list[str]:
        """Serialize unordered capability sets in stable lexical order."""
        return sorted(values)


# ---------------------------------------------------------------------------
# Pre-defined era configs
# ---------------------------------------------------------------------------

MODERN_ERA_CONFIG = EraConfig(era=Era.MODERN)

WW2_ERA_CONFIG = EraConfig(
    era=Era.WW2,
    disabled_modules={
        "ew",
        "space",
        "cbrn",
        "gps",
        "thermal_sights",
        "data_links",
        "pgm",
    },
    available_sensor_types={
        "VISUAL",
        "RADAR",
        "PASSIVE_SONAR",
        "ACTIVE_SONAR",
    },
)

WW1_ERA_CONFIG = EraConfig(
    era=Era.WW1,
    disabled_modules={
        "ew",
        "space",
        "gps",
        "thermal_sights",
        "data_links",
        "pgm",
    },
    available_sensor_types={"VISUAL", "PASSIVE_SONAR"},
)

NAPOLEONIC_ERA_CONFIG = EraConfig(
    era=Era.NAPOLEONIC,
    disabled_modules={
        "ew",
        "space",
        "cbrn",
        "gps",
        "thermal_sights",
        "data_links",
        "pgm",
    },
    available_sensor_types={"VISUAL"},
)

ANCIENT_MEDIEVAL_ERA_CONFIG = EraConfig(
    era=Era.ANCIENT_MEDIEVAL,
    disabled_modules={
        "ew",
        "space",
        "cbrn",
        "gps",
        "thermal_sights",
        "data_links",
        "pgm",
    },
    available_sensor_types={"VISUAL"},
)

_ERA_REGISTRY: dict[str, EraConfig] = {
    "modern": MODERN_ERA_CONFIG.model_copy(deep=True),
    "ww2": WW2_ERA_CONFIG.model_copy(deep=True),
    "ww1": WW1_ERA_CONFIG.model_copy(deep=True),
    "napoleonic": NAPOLEONIC_ERA_CONFIG.model_copy(deep=True),
    "ancient_medieval": ANCIENT_MEDIEVAL_ERA_CONFIG.model_copy(deep=True),
}


def _registry_id(value: object) -> str:
    """Return one canonical public era-registry identifier."""
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
    ):
        raise ValueError("era registry ID must be a non-empty trimmed string")
    return value.lower()


def get_era_config(era_name: str) -> EraConfig:
    """Return an isolated registered era configuration.

    Raises
    ------
    ValueError
        If ``era_name`` is not registered.
    """
    normalized_name = _registry_id(era_name)
    try:
        config = _ERA_REGISTRY[normalized_name]
    except KeyError as exc:
        registered = ", ".join(sorted(_ERA_REGISTRY))
        raise ValueError(
            f"Unknown era {era_name!r}; registered eras: {registered}",
        ) from exc
    return config.model_copy(deep=True)


def _registration_model_topology(
    model: BaseModel,
    *,
    label: str,
) -> None:
    """Reject bypass-added or missing fields before canonical validation."""
    declared = set(type(model).model_fields)
    actual = set(model.__dict__)
    extra = getattr(model, "__pydantic_extra__", None) or {}
    unknown = sorted((actual - declared) | set(extra))
    missing = sorted(declared - actual)
    if unknown or missing:
        raise ValueError(
            f"Invalid {label} field topology; unknown={unknown!r}, "
            f"missing={missing!r}",
        )


def _registration_sparse_data(
    overrides: _SparseOverrides,
    *,
    expected_type: type[_SparseOverrides],
    label: str,
) -> dict[str, object]:
    """Preserve authored-null fields while rebuilding one sparse input."""
    if type(overrides) is not expected_type:
        raise TypeError(f"{label} must be an {expected_type.__name__}")
    _registration_model_topology(overrides, label=label)
    return {
        field_name: getattr(overrides, field_name)
        for field_name in expected_type.model_fields
        if (
            field_name in overrides.model_fields_set
            or getattr(overrides, field_name) is not None
        )
    }


def register_era_config(era_name: str, config: EraConfig) -> None:
    """Validate and register an isolated custom era configuration."""
    normalized_name = _registry_id(era_name)
    if type(config) is not EraConfig:
        raise TypeError("config must be an EraConfig")
    _registration_model_topology(config, label="EraConfig")
    validated = EraConfig.model_validate(
        {
            "era": config.era,
            "disabled_modules": config.disabled_modules,
            "available_sensor_types": config.available_sensor_types,
            "physics_overrides": _registration_sparse_data(
                config.physics_overrides,
                expected_type=EraPhysicsOverrides,
                label="physics_overrides",
            ),
            "tick_resolution_overrides": _registration_sparse_data(
                config.tick_resolution_overrides,
                expected_type=EraTickResolutionOverrides,
                label="tick_resolution_overrides",
            ),
        },
        strict=True,
        extra="forbid",
    )
    _ERA_REGISTRY[normalized_name] = validated.model_copy(deep=True)
