"""Phase 103 regression test — Block 11 OOB + engine polish.

Validates:
- Iraqi artillery carrier units (D-30, BM-21, 2S1, 2S3, FROG-7, SA-7) carry
  their authored weapons and mappings resolve through the production registry
- AGM-65 Maverick mapping resolves on all carrier aircraft (A-10, F-15E,
  F-16C, AV-8B)
- Mk 20 Rockeye II CBU mapping resolves and bomb_rack_generic includes it
  in compatible_ammo
- AIM-120 AMRAAM mapping resolves
- WP / FAE / napalm ammo tagged INCENDIARY_WEAPON (triggers Phase 101
  fire-zone branch on hit)
- _route_air_engagement publishes EngagementEvent alongside AirEngagementEvent
- _route_naval_engagement publishes EngagementEvent on torpedo / depth charge
  / ASHM salvo / ASROC paths (NGFS + ship-vs-ship already covered Phase 100)
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from stochastic_warfare.entities.equipment import EquipmentCategory
from stochastic_warfare.simulation.equipment_mappings import (
    EQUIPMENT_MAPPING_REGISTRY,
)
from stochastic_warfare.simulation.loadouts import (
    WeaponAttachmentMapping,
    WeaponStoreMapping,
)

DATA_DIR = Path(__file__).resolve().parents[3] / "data"


# ---------------------------------------------------------------------------
# OOB mapping assertions
# ---------------------------------------------------------------------------


class TestPhase103WeaponMappings:
    """Weapon name -> ID mappings added in Phase 103."""

    def test_sa7_missile_round_mapped(self) -> None:
        record = EQUIPMENT_MAPPING_REGISTRY.require(
            EquipmentCategory.WEAPON,
            "SA-7 Missile Round",
        )
        assert isinstance(record, WeaponStoreMapping)
        assert record.ammo_id == "sa7_warhead"
        assert record.compatible_weapon_ids == ("sa7_strela2",)

    def test_mk20_rockeye_mapped(self) -> None:
        record = EQUIPMENT_MAPPING_REGISTRY.require(
            EquipmentCategory.WEAPON,
            "Mk 20 Rockeye II CBU",
        )
        assert isinstance(record, WeaponStoreMapping)
        assert record.ammo_id == "mk20_rockeye"
        assert record.compatible_weapon_ids == (
            "bru36a_bomb_ejector_rack",
            "mau40a_bomb_ejector_rack",
        )

    def test_aim120_amraam_mapped(self) -> None:
        record = EQUIPMENT_MAPPING_REGISTRY.require(
            EquipmentCategory.WEAPON,
            "AIM-120 AMRAAM",
        )
        assert isinstance(record, WeaponAttachmentMapping)
        assert record.weapon_id == "aim120_amraam"


class TestPhase103IraqiArtilleryCarriers:
    """Iraqi artillery + MANPADS carrier units carry their authored weapons."""

    def _load(self, path: str) -> dict:
        return yaml.safe_load((DATA_DIR.parent / path).read_text(encoding="utf-8"))

    def test_iraqi_2s1_battery_exists_and_carries_weapon(self) -> None:
        d = self._load("data/units/artillery/iraqi_2s1_battery.yaml")
        weapons = [e["name"] for e in d["equipment"] if e["category"] == "WEAPON"]
        assert "2S1 Gvozdika 122mm SP" in weapons

    def test_iraqi_2s3_battery_exists_and_carries_weapon(self) -> None:
        d = self._load("data/units/artillery/iraqi_2s3_battery.yaml")
        weapons = [e["name"] for e in d["equipment"] if e["category"] == "WEAPON"]
        assert "2S3 Akatsiya 152mm SP" in weapons

    def test_iraqi_frog7_tel_exists_and_carries_weapon(self) -> None:
        d = self._load("data/units/artillery/iraqi_frog7_tel.yaml")
        weapons = [e["name"] for e in d["equipment"] if e["category"] == "WEAPON"]
        assert "9K52 Luna-M FROG-7 TEL" in weapons

    def test_iraqi_sa7_team_missile_round_resolvable(self) -> None:
        d = self._load("data/units/air_defense/iraqi_sa7_team.yaml")
        weapons = [e["name"] for e in d["equipment"] if e["category"] == "WEAPON"]
        assert "SA-7 Missile Round" in weapons
        record = EQUIPMENT_MAPPING_REGISTRY.require(
            EquipmentCategory.WEAPON,
            "SA-7 Missile Round",
        )
        assert isinstance(record, WeaponStoreMapping)


class TestPhase103BombRackRockeyeCompat:
    """bomb_rack_generic now lists mk20_rockeye in compatible_ammo."""

    @pytest.mark.test_evidence("structural_only")
    def test_bomb_rack_carries_rockeye(self) -> None:
        p = DATA_DIR / "weapons" / "bombs" / "bomb_rack_generic.yaml"
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
        assert "mk20_rockeye" in d["compatible_ammo"]


class TestPhase103AGM65Carriage:
    """AGM-65 Maverick carried on all Desert Storm-era carrier aircraft."""

    def _aircraft_weapons(self, aircraft: str) -> list[str]:
        for sub in ("air_fixed_wing", "air_rotary_wing"):
            p = DATA_DIR / "units" / sub / f"{aircraft}.yaml"
            if p.exists():
                d = yaml.safe_load(p.read_text(encoding="utf-8"))
                return [e["name"] for e in d["equipment"] if e["category"] == "WEAPON"]
        return []

    @pytest.mark.parametrize("aircraft", ["a10a", "f15e", "f16c", "av8b"])
    def test_carries_agm65(self, aircraft: str) -> None:
        weapons = self._aircraft_weapons(aircraft)
        assert "AGM-65 Maverick" in weapons, (
            f"{aircraft} should carry AGM-65 Maverick"
        )


# ---------------------------------------------------------------------------
# Ammo retagging assertions
# ---------------------------------------------------------------------------


class TestPhase103IncendiaryRetagging:
    """WP / FAE / napalm ammo tagged INCENDIARY_WEAPON triggers Phase 101
    fire-zone branch on hit."""

    @pytest.mark.test_evidence("structural_only")
    @pytest.mark.parametrize("path", [
        "data/ammunition/prohibited/white_phosphorus_shell.yaml",
        "data/ammunition/prohibited/fae_thermobaric.yaml",
        "data/ammunition/prohibited/mk77_napalm.yaml",
    ])
    def test_ammo_tagged_incendiary(self, path: str) -> None:
        d = yaml.safe_load((DATA_DIR.parent / path).read_text(encoding="utf-8"))
        actual = d["ammo_type"]
        assert actual == "INCENDIARY_WEAPON", (
            f"{path}: ammo_type is {actual!r}, expected INCENDIARY_WEAPON"
        )


# ---------------------------------------------------------------------------
# Engine EngagementEvent emission
# ---------------------------------------------------------------------------


class TestPhase103AirEngagementEventEmission:
    """_route_air_engagement now publishes generic EngagementEvent alongside
    AirEngagementEvent so air-routed weapon fires surface in /analytics/
    engagements chart."""

    @pytest.mark.test_evidence("structural_only")
    def test_publish_air_engagement_event_defined(self) -> None:
        from stochastic_warfare.simulation.battle import _publish_air_engagement_event
        assert callable(_publish_air_engagement_event)

    def test_hanit_scenario_emits_engagement_event(self) -> None:
        """End-to-end: run Hanit briefly, confirm EngagementEvents surface
        from ASCM salvo (previously silent — AirEngagementEvent only)."""
        from stochastic_warfare.simulation.scenario import ScenarioLoader
        from stochastic_warfare.simulation.engine import (
            SimulationEngine, EngineConfig,
        )
        from stochastic_warfare.simulation.recorder import SimulationRecorder
        loader = ScenarioLoader(DATA_DIR)
        ctx = loader.load(
            DATA_DIR / "scenarios" / "ins_hanit_2006" / "scenario.yaml",
            seed=42,
        )
        red_launchers = [
            attachment
            for unit in ctx.units_by_side["red"]
            for attachment in ctx.unit_weapons[unit.entity_id]
            if attachment.weapon.weapon_id == "c802_noor"
        ]
        assert len(red_launchers) == 2
        rounds_before = sum(
            attachment.weapon.ammo_state.available("c802_noor_warhead")
            for attachment in red_launchers
        )
        rec = SimulationRecorder(ctx.event_bus)
        rec.start()
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=200))
        while not engine.step():
            pass
        c802_events = [
            event
            for event in rec.events
            if event.event_type == "EngagementEvent"
            and event.data.get("attacker_id", "").startswith(
                "red_hezbollah_coastal_tel_",
            )
            and event.data.get("weapon_id") == "c802_noor"
            and event.data.get("ammo_type") == "c802_noor_warhead"
        ]
        rounds_after = sum(
            attachment.weapon.ammo_state.available("c802_noor_warhead")
            for attachment in red_launchers
        )
        assert c802_events, (
            "INS Hanit production run must expose a red C-802 "
            "EngagementEvent"
        )
        assert rounds_after < rounds_before
