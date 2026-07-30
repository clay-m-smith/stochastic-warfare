"""Exact typed runtime-input failures translated to HTTP 422 by API routes."""

from __future__ import annotations

from stochastic_warfare.entities.loader import MissingUnitDefinitionError
from stochastic_warfare.simulation.loadouts import EquipmentMappingError
from stochastic_warfare.simulation.runtime import AnalysisInputError
from stochastic_warfare.simulation.scenario import ScenarioReferenceError
from stochastic_warfare.simulation.time_on_target import (
    TimeOnTargetResolutionError,
)


RUNTIME_INPUT_EXCEPTIONS: tuple[type[Exception], ...] = (
    AnalysisInputError,
    EquipmentMappingError,
    MissingUnitDefinitionError,
    ScenarioReferenceError,
    TimeOnTargetResolutionError,
)
"""Domain failures that identify invalid user-authored runtime input."""
