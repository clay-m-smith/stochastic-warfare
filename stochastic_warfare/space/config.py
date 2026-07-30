"""Strict, dependency-neutral configuration for the space domain.

The catalog and scenario models live here so constellation and ASAT runtime
modules can depend on one schema boundary without importing each other.
"""

from __future__ import annotations

import enum
import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_EARTH_RADIUS_M = 6_371_000.0
# The production propagator is an Earth-orbit campaign abstraction, not an
# interplanetary trajectory model.  One billion metres is a deliberately broad
# Earth-centred envelope (well beyond every shipped military orbit) and keeps
# all two-body/J2 arithmetic inside its validated numerical domain.
_MAX_SEMI_MAJOR_AXIS_M = 1_000_000_000.0
# NumPy's Poisson sampler returns signed 64-bit counts and rejects a mean
# within ten standard deviations of that integer limit.  This conservative
# ceiling leaves ample numerical headroom while remaining far above any
# defensible authored debris abstraction.
_MAX_DEBRIS_FRAGMENT_MEAN = 1.0e18


def _require_identifier(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
    return value


def _require_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value


def _require_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number")
    try:
        normalized = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{field_name} must be finite") from exc
    if not math.isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    return normalized


def _require_strict_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be boolean")
    return value


def _require_positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")
    return value


class ConstellationType(enum.IntEnum):
    """Type of satellite constellation."""

    GPS = 0
    GLONASS = 1
    IMAGING_OPTICAL = 2
    IMAGING_SAR = 3
    SIGINT = 4
    EARLY_WARNING = 5
    SATCOM = 6


class ASATType(enum.IntEnum):
    """Type of anti-satellite weapon definition."""

    DIRECT_ASCENT_KKV = 0
    CO_ORBITAL = 1
    GROUND_LASER_DAZZLE = 2
    GROUND_LASER_DESTRUCT = 3


class OrbitalElementsTemplate(BaseModel):
    """Validated classical elements used to generate one constellation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    semi_major_axis_m: float
    eccentricity: float
    inclination_deg: float
    raan_deg: float
    arg_perigee_deg: float
    true_anomaly_deg: float

    @field_validator(
        "semi_major_axis_m",
        "eccentricity",
        "inclination_deg",
        "raan_deg",
        "arg_perigee_deg",
        "true_anomaly_deg",
        mode="before",
    )
    @classmethod
    def _finite_elements(cls, value: Any, info: Any) -> float:
        return _require_number(value, info.field_name)

    @model_validator(mode="after")
    def _valid_orbit(self) -> OrbitalElementsTemplate:
        if self.semi_major_axis_m <= 0.0:
            raise ValueError("semi_major_axis_m must be positive")
        if self.semi_major_axis_m > _MAX_SEMI_MAJOR_AXIS_M:
            raise ValueError(
                "semi_major_axis_m exceeds the supported Earth-orbit "
                f"envelope {_MAX_SEMI_MAJOR_AXIS_M:g}",
            )
        if not 0.0 <= self.eccentricity < 1.0:
            raise ValueError("eccentricity must be in [0, 1)")
        if not 0.0 <= self.inclination_deg <= 180.0:
            raise ValueError("inclination_deg must be in [0, 180]")
        for field_name in (
            "raan_deg",
            "arg_perigee_deg",
            "true_anomaly_deg",
        ):
            if not 0.0 <= getattr(self, field_name) < 360.0:
                raise ValueError(f"{field_name} must be in [0, 360)")
        perigee_m = self.semi_major_axis_m * (1.0 - self.eccentricity)
        if perigee_m <= _EARTH_RADIUS_M:
            raise ValueError(
                "orbital perigee must remain above Earth's surface",
            )
        return self


class ConstellationDefinition(BaseModel):
    """Strict YAML-loaded constellation definition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    constellation_id: str
    display_name: str = ""
    constellation_type: ConstellationType
    side: str
    num_satellites: int
    orbital_elements_template: OrbitalElementsTemplate
    plane_count: int
    sats_per_plane: int
    sensor_resolution_m: float = 0.0
    sensor_swath_km: float = 0.0
    sensor_type: Literal["optical", "sar", "ir", "none"] = "none"
    imint_position_sigma_m: float | None = None
    bandwidth_bps: float = 0.0
    detection_delay_s: float = 0.0
    detection_confidence: float = 0.0

    @field_validator("constellation_id", "side", mode="before")
    @classmethod
    def _identifiers(cls, value: Any, info: Any) -> str:
        return _require_identifier(value, info.field_name)

    @field_validator("display_name", mode="before")
    @classmethod
    def _display_name_string(cls, value: Any) -> str:
        return _require_string(value, "display_name")

    @field_validator("constellation_type", mode="before")
    @classmethod
    def _known_constellation_type(cls, value: Any) -> ConstellationType:
        if not (
            type(value) is int
            or isinstance(value, ConstellationType)
        ):
            raise ValueError("constellation_type must be an integer enum value")
        try:
            return ConstellationType(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"unknown constellation_type {value!r}",
            ) from exc

    @field_validator(
        "num_satellites",
        "plane_count",
        "sats_per_plane",
        mode="before",
    )
    @classmethod
    def _positive_counts(cls, value: Any, info: Any) -> int:
        return _require_positive_int(value, info.field_name)

    @field_validator(
        "sensor_resolution_m",
        "sensor_swath_km",
        "bandwidth_bps",
        "detection_delay_s",
        "detection_confidence",
        mode="before",
    )
    @classmethod
    def _finite_metadata(cls, value: Any, info: Any) -> float:
        return _require_number(value, info.field_name)

    @field_validator("imint_position_sigma_m", mode="before")
    @classmethod
    def _optional_position_sigma(
        cls,
        value: Any,
    ) -> float | None:
        if value is None:
            return None
        return _require_number(value, "imint_position_sigma_m")

    @model_validator(mode="after")
    def _valid_metadata_and_topology(self) -> ConstellationDefinition:
        if self.num_satellites != self.plane_count * self.sats_per_plane:
            raise ValueError(
                "num_satellites must equal plane_count * sats_per_plane",
            )
        for field_name in (
            "sensor_resolution_m",
            "sensor_swath_km",
            "bandwidth_bps",
            "detection_delay_s",
        ):
            if getattr(self, field_name) < 0.0:
                raise ValueError(f"{field_name} must be non-negative")
        if not 0.0 <= self.detection_confidence <= 1.0:
            raise ValueError("detection_confidence must be in [0, 1]")
        imaging_types = {
            ConstellationType.IMAGING_OPTICAL,
            ConstellationType.IMAGING_SAR,
        }
        if self.imint_position_sigma_m is not None:
            if self.constellation_type not in imaging_types:
                raise ValueError(
                    "imint_position_sigma_m is valid only for imaging "
                    "constellations",
                )
            if self.imint_position_sigma_m <= 0.0:
                raise ValueError("imint_position_sigma_m must be positive")
        return self


class ASATWeaponDefinition(BaseModel):
    """Strict YAML-loaded ASAT weapon definition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    weapon_id: str
    display_name: str = ""
    asat_type: ASATType
    lethal_radius_m: float
    guidance_sigma_m: float
    max_altitude_km: float
    min_altitude_km: float
    closing_velocity_mps: float
    reload_time_s: float
    dazzle_duration_s: float
    dazzle_range_km: float

    @field_validator("weapon_id", mode="before")
    @classmethod
    def _weapon_identifier(cls, value: Any) -> str:
        return _require_identifier(value, "weapon_id")

    @field_validator("display_name", mode="before")
    @classmethod
    def _display_name_string(cls, value: Any) -> str:
        return _require_string(value, "display_name")

    @field_validator("asat_type", mode="before")
    @classmethod
    def _known_asat_type(cls, value: Any) -> ASATType:
        if not (
            type(value) is int
            or isinstance(value, ASATType)
        ):
            raise ValueError("asat_type must be an integer enum value")
        try:
            return ASATType(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"unknown asat_type {value!r}") from exc

    @field_validator(
        "lethal_radius_m",
        "guidance_sigma_m",
        "max_altitude_km",
        "min_altitude_km",
        "closing_velocity_mps",
        "reload_time_s",
        "dazzle_duration_s",
        "dazzle_range_km",
        mode="before",
    )
    @classmethod
    def _finite_parameters(cls, value: Any, info: Any) -> float:
        return _require_number(value, info.field_name)

    @model_validator(mode="after")
    def _valid_type_contract(self) -> ASATWeaponDefinition:
        if not 0.0 <= self.min_altitude_km < self.max_altitude_km:
            raise ValueError(
                "ASAT altitude bounds require "
                "0 <= min_altitude_km < max_altitude_km",
            )
        if self.reload_time_s < 0.0:
            raise ValueError("reload_time_s must be non-negative")

        kinetic_fields = (
            self.lethal_radius_m,
            self.guidance_sigma_m,
            self.closing_velocity_mps,
        )
        dazzle_fields = (self.dazzle_duration_s, self.dazzle_range_km)
        if self.asat_type in (
            ASATType.DIRECT_ASCENT_KKV,
            ASATType.CO_ORBITAL,
        ):
            if any(value <= 0.0 for value in kinetic_fields):
                raise ValueError(
                    "kinetic ASAT definitions require positive lethal radius, "
                    "guidance sigma, and closing velocity",
                )
            if any(value != 0.0 for value in dazzle_fields):
                raise ValueError(
                    "kinetic ASAT definitions require zero dazzle fields",
                )
        elif self.asat_type is ASATType.GROUND_LASER_DAZZLE:
            if any(value != 0.0 for value in kinetic_fields):
                raise ValueError(
                    "laser-dazzle definitions require zero kinetic fields",
                )
            if any(value <= 0.0 for value in dazzle_fields):
                raise ValueError(
                    "laser-dazzle definitions require positive dazzle fields",
                )
            if self.dazzle_range_km > self.max_altitude_km:
                raise ValueError(
                    "dazzle_range_km may not exceed max_altitude_km",
                )
        else:
            if any(value != 0.0 for value in (*kinetic_fields, *dazzle_fields)):
                raise ValueError(
                    "laser-destruct definitions require zero kinetic and "
                    "dazzle fields",
                )
        return self


class ASATAssetConfig(BaseModel):
    """One mutable, side-owned instance of an ASAT catalog definition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: str
    weapon_id: str
    side: str
    rounds_available: int

    @field_validator("asset_id", "weapon_id", "side", mode="before")
    @classmethod
    def _identifiers(cls, value: Any, info: Any) -> str:
        return _require_identifier(value, info.field_name)

    @field_validator("rounds_available", mode="before")
    @classmethod
    def _positive_rounds(cls, value: Any) -> int:
        return _require_positive_int(value, "rounds_available")


class ASATOrderConfig(BaseModel):
    """One immutable scheduled ASAT action against an exact satellite."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    order_id: str
    asset_id: str
    target_satellite_id: str
    execute_at_s: float

    @field_validator(
        "order_id",
        "asset_id",
        "target_satellite_id",
        mode="before",
    )
    @classmethod
    def _identifiers(cls, value: Any, info: Any) -> str:
        return _require_identifier(value, info.field_name)

    @field_validator("execute_at_s", mode="before")
    @classmethod
    def _execution_time(cls, value: Any) -> float:
        normalized = _require_number(value, "execute_at_s")
        if normalized < 0.0:
            raise ValueError("execute_at_s must be non-negative")
        return normalized


class SpaceConfig(BaseModel):
    """Strict scenario configuration for the space-domain runtime."""

    model_config = ConfigDict(extra="forbid")

    enable_space: bool = False
    constellation_ids: list[str] = Field(default_factory=list)
    imint_fusion_constellation_ids: list[str] = Field(default_factory=list)
    enable_asat: bool = False
    asat_assets: list[ASATAssetConfig] = Field(default_factory=list)
    asat_orders: list[ASATOrderConfig] = Field(default_factory=list)
    theater_lat: float | None = None
    theater_lon: float | None = None
    min_elevation_deg: float = 5.0
    update_interval_s: float = 3600.0
    gps_sigma_range_m: float = 3.0
    ins_drift_rate_m_per_s: float = 0.514
    ins_initial_sigma_m: float = 10.0
    cloud_cover_blocks_optical: bool = True
    isr_processing_delay_s: float = 300.0
    ew_processing_delay_s: float = 60.0
    debris_fragment_mean: float = 500.0
    debris_collision_prob_per_orbit: float = 1e-6

    @field_validator(
        "enable_space",
        "enable_asat",
        "cloud_cover_blocks_optical",
        mode="before",
    )
    @classmethod
    def _strict_booleans(cls, value: Any, info: Any) -> bool:
        return _require_strict_bool(value, info.field_name)

    @field_validator(
        "constellation_ids",
        "imint_fusion_constellation_ids",
        mode="before",
    )
    @classmethod
    def _constellation_identifiers(
        cls,
        value: Any,
        info: Any,
    ) -> Any:
        if not isinstance(value, list):
            raise ValueError(f"{info.field_name} must be a list")
        return [
            _require_identifier(item, f"{info.field_name} entry")
            for item in value
        ]

    @field_validator("asat_assets", "asat_orders", mode="before")
    @classmethod
    def _strict_declaration_lists(cls, value: Any, info: Any) -> Any:
        if not isinstance(value, list):
            raise ValueError(f"{info.field_name} must be a list")
        return value

    @field_validator("theater_lat", "theater_lon", mode="before")
    @classmethod
    def _optional_coordinates(cls, value: Any, info: Any) -> float | None:
        if value is None:
            return None
        return _require_number(value, info.field_name)

    @field_validator(
        "min_elevation_deg",
        "update_interval_s",
        "gps_sigma_range_m",
        "ins_drift_rate_m_per_s",
        "ins_initial_sigma_m",
        "isr_processing_delay_s",
        "ew_processing_delay_s",
        "debris_fragment_mean",
        "debris_collision_prob_per_orbit",
        mode="before",
    )
    @classmethod
    def _finite_parameters(cls, value: Any, info: Any) -> float:
        return _require_number(value, info.field_name)

    @model_validator(mode="after")
    def _valid_space_contract(self) -> SpaceConfig:
        if self.theater_lat is not None and not -90.0 <= self.theater_lat <= 90.0:
            raise ValueError("theater_lat must be in [-90, 90]")
        if self.theater_lon is not None and not -180.0 <= self.theater_lon <= 180.0:
            raise ValueError("theater_lon must be in [-180, 180]")
        if not 0.0 <= self.min_elevation_deg <= 90.0:
            raise ValueError("min_elevation_deg must be in [0, 90]")
        for field_name in (
            "update_interval_s",
            "gps_sigma_range_m",
            "ins_initial_sigma_m",
            "debris_fragment_mean",
        ):
            if getattr(self, field_name) <= 0.0:
                raise ValueError(f"{field_name} must be positive")
        if self.debris_fragment_mean > _MAX_DEBRIS_FRAGMENT_MEAN:
            raise ValueError(
                "debris_fragment_mean exceeds the safe Poisson sampling "
                f"limit {_MAX_DEBRIS_FRAGMENT_MEAN:g}",
            )
        for field_name in (
            "ins_drift_rate_m_per_s",
            "isr_processing_delay_s",
            "ew_processing_delay_s",
        ):
            if getattr(self, field_name) < 0.0:
                raise ValueError(f"{field_name} must be non-negative")
        if not 0.0 <= self.debris_collision_prob_per_orbit <= 1.0:
            raise ValueError(
                "debris_collision_prob_per_orbit must be in [0, 1]",
            )

        if len(self.constellation_ids) != len(set(self.constellation_ids)):
            raise ValueError("constellation_ids must not contain duplicates")
        if len(self.imint_fusion_constellation_ids) != len(
            set(self.imint_fusion_constellation_ids),
        ):
            raise ValueError(
                "imint_fusion_constellation_ids must not contain duplicates",
            )
        unknown_fusion_ids = [
            constellation_id
            for constellation_id in self.imint_fusion_constellation_ids
            if constellation_id not in self.constellation_ids
        ]
        if unknown_fusion_ids:
            raise ValueError(
                "imint_fusion_constellation_ids must be selected in "
                f"constellation_ids: {unknown_fusion_ids!r}",
            )
        asset_ids = [asset.asset_id for asset in self.asat_assets]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError("asat_assets must have unique asset_id values")
        order_ids = [order.order_id for order in self.asat_orders]
        if len(order_ids) != len(set(order_ids)):
            raise ValueError("asat_orders must have unique order_id values")
        known_assets = set(asset_ids)
        unknown_assets = [
            order.asset_id
            for order in self.asat_orders
            if order.asset_id not in known_assets
        ]
        if unknown_assets:
            raise ValueError(
                "asat_orders reference unknown asset_id values: "
                f"{unknown_assets!r}",
            )

        has_declarations = bool(
            self.constellation_ids
            or self.imint_fusion_constellation_ids
            or self.asat_assets
            or self.asat_orders
        )
        if not self.enable_space and (has_declarations or self.enable_asat):
            raise ValueError(
                "enable_space=false may not declare constellations, ASAT "
                "assets, ASAT orders, or enable ASAT",
            )
        if self.enable_asat and (
            not self.asat_assets
            or not self.asat_orders
        ):
            raise ValueError(
                "enable_asat=true requires at least one ASAT asset and order",
            )
        return self
