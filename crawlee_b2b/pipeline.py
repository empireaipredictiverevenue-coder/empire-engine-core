"""
Crawlee B2B pipeline — stores crawled site content in Supabase site_content table.

One row per (b2b_lead_id, page_url). Idempotent — upserts on re-crawl.
Handles JSONB serialization for arrays/nested objects.
"""
import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

log = logging.getLogger("crawlee_b2b.pipeline")

_SUPABASE_CLIENT = None


def _get_sb():
    """Lazy-init Supabase client."""
    global _SUPABASE_CLIENT
    if _SUPABASE_CLIENT is None:
        try:
            from supabase import create_client
            from dotenv import load_dotenv
            load_dotenv("/root/.env")
            _SUPABASE_CLIENT = create_client(
                os.environ["SUPABASE_URL"],
                os.environ["SUPABASE_SERVICE_KEY"],
            )
        except Exception as e:
            log.error(f"Supabase init failed: {e}")
            return None
    return _SUPABASE_CLIENT


def store_pages(
    pages: List[dict],
    lead_id: str,
    company_name: str = "",
    website: str = "",
) -> dict:
    """Store crawled pages in site_content table. Idempotent (upserts on lead+page_url).

    Args:
        pages: List of page dicts from crawlee_b2b.site_scraper.crawl_site()
        lead_id: UUID from b2b_leads
        company_name: Business name
        website: Lead's main website URL

    Returns:
        dict: {stored: int, updated: int, errors: int}
    """
    sb = _get_sb()
    if not sb:
        return {"stored": 0, "updated": 0, "errors": len(pages)}

    stats = {"stored": 0, "updated": 0, "errors": 0}
    now = datetime.now(timezone.utc).isoformat()

    for page in (pages or []):
        try:
            row = {
                "b2b_lead_id": lead_id,
                "company_name": company_name or page.get("company_name", ""),
                "website": website or page.get("website", ""),
                "page_url": page.get("page_url", ""),
                "page_type": page.get("page_type", "homepage"),
                "title": page.get("title", ""),
                "meta_desc": page.get("meta_desc", ""),
                "headings": page.get("headings", []),  # Python list → JSONB
                "raw_text": page.get("raw_text", ""),
                "word_count": page.get("word_count", 0),
                "pricing_mentions": page.get("pricing_mentions", []),  # Python list → JSONB
                "cta_buttons": page.get("cta_buttons", []),  # Python list → JSONB
                "contact_info": page.get("contact_info", {}),  # Python dict → JSONB
                "crawl_status": "done",
                "updated_at": now,
            }

            if not row["page_url"]:
                stats["errors"] += 1
                continue

            # Upsert: if (b2b_lead_id, page_url) exists, update; else insert
            r = (
                sb.table("site_content")
                .upsert(row, on_conflict="b2b_lead_id,page_url")
                .execute()
            )
            stats["stored"] += 1
        except Exception as e:
            log.error(f"[pipeline] store failed for {page.get('page_url','?')[:60]}: {e}")
            stats["errors"] += 1

    return stats


def mark_failed(lead_id: str, website: str, error: str):
    """Record a crawl failure for a lead."""
    sb = _get_sb()
    if not sb:
        return
    try:
        sb.table("site_content").upsert(
            {
                "b2b_lead_id": lead_id,
                "website": website,
                "page_url": website,
                "page_type": "homepage",
                "crawl_status": "failed",
                "crawl_error": error[:500],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="b2b_lead_id,page_url",
        ).execute()
    except Exception as e:
        log.warning(f"[pipeline] mark_failed error: {e}")


def get_enrichment_stats() -> dict:
    """Return site_content table statistics."""
    sb = _get_sb()
    if not sb:
        return {}
    try:
        total = sb.table("site_content").select("id", count="exact").execute()
        by_type = sb.table("site_content").select("page_type", count="exact").execute()
        by_status = sb.table("site_content").select("crawl_status", count="exact").execute()

        from collections import Counter
        types = Counter(r.get("page_type") for r in (by_type.data or []))
        statuses = Counter(r.get("crawl_status") for r in (by_status.data or []))

        return {
            "total_pages": total.count,
            "by_page_type": dict(types),
            "by_status": dict(statuses),
        }
    except Exception as e:
        return {"error": str(e)}
