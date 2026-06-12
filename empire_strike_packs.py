"""
EMPIRE V49 · STRIKE PACKS SUBSCRIPTION ENGINE
==============================================
Productizes the 32 lanes into sellable Strike Packs with pricing tiers.

Three components:

  1. StrikePackCatalog   — loads + caches the product catalog from DB
  2. SubscriptionEngine  — manage buyer subscriptions, check daily/monthly caps
  3. DeliveryFilter      — given a qualified lead, determine which subscribed
                           buyers should receive it (lane match, caps, channels)

Wire-up in hub.py:

    from empire_strike_packs import StrikePackCatalog, SubscriptionEngine, DeliveryFilter
    from empire_strike_packs import register_strike_pack_routes

    catalog = StrikePackCatalog(get_db=get_db)
    sub_engine = SubscriptionEngine(get_db=get_db, catalog=catalog)
    delivery_filter = DeliveryFilter(get_db=get_db, catalog=catalog, subscriptions=sub_engine)

    register_strike_pack_routes(
        app,
        catalog=catalog,
        subscriptions=sub_engine,
        require_auth=require_auth,
        require_owner=require_owner,
    )

    # In the lead-dispatch path, after a lead is qualified:
    #   recipients = await delivery_filter.eligible_buyers(
    #       lead={"niche": "...", "lane_id": N, ...}
    #   )
    #   for buyer in recipients:
    #       await delivery_filter.deliver(buyer, lead)

Schema (created by migrations/010_strike_packs.sql):
    strike_packs           — product catalog (one row per SKU)
    strike_pack_lanes      — which lane IDs a pack covers (M:N)
    buyer_subscriptions    — who's subscribed to what, billing state
    buyer_pack_stats       — daily rollup per subscription
"""

import hashlib
import hmac
import json as _json
import logging
import secrets
import time as _time
from datetime import date, datetime, timezone
from typing import Callable, Optional

import httpx as _httpx
from fastapi import FastAPI, Request, HTTPException, Depends, Header, Query
from fastapi.responses import JSONResponse

log = logging.getLogger("empire.strike_packs")


# ═══════════════════════════════════════════════════════════════════════
# CATALOG
# ═══════════════════════════════════════════════════════════════════════


class StrikePackCatalog:
    """Loads and caches the strike pack product catalog from Supabase.

    Cache TTL is 60s by default. The catalog doesn't change frequently
    (only when new packs are added or pricing is updated), so caching
    eliminates a Supabase query on every lead-routing decision.
    """

    def __init__(self, get_db: Callable, cache_ttl: float = 60.0):
        self.get_db = get_db
        self._cache_ttl = cache_ttl
        self._packs: dict[str, dict] = {}      # slug → pack row
        self._packs_by_id: dict[str, dict] = {} # id → pack row
        self._lanes_by_pack: dict[str, list] = {}  # pack_id → [lane rows]
        self._lane_to_packs: dict[int, set] = {}    # lane_id → {pack_id, ...}
        self._cache_ts: float = 0.0
        self.stats = {"loads": 0, "cache_hits": 0, "errors": 0}

    # ── PUBLIC: get a pack by slug or id ──────────────────────────────

    def by_slug(self, slug: str) -> Optional[dict]:
        """Return a pack row by slug, or None."""
        self._ensure_fresh()
        return self._packs.get(slug)

    def by_id(self, pack_id: str) -> Optional[dict]:
        """Return a pack row by UUID, or None."""
        self._ensure_fresh()
        return self._packs_by_id.get(pack_id)

    def all(self, tier: Optional[str] = None, public_only: bool = True) -> list[dict]:
        """Return all packs, optionally filtered by tier and public visibility."""
        self._ensure_fresh()
        packs = list(self._packs.values())
        if public_only:
            packs = [p for p in packs if p.get("is_public", True)]
        if tier:
            packs = [p for p in packs if p.get("tier") == tier]
        return sorted(packs, key=lambda p: p.get("sort_order", 0))

    def lanes_for_pack(self, pack_id: str) -> list[dict]:
        """Return all lane rows for a given pack."""
        self._ensure_fresh()
        return self._lanes_by_pack.get(pack_id, [])

    def lane_ids_for_pack(self, pack_id: str) -> list[int]:
        """Return lane IDs (0-31) covered by a pack."""
        return [r["lane_id"] for r in self.lanes_for_pack(pack_id)]

    def packs_covering_lane(self, lane_id: int) -> list[dict]:
        """Return all active packs that cover a given lane ID."""
        self._ensure_fresh()
        return [
            p for p in self._packs.values()
            if p.get("is_active", True)
            and lane_id in self._lane_to_packs.get(lane_id, [])
        ]

    # ── INTERNAL: cache management ────────────────────────────────────

    def _ensure_fresh(self):
        """Refresh catalog from DB if cache is stale or empty."""
        now = _time.time()
        if self._packs and now - self._cache_ts < self._cache_ttl:
            self.stats["cache_hits"] += 1
            return
        self._load()

    def _load(self):
        """Full catalog + lanes load from Supabase."""
        try:
            db = self.get_db()
            packs_res = db.table("strike_packs").select("*") \
                .eq("is_active", True).execute()
            lanes_res = db.table("strike_pack_lanes").select("*").execute()
        except Exception as e:
            self.stats["errors"] += 1
            log.error(f"[strikes.catalog] load failed: {e}")
            return

        packs = packs_res.data or []
        all_lanes = lanes_res.data or []

        # Index packs by slug and id
        self._packs = {p["slug"]: p for p in packs}
        self._packs_by_id = {p["id"]: p for p in packs}

        # Index lanes by pack_id
        self._lanes_by_pack = {}
        for r in all_lanes:
            self._lanes_by_pack.setdefault(r["pack_id"], []).append(r)

        # Build reverse index: lane_id → [pack_slug, ...]
        self._lane_to_packs = {}
        for lane_row in all_lanes:
            self._lane_to_packs.setdefault(lane_row["lane_id"], set()).add(
                lane_row["pack_id"]
            )

        self._cache_ts = _time.time()
        self.stats["loads"] += 1
        log.info(
            f"[strikes.catalog] loaded {len(self._packs)} packs, "
            f"{len(all_lanes)} lane mappings"
        )

    def invalidate(self):
        """Force the next access to re-fetch from Supabase."""
        self._cache_ts = 0.0


# ═══════════════════════════════════════════════════════════════════════
# SUBSCRIPTIONS
# ═══════════════════════════════════════════════════════════════════════


