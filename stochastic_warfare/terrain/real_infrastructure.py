"""OSM GeoJSON → InfrastructureManager loader.

Reads pre-converted GeoJSON files (roads, buildings, railways) and
produces an :class:`InfrastructureManager` with all features in ENU
coordinates.  No network dependencies at runtime — the download script
handles OSM→GeoJSON conversion.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from stochastic_warfare.coordinates.transforms import ScenarioProjection
    from stochastic_warfare.terrain.data_pipeline import BoundingBox

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.terrain.infrastructure import (
    Bridge,
    Building,
    InfrastructureManager,
    RailLine,
    Road,
    RoadType,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# OSM highway → RoadType mapping
# ---------------------------------------------------------------------------

_HIGHWAY_TO_ROAD_TYPE: dict[str, RoadType] = {
    "motorway": RoadType.HIGHWAY,
    "motorway_link": RoadType.HIGHWAY,
    "trunk": RoadType.HIGHWAY,
    "trunk_link": RoadType.HIGHWAY,
    "primary": RoadType.PAVED,
    "primary_link": RoadType.PAVED,
    "secondary": RoadType.PAVED,
    "secondary_link": RoadType.PAVED,
    "tertiary": RoadType.IMPROVED_DIRT,
    "tertiary_link": RoadType.IMPROVED_DIRT,
    "residential": RoadType.IMPROVED_DIRT,
    "service": RoadType.IMPROVED_DIRT,
    "unclassified": RoadType.IMPROVED_DIRT,
    "track": RoadType.UNIMPROVED,
    "path": RoadType.TRAIL,
    "footway": RoadType.TRAIL,
    "cycleway": RoadType.TRAIL,
    "bridleway": RoadType.TRAIL,
}


def highway_to_road_type(highway: str) -> RoadType:
    """Map an OSM ``highway`` tag value to RoadType."""
    return _HIGHWAY_TO_ROAD_TYPE.get(highway, RoadType.UNIMPROVED)


# ---------------------------------------------------------------------------
# Coordinate conversion
# ---------------------------------------------------------------------------


def _convert_coords(
    lon_lat_pairs: list[list[float]],
    projection: ScenarioProjection,
) -> list[tuple[float, float]]:
    """Convert [[lon, lat], ...] to [(easting, northing), ...]."""
    result: list[tuple[float, float]] = []
    for pair in lon_lat_pairs:
        lon, lat = pair[0], pair[1]
        pos = projection.geodetic_to_enu(lat, lon)
        result.append((pos.easting, pos.northing))
    return result


def _in_bbox(lon: float, lat: float, bbox: BoundingBox | None) -> bool:
    """Check if a point is within the bounding box."""
    if bbox is None:
        return True
    return (bbox.south <= lat <= bbox.north) and (bbox.west <= lon <= bbox.east)


# ---------------------------------------------------------------------------
# Feature extractors
# ---------------------------------------------------------------------------


def _extract_roads(
    features: list[dict[str, Any]],
    projection: ScenarioProjection,
    bbox: BoundingBox | None,
) -> tuple[list[Road], list[Bridge]]:
    """Extract roads and bridges from GeoJSON features."""
    roads: list[Road] = []
    bridges: list[Bridge] = []
    road_idx = 0

    for feat in features:
        geom = feat.get("geometry", {})
        props = feat.get("properties", {})
        geom_type = geom.get("type", "")

        if geom_type not in ("LineString", "MultiLineString"):
            continue

        highway = props.get("highway", "")
        if not highway:
            continue

        coords_list = geom.get("coordinates", [])
        if geom_type == "MultiLineString":
            segments = coords_list
        else:
            segments = [coords_list]

        for coords in segments:
            if not coords:
                continue

            # Bbox clip: skip if first point outside bbox
            if bbox is not None and not _in_bbox(coords[0][0], coords[0][1], bbox):
                continue

            enu_points = _convert_coords(coords, projection)
            road_id = f"osm_road_{road_idx}"
            road_idx += 1

            road_type = highway_to_road_type(highway)
            road = Road(
                road_id=road_id,
                road_type=road_type,
                points=enu_points,
                width=_road_width(highway),
            )
            roads.append(road)

            # Check bridge tag
            if props.get("bridge") in ("yes", "true", "1"):
                mid_idx = len(enu_points) // 2
                mid = enu_points[mid_idx] if enu_points else (0.0, 0.0)
                bridge = Bridge(
                    bridge_id=f"osm_bridge_{len(bridges)}",
                    position=mid,
                    road_id=road_id,
                    capacity_tons=_bridge_capacity(highway),
                )
                bridges.append(bridge)

    return roads, bridges


def _road_width(highway: str) -> float:
    """Estimate road width from OSM highway type."""
    widths = {
        "motorway": 12.0,
        "trunk": 10.0,
        "primary": 8.0,
        "secondary": 7.0,
        "tertiary": 6.0,
        "residential": 5.0,
        "service": 4.0,
        "track": 3.0,
        "path": 2.0,
        "footway": 1.5,
    }
    return widths.get(highway, 6.0)


def _bridge_capacity(highway: str) -> float:
    """Estimate bridge capacity from road type."""
    capacities = {
        "motorway": 70.0,
        "trunk": 60.0,
        "primary": 50.0,
        "secondary": 40.0,
    }
    return capacities.get(highway, 30.0)


def _extract_buildings(
    features: list[dict[str, Any]],
    projection: ScenarioProjection,
    bbox: BoundingBox | None,
) -> list[Building]:
    """Extract building footprints from GeoJSON features."""
    buildings: list[Building] = []

    for feat in features:
        geom = feat.get("geometry", {})
        props = feat.get("properties", {})
        geom_type = geom.get("type", "")

        if geom_type != "Polygon":
            continue

        coords = geom.get("coordinates", [])
        if not coords or not coords[0]:
            continue

        # Check bbox with first vertex
        first = coords[0][0]
        if bbox is not None and not _in_bbox(first[0], first[1], bbox):
            continue

        enu_ring = _convert_coords(coords[0], projection)
        building_type = props.get("building", "yes")
        height = float(props.get("height", props.get("building:levels", 3)) or 10.0)
        if isinstance(height, str):
            try:
                height = float(height)
            except ValueError:
                height = 10.0
        # If it's levels, convert to meters
        if height < 10 and "levels" in str(props.get("building:levels", "")):
            height *= 3.0

        construction = _building_construction(building_type)

        buildings.append(Building(
            building_id=f"osm_bldg_{len(buildings)}",
            footprint=enu_ring,
            height=max(height, 3.0),
            construction=construction,
        ))

    return buildings


def _building_construction(building_type: str) -> str:
    """Estimate construction material from OSM building type."""
    heavy = {"apartments", "commercial", "industrial", "office", "hospital"}
    if building_type in heavy:
        return "concrete"
    return "masonry"


def _extract_railways(
    features: list[dict[str, Any]],
    projection: ScenarioProjection,
    bbox: BoundingBox | None,
) -> list[RailLine]:
    """Extract rail lines from GeoJSON features."""
    rails: list[RailLine] = []

    for feat in features:
        geom = feat.get("geometry", {})
        props = feat.get("properties", {})
        geom_type = geom.get("type", "")

        if geom_type not in ("LineString", "MultiLineString"):
            continue

        railway = props.get("railway", "")
        if railway not in ("rail", "light_rail", "narrow_gauge"):
            continue

        coords_list = geom.get("coordinates", [])
        if geom_type == "MultiLineString":
            segments = coords_list
        else:
            segments = [coords_list]

        for coords in segments:
            if not coords:
                continue

            if bbox is not None and not _in_bbox(coords[0][0], coords[0][1], bbox):
                continue

            enu_points = _convert_coords(coords, projection)
            gauge = "narrow" if railway == "narrow_gauge" else "standard"
            rails.append(RailLine(
                rail_id=f"osm_rail_{len(rails)}",
                points=enu_points,
                gauge=gauge,
            ))

    return rails


# ---------------------------------------------------------------------------
# Main loader
# ---------------------------------------------------------------------------


def load_osm_infrastructure(
    geojson_paths: dict[str, Path],
    projection: ScenarioProjection,
    bbox: BoundingBox | None = None,
) -> InfrastructureManager:
    """Load OSM GeoJSON files and produce an InfrastructureManager.

    Parameters
    ----------
    geojson_paths:
        Mapping of layer name to GeoJSON file path.
        Expected keys: ``"roads"``, ``"buildings"``, ``"railways"``.
    projection:
        :class:`ScenarioProjection` for geodetic→ENU.
    bbox:
        Optional :class:`BoundingBox` for clipping.
    """
    roads: list[Road] = []
    bridges: list[Bridge] = []
    buildings: list[Building] = []
    rail_lines: list[RailLine] = []

    # Roads (+ bridges)
    if "roads" in geojson_paths:
        with open(geojson_paths["roads"]) as f:
            data = json.load(f)
        features = data.get("features", [])
        r, b = _extract_roads(features, projection, bbox)
        roads.extend(r)
        bridges.extend(b)
        logger.info("Loaded %d roads, %d bridges from OSM", len(r), len(b))

    # Buildings
    if "buildings" in geojson_paths:
        with open(geojson_paths["buildings"]) as f:
            data = json.load(f)
        features = data.get("features", [])
        bldgs = _extract_buildings(features, projection, bbox)
        buildings.extend(bldgs)
        logger.info("Loaded %d buildings from OSM", len(bldgs))

    # Railways
    if "railways" in geojson_paths:
        with open(geojson_paths["railways"]) as f:
            data = json.load(f)
        features = data.get("features", [])
        rls = _extract_railways(features, projection, bbox)
        rail_lines.extend(rls)
        logger.info("Loaded %d rail lines from OSM", len(rls))

    return InfrastructureManager(
        roads=roads,
        bridges=bridges,
        buildings=buildings,
        rail_lines=rail_lines,
    )
