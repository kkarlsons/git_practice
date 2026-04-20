#!/usr/bin/env python3
"""Sweep a coarse grid of origins across Riga, score each by how bad transit
is from that point, write CSV + GeoJSON for the viewer page.

Metrics computed per origin:
  reach_peak       cells reachable in <= max_minutes, Mon 08:00, all modes.
                   Lower = worse (fewer places you can get to).
  reach_direct     same, but capped at max_rides=1 (direct service only).
  transfer_burden  reach_peak - reach_direct. Higher = more of your reachable
                   area is only accessible via a transfer.
  reach_night      [optional] same as reach_peak but Sat 22:00.
  offpeak_cliff    reach_peak - reach_night. Higher = night-abandoned area.

Usage (on the server):
  python3 scripts/mobility_scan.py                # 1 km grid, peak+direct
  python3 scripts/mobility_scan.py --include-offpeak
  python3 scripts/mobility_scan.py --spacing-m 500
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

# Must match backend/riga.py RIGA_BBOX: (lat_min, lon_min, lat_max, lon_max).
RIGA_BBOX = (56.86, 23.93, 57.09, 24.35)
# Meters-to-degrees at Riga's latitude (~57° N).
DEG_PER_M_LAT = 1 / 111_320
DEG_PER_M_LON = 1 / (111_320 * 0.545)

MODES = ["BUS", "TRAM", "RAIL", "TROLLEYBUS", "WALK"]


def origin_grid(spacing_m: int):
    lat_min, lon_min, lat_max, lon_max = RIGA_BBOX
    step_lat = spacing_m * DEG_PER_M_LAT
    step_lon = spacing_m * DEG_PER_M_LON
    # Buffer slightly inside the bbox — backend 422s on the edges.
    margin = 0.002
    lat = lat_min + step_lat / 2
    while lat < lat_max - margin:
        if lat > lat_min + margin:
            lon = lon_min + step_lon / 2
            while lon < lon_max - margin:
                if lon > lon_min + margin:
                    yield lat, lon
                lon += step_lon
        lat += step_lat


def post(base_url: str, body: dict, timeout: int = 180) -> dict:
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/travel_times",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def count_reached(data: dict) -> int:
    return sum(1 for v in data["values"] if v >= 0)


def next_weekday_at(dow: int, hour: int, minute: int = 0) -> dt.datetime:
    now = dt.datetime.now()
    diff = (dow - now.weekday() + 7) % 7 or 7
    return (now + dt.timedelta(days=diff)).replace(hour=hour, minute=minute, second=0, microsecond=0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", default="http://localhost:2000/api")
    ap.add_argument("--spacing-m", type=int, default=1000, help="origin grid spacing in meters")
    ap.add_argument("--max-minutes", type=int, default=45)
    ap.add_argument("--grid-m", type=int, default=100, help="destination grid resolution")
    ap.add_argument("--include-offpeak", action="store_true")
    ap.add_argument("--output-dir", default=str(Path(__file__).resolve().parent.parent / "frontend"))
    args = ap.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    mon08 = next_weekday_at(0, 8)   # Monday
    sat22 = next_weekday_at(5, 22)  # Saturday
    base_body = {
        "grid_m": args.grid_m,
        "max_minutes": args.max_minutes,
        "modes": MODES,
        "view": "time",
        "departure": mon08.isoformat(),
    }

    origins = list(origin_grid(args.spacing_m))
    calls_per = 3 if args.include_offpeak else 2
    print(f"Scanning {len(origins)} origins × {calls_per} calls "
          f"= {len(origins) * calls_per} API calls total.")
    print(f"Peak: {mon08.isoformat()}   Night: {sat22.isoformat() if args.include_offpeak else '—'}\n")

    rows: list[dict] = []
    for i, (lat, lon) in enumerate(origins, 1):
        t0 = time.monotonic()
        body = {**base_body, "lat": lat, "lon": lon}
        try:
            peak = post(args.base_url, body)
            direct = post(args.base_url, {**body, "max_rides": 1})
            reach_peak = count_reached(peak)
            reach_direct = count_reached(direct)
            reach_night = None
            offpeak_cliff = None
            if args.include_offpeak:
                night = post(args.base_url, {**body, "departure": sat22.isoformat()})
                reach_night = count_reached(night)
                offpeak_cliff = reach_peak - reach_night
        except urllib.error.HTTPError as e:
            msg = e.read()[:200].decode("utf-8", "replace")
            print(f"[{i}/{len(origins)}] ({lat:.4f},{lon:.4f}) SKIP http {e.code}: {msg}")
            continue
        except Exception as e:
            print(f"[{i}/{len(origins)}] ({lat:.4f},{lon:.4f}) SKIP {type(e).__name__}: {e}")
            continue

        elapsed = time.monotonic() - t0
        row = {
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "reach_peak": reach_peak,
            "reach_direct": reach_direct,
            "transfer_burden": reach_peak - reach_direct,
            "reach_night": reach_night,
            "offpeak_cliff": offpeak_cliff,
        }
        rows.append(row)
        extra = f" night={reach_night} cliff={offpeak_cliff}" if args.include_offpeak else ""
        print(f"[{i}/{len(origins)}] ({lat:.4f},{lon:.4f}) "
              f"peak={reach_peak} direct={reach_direct} "
              f"burden={row['transfer_burden']}{extra} [{elapsed:.1f}s]")

    if not rows:
        print("No successful scans. Check backend and base-url.")
        return

    csv_path = out_dir / "mobility_scan.csv"
    with csv_path.open("w", newline="") as f:
        fields = ["lat", "lon", "reach_peak", "reach_direct", "transfer_burden",
                  "reach_night", "offpeak_cliff"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    features = []
    for r in rows:
        props = {k: v for k, v in r.items() if k not in ("lat", "lon") and v is not None}
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
            "properties": props,
        })
    geojson_path = out_dir / "mobility_scan.geojson"
    with geojson_path.open("w") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)

    print(f"\nWrote {len(rows)} rows → {csv_path}")
    print(f"Wrote {len(features)} points → {geojson_path}")
    print(f"\nView at http://<server>:2000/mobility.html")

    def top(rows, key, reverse, n=10):
        return sorted(rows, key=lambda r: (r[key] if r[key] is not None else 0), reverse=reverse)[:n]

    print("\n=== Worst outbound reach (lowest reach_peak) ===")
    for r in top(rows, "reach_peak", reverse=False):
        print(f"  ({r['lat']:.4f},{r['lon']:.4f})  reach_peak={r['reach_peak']}")

    print("\n=== Highest transfer burden (direct service leaves area stranded) ===")
    for r in top(rows, "transfer_burden", reverse=True):
        print(f"  ({r['lat']:.4f},{r['lon']:.4f})  "
              f"burden={r['transfer_burden']}  peak={r['reach_peak']}  direct={r['reach_direct']}")

    if args.include_offpeak:
        print("\n=== Biggest off-peak cliff (night service collapse) ===")
        for r in top(rows, "offpeak_cliff", reverse=True):
            print(f"  ({r['lat']:.4f},{r['lon']:.4f})  "
                  f"cliff={r['offpeak_cliff']}  peak={r['reach_peak']}  night={r['reach_night']}")


if __name__ == "__main__":
    main()
