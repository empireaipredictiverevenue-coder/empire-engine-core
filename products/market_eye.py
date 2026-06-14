"""
Empire AI · Market Eye Product (Phase 1)
=========================================
Competitive intelligence engine — DB-backed competitor tracking, website
scrape & diff detection, price change monitoring, review tracking, alert
system, and weekly competitive brief generation.

Tiers:
  MARKET_EYE_STARTER    ($199/mo)  — 500 checks, no briefs, no alerts
  MARKET_EYE_GROWTH     ($499/mo)  — 2,000 checks, weekly briefs + alerts
  MARKET_EYE_ENTERPRISE ($999/mo)  — 10,000 checks, everything unlimited
"""

import asyncio
import hashlib
import json
import logging
import re
import time as _time
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel

log = logging.getLogger("empire.market_eye")

# ── Tier limits ──────────────────────────────────────────────────────────────
TIER_LIMITS = {
    "MARKET_EYE_STARTER":    {"max_checks": 500,  "max_competitors": 5,   "brief": False, "alerts": False},
    "MARKET_EYE_GROWTH":     {"max_checks": 2000, "max_competitors": 20,  "brief": True,  "alerts": True},
    "MARKET_EYE_ENTERPRISE": {"max_checks": 10000,"max_competitors": 100, "brief": True,  "alerts": True},
}

# ── Price detection patterns (regex to find prices in HTML text) ────────────
_PRICE_PATTERNS = [
    re.compile(r'\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)', re.I),
    re.compile(r'(?:price|pricing|plans?|starting at)\s*[:\-]?\s*\$?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)', re.I),
    re.compile(r'monthly|/mo|per month|/month', re.I),
    re.compile(r'(?:free trial|free|demo|no credit card)', re.I),
]

# ── Config ─────────────────────────────────────────────────────────────────
MONITOR_INTERVAL_SEC = int(3600)  # scrape eligible competitors every hour
BRIEF_INTERVAL_SEC = 604800       # generate briefs weekly (7 days)

# ── Pydantic models ─────────────────────────────────────────────────────────
class CompetitorCreate(BaseModel):
    name: str
    website: str
    niche: str = ""
    notes: str = ""
    scrape_interval_h: int = 24


class CompetitorUpdate(BaseModel):
    name: Optional[str] = None
    website: Optional[str] = None
    niche: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None
    scrape_interval_h: Optional[int] = None


# ═════════════════════════════════════════════════════════════════════════
# MARKET EYE ENGINE
# ═════════════════════════════════════════════════════════════════════════

