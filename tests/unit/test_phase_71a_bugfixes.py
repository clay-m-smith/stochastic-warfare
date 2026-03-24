"""Phase 71a: bug-fix tests — _sim_time_s ordering and missing launch_missile args."""

from __future__ import annotations

import inspect


from stochastic_warfare.combat.engagement import EngagementEngine


# ---------------------------------------------------------------------------
# 71a-1: _sim_time_s used before assignment
# ---------------------------------------------------------------------------


class TestSimTimeOrdering:
    """Verify _sim_time_s is available before ATO sortie reset."""

    def _get_step_source(self) -> str:
        from stochastic_warfare.simulation.engine import SimulationEngine

        return inspect.getsource(SimulationEngine.step)

    def test_sim_time_computed_before_sortie_reset(self):
        """engine.py should compute _sim_time_s before the _cur_day_69a check."""
        src = self._get_step_source()
        assign_idx = src.index("_sim_time_s = ctx.clock.elapsed.total_seconds()")
        day_idx = src.index("_cur_day_69a = int(_sim_time_s / 86400)")
        assert assign_idx < day_idx, (
            "_sim_time_s must be computed before _cur_day_69a"
        )

    def test_no_duplicate_sim_time_assignment(self):
        """There should be exactly one _sim_time_s assignment in step()."""
        src = self._get_step_source()
        count = src.count("_sim_time_s = ctx.clock.elapsed.total_seconds()")
        assert count == 1, f"Expected 1 _sim_time_s assignment, found {count}"

    def test_sim_time_before_ato_block(self):
        """_sim_time_s computed before ATO engine usage."""
        src = self._get_step_source()
        assign_idx = src.index("_sim_time_s = ctx.clock.elapsed.total_seconds()")
        ato_idx = src.index("ato_engine")
        assert assign_idx < ato_idx


# ---------------------------------------------------------------------------
# 71a-2: Missing launcher_id / missile_id in engagement.py
# ---------------------------------------------------------------------------


class TestLaunchMissileArgs:
    """Verify COASTAL_DEFENSE and AIR_LAUNCHED_ASHM pass required args."""

    def _get_route_source(self) -> str:
        return inspect.getsource(EngagementEngine.route_engagement)

    def test_coastal_defense_has_launcher_id(self):
        """COASTAL_DEFENSE launch_missile call must include launcher_id."""
        src = self._get_route_source()
        # Find the if-block for COASTAL_DEFENSE engagement type
        idx = src.index("EngagementType.COASTAL_DEFENSE")
        block = src[idx:idx + 800]
        assert "launcher_id=" in block, "COASTAL_DEFENSE missing launcher_id"

    def test_coastal_defense_has_missile_id(self):
        """COASTAL_DEFENSE launch_missile call must include missile_id."""
        src = self._get_route_source()
        idx = src.index("EngagementType.COASTAL_DEFENSE")
        block = src[idx:idx + 800]
        assert "missile_id=" in block, "COASTAL_DEFENSE missing missile_id"

    def test_air_launched_ashm_has_launcher_id(self):
        """AIR_LAUNCHED_ASHM launch_missile call must include launcher_id."""
        src = self._get_route_source()
        idx = src.index("EngagementType.AIR_LAUNCHED_ASHM")
        block = src[idx:idx + 800]
        assert "launcher_id=" in block, "AIR_LAUNCHED_ASHM missing launcher_id"

    def test_air_launched_ashm_has_missile_id(self):
        """AIR_LAUNCHED_ASHM launch_missile call must include missile_id."""
        src = self._get_route_source()
        idx = src.index("EngagementType.AIR_LAUNCHED_ASHM")
        block = src[idx:idx + 800]
        assert "missile_id=" in block, "AIR_LAUNCHED_ASHM missing missile_id"

    def test_missile_handler_unchanged(self):
        """MISSILE handler should still have launcher_id and missile_id (regression)."""
        src = self._get_route_source()
        idx = src.index("EngagementType.MISSILE")
        block = src[idx:idx + 600]
        assert "launcher_id=attacker_id" in block
        assert "missile_id=" in block
