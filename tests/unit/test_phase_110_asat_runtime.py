"""Focused runtime semantics for the Phase 110 configured ASAT boundary."""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pytest

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.space.asat import ASATEngine
from stochastic_warfare.space.config import (
    ASATAssetConfig,
    ASATOrderConfig,
    ASATType,
    ASATWeaponDefinition,
    ConstellationDefinition,
    ConstellationType,
    SpaceConfig,
)
from stochastic_warfare.space.constellations import (
    ConstellationManager,
    SpaceEngine,
)
from stochastic_warfare.space.events import (
    ASATEngagementEvent,
    ConstellationDegradedEvent,
)
from stochastic_warfare.space.orbits import R_EARTH, OrbitalMechanicsEngine
from stochastic_warfare.space.satcom import SATCOMEngine

from tests.conftest import TS


CONSTELLATION_ID = "phase110_satcom"
ASSET_ID = "red_phase110_asset"
WEAPON_ID = "phase110_kkv"


@dataclass
class _CommsProbe:
    reliability_updates: list[float] = field(default_factory=list)

    def set_satcom_reliability(self, factor: float) -> None:
        self.reliability_updates.append(factor)


def _runtime(
    *,
    target_count: int = 2,
    target_indexes: tuple[int, ...] = (0,),
    execute_times_s: tuple[float, ...] | None = None,
    rounds_available: int = 1,
    reload_time_s: float = 100.0,
    enable_asat: bool = True,
    min_altitude_km: float = 200.0,
    max_altitude_km: float = 1_000.0,
    semi_major_axis_m: float = R_EARTH + 500_000.0,
    eccentricity: float = 0.0,
    true_anomaly_deg: float = 0.0,
    seed: int = 110,
    separate_assets: bool = False,
) -> tuple[
    SpaceEngine,
    ASATEngine,
    ConstellationManager,
    EventBus,
    np.random.Generator,
]:
    if execute_times_s is None:
        execute_times_s = tuple(0.0 for _ in target_indexes)
    if len(execute_times_s) != len(target_indexes):
        raise ValueError("one execution time is required per target")

    assets = [
        ASATAssetConfig(
            asset_id=(
                f"{ASSET_ID}_{index}"
                if separate_assets
                else ASSET_ID
            ),
            weapon_id=WEAPON_ID,
            side="red",
            rounds_available=rounds_available,
        )
        for index in (
            range(len(target_indexes))
            if separate_assets
            else range(1)
        )
    ]
    orders = [
        ASATOrderConfig(
            order_id=f"phase110_order_{index}",
            asset_id=(
                assets[index].asset_id
                if separate_assets
                else assets[0].asset_id
            ),
            target_satellite_id=(
                f"{CONSTELLATION_ID}_p0_s{target_index}"
            ),
            execute_at_s=execute_time,
        )
        for index, (target_index, execute_time) in enumerate(
            zip(target_indexes, execute_times_s, strict=True),
        )
    ]
    config = SpaceConfig(
        enable_space=True,
        constellation_ids=[CONSTELLATION_ID],
        enable_asat=enable_asat,
        asat_assets=assets,
        asat_orders=orders,
        theater_lat=0.0,
        theater_lon=0.0,
        debris_fragment_mean=20.0,
        debris_collision_prob_per_orbit=0.0,
    )
    constellation = ConstellationDefinition(
        constellation_id=CONSTELLATION_ID,
        display_name="Phase 110 LEO SATCOM",
        constellation_type=int(ConstellationType.SATCOM),
        side="blue",
        num_satellites=target_count,
        orbital_elements_template={
            "semi_major_axis_m": semi_major_axis_m,
            "eccentricity": eccentricity,
            "inclination_deg": 0.0,
            "raan_deg": 0.0,
            "arg_perigee_deg": 0.0,
            "true_anomaly_deg": true_anomaly_deg,
        },
        plane_count=1,
        sats_per_plane=target_count,
        bandwidth_bps=1_000_000.0,
    )
    weapon = ASATWeaponDefinition(
        weapon_id=WEAPON_ID,
        display_name="Phase 110 KKV",
        asat_type=int(ASATType.DIRECT_ASCENT_KKV),
        lethal_radius_m=100.0,
        guidance_sigma_m=0.1,
        min_altitude_km=min_altitude_km,
        max_altitude_km=max_altitude_km,
        closing_velocity_mps=8_000.0,
        reload_time_s=reload_time_s,
        dazzle_duration_s=0.0,
        dazzle_range_km=0.0,
    )

    bus = EventBus()
    rng = np.random.Generator(np.random.PCG64(seed))
    manager = ConstellationManager(
        OrbitalMechanicsEngine(),
        bus,
        rng,
        config,
    )
    manager.add_constellation(constellation)
    asat = ASATEngine(
        manager,
        config,
        bus,
        rng,
        weapon_definitions={WEAPON_ID: weapon},
        assets=config.asat_assets,
        orders=config.asat_orders,
        configuration_fingerprint="a" * 64,
    )
    satcom = SATCOMEngine(manager, config, bus, rng)
    space = SpaceEngine(
        config,
        manager,
        satcom_engine=satcom,
        asat_engine=asat,
        catalog_fingerprint="a" * 64,
    )
    return space, asat, manager, bus, rng


