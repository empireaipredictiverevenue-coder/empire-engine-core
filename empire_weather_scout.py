"""
EMPIRE V49 · WEATHER SCOUT
==========================
Real NWS poller. Replaces the demo stub.
Fetches https://api.weather.gov/alerts/active and filters for:
  - Texas metro zones (DFW, Houston, Austin, San Antonio)
  - Severe/Extreme events (Tornado/Thunderstorm/Hail/Flood)
"""
import logging
from typing import List, Dict, Optional, Tuple
import httpx

log = logging.getLogger("empire.scout")

# Texas county UGC zones — DFW, Houston, Austin, San Antonio metros
DEFAULT_TX_ZONES = [
    "TXC113",  # Dallas
    "TXC121",  # Denton
    "TXC439",  # Tarrant (Fort Worth)
    "TXC085",  # Collin (Plano/McKinney)
    "TXC257",  # Kaufman
    "TXC397",  # Rockwall
    "TXC367",  # Parker
    "TXC251",  # Johnson
    "TXC221",  # Hood
    "TXC237",  # Jack
    "TXC497",  # Wise
    "TXC181",  # Grayson
    "TXC231",  # Hunt
    "TXC379",  # Rains
    "TXC499",  # Wood
    "TXC499",  # Wood
    # Houston metro
    "TXC201",  # Harris
    "TXC157",  # Fort Bend
    "TXC339",  # Montgomery
    "TXC039",  # Brazoria
    "TXC291",  # Liberty
    "TXC473",  # Waller
    "TXC167",  # Galveston
    "TXC071",  # Chambers
    # Austin metro
    "TXC453",  # Travis
    "TXC491",  # Williamson
    "TXC209",  # Hays
    "TXC055",  # Caldwell
    "TXC021",  # Bastrop
    # San Antonio metro
    "TXC029",  # Bexar
    "TXC091",  # Comal
    "TXC187",  # Guadalupe
    "TXC325",  # Medina
    "TXC325",  # Medina
    "TXC013",  # Atascosa
    "TXC493",  # Wilson
    "TXC163",  # Frio
    "TXC265",  # Kerr
    "TXC259",  # Kendall
    "TXC031",  # Blanco
    "TXC411",  # San Saba
    "TXC265",  # Kerr
]

TRIGGER_EVENT_KEYWORDS = {
    "TORNADO",
    "SEVERE THUNDERSTORM",
    "HAIL",
    "FLASH FLOOD",
    "FLOOD WARNING",
    "FLOOD ADVISORY",
    "WIND",
    "HURRICANE",
}

SEVERITY_ALLOWLIST = {"Severe", "Extreme"}


class StormTracker:
    """
    Real NWS API client. Replaces the demo stub that hardcoded
    ["Tornado-Viper", "Storm-Front-Omega"].
    """

    def __init__(self, zones: Optional[List[str]] = None, user_agent: str = "EmpireAI-v49 (ops@empire-ai.co.uk)"):
        self.zones = set(zones or DEFAULT_TX_ZONES)
        self.user_agent = user_agent
        self.api = "https://api.weather.gov/alerts/active"

    async def get_active_alerts(self) -> List[Dict]:
        """
        Fetch all currently-active US alerts. Returns the raw feature list.
        We filter client-side because NWS query params on /active are unreliable.
        """
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.get(self.api, headers={"User-Agent": self.user_agent, "Accept": "application/geo+json"})
                r.raise_for_status()
                data = r.json()
                return data.get("features", []) or []
        except Exception as e:
            log.error(f"[scout] NWS fetch failed: {e}")
            return []

    def filter_relevant(self, alerts: List[Dict]) -> List[Dict]:
        """
        Drop alerts that don't match our zones, severity, or event types.
        Returns the alerts we should act on.
        """
        relevant = []
        for alert in alerts:
            props = alert.get("properties") or {}
            event = (props.get("event") or "").upper()
            severity = props.get("severity") or ""
            geocode = (props.get("geocode") or {}).get("UGC") or []

            # Zone match
            if not any(z in self.zones for z in geocode):
                continue
            # Severity match
            if severity not in SEVERITY_ALLOWLIST:
                continue
            # Event keyword match
            if not any(k in event for k in TRIGGER_EVENT_KEYWORDS):
                continue

            relevant.append(alert)
        return relevant

    def extract_polygon(self, alert: Dict) -> Optional[Dict]:
        """
        NWS alerts may carry a polygon (GeoJSON geometry).
        Returns dict with 'coords' (list of [lon, lat]) or None if not available.
        """
        geom = alert.get("geometry")
        if not geom:
            return None
        if geom.get("type") != "Polygon":
            return None
        coords = (geom.get("coordinates") or [[]])[0]  # outer ring
        if not coords:
            return None
        return {"type": "Polygon", "coords": coords}

    def extract_centroid(self, alert: Dict) -> Optional[Tuple[float, float]]:
        """Rough centroid of the alert polygon, for OSM/Overpass searches."""
        poly = self.extract_polygon(alert)
        if not poly or not poly["coords"]:
            return None
        coords = poly["coords"]
        lon = sum(c[0] for c in coords) / len(coords)
        lat = sum(c[1] for c in coords) / len(coords)
        return (lat, lon)

    def alert_summary(self, alert: Dict) -> Dict:
        """Compact summary for logging/strike_log."""
        props = alert.get("properties") or {}
        return {
            "id": props.get("id") or alert.get("id"),
            "event": props.get("event"),
            "severity": props.get("severity"),
            "urgency": props.get("urgency"),
            "headline": props.get("headline"),
            "area": props.get("areaDesc"),
            "effective": props.get("effective"),
            "expires": props.get("expires"),
            "sender": props.get("senderName"),
            "geocode_ugc": (props.get("geocode") or {}).get("UGC") or [],
        }
