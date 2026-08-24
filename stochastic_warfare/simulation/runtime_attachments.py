"""Immutable runtime weapon, sensor, resolution, and loadout attachments."""

from __future__ import annotations

from collections.abc import Collection, Iterator, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from stochastic_warfare.combat.ammunition import (
    AmmoDefinition,
    WeaponInstance,
)
from stochastic_warfare.detection.sensors import (
    SensorInstance,
)
from stochastic_warfare.detection.sensor_roles import SensorModeledRole
from stochastic_warfare.entities.equipment import EquipmentCategory, EquipmentItem
from stochastic_warfare.simulation.loadout_contracts import (
    ReferenceKind,
    ResolutionDisposition,
    WeaponModeledRole,
    _require_enum,
    _require_enum_tuple,
    _require_optional_trimmed,
    _require_source_index,
    _require_trimmed,
    _sha256_payload,
    _validate_live_reference_provenance,
    _validate_system_counts,
)


@dataclass(frozen=True, slots=True)
class WeaponAssignment:
    """One typed scenario-local weapon target override."""

    equipment_name: str
    weapon_id: str

    def __post_init__(self) -> None:
        _require_trimmed(self.equipment_name, "assignment equipment_name")
        _require_trimmed(self.weapon_id, "assignment weapon_id")


@dataclass(frozen=True, slots=True)
class WeaponAttachment:
    """One live weapon plus its immutable catalog/source links."""

    weapon: WeaponInstance
    ammunition: tuple[AmmoDefinition, ...]
    source_equipment: EquipmentItem
    source_equipment_index: int
    modeled_role: WeaponModeledRole
    reference_kind: ReferenceKind
    mapping_rationale: str | None
    mapping_source: str | None
    source_system_count: int
    target_system_count: int
    runtime_system_multiplier: int

    def __post_init__(self) -> None:
        if self.weapon.equipment is not self.source_equipment:
            raise ValueError(
                "WeaponAttachment source_equipment must be the exact object "
                "linked by its WeaponInstance",
            )
        if not isinstance(self.ammunition, tuple) or not self.ammunition:
            raise ValueError("WeaponAttachment ammunition must be a non-empty tuple")
        _require_source_index(
            self.source_equipment_index,
            "source_equipment_index",
        )
        _require_enum(self.modeled_role, WeaponModeledRole, "modeled_role")
        _validate_live_reference_provenance(
            reference_kind=self.reference_kind,
            mapping_rationale=self.mapping_rationale,
            mapping_source=self.mapping_source,
        )
        expected_multiplier = _validate_system_counts(
            equipment_name=self.source_equipment.name,
            source_system_count=self.source_system_count,
            target_system_count=self.target_system_count,
        )
        if self.runtime_system_multiplier != expected_multiplier:
            raise ValueError(
                "WeaponAttachment runtime_system_multiplier must equal "
                "source_system_count // target_system_count",
            )

    @property
    def weapon_instance(self) -> WeaponInstance:
        """Explicit alias for consumers migrating from tuple-shaped entries."""
        return self.weapon

    @property
    def ammo_definitions(self) -> tuple[AmmoDefinition, ...]:
        return self.ammunition

    def first_fireable_ammunition(
        self,
        *,
        excluded_ammo_ids: Collection[str] = (),
    ) -> AmmoDefinition | None:
        """Return the first currently usable definition in declaration order."""
        return next(
            (
                ammunition
                for ammunition in self.ammunition
                if (
                    ammunition.ammo_id not in excluded_ammo_ids
                    and self.weapon.can_fire(ammunition.ammo_id)
                )
            ),
            None,
        )

    def __iter__(self) -> Iterator[WeaponInstance | tuple[AmmoDefinition, ...]]:
        """Preserve tuple unpacking while callers migrate to named fields."""
        yield self.weapon
        yield self.ammunition

    def __len__(self) -> int:
        return 2

    def __getitem__(
        self,
        index: int,
    ) -> WeaponInstance | tuple[AmmoDefinition, ...]:
        return (self.weapon, self.ammunition)[index]


