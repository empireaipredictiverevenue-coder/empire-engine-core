"""
Empire AI · Inbound SMS Monitor
================================

Real-time inbound SMS router. When a homeowner replies (YES, NO, STOP,
or just a free-form message), the system needs to surface it to the
operator immediately. This endpoint exposes the latest inbound messages
plus a small SSE-friendly aggregator.

Endpoints:
  GET /api/v1/sms/inbound/recent?limit=20&minutes=60
      - List inbound SMS from sms_log, most recent first
      - Filtered to direction='inbound', within the last N minutes

The SPA's "Live Inbox" widget polls this every 5s and renders the
newest messages. Real-time SSE events come from the existing
broadcaster (type=sms_inbound), which is also fired on inbound.
"""
import os
from datetime import datetime, timezone, timedelta
from collections import Counter
from fastapi import Depends, HTTPException
from supabase import create_client


def register_inbound_monitor_routes(app, *, require_auth, get_db=None):
    def _db():
        if get_db is not None:
            return get_db()
        return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    @app.get("/api/v1/sms/inbound/recent")
    async def sms_inbound_recent(
        limit: int = 20,
        minutes: int = 1440,
        auth: bool = Depends(require_auth),
    ):
        try:
            db = _db()
            cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
            r = (db.table("sms_log")
                   .select("id, phone, body, step, created_at")
                   .eq("direction", "inbound")
                   .gte("created_at", cutoff)
                   .order("created_at", desc=True)
                   .limit(max(1, min(limit, 200)))
                   .execute())
            rows = r.data or []
            # classify each message
            for r in rows:
                body = (r.get("body") or "").strip().upper()
                if body in ("STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"):
                    r["intent"] = "stop"
                elif body in ("YES", "Y", "YEAH", "YEP", "OK", "OKAY", "SURE", "YEA", "Y"):
                    r["intent"] = "yes"
                elif body in ("NO", "N", "NOPE", "NAH"):
                    r["intent"] = "no"
                elif body.startswith("NOTNOW") or body.startswith("NOT NOW") or body.startswith("LATER"):
                    r["intent"] = "notnow"
                else:
                    r["intent"] = "freeform"
            # rollup
            intent_counts = Counter(r.get("intent") for r in rows)
            return {
                "messages": rows,
                "count": len(rows),
                "window_minutes": minutes,
                "by_intent": dict(intent_counts),
            }
        except Exception as e:
            raise HTTPException(500, str(e))
