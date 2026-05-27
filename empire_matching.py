import httpx
import os

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def find_best_lead_for_storm(storm_city: str):
    url = f"{SUPABASE_URL}/rest/v1/leads?city=eq.{storm_city}&status=eq.active&limit=1"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    
    with httpx.Client() as client:
        response = client.get(url, headers=headers)
        data = response.json()
        return data[0] if data else None
