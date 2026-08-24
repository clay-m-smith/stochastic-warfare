"""Production checkpoint controls for Phase 116 fog-of-war contacts."""

from __future__ import annotations

import copy
import math
from collections import Counter
from collections.abc import Callable
from typing import Any

import numpy as np
import pytest

from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.detection.detection import DetectionEngine
from stochastic_warfare.detection.fog_of_war import DataLinkConfig
from stochastic_warfare.detection.identification import IdentificationEngine
from stochastic_warfare.simulation.force_builder import (
    RuntimeUnitSpec,
    UnitInstanceOverrides,
)
from stochastic_warfare.simulation.battle import BattleConfig
from stochastic_warfare.simulation.runtime import PreparedScenario, RuntimeSession
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    register_dynamic_units,
)
from stochastic_warfare.simulation.tactical_targeting import ContactSource
from stochastic_warfare.simulation.targeting_exposure import (
    TargetingExposureBundle,
    capture_targeting_exposure,
)
from tests.integration.targeting.test_targeting_controls import (
    _prepare,
    _three_side_parallel_scenario,
)
from tests.integration.checkpoint.test_targeting_continuation import (
    VARIANT_ID as TARGETING_VARIANT_ID,
    _prepare_targeting_scenario,
    _versionless_pristine_checkpoint,
)


VARIANT_ID = "phase116-fow-contact-checkpoint"
SIDES = ("blue", "green", "red")


def _phase116_config() -> CampaignScenarioConfig:
    """Freeze the existing three-side probe while retaining live battles."""
    raw = _three_side_parallel_scenario().model_dump(mode="python")
    raw["calibration_overrides"]["defensive_sides"] = list(SIDES)
    return CampaignScenarioConfig.model_validate(raw)


def _build_probe(
    prepared: PreparedScenario,
    *,
    seed: int,
) -> RuntimeSession:
    session = prepared.build(
        VARIANT_ID,
        seed=seed,
        max_ticks=140,
        strict_mode=True,
        record_events=True,
    )
    assert session.recorder is not None
    session.recorder.start()
    # Keep all three production battles live without replacing their catalog
    # sensors, loadouts, targeting coordinator, movement, morale, or recorder.
    for attachments in session.context.unit_weapons.values():
        for attachment in attachments:
            for ammo_id in attachment.weapon.ammo_state.rounds_by_type:
                attachment.weapon.ammo_state.rounds_by_type[ammo_id] = 0
    return session


def _prime_checkpoint(
    prepared: PreparedScenario,
    *,
    seed: int = 91_115,
) -> tuple[RuntimeSession, bytes]:
    session = _build_probe(prepared, seed=seed)
    session.context.units_by_side["red"][0].heading = math.pi
    for _ in range(3):
        assert session.step() is False
    return session, session.engine.checkpoint()


def _contact_topology(session: RuntimeSession) -> dict[str, dict[str, tuple[Any, ...]]]:
    return {
        side: {
            contact_id: (
                contact.track.track_id,
                contact.track.status.name,
                contact.track.hits,
                contact.track.state.last_update_time,
                contact.first_detected_time,
                contact.last_sensor_contact_time,
                tuple(contact.reporting_sensors),
            )
            for contact_id, contact in sorted(
                session.context.fog_of_war.get_world_view(side).contacts.items(),
            )
        }
        for side in SIDES
    }


def _capture_exposure(session: RuntimeSession) -> TargetingExposureBundle:
    return capture_targeting_exposure(
        engine_tick=session.context.clock.tick_count,
        runtime=session.context.tactical_targeting,
        fog_of_war=session.context.fog_of_war,
        fog_of_war_enabled=True,
        viewer_sides=SIDES,
    )


def _assert_fusion_aliases(session: RuntimeSession) -> None:
    fog = session.context.fog_of_war
    for side in SIDES:
        fusion_tracks = fog.intel_fusion.get_tracks(side)
        for contact in fog.get_world_view(side).contacts.values():
            assert contact.track is fusion_tracks[contact.track.track_id]


def _fow_binding_observation(session: RuntimeSession) -> dict[str, Any]:
    """Capture mutable FOW-owner state without invoking its binding guard."""
    context = session.context
    fog = context.fog_of_war
    identification = fog._identification
    return {
        "clock": context.clock.get_state(),
        "rng_manager": copy.deepcopy(context.rng_manager.get_state()),
        "context_detection": copy.deepcopy(
            context.detection_engine.get_state(),
        ),
        "world_views": {side: view.get_state() for side, view in sorted(fog._world_views.items())},
        "witnesses": fog.get_current_detection_witnesses(),
        "fusion": copy.deepcopy(fog.intel_fusion.get_state()),
        "deception": copy.deepcopy(fog._deception.get_state()),
        "targeting": context.tactical_targeting.get_state(),
        "owner_ids": {
            "context_detection": id(context.detection_engine),
            "fow_detection": id(fog._detection),
            "fow_rng": id(fog._rng),
            "fow_estimator_rng": id(fog._estimator._rng),
            "fusion_rng": id(fog._intel_fusion._rng),
            "fusion_estimator_rng": id(
                fog._intel_fusion._estimator._rng,
            ),
            "deception_rng": id(fog._deception._rng),
            "identification": (None if identification is None else id(identification)),
            "identification_rng": (None if identification is None else id(identification._rng)),
        },
    }


def _assert_disabled_fow_state(session: RuntimeSession) -> None:
    assert session.context.cal_flat["enable_fog_of_war"] is False
    fog_state = session.context.fog_of_war.get_state()
    assert fog_state["world_views"] == {}
    assert fog_state["current_detection_witnesses"] == {}
    assert session.context.fog_of_war.get_current_detection_witnesses() == ()


def _assert_disabled_targeting_interval(session: RuntimeSession) -> None:
    interval = session.context.tactical_targeting.prepared_interval
    assert interval is not None
    assert interval.fog_of_war_enabled is False
    decisions = tuple(
        decision for picture in session.context.tactical_targeting.latest_pictures() for decision in picture.decisions
    )
    assert decisions
    assert all(
        decision.fog_of_war_enabled is False and decision.contact_source is ContactSource.NON_FOW_LOCAL_OBSERVATION
        for decision in decisions
    )


def _set_detection_headings(
    session: RuntimeSession,
    *,
    facing: bool,
) -> None:
    session.context.units_by_side["blue"][0].heading = 0.0 if facing else math.pi
    session.context.units_by_side["green"][0].heading = 0.0 if facing else math.pi
    session.context.units_by_side["red"][0].heading = math.pi if facing else 0.0


def _step_pair(
    control: RuntimeSession,
    resumed: RuntimeSession,
    count: int,
) -> None:
    for _ in range(count):
        assert control.step() is False
        assert resumed.step() is False


def _contact_statuses(session: RuntimeSession) -> dict[str, dict[str, str]]:
    return {
        side: {
            contact_id: contact.track.status.name
            for contact_id, contact in sorted(
                session.context.fog_of_war.get_world_view(side).contacts.items(),
            )
        }
        for side in SIDES
    }


def _fusion_statuses(session: RuntimeSession) -> dict[str, dict[str, str]]:
    return {
        side: {
            track_id: track.status.name
            for track_id, track in sorted(
                session.context.fog_of_war.intel_fusion.get_tracks(side).items(),
            )
        }
        for side in SIDES
    }


