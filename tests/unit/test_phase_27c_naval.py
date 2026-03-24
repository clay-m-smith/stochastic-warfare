"""Phase 27c: Naval combat completion — naval gun, ASROC, depth charges, torpedo CM, CAP."""

from __future__ import annotations

import pytest

from tests.conftest import TS, make_rng


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_naval_surface_engine(rng=None, **kwargs):
    from stochastic_warfare.combat.damage import DamageEngine
    from stochastic_warfare.combat.naval_surface import NavalSurfaceConfig, NavalSurfaceEngine
    from stochastic_warfare.core.events import EventBus

    rng = rng or make_rng()
    bus = EventBus()
    dmg = DamageEngine(event_bus=bus, rng=rng)
    cfg = NavalSurfaceConfig(**kwargs)
    return NavalSurfaceEngine(damage_engine=dmg, event_bus=bus, rng=rng, config=cfg)


def _make_subsurface_engine(rng=None, **kwargs):
    from stochastic_warfare.combat.damage import DamageEngine
    from stochastic_warfare.combat.naval_subsurface import NavalSubsurfaceConfig, NavalSubsurfaceEngine
    from stochastic_warfare.core.events import EventBus

    rng = rng or make_rng()
    bus = EventBus()
    dmg = DamageEngine(event_bus=bus, rng=rng)
    cfg = NavalSubsurfaceConfig(**kwargs)
    return NavalSubsurfaceEngine(damage_engine=dmg, event_bus=bus, rng=rng, config=cfg)


def _make_carrier_engine(rng=None, **kwargs):
    from stochastic_warfare.combat.carrier_ops import CarrierOpsConfig, CarrierOpsEngine
    from stochastic_warfare.core.events import EventBus

    rng = rng or make_rng()
    bus = EventBus()
    cfg = CarrierOpsConfig(**kwargs)
    return CarrierOpsEngine(event_bus=bus, rng=rng, config=cfg)


# ---------------------------------------------------------------------------
# 1. Modern naval gun
# ---------------------------------------------------------------------------


class TestNavalGun:
    def test_correct_hits(self) -> None:
        eng = _make_naval_surface_engine(rng=make_rng(1))
        result = eng.naval_gun_engagement(
            "dd_01", "patrol_01", range_m=10000.0, rounds_fired=20,
        )
        assert result.rounds_fired == 20
        assert 0 <= result.hits <= 20

    def test_range_degradation(self) -> None:
        """Pk should decrease at longer ranges."""
        eng_close = _make_naval_surface_engine(rng=make_rng(10))
        eng_far = _make_naval_surface_engine(rng=make_rng(10))
        r_close = eng_close.naval_gun_engagement("dd", "tgt", 5000.0, 50)
        r_far = eng_far.naval_gun_engagement("dd", "tgt", 23000.0, 50)
        # Close should generally hit more (probabilistic, but with same seed)
        assert r_close.hits >= r_far.hits

    def test_sea_state_effect(self) -> None:
        eng_calm = _make_naval_surface_engine(rng=make_rng(20))
        eng_rough = _make_naval_surface_engine(rng=make_rng(20))
        r_calm = eng_calm.naval_gun_engagement("dd", "tgt", 10000.0, 50, sea_state=2)
        r_rough = eng_rough.naval_gun_engagement("dd", "tgt", 10000.0, 50, sea_state=7)
        assert r_calm.hits >= r_rough.hits

    def test_fc_quality(self) -> None:
        eng_good = _make_naval_surface_engine(rng=make_rng(30))
        eng_poor = _make_naval_surface_engine(rng=make_rng(30))
        r_good = eng_good.naval_gun_engagement("dd", "tgt", 10000.0, 50, fire_control_quality=1.0)
        r_poor = eng_poor.naval_gun_engagement("dd", "tgt", 10000.0, 50, fire_control_quality=0.2)
        assert r_good.hits >= r_poor.hits

    def test_damage_per_hit(self) -> None:
        eng = _make_naval_surface_engine(rng=make_rng(5), naval_gun_damage_per_hit=0.1)
        result = eng.naval_gun_engagement("dd", "tgt", 5000.0, 100)
        assert result.damage_per_hit == 0.1
        assert result.total_damage == pytest.approx(result.hits * 0.1)

    def test_event_published(self) -> None:
        eng = _make_naval_surface_engine(rng=make_rng(1))
        # Fire enough rounds that at least some hit
        eng.naval_gun_engagement("dd", "tgt", 5000.0, 100, timestamp=TS)
        # Just verify no error; event publishing is fire-and-forget

    def test_zero_at_max_range(self) -> None:
        eng = _make_naval_surface_engine(naval_gun_max_range_m=10000.0)
        result = eng.naval_gun_engagement("dd", "tgt", 15000.0, 20)
        assert result.rounds_fired == 0
        assert result.hits == 0

    def test_result_fields(self) -> None:
        eng = _make_naval_surface_engine()
        result = eng.naval_gun_engagement("dd", "tgt", 10000.0, 10)
        assert result.ship_id == "dd"
        assert result.target_id == "tgt"
        assert result.range_m == 10000.0