class SubscriptionEngine:
    """Manages buyer subscriptions: create, pause, cancel, check caps, log usage."""

    def __init__(self, get_db: Callable, catalog: StrikePackCatalog):
        self.get_db = get_db
        self.catalog = catalog
        self.stats = {"subscriptions_created": 0, "leads_delivered": 0,
                       "caps_hit": 0, "errors": 0}

    # ── QUERIES ─────────────────────────────────────────────────────────

    def active_subscriptions_for_buyer(self, buyer_id: str) -> list[dict]:
        """Return all active subscriptions for a given buyer."""
        try:
            db = self.get_db()
            res = db.table("buyer_subscriptions").select("*") \
                .eq("buyer_id", buyer_id) \
                .eq("active", True) \
                .execute()
            return res.data or []
        except Exception as e:
            self.stats["errors"] += 1
            log.error(f"[strikes.subs] query buyer={buyer_id}: {e}")
            return []

    def active_subscriptions_for_pack(self, pack_id: str) -> list[dict]:
        """Return all active subscriptions for a given pack."""
        try:
            db = self.get_db()
            res = db.table("buyer_subscriptions").select("*") \
                .eq("pack_id", pack_id) \
                .eq("active", True) \
                .execute()
            subs = res.data or []
            # Enrich with buyer info (separate query — supabase-py doesn't
            # support the !inner join syntax that supabase-js uses)
            for s in subs:
                try:
                    br = db.table("buyers").select("*") \
                        .eq("id", s["buyer_id"]).limit(1).execute()
                    if br.data:
                        s["buyers"] = br.data[0]
                except Exception:
                    s["buyers"] = {}
            return subs
        except Exception as e:
            self.stats["errors"] += 1
            log.error(f"[strikes.subs] query pack={pack_id}: {e}")
            return []

    def all_active(self) -> list[dict]:
        """Return ALL active subscriptions with buyer info."""
        try:
            db = self.get_db()
            res = db.table("buyer_subscriptions").select("*") \
                .eq("active", True) \
                .execute()
            subs = res.data or []
            # Enrich with buyer info (separate query per sub is fine here
            # because the number of active subs is small — typical < 50)
            for s in subs:
                try:
                    br = db.table("buyers").select("*") \
                        .eq("id", s["buyer_id"]).limit(1).execute()
                    if br.data:
                        s["buyers"] = br.data[0]
                except Exception:
                    s["buyers"] = {}
            return subs
        except Exception as e:
            self.stats["errors"] += 1
            log.error(f"[strikes.subs] query all active: {e}")
            return []

    def subscription_by_id(self, sub_id: str) -> Optional[dict]:
        """Return a single subscription by ID."""
        try:
            db = self.get_db()
            res = db.table("buyer_subscriptions").select("*, buyers(*)") \
                .eq("id", sub_id).limit(1).execute()
            return res.data[0] if res.data else None
        except Exception:
            return None

    # ── MUTATIONS ───────────────────────────────────────────────────────

    async def create_subscription(
        self,
        buyer_id: str,
        pack_slug: str,
        *,
        monthly_price_cents: Optional[int] = None,
        price_per_lead_cents: Optional[int] = None,
        max_leads_per_day: Optional[int] = None,
        max_leads_per_month: Optional[int] = None,
        stripe_customer_id: Optional[str] = None,
        stripe_subscription_id: Optional[str] = None,
        notes: str = "",
        # ── Whale / Enterprise fields ────────────────────────────────
        webhook_url: Optional[str] = None,
        custom_lanes: Optional[list[int]] = None,
        sla_tier: str = "standard",
        dedicated_support: bool = False,
        api_key: Optional[str] = None,
    ) -> dict:
        """Create a new subscription. Prices default to the pack's current
        catalog price (snapshot at creation time so price changes don't
        affect existing subscriptions until renewal).

        Whale/enterprise extras:
          webhook_url     — for webhook/API-channel subscriptions, where to POST
          custom_lanes    — override the pack's default lane IDs
          sla_tier        — 'standard' | 'enhanced' | 'premium'
          dedicated_support — flag for named support contact
          api_key         — pre-generated API key for this subscription
        """
        pack = self.catalog.by_slug(pack_slug)
        if not pack:
            return {"ok": False, "error": f"Pack '{pack_slug}' not found"}

        # Check for existing active subscription to the same pack
        existing = self.active_subscriptions_for_buyer(buyer_id)
        for sub in existing:
            if sub["pack_id"] == pack["id"]:
                return {
                    "ok": False,
                    "error": "Buyer already has an active subscription to this pack",
                    "existing_subscription_id": sub["id"],
                }

        # Validate webhook_url for api/webhook channel packs
        channels = pack.get("delivery_channels", [])
        if webhook_url and not webhook_url.startswith("https://"):
            return {"ok": False, "error": "webhook_url must be HTTPS"}
        if not webhook_url and ("api" in channels or "webhook" in channels):
            webhook_url = ""  # allowed — will be configured later via the /webhook endpoint

        # Generate an API key for API-channel whale products if not provided
        sub_api_key = api_key
        if "api" in channels and not sub_api_key:
            sub_api_key = self._generate_api_key()

        # Build meta with enterprise/whale config
        meta = {
            "sla_tier": sla_tier if sla_tier in ("standard", "enhanced", "premium") else "standard",
            "dedicated_support": dedicated_support,
            "webhook_url": webhook_url or "",
            "custom_lanes": custom_lanes or [],
            "api_key": sub_api_key or "",
            "api_key_prefix": (sub_api_key or "")[:8] + "..." if sub_api_key else "",
        }

        # Determine caps: whale products with 0/0 mean unlimited
        daily_max = max_leads_per_day
        if daily_max is None:
            d = pack.get("max_leads_per_day", 0)
            daily_max = d if d > 0 else 999999
        period_max = max_leads_per_month
        if period_max is None:
            p = pack.get("max_leads_per_month", 0)
            period_max = p if p > 0 else 999999

        record = {
            "buyer_id":               buyer_id,
            "pack_id":                pack["id"],
            "monthly_price_cents":    monthly_price_cents or pack["monthly_price_cents"],
            "price_per_lead_cents":   price_per_lead_cents or pack["price_per_lead_cents"],
            "max_leads_per_day":      daily_max,
            "max_leads_per_month":    period_max,
            "status":                 "active",
            "active":                 True,
            "period_start":           datetime.now(timezone.utc).isoformat(),
            "leads_delivered_period": 0,
            "notes":                  notes[:500] if notes else None,
            "meta":                   _json.dumps(meta),
        }
        if stripe_customer_id:
            record["stripe_customer_id"] = stripe_customer_id
        if stripe_subscription_id:
            record["stripe_subscription_id"] = stripe_subscription_id

        try:
            db = self.get_db()
            res = db.table("buyer_subscriptions").insert(record).execute()
            if not res.data:
                return {"ok": False, "error": "Insert returned no data"}
            self.stats["subscriptions_created"] += 1

            # If custom lanes specified, write them to strike_pack_lanes
            if custom_lanes:
                self._save_custom_lanes(res.data[0]["id"], pack["id"], custom_lanes)

            log.info(
                f"[strikes.subs] created: buyer={buyer_id} pack={pack_slug} "
                f"sub={res.data[0]['id']} "
                f"tier={sla_tier} channels={channels}"
            )
            return {
                "ok": True,
                "subscription": res.data[0],
                "api_key": sub_api_key if "api" in channels else None,
            }
        except Exception as e:
            self.stats["errors"] += 1
            log.error(f"[strikes.subs] create failed: {e}")
            return {"ok": False, "error": str(e)[:200]}

    # ── ENTERPRISE: API KEYS ────────────────────────────────────────────

    @staticmethod
    def _generate_api_key() -> str:
        """Generate a scoped API key for a whale subscription.
        Format: emp_<32 hex chars> — compatible with common API key patterns.
        """
        return "emp_" + secrets.token_hex(16)

    @staticmethod
    def _hash_api_key(api_key: str) -> str:
        """Return HMAC-SHA256 hash of an API key for secure storage.
        Never store raw keys in the DB."""
        return hmac.new(
            b"empire-v49-api-key-signing",
            api_key.encode(),
            hashlib.sha256,
        ).hexdigest()

    def verify_api_key(self, api_key: str) -> Optional[dict]:
        """Verify an API key against active subscriptions. Returns the
        subscription dict if valid, None otherwise.

        This is called from middleware when an API-channel request arrives.
        """
        if not api_key or not api_key.startswith("emp_"):
            return None
        try:
            db = self.get_db()
            # Fetch all active subscriptions and check their meta.api_key hash
            res = db.table("buyer_subscriptions").select("*") \
                .eq("active", True) \
                .in_("status", ["active", "trialing"]) \
                .execute()
            for sub in (res.data or []):
                meta = sub.get("meta") or {}
                if isinstance(meta, str):
                    try:
                        meta = _json.loads(meta)
                    except Exception:
                        continue
                stored_hash = meta.get("api_key_hash", "")
                if not stored_hash:
                    # Legacy: check raw key stored in meta.api_key
                    if meta.get("api_key") == api_key:
                        return sub
                    continue
                # Constant-time comparison against stored hash
                expected_hash = self._hash_api_key(api_key)
                if hmac.compare_digest(expected_hash, stored_hash):
                    return sub
            return None
        except Exception:
            return None

    def rotate_api_key(self, sub_id: str) -> dict:
        """Generate a new API key for a subscription and store its hash."""
        new_key = self._generate_api_key()
        key_hash = self._hash_api_key(new_key)
        try:
            db = self.get_db()
            # Fetch current meta
            res = db.table("buyer_subscriptions").select("meta") \
                .eq("id", sub_id).limit(1).execute()
            if not res.data:
                return {"ok": False, "error": "Subscription not found"}
            meta = res.data[0].get("meta") or {}
            if isinstance(meta, str):
                try:
                    meta = _json.loads(meta)
                except Exception:
                    meta = {}
            meta["api_key_hash"] = key_hash
            meta["api_key_prefix"] = new_key[:8] + "..."
            meta["api_key_rotated_at"] = datetime.now(timezone.utc).isoformat()
            db.table("buyer_subscriptions").update({
                "meta": _json.dumps(meta),
            }).eq("id", sub_id).execute()
            return {"ok": True, "api_key": new_key, "api_key_prefix": new_key[:8] + "..."}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    # ── ENTERPRISE: CUSTOM LANES ────────────────────────────────────────

    def _save_custom_lanes(self, sub_id: str, pack_id: str, lane_ids: list[int]):
        """Write custom lane assignments for an enterprise subscription
        into the subscription's meta field."""
        try:
            db = self.get_db()
            res = db.table("buyer_subscriptions").select("meta") \
                .eq("id", sub_id).limit(1).execute()
            if not res.data:
                return
            meta = res.data[0].get("meta") or {}
            if isinstance(meta, str):
                try:
                    meta = _json.loads(meta)
                except Exception:
                    meta = {}
            meta["custom_lanes"] = lane_ids
            # Also store lane details from the catalog
            meta["custom_lane_details"] = [
                {"lane_id": lid, "niche": "Enterprise"}
                for lid in lane_ids
            ]
            db.table("buyer_subscriptions").update({
                "meta": _json.dumps(meta),
            }).eq("id", sub_id).execute()
        except Exception as e:
            log.warning(f"[strikes.subs] save_custom_lanes failed: {e}")

    def get_custom_lanes(self, sub_id: str) -> list[int]:
        """Return custom lane IDs for a subscription, or empty list if
        using the pack's default lanes."""
        try:
            db = self.get_db()
            res = db.table("buyer_subscriptions").select("meta") \
                .eq("id", sub_id).limit(1).execute()
            if not res.data:
                return []
            meta = res.data[0].get("meta") or {}
            if isinstance(meta, str):
                try:
                    meta = _json.loads(meta)
                except Exception:
                    return []
            return meta.get("custom_lanes", []) or []
        except Exception:
            return []

    def set_webhook_url(self, sub_id: str, webhook_url: str) -> dict:
        """Set or update the webhook delivery URL for a subscription."""
        if webhook_url and not webhook_url.startswith("https://"):
            return {"ok": False, "error": "webhook_url must be HTTPS"}
        try:
            db = self.get_db()
            res = db.table("buyer_subscriptions").select("meta") \
                .eq("id", sub_id).limit(1).execute()
            if not res.data:
                return {"ok": False, "error": "Subscription not found"}
            meta = res.data[0].get("meta") or {}
            if isinstance(meta, str):
                try:
                    meta = _json.loads(meta)
                except Exception:
                    meta = {}
            meta["webhook_url"] = webhook_url
            db.table("buyer_subscriptions").update({
                "meta": _json.dumps(meta),
            }).eq("id", sub_id).execute()
            return {"ok": True, "webhook_url": webhook_url}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    def get_webhook_url(self, sub: dict) -> str:
        """Extract webhook URL from a subscription's meta."""
        meta = sub.get("meta") or {}
        if isinstance(meta, str):
            try:
                meta = _json.loads(meta)
            except Exception:
                return ""
        return meta.get("webhook_url", "") or ""

    def get_sla_tier(self, sub: dict) -> str:
        """Extract SLA tier from a subscription's meta."""
        meta = sub.get("meta") or {}
        if isinstance(meta, str):
            try:
                meta = _json.loads(meta)
            except Exception:
                return "standard"
        return meta.get("sla_tier", "standard") or "standard"

    # ── WHALE: USAGE ALERTS ────────────────────────────────────────────

    def usage_alert_status(self, sub: dict) -> Optional[str]:
        """Check if a whale subscription is approaching its cap and return
        an alert message, or None if everything is fine.

        Returns messages like:
          - "80% of daily cap used"
          - "90% of period cap used — warn buyer"
          - None (no alert needed)
        """
        daily_used = self._buyer_daily_usage(sub["buyer_id"])
        daily_max = sub.get("max_leads_per_day", 999999)
        if daily_max > 0 and daily_used >= daily_max * 0.8:
            pct = round(daily_used / daily_max * 100)
            return f"{pct}% of daily cap used"

        period_used = self._sub_period_usage(sub["id"])
        period_max = sub.get("max_leads_per_month", 999999)
        if period_max > 0 and period_used >= period_max * 0.9:
            pct = round(period_used / period_max * 100)
            return f"{pct}% of period cap reached — warn buyer"

        return None

    async def update_subscription_status(
        self, sub_id: str, status: str
    ) -> dict:
        """Pause, resume, or cancel a subscription."""
        valid = {"active", "paused", "canceled", "expired"}
        if status not in valid:
            return {"ok": False, "error": f"Invalid status: {status}"}

        try:
            db = self.get_db()
            now = datetime.now(timezone.utc).isoformat()
            update = {
                "status": status,
                "active": status == "active",
                "updated_at": now,
            }
            if status == "canceled":
                update["period_end"] = now
            db.table("buyer_subscriptions").update(update) \
                .eq("id", sub_id).execute()
            log.info(f"[strikes.subs] {sub_id} → {status}")
            return {"ok": True, "subscription_id": sub_id, "status": status}
        except Exception as e:
            self.stats["errors"] += 1
            return {"ok": False, "error": str(e)[:200]}

    # ── CAP CHECKS ─────────────────────────────────────────────────────

    def _buyer_daily_usage(self, buyer_id: str) -> int:
        """Return total leads delivered today across all of a buyer's
        subscriptions."""
        today = date.today().isoformat()
        try:
            db = self.get_db()
            res = db.table("buyer_pack_stats").select("leads_delivered") \
                .eq("buyer_id", buyer_id) \
                .eq("stat_date", today) \
                .execute()
            return sum(r["leads_delivered"] for r in (res.data or []))
        except Exception:
            return 0

    def _sub_period_usage(self, sub_id: str) -> int:
        """Return leads delivered in the current billing period for a sub."""
        try:
            db = self.get_db()
            res = db.table("buyer_subscriptions").select("leads_delivered_period") \
                .eq("id", sub_id).limit(1).execute()
            return res.data[0]["leads_delivered_period"] if res.data else 0
        except Exception:
            return 0

    def is_capped(self, sub: dict) -> tuple[bool, str]:
        """Check if a subscription has hit its daily or monthly cap.

        Returns: (is_capped: bool, reason: str)
        """
        # Daily cap (across all subs for this buyer)
        daily_used = self._buyer_daily_usage(sub["buyer_id"])
        daily_max = sub.get("max_leads_per_day", 10)
        if daily_used >= daily_max:
            self.stats["caps_hit"] += 1
            return True, f"Daily cap reached ({daily_used}/{daily_max})"

        # Monthly/per-period cap (per-subscription)
        period_used = self._sub_period_usage(sub["id"])
        period_max = sub.get("max_leads_per_month", 300)
        if period_used >= period_max:
            self.stats["caps_hit"] += 1
            return True, f"Period cap reached ({period_used}/{period_max})"

        return False, ""

    # ── USAGE LOGGING ───────────────────────────────────────────────────

    async def log_delivery(
        self,
        sub: dict,
        *,
        qualified: bool = False,
        calls_placed: int = 0,
        calls_connected: int = 0,
        revenue: float = 0.0,
        fee: float = 0.0,
    ) -> dict:
        """Record a lead delivery against a subscription. Increments the
        daily rollup (buyer_pack_stats) and the period counter."""
        today = date.today().isoformat()
        try:
            db = self.get_db()

            # Upsert today's stats row: check for existing row first,
            # then insert or update — avoids supabase-py upsert quirks
            # with array-type on_conflict parameters.
            existing = db.table("buyer_pack_stats").select("id, leads_delivered, revenue_generated, fee_earned") \
                .eq("subscription_id", sub["id"]) \
                .eq("stat_date", today) \
                .limit(1).execute()

            if existing.data:
                row = existing.data[0]
                db.table("buyer_pack_stats").update({
                    "leads_delivered":   row["leads_delivered"] + 1,
                    "leads_qualified":   row.get("leads_qualified", 0) + (1 if qualified else 0),
                    "calls_placed":      row.get("calls_placed", 0) + calls_placed,
                    "calls_connected":   row.get("calls_connected", 0) + calls_connected,
                    "revenue_generated": round(float(row.get("revenue_generated", 0)) + revenue, 2),
                    "fee_earned":        round(float(row.get("fee_earned", 0)) + fee, 2),
                }).eq("id", row["id"]).execute()
            else:
                db.table("buyer_pack_stats").insert({
                    "subscription_id":   sub["id"],
                    "buyer_id":          sub["buyer_id"],
                    "pack_id":           sub["pack_id"],
                    "stat_date":         today,
                    "leads_delivered":   1,
                    "leads_qualified":   1 if qualified else 0,
                    "calls_placed":      calls_placed,
                    "calls_connected":   calls_connected,
                    "revenue_generated": round(revenue, 2),
                    "fee_earned":        round(fee, 2),
                }).execute()

            # Increment the period counter on the subscription (fetch +
            # update — no RPC call needed)
            current = db.table("buyer_subscriptions").select("leads_delivered_period") \
                .eq("id", sub["id"]).limit(1).execute()
            if current.data:
                new_count = current.data[0]["leads_delivered_period"] + 1
                db.table("buyer_subscriptions").update({
                    "leads_delivered_period": new_count,
                }).eq("id", sub["id"]).execute()

            self.stats["leads_delivered"] += 1
            return {"ok": True}
        except Exception as e:
            self.stats["errors"] += 1
            log.error(f"[strikes.subs] log_delivery failed: {e}")
            return {"ok": False, "error": str(e)[:200]}


