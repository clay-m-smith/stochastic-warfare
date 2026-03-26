"""Phase 88c: SoA integration — morale/engagement data extraction, scenario parity."""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.entities.personnel import CrewMember, CrewRole, InjuryState, SkillLevel
from stochastic_warfare.simulation.unit_arrays import UnitArrays


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_unit(
    eid: str,
    side: str = "blue",
    pos: tuple[float, float] = (0.0, 0.0),
    status: UnitStatus = UnitStatus.ACTIVE,
) -> Unit:
    return Unit(
        entity_id=eid,
        position=Position(pos[0], pos[1]),
        name=eid,
        unit_type="infantry",
        side=side,
        status=status,
    )


def _make_crew(n: int, wounded: int = 0) -> list[CrewMember]:
    crew = []
    for i in range(n):
        inj = InjuryState.SERIOUS_WOUND if i < wounded else InjuryState.HEALTHY
        crew.append(CrewMember(
            member_id=f"m{i}",
            role=CrewRole.RIFLEMAN,
            skill=SkillLevel.TRAINED,
            experience=0.5,
            injury=inj,
        ))
    return crew


# ---------------------------------------------------------------------------
# 88c: Morale batch extraction
# ---------------------------------------------------------------------------


class TestMoraleBatchExtraction:
    """Pre-extracted morale arrays match morale_states dict."""

    def test_morale_array_matches_dict(self):
        morale_states = {"u1": 0, "u2": 1, "u3": 3, "u4": 2}
        units = {
            "a": [_make_unit("u1"), _make_unit("u2")],
            "b": [_make_unit("u3", "b"), _make_unit("u4", "b")],
        }
        ua = UnitArrays.from_units(units, morale_states=morale_states)
        for i, uid in enumerate(ua.unit_ids):
            assert ua.morale_state[i] == morale_states[uid]

    def test_health_array_matches_personnel(self):
        """Health extraction matches per-unit effective fraction."""
        crews = [
            _make_crew(4, wounded=0),  # 1.0
            _make_crew(4, wounded=2),  # 0.5
            _make_crew(4, wounded=4),  # 0.0
        ]
        units = {"a": []}
        for i, c in enumerate(crews):
            u = _make_unit(f"u{i}")
            u.personnel = c
            units["a"].append(u)

        ua = UnitArrays.from_units(units)
        assert ua.health[0] == pytest.approx(1.0)
        assert ua.health[1] == pytest.approx(0.5)
        assert ua.health[2] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 88c: Engagement data — position arrays
# ---------------------------------------------------------------------------


class TestEngagementPositions:
    """Engagement phase position arrays from SoA."""

    def test_get_side_positions(self):
        units = {
            "blue": [_make_unit("b1", "blue", (100, 200)),
                     _make_unit("b2", "blue", (300, 400))],
            "red": [_make_unit("r1", "red", (1000, 1000))],
        }
        ua = UnitArrays.from_units(units)
        bp = ua.get_side_positions("blue")
        assert bp.shape == (2, 2)
        assert bp[0, 0] == pytest.approx(100.0)
        assert bp[1, 1] == pytest.approx(400.0)

    def test_distance_matches_per_pair(self):
        """SoA distance matrix matches per-pair manual computation."""
        import math
        units = {
            "blue": [_make_unit("b1", "blue", (0, 0)),
                     _make_unit("b2", "blue", (100, 0))],
            "red": [_make_unit("r1", "red", (50, 50))],
        }
        ua = UnitArrays.from_units(units)
        dm = ua.distance_matrix("blue", "red")

        # b1 → r1: sqrt(50² + 50²) = 70.71
        assert dm[0, 0] == pytest.approx(math.sqrt(50**2 + 50**2))
        # b2 → r1: sqrt((-50)² + 50²) = 70.71
        assert dm[1, 0] == pytest.approx(math.sqrt(50**2 + 50**2))


# ---------------------------------------------------------------------------
# 88c: Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    """enable_soa=False produces no behavioral change."""

    def test_enable_soa_default_false(self):
        from stochastic_warfare.simulation.calibration import CalibrationSchema
        cal = CalibrationSchema()
        assert cal.enable_soa is False

    def test_enable_soa_in_flat_dict(self):
        from stochastic_warfare.simulation.calibration import CalibrationSchema
        cal = CalibrationSchema(enable_soa=True)
        flat = cal.to_flat_dict(["blue", "red"])
        assert flat["enable_soa"] is True


# ---------------------------------------------------------------------------
# 88c: Structural tests
# ---------------------------------------------------------------------------


class TestStructural:
    """Structural verification — UnitArrays wired into battle loop."""

    def test_unit_arrays_imported_in_battle(self):
        from stochastic_warfare.simulation import battle
        assert hasattr(battle, "UnitArrays")

    def test_execute_tick_builds_unit_arrays(self):
        from stochastic_warfare.simulation.battle import BattleManager
        src = inspect.getsource(BattleManager.execute_tick)
        assert "UnitArrays.from_units" in src
        assert "enable_soa" in src

    def test_unit_arrays_rebuilt_after_movement(self):
        """UnitArrays is rebuilt after movement phase."""
        from stochastic_warfare.simulation.battle import BattleManager
        src = inspect.getsource(BattleManager.execute_tick)
        # Should have two UnitArrays.from_units calls (pre-movement + post-movement)
        count = src.count("UnitArrays.from_units")
        assert count == 2, f"Expected 2 UnitArrays.from_units calls, found {count}"

    def test_get_active_enemy_indices(self):
        units = {
            "blue": [_make_unit("b1", "blue", (0, 0))],
            "red": [
                _make_unit("r1", "red", (100, 100)),
                _make_unit("r2", "red", (200, 200), status=UnitStatus.DESTROYED),
                _make_unit("r3", "red", (300, 300)),
            ],
        }
        ua = UnitArrays.from_units(units)
        indices = ua.get_active_enemy_indices("blue")
        # r1 (flat idx 1) and r3 (flat idx 3) are active enemies
        assert len(indices) == 2
        # Verify these are the right units
        for idx in indices:
            assert ua.operational[idx]
            assert ua.side_indices[idx] != 0  # not blue
