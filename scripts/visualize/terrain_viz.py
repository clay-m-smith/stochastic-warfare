"""Terrain visualization: elevation heatmap, classification overlay, LOS viewshed.

Run: python scripts/visualize/terrain_viz.py
Requires matplotlib (dev dependency).
"""

from __future__ import annotations

import numpy as np

from stochastic_warfare.core.types import Position
from stochastic_warfare.terrain.classification import (
    ClassificationConfig,
    LandCover,
    SoilType,
    TerrainClassification,
)
from stochastic_warfare.terrain.heightmap import Heightmap, HeightmapConfig
from stochastic_warfare.terrain.infrastructure import (
    Building,
    InfrastructureManager,
    Road,
    RoadType,
)
from stochastic_warfare.terrain.los import LOSEngine


def main() -> None:
    import matplotlib.pyplot as plt

    config = HeightmapConfig(cell_size=50.0)

    # Generate synthetic terrain: two hills
    rows, cols = 60, 60
    y, x = np.mgrid[0:rows, 0:cols]
    hill1 = 200 * np.exp(-((x - 20) ** 2 + (y - 20) ** 2) / 80)
    hill2 = 150 * np.exp(-((x - 40) ** 2 + (y - 40) ** 2) / 60)
    elevation = hill1 + hill2 + 10
    hm = Heightmap(elevation.astype(np.float64), config)

    # Classification
    lc = np.full((rows, cols), LandCover.GRASSLAND, dtype=np.int32)
    lc[elevation > 100] = LandCover.FOREST_DECIDUOUS
    lc[elevation > 180] = LandCover.DESERT_ROCK
    soil = np.full((rows, cols), SoilType.LOAM, dtype=np.int32)
    cls_config = ClassificationConfig(cell_size=50.0)
    classification = TerrainClassification(lc, soil, cls_config)

    # Infrastructure
    roads = [Road(road_id="r1", road_type=RoadType.PAVED,
                  points=[(0, 1500), (3000, 1500)])]
    buildings = [Building(building_id="b1",
                          footprint=[(1400, 1400), (1600, 1400), (1600, 1600), (1400, 1600)],
                          height=20)]
    infra = InfrastructureManager(roads=roads, buildings=buildings)

    # LOS viewshed
    los = LOSEngine(hm, infra)
    observer = Position(1025.0, 1025.0)
    viewshed = los.visible_area(observer, max_range=1500.0, observer_height=2.0)

    # Plot
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    # Elevation
    ax = axes[0]
    im = ax.imshow(elevation, origin="lower", cmap="terrain",
                   extent=[0, cols * 50, 0, rows * 50])
    ax.contour(elevation, levels=10, origin="lower",
               extent=[0, cols * 50, 0, rows * 50], colors="black", linewidths=0.5)
    ax.set_title("Elevation (m)")
    ax.set_xlabel("Easting (m)")
    ax.set_ylabel("Northing (m)")
    plt.colorbar(im, ax=ax, label="m ASL")

    # Classification
    ax = axes[1]
    im = ax.imshow(lc, origin="lower", cmap="Set3",
                   extent=[0, cols * 50, 0, rows * 50])
    ax.set_title("Land Cover Classification")
    plt.colorbar(im, ax=ax)

    # Viewshed
    ax = axes[2]
    ax.imshow(elevation, origin="lower", cmap="terrain", alpha=0.5,
              extent=[0, cols * 50, 0, rows * 50])
    ax.imshow(viewshed.astype(float), origin="lower", cmap="RdYlGn", alpha=0.5,
              extent=[0, cols * 50, 0, rows * 50])
    ax.plot(observer.easting, observer.northing, "r*", markersize=15)
    ax.set_title("LOS Viewshed")

    plt.tight_layout()
    plt.savefig("terrain_viz.png", dpi=150)
    plt.show()
    print("Saved terrain_viz.png")


if __name__ == "__main__":
    main()
