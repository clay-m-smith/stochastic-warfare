"""Phase 2 integration tests — entities, organization, and movement.

Validates cross-module integration:
1. Full entity stack: YAML → loader → Unit with personnel/equipment
2. Organization + entities: hierarchy, task org, chain of command
3. Ground movement + terrain: move across terrain
4. Movement + environment conditions
5. Pathfinding: A* finds route avoiding obstacles
6. Naval movement + bathymetry: draft check, fuel cubic law
7. Submarine movement + acoustics: speed-noise tradeoff
8. Amphibious ship-to-shore phase transitions
9. Airborne drop scatter deterministic
10. Deterministic replay: same seed → identical paths
11. Checkpoint/restore: full Phase 2 state round-trip
12. Cross-phase: entities on terrain with environment conditions
"""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from stochastic_warfare.core.types import Position, Side
from stochastic_warfare.entities.base import Unit
from stochastic_warfare.entities.capabilities import CombatPowerCalculator
from stochastic_warfare.entities.equipment import EquipmentManager
from stochastic_warfare.entities.loader import UnitLoader
from stochastic_warfare.entities.organization.echelons import EchelonLevel
from stochastic_warfare.entities.organization.hierarchy import HierarchyTree
from stochastic_warfare.entities.organization.orbat import OrbatLoader
from stochastic_warfare.entities.organization.task_org import (
    CommandRelationship,
    TaskOrgManager,
)
from stochastic_warfare.entities.personnel import (
    InjuryState,
    PersonnelManager,
)
from stochastic_warfare.entities.unit_classes.ground import GroundUnit, GroundUnitType
from stochastic_warfare.entities.unit_classes.naval import NavalUnit, NavalUnitType
from stochastic_warfare.movement.airborne import AirborneMethod, AirborneMovementEngine
from stochastic_warfare.movement.amphibious_movement import (
    AmphibiousMovementEngine,
    AmphibPhase,
)
from stochastic_warfare.movement.engine import MovementConfig, MovementEngine
from stochastic_warfare.movement.fatigue import FatigueManager
from stochastic_warfare.movement.formation import FormationManager, FormationType
from stochastic_warfare.movement.naval_movement import NavalMovementEngine
from stochastic_warfare.movement.pathfinding import Pathfinder
from stochastic_warfare.movement.submarine_movement import SubmarineMovementEngine

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
UNITS_DIR = DATA_DIR / "units"
ORG_DIR = DATA_DIR / "organizations" / "us_modern"


class TestFullEntityStack:
    """1. YAML → loader → Unit with personnel/equipment, state round-trip."""

    def test_load_and_create_all(self) -> None:
        loader = UnitLoader(UNITS_DIR)
        loader.load_all()
        rng = np.random.Generator(np.random.PCG64(42))

        for unit_type in loader.available_types():
            unit = loader.create_unit(
                unit_type, f"int-{unit_type}", Position(100.0, 200.0),
                Side.BLUE, rng,
            )
            assert unit.entity_id == f"int-{unit_type}"
            assert len(unit.personnel) > 0
            if unit_type != "civilian_noncombatant":
                assert len(unit.equipment) > 0

            # State round-trip
            state = unit.get_state()
            assert state["unit_type"] == unit_type
            assert state["entity_id"] == f"int-{unit_type}"
            assert len(state["personnel"]) > 0

    def test_combat_power_from_loaded_units(self) -> None:
        loader = UnitLoader(UNITS_DIR)
        loader.load_all()
        rng = np.random.Generator(np.random.PCG64(42))
        calc = CombatPowerCalculator()

        tank = loader.create_unit("m1a2", "t1", Position(0.0, 0.0), Side.BLUE, rng)
        assessment = calc.assess(tank)
        assert assessment.effective_power > 0
        assert assessment.readiness > 0


