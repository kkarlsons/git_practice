"""Riga geometry: bounding box and grid generation."""
from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
from shapely.geometry import Point, box

# Riga city bbox (approximate, covers administrative area with a small margin).
# lat_min, lon_min, lat_max, lon_max
RIGA_BBOX = (56.86, 23.93, 57.09, 24.35)

# Metric CRS suitable for Latvia (LKS-92 / TM Baltic93).
METRIC_CRS = "EPSG:3059"
WGS84 = "EPSG:4326"


@dataclass(frozen=True)
class Grid:
    """A regular metric grid expressed in WGS84 cell centers.

    `times[i]` corresponds to `points.iloc[i]` and to cell
    (row = i // ncols, col = i % ncols) in a grid of origin
    (x_min, y_min) with `grid_m` spacing.
    """

    points: gpd.GeoDataFrame  # cell centers in WGS84
    grid_m: int
    nrows: int
    ncols: int
    x_min: float  # metric CRS origin
    y_min: float
    bbox_wgs84: tuple[float, float, float, float]  # lat_min, lon_min, lat_max, lon_max


def build_grid(grid_m: int = 100, bbox: tuple[float, float, float, float] = RIGA_BBOX) -> Grid:
    """Cover `bbox` with a regular `grid_m`-spaced grid in a metric CRS."""
    lat_min, lon_min, lat_max, lon_max = bbox
    aoi = gpd.GeoDataFrame(
        geometry=[box(lon_min, lat_min, lon_max, lat_max)], crs=WGS84
    ).to_crs(METRIC_CRS)

    x_min, y_min, x_max, y_max = aoi.total_bounds
    # Snap extent to whole cells so rows/cols are deterministic.
    x_min = np.floor(x_min / grid_m) * grid_m
    y_min = np.floor(y_min / grid_m) * grid_m
    x_max = np.ceil(x_max / grid_m) * grid_m
    y_max = np.ceil(y_max / grid_m) * grid_m

    xs = np.arange(x_min + grid_m / 2, x_max, grid_m)
    ys = np.arange(y_min + grid_m / 2, y_max, grid_m)
    ncols, nrows = len(xs), len(ys)

    # Row-major: row 0 is the southernmost row. The frontend will flip for display.
    xx, yy = np.meshgrid(xs, ys)
    pts = gpd.GeoSeries(
        gpd.points_from_xy(xx.ravel(), yy.ravel()), crs=METRIC_CRS
    ).to_crs(WGS84)

    gdf = gpd.GeoDataFrame({"id": np.arange(len(pts))}, geometry=pts, crs=WGS84)

    # Actual WGS84 extent of cell centers (the metric grid is reprojected, so
    # this drifts slightly from the input bbox). The frontend pads by half a
    # cell when rendering.
    lons = gdf.geometry.x.to_numpy()
    lats = gdf.geometry.y.to_numpy()
    cell_bbox = (float(lats.min()), float(lons.min()), float(lats.max()), float(lons.max()))

    return Grid(
        points=gdf,
        grid_m=grid_m,
        nrows=nrows,
        ncols=ncols,
        x_min=float(x_min),
        y_min=float(y_min),
        bbox_wgs84=cell_bbox,
    )


def origin_frame(lat: float, lon: float) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({"id": [0]}, geometry=[Point(lon, lat)], crs=WGS84)
