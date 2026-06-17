"""
Empire AI - Predictive Revenue
Quality Control Agent
==========================

A long-running daemon (NOT a cron tick) that watches the lead-gen
+ recruitment pipeline for anomalies and auto-remediates the safe
ones. Tier 1: auto-fix without pinging. Tier 2: log + Telegram
ping. Tier 3: daily summary rolled up at 23:00 UTC.

Runs as a pm2-managed async loop. Polls every 60s. Each tick:
  1. Check the dispatcher for missed sequences (active, due, no
     recent sms_log entry) -> reschedule and log
  2. Check for sequences whose failed_send_count >= 3 but are
     still status=active (gate regression) -> mark replied, log
  3. Check for 422 bursts (more than N failures in the last 10 min
     on a single phone) -> tier-2 ping
  4. Check for templates with unrendered placeholders in delivered
     sms_log rows -> tier-2 ping
  5. Check for enriched_lead marked converted in the last hour with
     no matching sms_sequence -> tier-2 ping
  6. Check for stale contractor rows (last_dispatched_at > 30d) ->
     tier-2 ping
  7. Check for duplicate enriched_leads by (phone, address) created
     in the last hour -> tier-1 dedupe
  8. At 23:00 UTC, write the daily summary row to qc_events

The agent is read-only against the dispatcher state and writes only
to qc_events (and the explicit auto-remediations). It does NOT
touch sms_sequences, sms_log, enriched_leads, contractors, etc.
except for the explicit auto-remediation cases.

Usage:
    python3 -m agents.sms_qc               # run the loop
    python3 -m agents.sms_qc --status     # one-shot read of recent events
"""
import os
import sys
import re
import json
import uuid
import logging
import asyncio
import subprocess
import argparse
from datetime import datetime, timezone, timedelta
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

log = logging.getLogger("empire.sms_qc")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


# ----------------------------------------------------------------------------
# Tunables
# ----------------------------------------------------------------------------
POLL_INTERVAL_S = 60                 # how often the daemon polls
DISPATCHER_MISS_GRACE_S = 300        # 5 min past next_send_at before we call it a miss
STUCK_SEQUENCE_HOURS = 48            # if active, current_step=0, no replies_count, >48h
DORMANT_CONTRACTOR_DAYS = 30         # contractors with last_dispatched_at older than this
BURST_WINDOW_MIN = 10                # 422 burst detection window
BURST_THRESHOLD = 5                  # N 422s in BURST_WINDOW_MIN triggers tier-2
DAILY_SUMMARY_HOUR_UTC = 23          # hour to roll up tier-3 daily summary

# Telegram ping throttling: don't ping the same (category, subject_id)
# more than once per hour
PING_DEDUP_WINDOW_MIN = 60

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)


async def _telegram_send(text: str) -> bool:
    """Send a Telegram message via hermes CLI. Best-effort: if hermes
    isn't on PATH, we just log and return False (the event is still
    in qc_events).

    Runs subprocess in a thread to avoid stalling the event loop."""
    try:
        result = await asyncio.to_thread(
            lambda: subprocess.run(
                ["/usr/local/bin/hermes", "send", "--to", "telegram", text],
                capture_output=True, text=True, timeout=15,
            )
        )
        return result.returncode == 0
    except Exception as e:
        log.debug(f"[sms_qc] telegram send failed: {e}")
        return False


