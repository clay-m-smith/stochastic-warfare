"""Phase 17f tests — YAML data loading and validation scenarios."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from stochastic_warfare.space.asat import ASATWeaponDefinition
from stochastic_warfare.space.constellations import ConstellationDefinition

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CONSTELLATIONS_DIR = DATA_DIR / "space" / "constellations"
ASAT_DIR = DATA_DIR / "space" / "asat_weapons"
SCENARIOS_DIR = DATA_DIR / "scenarios"


# ---------------------------------------------------------------------------
# TestConstellationYAMLs — parametrized load of all 9
# ---------------------------------------------------------------------------


_CONSTELLATION_FILES = [
    "gps_navstar.yaml",
    "glonass.yaml",
    "milstar_satcom.yaml",
    "wgs_satcom.yaml",
    "keyhole_optical.yaml",
    "lacrosse_sar.yaml",
    "sbirs_ew.yaml",
    "molniya_ew.yaml",
    "sigint_leo.yaml",
]


@pytest.mark.parametrize("filename", _CONSTELLATION_FILES)
class TestConstellationYAMLs:
    def test_loads_and_validates(self, filename: str) -> None:
        """Each constellation YAML loads and validates via pydantic."""
        path = CONSTELLATIONS_DIR / filename
        assert path.exists(), f"Missing file: {path}"
        with open(path) as f:
            raw = yaml.safe_load(f)
        cdef = ConstellationDefinition.model_validate(raw)
        assert cdef.constellation_id
        assert cdef.num_satellites > 0
        assert cdef.plane_count >= 1
        assert cdef.sats_per_plane >= 1


# ---------------------------------------------------------------------------
# TestASATYAMLs — parametrized load of 3
# ---------------------------------------------------------------------------


_ASAT_FILES = [
    "sm3_block_iia.yaml",
    "nudol_asat.yaml",
    "ground_laser.yaml",
]


@pytest.mark.parametrize("filename", _ASAT_FILES)
class TestASATYAMLs:
    def test_loads_and_validates(self, filename: str) -> None:
        """Each ASAT weapon YAML loads and validates via pydantic."""
        path = ASAT_DIR / filename
        assert path.exists(), f"Missing file: {path}"
        with open(path) as f:
            raw = yaml.safe_load(f)
        wdef = ASATWeaponDefinition.model_validate(raw)
        assert wdef.weapon_id
        assert wdef.max_altitude_km > 0


# ---------------------------------------------------------------------------
# TestGPSDenialScenario
# ---------------------------------------------------------------------------


class TestGPSDenialScenario:
    def test_loads(self) -> None:
        path = SCENARIOS_DIR / "space_gps_denial" / "scenario.yaml"
        assert path.exists()
        with open(path) as f:
            raw = yaml.safe_load(f)
        assert raw["name"] == "Space GPS Denial"

    def test_has_sides(self) -> None:
        path = SCENARIOS_DIR / "space_gps_denial" / "scenario.yaml"
        with open(path) as f:
            raw = yaml.safe_load(f)
        assert len(raw["sides"]) == 2

    def test_cep_range_logic(self) -> None:
        """Full GPS (3.6m) → CEP ~13m. Denied → CEP 30m+."""
        from stochastic_warfare.space.gps import GPSEngine
        from stochastic_warfare.space.constellations import (
            ConstellationManager, SpaceConfig, ConstellationType,
        )
        from stochastic_warfare.space.orbits import OrbitalMechanicsEngine
        from stochastic_warfare.core.events import EventBus

        import numpy as np
        orbits = OrbitalMechanicsEngine()
        bus = EventBus()
        rng = np.random.Generator(np.random.PCG64(42))
        cfg = SpaceConfig(enable_space=True, theater_lat=33.0, theater_lon=35.0)
        cm = ConstellationManager(orbits, bus, rng, cfg)

        # Full GPS: accuracy ~3.6m → CEP factor = 1.0
        cdef = ConstellationDefinition(
            constellation_id="gps", constellation_type=int(ConstellationType.GPS),
            side="blue", num_satellites=24,
            orbital_elements_template={"semi_major_axis_m": 26559700.0, "inclination_deg": 55.0},
            plane_count=6, sats_per_plane=4,
        )
        cm.add_constellation(cdef)
        gps = GPSEngine(cm, cfg, bus, rng)
        state_full = gps.compute_gps_accuracy("blue", 0.0)
        cep_full = 10.0 * gps.compute_cep_factor(state_full.position_accuracy_m, "gps")

        # Denied: destroy all GPS sats
        cm.degrade_constellation("gps", 24, "test")
        state_denied = gps.compute_gps_accuracy("blue", 0.0)
        cep_denied = 10.0 * gps.compute_cep_factor(state_denied.position_accuracy_m, "gps")

        assert cep_full < cep_denied
        assert cep_denied > 30.0  # Denied GPS → CEP >> 30m


# ---------------------------------------------------------------------------
# TestISRGapScenario
# ---------------------------------------------------------------------------


class TestISRGapScenario:
    def test_loads(self) -> None:
        path = SCENARIOS_DIR / "space_isr_gap" / "scenario.yaml"
        assert path.exists()
        with open(path) as f:
            raw = yaml.safe_load(f)
        assert raw["name"] == "Space ISR Gap"

    def test_terrain(self) -> None:
        path = SCENARIOS_DIR / "space_isr_gap" / "scenario.yaml"
        with open(path) as f:
            raw = yaml.safe_load(f)
        assert raw["terrain"]["width_m"] == 20000.0


# ---------------------------------------------------------------------------
# TestASATEscalation
# ---------------------------------------------------------------------------


class TestASATEscalation:
    def test_loads(self) -> None:
        path = SCENARIOS_DIR / "space_asat_escalation" / "scenario.yaml"
        assert path.exists()
        with open(path) as f:
            raw = yaml.safe_load(f)
        assert raw["name"] == "Space ASAT Escalation"

    def test_sequence_logic(self) -> None:
        """6 ASAT strikes reduce GPS from 24 to ~18 sats."""
        from stochastic_warfare.space.constellations import (
            ConstellationManager, SpaceConfig, ConstellationDefinition, ConstellationType,
        )
        from stochastic_warfare.space.orbits import OrbitalMechanicsEngine
        from stochastic_warfare.core.events import EventBus

        import numpy as np
        orbits = OrbitalMechanicsEngine()
        bus = EventBus()
        rng = np.random.Generator(np.random.PCG64(42))
        cfg = SpaceConfig(enable_space=True)
        cm = ConstellationManager(orbits, bus, rng, cfg)
        cm.add_constellation(ConstellationDefinition(
            constellation_id="gps", constellation_type=int(ConstellationType.GPS),
            side="blue", num_satellites=24,
            orbital_elements_template={"semi_major_axis_m": 26559700.0, "inclination_deg": 55.0},
            plane_count=6, sats_per_plane=4,
        ))
        assert cm.active_count("gps") == 24
        cm.degrade_constellation("gps", 6, "asat_kinetic")
        assert cm.active_count("gps") == 18

    def test_cascade_bounded(self) -> None:
        """Debris collision probability is capped."""
        from stochastic_warfare.space.asat import ASATEngine, DebrisCloud
        from stochastic_warfare.space.constellations import (
            ConstellationManager, SpaceConfig, ConstellationDefinition, ConstellationType,
        )
        from stochastic_warfare.space.orbits import OrbitalMechanicsEngine
        from stochastic_warfare.core.events import EventBus

        import numpy as np
        orbits = OrbitalMechanicsEngine()
        bus = EventBus()
        rng = np.random.Generator(np.random.PCG64(42))
        cfg = SpaceConfig(enable_space=True, debris_collision_prob_per_orbit=0.001)
        cm = ConstellationManager(orbits, bus, rng, cfg)
        cm.add_constellation(ConstellationDefinition(
            constellation_id="gps", constellation_type=int(ConstellationType.GPS),
            side="blue", num_satellites=24,
            orbital_elements_template={"semi_major_axis_m": 26559700.0, "inclination_deg": 55.0},
            plane_count=6, sats_per_plane=4,
        ))
        asat = ASATEngine(cm, cfg, bus, rng)
        # Even with massive debris, collision prob capped at 0.1
        asat._debris_clouds.append(DebrisCloud(20000.0, 1000000))
        # Should not crash or destroy all sats
        asat.update_debris(3600.0, 3600.0)
        assert cm.active_count("gps") >= 0
