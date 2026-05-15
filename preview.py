"""
Offline preview renderer for the Riga parking heatmap.

The deployed app fetches live parking data from the Overpass API and tiles
from OpenStreetMap. Neither is reachable from this sandbox, so this script
renders a STYLISED PREVIEW only:
  - parking locations are a curated set of ~25 well-known central-Riga
    facilities, hand-coded from general knowledge (approximate),
  - there is no street map underneath; instead we draw a coordinate frame
    plus an approximate outline of the river Daugava for spatial context.

Output: preview.png in the same directory.
"""

import math
from PIL import Image, ImageDraw, ImageFont

# --- Geometry (matches app.js) ----------------------------------------------

CENTER = (56.9496, 24.1052)
HALF_LAT = 0.009
HALF_LON = 0.0165
BBOX = {
    "south": CENTER[0] - HALF_LAT,
    "north": CENTER[0] + HALF_LAT,
    "west": CENTER[1] - HALF_LON,
    "east": CENTER[1] + HALF_LON,
}
CELL_M = 5
WALK_FACTOR = 1.3
MAX_DIST_M = 400

METERS_PER_DEG_LAT = 111320.0
def meters_per_deg_lon(lat):
    return 111320.0 * math.cos(math.radians(lat))

M_PER_LON = meters_per_deg_lon(CENTER[0])
WIDTH_M = (BBOX["east"] - BBOX["west"]) * M_PER_LON
HEIGHT_M = (BBOX["north"] - BBOX["south"]) * METERS_PER_DEG_LAT
COLS = round(WIDTH_M / CELL_M)
ROWS = round(HEIGHT_M / CELL_M)

# --- Curated parking facility coordinates (APPROXIMATE) ---------------------
# Selected well-known parking facilities in / around central Riga. These are
# hand-coded estimates, not OSM data. The deployed web app pulls the real,
# complete list from Overpass.

PARKING = [
    ("Origo / Central Station",       56.9466, 24.1192),
    ("Stockmann",                     56.9483, 24.1118),
    ("Galerija Centrs",               56.9485, 24.1135),
    ("Forum Cinemas",                 56.9486, 24.1112),
    ("Kalku iela",                    56.9492, 24.1080),
    ("Doma laukums",                  56.9495, 24.1043),
    ("11. novembra krastmala",        56.9476, 24.1058),
    ("Latvian National Opera",        56.9510, 24.1148),
    ("Bastejkalns",                   56.9514, 24.1149),
    ("Vermanes darzs E",              56.9530, 24.1190),
    ("Vermanes darzs W",              56.9528, 24.1141),
    ("Radisson Blu Latvija",          56.9559, 24.1149),
    ("Galleria Riga",                 56.9559, 24.1148),
    ("Esplanade",                     56.9554, 24.1095),
    ("National Museum of Art",        56.9568, 24.1118),
    ("Kongresu nams",                 56.9542, 24.1118),
    ("Berga bazars",                  56.9551, 24.1224),
    ("Elizabetes / Barona",           56.9551, 24.1233),
    ("Tērbatas iela",                 56.9540, 24.1244),
    ("Marijas iela",                  56.9518, 24.1227),
    ("Skanstes",                      56.9628, 24.1135),
    ("K. Valdemara",                  56.9580, 24.1085),
    ("Spikeri",                       56.9436, 24.1175),
    ("Stacijas laukums S",            56.9450, 24.1208),
    ("Bruninieku",                    56.9595, 24.1240),
    ("Hanzas",                        56.9612, 24.1180),
    ("Pulkveza Brieza",               56.9605, 24.1078),
]

# --- Color ramp (matches app.js colorForDistance) ---------------------------

STOPS = [
    (0,   (  0, 160,   0)),
    (100, (180, 200,   0)),
    (200, (230, 160,   0)),
    (300, (220,  60,  30)),
    (400, (120,   0,  60)),
]

