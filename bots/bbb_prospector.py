"""
BBB-driven prospector — runs bbb_search across multiple metros + niches
and saves real businesses to the `prospects` table.

Unlike bots/prospector.py (which used Google Places via API and BBB /category
pages — both broken now), this uses bbb_search to hit /search and extract
profile links to actual contractor businesses.

CLI:
    python3 bots/bbb_prospector.py                       # default 5 metros × 5 niches
    python3 bots/bbb_prospector.py --metros 10 --niches 7
    python3 bots/bbb_prospector.py --niche roofing --metro "Dallas-Fort Worth" --max 15
"""
import os
import sys
import json
import asyncio
import argparse
import logging
from pathlib import Path
from typing import List, Dict

REPO = Path("/root/empire-v49")
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv("/root/.env")

from config.metros import METROS
from bots.bbb_search import search_niche, NICHE_TO_BBB_CATEGORY
from supabase import create_client

log = logging.getLogger("bbb_prospector")

DEFAULT_NICHES = ["roofing", "hvac", "restoration", "general contractor", "solar"]
DEFAULT_METROS = [
    "Dallas-Fort Worth", "Houston", "San Antonio", "Austin",
    "Miami", "Tampa", "Orlando", "Atlanta", "Nashville", "Charlotte",
]


async def run(niches: List[str], metros: List[str], max_per: int, deep_scrape: bool) -> Dict:
    sb = create_client(os.environ["SUPABASE_URL"], os.getenv("SUPABASE_SERVICE_KEY"))

    total_found = 0
    total_saved = 0
    by_metro: Dict[str, int] = {}
    by_niche: Dict[str, int] = {}

    for metro in metros:
        if metro not in METROS:
            log.warning(f"[bbb-prospector] unknown metro: {metro}; skipping")
            continue
        for niche in niches:
            log.info(f"[bbb-prospector] {niche} × {metro}")
            try:
                results = await search_niche(niche, metro, max_profiles=max_per, deep_scrape=deep_scrape)
            except Exception as e:
                log.warning(f"[bbb-prospector] search failed for {niche}/{metro}: {e}")
                results = []

            total_found += len(results)
            by_metro[metro] = by_metro.get(metro, 0) + len(results)
            by_niche[niche] = by_niche.get(niche, 0) + len(results)

            # Save to prospects
            for r in results:
                name = r.get("name", "").strip()
                if not name or len(name) < 4:
                    continue
                # Skip obviously non-business "names" (BBB category labels leak sometimes)
                low = name.lower()
                if any(bad in low for bad in ["contractor", "near you", "in your area", "showing", "results for"]):
                    # Only skip if the name is JUST a category label (no real business)
                    parts = name.split()
                    if len(parts) <= 2:
                        continue
                url = r.get("url", "")
                row = {
                    "business_name": name[:120],
                    "niche": niche,
                    "metro": metro,
                    "phone": r.get("phone"),
                    "website": r.get("website") or url,
                    "address": r.get("address"),
                    "rating": None,
                    "review_count": None,
                    "buy_signal_score": 0,
                    "status": "new",
                    "notes": f"source=bbb-search; url={url}",
                }
                try:
                    sb.table("prospects").insert(row).execute()
                    total_saved += 1
                except Exception as e:
                    log.warning(f"[bbb-prospector] save failed for {name}: {str(e)[:100]}")
            log.info(f"  -> {len(results)} found")

    return {
        "total_found": total_found,
        "total_saved": total_saved,
        "by_metro": by_metro,
        "by_niche": by_niche,
    }


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--metros", type=int, default=None, help="number of metros")
    p.add_argument("--niches", type=int, default=None, help="number of niches")
    p.add_argument("--max", type=int, default=10, help="max profiles per niche×metro")
    p.add_argument("--shallow", action="store_true", help="skip profile deep-scrape")
    p.add_argument("--niche", type=str, help="single niche (overrides --niches)")
    p.add_argument("--metro", type=str, help="single metro (overrides --metros)")
    args = p.parse_args()

    if args.niche:
        niches = [args.niche]
    else:
        niches = DEFAULT_NICHES[:args.niches] if args.niches else DEFAULT_NICHES
    if args.metro:
        metros = [args.metro]
    else:
        metros = DEFAULT_METROS[:args.metros] if args.metros else DEFAULT_METROS

    summary = asyncio.run(run(niches, metros, args.max, not args.shallow))
    print("\n=== BBB PROSPECTOR SUMMARY ===")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()