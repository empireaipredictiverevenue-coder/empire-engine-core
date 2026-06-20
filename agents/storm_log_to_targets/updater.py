"""
EMPIRE V49 · STORM LOG TO TARGETS PIPELINE
===========================================
Reads storm_risk_log and applies metro-level risk to active radar_targets.

This agent fills the gap between:
  - warp_scout / storm_alert (which write metro-level risk to storm_risk_log)
  - radar_targets (which need property-level damage_severity + urgency_score)

Logic per run:
  1. Query storm_risk_log for the latest risk data per metro (aggregates
     across days, takes the max risk_rank for each metro)
  2. Filter to metros with risk_rank >= min_risk_rank threshold
  3. For each metro, query active radar_targets in that metro area
     (city-based matching using _METRO_ALIASES)
  4. Map risk_level → damage_severity and risk_rank → urgency_score
  5. Update radar_targets rows (upgrades only — never downgrades)

Cron: every 30 min (runs alongside storm_alert for complementary coverage).

Usage:
    python3 -m agents.storm_log_to_targets
    python3 -m agents.storm_log_to_targets --dry-run
    python3 -m agents.storm_log_to_targets --status
"""

import os
import sys
import json
import uuid
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
from agents.event_emitter import emit_agent_event

log = logging.getLogger("empire.storm_log_to_targets")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

AGENT_NAME = "storm_log_to_targets"

