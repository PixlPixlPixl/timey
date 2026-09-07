"""World-clock helpers — timezone lookups and formatting.

Pure Python on top of :mod:`zoneinfo` (stdlib), so Timey keeps its zero
dependency promise. The system timezone is the app default; additional
zones come from the curated list below (every entry is validated against
``zoneinfo.available_timezones()`` at import time).
"""

from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path
from zoneinfo import ZoneInfo, available_timezones

#: Well-known IANA zones for the "add a clock" list, ordered roughly by
#: longitude / common usage. The special name ``"Local"`` (always listed
#: first) tracks the system timezone.
CURATED_ZONES: list[tuple[str, str]] = [
    ("Los Angeles", "America/Los_Angeles"),
    ("Vancouver", "America/Vancouver"),
    ("Seattle", "America/Los_Angeles"),
    ("San Francisco", "America/Los_Angeles"),
    ("Denver", "America/Denver"),
    ("Chicago", "America/Chicago"),
    ("Dallas", "America/Chicago"),
    ("New York", "America/New_York"),
    ("Toronto", "America/Toronto"),
    ("Miami", "America/New_York"),
    ("Mexico City", "America/Mexico_City"),
    ("Bogotá", "America/Bogota"),
    ("Lima", "America/Lima"),
    ("São Paulo", "America/Sao_Paulo"),
    ("Buenos Aires", "America/Argentina/Buenos_Aires"),
    ("Reykjavík", "Atlantic/Reykjavik"),
    ("London", "Europe/London"),
    ("Lisbon", "Europe/Lisbon"),
    ("Dublin", "Europe/Dublin"),
    ("Paris", "Europe/Paris"),
    ("Berlin", "Europe/Berlin"),
    ("Madrid", "Europe/Madrid"),
    ("Rome", "Europe/Rome"),
    ("Amsterdam", "Europe/Amsterdam"),
    ("Brussels", "Europe/Brussels"),
    ("Zurich", "Europe/Zurich"),
    ("Stockholm", "Europe/Stockholm"),
    ("Copenhagen", "Europe/Copenhagen"),
    ("Vienna", "Europe/Vienna"),
    ("Warsaw", "Europe/Warsaw"),
    ("Prague", "Europe/Prague"),
    ("Athens", "Europe/Athens"),
    ("Helsinki", "Europe/Helsinki"),
    ("Moscow", "Europe/Moscow"),
    ("Istanbul", "Europe/Istanbul"),
    ("Cairo", "Africa/Cairo"),
    ("Johannesburg", "Africa/Johannesburg"),
    ("Lagos", "Africa/Lagos"),
    ("Nairobi", "Africa/Nairobi"),
    ("Dubai", "Asia/Dubai"),
    ("Tehran", "Asia/Tehran"),
    ("Karachi", "Asia/Karachi"),
    ("Mumbai", "Asia/Kolkata"),
    ("Dhaka", "Asia/Dhaka"),
    ("Bangkok", "Asia/Bangkok"),
    ("Jakarta", "Asia/Jakarta"),
    ("Ho Chi Minh City", "Asia/Ho_Chi_Minh"),
    ("Singapore", "Asia/Singapore"),
    ("Kuala Lumpur", "Asia/Kuala_Lumpur"),
    ("Hong Kong", "Asia/Hong_Kong"),
    ("Beijing", "Asia/Shanghai"),
    ("Shanghai", "Asia/Shanghai"),
    ("Taipei", "Asia/Taipei"),
    ("Seoul", "Asia/Seoul"),
    ("Tokyo", "Asia/Tokyo"),
    ("Osaka", "Asia/Tokyo"),
    ("Sydney", "Australia/Sydney"),
    ("Melbourne", "Australia/Melbourne"),
    ("Brisbane", "Australia/Brisbane"),
    ("Perth", "Australia/Perth"),
    ("Auckland", "Pacific/Auckland"),
    ("Honolulu", "Pacific/Honolulu"),
    ("Anchorage", "America/Anchorage"),
]

_available = available_timezones()

#: (display name, IANA zone) for zones that exist on this system.
CITIES: list[tuple[str, str]] = [
    (city, zone) for city, zone in CURATED_ZONES if zone in _available
]


def local_zone_name() -> str | None:
    """Best-effort IANA name for the system timezone.

    Reads ``/etc/timezone`` (Debian family) or the ``/etc/localtime``
    symlink (Arch family). Returns ``None`` when the name can't be
    determined (the UI then falls back to showing the UTC offset).
    """
    try:
        text = Path("/etc/timezone").read_text(encoding="utf-8").strip()
        if text:
            return text
    except OSError:
        pass
    try:
        target = os.readlink("/etc/localtime")
        marker = "/zoneinfo/"
        if marker in target:
            return target.split(marker, 1)[1]
        if target.startswith("/usr/share/zoneinfo/"):
            return target[len("/usr/share/zoneinfo/"):]
    except OSError:
        pass
    return None


def is_local(zone: str) -> bool:
    """Whether a stored zone is the special "local timezone" marker."""
    return not zone or zone == "Local"


def zone_info(zone: str) -> tuple[str, ZoneInfo | None]:
    """Resolve a stored zone to (label, ZoneInfo).

    The label is a short city-ish name; for the ``"Local"`` marker the
    system zone is resolved. Returns ``(label, None)`` when the zone is
    unknown (skipped by the UI).
    """
    if is_local(zone):
        name = local_zone_name()
        if name:
            try:
                return _city_label(name), ZoneInfo(name)
            except Exception:
                pass
        return "Local time", None
    label = _city_label(zone)
    try:
        return label, ZoneInfo(zone)
    except Exception:
        return label, None


def _city_label(zone: str) -> str:
    """Short readable label from an IANA name.

    Uses the final component, e.g. ``America/Argentina/Buenos_Aires`` ->
    ``Buenos Aires`` and ``Asia/Kolkata`` -> ``Kolkata``.
    """
    return zone.rsplit("/", 1)[-1].replace("_", " ")


def current_in(zone: str) -> _dt.datetime | None:
    """Current *aware* time for a stored zone, or None if unknown."""
    _label, info = zone_info(zone)
    if info is None:
        return None
    return _dt.datetime.now(info)


def snapshot_text(dt: _dt.datetime) -> dict[str, str]:
    """Render text parts for an aware datetime (clock display).

    Returns ``{"time": "13:04:22", "date": "Mon Sep 7", "offset": "UTC+08:00"}``.
    """
    clock = dt.strftime("%H:%M:%S")
    date = dt.strftime("%a %d %b")
    offset = dt.strftime("%z") or "+0000"
    sign = "+" if not offset.startswith("-") else "-"
    hours = int(offset[1:3])
    minutes = int(offset[3:5])
    utc = f"UTC{sign}{hours:02d}:{minutes:02d}"
    return {"time": clock, "date": date, "offset": utc}


def local_offset_label() -> str:
    """Human label like ``"UTC-07:00"`` for the system zone."""
    dt = _dt.datetime.now().astimezone()
    offset = dt.strftime("%z")
    if offset and len(offset) == 5:
        sign = "+" if not offset.startswith("-") else "-"
        return f"UTC{sign}{offset[1:3]}:{offset[3:5]}"
    return "UTC"


def tz_second_key(zone: str) -> str | None:
    """Coarse identity of the current time in a zone (one change/sec)."""
    dt = current_in(zone)
    return dt.strftime("%Y%m%d%H%M%S") if dt is not None else None
