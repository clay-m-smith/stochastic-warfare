"""Ordered, immutable loadout mapping registry."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from stochastic_warfare.detection.sensor_roles import SensorModeledRole
from stochastic_warfare.entities.equipment import EquipmentCategory
from stochastic_warfare.simulation.loadout_contracts import (
    DuplicateEquipmentMappingError,
    EquipmentMappingError,
    EquipmentMappingRecord,
    ReferenceKind,
    SensorAttachmentMapping,
    WeaponAttachmentMapping,
    WeaponModeledRole,
    _MAPPING_RECORD_TYPES,
)


@dataclass(frozen=True, slots=True, init=False)
class EquipmentMappingRegistry:
    """Ordered, immutable mapping declarations with a uniqueness-checked index."""

    _records: tuple[EquipmentMappingRecord, ...]
    _index: Mapping[
        tuple[EquipmentCategory, str],
        EquipmentMappingRecord,
    ]

    def __init__(self, records: Sequence[EquipmentMappingRecord]) -> None:
        if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
            raise TypeError("Equipment mappings must be an ordered sequence")
        frozen_records = tuple(records)

        # Validate every key and reject duplicates before constructing an index.
        seen: dict[tuple[EquipmentCategory, str], int] = {}
        exact_target_roles: dict[
            tuple[EquipmentCategory, str],
            tuple[
                WeaponModeledRole | SensorModeledRole,
                int,
            ],
        ] = {}
        for index, record in enumerate(frozen_records):
            if not isinstance(record, _MAPPING_RECORD_TYPES):
                raise TypeError(
                    "Equipment mapping declarations must use the typed "
                    f"record union, got {type(record).__name__} at index {index}",
                )
            key = (record.category, record.equipment_name)
            if key in seen:
                first_index = seen[key]
                raise DuplicateEquipmentMappingError(
                    "Duplicate equipment mapping for "
                    f"({record.category.name}, {record.equipment_name!r}) "
                    f"at declaration indexes {first_index} and {index}",
                )
            seen[key] = index
            if isinstance(
                record,
                (WeaponAttachmentMapping, SensorAttachmentMapping),
            ) and record.reference_kind is ReferenceKind.EXACT:
                target_key = (record.category, record.target_id)
                previous = exact_target_roles.get(target_key)
                if (
                    previous is not None
                    and previous[0] is not record.modeled_role
                ):
                    raise EquipmentMappingError(
                        f"Target {record.target_id!r} is declared with "
                        f"conflicting modeled roles "
                        f"{previous[0].value!r} (index {previous[1]}) and "
                        f"{record.modeled_role.value!r} (index {index})",
                    )
                if previous is None:
                    exact_target_roles[target_key] = (
                        record.modeled_role,
                        index,
                    )

        object.__setattr__(self, "_records", frozen_records)
        object.__setattr__(
            self,
            "_index",
            MappingProxyType({
                (record.category, record.equipment_name): record
                for record in frozen_records
            }),
        )

    @property
    def records(self) -> tuple[EquipmentMappingRecord, ...]:
        return self._records

    def get(
        self,
        category: EquipmentCategory,
        equipment_name: str,
    ) -> EquipmentMappingRecord | None:
        return self._index.get((category, equipment_name))

    def require(
        self,
        category: EquipmentCategory,
        equipment_name: str,
    ) -> EquipmentMappingRecord:
        try:
            return self._index[(category, equipment_name)]
        except KeyError as exc:
            raise EquipmentMappingError(
                "No equipment mapping for "
                f"({category.name}, {equipment_name!r})",
            ) from exc
