#!/usr/bin/env python3
"""
B2B Lead Enrichment Runner — Scrapy-based multi-source enrichment.

Orchestrates BBB, Yelp, and Google Business spiders against b2b_leads.
Loads leads from Supabase, runs spiders in sequence, reports results.

Usage:
    # Enrich ALL b2b_leads across all 3 sources:
    python3 scrapy_b2b/runner.py

    # Enrich a specific batch (e.g. first 50):
    python3 scrapy_b2b/runner.py --limit 50

    # Run a single source only:
    python3 scrapy_b2b/runner.py --source bbb --limit 25

    # Dry-run: show which leads would be enriched, don't actually scrape:
    python3 scrapy_b2b/runner.py --dry-run

    # Test with a single known lead:
    python3 scrapy_b2b/runner.py --lead-id <uuid>
"""
import os
import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv("/root/.env")

from supabase import create_client

log = logging.getLogger("scrapy_b2b.runner")

# Spider mapping: source → spider name
SPIDER_MAP = {
    "bbb": "bbb",
    "yelp": "yelp",
    "google_business": "google_business",
    "all": None,  # run all three in sequence
}


def load_leads(sb, limit: int = 0, lead_id: str = None) -> List[dict]:
    """Load leads from b2b_leads table.

    Priority: leads without enrichment (no meta.enrichments), then least-recently enriched.
    """
    query = sb.table("b2b_leads").select(
        "id,company_name,phone,address,city,state,website,niche,metro,meta,status"
    ).in_("status", ["new", "active"])

    if lead_id:
        query = query.eq("id", lead_id)
        r = query.limit(1).execute()
    else:
        # Order by created_at descending, newest first
        query = query.order("created_at", desc=True)
        if limit > 0:
            query = query.limit(limit)
        r = query.execute()

    leads = r.data or []
    log.info(f"Loaded {len(leads)} leads from b2b_leads")

    # Show enrichment status
    enriched = sum(1 for l in leads if l.get("meta") and isinstance(l.get("meta"), dict) and l["meta"].get("enrichments"))
    log.info(f"  Already enriched: {enriched}, Not yet enriched: {len(leads) - enriched}")

    return leads


