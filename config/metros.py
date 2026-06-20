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
    # ── Core tornado alley / plains ──
    "Wichita":             {"lat": 37.6872, "lon": -97.3301, "state": "KS"},
    "Oklahoma City":       {"lat": 35.4676, "lon": -97.5164, "state": "OK"},
    "Kansas City":         {"lat": 39.0997, "lon": -94.5786, "state": "MO"},
    "Tulsa":               {"lat": 36.1540, "lon": -95.9928, "state": "OK"},
    # ── Texas — storm + hail corridor ──
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
    # ── Florida — hurricane central ──
    "Miami":               {"lat": 25.7617, "lon": -80.1918, "state": "FL"},
    "Tampa":               {"lat": 27.9506, "lon": -82.4572, "state": "FL"},
    "Orlando":             {"lat": 28.5383, "lon": -81.3792, "state": "FL"},
    "Jacksonville":        {"lat": 30.3322, "lon": -81.6557, "state": "FL"},
    "Fort Myers":          {"lat": 26.6407, "lon": -81.8723, "state": "FL"},
    "Pensacola":           {"lat": 30.4213, "lon": -87.2169, "state": "FL"},
    "Tallahassee":         {"lat": 30.4383, "lon": -84.2807, "state": "FL"},
    # ── Gulf Coast ──
    "Mobile":              {"lat": 30.6954, "lon": -88.0399, "state": "AL"},
    "Birmingham":          {"lat": 33.5207, "lon": -86.8025, "state": "AL"},
    "Baton Rouge":         {"lat": 30.4515, "lon": -91.1871, "state": "LA"},
    "Jackson":             {"lat": 32.2988, "lon": -90.1848, "state": "MS"},
    "Gulfport":            {"lat": 30.3674, "lon": -89.0928, "state": "MS"},
    # ── Carolinas — hurricane + hail ──
    "Charlotte":           {"lat": 35.2271, "lon": -80.8431, "state": "NC"},
    "Raleigh":             {"lat": 35.7796, "lon": -78.6382, "state": "NC"},
    "Wilmington":          {"lat": 34.2257, "lon": -77.9447, "state": "NC"},
    "Columbia":            {"lat": 34.0007, "lon": -81.0348, "state": "SC"},
    "Charleston":          {"lat": 32.7765, "lon": -79.9311, "state": "SC"},
    "Myrtle Beach":        {"lat": 33.6891, "lon": -78.8867, "state": "SC"},
    # ── Midwest / Ohio Valley ──
    "Denver":              {"lat": 39.7392, "lon": -104.9903, "state": "CO"},
    "St. Louis":           {"lat": 38.6270, "lon": -90.1994, "state": "MO"},
    "Springfield":         {"lat": 37.2090, "lon": -93.2923, "state": "MO"},
    "Little Rock":         {"lat": 34.7465, "lon": -92.2896, "state": "AR"},
    "Omaha":               {"lat": 41.2565, "lon": -95.9345, "state": "NE"},
    "Des Moines":          {"lat": 41.5868, "lon": -93.6250, "state": "IA"},
    "Indianapolis":        {"lat": 39.7684, "lon": -86.1581, "state": "IN"},
    "Columbus":            {"lat": 39.9612, "lon": -82.9988, "state": "OH"},
    "Louisville":          {"lat": 38.2527, "lon": -85.7585, "state": "KY"},
    # ── Southeast ──
    "New Orleans":         {"lat": 29.9511, "lon": -90.0715, "state": "LA"},
    "Memphis":             {"lat": 35.1495, "lon": -90.0490, "state": "TN"},
    "Atlanta":             {"lat": 33.7490, "lon": -84.3880, "state": "GA"},
    "Nashville":           {"lat": 36.1627, "lon": -86.7816, "state": "TN"},
    "Knoxville":           {"lat": 35.9606, "lon": -83.9207, "state": "TN"},
    "Savannah":            {"lat": 32.0809, "lon": -81.0912, "state": "GA"},
    # ── Mid-Atlantic / Northeast ──
    "Richmond":            {"lat": 37.5407, "lon": -77.4360, "state": "VA"},
    "Virginia Beach":      {"lat": 36.8529, "lon": -75.9780, "state": "VA"},
    "Philadelphia":        {"lat": 39.9526, "lon": -75.1652, "state": "PA"},
    "New York City":       {"lat": 40.7128, "lon": -74.0060, "state": "NY"},
    "Boston":              {"lat": 42.3601, "lon": -71.0589, "state": "MA"},
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