def _engagement_payloads(events: list[Event]) -> list[dict[str, Any]]:
    return [
        {
            "order_id": event.order_id,
            "outcome": event.outcome,
            "reason": event.reason,
            "rounds_remaining": event.rounds_remaining,
        }
        for event in events
        if isinstance(event, ASATEngagementEvent)
    ]


def test_asat_hit_changes_real_satcom_consumer_in_the_same_tick() -> None:
    enabled, _, enabled_manager, enabled_bus, _ = _runtime(
        target_count=1,
        enable_asat=True,
    )
    disabled, _, disabled_manager, disabled_bus, _ = _runtime(
        target_count=1,
        enable_asat=False,
    )
    enabled_events: list[Event] = []
    disabled_events: list[Event] = []
    enabled_bus.subscribe(Event, enabled_events.append)
    disabled_bus.subscribe(Event, disabled_events.append)
    enabled_comms = _CommsProbe()
    disabled_comms = _CommsProbe()

    enabled.update(
        1.0,
        1.0,
        comms_engine=enabled_comms,
        timestamp=TS,
    )
    disabled.update(
        1.0,
        1.0,
        comms_engine=disabled_comms,
        timestamp=TS,
    )

    assert enabled_manager.active_count(CONSTELLATION_ID) == 0
    assert disabled_manager.active_count(CONSTELLATION_ID) == 1
    # SATCOM is the real downstream consumer. It observes blue constellation
    # health after the ASAT transition, before the red no-constellation value.
    assert enabled_comms.reliability_updates == [0.0, 1.0]
    assert disabled_comms.reliability_updates == [1.0, 1.0]
    assert [
        type(event) for event in enabled_events[:2]
    ] == [ConstellationDegradedEvent, ASATEngagementEvent]
    assert not _engagement_payloads(disabled_events)


@pytest.mark.parametrize(
    ("rounds_available", "expected_reason"),
    (
        (1, "asset_depleted"),
        (2, "asset_reloading"),
    ),
)
def test_simultaneous_orders_commit_in_declaration_order_without_extra_rng(
    rounds_available: int,
    expected_reason: str,
) -> None:
    _, asat, _, bus, rng = _runtime(
        target_indexes=(0, 1),
        execute_times_s=(0.0, 0.0),
        rounds_available=rounds_available,
    )
    events: list[Event] = []
    bus.subscribe(Event, events.append)

    results = asat.execute_due_orders(0.0, TS)

    assert [result["order_id"] for result in results] == [
        "phase110_order_0",
        "phase110_order_1",
    ]
    assert results[0]["outcome"] == "hit"
    assert results[1]["outcome"] == "rejected"
    assert results[1]["reason"] == expected_reason
    assert _engagement_payloads(events) == [
        {
            "order_id": "phase110_order_0",
            "outcome": "hit",
            "reason": "",
            "rounds_remaining": rounds_available - 1,
        },
        {
            "order_id": "phase110_order_1",
            "outcome": "rejected",
            "reason": expected_reason,
            "rounds_remaining": rounds_available - 1,
        },
    ]

    _, one_order, _, _, one_order_rng = _runtime(
        target_indexes=(0,),
        execute_times_s=(0.0,),
        rounds_available=rounds_available,
    )
    one_order.execute_due_orders(0.0, TS)
    assert rng.bit_generator.state == one_order_rng.bit_generator.state


