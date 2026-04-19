# Riga Transit Heatmap

Web app: drop a point anywhere on a map of Riga, get back a heatmap of how long
it takes to reach every other point by public transit + walking.

- **Basemap:** MapLibre GL JS + OpenStreetMap raster tiles. No account or
  API key required.
- **Routing:** [r5py](https://r5py.readthedocs.io/) (RAPTOR algorithm) over
  Riga's published GTFS feed and OpenStreetMap data. Travel-time computation
  runs locally, so a click costs nothing.
- **Grid:** configurable. Default 50 m (~120k cells over Riga). 20 m is
  possible (~720k cells) but each request takes minutes.

## Layout

```
backend/        FastAPI + r5py
frontend/       Static HTML/JS (Google Maps + Canvas heatmap overlay)
data/           GTFS + OSM inputs (downloaded, gitignored)
scripts/        Setup helpers
Dockerfile      Backend image (Java 21 + Python 3.12)
docker-compose.yml  Backend + Caddy reverse proxy
Caddyfile       TLS + static frontend + /api proxy
```

## Local development

Requirements: Python 3.10+, Java 21+, ~2 GB disk.

```bash
./scripts/fetch_data.sh
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app:app --reload                       # backend on :8000
python -m http.server --directory frontend 8080        # frontend on :8080
```

Set `backendUrl` in `frontend/config.js` to `http://localhost:8000` while
developing locally.

## Deploying to your own server

Prerequisites on the server: Docker + Docker Compose, and port **2000** open
(or whatever you change it to in `Caddyfile` + `docker-compose.yml`).

### 1. Clone and fetch data

```bash
git clone <this-repo> riga-heatmap && cd riga-heatmap
./scripts/fetch_data.sh    # pulls Latvia OSM (~90 MB) + Riga GTFS into ./data/
```

### 2. Configure (optional)

Defaults work out of the box on `:2000`. To change behaviour, create `.env`
next to `docker-compose.yml`:

```
RIGA_GRID_M=50
RIGA_MAX_TRIP_MIN=90
```

To move to HTTPS + a domain later, replace the `:2000 { ... }` block in
`Caddyfile` with `yourdomain.com { ... }` and remap ports 80/443 in
`docker-compose.yml`. Caddy will fetch a Let's Encrypt certificate on first
start.

### 3. Bring it up

```bash
docker compose up -d --build
docker compose logs -f         # watch until r5py finishes building its network
```

First request takes ~60 s: r5py parses the OSM PBF + GTFS into an in-memory
network and caches it.

### 4. Visit

Open `http://<your-server>:2000/` on any device. The frontend is touch-friendly
(viewport meta tag) and the heatmap renders client-side.

### Resource sizing

- **RAM:** 3–4 GB is comfortable for the backend. `JAVA_OPTS=-Xmx4g` is the
  default in compose. Bump if you use a 20 m grid.
- **Disk:** ~500 MB for OSM + GTFS + r5 cache.
- **CPU:** a single click is one r5py call on one core. 50 m grid ≈ a few
  seconds; 20 m grid ≈ a minute or more.

### Updating

```bash
git pull
docker compose up -d --build
```

GTFS feeds change often. Re-run `./scripts/fetch_data.sh` on a schedule (a
weekly cron job works) and `docker compose restart backend` so the new feed is
picked up.

## API

`POST /api/travel_times`
```json
{ "lat": 56.9496, "lon": 24.1052, "grid_m": 50, "max_minutes": 60 }
```

Response: grid metadata + row-major array of travel times in seconds
(`-1` for unreachable cells within `max_minutes`).