def test_nonempty_current_fow_checkpoint_restores_exactly_in_fresh_runtime() -> None:
    """A fresh runtime retains current contacts and their consumers exactly."""
    prepared = _prepare(_phase116_config(), variant_id=VARIANT_ID)
    source, checkpoint = _prime_checkpoint(prepared)
    expected_topology = {
        "blue": {
            "red_iron_duke_bb_0000": (
                "fow-track-0001",
                "CONFIRMED",
                3,
                15.0,
                5.0,
                15.0,
                ("binoculars_ww1",),
            ),
        },
        "green": {
            "red_iron_duke_bb_0000": (
                "fow-track-0001",
                "CONFIRMED",
                3,
                15.0,
                5.0,
                15.0,
                ("binoculars_ww1",),
            ),
        },
        "red": {
            "blue_iron_duke_bb_0000": (
                "fow-track-0001",
                "CONFIRMED",
                3,
                15.0,
                5.0,
                15.0,
                ("binoculars_ww1",),
            ),
            "green_iron_duke_bb_0000": (
                "fow-track-0002",
                "CONFIRMED",
                3,
                15.0,
                5.0,
                15.0,
                ("binoculars_ww1",),
            ),
        },
    }
    assert _contact_topology(source) == expected_topology
    expected_witnesses = source.context.fog_of_war.get_current_detection_witnesses()
    assert len(expected_witnesses) == 4
    expected_targeting = source.context.tactical_targeting.get_state()
    expected_exposure = _capture_exposure(source)

    resumed = _build_probe(prepared, seed=116_999)
    assert resumed.context.fog_of_war is not source.context.fog_of_war
    assert resumed.context.rng_manager is not source.context.rng_manager
    resumed.engine.restore(checkpoint)

    assert _contact_topology(resumed) == expected_topology
    resumed_witnesses = resumed.context.fog_of_war.get_current_detection_witnesses()
    assert resumed_witnesses == expected_witnesses
    assert all(
        resumed_witness is not source_witness
        for resumed_witness, source_witness in zip(
            resumed_witnesses,
            expected_witnesses,
            strict=True,
        )
    )
    assert resumed.context.tactical_targeting.get_state() == expected_targeting
    assert _capture_exposure(resumed) == expected_exposure
    _assert_fusion_aliases(source)
    _assert_fusion_aliases(resumed)
    assert resumed.engine.checkpoint() == checkpoint

    assert source.step() is False
    assert resumed.step() is False
    expected_refreshed = {
        side: {
            contact_id: (values[0], "CONFIRMED", 4, 20.0, values[4], 20.0, values[6])
            for contact_id, values in contacts.items()
        }
        for side, contacts in expected_topology.items()
    }
    assert _contact_topology(source) == expected_refreshed
    assert _contact_topology(resumed) == expected_refreshed
    assert source.engine.checkpoint() == resumed.engine.checkpoint()


def test_production_capture_rejects_state_equal_detached_contact_track() -> None:
    """A serialized-equal track copy cannot impersonate the fusion owner."""
    prepared = _prepare(_phase116_config(), variant_id=VARIANT_ID)
    source, valid_checkpoint = _prime_checkpoint(prepared)
    target = _build_probe(prepared, seed=116_117)
    target.engine.restore(valid_checkpoint)
    assert target.engine.checkpoint() == source.engine.checkpoint()

    fog = target.context.fog_of_war
    contact = fog.get_world_view("blue").contacts["red_iron_duke_bb_0000"]
    fusion_track = fog.intel_fusion.get_tracks("blue")[contact.track.track_id]
    original_track = contact.track
    assert original_track is fusion_track
    detached_track = copy.deepcopy(original_track)
    assert detached_track is not fusion_track
    assert detached_track.get_state() == fusion_track.get_state()
    contact.track = detached_track

    contact_before = copy.deepcopy(contact.get_state())
    fusion_before = copy.deepcopy(fusion_track.get_state())
    clock_before = target.context.clock.get_state()
    rng_before = copy.deepcopy(target.context.rng_manager.get_state())
    with pytest.raises(ValueError, match="exact fusion-owned track"):
        target.engine.checkpoint()
    assert contact.track is detached_track
    assert contact.get_state() == contact_before
    assert fusion_track.get_state() == fusion_before
    assert target.context.clock.get_state() == clock_before
    assert target.context.rng_manager.get_state() == rng_before

    contact.track = original_track
    assert target.engine.checkpoint() == valid_checkpoint
    target.engine.restore(valid_checkpoint)
    assert target.engine.checkpoint() == valid_checkpoint
    _assert_fusion_aliases(target)


@pytest.mark.parametrize(
    ("owner_name", "capture_match", "restore_match"),
    (
        (
            "detection_owner",
            "context DetectionEngine owner",
            "context DetectionEngine owner",
        ),
        (
            "context_detection_rng",
            "DetectionEngine must share",
            "DetectionEngine must use RNGManager's DETECTION generator",
        ),
        (
            "fow_rng",
            "must share FogOfWarManager's RNG",
            "FogOfWarManager must use RNGManager's DETECTION generator",
        ),
        (
            "fow_estimator_rng",
            "FogOfWarManager StateEstimator must share",
            "FogOfWarManager StateEstimator must share",
        ),
        (
            "fusion_rng",
            "IntelFusionEngine must share",
            "IntelFusionEngine must share",
        ),
        (
            "fusion_estimator_rng",
            "IntelFusionEngine StateEstimator must share",
            "IntelFusionEngine StateEstimator must share",
        ),
        (
            "deception_rng",
            "DeceptionEngine must share",
            "DeceptionEngine must share",
        ),
        (
            "identification_rng",
            "IdentificationEngine must share",
            "IdentificationEngine must share",
        ),
    ),
)
def test_factory_runtime_rejects_detached_fow_owner_and_rng_identity(
    owner_name: str,
    capture_match: str,
    restore_match: str,
) -> None:
    """Every factory-owned DETECTION identity is exact and fail-closed."""
    prepared = _prepare(_phase116_config(), variant_id=VARIANT_ID)
    source, valid_checkpoint = _prime_checkpoint(prepared)
    target = _build_probe(prepared, seed=216_117)
    target.engine.restore(valid_checkpoint)
    baseline = target.engine.checkpoint()
    assert baseline == source.engine.checkpoint()

    context = target.context
    fog = context.fog_of_war
    authoritative_rng = context.rng_manager.get_stream(ModuleId.DETECTION)
    detached_rng = np.random.default_rng()
    detached_rng.bit_generator.state = copy.deepcopy(
        authoritative_rng.bit_generator.state,
    )
    assert detached_rng is not authoritative_rng
    assert detached_rng.bit_generator.state == authoritative_rng.bit_generator.state

    repair: Callable[[], None]
    if owner_name == "detection_owner":
        original_owner = fog._detection
        detached_owner = DetectionEngine(rng=authoritative_rng)
        detached_owner.set_state(
            copy.deepcopy(context.detection_engine.get_state()),
        )
        fog._detection = detached_owner
        repair = lambda: setattr(fog, "_detection", original_owner)
    elif owner_name == "context_detection_rng":
        original_rng = context.detection_engine._rng
        context.detection_engine._rng = detached_rng
        repair = lambda: setattr(
            context.detection_engine,
            "_rng",
            original_rng,
        )
    elif owner_name == "fow_rng":
        original_rng = fog._rng
        fog._rng = detached_rng
        repair = lambda: setattr(fog, "_rng", original_rng)
    elif owner_name == "fow_estimator_rng":
        original_rng = fog._estimator._rng
        fog._estimator._rng = detached_rng
        repair = lambda: setattr(fog._estimator, "_rng", original_rng)
    elif owner_name == "fusion_rng":
        original_rng = fog._intel_fusion._rng
        fog._intel_fusion._rng = detached_rng
        repair = lambda: setattr(
            fog._intel_fusion,
            "_rng",
            original_rng,
        )
    elif owner_name == "fusion_estimator_rng":
        original_rng = fog._intel_fusion._estimator._rng
        fog._intel_fusion._estimator._rng = detached_rng
        repair = lambda: setattr(
            fog._intel_fusion._estimator,
            "_rng",
            original_rng,
        )
    elif owner_name == "deception_rng":
        original_rng = fog._deception._rng
        fog._deception._rng = detached_rng
        repair = lambda: setattr(fog._deception, "_rng", original_rng)
    else:
        assert owner_name == "identification_rng"
        original_identification = fog._identification
        fog._identification = IdentificationEngine(rng=authoritative_rng)
        fog._identification._rng = detached_rng
        repair = lambda: setattr(
            fog,
            "_identification",
            original_identification,
        )

    corrupted_before = _fow_binding_observation(target)
    with pytest.raises(ValueError, match=capture_match):
        target.engine.checkpoint()
    assert _fow_binding_observation(target) == corrupted_before

    with pytest.raises(ValueError, match=restore_match):
        target.engine.restore(valid_checkpoint)
    assert _fow_binding_observation(target) == corrupted_before

    repair()
    assert target.engine.checkpoint() == baseline
    target.engine.restore(valid_checkpoint)
    assert target.engine.checkpoint() == valid_checkpoint
    _assert_fusion_aliases(target)


