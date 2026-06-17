"""
EMPIRE V49 · COMPLIANCE MONITOR AGENT
=======================================
Autonomous compliance enforcement agent. Runs real-time TCPA/DNC/CCPA checks
on every outbound channel (SMS, voice, email), tracks consent lifecycle,
and generates violation alerts with severity scoring.

This agent wraps the existing compliance infrastructure:
  - agents/outreach/compliance.py  → per-message gate (opt-out, DNC, consent, quiet hours, rate)
  - compliance.py                  → deterministic rules engine (homeowner, billing, domain, scraping)
  - products/compliant.py          → productized compliance-as-a-service

And adds:
  - Unified compliance dashboard across all channels
  - Consent lifecycle tracking (granted, revoked, expired)
  - Violation detection with severity scoring (info/warn/critical)
  - Real-time alert generation
  - Compliance audit trail

Fleet parent: sales_director
Routes:
  GET    /api/compliance/overview      — Compliance dashboard snapshot
  GET    /api/compliance/check          — Run real-time compliance check
  GET    /api/compliance/history        — Compliance check history
  GET    /api/compliance/alerts         — Active violation alerts
  POST   /api/compliance/alert/ack      — Acknowledge/resolve an alert
  POST   /api/compliance/opt-out        — Register an opt-out
  GET    /api/compliance/consent        — Consent tracking by channel/niche
  GET    /api/compliance/audit          — Full compliance audit trail
  GET    /api/compliance/snapshot       — Condensed fleet snapshot
"""

import json
import logging
import os
import uuid
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable

log = logging.getLogger("empire.compliance_monitor")

# ── Severity levels for violations ─────────────────────────────────
ALERT_SEVERITIES = ["info", "warning", "critical"]

# ── Compliance check source mapping ────────────────────────────────
CHANNEL_TYPES = {
    "sms":   "outbound_sms",
    "voice": "outbound_call",
    "email": "outbound_email",
    "all":   "multi_channel",
}

# ── Consent status lifecycle ───────────────────────────────────────
CONSENT_STATES = [
    "unknown",         # No consent data
    "granted",         # Explicit consent given
    "implied",         # Existing business relationship
    "expired",         # Consent past its TTL
    "revoked",         # Opted out / withdrew consent
]

# ── CCPA-specific rights ───────────────────────────────────────────
CCPA_RIGHTS = [
    "right_to_know",       # What data is collected
    "right_to_delete",     # Delete my data
    "right_to_opt_out",    # Opt out of sale/sharing
    "right_to_correct",    # Correct inaccurate data
    "right_to_portability", # Data portability
]


