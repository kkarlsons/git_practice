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

Put your Google Maps key in `frontend/config.js` and set `backendUrl` to
`http://localhost:8000` while developing locally.

## Deploying to your own server

Prerequisites on the server: Docker + Docker Compose, a domain pointed at the
server (A/AAAA record), and ports **80** and **443** open.

### 1. Clone and fetch data

```bash
git clone <this-repo> riga-heatmap && cd riga-heatmap
./scripts/fetch_data.sh    # pulls Latvia OSM (~90 MB) + Riga GTFS into ./data/
```

### 2. Configure

Edit `Caddyfile` — replace `riga.example.com` with your domain.

Edit `frontend/config.js` — paste your Google Maps JS API key. Leave
`backendUrl: "/api"` as-is (same-origin through Caddy).

Optionally create `.env` next to `docker-compose.yml`:

```
ALLOWED_ORIGINS=https://riga.example.com
RIGA_GRID_M=50
RIGA_MAX_TRIP_MIN=90
```

### 3. Lock down the Google Maps key

In the Google Cloud Console, restrict the key by **HTTP referrer** to
`https://riga.example.com/*`. The key is served in the static frontend and
is visible to anyone who loads the page — referrer restrictions are what
prevent abuse.

### 4. Bring it up

```bash
docker compose up -d --build
docker compose logs -f         # watch until r5py finishes building its network
```

First request takes ~60 s: r5py parses the OSM PBF + GTFS into an in-memory
network and caches it as `*.mapdb` files inside the backend container.

Caddy will fetch a Let's Encrypt certificate automatically on first start
(DNS must resolve to the server already).

### 5. Visit

Open `https://riga.example.com/` on any device, including your phone — the
frontend is touch-friendly via the viewport meta tag, and the heatmap renders
client-side.

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
