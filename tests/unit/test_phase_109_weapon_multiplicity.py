"""Typed declaration proofs for Phase 109 composite weapon multiplicity."""

from __future__ import annotations

from collections import Counter

import pytest

from stochastic_warfare.combat.ammunition import WeaponCategory
from stochastic_warfare.core.types import Domain
from stochastic_warfare.simulation import equipment_mappings
from stochastic_warfare.simulation.loadouts import (
    EquipmentMappingError,
    EquipmentMappingRegistry,
    ReferenceKind,
    WeaponAttachmentMapping,
    WeaponModeledRole,
    equipment_name_declares_system_count,
)


_EXPECTED_SYSTEM_COUNTS = {
    "30.5cm SK L/50 Gun (5x2 turrets)": (10, 1),
    "BL 12-inch Mk X Gun (4x2 turrets)": (8, 1),
    "BL 13.5-inch Mk V Gun (5x2 turrets)": (10, 1),
    "15cm SK L/45 Gun (x14)": (14, 1),
    "QF 4-inch Mk III Gun (x16)": (16, 1),
    "BL 6-inch Mk VII Gun (x12)": (12, 1),
    "QF 4-inch Mk IV Gun (x3)": (3, 1),
    "8.8cm SK L/45 FlaK (x6)": (6, 1),
    "16-inch/50 Mk 7 Gun (3x3 turrets)": (9, 1),
    "18-inch Torpedo Tubes (x5)": (5, 1),
    "21-inch Torpedo Tubes (x2x2)": (4, 1),
    "21-inch Torpedo Tubes (x4)": (4, 1),
    "45cm Torpedo Tubes (x4)": (4, 1),
    "50cm Torpedo Tubes (x5)": (5, 1),
    "QF 18-Pounder Field Gun (x4)": (4, 1),
    "QF 3-inch AA Gun (x2)": (2, 1),
    "18-pdr Long Guns (upper deck, x30)": (30, 1),
    "18-pdr Long Guns (upper deck, x34)": (34, 1),
    "24-pdr Long Guns (middle deck, x34)": (34, 1),
    "24-pdr Long Guns (x26)": (26, 1),
    "32-pdr Long Guns (lower deck, x28)": (28, 1),
    "32-pdr Long Guns (lower deck, x32)": (32, 1),
    "5-inch/38 Mk 12 Gun (10x2 turrets)": (20, 1),
    "5-inch/38 Mk 12 Gun (4x2 turrets)": (8, 1),
    "5-inch/38 Mk 12 Gun (x5)": (5, 1),
    "Type 89 12.7cm AA Gun (8x2)": (16, 1),
    "9-pdr Guns (quarterdeck/forecastle, x16)": (16, 1),
    "9-pdr Long Guns (x18)": (18, 1),
    "7.7cm FK 96 n.A. Field Gun (x4)": (4, 1),
    "Ballistae (x2)": (2, 1),
    "Carronades 24-pdr (x2)": (2, 1),
    "Carronades 32-pdr (x6)": (6, 1),
    "Congreve Rocket Launcher Tripod (x4)": (4, 1),
    "LMG 08/15 Spandau MG (x2)": (2, 1),
    "Browning .303 Machine Gun (x4)": (4, 1),
    "M2 Browning .50 Cal (x13)": (13, 1),
    "M2 Browning .50 Cal (x6)": (6, 1),
    "MG 08 Machine Gun (x6)": (6, 1),
    "Hispano Mk II 20mm Cannon (x2)": (2, 1),
    "MG 131 13mm Machine Gun (x2)": (2, 1),
    "Mk 15 Torpedo Tubes (2x5)": (10, 10),
    "533mm Torpedo Tubes x6": (6, 1),
    "Harpoon Quad Launchers (x2)": (8, 8),
    "Mk 141 Harpoon Quad Launchers (x4)": (16, 16),
    "2x S-68 57mm Autocannon": (2, 1),
    "Type 99 Model 2 20mm Cannon (x2)": (2, 1),
    "Type 97 7.7mm MG (x2)": (2, 1),
    "Bofors 40mm Quad Mount (x20)": (80, 1),
    "Bofors 40mm Quad Mount (x8)": (32, 1),
    "Bofors 40mm Twin Mount (x2)": (4, 1),
    "Bofors 40mm Twin Mount (x5)": (10, 1),
    "Oerlikon 20mm (x46)": (46, 1),
    "Oerlikon 20mm (x49)": (49, 1),
    "Oerlikon 20mm (x6)": (6, 1),
    "Oerlikon 20mm (x7)": (7, 1),
    "Type 96 25mm Triple Mount (x12)": (36, 1),
    "Vickers .303 Synchronized MG (x2)": (2, 1),
    "M299 Launchers (x4)": (16, 16),
    "Depth Charge Rails and Throwers (x4)": (4, 1),
    "M60 7.62mm MG (sponson x4)": (4, 1),
    "53.3cm Torpedo Tubes (4 bow, 1 stern)": (5, 1),
    "53.3cm Torpedo Tubes (4 bow, 2 stern)": (6, 1),
}

