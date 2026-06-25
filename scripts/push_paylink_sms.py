import os, asyncio, uuid, time, httpx
from pathlib import Path
from supabase import create_client
import jwt as pyjwt

VAULT = "egJ1t9NZkDs8FvMbfnQTqXzC4KNuhAc9XSfpG9y9AZM"
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def _resolve_settle(dispatch_id: str, token: str) -> str:
    if dispatch_id and token:
        return f"empire-ai.co.uk/settle/{dispatch_id}?t={token}"
    return ""


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

    # Bulk-resolve dispatch + token per claim_id (1 query per claim)
    import uuid as _uuid
    valid_claim_ids = [f["claim_id"] for f in fees if _uuid.UUID(str(f["claim_id"]), errors="ignore") is not None or True] if False else []
    # Keep only UUID-shaped claim_ids (the /settle page test injected "webhook-<uuid>" strings)
    valid_claim_ids = []
    for f in fees:
        try:
            _uuid.UUID(str(f["claim_id"]))
            valid_claim_ids.append(f["claim_id"])
        except Exception:
            pass
    cc_by_claim = {}
    if valid_claim_ids:
        cc_rows = sb.table("carrier_claims").select("id,dispatch_id").in_("id", valid_claim_ids).execute().data
        cc_by_claim = {r["id"]: r["dispatch_id"] for r in cc_rows}
    disp_by_id = {}
    if cc_by_claim:
        disp_rows = sb.table("dispatches").select("id,token").in_("id", list(set(cc_by_claim.values()))).execute().data
        disp_by_id = {r["id"]: r.get("token","") for r in disp_rows}

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
        dispatch_id = cc_by_claim.get(fee["claim_id"])
        token = disp_by_id.get(dispatch_id, "") if dispatch_id else ""
        settle_url = _resolve_settle(dispatch_id, token) if dispatch_id else ""
        dispatch_short = (dispatch_id or "")[:8]

        pay_url = f"empire-ai.co.uk/pay/{fee['claim_id']}"
        if settle_url:
            body = (
                f"Empire AI: ${fee_amt:,.0f} fee on ${claim_amt:,.0f} claim ({dispatch_short}...). "
                f"Settled yet? Confirm 60s: {settle_url} "
                f"Or pay now: {pay_url} STOP to opt out."
            )
        else:
            body = (
                f"Empire AI: Final notice \u2014 ${fee_amt:,.0f} fee on ${claim_amt:,.0f} claim "
                f"({dispatch_short}...). Tap to pay in 60s: {pay_url} "
                f"STOP to opt out."
            )

        print(f"  sending to {name} {phone} (${fee_amt:,.0f})")
        r = await send_vonage_sms(phone, body, vonage_number)
        print(f"    {r}")
        sb.table("sms_log").insert({
            "phone": phone, "direction":"outbound", "body": body,
            "step": 7, "delivered": r.get("ok", False),
            "sms_variant": "dual_link_pay_settle" if settle_url else "final_pay_link",
        }).execute()
        results.append({"contractor": name, "phone": phone, "ok": r.get("ok"), "fee": fee_amt, "settle_url": settle_url})
    print("\n=== SUMMARY ===")
    for x in results:
        print(f"  {x['contractor']:35} {x['phone']:18} ${x['fee']:>9,.0f}  settle={'Y' if x['settle_url'] else 'N'}  {'OK' if x['ok'] else 'FAIL'}")


asyncio.run(main())