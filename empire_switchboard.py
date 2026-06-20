import os, logging, time as _time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from supabase import create_client

from empire_utils import tz_for_areacode
from conversion_funnel import COMMISSION_RATE

log = logging.getLogger("empire.switchboard")
_sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

WHALE_FALLBACK = os.getenv("WHALE_FALLBACK_NUMBER", "+18005550199")

# ── BUYERS CACHE (60s TTL) ────────────────────────────────────────────
_BUYERS_CACHE_TTL = 60.0          # seconds before cache is considered stale
_buyers_cache: list = []           # list of buyer dicts, mirroring Supabase rows
_buyers_cache_ts: float = 0.0     # epoch timestamp of last cache fill

# Minimum number of offered calls before the acceptance-rate heuristic kicks
# in. Below this threshold the buyer gets a free pass (rate=1.0) so new
# buyers don't get penalized while they're warming up. Tweakable at runtime
# by the SI Adaptive engine (switchboard.min_offered_for_rate).
_MIN_OFFERED_FOR_RATE = 5


def _get_cached_buyers() -> list:
    """Return the cached list of all active buyers, refreshing from Supabase
    if the cache is stale (>60s old). Buyer data (payouts, hours, niches, etc.)
    changes infrequently, so caching eliminates a Supabase query on every call."""
    global _buyers_cache, _buyers_cache_ts
    now = _time.time()
    if _buyers_cache and now - _buyers_cache_ts < _BUYERS_CACHE_TTL:
        return _buyers_cache
    try:
        res = _sb.table("buyers").select("*").eq("is_active", True).execute()
        _buyers_cache = res.data or []
        _buyers_cache_ts = now
        log.info(f"[switchboard] buyers cache refreshed: {len(_buyers_cache)} active")
    except Exception as e:
        log.error(f"[switchboard] buyers cache refresh failed: {e}")
        # Return stale cache on error rather than failing the call
    return _buyers_cache


def _invalidate_buyers_cache():
    """Force the next call to _get_cached_buyers to re-fetch."""
    global _buyers_cache_ts
    _buyers_cache_ts = 0.0



def buyer_is_open(buyer, caller_number):
    tz = buyer.get("timezone") or tz_for_areacode(caller_number)
    try:
        h = datetime.now(ZoneInfo(tz)).hour
    except Exception:
        h = datetime.now(timezone.utc).hour
    return buyer.get("hours_open", 8) <= h < buyer.get("hours_close", 20)

def _reset_if_new_day(buyer):
    from datetime import date
    today = date.today().isoformat()
    if str(buyer.get("last_reset")) != today:
        try:
            _sb.table("buyers").update({"calls_today":0,"calls_accepted":0,"calls_offered":0,"last_reset":today}).eq("id", buyer["id"]).execute()
            buyer["calls_today"]=0; buyer["calls_accepted"]=0; buyer["calls_offered"]=0
        except Exception as e:
            log.error(f"[switchboard] daily reset failed: {e}")

def _acceptance_rate(buyer):
    offered = buyer.get("calls_offered",0) or 0
    accepted = buyer.get("calls_accepted",0) or 0
    if offered < _MIN_OFFERED_FOR_RATE:
        return 1.0
    return accepted / offered

def find_buyer(niche, state, caller_number, value_score=0):
    try:
        # Use cached buyers — filters in-memory instead of querying Supabase
        buyers = _get_cached_buyers()
        if not buyers:
            return None
        candidates = []
        for b in buyers:
            # Skip buyers that don't match this niche/state
            if b.get("niche") != niche:
                continue
            coverage = b.get("state_coverage") or []
            if state not in coverage:
                continue
            _reset_if_new_day(b)
            if not buyer_is_open(b, caller_number):
                continue
            if (b.get("calls_today",0) or 0) >= (b.get("daily_cap",100) or 100):
                continue
            ar = _acceptance_rate(b)
            effective = float(b.get("base_payout",0)) * ar
            candidates.append((effective, ar, b))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        winner = candidates[0][2]
        # Write-through: increment counters in Supabase AND in the cached dict
        try:
            ct = (winner.get("calls_today",0) or 0) + 1
            co = (winner.get("calls_offered",0) or 0) + 1
            _sb.table("buyers").update({"calls_today":ct,"calls_offered":co}).eq("id", winner["id"]).execute()
            winner["calls_today"] = ct
            winner["calls_offered"] = co
        except Exception as e:
            log.error(f"[switchboard] claim failed: {e}")
        return winner
    except Exception as e:
        log.error(f"[switchboard] buyer lookup failed: {e}")
    return None