class MarketEyeEngine:
    """DB-backed competitive intelligence engine with persistence."""

    def __init__(
        self,
        guard: Optional[Callable] = None,
        get_db: Optional[Callable] = None,
    ):
        self.guard = guard
        self.get_db = get_db
        self.stats = {
            "competitors": 0, "scrapes": 0, "alerts": 0,
            "briefs": 0, "changes": 0, "errors": 0,
        }
        self._stop_loop = False

    # ── Entitlement ──────────────────────────────────────────────────────

    async def check_entitlement(self, account_id: str) -> dict:
        if not self.guard:
            return {"ok": True, "tier": "MARKET_EYE_GROWTH", "limits": TIER_LIMITS["MARKET_EYE_GROWTH"]}
        result = self.guard(account_id, "market_eye")
        if not isinstance(result, dict):
            result = {"ok": False, "error": "Guard returned non-dict"}
        if not result.get("ok"):
            return result
        tier = result.get("tier", "MARKET_EYE_STARTER")
        return {"ok": True, "tier": tier, "limits": TIER_LIMITS.get(tier, TIER_LIMITS["MARKET_EYE_STARTER"])}

    # ── Competitor CRUD ─────────────────────────────────────────────────

    def add_competitor(self, account_id: str, name: str, website: str,
                       niche: str = "", notes: str = "",
                       scrape_interval_h: int = 24) -> dict:
        """Register a competitor to monitor. Persisted via DB."""
        try:
            db = self.get_db()
            # Check tier limit
            existing = db.table("competitor_tracking") \
                .select("id", count="exact") \
                .eq("account_id", account_id) \
                .eq("is_active", True) \
                .execute()
            current_count = getattr(existing, "count", len(existing.data or []))
            # Check if already registered
            dup = db.table("competitor_tracking") \
                .select("id") \
                .eq("account_id", account_id) \
                .eq("name", name) \
                .limit(1) \
                .execute()
            if dup.data:
                return {"ok": False, "error": f"Competitor '{name}' already registered", "existing": dup.data[0]}

            now = datetime.now(timezone.utc).isoformat()
            row = db.table("competitor_tracking").insert({
                "account_id": account_id,
                "name": name,
                "website": website,
                "niche": niche,
                "notes": notes,
                "scrape_interval_h": scrape_interval_h,
                "created_at": now,
                "updated_at": now,
            }).execute()
            self.stats["competitors"] += 1
            return {"ok": True, "competitor": (row.data or [{}])[0]}
        except Exception as e:
            self.stats["errors"] += 1
            log.warning(f"[market_eye] add competitor failed: {e}")
            return {"ok": False, "error": str(e)[:200]}

    def list_competitors(self, account_id: str, niche: str = "") -> list:
        """List competitors for an account, optionally filtered by niche."""
        try:
            db = self.get_db()
            q = db.table("competitor_tracking") \
                .select("*") \
                .eq("account_id", account_id) \
                .order("created_at", desc=True)
            if niche:
                q = q.eq("niche", niche)
            r = q.execute()
            return r.data or []
        except Exception as e:
            log.warning(f"[market_eye] list competitors failed: {e}")
            return []

    def get_competitor(self, competitor_id: int, account_id: str = "") -> Optional[dict]:
        """Get a single competitor by ID."""
        try:
            db = self.get_db()
            q = db.table("competitor_tracking").select("*").eq("id", competitor_id)
            if account_id:
                q = q.eq("account_id", account_id)
            r = q.limit(1).execute()
            return (r.data or [None])[0]
        except Exception:
            return None

    def update_competitor(self, competitor_id: int, account_id: str,
                          updates: dict) -> dict:
        """Update competitor fields."""
        allowed = {"name", "website", "niche", "notes", "is_active", "scrape_interval_h"}
        clean = {k: v for k, v in updates.items() if k in allowed and v is not None}
        if not clean:
            return {"ok": False, "error": "No valid fields to update"}
        clean["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            db = self.get_db()
            q = db.table("competitor_tracking").update(clean).eq("id", competitor_id)
            if account_id:
                q = q.eq("account_id", account_id)
            r = q.execute()
            return {"ok": True, "competitor": (r.data or [{}])[0]}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    def delete_competitor(self, competitor_id: int, account_id: str) -> dict:
        """Soft-delete a competitor."""
        return self.update_competitor(competitor_id, account_id, {"is_active": False})

    # ── Scraping ────────────────────────────────────────────────────────

    def scrape(self, competitor_id: int, account_id: str = "") -> dict:
        """Scrape a competitor's website, compare with last snapshot, detect changes."""
        comp = self.get_competitor(competitor_id, account_id)
        if not comp:
            return {"ok": False, "error": "Competitor not found"}

        self.stats["scrapes"] += 1
        now = datetime.now(timezone.utc).isoformat()

        try:
            import httpx
            r = httpx.get(comp["website"], timeout=20.0, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0 (compatible; EmpireAI-MarketEye/1.0)"})
            body = r.text
            content_hash = hashlib.sha256(body.encode()).hexdigest()

            # Extract key signals
            title = ""
            if "<title>" in body:
                title = body.split("<title>")[1].split("</title>")[0].strip()

            # Extract meta/OG tags
            headers_json = {}
            for tag in re.findall(r'<meta\s+[^>]*>', body[:10000], re.I):
                name = re.search(r'(?:name|property)="([^"]+)"', tag)
                content = re.search(r'content="([^"]+)"', tag)
                if name and content:
                    headers_json[name.group(1)] = content.group(1)[:200]

            # Extract links count
            links_found = len(re.findall(r'<a\s+', body, re.I))

            # Word count (rough)
            text = re.sub(r'<[^>]+>', ' ', body)
            words = text.split()
            word_count = len(words)

            # Price detection
            prices_found = []
            for pat in _PRICE_PATTERNS:
                for m in pat.findall(body[:50000]):
                    prices_found.append(m.strip())
            unique_prices = list(set(prices_found))[:10]

            # Diff detection vs last snapshot
            diff_detected = False
            diff_summary = ""
            if comp.get("last_content_hash") and content_hash != comp["last_content_hash"]:
                diff_detected = True
                # Basic diff summary: title change, price change, or generic
                if title and title != (comp.get("last_title") or ""):
                    diff_summary = f"Title changed: '{comp.get('last_title')}' → '{title}'"
                elif unique_prices:
                    diff_summary = f"Prices detected: {', '.join(unique_prices[:3])}"
                else:
                    diff_summary = "Content structure changed"
                self.stats["changes"] += 1

            # Save snapshot
            db = self.get_db()
            db.table("competitor_snapshots").insert({
                "competitor_id": competitor_id,
                "account_id": account_id or comp.get("account_id", "demo"),
                "status_code": r.status_code,
                "title": title,
                "headers_json": json.dumps(headers_json),
                "body_snippet": body[:2000],
                "content_hash": content_hash,
                "word_count": word_count,
                "links_found": links_found,
                "diff_detected": 1 if diff_detected else 0,
                "diff_summary": diff_summary,
                "meta": json.dumps({"prices": unique_prices}),
                "created_at": now,
            }).execute()

            # Update competitor tracking record
            update_data = {
                "last_scraped_at": now,
                "last_title": title,
                "last_status": r.status_code,
                "last_content_hash": content_hash,
                "last_price_change": json.dumps(unique_prices) if unique_prices else comp.get("last_price_change"),
                "change_count": (comp.get("change_count", 0) or 0) + (1 if diff_detected else 0),
                "updated_at": now,
            }
            db.table("competitor_tracking").update(update_data).eq("id", competitor_id).execute()

            # Generate alert on change
            alert_created = False
            if diff_detected:
                alert_created = self._create_alert(
                    account_id=account_id or comp.get("account_id", "demo"),
                    competitor_id=competitor_id,
                    alert_type="content_change" if not unique_prices else "price_change",
                    severity="warning" if unique_prices else "info",
                    title=f"Change detected: {comp['name']}",
                    description=diff_summary or "Website content changed",
                    old_value=comp.get("last_title", ""),
                    new_value=title,
                )

            return {
                "ok": True,
                "competitor": comp["name"],
                "status_code": r.status_code,
                "title": title,
                "word_count": word_count,
                "links_found": links_found,
                "prices_detected": unique_prices,
                "content_hash": content_hash[:16],
                "diff_detected": diff_detected,
                "diff_summary": diff_summary,
                "alert_created": alert_created,
                "scraped_at": now,
            }
        except Exception as e:
            self.stats["errors"] += 1
            log.warning(f"[market_eye] scrape failed {comp['name']}: {e}")
            # Log the failed scrape attempt
            try:
                db = self.get_db()
                db.table("competitor_snapshots").insert({
                    "competitor_id": competitor_id,
                    "account_id": account_id or comp.get("account_id", "demo"),
                    "status_code": 0,
                    "body_snippet": f"Scrape error: {str(e)[:200]}",
                    "created_at": now,
                }).execute()
            except Exception:
                pass
            return {"ok": False, "error": str(e)[:200], "competitor": comp["name"]}

    # ── Alerts ──────────────────────────────────────────────────────────

    def _create_alert(self, account_id: str, competitor_id: int,
                      alert_type: str, severity: str, title: str,
                      description: str = "", old_value: str = "",
                      new_value: str = "") -> bool:
        """Create a competitor alert. Returns True if created."""
        try:
            db = self.get_db()
            db.table("competitor_alerts").insert({
                "account_id": account_id,
                "competitor_id": competitor_id,
                "alert_type": alert_type,
                "severity": severity,
                "title": title,
                "description": description,
                "old_value": old_value,
                "new_value": new_value,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
            self.stats["alerts"] += 1
            return True
        except Exception as e:
            log.warning(f"[market_eye] alert creation failed: {e}")
            return False

    def list_alerts(self, account_id: str, unread_only: bool = False,
                    limit: int = 50) -> list:
        """List alerts for an account."""
        try:
            db = self.get_db()
            q = db.table("competitor_alerts") \
                .select("*, competitor_tracking!inner(name, website, niche)") \
                .eq("competitor_alerts.account_id", account_id) \
                .order("created_at", desc=True) \
                .limit(min(limit, 200))
            if unread_only:
                q = q.eq("acknowledged", False)
            r = q.execute()
            return r.data or []
        except Exception:
            return []

    def acknowledge_alert(self, alert_id: int, account_id: str) -> dict:
        """Mark an alert as acknowledged."""
        try:
            db = self.get_db()
            now = datetime.now(timezone.utc).isoformat()
            r = db.table("competitor_alerts") \
                .update({"acknowledged": 1, "acknowledged_at": now}) \
                .eq("id", alert_id) \
                .eq("account_id", account_id) \
                .execute()
            return {"ok": bool(r.data)}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    # ── Brief Generation ────────────────────────────────────────────────

    def generate_brief(self, account_id: str) -> dict:
        """Generate a competitive intelligence brief for an account."""
        self.stats["briefs"] += 1
        competitors = self.list_competitors(account_id)
        if not competitors:
            return {"ok": False, "error": "No competitors registered"}

        now = datetime.now(timezone.utc)
        iso_week = now.strftime("%Y-W%V")  # ISO week number

        # Check if brief already exists for this week
        try:
            db = self.get_db()
            existing = db.table("market_briefs") \
                .select("id") \
                .eq("account_id", account_id) \
                .eq("brief_period", iso_week) \
                .limit(1) \
                .execute()
            if existing.data:
                return {"ok": False, "error": f"Brief already exists for {iso_week}",
                        "existing_id": existing.data[0]["id"]}
        except Exception:
            pass

        # Scrape all active competitors (fresh data)
        changes_detected = 0
        highlights = []
        for comp in competitors:
            if not comp.get("is_active", True):
                continue
            cid = comp.get("id")
            if not cid:
                continue
            result = self.scrape(cid, account_id)
            if result.get("diff_detected"):
                changes_detected += 1
                highlights.append({
                    "competitor": comp["name"],
                    "change": result.get("diff_summary", "Content changed"),
                })

        # Get unread alert count for context
        alerts = self.list_alerts(account_id, unread_only=True, limit=100)

        # Build summary
        niches = set(c.get("niche", "") for c in competitors if c.get("niche"))
        summary = (
            f"Weekly brief for {len(competitors)} competitors across {len(niches)} niche(s). "
            f"{changes_detected} changes detected, {len(alerts)} active alerts."
        )

        # Get scrape stats
        scraped_count = sum(1 for c in competitors if c.get("last_scraped_at"))

        try:
            db = self.get_db()
            brief = db.table("market_briefs").insert({
                "account_id": account_id,
                "brief_period": iso_week,
                "competitor_count": len(competitors),
                "changes_detected": changes_detected,
                "alerts_generated": len(alerts),
                "summary": summary,
                "highlights_json": json.dumps(highlights),
                "created_at": now.isoformat(),
            }).execute()
            brief_id = (brief.data or [{}])[0].get("id")

            # Create a system alert for the new brief (tier-gated: brief alert only for Growth+)
            tier_info = _tier_enabled(account_id, self.guard) if self.guard else TIER_LIMITS["MARKET_EYE_GROWTH"]
            if tier_info.get("alerts", True):
                self._create_alert(
                    account_id=account_id,
                    competitor_id=0,
                    alert_type="brief_ready",
                    severity="info",
                    title=f"Weekly brief ready — W{iso_week.split('-W')[-1]}",
                    description=summary,
                )

            return {
                "ok": True,
                "brief_id": brief_id,
                "period": iso_week,
                "competitors": len(competitors),
                "changes": changes_detected,
                "alerts": len(alerts),
                "summary": summary,
                "highlights": highlights,
                "niches": list(niches),
                "active_scraped": scraped_count,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    def list_briefs(self, account_id: str, limit: int = 12) -> list:
        """List recent briefs for an account."""
        try:
            db = self.get_db()
            r = db.table("market_briefs") \
                .select("*") \
                .eq("account_id", account_id) \
                .order("created_at", desc=True) \
                .limit(min(limit, 52)) \
                .execute()
            return r.data or []
        except Exception:
            return []

    # ── Snapshots / History ─────────────────────────────────────────────

    def snapshots(self, competitor_id: int, account_id: str = "",
                  limit: int = 20) -> list:
        """Return scrape history for a competitor."""
        try:
            db = self.get_db()
            q = db.table("competitor_snapshots") \
                .select("*") \
                .eq("competitor_id", competitor_id) \
                .order("created_at", desc=True) \
                .limit(min(limit, 100))
            if account_id:
                q = q.eq("account_id", account_id)
            r = q.execute()
            return r.data or []
        except Exception:
            return []

    # ── Stats ───────────────────────────────────────────────────────────

    def stats_snapshot(self, account_id: str = "") -> dict:
        """Engine-wide or per-account stats snapshot."""
        if account_id:
            try:
                db = self.get_db()
                comps = db.table("competitor_tracking") \
                    .select("id", count="exact") \
                    .eq("account_id", account_id) \
                    .execute()
                snapshots = db.table("competitor_snapshots") \
                    .select("id", count="exact") \
                    .eq("account_id", account_id) \
                    .execute()
                alerts = db.table("competitor_alerts") \
                    .select("id", count="exact") \
                    .eq("account_id", account_id) \
                    .eq("acknowledged", 0) \
                    .execute()
                return {
                    "account_id": account_id,
                    "competitors": getattr(comps, "count", len(comps.data or [])),
                    "snapshots": getattr(snapshots, "count", len(snapshots.data or [])),
                    "unread_alerts": getattr(alerts, "count", len(alerts.data or [])),
                }
            except Exception:
                pass
        return {
            "engine": dict(self.stats),
            "limits": TIER_LIMITS,
            "tiers": list(TIER_LIMITS.keys()),
        }

    # ── Background Monitoring Loop ──────────────────────────────────────

    async def monitoring_loop(self):
        """Background loop: scrape all eligible competitors every N seconds."""
        await asyncio.sleep(30)  # Let hub finish booting
        log.info("[market_eye] monitoring loop started")
        while not self._stop_loop:
            try:
                # Find all competitors that are due for scraping
                try:
                    db = self.get_db()
                    r = db.table("competitor_tracking") \
                        .select("id, account_id, name, website, last_scraped_at, scrape_interval_h") \
                        .eq("is_active", True) \
                        .execute()
                except Exception:
                    r = type("R", (), {"data": []})()

                now = datetime.now(timezone.utc)
                for comp in (r.data or []):
                    if self._stop_loop:
                        break
                    # Check if due
                    last = comp.get("last_scraped_at")
                    interval_h = comp.get("scrape_interval_h", 24)
                    if last:
                        try:
                            last_dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
                            hours_since = (now - last_dt).total_seconds() / 3600
                            if hours_since < interval_h:
                                continue
                        except (ValueError, TypeError):
                            pass  # scrape if parsing fails

                    # Scrape
                    log.debug(f"[market_eye] monitoring: scraping {comp['name']}")
                    self.scrape(comp["id"], comp.get("account_id", "demo"))
                    await asyncio.sleep(5)  # Polite delay between scrapes

            except Exception as e:
                log.warning(f"[market_eye] monitoring loop error: {e}")
                self.stats["errors"] += 1

            await asyncio.sleep(MONITOR_INTERVAL_SEC)

    def stop_monitoring(self):
        """Signal the monitoring loop to stop."""
        self._stop_loop = True


# ═════════════════════════════════════════════════════════════════════════
# HELPER
# ═════════════════════════════════════════════════════════════════════════

def _tier_enabled(account_id: str, guard: Optional[Callable] = None) -> dict:
    """Check what features are enabled for this account's tier."""
    if not guard:
        return TIER_LIMITS["MARKET_EYE_GROWTH"]
    result = guard(account_id, "market_eye")
    if not isinstance(result, dict) or not result.get("ok"):
        return TIER_LIMITS["MARKET_EYE_STARTER"]
    tier = result.get("tier", "MARKET_EYE_STARTER")
    return TIER_LIMITS.get(tier, TIER_LIMITS["MARKET_EYE_STARTER"])


# ═════════════════════════════════════════════════════════════════════════
# FASTAPI ROUTES
# ═════════════════════════════════════════════════════════════════════════

class MarketEyeRoutes:
    """FastAPI route registration for Market Eye product."""

    def __init__(self, engine: MarketEyeEngine, *, require_auth: Optional[Callable] = None):
        self.engine = engine
        self.require_auth = require_auth

    def register(self, app: FastAPI):
        require_auth = self.require_auth

        @app.get("/api/v6/suite/market-eye/health")
        async def market_eye_health(auth: bool = Depends(require_auth) if require_auth else None):
            return {"status": "operational", "service": "market_eye", "timestamp": datetime.now(timezone.utc).isoformat()}

        # ── Competitor CRUD ─────────────────────────────────────────

        @app.post("/api/v6/suite/market-eye/competitors")
        async def market_eye_add_competitor(body: CompetitorCreate,
                                             auth: bool = Depends(require_auth) if require_auth else None):
            # In a real setup, account_id comes from auth. For now use a default.
            account_id = "demo"  # TODO: extract from auth
            result = self.engine.add_competitor(
                account_id=account_id,
                name=body.name,
                website=body.website,
                niche=body.niche,
                notes=body.notes,
                scrape_interval_h=body.scrape_interval_h,
            )
            if not result.get("ok"):
                raise HTTPException(409 if "already" in (result.get("error") or "") else 400,
                                    result.get("error", "Add failed"))
            return result

        @app.get("/api/v6/suite/market-eye/competitors")
        async def market_eye_list_competitors(niche: str = "",
                                               auth: bool = Depends(require_auth) if require_auth else None):
            account_id = "demo"
            comps = self.engine.list_competitors(account_id, niche=niche)
            return {"competitors": comps, "count": len(comps)}

        @app.get("/api/v6/suite/market-eye/competitors/{competitor_id}")
        async def market_eye_get_competitor(competitor_id: int,
                                             auth: bool = Depends(require_auth) if require_auth else None):
            comp = self.engine.get_competitor(competitor_id)
            if not comp:
                raise HTTPException(404, "Competitor not found")
            return comp

        @app.patch("/api/v6/suite/market-eye/competitors/{competitor_id}")
        async def market_eye_update_competitor(competitor_id: int,
                                                body: CompetitorUpdate,
                                                auth: bool = Depends(require_auth) if require_auth else None):
            result = self.engine.update_competitor(competitor_id, "demo",
                                                    body.model_dump(exclude_none=True))
            if not result.get("ok"):
                raise HTTPException(400, result.get("error", "Update failed"))
            return result

        @app.delete("/api/v6/suite/market-eye/competitors/{competitor_id}")
        async def market_eye_delete_competitor(competitor_id: int,
                                                auth: bool = Depends(require_auth) if require_auth else None):
            result = self.engine.delete_competitor(competitor_id, "demo")
            if not result.get("ok"):
                raise HTTPException(400, result.get("error", "Delete failed"))
            return {"ok": True, "deleted": competitor_id}

        # ── Scraping ────────────────────────────────────────────────

        @app.post("/api/v6/suite/market-eye/scrape/{competitor_id}")
        async def market_eye_scrape(competitor_id: int,
                                     auth: bool = Depends(require_auth) if require_auth else None):
            result = self.engine.scrape(competitor_id)
            if not result.get("ok"):
                raise HTTPException(502, result.get("error", "Scrape failed"))
            return result

        @app.post("/api/v6/suite/market-eye/scrape-all")
        async def market_eye_scrape_all(auth: bool = Depends(require_auth) if require_auth else None):
            """Scrape all active competitors for this account."""
            account_id = "demo"
            comps = self.engine.list_competitors(account_id)
            results = []
            for comp in comps:
                if comp.get("is_active", True):
                    cid = comp.get("id")
                    if cid:
                        result = self.engine.scrape(cid, account_id)
                        results.append(result)
            return {
                "scraped": len(results),
                "errors": sum(1 for r in results if not r.get("ok")),
                "results": results,
            }

        # ── Snapshots / History ──────────────────────────────────────

        @app.get("/api/v6/suite/market-eye/snapshots/{competitor_id}")
        async def market_eye_snapshots(competitor_id: int, limit: int = 20,
                                        auth: bool = Depends(require_auth) if require_auth else None):
            return {
                "competitor_id": competitor_id,
                "snapshots": self.engine.snapshots(competitor_id, limit=limit),
            }

        # ── Alerts ───────────────────────────────────────────────────

        @app.get("/api/v6/suite/market-eye/alerts")
        async def market_eye_alerts(unread_only: bool = False, limit: int = 50,
                                     auth: bool = Depends(require_auth) if require_auth else None):
            account_id = "demo"
            return {
                "alerts": self.engine.list_alerts(account_id, unread_only=unread_only, limit=limit),
            }

        @app.post("/api/v6/suite/market-eye/alerts/{alert_id}/acknowledge")
        async def market_eye_acknowledge_alert(alert_id: int,
                                                auth: bool = Depends(require_auth) if require_auth else None):
            result = self.engine.acknowledge_alert(alert_id, "demo")
            if not result.get("ok"):
                raise HTTPException(404, "Alert not found")
            return result

        # ── Briefs ──────────────────────────────────────────────────

        @app.post("/api/v6/suite/market-eye/brief")
        async def market_eye_generate_brief(auth: bool = Depends(require_auth) if require_auth else None):
            account_id = "demo"
            result = self.engine.generate_brief(account_id)
            if not result.get("ok") and "already" not in (result.get("error") or ""):
                raise HTTPException(400, result.get("error", "Brief generation failed"))
            return result

        @app.get("/api/v6/suite/market-eye/briefs")
        async def market_eye_list_briefs(limit: int = 12,
                                          auth: bool = Depends(require_auth) if require_auth else None):
            account_id = "demo"
            return {"briefs": self.engine.list_briefs(account_id, limit=limit)}

        # ── Stats ───────────────────────────────────────────────────

        @app.get("/api/v6/suite/market-eye/stats")
        async def market_eye_stats(auth: bool = Depends(require_auth) if require_auth else None):
            return self.engine.stats_snapshot()

        log.info("[market_eye] Routes registered · /api/v6/suite/market-eye/*")
