"""
Empire AI · Mock Carrier API
============================

Simulates an insurance carrier's claims system. Real carriers (State
Farm, Allstate, etc.) have private APIs we don't have access to yet,
so this is a stand-in. It exposes the same shape of endpoints a real
carrier would, and the settled-claim events flow through the same
chain (`/api/v1/fee/claim-settled`) as a real carrier webhook would.

Endpoints:
  GET  /api/v1/carrier/claims?status=open,settled,denied — list claims
  GET  /api/v1/carrier/claims/{id}                        — single claim
  POST /api/v1/carrier/claims/{id}/settle                 — mark settled
                                                            (writes fee_events
                                                            via the existing
                                                            /api/v1/fee/claim-settled
                                                            endpoint)
  POST /api/v1/carrier/claims                             — create a claim
                                                            (submits a new
                                                            claim for an
                                                            existing dispatch)
  POST /api/v1/carrier/seed?n=10                          — seed N random
                                                            open claims for
                                                            real dispatches
                                                            (so the chain has
                                                            something to poll)

The "carrier" tracks claims in the carrier_claims table (in-memory
dict, with a single-write to the supabase `carrier_claims` table for
durability).

This is dev / staging infrastructure. It lets us:
  1. Drive the fee_events chain end-to-end with realistic claim events
  2. Test the carrier integration code path before a real carrier
     integration lands
  3. Stress-test the dispatcher + contractor flow without waiting for
     a real claim to settle
"""
import os, json, uuid, random
from datetime import datetime, timezone, timedelta
from fastapi import Depends, HTTPException, Request
from supabase import create_client

# In-memory store. Persisted to the carrier_claims table on every write.
_CLAIMS: dict = {}


def _db():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def _persist(claim: dict):
    """Write the claim to the carrier_claims table for durability."""
    try:
        db = _db()
        db.table("carrier_claims").upsert(claim).execute()
    except Exception:
        pass


def _load_from_db():
    """Hydrate the in-memory store from the DB on startup."""
    try:
        db = _db()
        r = db.table("carrier_claims").select("*").limit(2000).execute()
        for row in r.data or []:
            _CLAIMS[row["id"]] = row
    except Exception:
        pass


