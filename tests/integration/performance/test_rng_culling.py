"""Phase 118 behavioral red proof for dispatch RNG and culling geometry."""

from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
from typing import Any

import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    PreparedScenario,
    RuntimeSession,
    SimulationRuntimeFactory,
)
from stochastic_warfare.simulation.scenario import CampaignScenarioConfig


ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
SOURCE_LABEL = str(
    (DATA_DIR / "eras" / "ww1" / "scenarios" / "jutland" / "scenario.yaml").resolve(),
)
DIAGNOSTIC_SEED = 118_100


def _unit(
    unit_type: str,
    position: tuple[float, float, float],
    *,
    heading: float,
) -> dict[str, Any]:
    return {
        "unit_type": unit_type,
        "count": 1,
        "position": list(position),
        "overrides": {"heading": heading},
    }


def _scenario(
    *,
    name: str,
    era: str,
    terrain_type: str,
    terrain_size_m: float,
    visibility_m: float,
    blue_units: list[dict[str, Any]],
    red_units: list[dict[str, Any]],
) -> CampaignScenarioConfig:
    return CampaignScenarioConfig.model_validate(
        {
            "name": name,
            "date": ("1916-06-01T12:00:00Z" if era == "ww1" else "2004-11-10T12:00:00Z"),
            "duration_hours": 1.0,
            "era": era,
            "tick_resolution": {
                "strategic_s": 3_600.0,
                "operational_s": 300.0,
                "tactical_s": 5.0,
            },
            "weather_conditions": {
                "visibility_m": visibility_m,
                "precipitation": "none",
            },
            "terrain": {
                "width_m": terrain_size_m,
                "height_m": terrain_size_m,
                "cell_size_m": 100.0,
                "terrain_type": terrain_type,
            },
            "deployment": {"mode": "manual"},
            "sides": [
                {"side": "blue", "units": blue_units},
                {"side": "red", "units": red_units},
            ],
            "objectives": [],
            "victory_conditions": [],
            "calibration_overrides": {
                "defensive_sides": ["blue", "red"],
                "enable_fog_of_war": True,
                "enable_sensing_aware_standoff": True,
                "enable_detection_culling": False,
                "enable_scan_scheduling": False,
                "enable_lod": False,
                "enable_soa": False,
                "enable_parallel_detection": False,
                "target_selection_mode": "closest",
            },
        },
    )


def _prepare_pair(
    config: CampaignScenarioConfig,
    *,
    flag: str,
) -> PreparedScenario:
    return SimulationRuntimeFactory().prepare_config(
        config,
        DATA_DIR,
        (
            AnalysisVariant(
                variant_id=f"phase118-{flag}-off",
                calibration_patch={flag: False},
            ),
            AnalysisVariant(
                variant_id=f"phase118-{flag}-on",
                calibration_patch={flag: True},
            ),
        ),
        source_label=SOURCE_LABEL,
    )


def _build(
    prepared: PreparedScenario,
    variant_id: str,
    *,
    start_recorder: bool = True,
) -> RuntimeSession:
    session = prepared.build(
        variant_id,
        seed=DIAGNOSTIC_SEED,
        max_ticks=8,
        strict_mode=True,
        record_events=True,
    )
    assert session.recorder is not None
    if start_recorder:
        session.recorder.start()
    return session


def _semantic_state(session: RuntimeSession) -> dict[str, Any]:
    """Capture outcome-affecting state without the target flag/receipt fields."""
    fow_state = deepcopy(session.context.fog_of_war.get_state())
    fow_state.pop("rng_state")
    detection_state = deepcopy(session.context.detection_engine.get_state())
    detection_state.pop("rng_state")
    battle_state = deepcopy(session.engine.battle_manager.get_state())
    battle_state.pop("performance_execution_receipt", None)
    return {
        "clock": session.context.clock.get_state(),
        "units": {
            side: [unit.get_state() for unit in sorted(units, key=lambda item: item.entity_id)]
            for side, units in sorted(session.context.units_by_side.items())
        },
        "detection": detection_state,
        "fog_of_war": fow_state,
        "targeting": session.context.tactical_targeting.get_state(),
        "battle": battle_state,
        "campaign": session.engine.campaign_manager.get_state(),
        "victory": session.victory_evaluator.get_state(),
        "recorder": session.recorder.get_state(),
    }


def _rng_state(session: RuntimeSession) -> dict[str, Any]:
    return deepcopy(session.context.rng_manager.get_state())


