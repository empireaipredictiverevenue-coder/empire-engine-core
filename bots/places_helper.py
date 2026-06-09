import os, httpx

GOOGLE_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
GOOGLE_TEXT_URL = "https://places.googleapis.com/v1/places:searchText"

async def places_search(query, lat, lon, radius_m=40000):
    if not GOOGLE_KEY:
        print("[PROSPECT] No GOOGLE_MAPS_API_KEY")
        return []
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_KEY,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.websiteUri,places.rating,places.userRatingCount,places.businessStatus",
    }
    body = {
        "textQuery": query,
        "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lon}, "radius": radius_m}},
        "maxResultCount": 20,
    }
    out = []
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