def test_fow_disabled_runtime_stays_empty_and_uses_local_observations() -> None:
    """The production configuration gate bypasses FOW before and after restore."""
    prepared = _prepare_targeting_scenario(
        fog_of_war=False,
        separation_m=800.0,
        northward_target=True,
    )
    source = prepared.build(
        TARGETING_VARIANT_ID,
        seed=115,
        max_ticks=10,
        strict_mode=True,
    )
    _assert_disabled_fow_state(source)
    assert source.context.tactical_targeting.prepared_interval is None
    assert source.step() is False
    _assert_disabled_fow_state(source)
    _assert_disabled_targeting_interval(source)
    checkpoint = source.engine.checkpoint()

    resumed = prepared.build(
        TARGETING_VARIANT_ID,
        seed=116_118,
        max_ticks=10,
        strict_mode=True,
    )
    _assert_disabled_fow_state(resumed)
    resumed.engine.restore(checkpoint)
    assert resumed.engine.checkpoint() == checkpoint
    _assert_disabled_fow_state(resumed)
    _assert_disabled_targeting_interval(resumed)

    assert source.step() is False
    assert resumed.step() is False
    _assert_disabled_fow_state(source)
    _assert_disabled_fow_state(resumed)
    _assert_disabled_targeting_interval(source)
    _assert_disabled_targeting_interval(resumed)
    assert resumed.engine.checkpoint() == source.engine.checkpoint()


def test_fow_disabled_explicit_empty_views_restore_exactly() -> None:
    """Publicly allocated empty views are not ordinary contact evidence."""
    prepared = _prepare_targeting_scenario(
        fog_of_war=False,
        separation_m=800.0,
        northward_target=True,
    )
    source = prepared.build(
        TARGETING_VARIANT_ID,
        seed=115,
        max_ticks=10,
        strict_mode=True,
    )
    fog = source.context.fog_of_war
    assert fog.get_world_view("british").contacts == {}
    assert fog.get_world_view("german").contacts == {}
    checkpoint = source.engine.checkpoint()

    resumed = prepared.build(
        TARGETING_VARIANT_ID,
        seed=116_121,
        max_ticks=10,
        strict_mode=True,
    )
    resumed.engine.restore(checkpoint)

    assert resumed.engine.checkpoint() == checkpoint
    state = resumed.context.fog_of_war.get_state()
    assert state["world_views"] == {
        "british": {
            "side": "british",
            "contacts": {},
            "last_update_time": 0.0,
        },
        "german": {
            "side": "german",
            "contacts": {},
            "last_update_time": 0.0,
        },
    }
    assert state["current_detection_witnesses"] == {}


def test_fow_contacts_survive_dynamic_registration_and_restore() -> None:
    """Durable contacts remain valid across a between-interval roster change."""
    prepared = _prepare_targeting_scenario(
        fog_of_war=True,
        separation_m=800.0,
        northward_target=True,
    )
    source = prepared.build(
        TARGETING_VARIANT_ID,
        seed=115,
        max_ticks=10,
        strict_mode=True,
    )
    assert source.step() is False
    fog_before = source.context.fog_of_war.get_state()
    assert any(view["contacts"] for view in fog_before["world_views"].values())
    assert fog_before["current_detection_witnesses"]
    assert source.context.tactical_targeting.prepared_interval is not None

    force_builder = source.context.force_builder
    assert force_builder is not None
    reinforcement = force_builder.build_units(
        (
            RuntimeUnitSpec(
                entity_id="reinforce_british_phase116_fow_0000",
                unit_type="mark_iv_tank",
                side="british",
                position=Position(1_500.0, 1_500.0, 0.0),
                overrides=UnitInstanceOverrides(),
            ),
        ),
    )[0]

    register_dynamic_units(source.context, [reinforcement])

    assert reinforcement in source.context.units_by_side["british"]
    assert source.context.tactical_targeting.prepared_interval is None
    assert source.context.tactical_targeting.latest_pictures() == ()
    assert source.context.fog_of_war.get_state() == fog_before
    checkpoint = source.engine.checkpoint()

    resumed = prepared.build(
        TARGETING_VARIANT_ID,
        seed=116_120,
        max_ticks=10,
        strict_mode=True,
    )
    resumed.engine.restore(checkpoint)

    assert resumed.engine.checkpoint() == checkpoint
    assert reinforcement.entity_id in {unit.entity_id for unit in resumed.context.units_by_side["british"]}
    assert resumed.context.tactical_targeting.prepared_interval is None
    assert resumed.context.tactical_targeting.latest_pictures() == ()
    for side, view in resumed.context.fog_of_war._world_views.items():
        fusion_tracks = resumed.context.fog_of_war._intel_fusion._tracks[side]
        assert all(contact.track is fusion_tracks[contact.track.track_id] for contact in view.contacts.values())

    assert source.step() is False
    assert resumed.step() is False
    assert resumed.engine.checkpoint() == source.engine.checkpoint()


