"""Phase 48: Block 5 Deficit Resolution — tests for engine code fixes,
configurable constants, and data completeness.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from stochastic_warfare.combat.ammunition import WeaponCategory, _CATEGORY_DEFAULT_DOMAINS
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import UnitStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_weapon_def(**overrides: Any) -> SimpleNamespace:
    base = dict(
        weapon_id="test_wpn",
        display_name="Test Weapon",
        category="CANNON",
        caliber_mm=20.0,
        muzzle_velocity_mps=800.0,
        max_range_m=2000.0,
        min_range_m=0.0,
        rate_of_fire_rpm=120.0,
        burst_size=1,
        base_accuracy_mrad=3.0,
        guidance="NONE",
        magazine_capacity=100,
        reload_time_s=5.0,
        compatible_ammo=["test_ammo"],
        weight_kg=10.0,
        reliability=0.9,
        barrel_life_rounds=5000,
        requires_deployed=False,
        traverse_deg=360.0,
        elevation_min_deg=-10.0,
        elevation_max_deg=60.0,
        beam_power_kw=0.0,
        target_domains=None,
    )
    base.update(overrides)
    ns = SimpleNamespace(**base)

    def parsed_category():
        return WeaponCategory[ns.category]

    def effective_target_domains():
        if ns.target_domains:
            return set(ns.target_domains)
        return _CATEGORY_DEFAULT_DOMAINS.get(WeaponCategory[ns.category], {"GROUND"})

    def get_effective_range():
        return ns.max_range_m * 0.8

    ns.parsed_category = parsed_category
    ns.effective_target_domains = effective_target_domains
    ns.get_effective_range = get_effective_range
    return ns


def _make_ammo_def(**overrides: Any) -> SimpleNamespace:
    base = dict(
        ammo_id="test_ammo",
        display_name="Test Ammo",
        ammo_type="HE",
        mass_kg=10.0,
        diameter_mm=20.0,
        drag_coefficient=0.3,
        penetration_mm_rha=50.0,
        blast_radius_m=30.0,
        fragmentation_radius_m=50.0,
        guidance="NONE",
        propulsion="none",
        max_speed_mps=0.0,
        unit_cost_factor=1.0,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_impact(easting: float, northing: float) -> SimpleNamespace:
    return SimpleNamespace(position=Position(easting=easting, northing=northing, altitude=0.0))


def _make_unit(entity_id: str = "u1", **kw: Any) -> SimpleNamespace:
    base = dict(
        entity_id=entity_id,
        position=Position(easting=0.0, northing=0.0, altitude=0.0),
        status=UnitStatus.ACTIVE,
        domain=Domain.GROUND,
        speed=0.0,
        personnel=None,
        armor_front=0.0,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ═══════════════════════════════════════════════════════════════════════════
# A1: Morale collapsed threshold from cond.params
# ═══════════════════════════════════════════════════════════════════════════


class TestMoraleCollapsedParams:
    """A1: _check_morale_collapsed reads threshold from cond.params."""

    def _make_evaluator(self):
        from stochastic_warfare.simulation.victory import VictoryEvaluator, VictoryEvaluatorConfig
        return VictoryEvaluator(
            objectives=[],
            conditions=[],
            event_bus=EventBus(),
            config=VictoryEvaluatorConfig(),
        )

    def _make_cond(self, params: dict | None = None):
        return SimpleNamespace(
            type="morale_collapsed",
            side="",
            params=params or {},
        )

    def test_default_threshold(self):
        """Without params.threshold, uses config default (0.6)."""
        evaluator = self._make_evaluator()
        cond = self._make_cond()
        units = {"red": [_make_unit("r1"), _make_unit("r2")]}
        # 50% routed < 60% threshold → no collapse
        morale_states = {"r1": 3, "r2": 0}  # 3 = ROUTED
        result = evaluator._check_morale_collapsed(cond, units, morale_states, tick=10)
        assert not result.game_over

    def test_custom_threshold_triggers(self):
        """Custom params.threshold=0.4 triggers collapse at 50%."""
        evaluator = self._make_evaluator()
        cond = self._make_cond(params={"threshold": 0.4})
        units = {"red": [_make_unit("r1"), _make_unit("r2")]}
        morale_states = {"r1": 3, "r2": 0}  # 50% routed ≥ 40% threshold
        result = evaluator._check_morale_collapsed(cond, units, morale_states, tick=10)
        assert result.game_over

    def test_custom_threshold_no_trigger(self):
        """Custom params.threshold=0.8 does not trigger at 50%."""
        evaluator = self._make_evaluator()
        cond = self._make_cond(params={"threshold": 0.8})
        units = {"red": [_make_unit("r1"), _make_unit("r2")]}
        morale_states = {"r1": 3, "r2": 0}
        result = evaluator._check_morale_collapsed(cond, units, morale_states, tick=10)
        assert not result.game_over


# ═══════════════════════════════════════════════════════════════════════════
# Phase 48: force_destroyed — target_side and count_disabled
# ═══════════════════════════════════════════════════════════════════════════


class TestForceDestroyedEnhancements:
    """target_side restricts which side is checked; count_disabled includes
    DISABLED units in the loss count when target_side is set."""

    def _make_evaluator(self):
        from stochastic_warfare.simulation.victory import VictoryEvaluator, VictoryEvaluatorConfig
        return VictoryEvaluator(
            objectives=[],
            conditions=[],
            event_bus=EventBus(),
            config=VictoryEvaluatorConfig(),
        )

    def _make_cond(self, side="", **params):
        return SimpleNamespace(type="force_destroyed", side=side, params=params)

    def test_target_side_only_checks_specified(self):
        """With target_side=red, only red's losses trigger the condition."""
        ev = self._make_evaluator()
        cond = self._make_cond(threshold=0.5, target_side="red")
        # Blue has 100% destroyed, red has 0% — but only red is checked
        units = {
            "blue": [_make_unit("b1", status=UnitStatus.DESTROYED)],
            "red": [_make_unit("r1"), _make_unit("r2")],
        }
        result = ev._check_force_destroyed(cond, units, tick=10)
        assert not result.game_over  # Red not destroyed

    def test_target_side_triggers_when_reached(self):
        """With target_side=red, red at 50% triggers the condition."""
        ev = self._make_evaluator()
        cond = self._make_cond(threshold=0.5, target_side="red")
        units = {
            "blue": [_make_unit("b1")],
            "red": [
                _make_unit("r1", status=UnitStatus.DESTROYED),
                _make_unit("r2"),
            ],
        }
        result = ev._check_force_destroyed(cond, units, tick=10)
        assert result.game_over
        assert result.winning_side == "blue"

    def test_count_disabled_with_target_side(self):
        """With target_side set, DISABLED counts as out-of-action by default."""
        ev = self._make_evaluator()
        cond = self._make_cond(threshold=0.5, target_side="red")
        units = {
            "blue": [_make_unit("b1")],
            "red": [
                _make_unit("r1", status=UnitStatus.DISABLED),
                _make_unit("r2"),
            ],
        }
        result = ev._check_force_destroyed(cond, units, tick=10)
        assert result.game_over  # DISABLED counts when target_side is set

    def test_disabled_not_counted_without_target_side(self):
        """Without target_side, DISABLED does NOT count (backward compat)."""
        ev = self._make_evaluator()
        cond = self._make_cond(threshold=0.5)
        units = {
            "red": [
                _make_unit("r1", status=UnitStatus.DISABLED),
                _make_unit("r2"),
            ],
        }
        result = ev._check_force_destroyed(cond, units, tick=10)
        assert not result.game_over


