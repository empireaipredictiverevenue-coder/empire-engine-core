"""
Empire AI · Predictive Revenue
Lead Enricher Agent
===========================

Second of three agents in the lead-gen pipeline.

Reads enriched_leads (status=pending_enrichment), computes a score, writes
back with score + status=pending_outreach (or blocked if below threshold).

Idempotent: re-running on the same rows updates the score but doesn't move
rows back from pending_outreach. The scan + dedup query handles that.

Usage:
    python3 -m agents.lead_enricher
    python3 -m agents.lead_enricher --status
"""
import os
import sys
import json
import uuid
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO.parent / ".env")
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("empire.lead_enricher")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


# Asset-value keywords. Listed in priority order (first match wins).
_HIGH_VALUE_KEYWORDS = ["distribution", "logistics", "cold storage", "food", "manufacturing", "industrial", "freight"]
_MEDIUM_VALUE_KEYWORDS = ["retail", "store", "shop", "warehouse"]


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in env")
    return create_client(url, key)


def _read_config(sb, default_max=100, default_threshold=1.0):
    r = sb.table("agent_config").select("*").eq("agent_name", "lead_enricher").limit(1).execute()
    if not r.data:
        return {"enabled": True, "dry_run": True, "max_per_run": default_max, "min_score_threshold": default_threshold}
    row = r.data[0]
    cfg = row.get("config_json") or {}
    return {
        "enabled": row.get("enabled", True),
        "dry_run": row.get("dry_run", True),
        "max_per_run": cfg.get("max_per_run", default_max),
        "min_score_threshold": cfg.get("min_score_threshold", default_threshold),
    }


def _log_activity(sb, agent_name, run_id, started_at, status,
                  rows_seen=0, rows_processed=0, rows_blocked=0, rows_errored=0,
                  error=None, summary=None):
    finished_at = datetime.now(timezone.utc).isoformat()
    sb.table("agent_activity").insert({
        "agent_name": agent_name,
        "run_id": str(run_id),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at,
        "status": status,
        "rows_seen": rows_seen,
        "rows_processed": rows_processed,
        "rows_blocked": rows_blocked,
        "rows_errored": rows_errored,
        "error": error,
        "summary": summary,
    }).execute()
    return finished_at


