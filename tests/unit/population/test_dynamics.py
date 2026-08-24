"""Phase 12e — Civilian Population & COIN tests.

Tests for:
- 12e-1: Civilian entity manager
- 12e-2: Refugee displacement
- 12e-3: Collateral damage tracking
- 12e-4: Civilian HUMINT
- 12e-5: Population disposition dynamics
- 12e-6: ROE escalation triggers
"""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import ModuleId, Position

from tests.conftest import TS, make_rng

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rng(seed: int = 42) -> np.random.Generator:
    return make_rng(seed)


def _event_bus() -> EventBus:
    return EventBus()


def _make_region(
    region_id="r1", center=None, radius_m=5000.0, population=10000,
    disposition=None,
):
    from stochastic_warfare.population.civilians import CivilianDisposition, CivilianRegion
    return CivilianRegion(
        region_id=region_id,
        center=center or Position(0, 0, 0),
        radius_m=radius_m,
        population=population,
        disposition=disposition if disposition is not None else CivilianDisposition.NEUTRAL,
    )


def _make_civilian_manager(rng=None, event_bus=None):
    from stochastic_warfare.population.civilians import CivilianManager
    return CivilianManager(
        event_bus=event_bus or _event_bus(),
        rng=rng or _rng(),
    )


# ===================================================================
# 12e-1: Civilian Entity Manager
# ===================================================================


class TestCivilianManager:
    """CivilianManager region registration and query."""

    def test_register_and_get(self):
        mgr = _make_civilian_manager()
        r = _make_region("town1")
        mgr.register_region(r)
        assert mgr.get_region("town1").population == 10000

    def test_all_regions(self):
        mgr = _make_civilian_manager()
        mgr.register_region(_make_region("r1"))
        mgr.register_region(_make_region("r2", center=Position(10000, 0, 0)))
        assert len(mgr.all_regions()) == 2

    def test_query_disposition_inside(self):
        from stochastic_warfare.population.civilians import CivilianDisposition
        mgr = _make_civilian_manager()
        mgr.register_region(_make_region("r1", disposition=CivilianDisposition.FRIENDLY))
        result = mgr.query_disposition_at(Position(100, 100, 0))
        assert result == CivilianDisposition.FRIENDLY

    def test_query_disposition_outside(self):
        mgr = _make_civilian_manager()
        mgr.register_region(_make_region("r1", radius_m=100.0))
        result = mgr.query_disposition_at(Position(50000, 50000, 0))
        assert result is None

    def test_record_displacement(self):
        mgr = _make_civilian_manager()
        mgr.register_region(_make_region("r1", population=1000))
        mgr.record_displacement("r1", 200)
        assert mgr.get_region("r1").displaced_count == 200

    def test_displacement_capped_at_population(self):
        mgr = _make_civilian_manager()
        mgr.register_region(_make_region("r1", population=100))
        mgr.record_displacement("r1", 500)
        assert mgr.get_region("r1").displaced_count == 100

    def test_total_displaced(self):
        mgr = _make_civilian_manager()
        mgr.register_region(_make_region("r1", population=1000))
        mgr.register_region(_make_region("r2", population=2000, center=Position(10000, 0, 0)))
        mgr.record_displacement("r1", 100)
        mgr.record_displacement("r2", 200)
        assert mgr.total_displaced() == 300

    def test_record_collateral(self):
        mgr = _make_civilian_manager()
        mgr.register_region(_make_region("r1"))
        mgr.record_collateral("r1", 10)
        mgr.record_collateral("r1", 5)
        assert mgr.get_region("r1").cumulative_collateral == 15

    def test_state_serialization(self):
        mgr = _make_civilian_manager()
        mgr.register_region(_make_region("r1", population=5000))
        mgr.record_displacement("r1", 100)
        state = mgr.get_state()
        mgr2 = _make_civilian_manager()
        mgr2.set_state(state)
        assert mgr2.get_region("r1").displaced_count == 100

    def test_get_region_raises_keyerror(self):
        mgr = _make_civilian_manager()
        with pytest.raises(KeyError):
            mgr.get_region("nonexistent")


# ===================================================================
# 12e-2: Refugee Displacement
# ===================================================================


