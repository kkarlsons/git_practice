// Click-to-compute transit heatmap for Riga.
// Renders results as a Canvas ground overlay (google.maps.OverlayView).

let map, marker, overlay;

const RIGA_CENTER = { lat: 56.9496, lng: 24.1052 };

/* global google, initMap */
window.initMap = function () {
  map = new google.maps.Map(document.getElementById("map"), {
    center: RIGA_CENTER,
    zoom: 12,
    clickableIcons: false,
    streetViewControl: false,
    mapTypeControl: false,
    fullscreenControl: false,
  });

  map.addListener("click", (e) => {
    const lat = e.latLng.lat();
    const lng = e.latLng.lng();
    placeMarker(lat, lng);
    computeAndRender(lat, lng);
  });
};

function placeMarker(lat, lng) {
  const position = { lat, lng };
  if (marker) {
    marker.setPosition(position);
  } else {
    marker = new google.maps.Marker({
      position,
      map,
      title: "Origin",
      zIndex: 999,
    });
  }
}

function setStatus(text, kind = "idle") {
  const el = document.getElementById("status");
  el.textContent = text;
  el.className = `status ${kind}`;
}

async function computeAndRender(lat, lng) {
  const gridM = Number(document.getElementById("grid-m").value);
  const maxMin = Number(document.getElementById("max-min").value);
  document.getElementById("legend-max").textContent = `${maxMin} min`;

  setStatus(`Computing travel times on a ${gridM} m grid…`, "loading");
  const t0 = performance.now();

  let data;
  try {
    const res = await fetch(`${window.APP_CONFIG.backendUrl}/travel_times`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lat, lon: lng, grid_m: gridM, max_minutes: maxMin }),
    });
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
    data = await res.json();
  } catch (err) {
    setStatus(`Error: ${err.message}`, "error");
    return;
  }

  const elapsed = ((performance.now() - t0) / 1000).toFixed(1);
  const pct = ((data.stats.reached / data.stats.cells) * 100).toFixed(0);
  setStatus(
    `Reached ${pct}% of ${data.stats.cells} cells • median ${Math.round(data.stats.median_seconds / 60)} min • ${elapsed}s`,
    "ok",
  );

  renderHeatmap(data, maxMin * 60);
}

function renderHeatmap(data, maxSeconds) {
  if (overlay) overlay.setMap(null);
  overlay = new HeatmapOverlay(data, maxSeconds);
  overlay.setMap(map);
}

/* ---------- Heatmap overlay ---------- */

class HeatmapOverlay extends google.maps.OverlayView {
  constructor(data, maxSeconds) {
    super();
    this.data = data;
    this.maxSeconds = maxSeconds;
    const [latMin, lonMin, latMax, lonMax] = data.bbox;
    // Pad by half a cell so cell centers sit in cell middles.
    const halfLat = (latMax - latMin) / (2 * (data.nrows - 1 || 1));
    const halfLon = (lonMax - lonMin) / (2 * (data.ncols - 1 || 1));
    this.bounds = new google.maps.LatLngBounds(
      { lat: latMin - halfLat, lng: lonMin - halfLon },
      { lat: latMax + halfLat, lng: lonMax + halfLon },
    );
    this.canvas = document.createElement("canvas");
    this.canvas.width = data.ncols;
    this.canvas.height = data.nrows;
    this.canvas.style.position = "absolute";
    this.canvas.style.opacity = "0.65";
    this.canvas.style.pointerEvents = "none";
    this.canvas.style.imageRendering = "pixelated";
    this.paint();
  }

  paint() {
    const { ncols, nrows, times } = this.data;
    const ctx = this.canvas.getContext("2d");
    const img = ctx.createImageData(ncols, nrows);
    for (let r = 0; r < nrows; r++) {
      // Canvas y grows downward, our row 0 is the southernmost row.
      const srcRow = nrows - 1 - r;
      for (let c = 0; c < ncols; c++) {
        const t = times[srcRow * ncols + c];
        const o = (r * ncols + c) * 4;
        if (t < 0) {
          img.data[o + 3] = 0;
          continue;
        }
        const [R, G, B] = rampColor(Math.min(t / this.maxSeconds, 1));
        img.data[o] = R;
        img.data[o + 1] = G;
        img.data[o + 2] = B;
        img.data[o + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
  }

  onAdd() {
    this.getPanes().overlayLayer.appendChild(this.canvas);
  }

  onRemove() {
    this.canvas.remove();
  }

  draw() {
    const proj = this.getProjection();
    if (!proj) return;
    const sw = proj.fromLatLngToDivPixel(this.bounds.getSouthWest());
    const ne = proj.fromLatLngToDivPixel(this.bounds.getNorthEast());
    this.canvas.style.left = sw.x + "px";
    this.canvas.style.top = ne.y + "px";
    this.canvas.style.width = ne.x - sw.x + "px";
    this.canvas.style.height = sw.y - ne.y + "px";
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
