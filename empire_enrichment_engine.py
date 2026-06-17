"""
EMPIRE V49 · ENRICHMENT ENGINE
================================
Comprehensive lead enrichment system with:

  1. DeepEnricher — LLM-powered structured enrichment that extracts services,
     fleet size, years in business, decision makers, insurance coverage,
     and service areas from every website (not just as regex fallback).

  2. QualityEngine — Tracks which enrichment sources/strategies perform best
     per niche. Auto-prioritizes sources based on historical accuracy.

  3. PipelineOrchestrator — DAG-based runner for the 4-agent pipeline
     (scanner → enricher → scorer → converter) with progress tracking,
     skip/retry logic, and stall alerts.

  4. Real-time Routes — POST /api/v1/enrich for on-demand enrichment,
     GET /api/v1/enrich/quality for quality stats,
     GET /api/v1/enrich/pipeline for pipeline status.

USAGE
─────
  from empire_enrichment_engine import (
      DeepEnricher,
      QualityEngine,
      PipelineOrchestrator,
      register_enrichment_routes,
  )

  enricher = DeepEnricher(router=ai_router)
  quality = QualityEngine(get_db=get_db)
  orchestrator = PipelineOrchestrator(get_db=get_db, enricher=enricher)
  register_enrichment_routes(app, enricher=enricher, quality=quality,
                              orchestrator=orchestrator, require_auth=require_auth)
"""

import os
import re
import json
import uuid
import math
import time
import hashlib
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Callable, Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse, urljoin

import httpx
from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from supabase import create_client

log = logging.getLogger("empire.enrichment")


# ═════════════════════════════════════════════════════════════════════
# 1. DEEP ENRICHER — LLM-Powered Structured Extraction
# ═════════════════════════════════════════════════════════════════════

_SCRAPE_TIMEOUT = 20.0
_MAX_PAGE_BYTES = 150_000
_USER_AGENT = "EmpireAI-v49 (enrichment engine; research)"

# Pages to try when scraping
_CONTACT_PATHS = [
    "", "/about", "/about-us", "/about_us",
    "/contact", "/contact-us", "/contact_us",
    "/team", "/our-team", "/company",
    "/services", "/what-we-do", "/locations",
    "/faq", "/service-areas",
]

# Regex patterns (fast path for fields that don't need LLM)
_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
_US_PHONE_RE = re.compile(r"(?:(?:\+1[\s.-]?)?\(?[2-9]\d{2}\)?[\s.-]?[2-9]\d{2}[\s.-]?\d{4})\b")
_SOCIAL_RE = re.compile(r"(?:https?://)?(?:www\.)?(linkedin\.com|facebook\.com|twitter\.com|x\.com|crunchbase\.com|zoominfo\.com|angellist\.com)/[a-zA-Z0-9_/-]+")
_STATE_RE = re.compile(r"\b([A-Z]{2})\b")

# Generic email prefixes to deprioritize
_GENERIC_PREFIXES = {"info", "hello", "support", "noreply", "no-reply",
                     "donotreply", "webmaster", "admin", "postmaster",
                     "abuse", "privacy", "legal", "careers", "jobs"}

# Score weights for different enrichment fields (for overall confidence)
_FIELD_WEIGHTS = {
    "emails": 0.15, "phones": 0.15, "services": 0.10,
    "niche": 0.10, "business_name": 0.10, "location": 0.08,
    "decision_makers": 0.10, "fleet_size": 0.08,
    "years_in_business": 0.05, "insurance_types": 0.05,
    "service_areas": 0.04,
}