def _already_pinged_recently(sb, category: str, subject_id: str, within_min: int) -> bool:
    """Check qc_events for a recent tier_2 ping on the same
    (category, subject_id) within the dedup window."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=within_min)).isoformat()
    try:
        r = (sb.table("qc_events")
                .select("id")
                .eq("category", category)
                .eq("subject_id", subject_id)
                .eq("severity", "tier_2")
                .eq("telegram_pinged", True)
                .gte("created_at", cutoff)
                .limit(1).execute())
        return bool(r.data)
    except Exception as e:
        log.debug(f"[sms_qc] dedup check failed: {e}")
        return False


def _write_event(sb, severity, category, source_agent, subject_kind,
                 subject_id, summary, detail=None,
                 auto_remediated=False, remediation=None,
                 telegram_pinged=False) -> str:
    """Write a qc_events row. Returns the event id."""
    try:
        ins = sb.table("qc_events").insert({
            "severity":         severity,
            "category":         category,
            "source_agent":     source_agent,
            "subject_kind":     subject_kind,
            "subject_id":       subject_id,
            "summary":           summary,
            "detail":            detail or {},
            "auto_remediated":  auto_remediated,
            "remediation":       remediation,
            "telegram_pinged":  telegram_pinged,
        }).execute()
        if ins.data:
            return ins.data[0].get("id", "")
    except Exception as e:
        log.error(f"[sms_qc] write_event failed: {e}")
    return ""


# ----------------------------------------------------------------------------
# Tier 1 checks (auto-remediate, log)
# ----------------------------------------------------------------------------

async def _check_dispatcher_misses(sb):
    """Sequences that are active, due, but have no recent sms_log entry.

    If the dispatcher poll missed one, reschedule to now so the
    next tick picks it up. Log as tier_1.
    """
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(seconds=DISPATCHER_MISS_GRACE_S)).isoformat()
    try:
        r = (sb.table("sms_sequences")
                .select("id,phone,next_send_at,sequence_type")
                .eq("status", "active")
                .lte("next_send_at", cutoff)
                .limit(50).execute())
        candidates = r.data or []
    except Exception as e:
        log.error(f"[sms_qc] dispatcher-miss query failed: {e}")
        return 0
    n_fixed = 0
    for row in candidates:
        sid = row["id"]
        phone = row["phone"]
        # Did the dispatcher actually do anything for this phone in
        # the last 5 min? If yes, the miss is benign (we just polled
        # late). If no, it's a real miss.
        try:
            r2 = (sb.table("sms_log")
                    .select("id,created_at")
                    .eq("phone", phone)
                    .gte("created_at", cutoff)
                    .limit(1).execute())
            recent = r2.data or []
        except Exception:
            recent = []
        if recent:
            continue  # dispatcher is alive, just polled
        # Real miss: reschedule to now+1s
        new_send = (now + timedelta(seconds=1)).isoformat()
        try:
            sb.table("sms_sequences").update({"next_send_at": new_send}).eq("id", sid).execute()
            _write_event(sb,
                severity="tier_1",
                category="dispatcher_miss",
                source_agent="sms_qc",
                subject_kind="sms_sequence",
                subject_id=sid,
                summary=f"Dispatcher missed sequence {phone} (next_send_at {row.get('next_send_at')})",
                detail={"phone": phone, "sequence_type": row.get("sequence_type"), "old_next_send_at": row.get("next_send_at"), "new_next_send_at": new_send},
                auto_remediated=True,
                remediation=f"rescheduled to {new_send}",
            )
            n_fixed += 1
        except Exception as e:
            log.debug(f"[sms_qc] reschedule failed for {sid}: {e}")
    if n_fixed:
        log.info(f"[sms_qc] dispatcher-miss: {n_fixed} sequences rescheduled")
    return n_fixed


async def _check_gate_regressions(sb):
    """Sequences with failed_send_count >= 3 but still status=active.

    The dispatcher gate at 0e0b6a1 marks these replied after 3
    failures. If we find one still active, the gate regressed
    (process restart? race? bug?). Auto-fix.
    """
    try:
        # meta.failed_send_count >= 3 means it should have been
        # marked replied. Use a JSONB query via PostgREST.
        r = sb.rpc("find_high_failure_sequences", {"min_count": 3}).execute()
        candidates = r.data or []
    except Exception:
        # RPC may not exist; fall back to fetching and filtering
        try:
            r = (sb.table("sms_sequences")
                    .select("id,phone,meta")
                    .eq("status", "active")
                    .limit(200).execute())
            candidates = [row for row in (r.data or [])
                          if int((row.get("meta") or {}).get("failed_send_count", 0)) >= 3]
        except Exception as e:
            log.debug(f"[sms_qc] gate-regression query failed: {e}")
            return 0
    n_fixed = 0
    for row in candidates:
        sid = row["id"]
        phone = row.get("phone")
        try:
            sb.table("sms_sequences").update({
                "status": "replied",
                "meta": {**(row.get("meta") or {}),
                         "blocked_reason": "gate_regression_fixed_by_qc",
                         "qc_remediated_at": datetime.now(timezone.utc).isoformat()},
            }).eq("id", sid).execute()
            _write_event(sb,
                severity="tier_1",
                category="gate_regression",
                source_agent="sms_qc",
                subject_kind="sms_sequence",
                subject_id=sid,
                summary=f"Gate regression: sequence {phone} had failed_send_count>=3 but was still active. Marked replied.",
                detail={"phone": phone, "meta": row.get("meta")},
                auto_remediated=True,
                remediation="marked replied",
            )
            n_fixed += 1
        except Exception as e:
            log.debug(f"[sms_qc] gate-regression fix failed for {sid}: {e}")
    if n_fixed:
        log.info(f"[sms_qc] gate-regression: {n_fixed} sequences fixed")
    return n_fixed


async def _check_duplicate_leads(sb):
    """Duplicate enriched_leads rows by (phone, address) created in
    the last hour. Dedupe (keep the oldest, delete the rest).
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    try:
        r = (sb.table("enriched_leads")
                .select("id,phone,address,created_at")
                .gte("created_at", cutoff)
                .not_.is_("phone", "null")
                .not_.is_("address", "null")
                .limit(500).execute())
        rows = r.data or []
    except Exception as e:
        log.debug(f"[sms_qc] dedupe query failed: {e}")
        return 0
    # Group by (phone, address) lowercased
    by_key = {}
    for row in rows:
        phone = (row.get("phone") or "").strip()
        address = (row.get("address") or "").strip().lower()
        if not phone or not address:
            continue
        key = (phone, address)
        by_key.setdefault(key, []).append(row)
    n_fixed = 0
    for key, group in by_key.items():
        if len(group) < 2:
            continue
        # keep the oldest by created_at
        group.sort(key=lambda r: r.get("created_at") or "")
        kept = group[0]
        for dup in group[1:]:
            try:
                sb.table("enriched_leads").delete().eq("id", dup["id"]).execute()
                _write_event(sb,
                    severity="tier_1",
                    category="duplicate_lead",
                    source_agent="sms_qc",
                    subject_kind="enriched_lead",
                    subject_id=dup["id"],
                    summary=f"Deleted duplicate enriched_lead (phone={key[0]}, address prefix={key[1][:40]})",
                    detail={"phone": key[0], "kept_id": kept["id"], "deleted_id": dup["id"]},
                    auto_remediated=True,
                    remediation=f"deleted; kept {kept['id']}",
                )
                n_fixed += 1
            except Exception as e:
                log.debug(f"[sms_qc] dedupe delete failed: {e}")
    if n_fixed:
        log.info(f"[sms_qc] duplicate-leads: {n_fixed} duplicates removed")
    return n_fixed


