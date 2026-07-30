"""Phase 112 production proofs for typed delayed Space imagery."""

from __future__ import annotations

import copy
import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import numpy as np
import pytest

from stochastic_warfare.core.events import Event
from stochastic_warfare.core.types import Position
from stochastic_warfare.detection.estimation import TrackStatus
from stochastic_warfare.detection.intel_fusion import (
    IntelReport,
    IntelSource,
)
from stochastic_warfare.simulation.engine import SimulationEngine
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    SimulationRuntimeFactory,
)
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    ScenarioLoader,
    load_campaign_scenario_config,
)
from stochastic_warfare.space.catalog import (
    SpaceCatalog,
    UnsupportedIMINTFusionError,
    generated_satellite_ids,
)
from stochastic_warfare.space.config import ConstellationType
from stochastic_warfare.space.isr import (
    SpaceISRDeliveryError,
    SpaceISRIntegrityError,
    SpaceISRReport,
    UnsupportedISRTargetError,
)
from stochastic_warfare.space.orbits import OrbitalMechanicsEngine


DATA_ROOT = Path("data")
SPACE_ISR_PATH = DATA_ROOT / "scenarios" / "space_isr_gap" / "scenario.yaml"
SPACE_ASAT_PATH = DATA_ROOT / "scenarios" / "space_asat_escalation" / "scenario.yaml"
TAIWAN_PATH = DATA_ROOT / "scenarios" / "taiwan_strait" / "scenario.yaml"
KOREAN_PATH = DATA_ROOT / "scenarios" / "korean_peninsula" / "scenario.yaml"
SIGMA_M = 1.6309671062462963
RUNTIME_VARIANT = AnalysisVariant(variant_id="phase112-space-isr")


def _engine(
    *,
    seed: int = 42,
    config: CampaignScenarioConfig | None = None,
    path: Path = SPACE_ISR_PATH,
) -> SimulationEngine:
    factory = SimulationRuntimeFactory()
    prepared = (
        factory.prepare(
            path,
            DATA_ROOT,
            (RUNTIME_VARIANT,),
        )
        if config is None
        else factory.prepare_config(
            config,
            DATA_ROOT,
            (RUNTIME_VARIANT,),
            source_label=str(path.resolve()),
        )
    )
    return prepared.build(
        RUNTIME_VARIANT.variant_id,
        seed=seed,
        max_ticks=1_000_000,
        strict_mode=True,
    ).engine


def _advance_to(engine: SimulationEngine, elapsed_s: float) -> None:
    while engine._ctx.clock.elapsed.total_seconds() < elapsed_s:
        engine.step()


def _lifecycle_config() -> CampaignScenarioConfig:
    raw = load_campaign_scenario_config(
        SPACE_ISR_PATH,
    ).model_dump(mode="python")
    raw["space_config"]["constellation_ids"] = [
        "worldview2_reference_optical",
        "worldview3_reference_optical",
    ]
    raw["space_config"]["imint_fusion_constellation_ids"] = [
        "worldview2_reference_optical",
        "worldview3_reference_optical",
    ]
    raw["space_config"]["isr_processing_delay_s"] = 300.0
    return CampaignScenarioConfig.model_validate(raw)


def _long_delay_config() -> CampaignScenarioConfig:
    raw = load_campaign_scenario_config(
        SPACE_ISR_PATH,
    ).model_dump(mode="python")
    raw["duration_hours"] = 7.0
    raw["victory_conditions"][0]["params"]["max_time_s"] = 25_200
    return CampaignScenarioConfig.model_validate(raw)


def _short_delay_config() -> CampaignScenarioConfig:
    raw = load_campaign_scenario_config(
        SPACE_ISR_PATH,
    ).model_dump(mode="python")
    raw["space_config"]["isr_processing_delay_s"] = 300.0
    return CampaignScenarioConfig.model_validate(raw)


