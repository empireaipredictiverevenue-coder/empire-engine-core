"""
Billing Flow Integration Test
==============================
Traces: route_call -> call_completed -> _process_call_billing -> call_logs update

Usage: python3 test_billing_flow.py
"""
import os, sys, json, time, uuid
sys.path.insert(0, '/root/empire-v49')

from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
HUB_BASE = "http://localhost:8001"

if not SUPABASE_URL or not SUPABASE_KEY:
    print("FAIL: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_KEY)
test_tag = f"billing-test-{uuid.uuid4().hex[:8]}"
passed = 0
failed = 0

def check(label, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  PASS {label}")
        passed += 1
    else:
        print(f"  FAIL {label} -- {detail}")
        failed += 1

print("=" * 64)
print("BILLING FLOW VERIFICATION")
print("=" * 64)

# Step 0: Create a test buyer
print(f"\nStep 0: Create test buyer [{test_tag}]")
try:
    buyer_res = sb.table("buyers").insert({
        "buyer_name": f"Test Buyer {test_tag}",
        "niche": "roofing",
        "state_coverage": ["TX"],
        "timezone": "America/Chicago",
        "hours_open": 8,
        "hours_close": 22,
        "base_payout": 150.00,
        "fee_rate": 0.05,
        "destination_phone": "+12145551234",
        "daily_cap": 100,
        "is_active": True,
    }).execute()
    buyer = buyer_res.data[0]
    buyer_id = buyer["id"]
    check("Buyer created", buyer_id is not None, buyer_id)
    print(f"     Buyer ID: {buyer_id}")
    print(f"     Base payout: $150.00, Fee rate: 5%")
except Exception as e:
    check("Buyer created", False, str(e))
    sys.exit(1)

# Step 1: Route a call
print(f"\nStep 1: Route call via /api/switchboard/route")
test_call_id = f"test-call-{uuid.uuid4().hex[:12]}"
try:
    import httpx
    route_payload = {
        "niche": "roofing",
        "state": "TX",
        "caller_number": "+15125551234",
        "call_id": test_call_id,
        "source": "test_billing",
    }
    r = httpx.post(f"{HUB_BASE}/api/switchboard/route", json=route_payload, timeout=10)
    route_data = r.json()
    check("Route returned 200", r.status_code == 200, f"HTTP {r.status_code}")
    check("Route has payout_value", route_data.get("payout_value", 0) > 0, str(route_data))
    print(f"     Route response payout: ${route_data.get('payout_value')}")
except Exception as e:
    check("Route call", False, str(e))
    sb.table("buyers").delete().eq("id", buyer_id).execute()
    sys.exit(1)

# Step 2: Check call_logs was created with payout_value
print(f"\nStep 2: Verify call_logs record")
time.sleep(1)
try:
    cl_res = sb.table("call_logs").select("*").eq("vonage_call_id", test_call_id).execute()
    cl_data = cl_res.data
    check("call_logs record found", len(cl_data) == 1, f"found {len(cl_data)} records")
    if cl_data:
        cl = cl_data[0]
        check("buyer_id matches", cl.get("buyer_id") == buyer_id, f"{cl.get('buyer_id')} != {buyer_id}")
        check("payout_value = 150.0", float(cl.get("payout_value", 0)) == 150.0, f"got {cl.get('payout_value')}")
        check("is_billable is False initially", cl.get("is_billable") == False, f"got {cl.get('is_billable')}")
        print(f"     call_logs payout_value: ${cl.get('payout_value')}")
except Exception as e:
    check("call_logs lookup", False, str(e))
    sb.table("buyers").delete().eq("id", buyer_id).execute()
    sys.exit(1)

# Step 3: Post completed event (120s -- qualifies as billable)
print(f"\nStep 3: Post completed call event (duration=120s)")
try:
    event_payload = {
        "status": "completed",
        "uuid": test_call_id,
        "direction": "outbound",
        "duration": 120,
        "from": "+15125551234",
        "to": "+12145551234",
    }
    r = httpx.post(f"{HUB_BASE}/api/v1/voice/events", json=event_payload, timeout=10)
    check("Event returned 200", r.status_code == 200, f"HTTP {r.status_code}")
    print(f"     Event posted: completed, duration=120s")
except Exception as e:
    check("Post completed event", False, str(e))

# Step 4: Verify billing update
print(f"\nStep 4: Verify call_logs billing update (wait 2s)")
time.sleep(2)
try:
    cl_res = sb.table("call_logs").select("*").eq("vonage_call_id", test_call_id).execute()
    cl = cl_res.data[0]
    check("is_billable = True", cl.get("is_billable") == True, f"got {cl.get('is_billable')}")
    expected_fee = round(150.00 * 0.05, 2)
    actual_fee = float(cl.get("fee_earned", 0))
    check(f"fee_earned = ${expected_fee}", actual_fee == expected_fee, f"got ${actual_fee}")
    check("status = completed", cl.get("status") == "completed", f"got {cl.get('status')}")
    print(f"     is_billable: {cl.get('is_billable')}")
    print(f"     fee_earned: ${actual_fee}")
except Exception as e:
    check("Billing update", False, str(e))

# Step 5: Verify buyer calls_accepted incremented
print(f"\nStep 5: Verify buyer calls_accepted incremented")
try:
    buyer_check = sb.table("buyers").select("calls_accepted,calls_offered").eq("id", buyer_id).execute()
    if buyer_check.data:
        bc = buyer_check.data[0]
        check("calls_accepted >= 1", int(bc.get("calls_accepted", 0)) >= 1, f"got {bc.get('calls_accepted')}")
        check("calls_offered >= 1", int(bc.get("calls_offered", 0)) >= 1, f"got {bc.get('calls_offered')}")
        print(f"     calls_accepted: {bc.get('calls_accepted')}")
        print(f"     calls_offered: {bc.get('calls_offered')}")
except Exception as e:
    check("Buyer counter check", False, str(e))

# Step 6: Sub-90s call should NOT be billable
print(f"\nStep 6: Test sub-90s call (should NOT be billable)")
short_call_id = f"test-call-short-{uuid.uuid4().hex[:8]}"
try:
    route_payload["call_id"] = short_call_id
    httpx.post(f"{HUB_BASE}/api/switchboard/route", json=route_payload, timeout=10)
    short_event = {"status": "completed", "uuid": short_call_id, "direction": "outbound", "duration": 30, "from": "+15125551234", "to": "+12145551234"}
    httpx.post(f"{HUB_BASE}/api/v1/voice/events", json=short_event, timeout=10)
    time.sleep(2)
    short_cl = sb.table("call_logs").select("is_billable,fee_earned").eq("vonage_call_id", short_call_id).execute()
    if short_cl.data:
        sc = short_cl.data[0]
        check("Short call NOT billable", sc.get("is_billable") != True, f"is_billable={sc.get('is_billable')}")
        check("Short call fee = 0", float(sc.get("fee_earned", 0)) == 0.0, f"fee={sc.get('fee_earned')}")
        print(f"     is_billable: {sc.get('is_billable')}, fee_earned: {sc.get('fee_earned')}")
except Exception as e:
    check("Short call test", False, str(e))

# Cleanup: delete call_logs first (FK constraint), then buyer
print(f"\nCleanup: removing test data")
try:
    sb.table("call_logs").delete().eq("vonage_call_id", test_call_id).execute()
    sb.table("call_logs").delete().eq("vonage_call_id", short_call_id).execute()
    sb.table("buyers").delete().eq("id", buyer_id).execute()
    print("     Test data removed")
except Exception as e:
    print(f"     Cleanup: {e}")

print("\n" + "=" * 64)
print(f"RESULTS: {passed} passed, {failed} failed")
print("=" * 64)
if failed == 0:
    print("Billing flow verified end-to-end!")
else:
    print(f"{failed} checks failed")
sys.exit(0 if failed == 0 else 1)
