"""Phase 114 production-factory proofs for executable era contracts."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

import stochastic_warfare.core.era as era_module
from stochastic_warfare.core.era import (
    Era,
    EraConfig,
    get_era_config,
    register_era_config,
)
from stochastic_warfare.core.types import Position
from stochastic_warfare.logistics.maintenance import MaintenanceStatus
from stochastic_warfare.logistics.medical import (
    CasualtyRecord,
    MedicalFacility,
    MedicalFacilityType,
)
from stochastic_warfare.simulation.campaign import CampaignConfig
from stochastic_warfare.simulation.engine import TickResolution
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    PreparedScenario,
    RuntimeSession,
    SimulationRuntimeFactory,
)
from stochastic_warfare.simulation.scenario import CampaignScenarioConfig


_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _ROOT / "data"
_SOURCE_LABEL = str(
    (_DATA_DIR / "scenarios" / "test_scenario" / "scenario.yaml").resolve(),
)
_SEED = 114
_STRATEGIC_DISTANCE_M = 40_000.0
_OPERATIONAL_DISTANCE_M = 20_000.0
_TACTICAL_DISTANCE_M = 10_000.0


@pytest.fixture(autouse=True)
def _isolate_era_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        era_module,
        "_ERA_REGISTRY",
        copy.deepcopy(era_module._ERA_REGISTRY),
    )


def _scenario_config(
    era_id: str,
    *,
    blue_unit_type: str = "m1a2",
    red_unit_type: str = "t72m",
    distance_m: float = _STRATEGIC_DISTANCE_M,
    strategic_s: float = 3600.0,
    operational_s: float = 300.0,
    tactical_s: float = 5.0,
    duration_hours: float = 100_000.0,
) -> CampaignScenarioConfig:
    """Build a compact two-unit scenario with authored natural positions."""
    return CampaignScenarioConfig.model_validate(
        {
            "name": "Phase 114 factory runtime behavior",
            "date": "2024-01-01T00:00:00Z",
            "duration_hours": duration_hours,
            "era": era_id,
            "tick_resolution": {
                "strategic_s": strategic_s,
                "operational_s": operational_s,
                "tactical_s": tactical_s,
            },
            "terrain": {
                "width_m": 100_000.0,
                "height_m": 20_000.0,
                "cell_size_m": 100.0,
                "terrain_type": "flat_desert",
            },
            "deployment": {"mode": "manual"},
            "sides": [
                {
                    "side": "blue",
                    "units": [
                        {
                            "unit_type": blue_unit_type,
                            "count": 1,
                            "position": [1_000.0, 1_000.0, 0.0],
                        },
                    ],
                },
                {
                    "side": "red",
                    "units": [
                        {
                            "unit_type": red_unit_type,
                            "count": 1,
                            "position": [1_000.0 + distance_m, 1_000.0, 0.0],
                        },
                    ],
                },
            ],
            "objectives": [],
            "victory_conditions": [],
        },
    )


def _prepare(
    config: CampaignScenarioConfig,
    variant_id: str,
) -> PreparedScenario:
    return SimulationRuntimeFactory().prepare_config(
        config,
        _DATA_DIR,
        (AnalysisVariant(variant_id=variant_id),),
        source_label=_SOURCE_LABEL,
    )


def _build(
    prepared: PreparedScenario,
    variant_id: str,
    *,
    maintenance: bool = False,
    record_events: bool = False,
    max_ticks: int = 100,
) -> RuntimeSession:
    return prepared.build(
        variant_id,
        seed=_SEED,
        max_ticks=max_ticks,
        record_events=record_events,
        campaign_config=CampaignConfig(
            enable_maintenance=maintenance,
            enable_supply_network=False,
            enable_strategic_movement=False,
        ),
        strict_mode=True,
    )


def _prepare_and_build(
    config: CampaignScenarioConfig,
    variant_id: str,
    *,
    maintenance: bool = False,
    max_ticks: int = 100,
) -> RuntimeSession:
    return _build(
        _prepare(config, variant_id),
        variant_id,
        maintenance=maintenance,
        max_ticks=max_ticks,
    )


@pytest.mark.parametrize(
    ("distance_m", "resolution", "expected_elapsed_s"),
    (
        (_STRATEGIC_DISTANCE_M, TickResolution.STRATEGIC, 11.0),
        (_OPERATIONAL_DISTANCE_M, TickResolution.OPERATIONAL, 7.0),
        (_TACTICAL_DISTANCE_M, TickResolution.TACTICAL, 3.0),
    ),
)
def test_factory_runtime_uses_effective_cadence_on_natural_resolution_paths(
    distance_m: float,
    resolution: TickResolution,
    expected_elapsed_s: float,
) -> None:
    era_id = f"phase114-cadence-{resolution.name.lower()}"
    register_era_config(
        era_id,
        EraConfig(
            tick_resolution_overrides={
                "strategic_s": 11.0,
                "operational_s": 7.0,
                "tactical_s": 3.0,
            },
        ),
    )
    session = _prepare_and_build(
        _scenario_config(
            era_id,
            distance_m=distance_m,
            strategic_s=101.0,
            operational_s=102.0,
            tactical_s=103.0,
        ),
        f"cadence-{resolution.name.lower()}",
    )

    assert session.engine.resolution == resolution

    session.step()

    assert session.context.clock.elapsed.total_seconds() == expected_elapsed_s
    if resolution is TickResolution.TACTICAL:
        receipt = session.performance_execution_receipt()
        assert receipt.tactical_interval_microseconds == 3_000_000
        assert receipt.tactical_intervals == 1
        assert receipt.tactical_duration_microseconds == 3_000_000


def test_factory_runtime_receipt_preserves_microsecond_tactical_cadence() -> None:
    era_id = "phase114-cadence-one-microsecond"
    register_era_config(
        era_id,
        EraConfig(tick_resolution_overrides={"tactical_s": 1e-6}),
    )
    variant_id = "cadence-one-microsecond"
    prepared = _prepare(
        _scenario_config(
            era_id,
            distance_m=_TACTICAL_DISTANCE_M,
            tactical_s=103.0,
        ),
        variant_id,
    )
    session = _build(prepared, variant_id)
    restored = _build(prepared, variant_id)

    assert session.engine.resolution is TickResolution.TACTICAL
    assert session.step() is False

    receipt = session.performance_execution_receipt()
    assert session.context.clock.elapsed.total_seconds() == 1e-6
    assert receipt.tactical_interval_microseconds == 1
    assert receipt.tactical_intervals == 1
    assert receipt.tactical_duration_microseconds == 1

    checkpoint = session.engine.checkpoint()
    restored.engine.restore(checkpoint)
    assert restored.engine.checkpoint() == checkpoint

    assert session.step() is False
    assert restored.step() is False
    assert restored.engine.checkpoint() == session.engine.checkpoint()
    continued = restored.performance_execution_receipt()
    assert continued.tactical_intervals == 2
    assert continued.tactical_duration_microseconds == 2


def _admit_casualties(session: RuntimeSession) -> dict[int, CasualtyRecord]:
    facility = MedicalFacility(
        facility_id="phase114-field-hospital",
        facility_type=MedicalFacilityType.FIELD_HOSPITAL,
        position=Position(0.0, 0.0, 0.0),
        capacity=100,
    )
    session.context.medical_engine.register_facility(facility)
    unit_id = session.context.units_by_side["blue"][0].entity_id
    return {
        severity: session.context.medical_engine.receive_casualty(
            unit_id=unit_id,
            member_id=f"phase114-severity-{severity}",
            severity=severity,
            facility_id=facility.facility_id,
        )
        for severity in (1, 2, 3)
    }


def _medical_completion_endpoints(
    session: RuntimeSession,
    casualties: dict[int, CasualtyRecord],
) -> dict[int, float]:
    endpoints: dict[int, float] = {}
    while len(endpoints) < len(casualties):
        assert session.step() is False
        elapsed_hours = session.context.clock.elapsed.total_seconds() / 3600.0
        for severity, casualty in casualties.items():
            if casualty.outcome is not None and severity not in endpoints:
                endpoints[severity] = elapsed_hours
    return endpoints


def test_factory_medical_overrides_change_all_severity_completion_endpoints() -> None:
    declared_era = "phase114-medical-declared"
    omitted_era = "phase114-medical-omitted"
    register_era_config(
        declared_era,
        EraConfig(
            physics_overrides={
                "treatment_hours_minor": 1.0,
                "treatment_hours_serious": 2.0,
                "treatment_hours_critical": 3.0,
            },
        ),
    )
    register_era_config(omitted_era, EraConfig())
    declared = _prepare_and_build(
        _scenario_config(
            declared_era,
            strategic_s=3600.0,
            operational_s=3600.0,
            tactical_s=3600.0,
        ),
        "medical-declared",
        max_ticks=40,
    )
    omitted = _prepare_and_build(
        _scenario_config(
            omitted_era,
            strategic_s=3600.0,
            operational_s=3600.0,
            tactical_s=3600.0,
        ),
        "medical-omitted",
        max_ticks=40,
    )

    declared_endpoints = _medical_completion_endpoints(
        declared,
        _admit_casualties(declared),
    )
    omitted_endpoints = _medical_completion_endpoints(
        omitted,
        _admit_casualties(omitted),
    )

    assert declared_endpoints == {1: 2.0, 2: 3.0, 3: 4.0}
    assert omitted_endpoints == {1: 3.0, 2: 9.0, 3: 25.0}
    assert all(declared_endpoints[severity] < omitted_endpoints[severity] for severity in (1, 2, 3))


def _register_equipment_and_reach_breakdown(
    session: RuntimeSession,
) -> tuple[str, str]:
    unit_id = session.context.units_by_side["blue"][0].entity_id
    equipment_ids = [f"phase114-equipment-{index:03d}" for index in range(100)]
    session.context.maintenance_engine.register_equipment(
        unit_id,
        equipment_ids,
        mtbf_hours=1.0,
    )

    assert session.step() is False

    broken_ids = [
        equipment_id
        for equipment_id in equipment_ids
        if session.context.maintenance_engine.get_record(
            unit_id,
            equipment_id,
        ).status
        == MaintenanceStatus.AWAITING_PARTS
    ]
    assert broken_ids, "fixed-seed production step must reach a breakdown"
    return unit_id, broken_ids[0]


@pytest.mark.parametrize(
    ("distance_m", "resolution"),
    (
        (_STRATEGIC_DISTANCE_M, TickResolution.STRATEGIC),
        (_OPERATIONAL_DISTANCE_M, TickResolution.OPERATIONAL),
        (_TACTICAL_DISTANCE_M, TickResolution.TACTICAL),
    ),
)
def test_factory_maintenance_advances_once_per_interval_at_every_resolution(
    distance_m: float,
    resolution: TickResolution,
) -> None:
    era_id = f"phase114-maintenance-{resolution.name.lower()}"
    register_era_config(
        era_id,
        EraConfig(physics_overrides={"repair_time_hours": 15.0}),
    )
    session = _prepare_and_build(
        _scenario_config(
            era_id,
            distance_m=distance_m,
            strategic_s=36_000.0,
            operational_s=36_000.0,
            tactical_s=36_000.0,
        ),
        f"maintenance-{resolution.name.lower()}",
        maintenance=True,
    )
    assert session.engine.resolution == resolution
    unit_id, equipment_id = _register_equipment_and_reach_breakdown(session)

    assert session.context.maintenance_engine.start_repair(
        unit_id,
        equipment_id,
        spare_parts_available=1.0,
        timestamp=session.context.clock.current_time,
    )
    assert session.step() is False
    record = session.context.maintenance_engine.get_record(
        unit_id,
        equipment_id,
    )

    assert record.status == MaintenanceStatus.UNDER_REPAIR
    assert record.repair_elapsed == 10.0

    assert session.step() is False
    assert record.status == MaintenanceStatus.OPERATIONAL
    assert record.repair_elapsed == 20.0


def test_factory_maintenance_override_changes_completion_endpoint() -> None:
    declared_era = "phase114-repair-declared"
    omitted_era = "phase114-repair-omitted"
    register_era_config(
        declared_era,
        EraConfig(physics_overrides={"repair_time_hours": 15.0}),
    )
    register_era_config(omitted_era, EraConfig())

    def build_and_start(
        era_id: str,
        variant_id: str,
    ) -> tuple[RuntimeSession, str, str]:
        session = _prepare_and_build(
            _scenario_config(
                era_id,
                strategic_s=36_000.0,
                operational_s=36_000.0,
                tactical_s=36_000.0,
            ),
            variant_id,
            maintenance=True,
        )
        unit_id, equipment_id = _register_equipment_and_reach_breakdown(
            session,
        )
        assert session.context.maintenance_engine.start_repair(
            unit_id,
            equipment_id,
            spare_parts_available=1.0,
            timestamp=session.context.clock.current_time,
        )
        return session, unit_id, equipment_id

    declared, declared_unit_id, declared_equipment_id = build_and_start(
        declared_era,
        "repair-declared",
    )
    omitted, omitted_unit_id, omitted_equipment_id = build_and_start(
        omitted_era,
        "repair-omitted",
    )

    assert omitted.step() is False
    assert declared.step() is False
    omitted_record = omitted.context.maintenance_engine.get_record(
        omitted_unit_id,
        omitted_equipment_id,
    )
    declared_record = declared.context.maintenance_engine.get_record(
        declared_unit_id,
        declared_equipment_id,
    )

    assert omitted_record.status == MaintenanceStatus.OPERATIONAL
    assert declared_record.status == MaintenanceStatus.UNDER_REPAIR
    assert declared_record.repair_elapsed == 10.0

    assert declared.step() is False
    assert declared_record.status == MaintenanceStatus.OPERATIONAL
    assert declared.context.clock.elapsed.total_seconds() == 108_000.0
    assert omitted.context.clock.elapsed.total_seconds() == 72_000.0


def test_prepared_factory_freezes_registry_behavior_and_fingerprint() -> None:
    era_id = "phase114-registry-isolation"
    config = _scenario_config(
        era_id,
        distance_m=_TACTICAL_DISTANCE_M,
        strategic_s=101.0,
        operational_s=102.0,
        tactical_s=103.0,
    )
    register_era_config(
        era_id,
        EraConfig(tick_resolution_overrides={"tactical_s": 4.0}),
    )
    prepared = _prepare(config, "captured")
    captured_fingerprint = prepared.variant("captured").config_fingerprint

    register_era_config(
        era_id,
        EraConfig(tick_resolution_overrides={"tactical_s": 9.0}),
    )
    first = _build(prepared, "captured")
    second = _build(prepared, "captured")
    replacement = _prepare_and_build(config, "replacement")

    first.step()
    second.step()
    replacement.step()

    assert first.context.era_runtime_contract == second.context.era_runtime_contract
    assert first.context.era_runtime_contract.tactical_s == 4.0
    assert first.context.clock.elapsed.total_seconds() == 4.0
    assert second.context.clock.elapsed.total_seconds() == 4.0
    assert first.config_fingerprint == captured_fingerprint
    assert second.config_fingerprint == captured_fingerprint
    assert replacement.context.era_runtime_contract.tactical_s == 9.0
    assert replacement.context.clock.elapsed.total_seconds() == 9.0
    assert replacement.config_fingerprint != captured_fingerprint


def test_runtime_rejects_shadowed_authored_tick_source_drift() -> None:
    era_id = "phase114-source-drift"
    register_era_config(
        era_id,
        EraConfig(tick_resolution_overrides={"strategic_s": 11.0}),
    )
    session = _prepare_and_build(
        _scenario_config(era_id, strategic_s=101.0),
        "source-drift",
    )
    before = session.context.clock.get_state()

    session.context.config.tick_resolution.strategic_s = 999.0

    with pytest.raises(RuntimeError, match="source changed"):
        session.step()
    assert session.context.clock.get_state() == before
    with pytest.raises(RuntimeError, match="source changed"):
        session.engine.checkpoint()


@pytest.mark.parametrize("equivalent_value", (True, 101))
def test_runtime_rejects_type_equivalent_tick_source_drift(
    equivalent_value: object,
) -> None:
    era_id = "phase114-tick-source-type-drift"
    register_era_config(
        era_id,
        EraConfig(tick_resolution_overrides={"strategic_s": 11.0}),
    )
    session = _prepare_and_build(
        _scenario_config(era_id, strategic_s=101.0),
        "tick-source-type-drift",
    )
    before = session.context.clock.get_state()

    session.context.config.tick_resolution.strategic_s = equivalent_value

    with pytest.raises(RuntimeError, match="source is no longer valid"):
        session.step()
    assert session.context.clock.get_state() == before
    with pytest.raises(RuntimeError, match="source is no longer valid"):
        session.engine.checkpoint()


def test_factory_preparation_rejects_unreachable_calendar_horizon() -> None:
    era_id = "phase114-calendar-horizon"
    register_era_config(era_id, EraConfig())
    config = _scenario_config(
        era_id,
        strategic_s=260_000_000_000.0,
    )

    with pytest.raises(ValueError, match="execution horizon"):
        _prepare(config, "calendar-horizon")


def test_factory_preparation_rejects_invalid_horizon_source() -> None:
    era_id = "phase114-invalid-horizon-source"
    register_era_config(era_id, EraConfig())
    config = _scenario_config(era_id)
    config.date = " 2024-01-01 "

    with pytest.raises(ValueError, match="date"):
        _prepare(config, "invalid-horizon-source")


def test_factory_rejects_separately_overflowing_final_interval() -> None:
    era_id = "phase114-final-interval-overflow"
    register_era_config(era_id, EraConfig())
    config = _scenario_config(
        era_id,
        strategic_s=31e-6,
        operational_s=1e-6,
        tactical_s=1e-6,
        duration_hours=69_916_175.999_999_99,
    )
    config.date = "2024-01-01T00:00:00.000030+00:00"

    with pytest.raises(ValueError, match="execution horizon"):
        _prepare(config, "final-interval-overflow")


@pytest.mark.parametrize("equivalent_value", (True, 1))
def test_runtime_rejects_type_equivalent_horizon_drift(
    equivalent_value: object,
) -> None:
    era_id = "phase114-horizon-drift"
    register_era_config(era_id, EraConfig())
    session = _prepare_and_build(
        _scenario_config(era_id, duration_hours=1.0),
        "horizon-drift",
    )
    before = session.context.clock.get_state()

    session.context.config.duration_hours = equivalent_value

    with pytest.raises(RuntimeError, match="horizon is no longer valid"):
        session.step()
    assert session.context.clock.get_state() == before
    with pytest.raises(RuntimeError, match="horizon is no longer valid"):
        session.engine.checkpoint()


def test_factory_alias_uses_captured_era_for_catalog_and_runtime_updates() -> None:
    era_id = "phase114-ww2-alias"
    ww2_config = get_era_config("ww2")
    register_era_config(
        era_id,
        EraConfig.model_validate(
            {
                **ww2_config.model_dump(mode="python"),
                "tick_resolution_overrides": {
                    "strategic_s": 360_000.0,
                },
            },
            strict=True,
            extra="forbid",
        ),
    )
    prepared = _prepare(
        _scenario_config(
            era_id,
            blue_unit_type="soviet_rifle_squad",
            red_unit_type="wehrmacht_rifle_squad",
        ),
        "ww2-alias",
    )
    first = _build(
        prepared,
        "ww2-alias",
        maintenance=True,
        record_events=True,
    )
    second = _build(
        prepared,
        "ww2-alias",
        maintenance=True,
        record_events=True,
    )

    assert first.context.era_runtime_contract.selected_registry_id == era_id
    assert first.context.era_runtime_contract.era is Era.WW2
    assert {unit.unit_type for side_units in first.context.units_by_side.values() for unit in side_units} == {
        "soviet_rifle_squad",
        "wehrmacht_rifle_squad",
    }
    assert first.context.convoy_engine is not None
    assert second.context.convoy_engine is not None
    assert first.recorder is not None
    assert second.recorder is not None
    first.recorder.start()
    second.recorder.start()

    ship_ids = [f"phase114-merchant-{index:04d}" for index in range(1_000)]
    first_convoy = first.context.convoy_engine.form_convoy(
        "phase114-alias-convoy",
        ship_ids,
        [],
    )
    second_convoy = second.context.convoy_engine.form_convoy(
        "phase114-alias-convoy",
        ship_ids,
        [],
    )
    equipment_ids = [f"phase114-alias-equipment-{index:03d}" for index in range(64)]
    for session in (first, second):
        unit_id = session.context.units_by_side["blue"][0].entity_id
        session.context.maintenance_engine.register_equipment(
            unit_id,
            equipment_ids,
            mtbf_hours=0.001,
        )

    assert first.step() is False
    assert second.step() is False
    assert first_convoy.straggler_ids
    assert first_convoy.straggler_ids == second_convoy.straggler_ids
    for session in (first, second):
        unit_id = session.context.units_by_side["blue"][0].entity_id
        assert session.context.maintenance_engine.start_repair(
            unit_id,
            equipment_ids[0],
            spare_parts_available=1.0,
            timestamp=session.context.clock.current_time,
        )
    assert first.recorder.events
    assert "MaintenanceStartedEvent" in {event.event_type for event in first.recorder.events}
    assert first.recorder.get_state() == second.recorder.get_state()
    assert first.engine.checkpoint() == second.engine.checkpoint()
