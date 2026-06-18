"""
Empire AI · Predictive Revenue
Lead Enricher Agent (SI-Powered)
================================

Second of three agents in the lead-gen pipeline.

Reads enriched_leads (status=pending_enrichment), computes a predictive
score using the SI core's Bayesian beta-binomial model with feature
engineering, writes back with calibrated probability + status.

Features engineered from each lead:
  - Urgency: recency decay (logistic)
  - Completeness: % of required fields present
  - Asset value: keyword-match tier (high/medium/low)
  - Contact readiness: phone/email availability
  - Niche alignment: match vs service targets

Score is a Bayesian probability (0.0-1.0) calibrated by the SI core's
ProbabilityCalibrator, not a raw 0-10 heuristic.

Uses:
    python3 -m agents.lead_enricher
    python3 -m agents.lead_enricher --status
"""
import os
import sys
import json
import uuid
import math
import logging
import argparse
from datetime import datetime, timezone
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
from agents.event_emitter import emit_agent_event
from empire_si_core import SyntheticIntelligence, beta_posterior, get_si_core

log = logging.getLogger("empire.lead_enricher")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


# ── FEATURE WEIGHTS AND TIERS ───────────────────────────────────────────

_HIGH_VALUE_KEYWORDS = [
    "distribution", "logistics", "cold storage", "food",
    "manufacturing", "industrial", "freight", "fulfillment",
]
_MEDIUM_VALUE_KEYWORDS = ["retail", "store", "shop", "warehouse"]

# Niche alignment: which niches we actively target
_TARGET_NICHES = {
    "roofing", "hvac", "solar", "legal", "restoration",
    "construction", "logistics", "cpa", "medical",
}

# Required fields for data completeness
_REQUIRED_FIELDS = ["address", "city", "state", "warehouse_name"]

# Decay half-life in days (urgency score halves every N days)
_URGENCY_HALF_LIFE_DAYS = 7.0


# ── FEATURE ENGINEERING ─────────────────────────────────────────────────

def _age_days(created_at_iso: str) -> float:
    """Days since the lead was created."""
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


def _engineer_features(row: dict) -> Tuple[List[float], Dict]:
    """
    Engineer features from a lead row. Returns (feature_vector, trace).

    Feature vector (4 dimensions):
      [0] urgency_score: logistic decay 0->1 based on age
      [1] completeness_ratio: 0.0-1.0 fraction of required fields
      [2] asset_value_score: 0.0, 0.33, 0.66, or 1.0
      [3] contact_ready: 0.0 or 1.0
    """
    trace = {}

    # Feature 0: Urgency (logistic decay)
    age = _age_days(row.get("created_at"))
    # Logistic decay: starts at 0.95 for day 0, crosses 0.5 at half-life
    urgency = 1.0 - 1.0 / (1.0 + math.exp(-(age - _URGENCY_HALF_LIFE_DAYS)))
    urgency = max(0.05, min(0.95, urgency))
    trace["urgency"] = {"age_days": round(age, 1), "score": round(urgency, 3)}

    # Feature 1: Data completeness
    have = sum(1 for f in _REQUIRED_FIELDS if row.get(f))
    completeness = have / len(_REQUIRED_FIELDS)
    trace["completeness"] = {"have": have, "of": len(_REQUIRED_FIELDS), "ratio": completeness}

    # Feature 2: Asset value (keyword match)
    wh = (row.get("warehouse_name") or "").lower()
    asset_score = 0.0
    matched = None
    for kw in _HIGH_VALUE_KEYWORDS:
        if kw in wh:
            asset_score = 1.0
            matched = kw
            break
    if asset_score == 0.0:
        for kw in _MEDIUM_VALUE_KEYWORDS:
            if kw in wh:
                asset_score = 0.66
                matched = kw
                break
    if asset_score == 0.0 and wh:
        asset_score = 0.33  # has a name but no high-value match
    trace["asset_value"] = {"matched": matched, "score": asset_score}

    # Feature 3: Contact readiness
    contact = 1.0 if (row.get("phone") or row.get("email")) else 0.0
    trace["contact_ready"] = {"has_phone": bool(row.get("phone")),
                              "has_email": bool(row.get("email"))}

    features = [urgency, completeness, asset_score, contact]
    return features, trace


