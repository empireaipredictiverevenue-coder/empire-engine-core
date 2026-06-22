"""
Push fresh SMS with discount lead to the 4 ghosting contractors.
Uses the new fee_collection_call.py NCCO + push_paylink_sms.py pattern.
"""
import os, sys, asyncio, uuid, time
from pathlib import Path
from datetime import datetime, timezone
import httpx, jwt as pyjwt
from supabase import create_client

VAULT = "egJ1t9NZkDs8FvMbfnQTqXzC4KNuhAc9XSfpG9y9AZM"
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

async def send(to, body, vonage_number):
    app_id = os.environ["VONAGE_APPLICATION_ID"]
    key_path = os.environ.get("VONAGE_PRIVATE_KEY_PATH", "/root/vonage_private.key")
    with open(key_path) as f:
        private_key = f.read()
    now = int(time.time())
    token = pyjwt.encode({"iat":now,"exp":now+180,"jti":str(uuid.uuid4()),"application_id":app_id}, private_key, algorithm="RS256")
    msg = {"from": vonage_number.lstrip("+"), "to": to.lstrip("+"),
           "message_type": "text", "text": body[:1000], "channel": "sms"}
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post("https://api.nexmo.com/v1/messages",
            json=msg,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return {"ok": r.status_code < 400, "status": r.status_code, "body": r.text[:200]}

async def main():
    vonage_number = os.environ.get("VONAGE_NUMBER", "12142277528").lstrip("+")
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
        c = sb.table("contractors").select("name,phone").eq("id", cid).limit(1).execute().data
        if not c or not c[0].get("phone"):
            continue
        name = c[0]["name"]
        phone = c[0]["phone"]
        fee_amt = float(fee["fee_amount"])
        disc_amt = float(fee.get("discount_amount") or 0)
        claim_amt = float(fee["claim_amount"])
        disc_exp = fee.get("discount_expires_at", "")
        new_total = max(0.0, fee_amt - disc_amt)

        # Try to format date naturally
        try:
            from datetime import datetime as _dt
            exp_dt = _dt.fromisoformat(disc_exp.replace("Z","+00:00"))
            day_label = exp_dt.strftime("%b %-d")
        except Exception:
            day_label = "Jun 29"

        # Discount-led body, human-tone, 1 SMS segment
        body = (
            f"Empire AI: {name.split()[0]}, 20% off your ${fee_amt:,.0f} fee \u2014 "
            f"pay ${new_total:,.0f} by {day_label}, save ${disc_amt:,.0f}. "
            f"Tap: empire-ai.co.uk/pay/{fee['claim_id']} STOP to opt out."
        )
        print(f"  -> {name} {phone}")
        r = await send(phone, body, vonage_number)
        print(f"     {r}")
        sb.table("sms_log").insert({
            "phone": phone, "direction":"outbound", "body": body,
            "step": 8, "delivered": r.get("ok", False),
            "sms_variant": "discount_offer",
        }).execute()
        results.append({"contractor": name, "ok": r.get("ok"), "fee": fee_amt, "new_total": new_total})

    print("\n=== SUMMARY ===")
    for x in results:
        print(f"  {x['contractor']:35} ${x['fee']:>9,.0f} -> ${x['new_total']:>9,.0f}  {'OK' if x['ok'] else 'FAIL'}")

asyncio.run(main())