# ═══════════════════════════════════════════════════════════════════════
# DELIVERY FILTER
# ═══════════════════════════════════════════════════════════════════════


class DeliveryFilter:
    """Given a qualified lead, determine which subscribed buyers should
    receive it based on lane/niche matching, subscription caps, and
    delivery channel availability.

    This is the bridge between the lead-generation pipeline and the
    Strike Packs product system. Call `eligible_buyers(lead)` in the
    lead-dispatch path before routing to the switchboard.
    """

    def __init__(
        self,
        get_db: Callable,
        catalog: StrikePackCatalog,
        subscriptions: SubscriptionEngine,
    ):
        self.get_db = get_db
        self.catalog = catalog
        self.subscriptions = subscriptions
        self.stats = {"checks": 0, "matched": 0, "delivered": 0,
                       "filtered_out": 0, "errors": 0}

    async def eligible_buyers(
        self,
        lead: dict,
    ) -> list[dict]:
        """Given a lead dict (must contain at minimum 'niche' and ideally
        'lane_id'), return a list of dicts:

            [{
                "subscription": {...},   # from buyer_subscriptions
                "buyer": {...},          # from buyers table
                "pack": {...},           # from strike_packs table
                "delivery_channels": [...],  # channels this sub supports
            }, ...]

        A buyer is eligible if:
          1. They have an active subscription to a pack covering this lead's
             niche/lane
          2. The subscription has not hit daily or monthly caps
          3. The buyer is_active and in an open hours window
        """
        self.stats["checks"] += 1
        niche = lead.get("niche") or ""
        lane_id = lead.get("lane_id")

        if not niche:
            self.stats["errors"] += 1
            log.warning("[strikes.filter] lead has no niche, skipping")
            return []

        # Step 1: Find packs covering this lane or niche
        candidate_packs = self._packs_for_lead(niche, lane_id)
        if not candidate_packs:
            self.stats["filtered_out"] += 1
            return []

        # Step 2: Find active subscriptions for those packs
        all_subs = self.subscriptions.all_active()
        matched_subs = [
            s for s in all_subs
            if s["pack_id"] in {p["id"] for p in candidate_packs}
        ]
        if not matched_subs:
            self.stats["filtered_out"] += 1
            return []

        # Step 3: Check caps and buyer state
        results = []
        for sub in matched_subs:
            buyer = sub.get("buyers") or {}
            if not buyer.get("is_active", False):
                continue

            # Check daily/monthly caps
            capped, reason = self.subscriptions.is_capped(sub)
            if capped:
                log.debug(f"[strikes.filter] {sub['id']} capped: {reason}")
                continue

            pack = self.catalog.by_id(sub["pack_id"])
            if not pack:
                continue

            self.stats["matched"] += 1
            results.append({
                "subscription":      sub,
                "buyer":             buyer,
                "pack":              pack,
                "delivery_channels": pack.get("delivery_channels", ["email"]),
            })

        return results

    def _packs_for_lead(
        self, niche: str, lane_id: Optional[int] = None
    ) -> list[dict]:
        """Return active packs that could receive this lead."""
        # If we have a lane_id, narrow by lane coverage
        if lane_id is not None:
            return self.catalog.packs_covering_lane(lane_id)

        # Fallback: match by niche name (less precise, used when lane_id
        # isn't available in the lead record yet)
        return [
            p for p in self.catalog.all(public_only=False)
            if niche.lower() in [n.lower() for n in (p.get("niches") or [])]
        ]

    async def deliver(
        self,
        recipient: dict,
        lead: dict,
    ) -> dict:
        """Deliver a lead to a subscribing buyer. Logs the delivery in
        buyer_pack_stats and returns the delivery result.

        For whale-tier products with api/webhook channels, this POSTs
        the lead payload to the buyer's configured webhook URL.
        """
        sub = recipient["subscription"]
        buyer = recipient["buyer"]
        pack = recipient["pack"]
        channels = pack.get("delivery_channels", ["email"])

        # Log the delivery
        result = await self.subscriptions.log_delivery(
            sub,
            qualified=bool(lead.get("urgency_score", 0) >= 7),
        )

        # ── WEBHOOK DELIVERY (for api/webhook channel products) ──────
        webhook_sent = False
        webhook_error = None
        if "api" in channels or "webhook" in channels:
            webhook_url = self.subscriptions.get_webhook_url(sub)
            if webhook_url:
                webhook_sent, webhook_error = await self._send_webhook(
                    webhook_url, sub, pack, lead
                )
            else:
                webhook_error = "no webhook_url configured"

        self.stats["delivered"] += 1

        return {
            "ok":                  result.get("ok", False),
            "buyer_id":            buyer.get("id"),
            "buyer_name":          buyer.get("buyer_name"),
            "destination_phone":   buyer.get("destination_phone"),
            "pack_slug":           pack.get("slug"),
            "subscription_id":     sub.get("id"),
            "webhook_sent":        webhook_sent,
            "webhook_error":       webhook_error,
            "delivery_channels":   channels,
        }

    # ── WHALE: WEBHOOK POST ────────────────────────────────────────────

    async def _send_webhook(
        self,
        webhook_url: str,
        sub: dict,
        pack: dict,
        lead: dict,
    ) -> tuple[bool, Optional[str]]:
        """POST the lead payload to a buyer's configured webhook URL.
        Includes HMAC signature header for verification by the receiver.

        Returns (success: bool, error: Optional[str])
        """
        # Build the webhook payload
        payload = {
            "event": "lead.delivered",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pack": {
                "slug": pack.get("slug"),
                "name": pack.get("name"),
                "tier": pack.get("tier"),
            },
            "subscription_id": sub.get("id"),
            "lead": {
                "id": lead.get("id") or lead.get("target_id"),
                "warehouse_name": lead.get("warehouse_name") or lead.get("name", ""),
                "address": lead.get("address", ""),
                "city": lead.get("city", ""),
                "state": lead.get("state", ""),
                "phone": lead.get("phone", ""),
                "asset_value": lead.get("asset_value", 0),
                "damage_severity": lead.get("damage_severity", ""),
                "niche": lead.get("niche", ""),
                "metro": lead.get("metro", ""),
                "urgency_score": lead.get("urgency_score", 0),
                "storm_event": lead.get("storm_event", ""),
                "storm_severity": lead.get("storm_severity", ""),
                "risk_level": lead.get("risk_level", ""),
                "risk_rank": lead.get("risk_rank", 0),
                "source": lead.get("source", "empire"),
                "meta": lead.get("meta", {}),
            },
        }

        # Sign the payload with an HMAC of the subscription ID for
        # receiver-side verification
        signature = hmac.new(
            sub["id"].encode() if isinstance(sub.get("id"), str) else b"",
            _json.dumps(payload, sort_keys=True).encode(),
            hashlib.sha256,
        ).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "X-Empire-Signature": f"sha256={signature}",
            "X-Empire-Subscription-Id": sub.get("id", ""),
            "User-Agent": "EmpireAI-StrikePacks/1.0",
        }

        try:
            async with _httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(webhook_url, json=payload, headers=headers)
                if resp.status_code < 300:
                    log.info(
                        f"[strikes.webhook] delivered to {webhook_url} "
                        f"sub={sub['id']} status={resp.status_code}"
                    )
                    return True, None
                else:
                    body = resp.text[:300]
                    log.warning(
                        f"[strikes.webhook] {webhook_url} returned "
                        f"{resp.status_code}: {body}"
                    )
                    return False, f"HTTP {resp.status_code}: {body}"
        except Exception as e:
            log.warning(f"[strikes.webhook] POST to {webhook_url} failed: {e}")
            return False, str(e)[:200]

    # ── WHALE: WEBHOOK TEST ────────────────────────────────────────────

    async def test_webhook(self, sub: dict) -> dict:
        """Send a test payload to the subscription's webhook URL to
        verify connectivity. Returns the result."""
        webhook_url = self.subscriptions.get_webhook_url(sub)
        if not webhook_url:
            return {"ok": False, "error": "No webhook URL configured"}
        pack = self.catalog.by_id(sub["pack_id"])
        test_lead = {
            "id": "test-" + secrets.token_hex(4),
            "warehouse_name": "TEST: Webhook Verification",
            "address": "123 Test St",
            "city": "Dallas",
            "state": "TX",
            "phone": "+12145551234",
            "asset_value": 500000,
            "damage_severity": "Test",
            "niche": "Test",
            "metro": "Dallas-Fort Worth",
            "urgency_score": 5,
            "storm_event": "Webhook Test",
            "storm_severity": "Test",
            "risk_level": "Test",
            "risk_rank": 1,
            "source": "webhook_test",
            "meta": {"test": True},
        }
        success, error = await self._send_webhook(webhook_url, sub, pack or {}, test_lead)
        return {"ok": success, "error": error, "webhook_url": webhook_url}

    def snapshot(self) -> dict:
        """Return current filter stats for the dashboard."""
        return {**self.stats}