def _features_to_probability(features: List[float], wins: int = 0, losses: int = 0) -> Dict:
    """
    Convert feature vector to a calibrated probability using the SI core.

    Two components:
      1. Feature-based score: weighted linear combination
      2. Bayesian prior from historical outcomes (beta posterior)

    Final score is a Bayesian combination: the feature score acts as the
    likelihood, and the historical win rate acts as the prior.

    Formula:
      P(convert) = (prior_alpha + feature_wins) / (prior_alpha + prior_beta + feature_total)
    where feature_wins = feature_score * N (converted to pseudo-observations)
    """
    # Weights for each feature dimension
    WEIGHTS = [0.40, 0.15, 0.25, 0.20]  # urgency, completeness, asset, contact
    feature_score = sum(f * w for f, w in zip(features, WEIGHTS))
    feature_score = max(0.05, min(0.95, feature_score))

    # Bayesian combination with historical prior
    prior = beta_posterior(wins, losses)
    prior_mean = prior["mean"] if prior["mean"] > 0 else 0.5

    # Effective sample size from features (treat as 5 pseudo-observations)
    pseudo_n = 5.0
    pseudo_wins = feature_score * pseudo_n

    # Posterior: combine feature signal with historical prior
    total_alpha = prior["alpha"] + pseudo_wins
    total_beta = prior["beta"] + (pseudo_n - pseudo_wins)

    # Final calibrated probability
    posterior_mean = total_alpha / (total_alpha + total_beta) if (total_alpha + total_beta) > 0 else 0.5
    calibrated = max(0.01, min(0.99, posterior_mean))

    return {
        "feature_score": round(feature_score, 4),
        "prior_mean": round(prior_mean, 4),
        "posterior_mean": round(calibrated, 4),
        "prior_alpha": round(prior["alpha"], 2),
        "prior_beta": round(prior["beta"], 2),
        "pseudo_observations": pseudo_n,
    }


def _block_reason(row: dict, prob_result: Dict, threshold: float) -> Optional[str]:
    """Return a block reason string if the lead should be blocked."""
    if prob_result["posterior_mean"] >= threshold:
        return None
    if not row.get("warehouse_name"):
        return "below_threshold:no_warehouse_name"
    if not (row.get("phone") or row.get("email")):
        return "below_threshold:no_contact"
    return f"below_threshold:p={prob_result['posterior_mean']:.2f}"


# ── OUTCOME TRACKER (persistent within run) ─────────────────────────────

# Accumulates historical wins/losses for Bayesian prior computation
_OUTCOME_HISTORY: Dict = {"wins": 0, "losses": 0}


def load_outcome_history(sb) -> None:
    """Initialize _OUTCOME_HISTORY from enriched_leads outcomes."""
    global _OUTCOME_HISTORY
    try:
        r = sb.table("enriched_leads") \
            .select("status,score") \
            .in_("status", ["pending_outreach", "blocked", "contacted", "converted", "lost"]) \
            .limit(5000).execute()
        rows = r.data or []
        wins = sum(1 for row in rows if row.get("status") in ("contacted", "converted"))
        losses = sum(1 for row in rows if row.get("status") in ("blocked", "lost"))
        _OUTCOME_HISTORY = {"wins": wins, "losses": losses}
        log.info(f"[enricher] loaded outcome history: {wins} wins, {losses} losses ({len(rows)} total)")
    except Exception as e:
        log.warning(f"[enricher] could not load outcome history: {e}")


# ── SUPPORT FUNCTIONS ───────────────────────────────────────────────────

def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in env")
    return create_client(url, key)


def _read_config(sb, default_max=100, default_threshold=0.35):
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
    return emit_agent_event(
        sb=sb, agent_name=agent_name, run_id=run_id,
        started_at=started_at, status=status,
        rows_seen=rows_seen, rows_processed=rows_processed,
        rows_blocked=rows_blocked, rows_errored=rows_errored,
        error=error, summary=summary,
    )


