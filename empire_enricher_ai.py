"""
EMPIRE V49 · AI ENRICHER (LLM-Powered)
=======================================
Given a target with a website, fetches pages and extracts structured
business intelligence using regex (fast path) and local Llama (deep path).

Extracts:
  - Email addresses (primary + all found, deduped)
  - Phone numbers (US + international formats)
  - Business name (from page title / OG tags)
  - Services / product lines (from body text, classified)
  - Location hints (city, state from address blocks)
  - Employee count / revenue indicators (when present)

Each extracted field includes a confidence score (0.0-1.0) calibrated
by the SI core's ProbabilityCalibrator when outcome data is available.

Usage:
    from empire_enricher_ai import AIEnricher
    result = await enricher.enrich("https://example.com")
"""

import re
import json
import logging
import asyncio
from typing import Dict, Optional, List, Tuple
from urllib.parse import urlparse, urljoin

import httpx

from empire_ai_router import AIRouter

log = logging.getLogger("empire.enricher.ai")

# ── REGEX PATTERNS (fast path) ──────────────────────────────────────────

EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")

# US phone: (555) 123-4567, 555-123-4567, +15551234567
US_PHONE_RE = re.compile(
    r"(?:(?:\+1[\s.-]?)?\(?[2-9]\d{2}\)?[\s.-]?[2-9]\d{2}[\s.-]?\d{4})\b"
)

# Generic phone with country code
INTL_PHONE_RE = re.compile(r"\+\d{1,3}[-.\s]?\d{1,14}[-.\s]?\d{1,14}\b")

# Social / business profile links
SOCIAL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(linkedin\.com|facebook\.com|twitter\.com|x\.com|"
    r"crunchbase\.com|zoominfo\.com|angellist\.com)/[a-zA-Z0-9_/-]+"
)

# Employee count hints: "50-200 employees", "We are 1000+ strong"
EMPLOYEE_RE = re.compile(
    r"(\d{1,5})\s*(?:-\s*(\d{1,5}))?\s*(?:employees?|team members?|staff|people)",
    re.IGNORECASE,
)

# Pages to scrape
CONTACT_PATHS = ["", "/contact", "/contact-us", "/contact_us",
                 "/about", "/about-us", "/team", "/company"]

# Generic email prefixes we deprioritize
GENERIC_PREFIXES = {"info", "hello", "support", "noreply", "no-reply",
                    "donotreply", "webmaster", "admin", "postmaster",
                    "abuse", "privacy", "legal", "careers", "jobs",
                    "sales", "marketing"}

# Generic phone descriptions
GENERIC_PHONE_TAGS = {"fax", "toll-free", "toll free", "support", "customer service"}

# Business services/niche keywords for classification
SERVICE_KEYWORDS = {
    "roofing": ["roof", "shingle", "roofing", "gutter", "skylight"],
    "hvac": ["hvac", "heating", "cooling", "air conditioning", "furnace", "ac repair"],
    "legal": ["attorney", "law firm", "legal", "lawyer", "counsel", "plaintiff"],
    "solar": ["solar", "photovoltaic", "pv panel", "solar installation"],
    "restoration": ["restoration", "water damage", "fire damage", "flood", "mold"],
    "construction": ["contractor", "construction", "general contractor", "remodeling"],
    "logistics": ["logistics", "warehouse", "distribution", "freight", "supply chain"],
    "cpa": ["cpa", "accounting", "tax", "bookkeeping", "accountant"],
    "medical": ["clinic", "medical", "healthcare", "doctor", "physician", "hospital"],
}


