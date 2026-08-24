"""Strict deterministic construction of production runtime loadouts."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from stochastic_warfare.combat.ammunition import (
    AmmoDefinition,
    AmmoLoader,
    AmmoState,
    AmmoType,
    GuidanceType,
    WeaponDefinition,
    WeaponInstance,
    WeaponLoader,
)
from stochastic_warfare.core.era import EraConfig
from stochastic_warfare.core.types import Domain
from stochastic_warfare.detection.sensors import (
    SensorDefinition,
    SensorInstance,
    SensorLoader,
    SensorType,
    signature_domain_for_sensor_type,
)
from stochastic_warfare.detection.signatures import SignatureDomain
from stochastic_warfare.entities.base import Unit
from stochastic_warfare.entities.equipment import EquipmentCategory, EquipmentItem
from stochastic_warfare.entities.loader import (
    SensorPolicy,
    UnitDefinition,
    runtime_domain_for_definition,
)
from stochastic_warfare.simulation.loadout_contracts import (
    EquipmentMappingError,
    EquipmentMappingRecord,
    ResolutionDisposition,
    SensorAttachmentMapping,
    SensorNonRuntimeMapping,
    SensorUnsupportedMapping,
    UnsupportedEquipmentError,
    WeaponAttachmentMapping,
    WeaponNonRuntimeMapping,
    WeaponStoreMapping,
    WeaponUnsupportedMapping,
    _require_string_tuple,
    _require_trimmed,
    _sha256_payload,
    allowed_shooter_domains_for_sensor_role,
)
from stochastic_warfare.simulation.loadout_registry import EquipmentMappingRegistry
from stochastic_warfare.simulation.runtime_attachments import (
    EquipmentResolution,
    RuntimeLoadouts,
    SensorAttachment,
    WeaponAssignment,
    WeaponAttachment,
)


@dataclass(frozen=True, slots=True)
class _EquipmentPlan:
    source_equipment_index: int
    record: EquipmentMappingRecord
    target_id: str | None = None
    ammo_ids: tuple[str, ...] = ()
    attached_to_equipment_index: int | None = None
    attached_to_target_id: str | None = None


def _coerce_assignments(
    assignments: Mapping[str, str] | Sequence[WeaponAssignment],
) -> tuple[
    tuple[WeaponAssignment, ...],
    Mapping[str, WeaponAssignment],
]:
    if isinstance(assignments, Mapping):
        frozen = tuple(
            WeaponAssignment(equipment_name=name, weapon_id=weapon_id)
            for name, weapon_id in sorted(assignments.items())
        )
    elif isinstance(assignments, Sequence) and not isinstance(
        assignments,
        (str, bytes),
    ):
        frozen = tuple(assignments)
    else:
        raise TypeError(
            "assignment_overrides must be a mapping or ordered sequence "
            "of WeaponAssignment records",
        )

    seen: dict[str, int] = {}
    for index, assignment in enumerate(frozen):
        if not isinstance(assignment, WeaponAssignment):
            raise TypeError(
                "Typed assignment sequence contains "
                f"{type(assignment).__name__} at index {index}",
            )
        if assignment.equipment_name in seen:
            raise EquipmentMappingError(
                "Duplicate weapon assignment for "
                f"{assignment.equipment_name!r} at indexes "
                f"{seen[assignment.equipment_name]} and {index}",
            )
        seen[assignment.equipment_name] = index
    return frozen, MappingProxyType({
        assignment.equipment_name: assignment
        for assignment in frozen
    })


def _definition_context(
    unit_type: str,
    source_index: int,
    category: EquipmentCategory,
    equipment_name: str,
) -> str:
    return (
        f"unit_type {unit_type!r} equipment[{source_index}] "
        f"{equipment_name!r} ({category.name})"
    )


def _runtime_context(
    unit: Unit,
    source_index: int,
    equipment: EquipmentItem,
) -> str:
    return (
        f"unit {unit.entity_id!r} ({unit.unit_type!r}) equipment[{source_index}] "
        f"{equipment.name!r} ({equipment.category.name})"
    )


@dataclass(frozen=True, slots=True, init=False)
class RuntimeLoadoutBuilder:
    """Preflight and build all reachable loadouts through one strict boundary."""

    _weapon_definitions: Mapping[str, WeaponDefinition]
    _ammo_definitions: Mapping[str, AmmoDefinition]
    _sensor_definitions: Mapping[str, SensorDefinition]
    _unit_definitions: Mapping[str, UnitDefinition]
    _era_config: EraConfig
    _registry: EquipmentMappingRegistry
    _assignments: tuple[WeaponAssignment, ...]
    _assignment_index: Mapping[str, WeaponAssignment]
    _reachable_unit_types: tuple[str, ...]
    _plans: Mapping[str, tuple[_EquipmentPlan, ...]]
    _fingerprint: str

    def __init__(
        self,
        *,
        weapon_loader: WeaponLoader,
        ammo_loader: AmmoLoader,
        sensor_loader: SensorLoader,
        unit_definitions: Mapping[str, UnitDefinition],
        era_config: EraConfig,
        assignment_overrides: (
            Mapping[str, str] | Sequence[WeaponAssignment]
        ),
        reachable_unit_types: Sequence[str],
        registry: EquipmentMappingRegistry,
    ) -> None:
        if not isinstance(weapon_loader, WeaponLoader):
            raise TypeError("weapon_loader must be a concrete WeaponLoader")
        if not isinstance(ammo_loader, AmmoLoader):
            raise TypeError("ammo_loader must be a concrete AmmoLoader")
        if not isinstance(sensor_loader, SensorLoader):
            raise TypeError("sensor_loader must be a concrete SensorLoader")
        if not isinstance(era_config, EraConfig):
            raise TypeError("era_config must be an effective EraConfig")
        if not isinstance(registry, EquipmentMappingRegistry):
            raise TypeError("registry must be an EquipmentMappingRegistry")
        if not isinstance(unit_definitions, Mapping):
            raise TypeError("unit_definitions must be a mapping")
        if not isinstance(reachable_unit_types, Sequence) or isinstance(
            reachable_unit_types,
            (str, bytes),
        ):
            raise TypeError("reachable_unit_types must be an ordered sequence")

        frozen_units: dict[str, UnitDefinition] = {}
        for key, definition in unit_definitions.items():
            _require_trimmed(key, "unit_definitions key")
            if not isinstance(definition, UnitDefinition):
                raise TypeError(
                    f"unit_definitions[{key!r}] must be a UnitDefinition",
                )
            if definition.unit_type != key:
                raise EquipmentMappingError(
                    f"Unit definition key {key!r} does not match "
                    f"definition.unit_type {definition.unit_type!r}",
                )
            frozen_units[key] = definition.model_copy(deep=True)

        reachable: set[str] = set()
        for unit_type in reachable_unit_types:
            _require_trimmed(unit_type, "reachable unit_type")
            reachable.add(unit_type)

        assignments, assignment_index = _coerce_assignments(
            assignment_overrides,
        )
        object.__setattr__(
            self,
            "_weapon_definitions",
            MappingProxyType({
                weapon_id: WeaponDefinition.model_validate(
                    definition.model_dump(mode="python"),
                )
                for weapon_id, definition in weapon_loader.definitions().items()
            }),
        )
        object.__setattr__(
            self,
            "_ammo_definitions",
            MappingProxyType({
                ammo_id: AmmoDefinition.model_validate(
                    definition.model_dump(mode="python"),
                )
                for ammo_id, definition in ammo_loader.definitions().items()
            }),
        )
        object.__setattr__(
            self,
            "_sensor_definitions",
            MappingProxyType({
                sensor_id: SensorDefinition.model_validate(
                    definition.model_dump(mode="python"),
                )
                for sensor_id, definition in sensor_loader.definitions().items()
            }),
        )
        object.__setattr__(
            self,
            "_unit_definitions",
            MappingProxyType(frozen_units),
        )
        object.__setattr__(
            self,
            "_era_config",
            EraConfig.model_validate(era_config.model_dump(mode="python")),
        )
        object.__setattr__(self, "_registry", registry)
        object.__setattr__(self, "_assignments", assignments)
        object.__setattr__(self, "_assignment_index", assignment_index)
        object.__setattr__(
            self,
            "_reachable_unit_types",
            tuple(sorted(reachable)),
        )

        plans = self._preflight_plans()
        object.__setattr__(self, "_plans", MappingProxyType(plans))
        object.__setattr__(self, "_fingerprint", self._compute_fingerprint())

    @property
    def reachable_unit_types(self) -> tuple[str, ...]:
        return self._reachable_unit_types

    @property
    def era_config(self) -> EraConfig:
        """Return an isolated copy of the era gates frozen at preflight."""
        return EraConfig.model_validate(
            self._era_config.model_dump(mode="python"),
        )

    @property
    def registry(self) -> EquipmentMappingRegistry:
        return self._registry

    @property
    def assignments(self) -> tuple[WeaponAssignment, ...]:
        return self._assignments

    def preflight(self) -> None:
        """Repeat reachable validation against the builder's frozen envelope."""
        self._preflight_plans()

    def fingerprint(self) -> str:
        """Return active SHA-256 over the frozen reachable build envelope."""
        return self._fingerprint

    def topology(
        self,
        loadouts: RuntimeLoadouts,
    ) -> dict[str, list[dict[str, Any]]]:
        """Expose the transparent ordered topology produced by this boundary."""
        if not isinstance(loadouts, RuntimeLoadouts):
            raise TypeError("loadouts must be RuntimeLoadouts")
        return loadouts.topology()

    def _preflight_plans(self) -> dict[str, tuple[_EquipmentPlan, ...]]:
        plans: dict[str, tuple[_EquipmentPlan, ...]] = {}
        used_assignments: set[str] = set()
        for unit_type in self._reachable_unit_types:
            try:
                definition = self._unit_definitions[unit_type]
            except KeyError as exc:
                raise EquipmentMappingError(
                    f"Reachable unit_type {unit_type!r} has no effective "
                    "UnitDefinition",
                ) from exc
            plans[unit_type] = self._preflight_unit(
                definition,
                used_assignments,
            )

        stale_assignments = sorted(
            set(self._assignment_index) - used_assignments,
        )
        if stale_assignments:
            raise EquipmentMappingError(
                "Weapon assignments do not name reachable declared weapon "
                f"equipment: {stale_assignments}",
            )
        return plans

    def _preflight_unit(
        self,
        definition: UnitDefinition,
        used_assignments: set[str],
    ) -> tuple[_EquipmentPlan, ...]:
        plans: list[_EquipmentPlan] = []
        attachment_plans: list[_EquipmentPlan] = []
        sensor_attachments = 0

        if (
            not self._era_config.feature_enabled("data_links")
            and definition.data_link_range is not None
            and definition.data_link_range > 0
        ):
            raise EquipmentMappingError(
                f"unit_type {definition.unit_type!r}: era feature "
                f"'data_links' is disabled but data_link_range="
                f"{definition.data_link_range}",
            )

        for source_index, equipment in enumerate(definition.equipment):
            try:
                category = EquipmentCategory[equipment.category.upper()]
            except KeyError as exc:
                raise EquipmentMappingError(
                    f"unit_type {definition.unit_type!r} equipment[{source_index}] "
                    f"{equipment.name!r}: unknown category {equipment.category!r}",
                ) from exc
            if category not in (
                EquipmentCategory.WEAPON,
                EquipmentCategory.SENSOR,
            ):
                continue

            context = _definition_context(
                definition.unit_type,
                source_index,
                category,
                equipment.name,
            )
            record = self._registry.get(category, equipment.name)
            if record is None:
                raise EquipmentMappingError(f"{context}: no mapping declaration")
            if isinstance(
                record,
                (WeaponUnsupportedMapping, SensorUnsupportedMapping),
            ):
                raise UnsupportedEquipmentError(
                    f"{context}: explicitly unsupported: {record.reason}",
                )

            if isinstance(record, WeaponAttachmentMapping):
                assignment = self._assignment_index.get(equipment.name)
                target_id = record.weapon_id
                if assignment is not None:
                    used_assignments.add(equipment.name)
                    target_id = assignment.weapon_id
                    if not record.permits_target(target_id):
                        raise EquipmentMappingError(
                            f"{context}: assignment target {target_id!r} "
                            "contradicts the registry identity/role contract "
                            f"for {record.weapon_id!r}",
                        )
                ammo_definitions = self._validate_weapon_target(
                    context,
                    target_id,
                    record,
                )
                plan = _EquipmentPlan(
                    source_equipment_index=source_index,
                    record=record,
                    target_id=target_id,
                    ammo_ids=tuple(
                        ammo.ammo_id for ammo in ammo_definitions
                    ),
                )
                plans.append(plan)
                attachment_plans.append(plan)
            elif isinstance(record, WeaponStoreMapping):
                self._validate_store_target(context, record)
                plans.append(_EquipmentPlan(
                    source_equipment_index=source_index,
                    record=record,
                    target_id=record.ammo_id,
                ))
            elif isinstance(record, WeaponNonRuntimeMapping):
                if equipment.name in self._assignment_index:
                    used_assignments.add(equipment.name)
                    raise EquipmentMappingError(
                        f"{context}: weapon assignment cannot convert explicit "
                        "non-runtime equipment into a live attachment",
                    )
                plans.append(_EquipmentPlan(
                    source_equipment_index=source_index,
                    record=record,
                ))
            elif isinstance(record, SensorAttachmentMapping):
                shooter_domain = runtime_domain_for_definition(definition)
                allowed_shooter_domains = (
                    allowed_shooter_domains_for_sensor_role(
                        record.modeled_role,
                    )
                )
                if shooter_domain not in allowed_shooter_domains:
                    raise EquipmentMappingError(
                        f"{context}: sensor role {record.modeled_role.value!r} "
                        f"cannot be mounted on shooter domain "
                        f"{shooter_domain.name}; allowed domains are "
                        f"{[domain.name for domain in allowed_shooter_domains]}",
                    )
                self._validate_sensor_target(context, record)
                plans.append(_EquipmentPlan(
                    source_equipment_index=source_index,
                    record=record,
                    target_id=record.sensor_id,
                ))
                sensor_attachments += 1
            elif isinstance(record, SensorNonRuntimeMapping):
                plans.append(_EquipmentPlan(
                    source_equipment_index=source_index,
                    record=record,
                ))
            else:  # pragma: no cover - the typed registry makes this impossible
                raise AssertionError(f"Unhandled mapping record {record!r}")

        plans = self._link_stores(
            definition.unit_type,
            plans,
            attachment_plans,
        )
        if definition.sensor_policy is SensorPolicy.REQUIRED:
            if sensor_attachments == 0:
                raise EquipmentMappingError(
                    f"unit_type {definition.unit_type!r}: "
                    "sensor_policy='required' produced no live sensor attachment",
                )
        elif definition.sensor_policy is SensorPolicy.INTENTIONALLY_NONE:
            if sensor_attachments:
                raise EquipmentMappingError(
                    f"unit_type {definition.unit_type!r}: "
                    "sensor_policy='intentionally_none' produced a sensor",
                )
            _require_trimmed(
                definition.sensor_policy_reason,
                f"unit_type {definition.unit_type!r} sensor_policy_reason",
            )
        else:  # pragma: no cover - Pydantic validates this enum
            raise EquipmentMappingError(
                f"unit_type {definition.unit_type!r}: unhandled sensor policy "
                f"{definition.sensor_policy!r}",
            )
        return tuple(plans)

    def _validate_weapon_target(
        self,
        context: str,
        target_id: str,
        record: WeaponAttachmentMapping,
    ) -> tuple[AmmoDefinition, ...]:
        try:
            definition = self._weapon_definitions[target_id]
        except KeyError as exc:
            raise EquipmentMappingError(
                f"{context}: weapon target {target_id!r} is absent from the "
                "effective catalog",
            ) from exc
        try:
            category = definition.parsed_category()
        except (KeyError, ValueError) as exc:
            raise EquipmentMappingError(
                f"{context}: weapon target {target_id!r} has invalid category "
                f"{definition.category!r}",
            ) from exc
        if category is not record.expected_weapon_category:
            raise EquipmentMappingError(
                f"{context}: weapon target {target_id!r} category "
                f"{category.name} does not match required "
                f"{record.expected_weapon_category.name}",
            )
        try:
            guidance = definition.parsed_guidance()
        except (KeyError, ValueError) as exc:
            raise EquipmentMappingError(
                f"{context}: weapon target {target_id!r} has invalid guidance "
                f"{definition.guidance!r}",
            ) from exc
        if (
            record.expected_guidance is not None
            and guidance is not record.expected_guidance
        ):
            raise EquipmentMappingError(
                f"{context}: weapon target {target_id!r} guidance "
                f"{guidance.name} does not match required "
                f"{record.expected_guidance.name}",
            )
        if (
            record.expected_caliber_mm is not None
            and not math.isclose(
                definition.caliber_mm,
                float(record.expected_caliber_mm),
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        ):
            raise EquipmentMappingError(
                f"{context}: weapon target {target_id!r} caliber "
                f"{definition.caliber_mm} mm does not match required "
                f"{record.expected_caliber_mm} mm",
            )
        if definition.magazine_capacity <= 0:
            raise EquipmentMappingError(
                f"{context}: weapon target {target_id!r} has no usable "
                f"magazine capacity ({definition.magazine_capacity})",
            )
        compatible_ids = tuple(definition.compatible_ammo)
        _require_string_tuple(
            compatible_ids,
            f"{context} weapon target {target_id!r} compatible_ammo",
            non_empty=True,
        )
        ammunition_by_id: dict[str, AmmoDefinition] = {}
        ammo_type_by_id: dict[str, AmmoType] = {}
        ammo_guidance_by_id: dict[str, GuidanceType] = {}
        for ammo_id in compatible_ids:
            try:
                ammo = self._ammo_definitions[ammo_id]
            except KeyError as exc:
                raise EquipmentMappingError(
                    f"{context}: weapon target {target_id!r} references missing "
                    f"ammunition {ammo_id!r}",
                ) from exc
            try:
                ammo_type = ammo.parsed_ammo_type()
                ammo_guidance = ammo.parsed_guidance()
            except (KeyError, ValueError) as exc:
                raise EquipmentMappingError(
                    f"{context}: ammunition {ammo_id!r} has an invalid typed "
                    "ammo_type or guidance",
                ) from exc
            ammunition_by_id[ammo_id] = ammo
            ammo_type_by_id[ammo_id] = ammo_type
            ammo_guidance_by_id[ammo_id] = ammo_guidance

        selected_ids = (
            record.allowed_ammo_ids
            if record.allowed_ammo_ids
            else compatible_ids
        )
        disallowed_ids = [
            ammo_id
            for ammo_id in selected_ids
            if ammo_id not in ammunition_by_id
        ]
        if disallowed_ids:
            raise EquipmentMappingError(
                f"{context}: weapon target {target_id!r} does not declare "
                f"mapping-allowed ammunition {disallowed_ids}",
            )
        ammunition = [
            ammunition_by_id[ammo_id]
            for ammo_id in selected_ids
        ]
        ammo_types = {
            ammo_type_by_id[ammo_id]
            for ammo_id in selected_ids
        }
        for ammo in ammunition:
            self._validate_era_guidance(
                context,
                target_id,
                ammo.ammo_id,
                ammo_guidance_by_id[ammo.ammo_id],
            )

        missing_ammo_types = [
            ammo_type.name
            for ammo_type in record.required_ammo_types
            if ammo_type not in ammo_types
        ]
        if missing_ammo_types:
            raise EquipmentMappingError(
                f"{context}: weapon target {target_id!r} lacks required "
                f"ammunition roles {missing_ammo_types}",
            )

        actual_domains: set[Domain] = set()
        for domain_name in definition.effective_target_domains():
            try:
                actual_domains.add(Domain[domain_name.upper()])
            except KeyError as exc:
                raise EquipmentMappingError(
                    f"{context}: weapon target {target_id!r} has invalid target "
                    f"domain {domain_name!r}",
                ) from exc
        missing_domains = [
            domain.name
            for domain in record.required_target_domains
            if domain not in actual_domains
        ]
        if missing_domains:
            raise EquipmentMappingError(
                f"{context}: weapon target {target_id!r} lacks required target "
                f"domains {missing_domains}",
            )
        self._validate_era_guidance(
            context,
            target_id,
            None,
            guidance,
        )
        return tuple(ammunition)

    def _validate_era_guidance(
        self,
        context: str,
        weapon_id: str,
        ammo_id: str | None,
        guidance: GuidanceType,
    ) -> None:
        reference = (
            f"ammunition {ammo_id!r} for weapon {weapon_id!r}"
            if ammo_id is not None
            else f"weapon {weapon_id!r}"
        )
        if (
            not self._era_config.feature_enabled("gps")
            and guidance is GuidanceType.GPS
        ):
            raise EquipmentMappingError(
                f"{context}: era feature 'gps' is disabled but {reference} "
                "uses GPS guidance",
            )
        if (
            not self._era_config.feature_enabled("pgm")
            and guidance is not GuidanceType.NONE
        ):
            raise EquipmentMappingError(
                f"{context}: era feature 'pgm' is disabled but {reference} "
                f"uses {guidance.name} guidance",
            )

    def _validate_store_target(
        self,
        context: str,
        record: WeaponStoreMapping,
    ) -> None:
        try:
            ammo = self._ammo_definitions[record.ammo_id]
        except KeyError as exc:
            raise EquipmentMappingError(
                f"{context}: store ammunition {record.ammo_id!r} is absent "
                "from the effective catalog",
            ) from exc
        try:
            ammo_type = ammo.parsed_ammo_type()
            ammo_guidance = ammo.parsed_guidance()
        except (KeyError, ValueError) as exc:
            raise EquipmentMappingError(
                f"{context}: store ammunition {record.ammo_id!r} has an "
                "invalid typed ammo_type or guidance",
            ) from exc
        if (
            record.expected_ammo_type is not None
            and ammo_type is not record.expected_ammo_type
        ):
            raise EquipmentMappingError(
                f"{context}: store ammunition {record.ammo_id!r} type "
                f"{ammo_type.name} does not match required "
                f"{record.expected_ammo_type.name}",
            )
        self._validate_era_guidance(
            context,
            "<store attachment pending>",
            record.ammo_id,
            ammo_guidance,
        )

    def _validate_sensor_target(
        self,
        context: str,
        record: SensorAttachmentMapping,
    ) -> None:
        try:
            definition = self._sensor_definitions[record.sensor_id]
        except KeyError as exc:
            raise EquipmentMappingError(
                f"{context}: sensor target {record.sensor_id!r} is absent from "
                "the effective catalog",
            ) from exc
        try:
            sensor_type = definition.parsed_sensor_type()
        except (KeyError, ValueError) as exc:
            raise EquipmentMappingError(
                f"{context}: sensor target {record.sensor_id!r} has invalid "
                f"sensor_type {definition.sensor_type!r}",
            ) from exc
        if sensor_type is not record.expected_sensor_type:
            raise EquipmentMappingError(
                f"{context}: sensor target {record.sensor_id!r} type "
                f"{sensor_type.name} does not match required "
                f"{record.expected_sensor_type.name}",
            )
        try:
            signature_domain = signature_domain_for_sensor_type(sensor_type)
        except ValueError as exc:
            raise EquipmentMappingError(
                f"{context}: sensor target {record.sensor_id!r} is not handled "
                "by the production detection path",
            ) from exc
        if signature_domain is not record.expected_signature_domain:
            raise EquipmentMappingError(
                f"{context}: sensor target {record.sensor_id!r} production "
                f"domain {signature_domain.name} does not match required "
                f"{record.expected_signature_domain.name}",
            )

        authored_domains: list[SignatureDomain] = []
        for domain_name in definition.detects_domain:
            try:
                authored_domains.append(
                    SignatureDomain[domain_name.upper()],
                )
            except KeyError as exc:
                raise EquipmentMappingError(
                    f"{context}: sensor target {record.sensor_id!r} has invalid "
                    f"detects_domain value {domain_name!r}",
                ) from exc
        if authored_domains != [signature_domain]:
            raise EquipmentMappingError(
                f"{context}: sensor target {record.sensor_id!r} authored "
                f"detects_domain {[domain.name for domain in authored_domains]} "
                "disagrees with production dispatch "
                f"{signature_domain.name}",
            )

        actual_target_domains: set[Domain] = set()
        for domain_name in definition.effective_target_domains():
            try:
                actual_target_domains.add(Domain[domain_name.upper()])
            except KeyError as exc:
                raise EquipmentMappingError(
                    f"{context}: sensor target {record.sensor_id!r} has invalid "
                    f"target domain {domain_name!r}",
                ) from exc
        missing_target_domains = [
            domain.name
            for domain in record.required_target_domains
            if domain not in actual_target_domains
        ]
        if missing_target_domains:
            raise EquipmentMappingError(
                f"{context}: sensor target {record.sensor_id!r} lacks required "
                f"target domains {missing_target_domains}",
            )

        allowed_sensor_types = {
            sensor_name.upper()
            for sensor_name in self._era_config.available_sensor_types
        }
        if (
            allowed_sensor_types
            and sensor_type.name not in allowed_sensor_types
        ):
            raise EquipmentMappingError(
                f"{context}: era available_sensor_types forbids "
                f"{sensor_type.name} sensor {record.sensor_id!r}",
            )
        if (
            sensor_type is SensorType.THERMAL
            and not self._era_config.feature_enabled("thermal_sights")
        ):
            raise EquipmentMappingError(
                f"{context}: era feature 'thermal_sights' is disabled but "
                f"sensor {record.sensor_id!r} is THERMAL",
            )
        if (
            record.modeled_max_range_m is not None
            and record.modeled_max_range_m > definition.max_range_m
        ):
            raise EquipmentMappingError(
                f"{context}: sensor target {record.sensor_id!r} catalog range "
                f"{definition.max_range_m} m is below mapping-owned envelope "
                f"{record.modeled_max_range_m} m",
            )
        if (
            record.modeled_fov_deg is not None
            and record.modeled_fov_deg > definition.fov_deg
        ):
            raise EquipmentMappingError(
                f"{context}: sensor target {record.sensor_id!r} catalog FOV "
                f"{definition.fov_deg} degrees is below mapping-owned envelope "
                f"{record.modeled_fov_deg} degrees",
            )

    def _link_stores(
        self,
        unit_type: str,
        plans: list[_EquipmentPlan],
        attachment_plans: list[_EquipmentPlan],
    ) -> list[_EquipmentPlan]:
        linked: list[_EquipmentPlan] = []
        for plan in plans:
            if not isinstance(plan.record, WeaponStoreMapping):
                linked.append(plan)
                continue
            candidates = [
                attachment
                for attachment in attachment_plans
                if (
                    attachment.target_id
                    in plan.record.compatible_weapon_ids
                    and plan.record.ammo_id in attachment.ammo_ids
                )
            ]
            context = _definition_context(
                unit_type,
                plan.source_equipment_index,
                EquipmentCategory.WEAPON,
                plan.record.equipment_name,
            )
            if not candidates:
                raise EquipmentMappingError(
                    f"{context}: store {plan.record.ammo_id!r} has no "
                    "compatible same-unit live attachment",
                )
            if len(candidates) != 1:
                indexes = [
                    candidate.source_equipment_index
                    for candidate in candidates
                ]
                raise EquipmentMappingError(
                    f"{context}: store {plan.record.ammo_id!r} ambiguously "
                    f"matches attachment equipment indexes {indexes}",
                )
            attachment = candidates[0]
            linked.append(_EquipmentPlan(
                source_equipment_index=plan.source_equipment_index,
                record=plan.record,
                target_id=plan.target_id,
                attached_to_equipment_index=(
                    attachment.source_equipment_index
                ),
                attached_to_target_id=attachment.target_id,
            ))
        return linked

    def _compute_fingerprint(self) -> str:
        reachable_record_keys = {
            (plan.record.category, plan.record.equipment_name)
            for plans in self._plans.values()
            for plan in plans
        }
        reachable_records = [
            record
            for record in self._registry.records
            if (record.category, record.equipment_name)
            in reachable_record_keys
        ]

        referenced_weapon_ids = sorted({
            plan.target_id
            for plans in self._plans.values()
            for plan in plans
            if isinstance(plan.record, WeaponAttachmentMapping)
            and plan.target_id is not None
        })
        referenced_ammo_ids = sorted({
            ammo_id
            for plans in self._plans.values()
            for plan in plans
            for ammo_id in (
                plan.ammo_ids
                if isinstance(plan.record, WeaponAttachmentMapping)
                else (
                    (plan.target_id,)
                    if isinstance(plan.record, WeaponStoreMapping)
                    and plan.target_id is not None
                    else ()
                )
            )
        })
        referenced_sensor_ids = sorted({
            plan.target_id
            for plans in self._plans.values()
            for plan in plans
            if isinstance(plan.record, SensorAttachmentMapping)
            and plan.target_id is not None
        })
        payload = {
            "registry_records": reachable_records,
            "units": {
                unit_type: definition.model_dump(mode="python")
                for unit_type, definition in sorted(
                    (
                        (unit_type, self._unit_definitions[unit_type])
                        for unit_type in self._reachable_unit_types
                    ),
                )
            },
            "weapons": {
                weapon_id: self._weapon_definitions[weapon_id]
                for weapon_id in referenced_weapon_ids
            },
            "ammunition": {
                ammo_id: self._ammo_definitions[ammo_id]
                for ammo_id in referenced_ammo_ids
            },
            "sensors": {
                sensor_id: self._sensor_definitions[sensor_id]
                for sensor_id in referenced_sensor_ids
            },
            "era": self._era_config,
            "assignments": sorted(
                self._assignments,
                key=lambda assignment: assignment.equipment_name,
            ),
            "plans": self._plans,
        }
        return _sha256_payload(payload)

    def build(self, units: Sequence[Unit]) -> RuntimeLoadouts:
        """Atomically construct deterministic live attachments for *units*."""
        if not isinstance(units, Sequence) or isinstance(units, (str, bytes)):
            raise TypeError("units must be an ordered sequence")
        seen_ids: dict[str, int] = {}
        for index, unit in enumerate(units):
            if not isinstance(unit, Unit):
                raise TypeError(
                    f"units[{index}] must be a Unit, got {type(unit).__name__}",
                )
            if not unit.entity_id or not unit.entity_id.strip():
                raise EquipmentMappingError(
                    f"units[{index}] has an empty unit ID",
                )
            if unit.entity_id in seen_ids:
                raise EquipmentMappingError(
                    f"Duplicate unit ID {unit.entity_id!r} at indexes "
                    f"{seen_ids[unit.entity_id]} and {index}",
                )
            seen_ids[unit.entity_id] = index
            self._validate_runtime_topology(unit)

        unit_weapons: dict[str, tuple[WeaponAttachment, ...]] = {}
        unit_sensor_attachments: dict[
            str,
            tuple[SensorAttachment, ...],
        ] = {}
        unit_resolutions: dict[str, tuple[EquipmentResolution, ...]] = {}
        for unit in units:
            weapons: list[WeaponAttachment] = []
            for plan in self._plans[unit.unit_type]:
                record = plan.record
                if not isinstance(record, WeaponAttachmentMapping):
                    continue
                if plan.target_id is None:
                    raise AssertionError("Validated weapon plan has no target")
                equipment = unit.equipment[plan.source_equipment_index]
                definition = self._weapon_definitions[plan.target_id]
                # A catalog target can be a deliberately broad same-role
                # abstraction. The mapping remains the runtime authority for
                # this attachment's exact engagement envelope.
                runtime_definition = WeaponDefinition.model_validate({
                    **definition.model_dump(mode="python"),
                    "target_domains": [
                        domain.name
                        for domain in record.required_target_domains
                    ],
                    "compatible_ammo": list(plan.ammo_ids),
                    "rate_of_fire_rpm": (
                        definition.rate_of_fire_rpm
                        * record.runtime_system_multiplier
                    ),
                    # Aggregate systems produce more firing events, not more
                    # rounds in each target-system burst.
                    "burst_size": definition.burst_size,
                    "magazine_capacity": (
                        definition.magazine_capacity
                        * record.runtime_system_multiplier
                    ),
                    "barrel_life_rounds": (
                        definition.barrel_life_rounds
                        * record.runtime_system_multiplier
                    ),
                })
                ammo_definitions = tuple(
                    self._ammo_definitions[ammo_id]
                    for ammo_id in plan.ammo_ids
                )
                instance = WeaponInstance(
                    definition=runtime_definition,
                    ammo_state=AmmoState(rounds_by_type={
                        ammo.ammo_id: runtime_definition.magazine_capacity
                        for ammo in ammo_definitions
                    }),
                    equipment=equipment,
                )
                weapons.append(WeaponAttachment(
                    weapon=instance,
                    ammunition=ammo_definitions,
                    source_equipment=equipment,
                    source_equipment_index=plan.source_equipment_index,
                    modeled_role=record.modeled_role,
                    reference_kind=record.reference_kind,
                    mapping_rationale=record.rationale,
                    mapping_source=record.source,
                    source_system_count=record.source_system_count,
                    target_system_count=record.target_system_count,
                    runtime_system_multiplier=(
                        record.runtime_system_multiplier
                    ),
                ))

            weapon_by_source_index = {
                attachment.source_equipment_index: attachment
                for attachment in weapons
            }
            if len(weapon_by_source_index) != len(weapons):
                raise AssertionError("Validated weapon source indexes collided")

            sensor_attachments: list[SensorAttachment] = []
            resolutions: list[EquipmentResolution] = []
            for plan in self._plans[unit.unit_type]:
                equipment = unit.equipment[plan.source_equipment_index]
                record = plan.record
                if isinstance(record, WeaponAttachmentMapping):
                    if plan.target_id is None:
                        raise AssertionError("Validated weapon plan has no target")
                    resolutions.append(EquipmentResolution(
                        unit_id=unit.entity_id,
                        unit_type=unit.unit_type,
                        source_equipment=equipment,
                        source_equipment_index=plan.source_equipment_index,
                        category=EquipmentCategory.WEAPON,
                        disposition=ResolutionDisposition.ATTACHMENT,
                        modeled_role=record.modeled_role,
                        reference_kind=record.reference_kind,
                        target_id=plan.target_id,
                        source_system_count=record.source_system_count,
                        target_system_count=record.target_system_count,
                        runtime_system_multiplier=(
                            record.runtime_system_multiplier
                        ),
                    ))
                elif isinstance(record, WeaponStoreMapping):
                    resolutions.append(EquipmentResolution(
                        unit_id=unit.entity_id,
                        unit_type=unit.unit_type,
                        source_equipment=equipment,
                        source_equipment_index=plan.source_equipment_index,
                        category=EquipmentCategory.WEAPON,
                        disposition=ResolutionDisposition.STORE,
                        reference_kind=record.reference_kind,
                        target_id=record.ammo_id,
                        attached_to_equipment_index=(
                            plan.attached_to_equipment_index
                        ),
                        attached_to_target_id=plan.attached_to_target_id,
                    ))
                elif isinstance(record, WeaponNonRuntimeMapping):
                    resolutions.append(EquipmentResolution(
                        unit_id=unit.entity_id,
                        unit_type=unit.unit_type,
                        source_equipment=equipment,
                        source_equipment_index=plan.source_equipment_index,
                        category=EquipmentCategory.WEAPON,
                        disposition=ResolutionDisposition.NON_RUNTIME,
                        reason=record.reason,
                    ))
                elif isinstance(record, SensorAttachmentMapping):
                    if plan.target_id is None:
                        raise AssertionError("Validated sensor plan has no target")
                    definition = self._sensor_definitions[plan.target_id]
                    runtime_definition = SensorDefinition.model_validate({
                        **definition.model_dump(mode="python"),
                        "max_range_m": (
                            record.modeled_max_range_m
                            if record.modeled_max_range_m is not None
                            else definition.max_range_m
                        ),
                        "fov_deg": (
                            record.modeled_fov_deg
                            if record.modeled_fov_deg is not None
                            else definition.fov_deg
                        ),
                        "target_domains": [
                            domain.name
                            for domain in record.required_target_domains
                        ],
                    })
                    sensor = SensorInstance(
                        runtime_definition,
                        equipment,
                    )
                    compatible_weapon_source_indexes = tuple(sorted(
                        source_index
                        for source_index, weapon_attachment
                        in weapon_by_source_index.items()
                        if weapon_attachment.modeled_role
                        in record.compatible_weapon_roles
                    ))
                    sensor_attachments.append(SensorAttachment(
                        sensor=sensor,
                        source_equipment=equipment,
                        source_equipment_index=plan.source_equipment_index,
                        modeled_role=record.modeled_role,
                        reference_kind=record.reference_kind,
                        mapping_rationale=record.rationale,
                        mapping_source=record.source,
                        compatible_weapon_roles=(
                            record.compatible_weapon_roles
                        ),
                        compatible_weapon_source_indexes=(
                            compatible_weapon_source_indexes
                        ),
                    ))
                    resolutions.append(EquipmentResolution(
                        unit_id=unit.entity_id,
                        unit_type=unit.unit_type,
                        source_equipment=equipment,
                        source_equipment_index=plan.source_equipment_index,
                        category=EquipmentCategory.SENSOR,
                        disposition=ResolutionDisposition.ATTACHMENT,
                        modeled_role=record.modeled_role,
                        reference_kind=record.reference_kind,
                        target_id=plan.target_id,
                    ))
                elif isinstance(record, SensorNonRuntimeMapping):
                    resolutions.append(EquipmentResolution(
                        unit_id=unit.entity_id,
                        unit_type=unit.unit_type,
                        source_equipment=equipment,
                        source_equipment_index=plan.source_equipment_index,
                        category=EquipmentCategory.SENSOR,
                        disposition=ResolutionDisposition.NON_RUNTIME,
                        reason=record.reason,
                    ))
                else:  # pragma: no cover - unsupported fails preflight
                    raise AssertionError(f"Unhandled mapping record {record!r}")

            weapons.sort(key=lambda attachment: (
                -attachment.weapon.definition.max_range_m,
                attachment.source_equipment_index,
                attachment.weapon.weapon_id,
            ))
            unit_weapons[unit.entity_id] = tuple(weapons)
            unit_sensor_attachments[unit.entity_id] = tuple(
                sensor_attachments
            )
            unit_resolutions[unit.entity_id] = tuple(resolutions)

        return RuntimeLoadouts(
            unit_weapons=unit_weapons,
            unit_sensor_attachments=unit_sensor_attachments,
            equipment_resolutions=unit_resolutions,
        )

    def _validate_runtime_topology(self, unit: Unit) -> None:
        if unit.unit_type not in self._plans:
            raise EquipmentMappingError(
                f"unit {unit.entity_id!r} has unit_type {unit.unit_type!r} "
                "outside this builder's reachable envelope",
            )
        definition = self._unit_definitions[unit.unit_type]
        expected_domain = runtime_domain_for_definition(definition)
        if unit.domain is not expected_domain:
            raise EquipmentMappingError(
                f"unit {unit.entity_id!r} ({unit.unit_type!r}) has runtime "
                f"domain {unit.domain.name}, expected {expected_domain.name}",
            )
        if len(unit.equipment) != len(definition.equipment):
            raise EquipmentMappingError(
                f"unit {unit.entity_id!r} ({unit.unit_type!r}) has "
                f"{len(unit.equipment)} live equipment items but its effective "
                f"definition has {len(definition.equipment)}",
            )
        equipment_ids: dict[str, int] = {}
        for source_index, (live, authored) in enumerate(
            zip(unit.equipment, definition.equipment, strict=True),
        ):
            if not live.equipment_id or not live.equipment_id.strip():
                raise EquipmentMappingError(
                    f"{_runtime_context(unit, source_index, live)}: empty "
                    "equipment_id",
                )
            if live.equipment_id in equipment_ids:
                raise EquipmentMappingError(
                    f"{_runtime_context(unit, source_index, live)}: duplicate "
                    f"equipment_id also used at index "
                    f"{equipment_ids[live.equipment_id]}",
                )
            equipment_ids[live.equipment_id] = source_index
            try:
                authored_category = EquipmentCategory[
                    authored.category.upper()
                ]
            except KeyError as exc:
                raise EquipmentMappingError(
                    f"Effective unit definition {unit.unit_type!r} has unknown "
                    f"equipment category {authored.category!r}",
                ) from exc
            if (
                live.name != authored.name
                or live.category is not authored_category
                or live.weight_kg != authored.weight_kg
                or live.reliability != authored.reliability
                or live.temperature_range
                != (
                    tuple(authored.temperature_range)
                    if authored.temperature_range
                    else (-40.0, 50.0)
                )
            ):
                raise EquipmentMappingError(
                    f"{_runtime_context(unit, source_index, live)} does not "
                    "match effective authored topology "
                    f"({authored_category.name}, {authored.name!r}, "
                    f"weight_kg={authored.weight_kg}, "
                    f"reliability={authored.reliability}, "
                    "temperature_range="
                    f"{authored.temperature_range!r})",
                )