def run_spider(source: str, lead_ids: List[str]) -> dict:
    """Run a single Scrapy spider as a subprocess (avoids reactor restart bug).

    Returns stats dict: {items_scraped, errors, spider_stats}.
    """
    # Run spider as subprocess to avoid Twisted ReactorNotRestartable
    import subprocess
    import tempfile

    # Write lead IDs to temp file (command line is too short for 775 UUIDs)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
        json.dump(lead_ids, tf)
        ids_file = tf.name

    try:
        result = subprocess.run(
            [sys.executable, "-m", "scrapy", "crawl", spider_name,
             "-a", f"lead_ids_file={ids_file}",
             "-s", f"FEED_URI=logs/scrapy_b2b_{source}.jl"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=None,  # no timeout — 775 leads × ~30s = ~6.5 hours per source
            env={**os.environ, "PYTHONPATH": str(REPO)},
        )
        if result.returncode != 0:
            log.error(f"Spider {source} exited with code {result.returncode}")
            if result.stderr:
                log.error(f"Stderr: {result.stderr[:500]}")

        # Read items scraped from feed export
        feed_path = f"logs/scrapy_b2b_{source}.jl"
        items_scraped = 0
        try:
            with open(feed_path) as f:
                items_scraped = sum(1 for line in f if line.strip())
        except FileNotFoundError:
            pass

        return {"source": source, "items_scraped": items_scraped, "lead_ids": lead_ids}
    finally:
        try:
            os.unlink(ids_file)
        except OSError:
            pass


def main():
    parser = argparse.ArgumentParser(description="B2B Lead Enrichment Runner")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max leads to enrich (0 = all)")
    parser.add_argument("--source", type=str, default="all",
                        choices=["all", "bbb", "yelp", "google_business"],
                        help="Which source to run (default: all — runs each as subprocess)")
    parser.add_argument("--lead-id", type=str, default=None,
                        help="Enrich a single lead by UUID")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show leads to process, don't actually scrape")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from last enriched lead (skip already-enriched)")
    args = parser.parse_args()

    # Ensure logs directory exists
    Path("logs").mkdir(exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("logs/scrapy_b2b_runner.log"),
        ],
    )

    # ── Camofox health check (required for BBB/Yelp/Google anti-bot) ──
    try:
        import httpx
        camofox_url = os.environ.get("CAMOFOX_URL", "http://localhost:9377")
        hc = httpx.get(f"{camofox_url}/health", timeout=httpx.Timeout(3.0))
        if hc.status_code < 400:
            log.info(f"camofox-browser healthy at {camofox_url}")
        else:
            log.warning(f"camofox-browser returned {hc.status_code} — scraping may fail")
    except Exception as e:
        log.warning(f"camofox-browser not reachable ({e}) — spiders will return zero results")
        log.warning(f"Start it with: camofox-browser server start --port 9377 --background")
        if not args.dry_run:
            log.error("Aborting: camofox-browser is required for production scraping.")
            log.error("  Use --dry-run to preview leads without camofox.")
            sys.exit(1)

    # ── Connect to Supabase ──
    try:
        sb = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_KEY"],
        )
    except Exception as e:
        log.error(f"Supabase connection failed: {e}")
        sys.exit(1)

    # ── Load leads ──
    leads = load_leads(sb, limit=args.limit, lead_id=args.lead_id)

    if not leads:
        log.warning("No leads to enrich.")
        return

    # ── Filter already-enriched if resuming ──
    if args.resume and not args.lead_id:
        skipped = 0
        fresh = []
        for lead in leads:
            meta = lead.get("meta") or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except json.JSONDecodeError:
                    meta = {}
            enrichments = meta.get("enrichments", {})
            # Skip if already has all sources we're running
            sources_to_run = list(SPIDER_MAP.keys())[:-1] if args.source == "all" else [args.source]
            if all(s in enrichments for s in sources_to_run):
                skipped += 1
                continue
            fresh.append(lead)
        log.info(f"Resume mode: skipped {skipped} already-enriched leads, "
                 f"{len(fresh)} remaining")
        leads = fresh

    if not leads:
        log.info("All leads already enriched. Done.")
        return

    # ── Dry run ──
    if args.dry_run:
        log.info(f"DRY RUN — would enrich {len(leads)} leads:")
        for i, lead in enumerate(leads[:10]):
            log.info(f"  {i+1}. {lead.get('company_name','')[:40]:42} "
                     f"{lead.get('city','')} {lead.get('state','')}")
        if len(leads) > 10:
            log.info(f"  ... and {len(leads) - 10} more")
        return

    # ── Determine sources to run ──
    if args.source == "all":
        sources = ["bbb", "yelp", "google_business"]
    else:
        sources = [args.source]

    # ── Run spiders (one subprocess per source — avoids Twisted reactor restart) ──
    lead_ids = [l["id"] for l in leads]
    total_stats = {s: {"leads_submitted": 0, "items_scraped": 0, "errors": 0} for s in sources}

    for source in sources:
        log.info(f"\n{'='*60}")
        log.info(f"Starting {source.upper()} spider — {len(lead_ids)} leads")
        log.info(f"Note: single-threaded with polite 4-7s delays ~ 6-10 leads/min")
        log.info(f"{'='*60}")

        try:
            result = run_spider(source, lead_ids)
            actually_scraped = result.get("items_scraped", 0)
            total_stats[source]["leads_submitted"] = len(lead_ids)
            total_stats[source]["items_scraped"] = actually_scraped
            log.info(f"[runner] {source}: {actually_scraped} items scraped "
                     f"from {len(lead_ids)} leads submitted")
        except Exception as e:
            log.error(f"[{source}] Spider failed: {e}")
            total_stats[source]["errors"] += 1
            import traceback
            traceback.print_exc()

    # ── Final report ──
    log.info(f"\n{'='*60}")
    log.info("ENRICHMENT COMPLETE")
    log.info(f"{'='*60}")
    for source, stats in total_stats.items():
        log.info(f"  {source:20s}  {stats['items_scraped']:>5d} scraped  "
                 f"{stats['leads_submitted']:>5d} submitted  "
                 f"{stats['errors']:>3d} errors")
    log.info(f"{'='*60}")

    # ── Verification query ──
    try:
        r = sb.table("b2b_leads").select("id", count="exact").execute()
        total = r.count
        r2 = sb.table("b2b_leads").select("id").not_.is_("meta", "null").execute()
        with_meta = len(r2.data or [])
        log.info(f"\nTable state: {total} total leads, {with_meta} with meta")
    except Exception as e:
        log.warning(f"Verification query failed: {e}")


if __name__ == "__main__":
    main()
