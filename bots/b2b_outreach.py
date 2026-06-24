"""
EMPIRE V49 · B2B OUTREACH DRAFTER
==================================
Generates personalized email + SMS outreach drafts for B2B leads.
Pulls from b2b_leads table, enriches with site_content data, drafts
via local Ollama, and stores in email_drafts table.

Usage:
    python3 bots/b2b_outreach.py --limit 10 --dry-run
    python3 bots/b2b_outreach.py --lead-id <uuid>
    python3 bots/b2b_outreach.py --niche "Commercial Roofing" --metro "Dallas"
"""

import os
import sys
import json
import time
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, List

sys.path.insert(0, "/root/empire-v49")
try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("b2b.outreach")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

# ── Config ───────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("AI_MODEL_DRAFT", "llama3.2:3b")

_sb = None

def _get_sb():
    global _sb
    if _sb is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
        _sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _sb


# ── DRAFTING SYSTEM PROMPTS ──────────────────────────────────────────

EMAIL_SYSTEM = """You are a senior B2B sales copywriter for Empire AI, a lead generation platform
that connects businesses with qualified prospects in their industry.

You draft concise, personalized outreach emails to business owners and decision-makers.

STRICT RULES:
- Return ONLY valid JSON with keys: subject, body
- Body MUST be plain text, no HTML, no markdown
- Body MUST be under 120 words
- Body MUST mention the recipient's industry/niche specifically
- Body MUST include one data point about their business to show it's not spam
- Body MUST end with a single clear CTA (reply or schedule a call)
- Tone: professional, direct, respectful of recipient's time
- Mention Empire AI as a lead generation platform
- NO exclamation marks, NO all-caps, NO emoji
- NO fake urgency ("limited time", "act now")
- NO guarantee of results
- Sign as "Empire AI · Business Development"
"""

SMS_SYSTEM = """You are a B2B SMS copywriter for Empire AI, a lead generation platform.
Write ultra-short SMS outreach messages to business owners.

STRICT RULES:
- Return ONLY valid JSON with keys: body
- Body under 160 chars (SMS limit)
- Professional, not pushy
- Include company/industry reference
- End with reply-or-visit CTA
- NO emoji, NO all-caps, NO shortened URLs
- Include "empire-ai.co.uk" once
"""


async def query_llm(prompt: str, system: str = "", temperature: float = 0.5) -> str:
    """Query LLM for drafting — Groq → xAI/Grok → Anthropic → OpenAI → Ollama."""
    groq_key = os.getenv("GROQ_API_KEY", "")
    xai_key = os.getenv("XAI_API_KEY", "")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    openai_key = os.getenv("OPENAI_API_KEY", "")

    # ── Groq path (free tier, fast Llama inference) ────────────
    if groq_key and len(groq_key) > 10:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                import requests as _req
                messages = []
                if system:
                    messages.append({"role": "system", "content": system})
                messages.append({"role": "user", "content": prompt})
                groq_model = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
                r = _req.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                    json={
                        "model": groq_model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": 512,
                    },
                    timeout=60,
                )
                if r.status_code == 200:
                    content = r.json()["choices"][0]["message"]["content"]
                    log.info(f"[b2b_outreach] Groq OK — {len(content)} chars")
                    return content
                if r.status_code == 429:
                    delay = 2 ** attempt  # 1s, 2s, 4s backoff
                    log.warning(f"[b2b_outreach] Groq 429 (rate limit), retry {attempt+1}/{max_retries} in {delay}s")
                    time.sleep(delay)
                    continue
                log.warning(f"[b2b_outreach] Groq {r.status_code}: {r.text[:200]}")
                break
            except Exception as e:
                log.warning(f"[b2b_outreach] Groq failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)
                else:
                    break

    # ── xAI / Grok path (free tier, OpenAI-compatible) ─────────
    if xai_key and len(xai_key) > 10:
        try:
            import requests as _req
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            xai_model = os.environ.get("XAI_MODEL", "grok-3-mini")
            r = _req.post(
                "https://api.x.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {xai_key}", "Content-Type": "application/json"},
                json={
                    "model": xai_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": 512,
                },
                timeout=60,
            )
            if r.status_code == 200:
                content = r.json()["choices"][0]["message"]["content"]
                log.info(f"[b2b_outreach] xAI/Grok OK — {len(content)} chars")
                return content
            log.warning(f"[b2b_outreach] xAI/Grok {r.status_code}: {r.text[:200]}")
        except Exception as e:
            log.warning(f"[b2b_outreach] xAI/Grok failed: {e}")

    # ── Anthropic path (best quality, uses claude-3-haiku) ─────
    if anthropic_key and len(anthropic_key) > 10:
        try:
            import requests as _req
            _sys = f"{system}\n\nReturn ONLY valid JSON, no preamble." if system else "Return ONLY valid JSON, no preamble."
            r = _req.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": anthropic_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                json={
                    "model": "claude-3-haiku-20240307",
                    "max_tokens": 512,
                    "temperature": temperature,
                    "system": _sys,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=60,
            )
            if r.status_code == 200:
                content = r.json()["content"][0]["text"]
                log.info(f"[b2b_outreach] Anthropic OK — {len(content)} chars")
                return content
            log.warning(f"[b2b_outreach] Anthropic {r.status_code}: {r.text[:200]}")
        except Exception as e:
            log.warning(f"[b2b_outreach] Anthropic failed: {e}")

    # ── OpenAI path (fast, reliable) ────────────────────────────
    if openai_key and len(openai_key) > 10:
        try:
            import requests as _req
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            r = _req.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": 512,
                },
                timeout=60,
            )
            if r.status_code == 200:
                content = r.json()["choices"][0]["message"]["content"]
                log.info(f"[b2b_outreach] OpenAI OK — {len(content)} chars")
                return content
            log.warning(f"[b2b_outreach] OpenAI {r.status_code}: {r.text[:200]}")
        except Exception as e:
            log.warning(f"[b2b_outreach] OpenAI failed: {e}")

    # ── Ollama fallback ─────────────────────────────────────────
    import asyncio
    def _ollama():
        try:
            import requests as _req
            r = _req.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "system": system,
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": 256},
                },
                timeout=60,
            )
            if r.status_code == 200:
                return r.json().get("response", "")
        except Exception as e:
            log.error(f"[b2b_outreach] Ollama call failed: {e}")
        return ""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _ollama)


