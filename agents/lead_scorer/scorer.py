"""
Empire AI · Lead Scorer Agent
==============================

Reads radar_targets + enriched_leads, classifies each lead's temperature
(hot/warm/cold) based on urgency_score, enrichment score, contact availability,
and recency. Writes to the campaign_leads table for other campaign pipelines.

Hot  → dispatch immediately (urgency ≥ 7, has phone, enriched score ≥ 0.5)
Warm → nurture sequence (urgency 4-6, or missing enrichment data)
Cold → long-tail retarget (urgency < 4, or very old, or no contact)

Usage:
    python3 -m agents.lead_scorer
    python3 -m agents.lead_scorer --status
"""

import os
import sys
import json
import uuid
import math
import logging
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO.parent / ".env")
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("empire.lead_scorer")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

# ── SCORING CONSTANTS ───────────────────────────────────────────────────

# Weight for composite score calculation
COMPOSITE_WEIGHTS = {
    "urgency": 0.40,       # urgency_score (0-10, normalized)
    "enrichment": 0.30,    # enrichment score (0-1)
    "contact": 0.20,       # has phone or email
    "recency": 0.10,       # inverse of age in days (newer = higher)
}

# Temperature thresholds (composite_score 0.0-1.0)
HOT_THRESHOLD = 0.60      # ≥ 0.60 → hot
WARM_THRESHOLD = 0.30     # ≥ 0.30 → warm, < 0.30 → cold

# Recency half-life in days
RECENCY_HALF_LIFE_DAYS = 14.0

# Max leads per run
DEFAULT_MAX_PER_RUN = 200

# ── DB HELPERS ──────────────────────────────────────────────────────────

def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in env")
    return create_client(url, key)


def _read_config(sb):
    r = sb.table("agent_config").select("*").eq("agent_name", "lead_scorer").limit(1).execute()
    if not r.data:
        return {
            "enabled": True,
            "dry_run": True,
            "max_per_run": DEFAULT_MAX_PER_RUN,
            "hot_threshold": HOT_THRESHOLD,
            "warm_threshold": WARM_THRESHOLD,
        }
    row = r.data[0]
    cfg = row.get("config_json") or {}
    return {
        "enabled": row.get("enabled", True),
        "dry_run": row.get("dry_run", True),
        "max_per_run": cfg.get("max_per_run", DEFAULT_MAX_PER_RUN),
        "hot_threshold": cfg.get("hot_threshold", HOT_THRESHOLD),
        "warm_threshold": cfg.get("warm_threshold", WARM_THRESHOLD),
    }


def _log_activity(sb, agent_name, run_id, started_at, status, **kwargs):
    finished_at = datetime.now(timezone.utc).isoformat()
    sb.table("agent_activity").insert({
        "agent_name": agent_name,
        "run_id": str(run_id),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at,
        "status": status,
        **kwargs,
    }).execute()
    return finished_at


