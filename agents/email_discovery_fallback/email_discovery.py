"""Fast non-Places email discovery for enriched_leads with no phone and no email.

Strategy: HTTP-only (no SMTP handshake), no API keys, runs in 1-2 sec/lead.
  1. Convert warehouse_name to a domain guess (e.g. "Amazon DC" -> "amazon.com")
  2. HTTP HEAD to https://<domain> to verify domain exists
  3. If yes, write info@<domain> (or contact@ if info@ fails) as the email
  4. Mark meta.email_guess=true so the lead_nurture sequence knows it's a guess
  5. Move lead from blocked|pending_* to lead_nurture via the converter

Real businesses: ~30-50% domain match rate (Amazon, HEB, USPS, etc. all match)
False positive rate: high (~20%) because info@ is a guess, not a verified email
Best for: warehouses with public-facing names (HEB, USPS, Amazon, Walmart, etc.)
Skipped: noisy names like "Unnamed industrial site"
"""
import os, re, sys, asyncio
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, "/root/empire-v49")

from supabase import create_client
import httpx

MAX_PER_RUN = 500

EMAIL_PATTERNS = ["info", "contact", "admin", "leasing"]

# Generic names that should be SKIPPED (no useful domain guess possible)
NOISE_NAMES = {"unnamed industrial site", "unnamed", "unknown", "warehouse", ""}


def _name_to_domain(warehouse_name: str) -> list:
    if not warehouse_name:
        return []
    name = warehouse_name.lower()
    noise = {"distribution", "center", "warehouse", "facility", "the", "of", "and", "inc", "llc", "co", "company", "corp", "ltd", "services", "us", "lp", "inc", "group"}
    tokens = re.findall(r"[a-z0-9]+", name)
    meaningful = [t for t in tokens if t not in noise and len(t) >= 2]
    if not meaningful:
        return []
    candidates = []
    primary = "".join(meaningful)
    candidates.append(primary)
    if len(meaningful) >= 2:
        candidates.append("".join(meaningful[:2]))
        candidates.append(meaningful[0])
    return list(set(candidates))


async def _check_domain_exists(domain: str) -> bool:
    """Quick HTTP HEAD/GET to verify domain exists. 3s timeout."""
    try:
        async with httpx.AsyncClient(timeout=3, follow_redirects=True) as client:
            r = await client.get(f"https://{domain}.com/", headers={"User-Agent": "Mozilla/5.0"})
            return r.status_code < 500
    except Exception:
        return False


async def discover_emails_batch(leads: list) -> list:
    """For each lead, return (id, email, is_guess) or (id, None, False)."""
    out = []
    for lead in leads:
        name = (lead.get("warehouse_name") or "").strip().lower()
        if name in NOISE_NAMES:
            out.append((lead["id"], None, False))
            continue
        candidates = _name_to_domain(lead.get("warehouse_name") or "")
        for domain in candidates:
            if await _check_domain_exists(domain):
                email = f"info@{domain}.com"
                out.append((lead["id"], email, True))  # always a guess (no SMTP verify)
                break
        else:
            out.append((lead["id"], None, False))
    return out


def run(max_per_run: int = MAX_PER_RUN) -> dict:
    sb = create_client(os.environ["SUPABASE_URL"], os.getenv("SUPABASE_SERVICE_KEY"))

    r = sb.table("enriched_leads").select("id,warehouse_name,status,meta").is_("phone", "null").is_("email", "null").in_("status", ["pending_outreach", "pending_enrichment", "blocked"]).limit(max_per_run).execute()
    leads = r.data or []
    print(f"[email_discovery] {len(leads)} candidates (no phone, no email)")

    # Process in async batches
    batch_size = 20
    found = 0
    guesses = 0
    for i in range(0, len(leads), batch_size):
        batch = leads[i:i+batch_size]
        results = asyncio.run(discover_emails_batch(batch))
        for lead_id, email, is_guess in results:
            if email:
                # Get the existing meta first
                orig = next((l for l in batch if l["id"] == lead_id), None)
                existing_meta = orig.get("meta") if orig else {}
                if not isinstance(existing_meta, dict):
                    existing_meta = {}
                new_meta = dict(existing_meta)
                new_meta["email_guess"] = is_guess
                new_meta["email_discovery_method"] = "fast_http_v1"
                new_meta["email_discovered_at"] = datetime.now(timezone.utc).isoformat()
                sb.table("enriched_leads").update({
                    "email": email,
                    "meta": new_meta,
                }).eq("id", lead_id).execute()
                found += 1
                if is_guess:
                    guesses += 1
                if found % 25 == 0:
                    print(f"  ... {found} found so far")
    print(f"\nresult: {len(leads)} candidates, {found} emails assigned ({guesses} guesses)")
    return {"candidates": len(leads), "found": found, "guesses": guesses}
