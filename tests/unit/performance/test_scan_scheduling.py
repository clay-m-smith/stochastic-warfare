"""Catalog validation for sensor-native scan cadence.

Runtime scheduling is owned by the typed FOW cadence/receipt transaction and
is covered in ``tests/unit/detection/test_fow_receipts.py``.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from stochastic_warfare.detection.sensors import SensorDefinition


def _definition(**overrides: object) -> SensorDefinition:
    values: dict[str, object] = {
        "sensor_id": "cadence-sensor",
        "sensor_type": "VISUAL",
        "display_name": "Cadence sensor",
        "max_range_m": 1_000.0,
        "detection_threshold": 1.0,
    }
    values.update(overrides)
    return SensorDefinition.model_validate(values)


def test_scan_interval_defaults_to_one() -> None:
    assert _definition().scan_interval_ticks == 1


def test_scan_interval_preserves_explicit_positive_value() -> None:
    assert _definition(scan_interval_ticks=5).scan_interval_ticks == 5


@pytest.mark.parametrize("invalid", (0, -1))
def test_scan_interval_rejects_nonpositive_values(invalid: int) -> None:
    with pytest.raises(ValidationError):
        _definition(scan_interval_ticks=invalid)
