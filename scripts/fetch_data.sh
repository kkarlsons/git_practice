#!/usr/bin/env bash
# Download the inputs r5py needs: Latvia OSM extract + Riga GTFS feed.
set -euo pipefail

DATA_DIR="$(cd "$(dirname "$0")/.." && pwd)/data"
mkdir -p "$DATA_DIR"

OSM_URL="https://download.geofabrik.de/europe/latvia-latest.osm.pbf"
GTFS_URL="https://saraksti.rigassatiksme.lv/riga/gtfs.zip"

OSM_PATH="$DATA_DIR/latvia-latest.osm.pbf"
GTFS_PATH="$DATA_DIR/riga-gtfs.zip"

if [[ ! -f "$OSM_PATH" ]]; then
  echo "Downloading Latvia OSM extract (~90 MB)..."
  curl -fL --progress-bar -o "$OSM_PATH.tmp" "$OSM_URL"
  mv "$OSM_PATH.tmp" "$OSM_PATH"
else
  echo "OSM extract already present: $OSM_PATH"
fi

echo "Downloading Riga GTFS..."
curl -fL --progress-bar -o "$GTFS_PATH.tmp" "$GTFS_URL"
mv "$GTFS_PATH.tmp" "$GTFS_PATH"

echo "Done. Files in $DATA_DIR:"
ls -lh "$DATA_DIR"
