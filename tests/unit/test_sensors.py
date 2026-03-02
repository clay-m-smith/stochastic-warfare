"""Tests for detection/sensors.py — sensor definitions, loader, runtime instances."""

from __future__ import annotations

from pathlib import Path

import pytest

from stochastic_warfare.detection.sensors import (
    SensorDefinition,
    SensorInstance,
    SensorLoader,
    SensorSuite,
    SensorType,
)
from stochastic_warfare.detection.signatures import SignatureDomain
from stochastic_warfare.entities.equipment import EquipmentCategory, EquipmentItem

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "sensors"


# ── SensorType enum ───────────────────────────────────────────────────


class TestSensorType:
    def test_values(self) -> None:
        assert SensorType.VISUAL == 0
        assert SensorType.THERMAL == 1
        assert SensorType.RADAR == 2
        assert SensorType.PASSIVE_ACOUSTIC == 3
        assert SensorType.ACTIVE_SONAR == 4
        assert SensorType.PASSIVE_SONAR == 5
        assert SensorType.ESM == 6
        assert SensorType.MAD == 8
        assert SensorType.NVG == 9

    def test_count(self) -> None:
        assert len(SensorType) == 10


# ── SensorDefinition ─────────────────────────────────────────────────


class TestSensorDefinition:
    def test_minimal(self) -> None:
        d = SensorDefinition(
            sensor_id="test",
            sensor_type="VISUAL",
            display_name="Test Sensor",
            max_range_m=1000.0,
            detection_threshold=5.0,
        )
        assert d.sensor_id == "test"
        assert d.parsed_sensor_type() == SensorType.VISUAL

    def test_radar_fields(self) -> None:
        d = SensorDefinition(
            sensor_id="radar",
            sensor_type="RADAR",
            display_name="Test Radar",
            max_range_m=50000.0,
            detection_threshold=10.0,
            frequency_mhz=9400.0,
            peak_power_w=20000.0,
            antenna_gain_dbi=30.0,
        )
        assert d.frequency_mhz == 9400.0
        assert d.peak_power_w == 20000.0

    def test_sonar_fields(self) -> None:
        d = SensorDefinition(
            sensor_id="sonar",
            sensor_type="ACTIVE_SONAR",
            display_name="Test Sonar",
            max_range_m=50000.0,
            detection_threshold=6.0,
            source_level_db=235.0,
            directivity_index_db=20.0,
        )
        assert d.source_level_db == 235.0
        assert d.directivity_index_db == 20.0

    def test_defaults(self) -> None:
        d = SensorDefinition(
            sensor_id="test",
            sensor_type="VISUAL",
            display_name="Test",
            max_range_m=1000.0,
            detection_threshold=5.0,
        )
        assert d.false_alarm_rate == 1e-6
        assert d.scan_time_s == 1.0
        assert d.fov_deg == 360.0
        assert d.requires_los is True
        assert d.min_range_m == 0.0


# ── SensorLoader ──────────────────────────────────────────────────────


class TestSensorLoader:
    def test_load_single(self) -> None:
        loader = SensorLoader(DATA_DIR)
        defn = loader.load_definition(DATA_DIR / "mk1_eyeball.yaml")
        assert defn.sensor_id == "mk1_eyeball"
        assert defn.sensor_type == "VISUAL"

    def test_load_all(self) -> None:
        loader = SensorLoader(DATA_DIR)
        loader.load_all()
        sensors = loader.available_sensors()
        assert len(sensors) == 8
        assert "mk1_eyeball" in sensors
        assert "air_search_radar" in sensors
        assert "passive_sonar" in sensors

    def test_get_definition(self) -> None:
        loader = SensorLoader(DATA_DIR)
        loader.load_all()
        d = loader.get_definition("air_search_radar")
        assert d.max_range_m == 400000.0
        assert d.frequency_mhz == 3300.0

    def test_get_not_found(self) -> None:
        loader = SensorLoader(DATA_DIR)
        with pytest.raises(KeyError):
            loader.get_definition("nonexistent")

    def test_available_sorted(self) -> None:
        loader = SensorLoader(DATA_DIR)
        loader.load_all()
        sensors = loader.available_sensors()
        assert sensors == sorted(sensors)

    def test_all_valid(self) -> None:
        loader = SensorLoader(DATA_DIR)
        loader.load_all()
        for sid in loader.available_sensors():
            d = loader.get_definition(sid)
            assert d.sensor_id == sid
            assert d.max_range_m > 0

    def test_esm_no_los(self) -> None:
        loader = SensorLoader(DATA_DIR)
        loader.load_all()
        d = loader.get_definition("esm_suite")
        assert d.requires_los is False

    def test_sonar_no_los(self) -> None:
        loader = SensorLoader(DATA_DIR)
        loader.load_all()
        d = loader.get_definition("passive_sonar")
        assert d.requires_los is False

    def test_visual_requires_los(self) -> None:
        loader = SensorLoader(DATA_DIR)
        loader.load_all()
        d = loader.get_definition("mk1_eyeball")
        assert d.requires_los is True


# ── SensorInstance ────────────────────────────────────────────────────


