"""
EMPIRE V49 · PRODUCT: B2B PRO
==============================
Comprehensive B2B product combining three pillars:

1. COMMERCIAL PROPERTY INTEL
   - Property profiles (type, age, value, roof, flood zone)
   - Storm/weather risk assessments
   - Decision-maker contact discovery

2. B2B LEAD NETWORK
   - Browse available lead streams by niche + metro
   - Subscribe to receive qualified leads
   - Track delivery and usage

3. CONTRACTOR PROSPECTING ENGINE
   - Find commercial contract opportunities
   - Enrich with decision-maker contacts
   - Ranked opportunity list with outreach-ready data

Built on top of existing systems: research_agent, prospector, decision_makers,
strike_packs, and the suite gateway monetization.
"""
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, List, Dict, Any

from fastapi import FastAPI

log = logging.getLogger("empire.product.b2b_pro")

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "storm_alerts.sqlite"

# ── Lazy imports for existing subsystems ────────────────────────────
_RESEARCH_AGENT = None
_PROSPECTOR = None
_DECISION_MAKERS = None


def _get_research_agent():
    global _RESEARCH_AGENT
    if _RESEARCH_AGENT is None:
        from bots.research_agent import ResearchAgent
        _RESEARCH_AGENT = ResearchAgent()
    return _RESEARCH_AGENT


def _get_prospector():
    global _PROSPECTOR
    if _PROSPECTOR is None:
        from bots.prospector import find_prospects
        _PROSPECTOR = find_prospects
    return _PROSPECTOR


def _get_decision_makers():
    global _DECISION_MAKERS
    if _DECISION_MAKERS is None:
        from bots import decision_makers
        _DECISION_MAKERS = decision_makers
    return _DECISION_MAKERS