def test_fow_disabled_restore_rejects_injected_ordinary_state_atomically() -> None:
    """The disabled production gate cannot inherit enabled contact history."""
    enabled_prepared = _prepare(_phase116_config(), variant_id=VARIANT_ID)
    enabled, _ = _prime_checkpoint(enabled_prepared, seed=116_501)
    enabled_state = enabled.engine.get_state()
    enabled_fow = enabled_state["context"]["fog_of_war"]
    assert any(view["contacts"] for view in enabled_fow["world_views"].values())
    assert any(enabled_fow["current_detection_witnesses"].values())

    disabled_raw = _phase116_config().model_dump(mode="python")
    disabled_raw["calibration_overrides"]["enable_fog_of_war"] = False
    disabled_prepared = _prepare(
        CampaignScenarioConfig.model_validate(disabled_raw),
        variant_id=VARIANT_ID,
    )
    target = _build_probe(disabled_prepared, seed=116_502)
    for _ in range(3):
        assert target.step() is False
    valid = target.engine.get_state()
    invalid = copy.deepcopy(valid)
    injected = copy.deepcopy(enabled_fow)
    target_fow = valid["context"]["fog_of_war"]
    injected["rng_state"] = copy.deepcopy(target_fow["rng_state"])
    injected["intel_fusion"]["rng_state"] = copy.deepcopy(
        target_fow["intel_fusion"]["rng_state"],
    )
    # Keep the Phase 118 cadence/scan owners coherent with the disabled
    # target. The deliberate corruption is ordinary FOW contact history,
    # which must reach the disabled-feature semantic guard.
    injected["scan_counts"] = copy.deepcopy(target_fow["scan_counts"])
    injected["cadence"] = copy.deepcopy(target_fow["cadence"])
    invalid["context"]["fog_of_war"] = injected
    before = target.engine.checkpoint()

    with pytest.raises(ValueError, match="disabled.*fog-of-war"):
        target.engine.set_state(invalid)
    assert target.engine.checkpoint() == before

    target.engine.set_state(valid)
    assert target.engine.get_state() == valid
    _assert_disabled_fow_state(target)


def test_versionless_production_restore_accepts_bounded_nonzero_ordinary_contacts() -> None:
    """The bounded legacy path retains coherent contact/track history."""
    prepared = _prepare_targeting_scenario(
        fog_of_war=True,
        separation_m=800.0,
        northward_target=True,
    )
    pristine = prepared.build(
        TARGETING_VARIANT_ID,
        seed=115,
        max_ticks=10,
        strict_mode=True,
    )
    pristine_checkpoint = pristine.engine.checkpoint()
    valid_versionless = _versionless_pristine_checkpoint(
        pristine.engine.get_state(),
    )
    assert "checkpoint_version" not in valid_versionless

    active = prepared.build(
        TARGETING_VARIANT_ID,
        seed=115,
        max_ticks=10,
        strict_mode=True,
    )
    assert active.step() is False
    legacy_fow = copy.deepcopy(
        active.engine.get_state()["context"]["fog_of_war"],
    )
    legacy_fow.pop("current_detection_witnesses")
    legacy_fow.pop("observer_track_supports")
    legacy_fow.pop("scan_counts")
    legacy_fow.pop("cadence")
    assert any(view["contacts"] for view in legacy_fow["world_views"].values())

    # Keep the legacy tick-zero envelope internally coherent so the only
    # unsupported content is the ordinary-contact topology itself.
    for view in legacy_fow["world_views"].values():
        view["last_update_time"] = 0.0
        for contact in view["contacts"].values():
            contact["first_detected_time"] = 0.0
            contact["last_sensor_contact_time"] = 0.0
            contact["track"]["state"]["last_update_time"] = 0.0
    for tracks in legacy_fow["intel_fusion"]["tracks"].values():
        for track in tracks.values():
            track["state"]["last_update_time"] = 0.0
    pristine_detection_rng = copy.deepcopy(
        valid_versionless["context"]["rng"]["streams"][ModuleId.DETECTION.value],
    )
    legacy_fow["rng_state"] = copy.deepcopy(pristine_detection_rng)
    legacy_fow["intel_fusion"]["rng_state"] = copy.deepcopy(
        pristine_detection_rng,
    )

    invalid_versionless = copy.deepcopy(valid_versionless)
    invalid_versionless["context"]["fog_of_war"] = legacy_fow
    assert set(legacy_fow) == {"world_views", "rng_state", "intel_fusion"}

    target = prepared.build(
        TARGETING_VARIANT_ID,
        seed=116_119,
        max_ticks=10,
        strict_mode=True,
    )
    target.engine.set_state(invalid_versionless)
    restored_fow = target.context.fog_of_war.get_state()
    assert restored_fow["world_views"] == legacy_fow["world_views"]
    assert restored_fow["intel_fusion"] == legacy_fow["intel_fusion"]
    assert restored_fow["current_detection_witnesses"] == {}
    assert restored_fow["scan_counts"] == {}
    assert restored_fow["cadence"] == {
        "schema_version": 2,
        "committed_ordinal": 0,
        "complete_from_tick_zero": False,
        "attachments": [],
        "native_phase_assignments": [],
        "native_phase_assignments_sha256": (
            "07e1061e806688ca185002ae49978fb2aafe1a5bc9971afc52b6ecb88949a4b2"
        ),
    }
    _assert_fusion_aliases(target)

    lost_history = copy.deepcopy(legacy_fow)
    for view in lost_history["world_views"].values():
        view["contacts"].clear()
    for tracks in lost_history["intel_fusion"]["tracks"].values():
        for track in tracks.values():
            track["status"] = 4
    invalid_versionless["context"]["fog_of_war"] = lost_history
    target.engine.set_state(invalid_versionless)
    restored_lost_history = target.context.fog_of_war.get_state()
    assert all(not view["contacts"] for view in restored_lost_history["world_views"].values())
    assert restored_lost_history["intel_fusion"] == lost_history["intel_fusion"]
    assert restored_lost_history["scan_counts"] == {}
    assert restored_lost_history["cadence"]["complete_from_tick_zero"] is False

    incomplete_checkpoint = target.engine.checkpoint()
    with pytest.raises(ValueError, match="completeness cannot be promoted"):
        target.engine.restore(pristine_checkpoint)
    assert target.engine.checkpoint() == incomplete_checkpoint

    modern_target = prepared.build(
        TARGETING_VARIANT_ID,
        seed=116_120,
        max_ticks=10,
        strict_mode=True,
    )
    modern_target.engine.restore(pristine_checkpoint)
    assert modern_target.engine.checkpoint() == pristine_checkpoint

    pristine_legacy_target = prepared.build(
        TARGETING_VARIANT_ID,
        seed=116_121,
        max_ticks=10,
        strict_mode=True,
    )
    pristine_legacy_target.engine.set_state(valid_versionless)
    migrated_pristine = pristine_legacy_target.engine.get_state()
    assert migrated_pristine["checkpoint_version"] == 118
    assert migrated_pristine["context"]["fog_of_war"]["cadence"]["complete_from_tick_zero"] is False
    assert migrated_pristine["context"]["rng"]["indexed_fow"]["complete_from_tick_zero"] is False
    assert migrated_pristine["battle"]["performance_execution_receipt"]["complete_from_tick_zero"] is False


def _assert_fow_targeting_consumers(session: RuntimeSession) -> None:
    """Require one exact FOW decision to drive movement and engagement."""
    runtime = session.context.tactical_targeting
    decision = next(
        decision
        for picture in runtime.latest_pictures()
        for decision in picture.decisions
        if decision.contact_source is ContactSource.FOW_OBSERVER_WITNESS
    )
    assert decision.can_hold
    revalidation = runtime.engagement_revalidation_for(
        engine_tick=decision.engine_tick,
        battle_id=decision.battle_id,
        shooter_id=decision.shooter_id,
    )
    assert revalidation is not None
    assert revalidation.target_id == decision.target_id
    assert revalidation.revalidation_passed
    movement_state = session.context.movement_diagnostics.get_state()["units"][decision.shooter_id]
    observation = movement_state["recent_observations"][-1]
    assert observation["reason"] == "ENGINE_WEAPON_STANDOFF"
    assert observation["targeting_decision"]["contact_source"] == ("FOW_OBSERVER_WITNESS")
    assert observation["targeting_decision"]["target_id"] == (decision.target_id)


