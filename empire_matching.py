"""
EMPIRE V49 · CONTRACTOR MATCHING ENGINE
=========================================
Replaces the "broadcast to everyone" dispatch model with intelligent
matching. For each lead that needs dispatch, we score every active
contractor and send the magic link to the top N matches only. First
to accept wins.

Scoring model (weighted sum, all factors normalized 0-1):

  metro_match      0.40   exact metro match → 1.0, adjacent metro → 0.5, else → 0
  specialty_match  0.25   jaccard overlap of required specialties vs theirs
  trust_score      0.15   running 0-10 score updated from outcomes
  freshness        0.10   inverse of days since last accepted dispatch
  capacity         0.10   1 - (active_dispatches / max_concurrent)

Trust score evolution (called by claim_outcomes hook in hub.py):

  COMPLETED  → +0.3
  SETTLED    → +0.6 (extra reward for outcome the operator earned a fee on)
  GHOSTED    → -1.5 (accepted but never updated)
  CUSTOMER_COMPLAINT → -2.0 (worst signal)
  Trust score clamped to [0.0, 10.0]

Wire-up in hub.py:

    from empire_matching import (
        ContractorMatcher,
        register_matching_routes,
    )

    matcher = ContractorMatcher(get_db=get_db)
    register_matching_routes(
        app,
        matcher=matcher,
        require_auth=require_auth,
        sign_token=_sign_token,
        send_email=_send_email,
        broadcaster=live_broadcaster,
        public_base_url=PUBLIC_BASE_URL,
    )

    # Replace the existing "broadcast dispatch" code path with:
    matched = await matcher.match_for_lead(
        target=p,
        required_specialties=["roofing", "storm_damage"],
        top_n=5,
    )
    await matcher.dispatch_to_matched(
        matched=matched,
        target=p,
        urgency=analysis.get("urgency", 7),
    )

    # Wire the trust score update inside record_outcome handler:
    await matcher.update_trust_from_outcome(
        contractor_id=outcome["contractor_id"],
        outcome=outcome["outcome"],
    )


Supabase schema additions:

    -- ────────────────────────────────────────────────────────────────────
    -- DISPATCHES — one row per (lead, contractor) magic link sent
    -- Existing dispatches table may already have most of this; here's the
    -- target schema. Use ALTER TABLE for missing columns.
    -- ────────────────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS dispatches (
      id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      created_at        timestamptz NOT NULL DEFAULT now(),
      lead_id           uuid,                    -- references radar_targets.id
      contractor_id     uuid NOT NULL,           -- references contractors.id
      match_score       numeric(4,3),            -- 0.000 to 1.000
      match_components  jsonb DEFAULT '{}'::jsonb,
      token             text UNIQUE,             -- HMAC magic link
      status            text NOT NULL DEFAULT 'sent'
        CHECK (status IN ('sent','accepted','rejected','expired','completed','ghosted')),
      accepted_at       timestamptz,
      completed_at      timestamptz,
      ghosted_at        timestamptz,
      payout_amount     numeric(12,2),
      meta              jsonb DEFAULT '{}'::jsonb
    );
    CREATE INDEX IF NOT EXISTS dispatches_lead_idx       ON dispatches (lead_id);
    CREATE INDEX IF NOT EXISTS dispatches_contractor_idx ON dispatches (contractor_id);
    CREATE INDEX IF NOT EXISTS dispatches_status_idx     ON dispatches (status, created_at DESC);

    -- Adjacent-metro relationships (manual config; populate via SQL or admin UI)
    CREATE TABLE IF NOT EXISTS metro_adjacency (
      metro       text NOT NULL,
      adjacent_to text NOT NULL,
      distance_km numeric(6,1),
      PRIMARY KEY (metro, adjacent_to)
    );

    -- Seed example (Texas metros):
    INSERT INTO metro_adjacency (metro, adjacent_to) VALUES
      ('Dallas / Fort Worth', 'Plano'),
      ('Plano', 'Dallas / Fort Worth'),
      ('Houston', 'Galveston'),
      ('Galveston', 'Houston')
    ON CONFLICT DO NOTHING;

    -- contractors table — ensure the columns we score on exist
    ALTER TABLE contractors
      ADD COLUMN IF NOT EXISTS trust_score        numeric(4,2) DEFAULT 5.0,
      ADD COLUMN IF NOT EXISTS completed_jobs     int  DEFAULT 0,
      ADD COLUMN IF NOT EXISTS active             boolean DEFAULT true,
      ADD COLUMN IF NOT EXISTS specialties        text[] DEFAULT '{}',
      ADD COLUMN IF NOT EXISTS metro              text,
      ADD COLUMN IF NOT EXISTS last_dispatched_at timestamptz,
      ADD COLUMN IF NOT EXISTS max_concurrent     int DEFAULT 3,
      ADD COLUMN IF NOT EXISTS solana_wallet      text;
    CREATE INDEX IF NOT EXISTS contractors_active_metro_idx
      ON contractors (active, metro) WHERE active = true;
"""