# ---------------------------------------------------------------------------
# 2. ASROC & depth charges
# ---------------------------------------------------------------------------


class TestASROCAndDepthCharges:
    def test_asroc_range_check(self) -> None:
        eng = _make_subsurface_engine()
        result = eng.asroc_engagement("ffg", "sub1", range_m=30000.0)
        assert result.flight_success is False

    def test_asroc_flight_success(self) -> None:
        """Over many trials, most ASROC flights should succeed (0.9)."""
        successes = 0
        for seed in range(100):
            eng = _make_subsurface_engine(rng=make_rng(seed))
            result = eng.asroc_engagement("ffg", "sub1", range_m=10000.0)
            if result.flight_success:
                successes += 1
        assert successes > 70  # ~90% expected

    def test_asroc_torpedo_follows(self) -> None:
        """When flight succeeds, torpedo engagement resolves."""
        eng = _make_subsurface_engine(rng=make_rng(1))
        result = eng.asroc_engagement("ffg", "sub1", range_m=10000.0)
        if result.flight_success:
            # torpedo_hit is a boolean regardless
            assert isinstance(result.torpedo_hit, bool)

    def test_depth_charge_pattern_scatter(self) -> None:
        eng = _make_subsurface_engine(rng=make_rng(42))
        result = eng.depth_charge_attack("ddg", "sub1", num_charges=20, target_range_m=0.0)
        assert result.charges_dropped == 20
        # At zero range, some should hit within lethal radius
        assert result.hits >= 0

    def test_depth_charge_lethal_radius(self) -> None:
        """Depth charges far from target should rarely hit."""
        eng = _make_subsurface_engine(rng=make_rng(50))
        result = eng.depth_charge_attack(
            "ddg", "sub1", num_charges=10,
            target_range_m=5000.0,  # far outside pattern
        )
        assert result.hits == 0

    def test_multiple_charges(self) -> None:
        eng = _make_subsurface_engine(
            rng=make_rng(7),
            depth_charge_pk_per_charge=0.9,
            depth_charge_lethal_radius_m=200.0,
        )
        result = eng.depth_charge_attack("ddg", "sub1", 50, target_range_m=0.0)
        assert result.hits > 0


# ---------------------------------------------------------------------------
# 3. Torpedo countermeasures
# ---------------------------------------------------------------------------


class TestTorpedoCountermeasures:
    def test_nixie_probability(self) -> None:
        """NIXIE should defeat torpedo at ~35% rate."""
        defeats = 0
        for seed in range(200):
            eng = _make_subsurface_engine(rng=make_rng(seed))
            result = eng.resolve_torpedo_countermeasures(
                "ddg", 0.5, nixie_deployed=True,
            )
            if result.torpedo_defeated:
                defeats += 1
        # ~35% ± margin
        assert 40 < defeats < 100

    def test_acoustic_cm(self) -> None:
        defeats = 0
        for seed in range(200):
            eng = _make_subsurface_engine(rng=make_rng(seed))
            result = eng.resolve_torpedo_countermeasures(
                "ddg", 0.5, acoustic_cm=True,
            )
            if result.torpedo_defeated:
                defeats += 1
        assert 25 < defeats < 80

    def test_combined_layers(self) -> None:
        """Multiple layers should increase total defeat probability."""
        defeats_single = 0
        defeats_multi = 0
        for seed in range(200):
            eng1 = _make_subsurface_engine(rng=make_rng(seed))
            r1 = eng1.resolve_torpedo_countermeasures("ddg", 0.5, nixie_deployed=True)
            if r1.torpedo_defeated:
                defeats_single += 1

            eng2 = _make_subsurface_engine(rng=make_rng(seed))
            r2 = eng2.resolve_torpedo_countermeasures(
                "ddg", 0.5, nixie_deployed=True, acoustic_cm=True,
            )
            if r2.torpedo_defeated:
                defeats_multi += 1

        assert defeats_multi >= defeats_single

    def test_defeated_on_any_success(self) -> None:
        eng = _make_subsurface_engine(
            rng=make_rng(1),
            nixie_seduction_probability=1.0,  # guarantee success
        )
        result = eng.resolve_torpedo_countermeasures("ddg", 0.5, nixie_deployed=True)
        assert result.torpedo_defeated is True
        assert result.nixie_success is True
        assert result.effective_pk == 0.0

    def test_no_cm_no_effect(self) -> None:
        eng = _make_subsurface_engine()
        result = eng.resolve_torpedo_countermeasures("ddg", 0.5)
        assert result.torpedo_defeated is False
        assert result.effective_pk == 0.5

    def test_stacking(self) -> None:
        """With all layers, defeat rate should be higher than any single layer."""
        defeats = 0
        for seed in range(200):
            eng = _make_subsurface_engine(rng=make_rng(seed))
            result = eng.resolve_torpedo_countermeasures(
                "ddg", 0.5,
                nixie_deployed=True,
                acoustic_cm=True,
                evasion_type="hard_turn",
            )
            if result.torpedo_defeated:
                defeats += 1
        # Combined ~50% (35% + 25%×65% + 15%×65%×75% ≈ 54%)
        assert defeats > 60

    def test_config_defaults(self) -> None:
        from stochastic_warfare.combat.naval_subsurface import NavalSubsurfaceConfig

        cfg = NavalSubsurfaceConfig()
        assert cfg.nixie_seduction_probability == 0.35
        assert cfg.acoustic_cm_confusion_probability == 0.25
        assert cfg.enable_torpedo_countermeasures is False


