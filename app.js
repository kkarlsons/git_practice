// Riga center parking + walk-distance heatmap.
//
// Data source: OpenStreetMap via the Overpass API.
// Heatmap: 5 m grid, value = 1.3 * great-circle distance to nearest parking
// centroid (cheap proxy for walking distance).

const CENTER = { lat: 56.9496, lon: 24.1052 }; // Doma laukums
const HALF_LAT = 0.009;  // ~1 km N-S
const HALF_LON = 0.0165; // ~1 km E-W at this latitude
const BBOX = {
  south: CENTER.lat - HALF_LAT,
  north: CENTER.lat + HALF_LAT,
  west: CENTER.lon - HALF_LON,
  east: CENTER.lon + HALF_LON,
};

const CELL_M = 5;            // 5 x 5 m grid
const WALK_FACTOR = 1.3;     // straight-line -> walking detour
const MAX_DIST_M = 400;      // cap for colour ramp

const statusEl = document.getElementById("status");
const opacityEl = document.getElementById("opacity");
const showHeatmapEl = document.getElementById("showHeatmap");
const showParkingEl = document.getElementById("showParking");
const recomputeBtn = document.getElementById("recompute");

const map = L.map("map", { preferCanvas: true }).setView(
  [CENTER.lat, CENTER.lon],
  15
);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution:
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).addTo(map);

L.rectangle(
  [
    [BBOX.south, BBOX.west],
    [BBOX.north, BBOX.east],
  ],
  { color: "#333", weight: 1, fill: false, dashArray: "4 4" }
).addTo(map);

const parkingLayer = L.layerGroup().addTo(map);
let heatmapOverlay = null;
let parkingPoints = []; // [{lat, lon, name}]

function setStatus(msg) {
  statusEl.textContent = msg;
}

// --- Overpass ---------------------------------------------------------------

async function fetchParking() {
  // Query a slightly larger area than the heatmap bbox so that cells near the
  // edge can still find a "nearest parking" that lies just outside.
  const pad = 0.005; // ~500 m
  const s = BBOX.south - pad;
  const n = BBOX.north + pad;
  const w = BBOX.west - pad;
  const e = BBOX.east + pad;
  const query = `
    [out:json][timeout:25];
    (
      node["amenity"="parking"](${s},${w},${n},${e});
      way["amenity"="parking"](${s},${w},${n},${e});
      relation["amenity"="parking"](${s},${w},${n},${e});
    );
    out center tags;
  `;
  const endpoints = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
  ];

  let lastErr = null;
  for (const url of endpoints) {
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: "data=" + encodeURIComponent(query),
      });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const json = await res.json();
      return parseOverpass(json);
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr ?? new Error("All Overpass endpoints failed");
}

function parseOverpass(json) {
  const out = [];
  for (const el of json.elements ?? []) {
    let lat, lon;
    if (el.type === "node") {
      lat = el.lat;
      lon = el.lon;
    } else if (el.center) {
      lat = el.center.lat;
      lon = el.center.lon;
    } else {
      continue;
    }
    out.push({
      lat,
      lon,
      name: el.tags?.name ?? "Parking",
      access: el.tags?.access ?? null,
      fee: el.tags?.fee ?? null,
      capacity: el.tags?.capacity ?? null,
    });
  }
  return out;
}

// --- Parking markers --------------------------------------------------------

function renderParking(points) {
  parkingLayer.clearLayers();
  for (const p of points) {
    const marker = L.marker([p.lat, p.lon], {
      icon: L.divIcon({
        className: "",
        html: '<div class="parking-marker"></div>',
        iconSize: [12, 12],
        iconAnchor: [6, 6],
      }),
    });
    const lines = [`<strong>${escapeHtml(p.name)}</strong>`];
    if (p.capacity) lines.push("Capacity: " + escapeHtml(p.capacity));
    if (p.fee) lines.push("Fee: " + escapeHtml(p.fee));
    if (p.access) lines.push("Access: " + escapeHtml(p.access));
    marker.bindPopup(lines.join("<br>"));
    marker.addTo(parkingLayer);
  }
}

function escapeHtml(s) {
  return String(s).replace(
    /[&<>"']/g,
    (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }[c])
  );
}

// --- Heatmap ---------------------------------------------------------------

// Equirectangular metres-per-degree at the bbox latitude. The bbox is small
// enough that this projection error is negligible compared to the 5 m grid.
const METERS_PER_DEG_LAT = 111320;
function metersPerDegLon(lat) {
  return 111320 * Math.cos((lat * Math.PI) / 180);
}

function computeGridDims() {
  const mPerLon = metersPerDegLon(CENTER.lat);
  const widthM = (BBOX.east - BBOX.west) * mPerLon;
  const heightM = (BBOX.north - BBOX.south) * METERS_PER_DEG_LAT;
  const cols = Math.round(widthM / CELL_M);
  const rows = Math.round(heightM / CELL_M);
  return { cols, rows, widthM, heightM, mPerLon };
}

// Convert parking lat/lon to local metric coords (x = east, y = north) with
// origin at bbox SW corner.
function toLocalMeters(points, mPerLon) {
  return points.map((p) => ({
    x: (p.lon - BBOX.west) * mPerLon,
    y: (p.lat - BBOX.south) * METERS_PER_DEG_LAT,
  }));
}

