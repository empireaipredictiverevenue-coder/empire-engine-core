"""
EMPIRE V49 · SEED EMAIL DRAFTS
===============================
One-shot: for every radar_target that has an email but no draft yet,
generate a draft for the most recent storm strike.
"""
import os
import sys
import asyncio
from pathlib import Path

ROOT = Path("/root/empire-v49")
sys.path.insert(0, str(ROOT))

from supabase import create_client
from empire_ai_router import AIRouter
from empire_email_drafter import EmailDrafter

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
if not (SUPABASE_URL and SUPABASE_KEY):
    print("ERROR: SUPABASE_URL/SERVICE_KEY missing")
    sys.exit(1)

_db = create_client(SUPABASE_URL, SUPABASE_KEY)
def get_db():
    return _db


async def main():
    router = AIRouter(get_db=get_db)
    drafter = EmailDrafter(router=router, get_db=get_db)

    targets = (_db.table("radar_targets")
               .select("id,address,phone,meta")
               .order("created_at", desc=True)
               .limit(100)
               .execute()).data or []
    print(f"Loaded {len(targets)} recent targets")

    existing = (_db.table("email_drafts").select("target_id").execute()).data or []
    drafted = {d["target_id"] for d in existing if d.get("target_id")}
    print(f"Already drafted: {len(drafted)}")

    candidates = []
    for t in targets:
        if t["id"] in drafted:
            continue
        meta = t.get("meta") or {}
        raw = meta.get("raw") or {}
        # Synthesize a target dict like the orchestrator would pass
        target = {
            "warehouse_name": meta.get("warehouse_name") or raw.get("name") or "Facility",
            "address": t.get("address"),
            "phone": t.get("phone"),
            "email": raw.get("email"),
            "website": raw.get("website"),
        }
        if not target["email"]:
            continue
        candidates.append((t["id"], target))

    print(f"Candidates with email: {len(candidates)}")

    # Mock alert + brain decision (fresh drafts use today's date)
    alert_summary = {
        "event": "Severe Thunderstorm Warning",
        "severity": "Severe",
        "urgency": "Immediate",
        "area": "Dallas-Fort Worth metro",
    }
    brain_decision = {"decision": "GO", "confidence": 0.85,
                      "reasoning": "commercial target in active storm zone"}

    created = 0
    for target_id, target in candidates[:30]:  # cap at 30 for the seed run
        draft = await drafter.draft_for_target(
            target=target,
            alert_summary=alert_summary,
            brain_decision=brain_decision,
            target_id=target_id,
        )
        if draft:
            created += 1
            print(f"  ✓ {target['warehouse_name']} -> {target['email']}")
    print(f"\nSeeded {created} drafts.")


if __name__ == "__main__":
    asyncio.run(main())
