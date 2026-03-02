"""Tests for combat/carrier_ops.py — carrier flight operations."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.combat.carrier_ops import (
    CAPStatus,
    CarrierOpsConfig,
    CarrierOpsEngine,
    DeckState,
    LaunchResult,
    RecoveryResult,
)
from stochastic_warfare.core.events import Event, EventBus


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _engine(seed: int = 42, config: CarrierOpsConfig | None = None) -> CarrierOpsEngine:
    rng = _rng(seed)
    bus = EventBus()
    return CarrierOpsEngine(bus, rng, config)


def _engine_with_bus(seed: int = 42) -> tuple[CarrierOpsEngine, EventBus]:
    rng = _rng(seed)
    bus = EventBus()
    return CarrierOpsEngine(bus, rng), bus


class TestComputeSortieRate:
    def test_basic_rate(self) -> None:
        e = _engine()
        rate = e.compute_sortie_rate(20, 0.8, 1.0, DeckState.IDLE)
        assert rate > 0

    def test_no_aircraft_no_sorties(self) -> None:
        e = _engine()
        rate = e.compute_sortie_rate(0, 0.8, 1.0, DeckState.IDLE)
        assert rate == 0.0

    def test_damaged_deck_reduces_rate(self) -> None:
        e = _engine()
        normal = e.compute_sortie_rate(20, 0.8, 1.0, DeckState.IDLE)
        damaged = e.compute_sortie_rate(20, 0.8, 1.0, DeckState.DAMAGED)
        assert damaged < normal

    def test_maintenance_blocks_sorties(self) -> None:
        e = _engine()
        rate = e.compute_sortie_rate(20, 0.8, 1.0, DeckState.MAINTENANCE)
        assert rate == 0.0

    def test_bad_weather_reduces_rate(self) -> None:
        e = _engine()
        good = e.compute_sortie_rate(20, 0.8, 1.0, DeckState.IDLE)
        bad = e.compute_sortie_rate(20, 0.8, 0.3, DeckState.IDLE)
        assert bad < good

    def test_better_crew_higher_rate(self) -> None:
        e = _engine()
        poor = e.compute_sortie_rate(20, 0.3, 1.0, DeckState.IDLE)
        good = e.compute_sortie_rate(20, 0.9, 1.0, DeckState.IDLE)
        assert good > poor

    def test_recovery_cycle_partial(self) -> None:
        e = _engine()
        launch = e.compute_sortie_rate(20, 0.8, 1.0, DeckState.LAUNCH_CYCLE)
        recovery = e.compute_sortie_rate(20, 0.8, 1.0, DeckState.RECOVERY_CYCLE)
        assert recovery < launch


class TestLaunchAircraft:
    def test_successful_launch(self) -> None:
        """Launches from idle deck should almost always succeed."""
        successes = sum(
            1 for seed in range(30)
            if _engine(seed).launch_aircraft("cv1", "f1", "CAP", DeckState.LAUNCH_CYCLE).success
        )
        assert successes > 25

    def test_maintenance_always_fails(self) -> None:
        e = _engine()
        result = e.launch_aircraft("cv1", "f1", "CAP", DeckState.MAINTENANCE)
        assert result.success is False

    def test_damaged_deck_less_reliable(self) -> None:
        normal = sum(
            1 for seed in range(50)
            if _engine(seed).launch_aircraft("cv1", "f1", "STRIKE", DeckState.IDLE).success
        )
        damaged = sum(
            1 for seed in range(50)
            if _engine(seed).launch_aircraft("cv1", "f1", "STRIKE", DeckState.DAMAGED).success
        )
        assert normal > damaged

    def test_event_published_on_success(self) -> None:
        e, bus = _engine_with_bus()
        received: list[Event] = []
        bus.subscribe(Event, lambda ev: received.append(ev))
        ts = datetime(2024, 6, 15, tzinfo=timezone.utc)
        result = e.launch_aircraft("cv1", "f1", "CAP", DeckState.IDLE, timestamp=ts)
        if result.success:
            assert len(received) >= 1

    def test_mission_type_in_result(self) -> None:
        e = _engine()
        result = e.launch_aircraft("cv1", "f1", "ASW", DeckState.IDLE)
        assert result.mission_type == "ASW"

    def test_deterministic_with_seed(self) -> None:
        e1 = _engine(42)
        e2 = _engine(42)
        r1 = e1.launch_aircraft("cv1", "f1", "CAP", DeckState.IDLE)
        r2 = e2.launch_aircraft("cv1", "f1", "CAP", DeckState.IDLE)
        assert r1.success == r2.success


class TestRecoverAircraft:
    def test_calm_seas_good_pilot(self) -> None:
        """Calm seas + good pilot should recover successfully."""
        successes = sum(
            1 for seed in range(30)
            if _engine(seed).recover_aircraft("cv1", "f1", 1.0, 0.9).success
        )
        assert successes > 20

    def test_rough_seas_more_bolters(self) -> None:
        """Rough seas should cause more bolters."""
        calm_bolters = sum(
            1 for seed in range(50)
            if _engine(seed).recover_aircraft("cv1", "f1", 1.0, 0.7).bolter
        )
        rough_bolters = sum(
            1 for seed in range(50)
            if _engine(seed).recover_aircraft("cv1", "f1", 7.0, 0.7).bolter
        )
        assert rough_bolters >= calm_bolters

    def test_low_skill_more_failures(self) -> None:
        """Low skill pilot should have more recovery failures."""
        good = sum(
            1 for seed in range(50)
            if _engine(seed).recover_aircraft("cv1", "f1", 2.0, 0.95).success
        )
        poor = sum(
            1 for seed in range(50)
            if _engine(seed).recover_aircraft("cv1", "f1", 2.0, 0.2).success
        )
        assert good > poor

    def test_bolter_or_waveoff_or_success(self) -> None:
        """Each recovery should be exactly one of success, bolter, or wave-off."""
        for seed in range(20):
            result = _engine(seed).recover_aircraft("cv1", "f1", 3.0, 0.5)
            outcomes = [result.success, result.bolter, result.wave_off]
            assert sum(outcomes) == 1

    def test_deterministic_with_seed(self) -> None:
        e1 = _engine(42)
        e2 = _engine(42)
        r1 = e1.recover_aircraft("cv1", "f1", 3.0, 0.7)
        r2 = e2.recover_aircraft("cv1", "f1", 3.0, 0.7)
        assert r1.success == r2.success
        assert r1.bolter == r2.bolter


class TestTurnaroundAircraft:
    def test_returns_positive_time(self) -> None:
        e = _engine()
        t = e.turnaround_aircraft("f1", "full")
        assert t > 0

    def test_hot_refuel_faster(self) -> None:
        """Hot refuel should be faster than full turnaround."""
        full_times = [_engine(seed).turnaround_aircraft("f1", "full") for seed in range(20)]
        hot_times = [_engine(seed).turnaround_aircraft("f1", "hot_refuel") for seed in range(20)]
        assert sum(hot_times) / len(hot_times) < sum(full_times) / len(full_times)

    def test_reconfigure_slower(self) -> None:
        """Reconfigure should take longer than basic rearm."""
        rearm_times = [_engine(seed).turnaround_aircraft("f1", "rearm") for seed in range(20)]
        reconf_times = [_engine(seed).turnaround_aircraft("f1", "reconfigure") for seed in range(20)]
        assert sum(reconf_times) / len(reconf_times) > sum(rearm_times) / len(rearm_times)

    def test_deterministic_with_seed(self) -> None:
        e1 = _engine(42)
        e2 = _engine(42)
        t1 = e1.turnaround_aircraft("f1", "full")
        t2 = e2.turnaround_aircraft("f1", "full")
        assert t1 == pytest.approx(t2)


class TestDeckState:
    def test_enum_values(self) -> None:
        assert DeckState.IDLE == 0
        assert DeckState.DAMAGED == 4

    def test_all_states_exist(self) -> None:
        assert len(DeckState) == 5


class TestState:
    def test_state_roundtrip(self) -> None:
        e = _engine(42)
        e.launch_aircraft("cv1", "f1", "CAP", DeckState.IDLE)
        e.turnaround_aircraft("f2", "full")
        saved = e.get_state()

        e2 = _engine(99)
        e2.set_state(saved)

        t1 = e.turnaround_aircraft("f3", "full")
        t2 = e2.turnaround_aircraft("f3", "full")
        assert t1 == pytest.approx(t2)

    def test_sorties_count_restored(self) -> None:
        e = _engine(42)
        e.launch_aircraft("cv1", "f1", "CAP", DeckState.IDLE)
        e.launch_aircraft("cv1", "f2", "STRIKE", DeckState.IDLE)
        saved = e.get_state()
        assert saved["sorties_launched"] == 2

    def test_turnaround_state_restored(self) -> None:
        e = _engine(42)
        e.turnaround_aircraft("f1", "full")
        saved = e.get_state()
        assert "f1" in saved["aircraft_turnaround"]