import os
import uuid
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional

import httpx
from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse


log = logging.getLogger("empire.matching")


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
# Score weights — change these to re-balance the matching priorities
SCORE_WEIGHTS = {
    "metro_match":     0.40,
    "specialty_match": 0.25,
    "trust_score":     0.15,
    "freshness":       0.10,
    "capacity":        0.10,
}
assert abs(sum(SCORE_WEIGHTS.values()) - 1.0) < 1e-9, "Weights must sum to 1"

# Trust score effects on outcomes
TRUST_DELTA = {
    "completed":          +0.3,
    "settled":            +0.6,
    "ghosted":            -1.5,
    "customer_complaint": -2.0,
    "withdrew":           -0.5,
    "no_show":            -1.0,
}
TRUST_MIN = 0.0
TRUST_MAX = 10.0
TRUST_DEFAULT = 5.0

DEFAULT_TOP_N        = 5
DEFAULT_MAX_CONCUR   = 3
DEFAULT_LINK_TTL     = 60 * 60 * 24  # 24h to accept


# ─────────────────────────────────────────────────────────────────────────────
# THE MATCHER
# ─────────────────────────────────────────────────────────────────────────────
class ContractorMatcher:
    """
    Stateless engine. Given a lead's metro + required specialties, returns
    the ranked top N contractors. Also handles trust score updates.
    """

    def __init__(
        self,
        get_db: Callable,
        score_weights: Optional[dict] = None,
    ):
        self.get_db = get_db
        self.weights = score_weights or SCORE_WEIGHTS
        self.stats = {
            "matches_computed":     0,
            "dispatches_sent":      0,
            "dispatches_accepted":  0,
            "trust_updates":        0,
            "last_match_score_avg": None,
        }

    # ── PUBLIC: GET MATCHES ────────────────────────────────────────────
    async def match_for_lead(
        self,
        *,
        metro: str,
        required_specialties: list[str],
        top_n: int = DEFAULT_TOP_N,
        exclude_contractor_ids: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        Returns top N contractors sorted by score descending.

        Each entry: {contractor: <row>, score: 0.0-1.0, components: {...}}
        """
        exclude_contractor_ids = exclude_contractor_ids or []

        try:
            db = self.get_db()
        except Exception as e:
            log.error(f"[matching] DB unavailable: {e}")
            return []

        # Pull all active contractors (Postgres-side filter on active=true).
        # We score everyone in Python so we can use complex weights without
        # writing complex SQL.
        try:
            res = db.table("contractors").select("*") \
                .eq("active", True).limit(500).execute()
            candidates = res.data or []
        except Exception as e:
            log.error(f"[matching] contractor query failed: {e}")
            return []

        if not candidates:
            log.warning("[matching] no active contractors found")
            return []

        # Filter out excluded
        if exclude_contractor_ids:
            candidates = [c for c in candidates if c["id"] not in exclude_contractor_ids]

        # Load metro adjacency (cached per call · cheap)
        adjacency = await self._load_adjacency(metro)

        # Load active dispatch counts per contractor for capacity scoring
        active_loads = await self._load_active_dispatch_counts([c["id"] for c in candidates])

        scored = []
        for contractor in candidates:
            score, components = self._score_contractor(
                contractor=contractor,
                lead_metro=metro,
                required_specialties=required_specialties,
                metro_adjacency=adjacency,
                active_load=active_loads.get(contractor["id"], 0),
            )

            # Hard exclusion: zero metro match AND zero specialty overlap
            # means this contractor genuinely cannot serve this lead.
            if components["metro_match"] == 0 and components["specialty_match"] == 0:
                continue

            # Hard exclusion: contractor at or above max capacity
            max_concurrent = contractor.get("max_concurrent") or DEFAULT_MAX_CONCUR
            if active_loads.get(contractor["id"], 0) >= max_concurrent:
                continue

            scored.append({
                "contractor": contractor,
                "score":      score,
                "components": components,
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        top = scored[:top_n]

        self.stats["matches_computed"] += 1
        if top:
            avg_score = sum(m["score"] for m in top) / len(top)
            self.stats["last_match_score_avg"] = round(avg_score, 3)

        log.info(
            f"[matching] metro={metro!r} specialties={required_specialties} "
            f"→ {len(top)} matches "
            f"(top score: {top[0]['score']:.2f} {top[0]['contractor'].get('name', '')!r})"
            if top else
            f"[matching] metro={metro!r} specialties={required_specialties} → 0 matches"
        )
        return top

    # ── PUBLIC: DISPATCH ─────────────────────────────────────────────────
    async def dispatch_to_matched(
        self,
        *,
        matched: list[dict],
        lead: dict,
        urgency: int,
        sign_token: Callable,
        send_email: Callable,
        public_base_url: str,
        link_ttl: int = DEFAULT_LINK_TTL,
        broadcaster=None,
        strategy: Optional[str] = None,
        niche: Optional[str] = None,
    ) -> dict:
        """
        Send dispatch magic links to the matched contractors. Creates a
        dispatches row per contractor. First to accept wins via accept route.

        `strategy` and `niche` (if provided) are stamped into each
        dispatches.meta row so the contractor-dispatch path carries the
        SI Strategy Evolution signal end-to-end. The outcome path looks
        these up to call record_strategy_outcome on settlement.

        Returns: {ok, dispatched: N, dispatch_ids: [...]}
        """
        if not matched:
            return {"ok": False, "dispatched": 0, "error": "no matches"}

        try:
            db = self.get_db()
        except Exception as e:
            return {"ok": False, "error": f"DB unavailable: {e}"}

        dispatch_ids = []
        sent = 0

        for entry in matched:
            contractor = entry["contractor"]
            score      = entry["score"]
            components = entry["components"]

            # Build a per-(contractor,lead) token
            token_payload = {
                "lead_id":       str(lead.get("id", "")),
                "contractor_id": str(contractor["id"]),
                "exp":           int(time.time()) + link_ttl,
                "iat":           int(time.time()),
                "kind":          "dispatch_accept",
            }
            token = sign_token(token_payload)
            accept_link = f"{public_base_url.rstrip('/')}/dispatch/accept?t={token}"

            # Insert dispatch row
            try:
                dispatch_meta = {
                    "urgency":     urgency,
                    "lead_addr":   lead.get("address"),
                    "lead_metro":  lead.get("city"),
                }
                if strategy:
                    dispatch_meta["strategy"] = strategy
                if niche:
                    dispatch_meta["niche"] = niche
                ins = db.table("dispatches").insert({
                    "lead_id":         str(lead.get("id")) if lead.get("id") else None,
                    "contractor_id":   str(contractor["id"]),
                    "match_score":     round(score, 3),
                    "match_components":components,
                    "token":           token,
                    "status":          "sent",
                    "meta":            dispatch_meta,
                }).execute()
                dispatch_ids.append(ins.data[0]["id"] if ins.data else None)
            except Exception as e:
                log.error(f"[matching] dispatch insert failed: {e}")
                continue

            # Send the email to the contractor
            html = self._render_dispatch_email(
                contractor=contractor,
                lead=lead,
                urgency=urgency,
                accept_link=accept_link,
                score=score,
            )
            try:
                await send_email(
                    to=contractor["email"],
                    subject=f"⚡ New strike · {lead.get('city', 'Empire')} · urgency {urgency}/10",
                    html=html,
                )
                sent += 1
            except Exception as e:
                log.error(f"[matching] dispatch email failed for {contractor.get('email')}: {e}")

            # SMS notification: contractors miss emails. Push the lead
            # details as an SMS so the contractor has two channels.
            # The accept-link is the same magic link sent via email.
            try:
                if contractor.get("phone"):
                    from empire_voice import VoiceRouter
                    _sms_router = VoiceRouter(
                        vonage_api_key=os.environ.get("VONAGE_API_KEY", ""),
                        vonage_api_secret=os.environ.get("VONAGE_API_SECRET", ""),
                        vonage_app_id=os.environ.get("VONAGE_APPLICATION_ID", ""),
                        vonage_private_key_path=os.environ.get("VONAGE_PRIVATE_KEY_PATH", ""),
                        vonage_number=os.environ.get("VONAGE_NUMBER", ""),
                        public_base_url=os.environ.get("PUBLIC_BASE_URL", ""),
                    )
                    sms_body = (
                        f"⚡ Empire AI · New lead in {lead.get('city', 'your area')}: "
                        f"{lead.get('address', 'a property')} · "
                        f"urgency {urgency}/10. "
                        f"Accept: {accept_link[:160]} "
                        f"STOP to opt out"
                    )
                    sms_result = await _sms_router.send_sms(contractor["phone"], sms_body)
                    if sms_result.get("ok"):
                        # outreach_log: dispatch event audit
                        db.table("outreach_log").insert({
                            "enriched_lead_id": None,
                            "agent_name": "matching_dispatch_sms",
                            "run_id": str(uuid.uuid4()),
                            "channel": "sms",
                            "sequence": "manual_dispatch",
                            "step": 0,
                            "body_preview": sms_body[:200],
                            "compliance_passed": True,
                            "mode": "live",
                            "sent_at": datetime.now(timezone.utc).isoformat(),
                            "sent_status": "sent",
                            "meta": {"dispatch_id": str(ins.data[0]["id"]) if ins.data else None, "contractor_id": str(contractor["id"])},
                        }).execute()
                        # sms_log: actual SMS audit (for reply rate tracking)
                        db.table("sms_log").insert({
                            "phone":         contractor["phone"],
                            "direction":     "outbound",
                            "body":          sms_body,
                            "step":          0,
                            "message_uuid":  sms_result.get("message_uuid"),
                            "delivered":     True,
                        }).execute()
            except Exception as e:
                log.warning(f"[matching] dispatch SMS failed for {contractor.get('phone')}: {e}")

        # Touch last_dispatched_at for the matched contractors
        try:
            now = datetime.now(timezone.utc).isoformat()
            for entry in matched:
                db.table("contractors").update({
                    "last_dispatched_at": now,
                }).eq("id", entry["contractor"]["id"]).execute()
        except Exception:
            pass

        self.stats["dispatches_sent"] += sent

        # Broadcast to operator dashboard
        if broadcaster:
            try:
                await broadcaster.broadcast({
                    "type":      "dispatch_fanout",
                    "lead_addr": lead.get("address"),
                    "metro":     lead.get("city"),
                    "matches":   len(matched),
                    "sent":      sent,
                    "urgency":   urgency,
                    "top_contractor": matched[0]["contractor"].get("name") if matched else None,
                    "top_score":      round(matched[0]["score"], 3) if matched else 0,
                })
            except Exception:
                pass

        return {
            "ok":            True,
            "dispatched":    sent,
            "dispatch_ids":  dispatch_ids,
            "top_score":     round(matched[0]["score"], 3) if matched else 0,
        }

    # ── PUBLIC: TRUST SCORE UPDATE FROM OUTCOMES ─────────────────────────
    async def update_trust_from_outcome(
        self,
        contractor_id: str,
        outcome: str,
        notes: str = "",
    ) -> dict:
        """
        Adjust a contractor's trust score based on a dispatched job's outcome.
        Call this from the record_outcome handler in hub.py.

        outcome must be one of: completed, settled, ghosted, customer_complaint,
        withdrew, no_show.
        """
        delta = TRUST_DELTA.get(outcome)
        if delta is None:
            log.warning(f"[matching] unknown outcome '{outcome}' — skipping trust update")
            return {"ok": False, "error": "unknown outcome"}

        try:
            db = self.get_db()
            res = db.table("contractors").select("trust_score, completed_jobs, name") \
                .eq("id", contractor_id).limit(1).execute()
            if not res.data:
                return {"ok": False, "error": "contractor not found"}

            current = res.data[0]
            current_trust = float(current.get("trust_score") or TRUST_DEFAULT)
            new_trust = max(TRUST_MIN, min(TRUST_MAX, current_trust + delta))

            update = {"trust_score": round(new_trust, 2)}
            if outcome in ("completed", "settled"):
                update["completed_jobs"] = (current.get("completed_jobs") or 0) + 1

            db.table("contractors").update(update).eq("id", contractor_id).execute()
            self.stats["trust_updates"] += 1

            # Log the change
            try:
                db.table("contractor_trust_log").insert({
                    "contractor_id": contractor_id,
                    "outcome":       outcome,
                    "delta":         delta,
                    "before":        round(current_trust, 2),
                    "after":         round(new_trust, 2),
                    "notes":         notes[:300] if notes else None,
                }).execute()
            except Exception as e:
                log.debug(f"[matching] trust log insert (table may not exist): {e}")

            log.info(
                f"[matching] trust · {current.get('name', '?')} · "
                f"{outcome} · {current_trust:.2f} → {new_trust:.2f}"
            )

            return {
                "ok":        True,
                "before":    round(current_trust, 2),
                "after":     round(new_trust, 2),
                "delta":     delta,
            }
        except Exception as e:
            log.error(f"[matching] trust update failed: {e}")
            return {"ok": False, "error": str(e)}

    # ─────────────────────────────────────────────────────────────────────
    # INTERNALS
    # ─────────────────────────────────────────────────────────────────────
    def _score_contractor(
        self,
        contractor: dict,
        lead_metro: str,
        required_specialties: list[str],
        metro_adjacency: set,
        active_load: int,
    ) -> tuple[float, dict]:
        """Return (total_score, components) for one contractor."""
        # 1. Metro match
        ctr_metro = (contractor.get("metro") or "").strip()
        if not ctr_metro:
            metro_score = 0.0
        elif ctr_metro.lower() == (lead_metro or "").lower():
            metro_score = 1.0
        elif ctr_metro in metro_adjacency:
            metro_score = 0.5
        else:
            metro_score = 0.0

        # 2. Specialty match (Jaccard)
        ctr_specs = set((contractor.get("specialties") or []))
        req_specs = set(required_specialties or [])
        if not req_specs:
            specialty_score = 1.0  # if no specialty required, everyone matches
        elif not ctr_specs:
            specialty_score = 0.0
        else:
            intersection = ctr_specs & req_specs
            union = ctr_specs | req_specs
            specialty_score = len(intersection) / len(union) if union else 0.0

        # 3. Trust score (normalize 0-10 → 0-1)
        trust_raw = float(contractor.get("trust_score") or TRUST_DEFAULT)
        trust_score_norm = max(0.0, min(1.0, trust_raw / TRUST_MAX))

        # 4. Freshness (1.0 if not dispatched in last 14 days → 0 if dispatched today)
        last_dispatched = contractor.get("last_dispatched_at")
        if not last_dispatched:
            freshness = 1.0
        else:
            try:
                if isinstance(last_dispatched, str):
                    last_dt = datetime.fromisoformat(last_dispatched.replace("Z", "+00:00"))
                else:
                    last_dt = last_dispatched
                days_since = (datetime.now(timezone.utc) - last_dt).total_seconds() / 86400
                freshness = max(0.0, min(1.0, days_since / 14.0))
            except Exception:
                freshness = 0.5

        # 5. Capacity (1.0 if idle → 0 if at max)
        max_concurrent = contractor.get("max_concurrent") or DEFAULT_MAX_CONCUR
        capacity = max(0.0, 1.0 - (active_load / max_concurrent)) if max_concurrent else 0.0

        components = {
            "metro_match":     round(metro_score, 3),
            "specialty_match": round(specialty_score, 3),
            "trust_score":     round(trust_score_norm, 3),
            "freshness":       round(freshness, 3),
            "capacity":        round(capacity, 3),
        }

        total = sum(
            components[key] * self.weights[key]
            for key in self.weights
        )
        return round(total, 3), components

    async def _load_adjacency(self, metro: str) -> set:
        """Return the set of metros adjacent to the given one."""
        if not metro:
            return set()
        try:
            db = self.get_db()
            res = db.table("metro_adjacency").select("adjacent_to") \
                .eq("metro", metro).execute()
            return {r["adjacent_to"] for r in (res.data or [])}
        except Exception:
            return set()

    async def _load_active_dispatch_counts(self, contractor_ids: list[str]) -> dict:
        """Return {contractor_id: count_of_open_dispatches}."""
        if not contractor_ids:
            return {}
        try:
            db = self.get_db()
            res = db.table("dispatches").select("contractor_id") \
                .in_("contractor_id", contractor_ids) \
                .in_("status", ["sent", "accepted"]).execute()
            counts: dict[str, int] = {cid: 0 for cid in contractor_ids}
            for row in (res.data or []):
                cid = row["contractor_id"]
                counts[cid] = counts.get(cid, 0) + 1
            return counts
        except Exception as e:
            log.debug(f"[matching] load active counts failed: {e}")
            return {}

    def _render_dispatch_email(
        self,
        contractor: dict,
        lead: dict,
        urgency: int,
        accept_link: str,
        score: float,
    ) -> str:
        """Render the dispatch magic-link email."""
        addr = lead.get("address", "a property in your service area")
        metro = lead.get("city", contractor.get("metro", ""))
        severity = lead.get("damage_severity", "severe")
        name = contractor.get("name", "Contractor")
        first_name = name.split()[0] if name else "there"

        urgency_color = "#f43f5e" if urgency >= 9 else ("#f59e0b" if urgency >= 7 else "#10b981")

        return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#0a0a0a;font-family:-apple-system,system-ui,sans-serif;">
<table cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#0a0a0a;">
<tr><td align="center" style="padding:32px 16px;">
  <table cellpadding="0" cellspacing="0" border="0" width="560" style="max-width:560px;background:#0a0a0a;color:#e4e4e7;">
    <tr><td style="padding-bottom:18px;border-bottom:1px solid #27272a;">
      <div style="font-size:11px;color:#71717a;letter-spacing:.18em;text-transform:uppercase;">Empire AI · Strike Dispatch</div>
      <div style="font-size:24px;font-weight:700;color:{urgency_color};margin-top:6px;letter-spacing:-0.02em;">
        Urgency {urgency}/10 · {metro}
      </div>
    </td></tr>
    <tr><td style="padding:24px 0;">
      <p style="font-size:14px;line-height:1.7;color:#a1a1aa;margin:0 0 14px;">
        Hi {first_name}, a verified strike just landed in your dispatch zone.
        Empire AI's matching engine ranked you in the top 5 for this lead.
      </p>
      <div style="margin:24px 0;padding:18px 20px;background:#15263F;border-left:3px solid #44E5B8;">
        <div style="font-size:11px;color:#71717a;letter-spacing:.18em;text-transform:uppercase;margin-bottom:8px;">Target</div>
        <div style="font-size:16px;color:#f8fafd;font-weight:500;margin-bottom:4px;">{addr}</div>
        <div style="font-size:12px;color:#a1a1aa;">Damage: {severity}</div>
      </div>
      <div style="margin:28px 0;text-align:center;">
        <a href="{accept_link}" style="display:inline-block;background:#44E5B8;color:#000;padding:16px 36px;text-decoration:none;font-weight:700;letter-spacing:.04em;font-size:14px;">
          Accept dispatch &rarr;
        </a>
      </div>
      <p style="font-size:11px;line-height:1.7;color:#71717a;margin:14px 0 0;text-align:center;">
        First contractor to accept wins this dispatch. Link expires in 24 hours.
      </p>
    </td></tr>
    <tr><td style="padding-top:18px;border-top:1px solid #27272a;font-size:10px;color:#52525b;line-height:1.7;">
      Match score: {score:.2f} · You are receiving this because you are an
      active vetted contractor in the Empire AI network. To pause your
      dispatch list temporarily or update your specialties, reply to this email.
    </td></tr>
  </table>
</td></tr>
</table>
</body></html>"""


# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI ROUTES
# ─────────────────────────────────────────────────────────────────────────────
def register_matching_routes(
    app: FastAPI,
    matcher: ContractorMatcher,
    *,
    require_auth: Callable,
    sign_token: Callable,
    verify_token: Callable,
    send_email: Callable,
    broadcaster=None,
    public_base_url: str = "",
):
    """
    Wire matching-related operator endpoints and the public dispatch
    accept route.
    """

    # ── OPERATOR: PREVIEW MATCHES (for a given lead) ───────────────────
    @app.post("/api/v1/matching/preview")
    async def matching_preview(request: Request, auth: bool = Depends(require_auth)):
        """
        Returns the top N matches for a hypothetical lead. Useful for
        operator review before firing dispatch.
        """
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")

        metro = (body.get("metro") or "").strip()
        specialties = body.get("specialties") or []
        top_n = int(body.get("top_n", DEFAULT_TOP_N))

        if not metro:
            raise HTTPException(400, "metro required")

        matched = await matcher.match_for_lead(
            metro=metro,
            required_specialties=specialties,
            top_n=top_n,
        )
        # Strip contractor sensitive fields from the response
        return {
            "matches": [
                {
                    "contractor_id":   m["contractor"]["id"],
                    "contractor_name": m["contractor"].get("name"),
                    "metro":           m["contractor"].get("metro"),
                    "specialties":     m["contractor"].get("specialties"),
                    "trust_score":     m["contractor"].get("trust_score"),
                    "score":           m["score"],
                    "components":      m["components"],
                }
                for m in matched
            ]
        }

    # ── OPERATOR: TRIGGER DISPATCH FAN-OUT MANUALLY ────────────────────
    @app.post("/api/v1/matching/dispatch")
    async def matching_dispatch(request: Request, auth: bool = Depends(require_auth)):
        """
        Manually fire dispatch for a lead. Body: {lead_id, urgency, specialties}.
        """
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")

        lead_id = body.get("lead_id")
        if not lead_id:
            raise HTTPException(400, "lead_id required")

        # Pull the lead from radar_targets
        try:
            db = matcher.get_db()
            res = db.table("radar_targets").select("*") \
                .eq("id", lead_id).limit(1).execute()
            if not res.data:
                raise HTTPException(404, "lead not found")
            lead = res.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"lead query failed: {e}")

        # Run match
        matched = await matcher.match_for_lead(
            metro=lead.get("city") or "",
            required_specialties=body.get("specialties") or [],
            top_n=int(body.get("top_n", DEFAULT_TOP_N)),
        )

        # Look up the SI-chosen strategy + niche from the strike_log so the
        # contractor-dispatch path carries the genome signal end-to-end.
        # Uses the shared StateManager helper (no inline meta-parsing).
        strategy = None
        niche = None
        try:
            from empire_state_manager import StateManager
            _state = StateManager(get_db=matcher.get_db)
            _si = _state.get_strike_strategy(target_id=lead_id)
            strategy = _si.get("strategy")
            niche = _si.get("niche")
        except Exception as e:
            log.debug(f"[matching] strategy lookup failed: {e}")

        # Fan out
        result = await matcher.dispatch_to_matched(
            matched=matched,
            lead=lead,
            urgency=int(body.get("urgency", 7)),
            sign_token=sign_token,
            send_email=send_email,
            public_base_url=public_base_url,
            broadcaster=broadcaster,
            strategy=strategy,
            niche=niche,
        )
        return result

    # ── OPERATOR: STATS SNAPSHOT ───────────────────────────────────────
    @app.get("/api/v1/matching/stats")
    async def matching_stats(auth: bool = Depends(require_auth)):
        return matcher.stats

    # ── OPERATOR: DISPATCHES LIST (for the operator SPA "Dispatches" section) ─
    @app.get("/api/v1/matching/dispatches")
    async def matching_dispatches(
        status: str = "all",
        limit: int = 50,
        auth: bool = Depends(require_auth),
    ):
        """List recent dispatches with status filter. Used by the operator SPA
        "Dispatches" section to render the mark-settled UI."""
        try:
            db = matcher.get_db()
            q = (db.table("dispatches")
                   .select("id, created_at, lead_id, contractor_id, match_score, status, payout_amount, meta, accepted_at, completed_at, ghosted_at")
                   .order("created_at", desc=True)
                   .limit(max(1, min(limit, 500))))
            if status and status != "all":
                q = q.eq("status", status)
            res = q.execute()
            return {"dispatches": res.data or []}
        except Exception as e:
            raise HTTPException(500, str(e))

    # ── OPERATOR: LEADERBOARD ──────────────────────────────────────────
    @app.get("/api/v1/matching/leaderboard")
    async def matching_leaderboard(
        limit: int = Query(20, ge=1, le=100),
        auth: bool = Depends(require_auth),
    ):
        """Top contractors by trust score + completed jobs."""
        try:
            db = matcher.get_db()
            res = db.table("contractors").select(
                "id, name, metro, trust_score, completed_jobs, active, last_dispatched_at, specialties"
            ).eq("active", True).order("trust_score", desc=True).limit(limit).execute()
            return {"contractors": res.data or []}
        except Exception as e:
            raise HTTPException(500, str(e))

    # ── PUBLIC: CONTRACTOR ACCEPTS DISPATCH ─────────────────────────────
    @app.get("/dispatch/accept", response_class=HTMLResponse)
    async def dispatch_accept(t: str = Query(...)):
        """
        Contractor clicks the magic link in the dispatch email. First-come,
        first-served — if another contractor already accepted this lead,
        we show a polite "claimed" page.
        """
        payload = verify_token(t)
        if not payload or payload.get("kind") != "dispatch_accept":
            return HTMLResponse(_dispatch_page(
                "Link invalid",
                "This dispatch link is invalid or has expired.",
                error=True,
            ), status_code=401)

        lead_id       = payload.get("lead_id")
        contractor_id = payload.get("contractor_id")

        try:
            db = matcher.get_db()

            # Look up this specific dispatch by token
            disp_res = db.table("dispatches").select("*") \
                .eq("token", t).limit(1).execute()
            if not disp_res.data:
                return HTMLResponse(_dispatch_page(
                    "Not found",
                    "Dispatch record not found.",
                    error=True,
                ), status_code=404)
            dispatch = disp_res.data[0]

            # Already claimed by SOMEONE?
            claimed = db.table("dispatches").select("contractor_id, status, accepted_at") \
                .eq("lead_id", lead_id) \
                .eq("status", "accepted").limit(1).execute()

            if claimed.data:
                claimed_row = claimed.data[0]
                # Was it claimed by us?
                if claimed_row["contractor_id"] == contractor_id:
                    return HTMLResponse(_dispatch_page(
                        "Already accepted by you",
                        "You already accepted this dispatch. Check your email for next steps.",
                    ))
                # Claimed by someone else
                # Mark our own status as expired so it doesn't show as still-open
                db.table("dispatches").update({"status": "expired"}) \
                    .eq("id", dispatch["id"]).execute()
                return HTMLResponse(_dispatch_page(
                    "Claimed by another contractor",
                    "Another contractor in your network already accepted this dispatch. Keep an eye on your inbox — more will follow.",
                ))

            # Accept it · race-safe by updating only if still 'sent'
            now = datetime.now(timezone.utc).isoformat()
            upd = db.table("dispatches").update({
                "status":      "accepted",
                "accepted_at": now,
            }).eq("id", dispatch["id"]).eq("status", "sent").execute()

            if not upd.data:
                # Someone won the race between our check and update
                return HTMLResponse(_dispatch_page(
                    "Claimed by another contractor",
                    "Another contractor just accepted this dispatch. Keep an eye on your inbox.",
                ))

            # Mark all OTHER dispatches for this lead as expired (lost the race)
            db.table("dispatches").update({"status": "expired"}) \
                .eq("lead_id", lead_id) \
                .eq("status", "sent") \
                .neq("id", dispatch["id"]).execute()

            matcher.stats["dispatches_accepted"] += 1

            # Get the lead for the success page
            lead_res = db.table("radar_targets").select("address, city, phone") \
                .eq("id", lead_id).limit(1).execute()
            lead = lead_res.data[0] if lead_res.data else {}

            # Get the contractor
            ctr_res = db.table("contractors").select("name, email") \
                .eq("id", contractor_id).limit(1).execute()
            contractor = ctr_res.data[0] if ctr_res.data else {}

            # Send a confirmation email with lead contact details
            confirm_html = f"""
              <div style="font-family:system-ui,sans-serif;max-width:560px;margin:0 auto;padding:32px;background:#0a0a0a;color:#e4e4e7;">
                <div style="border-bottom:1px solid #27272a;padding-bottom:16px;margin-bottom:22px;">
                  <div style="font-size:11px;color:#71717a;letter-spacing:.18em;text-transform:uppercase;">Empire AI · Dispatch Confirmed</div>
                  <div style="font-size:22px;font-weight:700;color:#44E5B8;margin-top:6px;">You won the race</div>
                </div>
                <p style="font-size:14px;line-height:1.7;color:#a1a1aa;">
                  You've accepted dispatch on the following lead:
                </p>
                <div style="margin:24px 0;padding:18px 20px;background:#15263F;border-left:3px solid #44E5B8;">
                  <div style="font-size:16px;color:#f8fafd;font-weight:500;margin-bottom:8px;">{lead.get('address', 'Address withheld')}</div>
                  <div style="font-size:13px;color:#a1a1aa;">Metro: {lead.get('city', '')}</div>
                  <div style="font-size:13px;color:#a1a1aa;">Phone: {lead.get('phone', 'see operator')}</div>
                </div>
                <p style="font-size:14px;line-height:1.7;color:#a1a1aa;">
                  Next steps:
                </p>
                <ol style="font-size:14px;line-height:1.8;color:#a1a1aa;padding-left:20px;">
                  <li>Reach out to the property owner within 4 hours</li>
                  <li>Schedule on-site assessment ASAP — 72hr insurance window</li>
                  <li>Mark complete via your contractor portal once done</li>
                  <li>Empire's 3% fee + your share triggers on settled claim</li>
                </ol>
              </div>
            """
            try:
                await send_email(
                    to=contractor.get("email", ""),
                    subject=f"Empire AI · Dispatch confirmed · {lead.get('address', 'lead')}",
                    html=confirm_html,
                )
            except Exception:
                pass

            # Push to operator dashboard
            if broadcaster:
                try:
                    await broadcaster.broadcast({
                        "type":            "dispatch_accepted",
                        "contractor":      contractor.get("name"),
                        "lead_addr":       lead.get("address"),
                        "metro":           lead.get("city"),
                        "match_score":     dispatch.get("match_score"),
                    })
                except Exception:
                    pass

            return HTMLResponse(_dispatch_page(
                "Dispatch accepted",
                f"You won this dispatch. Check your inbox for the property owner's contact details and next steps. Move fast — the 72-hour insurance documentation window is open.",
            ))
        except Exception as e:
            log.error(f"[matching] accept failed: {e}")
            return HTMLResponse(_dispatch_page(
                "Error",
                "Could not process your acceptance. Please contact ops@empire-ai.co.uk",
                error=True,
            ), status_code=500)

    log.info("[matching] Routes registered · /dispatch/accept · /api/v1/matching/{preview,dispatch,stats,leaderboard}")


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC DISPATCH ACCEPTANCE PAGE (Empire-styled)
# ─────────────────────────────────────────────────────────────────────────────
def _dispatch_page(title: str, message: str, *, error: bool = False) -> str:
    color = "#f43f5e" if error else "#44E5B8"
    icon  = "✗" if error else "✓"
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Empire AI · Dispatch</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@200;400;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: #0A1A2F; color: #F8FAFD;
  font-family: 'Inter', -apple-system, sans-serif; letter-spacing: -0.02em;
  min-height: 100vh; padding: 60px 20px;
  display: flex; align-items: center; justify-content: center;
}}
.box {{
  max-width: 480px; width: 100%;
  background: #15263F; border: 1px solid rgba(122,140,163,0.18);
  padding: 40px 36px; text-align: center;
}}
.brand {{
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px; color: #7A8CA3;
  letter-spacing: 0.32em; text-transform: uppercase; margin-bottom: 24px;
}}
.icon {{
  font-size: 48px; color: {color}; margin-bottom: 18px;
}}
h1 {{
  font-weight: 200; font-size: 26px;
  letter-spacing: -0.04em; margin-bottom: 14px;
  color: #F8FAFD;
}}
p {{
  font-size: 14px; color: #C8D4E4;
  line-height: 1.7;
}}
</style></head><body>
<div class="box">
  <div class="brand">Empire AI · Strike Dispatch</div>
  <div class="icon">{icon}</div>
  <h1>{title}</h1>
  <p>{message}</p>
</div>
</body></html>"""
