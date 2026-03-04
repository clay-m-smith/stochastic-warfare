"""Phase 18a tests — CBRN agents, events, dispersal model."""

from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.cbrn.agents import AgentCategory, AgentDefinition, AgentRegistry
from stochastic_warfare.cbrn.dispersal import (
    DispersalConfig,
    DispersalEngine,
    PuffState,
    StabilityClass,
)
from stochastic_warfare.cbrn.events import (
    CBRNCasualtyEvent,
    CBRNReleaseEvent,
    ContaminationClearedEvent,
    ContaminationDetectedEvent,
    DecontaminationCompletedEvent,
    DecontaminationStartedEvent,
    EMPEvent,
    FalloutPlumeEvent,
    MOPPLevelChangedEvent,
    NuclearDetonationEvent,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import ModuleId

TS = datetime(2024, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


class TestEvents:
    def test_release_event_creation(self):
        e = CBRNReleaseEvent(
            timestamp=TS, source=ModuleId.CBRN,
            release_id="r1", agent_id="sarin", agent_category=0,
            position_easting=100.0, position_northing=200.0,
            quantity_kg=5.0, delivery_method="artillery",
        )
        assert e.agent_id == "sarin"
        assert e.quantity_kg == 5.0

    def test_events_frozen(self):
        e = NuclearDetonationEvent(
            timestamp=TS, source=ModuleId.CBRN,
            weapon_id="w1", position_easting=0.0, position_northing=0.0,
            yield_kt=10.0, airburst=True,
        )
        with pytest.raises(AttributeError):
            e.yield_kt = 20.0  # type: ignore[misc]

    def test_event_bus_publish(self):
        bus = EventBus()
        received = []
        bus.subscribe(CBRNReleaseEvent, received.append)
        event = CBRNReleaseEvent(
            timestamp=TS, source=ModuleId.CBRN,
            release_id="r1", agent_id="vx", agent_category=0,
            position_easting=0.0, position_northing=0.0,
            quantity_kg=1.0, delivery_method="spray",
        )
        bus.publish(event)
        assert len(received) == 1
        assert received[0].agent_id == "vx"

    def test_all_event_types_instantiate(self):
        """Ensure all 10 event types can be created."""
        events = [
            CBRNReleaseEvent(timestamp=TS, source=ModuleId.CBRN,
                             release_id="r1", agent_id="a", agent_category=0,
                             position_easting=0.0, position_northing=0.0,
                             quantity_kg=1.0, delivery_method="shell"),
            NuclearDetonationEvent(timestamp=TS, source=ModuleId.CBRN,
                                   weapon_id="w1", position_easting=0.0,
                                   position_northing=0.0, yield_kt=10.0, airburst=True),
            ContaminationDetectedEvent(timestamp=TS, source=ModuleId.CBRN,
                                       cell_row=0, cell_col=0, agent_id="a",
                                       concentration_mg_m3=1.0),
            ContaminationClearedEvent(timestamp=TS, source=ModuleId.CBRN,
                                      cell_row=0, cell_col=0, agent_id="a"),
            MOPPLevelChangedEvent(timestamp=TS, source=ModuleId.CBRN,
                                   unit_id="u1", previous_level=0, new_level=4),
            CBRNCasualtyEvent(timestamp=TS, source=ModuleId.CBRN,
                              unit_id="u1", agent_id="a", casualties_incapacitated=1,
                              casualties_lethal=0, dosage_ct=5.0),
            DecontaminationStartedEvent(timestamp=TS, source=ModuleId.CBRN,
                                        unit_id="u1", decon_type=0,
                                        estimated_duration_s=300.0),
            DecontaminationCompletedEvent(timestamp=TS, source=ModuleId.CBRN,
                                          unit_id="u1", decon_type=0,
                                          effectiveness=0.95),
            EMPEvent(timestamp=TS, source=ModuleId.CBRN,
                     center_easting=0.0, center_northing=0.0, radius_m=5000.0,
                     affected_unit_ids=("u1", "u2")),
            FalloutPlumeEvent(timestamp=TS, source=ModuleId.CBRN,
                              detonation_id="d1", initial_center_easting=0.0,
                              initial_center_northing=0.0, wind_direction_rad=0.0,
                              estimated_plume_length_m=10000.0),
        ]
        assert len(events) == 10


# ---------------------------------------------------------------------------
# ModuleId
# ---------------------------------------------------------------------------


class TestModuleId:
    def test_cbrn_in_module_id(self):
        assert ModuleId.CBRN == "cbrn"
        assert ModuleId.CBRN in list(ModuleId)


# ---------------------------------------------------------------------------
# Agent registry
# ---------------------------------------------------------------------------


class TestAgentRegistry:
    def _make_defn(self, agent_id: str = "sarin") -> AgentDefinition:
        return AgentDefinition(agent_id=agent_id, category=int(AgentCategory.NERVE),
                               lct50_mg_min_m3=70.0)

    def test_register_and_get(self):
        reg = AgentRegistry()
        defn = self._make_defn()
        reg.register(defn)
        assert reg.get("sarin") is defn

    def test_get_missing(self):
        reg = AgentRegistry()
        assert reg.get("nonexistent") is None

    def test_all_agents(self):
        reg = AgentRegistry()
        reg.register(self._make_defn("sarin"))
        reg.register(self._make_defn("vx"))
        assert len(reg.all_agents()) == 2

    def test_state_roundtrip(self):
        reg = AgentRegistry()
        reg.register(self._make_defn("sarin"))
        state = reg.get_state()
        reg2 = AgentRegistry()
        reg2.set_state(state)
        assert reg2.get("sarin") is not None
        assert reg2.get("sarin").lct50_mg_min_m3 == 70.0


class TestAgentDefinition:
    def test_pydantic_validation(self):
        defn = AgentDefinition(agent_id="vx", category=0, lct50_mg_min_m3=10.0,
                               persistence_hours=168.0)
        assert defn.agent_id == "vx"
        assert defn.persistence_hours == 168.0

    def test_yaml_roundtrip(self):
        defn = AgentDefinition(agent_id="mustard", category=int(AgentCategory.BLISTER),
                               lct50_mg_min_m3=1500.0, decon_difficulty=0.7)
        data = defn.model_dump()
        restored = AgentDefinition(**data)
        assert restored.agent_id == "mustard"
        assert restored.decon_difficulty == 0.7


# ---------------------------------------------------------------------------
# Stability classification
# ---------------------------------------------------------------------------


class TestStabilityClass:
    def test_strong_sun_light_wind(self):
        """Class A: daytime, light wind, clear sky."""
        assert DispersalEngine.classify_stability(1.0, 0.2, True) == StabilityClass.A

    def test_neutral(self):
        """Class D: moderate-high wind."""
        assert DispersalEngine.classify_stability(6.0, 0.5, True) == StabilityClass.D

    def test_stable_night(self):
        """Class F: nighttime, light wind, clear sky."""
        assert DispersalEngine.classify_stability(1.0, 0.2, False) == StabilityClass.F

    def test_boundary_cases(self):
        """Night moderate wind → D."""
        assert DispersalEngine.classify_stability(4.0, 0.5, False) == StabilityClass.D


# ---------------------------------------------------------------------------
# Sigma coefficients
# ---------------------------------------------------------------------------


class TestSigmaCoefficients:
    def test_sigma_y_stability_ordering(self):
        """Class A should produce larger σy than class F at same distance."""
        sy_a = DispersalEngine.sigma_y(1000.0, StabilityClass.A)
        sy_f = DispersalEngine.sigma_y(1000.0, StabilityClass.F)
        assert sy_a > sy_f

    def test_sigma_z_stability_ordering(self):
        """Class A should produce larger σz than class F."""
        sz_a = DispersalEngine.sigma_z(1000.0, StabilityClass.A)
        sz_f = DispersalEngine.sigma_z(1000.0, StabilityClass.F)
        assert sz_a > sz_f

    def test_sigma_increases_with_distance(self):
        """Sigma should increase with downwind distance."""
        sy_near = DispersalEngine.sigma_y(100.0, StabilityClass.D)
        sy_far = DispersalEngine.sigma_y(1000.0, StabilityClass.D)
        assert sy_far > sy_near


# ---------------------------------------------------------------------------
# Concentration
# ---------------------------------------------------------------------------


class TestConcentration:
    def test_gaussian_decay_with_distance(self):
        """Concentration should decrease with crosswind distance."""
        engine = DispersalEngine()
        puff = PuffState("p0", "sarin", 0.0, 0.0, 1.0, 0.0)
        # Wind blows north (direction=0 rad)
        c_center = engine.compute_concentration(puff, 0.0, 500.0, 5.0, 0.0, StabilityClass.D)
        c_offset = engine.compute_concentration(puff, 200.0, 500.0, 5.0, 0.0, StabilityClass.D)
        assert c_center > c_offset > 0

    def test_wind_direction(self):
        """Upwind points should have zero concentration."""
        engine = DispersalEngine()
        puff = PuffState("p0", "sarin", 0.0, 0.0, 1.0, 0.0)
        # Wind blows north → south of source is upwind
        c_upwind = engine.compute_concentration(puff, 0.0, -500.0, 5.0, 0.0, StabilityClass.D)
        assert c_upwind == 0.0

    def test_ground_reflection(self):
        """Ground-level concentration should be positive downwind."""
        engine = DispersalEngine()
        puff = PuffState("p0", "vx", 0.0, 0.0, 0.5, 0.0)
        c = engine.compute_concentration(puff, 0.0, 300.0, 3.0, 0.0, StabilityClass.D)
        assert c > 0

    def test_zero_at_far_range(self):
        """Concentration should be negligible at very far range."""
        engine = DispersalEngine()
        puff = PuffState("p0", "sarin", 0.0, 0.0, 0.001, 0.0)
        c = engine.compute_concentration(puff, 0.0, 100000.0, 5.0, 0.0, StabilityClass.D)
        assert c < 0.001


# ---------------------------------------------------------------------------
# Puff advection
# ---------------------------------------------------------------------------


class TestPuffAdvection:
    def test_wind_drift_direction(self):
        """Puff should drift in wind direction."""
        engine = DispersalEngine()
        puff = engine.create_puff("sarin", 0.0, 0.0, 1.0, 0.0)
        # Wind blows east (π/2 rad from north)
        engine.advect_puff(puff, 10.0, 5.0, math.pi / 2)
        assert puff.center_e > 0
        assert abs(puff.center_n) < 1.0  # Minimal northward drift

    def test_drift_distance(self):
        """Drift = wind_speed * dt."""
        engine = DispersalEngine()
        puff = engine.create_puff("vx", 0.0, 0.0, 1.0, 0.0)
        engine.advect_puff(puff, 100.0, 10.0, 0.0)  # North
        assert abs(puff.center_n - 1000.0) < 0.1
        assert puff.age_s == 100.0


# ---------------------------------------------------------------------------
# Terrain channeling
# ---------------------------------------------------------------------------


class TestTerrainChanneling:
    def _make_heightmap(self, center_elev: float, neighbor_elev: float):
        """Mock heightmap: center at (500,500), neighbors at offset."""
        class MockHeightmap:
            def elevation_at(self, e, n):
                dist = math.sqrt((e - 500.0) ** 2 + (n - 500.0) ** 2)
                if dist < 25.0:
                    return center_elev
                return neighbor_elev
        return MockHeightmap()

    def test_valley_concentrates(self):
        """Valley (low center) should increase concentration."""
        engine = DispersalEngine()
        hm = self._make_heightmap(10.0, 30.0)  # Center lower by 20m
        result = engine.apply_terrain_channeling(100.0, 500.0, 500.0, hm)
        assert result == pytest.approx(150.0)  # 1.5x default

    def test_ridge_deflects(self):
        """Ridge (high center) should decrease concentration."""
        engine = DispersalEngine()
        hm = self._make_heightmap(30.0, 10.0)  # Center higher by 20m
        result = engine.apply_terrain_channeling(100.0, 500.0, 500.0, hm)
        assert result == pytest.approx(50.0)  # 0.5x default


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------


class TestDispersalState:
    def test_get_set_state(self):
        engine = DispersalEngine()
        engine.create_puff("sarin", 100.0, 200.0, 0.5, 10.0)
        engine.create_puff("vx", 300.0, 400.0, 1.0, 20.0)
        state = engine.get_state()

        engine2 = DispersalEngine()
        engine2.set_state(state)
        assert len(engine2.puffs) == 2
        assert engine2.puffs[0].agent_id == "sarin"

    def test_puff_persistence(self):
        """Puff IDs should be deterministic and unique."""
        engine = DispersalEngine()
        p1 = engine.create_puff("a", 0.0, 0.0, 1.0, 0.0)
        p2 = engine.create_puff("b", 0.0, 0.0, 1.0, 0.0)
        assert p1.puff_id != p2.puff_id
        assert p1.puff_id == "puff_0"
        assert p2.puff_id == "puff_1"