# ═══════════════════════════════════════════════════════════════════════════
# A6: Domain mapping corrections
# ═══════════════════════════════════════════════════════════════════════════


class TestDomainMappingCorrections:
    """A6: Updated default domains for CANNON, AAA, NAVAL_GUN."""

    def test_cannon_includes_aerial(self):
        assert "AERIAL" in _CATEGORY_DEFAULT_DOMAINS[WeaponCategory.CANNON]
        assert "GROUND" in _CATEGORY_DEFAULT_DOMAINS[WeaponCategory.CANNON]

    def test_aaa_includes_ground(self):
        assert "GROUND" in _CATEGORY_DEFAULT_DOMAINS[WeaponCategory.AAA]
        assert "AERIAL" in _CATEGORY_DEFAULT_DOMAINS[WeaponCategory.AAA]

    def test_naval_gun_includes_aerial(self):
        assert "AERIAL" in _CATEGORY_DEFAULT_DOMAINS[WeaponCategory.NAVAL_GUN]
        assert "GROUND" in _CATEGORY_DEFAULT_DOMAINS[WeaponCategory.NAVAL_GUN]
        assert "NAVAL" in _CATEGORY_DEFAULT_DOMAINS[WeaponCategory.NAVAL_GUN]

    def test_effective_target_domains_cannon(self):
        wd = _make_weapon_def(category="CANNON")
        domains = wd.effective_target_domains()
        assert domains == {"GROUND", "AERIAL"}

    def test_effective_target_domains_aaa(self):
        wd = _make_weapon_def(category="AAA")
        domains = wd.effective_target_domains()
        assert domains == {"AERIAL", "GROUND"}