def test_restored_fow_decision_drives_movement_and_engagement_consumers() -> None:
    """Restored current evidence remains outcome-affecting in production."""
    prepared = _prepare_targeting_scenario(
        fog_of_war=True,
        separation_m=800.0,
        northward_target=True,
    )
    source = prepared.build(
        TARGETING_VARIANT_ID,
        seed=115,
        max_ticks=10,
        strict_mode=True,
    )
    british = source.context.units_by_side["british"][0]
    initial_position = british.position
    assert source.step() is False
    assert british.position == initial_position
    _assert_fow_targeting_consumers(source)
    checkpoint = source.engine.checkpoint()

    resumed = prepared.build(
        TARGETING_VARIANT_ID,
        seed=116_999,
        max_ticks=10,
        strict_mode=True,
    )
    resumed.engine.restore(checkpoint)
    assert resumed.engine.checkpoint() == checkpoint
    _assert_fow_targeting_consumers(resumed)

    assert source.step() is False
    assert resumed.step() is False
    _assert_fow_targeting_consumers(source)
    _assert_fow_targeting_consumers(resumed)
    assert resumed.engine.checkpoint() == source.engine.checkpoint()


def test_contacts_continue_through_coast_loss_redetection_and_events() -> None:
    """Fresh continuation is exact across the complete ordinary lifecycle."""
    prepared = _prepare(_phase116_config(), variant_id=VARIANT_ID)
    control, checkpoint = _prime_checkpoint(prepared)
    resumed = _build_probe(prepared, seed=216_116)
    resumed.engine.restore(checkpoint)

    # A current detection must update the restored fusion-owned track instead
    # of allocating a new public ordinal beside an unreachable predecessor.
    _step_pair(control, resumed, 1)
    assert control.context.clock.elapsed.total_seconds() == 20.0
    assert _contact_topology(control) == _contact_topology(resumed)
    assert {
        side: {contact_id: (values[0], values[2], values[3]) for contact_id, values in contacts.items()}
        for side, contacts in _contact_topology(control).items()
    } == {
        "blue": {"red_iron_duke_bb_0000": ("fow-track-0001", 4, 20.0)},
        "green": {"red_iron_duke_bb_0000": ("fow-track-0001", 4, 20.0)},
        "red": {
            "blue_iron_duke_bb_0000": ("fow-track-0001", 4, 20.0),
            "green_iron_duke_bb_0000": ("fow-track-0002", 4, 20.0),
        },
    }
    assert control.engine.checkpoint() == resumed.engine.checkpoint()

    _set_detection_headings(control, facing=False)
    _set_detection_headings(resumed, facing=False)

    # The lifecycle uses strict greater-than boundaries.  Age 300s remains
    # CONFIRMED; age 305s coasts.  Age 600s remains COASTING; age 605s is LOST
    # and removed from the ordinary side picture while fusion retains history.
    _step_pair(control, resumed, 60)
    assert control.context.clock.elapsed.total_seconds() == 320.0
    assert _contact_statuses(control) == {
        "blue": {"red_iron_duke_bb_0000": "CONFIRMED"},
        "green": {"red_iron_duke_bb_0000": "CONFIRMED"},
        "red": {
            "blue_iron_duke_bb_0000": "CONFIRMED",
            "green_iron_duke_bb_0000": "CONFIRMED",
        },
    }
    assert control.engine.checkpoint() == resumed.engine.checkpoint()

    _step_pair(control, resumed, 1)
    assert control.context.clock.elapsed.total_seconds() == 325.0
    assert set(status for contacts in _contact_statuses(control).values() for status in contacts.values()) == {
        "COASTING"
    }
    assert control.engine.checkpoint() == resumed.engine.checkpoint()

    # The current witness cache is empty after a missed interval, but each
    # older contact's reporting sensor must still resolve to a real staged
    # reporting-side attachment.
    coasting_state = control.engine.get_state()
    assert all(
        not witnesses for witnesses in coasting_state["context"]["fog_of_war"]["current_detection_witnesses"].values()
    )
    coasting_checkpoint = control.engine.checkpoint()
    coasting_target = _build_probe(prepared, seed=316_325)
    coasting_target.engine.restore(coasting_checkpoint)
    assert coasting_target.engine.checkpoint() == coasting_checkpoint
    _assert_fusion_aliases(coasting_target)

    for invalid_sensors in ([], ["missing-catalog-sensor"]):
        invalid_coasting = copy.deepcopy(coasting_state)
        _blue_contact(invalid_coasting)["reporting_sensors"] = invalid_sensors
        before_rejection = coasting_target.engine.checkpoint()
        with pytest.raises(ValueError, match="reporting sensor"):
            coasting_target.engine.set_state(invalid_coasting)
        assert coasting_target.engine.checkpoint() == before_rejection
        coasting_target.engine.set_state(coasting_state)
        assert coasting_target.engine.checkpoint() == coasting_checkpoint

    _step_pair(control, resumed, 59)
    assert control.context.clock.elapsed.total_seconds() == 620.0
    assert set(status for contacts in _contact_statuses(control).values() for status in contacts.values()) == {
        "COASTING"
    }
    assert control.engine.checkpoint() == resumed.engine.checkpoint()

    _step_pair(control, resumed, 1)
    assert control.context.clock.tick_count == 125
    assert control.context.clock.elapsed.total_seconds() == 625.0
    assert _contact_statuses(control) == {
        "blue": {},
        "green": {},
        "red": {},
    }
    expected_lost_fusion = {
        "blue": {"fow-track-0001": "LOST"},
        "green": {"fow-track-0001": "LOST"},
        "red": {
            "fow-track-0001": "LOST",
            "fow-track-0002": "LOST",
        },
    }
    assert _fusion_statuses(control) == expected_lost_fusion
    assert _fusion_statuses(resumed) == expected_lost_fusion
    assert control.recorder is not None
    assert resumed.recorder is not None
    assert Counter(event.event_type for event in control.recorder.events) == {
        "MoraleStateChangeEvent": 13,
        "RallyEvent": 1,
    }
    assert control.recorder.get_state() == resumed.recorder.get_state()
    assert control.engine.checkpoint() == resumed.engine.checkpoint()

    _set_detection_headings(control, facing=True)
    _set_detection_headings(resumed, facing=True)
    _step_pair(control, resumed, 1)
    assert control.context.clock.tick_count == 126
    assert control.context.clock.elapsed.total_seconds() == 630.0
    expected_redetection = {
        "blue": {},
        "green": {
            "red_iron_duke_bb_0000": (
                "fow-track-0002",
                "TENTATIVE",
                1,
                630.0,
                630.0,
                630.0,
                ("binoculars_ww1",),
            ),
        },
        "red": {
            "green_iron_duke_bb_0000": (
                "fow-track-0003",
                "TENTATIVE",
                1,
                630.0,
                630.0,
                630.0,
                ("binoculars_ww1",),
            ),
        },
    }
    assert _contact_topology(control) == expected_redetection
    assert _contact_topology(resumed) == expected_redetection
    expected_redetected_fusion = {
        "blue": {"fow-track-0001": "LOST"},
        "green": {
            "fow-track-0001": "LOST",
            "fow-track-0002": "TENTATIVE",
        },
        "red": {
            "fow-track-0001": "LOST",
            "fow-track-0002": "LOST",
            "fow-track-0003": "TENTATIVE",
        },
    }
    assert _fusion_statuses(control) == expected_redetected_fusion
    assert _fusion_statuses(resumed) == expected_redetected_fusion
    assert _capture_exposure(control) == _capture_exposure(resumed)
    _assert_fusion_aliases(control)
    _assert_fusion_aliases(resumed)
    assert control.recorder.get_state() == resumed.recorder.get_state()
    assert control.engine.checkpoint() == resumed.engine.checkpoint()


