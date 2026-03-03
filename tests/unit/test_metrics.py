"""Tests for stochastic_warfare.validation.metrics."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

from stochastic_warfare.core.events import Event
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.validation.metrics import (
    EngagementMetrics,
    SimulationResult,
    UnitFinalState,
)

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


# ── helpers ──────────────────────────────────────────────────────────


def _make_unit(
    entity_id: str = "u1",
    side: str = "blue",
    unit_type: str = "m1a1",
    status: str = "ACTIVE",
    pers_remaining: int = 4,
    pers_initial: int = 4,
    equip_destroyed: int = 0,
    equip_total: int = 5,
    morale: str = "STEADY",
    ammo: dict[str, int] | None = None,
) -> UnitFinalState:
    return UnitFinalState(
        entity_id=entity_id,
        side=side,
        unit_type=unit_type,
        status=status,
        personnel_remaining=pers_remaining,
        personnel_initial=pers_initial,
        equipment_destroyed=equip_destroyed,
        equipment_total=equip_total,
        morale_state=morale,
        ammo_expended=ammo or {},
    )


def _make_result(
    units: list[UnitFinalState] | None = None,
    events: list[Event] | None = None,
    duration_s: float = 1380.0,
    seed: int = 42,
) -> SimulationResult:
    return SimulationResult(
        seed=seed,
        ticks_executed=100,
        duration_simulated_s=duration_s,
        units_final=units or [],
        event_log=events or [],
        terminated_by="time_limit",
    )


# ── UnitFinalState ───────────────────────────────────────────────────


class TestUnitFinalState:
    def test_defaults(self) -> None:
        u = UnitFinalState(
            entity_id="x", side="blue", unit_type="m1a1", status="ACTIVE"
        )
        assert u.personnel_remaining == 0
        assert u.morale_state == "STEADY"
        assert u.ammo_expended == {}

    def test_full_construction(self) -> None:
        u = _make_unit(ammo={"m829a3_apfsds": 5})
        assert u.ammo_expended["m829a3_apfsds"] == 5


# ── casualty_exchange_ratio ──────────────────────────────────────────


class TestCasualtyExchangeRatio:
    def test_normal_ratio(self) -> None:
        units = [
            _make_unit("b1", "blue", status="ACTIVE"),
            _make_unit("r1", "red", status="DESTROYED"),
            _make_unit("r2", "red", status="DESTROYED"),
        ]
        result = _make_result(units)
        ratio = EngagementMetrics.casualty_exchange_ratio(result, "blue", "red")
        assert ratio == float("inf")  # blue: 0 destroyed, red: 2

    def test_both_sides_losses(self) -> None:
        units = [
            _make_unit("b1", "blue", status="DESTROYED"),
            _make_unit("r1", "red", status="DESTROYED"),
            _make_unit("r2", "red", status="DESTROYED"),
            _make_unit("r3", "red", status="DESTROYED"),
        ]
        result = _make_result(units)
        ratio = EngagementMetrics.casualty_exchange_ratio(result, "blue", "red")
        assert ratio == 3.0  # 3 red / 1 blue

    def test_no_losses(self) -> None:
        units = [
            _make_unit("b1", "blue", status="ACTIVE"),
            _make_unit("r1", "red", status="ACTIVE"),
        ]
        result = _make_result(units)
        ratio = EngagementMetrics.casualty_exchange_ratio(result, "blue", "red")
        assert ratio == 0.0

    def test_blue_only_losses(self) -> None:
        units = [
            _make_unit("b1", "blue", status="DESTROYED"),
            _make_unit("r1", "red", status="ACTIVE"),
        ]
        result = _make_result(units)
        ratio = EngagementMetrics.casualty_exchange_ratio(result, "blue", "red")
        assert ratio == 0.0  # 0 red / 1 blue

    def test_empty_result(self) -> None:
        result = _make_result([])
        ratio = EngagementMetrics.casualty_exchange_ratio(result, "blue", "red")
        assert ratio == 0.0


# ── personnel_casualties ─────────────────────────────────────────────


class TestPersonnelCasualties:
    def test_basic_casualties(self) -> None:
        units = [
            _make_unit("b1", "blue", pers_remaining=3, pers_initial=4),
            _make_unit("b2", "blue", pers_remaining=0, pers_initial=4),
        ]
        result = _make_result(units)
        pers = EngagementMetrics.personnel_casualties(result, "blue")
        assert pers["initial"] == 8
        assert pers["remaining"] == 3
        assert pers["casualties"] == 5

    def test_no_casualties(self) -> None:
        units = [_make_unit("b1", "blue", pers_remaining=4, pers_initial=4)]
        result = _make_result(units)
        pers = EngagementMetrics.personnel_casualties(result, "blue")
        assert pers["casualties"] == 0

    def test_empty_side(self) -> None:
        result = _make_result([])
        pers = EngagementMetrics.personnel_casualties(result, "blue")
        assert pers == {"initial": 0, "remaining": 0, "casualties": 0}


# ── equipment_losses ─────────────────────────────────────────────────


class TestEquipmentLosses:
    def test_losses(self) -> None:
        units = [
            _make_unit("b1", "blue", equip_destroyed=2, equip_total=5),
            _make_unit("b2", "blue", equip_destroyed=1, equip_total=5),
        ]
        result = _make_result(units)
        losses = EngagementMetrics.equipment_losses(result, "blue")
        assert losses == {"destroyed": 3, "total": 10}

    def test_equipment_loss_count(self) -> None:
        units = [
            _make_unit("b1", "blue", equip_destroyed=2, equip_total=5),
        ]
        result = _make_result(units)
        assert EngagementMetrics.equipment_loss_count(result, "blue") == 2


# ── units_destroyed_count ────────────────────────────────────────────


class TestUnitsDestroyedCount:
    def test_count(self) -> None:
        units = [
            _make_unit("r1", "red", status="DESTROYED"),
            _make_unit("r2", "red", status="DESTROYED"),
            _make_unit("r3", "red", status="ACTIVE"),
        ]
        result = _make_result(units)
        assert EngagementMetrics.units_destroyed_count(result, "red") == 2

    def test_none_destroyed(self) -> None:
        units = [_make_unit("r1", "red", status="ACTIVE")]
        result = _make_result(units)
        assert EngagementMetrics.units_destroyed_count(result, "red") == 0


# ── engagement_duration_s ────────────────────────────────────────────


class TestEngagementDuration:
    def test_duration(self) -> None:
        result = _make_result(duration_s=1380.0)
        assert EngagementMetrics.engagement_duration_s(result) == 1380.0


# ── ammunition_expended ──────────────────────────────────────────────


class TestAmmunitionExpended:
    def test_aggregation(self) -> None:
        units = [
            _make_unit("b1", "blue", ammo={"apfsds": 5, "heat": 2}),
            _make_unit("b2", "blue", ammo={"apfsds": 3}),
        ]
        result = _make_result(units)
        totals = EngagementMetrics.ammunition_expended(result)
        assert totals["apfsds"] == 8
        assert totals["heat"] == 2

    def test_empty(self) -> None:
        result = _make_result([])
        assert EngagementMetrics.ammunition_expended(result) == {}


# ── morale_distribution ──────────────────────────────────────────────


class TestMoraleDistribution:
    def test_distribution(self) -> None:
        units = [
            _make_unit("r1", "red", morale="BROKEN"),
            _make_unit("r2", "red", morale="BROKEN"),
            _make_unit("r3", "red", morale="ROUTED"),
            _make_unit("r4", "red", morale="STEADY"),
        ]
        result = _make_result(units)
        dist = EngagementMetrics.morale_distribution(result, "red")
        assert dist == {"BROKEN": 2, "ROUTED": 1, "STEADY": 1}

    def test_filters_by_side(self) -> None:
        units = [
            _make_unit("b1", "blue", morale="STEADY"),
            _make_unit("r1", "red", morale="BROKEN"),
        ]
        result = _make_result(units)
        assert EngagementMetrics.morale_distribution(result, "blue") == {"STEADY": 1}


# ── ships_sunk ───────────────────────────────────────────────────────


class TestShipsSunk:
    def test_ships_sunk(self) -> None:
        units = [
            _make_unit("s1", "blue", unit_type="type42_destroyer", status="DESTROYED"),
            _make_unit("s2", "blue", unit_type="type22_frigate", status="ACTIVE"),
            _make_unit("s3", "blue", unit_type="ddg51", status="DESTROYED"),
        ]
        result = _make_result(units)
        assert EngagementMetrics.ships_sunk(result, "blue") == 2

    def test_non_naval_not_counted(self) -> None:
        units = [
            _make_unit("t1", "blue", unit_type="m1a1", status="DESTROYED"),
        ]
        result = _make_result(units)
        assert EngagementMetrics.ships_sunk(result, "blue") == 0


# ── missiles_hit_ratio ───────────────────────────────────────────────


class TestMissilesHitRatio:
    def test_no_events(self) -> None:
        result = _make_result(events=[])
        assert EngagementMetrics.missiles_hit_ratio(result) == 0.0

    def test_with_launches(self) -> None:
        # Simulate with mock events matching expected class names
        @dataclass(frozen=True)
        class MissileLaunchEvent(Event):
            launcher_id: str = ""
            missile_id: str = ""
            target_id: str = ""
            missile_type: str = ""

        events = [
            MissileLaunchEvent(
                timestamp=_TS,
                source=ModuleId.COMBAT,
                launcher_id="l1",
                missile_id="m1",
                target_id="t1",
                missile_type="exocet",
            ),
            MissileLaunchEvent(
                timestamp=_TS,
                source=ModuleId.COMBAT,
                launcher_id="l1",
                missile_id="m2",
                target_id="t2",
                missile_type="exocet",
            ),
        ]
        result = _make_result(events=events)
        # 2 launches, 0 hits → 0.0
        assert EngagementMetrics.missiles_hit_ratio(result) == 0.0


# ── extract_all ──────────────────────────────────────────────────────


class TestExtractAll:
    def test_complete_extraction(self) -> None:
        units = [
            _make_unit("b1", "blue", status="ACTIVE", pers_remaining=4,
                        pers_initial=4, equip_destroyed=0, equip_total=5),
            _make_unit("r1", "red", status="DESTROYED", pers_remaining=0,
                        pers_initial=4, equip_destroyed=3, equip_total=5),
            _make_unit("r2", "red", status="DESTROYED", pers_remaining=0,
                        pers_initial=4, equip_destroyed=5, equip_total=5),
        ]
        result = _make_result(units, duration_s=1380.0)
        metrics = EngagementMetrics.extract_all(result)

        assert metrics["exchange_ratio"] == float("inf")  # 2:0
        assert metrics["duration_s"] == 1380.0
        assert metrics["blue_personnel_casualties"] == 0.0
        assert metrics["red_personnel_casualties"] == 8.0
        assert metrics["blue_equipment_destroyed"] == 0.0
        assert metrics["red_equipment_destroyed"] == 8.0
        assert metrics["blue_units_destroyed"] == 0.0
        assert metrics["red_units_destroyed"] == 2.0

    def test_empty_battlefield(self) -> None:
        result = _make_result([])
        metrics = EngagementMetrics.extract_all(result)
        assert metrics["exchange_ratio"] == 0.0
        assert metrics["blue_personnel_casualties"] == 0.0
