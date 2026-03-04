"""Phase 18d tests -- Nuclear Effects Engine.

Tests nuclear detonation physics: blast overpressure (Hopkinson-Cranz),
thermal fluence (inverse-square), initial radiation (exp attenuation),
EMP, fallout plume generation, terrain modification, and full detonation
orchestration.
"""

from __future__ import annotations

import math
import types
from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.cbrn.events import (
    EMPEvent,
    FalloutPlumeEvent,
    NuclearDetonationEvent,
)
from stochastic_warfare.cbrn.nuclear import (
    NuclearConfig,
    NuclearEffectsEngine,
    _BLAST_EXPONENT,
    _BLAST_K,
    _BLAST_LETHAL_PSI,
    _BLAST_LIGHT_DAMAGE_PSI,
    _BLAST_INJURY_PSI,
    _CAL_CM2_TO_J_M2,
    _CRATER_RADIUS_FACTOR,
    _EMP_RADIUS_FACTOR,
    _FALLOUT_MASS_PER_KT,
    _KT_TO_JOULES,
    _RAD_D0,
    _RAD_LAMBDA,
    _THERMAL_ETA,
    _THERMAL_LETHAL_CAL,
    _THERMAL_SEVERE_BURN_CAL,
    _THERMAL_SECOND_DEGREE_CAL,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import ModuleId, Position

TS = datetime(2024, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_unit(
    entity_id: str = "u1",
    easting: float = 500.0,
    northing: float = 500.0,
    personnel_count: int = 100,
    hardened_electronics: bool = False,
) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        entity_id=entity_id,
        position=Position(easting, northing, 0.0),
        personnel_count=personnel_count,
        hardened_electronics=hardened_electronics,
    )


def _make_weather(
    wind_speed_m_s: float = 5.0,
    wind_direction_rad: float = 0.0,
) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        wind_speed_m_s=wind_speed_m_s,
        wind_direction_rad=wind_direction_rad,
    )


def _make_dispersal_engine() -> types.SimpleNamespace:
    """Minimal mock for DispersalEngine with create_puff."""
    puffs_created: list[dict] = []
    counter = [0]

    def create_puff(agent_id, position_e, position_n, mass_kg, sim_time_s):
        puff_id = f"puff_{counter[0]}"
        counter[0] += 1
        puff = types.SimpleNamespace(
            puff_id=puff_id,
            agent_id=agent_id,
            center_e=position_e,
            center_n=position_n,
            mass_kg=mass_kg,
        )
        puffs_created.append(
            {
                "puff_id": puff_id,
                "agent_id": agent_id,
                "position_e": position_e,
                "position_n": position_n,
                "mass_kg": mass_kg,
            }
        )
        return puff

    engine = types.SimpleNamespace(
        create_puff=create_puff,
        puffs_created=puffs_created,
    )
    return engine


def _make_heightmap(
    rows: int = 20,
    cols: int = 20,
    cell_size: float = 100.0,
    elevation: float = 100.0,
) -> types.SimpleNamespace:
    """Mock heightmap with mutable _data array."""
    data = np.full((rows, cols), elevation, dtype=np.float64)
    config = types.SimpleNamespace(
        origin_easting=0.0,
        origin_northing=0.0,
    )
    return types.SimpleNamespace(
        rows=rows,
        cols=cols,
        cell_size=cell_size,
        _data=data,
        _config=config,
        elevation_at=lambda e, n: elevation,
    )


def _make_classification(
    rows: int = 20,
    cols: int = 20,
    cell_size: float = 100.0,
) -> types.SimpleNamespace:
    """Mock classification grid with set_classification."""
    land_cover = np.full((rows, cols), 1, dtype=np.int32)  # 1 = GRASSLAND
    changes: list[tuple[int, int, int]] = []
    config = types.SimpleNamespace(
        origin_easting=0.0,
        origin_northing=0.0,
    )

    def set_classification(row, col, value):
        land_cover[row, col] = value
        changes.append((row, col, value))

    return types.SimpleNamespace(
        cell_size=cell_size,
        shape=(rows, cols),
        _config=config,
        _land_cover=land_cover,
        set_classification=set_classification,
        changes=changes,
    )


