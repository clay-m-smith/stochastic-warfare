"""Tests for running estimates engine (c2.planning.estimates).

Uses shared fixtures from conftest.py.
"""

from __future__ import annotations

import pytest

from stochastic_warfare.c2.events import EstimateUpdatedEvent
from stochastic_warfare.c2.planning.estimates import (
    CommsEstimate,
    EstimatesConfig,
    EstimatesEngine,
    EstimateType,
    IntelEstimate,
    LogisticsEstimate,
    OperationsEstimate,
    PersonnelEstimate,
    RunningEstimates,
)
from stochastic_warfare.core.events import EventBus
from tests.conftest import TS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Default "favorable" inputs -- everything healthy
_GOOD_KWARGS: dict = dict(
    strength_ratio=0.9,
    casualty_rate=1.0,
    replacement_available=True,
    confirmed_contacts=3,
    estimated_enemy_strength=100.0,
    intel_coverage=0.8,
    collection_assets=3,
    combat_power_ratio=2.0,
    tempo=2.0,
    objectives_progress=0.5,
    terrain_favorability=0.5,
    supply_level=0.8,
    ammo_level=0.7,
    fuel_level=0.9,
    transport_available=0.9,
    msr_status=1.0,
    network_connectivity=0.9,
    primary_comms_up=True,
    alternate_comms_available=True,
    jamming_threat=0.1,
    ts=TS,
)

# "Unfavorable" inputs -- everything bad
_BAD_KWARGS: dict = dict(
    strength_ratio=0.2,
    casualty_rate=15.0,
    replacement_available=False,
    confirmed_contacts=0,
    estimated_enemy_strength=500.0,
    intel_coverage=0.0,
    collection_assets=0,
    combat_power_ratio=0.3,
    tempo=0.0,
    objectives_progress=0.0,
    terrain_favorability=-1.0,
    supply_level=0.1,
    ammo_level=0.05,
    fuel_level=0.1,
    transport_available=0.1,
    msr_status=0.0,
    network_connectivity=0.1,
    primary_comms_up=False,
    alternate_comms_available=False,
    jamming_threat=0.9,
    ts=TS,
)


def _make_engine(
    event_bus: EventBus | None = None,
    config: EstimatesConfig | None = None,
) -> EstimatesEngine:
    eb = event_bus or EventBus()
    return EstimatesEngine(eb, config)


# ---------------------------------------------------------------------------
# EstimateType enum
# ---------------------------------------------------------------------------


class TestEstimateType:
    def test_personnel_value(self) -> None:
        assert EstimateType.PERSONNEL == 0

    def test_intelligence_value(self) -> None:
        assert EstimateType.INTELLIGENCE == 1

    def test_operations_value(self) -> None:
        assert EstimateType.OPERATIONS == 2

    def test_logistics_value(self) -> None:
        assert EstimateType.LOGISTICS == 3

    def test_communications_value(self) -> None:
        assert EstimateType.COMMUNICATIONS == 4


# ---------------------------------------------------------------------------
# Estimate dataclass creation
# ---------------------------------------------------------------------------


class TestPersonnelEstimate:
    def test_creation_and_fields(self) -> None:
        est = PersonnelEstimate(
            strength_ratio=0.85,
            casualty_rate=2.0,
            replacement_available=True,
            supportability=0.7,
        )
        assert est.strength_ratio == 0.85
        assert est.casualty_rate == 2.0
        assert est.replacement_available is True
        assert est.supportability == 0.7

    def test_frozen(self) -> None:
        est = PersonnelEstimate(0.5, 1.0, False, 0.4)
        with pytest.raises(AttributeError):
            est.supportability = 0.9  # type: ignore[misc]


class TestIntelEstimate:
    def test_creation_and_fields(self) -> None:
        est = IntelEstimate(
            confirmed_contacts=5,
            estimated_enemy_strength=200.0,
            intel_coverage=0.6,
            collection_assets_available=2,
            supportability=0.55,
        )
        assert est.confirmed_contacts == 5
        assert est.estimated_enemy_strength == 200.0
        assert est.intel_coverage == 0.6
        assert est.collection_assets_available == 2
        assert est.supportability == 0.55


