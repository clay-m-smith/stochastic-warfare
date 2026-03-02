"""Tests for entities/organization/staff.py."""

import pytest

from stochastic_warfare.entities.organization.staff import (
    StaffCapabilities,
    StaffFunction,
    StaffSection,
)


class TestStaffFunction:
    def test_values(self) -> None:
        assert StaffFunction.S1 == 1
        assert StaffFunction.S6 == 6

    def test_count(self) -> None:
        assert len(StaffFunction) == 6


class TestStaffSection:
    def test_creation(self) -> None:
        s = StaffSection(StaffFunction.S3, 0.9, 5)
        assert s.function == StaffFunction.S3
        assert s.effectiveness == 0.9
        assert s.personnel_count == 5

    def test_roundtrip(self) -> None:
        s = StaffSection(StaffFunction.S2, 0.85, 3)
        state = s.get_state()
        r = StaffSection(StaffFunction.S1, 0.0, 0)
        r.set_state(state)
        assert r.function == StaffFunction.S2
        assert r.effectiveness == 0.85
        assert r.personnel_count == 3


class TestStaffCapabilities:
    def _make_caps(self) -> StaffCapabilities:
        return StaffCapabilities([
            StaffSection(StaffFunction.S1, 0.8, 2),
            StaffSection(StaffFunction.S2, 0.9, 3),
            StaffSection(StaffFunction.S3, 1.0, 5),
            StaffSection(StaffFunction.S4, 0.7, 2),
        ])

    def test_get_effectiveness(self) -> None:
        caps = self._make_caps()
        assert caps.get_effectiveness(StaffFunction.S3) == 1.0
        assert caps.get_effectiveness(StaffFunction.S4) == 0.7

    def test_missing_function(self) -> None:
        caps = self._make_caps()
        assert caps.get_effectiveness(StaffFunction.S5) == 0.0

    def test_has_function(self) -> None:
        caps = self._make_caps()
        assert caps.has_function(StaffFunction.S1)
        assert not caps.has_function(StaffFunction.S6)

    def test_degrade(self) -> None:
        caps = self._make_caps()
        caps.degrade(StaffFunction.S3, 0.3)
        assert caps.get_effectiveness(StaffFunction.S3) == pytest.approx(0.7)

    def test_degrade_floor_zero(self) -> None:
        caps = self._make_caps()
        caps.degrade(StaffFunction.S1, 5.0)
        assert caps.get_effectiveness(StaffFunction.S1) == 0.0

    def test_degrade_missing_no_error(self) -> None:
        caps = self._make_caps()
        caps.degrade(StaffFunction.S6, 0.5)  # should not raise

    def test_overall_effectiveness(self) -> None:
        caps = self._make_caps()
        expected = (0.8 + 0.9 + 1.0 + 0.7) / 4
        assert caps.overall_effectiveness == pytest.approx(expected)

    def test_empty_caps(self) -> None:
        caps = StaffCapabilities()
        assert caps.overall_effectiveness == 0.0

    def test_roundtrip(self) -> None:
        original = self._make_caps()
        state = original.get_state()
        restored = StaffCapabilities()
        restored.set_state(state)
        assert restored.get_effectiveness(StaffFunction.S3) == 1.0
        assert restored.get_effectiveness(StaffFunction.S4) == 0.7
        assert restored.has_function(StaffFunction.S1)
