"""Tests for entities/unit_classes/air_defense.py."""

from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import Entity, Unit
from stochastic_warfare.entities.unit_classes.air_defense import (
    ADUnitType,
    AirDefenseUnit,
    RadarState,
)


class TestADUnitType:
    def test_values(self) -> None:
        assert ADUnitType.SAM_LONG == 0
        assert ADUnitType.RADAR_FIRE_CONTROL == 7

    def test_count(self) -> None:
        assert len(ADUnitType) == 8


class TestRadarState:
    def test_progression(self) -> None:
        assert RadarState.OFF < RadarState.STANDBY < RadarState.TRACK


class TestAirDefenseCreation:
    def test_defaults(self) -> None:
        u = AirDefenseUnit(entity_id="ad1", position=Position(0.0, 0.0))
        assert u.ad_type == ADUnitType.SAM_MEDIUM
        assert u.radar_state == RadarState.OFF
        assert u.domain == Domain.GROUND

    def test_patriot(self) -> None:
        u = AirDefenseUnit(
            entity_id="pat1", position=Position(0.0, 0.0),
            ad_type=ADUnitType.SAM_LONG,
            max_engagement_altitude=24000.0,
            max_engagement_range=160000.0,
            ready_missiles=16,
        )
        assert u.max_engagement_range == 160000.0
        assert u.ready_missiles == 16

    def test_is_entity_subclass(self) -> None:
        u = AirDefenseUnit(entity_id="ad2", position=Position(0.0, 0.0))
        assert isinstance(u, Entity)
        assert isinstance(u, Unit)


class TestCanEngage:
    def _make_sam(self) -> AirDefenseUnit:
        return AirDefenseUnit(
            entity_id="sam1", position=Position(0.0, 0.0),
            ad_type=ADUnitType.SAM_MEDIUM,
            radar_state=RadarState.TRACK,
            min_engagement_altitude=50.0,
            max_engagement_altitude=20000.0,
            max_engagement_range=80000.0,
            ready_missiles=4,
        )

    def test_valid_engagement(self) -> None:
        u = self._make_sam()
        assert u.can_engage(target_altitude=5000.0, target_range=50000.0)

    def test_radar_off(self) -> None:
        u = self._make_sam()
        u.radar_state = RadarState.OFF
        assert not u.can_engage(5000.0, 50000.0)

    def test_radar_standby(self) -> None:
        u = self._make_sam()
        u.radar_state = RadarState.STANDBY
        assert not u.can_engage(5000.0, 50000.0)

    def test_no_missiles(self) -> None:
        u = self._make_sam()
        u.ready_missiles = 0
        assert not u.can_engage(5000.0, 50000.0)

    def test_below_min_altitude(self) -> None:
        u = self._make_sam()
        assert not u.can_engage(target_altitude=10.0, target_range=50000.0)

    def test_above_max_altitude(self) -> None:
        u = self._make_sam()
        assert not u.can_engage(target_altitude=25000.0, target_range=50000.0)

    def test_beyond_range(self) -> None:
        u = self._make_sam()
        assert not u.can_engage(target_altitude=5000.0, target_range=100000.0)

    def test_at_boundary(self) -> None:
        u = self._make_sam()
        assert u.can_engage(target_altitude=50.0, target_range=80000.0)


class TestAirDefenseState:
    def test_roundtrip(self) -> None:
        original = AirDefenseUnit(
            entity_id="ad1", position=Position(500.0, 600.0),
            name="Patriot Battery", ad_type=ADUnitType.SAM_LONG,
            radar_state=RadarState.SEARCH,
            min_engagement_altitude=60.0,
            max_engagement_altitude=24000.0,
            max_engagement_range=160000.0,
            ready_missiles=16, reload_time=300.0,
        )
        state = original.get_state()
        restored = AirDefenseUnit(entity_id="", position=Position(0.0, 0.0))
        restored.set_state(state)

        assert restored.ad_type == original.ad_type
        assert restored.radar_state == original.radar_state
        assert restored.max_engagement_range == original.max_engagement_range
        assert restored.ready_missiles == original.ready_missiles
        assert restored.reload_time == original.reload_time

    def test_roundtrip_all_types(self) -> None:
        for adt in ADUnitType:
            u = AirDefenseUnit(entity_id=f"ad{adt}", position=Position(0.0, 0.0),
                               ad_type=adt)
            state = u.get_state()
            r = AirDefenseUnit(entity_id="", position=Position(0.0, 0.0))
            r.set_state(state)
            assert r.ad_type == adt

    def test_roundtrip_all_radar_states(self) -> None:
        for rs in RadarState:
            u = AirDefenseUnit(entity_id="ad", position=Position(0.0, 0.0),
                               radar_state=rs)
            state = u.get_state()
            r = AirDefenseUnit(entity_id="", position=Position(0.0, 0.0))
            r.set_state(state)
            assert r.radar_state == rs
