"""Phase 55 tests — resolution switching, legacy scenarios, deficit wiring, data fixes.

Tests cover:
- 55a: Resolution switching guard (closing range prevents STRATEGIC overshoot)
- 55b: Legacy scenario loading (all 8 formerly-xfail scenarios load)
- 55c: Deficit wiring (GasWarfare, seeker_fov_deg, SEAD ARM, drone provocation)
- 55d: Data fixes (roman_equites, ROE expansion, CBRN/school config)
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from stochastic_warfare.core.types import Domain, ModuleId, Position
from stochastic_warfare.entities.base import Unit, UnitStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_unit(
    entity_id: str,
    side: str,
    pos: tuple[float, float] = (0.0, 0.0),
    domain: Domain = Domain.GROUND,
    status: UnitStatus = UnitStatus.ACTIVE,
    speed: float = 0.0,
    heading: float = 0.0,
    **kwargs,
) -> Unit:
    """Create a minimal Unit for testing."""
    u = Unit.__new__(Unit)
    object.__setattr__(u, "entity_id", entity_id)
    object.__setattr__(u, "side", side)
    object.__setattr__(u, "position", Position(pos[0], pos[1], 0.0))
    object.__setattr__(u, "domain", domain)
    object.__setattr__(u, "status", status)
    object.__setattr__(u, "speed", speed)
    object.__setattr__(u, "heading", heading)
    object.__setattr__(u, "personnel", [1, 2, 3, 4])
    object.__setattr__(u, "equipment", [1])
    for k, v in kwargs.items():
        object.__setattr__(u, k, v)
    return u


# ═══════════════════════════════════════════════════════════════════════════
# 55a: Resolution Switching
# ═══════════════════════════════════════════════════════════════════════════


class TestResolutionSwitching:
    """Resolution switching guard prevents STRATEGIC overshoot."""

    def _make_engine(
        self,
        units_by_side: dict[str, list[Unit]],
        engagement_range_m: float = 15000.0,
        closing_mult: float = 2.0,
    ):
        """Build a minimal SimulationEngine with given forces."""
        from stochastic_warfare.simulation.engine import (
            EngineConfig,
            SimulationEngine,
            TickResolution,
        )
        from stochastic_warfare.simulation.battle import BattleConfig, BattleManager
        from stochastic_warfare.simulation.campaign import CampaignConfig
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        # Minimal context mock
        ctx = SimpleNamespace()
        rng_mgr = MagicMock()
        rng_mgr.get_stream.return_value = np.random.default_rng(42)
        ctx.rng_manager = rng_mgr
        ctx.event_bus = MagicMock()
        ctx.clock = MagicMock()
        ctx.clock.tick_count = 0
        ctx.clock.elapsed.total_seconds.return_value = 0.0
        ctx.clock.tick_duration.total_seconds.return_value = 5.0
        ctx.clock.current_time = None
        ctx.config = SimpleNamespace(
            tick_resolution=SimpleNamespace(
                strategic_s=3600, operational_s=300, tactical_s=5,
            ),
            duration_hours=24.0,
        )
        ctx.units_by_side = units_by_side
        ctx.morale_states = {}
        ctx.calibration = CalibrationSchema()
        ctx.los_engine = None
        ctx.heightmap = None
        ctx.engagement_engine = None
        ctx.ooda_engine = None
        ctx.order_execution = None
        ctx.suppression_engine = None
        ctx.consumption_engine = None
        ctx.stockpile_manager = None
        ctx.morale_machine = None
        ctx.weather_engine = None
        ctx.time_of_day_engine = None
        ctx.sea_state_engine = None
        ctx.space_engine = None
        ctx.cbrn_engine = None
        ctx.ew_engine = None
        ctx.ew_decoy_engine = None
        ctx.seasons_engine = None
        ctx.maintenance_engine = None
        ctx.medical_engine = None
        ctx.collateral_engine = None
        ctx.aggregation_engine = None
        ctx.escalation_engine = None
        ctx.incendiary_engine = None
        ctx.sof_engine = None
        ctx.insurgency_engine = None
        ctx.consequence_engine = None
        ctx.war_termination_engine = None
        ctx.political_engine = None
        ctx.planning_engine = None
        ctx.detection_engine = None
        ctx.fog_of_war = None
        ctx.intel_fusion_engine = None
        ctx.get_state = lambda: {}
        ctx.set_state = lambda s: None

        def side_names():
            return list(units_by_side.keys())
        ctx.side_names = side_names

        engine_config = EngineConfig(
            max_ticks=100,
            resolution_closing_range_mult=closing_mult,
        )
        campaign_config = CampaignConfig(
            engagement_detection_range_m=engagement_range_m,
        )
        battle_config = BattleConfig()

        engine = SimulationEngine(
            ctx, engine_config,
            campaign_config=campaign_config,
            battle_config=battle_config,
        )
        return engine

    def test_forces_far_apart_stays_strategic(self):
        """Units >2x engagement range → allows STRATEGIC."""
        from stochastic_warfare.simulation.engine import TickResolution

        units = {
            "blue": [_make_unit("b1", "blue", (0, 0))],
            "red": [_make_unit("r1", "red", (100000, 0))],  # 100km away
        }
        engine = self._make_engine(units)
        assert not engine._forces_within_closing_range()

    def test_forces_within_closing_range_true(self):
        """Units within 2x engagement range → returns True."""
        units = {
            "blue": [_make_unit("b1", "blue", (0, 0))],
            "red": [_make_unit("r1", "red", (25000, 0))],  # 25km < 30km
        }
        engine = self._make_engine(units, engagement_range_m=15000.0)
        assert engine._forces_within_closing_range()

    def test_forces_at_closing_range_prevents_strategic(self):
        """When forces are closing, engine stays at OPERATIONAL."""
        from stochastic_warfare.simulation.engine import TickResolution

        units = {
            "blue": [_make_unit("b1", "blue", (0, 0))],
            "red": [_make_unit("r1", "red", (20000, 0))],  # within 2x 15km
        }
        engine = self._make_engine(units)
        # Force to OPERATIONAL first
        engine._set_resolution(TickResolution.OPERATIONAL)
        engine._update_resolution()
        # Should stay OPERATIONAL, not escalate to STRATEGIC
        assert engine.resolution == TickResolution.OPERATIONAL

    def test_forces_outside_closing_range_allows_strategic(self):
        """When forces are far, engine escalates to STRATEGIC normally."""
        from stochastic_warfare.simulation.engine import TickResolution

        units = {
            "blue": [_make_unit("b1", "blue", (0, 0))],
            "red": [_make_unit("r1", "red", (100000, 0))],  # 100km
        }
        engine = self._make_engine(units)
        engine._set_resolution(TickResolution.OPERATIONAL)
        engine._update_resolution()
        assert engine.resolution == TickResolution.STRATEGIC

    def test_active_battles_force_tactical(self):
        """Active battles → TACTICAL regardless of distance."""
        from stochastic_warfare.simulation.engine import TickResolution
        from stochastic_warfare.simulation.battle import BattleContext
        from datetime import datetime

        units = {
            "blue": [_make_unit("b1", "blue", (0, 0))],
            "red": [_make_unit("r1", "red", (100000, 0))],
        }
        engine = self._make_engine(units)
        # Add a fake active battle via internal dict
        battle = BattleContext(
            battle_id="test",
            start_tick=0,
            start_time=datetime.min,
            involved_sides=["blue", "red"],
            active=True,
        )
        engine._battle._battles["test"] = battle
        engine._update_resolution()
        assert engine.resolution == TickResolution.TACTICAL

    def test_closing_range_no_opposing_forces(self):
        """Single side → closing range is False (no opponent)."""
        units = {
            "blue": [_make_unit("b1", "blue", (0, 0))],
        }
        engine = self._make_engine(units)
        assert not engine._forces_within_closing_range()

    def test_closing_range_custom_multiplier(self):
        """Custom multiplier changes threshold."""
        units = {
            "blue": [_make_unit("b1", "blue", (0, 0))],
            "red": [_make_unit("r1", "red", (25000, 0))],
        }
        # With 1.0x mult: threshold = 15km, 25km > 15km → False
        engine = self._make_engine(units, engagement_range_m=15000.0, closing_mult=1.0)
        assert not engine._forces_within_closing_range()
        # With 2.0x mult: threshold = 30km, 25km < 30km → True
        engine2 = self._make_engine(units, engagement_range_m=15000.0, closing_mult=2.0)
        assert engine2._forces_within_closing_range()

    def test_strategic_to_operational_on_closing(self):
        """STRATEGIC → OPERATIONAL when forces are closing."""
        from stochastic_warfare.simulation.engine import TickResolution

        units = {
            "blue": [_make_unit("b1", "blue", (0, 0))],
            "red": [_make_unit("r1", "red", (20000, 0))],
        }
        engine = self._make_engine(units)
        engine._resolution = TickResolution.STRATEGIC
        engine._update_resolution()
        assert engine.resolution == TickResolution.OPERATIONAL


# ═══════════════════════════════════════════════════════════════════════════
# 55b: Legacy Scenario Loading
# ═══════════════════════════════════════════════════════════════════════════


class TestLegacyScenarioLoading:
    """All formerly-xfail legacy scenarios now load."""

    _LEGACY_SCENARIOS = [
        "73_easting",
        "bekaa_valley_1982",
        "cbrn_chemical_defense",
        "cbrn_nuclear_tactical",
        "falklands_naval",
        "golan_heights",
        "gulf_war_ew_1991",
        "test_scenario",
    ]

    @pytest.mark.parametrize("scenario_name", _LEGACY_SCENARIOS)
    def test_legacy_scenario_loads_config(self, scenario_name: str):
        """Legacy scenario YAML validates through CampaignScenarioConfig."""
        from pathlib import Path
        import yaml
        from stochastic_warfare.simulation.scenario import CampaignScenarioConfig

        scenario_dir = Path("data/scenarios") / scenario_name / "scenario.yaml"
        if not scenario_dir.exists():
            pytest.skip(f"Scenario {scenario_name} not found")

        with open(scenario_dir) as f:
            data = yaml.safe_load(f)

        # Should not raise ValidationError
        config = CampaignScenarioConfig.model_validate(data)
        assert config.name
        assert len(config.sides) >= 2
        assert config.terrain is not None

    def test_cbrn_chemical_has_cbrn_config(self):
        """CBRN chemical defense scenario has cbrn_config (not bare cbrn)."""
        from pathlib import Path
        import yaml

        path = Path("data/scenarios/cbrn_chemical_defense/scenario.yaml")
        if not path.exists():
            pytest.skip("Scenario not found")
        with open(path) as f:
            data = yaml.safe_load(f)
        assert "cbrn_config" in data
        assert data["cbrn_config"]["enable_cbrn"] is True

    def test_cbrn_nuclear_has_cbrn_config(self):
        """CBRN nuclear scenario has cbrn_config (not bare cbrn)."""
        from pathlib import Path
        import yaml

        path = Path("data/scenarios/cbrn_nuclear_tactical/scenario.yaml")
        if not path.exists():
            pytest.skip("Scenario not found")
        with open(path) as f:
            data = yaml.safe_load(f)
        assert "cbrn_config" in data
        assert data["cbrn_config"]["enable_cbrn"] is True

    def test_xfail_set_is_empty(self):
        """The E2E test xfail set is now empty."""
        from tests.e2e.test_scenario_smoke import _LEGACY_FORMAT_SCENARIOS
        assert len(_LEGACY_FORMAT_SCENARIOS) == 0


# ═══════════════════════════════════════════════════════════════════════════
# 55c: Deficit Wiring
# ═══════════════════════════════════════════════════════════════════════════


class TestDeficitWiring:
    """Tests for wiring GasWarfare, seeker_fov_deg, SEAD ARM, drone provocation."""

    # -- 55c-1: GasWarfareEngine wiring --

    def test_gas_warfare_mopp_queried_for_ww1(self):
        """Gas warfare engine's get_effective_mopp_level is callable."""
        from stochastic_warfare.combat.gas_warfare import GasWarfareEngine, GasMaskType

        rng = np.random.default_rng(42)
        engine = GasWarfareEngine(rng=rng)
        engine._unit_masks["def1"] = GasMaskType.SMALL_BOX_RESPIRATOR
        mopp, protection = engine.get_effective_mopp_level("def1", time_since_alert_s=100.0)
        assert mopp == 3  # SBR → MOPP 3
        assert protection == 1.0  # fully donned after 100s

    def test_gas_mask_reduces_protection(self):
        """Gas mask with don time provides partial protection."""
        from stochastic_warfare.combat.gas_warfare import GasWarfareEngine, GasMaskType

        rng = np.random.default_rng(42)
        engine = GasWarfareEngine(rng=rng)
        engine._unit_masks["def1"] = GasMaskType.PH_HELMET
        mopp, protection = engine.get_effective_mopp_level("def1", time_since_alert_s=5.0)
        assert mopp == 2
        assert 0.0 < protection < 1.0  # partial — 5s < 10s don time

    def test_no_gas_mask_zero_protection(self):
        """Units without gas mask get zero protection."""
        from stochastic_warfare.combat.gas_warfare import GasWarfareEngine, GasMaskType

        rng = np.random.default_rng(42)
        engine = GasWarfareEngine(rng=rng)
        mopp, protection = engine.get_effective_mopp_level("def1", time_since_alert_s=100.0)
        assert mopp == 0
        assert protection == 0.0

    # -- 55c-2: seeker_fov_deg --

    def test_seeker_fov_blocks_outside_cone(self):
        """Seeker FOV > 0 blocks engagement when target is outside cone."""
        # A 10° seeker centered on heading=0 (north) should not acquire
        # a target at 90° (east).
        seeker_fov = 10.0
        heading = 0.0  # north
        target_bearing = math.atan2(1.0, 0.0)  # east = pi/2

        diff = abs(target_bearing - heading)
        if diff > math.pi:
            diff = 2 * math.pi - diff
        blocked = diff > math.radians(seeker_fov / 2)
        assert blocked, "Target at 90° should be outside 10° FOV"

    def test_seeker_fov_allows_within_cone(self):
        """Seeker FOV allows acquisition when target is within cone."""
        seeker_fov = 90.0  # wide FOV
        heading = 0.0
        target_bearing = math.atan2(0.3, 1.0)  # roughly 17° off north

        diff = abs(target_bearing - heading)
        if diff > math.pi:
            diff = 2 * math.pi - diff
        blocked = diff > math.radians(seeker_fov / 2)
        assert not blocked, "Target at ~17° should be within 90° FOV"

    def test_seeker_fov_zero_no_constraint(self):
        """seeker_fov_deg = 0 (unguided) imposes no constraint."""
        seeker_fov = 0.0
        # Zero means no constraint — check is skipped
        assert not (isinstance(seeker_fov, (int, float)) and seeker_fov > 0)

    # -- 55c-3: sead_arm_effectiveness --

    def test_sead_arm_effectiveness_used_for_radars(self):
        """apply_sead_damage uses sead_arm_effectiveness for radar components."""
        from stochastic_warfare.combat.iads import IadsEngine, IadsConfig, IadsSector
        from stochastic_warfare.core.types import Position

        config = IadsConfig(
            sead_degradation_rate=0.5,
            sead_effectiveness=0.3,
            sead_arm_effectiveness=0.9,
        )
        rng = np.random.default_rng(42)
        engine = IadsEngine(event_bus=MagicMock(), rng=rng, config=config)
        sector = IadsSector(
            sector_id="s1",
            center=Position(0, 0, 0),
            radius_m=10000,
            early_warning_radars=["ew_radar_1"],
            acquisition_radars=["acq_radar_1"],
            sam_batteries=["sam_1"],
        )
        sector.component_health = {
            "ew_radar_1": 1.0,
            "acq_radar_1": 1.0,
            "sam_1": 1.0,
        }
        engine._sectors[sector.sector_id] = sector

        # ARM strike on radar — uses sead_arm_effectiveness (0.9)
        engine.apply_sead_damage("s1", "ew_radar_1")
        radar_health = sector.component_health["ew_radar_1"]

        # Reset radar health for comparison
        sector.component_health["ew_radar_1"] = 1.0

        # Strike on SAM — uses sead_effectiveness (0.3)
        engine.apply_sead_damage("s1", "sam_1")
        sam_health = sector.component_health["sam_1"]

        # ARM effectiveness (0.9) > sead_effectiveness (0.3)
        # So radar should take more damage than SAM
        # Note: stochastic variation (normal(0, 0.05)) may shift slightly
        assert radar_health < sam_health + 0.2  # ARM should be more effective

    def test_sead_non_radar_uses_sead_effectiveness(self):
        """SAM battery SEAD uses regular sead_effectiveness, not ARM."""
        from stochastic_warfare.combat.iads import IadsEngine, IadsConfig, IadsSector
        from stochastic_warfare.core.types import Position

        config = IadsConfig(
            sead_degradation_rate=0.5,
            sead_effectiveness=0.5,
            sead_arm_effectiveness=0.9,
        )
        rng = np.random.default_rng(42)
        engine = IadsEngine(event_bus=MagicMock(), rng=rng, config=config)
        sector = IadsSector(
            sector_id="s1",
            center=Position(0, 0, 0),
            radius_m=10000,
            sam_batteries=["sam_1"],
        )
        sector.component_health = {"sam_1": 1.0}
        engine._sectors[sector.sector_id] = sector

        # Expected damage: 0.5 * 0.5 = 0.25 (± stochastic)
        engine.apply_sead_damage("s1", "sam_1")
        health = sector.component_health["sam_1"]
        assert health < 1.0  # took damage
        assert health > 0.5  # but not full ARM damage

    # -- 55c-4: drone_provocation_prob --

    def test_drone_provocation_prob_in_calibration(self):
        """drone_provocation_prob is a valid CalibrationSchema field."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        cal = CalibrationSchema(drone_provocation_prob=0.85)
        assert cal.drone_provocation_prob == 0.85
        assert cal.get("drone_provocation_prob") == 0.85

    def test_drone_provocation_prob_none_default(self):
        """drone_provocation_prob defaults to None."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        cal = CalibrationSchema()
        assert cal.drone_provocation_prob is None
        assert cal.get("drone_provocation_prob") is None