def test_in_place_restore_rewinds_contacts_and_replaces_pristine_views() -> None:
    """In-place restore rewinds live contacts and removes target-only views."""
    prepared = _prepare(_phase116_config(), variant_id=VARIANT_ID)
    session, checkpoint = _prime_checkpoint(prepared)
    expected_topology = _contact_topology(session)
    expected_targeting = session.context.tactical_targeting.get_state()
    expected_witnesses = session.context.fog_of_war.get_current_detection_witnesses()
    assert len(expected_witnesses) == 4
    assert session.step() is False
    assert any(values[2] == 4 for contacts in _contact_topology(session).values() for values in contacts.values())
    assert len(session.context.fog_of_war.get_current_detection_witnesses()) == 4

    session.engine.restore(checkpoint)

    assert _contact_topology(session) == expected_topology
    assert session.context.tactical_targeting.get_state() == expected_targeting
    restored_witnesses = session.context.fog_of_war.get_current_detection_witnesses()
    assert restored_witnesses == expected_witnesses
    assert all(
        restored_witness is not expected_witness
        for restored_witness, expected_witness in zip(
            restored_witnesses,
            expected_witnesses,
            strict=True,
        )
    )
    _assert_fusion_aliases(session)
    assert session.engine.checkpoint() == checkpoint

    pristine = _build_probe(prepared, seed=316_116)
    pristine_checkpoint = pristine.engine.checkpoint()
    assert pristine.context.fog_of_war.get_state()["world_views"] == {}
    _set_detection_headings(pristine, facing=True)
    assert pristine.step() is False
    assert _contact_topology(pristine) != {side: {} for side in SIDES}

    pristine.engine.restore(pristine_checkpoint)

    assert pristine.context.fog_of_war.get_state()["world_views"] == {}
    assert all(pristine.context.fog_of_war.peek_world_view(side) is None for side in SIDES)
    assert pristine.context.fog_of_war.get_current_detection_witnesses() == ()
    assert pristine.engine.checkpoint() == pristine_checkpoint


def test_stale_consumable_fow_interval_requires_its_retained_witness() -> None:
    """Clock-stale retained decisions cannot outlive their exact evidence."""
    prepared = _prepare_targeting_scenario(
        fog_of_war=True,
        separation_m=800.0,
        northward_target=True,
    )
    battle_config = BattleConfig(max_ticks_per_battle=1)
    source = prepared.build(
        TARGETING_VARIANT_ID,
        seed=115,
        max_ticks=10,
        strict_mode=True,
        battle_config=battle_config,
    )
    source.step()
    source.step()

    interval = source.context.tactical_targeting.prepared_interval
    assert interval is not None
    assert interval.engine_tick == 1
    assert source.context.clock.tick_count == 2
    decisions = tuple(
        decision
        for picture in source.context.tactical_targeting.latest_pictures()
        for decision in picture.decisions
        if decision.contact_source is ContactSource.FOW_OBSERVER_WITNESS
    )
    assert decisions
    assert all(decision.consumable for decision in decisions)
    valid = source.engine.get_state()
    assert valid["context"]["fog_of_war"]["current_detection_witnesses"]

    invalid = copy.deepcopy(valid)
    invalid["context"]["fog_of_war"]["current_detection_witnesses"] = {}
    target = prepared.build(
        TARGETING_VARIANT_ID,
        seed=999,
        max_ticks=10,
        strict_mode=True,
        battle_config=battle_config,
    )
    before = target.engine.checkpoint()
    with pytest.raises(ValueError, match="exact detection witness"):
        target.engine.set_state(invalid)
    assert target.engine.checkpoint() == before

    target.engine.set_state(valid)
    assert target.engine.checkpoint() == source.engine.checkpoint()


CheckpointCorruptor = Callable[[dict[str, Any]], None]


def _fow_state(state: dict[str, Any]) -> dict[str, Any]:
    return state["context"]["fog_of_war"]


def _blue_contact(state: dict[str, Any]) -> dict[str, Any]:
    return _fow_state(state)["world_views"]["blue"]["contacts"]["red_iron_duke_bb_0000"]


def _blue_fusion_track(state: dict[str, Any]) -> dict[str, Any]:
    contact = _blue_contact(state)
    return _fow_state(state)["intel_fusion"]["tracks"]["blue"][contact["track"]["track_id"]]


def _mutate_rng_state(rng_state: dict[str, Any]) -> None:
    rng_state["state"]["state"] += 1


def _extra_fow_key(state: dict[str, Any]) -> None:
    _fow_state(state)["unexpected"] = None


def _missing_fow_owner(state: dict[str, Any]) -> None:
    del state["context"]["fog_of_war"]


def _missing_detection_owner(state: dict[str, Any]) -> None:
    del state["context"]["detection_engine"]


def _extra_view_key(state: dict[str, Any]) -> None:
    _fow_state(state)["world_views"]["blue"]["unexpected"] = None


def _extra_contact_key(state: dict[str, Any]) -> None:
    _blue_contact(state)["unexpected"] = None


def _view_side_mismatch(state: dict[str, Any]) -> None:
    _fow_state(state)["world_views"]["blue"]["side"] = "red"


def _unknown_view_side(state: dict[str, Any]) -> None:
    view = _fow_state(state)["world_views"].pop("blue")
    view["side"] = "unknown"
    _fow_state(state)["world_views"]["unknown"] = view


def _contact_key_mismatch(state: dict[str, Any]) -> None:
    _blue_contact(state)["contact_id"] = "green_iron_duke_bb_0000"


def _retarget_blue_contact(
    state: dict[str, Any],
    target_id: str,
) -> None:
    contacts = _fow_state(state)["world_views"]["blue"]["contacts"]
    contact = contacts.pop("red_iron_duke_bb_0000")
    contact["contact_id"] = target_id
    contacts[target_id] = contact


def _friendly_contact(state: dict[str, Any]) -> None:
    _retarget_blue_contact(state, "blue_iron_duke_bb_0000")


def _missing_roster_contact(state: dict[str, Any]) -> None:
    _retarget_blue_contact(state, "missing-roster-target")


def _duplicate_track_alias(state: dict[str, Any]) -> None:
    contact = copy.deepcopy(_blue_contact(state))
    contact["contact_id"] = "green_iron_duke_bb_0000"
    contacts = _fow_state(state)["world_views"]["blue"]["contacts"]
    contacts["green_iron_duke_bb_0000"] = contact
    _fow_state(state)["world_views"]["blue"]["contacts"] = dict(
        sorted(contacts.items()),
    )


