"""
EMPIRE V49 · PRODUCT: HEXSTRIKE AI
====================================
Wraps the internal HexStrike security agent (empire_hexstrike_ai.py) into a
productized Suite API with tier-based scan limits, usage metering, and a
dashboard stats endpoint.

Tiers:
  HEXSTRIKE_STARTER    — $99/mo, 100 scans/mo, container + API scans
  HEXSTRIKE_GROWTH     — $249/mo, 500 scans/mo, all scan types, weekly schedule
  HEXSTRIKE_ENTERPRISE — $499/mo, unlimited scans, custom targets, SLA, priority alerts

Integration:
    engine = HexStrikeProduct(get_db, guard, log_usage)
    result = await engine.run_scan(account_id, scan_type)
    report = await engine.scan_report(account_id)
"""

import logging
from datetime import datetime, timezone
from typing import Callable, Optional

log = logging.getLogger("empire.product.hexstrike")

# ── Import the internal security agent ──────────────────────────────
try:
    from empire_hexstrike_ai import HexStrike as _InternalHexStrike
except ImportError:
    _InternalHexStrike = None

# Tier limits (scans per month)
_TIER_LIMITS = {
    "HEXSTRIKE_STARTER": {
        "max_scans": 100,
        "scan_types": ["containers", "api"],
        "scheduled": False,
        "custom_targets": False,
        "priority_alerts": False,
    },
    "HEXSTRIKE_GROWTH": {
        "max_scans": 500,
        "scan_types": ["containers", "api", "secrets", "pipeline"],
        "scheduled": True,
        "custom_targets": False,
        "priority_alerts": False,
    },
    "HEXSTRIKE_ENTERPRISE": {
        "max_scans": 0,  # 0 = unlimited
        "scan_types": ["containers", "api", "secrets", "pipeline", "full"],
        "scheduled": True,
        "custom_targets": True,
        "priority_alerts": True,
    },
}

# Map product scan type to internal scan method name
_SCAN_TYPE_MAP = {
    "containers": "scan_containers",
    "api": "scan_api",
    "secrets": "scan_secrets",
    "pipeline": "scan_pipeline",
    "full": "scan_full",
}


