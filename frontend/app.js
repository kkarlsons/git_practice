// Click-to-compute transit heatmap for Riga, rendered on MapLibre GL.

const RIGA_CENTER = [24.1052, 56.9496]; // [lng, lat]

const map = new maplibregl.Map({
  container: "map",
  style: {
    version: 8,
    sources: {
      osm: {
        type: "raster",
        tiles: [
          "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
          "https://b.tile.openstreetmap.org/{z}/{x}/{y}.png",
          "https://c.tile.openstreetmap.org/{z}/{x}/{y}.png",
        ],
        tileSize: 256,
        attribution: "&copy; <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a> contributors",
      },
    },
    layers: [{ id: "osm", type: "raster", source: "osm" }],
  },
  center: RIGA_CENTER,
  zoom: 11,
});

map.addControl(new maplibregl.NavigationControl(), "top-right");

let marker = null;

map.on("click", (e) => {
  const { lng, lat } = e.lngLat;
  if (marker) {
    marker.setLngLat([lng, lat]);
  } else {
    marker = new maplibregl.Marker({ color: "#111" }).setLngLat([lng, lat]).addTo(map);
  }
  computeAndRender(lat, lng);
});

function setStatus(text, kind = "idle") {
  const el = document.getElementById("status");
  el.textContent = text;
  el.className = `status ${kind}`;
}

function computeDeparture() {
  const wantedDow = Number(document.getElementById("dow").value);
  const [hh, mm] = document.getElementById("time").value.split(":").map(Number);
  const now = new Date();
  // Pick the nearest date (± a few days) whose weekday matches — keeps the
  // chosen date inside the GTFS feed's validity window.
  let diff = (wantedDow - now.getDay() + 7) % 7;
  if (diff > 3) diff -= 7;
  const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + diff, hh, mm, 0, 0);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:00`;
}

function selectedModes() {
  const modes = Array.from(document.querySelectorAll(".mode:checked")).map((el) => el.value);
  modes.push("WALK"); // walking is always allowed (access/egress to transit)
  return modes;
}

async function computeAndRender(lat, lng) {
  const gridM = Number(document.getElementById("grid-m").value);
  const maxMin = Number(document.getElementById("max-min").value);
  const view = document.getElementById("view").value;
  const modes = selectedModes();
  const departure = computeDeparture();

  const loadMsg = view === "rides"
    ? `Computing number of rides (${gridM} m grid, ~15 s)…`
    : `Computing travel times (${gridM} m grid)…`;
  setStatus(loadMsg, "loading");
  const t0 = performance.now();

  let data;
  try {
    const res = await fetch(`${window.APP_CONFIG.backendUrl}/travel_times`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        lat, lon: lng, grid_m: gridM, max_minutes: maxMin,
        departure, modes, view,
      }),
    });
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
    data = await res.json();
  } catch (err) {
    setStatus(`Error: ${err.message}`, "error");
    return;
  }

  const elapsed = ((performance.now() - t0) / 1000).toFixed(1);
  const pct = ((data.stats.reached / data.stats.cells) * 100).toFixed(0);
  const medianLabel = view === "rides"
    ? `median ${data.stats.median} ride(s)`
    : `median ${Math.round(data.stats.median / 60)} min`;
  setStatus(
    `Reached ${pct}% of ${data.stats.cells} cells • ${medianLabel} • ${elapsed}s`,
    "ok",
  );

  updateLegend(view, maxMin);
  renderHeatmap(data, view === "rides" ? MAX_RIDES_DISPLAY : maxMin * 60);
}

const MAX_RIDES_DISPLAY = 4; // colors saturate at 4+ rides

function updateLegend(view, maxMin) {
  const minEl = document.getElementById("legend-min");
  const maxEl = document.getElementById("legend-max");
  if (view === "rides") {
    minEl.textContent = "0";
    maxEl.textContent = `${MAX_RIDES_DISPLAY}+`;
  } else {
    minEl.textContent = "0";
    maxEl.textContent = `${maxMin} min`;
  }
}

function renderHeatmap(data, maxValue) {
  const canvas = document.createElement("canvas");
  canvas.width = data.ncols;
  canvas.height = data.nrows;
  const ctx = canvas.getContext("2d");
  const img = ctx.createImageData(data.ncols, data.nrows);
  const values = data.values;

  for (let r = 0; r < data.nrows; r++) {
    const srcRow = data.nrows - 1 - r;
    for (let c = 0; c < data.ncols; c++) {
      const v = values[srcRow * data.ncols + c];
      const o = (r * data.ncols + c) * 4;
      if (v < 0) {
        img.data[o + 3] = 0;
        continue;
      }
      const [R, G, B] = rampColor(Math.min(v / maxValue, 1));
      img.data[o] = R;
      img.data[o + 1] = G;
      img.data[o + 2] = B;
      img.data[o + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  const url = canvas.toDataURL();

  const [latMin, lonMin, latMax, lonMax] = data.bbox;
  const halfLat = (latMax - latMin) / (2 * (data.nrows - 1 || 1));
  const halfLon = (lonMax - lonMin) / (2 * (data.ncols - 1 || 1));
  const coords = [
    [lonMin - halfLon, latMax + halfLat], // top-left
    [lonMax + halfLon, latMax + halfLat], // top-right
    [lonMax + halfLon, latMin - halfLat], // bottom-right
    [lonMin - halfLon, latMin - halfLat], // bottom-left
  ];

  if (map.getSource("heatmap")) {
    map.getSource("heatmap").updateImage({ url, coordinates: coords });
  } else {
    map.addSource("heatmap", { type: "image", url, coordinates: coords });
    map.addLayer({
      id: "heatmap",
      type: "raster",
      source: "heatmap",
      paint: { "raster-opacity": 0.65, "raster-resampling": "nearest" },
    });
  }
}

/* Color ramp: blue → green → yellow → orange → red. */
const RAMP = [
  [0.0, [13, 71, 161]],
  [0.25, [26, 152, 80]],
  [0.5, [255, 224, 71]],
  [0.75, [253, 141, 60]],
  [1.0, [189, 0, 38]],
];
function rampColor(t) {
  t = Math.max(0, Math.min(1, t));
  for (let i = 1; i < RAMP.length; i++) {
    const [t1, c1] = RAMP[i];
    if (t <= t1) {
      const [t0, c0] = RAMP[i - 1];
      const k = (t - t0) / (t1 - t0);
      return c0.map((v, j) => Math.round(v + (c1[j] - v) * k));
    }
  }
  return RAMP[RAMP.length - 1][1];
}
