"""Tests for logistics/supply_classes.py -- enums, items, inventory, loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from stochastic_warfare.logistics.supply_classes import (
    FuelType,
    SupplyClass,
    SupplyInventory,
    SupplyItemDefinition,
    SupplyItemLoader,
    SupplyRequirement,
)


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestSupplyClassEnum:
    def test_class_i_food(self) -> None:
        assert SupplyClass.CLASS_I == 1

    def test_class_iii_fuel(self) -> None:
        assert SupplyClass.CLASS_III == 3

    def test_class_iiia_aviation_fuel(self) -> None:
        assert SupplyClass.CLASS_IIIA == 30

    def test_class_v_ammo(self) -> None:
        assert SupplyClass.CLASS_V == 5

    def test_class_viii_medical(self) -> None:
        assert SupplyClass.CLASS_VIII == 8

    def test_class_ix_spare_parts(self) -> None:
        assert SupplyClass.CLASS_IX == 9

    def test_all_members(self) -> None:
        assert len(SupplyClass) == 9


class TestFuelTypeEnum:
    def test_diesel(self) -> None:
        assert FuelType.DIESEL == 0

    def test_jp8(self) -> None:
        assert FuelType.JP8 == 1

    def test_nuclear(self) -> None:
        assert FuelType.NUCLEAR == 4

    def test_all_members(self) -> None:
        assert len(FuelType) == 5


# ---------------------------------------------------------------------------
# SupplyItemDefinition
# ---------------------------------------------------------------------------


class TestSupplyItemDefinition:
    def test_basic_construction(self) -> None:
        defn = SupplyItemDefinition(
            item_id="ration_mre",
            supply_class="CLASS_I",
            display_name="MRE",
            weight_per_unit_kg=0.85,
            volume_per_unit_m3=0.002,
        )
        assert defn.item_id == "ration_mre"
        assert defn.weight_per_unit_kg == 0.85

    def test_supply_class_enum_property(self) -> None:
        defn = SupplyItemDefinition(
            item_id="fuel_diesel",
            supply_class="CLASS_III",
            display_name="Diesel",
            weight_per_unit_kg=0.85,
            volume_per_unit_m3=0.001,
        )
        assert defn.supply_class_enum == SupplyClass.CLASS_III

    def test_perishable_defaults_false(self) -> None:
        defn = SupplyItemDefinition(
            item_id="x",
            supply_class="CLASS_IX",
            display_name="Parts",
            weight_per_unit_kg=1.0,
            volume_per_unit_m3=0.01,
        )
        assert defn.perishable is False
        assert defn.shelf_life_hours is None

    def test_perishable_with_shelf_life(self) -> None:
        defn = SupplyItemDefinition(
            item_id="blood_unit",
            supply_class="CLASS_VIII",
            display_name="Blood",
            weight_per_unit_kg=0.5,
            volume_per_unit_m3=0.0005,
            perishable=True,
            shelf_life_hours=1008.0,
        )
        assert defn.perishable is True
        assert defn.shelf_life_hours == 1008.0

    def test_model_validate(self) -> None:
        data = {
            "item_id": "test_item",
            "supply_class": "CLASS_V",
            "display_name": "Test",
            "weight_per_unit_kg": 10.0,
            "volume_per_unit_m3": 0.05,
        }
        defn = SupplyItemDefinition.model_validate(data)
        assert defn.supply_class_enum == SupplyClass.CLASS_V


# ---------------------------------------------------------------------------
# SupplyItemLoader
# ---------------------------------------------------------------------------


class TestSupplyItemLoader:
    def test_load_all_yaml(self) -> None:
        loader = SupplyItemLoader()
        loader.load_all()
        items = loader.available_items()
        assert len(items) >= 14  # 3 + 4 + 4 + 3 + 4 across 5 files

    def test_get_known_item(self) -> None:
        loader = SupplyItemLoader()
        loader.load_all()
        defn = loader.get_definition("ration_mre")
        assert defn.display_name == "MRE (Meal Ready to Eat)"
        assert defn.supply_class_enum == SupplyClass.CLASS_I

    def test_get_fuel_item(self) -> None:
        loader = SupplyItemLoader()
        loader.load_all()
        defn = loader.get_definition("fuel_diesel")
        assert defn.supply_class_enum == SupplyClass.CLASS_III

    def test_get_unknown_raises(self) -> None:
        loader = SupplyItemLoader()
        with pytest.raises(KeyError):
            loader.get_definition("nonexistent_item")

    def test_load_custom_directory(self, tmp_path: Path) -> None:
        import yaml

        item = {
            "item_id": "custom_item",
            "supply_class": "CLASS_X",
            "display_name": "Custom",
            "weight_per_unit_kg": 1.0,
            "volume_per_unit_m3": 0.01,
        }
        (tmp_path / "custom.yaml").write_text(yaml.dump(item))
        loader = SupplyItemLoader(data_dir=tmp_path)
        loader.load_all()
        assert "custom_item" in loader.available_items()

    def test_load_list_yaml(self, tmp_path: Path) -> None:
        import yaml

        items = [
            {
                "item_id": "a",
                "supply_class": "CLASS_I",
                "display_name": "A",
                "weight_per_unit_kg": 1.0,
                "volume_per_unit_m3": 0.01,
            },
            {
                "item_id": "b",
                "supply_class": "CLASS_I",
                "display_name": "B",
                "weight_per_unit_kg": 2.0,
                "volume_per_unit_m3": 0.02,
            },
        ]
        (tmp_path / "list.yaml").write_text(yaml.dump(items))
        loader = SupplyItemLoader(data_dir=tmp_path)
        loader.load_all()
        assert "a" in loader.available_items()
        assert "b" in loader.available_items()


# ---------------------------------------------------------------------------
# SupplyInventory
# ---------------------------------------------------------------------------


class TestSupplyInventory:
    def test_add_and_available(self) -> None:
        inv = SupplyInventory()
        inv.add(int(SupplyClass.CLASS_I), "ration_mre", 100.0)
        assert inv.available(int(SupplyClass.CLASS_I), "ration_mre") == 100.0

    def test_add_accumulates(self) -> None:
        inv = SupplyInventory()
        inv.add(1, "ration_mre", 50.0)
        inv.add(1, "ration_mre", 30.0)
        assert inv.available(1, "ration_mre") == 80.0

    def test_consume_full(self) -> None:
        inv = SupplyInventory()
        inv.add(3, "fuel_diesel", 200.0)
        consumed = inv.consume(3, "fuel_diesel", 200.0)
        assert consumed == 200.0
        assert inv.available(3, "fuel_diesel") == 0.0

    def test_consume_partial(self) -> None:
        inv = SupplyInventory()
        inv.add(3, "fuel_diesel", 50.0)
        consumed = inv.consume(3, "fuel_diesel", 100.0)
        assert consumed == 50.0
        assert inv.available(3, "fuel_diesel") == 0.0

    def test_consume_missing_class(self) -> None:
        inv = SupplyInventory()
        consumed = inv.consume(99, "nonexistent", 10.0)
        assert consumed == 0.0

    def test_consume_missing_item(self) -> None:
        inv = SupplyInventory()
        inv.add(1, "ration_mre", 100.0)
        consumed = inv.consume(1, "nonexistent", 10.0)
        assert consumed == 0.0

    def test_available_empty(self) -> None:
        inv = SupplyInventory()
        assert inv.available(1, "ration_mre") == 0.0

    def test_total_by_class(self) -> None:
        inv = SupplyInventory()
        inv.add(1, "ration_mre", 100.0)
        inv.add(1, "water_potable", 200.0)
        assert inv.total_by_class(1) == 300.0

    def test_total_by_class_empty(self) -> None:
        inv = SupplyInventory()
        assert inv.total_by_class(99) == 0.0

    def test_fraction_of(self) -> None:
        inv = SupplyInventory()
        inv.add(3, "fuel_diesel", 75.0)
        assert inv.fraction_of(3, "fuel_diesel", 100.0) == 0.75

    def test_fraction_of_zero_max(self) -> None:
        inv = SupplyInventory()
        assert inv.fraction_of(3, "fuel_diesel", 0.0) == 0.0

    def test_fraction_of_over_max(self) -> None:
        inv = SupplyInventory()
        inv.add(3, "fuel_diesel", 150.0)
        assert inv.fraction_of(3, "fuel_diesel", 100.0) == 1.0

    def test_classes_present(self) -> None:
        inv = SupplyInventory()
        inv.add(1, "ration_mre", 10.0)
        inv.add(3, "fuel_diesel", 20.0)
        inv.add(5, "ammo_762", 0.0)  # zero — should NOT appear
        assert inv.classes_present() == [1, 3]

    def test_total_weight_no_loader(self) -> None:
        inv = SupplyInventory()
        inv.add(1, "ration_mre", 100.0)
        inv.add(3, "fuel_diesel", 50.0)
        # Without loader, each unit counts as 1 kg
        assert inv.total_weight() == 150.0

    def test_total_weight_with_loader(self) -> None:
        loader = SupplyItemLoader()
        loader.load_all()
        inv = SupplyInventory()
        inv.add(int(SupplyClass.CLASS_I), "ration_mre", 10.0)
        weight = inv.total_weight(loader)
        assert weight == pytest.approx(10.0 * 0.85)


# ---------------------------------------------------------------------------
# SupplyInventory state round-trip
# ---------------------------------------------------------------------------


class TestSupplyInventoryState:
    def test_get_set_state(self) -> None:
        inv = SupplyInventory()
        inv.add(1, "ration_mre", 100.0)
        inv.add(3, "fuel_diesel", 200.0)
        state = inv.get_state()

        inv2 = SupplyInventory()
        inv2.set_state(state)
        assert inv2.available(1, "ration_mre") == 100.0
        assert inv2.available(3, "fuel_diesel") == 200.0

    def test_set_state_clears_previous(self) -> None:
        inv = SupplyInventory()
        inv.add(1, "ration_mre", 100.0)
        inv.set_state({"items": {}})
        assert inv.available(1, "ration_mre") == 0.0


# ---------------------------------------------------------------------------
# SupplyRequirement
# ---------------------------------------------------------------------------


class TestSupplyRequirement:
    def test_namedtuple(self) -> None:
        req = SupplyRequirement(
            supply_class=int(SupplyClass.CLASS_III),
            item_id="fuel_diesel",
            rate_per_hour=10.0,
            minimum_reserve=50.0,
        )
        assert req.supply_class == 3
        assert req.item_id == "fuel_diesel"
        assert req.rate_per_hour == 10.0
        assert req.minimum_reserve == 50.0

    def test_unpacking(self) -> None:
        req = SupplyRequirement(1, "ration_mre", 0.104, 5.0)
        cls, item, rate, reserve = req
        assert cls == 1
        assert item == "ration_mre"
        assert rate == 0.104
        assert reserve == 5.0