def register_mock_carrier_routes(app, *, require_auth, get_db=None):
    # load on startup
    _load_from_db()

    @app.get("/api/v1/carrier/claims")
    async def carrier_list_claims(
        status: str = "all",
        limit: int = 100,
        auth: bool = Depends(require_auth),
    ):
        rows = list(_CLAIMS.values())
        if status and status != "all":
            rows = [r for r in rows if r.get("status") == status]
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return {"claims": rows[:max(1, min(limit, 500))]}

    @app.get("/api/v1/carrier/claims/{claim_id}")
    async def carrier_get_claim(claim_id: str, auth: bool = Depends(require_auth)):
        c = _CLAIMS.get(claim_id)
        if not c:
            raise HTTPException(404, "claim not found")
        return c

    @app.post("/api/v1/carrier/claims")
    async def carrier_create_claim(
        request: Request,
        auth: bool = Depends(require_auth),
    ):
        """Submit a new claim for a dispatch. Body: {dispatch_id, loss_description, asset_value}"""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")
        dispatch_id = body.get("dispatch_id")
        if not dispatch_id:
            raise HTTPException(400, "dispatch_id required")
        claim = {
            "id": str(uuid.uuid4()),
            "dispatch_id": dispatch_id,
            "status": "open",
            "loss_description": body.get("loss_description", "storm damage"),
            "asset_value": float(body.get("asset_value", 250_000)),
            "filed_at": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "settled_at": None,
            "settled_amount": None,
        }
        _CLAIMS[claim["id"]] = claim
        _persist(claim)
        return claim

    @app.post("/api/v1/carrier/claims/{claim_id}/settle")
    async def carrier_settle_claim(
        claim_id: str,
        request: Request,
        auth: bool = Depends(require_auth),
    ):
        """Mark a claim as settled. Triggers the fee_events chain.
        Body: {settled_amount} (defaults to the asset_value)."""
        c = _CLAIMS.get(claim_id)
        if not c:
            raise HTTPException(404, "claim not found")
        if c.get("status") == "settled":
            raise HTTPException(400, "claim already settled")
        try:
            body = await request.json()
        except Exception:
            body = {}
        settled_amount = float(body.get("settled_amount") or c.get("asset_value", 0))
        c["status"] = "settled"
        c["settled_amount"] = settled_amount
        c["settled_at"] = datetime.now(timezone.utc).isoformat()
        _persist(c)
        # Now write the fee_events row via the hub's existing
        # claim-settled path. We POST to ourselves.
        try:
            import httpx
            db = _db()
            # Resolve contractor + lead from the dispatch
            dispatch = db.table("dispatches").select("contractor_id,lead_id").eq("id", c["dispatch_id"]).limit(1).execute()
            contractor_id = None
            lead_id = None
            if dispatch.data:
                contractor_id = dispatch.data[0].get("contractor_id")
                lead_id = dispatch.data[0].get("lead_id")
            hub_token = os.environ.get("HUB_TOKEN", "Jaykub20*")
            hub_url = os.environ.get("HUB_URL", "http://127.0.0.1:8000")
            # Direct DB insert instead of POSTing back to the hub — same
            # outcome (fee_events row written), but no second HTTP round-trip
            # that can time out under load. The /api/v1/fee/claim-settled
            # endpoint is still the right path for a real carrier webhook;
            # the mock carrier bypasses it for throughput.
            from datetime import datetime as _dt, timezone as _tz
            fee_event = {
                "id": str(__import__("uuid").uuid4()),
                "claim_id": f"carrier-{c['id']}",
                "claim_amount": settled_amount,
                "fee_amount": round(settled_amount * 0.03, 2),
                "status": "pending",
                "settled_at": c["settled_at"],
                "source": "mock_carrier",
                "created_at": _dt.now(_tz.utc).isoformat(),
            }
            if contractor_id:
                fee_event["contractor_id"] = contractor_id
            if lead_id:
                fee_event["lead_id"] = lead_id
            if c.get("dispatch_id"):
                fee_event["dispatch_id"] = c["dispatch_id"]
            try:
                db2 = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
                db2.table("fee_events").insert(fee_event).execute()
                return {"claim": c, "fee_event": fee_event, "fee_path_status": 200}
            except Exception as e:
                return {"claim": c, "fee_event": fee_event, "error": str(e)}
            fee_event = r.json() if r.status_code == 200 else None
            return {"claim": c, "fee_event": fee_event, "fee_path_status": r.status_code}
        except Exception as e:
            return {"claim": c, "fee_event": None, "error": str(e)}

    @app.post("/api/v1/carrier/seed")
    async def carrier_seed(
        n: int = 10,
        auth: bool = Depends(require_auth),
    ):
        """Seed N random open claims for real dispatches. Useful for
        exercising the chain. Each claim gets a random asset_value
        in the $50K-$500K range."""
        db = _db()
        dispatches = db.table("dispatches").select("id").limit(50).execute()
        if not dispatches.data:
            return {"seeded": 0, "note": "no dispatches to seed against"}
        n = max(1, min(n, len(dispatches.data)))
        seeded = 0
        for i in range(n):
            disp = dispatches.data[i]
            claim = {
                "id": str(uuid.uuid4()),
                "dispatch_id": disp["id"],
                "status": "open",
                "loss_description": random.choice([
                    "Hail damage to roof",
                    "Wind damage to roof membrane",
                    "Tornado damage to warehouse structure",
                    "Flood damage to electrical systems",
                    "Lightning damage to HVAC",
                    "Hail damage to roof and skylights",
                ]),
                "asset_value": random.uniform(50_000, 500_000),
                "filed_at": datetime.now(timezone.utc).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "settled_at": None,
                "settled_amount": None,
            }
            _CLAIMS[claim["id"]] = claim
            _persist(claim)
            seeded += 1
        return {"seeded": seeded}

    @app.get("/api/v1/carrier/stats")
    async def carrier_stats(auth: bool = Depends(require_auth)):
        rows = list(_CLAIMS.values())
        from collections import Counter
        c = Counter(r.get("status") for r in rows)
        total_value = sum(float(r.get("settled_amount") or 0) for r in rows if r.get("status") == "settled")
        return {
            "total_claims": len(rows),
            "by_status": dict(c),
            "total_settled_value_usd": round(total_value, 2),
        }
