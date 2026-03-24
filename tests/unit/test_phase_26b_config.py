"""Phase 26b: Configurable constants — verify defaults match originals, custom values change behavior."""

from __future__ import annotations


import pytest

from tests.conftest import TS, make_rng


# ---------------------------------------------------------------------------
# 1. DispersalConfig — terrain_channel_offset_m, terrain_channel_height_m
# ---------------------------------------------------------------------------


class TestDispersalConfigDefaults:
    def test_default_offset(self) -> None:
        from stochastic_warfare.cbrn.dispersal import DispersalConfig
        cfg = DispersalConfig()
        assert cfg.terrain_channel_offset_m == 50.0

    def test_default_height(self) -> None:
        from stochastic_warfare.cbrn.dispersal import DispersalConfig
        cfg = DispersalConfig()
        assert cfg.terrain_channel_height_m == 5.0

    def test_custom_values_accepted(self) -> None:
        from stochastic_warfare.cbrn.dispersal import DispersalConfig
        cfg = DispersalConfig(terrain_channel_offset_m=100.0, terrain_channel_height_m=10.0)
        assert cfg.terrain_channel_offset_m == 100.0
        assert cfg.terrain_channel_height_m == 10.0


# ---------------------------------------------------------------------------
# 2. CBRNConfig — fallback weather values
# ---------------------------------------------------------------------------


class TestCBRNConfigDefaults:
    def test_default_wind_speed(self) -> None:
        from stochastic_warfare.cbrn.engine import CBRNConfig
        cfg = CBRNConfig()
        assert cfg.fallback_wind_speed_mps == 2.0

    def test_default_wind_direction(self) -> None:
        from stochastic_warfare.cbrn.engine import CBRNConfig
        cfg = CBRNConfig()
        assert cfg.fallback_wind_direction_rad == 0.0

    def test_default_cloud_cover(self) -> None:
        from stochastic_warfare.cbrn.engine import CBRNConfig
        cfg = CBRNConfig()
        assert cfg.fallback_cloud_cover == 0.5

    def test_custom_values_accepted(self) -> None:
        from stochastic_warfare.cbrn.engine import CBRNConfig
        cfg = CBRNConfig(
            fallback_wind_speed_mps=5.0,
            fallback_wind_direction_rad=1.5,
            fallback_cloud_cover=0.8,
        )
        assert cfg.fallback_wind_speed_mps == 5.0
        assert cfg.fallback_wind_direction_rad == 1.5
        assert cfg.fallback_cloud_cover == 0.8


# ---------------------------------------------------------------------------
# 3. GasWarfareConfig — max_wind_angle_deg
# ---------------------------------------------------------------------------


class TestGasWarfareConfigDefaults:
    def test_default_wind_angle(self) -> None:
        from stochastic_warfare.combat.gas_warfare import GasWarfareConfig
        cfg = GasWarfareConfig()
        assert cfg.max_wind_angle_deg == 60.0

    def test_custom_wind_angle(self) -> None:
        from stochastic_warfare.combat.gas_warfare import GasWarfareConfig
        cfg = GasWarfareConfig(max_wind_angle_deg=90.0)
        assert cfg.max_wind_angle_deg == 90.0

    def test_wind_angle_affects_check(self) -> None:
        from stochastic_warfare.combat.gas_warfare import GasWarfareConfig, GasWarfareEngine
        rng = make_rng()
        eng_default = GasWarfareEngine(rng=rng)
        eng_tight = GasWarfareEngine(config=GasWarfareConfig(max_wind_angle_deg=30.0), rng=rng)
        # wind_speed=3, wind_dir=0, target_bearing=150 → gas travel=180, diff=30 → both allow
        assert eng_default.check_wind_favorable(3.0, 0.0, 150.0) is True
        assert eng_tight.check_wind_favorable(3.0, 0.0, 150.0) is True
        # wind_speed=3, wind_dir=0, target_bearing=120 → diff=60 → default allows, tight does NOT
        assert eng_default.check_wind_favorable(3.0, 0.0, 120.0) is True
        assert eng_tight.check_wind_favorable(3.0, 0.0, 120.0) is False


# ---------------------------------------------------------------------------
# 4. TrenchConfig — along/crossing angle thresholds
# ---------------------------------------------------------------------------