async def get_lead_enrichment(lead_id: str) -> Dict:
    """Fetch site_content enrichment for a lead."""
    try:
        sb = _get_sb()
        r = sb.table("site_content").select("page_type,raw_text,headings,pricing_mentions,cta_buttons,contact_info").eq("b2b_lead_id", lead_id).limit(5).execute()
        if r.data:
            pages = r.data
            has_pricing = any(p.get("pricing_mentions") for p in pages)
            has_contact = any(p.get("contact_info") for p in pages)
            service_pages = [p for p in pages if p.get("page_type") == "services"]
            contact_pages = [p for p in pages if p.get("page_type") == "contact"]
            return {
                "has_site": True,
                "pages_scraped": len(pages),
                "has_pricing": has_pricing,
                "has_contact_form": has_contact,
                "service_pages": len(service_pages),
                "contact_pages": len(contact_pages),
            }
    except Exception:
        pass
    return {"has_site": False}


async def draft_email_for_lead(lead: Dict, enrichment: Dict = None) -> Optional[Dict]:
    """Generate a personalized email draft for one B2B lead."""
    company = lead.get("company_name", "your business")
    niche = lead.get("niche", "your industry")
    metro = lead.get("metro", "your area")
    city = lead.get("city", "") or metro
    website = lead.get("website", "")
    email = lead.get("email", "")

    if not email:
        return None

    enrich = enrichment or {}
    site_bits = ""
    if enrich.get("has_site"):
        site_bits = (
            f"Their website has {enrich.get('service_pages', 0)} service pages "
            f"and {'has' if enrich.get('has_pricing') else 'no visible'} pricing info. "
        )

    prompt = f"""Draft a B2B outreach email:

COMPANY: {company}
INDUSTRY: {niche}
LOCATION: {city}, {metro or ''}
WEBSITE: {website}
{site_bits}

Research context: This is a {niche} business in {city}. They may benefit from
qualified lead generation in their industry. Empire AI provides verified,
industry-specific leads to help businesses grow.

Return JSON only, no preamble."""

    result = await query_llm(prompt, EMAIL_SYSTEM, temperature=0.5)
    if not result:
        return None

    try:
        clean = result.strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()
        draft = json.loads(clean)

        subject = draft.get("subject", f"Lead generation for {company}")
        body = draft.get("body", "")

        if not body:
            return None

        return {
            "to_email": email,
            "subject": subject[:200],
            "body": body[:3000],
            "company": company,
            "niche": niche,
            "metro": metro,
            "channel": "email",
        }
    except (json.JSONDecodeError, IndexError):
        return None


async def draft_sms_for_lead(lead: Dict) -> Optional[Dict]:
    """Generate a short SMS draft for one B2B lead."""
    company = lead.get("company_name", "your business")
    niche = lead.get("niche", "your industry")
    city = lead.get("city", "")
    phone = lead.get("phone", "")

    if not phone:
        return None

    prompt = (
        f"Company: {company}\n"
        f"Industry: {niche}\n"
        f"City: {city}\n"
        f"Write one short SMS outreach message. JSON only: {{\"body\": \"...\"}}"
    )

    result = await query_llm(prompt, SMS_SYSTEM, temperature=0.4)
    if not result:
        return None

    try:
        clean = result.strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()
        draft = json.loads(clean)
        body = draft.get("body", "")
        if body:
            return {
                "to_phone": phone,
                "body": body[:160],
                "company": company,
                "niche": niche,
                "channel": "sms",
            }
    except (json.JSONDecodeError, IndexError):
        pass
    return None