def _noncanonical_track_id(state: dict[str, Any]) -> None:
    fow = _fow_state(state)
    contact = _blue_contact(state)
    old_track_id = contact["track"]["track_id"]
    track = fow["intel_fusion"]["tracks"]["blue"].pop(old_track_id)
    track["track_id"] = "track-0001"
    contact["track"]["track_id"] = "track-0001"
    fow["intel_fusion"]["tracks"]["blue"]["track-0001"] = track
    fow["intel_fusion"]["track_counter"] = 1
    fow["intel_fusion"]["fow_track_counters"].pop("blue")


def _missing_fusion_track(state: dict[str, Any]) -> None:
    track_id = _blue_contact(state)["track"]["track_id"]
    del _fow_state(state)["intel_fusion"]["tracks"]["blue"][track_id]


def _nested_fusion_mismatch(state: dict[str, Any]) -> None:
    _blue_contact(state)["track"]["state"]["position"][0] += 1.0


def _wrong_track_side(state: dict[str, Any]) -> None:
    _blue_contact(state)["track"]["side"] = "red"
    _blue_fusion_track(state)["side"] = "red"


def _unknown_contact_level(state: dict[str, Any]) -> None:
    for contact_info in (
        _blue_contact(state)["contact_info"],
        _blue_contact(state)["track"]["contact_info"],
        _blue_fusion_track(state)["contact_info"],
    ):
        contact_info["level"] = 0


def _invalid_contact_confidence(state: dict[str, Any]) -> None:
    for contact_info in (
        _blue_contact(state)["contact_info"],
        _blue_contact(state)["track"]["contact_info"],
        _blue_fusion_track(state)["contact_info"],
    ):
        contact_info["confidence"] = 1.01


def _premature_type_estimate(state: dict[str, Any]) -> None:
    for contact_info in (
        _blue_contact(state)["contact_info"],
        _blue_contact(state)["track"]["contact_info"],
        _blue_fusion_track(state)["contact_info"],
    ):
        contact_info["type_estimate"] = "iron_duke_bb"


def _invalid_live_track_status(state: dict[str, Any]) -> None:
    _blue_contact(state)["track"]["status"] = 4
    _blue_fusion_track(state)["status"] = 4


def _invalid_track_hits(state: dict[str, Any]) -> None:
    _blue_contact(state)["track"]["hits"] = 0
    _blue_fusion_track(state)["hits"] = 0


def _invalid_covariance(state: dict[str, Any]) -> None:
    for track in (_blue_contact(state)["track"], _blue_fusion_track(state)):
        track["state"]["covariance"][0][0] = -1.0


def _invalid_position_shape(state: dict[str, Any]) -> None:
    for track in (_blue_contact(state)["track"], _blue_fusion_track(state)):
        track["state"]["position"] = [1.0]


def _first_after_sensor_contact(state: dict[str, Any]) -> None:
    _blue_contact(state)["first_detected_time"] = 16.0


def _sensor_track_time_mismatch(state: dict[str, Any]) -> None:
    _blue_contact(state)["last_sensor_contact_time"] = 14.0


def _view_after_checkpoint(state: dict[str, Any]) -> None:
    _fow_state(state)["world_views"]["blue"]["last_update_time"] = 16.0


def _duplicate_reporting_sensor(state: dict[str, Any]) -> None:
    _blue_contact(state)["reporting_sensors"].append("binoculars_ww1")


def _blank_reporting_sensor(state: dict[str, Any]) -> None:
    _blue_contact(state)["reporting_sensors"] = [" "]


def _unmapped_reporting_sensor(state: dict[str, Any]) -> None:
    _blue_contact(state)["reporting_sensors"] = ["missing-catalog-sensor"]
    _fow_state(state)["current_detection_witnesses"]["blue"][0]["sensor_id"] = "missing-catalog-sensor"


def _witness_wrong_side_observer(state: dict[str, Any]) -> None:
    _fow_state(state)["current_detection_witnesses"]["blue"][0]["observer_unit_id"] = "green_iron_duke_bb_0000"


def _witness_source_index_mismatch(state: dict[str, Any]) -> None:
    _fow_state(state)["current_detection_witnesses"]["blue"][0]["source_equipment_index"] = 9_999


def _witness_modeled_role_mismatch(state: dict[str, Any]) -> None:
    _fow_state(state)["current_detection_witnesses"]["blue"][0]["modeled_role"] = "night_vision"


def _witness_sensor_type_mismatch(state: dict[str, Any]) -> None:
    _fow_state(state)["current_detection_witnesses"]["blue"][0]["sensor_type"] = "RADAR"


def _witness_targeting_range_mismatch(state: dict[str, Any]) -> None:
    _fow_state(state)["current_detection_witnesses"]["blue"][0]["range_m"] += 0.25


def _fow_rng_mismatch(state: dict[str, Any]) -> None:
    _mutate_rng_state(_fow_state(state)["rng_state"])


def _fusion_rng_mismatch(state: dict[str, Any]) -> None:
    _mutate_rng_state(_fow_state(state)["intel_fusion"]["rng_state"])


def _detection_rng_mismatch(state: dict[str, Any]) -> None:
    _mutate_rng_state(state["context"]["detection_engine"]["rng_state"])


def _rng_manager_detection_mismatch(state: dict[str, Any]) -> None:
    _mutate_rng_state(state["context"]["rng"]["streams"]["detection"])


def _unowned_live_fusion_track(state: dict[str, Any]) -> None:
    del _fow_state(state)["world_views"]["blue"]["contacts"]["red_iron_duke_bb_0000"]


def _ahead_fow_counter(state: dict[str, Any]) -> None:
    _fow_state(state)["intel_fusion"]["fow_track_counters"]["blue"] = 9


def _witness_contact_epoch_mismatch(state: dict[str, Any]) -> None:
    contact = _blue_contact(state)
    contact["last_sensor_contact_time"] = 10.0
    contact["track"]["state"]["last_update_time"] = 10.0
    _blue_fusion_track(state)["state"]["last_update_time"] = 10.0


def _old_checkpoint_version(state: dict[str, Any]) -> None:
    state["checkpoint_version"] = 115