class TestTrenchConfigDefaults:
    def test_default_along(self) -> None:
        from stochastic_warfare.terrain.trenches import TrenchConfig
        cfg = TrenchConfig()
        assert cfg.along_angle_threshold_deg == 30.0

    def test_default_crossing(self) -> None:
        from stochastic_warfare.terrain.trenches import TrenchConfig
        cfg = TrenchConfig()
        assert cfg.crossing_angle_threshold_deg == 60.0

    def test_custom_values(self) -> None:
        from stochastic_warfare.terrain.trenches import TrenchConfig
        cfg = TrenchConfig(along_angle_threshold_deg=15.0, crossing_angle_threshold_deg=45.0)
        assert cfg.along_angle_threshold_deg == 15.0
        assert cfg.crossing_angle_threshold_deg == 45.0


# ---------------------------------------------------------------------------
# 5. ForagingConfig — ambush_casualty_rate
# ---------------------------------------------------------------------------


class TestForagingConfigDefaults:
    def test_default_ambush_rate(self) -> None:
        from stochastic_warfare.logistics.foraging import ForagingConfig
        cfg = ForagingConfig()
        assert cfg.ambush_casualty_rate == 0.1

    def test_custom_ambush_rate(self) -> None:
        from stochastic_warfare.logistics.foraging import ForagingConfig
        cfg = ForagingConfig(ambush_casualty_rate=0.5)
        assert cfg.ambush_casualty_rate == 0.5


# ---------------------------------------------------------------------------
# 6. JammingConfig — jamming_event_radius_m
# ---------------------------------------------------------------------------


class TestJammingConfigDefaults:
    def test_default_radius(self) -> None:
        from stochastic_warfare.ew.jamming import JammingConfig
        cfg = JammingConfig()
        assert cfg.jamming_event_radius_m == 50000.0

    def test_custom_radius(self) -> None:
        from stochastic_warfare.ew.jamming import JammingConfig
        cfg = JammingConfig(jamming_event_radius_m=100000.0)
        assert cfg.jamming_event_radius_m == 100000.0


# ---------------------------------------------------------------------------
# 7. Spoofing — unit_id flows through to event
# ---------------------------------------------------------------------------


class TestSpoofingUnitId:
    def test_unit_id_default_empty(self) -> None:
        """check_spoof_detection defaults unit_id to empty string."""
        from stochastic_warfare.ew.spoofing import (
            GPSSpoofZone, SpoofingConfig, SpoofingEngine, ReceiverType,
        )
        from stochastic_warfare.core.events import EventBus
        from stochastic_warfare.core.types import Position
        from stochastic_warfare.ew.events import GPSSpoofingDetectedEvent

        bus = EventBus()
        eng = SpoofingEngine(bus, make_rng(), SpoofingConfig())
        eng.add_spoof_zone(GPSSpoofZone(
            zone_id="z1", center=Position(0, 0), radius_m=10000.0,
            offset_east_m=100.0, offset_north_m=100.0, power_dbm=40.0,
        ))
        events: list[GPSSpoofingDetectedEvent] = []
        bus.subscribe(GPSSpoofingDetectedEvent, events.append)
        eng.check_spoof_detection(
            Position(0, 0), ReceiverType.CIVILIAN, 200.0, timestamp=TS,
        )
        assert len(events) == 1
        assert events[0].unit_id == ""

    def test_unit_id_flows_through(self) -> None:
        """Explicit unit_id appears in event."""
        from stochastic_warfare.ew.spoofing import (
            GPSSpoofZone, SpoofingConfig, SpoofingEngine, ReceiverType,
        )
        from stochastic_warfare.core.events import EventBus
        from stochastic_warfare.core.types import Position
        from stochastic_warfare.ew.events import GPSSpoofingDetectedEvent

        bus = EventBus()
        eng = SpoofingEngine(bus, make_rng(), SpoofingConfig())
        eng.add_spoof_zone(GPSSpoofZone(
            zone_id="z1", center=Position(0, 0), radius_m=10000.0,
            offset_east_m=100.0, offset_north_m=100.0, power_dbm=40.0,
        ))
        events: list[GPSSpoofingDetectedEvent] = []
        bus.subscribe(GPSSpoofingDetectedEvent, events.append)
        eng.check_spoof_detection(
            Position(0, 0), ReceiverType.CIVILIAN, 200.0, timestamp=TS, unit_id="inf_01",
        )
        assert len(events) == 1
        assert events[0].unit_id == "inf_01"


# ---------------------------------------------------------------------------
# 8. EW Decoy matrix — dict lookup matches original if/elif
# ---------------------------------------------------------------------------


