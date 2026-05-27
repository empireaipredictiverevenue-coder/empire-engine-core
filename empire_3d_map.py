"""
EMPIRE V49 · 3D MAP
====================
GeoJSON API for the holographic Mapbox view in the dashboard.
Serves: active storm polygons + target markers + dispatch trails.
"""
import logging
from typing import Dict, List, Callable

log = logging.getLogger("empire.map")


def build_storm_geojson(alerts: List[Dict]) -> Dict:
    """Convert raw NWS alerts to GeoJSON FeatureCollection of storm polygons."""
    features = []
    for alert in alerts:
        geom = alert.get("geometry")
        props = alert.get("properties") or {}
        if not geom or geom.get("type") != "Polygon":
            continue
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "id": props.get("id"),
                "event": props.get("event"),
                "severity": props.get("severity"),
                "urgency": props.get("urgency"),
                "headline": props.get("headline"),
                "area": props.get("areaDesc"),
            },
        })
    return {"type": "FeatureCollection", "features": features}


def build_target_geojson(targets: List[Dict]) -> Dict:
    """Convert radar_targets rows to GeoJSON Points."""
    features = []
    for t in targets:
        loc = t.get("location")
        meta = t.get("meta") or {}
        # Try meta.lat/lon first, then PostGIS location
        lat = meta.get("lat")
        lon = meta.get("lon")
        if lat is None or lon is None:
            raw = meta.get("raw") or {}
            lat = raw.get("lat")
            lon = raw.get("lon")
        if lat is None or lon is None:
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
            "properties": {
                "id": t.get("id"),
                "name": meta.get("warehouse_name") or "Target",
                "address": t.get("address"),
                "phone": t.get("phone"),
                "status": t.get("status"),
                "source": meta.get("source"),
            },
        })
    return {"type": "FeatureCollection", "features": features}


def register_map_routes(app, scout, get_db: Callable, require_auth):
    """Register /api/v1/map/* endpoints."""
    from fastapi import Depends

    @app.get("/api/v1/map/storms")
    async def map_storms(auth: bool = Depends(require_auth)):
        try:
            alerts = await scout.get_active_alerts()
            relevant = scout.filter_relevant(alerts)
            return build_storm_geojson(relevant)
        except Exception as e:
            log.error(f"[map] storms fetch failed: {e}")
            return {"type": "FeatureCollection", "features": []}

    @app.get("/api/v1/map/targets")
    async def map_targets(limit: int = 300, auth: bool = Depends(require_auth)):
        try:
            db = get_db()
            r = (db.table("radar_targets")
                 .select("id,address,phone,status,meta,location")
                 .order("created_at", desc=True)
                 .limit(limit)
                 .execute())
            return build_target_geojson(r.data or [])
        except Exception as e:
            log.error(f"[map] targets fetch failed: {e}")
            return {"type": "FeatureCollection", "features": []}

    @app.get("/api/v1/map/config")
    async def map_config(auth: bool = Depends(require_auth)):
        import os
        return {
            "mapbox_token": os.environ.get("MAPBOX_TOKEN", ""),
            "style": "mapbox://styles/mapbox/dark-v11",
            "center": [-96.797, 32.776],  # Dallas
            "zoom": 8.5,
            "pitch": 45,
            "bearing": 0,
            "theme": {
                "storm_fill":   "rgba(0, 245, 255, 0.18)",
                "storm_stroke": "#00f5ff",
                "target_color": "#00ffae",
                "target_glow":  "rgba(0, 255, 174, 0.35)",
                "buildings_color": "#1a2438",
                "buildings_edge":  "#00f5ff",
            },
        }

    log.info("[map] Routes registered - /api/v1/map/{storms,targets,config}")