def color_for_distance(d):
    if d <= STOPS[0][0]:
        return STOPS[0][1]
    if d >= STOPS[-1][0]:
        return STOPS[-1][1]
    for (a_d, a_c), (b_d, b_c) in zip(STOPS, STOPS[1:]):
        if a_d <= d <= b_d:
            t = (d - a_d) / (b_d - a_d)
            return (
                int(a_c[0] + t * (b_c[0] - a_c[0])),
                int(a_c[1] + t * (b_c[1] - a_c[1])),
                int(a_c[2] + t * (b_c[2] - a_c[2])),
            )
    return (0, 0, 0)

# --- Heatmap grid -----------------------------------------------------------

def to_local_meters(points):
    out = []
    for _, lat, lon in points:
        x = (lon - BBOX["west"]) * M_PER_LON
        y = (lat - BBOX["south"]) * METERS_PER_DEG_LAT
        out.append((x, y))
    return out

def build_heatmap():
    locals_ = to_local_meters(PARKING)
    img = Image.new("RGB", (COLS, ROWS))
    px = img.load()
    for r in range(ROWS):
        y = (ROWS - r - 0.5) * CELL_M
        for c in range(COLS):
            x = (c + 0.5) * CELL_M
            best = float("inf")
            for (lx, ly) in locals_:
                dx = lx - x
                dy = ly - y
                d2 = dx * dx + dy * dy
                if d2 < best:
                    best = d2
            walk = math.sqrt(best) * WALK_FACTOR
            px[c, r] = color_for_distance(min(walk, MAX_DIST_M))
    return img

# --- Composition ------------------------------------------------------------

OUT_W, OUT_H = 1400, int(1400 * ROWS / COLS)  # preserve aspect

def lonlat_to_px(lat, lon):
    fx = (lon - BBOX["west"]) / (BBOX["east"] - BBOX["west"])
    fy = (BBOX["north"] - lat) / (BBOX["north"] - BBOX["south"])
    return (fx * OUT_W, fy * OUT_H)

def font(size):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except Exception:
            pass
    return ImageFont.load_default()

# Approximate Daugava river centerline through central Riga (rough).
RIVER_CENTERLINE = [
    (56.9650, 24.0900),
    (56.9610, 24.0930),
    (56.9560, 24.0950),
    (56.9510, 24.0970),
    (56.9460, 24.0995),
    (56.9410, 24.1040),
]
RIVER_HALF_WIDTH_M = 350  # half of ~700m

def river_polygon_px():
    # Build a polygon by offsetting the centerline perpendicular to itself
    # by RIVER_HALF_WIDTH_M on each side.
    pts_m = []
    for lat, lon in RIVER_CENTERLINE:
        x = (lon - BBOX["west"]) * M_PER_LON
        y = (lat - BBOX["south"]) * METERS_PER_DEG_LAT
        pts_m.append((x, y))
    left, right = [], []
    for i, (x, y) in enumerate(pts_m):
        if i == 0:
            dx = pts_m[1][0] - x; dy = pts_m[1][1] - y
        elif i == len(pts_m) - 1:
            dx = x - pts_m[-2][0]; dy = y - pts_m[-2][1]
        else:
            dx = pts_m[i+1][0] - pts_m[i-1][0]
            dy = pts_m[i+1][1] - pts_m[i-1][1]
        L = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / L, dx / L
        left.append((x + nx * RIVER_HALF_WIDTH_M, y + ny * RIVER_HALF_WIDTH_M))
        right.append((x - nx * RIVER_HALF_WIDTH_M, y - ny * RIVER_HALF_WIDTH_M))
    poly_m = left + list(reversed(right))
    # Convert to pixels
    out = []
    for (mx, my) in poly_m:
        fx = mx / WIDTH_M
        fy = 1 - my / HEIGHT_M
        out.append((fx * OUT_W, fy * OUT_H))
    return out

