"""One-shot b2b scrape watchdog.

Runs every 30 min. Checks if Google Places quota is open (not 429), and if so,
fires the b2b_lead_scraper once. After the scrape completes, re-disables itself
in agent_config and exits.

This handles Phil's 'raise the cap, scrape once, turn it off' pattern without
him having to manually SSH and trigger.
"""
import sys, os
from datetime import datetime, timezone

# Configure path before imports
sys.path.insert(0, "/root/empire-v49")
os.chdir("/root/empire-v49")

# Sourced env should already have SUPABASE_URL etc. from the cron.sh wrapper
from supabase import create_client
import httpx

sb = create_client(os.environ["SUPABASE_URL"], os.getenv("SUPABASE_SERVICE_KEY"))

# 1. Check agent_config
r = sb.table("agent_config").select("*").eq("agent_name", "b2b_lead_scraper").limit(1).execute()
if not r.data:
    print("watchdog: no agent_config row for b2b_lead_scraper; exit")
    sys.exit(0)
cfg = r.data[0]
if not cfg.get("enabled"):
    print(f"watchdog: b2b_lead_scraper is disabled ({cfg.get('last_run_status', '?')}); exit")
    sys.exit(0)

# 2. Probe Google Places quota with a tiny text query
api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
if not api_key:
    print("watchdog: no GOOGLE_MAPS_API_KEY; exit")
    sys.exit(0)

url = "https://places.googleapis.com/v1/places:searchText"
headers = {
    "Content-Type": "application/json",
    "X-Goog-Api-Key": api_key,
    "X-Goog-FieldMask": "places.id,places.displayName",
}
body = {
    "textQuery": "test",
    "maxResultCount": 1,
}
try:
    r = httpx.post(url, headers=headers, json=body, timeout=10)
except Exception as e:
    print(f"watchdog: probe error: {e}; exit")
    sys.exit(0)

if r.status_code == 429:
    print(f"watchdog: Google quota still 429 — wait for reset. exit.")
    sys.exit(0)

if r.status_code != 200:
    print(f"watchdog: probe returned {r.status_code} (not quota-OK); exit")
    sys.exit(0)

print("watchdog: Google quota OPEN. firing b2b_lead_scraper...")

# 3. Fire the scraper (synchronous wrapper around the async run_async)
import asyncio
from bots.b2b_lead_scraper import run_async

os.environ["PLACES_DAILY_BUDGET"] = "2000"
try:
    result = asyncio.run(run_async())
    print(f"watchdog: scraper result: {result}")
except Exception as e:
    print(f"watchdog: scraper error: {e}")

# 4. Disable in agent_config so we don't refire
sb.table("agent_config").update({
    "enabled": False,
    "dry_run": True,
    "updated_at": datetime.now(timezone.utc).isoformat(),
}).eq("agent_name", "b2b_lead_scraper").execute()

print("watchdog: disabled b2b_lead_scraper; exit")
