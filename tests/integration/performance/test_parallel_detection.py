"""Production proof for the supported parallel-detection optimization.

The terminal Phase 118 study retired production scan scheduling and LOD.
Their scheduler, tiering, receipt, and archive contracts remain covered by
lower-level tests without presenting either control as a supported runtime
configuration.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.simulation.battle import BattleConfig
from stochastic_warfare.simulation.campaign import CampaignConfig
from stochastic_warfare.simulation.engine import TickResolution
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    PreparedScenario,
    RuntimeSession,
    SimulationRuntimeFactory,
)
from stochastic_warfare.simulation.scenario import CampaignScenarioConfig


ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
CALIBRATION_SCENARIO = DATA_DIR / "scenarios" / "calibration_air_ground" / "scenario.yaml"
SOURCE_LABEL = str(CALIBRATION_SCENARIO.resolve())


def _scenario() -> CampaignScenarioConfig:
    return CampaignScenarioConfig.model_validate(
        {
            "name": "Phase 118 parallel detection proof",
            "date": "2024-03-10T06:00:00Z",
            "duration_hours": 1.0,
            "era": "modern",
            "tick_resolution": {
                "strategic_s": 3_600.0,
                "operational_s": 300.0,
                "tactical_s": 5.0,
            },
            "weather_conditions": {
                "visibility_m": 10_000.0,
                "precipitation": "none",
            },
            "terrain": {
                "width_m": 20_000.0,
                "height_m": 20_000.0,
                "cell_size_m": 1_000.0,
                "terrain_type": "flat_desert",
            },
            "deployment": {"mode": "manual"},
            "sides": [
                {
                    "side": "blue",
                    "units": [
                        {
                            "unit_type": "f16c",
                            "count": 1,
                            "position": [1_000.0, 1_000.0, 0.0],
                        },
                    ],
                },
                {
                    "side": "red",
                    "units": [
                        {
                            "unit_type": "mig29a",
                            "count": 1,
                            "position": [1_000.0, 6_001.0, 0.0],
                        },
                    ],
                },
            ],
            "objectives": [],
            "victory_conditions": [],
            "behavior_rules": {
                "blue": {"hold_position": True},
                "red": {"hold_position": True},
            },
            "calibration_overrides": {
                "defensive_sides": ["blue", "red"],
                "enable_detection_culling": False,
                "enable_scan_scheduling": False,
                "enable_lod": False,
                "enable_soa": False,
                "enable_parallel_detection": False,
                "enable_fog_of_war": True,
                "enable_sensing_aware_standoff": True,
                "roe_level": "WEAPONS_HOLD",
                "target_selection_mode": "closest",
            },
        },
    )


def _prepare(*variants: AnalysisVariant) -> PreparedScenario:
    return SimulationRuntimeFactory().prepare_config(
        _scenario(),
        DATA_DIR,
        variants,
        source_label=SOURCE_LABEL,
    )


def _build(
    prepared: PreparedScenario,
    variant_id: str,
) -> RuntimeSession:
    session = prepared.build(
        variant_id,
        seed=118_014,
        max_ticks=2,
        campaign_config=CampaignConfig(
            engagement_detection_range_m=10_000.0,
            enable_strategic_movement=False,
            enable_maintenance=False,
            enable_supply_network=False,
        ),
        battle_config=BattleConfig(
            engagement_range_m=10_000.0,
            morale_check_interval=12,
        ),
        strict_mode=True,
    )
    assert session.engine.resolution is TickResolution.TACTICAL
    assert len(session.engine.battle_manager.active_battles) == 1
    return session


def _detection_rng_state(session: RuntimeSession) -> dict[str, Any]:
    return copy.deepcopy(
        session.context.rng_manager.get_stream(
            ModuleId.DETECTION,
        ).bit_generator.state,
    )


def _indexed_transcript_state(
    session: RuntimeSession,
) -> tuple[int, int, str]:
    manager = session.context.rng_manager
    return (
        manager.indexed_fow_committed_interval_count,
        manager.indexed_fow_committed_entry_count,
        manager.indexed_fow_transcript_digest_hex,
    )


def test_production_parallel_dispatch_preserves_fow_transaction_and_detection_rng() -> None:
    """Dispatch choice changes execution only, never FOW publication or RNG."""
    serial_id = "phase118-production-fow-serial"
    threaded_id = "phase118-production-fow-threaded"
    prepared = _prepare(
        AnalysisVariant(
            variant_id=serial_id,
            calibration_patch={"enable_parallel_detection": False},
        ),
        AnalysisVariant(
            variant_id=threaded_id,
            calibration_patch={"enable_parallel_detection": True},
        ),
    )
    sessions = {variant_id: _build(prepared, variant_id) for variant_id in (serial_id, threaded_id)}
    detection_rng_before = {variant_id: _detection_rng_state(session) for variant_id, session in sessions.items()}

    for session in sessions.values():
        assert session.step() is False

    serial = sessions[serial_id]
    threaded = sessions[threaded_id]
    serial_receipt = serial.performance_execution_receipt()
    threaded_receipt = threaded.performance_execution_receipt()

    assert serial.context.fog_of_war.get_state() == threaded.context.fog_of_war.get_state()
    assert serial.context.fog_of_war.cadence.get_state() == threaded.context.fog_of_war.cadence.get_state()
    assert _indexed_transcript_state(serial) == _indexed_transcript_state(
        threaded,
    )
    assert serial.fow_indexed_interval_record() == threaded.fow_indexed_interval_record()
    assert serial_receipt.fow == threaded_receipt.fow
    assert serial_receipt.lod == threaded_receipt.lod
    assert serial_receipt.dispatch.sequential_intervals == 1
    assert threaded_receipt.dispatch.parallel_intervals == 1
    for variant_id, session in sessions.items():
        assert _detection_rng_state(session) == detection_rng_before[variant_id]