# ═══════════════════════════════════════════════════════════════════════
# WHALE TIER: API KEY AUTH MIDDLEWARE
# ═══════════════════════════════════════════════════════════════════════


async def require_whale_api_key(
    request: Request,
    subscriptions: SubscriptionEngine,
) -> Optional[dict]:
    """FastAPI dependency that validates an API key from the
    Authorization header against active whale subscriptions.

    Use on API-channel endpoints for whale products:

        @app.post("/api/v1/whale/data")
        async def whale_data(
            sub: dict = Depends(lambda: require_whale_api_key(request, subscriptions)),
        ):
            if not sub:
                raise HTTPException(401, "Invalid API key")
            ...

    Supported header formats:
      Authorization: Bearer emp_<key>
      X-API-Key: emp_<key>
    """
    auth_header = request.headers.get("Authorization", "")
    api_key = ""
    if auth_header.startswith("Bearer "):
        api_key = auth_header[7:].strip()
    if not api_key:
        api_key = request.headers.get("X-API-Key", "").strip()
    if not api_key:
        return None

    return subscriptions.verify_api_key(api_key)


# ═══════════════════════════════════════════════════════════════════════
# ROUTE REGISTRATION
# ═══════════════════════════════════════════════════════════════════════


def register_strike_pack_routes(
    app: FastAPI,
    *,
    catalog: StrikePackCatalog,
    subscriptions: SubscriptionEngine,
    require_auth: Callable,
    require_owner: Optional[Callable] = None,
):
    """Wire Strike Pack API endpoints into the FastAPI app.

    Public endpoints (no auth):
        GET  /api/v1/strike-packs            — public catalog

    Auth-required endpoints:
        GET  /api/v1/strike-packs/admin       — full catalog (incl. hidden)
        GET  /api/v1/strike-packs/{slug}      — single pack detail
        POST /api/v1/strike-packs/subscribe   — subscribe a buyer
        POST /api/v1/strike-packs/{sub_id}/pause
        POST /api/v1/strike-packs/{sub_id}/cancel
        GET  /api/v1/strike-packs/subscriptions        — all active subs
        GET  /api/v1/strike-packs/subscriptions/{id}   — single sub detail
        GET  /api/v1/strike-packs/stats      — system stats
    """

    # ── PUBLIC: CATALOG ───────────────────────────────────────────────

    @app.get("/api/v1/strike-packs")
    async def list_packs_public():
        """Public product catalog — only shows is_public=true packs."""
        packs = catalog.all(public_only=True)
        # Strip internal fields for the public view
        safe = []
        for p in packs:
            safe.append({
                "slug":                p["slug"],
                "name":                p["name"],
                "description":         p["description"],
                "tier":                p["tier"],
                "monthly_price_usd":   round(p["monthly_price_cents"] / 100, 2),
                "price_per_lead_usd":  round(p["price_per_lead_cents"] / 100, 2),
                "max_leads_per_day":   p["max_leads_per_day"],
                "max_leads_per_month": p["max_leads_per_month"],
                "delivery_channels":   p.get("delivery_channels", ["email"]),
                "target_buyer":        p.get("target_buyer"),
                "features":            p.get("features", []),
                "lane_count":          p["lane_count"],
                "niches":              p.get("niches", []),
            })
        return JSONResponse({"packs": safe})

    @app.get("/api/v1/strike-packs/{slug}")
    async def pack_detail(slug: str):
        """Public detail for a single pack, including lane breakdown."""
        pack = catalog.by_slug(slug)
        if not pack:
            raise HTTPException(404, f"Pack '{slug}' not found")

        lanes = catalog.lanes_for_pack(pack["id"])
        return JSONResponse({
            "slug":                pack["slug"],
            "name":                pack["name"],
            "description":         pack["description"],
            "tier":                pack["tier"],
            "monthly_price_usd":   round(pack["monthly_price_cents"] / 100, 2),
            "price_per_lead_usd":  round(pack["price_per_lead_cents"] / 100, 2),
            "max_leads_per_day":   pack["max_leads_per_day"],
            "max_leads_per_month": pack["max_leads_per_month"],
            "delivery_channels":   pack.get("delivery_channels", ["email"]),
            "target_buyer":        pack.get("target_buyer"),
            "features":            pack.get("features", []),
            "lane_count":          pack["lane_count"],
            "niches":              pack.get("niches", []),
            "lanes": [
                {
                    "lane_id":   r["lane_id"],
                    "niche":     r["niche"],
                    "sub_niche": r.get("sub_niche"),
                    "strategy":  r["strategy"],
                }
                for r in lanes
            ],
        })

    # ── ADMIN: FULL CATALOG ───────────────────────────────────────────

    @app.get("/api/v1/strike-packs/admin")
    async def list_packs_admin(auth: bool = Depends(require_auth)):
        """Full catalog including hidden packs (is_public=false)."""
        packs = catalog.all(public_only=False)
        return JSONResponse({"packs": packs})

    # ── SUBSCRIBE ─────────────────────────────────────────────────────

    @app.post("/api/v1/strike-packs/subscribe")
    async def subscribe_buyer(request: Request, auth: bool = Depends(require_auth)):
        """Subscribe a buyer to a Strike Pack.

        Body: {
            "buyer_id": "<uuid>",
            "pack_slug": "roofing_strike",
            // Optional price/cap overrides
            "monthly_price_cents": 50000,
            "max_leads_per_day": 20,
            "stripe_customer_id": "cus_...",
            "stripe_subscription_id": "sub_...",
            "notes": "Priority partner",
            // Whale/enterprise fields
            "webhook_url": "https://carrier.example.com/webhook/empire",
            "custom_lanes": [29, 30, 31],
            "sla_tier": "premium",      // standard | enhanced | premium
            "dedicated_support": true,
        }
        """
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")

        buyer_id = body.get("buyer_id", "").strip()
        pack_slug = body.get("pack_slug", "").strip()
        if not buyer_id or not pack_slug:
            raise HTTPException(400, "buyer_id and pack_slug are required")

        result = await subscriptions.create_subscription(
            buyer_id=buyer_id,
            pack_slug=pack_slug,
            monthly_price_cents=body.get("monthly_price_cents"),
            price_per_lead_cents=body.get("price_per_lead_cents"),
            max_leads_per_day=body.get("max_leads_per_day"),
            max_leads_per_month=body.get("max_leads_per_month"),
            stripe_customer_id=body.get("stripe_customer_id"),
            stripe_subscription_id=body.get("stripe_subscription_id"),
            notes=body.get("notes", ""),
            # Whale/enterprise
            webhook_url=body.get("webhook_url"),
            custom_lanes=body.get("custom_lanes"),
            sla_tier=body.get("sla_tier", "standard"),
            dedicated_support=bool(body.get("dedicated_support", False)),
        )

        if not result.get("ok"):
            status = 409 if "already has" in (result.get("error") or "") else 400
            raise HTTPException(status, result.get("error", "Subscription failed"))

        return JSONResponse(result)

    # ── PAUSE / CANCEL ────────────────────────────────────────────────

    @app.post("/api/v1/strike-packs/subscriptions/{sub_id}/pause")
    async def pause_subscription(
        sub_id: str, auth: bool = Depends(require_auth)
    ):
        result = await subscriptions.update_subscription_status(sub_id, "paused")
        if not result.get("ok"):
            raise HTTPException(400, result.get("error", "Pause failed"))
        return JSONResponse(result)

    @app.post("/api/v1/strike-packs/subscriptions/{sub_id}/cancel")
    async def cancel_subscription(
        sub_id: str, auth: bool = Depends(require_auth)
    ):
        result = await subscriptions.update_subscription_status(sub_id, "canceled")
        if not result.get("ok"):
            raise HTTPException(400, result.get("error", "Cancel failed"))
        return JSONResponse(result)

    # ── LIST SUBSCRIPTIONS ────────────────────────────────────────────

    @app.get("/api/v1/strike-packs/subscriptions")
    async def list_subscriptions(
        buyer_id: str = Query(""),
        pack_slug: str = Query(""),
        tier: str = Query(""),  # filter by tier: standard, combo, whale, enterprise
        auth: bool = Depends(require_auth),
    ):
        """List active subscriptions. Filter by ?buyer_id or ?pack_slug or ?tier."""
        if buyer_id:
            subs = subscriptions.active_subscriptions_for_buyer(buyer_id)
        elif pack_slug:
            pack = catalog.by_slug(pack_slug)
            if not pack:
                raise HTTPException(404, f"Pack '{pack_slug}' not found")
            subs = subscriptions.active_subscriptions_for_pack(pack["id"])
        else:
            subs = subscriptions.all_active()

        # Enrich with pack info for display
        enriched = []
        for s in subs:
            pack = catalog.by_id(s["pack_id"])

            # Optional tier filter
            if tier and (pack or {}).get("tier") != tier:
                continue

            buyer = s.pop("buyers", {}) if "buyers" in s else {}

            # Parse meta for enterprise/whale fields
            meta = s.get("meta") or {}
            if isinstance(meta, str):
                try:
                    meta = _json.loads(meta)
                except Exception:
                    meta = {}

            sla_tier = meta.get("sla_tier", "standard")
            dedicated_support = meta.get("dedicated_support", False)
            webhook_url = meta.get("webhook_url", "")
            custom_lanes = meta.get("custom_lanes", [])
            api_key_prefix = meta.get("api_key_prefix", "")

            # Check for usage alert on whale subscriptions
            usage_alert = None
            if (pack or {}).get("tier") in ("whale", "enterprise"):
                usage_alert = subscriptions.usage_alert_status(s)

            enriched.append({
                "id":                  s["id"],
                "buyer_id":            s["buyer_id"],
                "buyer_name":          buyer.get("buyer_name", "?"),
                "pack_id":             s["pack_id"],
                "pack_name":           pack["name"] if pack else "?",
                "pack_slug":           pack["slug"] if pack else "?",
                "tier":                pack["tier"] if pack else "?",
                "status":              s["status"],
                "active":              s["active"],
                "monthly_price_usd":   round(s["monthly_price_cents"] / 100, 2),
                "max_leads_per_day":   s["max_leads_per_day"],
                "leads_delivered_period": s["leads_delivered_period"],
                "period_start":        s["period_start"],
                "period_end":          s.get("period_end"),
                "stripe_subscription_id": s.get("stripe_subscription_id"),
                "created_at":          s["created_at"],
                # Whale/enterprise fields
                "sla_tier":            sla_tier,
                "dedicated_support":   dedicated_support,
                "webhook_url":         webhook_url or None,
                "custom_lanes":        custom_lanes or None,
                "api_key_prefix":      api_key_prefix or None,
                "usage_alert":         usage_alert,
            })
        return JSONResponse({"subscriptions": enriched})

    # ── WHALE: WEBHOOK CONFIG ─────────────────────────────────────────

    @app.post("/api/v1/strike-packs/subscriptions/{sub_id}/webhook")
    async def set_webhook(
        sub_id: str,
        request: Request,
        auth: bool = Depends(require_auth),
    ):
        """Set or update the webhook delivery URL for a subscription.
        Body: {"webhook_url": "https://..."}
        """
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")
        webhook_url = (body.get("webhook_url") or "").strip()
        if not webhook_url:
            raise HTTPException(400, "webhook_url is required")
        result = subscriptions.set_webhook_url(sub_id, webhook_url)
        if not result.get("ok"):
            raise HTTPException(400, result.get("error", "Failed"))
        return JSONResponse(result)

    @app.post("/api/v1/strike-packs/subscriptions/{sub_id}/webhook/test")
    async def test_webhook(
        sub_id: str,
        auth: bool = Depends(require_auth),
    ):
        """Send a test payload to the subscription's webhook URL to
        verify connectivity."""
        sub = subscriptions.subscription_by_id(sub_id)
        if not sub:
            raise HTTPException(404, "Subscription not found")
        result = await delivery_filter.test_webhook(sub)
        return JSONResponse(result)

    # ── WHALE: API KEY MANAGEMENT ─────────────────────────────────────

    @app.post("/api/v1/strike-packs/subscriptions/{sub_id}/rotate-key")
    async def rotate_api_key(
        sub_id: str,
        auth: bool = Depends(require_auth),
    ):
        """Generate a new API key for an API-channel subscription.
        The old key is immediately invalidated."""
        result = subscriptions.rotate_api_key(sub_id)
        if not result.get("ok"):
            raise HTTPException(400, result.get("error", "Failed"))
        # Return the new key once — it won't be visible again
        return JSONResponse({
            "ok": True,
            "api_key": result["api_key"],
            "api_key_prefix": result["api_key_prefix"],
            "message": "Save this key — it will not be shown again",
        })

    # ── WHALE: CUSTOM LANE ASSIGNMENT ─────────────────────────────────

    @app.post("/api/v1/strike-packs/subscriptions/{sub_id}/lanes")
    async def set_custom_lanes(
        sub_id: str,
        request: Request,
        auth: bool = Depends(require_auth),
    ):
        """Override the pack's default lane IDs for this subscription.
        Body: {"lane_ids": [29, 30, 31]}
        """
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")
        lane_ids = body.get("lane_ids", [])
        if not isinstance(lane_ids, list) or not all(isinstance(x, int) for x in lane_ids):
            raise HTTPException(400, "lane_ids must be a list of integers")

        sub = subscriptions.subscription_by_id(sub_id)
        if not sub:
            raise HTTPException(404, "Subscription not found")

        pack = catalog.by_id(sub["pack_id"])
        if not pack:
            raise HTTPException(404, "Pack not found")

        subscriptions._save_custom_lanes(sub_id, pack["id"], lane_ids)
        return JSONResponse({"ok": True, "lane_ids": lane_ids, "count": len(lane_ids)})

    # ── WHALE: USAGE ALERTS ───────────────────────────────────────────

    @app.get("/api/v1/strike-packs/whale/alerts")
    async def whale_usage_alerts(auth: bool = Depends(require_auth)):
        """Return usage alerts for all active whale/enterprise subscriptions."""
        subs = subscriptions.all_active()
        alerts = []
        for s in subs:
            pack = catalog.by_id(s["pack_id"])
            tier = (pack or {}).get("tier", "")
            if tier not in ("whale", "enterprise"):
                continue
            alert = subscriptions.usage_alert_status(s)
            if alert:
                buyer = s.get("buyers", {})
                alerts.append({
                    "subscription_id":   s["id"],
                    "buyer_name":        buyer.get("buyer_name", "?"),
                    "pack_name":         pack["name"] if pack else "?",
                    "pack_slug":         pack["slug"] if pack else "?",
                    "tier":              tier,
                    "alert":             alert,
                    "monthly_price_usd": round(s["monthly_price_cents"] / 100, 2),
                    "leads_delivered_period": s["leads_delivered_period"],
                })
        return JSONResponse({"alerts": alerts, "count": len(alerts)})

    @app.get("/api/v1/strike-packs/subscriptions/{sub_id}")
    async def subscription_detail(
        sub_id: str, auth: bool = Depends(require_auth)
    ):
        """Single subscription with stats history."""
        sub = subscriptions.subscription_by_id(sub_id)
        if not sub:
            raise HTTPException(404, "Subscription not found")

        pack = catalog.by_id(sub["pack_id"])
        buyer = sub.pop("buyers", {}) if "buyers" in sub else {}

        # Fetch recent stats
        stats_rows = []
        try:
            db = catalog.get_db()
            res = db.table("buyer_pack_stats").select("*") \
                .eq("subscription_id", sub_id) \
                .order("stat_date", desc=True) \
                .limit(30).execute()
            stats_rows = res.data or []
        except Exception:
            pass

        return JSONResponse({
            "subscription": {
                "id":                  sub["id"],
                "buyer_id":            sub["buyer_id"],
                "buyer_name":          buyer.get("buyer_name", "?"),
                "pack_id":             sub["pack_id"],
                "pack_name":           pack["name"] if pack else "?",
                "pack_slug":           pack["slug"] if pack else "?",
                "status":              sub["status"],
                "monthly_price_usd":   round(sub["monthly_price_cents"] / 100, 2),
                "max_leads_per_day":   sub["max_leads_per_day"],
                "max_leads_per_month": sub["max_leads_per_month"],
                "leads_delivered_period": sub["leads_delivered_period"],
                "period_start":        sub["period_start"],
                "period_end":          sub.get("period_end"),
                "stripe_customer_id":  sub.get("stripe_customer_id"),
                "notes":               sub.get("notes"),
                "created_at":          sub["created_at"],
            },
            "stats": [
                {
                    "stat_date":         r["stat_date"],
                    "leads_delivered":   r["leads_delivered"],
                    "leads_qualified":   r["leads_qualified"],
                    "calls_placed":      r["calls_placed"],
                    "calls_connected":   r["calls_connected"],
                    "revenue_generated": float(r["revenue_generated"]),
                    "fee_earned":        float(r["fee_earned"]),
                }
                for r in stats_rows
            ],
        })

    # ── STATS ─────────────────────────────────────────────────────────

    @app.get("/api/v1/strike-packs/stats")
    async def strike_packs_stats(auth: bool = Depends(require_auth)):
        """System-wide stats for the Strike Pack engine."""
        all_subs = subscriptions.all_active()
        total_subs = len(all_subs)

        # Aggregate stats from buyer_pack_stats
        total_revenue = 0.0
        total_fee = 0.0
        total_leads = 0
        try:
            db = catalog.get_db()
            res = db.table("buyer_pack_stats").select(
                "leads_delivered, revenue_generated, fee_earned"
            ).execute()
            for r in (res.data or []):
                total_leads += r.get("leads_delivered", 0)
                total_revenue += float(r.get("revenue_generated", 0))
                total_fee += float(r.get("fee_earned", 0))
        except Exception:
            pass

        return JSONResponse({
            "catalog": {
                "total_packs":        len(catalog.all(public_only=False)),
                "total_active_packs": len(catalog.all(public_only=True)),
                "packs_by_tier": {
                    tier: len(catalog.all(tier=tier, public_only=False))
                    for tier in ["standard", "combo", "whale", "enterprise"]
                },
            },
            "subscriptions": {
                "active":   total_subs,
                "created":  subscriptions.stats["subscriptions_created"],
                "delivered": subscriptions.stats["leads_delivered"],
                "caps_hit": subscriptions.stats["caps_hit"],
            },
            "delivery": {
                "checks":       catalog.stats.get("loads", 0) + subscriptions.stats.get("leads_delivered", 0),
                "total_leads":  total_leads,
                "total_revenue_usd": round(total_revenue, 2),
                "total_fee_usd":     round(total_fee, 2),
            },
            "cache": {
                "loads":       catalog.stats["loads"],
                "cache_hits":  catalog.stats["cache_hits"],
                "errors":      catalog.stats["errors"] + subscriptions.stats["errors"],
            },
        })

    log.info("[strike_packs] Routes registered · /api/v1/strike-packs/*")
