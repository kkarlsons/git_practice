"""FastAPI server: compute transit travel-time grids for Riga."""
from __future__ import annotations

import datetime as dt
import logging
import os
from functools import lru_cache
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .riga import Grid, RIGA_BBOX, build_grid, origin_frame

log = logging.getLogger("riga-heatmap")

DATA_DIR = Path(os.environ.get("RIGA_DATA_DIR", Path(__file__).parent.parent / "data"))
OSM_PATH = DATA_DIR / "latvia-latest.osm.pbf"
GTFS_PATH = DATA_DIR / "riga-gtfs.zip"
DEFAULT_GRID_M = int(os.environ.get("RIGA_GRID_M", "50"))
MAX_TRIP_MIN = int(os.environ.get("RIGA_MAX_TRIP_MIN", "90"))


_allowed_origins = [
    o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()
]

app = FastAPI(title="Riga Transit Heatmap")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins or ["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


class TravelTimeRequest(BaseModel):
    lat: float = Field(..., ge=RIGA_BBOX[0], le=RIGA_BBOX[2])
    lon: float = Field(..., ge=RIGA_BBOX[1], le=RIGA_BBOX[3])
    grid_m: int = Field(DEFAULT_GRID_M, ge=20, le=1000)
    departure: dt.datetime | None = None
    max_minutes: int = Field(MAX_TRIP_MIN, ge=5, le=240)


class TravelTimeResponse(BaseModel):
    grid_m: int
    nrows: int
    ncols: int
    bbox: tuple[float, float, float, float]  # lat_min, lon_min, lat_max, lon_max
    # Row-major, length nrows*ncols. Seconds, or -1 if unreachable within max_minutes.
    times: list[int]
    stats: dict


@lru_cache(maxsize=4)
def _cached_grid(grid_m: int) -> Grid:
    log.info("Building %dm grid over Riga", grid_m)
    return build_grid(grid_m=grid_m)


@lru_cache(maxsize=1)
def _transport_network():
    import r5py  # heavy import, defer until first request

    if not OSM_PATH.exists() or not GTFS_PATH.exists():
        raise RuntimeError(
            f"Missing data. Expected {OSM_PATH} and {GTFS_PATH}. "
            "Run scripts/fetch_data.sh."
        )
    log.info("Loading transport network (OSM + GTFS). First call may take a minute.")
    return r5py.TransportNetwork(str(OSM_PATH), [str(GTFS_PATH)])


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "osm": OSM_PATH.exists(),
        "gtfs": GTFS_PATH.exists(),
    }


@app.post("/travel_times", response_model=TravelTimeResponse)
def travel_times(req: TravelTimeRequest) -> TravelTimeResponse:
    import r5py

    try:
        net = _transport_network()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    grid = _cached_grid(req.grid_m)
    origins = origin_frame(req.lat, req.lon)
    departure = req.departure or _next_weekday_morning()

    computer = r5py.TravelTimeMatrixComputer(
        net,
        origins=origins,
        destinations=grid.points,
        departure=departure,
        departure_time_window=dt.timedelta(minutes=30),
        max_time=dt.timedelta(minutes=req.max_minutes),
        transport_modes=[r5py.TransportMode.TRANSIT, r5py.TransportMode.WALK],
    )
    df = computer.compute_travel_times()

    # r5py returns a long-form DataFrame (from_id, to_id, travel_time minutes).
    times = np.full(len(grid.points), -1, dtype=np.int32)
    reachable = df.dropna(subset=["travel_time"])
    idx = reachable["to_id"].to_numpy(dtype=np.int64)
    secs = (reachable["travel_time"].to_numpy() * 60).astype(np.int32)
    times[idx] = secs

    reached = int((times >= 0).sum())
    return TravelTimeResponse(
        grid_m=grid.grid_m,
        nrows=grid.nrows,
        ncols=grid.ncols,
        bbox=grid.bbox_wgs84,
        times=times.tolist(),
        stats={
            "cells": len(times),
            "reached": reached,
            "median_seconds": int(np.median(times[times >= 0])) if reached else 0,
            "departure": departure.isoformat(),
        },
    )


def _next_weekday_morning(hour: int = 8) -> dt.datetime:
    """Pick a near-future weekday at 08:00 local — GTFS often lacks far-out dates."""
    now = dt.datetime.now().replace(hour=hour, minute=0, second=0, microsecond=0)
    if now <= dt.datetime.now():
        now += dt.timedelta(days=1)
    while now.weekday() >= 5:
        now += dt.timedelta(days=1)
    return now
