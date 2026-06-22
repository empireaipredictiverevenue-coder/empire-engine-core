"""
BBB spider — search by company name + city, extract profile page data.

Uses BBB's search endpoint with polite delays. Extracts:
  - Rating (A+ to F letter grade + numeric score)
  - Accreditation status
  - Years in business
  - Categories
  - Phone/address match verification
  - Review count

Anti-bot notes:
  - BBB uses Cloudflare; we use simple GET with rotating UAs
  - If blocked, fall back to camofox-browser path (bots/bbb_search.py)
"""
import re
import json
from typing import Optional
from urllib.parse import quote_plus

import scrapy
from scrapy_b2b.items import B2BBusinessItem


class BBBSpider(scrapy.Spider):
    name = "bbb"
    allowed_domains = ["bbb.org", "www.bbb.org"]

    # BBB rating letter → numeric score
    RATING_MAP = {
        "A+": 5.0, "A": 4.5, "A-": 4.0,
        "B+": 3.5, "B": 3.0, "B-": 2.5,
        "C+": 2.0, "C": 1.5, "C-": 1.0,
        "D+": 0.5, "D": 0.0, "F": 0.0,
        "NR": None, "": None,
    }

    custom_settings = {
        "DOWNLOAD_DELAY": 5,
        "AUTOTHROTTLE_START_DELAY": 5,
        "AUTOTHROTTLE_MAX_DELAY": 20,
    }

    def __init__(self, lead_ids_json: str = "[]", lead_ids_file: str = "", *args, **kwargs):
        super().__init__(*args, **kwargs)
        if lead_ids_file:
            with open(lead_ids_file) as f:
                self.lead_ids = json.load(f)
        else:
            self.lead_ids = json.loads(lead_ids_json)
        self._leads_cache: dict = {}  # lead_id → lead row

    def start_requests(self):
        """For each lead, search BBB by company name + city + state."""
        sb = self._get_sb()
        if not sb:
            return

        for lead_id in self.lead_ids:
            lead = self._fetch_lead(sb, lead_id)
            if not lead:
                continue

            # Build BBB search URL
            company = (lead.get("company_name") or "").strip()
            city = (lead.get("city") or "").strip()
            state = (lead.get("state") or "").strip()
            if not company or not city:
                continue

            search_url = (
                f"https://www.bbb.org/search?"
                f"find_text={quote_plus(company[:80])}&"
                f"find_loc={quote_plus(f'{city}, {state}')}&"
                f"find_type=Category"
            )

            yield scrapy.Request(
                url=search_url,
                callback=self.parse_search_results,
                meta={
                    "lead_id": lead_id,
                    "lead": lead,
                    "search_url": search_url,
                },
                dont_filter=True,
                errback=self._handle_error,
            )

    def parse_search_results(self, response):
        """Parse BBB search results page. Extract first matching profile URL."""
        lead = response.meta["lead"]
        lead_id = response.meta["lead_id"]

        # BBB search results are in a list of result cards
        # Look for profile links: /us/<state>/<city>/profile/<category>/<slug>-<id>
        profile_links = response.css(
            'a[href*="/profile/"]::attr(href), '
            'a[href*="/us/"][href*="/profile/"]::attr(href)'
        ).getall()

        # Also try regex fallback for JS-rendered pages
        if not profile_links:
            profile_re = re.compile(
                r'href="(/us/[a-z]{2}/[a-z0-9\-]+/profile/[^"]+)"',
                re.IGNORECASE,
            )
            profile_links = profile_re.findall(response.text)
        if not profile_links:
            # Try a11y snapshot style: /url: /us/...
            profile_re2 = re.compile(
                r'/url:\s*(/us/[a-z]{2}/[a-z0-9\-]+/profile/[^\s\n]+)',
                re.IGNORECASE,
            )
            profile_links = profile_re2.findall(response.text)

        if not profile_links:
            self.logger.info(f"[bbb] No results for {lead.get('company_name','')[:40]} in {lead.get('city','')}")
            return

        # Take the first profile URL
        profile_path = profile_links[0]
        if not profile_path.startswith("http"):
            profile_url = f"https://www.bbb.org{profile_path}"
        else:
            profile_url = profile_path

        yield scrapy.Request(
            url=profile_url,
            callback=self.parse_profile,
            meta={
                "lead_id": lead_id,
                "lead": lead,
                "profile_url": profile_url,
            },
            dont_filter=True,
            errback=self._handle_error,
        )

    def parse_profile(self, response):
        """Parse a BBB business profile page."""
        lead = response.meta["lead"]
        lead_id = response.meta["lead_id"]
        profile_url = response.meta["profile_url"]

        text = response.text

        # ── Rating (letter grade) ──
        rating_letter = None
        rating_match = re.search(
            r'(?:rating|grade)[:"]\s*([A-F][+\-]?|NR)',
            text, re.IGNORECASE,
        )
        if not rating_match:
            # Look for rating in schema.org JSON-LD
            rating_match = re.search(
                r'"ratingValue"\s*:\s*"([A-F][+\-]?)"',
                text,
            )
        if rating_match:
            rating_letter = rating_match.group(1).strip()

        # ── Accreditation ──
        accredited = bool(re.search(
            r'accredited\s+business|bbb\s+accredited|"accredited"',
            text, re.IGNORECASE,
        ))

        # ── Years in business ──
        years_match = re.search(
            r'(\d+)\s+years?\s+in\s+business',
            text, re.IGNORECASE,
        )
        years_in_business = int(years_match.group(1)) if years_match else None

        # ── Review count / complaints ──
        review_match = re.search(
            r'(?:customer\s+reviews?|reviews?)[:\s]*(\d[\d,]*)',
            text, re.IGNORECASE,
        )
        review_count = None
        if review_match:
            review_count = int(review_match.group(1).replace(",", ""))

        # ── Categories ──
        categories = []
        cat_matches = re.findall(
            r'"category"\s*:\s*"([^"]+)"|BBB\s+Category[:\s]*([^<\n]+)',
            text, re.IGNORECASE,
        )
        for m in cat_matches:
            cat = m[0] or m[1]
            cat = cat.strip()
            if cat and cat.lower() not in ("null", "none"):
                categories.append(cat)

        # ── Phone on profile ──
        phone_on_profile = None
        tel_match = re.search(r'tel:(\+?1?\d{10,})', text)
        if not tel_match:
            tel_match = re.search(r'(\(\d{3}\)\s*\d{3}[\-\s]?\d{4})', text)
        if tel_match:
            phone_on_profile = tel_match.group(1)

        # ── Address on profile ──
        address_on_profile = None
        addr_match = re.search(
            r'(\d{1,5}\s+[A-Z][a-zA-Z\s\.]+(?:St|Ave|Blvd|Rd|Dr|Ln|Way|Ct|Plaza|Court)[^,<]{5,80})',
            text,
        )
        if addr_match:
            address_on_profile = addr_match.group(1).strip()

        # ── Website on profile ──
        website_on_profile = None
        site_match = re.search(
            r'href="(https?://(?!www\.bbb\.org)[^"]+)"[^>]*>\s*(?:website|visit|www\.)',
            text, re.IGNORECASE,
        )
        if site_match:
            website_on_profile = site_match.group(1)

        # ── Match confidence ──
        match_confidence, match_reason = self._compute_confidence(
            lead, phone_on_profile, address_on_profile, website_on_profile,
        )

        yield B2BBusinessItem(
            b2b_lead_id=lead_id,
            company_name=lead.get("company_name", ""),
            search_phone=lead.get("phone", ""),
            search_website=lead.get("website", ""),
            source="bbb",
            profile_url=profile_url,
            rating=self.RATING_MAP.get(rating_letter) if rating_letter else None,
            review_count=review_count,
            categories=categories if categories else None,
            accreditation=rating_letter if accredited else None,
            phone_on_profile=phone_on_profile,
            address_on_profile=address_on_profile,
            website_on_profile=website_on_profile,
            claimed=accredited,
            match_confidence=match_confidence,
            match_reason=match_reason,
            scraped_at=None,  # set by pipeline
        )

    def _compute_confidence(self, lead, phone, addr, website):
        """How confident are we that this BBB profile matches the lead?"""
        score = 0
        reasons = []

        lead_phone = re.sub(r"\D", "", lead.get("phone", "") or "")
        profile_phone = re.sub(r"\D", "", phone or "")

        if lead_phone and profile_phone:
            if lead_phone[-10:] == profile_phone[-10:]:
                score += 3
                reasons.append("phone_match")
            elif lead_phone[-7:] == profile_phone[-7:]:
                score += 1
                reasons.append("phone_partial")

        lead_addr = (lead.get("address", "") or "").lower().split(",")[0].strip()
        profile_addr = (addr or "").lower().split(",")[0].strip()
        if lead_addr and profile_addr and lead_addr[:15] == profile_addr[:15]:
            score += 3
            reasons.append("address_match")
        elif lead_addr and profile_addr and lead_addr[:10] in profile_addr:
            score += 1
            reasons.append("address_partial")

        lead_site = (lead.get("website", "") or "").lower().replace("http://", "").replace("https://", "").rstrip("/")
        profile_site = (website or "").lower().replace("http://", "").replace("https://", "").rstrip("/")
        if lead_site and profile_site and lead_site == profile_site:
            score += 3
            reasons.append("website_match")

        if score >= 4:
            return "high", ",".join(reasons)
        elif score >= 2:
            return "medium", ",".join(reasons)
        else:
            return "low", ",".join(reasons)

    def _fetch_lead(self, sb, lead_id: str) -> Optional[dict]:
        """Fetch a single lead from b2b_leads for enrichment."""
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
            self.logger.error(f"Failed to fetch lead {lead_id}: {e}")
        return None

    def _get_sb(self):
        """Lazy Supabase client."""
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
                self.logger.error(f"Supabase init: {e}")
                self._sb = None
        return self._sb

    def _handle_error(self, failure):
        """Handle request errors — track in crawler stats."""
        self.crawler.stats.inc_value("camofox/errors")
        self.logger.warning(
            f"[bbb] Request failed: {failure.request.url[:100]} "
            f"— {failure.value}"
        )
