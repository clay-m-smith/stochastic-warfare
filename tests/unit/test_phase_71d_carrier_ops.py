"""Phase 71d: carrier ops battle loop tests.

Verifies CarrierOpsEngine wiring in the battle loop — CAP station updates,
sortie rate computation, Beaufort sea state gating, and enable_carrier_ops flag.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.combat.carrier_ops import (
    CarrierOpsEngine,
    CarrierOpsConfig,
    DeckState,
)
from stochastic_warfare.core.events import EventBus

TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _make_rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


@pytest.fixture
def carrier_engine():
    bus = EventBus()
    rng = _make_rng()
    return CarrierOpsEngine(event_bus=bus, rng=rng)


# ---------------------------------------------------------------------------
# CAP station management
# ---------------------------------------------------------------------------


class TestCAPStations:
    """Test CAP station update mechanics."""

    def test_update_cap_stations(self, carrier_engine):
        """update_cap_stations should return list of CAPStation."""
        station = carrier_engine.create_cap_station(
            station_id="cap_1",
            aircraft_ids=["f18_1", "f18_2"],
        )
        results = carrier_engine.update_cap_stations(dt_s=60.0)
        assert isinstance(results, list)

    def test_cap_relief_after_endurance(self, carrier_engine):
        """CAP station flags relief_needed after endurance exceeded."""
        config = CarrierOpsConfig(cap_station_endurance_s=100.0, cap_relief_margin_s=10.0)
        bus = EventBus()
        eng = CarrierOpsEngine(event_bus=bus, rng=_make_rng(), config=config)
        eng.create_cap_station(station_id="cap_1", aircraft_ids=["f18_1"])
        # Advance past endurance - relief margin
        for _ in range(10):
            results = eng.update_cap_stations(dt_s=10.0)  # 100s total
        # Should flag relief needed (100s >= endurance_s - margin_s = 90s)
        assert any(s.relief_needed for s in results)


# ---------------------------------------------------------------------------
# Sortie rate computation
# ---------------------------------------------------------------------------


class TestSortieRate:
    """Test carrier sortie rate computation."""

    def test_sortie_rate_scales_with_aircraft(self, carrier_engine):
        """More available aircraft increases sortie rate."""
        rate_low = carrier_engine.compute_sortie_rate(
            aircraft_available=2,
            deck_crew_quality=0.8,
            weather_factor=1.0,
            deck_state=DeckState.IDLE,
        )
        rate_high = carrier_engine.compute_sortie_rate(
            aircraft_available=20,
            deck_crew_quality=0.8,
            weather_factor=1.0,
            deck_state=DeckState.IDLE,
        )
        assert rate_high > rate_low

    def test_zero_aircraft_zero_sorties(self, carrier_engine):
        """No aircraft means zero sortie rate."""
        rate = carrier_engine.compute_sortie_rate(
            aircraft_available=0,
            deck_crew_quality=0.8,
            weather_factor=1.0,
            deck_state=DeckState.IDLE,
        )
        assert rate == 0.0

    def test_damaged_deck_reduces_rate(self, carrier_engine):
        """Damaged deck state reduces sortie rate."""
        rate_idle = carrier_engine.compute_sortie_rate(
            aircraft_available=10,
            deck_crew_quality=0.8,
            weather_factor=1.0,
            deck_state=DeckState.IDLE,
        )
        rate_damaged = carrier_engine.compute_sortie_rate(
            aircraft_available=10,
            deck_crew_quality=0.8,
            weather_factor=1.0,
            deck_state=DeckState.DAMAGED,
        )
        assert rate_damaged < rate_idle

    def test_weather_scales_rate(self, carrier_engine):
        """Poor weather reduces sortie rate."""
        rate_clear = carrier_engine.compute_sortie_rate(
            aircraft_available=10,
            deck_crew_quality=0.8,
            weather_factor=1.0,
            deck_state=DeckState.IDLE,
        )
        rate_storm = carrier_engine.compute_sortie_rate(
            aircraft_available=10,
            deck_crew_quality=0.8,
            weather_factor=0.3,
            deck_state=DeckState.IDLE,
        )
        assert rate_storm < rate_clear


# ---------------------------------------------------------------------------
# CalibrationSchema flag
# ---------------------------------------------------------------------------


class TestCarrierOpsCalibration:
    """Test enable_carrier_ops CalibrationSchema field."""

    def test_enable_carrier_ops_exists(self):
        """CalibrationSchema should have enable_carrier_ops field."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        cal = CalibrationSchema()
        assert hasattr(cal, "enable_carrier_ops")
        assert cal.enable_carrier_ops is False

    def test_enable_carrier_ops_parseable(self):
        """enable_carrier_ops should be settable from YAML dict."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        cal = CalibrationSchema(enable_carrier_ops=True)
        assert cal.enable_carrier_ops is True


# ---------------------------------------------------------------------------
# Battle loop integration (structural)
# ---------------------------------------------------------------------------


class TestCarrierOpsBattleLoop:
    """Verify carrier ops wired into battle.py execute_tick."""

    def test_battle_loop_has_carrier_ops(self):
        """battle.py execute_tick should contain carrier ops code."""
        import inspect
        from stochastic_warfare.simulation.battle import BattleManager

        src = inspect.getsource(BattleManager.execute_tick)
        assert "carrier_ops_engine" in src

    def test_enable_carrier_ops_gates_processing(self):
        """Carrier ops should be gated by enable_carrier_ops."""
        import inspect
        from stochastic_warfare.simulation.battle import BattleManager

        src = inspect.getsource(BattleManager.execute_tick)
        assert "enable_carrier_ops" in src

    def test_beaufort_gate_in_battle_loop(self):
        """Beaufort > 7 should suspend flight ops."""
        import inspect
        from stochastic_warfare.simulation.battle import BattleManager

        src = inspect.getsource(BattleManager.execute_tick)
        assert "7.0" in src  # Beaufort threshold
        assert "flight ops suspended" in src

    def test_carrier_unit_identified(self):
        """Carrier unit identification by unit_type."""
        import inspect
        from stochastic_warfare.simulation.battle import BattleManager

        src = inspect.getsource(BattleManager.execute_tick)
        # Should check for "carrier" or "cv" in unit_type
        assert '"carrier"' in src or "'carrier'" in src

    def test_compute_sortie_rate_called(self):
        """Carrier ops should compute sortie rate."""
        import inspect
        from stochastic_warfare.simulation.battle import BattleManager

        src = inspect.getsource(BattleManager.execute_tick)
        assert "compute_sortie_rate" in src

    def test_update_cap_stations_called(self):
        """Carrier ops should update CAP stations."""
        import inspect
        from stochastic_warfare.simulation.battle import BattleManager

        src = inspect.getsource(BattleManager.execute_tick)
        assert "update_cap_stations" in src