_TEXTUAL_COUNT_NAMES = {
    "53.3cm Torpedo Tubes (4 bow, 1 stern)",
    "53.3cm Torpedo Tubes (4 bow, 2 stern)",
}


def _mapping(
    equipment_name: str,
    *,
    source_system_count: int = 1,
    target_system_count: int = 1,
) -> WeaponAttachmentMapping:
    return WeaponAttachmentMapping(
        equipment_name=equipment_name,
        weapon_id="test-gun",
        expected_weapon_category=WeaponCategory.CANNON,
        modeled_role=WeaponModeledRole.GROUND_DIRECT_FIRE,
        required_target_domains=(Domain.GROUND,),
        source_system_count=source_system_count,
        target_system_count=target_system_count,
    )


def test_all_reviewed_composite_weapon_names_have_explicit_typed_counts() -> None:
    records = {
        record.equipment_name: record
        for record in equipment_mappings.EQUIPMENT_MAPPING_RECORDS
        if isinstance(record, WeaponAttachmentMapping) and record.source_system_count > 1
    }
    actual = {name: (record.source_system_count, record.target_system_count) for name, record in records.items()}

    # The initial multiplicative-syntax audit found 60 names.  The production
    # declaration also closes the two textual bow/stern encodings discovered
    # while implementing the invariant.
    assert len(set(_EXPECTED_SYSTEM_COUNTS) - _TEXTUAL_COUNT_NAMES) == 60
    assert len(_EXPECTED_SYSTEM_COUNTS) == 62
    assert actual == _EXPECTED_SYSTEM_COUNTS
    assert set(equipment_mappings._WEAPON_SYSTEM_COUNT_INDEX) == set(actual)
    assert all(equipment_name_declares_system_count(name) for name in actual)
    assert Counter(record.reference_kind for record in records.values()) == {
        ReferenceKind.EXACT: 59,
        ReferenceKind.VARIANT: 1,
        ReferenceKind.FUNCTIONAL_ANALOGUE: 2,
    }
    assert {name: record.runtime_system_multiplier for name, record in records.items()} == {
        name: source_count // target_count for name, (source_count, target_count) in _EXPECTED_SYSTEM_COUNTS.items()
    }


def test_count_declarations_reject_duplicates_before_indexing() -> None:
    declaration = equipment_mappings._WeaponSystemCountDeclaration(
        "Synthetic Battery (x2)",
        2,
    )
    with pytest.raises(
        EquipmentMappingError,
        match=r"Duplicate weapon system-count declaration.*indexes 0 and 1",
    ):
        equipment_mappings._checked_weapon_system_count_index(
            (declaration, declaration),
        )


def test_count_bearing_attachment_cannot_use_implicit_single_system_default() -> None:
    with pytest.raises(
        EquipmentMappingError,
        match=r"Count-bearing weapon equipment.*source_system_count",
    ):
        _mapping("Undeclared Battery (x2)")


@pytest.mark.parametrize(
    ("source_system_count", "target_system_count", "expected"),
    (
        (True, 1, "source_system_count"),
        (0, 1, "source_system_count"),
        (1, False, "target_system_count"),
        (1, 0, "target_system_count"),
        (3, 2, "exactly divisible"),
    ),
)
def test_mapping_rejects_malformed_or_fractional_system_counts(
    source_system_count: int,
    target_system_count: int,
    expected: str,
) -> None:
    with pytest.raises(EquipmentMappingError, match=expected):
        _mapping(
            "Synthetic Battery",
            source_system_count=source_system_count,
            target_system_count=target_system_count,
        )


def test_registry_preserves_declared_count_topology() -> None:
    record = _mapping(
        "Synthetic Battery (x4)",
        source_system_count=4,
        target_system_count=2,
    )
    registry = EquipmentMappingRegistry((record,))

    resolved = registry.require(record.category, record.equipment_name)
    assert resolved is record
    assert record.runtime_system_multiplier == 2
