#!/usr/bin/env python3
"""
Crawlee B2B Website Scraper Runner — feeds STORM copywriting engine.

Crawls B2B lead websites using Crawlee's PlaywrightCrawler, extracts clean
text from service pages, pricing, and contact forms, and stores in Supabase
site_content table for the STORM copywriting engine.

Usage:
    # Crawl ALL 775 b2b_leads with websites:
    python3 crawlee_b2b/runner.py

    # Crawl a specific batch:
    python3 crawlee_b2b/runner.py --limit 25 --batch 1  # batch 1 of N

    # Crawl a single lead by UUID:
    python3 crawlee_b2b/runner.py --lead-id <uuid>

    # Dry-run: show which leads would be crawled:
    python3 crawlee_b2b/runner.py --dry-run --limit 10

    # Resume from last crawled lead:
    python3 crawlee_b2b/runner.py --resume

Speed: ~15-30s per site (3 pages × 5-10s each). 775 leads = ~4-6 hours.
"""
import os
import sys
import json
import asyncio
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

log = logging.getLogger("crawlee_b2b.runner")


def load_leads(sb, limit: int = 0, lead_id: str = None, resume: bool = False) -> List[dict]:
    """Load B2B leads with websites, optionally skipping ones already crawled."""
    query = sb.table("b2b_leads").select(
        "id,company_name,website,niche,metro,status"
    ).not_.is_("website", "null").in_("status", ["new", "active"])

    if lead_id:
        query = query.eq("id", lead_id)
        r = query.limit(1).execute()
    else:
        query = query.order("created_at", desc=True)
        if limit > 0:
            query = query.limit(limit)
        r = query.execute()

    leads = r.data or []
    log.info(f"Loaded {len(leads)} leads with websites")

    if resume:
        # Check which leads already have site_content
        try:
            crawled = sb.table("site_content").select("b2b_lead_id").eq("crawl_status", "done").execute()
            crawled_ids = {r["b2b_lead_id"] for r in (crawled.data or [])}
            skipped = sum(1 for l in leads if l["id"] in crawled_ids)
            leads = [l for l in leads if l["id"] not in crawled_ids]
            log.info(f"Resume mode: skipped {skipped} already crawled, {len(leads)} remaining")
        except Exception as e:
            log.warning(f"Resume check failed: {e}")

    return leads


async def crawl_one_lead(sb, lead: dict) -> dict:
    """Crawl a single lead's website and store results."""
    from crawlee_b2b.site_scraper import crawl_site
    from crawlee_b2b.pipeline import store_pages, mark_failed

    lead_id = lead["id"]
    website = (lead.get("website") or "").strip()
    company = (lead.get("company_name") or "")[:120]

    if not website:
        return {"lead_id": lead_id, "status": "skipped", "reason": "no website"}

    log.info(f"[{company[:40]}] Crawling: {website[:80]}")

    try:
        pages = await crawl_site(
            website=website,
            lead_id=lead_id,
            company_name=company,
            max_pages=3,
            max_concurrency=1,
        )

        if not pages:
            mark_failed(lead_id, website, "no pages extracted")
            return {"lead_id": lead_id, "status": "no_pages", "website": website}

        stats = store_pages(pages, lead_id, company, website)
        log.info(f"  → {stats['stored']} pages stored "
                 f"(types: {[p.get('page_type','?') for p in pages]})")
        return {
            "lead_id": lead_id,
            "status": "done",
            "website": website,
            "pages_stored": stats["stored"],
        }

    except Exception as e:
        log.warning(f"[{company[:40]}] Crawl error: {e}")
        mark_failed(lead_id, website, str(e)[:500])
        return {"lead_id": lead_id, "status": "error", "website": website, "error": str(e)[:200]}


async def main_async(args):
    """Async main — crawl all leads sequentially."""
    from crawlee_b2b.pipeline import get_enrichment_stats

    # ── Connect Supabase ──
    try:
        sb = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_KEY"],
        )
    except Exception as e:
        log.error(f"Supabase connect error: {e}")
        sys.exit(1)

    # ── Show enrichment stats ──
    stats = get_enrichment_stats()
    if stats:
        log.info(f"site_content: {stats}")

    # ── Load leads ──
    leads = load_leads(sb, limit=args.limit, lead_id=args.lead_id, resume=args.resume)
    if not leads:
        log.warning("No leads to crawl.")
        return

    # ── Dry run ──
    if args.dry_run:
        log.info(f"DRY RUN — would crawl {len(leads)} websites:")
        for i, lead in enumerate(leads[:15]):
            log.info(f"  {i+1}. {lead.get('company_name','')[:40]:42} "
                     f"{lead.get('website','')[:60]}")
        if len(leads) > 15:
            log.info(f"  ... and {len(leads) - 15} more")
        log.info(f"\nEst. duration: {len(leads) * 20 // 60} min "
                 f"(~20s per site × 3 pages)")
        return

    # ── Crawl sequentially ──
    total = {"done": 0, "no_pages": 0, "error": 0, "skipped": 0}
    started_at = datetime.now(timezone.utc)

    for i, lead in enumerate(leads):
        log.info(f"\n[{i+1}/{len(leads)}] {lead.get('company_name','?')[:50]}")

        try:
            result = await asyncio.wait_for(
                crawl_one_lead(sb, lead), timeout=90
            )
            total[result.get("status", "error")] += 1
        except asyncio.TimeoutError:
            log.warning(f"  Timeout after 90s — skipping")
            total["timeout"] = total.get("timeout", 0) + 1

        # Small delay between sites (politeness)
        if i < len(leads) - 1:
            await asyncio.sleep(1)

    # ── Final report ──
    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
    log.info(f"\n{'='*60}")
    log.info(f"WEBSITE CRAWL COMPLETE — {elapsed:.0f}s ({elapsed/60:.1f} min)")
    log.info(f"{'='*60}")
    for status, count in total.items():
        log.info(f"  {status:15s}  {count:>5d}")
    log.info(f"{'='*60}")

    # ── Enrichment stats ──
    stats = get_enrichment_stats()
    if stats:
        log.info(f"\nsite_content table: {json.dumps(stats, indent=2)}")


def main():
    parser = argparse.ArgumentParser(
        description="Crawlee B2B Website Scraper — feeds STORM copywriting engine"
    )
    parser.add_argument("--limit", type=int, default=0,
                        help="Max leads to crawl (0 = all 775)")
    parser.add_argument("--lead-id", type=str, default=None,
                        help="Crawl a single lead by UUID")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show leads to crawl, don't actually scrape")
    parser.add_argument("--resume", action="store_true",
                        help="Skip leads that already have site_content")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("logs/crawlee_b2b.log"),
        ],
    )

    # Ensure logs dir
    Path("logs").mkdir(exist_ok=True)

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
