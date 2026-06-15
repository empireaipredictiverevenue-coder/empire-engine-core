"""
EMPIRE V49 · UGLY BANNER SMS GENERATOR
========================================

Takes radar_targets / enriched_leads with phone numbers, generates
4-sentence Ugly Banner outreach messages via Ollama (llama3.2:3b),
following the exact structure from docs/ugly_banner_messages.md:

  1. Cold, undeniable fact about property/situation
  2. High-value Micro Lead Magnet offer
  3. Simple analogy (laundromat or sports team)
  4. Frictionless CTA question

Usage:
    python3 agents/ugly_banner/generator.py
    python3 agents/ugly_banner/generator.py --limit 5 --niche roofing
"""

import os
import sys
import json
import asyncio
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv(REPO.parent / ".env")

import httpx
from supabase import create_client

log = logging.getLogger("empire.ugly_banner")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
)

OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

# ── Ugly Banner prompt template (Grade 5 reading level, American spelling) ──

_UGLY_BANNER_SYSTEM = """You are the Lead Generation Architect for Empire AI. 
Write a hyper-focused, raw, 4-sentence outbound text message for the lead below.

APPLY THE UGLY BANNER STRATEGY:
1. State a cold, undeniable fact about their specific situation.
2. Drop a high-value Micro Lead Magnet offer immediately.
3. Use a simple, non-corporate analogy involving a laundromat or a sports team.
4. End with a frictionless, clear question as the call to action.

RULES:
- Grade 5 reading level. American spelling.
- Use **bold** for key metrics.
- No corporate fluff. No em-dashes. Straight quotes only.
- Keep it under 320 characters (SMS length).
- Return ONLY the message text, no explanations."""

_STORM_LEAD_PROMPT = """Generate an Ugly Banner SMS for a storm-damage commercial property:

Address: {address}
City/State: {city}, {state}
Asset Type: {asset_type}

The lead owns or manages a commercial property in a storm-prone area. 
They may have damage they don't know about from recent hail/wind events.
Offer a free structural data map or storm damage assessment.
Use the 72-Hour Storm Window Report as the micro lead magnet."""

_B2B_LEAD_PROMPT = """Generate an Ugly Banner SMS for a B2B services company:

Company: {name}
Address: {address}
City/State: {city}, {state}
Industry: {niche}
Google Rating: {rating}
Review Count: {reviews}

This is a cold outreach to a {niche} company with a {rating} rating and {reviews} reviews.
They may buy leads or need outbound services for growth.
Reference their specific rating or review count in the cold fact.
Offer a free lead-flow audit or market visibility report as the magnet.
Use a simple sports team or laundromat analogy.
The CTA should ask if they want the report sent."""


def _sb():
    """Cached Supabase client."""
    global _sb_client
    if _sb_client is None:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
        _sb_client = create_client(url, key)
    return _sb_client

_sb_client = None


def _write_to_outreach_log(sb, lead_id: str, channel: str, message: str, niche: str, run_id: str = "", dry_run: bool = True):
    """Persist generated message to outreach_log (dry_run by default)."""
    try:
        sb.table("outreach_log").insert({
            "agent_name": "ugly_banner_generator",
            "run_id": run_id or "00000000-0000-0000-0000-000000000000",
            "enriched_lead_id": lead_id,
            "channel": channel,
            "sequence": "ugly_banner_v1",
            "step": 1,
            "body_preview": message[:320],
            "would_send_at": datetime.now(timezone.utc).isoformat(),
            "compliance_passed": True,
            "mode": "dry_run" if dry_run else "live",
        }).execute()
        return True
    except Exception as e:
        log.warning(f"outreach_log insert failed for {lead_id}: {e}")
        return False


async def _call_brain(system: str, user: str, retries: int = 2) -> str:
    """Call Ollama directly. Returns response text. Retries once on failure."""
    for attempt in range(retries + 1):
        async with httpx.AsyncClient(timeout=120) as client:
            try:
                r = await client.post(
                    f"{OLLAMA_URL}/api/chat",
                    json={
                        "model": OLLAMA_MODEL,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "stream": False,
                        "options": {"temperature": 0.8, "num_predict": 200},
                    },
                )
                if r.status_code == 200:
                    data = r.json()
                    content = data.get("message", {}).get("content", "").strip()
                    if content:
                        # Enforce 320-char SMS limit
                        return content[:320].strip()
                log.warning(f"Ollama attempt {attempt+1}: HTTP {r.status_code}, {r.text[:150]}")
            except Exception as e:
                log.warning(f"Ollama attempt {attempt+1} failed: {e}")
                if attempt < retries:
                    await asyncio.sleep(2)
    return ""