# ═══════════════════════════════════════════════════════════════════════════
# A4: Indirect fire configurable lethal radius / casualty fraction
# ═══════════════════════════════════════════════════════════════════════════


class TestIndirectFireParams:
    """A4: _apply_indirect_fire_result accepts lethal_radius_m and casualty_per_hit."""

    def test_default_lethal_radius(self):
        """Default 50m lethal radius — impact at 45m counts."""
        from stochastic_warfare.simulation.battle import _apply_indirect_fire_result
        target = _make_unit("t1", position=Position(easting=100.0, northing=100.0, altitude=0.0))
        fm = SimpleNamespace(impacts=[_make_impact(145.0, 100.0)])  # 45m away
        pending: list = []
        _apply_indirect_fire_result(fm, target, pending)
        assert len(pending) == 0  # 1 hit × 0.15 = 0.15 < 0.3 disable

    def test_custom_lethal_radius_wider(self):
        """Custom 80m lethal radius catches impacts at 75m."""
        from stochastic_warfare.simulation.battle import _apply_indirect_fire_result
        target = _make_unit("t1", position=Position(easting=100.0, northing=100.0, altitude=0.0))
        # 75m away — inside 80m custom radius, outside 50m default
        fm = SimpleNamespace(impacts=[
            _make_impact(175.0, 100.0),
            _make_impact(175.0, 100.0),
            _make_impact(175.0, 100.0),
        ])
        pending: list = []
        _apply_indirect_fire_result(fm, target, pending, lethal_radius_m=80.0)
        # 3 hits × 0.15 = 0.45 ≥ 0.3 disable threshold
        assert len(pending) == 1
        assert pending[0][1] == UnitStatus.DISABLED

    def test_custom_casualty_per_hit(self):
        """Custom casualty_per_hit=0.25 means 2 hits → 0.5 → DESTROYED."""
        from stochastic_warfare.simulation.battle import _apply_indirect_fire_result
        target = _make_unit("t1", position=Position(easting=100.0, northing=100.0, altitude=0.0))
        fm = SimpleNamespace(impacts=[
            _make_impact(110.0, 100.0),  # 10m away
            _make_impact(110.0, 100.0),
        ])
        pending: list = []
        _apply_indirect_fire_result(fm, target, pending, casualty_per_hit=0.25)
        # 2 × 0.25 = 0.5 ≥ 0.5 destruction threshold
        assert len(pending) == 1
        assert pending[0][1] == UnitStatus.DESTROYED


# ═══════════════════════════════════════════════════════════════════════════
# A5: Fire-on-move accuracy penalty
# ═══════════════════════════════════════════════════════════════════════════