class HexStrikeProduct:
    """
    HexStrike AI as a Suite product. Wraps the internal security agent
    with tier-based scan limits, usage metering, and quota enforcement.

    Integration with Suite Gateway:
      - guard(account_id, "hexstrike") -> {"ok": bool, "tier": str, ...}
      - log_usage(account_id, "hexstrike", "scan", quantity=1)
    """

    def __init__(
        self,
        get_db: Callable,
        guard: Optional[Callable] = None,       # SuiteGuard.check_access
        log_usage: Optional[Callable] = None,    # SuiteGuard.log_usage
    ):
        self._get_db = get_db
        self.guard = guard
        self.log_usage = log_usage
        self._engine = None if _InternalHexStrike is None else _InternalHexStrike(get_db=get_db)
        self.stats = {
            "scans": 0,
            "blocked": 0,
            "errors": 0,
        }
        # In-memory scan log per account
        self._account_scans: dict[str, list[dict]] = {}

    # ── ENTITLEMENT ──────────────────────────────────────────────────

    async def check_entitlement(self, account_id: str) -> dict:
        """Verify the account has HexStrike access and return tier info."""
        if not self.guard:
            return {"ok": True, "tier": "HEXSTRIKE_STARTER",
                    "limits": _TIER_LIMITS["HEXSTRIKE_STARTER"]}
        result = self.guard(account_id, "hexstrike")
        if not result.get("ok"):
            return result
        tier = result.get("tier", "HEXSTRIKE_STARTER")
        return {
            "ok": True,
            "tier": tier,
            "limits": _TIER_LIMITS.get(tier, _TIER_LIMITS["HEXSTRIKE_STARTER"]),
        }

    def _get_tier_limits(self, tier: str) -> dict:
        return _TIER_LIMITS.get(tier, _TIER_LIMITS["HEXSTRIKE_STARTER"])

    def _scan_type_allowed(self, tier: str, scan_type: str) -> bool:
        """Check if scan type is allowed for the given tier."""
        limits = self._get_tier_limits(tier)
        allowed = limits.get("scan_types", [])
        if scan_type == "full":
            return len(allowed) >= 4  # full requires all 4
        return scan_type in allowed

    # ── PUBLIC API ──────────────────────────────────────────────────

    async def run_scan(self, account_id: str, scan_type: str) -> dict:
        """
        Run a security scan of the given type, gated by entitlement and tier limits.

        scan_type: "containers" | "api" | "secrets" | "pipeline" | "full"
        """
        # 1. Entitlement check
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            self.stats["blocked"] += 1
            return {"ok": False, "error": entitlement.get("error", "Access denied")}

        tier = entitlement.get("tier", "HEXSTRIKE_STARTER")
        limits = entitlement.get("limits", {})
        max_scans = limits.get("max_scans", 100)

        # 2. Check scan type is allowed for this tier
        if not self._scan_type_allowed(tier, scan_type):
            self.stats["blocked"] += 1
            return {
                "ok": False,
                "error": f"Scan type '{scan_type}' is not available on {tier} tier",
                "account_id": account_id,
                "tier": tier,
                "available_scan_types": limits.get("scan_types", []),
            }

        # 3. Check monthly scan limit (0 = unlimited)
        account_count = len(self._account_scans.get(account_id, []))
        if max_scans > 0 and account_count >= max_scans:
            self.stats["blocked"] += 1
            return {
                "ok": False,
                "error": f"Monthly scan limit reached ({account_count}/{max_scans})",
                "account_id": account_id,
                "tier": tier,
                "limit": max_scans,
                "used": account_count,
            }

        # 4. Check internal engine availability
        if self._engine is None:
            self.stats["errors"] += 1
            return {"ok": False, "error": "HexStrike engine not available (import failed)"}

        # 5. Run the scan
        method_name = _SCAN_TYPE_MAP.get(scan_type)
        if not method_name:
            self.stats["errors"] += 1
            return {"ok": False, "error": f"Unknown scan type: {scan_type}"}

        method = getattr(self._engine, method_name, None)
        if method is None:
            self.stats["errors"] += 1
            return {"ok": False, "error": f"Scan method '{scan_type}' not found"}

        try:
            result = await method()
        except Exception as e:
            self.stats["errors"] += 1
            return {"ok": False, "error": f"Scan failed: {str(e)[:200]}"}

        # 6. Meter usage
        if self.log_usage:
            try:
                self.log_usage(account_id, "hexstrike", "scan",
                               quantity=1, metadata={
                                   "scan_type": scan_type,
                                   "findings_count": result.get("findings_count", 0),
                                   "critical_count": result.get("critical_count", 0),
                               })
            except Exception:
                pass

        self.stats["scans"] += 1
        self._account_scans.setdefault(account_id, []).append({
            "scan_id": result.get("scan_id"),
            "scan_type": scan_type,
            "tier": tier,
            "findings_count": result.get("findings_count", 0),
            "critical_count": result.get("critical_count", 0),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Attach account info to result
        result["account_id"] = account_id
        result["tier"] = tier
        result["limit_used"] = account_count + 1 if max_scans > 0 else "unlimited"
        result["limit_max"] = max_scans

        return result

    async def scan_report(self, account_id: str) -> dict:
        """
        Return a summary report for the account: scan history, tier info,
        limits, and overall security posture.
        """
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            return {"ok": False, "error": entitlement.get("error", "Access denied")}

        tier = entitlement.get("tier", "HEXSTRIKE_STARTER")
        limits = entitlement.get("limits", {})
        account_scans = self._account_scans.get(account_id, [])

        # Get overview from internal engine if available
        overview = {}
        if self._engine:
            try:
                overview = self._engine.overview()
            except Exception:
                pass

        return {
            "ok": True,
            "account_id": account_id,
            "tier": tier,
            "limits": limits,
            "scans_this_month": len(account_scans),
            "max_scans": limits.get("max_scans", 100),
            "usage_pct": round(
                (len(account_scans) / max(limits.get("max_scans", 100), 1)) * 100, 1
            ) if limits.get("max_scans", 0) > 0 else 0,
            "overview": overview,
            "last_scan": account_scans[-1] if account_scans else None,
        }

    async def list_scan_types(self, account_id: str) -> dict:
        """Return available scan types for the account's tier."""
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            return {"ok": False, "error": entitlement.get("error", "Access denied")}

        tier = entitlement.get("tier", "HEXSTRIKE_STARTER")
        limits = entitlement.get("limits", {})
        return {
            "ok": True,
            "account_id": account_id,
            "tier": tier,
            "scan_types": limits.get("scan_types", []),
        }

    async def health_check(self) -> dict:
        """Return HexStrike product engine health."""
        return {
            "status": "operational" if self._engine else "degraded",
            "service": "hexstrike",
            "internal_engine": "loaded" if self._engine else "unavailable",
            "stats": dict(self.stats),
            "tier_limits": {
                k: {"max_scans": v["max_scans"], "scan_types": v["scan_types"]}
                for k, v in _TIER_LIMITS.items()
            },
        }

    def stats_snapshot(self) -> dict:
        """Return in-memory stats snapshot."""
        total_accounts = len(self._account_scans)
        total_scans = sum(len(v) for v in self._account_scans.values())
        return {
            "engine": dict(self.stats),
            "accounts_active": total_accounts,
            "total_scans_metered": total_scans,
            "tier_limits": _TIER_LIMITS,
            "tiers": list(_TIER_LIMITS.keys()),
        }


# ── FASTAPI ROUTES ──────────────────────────────────────────────────

class HexStrikeProductRoutes:
    """Wire HexStrike product endpoints into the FastAPI app."""

    def __init__(self, engine: HexStrikeProduct, *, require_auth: Optional[Callable] = None):
        self.engine = engine
        self.require_auth = require_auth

    def register(self, app):
        from fastapi import Depends, HTTPException, Query, Request
        from fastapi.responses import JSONResponse

        @app.get("/api/v6/suite/hexstrike/health")
        async def hs_health(auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """HexStrike product health check."""
            return JSONResponse(await self.engine.health_check())

        @app.get("/api/v6/suite/hexstrike/stats")
        async def hs_stats(auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """HexStrike product stats snapshot."""
            return JSONResponse(self.engine.stats_snapshot())

        @app.get("/api/v6/suite/hexstrike/scan-types")
        async def hs_scan_types(
            account_id: str = Query(..., description="Customer account ID"),
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """Return available scan types for the account's tier."""
            result = await self.engine.list_scan_types(account_id)
            status = 200 if result.get("ok") else 403
            return JSONResponse(result, status_code=status)

        @app.post("/api/v6/suite/hexstrike/scan")
        async def hs_run_scan(
            request: Request,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """Run a security scan, gated by entitlement and tier limits.
            Body: {account_id: str (required), scan_type: str (required)}
            scan_type: "containers" | "api" | "secrets" | "pipeline" | "full"
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")

            account_id = (body.get("account_id") or "").strip()
            scan_type = (body.get("scan_type") or "").strip().lower()

            if not account_id:
                raise HTTPException(400, "account_id required")
            if scan_type not in _SCAN_TYPE_MAP:
                raise HTTPException(400,
                    f"Invalid scan_type. Valid: {', '.join(_SCAN_TYPE_MAP.keys())}")

            if not self.engine:
                raise HTTPException(503, "HexStrike engine not initialized")

            result = await self.engine.run_scan(account_id, scan_type)

            if not result.get("ok"):
                error = result.get("error", "Scan denied")
                if "limit" in error.lower() or "not available" in error.lower():
                    return JSONResponse(result, status_code=403)
                return JSONResponse(result, status_code=400)

            return JSONResponse(result)

        @app.get("/api/v6/suite/hexstrike/report")
        async def hs_report(
            account_id: str = Query(..., description="Customer account ID"),
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """Return scan report for the account: history, tier info, limits, posture."""
            result = await self.engine.scan_report(account_id)
            status = 200 if result.get("ok") else 403
            return JSONResponse(result, status_code=status)

        log.info("[hexstrike-product] Routes registered · /api/v6/suite/hexstrike/*")
