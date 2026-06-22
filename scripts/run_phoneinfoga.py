"""
EMPIRE V49 · PHONEINFOGA RUNNER
================================
Daily cycle: pull contractors without phone numbers, scan them with
PhoneInfoga, write the results back to the contractors table.

PhoneInfoga is a Go CLI for OSINT phone number scanning. We invoke it
as a subprocess for each phone number, parse the JSON output, and
update the contractor record with provider/location signals.

VERIFIED:
  phoneinfoga binary at /usr/local/bin/phoneinfoga (working)
  No API keys required for basic scan (uses free OSINT sources)
"""
import os
import sys
import json
import subprocess
import logging
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, List

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env")
except ImportError:
    pass

try:
    from supabase import create_client
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
except Exception as e:
    sb = None
    print(f"[phoneinfoga] Supabase init failed: {e}")

log = logging.getLogger("empire.phoneinfoga")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [phoneinfoga] %(levelname)s %(message)s")

PHONEINFOGA_BIN = "/usr/local/bin/phoneinfoga"


def _scan_one(number: str) -> Dict:
    """Run phoneinfoga scan on a single number. Returns parsed JSON or {}."""
    try:
        # phoneinfoga scan -n <number> --json
        result = subprocess.run(
            [PHONEINFOGA_BIN, "scan", "-n", number, "--json"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                # non-json output, treat as text
                return {"raw": result.stdout.strip()[:500], "valid": "true" in result.stdout.lower()}
        return {"error": result.stderr.strip()[:200] or "no output", "returncode": result.returncode}
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except Exception as e:
        return {"error": str(e)[:200]}


def _fetch_contractors_without_phone_validation(limit: int = 50) -> List[Dict]:
    """Get contractors that have a phone but no phone_validation_json yet."""
    if not sb:
        return []
    try:
        r = sb.table("contractors").select("id,name,phone").not_.is_("phone", "null").is_("phone_validation_json", "null").limit(limit).execute()
        return r.data or []
    except Exception as e:
        log.warning(f"fetch contractors failed: {e}")
        # try alternate: just any contractor with a phone
        try:
            r = sb.table("contractors").select("id,name,phone").not_.is_("phone", "null").limit(limit).execute()
            return r.data or []
        except Exception:
            return []


def _record_agent_activity(agent_name: str, status: str, rows: int, summary: str):
    if not sb:
        return
    try:
        sb.table("agent_activity").insert({
            "agent_name": agent_name,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "rows_processed": rows,
            "summary": summary[:500],
        }).execute()
    except Exception as e:
        log.warning(f"agent_activity insert failed: {e}")


def run_once() -> Dict:
    """Single validation cycle: scan up to 50 contractor phones."""
    log.info("[phoneinfoga] starting daily phone validation cycle")
    started = datetime.now(timezone.utc)

    contractors = _fetch_contractors_without_phone_validation(limit=50)
    log.info(f"[phoneinfoga] scanning {len(contractors)} contractor phones")

    if not contractors:
        log.info("[phoneinfoga] no contractors to scan (all have validation or no phones)")
        return {"scanned": 0, "valid": 0, "invalid": 0, "errors": 0}

    valid = 0
    invalid = 0
    errors = 0
    rows = []

    for c in contractors:
        phone = c.get("phone")
        if not phone:
            continue
        # normalize: strip non-digits
        digits = "".join(ch for ch in str(phone) if ch.isdigit() or ch == "+")
        if len(digits) < 7:
            errors += 1
            continue

        result = _scan_one(digits)
        is_valid = "error" not in result
        if is_valid:
            valid += 1
        else:
            invalid += 1
            errors += 1

        # write back
        if sb:
            try:
                sb.table("contractors").update({
                    "phone_validation_json": result,
                    "phone_validated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", c["id"]).execute()
            except Exception as e:
                log.warning(f"update contractor {c.get('id')} failed: {e}")

        rows.append({"contractor": c.get("business_name", "?"), "phone": digits, "valid": is_valid})

        # be polite to OSINT sources
        time.sleep(0.5)

    duration = (datetime.now(timezone.utc) - started).total_seconds()
    summary = json.dumps({
        "scanned": len(rows),
        "valid": valid,
        "invalid": invalid,
        "errors": errors,
        "duration_s": round(duration, 1),
    })

    status = "ok" if errors == 0 else "error"
    _record_agent_activity("phoneinfoga", status, len(rows), summary)
    log.info(f"[phoneinfoga] cycle complete: {summary}")
    return {"scanned": len(rows), "valid": valid, "invalid": invalid, "errors": errors}


def run_loop(interval_seconds: int = 86400):
    """Loop wrapper for agent_runner."""
    import asyncio
    async def _run():
        while True:
            try:
                run_once()
            except Exception as e:
                log.error(f"phoneinfoga cycle error: {e}")
            await asyncio.sleep(max(60, interval_seconds))
    asyncio.run(_run())


if __name__ == "__main__":
    run_once()