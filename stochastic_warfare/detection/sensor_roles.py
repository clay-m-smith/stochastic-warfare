"""Typed production roles represented by runtime sensor attachments."""

from __future__ import annotations

import enum


class SensorModeledRole(str, enum.Enum):
    """Production detection role represented by a sensor attachment."""

    VISUAL_OBSERVATION = "visual_observation"
    NIGHT_VISION = "night_vision"
    THERMAL_TARGETING = "thermal_targeting"
    AIRBORNE_FIRE_CONTROL_RADAR = "airborne_fire_control_radar"
    AIRBORNE_GROUND_FIRE_CONTROL_RADAR = (
        "airborne_ground_fire_control_radar"
    )
    AIRBORNE_MULTI_DOMAIN_FIRE_CONTROL_RADAR = (
        "airborne_multi_domain_fire_control_radar"
    )
    AIRBORNE_MARITIME_SEARCH_RADAR = "airborne_maritime_search_radar"
    AIR_SEARCH_RADAR = "air_search_radar"
    SHIP_AIR_SURFACE_SEARCH_RADAR = "ship_air_surface_search_radar"
    SURFACE_SEARCH_RADAR = "surface_search_radar"
    SHIP_SURFACE_SEARCH_RADAR = "ship_surface_search_radar"
    SUBMARINE_SURFACE_SEARCH_RADAR = "submarine_surface_search_radar"
    GROUND_SURVEILLANCE_RADAR = "ground_surveillance_radar"
    COASTAL_SURVEILLANCE_RADAR = "coastal_surveillance_radar"
    FIRE_CONTROL_RADAR = "fire_control_radar"
    GROUND_AIR_DEFENSE_FIRE_CONTROL_RADAR = (
        "ground_air_defense_fire_control_radar"
    )
    NAVAL_FIRE_CONTROL_RADAR = "naval_fire_control_radar"
    NAVAL_AIR_DEFENSE_FIRE_CONTROL_RADAR = (
        "naval_air_defense_fire_control_radar"
    )
    GROUND_VISUAL_SIGHT = "ground_visual_sight"
    GROUND_AIR_DEFENSE_OPTICAL_SIGHT = (
        "ground_air_defense_optical_sight"
    )
    AIRBORNE_VISUAL_SIGHT = "airborne_visual_sight"
    AIRBORNE_GROUND_VISUAL_TARGETING = (
        "airborne_ground_visual_targeting"
    )
    AIRBORNE_GROUND_BOMBSIGHT = "airborne_ground_bombsight"
    NAVAL_VISUAL_DIRECTOR = "naval_visual_director"
    NAVAL_AIR_DEFENSE_OPTICAL_DIRECTOR = (
        "naval_air_defense_optical_director"
    )
    NAVAL_LOOKOUT = "naval_lookout"
    GROUND_NIGHT_SIGHT = "ground_night_sight"
    GROUND_ACTIVE_IR_SIGHT = "ground_active_ir_sight"
    AIRBORNE_LOW_LIGHT_OBSERVATION = "airborne_low_light_observation"
    INDIVIDUAL_NIGHT_VISION = "individual_night_vision"
    GROUND_THERMAL_TARGETING = "ground_thermal_targeting"
    AIRBORNE_GROUND_THERMAL_TARGETING = (
        "airborne_ground_thermal_targeting"
    )
    AIRBORNE_AIR_THERMAL_SEARCH = "airborne_air_thermal_search"
    AIRBORNE_SURFACE_THERMAL_SEARCH = (
        "airborne_surface_thermal_search"
    )
    RADAR_WARNING_ESM = "radar_warning_esm"
    ELECTRONIC_SUPPORT = "electronic_support"
    ACTIVE_SONAR = "active_sonar"
    PASSIVE_SONAR = "passive_sonar"
