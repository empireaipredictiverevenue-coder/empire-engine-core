"""Run skip-trace in batches of 100 with parallel MX lookups."""
import os
import sys
import json
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
load_dotenv(Path("/root/.env"))

sys.path.insert(0, "/root/empire-v49")
from supabase import create_client
from empire_vonage_email import _skip_trace_email

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

# Get all contractors without email (limit 6000)
r = sb.table("contractors").select("id,name,metro,email").eq("active", True).is_("email", "null").limit(6000).execute()
all_rows = r.data or []
print(f"total without email: {len(all_rows)}", flush=True)

# Process in parallel
def process(c):
    res = _skip_trace_email(c.get("name", ""), c.get("metro", ""), "")
    return c, res

found = 0
scanned = 0
t0 = time.time()
batch_size = 100
with ThreadPoolExecutor(max_workers=10) as ex:
    for i in range(0, len(all_rows), batch_size):
        chunk = all_rows[i:i+batch_size]
        results = list(ex.map(process, chunk))
        for c, res in results:
            scanned += 1
            if res["email"]:
                try:
                    sb.table("contractors").update({"email": res["email"]}).eq("id", c["id"]).execute()
                    found += 1
                except Exception:
                    pass
        elapsed = time.time() - t0
        rate = scanned / elapsed if elapsed > 0 else 0
        print(f"  scanned {scanned}/{len(all_rows)}  found {found}  ({rate:.1f}/sec, {elapsed:.0f}s)", flush=True)

print(f"\nDONE: scanned={scanned}, found={found}, in {time.time()-t0:.0f}s")