def _naval_dispatch_scenario() -> CampaignScenarioConfig:
    return _scenario(
        name="Phase 118 probabilistic parallel-dispatch red control",
        era="ww1",
        terrain_type="open_ocean",
        terrain_size_m=10_000.0,
        visibility_m=500.0,
        blue_units=[
            _unit(
                "iron_duke_bb",
                (1_000.0, 1_000.0, 0.0),
                heading=0.0,
            ),
        ],
        red_units=[
            _unit(
                "konig_bb",
                (950.0, 2_100.0, 0.0),
                heading=math.pi,
            ),
            _unit(
                "konig_bb",
                (1_050.0, 2_100.0, 0.0),
                heading=math.pi,
            ),
        ],
    )


def _culling_boundary_scenario(
    *,
    bearing_rad: float,
    target_range_m: float,
) -> CampaignScenarioConfig:
    observer_easting = 10_000.0
    observer_northing = 10_000.0
    boundary_easting = observer_easting + target_range_m * math.sin(bearing_rad)
    boundary_northing = observer_northing + target_range_m * math.cos(bearing_rad)
    return _scenario(
        name=(f"Phase 118 closed-range culling boundary {bearing_rad.hex()} {target_range_m.hex()}"),
        era="modern",
        terrain_type="open_ocean",
        terrain_size_m=25_000.0,
        visibility_m=25_000.0,
        blue_units=[
            _unit(
                "engineer_squad",
                (observer_easting, observer_northing, 0.0),
                heading=bearing_rad,
            ),
        ],
        red_units=[
            _unit(
                "lhd1",
                (boundary_easting, boundary_northing, 0.0),
                heading=math.pi,
            ),
            _unit(
                "lhd1",
                (24_000.0, 24_000.0, 0.0),
                heading=math.pi,
            ),
        ],
    )


def test_parallel_detection_preserves_semantics_rng_and_continuation() -> None:
    """Dispatch choice must not phase-shift production detection or replay."""
    flag = "enable_parallel_detection"
    prepared = _prepare_pair(_naval_dispatch_scenario(), flag=flag)
    serial_id = f"phase118-{flag}-off"
    parallel_id = f"phase118-{flag}-on"

    serial = _build(prepared, serial_id)
    parallel = _build(prepared, parallel_id)
    serial_repeat = _build(prepared, serial_id)
    parallel_repeat = _build(prepared, parallel_id)
    serial_rng_before = _rng_state(serial)
    parallel_rng_before = _rng_state(parallel)

    for session in (serial, parallel, serial_repeat, parallel_repeat):
        assert session.step() is False
        assert (
            sum(
                session.context.detection_engine.get_state()["scan_counts"].values(),
            )
            > 0
        )

    assert _rng_state(serial) != serial_rng_before
    assert _rng_state(parallel) != parallel_rng_before
    assert set(serial.context.fog_of_war.get_state()["world_views"]) == {
        "blue",
        "red",
    }
    assert set(parallel.context.fog_of_war.get_state()["world_views"]) == {
        "blue",
        "red",
    }
    assert serial.engine.checkpoint() == serial_repeat.engine.checkpoint()
    assert parallel.engine.checkpoint() == parallel_repeat.engine.checkpoint()

    serial_checkpoint = serial.engine.checkpoint()
    parallel_checkpoint = parallel.engine.checkpoint()
    serial_resumed = _build(
        prepared,
        serial_id,
        start_recorder=False,
    )
    parallel_resumed = _build(
        prepared,
        parallel_id,
        start_recorder=False,
    )
    serial_resumed.engine.restore(serial_checkpoint)
    parallel_resumed.engine.restore(parallel_checkpoint)
    restored_exact = {
        "serial": serial_resumed.engine.checkpoint() == serial_checkpoint,
        "parallel": (parallel_resumed.engine.checkpoint() == parallel_checkpoint),
    }
    serial_resumed.recorder.start()
    parallel_resumed.recorder.start()

    for session in (serial, parallel, serial_resumed, parallel_resumed):
        assert session.step() is False

    observations = {
        "first_interval_semantics": (_semantic_state(serial_repeat) == _semantic_state(parallel_repeat)),
        "first_interval_rng": (_rng_state(serial_repeat) == _rng_state(parallel_repeat)),
        "serial_restore": restored_exact["serial"],
        "parallel_restore": restored_exact["parallel"],
        "serial_continuation": (serial.engine.checkpoint() == serial_resumed.engine.checkpoint()),
        "parallel_continuation": (parallel.engine.checkpoint() == parallel_resumed.engine.checkpoint()),
        "continued_semantics": (_semantic_state(serial) == _semantic_state(parallel)),
        "continued_rng": _rng_state(serial) == _rng_state(parallel),
    }
    assert observations == dict.fromkeys(observations, True)


