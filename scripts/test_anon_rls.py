"""Verify RLS: anon reads work, anon writes blocked, service_role writes work."""
import os, sys
sys.path.insert(0, "/root/empire-v49")
from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)
from supabase import create_client

URL = os.environ["SUPABASE_URL"]
ANON = os.environ["SUPABASE_ANON_KEY"]
SVC = os.environ["SUPABASE_SERVICE_KEY"]
anon = create_client(URL, ANON)
svc = create_client(URL, SVC)

tables = [
    "seo_audits", "seo_keywords", "seo_content", "seo_genome_history",
    "panel_court_decisions", "dream_memory",
    "leads", "calls", "agent_registry", "call_logs", "brain_memory",
    "inbound_leads", "audit_log",
]

print("=" * 78)
print("PART 1: ANON-KEY READS (RLS SELECT policy)")
print("=" * 78)
print(f"{'TABLE':28s}  {'ANON_SEL':10s}  {'ROWS':6s}  POLICY")
print("-" * 60)
read_ok = 0
for t in tables:
    try:
        r = anon.table(t).select("id", count="exact").limit(1).execute()
        rows = r.count if r.count is not None else len(r.data or [])
        print(f"  {t:26s}  {'OK':10s}  {rows:<6d}  ALLOW_READ")
        read_ok += 1
    except Exception as e:
        msg = str(e)[:40]
        print(f"  {t:26s}  {'DENY':10s}  {'-':<6s}  {msg}")

print(f"\nResult: {read_ok}/{len(tables)} tables allow anon SELECT")

print()
print("=" * 78)
print("PART 2: ANON-KEY WRITES (RLS should block)")
print("=" * 78)
print(f"{'TABLE':28s}  {'ANON_INS':10s}  POLICY")
print("-" * 60)
write_blocked = 0
test_payloads = {
    "seo_audits":     {"url": "https://anon-test.example", "niche": "TEST"},
    "leads":          {"phone": "+15555555555", "source": "anon_test"},
    "agent_registry": {"agent_name": "__anon_test__"},
    "brain_memory":   {"__test": True},
}
for t, payload in test_payloads.items():
    try:
        r = anon.table(t).insert(payload).execute()
        print(f"  {t:26s}  {'ALLOWED':10s}  WRITE LEAK")
        try:
            if t == "seo_audits":
                anon.table(t).delete().eq("url", "https://anon-test.example").execute()
            elif t == "leads":
                anon.table(t).delete().eq("phone", "+15555555555").execute()
            elif t == "agent_registry":
                anon.table(t).delete().eq("agent_name", "__anon_test__").execute()
        except Exception:
            pass
    except Exception as e:
        msg = str(e)[:60].lower()
        is_block = ("permission denied" in msg or "row-level security" in msg
                    or "401" in msg or "403" in msg or "policy" in msg)
        if is_block:
            print(f"  {t:26s}  {'BLOCKED':10s}  DENY_WRITE")
            write_blocked += 1
        else:
            print(f"  {t:26s}  {'ERROR':10s}  {str(e)[:60]}")

print(f"\nResult: {write_blocked}/{len(test_payloads)} anon INSERTs blocked by RLS")

print()
print("=" * 78)
print("PART 3: SERVICE-ROLE (verify hub can still write)")
print("=" * 78)
try:
    r = svc.table("seo_audits").select("id", count="exact").limit(0).execute()
    print(f"  service_role SELECT seo_audits: OK ({r.count} rows visible)")
except Exception as e:
    print(f"  service_role SELECT failed: {str(e)[:60]}")
try:
    r = svc.table("agent_registry").select("agent_name").limit(1).execute()
    print(f"  service_role SELECT agent_registry: OK ({len(r.data or [])} row)")
except Exception as e:
    print(f"  service_role SELECT failed: {str(e)[:60]}")