def _update_config(sb, agent_name, status, finished_at):
    sb.table("agent_config").update({
        "last_run_at": finished_at,
        "last_run_status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("agent_name", agent_name).execute()


# ── MAIN RUN LOOP ───────────────────────────────────────────────────────

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

    # Load historical outcome data for Bayesian prior
    load_outcome_history(sb)

    # 1) Read pending rows
    rows_res = (sb.table("enriched_leads")
                  .select("id, radar_target_id, address, city, state, phone, email, "
                          "warehouse_name, asset_value, status, created_at, meta")
                  .eq("status", "pending_enrichment")
                  .order("created_at", desc=False)
                  .limit(cfg["max_per_run"])
                  .execute())
    rows = rows_res.data or []
    log.info(f"[enricher] {len(rows)} pending rows")
    rows_seen = len(rows)
    if not rows:
        log.info("[enricher] no pending rows")
        return {"status": "ok", "rows_seen": 0, "rows_processed": 0}

    # 2) Score each row
    rows_processed = 0
    rows_blocked = 0
    rows_errored = 0
    error_msgs = []
    predictions = []   # for SI core calibration feedback
    outcomes = []      # for SI core calibration feedback

    si = get_si_core()

    for row in rows:
        try:
            # Engineer features
            features, trace = _engineer_features(row)

            # Bayesian probability score
            prob_result = _features_to_probability(
                features,
                wins=_OUTCOME_HISTORY["wins"],
                losses=_OUTCOME_HISTORY["losses"],
            )

            score = prob_result["posterior_mean"]
            threshold = cfg["min_score_threshold"]
            above = score >= threshold

            new_status = "pending_outreach" if above else "blocked"
            if not above:
                rows_blocked += 1
            block_reason = _block_reason(row, prob_result, threshold)

            # Merge trace and scoring data into meta
            existing_meta = row.get("meta") or {}
            new_meta = dict(existing_meta)
            new_meta["feature_vector"] = [round(f, 3) for f in features]
            new_meta["feature_trace"] = trace
            new_meta["probability"] = prob_result
            new_meta["enrichment_block_reason"] = block_reason
            new_meta["enrichment_scored_at"] = datetime.now(timezone.utc).isoformat()

            sb.table("enriched_leads").update({
                "score": score,
                "status": new_status,
                "last_enriched_at": datetime.now(timezone.utc).isoformat(),
                "meta": new_meta,
            }).eq("id", row["id"]).execute()
            rows_processed += 1

            # Track predictions for SI core calibration
            predictions.append(score)
            outcomes.append(1 if above else 0)

        except Exception as e:
            rows_errored += 1
            error_msgs.append(f"{row.get('id', '?')[:8]}: {type(e).__name__}: {e}")
            log.warning(f"[enricher] failed for {row.get('id')}: {e}")

    # 3) Feed prediction-outcome pairs to SI core calibrator
    if predictions:
        try:
            calibration = si.evolve_logic({
                "predictions": predictions,
                "outcomes": outcomes,
                "revenues": [0.0] * len(predictions),
                "niche": "lead_enricher",
            })
            log.info(
                f"[enricher] SI calibration: a={calibration['calibration']['a']:.3f} "
                f"b={calibration['calibration']['b']:.3f}"
            )
        except Exception as e:
            log.debug(f"[enricher] calibration feedback failed: {e}")

    finished_at = datetime.now(timezone.utc)
    passed = rows_seen - rows_blocked - rows_errored
    summary = (
        f"scored {rows_seen} rows, {rows_processed} updated "
        f"({passed} to pending_outreach, {rows_blocked} to blocked), "
        f"{rows_errored} errored"
    )
    status = "ok" if rows_errored == 0 else "partial"
    err_field = None if rows_errored == 0 else "; ".join(error_msgs[:5])

    _log_activity(sb, "lead_enricher", run_id, started_at, status,
                  rows_seen=rows_seen, rows_processed=rows_processed,
                  rows_blocked=rows_blocked, rows_errored=rows_errored,
                  error=err_field, summary=summary)
    _update_config(sb, "lead_enricher", status, finished_at.isoformat())

    log.info(summary)
    return {
        "status": status,
        "rows_seen": rows_seen,
        "rows_processed": rows_processed,
        "rows_blocked": rows_blocked,
        "rows_errored": rows_errored,
        "threshold_used": cfg["min_score_threshold"],
        "calibrated": len(predictions),
    }


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
    sys.exit(0 if result["status"] in ("ok", "skipped_disabled", "partial") else 1)


if __name__ == "__main__":
    main()