class ComplianceMonitor:
    """Autonomous compliance enforcement agent.

    Three core capabilities:
      1. Real-time TCPA/DNC/CCPA checks across all outbound channels
      2. Consent lifecycle tracking with expiry and revocation
      3. Violation detection with severity scoring and alert generation
    """

    def __init__(self, get_db: Callable):
        self.get_db = get_db
        self._check_history: list[dict] = []     # compliance check log
        self._alerts: list[dict] = []             # active violation alerts
        self._consent_log: list[dict] = []        # consent lifecycle events
        self._audit_trail: list[dict] = []        # full audit events

    def _db(self):
        return self.get_db()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _days_ago(self, d: int) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=d)).isoformat()

    # ── INTERNAL COMPLIANCE ENGINE ──────────────────────────────────
    # Wraps agents/outreach/compliance.py and compliance.py

    def _check_opt_out(self, phone: str) -> dict:
        """Check if a phone is in sms_opt_outs."""
        try:
            from agents.outreach.compliance import is_opted_out
            opted_out = is_opted_out(phone)
            return {"blocked": opted_out, "reason": "opted_out" if opted_out else ""}
        except (ImportError, AttributeError):
            return {"blocked": False, "reason": "", "note": "compliance gate not loaded"}

    def _check_dnc(self, phone: str) -> dict:
        """Check if a phone is on the DNC list."""
        try:
            from agents.outreach.compliance import is_on_dnc
            on_dnc = is_on_dnc(phone)
            return {"blocked": on_dnc, "reason": "on_dnc" if on_dnc else ""}
        except (ImportError, AttributeError):
            return {"blocked": False, "reason": "", "note": "compliance gate not loaded"}

    def _check_consent(self, consent_flag: Optional[bool]) -> dict:
        """Check if consent is explicitly granted."""
        try:
            from agents.outreach.compliance import has_consent
            granted = has_consent(consent_flag)
            return {"blocked": not granted, "reason": "no_consent" if not granted else "",
                    "consent_granted": granted, "consent_flag": consent_flag}
        except (ImportError, AttributeError):
            return {"blocked": False, "reason": "", "consent_granted": True,
                    "note": "compliance gate not loaded"}

    def _check_quiet_hours(self, area_code: str = "") -> dict:
        """Check if it's quiet hours in the recipient's timezone."""
        try:
            from agents.outreach.compliance import is_quiet_hours
            quiet = is_quiet_hours(area_code)
            return {"blocked": quiet, "reason": "quiet_hours" if quiet else "",
                    "quiet_hours": quiet}
        except (ImportError, AttributeError):
            return {"blocked": False, "reason": "", "quiet_hours": False,
                    "note": "compliance gate not loaded"}

    def _check_rate_limit(self, phone: str) -> dict:
        """Check per-number daily rate limit."""
        try:
            from agents.outreach.compliance import can_send_today
            can_send = can_send_today(phone)
            return {"blocked": not can_send, "reason": "rate_limited" if not can_send else "",
                    "can_send_today": can_send}
        except (ImportError, AttributeError):
            return {"blocked": False, "reason": "", "can_send_today": True,
                    "note": "compliance gate not loaded"}

    def _check_rules_engine(self, action_type: str, payload: Optional[dict] = None) -> dict:
        """Check against the deterministic compliance rules engine."""
        try:
            import compliance as rules
            result = rules.check(action_type, payload or {})
            return {
                "blocked": not result.get("allowed", True),
                "rule": result.get("rule", "none"),
                "reason": result.get("reason", ""),
                "allowed": result.get("allowed", True),
            }
        except (ImportError, AttributeError):
            return {"blocked": False, "rule": "none", "reason": "",
                    "note": "rules engine not loaded"}

    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone to 11 digits for consistent lookup."""
        import re
        digits = re.sub(r"\D", "", phone or "")
        if len(digits) >= 11 and digits.startswith("1"):
            return digits[-11:]
        if len(digits) == 10:
            return "1" + digits
        return digits

    def _extract_area_code(self, phone: str) -> str:
        """Extract 3-digit area code from a phone number."""
        n = self._normalize_phone(phone)
        return n[2:5] if len(n) >= 11 else (n[:3] if len(n) >= 3 else "")

    # ── 1. SINGLE COMPLIANCE CHECK ──────────────────────────────────

    def run_check(
        self,
        phone: str = "",
        email: str = "",
        channel: str = "sms",
        consent_flag: Optional[bool] = None,
        action_type: str = "outreach",
        payload: Optional[dict] = None,
        niche: str = "",
        record: bool = True,
    ) -> dict:
        """Run a comprehensive compliance check across all layers.

        Combines:
          1. Deterministic rules (homeowner, billing, domain, scraping)
          2. Opt-out registry check
          3. DNC list check
          4. Consent check
          5. Quiet hours check
          6. Rate limit check

        Returns full check result with per-layer breakdown.
        """
        area_code = self._extract_area_code(phone) if phone else ""
        check_id = f"CMP-{uuid.uuid4().hex[:8].upper()}"
        ts = self._now()

        # Layer 1: Rules engine
        rules_result = self._check_rules_engine(action_type, payload)

        # Layer 2-6: Outreach compliance (phone-based)
        opt_out_result = self._check_opt_out(phone) if phone else {"blocked": False, "reason": "", "skipped": True}
        dnc_result = self._check_dnc(phone) if phone else {"blocked": False, "reason": "", "skipped": True}
        consent_result = self._check_consent(consent_flag)
        quiet_hours_result = self._check_quiet_hours(area_code) if phone else {"blocked": False, "reason": "", "skipped": True}
        rate_limit_result = self._check_rate_limit(phone) if phone else {"blocked": False, "reason": "", "skipped": True}

        # Combine: blocked if ANY layer blocks
        blocked = (
            rules_result.get("blocked", False)
            or opt_out_result.get("blocked", False)
            or dnc_result.get("blocked", False)
            or consent_result.get("blocked", False)
            or quiet_hours_result.get("blocked", False)
            or rate_limit_result.get("blocked", False)
        )

        # Determine blocking reason
        block_reason = ""
        if rules_result.get("blocked"):
            block_reason = rules_result.get("rule", "rules_blocked")
        elif opt_out_result.get("blocked"):
            block_reason = "opted_out"
        elif dnc_result.get("blocked"):
            block_reason = "on_dnc"
        elif consent_result.get("blocked"):
            block_reason = "no_consent"
        elif quiet_hours_result.get("blocked"):
            block_reason = "quiet_hours"
        elif rate_limit_result.get("blocked"):
            block_reason = "rate_limited"

        # Compute severity
        severity = self._compute_severity(blocked, block_reason)

        result = {
            "check_id": check_id,
            "timestamp": ts,
            "channel": channel,
            "phone": phone,
            "email": email,
            "niche": niche or "unknown",
            "action_type": action_type,
            "blocked": blocked,
            "block_reason": block_reason,
            "severity": severity,
            "layers": {
                "rules_engine": rules_result,
                "opt_out": opt_out_result,
                "dnc": dnc_result,
                "consent": consent_result,
                "quiet_hours": quiet_hours_result,
                "rate_limit": rate_limit_result,
            },
            "verdict": "BLOCK" if blocked else "ALLOW",
        }

        if record:
            self._check_history.append(result)
            # Generate alert if blocked
            if blocked:
                self._generate_alert(result)
            # Log to audit trail
            self._audit("compliance_check", {
                "check_id": check_id,
                "channel": channel,
                "phone": phone,
                "blocked": blocked,
                "block_reason": block_reason,
                "severity": severity,
            })

        return result

    def _compute_severity(self, blocked: bool, reason: str) -> str:
        if not blocked:
            return "info"
        if reason in ("opted_out", "on_dnc"):
            return "critical"  # Sending to opted-out/DNC is a TCPA violation
        if reason in ("no_consent",):
            return "critical"  # No consent is serious
        if reason in ("quiet_hours",):
            return "warning"   # Time-of-day violation
        if reason in ("rate_limited",):
            return "warning"
        if reason in ("rules_blocked",):
            return "critical"
        return "warning"

    # ── 2. VIOLATION ALERTS ─────────────────────────────────────────

    def _generate_alert(self, check_result: dict) -> dict:
        """Generate a violation alert from a blocked compliance check."""
        alert = {
            "alert_id": f"ALERT-{uuid.uuid4().hex[:8].upper()}",
            "timestamp": self._now(),
            "check_id": check_result.get("check_id", ""),
            "severity": check_result.get("severity", "warning"),
            "channel": check_result.get("channel", "unknown"),
            "phone": check_result.get("phone", ""),
            "niche": check_result.get("niche", "unknown"),
            "block_reason": check_result.get("block_reason", ""),
            "verdict": check_result.get("verdict", "BLOCK"),
            "status": "open",
            "acknowledged_at": None,
            "acknowledged_by": None,
            "resolved_at": None,
        }
        self._alerts.append(alert)

        # Log critical alerts to the DB for persistence
        if alert["severity"] == "critical":
            self._persist_alert(alert)

        return alert

    def _persist_alert(self, alert: dict) -> None:
        """Persist critical alerts to Supabase compliance_alerts table."""
        try:
            db = self._db()
            db.table("compliance_alerts").upsert({
                "alert_id": alert["alert_id"],
                "check_id": alert["check_id"],
                "severity": alert["severity"],
                "channel": alert["channel"],
                "phone": alert["phone"],
                "niche": alert["niche"],
                "block_reason": alert["block_reason"],
                "status": "open",
                "created_at": alert["timestamp"],
            }, on_conflict="alert_id").execute()
        except Exception as e:
            log.debug(f"[compliance] persist alert failed: {e}")

    def acknowledge_alert(self, alert_id: str, acknowledged_by: str = "operator") -> dict:
        """Acknowledge and optionally resolve a violation alert."""
        for a in self._alerts:
            if a.get("alert_id") == alert_id:
                a["status"] = "acknowledged"
                a["acknowledged_at"] = self._now()
                a["acknowledged_by"] = acknowledged_by
                self._audit("alert_acknowledged", {
                    "alert_id": alert_id,
                    "acknowledged_by": acknowledged_by,
                })
                return {"ok": True, "alert_id": alert_id, "status": "acknowledged"}
        return {"ok": False, "error": f"Alert {alert_id} not found"}

    def resolve_alert(self, alert_id: str) -> dict:
        """Mark a violation alert as resolved (action taken)."""
        for a in self._alerts:
            if a.get("alert_id") == alert_id:
                a["status"] = "resolved"
                a["resolved_at"] = self._now()
                self._audit("alert_resolved", {
                    "alert_id": alert_id,
                })
                return {"ok": True, "alert_id": alert_id, "status": "resolved"}
        return {"ok": False, "error": f"Alert {alert_id} not found"}

    def get_alerts(self, severity: str = "", status: str = "", limit: int = 50) -> dict:
        """Get active violation alerts, optionally filtered."""
        alerts = self._alerts
        if severity:
            alerts = [a for a in alerts if a.get("severity") == severity]
        if status:
            alerts = [a for a in alerts if a.get("status") == status]

        alerts.sort(key=lambda a: a.get("timestamp", ""), reverse=True)

        critical = [a for a in alerts if a.get("severity") == "critical"]
        warnings = [a for a in alerts if a.get("severity") == "warning"]
        info = [a for a in alerts if a.get("severity") == "info"]
        open_alerts = [a for a in alerts if a.get("status") == "open"]

        return {
            "ts": self._now(),
            "total": len(alerts),
            "critical_count": len(critical),
            "warning_count": len(warnings),
            "info_count": len(info),
            "open_count": len(open_alerts),
            "alerts": alerts[:limit],
            "severity_filter": severity or "all",
            "status_filter": status or "all",
        }

    # ── 3. CONSENT TRACKING ─────────────────────────────────────────

    def track_consent(self, phone: str = "", email: str = "",
                       channel: str = "sms", state: str = "granted",
                       source: str = "operator", notes: str = "") -> dict:
        """Record a consent lifecycle event."""
        event = {
            "consent_id": f"CNST-{uuid.uuid4().hex[:8].upper()}",
            "timestamp": self._now(),
            "phone": phone,
            "email": email,
            "channel": channel,
            "previous_state": "unknown",
            "new_state": state,
            "source": source,
            "notes": notes,
        }

        # Find previous state for this contact+channel
        for ev in reversed(self._consent_log):
            if ev.get("phone") == phone and ev.get("channel") == channel:
                event["previous_state"] = ev.get("new_state", "unknown")
                break

        self._consent_log.append(event)
        self._audit("consent_change", event)

        return event

    def get_consent_status(self, phone: str = "", email: str = "",
                            channel: str = "") -> dict:
        """Get current consent status for a contact."""
        status = {
            "phone": phone,
            "email": email,
            "overall": "unknown",
            "by_channel": {},
            "events_count": 0,
        }

        # Filter consent events for this contact
        events = []
        for ev in self._consent_log:
            if (phone and ev.get("phone") == phone) or (email and ev.get("email") == email):
                events.append(ev)

        status["events_count"] = len(events)

        # Get latest state per channel
        channels_seen = {}
        for ev in reversed(events):
            ch = ev.get("channel", "unknown")
            if ch not in channels_seen:
                channels_seen[ch] = ev.get("new_state", "unknown")

        status["by_channel"] = channels_seen

        # Overall: if any channel is "revoked", overall is revoked
        if any(s == "revoked" for s in channels_seen.values()):
            status["overall"] = "revoked"
        elif any(s == "granted" for s in channels_seen.values()):
            status["overall"] = "granted"
        elif any(s == "implied" for s in channels_seen.values()):
            status["overall"] = "implied"
        elif any(s == "expired" for s in channels_seen.values()):
            status["overall"] = "expired"
        elif events:
            status["overall"] = list(channels_seen.values())[0]

        # Check DB for persisted opt-outs
        if phone:
            opt_out = self._check_opt_out(phone)
            if opt_out.get("blocked"):
                status["overall"] = "revoked"
                status["db_opt_out"] = True

        return status

    def consent_summary(self) -> dict:
        """Aggregate consent stats across all tracked contacts."""
        total_events = len(self._consent_log)
        by_state = {}
        by_channel = {}

        for ev in self._consent_log:
            state = ev.get("new_state", "unknown")
            by_state[state] = by_state.get(state, 0) + 1

            ch = ev.get("channel", "unknown")
            by_channel[ch] = by_channel.get(ch, 0) + 1

        # Unique contacts
        unique_phones = set(ev.get("phone") for ev in self._consent_log if ev.get("phone"))
        unique_emails = set(ev.get("email") for ev in self._consent_log if ev.get("email"))

        return {
            "ts": self._now(),
            "total_events": total_events,
            "unique_contacts": len(unique_phones | unique_emails),
            "unique_phones": len(unique_phones),
            "unique_emails": len(unique_emails),
            "by_state": by_state,
            "by_channel": by_channel,
            "revoked_count": by_state.get("revoked", 0),
            "granted_count": by_state.get("granted", 0),
        }

    # ── 4. AUDIT TRAIL ──────────────────────────────────────────────

    def _audit(self, action: str, details: dict) -> None:
        """Record an audit event."""
        entry = {
            "audit_id": f"AUD-{uuid.uuid4().hex[:8].upper()}",
            "timestamp": self._now(),
            "action": action,
            "details": details,
            "source": "compliance_monitor",
        }
        self._audit_trail.append(entry)

        # Persist to DB
        try:
            db = self._db()
            db.table("compliance_audit_logs").insert({
                "action": action,
                "entity_type": "compliance_check",
                "entity_id": details.get("check_id", details.get("alert_id", "")),
                "details": details,
                "created_at": self._now(),
            }).execute()
        except Exception as e:
            log.debug(f"[compliance] audit persist failed: {e}")

    def get_audit_trail(self, action: str = "", limit: int = 50) -> dict:
        """Get compliance audit trail, optionally filtered by action."""
        entries = self._audit_trail
        if action:
            entries = [e for e in entries if e.get("action") == action]
        entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)

        # Also fetch from DB for historical data
        db_entries = []
        try:
            q = self._db().table("compliance_audit_logs") \
                .select("*") \
                .eq("entity_type", "compliance_check") \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()
            db_entries = q.data or []
        except Exception:
            pass

        return {
            "ts": self._now(),
            "in_memory": len(entries[:limit]),
            "db_entries": len(db_entries),
            "total": len(entries) + len(db_entries),
            "entries": entries[:limit],
            "filter": action or "all",
        }

    # ── 5. CCPA COMPLIANCE ──────────────────────────────────────────

    def ccpa_check(self, phone: str = "", email: str = "",
                    right: str = "right_to_know") -> dict:
        """Check CCPA compliance status for a contact."""
        consent = self.get_consent_status(phone=phone, email=email)

        return {
            "ts": self._now(),
            "phone": phone,
            "email": email,
            "right_requested": right,
            "right_description": {
                "right_to_know": "Right to know what personal data is collected",
                "right_to_delete": "Right to request deletion of personal data",
                "right_to_opt_out": "Right to opt out of sale/sharing of personal data",
                "right_to_correct": "Right to correct inaccurate personal data",
                "right_to_portability": "Right to receive personal data in portable format",
            }.get(right, "Unknown right"),
            "consent_status": consent.get("overall", "unknown"),
            "can_process": consent.get("overall") != "revoked",
            "action_required": right in ("right_to_delete", "right_to_opt_out"),
        }

    # ── 6. COMPLIANCE DASHBOARD ─────────────────────────────────────

    def compliance_overview(self) -> dict:
        """Full compliance dashboard — check volume, alert stats, consent summary."""
        total_checks = len(self._check_history)
        blocked_checks = [c for c in self._check_history if c.get("blocked")]
        allowed_checks = [c for c in self._check_history if not c.get("blocked")]

        # Check volume by channel
        by_channel = {}
        for c in self._check_history:
            ch = c.get("channel", "unknown")
            if ch not in by_channel:
                by_channel[ch] = {"total": 0, "blocked": 0, "allowed": 0}
            by_channel[ch]["total"] += 1
            if c.get("blocked"):
                by_channel[ch]["blocked"] += 1
            else:
                by_channel[ch]["allowed"] += 1

        # Block reasons breakdown
        block_reasons = {}
        for c in blocked_checks:
            reason = c.get("block_reason", "unknown")
            block_reasons[reason] = block_reasons.get(reason, 0) + 1

        # Alert summary
        open_critical = len([a for a in self._alerts
                             if a["severity"] == "critical" and a["status"] == "open"])
        open_warnings = len([a for a in self._alerts
                             if a["severity"] == "warning" and a["status"] == "open"])

        # Fetch DB snapshot for dashboard
        db_stats = {}
        try:
            db = self._db()
            now = datetime.now(timezone.utc)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

            # Blocked today from DB
            r = db.table("compliance_audit_logs").select("count", count="exact") \
                .eq("action", "outbound_call_blocked") \
                .gte("created_at", today_start) \
                .execute()
            db_stats["blocked_today_db"] = getattr(r, "count", 0)

            # DNC/opt-out counts
            r = db.table("sms_opt_outs").select("count", count="exact").limit(1).execute()
            db_stats["sms_opt_outs"] = getattr(r, "count", 0)

            r = db.table("outbound_dnc").select("count", count="exact").limit(1).execute()
            db_stats["outbound_dnc"] = getattr(r, "count", 0)
        except Exception:
            pass

        return {
            "ts": self._now(),
            "checks": {
                "total": total_checks,
                "blocked": len(blocked_checks),
                "allowed": len(allowed_checks),
                "block_rate_pct": round(len(blocked_checks) / max(total_checks, 1) * 100, 1),
                "by_channel": by_channel,
                "block_reasons": block_reasons,
            },
            "alerts": {
                "total": len(self._alerts),
                "open_critical": open_critical,
                "open_warnings": open_warnings,
                "resolved": len([a for a in self._alerts if a["status"] == "resolved"]),
            },
            "consent": self.consent_summary(),
            "db_snapshot": db_stats,
            "health": "critical" if open_critical > 0 else (
                "warning" if open_warnings > 0 else "ok"
            ),
        }

    def check_history(self, limit: int = 50) -> dict:
        """Recent compliance check history."""
        checks = sorted(self._check_history,
                        key=lambda c: c.get("timestamp", ""), reverse=True)
        recent = checks[:limit]
        blocked = [c for c in recent if c.get("blocked")]
        return {
            "ts": self._now(),
            "recent": recent,
            "blocked_in_window": len(blocked),
            "total_available": len(self._check_history),
        }

    def run_multi_channel_check(self, phone: str = "",
                                 email: str = "",
                                 consent_flag: Optional[bool] = None,
                                 niche: str = "") -> dict:
        """Run compliance checks across all outbound channels (SMS + voice + email)."""
        results = {}
        all_blocked = False
        for channel in ["sms", "voice", "email"]:
            payload = {"channel": channel, "target_type": "business"}
            result = self.run_check(
                phone=phone, email=email, channel=channel,
                consent_flag=consent_flag,
                action_type="outreach",
                payload=payload, niche=niche,
                record=True,
            )
            results[channel] = result
            if result.get("blocked"):
                all_blocked = True

        return {
            "ts": self._now(),
            "phone": phone,
            "email": email,
            "all_channels_blocked": all_blocked,
            "some_channels_blocked": any(r.get("blocked") for r in results.values()),
            "results": results,
        }

    # ── SNAPSHOT ─────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Condensed fleet snapshot."""
        overview = self.compliance_overview()
        return {
            "checks_total": overview.get("checks", {}).get("total", 0),
            "blocked_total": overview.get("checks", {}).get("blocked", 0),
            "block_rate_pct": overview.get("checks", {}).get("block_rate_pct", 0),
            "open_critical": overview.get("alerts", {}).get("open_critical", 0),
            "open_warnings": overview.get("alerts", {}).get("open_warnings", 0),
            "alerts_total": overview.get("alerts", {}).get("total", 0),
            "consent_events": overview.get("consent", {}).get("total_events", 0),
            "health": overview.get("health", "ok"),
            "modified": self._now(),
        }


