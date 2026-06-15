"""
EMPIRE V49 · MASTER ADMIN EXECUTIVE COMMAND CENTER
====================================================
Single-window view of the entire empire.

Aggregates real-time metrics from Supabase tables:
  - Dashboard layout bugs (dashboard_layout_diagnostics)
  - Warehouse Sniper leads (warehouse_sniper_leads)
  - Active pay-per-call lines (empire_switchboard_sessions)
  - On-chain USDC revenue (empire_revenue_ledger)

Runs on port 8120 as a standalone microservice.

Environment:
  SUPABASE_URL              — Supabase project URL
  SUPABASE_SERVICE_KEY      — Service role key (NOT anon key)
"""

import os
import logging
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, HTTPException, status

log = logging.getLogger("empire.admin.portal")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
)

app = FastAPI(
    title="Empire_AI_Executive_Command_Center",
    version="1.0.0",
    description="Single-window system status aggregation for the Empire AI fleet.",
)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get(
    "SUPABASE_SERVICE_KEY",
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
)


# ── HELPERS ──────────────────────────────────────────────────────────────


async def fetch_table_count(table_name: str, filter_query: str = "") -> int:
    """Query Supabase REST API for a row count with optional filter.

    Uses the Content-Range header to extract the total count without
    fetching full row data. Returns 0 if the table doesn't exist or
    is unreachable (graceful degradation — not an error).
    """
    if not SUPABASE_KEY:
        return 0

    url = f"{SUPABASE_URL}/rest/v1/{table_name}?select=count"
    if filter_query:
        url = f"{SUPABASE_URL}/rest/v1/{table_name}?{filter_query}&select=count"

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=10.0)
            if response.status_code == 200:
                content_range = response.headers.get("content-range", "")
                if "/" in content_range:
                    return int(content_range.split("/")[-1])
            return 0
        except Exception:
            log.debug(f"[portal] count query failed for {table_name}", exc_info=True)
            return 0


async def fetch_sum(table_name: str, column: str) -> float:
    """Sum a numeric column via Supabase REST, returning total or 0.0."""
    if not SUPABASE_KEY:
        return 0.0

    url = f"{SUPABASE_URL}/rest/v1/{table_name}?select={column}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=15.0)
            if response.status_code == 200:
                records = response.json()
                total = sum(float(row.get(column, 0)) for row in records if row.get(column) is not None)
                return round(total, 2)
        except Exception:
            log.debug(f"[portal] sum query failed for {table_name}.{column}", exc_info=True)
    return 0.0


# ── ENDPOINTS ────────────────────────────────────────────────────────────


@app.get("/health", status_code=status.HTTP_200_OK)
async def health():
    """Health check — used by deploy script and load balancers."""
    return {
        "status": "OPERATIONAL",
        "service": "empire-executive-command-center",
        "port": 8120,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/admin/cockpit-summary", status_code=status.HTTP_200_OK)
async def get_master_system_status():
    """The Single Window View.

    Aggregates live metrics from every major subsystem and returns
    a unified control response. Every field degrades gracefully —
    a missing table returns 0, not an error.
    """
    if not SUPABASE_KEY:
        raise HTTPException(
            status_code=500,
            detail="Missing server configuration tokens — set SUPABASE_SERVICE_KEY in /root/.env",
        )

    # ── Gather metrics across all subsystems ──────────────────────
    open_layout_bugs = await fetch_table_count(
        "dashboard_layout_diagnostics",
        "resolution_status=eq.OPEN",
    )
    total_hunted_warehouses = await fetch_table_count("warehouse_sniper_leads")
    active_pay_per_call_lines = await fetch_table_count(
        "empire_switchboard_sessions",
        "monetization_mode=eq.PAY_PER_CALL",
    )
    total_usdc_earned = await fetch_sum("empire_revenue_ledger", "usdc_amount")

    # ── Build response ────────────────────────────────────────────
    system_health = "SHIELD_ACTIVE" if open_layout_bugs == 0 else "ATTENTION_REQUIRED"

    return {
        "system_health": system_health,
        "metrics": {
            "active_layout_blockers": open_layout_bugs,
            "total_hunted_properties": total_hunted_warehouses,
            "monetized_voice_channels": active_pay_per_call_lines,
        },
        "financial_ledger": {
            "onchain_settled_revenue_usdc": total_usdc_earned,
            "currency_ticker": "USDC_SOLANA",
        },
        "engine_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
