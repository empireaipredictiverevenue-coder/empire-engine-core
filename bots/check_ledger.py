import os
from supabase import create_client

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_KEY")
sb = create_client(url, key)

try:
    # Changed descending=True to desc=True to match the library requirements
    res = sb.table("call_logs").select("*").order("created_at", desc=True).limit(1).execute()
    if res.data:
        log = res.data[0]
        print("[SUCCESS] Live Scoreboard Record Confirmed!")
        print(f"NICHE: {log.get('niche')} | STATE: {log.get('caller_state')} | STATUS: {log.get('status')} | SOURCE: {log.get('source')}")
    else:
        print("[LEDGER STATUS] Table is empty.")
except Exception as e:
    print(f"[ERROR] Could not read ledger: {e}")