def _make_engine(
    event_bus: EventBus | None = None,
    rng: np.random.Generator | None = None,
    dispersal_engine: types.SimpleNamespace | None = None,
    config: NuclearConfig | None = None,
) -> NuclearEffectsEngine:
    if event_bus is None:
        event_bus = EventBus()
    if rng is None:
        rng = np.random.default_rng(42)
    if dispersal_engine is None:
        dispersal_engine = _make_dispersal_engine()
    return NuclearEffectsEngine(event_bus, rng, dispersal_engine, config)


# ---------------------------------------------------------------------------
# TestBlastOverpressure
# ---------------------------------------------------------------------------


class TestBlastOverpressure:
    """Blast overpressure via Hopkinson-Cranz scaling."""

    def test_known_range_values(self):
        """Overpressure at specific ranges matches formula."""
        # For 20kt at 1000m: Z = 1000/20^(1/3), DP = K * Z^(-a)
        w = 20.0
        r = 1000.0
        z = r / (w ** (1.0 / 3.0))
        expected = _BLAST_K * z ** (-_BLAST_EXPONENT)
        result = NuclearEffectsEngine.blast_overpressure_psi(r, w)
        assert abs(result - expected) < 1e-6

    def test_scaling_with_yield(self):
        """Higher yield produces higher overpressure at the same range."""
        r = 2000.0
        dp_low = NuclearEffectsEngine.blast_overpressure_psi(r, 1.0)
        dp_high = NuclearEffectsEngine.blast_overpressure_psi(r, 100.0)
        assert dp_high > dp_low

    def test_near_mid_far_zones(self):
        """Overpressure decreases with distance: near > mid > far."""
        w = 20.0
        dp_near = NuclearEffectsEngine.blast_overpressure_psi(100.0, w)
        dp_mid = NuclearEffectsEngine.blast_overpressure_psi(1000.0, w)
        dp_far = NuclearEffectsEngine.blast_overpressure_psi(5000.0, w)
        assert dp_near > dp_mid > dp_far > 0.0

    def test_inverse_square_decay(self):
        """With exponent 2.0, overpressure follows approximate inverse-square."""
        w = 10.0
        r1 = 1000.0
        r2 = 2000.0
        dp1 = NuclearEffectsEngine.blast_overpressure_psi(r1, w)
        dp2 = NuclearEffectsEngine.blast_overpressure_psi(r2, w)
        # For pure inverse-square (exponent=2), ratio should be 4.0
        ratio = dp1 / dp2
        assert abs(ratio - 4.0) < 0.01


# ---------------------------------------------------------------------------
# TestThermalFluence
# ---------------------------------------------------------------------------


class TestThermalFluence:
    """Thermal fluence via inverse-square law."""

    def test_inverse_square(self):
        """Thermal fluence follows strict inverse-square with distance."""
        w = 20.0
        q1 = NuclearEffectsEngine.thermal_fluence_cal_cm2(1000.0, w)
        q2 = NuclearEffectsEngine.thermal_fluence_cal_cm2(2000.0, w)
        # Inverse-square: ratio should be exactly 4.0
        ratio = q1 / q2
        assert abs(ratio - 4.0) < 1e-6

    def test_known_value(self):
        """Thermal fluence at a specific range matches formula."""
        w = 20.0
        r = 1000.0
        energy_j = _THERMAL_ETA * w * _KT_TO_JOULES
        expected = energy_j / (4.0 * math.pi * r * r) / _CAL_CM2_TO_J_M2
        result = NuclearEffectsEngine.thermal_fluence_cal_cm2(r, w)
        assert abs(result - expected) < 1e-6

    def test_yield_scaling(self):
        """Thermal fluence scales linearly with yield at fixed range."""
        r = 1000.0
        q1 = NuclearEffectsEngine.thermal_fluence_cal_cm2(r, 10.0)
        q2 = NuclearEffectsEngine.thermal_fluence_cal_cm2(r, 20.0)
        ratio = q2 / q1
        assert abs(ratio - 2.0) < 1e-6


