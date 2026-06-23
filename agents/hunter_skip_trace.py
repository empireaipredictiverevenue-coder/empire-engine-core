"""Hunter.io skip-trace agent. Free tier: 25 searches/mo.

API: https://hunter.io/api-documentation/v2
- /v2/email-finder: name + domain -> email (1 credit)
- /v2/domain-search: domain -> all emails (50 credits)  - too expensive
- /v2/email-verifier: email -> valid? (1 credit per email verified, free tier has 100/mo)
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
EMAIL_PATTERNS = ["info", "contact", "office", "hello", "sales", "team"]


def _sb():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def _hunter_get(path: str, params: dict) -> dict:
    key = os.environ.get("HUNTER_API_KEY")
    if not key or "PLACEHOLDER" in key:
        return {"error": "no HUNTER_API_KEY in env (set it in /root/.env)"}
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


def _extract_company_keywords(full: str) -> str:
    """Strip city/state/category. 'Credit Repair New Orleans LA' -> 'Credit Repair'"""
    if not full:
        return ""
    s = re.sub(r"\s+(New Orleans|Atlanta|Dallas|Houston|Chicago|Miami|Phoenix|Denver|Seattle|Detroit|Boston|Philadelphia|San Antonio|Memphis|Nashville|Austin|Charlotte|Washington|Las Vegas|Los Angeles|San Diego|Oklahoma City|Wichita|Hollywood|Brooklyn|Bronx|Queens|Manhattan|St\.? Louis|Minneapolis|Sacramento|Indianapolis|San Jose|Jacksonville|Baltimore|Fort Worth|El Paso|Milwaukee|Albuquerque|Tucson|Fresno|Mesa|Kansas City|Long Beach|Virginia Beach|Colorado Springs|Tampa|Newark|St\.? Paul|Orlando|Cleveland|Cincinnati|Pittsburgh|Greensboro|St\.? Petersburg).*?(LA|TX|CA|NY|FL|GA|IL|PA|OH|MI|NC|NJ|VA|WA|MA|MD|AZ|MN|TN|OR|OK|CT|IA|MS|AR|KS|UT|NV|SC|MO|KY|ID|NE|NM|AL|ME|HI|MT|DE|ND|SD|WY|WV|RI|NH|VT|AK| \d{5}).*$", "", full, flags=re.I)
    s = s.strip().rstrip(",")
    return s


def _find_email_hunter(contractor: dict) -> dict:
    """Use Hunter email-finder: given first_name + last_name + domain, returns email."""
    full_name = contractor.get("name", "")
    if not full_name:
        return {"email": "", "source": "no_name"}
    # Get company keywords
    company_kw = _extract_company_keywords(full_name)
    if not company_kw or len(company_kw) < 3:
        return {"email": "", "source": "no_keywords"}

    # First try to find the domain via Hunter domain-search (50 credits - too expensive)
    # Instead, derive domain from keywords
    base = re.sub(r"[^a-z0-9]", "", company_kw.lower())[:25]
    domain = f"{base}.com" if base else ""
    if not domain or not _smtp_validate("info@" + domain):
        # Try other TLDs
        for tld in ["net", "org", "co", "io"]:
            test = f"{base}.{tld}" if base else ""
            if test and _smtp_validate("info@" + test):
                domain = test
                break

    if not domain:
        return {"email": "", "source": "no_domain"}

    # Try Hunter email-finder
    for pat in EMAIL_PATTERNS:
        # email-finder needs first/last name + domain. We don't have a real name,
        # but Hunter can sometimes infer.
        # We'll skip the people-finder since we don't have first/last name.
        # Instead, validate info@domain via Hunter's email-verifier
        candidate = f"{pat}@{domain}"
        res = _hunter_get("/email-verifier", {"email": candidate})
        if res.get("data", {}).get("status") == "valid":
            return {"email": candidate, "domain": domain, "source": "hunter_verified"}
    return {"email": "", "domain": domain, "source": "hunter_no_valid"}


def _is_valid_email(e):
    if not e:
        return False
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", e))


def run(limit: int = 25) -> dict:
    started = datetime.now(timezone.utc)
    sb = _sb()
    r = sb.table("contractors").select("id,name,phone,metro,email").eq("active", True).is_("email", "null").limit(limit).execute()
    candidates = r.data or []
    log.info(f"hunter_skip_trace: {len(candidates)} contractors to enrich")

    found = 0
    skipped = 0
    errors = 0
    for i, c in enumerate(candidates):
        try:
            res = _find_email_hunter(c)
            if res.get("email") and _is_valid_email(res["email"]):
                sb.table("contractors").update({
                    "email": res["email"],
                    "meta": {**(c.get("meta") or {}), "hunter_enriched_at": started.isoformat()},
                }).eq("id", c["id"]).execute()
                found += 1
                log.info(f"  [{i+1}/{len(candidates)}] {c.get('name','?')[:40]:40}  -> {res['email']}")
            else:
                skipped += 1
                if i < 8:
                    log.info(f"  [{i+1}/{len(candidates)}] {c.get('name','?')[:40]:40}  no match ({res.get('source')})")
        except Exception as e:
            errors += 1
            log.warning(f"  [{i+1}] ERR: {e}")

    import uuid
    summary = f"hunter: found={found} skipped={skipped} errors={errors} of {len(candidates)}"
    log.info(summary)
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
    return {"status": "ok", "found": found, "skipped": skipped, "errors": errors, "candidates": len(candidates)}


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    res = run(limit=limit)
    print(json.dumps(res, indent=2))
    sys.exit(0 if res["status"] == "ok" else 1)


if __name__ == "__main__":
    main()