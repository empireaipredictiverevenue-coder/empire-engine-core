"""
EMPIRE V49 · PEEK LEADS (REAL DATA)
=====================================
Shows the 5 most recent radar_targets from Supabase.
Real warehouses, real addresses, real phones.
"""
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

load_dotenv("/root/.env")
from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")


def peek_recent_leads():
    if not (SUPABASE_URL and SUPABASE_KEY):
        print("ERROR: SUPABASE_URL/SERVICE_KEY missing in /root/.env")
        return

    db = create_client(SUPABASE_URL, SUPABASE_KEY)
    r = (db.table("radar_targets")
         .select("address,phone,status,meta,created_at")
         .order("created_at", desc=True)
         .limit(5)
         .execute())
    rows = r.data or []

    print("--- LAST 5 REAL RADAR TARGETS ---")
    print(f"{'NAME':<35} | {'PHONE':<18} | {'STATUS':<10} | CREATED")
    print("-" * 95)

    for row in rows:
        meta = row.get("meta") or {}
        raw = meta.get("raw") or {}
        name = (meta.get("warehouse_name") or raw.get("name") or "Unknown")[:34]
        phone = row.get("phone") or raw.get("phone") or "(no phone)"
        status = row.get("status") or "?"
        created = row.get("created_at", "")[:19]
        print(f"{name:<35} | {phone:<18} | {status:<10} | {created}")

    if not rows:
        print("(no targets yet — storm trigger hasn't found any)")


if __name__ == "__main__":
    peek_recent_leads()