# ── Initialize DB tables on first import ────────────────────────────
def _init_tables():
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS b2b_lead_subscriptions (
                subscription_id       TEXT PRIMARY KEY,
                customer_account_id   TEXT NOT NULL,
                niche                 TEXT NOT NULL,
                metro                 TEXT NOT NULL,
                max_leads_per_day     INTEGER DEFAULT 10,
                webhook_url           TEXT DEFAULT '',
                status                TEXT DEFAULT 'ACTIVE',
                leads_delivered       INTEGER DEFAULT 0,
                created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_b2b_subs_account
                ON b2b_lead_subscriptions (customer_account_id, status);
        """)
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


_init_tables()


class B2BPro:
    """Enterprise B2B product — property intelligence, lead marketplace,
    and contractor prospecting. Suite-gated with guard and log_usage."""

    def __init__(
        self,
        guard: Optional[Callable] = None,      # SuiteGuard.check_access
        log_usage: Optional[Callable] = None,  # SuiteGuard.log_usage
    ):
        self.guard = guard
        self.log_usage = log_usage
        self.stats = {
            "property_lookups": 0,
            "risk_assessments": 0,
            "owner_lookups": 0,
            "leads_browsed": 0,
            "subscriptions_active": 0,
            "opportunities_found": 0,
            "errors": 0,
        }

    async def check_entitlement(self, account_id: str) -> dict:
        if not self.guard:
            return {"ok": True, "tier": "standalone"}
        if not account_id:
            return {"ok": False, "error": "customer_account_id required"}
        return self.guard(account_id, "inbound_router")

    # ═════════════════════════════════════════════════════════════════
    # PILLAR 1: COMMERCIAL PROPERTY INTEL
    # ═════════════════════════════════════════════════════════════════

    async def property_intel(self, account_id: str, address: str,
                              zip_code: str = "", metro: str = "",
                              niche: str = "Commercial Property") -> Dict:
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            return {"ok": False, "error": entitlement.get("error", "Access denied")}

        try:
            agent = _get_research_agent()
            import asyncio
            prop_task = agent.research_property(address, zip_code, metro)
            market_task = agent.research_market(metro or "national", niche)
            results = await asyncio.gather(prop_task, market_task, return_exceptions=True)

            property_data = results[0] if not isinstance(results[0], Exception) else {}
            market_data = results[1] if not isinstance(results[1], Exception) else {}

            if isinstance(results[0], Exception):
                log.debug(f"[b2b-pro] property research failed: {results[0]}")
            if isinstance(results[1], Exception):
                log.debug(f"[b2b-pro] market research failed: {results[1]}")

            self.stats["property_lookups"] += 1

            if self.log_usage:
                try:
                    self.log_usage(account_id, "b2b_pro", "property_intel",
                                   metadata={"address": address[:60], "zip": zip_code})
                except Exception:
                    pass

            return {
                "ok": True,
                "property": property_data,
                "market": market_data,
                "confidence": property_data.get("confidence_level", "low"),
            }
        except Exception as e:
            self.stats["errors"] += 1
            return {"ok": False, "error": str(e)}

    async def property_risk(self, account_id: str, zip_code: str,
                             metro: str = "") -> Dict:
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            return {"ok": False, "error": entitlement.get("error", "Access denied")}

        try:
            agent = _get_research_agent()
            risk_data = await agent.research_storm_history(zip_code, metro)
            self.stats["risk_assessments"] += 1

            if self.log_usage:
                try:
                    self.log_usage(account_id, "b2b_pro", "property_risk",
                                   metadata={"zip": zip_code, "metro": metro})
                except Exception:
                    pass

            return {
                "ok": True,
                "risk": risk_data,
                "confidence": risk_data.get("confidence_level", "low"),
            }
        except Exception as e:
            self.stats["errors"] += 1
            return {"ok": False, "error": str(e)}

    async def property_owners(self, account_id: str, address: str,
                               business_name: str = "") -> Dict:
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            return {"ok": False, "error": entitlement.get("error", "Access denied")}

        try:
            owners = []
            if business_name:
                # Run sync enrichment off the event loop via thread pool
                import asyncio
                enriched = await asyncio.to_thread(
                    _sync_enrich_website, business_name
                )
                if enriched:
                    owners.append(enriched)

            if not owners and address:
                owners.append({
                    "name": "Property Owner (unverified)",
                    "title": "Owner / Manager",
                    "source": "property_record",
                    "confidence": "low",
                })

            self.stats["owner_lookups"] += 1

            if self.log_usage:
                try:
                    self.log_usage(account_id, "b2b_pro", "owner_lookup",
                                   metadata={"address": address[:60]})
                except Exception:
                    pass

            return {"ok": True, "owners": owners, "count": len(owners)}
        except Exception as e:
            self.stats["errors"] += 1
            return {"ok": False, "error": str(e)}

    # ═════════════════════════════════════════════════════════════════
    # PILLAR 2: B2B LEAD NETWORK
    # ═════════════════════════════════════════════════════════════════

    async def available_leads(self, account_id: str, niche: str = "",
                               metro: str = "") -> Dict:
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            return {"ok": False, "error": entitlement.get("error", "Access denied")}

        self.stats["leads_browsed"] += 1

        lead_streams = [
            {
                "niche": "Roofing Restoration",
                "metros": ["Dallas", "Fort Worth", "Houston", "Austin", "San Antonio",
                          "Oklahoma City", "Wichita", "Denver", "Kansas City"],
                "estimated_leads_per_day": 15,
                "price_per_lead": 4.50,
                "lead_types": ["storm_damage", "insurance_claim", "emergency_repair"],
                "buyer_types": ["roofing_contractor", "restoration_company"],
            },
            {
                "niche": "Mass Tort",
                "metros": ["National"],
                "estimated_leads_per_day": 8,
                "price_per_lead": 12.00,
                "lead_types": ["pharma_liability", "medical_device", "toxic_exposure"],
                "buyer_types": ["law_firm", "legal_intake"],
            },
            {
                "niche": "Commercial Property",
                "metros": ["Dallas", "Houston", "Austin", "San Antonio", "Fort Worth"],
                "estimated_leads_per_day": 10,
                "price_per_lead": 8.00,
                "lead_types": ["warehouse", "industrial", "office", "retail"],
                "buyer_types": ["commercial_contractor", "property_manager"],
            },
            {
                "niche": "Tornado Damage Repair",
                "metros": ["Oklahoma City", "Wichita", "Dallas", "Kansas City", "Denver"],
                "estimated_leads_per_day": 12,
                "price_per_lead": 5.00,
                "lead_types": ["tornado_damage", "structural_repair", "emergency_tarp"],
                "buyer_types": ["restoration_contractor", "general_contractor"],
            },
            {
                "niche": "Hurricane Damage Restoration",
                "metros": ["Houston", "Gulf Coast", "Florida", "Carolinas"],
                "estimated_leads_per_day": 20,
                "price_per_lead": 6.00,
                "lead_types": ["flood_damage", "wind_damage", "mold_remediation"],
                "buyer_types": ["restoration_company", "water_damage_specialist"],
            },
            {
                "niche": "Consumer CPA",
                "metros": ["National"],
                "estimated_leads_per_day": 5,
                "price_per_lead": 15.00,
                "lead_types": ["tax_preparation", "small_business_accounting", "irs_help"],
                "buyer_types": ["cpa_firm", "tax_preparer"],
            },
        ]

        if niche:
            lead_streams = [s for s in lead_streams
                           if niche.lower() in s["niche"].lower()]
        if metro:
            filtered = []
            for s in lead_streams:
                matching_metros = [m for m in s["metros"]
                                  if metro.lower() in m.lower()]
                if matching_metros:
                    s_filtered = dict(s)
                    s_filtered["metros"] = matching_metros
                    filtered.append(s_filtered)
            lead_streams = filtered

        return {"ok": True, "lead_streams": lead_streams, "count": len(lead_streams)}

    async def subscribe(self, account_id: str, niche: str,
                         metro: str, max_leads_per_day: int = 10,
                         webhook_url: str = "") -> Dict:
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            return {"ok": False, "error": entitlement.get("error", "Access denied")}
        if not niche or not metro:
            return {"ok": False, "error": "niche and metro required"}

        subscription_id = "b2b_sub_" + str(uuid.uuid4())[:12]

        conn = sqlite3.connect(str(DB_PATH))
        try:
            conn.execute(
                """INSERT OR REPLACE INTO b2b_lead_subscriptions
                   (subscription_id, customer_account_id, niche, metro,
                    max_leads_per_day, webhook_url, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', datetime('now'))""",
                (subscription_id, account_id, niche, metro,
                 max_leads_per_day, webhook_url or ""),
            )
            conn.commit()
            self.stats["subscriptions_active"] += 1
        except sqlite3.OperationalError as e:
            log.warning(f"[b2b-pro] subscribe persistence failed: {e}")
        finally:
            conn.close()

        if self.log_usage:
            try:
                self.log_usage(account_id, "b2b_pro", "lead_subscribe",
                               quantity=max_leads_per_day,
                               metadata={"niche": niche, "metro": metro})
            except Exception:
                pass

        return {
            "ok": True,
            "subscription_id": subscription_id,
            "niche": niche,
            "metro": metro,
            "max_leads_per_day": max_leads_per_day,
            "status": "ACTIVE",
        }

    async def my_subscriptions(self, account_id: str) -> Dict:
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            return {"ok": False, "error": entitlement.get("error", "Access denied")}

        subscriptions = []
        conn = sqlite3.connect(str(DB_PATH))
        try:
            cursor = conn.execute(
                "SELECT * FROM b2b_lead_subscriptions WHERE customer_account_id = ? ORDER BY created_at DESC",
                (account_id,),
            )
            columns = [d[0] for d in cursor.description]
            for row in cursor.fetchall():
                subscriptions.append(dict(zip(columns, row)))
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()

        return {"ok": True, "subscriptions": subscriptions, "count": len(subscriptions)}

    # ═════════════════════════════════════════════════════════════════
    # PILLAR 3: CONTRACTOR PROSPECTING ENGINE
    # ═════════════════════════════════════════════════════════════════

    async def find_opportunities(self, account_id: str, metro: str,
                                  niche: str = "roofing") -> Dict:
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            return {"ok": False, "error": entitlement.get("error", "Access denied")}
        if not metro:
            return {"ok": False, "error": "metro required"}

        try:
            find_prospects = _get_prospector()
            prospects = await find_prospects(metro=metro, niche=niche)

            enriched_count = 0
            opportunities = []
            for p in prospects[:25]:
                opp = {
                    "business_name": p.get("business_name", ""),
                    "phone": p.get("phone", ""),
                    "website": p.get("website", ""),
                    "address": p.get("address", ""),
                    "rating": p.get("rating", 0),
                    "review_count": p.get("review_count", 0) or p.get("user_ratings_total", 0),
                    "opportunity_score": p.get("buy_signal_score", 0),
                    "decision_maker": None,
                    "contact_title": None,
                }
                opportunities.append(opp)

            # Enrich businesses with websites — run sync scraping off event loop
            import asyncio
            enrichment_tasks = []
            website_indices = []
            for i, opp in enumerate(opportunities):
                if opp["website"]:
                    enrichment_tasks.append(
                        asyncio.to_thread(_sync_enrich_website, opp["business_name"])
                    )
                    website_indices.append(i)

            if enrichment_tasks:
                results = await asyncio.gather(*enrichment_tasks, return_exceptions=True)
                for idx, result in zip(website_indices, results):
                    if isinstance(result, dict) and result.get("name"):
                        opportunities[idx]["decision_maker"] = result["name"]
                        opportunities[idx]["contact_title"] = result.get("title", "Owner")
                        enriched_count += 1

            self.stats["opportunities_found"] += len(opportunities)

            if self.log_usage:
                try:
                    self.log_usage(account_id, "b2b_pro", "prospect_scan",
                                   quantity=len(opportunities),
                                   metadata={"metro": metro, "niche": niche})
                except Exception:
                    pass

            # Market context
            market_context = {}
            try:
                agent = _get_research_agent()
                market_data = await agent.research_market(metro, niche)
                if isinstance(market_data, dict):
                    market_context = {
                        "demand_level": market_data.get("demand_level", "unknown"),
                        "price_trend": market_data.get("price_trend", "unknown"),
                        "market_health_score": market_data.get("market_health_score"),
                    }
            except Exception:
                pass

            return {
                "ok": True,
                "metro": metro,
                "niche": niche,
                "opportunities": opportunities,
                "total_found": len(opportunities),
                "enriched_count": enriched_count,
                "market_context": market_context,
            }
        except Exception as e:
            self.stats["errors"] += 1
            return {"ok": False, "error": str(e)}

    # ── Stats ────────────────────────────────────────────────────────

    def snapshot(self) -> Dict:
        return {**self.stats}


# ── Sync enrichment helper (runs off event loop via asyncio.to_thread) ──
def _sync_enrich_website(business_name: str) -> Optional[Dict]:
    """Sync decision-maker lookup — runs in thread pool to avoid blocking.
    Queries the Supabase prospects table directly for a matching business."""
    try:
        import os as _os
        from supabase import create_client
        _url = _os.environ.get("SUPABASE_URL", "")
        _key = _os.environ.get("SUPABASE_SERVICE_KEY", "")
        if not _url or not _key:
            return None
        _sb = create_client(_url, _key)
        res = _sb.table("prospects") \
            .select("contact_name,contact_title") \
            .ilike("business_name", f"%{business_name[:60]}%") \
            .not_.is_("contact_name", "null") \
            .limit(1).execute()
        if res.data and res.data[0].get("contact_name"):
            return {
                "name": res.data[0]["contact_name"],
                "title": res.data[0].get("contact_title", "Owner"),
                "source": "prospects_db",
            }
        return None
    except Exception:
        return None


# ═════════════════════════════════════════════════════════════════════
# ROUTES
# ═════════════════════════════════════════════════════════════════════

class B2BProRoutes:
    """Wire B2B Pro endpoints into the FastAPI app."""

    def __init__(self, engine: B2BPro, require_auth: Optional[Callable] = None):
        self.engine = engine
        self.require_auth = require_auth

    def register(self, app):
        from fastapi import Depends, Query
        from fastapi.responses import JSONResponse

        # ── Property Intel ───────────────────────────────────────────

        @app.get("/api/v6/b2b/property/lookup")
        async def b2b_property_lookup(
            account_id: str = Query("standalone_user"),
            address: str = Query(...),
            zip_code: str = "",
            metro: str = "",
            niche: str = "Commercial Property",
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            result = await self.engine.property_intel(
                account_id=account_id, address=address,
                zip_code=zip_code, metro=metro, niche=niche,
            )
            status = 403 if result.get("step") == "entitlement" else (
                200 if result.get("ok") else 400)
            return JSONResponse(result, status_code=status)

        @app.get("/api/v6/b2b/property/risk")
        async def b2b_property_risk(
            account_id: str = Query("standalone_user"),
            zip_code: str = Query(...),
            metro: str = "",
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            result = await self.engine.property_risk(account_id, zip_code, metro)
            status = 403 if result.get("step") == "entitlement" else (
                200 if result.get("ok") else 400)
            return JSONResponse(result, status_code=status)

        @app.get("/api/v6/b2b/property/owners")
        async def b2b_property_owners(
            account_id: str = Query("standalone_user"),
            address: str = Query(...),
            business_name: str = "",
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            result = await self.engine.property_owners(account_id, address, business_name)
            status = 403 if result.get("step") == "entitlement" else (
                200 if result.get("ok") else 400)
            return JSONResponse(result, status_code=status)

        # ── Lead Network ─────────────────────────────────────────────

        @app.get("/api/v6/b2b/leads/available")
        async def b2b_leads_available(
            account_id: str = Query("standalone_user"),
            niche: str = "",
            metro: str = "",
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            return JSONResponse(
                await self.engine.available_leads(account_id, niche, metro))

        @app.post("/api/v6/b2b/leads/subscribe")
        async def b2b_leads_subscribe(
            payload: dict,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            account_id = payload.get("customer_account_id") or "standalone_user"
            result = await self.engine.subscribe(
                account_id=account_id,
                niche=payload.get("niche", ""),
                metro=payload.get("metro", ""),
                max_leads_per_day=payload.get("max_leads_per_day", 10),
                webhook_url=payload.get("webhook_url", ""),
            )
            status = 403 if result.get("step") == "entitlement" else (
                200 if result.get("ok") else 400)
            return JSONResponse(result, status_code=status)

        @app.get("/api/v6/b2b/leads/mine")
        async def b2b_leads_mine(
            account_id: str = Query("standalone_user"),
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            return JSONResponse(await self.engine.my_subscriptions(account_id))

        # ── Contractor Prospecting ───────────────────────────────────

        @app.get("/api/v6/b2b/prospect/opportunities")
        async def b2b_prospect_opportunities(
            account_id: str = Query("standalone_user"),
            metro: str = Query(...),
            niche: str = "roofing",
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            result = await self.engine.find_opportunities(account_id, metro, niche)
            status = 403 if result.get("step") == "entitlement" else (
                200 if result.get("ok") else 400)
            return JSONResponse(result, status_code=status)

        @app.get("/api/v6/b2b/stats")
        async def b2b_stats(
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            return JSONResponse(self.engine.snapshot())

        log.info("[b2b-pro] Routes registered · /api/v6/b2b/*")


# ═════════════════════════════════════════════════════════════════════
# STANDALONE APP
# ═════════════════════════════════════════════════════════════════════

def create_standalone_app() -> FastAPI:
    standalone = FastAPI(title="Empire AI · B2B Pro", version="1.0.0")

    from fastapi.middleware.cors import CORSMiddleware
    standalone.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    engine = B2BPro()
    B2BProRoutes(engine).register(standalone)

    @standalone.get("/")
    async def root():
        return {
            "service": "Empire AI B2B Pro",
            "version": "1.0.0",
            "endpoints": [
                "GET  /api/v6/b2b/property/lookup",
                "GET  /api/v6/b2b/property/risk",
                "GET  /api/v6/b2b/property/owners",
                "GET  /api/v6/b2b/leads/available",
                "POST /api/v6/b2b/leads/subscribe",
                "GET  /api/v6/b2b/leads/mine",
                "GET  /api/v6/b2b/prospect/opportunities",
                "GET  /api/v6/b2b/stats",
            ],
        }

    return standalone


app = create_standalone_app()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("B2B_PRO_PORT", "8044"))
    host = os.environ.get("B2B_PRO_HOST", "0.0.0.0")
    log.info(f"[b2b-pro] Starting standalone on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