def _update_config(sb, agent_name, status, finished_at):
    sb.table("agent_config").update({
        "last_run_at": finished_at,
        "last_run_status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("agent_name", agent_name).execute()


def _age_days(created_at_iso: str) -> float:
    """Days since the radar_target was created. Handles ISO strings and datetime."""
    if not created_at_iso:
        return 9999.0
    try:
        if isinstance(created_at_iso, str):
            dt = datetime.fromisoformat(created_at_iso.replace("Z", "+00:00"))
        else:
            dt = created_at_iso
        return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0)
    except Exception:
        return 9999.0


def _score_row(row: dict) -> tuple[float, list[dict]]:
    """Compute a 0-10 score for a lead. Returns (score, trace)."""
    trace = []
    score = 0.0

    # urgency (40% of 10 = 4.0 max)
    # we need the radar_target created_at; fall back to enriched_leads.created_at
    age = _age_days(row.get("created_at"))
    if age <= 1:
        s = 4.0
    elif age <= 7:
        s = 3.0
    elif age <= 30:
        s = 1.5
    else:
        s = 0.5
    score += s
    trace.append({"step": "urgency", "age_days": age, "delta": s})

    # data completeness (20% of 10 = 2.0 max)
    fields = ["address", "city", "state", "warehouse_name"]
    have = sum(1 for f in fields if row.get(f))
    completeness = (have / len(fields)) * 2.0
    score += completeness
    trace.append({"step": "completeness", "have": have, "of": len(fields), "delta": completeness})

    # asset value (30% of 10 = 3.0 max)
    wh = (row.get("warehouse_name") or "").lower()
    asset_delta = 0.0
    matched = None
    for kw in _HIGH_VALUE_KEYWORDS:
        if kw in wh:
            asset_delta = 3.0
            matched = kw
            break
    if asset_delta == 0.0:
        for kw in _MEDIUM_VALUE_KEYWORDS:
            if kw in wh:
                asset_delta = 1.5
                matched = kw
                break
    if asset_delta == 0.0 and wh:
        asset_delta = 0.5
    score += asset_delta
    trace.append({"step": "asset_value", "matched": matched, "delta": asset_delta})

    # contact ready (10% of 10 = 1.0 max)
    contact_delta = 1.0 if (row.get("phone") or row.get("email")) else 0.0
    score += contact_delta
    trace.append({"step": "contact_ready", "has_phone": bool(row.get("phone")),
                  "has_email": bool(row.get("email")), "delta": contact_delta})

    return round(score, 2), trace


def _block_reason(row: dict, score: float, threshold: float) -> str:
    if score < threshold:
        if not row.get("warehouse_name"):
            return "below_threshold:no_warehouse_name"
        if not (row.get("phone") or row.get("email")):
            return "below_threshold:no_contact"
        return "below_threshold:low_urgency"
    return ""


def run() -> dict:
    started_at = datetime.now(timezone.utc)
    run_id = uuid.uuid4()
    sb = _sb()
    cfg = _read_config(sb)

    if not cfg["enabled"]:
        _log_activity(sb, "lead_enricher", run_id, started_at, "skipped_disabled",
                      summary="disabled in agent_config")
        _update_config(sb, "lead_enricher", "skipped_disabled", datetime.now(timezone.utc).isoformat())
        return {"status": "skipped_disabled", "rows_processed": 0}

    # 1) Read pending rows
    rows_res = (sb.table("enriched_leads")
                  .select("id, radar_target_id, address, city, state, phone, email, warehouse_name, asset_value, status, created_at, meta")
                  .eq("status", "pending_enrichment")
                  .order("created_at", desc=False)
                  .limit(cfg["max_per_run"])
                  .execute())
    rows = rows_res.data or []
    log.info(f"enricher: {len(rows)} pending rows")
    rows_seen = len(rows)

    # 2) Score + update each
    rows_processed = 0
    rows_blocked = 0
    rows_errored = 0
    error_msgs = []

    for row in rows:
        try:
            score, trace = _score_row(row)
            threshold = cfg["min_score_threshold"]
            above = score >= threshold
            new_status = "pending_outreach" if above else "blocked"
            if not above:
                rows_blocked += 1
            block_reason = _block_reason(row, score, threshold) if not above else None

            # merge trace into existing meta (preserve scanner's data)
            existing_meta = row.get("meta") or {}
            new_meta = dict(existing_meta)
            new_meta["enrichment_trace"] = trace
            new_meta["enrichment_block_reason"] = block_reason
            new_meta["enrichment_scored_at"] = datetime.now(timezone.utc).isoformat()

            sb.table("enriched_leads").update({
                "score": score,
                "status": new_status,
                "last_enriched_at": datetime.now(timezone.utc).isoformat(),
                "meta": new_meta,
            }).eq("id", row["id"]).execute()
            rows_processed += 1
        except Exception as e:
            rows_errored += 1
            error_msgs.append(f"{row.get('id', '?')[:8]}: {type(e).__name__}: {e}")
            log.warning(f"enricher: update failed for {row.get('id')}: {e}")

    finished_at = datetime.now(timezone.utc)
    summary = (f"scored {rows_seen} rows, {rows_processed} updated "
               f"({rows_seen - rows_blocked - rows_errored} to pending_outreach, "
               f"{rows_blocked} to blocked), {rows_errored} errored")
    status = "ok" if rows_errored == 0 else "ok"
    err_field = None if rows_errored == 0 else "; ".join(error_msgs[:5])

    _log_activity(sb, "lead_enricher", run_id, started_at, status,
                  rows_seen=rows_seen, rows_processed=rows_processed,
                  rows_blocked=rows_blocked, rows_errored=rows_errored,
                  error=err_field, summary=summary)
    _update_config(sb, "lead_enricher", status, finished_at.isoformat())

    log.info(summary)
    return {"status": status, "rows_seen": rows_seen, "rows_processed": rows_processed,
            "rows_blocked": rows_blocked, "rows_errored": rows_errored}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--status", action="store_true")
    args = p.parse_args()
    if args.status:
        sb = _sb()
        cfg = _read_config(sb)
        last_act = (sb.table("agent_activity")
                      .select("*").eq("agent_name", "lead_enricher")
                      .order("started_at", desc=True).limit(1).execute())
        print(json.dumps({"config": cfg, "last_run": last_act.data[0] if last_act.data else None},
                         indent=2, default=str))
        return
    result = run()
    sys.exit(0 if result["status"] in ("ok", "skipped_disabled") else 1)


if __name__ == "__main__":
    main()