# ---------------------------------------------------------------------------
# TestRadiation
# ---------------------------------------------------------------------------


class TestRadiation:
    """Initial (prompt) radiation dose model."""

    def test_dose_at_range(self):
        """Dose at a specific range matches the formula."""
        w = 1.0
        r = 100.0
        expected = _RAD_D0 * w * math.exp(-r / _RAD_LAMBDA) / (r * r)
        result = NuclearEffectsEngine.initial_radiation_rem(r, w)
        assert abs(result - expected) < 1e-6

    def test_exponential_attenuation(self):
        """Dose drops faster than inverse-square due to exponential term."""
        w = 20.0
        d1 = NuclearEffectsEngine.initial_radiation_rem(100.0, w)
        d2 = NuclearEffectsEngine.initial_radiation_rem(200.0, w)
        # Pure inverse-square would give ratio = 4.0
        # With exp attenuation, ratio > 4.0
        ratio = d1 / d2
        assert ratio > 4.0

    def test_yield_scaling(self):
        """Dose scales linearly with yield at fixed range."""
        r = 200.0
        d1 = NuclearEffectsEngine.initial_radiation_rem(r, 5.0)
        d2 = NuclearEffectsEngine.initial_radiation_rem(r, 10.0)
        ratio = d2 / d1
        assert abs(ratio - 2.0) < 1e-6


# ---------------------------------------------------------------------------
# TestEMPRadius
# ---------------------------------------------------------------------------


class TestEMPRadius:
    """EMP radius scaling."""

    def test_scaling_with_yield(self):
        """EMP radius scales with cube root of yield."""
        r1 = NuclearEffectsEngine.emp_radius_m(1.0)
        r8 = NuclearEffectsEngine.emp_radius_m(8.0)
        # 8^(1/3) = 2, so radius should double
        assert abs(r8 / r1 - 2.0) < 1e-6

    def test_known_values(self):
        """EMP radius matches formula for specific yields."""
        assert abs(
            NuclearEffectsEngine.emp_radius_m(1.0)
            - _EMP_RADIUS_FACTOR * 1.0
        ) < 1e-6
        # For 27 kt: 27^(1/3) = 3
        assert abs(
            NuclearEffectsEngine.emp_radius_m(27.0)
            - _EMP_RADIUS_FACTOR * 3.0
        ) < 1e-6


# ---------------------------------------------------------------------------
# TestBlastCasualties
# ---------------------------------------------------------------------------