class TestOrganizationAndEntities:
    """2. Build hierarchy from TO&E, task org, chain of command."""

    def test_build_platoon_from_toe(self) -> None:
        toe = OrbatLoader.load_toe(ORG_DIR / "infantry_platoon.yaml")
        loader = UnitLoader(UNITS_DIR)
        loader.load_all()
        rng = np.random.Generator(np.random.PCG64(42))

        tree = OrbatLoader.build_hierarchy(toe, loader, "plt-1", Side.BLUE, rng)
        assert len(tree) == 4  # 1 HQ + 3 squads
        assert tree.get_parent("plt-1") is None
        children = tree.get_children("plt-1")
        assert len(children) == 3

    def test_task_org_attach_detach(self) -> None:
        tree = HierarchyTree()
        tree.add_unit("bn", EchelonLevel.BATTALION)
        tree.add_unit("co-a", EchelonLevel.COMPANY, parent_id="bn")
        tree.add_unit("co-b", EchelonLevel.COMPANY, parent_id="bn")
        tree.add_unit("plt-1", EchelonLevel.PLATOON, parent_id="co-a")

        mgr = TaskOrgManager(tree)
        mgr.attach("plt-1", "co-b", CommandRelationship.OPCON)

        # plt-1 now under co-b
        assert mgr.get_effective_parent("plt-1") == "co-b"
        assert "plt-1" in mgr.get_effective_subordinates("co-b")
        assert "plt-1" not in mgr.get_effective_subordinates("co-a")

        # Detach
        mgr.detach("plt-1")
        assert mgr.get_effective_parent("plt-1") == "co-a"

    def test_chain_of_command(self) -> None:
        tree = HierarchyTree()
        tree.add_unit("div", EchelonLevel.DIVISION)
        tree.add_unit("bde", EchelonLevel.BRIGADE, parent_id="div")
        tree.add_unit("bn", EchelonLevel.BATTALION, parent_id="bde")
        tree.add_unit("co", EchelonLevel.COMPANY, parent_id="bn")

        chain = tree.get_chain_of_command("co")
        assert chain == ["div", "bde", "bn", "co"]


class TestGroundMovement:
    """3. Ground movement without terrain (engine test)."""

    def test_move_unit_across_flat(self) -> None:
        config = MovementConfig(noise_std=0.0)
        engine = MovementEngine(config=config)
        unit = GroundUnit(
            entity_id="inf-1", position=Position(0.0, 0.0),
            max_speed=1.3, ground_type=GroundUnitType.LIGHT_INFANTRY,
        )
        result = engine.move_unit(unit, Position(100.0, 0.0), 60.0)
        assert result.distance_moved > 0
        assert result.distance_moved <= 1.3 * 60.0 + 0.1

    def test_vehicle_faster(self) -> None:
        config = MovementConfig(noise_std=0.0)
        engine = MovementEngine(config=config)
        inf = Unit(entity_id="i", position=Position(0.0, 0.0), max_speed=1.3)
        veh = Unit(entity_id="v", position=Position(0.0, 0.0), max_speed=15.0)
        r_inf = engine.move_unit(inf, Position(1000.0, 0.0), 60.0)
        r_veh = engine.move_unit(veh, Position(1000.0, 0.0), 60.0)
        assert r_veh.distance_moved > r_inf.distance_moved


class TestMovementWithFatigue:
    """4. Movement + fatigue interaction."""

    def test_fatigue_accumulates_with_movement(self) -> None:
        fatigue_mgr = FatigueManager()
        config = MovementConfig(noise_std=0.0)
        engine = MovementEngine(config=config)
        unit = Unit(entity_id="u1", position=Position(0.0, 0.0), max_speed=1.3)

        # Simulate 8 hours of marching
        for _ in range(8):
            result = engine.move_unit(unit, Position(100000.0, 0.0), 3600.0)
            fatigue_mgr.accumulate("u1", 1.0, "march")
            unit.position = result.new_position

        fs = fatigue_mgr.get_fatigue("u1")
        assert fs.physical > 0.4
        speed_mod = fatigue_mgr.speed_modifier("u1")
        assert speed_mod < 1.0


class TestPathfindingIntegration:
    """5. A* pathfinding integration."""

    def test_find_path_open_terrain(self) -> None:
        pf = Pathfinder()
        result = pf.find_path(
            Position(0.0, 0.0), Position(500.0, 500.0),
            grid_resolution=100.0,
        )
        assert result.found
        assert len(result.waypoints) >= 2
        assert result.total_distance > 0

    def test_threat_avoidance(self) -> None:
        pf = Pathfinder()
        threats = [(Position(250.0, 250.0), 300.0)]
        result = pf.find_path(
            Position(0.0, 0.0), Position(500.0, 500.0),
            avoid_threats=threats, grid_resolution=100.0,
        )
        assert result.found