PRODUCTION_CORRUPTIONS: tuple[tuple[str, CheckpointCorruptor], ...] = (
    ("missing_detection_owner", _missing_detection_owner),
    ("missing_fow_owner", _missing_fow_owner),
    ("extra_fow_key", _extra_fow_key),
    ("extra_view_key", _extra_view_key),
    ("extra_contact_key", _extra_contact_key),
    ("view_side_mismatch", _view_side_mismatch),
    ("unknown_view_side", _unknown_view_side),
    ("contact_key_mismatch", _contact_key_mismatch),
    ("friendly_contact", _friendly_contact),
    ("missing_roster_contact", _missing_roster_contact),
    ("duplicate_track_alias", _duplicate_track_alias),
    ("noncanonical_track_id", _noncanonical_track_id),
    ("missing_fusion_track", _missing_fusion_track),
    ("nested_fusion_mismatch", _nested_fusion_mismatch),
    ("wrong_track_side", _wrong_track_side),
    ("unknown_contact_level", _unknown_contact_level),
    ("invalid_contact_confidence", _invalid_contact_confidence),
    ("premature_type_estimate", _premature_type_estimate),
    ("invalid_live_track_status", _invalid_live_track_status),
    ("invalid_track_hits", _invalid_track_hits),
    ("invalid_covariance", _invalid_covariance),
    ("invalid_position_shape", _invalid_position_shape),
    ("first_after_sensor_contact", _first_after_sensor_contact),
    ("sensor_track_time_mismatch", _sensor_track_time_mismatch),
    ("view_after_checkpoint", _view_after_checkpoint),
    ("duplicate_reporting_sensor", _duplicate_reporting_sensor),
    ("blank_reporting_sensor", _blank_reporting_sensor),
    ("unmapped_reporting_sensor", _unmapped_reporting_sensor),
    ("witness_wrong_side_observer", _witness_wrong_side_observer),
    ("witness_source_index_mismatch", _witness_source_index_mismatch),
    ("witness_modeled_role_mismatch", _witness_modeled_role_mismatch),
    ("witness_sensor_type_mismatch", _witness_sensor_type_mismatch),
    ("witness_targeting_range_mismatch", _witness_targeting_range_mismatch),
    ("fow_rng_mismatch", _fow_rng_mismatch),
    ("fusion_rng_mismatch", _fusion_rng_mismatch),
    ("detection_rng_mismatch", _detection_rng_mismatch),
    ("rng_manager_detection_mismatch", _rng_manager_detection_mismatch),
    ("unowned_live_fusion_track", _unowned_live_fusion_track),
    ("ahead_fow_counter", _ahead_fow_counter),
    ("witness_contact_epoch_mismatch", _witness_contact_epoch_mismatch),
    ("old_checkpoint_version", _old_checkpoint_version),
)

_PRODUCTION_ERROR_MATCHES = {
    "missing_detection_owner": "missing=\\['detection_engine'\\]",
    "missing_fow_owner": "missing=\\['fog_of_war'\\]",
    "unknown_view_side": "Unknown fog-of-war side",
    "duplicate_track_alias": "share one fusion track",
    "noncanonical_track_id": "canonical opaque FOW ordinal",
    "witness_targeting_range_mismatch": "exact detection witness",
    "unowned_live_fusion_track": "no ordinary contact owner",
    "ahead_fow_counter": "counter disagrees with issued tracks",
    "witness_contact_epoch_mismatch": "witness chronology",
    "old_checkpoint_version": "expected 118",
}


@pytest.mark.parametrize("owner_name", ("detection_engine", "fog_of_war"))
def test_current_context_rejects_missing_stateful_owner_atomically(
    owner_name: str,
) -> None:
    """Direct context restore cannot retain an omitted target-only owner."""
    prepared = _prepare(_phase116_config(), variant_id=VARIANT_ID)
    target = _build_probe(prepared, seed=616_116)
    if owner_name == "detection_engine":
        target.context.detection_engine._scan_counts[("target-only-observer", "target-only-contact")] = 7
        error_match = "missing DetectionEngine state"
    else:
        target.context.fog_of_war.get_world_view("blue")
        error_match = "missing fog-of-war state"
    valid = target.context.get_state()
    invalid = copy.deepcopy(valid)
    del invalid[owner_name]
    before = target.context.get_state()

    with pytest.raises(ValueError, match=error_match):
        target.context.set_state(invalid)
    assert target.context.get_state() == before

    target.context.set_state(valid)
    assert target.context.get_state() == valid


@pytest.mark.parametrize("also_remove_detection", (False, True))
def test_enabled_capture_rejects_missing_live_fow_owner(
    also_remove_detection: bool,
) -> None:
    """An enabled current runtime cannot omit its live FOW owner on capture."""
    prepared = _prepare(_phase116_config(), variant_id=VARIANT_ID)
    target = _build_probe(prepared, seed=616_117)
    assert target.step() is False
    valid = target.engine.checkpoint()
    fog = target.context.fog_of_war
    detection = target.context.detection_engine
    target.context.fog_of_war = None
    if also_remove_detection:
        target.context.detection_engine = None

    with pytest.raises(ValueError, match="enabled fog-of-war.*owner"):
        target.engine.checkpoint()

    target.context.fog_of_war = fog
    target.context.detection_engine = detection
    assert target.engine.checkpoint() == valid


def test_production_contact_corruptions_reject_atomically_with_valid_retry() -> None:
    """Every contact/cross-owner corruption rejects before live mutation."""
    prepared = _prepare(_phase116_config(), variant_id=VARIANT_ID)
    source, checkpoint = _prime_checkpoint(prepared)
    valid_state = source.engine.get_state()
    assert valid_state["checkpoint_version"] == 118
    target = _build_probe(prepared, seed=416_116)

    for corruption_name, corrupt in PRODUCTION_CORRUPTIONS:
        invalid = copy.deepcopy(valid_state)
        corrupt(invalid)
        before = target.engine.checkpoint()

        with pytest.raises(
            ValueError,
            match=_PRODUCTION_ERROR_MATCHES.get(corruption_name),
        ):
            target.engine.set_state(invalid)

        assert target.engine.checkpoint() == before, corruption_name
        target.engine.restore(checkpoint)
        assert target.engine.checkpoint() == checkpoint, corruption_name
        _assert_fusion_aliases(target)


@pytest.mark.parametrize(
    "omitted_owner",
    ("deception", "cop_config", "cop_networks"),
)
def test_production_capture_and_restore_reject_omitted_fow_owner_state(
    omitted_owner: str,
) -> None:
    """Unserialized deception/COP state cannot leak through a valid restore."""
    prepared = _prepare(_phase116_config(), variant_id=VARIANT_ID)
    source, checkpoint = _prime_checkpoint(prepared)
    target = _build_probe(prepared, seed=516_116)
    fog = target.context.fog_of_war
    pristine_clock = target.context.clock.get_state()
    pristine_rng = copy.deepcopy(target.context.rng_manager.get_state())
    pristine_fusion = copy.deepcopy(fog.intel_fusion.get_state())
    pristine_views = copy.deepcopy(fog._world_views)

    if omitted_owner == "deception":
        fog.deploy_decoy(Position(1.0, 2.0, 0.0))
    elif omitted_owner == "cop_config":
        fog._dl_config = DataLinkConfig(enable_cop_sharing=True)
    else:
        fog.set_data_link_networks(
            {"link16": ["blue_iron_duke_bb_0000"]},
        )
    deception_before = copy.deepcopy(fog._deception.get_state())
    config_before = fog._dl_config.model_copy(deep=True)
    networks_before = copy.deepcopy(fog._data_link_networks)
    units_before = copy.deepcopy(fog._unit_networks)

    with pytest.raises(ValueError, match="unsupported"):
        target.engine.checkpoint()
    with pytest.raises(ValueError, match="unsupported"):
        target.engine.restore(checkpoint)

    assert target.context.clock.get_state() == pristine_clock
    assert target.context.rng_manager.get_state() == pristine_rng
    assert fog.intel_fusion.get_state() == pristine_fusion
    assert fog._world_views == pristine_views
    assert fog._deception.get_state() == deception_before
    assert fog._dl_config == config_before
    assert fog._data_link_networks == networks_before
    assert fog._unit_networks == units_before

    fog._deception._decoys.clear()
    fog._deception._decoy_counter = 0
    fog._dl_config = DataLinkConfig()
    fog.set_data_link_networks({})
    target.engine.restore(checkpoint)
    assert target.engine.checkpoint() == source.engine.checkpoint()
