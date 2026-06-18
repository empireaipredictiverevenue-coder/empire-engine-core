"""
Empire AI · B2B Lead Scraper (Apify Version)
==========================================
Replaces Google Places with Apify Google Maps Scraper.

Ready for switch on July 10th 2026.

Usage:
    python3 b2b_lead_scraper_apify.py --niches "Commercial Roofing,Solar" --metros "Dallas,Fort Worth"

Requires:
    - APIFY_API_TOKEN in .env
    - SUPABASE_URL + SUPABASE_SERVICE_KEY in .env
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from supabase import create_client
import httpx

log = logging.getLogger("empire.b2b_apify")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

# ── CONFIG ──────────────────────────────────────────────────────────────
APIFY_TOKEN = os.getenv("APIFY_API_TOKEN")
APIFY_ACTOR_ID = "compass~google-maps-scraper"   # Most popular & reliable
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

NICHES = [
    "Managed IT", "Merchant Services", "HR & Staffing",
    "Commercial Roofing", "Commercial Solar", "Debt Relief",
    "HVAC", "Plumbing", "Electrical", "Landscaping",
    "Pest Control", "Security Systems", "Janitorial",
    "Signage", "Printing", "Office Furniture", "IT Support",
    "Cloud Services", "Cybersecurity", "VoIP", "POS Systems",
    "Payroll Services", "Accounting", "Legal Services",
    "Marketing Agencies", "Web Design", "SEO Agencies",
    "Insurance Agencies", "Financial Advisors", "Real Estate"
]

DEFAULT_METROS = ["Dallas", "Fort Worth", "Houston", "Austin", "San Antonio", "Oklahoma City"]

sb = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None


def get_apify_run(niche: str, metro: str, max_results: int = 50) -> Dict:
    """Start an Apify actor run for Google Maps search."""
    url = f"https://api.apify.com/v2/acts/{APIFY_ACTOR_ID}/runs"
    payload = {
        "searchString": f"{niche} in {metro}",
        "maxResults": max_results,
        "language": "en",
        "countryCode": "US",
    }
    headers = {"Authorization": f"Bearer {APIFY_TOKEN}"}

    resp = httpx.post(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()["data"]


def wait_for_run(run_id: str) -> Dict:
    """Poll until the Apify run finishes."""
    url = f"https://api.apify.com/v2/actor-runs/{run_id}"
    headers = {"Authorization": f"Bearer {APIFY_TOKEN}"}

    while True:
        resp = httpx.get(url, headers=headers, timeout=30)
        data = resp.json()["data"]
        if data["status"] in ["SUCCEEDED", "FAILED", "ABORTED"]:
            return data
        import time
        time.sleep(8)


def get_dataset_items(dataset_id: str) -> List[Dict]:
    url = f"https://api.apify.com/v2/datasets/{dataset_id}/items"
    resp = httpx.get(url, timeout=60)
    return resp.json()


def normalize_place(place: Dict, niche: str, metro: str) -> Optional[Dict]:
    """Convert Apify result into radar_targets format."""
    if not place.get("title") or not place.get("address"):
        return None

    return {
        "address": place.get("address"),
        "city": metro,
        "state": "TX" if metro in ["Dallas", "Fort Worth", "Houston", "Austin", "San Antonio"] else "OK",
        "phone": place.get("phone"),
        "email": place.get("email"),
        "website": place.get("website"),
        "niche": niche,
        "sub_niche": niche,
        "source": "apify_google_maps",
        "status": "active",
        "meta": {
            "place_id": place.get("placeId"),
            "rating": place.get("rating"),
            "review_count": place.get("reviewCount"),
            "categories": place.get("categories", []),
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def insert_to_supabase(records: List[Dict]):
    if not sb or not records:
        return 0
    try:
        sb.table("radar_targets").insert(records).execute()
        return len(records)
    except Exception as e:
        log.error(f"Supabase insert error: {e}")
        return 0


def run(niches: List[str] = None, metros: List[str] = None, max_results: int = 40):
    niches = niches or NICHES
    metros = metros or DEFAULT_METROS

    total_inserted = 0

    for niche in niches:
        for metro in metros:
            log.info(f"Scraping: {niche} in {metro}")
            try:
                run_data = get_apify_run(niche, metro, max_results)
                run_id = run_data["id"]
                final = wait_for_run(run_id)

                if final["status"] != "SUCCEEDED":
                    log.warning(f"Apify run failed: {final[status]}")
                    continue

                dataset_id = final["defaultDatasetId"]
                items = get_dataset_items(dataset_id)

                records = []
                for item in items:
                    rec = normalize_place(item, niche, metro)
                    if rec:
                        records.append(rec)

                inserted = insert_to_supabase(records)
                total_inserted += inserted
                log.info(f"Inserted {inserted} leads for {niche} in {metro}")

            except Exception as e:
                log.error(f"Error on {niche} in {metro}: {e}")
                continue

    log.info(f"Total leads inserted via Apify: {total_inserted}")
    return total_inserted


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--niches", type=str, help="Comma separated niches")
    parser.add_argument("--metros", type=str, help="Comma separated metros")
    parser.add_argument("--max", type=int, default=40)
    args = parser.parse_args()

    niches = args.niches.split(",") if args.niches else None
    metros = args.metros.split(",") if args.metros else None

    run(niches=niches, metros=metros, max_results=args.max)