def _make_defn(**kwargs) -> SensorDefinition:
    defaults = dict(
        sensor_id="test",
        sensor_type="VISUAL",
        display_name="Test",
        max_range_m=5000.0,
        detection_threshold=3.0,
    )
    defaults.update(kwargs)
    return SensorDefinition(**defaults)


def _make_equip(condition: float = 1.0, operational: bool = True) -> EquipmentItem:
    return EquipmentItem(
        equipment_id="eq-001",
        name="Test Sensor",
        category=EquipmentCategory.SENSOR,
        condition=condition,
        operational=operational,
    )


class TestSensorInstance:
    def test_operational_no_equipment(self) -> None:
        si = SensorInstance(_make_defn())
        assert si.operational is True

    def test_operational_good_equipment(self) -> None:
        si = SensorInstance(_make_defn(), _make_equip(condition=0.9))
        assert si.operational is True

    def test_not_operational_broken(self) -> None:
        si = SensorInstance(_make_defn(), _make_equip(operational=False))
        assert si.operational is False

    def test_not_operational_zero_condition(self) -> None:
        si = SensorInstance(_make_defn(), _make_equip(condition=0.0))
        assert si.operational is False

    def test_effective_range_full(self) -> None:
        si = SensorInstance(_make_defn(max_range_m=10000.0))
        assert si.effective_range == pytest.approx(10000.0)

    def test_effective_range_degraded(self) -> None:
        si = SensorInstance(_make_defn(max_range_m=10000.0), _make_equip(condition=0.5))
        assert si.effective_range == pytest.approx(5000.0)

    def test_sensor_type_property(self) -> None:
        si = SensorInstance(_make_defn(sensor_type="RADAR"))
        assert si.sensor_type == SensorType.RADAR

    def test_sensor_id_property(self) -> None:
        si = SensorInstance(_make_defn(sensor_id="my_sensor"))
        assert si.sensor_id == "my_sensor"

    def test_state_roundtrip(self) -> None:
        equip = _make_equip(condition=0.75)
        si = SensorInstance(_make_defn(), equip)
        state = si.get_state()
        assert state["equipment_condition"] == 0.75

        equip2 = _make_equip(condition=1.0)
        si2 = SensorInstance(_make_defn(), equip2)
        si2.set_state(state)
        assert si2.equipment.condition == 0.75

    def test_state_no_equipment(self) -> None:
        si = SensorInstance(_make_defn())
        state = si.get_state()
        assert state["equipment_condition"] == 1.0
        assert state["equipment_operational"] is True


# ── SensorSuite ───────────────────────────────────────────────────────


class TestSensorSuite:
    def _make_suite(self) -> SensorSuite:
        s1 = SensorInstance(_make_defn(sensor_id="eye", sensor_type="VISUAL", max_range_m=5000.0))
        s2 = SensorInstance(_make_defn(sensor_id="therm", sensor_type="THERMAL", max_range_m=4000.0))
        s3 = SensorInstance(_make_defn(sensor_id="radar", sensor_type="RADAR", max_range_m=60000.0))
        s4 = SensorInstance(
            _make_defn(sensor_id="radar2", sensor_type="RADAR", max_range_m=30000.0),
            _make_equip(operational=False),
        )
        return SensorSuite([s1, s2, s3, s4])

    def test_sensors_list(self) -> None:
        suite = self._make_suite()
        assert len(suite.sensors) == 4

    def test_sensors_of_type(self) -> None:
        suite = self._make_suite()
        radars = suite.sensors_of_type(SensorType.RADAR)
        assert len(radars) == 2

    def test_operational_sensors(self) -> None:
        suite = self._make_suite()
        ops = suite.operational_sensors()
        assert len(ops) == 3  # radar2 is broken

    def test_best_sensor_for_visual(self) -> None:
        suite = self._make_suite()
        best = suite.best_sensor_for(SignatureDomain.VISUAL)
        assert best is not None
        assert best.sensor_id == "eye"

    def test_best_sensor_for_radar(self) -> None:
        suite = self._make_suite()
        best = suite.best_sensor_for(SignatureDomain.RADAR)
        assert best is not None
        assert best.sensor_id == "radar"  # radar2 is broken, so radar wins

    def test_best_sensor_for_acoustic_none(self) -> None:
        suite = self._make_suite()
        assert suite.best_sensor_for(SignatureDomain.ACOUSTIC) is None

    def test_add_sensor(self) -> None:
        suite = SensorSuite()
        assert len(suite.sensors) == 0
        suite.add_sensor(SensorInstance(_make_defn()))
        assert len(suite.sensors) == 1

    def test_state_roundtrip(self) -> None:
        equip = _make_equip(condition=0.8)
        s1 = SensorInstance(_make_defn(sensor_id="a"), equip)
        suite = SensorSuite([s1])
        state = suite.get_state()

        equip2 = _make_equip(condition=1.0)
        s2 = SensorInstance(_make_defn(sensor_id="a"), equip2)
        suite2 = SensorSuite([s2])
        suite2.set_state(state)
        assert suite2.sensors[0].equipment.condition == 0.8
