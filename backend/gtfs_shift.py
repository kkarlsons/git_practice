"""Shift an expired GTFS feed's calendar forward so r5py treats it as active.

Real fix is a fresh feed from the operator; this is a workaround for feeds
that haven't been renewed but whose schedule pattern is still accurate.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import logging
import zipfile
from pathlib import Path

log = logging.getLogger("riga-heatmap")


def _parse(d: str) -> dt.date | None:
    s = (d or "").strip()
    if len(s) != 8 or not s.isdigit():
        return None
    return dt.date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def _fmt(d: dt.date) -> str:
    return d.strftime("%Y%m%d")


def _latest_end_date(z: zipfile.ZipFile) -> dt.date | None:
    latest: dt.date | None = None
    for name, col in (("calendar.txt", "end_date"), ("calendar_dates.txt", "date")):
        try:
            text = z.read(name).decode("utf-8-sig")
        except KeyError:
            continue
        for row in csv.DictReader(io.StringIO(text)):
            d = _parse(row.get(col, ""))
            if d and (latest is None or d > latest):
                latest = d
    return latest


def _shift_text(text: str, cols: list[str], shift_days: int) -> str:
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames or []
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames)
    writer.writeheader()
    for row in reader:
        for c in cols:
            d = _parse(row.get(c, ""))
            if d is not None:
                row[c] = _fmt(d + dt.timedelta(days=shift_days))
        writer.writerow(row)
    return out.getvalue()


def shift_gtfs_if_expired(src: Path, dst: Path, target_end_min: dt.date) -> Path:
    """Return src unchanged if its calendar still covers target_end_min; otherwise
    write a forward-shifted copy to dst and return dst. Shift is always a whole
    number of weeks so weekday-of-service is preserved."""
    with zipfile.ZipFile(src) as z:
        latest = _latest_end_date(z)
    if latest is None or latest >= target_end_min:
        return src

    delta = (target_end_min - latest).days
    shift_days = ((delta + 6) // 7) * 7  # round up to whole weeks
    dst.parent.mkdir(parents=True, exist_ok=True)
    log.info(
        "GTFS %s expired (last end_date %s). Shifting +%d days (%d weeks) -> %s",
        src.name, _fmt(latest), shift_days, shift_days // 7, dst,
    )

    shift_map = {
        "calendar.txt": ["start_date", "end_date"],
        "calendar_dates.txt": ["date"],
        "feed_info.txt": ["feed_start_date", "feed_end_date"],
    }
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            cols = shift_map.get(item.filename)
            if cols:
                data = _shift_text(data.decode("utf-8-sig"), cols, shift_days).encode("utf-8")
            zout.writestr(item, data)
    return dst