class AIEnricher:
    """
    Multi-source business intelligence extractor.

    Uses regex for the fast path and the local Llama model (via AIRouter)
    for deep extraction on unstructured pages. Each field is scored with
    a confidence estimate (0.0-1.0).
    """

    def __init__(self, router: Optional[AIRouter] = None):
        self.router = router
        self._stats = {"regex_hits": 0, "llm_fallbacks": 0, "errors": 0}

    # ── PUBLIC API ─────────────────────────────────────────────────────

    async def enrich(
        self,
        website: str,
        business_name: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        Enrich a website with full business intelligence.

        Args:
            website: Website URL (with or without https://).
            business_name: Known business name (optional, for cross-check).

        Returns:
            Dict with all extracted fields and confidence scores, or None
            if the website is unreachable.
        """
        if not website:
            return None
        website = self._normalize_url(website)

        # 1. Fetch pages
        pages = await self._fetch_pages(website)
        if not pages:
            return None

        # 2. Extract raw signals
        raw = self._extract_regex(pages, business_name)

        # 3. LLM deep extraction for fields with low confidence
        if self.router and any(v.get("confidence", 1.0) < 0.6 for v in raw.values()):
            llm_fields = await self._extract_llm(pages, business_name, website)
            for field, value in llm_fields.items():
                if value and (field not in raw or raw[field].get("confidence", 0) < value.get("confidence", 0)):
                    raw[field] = value

        # 4. Build result
        return {
            "emails": raw.get("emails", {"primary": None, "all": [], "confidence": 0.0}),
            "phones": raw.get("phones", {"primary": None, "all": [], "confidence": 0.0}),
            "business_name": raw.get("business_name", {"value": business_name, "confidence": 0.0}),
            "services": raw.get("services", {"value": [], "confidence": 0.0}),
            "location": raw.get("location", {"city": None, "state": None, "confidence": 0.0}),
            "employee_hint": raw.get("employee_hint", {"value": None, "confidence": 0.0}),
            "social_links": raw.get("social_links", {"value": [], "confidence": 0.0}),
            "niche_classification": raw.get("niche_classification", []),
            "source_pages": list(pages.keys()),
            "regex_hits": self._stats["regex_hits"],
            "llm_fallbacks": self._stats["llm_fallbacks"],
        }

    async def enrich_targets(
        self, targets: List[Dict], max_concurrent: int = 3
    ) -> List[Dict]:
        """Run enrich() on a list of targets with a concurrency limit."""
        sem = asyncio.Semaphore(max_concurrent)

        async def _one(t):
            if t.get("email") or not t.get("website"):
                return t
            async with sem:
                result = await self.enrich(t["website"], t.get("warehouse_name"))
                if result:
                    self._merge_into_target(t, result)
            return t

        return await asyncio.gather(*(_one(t) for t in targets))

    def _merge_into_target(self, target: Dict, enrichment: Dict) -> None:
        """Merge enrichment results into a target dict."""
        emails = enrichment.get("emails", {})
        if emails.get("primary"):
            target["email"] = emails["primary"]
            target["email_confidence"] = emails.get("confidence", 0.0)
            target["all_emails"] = emails.get("all", [])

        phones = enrichment.get("phones", {})
        if phones.get("primary"):
            target["phone"] = phones["primary"]
            target["phone_confidence"] = phones.get("confidence", 0.0)

        biz = enrichment.get("business_name", {})
        if biz.get("value") and biz.get("confidence", 0) > 0.5:
            target["warehouse_name"] = biz["value"]

        loc = enrichment.get("location", {})
        if loc.get("city"):
            target["city"] = loc["city"]
        if loc.get("state"):
            target["state"] = loc["state"]

        if enrichment.get("niche_classification"):
            target["niche_hints"] = enrichment["niche_classification"]

        target["_enrichment_meta"] = {
            "source_pages": enrichment.get("source_pages", []),
            "regex_hits": enrichment.get("regex_hits", 0),
            "llm_fallbacks": enrichment.get("llm_fallbacks", 0),
        }

    # ── FETCH ─────────────────────────────────────────────────────────

    async def _fetch_pages(self, website: str) -> Dict[str, str]:
        """Fetch relevant pages from a website. Returns {path: text}."""
        pages = {}
        async with httpx.AsyncClient(
            timeout=15.0, follow_redirects=True,
            headers={"User-Agent": "EmpireAI-v49 (research enricher)"},
        ) as client:
            for path in CONTACT_PATHS:
                try:
                    url = website + path
                    r = await client.get(url)
                    if r.status_code == 200:
                        text = r.text[:100000]  # cap at 100KB
                        pages[path or "/"] = text
                        # If we got a generic page and found contact info, stop
                        if path in ("", "/contact", "/contact-us") and self._has_contact_signals(text):
                            break
                except Exception as e:
                    log.debug(f"[enricher.ai] fetch fail {website}{path}: {e}")
                    continue
        return pages

    @staticmethod
    def _has_contact_signals(text: str) -> bool:
        """Quick check if page has contact info."""
        return bool(
            re.search(r"email|phone|contact|@|call us|get in touch", text[:5000], re.IGNORECASE)
        )

    # ── REGEX EXTRACTION (fast path) ───────────────────────────────────

    def _extract_regex(
        self, pages: Dict[str, str], known_name: Optional[str] = None
    ) -> Dict:
        """Extract structured data from page text using regex patterns."""
        all_text = "\n".join(pages.values())
        result: Dict = {}

        # ── Emails ───────────────────────────────────────────────────
        emails_found = EMAIL_RE.findall(all_text)
        unique_emails = list(dict.fromkeys(e.lower() for e in emails_found))
        non_generic = [e for e in unique_emails
                       if e.split("@")[0] not in GENERIC_PREFIXES]

        if non_generic:
            result["emails"] = {
                "primary": non_generic[0],
                "all": unique_emails,
                "confidence": min(0.95, 0.5 + 0.1 * len(non_generic)),
            }
            self._stats["regex_hits"] += 1
        elif unique_emails:
            result["emails"] = {
                "primary": unique_emails[0],
                "all": unique_emails,
                "confidence": 0.4,  # generic only — lower confidence
            }
        else:
            result["emails"] = {"primary": None, "all": [], "confidence": 0.0}

        # ── Phones ──────────────────────────────────────────────────
        us_phones = list(dict.fromkeys(US_PHONE_RE.findall(all_text)))
        intl_phones = list(dict.fromkeys(INTL_PHONE_RE.findall(all_text)))
        all_phones = us_phones + [p for p in intl_phones if p not in us_phones]

        if all_phones:
            result["phones"] = {
                "primary": all_phones[0],
                "all": all_phones,
                "confidence": min(0.9, 0.4 + 0.08 * len(all_phones)),
            }
            self._stats["regex_hits"] += 1
        else:
            result["phones"] = {"primary": None, "all": [], "confidence": 0.0}

        # ── Business name ───────────────────────────────────────────
        name = self._extract_business_name(all_text, known_name)
        result["business_name"] = name

        # ── Location ────────────────────────────────────────────────
        loc = self._extract_location(all_text)
        result["location"] = loc

        # ── Services ────────────────────────────────────────────────
        services = self._classify_services(all_text)
        result["services"] = {
            "value": list(dict.fromkeys(services)),  # dedup preserve order
            "confidence": min(0.8, 0.3 + 0.1 * len(services)),
        }

        # ── Employee hints ──────────────────────────────────────────
        emp = EMPLOYEE_RE.findall(all_text)
        if emp:
            low, high = emp[0]
            hint = f"{low}-{high}" if high else low
            result["employee_hint"] = {
                "value": hint,
                "confidence": 0.7,
            }
            self._stats["regex_hits"] += 1
        else:
            result["employee_hint"] = {"value": None, "confidence": 0.0}

        # ── Social links ────────────────────────────────────────────
        socials = list(dict.fromkeys(SOCIAL_RE.findall(all_text)))
        result["social_links"] = {
            "value": [s if s.startswith("http") else f"https://{s}" for s in socials],
            "confidence": 0.8 if socials else 0.0,
        }

        # ── Niche classification ────────────────────────────────────
        result["niche_classification"] = self._classify_services(all_text)

        return result

    @staticmethod
    def _extract_business_name(text: str, known: Optional[str] = None) -> Dict:
        """Extract business name from meta tags and title."""
        # OG: site_name
        m = re.search(r'<meta\s+(?:property|name)=["\'](?:og:)?site_name["\']\s+content=["\']([^"\']+)["\']', text, re.IGNORECASE)
        if m:
            return {"value": m.group(1).strip(), "confidence": 0.85}

        # Title tag (strip site name patterns)
        m = re.search(r'<title[^>]*>([^<]+)</title>', text, re.IGNORECASE)
        if m:
            title = m.group(1).strip()
            # Remove common suffixes like " | Home" " - About"
            title = re.split(r'\s*[|\-–—•·]\s*(?:Home|About|Contact|Welcome)', title)[0].strip()
            if len(title) >= 3 and len(title) <= 100:
                return {"value": title, "confidence": 0.7}

        # H1
        m = re.search(r'<h1[^>]*>([^<]+)</h1>', text, re.IGNORECASE)
        if m:
            h1 = m.group(1).strip()
            if len(h1) >= 3 and len(h1) <= 80:
                return {"value": h1, "confidence": 0.55}

        if known:
            return {"value": known, "confidence": 0.3}
        return {"value": None, "confidence": 0.0}

    @staticmethod
    def _extract_location(text: str) -> Dict:
        """Extract city/state from address blocks."""
        # Common patterns: "123 Main St, City, ST 12345"
        m = re.search(
            r"\b([A-Z][a-z]+(?:[\s-][A-Z][a-z]+)*),?\s*([A-Z]{2})\s+\d{5}(?:-\d{4})?\b",
            text,
        )
        if m:
            return {"city": m.group(1).strip(), "state": m.group(2), "confidence": 0.8}

        # "City, ST" without zip
        m = re.search(r"\b([A-Z][a-z]+(?:[\s-][A-Z][a-z]+)*),\s*([A-Z]{2})\b", text)
        if m:
            return {"city": m.group(1).strip(), "state": m.group(2), "confidence": 0.5}

        return {"city": None, "state": None, "confidence": 0.0}

    @staticmethod
    def _classify_services(text: str) -> List[str]:
        """Classify the business into service niches based on keyword matches."""
        text_lower = text.lower()
        matched = []
        for niche, keywords in SERVICE_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                matched.append(niche)
        return matched

    # ── LLM EXTRACTION (deep path) ─────────────────────────────────────

    async def _extract_llm(
        self, pages: Dict[str, str], known_name: Optional[str] = None, website: str = ""
    ) -> Dict:
        """
        Use local Llama via AIRouter to extract structured data from
        pages where regex was insufficient.
        """
        if not self.router:
            return {}

        self._stats["llm_fallbacks"] += 1

        # Build a compact text blob (first 15KB of the most relevant page)
        best_page = pages.get("/") or pages.get("") or next(iter(pages.values()), "")
        text_blob = best_page[:15000]

        prompt = (
            f"Extract business intelligence from this website text. "
            f"Website: {website}\n"
            f"{'Known business name: ' + known_name if known_name else ''}\n\n"
            f"Page text:\n{text_blob}\n\n"
            f"Return JSON with these fields (null if not found):\n"
            f"  business_name: str\n"
            f"  city: str\n"
            f"  state: str (2-letter code)\n"
            f"  services: [str] (list of business services/products)\n"
            f"  email: str (best contact email)\n"
            f"  phone: str (best contact phone)\n"
            f"  employee_count_hint: str or null\n"
            f"Only include fields you are confident about."
        )

        try:
            raw = await self.router.route(
                "enricher.extract",
                prompt,
                system="You are a business intelligence extraction agent. Extract structured data from website text. Return only valid JSON.",
            )
            data = json.loads(raw) if isinstance(raw, str) else raw
        except Exception as e:
            log.debug(f"[enricher.ai] LLM extraction failed: {e}")
            return {}

        result = {}
        if data.get("email"):
            result["emails"] = {
                "primary": data["email"],
                "all": [data["email"]],
                "confidence": 0.6,  # LLM-extracted, lower than regex
            }
        if data.get("phone"):
            result["phones"] = {
                "primary": data["phone"],
                "all": [data["phone"]],
                "confidence": 0.55,
            }
        if data.get("business_name"):
            result["business_name"] = {
                "value": data["business_name"],
                "confidence": 0.65,
            }
        if data.get("services"):
            result["services"] = {
                "value": data["services"] if isinstance(data["services"], list) else [data["services"]],
                "confidence": 0.5,
            }
        if data.get("city") or data.get("state"):
            result["location"] = {
                "city": data.get("city"),
                "state": data.get("state"),
                "confidence": 0.5,
            }
        if data.get("employee_count_hint"):
            result["employee_hint"] = {
                "value": str(data["employee_count_hint"]),
                "confidence": 0.45,
            }

        return result

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Ensure URL has scheme and no trailing slash."""
        url = url.strip()
        if not url.startswith("http"):
            url = "https://" + url
        return url.rstrip("/")

    # ── STATS ──────────────────────────────────────────────────────────

    def get_stats(self) -> Dict:
        return dict(self._stats)

    def reset_stats(self) -> None:
        self._stats = {"regex_hits": 0, "llm_fallbacks": 0, "errors": 0}