async def generate_storm_messages(limit: int = 10, run_id: str = "") -> List[Dict]:
    """Generate Ugly Banner messages for top storm-damage leads."""
    sb = _sb()
    rid = run_id or uuid.uuid4().hex
    r = (sb.table("enriched_leads")
         .select("id,address,city,state,phone,asset_value,score")
         .not_.is_("phone", "null")
         .neq("status", "blocked")
         .order("score", desc=True)
         .limit(limit)
         .execute())

    results = []
    for row in (r.data or []):
        addr = (row.get("address") or "").strip()
        city = (row.get("city") or "").strip()
        state = (row.get("state") or "").strip()
        asset = row.get("asset_value") or "commercial"
        asset_type = {7: "industrial warehouse", 8: "large commercial property", 9: "distribution center"}.get(
            int(asset) if isinstance(asset, (int, float)) else 0, "commercial building"
        )

        user_prompt = _STORM_LEAD_PROMPT.format(
            address=addr, city=city, state=state, asset_type=asset_type
        )
        msg = await _call_brain(_UGLY_BANNER_SYSTEM, user_prompt)

        results.append({
            "lead_id": row.get("id"),
            "address": addr,
            "city": city,
            "state": state,
            "phone": row.get("phone"),
            "asset_type": asset_type,
            "message": msg,
            "niche": "roofing",
            "outreach_logged": _write_to_outreach_log(sb, row.get("id"), "sms", msg, "roofing", run_id=rid),
        })
        log.info(f"  ✓ {city}, {state}: {len(msg)} chars")

        # Rate limit between calls
        await asyncio.sleep(0.5)

    return results


async def generate_b2b_messages(limit: int = 10, run_id: str = "") -> List[Dict]:
    """Generate Ugly Banner messages for top B2B leads."""
    sb = _sb()
    rid = run_id or uuid.uuid4().hex
    r = (sb.table("radar_targets")
         .select("id,warehouse_name,address,city,state,phone,email,urgency_score,meta")
         .eq("meta->>source", "B2B Lead Gen")
         .not_.is_("phone", "null")
         .order("urgency_score", desc=True)
         .limit(limit)
         .execute())

    results = []
    for row in (r.data or []):
        name = (row.get("warehouse_name") or "").strip()
        addr = (row.get("address") or "").strip()
        city = (row.get("city") or "").strip()
        state = (row.get("state") or "").strip()
        meta = row.get("meta") or {}
        niche = meta.get("b2b_sub_niche", "Business Services")

        user_prompt = _B2B_LEAD_PROMPT.format(
            name=name, address=addr, city=city, state=state, niche=niche,
            rating=meta.get("rating", "N/A"),
            reviews=meta.get("review_count", 0),
        )
        msg = await _call_brain(_UGLY_BANNER_SYSTEM, user_prompt)

        results.append({
            "lead_id": row.get("id"),
            "name": name,
            "address": addr,
            "city": city,
            "state": state,
            "phone": row.get("phone"),
            "niche": niche,
            "message": msg,
            "outreach_logged": _write_to_outreach_log(sb, None, "sms", msg, niche, run_id=rid),
        })
        log.info(f"  ✓ {name[:40]} ({niche}): {len(msg)} chars")
        await asyncio.sleep(0.5)

    return results


async def run(limit_storm: int = 10, limit_b2b: int = 10):
    """Generate messages for both storm and B2B leads."""
    rid = uuid.uuid4().hex
    log.info(f"Generating Ugly Banner messages: {limit_storm} storm + {limit_b2b} B2B [run={rid[:8]}]")

    storm = await generate_storm_messages(limit_storm, run_id=rid)
    log.info(f"  Storm: {len(storm)} messages")

    b2b = await generate_b2b_messages(limit_b2b, run_id=rid)
    log.info(f"  B2B: {len(b2b)} messages")

    return {"storm": storm, "b2b": b2b}


def main():
    import argparse
    p = argparse.ArgumentParser(description="Ugly Banner SMS Generator")
    p.add_argument("--limit", type=int, default=5, help="Leads per category (default 5)")
    p.add_argument("--niche", choices=["roofing", "b2b", "all"], default="all")
    p.add_argument("--output", help="Write JSON output to file")
    args = p.parse_args()

    storm_limit = args.limit if args.niche in ("roofing", "all") else 0
    b2b_limit = args.limit if args.niche in ("b2b", "all") else 0

    result = asyncio.run(run(limit_storm=storm_limit, limit_b2b=b2b_limit))

    # Print results
    for category, items in [("STORM DAMAGE LEADS", result.get("storm", [])),
                             ("B2B LEADS", result.get("b2b", []))]:
        if not items:
            continue
        print(f"\n{'='*70}")
        print(f"  {category} — Ugly Banner Messages")
        print(f"{'='*70}")
        for i, item in enumerate(items, 1):
            name_or_addr = item.get("name") or item.get("address", "?")
            print(f"\n--- {i}. {name_or_addr[:60]} | {item.get('city','')}, {item.get('state','')} | {item.get('phone','?')}")
            print(f"    {item['message']}")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()