def test_supported_catalog_values_and_classified_selection_fail_closed() -> None:
    catalog = SpaceCatalog.load(DATA_ROOT)
    worldview2 = catalog.constellations["worldview2_reference_optical"]
    worldview3 = catalog.constellations["worldview3_reference_optical"]

    assert worldview2.constellation_id == "worldview2_reference_optical"
    assert worldview2.display_name == ("WorldView-2 Public Reference Optical")
    assert worldview2.constellation_type is (ConstellationType.IMAGING_OPTICAL)
    assert worldview2.side == "blue"
    assert (
        worldview2.num_satellites,
        worldview2.plane_count,
        worldview2.sats_per_plane,
    ) == (1, 1, 1)
    assert worldview2.sensor_type == "optical"
    assert worldview2.sensor_resolution_m == 0.46
    assert worldview2.sensor_swath_km == 16.4
    assert worldview2.imint_position_sigma_m == SIGMA_M
    assert generated_satellite_ids(worldview2) == ("worldview2_reference_optical_p0_s0",)
    assert worldview2.orbital_elements_template.model_dump() == {
        "semi_major_axis_m": 7_141_000.0,
        "eccentricity": 0.0,
        "inclination_deg": 98.0,
        "raan_deg": 115.0,
        "arg_perigee_deg": 0.0,
        "true_anomaly_deg": 235.0,
    }

    assert worldview3.constellation_id == "worldview3_reference_optical"
    assert worldview3.display_name == ("WorldView-3 Public Reference Optical")
    assert worldview3.constellation_type is (ConstellationType.IMAGING_OPTICAL)
    assert worldview3.side == "blue"
    assert (
        worldview3.num_satellites,
        worldview3.plane_count,
        worldview3.sats_per_plane,
    ) == (1, 1, 1)
    assert worldview3.sensor_type == "optical"
    assert worldview3.sensor_resolution_m == 0.31
    assert worldview3.sensor_swath_km == 13.1
    assert worldview3.imint_position_sigma_m == SIGMA_M
    assert generated_satellite_ids(worldview3) == ("worldview3_reference_optical_p0_s0",)
    assert worldview3.orbital_elements_template.model_dump() == {
        "semi_major_axis_m": 6_988_000.0,
        "eccentricity": 0.0,
        "inclination_deg": 97.0,
        "raan_deg": 105.0,
        "arg_perigee_deg": 0.0,
        "true_anomaly_deg": 205.0,
    }

    orbital_mechanics = OrbitalMechanicsEngine()
    assert orbital_mechanics.orbital_period(
        worldview2.orbital_elements_template.semi_major_axis_m,
    ) == pytest.approx(6_005.504961558136, rel=0.0, abs=1.0e-9)
    assert orbital_mechanics.orbital_period(
        worldview3.orbital_elements_template.semi_major_axis_m,
    ) == pytest.approx(5_813.535448574455, rel=0.0, abs=1.0e-9)

    cases = (
        (TAIWAN_PATH, "keyhole_optical"),
        (TAIWAN_PATH, "lacrosse_sar"),
        (KOREAN_PATH, "keyhole_optical"),
        (SPACE_ASAT_PATH, "keyhole_optical"),
    )
    for path, constellation_id in cases:
        config = load_campaign_scenario_config(path)
        assert config.space_config is not None
        assert config.space_config.imint_fusion_constellation_ids == []
        raw = config.model_dump(mode="python")
        raw["space_config"]["imint_fusion_constellation_ids"] = [
            constellation_id,
        ]
        if not raw["calibration_overrides"].get(
            "enable_space_effects",
            False,
        ):
            raw["calibration_overrides"]["enable_space_effects"] = True
        selected = CampaignScenarioConfig.model_validate(raw)
        with pytest.raises(
            UnsupportedIMINTFusionError,
            match="no sourced imint_position_sigma_m",
        ):
            ScenarioLoader(DATA_ROOT).load(
                path,
                seed=42,
                scenario_config=selected,
            )

    disabled = load_campaign_scenario_config(
        SPACE_ISR_PATH,
    ).model_dump(mode="python")
    disabled["calibration_overrides"]["enable_space_effects"] = False
    with pytest.raises(
        ValueError,
        match="requires calibration_overrides.enable_space_effects=true",
    ):
        CampaignScenarioConfig.model_validate(disabled)


def test_real_unit_boundary_rejects_unknown_shape_without_mutation() -> None:
    engine = _engine()
    _advance_to(engine, 14_400.0)
    isr = engine._ctx.space_engine.isr_engine
    before_state = copy.deepcopy(isr.get_state())
    before_rng = copy.deepcopy(
        engine._ctx.rng_manager.get_state()["streams"]["space"],
    )

    with pytest.raises(
        UnsupportedISRTargetError,
        match="repository Unit instances",
    ):
        isr.generate_isr_reports(
            "blue",
            "red",
            [object()],
            14_460.0,
        )

    assert isr.get_state() == before_state
    assert engine._ctx.rng_manager.get_state()["streams"]["space"] == before_rng


def test_report_generation_rejects_owner_and_target_side_mismatches() -> None:
    engine = _engine()
    _advance_to(engine, 14_340.0)
    context = engine._ctx
    isr = context.space_engine.isr_engine
    before_isr = copy.deepcopy(isr.get_state())
    before_space_rng = copy.deepcopy(
        context.rng_manager.get_state()["streams"]["space"],
    )

    with pytest.raises(
        SpaceISRIntegrityError,
        match="does not own a selected imagery-fusion constellation",
    ):
        isr.generate_isr_reports(
            "red",
            "blue",
            context.units_by_side["blue"],
            14_400.0,
        )
    assert isr.get_state() == before_isr
    assert context.rng_manager.get_state()["streams"]["space"] == before_space_rng

    with pytest.raises(
        UnsupportedISRTargetError,
        match="does not match target_side 'red'",
    ):
        isr.generate_isr_reports(
            "blue",
            "red",
            context.units_by_side["blue"],
            14_400.0,
        )
    assert isr.get_state() == before_isr
    assert context.rng_manager.get_state()["streams"]["space"] == before_space_rng


def test_update_rejects_later_side_target_before_any_batch_mutation() -> None:
    engine = _engine()
    _advance_to(engine, 14_340.0)
    context = engine._ctx
    context.space_engine.constellation_manager.update(60.0, 14_400.0)
    isr = context.space_engine.isr_engine
    fusion = context.fog_of_war.intel_fusion
    before_state = copy.deepcopy(isr.get_state())
    before_fusion = copy.deepcopy(fusion.get_state())
    before_rng = copy.deepcopy(
        context.rng_manager.get_state()["streams"]["space"],
    )

    with pytest.raises(
        UnsupportedISRTargetError,
        match="repository Unit instances",
    ):
        isr.update(
            60.0,
            14_400.0,
            {
                "blue": [object()],
                "red": context.units_by_side["red"],
            },
            intel_fusion=fusion,
        )

    assert isr.get_state() == before_state
    assert fusion.get_state() == before_fusion
    assert context.rng_manager.get_state()["streams"]["space"] == before_rng


