"""
Google Business Profile spider — search by company name + phone + city.

Uses Google Maps search (not the Places API — API-free scraping).
This is the hardest source due to Google's anti-bot defenses.

Strategy:
  1. Search maps.google.com by company name + address
  2. Extract the business profile link from search results
  3. Visit the profile and extract rating/reviews/categories/hours

Because Google Maps is heavily JS-rendered, this spider uses a hybrid approach:
  - First tries direct HTTP scraping (may work for static SSR content)
  - Falls back gracefully; camofox-browser path available in bots/

For production use, consider Google Places API (requires API key) or the
camofox-browser based scraper (bots/bbb_search.py pattern adapted for Maps).
"""
import re
import json
from typing import Optional
from urllib.parse import quote_plus

import scrapy
from scrapy_b2b.items import B2BBusinessItem


class GoogleBusinessSpider(scrapy.Spider):
    name = "google_business"
    allowed_domains = [
        "google.com", "www.google.com",
        "maps.google.com",
        "business.google.com",
    ]

    custom_settings = {
        "DOWNLOAD_DELAY": 7,
        "AUTOTHROTTLE_START_DELAY": 7,
        "AUTOTHROTTLE_MAX_DELAY": 30,
    }

    def __init__(self, lead_ids_json: str = "[]", lead_ids_file: str = "", *args, **kwargs):
        super().__init__(*args, **kwargs)
        if lead_ids_file:
            with open(lead_ids_file) as f:
                self.lead_ids = json.load(f)
        else:
            self.lead_ids = json.loads(lead_ids_json)
        self._leads_cache: dict = {}

    def start_requests(self):
        sb = self._get_sb()
        if not sb:
            return

        for lead_id in self.lead_ids:
            lead = self._fetch_lead(sb, lead_id)
            if not lead:
                continue

            company = (lead.get("company_name") or "").strip()
            city = (lead.get("city") or "").strip()
            state = (lead.get("state") or "").strip()
            address = (lead.get("address") or "").strip()
            phone = (lead.get("phone") or "").strip()

            if not company:
                continue

            # Google search: "Company Name City State" site:business.google.com
            # This finds Google Business Profile pages indexed by Google
            search_query = f'"{company}" "{city}" "{state}" site:google.com/maps'
            search_url = (
                f"https://www.google.com/search?"
                f"q={quote_plus(search_query)}&"
                f"num=5"
            )

            yield scrapy.Request(
                url=search_url,
                callback=self.parse_google_search,
                meta={
                    "lead_id": lead_id,
                    "lead": lead,
                    "search_url": search_url,
                },
                dont_filter=True,
                errback=self._handle_error,
            )

    def parse_google_search(self, response):
        """Parse Google search results for a Google Maps business listing."""
        lead = response.meta["lead"]
        lead_id = response.meta["lead_id"]
        text = response.text

        # Extract Google Maps place URLs from search results
        # Format: https://www.google.com/maps/place/... or /maps/place/...
        maps_urls = re.findall(
            r'(?:https?://(?:www\.)?google\.com)?(/maps/place/[^"&\s]+)',
            text,
        )
        if not maps_urls:
            # Also try the "knowledge panel" embedded data
            maps_urls = re.findall(
                r'https://www\.google\.com/maps/place/[^"&\s]+',
                text,
            )

        if not maps_urls:
            self.logger.info(
                f"[google] No Maps listing for {lead.get('company_name','')[:40]}"
            )
            return

        maps_path = maps_urls[0]
        if not maps_path.startswith("http"):
            maps_url = f"https://www.google.com{maps_path}"
        else:
            maps_url = maps_path

        yield scrapy.Request(
            url=maps_url,
            callback=self.parse_maps_listing,
            meta={
                "lead_id": lead_id,
                "lead": lead,
                "profile_url": maps_url,
            },
            dont_filter=True,
            errback=self._handle_error,
        )

    def parse_maps_listing(self, response):
        """Parse a Google Maps business listing page."""
        lead = response.meta["lead"]
        lead_id = response.meta["lead_id"]
        profile_url = response.meta["profile_url"]
        text = response.text

        # ── Rating ──
        rating = None
        rating_match = re.search(
            r'(?:ratingValue|rating)[:\s"]+(\d+(?:\.\d+)?)',
            text, re.IGNORECASE,
        )
        if not rating_match:
            rating_match = re.search(
                r'aria-label="(\d+(?:\.\d+)?)\s+stars?',
                text,
            )
        if rating_match:
            try:
                rating = float(rating_match.group(1))
            except ValueError:
                pass

        # ── Review count ──
        review_count = None
        review_match = re.search(
            r'(\d[\d,]*)\s+(?:Google\s+)?reviews?',
            text, re.IGNORECASE,
        )
        if review_match:
            review_count = int(review_match.group(1).replace(",", ""))

        # ── Categories ──
        categories = []
        cat_matches = re.findall(
            r'(?:category|categories?)[:\s"]+([A-Z][A-Za-z\s&/-]{3,40})',
            text,
        )
        for cat in cat_matches:
            cat = cat.strip()
            if cat and len(cat) > 3:
                categories.append(cat)

        # ── Hours ──
        hours = None
        hours_match = re.search(
            r'(?:openingHours|hours)[:\s"]+([^"]{10,200})',
            text, re.IGNORECASE,
        )
        if hours_match:
            hours = hours_match.group(1).strip()

        # ── Phone from profile ──
        phone_on_profile = None
        tel_match = re.search(
            r'(?:tel:|phone[:\s"]+)(\+?1?\s*\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4})',
            text, re.IGNORECASE,
        )
        if tel_match:
            phone_on_profile = re.sub(r"\D", "", tel_match.group(1))

        # ── Address from profile ──
        address_on_profile = None
        addr_match = re.search(
            r'"streetAddress"\s*:\s*"([^"]+)"',
            text,
        )
        if not addr_match:
            addr_match = re.search(
                r'(\d{1,5}\s+[A-Z][a-zA-Z\s\.]+(?:St|Ave|Blvd|Rd|Dr|Ln|Way|Ct)[^,]{5,60})',
                text,
            )
        if addr_match:
            address_on_profile = addr_match.group(1).strip()

        # ── Photos count ──
        photos_count = None
        photos_match = re.search(r'(\d+)\s+photos?', text, re.IGNORECASE)
        if photos_match:
            photos_count = int(photos_match.group(1))

        # ── Price level ──
        price_level = None
        price_match = re.search(
            r'(?:priceLevel|price_range)[:\s"]+(\d)',
            text, re.IGNORECASE,
        )
        if price_match:
            price_map = {"1": "$", "2": "$$", "3": "$$$", "4": "$$$$"}
            price_level = price_map.get(price_match.group(1))

        # ── Match confidence ──
        match_confidence, match_reason = self._compute_confidence(
            lead, phone_on_profile, address_on_profile,
        )

        yield B2BBusinessItem(
            b2b_lead_id=lead_id,
            company_name=lead.get("company_name", ""),
            search_phone=lead.get("phone", ""),
            search_website=lead.get("website", ""),
            source="google_business",
            profile_url=profile_url,
            rating=rating,
            review_count=review_count,
            categories=categories if categories else None,
            price_level=price_level,
            hours=hours,
            phone_on_profile=phone_on_profile,
            address_on_profile=address_on_profile,
            photos_count=photos_count,
            claimed=None,  # Google doesn't expose this reliably
            match_confidence=match_confidence,
            match_reason=match_reason,
            scraped_at=None,
        )

    def _compute_confidence(self, lead, profile_phone, profile_addr):
        score = 0
        reasons = []

        lead_phone = re.sub(r"\D", "", lead.get("phone", "") or "")
        if lead_phone and profile_phone and lead_phone[-10:] == profile_phone[-10:]:
            score += 4
            reasons.append("phone_match")

        lead_addr = (lead.get("address", "") or "").lower().split(",")[0].strip()
        p_addr = (profile_addr or "").lower().split(",")[0].strip()
        if lead_addr and p_addr and lead_addr[:15] == p_addr[:15]:
            score += 3
            reasons.append("address_match")

        if score >= 4:
            return "high", ",".join(reasons)
        elif score >= 2:
            return "medium", ",".join(reasons)
        else:
            return "low", ",".join(reasons)

    def _fetch_lead(self, sb, lead_id):
        if lead_id in self._leads_cache:
            return self._leads_cache[lead_id]
        try:
            r = sb.table("b2b_leads").select(
                "id,company_name,phone,address,city,state,website,niche,metro"
            ).eq("id", lead_id).limit(1).execute()
            if r.data:
                self._leads_cache[lead_id] = r.data[0]
                return r.data[0]
        except Exception as e:
            self.logger.error(f"Fetch lead failed {lead_id}: {e}")
        return None

    def _get_sb(self):
        if not hasattr(self, "_sb"):
            try:
                from supabase import create_client
                from dotenv import load_dotenv
                import os as _os
                load_dotenv("/root/.env")
                self._sb = create_client(
                    _os.environ["SUPABASE_URL"],
                    _os.environ["SUPABASE_SERVICE_KEY"],
                )
            except Exception as e:
                self.logger.error(f"Supabase: {e}")
                self._sb = None
        return self._sb

    def _handle_error(self, failure):
        """Handle request errors — track in crawler stats."""
        self.crawler.stats.inc_value("camofox/errors")
        self.logger.warning(
            f"[google] Request failed: {failure.request.url[:100]} "
            f"— {failure.value}"
        )
