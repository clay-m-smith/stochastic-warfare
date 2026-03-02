"""Tests for combat/ammunition.py — weapon/ammo definitions, loaders, runtime state."""

from __future__ import annotations

from pathlib import Path

import pytest

from stochastic_warfare.combat.ammunition import (
    AmmoDefinition,
    AmmoLoader,
    AmmoState,
    AmmoType,
    GuidanceType,
    MissileState,
    WeaponCategory,
    WeaponDefinition,
    WeaponInstance,
    WeaponLoader,
)
from stochastic_warfare.entities.equipment import EquipmentCategory, EquipmentItem

_DATA_ROOT = Path(__file__).resolve().parents[2] / "data"


# ---------------------------------------------------------------------------
# Enum sanity
# ---------------------------------------------------------------------------


class TestEnums:
    def test_weapon_category_values(self) -> None:
        assert WeaponCategory.CANNON == 0
        assert WeaponCategory.CIWS == 11

    def test_guidance_type_values(self) -> None:
        assert GuidanceType.NONE == 0
        assert GuidanceType.COMBINED == 10

    def test_ammo_type_values(self) -> None:
        assert AmmoType.AP == 0
        assert AmmoType.TORPEDO == 9


# ---------------------------------------------------------------------------
# WeaponDefinition pydantic model
# ---------------------------------------------------------------------------


class TestWeaponDefinition:
    def test_minimal_weapon(self) -> None:
        w = WeaponDefinition(
            weapon_id="test_gun",
            display_name="Test Gun",
            category="CANNON",
            caliber_mm=120.0,
        )
        assert w.weapon_id == "test_gun"
        assert w.parsed_category() == WeaponCategory.CANNON
        assert w.parsed_guidance() == GuidanceType.NONE

    def test_full_weapon(self) -> None:
        w = WeaponDefinition(
            weapon_id="test_missile",
            display_name="Test Missile",
            category="MISSILE_LAUNCHER",
            caliber_mm=200.0,
            guidance="RADAR_ACTIVE",
            max_range_m=100000.0,
            compatible_ammo=["test_ammo"],
        )
        assert w.parsed_guidance() == GuidanceType.RADAR_ACTIVE
        assert w.compatible_ammo == ["test_ammo"]

    def test_invalid_category_raises(self) -> None:
        w = WeaponDefinition(
            weapon_id="bad",
            display_name="Bad",
            category="INVALID",
            caliber_mm=10.0,
        )
        with pytest.raises(KeyError):
            w.parsed_category()


# ---------------------------------------------------------------------------
# AmmoDefinition pydantic model
# ---------------------------------------------------------------------------


class TestAmmoDefinition:
    def test_minimal_ammo(self) -> None:
        a = AmmoDefinition(
            ammo_id="test_ap",
            display_name="Test AP",
            ammo_type="AP",
        )
        assert a.parsed_ammo_type() == AmmoType.AP
        assert a.parsed_guidance() == GuidanceType.NONE

    def test_guided_ammo(self) -> None:
        a = AmmoDefinition(
            ammo_id="test_guided",
            display_name="Test Guided",
            ammo_type="GUIDED",
            guidance="GPS",
            pk_at_reference=0.9,
            countermeasure_susceptibility=0.05,
        )
        assert a.parsed_guidance() == GuidanceType.GPS
        assert a.pk_at_reference == 0.9

    def test_submunition_ammo(self) -> None:
        a = AmmoDefinition(
            ammo_id="test_dpicm",
            display_name="Test DPICM",
            ammo_type="DPICM",
            submunition_count=72,
            submunition_lethal_radius_m=5.0,
        )
        assert a.submunition_count == 72


# ---------------------------------------------------------------------------
# WeaponLoader
# ---------------------------------------------------------------------------


