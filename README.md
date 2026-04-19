# Riga Transit Heatmap

Web app: drop a point anywhere on a map of Riga, get back a heatmap of how long
it takes to reach every other point by public transit + walking.

- **Basemap:** Google Maps JavaScript API.
- **Routing:** [r5py](https://r5py.readthedocs.io/) (RAPTOR algorithm) over
  Riga's published GTFS feed and OpenStreetMap data. No Google Directions API
  calls — travel-time computation runs locally, so a click costs nothing.
- **Grid:** configurable. Default 50 m (~120k cells over Riga). 20 m is
  possible (~720k cells) but each request takes minutes.

## Layout

```
backend/   FastAPI server wrapping r5py
frontend/  Static HTML/JS, Google Maps + Canvas heatmap overlay
data/      GTFS + OSM inputs (downloaded by scripts/fetch_data.sh)
scripts/   Setup helpers
```

## Setup

Requirements: Python 3.10+, Java 21+ (for r5py), ~2 GB disk for OSM + GTFS.

```bash
# 1. Fetch Riga GTFS and Latvia OSM extract
./scripts/fetch_data.sh

# 2. Install Python deps
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

# 3. Start the backend
uvicorn backend.app:app --reload

# 4. Serve the frontend (any static server works)
# Put your Google Maps API key in frontend/config.js first
python -m http.server --directory frontend 8080
```

Open http://localhost:8080 and click somewhere in Riga.

## API

`POST /travel_times`
```json
{ "lat": 56.9496, "lon": 24.1052, "grid_m": 100, "departure": "2025-06-10T08:00:00" }
```
Response: grid metadata + a flat array of travel times in seconds (`-1` for
unreachable cells).
