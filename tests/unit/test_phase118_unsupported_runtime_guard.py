"""Direct runtime guard coverage for unsupported Phase 118 controls."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.simulation.battle import BattleManager
from stochastic_warfare.simulation.calibration import CalibrationSchema
from stochastic_warfare.simulation.performance_flags import (
    EffectivePerformanceFlags,
    LOD_RUNTIME_COMPATIBILITY_DEFAULTS,
    UnsupportedPerformanceConfigurationError,
)


@pytest.mark.parametrize(
    "flag",
    ("enable_scan_scheduling", "enable_lod"),
)
def test_direct_battle_manager_rejects_unsupported_effective_flag(
    flag: str,
) -> None:
    """A hand-built manager cannot bypass the live-runtime support guard."""
    state = EffectivePerformanceFlags.all_disabled().to_state()
    state["enable_detection_culling"] = True
    state[flag] = True
    historical_flags = EffectivePerformanceFlags.from_state(state)

    assert getattr(historical_flags, flag) is True
    with pytest.raises(
        UnsupportedPerformanceConfigurationError,
        match=flag,
    ):
        BattleManager(
            EventBus(),
            effective_performance_flags=historical_flags,
        )


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    (
        ("enable_scan_scheduling", True),
        ("enable_lod", True),
        *tuple(
            (field_name, default_value + 1)
            for field_name, default_value in LOD_RUNTIME_COMPATIBILITY_DEFAULTS.items()
        ),
    ),
)
def test_direct_battle_manager_rejects_flat_runtime_drift(
    field_name: str,
    invalid_value: bool | int,
) -> None:
    """Direct battle entry cannot bypass typed/flat/receipt cross-binding."""
    calibration = CalibrationSchema()
    cal_flat = calibration.to_flat_dict(["blue", "red"])
    manager = BattleManager(EventBus())
    context = SimpleNamespace(
        config=SimpleNamespace(calibration_overrides=calibration),
        calibration=calibration,
        cal_flat=cal_flat,
    )
    cal_flat[field_name] = invalid_value

    with pytest.raises(
        UnsupportedPerformanceConfigurationError,
        match=field_name,
    ):
        manager.prepare_tactical_interval(context, (), 5.0)


def test_direct_battle_manager_rejects_authored_config_drift() -> None:
    """Authored configuration cannot diverge from effective runtime owners."""
    calibration = CalibrationSchema()
    manager = BattleManager(EventBus())
    context = SimpleNamespace(
        config=SimpleNamespace(
            calibration_overrides=calibration.model_copy(
                update={"enable_lod": True},
            ),
        ),
        calibration=calibration,
        cal_flat=calibration.to_flat_dict(["blue", "red"]),
    )

    with pytest.raises(
        UnsupportedPerformanceConfigurationError,
        match="enable_lod",
    ):
        manager.prepare_tactical_interval(context, (), 5.0)
