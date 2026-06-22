"""
Scrapy pipeline: write enriched B2B data to the b2b_leads table in Supabase.

Each B2BBusinessItem is upserted into b2b_leads.meta as a source-specific
enrichment blob, and top-level rating/review_count fields are updated.
"""
import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

log = logging.getLogger("scrapy_b2b.pipeline")

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


class B2BEnrichmentPipeline:
    """Store enriched business data in b2b_leads.meta enrichment blob."""

    def __init__(self):
        self.stats = {"bbb": 0, "yelp": 0, "google_business": 0, "errors": 0}
        self._seen = set()  # dedup by (b2b_lead_id, source)

    def process_item(self, item, spider):
        sb = _get_sb()
        if not sb:
            self.stats["errors"] += 1
            return item

        lead_id = item.get("b2b_lead_id")
        source = item.get("source", "unknown")
        dedup_key = (lead_id, source)

        if dedup_key in self._seen:
            spider.logger.debug(f"Skipping duplicate: {dedup_key}")
            return item
        self._seen.add(dedup_key)

        if not lead_id:
            spider.logger.warning(f"No b2b_lead_id for {source} item, skipping")
            self.stats["errors"] += 1
            return item

        # Build enrichment blob
        enrichment = {
            "source": source,
            "profile_url": item.get("profile_url"),
            "rating": item.get("rating"),
            "review_count": item.get("review_count"),
            "categories": item.get("categories"),
            "accreditation": item.get("accreditation"),
            "price_level": item.get("price_level"),
            "hours": item.get("hours"),
            "phone_on_profile": item.get("phone_on_profile"),
            "address_on_profile": item.get("address_on_profile"),
            "website_on_profile": item.get("website_on_profile"),
            "claimed": item.get("claimed"),
            "photos_count": item.get("photos_count"),
            "match_confidence": item.get("match_confidence"),
            "match_reason": item.get("match_reason"),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }
        # Remove None values
        enrichment = {k: v for k, v in enrichment.items() if v is not None}

        try:
            # Fetch existing meta to merge (avoid overwriting other sources)
            existing = sb.table("b2b_leads").select("meta").eq("id", lead_id).limit(1).execute()
            current_meta = {}
            if existing.data:
                current_meta = existing.data[0].get("meta") or {}
                if isinstance(current_meta, str):
                    try:
                        current_meta = json.loads(current_meta)
                    except json.JSONDecodeError:
                        current_meta = {}

            # Merge: store enrichment under meta.enrichments.<source>
            if "enrichments" not in current_meta:
                current_meta["enrichments"] = {}
            current_meta["enrichments"][source] = enrichment
            current_meta["last_enriched_at"] = datetime.now(timezone.utc).isoformat()

            # Update meta blob only — don't overwrite lead_score (set during import)
            # Directory rating is stored in meta.enrichments.<source>.rating
            updates = {"meta": current_meta, "updated_at": datetime.now(timezone.utc).isoformat()}

            sb.table("b2b_leads").update(updates).eq("id", lead_id).execute()

            self.stats[source] = self.stats.get(source, 0) + 1
            spider.logger.info(
                f"[pipeline] {source} enriched {lead_id[:8]}... "
                f"rating={item.get('rating')} reviews={item.get('review_count')} "
                f"confidence={item.get('match_confidence')}"
            )
        except Exception as e:
            self.stats["errors"] += 1
            spider.logger.error(f"[pipeline] update failed for {lead_id[:8]} ({source}): {e}")

        return item

    def close_spider(self, spider):
        spider.logger.info(f"[pipeline] Stats: {json.dumps(self.stats)}")
