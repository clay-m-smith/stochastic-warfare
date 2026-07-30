"""Typed procedural-terrain construction shared by runtime consumers."""

from __future__ import annotations

from typing import Any, Protocol

import numpy as np

from stochastic_warfare.terrain.heightmap import Heightmap, HeightmapConfig


class ProceduralTerrainSpec(Protocol):
    """Read-only terrain inputs required by the procedural builders."""

    @property
    def width_m(self) -> float: ...

    @property
    def height_m(self) -> float: ...

    @property
    def cell_size_m(self) -> float: ...

    @property
    def base_elevation_m(self) -> float: ...

    @property
    def terrain_type(self) -> str: ...

    @property
    def features(self) -> list[dict[str, Any]]: ...


def build_flat_desert(spec: ProceduralTerrainSpec) -> Heightmap:
    """Construct a flat desert heightmap."""
    rows = max(1, int(spec.height_m / spec.cell_size_m))
    cols = max(1, int(spec.width_m / spec.cell_size_m))
    data = np.full(
        (rows, cols),
        spec.base_elevation_m,
        dtype=np.float64,
    )
    config = HeightmapConfig(
        origin_easting=0.0,
        origin_northing=0.0,
        cell_size=spec.cell_size_m,
    )
    return Heightmap(data, config)


def build_open_ocean(spec: ProceduralTerrainSpec) -> Heightmap:
    """Construct a flat ocean heightmap with zero elevation."""
    rows = max(1, int(spec.height_m / spec.cell_size_m))
    cols = max(1, int(spec.width_m / spec.cell_size_m))
    data = np.zeros((rows, cols), dtype=np.float64)
    config = HeightmapConfig(
        origin_easting=0.0,
        origin_northing=0.0,
        cell_size=spec.cell_size_m,
    )
    return Heightmap(data, config)


def build_hilly_defense(
    spec: ProceduralTerrainSpec,
    rng: np.random.Generator,
) -> Heightmap:
    """Construct hilly terrain with ridge and berm features."""
    rows = max(1, int(spec.height_m / spec.cell_size_m))
    cols = max(1, int(spec.width_m / spec.cell_size_m))
    data = np.full(
        (rows, cols),
        spec.base_elevation_m,
        dtype=np.float64,
    )

    x_coords = np.arange(cols) * spec.cell_size_m
    y_coords = np.arange(rows) * spec.cell_size_m
    xx, yy = np.meshgrid(x_coords, y_coords)
    data += 30.0 * np.sin(xx / 800.0) * np.cos(yy / 600.0)
    data += rng.normal(0.0, 2.0, size=(rows, cols))

    for feature in spec.features:
        feature_type = feature.get("type", "")
        position = feature.get("position", [0, 0])
        parameters = feature.get("params", {})

        if feature_type == "ridge":
            ridge_height = parameters.get("height_m", 100.0)
            ridge_width = parameters.get("width_m", 200.0)
            ridge_col = int(position[0] / spec.cell_size_m)
            col_indices = np.arange(cols)
            distance = np.abs(col_indices - ridge_col) * spec.cell_size_m
            mask = distance < ridge_width
            ridge_profile = np.where(
                mask,
                ridge_height * (1.0 - distance / ridge_width),
                0.0,
            )
            data += ridge_profile[np.newaxis, :]
        elif feature_type == "berm":
            berm_height = parameters.get("height_m", 3.0)
            berm_radius = parameters.get("radius_m", 50.0)
            berm_row = int(position[1] / spec.cell_size_m)
            berm_col = int(position[0] / spec.cell_size_m)
            row_low = max(0, berm_row - 5)
            row_high = min(rows, berm_row + 5)
            col_low = max(0, berm_col - 5)
            col_high = min(cols, berm_col + 5)
            if row_high > row_low and col_high > col_low:
                row_indices = np.arange(row_low, row_high)
                col_indices = np.arange(col_low, col_high)
                rr, cc = np.meshgrid(
                    row_indices,
                    col_indices,
                    indexing="ij",
                )
                distance = np.sqrt(
                    ((rr - berm_row) * spec.cell_size_m) ** 2 + ((cc - berm_col) * spec.cell_size_m) ** 2,
                )
                berm_mask = distance < berm_radius
                data[row_low:row_high, col_low:col_high] += np.where(
                    berm_mask,
                    berm_height * (1.0 - distance / berm_radius),
                    0.0,
                )

    config = HeightmapConfig(
        origin_easting=0.0,
        origin_northing=0.0,
        cell_size=spec.cell_size_m,
    )
    return Heightmap(data, config)


def build_terrain(
    spec: ProceduralTerrainSpec,
    rng: np.random.Generator | None = None,
) -> Heightmap:
    """Construct the procedural heightmap selected by ``spec``."""
    if spec.terrain_type == "flat_desert":
        return build_flat_desert(spec)
    if spec.terrain_type == "open_ocean":
        return build_open_ocean(spec)
    if spec.terrain_type == "hilly_defense":
        if rng is None:
            raise ValueError(
                "hilly_defense terrain requires an injected RNG stream",
            )
        return build_hilly_defense(spec, rng)
    if spec.terrain_type in {"trench_warfare", "open_field"}:
        return build_flat_desert(spec)
    raise ValueError(f"Unknown terrain type: {spec.terrain_type!r}")