class TestWeaponLoader:
    def test_load_all_weapons(self) -> None:
        loader = WeaponLoader(_DATA_ROOT / "weapons")
        loader.load_all()
        weapons = loader.available_weapons()
        assert len(weapons) >= 24
        assert "m256_120mm" in weapons
        assert "mk15_phalanx" in weapons

    def test_get_definition(self) -> None:
        loader = WeaponLoader(_DATA_ROOT / "weapons")
        loader.load_all()
        defn = loader.get_definition("m256_120mm")
        assert defn.caliber_mm == 120.0
        assert defn.muzzle_velocity_mps == 1750.0

    def test_get_definition_not_loaded_raises(self) -> None:
        loader = WeaponLoader(_DATA_ROOT / "weapons")
        with pytest.raises(KeyError):
            loader.get_definition("nonexistent")

    def test_m284_howitzer_loaded(self) -> None:
        loader = WeaponLoader(_DATA_ROOT / "weapons")
        loader.load_all()
        defn = loader.get_definition("m284_155mm")
        assert defn.parsed_category() == WeaponCategory.HOWITZER
        assert defn.requires_deployed is True
        assert "m982_excalibur" in defn.compatible_ammo

    def test_aim120_amraam_loaded(self) -> None:
        loader = WeaponLoader(_DATA_ROOT / "weapons")
        loader.load_all()
        defn = loader.get_definition("aim120_amraam")
        assert defn.parsed_category() == WeaponCategory.MISSILE_LAUNCHER
        assert defn.parsed_guidance() == GuidanceType.RADAR_ACTIVE

    def test_mk48_torpedo_loaded(self) -> None:
        loader = WeaponLoader(_DATA_ROOT / "weapons")
        loader.load_all()
        defn = loader.get_definition("mk48_adcap")
        assert defn.parsed_category() == WeaponCategory.TORPEDO_TUBE

    def test_mk15_phalanx_ciws(self) -> None:
        loader = WeaponLoader(_DATA_ROOT / "weapons")
        loader.load_all()
        defn = loader.get_definition("mk15_phalanx")
        assert defn.parsed_category() == WeaponCategory.CIWS
        assert defn.rate_of_fire_rpm == 4500.0

    def test_mk41_vls_loaded(self) -> None:
        loader = WeaponLoader(_DATA_ROOT / "weapons")
        loader.load_all()
        defn = loader.get_definition("mk41_vls")
        assert defn.magazine_capacity == 96
        assert len(defn.compatible_ammo) >= 3


# ---------------------------------------------------------------------------
# AmmoLoader
# ---------------------------------------------------------------------------


class TestAmmoLoader:
    def test_load_all_ammo(self) -> None:
        loader = AmmoLoader(_DATA_ROOT / "ammunition")
        loader.load_all()
        ammo = loader.available_ammo()
        assert len(ammo) >= 15
        assert "m829a3_apfsds" in ammo
        assert "mk48_torpedo_warhead" in ammo

    def test_get_definition(self) -> None:
        loader = AmmoLoader(_DATA_ROOT / "ammunition")
        loader.load_all()
        defn = loader.get_definition("m829a3_apfsds")
        assert defn.parsed_ammo_type() == AmmoType.AP
        assert defn.penetration_mm_rha == 750.0

    def test_heat_round(self) -> None:
        loader = AmmoLoader(_DATA_ROOT / "ammunition")
        loader.load_all()
        defn = loader.get_definition("m830a1_heat_mp")
        assert defn.parsed_ammo_type() == AmmoType.HEAT
        assert defn.blast_radius_m > 0

    def test_guided_excalibur(self) -> None:
        loader = AmmoLoader(_DATA_ROOT / "ammunition")
        loader.load_all()
        defn = loader.get_definition("m982_excalibur")
        assert defn.parsed_guidance() == GuidanceType.GPS
        assert defn.pk_at_reference == 0.9

    def test_dpicm_submunitions(self) -> None:
        loader = AmmoLoader(_DATA_ROOT / "ammunition")
        loader.load_all()
        defn = loader.get_definition("m864_dpicm")
        assert defn.submunition_count == 72

    def test_torpedo_warhead(self) -> None:
        loader = AmmoLoader(_DATA_ROOT / "ammunition")
        loader.load_all()
        defn = loader.get_definition("mk48_torpedo_warhead")
        assert defn.parsed_ammo_type() == AmmoType.TORPEDO
        assert defn.terminal_maneuver is True


# ---------------------------------------------------------------------------
# AmmoState
# ---------------------------------------------------------------------------