class TestDisplacement:
    """DisplacementEngine displaces civilians from combat zones."""

    def test_combat_causes_displacement(self):
        from stochastic_warfare.population.displacement import DisplacementEngine
        mgr = _make_civilian_manager()
        mgr.register_region(_make_region("r1", population=10000))
        eng = DisplacementEngine(mgr, _event_bus(), _rng())
        result = eng.update(
            dt_hours=1.0,
            combat_zones=[(Position(0, 0, 0), 0.8)],
            timestamp=TS,
        )
        assert "r1" in result
        assert result["r1"] > 0
        assert mgr.get_region("r1").displaced_count > 0

    def test_no_combat_no_displacement(self):
        from stochastic_warfare.population.displacement import DisplacementEngine
        mgr = _make_civilian_manager()
        mgr.register_region(_make_region("r1"))
        eng = DisplacementEngine(mgr, _event_bus(), _rng())
        result = eng.update(dt_hours=1.0, combat_zones=[])
        assert len(result) == 0

    def test_distant_combat_no_effect(self):
        from stochastic_warfare.population.displacement import DisplacementEngine
        mgr = _make_civilian_manager()
        mgr.register_region(_make_region("r1", radius_m=1000.0))
        eng = DisplacementEngine(mgr, _event_bus(), _rng())
        result = eng.update(
            dt_hours=1.0,
            combat_zones=[(Position(100000, 100000, 0), 1.0)],
        )
        assert len(result) == 0

    def test_transport_penalty(self):
        from stochastic_warfare.population.displacement import DisplacementEngine
        eng = DisplacementEngine(_make_civilian_manager(), _event_bus(), _rng())
        assert eng.compute_transport_penalty(0) == 1.0
        penalty = eng.compute_transport_penalty(5000)
        assert penalty < 1.0
        assert penalty >= 0.1  # minimum

    def test_max_displacement_fraction(self):
        from stochastic_warfare.population.displacement import DisplacementConfig, DisplacementEngine
        mgr = _make_civilian_manager()
        mgr.register_region(_make_region("r1", population=100))
        cfg = DisplacementConfig(
            displacement_rate_per_intensity=10.0,  # very high
            max_displacement_fraction=0.5,
        )
        eng = DisplacementEngine(mgr, _event_bus(), _rng(), cfg)
        # Very high intensity, many steps
        for _ in range(20):
            eng.update(dt_hours=1.0, combat_zones=[(Position(0, 0, 0), 1.0)])
        assert mgr.get_region("r1").displaced_count <= 50  # 50% of 100


# ===================================================================
# 12e-3: Collateral Damage Tracking
# ===================================================================


class TestCollateral:
    """CollateralEngine tracks civilian casualties."""

    def test_record_and_get_cumulative(self):
        from stochastic_warfare.population.collateral import CollateralEngine
        eng = CollateralEngine(_event_bus())
        eng.record_damage(Position(0, 0, 0), 10, "air_strike", "blue", TS)
        eng.record_damage(Position(0, 0, 0), 5, "indirect_fire", "blue", TS)
        assert eng.get_cumulative("blue") == 15

    def test_separate_sides(self):
        from stochastic_warfare.population.collateral import CollateralEngine
        eng = CollateralEngine(_event_bus())
        eng.record_damage(Position(0, 0, 0), 10, "air_strike", "blue", TS)
        eng.record_damage(Position(0, 0, 0), 20, "artillery", "red", TS)
        assert eng.get_cumulative("blue") == 10
        assert eng.get_cumulative("red") == 20

    def test_exceeds_threshold(self):
        from stochastic_warfare.population.collateral import CollateralConfig, CollateralEngine
        eng = CollateralEngine(_event_bus(), CollateralConfig(escalation_threshold=25))
        eng.record_damage(Position(0, 0, 0), 10, "fire", "blue")
        assert eng.exceeds_threshold("blue") is False
        eng.record_damage(Position(0, 0, 0), 20, "fire", "blue")
        assert eng.exceeds_threshold("blue") is True

    def test_publishes_event(self):
        from stochastic_warfare.population.collateral import CollateralEngine
        from stochastic_warfare.population.events import CollateralDamageEvent
        eb = _event_bus()
        events: list = []
        eb.subscribe(CollateralDamageEvent, lambda e: events.append(e))
        eng = CollateralEngine(eb)
        eng.record_damage(Position(100, 200, 0), 5, "strike", "blue", TS)
        assert len(events) == 1
        assert events[0].casualties == 5

    def test_get_records(self):
        from stochastic_warfare.population.collateral import CollateralEngine
        eng = CollateralEngine(_event_bus())
        eng.record_damage(Position(0, 0, 0), 3, "fire", "blue", TS)
        records = eng.get_records()
        assert len(records) == 1
        assert records[0]["casualties"] == 3

    def test_unknown_side_returns_zero(self):
        from stochastic_warfare.population.collateral import CollateralEngine
        eng = CollateralEngine(_event_bus())
        assert eng.get_cumulative("unknown") == 0

    def test_state_serialization(self):
        from stochastic_warfare.population.collateral import CollateralEngine
        eng = CollateralEngine(_event_bus())
        eng.record_damage(Position(0, 0, 0), 10, "fire", "blue")
        state = eng.get_state()
        assert state["cumulative_by_side"]["blue"] == 10


