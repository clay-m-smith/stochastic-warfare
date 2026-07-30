"""Strict production loading and semantic resolution for space catalogs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from stochastic_warfare.core.strict_yaml import load_yaml_unique
from stochastic_warfare.space.config import (
    ASATAssetConfig,
    ASATOrderConfig,
    ASATType,
    ASATWeaponDefinition,
    ConstellationDefinition,
    ConstellationType,
    SpaceConfig,
)
from stochastic_warfare.space.orbits import R_EARTH


class UnsupportedIMINTFusionError(ValueError):
    """Raised when selected imagery lacks a defensible fusion contract."""


@dataclass(frozen=True, slots=True)
class ResolvedSpaceCatalog:
    """One scenario's immutable selected space catalog envelope."""

    constellations: tuple[ConstellationDefinition, ...]
    imint_fusion_constellations: tuple[ConstellationDefinition, ...]
    weapon_definitions: dict[str, ASATWeaponDefinition]
    assets: tuple[ASATAssetConfig, ...]
    orders: tuple[ASATOrderConfig, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class SpaceCatalog:
    """All validated repository constellation and ASAT definitions."""

    constellations: dict[str, ConstellationDefinition]
    weapons: dict[str, ASATWeaponDefinition]

    @classmethod
    def load(cls, data_dir: Path) -> SpaceCatalog:
        """Load every repository space definition in canonical path order."""
        root = Path(data_dir) / "space"
        constellation_dir = root / "constellations"
        weapon_dir = root / "asat_weapons"
        constellation_paths = sorted(constellation_dir.glob("*.yaml"))
        weapon_paths = sorted(weapon_dir.glob("*.yaml"))
        if not constellation_paths:
            raise ValueError(
                f"No constellation definitions found under {constellation_dir}",
            )
        if not weapon_paths:
            raise ValueError(
                f"No ASAT weapon definitions found under {weapon_dir}",
            )

        constellations: dict[str, ConstellationDefinition] = {}
        for path in constellation_paths:
            definition = _load_definition(path, ConstellationDefinition)
            prior = constellations.get(definition.constellation_id)
            if prior is not None:
                raise ValueError(
                    "Duplicate constellation_id "
                    f"{definition.constellation_id!r} in {path}",
                )
            constellations[definition.constellation_id] = definition

        weapons: dict[str, ASATWeaponDefinition] = {}
        for path in weapon_paths:
            definition = _load_definition(path, ASATWeaponDefinition)
            prior = weapons.get(definition.weapon_id)
            if prior is not None:
                raise ValueError(
                    f"Duplicate ASAT weapon_id {definition.weapon_id!r} in {path}",
                )
            weapons[definition.weapon_id] = definition

        return cls(
            constellations=constellations,
            weapons=weapons,
        )

    def resolve(
        self,
        config: SpaceConfig,
        *,
        scenario_sides: set[str],
    ) -> ResolvedSpaceCatalog:
        """Resolve one strict scenario selection before runtime construction."""
        selected: list[ConstellationDefinition] = []
        satellite_sides: dict[str, tuple[str, str]] = {}
        for constellation_id in config.constellation_ids:
            try:
                definition = self.constellations[constellation_id]
            except KeyError as exc:
                raise ValueError(
                    "space_config references unknown constellation_id "
                    f"{constellation_id!r}",
                ) from exc
            if definition.side not in scenario_sides:
                raise ValueError(
                    f"Constellation {constellation_id!r} belongs to side "
                    f"{definition.side!r}, which is not declared by the scenario",
                )
            selected.append(definition)
            for satellite_id in generated_satellite_ids(definition):
                if satellite_id in satellite_sides:
                    raise ValueError(
                        f"Selected constellations generate duplicate satellite_id "
                        f"{satellite_id!r}",
                    )
                satellite_sides[satellite_id] = (
                    definition.side,
                    definition.constellation_id,
                )

        selected_by_id = {
            definition.constellation_id: definition
            for definition in selected
        }
        fusion_constellations: list[ConstellationDefinition] = []
        expected_sensor_type = {
            ConstellationType.IMAGING_OPTICAL: "optical",
            ConstellationType.IMAGING_SAR: "sar",
        }
        for constellation_id in config.imint_fusion_constellation_ids:
            definition = selected_by_id[constellation_id]
            sensor_type = expected_sensor_type.get(
                definition.constellation_type,
            )
            if sensor_type is None or definition.sensor_type != sensor_type:
                raise UnsupportedIMINTFusionError(
                    f"Constellation {constellation_id!r} is not a supported "
                    "optical or SAR imaging definition",
                )
            if (
                definition.sensor_resolution_m <= 0.0
                or definition.sensor_swath_km <= 0.0
            ):
                raise UnsupportedIMINTFusionError(
                    f"Constellation {constellation_id!r} requires positive "
                    "sensor resolution and swath for IMINT fusion",
                )
            if definition.imint_position_sigma_m is None:
                raise UnsupportedIMINTFusionError(
                    f"Constellation {constellation_id!r} has no sourced "
                    "imint_position_sigma_m and is unsupported for fusion",
                )
            fusion_constellations.append(definition)

        referenced_weapons: dict[str, ASATWeaponDefinition] = {}
        assets_by_id = {asset.asset_id: asset for asset in config.asat_assets}
        for asset in config.asat_assets:
            if asset.side not in scenario_sides:
                raise ValueError(
                    f"ASAT asset {asset.asset_id!r} belongs to unknown scenario "
                    f"side {asset.side!r}",
                )
            try:
                definition = self.weapons[asset.weapon_id]
            except KeyError as exc:
                raise ValueError(
                    f"ASAT asset {asset.asset_id!r} references unknown weapon_id "
                    f"{asset.weapon_id!r}",
                ) from exc
            if definition.asat_type is not ASATType.DIRECT_ASCENT_KKV:
                raise ValueError(
                    f"ASAT asset {asset.asset_id!r} uses unsupported production "
                    f"type {definition.asat_type.name}",
                )
            referenced_weapons[definition.weapon_id] = definition

        for order in config.asat_orders:
            asset = assets_by_id[order.asset_id]
            try:
                target_side, constellation_id = satellite_sides[
                    order.target_satellite_id
                ]
            except KeyError as exc:
                raise ValueError(
                    f"ASAT order {order.order_id!r} references unknown selected "
                    f"target_satellite_id {order.target_satellite_id!r}",
                ) from exc
            if target_side == asset.side:
                raise ValueError(
                    f"ASAT order {order.order_id!r} targets friendly satellite "
                    f"{order.target_satellite_id!r} on side {target_side!r}",
                )
            weapon = referenced_weapons[asset.weapon_id]
            constellation = self.constellations[constellation_id]
            minimum_altitude_km, maximum_altitude_km = altitude_envelope_km(
                constellation,
            )
            if (
                maximum_altitude_km < weapon.min_altitude_km
                or minimum_altitude_km > weapon.max_altitude_km
            ):
                raise ValueError(
                    f"ASAT order {order.order_id!r} target orbit "
                    f"[{minimum_altitude_km:.3f}, {maximum_altitude_km:.3f}] km "
                    f"does not intersect weapon {weapon.weapon_id!r} envelope "
                    f"[{weapon.min_altitude_km:.3f}, "
                    f"{weapon.max_altitude_km:.3f}] km",
                )

        payload = {
            "config": config.model_dump(mode="json"),
            "constellations": [
                definition.model_dump(mode="json")
                for definition in selected
            ],
            "weapons": [
                referenced_weapons[weapon_id].model_dump(mode="json")
                for weapon_id in sorted(referenced_weapons)
            ],
            "assets": [
                asset.model_dump(mode="json")
                for asset in config.asat_assets
            ],
            "orders": [
                order.model_dump(mode="json")
                for order in config.asat_orders
            ],
        }
        fingerprint = hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
        ).hexdigest()
        return ResolvedSpaceCatalog(
            constellations=tuple(selected),
            imint_fusion_constellations=tuple(fusion_constellations),
            weapon_definitions=referenced_weapons,
            assets=tuple(config.asat_assets),
            orders=tuple(config.asat_orders),
            fingerprint=fingerprint,
        )