def test_non_strict_master_loop_propagates_malformed_real_target_immediately() -> None:
    engine = _engine()
    _advance_to(engine, 14_340.0)
    context = engine._ctx
    target = context.units_by_side["blue"][0]
    target.position = Position(
        math.nan,
        target.position.northing,
        target.position.altitude,
    )
    before_diagnostics = copy.deepcopy(
        context.movement_diagnostics.get_state(),
    )
    before_space = copy.deepcopy(context.space_engine.get_state())
    before_fusion = copy.deepcopy(
        context.fog_of_war.intel_fusion.get_state(),
    )
    before_space_rng = copy.deepcopy(
        context.rng_manager.get_state()["streams"]["space"],
    )
    before_detection_rng = copy.deepcopy(
        context.rng_manager.get_state()["streams"]["detection"],
    )
    before_checkpoint = engine.checkpoint()

    with pytest.raises(
        UnsupportedISRTargetError,
        match="position\\[0\\] must be a finite number",
    ):
        engine.step()

    assert engine.checkpoint() == before_checkpoint
    assert context.movement_diagnostics.get_state() == before_diagnostics
    assert context.space_engine.get_state() == before_space
    assert context.fog_of_war.intel_fusion.get_state() == before_fusion
    assert context.rng_manager.get_state()["streams"]["space"] == before_space_rng
    assert context.rng_manager.get_state()["streams"]["detection"] == before_detection_rng


def test_non_strict_fusion_lifecycle_failure_is_preflight_atomic_and_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed = _engine(seed=772_112)
    clean = _engine(seed=772_112)
    context = failed._ctx
    fusion = context.fog_of_war.intel_fusion
    original_prepare = fusion.prepare_imint_lifecycle
    before = failed.checkpoint()

    def _fail_lifecycle(current_time_s: float) -> None:
        del current_time_s
        raise RuntimeError("injected fusion-integrity failure")

    monkeypatch.setattr(
        fusion,
        "prepare_imint_lifecycle",
        _fail_lifecycle,
    )
    with pytest.raises(
        SpaceISRDeliveryError,
        match="preflight imagery-fusion lifecycle",
    ):
        failed.step()
    assert failed.checkpoint() == before

    monkeypatch.setattr(
        fusion,
        "prepare_imint_lifecycle",
        original_prepare,
    )
    assert failed.step() == clean.step()
    assert failed.checkpoint() == clean.checkpoint()


def test_space_update_preflight_rejects_without_effects_then_retries_exactly() -> None:
    failed = _engine()
    clean = _engine()
    _advance_to(failed, 14_340.0)
    _advance_to(clean, 14_340.0)
    failed_context = failed._ctx
    clean_context = clean._ctx
    failed_events: list[Event] = []
    clean_events: list[Event] = []
    failed_context.event_bus.subscribe(Event, failed_events.append)
    clean_context.event_bus.subscribe(Event, clean_events.append)

    target = failed_context.units_by_side["blue"][0]
    valid_position = target.position
    target.position = Position(
        math.nan,
        target.position.northing,
        target.position.altitude,
    )
    before_space = copy.deepcopy(failed_context.space_engine.get_state())
    before_fusion = copy.deepcopy(
        failed_context.fog_of_war.intel_fusion.get_state(),
    )
    before_rng = copy.deepcopy(failed_context.rng_manager.get_state())
    before_clock = copy.deepcopy(failed_context.clock.get_state())

    with pytest.raises(
        UnsupportedISRTargetError,
        match="position\\[0\\] must be a finite number",
    ):
        failed_context.space_engine.update(
            60.0,
            14_400.0,
            em_environment=failed_context.conditions_engine,
            comms_engine=failed_context.comms_engine,
            targets_by_side=failed_context.units_by_side,
            timestamp=failed_context.clock.current_time,
            intel_fusion=failed_context.fog_of_war.intel_fusion,
        )

    assert failed_context.space_engine.get_state() == before_space
    assert failed_context.fog_of_war.intel_fusion.get_state() == before_fusion
    assert failed_context.rng_manager.get_state() == before_rng
    assert failed_context.clock.get_state() == before_clock
    assert failed_events == []

    target.position = valid_position
    failed_context.space_engine.update(
        60.0,
        14_400.0,
        em_environment=failed_context.conditions_engine,
        comms_engine=failed_context.comms_engine,
        targets_by_side=failed_context.units_by_side,
        timestamp=failed_context.clock.current_time,
        intel_fusion=failed_context.fog_of_war.intel_fusion,
    )
    clean_context.space_engine.update(
        60.0,
        14_400.0,
        em_environment=clean_context.conditions_engine,
        comms_engine=clean_context.comms_engine,
        targets_by_side=clean_context.units_by_side,
        timestamp=clean_context.clock.current_time,
        intel_fusion=clean_context.fog_of_war.intel_fusion,
    )

    assert failed_context.space_engine.get_state() == (clean_context.space_engine.get_state())
    assert failed_context.fog_of_war.intel_fusion.get_state() == (clean_context.fog_of_war.intel_fusion.get_state())
    assert failed_context.rng_manager.get_state() == (clean_context.rng_manager.get_state())
    assert failed_events == clean_events