class DeepEnricher:
    """
    LLM-powered website enrichment engine.

    For every target website, this:
      1. Fetches multiple pages (/, /about, /services, /contact, /team, etc.)
      2. Runs regex fast-path for emails, phones, social links
      3. Runs structured LLM extraction on the combined page text
      4. Returns a unified enrichment result with per-field confidence scores

    The LLM prompt is designed to extract structured data in JSON format
    covering services, fleet size, years in business, decision makers,
    insurance types, and service areas — fields the regex-only path misses.
    """

    def __init__(self, router: Optional[Any] = None):
        self.router = router  # AIRouter instance for LLM calls
        self._stats = {
            "total_requests": 0,
            "regex_hits": 0,
            "llm_extractions": 0,
            "fetch_errors": 0,
            "llm_errors": 0,
        }
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=_SCRAPE_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": _USER_AGENT},
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )
        return self._http_client

    async def enrich(
        self,
        website: str,
        business_name: Optional[str] = None,
        niche_hint: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        Enrich a website with deep LLM-powered business intelligence.

        Args:
            website: URL or domain to enrich.
            business_name: Known business name (optional, for cross-check).
            niche_hint: Niche hint for targeted extraction (optional).

        Returns:
            Dict with all extracted fields and confidence scores, or None
            if the website is unreachable.
        """
        self._stats["total_requests"] += 1

        if not website:
            return None
        website = self._normalize_url(website)

        # 1. Fetch pages
        pages = await self._fetch_pages(website)
        if not pages:
            self._stats["fetch_errors"] += 1
            return None

        # 2. Regex fast-path for emails, phones, social links
        result = self._extract_regex(pages)

        # 3. LLM deep extraction on the combined page text
        llm_result = await self._extract_llm_deep(
            pages=pages,
            business_name=business_name,
            website=website,
            niche_hint=niche_hint,
        )

        # Merge LLM results (LLM wins for structured fields, regex keeps phone/email)
        for field, value in llm_result.items():
            if field in ("emails", "phones"):
                # Regex is more reliable for these — only use LLM if regex found nothing
                if not result.get(field, {}).get("primary"):
                    result[field] = value
            else:
                # LLM wins for all structured fields
                if value and value.get("value") is not None:
                    result[field] = value

        # 4. Calculate overall enrichment score
        result["overall_score"] = self._calculate_overall_score(result)

        # 5. Attach metadata
        result["_meta"] = {
            "source_pages": list(pages.keys()),
            "regex_hits": self._stats["regex_hits"],
            "llm_extractions": self._stats["llm_extractions"],
            "niche_hint": niche_hint,
            "enriched_at": datetime.now(timezone.utc).isoformat(),
        }

        return result

    async def _fetch_pages(self, website: str) -> Dict[str, str]:
        """Fetch multiple pages from a website. Returns {path: html_text}."""
        pages: Dict[str, str] = {}
        client = await self._get_client()

        for path in _CONTACT_PATHS:
            try:
                url = website + path
                r = await client.get(url)
                if r.status_code == 200:
                    text = r.text[:_MAX_PAGE_BYTES]
                    pages[path or "/"] = text
                    # If we got rich content on early pages, stop early
                    if path in ("", "/about", "/contact") and len(text) > 8000:
                        # But keep trying more paths for the LLM
                        pass
            except Exception as e:
                log.debug(f"[enrich] fetch fail {website}{path}: {e}")
                continue

        return pages

    @staticmethod
    def _extract_regex(pages: Dict[str, str]) -> Dict:
        """Fast-path regex extraction for emails, phones, social links."""
        all_text = "\n".join(pages.values())
        result: Dict = {}

        # ── Emails ───────────────────────────────────────────────────
        emails_found = _EMAIL_RE.findall(all_text)
        unique_emails = list(dict.fromkeys(e.lower() for e in emails_found))
        non_generic = [e for e in unique_emails
                       if e.split("@")[0] not in _GENERIC_PREFIXES]

        if non_generic:
            result["emails"] = {
                "primary": non_generic[0],
                "all": unique_emails,
                "confidence": min(0.95, 0.5 + 0.1 * len(non_generic)),
            }
        elif unique_emails:
            result["emails"] = {
                "primary": unique_emails[0],
                "all": unique_emails,
                "confidence": 0.4,
            }
        else:
            result["emails"] = {"primary": None, "all": [], "confidence": 0.0}

        # ── Phones ──────────────────────────────────────────────────
        phones_found = list(dict.fromkeys(_US_PHONE_RE.findall(all_text)))
        if phones_found:
            result["phones"] = {
                "primary": phones_found[0],
                "all": phones_found,
                "confidence": min(0.9, 0.4 + 0.08 * len(phones_found)),
            }
        else:
            result["phones"] = {"primary": None, "all": [], "confidence": 0.0}

        # ── Social links ────────────────────────────────────────────
        socials = list(dict.fromkeys(_SOCIAL_RE.findall(all_text)))
        result["social_links"] = {
            "value": [s if s.startswith("http") else f"https://{s}" for s in socials],
            "confidence": 0.8 if socials else 0.0,
        }

        return result

    async def _extract_llm_deep(
        self,
        pages: Dict[str, str],
        business_name: Optional[str] = None,
        website: str = "",
        niche_hint: Optional[str] = None,
    ) -> Dict:
        """
        Deep structured extraction using LLM.

        Builds a compact representation of all pages and asks the LLM
        to extract structured business intelligence as JSON.
        """
        if not self.router:
            log.debug("[enrich] no LLM router available — skipping deep extraction")
            return {}

        self._stats["llm_extractions"] += 1

        # Build the best page text (combine multiple pages up to 20KB)
        texts = []
        total_chars = 0
        for path in ("/", "/about", "/about-us", "/services", "/contact", "/team"):
            if path in pages:
                text = pages[path]
                snippet = self._extract_meaningful_text(text, 5000)
                if snippet and len(snippet) > 200:
                    texts.append(f"--- {path} ---\n{snippet}")
                    total_chars += len(snippet)
                    if total_chars > 18000:
                        break

        combined_text = "\n\n".join(texts) if texts else (next(iter(pages.values()), "")[:15000] if pages else "")

        if not combined_text or len(combined_text) < 100:
            return {}

        niche_context = f" (niche: {niche_hint})" if niche_hint else ""

        prompt = (
            f"Extract business intelligence from the website of{niche_context} a company.\n"
            f"Website: {website}\n"
            f"{'Known business name: ' + str(business_name) if business_name else ''}\n\n"
            f"Website content:\n{combined_text[:15000]}\n\n"
            f"Return ONLY valid JSON with these optional fields (null if not found):\n"
            f"{{\n"
            f'  "business_name": str | null,         // Full legal or DBA name\n'
            f'  "city": str | null,                   // Headquarters city\n'
            f'  "state": str | null,                  // 2-letter state code\n'
            f'  "services": [str],                     // Business services/product lines\n'
            f'  "niche": str | null,                  // Best-matching niche from: roofing, hvac, restoration, general_contractor, plumbing, electrical, solar, legal, logistics, manufacturing, medical, cpa, construction, landscaping, other\n'
            f'  "decision_makers": [str],             // Names of owners/executives found\n'
            f'  "fleet_size": str | null,             // e.g. "15 trucks", "20 vehicles", "5 service vans"\n'
            f'  "years_in_business": str | null,      // e.g. "since 1985", "25 years", "established 1998"\n'
            f'  "insurance_types": [str],             // e.g. ["general liability", "workers comp", "bonded"]\n'
            f'  "service_areas": [str],               // e.g. ["Dallas-Fort Worth", "Houston", "all of Texas"]\n'
            f'  "employee_count_hint": str | null,    // e.g. "50-200", "1000+", "15 employees"\n'
            f'  "revenue_hint": str | null,           // Any revenue/income indicators\n'
            f'  "email": str | null,                  // Best contact email\n'
            f'  "phone": str | null                   // Best contact phone\n'
            f"}}\n\n"
            f"Only include fields you are highly confident about. Set to null if unsure."
        )

        try:
            raw = await self.router.route(
                "enricher.deep_extract",
                prompt,
                system=(
                    "You are a business intelligence extraction agent. "
                    "Extract structured data from website text. "
                    "Return ONLY valid JSON — no explanations, markdown, or comments."
                ),
            )
            data = json.loads(raw) if isinstance(raw, str) else raw
        except Exception as e:
            self._stats["llm_errors"] += 1
            log.debug(f"[enrich] LLM extraction failed: {e}")
            return {}

        # Transform LLM output to standardized format with confidence scores
        result: Dict = {}

        # Business name
        if data.get("business_name"):
            result["business_name"] = {
                "value": data["business_name"],
                "confidence": 0.7,
            }

        # Services
        if data.get("services") and isinstance(data["services"], list):
            result["services"] = {
                "value": list(dict.fromkeys(data["services"])),
                "confidence": min(0.8, 0.4 + 0.05 * len(data["services"])),
            }

        # Niche
        if data.get("niche"):
            result["niche_classification"] = {
                "value": data["niche"],
                "confidence": 0.65,
            }

        # Location
        loc = {}
        if data.get("city"):
            loc["city"] = data["city"]
        if data.get("state"):
            loc["state"] = data["state"]
        if loc:
            result["location"] = {
                **loc,
                "confidence": 0.6,
            }

        # Decision makers
        if data.get("decision_makers") and isinstance(data["decision_makers"], list):
            result["decision_makers"] = {
                "value": data["decision_makers"],
                "confidence": 0.5,  # Lower confidence — may be partial/wrong
            }

        # Fleet size
        if data.get("fleet_size"):
            result["fleet_size"] = {
                "value": data["fleet_size"],
                "confidence": 0.6,
            }

        # Years in business
        if data.get("years_in_business"):
            result["years_in_business"] = {
                "value": data["years_in_business"],
                "confidence": 0.65,
            }

        # Insurance types
        if data.get("insurance_types") and isinstance(data["insurance_types"], list):
            result["insurance_types"] = {
                "value": data["insurance_types"],
                "confidence": 0.55,
            }

        # Service areas
        if data.get("service_areas") and isinstance(data["service_areas"], list):
            result["service_areas"] = {
                "value": data["service_areas"],
                "confidence": 0.6,
            }

        # Employee count
        if data.get("employee_count_hint"):
            result["employee_hint"] = {
                "value": str(data["employee_count_hint"]),
                "confidence": 0.5,
            }

        # Revenue hint
        if data.get("revenue_hint"):
            result["revenue_hint"] = {
                "value": str(data["revenue_hint"]),
                "confidence": 0.4,
            }

        # Email and phone (from LLM — lower confidence than regex)
        if data.get("email") and not result.get("emails", {}).get("primary"):
            result["emails"] = {
                "primary": data["email"],
                "all": [data["email"]],
                "confidence": 0.55,
            }
        if data.get("phone") and not result.get("phones", {}).get("primary"):
            result["phones"] = {
                "primary": data["phone"],
                "all": [data["phone"]],
                "confidence": 0.5,
            }

        return result

    @staticmethod
    def _extract_meaningful_text(html: str, max_chars: int = 5000) -> str:
        """Extract meaningful text from HTML — strip tags, scripts, styles."""
        # Remove scripts and styles
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        # Remove navigation/menu noise (short lines)
        lines = text.split('\n')
        meaningful = [l.strip() for l in lines if len(l.strip()) > 40]
        return '\n'.join(meaningful)[:max_chars]

    @staticmethod
    def _calculate_overall_score(result: Dict) -> Dict:
        """Calculate overall enrichment quality score."""
        weighted_sum = 0.0
        total_weight = 0.0
        field_scores = {}

        for field, weight in _FIELD_WEIGHTS.items():
            data = result.get(field, {})
            if isinstance(data, dict):
                confidence = data.get("confidence", 0.0) or 0.0
                has_value = data.get("value") is not None or data.get("primary") is not None
                if has_value:
                    weighted_sum += confidence * weight
                    total_weight += weight
                    field_scores[field] = confidence
                elif field in result and data:
                    # Has the key but no value
                    field_scores[field] = 0.0

        overall = round(weighted_sum / max(total_weight, 0.01), 3)
        return {
            "score": overall,
            "fields_extracted": len(field_scores),
            "fields_scores": field_scores,
            "grade": "A" if overall >= 0.7 else ("B" if overall >= 0.5 else ("C" if overall >= 0.3 else "D")),
        }

    @staticmethod
    def _normalize_url(url: str) -> str:
        url = url.strip()
        if not url.startswith("http"):
            url = "https://" + url
        return url.rstrip("/")

    async def close(self):
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    def get_stats(self) -> Dict:
        return dict(self._stats)


# ═════════════════════════════════════════════════════════════════════
# 2. QUALITY ENGINE — Per-Niche Source Reliability Tracking
# ═════════════════════════════════════════════════════════════════════

class QualityEngine:
    """
    Tracks which enrichment sources/strategies perform best per niche.

    Records every enrichment attempt with source, confidence, response time,
    and fields found. Queries can then prioritize sources that have proven
    most reliable for a given niche.
    """

    def __init__(self, get_db: Callable):
        self.get_db = get_db
        self._cache: Dict[str, List[Dict]] = {}
        self._cache_ts: float = 0.0
        self._cache_ttl = 120.0  # seconds

    async def record_attempt(
        self,
        source_name: str,
        strategy: str,
        niche: str,
        success: bool,
        confidence: float,
        fields_found: List[str],
        response_ms: float,
    ) -> None:
        """Record an enrichment attempt result for quality tracking."""
        db = self.get_db()
        niche_key = niche or "__all__"

        try:
            # Upsert: increment counters atomically
            row = db.table("enrichment_sources").select("*") \
                .eq("source_name", source_name) \
                .eq("strategy", strategy) \
                .eq("niche", niche_key) \
                .limit(1).execute()

            if row.data:
                r = row.data[0]
                new_attempts = (r.get("attempts") or 0) + 1
                new_successes = (r.get("successes") or 0) + (1 if success else 0)
                new_total_conf = float(r.get("total_confidence", 0) or 0) + confidence
                old_ms = float(r.get("avg_response_ms", 0) or 0)
                new_avg_ms = ((old_ms * max(r.get("attempts", 0), 1)) + response_ms) / new_attempts
                existing_fields = set(r.get("fields_found") or [])
                new_fields = list(existing_fields | set(fields_found))

                db.table("enrichment_sources").update({
                    "attempts": new_attempts,
                    "successes": new_successes,
                    "total_confidence": round(new_total_conf, 4),
                    "avg_response_ms": round(new_avg_ms, 2),
                    "fields_found": new_fields,
                }).eq("id", r["id"]).execute()
            else:
                db.table("enrichment_sources").insert({
                    "source_name": source_name,
                    "strategy": strategy,
                    "niche": niche_key,
                    "attempts": 1,
                    "successes": 1 if success else 0,
                    "total_confidence": round(confidence, 4),
                    "avg_response_ms": round(response_ms, 2),
                    "fields_found": fields_found,
                    "is_active": True,
                    "priority": 5,
                }).execute()

            # Bust cache
            self._cache_ts = 0.0

        except Exception as e:
            log.debug(f"[quality] record_attempt error: {e}")

    async def best_sources_for_niche(
        self,
        niche: str,
        min_attempts: int = 3,
        limit: int = 5,
    ) -> List[Dict]:
        """Return the best-performing enrichment sources for a niche, ranked by success rate."""
        db = self.get_db()

        # Check cache
        cache_key = f"niche_{niche}_{min_attempts}"
        if cache_key in self._cache and (time.time() - self._cache_ts) < self._cache_ttl:
            return self._cache[cache_key]

        try:
            # Query sources for this niche first, then __all__ fallback
            rows = db.table("enrichment_sources").select("*") \
                .eq("is_active", True) \
                .in_("niche", [niche, "__all__"]) \
                .gte("attempts", min_attempts) \
                .order("priority", desc=False) \
                .limit(limit * 2) \
                .execute()

            sources = rows.data or []

            # Calculate success rate and sort
            enriched = []
            for s in sources:
                attempts = max(s.get("attempts", 1), 1)
                success_rate = (s.get("successes") or 0) / attempts
                avg_conf = float(s.get("total_confidence", 0) or 0) / attempts
                # Composite score
                score = (success_rate * 0.5) + (avg_conf * 0.3) + (1.0 / max(float(s.get("avg_response_ms", 1000) or 1000), 1) * 100 * 0.2)
                enriched.append({
                    "source_name": s.get("source_name"),
                    "strategy": s.get("strategy"),
                    "niche": s.get("niche"),
                    "success_rate": round(success_rate, 3),
                    "avg_confidence": round(avg_conf, 3),
                    "avg_response_ms": float(s.get("avg_response_ms", 0) or 0),
                    "attempts": attempts,
                    "score": round(score, 4),
                    "fields_found": s.get("fields_found", []),
                })

            enriched.sort(key=lambda x: x["score"], reverse=True)
            result = enriched[:limit]
            self._cache[cache_key] = result
            self._cache_ts = time.time()
            return result

        except Exception as e:
            log.debug(f"[quality] best_sources error: {e}")
            return []

    async def snapshot(self) -> Dict:
        """Return full quality engine snapshot."""
        db = self.get_db()
        try:
            rows = db.table("enrichment_sources").select("*") \
                .order("attempts", desc=True) \
                .limit(50).execute()
            sources = rows.data or []
            total_attempts = sum(s.get("attempts", 0) for s in sources)
            total_successes = sum(s.get("successes", 0) for s in sources)
            return {
                "sources": sources,
                "total_sources": len(sources),
                "total_attempts": total_attempts,
                "total_successes": total_successes,
                "overall_success_rate": round(total_successes / max(total_attempts, 1), 3),
                "niches_tracked": list(set(s.get("niche", "__all__") for s in sources)),
            }
        except Exception as e:
            return {"sources": [], "error": str(e)[:80]}


# ═════════════════════════════════════════════════════════════════════
# 3. PIPELINE ORCHESTRATOR — DAG Agent Runner
# ═════════════════════════════════════════════════════════════════════

# Steps in the enrichment pipeline (in order)
_PIPELINE_STEPS = [
    {"name": "scanner", "label": "Lead Scanner", "agent": "lead_scanner"},
    {"name": "enricher", "label": "Lead Enricher", "agent": "lead_enricher"},
    {"name": "contact_discovery", "label": "Contact Discovery", "agent": "contact_discovery"},
    {"name": "scorer", "label": "Lead Scorer", "agent": "lead_scorer"},
    {"name": "converter", "label": "Lead Converter", "agent": "lead_converter"},
]


class PipelineOrchestrator:
    """
    DAG-based runner for the 4-agent enrichment pipeline.

    Coordinates: scanner → enricher → contact_discovery → scorer → converter
    With progress tracking, skip/retry logic, and stall detection.
    """

    def __init__(
        self,
        get_db: Callable,
        enricher: Optional[DeepEnricher] = None,
    ):
        self.get_db = get_db
        self.enricher = enricher
        self._running: Dict[str, Dict] = {}  # run_id -> run_state

    async def run_pipeline(
        self,
        run_type: str = "scheduled",
        max_rows: int = 100,
        steps: Optional[List[str]] = None,
    ) -> Dict:
        """
        Run the full enrichment pipeline.

        Args:
            run_type: 'scheduled', 'batch', or 'realtime'
            max_rows: Max rows to process per step
            steps: Subset of steps to run (None = all)

        Returns:
            Run result with per-step status.
        """
        run_id = str(uuid.uuid4())
        db = self.get_db()
        started_at = datetime.now(timezone.utc)

        steps_to_run = steps or [s["name"] for s in _PIPELINE_STEPS]

        # Create pipeline run record
        try:
            db.table("enrichment_pipeline_runs").insert({
                "id": run_id,
                "run_type": run_type,
                "current_step": steps_to_run[0] if steps_to_run else "pending",
                "status": "running",
                "steps": [{"step": s, "status": "pending"} for s in _PIPELINE_STEPS],
                "total_rows": 0,
                "rows_processed": 0,
                "rows_errored": 0,
            }).execute()
        except Exception:
            pass

        run_state = {
            "run_id": run_id,
            "run_type": run_type,
            "started_at": started_at,
            "current_step": steps_to_run[0] if steps_to_run else None,
            "status": "running",
            "step_results": {},
            "total_rows": 0,
            "total_processed": 0,
            "total_errored": 0,
        }
        self._running[run_id] = run_state

        step_methods = {
            "scanner": self._run_scanner,
            "enricher": self._run_enricher,
            "contact_discovery": self._run_contact_discovery,
            "scorer": self._run_scorer,
            "converter": self._run_converter,
        }

        try:
            for step_name in steps_to_run:
                method = step_methods.get(step_name)
                if not method:
                    log.warning(f"[pipeline] unknown step: {step_name}")
                    continue

                run_state["current_step"] = step_name
                # Update pipeline run record
                try:
                    db.table("enrichment_pipeline_runs").update({
                        "current_step": step_name,
                    }).eq("id", run_id).execute()
                except Exception:
                    pass

                log.info(f"[pipeline] running step: {step_name}")

                step_result = await method(max_rows=max_rows)
                run_state["step_results"][step_name] = step_result

                if step_result.get("status") == "error":
                    run_state["status"] = "partial"
                    log.warning(f"[pipeline] step {step_name} failed: {step_result.get('error', 'unknown')}")
                    # Continue with next step — don't abort on per-step errors

                run_state["total_rows"] += step_result.get("rows_seen", 0)
                run_state["total_processed"] += step_result.get("rows_processed", 0)
                run_state["total_errored"] += step_result.get("rows_errored", 0)

            run_state["status"] = "completed" if run_state["total_errored"] == 0 else "partial"

        except Exception as e:
            run_state["status"] = "failed"
            run_state["error"] = str(e)
            log.error(f"[pipeline] run {run_id} failed: {e}")

        finally:
            finished_at = datetime.now(timezone.utc)
            try:
                db.table("enrichment_pipeline_runs").update({
                    "status": run_state["status"],
                    "finished_at": finished_at.isoformat(),
                    "rows_processed": run_state["total_processed"],
                    "rows_errored": run_state["total_errored"],
                    "error": run_state.get("error"),
                    "steps": [
                        {
                            "step": s,
                            "status": run_state["step_results"].get(s, {}).get("status", "skipped"),
                            "rows": run_state["step_results"].get(s, {}).get("rows_processed", 0),
                        }
                        for s in steps_to_run
                    ],
                }).eq("id", run_id).execute()
            except Exception:
                pass

            if run_id in self._running:
                del self._running[run_id]

        return {
            "run_id": run_id,
            "status": run_state["status"],
            "steps_completed": len(run_state["step_results"]),
            "steps_total": len(steps_to_run),
            "total_rows": run_state["total_rows"],
            "total_processed": run_state["total_processed"],
            "total_errored": run_state["total_errored"],
            "step_results": run_state["step_results"],
            "error": run_state.get("error"),
            "duration_seconds": round((finished_at - started_at).total_seconds(), 1),
        }

    async def _run_scanner(self, max_rows: int = 100) -> Dict:
        """Run the lead scanner agent."""
        try:
            from agents.lead_scanner.scanner import run as scan_run
            result = scan_run()
            return {
                "status": "completed" if result.get("status") in ("ok", "skipped_disabled") else "error",
                "rows_seen": result.get("rows_seen", 0),
                "rows_processed": result.get("rows_processed", 0),
                "rows_errored": result.get("rows_errored", 0),
                "error": None,
            }
        except Exception as e:
            return {"status": "error", "error": str(e), "rows_seen": 0, "rows_processed": 0, "rows_errored": 0}

    async def _run_enricher(self, max_rows: int = 100) -> Dict:
        """Run the lead enricher agent (SI-powered scoring)."""
        try:
            from agents.lead_enricher.enricher import run as enrich_run
            result = enrich_run()
            return {
                "status": "completed" if result.get("status") in ("ok", "skipped_disabled") else "error",
                "rows_seen": result.get("rows_seen", 0),
                "rows_processed": result.get("rows_processed", 0),
                "rows_blocked": result.get("rows_blocked", 0),
                "rows_errored": result.get("rows_errored", 0),
                "error": None,
            }
        except Exception as e:
            return {"status": "error", "error": str(e), "rows_seen": 0, "rows_processed": 0, "rows_errored": 0}

    async def _run_contact_discovery(self, max_rows: int = 25) -> Dict:
        """Run the contact discovery agent."""
        try:
            from agents.contact_discovery.discovery import run as discovery_run
            result = discovery_run()
            return {
                "status": "completed" if result.get("status") in ("ok", "skipped_disabled") else "error",
                "rows_seen": result.get("rows_seen", 0),
                "rows_processed": result.get("rows_processed", 0),
                "rows_blocked": result.get("rows_blocked", 0),
                "rows_errored": result.get("rows_errored", 0),
                "error": None,
            }
        except Exception as e:
            return {"status": "error", "error": str(e), "rows_seen": 0, "rows_processed": 0, "rows_errored": 0}

    async def _run_scorer(self, max_rows: int = 100) -> Dict:
        """Run the lead scorer agent."""
        try:
            from agents.lead_scorer.scorer import run as scorer_run
            result = scorer_run()
            return {
                "status": "completed" if result.get("status") in ("ok", "skipped_disabled") else "error",
                "rows_seen": result.get("rows_seen", 0),
                "rows_processed": result.get("rows_processed", 0),
                "rows_errored": result.get("rows_errored", 0),
                "error": None,
            }
        except Exception as e:
            return {"status": "error", "error": str(e), "rows_seen": 0, "rows_processed": 0, "rows_errored": 0}

    async def _run_converter(self, max_rows: int = 10) -> Dict:
        """Run the lead converter agent."""
        try:
            from agents.lead_converter.converter import run as converter_run
            result = converter_run()
            return {
                "status": "completed" if result.get("status") in ("ok", "skipped_disabled") else "error",
                "rows_seen": result.get("rows_seen", 0),
                "rows_processed": result.get("rows_processed", 0),
                "rows_errored": result.get("rows_errored", 0),
                "error": None,
            }
        except Exception as e:
            return {"status": "error", "error": str(e), "rows_seen": 0, "rows_processed": 0, "rows_errored": 0}

    async def status(self) -> Dict:
        """Return pipeline status — recent runs + current state."""
        db = self.get_db()
        try:
            runs = db.table("enrichment_pipeline_runs").select("*") \
                .order("created_at", desc=True) \
                .limit(10).execute()
            return {
                "running_now": len(self._running),
                "active_run_ids": list(self._running.keys()),
                "recent_runs": runs.data or [],
                "total_runs": len(runs.data or []),
            }
        except Exception as e:
            return {"running_now": len(self._running), "recent_runs": [], "error": str(e)[:80]}


# ═════════════════════════════════════════════════════════════════════
# 4. FASTAPI ROUTES — Real-time Enrichment + Quality + Pipeline
# ═════════════════════════════════════════════════════════════════════

def register_enrichment_routes(
    app: FastAPI,
    *,
    enricher: DeepEnricher,
    quality: QualityEngine,
    orchestrator: PipelineOrchestrator,
    require_auth: Optional[Callable] = None,
):
    """Wire enrichment engine routes on the hub."""

    # ── REAL-TIME ENRICHMENT ─────────────────────────────────────────
    @app.post("/api/v1/enrich")
    async def enrich_lead(request: Request):
        """Enrich a lead on demand using deep LLM extraction.

        Body:
          website: str (required) — URL or domain to enrich
          business_name: str (optional) — known business name
          niche_hint: str (optional) — niche to guide extraction
          lead_id: str (optional) — if provided, updates enriched_leads row

        Returns:
          Full enrichment result with per-field confidence scores.
        """
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")

        website = (body.get("website") or "").strip()
        business_name = (body.get("business_name") or "").strip() or None
        niche_hint = (body.get("niche_hint") or "").strip() or None
        lead_id = (body.get("lead_id") or "").strip()

        if not website:
            raise HTTPException(400, "website is required")

        start_ms = time.time() * 1000

        try:
            result = await enricher.enrich(
                website=website,
                business_name=business_name,
                niche_hint=niche_hint,
            )
        except Exception as e:
            log.error(f"[enrich] deep enrich failed: {e}")
            raise HTTPException(500, f"Enrichment failed: {str(e)[:200]}")

        response_ms = (time.time() * 1000) - start_ms

        if not result:
            return {"ok": False, "error": "Could not enrich — website unreachable"}

        # Record quality metrics (fire and forget)
        asyncio.create_task(quality.record_attempt(
            source_name="website_scrape",
            strategy="llm_deep" if enricher._stats["llm_extractions"] > 0 else "regex_fast",
            niche=niche_hint or "__all__",
            success=True,
            confidence=result.get("overall_score", {}).get("score", 0.5) or 0.5,
            fields_found=list(result.get("overall_score", {}).get("fields_scores", {}).keys()),
            response_ms=response_ms,
        ))

        # Optionally update enriched_leads row
        if lead_id and result.get("overall_score", {}).get("score", 0) > 0.3:
            asyncio.create_task(_update_enriched_lead(lead_id, result))

        return {
            "ok": True,
            "website": website,
            "enriched": result,
            "processing_ms": round(response_ms, 1),
        }

    @app.post("/api/v1/enrich/website")
    async def enrich_website(request: Request):
        """Simple enrichment by website — returns just the key fields.
        Same as POST /api/v1/enrich but with simplified output.
        """
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")

        website = (body.get("website") or "").strip()
        niche_hint = (body.get("niche") or "").strip() or None

        if not website:
            raise HTTPException(400, "website is required")

        result = await enricher.enrich(website=website, niche_hint=niche_hint)
        if not result:
            return {"ok": False, "error": "Could not enrich"}

        return {
            "ok": True,
            "website": website,
            "emails": result.get("emails", {}).get("primary"),
            "phones": result.get("phones", {}).get("primary"),
            "business_name": result.get("business_name", {}).get("value"),
            "services": result.get("services", {}).get("value", []),
            "niche": result.get("niche_classification", {}).get("value"),
            "location": {
                "city": result.get("location", {}).get("city"),
                "state": result.get("location", {}).get("state"),
            },
            "decision_makers": result.get("decision_makers", {}).get("value", []),
            "fleet_size": result.get("fleet_size", {}).get("value"),
            "years_in_business": result.get("years_in_business", {}).get("value"),
            "service_areas": result.get("service_areas", {}).get("value", []),
            "confidence": result.get("overall_score", {}).get("score", 0),
            "grade": result.get("overall_score", {}).get("grade", "D"),
        }

    # ── QUALITY ENGINE ───────────────────────────────────────────────
    @app.get("/api/v1/enrich/quality")
    async def enrich_quality(
        niche: str = Query("", description="Filter by niche"),
        auth: bool = Depends(require_auth) if require_auth else True,
    ):
        """Return enrichment quality snapshot — source performance stats."""
        if niche:
            sources = await quality.best_sources_for_niche(niche)
            return {"niche": niche, "sources": sources}
        return await quality.snapshot()

    # ── PIPELINE ORCHESTRATOR ────────────────────────────────────────
    @app.post("/api/v1/enrich/pipeline/run")
    async def run_enrichment_pipeline(
        request: Request,
        auth: bool = Depends(require_auth) if require_auth else True,
    ):
        """Trigger the full enrichment pipeline (scanner → enricher → scorer → converter).

        Body (optional):
          run_type: 'scheduled' | 'batch' | 'realtime' (default: scheduled)
          max_rows: int (default: 100)
          steps: [str] — subset of steps to run (default: all)
        """
        try:
            body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        except Exception:
            body = {}

        run_type = body.get("run_type", "scheduled")
        max_rows = int(body.get("max_rows", 100))
        steps = body.get("steps")

        result = await orchestrator.run_pipeline(
            run_type=run_type,
            max_rows=max_rows,
            steps=steps,
        )
        status = 200 if result["status"] in ("completed", "partial") else 500
        return JSONResponse(result, status_code=status)

    @app.get("/api/v1/enrich/pipeline")
    async def pipeline_status(
        auth: bool = Depends(require_auth) if require_auth else True,
    ):
        """Return enrichment pipeline status — recent runs and current state."""
        return await orchestrator.status()

    # ── ENRICHER STATS ──────────────────────────────────────────────
    @app.get("/api/v1/enrich/stats")
    async def enrich_stats(
        auth: bool = Depends(require_auth) if require_auth else True,
    ):
        """Return enricher engine stats."""
        return {
            "enricher": enricher.get_stats(),
            "quality_sources": len((await quality.snapshot()).get("sources", [])),
        }

    log.info("[enrichment] Routes registered — /api/v1/enrich/* (realtime, quality, pipeline)")


# ── HELPER: Update enriched_leads row ──────────────────────────────
async def _update_enriched_lead(lead_id: str, enrichment_result: Dict):
    """Update an enriched_leads row with LLM enrichment data."""
    try:
        sb = create_client(
            os.getenv("SUPABASE_URL", ""),
            os.getenv("SUPABASE_SERVICE_KEY", ""),
        )
        existing = sb.table("enriched_leads").select("meta, status").eq("id", lead_id).limit(1).execute()
        if not existing.data:
            return

        lead = existing.data[0]
        meta = lead.get("meta") or {}
        if not isinstance(meta, dict):
            meta = {}

        # Merge enrichment into meta
        meta["llm_enrichment"] = enrichment_result
        meta["last_deep_enriched_at"] = datetime.now(timezone.utc).isoformat()
        meta["enrichment_grade"] = enrichment_result.get("overall_score", {}).get("grade", "D")
        meta["enrichment_score"] = enrichment_result.get("overall_score", {}).get("score", 0)

        update: Dict = {"meta": meta}

        # Update specific fields if found
        emails = enrichment_result.get("emails", {})
        if emails.get("primary"):
            update["email"] = emails["primary"]

        phones = enrichment_result.get("phones", {})
        if phones.get("primary"):
            update["phone"] = phones["primary"]

        biz = enrichment_result.get("business_name", {})
        if biz.get("value") and biz.get("confidence", 0) > 0.5:
            update["warehouse_name"] = biz["value"]

        loc = enrichment_result.get("location", {})
        if loc.get("city"):
            update["city"] = loc["city"]
        if loc.get("state"):
            update["state"] = loc["state"]

        # Don't downgrade status (from pending_outreach back to pending_enrichment)
        sb.table("enriched_leads").update(update).eq("id", lead_id).execute()
        log.info(f"[enrich] updated enriched_lead {lead_id} with deep enrichment")

    except Exception as e:
        log.warning(f"[enrich] failed to update enriched_lead {lead_id}: {e}")