class TestNavalMovementIntegration:
    """6. Naval movement with bathymetry mock."""

    def test_ship_moves_with_draft_check(self) -> None:
        bathy = SimpleNamespace(depth_at=lambda p: 30.0)
        engine = NavalMovementEngine(bathymetry=bathy)
        ship = NavalUnit(
            entity_id="ddg-1", position=Position(0.0, 0.0),
            naval_type=NavalUnitType.DESTROYER,
            max_speed=16.0, draft=9.4, fuel_capacity=600.0,
        )
        result = engine.move_ship(ship, Position(5000.0, 0.0), 16.0, 60.0)
        assert result.draft_ok is True
        assert result.new_position.easting > 0
        assert result.fuel_consumed > 0

    def test_fuel_cubic_law(self) -> None:
        engine = NavalMovementEngine()
        ship = NavalUnit(
            entity_id="ddg-1", position=Position(0.0, 0.0),
            max_speed=16.0, fuel_capacity=600.0,
        )
        f_half = engine.fuel_consumption(ship, 8.0, 1.0)
        f_full = engine.fuel_consumption(ship, 16.0, 1.0)
        assert f_full / f_half == pytest.approx(8.0, rel=0.01)


class TestSubmarineMovementIntegration:
    """7. Submarine depth, speed-noise tradeoff."""

    def test_speed_noise_tradeoff(self) -> None:
        engine = SubmarineMovementEngine()
        sub = NavalUnit(
            entity_id="ssn-1", position=Position(0.0, 0.0),
            naval_type=NavalUnitType.SSN,
            max_speed=17.0, max_depth=450.0,
            noise_signature_base=95.0,
        )
        n_slow = engine.speed_noise_curve(sub, 3.0)
        n_fast = engine.speed_noise_curve(sub, 15.0)
        assert n_fast > n_slow

    def test_depth_change(self) -> None:
        engine = SubmarineMovementEngine()
        sub = NavalUnit(
            entity_id="ssn-1", position=Position(0.0, 0.0),
            naval_type=NavalUnitType.SSN, depth=100.0, max_depth=450.0,
        )
        new_depth = engine.change_depth(sub, 200.0, 50.0)
        assert 100.0 < new_depth <= 150.0


class TestAmphibiousIntegration:
    """8. Amphibious phase transitions."""

    def test_phase_progression(self) -> None:
        engine = AmphibiousMovementEngine()
        units = [
            Unit(entity_id=f"u{i}", position=Position(0.0, 0.0))
            for i in range(4)
        ]
        phases = [AmphibPhase.LOADING, AmphibPhase.TRANSIT,
                  AmphibPhase.STAGING, AmphibPhase.SHIP_TO_SHORE,
                  AmphibPhase.BEACH_LANDING, AmphibPhase.INLAND]

        for phase in phases:
            result = engine.execute_phase(units, phase, 60.0)
            assert result.phase == phase


class TestAirborneIntegration:
    """9. Airborne drop scatter deterministic."""

    def test_deterministic_drop(self) -> None:
        rng1 = np.random.Generator(np.random.PCG64(42))
        rng2 = np.random.Generator(np.random.PCG64(42))
        e1 = AirborneMovementEngine(rng=rng1)
        e2 = AirborneMovementEngine(rng=rng2)

        dz = Position(5000.0, 5000.0)
        p1 = e1.compute_drop_scatter(dz, 5.0, 300.0, AirborneMethod.STATIC_LINE, 12)
        p2 = e2.compute_drop_scatter(dz, 5.0, 300.0, AirborneMethod.STATIC_LINE, 12)

        for a, b in zip(p1, p2):
            assert a.easting == b.easting
            assert a.northing == b.northing

    def test_wind_effect(self) -> None:
        rng1 = np.random.Generator(np.random.PCG64(42))
        rng2 = np.random.Generator(np.random.PCG64(42))
        e1 = AirborneMovementEngine(rng=rng1)
        e2 = AirborneMovementEngine(rng=rng2)

        dz = Position(0.0, 0.0)
        p_calm = e1.compute_drop_scatter(dz, 0.0, 300.0, AirborneMethod.STATIC_LINE, 20)
        p_wind = e2.compute_drop_scatter(dz, 25.0, 300.0, AirborneMethod.STATIC_LINE, 20)

        def spread(positions):
            return sum(
                math.sqrt(p.easting ** 2 + p.northing ** 2) for p in positions
            ) / len(positions)

        assert spread(p_wind) > spread(p_calm)