class TestBlastCasualties:
    """Blast casualty computation by overpressure zone."""

    def test_lethal_zone(self):
        """Units in lethal zone (>12 psi) suffer 100% killed."""
        engine = _make_engine()
        # Place unit very close to detonation for lethal overpressure
        unit = _make_unit("u_close", easting=0.0, northing=0.0, personnel_count=50)
        det_pos = Position(10.0, 0.0, 0.0)  # 10m away
        # Verify overpressure is lethal
        dp = NuclearEffectsEngine.blast_overpressure_psi(10.0, 20.0)
        assert dp >= _BLAST_LETHAL_PSI
        results = engine.compute_blast_casualties([unit], det_pos, 20.0)
        killed, injured, light = results["u_close"]
        assert killed == 50
        assert injured == 0
        assert light == 0

    def test_injury_zone(self):
        """Units in injury zone (5-12 psi) suffer mix of killed and injured."""
        engine = _make_engine()
        # Find a range that gives overpressure between 5 and 12 psi for 20kt
        # DP = 1e7 * (R/20^(1/3))^(-2) = 1e7 / (R/2.714)^2
        # For 7 psi: R^2 = 1e7 * 2.714^2 / 7 = 1e7 * 7.366 / 7 = 1.052e7
        # R = 3244 m
        # Let's pick R=3000m: DP = 1e7 / (3000/2.714)^2 = 1e7 / 1105.4^2 = 1e7/1221909 = 8.18 psi
        unit = _make_unit("u_mid", easting=3000.0, northing=0.0, personnel_count=100)
        det_pos = Position(0.0, 0.0, 0.0)
        dp = NuclearEffectsEngine.blast_overpressure_psi(3000.0, 20.0)
        assert _BLAST_INJURY_PSI <= dp < _BLAST_LETHAL_PSI
        results = engine.compute_blast_casualties([unit], det_pos, 20.0)
        killed, injured, light = results["u_mid"]
        assert killed > 0
        assert injured > 0
        assert light == 0
        assert killed + injured == 100

    def test_light_damage_zone(self):
        """Units in light damage zone (2-5 psi) suffer injuries and light damage."""
        engine = _make_engine()
        # For 3 psi: R^2 = 1e7*7.366/3 = 2.455e7, R = 4955
        # Check ~5000m: DP = 1e7/(5000/2.714)^2 = 1e7/3393360 = 2.95 psi
        unit = _make_unit("u_far", easting=5000.0, northing=0.0, personnel_count=100)
        det_pos = Position(0.0, 0.0, 0.0)
        dp = NuclearEffectsEngine.blast_overpressure_psi(5000.0, 20.0)
        assert _BLAST_LIGHT_DAMAGE_PSI <= dp < _BLAST_INJURY_PSI
        results = engine.compute_blast_casualties([unit], det_pos, 20.0)
        killed, injured, light = results["u_far"]
        assert killed == 0
        assert injured >= 0
        assert light > 0

    def test_distance_dependence(self):
        """Closer units suffer more casualties than farther units."""
        engine = _make_engine()
        u_close = _make_unit("u1", easting=100.0, northing=0.0, personnel_count=100)
        u_far = _make_unit("u2", easting=6000.0, northing=0.0, personnel_count=100)
        det_pos = Position(0.0, 0.0, 0.0)
        results = engine.compute_blast_casualties([u_close, u_far], det_pos, 20.0)
        k_close = results["u1"][0]
        k_far = results["u2"][0]
        assert k_close >= k_far


# ---------------------------------------------------------------------------
# TestThermalCasualties
# ---------------------------------------------------------------------------