async def _check_stuck_sequences(sb):
    """Sequences active at step 0 for >48h with no replies_count increase.

    Tier 1: reschedule to now so the dispatcher tries them again.
    Often this is just quiet-hours drift; the reschedule unsticks it.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=STUCK_SEQUENCE_HOURS)).isoformat()
    try:
        r = (sb.table("sms_sequences")
                .select("id,phone,sequence_type,current_step,replies_count,created_at")
                .eq("status", "active")
                .eq("current_step", 0)
                .lte("created_at", cutoff)
                .limit(50).execute())
        candidates = r.data or []
    except Exception as e:
        log.debug(f"[sms_qc] stuck-sequence query failed: {e}")
        return 0
    n_fixed = 0
    now = datetime.now(timezone.utc)
    for row in candidates:
        sid = row["id"]
        # Don't touch sequences the dispatcher is actively working on
        if (row.get("replies_count") or 0) > 0:
            continue
        new_send = (now + timedelta(seconds=2)).isoformat()
        try:
            sb.table("sms_sequences").update({"next_send_at": new_send}).eq("id", sid).execute()
            _write_event(sb,
                severity="tier_1",
                category="stuck_sequence",
                source_agent="sms_qc",
                subject_kind="sms_sequence",
                subject_id=sid,
                summary=f"Stuck sequence {row.get('phone')} (active, step 0, no replies for {STUCK_SEQUENCE_HOURS}h) -- rescheduled",
                detail={"phone": row.get("phone"), "sequence_type": row.get("sequence_type"), "created_at": row.get("created_at")},
                auto_remediated=True,
                remediation=f"rescheduled to {new_send}",
            )
            n_fixed += 1
        except Exception as e:
            log.debug(f"[sms_qc] stuck-sequence fix failed: {e}")
    if n_fixed:
        log.info(f"[sms_qc] stuck-sequence: {n_fixed} sequences unstuck")
    return n_fixed


# ----------------------------------------------------------------------------
# Tier 2 checks (Telegram ping)
# ----------------------------------------------------------------------------

async def _check_422_bursts(sb):
    """More than BURST_THRESHOLD 422s on a single phone in BURST_WINDOW_MIN."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=BURST_WINDOW_MIN)).isoformat()
    try:
        r = (sb.table("sms_log")
                .select("phone,created_at")
                .eq("direction", "outbound")
                .eq("delivered", False)
                .gte("created_at", cutoff)
                .limit(500).execute())
        rows = r.data or []
    except Exception as e:
        log.debug(f"[sms_qc] 422-burst query failed: {e}")
        return 0
    counts = {}
    for row in rows:
        ph = row.get("phone") or "?"
        counts[ph] = counts.get(ph, 0) + 1
    n_pinged = 0
    for phone, n in counts.items():
        if n < BURST_THRESHOLD:
            continue
        if _already_pinged_recently(sb, "422_burst", phone, PING_DEDUP_WINDOW_MIN):
            continue
        summary = f"422 burst: {phone} has {n} failed sends in the last {BURST_WINDOW_MIN} min"
        event_id = _write_event(sb,
            severity="tier_2",
            category="422_burst",
            source_agent="sms_qc",
            subject_kind="phone",
            subject_id=phone,
            summary=summary,
            detail={"phone": phone, "failure_count": n, "window_min": BURST_WINDOW_MIN},
            telegram_pinged=False,
        )
        sent = await _telegram_send(f"[sms_qc] {summary}")
        if sent:
            try:
                sb.table("qc_events").update({"telegram_pinged": True}).eq("id", event_id).execute()
            except Exception:
                pass
        n_pinged += 1
    if n_pinged:
        log.info(f"[sms_qc] 422-burst: {n_pinged} phones pinged")
    return n_pinged


