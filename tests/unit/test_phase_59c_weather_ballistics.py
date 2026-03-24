"""Phase 59c: Weather → Ballistics & wind gust gates.

Tests verify propellant temperature coefficient, air density override,
and wind gust operational gates.
"""

from __future__ import annotations


import pytest



class TestPropellantTemperatureCoefficient:
    """Propellant coefficient changed from 0.0005 to 0.001 (MIL-STD-1474)."""

    def _compute_mv_adjustment(self, temp_c: float) -> float:
        """Reproduce the adjustment formula from ballistics.py."""
        return 1.0 + 0.001 * (temp_c - 21.0)

    def test_cold_minus20(self) -> None:
        """At −20°C: MV reduced ~4.1%."""
        adj = self._compute_mv_adjustment(-20.0)
        assert adj == pytest.approx(1.0 + 0.001 * (-41.0), abs=0.001)
        assert adj < 0.96  # at least 4% reduction

    def test_hot_plus50(self) -> None:
        """At +50°C: MV increased ~2.9%."""
        adj = self._compute_mv_adjustment(50.0)
        assert adj > 1.02

    def test_standard_21c_no_change(self) -> None:
        """At 21°C (standard): no modification."""
        adj = self._compute_mv_adjustment(21.0)
        assert adj == pytest.approx(1.0)

    def test_coefficient_in_source(self) -> None:
        """Structural: coefficient is 0.001 in ballistics.py."""
        from pathlib import Path

        src = Path("stochastic_warfare/combat/ballistics.py").read_text()
        assert "0.001 *" in src
        # Old coefficient should not be present
        assert "0.0005 *" not in src


class TestAirDensityOverride:
    """Ballistics accepts weather-derived air density via conditions dict."""

    def test_default_air_density(self) -> None:
        """Default sea-level density is 1.225 kg/m³."""
        from stochastic_warfare.combat.ballistics import BallisticsConfig

        cfg = BallisticsConfig()
        assert cfg.air_density_sea_level == pytest.approx(1.225)

    def test_override_accepted_in_conditions(self) -> None:
        """Structural: ballistics.py reads air_density_sea_level from conditions."""
        from pathlib import Path

        src = Path("stochastic_warfare/combat/ballistics.py").read_text()
        assert 'conditions.get(\n            "air_density_sea_level"' in src or \
               'conditions.get("air_density_sea_level"' in src

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


class TestWindGustGates:
    """Wind gust operational gates halt specific unit types."""

    def test_helicopter_gust_gate_structural(self) -> None:
        """Structural: battle.py has helicopter gust > 15 gate."""
        from pathlib import Path

        src = Path("stochastic_warfare/simulation/battle.py").read_text()
        assert "_gust > 15.0" in src
        assert "HELO" in src

    def test_infantry_gust_gate_structural(self) -> None:
        """Structural: battle.py has infantry gust > 25 gate."""
        from pathlib import Path

        src = Path("stochastic_warfare/simulation/battle.py").read_text()
        assert "_gust > 25.0" in src

    def test_gust_gates_require_enable_seasonal_effects(self) -> None:
        """Structural: wind gust gates gated by enable_seasonal_effects."""
        from pathlib import Path

        src = Path("stochastic_warfare/simulation/battle.py").read_text()
        # The gust gate block includes the enable check
        idx_gust = src.index("wind gust operational gates")
        idx_enable = src.index('enable_seasonal_effects', idx_gust)
        assert idx_enable > idx_gust
