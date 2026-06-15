"""
EMPIRE AI · Shared Metro Configuration
=======================================
Single source of truth for metro centroids used across the fleet.
Imported by bots/prospector.py, bots/mesh_scout.py, and any other
agent that needs lat/lon/state for a metro area.

Every entry has: lat, lon, state
  - lat/lon are the approximate city center (for Places API location bias)
  - state is the 2-letter USPS code (for compliance/routing)

Add new metros here, not in individual agent files.
"""
from typing import Dict, List, Optional, Tuple

METROS: Dict[str, Dict[str, float | str]] = {
    "Wichita":             {"lat": 37.6872, "lon": -97.3301, "state": "KS"},
    "Oklahoma City":       {"lat": 35.4676, "lon": -97.5164, "state": "OK"},
    "Kansas City":         {"lat": 39.0997, "lon": -94.5786, "state": "MO"},
    "Dallas-Fort Worth":   {"lat": 32.7767, "lon": -96.7970, "state": "TX"},
    "Houston":             {"lat": 29.7604, "lon": -95.3698, "state": "TX"},
    "San Antonio":         {"lat": 29.4252, "lon": -98.4946, "state": "TX"},
    "Austin":              {"lat": 30.2672, "lon": -97.7431, "state": "TX"},
    "Waco":                {"lat": 31.5493, "lon": -97.1467, "state": "TX"},
    "Temple":              {"lat": 31.0982, "lon": -97.3428, "state": "TX"},
    "Bryan/College Station": {"lat": 30.6279, "lon": -96.3344, "state": "TX"},
    "Tyler":               {"lat": 32.3513, "lon": -95.3011, "state": "TX"},
    "Lubbock":             {"lat": 33.5779, "lon": -101.8552, "state": "TX"},
    "Amarillo":            {"lat": 35.2220, "lon": -101.8313, "state": "TX"},
    "El Paso":             {"lat": 31.7619, "lon": -106.4850, "state": "TX"},
    "Corpus Christi":      {"lat": 27.8006, "lon": -97.3964, "state": "TX"},
    "Tulsa":               {"lat": 36.1540, "lon": -95.9928, "state": "OK"},
    "Denver":              {"lat": 39.7392, "lon": -104.9903, "state": "CO"},
    "St. Louis":           {"lat": 38.6270, "lon": -90.1994, "state": "MO"},
    "New Orleans":         {"lat": 29.9511, "lon": -90.0715, "state": "LA"},
    "Memphis":             {"lat": 35.1495, "lon": -90.0490, "state": "TN"},
    "Atlanta":             {"lat": 33.7490, "lon": -84.3880, "state": "GA"},
    "Nashville":           {"lat": 36.1627, "lon": -86.7816, "state": "TN"},
}


def metro_keys() -> List[str]:
    """Return sorted list of metro keys for dropdowns / filters."""
    return sorted(METROS.keys())


def metro_coords(metro: str) -> Tuple[Optional[float], Optional[float]]:
    """Return (lat, lon) for a metro, or (None, None) if unknown."""
    m = METROS.get(metro)
    if m:
        return (float(m["lat"]), float(m["lon"]))
    return (None, None)


def metro_state(metro: str) -> str:
    """Return the 2-letter state code for a metro, or '' if unknown."""
    m = METROS.get(metro)
    return str(m["state"]) if m else ""
