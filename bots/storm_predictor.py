import os, time, json
from datetime import datetime, timezone
from dotenv import load_dotenv
import httpx
from supabase import create_client
import json

load_dotenv("/root/.env")
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

BASE = "https://mapservices.weather.noaa.gov/vector/rest/services/outlooks/SPC_wx_outlks/MapServer"
# Day1 categorical=1, Day2=9, Day3=17 (group layer offsets)
DAY_LAYERS = {1: 1, 2: 9, 3: 17}

RISK = {2:"Thunderstorm",3:"Marginal",4:"Slight",5:"Enhanced",6:"Moderate",8:"High"}
RISK_RANK = {2:1,3:2,4:3,5:4,6:5,8:6}

# Target metro centroids (lat, lon)
METROS = {
    "Dallas-Fort Worth": (32.78, -96.80),
    "Houston": (29.76, -95.37),
    "Austin": (30.27, -97.74),
    "San Antonio": (29.42, -98.49),
    "Wichita": (37.69, -97.34),
    "Oklahoma City": (35.47, -97.52),
    "Kansas City": (39.10, -94.58),
    "New Orleans": (29.95, -90.07),
    "Memphis": (35.15, -90.05),
    "Atlanta": (33.75, -84.39),
    "Nashville": (36.16, -86.78),
    # ── I-35 Corridor / Texas ──
    "Waco": (31.55, -97.15),
    "Temple": (31.10, -97.34),
    "Bryan/College Station": (30.63, -96.33),
    "Tyler": (32.35, -95.30),
    "Lubbock": (33.58, -101.85),
    "Amarillo": (35.20, -101.83),
    "El Paso": (31.76, -106.49),
    "Corpus Christi": (27.80, -97.40),
    # ── I-35 Fill-ins ──
    "San Marcos": (29.88, -97.94),
    "New Braunfels": (29.70, -98.12),
    "Round Rock": (30.51, -97.67),
    "Georgetown": (30.63, -97.68),
    "Killeen": (31.12, -97.73),
    "Denton": (33.21, -97.13),
    "Sherman": (33.63, -96.61),
    # ── Rio Grande Valley ──
    "McAllen": (26.20, -98.24),
    "Brownsville": (25.93, -97.48),
    "Laredo": (27.50, -99.50),
    # ── Louisiana ──
    "Shreveport": (32.52, -93.75),
    "Lafayette LA": (30.22, -92.02),
}

import math

def haversine_miles(lat1, lon1, lat2, lon2):
    R = 3959
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def min_dist_to_ring(lat, lon, ring):
    return min(haversine_miles(lat, lon, c[1], c[0]) for c in ring)

def point_in_ring(pt, ring):
    x, y = pt
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside

def fetch_layer(layer_id):
    url = f"{BASE}/{layer_id}/query"
    params = {"where":"1=1","outFields":"dn,valid,label","returnGeometry":"true","f":"geojson"}
    try:
        r = httpx.get(url, params=params, timeout=30)
        r.raise_for_status()
        return r.json().get("features", [])
    except Exception as e:
        print(f"[PREDICT] layer {layer_id} fetch error: {e}")
        return []

def assess():
    forecasts = []
    for day, layer in DAY_LAYERS.items():
        feats = fetch_layer(layer)
        for metro, (lat, lon) in METROS.items():
            best_risk = 0
            for f in feats:
                props = f.get("properties", {})
                dn = props.get("dn")
                if dn not in RISK: continue
                geom = f.get("geometry", {})
                rings = []
                if geom.get("type") == "Polygon":
                    rings = geom.get("coordinates", [])
                elif geom.get("type") == "MultiPolygon":
                    for poly in geom.get("coordinates", []):
                        rings.extend(poly)
                for ring in rings:
                    inside = point_in_ring((lon, lat), ring)
                    near = (not inside) and min_dist_to_ring(lat, lon, ring) <= 100
                    if inside or near:
                        if RISK_RANK.get(dn,0) > RISK_RANK.get(best_risk,0):
                            best_risk = dn
                        break
            if best_risk >= 4:  # Slight or higher
                forecasts.append({
                    "metro": metro, "day": day,
                    "risk_level": RISK[best_risk],
                    "risk_rank": RISK_RANK[best_risk],
                    "lat": lat, "lon": lon
                })
                print(f"[PREDICT] Day {day}: {metro} = {RISK[best_risk]} risk")
    return forecasts

def save_forecasts(forecasts):
    try:
        sb.table("storm_forecasts").upsert({
            "id": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "forecasts": json.dumps(forecasts),
            "count": len(forecasts)
        }, on_conflict="id").execute()
    except Exception as e:
        print(f"[PREDICT] save error: {e}")

def heartbeat(count):
    try:
        sb.table("agent_registry").upsert({
            "agent_name": "predictor",
            "role_name": "storm_predictor",
            "status": "ACTIVE",
            "leads_today": count,
            "last_ping": datetime.now(timezone.utc).isoformat(),
            "enabled": True,
            "capabilities": json.dumps(["storm_scan", "geo_analyze", "find_targets"]),
            "task_types": json.dumps(["scout.storm_scan", "scout.find_roofs"]),
        }, on_conflict="agent_name").execute()
    except Exception as e:
        print(f"[PREDICT] heartbeat error: {e}")

def run():
    print("[PREDICT] Storm Predictor (Warp Scout) starting...")
    while True:
        try:
            forecasts = assess()
            save_forecasts(forecasts)
            heartbeat(len(forecasts))
            print(f"[PREDICT] Cycle done. {len(forecasts)} metro-risk forecasts.")
        except Exception as e:
            print(f"[PREDICT] Loop error: {e}")
        time.sleep(3600)  # hourly

if __name__ == "__main__":
    run()
