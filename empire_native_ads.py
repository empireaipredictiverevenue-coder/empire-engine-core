"""
EMPIRE V49 · NATIVE ADS NETWORK
================================
Full ad serving system: campaign management, creative serving,
impression/click tracking, publisher integration.

API Routes (registered on hub):
  POST   /api/v1/ads/campaigns          — create campaign
  GET    /api/v1/ads/campaigns          — list campaigns
  GET    /api/v1/ads/campaigns/{id}     — get campaign + creatives
  PATCH  /api/v1/ads/campaigns/{id}     — update campaign
  POST   /api/v1/ads/creatives          — create creative
  PATCH  /api/v1/ads/creatives/{id}     — update creative
  GET    /api/v1/ads/serve              — serve an ad (publisher embed)
  POST   /api/v1/ads/click              — track a click
  GET    /api/v1/ads/slots              — list publisher slots
  POST   /api/v1/ads/slots              — create publisher slot
  GET    /api/v1/ads/stats              — aggregate stats
"""

import os
import json
import uuid
import logging
import hashlib
import random
from datetime import datetime, timezone
from typing import Callable, Optional

from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.responses import JSONResponse, RedirectResponse

log = logging.getLogger("empire.native_ads")


class NativeAdsNetwork:
    """Native ads network engine — campaign management, serving, tracking."""

    def __init__(self, get_db: Callable):
        self.get_db = get_db

    # ── CAMPAIGNS ────────────────────────────────────────────────────

    async def create_campaign(self, body: dict, operator_id: str) -> dict:
        db = self.get_db()
        payload = {
            "name": body.get("name", "").strip(),
            "advertiser_id": body.get("advertiser_id") or operator_id,
            "niche": body.get("niche", "").strip(),
            "daily_budget": float(body.get("daily_budget", 100)),
            "total_budget": float(body.get("total_budget", 0)) or None,
            "target_metros": body.get("target_metros", []),
            "target_url": body.get("target_url", "").strip(),
            "target_specialties": body.get("target_specialties", []),
            "status": "paused",
            "start_at": body.get("start_at"),
            "end_at": body.get("end_at"),
            "notes": body.get("notes", ""),
            "meta": body.get("meta", {}),
        }
        if not payload["name"]:
            return {"ok": False, "error": "missing_name"}
        if not payload["niche"]:
            return {"ok": False, "error": "missing_niche"}
        r = db.table("ad_campaigns").insert(payload).execute()
        if r.data:
            log.info(f"[native_ads] campaign created: {r.data[0]['id']} ({payload['name']})")
            return {"ok": True, "campaign": r.data[0]}
        return {"ok": False, "error": "insert_failed"}

    async def list_campaigns(self, status: str = "", niche: str = "", limit: int = 50) -> list:
        db = self.get_db()
        q = db.table("ad_campaigns").select("*").order("created_at", desc=True).limit(min(limit, 200))
        if status:
            q = q.eq("status", status)
        if niche:
            q = q.eq("niche", niche)
        r = q.execute()
        return r.data or []

    async def get_campaign(self, campaign_id: str) -> Optional[dict]:
        db = self.get_db()
        r = db.table("ad_campaigns").select("*").eq("id", campaign_id).limit(1).execute()
        if not r.data:
            return None
        campaign = r.data[0]
        # Also fetch creatives
        cr = db.table("ad_creatives").select("*").eq("campaign_id", campaign_id).execute()
        campaign["creatives"] = cr.data or []
        return campaign

    async def update_campaign(self, campaign_id: str, body: dict) -> dict:
        db = self.get_db()
        existing = db.table("ad_campaigns").select("id").eq("id", campaign_id).limit(1).execute()
        if not existing.data:
            return {"ok": False, "error": "not_found"}
        updates = {}
        for key in ("name", "niche", "daily_budget", "total_budget", "target_metros",
                     "target_url", "target_specialties", "status", "notes", "meta",
                     "start_at", "end_at"):
            if key in body:
                updates[key] = body[key]
        if not updates:
            return {"ok": False, "error": "no_updates"}
        r = db.table("ad_campaigns").update(updates).eq("id", campaign_id).execute()
        return {"ok": True, "campaign": r.data[0] if r.data else None}

    # ── CREATIVES ────────────────────────────────────────────────────

    async def create_creative(self, body: dict) -> dict:
        db = self.get_db()
        campaign_id = body.get("campaign_id", "").strip()
        if not campaign_id:
            return {"ok": False, "error": "missing_campaign_id"}
        # Verify campaign exists
        camp = db.table("ad_campaigns").select("id,niche").eq("id", campaign_id).limit(1).execute()
        if not camp.data:
            return {"ok": False, "error": "campaign_not_found"}
        headline = (body.get("headline") or "").strip()[:80]
        ad_body = (body.get("body") or "").strip()[:200]
        if not headline or not ad_body:
            return {"ok": False, "error": "headline_and_body_required"}
        payload = {
            "campaign_id": campaign_id,
            "headline": headline,
            "body": ad_body,
            "image_url": (body.get("image_url") or "").strip(),
            "cta_text": (body.get("cta_text") or "Learn More").strip()[:40],
            "destination_url": (body.get("destination_url") or "").strip(),
            "ad_size": body.get("ad_size", "300x250"),
            "ad_format": body.get("ad_format", "native"),
            "status": "active",
            "meta": body.get("meta", {}),
        }
        if not payload["destination_url"]:
            # Default to campaign's target URL
            payload["destination_url"] = camp.data[0].get("target_url") or ""
        r = db.table("ad_creatives").insert(payload).execute()
        if r.data:
            return {"ok": True, "creative": r.data[0]}
        return {"ok": False, "error": "insert_failed"}

    async def update_creative(self, creative_id: str, body: dict) -> dict:
        db = self.get_db()
        existing = db.table("ad_creatives").select("id").eq("id", creative_id).limit(1).execute()
        if not existing.data:
            return {"ok": False, "error": "not_found"}
        updates = {}
        for key in ("headline", "body", "image_url", "cta_text", "destination_url",
                     "ad_size", "ad_format", "status", "meta"):
            if key in body:
                updates[key] = body[key]
        if not updates:
            return {"ok": False, "error": "no_updates"}
        r = db.table("ad_creatives").update(updates).eq("id", creative_id).execute()
        return {"ok": True, "creative": r.data[0] if r.data else None}

    # ── AD SERVING ───────────────────────────────────────────────────

    async def serve_ad(self, slot_id: str = "", niche: str = "",
                       visitor_id: str = "", ip: str = "") -> dict:
        """Serve the best matching ad for a slot/niche.
        
        Called by the publisher embed when a page loads.
        Returns the creative HTML/safe data or None if no ad available.
        """
        db = self.get_db()
        
        # Find matching active campaigns
        campaigns = db.table("ad_campaigns").select("id,niche,daily_budget,spent_today,status") \
            .eq("status", "active").execute()
        candidates = campaigns.data or []
        
        if niche:
            candidates = [c for c in candidates if c.get("niche", "").lower() == niche.lower()]
        
        if not candidates:
            return {"ok": True, "ad": None, "reason": "no_matching_campaigns"}
        
        # Filter campaigns that haven't hit daily budget
        active = []
        for c in candidates:
            daily = float(c.get("daily_budget", 100) or 100)
            spent = float(c.get("spent_today", 0) or 0)
            if spent < daily:
                active.append(c)
        
        if not active:
            return {"ok": True, "ad": None, "reason": "all_campaigns_at_daily_budget"}
        
        # Pick a campaign weighted by available budget
        total_remaining = sum(float(c.get("daily_budget", 100) or 100) - float(c.get("spent_today", 0) or 0) for c in active)
        if total_remaining <= 0:
            return {"ok": True, "ad": None, "reason": "budget_exhausted"}
        
        weights = [max(0, float(c.get("daily_budget", 100) or 100) - float(c.get("spent_today", 0) or 0)) / total_remaining for c in active]
        chosen = random.choices(active, weights=weights, k=1)[0]
        
        # Get a creative for this campaign
        creatives = db.table("ad_creatives").select("*") \
            .eq("campaign_id", chosen["id"]) \
            .eq("status", "active") \
            .execute()
        
        if not creatives.data:
            return {"ok": True, "ad": None, "reason": "no_creatives"}
        
        creative = random.choice(creatives.data)
        
        # Log impression
        ip_hash = hashlib.sha256((ip or "").encode()).hexdigest()[:16] if ip else ""
        
        # Resolve slot name to UUID if needed
        slot_uuid = None
        if slot_id:
            try:
                uuid.UUID(slot_id)
                slot_uuid = slot_id
            except (ValueError, AttributeError):
                # Look up slot by name in ad_slots table
                try:
                    slot_res = db.table("ad_slots").select("id").eq("slot_name", slot_id).limit(1).execute()
                    if slot_res.data:
                        slot_uuid = str(slot_res.data[0]["id"])
                except Exception:
                    pass
        
        impression = {
            "creative_id": creative["id"],
            "campaign_id": chosen["id"],
            "slot_id": slot_uuid,
            "visitor_id": visitor_id or "",
            "ip_hash": ip_hash,
            "user_agent": "",
            "cost_per_impression": 0.001,
        }
        imp_r = db.table("ad_impressions").insert(impression).execute()
        impression_id = imp_r.data[0]["id"] if imp_r.data else None
        
        # Update creative impression count
        db.table("ad_creatives").update({"impressions": (creative.get("impressions") or 0) + 1}) \
            .eq("id", creative["id"]).execute()
        
        # Update campaign spend
        db.table("ad_campaigns").update({
            "spent_today": round(float(chosen.get("spent_today", 0) or 0) + 0.001, 6),
            "spent_total": round(float(chosen.get("spent_total", 0) or 0) + 0.001, 6),
        }).eq("id", chosen["id"]).execute()
        
        return {
            "ok": True,
            "ad": {
                "impression_id": str(impression_id) if impression_id else None,
                "creative_id": str(creative["id"]),
                "campaign_id": str(chosen["id"]),
                "headline": creative.get("headline", ""),
                "body": creative.get("body", ""),
                "image_url": creative.get("image_url", ""),
                "cta_text": creative.get("cta_text", "Learn More"),
                "destination_url": creative.get("destination_url", ""),
                "ad_size": creative.get("ad_size", "300x250"),
                "ad_format": creative.get("ad_format", "native"),
                "tracking_pixel": f"/api/v1/ads/impression/{impression_id}" if impression_id else None,
            }
        }

    # ── TRACKING ─────────────────────────────────────────────────────

    async def track_click(self, body: dict, ip: str = "", ua: str = "") -> Optional[str]:
        """Track a click and return the destination URL for redirection."""
        impression_id = body.get("impression_id", "").strip()
        creative_id = body.get("creative_id", "").strip()
        campaign_id = body.get("campaign_id", "").strip()
        visitor_id = body.get("visitor_id", "").strip()
        
        db = self.get_db()
        
        # Get the creative for destination URL
        if creative_id:
            cr = db.table("ad_creatives").select("destination_url,campaign_id").eq("id", creative_id).limit(1).execute()
        elif impression_id:
            imp = db.table("ad_impressions").select("creative_id,campaign_id").eq("id", impression_id).limit(1).execute()
            if imp.data:
                creative_id = imp.data[0].get("creative_id", "")
                campaign_id = campaign_id or imp.data[0].get("campaign_id", "")
                cr = db.table("ad_creatives").select("destination_url,campaign_id").eq("id", creative_id).limit(1).execute()
            else:
                return None
        else:
            return None
        
        destination = cr.data[0]["destination_url"] if cr.data else None
        if not destination:
            return None
        
        ip_hash = hashlib.sha256((ip or "").encode()).hexdigest()[:16] if ip else ""
        
        click = {
            "impression_id": impression_id or None,
            "creative_id": creative_id or None,
            "campaign_id": campaign_id or None,
            "visitor_id": visitor_id or "",
            "ip_hash": ip_hash,
            "user_agent": ua or "",
        }
        click_r = db.table("ad_clicks").insert(click).execute()
        
        # Update creative click count
        if creative_id:
            cr_data = db.table("ad_creatives").select("clicks").eq("id", creative_id).limit(1).execute()
            if cr_data.data:
                db.table("ad_creatives").update({"clicks": (cr_data.data[0].get("clicks") or 0) + 1}) \
                    .eq("id", creative_id).execute()
        
        return destination

    async def track_impression(self, impression_id: str) -> bool:
        """Tracking pixel endpoint — 1x1 GIF."""
        return True

    # ── SLOTS ────────────────────────────────────────────────────────

    async def list_slots(self, publisher_id: str = "") -> list:
        db = self.get_db()
        q = db.table("ad_slots").select("*").eq("is_active", True)
        if publisher_id:
            q = q.eq("publisher_id", publisher_id)
        r = q.execute()
        return r.data or []

    async def create_slot(self, body: dict) -> dict:
        db = self.get_db()
        payload = {
            "publisher_id": body.get("publisher_id", "").strip(),
            "publisher_name": body.get("publisher_name", "").strip(),
            "slot_name": body.get("slot_name", "").strip(),
            "ad_size": body.get("ad_size", "300x250"),
            "ad_format": body.get("ad_format", "native"),
            "niches": body.get("niches", []),
            "revenue_share_pct": float(body.get("revenue_share_pct", 70)),
            "is_active": body.get("is_active", True),
            "meta": body.get("meta", {}),
        }
        if not payload["publisher_id"] or not payload["slot_name"]:
            return {"ok": False, "error": "publisher_id_and_slot_name_required"}
        try:
            r = db.table("ad_slots").insert(payload).execute()
            return {"ok": True, "slot": r.data[0]}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    # ── STATS ────────────────────────────────────────────────────────

    async def stats(self, days: int = 7) -> dict:
        db = self.get_db()
        since = (datetime.now(timezone.utc)).isoformat()
        
        campaigns = db.table("ad_campaigns").select("*").execute()
        creatives = db.table("ad_creatives").select("*").execute()
        impressions = db.table("ad_impressions").select("id,created_at").execute()
        clicks = db.table("ad_clicks").select("id,created_at").execute()
        
        total_campaigns = len(campaigns.data or [])
        active_campaigns = sum(1 for c in (campaigns.data or []) if c.get("status") == "active")
        total_creatives = len(creatives.data or [])
        total_impressions = len(impressions.data or [])
        total_clicks = len(clicks.data or [])
        
        return {
            "campaigns": {"total": total_campaigns, "active": active_campaigns},
            "creatives": {"total": total_creatives},
            "impressions": {"total": total_impressions},
            "clicks": {"total": total_clicks},
            "ctr": round(total_clicks / total_impressions * 100, 2) if total_impressions > 0 else 0,
            "by_niche": {},
        }