@dataclass(frozen=True, slots=True)
class SensorAttachment:
    """One live sensor plus immutable mapping and fire-control bindings."""

    sensor: SensorInstance
    source_equipment: EquipmentItem
    source_equipment_index: int
    modeled_role: SensorModeledRole
    reference_kind: ReferenceKind
    mapping_rationale: str | None
    mapping_source: str | None
    compatible_weapon_roles: tuple[WeaponModeledRole, ...]
    compatible_weapon_source_indexes: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.sensor.equipment is not self.source_equipment:
            raise ValueError(
                "SensorAttachment source_equipment must be the exact object "
                "linked by its SensorInstance",
            )
        _require_source_index(
            self.source_equipment_index,
            "source_equipment_index",
        )
        _require_enum(self.modeled_role, SensorModeledRole, "modeled_role")
        _validate_live_reference_provenance(
            reference_kind=self.reference_kind,
            mapping_rationale=self.mapping_rationale,
            mapping_source=self.mapping_source,
        )
        _require_enum_tuple(
            self.compatible_weapon_roles,
            WeaponModeledRole,
            "compatible_weapon_roles",
        )
        if not isinstance(self.compatible_weapon_source_indexes, tuple):
            raise ValueError(
                "compatible_weapon_source_indexes must be an immutable tuple",
            )
        if tuple(sorted(self.compatible_weapon_source_indexes)) != (
            self.compatible_weapon_source_indexes
        ):
            raise ValueError(
                "compatible_weapon_source_indexes must be in source order",
            )
        if len(self.compatible_weapon_source_indexes) != len(
            set(self.compatible_weapon_source_indexes),
        ):
            raise ValueError(
                "compatible_weapon_source_indexes contains duplicates",
            )
        for index in self.compatible_weapon_source_indexes:
            if (
                not isinstance(index, int)
                or isinstance(index, bool)
                or index < 0
            ):
                raise ValueError(
                    "compatible_weapon_source_indexes must contain only "
                    "non-negative integers",
                )

    @property
    def sensor_instance(self) -> SensorInstance:
        """Return the exact compatibility-projection object."""
        return self.sensor

    @property
    def sensor_id(self) -> str:
        return self.sensor.sensor_id