class TestOperationsEstimate:
    def test_creation_and_fields(self) -> None:
        est = OperationsEstimate(
            combat_power_ratio=1.5,
            tempo=3.0,
            objectives_progress=0.4,
            terrain_favorability=0.2,
            supportability=0.65,
        )
        assert est.combat_power_ratio == 1.5
        assert est.tempo == 3.0
        assert est.objectives_progress == 0.4
        assert est.terrain_favorability == 0.2
        assert est.supportability == 0.65


class TestLogisticsEstimate:
    def test_creation_and_fields(self) -> None:
        est = LogisticsEstimate(
            supply_level=0.7,
            ammo_level=0.5,
            fuel_level=0.8,
            transport_available=0.9,
            msr_status=1.0,
            supportability=0.72,
        )
        assert est.supply_level == 0.7
        assert est.ammo_level == 0.5
        assert est.fuel_level == 0.8
        assert est.transport_available == 0.9
        assert est.msr_status == 1.0
        assert est.supportability == 0.72


class TestCommsEstimate:
    def test_creation_and_fields(self) -> None:
        est = CommsEstimate(
            network_connectivity=0.8,
            primary_comms_up=True,
            alternate_comms_available=True,
            jamming_threat=0.3,
            supportability=0.77,
        )
        assert est.network_connectivity == 0.8
        assert est.primary_comms_up is True
        assert est.alternate_comms_available is True
        assert est.jamming_threat == 0.3
        assert est.supportability == 0.77


# ---------------------------------------------------------------------------
# RunningEstimates composite
# ---------------------------------------------------------------------------


class TestRunningEstimates:
    def _make(self, sups: tuple[float, float, float, float, float]) -> RunningEstimates:
        """Build a RunningEstimates with given supportabilities."""
        return RunningEstimates(
            unit_id="u1",
            timestamp=TS,
            personnel=PersonnelEstimate(0.9, 1.0, True, sups[0]),
            intelligence=IntelEstimate(3, 100, 0.8, 2, sups[1]),
            operations=OperationsEstimate(2.0, 2.0, 0.5, 0.0, sups[2]),
            logistics=LogisticsEstimate(0.8, 0.7, 0.9, 0.9, 1.0, sups[3]),
            communications=CommsEstimate(0.9, True, True, 0.1, sups[4]),
        )

    def test_overall_supportability_is_min(self) -> None:
        est = self._make((0.8, 0.9, 0.7, 0.85, 0.95))
        assert est.overall_supportability == pytest.approx(0.7)

    def test_overall_bottlenecked_by_worst(self) -> None:
        est = self._make((0.9, 0.9, 0.9, 0.1, 0.9))
        assert est.overall_supportability == pytest.approx(0.1)

    def test_overall_all_equal(self) -> None:
        est = self._make((0.5, 0.5, 0.5, 0.5, 0.5))
        assert est.overall_supportability == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# EstimatesConfig
# ---------------------------------------------------------------------------


class TestEstimatesConfig:
    def test_defaults(self) -> None:
        cfg = EstimatesConfig()
        assert cfg.update_interval_s == 300.0
        assert cfg.significant_change_threshold == 0.10
        assert cfg.personnel_critical == 0.5
        assert cfg.supply_critical == 0.2
        assert cfg.comms_critical == 0.3

    def test_custom_values(self) -> None:
        cfg = EstimatesConfig(update_interval_s=60.0, significant_change_threshold=0.05)
        assert cfg.update_interval_s == 60.0
        assert cfg.significant_change_threshold == 0.05


# ---------------------------------------------------------------------------
# EstimatesEngine -- update_all
# ---------------------------------------------------------------------------