async def _check_unrendered_placeholders(sb):
    """Outbound sms_log rows delivered=true but body has {event}/{city}/
    {address} unrendered. Indicates a template bug."""
    try:
        r = (sb.table("sms_log")
                .select("phone,body,created_at")
                .eq("direction", "outbound")
                .eq("delivered", True)
                .gte("created_at", (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat())
                .limit(200).execute())
        rows = r.data or []
    except Exception as e:
        log.debug(f"[sms_qc] placeholder check failed: {e}")
        return 0
    n_pinged = 0
    for row in rows:
        body = row.get("body") or ""
        # Look for unrendered placeholders (any {word} with no fill)
        unrendered = re.findall(r"\{(\w+)\}", body)
        # Some of these are valid (e.g. {prefix}) but only the storm_strike
        # templates use {event}/{city}/{address}/{severity}/{urgency}.
        # If we see those, that's a bug.
        bug_placeholders = {"event", "city", "address", "severity", "urgency"}
        found = [p for p in unrendered if p in bug_placeholders]
        if not found:
            continue
        key = f"unrendered:{row.get('phone')}:{','.join(sorted(set(found)))}"
        if _already_pinged_recently(sb, "unrendered_placeholder", key, PING_DEDUP_WINDOW_MIN):
            continue
        summary = f"Unrendered placeholder in delivered SMS to {row.get('phone')}: {sorted(set(found))}"
        event_id = _write_event(sb,
            severity="tier_2",
            category="unrendered_placeholder",
            source_agent="sms_qc",
            subject_kind="sms_log",
            subject_id=row.get("phone") or "?",
            summary=summary,
            detail={"body": body[:200], "placeholders": found, "created_at": row.get("created_at")},
            telegram_pinged=False,
        )
        sent = await _telegram_send(f"[sms_qc] {summary}")
        if sent:
            try:
                sb.table("qc_events").update({"telegram_pinged": True}).eq("id", event_id).execute()
            except Exception:
                pass
        n_pinged += 1
    if n_pinged:
        log.info(f"[sms_qc] unrendered: {n_pinged} pings")
    return n_pinged


async def _check_converted_no_sequence(sb):
    """enriched_leads marked status=converted in the last hour, but no
    sms_sequence exists for that lead. Means the converter marked it
    converted but the enroll call to the hub didn't create a sequence.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    try:
        r = (sb.table("enriched_leads")
                .select("id,phone,converted_at")
                .eq("status", "converted")
                .gte("converted_at", cutoff)
                .not_.is_("phone", "null")
                .limit(100).execute())
        candidates = r.data or []
    except Exception as e:
        log.debug(f"[sms_qc] converted-no-seq query failed: {e}")
        return 0
    n_pinged = 0
    for row in candidates:
        ph = row.get("phone")
        try:
            r2 = sb.table("sms_sequences").select("id").eq("phone", ph).limit(1).execute()
            if r2.data:
                continue  # sequence exists, no problem
        except Exception:
            continue
        if _already_pinged_recently(sb, "converted_no_sequence", ph, PING_DEDUP_WINDOW_MIN):
            continue
        summary = f"enriched_lead {row['id']} marked converted but no sms_sequence for {ph}"
        event_id = _write_event(sb,
            severity="tier_2",
            category="converted_no_sequence",
            source_agent="sms_qc",
            subject_kind="enriched_lead",
            subject_id=row["id"],
            summary=summary,
            detail={"phone": ph, "converted_at": row.get("converted_at")},
            telegram_pinged=False,
        )
        sent = await _telegram_send(f"[sms_qc] {summary}")
        if sent:
            try:
                sb.table("qc_events").update({"telegram_pinged": True}).eq("id", event_id).execute()
            except Exception:
                pass
        n_pinged += 1
    if n_pinged:
        log.info(f"[sms_qc] converted-no-seq: {n_pinged} pings")
    return n_pinged


async def _check_stale_contractors(sb):
    """Contractors active but last_dispatched_at > DORMANT_CONTRACTOR_DAYS ago.
    Ping so the operator knows the network is going cold."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=DORMANT_CONTRACTOR_DAYS)).isoformat()
    try:
        r = (sb.table("contractors")
                .select("id,name,last_dispatched_at,completed_jobs")
                .eq("active", True)
                .lt("last_dispatched_at", cutoff)
                .limit(50).execute())
        candidates = r.data or []
    except Exception:
        return 0
    n_pinged = 0
    for row in candidates:
        cid = row["id"]
        if _already_pinged_recently(sb, "stale_contractor", cid, PING_DEDUP_WINDOW_MIN * 24):
            continue  # dedup across 24h for stale checks
        summary = f"Stale contractor: {row.get('name')} (no dispatch in {DORMANT_CONTRACTOR_DAYS}d, {row.get('completed_jobs', 0)} jobs done)"
        event_id = _write_event(sb,
            severity="tier_2",
            category="stale_contractor",
            source_agent="sms_qc",
            subject_kind="contractor",
            subject_id=cid,
            summary=summary,
            detail={"name": row.get("name"), "last_dispatched_at": row.get("last_dispatched_at"), "completed_jobs": row.get("completed_jobs")},
            telegram_pinged=False,
        )
        sent = await _telegram_send(f"[sms_qc] {summary}")
        if sent:
            try:
                sb.table("qc_events").update({"telegram_pinged": True}).eq("id", event_id).execute()
            except Exception:
                pass
        n_pinged += 1
    if n_pinged:
        log.info(f"[sms_qc] stale-contractor: {n_pinged} pings")
    return n_pinged


# ----------------------------------------------------------------------------
# Tier 3: daily summary at 23:00 UTC
# ----------------------------------------------------------------------------

async def _daily_summary(sb):
    """Roll up the day's metrics into a single qc_events row at tier_3.
    Best-effort: if any of the queries fail, we still write the row
    with partial data.
    """
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_iso = today_start.isoformat()
    summary = {"date": today_start.date().isoformat()}

    def safe_count(table, **kwargs):
        try:
            r = sb.table(table).select("id", count="exact").gte("created_at", today_iso).execute()
            return r.count or 0
        except Exception:
            return None

    summary["outbound_sms_total"]      = safe_count("sms_log", **{"direction": "outbound"})
    # Hmm need to filter direction -- let me do these one at a time
    try:
        r = sb.table("sms_log").select("id", count="exact").eq("direction", "outbound").gte("created_at", today_iso).execute()
        summary["outbound_sms_total"] = r.count or 0
    except Exception:
        pass
    try:
        r = sb.table("sms_log").select("id", count="exact").eq("direction", "outbound").eq("delivered", True).gte("created_at", today_iso).execute()
        summary["delivered_sms"] = r.count or 0
    except Exception:
        pass
    try:
        r = sb.table("sms_log").select("id", count="exact").eq("direction", "outbound").eq("delivered", False).gte("created_at", today_iso).execute()
        summary["failed_sms"] = r.count or 0
    except Exception:
        pass
    try:
        r = sb.table("sms_log").select("id", count="exact").eq("direction", "inbound").gte("created_at", today_iso).execute()
        summary["inbound_sms"] = r.count or 0
    except Exception:
        pass
    try:
        r = sb.table("enriched_leads").select("id", count="exact").gte("created_at", today_iso).execute()
        summary["new_enriched_leads"] = r.count or 0
    except Exception:
        pass
    try:
        r = sb.table("contractors").select("id", count="exact").gte("created_at", today_iso).execute()
        summary["new_contractors"] = r.count or 0
    except Exception:
        pass
    try:
        r = sb.table("dispatches").select("id", count="exact").gte("created_at", today_iso).execute()
        summary["dispatches"] = r.count or 0
    except Exception:
        pass
    try:
        r = sb.table("agent_activity").select("id", count="exact").gte("started_at", today_iso).execute()
        summary["agent_runs"] = r.count or 0
    except Exception:
        pass
    try:
        r = sb.table("qc_events").select("id", count="exact").eq("severity", "tier_1").gte("created_at", today_iso).execute()
        summary["tier_1_remediations_today"] = r.count or 0
    except Exception:
        pass
    try:
        r = sb.table("qc_events").select("id", count="exact").eq("severity", "tier_2").gte("created_at", today_iso).execute()
        summary["tier_2_pings_today"] = r.count or 0
    except Exception:
        pass

    # Build the prose summary
    prose = (
        f"Daily summary ({summary['date']} UTC): "
        f"outbound {summary.get('outbound_sms_total', '?')}, "
        f"delivered {summary.get('delivered_sms', '?')}, "
        f"failed {summary.get('failed_sms', '?')}, "
        f"inbound {summary.get('inbound_sms', '?')}, "
        f"new leads {summary.get('new_enriched_leads', '?')}, "
        f"new contractors {summary.get('new_contractors', '?')}, "
        f"dispatches {summary.get('dispatches', '?')}, "
        f"qc tier_1 fixes {summary.get('tier_1_remediations_today', '?')}, "
        f"qc tier_2 pings {summary.get('tier_2_pings_today', '?')}."
    )
    _write_event(sb,
        severity="tier_3",
        category="daily_summary",
        source_agent="sms_qc",
        subject_kind="system",
        subject_id=f"daily:{summary['date']}",
        summary=prose,
        detail=summary,
    )
    # Telegram a daily summary (high-signal, low-frequency)
    await _telegram_send(f"[sms_qc] {prose}")
    log.info(f"[sms_qc] daily summary written")


# ----------------------------------------------------------------------------
# Main loop
# ----------------------------------------------------------------------------

async def _one_tick(sb):
    """Run every check once. Returns a dict of counts for logging."""
    counts = {}
    counts["dispatcher_misses"]    = await _check_dispatcher_misses(sb)
    counts["gate_regressions"]     = await _check_gate_regressions(sb)
    counts["duplicate_leads"]      = await _check_duplicate_leads(sb)
    counts["stuck_sequences"]      = await _check_stuck_sequences(sb)
    counts["bursts_422"]           = await _check_422_bursts(sb)
    counts["unrendered"]           = await _check_unrendered_placeholders(sb)
    counts["converted_no_seq"]     = await _check_converted_no_sequence(sb)
    counts["stale_contractors"]    = await _check_stale_contractors(sb)
    return counts


async def _run_daemon():
    log.info(f"[sms_qc] daemon ONLINE · poll={POLL_INTERVAL_S}s")
    sb = _sb()
    last_daily = None  # date of last daily summary
    while True:
        try:
            counts = await _one_tick(sb)
            now = datetime.now(timezone.utc)
            # Daily summary at 23:00 UTC, but only once per day
            if now.hour >= DAILY_SUMMARY_HOUR_UTC and (last_daily != now.date()):
                try:
                    await _daily_summary(sb)
                except Exception as e:
                    log.error(f"[sms_qc] daily summary failed: {e}")
                last_daily = now.date()
            # Reset last_daily at midnight so tomorrow's summary fires
            if now.hour < DAILY_SUMMARY_HOUR_UTC:
                last_daily = None
            nonzero = {k: v for k, v in counts.items() if v}
            if nonzero:
                log.info(f"[sms_qc] tick: {nonzero}")
        except Exception as e:
            log.error(f"[sms_qc] tick failed: {e}")
        await asyncio.sleep(POLL_INTERVAL_S)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--status", action="store_true",
                   help="Print recent qc_events and exit (one-shot read).")
    args = p.parse_args()
    if args.status:
        sb = _sb()
        try:
            r = (sb.table("qc_events")
                    .select("created_at,severity,category,subject_kind,subject_id,summary,auto_remediated,telegram_pinged,resolved")
                    .order("created_at", desc=True)
                    .limit(30).execute())
            print(json.dumps(r.data or [], indent=2, default=str))
        except Exception as e:
            print(f"qc_events query failed: {e}")
        return
    try:
        asyncio.run(_run_daemon())
    except KeyboardInterrupt:
        log.info("[sms_qc] daemon interrupted, exiting")


if __name__ == "__main__":
    main()