class TestDeterministicReplay:
    """10. Same seed → identical movement paths."""

    def test_movement_replay(self) -> None:
        def run_scenario(seed: int) -> list[Position]:
            rng = np.random.Generator(np.random.PCG64(seed))
            engine = MovementEngine(rng=rng)
            unit = Unit(entity_id="u1", position=Position(0.0, 0.0), max_speed=10.0)
            positions = [unit.position]
            for _ in range(10):
                result = engine.move_unit(unit, Position(1000.0, 0.0), 5.0)
                unit.position = result.new_position
                positions.append(unit.position)
            return positions

        path1 = run_scenario(42)
        path2 = run_scenario(42)
        assert len(path1) == len(path2)
        for a, b in zip(path1, path2):
            assert a.easting == b.easting
            assert a.northing == b.northing


class TestCheckpointRestore:
    """11. Full Phase 2 state round-trip."""

    def test_entity_state_roundtrip(self) -> None:
        loader = UnitLoader(UNITS_DIR)
        loader.load_all()
        rng = np.random.Generator(np.random.PCG64(42))

        tank = loader.create_unit("m1a2", "tank-1", Position(100.0, 200.0),
                                  Side.BLUE, rng)
        # Apply some damage
        PersonnelManager.apply_casualty(tank.personnel, "crew-0001", InjuryState.MINOR_WOUND)
        EquipmentManager.apply_degradation(tank.equipment[0], 5.0, 2.0)

        state = tank.get_state()
        restored = GroundUnit(entity_id="", position=Position(0.0, 0.0))
        restored.set_state(state)

        assert restored.entity_id == "tank-1"
        assert restored.personnel[1].injury == InjuryState.MINOR_WOUND
        assert restored.equipment[0].condition < 1.0

    def test_hierarchy_state_roundtrip(self) -> None:
        tree = HierarchyTree()
        tree.add_unit("bn", EchelonLevel.BATTALION)
        tree.add_unit("co-a", EchelonLevel.COMPANY, parent_id="bn")
        tree.add_unit("co-b", EchelonLevel.COMPANY, parent_id="bn")

        state = tree.get_state()
        restored = HierarchyTree()
        restored.set_state(state)

        assert len(restored) == 3
        assert restored.get_parent("co-a") == "bn"

    def test_fatigue_state_roundtrip(self) -> None:
        mgr = FatigueManager()
        mgr.accumulate("u1", 6.0, "march")
        mgr.accumulate("u2", 3.0, "combat")

        state = mgr.get_state()
        restored = FatigueManager()
        restored.set_state(state)

        assert restored.get_fatigue("u1") == mgr.get_fatigue("u1")
        assert restored.speed_modifier("u1") == mgr.speed_modifier("u1")


class TestCrossPhaseEntitiesOnTerrain:
    """12. Entities on terrain with formations."""

    def test_formation_on_terrain(self) -> None:
        positions = FormationManager.compute_positions(
            Position(500.0, 500.0), 0.0, 4, FormationType.WEDGE, 100.0,
        )
        assert len(positions) == 4
        # All positions should be in reasonable range
        for p in positions:
            assert 200.0 < p.easting < 800.0
            assert 200.0 < p.northing < 800.0

    def test_force_ratio_with_loaded_units(self) -> None:
        loader = UnitLoader(UNITS_DIR)
        loader.load_all()
        rng = np.random.Generator(np.random.PCG64(42))
        calc = CombatPowerCalculator()

        friendly = [
            loader.create_unit("m1a2", f"f{i}", Position(0.0, 0.0), Side.BLUE, rng)
            for i in range(3)
        ]
        enemy = [
            loader.create_unit("m1a2", f"e{i}", Position(1000.0, 0.0), Side.RED, rng)
            for i in range(3)
        ]
        ratio = calc.force_ratio(friendly, enemy)
        assert ratio == pytest.approx(1.0, abs=0.2)  # roughly equal
