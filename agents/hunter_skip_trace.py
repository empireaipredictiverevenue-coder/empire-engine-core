"""Empire AI · Hunter.io skip-trace agent.

Hunter.io free tier gives ~50 domain-searches/mo and 25 email-finders/mo.
Strategy:
  - Use domain-search?company=<name> to find the company's domain + emails
  - Prefer generic emails (info@, office@, contact@) over personal
  - Falls back to pattern-guess on the found domain
"""
import os
import sys
import re
import json
import time
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

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

log = logging.getLogger("empire.hunter_skip_trace")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

HUNTER_BASE = "https://api.hunter.io/v2"

GENERIC_PATTERNS = ["info", "contact", "office", "hello", "sales", "team", "admin"]


def _sb():
    return create_client(os.environ["SUPABASE_URL"], os.getenv("SUPABASE_SERVICE_KEY"))


def _hunter_get(path: str, params: dict) -> dict:
    """Hunter uses ?api_key=KEY URL param (NOT Bearer header)."""
    key = os.getenv("HUNTER_API_KEY")
    if not key or "PLACEHOLDER" in key:
        return {"error": "no HUNTER_API_KEY"}
    qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items() if v is not None)
    url = f"{HUNTER_BASE}{path}?{qs}&api_key={key}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return {"error": f"HTTP {e.code}: {e.read()[:300].decode('utf-8', errors='replace')}"}
        except Exception:
            return {"error": f"HTTP {e.code}"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def _clean_company(name: str) -> str:
    """Strip city/state/numeric suffix from descriptive names.
    'Credit Repair New Orleans LA' -> 'Credit Repair'
    'The Carry Auto Insurance Memphis TN' -> 'Carry Insurance'
    'Holly Ryherd - Souders & Associates Insurance' -> 'Souders & Associates Insurance'
    """
    if not name:
        return ""
    # Remove trailing city/state/category
    s = re.sub(r"\s+(New Orleans|Atlanta|Dallas|Houston|Chicago|Miami|Phoenix|Denver|Seattle|Detroit|Boston|Philadelphia|San Antonio|Memphis|Nashville|Austin|Charlotte|Washington|Las Vegas|Los Angeles|San Diego|Oklahoma City|Wichita|Hollywood|Brooklyn|Bronx|Queens|Manhattan|St\.? Louis|Minneapolis|Sacramento|Indianapolis|San Jose|Jacksonville|Baltimore|Fort Worth|El Paso|Milwaukee|Albuquerque|Tucson|Fresno|Mesa|Kansas City|Long Beach|Virginia Beach|Colorado Springs|Tampa|Newark|St\.? Paul|Orlando|Cleveland|Cincinnati|Pittsburgh|Greensboro|St\.? Petersburg).*?(LA|TX|CA|NY|FL|GA|IL|PA|OH|MI|NC|NJ|VA|WA|MA|MD|AZ|MN|TN|OR|OK|CT|IA|MS|AR|KS|UT|NV|SC|MO|KY|ID|NE|NM|AL|ME|HI|MT|DE|ND|SD|WY|WV|RI|NH|VT|AK| \d{5}).*$", "", name, flags=re.I)
    # Remove leading "FirstName LastName - " prefix to get the actual company
    if " - " in s:
        s = s.split(" - ", 1)[1]
    s = s.strip().rstrip(",")
    # If too short, return as-is
    return s if len(s) >= 3 else name


def _hunter_lookup(contractor: dict) -> dict:
    """For a contractor, try Hunter domain-search by company name.
    Returns {email, domain, source, candidates: [...]}.
    """
    full_name = contractor.get("name", "")
    if not full_name:
        return {"email": "", "source": "no_name"}

    company = _clean_company(full_name)
    if not company:
        return {"email": "", "source": "no_company"}

    res = _hunter_get("/domain-search", {
        "company": company,
        "limit": 3,
    })
    if "error" in res:
        return {"email": "", "source": "api_error", "detail": res["error"][:200]}
    data = res.get("data") or {}
    domain = data.get("domain", "")
    emails = data.get("emails", [])
    if not domain or not emails:
        return {"email": "", "source": "no_match", "company_searched": company}

    # Prefer generic emails (info@, office@, contact@)
    candidates = sorted(emails, key=lambda e: (
        0 if e.get("type") == "generic" else
        1 if e.get("type") == "role" else
        2
    ))
    best = candidates[0]
    email = best.get("value", "")

    return {
        "email": email,
        "domain": domain,
        "type": best.get("type"),
        "company_searched": company,
        "candidates": [{"email": c.get("value"), "type": c.get("type")} for c in candidates[:3]],
        "source": "hunter_company_search",
    }


def _is_valid_email(e):
    if not e:
        return False
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", e))


def run(limit: int = 50) -> dict:
    started = datetime.now(timezone.utc)
    sb = _sb()
    r = sb.table("contractors").select("id,name,phone,metro,email").eq("active", True).is_("email", "null").limit(limit).execute()
    candidates = r.data or []
    log.info(f"hunter_skip_trace: {len(candidates)} contractors to enrich")

    found = 0
    skipped = 0
    errors = 0
    by_source = {}

    for i, c in enumerate(candidates):
        try:
            res = _hunter_lookup(c)
            by_source[res["source"]] = by_source.get(res["source"], 0) + 1
            if res.get("email") and _is_valid_email(res["email"]):
                sb.table("contractors").update({
                    "email": res["email"],
                    "meta": {**(c.get("meta") or {}),
                             "hunter_enriched_at": started.isoformat(),
                             "hunter_domain": res.get("domain", "")},
                }).eq("id", c["id"]).execute()
                found += 1
                log.info(f"  [{i+1}/{len(candidates)}] {c.get('name','?')[:35]:35}  -> {res['email']} (via {res.get('domain')})")
            else:
                skipped += 1
                if i < 8:
                    log.info(f"  [{i+1}/{len(candidates)}] {c.get('name','?')[:35]:35}  {res.get('source')}: {res.get('detail', res.get('company_searched', ''))[:60]}")
        except Exception as e:
            errors += 1
            log.warning(f"  [{i+1}] ERR: {e}")
        if i % 20 == 0 and i > 0:
            time.sleep(0.5)

    summary = f"hunter: found={found} skipped={skipped} errors={errors} by_source={by_source} of {len(candidates)}"
    log.info(summary)
    import uuid
    sb.table("agent_activity").insert({
        "agent_name": "hunter_skip_trace",
        "run_id": str(uuid.uuid4()),
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
        "rows_seen": len(candidates),
        "rows_processed": found,
        "summary": summary,
    }).execute()
    return {"status": "ok", "found": found, "skipped": skipped, "errors": errors, "candidates": len(candidates), "by_source": by_source}


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    res = run(limit=limit)
    print(json.dumps(res, indent=2))
    sys.exit(0 if res["status"] == "ok" else 1)


if __name__ == "__main__":
    main()