def test_long_delay_delivery_is_owner_scoped_and_checkpoint_exact() -> None:
    config = _long_delay_config()
    uninterrupted = _engine(config=config)
    _advance_to(uninterrupted, 14_400.0)
    isr = uninterrupted._ctx.space_engine.isr_engine
    fusion = uninterrupted._ctx.fog_of_war.intel_fusion
    assert len(isr._report_queue) == 8
    assert uninterrupted._ctx.ew_engine is None
    assert fusion.get_state()["satellite_passes"] == {
        "blue": [
            {
                "satellite_id": ("worldview3_reference_optical_p0_s0"),
                "constellation_id": ("worldview3_reference_optical"),
                "side": "blue",
                "start_time": 14_400.0,
                "end_time": 14_460.0,
                "coverage_center_x": 33.0,
                "coverage_center_y": 35.0,
                "coverage_radius_m": 6_550.0,
                "resolution_m": 0.31,
                "revisit_interval_s": 60.0,
                "source_type": int(IntelSource.IMINT),
            },
        ],
    }
    assert fusion.delivery_receipts == ()
    assert fusion.get_tracks("blue") == {}
    assert fusion.get_tracks("red") == {}

    before_duplicate = uninterrupted.checkpoint()
    duplicate_reports = isr.generate_isr_reports(
        "blue",
        "red",
        uninterrupted._ctx.units_by_side["red"],
        14_400.0,
    )
    assert duplicate_reports == ()
    assert uninterrupted.checkpoint() == before_duplicate

    _advance_to(uninterrupted, 18_000.0)
    isr = uninterrupted._ctx.space_engine.isr_engine
    fusion = uninterrupted._ctx.fog_of_war.intel_fusion

    assert len(isr._report_queue) > 8
    assert fusion.delivery_receipts == ()
    assert fusion.get_tracks("blue") == {}
    assert fusion.get_tracks("red") == {}

    checkpoint = uninterrupted.checkpoint()
    resumed = _engine(seed=999_112, config=config)
    resumed.restore(checkpoint)
    assert resumed.checkpoint() == checkpoint

    _advance_to(uninterrupted, 21_600.0)
    _advance_to(resumed, 21_600.0)
    assert resumed.checkpoint() == uninterrupted.checkpoint()

    context = uninterrupted._ctx
    isr = context.space_engine.isr_engine
    fusion = context.fog_of_war.intel_fusion
    red_target_ids = tuple(sorted(unit.entity_id for unit in context.units_by_side["red"]))
    receipts = fusion.delivery_receipts

    assert len(receipts) == 8
    assert tuple(receipt.report_id for receipt in receipts) == tuple(
        range(1, 9),
    )
    assert tuple(receipt.target_id for receipt in receipts) == red_target_ids
    assert all(receipt.source is IntelSource.IMINT for receipt in receipts)
    assert all(receipt.reporting_side == "blue" for receipt in receipts)
    assert all(receipt.target_side == "red" for receipt in receipts)
    assert all(receipt.observed_at_s == 14_400.0 for receipt in receipts)
    assert all(receipt.available_at_s == 21_600.0 for receipt in receipts)
    assert all(receipt.delivery_time_s == 21_600.0 for receipt in receipts)
    assert fusion.get_tracks("red") == {}

    blue_tracks = fusion.get_tracks("blue")
    assert len(blue_tracks) == 8
    assert fusion.get_actionable_tracks("blue") == {}
    associations = fusion.imint_target_tracks["blue"]
    assert set(associations) == set(red_target_ids)
    for target_id, association in associations.items():
        track = blue_tracks[association.track_id]
        assert association.target_id == target_id
        assert association.last_report_id in range(1, 9)
        assert association.last_observed_at_s == 14_400.0
        assert association.last_received_at_s == 21_600.0
        assert track.status is TrackStatus.STALE
        assert track.state.last_update_time == 14_400.0
        np.testing.assert_allclose(
            track.state.covariance[:2, :2],
            np.diag([SIGMA_M**2, SIGMA_M**2]),
            rtol=0.0,
            atol=1.0e-12,
        )

    assert isr._report_queue[0].observed_at_s == 14_460.0
    world_views = {side: context.fog_of_war.get_world_view(side).contacts for side in context.side_names()}
    resumed_world_views = {
        side: resumed._ctx.fog_of_war.get_world_view(side).contacts for side in resumed._ctx.side_names()
    }
    assert world_views == resumed_world_views == {"blue": {}, "red": {}}
    assert (
        fusion.get_state()["satellite_passes"] == (resumed._ctx.fog_of_war.intel_fusion.get_state()["satellite_passes"])
    )

    post_delivery_checkpoint = uninterrupted.checkpoint()
    restored_after_delivery = _engine(seed=888_112, config=config)
    restored_after_delivery.restore(post_delivery_checkpoint)
    assert restored_after_delivery.checkpoint() == post_delivery_checkpoint

    initial_track_ids = {target_id: association.track_id for target_id, association in associations.items()}
    uninterrupted.step()
    resumed.step()
    restored_after_delivery.step()
    assert resumed.checkpoint() == uninterrupted.checkpoint()
    assert restored_after_delivery.checkpoint() == uninterrupted.checkpoint()
    assert len(fusion.delivery_receipts) == 16
    assert {
        target_id: association.track_id for target_id, association in fusion.imint_target_tracks["blue"].items()
    } == initial_track_ids
    assert {association.last_observed_at_s for association in fusion.imint_target_tracks["blue"].values()} == {14_460.0}


def test_imint_delivery_prepare_is_non_mutating_until_commit() -> None:
    engine = _engine(config=_short_delay_config())
    _advance_to(engine, 14_400.0)
    isr = engine._ctx.space_engine.isr_engine
    fusion = engine._ctx.fog_of_war.intel_fusion
    report = isr.get_recent_reports()[0]
    before_fusion = copy.deepcopy(fusion.get_state())
    before_queue = isr.get_recent_reports()

    plan = fusion.prepare_imint_report(
        report,
        delivery_time_s=14_700.0,
    )
    stale_plan = fusion.prepare_imint_report(
        report,
        delivery_time_s=14_700.0,
    )

    assert fusion.get_state() == before_fusion
    assert isr.get_recent_reports() == before_queue

    receipt = fusion.commit_imint_report(plan)

    assert receipt.report_id == report.report_id
    assert fusion.delivery_receipts == (receipt,)
    assert fusion._delivery_receipts.count == 1
    assert fusion._delivery_receipts.revision == 1
    assert fusion._delivery_receipts.get(receipt.report_id) is receipt
    assert receipt.resulting_track_id in fusion.get_tracks("blue")
    assert isr.get_recent_reports() == before_queue

    after_commit = copy.deepcopy(fusion.get_state())
    with pytest.raises(RuntimeError, match="stale"):
        fusion.commit_imint_report(stale_plan)
    assert fusion.get_state() == after_commit


