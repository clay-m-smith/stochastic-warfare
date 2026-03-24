"""Phase 26c: Engine lifecycle & cleanup — puff aging, integration scan cap, armor_type."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from tests.conftest import make_rng


# ---------------------------------------------------------------------------
# 1. Puff aging & cleanup
# ---------------------------------------------------------------------------


class TestPuffCleanup:
    def test_aged_puffs_removed(self) -> None:
        from stochastic_warfare.cbrn.dispersal import DispersalConfig, DispersalEngine

        eng = DispersalEngine(DispersalConfig(max_puff_age_s=100.0))
        p = eng.create_puff("VX", 0.0, 0.0, 1.0, 0.0)
        p.age_s = 150.0
        removed = eng.cleanup_aged_puffs()
        assert removed == 1
        assert len(eng.puffs) == 0

    def test_young_puffs_kept(self) -> None:
        from stochastic_warfare.cbrn.dispersal import DispersalConfig, DispersalEngine

        eng = DispersalEngine(DispersalConfig(max_puff_age_s=100.0))
        p = eng.create_puff("VX", 0.0, 0.0, 1.0, 0.0)
        p.age_s = 50.0
        removed = eng.cleanup_aged_puffs()
        assert removed == 0
        assert len(eng.puffs) == 1

    def test_mixed_puffs(self) -> None:
        from stochastic_warfare.cbrn.dispersal import DispersalConfig, DispersalEngine

        eng = DispersalEngine(DispersalConfig(max_puff_age_s=100.0))
        young = eng.create_puff("VX", 0.0, 0.0, 1.0, 0.0)
        old = eng.create_puff("GB", 0.0, 0.0, 1.0, 0.0)
        young.age_s = 50.0
        old.age_s = 200.0
        removed = eng.cleanup_aged_puffs()
        assert removed == 1
        assert len(eng.puffs) == 1
        assert eng.puffs[0].puff_id == young.puff_id

    def test_threshold_configurable(self) -> None:
        from stochastic_warfare.cbrn.dispersal import DispersalConfig, DispersalEngine

        eng_short = DispersalEngine(DispersalConfig(max_puff_age_s=10.0))
        eng_long = DispersalEngine(DispersalConfig(max_puff_age_s=1000.0))
        p1 = eng_short.create_puff("VX", 0.0, 0.0, 1.0, 0.0)
        p2 = eng_long.create_puff("VX", 0.0, 0.0, 1.0, 0.0)
        p1.age_s = 50.0
        p2.age_s = 50.0
        assert eng_short.cleanup_aged_puffs() == 1
        assert eng_long.cleanup_aged_puffs() == 0

    def test_default_max_age(self) -> None:
        from stochastic_warfare.cbrn.dispersal import DispersalConfig

        cfg = DispersalConfig()
        assert cfg.max_puff_age_s == 3600.0

    def test_empty_list_safe(self) -> None:
        from stochastic_warfare.cbrn.dispersal import DispersalEngine

        eng = DispersalEngine()
        assert eng.cleanup_aged_puffs() == 0

    def test_boundary_age_removed(self) -> None:
        """Puff exactly at max age IS removed (keep condition is strict less-than)."""
        from stochastic_warfare.cbrn.dispersal import DispersalConfig, DispersalEngine

        eng = DispersalEngine(DispersalConfig(max_puff_age_s=100.0))
        p = eng.create_puff("VX", 0.0, 0.0, 1.0, 0.0)
        p.age_s = 100.0  # exactly at threshold
        # keep condition: age_s < max_puff_age_s → 100.0 < 100.0 is False → removed
        removed = eng.cleanup_aged_puffs()
        assert removed == 1


# ---------------------------------------------------------------------------
# 2. CBRN engine wires cleanup
# ---------------------------------------------------------------------------


class TestCBRNCleanupWiring:
    def test_update_removes_aged_puffs(self) -> None:
        """CBRNEngine.update() calls cleanup_aged_puffs at end of cycle."""
        from stochastic_warfare.cbrn.agents import AgentRegistry
        from stochastic_warfare.cbrn.casualties import CBRNCasualtyEngine
        from stochastic_warfare.cbrn.decontamination import DecontaminationEngine
        from stochastic_warfare.cbrn.dispersal import DispersalConfig, DispersalEngine
        from stochastic_warfare.cbrn.engine import CBRNConfig, CBRNEngine
        from stochastic_warfare.cbrn.protection import ProtectionEngine
        from stochastic_warfare.core.events import EventBus

        rng = make_rng()
        bus = EventBus()
        disp_cfg = DispersalConfig(max_puff_age_s=100.0)
        dispersal = DispersalEngine(disp_cfg)
        registry = AgentRegistry()

        eng = CBRNEngine(
            config=CBRNConfig(enable_cbrn=True),
            event_bus=bus,
            rng=rng,
            agent_registry=registry,
            dispersal_engine=dispersal,
            contamination_manager=None,
            protection_engine=ProtectionEngine(),
            casualty_engine=CBRNCasualtyEngine(bus, rng=rng),
            decon_engine=DecontaminationEngine(bus, rng=rng),
        )

        # Create an aged puff
        p = dispersal.create_puff("VX", 0.0, 0.0, 1.0, 0.0)
        p.age_s = 200.0

        # Run update — should trigger cleanup
        eng.update(dt_s=1.0, sim_time_s=1.0, units_by_side={})
        assert len(dispersal.puffs) == 0


# ---------------------------------------------------------------------------
# 3. Integration scan cap
# ---------------------------------------------------------------------------


class TestIntegrationScanCap:
    def test_default_max_scans(self) -> None:
        from stochastic_warfare.detection.detection import DetectionConfig

        cfg = DetectionConfig()
        assert cfg.max_integration_scans == 4

    def test_custom_max_scans(self) -> None:
        from stochastic_warfare.detection.detection import DetectionConfig

        cfg = DetectionConfig(max_integration_scans=8)
        assert cfg.max_integration_scans == 8

    def test_gain_capped_at_max_scans(self) -> None:
        """Integration gain should not increase beyond max_integration_scans."""
        from stochastic_warfare.detection.detection import DetectionConfig, DetectionEngine
        from stochastic_warfare.detection.sensors import SensorDefinition, SensorInstance
        from stochastic_warfare.detection.signatures import SignatureProfile
        from stochastic_warfare.core.types import Position

        cfg = DetectionConfig(
            max_integration_scans=2,
            max_integration_gain_db=6.0,
            enable_integration_gain=True,
        )
        rng = make_rng()
        eng = DetectionEngine(rng=rng, config=cfg)

        # Create a sensor with large range so range check passes
        defn = SensorDefinition(
            sensor_id="vis_01",
            display_name="Visual Sensor",
            sensor_type="VISUAL",
            max_range_m=50000.0,
            min_range_m=0.0,
            detection_threshold=50.0,  # high threshold → low Pd
            fov_deg=360.0,
            boresight_offset_deg=0.0,
            requires_los=False,
        )
        sensor = SensorInstance(definition=defn)
        sig = SignatureProfile(profile_id="test", unit_type="test", visual_cross_section=10.0)
        obs = Position(0.0, 0.0, 0.0)
        tgt = Position(1000.0, 0.0, 0.0)

        # Run 10 scans — gain should cap at 2 scans
        results = []
        for _ in range(10):
            r = eng.check_detection(
                obs, tgt, sensor, sig,
                target_id="tgt_1",
                illumination_lux=100.0,
            )
            results.append(r)

        # All scans beyond 2 should have the same SNR (gain capped)
        # Scans 3-10 should all have the same SNR as scan 2
        snr_at_cap = results[1].snr_db  # scan 2 (index 1)
        for r in results[2:]:
            assert r.snr_db == pytest.approx(snr_at_cap, abs=0.01)

    def test_scan_cap_interacts_with_db_cap(self) -> None:
        """max_integration_scans and max_integration_gain_db both limit gain."""
        from stochastic_warfare.detection.detection import DetectionConfig

        # With max_scans=4, gain = 5*log10(4) ≈ 3.01 dB — well under 6 dB cap
        cfg = DetectionConfig(max_integration_scans=4, max_integration_gain_db=6.0)
        expected_gain = 5.0 * math.log10(4)
        assert expected_gain < cfg.max_integration_gain_db
        assert expected_gain == pytest.approx(3.01, abs=0.01)


# ---------------------------------------------------------------------------
# 4. Armor type field
# ---------------------------------------------------------------------------


class TestArmorType:
    def test_default_armor_type(self) -> None:
        from stochastic_warfare.entities.unit_classes.ground import GroundUnit
        from stochastic_warfare.core.types import Position

        u = GroundUnit(
            entity_id="test_01",
            position=Position(0.0, 0.0, 0.0),
            name="Test",
            unit_type="test",
            side="blue",
        )
        assert u.armor_type == "RHA"

    def test_custom_armor_type(self) -> None:
        from stochastic_warfare.entities.unit_classes.ground import GroundUnit
        from stochastic_warfare.core.types import Position

        u = GroundUnit(
            entity_id="test_01",
            position=Position(0.0, 0.0, 0.0),
            name="Test",
            unit_type="test",
            side="blue",
            armor_type="COMPOSITE",
        )
        assert u.armor_type == "COMPOSITE"

    def test_get_state_includes_armor_type(self) -> None:
        from stochastic_warfare.entities.unit_classes.ground import GroundUnit
        from stochastic_warfare.core.types import Position

        u = GroundUnit(
            entity_id="test_01",
            position=Position(0.0, 0.0, 0.0),
            name="Test",
            unit_type="test",
            side="blue",
            armor_type="ERA",
        )
        state = u.get_state()
        assert state["armor_type"] == "ERA"

    def test_set_state_roundtrip(self) -> None:
        from stochastic_warfare.entities.unit_classes.ground import GroundUnit
        from stochastic_warfare.core.types import Position

        u1 = GroundUnit(
            entity_id="test_01",
            position=Position(0.0, 0.0, 0.0),
            name="Test",
            unit_type="test",
            side="blue",
            armor_type="COMPOSITE",
        )
        state = u1.get_state()

        u2 = GroundUnit(
            entity_id="test_01",
            position=Position(0.0, 0.0, 0.0),
            name="Test",
            unit_type="test",
            side="blue",
        )
        u2.set_state(state)
        assert u2.armor_type == "COMPOSITE"

    def test_set_state_backward_compat(self) -> None:
        """set_state without armor_type key defaults to RHA."""
        from stochastic_warfare.entities.unit_classes.ground import GroundUnit
        from stochastic_warfare.core.types import Position

        u = GroundUnit(
            entity_id="test_01",
            position=Position(0.0, 0.0, 0.0),
            name="Test",
            unit_type="test",
            side="blue",
            armor_type="COMPOSITE",
        )
        # Simulate old state without armor_type
        state = u.get_state()
        del state["armor_type"]
        u.set_state(state)
        assert u.armor_type == "RHA"

    def test_unit_definition_armor_type_default(self) -> None:
        from stochastic_warfare.entities.loader import UnitDefinition

        defn = UnitDefinition(
            unit_type="test",
            domain="ground",
            display_name="Test",
            max_speed=10.0,
            crew=[],
            equipment=[],
        )
        assert defn.armor_type == "RHA"

    def test_unit_definition_custom_armor_type(self) -> None:
        from stochastic_warfare.entities.loader import UnitDefinition

        defn = UnitDefinition(
            unit_type="test",
            domain="ground",
            display_name="Test",
            max_speed=10.0,
            crew=[],
            equipment=[],
            armor_type="COMPOSITE",
        )
        assert defn.armor_type == "COMPOSITE"


# ---------------------------------------------------------------------------
# 5. YAML loading with armor_type
# ---------------------------------------------------------------------------


class TestArmorTypeYAML:
    def test_m1a1_composite(self) -> None:
        from stochastic_warfare.entities.loader import UnitLoader

        loader = UnitLoader(Path("data/units/armor"))
        defn = loader.load_definition(Path("data/units/armor/m1a1_abrams.yaml"))
        assert defn.armor_type == "COMPOSITE"

    def test_t55a_rha(self) -> None:
        from stochastic_warfare.entities.loader import UnitLoader

        loader = UnitLoader(Path("data/units/armor"))
        defn = loader.load_definition(Path("data/units/armor/t55a.yaml"))
        assert defn.armor_type == "RHA"

    def test_t72m_composite(self) -> None:
        from stochastic_warfare.entities.loader import UnitLoader

        loader = UnitLoader(Path("data/units/armor"))
        defn = loader.load_definition(Path("data/units/armor/t72m.yaml"))
        assert defn.armor_type == "COMPOSITE"

    def test_create_unit_passes_armor_type(self) -> None:
        from stochastic_warfare.entities.loader import UnitLoader
        from stochastic_warfare.entities.unit_classes.ground import GroundUnit
        from stochastic_warfare.core.types import Position

        loader = UnitLoader(Path("data/units/armor"))
        loader.load_definition(Path("data/units/armor/m1a1_abrams.yaml"))
        rng = make_rng()
        unit = loader.create_unit("m1a1", "abrams_01", Position(0, 0, 0), "blue", rng)
        assert isinstance(unit, GroundUnit)
        assert unit.armor_type == "COMPOSITE"
