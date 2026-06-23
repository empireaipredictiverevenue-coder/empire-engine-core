"""Apollo.io skip-trace using FREE-TIER endpoints only.

organizations/search is available on free plans. People endpoints
(people/match, people/search, mixed_people/search) require paid.

Strategy: org search -> get primary_domain -> MX-validated email
patterns (info@, contact@, etc). Reuses the pattern guessing
from empire_vonage_email.py.
"""
import os
import sys
import re
import json
import time
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "agents"))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO / ".env")
except ImportError:
    pass

from supabase import create_client
from empire_vonage_email import _smtp_validate

log = logging.getLogger("empire.apollo_skip_trace")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

APOLLO_BASE = "https://api.apollo.io/v1"
EMAIL_PATTERNS = ["info", "contact", "office", "hello", "sales", "team", "admin", "support"]


def _sb():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def _apollo_post(path: str, body: dict) -> dict:
    key = os.environ.get("APOLLO_API_KEY")
    if not key:
        return {"error": "no APOLLO_API_KEY in env"}
    try:
        req = urllib.request.Request(
            f"{APOLLO_BASE}{path}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        req.add_header("x-api-key", key)
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            body_text = e.read()[:300].decode("utf-8", errors="replace")
            return {"error": f"HTTP {e.code}: {body_text}"}
        except Exception:
            return {"error": f"HTTP {e.code}"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def _extract_org_keywords(full: str) -> str:
    """Strip corporate suffixes + category words. 'Credit Repair New Orleans LA' -> 'Credit Repair'."""
    if not full:
        return ""
    # Remove common city/state suffixes for generic names
    city_state_kw = [
        r"\s+(New Orleans|Atlanta|Dallas|Houston|Chicago|Miami|Phoenix|Denver|Seattle|Detroit|Boston|Philadelphia|San Antonio|Memphis|Nashville|Austin|Charlotte|Washington|Las Vegas|Los Angeles|San Diego|Oklahoma City|Wichita|Hollywood|Brooklyn|Bronx|Queens|Manhattan|St\.? Louis|Minneapolis|Sacramento|Indianapolis|San Jose|Jacksonville|Baltimore|Fort Worth|El Paso|Milwaukee|Albuquerque|Tucson|Fresno|Sacramento|Mesa|Kansas City|Atlanta|Long Beach|Virginia Beach|Minneapolis|Colorado Springs|Tampa|Miami|Newark|St\.? Paul|Orlando|Cleveland|Cincinnati|Pittsburgh|Cincinnati|Greensboro|St\.? Petersburg)",
        r"\s+(LA|TX|CA|NY|FL|GA|IL|PA|OH|MI|NC|NJ|VA|WA|MA|MD|AZ|MN|TN|OR|OK|CT|IA|MS|AR|KS|UT|NV|SC|MO|KY|ID|NE|NM|AL|ME|HI|MT|DE|ND|SD|WY|WV|RI|NH|VT|AK|DE|ME)",
        r"\s+\d{5}",
    ]
    s = full
    for p in city_state_kw:
        s = re.sub(p, "", s, flags=re.I)
    s = s.strip().rstrip(",")
    return s


def _find_org_for_contractor(c: dict) -> dict:
    """Use Apollo organizations/search to find the company domain for this contractor."""
    full_name = c.get("name", "")
    metro = c.get("metro", "")
    if not full_name:
        return {"domain": "", "source": "no_name"}

    keywords = _extract_org_keywords(full_name)

    # Try a few search strategies
    candidates = []
    # 1. Stripped keywords (no city/state)
    if keywords and keywords != full_name:
        candidates.append(keywords)
    # 2. Full name
    candidates.append(full_name)
    # 3. Full name + metro (broad search)
    if metro:
        candidates.append(f"{full_name} {metro}")

    for kw in candidates:
        if not kw or len(kw) < 3:
            continue
        res = _apollo_post("/organizations/search", {
            "q_keywords": kw[:80],
            "page": 1,
            "per_page": 5,
        })
        if "organizations" in res and res["organizations"]:
            for org in res["organizations"]:
                domain = org.get("primary_domain") or ""
                # Skip Google's results (Apollo seems to always return Google first)
                if "google.com" in domain:
                    continue
                name = org.get("name", "")
                # Score: does the org name match the contractor name?
                biz_words = set(w.lower() for w in re.findall(r"[a-z]{3,}", keywords.lower()))
                org_words = set(w.lower() for w in re.findall(r"[a-z]{3,}", name.lower()))
                overlap = biz_words & org_words
                score = len(overlap) / max(len(biz_words), 1) if biz_words else 0
                if score >= 0.5:  # at least 50% word overlap
                    return {
                        "domain": domain,
                        "apollo_org_name": name,
                        "score": score,
                        "source": "apollo_org_search",
                    }
    return {"domain": "", "source": "no_org_match"}


def _try_email_patterns(domain: str) -> str:
    for pat in EMAIL_PATTERNS:
        cand = f"{pat}@{domain}"
        if _smtp_validate(cand):
            return cand
    return ""


def _is_valid_email(e: str) -> bool:
    if not e:
        return False
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", e):
        return False
    bad = ["@example.com", "@noreply", "@apollo", "@placeholder"]
    return not any(b in e.lower() for b in bad)


def run(limit: int = 100) -> dict:
    started = datetime.now(timezone.utc)
    api_key = os.environ.get("APOLLO_API_KEY")
    if not api_key:
        return {"status": "error", "error": "no APOLLO_API_KEY in env"}

    sb = _sb()
    r = sb.table("contractors").select("id,name,phone,metro,email").eq("active", True).is_("email", "null").limit(limit).execute()
    candidates = r.data or []
    log.info(f"apollo_skip_trace: {len(candidates)} contractors to enrich")

    found = 0
    skipped = 0
    errors = 0
    rate_limited = 0
    by_source = {"apollo_org_search": 0, "no_org_match": 0, "no_email_match": 0, "api_error": 0}

    for i, c in enumerate(candidates):
        try:
            org_res = _find_org_for_contractor(c)
            by_source[org_res["source"]] = by_source.get(org_res["source"], 0) + 1
            if org_res.get("error"):
                errors += 1
                if "rate" in org_res["error"].lower() or "429" in org_res["error"]:
                    rate_limited += 1
                    log.warning(f"  rate limit hit, pausing 60s")
                    time.sleep(60)
            domain = org_res.get("domain", "")
            if not domain:
                skipped += 1
                if i < 8:
                    log.info(f"  [{i+1}/{len(candidates)}] {c.get('name','?')[:40]:40}  no domain")
                continue

            # Domain found via Apollo - try email patterns
            email = _try_email_patterns(domain)
            if email and _is_valid_email(email):
                try:
                    sb.table("contractors").update({
                        "email": email,
                        "meta": {**(c.get("meta") or {}), "apollo_enriched_at": started.isoformat(), "apollo_domain": domain},
                    }).eq("id", c["id"]).execute()
                    found += 1
                    log.info(f"  [{i+1}/{len(candidates)}] {c.get('name','?')[:40]:40}  -> {email} (via {domain})")
                except Exception as e:
                    errors += 1
                    log.warning(f"  [{i+1}] db update failed: {e}")
            else:
                by_source["no_email_match"] += 1
                if i < 8:
                    log.info(f"  [{i+1}/{len(candidates)}] {c.get('name','?')[:40]:40}  domain={domain} but no email pattern matched")

        except Exception as e:
            errors += 1
            log.warning(f"  [{i+1}] ERR: {e}")

        # Be polite
        if i % 20 == 0 and i > 0:
            time.sleep(0.5)

    summary = f"apollo: found={found} skipped={skipped} errors={errors} by_source={by_source} of {len(candidates)}"
    log.info(summary)
    import uuid
    sb.table("agent_activity").insert({
        "agent_name": "apollo_skip_trace",
        "run_id": str(uuid.uuid4()),
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok" if errors == 0 else "ok",
        "rows_seen": len(candidates),
        "rows_processed": found,
        "summary": summary,
    }).execute()
    return {"status": "ok", "found": found, "skipped": skipped, "errors": errors, "rate_limited": rate_limited, "candidates": len(candidates), "by_source": by_source}


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    res = run(limit=limit)
    print(json.dumps(res, indent=2))
    sys.exit(0 if res["status"] == "ok" else 1)


if __name__ == "__main__":
    main()