async def save_draft(draft: Dict, lead_id: str) -> Optional[str]:
    """Save a draft to the email_drafts table."""
    try:
        sb = _get_sb()
        row = {
            "to_email": draft.get("to_email") or "",
            "subject": draft.get("subject", ""),
            "body": draft.get("body", ""),
            "status": "pending",
            "meta": json.dumps({
                "source": "b2b_outreach",
                "channel": draft.get("channel", "email"),
                "company": draft.get("company"),
                "niche": draft.get("niche"),
                "lead_id": lead_id,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }),
        }
        r = sb.table("email_drafts").insert(row).execute()
        draft_id = (r.data or [{}])[0].get("id")
        if draft_id:
            log.info(f"[b2b_outreach] draft saved: {draft_id[:8]} — {draft.get('company')}")
        return draft_id
    except Exception as e:
        log.warning(f"[b2b_outreach] save error: {e}")
        return None


async def draft_for_lead(lead_id: str, channels: List[str] = None) -> Dict:
    """Draft outreach for a single B2B lead. Returns dict with email/sms drafts."""
    channels = channels or ["email", "sms"]
    try:
        sb = _get_sb()
        r = sb.table("b2b_leads").select("*").eq("id", lead_id).limit(1).execute()
        if not r.data:
            return {"ok": False, "error": "lead not found", "lead_id": lead_id}
        lead = r.data[0]

        enrichment = await get_lead_enrichment(lead_id)
        result = {"ok": True, "lead_id": lead_id, "company": lead.get("company_name"), "drafts": []}

        if "email" in channels:
            email_draft = await draft_email_for_lead(lead, enrichment)
            if email_draft:
                draft_id = await save_draft(email_draft, lead_id)
                if draft_id:
                    result["drafts"].append({"channel": "email", "draft_id": draft_id, "subject": email_draft["subject"]})

        if "sms" in channels:
            sms_draft = await draft_sms_for_lead(lead)
            if sms_draft:
                draft_id = await save_draft(sms_draft, lead_id)
                if draft_id:
                    result["drafts"].append({"channel": "sms", "draft_id": draft_id, "preview": sms_draft["body"][:80]})

        return result
    except Exception as e:
        return {"ok": False, "error": str(e), "lead_id": lead_id}


async def draft_batch(limit: int = 10, niche: str = "", metro: str = "", dry_run: bool = False, delay: float = 0.3, skip_existing: bool = False) -> Dict:
    """Draft outreach for a batch of B2B leads. Optionally skips leads that already have drafts."""
    try:
        sb = _get_sb()

        # ── Build skip-set from existing drafts ───────────────────
        existing_lead_ids = set()
        if skip_existing:
            try:
                r_existing = sb.table("email_drafts").select("meta").limit(2000).execute()
                for d in (r_existing.data or []):
                    m = d.get("meta") or {}
                    if isinstance(m, str):
                        m = json.loads(m)
                    if m.get("source") == "b2b_outreach":
                        lid = m.get("lead_id", "")
                        if lid:
                            existing_lead_ids.add(lid)
                log.info(f"[b2b_outreach] --skip-existing: {len(existing_lead_ids)} leads already drafted")
            except Exception as e:
                log.warning(f"[b2b_outreach] skip-existing query failed: {e}")

        query = sb.table("b2b_leads").select("id,company_name,email,phone,niche,metro").not_.is_("email", "null").order("lead_score", desc=True).limit(limit)

        if niche:
            query = query.eq("niche", niche)
        if metro:
            query = query.eq("metro", metro)

        r = query.execute()
        leads = r.data or []

        results = {"total": len(leads), "drafted": 0, "skipped_no_email": 0, "skipped_existing": 0, "failed": 0, "dry_run": dry_run}
        for lead in leads:
            if not lead.get("email") and not lead.get("phone"):
                results["skipped_no_email"] += 1
                continue

            if skip_existing and lead["id"] in existing_lead_ids:
                results["skipped_existing"] += 1
                continue

            if dry_run:
                results["drafted"] += 1
                continue

            result = await draft_for_lead(lead["id"])
            if result.get("ok") and result.get("drafts"):
                results["drafted"] += 1
            else:
                results["failed"] += 1

            if delay > 0:
                await asyncio.sleep(delay)

        log.info(f"[b2b_outreach] batch complete: {results}")
        return results
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── CLI ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="B2B Outreach Drafter")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--niche", type=str, default="")
    ap.add_argument("--metro", type=str, default="")
    ap.add_argument("--lead-id", type=str, default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--delay", type=float, default=0.3, help="Seconds between leads to avoid rate limiting")
    ap.add_argument("--skip-existing", action="store_true", help="Skip leads that already have b2b_outreach drafts")
    args = ap.parse_args()

    if args.lead_id:
        result = asyncio.run(draft_for_lead(args.lead_id))
        print(json.dumps(result, indent=2))
    else:
        result = asyncio.run(draft_batch(
            limit=args.limit,
            niche=args.niche,
            metro=args.metro,
            dry_run=args.dry_run,
            delay=args.delay,
            skip_existing=args.skip_existing,
        ))
        print(json.dumps(result, indent=2))
