"""Small production-executor harness shared by battle feature tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import numpy as np

from stochastic_warfare.combat.ammunition import (
    AmmoDefinition,
    AmmoState,
    WeaponDefinition,
    WeaponInstance,
)
from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import Unit
from stochastic_warfare.morale.state import MoraleState
from stochastic_warfare.simulation.battle import BattleManager
from tests.conftest import bind_test_era_runtime

TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


class RecordingEngagementEngine:
    """Record the inputs selected by the real engagement executor."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def route_engagement(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            engaged=False,
            hit_result=None,
            damage_result=None,
        )


class RecordingDecisionEngine:
    """Capture decisions emitted by the production OODA executor."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def decide(self, **kwargs: Any) -> None:
        call = dict(kwargs)
        adjustments = call.get("school_adjustments")
        if adjustments is not None:
            call["school_adjustments"] = dict(adjustments)
        self.calls.append(call)


class FixedDoctrinalSchool:
    """Supply one stable doctrinal adjustment map at the school boundary."""

    def __init__(self, adjustments: dict[str, float]) -> None:
        self.adjustments = adjustments
        self.definition = SimpleNamespace(opponent_modeling_enabled=False)

    def get_decision_score_adjustments(
        self,
        **_kwargs: Any,
    ) -> dict[str, float]:
        return dict(self.adjustments)

    @staticmethod
    def get_ooda_multiplier() -> float:
        return 1.0


class FixedSchoolRegistry:
    """Resolve every fixture unit to the supplied doctrinal school."""

    def __init__(self, school: FixedDoctrinalSchool) -> None:
        self.school = school

    def get_for_unit(self, _unit_id: str) -> FixedDoctrinalSchool:
        return self.school


class Sensor:
    """Minimal live sensor boundary for executor tests."""

    def __init__(self, effective_range_m: float, sensor_type: Any) -> None:
        self.effective_range = effective_range_m
        self.operational = True
        self.sensor_type = sensor_type

    @staticmethod
    def supports_target_domain(_domain: Domain) -> bool:
        return True


class VisualSensor(Sensor):
    """Visual specialization used by detection-quality tests."""

    def __init__(self, effective_range_m: float) -> None:
        from stochastic_warfare.detection.sensors import SensorType

        super().__init__(effective_range_m, SensorType.VISUAL)


def make_unit(
    entity_id: str,
    side: str,
    easting: float,
    *,
    northing: float = 0.0,
    domain: Domain = Domain.GROUND,
    speed: float = 0.0,
    max_speed: float = 10.0,
    training_level: float = 0.5,
) -> Unit:
    """Build one real Unit accepted by the production executors."""
    return Unit(
        entity_id=entity_id,
        name=entity_id,
        side=side,
        domain=domain,
        position=Position(easting, northing, 0.0),
        speed=speed,
        max_speed=max_speed,
        training_level=training_level,
    )


def make_weapon(
    *,
    max_range_m: float = 3_000.0,
    effective_range_m: float | None = None,
    weapon_id: str = "test-gun",
    category: str = "CANNON",
    target_domains: list[str] | None = None,
) -> tuple[WeaponInstance, list[AmmoDefinition]]:
    """Build one live weapon/ammunition pair with deterministic availability."""
    ammunition = AmmoDefinition(
        ammo_id=f"{weapon_id}-round",
        display_name="Test round",
        ammo_type="HE",
        mass_kg=10.0,
        diameter_mm=120.0,
        drag_coefficient=0.3,
    )
    definition_kwargs: dict[str, Any] = {}
    if effective_range_m is not None:
        definition_kwargs["effective_range_m"] = effective_range_m
    if target_domains is not None:
        definition_kwargs["target_domains"] = target_domains
    definition = WeaponDefinition(
        weapon_id=weapon_id,
        display_name="Test gun",
        category=category,
        caliber_mm=120.0,
        max_range_m=max_range_m,
        rate_of_fire_rpm=6.0,
        compatible_ammo=[ammunition.ammo_id],
        **definition_kwargs,
    )
    weapon = WeaponInstance(
        definition=definition,
        ammo_state=AmmoState(rounds_by_type={ammunition.ammo_id: 20}),
    )
    return weapon, [ammunition]


def make_context(
    units_by_side: dict[str, list[Unit]],
    *,
    unit_weapons: dict[str, list[tuple[WeaponInstance, list[AmmoDefinition]]]],
    calibration: dict[str, Any] | None = None,
    unit_sensors: dict[str, list[Any]] | None = None,
    engagement_engine: Any | None = None,
    detection_engine: Any | None = None,
    behavior_rules: dict[str, dict[str, Any]] | None = None,
    classification: Any | None = None,
) -> SimpleNamespace:
    """Build the narrow SimulationContext surface consumed by engagement."""
    clock = SimulationClock(
        start=TS,
        tick_duration=timedelta(seconds=5.0),
    )
    config = SimpleNamespace(
        sides=[
            SimpleNamespace(side=side, experience_level=0.8)
            for side in sorted(units_by_side)
        ],
        era="modern",
        behavior_rules=behavior_rules or {},
        calibration_overrides=calibration or {},
    )
    return bind_test_era_runtime(
        SimpleNamespace(
            calibration=calibration or {},
            config=config,
            clock=clock,
            event_bus=EventBus(),
            units_by_side=units_by_side,
            unit_weapons=unit_weapons,
            unit_sensors=unit_sensors or {},
            morale_states={
                unit.entity_id: MoraleState.STEADY
                for units in units_by_side.values()
                for unit in units
            },
            engagement_engine=engagement_engine or RecordingEngagementEngine(),
            detection_engine=detection_engine,
            classification=classification,
        ),
    )


def make_ooda_context(
    unit: Unit,
    *,
    calibration: dict[str, Any],
    school_adjustments: dict[str, float],
    order_propagation: Any | None = None,
    planning_engine: Any | None = None,
    seed: int = 42,
) -> tuple[SimpleNamespace, RecordingDecisionEngine]:
    """Build the narrow live context consumed by the production OODA path."""
    units_by_side = {unit.side: [unit], "red": []}
    clock = SimulationClock(
        start=TS,
        tick_duration=timedelta(seconds=1.0),
    )
    decision_engine = RecordingDecisionEngine()
    school = FixedDoctrinalSchool(school_adjustments)
    context = SimpleNamespace(
        calibration=calibration,
        clock=clock,
        rng_manager=RNGManager(seed),
        event_bus=EventBus(),
        units_by_side=units_by_side,
        decision_engine=decision_engine,
        order_propagation=order_propagation,
        planning_engine=planning_engine,
        school_registry=FixedSchoolRegistry(school),
        ooda_engine=None,
        assessor=None,
        commander_engine=None,
        comms_engine=None,
        cbrn_engine=None,
        stockpile_manager=None,
        stratagem_engine=None,
        fog_of_war=None,
        morale_states={},
    )
    context.active_units = lambda side: tuple(units_by_side.get(side, ()))
    context.side_names = lambda: tuple(units_by_side)
    return context, decision_engine


def execute_engagement_side(
    manager: BattleManager,
    context: SimpleNamespace,
    side: str,
    enemies: list[Unit],
) -> list[tuple[Unit, object, str]]:
    """Run one side through BattleManager and its production executor."""
    positions = np.array(
        [[enemy.position.easting, enemy.position.northing] for enemy in enemies],
        dtype=np.float64,
    ).reshape((-1, 2))
    return manager._execute_engagements(
        context,
        {side: context.units_by_side[side]},
        {side: enemies},
        {side: positions},
        5.0,
        TS,
    )
