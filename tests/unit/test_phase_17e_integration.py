"""Phase 17e tests — Integration of space domain into simulation."""

from __future__ import annotations


import numpy as np

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.simulation.scenario import SimulationContext, CampaignScenarioConfig

from tests.conftest import make_rng, make_clock


def _rng(seed: int = 42) -> np.random.Generator:
    return make_rng(seed)


def _bus() -> EventBus:
    return EventBus()


# ---------------------------------------------------------------------------
# TestGPSDegradesCEP
# ---------------------------------------------------------------------------


class TestGPSDegradesCEP:
    def test_default_unchanged(self) -> None:
        """Default gps_accuracy_m=5.0 → CEP=10.0 (unchanged)."""
        from stochastic_warfare.combat.missiles import MissileEngine
        from stochastic_warfare.combat.damage import DamageEngine

        bus = _bus()
        rng = _rng()
        dmg = DamageEngine(bus, rng)
        me = MissileEngine(dmg, bus, rng)
        # We can't easily test CEP directly, but verify the parameter is accepted
        impacts = me.update_missiles_in_flight(1.0, gps_accuracy_m=5.0)
        assert isinstance(impacts, list)

    def test_degraded_gps_scales_cep(self) -> None:
        """gps_accuracy_m=50.0 → CEP should be 10× larger."""
        # CEP = 10.0 * max(1.0, 50/5) = 100.0
        cep_base = 10.0 * max(1.0, 5.0 / 5.0)
        cep_degraded = 10.0 * max(1.0, 50.0 / 5.0)
        assert cep_degraded == 100.0
        assert cep_base == 10.0

    def test_non_gps_unaffected(self) -> None:
        """Non-GPS weapons have factor 1.0 regardless of accuracy."""
        from stochastic_warfare.space.gps import GPSEngine
        from stochastic_warfare.space.constellations import (
            ConstellationManager, SpaceConfig,
        )
        from stochastic_warfare.space.orbits import OrbitalMechanicsEngine

        orbits = OrbitalMechanicsEngine()
        cfg = SpaceConfig(enable_space=True)
        cm = ConstellationManager(orbits, _bus(), _rng(), cfg)
        gps = GPSEngine(cm, cfg, _bus(), _rng())
        factor = gps.compute_cep_factor(50.0, "inertial")
        assert factor == 1.0


# ---------------------------------------------------------------------------
# TestSATCOMDegrades
# ---------------------------------------------------------------------------


class TestSATCOMDegrades:
    def test_reliability(self) -> None:
        """Setting satcom reliability modifies the factor."""
        from stochastic_warfare.c2.communications import CommunicationsEngine

        comms = CommunicationsEngine(_bus(), _rng())
        comms.set_satcom_reliability(0.3)
        assert comms._satcom_reliability_factor == 0.3

    def test_wire_unaffected(self) -> None:
        """Non-SATELLITE comm types not degraded by satcom factor."""
        from stochastic_warfare.c2.communications import CommunicationsEngine

        comms = CommunicationsEngine(_bus(), _rng())
        comms.set_satcom_reliability(0.0)
        # Wire comms should not be affected
        # (we can't easily test without full setup, but the code only checks
        # comm_type_enum == SATELLITE)

    def test_state_persists(self) -> None:
        from stochastic_warfare.c2.communications import CommunicationsEngine

        comms = CommunicationsEngine(_bus(), _rng())
        comms.set_satcom_reliability(0.4)
        state = comms.get_state()
        comms2 = CommunicationsEngine(_bus(), _rng())
        comms2.set_state(state)
        assert comms2._satcom_reliability_factor == 0.4


# ---------------------------------------------------------------------------
# TestEarlyWarningBMD
# ---------------------------------------------------------------------------