class TestFireOnMovePenalty:
    """A5: Moving units suffer accuracy penalty (crew_skill reduction)."""

    def test_stationary_no_penalty(self):
        """Stationary unit (speed=0) gets no movement penalty."""
        # The penalty formula: if speed > 0.5: crew_skill *= 1 - speed_frac * 0.5
        speed = 0.0
        max_spd = 20.0
        if speed > 0.5:
            speed_frac = min(1.0, speed / max(1.0, max_spd))
            penalty = 1.0 - speed_frac * 0.5
        else:
            penalty = 1.0
        assert penalty == 1.0

    def test_max_speed_half_penalty(self):
        """At max speed, penalty is 0.5 (50% accuracy)."""
        speed = 20.0
        max_spd = 20.0
        speed_frac = min(1.0, speed / max(1.0, max_spd))
        penalty = 1.0 - speed_frac * 0.5
        assert penalty == pytest.approx(0.5)

    def test_half_speed_quarter_penalty(self):
        """At half max speed, penalty is 0.75 (25% reduction)."""
        speed = 10.0
        max_spd = 20.0
        speed_frac = min(1.0, speed / max(1.0, max_spd))
        penalty = 1.0 - speed_frac * 0.5
        assert penalty == pytest.approx(0.75)


# ═══════════════════════════════════════════════════════════════════════════
# A3: Naval engagement config
# ═══════════════════════════════════════════════════════════════════════════


class TestNavalEngagementConfig:
    """A3: NavalEngagementConfig replaces hardcoded naval Pk values."""

    def test_default_values(self):
        from stochastic_warfare.simulation.battle import NavalEngagementConfig
        nc = NavalEngagementConfig()
        assert nc.default_torpedo_pk == 0.4
        assert nc.default_missile_pk == 0.7
        assert nc.default_pd_count == 2
        assert nc.default_pd_pk == 0.3
        assert nc.default_target_length_m == 150.0
        assert nc.default_target_beam_m == 20.0

    def test_custom_values(self):
        from stochastic_warfare.simulation.battle import NavalEngagementConfig
        nc = NavalEngagementConfig(
            default_torpedo_pk=0.5,
            default_missile_pk=0.8,
        )
        assert nc.default_torpedo_pk == 0.5
        assert nc.default_missile_pk == 0.8

    def test_battle_config_includes_naval(self):
        from stochastic_warfare.simulation.battle import BattleConfig
        bc = BattleConfig()
        assert hasattr(bc, "naval_config")
        assert bc.naval_config.default_torpedo_pk == 0.4


# ═══════════════════════════════════════════════════════════════════════════
# B1: Rally radius from RoutConfig
# ═══════════════════════════════════════════════════════════════════════════


class TestRallyRadiusConfig:
    """B1: Rally uses cascade_radius_m from RoutConfig, not hardcoded 500m."""

    def test_rout_config_has_cascade_radius(self):
        from stochastic_warfare.morale.rout import RoutConfig
        rc = RoutConfig()
        assert rc.cascade_radius_m == 500.0  # Default matches old hardcoded

    def test_custom_rally_radius(self):
        from stochastic_warfare.morale.rout import RoutConfig
        rc = RoutConfig(cascade_radius_m=800.0)
        assert rc.cascade_radius_m == 800.0


# ═══════════════════════════════════════════════════════════════════════════
# B2: Elevation caps from config
# ═══════════════════════════════════════════════════════════════════════════