class TestAmmoState:
    def test_consume_rounds(self) -> None:
        state = AmmoState(rounds_by_type={"ap": 10})
        assert state.consume("ap", 3) is True
        assert state.available("ap") == 7
        assert state.total_rounds_fired == 3

    def test_consume_insufficient(self) -> None:
        state = AmmoState(rounds_by_type={"ap": 2})
        assert state.consume("ap", 5) is False
        assert state.available("ap") == 2

    def test_consume_unknown_type(self) -> None:
        state = AmmoState()
        assert state.consume("nonexistent", 1) is False

    def test_add_rounds(self) -> None:
        state = AmmoState()
        state.add("he", 50)
        assert state.available("he") == 50
        state.add("he", 30)
        assert state.available("he") == 80

    def test_missile_launch(self) -> None:
        m1 = MissileState(missile_id="m1", ammo_id="amraam")
        m2 = MissileState(missile_id="m2", ammo_id="amraam")
        state = AmmoState(missiles=[m1, m2])
        assert state.ready_missile_count() == 2
        assert state.launch_missile("m1") is True
        assert state.ready_missile_count() == 1
        assert m1.status == "launched"

    def test_launch_nonexistent_missile(self) -> None:
        state = AmmoState()
        assert state.launch_missile("m99") is False

    def test_ready_missile_count_by_type(self) -> None:
        m1 = MissileState(missile_id="m1", ammo_id="amraam")
        m2 = MissileState(missile_id="m2", ammo_id="sidewinder")
        state = AmmoState(missiles=[m1, m2])
        assert state.ready_missile_count("amraam") == 1
        assert state.ready_missile_count("sidewinder") == 1

    def test_state_roundtrip(self) -> None:
        m1 = MissileState(missile_id="m1", ammo_id="amraam", status="launched")
        state = AmmoState(
            rounds_by_type={"ap": 10, "he": 5},
            missiles=[m1],
            total_rounds_fired=3,
        )
        saved = state.get_state()
        restored = AmmoState()
        restored.set_state(saved)
        assert restored.available("ap") == 10
        assert restored.total_rounds_fired == 3
        assert len(restored.missiles) == 1
        assert restored.missiles[0].status == "launched"


# ---------------------------------------------------------------------------
# MissileState
# ---------------------------------------------------------------------------


class TestMissileState:
    def test_default_status(self) -> None:
        m = MissileState(missile_id="m1", ammo_id="amraam")
        assert m.status == "ready"

    def test_state_roundtrip(self) -> None:
        m = MissileState(missile_id="m1", ammo_id="amraam", status="launched", ready_time=100.0)
        saved = m.get_state()
        m2 = MissileState(missile_id="", ammo_id="")
        m2.set_state(saved)
        assert m2.missile_id == "m1"
        assert m2.status == "launched"
        assert m2.ready_time == 100.0


# ---------------------------------------------------------------------------
# WeaponInstance
# ---------------------------------------------------------------------------


class TestWeaponInstance:
    def _make_weapon(
        self,
        ammo_rounds: dict[str, int] | None = None,
        condition: float = 1.0,
    ) -> WeaponInstance:
        defn = WeaponDefinition(
            weapon_id="test_gun",
            display_name="Test Gun",
            category="CANNON",
            caliber_mm=120.0,
            compatible_ammo=["ap", "he"],
            barrel_life_rounds=100,
        )
        equip = EquipmentItem(
            equipment_id="e1", name="Test Gun", category=EquipmentCategory.WEAPON,
            condition=condition,
        )
        ammo = AmmoState(rounds_by_type=ammo_rounds or {"ap": 10, "he": 5})
        return WeaponInstance(definition=defn, ammo_state=ammo, equipment=equip)

    def test_can_fire_with_ammo(self) -> None:
        wi = self._make_weapon()
        assert wi.can_fire("ap") is True

    def test_cannot_fire_incompatible_ammo(self) -> None:
        wi = self._make_weapon()
        assert wi.can_fire("smoke") is False

    def test_cannot_fire_when_inoperational(self) -> None:
        wi = self._make_weapon(condition=0.0)
        wi.equipment.operational = False
        assert wi.can_fire("ap") is False

    def test_fire_consumes_ammo(self) -> None:
        wi = self._make_weapon()
        assert wi.fire("ap") is True
        assert wi.ammo_state.available("ap") == 9

    def test_fire_fails_no_ammo(self) -> None:
        wi = self._make_weapon(ammo_rounds={"ap": 0, "he": 5})
        assert wi.fire("ap") is False

    def test_barrel_wear_degrades_condition(self) -> None:
        wi = self._make_weapon()
        initial_condition = wi.condition
        for _ in range(50):
            wi.fire("ap")
        assert wi.condition < initial_condition

    def test_reload_adds_ammo(self) -> None:
        wi = self._make_weapon()
        wi.reload("ap", 20)
        assert wi.ammo_state.available("ap") == 30

    def test_operational_without_equipment(self) -> None:
        defn = WeaponDefinition(
            weapon_id="bare", display_name="Bare", category="CANNON",
            caliber_mm=10.0, compatible_ammo=["ap"],
        )
        wi = WeaponInstance(definition=defn)
        assert wi.operational is True

    def test_weapon_id_property(self) -> None:
        wi = self._make_weapon()
        assert wi.weapon_id == "test_gun"

    def test_state_roundtrip(self) -> None:
        wi = self._make_weapon()
        wi.fire("ap")
        wi.fire("ap")
        saved = wi.get_state()

        wi2 = self._make_weapon()
        wi2.set_state(saved)
        assert wi2.ammo_state.available("ap") == 8
        assert wi2._rounds_since_maintenance == 2
