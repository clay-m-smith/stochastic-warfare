"""Typed construction of runtime morale configuration."""

from __future__ import annotations

from typing import Protocol

from stochastic_warfare.morale.state import MoraleConfig


class MoraleCalibrationValues(Protocol):
    """Read-only calibration values consumed by the morale subsystem."""

    @property
    def base_degrade_rate(self) -> float: ...

    @property
    def base_recover_rate(self) -> float: ...

    @property
    def casualty_weight(self) -> float: ...

    @property
    def suppression_weight(self) -> float: ...

    @property
    def leadership_weight(self) -> float: ...

    @property
    def cohesion_weight(self) -> float: ...

    @property
    def force_ratio_weight(self) -> float: ...

    @property
    def transition_cooldown_s(self) -> float: ...


_RUNTIME_MORALE_FIELDS = (
    "base_degrade_rate",
    "base_recover_rate",
    "casualty_weight",
    "suppression_weight",
    "leadership_weight",
    "cohesion_weight",
    "force_ratio_weight",
    "transition_cooldown_s",
)


def build_morale_config(
    calibration: MoraleCalibrationValues | None,
) -> MoraleConfig | None:
    """Return only non-default runtime morale calibration values."""
    if calibration is None:
        return None

    values = {
        field_name: getattr(calibration, field_name)
        for field_name in _RUNTIME_MORALE_FIELDS
        if (getattr(calibration, field_name) != MoraleConfig.model_fields[field_name].default)
    }
    return MoraleConfig(**values) if values else None