def test_space_restore_rejects_mapping_and_attribute_receipt_proxies() -> None:
    """Only an exact fusion-owned receipt may cross the Space restore boundary."""
    engine = _engine()
    _advance_to(engine, 14_400.0)
    space_engine = engine._ctx.space_engine
    assert space_engine is not None
    state = space_engine.get_state()
    report_state = state["isr_engine"]["report_queue"].pop(0)
    before = engine.checkpoint()

    for untyped_receipt in (
        report_state,
        SimpleNamespace(**report_state),
    ):
        with pytest.raises(
            ValueError,
            match=(
                "Delivered ISR receipt 0 must be an "
                "IntelDeliveryReceipt instance"
            ),
        ):
            space_engine.stage_state(
                state,
                delivered_receipts=(untyped_receipt,),
            )
        assert engine.checkpoint() == before


def test_imint_prepare_and_commit_do_not_iterate_large_receipt_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Indexed delivery remains independent of the persisted ledger length."""
    engine = _engine(config=_short_delay_config())
    _advance_to(engine, 15_180.0)
    isr = engine._ctx.space_engine.isr_engine
    fusion = engine._ctx.fog_of_war.intel_fusion
    ledger = fusion._delivery_receipts
    initial_count = ledger.count
    initial_revision = ledger.revision
    assert initial_count >= 64
    queued = isr.get_recent_reports()
    assert len(queued) == 8

    def _reject_ledger_iteration(_ledger: object) -> None:
        raise AssertionError(
            "IMINT prepare/commit must not scan or copy the receipt ledger",
        )

    monkeypatch.setattr(
        type(ledger),
        "__iter__",
        _reject_ledger_iteration,
    )
    receipts = isr.process_ready_reports(
        fusion,
        queued[0].available_at_s,
    )

    assert receipts
    assert tuple(receipt.report_id for receipt in receipts) == tuple(
        report.report_id for report in queued
    )
    assert ledger.count == initial_count + len(receipts)
    assert ledger.revision == initial_revision + len(receipts)
    assert all(
        ledger.get(receipt.report_id) is receipt
        for receipt in receipts
    )
    assert isr.get_recent_reports() == ()


def test_ready_delivery_report_n_failure_preserves_prior_commits_and_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _engine(config=_short_delay_config())
    _advance_to(engine, 14_400.0)
    isr = engine._ctx.space_engine.isr_engine
    fusion = engine._ctx.fog_of_war.intel_fusion
    original_prepare = fusion.prepare_imint_report
    failure_boundary: dict[str, Any] = {}

    def _fail_third_after_prepare(
        report: SpaceISRReport,
        *,
        delivery_time_s: float,
    ) -> Any:
        plan = original_prepare(
            report,
            delivery_time_s=delivery_time_s,
        )
        if report.report_id != 3:
            return plan
        failure_boundary["fusion"] = copy.deepcopy(fusion.get_state())
        failure_boundary["queue"] = copy.deepcopy(
            isr.get_recent_reports(),
        )
        failure_boundary["detection_rng"] = copy.deepcopy(
            engine._ctx.rng_manager.get_state()["streams"]["detection"],
        )
        raise RuntimeError("injected report-N post-prepare failure")

    monkeypatch.setattr(
        fusion,
        "prepare_imint_report",
        _fail_third_after_prepare,
    )
    with pytest.raises(
        SpaceISRDeliveryError,
        match="Failed to deliver Space ISR report 3",
    ):
        _advance_to(engine, 14_700.0)

    assert engine._ctx.clock.elapsed.total_seconds() == 14_700.0
    prior_receipts = fusion.delivery_receipts
    assert tuple(receipt.report_id for receipt in prior_receipts) == (1, 2)
    assert tuple(report.report_id for report in isr.get_recent_reports()) == tuple(range(3, 49))
    assert fusion.get_state() == failure_boundary["fusion"]
    assert isr.get_recent_reports() == failure_boundary["queue"]
    assert engine._ctx.rng_manager.get_state()["streams"]["detection"] == failure_boundary["detection_rng"]

    failed_checkpoint = engine.checkpoint()
    resumed = _engine(seed=333_112, config=_short_delay_config())
    resumed.restore(failed_checkpoint)
    assert resumed.checkpoint() == failed_checkpoint
    resumed_fusion = resumed._ctx.fog_of_war.intel_fusion
    assert resumed_fusion.delivery_receipts == prior_receipts
    assert resumed_fusion._delivery_receipts.count == len(prior_receipts)
    assert resumed_fusion._delivery_receipts.revision > 0
    assert all(
        resumed_fusion._delivery_receipts.get(receipt.report_id) is restored
        for receipt, restored in zip(
            prior_receipts,
            resumed_fusion.delivery_receipts,
            strict=True,
        )
    )
    assert tuple(report.report_id for report in (resumed._ctx.space_engine.isr_engine.get_recent_reports())) == tuple(
        range(3, 49)
    )

    monkeypatch.setattr(
        fusion,
        "prepare_imint_report",
        original_prepare,
    )
    receipts = isr.process_ready_reports(fusion, 14_700.0)
    resumed_receipts = resumed._ctx.space_engine.isr_engine.process_ready_reports(
        resumed._ctx.fog_of_war.intel_fusion,
        14_700.0,
    )
    assert tuple(receipt.report_id for receipt in receipts) == tuple(
        range(3, 9),
    )
    assert resumed_receipts == receipts
    assert resumed.checkpoint() == engine.checkpoint()
    assert tuple(report.report_id for report in isr.get_recent_reports()) == tuple(range(9, 49))
    assert fusion.delivery_receipts[:2] == prior_receipts
    assert tuple(receipt.report_id for receipt in fusion.delivery_receipts) == tuple(range(1, 9))
    assert isr.process_ready_reports(fusion, 14_700.0) == ()
    assert len(fusion.delivery_receipts) == 8


def test_imint_commit_rejects_in_place_affected_track_mutation() -> None:
    engine = _engine(config=_short_delay_config())
    _advance_to(engine, 14_400.0)
    isr = engine._ctx.space_engine.isr_engine
    fusion = engine._ctx.fog_of_war.intel_fusion
    first_report = isr.get_recent_reports()[0]
    first_plan = fusion.prepare_imint_report(
        first_report,
        delivery_time_s=14_700.0,
    )
    first_receipt = fusion.commit_imint_report(first_plan)
    next_report = first_report.model_copy(
        update={
            "report_id": 900_112,
            "observed_at_s": 14_401.0,
            "available_at_s": 14_701.0,
        },
    )
    plan = fusion.prepare_imint_report(
        next_report,
        delivery_time_s=14_701.0,
    )
    live_track = fusion.get_tracks("blue")[first_receipt.resulting_track_id]
    live_track.hits += 1
    after_mutation = copy.deepcopy(fusion.get_state())

    with pytest.raises(RuntimeError, match="stale"):
        fusion.commit_imint_report(plan)

    assert fusion.get_state() == after_mutation


def test_imint_commit_rejects_same_length_receipt_replacement() -> None:
    engine = _engine(config=_short_delay_config())
    _advance_to(engine, 14_400.0)
    isr = engine._ctx.space_engine.isr_engine
    fusion = engine._ctx.fog_of_war.intel_fusion
    first_report = isr.get_recent_reports()[0]
    first_receipt = fusion.commit_imint_report(
        fusion.prepare_imint_report(
            first_report,
            delivery_time_s=14_700.0,
        ),
    )
    next_report = first_report.model_copy(
        update={
            "report_id": 900_113,
            "observed_at_s": 14_401.0,
            "available_at_s": 14_701.0,
        },
    )
    plan = fusion.prepare_imint_report(
        next_report,
        delivery_time_s=14_701.0,
    )
    fusion._delivery_receipts[0] = first_receipt.model_copy(
        update={"delivery_time_s": 14_701.0},
    )
    after_replacement = copy.deepcopy(fusion.get_state())

    with pytest.raises(RuntimeError, match="stale"):
        fusion.commit_imint_report(plan)

    assert fusion.get_state() == after_replacement


def test_lifecycle_boundaries_reactivate_and_preserve_track_identity() -> None:
    engine = _engine(config=_lifecycle_config())
    _advance_to(engine, 15_300.0)
    context = engine._ctx
    isr = context.space_engine.isr_engine
    fusion = context.fog_of_war.intel_fusion

    initial_ids = {
        target_id: association.track_id for target_id, association in fusion.imint_target_tracks["blue"].items()
    }
    assert len(initial_ids) == 8
    assert {association.last_observed_at_s for association in fusion.imint_target_tracks["blue"].values()} == {15_000.0}
    assert {track.status for track in fusion.get_tracks("blue").values()} == {TrackStatus.CONFIRMED}

    isr.process_ready_reports(fusion, 15_301.0)
    assert {track.status for track in fusion.get_tracks("blue").values()} == {TrackStatus.COASTING}
    _advance_to(engine, 15_600.0)
    assert {track.status for track in fusion.get_tracks("blue").values()} == {TrackStatus.COASTING}
    isr.process_ready_reports(fusion, 15_601.0)
    assert {track.status for track in fusion.get_tracks("blue").values()} == {TrackStatus.STALE}

    _advance_to(engine, 20_580.0)
    assert {
        target_id: association.track_id for target_id, association in fusion.imint_target_tracks["blue"].items()
    } == initial_ids
    assert {association.last_observed_at_s for association in fusion.imint_target_tracks["blue"].values()} == {20_280.0}
    assert {track.status for track in fusion.get_tracks("blue").values()} == {TrackStatus.CONFIRMED}

    receipt_count = len(fusion.delivery_receipts)
    prior_report_id = max(receipt.report_id for receipt in fusion.delivery_receipts)
    _advance_to(engine, 20_640.0)
    same_epoch = fusion.delivery_receipts[receipt_count:]
    assert len(same_epoch) == 16
    target_ids = tuple(
        sorted(unit.entity_id for unit in context.units_by_side["red"]),
    )
    expected_same_epoch: list[tuple[Any, ...]] = []
    report_id = prior_report_id + 1
    for constellation_id in (
        "worldview2_reference_optical",
        "worldview3_reference_optical",
    ):
        satellite_id = f"{constellation_id}_p0_s0"
        for target_id in target_ids:
            expected_same_epoch.append(
                (
                    20_640.0,
                    20_340.0,
                    "blue",
                    constellation_id,
                    satellite_id,
                    target_id,
                    report_id,
                    "red",
                    20_640.0,
                    initial_ids[target_id],
                ),
            )
            report_id += 1
    assert [
        (
            receipt.available_at_s,
            receipt.observed_at_s,
            receipt.reporting_side,
            receipt.constellation_id,
            receipt.satellite_id,
            receipt.target_id,
            receipt.report_id,
            receipt.target_side,
            receipt.delivery_time_s,
            receipt.resulting_track_id,
        )
        for receipt in same_epoch
    ] == expected_same_epoch
    assert {association.last_observed_at_s for association in fusion.imint_target_tracks["blue"].values()} == {20_340.0}


def test_older_and_gated_imint_reports_are_transactional() -> None:
    engine = _engine(config=_lifecycle_config())
    _advance_to(engine, 20_580.0)
    fusion = engine._ctx.fog_of_war.intel_fusion
    association = next(
        iter(fusion.imint_target_tracks["blue"].values()),
    )
    latest = next(
        receipt for receipt in reversed(fusion.delivery_receipts) if receipt.target_id == association.target_id
    )

    older = SpaceISRReport(
        report_id=900_001,
        reporting_side=latest.reporting_side,
        target_side=latest.target_side,
        target_id=latest.target_id,
        satellite_id=latest.satellite_id,
        constellation_id=latest.constellation_id,
        sensor_type=latest.sensor_type,
        resolution_m=latest.resolution_m,
        position_sigma_m=latest.position_sigma_m,
        target_position=latest.observed_position,
        observed_at_s=latest.observed_at_s - 1.0,
        available_at_s=latest.available_at_s,
    )
    before = copy.deepcopy(fusion.get_state())
    with pytest.raises(ValueError, match="predates"):
        fusion.submit_imint_report(
            older,
            delivery_time_s=latest.delivery_time_s,
        )
    assert fusion.get_state() == before

    gated = SpaceISRReport(
        report_id=900_002,
        reporting_side=latest.reporting_side,
        target_side=latest.target_side,
        target_id=latest.target_id,
        satellite_id=latest.satellite_id,
        constellation_id=latest.constellation_id,
        sensor_type=latest.sensor_type,
        resolution_m=latest.resolution_m,
        position_sigma_m=latest.position_sigma_m,
        target_position=Position(1.0e9, -1.0e9, 0.0),
        observed_at_s=latest.observed_at_s + 1.0,
        available_at_s=latest.delivery_time_s,
    )
    with pytest.raises(ValueError, match="gating"):
        fusion.submit_imint_report(
            gated,
            delivery_time_s=latest.delivery_time_s,
        )
    assert fusion.get_state() == before


@pytest.fixture(scope="module")
def delivered_state() -> dict[str, Any]:
    engine = _engine()
    _advance_to(engine, 21_600.0)
    return engine.get_state()


def test_report_restore_rejects_owner_and_target_side_mismatches_atomically() -> None:
    source = _engine()
    _advance_to(source, 14_400.0)
    valid = source.get_state()
    queue_path = valid["context"]["space_engine"]["isr_engine"]["report_queue"]
    assert len(queue_path) == 8
    blue_target_id = source._ctx.units_by_side["blue"][0].entity_id

    wrong_owner = copy.deepcopy(valid)
    owner_report = wrong_owner["context"]["space_engine"]["isr_engine"]["report_queue"][0]
    owner_report["reporting_side"] = "red"
    owner_report["target_side"] = "blue"
    owner_report["target_id"] = blue_target_id

    wrong_target_side = copy.deepcopy(valid)
    wrong_target_side["context"]["space_engine"]["isr_engine"]["report_queue"][0]["target_id"] = blue_target_id

    target = _engine(seed=551_112)
    before = target.checkpoint()
    with pytest.raises(
        ValueError,
        match="constellation ownership mismatch",
    ):
        target.set_state(wrong_owner)
    assert target.checkpoint() == before

    with pytest.raises(
        ValueError,
        match="target is absent or on the wrong side",
    ):
        target.set_state(wrong_target_side)
    assert target.checkpoint() == before

    target.set_state(valid)
    assert target.checkpoint() == source.checkpoint()


def _receipt_before_availability(state: dict[str, Any]) -> None:
    receipt = state["context"]["fog_of_war"]["intel_fusion"]["delivery_receipts"][0]
    receipt["delivery_time_s"] = receipt["available_at_s"] - 1.0


def _receipt_after_checkpoint(state: dict[str, Any]) -> None:
    receipt = state["context"]["fog_of_war"]["intel_fusion"]["delivery_receipts"][0]
    receipt["delivery_time_s"] = 21_601.0


def _association_report_mismatch(state: dict[str, Any]) -> None:
    state["context"]["fog_of_war"]["intel_fusion"]["imint_target_tracks"][0]["last_report_id"] = 999_112


def _association_epoch_mismatch(state: dict[str, Any]) -> None:
    state["context"]["fog_of_war"]["intel_fusion"]["imint_target_tracks"][0]["last_observed_at_s"] -= 1.0


def _association_track_mismatch(state: dict[str, Any]) -> None:
    state["context"]["fog_of_war"]["intel_fusion"]["imint_target_tracks"][0]["track_id"] = "track-9999"


def _association_track_ambiguity(state: dict[str, Any]) -> None:
    fusion = state["context"]["fog_of_war"]["intel_fusion"]
    first = fusion["imint_target_tracks"][0]
    second = fusion["imint_target_tracks"][1]
    second["track_id"] = first["track_id"]
    matching_receipt = next(
        receipt for receipt in fusion["delivery_receipts"] if receipt["report_id"] == second["last_report_id"]
    )
    matching_receipt["resulting_track_id"] = first["track_id"]


def _cadence_derivation_mismatch(state: dict[str, Any]) -> None:
    state["context"]["space_engine"]["isr_engine"]["last_reported_at"][0]["observed_at_s"] -= 1.0


def _cadence_reporting_side_mismatch(state: dict[str, Any]) -> None:
    state["context"]["space_engine"]["isr_engine"]["last_reported_at"][0]["reporting_side"] = "red"


def _cadence_satellite_mismatch(state: dict[str, Any]) -> None:
    state["context"]["space_engine"]["isr_engine"]["last_reported_at"][0]["satellite_id"] = "unknown-satellite"


def _cadence_target_mismatch(state: dict[str, Any]) -> None:
    state["context"]["space_engine"]["isr_engine"]["last_reported_at"][0]["target_id"] = "unknown-target"


def _obscurant_counter_mismatch(state: dict[str, Any]) -> None:
    state["context"]["obscurants_engine"]["next_cloud_sequence"] = 0


def _fusion_counter_mismatch(state: dict[str, Any]) -> None:
    state["context"]["fog_of_war"]["intel_fusion"]["track_counter"] += 1


def _queued_report_predates_delivery(state: dict[str, Any]) -> None:
    queued = state["context"]["space_engine"]["isr_engine"]["report_queue"][0]
    queued["observed_at_s"] = 14_340.0
    queued["available_at_s"] = 21_540.0


def _terminal_tick_mismatch(state: dict[str, Any]) -> None:
    state["last_victory"]["tick"] -= 1


def _malformed_position(state: dict[str, Any]) -> None:
    state["context"]["space_engine"]["isr_engine"]["report_queue"][0]["target_position"] = [1.0, 2.0]


@pytest.mark.parametrize(
    "corrupt",
    (
        _receipt_before_availability,
        _receipt_after_checkpoint,
        _association_report_mismatch,
        _association_epoch_mismatch,
        _association_track_mismatch,
        _association_track_ambiguity,
        _cadence_derivation_mismatch,
        _cadence_reporting_side_mismatch,
        _cadence_satellite_mismatch,
        _cadence_target_mismatch,
        _obscurant_counter_mismatch,
        _fusion_counter_mismatch,
        _queued_report_predates_delivery,
        _terminal_tick_mismatch,
        _malformed_position,
    ),
    ids=lambda function: function.__name__,
)
def test_cross_state_corruption_rejects_atomically(
    delivered_state: dict[str, Any],
    corrupt: Callable[[dict[str, Any]], None],
) -> None:
    invalid = copy.deepcopy(delivered_state)
    corrupt(invalid)
    target = _engine(seed=777_112)
    before = target.checkpoint()

    with pytest.raises(ValueError):
        target.set_state(invalid)

    assert target.checkpoint() == before


def test_non_imint_stale_checkpoint_rejects_then_valid_retry_continues() -> None:
    source = _engine(seed=812_112)
    fusion = source._ctx.fog_of_war.intel_fusion
    track_id = fusion.submit_report(
        "blue",
        IntelReport(
            source=IntelSource.SENSOR,
            timestamp=0.0,
            reliability=1.0,
            target_position=Position(1_000.0, 2_000.0, 0.0),
            position_uncertainty_m=25.0,
        ),
    )
    assert track_id is not None
    assert track_id in fusion.get_actionable_tracks("blue")
    valid = copy.deepcopy(source.get_state())
    invalid = copy.deepcopy(valid)
    invalid["context"]["fog_of_war"]["intel_fusion"]["tracks"]["blue"][track_id]["status"] = int(TrackStatus.STALE)

    target = _engine(seed=913_112)
    before = target.checkpoint()
    with pytest.raises(
        ValueError,
        match="STALE track has no unique IMINT association",
    ):
        target.set_state(invalid)
    assert target.checkpoint() == before

    target.set_state(valid)
    assert target.checkpoint() == source.checkpoint()
    assert target.step() == source.step()
    assert target.checkpoint() == source.checkpoint()


def test_empty_fusion_selection_produces_no_reports() -> None:
    engine = _engine(path=SPACE_ASAT_PATH)
    _advance_to(engine, 7_200.0)

    assert engine._ctx.space_engine.isr_engine.get_recent_reports() == ()
    assert engine._ctx.fog_of_war.intel_fusion.delivery_receipts == ()


def test_terminal_step_is_idempotent_and_persists_across_restore() -> None:
    terminal = _engine()
    _advance_to(terminal, 21_600.0)
    assert terminal.finalize().victory_result.condition_type == "time_expired"
    terminal_checkpoint = terminal.checkpoint()

    assert terminal.step() is True
    assert terminal.step() is True
    assert terminal.checkpoint() == terminal_checkpoint

    restored = _engine(seed=123_112)
    restored.restore(terminal_checkpoint)
    assert restored.finalize() == terminal.finalize()
    assert restored.step() is True
    assert restored.checkpoint() == terminal_checkpoint


def test_obscurant_ids_continue_exactly_across_fresh_restore() -> None:
    uninterrupted = _engine()
    obscurants = uninterrupted._ctx.obscurants_engine
    assert (
        obscurants.deploy_smoke(
            Position(100.0, 200.0, 0.0),
            50.0,
        )
        == "smoke_00000001"
    )
    checkpoint = uninterrupted.checkpoint()

    malformed = copy.deepcopy(uninterrupted.get_state())
    malformed["context"]["obscurants_engine"]["clouds"][0]["cloud_type"] = 2
    target = _engine(seed=555_112)
    before = target.checkpoint()
    with pytest.raises(
        ValueError,
        match="cloud_id must match its type",
    ):
        target.set_state(malformed)
    assert target.checkpoint() == before

    resumed = _engine(seed=444_112)
    resumed.restore(checkpoint)
    assert resumed.checkpoint() == checkpoint
    assert (
        obscurants.add_dust(
            Position(300.0, 400.0, 0.0),
            75.0,
        )
        == "dust_00000002"
    )
    assert (
        resumed._ctx.obscurants_engine.add_dust(
            Position(300.0, 400.0, 0.0),
            75.0,
        )
        == "dust_00000002"
    )
    obscurants.update(60.0)
    resumed._ctx.obscurants_engine.update(60.0)
    assert resumed._ctx.obscurants_engine.opacity_at(
        Position(100.0, 200.0, 0.0),
    ) == obscurants.opacity_at(
        Position(100.0, 200.0, 0.0),
    )
    assert resumed.checkpoint() == uninterrupted.checkpoint()
