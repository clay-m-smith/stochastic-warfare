"""Phase 88a: UnitArrays SoA data layer — round-trip sync, filtering, distance."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import pytest
from scipy.spatial.distance import cdist

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
    personnel: list[CrewMember] | None = None,
    fuel: float | None = None,
) -> Unit:
    """Build a Unit with optional personnel and fuel."""
    u = Unit(
        entity_id=eid,
        position=Position(pos[0], pos[1]),
        name=eid,
        unit_type="infantry",
        side=side,
        status=status,
    )
    if personnel is not None:
        u.personnel = personnel
    if fuel is not None:
        object.__setattr__(u, "fuel_remaining", fuel)
    return u


def _make_crew(n: int, wounded: int = 0) -> list[CrewMember]:
    """Create n crew members, with *wounded* of them seriously wounded."""
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


def _two_side_setup() -> dict[str, list[Unit]]:
    """Blue: 3 units, Red: 2 units — standard test fixture."""
    return {
        "blue": [
            _make_unit("b1", "blue", (100, 200)),
            _make_unit("b2", "blue", (300, 400)),
            _make_unit("b3", "blue", (500, 600), status=UnitStatus.DESTROYED),
        ],
        "red": [
            _make_unit("r1", "red", (1000, 1000)),
            _make_unit("r2", "red", (2000, 2000)),
        ],
    }


# ---------------------------------------------------------------------------
# 88a: Core round-trip and field extraction
# ---------------------------------------------------------------------------

class TestFromUnits:
    """Verify from_units builds correct SoA arrays."""

    def test_positions_shape_and_values(self):
        units = _two_side_setup()
        ua = UnitArrays.from_units(units)
        assert ua.positions.shape == (5, 2)
        assert ua.positions[0, 0] == pytest.approx(100.0)
        assert ua.positions[0, 1] == pytest.approx(200.0)
        assert ua.positions[3, 0] == pytest.approx(1000.0)

    def test_side_indices(self):
        units = _two_side_setup()
        ua = UnitArrays.from_units(units)
        # blue = 0, red = 1
        assert list(ua.side_indices[:3]) == [0, 0, 0]
        assert list(ua.side_indices[3:]) == [1, 1]

    def test_operational_flags(self):
        units = _two_side_setup()
        ua = UnitArrays.from_units(units)
        assert ua.operational[0] is np.True_   # b1 ACTIVE
        assert ua.operational[2] is np.False_  # b3 DESTROYED
        assert ua.operational[3] is np.True_   # r1 ACTIVE

    def test_unit_ids_order(self):
        units = _two_side_setup()
        ua = UnitArrays.from_units(units)
        assert ua.unit_ids == ["b1", "b2", "b3", "r1", "r2"]

    def test_health_from_personnel(self):
        crew = _make_crew(4, wounded=1)  # 3/4 effective
        units = {"a": [_make_unit("u1", "a", personnel=crew)]}
        ua = UnitArrays.from_units(units)
        assert ua.health[0] == pytest.approx(0.75)

    def test_health_no_personnel(self):
        """Units without personnel default to health=1.0."""
        units = {"a": [_make_unit("u1", "a")]}
        ua = UnitArrays.from_units(units)
        assert ua.health[0] == pytest.approx(1.0)

    def test_fuel_extraction(self):
        units = {"a": [_make_unit("u1", "a", fuel=0.6)]}
        ua = UnitArrays.from_units(units)
        assert ua.fuel[0] == pytest.approx(0.6)

    def test_fuel_default(self):
        """Units without fuel_remaining default to 1.0."""
        units = {"a": [_make_unit("u1", "a")]}
        ua = UnitArrays.from_units(units)
        assert ua.fuel[0] == pytest.approx(1.0)

    def test_morale_extraction(self):
        units = {"a": [_make_unit("u1", "a"), _make_unit("u2", "a")]}
        morale = {"u1": 2, "u2": 0}
        ua = UnitArrays.from_units(units, morale_states=morale)
        assert ua.morale_state[0] == 2
        assert ua.morale_state[1] == 0

    def test_morale_default(self):
        units = {"a": [_make_unit("u1", "a")]}
        ua = UnitArrays.from_units(units)
        assert ua.morale_state[0] == 0  # STEADY

    def test_empty_units(self):
        ua = UnitArrays.from_units({})
        assert ua.n == 0
        assert ua.positions.shape == (0, 2)

    def test_n_property(self):
        units = _two_side_setup()
        ua = UnitArrays.from_units(units)
        assert ua.n == 5


# ---------------------------------------------------------------------------
# 88a: Filtering
# ---------------------------------------------------------------------------

class TestFiltering:
    """Side and operational filtering."""

    def test_side_mask(self):
        units = _two_side_setup()
        ua = UnitArrays.from_units(units)
        mask = ua.side_mask("blue")
        assert mask.sum() == 3
        assert not mask[3] and not mask[4]

    def test_enemy_mask(self):
        units = _two_side_setup()
        ua = UnitArrays.from_units(units)
        mask = ua.enemy_mask("blue")
        # red units that are operational: r1, r2
        assert mask.sum() == 2
        assert mask[3] and mask[4]

    def test_enemy_mask_excludes_non_operational(self):
        units = _two_side_setup()
        # Destroy r1
        units["red"][0].status = UnitStatus.DESTROYED
        ua = UnitArrays.from_units(units)
        mask = ua.enemy_mask("blue")
        assert mask.sum() == 1  # only r2

    def test_get_enemy_positions(self):
        units = _two_side_setup()
        ua = UnitArrays.from_units(units)
        pos = ua.get_enemy_positions("blue")
        assert pos.shape == (2, 2)
        assert pos[0, 0] == pytest.approx(1000.0)
        assert pos[1, 0] == pytest.approx(2000.0)

    def test_get_enemy_positions_empty(self):
        """Single side → no enemies."""
        units = {"a": [_make_unit("u1", "a")]}
        ua = UnitArrays.from_units(units)
        pos = ua.get_enemy_positions("a")
        assert pos.shape == (0, 2)


# ---------------------------------------------------------------------------
# 88a: Distance matrix
# ---------------------------------------------------------------------------

class TestDistanceMatrix:
    """Vectorized distance computation."""

    def test_distance_matrix_values(self):
        units = {
            "blue": [_make_unit("b1", "blue", (0, 0))],
            "red": [_make_unit("r1", "red", (3, 4))],
        }
        ua = UnitArrays.from_units(units)
        dm = ua.distance_matrix("blue", "red")
        assert dm.shape == (1, 1)
        assert dm[0, 0] == pytest.approx(5.0)

    def test_distance_matrix_matches_cdist(self):
        rng = np.random.default_rng(42)
        blue_pos = rng.uniform(0, 10000, (10, 2))
        red_pos = rng.uniform(0, 10000, (8, 2))
        units = {
            "blue": [_make_unit(f"b{i}", "blue", (blue_pos[i, 0], blue_pos[i, 1]))
                     for i in range(10)],
            "red": [_make_unit(f"r{i}", "red", (red_pos[i, 0], red_pos[i, 1]))
                    for i in range(8)],
        }
        ua = UnitArrays.from_units(units)
        dm = ua.distance_matrix("blue", "red")
        expected = cdist(blue_pos, red_pos, metric="euclidean")
        np.testing.assert_allclose(dm, expected, atol=1e-10)

    def test_distance_matrix_empty_side(self):
        units = {"a": [_make_unit("u1", "a")], "b": []}
        ua = UnitArrays.from_units(units)
        dm = ua.distance_matrix("a", "b")
        assert dm.shape == (1, 0)

    def test_distance_matrix_performance(self):
        """500 units per side: vectorized should be much faster than loop."""
        rng = np.random.default_rng(99)
        n = 500
        units = {
            "blue": [_make_unit(f"b{i}", "blue",
                                (rng.uniform(0, 50000), rng.uniform(0, 50000)))
                     for i in range(n)],
            "red": [_make_unit(f"r{i}", "red",
                               (rng.uniform(0, 50000), rng.uniform(0, 50000)))
                    for i in range(n)],
        }
        ua = UnitArrays.from_units(units)

        # Vectorized (cdist)
        t0 = time.perf_counter()
        dm = ua.distance_matrix("blue", "red")
        t_vec = time.perf_counter() - t0

        # Scalar loop
        blue_units = units["blue"]
        red_units = units["red"]
        t0 = time.perf_counter()
        for bu in blue_units:
            for ru in red_units:
                dx = bu.position.easting - ru.position.easting
                dy = bu.position.northing - ru.position.northing
                _ = (dx * dx + dy * dy) ** 0.5
        t_loop = time.perf_counter() - t0

        assert dm.shape == (n, n)
        assert t_vec < t_loop, f"Vectorized {t_vec:.4f}s not faster than loop {t_loop:.4f}s"


# ---------------------------------------------------------------------------
# 88a: Position sync-back
# ---------------------------------------------------------------------------

class TestSyncPositions:
    """sync_positions_to_units round-trip."""

    def test_round_trip(self):
        units = {"a": [_make_unit("u1", "a", (100, 200))]}
        ua = UnitArrays.from_units(units)
        # Modify positions in the array
        ua.positions[0, 0] = 999.0
        ua.positions[0, 1] = 888.0
        ua.sync_positions_to_units(units)
        assert units["a"][0].position.easting == pytest.approx(999.0)
        assert units["a"][0].position.northing == pytest.approx(888.0)

    def test_altitude_preserved(self):
        u = _make_unit("u1", "a", (100, 200))
        u.position = Position(100, 200, 500.0)
        units = {"a": [u]}
        ua = UnitArrays.from_units(units)
        ua.positions[0] = [300, 400]
        ua.sync_positions_to_units(units)
        assert units["a"][0].position.altitude == pytest.approx(500.0)


# ---------------------------------------------------------------------------
# 88a: Three-side edge case
# ---------------------------------------------------------------------------

class TestThreeSides:
    """Multi-faction scenarios."""

    def test_three_sides(self):
        units = {
            "blue": [_make_unit("b1", "blue", (0, 0))],
            "red": [_make_unit("r1", "red", (100, 100))],
            "green": [_make_unit("g1", "green", (200, 200))],
        }
        ua = UnitArrays.from_units(units)
        assert ua.n == 3
        assert len(ua.side_names) == 3
        # Enemy of blue = red + green
        enemy_pos = ua.get_enemy_positions("blue")
        assert enemy_pos.shape == (2, 2)


# ---------------------------------------------------------------------------
# 88a: Structural — enable_soa=False unchanged path
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    """enable_soa flag gates SoA usage."""

    def test_calibration_default_false(self):
        from stochastic_warfare.simulation.calibration import CalibrationSchema
        cal = CalibrationSchema()
        assert cal.enable_soa is False

    def test_build_enemy_data_in_battle_source(self):
        """When enable_soa=False, _build_enemy_data is still called."""
        import inspect
        from stochastic_warfare.simulation.battle import BattleManager
        src = inspect.getsource(BattleManager.execute_tick)
        assert "_build_enemy_data" in src
        assert 'cal_flat.get("enable_soa"' in src