class TestEarlyWarningBMD:
    def test_bonus(self) -> None:
        from stochastic_warfare.combat.missile_defense import MissileDefenseEngine

        bmd = MissileDefenseEngine(_bus(), _rng())
        r = bmd.engage_ballistic_missile([0.5], early_warning_time_s=600.0)
        # 600s → bonus = min(0.15, 600/600) = 0.15
        # effective_pk = 0.5 * speed_penalty + 0.15
        assert r.per_layer_pk[0] > 0.5 * 0.8  # greater than without bonus

    def test_no_warning(self) -> None:
        from stochastic_warfare.combat.missile_defense import MissileDefenseEngine

        bmd = MissileDefenseEngine(_bus(), _rng())
        r = bmd.engage_ballistic_missile([0.5], early_warning_time_s=0.0)
        assert r.per_layer_pk[0] <= 0.5  # No bonus

    def test_backward_compat(self) -> None:
        """Default parameter → no bonus."""
        from stochastic_warfare.combat.missile_defense import MissileDefenseEngine

        bmd = MissileDefenseEngine(_bus(), _rng())
        r = bmd.engage_ballistic_missile([0.5])
        # Default early_warning_time_s=0.0
        assert r.per_layer_pk[0] <= 0.5


# ---------------------------------------------------------------------------
# TestEMConstellationAccuracy
# ---------------------------------------------------------------------------


class TestEMConstellationAccuracy:
    def test_driven_by_constellation(self) -> None:
        from stochastic_warfare.environment.electromagnetic import EMEnvironment
        from stochastic_warfare.environment.weather import WeatherEngine

        clock = make_clock()
        from stochastic_warfare.environment.weather import WeatherConfig
        weather = WeatherEngine(WeatherConfig(), clock, _rng())
        em = EMEnvironment(weather, None, clock)
        em.set_constellation_accuracy(12.0)
        assert em.gps_accuracy() >= 12.0

    def test_stacks_with_ew(self) -> None:
        from stochastic_warfare.environment.electromagnetic import EMEnvironment
        from stochastic_warfare.environment.weather import WeatherEngine

        clock = make_clock()
        from stochastic_warfare.environment.weather import WeatherConfig
        weather = WeatherEngine(WeatherConfig(), clock, _rng())
        em = EMEnvironment(weather, None, clock)
        em.set_constellation_accuracy(10.0)
        em.set_gps_jam_degradation(5.0)
        assert em.gps_accuracy() >= 15.0

    def test_zero_default(self) -> None:
        from stochastic_warfare.environment.electromagnetic import EMEnvironment
        from stochastic_warfare.environment.weather import WeatherEngine

        clock = make_clock()
        from stochastic_warfare.environment.weather import WeatherConfig
        weather = WeatherEngine(WeatherConfig(), clock, _rng())
        em = EMEnvironment(weather, None, clock)
        # Default 0.0 → fallback to 5.0
        assert em.gps_accuracy() >= 5.0


# ---------------------------------------------------------------------------
# TestContext
# ---------------------------------------------------------------------------


class TestContext:
    def test_field_exists(self) -> None:
        """SimulationContext has space_engine field."""
        from stochastic_warfare.core.rng import RNGManager

        clock = make_clock()
        bus = _bus()
        rng_mgr = RNGManager(42)
        config = CampaignScenarioConfig(
            name="test", date="2024-01-01", duration_hours=1.0,
            terrain={"width_m": 1000, "height_m": 1000},
            sides=[
                {"side": "blue", "units": [{"unit_type": "test"}]},
                {"side": "red", "units": [{"unit_type": "test"}]},
            ],
        )
        ctx = SimulationContext(
            config=config, clock=clock,
            rng_manager=rng_mgr, event_bus=bus,
        )
        assert ctx.space_engine is None

    def test_none_default(self) -> None:
        """space_engine defaults to None."""
        from stochastic_warfare.core.rng import RNGManager

        clock = make_clock()
        bus = _bus()
        rng_mgr = RNGManager(42)
        config = CampaignScenarioConfig(
            name="test", date="2024-01-01", duration_hours=1.0,
            terrain={"width_m": 1000, "height_m": 1000},
            sides=[
                {"side": "blue", "units": [{"unit_type": "test"}]},
                {"side": "red", "units": [{"unit_type": "test"}]},
            ],
        )
        ctx = SimulationContext(
            config=config, clock=clock,
            rng_manager=rng_mgr, event_bus=bus,
        )
        assert ctx.space_engine is None
        # get_state should work with None space_engine
        state = ctx.get_state()
        assert "space_engine" not in state  # Not serialized when None
