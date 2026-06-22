"""
Yelp spider — search by company name + phone + city, extract profile data.

Yelp is aggressive about anti-scraping. This spider uses:
  - Rotating user agents
  - Longer delays (5-8s between requests)
  - Search by phone number (most reliable) with fallback to name+city
  - Extracts: rating, review count, price level, categories, claimed status

Anti-bot notes:
  - Yelp now requires JS for search results; we use regex on the raw HTML
  - May need camofox-browser fallback for JS-rendered pages
"""
import re
import json
from typing import Optional
from urllib.parse import quote_plus

import scrapy
from scrapy_b2b.items import B2BBusinessItem


class YelpSpider(scrapy.Spider):
    name = "yelp"
    allowed_domains = ["yelp.com", "www.yelp.com"]

    custom_settings = {
        "DOWNLOAD_DELAY": 6,
        "AUTOTHROTTLE_START_DELAY": 6,
        "AUTOTHROTTLE_MAX_DELAY": 25,
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
            phone = (lead.get("phone") or "").strip()
            city = (lead.get("city") or "").strip()
            state = (lead.get("state") or "").strip()

            if not company:
                continue

            # Strategy 1: Search by phone (most reliable on Yelp)
            clean_phone = re.sub(r"\D", "", phone)
            if clean_phone and len(clean_phone) >= 10:
                search_url = (
                    f"https://www.yelp.com/search?"
                    f"find_desc={quote_plus(company[:60])}&"
                    f"find_loc={quote_plus(f'{city}, {state}')}&"
                    f"phone={clean_phone[-10:]}"
                )
            else:
                # Fallback: search by name + city
                search_url = (
                    f"https://www.yelp.com/search?"
                    f"find_desc={quote_plus(company[:60])}&"
                    f"find_loc={quote_plus(f'{city}, {state}')}"
                )

            yield scrapy.Request(
                url=search_url,
                callback=self.parse_search_results,
                meta={
                    "lead_id": lead_id,
                    "lead": lead,
                    "search_url": search_url,
                    "clean_phone": clean_phone,
                },
                dont_filter=True,
                errback=self._handle_error,
            )

    def parse_search_results(self, response):
        """Parse Yelp search results. Extract first matching business URL."""
        lead = response.meta["lead"]
        lead_id = response.meta["lead_id"]
        clean_phone = response.meta.get("clean_phone", "")

        text = response.text

        # Yelp business URLs: /biz/<slug>
        biz_urls = re.findall(
            r'href="(/biz/[a-z0-9\-]+(?:\?[^"]*)?)"',
            text,
        )

        if not biz_urls:
            self.logger.info(
                f"[yelp] No results for {lead.get('company_name','')[:40]} "
                f"in {lead.get('city','')}"
            )
            return

        # Filter out ad/sponsored URLs
        biz_urls = [u for u in biz_urls if "adredir" not in u.lower()]

        # Take first organic result
        profile_path = biz_urls[0].split("?")[0]  # strip query params
        profile_url = f"https://www.yelp.com{profile_path}"

        yield scrapy.Request(
            url=profile_url,
            callback=self.parse_profile,
            meta={
                "lead_id": lead_id,
                "lead": lead,
                "profile_url": profile_url,
                "clean_phone": clean_phone,
            },
            dont_filter=True,
            errback=self._handle_error,
        )

    def parse_profile(self, response):
        """Parse a Yelp business profile page."""
        lead = response.meta["lead"]
        lead_id = response.meta["lead_id"]
        profile_url = response.meta["profile_url"]
        clean_phone = response.meta.get("clean_phone", "")
        text = response.text

        # ── Rating ──
        rating = None
        rating_match = re.search(
            r'(?:ratingValue|rating)[:\s"]+(\d+(?:\.\d+)?)',
            text, re.IGNORECASE,
        )
        if not rating_match:
            # Yelp embeds rating in aria-label like "4.5 star rating"
            rating_match = re.search(
                r'aria-label="(\d+(?:\.\d+)?)\s+star\s+rating"',
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
            r'(?:reviewCount|reviews?)[:\s"]+(\d[\d,]*)',
            text, re.IGNORECASE,
        )
        if not review_match:
            review_match = re.search(
                r'(\d[\d,]*)\s+reviews?',
                text, re.IGNORECASE,
            )
        if review_match:
            review_count = int(review_match.group(1).replace(",", ""))

        # ── Price level ──
        price_level = None
        price_match = re.search(
            r'(?:priceRange|price)[:\s"]+(\${1,4})',
            text, re.IGNORECASE,
        )
        if price_match:
            price_level = price_match.group(1)

        # ── Categories ──
        categories = []
        cat_matches = re.findall(
            r'href="/(?:search|biz)/[^"]*"[^>]*>\s*([A-Z][A-Za-z\s&/-]+?)\s*<',
            text,
        )
        for cat in cat_matches:
            cat = cat.strip()
            if cat and len(cat) > 2 and cat.lower() not in ("home", "write a review", "photos", "null"):
                categories.append(cat)
        categories = list(dict.fromkeys(categories))[:8]  # dedup, cap

        # ── Phone ──
        phone_on_profile = None
        tel_match = re.search(r'tel:(\+?1?\d{10,})', text)
        if not tel_match:
            tel_match = re.search(
                r'phone[:\s"]+(\+?1?\s*\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4})',
                text, re.IGNORECASE,
            )
        if tel_match:
            phone_on_profile = re.sub(r"\D", "", tel_match.group(1))

        # ── Address ──
        address_on_profile = None
        addr_match = re.search(
            r'"streetAddress"\s*:\s*"([^"]+)"',
            text,
        )
        if not addr_match:
            addr_match = re.search(
                r'(\d{1,5}\s+[A-Z][a-zA-Z\s\.]+(?:St|Ave|Blvd|Rd|Dr|Ln|Way|Ct)[^,]{5,60}),\s*([A-Z][a-zA-Z\s]+),\s*([A-Z]{2})\s+(\d{5})',
                text,
            )
        if addr_match:
            if addr_match.lastindex and addr_match.lastindex >= 4:
                address_on_profile = (
                    f"{addr_match.group(1).strip()}, "
                    f"{addr_match.group(2).strip()}, "
                    f"{addr_match.group(3)} {addr_match.group(4)}"
                )
            else:
                address_on_profile = addr_match.group(0).strip()

        # ── Website ──
        website_on_profile = None
        site_match = re.search(
            r'href="(https?://(?!www\.yelp\.)[^"]+)"[^>]*>\s*(?:website|business\s+website|visit)',
            text, re.IGNORECASE,
        )
        if site_match:
            website_on_profile = site_match.group(1)

        # ── Claimed ──
        claimed = bool(re.search(
            r'claimed|business\s+owner|verified\s+business',
            text, re.IGNORECASE,
        ))

        # ── Photos count ──
        photos_count = None
        photos_match = re.search(r'(\d+)\s+photos?', text, re.IGNORECASE)
        if photos_match:
            photos_count = int(photos_match.group(1))

        # ── Match confidence ──
        match_confidence, match_reason = self._compute_confidence(
            lead, clean_phone, phone_on_profile, address_on_profile, website_on_profile,
        )

        yield B2BBusinessItem(
            b2b_lead_id=lead_id,
            company_name=lead.get("company_name", ""),
            search_phone=lead.get("phone", ""),
            search_website=lead.get("website", ""),
            source="yelp",
            profile_url=profile_url,
            rating=rating,
            review_count=review_count,
            categories=categories if categories else None,
            price_level=price_level,
            phone_on_profile=phone_on_profile,
            address_on_profile=address_on_profile,
            website_on_profile=website_on_profile,
            claimed=claimed,
            photos_count=photos_count,
            match_confidence=match_confidence,
            match_reason=match_reason,
            scraped_at=None,
        )

    def _compute_confidence(self, lead, search_phone, profile_phone, addr, website):
        score = 0
        reasons = []

        if search_phone and profile_phone:
            if search_phone[-10:] == profile_phone[-10:]:
                score += 4
                reasons.append("phone_match")

        lead_addr = (lead.get("address", "") or "").lower().split(",")[0].strip()
        profile_addr = (addr or "").lower().split(",")[0].strip()
        if lead_addr and profile_addr and lead_addr[:15] == profile_addr[:15]:
            score += 3
            reasons.append("address_match")

        lead_site = (lead.get("website", "") or "").lower().replace("http://", "").replace("https://", "").rstrip("/")
        profile_site = (website or "").lower().replace("http://", "").replace("https://", "").rstrip("/")
        if lead_site and profile_site and lead_site == profile_site:
            score += 3
            reasons.append("website_match")

        if score >= 5:
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
            f"[yelp] Request failed: {failure.request.url[:100]} "
            f"— {failure.value}"
        )