# ── Metro name → city alias matching (sync with empire_satellite_strike.py) ──
_METRO_ALIASES: Dict[str, List[str]] = {
    "Dallas-Fort Worth":   ["dallas", "fort worth", "dfw", "arlington", "plano", "irving", "garland", "mesquite", "carrollton", "frisco", "mckinney", "denton", "lewisville", "richardson", "allen"],
    "Dallas":              ["dallas", "dfw"],
    "Fort Worth":          ["fort worth", "ft worth"],
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
    # ── Florida ──
    "Miami":               ["miami", "fort lauderdale", "hialeah", "miami beach", "coral gables", "davie", "pembroke pines", "hollywood fl"],
    "Tampa":               ["tampa", "st petersburg", "clearwater", "brandon", "riverview", "largo", "tampa fl"],
    "Orlando":             ["orlando", "kissimmee", "sanford", "winter park", "maitland", "altamonte springs", "orlando fl"],
    "Jacksonville":        ["jacksonville", "jacksonville beach", "atlantic beach", "neptune beach", "orange park", "fl"],
    "Fort Myers":          ["fort myers", "cape coral", "naples", "bonita springs", "estero"],
    "Pensacola":           ["pensacola", "gulf breeze", "navarre", "pace", "milton fl"],
    "Tallahassee":         ["tallahassee", "crawfordville", "havana"],
    # ── Gulf Coast ──
    "Mobile":              ["mobile", "daphne", "fairhope", "foley", "spanish fort", "al"],
    "Birmingham":          ["birmingham", "hoover", "bessemer", "vestavia", "alabaster", "birmingham al"],
    "Baton Rouge":         ["baton rouge", "prarieville", "zachary", "central", "walker", "denham springs", "la"],
    "Jackson MS":          ["jackson ms", "clinton", "byram", "richland", "ridgeland"],
    "Gulfport":            ["gulfport", "biloxi", "ocean springs", "long beach ms", "pass christian", "diberville", "ms"],
    # ── Carolinas ──
    "Charlotte":           ["charlotte", "concord nc", "gastonia", "rock hill", "huntersville", "hickory", "matthews", "pineville", "nc"],
    "Raleigh":             ["raleigh", "durham", "cary", "chapel hill", "apex", "holly springs", "morrisville", "wake forest", "nc"],
    "Wilmington":          ["wilmington nc", "jacksonville nc", "lelände", "carolina beach", "wrightsville beach"],
    "Columbia":            ["columbia sc", "lexington sc", "irmo", "cayce", "west columbia"],
    "Charleston":          ["charleston sc", "mount pleasant", "north charleston", "summerville", "goose creek", "hanahan"],
    "Myrtle Beach":        ["myrtle beach", "conway sc", "north myrtle beach", "surfside beach", "garden city"],
    # ── Midwest / Plains ──
    "Denver":              ["denver", "aurora co", "lakewood", "westminster co", "arvada", "centennial", "thornton", "boulder", "littleton", "broomfield", "highlands ranch", "co"],
    "St. Louis":           ["st louis", "st. louis", "saint louis", "chesterfield", "florissant", "o'fallon mo", "st charles", "st peters", "mo"],
    "Springfield MO":      ["springfield mo", "nixa", "ozark", "republic"],
    "Little Rock":         ["little rock", "north little rock", "conway ar", "sherwood", "benton", "cabot", "ar"],
    "Omaha":               ["omaha", "lincoln", "council bluffs", "bellevue", "papillion", "la vista"],
    "Des Moines":          ["des moines", "ankeny", "west des moines", "urbandale", "clive", "johnston", "ia"],
    "Waco":                ["waco", "woodway", "hewitt", "robinson", "bellmead", "mcgill"],
    "Temple":              ["temple tx", "belton", "harker heights", "nolanville"],
    "Bryan/College Station": ["bryan", "college station", "b/cs"],
    "Tyler":               ["tyler tx", "whitehouse", "bullard"],
    "Lubbock":             ["lubbock", "wolfforth", "shallowater", "slaton"],
    "Amarillo":            ["amarillo", "canyon", "borger"],
    "El Paso":             ["el paso", "socorro", "horizon city"],
    "Corpus Christi":       ["corpus Christi", "portland tx", "kingsville", "alice"],
    # ── Mid-Atlantic / Northeast ──
    "Richmond":            ["richmond va", "henrico", "chesterfield", "midlothian", "glen allen", "va"],
    "Virginia Beach":      ["virginia beach", "norfolk", "chesapeake", "newport news", "hampton", "portsmouth va", "suffolk va", "va beach"],
    "Philadelphia":        ["philadelphia", "philly", "camden", "cherry hill", "upper darby", "bala cynwyd"],
    "New York City":       ["new york", "manhattan", "brooklyn", "queens", "bronx", "staten island", "nyc"],
    "Boston":              ["boston", "cambridge ma", "somerville", "newton", "quincy", "brookline ma"],
    # ── Ohio Valley ──
    "Indianapolis":        ["indianapolis", "fishers", "carmel", "noblesville", "greenwood", "plainfield", "avon in", "in"],
    "Columbus":            ["columbus oh", "dublin", "gahanna", "westerville", "hilliard", "grove city"],
    "Louisville":          ["louisville", "lexington ky", "bowling green", "owensboro", "elizabethtown", "ky"],
    # ── County-name variants from NWS storm_alert ────────────────────
    # NWS areaDesc uses county names (e.g. "Dallas, TX") not metro names.
    # These entries bridge the gap so storm_log_to_targets can match
    # county-name entries written by storm_alert into storm_risk_log.
    # Lists share references with parent metro entries (immutable at runtime).
    "Dallas, TX":        ["dallas", "dfw", "arlington", "plano", "irving", "garland", "mesquite", "carrollton", "frisco", "mckinney", "denton", "lewisville", "richardson", "allen"],
    "Collin, TX":        ["plano", "frisco", "mckinney", "allen", "richardson", "wylie", "princeton", "celina", "anna", "melissa", "fairview", "lucas", "parker", "dallas"],
    "Hunt, TX":          ["greenville tx", "commerce tx", "quinlan", "caddo mills", "lone oak", "wolfe city"],
    "Tarrant, TX":       ["fort worth", "arlington", "ft worth", "bedford", "euless", "grapevine", "hurst", "colleyville", "southlake", "keller", "north richland hills"],
    "Denton, TX":        ["denton", "lewisville", "flower mound", "highland village", "coppell", "the colony", "frisco", "little elm", "lake dallas"],
    "Ellis, TX":         ["waxahachie", "ennis", "midlothian", "red oak", "lancaster", "italy tx", "ferris"],
    "Johnson, TX":       ["cleburne", "burleson", "alvarado", "keene"],
    "Rockwall, TX":      ["rockwall", "rowlett", "garland", "heath", "fate"],
    "Kaufman, TX":       ["kaufman", "terrell", "forney", "crandall", "talty", "mesquite"],
    "Parker, TX":        ["weatherford", "aledo", "willow park", "hudson oaks"],
    "Harris, TX":        ["houston", "sugar land", "pearland", "pasadena", "cypress", "katy", "spring", "missouri city"],
    "Montgomery, TX":    ["the woodlands", "conroe", "spring", "magnolia", "montgomery tx", "splendora"],
    "Fort Bend, TX":     ["sugar land", "missouri city", "richmond tx", "rosenberg", "stafford", "katy"],
    "Brazoria, TX":      ["pearland", "alvin", "angleton", "lake jackson", "freeport", "clute"],
    "Galveston, TX":     ["galveston", "texas city", "league city", "la marque", "santa fe", "dickinson"],
    "Travis, TX":        ["austin", "rollingwood", "sunset valley"],
    "Williamson, TX":    ["round rock", "cedar park", "georgetown", "leander", "hutto", "taylor", "pflugerville"],
    "Hays, TX":          ["san marcos", "kyle", "buda", "dripping springs", "wimberley"],
    "Bexar, TX":         ["san antonio", "schertz", "converse", "cibolo"],
    "Comal, TX":         ["new braunfels", "garden ridge", "bulverde", "canyon lake"],
    "Guadalupe, TX":     ["schertz", "cibolo", "seguin", "marion", "new berlin"],
    "Bastrop, TX":       ["bastrop", "elgin", "smithville"],
    "Caldwell, TX":      ["lockhart", "luling"],
    "McLennan, TX":      ["waco", "woodway", "hewitt", "robinson", "bellmead", "mcgregor", "west tx"],
    "Bell, TX":          ["temple tx", "belton", "harker heights", "killeen", "copperas cove", "nolanville"],
    "Coryell, TX":       ["gatesville", "copperas cove", "oglesby"],
    "Smith, TX":         ["tyler tx", "whitehouse", "bullard", "lindale"],
    "Gregg, TX":         ["longview", "white oak", "kilgore"],
    "Bowie, TX":         ["texarkana"],
    "Lubbock, TX":       ["lubbock", "wolfforth", "shallowater", "slaton"],
    "Potter, TX":        ["amarillo"],
    "Randall, TX":       ["canyon"],
    "El Paso, TX":       ["el paso", "socorro", "horizon city"],
    "Nueces, TX":        ["corpus christi", "portland tx", "kingsville", "robstown", "agua dulce"],
    "Webb, TX":          ["laredo"],
    "Hidalgo, TX":       ["mcallen", "edinburg", "pharr", "mission", "weslaco", "donna"],
    "Cameron, TX":       ["brownsville", "harlingen", "san benito", "los fresnos"],
}

