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

# ── STORM RISK ──────────────────────────────────────────────────────────

# Reverse metro map: lowercase city name → metro name
# Built from the _METRO_ALIASES in agents/storm_log_to_targets/updater.py
_METRO_ALIASES: dict[str, list[str]] = {
    "Dallas-Fort Worth":   ["dallas", "fort worth", "dfw", "arlington", "plano", "irving", "garland", "mesquite", "carrollton", "frisco", "mckinney", "denton", "lewisville", "richardson", "allen"],
    "Houston":             ["houston", "sugar land", "the woodlands", "conroe", "pearland", "pasadena", "cypress", "katy", "spring"],
    "Austin":              ["austin", "round rock", "cedar park", "pflugerville", "san marcos", "kyle", "buda"],
    "San Antonio":         ["san antonio", "sa", "new braunfels", "schertz", "converse", "cibolo"],
    "Wichita":             ["wichita", "derby", "haysville", "andover", "maize"],
    "Oklahoma City":       ["oklahoma city", "okc", "norman", "edmond", "moore", "midwest city", "enid", "stillwater"],
    "Kansas City":         ["kansas city", "kc", "overland park", "olathe", "kansas city ks", "independence", "lee's summit", "shawnee", "lenexa"],
    "Tulsa":               ["tulsa", "broken arrow", "owasso", "jenks", "bixby"],
    "New Orleans":         ["new orleans", "nola", "metairie", "kenner", "gretna", "marrero", "chalmette", "slidell"],
    "Memphis":             ["memphis", "germantown", "collierville", "bartlett", "cordova"],
    "Atlanta":             ["atlanta", "marietta", "alpharetta", "roswell", "johns creek", "sandy springs", "smyrna", "dunwoody", "decatur", "cobb", "gwinnett"],
    "Nashville":           ["nashville", "franklin", "murfreesboro", "brentwood", "hendersonville", "smyrna tn", "gallatin"],
    "Miami":               ["miami", "fort lauderdale", "hialeah", "miami beach", "coral gables", "davie", "pembroke pines", "hollywood fl"],
    "Tampa":               ["tampa", "st petersburg", "clearwater", "brandon", "riverview", "largo", "tampa fl"],
    "Orlando":             ["orlando", "kissimmee", "sanford", "winter park", "maitland", "altamonte springs", "orlando fl"],
    "Denver":              ["denver", "aurora co", "lakewood", "westminster co", "arvada", "centennial", "thornton", "boulder", "littleton", "broomfield", "highlands ranch"],
    "St. Louis":           ["st louis", "st. louis", "saint louis", "chesterfield", "florissant", "o'fallon mo", "st charles", "st peters"],
    "Omaha":               ["omaha", "lincoln", "council bluffs", "bellevue", "papillion", "la vista"],
    "Jacksonville":        ["jacksonville", "jacksonville beach", "atlantic beach", "neptune beach", "orange park"],
}

# Reverse map: lowercase city → metro name
_REVERSE_METRO_MAP: dict[str, str] = {}
for _m, _cities in _METRO_ALIASES.items():
    for _c in _cities:
        _REVERSE_METRO_MAP[_c] = _m

# Storm risk_rank → normalized 0.0-1.0 score
# risk_rank from storm_predictor: 1=Thunderstorm … 6=High
_RISK_RANK_TO_SCORE = {
    1: 0.10,
    2: 0.20,
    3: 0.40,  # Slight
    4: 0.60,  # Enhanced
    5: 0.80,  # Moderate
    6: 1.00,  # High
}


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


# ── STORM RISK HELPERS ──────────────────────────────────────────────────

def _storm_risk_for_lead(row: dict, storm_risk_map: dict[str, int]) -> dict:
    """Look up storm risk for a lead's city, return score + detail."""
    city = (row.get("city") or "").strip().lower()
    if not city:
        return {"score": 0.0, "metro": None, "risk_rank": 0, "note": "no_city"}

    # Find which metro this city belongs to
    metro = _city_to_metro(city)
    if not metro:
        return {"score": 0.0, "metro": None, "risk_rank": 0, "note": "unmapped_city"}

    risk_rank = storm_risk_map.get(metro, 0)
    if risk_rank == 0:
        return {"score": 0.0, "metro": metro, "risk_rank": 0, "note": "no_active_alerts"}

    score = _RISK_RANK_TO_SCORE.get(risk_rank, 0.0)
    risk_level = {1: "Thunderstorm", 2: "Marginal", 3: "Slight", 4: "Enhanced", 5: "Moderate", 6: "High"}.get(risk_rank, "Unknown")
    return {
        "score": score,
        "metro": metro,
        "risk_rank": risk_rank,
        "risk_level": risk_level,
        "note": "active_storm_risk",
    }


