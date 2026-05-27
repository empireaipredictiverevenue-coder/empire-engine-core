"""
EMPIRE V49 · SNIPER SATELLITE  (real enricher wrapper)
========================================================
Calls enricher_sniper.find_leads_in_storm_zone(center_lat, center_lon, bbox).
Enricher internally uses Google Places + OSM + Nominatim + SEC EDGAR +
Wikidata + USPTO + Texas SoS.
"""
import logging
from typing import Dict, List, Optional

import enricher_sniper

log = logging.getLogger("empire.satellite")


class SniperSatellite:
    """Identifies high-value targets in a storm zone via the multi-source enricher."""

    def __init__(self, *args, **kwargs):
        pass

    async def scan_and_identify(
        self,
        lat: float,
        lon: float,
        storm_name: str,
        polygon_coords: Optional[List] = None,
        max_results: int = 40,
    ) -> Dict:
        """
        Returns:
            {"status": "STRIKE",       "targets": [...], "storm": ...}
            {"status": "NO_STORM_RISK", "storm": ...}
        """
        # Compute bbox from polygon if available, else padded centroid
        if polygon_coords:
            lats = [c[1] for c in polygon_coords]
            lons = [c[0] for c in polygon_coords]
            bbox = (min(lats), min(lons), max(lats), max(lons))
        else:
            pad = 0.15
            bbox = (lat - pad, lon - pad, lat + pad, lon + pad)

        try:
            leads = await enricher_sniper.find_leads_in_storm_zone(
                center_lat=lat,
                center_lon=lon,
                bbox=bbox,
            )
        except Exception as e:
            log.error(f"[satellite] enricher failed: {e}")
            return {"status": "NO_STORM_RISK", "storm": storm_name, "error": str(e)}

        if not leads:
            return {"status": "NO_STORM_RISK", "storm": storm_name, "centroid": [lat, lon]}

        # Normalize fields the orchestrator expects
        targets = []
        for lead in leads:
            entity = lead.get("entity") or {}
            targets.append({
                "warehouse_name": lead.get("name") or lead.get("warehouse_name") or "Unknown",
                "address": lead.get("address") or lead.get("formatted_address"),
                "lat": lead.get("lat") or lead.get("latitude"),
                "lon": lead.get("lon") or lead.get("longitude"),
                "phone": lead.get("phone") or lead.get("formatted_phone_number"),
                "website": lead.get("website") or lead.get("url"),
                "email": lead.get("email"),
                "city": lead.get("city"),
                "state": lead.get("state"),
                "source": lead.get("source"),
                "entity_match": entity,
                "raw_tags": lead,
            })

        # Cap results to keep the orchestrator predictable
        targets = targets[:max_results]

        return {
            "status": "STRIKE",
            "storm": storm_name,
            "centroid": [lat, lon],
            "bbox": list(bbox),
            "targets": targets,
            "target_count": len(targets),
        }
