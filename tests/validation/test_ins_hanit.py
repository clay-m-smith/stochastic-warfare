"""Phase 102 regression test — INS Hanit C-802 strike (14 July 2006).

Naval vignette asserting that the INS Hanit scenario produces outcomes
consistent with the historical degraded-ECM hit envelope and that
Phase 102 new naval/ASCM infrastructure works end-to-end:

- Sa'ar 5 corvette (INS Hanit) loads with Barak-1 + Harpoon + Oto 76mm
  + Phalanx + EL/M radar + ESM loadout
- Hezbollah coastal TEL with C-802 Noor launcher loads
- C-802 Noor ASCM + 165kg SAP warhead load
- C-802 engages Hanit via missile routing path

Historical outcome (ONI 2006-2009, IDF Navy statements, USNI 2007):
- Sa'ar 5 HIT (not destroyed); damaged, 4 KIA, returned under power
- Second C-802 struck Cambodian merchantman ~60km offshore (not modeled
  in this vignette — Hezbollah + Hanit only)
- Key dynamic: sea-skimming ASCM defeating reduced-alert defensive
  posture (Barak/Phalanx reportedly off or in standby)

Engine-observed envelope:
- Hanit survives (not DESTROYED)
- C-802 firing + missile engagement events occur

Tests marked @slow for runtime assertions; load tests run fast.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from stochastic_warfare.entities.equipment import EquipmentCategory
from stochastic_warfare.entities.base import UnitStatus
from stochastic_warfare.simulation.equipment_mappings import (
    EQUIPMENT_MAPPING_REGISTRY,
)
from stochastic_warfare.simulation.engine import EngineConfig, SimulationEngine
from stochastic_warfare.simulation.loadouts import (
    ReferenceKind,
    SensorAttachmentMapping,
    SensorModeledRole,
    WeaponModeledRole,
)
from stochastic_warfare.simulation.recorder import SimulationRecorder
from stochastic_warfare.simulation.scenario import (
    ScenarioLoader,
    VictoryConditionConfig,
)
from stochastic_warfare.simulation.tactical_targeting import (
    FireControlSource,
    TacticalTargetingDecision,
)
from stochastic_warfare.simulation.victory import VictoryEvaluator

SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "ins_hanit_2006" / "scenario.yaml"
)
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _run_one(seed: int, max_ticks: int = 1500) -> dict:
    """Run one iteration of Hanit vignette and return summary metrics."""
    with open(SCENARIO_PATH) as f:
        scn = yaml.safe_load(f)
    conditions = [VictoryConditionConfig(**vc) for vc in scn["victory_conditions"]]
    loader = ScenarioLoader(str(DATA_DIR))
    ctx = loader.load(SCENARIO_PATH, seed=seed)
    victory_eval = VictoryEvaluator(
        objectives=[],
        conditions=conditions,
        event_bus=ctx.event_bus,
        max_duration_s=7200.0,
    )
    recorder = SimulationRecorder(ctx.event_bus)
    red_launchers = [
        attachment
        for unit in ctx.units_by_side["red"]
        for attachment in ctx.unit_weapons[unit.entity_id]
        if attachment.weapon.weapon_id == "c802_noor"
    ]
    c802_rounds_before = sum(
        attachment.weapon.ammo_state.available("c802_noor_warhead")
        for attachment in red_launchers
    )
    engine = SimulationEngine(
        ctx,
        config=EngineConfig(max_ticks=max_ticks),
        victory_evaluator=victory_eval,
        recorder=recorder,
    )
    red_unit_ids = tuple(
        unit.entity_id for unit in ctx.units_by_side["red"]
    )
    c802_targeting_by_key: dict[tuple[int, str, str], TacticalTargetingDecision] = {}
    recorder.start()
    while True:
        done = engine.step()
        for picture in ctx.tactical_targeting.latest_pictures():
            for unit_id in red_unit_ids:
                decision = picture.decision_for(unit_id)
                if decision is not None and decision.weapon_id == "c802_noor":
                    c802_targeting_by_key[decision.key] = decision
        if done:
            break
    blue_units = ctx.units_by_side["blue"]
    hanit_status = blue_units[0].status if blue_units else None
    red_d = sum(1 for u in ctx.units_by_side["red"] if u.status == UnitStatus.DESTROYED)
    victory = getattr(engine, "_last_victory", None)
    winner = (getattr(victory, "winning_side", "") or "").lower()
    ticks = ctx.clock.tick_count
    c802_events = [
        event
        for event in recorder.events
        if event.event_type == "EngagementEvent"
        and event.data.get("attacker_id", "").startswith(
            "red_hezbollah_coastal_tel_",
        )
        and event.data.get("weapon_id") == "c802_noor"
        and event.data.get("ammo_type") == "c802_noor_warhead"
    ]
    c802_rounds_after = sum(
        attachment.weapon.ammo_state.available("c802_noor_warhead")
        for attachment in red_launchers
    )
    return {
        "hanit_status": hanit_status,
        "red_destroyed": red_d,
        "winner": winner,
        "ticks": ticks,
        "events": recorder.events,
        "c802_events": c802_events,
        "c802_targeting": tuple(c802_targeting_by_key.values()),
        "c802_rounds_before": c802_rounds_before,
        "c802_rounds_after": c802_rounds_after,
    }


# ---------------------------------------------------------------------------
# Load-time assertions (fast)
# ---------------------------------------------------------------------------


class TestInsHanitScenarioLoad:
    """Phase 102 naval/ASCM plumbing loads cleanly."""

    def test_scenario_loads(self) -> None:
        loader = ScenarioLoader(str(DATA_DIR))
        ctx = loader.load(SCENARIO_PATH, seed=42)
        assert ctx.config.name.startswith("INS Hanit"), (
            f"Wrong scenario loaded: {ctx.config.name}"
        )

    def test_force_structure(self) -> None:
        """Vignette has 1 Hanit (blue) + 2 Hezbollah TELs (red) = 3 total."""
        loader = ScenarioLoader(str(DATA_DIR))
        ctx = loader.load(SCENARIO_PATH, seed=42)
        assert len(ctx.units_by_side["blue"]) == 1
        assert len(ctx.units_by_side["red"]) == 2

    def test_hanit_unit_type(self) -> None:
        """Blue unit is Sa'ar 5 corvette."""
        loader = ScenarioLoader(str(DATA_DIR))
        ctx = loader.load(SCENARIO_PATH, seed=42)
        assert ctx.units_by_side["blue"][0].unit_type == "idf_saar5"

    def test_tel_unit_type(self) -> None:
        """Red units are Hezbollah coastal TELs."""
        loader = ScenarioLoader(str(DATA_DIR))
        ctx = loader.load(SCENARIO_PATH, seed=42)
        for u in ctx.units_by_side["red"]:
            assert u.unit_type == "hezbollah_coastal_tel"

    def test_scenario_duration(self) -> None:
        """2-hour vignette — brief engagement."""
        loader = ScenarioLoader(str(DATA_DIR))
        ctx = loader.load(SCENARIO_PATH, seed=42)
        assert ctx.config.duration_hours == 2.0

    def test_coastal_targeting_network_mapping_is_bounded_anti_ship_fire_control(
        self,
    ) -> None:
        """The composite network is a bounded director, not a search proxy."""
        record = EQUIPMENT_MAPPING_REGISTRY.require(
            EquipmentCategory.SENSOR,
            "Coastal Missile Targeting Network",
        )

        assert isinstance(record, SensorAttachmentMapping)
        assert record.sensor_id == "ground_search_radar"
        assert record.modeled_role is SensorModeledRole.FIRE_CONTROL_RADAR
        assert record.compatible_weapon_roles == (
            WeaponModeledRole.ANTI_SHIP_MISSILE,
        )
        assert record.modeled_max_range_m == 60_000.0
        assert record.modeled_fov_deg == 360.0
        assert record.reference_kind is ReferenceKind.FUNCTIONAL_ANALOGUE
        assert record.allowed_target_ids == ("ground_search_radar",)
        assert record.rationale is not None
        assert record.source is not None
        assert EQUIPMENT_MAPPING_REGISTRY.get(
            EquipmentCategory.SENSOR,
            "Coastal Surveillance Radar",
        ) is None

    def test_coastal_targeting_network_binds_only_the_live_c802_attachment(
        self,
    ) -> None:
        """Production loading wires the network to each TEL's exact launcher."""
        loader = ScenarioLoader(str(DATA_DIR))
        ctx = loader.load(SCENARIO_PATH, seed=42)

        for unit in ctx.units_by_side["red"]:
            sensor_equipment = tuple(
                equipment
                for equipment in unit.equipment
                if equipment.category is EquipmentCategory.SENSOR
            )
            assert tuple(
                equipment.name for equipment in sensor_equipment
            ) == ("Coastal Missile Targeting Network",)

            sensor_attachments = ctx.unit_sensor_attachments[unit.entity_id]
            assert len(sensor_attachments) == 1
            director = sensor_attachments[0]
            assert director.source_equipment is sensor_equipment[0]
            assert director.sensor_id == "ground_search_radar"
            assert director.modeled_role is SensorModeledRole.FIRE_CONTROL_RADAR
            assert director.compatible_weapon_roles == (
                WeaponModeledRole.ANTI_SHIP_MISSILE,
            )
            assert director.sensor.definition.max_range_m == 60_000.0
            assert director.sensor.definition.fov_deg == 360.0

            weapons = ctx.unit_weapons[unit.entity_id]
            c802 = next(
                attachment
                for attachment in weapons
                if attachment.weapon.weapon_id == "c802_noor"
            )
            assert c802.modeled_role is WeaponModeledRole.ANTI_SHIP_MISSILE
            assert director.compatible_weapon_source_indexes == (
                c802.source_equipment_index,
            )

            resolution = next(
                item
                for item in ctx.equipment_resolutions[unit.entity_id]
                if item.source_equipment is sensor_equipment[0]
            )
            assert resolution.target_id == "ground_search_radar"
            assert resolution.modeled_role is SensorModeledRole.FIRE_CONTROL_RADAR
            assert resolution.reference_kind is ReferenceKind.FUNCTIONAL_ANALOGUE


