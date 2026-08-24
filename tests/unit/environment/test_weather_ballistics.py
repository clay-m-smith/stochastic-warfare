"""Phase 59c: Weather-derived air-density ballistics contracts."""

from __future__ import annotations


import pytest


class TestAirDensityOverride:
    """Ballistics accepts weather-derived air density via conditions dict."""

    def test_default_air_density(self) -> None:
        """Default sea-level density is 1.225 kg/m³."""
        from stochastic_warfare.combat.ballistics import BallisticsConfig

        cfg = BallisticsConfig()
        assert cfg.air_density_sea_level == pytest.approx(1.225)

    def test_air_density_method_accepts_override(self) -> None:
        """_air_density accepts rho0_override parameter."""
        import numpy as np

        from stochastic_warfare.combat.ballistics import BallisticsEngine

        rng = np.random.default_rng(42)
        engine = BallisticsEngine(rng)

        # Default density at sea level
        rho_default = engine._air_density(0.0)
        assert rho_default == pytest.approx(1.225)

        # Override density
        rho_override = engine._air_density(0.0, rho0_override=1.1)
        assert rho_override == pytest.approx(1.1)