# ===================================================================
# 12e-4: Civilian HUMINT
# ===================================================================


class TestHumint:
    """CivilianHumintEngine generates tips from civilian population."""

    def test_friendly_pop_generates_tips(self):
        from stochastic_warfare.population.civilians import CivilianDisposition
        from stochastic_warfare.population.humint import CivilianHumintEngine, HumintConfig
        mgr = _make_civilian_manager()
        mgr.register_region(_make_region(
            "r1", population=50000, disposition=CivilianDisposition.FRIENDLY,
        ))
        cfg = HumintConfig(base_tip_rate=5.0, density_scale=10000.0)
        eng = CivilianHumintEngine(mgr, _event_bus(), _rng(), cfg)
        tips = eng.generate_tips(
            enemy_units=[("enemy1", Position(100, 100, 0), "red")],
            dt_hours=1.0,
            timestamp=TS,
        )
        assert len(tips) > 0
        assert all(t["tip_side"] == "blue" for t in tips)

    def test_hostile_pop_warns_enemy(self):
        from stochastic_warfare.population.civilians import CivilianDisposition
        from stochastic_warfare.population.humint import CivilianHumintEngine, HumintConfig
        mgr = _make_civilian_manager()
        mgr.register_region(_make_region(
            "r1", population=50000, disposition=CivilianDisposition.HOSTILE,
        ))
        cfg = HumintConfig(base_tip_rate=5.0)
        eng = CivilianHumintEngine(mgr, _event_bus(), _rng(), cfg)
        tips = eng.generate_tips(
            enemy_units=[("blue1", Position(100, 100, 0), "blue")],
            dt_hours=1.0,
            timestamp=TS,
        )
        assert len(tips) > 0
        assert all(t["tip_side"] == "red" for t in tips)

    def test_neutral_pop_no_tips(self):
        from stochastic_warfare.population.humint import CivilianHumintEngine
        mgr = _make_civilian_manager()
        mgr.register_region(_make_region("r1", population=50000))
        eng = CivilianHumintEngine(mgr, _event_bus(), _rng())
        tips = eng.generate_tips(
            enemy_units=[("e1", Position(0, 0, 0), "red")],
            dt_hours=1.0,
        )
        assert len(tips) == 0

    def test_unit_outside_region_no_tip(self):
        from stochastic_warfare.population.civilians import CivilianDisposition
        from stochastic_warfare.population.humint import CivilianHumintEngine, HumintConfig
        mgr = _make_civilian_manager()
        mgr.register_region(_make_region(
            "r1", radius_m=100.0, population=10000,
            disposition=CivilianDisposition.FRIENDLY,
        ))
        cfg = HumintConfig(base_tip_rate=10.0)
        eng = CivilianHumintEngine(mgr, _event_bus(), _rng(), cfg)
        tips = eng.generate_tips(
            enemy_units=[("e1", Position(50000, 50000, 0), "red")],
            dt_hours=1.0,
        )
        assert len(tips) == 0

    def test_tips_have_position_noise(self):
        from stochastic_warfare.population.civilians import CivilianDisposition
        from stochastic_warfare.population.humint import CivilianHumintEngine, HumintConfig
        mgr = _make_civilian_manager()
        mgr.register_region(_make_region(
            "r1", population=50000, disposition=CivilianDisposition.FRIENDLY,
        ))
        cfg = HumintConfig(base_tip_rate=10.0, position_noise_m=1000.0)
        eng = CivilianHumintEngine(mgr, _event_bus(), _rng(), cfg)
        tips = eng.generate_tips(
            enemy_units=[("e1", Position(100, 100, 0), "red")],
            dt_hours=1.0,
            timestamp=TS,
        )
        if tips:
            # At least one tip should have position different from exact
            offsets = [
                abs(t["reported_position"].easting - 100.0) +
                abs(t["reported_position"].northing - 100.0)
                for t in tips
            ]
            assert any(o > 1.0 for o in offsets)

    def test_publishes_humint_event(self):
        from stochastic_warfare.population.civilians import CivilianDisposition
        from stochastic_warfare.population.events import HumintTipEvent
        from stochastic_warfare.population.humint import CivilianHumintEngine, HumintConfig
        eb = _event_bus()
        events: list = []
        eb.subscribe(HumintTipEvent, lambda e: events.append(e))
        mgr = _make_civilian_manager(event_bus=eb)
        mgr.register_region(_make_region(
            "r1", population=50000, disposition=CivilianDisposition.FRIENDLY,
        ))
        cfg = HumintConfig(base_tip_rate=10.0)
        eng = CivilianHumintEngine(mgr, eb, _rng(), cfg)
        eng.generate_tips(
            enemy_units=[("e1", Position(0, 0, 0), "red")],
            dt_hours=1.0,
            timestamp=TS,
        )
        assert len(events) > 0