def test_shared_weapon_definition_preserves_independent_asset_state(
) -> None:
    space, asat, manager, _, _ = _runtime(
        target_indexes=(0, 1),
        execute_times_s=(0.0, 0.0),
        rounds_available=1,
        separate_assets=True,
    )

    results = asat.execute_due_orders(0.0, TS)

    assert [result["asset_id"] for result in results] == [
        f"{ASSET_ID}_0",
        f"{ASSET_ID}_1",
    ]
    assert [result["outcome"] for result in results] == ["hit", "hit"]
    assert manager.active_count(CONSTELLATION_ID) == 0
    state = asat.get_state()
    assert set(state["assets"]) == {
        f"{ASSET_ID}_0",
        f"{ASSET_ID}_1",
    }
    assert {
        asset_id: (
            asset_state["rounds_remaining"],
            asset_state["ready_at_s"],
        )
        for asset_id, asset_state in state["assets"].items()
    } == {
        f"{ASSET_ID}_0": (0, 100.0),
        f"{ASSET_ID}_1": (0, 100.0),
    }

    checkpoint = space.get_state()
    restored, restored_asat, restored_manager, _, _ = _runtime(
        target_indexes=(0, 1),
        execute_times_s=(0.0, 0.0),
        rounds_available=1,
        separate_assets=True,
    )
    restored.set_state(copy.deepcopy(checkpoint))
    assert restored.get_state() == checkpoint
    assert restored_manager.active_count(CONSTELLATION_ID) == 0
    assert restored_asat.execute_due_orders(1.0, TS) == []


def test_not_yet_due_and_runtime_rejections_do_not_draw_rng() -> None:
    _, pending, _, _, pending_rng = _runtime(
        execute_times_s=(10.0,),
    )
    pending_before = copy.deepcopy(pending.get_state())
    pending_rng_before = copy.deepcopy(pending_rng.bit_generator.state)
    assert pending.execute_due_orders(9.0, TS) == []
    assert pending.get_state() == pending_before
    assert pending_rng.bit_generator.state == pending_rng_before

    _, inactive, inactive_manager, _, inactive_rng = _runtime()
    inactive_manager.deactivate_satellite(
        f"{CONSTELLATION_ID}_p0_s0",
        "test_setup",
        TS,
    )
    inactive_rng_before = copy.deepcopy(inactive_rng.bit_generator.state)
    inactive_result = inactive.execute_due_orders(0.0, TS)[0]
    assert inactive_result["reason"] == "target_inactive"
    assert inactive_result["launched"] is False
    assert inactive_rng.bit_generator.state == inactive_rng_before

    _, out_of_range, _, _, range_rng = _runtime(
        min_altitude_km=200.0,
        max_altitude_km=400.0,
    )
    range_rng_before = copy.deepcopy(range_rng.bit_generator.state)
    range_result = out_of_range.execute_due_orders(0.0, TS)[0]
    assert range_result["reason"] == "target_out_of_range"
    assert range_result["launched"] is False
    assert range_rng.bit_generator.state == range_rng_before


def test_observer_failure_cannot_rollback_or_retry_committed_order(
    caplog: pytest.LogCaptureFixture,
) -> None:
    _, asat, manager, bus, _ = _runtime(target_count=1)
    observed: list[Event] = []

    def fail_degradation(_event: ConstellationDegradedEvent) -> None:
        raise RuntimeError("phase110 observer failure")

    bus.subscribe(ConstellationDegradedEvent, fail_degradation)
    bus.subscribe(Event, observed.append)

    with caplog.at_level(
        logging.ERROR,
        logger="stochastic_warfare.space.asat",
    ):
        first = asat.execute_due_orders(0.0, TS)
        second = asat.execute_due_orders(1.0, TS)

    assert len(first) == 1
    assert first[0]["outcome"] == "hit"
    assert second == []
    assert manager.active_count(CONSTELLATION_ID) == 0
    assert _engagement_payloads(observed) == [
        {
            "order_id": "phase110_order_0",
            "outcome": "hit",
            "reason": "",
            "rounds_remaining": 0,
        },
    ]
    assert "phase110 observer failure" in caplog.text
    state = asat.get_state()
    assert state["pending_order_ids"] == []
    assert list(state["completed_orders"]) == ["phase110_order_0"]


def test_checkpoint_rejects_nonchronological_constellation_count_history(
) -> None:
    space, asat, _, _, _ = _runtime(
        target_count=2,
        target_indexes=(0, 1),
        execute_times_s=(0.0, 0.0),
        rounds_available=2,
    )
    results = asat.execute_due_orders(0.0, TS)
    assert [result["reason"] for result in results] == [
        "",
        "asset_reloading",
    ]

    invalid = space.get_state()
    second = invalid["asat_engine"]["completed_orders"][
        "phase110_order_1"
    ]
    second["previous_constellation_count"] = 2
    second["new_constellation_count"] = 2

    with pytest.raises(ValueError, match="count history is not chronological"):
        space.stage_state(invalid)
