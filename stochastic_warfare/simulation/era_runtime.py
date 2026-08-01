"""Resolved production runtime contract for typed era overrides."""

from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, field_validator

from stochastic_warfare.core.clock import (
    clock_execution_horizon_end,
    normalize_clock_duration_seconds,
    validate_clock_execution_horizon,
)
from stochastic_warfare.core.era import (
    Era,
    EraConfig,
    PositiveFiniteFloat,
)
from stochastic_warfare.logistics.maintenance import MaintenanceConfig
from stochastic_warfare.logistics.medical import MedicalConfig


class EraRuntimeSource(BaseModel):
    """Immutable scenario-side inputs used to resolve an era contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    selected_registry_id: str
    strategic_s: PositiveFiniteFloat
    operational_s: PositiveFiniteFloat
    tactical_s: PositiveFiniteFloat
    tick_duration_seconds: PositiveFiniteFloat | None = None

    @field_validator(
        "strategic_s",
        "operational_s",
        "tactical_s",
        "tick_duration_seconds",
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

    @field_validator("selected_registry_id", mode="before")
    @classmethod
    def _valid_registry_id(cls, value: object) -> str:
        return _validate_registry_id(value)

    @field_validator(
        "strategic_s",
        "operational_s",
        "tactical_s",
        "tick_duration_seconds",
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


class EraExecutionHorizonSource(BaseModel):
    """Immutable scenario inputs that bound executable calendar time."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    date: str
    duration_hours: PositiveFiniteFloat

    @field_validator("date", mode="before")
    @classmethod
    def _strict_date(cls, value: object) -> str:
        if (
            type(value) is not str
            or not value
            or value != value.strip()
        ):
            raise ValueError("date must be a non-empty trimmed strict string")
        return value

    @field_validator("duration_hours", mode="before")
    @classmethod
    def _strict_duration(cls, value: object) -> float:
        if type(value) is not float:
            raise ValueError("duration_hours must be a strict float")
        return value


def _validate_registry_id(value: object) -> str:
    """Validate the exact normalized registry identity."""
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or value != value.lower()
    ):
        raise ValueError(
            "selected_registry_id must be a non-empty trimmed lowercase "
            "string",
        )
    return value


class EraRuntimeContract(BaseModel):
    """Immutable effective values consumed by one production runtime."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    selected_registry_id: str
    era: Era
    strategic_s: PositiveFiniteFloat
    operational_s: PositiveFiniteFloat
    tactical_s: PositiveFiniteFloat
    treatment_hours_minor: PositiveFiniteFloat
    treatment_hours_serious: PositiveFiniteFloat
    treatment_hours_critical: PositiveFiniteFloat
    repair_time_hours: PositiveFiniteFloat

    @field_validator(
        "strategic_s",
        "operational_s",
        "tactical_s",
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
        if type(value) is not float:
            raise ValueError(
                f"{getattr(info, 'field_name')} must be a strict float",
            )
        return value

    @field_validator("selected_registry_id", mode="before")
    @classmethod
    def _valid_registry_id(cls, value: object) -> str:
        return _validate_registry_id(value)

    @field_validator("strategic_s", "operational_s", "tactical_s")
    @classmethod
    def _clock_representable(
        cls,
        value: float,
        info: object,
    ) -> float:
        return normalize_clock_duration_seconds(
            value,
            field_name=getattr(info, "field_name"),
        )

    @classmethod
    def resolve(
        cls,
        *,
        selected_registry_id: str,
        era_config: EraConfig,
        strategic_s: float,
        operational_s: float,
        tactical_s: float,
        tick_duration_seconds: float | None,
    ) -> Self:
        """Materialize destination defaults and apply sparse era overlays."""
        if not isinstance(era_config, EraConfig):
            raise TypeError("era_config must be an effective EraConfig")
        source = EraRuntimeSource(
            selected_registry_id=selected_registry_id,
            strategic_s=strategic_s,
            operational_s=operational_s,
            tactical_s=tactical_s,
            tick_duration_seconds=tick_duration_seconds,
        )
        if (
            source.tick_duration_seconds is not None
            and era_config.has_tick_resolution_overrides
        ):
            raise ValueError(
                "tick_duration_seconds cannot be combined with era "
                "tick_resolution_overrides",
            )

        if tick_duration_seconds is None:
            effective_ticks = {
                "strategic_s": source.strategic_s,
                "operational_s": source.operational_s,
                "tactical_s": source.tactical_s,
            }
            for field_name in effective_ticks:
                override = getattr(
                    era_config.tick_resolution_overrides,
                    field_name,
                )
                if override is not None:
                    effective_ticks[field_name] = override
        else:
            effective_ticks = {
                "strategic_s": source.tick_duration_seconds,
                "operational_s": source.tick_duration_seconds,
                "tactical_s": source.tick_duration_seconds,
            }

        medical_defaults = MedicalConfig()
        maintenance_defaults = MaintenanceConfig()
        effective_physics = {
            "treatment_hours_minor": medical_defaults.treatment_hours_minor,
            "treatment_hours_serious": (
                medical_defaults.treatment_hours_serious
            ),
            "treatment_hours_critical": (
                medical_defaults.treatment_hours_critical
            ),
            "repair_time_hours": maintenance_defaults.repair_time_hours,
        }
        for field_name in effective_physics:
            override = getattr(era_config.physics_overrides, field_name)
            if override is not None:
                effective_physics[field_name] = override

        return cls(
            selected_registry_id=source.selected_registry_id,
            era=era_config.era,
            **effective_ticks,
            **effective_physics,
        )

    def medical_config(self) -> MedicalConfig:
        """Build the exact medical configuration owned by this contract."""
        return MedicalConfig(
            treatment_hours_minor=self.treatment_hours_minor,
            treatment_hours_serious=self.treatment_hours_serious,
            treatment_hours_critical=self.treatment_hours_critical,
        )

    def maintenance_config(self) -> MaintenanceConfig:
        """Build the exact maintenance configuration owned by this contract."""
        return MaintenanceConfig(repair_time_hours=self.repair_time_hours)

    def validate_execution_horizon(
        self,
        *,
        start: datetime,
        duration_hours: float,
    ) -> None:
        """Validate one full declared run plus its final bound interval."""
        validate_clock_execution_horizon(
            start=start,
            scenario_duration_seconds=duration_hours * 3600.0,
            maximum_tick_seconds=max(
                self.strategic_s,
                self.operational_s,
                self.tactical_s,
            ),
        )

    def execution_horizon_end(
        self,
        *,
        start: datetime,
        duration_hours: float,
    ) -> datetime:
        """Return the final calendar endpoint this contract can execute."""
        return clock_execution_horizon_end(
            start=start,
            scenario_duration_seconds=duration_hours * 3600.0,
            maximum_tick_seconds=max(
                self.strategic_s,
                self.operational_s,
                self.tactical_s,
            ),
        )