# ===================================================================
# 12e-5: Population Disposition Dynamics
# ===================================================================


class TestInfluence:
    """InfluenceEngine drives disposition changes."""

    def test_collateral_shifts_toward_hostile(self):
        from stochastic_warfare.population.civilians import CivilianDisposition
        from stochastic_warfare.population.influence import InfluenceConfig, InfluenceEngine
        mgr = _make_civilian_manager()
        mgr.register_region(_make_region("r1", disposition=CivilianDisposition.NEUTRAL))
        cfg = InfluenceConfig(collateral_hostility_rate=1.0)  # very high
        changed = False
        for seed in range(50):
            mgr2 = _make_civilian_manager(rng=_rng(seed))
            mgr2.register_region(_make_region("r1", disposition=CivilianDisposition.NEUTRAL))
            eng = InfluenceEngine(mgr2, _event_bus(), _rng(seed), cfg)
            changes = eng.update(
                dt_hours=1.0,
                collateral_events={"r1": 100},
            )
            if "r1" in changes:
                assert changes["r1"] == "HOSTILE"
                changed = True
                break
        assert changed, "Expected at least one NEUTRAL→HOSTILE transition"

    def test_aid_shifts_toward_friendly(self):
        from stochastic_warfare.population.civilians import CivilianDisposition
        from stochastic_warfare.population.influence import InfluenceConfig, InfluenceEngine
        changed = False
        for seed in range(50):
            mgr = _make_civilian_manager(rng=_rng(seed))
            mgr.register_region(_make_region("r1", disposition=CivilianDisposition.NEUTRAL))
            cfg = InfluenceConfig(aid_friendliness_rate=1.0)
            eng = InfluenceEngine(mgr, _event_bus(), _rng(seed), cfg)
            changes = eng.update(
                dt_hours=1.0,
                aid_events={"r1": 100},
            )
            if "r1" in changes:
                assert changes["r1"] == "FRIENDLY"
                changed = True
                break
        assert changed, "Expected at least one NEUTRAL→FRIENDLY transition"

    def test_no_events_minimal_change(self):
        from stochastic_warfare.population.influence import InfluenceEngine
        mgr = _make_civilian_manager()
        mgr.register_region(_make_region("r1"))
        eng = InfluenceEngine(mgr, _event_bus(), _rng())
        changes = eng.update(dt_hours=0.001)  # very short step
        # With no events and short dt, change is unlikely
        assert len(changes) == 0

    def test_publishes_disposition_event(self):
        from stochastic_warfare.population.civilians import CivilianDisposition
        from stochastic_warfare.population.events import DispositionChangeEvent
        from stochastic_warfare.population.influence import InfluenceConfig, InfluenceEngine
        eb = _event_bus()
        events: list = []
        eb.subscribe(DispositionChangeEvent, lambda e: events.append(e))
        found = False
        for seed in range(50):
            eb2 = _event_bus()
            ev2: list = []
            eb2.subscribe(DispositionChangeEvent, lambda e: ev2.append(e))
            mgr = _make_civilian_manager(rng=_rng(seed), event_bus=eb2)
            mgr.register_region(_make_region("r1", disposition=CivilianDisposition.NEUTRAL))
            cfg = InfluenceConfig(collateral_hostility_rate=1.0)
            eng = InfluenceEngine(mgr, eb2, _rng(seed), cfg)
            eng.update(dt_hours=1.0, collateral_events={"r1": 50}, timestamp=TS)
            if ev2:
                found = True
                break
        assert found


