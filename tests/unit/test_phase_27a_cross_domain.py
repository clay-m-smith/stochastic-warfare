"""Phase 27a: Cross-domain engagement paths — router, ASHM, ATGM, EW integration."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tests.conftest import make_rng
from stochastic_warfare.core.types import Position


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engagement_engine(rng=None, config=None):
    from stochastic_warfare.combat.ballistics import BallisticsEngine
    from stochastic_warfare.combat.damage import DamageEngine
    from stochastic_warfare.combat.engagement import EngagementConfig, EngagementEngine
    from stochastic_warfare.combat.fratricide import FratricideEngine
    from stochastic_warfare.combat.hit_probability import HitProbabilityEngine
    from stochastic_warfare.combat.suppression import SuppressionEngine
    from stochastic_warfare.core.events import EventBus

    rng = rng or make_rng()
    bus = EventBus()
    cfg = config or EngagementConfig()
    bal_eng = BallisticsEngine(rng=rng)
    hit_eng = HitProbabilityEngine(ballistics=bal_eng, rng=rng)
    dmg_eng = DamageEngine(event_bus=bus, rng=rng)
    sup_eng = SuppressionEngine(event_bus=bus, rng=rng)
    frat_eng = FratricideEngine(event_bus=bus, rng=rng)
    return EngagementEngine(
        hit_engine=hit_eng, damage_engine=dmg_eng,
        suppression_engine=sup_eng, fratricide_engine=frat_eng,
        event_bus=bus, rng=rng, config=cfg,
    )


def _make_weapon_instance():
    from stochastic_warfare.combat.ammunition import WeaponDefinition, WeaponInstance

    defn = WeaponDefinition(
        weapon_id="atgm_01", display_name="ATGM",
        category="MISSILE_LAUNCHER", caliber_mm=152,
        max_range_m=5000.0, min_range_m=100.0,
        rate_of_fire_rpm=6, burst_size=1,
        magazine_capacity=4, compatible_ammo=["atgm_round"],
        guidance="WIRE",
    )
    wi = WeaponInstance(definition=defn)
    wi.ammo_state.add("atgm_round", 4)
    return wi


def _make_ammo_def():
    from stochastic_warfare.combat.ammunition import AmmoDefinition

    return AmmoDefinition(
        ammo_id="atgm_round", display_name="ATGM Round",
        ammo_type="HEAT", caliber_mm=152,
        penetration_mm_rha=700.0,
        pk_at_reference=0.6,
        guidance="WIRE",
    )


# ---------------------------------------------------------------------------
# 1. Router dispatch tests
# ---------------------------------------------------------------------------


class TestEngagementRouter:
    def test_direct_fire_dispatches(self) -> None:
        from stochastic_warfare.combat.engagement import EngagementType

        eng = _make_engagement_engine()
        wi = _make_weapon_instance()
        ammo = _make_ammo_def()
        result = eng.route_engagement(
            EngagementType.DIRECT_FIRE,
            "att1", "tgt1",
            Position(0, 0, 0), Position(1000, 0, 0),
            wi, "atgm_round", ammo,
        )
        assert result.engaged or result.aborted_reason != ""

    def test_unknown_type_not_engaged(self) -> None:
        from stochastic_warfare.combat.engagement import EngagementType

        eng = _make_engagement_engine()
        wi = _make_weapon_instance()
        ammo = _make_ammo_def()
        # Use an invalid int cast
        result = eng.route_engagement(
            EngagementType(8),  # MINE — no handler dispatched through router
            "att1", "tgt1",
            Position(0, 0, 0), Position(1000, 0, 0),
            wi, "atgm_round", ammo,
        )
        assert result.aborted_reason == "unknown_engagement_type"
        assert result.engaged is False

    def test_coastal_defense_no_missile_engine(self) -> None:
        from stochastic_warfare.combat.engagement import EngagementType

        eng = _make_engagement_engine()
        wi = _make_weapon_instance()
        ammo = _make_ammo_def()
        result = eng.route_engagement(
            EngagementType.COASTAL_DEFENSE,
            "att1", "tgt1",
            Position(0, 0, 0), Position(1000, 0, 0),
            wi, "atgm_round", ammo,
        )
        assert result.engaged is False
        assert result.aborted_reason == "no_missile_engine"

    def test_coastal_defense_with_missile_engine(self) -> None:
        from stochastic_warfare.combat.engagement import EngagementType

        eng = _make_engagement_engine()
        wi = _make_weapon_instance()
        ammo = _make_ammo_def()
        mock_missile = MagicMock()
        result = eng.route_engagement(
            EngagementType.COASTAL_DEFENSE,
            "att1", "tgt1",
            Position(0, 0, 0), Position(50000, 0, 0),
            wi, "atgm_round", ammo,
            missile_engine=mock_missile,
        )
        assert result.engaged is True
        mock_missile.launch_missile.assert_called_once()

    def test_ashm_dispatches(self) -> None:
        from stochastic_warfare.combat.engagement import EngagementType

        eng = _make_engagement_engine()
        wi = _make_weapon_instance()
        ammo = _make_ammo_def()
        mock_missile = MagicMock()
        result = eng.route_engagement(
            EngagementType.AIR_LAUNCHED_ASHM,
            "att1", "tgt1",
            Position(0, 0, 5000), Position(50000, 0, 0),
            wi, "atgm_round", ammo,
            missile_engine=mock_missile,
        )
        assert result.engaged is True

    def test_atgm_vs_rotary_dispatches(self) -> None:
        from stochastic_warfare.combat.engagement import EngagementType

        eng = _make_engagement_engine()
        wi = _make_weapon_instance()
        ammo = _make_ammo_def()
        result = eng.route_engagement(
            EngagementType.ATGM_VS_ROTARY,
            "att1", "helo1",
            Position(0, 0, 0), Position(2000, 0, 200),
            wi, "atgm_round", ammo,
            target_altitude_m=200.0,
        )
        assert result.engaged is True

    def test_new_enum_values_exist(self) -> None:
        from stochastic_warfare.combat.engagement import EngagementType

        assert EngagementType.COASTAL_DEFENSE == 9
        assert EngagementType.AIR_LAUNCHED_ASHM == 10
        assert EngagementType.ATGM_VS_ROTARY == 11


# ---------------------------------------------------------------------------
# 2. ATGM vs rotary
# ---------------------------------------------------------------------------


class TestATGMVsRotary:
    def test_altitude_check(self) -> None:
        from stochastic_warfare.combat.engagement import EngagementConfig, EngagementType

        cfg = EngagementConfig(atgm_max_altitude_m=300.0)
        eng = _make_engagement_engine(config=cfg)
        wi = _make_weapon_instance()
        ammo = _make_ammo_def()
        result = eng.route_engagement(
            EngagementType.ATGM_VS_ROTARY,
            "att1", "helo1",
            Position(0, 0, 0), Position(2000, 0, 400),
            wi, "atgm_round", ammo,
            target_altitude_m=400.0,
        )
        assert result.aborted_reason == "target_too_high"
        assert result.engaged is False

    def test_range_decay(self) -> None:
        eng = _make_engagement_engine()
        wi = _make_weapon_instance()
        ammo = _make_ammo_def()
        # At max range, effective Pk should be reduced
        result = eng._resolve_atgm_vs_rotary(
            "att1", "helo1",
            Position(0, 0, 0), Position(4500, 0, 100),
            wi, "atgm_round", ammo,
            target_altitude_m=100.0,
        )
        assert result.engaged is True
        assert result.hit_result is not None
        # At 4500m range with decay factor 0.0001, range_factor = 1 - 0.0001*4500 = 0.55
        assert result.hit_result.p_hit < ammo.pk_at_reference

    def test_wire_guided_bonus_hovering(self) -> None:
        """Wire-guided ATGM gets bonus against stationary target."""
        eng = _make_engagement_engine()
        wi = _make_weapon_instance()
        ammo = _make_ammo_def()
        result = eng._resolve_atgm_vs_rotary(
            "att1", "helo1",
            Position(0, 0, 0), Position(1000, 0, 50),
            wi, "atgm_round", ammo,
            target_altitude_m=50.0,
            target_speed_mps=0.0,
        )
        assert result.engaged is True
        # Wire guidance bonus only when target_speed < 5 and guidance=WIRE
        assert result.hit_result.p_hit > 0

    def test_out_of_range(self) -> None:
        from stochastic_warfare.combat.engagement import EngagementType

        eng = _make_engagement_engine()
        wi = _make_weapon_instance()
        ammo = _make_ammo_def()
        result = eng.route_engagement(
            EngagementType.ATGM_VS_ROTARY,
            "att1", "helo1",
            Position(0, 0, 0), Position(10000, 0, 100),
            wi, "atgm_round", ammo,
            target_altitude_m=100.0,
        )
        assert result.aborted_reason == "out_of_range"

    def test_engagement_result_fields(self) -> None:
        from stochastic_warfare.combat.engagement import EngagementType

        eng = _make_engagement_engine()
        wi = _make_weapon_instance()
        ammo = _make_ammo_def()
        result = eng.route_engagement(
            EngagementType.ATGM_VS_ROTARY,
            "att1", "helo1",
            Position(0, 0, 0), Position(2000, 0, 100),
            wi, "atgm_round", ammo,
            target_altitude_m=100.0,
        )
        assert result.engagement_type == EngagementType.ATGM_VS_ROTARY
        assert result.range_m > 0


# ---------------------------------------------------------------------------
# 3. Air-launched ASHM
# ---------------------------------------------------------------------------


class TestAirLaunchedASHM:
    def _make_engine(self):
        from stochastic_warfare.combat.air_ground import AirGroundEngine
        from stochastic_warfare.core.events import EventBus

        return AirGroundEngine(EventBus(), make_rng())

    def test_valid_launch(self) -> None:
        eng = self._make_engine()
        result = eng.execute_ashm(
            "f18_01", "destroyer_01",
            Position(0, 0, 5000), Position(100000, 0, 0),
            missile_pk=0.7,
        )
        assert result.launched is True
        assert result.aircraft_id == "f18_01"

    def test_out_of_range(self) -> None:
        eng = self._make_engine()
        result = eng.execute_ashm(
            "f18_01", "destroyer_01",
            Position(0, 0, 5000), Position(300000, 0, 0),
            missile_pk=0.7,
        )
        assert result.launched is False
        assert result.abort_reason == "out_of_range"

    def test_result_fields(self) -> None:
        eng = self._make_engine()
        result = eng.execute_ashm(
            "f18_01", "ship_01",
            Position(0, 0, 3000), Position(50000, 0, 0),
            missile_pk=0.5,
        )
        assert result.missile_type == "CRUISE_SUBSONIC"
        assert result.target_ship_id == "ship_01"

    def test_new_mission_enum(self) -> None:
        from stochastic_warfare.combat.air_ground import AirGroundMission

        assert AirGroundMission.ASHM == 5


# ---------------------------------------------------------------------------
# 4. EW integration — air combat
# ---------------------------------------------------------------------------


class TestEWAirCombat:
    def _make_engine(self, **kwargs):
        from stochastic_warfare.combat.air_combat import AirCombatConfig, AirCombatEngine
        from stochastic_warfare.core.events import EventBus

        cfg = AirCombatConfig(**kwargs)
        return AirCombatEngine(EventBus(), make_rng(), cfg)

    def test_disabled_old_behavior(self) -> None:
        eng = self._make_engine(enable_ew_countermeasures=False)
        result = eng.resolve_air_engagement(
            "att1", "def1",
            Position(0, 0, 5000), Position(50000, 0, 5000),
            missile_pk=0.7, countermeasure_type="chaff",
        )
        assert result.countermeasure_reduction > 0

    def test_ew_decoy_reduces_pk(self) -> None:
        mock_decoy = MagicMock()
        mock_decoy.compute_missile_divert_probability.return_value = 0.3

        eng = self._make_engine(enable_ew_countermeasures=True)
        result = eng.resolve_air_engagement(
            "att1", "def1",
            Position(0, 0, 5000), Position(50000, 0, 5000),
            missile_pk=0.7,
            ew_decoy_engine=mock_decoy,
        )
        assert result.countermeasure_reduction >= 0.3

    def test_jamming_reduces_radar_pk(self) -> None:
        mock_jammer = MagicMock()
        mock_jammer.compute_radar_snr_penalty.return_value = -10.0

        eng = self._make_engine(enable_ew_countermeasures=True)
        result = eng.resolve_air_engagement(
            "att1", "def1",
            Position(0, 0, 5000), Position(50000, 0, 5000),
            missile_pk=0.7,
            jamming_engine=mock_jammer,
        )
        assert result.effective_pk < 0.7

    def test_guns_unaffected_by_ew(self) -> None:
        """Guns engagements should not be affected by EW CM."""
        from stochastic_warfare.combat.air_combat import AirCombatMode

        mock_decoy = MagicMock()
        mock_decoy.compute_missile_divert_probability.return_value = 0.5

        eng = self._make_engine(enable_ew_countermeasures=True)
        result = eng.resolve_air_engagement(
            "att1", "def1",
            Position(0, 0, 5000), Position(500, 0, 5000),
            missile_pk=0.7,
            mode=AirCombatMode.GUNS_ONLY,
            ew_decoy_engine=mock_decoy,
        )
        # Guns should not have EW reduction applied
        assert result.countermeasure_reduction == 0.0

    def test_multi_cm_chaff_flare_stacks(self) -> None:
        eng = self._make_engine()
        from stochastic_warfare.combat.air_combat import AirCombatMode

        result = eng.resolve_air_engagement(
            "att1", "def1",
            Position(0, 0, 5000), Position(5000, 0, 5000),
            missile_pk=0.8,
            mode=AirCombatMode.WVR,
            countermeasure_types=["flare", "chaff"],
        )
        assert result.countermeasure_reduction > 0

    def test_dircm_for_ir(self) -> None:
        eng = self._make_engine(dircm_effectiveness=0.5)
        reduction = eng.apply_countermeasures_multi("ir", ["dircm"])
        assert reduction == pytest.approx(0.5)

    def test_empty_cm_list(self) -> None:
        eng = self._make_engine()
        reduction = eng.apply_countermeasures_multi("radar", [])
        assert reduction == 0.0


# ---------------------------------------------------------------------------
# 5. EW integration — air defense
# ---------------------------------------------------------------------------


class TestEWAirDefense:
    def _make_engine(self, **kwargs):
        from stochastic_warfare.combat.air_defense import AirDefenseConfig, AirDefenseEngine
        from stochastic_warfare.core.events import EventBus

        cfg = AirDefenseConfig(**kwargs)
        return AirDefenseEngine(EventBus(), make_rng(), cfg)

    def test_disabled_old_behavior(self) -> None:
        eng = self._make_engine(enable_ew_countermeasures=False)
        result = eng.fire_interceptor(
            "sam1", "tgt1", 0.7, 30000.0,
            countermeasures="chaff",
        )
        assert result.effective_pk < 0.7 * 1.5  # chaff reduces

    def test_ew_decoy_diversion(self) -> None:
        mock_decoy = MagicMock()
        mock_decoy.compute_missile_divert_probability.return_value = 0.4

        eng = self._make_engine(enable_ew_countermeasures=True)
        result = eng.fire_interceptor(
            "sam1", "tgt1", 0.8, 30000.0,
            ew_decoy_engine=mock_decoy,
        )
        assert result.effective_pk < 0.8

    def test_jamming_degrades_tracking(self) -> None:
        mock_jammer = MagicMock()
        mock_jammer.compute_radar_snr_penalty.return_value = -15.0

        eng = self._make_engine(enable_ew_countermeasures=True)
        result = eng.fire_interceptor(
            "sam1", "tgt1", 0.8, 30000.0,
            jamming_engine=mock_jammer,
        )
        assert result.effective_pk < 0.8

    def test_string_fallback(self) -> None:
        """When EW disabled, string CM still works."""
        eng = self._make_engine(enable_ew_countermeasures=False)
        r_none = eng.fire_interceptor("sam1", "tgt1", 0.8, 30000.0, countermeasures="none")
        eng2 = self._make_engine(enable_ew_countermeasures=False)
        r_ecm = eng2.fire_interceptor("sam1", "tgt1", 0.8, 30000.0, countermeasures="ecm")
        # ECM should reduce effective Pk
        assert r_ecm.effective_pk <= r_none.effective_pk


# ---------------------------------------------------------------------------
# 6. Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompat27a:
    def test_engagement_config_defaults(self) -> None:
        from stochastic_warfare.combat.engagement import EngagementConfig

        cfg = EngagementConfig()
        assert cfg.atgm_max_altitude_m == 500.0
        assert cfg.atgm_range_decay_factor == 0.0001
        assert cfg.enable_burst_fire is False
        assert cfg.max_burst_size == 10

    def test_air_combat_config_defaults(self) -> None:
        from stochastic_warfare.combat.air_combat import AirCombatConfig

        cfg = AirCombatConfig()
        assert cfg.enable_ew_countermeasures is False
        assert cfg.dircm_effectiveness == 0.5

    def test_air_defense_config_defaults(self) -> None:
        from stochastic_warfare.combat.air_defense import AirDefenseConfig

        cfg = AirDefenseConfig()
        assert cfg.enable_ew_countermeasures is False

    def test_air_ground_config_defaults(self) -> None:
        from stochastic_warfare.combat.air_ground import AirGroundConfig

        cfg = AirGroundConfig()
        assert cfg.jtac_designation_delay_s == 15.0
        assert cfg.designation_accuracy_bonus == 0.15