@dataclass(frozen=True, slots=True)
class EquipmentResolution:
    """Transparent outcome for one mapped runtime equipment item."""

    unit_id: str
    unit_type: str
    source_equipment: EquipmentItem
    source_equipment_index: int
    category: EquipmentCategory
    disposition: ResolutionDisposition
    modeled_role: WeaponModeledRole | SensorModeledRole | None = None
    reference_kind: ReferenceKind | None = None
    target_id: str | None = None
    attached_to_equipment_index: int | None = None
    attached_to_target_id: str | None = None
    reason: str | None = None
    source_system_count: int | None = None
    target_system_count: int | None = None
    runtime_system_multiplier: int | None = None

    def __post_init__(self) -> None:
        _require_trimmed(self.unit_id, "resolution unit_id")
        _require_trimmed(self.unit_type, "resolution unit_type")
        _require_source_index(
            self.source_equipment_index,
            "source_equipment_index",
        )
        if self.attached_to_equipment_index is not None:
            _require_source_index(
                self.attached_to_equipment_index,
                "attached_to_equipment_index",
            )
        _require_enum(self.category, EquipmentCategory, "resolution category")
        if self.source_equipment.category is not self.category:
            raise ValueError(
                "resolution category must match the exact source equipment",
            )
        _require_enum(
            self.disposition,
            ResolutionDisposition,
            "resolution disposition",
        )
        if self.reference_kind is not None:
            _require_enum(
                self.reference_kind,
                ReferenceKind,
                "resolution reference_kind",
            )
        if self.modeled_role is not None and not isinstance(
            self.modeled_role,
            (WeaponModeledRole, SensorModeledRole),
        ):
            raise ValueError(
                "resolution modeled_role must be a typed weapon or sensor role",
            )
        _require_optional_trimmed(self.target_id, "resolution target_id")
        _require_optional_trimmed(
            self.attached_to_target_id,
            "resolution attached_to_target_id",
        )
        _require_optional_trimmed(self.reason, "resolution reason")

        if self.disposition is ResolutionDisposition.ATTACHMENT:
            if (
                self.target_id is None
                or self.reference_kind is None
                or self.modeled_role is None
            ):
                raise ValueError(
                    "Attachment resolutions require target_id, reference_kind, "
                    "and modeled_role",
                )
            if (
                self.attached_to_equipment_index is not None
                or self.attached_to_target_id is not None
                or self.reason is not None
            ):
                raise ValueError(
                    "Attachment resolutions cannot carry store/non-runtime fields",
                )
            if self.category is EquipmentCategory.WEAPON:
                if (
                    self.source_system_count is None
                    or self.target_system_count is None
                    or self.runtime_system_multiplier is None
                ):
                    raise ValueError(
                        "Weapon attachment resolutions require complete system "
                        "count topology",
                    )
                expected_multiplier = _validate_system_counts(
                    equipment_name=self.source_equipment.name,
                    source_system_count=self.source_system_count,
                    target_system_count=self.target_system_count,
                )
                if self.runtime_system_multiplier != expected_multiplier:
                    raise ValueError(
                        "Resolution runtime_system_multiplier must equal "
                        "source_system_count // target_system_count",
                    )
            elif any(
                count is not None
                for count in (
                    self.source_system_count,
                    self.target_system_count,
                    self.runtime_system_multiplier,
                )
            ):
                raise ValueError(
                    "Sensor attachment resolutions cannot carry weapon system "
                    "count topology",
                )
        elif self.disposition is ResolutionDisposition.STORE:
            if (
                self.category is not EquipmentCategory.WEAPON
                or
                self.target_id is None
                or self.reference_kind is None
                or self.modeled_role is not None
                or self.attached_to_equipment_index is None
                or self.attached_to_target_id is None
                or self.reason is not None
            ):
                raise ValueError(
                    "Weapon store resolutions require a target and one "
                    "attachment link",
                )
            if any(
                count is not None
                for count in (
                    self.source_system_count,
                    self.target_system_count,
                    self.runtime_system_multiplier,
                )
            ):
                raise ValueError(
                    "Store resolutions cannot carry live system count topology",
                )
        elif self.disposition is ResolutionDisposition.NON_RUNTIME:
            if (
                self.reason is None
                or self.target_id is not None
                or self.reference_kind is not None
                or self.modeled_role is not None
                or self.attached_to_equipment_index is not None
                or self.attached_to_target_id is not None
            ):
                raise ValueError(
                    "Non-runtime resolutions require only an explicit reason",
                )
            if any(
                count is not None
                for count in (
                    self.source_system_count,
                    self.target_system_count,
                    self.runtime_system_multiplier,
                )
            ):
                raise ValueError(
                    "Non-runtime resolutions cannot carry live system count "
                    "topology",
                )
        else:
            raise ValueError(
                "Unsupported equipment raises before RuntimeLoadouts publication",
            )

    @property
    def equipment_id(self) -> str:
        return self.source_equipment.equipment_id

    @property
    def equipment_name(self) -> str:
        return self.source_equipment.name

    def topology(self) -> dict[str, Any]:
        return {
            "source_equipment_index": self.source_equipment_index,
            "equipment_id": self.source_equipment.equipment_id,
            "equipment_name": self.source_equipment.name,
            "category": self.category.name,
            "disposition": self.disposition.value,
            "modeled_role": (
                self.modeled_role.value
                if self.modeled_role is not None
                else None
            ),
            "reference_kind": (
                self.reference_kind.value
                if self.reference_kind is not None
                else None
            ),
            "target_id": self.target_id,
            "attached_to_equipment_index": self.attached_to_equipment_index,
            "attached_to_target_id": self.attached_to_target_id,
            "reason": self.reason,
            "source_system_count": self.source_system_count,
            "target_system_count": self.target_system_count,
            "runtime_system_multiplier": self.runtime_system_multiplier,
        }


