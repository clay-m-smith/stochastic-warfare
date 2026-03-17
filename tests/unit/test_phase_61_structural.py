"""Phase 61 structural verification: code-level wiring checks."""

from __future__ import annotations

from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2] / "stochastic_warfare"


class TestPhase61Structural:
    """Verify all Phase 61 wiring is present at the source level."""

    def test_underwater_acoustics_engine_on_context(self) -> None:
        """underwater_acoustics_engine field present in SimulationContext."""
        src = (_SRC / "simulation" / "scenario.py").read_text()
        assert "underwater_acoustics_engine" in src

    def test_carrier_ops_engine_on_context(self) -> None:
        """carrier_ops_engine field present in SimulationContext."""
        src = (_SRC / "simulation" / "scenario.py").read_text()
        assert "carrier_ops_engine" in src

    def test_beaufort_queried_in_battle(self) -> None:
        """battle.py queries Beaufort sea state for naval ops."""
        src = (_SRC / "simulation" / "battle.py").read_text()
        assert (
            "beaufort_scale" in src
            or "_bf" in src
            or "beaufort" in src
        ), "Expected beaufort_scale, _bf, or beaufort in battle.py"

    def test_tidal_current_queried_in_battle(self) -> None:
        """battle.py queries tidal_current_speed for movement."""
        src = (_SRC / "simulation" / "battle.py").read_text()
        assert "tidal_current_speed" in src

    def test_thermocline_depth_queried_in_battle(self) -> None:
        """battle.py queries thermocline_depth for sonar detection."""
        src = (_SRC / "simulation" / "battle.py").read_text()
        assert "thermocline_depth" in src

    def test_radar_horizon_called_in_battle(self) -> None:
        """battle.py calls radar_horizon for over-horizon detection."""
        src = (_SRC / "simulation" / "battle.py").read_text()
        assert "radar_horizon" in src

    def test_humidity_in_dew_engagement(self) -> None:
        """battle.py passes humidity/precipitation_rate in DEW engagement call."""
        src = (_SRC / "simulation" / "battle.py").read_text()
        assert (
            "humidity=" in src
            or "precipitation_rate=" in src
        ), "Expected humidity= or precipitation_rate= in DEW engagement path"

    def test_hf_propagation_quality_in_communications(self) -> None:
        """communications.py calls hf_propagation_quality."""
        src = (_SRC / "c2" / "communications.py").read_text()
        assert "hf_propagation_quality" in src
