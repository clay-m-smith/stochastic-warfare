"""Tests for combat/naval_mine.py — mine warfare."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.naval_mine import (
    Mine,
    MineResult,
    MineType,
    MineWarfareConfig,
    MineWarfareEngine,
    SweepResult,
    TransitRisk,
)
from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.types import Position


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _engine(seed: int = 42, config: MineWarfareConfig | None = None) -> MineWarfareEngine:
    rng = _rng(seed)
    bus = EventBus()
    dmg = DamageEngine(bus, rng)
    return MineWarfareEngine(dmg, bus, rng, config)


def _engine_with_bus(seed: int = 42) -> tuple[MineWarfareEngine, EventBus]:
    rng = _rng(seed)
    bus = EventBus()
    dmg = DamageEngine(bus, rng)
    return MineWarfareEngine(dmg, bus, rng), bus


class TestLayMines:
    def test_lays_correct_count(self) -> None:
        e = _engine()
        positions = [Position(0, 0, 0), Position(100, 0, 0)]
        mines = e.lay_mines("layer1", positions, MineType.MAGNETIC, count_per_pos=3)
        assert len(mines) == 6

    def test_mine_ids_unique(self) -> None:
        e = _engine()
        positions = [Position(i * 100, 0, 0) for i in range(5)]
        mines = e.lay_mines("layer1", positions, MineType.CONTACT, count_per_pos=2)
        ids = [m.mine_id for m in mines]
        assert len(set(ids)) == len(ids)

    def test_mines_armed(self) -> None:
        e = _engine()
        mines = e.lay_mines("layer1", [Position(0, 0, 0)], MineType.ACOUSTIC)
        assert all(m.armed for m in mines)

    def test_mine_type_set(self) -> None:
        e = _engine()
        mines = e.lay_mines("layer1", [Position(0, 0, 0)], MineType.PRESSURE)
        assert all(m.mine_type == MineType.PRESSURE for m in mines)

    def test_mine_positions(self) -> None:
        e = _engine()
        pos = Position(500.0, 600.0, -10.0)
        mines = e.lay_mines("layer1", [pos], MineType.CONTACT)
        assert mines[0].position == pos


class TestTransitRisk:
    def test_high_density_high_risk(self) -> None:
        e = _engine()
        risk = e.compute_transit_risk(10000.0, 0.001, 0.5)
        assert risk.encounter_probability > 0.5

    def test_zero_density_no_risk(self) -> None:
        e = _engine()
        risk = e.compute_transit_risk(10000.0, 0.0, 0.5)
        assert risk.encounter_probability == pytest.approx(0.0)
        assert risk.risk_level == "low"

    def test_larger_signature_higher_risk(self) -> None:
        e = _engine()
        small = e.compute_transit_risk(10000.0, 0.0001, 0.1)
        large = e.compute_transit_risk(10000.0, 0.0001, 0.9)
        assert large.encounter_probability > small.encounter_probability

    def test_risk_levels(self) -> None:
        e = _engine()
        low = e.compute_transit_risk(100.0, 0.000001, 0.1)
        assert low.risk_level == "low"

    def test_expected_encounters_positive(self) -> None:
        e = _engine()
        risk = e.compute_transit_risk(10000.0, 0.0005, 0.5)
        assert risk.expected_encounters > 0


class TestResolveMineEncounter:
    def test_contact_mine_high_trigger(self) -> None:
        """Contact mines should trigger frequently."""
        triggered = sum(
            1 for seed in range(30)
            if _engine(seed).resolve_mine_encounter(
                "ship1",
                Mine("m1", Position(0, 0, 0), MineType.CONTACT),
                0.5, 0.5,
            ).triggered
        )
        assert triggered > 15

    def test_high_magnetic_sig_triggers_magnetic(self) -> None:
        """High magnetic signature should trigger magnetic mines."""
        triggered = sum(
            1 for seed in range(30)
            if _engine(seed).resolve_mine_encounter(
                "ship1",
                Mine("m1", Position(0, 0, 0), MineType.MAGNETIC),
                0.9, 0.1,
            ).triggered
        )
        assert triggered > 10

    def test_low_signature_less_likely(self) -> None:
        """Low signature should reduce trigger probability."""
        high_sig = sum(
            1 for seed in range(30)
            if _engine(seed).resolve_mine_encounter(
                "ship1",
                Mine("m1", Position(0, 0, 0), MineType.MAGNETIC),
                0.9, 0.5,
            ).triggered
        )
        low_sig = sum(
            1 for seed in range(30)
            if _engine(seed).resolve_mine_encounter(
                "ship1",
                Mine("m1", Position(0, 0, 0), MineType.MAGNETIC),
                0.1, 0.5,
            ).triggered
        )
        assert high_sig >= low_sig

    def test_disarmed_mine_no_trigger(self) -> None:
        e = _engine()
        mine = Mine("m1", Position(0, 0, 0), MineType.CONTACT, armed=False)
        result = e.resolve_mine_encounter("ship1", mine, 0.9, 0.9)
        assert result.triggered is False

    def test_detonated_mine_no_retrigger(self) -> None:
        e = _engine()
        mine = Mine("m1", Position(0, 0, 0), MineType.CONTACT, detonated=True)
        result = e.resolve_mine_encounter("ship1", mine, 0.9, 0.9)
        assert result.triggered is False

    def test_detonation_causes_damage(self) -> None:
        """A detonated mine should cause damage."""
        for seed in range(50):
            result = _engine(seed).resolve_mine_encounter(
                "ship1",
                Mine("m1", Position(0, 0, 0), MineType.CONTACT),
                0.5, 0.5,
            )
            if result.detonated:
                assert result.damage_fraction > 0
                break
        else:
            pytest.fail("No detonations in 50 attempts")

    def test_dud_possible(self) -> None:
        """Some triggered mines should be duds."""
        duds = 0
        for seed in range(200):
            result = _engine(seed).resolve_mine_encounter(
                "ship1",
                Mine("m1", Position(0, 0, 0), MineType.CONTACT),
                0.5, 0.5,
            )
            if result.dud:
                duds += 1
        assert duds > 0

    def test_event_published(self) -> None:
        e, bus = _engine_with_bus()
        received: list[Event] = []
        bus.subscribe(Event, lambda ev: received.append(ev))
        ts = datetime(2024, 6, 15, tzinfo=timezone.utc)
        mine = Mine("m1", Position(0, 0, 0), MineType.CONTACT)
        e.resolve_mine_encounter("ship1", mine, 0.5, 0.5, timestamp=ts)
        assert len(received) >= 1

    def test_combination_mine_needs_both_signatures(self) -> None:
        """Combination mine should require both magnetic and acoustic."""
        both = sum(
            1 for seed in range(30)
            if _engine(seed).resolve_mine_encounter(
                "ship1",
                Mine("m1", Position(0, 0, 0), MineType.COMBINATION),
                0.9, 0.9,
            ).triggered
        )
        one_only = sum(
            1 for seed in range(30)
            if _engine(seed).resolve_mine_encounter(
                "ship1",
                Mine("m1", Position(0, 0, 0), MineType.COMBINATION),
                0.9, 0.1,
            ).triggered
        )
        assert both >= one_only


class TestSweepMines:
    def test_sweeps_some_mines(self) -> None:
        e = _engine()
        e.lay_mines("layer1", [Position(i * 50, 0, 0) for i in range(10)],
                     MineType.CONTACT, count_per_pos=1)
        result = e.sweep_mines("sweeper1", 50000.0, MineType.CONTACT, dt=120.0)
        assert result.area_cleared_m2 > 0

    def test_harder_mines_slower_sweep(self) -> None:
        e1 = _engine(42)
        e2 = _engine(42)
        e1.lay_mines("layer1", [Position(i * 50, 0, 0) for i in range(10)], MineType.CONTACT)
        e2.lay_mines("layer1", [Position(i * 50, 0, 0) for i in range(10)], MineType.SMART)
        r1 = e1.sweep_mines("sweeper1", 100000.0, MineType.CONTACT, dt=120.0)
        r2 = e2.sweep_mines("sweeper1", 100000.0, MineType.SMART, dt=120.0)
        assert r1.area_cleared_m2 >= r2.area_cleared_m2


class TestMineType:
    def test_enum_values(self) -> None:
        assert MineType.CONTACT == 0
        assert MineType.SMART == 6

    def test_all_types_exist(self) -> None:
        assert len(MineType) == 7


class TestState:
    def test_state_roundtrip(self) -> None:
        e = _engine(42)
        e.lay_mines("layer1", [Position(0, 0, 0)], MineType.MAGNETIC, count_per_pos=2)
        saved = e.get_state()

        e2 = _engine(99)
        e2.set_state(saved)

        assert saved["mine_counter"] == 2
        assert len(saved["mines"]) == 2

    def test_mine_state_roundtrip(self) -> None:
        mine = Mine("m1", Position(100.0, 200.0, -5.0), MineType.ACOUSTIC)
        saved = mine.get_state()
        mine2 = Mine("", Position(0, 0, 0), MineType.CONTACT)
        mine2.set_state(saved)
        assert mine2.mine_id == "m1"
        assert mine2.mine_type == MineType.ACOUSTIC
        assert mine2.position.easting == pytest.approx(100.0)
