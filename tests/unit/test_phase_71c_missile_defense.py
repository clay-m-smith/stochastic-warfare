"""Phase 71c: missile defense intercept tests.

Verifies MissileDefenseEngine instantiation on SimulationContext and
intercept wiring in the battle loop.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.combat.missile_defense import (
    MissileDefenseEngine,
)
from stochastic_warfare.core.events import EventBus

TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _make_rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


@pytest.fixture
def md_engine():
    bus = EventBus()
    rng = _make_rng()
    return MissileDefenseEngine(event_bus=bus, rng=rng)


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------


class TestMissileDefenseInstantiation:
    """Verify MissileDefenseEngine is on SimulationContext."""

    def test_context_has_missile_defense_field(self):
        """SimulationContext should have missile_defense_engine field."""
        import inspect
        from stochastic_warfare.simulation.scenario import SimulationContext

        src = inspect.getsource(SimulationContext)
        assert "missile_defense_engine" in src

    def test_create_engines_instantiates_defense(self):
        """_create_engines should instantiate MissileDefenseEngine."""
        import inspect
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        src = inspect.getsource(ScenarioLoader._create_engines)
        assert "MissileDefenseEngine" in src
        assert "missile_defense_engine" in src

    def test_result_dict_includes_defense(self):
        """Engines result dict should include missile_defense_engine."""
        import inspect
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        src = inspect.getsource(ScenarioLoader._create_engines)
        assert '"missile_defense_engine"' in src


# ---------------------------------------------------------------------------
# Cruise missile defense
# ---------------------------------------------------------------------------


class TestCruiseMissileDefense:
    """Test engage_cruise_missile behavior."""

    def test_cruise_intercept_returns_result(self, md_engine):
        """engage_cruise_missile returns a CruiseMissileDefenseResult."""
        result = md_engine.engage_cruise_missile(
            defender_pk=0.9,
            missile_speed_mps=250.0,
            sea_skimming=False,
            defender_id="sam_1",
            missile_id="cm_1",
        )
        assert hasattr(result, "hit")
        assert hasattr(result, "effective_pk")

    def test_high_pk_intercepts(self):
        """Defender with near-perfect Pk should usually intercept."""
        bus = EventBus()
        intercepts = 0
        for seed in range(30):
            rng = _make_rng(seed)
            eng = MissileDefenseEngine(event_bus=bus, rng=rng)
            result = eng.engage_cruise_missile(
                defender_pk=0.99,
                missile_speed_mps=250.0,
                sea_skimming=False,
            )
            if result.hit:
                intercepts += 1
        assert intercepts > 20, f"Expected >20/30 intercepts at Pk=0.99, got {intercepts}"

    def test_sea_skimming_reduces_pk(self):
        """Sea-skimming missiles should be harder to intercept."""
        bus = EventBus()
        hits_normal = 0
        hits_skimming = 0
        n = 50

        for seed in range(n):
            rng = _make_rng(seed)
            eng = MissileDefenseEngine(event_bus=bus, rng=rng)
            r = eng.engage_cruise_missile(defender_pk=0.7, sea_skimming=False)
            if r.hit:
                hits_normal += 1

        for seed in range(n):
            rng = _make_rng(seed + 1000)
            eng = MissileDefenseEngine(event_bus=bus, rng=rng)
            r = eng.engage_cruise_missile(defender_pk=0.7, sea_skimming=True)
            if r.hit:
                hits_skimming += 1

        # Sea skimming penalty should reduce effective Pk
        assert hits_normal >= hits_skimming, (
            f"Normal ({hits_normal}) should intercept >= sea-skimming ({hits_skimming})"
        )

    def test_zero_pk_never_intercepts(self, md_engine):
        """Defender with Pk=0 should never intercept."""
        result = md_engine.engage_cruise_missile(
            defender_pk=0.0,
            missile_speed_mps=250.0,
        )
        assert not result.hit


# ---------------------------------------------------------------------------
# Ballistic missile defense
# ---------------------------------------------------------------------------


class TestBallisticMissileDefense:
    """Test engage_ballistic_missile behavior."""

    def test_bmd_returns_result(self, md_engine):
        """engage_ballistic_missile returns a BMDResult."""
        result = md_engine.engage_ballistic_missile(
            defender_pks=[0.8],
            missile_speed_mps=3000.0,
            defender_id="bmd_1",
            missile_id="tbm_1",
        )
        assert hasattr(result, "intercepted")
        assert hasattr(result, "cumulative_pk")
        assert hasattr(result, "layers_engaged")

    def test_multilayer_defense(self, md_engine):
        """Multiple defense layers improve cumulative Pk."""
        result = md_engine.engage_ballistic_missile(
            defender_pks=[0.5, 0.5, 0.5],
            missile_speed_mps=3000.0,
        )
        # Cumulative Pk should be higher than single layer
        assert result.cumulative_pk > 0.5
        # layers_engaged may be < 3 if an early layer intercepts
        assert result.layers_engaged >= 1
        assert result.layers_engaged <= 3


# ---------------------------------------------------------------------------
# Battle loop integration (structural)
# ---------------------------------------------------------------------------


class TestMissileDefenseBattleLoop:
    """Verify missile defense intercept is wired into battle.py."""

    def test_battle_loop_has_defense_intercept(self):
        """battle.py execute_tick should contain missile defense intercept code."""
        import inspect
        from stochastic_warfare.simulation.battle import BattleManager

        src = inspect.getsource(BattleManager.execute_tick)
        assert "missile_defense_engine" in src

    def test_intercept_deactivates_missile(self):
        """Successful intercept should set missile.active = False."""
        import inspect
        from stochastic_warfare.simulation.battle import BattleManager

        src = inspect.getsource(BattleManager.execute_tick)
        # After intercept, missile should be deactivated
        assert "_m71.active = False" in src

    def test_ad_unit_identified_by_weapon_category(self):
        """AD units should be identified by SAM/CIWS/MISSILE_LAUNCHER weapon category."""
        import inspect
        from stochastic_warfare.simulation.battle import BattleManager

        src = inspect.getsource(BattleManager.execute_tick)
        assert '"SAM"' in src or "'SAM'" in src
        assert '"CIWS"' in src or "'CIWS'" in src
