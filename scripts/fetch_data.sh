#!/usr/bin/env bash
# Download the inputs r5py needs: Latvia OSM extract + Riga GTFS feed.
set -euo pipefail

DATA_DIR="$(cd "$(dirname "$0")/.." && pwd)/data"
mkdir -p "$DATA_DIR"

OSM_URL="https://download.geofabrik.de/europe/latvia-latest.osm.pbf"
RIGA_GTFS_URL="https://saraksti.rigassatiksme.lv/riga/gtfs.zip"
# Vivi (Pasažieru vilciens) — Latvian commuter trains.
PV_GTFS_URL="https://www.vivi.lv/uploads/Jaunumi/GTFS.zip"

OSM_PATH="$DATA_DIR/latvia-latest.osm.pbf"
RIGA_GTFS_PATH="$DATA_DIR/riga-gtfs.zip"
PV_GTFS_PATH="$DATA_DIR/pv-gtfs.zip"

if [[ ! -f "$OSM_PATH" ]]; then
  echo "Downloading Latvia OSM extract (~90 MB)..."
  curl -fL --progress-bar -o "$OSM_PATH.tmp" "$OSM_URL"
  mv "$OSM_PATH.tmp" "$OSM_PATH"
else
  echo "OSM extract already present: $OSM_PATH"
fi

echo "Downloading Riga Satiksme GTFS..."
curl -fL --progress-bar -o "$RIGA_GTFS_PATH.tmp" "$RIGA_GTFS_URL"
mv "$RIGA_GTFS_PATH.tmp" "$RIGA_GTFS_PATH"

echo "Downloading Vivi (trains) GTFS..."
if curl -fL --progress-bar -o "$PV_GTFS_PATH.tmp" "$PV_GTFS_URL"; then
  mv "$PV_GTFS_PATH.tmp" "$PV_GTFS_PATH"
else
  rm -f "$PV_GTFS_PATH.tmp"
  echo "WARNING: Vivi GTFS download failed. The app will still work without trains."
fi

echo "Done. Files in $DATA_DIR:"
ls -lh "$DATA_DIR"