# ===================================================================
# 12e-6: ROE Escalation Triggers
# ===================================================================


class TestRoeEscalation:
    """evaluate_escalation on RoeEngine."""

    def test_below_threshold_returns_none(self):
        from stochastic_warfare.c2.roe import RoeEngine, RoeLevel
        eng = RoeEngine(_event_bus(), default_level=RoeLevel.WEAPONS_FREE)
        result = eng.evaluate_escalation(cumulative_collateral=10.0, threshold=50.0)
        assert result is None

    def test_free_escalates_to_tight(self):
        from stochastic_warfare.c2.roe import RoeEngine, RoeLevel
        eng = RoeEngine(_event_bus(), default_level=RoeLevel.WEAPONS_FREE)
        result = eng.evaluate_escalation(cumulative_collateral=60.0, threshold=50.0)
        assert result == RoeLevel.WEAPONS_TIGHT

    def test_tight_escalates_to_hold(self):
        from stochastic_warfare.c2.roe import RoeEngine, RoeLevel
        eng = RoeEngine(_event_bus(), default_level=RoeLevel.WEAPONS_TIGHT)
        result = eng.evaluate_escalation(cumulative_collateral=100.0, threshold=50.0)
        assert result == RoeLevel.WEAPONS_HOLD

    def test_hold_returns_none(self):
        from stochastic_warfare.c2.roe import RoeEngine, RoeLevel
        eng = RoeEngine(_event_bus(), default_level=RoeLevel.WEAPONS_HOLD)
        result = eng.evaluate_escalation(cumulative_collateral=200.0, threshold=50.0)
        assert result is None

    def test_exact_threshold_triggers(self):
        from stochastic_warfare.c2.roe import RoeEngine, RoeLevel
        eng = RoeEngine(_event_bus(), default_level=RoeLevel.WEAPONS_FREE)
        result = eng.evaluate_escalation(cumulative_collateral=50.0, threshold=50.0)
        assert result == RoeLevel.WEAPONS_TIGHT


# ===================================================================
# Events
# ===================================================================


class TestPopulationEvents:
    """Population event dataclasses."""

    def test_displacement_event(self):
        from stochastic_warfare.population.events import DisplacementEvent
        e = DisplacementEvent(
            timestamp=TS, source=ModuleId.POPULATION,
            region_id="r1", displaced_count=100,
        )
        assert e.displaced_count == 100

    def test_collateral_event(self):
        from stochastic_warfare.population.events import CollateralDamageEvent
        e = CollateralDamageEvent(
            timestamp=TS, source=ModuleId.POPULATION,
            position=Position(0, 0, 0), casualties=5,
            cause="air_strike", responsible_side="blue",
        )
        assert e.cause == "air_strike"

    def test_disposition_event(self):
        from stochastic_warfare.population.events import DispositionChangeEvent
        e = DispositionChangeEvent(
            timestamp=TS, source=ModuleId.POPULATION,
            region_id="r1", old_disposition="NEUTRAL",
            new_disposition="HOSTILE",
        )
        assert e.new_disposition == "HOSTILE"

    def test_humint_event(self):
        from stochastic_warfare.population.events import HumintTipEvent
        e = HumintTipEvent(
            timestamp=TS, source=ModuleId.POPULATION,
            region_id="r1", target_unit_id="e1",
            reported_position=Position(100, 200, 0),
            reliability=0.5, delay_hours=2.0, tip_side="blue",
        )
        assert e.reliability == 0.5