class TestThermalCasualties:
    """Thermal burn casualty computation."""

    def test_lethal_burn_zone(self):
        """Units with fluence >12 cal/cm^2 suffer lethal burns."""
        engine = _make_engine()
        # Close range: thermal fluence very high
        unit = _make_unit("u1", easting=50.0, northing=0.0, personnel_count=80)
        det_pos = Position(0.0, 0.0, 0.0)
        fluence = NuclearEffectsEngine.thermal_fluence_cal_cm2(50.0, 20.0)
        assert fluence >= _THERMAL_LETHAL_CAL
        results = engine.compute_thermal_casualties([unit], det_pos, 20.0)
        lethal, severe = results["u1"]
        assert lethal == 80
        assert severe == 0

    def test_severe_burn_zone(self):
        """Units with fluence between 6 and 12 cal/cm^2 get partial lethal + severe."""
        engine = _make_engine()
        # Find range for ~9 cal/cm^2 at 20kt
        # Q = eta*W*4.184e12 / (4*pi*R^2) / 41868
        # 9 = 0.35*20*4.184e12 / (4*pi*R^2*41868)
        # R^2 = 0.35*20*4.184e12 / (4*pi*41868*9)
        energy = _THERMAL_ETA * 20.0 * _KT_TO_JOULES
        r_target = math.sqrt(energy / (4.0 * math.pi * 9.0 * _CAL_CM2_TO_J_M2))
        unit = _make_unit("u1", easting=r_target, northing=0.0, personnel_count=100)
        det_pos = Position(0.0, 0.0, 0.0)
        fluence = NuclearEffectsEngine.thermal_fluence_cal_cm2(r_target, 20.0)
        assert _THERMAL_SEVERE_BURN_CAL <= fluence <= _THERMAL_LETHAL_CAL
        results = engine.compute_thermal_casualties([unit], det_pos, 20.0)
        lethal, severe = results["u1"]
        assert lethal + severe == 100
        assert lethal > 0
        assert severe > 0

    def test_second_degree_zone(self):
        """Units with fluence between 3 and 6 cal/cm^2 get only severe burns."""
        engine = _make_engine()
        # Range for ~4 cal/cm^2
        energy = _THERMAL_ETA * 20.0 * _KT_TO_JOULES
        r_target = math.sqrt(energy / (4.0 * math.pi * 4.0 * _CAL_CM2_TO_J_M2))
        unit = _make_unit("u1", easting=r_target, northing=0.0, personnel_count=100)
        det_pos = Position(0.0, 0.0, 0.0)
        fluence = NuclearEffectsEngine.thermal_fluence_cal_cm2(r_target, 20.0)
        assert _THERMAL_SECOND_DEGREE_CAL <= fluence < _THERMAL_SEVERE_BURN_CAL
        results = engine.compute_thermal_casualties([unit], det_pos, 20.0)
        lethal, severe = results["u1"]
        assert lethal == 0
        assert severe > 0


# ---------------------------------------------------------------------------
# TestEMP
# ---------------------------------------------------------------------------


class TestEMP:
    """EMP electronics effects."""

    def test_disables_unshielded(self):
        """Unshielded electronics within EMP radius are disabled with high probability."""
        config = NuclearConfig(emp_electronics_disable_prob=1.0)
        engine = _make_engine(config=config)
        unit = _make_unit("u1", easting=100.0, northing=0.0, hardened_electronics=False)
        det_pos = Position(0.0, 0.0, 0.0)
        affected = engine.apply_emp([unit], det_pos, 20.0, TS)
        assert "u1" in affected

    def test_spares_hardened(self):
        """Hardened electronics survive EMP with configured probability."""
        config = NuclearConfig(hardened_electronics_survive_prob=1.0)
        engine = _make_engine(config=config)
        unit = _make_unit("u1", easting=100.0, northing=0.0, hardened_electronics=True)
        det_pos = Position(0.0, 0.0, 0.0)
        affected = engine.apply_emp([unit], det_pos, 20.0, TS)
        assert "u1" not in affected

    def test_probability_stochastic(self):
        """Over many trials, unshielded disable probability matches config."""
        config = NuclearConfig(emp_electronics_disable_prob=0.6)
        affected_count = 0
        n_trials = 500
        for seed in range(n_trials):
            rng = np.random.default_rng(seed)
            engine = NuclearEffectsEngine(EventBus(), rng, _make_dispersal_engine(), config)
            unit = _make_unit("u1", easting=100.0, northing=0.0)
            det_pos = Position(0.0, 0.0, 0.0)
            if "u1" in engine.apply_emp([unit], det_pos, 20.0, TS):
                affected_count += 1
        rate = affected_count / n_trials
        # Should be approximately 0.6
        assert 0.5 < rate < 0.7


# ---------------------------------------------------------------------------
# TestFallout
# ---------------------------------------------------------------------------