class TestEstimatesEngineUpdateAll:
    def test_creates_estimates(self, event_bus: EventBus) -> None:
        engine = EstimatesEngine(event_bus)
        result = engine.update_all(unit_id="u1", **_GOOD_KWARGS)
        assert isinstance(result, RunningEstimates)
        assert result.unit_id == "u1"
        assert result.timestamp == TS

    def test_personnel_supportability_healthy(self, event_bus: EventBus) -> None:
        engine = EstimatesEngine(event_bus)
        # strength=0.9, casualty_rate=1.0, replacement=True
        # raw = 0.9 * (1 - 1/10) = 0.9 * 0.9 = 0.81 + 0.1 = 0.91
        result = engine.update_all(unit_id="u1", **_GOOD_KWARGS)
        assert result.personnel.supportability == pytest.approx(0.91)

    def test_high_casualty_rate_low_personnel(self, event_bus: EventBus) -> None:
        engine = EstimatesEngine(event_bus)
        kw = dict(_GOOD_KWARGS)
        kw["casualty_rate"] = 12.0  # > 10 clamps to 1.0
        kw["replacement_available"] = False
        # raw = 0.9 * (1 - 1.0) = 0.0
        result = engine.update_all(unit_id="u1", **kw)
        assert result.personnel.supportability == pytest.approx(0.0)

    def test_replacement_boosts_personnel(self, event_bus: EventBus) -> None:
        engine = EstimatesEngine(event_bus)
        kw_no = dict(_GOOD_KWARGS, replacement_available=False)
        kw_yes = dict(_GOOD_KWARGS, replacement_available=True)
        r_no = engine.update_all(unit_id="u_no", **kw_no)
        r_yes = engine.update_all(unit_id="u_yes", **kw_yes)
        assert r_yes.personnel.supportability == pytest.approx(
            r_no.personnel.supportability + 0.1
        )

    def test_intel_supportability(self, event_bus: EventBus) -> None:
        engine = EstimatesEngine(event_bus)
        # coverage=0.8, assets=3, contacts=3
        # raw = 0.8*0.4 + min(1,3/3)*0.3 + 0.3 = 0.32 + 0.3 + 0.3 = 0.92
        result = engine.update_all(unit_id="u1", **_GOOD_KWARGS)
        assert result.intelligence.supportability == pytest.approx(0.92)

    def test_operations_supportability(self, event_bus: EventBus) -> None:
        engine = EstimatesEngine(event_bus)
        # cpr=2.0, terrain=0.5, progress=0.5
        # raw = min(1,2/3)*0.5 + (0.5+1)/2*0.3 + 0.5*0.2
        # = 0.6667*0.5 + 0.75*0.3 + 0.1 = 0.3333 + 0.225 + 0.1 = 0.6583
        result = engine.update_all(unit_id="u1", **_GOOD_KWARGS)
        assert result.operations.supportability == pytest.approx(0.6583, abs=0.001)

    def test_logistics_supportability(self, event_bus: EventBus) -> None:
        engine = EstimatesEngine(event_bus)
        # supply=0.8, ammo=0.7, fuel=0.9 -> min=0.7
        # raw = 0.7*0.5 + 0.9*0.25 + 1.0*0.25 = 0.35 + 0.225 + 0.25 = 0.825
        result = engine.update_all(unit_id="u1", **_GOOD_KWARGS)
        assert result.logistics.supportability == pytest.approx(0.825)

    def test_logistics_bottlenecked_by_worst_supply(self, event_bus: EventBus) -> None:
        engine = EstimatesEngine(event_bus)
        kw = dict(_GOOD_KWARGS, supply_level=0.9, ammo_level=0.1, fuel_level=0.9)
        # min = 0.1 -> 0.1*0.5 + 0.9*0.25 + 1.0*0.25 = 0.05 + 0.225 + 0.25 = 0.525
        result = engine.update_all(unit_id="u1", **kw)
        assert result.logistics.supportability == pytest.approx(0.525)

    def test_comms_supportability(self, event_bus: EventBus) -> None:
        engine = EstimatesEngine(event_bus)
        # connectivity=0.9, primary=True, alt=True, jamming=0.1
        # raw = 0.9*0.5 + 0.25 + 0.15 + (1-0.1)*0.1 = 0.45 + 0.25 + 0.15 + 0.09 = 0.94
        result = engine.update_all(unit_id="u1", **_GOOD_KWARGS)
        assert result.communications.supportability == pytest.approx(0.94)

    def test_comms_with_jamming(self, event_bus: EventBus) -> None:
        engine = EstimatesEngine(event_bus)
        kw = dict(
            _GOOD_KWARGS,
            network_connectivity=0.5,
            primary_comms_up=False,
            alternate_comms_available=False,
            jamming_threat=0.8,
        )
        # raw = 0.5*0.5 + 0 + 0 + (1-0.8)*0.1 = 0.25 + 0.02 = 0.27
        result = engine.update_all(unit_id="u1", **kw)
        assert result.communications.supportability == pytest.approx(0.27)