def score_call_value(niche, state):
    try:
        from bots import predictive_revenue as pr
        return pr.base_for(niche) * pr.COMMISSION_RATE
    except Exception:
        return 0.0

def register_switchboard_routes(app, require_auth=None):

    @app.post("/api/switchboard/route")
    async def route_call(payload: dict):
        niche = payload.get("vertical") or payload.get("niche") or "roofing"
        state = payload.get("caller_state") or payload.get("state") or "TX"
        caller = payload.get("caller_number", "")
        call_id = payload.get("call_id")
        vscore = score_call_value(niche, state)
        buyer = find_buyer(niche, state, caller, vscore)
        try:
            _sb.table("call_logs").insert({
                "vonage_call_id": call_id,
                "buyer_id": buyer["id"] if buyer else None,
                "niche": niche, "caller_state": state, "caller_number": caller,
                "status": "routed" if buyer else "fallback",
                "payout_value": float(buyer.get("base_payout", 0)) if buyer else 0.0,
                "source": payload.get("source","direct"),
            }).execute()
        except Exception as e:
            log.error(f"[switchboard] route log failed: {e}")
        if not buyer:
            return {"destination_phone": WHALE_FALLBACK, "routing_type": "whale_fallback"}
        return {
            "destination_phone": buyer["destination_phone"],
            "routing_type": "predictive_auction",
            "payout_value": float(buyer["base_payout"]),
            "value_score": round(vscore, 2),
        }

    @app.get("/api/switchboard/stats")
    async def stats():
        try:
            today = datetime.now(timezone.utc).date().isoformat()
            r = _sb.table("call_logs").select("status,is_billable,fee_earned,payout_value").gte("created_at", today).execute()
            rows = r.data or []
            bill = [x for x in rows if x.get("is_billable")]
            return {
                "calls_today": len(rows),
                "connected": len([x for x in rows if x.get("status") in ("connected","completed")]),
                "billable": len(bill),
                "total_payout": round(sum(float(x.get("payout_value") or 0) for x in bill), 2),
                "total_fee": round(sum(float(x.get("fee_earned") or 0) for x in bill), 2),
            }
        except Exception as e:
            return {"error": str(e), "calls_today": 0}

    @app.get("/api/switchboard/buyers")
    async def list_buyers():
        try:
            r = _sb.table("buyers").select("*").order("base_payout", desc=True).execute()
            return {"buyers": r.data or []}
        except Exception as e:
            return {"buyers": [], "error": str(e)}

    @app.post("/api/switchboard/buyers")
    async def add_buyer(payload: dict):
        try:
            row = {
                "buyer_name": payload.get("buyer_name","Unnamed"),
                "niche": payload.get("niche","roofing"),
                "state_coverage": payload.get("state_coverage", []),
                "timezone": payload.get("timezone","America/Chicago"),
                "hours_open": int(payload.get("hours_open", 8)),
                "hours_close": int(payload.get("hours_close", 20)),
                "base_payout": float(payload.get("base_payout", 0)),
                "fee_rate": float(payload.get("fee_rate", COMMISSION_RATE)),
                "per_minute_rate": float(payload["per_minute_rate"]) if payload.get("per_minute_rate") is not None else None,
                "per_lead_rate": float(payload["per_lead_rate"]) if payload.get("per_lead_rate") is not None else None,
                "per_schedule_rate": float(payload["per_schedule_rate"]) if payload.get("per_schedule_rate") is not None else None,
            "settlement_rate": float(payload["settlement_rate"]) if payload.get("settlement_rate") is not None else None,
                "destination_phone": payload.get("destination_phone",""),
                "daily_cap": int(payload.get("daily_cap", 100)),
                "is_active": True,
            }
            r = _sb.table("buyers").insert(row).execute()
            _invalidate_buyers_cache()
            return {"ok": True, "buyer": r.data[0] if r.data else None}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.post("/api/switchboard/buyers/{buyer_id}/toggle")
    async def toggle_buyer(buyer_id: str):
        try:
            cur = _sb.table("buyers").select("is_active").eq("id", buyer_id).limit(1).execute()
            if not cur.data:
                return {"ok": False, "error": "not found"}
            newv = not cur.data[0]["is_active"]
            _sb.table("buyers").update({"is_active": newv}).eq("id", buyer_id).execute()
            _invalidate_buyers_cache()
            return {"ok": True, "is_active": newv}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.patch("/api/switchboard/buyers/{buyer_id}")
    async def update_buyer(buyer_id: str, payload: dict):
        try:
            cur = _sb.table("buyers").select("id").eq("id", buyer_id).limit(1).execute()
            if not cur.data:
                return {"ok": False, "error": "buyer not found"}
            updates = {}
            for field in ("buyer_name", "niche", "state_coverage", "timezone",
                         "hours_open", "hours_close", "base_payout", "fee_rate",
                         "destination_phone", "daily_cap", "is_active"):
                if field in payload:
                    val = payload[field]
                    if field in ("hours_open", "hours_close", "daily_cap"):
                        val = int(val)
                    elif field in ("base_payout", "fee_rate"):
                        val = float(val)
                    updates[field] = val
            if "per_minute_rate" in payload:
                pmr = payload["per_minute_rate"]
                updates["per_minute_rate"] = float(pmr) if pmr is not None else None
            if "per_lead_rate" in payload:
                plr = payload["per_lead_rate"]
                updates["per_lead_rate"] = float(plr) if plr is not None else None
            if "per_schedule_rate" in payload:
                psr = payload["per_schedule_rate"]
                updates["per_schedule_rate"] = float(psr) if psr is not None else None
            if "settlement_rate" in payload:
                sr = payload["settlement_rate"]
                updates["settlement_rate"] = float(sr) if sr is not None else None
            if not updates:
                return {"ok": False, "error": "no fields to update"}
            _sb.table("buyers").update(updates).eq("id", buyer_id).execute()
            _invalidate_buyers_cache()
            return {"ok": True, "updated": updates}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/switchboard/calls")
    async def call_history(limit: int = 50):
        try:
            r = (_sb.table("call_logs").select("*")
                 .order("created_at", desc=True).limit(limit).execute())
            return {"calls": r.data or []}
        except Exception as e:
            return {"calls": [], "error": str(e)}

    @app.get("/api/switchboard/timeseries")
    async def timeseries(days: int = 14):
        try:
            from datetime import date, timedelta
            start = (date.today() - timedelta(days=days)).isoformat()
            r = (_sb.table("call_logs").select("created_at,is_billable,fee_earned")
                 .gte("created_at", start).execute())
            rows = r.data or []
            buckets = {}
            for x in rows:
                d = (x.get("created_at") or "")[:10]
                if not d: continue
                b = buckets.setdefault(d, {"date": d, "calls": 0, "billable": 0, "fee": 0.0})
                b["calls"] += 1
                if x.get("is_billable"):
                    b["billable"] += 1
                    b["fee"] += float(x.get("fee_earned") or 0)
            series = sorted(buckets.values(), key=lambda z: z["date"])
            for s in series:
                s["fee"] = round(s["fee"], 2)
            return {"series": series}
        except Exception as e:
            return {"series": [], "error": str(e)}

    @app.get("/api/switchboard/sources")
    async def source_breakdown():
        try:
            from datetime import date
            today = date.today().isoformat()
            r = (_sb.table("call_logs").select("source,is_billable,fee_earned")
                 .gte("created_at", today).execute())
            rows = r.data or []
            agg = {}
            for x in rows:
                src_name = x.get("source") or "direct"
                a = agg.setdefault(src_name, {"source": src_name, "calls": 0, "billable": 0, "fee": 0.0})
                a["calls"] += 1
                if x.get("is_billable"):
                    a["billable"] += 1
                    a["fee"] += float(x.get("fee_earned") or 0)
            out = sorted(agg.values(), key=lambda z: z["fee"], reverse=True)
            for o in out:
                o["fee"] = round(o["fee"], 2)
            return {"sources": out}
        except Exception as e:
            return {"sources": [], "error": str(e)}

    log.info("[switchboard] routes registered")
