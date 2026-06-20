"""
EMPIRE V49 · CONTRACTOR AGENT-REACH INTEL ENRICHER
===================================================
Runs Agent-Reach multi-source intelligence on contractors that have
real emails (from Clay or phone-matching) but no intel yet.

Channels used per contractor:
  - semantic_search (Exa) — competitive intel, reviews, web presence
  - jina_read          — read contractor's website if URL is available
  - github_search       — only if specialties include tech/software/IT

Results are written to contractors.meta.agent_reach_intel.

Rate-limited: 3.5s sleep between contractors to stay under 20/min
semantic search cap. ~1,000 contractors takes ~1 hour.

Usage:
    python3 scripts/enrich_contractor_agent_reach.py            # dry-run
    python3 scripts/enrich_contractor_agent_reach.py --apply    # write to DB
    python3 scripts/enrich_contractor_agent_reach.py --limit 10 # first 10 only

Integrates with Clay workflow:
    1. Clay enriches contractor emails → updates contractors.email
    2. Run this script → adds multi-source intel to meta.agent_reach_intel
    3. Also chainable via: python3 scripts/enrich_contractor_emails.py --agent-reach
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env")
except ImportError:
    pass

from supabase import create_client

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from products.agent_reach_enrichment import AgentReachEnricher, CHANNELS, TIER_CHANNELS

logging.basicConfig(level=logging.INFO, format="%(asctime)s:%(levelname)s:%(name)s:%(message)s")
log = logging.getLogger("enrich.agent_reach")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Rate limits ─────────────────────────────────────────────────────
# Lowest limit is semantic_search at 20/min = 1 per 3.0s.
# We use 3.5s to provide a safety margin.
RATE_LIMIT_SLEEP = 3.5

# Channels run per contractor (always semantic, optional others)
DEFAULT_CHANNELS = ["semantic_search"]
TECH_CHANNELS = ["semantic_search", "github_search"]  # For IT-adjacent contractors

# Specialties that suggest the contractor might have a GitHub/tech presence
TECH_SPECIALTIES = {
    "software", "it_services", "technology", "web_development",
    "app_development", "data_science", "ai", "machine_learning",
    "cybersecurity", "cloud", "devops", "saas",
}


def get_db():
    return sb


def get_pending_contractors(limit: int = 0) -> list[dict]:
    """Fetch contractors with real emails that haven't been intel-enriched yet.

    A contractor is "pending" if:
      - email is present and NOT a placeholder
      - meta.agent_reach_intel is not set (or empty)
    """
    # Fetch all active contractors with real emails
    r = sb.table("contractors") \
        .select("id,name,email,phone,metro,specialties,meta") \
        .eq("active", True) \
        .not_.is_("email", "null") \
        .limit(2000) \
        .execute()

    all_contractors = r.data or []

    # Filter: real email only (no placeholders)
    pending = []
    for c in all_contractors:
        email = (c.get("email") or "").strip()
        if not email or "placeholder" in email.lower() or "prospector" in email.lower():
            continue

        meta = c.get("meta") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except (json.JSONDecodeError, TypeError):
                meta = {}

        # Skip if already has agent_reach_intel
        if meta.get("agent_reach_intel"):
            continue

        # Parse specialties from JSONB if needed
        specialties = c.get("specialties") or []
        if isinstance(specialties, str):
            try:
                specialties = json.loads(specialties)
            except (json.JSONDecodeError, TypeError):
                specialties = [specialties] if specialties else []

        c["_specialties_parsed"] = specialties if isinstance(specialties, list) else []
        c["_meta_parsed"] = meta
        pending.append(c)

    if limit and limit > 0:
        pending = pending[:limit]

    return pending


def pick_channels(contractor: dict) -> list[str]:
    """Pick the most relevant Agent-Reach channels for this contractor."""
    channels = list(DEFAULT_CHANNELS)  # semantic_search always

    # Add github_search if they're tech-adjacent
    specialties = contractor.get("_specialties_parsed", [])
    if isinstance(specialties, list):
        specs_lower = {s.lower().replace(" ", "_") for s in specialties if isinstance(s, str)}
        if specs_lower & TECH_SPECIALTIES:
            channels.append("github_search")

    return channels


async def enrich_one(
    enricher: AgentReachEnricher,
    contractor: dict,
    dry_run: bool = True,
) -> dict:
    """Run Agent-Reach enrichment for a single contractor."""
    cid = contractor["id"]
    name = contractor.get("name", "Unknown")
    metro = contractor.get("metro", "")

    channels = pick_channels(contractor)
    query = f"{name} {metro} contractor"

    if dry_run:
        # Don't actually call the CLI — just report what would happen
        return {
            "id": cid,
            "name": name,
            "metro": metro,
            "query": query,
            "channels": channels,
            "dry_run": True,
        }

    # ── Live enrichment ──
    try:
        tasks = []
        for ch in channels:
            if ch == "semantic_search":
                tasks.append(enricher.semantic_search(query, max_results=5))
            elif ch == "jina_read":
                tasks.append(enricher.jina_read(query))
            elif ch == "github_search":
                tasks.append(enricher.github_search(name, max_results=5))

        gathered = await asyncio.gather(*tasks, return_exceptions=True)

        results = {}
        for ch, r in zip(channels, gathered):
            if isinstance(r, Exception):
                results[ch] = {"ok": False, "error": str(r)[:120]}
            else:
                results[ch] = r

        return {
            "id": cid,
            "name": name,
            "metro": metro,
            "query": query,
            "channels": channels,
            "results": results,
            "dry_run": False,
        }
    except Exception as e:
        return {
            "id": cid,
            "name": name,
            "error": str(e)[:200],
            "dry_run": False,
        }


def write_to_db(enrichment_results: list[dict]):
    """Write Agent-Reach intel back to contractors.meta."""
    written = 0
    errors = 0
    for er in enrichment_results:
        if er.get("dry_run"):
            continue
        if er.get("error"):
            errors += 1
            continue

        cid = er["id"]
        try:
            # Fetch current meta
            cur = sb.table("contractors").select("meta").eq("id", cid).limit(1).execute()
            existing_meta = cur.data[0].get("meta", {}) if cur.data else {}
            if isinstance(existing_meta, str):
                try:
                    existing_meta = json.loads(existing_meta)
                except (json.JSONDecodeError, TypeError):
                    existing_meta = {}
            if not isinstance(existing_meta, dict):
                existing_meta = {}

            # Store intel under meta.agent_reach_intel
            existing_meta["agent_reach_intel"] = {
                "enriched_at": datetime.now(timezone.utc).isoformat(),
                "query": er.get("query", ""),
                "channels_used": er.get("channels", []),
                "results": er.get("results", {}),
            }

            sb.table("contractors").update({"meta": existing_meta}).eq("id", cid).execute()
            written += 1
        except Exception as e:
            log.warning(f"[agent_reach] write failed for {er.get('name', cid)}: {e}")
            errors += 1

    return written, errors


async def run_enrichment(dry_run: bool = True, limit: int = 0):
    """Main enrichment loop."""
    contractors = get_pending_contractors(limit=limit)
    total = len(contractors)

    if not contractors:
        log.info("No contractors need Agent-Reach enrichment — all up to date")
        return

    log.info(f"{'DRY RUN' if dry_run else 'APPLY'} — {total} contractors pending")
    if not dry_run:
        est_minutes = total * RATE_LIMIT_SLEEP / 60
        log.info(f"Rate limit: {RATE_LIMIT_SLEEP}s/contractor · estimated {est_minutes:.0f} min")

    enricher = AgentReachEnricher(get_db=get_db)
    enrichment_results = []

    for i, c in enumerate(contractors):
        result = await enrich_one(enricher, c, dry_run=dry_run)

        # Progress indicator
        name = c.get("name", "?")[:35]
        channels = result.get("channels", [])
        status = "DRY" if dry_run else "OK"
        if result.get("error"):
            status = "ERR"
        log.info(f"  [{i+1:4d}/{total}] {status} {name:35s} channels={channels}")

        enrichment_results.append(result)

        # Rate-limit sleep (only in live mode)
        if not dry_run and i < total - 1:
            await asyncio.sleep(RATE_LIMIT_SLEEP)

    # ── Write to DB ──
    written = errors = 0
    if not dry_run:
        written, errors = write_to_db(enrichment_results)

    # ── Print summary ──
    total_ok = sum(1 for r in enrichment_results if not r.get("error") and not r.get("dry_run"))
    total_dry = sum(1 for r in enrichment_results if r.get("dry_run"))
    total_err = sum(1 for r in enrichment_results if r.get("error"))

    channel_usage = {}
    for r in enrichment_results:
        for ch in r.get("channels", []):
            channel_usage[ch] = channel_usage.get(ch, 0) + 1

    print()
    print("=" * 60)
    print(f"  CONTRACTOR AGENT-REACH INTEL {'(DRY RUN)' if dry_run else '(APPLIED)'}")
    print("=" * 60)
    print(f"  Contractors scanned:          {total}")
    print(f"  Successfully enriched:        {total_ok}")
    print(f"  Dry run (no call):            {total_dry}")
    print(f"  Errors:                       {total_err}")
    print(f"  Channel usage:")
    for ch, count in sorted(channel_usage.items()):
        print(f"    {ch:25s} {count:4d}")
    if not dry_run:
        print(f"  Written to DB:                {written}")
        print(f"  Write errors:                 {errors}")
    print()

    # Show sample results
    if enrichment_results:
        print("  SAMPLE RESULTS:")
        for r in enrichment_results[:5]:
            name = r.get("name", "?")[:35]
            if r.get("dry_run"):
                print(f"    [DRY] {name:35s} → {r.get('channels', [])}")
                continue
            if r.get("error"):
                print(f"    [ERR] {name:35s} → {r.get('error', '')[:60]}")
                continue
            # Show channel results summary
            results = r.get("results", {})
            for ch, cr in results.items():
                if cr.get("ok"):
                    data = cr.get("data", {})
                    if isinstance(data, dict) and "text" in data:
                        size = len(data["text"])
                        print(f"    [OK]  {name:35s} {ch}: {size} chars")
                    elif isinstance(data, dict) and "items" in data:
                        print(f"    [OK]  {name:35s} {ch}: {len(data['items'])} items")
                    else:
                        print(f"    [OK]  {name:35s} {ch}: data received")
                else:
                    print(f"    [ERR] {name:35s} {ch}: {cr.get('error', '?')[:40]}")
        if len(enrichment_results) > 5:
            print(f"    ... and {len(enrichment_results) - 5} more")

    return {
        "dry_run": dry_run,
        "total_scanned": total,
        "total_ok": total_ok,
        "total_errors": total_err,
        "written": written,
        "write_errors": errors,
        "channel_usage": channel_usage,
    }


if __name__ == "__main__":
    dry_run = "--apply" not in sys.argv
    limit = 0
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        if idx + 1 < len(sys.argv):
            limit = int(sys.argv[idx + 1])

    result = asyncio.run(run_enrichment(dry_run=dry_run, limit=limit))
    action = "APPLIED" if not result["dry_run"] else "DRY RUN"
    next_step = "--apply" if result["dry_run"] else "(already applied)"
    print(f"\n{action} — use {next_step} to {'write to DB' if result['dry_run'] else 're-run'}")
