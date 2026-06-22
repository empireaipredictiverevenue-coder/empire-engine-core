"""
Empire AI · Fee Expired Handler
================================

When a discount expires and the fee is still unpaid:
1. Mark meta.discount_expired_at = now
2. Log a "high_touch" event for the operator
3. Increment a "push_count" — if < 3, queue one more follow-up

Cron (hourly):
  0 * * * * /usr/bin/python3 /root/empire-v49/scripts/fee_expired_handler.py >> /root/empire-v49/logs/fee_expired_handler.log 2>&1
"""
import os, sys, json, logging, time, uuid
from datetime import datetime, timezone
from pathlib import Path

REPO = Path("/root/empire-v49")
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)

import httpx, jwt as pyjwt
from supabase import create_client

log = logging.getLogger("fee_expired_handler")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

MARKER_KEY = "discount_expired_at"
MAX_HIGH_TOUCH_PUSHES = 3  # after this many pushes, stop auto-nudging


def _send_vonage_sms(to: str, body: str) -> dict:
    app_id = os.environ.get("VONAGE_APPLICATION_ID", "")
    key_path = os.environ.get("VONAGE_PRIVATE_KEY_PATH", "/root/vonage_private.key")
    from_number = os.environ.get("VONAGE_NUMBER", "12142277528").lstrip("+")
    if not (app_id and os.path.exists(key_path)):
        return {"ok": False, "error": "vonage creds missing"}
    with open(key_path) as f:
        private_key = f.read()
    now = int(time.time())
    token = pyjwt.encode(
        {"iat": now, "exp": now + 180, "jti": str(uuid.uuid4()), "application_id": app_id},
        private_key, algorithm="RS256",
    )
    msg = {"from": from_number, "to": to.lstrip("+"),
           "message_type": "text", "text": body[:1000], "channel": "sms"}
    try:
        with httpx.Client(timeout=15) as c:
            r = c.post("https://api.nexmo.com/v1/messages",
                json=msg,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        return {"ok": r.status_code < 400, "status": r.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def _send_telegram(text: str) -> bool:
    bot = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not (bot and chat):
        return False
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{bot}/sendMessage",
            json={"chat_id": chat, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        return r.status_code == 200
    except Exception:
        return False


def _is_expired_now(fee: dict) -> bool:
    exp = fee.get("discount_expires_at")
    if not exp:
        return False
    try:
        dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
        return dt <= datetime.now(timezone.utc)
    except Exception:
        return False


def _high_touch_message(name: str, fee_amt: float, claim_id: str) -> str:
    """Tone: direct, no AI-polish, slightly more urgent now that the discount is gone."""
    return (
        f"Empire AI: {name}, your discount has expired and the {fee_amt:,.0f} fee is now due in full. "
        f"Tap to settle: empire-ai.co.uk/pay/{claim_id} STOP to opt out."
    )


def main():
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    now = datetime.now(timezone.utc)

    # Pending fees with discount already expired (or no discount at all that's recent)
    fees = sb.table("fee_events").select(
        "id,claim_id,contractor_id,fee_amount,discount_amount,status,discount_expires_at,meta"
    ).eq("status", "pending").execute().data or []

    newly_expired = []
    already_handled = []
    for f in fees:
        meta = f.get("meta") or {}
        if isinstance(meta, str):
            try: meta = json.loads(meta)
            except Exception: meta = {}
        if _is_expired_now(f) and not meta.get(MARKER_KEY):
            f["_meta"] = meta
            newly_expired.append(f)
        elif _is_expired_now(f) and meta.get(MARKER_KEY):
            already_handled.append(f)

    log.info(f"newly expired: {len(newly_expired)}, already handled: {len(already_handled)}")

    handled = 0
    pushed = 0
    for f in newly_expired:
        cid = f.get("contractor_id")
        c = sb.table("contractors").select("name,phone,email").eq("id", cid).limit(1).execute().data
        if not c:
            continue
        cont = c[0]
        name = cont["name"]
        first = name.split()[0]
        fee_amt = float(f["fee_amount"])
        claim_id = f.get("claim_id", "")

        new_meta = dict(f["_meta"])
        new_meta[MARKER_KEY] = now.isoformat()
        new_meta["discount_expired_high_touch_count"] = 0
        sb.table("fee_events").update({"meta": new_meta}).eq("id", f["id"]).execute()
        handled += 1
        log.info(f"  marked expired: {name} ${fee_amt:,.0f} claim {claim_id[:13]}")

    # For fees already marked expired but not yet at MAX_HIGH_TOUCH_PUSHES,
    # send one more follow-up.
    for f in already_handled:
        cid = f.get("contractor_id")
        c = sb.table("contractors").select("name,phone").eq("id", cid).limit(1).execute().data
        if not c or not c[0].get("phone"):
            continue
        meta = f.get("meta") or {}
        if isinstance(meta, str):
            try: meta = json.loads(meta)
            except: meta = {}
        count = meta.get("discount_expired_high_touch_count", 0)
        if count >= MAX_HIGH_TOUCH_PUSHES:
            continue

        body = _high_touch_message(c[0]["name"].split()[0], f["fee_amount"], f.get("claim_id", ""))
        r = _send_vonage_sms(c[0]["phone"], body)
        if r.get("ok"):
            meta["discount_expired_high_touch_count"] = count + 1
            meta.setdefault("discount_expired_high_touch_log", []).append({
                "ts": now.isoformat(), "ok": True, "count_after": count + 1,
            })
            sb.table("fee_events").update({"meta": meta}).eq("id", f["id"]).execute()
            pushed += 1
            log.info(f"  high-touch push #{count+1}: {c[0]['name']} ${f['fee_amount']:,.0f}")
        else:
            log.warning(f"  high-touch push failed: {r}")

    if handled or pushed:
        _send_telegram(
            f"⏰ <b>Fee expired handler</b>\n"
            f"newly marked expired: {handled}\n"
            f"high-touch pushes sent: {pushed}\n"
            f"max-pushed (manual review needed): "
            f"{sum(1 for f in already_handled if (f.get('meta') or {}).get('discount_expired_high_touch_count', 0) >= MAX_HIGH_TOUCH_PUSHES)}"
        )

    print(json.dumps({"newly_expired_marked": handled,
                      "high_touch_pushes_sent": pushed,
                      "max_pushed_pending_review": sum(1 for f in already_handled
                          if (f.get("meta") or {}).get("discount_expired_high_touch_count", 0) >= MAX_HIGH_TOUCH_PUSHES)}))


if __name__ == "__main__":
    main()