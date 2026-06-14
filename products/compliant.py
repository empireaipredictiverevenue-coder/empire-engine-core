"""
EMPIRE V49 · PRODUCT: COMPLIANT
================================
Standalone compliance-as-a-service product. Wraps the existing deterministic
compliance rules engine (compliance.py) and the outreach compliance gate
(agents/outreach/compliance.py) into a productized API with tier-based
rate limits, usage metering, and a dashboard stats endpoint.

Tiers:
  COMPLIANT_STARTER    — $199/mo, 500 checks/mo, basic TCPA/DNC/opt-out
  COMPLIANT_GROWTH     — $499/mo, 2,000 checks/mo, full suite + quiet hours
  COMPLIANT_ENTERPRISE — $999/mo, 10,000 checks/mo, audit logging + custom rules

Integration:
    engine = Compliant(guard, log_usage)
    result = await engine.check_action(account_id, action_type, payload)
    report = await engine.check_batch(account_id, [check, ...])
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Any

log = logging.getLogger("empire.product.compliant")

# ── IMPORT COMPLIANCE RULES ENGINE ──────────────────────────────────
# Import the deterministic rules engine from compliance.py (always available).
# The outreach compliance gate (agents/outreach/compliance.py) is imported
# lazily because it has a Supabase dependency.
try:
    import compliance as _compliance_rules
except ImportError:
    _compliance_rules = None

try:
    from agents.outreach.compliance import (
        can_send_sms as _outreach_can_send_sms,
        can_place_call as _outreach_can_place_call,
        is_opted_out as _outreach_is_opted_out,
        is_on_dnc as _outreach_is_on_dnc,
        has_consent as _outreach_has_consent,
        is_quiet_hours as _outreach_is_quiet_hours,
        can_send_today as _outreach_can_send_today,
        register_opt_out as _outreach_register_opt_out,
    )
except ImportError:
    _outreach_can_send_sms = None
    _outreach_can_place_call = None
    _outreach_is_opted_out = None
    _outreach_is_on_dnc = None
    _outreach_has_consent = None
    _outreach_is_quiet_hours = None
    _outreach_can_send_today = None
    _outreach_register_opt_out = None

# Tier limits (compliance checks per month)
_TIER_LIMITS = {
    "COMPLIANT_STARTER": 500,
    "COMPLIANT_GROWTH": 2000,
    "COMPLIANT_ENTERPRISE": 10000,
}


class Compliant:
    """
    Compliance-as-a-Service engine. Wraps the deterministic rules engine
    from compliance.py and the outreach compliance gate into a productized
    API with tier-based rate limits, usage metering, and a dashboard snapshot.

    Integration with Suite Gateway:
      - guard(account_id, "compliant") -> {"ok": bool, "tier": str, ...}
      - log_usage(account_id, "compliant", "check", quantity=1)
    """

    def __init__(
        self,
        guard: Optional[Callable] = None,      # SuiteGuard.check_access
        log_usage: Optional[Callable] = None,   # SuiteGuard.log_usage
    ):
        self.guard = guard
        self.log_usage = log_usage
        self.stats = {
            "checks": 0,
            "blocks": 0,
            "allows": 0,
            "blocked": 0,
            "errors": 0,
        }
        self._results: Dict[str, List[Dict]] = {}

    # ── ENTITLEMENT ──────────────────────────────────────────────────

    async def check_entitlement(self, account_id: str) -> dict:
        """Verify the account has Compliant access."""
        if not self.guard:
            return {"ok": True, "tier": "COMPLIANT_STARTER"}
        return self.guard(account_id, "compliant")

    def _get_tier_limit(self, tier: str) -> int:
        return _TIER_LIMITS.get(tier, 500)

    # ── COMPLIANCE CHECK METHODS ─────────────────────────────────────

    @staticmethod
    def check_action_type(action_type: str, payload: Optional[dict] = None) -> dict:
        """
        Run a single compliance check against the deterministic rules engine.

        Wraps compliance.check() which applies hardcoded rules:
          - No homeowner cold-contact (TCPA/privacy)
          - Billing gated on qualified + 90s call
          - No cold outreach from protected domain
          - No scraping of banned platforms

        Returns: {
          "allowed": bool,
          "rule": str,
          "reason": str,
        }
        """
        if _compliance_rules is None:
            return {
                "allowed": False,
                "rule": "engine_unavailable",
                "reason": "Compliance rules engine not available",
            }
        return _compliance_rules.check(action_type, payload or {})

    @staticmethod
    def check_sms_compliance(
        phone: str,
        consent_flag: Optional[bool] = None,
        area_code: str = "",
    ) -> dict:
        """
        Run outreach compliance checks for SMS sends.

        Checks (in order):
          1. Opt-out registry
          2. DNC list
          3. TCPA consent flag
          4. Quiet hours (recipient local time)
          5. Per-number per-day rate limit

        Returns: {"allowed": bool, "reason": str, "checks": {...}}
        """
        if _outreach_can_send_sms is None:
            return {
                "allowed": True,
                "reason": "",
                "note": "outreach compliance gate not loaded; using permissive default",
                "checks": {},
            }

        allowed, reason = _outreach_can_send_sms(phone, consent_flag, area_code)

        checks = {
            "opted_out": _outreach_is_opted_out(phone) if _outreach_is_opted_out else None,
            "on_dnc": _outreach_is_on_dnc(phone) if _outreach_is_on_dnc else None,
            "has_consent": _outreach_has_consent(consent_flag) if _outreach_has_consent else None,
            "quiet_hours": _outreach_is_quiet_hours(area_code) if _outreach_is_quiet_hours else None,
            "can_send_today": _outreach_can_send_today(phone) if _outreach_can_send_today else None,
        }

        return {
            "allowed": allowed,
            "reason": reason,
            "checks": {k: v for k, v in checks.items() if v is not None},
        }

    @staticmethod
    def check_call_compliance(
        phone: str,
        consent_flag: Optional[bool] = None,
        area_code: str = "",
    ) -> dict:
        """
        Run outreach compliance checks for voice calls.

        Checks (in order):
          1. Opt-out registry
          2. DNC list
          3. TCPA consent flag
          4. Quiet hours (recipient local time)

        Returns: {"allowed": bool, "reason": str, "checks": {...}}
        """
        if _outreach_can_place_call is None:
            return {
                "allowed": True,
                "reason": "",
                "note": "outreach compliance gate not loaded; using permissive default",
                "checks": {},
            }

        allowed, reason = _outreach_can_place_call(phone, consent_flag, area_code)

        checks = {
            "opted_out": _outreach_is_opted_out(phone) if _outreach_is_opted_out else None,
            "on_dnc": _outreach_is_on_dnc(phone) if _outreach_is_on_dnc else None,
            "has_consent": _outreach_has_consent(consent_flag) if _outreach_has_consent else None,
            "quiet_hours": _outreach_is_quiet_hours(area_code) if _outreach_is_quiet_hours else None,
        }

        return {
            "allowed": allowed,
            "reason": reason,
            "checks": {k: v for k, v in checks.items() if v is not None},
        }

    @staticmethod
    def register_opt_out(phone: str, reason: str = "user request") -> dict:
        """Register an opt-out in the sms_opt_outs table."""
        if _outreach_register_opt_out is None:
            return {"ok": False, "error": "outreach compliance gate not loaded"}
        result = _outreach_register_opt_out(phone, reason)
        return {"ok": result, "phone": phone, "reason": reason}

    # ── PUBLIC API ──────────────────────────────────────────────────

    async def check_action(
        self,
        account_id: str,
        action_type: str,
        payload: Optional[dict] = None,
        phone: str = "",
        consent_flag: Optional[bool] = None,
        area_code: str = "",
    ) -> dict:
        """
        Run a compliance check against the full rules engine.

        Two-layer check:
          1. Deterministic rules (compliance.check) — homeowner contact, billing gate,
             domain protection, banned scraping
          2. Outreach compliance (if phone provided) — opt-out, DNC, consent, quiet hours, rate limit

        Entitlement-gated by tier. Metered as one check.

        Returns: {"ok": bool, "allowed": bool, "rule": str, "reason": str, ...}
        """
        # 1. Entitlement check
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            self.stats["blocked"] += 1
            return {"ok": False, "error": entitlement.get("error", "Access denied")}

        tier = entitlement.get("tier", "COMPLIANT_STARTER")
        limit = self._get_tier_limit(tier)

        # 2. Check tier limit
        account_count = len(self._results.get(account_id, []))
        if account_count >= limit:
            self.stats["blocked"] += 1
            return {
                "ok": False,
                "error": f"Monthly tier limit reached ({account_count}/{limit})",
                "account_id": account_id,
                "tier": tier,
                "limit": limit,
                "used": account_count,
            }

        # 3. Run deterministic rules check
        rules_result = self.check_action_type(action_type, payload)

        # 4. Run outreach compliance check (if phone provided)
        outreach_result = None
        if phone:
            if action_type in ("outreach", "send", "sms"):
                outreach_result = self.check_sms_compliance(phone, consent_flag, area_code)
            elif action_type in ("dial", "call", "voice"):
                outreach_result = self.check_call_compliance(phone, consent_flag, area_code)

        # 5. Combine: allow only if BOTH pass
        allowed = rules_result.get("allowed", False)
        if outreach_result is not None:
            allowed = allowed and outreach_result.get("allowed", True)

        if allowed:
            self.stats["allows"] += 1
        else:
            self.stats["blocks"] += 1

        self.stats["checks"] += 1

        # 6. Meter usage
        if self.log_usage:
            try:
                self.log_usage(account_id, "compliant", "check",
                               quantity=1, metadata={
                                   "action": action_type,
                                   "allowed": allowed,
                                   "rule": rules_result.get("rule", ""),
                               })
            except Exception:
                pass

        result = {
            "ok": True,
            "allowed": allowed,
            "account_id": account_id,
            "tier": tier,
            "limit_used": account_count + 1,
            "limit_max": limit,
            "action_type": action_type,
            "rules_result": rules_result,
            "outreach_result": outreach_result,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

        self._results.setdefault(account_id, []).append(result)
        return result

    async def check_batch(
        self,
        account_id: str,
        checks: List[dict],
    ) -> dict:
        """
        Run a batch of compliance checks.

        Each check in the list should be:
          {"action_type": str, "payload": dict?, "phone": str?, "consent_flag": bool?, "area_code": str?}

        Returns summary with per-check results.
        """
        # 1. Entitlement check
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            self.stats["blocked"] += 1
            return {"ok": False, "error": entitlement.get("error", "Access denied")}

        if not checks or not isinstance(checks, list):
            return {"ok": False, "error": "Invalid checks array"}

        tier = entitlement.get("tier", "COMPLIANT_STARTER")
        limit = self._get_tier_limit(tier)
        results = []
        allowed_count = 0
        blocked_count = 0

        for check in checks[:limit]:
            if not isinstance(check, dict):
                continue

            # Run the check inline (no per-check entitlement — already gated)
            rules_result = self.check_action_type(
                check.get("action_type", ""),
                check.get("payload"),
            )
            phone = check.get("phone", "")
            consent_flag = check.get("consent_flag")
            area_code = check.get("area_code", "")

            outreach_result = None
            if phone:
                at = check.get("action_type", "")
                if at in ("outreach", "send", "sms"):
                    outreach_result = self.check_sms_compliance(phone, consent_flag, area_code)
                elif at in ("dial", "call", "voice"):
                    outreach_result = self.check_call_compliance(phone, consent_flag, area_code)

            allowed = rules_result.get("allowed", False)
            if outreach_result is not None:
                allowed = allowed and outreach_result.get("allowed", True)

            if allowed:
                allowed_count += 1
            else:
                blocked_count += 1

            results.append({
                "action_type": check.get("action_type", ""),
                "allowed": allowed,
                "rules_result": rules_result,
                "outreach_result": outreach_result,
            })

        self.stats["checks"] += len(results)
        self.stats["allows"] += allowed_count
        self.stats["blocks"] += blocked_count

        # Meter usage
        if self.log_usage:
            try:
                self.log_usage(account_id, "compliant", "check",
                               quantity=len(results))
            except Exception:
                pass

        self._results.setdefault(account_id, []).extend(results)

        return {
            "ok": True,
            "account_id": account_id,
            "tier": tier,
            "batch_size": len(results),
            "allowed": allowed_count,
            "blocked": blocked_count,
            "results": results,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    async def stats_snapshot(self, get_db: Optional[Callable] = None) -> dict:
        """
        Return compliance stats dashboard data.

        If get_db is provided, queries Supabase for live counts from
        compliance_audit_logs, sms_opt_outs, and outbound_dnc tables.
        Otherwise returns in-memory product stats only.
        """
        dashboard = {}

        if get_db:
            try:
                db = get_db()
                now = datetime.now(timezone.utc)
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

                # Blocked today
                blocked_today = 0
                try:
                    r = db.table("compliance_audit_logs").select("*", count="exact") \
                        .eq("action", "outbound_call_blocked") \
                        .gte("created_at", today_start) \
                        .execute()
                    blocked_today = getattr(r, "count", len(r.data or []))
                except Exception:
                    pass

                # Recent blocks (last 10)
                recent_blocks = []
                try:
                    r = db.table("compliance_audit_logs").select("*") \
                        .eq("action", "outbound_call_blocked") \
                        .order("created_at", desc=True).limit(10).execute()
                    for e in (r.data or []):
                        det = e.get("details", {}) or {}
                        recent_blocks.append({
                            "ts": (e.get("created_at") or "")[:19],
                            "rule": det.get("rule", "") if isinstance(det, dict) else "",
                            "phone": e.get("entity_id", "") or det.get("phone", "") if isinstance(det, dict) else "",
                        })
                except Exception:
                    pass

                # DNC table counts
                sms_opt_outs = 0
                outbound_dnc = 0
                try:
                    r = db.table("sms_opt_outs").select("*", count="exact").limit(1).execute()
                    sms_opt_outs = getattr(r, "count", 0)
                except Exception:
                    pass
                try:
                    r = db.table("outbound_dnc").select("*", count="exact").limit(1).execute()
                    outbound_dnc = getattr(r, "count", 0)
                except Exception:
                    pass

                # Call window
                from zoneinfo import ZoneInfo as _zi
                tz_name = "America/Chicago"
                try:
                    h = datetime.now(_zi(tz_name)).hour
                except Exception:
                    h = now.hour
                within_hours = 8 <= h < 21

                dashboard = {
                    "blocked_today": blocked_today,
                    "recent_blocks": recent_blocks,
                    "sms_opt_outs": sms_opt_outs,
                    "outbound_dnc": outbound_dnc,
                    "call_window": {
                        "open": within_hours,
                        "local_hour": h,
                        "window": f"08:00-21:00 {tz_name}",
                    },
                }
            except Exception as e:
                log.debug(f"[compliant] dashboard query failed: {e}")
                dashboard = {}

        return {
            "stats": {
                "total_checks": self.stats["checks"],
                "total_allows": self.stats["allows"],
                "total_blocks": self.stats["blocks"],
                "total_blocked": self.stats["blocked"],
                "total_errors": self.stats["errors"],
                "accounts_active": len(self._results),
            },
            "dashboard": dashboard,
            "tier_limits": _TIER_LIMITS,
        }

    async def health_check(self) -> dict:
        """Return Compliant health status."""
        rules_ok = _compliance_rules is not None
        outreach_ok = _outreach_can_send_sms is not None

        return {
            "status": "operational" if (rules_ok or outreach_ok) else "degraded",
            "service": "compliant",
            "engines": {
                "rules_engine": "loaded" if rules_ok else "unavailable",
                "outreach_gate": "loaded" if outreach_ok else "unavailable",
            },
            "stats": dict(self.stats),
        }


# ── FASTAPI ROUTES ──────────────────────────────────────────────────

class CompliantRoutes:
    """Wire Compliant endpoints into the FastAPI app."""

    def __init__(self, engine: Compliant, require_auth: Optional[Callable] = None,
                 get_db: Optional[Callable] = None):
        self.engine = engine
        self.require_auth = require_auth
        self.get_db = get_db

    def register(self, app):
        from fastapi import Depends, HTTPException, Request
        from fastapi.responses import JSONResponse

        @app.post("/api/v6/suite/compliant/check")
        async def compliant_check(
            request: Request,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """Run a single compliance check.
            Body: {
              account_id: str (required),
              action_type: str (required — "outreach", "send", "dial", "book_revenue", "scrape"),
              payload?: dict,
              phone?: str,
              consent_flag?: bool,
              area_code?: str,
            }
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")

            account_id = (body.get("account_id") or "").strip()
            action_type = (body.get("action_type") or "").strip().lower()
            payload = body.get("payload")
            phone = body.get("phone", "")
            consent_flag = body.get("consent_flag")
            area_code = body.get("area_code", "")

            if not account_id:
                raise HTTPException(400, "account_id required")
            if not action_type:
                raise HTTPException(400, "action_type required")

            result = await self.engine.check_action(
                account_id, action_type, payload,
                phone=phone, consent_flag=consent_flag, area_code=area_code,
            )
            status = 403 if not result.get("ok") and "denied" in str(result.get("error", "")).lower() else (
                200 if result.get("ok") else 400
            )
            return JSONResponse(result, status_code=status)

        @app.post("/api/v6/suite/compliant/check-batch")
        async def compliant_check_batch(
            request: Request,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """Run a batch of compliance checks.
            Body: {
              account_id: str (required),
              checks: [{"action_type": str, "payload"?: dict, "phone"?: str, ...}]
            }
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")

            account_id = (body.get("account_id") or "").strip()
            checks = body.get("checks", [])

            if not account_id:
                raise HTTPException(400, "account_id required")
            if not isinstance(checks, list) or len(checks) == 0:
                raise HTTPException(400, "checks must be a non-empty array")

            result = await self.engine.check_batch(account_id, checks)
            status = 403 if not result.get("ok") and "denied" in str(result.get("error", "")).lower() else (
                200 if result.get("ok") else 400
            )
            return JSONResponse(result, status_code=status)

        @app.get("/api/v6/suite/compliant/stats")
        async def compliant_stats(
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """Compliant stats snapshot — checks, blocks, dashboard data."""
            return JSONResponse(await self.engine.stats_snapshot(get_db=self.get_db))

        @app.get("/api/v6/suite/compliant/health")
        async def compliant_health(
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """Compliant health check — rules engine and outreach gate status."""
            return JSONResponse(await self.engine.health_check())

        @app.post("/api/v6/suite/compliant/opt-out")
        async def compliant_register_opt_out(
            request: Request,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """Register an opt-out for a phone number.
            Body: {phone: str (required), reason?: str}
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")

            phone = (body.get("phone") or "").strip()
            reason = body.get("reason", "user request")

            if not phone:
                raise HTTPException(400, "phone required")

            result = self.engine.register_opt_out(phone, reason)
            status = 200 if result.get("ok") else 400
            return JSONResponse(result, status_code=status)

        log.info("[compliant] Routes registered · /api/v6/suite/compliant/*")
