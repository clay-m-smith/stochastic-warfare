#!/usr/bin/env python
"""Download real-world terrain data for a bounding box.

This is the **only** script that performs network I/O.  The simulation
runtime is fully offline — it reads local files produced by this script.

Usage::

    uv run python scripts/download_terrain.py \\
        --bbox 32.6,35.3,33.6,36.3 \\
        --output data/terrain_raw \\
        --sources srtm,copernicus,osm

Sources
-------
- **srtm**: SRTM 1-arc-second elevation tiles (.hgt) from OpenTopography
- **copernicus**: CGLS-LC100 land cover GeoTIFF
- **osm**: OpenStreetMap features via Overpass API → GeoJSON
- **gebco**: GEBCO gridded bathymetry NetCDF (sub-oceanic regions only)
"""

from __future__ import annotations

import argparse
import json
import math
import urllib.request
from pathlib import Path


def _parse_bbox(s: str) -> tuple[float, float, float, float]:
    """Parse 'south,west,north,east' string."""
    parts = [float(x.strip()) for x in s.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must be south,west,north,east")
    south, west, north, east = parts
    if south >= north:
        raise ValueError(f"south ({south}) must be < north ({north})")
    if west >= east:
        raise ValueError(f"west ({west}) must be < east ({east})")
    return south, west, north, east


# ---------------------------------------------------------------------------
# SRTM
# ---------------------------------------------------------------------------


def _srtm_tiles(south: float, west: float, north: float, east: float) -> list[str]:
    lat_min, lat_max = int(math.floor(south)), int(math.floor(north))
    lon_min, lon_max = int(math.floor(west)), int(math.floor(east))
    tiles = []
    for lat in range(lat_min, lat_max + 1):
        for lon in range(lon_min, lon_max + 1):
            ns = "N" if lat >= 0 else "S"
            ew = "E" if lon >= 0 else "W"
            tiles.append(f"{ns}{abs(lat):02d}{ew}{abs(lon):03d}")
    return tiles


def download_srtm(
    south: float, west: float, north: float, east: float, output: Path,
) -> None:
    """Download SRTM .hgt tiles."""
    srtm_dir = output / "srtm"
    srtm_dir.mkdir(parents=True, exist_ok=True)

    tiles = _srtm_tiles(south, west, north, east)
    base_url = "https://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL1.003/2000.02.11"

    print(f"[SRTM] Need {len(tiles)} tiles: {tiles}")
    for tile in tiles:
        dest = srtm_dir / f"{tile}.hgt"
        if dest.exists():
            print(f"  {tile}.hgt — cached")
            continue

        url = f"{base_url}/{tile}.SRTMGL1.hgt.zip"
        print(f"  Downloading {tile} from USGS …")
        print(f"    URL: {url}")
        print("    NOTE: USGS requires Earthdata credentials.")
        print("    Manual download: visit https://search.earthdata.nasa.gov")
        print(f"    Place {tile}.hgt in {srtm_dir}")


# ---------------------------------------------------------------------------
# Copernicus
# ---------------------------------------------------------------------------


def download_copernicus(
    south: float, west: float, north: float, east: float, output: Path,
) -> None:
    """Download Copernicus land cover tile."""
    cop_dir = output / "copernicus"
    cop_dir.mkdir(parents=True, exist_ok=True)

    print("[Copernicus] Land cover download:")
    print("  Visit: https://lcviewer.vito.be/download")
    print(f"  Select area: S={south}, W={west}, N={north}, E={east}")
    print(f"  Place .tif file in {cop_dir}")


# ---------------------------------------------------------------------------
# OSM (Overpass API)
# ---------------------------------------------------------------------------

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"

_OVERPASS_QUERIES = {
    "roads": 'way["highway"]({s},{w},{n},{e});(._;>;);out body;',
    "buildings": 'way["building"]({s},{w},{n},{e});(._;>;);out body;',
    "railways": 'way["railway"]({s},{w},{n},{e});(._;>;);out body;',
    "waterways": 'way["waterway"]({s},{w},{n},{e});(._;>;);out body;',
}


def _overpass_to_geojson(
    query_template: str,
    south: float, west: float, north: float, east: float,
) -> dict:
    """Run an Overpass query and convert result to GeoJSON."""
    query = f"[out:json];{query_template.format(s=south, w=west, n=north, e=east)}"
    data = urllib.request.urlopen(
        urllib.request.Request(
            _OVERPASS_URL,
            data=f"data={query}".encode(),
            method="POST",
        ),
        timeout=120,
    ).read()
    result = json.loads(data)

    # Build node lookup
    nodes = {}
    for elem in result.get("elements", []):
        if elem["type"] == "node":
            nodes[elem["id"]] = (elem["lon"], elem["lat"])

    # Convert ways to GeoJSON features
    features = []
    for elem in result.get("elements", []):
        if elem["type"] != "way":
            continue
        coords = [nodes[nid] for nid in elem.get("nodes", []) if nid in nodes]
        if len(coords) < 2:
            continue

        tags = elem.get("tags", {})
        # Determine geometry type
        if coords[0] == coords[-1] and len(coords) >= 4:
            geom = {"type": "Polygon", "coordinates": [coords]}
        else:
            geom = {"type": "LineString", "coordinates": coords}

        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": tags,
        })

    return {"type": "FeatureCollection", "features": features}


