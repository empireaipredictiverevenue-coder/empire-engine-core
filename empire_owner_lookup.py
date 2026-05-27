"""
EMPIRE V49 · OWNER LOOKUP
=========================
Real reverse-geocode + warehouse identification.
Replaces the stub that returned "Logistics-Hub-TX-04".
Falls back gracefully through Nominatim → OSM → coords-only.
"""
import logging
from typing import Dict, Optional, Tuple
import httpx

log = logging.getLogger("empire.owner_lookup")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "EmpireAI-v49 (ops@empire-ai.co.uk)"


async def get_property_details(lat: float, lon: float) -> Dict:
    """
    Reverse-geocode coordinates to building/business details.
    Returns dict with warehouse_name, address, raw OSM data.
    Never raises — degrades to coords-only if all lookups fail.
    """
    fallback = {
        "warehouse_name": f"Site @ {lat:.4f},{lon:.4f}",
        "address": f"{lat:.6f}, {lon:.6f}",
        "lat": lat,
        "lon": lon,
        "source": "fallback",
    }
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.get(
                NOMINATIM_URL,
                params={"lat": lat, "lon": lon, "format": "json", "zoom": 18, "addressdetails": 1},
                headers={"User-Agent": USER_AGENT},
            )
            r.raise_for_status()
            d = r.json() or {}
    except Exception as e:
        log.warning(f"[owner_lookup] Nominatim failed @ {lat},{lon}: {e}")
        return fallback

    address = d.get("address") or {}
    display = d.get("display_name") or ""
    name = (
        d.get("name")
        or address.get("amenity")
        or address.get("building")
        or address.get("commercial")
        or address.get("industrial")
        or address.get("shop")
        or (display.split(",")[0] if display else None)
    )

    return {
        "warehouse_name": name or f"Site @ {lat:.4f},{lon:.4f}",
        "address": display or f"{lat:.6f}, {lon:.6f}",
        "lat": lat,
        "lon": lon,
        "osm_type": d.get("osm_type"),
        "osm_id": d.get("osm_id"),
        "raw_address": address,
        "source": "nominatim",
    }