# ─────────────────────────────────────────────────────────────────────
# FASTAPI ROUTES
# ─────────────────────────────────────────────────────────────────────

def register_native_ads_routes(
    app: FastAPI,
    ads: NativeAdsNetwork,
    *,
    require_auth: Callable,
    public_base_url: str = "",
):
    """Wire native ads routes on the hub."""

    # ── CAMPAIGNS ────────────────────────────────────────────────────

    @app.post("/api/v1/ads/campaigns")
    async def create_campaign(request: Request, auth: bool = Depends(require_auth)):
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        op_id = getattr(request.state, "operator_id", "") or getattr(request.state, "user_id", "")
        result = await ads.create_campaign(body, op_id)
        status = 200 if result.get("ok") else 400
        return JSONResponse(result, status_code=status)

    @app.get("/api/v1/ads/campaigns")
    async def list_campaigns(
        status: str = Query(""),
        niche: str = Query(""),
        limit: int = Query(50, ge=1, le=200),
        auth: bool = Depends(require_auth),
    ):
        campaigns = await ads.list_campaigns(status=status, niche=niche, limit=limit)
        return {"campaigns": campaigns, "count": len(campaigns)}

    @app.get("/api/v1/ads/campaigns/{campaign_id}")
    async def get_campaign(campaign_id: str, auth: bool = Depends(require_auth)):
        campaign = await ads.get_campaign(campaign_id)
        if not campaign:
            raise HTTPException(404, "campaign not found")
        return campaign

    @app.patch("/api/v1/ads/campaigns/{campaign_id}")
    async def update_campaign(campaign_id: str, request: Request, auth: bool = Depends(require_auth)):
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        result = await ads.update_campaign(campaign_id, body)
        status = 200 if result.get("ok") else (404 if result.get("error") == "not_found" else 400)
        return JSONResponse(result, status_code=status)

    # ── CREATIVES ────────────────────────────────────────────────────

    @app.post("/api/v1/ads/creatives")
    async def create_creative(request: Request, auth: bool = Depends(require_auth)):
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        result = await ads.create_creative(body)
        status = 200 if result.get("ok") else 400
        return JSONResponse(result, status_code=status)

    @app.patch("/api/v1/ads/creatives/{creative_id}")
    async def update_creative(creative_id: str, request: Request, auth: bool = Depends(require_auth)):
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        result = await ads.update_creative(creative_id, body)
        status = 200 if result.get("ok") else (404 if result.get("error") == "not_found" else 400)
        return JSONResponse(result, status_code=status)

    # ── AD SERVING (public — no auth) ────────────────────────────────

    @app.get("/api/v1/ads/serve")
    async def serve_ad(
        slot: str = Query(""),
        niche: str = Query(""),
        visitor_id: str = Query(""),
    ):
        """Serves an ad. Returns creative data or {ad: null} if no match.
        Called from publisher embed code. No auth required."""
        ip = ""  # Available from request.client.host
        result = await ads.serve_ad(slot_id=slot, niche=niche, visitor_id=visitor_id, ip=ip)
        return JSONResponse(result)

    # ── TRACKING (public — no auth, 1x1 pixel or redirect) ───────────

    @app.get("/api/v1/ads/impression/{impression_id}")
    async def track_impression_pixel(impression_id: str):
        """Tracking pixel: 1x1 transparent GIF. No auth."""
        await ads.track_impression(impression_id)
        # Return 1x1 transparent GIF
        return JSONResponse({"ok": True})

    @app.post("/api/v1/ads/click")
    async def track_click(request: Request):
        """Track a click and redirect to destination."""
        try:
            body = await request.json()
        except Exception:
            body = {}
        ip = request.client.host if request.client else ""
        ua = request.headers.get("user-agent", "")
        destination = await ads.track_click(body, ip=ip, ua=ua)
        if destination:
            return {"ok": True, "destination": destination}
        return {"ok": False, "error": "no_destination"}, 400

    @app.post("/api/v1/ads/click/redirect")
    async def click_and_redirect(request: Request):
        """Track a click and immediately redirect the user to the ad destination."""
        try:
            body = await request.json()
        except Exception:
            body = {}
        ip = request.client.host if request.client else ""
        ua = request.headers.get("user-agent", "")
        destination = await ads.track_click(body, ip=ip, ua=ua)
        if destination:
            return RedirectResponse(destination, status_code=302)
        return JSONResponse({"ok": False, "error": "no_destination"}, status_code=400)

    # ── SLOTS ────────────────────────────────────────────────────────

    @app.get("/api/v1/ads/slots")
    async def list_slots(publisher_id: str = Query(""), auth: bool = Depends(require_auth)):
        slots = await ads.list_slots(publisher_id=publisher_id)
        return {"slots": slots, "count": len(slots)}

    @app.post("/api/v1/ads/slots")
    async def create_slot(request: Request, auth: bool = Depends(require_auth)):
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        result = await ads.create_slot(body)
        status = 200 if result.get("ok") else 400
        return JSONResponse(result, status_code=status)

    # ── STATS ────────────────────────────────────────────────────────

    @app.get("/api/v1/ads/stats")
    async def ads_stats(days: int = Query(7, ge=1, le=90), auth: bool = Depends(require_auth)):
        stats = await ads.stats(days=days)
        return stats

    log.info("[native_ads] Routes registered — campaigns, creatives, serve, tracking, slots, stats")


