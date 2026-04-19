"""FastAPI server: compute transit travel-time grids for Riga."""
from __future__ import annotations

import csv
import datetime as dt
import io
import logging
import os
import threading
import zipfile
from collections import Counter
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Literal

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .riga import Grid, RIGA_BBOX, build_grid, origin_frame

log = logging.getLogger("riga-heatmap")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

DATA_DIR = Path(os.environ.get("RIGA_DATA_DIR", Path(__file__).parent.parent / "data"))
OSM_PATH = DATA_DIR / "latvia-latest.osm.pbf"
DEFAULT_GRID_M = int(os.environ.get("RIGA_GRID_M", "50"))
MAX_TRIP_MIN = int(os.environ.get("RIGA_MAX_TRIP_MIN", "90"))


def _gtfs_paths() -> list[Path]:
    return sorted(DATA_DIR.glob("*.zip"))


# GTFS extended route_type → friendly label. Legacy types map directly.
ROUTE_TYPE_LABEL = {
    "0": "tram", "1": "subway", "2": "rail", "3": "bus", "4": "ferry",
    "5": "cable_tram", "6": "aerial", "7": "funicular", "11": "trolleybus",
    "12": "monorail",
}
def _route_type_label(rt: str) -> str:
    if rt in ROUTE_TYPE_LABEL:
        return ROUTE_TYPE_LABEL[rt]
    try:
        n = int(rt)
    except ValueError:
        return f"unknown({rt})"
    if 100 <= n < 200: return "rail"
    if 200 <= n < 300: return "coach"
    if 400 <= n < 500: return "urban_rail"
    if 700 <= n < 800: return "bus"
    if 800 <= n < 900: return "trolleybus"
    if 900 <= n < 1000: return "tram"
    return f"other({n})"


