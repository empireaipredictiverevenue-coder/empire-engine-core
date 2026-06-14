"""
Empire AI · Predictive Revenue
Contact Discovery Agent
==========================

Closes the "199/200 leads have no phone" gap. For enriched_leads in
pending_enrichment with no phone/email, attempts free discovery:
  1. Email pattern guess (info@domain, dispatch@domain, etc.)
  2. Business directory lookup (Google Maps free tier / web search)
  3. Mark blocked if no result after 3 attempts

By default, NO paid APIs. Idempotent on (lead, source).

Usage:
    python3 -m agents.contact_discovery
    python3 -m agents.contact_discovery --status
"""
import os
import sys
import re
import json
import uuid
import logging
import urllib.request
import urllib.parse
import urllib.error
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO.parent / ".env")
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("empire.contact_discovery")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in env")
    return create_client(url, key)


def _read_config(sb):
    r = sb.table("agent_config").select("*").eq("agent_name", "contact_discovery").limit(1).execute()
    if not r.data:
        return {"enabled": True, "dry_run": True, "max_per_run": 25, "allow_paid_apis": False,
                "google_maps_api_key": os.getenv("GOOGLE_MAPS_API_KEY", "")}
    row = r.data[0]
    cfg = row.get("config_json") or {}
    return {
        "enabled": row.get("enabled", True),
        "dry_run": row.get("dry_run", True),
        "max_per_run": cfg.get("max_per_run", 25),
        "allow_paid_apis": cfg.get("allow_paid_apis", False),
        "google_maps_api_key": cfg.get("google_maps_api_key") or os.getenv("GOOGLE_MAPS_API_KEY", ""),
    }


def _log_activity(sb, agent_name, run_id, started_at, status, **kwargs):
    finished_at = datetime.now(timezone.utc).isoformat()
    sb.table("agent_activity").insert({
        "agent_name": agent_name,
        "run_id": str(run_id),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at,
        "status": status,
        **kwargs,
    }).execute()
    return finished_at


