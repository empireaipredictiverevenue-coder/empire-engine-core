"""
A/B reply-rate measurement.
Compares storm_strike (new shorter copy) vs storm_strike_v2 (longer scarcity).
Reply-rate = replied / (replied + completed + active_aging_7d).
"""
import sys, os
sys.path.insert(0, "/root/empire-v49")
from supabase import create_client
from datetime import datetime, timezone, timedelta

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
now = datetime.now(timezone.utc)
old_cutoff = (now - timedelta(days=7)).isoformat()

for seq in ["storm_strike", "storm_strike_v2"]:
    r = sb.table("sms_sequences").select("status,created_at").eq("sequence_type", seq).execute()
    rows = r.data or []
    if not rows:
        print(f"{seq}: 0 sequences (skipping)")
        continue
    replied = sum(1 for r in rows if r.get("status") == "replied")
    completed = sum(1 for r in rows if r.get("status") == "completed")
    active = sum(1 for r in rows if r.get("status") == "active")
    opted_out = sum(1 for r in rows if r.get("status") == "opted_out")
    failed = sum(1 for r in rows if r.get("status") == "failed")
    total_terminal = replied + completed + opted_out + failed
    recent = sum(1 for r in rows if r.get("created_at", "") >= old_cutoff)
    rate = (replied / total_terminal * 100) if total_terminal > 0 else 0
    print(f"{seq}:")
    print(f"  total: {len(rows)}  recent_7d: {recent}")
    print(f"  replied: {replied}  completed: {completed}  active: {active}  opted_out: {opted_out}  failed: {failed}")
    print(f"  reply_rate: {rate:.2f}% ({replied}/{total_terminal} terminal)")
    print()
