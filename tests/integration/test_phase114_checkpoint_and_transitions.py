"""Phase 114 interval binding and era-contract checkpoint integrity."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable

import pytest

import stochastic_warfare.core.era as era_module
from stochastic_warfare.core.era import EraConfig, register_era_config
from stochastic_warfare.core.types import Position
from stochastic_warfare.logistics.maintenance import MaintenanceStatus
from stochastic_warfare.logistics.events import (
    MaintenanceCompletedEvent,
    MaintenanceStartedEvent,
)
from stochastic_warfare.logistics.medical import (
    MedicalFacility,
    MedicalFacilityType,
)
from stochastic_warfare.simulation.movement_diagnostics import MovementStage
from stochastic_warfare.simulation.campaign import CampaignConfig
from stochastic_warfare.simulation.engine import (
    EngineConfig,
    SimulationEngine,
    TickResolution,
)
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    SimulationRuntimeFactory,
)
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    ScenarioLoader,
    SimulationContext,
)
from tests.conftest import make_versionless_legacy_morale_checkpoint


_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _ROOT / "data"
_SCENARIO_PATH = _DATA_DIR / "scenarios/test_campaign/scenario.yaml"
_TRANSITION_ERA = "phase114_transition_era"
_STATE_ERA = "phase114_state_era"
_TICK_SECONDS = {
    TickResolution.STRATEGIC: 101.0,
    TickResolution.OPERATIONAL: 17.0,
    TickResolution.TACTICAL: 3.0,
}
_CONTRACT_KEYS = (
    "selected_registry_id",
    "era",
    "strategic_s",
    "operational_s",
    "tactical_s",
    "treatment_hours_minor",
    "treatment_hours_serious",
    "treatment_hours_critical",
    "repair_time_hours",
)


@pytest.fixture(autouse=True)
def _isolated_era_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep synthetic Phase 114 declarations local to each test."""
    monkeypatch.setattr(
        era_module,
        "_ERA_REGISTRY",
        copy.deepcopy(era_module._ERA_REGISTRY),
    )


def _scenario_config(
    *,
    era: str = "modern",
    separation_m: float = 50_000.0,
    duration_hours: float = 10_000.0,
) -> CampaignScenarioConfig:
    """Return a manual, stationary, production-loadable two-unit scenario."""
    return CampaignScenarioConfig.model_validate(
        {
            "name": "Phase 114 interval and checkpoint acceptance",
            "date": "2024-06-15T12:00:00Z",
            "duration_hours": duration_hours,
            "era": era,
            "tick_resolution": {
                "strategic_s": 3600.0,
                "operational_s": 300.0,
                "tactical_s": 5.0,
            },
            "terrain": {
                "width_m": 70_000.0,
                "height_m": 10_000.0,
                "cell_size_m": 100.0,
                "terrain_type": "flat_desert",
            },
            "deployment": {"mode": "manual"},
            "sides": [
                {
                    "side": "blue",
                    "units": [
                        {
                            "unit_type": "hemtt",
                            "count": 1,
                            "position": [1_000.0, 5_000.0, 0.0],
                        },
                    ],
                    "morale_initial": "STEADY",
                },
                {
                    "side": "red",
                    "units": [
                        {
                            "unit_type": "hemtt",
                            "count": 1,
                            "position": [
                                1_000.0 + separation_m,
                                5_000.0,
                                0.0,
                            ],
                        },
                    ],
                    "morale_initial": "STEADY",
                },
            ],
            "behavior_rules": {
                "blue": {"hold_position": True},
                "red": {"hold_position": True},
            },
            "victory_conditions": [{"type": "time_expired"}],
        },
    )


def _register_transition_era() -> None:
    register_era_config(
        _TRANSITION_ERA,
        EraConfig(
            physics_overrides={"repair_time_hours": 0.001},
            tick_resolution_overrides={
                "strategic_s": _TICK_SECONDS[TickResolution.STRATEGIC],
                "operational_s": _TICK_SECONDS[TickResolution.OPERATIONAL],
                "tactical_s": _TICK_SECONDS[TickResolution.TACTICAL],
            },
        ),
    )


