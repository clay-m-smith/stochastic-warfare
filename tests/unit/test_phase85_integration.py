"""Phase 85: LOD integration tests.

Validates that LOD tier classification integrates correctly with
engagement, morale, supply, and FOW subsystems in the battle loop.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.morale.runtime import MoraleRegistration, MoraleRuntime
from stochastic_warfare.morale.state import MoraleConfig, MoraleState
from stochastic_warfare.simulation.battle import BattleManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_unit(uid: str, easting: float = 0.0, side: str = "blue") -> SimpleNamespace:
    return SimpleNamespace(
        entity_id=uid,
        position=Position(easting, 0.0, 0.0),
        status=UnitStatus.ACTIVE,
        side=side,
        speed=5.0,
        heading=0.0,
        domain=Domain.GROUND,
        unit_type="infantry",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLodMoraleIntegration:
    """LOD filtering in _execute_morale()."""

    def test_lod_preserves_morale_for_distant(self):
        """LOD affects sensing cadence, not discrete-time morale work."""
        bus = EventBus()
        bm = BattleManager(event_bus=bus)
        u_active = Unit(
            entity_id="u1",
            position=Position(0.0, 0.0, 0.0),
            side="blue",
        )
        u_distant = Unit(
            entity_id="u2",
            position=Position(50_000.0, 0.0, 0.0),
            side="blue",
        )
        morale_runtime = MoraleRuntime(
            bus,
            np.random.default_rng(85),
            MoraleConfig(
                base_degrade_rate=0.0,
                base_recover_rate=0.0,
                casualty_weight=0.0,
                suppression_weight=0.0,
                leadership_weight=0.0,
                cohesion_weight=0.0,
                force_ratio_weight=0.0,
            ),
        )
        morale_runtime.register_units(
            (
                MoraleRegistration("u1", MoraleState.STEADY),
                MoraleRegistration("u2", MoraleState.STEADY),
            ),
            {"u1": u_active, "u2": u_distant},
        )
        ctx = SimpleNamespace(
            calibration={"morale_degrade_rate_modifier": 1.0},
            morale_runtime=morale_runtime,
            morale_states=morale_runtime.states,
            clock=SimpleNamespace(elapsed=timedelta(seconds=100.0)),
        )
        units_by_side = {"blue": [u_active, u_distant]}
        active_enemies = {"blue": []}

        bm._execute_morale(
            ctx, units_by_side, active_enemies,
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert morale_runtime.record_for("u1").generation == 1
        assert morale_runtime.record_for("u2").generation == 1


class TestCombatConsumptionBoundary:
    """Combat consumption remains an explicit, unwired residual gap."""

    def test_compute_and_discard_hook_is_not_exposed(self):
        """A non-mutating helper must not masquerade as supply consumption."""
        bm = BattleManager(event_bus=EventBus())
        assert not hasattr(bm, "_execute_supply_consumption")


class TestLodBackwardCompat:
    """LOD disabled = identical behavior."""

    def test_enable_lod_false_backward_compat(self):
        """Disabled LOD records every active unit at native sensing cadence."""
        bm = BattleManager(event_bus=EventBus())
        units = [_make_unit(f"u{i}", float(i * 100)) for i in range(5)]
        units_by_side = {"blue": units}
        enemy = np.array([[50_000.0, 0.0]])
        ctx = SimpleNamespace(
            calibration={"enable_lod": False},
            unit_weapons={},
            unit_sensors={},
        )
        plan = bm._stage_lod_tiers(
            ctx,
            units_by_side,
            {"blue": enemy},
        )
        assert plan.receipt.active_classifications == 5
        assert plan.receipt.nearby_classifications == 0
        assert plan.receipt.distant_classifications == 0

    @pytest.mark.structural
    def test_non_sensing_owners_expose_no_lod_skip_control(self):
        """Combat, morale, and movement cannot re-enable obsolete LOD skips."""
        import inspect

        for method in (
            BattleManager._execute_engagements,
            BattleManager._execute_morale,
            BattleManager._execute_movement,
        ):
            assert "_lod_full_update" not in inspect.signature(method).parameters
