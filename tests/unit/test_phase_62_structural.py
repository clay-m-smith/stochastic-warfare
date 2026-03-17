"""Phase 62 structural verification: source-level string assertions.

Confirms that Phase 62 wiring exists in the correct source files by
searching for key identifiers.  These tests catch regressions 100x
faster than full scenario runs.
"""

from __future__ import annotations

import pathlib

import pytest

_SRC = pathlib.Path(__file__).resolve().parents[2] / "stochastic_warfare"

_CALIBRATION = (_SRC / "simulation" / "calibration.py").read_text()
_BATTLE = (_SRC / "simulation" / "battle.py").read_text()
_DISPERSAL = (_SRC / "cbrn" / "dispersal.py").read_text()
_ENGINE = (_SRC / "simulation" / "engine.py").read_text()
_CBRN_ENGINE = (_SRC / "cbrn" / "engine.py").read_text()


class TestPhase62Structural:
    """Source-level assertions for Phase 62 wiring."""

    def test_enable_human_factors_in_calibration(self) -> None:
        assert "enable_human_factors" in _CALIBRATION

    def test_enable_cbrn_environment_in_calibration(self) -> None:
        assert "enable_cbrn_environment" in _CALIBRATION

    def test_enable_air_combat_environment_in_calibration(self) -> None:
        assert "enable_air_combat_environment" in _CALIBRATION

    def test_wbgt_in_battle(self) -> None:
        assert "_compute_wbgt" in _BATTLE

    def test_wind_chill_in_battle(self) -> None:
        assert "_compute_wind_chill" in _BATTLE

    def test_altitude_sickness_in_battle(self) -> None:
        assert "altitude_sickness" in _BATTLE or "altitude_performance" in _BATTLE

    def test_apply_weather_effects_in_dispersal(self) -> None:
        assert "apply_weather_effects" in _DISPERSAL

    def test_washout_in_dispersal(self) -> None:
        assert "washout" in _DISPERSAL

    def test_cloud_ceiling_in_battle(self) -> None:
        assert "cloud_ceiling" in _BATTLE

    def test_icing_in_battle(self) -> None:
        assert "icing" in _BATTLE.lower()

    def test_energy_state_in_battle(self) -> None:
        assert "EnergyState" in _BATTLE

    def test_cbrn_environment_forwarded_in_engine(self) -> None:
        assert "enable_cbrn_environment" in _ENGINE or "enable_cbrn_environment" in _CBRN_ENGINE

    def test_mopp_fov_reduction_in_battle(self) -> None:
        assert "mopp_fov_reduction" in _BATTLE

    def test_mopp_reload_factor_in_battle(self) -> None:
        assert "mopp_reload_factor" in _BATTLE

    def test_mopp_comms_factor_in_battle(self) -> None:
        assert "mopp_comms_factor" in _BATTLE

    def test_arrhenius_in_dispersal(self) -> None:
        assert "arrhenius" in _DISPERSAL.lower()

    def test_icing_radar_penalty_in_battle(self) -> None:
        assert "icing_radar_penalty_db" in _BATTLE
