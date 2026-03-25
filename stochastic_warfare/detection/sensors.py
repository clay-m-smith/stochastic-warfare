"""Sensor definitions, loading, and runtime sensor management.

Each sensor type is defined in a YAML file under ``data/sensors/``.
:class:`SensorInstance` wraps a definition with runtime state (operational
status from equipment condition).  :class:`SensorSuite` groups all sensors
on a single unit.
"""

from __future__ import annotations

import enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.detection.signatures import SignatureDomain
from stochastic_warfare.entities.equipment import EquipmentItem

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SensorType(enum.IntEnum):
    """Sensor technology classification."""

    VISUAL = 0
    THERMAL = 1
    RADAR = 2
    PASSIVE_ACOUSTIC = 3
    ACTIVE_SONAR = 4
    PASSIVE_SONAR = 5
    ESM = 6
    SEISMIC = 7
    MAD = 8
    NVG = 9


# Mapping from sensor type to the signature domain it reads.
_SENSOR_TO_SIGNATURE: dict[SensorType, SignatureDomain] = {
    SensorType.VISUAL: SignatureDomain.VISUAL,
    SensorType.NVG: SignatureDomain.VISUAL,
    SensorType.THERMAL: SignatureDomain.THERMAL,
    SensorType.RADAR: SignatureDomain.RADAR,
    SensorType.PASSIVE_ACOUSTIC: SignatureDomain.ACOUSTIC,
    SensorType.ACTIVE_SONAR: SignatureDomain.ACOUSTIC,
    SensorType.PASSIVE_SONAR: SignatureDomain.ACOUSTIC,
    SensorType.ESM: SignatureDomain.ELECTROMAGNETIC,
    SensorType.MAD: SignatureDomain.ELECTROMAGNETIC,
}


# ---------------------------------------------------------------------------
# Pydantic definition
# ---------------------------------------------------------------------------


class SensorDefinition(BaseModel):
    """Pydantic model validated from YAML sensor files."""

    sensor_id: str
    sensor_type: str  # "VISUAL", "THERMAL", "RADAR", etc.
    display_name: str
    max_range_m: float
    detection_threshold: float  # minimum SNR for detection (dB)
    false_alarm_rate: float = 1e-6
    scan_time_s: float = 1.0
    scan_interval_ticks: int = Field(default=1, ge=1)

    # Radar-specific
    frequency_mhz: float | None = None
    peak_power_w: float | None = None
    antenna_gain_dbi: float | None = None
    antenna_height_m: float = 2.0

    # Sonar-specific
    source_level_db: float | None = None  # active sonar only
    directivity_index_db: float = 0.0

    # General
    min_range_m: float = 0.0
    fov_deg: float = 360.0
    boresight_offset_deg: float = 0.0  # sensor boresight offset from unit heading
    requires_los: bool = True
    detects_domain: list[str] = []

    def parsed_sensor_type(self) -> SensorType:
        """Return the enum value for this definition's sensor_type string."""
        return SensorType[self.sensor_type.upper()]


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


class SensorLoader:
    """Load and cache :class:`SensorDefinition` instances from YAML files."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._definitions: dict[str, SensorDefinition] = {}

    def load_definition(self, path: Path) -> SensorDefinition:
        """Load and validate a single YAML sensor definition."""
        import yaml

        with open(path) as f:
            raw = yaml.safe_load(f)
        defn = SensorDefinition.model_validate(raw)
        self._definitions[defn.sensor_id] = defn
        return defn

    def load_all(self) -> None:
        """Recursively load all ``*.yaml`` files under *data_dir*."""
        for yaml_path in sorted(self._data_dir.rglob("*.yaml")):
            self.load_definition(yaml_path)
        logger.info("Loaded %d sensor definitions", len(self._definitions))

    def get_definition(self, sensor_id: str) -> SensorDefinition:
        """Return a loaded definition.  Raises ``KeyError`` if not found."""
        return self._definitions[sensor_id]

    def available_sensors(self) -> list[str]:
        """Return sorted list of loaded sensor identifiers."""
        return sorted(self._definitions.keys())


# ---------------------------------------------------------------------------
# Runtime sensor instance
# ---------------------------------------------------------------------------


class SensorInstance:
    """Runtime sensor on a specific unit — wraps definition + operational state.

    Parameters
    ----------
    definition:
        The sensor's YAML-loaded specification.
    equipment:
        Optional link to an :class:`EquipmentItem` for condition tracking.
    """

    def __init__(
        self,
        definition: SensorDefinition,
        equipment: EquipmentItem | None = None,
    ) -> None:
        self.definition = definition
        self.equipment = equipment
        self._sensor_type = definition.parsed_sensor_type()

    @property
    def sensor_id(self) -> str:
        return self.definition.sensor_id

    @property
    def sensor_type(self) -> SensorType:
        return self._sensor_type

    @property
    def operational(self) -> bool:
        """True if the sensor is functional (equipment condition > 0)."""
        if self.equipment is None:
            return True
        return self.equipment.operational and self.equipment.condition > 0.0

    @property
    def effective_range(self) -> float:
        """Max detection range degraded by equipment condition."""
        if self.equipment is None:
            return self.definition.max_range_m
        return self.definition.max_range_m * self.equipment.condition

    def get_state(self) -> dict[str, Any]:
        return {
            "sensor_id": self.definition.sensor_id,
            "equipment_condition": (
                self.equipment.condition if self.equipment else 1.0
            ),
            "equipment_operational": (
                self.equipment.operational if self.equipment else True
            ),
        }

    def set_state(self, state: dict[str, Any]) -> None:
        if self.equipment is not None:
            self.equipment.condition = state["equipment_condition"]
            self.equipment.operational = state["equipment_operational"]


# ---------------------------------------------------------------------------
# Sensor suite — all sensors on a unit
# ---------------------------------------------------------------------------


class SensorSuite:
    """Collection of all sensors on a single unit."""

    def __init__(self, sensors: list[SensorInstance] | None = None) -> None:
        self._sensors: list[SensorInstance] = sensors or []

    @property
    def sensors(self) -> list[SensorInstance]:
        return list(self._sensors)

    def add_sensor(self, sensor: SensorInstance) -> None:
        self._sensors.append(sensor)

    def sensors_of_type(self, sensor_type: SensorType) -> list[SensorInstance]:
        """Return all sensors of the given type."""
        return [s for s in self._sensors if s.sensor_type == sensor_type]

    def operational_sensors(self) -> list[SensorInstance]:
        """Return all currently operational sensors."""
        return [s for s in self._sensors if s.operational]

    def best_sensor_for(self, sig_domain: SignatureDomain) -> SensorInstance | None:
        """Return the operational sensor with the longest range for *sig_domain*.

        Returns ``None`` if no operational sensor can detect in that domain.
        """
        candidates = [
            s for s in self._sensors
            if s.operational and _SENSOR_TO_SIGNATURE.get(s.sensor_type) == sig_domain
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda s: s.effective_range)

    def get_state(self) -> dict[str, Any]:
        return {
            "sensors": [s.get_state() for s in self._sensors],
        }

    def set_state(self, state: dict[str, Any]) -> None:
        for i, ss in enumerate(state["sensors"]):
            if i < len(self._sensors):
                self._sensors[i].set_state(ss)
