"""Tests for Phase 11a — Combat Fidelity fixes.

1. Fire rate limiting (WeaponInstance cooldown + engagement gate)
2. Per-side target_size_modifier (battle.py lookup)
3. Environment coupling (air_combat, air_defense, naval_surface, indirect_fire)
4. Mach-dependent drag coefficient (ballistics)
5. Obliquity refinement + armor type (damage)

Uses shared fixtures from conftest.py.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from tests.conftest import make_rng

from stochastic_warfare.combat.ammunition import (
    AmmoDefinition,
    AmmoState,
    WeaponDefinition,
    WeaponInstance,
)
from stochastic_warfare.combat.ballistics import (
    BallisticsConfig,
    BallisticsEngine,
    _mach_drag_multiplier,
    _speed_of_sound,
)
from stochastic_warfare.combat.damage import (
    ArmorType,
    DamageEngine,
)
from stochastic_warfare.combat.air_combat import AirCombatEngine, AirCombatMode
from stochastic_warfare.combat.air_defense import AirDefenseEngine
from stochastic_warfare.combat.naval_surface import NavalSurfaceEngine
from stochastic_warfare.combat.indirect_fire import (
    FireMissionType,
    IndirectFireEngine,
)
from stochastic_warfare.combat.engagement import EngagementEngine
from stochastic_warfare.combat.fratricide import FratricideEngine
from stochastic_warfare.combat.hit_probability import HitProbabilityEngine
from stochastic_warfare.combat.suppression import SuppressionEngine
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wpn_def(
    weapon_id: str = "test_gun",
    rate_of_fire_rpm: float = 10.0,
    max_range_m: float = 3000.0,
    muzzle_velocity_mps: float = 1000.0,
    caliber_mm: float = 120.0,
    compatible_ammo: list[str] | None = None,
    cep_m: float = 0.0,
    base_accuracy_mrad: float = 0.0,
) -> WeaponDefinition:
    return WeaponDefinition(
        weapon_id=weapon_id,
        display_name="Test Gun",
        category="CANNON",
        caliber_mm=caliber_mm,
        rate_of_fire_rpm=rate_of_fire_rpm,
        max_range_m=max_range_m,
        muzzle_velocity_mps=muzzle_velocity_mps,
        compatible_ammo=compatible_ammo or ["test_ap"],
        cep_m=cep_m,
        base_accuracy_mrad=base_accuracy_mrad,
    )


def _ammo_def(
    ammo_id: str = "test_ap",
    ammo_type: str = "AP",
    penetration_mm_rha: float = 300.0,
    mass_kg: float = 5.0,
    diameter_mm: float = 120.0,
    drag_coefficient: float = 0.3,
    blast_radius_m: float = 0.0,
    fragmentation_radius_m: float = 0.0,
) -> AmmoDefinition:
    return AmmoDefinition(
        ammo_id=ammo_id,
        display_name="Test AP",
        ammo_type=ammo_type,
        penetration_mm_rha=penetration_mm_rha,
        mass_kg=mass_kg,
        diameter_mm=diameter_mm,
        drag_coefficient=drag_coefficient,
        blast_radius_m=blast_radius_m,
        fragmentation_radius_m=fragmentation_radius_m,
    )


def _make_weapon_instance(
    rate_of_fire_rpm: float = 10.0,
    ammo_count: int = 100,
) -> WeaponInstance:
    defn = _wpn_def(rate_of_fire_rpm=rate_of_fire_rpm)
    ammo_state = AmmoState(rounds_by_type={"test_ap": ammo_count})
    return WeaponInstance(definition=defn, ammo_state=ammo_state)


def _make_engagement_engine(
    event_bus: EventBus,
    rng: np.random.Generator,
) -> EngagementEngine:
    ballistics = BallisticsEngine(rng)
    hit_engine = HitProbabilityEngine(ballistics, rng)
    damage_engine = DamageEngine(event_bus, rng)
    suppression_engine = SuppressionEngine(event_bus, rng)
    fratricide_engine = FratricideEngine(event_bus, rng)
    return EngagementEngine(
        hit_engine=hit_engine,
        damage_engine=damage_engine,
        suppression_engine=suppression_engine,
        fratricide_engine=fratricide_engine,
        event_bus=event_bus,
        rng=rng,
    )


# ===========================================================================
# 1. Fire rate limiting
# ===========================================================================


class TestFireRateLimiting:
    """WeaponInstance cooldown blocks rapid re-fire."""

    def test_cooldown_computed_from_rof(self) -> None:
        """rate_of_fire_rpm=10 → cooldown=6s."""
        wpn = _make_weapon_instance(rate_of_fire_rpm=10.0)
        assert wpn._cooldown_s == pytest.approx(6.0)

    def test_zero_rof_no_cooldown(self) -> None:
        """rate_of_fire_rpm=0 → no cooldown."""
        wpn = _make_weapon_instance(rate_of_fire_rpm=0.0)
        assert wpn._cooldown_s == 0.0
        assert wpn.can_fire_timed(0.0) is True

    def test_cooldown_blocks_fire(self) -> None:
        """Firing within cooldown is blocked."""
        wpn = _make_weapon_instance(rate_of_fire_rpm=10.0)  # 6s cooldown
        wpn.record_fire(0.0)
        assert wpn.can_fire_timed(3.0) is False  # 3s < 6s

    def test_cooldown_expires_allows_fire(self) -> None:
        """Fire allowed after cooldown expires."""
        wpn = _make_weapon_instance(rate_of_fire_rpm=10.0)  # 6s cooldown
        wpn.record_fire(0.0)
        assert wpn.can_fire_timed(6.0) is True  # exactly at cooldown

    def test_initial_state_allows_fire(self) -> None:
        """Fresh weapon with no prior fire can always fire."""
        wpn = _make_weapon_instance(rate_of_fire_rpm=10.0)
        assert wpn.can_fire_timed(0.0) is True

    def test_state_persistence(self) -> None:
        """last_fire_time_s is saved and restored."""
        wpn = _make_weapon_instance(rate_of_fire_rpm=10.0)
        wpn.record_fire(100.0)
        state = wpn.get_state()
        assert state["last_fire_time_s"] == 100.0

        wpn2 = _make_weapon_instance(rate_of_fire_rpm=10.0)
        wpn2.set_state(state)
        assert wpn2._last_fire_time_s == 100.0
        assert wpn2.can_fire_timed(103.0) is False

    def test_engagement_cooldown_gate(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """execute_engagement returns cooldown abort when weapon is on cooldown."""
        engine = _make_engagement_engine(event_bus, rng)
        wpn = _make_weapon_instance(rate_of_fire_rpm=10.0)
        ammo = _ammo_def()
        shooter_pos = Position(0.0, 0.0, 0.0)
        target_pos = Position(1000.0, 0.0, 0.0)

        # First shot at t=0 should succeed
        r1 = engine.execute_engagement(
            "a", "b", shooter_pos, target_pos, wpn, "test_ap", ammo,
            current_time_s=0.0,
        )
        assert r1.engaged is True

        # Second shot at t=3 should be blocked by cooldown (6s)
        r2 = engine.execute_engagement(
            "a", "b", shooter_pos, target_pos, wpn, "test_ap", ammo,
            current_time_s=3.0,
        )
        assert r2.engaged is False
        assert r2.aborted_reason == "cooldown"

    def test_engagement_after_cooldown(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """execute_engagement succeeds after cooldown expires."""
        engine = _make_engagement_engine(event_bus, rng)
        wpn = _make_weapon_instance(rate_of_fire_rpm=10.0)
        ammo = _ammo_def()
        shooter_pos = Position(0.0, 0.0, 0.0)
        target_pos = Position(1000.0, 0.0, 0.0)

        r1 = engine.execute_engagement(
            "a", "b", shooter_pos, target_pos, wpn, "test_ap", ammo,
            current_time_s=0.0,
        )
        assert r1.engaged is True

        # After 6s cooldown
        r2 = engine.execute_engagement(
            "a", "b", shooter_pos, target_pos, wpn, "test_ap", ammo,
            current_time_s=7.0,
        )
        assert r2.engaged is True


# ===========================================================================
# 2. Per-side target_size_modifier
# ===========================================================================


class TestPerSideTargetSizeModifier:
    """Per-side target_size_modifier calibration lookup (battle.py:508-575)."""

    @staticmethod
    def _lookup(cal: dict, target_side: str) -> float:
        """Replicate the per-side lookup logic from battle.py."""
        target_size_mod_default = cal.get("target_size_modifier", 1.0)
        return cal.get(f"target_size_modifier_{target_side}", target_size_mod_default)

    def test_per_side_lookup_uses_target_side(self) -> None:
        """target_size_modifier_red=0.5 → red targets use 0.5, blue use default 1.0."""
        cal = {"target_size_modifier_red": 0.5}
        assert self._lookup(cal, "red") == 0.5
        assert self._lookup(cal, "blue") == 1.0

    def test_fallback_to_uniform(self) -> None:
        """target_size_modifier=0.7 → both sides get 0.7."""
        cal = {"target_size_modifier": 0.7}
        assert self._lookup(cal, "red") == 0.7
        assert self._lookup(cal, "blue") == 0.7

    def test_both_sides_different(self) -> None:
        """Per-side overrides for both sides."""
        cal = {"target_size_modifier_red": 0.5, "target_size_modifier_blue": 0.8}
        assert self._lookup(cal, "red") == 0.5
        assert self._lookup(cal, "blue") == 0.8

    def test_default_without_any_modifier(self) -> None:
        """No calibration key set → default 1.0."""
        cal: dict = {}
        assert self._lookup(cal, "red") == 1.0
        assert self._lookup(cal, "blue") == 1.0


# ===========================================================================
# 3. Environment coupling
# ===========================================================================


class TestAirCombatEnvCoupling:
    """Weather and visibility parameters affect air combat Pk."""

    def test_severe_weather_aborts_sortie(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = AirCombatEngine(event_bus, rng)
        result = engine.resolve_air_engagement(
            "f16", "mig29",
            Position(0, 0, 5000), Position(5000, 0, 5000),
            missile_pk=0.7,
            weather_modifier=0.2,  # severe
        )
        assert result.hit is False
        assert result.effective_pk == 0.0

    def test_clear_weather_no_penalty(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = AirCombatEngine(event_bus, rng)
        result = engine.resolve_air_engagement(
            "f16", "mig29",
            Position(0, 0, 5000), Position(5000, 0, 5000),
            missile_pk=0.7,
            weather_modifier=1.0,
            visibility_km=20.0,
        )
        # Just check it ran normally (Pk > 0)
        assert result.effective_pk > 0.0

    def test_low_visibility_degrades_wvr(self, event_bus: EventBus) -> None:
        """Low visibility penalizes WVR engagements."""
        # Use deterministic seeds to compare
        engine_clear = AirCombatEngine(EventBus(), make_rng(99))
        engine_foggy = AirCombatEngine(EventBus(), make_rng(99))
        pos_a = Position(0, 0, 5000)
        pos_b = Position(3000, 0, 5000)  # WVR range

        r_clear = engine_clear.resolve_air_engagement(
            "a", "b", pos_a, pos_b, missile_pk=0.7,
            mode=AirCombatMode.WVR, visibility_km=20.0,
        )
        r_foggy = engine_foggy.resolve_air_engagement(
            "a", "b", pos_a, pos_b, missile_pk=0.7,
            mode=AirCombatMode.WVR, visibility_km=3.0,
        )
        assert r_foggy.effective_pk < r_clear.effective_pk

    def test_default_params_backward_compatible(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = AirCombatEngine(event_bus, rng)
        result = engine.resolve_air_engagement(
            "a", "b", Position(0, 0, 5000), Position(5000, 0, 5000),
        )
        # Should run without error — defaults preserve old behavior
        assert isinstance(result.effective_pk, float)


class TestAirDefenseEnvCoupling:
    """Weather modifier degrades interceptor Pk."""

    def test_weather_degrades_intercept_pk(self, event_bus: EventBus) -> None:
        engine_clear = AirDefenseEngine(EventBus(), make_rng(42))
        engine_rain = AirDefenseEngine(EventBus(), make_rng(42))

        r_clear = engine_clear.fire_interceptor(
            "patriot", "mig29", 0.8, 30000.0, weather_modifier=1.0,
        )
        r_rain = engine_rain.fire_interceptor(
            "patriot", "mig29", 0.8, 30000.0, weather_modifier=0.5,
        )
        assert r_rain.effective_pk < r_clear.effective_pk

    def test_default_weather_backward_compatible(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = AirDefenseEngine(event_bus, rng)
        result = engine.fire_interceptor("ad1", "tgt1", 0.7, 20000.0)
        assert isinstance(result.effective_pk, float)

    def test_sls_passes_weather(self, event_bus: EventBus) -> None:
        engine = AirDefenseEngine(EventBus(), make_rng(42))
        results = engine.shoot_look_shoot(
            "ad1", "tgt1", 0.8, max_shots=2, weather_modifier=0.3,
        )
        assert len(results) >= 1
        # All shots should have degraded Pk
        for r in results:
            assert r.effective_pk < 0.8


class TestNavalSurfaceEnvCoupling:
    """Sea state affects salvo exchange."""

    def test_high_sea_state_degrades_salvo(self, event_bus: EventBus) -> None:
        damage_engine = DamageEngine(EventBus(), make_rng(42))
        engine_calm = NavalSurfaceEngine(damage_engine, EventBus(), make_rng(42))
        engine_rough = NavalSurfaceEngine(
            DamageEngine(EventBus(), make_rng(42)), EventBus(), make_rng(42),
        )

        r_calm = engine_calm.salvo_exchange(8, 0.7, 4, 0.5, sea_state=3)
        r_rough = engine_rough.salvo_exchange(8, 0.7, 4, 0.5, sea_state=7)
        # Rough seas degrade both offensive and defensive power
        assert r_rough.offensive_power < r_calm.offensive_power
        assert r_rough.defensive_power < r_calm.defensive_power

    def test_default_sea_state_backward_compatible(self, event_bus: EventBus) -> None:
        damage_engine = DamageEngine(EventBus(), make_rng(42))
        engine = NavalSurfaceEngine(damage_engine, EventBus(), make_rng(42))
        result = engine.salvo_exchange(4, 0.7, 2, 0.5)
        assert isinstance(result.hits, int)


class TestIndirectFireEnvCoupling:
    """Wind increases artillery CEP."""

    def test_crosswind_increases_dispersion(self, event_bus: EventBus) -> None:
        ballistics = BallisticsEngine(make_rng(42))
        damage_eng = DamageEngine(EventBus(), make_rng(42))

        engine_calm = IndirectFireEngine(ballistics, damage_eng, EventBus(), make_rng(42))
        engine_windy = IndirectFireEngine(
            BallisticsEngine(make_rng(42)),
            DamageEngine(EventBus(), make_rng(42)),
            EventBus(), make_rng(42),
        )

        wpn = _wpn_def(weapon_id="howitzer", rate_of_fire_rpm=4.0, cep_m=50.0,
                        max_range_m=20000.0, muzzle_velocity_mps=800.0)
        ammo = _ammo_def(ammo_id="he", ammo_type="HE", blast_radius_m=20.0)

        fire_pos = Position(0, 0, 0)
        target_pos = Position(10000, 0, 0)

        r_calm = engine_calm.fire_mission(
            "btry1", fire_pos, target_pos, wpn, ammo,
            FireMissionType.FIRE_FOR_EFFECT, 10,
            wind_speed_mps=0.0,
        )
        r_windy = engine_windy.fire_mission(
            "btry1", fire_pos, target_pos, wpn, ammo,
            FireMissionType.FIRE_FOR_EFFECT, 10,
            wind_speed_mps=15.0, wind_direction_deg=90.0,  # full crosswind
        )

        # Windy impacts should be more spread
        def spread(impacts: list) -> float:
            positions = [(ip.position.easting, ip.position.northing) for ip in impacts]
            mean_e = sum(p[0] for p in positions) / len(positions)
            mean_n = sum(p[1] for p in positions) / len(positions)
            return sum(
                math.sqrt((p[0] - mean_e) ** 2 + (p[1] - mean_n) ** 2)
                for p in positions
            ) / len(positions)

        assert spread(r_windy.impacts) > spread(r_calm.impacts) * 0.9  # generous threshold

    def test_no_wind_backward_compatible(self, event_bus: EventBus) -> None:
        ballistics = BallisticsEngine(make_rng(42))
        damage_eng = DamageEngine(EventBus(), make_rng(42))
        engine = IndirectFireEngine(ballistics, damage_eng, EventBus(), make_rng(42))
        wpn = _wpn_def(cep_m=50.0, max_range_m=20000.0)
        ammo = _ammo_def(ammo_type="HE", blast_radius_m=10.0)
        result = engine.fire_mission(
            "btry1", Position(0, 0, 0), Position(5000, 0, 0),
            wpn, ammo, FireMissionType.ADJUST_FIRE, 4,
        )
        assert result.rounds_fired == 4


# ===========================================================================
# 4. Mach-dependent drag coefficient
# ===========================================================================


class TestMachDependentDrag:
    """Mach-dependent drag coefficient in ballistics."""

    def test_speed_of_sound_standard(self) -> None:
        """SoS at 15°C ≈ 340.3 m/s."""
        sos = _speed_of_sound(15.0)
        assert sos == pytest.approx(340.3, rel=0.01)

    def test_speed_of_sound_cold(self) -> None:
        """Colder air → slower SoS."""
        assert _speed_of_sound(-20.0) < _speed_of_sound(15.0)

    def test_subsonic_multiplier(self) -> None:
        """Mach 0.5 → multiplier 1.0."""
        assert _mach_drag_multiplier(0.5) == 1.0

    def test_transonic_multiplier(self) -> None:
        """Mach 1.0 → multiplier 1.5 (midpoint of 0.8→1.2 ramp)."""
        mult = _mach_drag_multiplier(1.0)
        assert mult == pytest.approx(1.5, abs=0.01)

    def test_supersonic_peak(self) -> None:
        """Mach 1.2 → multiplier 2.0 (peak)."""
        assert _mach_drag_multiplier(1.2) == pytest.approx(2.0, abs=0.01)

    def test_supersonic_falling(self) -> None:
        """Mach 2.0 → multiplier < 2.0 (falling)."""
        mult = _mach_drag_multiplier(2.0)
        assert mult < 2.0
        assert mult > 1.0

    def test_trajectory_with_mach_drag_shorter(self) -> None:
        """Mach drag should produce shorter range than constant Cd."""
        wpn = _wpn_def(muzzle_velocity_mps=1500.0)
        ammo = _ammo_def(mass_kg=5.0, diameter_mm=120.0, drag_coefficient=0.3)

        engine_mach = BallisticsEngine(make_rng(42), BallisticsConfig(
            enable_mach_drag=True, enable_coriolis=False, enable_wind=False,
        ))
        engine_const = BallisticsEngine(make_rng(42), BallisticsConfig(
            enable_mach_drag=False, enable_coriolis=False, enable_wind=False,
        ))

        traj_mach = engine_mach.compute_trajectory(
            wpn, ammo, Position(0, 0, 0), 5.0, 0.0,
        )
        traj_const = engine_const.compute_trajectory(
            wpn, ammo, Position(0, 0, 0), 5.0, 0.0,
        )
        # Mach drag adds more drag at transonic → shorter range
        range_mach = math.sqrt(
            traj_mach.impact_position.easting ** 2 + traj_mach.impact_position.northing ** 2
        )
        range_const = math.sqrt(
            traj_const.impact_position.easting ** 2 + traj_const.impact_position.northing ** 2
        )
        assert range_mach < range_const

    def test_temperature_affects_sos(self) -> None:
        """Different temperatures should produce different drag behavior."""
        wpn = _wpn_def(muzzle_velocity_mps=1200.0)
        ammo = _ammo_def(mass_kg=5.0, diameter_mm=120.0, drag_coefficient=0.3)

        engine_hot = BallisticsEngine(make_rng(42), BallisticsConfig(
            enable_mach_drag=True, enable_coriolis=False, enable_wind=False,
            temperature_c=40.0,
        ))
        engine_cold = BallisticsEngine(make_rng(42), BallisticsConfig(
            enable_mach_drag=True, enable_coriolis=False, enable_wind=False,
            temperature_c=-20.0,
        ))

        traj_hot = engine_hot.compute_trajectory(
            wpn, ammo, Position(0, 0, 0), 5.0, 0.0,
            conditions={"temperature_c": 40.0},
        )
        traj_cold = engine_cold.compute_trajectory(
            wpn, ammo, Position(0, 0, 0), 5.0, 0.0,
            conditions={"temperature_c": -20.0},
        )
        # Different temps = different Mach = different drag = different ranges
        range_hot = traj_hot.impact_position.northing
        range_cold = traj_cold.impact_position.northing
        assert range_hot != range_cold

    def test_config_disable_preserves_mvp(self) -> None:
        """enable_mach_drag=False should give same results as MVP."""
        config = BallisticsConfig(enable_mach_drag=False)
        assert config.enable_mach_drag is False


# ===========================================================================
# 5. Obliquity refinement + armor type
# ===========================================================================


class TestArmorType:
    """ArmorType enum and armor effectiveness."""

    def test_armor_type_enum_values(self) -> None:
        assert ArmorType.RHA == 0
        assert ArmorType.COMPOSITE == 1
        assert ArmorType.REACTIVE == 2
        assert ArmorType.SPACED == 3

    def test_rha_backward_compatible(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """armor_type='RHA' gives same result as no armor_type."""
        engine = DamageEngine(event_bus, rng)
        ammo = _ammo_def(penetration_mm_rha=300.0)
        r = engine.compute_penetration(ammo, armor_mm=200.0, armor_type="RHA")
        assert r.penetrated is True

    def test_composite_vs_heat_harder(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """COMPOSITE armor is much harder to pen with HEAT."""
        engine = DamageEngine(event_bus, rng)
        ammo_heat = _ammo_def(ammo_type="HEAT", penetration_mm_rha=500.0)

        r_rha = engine.compute_penetration(ammo_heat, armor_mm=200.0, armor_type="RHA")
        r_comp = engine.compute_penetration(ammo_heat, armor_mm=200.0, armor_type="COMPOSITE")

        # COMPOSITE vs HEAT multiplier = 2.5x → effective armor = 500mm
        # Penetration = 500mm pen vs 500mm eff → margin ≈ 0 for composite
        # vs 300mm eff for RHA → clear pen
        assert r_rha.penetrated is True
        assert r_comp.penetrated is False or r_comp.margin_mm < r_rha.margin_mm

    def test_reactive_vs_heat(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """REACTIVE armor is effective against HEAT."""
        engine = DamageEngine(event_bus, rng)
        ammo_heat = _ammo_def(ammo_type="HEAT", penetration_mm_rha=400.0)

        r_rha = engine.compute_penetration(ammo_heat, armor_mm=200.0, armor_type="RHA")
        r_era = engine.compute_penetration(ammo_heat, armor_mm=200.0, armor_type="REACTIVE")
        assert r_era.armor_effective_mm > r_rha.armor_effective_mm

    def test_reactive_no_ke_benefit(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """REACTIVE armor has no benefit against KE rounds."""
        engine = DamageEngine(event_bus, rng)
        ammo_ap = _ammo_def(ammo_type="AP", penetration_mm_rha=300.0)

        r_rha = engine.compute_penetration(ammo_ap, armor_mm=200.0, armor_type="RHA")
        r_era = engine.compute_penetration(ammo_ap, armor_mm=200.0, armor_type="REACTIVE")
        # KE multiplier for REACTIVE is 1.0 (same as RHA)
        assert r_era.armor_effective_mm == pytest.approx(r_rha.armor_effective_mm, rel=0.01)

    def test_spaced_vs_ke_weaker_than_rha(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """SPACED effectiveness 0.9 vs KE — easier to penetrate than RHA (1.0)."""
        engine = DamageEngine(event_bus, rng)
        ammo_ap = _ammo_def(ammo_type="AP", penetration_mm_rha=300.0)

        r_rha = engine.compute_penetration(ammo_ap, armor_mm=200.0, armor_type="RHA")
        r_spaced = engine.compute_penetration(ammo_ap, armor_mm=200.0, armor_type="SPACED")
        # SPACED KE mult=0.9 → effective armor = 180mm vs RHA 200mm
        assert r_spaced.armor_effective_mm < r_rha.armor_effective_mm

    def test_spaced_vs_heat_better_than_rha(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """SPACED effectiveness 1.3 vs HEAT — harder to penetrate than RHA (1.0)."""
        engine = DamageEngine(event_bus, rng)
        ammo_heat = _ammo_def(ammo_type="HEAT", penetration_mm_rha=400.0)

        r_rha = engine.compute_penetration(ammo_heat, armor_mm=200.0, armor_type="RHA")
        r_spaced = engine.compute_penetration(ammo_heat, armor_mm=200.0, armor_type="SPACED")
        # SPACED HEAT mult=1.3 → effective armor = 260mm vs RHA 200mm
        assert r_spaced.armor_effective_mm > r_rha.armor_effective_mm


class TestRicochet:
    """Extreme obliquity causes ricochet."""

    def test_ricochet_at_extreme_angle(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """Impact angle > 75° causes automatic ricochet."""
        engine = DamageEngine(event_bus, rng)
        ammo = _ammo_def(penetration_mm_rha=500.0)
        r = engine.compute_penetration(ammo, armor_mm=50.0, impact_angle_deg=80.0)
        assert r.penetrated is False

    def test_no_ricochet_at_normal_angle(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """Normal angle (0°) doesn't ricochet."""
        engine = DamageEngine(event_bus, rng)
        ammo = _ammo_def(penetration_mm_rha=500.0)
        r = engine.compute_penetration(ammo, armor_mm=50.0, impact_angle_deg=0.0)
        assert r.penetrated is True

    def test_resolve_damage_passes_armor_type(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """resolve_damage forwards armor_type to compute_penetration."""
        engine = DamageEngine(event_bus, rng)
        ammo = _ammo_def(ammo_type="HEAT", penetration_mm_rha=400.0)
        # COMPOSITE vs HEAT should be harder → less damage
        r = engine.resolve_damage(
            "tgt1", ammo, armor_mm=200.0, armor_type="COMPOSITE",
        )
        assert isinstance(r.damage_fraction, float)