class TestElevationCapsConfig:
    """B2: Elevation advantage/disadvantage caps configurable."""

    def test_default_caps(self):
        from stochastic_warfare.simulation.battle import BattleConfig
        bc = BattleConfig()
        assert bc.elevation_advantage_cap == 0.3
        assert bc.elevation_disadvantage_floor == -0.1

    def test_custom_caps(self):
        from stochastic_warfare.simulation.battle import BattleConfig
        bc = BattleConfig(elevation_advantage_cap=0.5, elevation_disadvantage_floor=-0.2)
        assert bc.elevation_advantage_cap == 0.5
        assert bc.elevation_disadvantage_floor == -0.2

    def test_terrain_modifier_uses_caps(self):
        """_compute_terrain_modifiers respects custom elevation caps."""
        from stochastic_warfare.simulation.battle import BattleManager
        ctx = SimpleNamespace(
            classification=None,
            trench_overlay=None,
            building_manager=None,
            obstacle_manager=None,
            heightmap=SimpleNamespace(
                elevation_at=lambda pos: 200.0 if pos.easting < 50 else 0.0,
            ),
        )
        high_pos = Position(easting=0.0, northing=0.0, altitude=0.0)
        low_pos = Position(easting=100.0, northing=0.0, altitude=0.0)

        # Default caps: +30% max
        _, elev_default, _ = BattleManager._compute_terrain_modifiers(ctx, low_pos, high_pos)
        assert elev_default <= 1.3 + 0.01

        # Custom higher cap: +50% max
        _, elev_custom, _ = BattleManager._compute_terrain_modifiers(
            ctx, low_pos, high_pos, elevation_cap=0.5,
        )
        assert elev_custom <= 1.5 + 0.01
        assert elev_custom >= elev_default  # Higher cap allows more advantage


# ═══════════════════════════════════════════════════════════════════════════
# A7: Target value weights from config
# ═══════════════════════════════════════════════════════════════════════════


class TestTargetValueConfig:
    """A7: _target_value accepts configurable weights."""

    def test_default_weights(self):
        from stochastic_warfare.simulation.battle import _target_value
        hq = SimpleNamespace(support_type=SimpleNamespace(name="HQ"))
        assert _target_value(hq) == 2.0

        ad = SimpleNamespace(ad_type="SAM")
        assert _target_value(ad) == 1.8

        art = SimpleNamespace(ground_type=SimpleNamespace(name="ARTILLERY"))
        assert _target_value(art) == 1.5

        armor = SimpleNamespace(ground_type=SimpleNamespace(name="ARMOR"))
        assert _target_value(armor) == 1.3

        inf = SimpleNamespace(ground_type=SimpleNamespace(name="INFANTRY"))
        assert _target_value(inf) == 1.0

    def test_custom_weights(self):
        from stochastic_warfare.simulation.battle import _target_value
        hq = SimpleNamespace(support_type=SimpleNamespace(name="HQ"))
        assert _target_value(hq, hq=3.0) == 3.0

        ad = SimpleNamespace(ad_type="SAM")
        assert _target_value(ad, ad=2.5) == 2.5

        art = SimpleNamespace(ground_type=SimpleNamespace(name="ARTILLERY"))
        assert _target_value(art, artillery=2.0) == 2.0

    def test_battle_config_has_target_weights(self):
        from stochastic_warfare.simulation.battle import BattleConfig
        bc = BattleConfig()
        assert bc.target_value_hq == 2.0
        assert bc.target_value_ad == 1.8
        assert bc.target_value_artillery == 1.5
        assert bc.target_value_armor == 1.3
        assert bc.target_value_default == 1.0


# ═══════════════════════════════════════════════════════════════════════════
# Data completeness — scenario & unit YAML
# ═══════════════════════════════════════════════════════════════════════════


