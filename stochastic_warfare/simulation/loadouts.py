"""Compatibility facade for typed runtime loadout construction.

Public definitions live in focused loadout modules.  This facade preserves the
established import surface while keeping dependency flow one-way from contracts
through registry/runtime attachments to the builder.
"""

from stochastic_warfare.simulation.loadout_contracts import (
    DuplicateEquipmentMappingError as DuplicateEquipmentMappingError,
    EquipmentMappingError as EquipmentMappingError,
    EquipmentMappingRecord as EquipmentMappingRecord,
    ReferenceKind as ReferenceKind,
    ResolutionDisposition as ResolutionDisposition,
    SensorAttachmentMapping as SensorAttachmentMapping,
    SensorModeledRole as SensorModeledRole,
    SensorNonRuntimeMapping as SensorNonRuntimeMapping,
    SensorTargetingClass as SensorTargetingClass,
    SensorUnsupportedMapping as SensorUnsupportedMapping,
    UnsupportedEquipmentError as UnsupportedEquipmentError,
    WeaponAttachmentMapping as WeaponAttachmentMapping,
    WeaponModeledRole as WeaponModeledRole,
    WeaponNonRuntimeMapping as WeaponNonRuntimeMapping,
    WeaponStandoffClass as WeaponStandoffClass,
    WeaponStoreMapping as WeaponStoreMapping,
    WeaponUnsupportedMapping as WeaponUnsupportedMapping,
    allowed_shooter_domains_for_sensor_role as allowed_shooter_domains_for_sensor_role,
    compatible_sensor_roles_for_weapon_role as compatible_sensor_roles_for_weapon_role,
    equipment_name_declares_system_count as equipment_name_declares_system_count,
    required_domains_for_sensor_role as required_domains_for_sensor_role,
    required_domains_for_weapon_role as required_domains_for_weapon_role,
    sensor_targeting_class as sensor_targeting_class,
    weapon_role_supports_target_domain as weapon_role_supports_target_domain,
    weapon_standoff_class as weapon_standoff_class,
)
from stochastic_warfare.simulation.loadout_registry import (
    EquipmentMappingRegistry as EquipmentMappingRegistry,
)
from stochastic_warfare.simulation.runtime_attachments import (
    EquipmentResolution as EquipmentResolution,
    RuntimeLoadouts as RuntimeLoadouts,
    SensorAttachment as SensorAttachment,
    WeaponAssignment as WeaponAssignment,
    WeaponAttachment as WeaponAttachment,
)
from stochastic_warfare.simulation.loadout_builder import (
    RuntimeLoadoutBuilder as RuntimeLoadoutBuilder,
)

__all__ = [
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
