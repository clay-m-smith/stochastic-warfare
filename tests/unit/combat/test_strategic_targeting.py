"""Unit tests for StrategicTargetingEngine — TPL, strikes, BDA, regeneration."""

from __future__ import annotations

import pytest

from stochastic_warfare.combat.strategic_targeting import (
    StrategicTarget,
    StrategicTargetingConfig,
    StrategicTargetingEngine,
    TargetEffectChain,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position

from .conftest import _rng


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_targeting_engine(seed: int = 42, **cfg_kwargs) -> StrategicTargetingEngine:
    bus = EventBus()
    config = StrategicTargetingConfig(**cfg_kwargs) if cfg_kwargs else None
    return StrategicTargetingEngine(bus, _rng(seed), config)


def _make_target(
    target_id: str = "t1",
    target_type: str = "bridge",
    health: float = 1.0,
    repair_rate: float = 0.01,
) -> StrategicTarget:
    return StrategicTarget(
        target_id=target_id,
        target_type=target_type,
        position=Position(1000.0, 2000.0, 0.0),
        health=health,
        repair_rate=repair_rate,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTargetRegistration:
    """Targets should be registered and retrievable."""

    def test_register_and_get(self):
        eng = _make_targeting_engine(seed=100)
        target = _make_target("bridge_1", "bridge")
        eng.register_target(target)
        retrieved = eng.get_target("bridge_1")
        assert retrieved.target_id == "bridge_1"
        assert retrieved.target_type == "bridge"

    def test_missing_target_raises(self):
        eng = _make_targeting_engine(seed=101)
        with pytest.raises(KeyError):
            eng.get_target("nonexistent")


class TestTPLGeneration:
    """Target priority list should be sorted by weighted score."""

    def test_higher_weight_type_ranked_first(self):
        eng = _make_targeting_engine(seed=200)
        # power_plant has weight 2.5, bridge has weight 1.5 by default
        eng.register_target(_make_target("pp_1", "power_plant"))
        eng.register_target(_make_target("br_1", "bridge"))
        eng.register_target(_make_target("dp_1", "depot"))

        tpl = eng.generate_tpl()
        ids = [tid for tid, _ in tpl]
        # Power plant (2.5) should be first, then bridge (1.5), then depot (1.2)
        assert ids[0] == "pp_1"
        assert ids[-1] == "dp_1"

    def test_damaged_targets_score_higher(self):
        """Partially damaged targets need fewer resources to destroy, scoring higher."""
        eng = _make_targeting_engine(seed=201)
        eng.register_target(_make_target("br_full", "bridge", health=1.0))
        eng.register_target(_make_target("br_damaged", "bridge", health=0.3))

        tpl = eng.generate_tpl()
        scores = {tid: score for tid, score in tpl}
        assert scores["br_damaged"] > scores["br_full"]

    def test_destroyed_targets_excluded(self):
        eng = _make_targeting_engine(seed=202)
        eng.register_target(_make_target("alive", "bridge", health=0.5))
        eng.register_target(_make_target("dead", "bridge", health=0.0))

        tpl = eng.generate_tpl()
        ids = [tid for tid, _ in tpl]
        assert "alive" in ids
        assert "dead" not in ids

    def test_commander_priority_overrides(self):
        eng = _make_targeting_engine(seed=203)
        eng.register_target(_make_target("br_1", "bridge"))
        eng.register_target(_make_target("dp_1", "depot"))

        # Override depot weight to be very high
        tpl = eng.generate_tpl(commander_priorities={"depot": 10.0})
        ids = [tid for tid, _ in tpl]
        assert ids[0] == "dp_1"


class TestStrikeDamage:
    """Strikes should reduce target health and trigger effect chains."""

    def test_strike_reduces_health(self):
        eng = _make_targeting_engine(seed=300)
        eng.register_target(_make_target("t1", "factory"))

        effects = eng.apply_strike("t1", 0.4)
        assert eng.get_target("t1").health == pytest.approx(0.6)

    def test_strike_health_floors_at_zero(self):
        eng = _make_targeting_engine(seed=301)
        eng.register_target(_make_target("t1", "bridge", health=0.3))

        eng.apply_strike("t1", 0.5)
        assert eng.get_target("t1").health == pytest.approx(0.0)


class TestEffectChainCascade:
    """Effect chains should trigger when target type matches."""

    def test_chain_triggered_on_matching_type(self):
        eng = _make_targeting_engine(seed=400)
        eng.register_target(_make_target("br_1", "bridge"))
        eng.register_effect_chain(TargetEffectChain(
            target_type="bridge",
            effect_type="supply_severed",
            effect_magnitude=1.0,
        ))

        effects = eng.apply_strike("br_1", 0.6)
        assert len(effects) == 1
        assert effects[0]["effect_type"] == "supply_severed"
        assert effects[0]["effect_amount"] > 0.0

    def test_no_chain_for_unmatched_type(self):
        eng = _make_targeting_engine(seed=401)
        eng.register_target(_make_target("fac_1", "factory"))
        eng.register_effect_chain(TargetEffectChain(
            target_type="bridge",
            effect_type="supply_severed",
            effect_magnitude=1.0,
        ))

        effects = eng.apply_strike("fac_1", 0.5)
        assert len(effects) == 0


class TestBDAOverestimate:
    """BDA should overestimate actual damage on average."""

    def test_bda_overestimates(self):
        eng = _make_targeting_engine(seed=500, bda_overestimate_factor=3.0)
        eng.register_target(_make_target("t1", "factory", health=0.7))

        # True damage is 0.3
        assessments = [eng.run_bda_cycle("t1") for _ in range(50)]
        mean_assessed = sum(assessments) / len(assessments)
        true_damage = 0.3

        # Mean BDA should overestimate (factor=3.0 with log bias)
        assert mean_assessed > true_damage

    def test_bda_zero_damage_returns_zero(self):
        eng = _make_targeting_engine(seed=501)
        eng.register_target(_make_target("t1", "bridge", health=1.0))
        assessed = eng.run_bda_cycle("t1")
        assert assessed == pytest.approx(0.0)


class TestRegeneration:
    """Target health should regenerate over time."""

    def test_regeneration_repairs_damage(self):
        eng = _make_targeting_engine(seed=600)
        eng.register_target(_make_target("t1", "factory", health=0.5, repair_rate=0.05))

        eng.update_regeneration(dt_hours=10.0)
        assert eng.get_target("t1").health == pytest.approx(1.0)

    def test_regeneration_caps_at_one(self):
        eng = _make_targeting_engine(seed=601)
        eng.register_target(_make_target("t1", "bridge", health=0.9, repair_rate=0.5))

        eng.update_regeneration(dt_hours=10.0)
        assert eng.get_target("t1").health == pytest.approx(1.0)

    def test_fully_destroyed_does_not_regenerate(self):
        eng = _make_targeting_engine(seed=602)
        eng.register_target(_make_target("t1", "bridge", health=0.0, repair_rate=0.1))

        eng.update_regeneration(dt_hours=24.0)
        # health == 0.0 fails the `0.0 < target.health` check
        assert eng.get_target("t1").health == pytest.approx(0.0)


class TestStateRoundtrip:
    """get_state / set_state should preserve target data."""

    def test_state_roundtrip(self):
        eng = _make_targeting_engine(seed=700)
        eng.register_target(_make_target("t1", "factory"))
        eng.register_target(_make_target("t2", "bridge"))
        eng.apply_strike("t1", 0.3)

        state = eng.get_state()

        eng2 = _make_targeting_engine(seed=999)
        eng2.set_state(state)

        assert eng2.get_target("t1").health == pytest.approx(0.7)
        assert eng2.get_target("t2").health == pytest.approx(1.0)