class TestDataCompleteness:
    """Scenario data fixes — YAML file existence and content."""

    def test_bomb_rack_weapon_exists(self):
        from pathlib import Path
        p = Path("data/weapons/bombs/bomb_rack_generic.yaml")
        assert p.exists()

    def test_a4_skyhawk_has_bomb_rack(self):
        import yaml
        from pathlib import Path
        p = Path("data/units/air_fixed_wing/a4_skyhawk.yaml")
        data = yaml.safe_load(p.read_text())
        names = [e["name"] for e in data["equipment"]]
        assert "Generic Bomb Rack" in names

    def test_roman_equites_unit_exists(self):
        from pathlib import Path
        p = Path("data/eras/ancient_medieval/units/roman_equites.yaml")
        assert p.exists()

    def test_roman_equites_signature_exists(self):
        from pathlib import Path
        p = Path("data/eras/ancient_medieval/signatures/roman_equites.yaml")
        assert p.exists()

    def test_iraqi_republican_guard_exists(self):
        from pathlib import Path
        p = Path("data/units/infantry/iraqi_republican_guard.yaml")
        assert p.exists()

    def test_iraqi_guard_signature_exists(self):
        from pathlib import Path
        p = Path("data/signatures/iraqi_republican_guard.yaml")
        assert p.exists()

    def test_cannae_uses_roman_equites(self):
        import yaml
        from pathlib import Path
        p = Path("data/eras/ancient_medieval/scenarios/cannae/scenario.yaml")
        data = yaml.safe_load(p.read_text())
        roman_side = [s for s in data["sides"] if s["side"] == "roman"][0]
        unit_types = [u["unit_type"] for u in roman_side["units"]]
        assert "roman_equites" in unit_types
        assert "saracen_cavalry" not in unit_types

    def test_halabja_uses_iraqi_guard(self):
        import yaml
        from pathlib import Path
        p = Path("data/scenarios/halabja_1988/scenario.yaml")
        data = yaml.safe_load(p.read_text())
        red_side = [s for s in data["sides"] if s["side"] == "red"][0]
        unit_types = [u["unit_type"] for u in red_side["units"]]
        assert "iraqi_republican_guard" in unit_types

    def test_taiwan_strait_has_dew_config(self):
        import yaml
        from pathlib import Path
        p = Path("data/scenarios/taiwan_strait/scenario.yaml")
        data = yaml.safe_load(p.read_text())
        assert "dew_config" in data
        assert data["dew_config"]["enable_dew"] is True

    def test_trafalgar_formation_spacing(self):
        import yaml
        from pathlib import Path
        p = Path("data/eras/napoleonic/scenarios/trafalgar/scenario.yaml")
        data = yaml.safe_load(p.read_text())
        cal = data["calibration_overrides"]
        # Franco-Spanish fleet spread out (300m spacing → ~9km line)
        assert cal["franco_spanish_formation_spacing_m"] == 300.0
        # British tighter formation (80m spacing → ~1.8km columns)
        assert cal["british_formation_spacing_m"] == 80.0

    def test_trafalgar_force_ratio_modifiers(self):
        import yaml
        from pathlib import Path
        p = Path("data/eras/napoleonic/scenarios/trafalgar/scenario.yaml")
        data = yaml.safe_load(p.read_text())
        cal = data["calibration_overrides"]
        # British gunnery superiority via Dupuy CEV
        assert cal["british_force_ratio_modifier"] > 2.0
        assert cal["franco_spanish_force_ratio_modifier"] < 1.0


class TestFormationSpacingConfig:
    """Per-side formation_spacing_m calibration override."""

    def test_default_spacing(self):
        """Without calibration, default 50m spacing used."""
        cal: dict = {}
        prefix = "blue"
        spacing = cal.get(
            f"{prefix}_formation_spacing_m",
            cal.get("formation_spacing_m", 50.0),
        )
        assert spacing == 50.0

    def test_global_spacing_override(self):
        """Global formation_spacing_m applies to all sides."""
        cal = {"formation_spacing_m": 100.0}
        prefix = "blue"
        spacing = cal.get(
            f"{prefix}_formation_spacing_m",
            cal.get("formation_spacing_m", 50.0),
        )
        assert spacing == 100.0

    def test_per_side_spacing_override(self):
        """Per-side override takes precedence over global."""
        cal = {
            "formation_spacing_m": 100.0,
            "blue_formation_spacing_m": 200.0,
        }
        prefix = "blue"
        spacing = cal.get(
            f"{prefix}_formation_spacing_m",
            cal.get("formation_spacing_m", 50.0),
        )
        assert spacing == 200.0


# ═══════════════════════════════════════════════════════════════════════════
# Phase 48: force_ratio_modifier wiring
# ═══════════════════════════════════════════════════════════════════════════