class TestFallout:
    """Fallout plume generation."""

    def test_creates_plume(self):
        """Fallout generation creates a puff via dispersal engine."""
        dispersal = _make_dispersal_engine()
        engine = _make_engine(dispersal_engine=dispersal)
        det_pos = Position(1000.0, 2000.0, 0.0)
        puff_id = engine.generate_fallout_plume(
            det_pos, 20.0, 5.0, 0.0, None, None, TS
        )
        assert puff_id == "puff_0"
        assert len(dispersal.puffs_created) == 1
        assert dispersal.puffs_created[0]["agent_id"] == "nuclear_fallout"

    def test_wind_driven(self):
        """Fallout plume passes wind parameters to dispersal engine (puff created at detonation pos)."""
        dispersal = _make_dispersal_engine()
        engine = _make_engine(dispersal_engine=dispersal)
        det_pos = Position(500.0, 500.0, 0.0)
        engine.generate_fallout_plume(det_pos, 10.0, 8.0, 1.57, None, None, TS)
        puff = dispersal.puffs_created[0]
        assert abs(puff["position_e"] - 500.0) < 1e-6
        assert abs(puff["position_n"] - 500.0) < 1e-6

    def test_yield_dependent_mass(self):
        """Fallout puff mass scales linearly with weapon yield."""
        dispersal = _make_dispersal_engine()
        engine = _make_engine(dispersal_engine=dispersal)
        det_pos = Position(0.0, 0.0, 0.0)
        engine.generate_fallout_plume(det_pos, 10.0, 5.0, 0.0, None, None, TS)
        engine.generate_fallout_plume(det_pos, 20.0, 5.0, 0.0, None, None, TS)
        mass_10kt = dispersal.puffs_created[0]["mass_kg"]
        mass_20kt = dispersal.puffs_created[1]["mass_kg"]
        assert abs(mass_10kt - _FALLOUT_MASS_PER_KT * 10.0) < 1e-6
        assert abs(mass_20kt - _FALLOUT_MASS_PER_KT * 20.0) < 1e-6
        assert abs(mass_20kt / mass_10kt - 2.0) < 1e-6


# ---------------------------------------------------------------------------
# TestTerrainModification
# ---------------------------------------------------------------------------


class TestTerrainModification:
    """Terrain crater creation."""

    def test_crater_radius(self):
        """Crater modifies heightmap cells within expected radius."""
        heightmap = _make_heightmap(rows=20, cols=20, cell_size=50.0, elevation=100.0)
        engine = _make_engine()
        det_pos = Position(500.0, 500.0, 0.0)
        yield_kt = 20.0
        crater_radius = _CRATER_RADIUS_FACTOR * (yield_kt ** (1.0 / 3.0))

        engine.modify_terrain(det_pos, yield_kt, heightmap, None)

        # Center cell (row=10, col=10 for origin 0,0 with cell_size 50m)
        center_row = int(500.0 / 50.0)
        center_col = int(500.0 / 50.0)
        # Center should have maximum depression
        assert heightmap._data[center_row, center_col] < 100.0
        # Far corner should be unaffected
        assert heightmap._data[0, 0] == 100.0

    def test_classification_changes(self):
        """Cells within crater are set to OPEN (0) classification."""
        classification = _make_classification(rows=20, cols=20, cell_size=50.0)
        engine = _make_engine()
        det_pos = Position(500.0, 500.0, 0.0)
        yield_kt = 20.0
        engine.modify_terrain(det_pos, yield_kt, None, classification)

        # At least some cells near center should have been changed to OPEN (0)
        assert len(classification.changes) > 0
        for row, col, val in classification.changes:
            assert val == 0  # OPEN


# ---------------------------------------------------------------------------
# TestDetonate
# ---------------------------------------------------------------------------


