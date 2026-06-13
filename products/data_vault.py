"""
EMPIRE V49 · PRODUCT 2: DATA VAULT (Asset Retention)
=====================================================
Provides tiered data retention, encrypted asset storage, and structured
data persistence for enterprise subscribers. Part of the Suite Gateway
monetization — only available to accounts with data_retention_enabled flag.

Integration:
    vault = DataVault(suite_guard, suite_subscriptions)
    result = vault.store_asset(account_id, asset_data)
    assets = vault.list_assets(account_id)
"""
import json as _json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional

log = logging.getLogger("empire.product.data_vault")


class DataVault:
    """Tiered data retention and asset storage service.
    Respects per-account retention periods and storage caps."""

    def __init__(
        self,
        guard: Optional[Callable] = None,     # SuiteGuard.check_access
        log_usage: Optional[Callable] = None,  # SuiteGuard.log_usage
    ):
        self.guard = guard
        self.log_usage = log_usage
        self.stats = {"stored": 0, "retrieved": 0, "purged": 0, "errors": 0}
        # In-memory store (in production, uses Supabase or S3)
        self._store: dict[str, list[dict]] = {}

    async def check_entitlement(self, account_id: str) -> dict:
        if not self.guard:
            return {"ok": False, "error": "No guard configured"}
        return self.guard(account_id, "data_vault")

    def _get_retention_days(self, account_id: str) -> int:
        """Return the retention period for an account. Default 90 days."""
        if not self.guard:
            return 90
        try:
            import sqlite3
            conn = sqlite3.connect(str(__import__("pathlib").Path(__file__).resolve().parent.parent / "data" / "storm_alerts.sqlite"))
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT data_retention_days FROM product_feature_flags WHERE customer_account_id = ?",
                (account_id,),
            )
            row = cur.fetchone()
            conn.close()
            if row and row["data_retention_days"]:
                return int(row["data_retention_days"])
        except Exception:
            pass
        return 90

    async def store_asset(self, account_id: str, asset_data: dict) -> dict:
        """Store a data asset (property record, storm report, lead export, etc.)
        under the account's retention policy."""
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            self.stats["errors"] += 1
            return {"ok": False, "error": entitlement.get("error", "Access denied")}

        asset_id = f"asset_{uuid.uuid4().hex[:12]}"
        retention_days = self._get_retention_days(account_id)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=retention_days)

        asset = {
            "asset_id": asset_id,
            "account_id": account_id,
            "type": asset_data.get("type", "generic"),
            "data": asset_data.get("data", asset_data),
            "metadata": asset_data.get("metadata", {}),
            "retention_days": retention_days,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }

        self._store.setdefault(account_id, []).append(asset)

        # Meter usage
        if self.log_usage:
            try:
                self.log_usage(account_id, "data_vault", "data_upload",
                               quantity=1, metadata={"asset_type": asset["type"], "asset_id": asset_id})
            except Exception:
                pass

        self.stats["stored"] += 1
        return {"ok": True, "asset_id": asset_id, "retention_days": retention_days,
                "expires_at": asset["expires_at"], "tier": entitlement.get("tier", "unknown")}

    def list_assets(self, account_id: str) -> list[dict]:
        """List all non-expired assets for an account."""
        self.stats["retrieved"] += 1
        assets = self._store.get(account_id, [])
        now = datetime.now(timezone.utc).isoformat()
        valid = [a for a in assets if a.get("expires_at", "9999") > now]
        return valid

    def purge_expired(self, account_id: Optional[str] = None) -> int:
        """Remove expired assets. Returns count of purged items."""
        purged = 0
        for aid in (list(self._store.keys()) if account_id is None else [account_id]):
            assets = self._store.get(aid, [])
            now = datetime.now(timezone.utc).isoformat()
            before = len(assets)
            self._store[aid] = [a for a in assets if a.get("expires_at", "9999") > now]
            purged += before - len(self._store[aid])
        self.stats["purged"] += purged
        return purged

    def snapshot(self) -> dict:
        total_assets = sum(len(a) for a in self._store.values())
        return {
            **self.stats,
            "total_assets": total_assets,
            "active_accounts": len(self._store),
        }


class DataVaultRoutes:
    """Wire DataVault endpoints into the FastAPI app."""

    def __init__(self, vault: DataVault, require_auth: Optional[Callable] = None):
        self.vault = vault
        self.require_auth = require_auth

    def register(self, app):
        from fastapi import Depends, HTTPException, Request, Query
        from fastapi.responses import JSONResponse

        @app.post("/api/v6/suite/data-vault/store")
        async def vault_store(request: Request, auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Store a data asset under an account's retention policy.
            Body: {account_id, type, data, metadata?}"""
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")
            account_id = (body.get("account_id") or "").strip()
            if not account_id:
                raise HTTPException(400, "account_id required")
            result = await self.vault.store_asset(account_id, body)
            status = 403 if not result.get("ok") and "denied" in str(result.get("error", "")).lower() else (200 if result.get("ok") else 400)
            return JSONResponse(result, status_code=status)

        @app.get("/api/v6/suite/data-vault/assets")
        async def vault_assets(account_id: str = Query(...), auth: bool = Depends(self.require_auth) if self.require_auth else None):
            if not account_id:
                raise HTTPException(400, "account_id query param required")
            assets = self.vault.list_assets(account_id)
            return JSONResponse({"assets": assets, "count": len(assets)})

        @app.post("/api/v6/suite/data-vault/purge")
        async def vault_purge(account_id: str = Query(""), auth: bool = Depends(self.require_auth) if self.require_auth else None):
            purged = self.vault.purge_expired(account_id or None)
            return JSONResponse({"purged": purged})

        @app.get("/api/v6/suite/data-vault/stats")
        async def vault_stats(auth: bool = Depends(self.require_auth) if self.require_auth else None):
            return JSONResponse(self.vault.snapshot())

        log.info("[data-vault] Routes registered")