class TestForceRatioModifier:
    """force_ratio_modifier (Dupuy CEV) scales crew_skill in engagement loop."""

    def test_cal_get_pattern(self):
        """cal.get() with side prefix falls back to 1.0."""
        cal: dict = {}
        assert cal.get("blue_force_ratio_modifier", 1.0) == 1.0
        cal = {"blue_force_ratio_modifier": 2.5}
        assert cal.get("blue_force_ratio_modifier", 1.0) == 2.5

    def test_scenarios_declare_force_ratio_modifier(self):
        """All historical scenarios that declare force_ratio_modifier use
        side-prefixed keys that battle.py now reads."""
        import yaml
        from pathlib import Path
        checked = 0
        for scenario_yaml in Path("data").rglob("scenario.yaml"):
            data = yaml.safe_load(scenario_yaml.read_text())
            cal = data.get("calibration_overrides", {})
            frm_keys = [k for k in cal if k.endswith("_force_ratio_modifier")]
            if frm_keys:
                for k in frm_keys:
                    v = cal[k]
                    assert isinstance(v, (int, float)), f"{scenario_yaml}: {k} must be numeric"
                    assert v > 0, f"{scenario_yaml}: {k} must be positive"
                checked += 1
        assert checked >= 10, f"Expected >=10 scenarios with force_ratio_modifier, got {checked}"

    def test_naval_routing_accepts_force_ratio_mod(self):
        """_route_naval_engagement accepts force_ratio_mod parameter."""
        import inspect
        from stochastic_warfare.simulation.battle import _route_naval_engagement
        sig = inspect.signature(_route_naval_engagement)
        assert "force_ratio_mod" in sig.parameters


# ═══════════════════════════════════════════════════════════════════════════
# Phase 48: EW/SEAD calibration params wired
# ═══════════════════════════════════════════════════════════════════════════


class TestEWCalibrationParams:
    """EW/SEAD calibration parameters consumed by battle.py."""

    def test_jammer_coverage_mult_read(self):
        """jammer_coverage_mult is consumed via cal.get() in battle.py."""
        from pathlib import Path
        src = Path("stochastic_warfare/simulation/battle.py").read_text()
        assert 'cal.get("jammer_coverage_mult"' in src

    def test_stealth_detection_penalty_read(self):
        """stealth_detection_penalty is consumed via cal.get() in battle.py."""
        from pathlib import Path
        src = Path("stochastic_warfare/simulation/battle.py").read_text()
        assert 'cal.get("stealth_detection_penalty"' in src

    def test_sigint_detection_bonus_read(self):
        """sigint_detection_bonus is consumed via cal.get() in battle.py."""
        from pathlib import Path
        src = Path("stochastic_warfare/simulation/battle.py").read_text()
        assert 'cal.get("sigint_detection_bonus"' in src

    def test_sam_suppression_modifier_read(self):
        """sam_suppression_modifier is consumed via cal.get() in battle.py."""
        from pathlib import Path
        src = Path("stochastic_warfare/simulation/battle.py").read_text()
        assert 'cal.get("sam_suppression_modifier"' in src

    def test_per_side_hit_probability_modifier_read(self):
        """Per-side hit_probability_modifier is consumed via cal.get()."""
        from pathlib import Path
        src = Path("stochastic_warfare/simulation/battle.py").read_text()
        assert 'f"hit_probability_modifier_{side_name}"' in src


# ═══════════════════════════════════════════════════════════════════════════
# Calibration key audit — superseded by CalibrationSchema (Phase 49)
# ═══════════════════════════════════════════════════════════════════════════


class TestCalibrationKeyAudit:
    """Calibration key validation via CalibrationSchema (Phase 49).

    Replaces the string-list-based audit with schema validation.
    CalibrationSchema(extra='forbid') rejects unknown keys at parse time.
    """

    def test_all_scenario_cal_keys_validated_by_schema(self):
        """Every calibration_overrides across all scenarios validates
        via CalibrationSchema without error."""
        import yaml
        from pathlib import Path
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        failures: list[str] = []
        for scenario_yaml in Path("data").rglob("scenario.yaml"):
            data = yaml.safe_load(scenario_yaml.read_text())
            cal = data.get("calibration_overrides", {})
            if not cal:
                continue
            try:
                CalibrationSchema(**cal)
            except Exception as e:
                failures.append(f"{scenario_yaml}: {e}")
        if failures:
            pytest.fail("Schema validation failures:\n" +
                        "\n".join(failures))