@dataclass(frozen=True, slots=True)
class RuntimeLoadouts:
    """Immutable per-unit runtime attachments and equipment outcomes."""

    unit_weapons: Mapping[str, tuple[WeaponAttachment, ...]]
    unit_sensor_attachments: Mapping[str, tuple[SensorAttachment, ...]]
    equipment_resolutions: Mapping[str, tuple[EquipmentResolution, ...]]
    unit_sensors: Mapping[str, tuple[SensorInstance, ...]] = field(init=False)

    def __post_init__(self) -> None:
        weapon_keys = set(self.unit_weapons)
        sensor_keys = set(self.unit_sensor_attachments)
        resolution_keys = set(self.equipment_resolutions)
        if weapon_keys != sensor_keys or weapon_keys != resolution_keys:
            raise ValueError(
                "RuntimeLoadouts must contain weapons, sensor attachments, "
                "and resolutions for exactly the same unit IDs",
            )
        normalized_weapons = {
            unit_id: tuple(attachments)
            for unit_id, attachments in self.unit_weapons.items()
        }
        normalized_sensor_attachments = {
            unit_id: tuple(attachments)
            for unit_id, attachments in self.unit_sensor_attachments.items()
        }
        normalized_resolutions = {
            unit_id: tuple(resolutions)
            for unit_id, resolutions in self.equipment_resolutions.items()
        }
        normalized_sensors: dict[str, tuple[SensorInstance, ...]] = {}

        for unit_id in normalized_weapons:
            weapons = normalized_weapons[unit_id]
            sensor_attachments = normalized_sensor_attachments[unit_id]
            resolutions = normalized_resolutions[unit_id]

            weapon_by_source_index: dict[int, WeaponAttachment] = {}
            for attachment in weapons:
                if not isinstance(attachment, WeaponAttachment):
                    raise TypeError(
                        f"unit_weapons[{unit_id!r}] must contain only "
                        "WeaponAttachment values",
                    )
                if attachment.source_equipment_index in weapon_by_source_index:
                    raise ValueError(
                        f"unit {unit_id!r} has duplicate weapon source index "
                        f"{attachment.source_equipment_index}",
                    )
                weapon_by_source_index[
                    attachment.source_equipment_index
                ] = attachment
            weapon_order = tuple(
                (
                    -attachment.weapon.definition.max_range_m,
                    attachment.source_equipment_index,
                    attachment.weapon.weapon_id,
                )
                for attachment in weapons
            )
            if weapon_order != tuple(sorted(weapon_order)):
                raise ValueError(
                    f"unit {unit_id!r} weapon attachments must retain "
                    "canonical range/source/ID order",
                )

            sensor_indexes = tuple(
                attachment.source_equipment_index
                for attachment in sensor_attachments
            )
            if sensor_indexes != tuple(sorted(sensor_indexes)):
                raise ValueError(
                    f"unit {unit_id!r} sensor attachments must retain source "
                    "equipment order",
                )
            if len(sensor_indexes) != len(set(sensor_indexes)):
                raise ValueError(
                    f"unit {unit_id!r} has duplicate sensor source indexes",
                )
            sensor_by_source_index: dict[int, SensorAttachment] = {}
            for attachment in sensor_attachments:
                if not isinstance(attachment, SensorAttachment):
                    raise TypeError(
                        f"unit_sensor_attachments[{unit_id!r}] must contain "
                        "only SensorAttachment values",
                    )
                sensor_by_source_index[
                    attachment.source_equipment_index
                ] = attachment
                expected_indexes = tuple(sorted(
                    source_index
                    for source_index, weapon_attachment
                    in weapon_by_source_index.items()
                    if weapon_attachment.modeled_role
                    in attachment.compatible_weapon_roles
                ))
                if (
                    attachment.compatible_weapon_source_indexes
                    != expected_indexes
                ):
                    raise ValueError(
                        f"unit {unit_id!r} sensor source index "
                        f"{attachment.source_equipment_index} declares resolved "
                        "weapon indexes "
                        f"{attachment.compatible_weapon_source_indexes!r}, "
                        f"expected {expected_indexes!r}",
                    )

            resolution_by_key: dict[
                tuple[EquipmentCategory, int],
                EquipmentResolution,
            ] = {}
            resolution_indexes: list[int] = []
            for resolution in resolutions:
                if not isinstance(resolution, EquipmentResolution):
                    raise TypeError(
                        f"equipment_resolutions[{unit_id!r}] must contain "
                        "only EquipmentResolution values",
                    )
                if resolution.unit_id != unit_id:
                    raise ValueError(
                        f"RuntimeLoadouts key {unit_id!r} contains resolution "
                        f"for unit {resolution.unit_id!r}",
                    )
                key = (resolution.category, resolution.source_equipment_index)
                if key in resolution_by_key:
                    raise ValueError(
                        f"unit {unit_id!r} has duplicate resolution for "
                        f"{resolution.category.name} source index "
                        f"{resolution.source_equipment_index}",
                    )
                resolution_by_key[key] = resolution
                resolution_indexes.append(resolution.source_equipment_index)
            if resolution_indexes != sorted(resolution_indexes):
                raise ValueError(
                    f"unit {unit_id!r} equipment resolutions must retain "
                    "source equipment order",
                )
            if len(resolution_indexes) != len(set(resolution_indexes)):
                raise ValueError(
                    f"unit {unit_id!r} has duplicate equipment resolution "
                    "source indexes",
                )

            for attachment in weapons:
                resolution = resolution_by_key.get((
                    EquipmentCategory.WEAPON,
                    attachment.source_equipment_index,
                ))
                if (
                    resolution is None
                    or resolution.disposition
                    is not ResolutionDisposition.ATTACHMENT
                    or resolution.source_equipment
                    is not attachment.source_equipment
                    or resolution.target_id != attachment.weapon.weapon_id
                    or resolution.modeled_role is not attachment.modeled_role
                    or resolution.reference_kind
                    is not attachment.reference_kind
                ):
                    raise ValueError(
                        f"unit {unit_id!r} weapon source index "
                        f"{attachment.source_equipment_index} lacks an exact "
                        "attachment resolution",
                    )
            for attachment in sensor_attachments:
                resolution = resolution_by_key.get((
                    EquipmentCategory.SENSOR,
                    attachment.source_equipment_index,
                ))
                if (
                    resolution is None
                    or resolution.disposition
                    is not ResolutionDisposition.ATTACHMENT
                    or resolution.source_equipment
                    is not attachment.source_equipment
                    or resolution.target_id != attachment.sensor.sensor_id
                    or resolution.modeled_role is not attachment.modeled_role
                    or resolution.reference_kind
                    is not attachment.reference_kind
                ):
                    raise ValueError(
                        f"unit {unit_id!r} sensor source index "
                        f"{attachment.source_equipment_index} lacks an exact "
                        "attachment resolution",
                    )
            for resolution in resolutions:
                if resolution.disposition is not ResolutionDisposition.ATTACHMENT:
                    if resolution.disposition is ResolutionDisposition.STORE:
                        linked_weapon = weapon_by_source_index.get(
                            resolution.attached_to_equipment_index,
                        )
                        if (
                            linked_weapon is None
                            or linked_weapon.weapon.weapon_id
                            != resolution.attached_to_target_id
                            or resolution.target_id
                            not in {
                                ammunition.ammo_id
                                for ammunition in linked_weapon.ammunition
                            }
                        ):
                            raise ValueError(
                                f"unit {unit_id!r} store resolution at source "
                                f"index {resolution.source_equipment_index} "
                                "does not match an exact weapon/ammunition "
                                "attachment",
                            )
                    continue
                attachment = (
                    weapon_by_source_index.get(
                        resolution.source_equipment_index,
                    )
                    if resolution.category is EquipmentCategory.WEAPON
                    else sensor_by_source_index.get(
                        resolution.source_equipment_index,
                    )
                )
                if attachment is None:
                    raise ValueError(
                        f"unit {unit_id!r} {resolution.category.name.lower()} "
                        f"resolution at source index "
                        f"{resolution.source_equipment_index} has no exact "
                        "live attachment",
                    )

            normalized_sensors[unit_id] = tuple(
                attachment.sensor
                for attachment in sensor_attachments
            )

        object.__setattr__(
            self,
            "unit_weapons",
            MappingProxyType(normalized_weapons),
        )
        object.__setattr__(
            self,
            "unit_sensor_attachments",
            MappingProxyType(normalized_sensor_attachments),
        )
        object.__setattr__(
            self,
            "equipment_resolutions",
            MappingProxyType(normalized_resolutions),
        )
        object.__setattr__(
            self,
            "unit_sensors",
            MappingProxyType(normalized_sensors),
        )

    @property
    def weapons(self) -> Mapping[str, tuple[WeaponAttachment, ...]]:
        return self.unit_weapons

    @property
    def sensors(self) -> Mapping[str, tuple[SensorInstance, ...]]:
        return self.unit_sensors

    @property
    def sensor_attachments(self) -> Mapping[str, tuple[SensorAttachment, ...]]:
        return self.unit_sensor_attachments

    @property
    def resolutions(self) -> Mapping[str, tuple[EquipmentResolution, ...]]:
        return self.equipment_resolutions

    def topology(self) -> dict[str, list[dict[str, Any]]]:
        """Return transparent, canonicalizable ordered attachment decisions."""
        return {
            unit_id: [
                resolution.topology()
                for resolution in self.equipment_resolutions[unit_id]
            ]
            for unit_id in sorted(self.equipment_resolutions)
        }

    def topology_fingerprint(self) -> str:
        """Return SHA-256 of the current ordered resolution topology."""
        return _sha256_payload(self.topology())
