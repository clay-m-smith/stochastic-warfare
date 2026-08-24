"""Phase 62 infrastructure: CalibrationSchema human-factors, CBRN-environment, and air-combat-environment flags."""

from __future__ import annotations

import pytest

from stochastic_warfare.simulation.calibration import CalibrationSchema


class TestCalibrationSchemaPhase62:
    """Three new enable flags + rate/factor params accepted and default correctly."""

    def test_enable_human_factors_default_false(self) -> None:
        cal = CalibrationSchema()
        assert cal.enable_human_factors is False

    def test_enable_cbrn_environment_default_false(self) -> None:
        cal = CalibrationSchema()
        assert cal.enable_cbrn_environment is False

    def test_enable_air_combat_environment_default_false(self) -> None:
        cal = CalibrationSchema()
        assert cal.enable_air_combat_environment is False

    def test_backward_compat_no_phase62_flags_required(self) -> None:
        """CalibrationSchema() still works without specifying any Phase 62 flags."""
        cal = CalibrationSchema()
        assert cal.hit_probability_modifier == 1.0
        assert cal.enable_human_factors is False
        assert cal.enable_cbrn_environment is False
        assert cal.enable_air_combat_environment is False

    def test_heat_cold_rate_defaults(self) -> None:
        cal = CalibrationSchema()
        assert cal.heat_casualty_base_rate == pytest.approx(0.02)
        assert cal.cold_casualty_base_rate == pytest.approx(0.015)

    def test_mopp_degradation_defaults(self) -> None:
        cal = CalibrationSchema()
        assert cal.mopp_fov_reduction_4 == pytest.approx(0.7)
        assert cal.mopp_reload_factor_4 == pytest.approx(1.5)
        assert cal.mopp_comms_factor_4 == pytest.approx(0.5)
        assert cal.altitude_sickness_threshold_m == pytest.approx(2500.0)
        assert cal.altitude_sickness_rate == pytest.approx(0.03)

    def test_cbrn_environment_param_defaults(self) -> None:
        cal = CalibrationSchema()
        assert cal.cbrn_washout_coefficient == pytest.approx(1e-4)
        assert cal.cbrn_arrhenius_ea == pytest.approx(50000.0)
        assert cal.cbrn_inversion_multiplier == pytest.approx(8.0)
        assert cal.cbrn_uv_degradation_rate == pytest.approx(0.1)

    def test_air_combat_environment_param_defaults(self) -> None:
        cal = CalibrationSchema()
        assert cal.cloud_ceiling_min_attack_m == pytest.approx(500.0)
        assert cal.icing_maneuver_penalty == pytest.approx(0.15)
        assert cal.icing_power_penalty == pytest.approx(0.10)
        assert cal.icing_radar_penalty_db == pytest.approx(3.0)
        assert cal.wind_bvr_missile_speed_mps == pytest.approx(1000.0)

    def test_custom_human_factors_overrides(self) -> None:
        cal = CalibrationSchema(
            enable_human_factors=True,
            heat_casualty_base_rate=0.05,
            cold_casualty_base_rate=0.03,
            mopp_fov_reduction_4=0.5,
            altitude_sickness_rate=0.05,
        )
        assert cal.enable_human_factors is True
        assert cal.heat_casualty_base_rate == pytest.approx(0.05)
        assert cal.cold_casualty_base_rate == pytest.approx(0.03)
        assert cal.mopp_fov_reduction_4 == pytest.approx(0.5)
        assert cal.altitude_sickness_rate == pytest.approx(0.05)

    def test_custom_cbrn_environment_overrides(self) -> None:
        cal = CalibrationSchema(
            enable_cbrn_environment=True,
            cbrn_washout_coefficient=5e-4,
            cbrn_inversion_multiplier=10.0,
        )
        assert cal.enable_cbrn_environment is True
        assert cal.cbrn_washout_coefficient == pytest.approx(5e-4)
        assert cal.cbrn_inversion_multiplier == pytest.approx(10.0)

    def test_custom_air_combat_environment_overrides(self) -> None:
        cal = CalibrationSchema(
            enable_air_combat_environment=True,
            cloud_ceiling_min_attack_m=300.0,
            icing_maneuver_penalty=0.25,
        )
        assert cal.enable_air_combat_environment is True
        assert cal.cloud_ceiling_min_attack_m == pytest.approx(300.0)
        assert cal.icing_maneuver_penalty == pytest.approx(0.25)