function colorForDistance(d) {
  // d in metres. Returns [r, g, b].
  // Piecewise gradient: green -> yellow -> orange -> red -> dark magenta.
  const stops = [
    { d: 0,   c: [0, 160, 0] },
    { d: 100, c: [180, 200, 0] },
    { d: 200, c: [230, 160, 0] },
    { d: 300, c: [220, 60, 30] },
    { d: 400, c: [120, 0, 60] },
  ];
  if (d <= stops[0].d) return stops[0].c;
  if (d >= stops[stops.length - 1].d) return stops[stops.length - 1].c;
  for (let i = 0; i < stops.length - 1; i++) {
    const a = stops[i], b = stops[i + 1];
    if (d >= a.d && d <= b.d) {
      const t = (d - a.d) / (b.d - a.d);
      return [
        Math.round(a.c[0] + t * (b.c[0] - a.c[0])),
        Math.round(a.c[1] + t * (b.c[1] - a.c[1])),
        Math.round(a.c[2] + t * (b.c[2] - a.c[2])),
      ];
    }
  }
  return [0, 0, 0];
}

function buildHeatmapCanvas(points) {
  const { cols, rows, mPerLon } = computeGridDims();
  const locals = toLocalMeters(points, mPerLon);

  const canvas = document.createElement("canvas");
  canvas.width = cols;
  canvas.height = rows;
  const ctx = canvas.getContext("2d");
  const img = ctx.createImageData(cols, rows);
  const data = img.data;

  // For each cell, find min distance to any parking centroid.
  // Brute force: cols*rows*N. For ~160k cells and ~150 parkings -> ~24M ops.
  // Runs in well under a second on modern browsers.
  const n = locals.length;
  for (let r = 0; r < rows; r++) {
    // y at cell centre, measured from bbox south. Canvas pixel row 0 is the
    // TOP (north), so we flip: top row -> highest y.
    const y = (rows - r - 0.5) * CELL_M;
    for (let c = 0; c < cols; c++) {
      const x = (c + 0.5) * CELL_M;
      let best = Infinity;
      for (let i = 0; i < n; i++) {
        const dx = locals[i].x - x;
        const dy = locals[i].y - y;
        const d2 = dx * dx + dy * dy;
        if (d2 < best) best = d2;
      }
      const walk = Math.sqrt(best) * WALK_FACTOR;
      const clamped = Math.min(walk, MAX_DIST_M);
      const [rr, gg, bb] = colorForDistance(clamped);
      const idx = (r * cols + c) * 4;
      data[idx] = rr;
      data[idx + 1] = gg;
      data[idx + 2] = bb;
      data[idx + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  return canvas;
}

function renderHeatmap(points) {
  if (heatmapOverlay) {
    map.removeLayer(heatmapOverlay);
    heatmapOverlay = null;
  }
  if (!points.length) return;

  const canvas = buildHeatmapCanvas(points);
  const url = canvas.toDataURL("image/png");
  const bounds = [
    [BBOX.south, BBOX.west],
    [BBOX.north, BBOX.east],
  ];
  heatmapOverlay = L.imageOverlay(url, bounds, {
    opacity: opacityEl.valueAsNumber / 100,
    interactive: false,
    // Nearest-neighbour scaling so the 5 m cells stay crisp when zoomed in.
    className: "heatmap-overlay",
  });
  if (showHeatmapEl.checked) heatmapOverlay.addTo(map);
}

// Inject CSS rule that disables image smoothing on the overlay.
const styleEl = document.createElement("style");
styleEl.textContent = `
  .heatmap-overlay {
    image-rendering: pixelated;
    image-rendering: -moz-crisp-edges;
  }
`;
document.head.appendChild(styleEl);

// --- Wiring ---------------------------------------------------------------

opacityEl.addEventListener("input", () => {
  if (heatmapOverlay) heatmapOverlay.setOpacity(opacityEl.valueAsNumber / 100);
});

showHeatmapEl.addEventListener("change", () => {
  if (!heatmapOverlay) return;
  if (showHeatmapEl.checked) heatmapOverlay.addTo(map);
  else map.removeLayer(heatmapOverlay);
});

showParkingEl.addEventListener("change", () => {
  if (showParkingEl.checked) parkingLayer.addTo(map);
  else map.removeLayer(parkingLayer);
});

recomputeBtn.addEventListener("click", () => {
  if (!parkingPoints.length) return;
  setStatus("Recomputing heatmap…");
  // Defer to next tick so the UI can update.
  setTimeout(() => {
    const t0 = performance.now();
    renderHeatmap(parkingPoints);
    const ms = Math.round(performance.now() - t0);
    setStatus(
      `${parkingPoints.length} parking lots, ${CELL_M} m grid, heatmap in ${ms} ms.`
    );
  }, 20);
});

async function init() {
  try {
    setStatus("Fetching parking data from OpenStreetMap…");
    parkingPoints = await fetchParking();
    renderParking(parkingPoints);

    setStatus(`Computing ${CELL_M} m heatmap for ${parkingPoints.length} lots…`);
    // Defer so the status text actually paints first.
    await new Promise((r) => setTimeout(r, 30));

    const t0 = performance.now();
    renderHeatmap(parkingPoints);
    const ms = Math.round(performance.now() - t0);
    setStatus(
      `${parkingPoints.length} parking lots, ${CELL_M} m grid, heatmap in ${ms} ms.`
    );
  } catch (e) {
    console.error(e);
    setStatus("Failed to load parking data: " + e.message);
  }
}

init();
