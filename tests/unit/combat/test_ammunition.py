"""Unit tests for WeaponDefinition, AmmoDefinition, WeaponInstance, AmmoState."""

from __future__ import annotations

import pytest

from stochastic_warfare.combat.ammunition import (
    AmmoState,
    MissileState,
    WeaponDefinition,
    WeaponInstance,
)
from stochastic_warfare.entities.equipment import EquipmentCategory, EquipmentItem

from .conftest import _make_ap, _make_gun, _make_weapon_instance


# ---------------------------------------------------------------------------
# WeaponDefinition
# ---------------------------------------------------------------------------


class TestWeaponDefinition:
    """WeaponDefinition validation and domain inference."""

    def test_effective_target_domains_cannon(self):
        gun = _make_gun(category="CANNON")
        domains = gun.effective_target_domains()
        assert "GROUND" in domains
        assert "AERIAL" in domains

    def test_effective_target_domains_torpedo(self):
        torp = _make_gun(category="TORPEDO_TUBE")
        domains = torp.effective_target_domains()
        assert "NAVAL" in domains or "SUBMARINE" in domains

    def test_explicit_target_domains_override(self):
        gun = _make_gun()
        gun_dict = gun.model_dump()
        gun_dict["target_domains"] = ["NAVAL"]
        custom = WeaponDefinition.model_validate(gun_dict)
        assert custom.effective_target_domains() == {"NAVAL"}

    def test_get_effective_range_default(self):
        gun = _make_gun(max_range_m=4000.0)
        assert gun.get_effective_range() == pytest.approx(3200.0)

    def test_get_effective_range_explicit(self):
        gun = WeaponDefinition(
            weapon_id="t", display_name="T", category="CANNON",
            caliber_mm=120.0, max_range_m=4000.0, effective_range_m=2500.0,
        )
        assert gun.get_effective_range() == 2500.0

    def test_parsed_category(self):
        gun = _make_gun(category="MACHINE_GUN")
        from stochastic_warfare.combat.ammunition import WeaponCategory
        assert gun.parsed_category() == WeaponCategory.MACHINE_GUN


# ---------------------------------------------------------------------------
# AmmoDefinition
# ---------------------------------------------------------------------------


class TestAmmoDefinition:
    def test_parsed_ammo_type(self):
        ammo = _make_ap()
        from stochastic_warfare.combat.ammunition import AmmoType
        assert ammo.parsed_ammo_type() == AmmoType.AP

    def test_parsed_guidance(self):
        ammo = _make_ap()
        from stochastic_warfare.combat.ammunition import GuidanceType
        assert ammo.parsed_guidance() == GuidanceType.NONE


# ---------------------------------------------------------------------------
# AmmoState
# ---------------------------------------------------------------------------


class TestAmmoState:
    def test_consume_success(self):
        state = AmmoState()
        state.add("ap", 10)
        assert state.consume("ap", 3)
        assert state.available("ap") == 7
        assert state.total_rounds_fired == 3

    def test_consume_insufficient(self):
        state = AmmoState()
        state.add("ap", 2)
        assert not state.consume("ap", 5)
        assert state.available("ap") == 2

    def test_consume_independent_types(self):
        state = AmmoState()
        state.add("ap", 10)
        state.add("he", 20)
        state.consume("ap", 5)
        assert state.available("ap") == 5
        assert state.available("he") == 20

    def test_zero_rounds_edge(self):
        state = AmmoState()
        assert state.available("ap") == 0
        assert not state.consume("ap")

    def test_launch_missile(self):
        state = AmmoState()
        state.missiles.append(MissileState(missile_id="m1", ammo_id="atgm"))
        assert state.ready_missile_count() == 1
        assert state.launch_missile("m1")
        assert state.ready_missile_count() == 0

    def test_launch_missile_not_ready(self):
        state = AmmoState()
        state.missiles.append(MissileState(missile_id="m1", ammo_id="atgm", status="launched"))
        assert not state.launch_missile("m1")

    def test_ready_missile_count_filtered(self):
        state = AmmoState()
        state.missiles.append(MissileState(missile_id="m1", ammo_id="atgm"))
        state.missiles.append(MissileState(missile_id="m2", ammo_id="sam"))
        assert state.ready_missile_count("atgm") == 1
        assert state.ready_missile_count("sam") == 1
        assert state.ready_missile_count() == 2

    def test_state_roundtrip(self):
        state = AmmoState()
        state.add("ap", 10)
        state.missiles.append(MissileState(missile_id="m1", ammo_id="atgm"))
        state.consume("ap", 3)
        s = state.get_state()
        state2 = AmmoState()
        state2.set_state(s)
        assert state2.available("ap") == 7
        assert state2.total_rounds_fired == 3
        assert len(state2.missiles) == 1


# ---------------------------------------------------------------------------
# WeaponInstance
# ---------------------------------------------------------------------------


class TestWeaponInstance:
    def test_can_fire_with_ammo(self):
        wi = _make_weapon_instance(rounds=10)
        assert wi.can_fire("test_ap")

    def test_can_fire_no_ammo(self):
        wi = _make_weapon_instance(rounds=0)
        assert not wi.can_fire("test_ap")

    def test_fire_cooldown(self):
        gun = _make_gun(rate_of_fire_rpm=60.0)  # 1 round/s
        wi = _make_weapon_instance(weapon=gun)
        assert wi.can_fire_timed(0.0)
        wi.record_fire(0.0)
        assert not wi.can_fire_timed(0.5)  # only 0.5s elapsed
        assert wi.can_fire_timed(1.0)  # 1.0s elapsed = cooldown met

    def test_fire_consumes_ammo(self):
        wi = _make_weapon_instance(rounds=5)
        assert wi.fire("test_ap")
        assert wi.ammo_state.available("test_ap") == 4

    def test_barrel_wear_degradation(self):
        gun = _make_gun(barrel_life_rounds=100)
        wi = _make_weapon_instance(weapon=gun, rounds=200)
        assert wi.condition == pytest.approx(1.0)
        for _ in range(50):
            wi.fire("test_ap")
        assert wi.condition == pytest.approx(0.5)

    def test_operational_with_broken_equipment(self):
        gun = _make_gun()
        equip = EquipmentItem(
            equipment_id="eq1", name="Gun", category=EquipmentCategory.WEAPON,
            condition=0.0, operational=False,
        )
        wi = WeaponInstance(definition=gun, equipment=equip)
        assert not wi.operational
        assert not wi.can_fire("test_ap")

    def test_state_roundtrip(self):
        wi = _make_weapon_instance(rounds=20)
        wi.fire("test_ap")
        wi.record_fire(5.0)
        state = wi.get_state()
        wi2 = _make_weapon_instance(rounds=20)
        wi2.set_state(state)
        assert wi2.ammo_state.available("test_ap") == 19
        assert wi2._rounds_since_maintenance == 1
