"""Phase 24a tests — Escalation Ladder, Political Pressure, Consequences.

Covers:
* EscalationLadder — desperation index computation, escalation/de-escalation
  transitions, cooldown enforcement, personality modulation, authorization
* PoliticalPressureEngine — international/domestic pressure accumulation,
  decay, existential threat suppression, threshold-based effects
* ConsequenceEngine — war crime consequences, prohibited weapons, prisoner
  mistreatment, documented multiplier, Bernoulli spiral
* Events — all 8 frozen dataclass event types
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from tests.conftest import TS

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.types import ModuleId, Position

from stochastic_warfare.escalation.events import (
    CivilianAtrocityEvent,
    CoalitionFractureEvent,
    EscalationLevelChangeEvent,
    PoliticalPressureChangeEvent,
    PrisonerMistreatmentEvent,
    ProhibitedWeaponEmployedEvent,
    ScorchedEarthEvent,
    WarCrimeRecordedEvent,
)
from stochastic_warfare.escalation.ladder import (
    DesperationWeights,
    EscalationLadder,
    EscalationLadderConfig,
    EscalationLevel,
)
from stochastic_warfare.escalation.political import (
    PoliticalEffect,
    PoliticalPressureConfig,
    PoliticalPressureEngine,
    PoliticalPressureState,
)
from stochastic_warfare.escalation.consequences import (
    ConsequenceConfig,
    ConsequenceEngine,
    ConsequenceResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

POS = Position(1000.0, 2000.0, 0.0)


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.default_rng(seed)


def _ts(offset_s: float = 0.0) -> datetime:
    return TS + timedelta(seconds=offset_s)


# ===========================================================================
# Section 1: EscalationLadder (~20 tests)
# ===========================================================================


class TestEscalationLevel:
    """Validate EscalationLevel enum values."""

    def test_conventional_is_zero(self) -> None:
        assert EscalationLevel.CONVENTIONAL == 0

    def test_strategic_nuclear_general_is_ten(self) -> None:
        assert EscalationLevel.STRATEGIC_NUCLEAR_GENERAL == 10

    def test_all_levels_sequential(self) -> None:
        for i, level in enumerate(EscalationLevel):
            assert level.value == i


class TestDesperationIndex:
    """Validate desperation index computation."""

    def test_all_zero_factors(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        ladder = EscalationLadder(event_bus, rng)
        d = ladder.compute_desperation(
            "blue", casualties_sustained=0, initial_strength=100,
            supply_state=1.0, avg_morale=1.0, stalemate_duration_s=0,
            domestic_pressure=0.0,
        )
        assert d == pytest.approx(0.0)

    def test_all_max_factors(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        ladder = EscalationLadder(event_bus, rng)
        d = ladder.compute_desperation(
            "blue", casualties_sustained=200, initial_strength=100,
            supply_state=0.0, avg_morale=0.0, stalemate_duration_s=1e9,
            domestic_pressure=1.0,
        )
        assert d == pytest.approx(1.0)

    def test_casualty_factor_only(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        ladder = EscalationLadder(event_bus, rng)
        d = ladder.compute_desperation(
            "blue", casualties_sustained=50, initial_strength=100,
            supply_state=1.0, avg_morale=1.0, stalemate_duration_s=0,
            domestic_pressure=0.0,
        )
        # casualty_factor = 50/100 = 0.5, weight = 0.30
        assert d == pytest.approx(0.30 * 0.5)

    def test_supply_factor_only(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        ladder = EscalationLadder(event_bus, rng)
        d = ladder.compute_desperation(
            "blue", casualties_sustained=0, initial_strength=100,
            supply_state=0.3, avg_morale=1.0, stalemate_duration_s=0,
            domestic_pressure=0.0,
        )
        # supply_factor = 1 - 0.3 = 0.7, weight = 0.20
        assert d == pytest.approx(0.20 * 0.7)

    def test_morale_factor_only(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        ladder = EscalationLadder(event_bus, rng)
        d = ladder.compute_desperation(
            "blue", casualties_sustained=0, initial_strength=100,
            supply_state=1.0, avg_morale=0.4, stalemate_duration_s=0,
            domestic_pressure=0.0,
        )
        # morale_factor = 1 - 0.4 = 0.6, weight = 0.20
        assert d == pytest.approx(0.20 * 0.6)

    def test_stalemate_factor_only(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        ladder = EscalationLadder(event_bus, rng)
        w = DesperationWeights()
        d = ladder.compute_desperation(
            "blue", casualties_sustained=0, initial_strength=100,
            supply_state=1.0, avg_morale=1.0,
            stalemate_duration_s=w.stalemate_normalize_s / 2.0,
            domestic_pressure=0.0,
        )
        # stalemate_factor = 0.5, weight = 0.15
        assert d == pytest.approx(0.15 * 0.5)

    def test_political_factor_only(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        ladder = EscalationLadder(event_bus, rng)
        d = ladder.compute_desperation(
            "blue", casualties_sustained=0, initial_strength=100,
            supply_state=1.0, avg_morale=1.0, stalemate_duration_s=0,
            domestic_pressure=0.8,
        )
        # political_factor = 0.8, weight = 0.15
        assert d == pytest.approx(0.15 * 0.8)

    def test_combined_factors(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        ladder = EscalationLadder(event_bus, rng)
        d = ladder.compute_desperation(
            "blue", casualties_sustained=30, initial_strength=100,
            supply_state=0.5, avg_morale=0.6, stalemate_duration_s=129600,
            domestic_pressure=0.4,
        )
        # casualty = 0.30 * 0.3, supply = 0.20 * 0.5, morale = 0.20 * 0.4,
        # stalemate = 0.15 * 0.5, political = 0.15 * 0.4
        expected = 0.30 * 0.3 + 0.20 * 0.5 + 0.20 * 0.4 + 0.15 * 0.5 + 0.15 * 0.4
        assert d == pytest.approx(expected)

    def test_clamping_at_zero(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        ladder = EscalationLadder(event_bus, rng)
        d = ladder.compute_desperation(
            "blue", casualties_sustained=0, initial_strength=100,
            supply_state=1.5, avg_morale=1.5, stalemate_duration_s=0,
            domestic_pressure=-0.5,
        )
        assert d >= 0.0

    def test_initial_strength_zero_safe(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        ladder = EscalationLadder(event_bus, rng)
        # Should not divide by zero
        d = ladder.compute_desperation(
            "blue", casualties_sustained=10, initial_strength=0,
            supply_state=1.0, avg_morale=1.0, stalemate_duration_s=0,
            domestic_pressure=0.0,
        )
        assert d >= 0.0


class TestEscalationTransitions:
    """Validate escalation/de-escalation logic."""

    def test_step_up_when_desperate(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        ladder = EscalationLadder(event_bus, rng)
        # Level 1 threshold = 0.15 / (1 + 0) = 0.15. desperation=0.20 > 0.15
        result = ladder.evaluate_transition(
            "blue", desperation=0.20, commander_violation_tolerance=0.0,
            commander_escalation_awareness=0.0, timestamp=_ts(),
        )
        assert result is not None
        assert result == EscalationLevel.ROE_RELAXATION
        assert ladder.get_level("blue") == EscalationLevel.ROE_RELAXATION

    def test_no_transition_below_threshold(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        ladder = EscalationLadder(event_bus, rng)
        result = ladder.evaluate_transition(
            "blue", desperation=0.10, commander_violation_tolerance=0.0,
            commander_escalation_awareness=0.0, timestamp=_ts(),
        )
        assert result is None
        assert ladder.get_level("blue") == EscalationLevel.CONVENTIONAL

    def test_hysteresis_prevents_immediate_deescalation(
        self, event_bus: EventBus, rng: np.random.Generator,
    ) -> None:
        ladder = EscalationLadder(event_bus, rng)
        # Step up first
        ladder.evaluate_transition(
            "blue", desperation=0.20, commander_violation_tolerance=0.0,
            commander_escalation_awareness=0.0, timestamp=_ts(0),
        )
        assert ladder.get_level("blue") == EscalationLevel.ROE_RELAXATION

        # Desperation drops slightly but above exit threshold (0.15 * 0.7 = 0.105)
        result = ladder.evaluate_transition(
            "blue", desperation=0.12, commander_violation_tolerance=0.0,
            commander_escalation_awareness=0.0, timestamp=_ts(7200),
        )
        assert result is None
        assert ladder.get_level("blue") == EscalationLevel.ROE_RELAXATION

    def test_deescalation_below_exit_threshold(
        self, event_bus: EventBus, rng: np.random.Generator,
    ) -> None:
        ladder = EscalationLadder(event_bus, rng)
        # Step up first
        ladder.evaluate_transition(
            "blue", desperation=0.20, commander_violation_tolerance=0.0,
            commander_escalation_awareness=0.0, timestamp=_ts(0),
        )
        assert ladder.get_level("blue") == EscalationLevel.ROE_RELAXATION

        # Drop below exit threshold (0.15 * 0.7 = 0.105) after cooldown
        result = ladder.evaluate_transition(
            "blue", desperation=0.05, commander_violation_tolerance=0.0,
            commander_escalation_awareness=0.0, timestamp=_ts(7200),
        )
        assert result == EscalationLevel.CONVENTIONAL
        assert ladder.get_level("blue") == EscalationLevel.CONVENTIONAL

    def test_cooldown_blocks_rapid_transition(
        self, event_bus: EventBus, rng: np.random.Generator,
    ) -> None:
        ladder = EscalationLadder(event_bus, rng)
        # First transition
        ladder.evaluate_transition(
            "blue", desperation=0.20, commander_violation_tolerance=0.0,
            commander_escalation_awareness=0.0, timestamp=_ts(0),
        )
        # Immediate second attempt (within cooldown)
        result = ladder.evaluate_transition(
            "blue", desperation=0.30, commander_violation_tolerance=0.0,
            commander_escalation_awareness=0.0, timestamp=_ts(100),
        )
        assert result is None

    def test_violation_tolerance_lowers_threshold(
        self, event_bus: EventBus, rng: np.random.Generator,
    ) -> None:
        ladder = EscalationLadder(event_bus, rng)
        # With tolerance=1.0, threshold for level 1 = 0.15 / (1+1) = 0.075
        result = ladder.evaluate_transition(
            "blue", desperation=0.10, commander_violation_tolerance=1.0,
            commander_escalation_awareness=0.0, timestamp=_ts(),
        )
        assert result is not None
        assert result.value >= 1

    def test_escalation_awareness_inhibits(
        self, event_bus: EventBus, rng: np.random.Generator,
    ) -> None:
        ladder = EscalationLadder(event_bus, rng)
        # Without awareness, desperation=0.20 > threshold=0.15 → escalate
        # With awareness=1.0, consequence_cost for level 1 = 1*0.1*1.0 = 0.1
        # effective = 0.20 - 0.10 = 0.10, still < 0.15? No, 0.10 < 0.15
        result = ladder.evaluate_transition(
            "blue", desperation=0.20, commander_violation_tolerance=0.0,
            commander_escalation_awareness=1.0, timestamp=_ts(),
        )
        assert result is None

    def test_publishes_event_on_transition(
        self, event_bus: EventBus, rng: np.random.Generator,
    ) -> None:
        events_received: list[Event] = []
        event_bus.subscribe(EscalationLevelChangeEvent, events_received.append)
        ladder = EscalationLadder(event_bus, rng)
        ladder.evaluate_transition(
            "blue", desperation=0.20, commander_violation_tolerance=0.0,
            commander_escalation_awareness=0.0, timestamp=_ts(),
        )
        assert len(events_received) == 1
        evt = events_received[0]
        assert isinstance(evt, EscalationLevelChangeEvent)
        assert evt.side == "blue"
        assert evt.old_level == 0
        assert evt.new_level == 1

    def test_is_authorized(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        ladder = EscalationLadder(event_bus, rng)
        ladder.set_level("blue", EscalationLevel.CHEMICAL)
        assert ladder.is_authorized(EscalationLevel.CONVENTIONAL, "blue")
        assert ladder.is_authorized(EscalationLevel.CHEMICAL, "blue")
        assert not ladder.is_authorized(EscalationLevel.BIOLOGICAL, "blue")

    def test_state_roundtrip(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        ladder = EscalationLadder(event_bus, rng)
        ladder.set_level("blue", EscalationLevel.ROE_VIOLATIONS)
        ladder.evaluate_transition(
            "blue", desperation=0.80, commander_violation_tolerance=0.0,
            commander_escalation_awareness=0.0, timestamp=_ts(),
        )
        state = ladder.get_state()
        ladder2 = EscalationLadder(event_bus, rng)
        ladder2.set_state(state)
        assert ladder2.get_level("blue") == ladder.get_level("blue")

    def test_default_level_conventional(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        ladder = EscalationLadder(event_bus, rng)
        assert ladder.get_level("unknown_side") == EscalationLevel.CONVENTIONAL

    def test_multi_step_escalation(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """Very high desperation can jump multiple levels."""
        ladder = EscalationLadder(event_bus, rng)
        # desperation=0.95, tolerance=0, awareness=0
        # Scans from level 10 down. Level 10 threshold = 0.95.
        # 0.95 > 0.95 is false. Level 9 threshold = 0.90. 0.95 > 0.90 → yes.
        result = ladder.evaluate_transition(
            "blue", desperation=0.96, commander_violation_tolerance=0.0,
            commander_escalation_awareness=0.0, timestamp=_ts(),
        )
        assert result is not None
        assert result.value >= 9


# ===========================================================================
# Section 2: PoliticalPressureEngine (~20 tests)
# ===========================================================================


class TestPoliticalPressureInternational:
    """International pressure accumulation and decay."""

    def test_war_crimes_increase_international(self, event_bus: EventBus) -> None:
        engine = PoliticalPressureEngine(event_bus)
        state = engine.update(
            "blue", dt_hours=1.0, war_crime_count=5, civilian_casualties=0,
            prohibited_weapon_events=0, media_visibility=0.0,
            own_casualties=0, stalemate_indicator=0.0,
            enemy_psyop_effectiveness=0.0, perceived_existential_threat=0.0,
            timestamp=_ts(),
        )
        # growth = 1.0 * (0.05 * 5) = 0.25. decay = 0.01 * 1.0 = 0.01
        assert state.international == pytest.approx(0.25 - 0.01)

    def test_collateral_increases_international(self, event_bus: EventBus) -> None:
        engine = PoliticalPressureEngine(event_bus)
        state = engine.update(
            "blue", dt_hours=1.0, war_crime_count=0, civilian_casualties=200,
            prohibited_weapon_events=0, media_visibility=0.0,
            own_casualties=0, stalemate_indicator=0.0,
            enemy_psyop_effectiveness=0.0, perceived_existential_threat=0.0,
            timestamp=_ts(),
        )
        # growth = 1.0 * (0.002 * 200/100) = 0.004. decay = 0.01
        assert state.international == pytest.approx(max(0.0, 0.004 - 0.01))

    def test_prohibited_weapons_increase_international(self, event_bus: EventBus) -> None:
        engine = PoliticalPressureEngine(event_bus)
        state = engine.update(
            "blue", dt_hours=1.0, war_crime_count=0, civilian_casualties=0,
            prohibited_weapon_events=3, media_visibility=0.0,
            own_casualties=0, stalemate_indicator=0.0,
            enemy_psyop_effectiveness=0.0, perceived_existential_threat=0.0,
            timestamp=_ts(),
        )
        # growth = 1.0 * (0.10 * 3) = 0.30. decay = 0.01
        assert state.international == pytest.approx(0.30 - 0.01)

    def test_media_visibility_increases_international(self, event_bus: EventBus) -> None:
        engine = PoliticalPressureEngine(event_bus)
        state = engine.update(
            "blue", dt_hours=1.0, war_crime_count=0, civilian_casualties=0,
            prohibited_weapon_events=0, media_visibility=1.0,
            own_casualties=0, stalemate_indicator=0.0,
            enemy_psyop_effectiveness=0.0, perceived_existential_threat=0.0,
            timestamp=_ts(),
        )
        # growth = 1.0 * (0.03 * 1.0) = 0.03. decay = 0.01
        assert state.international == pytest.approx(0.03 - 0.01)

    def test_international_decay_over_time(self, event_bus: EventBus) -> None:
        engine = PoliticalPressureEngine(event_bus)
        # Build up some pressure
        engine.update(
            "blue", dt_hours=1.0, war_crime_count=10, civilian_casualties=0,
            prohibited_weapon_events=0, media_visibility=0.0,
            own_casualties=0, stalemate_indicator=0.0,
            enemy_psyop_effectiveness=0.0, perceived_existential_threat=0.0,
            timestamp=_ts(0),
        )
        p_before = engine.get_international("blue")
        # Now let it decay (no new crimes)
        engine.update(
            "blue", dt_hours=10.0, war_crime_count=0, civilian_casualties=0,
            prohibited_weapon_events=0, media_visibility=0.0,
            own_casualties=0, stalemate_indicator=0.0,
            enemy_psyop_effectiveness=0.0, perceived_existential_threat=0.0,
            timestamp=_ts(36000),
        )
        p_after = engine.get_international("blue")
        assert p_after < p_before

    def test_international_clamped_at_one(self, event_bus: EventBus) -> None:
        engine = PoliticalPressureEngine(event_bus)
        state = engine.update(
            "blue", dt_hours=100.0, war_crime_count=100, civilian_casualties=10000,
            prohibited_weapon_events=100, media_visibility=1.0,
            own_casualties=0, stalemate_indicator=0.0,
            enemy_psyop_effectiveness=0.0, perceived_existential_threat=0.0,
            timestamp=_ts(),
        )
        assert state.international <= 1.0


class TestPoliticalPressureDomestic:
    """Domestic pressure accumulation, suppression, and decay."""

    def test_own_casualties_increase_domestic(self, event_bus: EventBus) -> None:
        engine = PoliticalPressureEngine(event_bus)
        state = engine.update(
            "blue", dt_hours=1.0, war_crime_count=0, civilian_casualties=0,
            prohibited_weapon_events=0, media_visibility=0.0,
            own_casualties=100, stalemate_indicator=0.0,
            enemy_psyop_effectiveness=0.0, perceived_existential_threat=0.0,
            timestamp=_ts(),
        )
        # growth = 1.0 * (0.003 * 100) = 0.30. decay = 0.005
        assert state.domestic == pytest.approx(0.30 - 0.005)

    def test_stalemate_increases_domestic(self, event_bus: EventBus) -> None:
        engine = PoliticalPressureEngine(event_bus)
        state = engine.update(
            "blue", dt_hours=1.0, war_crime_count=0, civilian_casualties=0,
            prohibited_weapon_events=0, media_visibility=0.0,
            own_casualties=0, stalemate_indicator=1.0,
            enemy_psyop_effectiveness=0.0, perceived_existential_threat=0.0,
            timestamp=_ts(),
        )
        # growth = 1.0 * (0.02 * 1.0) = 0.02. decay = 0.005
        assert state.domestic == pytest.approx(0.02 - 0.005)

    def test_propaganda_increases_domestic(self, event_bus: EventBus) -> None:
        engine = PoliticalPressureEngine(event_bus)
        state = engine.update(
            "blue", dt_hours=1.0, war_crime_count=0, civilian_casualties=0,
            prohibited_weapon_events=0, media_visibility=0.0,
            own_casualties=0, stalemate_indicator=0.0,
            enemy_psyop_effectiveness=1.0, perceived_existential_threat=0.0,
            timestamp=_ts(),
        )
        # growth = 1.0 * (0.01 * 1.0) = 0.01. decay = 0.005
        assert state.domestic == pytest.approx(0.01 - 0.005)

    def test_existential_threat_suppresses_domestic(self, event_bus: EventBus) -> None:
        engine = PoliticalPressureEngine(event_bus)
        # Without existential threat
        state_no_threat = engine.update(
            "blue", dt_hours=1.0, war_crime_count=0, civilian_casualties=0,
            prohibited_weapon_events=0, media_visibility=0.0,
            own_casualties=50, stalemate_indicator=0.0,
            enemy_psyop_effectiveness=0.0, perceived_existential_threat=0.0,
            timestamp=_ts(0),
        )
        dom_no_threat = state_no_threat.domestic

        # Reset for clean comparison
        engine2 = PoliticalPressureEngine(event_bus)
        state_threat = engine2.update(
            "blue", dt_hours=1.0, war_crime_count=0, civilian_casualties=0,
            prohibited_weapon_events=0, media_visibility=0.0,
            own_casualties=50, stalemate_indicator=0.0,
            enemy_psyop_effectiveness=0.0, perceived_existential_threat=1.0,
            timestamp=_ts(0),
        )
        dom_threat = state_threat.domestic

        assert dom_threat < dom_no_threat

    def test_domestic_clamped_at_zero(self, event_bus: EventBus) -> None:
        engine = PoliticalPressureEngine(event_bus)
        state = engine.update(
            "blue", dt_hours=1.0, war_crime_count=0, civilian_casualties=0,
            prohibited_weapon_events=0, media_visibility=0.0,
            own_casualties=0, stalemate_indicator=0.0,
            enemy_psyop_effectiveness=0.0, perceived_existential_threat=1.0,
            timestamp=_ts(),
        )
        assert state.domestic >= 0.0

    def test_domestic_decay_over_time(self, event_bus: EventBus) -> None:
        engine = PoliticalPressureEngine(event_bus)
        engine.update(
            "blue", dt_hours=1.0, war_crime_count=0, civilian_casualties=0,
            prohibited_weapon_events=0, media_visibility=0.0,
            own_casualties=200, stalemate_indicator=0.0,
            enemy_psyop_effectiveness=0.0, perceived_existential_threat=0.0,
            timestamp=_ts(0),
        )
        p_before = engine.get_domestic("blue")
        engine.update(
            "blue", dt_hours=10.0, war_crime_count=0, civilian_casualties=0,
            prohibited_weapon_events=0, media_visibility=0.0,
            own_casualties=0, stalemate_indicator=0.0,
            enemy_psyop_effectiveness=0.0, perceived_existential_threat=0.0,
            timestamp=_ts(36000),
        )
        p_after = engine.get_domestic("blue")
        assert p_after < p_before


class TestPoliticalEffects:
    """Threshold-based effect evaluation."""

    def test_no_effects_at_zero(self, event_bus: EventBus) -> None:
        engine = PoliticalPressureEngine(event_bus)
        effects = engine.evaluate_effects("blue")
        assert effects == []

    def test_supply_constraint_at_threshold(self, event_bus: EventBus) -> None:
        engine = PoliticalPressureEngine(event_bus)
        engine._international["blue"] = 0.3
        effects = engine.evaluate_effects("blue")
        assert PoliticalEffect.SUPPLY_CONSTRAINT in effects

    def test_coalition_fracture_at_threshold(self, event_bus: EventBus) -> None:
        engine = PoliticalPressureEngine(event_bus)
        engine._international["blue"] = 0.5
        effects = engine.evaluate_effects("blue")
        assert PoliticalEffect.COALITION_FRACTURE_RISK in effects

    def test_forced_roe_at_threshold(self, event_bus: EventBus) -> None:
        engine = PoliticalPressureEngine(event_bus)
        engine._international["blue"] = 0.7
        effects = engine.evaluate_effects("blue")
        assert PoliticalEffect.FORCED_ROE_TIGHTENING in effects

    def test_war_termination_at_threshold(self, event_bus: EventBus) -> None:
        engine = PoliticalPressureEngine(event_bus)
        engine._international["blue"] = 0.9
        effects = engine.evaluate_effects("blue")
        assert PoliticalEffect.WAR_TERMINATION_PRESSURE in effects

    def test_roe_loosening_domestic(self, event_bus: EventBus) -> None:
        engine = PoliticalPressureEngine(event_bus)
        engine._domestic["blue"] = 0.3
        effects = engine.evaluate_effects("blue")
        assert PoliticalEffect.ROE_LOOSENING_AUTHORIZED in effects

    def test_escalation_auth_domestic(self, event_bus: EventBus) -> None:
        engine = PoliticalPressureEngine(event_bus)
        engine._domestic["blue"] = 0.5
        effects = engine.evaluate_effects("blue")
        assert PoliticalEffect.ESCALATION_AUTHORIZED in effects

    def test_high_international_cascading_effects(self, event_bus: EventBus) -> None:
        engine = PoliticalPressureEngine(event_bus)
        engine._international["blue"] = 0.95
        effects = engine.evaluate_effects("blue")
        # Should have all international effects
        assert PoliticalEffect.SUPPLY_CONSTRAINT in effects
        assert PoliticalEffect.COALITION_FRACTURE_RISK in effects
        assert PoliticalEffect.FORCED_ROE_TIGHTENING in effects
        assert PoliticalEffect.WAR_TERMINATION_PRESSURE in effects

    def test_update_returns_state_with_effects(self, event_bus: EventBus) -> None:
        cfg = PoliticalPressureConfig(k_int_decay=0.0)
        engine = PoliticalPressureEngine(event_bus, config=cfg)
        state = engine.update(
            "blue", dt_hours=1.0, war_crime_count=20, civilian_casualties=0,
            prohibited_weapon_events=0, media_visibility=0.0,
            own_casualties=0, stalemate_indicator=0.0,
            enemy_psyop_effectiveness=0.0, perceived_existential_threat=0.0,
            timestamp=_ts(),
        )
        assert isinstance(state, PoliticalPressureState)
        # 20 * 0.05 * 1.0 = 1.0 → clamped to 1.0
        assert state.international == pytest.approx(1.0)
        assert PoliticalEffect.WAR_TERMINATION_PRESSURE in state.effects


class TestPoliticalPressureState:
    """State roundtrip."""

    def test_state_roundtrip(self, event_bus: EventBus) -> None:
        engine = PoliticalPressureEngine(event_bus)
        engine._international["blue"] = 0.45
        engine._domestic["blue"] = 0.22
        state = engine.get_state()
        engine2 = PoliticalPressureEngine(event_bus)
        engine2.set_state(state)
        assert engine2.get_international("blue") == pytest.approx(0.45)
        assert engine2.get_domestic("blue") == pytest.approx(0.22)

    def test_publishes_event_on_change(self, event_bus: EventBus) -> None:
        events_received: list[Event] = []
        event_bus.subscribe(PoliticalPressureChangeEvent, events_received.append)
        engine = PoliticalPressureEngine(event_bus)
        engine.update(
            "blue", dt_hours=1.0, war_crime_count=5, civilian_casualties=0,
            prohibited_weapon_events=0, media_visibility=0.0,
            own_casualties=100, stalemate_indicator=0.0,
            enemy_psyop_effectiveness=0.0, perceived_existential_threat=0.0,
            timestamp=_ts(),
        )
        assert len(events_received) == 1
        evt = events_received[0]
        assert isinstance(evt, PoliticalPressureChangeEvent)
        assert evt.side == "blue"
        assert evt.old_international == 0.0
        assert evt.new_international > 0.0


# ===========================================================================
# Section 3: ConsequenceEngine (~15 tests)
# ===========================================================================


class TestWarCrimeConsequences:
    """War crime processing."""

    def test_own_morale_penalty(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = ConsequenceEngine(event_bus, rng)
        result = engine.process_war_crime(
            "targeting_civilians", "blue", severity=1.0, position=POS, timestamp=_ts(),
        )
        assert result.own_morale_delta == pytest.approx(-0.05)

    def test_enemy_hardening(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = ConsequenceEngine(event_bus, rng)
        result = engine.process_war_crime(
            "targeting_civilians", "blue", severity=1.0, position=POS, timestamp=_ts(),
        )
        assert result.enemy_morale_delta == pytest.approx(0.03)

    def test_civilian_hostility(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = ConsequenceEngine(event_bus, rng)
        result = engine.process_war_crime(
            "targeting_civilians", "blue", severity=1.0, position=POS, timestamp=_ts(),
        )
        assert result.civilian_hostility_delta == pytest.approx(0.10)

    def test_severity_scaling(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = ConsequenceEngine(event_bus, rng)
        result = engine.process_war_crime(
            "looting", "blue", severity=0.5, position=POS, timestamp=_ts(),
        )
        assert result.own_morale_delta == pytest.approx(-0.05 * 0.5)
        assert result.enemy_morale_delta == pytest.approx(0.03 * 0.5)
        assert result.civilian_hostility_delta == pytest.approx(0.10 * 0.5)

    def test_publishes_war_crime_event(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        events_received: list[Event] = []
        event_bus.subscribe(WarCrimeRecordedEvent, events_received.append)
        engine = ConsequenceEngine(event_bus, rng)
        engine.process_war_crime(
            "torture", "red", severity=0.8, position=POS, timestamp=_ts(),
        )
        assert len(events_received) == 1
        evt = events_received[0]
        assert isinstance(evt, WarCrimeRecordedEvent)
        assert evt.responsible_side == "red"
        assert evt.crime_type == "torture"
        assert evt.severity == pytest.approx(0.8)

    def test_crime_count_increments(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = ConsequenceEngine(event_bus, rng)
        engine.process_war_crime("a", "blue", 0.5, POS, _ts(0))
        engine.process_war_crime("b", "blue", 0.5, POS, _ts(1))
        assert engine.get_crime_count("blue") == 2
        assert engine.get_crime_count("red") == 0


class TestProhibitedWeaponConsequences:
    """Prohibited weapon processing."""

    def test_severity_from_casualties(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = ConsequenceEngine(event_bus, rng)
        result = engine.process_prohibited_weapon(
            "VX-launcher", "VX-round", "blue", civilian_casualties=50,
            position=POS, timestamp=_ts(),
        )
        # severity = min(1.0, 50/100) = 0.5
        assert result.own_morale_delta == pytest.approx(-0.05 * 0.5)

    def test_severity_capped_at_one(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = ConsequenceEngine(event_bus, rng)
        result = engine.process_prohibited_weapon(
            "cluster-bomb", "cluster-round", "blue", civilian_casualties=500,
            position=POS, timestamp=_ts(),
        )
        # severity = min(1.0, 500/100) = 1.0
        assert result.own_morale_delta == pytest.approx(-0.05)

    def test_publishes_prohibited_event(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        events_received: list[Event] = []
        event_bus.subscribe(ProhibitedWeaponEmployedEvent, events_received.append)
        engine = ConsequenceEngine(event_bus, rng)
        engine.process_prohibited_weapon(
            "napalm", "napalm-canister", "red", civilian_casualties=30,
            position=POS, timestamp=_ts(),
        )
        assert len(events_received) == 1
        evt = events_received[0]
        assert isinstance(evt, ProhibitedWeaponEmployedEvent)
        assert evt.weapon_id == "napalm"
        assert evt.ammo_id == "napalm-canister"


class TestPrisonerMistreatment:
    """Prisoner mistreatment processing."""

    def test_level_zero_no_penalty(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = ConsequenceEngine(event_bus, rng)
        result = engine.process_prisoner_mistreatment(
            "blue", treatment_level=0, documented=False, timestamp=_ts(),
        )
        assert result.own_morale_delta == pytest.approx(0.0)
        assert result.enemy_morale_delta == pytest.approx(0.0)

    def test_level_one_moderate(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = ConsequenceEngine(event_bus, rng)
        result = engine.process_prisoner_mistreatment(
            "blue", treatment_level=1, documented=False, timestamp=_ts(),
        )
        assert result.own_morale_delta == pytest.approx(-0.05 * 0.5)
        assert result.enemy_morale_delta == pytest.approx(0.03 * 0.5)

    def test_level_two_severe(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = ConsequenceEngine(event_bus, rng)
        result = engine.process_prisoner_mistreatment(
            "blue", treatment_level=2, documented=False, timestamp=_ts(),
        )
        assert result.own_morale_delta == pytest.approx(-0.05)

    def test_documented_doubles_international_pressure(
        self, event_bus: EventBus, rng: np.random.Generator,
    ) -> None:
        engine = ConsequenceEngine(event_bus, rng)
        result_undoc = engine.process_prisoner_mistreatment(
            "blue", treatment_level=2, documented=False, timestamp=_ts(),
        )
        engine2 = ConsequenceEngine(event_bus, _rng(99))
        result_doc = engine2.process_prisoner_mistreatment(
            "blue", treatment_level=2, documented=True, timestamp=_ts(),
        )
        assert result_doc.international_pressure_delta == pytest.approx(
            result_undoc.international_pressure_delta * 2.0,
        )

    def test_publishes_prisoner_event(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        events_received: list[Event] = []
        event_bus.subscribe(PrisonerMistreatmentEvent, events_received.append)
        engine = ConsequenceEngine(event_bus, rng)
        engine.process_prisoner_mistreatment(
            "red", treatment_level=1, documented=True, timestamp=_ts(),
        )
        assert len(events_received) == 1
        evt = events_received[0]
        assert isinstance(evt, PrisonerMistreatmentEvent)
        assert evt.responsible_side == "red"
        assert evt.treatment_level == 1


class TestSpiralRetaliation:
    """Bernoulli escalation spiral triggering."""

    def test_spiral_deterministic_high_severity(self, event_bus: EventBus) -> None:
        """With severity=1.0 and spiral_prob=1.0, spiral always triggers."""
        cfg = ConsequenceConfig(spiral_retaliation_probability=1.0)
        engine = ConsequenceEngine(event_bus, _rng(0), config=cfg)
        result = engine.process_war_crime(
            "massacre", "blue", severity=1.0, position=POS, timestamp=_ts(),
        )
        assert result.escalation_spiral_triggered is True

    def test_spiral_deterministic_zero_severity(self, event_bus: EventBus) -> None:
        """With severity=0.0, spiral never triggers regardless of probability."""
        cfg = ConsequenceConfig(spiral_retaliation_probability=1.0)
        engine = ConsequenceEngine(event_bus, _rng(0), config=cfg)
        result = engine.process_war_crime(
            "minor", "blue", severity=0.0, position=POS, timestamp=_ts(),
        )
        assert result.escalation_spiral_triggered is False


class TestConsequenceState:
    """State roundtrip for ConsequenceEngine."""

    def test_state_roundtrip(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = ConsequenceEngine(event_bus, rng)
        engine.process_war_crime("a", "blue", 0.5, POS, _ts(0))
        engine.process_war_crime("b", "red", 0.3, POS, _ts(1))
        state = engine.get_state()
        engine2 = ConsequenceEngine(event_bus, _rng(99))
        engine2.set_state(state)
        assert engine2.get_crime_count("blue") == 1
        assert engine2.get_crime_count("red") == 1


# ===========================================================================
# Section 4: Events (~10 tests)
# ===========================================================================


class TestEventConstruction:
    """Validate all 8 event types can be constructed with expected fields."""

    def test_escalation_level_change_event(self) -> None:
        evt = EscalationLevelChangeEvent(
            timestamp=TS, source=ModuleId.ESCALATION,
            side="blue", old_level=0, new_level=1, desperation_index=0.3,
        )
        assert evt.side == "blue"
        assert evt.old_level == 0
        assert evt.new_level == 1
        assert evt.desperation_index == pytest.approx(0.3)
        assert isinstance(evt, Event)

    def test_war_crime_recorded_event(self) -> None:
        evt = WarCrimeRecordedEvent(
            timestamp=TS, source=ModuleId.ESCALATION,
            responsible_side="red", crime_type="targeting_civilians",
            severity=0.8, position=POS,
        )
        assert evt.responsible_side == "red"
        assert evt.crime_type == "targeting_civilians"
        assert evt.severity == pytest.approx(0.8)
        assert evt.position == POS

    def test_political_pressure_change_event(self) -> None:
        evt = PoliticalPressureChangeEvent(
            timestamp=TS, source=ModuleId.ESCALATION,
            side="blue", old_international=0.1, new_international=0.2,
            old_domestic=0.05, new_domestic=0.10,
        )
        assert evt.side == "blue"
        assert evt.new_international == pytest.approx(0.2)
        assert evt.new_domestic == pytest.approx(0.10)

    def test_coalition_fracture_event(self) -> None:
        evt = CoalitionFractureEvent(
            timestamp=TS, source=ModuleId.ESCALATION,
            side="blue", departing_ally="ally_1", units_removed=5,
        )
        assert evt.departing_ally == "ally_1"
        assert evt.units_removed == 5

    def test_prohibited_weapon_employed_event(self) -> None:
        evt = ProhibitedWeaponEmployedEvent(
            timestamp=TS, source=ModuleId.ESCALATION,
            responsible_side="red", weapon_id="vx-launcher",
            ammo_id="vx-round", position=POS,
        )
        assert evt.weapon_id == "vx-launcher"
        assert evt.ammo_id == "vx-round"
        assert evt.position == POS

    def test_civilian_atrocity_event(self) -> None:
        evt = CivilianAtrocityEvent(
            timestamp=TS, source=ModuleId.ESCALATION,
            responsible_side="blue", atrocity_type="massacre",
            civilian_casualties=50, position=POS,
        )
        assert evt.atrocity_type == "massacre"
        assert evt.civilian_casualties == 50

    def test_prisoner_mistreatment_event(self) -> None:
        evt = PrisonerMistreatmentEvent(
            timestamp=TS, source=ModuleId.ESCALATION,
            responsible_side="red", treatment_level=2, prisoner_count=30,
        )
        assert evt.treatment_level == 2
        assert evt.prisoner_count == 30

    def test_scorched_earth_event(self) -> None:
        evt = ScorchedEarthEvent(
            timestamp=TS, source=ModuleId.ESCALATION,
            responsible_side="blue", infrastructure_destroyed=15,
            position=POS,
        )
        assert evt.infrastructure_destroyed == 15
        assert evt.position == POS

    def test_events_are_frozen(self) -> None:
        evt = EscalationLevelChangeEvent(
            timestamp=TS, source=ModuleId.ESCALATION,
            side="blue", old_level=0, new_level=1, desperation_index=0.3,
        )
        with pytest.raises(AttributeError):
            evt.side = "red"  # type: ignore[misc]

    def test_events_inherit_from_event(self) -> None:
        evt = ScorchedEarthEvent(
            timestamp=TS, source=ModuleId.ESCALATION,
            responsible_side="blue", infrastructure_destroyed=5,
            position=POS,
        )
        assert isinstance(evt, Event)
        assert evt.timestamp == TS
        assert evt.source == ModuleId.ESCALATION