def main():
    print(f"Heatmap grid: {COLS} x {ROWS} cells ({CELL_M} m each)")
    print(f"Parking count: {len(PARKING)} (curated, approximate)")

    heat_small = build_heatmap()
    heat = heat_small.resize((OUT_W, OUT_H), Image.NEAREST)

    # Background: pale grey
    bg = Image.new("RGB", (OUT_W, OUT_H), (245, 245, 244))

    # Composite heatmap at 75% opacity over background
    heat_rgba = heat.convert("RGBA")
    alpha = Image.new("L", (OUT_W, OUT_H), int(255 * 0.78))
    heat_rgba.putalpha(alpha)
    canvas = bg.convert("RGBA")
    canvas = Image.alpha_composite(canvas, heat_rgba)

    draw = ImageDraw.Draw(canvas, "RGBA")

    # River overlay
    river = river_polygon_px()
    draw.polygon(river, fill=(100, 140, 200, 170))

    # Parking markers
    for name, lat, lon in PARKING:
        x, y = lonlat_to_px(lat, lon)
        r = 7
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(30, 60, 200, 255),
                     outline=(255, 255, 255, 255), width=2)

    # Title
    title_font = font(28)
    sub_font = font(16)
    draw.rectangle([0, 0, OUT_W, 80], fill=(20, 20, 20, 220))
    draw.text((20, 16), "Riga center - walking distance to nearest parking",
              fill=(255, 255, 255), font=title_font)
    draw.text((20, 52),
              "DEMO PREVIEW. Sandbox cannot reach OSM/Overpass; map tiles + "
              "real parking data are unavailable here.",
              fill=(220, 220, 220), font=sub_font)

    # Legend
    lg_x, lg_y, lg_w, lg_h = 20, OUT_H - 80, 380, 18
    grad = Image.new("RGB", (lg_w, lg_h))
    for px_x in range(lg_w):
        d = px_x / (lg_w - 1) * MAX_DIST_M
        for px_y in range(lg_h):
            grad.putpixel((px_x, px_y), color_for_distance(d))
    canvas.paste(grad, (lg_x, lg_y))
    label_font = font(13)
    for i, lbl in enumerate(["0", "100", "200", "300", "400+ m"]):
        x = lg_x + i * (lg_w / 4)
        draw.text((x - 8, lg_y + lg_h + 4), lbl,
                  fill=(20, 20, 20), font=label_font)
    draw.text((lg_x, lg_y - 18), "Approximate walking distance (m)",
              fill=(20, 20, 20), font=label_font)

    # Scale bar (200 m)
    sb_m = 200
    sb_px = sb_m / WIDTH_M * OUT_W
    sb_x = OUT_W - sb_px - 30
    sb_y = OUT_H - 40
    draw.rectangle([sb_x, sb_y, sb_x + sb_px, sb_y + 6], fill=(20, 20, 20))
    draw.text((sb_x, sb_y - 18), f"{sb_m} m",
              fill=(20, 20, 20), font=label_font)

    # Compass
    draw.text((OUT_W - 30, 90), "N",
              fill=(20, 20, 20), font=font(20))
    draw.line([(OUT_W - 22, 110), (OUT_W - 22, 140)],
              fill=(20, 20, 20), width=2)
    draw.polygon([(OUT_W - 27, 115), (OUT_W - 17, 115), (OUT_W - 22, 105)],
                 fill=(20, 20, 20))

    # River label
    rx, ry = lonlat_to_px(56.9500, 24.0975)
    draw.text((rx - 30, ry), "Daugava", fill=(255, 255, 255),
              font=font(16))

    # Legend dot for parking
    dx, dy = OUT_W - 220, OUT_H - 80
    draw.ellipse([dx, dy, dx + 14, dy + 14], fill=(30, 60, 200),
                 outline=(255, 255, 255), width=2)
    draw.text((dx + 22, dy - 2),
              f"Parking ({len(PARKING)} curated)",
              fill=(20, 20, 20), font=label_font)

    canvas.convert("RGB").save("preview.png", "PNG", optimize=True)
    print("Wrote preview.png")

if __name__ == "__main__":
    main()
