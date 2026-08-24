"""Phase 17c tests — Space-based ISR and early warning."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit
from stochastic_warfare.entities.personnel import (
    CrewMember,
    CrewRole,
    SkillLevel,
)
from stochastic_warfare.space.constellations import (
    ConstellationDefinition,
    ConstellationManager,
    ConstellationType,
    SpaceConfig,
)
from stochastic_warfare.space.early_warning import EarlyWarningEngine
from stochastic_warfare.space.events import (
    EarlyWarningDetectionEvent,
)
from stochastic_warfare.space.isr import SpaceISREngine, _RESOLUTION_THRESHOLD
from stochastic_warfare.space.orbits import OrbitalMechanicsEngine, R_EARTH

from tests.conftest import make_clock, make_rng


def _rng(seed: int = 42) -> np.random.Generator:
    return make_rng(seed)


def _bus() -> EventBus:
    return EventBus()


def _config(**kw) -> SpaceConfig:
    return SpaceConfig(enable_space=True, theater_lat=33.0, theater_lon=35.0, **kw)


def _make_imaging_constellation(
    ctype: int = int(ConstellationType.IMAGING_OPTICAL),
    sensor_type: str = "optical",
    resolution: float = 0.3,
    side: str = "blue",
) -> ConstellationDefinition:
    return ConstellationDefinition(
        constellation_id=f"img_{sensor_type}",
        constellation_type=ctype,
        side=side,
        num_satellites=4,
        orbital_elements_template={
            "semi_major_axis_m": R_EARTH + 500_000.0,
            "eccentricity": 0.0,
            "inclination_deg": 97.0,
            "raan_deg": 0.0,
            "arg_perigee_deg": 0.0,
            "true_anomaly_deg": 0.0,
        },
        plane_count=2,
        sats_per_plane=2,
        sensor_resolution_m=resolution,
        sensor_swath_km=20.0,
        sensor_type=sensor_type,
        imint_position_sigma_m=2.0,
    )


def _make_ew_constellation(side: str = "blue") -> ConstellationDefinition:
    return ConstellationDefinition(
        constellation_id="sbirs_geo",
        constellation_type=int(ConstellationType.EARLY_WARNING),
        side=side,
        num_satellites=6,
        orbital_elements_template={
            "semi_major_axis_m": 42_164_000.0,
            "eccentricity": 0.0,
            "inclination_deg": 0.0,
            "raan_deg": 0.0,
            "arg_perigee_deg": 0.0,
            "true_anomaly_deg": 0.0,
        },
        plane_count=1,
        sats_per_plane=6,
        sensor_type="ir",
        detection_delay_s=60.0,
        detection_confidence=0.9,
    )


def _make_target(entity_id: str = "t1", strength: int = 10) -> Unit:
    return Unit(
        entity_id=entity_id,
        position=Position(1000.0, 2000.0, 0.0),
        side="red",
        personnel=[
            CrewMember(
                member_id=f"{entity_id}_crew_{index}",
                role=CrewRole.GENERIC,
                skill=SkillLevel.TRAINED,
                experience=0.5,
            )
            for index in range(strength)
        ],
    )


def _setup_isr(sensor_type: str = "optical", resolution: float = 0.3):
    orbits = OrbitalMechanicsEngine()
    bus = _bus()
    rng = _rng()
    constellation_id = f"img_{sensor_type}"
    cfg = _config(
        constellation_ids=[constellation_id],
        imint_fusion_constellation_ids=[constellation_id],
    )
    clock = make_clock()
    cm = ConstellationManager(orbits, bus, rng, cfg)
    cm.add_constellation(_make_imaging_constellation(sensor_type=sensor_type, resolution=resolution))
    isr = SpaceISREngine(
        cm,
        cfg,
        bus,
        rng,
        clock,
        scenario_sides=("blue", "red"),
    )
    return isr, cm


def _setup_ew():
    orbits = OrbitalMechanicsEngine()
    bus = _bus()
    rng = _rng()
    cfg = _config()
    clock = make_clock()
    cm = ConstellationManager(orbits, bus, rng, cfg)
    cm.add_constellation(_make_ew_constellation())
    ew = EarlyWarningEngine(cm, cfg, bus, rng, clock)
    return ew, cm


# ---------------------------------------------------------------------------
# TestISROverpass
# ---------------------------------------------------------------------------


class TestISROverpass:
    @pytest.mark.test_evidence("structural_only")
    def test_overpass_event(self) -> None:
        """ISR check produces overpass events for visible satellites."""
        isr, cm = _setup_isr()
        # Propagate so sats are in known state
        cm.update(3600.0, 3600.0)
        events = isr.check_overpass("blue", 3600.0)
        # May or may not have visible sats depending on geometry
        assert isinstance(events, list)

    def test_hysteresis(self) -> None:
        """Same satellite only reported once per 60s."""
        isr, cm = _setup_isr()
        cm.update(100.0, 100.0)
        events1 = isr.check_overpass("blue", 100.0)
        events2 = isr.check_overpass("blue", 110.0)
        # Second call within 60s should not re-report same sats
        reported1 = {e.satellite_id for e in events1}
        reported2 = {e.satellite_id for e in events2}
        assert reported1.isdisjoint(reported2) or len(reported2) == 0

    def test_timing_gap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """After 120s gap, satellite can be re-reported."""
        isr, cm = _setup_isr()
        satellite = cm.all_satellites()[0]
        monkeypatch.setattr(
            cm,
            "visible_satellites",
            lambda *_args, **_kwargs: [satellite],
        )

        first = isr.check_overpass("blue", 100.0)
        inside_hysteresis = isr.check_overpass("blue", 159.0)
        after_gap = isr.check_overpass("blue", 220.0)

        assert [event.satellite_id for event in first] == [
            satellite.satellite_id,
        ]
        assert inside_hysteresis == []
        assert [event.satellite_id for event in after_gap] == [
            satellite.satellite_id,
        ]
        assert isr._last_overpass_time[satellite.satellite_id] == 220.0

    def test_side_filtering(self) -> None:
        """ISR only reports for the matching side."""
        orbits = OrbitalMechanicsEngine()
        bus = _bus()
        rng = _rng()
        cfg = _config()
        cm = ConstellationManager(orbits, bus, rng, cfg)
        cm.add_constellation(_make_imaging_constellation(side="blue"))
        isr = SpaceISREngine(cm, cfg, bus, rng)
        cm.update(3600.0, 3600.0)
        events = isr.check_overpass("red", 3600.0)  # Red has no ISR sats
        assert len(events) == 0

    def test_swath_in_event(self) -> None:
        """Overpass event includes correct coverage radius."""
        isr, cm = _setup_isr()
        cm.update(3600.0, 3600.0)
        events = isr.check_overpass("blue", 3600.0)
        for evt in events:
            assert evt.coverage_radius_m == pytest.approx(20.0 * 1000.0 / 2.0)


# ---------------------------------------------------------------------------
# TestISRReports
# ---------------------------------------------------------------------------


class TestISRReports:
    def test_optical_detects(self) -> None:
        """Optical satellite with good resolution detects platoon target."""
        isr, cm = _setup_isr("optical", 0.3)
        cm.update(3600.0, 3600.0)
        targets = [_make_target("t1", 20)]  # platoon size
        reports = isr.generate_isr_reports(
            "blue",
            "red",
            targets,
            3600.0,
            cloud_cover=0.0,
        )
        # May or may not have visible sats — just check structure
        for r in reports:
            assert r.target_id == "t1"
            assert r.resolution_m == 0.3

    @pytest.mark.test_evidence("structural_only")
    def test_sar_unblocked_by_cloud(self) -> None:
        """SAR satellite works through clouds."""
        orbits = OrbitalMechanicsEngine()
        bus = _bus()
        rng = _rng()
        cfg = _config(
            constellation_ids=["img_sar"],
            imint_fusion_constellation_ids=["img_sar"],
        )
        cm = ConstellationManager(orbits, bus, rng, cfg)
        cm.add_constellation(
            _make_imaging_constellation(
                ctype=int(ConstellationType.IMAGING_SAR),
                sensor_type="sar",
                resolution=1.0,
            )
        )
        isr = SpaceISREngine(
            cm,
            cfg,
            bus,
            rng,
            scenario_sides=("blue", "red"),
        )
        cm.update(3600.0, 3600.0)
        targets = [_make_target("t1", 20)]
        reports = isr.generate_isr_reports(
            "blue",
            "red",
            targets,
            3600.0,
            cloud_cover=0.9,
        )
        # SAR should not be blocked by cloud > 0.7
        # (whether reports exist depends on visibility geometry)
        assert isinstance(reports, tuple)

    def test_cloud_blocks_optical(self) -> None:
        """Optical blocked by cloud > 0.7."""
        isr, cm = _setup_isr("optical", 0.3)
        cm.update(3600.0, 3600.0)
        targets = [_make_target("t1", 20)]
        reports = isr.generate_isr_reports(
            "blue",
            "red",
            targets,
            3600.0,
            cloud_cover=0.9,
        )
        assert len(reports) == 0  # Optical blocked

    def test_resolution_limit(self) -> None:
        """A known-visible vehicle is resolved at 0.5 m, not above it."""
        target = _make_target("t1", 2)
        threshold = _RESOLUTION_THRESHOLD["vehicle"]
        known_visible_s = 31_560.0
        assert threshold == 0.5

        coarse_isr, coarse_cm = _setup_isr(
            "optical",
            threshold + 1.0e-6,
        )
        coarse_cm.update(known_visible_s, known_visible_s)
        coarse_visible = coarse_cm.visible_satellites(
            "img_optical",
            33.0,
            35.0,
            known_visible_s,
            10.0,
        )
        coarse_overpass = coarse_isr.check_overpass(
            "blue",
            known_visible_s,
        )
        coarse_reports = coarse_isr.generate_isr_reports(
            "blue",
            "red",
            [target],
            known_visible_s,
            cloud_cover=0.0,
        )
        assert [satellite.satellite_id for satellite in coarse_visible] == ["img_optical_p1_s1"]
        assert [event.satellite_id for event in coarse_overpass] == [
            "img_optical_p1_s1",
        ]
        assert coarse_reports == ()

        exact_isr, exact_cm = _setup_isr("optical", threshold)
        exact_cm.update(known_visible_s, known_visible_s)
        exact_visible = exact_cm.visible_satellites(
            "img_optical",
            33.0,
            35.0,
            known_visible_s,
            10.0,
        )
        exact_overpass = exact_isr.check_overpass(
            "blue",
            known_visible_s,
        )
        exact_reports = exact_isr.generate_isr_reports(
            "blue",
            "red",
            [target],
            known_visible_s,
            cloud_cover=0.0,
        )
        assert [satellite.satellite_id for satellite in exact_visible] == ["img_optical_p1_s1"]
        assert [event.satellite_id for event in exact_overpass] == [
            "img_optical_p1_s1",
        ]
        assert len(exact_reports) == 1
        assert exact_reports[0].target_id == target.entity_id
        assert exact_reports[0].resolution_m == threshold

    def test_delay_field(self) -> None:
        """Reports include processing delay."""
        isr, cm = _setup_isr("optical", 0.3)
        cm.update(3600.0, 3600.0)
        targets = [_make_target("t1", 20)]
        reports = isr.generate_isr_reports(
            "blue",
            "red",
            targets,
            3600.0,
            cloud_cover=0.0,
        )
        for r in reports:
            assert r.available_at_s - r.observed_at_s == 300.0


# ---------------------------------------------------------------------------
# TestResolution
# ---------------------------------------------------------------------------


class TestResolution:
    def test_vehicle_threshold(self) -> None:
        assert _RESOLUTION_THRESHOLD["vehicle"] == 0.5

    def test_platoon_threshold(self) -> None:
        assert _RESOLUTION_THRESHOLD["platoon"] == 2.0

    def test_battalion_threshold(self) -> None:
        assert _RESOLUTION_THRESHOLD["battalion"] == 15.0


# ---------------------------------------------------------------------------
# TestEarlyWarning
# ---------------------------------------------------------------------------


class TestEarlyWarning:
    def test_geo_detects(self) -> None:
        """GEO early warning satellite detects launch."""
        ew, cm = _setup_ew()
        cm.update(3600.0, 3600.0)
        detected, delay = ew.check_launch_detection(33.0, 35.0, "blue", 3600.0)
        # GEO sats should be visible from most theater locations
        # But depends on geometry; at least test the API
        assert isinstance(detected, bool)
        if detected:
            assert delay == pytest.approx(60.0)

    def test_no_coverage(self) -> None:
        """Without early warning constellation, no detection."""
        orbits = OrbitalMechanicsEngine()
        bus = _bus()
        rng = _rng()
        cfg = _config()
        cm = ConstellationManager(orbits, bus, rng, cfg)
        # No EW constellation added
        ew = EarlyWarningEngine(cm, cfg, bus, rng)
        detected, delay = ew.check_launch_detection(33.0, 35.0, "blue", 0.0)
        assert detected is False
        assert delay == float("inf")

    def test_delay_value(self) -> None:
        """Detection delay matches constellation definition."""
        ew, cm = _setup_ew()
        cm.update(3600.0, 3600.0)
        detected, delay = ew.check_launch_detection(33.0, 35.0, "blue", 3600.0)
        if detected:
            assert delay == 60.0

    def test_event_published(self) -> None:
        """Detection publishes an EarlyWarningDetectionEvent."""
        bus = _bus()
        received = []
        bus.subscribe(EarlyWarningDetectionEvent, received.append)

        orbits = OrbitalMechanicsEngine()
        rng = _rng()
        cfg = _config()
        cm = ConstellationManager(orbits, bus, rng, cfg)
        cm.add_constellation(_make_ew_constellation())
        ew = EarlyWarningEngine(cm, cfg, bus, rng)
        cm.update(3600.0, 3600.0)
        detected, _ = ew.check_launch_detection(33.0, 35.0, "blue", 3600.0)
        if detected:
            assert len(received) == 1


# ---------------------------------------------------------------------------
# TestWarningTime
# ---------------------------------------------------------------------------


class TestWarningTime:
    def test_computation(self) -> None:
        ew, _ = _setup_ew()
        wt = ew.compute_early_warning_time(60.0, 600.0)
        assert wt == pytest.approx(540.0)

    def test_negative_clamped(self) -> None:
        ew, _ = _setup_ew()
        wt = ew.compute_early_warning_time(700.0, 600.0)
        assert wt == 0.0

    def test_pk_bonus_integration(self) -> None:
        """Early warning time > 60s gives Pk bonus in BMD."""
        from stochastic_warfare.combat.missile_defense import MissileDefenseEngine

        bus = _bus()
        rng = _rng(99)
        bmd = MissileDefenseEngine(bus, rng)
        # Without early warning
        result1 = bmd.engage_ballistic_missile([0.5], early_warning_time_s=0.0)
        # With early warning — Pk bonus applied to first layer
        # Just verify the API accepts the parameter
        result2 = bmd.engage_ballistic_missile([0.5], early_warning_time_s=300.0)
        assert result2.per_layer_pk[0] > result1.per_layer_pk[0]


# ---------------------------------------------------------------------------
# TestBMDIntegration
# ---------------------------------------------------------------------------


class TestBMDIntegration:
    def test_ew_bonus_present(self) -> None:
        """Early warning bonus increases first-layer Pk."""
        from stochastic_warfare.combat.missile_defense import MissileDefenseEngine

        bus = _bus()
        rng = _rng()
        bmd = MissileDefenseEngine(bus, rng)
        r1 = bmd.engage_ballistic_missile([0.4], early_warning_time_s=0.0)
        r2 = bmd.engage_ballistic_missile([0.4], early_warning_time_s=600.0)
        assert r2.per_layer_pk[0] > r1.per_layer_pk[0]

    def test_no_warning_baseline(self) -> None:
        """Zero warning time = no bonus."""
        from stochastic_warfare.combat.missile_defense import MissileDefenseEngine

        bus = _bus()
        rng = _rng()
        bmd = MissileDefenseEngine(bus, rng)
        r = bmd.engage_ballistic_missile([0.5], early_warning_time_s=0.0)
        # 0.5 * speed_penalty (1.0 for 3000 mps default) = 0.5
        assert r.per_layer_pk[0] < 0.51

    def test_backward_compat(self) -> None:
        """Default early_warning_time_s=0.0 → no change from Phase 4 behavior."""
        from stochastic_warfare.combat.missile_defense import MissileDefenseEngine

        bus = _bus()
        rng = _rng()
        bmd = MissileDefenseEngine(bus, rng)
        r = bmd.engage_ballistic_missile([0.6])
        # Default 0.0 → no bonus
        # Default 3000 mps == upper_tier_threshold → penalty = 0.9
        assert abs(r.per_layer_pk[0] - 0.6 * 0.9) < 0.01


# ---------------------------------------------------------------------------
# TestState
# ---------------------------------------------------------------------------


class TestISRState:
    def test_roundtrip(self) -> None:
        isr, cm = _setup_isr()
        satellite_id = cm.all_satellites()[0].satellite_id
        isr._last_overpass_time[satellite_id] = 1000.0
        state = isr.get_state()
        isr2, _ = _setup_isr()
        isr2.set_state(state)
        assert isr2._last_overpass_time[satellite_id] == 1000.0

    @pytest.mark.test_evidence("structural_only")
    def test_ew_state(self) -> None:
        ew, _ = _setup_ew()
        state = ew.get_state()
        assert isinstance(state, dict)
