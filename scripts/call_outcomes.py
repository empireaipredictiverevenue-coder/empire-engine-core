"""
Empire AI · Fee Call Outcome Tracker
====================================

Reads call_events (logged by empire_voice.py /api/v1/voice/events) and
back-links each call to the matching fee_event via the vonage_uuid stored
in fee_events.meta.call_log.

Once linked, we know:
  - Was the call answered by a human, voicemail, or no-answer?
  - How long did the call last?
  - Should we retry tomorrow, or move on?

Outputs a human-readable report and writes per-fee stats into
fee_events.meta.call_outcomes so we can decide retries.
"""
import os
import sys
import json
import argparse
import logging
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone, timedelta

REPO = Path("/root/empire-v49")
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv("/root/.env")

from supabase import create_client

log = logging.getLogger("call_outcomes")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


def _classify(call_events: list) -> dict:
    """
    Given all events for a single call_uuid, return a summary:
      - human_answered: bool
      - voicemail: bool
      - completed: bool
      - duration_s: int (max reported)
      - amd_result: 'human' | 'machine' | 'unknown'
    """
    summary = {
        "human_answered": False,
        "voicemail": False,
        "completed": False,
        "duration_s": 0,
        "amd_result": "unknown",
        "events": [],
    }
    for e in call_events:
        s = e.get("status", "")
        summary["events"].append(s)
        if s == "human":
            summary["human_answered"] = True
            summary["amd_result"] = "human"
        elif s == "machine":
            summary["voicemail"] = True
            summary["amd_result"] = "machine"
        elif s == "answered":
            # AMD not yet classified but a human/reception picked up
            summary["human_answered"] = True
            if summary["amd_result"] == "unknown":
                summary["amd_result"] = "human"
        elif s == "completed":
            summary["completed"] = True
            d = int(e.get("duration") or 0)
            if d > summary["duration_s"]:
                summary["duration_s"] = d
            # If we never saw a human/machine/answered event but the call
            # ran for >5s, treat it as a real conversation (probably voicemail
            # if duration < 8s, human otherwise)
            if summary["amd_result"] == "unknown" and d > 0:
                if d < 8:
                    summary["voicemail"] = True
                    summary["amd_result"] = "machine"
                else:
                    summary["human_answered"] = True
                    summary["amd_result"] = "human"
        elif s in ("failed", "rejected", "busy", "timeout", "no_answer"):
            summary["amd_result"] = s
    # If human_answered but voicemail also true, prefer human
    if summary["human_answered"]:
        summary["voicemail"] = False
        summary["amd_result"] = "human"
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--since-hours", type=int, default=48, help="look back N hours")
    p.add_argument("--write", action="store_true", help="write outcomes back to fee_events.meta")
    p.add_argument("--report", action="store_true", help="print report (default if no --write)")
    args = p.parse_args()

    since = (datetime.now(timezone.utc) - timedelta(hours=args.since_hours)).isoformat()

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    # Pull all call_events since window
    r = sb.table("call_events").select("*").gte("created_at", since).order("created_at", desc=True).execute()
    by_uuid = {}
    for e in (r.data or []):
        cu = e.get("call_uuid") or ""
        by_uuid.setdefault(cu, []).append(e)
    log.info(f"call_events in window: {len(r.data)} across {len(by_uuid)} uuids")

    # Pull fee_events with call_log entries
    fees = sb.table("fee_events").select("id,claim_id,status,meta,contractor_id,fee_amount").execute().data
    pending_with_calls = []
    for f in fees:
        meta = f.get("meta") or {}
        if isinstance(meta, str):
            try: meta = json.loads(meta)
            except Exception: meta = {}
        cl = meta.get("call_log") or []
        if cl:
            pending_with_calls.append((f, meta, cl))
    log.info(f"fees with call_log: {len(pending_with_calls)}")

    # Match each call uuid to events
    bucket_by_outcome = Counter()
    matched = 0
    updates = []
    for fee, meta, cl in pending_with_calls:
        fee_uuid_to_outcome = {}
        for c in cl:
            uuid = c.get("vonage_uuid") or ""
            if not uuid:
                continue
            events = by_uuid.get(uuid, [])
            if not events:
                continue
            outcome = _classify(events)
            fee_uuid_to_outcome[uuid] = outcome
            bucket_by_outcome[outcome["amd_result"]] += 1
            matched += 1

        if args.write and fee_uuid_to_outcome:
            meta["call_outcomes"] = {
                uuid: {
                    "amd": o["amd_result"],
                    "completed": o["completed"],
                    "duration_s": o["duration_s"],
                    "human_answered": o["human_answered"],
                    "voicemail": o["voicemail"],
                    "last_event_at": max((e.get("created_at","") for e in by_uuid.get(uuid,[])), default=""),
                }
                for uuid, o in fee_uuid_to_outcome.items()
            }
            updates.append((fee["id"], meta))

    print("\n=== OUTCOME BREAKDOWN (last {}h) ===".format(args.since_hours))
    for k, v in bucket_by_outcome.most_common():
        print(f"  {k:20} {v}")
    print(f"\n  TOTAL matched calls: {matched}")

    if args.write and updates:
        for fid, m in updates:
            sb.table("fee_events").update({"meta": m}).eq("id", fid).execute()
        print(f"\n  wrote call_outcomes to {len(updates)} fee_events")
    elif not args.write:
        print("\n  (dry-run — pass --write to persist)")


if __name__ == "__main__":
    main()