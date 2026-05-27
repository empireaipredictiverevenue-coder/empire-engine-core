"""
EMPIRE V49 · OPERATOR DAILY PLAYBOOK
======================================
The morning view. The operator opens this once per day, works through
the prioritized task list, and the empire moves forward. Replaces the
"stare at the dashboard and guess what to do next" problem.

Four panels, each ranked, each actionable:

  1. 🔥 HOTTEST LEADS — top 10 by urgency × freshness × asset value
                      → click → SMS now, call now, dispatch now

  2. 📞 5-MIN TASKS  — discrete actions completable in <5 min each
                     → callbacks owed, dispatches awaiting accept,
                       contractor applications pending review

  3. ⏱  TIME DECAY   — leads aging out of the 72-hour insurance window
                     → 0-24h, 24-48h, 48-72h, EXPIRING SOON

  4. 🚨 ANOMALIES   — things that shouldn't be true:
                     → SMS sequences stalled for >24h
                     → dispatches accepted but not completed in 7+ days
                     → contractors ghosting (accepted but never updated)
                     → high-asset leads with no outreach yet

Wire-up in hub.py:

    from empire_playbook import register_playbook_routes, playbook_view

    register_playbook_routes(app, require_auth=require_auth, get_db=get_db)

    @app.get("/view/playbook", response_class=HTMLResponse)
    async def view_playbook(token: str = Query("")):
        return HTMLResponse(playbook_view(token=token))

Add to MODULES in empire_layout.py (insert before sovereign):

    ("playbook", "10", "Daily Playbook", "ti-list-check", False),
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Callable

from fastapi import FastAPI, Depends, HTTPException, Query


log = logging.getLogger("empire.playbook")


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
HOT_LEAD_LOOKBACK_HOURS    = 72        # leads stay "hot" for 72h after scrape
HOT_LEAD_LIMIT             = 10
TASK_QUEUE_LIMIT           = 20
TIME_DECAY_BUCKETS_HOURS   = [24, 48, 72]
ANOMALY_STALLED_SMS_HOURS  = 24
ANOMALY_GHOSTED_DAYS       = 7
ANOMALY_HIGH_ASSET_USD     = 1_000_000


# ─────────────────────────────────────────────────────────────────────────────
# API · the four data endpoints powering the view
# ─────────────────────────────────────────────────────────────────────────────
def register_playbook_routes(
    app: FastAPI,
    *,
    require_auth: Callable,
    get_db: Callable,
):
    """Wire the operator playbook data endpoints."""

    # ── HOTTEST LEADS ────────────────────────────────────────────────────
    @app.get("/api/v1/playbook/hot-leads")
    async def hot_leads(
        limit: int = Query(HOT_LEAD_LIMIT, ge=1, le=50),
        auth: bool = Depends(require_auth),
    ):
        """
        Top leads ranked by composite hot-score:
            urgency × freshness × log(asset_value)

        urgency:    radar_targets.urgency_score (1-10)
        freshness:  1.0 at scrape, decays linearly to 0 over 72h
        asset:      log10(asset_value) clipped to [0, 8]

        Returns each lead with the contributing components so the operator
        can see WHY it's hot.
        """
        try:
            db = get_db()
        except Exception as e:
            raise HTTPException(503, f"DB unavailable: {e}")

        since = (datetime.now(timezone.utc) - timedelta(hours=HOT_LEAD_LOOKBACK_HOURS)).isoformat()

        try:
            res = db.table("radar_targets").select(
                "id, address, phone, email, city, damage_severity, "
                "urgency_score, created_at, meta, status"
            ) \
                .eq("status", "active") \
                .gte("created_at", since) \
                .order("created_at", desc=True) \
                .limit(200).execute()
            leads = res.data or []
        except Exception as e:
            raise HTTPException(500, f"radar_targets query failed: {e}")

        # Pull which leads already have outreach in flight
        try:
            sms_res = db.table("sms_sequences").select("phone, status") \
                .in_("status", ["active", "replied"]) \
                .gte("created_at", since).execute()
            sms_by_phone = {r["phone"]: r["status"] for r in (sms_res.data or [])}
        except Exception:
            sms_by_phone = {}

        try:
            email_res = db.table("email_sequences").select("email, status") \
                .in_("status", ["active", "replied"]) \
                .gte("created_at", since).execute()
            email_by_addr = {r["email"]: r["status"] for r in (email_res.data or [])}
        except Exception:
            email_by_addr = {}

        # Pull dispatches in flight
        try:
            disp_res = db.table("dispatches").select("lead_id, status") \
                .in_("status", ["sent", "accepted"]) \
                .gte("created_at", since).execute()
            dispatches_by_lead: dict[str, list[str]] = {}
            for d in (disp_res.data or []):
                lid = d.get("lead_id")
                if lid:
                    dispatches_by_lead.setdefault(lid, []).append(d["status"])
        except Exception:
            dispatches_by_lead = {}

        # Score each lead
        import math
        now = datetime.now(timezone.utc)
        scored = []
        for lead in leads:
            urgency = float(lead.get("urgency_score") or 5)

            try:
                created = lead["created_at"]
                if isinstance(created, str):
                    created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                else:
                    created_dt = created
                age_hours = (now - created_dt).total_seconds() / 3600
            except Exception:
                age_hours = 0

            freshness = max(0.0, 1.0 - (age_hours / HOT_LEAD_LOOKBACK_HOURS))

            meta = lead.get("meta") or {}
            asset_value = 0
            for k in ("asset_value", "estimated_value", "peak_wind_kmh"):
                if k in meta and meta[k]:
                    try:
                        asset_value = float(meta[k])
                        break
                    except Exception:
                        pass

            # log10 normalized to 0-1 (cap at $100M which gives log = 8)
            asset_factor = min(1.0, max(0.0, math.log10(max(1, asset_value)) / 8.0))

            # Composite hot-score · 50% urgency, 30% freshness, 20% asset
            hot_score = (urgency / 10) * 0.5 + freshness * 0.3 + asset_factor * 0.2

            # Bonus: penalize if outreach already in flight
            phone = lead.get("phone") or ""
            email = lead.get("email") or ""
            sms_status     = sms_by_phone.get(phone, "")
            email_status   = email_by_addr.get(email, "")
            dispatch_count = len(dispatches_by_lead.get(lead.get("id"), []))
            already_in_flight = bool(sms_status or email_status or dispatch_count)

            if already_in_flight:
                hot_score *= 0.7  # de-prioritize but don't hide

            scored.append({
                "id":              lead.get("id"),
                "address":         lead.get("address"),
                "phone":           phone,
                "email":           email,
                "city":            lead.get("city"),
                "damage_severity": lead.get("damage_severity"),
                "urgency":         urgency,
                "age_hours":       round(age_hours, 1),
                "asset_value":     asset_value,
                "hot_score":       round(hot_score, 3),
                "components": {
                    "urgency_norm": round(urgency / 10, 2),
                    "freshness":    round(freshness, 2),
                    "asset":        round(asset_factor, 2),
                },
                "outreach_status": {
                    "sms":          sms_status or None,
                    "email":        email_status or None,
                    "dispatches":   dispatch_count,
                },
                "already_in_flight": already_in_flight,
            })

        scored.sort(key=lambda x: x["hot_score"], reverse=True)
        return {"leads": scored[:limit]}

    # ── 5-MIN TASKS ──────────────────────────────────────────────────────
    @app.get("/api/v1/playbook/tasks")
    async def tasks(
        limit: int = Query(TASK_QUEUE_LIMIT, ge=1, le=100),
        auth: bool = Depends(require_auth),
    ):
        """
        Discrete < 5-minute tasks the operator can knock out one at a time.

        Categories:
          1. Contractor applications pending review
          2. SMS replies awaiting human follow-up
          3. Dispatches sent but not accepted in 12+ hours
          4. Voice messages from inbound calls (if recordings enabled)
          5. Outcomes pending operator confirmation
        """
        try:
            db = get_db()
        except Exception as e:
            raise HTTPException(503, f"DB unavailable: {e}")

        tasks_out = []

        # Category 1: Contractor applications pending review
        try:
            res = db.table("contractor_applications").select(
                "id, name, email, metro, specialties, created_at"
            ) \
                .eq("status", "pending_review") \
                .order("created_at", desc=False) \
                .limit(10).execute()
            for app_row in (res.data or []):
                tasks_out.append({
                    "category":     "contractor_review",
                    "category_label": "Review contractor application",
                    "priority":     "high",
                    "title":        f"Review: {app_row.get('name')}",
                    "subtitle":     f"{app_row.get('metro')} · {len(app_row.get('specialties') or [])} specialties",
                    "ref_id":       app_row["id"],
                    "ref_type":     "contractor_application",
                    "action_url":   f"/view/contractors/applications#{app_row['id']}",
                    "created_at":   app_row.get("created_at"),
                })
        except Exception as e:
            log.debug(f"[playbook] contractor apps query: {e}")

        # Category 2: SMS replies awaiting human follow-up
        try:
            res = db.table("sms_sequences").select(
                "id, phone, target_addr, last_sent_at, replies_count, status"
            ) \
                .eq("status", "replied") \
                .order("last_sent_at", desc=True) \
                .limit(15).execute()
            for seq in (res.data or []):
                tasks_out.append({
                    "category":     "sms_reply",
                    "category_label": "Follow up on SMS reply",
                    "priority":     "urgent",
                    "title":        f"Reply from {seq.get('phone')}",
                    "subtitle":     f"{seq.get('target_addr') or 'Unknown property'} · {seq.get('replies_count') or 1} reply",
                    "ref_id":       seq["id"],
                    "ref_type":     "sms_sequence",
                    "action_url":   f"/view/sms/conversation?phone={seq.get('phone')}",
                    "created_at":   seq.get("last_sent_at"),
                })
        except Exception as e:
            log.debug(f"[playbook] sms replies query: {e}")

        # Category 3: Dispatches sent but not accepted in 12+ hours
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
            res = db.table("dispatches").select(
                "id, lead_id, contractor_id, created_at, status, match_score"
            ) \
                .eq("status", "sent") \
                .lte("created_at", cutoff) \
                .order("created_at", desc=False) \
                .limit(10).execute()
            for disp in (res.data or []):
                tasks_out.append({
                    "category":     "dispatch_stale",
                    "category_label": "Dispatch waiting · resend or escalate",
                    "priority":     "medium",
                    "title":        f"Dispatch unaccepted (score {disp.get('match_score', '?')})",
                    "subtitle":     "Consider widening match radius or re-fanning",
                    "ref_id":       disp["id"],
                    "ref_type":     "dispatch",
                    "action_url":   f"/api/v1/matching/dispatch (resend with top_n=10)",
                    "created_at":   disp.get("created_at"),
                })
        except Exception as e:
            log.debug(f"[playbook] stale dispatch query: {e}")

        # Category 4: Dispatches accepted but not marked complete in 5+ days
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
            res = db.table("dispatches").select(
                "id, contractor_id, accepted_at"
            ) \
                .eq("status", "accepted") \
                .lte("accepted_at", cutoff) \
                .order("accepted_at", desc=False) \
                .limit(10).execute()
            for disp in (res.data or []):
                tasks_out.append({
                    "category":     "contractor_check_in",
                    "category_label": "Check in with contractor · job status",
                    "priority":     "medium",
                    "title":        "Contractor check-in needed",
                    "subtitle":     "Accepted 5+ days ago · no completion update",
                    "ref_id":       disp["id"],
                    "ref_type":     "dispatch",
                    "action_url":   "/view/contractors#leaderboard",
                    "created_at":   disp.get("accepted_at"),
                })
        except Exception as e:
            log.debug(f"[playbook] check-in query: {e}")

        # Category 5: Outcomes pending operator confirmation
        try:
            res = db.table("claim_outcomes").select(
                "id, target_addr, outcome, created_at"
            ) \
                .eq("outcome", "pending") \
                .order("created_at", desc=True) \
                .limit(5).execute()
            for o in (res.data or []):
                tasks_out.append({
                    "category":     "outcome_pending",
                    "category_label": "Confirm claim outcome",
                    "priority":     "medium",
                    "title":        f"Outcome pending · {o.get('target_addr')}",
                    "subtitle":     "Mark settled, denied, or withdrawn",
                    "ref_id":       o["id"],
                    "ref_type":     "claim_outcome",
                    "action_url":   "/view/calibration",
                    "created_at":   o.get("created_at"),
                })
        except Exception as e:
            log.debug(f"[playbook] pending outcomes query: {e}")

        # Priority sort then return
        priority_rank = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
        tasks_out.sort(key=lambda t: (priority_rank.get(t["priority"], 9), t.get("created_at") or ""))
        return {
            "count": len(tasks_out),
            "tasks": tasks_out[:limit],
        }

    # ── TIME DECAY ───────────────────────────────────────────────────────
    @app.get("/api/v1/playbook/time-decay")
    async def time_decay(auth: bool = Depends(require_auth)):
        """
        How many active leads sit in each decay bucket?
        Buckets: 0-24h, 24-48h, 48-72h, EXPIRING_SOON, EXPIRED.

        Expiring soon = 60-72h old. Expired = >72h.
        """
        try:
            db = get_db()
        except Exception as e:
            raise HTTPException(503, f"DB unavailable: {e}")

        now = datetime.now(timezone.utc)
        windows = [
            ("0-24h",          0,  24, "ok"),
            ("24-48h",        24,  48, "ok"),
            ("48-60h",        48,  60, "warn"),
            ("expiring_soon", 60,  72, "alert"),
            ("expired_72h+",  72, None, "critical"),
        ]

        result = []
        # Pull active leads created in the last 7 days
        try:
            since = (now - timedelta(days=7)).isoformat()
            res = db.table("radar_targets").select(
                "id, address, city, created_at, urgency_score"
            ) \
                .eq("status", "active") \
                .gte("created_at", since) \
                .execute()
            leads = res.data or []
        except Exception as e:
            log.error(f"[playbook] time-decay query: {e}")
            leads = []

        # Bucket each lead
        bucket_counts = {w[0]: 0 for w in windows}
        bucket_samples = {w[0]: [] for w in windows}

        for lead in leads:
            try:
                created = lead["created_at"]
                if isinstance(created, str):
                    created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                else:
                    created_dt = created
                age_hours = (now - created_dt).total_seconds() / 3600
            except Exception:
                continue

            for label, lo, hi, _ in windows:
                if age_hours >= lo and (hi is None or age_hours < hi):
                    bucket_counts[label] += 1
                    if len(bucket_samples[label]) < 5:
                        bucket_samples[label].append({
                            "address":  lead.get("address"),
                            "city":     lead.get("city"),
                            "urgency":  lead.get("urgency_score"),
                            "age_hours": round(age_hours, 1),
                        })
                    break

        for label, lo, hi, severity in windows:
            result.append({
                "bucket":   label,
                "lo_hours": lo,
                "hi_hours": hi,
                "count":    bucket_counts[label],
                "severity": severity,
                "samples":  bucket_samples[label],
            })

        return {"buckets": result, "total_active": sum(bucket_counts.values())}

    # ── ANOMALIES ────────────────────────────────────────────────────────
    @app.get("/api/v1/playbook/anomalies")
    async def anomalies(auth: bool = Depends(require_auth)):
        """
        Surface things that shouldn't be true. The "is anything broken?" panel.
        """
        try:
            db = get_db()
        except Exception as e:
            raise HTTPException(503, f"DB unavailable: {e}")

        found = []

        # A1: SMS sequences stalled — active but no send in 24h+
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=ANOMALY_STALLED_SMS_HOURS)).isoformat()
            res = db.table("sms_sequences").select("id, phone, last_sent_at, current_step, status") \
                .eq("status", "active") \
                .lte("last_sent_at", cutoff) \
                .limit(10).execute()
            for r in (res.data or []):
                found.append({
                    "type":     "stalled_sms_sequence",
                    "severity": "warn",
                    "title":    "SMS sequence stalled",
                    "detail":   f"{r['phone']} · step {r['current_step']} · last sent {r['last_sent_at']}",
                    "ref_id":   r["id"],
                })
        except Exception as e:
            log.debug(f"[playbook] stalled SMS: {e}")

        # A2: Ghosted contractors — accepted 7+ days ago, no completion
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=ANOMALY_GHOSTED_DAYS)).isoformat()
            res = db.table("dispatches").select("id, contractor_id, accepted_at, lead_id") \
                .eq("status", "accepted") \
                .lte("accepted_at", cutoff) \
                .limit(10).execute()
            for r in (res.data or []):
                found.append({
                    "type":     "ghosted_contractor",
                    "severity": "alert",
                    "title":    "Contractor ghosting",
                    "detail":   f"Accepted {ANOMALY_GHOSTED_DAYS}+ days ago · no completion",
                    "ref_id":   r["id"],
                })
        except Exception as e:
            log.debug(f"[playbook] ghosted dispatches: {e}")

        # A3: High-asset leads with zero outreach attempted
        try:
            since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            res = db.table("radar_targets").select(
                "id, address, city, phone, email, meta, urgency_score"
            ) \
                .eq("status", "active") \
                .gte("created_at", since) \
                .limit(50).execute()

            sms_phones = set()
            email_addrs = set()
            try:
                s_res = db.table("sms_sequences").select("phone") \
                    .gte("created_at", since).execute()
                sms_phones = {r["phone"] for r in (s_res.data or [])}
            except Exception:
                pass
            try:
                e_res = db.table("email_sequences").select("email") \
                    .gte("created_at", since).execute()
                email_addrs = {r["email"] for r in (e_res.data or [])}
            except Exception:
                pass

            for lead in (res.data or []):
                meta = lead.get("meta") or {}
                asset_value = 0
                for k in ("asset_value", "estimated_value"):
                    if k in meta and meta[k]:
                        try:
                            asset_value = float(meta[k])
                            break
                        except Exception:
                            pass
                if asset_value < ANOMALY_HIGH_ASSET_USD:
                    continue
                phone = lead.get("phone") or ""
                email = lead.get("email") or ""
                if phone in sms_phones or email in email_addrs:
                    continue
                found.append({
                    "type":     "high_asset_no_outreach",
                    "severity": "alert",
                    "title":    f"$1M+ lead with no outreach",
                    "detail":   f"{lead.get('address')} · {lead.get('city')} · ${asset_value:,.0f}",
                    "ref_id":   lead["id"],
                })
        except Exception as e:
            log.debug(f"[playbook] high-asset check: {e}")

        # A4: Email bounce rate spike (>5% in last 24h)
        try:
            since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            sent_res = db.table("email_log").select("id", count="exact") \
                .eq("direction", "outbound") \
                .gte("created_at", since).execute()
            bounce_res = db.table("email_log").select("id", count="exact") \
                .eq("direction", "bounce") \
                .gte("created_at", since).execute()
            sent_count = sent_res.count or 0
            bounce_count = bounce_res.count or 0
            if sent_count >= 20 and bounce_count / sent_count > 0.05:
                found.append({
                    "type":     "email_bounce_spike",
                    "severity": "critical",
                    "title":    f"Email bounce rate {bounce_count/sent_count*100:.1f}%",
                    "detail":   f"{bounce_count} bounces out of {sent_count} sends · check Resend dashboard",
                    "ref_id":   "email_log",
                })
        except Exception as e:
            log.debug(f"[playbook] bounce check: {e}")

        # A5: Subconscious mind silent — no strikes in 30+ min during business hours
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
            res = db.table("strike_log").select("id", count="exact") \
                .gte("created_at", cutoff).execute()
            recent_strikes = res.count or 0
            # Only flag during NWS-active hours (US daytime roughly 12-04 UTC)
            now_utc_hour = datetime.now(timezone.utc).hour
            if recent_strikes == 0 and 12 <= now_utc_hour <= 4:
                pass  # don't flag — could just be quiet weather
        except Exception:
            pass

        severity_rank = {"critical": 0, "alert": 1, "warn": 2, "info": 3}
        found.sort(key=lambda a: severity_rank.get(a["severity"], 9))

        return {"count": len(found), "anomalies": found}

    # ── PLAYBOOK SUMMARY (single endpoint for the top stat strip) ────────
    @app.get("/api/v1/playbook/summary")
    async def playbook_summary(auth: bool = Depends(require_auth)):
        """Single endpoint returning the top-strip numbers."""
        try:
            db = get_db()
        except Exception as e:
            raise HTTPException(503, f"DB unavailable: {e}")

        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

        # Today's strikes
        try:
            res = db.table("strike_log").select("id", count="exact") \
                .gte("created_at", today_start).execute()
            strikes_today = res.count or 0
        except Exception:
            strikes_today = 0

        # Today's GO decisions
        try:
            res = db.table("brain_decisions").select("id", count="exact") \
                .eq("decision", "GO") \
                .gte("created_at", today_start).execute()
            go_today = res.count or 0
        except Exception:
            go_today = 0

        # Today's dispatches accepted
        try:
            res = db.table("dispatches").select("id", count="exact") \
                .eq("status", "accepted") \
                .gte("accepted_at", today_start).execute()
            accepted_today = res.count or 0
        except Exception:
            accepted_today = 0

        # Today's settled outcomes
        try:
            res = db.table("claim_outcomes").select("actual_fee") \
                .eq("outcome", "settled") \
                .gte("created_at", today_start).execute()
            settled_rows = res.data or []
            fees_today = sum(float(r.get("actual_fee") or 0) for r in settled_rows)
        except Exception:
            fees_today = 0

        return {
            "today": {
                "strikes":   strikes_today,
                "brain_go":  go_today,
                "accepted":  accepted_today,
                "fees":      round(fees_today, 2),
            },
        }


# ─────────────────────────────────────────────────────────────────────────────
# VIEW · the operator's morning page
# ─────────────────────────────────────────────────────────────────────────────
def playbook_view(token: str = "") -> str:
    """Render the /view/playbook page."""
    from empire_layout import base_layout
    from empire_live import LIVE_CLIENT_JS

    extra_css = """
    /* Layout */
    .pb-grid {
      display: grid;
      grid-template-columns: 1.5fr 1fr;
      gap: 14px;
      margin-bottom: 16px;
    }
    @media (max-width: 1100px) { .pb-grid { grid-template-columns: 1fr; } }

    /* Today strip */
    .today-strip {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin-bottom: 18px;
    }
    @media (max-width: 800px) {
      .today-strip { grid-template-columns: repeat(2, 1fr); }
    }

    /* Hot lead card */
    .hot-lead {
      padding: 14px 16px;
      background: var(--empire-elevated);
      border-left: 3px solid;
      margin-bottom: 8px;
      transition: transform 0.2s var(--ease-snap);
      cursor: pointer;
    }
    .hot-lead:hover {
      transform: translateX(2px);
      background: rgba(26, 45, 74, 0.95);
    }
    .hot-lead.tier-1 { border-left-color: var(--signal-teal); }
    .hot-lead.tier-2 { border-left-color: var(--strike-cyan); }
    .hot-lead.tier-3 { border-left-color: var(--status-amber); }
    .hot-lead.in-flight {
      opacity: 0.55;
      border-left-color: var(--empire-shadow);
    }

    .hot-lead-top {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 4px;
    }
    .hot-lead-rank {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--signal-teal);
      font-weight: 700;
      letter-spacing: 0.1em;
      flex-shrink: 0;
      min-width: 28px;
    }
    .hot-lead-name {
      font-family: var(--font-ui);
      font-size: 13px;
      font-weight: 500;
      color: var(--empire-white);
      letter-spacing: -0.01em;
      flex: 1;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .hot-lead-score {
      font-family: var(--font-mono);
      font-size: 13px;
      color: var(--signal-teal);
      font-weight: 600;
      flex-shrink: 0;
    }
    .hot-lead-meta {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-mist);
      letter-spacing: 0.05em;
      margin-top: 4px;
    }
    .hot-lead-meta .sep { color: var(--empire-shadow); padding: 0 5px; }
    .hot-lead-actions {
      display: flex;
      gap: 6px;
      margin-top: 8px;
    }
    .hot-lead-actions .pill {
      font-family: var(--font-mono);
      font-size: 9px;
      letter-spacing: 0.14em;
      padding: 3px 9px;
      border: 1px solid var(--empire-border);
      color: var(--empire-mist);
      text-transform: uppercase;
      background: rgba(0,0,0,0.2);
    }
    .hot-lead-actions .pill.active {
      color: var(--signal-teal);
      border-color: rgba(68,229,184,0.3);
      background: rgba(68,229,184,0.06);
    }

    /* Task row */
    .task-row {
      display: grid;
      grid-template-columns: 14px 1fr auto;
      gap: 10px;
      align-items: center;
      padding: 10px 12px;
      background: var(--empire-elevated);
      border-left: 2px solid;
      margin-bottom: 6px;
      transition: all 0.2s var(--ease-snap);
    }
    .task-row:hover { background: rgba(26, 45, 74, 0.95); }
    .task-row.priority-urgent { border-left-color: var(--status-red); }
    .task-row.priority-high   { border-left-color: var(--status-amber); }
    .task-row.priority-medium { border-left-color: var(--strike-cyan); }
    .task-row.priority-low    { border-left-color: var(--empire-fog); }

    .task-icon {
      width: 14px;
      text-align: center;
      font-family: var(--font-mono);
      font-size: 11px;
    }
    .priority-urgent .task-icon { color: var(--status-red); }
    .priority-high   .task-icon { color: var(--status-amber); }
    .priority-medium .task-icon { color: var(--strike-cyan); }

    .task-body { min-width: 0; }
    .task-title {
      font-size: 12px;
      color: var(--empire-white);
      letter-spacing: -0.01em;
      font-weight: 500;
      margin-bottom: 2px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .task-sub {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-mist);
      letter-spacing: 0.05em;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .task-cta {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-mist);
      letter-spacing: 0.1em;
      text-transform: uppercase;
      padding: 5px 10px;
      border: 1px solid var(--empire-border);
      background: transparent;
      cursor: pointer;
      transition: all 0.2s;
    }
    .task-cta:hover {
      color: var(--signal-teal);
      border-color: var(--signal-teal);
    }

    /* Time decay buckets */
    .decay-grid {
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 8px;
      margin-bottom: 8px;
    }
    @media (max-width: 600px) { .decay-grid { grid-template-columns: repeat(2, 1fr); } }

    .decay-bucket {
      padding: 12px 10px;
      background: var(--empire-elevated);
      border-top: 3px solid;
      text-align: center;
      transition: transform 0.2s;
    }
    .decay-bucket:hover { transform: translateY(-2px); }
    .decay-bucket.ok       { border-top-color: var(--signal-teal); }
    .decay-bucket.warn     { border-top-color: var(--status-amber); }
    .decay-bucket.alert    { border-top-color: var(--status-amber); }
    .decay-bucket.critical { border-top-color: var(--status-red); }

    .decay-count {
      font-family: var(--font-mono);
      font-size: 24px;
      font-weight: 600;
      letter-spacing: -0.04em;
      line-height: 1;
    }
    .decay-bucket.ok       .decay-count { color: var(--empire-white); }
    .decay-bucket.warn     .decay-count,
    .decay-bucket.alert    .decay-count { color: var(--status-amber); }
    .decay-bucket.critical .decay-count { color: var(--status-red); }

    .decay-label {
      font-family: var(--font-mono);
      font-size: 9px;
      color: var(--empire-mist);
      letter-spacing: 0.18em;
      text-transform: uppercase;
      margin-top: 6px;
    }

    /* Anomaly row */
    .anomaly {
      padding: 11px 14px;
      background: rgba(245, 166, 35, 0.04);
      border-left: 3px solid var(--status-amber);
      margin-bottom: 6px;
      animation: empire-fade-up 0.3s var(--ease-out-empire) both;
    }
    .anomaly.severity-critical {
      background: rgba(255, 71, 87, 0.05);
      border-left-color: var(--status-red);
    }
    .anomaly.severity-warn {
      background: rgba(122, 140, 163, 0.04);
      border-left-color: var(--empire-mist);
    }
    .anomaly-title {
      font-size: 12px;
      font-weight: 500;
      color: var(--empire-white);
      letter-spacing: -0.01em;
      margin-bottom: 3px;
    }
    .anomaly-detail {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-mist);
      letter-spacing: 0.04em;
    }

    .empty-state {
      padding: 32px 18px;
      text-align: center;
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-fog);
      letter-spacing: 0.18em;
      text-transform: uppercase;
    }

    .panel-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 14px;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--empire-divider);
    }
    """

    content = """
    <div class="e-page">
      <div class="e-page-header">
        <div>
          <div class="e-page-title">Daily <em>Playbook</em></div>
          <div class="e-page-sub">Operator Mode · Today's Tasks · Open This Every Morning</div>
        </div>
        <div style="display:flex; gap:10px; align-items:center;">
          <span class="e-stat-label" id="last-refresh">—</span>
          <button class="e-btn-ghost" onclick="loadAll()">Refresh</button>
        </div>
      </div>

      <!-- TODAY STRIP -->
      <div class="today-strip">
        <div class="e-stat teal">
          <div class="e-stat-label">Strikes today</div>
          <div class="e-stat-value teal" id="today-strikes">—</div>
          <div class="e-stat-delta">verified hits</div>
        </div>
        <div class="e-stat cyan">
          <div class="e-stat-label">Brain GO today</div>
          <div class="e-stat-value" id="today-go">—</div>
          <div class="e-stat-delta">decisions</div>
        </div>
        <div class="e-stat amber">
          <div class="e-stat-label">Dispatches accepted</div>
          <div class="e-stat-value amber" id="today-accepted">—</div>
          <div class="e-stat-delta">contractors</div>
        </div>
        <div class="e-stat teal">
          <div class="e-stat-label">Fees today</div>
          <div class="e-stat-value teal" id="today-fees">$0</div>
          <div class="e-stat-delta up">settled</div>
        </div>
      </div>

      <!-- TIME DECAY -->
      <div class="e-panel">
        <div class="panel-head">
          <span class="e-section-label" style="margin-bottom:0;">⏱ Time Decay · 72-hour Insurance Window</span>
          <span class="e-stat-label" id="decay-total">— active</span>
        </div>
        <div class="decay-grid" id="decay-grid">
          <div class="decay-bucket ok"><div class="decay-count">—</div><div class="decay-label">0-24h</div></div>
          <div class="decay-bucket ok"><div class="decay-count">—</div><div class="decay-label">24-48h</div></div>
          <div class="decay-bucket warn"><div class="decay-count">—</div><div class="decay-label">48-60h</div></div>
          <div class="decay-bucket alert"><div class="decay-count">—</div><div class="decay-label">60-72h</div></div>
          <div class="decay-bucket critical"><div class="decay-count">—</div><div class="decay-label">Expired</div></div>
        </div>
      </div>

      <!-- HOT LEADS + TASKS -->
      <div class="pb-grid">
        <!-- HOT LEADS -->
        <div class="e-panel">
          <div class="panel-head">
            <span class="e-section-label" style="margin-bottom:0;">🔥 Hottest Leads · Top 10</span>
            <span class="e-stat-label">urgency × freshness × asset</span>
          </div>
          <div id="hot-leads">
            <div class="empty-state">Loading hot leads...</div>
          </div>
        </div>

        <!-- 5-MIN TASKS -->
        <div class="e-panel">
          <div class="panel-head">
            <span class="e-section-label" style="margin-bottom:0;">📋 5-min Tasks</span>
            <span class="e-stat-label" id="tasks-count">—</span>
          </div>
          <div id="tasks-list">
            <div class="empty-state">Loading task queue...</div>
          </div>
        </div>
      </div>

      <!-- ANOMALIES -->
      <div class="e-panel">
        <div class="panel-head">
          <span class="e-section-label" style="margin-bottom:0;">🚨 Anomalies · Things to Fix</span>
          <span class="e-stat-label" id="anomalies-count">—</span>
        </div>
        <div id="anomalies-list">
          <div class="empty-state">Scanning for anomalies...</div>
        </div>
      </div>
    </div>
    """

    extra_js = LIVE_CLIENT_JS + """
    <script>
    (function() {
      const TOKEN = window.EMPIRE_TOKEN;

      const fmtMoney = n => n != null ? '$' + Math.round(Number(n)).toLocaleString() : '$0';
      const fmtNum   = n => n != null ? Number(n).toLocaleString() : '0';
      const truncate = (s, n) => s && s.length > n ? s.slice(0, n) + '...' : (s || '');

      async function loadSummary() {
        try {
          const r = await fetch('/api/v1/playbook/summary', {
            headers: { Authorization: 'Bearer ' + TOKEN }
          });
          if (!r.ok) return;
          const d = await r.json();
          const t = d.today || {};
          document.getElementById('today-strikes').textContent  = fmtNum(t.strikes);
          document.getElementById('today-go').textContent       = fmtNum(t.brain_go);
          document.getElementById('today-accepted').textContent = fmtNum(t.accepted);
          document.getElementById('today-fees').textContent     = fmtMoney(t.fees);
        } catch (e) {}
      }

      async function loadHotLeads() {
        try {
          const r = await fetch('/api/v1/playbook/hot-leads?limit=10', {
            headers: { Authorization: 'Bearer ' + TOKEN }
          });
          if (!r.ok) throw new Error('HTTP ' + r.status);
          const d = await r.json();
          renderHotLeads(d.leads || []);
        } catch (e) {
          document.getElementById('hot-leads').innerHTML =
            '<div class="empty-state">Could not load · ' + e.message + '</div>';
        }
      }

      function renderHotLeads(leads) {
        const container = document.getElementById('hot-leads');
        if (!leads.length) {
          container.innerHTML = '<div class="empty-state">No active leads in the 72hr window</div>';
          return;
        }
        container.innerHTML = leads.map((lead, idx) => {
          const tier = idx < 3 ? 'tier-1' : (idx < 6 ? 'tier-2' : 'tier-3');
          const dim  = lead.already_in_flight ? ' in-flight' : '';
          const status = lead.outreach_status || {};
          const pills = [];
          if (status.sms)        pills.push(`<span class="pill active">SMS · ${status.sms}</span>`);
          if (status.email)      pills.push(`<span class="pill active">EMAIL · ${status.email}</span>`);
          if (status.dispatches) pills.push(`<span class="pill active">DISPATCH × ${status.dispatches}</span>`);
          if (!pills.length)     pills.push(`<span class="pill">UNTOUCHED</span>`);

          const assetStr = lead.asset_value ? `· ${fmtMoney(lead.asset_value)}` : '';
          return `
            <div class="hot-lead ${tier}${dim}" onclick="window.open('/api/lead/${lead.id}', '_blank')">
              <div class="hot-lead-top">
                <span class="hot-lead-rank">${String(idx+1).padStart(2,'0')}</span>
                <span class="hot-lead-name">${truncate(lead.address, 40)}</span>
                <span class="hot-lead-score">${lead.hot_score.toFixed(2)}</span>
              </div>
              <div class="hot-lead-meta">
                ${lead.city || 'Unknown'}<span class="sep">·</span>
                urg ${lead.urgency}/10<span class="sep">·</span>
                ${lead.age_hours.toFixed(1)}h old
                ${assetStr}
              </div>
              <div class="hot-lead-actions">${pills.join('')}</div>
            </div>
          `;
        }).join('');
      }

      async function loadTasks() {
        try {
          const r = await fetch('/api/v1/playbook/tasks?limit=20', {
            headers: { Authorization: 'Bearer ' + TOKEN }
          });
          if (!r.ok) throw new Error('HTTP ' + r.status);
          const d = await r.json();
          renderTasks(d.tasks || [], d.count || 0);
        } catch (e) {
          document.getElementById('tasks-list').innerHTML =
            '<div class="empty-state">Could not load · ' + e.message + '</div>';
        }
      }

      function renderTasks(tasks, count) {
        document.getElementById('tasks-count').textContent =
          count > 0 ? `${count} pending` : 'all clear';
        const container = document.getElementById('tasks-list');
        if (!tasks.length) {
          container.innerHTML = '<div class="empty-state">Nothing in the queue · close empire</div>';
          return;
        }
        const icons = {
          urgent: '!', high: '⚠', medium: '·', low: '○',
        };
        container.innerHTML = tasks.map(t => `
          <div class="task-row priority-${t.priority}">
            <div class="task-icon">${icons[t.priority] || '·'}</div>
            <div class="task-body">
              <div class="task-title">${t.title}</div>
              <div class="task-sub">${t.category_label} · ${t.subtitle}</div>
            </div>
            <button class="task-cta" onclick="window.open('${t.action_url}', '_blank')">Open</button>
          </div>
        `).join('');
      }

      async function loadDecay() {
        try {
          const r = await fetch('/api/v1/playbook/time-decay', {
            headers: { Authorization: 'Bearer ' + TOKEN }
          });
          if (!r.ok) throw new Error('HTTP ' + r.status);
          const d = await r.json();
          renderDecay(d.buckets || [], d.total_active || 0);
        } catch (e) {}
      }

      function renderDecay(buckets, total) {
        document.getElementById('decay-total').textContent = `${total} active`;
        const grid = document.getElementById('decay-grid');
        const labelMap = {
          '0-24h': '0-24h',
          '24-48h': '24-48h',
          '48-60h': '48-60h',
          'expiring_soon': '60-72h',
          'expired_72h+': 'EXPIRED',
        };
        grid.innerHTML = buckets.map(b => `
          <div class="decay-bucket ${b.severity}">
            <div class="decay-count">${fmtNum(b.count)}</div>
            <div class="decay-label">${labelMap[b.bucket] || b.bucket}</div>
          </div>
        `).join('');
      }

      async function loadAnomalies() {
        try {
          const r = await fetch('/api/v1/playbook/anomalies', {
            headers: { Authorization: 'Bearer ' + TOKEN }
          });
          if (!r.ok) throw new Error('HTTP ' + r.status);
          const d = await r.json();
          renderAnomalies(d.anomalies || [], d.count || 0);
        } catch (e) {}
      }

      function renderAnomalies(anomalies, count) {
        document.getElementById('anomalies-count').textContent =
          count > 0 ? `${count} detected` : 'all green';
        const container = document.getElementById('anomalies-list');
        if (!anomalies.length) {
          container.innerHTML = '<div class="empty-state">✓ Nothing weird · system healthy</div>';
          return;
        }
        container.innerHTML = anomalies.map(a => `
          <div class="anomaly severity-${a.severity}">
            <div class="anomaly-title">${a.title}</div>
            <div class="anomaly-detail">${a.detail}</div>
          </div>
        `).join('');
      }

      async function loadAll() {
        await Promise.all([
          loadSummary(),
          loadHotLeads(),
          loadTasks(),
          loadDecay(),
          loadAnomalies(),
        ]);
        const now = new Date();
        const t = now.toTimeString().slice(0, 8);
        document.getElementById('last-refresh').textContent = `refreshed ${t}`;
      }

      // Reload on real-time events
      if (window.EMPIRE_LIVE) {
        ['strike','brain','settlement','dispatch_fanout','dispatch_accepted'].forEach(evt => {
          window.EMPIRE_LIVE.on(evt, () => loadAll());
        });
      }

      loadAll();
      setInterval(loadAll, 60000); // refresh every minute
    })();
    </script>
    """

    return base_layout(
        title="Daily Playbook",
        subtitle="Operator Mode",
        content=content,
        active_module="playbook",
        extra_css=extra_css,
        extra_js=extra_js,
    )