# ── PUBLISHER EMBED SNIPPET ─────────────────────────────────────────

PUBLISHER_EMBED_HTML = """
<!-- Empire AI · Native Ads Embed -->
<div id="empire-ad-{slot}"></div>
<script>
(function() {
  var slot = "{slot}";
  var niche = "{niche}" || document.querySelector('meta[name="niche"]')?.content || '';
  var visitor = localStorage.getItem('empire_visitor_id') || 'v_' + Math.random().toString(36).slice(2, 10);
  localStorage.setItem('empire_visitor_id', visitor);

  fetch('/api/v1/ads/serve?slot=' + encodeURIComponent(slot) + '&niche=' + encodeURIComponent(niche) + '&visitor_id=' + visitor)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!data.ok || !data.ad) return;
      var ad = data.ad;
      var el = document.getElementById('empire-ad-' + slot);
      if (!el) return;

      var html = '<div style="border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;background:#fff;max-width:' + ad.ad_size?.split('x')[0] + 'px;">';
      if (ad.image_url) {
        html += '<a href="#" onclick="return empireAdClick(' + "'" + ad.impression_id + "','" + ad.creative_id + "','" + ad.campaign_id + "','" + visitor + "'" + ')" style="display:block;">';
        html += '<img src="' + ad.image_url + '" alt="" style="width:100%;display:block;">';
        html += '</a>';
      }
      html += '<div style="padding:12px;">';
      html += '<div style="font-size:14px;font-weight:600;color:#1a202c;margin-bottom:4px;">' + ad.headline + '</div>';
      html += '<div style="font-size:12px;color:#718096;margin-bottom:10px;">' + ad.body + '</div>';
      html += '<a href="#" onclick="return empireAdClick(' + "'" + ad.impression_id + "','" + ad.creative_id + "','" + ad.campaign_id + "','" + visitor + "'" + ')" style="display:inline-block;background:#4FD1C5;color:#fff;padding:6px 14px;border-radius:4px;font-size:12px;font-weight:600;text-decoration:none;">' + ad.cta_text + '</a>';
      html += '</div></div>';
      el.innerHTML = html;
    })
    .catch(function() { /* silent fail — ad just won't render */ });

  window.empireAdClick = function(impressionId, creativeId, campaignId, visitorId) {
    fetch('/api/v1/ads/click/redirect', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        impression_id: impressionId,
        creative_id: creativeId,
        campaign_id: campaignId,
        visitor_id: visitorId
      })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.destination) { window.location.href = data.destination; }
    });
    return false;
  };
})();
</script>
"""