# ---------------------------------------------------------------------------
# Runtime assertions (@slow)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def run_result() -> dict:
    """Single-seed run — vignette is short so this is fast compared to other scenarios."""
    return _run_one(seed=42, max_ticks=1500)


@pytest.mark.slow
class TestInsHanitRuntime:
    """Runtime envelope assertions."""

    def test_scenario_progresses(self, run_result: dict) -> None:
        """Scenario runs — vignette completes within max_ticks."""
        assert run_result["ticks"] >= 10, (
            f"Scenario barely progressed: {run_result['ticks']} ticks"
        )

    def test_hanit_survives(self, run_result: dict) -> None:
        """Historical outcome: Hanit damaged but not destroyed."""
        status = run_result["hanit_status"]
        assert status != UnitStatus.DESTROYED, (
            "Hanit destroyed — historical outcome was damage + survival"
        )

    def test_c802_engages_hanit(self, run_result: dict) -> None:
        """The red launchers exercise the production ASCM route."""
        assert run_result["c802_events"]

    def test_c802_consumes_live_ammunition(self, run_result: dict) -> None:
        """A recorded launch must consume the launcher's live round."""
        assert (
            run_result["c802_rounds_after"]
            < run_result["c802_rounds_before"]
        )

    def test_c802_uses_the_live_coastal_targeting_network(
        self,
        run_result: dict,
    ) -> None:
        """The production targeting decision consumes the mapped director."""
        authorized = tuple(
            decision
            for decision in run_result["c802_targeting"]
            if decision.can_engage
        )
        assert authorized
        for decision in authorized:
            assert decision.weapon_modeled_role is (
                WeaponModeledRole.ANTI_SHIP_MISSILE
            )
            assert decision.fire_control_source is (
                FireControlSource.SENSOR_ATTACHMENT
            )
            assert decision.fire_control_sensor_id == "ground_search_radar"
            assert decision.fire_control_sensor_modeled_role is (
                SensorModeledRole.FIRE_CONTROL_RADAR
            )
            assert decision.fire_control_range_m >= decision.distance_m > 0.0
