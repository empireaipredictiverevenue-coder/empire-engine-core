import os, sys, asyncio, uuid, time, httpx
from pathlib import Path
from supabase import create_client
import jwt as pyjwt

VAULT = "egJ1t9NZkDs8FvMbfnQTqXzC4KNuhAc9XSfpG9y9AZM"
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

async def send_vonage_sms(to, body, vonage_number):
    app_id = os.environ["VONAGE_APPLICATION_ID"]
    key_path = os.environ.get("VONAGE_PRIVATE_KEY_PATH", "/root/vonage_private.key")
    with open(key_path) as f:
        private_key = f.read()
    now = int(time.time())
    payload = {
        "iat": now,
        "exp": now + 180,
        "jti": str(uuid.uuid4()),
        "application_id": app_id,
    }
    token = pyjwt.encode(payload, private_key, algorithm="RS256")
    msg = {
        "from": vonage_number.lstrip("+"),
        "to": to.lstrip("+"),
        "message_type": "text",
        "text": body[:1000],
        "channel": "sms",
    }
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            "https://api.nexmo.com/v1/messages",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=msg,
        )
    return {"ok": r.status_code < 400, "status": r.status_code, "body": r.text[:200]}

async def main():
    vonage_number = os.environ.get("VONAGE_NUMBER", "14155551234")
    fees = sb.table("fee_events").select("*").eq("status","pending").execute().data
    seen = {}
    for f in fees:
        cid = f.get("contractor_id")
        if cid in seen:
            if f["fee_amount"] > seen[cid]["fee_amount"]:
                seen[cid] = f
        else:
            seen[cid] = f
    print(f"unique contractors with pending fees: {len(seen)}")
    results = []
    for cid, fee in seen.items():
        c = sb.table("contractors").select("name,phone,email").eq("id", cid).limit(1).execute().data
        if not c or not c[0].get("phone"):
            print(f"  skip {cid[:8]} (no phone)")
            continue
        cont = c[0]
        name = cont["name"]
        phone = cont["phone"]
        fee_amt = float(fee["fee_amount"])
        claim_amt = float(fee["claim_amount"])
        dispatch_id = fee.get("meta", {}).get("dispatch_id", fee.get("claim_id",""))[:8]
        body = (
            f"Empire AI: Final notice \u2014 ${fee_amt:,.0f} fee on ${claim_amt:,.0f} claim "
            f"({dispatch_id}...). Tap to pay in 60s: empire-ai.co.uk/pay/{fee['claim_id']} "
            f"STOP to opt out."
        )
        print(f"  sending to {name} {phone} (${fee_amt:,.0f})")
        r = await send_vonage_sms(phone, body, vonage_number)
        print(f"    {r}")
        sb.table("sms_log").insert({
            "phone": phone, "direction":"outbound", "body": body,
            "step": 7, "delivered": r.get("ok", False),
            "sms_variant": "final_pay_link",
        }).execute()
        results.append({"contractor": name, "phone": phone, "ok": r.get("ok"), "fee": fee_amt})
    print("\n=== SUMMARY ===")
    for x in results:
        print(f"  {x['contractor']:35} {x['phone']:18} ${x['fee']:>9,.0f}  {'OK' if x['ok'] else 'FAIL'}")

asyncio.run(main())