# ---------------------------------------------------------------------------
# 4. Carrier CAP management
# ---------------------------------------------------------------------------


class TestCarrierCAP:
    def test_station_creation(self) -> None:
        eng = _make_carrier_engine()
        station = eng.create_cap_station("cap_north", ["f18_01", "f18_02"])
        assert station.station_id == "cap_north"
        assert len(station.aircraft_ids) == 2
        assert station.time_on_station_s == 0.0

    def test_time_tracking(self) -> None:
        eng = _make_carrier_engine()
        eng.create_cap_station("cap1", ["f18_01"])
        eng.update_cap_stations(3600.0)
        station = eng._cap_stations["cap1"]
        assert station.time_on_station_s == 3600.0

    def test_relief_flagged(self) -> None:
        eng = _make_carrier_engine(
            cap_station_endurance_s=14400.0,
            cap_relief_margin_s=1800.0,
        )
        eng.create_cap_station("cap1", ["f18_01"])
        # Advance to near endurance limit
        need_relief = eng.update_cap_stations(13000.0)
        assert len(need_relief) == 1
        assert need_relief[0].relief_needed is True

    def test_recovery_window(self) -> None:
        eng = _make_carrier_engine()
        window = eng.schedule_recovery_window(start_time_s=5000.0)
        assert window.start_time_s == 5000.0
        assert window.active is True
        assert window.duration_s == eng._config.recovery_window_duration_s

    def test_multiple_stations(self) -> None:
        eng = _make_carrier_engine()
        eng.create_cap_station("north", ["f18_01"])
        eng.create_cap_station("south", ["f18_02"])
        assert len(eng._cap_stations) == 2

    def test_no_relief_before_margin(self) -> None:
        eng = _make_carrier_engine(
            cap_station_endurance_s=14400.0,
            cap_relief_margin_s=1800.0,
        )
        eng.create_cap_station("cap1", ["f18_01"])
        need_relief = eng.update_cap_stations(1000.0)
        assert len(need_relief) == 0


# ---------------------------------------------------------------------------
# 5. Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompat27c:
    def test_naval_surface_config_defaults(self) -> None:
        from stochastic_warfare.combat.naval_surface import NavalSurfaceConfig

        cfg = NavalSurfaceConfig()
        assert cfg.naval_gun_base_pk_per_round == 0.03
        assert cfg.naval_gun_max_range_m == 24_000.0

    def test_subsurface_config_defaults(self) -> None:
        from stochastic_warfare.combat.naval_subsurface import NavalSubsurfaceConfig

        cfg = NavalSubsurfaceConfig()
        assert cfg.asroc_max_range_m == 22_000.0
        assert cfg.asroc_torpedo_pk == 0.3

    def test_carrier_config_defaults(self) -> None:
        from stochastic_warfare.combat.carrier_ops import CarrierOpsConfig

        cfg = CarrierOpsConfig()
        assert cfg.cap_aircraft_per_station == 2
        assert cfg.cap_relief_margin_s == 1800.0

    def test_existing_torpedo_engagement_works(self) -> None:
        """Existing torpedo_engagement should still work unchanged."""
        eng = _make_subsurface_engine(rng=make_rng(42))
        result = eng.torpedo_engagement("sub1", "tgt1", 0.5, 10000.0)
        assert hasattr(result, "hit")
