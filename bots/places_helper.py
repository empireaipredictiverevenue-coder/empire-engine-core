"""
Empire AI · Places Helper
==========================
Google Places API wrapper for the prospector agent.
Searches for businesses by text query + location bias.
"""
import os
from typing import Any, Dict, List, Optional

import httpx


GOOGLE_KEY: Optional[str] = os.getenv("GOOGLE_MAPS_API_KEY")
GOOGLE_TEXT_URL: str = "https://places.googleapis.com/v1/places:searchText"


async def places_search(
    query: str,
    lat: float,
    lon: float,
    radius_m: int = 40000,
) -> List[Dict[str, Any]]:
    """Search Google Places for businesses matching a text query near a location.

    Args:
        query: Text search query (e.g. "roofing contractors in Wichita").
        lat: Latitude of the search center.
        lon: Longitude of the search center.
        radius_m: Search radius in meters (default 40km).

    Returns:
        List of normalized place dicts with name, address, phone, website,
        rating, review_count, business_status.
    """
    if not GOOGLE_KEY:
        print("[PROSPECT] No GOOGLE_MAPS_API_KEY")
        return []
    headers: Dict[str, str] = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_KEY,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.nationalPhoneNumber,places.websiteUri,places.rating,"
            "places.userRatingCount,places.businessStatus"
        ),
    }
    body: Dict[str, Any] = {
        "textQuery": query,
        "locationBias": {
            "circle": {
                "center": {"latitude": lat, "longitude": lon},
                "radius": radius_m,
            }
        },
        "maxResultCount": 20,
    }
    out: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.post(GOOGLE_TEXT_URL, headers=headers, json=body)
            r.raise_for_status()
            for p in r.json().get("places", []):
                out.append({
                    "name": p.get("displayName", {}).get("text"),
                    "address": p.get("formattedAddress"),
                    "phone": p.get("nationalPhoneNumber"),
                    "website": p.get("websiteUri"),
                    "rating": p.get("rating"),
                    "review_count": p.get("userRatingCount"),
                    "business_status": p.get("businessStatus"),
                })
        except httpx.HTTPError as e:
            print(f"[PROSPECT] Places error: {e}")
    return out
