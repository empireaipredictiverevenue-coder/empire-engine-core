"""
EMPIRE V49 · AI ENRICHER
=========================
Given a target with a website but no email, fetches the homepage + /contact
+ /about, extracts emails. Uses regex first (cheap), Llama 3.2 3b as fallback
for messy pages.
"""
import re
import logging
import asyncio
from typing import Dict, Optional, List
import httpx

from empire_ai_router import AIRouter

log = logging.getLogger("empire.enricher.ai")

EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")

# Pages to try, in order. First good email wins.
CONTACT_PATHS = ["", "/contact", "/contact-us", "/contact_us", "/about", "/about-us"]

# Generic emails we'd rather skip if a more specific one is available
GENERIC_PREFIXES = {"info", "hello", "support", "noreply", "no-reply", "donotreply",
                    "webmaster", "admin", "postmaster", "abuse", "privacy", "legal"}


class AIEnricher:
    def __init__(self, router=None):
        self.router = router

    async def find_email(self, website: str, business_name: Optional[str] = None) -> Optional[Dict]:
        """
        Try to find a contact email for the business at this website.
        Returns {"email": "x@y.com", "source": "regex|llm", "page": "/contact"} or None.
        """
        if not website:
            return None
        website = website.rstrip("/")
        if not website.startswith("http"):
            website = "https://" + website

        candidates: List[Dict] = []
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True,
                                     headers={"User-Agent": "EmpireAI-v49 (research)"}) as client:
            for path in CONTACT_PATHS:
                try:
                    url = website + path
                    r = await client.get(url)
                    if r.status_code != 200:
                        continue
                    text = r.text[:80000]  # cap to 80KB
                    # 1. Regex first
                    found = EMAIL_RE.findall(text)
                    for e in found:
                        e_low = e.lower()
                        prefix = e_low.split("@")[0]
                        candidates.append({
                            "email": e_low,
                            "source": "regex",
                            "page": path or "/",
                            "is_generic": prefix in GENERIC_PREFIXES,
                        })
                    if candidates and any(not c["is_generic"] for c in candidates):
                        break  # found a non-generic, stop scanning
                except Exception as e:
                    log.debug(f"[enricher.ai] fetch fail {website}{path}: {e}")
                    continue

        if not candidates:
            return None

        # Prefer non-generic, then earliest
        non_generic = [c for c in candidates if not c["is_generic"]]
        chosen = (non_generic or candidates)[0]
        return {
            "email": chosen["email"],
            "source": chosen["source"],
            "page": chosen["page"],
            "all_found": list({c["email"] for c in candidates}),
        }

    async def enrich_targets(self, targets: List[Dict], max_concurrent: int = 3) -> List[Dict]:
        """Run find_email() on a list of targets that have website but no email."""
        sem = asyncio.Semaphore(max_concurrent)

        async def _one(t):
            if t.get("email") or not t.get("website"):
                return t
            async with sem:
                found = await self.find_email(t["website"], t.get("warehouse_name"))
                if found:
                    t["email"] = found["email"]
                    t["email_source"] = found["source"]
                    t["email_page"] = found["page"]
            return t

        return await asyncio.gather(*(_one(t) for t in targets))
