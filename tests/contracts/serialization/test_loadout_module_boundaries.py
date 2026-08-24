"""Compatibility contracts for the mechanical loadout-module split."""

from __future__ import annotations

import pytest

from stochastic_warfare.simulation import loadout_builder
from stochastic_warfare.simulation import loadout_contracts
from stochastic_warfare.simulation import loadout_registry
from stochastic_warfare.simulation import loadouts as facade
from stochastic_warfare.simulation import runtime_attachments


pytestmark = pytest.mark.test_evidence("structural_only")


def test_compatibility_facade_reexports_owner_identity() -> None:
    """The legacy path exposes each owner definition, not a wrapper copy."""
    owners = {
        "DuplicateEquipmentMappingError": loadout_contracts,
        "EquipmentMappingError": loadout_contracts,
        "EquipmentMappingRecord": loadout_contracts,
        "EquipmentMappingRegistry": loadout_registry,
        "EquipmentResolution": runtime_attachments,
        "ReferenceKind": loadout_contracts,
        "ResolutionDisposition": loadout_contracts,
        "RuntimeLoadoutBuilder": loadout_builder,
        "RuntimeLoadouts": runtime_attachments,
        "SensorAttachment": runtime_attachments,
        "SensorAttachmentMapping": loadout_contracts,
        "SensorModeledRole": loadout_contracts,
        "SensorNonRuntimeMapping": loadout_contracts,
        "SensorTargetingClass": loadout_contracts,
        "SensorUnsupportedMapping": loadout_contracts,
        "UnsupportedEquipmentError": loadout_contracts,
        "WeaponAssignment": runtime_attachments,
        "WeaponAttachment": runtime_attachments,
        "WeaponAttachmentMapping": loadout_contracts,
        "WeaponModeledRole": loadout_contracts,
        "WeaponNonRuntimeMapping": loadout_contracts,
        "WeaponStandoffClass": loadout_contracts,
        "WeaponStoreMapping": loadout_contracts,
        "WeaponUnsupportedMapping": loadout_contracts,
        "allowed_shooter_domains_for_sensor_role": loadout_contracts,
        "compatible_sensor_roles_for_weapon_role": loadout_contracts,
        "equipment_name_declares_system_count": loadout_contracts,
        "required_domains_for_sensor_role": loadout_contracts,
        "required_domains_for_weapon_role": loadout_contracts,
        "sensor_targeting_class": loadout_contracts,
        "weapon_role_supports_target_domain": loadout_contracts,
        "weapon_standoff_class": loadout_contracts,
    }
    assert {
        name: getattr(facade, name) is getattr(owner, name)
        for name, owner in owners.items()
    } == dict.fromkeys(owners, True)


def test_owner_dependencies_share_contract_objects() -> None:
    """Focused modules consume the same contract and attachment definitions."""
    assert (
        loadout_registry.EquipmentMappingRecord
        is loadout_contracts.EquipmentMappingRecord
    )
    assert (
        runtime_attachments._sha256_payload
        is loadout_contracts._sha256_payload
    )
    assert loadout_builder.RuntimeLoadouts is runtime_attachments.RuntimeLoadouts


def test_facade_preserves_ordered_public_loadout_surface() -> None:
    """Wildcard imports retain the established ordered compatibility API."""
    assert facade.__all__ == [
        "DuplicateEquipmentMappingError",
        "EquipmentMappingError",
        "EquipmentMappingRecord",
        "EquipmentMappingRegistry",
        "EquipmentResolution",
        "ReferenceKind",
        "ResolutionDisposition",
        "RuntimeLoadoutBuilder",
        "RuntimeLoadouts",
        "SensorAttachment",
        "SensorAttachmentMapping",
        "SensorModeledRole",
        "SensorNonRuntimeMapping",
        "SensorTargetingClass",
        "SensorUnsupportedMapping",
        "UnsupportedEquipmentError",
        "WeaponAssignment",
        "WeaponAttachment",
        "WeaponAttachmentMapping",
        "WeaponModeledRole",
        "WeaponNonRuntimeMapping",
        "WeaponStandoffClass",
        "WeaponStoreMapping",
        "WeaponUnsupportedMapping",
        "allowed_shooter_domains_for_sensor_role",
        "compatible_sensor_roles_for_weapon_role",
        "equipment_name_declares_system_count",
        "required_domains_for_sensor_role",
        "required_domains_for_weapon_role",
        "sensor_targeting_class",
        "weapon_role_supports_target_domain",
        "weapon_standoff_class",
    ]
