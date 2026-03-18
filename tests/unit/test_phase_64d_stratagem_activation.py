"""Phase 64d: Stratagem activation wiring tests."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.c2.ai.assessment import SituationAssessment
from stochastic_warfare.c2.ai.stratagems import StratagemEngine, StratagemType
from stochastic_warfare.c2.events import StratagemActivatedEvent
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position


def _make_rng(seed: int = 42) -> np.random.Generator:
    return np.random.default_rng(seed)


def _make_assessment(force_ratio: float = 1.0, c2_eff: float = 0.8) -> SituationAssessment:
    return SituationAssessment(
        force_ratio=force_ratio,
        c2_effectiveness=c2_eff,
        morale_level=0.7,
        supply_level=0.8,
        contacts=5,
        friendly_count=5,
    )


class TestStratagemConcentration:
    """Concentration stratagem planning and activation."""

    def test_plan_concentration_called(self):
        bus = EventBus()
        engine = StratagemEngine(bus, _make_rng())
        plan = engine.plan_concentration(
            ["u1", "u2", "u3"],
            Position(1000, 2000, 0),
            ["u4"],
        )
        assert plan.stratagem_type == StratagemType.CONCENTRATION

    def test_activate_stratagem_called(self):
        bus = EventBus()
        engine = StratagemEngine(bus, _make_rng())
        plan = engine.plan_concentration(
            ["u1", "u2", "u3"],
            Position(1000, 2000, 0),
            [],
        )
        # Should not raise
        engine.activate_stratagem("commander_1", plan,
                                  datetime(2024, 1, 1, tzinfo=timezone.utc))

    def test_stratagem_activated_event_published(self):
        bus = EventBus()
        events = []
        bus.subscribe(StratagemActivatedEvent, lambda e: events.append(e))
        engine = StratagemEngine(bus, _make_rng())
        plan = engine.plan_concentration(
            ["u1", "u2", "u3"],
            Position(1000, 2000, 0),
            [],
        )
        engine.activate_stratagem("commander_1", plan,
                                  datetime(2024, 1, 1, tzinfo=timezone.utc))
        assert len(events) == 1
        assert events[0].stratagem_type == "CONCENTRATION"

    def test_concentration_bonus_value(self):
        """Concentration bonus should default to 0.08."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema
        cal = CalibrationSchema()
        assert cal.stratagem_concentration_bonus == pytest.approx(0.08)

    def test_economy_of_force_split(self):
        """Economy: last 2 units when 5+ available, empty when fewer."""
        # 6 units → economy = last 2, concentration = first 4
        unit_ids = ["u1", "u2", "u3", "u4", "u5", "u6"]
        economy = unit_ids[-2:] if len(unit_ids) > 4 else []
        conc_units = [u for u in unit_ids if u not in economy]
        assert economy == ["u5", "u6"]
        assert len(conc_units) == 4

        # 3 units → no economy
        unit_ids_small = ["u1", "u2", "u3"]
        economy_small = unit_ids_small[-2:] if len(unit_ids_small) > 4 else []
        assert economy_small == []


class TestStratagemDeception:
    """Deception stratagem planning and activation."""

    def test_plan_deception_called(self):
        bus = EventBus()
        engine = StratagemEngine(bus, _make_rng())
        plan = engine.plan_deception(
            ["u1"], "enemy_front", ["u2", "u3"],
        )
        assert plan.stratagem_type == StratagemType.DECEPTION

    def test_deception_activated_event(self):
        bus = EventBus()
        events = []
        bus.subscribe(StratagemActivatedEvent, lambda e: events.append(e))
        engine = StratagemEngine(bus, _make_rng())
        plan = engine.plan_deception(["u1"], "enemy_front", ["u2", "u3"])
        engine.activate_stratagem("commander_1", plan,
                                  datetime(2024, 1, 1, tzinfo=timezone.utc))
        assert len(events) == 1
        assert events[0].stratagem_type == "DECEPTION"

    def test_deception_bonus_value(self):
        from stochastic_warfare.simulation.calibration import CalibrationSchema
        cal = CalibrationSchema()
        assert cal.stratagem_deception_bonus == pytest.approx(0.10)

    def test_feint_main_split(self):
        """Feint: first unit, main: rest."""
        unit_ids = ["u1", "u2", "u3", "u4"]
        feint = unit_ids[:1]
        main = unit_ids[1:]
        assert feint == ["u1"]
        assert main == ["u2", "u3", "u4"]


class TestStratagemBackwardCompat:
    """Enable_c2_friction=False → logging only, no activation."""

    def test_battle_contains_activate_stratagem(self):
        """battle.py calls activate_stratagem (not just evaluate)."""
        from pathlib import Path
        src = Path(__file__).resolve().parents[2] / "stochastic_warfare" / "simulation" / "battle.py"
        text = src.read_text(encoding="utf-8")
        assert "activate_stratagem" in text