def _engine(
    *,
    era: str = "modern",
    separation_m: float = 50_000.0,
    seed: int = 114,
) -> tuple[SimulationEngine, SimulationContext]:
    context = ScenarioLoader(_DATA_DIR).load(
        _SCENARIO_PATH,
        seed=seed,
        scenario_config=_scenario_config(
            era=era,
            separation_m=separation_m,
        ),
    )
    return (
        SimulationEngine(
            context,
            config=EngineConfig(max_ticks=100),
            campaign_config=CampaignConfig(
                enable_strategic_movement=False,
                enable_maintenance=True,
            ),
            strict_mode=True,
        ),
        context,
    )


def _move_red_to_separation(
    context: SimulationContext,
    separation_m: float,
) -> None:
    blue = context.units_by_side["blue"][0]
    red = context.units_by_side["red"][0]
    red.position = Position(
        blue.position.easting + separation_m,
        blue.position.northing,
        blue.position.altitude,
    )


def _trace_interval_consumers(
    engine: SimulationEngine,
    context: SimulationContext,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, list[Any]]:
    """Wrap real consumers, retaining their production behavior."""
    calls: dict[str, list[Any]] = {
        "campaign": [],
        "maintenance_update": [],
        "maintenance_complete": [],
        "medical": [],
        "battle": [],
    }

    campaign = engine.campaign_manager
    original_campaign = campaign.update_strategic

    def traced_campaign(
        context: Any,
        dt: float,
        *,
        stage: MovementStage,
    ) -> None:
        calls["campaign"].append((dt, stage))
        original_campaign(context, dt, stage=stage)

    monkeypatch.setattr(campaign, "update_strategic", traced_campaign)

    maintenance = context.maintenance_engine
    assert maintenance is not None
    original_maintenance_update = maintenance.update
    original_maintenance_complete = maintenance.complete_repairs

    def traced_maintenance_update(
        dt_hours: float,
        temperature_c: float = 20.0,
        timestamp: Any = None,
    ) -> list[tuple[str, str]]:
        calls["maintenance_update"].append(dt_hours)
        return original_maintenance_update(
            dt_hours,
            temperature_c=temperature_c,
            timestamp=timestamp,
        )

    def traced_maintenance_complete(
        dt_hours: float,
        timestamp: Any = None,
    ) -> list[tuple[str, str]]:
        calls["maintenance_complete"].append(dt_hours)
        return original_maintenance_complete(
            dt_hours,
            timestamp=timestamp,
        )

    monkeypatch.setattr(maintenance, "update", traced_maintenance_update)
    monkeypatch.setattr(
        maintenance,
        "complete_repairs",
        traced_maintenance_complete,
    )

    medical = context.medical_engine
    assert medical is not None
    original_medical = medical.update

    def traced_medical(
        dt_hours: float,
        timestamp: Any = None,
    ) -> list[Any]:
        calls["medical"].append(dt_hours)
        return original_medical(dt_hours, timestamp)

    monkeypatch.setattr(medical, "update", traced_medical)

    battle_manager = engine.battle_manager
    original_battle = battle_manager.execute_tick

    def traced_battle(
        context: Any,
        battle: Any,
        dt: float,
    ) -> None:
        calls["battle"].append(dt)
        original_battle(context, battle, dt)

    monkeypatch.setattr(battle_manager, "execute_tick", traced_battle)
    return calls