# ── Risk rank → damage_severity + urgency_score mapping ──────────────────
# risk_rank from storm_predictor: 1=Thunderstorm, 2=Marginal, 3=Slight,
# 4=Enhanced, 5=Moderate, 6=High
# urgency_score: 1-10 scale consistent with storm_alert.py
_RISK_RANK_MAP: Dict[int, Tuple[str, int]] = {
    1: ("Light",     2),   # Thunderstorm
    2: ("Light",     3),   # Marginal
    3: ("Moderate",  5),   # Slight
    4: ("Moderate",  7),   # Enhanced
    5: ("Severe",    8),   # Moderate
    6: ("Severe",    9),   # High
}

# Minimum risk_rank to act on (4 = Enhanced or higher)
DEFAULT_MIN_RISK_RANK = 4


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)


def _read_config(sb):
    r = sb.table("agent_config").select("*").eq("agent_name", AGENT_NAME).limit(1).execute()
    if not r.data:
        return {"enabled": True, "dry_run": True, "min_risk_rank": DEFAULT_MIN_RISK_RANK}
    row = r.data[0]
    cfg = row.get("config_json") or {}
    return {
        "enabled":      row.get("enabled", True),
        "dry_run":      row.get("dry_run", True),
        "min_risk_rank": cfg.get("min_risk_rank", DEFAULT_MIN_RISK_RANK),
    }


