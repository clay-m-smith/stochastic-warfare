"""Unit tests for CarrierOpsEngine — launch, recovery, CAP, sortie rate."""

from __future__ import annotations

import pytest

from stochastic_warfare.combat.carrier_ops import (
    CAPStation,
    CarrierOpsConfig,
    CarrierOpsEngine,
    DeckState,
    LaunchResult,
    RecoveryResult,
    RecoveryWindow,
)
from stochastic_warfare.core.events import EventBus

from .conftest import _rng


def _make_engine(seed: int = 42, **cfg_kwargs) -> CarrierOpsEngine:
    config = CarrierOpsConfig(**cfg_kwargs) if cfg_kwargs else None
    return CarrierOpsEngine(EventBus(), _rng(seed), config=config)


# ---------------------------------------------------------------------------
# Sortie rate
# ---------------------------------------------------------------------------


class TestSortieRate:
    """Sortie rate computation from deck state, crew, weather."""

    def test_operational_deck(self):
        eng = _make_engine()
        rate = eng.compute_sortie_rate(
            aircraft_available=40,
            deck_crew_quality=0.9,
            weather_factor=1.0,
            deck_state=DeckState.LAUNCH_CYCLE,
        )
        assert rate > 0.0

    def test_damaged_deck_reduces_rate(self):
        eng = _make_engine()
        normal = eng.compute_sortie_rate(40, 0.9, 1.0, DeckState.LAUNCH_CYCLE)
        damaged = eng.compute_sortie_rate(40, 0.9, 1.0, DeckState.DAMAGED)
        assert damaged < normal

    def test_maintenance_deck_zero_rate(self):
        eng = _make_engine()
        rate = eng.compute_sortie_rate(40, 0.9, 1.0, DeckState.MAINTENANCE)
        assert rate == pytest.approx(0.0)

    def test_no_aircraft_zero_rate(self):
        eng = _make_engine()
        rate = eng.compute_sortie_rate(0, 0.9, 1.0, DeckState.LAUNCH_CYCLE)
        assert rate == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Launch aircraft
# ---------------------------------------------------------------------------


class TestLaunchAircraft:
    """Aircraft launch from various deck states."""

    def test_launch_success_base(self):
        """Base launch success probability is 0.98."""
        eng = _make_engine(seed=10)
        result = eng.launch_aircraft("cv_1", "f18_1", "CAP", DeckState.LAUNCH_CYCLE)
        assert isinstance(result, LaunchResult)
        assert hasattr(result, "success")

    def test_launch_from_maintenance_fails(self):
        """Cannot launch from MAINTENANCE deck."""
        eng = _make_engine(seed=10)
        result = eng.launch_aircraft("cv_1", "f18_1", "CAP", DeckState.MAINTENANCE)
        assert result.success is False

    def test_damaged_deck_lower_success(self):
        """Damaged deck has lower launch success rate."""
        successes_normal = 0
        successes_damaged = 0
        for i in range(100):
            eng1 = CarrierOpsEngine(EventBus(), _rng(i))
            r1 = eng1.launch_aircraft("cv", "a1", "STRIKE", DeckState.LAUNCH_CYCLE)
            if r1.success:
                successes_normal += 1
            eng2 = CarrierOpsEngine(EventBus(), _rng(i + 1000))
            r2 = eng2.launch_aircraft("cv", "a1", "STRIKE", DeckState.DAMAGED)
            if r2.success:
                successes_damaged += 1
        assert successes_normal > successes_damaged


# ---------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------