# ---------------------------------------------------------------------------
# EstimatesEngine -- queries
# ---------------------------------------------------------------------------


class TestEstimatesEngineQueries:
    def test_get_estimates_returns_none_for_unknown(self, event_bus: EventBus) -> None:
        engine = EstimatesEngine(event_bus)
        assert engine.get_estimates("nonexistent") is None

    def test_get_estimates_returns_stored(self, event_bus: EventBus) -> None:
        engine = EstimatesEngine(event_bus)
        engine.update_all(unit_id="u1", **_GOOD_KWARGS)
        est = engine.get_estimates("u1")
        assert est is not None
        assert est.unit_id == "u1"

    def test_check_supportability_returns_overall(self, event_bus: EventBus) -> None:
        engine = EstimatesEngine(event_bus)
        result = engine.update_all(unit_id="u1", **_GOOD_KWARGS)
        assert engine.check_supportability("u1") == pytest.approx(
            result.overall_supportability
        )

    def test_check_supportability_returns_1_for_unknown(self, event_bus: EventBus) -> None:
        engine = EstimatesEngine(event_bus)
        assert engine.check_supportability("nonexistent") == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# EstimatesEngine -- update timing
# ---------------------------------------------------------------------------


class TestEstimatesEngineTiming:
    def test_should_update_true_when_interval_exceeded(self, event_bus: EventBus) -> None:
        engine = EstimatesEngine(event_bus)
        assert engine.should_update("u1", elapsed_s=301.0) is True

    def test_should_update_false_when_recently_updated(self, event_bus: EventBus) -> None:
        engine = EstimatesEngine(event_bus)
        assert engine.should_update("u1", elapsed_s=100.0) is False

    def test_should_update_exact_boundary(self, event_bus: EventBus) -> None:
        engine = EstimatesEngine(event_bus)
        assert engine.should_update("u1", elapsed_s=300.0) is True

    def test_mark_updated_resets_timer(self, event_bus: EventBus) -> None:
        engine = EstimatesEngine(event_bus)
        # Accumulate time so should_update is True
        assert engine.should_update("u1", elapsed_s=301.0) is True
        # Mark as updated -- now needs full interval again
        engine.mark_updated("u1")
        assert engine.should_update("u1", elapsed_s=100.0) is False


# ---------------------------------------------------------------------------
# EstimatesEngine -- events
# ---------------------------------------------------------------------------


class TestEstimatesEngineEvents:
    def test_significant_change_publishes_event(self, event_bus: EventBus) -> None:
        engine = EstimatesEngine(event_bus)
        events_received: list[EstimateUpdatedEvent] = []
        event_bus.subscribe(EstimateUpdatedEvent, events_received.append)

        # First update -- no previous, no events
        engine.update_all(unit_id="u1", **_GOOD_KWARGS)
        assert len(events_received) == 0

        # Second update with significant personnel change
        kw2 = dict(_GOOD_KWARGS, strength_ratio=0.3, casualty_rate=8.0)
        engine.update_all(unit_id="u1", **kw2)
        # Personnel supportability dropped significantly
        pers_events = [e for e in events_received if e.estimate_type == "PERSONNEL"]
        assert len(pers_events) >= 1
        assert pers_events[0].unit_id == "u1"

    def test_no_event_below_threshold(self, event_bus: EventBus) -> None:
        engine = EstimatesEngine(event_bus)
        events_received: list[EstimateUpdatedEvent] = []
        event_bus.subscribe(EstimateUpdatedEvent, events_received.append)

        # First update
        engine.update_all(unit_id="u1", **_GOOD_KWARGS)
        assert len(events_received) == 0

        # Very minor change -- strength from 0.9 to 0.88
        kw2 = dict(_GOOD_KWARGS, strength_ratio=0.88)
        engine.update_all(unit_id="u1", **kw2)
        # Change: 0.9*0.9+0.1=0.91 vs 0.88*0.9+0.1=0.892 -> delta=0.018 < 0.10
        assert len(events_received) == 0

    def test_no_event_on_first_update(self, event_bus: EventBus) -> None:
        engine = EstimatesEngine(event_bus)
        events_received: list[EstimateUpdatedEvent] = []
        event_bus.subscribe(EstimateUpdatedEvent, events_received.append)

        engine.update_all(unit_id="u1", **_GOOD_KWARGS)
        assert len(events_received) == 0


