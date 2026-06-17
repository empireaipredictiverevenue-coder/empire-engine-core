import os
import asyncio
import httpx
from supabase import create_client

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

# Look for any NEW reply from james after 2026-06-17 (when we sent our followup)
# Empty-body replies don't count; we want a real reply.
r = sb.table("inbox_messages").select("id,body,created_at").eq("from_address", "jstamatis@alt-pay.net").order("created_at", desc=True).execute()
real_replies = [x for x in (r.data or []) if (x.get("body") or "").strip()]
since_followup = [x for x in real_replies if x.get("created_at", "") > "2026-06-17T21:15:00Z"]

if since_followup:
    latest = since_followup[0]
    msg = (
        "James Stamatis (Alt-Pay) DID follow up. "
        "Latest reply at " + str(latest.get("created_at")) + ":\n\n"
        + (latest.get("body") or "")[:400]
    )
else:
    msg = (
        "James Stamatis (Alt-Pay) has NOT sent a follow-up "
        "since we delivered the sample-lead email on 2026-06-17. "
        "4 days silent. Decision point: send another nudge, "
        "mark dormant, or wait longer."
    )

tok = os.environ.get("TELEGRAM_BOT_TOKEN")
chat = os.environ.get("OPERATOR_TELEGRAM_CHAT_ID", "808657420")
if tok:
    asyncio.run(httpx.AsyncClient().post(
        "https://api.telegram.org/bot" + tok + "/sendMessage",
        json={"chat_id": chat, "text": msg}
    ))
    print("telegram sent: " + msg[:100])
else:
    print("TELEGRAM_BOT_TOKEN not set; would have sent: " + msg)