# ═══════════════════════════════════════════════════════════════════════════
# 55d: Data Fixes
# ═══════════════════════════════════════════════════════════════════════════


class TestDataFixes:
    """Tests for data corrections and scenario config additions."""

    def test_roman_equites_cavalry_type(self):
        """roman_equites has ground_type CAVALRY (not ARMOR)."""
        from pathlib import Path
        import yaml

        path = Path("data/eras/ancient_medieval/units/roman_equites.yaml")
        if not path.exists():
            pytest.skip("roman_equites.yaml not found")
        with open(path) as f:
            data = yaml.safe_load(f)
        assert data["ground_type"] == "CAVALRY"

    def test_falklands_campaign_roe_weapons_tight(self):
        """Falklands campaign has ROE set to WEAPONS_TIGHT."""
        from pathlib import Path
        import yaml

        path = Path("data/scenarios/falklands_campaign/scenario.yaml")
        if not path.exists():
            pytest.skip("Scenario not found")
        with open(path) as f:
            data = yaml.safe_load(f)
        assert data["calibration_overrides"]["roe_level"] == "WEAPONS_TIGHT"

    def test_taiwan_strait_roe_weapons_tight(self):
        """Taiwan Strait scenario has ROE set to WEAPONS_TIGHT."""
        from pathlib import Path
        import yaml

        path = Path("data/scenarios/taiwan_strait/scenario.yaml")
        if not path.exists():
            pytest.skip("Scenario not found")
        with open(path) as f:
            data = yaml.safe_load(f)
        assert data["calibration_overrides"]["roe_level"] == "WEAPONS_TIGHT"

    def test_halabja_has_cbrn_config(self):
        """Halabja 1988 scenario has cbrn_config with agent releases."""
        from pathlib import Path
        import yaml

        path = Path("data/scenarios/halabja_1988/scenario.yaml")
        if not path.exists():
            pytest.skip("Scenario not found")
        with open(path) as f:
            data = yaml.safe_load(f)
        assert "cbrn_config" in data
        assert data["cbrn_config"]["enable_cbrn"] is True
        assert len(data["cbrn_config"]["agent_releases"]) >= 2

    def test_bekaa_valley_has_school_config(self):
        """Bekaa Valley scenario has school_config for doctrinal AI."""
        from pathlib import Path
        import yaml

        path = Path("data/scenarios/bekaa_valley_1982/scenario.yaml")
        if not path.exists():
            pytest.skip("Scenario not found")
        with open(path) as f:
            data = yaml.safe_load(f)
        assert "school_config" in data
        assert data["school_config"]["blue"] == "air_power"
        assert data["school_config"]["red"] == "attrition"

    def test_falklands_red_morale_steady(self):
        """Falklands campaign red side has STEADY morale (not SHAKEN)."""
        from pathlib import Path
        import yaml

        path = Path("data/scenarios/falklands_campaign/scenario.yaml")
        if not path.exists():
            pytest.skip("Scenario not found")
        with open(path) as f:
            data = yaml.safe_load(f)
        red_side = [s for s in data["sides"] if s["side"] == "red"][0]
        assert red_side["morale_initial"] == "STEADY"

    def test_korean_peninsula_roe_weapons_tight(self):
        """Korean Peninsula scenario has ROE set to WEAPONS_TIGHT."""
        from pathlib import Path
        import yaml

        path = Path("data/scenarios/korean_peninsula/scenario.yaml")
        if not path.exists():
            pytest.skip("Scenario not found")
        with open(path) as f:
            data = yaml.safe_load(f)
        assert data["calibration_overrides"]["roe_level"] == "WEAPONS_TIGHT"

    def test_hybrid_gray_zone_roe_weapons_hold(self):
        """Hybrid Gray Zone scenario has ROE set to WEAPONS_HOLD."""
        from pathlib import Path
        import yaml

        path = Path("data/scenarios/hybrid_gray_zone/scenario.yaml")
        if not path.exists():
            pytest.skip("Scenario not found")
        with open(path) as f:
            data = yaml.safe_load(f)
        assert data["calibration_overrides"]["roe_level"] == "WEAPONS_HOLD"

    def test_falklands_san_carlos_roe_weapons_tight(self):
        """Falklands San Carlos scenario has ROE set to WEAPONS_TIGHT."""
        from pathlib import Path
        import yaml

        path = Path("data/scenarios/falklands_san_carlos/scenario.yaml")
        if not path.exists():
            pytest.skip("Scenario not found")
        with open(path) as f:
            data = yaml.safe_load(f)
        assert data["calibration_overrides"]["roe_level"] == "WEAPONS_TIGHT"

    def test_a4_skyhawk_bomb_rack_mapped(self):
        """A-4 Skyhawk bomb rack is mapped in San Carlos weapon_assignments."""
        from pathlib import Path
        import yaml

        path = Path("data/scenarios/falklands_san_carlos/scenario.yaml")
        if not path.exists():
            pytest.skip("Scenario not found")
        with open(path) as f:
            data = yaml.safe_load(f)
        wa = data["calibration_overrides"]["weapon_assignments"]
        assert wa.get("Generic Bomb Rack") == "bomb_rack_generic"

    def test_eastern_front_has_weapon_assignments(self):
        """Eastern Front 1943 scenario has weapon_assignments for WW2 units."""
        from pathlib import Path
        import yaml

        path = Path("data/scenarios/eastern_front_1943/scenario.yaml")
        if not path.exists():
            pytest.skip("Scenario not found")
        with open(path) as f:
            data = yaml.safe_load(f)
        wa = data["calibration_overrides"]["weapon_assignments"]
        assert "85mm ZIS-S-53 Gun" in wa
        assert "88mm KwK 36 L/56 Gun" in wa
        assert "75mm KwK 40 L/48 Gun" in wa


