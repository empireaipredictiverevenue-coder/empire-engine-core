from supabase import create_client
import os
from dotenv import load_dotenv
load_dotenv("/root/.env")
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

print("=== CURRENT STATE CHECK ===\n")

# 1. High-urgency leads
leads = sb.table("radar_targets").select("address,urgency_score,email,status,created_at").gte("urgency_score", 7).order("created_at", desc=True).limit(5).execute().data
print("Recent high-urgency leads (urgency >= 7):")
for l in leads:
    print("  " + l["address"] + " | urgency: " + str(l["urgency_score"]) + " | email: " + str(l["email"]) + " | status: " + l["status"])
print()

# 2. Active contractors
contractors = sb.table("contractors").select("name,email,active,trust_score,completed_jobs").eq("active", True).order("created_at", desc=True).limit(5).execute().data
print("Recent active contractors:")
for c in contractors:
    print("  " + c["name"] + " | email: " + c["email"] + " | trust: " + str(c["trust_score"]) + " | jobs: " + str(c["completed_jobs"]))
print()

# 3. Recent fee_events
fees = sb.table("fee_event").select("*").order("created_at", desc=True).limit(5).execute().data
print("Recent fee events:")
for f in fees:
    print("  amount: " + str(f.get("amount")) + " | claim: " + str(f.get("claim_amount")) + " | seed: " + str(f.get("seed_for_test")))
print()

print("=== CHECK COMPLETE ===")