class TestDetonate:
    """Full detonation orchestration."""

    def test_full_sequence(self):
        """Detonate orchestrates all effects and publishes events."""
        bus = EventBus()
        events_received: list = []
        bus.subscribe(NuclearDetonationEvent, events_received.append)
        bus.subscribe(EMPEvent, events_received.append)
        bus.subscribe(FalloutPlumeEvent, events_received.append)

        dispersal = _make_dispersal_engine()
        rng = np.random.default_rng(42)
        engine = NuclearEffectsEngine(bus, rng, dispersal)

        u_close = _make_unit("u1", easting=100.0, northing=0.0, personnel_count=50)
        u_far = _make_unit("u2", easting=8000.0, northing=0.0, personnel_count=50)
        units_by_side = {"blue": [u_close], "red": [u_far]}
        weather = _make_weather(wind_speed_m_s=10.0, wind_direction_rad=0.5)
        heightmap = _make_heightmap()
        classification = _make_classification()

        result = engine.detonate(
            weapon_id="nuke_01",
            position=Position(0.0, 0.0, 0.0),
            yield_kt=20.0,
            airburst=False,
            units_by_side=units_by_side,
            weather_conditions=weather,
            contamination_manager=None,
            agent_registry=None,
            heightmap=heightmap,
            classification=classification,
            timestamp=TS,
        )

        # Result structure
        assert result["weapon_id"] == "nuke_01"
        assert result["yield_kt"] == 20.0
        assert result["airburst"] is False

        # Blast casualties computed
        assert "u1" in result["blast_casualties"]
        assert "u2" in result["blast_casualties"]

        # Thermal casualties computed
        assert "u1" in result["thermal_casualties"]

        # EMP affected computed
        assert isinstance(result["emp_affected"], list)

        # Fallout generated (ground burst)
        assert result["fallout_puff_id"] is not None
        assert len(dispersal.puffs_created) == 1

        # Events published: NuclearDetonationEvent + EMPEvent + FalloutPlumeEvent
        event_types = [type(e) for e in events_received]
        assert NuclearDetonationEvent in event_types
        assert EMPEvent in event_types
        assert FalloutPlumeEvent in event_types

    def test_airburst_vs_ground_burst(self):
        """Airburst skips fallout and terrain modification."""
        bus = EventBus()
        events_received: list = []
        bus.subscribe(FalloutPlumeEvent, events_received.append)

        dispersal = _make_dispersal_engine()
        rng = np.random.default_rng(42)
        engine = NuclearEffectsEngine(bus, rng, dispersal)

        unit = _make_unit("u1", easting=500.0, northing=0.0)
        heightmap = _make_heightmap()
        original_center = float(heightmap._data[5, 5])

        result = engine.detonate(
            weapon_id="nuke_02",
            position=Position(0.0, 0.0, 0.0),
            yield_kt=20.0,
            airburst=True,
            units_by_side={"blue": [unit]},
            weather_conditions=_make_weather(),
            contamination_manager=None,
            agent_registry=None,
            heightmap=heightmap,
            classification=None,
            timestamp=TS,
        )

        # No fallout for airburst
        assert result["fallout_puff_id"] is None
        assert len(dispersal.puffs_created) == 0

        # No FalloutPlumeEvent published
        fallout_events = [e for e in events_received if isinstance(e, FalloutPlumeEvent)]
        assert len(fallout_events) == 0

        # Terrain not modified
        assert heightmap._data[5, 5] == original_center


# ---------------------------------------------------------------------------
# TestState
# ---------------------------------------------------------------------------


class TestState:
    """Checkpoint/restore via get_state/set_state."""

    def test_roundtrip(self):
        """State can be saved and restored."""
        engine = _make_engine()
        # Perform a detonation to modify internal state
        unit = _make_unit("u1", easting=500.0, northing=0.0)
        engine.detonate(
            weapon_id="w1",
            position=Position(0.0, 0.0, 0.0),
            yield_kt=10.0,
            airburst=True,
            units_by_side={"blue": [unit]},
            weather_conditions=_make_weather(),
            contamination_manager=None,
            agent_registry=None,
            heightmap=None,
            classification=None,
            timestamp=TS,
        )

        state = engine.get_state()
        assert state["detonation_count"] == 1

        # Create fresh engine and restore
        engine2 = _make_engine()
        assert engine2.get_state()["detonation_count"] == 0
        engine2.set_state(state)
        assert engine2.get_state()["detonation_count"] == 1

        # Config also round-trips
        assert engine2.get_state()["config"]["emp_electronics_disable_prob"] == 0.95