_allowed_origins = [
    o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Build the transport network up front. Without this, two requests that
    # arrive while the cache is cold both call into r5py's MapDB writer at
    # once and the writer thread crashes (ArrayIndexOutOfBoundsException).
    try:
        _transport_network()
    except Exception as e:
        log.warning("Initial transport network build failed: %s", e)
    yield


app = FastAPI(title="Riga Transit Heatmap", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins or ["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


# "TRANSIT" is shorthand for every transit mode r5py knows about.
ALL_MODES = ["BUS", "TRAM", "RAIL", "TROLLEYBUS", "SUBWAY", "FERRY"]
WALK = "WALK"


class TravelTimeRequest(BaseModel):
    lat: float = Field(..., ge=RIGA_BBOX[0], le=RIGA_BBOX[2])
    lon: float = Field(..., ge=RIGA_BBOX[1], le=RIGA_BBOX[3])
    grid_m: int = Field(DEFAULT_GRID_M, ge=20, le=1000)
    departure: dt.datetime | None = None
    max_minutes: int = Field(MAX_TRIP_MIN, ge=5, le=240)
    modes: list[str] = Field(default_factory=lambda: ALL_MODES + [WALK])
    view: Literal["time", "rides"] = "time"
    # Cap on transit boardings (1 = direct only, 2 = one transfer, ...).
    # None means r5py's default (no effective cap for our purposes).
    max_rides: int | None = Field(default=None, ge=0, le=8)


class TravelTimeResponse(BaseModel):
    grid_m: int
    nrows: int
    ncols: int
    bbox: tuple[float, float, float, float]
    view: str
    # "time": seconds (or -1 unreachable). "rides": number of transit boardings
    # needed (0 = walk only, 1 = direct, N = N-1 transfers; -1 = unreachable).
    values: list[int]
    stats: dict


@lru_cache(maxsize=4)
def _cached_grid(grid_m: int) -> Grid:
    log.info("Building %dm grid over Riga", grid_m)
    return build_grid(grid_m=grid_m)


_network_lock = threading.Lock()
_network_status = {"ready": False, "started_at": None, "elapsed_s": 0.0, "error": None}


def _heartbeat(stop: threading.Event, label: str) -> None:
    import time as _time
    start = _time.monotonic()
    while not stop.wait(5):
        log.info("%s still running (%ds elapsed)…", label, int(_time.monotonic() - start))


@lru_cache(maxsize=1)
def _build_network():
    import r5py
    import time as _time

    gtfs = _gtfs_paths()
    if not OSM_PATH.exists() or not gtfs:
        raise RuntimeError(
            f"Missing data. Need {OSM_PATH} and at least one *.zip GTFS feed "
            f"under {DATA_DIR}. Run scripts/fetch_data.sh."
        )
    log.info("Loading transport network: OSM + %d GTFS feed(s): %s", len(gtfs), [p.name for p in gtfs])
    _network_status["started_at"] = _time.monotonic()
    stop = threading.Event()
    threading.Thread(target=_heartbeat, args=(stop, "Transport-network build"), daemon=True).start()
    try:
        net = r5py.TransportNetwork(str(OSM_PATH), [str(p) for p in gtfs])
    except Exception as e:
        _network_status["error"] = str(e)
        raise
    finally:
        stop.set()
        _network_status["elapsed_s"] = _time.monotonic() - (_network_status["started_at"] or _time.monotonic())
    _network_status["ready"] = True
    log.info("Transport network ready in %.1fs", _network_status["elapsed_s"])
    return net


def _transport_network():
    # Serialize concurrent first-time builds — r5py's MapDB writer is not
    # safe against two threads writing the same files at once.
    with _network_lock:
        return _build_network()


def _resolve_modes(names: list[str]) -> list:
    """Map user-supplied mode names to r5py.TransportMode values, dropping unknowns."""
    import r5py

    tm = r5py.TransportMode
    available = {n: getattr(tm, n) for n in dir(tm) if not n.startswith("_")}
    modes = []
    for n in names:
        key = n.upper()
        if key in available:
            modes.append(available[key])
        else:
            log.warning("Unknown transport mode %r (have: %s)", n, sorted(available))
    return modes


@app.get("/ready")
def ready() -> dict:
    import time as _time
    started = _network_status["started_at"]
    elapsed = _network_status["elapsed_s"] if _network_status["ready"] else (
        (_time.monotonic() - started) if started else 0.0
    )
    return {
        "ready": _network_status["ready"],
        "elapsed_s": round(elapsed, 1),
        "error": _network_status["error"],
    }


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "osm": OSM_PATH.exists(),
        "gtfs_feeds": [p.name for p in _gtfs_paths()],
    }


@app.get("/gtfs_summary")
def gtfs_summary() -> dict:
    """Per-feed route_type counts — lets the frontend confirm trains, etc."""
    result: dict = {}
    for p in _gtfs_paths():
        try:
            with zipfile.ZipFile(p) as z:
                with z.open("routes.txt") as f:
                    rows = list(csv.DictReader(io.StringIO(f.read().decode("utf-8-sig"))))
            by_label: Counter = Counter(_route_type_label(r.get("route_type", "")) for r in rows)
            result[p.name] = {"total_routes": len(rows), "by_mode": dict(by_label)}
        except Exception as e:
            result[p.name] = {"error": str(e)}
    return result


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
    modes = _resolve_modes(req.modes) or _resolve_modes([WALK])

    if req.view == "time":
        values, reached, median = _compute_time(
            r5py, net, origins, grid, departure, req.max_minutes, modes, req.max_rides
        )
    else:
        values, reached, median = _compute_rides(
            r5py, net, origins, grid, departure, req.max_minutes, modes, req.max_rides
        )

    return TravelTimeResponse(
        grid_m=grid.grid_m,
        nrows=grid.nrows,
        ncols=grid.ncols,
        bbox=grid.bbox_wgs84,
        view=req.view,
        values=values.tolist(),
        stats={
            "cells": int(values.size),
            "reached": reached,
            "median": median,
            "departure": departure.isoformat(),
            "modes": req.modes,
            "max_rides": req.max_rides,
        },
    )


def _matrix(r5py, net, origins, grid, departure, max_minutes, modes, max_rides):
    kwargs = dict(
        origins=origins,
        destinations=grid.points,
        departure=departure,
        departure_time_window=dt.timedelta(minutes=30),
        max_time=dt.timedelta(minutes=max_minutes),
        transport_modes=modes,
    )
    if max_rides is not None:
        kwargs["max_public_transport_rides"] = max_rides
    try:
        return r5py.TravelTimeMatrix(net, **kwargs)
    except TypeError:
        # r5py API rename fallback.
        if "max_public_transport_rides" in kwargs:
            kwargs["max_rides"] = kwargs.pop("max_public_transport_rides")
        return r5py.TravelTimeMatrix(net, **kwargs)


def _compute_time(r5py, net, origins, grid, departure, max_minutes, modes, max_rides):
    df = _matrix(r5py, net, origins, grid, departure, max_minutes, modes, max_rides)
    times = np.full(len(grid.points), -1, dtype=np.int32)
    reachable = df.dropna(subset=["travel_time"])
    idx = reachable["to_id"].to_numpy(dtype=np.int64)
    secs = (reachable["travel_time"].to_numpy() * 60).astype(np.int32)
    times[idx] = secs
    reached = int((times >= 0).sum())
    median = int(np.median(times[times >= 0])) if reached else 0
    return times, reached, median


def _compute_rides(r5py, net, origins, grid, departure, max_minutes, modes, max_rides):
    """For each cell: the minimum number of transit boardings needed to reach it.

    0 = walk only, 1 = direct ride, 2 = one transfer, etc. -1 = unreachable.
    Works by calling TravelTimeMatrix with progressively higher ride caps and
    keeping the smallest cap for which each cell becomes reachable.
    """
    n = len(grid.points)
    rides = np.full(n, -1, dtype=np.int32)

    upper = max_rides if max_rides is not None else int(os.environ.get("RIGA_MAX_TRANSFERS", "3")) + 1
    for r in range(upper + 1):  # 0..upper
        df = _matrix(r5py, net, origins, grid, departure, max_minutes, modes, r)
        reachable = df.dropna(subset=["travel_time"])
        idx = reachable["to_id"].to_numpy(dtype=np.int64)
        unset = rides[idx] < 0
        rides[idx[unset]] = r

    reached = int((rides >= 0).sum())
    median = int(np.median(rides[rides >= 0])) if reached else 0
    return rides, reached, median


def _next_weekday_morning(hour: int = 8) -> dt.datetime:
    now = dt.datetime.now().replace(hour=hour, minute=0, second=0, microsecond=0)
    if now <= dt.datetime.now():
        now += dt.timedelta(days=1)
    while now.weekday() >= 5:
        now += dt.timedelta(days=1)
    return now