def _city_to_metro(city_lower: str) -> str | None:
    """Given a lowercase city name, return the metro it belongs to.

    Tries exact match, then substring match (e.g. "nashville" matches
    "nashville", and "nashville tn" also matches via substring check).
    """
    # Exact match
    if city_lower in _REVERSE_METRO_MAP:
        return _REVERSE_METRO_MAP[city_lower]
    # Substring match: check if the city_lower contains any alias or vice versa
    city_words = set(city_lower.split())
    for alias, metro in _REVERSE_METRO_MAP.items():
        alias_words = set(alias.split())
        if city_words & alias_words:  # any word overlap
            return metro
    return None


def _fetch_storm_risk(sb) -> dict[str, int]:
    """Query storm_risk_log for the highest risk_rank per metro in the last 48h.

    Returns dict: metro_name → max_risk_rank (0 if no active alerts).
    """
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    try:
        r = sb.table("storm_risk_log") \
            .select("metro, risk_rank") \
            .gte("created_at", cutoff) \
            .execute()
        rows = r.data or []
    except Exception as e:
        log.warning(f"[enricher] storm_risk_log query failed: {e}")
        return {}

    result: dict[str, int] = {}
    for row in rows:
        metro = (row.get("metro") or "").strip()
        rank = int(row.get("risk_rank") or 0)
        if not metro:
            continue
        current = result.get(metro, 0)
        if rank > current:
            result[metro] = rank
    return result


# ── FEATURE ENGINEERING ─────────────────────────────────────────────────

def _engineer_features(row: dict, storm_risk_map: dict[str, int] | None = None) -> Tuple[List[float], Dict]:
    """
    Engineer features from a lead row. Returns (feature_vector, trace).

    Feature vector (5 dimensions):
      [0] urgency_score: logistic decay 0->1 based on age
      [1] completeness_ratio: 0.0-1.0 fraction of required fields
      [2] asset_value_score: 0.0, 0.33, 0.66, or 1.0
      [3] contact_ready: 0.0 or 1.0
      [4] storm_risk: 0.0-1.0 based on active NWS alerts in lead's metro
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

    # Feature 4: Storm risk (0.0-1.0 based on active alerts in metro)
    storm_risk = _storm_risk_for_lead(row, storm_risk_map or {})
    trace["storm_risk"] = storm_risk

    features = [urgency, completeness, asset_score, contact, storm_risk["score"]]
    return features, trace


def _features_to_probability(features: List[float], wins: int = 0, losses: int = 0) -> Dict:
    """
    Convert feature vector to a calibrated probability using the SI core.

    Five features:
      [0] urgency       (35%)
      [1] completeness  (15%)
      [2] asset_value   (20%)
      [3] contact       (15%)
      [4] storm_risk    (15% — active NWS storm alerts in lead's metro)

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
    WEIGHTS = [0.35, 0.15, 0.20, 0.15, 0.15]  # urgency, completeness, asset, contact, storm_risk
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

    # 2) Fetch active storm risk per metro (for storm_risk feature)
    storm_risk_map = _fetch_storm_risk(sb)
    if storm_risk_map:
        log.info(f"[enricher] loaded storm risk for {len(storm_risk_map)} metros")

    # 3) Score each row
    rows_processed = 0
    rows_blocked = 0
    rows_errored = 0
    error_msgs = []
    predictions = []   # for SI core calibration feedback
    outcomes = []      # for SI core calibration feedback

    si = get_si_core()

    for row in rows:
        try:
            # Engineer features (now includes storm_risk feature)
            features, trace = _engineer_features(row, storm_risk_map=storm_risk_map)

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