# ---------------------------------------------------------------------------
# EstimatesEngine -- multiple units
# ---------------------------------------------------------------------------


class TestEstimatesEngineMultiUnit:
    def test_multiple_units_dont_interfere(self, event_bus: EventBus) -> None:
        engine = EstimatesEngine(event_bus)
        r1 = engine.update_all(unit_id="u1", **_GOOD_KWARGS)
        r2 = engine.update_all(unit_id="u2", **_BAD_KWARGS)

        assert engine.get_estimates("u1") is r1
        assert engine.get_estimates("u2") is r2
        assert r1.overall_supportability > r2.overall_supportability


# ---------------------------------------------------------------------------
# EstimatesEngine -- extreme inputs
# ---------------------------------------------------------------------------


class TestEstimatesEngineExtremes:
    def test_all_favorable_high_supportability(self, event_bus: EventBus) -> None:
        engine = EstimatesEngine(event_bus)
        result = engine.update_all(unit_id="u1", **_GOOD_KWARGS)
        assert result.overall_supportability > 0.5

    def test_all_unfavorable_low_supportability(self, event_bus: EventBus) -> None:
        engine = EstimatesEngine(event_bus)
        result = engine.update_all(unit_id="u1", **_BAD_KWARGS)
        assert result.overall_supportability < 0.2


# ---------------------------------------------------------------------------
# State protocol
# ---------------------------------------------------------------------------


class TestEstimatesEngineState:
    def test_get_set_state_round_trip(self, event_bus: EventBus) -> None:
        engine = EstimatesEngine(event_bus)
        engine.update_all(unit_id="u1", **_GOOD_KWARGS)
        engine.mark_updated("u1")

        state = engine.get_state()

        # Restore into a fresh engine
        engine2 = EstimatesEngine(event_bus)
        engine2.set_state(state)

        est1 = engine.get_estimates("u1")
        est2 = engine2.get_estimates("u1")
        assert est1 is not None
        assert est2 is not None
        assert est1.unit_id == est2.unit_id
        assert est1.personnel.supportability == pytest.approx(
            est2.personnel.supportability
        )
        assert est1.intelligence.supportability == pytest.approx(
            est2.intelligence.supportability
        )
        assert est1.operations.supportability == pytest.approx(
            est2.operations.supportability
        )
        assert est1.logistics.supportability == pytest.approx(
            est2.logistics.supportability
        )
        assert est1.communications.supportability == pytest.approx(
            est2.communications.supportability
        )
        assert est1.overall_supportability == pytest.approx(
            est2.overall_supportability
        )

    def test_state_preserves_previous_supportability(self, event_bus: EventBus) -> None:
        """After restore, significant-change detection still works."""
        engine = EstimatesEngine(event_bus)
        engine.update_all(unit_id="u1", **_GOOD_KWARGS)
        state = engine.get_state()

        engine2 = EstimatesEngine(event_bus)
        engine2.set_state(state)

        events_received: list[EstimateUpdatedEvent] = []
        event_bus.subscribe(EstimateUpdatedEvent, events_received.append)

        # Big change should trigger event even on restored engine
        engine2.update_all(unit_id="u1", **_BAD_KWARGS)
        assert len(events_received) > 0