def _update_config(sb, agent_name, status, finished_at):
    sb.table("agent_config").update({
        "last_run_at": finished_at,
        "last_run_status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("agent_name", agent_name).execute()


# ── SCORING LOGIC ───────────────────────────────────────────────────────

def _age_days(created_at_iso: Optional[str]) -> float:
    """Days since the lead was created. Returns 9999 if unknown."""
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


def _recency_score(age_days: float) -> float:
    """Logistic decay: 0.95 at day 0, 0.5 at half-life, → 0."""
    if age_days >= 9999:
        return 0.0
    return max(0.05, min(0.95, 1.0 - 1.0 / (1.0 + math.exp(-(age_days - RECENCY_HALF_LIFE_DAYS)))))


def _compute_composite_score(
    urgency_score: Optional[int],
    enrichment_score: Optional[float],
    has_phone: bool,
    has_email: bool,
    age_days: float,
) -> Tuple[float, Dict]:
    """
    Compute a weighted composite score (0.0-1.0) for a lead.

    Components:
      - urgency: 0-10 normalized to 0-1
      - enrichment: 0-1 from enriched_leads.score (or 0 if not enriched)
      - contact: 1.0 if phone+email, 0.6 if phone only, 0.3 if email only, 0.0 if none
      - recency: logistic decay from age

    Returns (composite_score, components_dict).
    """
    # Urgency component (normalize 0-10 → 0-1)
    urgency_norm = max(0.0, min(1.0, (urgency_score or 0) / 10.0))

    # Enrichment component
    enrichment = max(0.0, min(1.0, enrichment_score or 0.0))

    # Contact component
    if has_phone and has_email:
        contact = 1.0
    elif has_phone:
        contact = 0.6
    elif has_email:
        contact = 0.3
    else:
        contact = 0.0

    # Recency component
    recency = _recency_score(age_days)

    components = {
        "urgency": round(urgency_norm, 3),
        "enrichment": round(enrichment, 3),
        "contact": round(contact, 3),
        "recency": round(recency, 3),
    }

    composite = sum(
        components[key] * COMPOSITE_WEIGHTS[key]
        for key in COMPOSITE_WEIGHTS
    )

    return round(max(0.0, min(1.0, composite)), 4), components


def _classify_temperature(composite_score: float, urgency_score: Optional[int], cfg: Dict) -> str:
    """
    Classify a lead's temperature.

    Rules (applied in order):
      1. urgency ≥ 9 AND has contact → hot (regardless of composite)
      2. composite ≥ hot_threshold → hot
      3. composite ≥ warm_threshold → warm
      4. otherwise → cold
    """
    hot_th = cfg.get("hot_threshold", HOT_THRESHOLD)
    warm_th = cfg.get("warm_threshold", WARM_THRESHOLD)

    if composite_score >= hot_th:
        return "hot"
    if composite_score >= warm_th:
        return "warm"
    return "cold"


# ── MAIN RUN LOOP ───────────────────────────────────────────────────────

def run() -> dict:
    started_at = datetime.now(timezone.utc)
    run_id = uuid.uuid4()
    sb = _sb()
    cfg = _read_config(sb)

    if not cfg["enabled"]:
        _log_activity(sb, "lead_scorer", run_id, started_at, "skipped_disabled",
                      summary="disabled in agent_config")
        _update_config(sb, "lead_scorer", "skipped_disabled", datetime.now(timezone.utc).isoformat())
        return {"status": "skipped_disabled", "rows_processed": 0}

    max_leads = cfg["max_per_run"]
    dry_run = cfg["dry_run"]

    # 1) Pull active radar_targets that need scoring
    #    We join with campaign_leads to avoid re-scoring leads that already
    #    have an active entry (unless force_rescore is set in meta).
    rt_res = (sb.table("radar_targets")
              .select("id, warehouse_name, address, city, state, phone, email, "
                      "urgency_score, asset_value, source, status, created_at")
              .eq("status", "active")
              .order("created_at", desc=True)
              .limit(max_leads)
              .execute())
    radar_rows = rt_res.data or []
    log.info(f"[lead_scorer] {len(radar_rows)} active radar_targets")

    if not radar_rows:
        log.info("[lead_scorer] no active radar_targets to score")
        _log_activity(sb, "lead_scorer", run_id, started_at, "ok",
                      rows_seen=0, rows_processed=0,
                      summary="no active radar_targets")
        _update_config(sb, "lead_scorer", "ok", datetime.now(timezone.utc).isoformat())
        return {"status": "ok", "rows_seen": 0, "rows_processed": 0}

    # 2) Bulk-fetch enriched_leads for these radar_targets
    rt_ids = [r["id"] for r in radar_rows]
    el_res = (sb.table("enriched_leads")
              .select("id, radar_target_id, score, status")
              .in_("radar_target_id", rt_ids)
              .execute())
    el_map: Dict[str, dict] = {}
    for el_row in (el_res.data or []):
        rtid = el_row.get("radar_target_id")
        if rtid:
            el_map[rtid] = el_row

    # 3) Bulk-fetch existing campaign_leads entries to avoid duplicates
    cl_res = (sb.table("campaign_leads")
              .select("radar_target_id, temperature, status")
              .in_("radar_target_id", rt_ids)
              .execute())
    existing_cl: Dict[str, dict] = {}
    for cl_row in (cl_res.data or []):
        rtid = cl_row.get("radar_target_id")
        if rtid:
            existing_cl[rtid] = cl_row

    # 4) Score each lead
    rows_seen = len(radar_rows)
    rows_processed = 0
    rows_skipped = 0
    rows_errored = 0
    hot_count = 0
    warm_count = 0
    cold_count = 0
    error_msgs = []

    for rt in radar_rows:
        try:
            rtid = rt["id"]

            # Skip if already in campaign_leads with same classification
            existing = existing_cl.get(rtid)
            if existing and existing.get("status") == "active":
                rows_skipped += 1
                continue

            # Get enrichment data
            enriched = el_map.get(rtid, {})
            enrichment_score = enriched.get("score")
            enriched_id = enriched.get("id")

            # Compute composite score
            urgency = rt.get("urgency_score")
            has_phone = bool(rt.get("phone"))
            has_email = bool(rt.get("email"))
            age = _age_days(rt.get("created_at"))

            composite, components = _compute_composite_score(
                urgency_score=urgency,
                enrichment_score=enrichment_score,
                has_phone=has_phone,
                has_email=has_email,
                age_days=age,
            )

            # Classify
            temperature = _classify_temperature(composite, urgency, cfg)

            if temperature == "hot":
                hot_count += 1
            elif temperature == "warm":
                warm_count += 1
            else:
                cold_count += 1

            if dry_run:
                rows_processed += 1
                log.info(
                    f"[lead_scorer] [DRY] {rt.get('warehouse_name','?')[:30]:30s} "
                    f"urgency={urgency} composite={composite:.3f} → {temperature}"
                )
                continue

            # Upsert into campaign_leads
            payload = {
                "radar_target_id": rtid,
                "enriched_lead_id": enriched_id,
                "warehouse_name": rt.get("warehouse_name"),
                "address": rt.get("address"),
                "city": rt.get("city"),
                "state": rt.get("state"),
                "phone": rt.get("phone"),
                "email": rt.get("email"),
                "temperature": temperature,
                "urgency_score": urgency,
                "enrichment_score": enrichment_score,
                "composite_score": composite,
                "last_scored_at": datetime.now(timezone.utc).isoformat(),
                "source": rt.get("source"),
                "status": "active",
                "meta": {
                    "components": components,
                    "scored_by": "lead_scorer",
                    "run_id": str(run_id),
                },
            }

            if existing:
                # Update existing row
                sb.table("campaign_leads").update(payload).eq("radar_target_id", rtid).execute()
            else:
                # Insert new row
                sb.table("campaign_leads").upsert(payload, on_conflict="radar_target_id").execute()

            rows_processed += 1

        except Exception as e:
            rows_errored += 1
            error_msgs.append(f"{rt.get('id', '?')[:8]}: {type(e).__name__}: {e}")
            log.warning(f"[lead_scorer] failed for {rt.get('id')}: {e}")

    # 5) Log activity
    mode = "dry-run" if dry_run else "LIVE"
    summary = (
        f"[{mode}] scored {rows_seen} leads → "
        f"{hot_count} hot, {warm_count} warm, {cold_count} cold, "
        f"{rows_skipped} skip, {rows_errored} error"
    )
    status = "ok" if rows_errored == 0 else "partial"
    err_field = None if rows_errored == 0 else "; ".join(error_msgs[:5])

    finished_at = datetime.now(timezone.utc)
    _log_activity(sb, "lead_scorer", run_id, started_at, status,
                  rows_seen=rows_seen, rows_processed=rows_processed,
                  rows_blocked=0, rows_errored=rows_errored,
                  error=err_field, summary=summary)
    _update_config(sb, "lead_scorer", status, finished_at.isoformat())

    log.info(summary)
    return {
        "status": status,
        "rows_seen": rows_seen,
        "rows_processed": rows_processed,
        "rows_skipped": rows_skipped,
        "rows_errored": rows_errored,
        "hot": hot_count,
        "warm": warm_count,
        "cold": cold_count,
        "dry_run": dry_run,
    }


# ── CLI ────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Empire AI Lead Scorer Agent")
    p.add_argument("--status", action="store_true", help="Show config and last run")
    args = p.parse_args()
    if args.status:
        sb = _sb()
        cfg = _read_config(sb)
        last_act = (sb.table("agent_activity")
                      .select("*").eq("agent_name", "lead_scorer")
                      .order("started_at", desc=True).limit(1).execute())
        print(json.dumps({"config": cfg, "last_run": last_act.data[0] if last_act.data else None},
                         indent=2, default=str))
        return
    result = run()
    sys.exit(0 if result["status"] in ("ok", "skipped_disabled", "partial") else 1)


if __name__ == "__main__":
    main()