@pytest.mark.parametrize(
    ("separation_m", "resolution", "stage"),
    (
        (50_000.0, TickResolution.STRATEGIC, MovementStage.STRATEGIC),
        (20_000.0, TickResolution.OPERATIONAL, MovementStage.OPERATIONAL),
        (8_000.0, TickResolution.TACTICAL, None),
    ),
)
def test_natural_resolution_interval_binds_clock_manager_and_subsystems(
    separation_m: float,
    resolution: TickResolution,
    stage: MovementStage | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _register_transition_era()
    engine, context = _engine(
        era=_TRANSITION_ERA,
        separation_m=separation_m,
    )
    calls = _trace_interval_consumers(engine, context, monkeypatch)
    before = context.clock.elapsed.total_seconds()

    assert engine.resolution is resolution
    assert engine.step() is False

    expected_seconds = _TICK_SECONDS[resolution]
    assert context.clock.elapsed.total_seconds() - before == expected_seconds
    assert calls["maintenance_update"] == [expected_seconds / 3600.0]
    assert calls["maintenance_complete"] == [expected_seconds / 3600.0]
    assert calls["medical"] == [expected_seconds / 3600.0]
    if stage is None:
        assert calls["campaign"] == []
        assert calls["battle"] == [expected_seconds]
    else:
        assert calls["campaign"] == [(expected_seconds, stage)]
        assert calls["battle"] == []


def test_strategic_to_operational_transition_binds_the_next_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _register_transition_era()
    engine, context = _engine(
        era=_TRANSITION_ERA,
        separation_m=50_000.0,
    )
    calls = _trace_interval_consumers(engine, context, monkeypatch)
    maintenance_events: list[
        MaintenanceStartedEvent | MaintenanceCompletedEvent
    ] = []
    context.event_bus.subscribe(
        MaintenanceStartedEvent,
        maintenance_events.append,
    )
    context.event_bus.subscribe(
        MaintenanceCompletedEvent,
        maintenance_events.append,
    )
    # Maintenance registration is not yet automatically derived from runtime
    # loadouts (a tracked Phase 114 follow-up), so use a public registration
    # owner that cannot alter either force's readiness during this cadence test.
    unit_id = "phase114-boundary-maintenance-owner"
    equipment_id = "phase114-boundary-repair"
    context.maintenance_engine.register_equipment(
        unit_id,
        [equipment_id],
        mtbf_hours=0.000_001,
    )

    assert engine.step() is False
    first_endpoint = context.clock.elapsed.total_seconds()
    first_timestamp = context.clock.current_time
    assert first_endpoint == _TICK_SECONDS[TickResolution.STRATEGIC]
    assert engine.resolution is TickResolution.STRATEGIC
    assert (
        context.maintenance_engine.get_record(unit_id, equipment_id).status
        is MaintenanceStatus.MAINTENANCE_DUE
    )
    assert context.maintenance_engine.start_repair(
        unit_id,
        equipment_id,
        spare_parts_available=5.0,
        timestamp=context.clock.current_time,
    )

    _move_red_to_separation(context, 20_000.0)
    assert engine.step() is False

    assert engine.resolution is TickResolution.OPERATIONAL
    assert (
        context.clock.elapsed.total_seconds() - first_endpoint
        == _TICK_SECONDS[TickResolution.OPERATIONAL]
    )
    assert calls["campaign"] == [
        (
            _TICK_SECONDS[TickResolution.STRATEGIC],
            MovementStage.STRATEGIC,
        ),
        (
            _TICK_SECONDS[TickResolution.OPERATIONAL],
            MovementStage.OPERATIONAL,
        ),
    ]
    assert [type(event) for event in maintenance_events] == [
        MaintenanceStartedEvent,
        MaintenanceCompletedEvent,
    ]
    assert maintenance_events[0].timestamp == first_timestamp
    assert maintenance_events[1].timestamp == context.clock.current_time
    assert (
        context.maintenance_engine.get_record(unit_id, equipment_id).status
        is MaintenanceStatus.OPERATIONAL
    )


def test_operational_contact_waits_for_next_tactical_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _register_transition_era()
    engine, context = _engine(
        era=_TRANSITION_ERA,
        separation_m=20_000.0,
    )
    calls = _trace_interval_consumers(engine, context, monkeypatch)
    _move_red_to_separation(context, 8_000.0)

    assert engine.step() is False

    operational_endpoint = context.clock.elapsed.total_seconds()
    assert operational_endpoint == _TICK_SECONDS[TickResolution.OPERATIONAL]
    assert engine.resolution is TickResolution.OPERATIONAL
    assert len(engine.battle_manager.active_battles) == 1
    newly_detected = engine.battle_manager.active_battles[0]
    assert newly_detected.start_time == context.clock.current_time
    assert newly_detected.ticks_executed == 0
    assert calls["battle"] == []
    assert calls["campaign"] == [
        (
            _TICK_SECONDS[TickResolution.OPERATIONAL],
            MovementStage.OPERATIONAL,
        ),
    ]

    assert engine.step() is False

    assert engine.resolution is TickResolution.TACTICAL
    assert (
        context.clock.elapsed.total_seconds() - operational_endpoint
        == _TICK_SECONDS[TickResolution.TACTICAL]
    )
    assert calls["battle"] == [_TICK_SECONDS[TickResolution.TACTICAL]]
    assert newly_detected.ticks_executed == 1


def test_deescalation_binds_operational_then_strategic_intervals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _register_transition_era()
    engine, context = _engine(
        era=_TRANSITION_ERA,
        separation_m=8_000.0,
    )
    calls = _trace_interval_consumers(engine, context, monkeypatch)

    assert engine.step() is False
    tactical_endpoint = context.clock.elapsed.total_seconds()
    assert tactical_endpoint == _TICK_SECONDS[TickResolution.TACTICAL]
    battle = engine.battle_manager.active_battles[0]

    engine.battle_manager.resolve_battle(battle, context.units_by_side)
    _move_red_to_separation(context, 20_000.0)
    assert engine.step() is False
    operational_endpoint = context.clock.elapsed.total_seconds()

    assert engine.resolution is TickResolution.OPERATIONAL
    assert (
        operational_endpoint - tactical_endpoint
        == _TICK_SECONDS[TickResolution.OPERATIONAL]
    )

    _move_red_to_separation(context, 50_000.0)
    assert engine.step() is False

    assert engine.resolution is TickResolution.STRATEGIC
    assert (
        context.clock.elapsed.total_seconds() - operational_endpoint
        == _TICK_SECONDS[TickResolution.STRATEGIC]
    )
    assert calls["campaign"] == [
        (
            _TICK_SECONDS[TickResolution.OPERATIONAL],
            MovementStage.OPERATIONAL,
        ),
        (
            _TICK_SECONDS[TickResolution.STRATEGIC],
            MovementStage.STRATEGIC,
        ),
    ]
    assert calls["battle"] == [_TICK_SECONDS[TickResolution.TACTICAL]]


def test_natural_transition_checkpoints_restore_each_bound_cadence() -> None:
    _register_transition_era()
    source, source_context = _engine(
        era=_TRANSITION_ERA,
        separation_m=50_000.0,
        seed=11_414,
    )

    assert source.step() is False
    _move_red_to_separation(source_context, 20_000.0)
    assert source.step() is False
    assert source.resolution is TickResolution.OPERATIONAL
    operational_checkpoint = source.checkpoint()
    operational_state = json.loads(operational_checkpoint)
    assert operational_state["resolution"] == TickResolution.OPERATIONAL.value
    assert operational_state["context"]["clock"][
        "tick_duration_seconds"
    ] == _TICK_SECONDS[TickResolution.OPERATIONAL]
    assert operational_state["context"]["era_runtime_contract"] == (
        source_context.era_runtime_contract.model_dump(mode="json")
    )

    resumed, resumed_context = _engine(
        era=_TRANSITION_ERA,
        separation_m=50_000.0,
        seed=99_414,
    )
    resumed.restore(operational_checkpoint)
    assert resumed.resolution is TickResolution.OPERATIONAL
    assert resumed_context.clock.tick_duration.total_seconds() == 17.0
    assert resumed.checkpoint() == operational_checkpoint

    _move_red_to_separation(source_context, 8_000.0)
    _move_red_to_separation(resumed_context, 8_000.0)
    assert source.step() is False
    assert resumed.step() is False
    assert source.checkpoint() == resumed.checkpoint()
    assert source.resolution is TickResolution.OPERATIONAL
    assert len(source.battle_manager.active_battles) == 1
    assert source.battle_manager.active_battles[0].ticks_executed == 0

    assert source.step() is False
    assert resumed.step() is False
    tactical_checkpoint = source.checkpoint()
    assert resumed.checkpoint() == tactical_checkpoint
    tactical_state = json.loads(tactical_checkpoint)
    assert tactical_state["resolution"] == TickResolution.TACTICAL.value
    assert tactical_state["context"]["clock"][
        "tick_duration_seconds"
    ] == _TICK_SECONDS[TickResolution.TACTICAL]
    assert tactical_state["context"]["era_runtime_contract"] == (
        source_context.era_runtime_contract.model_dump(mode="json")
    )

    fresh, fresh_context = _engine(
        era=_TRANSITION_ERA,
        separation_m=50_000.0,
        seed=999_414,
    )
    fresh.restore(tactical_checkpoint)
    assert fresh.resolution is TickResolution.TACTICAL
    assert fresh_context.clock.tick_duration.total_seconds() == 3.0
    assert fresh.checkpoint() == tactical_checkpoint

    before = fresh_context.clock.elapsed.total_seconds()
    assert source.step() is False
    assert fresh.step() is False
    assert fresh_context.clock.elapsed.total_seconds() - before == 3.0
    assert fresh.checkpoint() == source.checkpoint()


def _count_mapping_key(value: Any, key: str) -> int:
    if isinstance(value, dict):
        return int(key in value) + sum(
            _count_mapping_key(nested, key)
            for nested in value.values()
        )
    if isinstance(value, list):
        return sum(_count_mapping_key(nested, key) for nested in value)
    return 0


def test_format_116_persists_one_exact_effective_contract() -> None:
    _register_transition_era()
    engine, context = _engine(era=_TRANSITION_ERA)
    state = json.loads(engine.checkpoint().decode("utf-8"))

    assert state["checkpoint_version"] == 116
    contract = state["context"]["era_runtime_contract"]
    assert tuple(contract) == _CONTRACT_KEYS
    assert contract == context.era_runtime_contract.model_dump(mode="json")
    assert _count_mapping_key(state, "era_runtime_contract") == 1


def _without_contract(state: dict[str, Any]) -> None:
    state["context"].pop("era_runtime_contract")


def _with_extra_contract_key(state: dict[str, Any]) -> None:
    state["context"]["era_runtime_contract"]["invented"] = 1.0


def _with_malformed_contract(state: dict[str, Any]) -> None:
    state["context"]["era_runtime_contract"]["tactical_s"] = True


def _with_mismatched_contract(state: dict[str, Any]) -> None:
    contract = state["context"]["era_runtime_contract"]
    contract["repair_time_hours"] += 1.0


def _assert_atomic_rejection(
    engine: SimulationEngine,
    mutation: Callable[[dict[str, Any]], None],
    *,
    match: str,
) -> None:
    before = engine.checkpoint()
    invalid = json.loads(before.decode("utf-8"))
    mutation(invalid)

    with pytest.raises(ValueError, match=match):
        engine.set_state(invalid)

    assert engine.checkpoint() == before


@pytest.mark.parametrize(
    ("mutation", "match"),
    (
        (_without_contract, "era_runtime_contract|era runtime contract"),
        (_with_extra_contract_key, "invented|extra"),
        (_with_malformed_contract, "tactical_s|valid number"),
        (_with_mismatched_contract, "does not match"),
    ),
    ids=("missing", "extra", "malformed", "mismatch"),
)
def test_format_116_rejects_invalid_contract_atomically(
    mutation: Callable[[dict[str, Any]], None],
    match: str,
) -> None:
    _register_transition_era()
    engine, _ = _engine(era=_TRANSITION_ERA)
    _assert_atomic_rejection(engine, mutation, match=match)


def test_format_113_is_explicitly_rejected_atomically() -> None:
    engine, _ = _engine()

    def format_113(state: dict[str, Any]) -> None:
        state["checkpoint_version"] = 113

    _assert_atomic_rejection(
        engine,
        format_113,
        match="Unsupported checkpoint version 113",
    )


@pytest.mark.parametrize(
    "mutation",
    (
        lambda state: state.update(
            {"resolution": TickResolution.OPERATIONAL.value},
        ),
        lambda state: state["context"]["clock"].update(
            {
                "tick_duration_seconds": _TICK_SECONDS[
                    TickResolution.OPERATIONAL
                ],
            },
        ),
    ),
    ids=("resolution", "clock-duration"),
)
def test_resolution_clock_mismatch_is_rejected_atomically(
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    _register_transition_era()
    engine, _ = _engine(era=_TRANSITION_ERA)
    _assert_atomic_rejection(
        engine,
        mutation,
        match="resolution and clock tick duration disagree",
    )


@pytest.mark.parametrize(
    ("mutation", "match"),
    (
        (
            lambda state: state["context"]["clock"].update(
                {
                    "start": state["context"]["clock"]["start"].replace(
                        "+00:00",
                        "",
                    ),
                    "current": state["context"]["clock"]["current"].replace(
                        "+00:00",
                        "",
                    ),
                },
            ),
            "timezone-aware",
        ),
        (
            lambda state: state["context"]["clock"].update(
                {
                    "start": "9999-12-30T00:00:00+00:00",
                    "current": "9999-12-30T00:00:00+00:00",
                },
            ),
            "scenario start",
        ),
        (
            lambda state: state["context"]["clock"].update(
                {
                    "current": "9999-12-30T00:00:00+00:00",
                    "tick_count": 1,
                },
            ),
            "executable scenario horizon",
        ),
    ),
    ids=("naive", "shifted-start", "beyond-horizon"),
)
def test_format_116_rejects_invalid_clock_calendar_atomically(
    mutation: Callable[[dict[str, Any]], None],
    match: str,
) -> None:
    engine, _ = _engine()
    before = engine.checkpoint()
    invalid = json.loads(before.decode("utf-8"))
    mutation(invalid)

    with pytest.raises(ValueError, match=match):
        engine.set_state(invalid)

    assert engine.checkpoint() == before


def test_versionless_baseline_checkpoint_remains_bounded_and_compatible() -> None:
    source, _ = _engine(seed=114)
    legacy = make_versionless_legacy_morale_checkpoint(source.get_state())
    assert "era_runtime_contract" not in legacy["context"]

    resumed, _ = _engine(seed=999_114)
    resumed.set_state(legacy)

    assert resumed.checkpoint() == source.checkpoint()
    assert source.step() is False
    assert resumed.step() is False
    assert resumed.checkpoint() == source.checkpoint()


@pytest.mark.parametrize(
    "contract",
    (None, {}),
    ids=("null", "mapping"),
)
def test_versionless_checkpoint_rejects_format_114_contract_key_atomically(
    contract: object,
) -> None:
    source, _ = _engine(seed=114)
    legacy = make_versionless_legacy_morale_checkpoint(source.get_state())
    legacy["context"]["era_runtime_contract"] = contract

    resumed, _ = _engine(seed=999_114)
    before = resumed.checkpoint()
    with pytest.raises(
        ValueError,
        match="Versionless checkpoints cannot contain format-114",
    ):
        resumed.set_state(legacy)

    assert resumed.checkpoint() == before


def test_versionless_checkpoint_cannot_infer_declared_era_overrides() -> None:
    _register_transition_era()
    engine, _ = _engine(era=_TRANSITION_ERA)
    legacy = make_versionless_legacy_morale_checkpoint(engine.get_state())
    before = engine.checkpoint()

    with pytest.raises(ValueError, match="declared era overrides"):
        engine.set_state(legacy)

    assert engine.checkpoint() == before


def _prepare_stateful_runtime() -> Any:
    register_era_config(
        _STATE_ERA,
        EraConfig(
            physics_overrides={
                "treatment_hours_minor": 300.0,
                "repair_time_hours": 300.0,
            },
            tick_resolution_overrides={"strategic_s": 360_000.0},
        ),
    )
    return SimulationRuntimeFactory().prepare_config(
        _scenario_config(
            era=_STATE_ERA,
            separation_m=50_000.0,
            duration_hours=1_000.0,
        ),
        _DATA_DIR,
        [AnalysisVariant(variant_id="phase114-state")],
        source_label="phase114-stateful-checkpoint",
    )


def _build_stateful_session(prepared: Any, *, seed: int = 11_400) -> Any:
    session = prepared.build(
        "phase114-state",
        seed=seed,
        max_ticks=20,
        record_events=True,
        campaign_config=CampaignConfig(
            enable_strategic_movement=False,
            enable_maintenance=True,
        ),
        strict_mode=True,
    )
    assert session.recorder is not None
    session.recorder.start()
    return session


def _start_active_treatment_and_repair(session: Any) -> str:
    context = session.context
    unit_id = context.units_by_side["blue"][0].entity_id
    facility = MedicalFacility(
        facility_id="phase114-aid-station",
        facility_type=MedicalFacilityType.AID_STATION,
        position=Position(1_000.0, 5_000.0, 0.0),
        capacity=100,
    )
    context.medical_engine.register_facility(facility)
    casualty = context.medical_engine.receive_casualty(
        unit_id=unit_id,
        member_id="phase114-active-casualty",
        severity=1,
        facility_id=facility.facility_id,
    )
    equipment_ids = [f"phase114-equipment-{index:03d}" for index in range(64)]
    context.maintenance_engine.register_equipment(
        unit_id,
        equipment_ids,
        mtbf_hours=0.001,
    )

    assert session.step() is False
    assert casualty.status == "IN_TREATMENT"
    assert casualty.outcome is None

    broken_ids = [
        equipment_id
        for equipment_id in equipment_ids
        if context.maintenance_engine.get_record(
            unit_id,
            equipment_id,
        ).status
        is MaintenanceStatus.AWAITING_PARTS
    ]
    assert broken_ids, "fixed-seed production step must reach a breakdown"
    repaired_equipment_id = broken_ids[0]
    assert context.maintenance_engine.start_repair(
        unit_id,
        repaired_equipment_id,
        spare_parts_available=5.0,
        timestamp=context.clock.current_time,
    )
    assert (
        context.maintenance_engine.get_record(
            unit_id,
            repaired_equipment_id,
        ).status
        is MaintenanceStatus.UNDER_REPAIR
    )
    return repaired_equipment_id


def _advance(session: Any, ticks: int) -> None:
    for _ in range(ticks):
        assert session.step() is False


def test_active_medical_and_maintenance_state_restore_and_continue_exactly() -> None:
    prepared = _prepare_stateful_runtime()
    control = _build_stateful_session(prepared)
    repaired_equipment_id = _start_active_treatment_and_repair(control)
    unit_id = control.context.units_by_side["blue"][0].entity_id
    checkpoint_at_t = control.engine.checkpoint()
    state_at_t = json.loads(checkpoint_at_t.decode("utf-8"))

    assert state_at_t["checkpoint_version"] == 116
    assert state_at_t["context"]["era_runtime_contract"] == {
        "selected_registry_id": _STATE_ERA,
        "era": "modern",
        "strategic_s": 360_000.0,
        "operational_s": 300.0,
        "tactical_s": 5.0,
        "treatment_hours_minor": 300.0,
        "treatment_hours_serious": 8.0,
        "treatment_hours_critical": 24.0,
        "repair_time_hours": 300.0,
    }

    _advance(control, 3)
    uninterrupted = control.engine.checkpoint()
    uninterrupted_state = json.loads(uninterrupted.decode("utf-8"))
    event_types = {
        event["event_type"]
        for event in uninterrupted_state["recorder"]["events"]
    }
    assert "CasualtyTreatedEvent" in event_types
    assert "MaintenanceCompletedEvent" in event_types
    assert (
        control.context.maintenance_engine.get_record(
            unit_id,
            repaired_equipment_id,
        ).status
        is MaintenanceStatus.OPERATIONAL
    )
    assert (
        control.context.medical_engine.get_casualty(
            "phase114-active-casualty",
        ).outcome
        is not None
    )

    control.engine.restore(checkpoint_at_t)
    assert control.engine.checkpoint() == checkpoint_at_t
    _advance(control, 3)
    assert control.engine.checkpoint() == uninterrupted

    fresh = _build_stateful_session(prepared)
    fresh.engine.restore(checkpoint_at_t)
    assert fresh.engine.checkpoint() == checkpoint_at_t
    _advance(fresh, 3)
    assert fresh.engine.checkpoint() == uninterrupted