def _update_config(sb, status, finished_at):
    sb.table("agent_config").update({
        "last_run_at": finished_at,
        "last_run_status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("agent_name", AGENT_NAME).execute()


def _log_activity(sb, run_id, started_at, status,
                  rows_seen=0, rows_processed=0, rows_blocked=0, rows_errored=0,
                  error=None, summary=None):
    return emit_agent_event(
        sb=sb, agent_name=AGENT_NAME, run_id=run_id,
        started_at=started_at, status=status,
        rows_seen=rows_seen, rows_processed=rows_processed,
        rows_blocked=rows_blocked, rows_errored=rows_errored,
        error=error, summary=summary,
    )


def _fetch_metro_risk(sb, lookback_hours: int = 48) -> List[Dict]:
    """Query storm_risk_log for the latest risk per metro (max risk_rank)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).isoformat()
    r = sb.table("storm_risk_log") \
        .select("metro, risk_level, risk_rank") \
        .gte("created_at", cutoff) \
        .execute()
    rows = r.data or []
    if not rows:
        return []

    # Aggregate per-metro: take the highest risk_rank seen in the lookback window
    metro_risk: Dict[str, Dict] = {}
    for row in rows:
        metro = (row.get("metro") or "").strip()
        rank = int(row.get("risk_rank") or 0)
        if not metro:
            continue
        current = metro_risk.get(metro)
        if not current or rank > current["risk_rank"]:
            metro_risk[metro] = {
                "metro": metro,
                "risk_level": row.get("risk_level", ""),
                "risk_rank": rank,
            }

    return list(metro_risk.values())


def _find_targets_for_metro(sb, metro: str, aliases: List[str]) -> List[Dict]:
    """Query active radar_targets in a metro by matching city against aliases."""
    try:
        # Build OR filter: city ILIKE any of the aliases
        or_parts = ",".join([f"city.ilike.%{a}%" for a in aliases])
        r = sb.table("radar_targets") \
            .select("id, city, state, damage_severity, urgency_score") \
            .eq("status", "active") \
            .or_(or_parts) \
            .execute()
        return r.data or []
    except Exception as e:
        log.warning(f"[{AGENT_NAME}] radar_targets query for metro={metro} failed: {e}")
        return []


def run_once(dry_run_override: Optional[bool] = None) -> dict:
    """Run one pipeline cycle.

    1. Fetch latest per-metro risk from storm_risk_log
    2. For each risk metro, find active radar_targets
    3. Map risk → damage_severity + urgency_score
    4. Update radar_targets (upgrades only)
    5. Log to storm_risk_log + agent_activity
    """
    started_at = datetime.now(timezone.utc)
    run_id = uuid.uuid4()
    sb = _sb()
    cfg = _read_config(sb)
    dry_run = cfg["dry_run"] if dry_run_override is None else dry_run_override
    min_rank = cfg["min_risk_rank"]

    if not cfg["enabled"]:
        msg = "agent disabled in agent_config — skipping"
        log.info(msg)
        _log_activity(sb, run_id, started_at, "skipped", summary=msg)
        return {"status": "skipped", "reason": msg}

    # ── 1. Fetch metro risk data ──────────────────────────────────────
    metro_risks = _fetch_metro_risk(sb, lookback_hours=48)
    if not metro_risks:
        summary = "storm_risk_log has no entries in the last 48h — nothing to apply"
        log.info(summary)
        _log_activity(sb, run_id, started_at, "ok", summary=summary)
        return {"status": "ok", "note": summary}

    # Filter by min_risk_rank
    qualifying = [m for m in metro_risks if m["risk_rank"] >= min_rank]
    if not qualifying:
        summary = (
            f"{len(metro_risks)} metros with risk data, "
            f"none above min_risk_rank={min_rank}"
        )
        log.info(summary)
        _log_activity(sb, run_id, started_at, "ok", summary=summary)
        return {"status": "ok", "note": summary, "metros_scanned": len(metro_risks)}

    log.info(
        f"[{AGENT_NAME}] {len(qualifying)} qualifying metros "
        f"(out of {len(metro_risks)} total): "
        + ", ".join(f"{m['metro']}(rank={m['risk_rank']})" for m in qualifying)
    )

    # ── 2. Find targets per qualifying metro ──────────────────────────
    total_targets_found = 0
    updates_to_apply: Dict[str, Tuple[str, int]] = {}  # target_id → (severity, urgency)

    for metro in qualifying:
        aliases = _METRO_ALIASES.get(metro["metro"])
        if not aliases:
            log.debug(f"[{AGENT_NAME}] no alias map for metro={metro['metro']}, skipping")
            continue

        targets = _find_targets_for_metro(sb, metro["metro"], aliases)
        total_targets_found += len(targets)

        # Map risk → severity + urgency
        sev, urg = _RISK_RANK_MAP.get(metro["risk_rank"], ("Moderate", 5))

        for t in targets:
            tid = t["id"]
            old_sev = (t.get("damage_severity") or "").lower()
            old_urg = int(t.get("urgency_score") or 0)

            # Upgrade only: never downgrade
            current = updates_to_apply.get(tid)
            current_urg = current[1] if current else old_urg

            if urg > current_urg:
                updates_to_apply[tid] = (sev, urg)

    if not updates_to_apply:
        summary = (
            f"Found {total_targets_found} targets across {len(qualifying)} metros, "
            f"none needed upgrade"
        )
        log.info(summary)
        _log_activity(sb, run_id, started_at, "ok",
                      rows_seen=total_targets_found, summary=summary)
        return {"status": "ok", "note": summary, "targets_checked": total_targets_found}

    # ── 3. Apply updates ─────────────────────────────────────────────
    updated = 0
    errors = 0
    if not dry_run:
        now_iso = datetime.now(timezone.utc).isoformat()
        for tid, (sev, urg) in updates_to_apply.items():
            try:
                sb.table("radar_targets").update({
                    "damage_severity": sev,
                    "urgency_score": urg,
                    "updated_at": now_iso,
                }).eq("id", tid).execute()
                updated += 1
            except Exception as e:
                log.warning(f"Failed to update target {tid[:12]}: {e}")
                errors += 1

    summary = (
        f"[{'DRY-RUN' if dry_run else 'LIVE'}] "
        f"metros={len(qualifying)} "
        f"targets_found={total_targets_found} "
        f"targets_upgraded={len(updates_to_apply)} "
        f"targets_updated={updated} "
        f"errors={errors}"
    )
    log.info(summary)
    finished_at = _log_activity(
        sb, run_id, started_at, "ok",
        rows_seen=total_targets_found,
        rows_processed=updated,
        rows_errored=errors,
        summary=summary[:500],
    )
    _update_config(sb, "ok", finished_at)

    return {
        "status": "ok",
        "metros_qualifying": len(qualifying),
        "metros_detail": [
            {"metro": m["metro"], "risk_level": m["risk_level"], "risk_rank": m["risk_rank"]}
            for m in qualifying
        ],
        "targets_found": total_targets_found,
        "targets_upgraded": len(updates_to_apply),
        "targets_updated": updated,
        "errors": errors,
        "dry_run": dry_run,
    }


# ── CLI ────────────────────────────────────────────────────────────────

def show_status():
    """Print agent status and recent run history."""
    sb = _sb()
    r = sb.table("agent_config").select("*").eq("agent_name", AGENT_NAME).limit(1).execute()
    if r.data:
        row = r.data[0]
        cfg = row.get("config_json") or {}
        print(f"agent:         {AGENT_NAME}")
        print(f"enabled:       {row.get('enabled')}")
        print(f"dry_run:       {row.get('dry_run')}")
        print(f"min_risk_rank: {cfg.get('min_risk_rank', DEFAULT_MIN_RISK_RANK)}")
        print(f"last_run_at:   {row.get('last_run_at')}")
        print(f"last_status:   {row.get('last_run_status')}")
    else:
        print(f"agent:         {AGENT_NAME}  (not initialized — run once to create config)")
    print()
    r2 = sb.table("agent_activity").select(
        "started_at,status,rows_seen,rows_processed,summary"
    ).eq("agent_name", AGENT_NAME).order("started_at", desc=True).limit(5).execute()
    print("recent runs:")
    for row in r2.data:
        sa = (row.get("started_at") or "")[:19]
        st = row.get("status", "")
        rs = row.get("rows_seen", 0)
        rp = row.get("rows_processed", 0)
        sm = (row.get("summary") or "")[:80]
        print(f"  {sa}  {st:10}  seen={rs}  updated={rp}  {sm}")
    print()
    # Show storm_risk_log entries
    r3 = sb.table("storm_risk_log").select("created_at,metro,risk_level,risk_rank") \
        .eq("source", AGENT_NAME).order("created_at", desc=True).limit(8).execute()
    if r3.data:
        print("recent storm_risk_log entries (from this agent):")
        for row in r3.data:
            ca = (row.get("created_at") or "")[:19]
            m  = (row.get("metro") or "")[:30]
            rl = row.get("risk_level", "")
            rr = row.get("risk_rank", 0)
            print(f"  {ca}  {m:30s}  {rl:12}  rank={rr}")


def main():
    p = argparse.ArgumentParser(
        description="Empire AI Storm Log → Radar Targets Pipeline"
    )
    p.add_argument("--dry-run", action="store_true",
                   help="report only, no DB writes")
    p.add_argument("--status", action="store_true",
                   help="print last run + stats")
    args = p.parse_args()
    if args.status:
        show_status()
        return
    result = run_once(dry_run_override=True if args.dry_run else None)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