# ── FASTAPI ROUTES ──────────────────────────────────────────────────────

def register_compliance_routes(app, get_db=None, require_auth=None):
    """Register Compliance Monitor routes on a FastAPI app."""
    from fastapi import Depends, HTTPException, Query

    if get_db is None:
        log.warning("[compliance] No get_db — agent will return errors on DB calls")
    _cm = ComplianceMonitor(get_db=get_db) if get_db else None

    def _get_cm():
        if _cm is None:
            raise HTTPException(503, "Compliance Monitor not initialized (no get_db)")
        return _cm

    @app.get("/api/compliance/overview")
    async def compliance_overview(auth=Depends(require_auth) if require_auth else None):
        """Compliance dashboard — check volume, alert stats, consent summary."""
        return _get_cm().compliance_overview()

    @app.get("/api/compliance/check")
    async def compliance_run_check(
        phone: str = Query("", description="Phone number to check"),
        email: str = Query("", description="Email to check"),
        channel: str = Query("sms", description="Channel: sms|voice|email|all"),
        consent: Optional[bool] = Query(None, description="TCPA consent flag"),
        action_type: str = Query("outreach", description="Action type"),
        niche: str = Query("", description="Lead niche"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Run a real-time compliance check across all layers."""
        cm = _get_cm()
        if channel == "all":
            return cm.run_multi_channel_check(
                phone=phone, email=email, consent_flag=consent, niche=niche,
            )
        payload = {"channel": channel, "target_type": "business"}
        return cm.run_check(
            phone=phone, email=email, channel=channel,
            consent_flag=consent, action_type=action_type,
            payload=payload, niche=niche, record=True,
        )

    @app.get("/api/compliance/history")
    async def compliance_history(
        limit: int = Query(50, ge=1, le=200),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Recent compliance check history."""
        return _get_cm().check_history(limit=limit)

    @app.get("/api/compliance/alerts")
    async def compliance_alerts(
        severity: str = Query("", description="Filter: info|warning|critical"),
        status: str = Query("", description="Filter: open|acknowledged|resolved"),
        limit: int = Query(50, ge=1, le=200),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Active violation alerts."""
        return _get_cm().get_alerts(severity=severity, status=status, limit=limit)

    @app.post("/api/compliance/alert/ack")
    async def compliance_alert_ack(
        alert_id: str = Query("", description="Alert ID to acknowledge"),
        acknowledged_by: str = Query("operator", description="Who acknowledged"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Acknowledge a violation alert."""
        result = _get_cm().acknowledge_alert(alert_id, acknowledged_by)
        status = 200 if result.get("ok") else 404
        return result

    @app.post("/api/compliance/alert/resolve")
    async def compliance_alert_resolve(
        alert_id: str = Query("", description="Alert ID to resolve"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Resolve a violation alert (action taken)."""
        result = _get_cm().resolve_alert(alert_id)
        status = 200 if result.get("ok") else 404
        return result

    @app.post("/api/compliance/opt-out")
    async def compliance_register_opt_out(
        phone: str = Query("", description="Phone to opt out"),
        reason: str = Query("user request", description="Opt-out reason"),
        channel: str = Query("sms", description="Channel opting out from"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Register an opt-out for a phone number."""
        cm = _get_cm()

        # Track consent change
        cm.track_consent(phone=phone, channel=channel, state="revoked",
                         source="opt_out", notes=reason)

        # Register via compliance gate
        try:
            from agents.outreach.compliance import register_opt_out
            result = register_opt_out(phone, reason)
            if result:
                return {
                    "ok": True,
                    "phone": phone,
                    "reason": reason,
                    "consent_state": "revoked",
                    "note": "Phone opted out via compliance gate — removed from all active sequences",
                }
        except (ImportError, AttributeError):
            pass

        # Fallback: write directly to sms_opt_outs if compliance gate unavailable
        try:
            db = self._db()
            db.table("sms_opt_outs").upsert({
                "phone": phone,
                "reason": reason,
                "created_at": self._now(),
            }, on_conflict="phone").execute()
            log.warning(f"[compliance] opt-out persisted directly to sms_opt_outs (gate unavailable): {phone}")
            return {
                "ok": True,
                "phone": phone,
                "reason": reason,
                "consent_state": "revoked",
                "note": "Phone opted out via direct DB write (compliance gate was unavailable)",
                "fallback": "direct_db",
            }
        except Exception as e:
            log.warning(f"[compliance] opt-out fallback failed: {e}")
            return {
                "ok": True,
                "phone": phone,
                "reason": reason,
                "consent_state": "revoked",
                "note": "Consent tracked in memory only — DB write failed. Data will be lost on restart.",
                "warning": "opt-out not persisted to database",
            }

    @app.get("/api/compliance/consent")
    async def compliance_consent(
        phone: str = Query("", description="Phone to check consent for"),
        email: str = Query("", description="Email to check consent for"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Consent tracking by contact."""
        return _get_cm().get_consent_status(phone=phone, email=email)

    @app.get("/api/compliance/consent/summary")
    async def compliance_consent_summary(auth=Depends(require_auth) if require_auth else None):
        """Aggregate consent stats."""
        return _get_cm().consent_summary()

    @app.get("/api/compliance/ccpa")
    async def compliance_ccpa(
        phone: str = Query("", description="Phone for CCPA check"),
        email: str = Query("", description="Email for CCPA check"),
        right: str = Query("right_to_know", description="CCPA right to check"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """CCPA compliance status for a contact."""
        return _get_cm().ccpa_check(phone=phone, email=email, right=right)

    @app.get("/api/compliance/audit")
    async def compliance_audit(
        action: str = Query("", description="Filter by action type"),
        limit: int = Query(50, ge=1, le=200),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Full compliance audit trail."""
        return _get_cm().get_audit_trail(action=action, limit=limit)

    @app.get("/api/compliance/snapshot")
    async def compliance_snapshot(auth=Depends(require_auth) if require_auth else None):
        """Condensed snapshot for fleet dashboard."""
        return _get_cm().snapshot()

    log.info("[compliance] Routes registered · /api/compliance/{overview,check,history,alerts,alert,opt-out,consent,ccpa,audit,snapshot}")