def generated_satellite_ids(
    definition: ConstellationDefinition,
) -> tuple[str, ...]:
    """Return the exact stable IDs produced for one strict constellation."""
    return tuple(
        f"{definition.constellation_id}_p{plane}_s{slot}"
        for plane in range(definition.plane_count)
        for slot in range(definition.sats_per_plane)
    )


def altitude_envelope_km(
    definition: ConstellationDefinition,
) -> tuple[float, float]:
    """Return perigee/apogee altitudes for static reachability validation."""
    elements = definition.orbital_elements_template
    perigee = elements.semi_major_axis_m * (1.0 - elements.eccentricity)
    apogee = elements.semi_major_axis_m * (1.0 + elements.eccentricity)
    return (
        (perigee - R_EARTH) / 1000.0,
        (apogee - R_EARTH) / 1000.0,
    )


def validate_constellation_file(path: Path) -> ConstellationDefinition:
    """Strictly validate one constellation catalog file."""
    return _load_definition(path, ConstellationDefinition)


def validate_asat_weapon_file(path: Path) -> ASATWeaponDefinition:
    """Strictly validate one ASAT weapon catalog file."""
    return _load_definition(path, ASATWeaponDefinition)


def _load_definition(path: Path, model_type: type[Any]) -> Any:
    try:
        with open(path, encoding="utf-8") as definition_file:
            raw = load_yaml_unique(definition_file)
        if not isinstance(raw, dict):
            raise ValueError("definition root must be a mapping")
        return model_type.model_validate(raw)
    except (OSError, TypeError, ValueError, ValidationError) as exc:
        raise ValueError(f"{path}: invalid space catalog definition: {exc}") from exc