class TestDecoyMatrix:
    def test_chaff_vs_radar(self) -> None:
        from stochastic_warfare.ew.decoys_ew import EWDecoyConfig
        cfg = EWDecoyConfig()
        assert cfg.decoy_seeker_effectiveness[0][0] == pytest.approx(0.7)

    def test_chaff_vs_anti_rad(self) -> None:
        from stochastic_warfare.ew.decoys_ew import EWDecoyConfig
        cfg = EWDecoyConfig()
        assert cfg.decoy_seeker_effectiveness[0][3] == pytest.approx(0.3)

    def test_flare_vs_ir(self) -> None:
        from stochastic_warfare.ew.decoys_ew import EWDecoyConfig
        cfg = EWDecoyConfig()
        assert cfg.decoy_seeker_effectiveness[1][1] == pytest.approx(0.8)

    def test_flare_vs_eo(self) -> None:
        from stochastic_warfare.ew.decoys_ew import EWDecoyConfig
        cfg = EWDecoyConfig()
        assert cfg.decoy_seeker_effectiveness[1][2] == pytest.approx(0.2)

    def test_towed_vs_radar(self) -> None:
        from stochastic_warfare.ew.decoys_ew import EWDecoyConfig
        cfg = EWDecoyConfig()
        assert cfg.decoy_seeker_effectiveness[2][0] == pytest.approx(0.8)

    def test_drfm_vs_radar(self) -> None:
        from stochastic_warfare.ew.decoys_ew import EWDecoyConfig
        cfg = EWDecoyConfig()
        assert cfg.decoy_seeker_effectiveness[3][0] == pytest.approx(0.6)

    def test_drfm_vs_anti_rad(self) -> None:
        from stochastic_warfare.ew.decoys_ew import EWDecoyConfig
        cfg = EWDecoyConfig()
        assert cfg.decoy_seeker_effectiveness[3][3] == pytest.approx(0.5)

    def test_no_match_returns_zero(self) -> None:
        from stochastic_warfare.ew.decoys_ew import EWDecoyConfig
        cfg = EWDecoyConfig()
        # CHAFF vs IR — not in matrix
        assert cfg.decoy_seeker_effectiveness.get(0, {}).get(1, 0.0) == 0.0

    def test_custom_matrix(self) -> None:
        from stochastic_warfare.ew.decoys_ew import EWDecoyConfig
        custom = {0: {0: 0.99}}
        cfg = EWDecoyConfig(decoy_seeker_effectiveness=custom)
        assert cfg.decoy_seeker_effectiveness[0][0] == 0.99
        assert 1 not in cfg.decoy_seeker_effectiveness


# ---------------------------------------------------------------------------
# 9. SIGINTConfig — activity sigmoid parameters
# ---------------------------------------------------------------------------


class TestSIGINTConfigDefaults:
    def test_default_center(self) -> None:
        from stochastic_warfare.ew.sigint import SIGINTConfig
        cfg = SIGINTConfig()
        assert cfg.activity_sigmoid_center == 10.0

    def test_default_scale(self) -> None:
        from stochastic_warfare.ew.sigint import SIGINTConfig
        cfg = SIGINTConfig()
        assert cfg.activity_sigmoid_scale == 10.0

    def test_custom_values(self) -> None:
        from stochastic_warfare.ew.sigint import SIGINTConfig
        cfg = SIGINTConfig(activity_sigmoid_center=20.0, activity_sigmoid_scale=5.0)
        assert cfg.activity_sigmoid_center == 20.0
        assert cfg.activity_sigmoid_scale == 5.0

    def test_engine_accepts_config(self) -> None:
        from stochastic_warfare.ew.sigint import SIGINTConfig, SIGINTEngine
        from stochastic_warfare.core.events import EventBus
        cfg = SIGINTConfig(activity_sigmoid_center=5.0)
        eng = SIGINTEngine(EventBus(), make_rng(), config=cfg)
        assert eng._sigint_config.activity_sigmoid_center == 5.0

    def test_engine_default_config(self) -> None:
        from stochastic_warfare.ew.sigint import SIGINTEngine
        from stochastic_warfare.core.events import EventBus
        eng = SIGINTEngine(EventBus(), make_rng())
        assert eng._sigint_config.activity_sigmoid_center == 10.0


# ---------------------------------------------------------------------------
# 10. J/S sigmoid NOT changed (documented review)
# ---------------------------------------------------------------------------


class TestJSSigmoidUnchanged:
    def test_js_sigmoid_is_physics(self) -> None:
        """1/(1 + 10^(-js/20)) is standard dB power conversion — NOT configurable."""
        from stochastic_warfare.ew.jamming import JammingConfig
        cfg = JammingConfig()
        # No "js_sigmoid_*" field should exist
        field_names = set(JammingConfig.model_fields.keys())
        assert "js_sigmoid_center" not in field_names
        assert "js_sigmoid_scale" not in field_names