@pytest.mark.parametrize(
    ("bearing_rad", "target_range_m", "expected_admitted"),
    (
        pytest.param(0.0, 5_000.0, True, id="north-boundary"),
        pytest.param(math.pi / 2.0, 5_000.0, True, id="east-boundary"),
        pytest.param(math.pi, 5_000.0, True, id="south-boundary"),
        pytest.param(3.0 * math.pi / 2.0, 5_000.0, True, id="west-boundary"),
        pytest.param(math.pi / 64.0, 5_000.0, True, id="inter-vertex-boundary"),
        pytest.param(
            0.0,
            math.nextafter(5_000.0, 0.0),
            True,
            id="adjacent-inside",
        ),
        pytest.param(
            0.0,
            math.nextafter(5_000.0, math.inf),
            False,
            id="adjacent-outside",
        ),
    ),
)
def test_culling_closed_range_boundaries_preserve_state_and_rng(
    bearing_rad: float,
    target_range_m: float,
    expected_admitted: bool,
) -> None:
    """Closed-square preselection must never omit a canonically valid target."""
    flag = "enable_detection_culling"
    prepared = _prepare_pair(
        _culling_boundary_scenario(
            bearing_rad=bearing_rad,
            target_range_m=target_range_m,
        ),
        flag=flag,
    )
    brute_force = _build(prepared, f"phase118-{flag}-off")
    culled = _build(prepared, f"phase118-{flag}-on")

    if target_range_m != 5_000.0:
        # The authored ENU -> geodetic -> ENU load path cannot retain a
        # one-ULP delta around 5 km.  Rebind both fresh runtimes to the exact
        # production Position boundary before either engine steps.  Placing
        # the target south of the loaded observer keeps the subtraction exact
        # at this coordinate magnitude; align the observer heading with that
        # cardinal direction so only the range boundary changes.
        for session in (brute_force, culled):
            loaded_observer = session.context.units_by_side["blue"][0]
            loaded_target = session.context.units_by_side["red"][0]
            loaded_observer.heading = math.pi
            loaded_target.position = Position(
                loaded_observer.position.easting,
                loaded_observer.position.northing - target_range_m,
                loaded_observer.position.altitude,
            )
            rebound_range = math.hypot(
                loaded_target.position.easting - loaded_observer.position.easting,
                loaded_target.position.northing - loaded_observer.position.northing,
            )
            assert rebound_range == target_range_m

    observer = brute_force.context.units_by_side["blue"][0]
    boundary_target = brute_force.context.units_by_side["red"][0]
    attachments = brute_force.context.unit_sensor_attachments[observer.entity_id]
    assert len(attachments) == 1
    sensor = attachments[0].sensor
    assert sensor.sensor_id == "mk1_eyeball"
    assert sensor.effective_range == 5_000.0
    actual_range = math.hypot(
        boundary_target.position.easting - observer.position.easting,
        boundary_target.position.northing - observer.position.northing,
    )
    if target_range_m < sensor.effective_range:
        assert actual_range == math.nextafter(
            sensor.effective_range,
            0.0,
        )
        assert math.nextafter(actual_range, math.inf) == sensor.effective_range
    elif target_range_m > sensor.effective_range:
        assert actual_range == math.nextafter(
            sensor.effective_range,
            math.inf,
        )
        assert math.nextafter(actual_range, 0.0) == sensor.effective_range
    else:
        assert actual_range == sensor.effective_range
    assert (actual_range <= sensor.effective_range) is expected_admitted

    assert brute_force.step() is False
    assert culled.step() is False
    brute_force_witnesses = brute_force.context.fog_of_war.get_current_detection_witnesses(
        "blue",
    )
    culled_witnesses = culled.context.fog_of_war.get_current_detection_witnesses("blue")
    brute_force_admitted = any(witness.target_id == boundary_target.entity_id for witness in brute_force_witnesses)
    assert brute_force_admitted is expected_admitted

    observations = {
        "boundary_witness": any(witness.target_id == boundary_target.entity_id for witness in culled_witnesses)
        is expected_admitted,
        "detection_state": (_semantic_state(brute_force) == _semantic_state(culled)),
        "rng_continuation": (_rng_state(brute_force) == _rng_state(culled)),
    }
    assert observations == dict.fromkeys(observations, True)
