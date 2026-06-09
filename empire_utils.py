"""Empire AI · Shared Utilities
==================================
Single source of truth for cross-module helpers. Keeps duplicate definitions
(area-code → timezone maps, etc.) from drifting across the codebase.
"""

from zoneinfo import ZoneInfo
from datetime import datetime, timezone


# ── AREA CODE → TIMEZONE ────────────────────────────────────────────
# Used by the switchboard (inbound call routing) and the outbound dialer
# (compliance window checks). Update here — not in two places.
AREACODE_TZ: dict[str, str] = {
    "212": "America/New_York",
    "305": "America/New_York",
    "404": "America/New_York",
    "312": "America/Chicago",
    "713": "America/Chicago",
    "214": "America/Chicago",
    "469": "America/Chicago",
    "972": "America/Chicago",
    "316": "America/Chicago",
    "405": "America/Chicago",
    "816": "America/Chicago",
    "615": "America/Chicago",
    "323": "America/Los_Angeles",
    "415": "America/Los_Angeles",
    "206": "America/Los_Angeles",
    "602": "America/Phoenix",
    "303": "America/Denver",
    "801": "America/Denver",
}


def tz_for_areacode(number: str) -> str:
    """Determine the IANA timezone name from a phone number's area code.

    Strips non-digit characters and a leading \"1\" country code, then
    looks up the 3-digit area code. Falls back to America/Chicago.
    """
    d = "".join(c for c in (number or "") if c.isdigit())
    if d.startswith("1"):
        d = d[1:]
    return AREACODE_TZ.get(d[:3], "America/Chicago")