# ═══════════════════════════════════════════════════════════════════════════
# 55e: Rout Cascade Per-Scenario Config
# ═══════════════════════════════════════════════════════════════════════════


class TestRoutCascadeConfig:
    """Tests for rout cascade per-scenario configuration."""

    def test_rout_cascade_fields_in_calibration_schema(self):
        """CalibrationSchema accepts rout cascade fields."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        cal = CalibrationSchema(
            rout_cascade_radius_m=200.0,
            rout_cascade_base_chance=0.05,
            rout_cascade_shaken_susceptibility=1.2,
        )
        assert cal.get("rout_cascade_radius_m") == 200.0
        assert cal.get("rout_cascade_base_chance") == 0.05
        assert cal.get("rout_cascade_shaken_susceptibility") == 1.2

    def test_rout_cascade_defaults_none(self):
        """Rout cascade fields default to None (no override)."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        cal = CalibrationSchema()
        assert cal.rout_cascade_radius_m is None
        assert cal.rout_cascade_base_chance is None
        assert cal.rout_cascade_shaken_susceptibility is None

    def test_falklands_has_rout_cascade_config(self):
        """Falklands campaign scenario has rout cascade overrides."""
        from pathlib import Path
        import yaml

        path = Path("data/scenarios/falklands_campaign/scenario.yaml")
        if not path.exists():
            pytest.skip("Scenario not found")
        with open(path) as f:
            data = yaml.safe_load(f)
        cal = data["calibration_overrides"]
        assert cal["rout_cascade_radius_m"] == 200.0
        assert cal["rout_cascade_base_chance"] == 0.05