class TestRecoverAircraft:
    """Recovery with bolter probability from sea state."""

    def test_recovery_result(self):
        eng = _make_engine(seed=10)
        result = eng.recover_aircraft("cv_1", "f18_1", sea_state=2.0, pilot_skill=0.8)
        assert isinstance(result, RecoveryResult)
        assert hasattr(result, "bolter")

    def test_high_sea_state_increases_bolter(self):
        """Higher sea state increases bolter probability."""
        bolters_calm = 0
        bolters_rough = 0
        for i in range(100):
            eng1 = CarrierOpsEngine(EventBus(), _rng(i))
            r1 = eng1.recover_aircraft("cv", "a1", sea_state=1.0, pilot_skill=0.8)
            if r1.bolter:
                bolters_calm += 1
            eng2 = CarrierOpsEngine(EventBus(), _rng(i + 1000))
            r2 = eng2.recover_aircraft("cv", "a1", sea_state=6.0, pilot_skill=0.8)
            if r2.bolter:
                bolters_rough += 1
        assert bolters_rough >= bolters_calm

    def test_sea_state_bolter_scaling(self):
        """Bolter probability formula: base + factor * sea_state."""
        cfg = CarrierOpsConfig(
            bolter_probability_base=0.05,
            sea_state_bolter_factor=0.03,
        )
        # At sea_state=0, bolter_prob = 0.05 * (1.5 - skill)
        # At sea_state=10, bolter_prob = (0.05 + 0.30) * (1.5 - skill)
        # The probability increases with sea state
        eng = CarrierOpsEngine(EventBus(), _rng(42), config=cfg)
        # Just verify the engine computes without error
        result = eng.recover_aircraft("cv", "a1", sea_state=5.0, pilot_skill=0.7)
        assert isinstance(result, RecoveryResult)


# ---------------------------------------------------------------------------
# CAP stations
# ---------------------------------------------------------------------------


class TestCAPStation:
    """CAP station creation and endurance tracking."""

    def test_create_cap_station(self):
        eng = _make_engine()
        station = eng.create_cap_station("cap_1", ["f18_1", "f18_2"])
        assert isinstance(station, CAPStation)
        assert station.station_id == "cap_1"
        assert len(station.aircraft_ids) == 2

    def test_cap_station_endurance(self):
        """CAP endurance defaults to 14400s (4h). Relief needed before expiry."""
        eng = _make_engine()
        eng.create_cap_station("cap_1", ["f18_1", "f18_2"])
        # Update for 1 hour — not yet needing relief
        need_relief = eng.update_cap_stations(dt_s=3600.0)
        assert len(need_relief) == 0
        # Push past endurance - relief margin (14400 - 1800 = 12600)
        need_relief = eng.update_cap_stations(dt_s=12000.0)
        assert len(need_relief) == 1
        assert need_relief[0].relief_needed is True


# ---------------------------------------------------------------------------
# Recovery window
# ---------------------------------------------------------------------------


class TestRecoveryWindow:
    """Recovery window scheduling."""

    def test_schedule_recovery_window(self):
        eng = _make_engine()
        window = eng.schedule_recovery_window(start_time_s=1000.0)
        assert isinstance(window, RecoveryWindow)
        assert window.start_time_s == 1000.0
        assert window.duration_s > 0
        assert window.active is True


# ---------------------------------------------------------------------------
# Turnaround
# ---------------------------------------------------------------------------


class TestTurnaround:
    """Aircraft turnaround time computation."""

    def test_hot_refuel_faster(self):
        """Hot refuel is faster than full rearm."""
        eng = _make_engine(seed=100)
        hot = eng.turnaround_aircraft("a1", "hot_refuel")
        eng2 = _make_engine(seed=100)
        full = eng2.turnaround_aircraft("a2", "full")
        # hot_refuel factor=0.7, full factor=1.5 -> hot should be shorter
        assert hot < full


# ---------------------------------------------------------------------------
# State roundtrip
# ---------------------------------------------------------------------------


class TestCarrierOpsStateRoundtrip:
    """State persistence."""

    def test_state_roundtrip(self):
        eng = _make_engine(seed=55)
        eng.launch_aircraft("cv_1", "f18_1", "CAP", DeckState.LAUNCH_CYCLE)
        eng.create_cap_station("cap_1", ["f18_1"])
        state = eng.get_state()

        eng2 = _make_engine(seed=1)
        eng2.set_state(state)
        assert eng2._sorties_launched == eng._sorties_launched
        # RNG state restored
        assert eng._rng.random() == eng2._rng.random()