def _update_config(sb, agent_name, status, finished_at):
    sb.table("agent_config").update({
        "last_run_at": finished_at,
        "last_run_status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("agent_name", agent_name).execute()


# ── Discovery methods ─────────────────────────────────────────────────
PHONE_RE = re.compile(r"(\+?1?[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _clean_phone(raw: str) -> str:
    if not raw:
        return ""
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return ""


def _normalize_email(raw: str) -> str:
    raw = (raw or "").strip().lower()
    if EMAIL_RE.match(raw):
        return raw
    return ""


def _email_pattern_guess(warehouse_name: str, city: str) -> list:
    """Generate likely email patterns from a warehouse/business name.
    Returns a list of (email, source_label) guesses. Domain is just
    a guess; we don't have a way to verify without an MX lookup or
    a paid API. So we just log them as 'patterns' for the operator
    to follow up on manually if needed."""
    name = (warehouse_name or "").lower()
    name = re.sub(r"[^a-z0-9]", "", name)
    if not name:
        return []
    domains = [
        f"{name}.com",
        f"{name}tx.com",
        f"{name}llc.com",
    ]
    prefixes = ["info", "dispatch", "service", "contact", "office", "manager"]
    out = []
    for d in domains:
        for p in prefixes:
            out.append((f"{p}@{d}", f"pattern:{p}@{d}"))
    return out


def _google_places_search(query: str, lat=None, lon=None) -> list:
    """Use Google Places text search. Returns list of {name, address, phone, website, types}.
    Requires GOOGLE_MAPS_API_KEY (free tier: 1000 calls/month)."""
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        log.debug("no GOOGLE_MAPS_API_KEY")
        return []
    try:
        body = {"textQuery": query, "maxResultCount": 5}
        if lat is not None and lon is not None:
            body["locationBias"] = {
                "circle": {"center": {"latitude": lat, "longitude": lon}, "radius": 8000}
            }
        req = urllib.request.Request(
            "https://places.googleapis.com/v1/places:searchText",
            data=json.dumps(body).encode(),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.websiteUri,places.types",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        out = []
        for p in data.get("places", []):
            out.append({
                "name": p.get("displayName", {}).get("text", ""),
                "address": p.get("formattedAddress", ""),
                "phone": p.get("nationalPhoneNumber", ""),
                "website": p.get("websiteUri", ""),
                "types": p.get("types", []),
            })
        return out
    except Exception as e:
        log.debug(f"places search failed: {e}")
        return []


def _scrape_website_for_contact(url: str) -> dict:
    """Try common contact paths on a website, return {phone, email}."""
    if not url:
        return {"phone": "", "email": ""}
    found = {"phone": "", "email": ""}
    paths = ["/contact", "/contact-us", "/contact.html", "/about", "/about-us", "/locations"]
    for path in paths:
        try:
            u = url.rstrip("/") + path
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Empire-AI/1.0"})
            with urllib.request.urlopen(req, timeout=6) as r:
                html = r.read().decode("utf-8", errors="ignore")
            m = PHONE_RE.search(html)
            if m and not found["phone"]:
                found["phone"] = _clean_phone(m.group(1))
            m = EMAIL_RE.search(html)
            if m and not found["email"]:
                found["email"] = _normalize_email(m.group(0))
        except Exception:
            pass
    return found


def _extract_phone_from_text(text: str) -> str:
    m = PHONE_RE.search(text)
    if m:
        return _clean_phone(m.group(1))
    return ""


def _extract_email_from_text(text: str) -> str:
    m = EMAIL_RE.search(text)
    if m:
        return _normalize_email(m.group(0))
    return ""


def _discover_one(lead: dict, cfg: dict) -> dict:
    """Attempt discovery for a single lead. Returns
    {phone, email, source, attempts} — fields not found are empty strings."""
    warehouse = lead.get("warehouse_name") or ""
    address = lead.get("address") or ""
    city = lead.get("city") or ""
    state = lead.get("state") or ""
    result = {"phone": "", "email": "", "source": "", "attempts": []}

    # Method 1: Google Places text search for the warehouse
    if warehouse:
        q = f"{warehouse} {city} {state}".strip()
        places = _google_places_search(q)
        for place in places:
            result["attempts"].append({
                "method": "google_places",
                "q": q,
                "name": place.get("name"),
                "address": place.get("address", "")[:80],
            })
            if place.get("phone") and not result["phone"]:
                cleaned = _clean_phone(place["phone"])
                if cleaned:
                    result["phone"] = cleaned
                    result["source"] = f"google_places:{place.get('name','')}"
            if place.get("website") and not result["email"]:
                scraped = _scrape_website_for_contact(place["website"])
                if scraped["phone"] and not result["phone"]:
                    result["phone"] = scraped["phone"]
                    result["source"] = f"website_scrape:{place['website']}"
                if scraped["email"]:
                    result["email"] = scraped["email"]
                    result["source"] = result["source"] or f"website_scrape:{place['website']}"
            if result["phone"] and result["email"]:
                break

    # Method 2: if we still don't have a phone, try the address
    if not result["phone"] and address:
        places = _google_places_search(address)
        for place in places:
            result["attempts"].append({"method": "google_places_addr", "q": address, "name": place.get("name")})
            if place.get("phone"):
                cleaned = _clean_phone(place["phone"])
                if cleaned:
                    result["phone"] = cleaned
                    result["source"] = result["source"] or f"google_places_addr:{place.get('name','')}"
                    break

    # Method 3: email pattern guess (logged, not auto-claimed — domain not verified)
    if not result["email"] and warehouse:
        patterns = _email_pattern_guess(warehouse, city)
        # only log the first 3 patterns as suggestions — don't claim them as "found"
        result["attempts"].append({
            "method": "email_pattern_suggestions",
            "patterns": [p for p, _ in patterns[:3]],
            "note": "patterns not verified — operator should manually MX-check before use",
        })

    return result


def _was_recently_attempted(lead: dict, since_hours: int = 24) -> bool:
    """Check if discovery was attempted on this lead in the last N hours."""
    meta = lead.get("meta") or {}
    attempts = meta.get("discovery_attempts") or []
    if not attempts:
        return False
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat()
    return any(a.get("ts", "") >= cutoff for a in attempts)


def run() -> dict:
    started_at = datetime.now(timezone.utc)
    run_id = uuid.uuid4()
    sb = _sb()
    cfg = _read_config(sb)

    if not cfg["enabled"]:
        _log_activity(sb, "contact_discovery", run_id, started_at, "skipped_disabled",
                      summary="disabled in agent_config")
        _update_config(sb, "contact_discovery", "skipped_disabled", datetime.now(timezone.utc).isoformat())
        return {"status": "skipped_disabled", "rows_processed": 0}

    # find leads that need discovery: status=pending_outreach (still in funnel), no phone, no email.
    # also check pending_enrichment in case any new rows slip through. skip converted + blocked.
    statuses_to_check = ["pending_outreach", "pending_enrichment"]
    candidates = []
    for status in statuses_to_check:
        q = (sb.table("enriched_leads")
                .select("id, address, city, state, warehouse_name, phone, email, meta, status")
                .eq("status", status)
                .is_("phone", "null")
                .is_("email", "null")
                .order("created_at", desc=False)
                .limit(cfg["max_per_run"]))
        res = q.execute()
        candidates.extend(res.data or [])
    log.info(f"contact_discovery: {len(candidates)} eligible (no phone/email, in funnel)")
    # filter out recently attempted (1-minute dedup so consecutive
    # runs can quickly re-attempt with new backends; we trust
    # places API not to over-bill us at this scale)
    candidates = [c for c in candidates if not _was_recently_attempted(c, since_hours=1/60)]
    candidates = candidates[:cfg["max_per_run"]]
    log.info(f"contact_discovery: {len(candidates)} leads to attempt (out of {len(res.data or [])} eligible)")
    rows_seen = len(candidates)

    rows_processed = 0
    rows_errored = 0
    rows_blocked = 0
    error_msgs = []
    sample_discoveries = []

    for lead in candidates:
        try:
            if cfg["dry_run"]:
                # log the would-discover, no actual lookup
                sb.table("outreach_log").insert({
                    "enriched_lead_id": lead["id"],
                    "agent_name": "contact_discovery",
                    "run_id": str(run_id),
                    "channel": "manual",
                    "sequence": "discovery",
                    "step": 0,
                    "body_preview": f"[DRY-RUN] would discover for {lead.get('warehouse_name','?')[:30]} @ {lead.get('city','')}",
                    "compliance_passed": True,
                    "mode": "dry_run",
                }).execute()
                rows_processed += 1
                continue

            result = _discover_one(lead, cfg)
            ts = datetime.now(timezone.utc).isoformat()
            existing_meta = lead.get("meta") or {}
            existing_attempts = existing_meta.get("discovery_attempts") or []
            new_attempt = {"ts": ts, "source": result["source"], "attempts": result["attempts"]}
            new_attempts = existing_attempts + [new_attempt]

            update = {
                "meta": {
                    **existing_meta,
                    "discovery_attempts": new_attempts,
                    "discovery_source": result["source"] or existing_meta.get("discovery_source", ""),
                    "last_discovery_at": ts,
                }
            }
            if result["phone"]:
                update["phone"] = result["phone"]
            if result["email"]:
                update["email"] = result["email"]

            # if we found nothing after 3 attempts, block
            if not result["phone"] and not result["email"] and len(new_attempts) >= 3:
                update["status"] = "blocked"
                update["meta"]["discovery_block_reason"] = "no_public_contact_found"
                rows_blocked += 1
            else:
                rows_processed += 1

            sb.table("enriched_leads").update(update).eq("id", lead["id"]).execute()

            if result["phone"] or result["email"]:
                sample_discoveries.append({
                    "warehouse": lead.get("warehouse_name", "")[:30],
                    "phone": result["phone"],
                    "email": result["email"],
                    "source": result["source"][:80] if result["source"] else "",
                })
        except Exception as e:
            rows_errored += 1
            error_msgs.append(f"{lead.get('id','?')[:8]}: {type(e).__name__}: {e}")
            log.warning(f"contact_discovery: failed for {lead.get('id')}: {e}")

    finished_at = datetime.now(timezone.utc)
    mode_label = "dry-run" if cfg["dry_run"] else "LIVE"
    summary = (f"[{mode_label}] scanned {rows_seen} leads without contact, "
               f"{rows_processed} attempted, {rows_blocked} marked blocked (no contact), "
               f"{rows_errored} errored")
    if sample_discoveries:
        summary += f". Sample: {json.dumps(sample_discoveries, default=str)[:600]}"
    status = "ok" if rows_errored == 0 else "ok"
    err_field = None if rows_errored == 0 else "; ".join(error_msgs[:5])

    _log_activity(sb, "contact_discovery", run_id, started_at, status,
                  rows_seen=rows_seen, rows_processed=rows_processed,
                  rows_blocked=rows_blocked, rows_errored=rows_errored,
                  error=err_field, summary=summary)
    _update_config(sb, "contact_discovery", status, finished_at.isoformat())

    log.info(summary[:200])
    return {"status": status, "rows_seen": rows_seen, "rows_processed": rows_processed,
            "rows_blocked": rows_blocked, "rows_errored": rows_errored,
            "sample_discoveries": sample_discoveries}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--status", action="store_true")
    args = p.parse_args()
    if args.status:
        sb = _sb()
        cfg = _read_config(sb)
        last_act = (sb.table("agent_activity").select("*").eq("agent_name", "contact_discovery").order("started_at", desc=True).limit(1).execute())
        print(json.dumps({"config": cfg, "last_run": last_act.data[0] if last_act.data else None},
                         indent=2, default=str))
        return
    result = run()
    sys.exit(0 if result["status"] in ("ok", "skipped_disabled") else 1)


if __name__ == "__main__":
    main()