def download_osm(
    south: float, west: float, north: float, east: float, output: Path,
) -> None:
    """Download OSM features via Overpass API and save as GeoJSON."""
    osm_dir = output / "osm"
    osm_dir.mkdir(parents=True, exist_ok=True)

    for layer, template in _OVERPASS_QUERIES.items():
        dest = osm_dir / f"{layer}.geojson"
        if dest.exists():
            print(f"  [OSM] {layer}.geojson — cached")
            continue

        print(f"  [OSM] Fetching {layer} …")
        try:
            geojson = _overpass_to_geojson(template, south, west, north, east)
            with open(dest, "w") as f:
                json.dump(geojson, f)
            n = len(geojson["features"])
            print(f"    → {n} features saved to {dest}")
        except Exception as e:
            print(f"    ERROR: {e}")


# ---------------------------------------------------------------------------
# GEBCO
# ---------------------------------------------------------------------------


def download_gebco(
    south: float, west: float, north: float, east: float, output: Path,
) -> None:
    """Instructions for GEBCO bathymetry download."""
    gebco_dir = output / "gebco"
    gebco_dir.mkdir(parents=True, exist_ok=True)

    print("[GEBCO] Bathymetry download:")
    print("  Visit: https://download.gebco.net/")
    print(f"  Select area: S={south}, W={west}, N={north}, E={east}")
    print("  Format: NetCDF")
    print(f"  Place .nc file in {gebco_dir}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download real-world terrain data for simulation scenarios",
    )
    parser.add_argument(
        "--bbox", required=True,
        help="Bounding box as south,west,north,east (decimal degrees)",
    )
    parser.add_argument(
        "--output", default="data/terrain_raw",
        help="Output directory (default: data/terrain_raw)",
    )
    parser.add_argument(
        "--sources", default="srtm,osm",
        help="Comma-separated sources: srtm,copernicus,osm,gebco (default: srtm,osm)",
    )
    args = parser.parse_args()

    south, west, north, east = _parse_bbox(args.bbox)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    sources = {s.strip() for s in args.sources.split(",")}

    print("Terrain data download")
    print(f"  BBox: S={south}, W={west}, N={north}, E={east}")
    print(f"  Output: {output}")
    print(f"  Sources: {sources}")
    print()

    if "srtm" in sources:
        download_srtm(south, west, north, east, output)
    if "copernicus" in sources:
        download_copernicus(south, west, north, east, output)
    if "osm" in sources:
        download_osm(south, west, north, east, output)
    if "gebco" in sources:
        download_gebco(south, west, north, east, output)

    print("\nDone.")


if __name__ == "__main__":
    main()
