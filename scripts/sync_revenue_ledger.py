#!/usr/bin/env python3
"""
EMPIRE V49 · UNIFIED REVENUE LEDGER SYNC
=========================================
Populates empire_revenue_ledger from fee_events and call_logs so the
operator console and daily digest can query one table for a complete
financial picture.

Sources:
  - fee_events: settled-claim fees (fee_amount, claim_amount)
  - call_logs:  call revenue (fee_earned, payout_value, lead_fee)
  - solana:     on-chain USDC payments (already in the ledger)

Modes:
    --backfill       One-time backfill of ALL existing fee_events + call_logs
                     (skips already-synced rows via source_type + source_id)
    --sync           Incremental sync of recent records (last 24h)
    --dry-run        Report only — no writes

Examples:
    python3 scripts/sync_revenue_ledger.py --backfill         # full backfill
    python3 scripts/sync_revenue_ledger.py --sync             # last 24h
    python3 scripts/sync_revenue_ledger.py --backfill --dry-run  # preview
    python3 scripts/sync_revenue_ledger.py --sync --hours 72    # last 72h
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO.parent / ".env")
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("sync_revenue_ledger")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [sync-ledger] %(levelname)s %(message)s",
)

AGENT_NAME = "sync_revenue_ledger"


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)


def _existing_source_ids(sb, source_type: str) -> set:
    """Return set of source_ids already synced for a given source_type.

    Used by check-then-insert dedup (PostgREST's upsert doesn't consistently
    detect UNIQUE constraints).
    """
    ids = set()
    limit = 1000
    offset = 0
    while True:
        r = sb.table("empire_revenue_ledger").select("source_id") \
            .eq("source_type", source_type).limit(limit).offset(offset).execute()
        batch = r.data or []
        if not batch:
            break
        ids.update(row["source_id"] for row in batch if row.get("source_id"))
        if len(batch) < limit:
            break
        offset += limit
    return ids



def _sync_fee_events(sb, hours: int, dry_run: bool) -> dict:
    """Sync fee_events into empire_revenue_ledger."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    r = sb.table("fee_events").select(
        "id, created_at, claim_id, contractor_id, claim_amount, "
        "fee_amount, fee_percent, status, settled_at, source, meta"
    ).gte("created_at", cutoff).order("created_at", desc=True).limit(5000).execute()
    rows = r.data or []

    if not rows:
        return {"fetched": 0, "inserted": 0, "skipped_dup": 0}

    # Pre-fetch already-synced IDs to avoid PostgREST upsert issues
    existing = _existing_source_ids(sb, "fee_event") if not dry_run else set()

    inserted = 0
    skipped_dup = 0
    entries_to_insert = []

    for row in rows:
        fee_id = str(row["id"])

        if fee_id in existing:
            skipped_dup += 1
            continue

        fee_amount = float(row.get("fee_amount") or 0)
        claim_amount = float(row.get("claim_amount") or 0)
        status = row.get("status", "pending")
        settled_at = row.get("settled_at")
        created_at = row.get("created_at")

        # Build description
        desc_parts = [f"Fee event — ${fee_amount:,.2f} on ${claim_amount:,.2f} claim"]
        if row.get("source"):
            desc_parts.append(f"[{row['source']}]")
        if status != "pending":
            desc_parts.append(f"({status})")
        description = " ".join(desc_parts)

        entry = {
            "status":            "accrued",
            "source_type":       "fee_event",
            "source_id":         fee_id,
            "amount":            fee_amount,
            "usdc_amount":       fee_amount,
            "description":       description,
            "sender_address":    "fee_event:system",
            "destination_address": "fee_event:system",
            "tracking_memo":     f"fee:{fee_id[:12]}" if fee_id else None,
            "block_time_stamp":  settled_at or created_at,
            "logged_at":         created_at or datetime.now(timezone.utc).isoformat(),
            "meta": {
                "fee_id": fee_id,
                "claim_id": row.get("claim_id"),
                "contractor_id": row.get("contractor_id"),
                "claim_amount": claim_amount,
                "fee_percent": float(row.get("fee_percent") or 0.03),
                "status": status,
                "source": row.get("source"),
                "settled_at": settled_at,
            },
        }

        if dry_run:
            log.info(f"  [DRY-RUN] would insert fee_event {fee_id[:12]} — ${fee_amount:,.2f}")
        else:
            entries_to_insert.append(entry)
        inserted += 1

    # Batch insert
    if entries_to_insert and not dry_run:
        try:
            sb.table("empire_revenue_ledger").insert(entries_to_insert).execute()
            log.info(f"  Inserted {len(entries_to_insert)} fee_event rows")
        except Exception as e:
            log.warning(f"  Batch insert failed for {len(entries_to_insert)} fee_events: {e}")
            # Try one-by-one on failure to salvage what we can
            saved = 0
            for ent in entries_to_insert:
                try:
                    sb.table("empire_revenue_ledger").insert(ent).execute()
                    saved += 1
                except Exception:
                    pass
            log.info(f"  Salvaged {saved}/{len(entries_to_insert)} fee_events via single inserts")
            inserted = saved

    return {"fetched": len(rows), "inserted": inserted, "skipped_dup": skipped_dup}


def _sync_call_logs(sb, hours: int, dry_run: bool) -> dict:
    """Sync call_logs revenue into empire_revenue_ledger.

    Only syncs rows where at least one revenue field is > 0:
      - fee_earned (commissions)
      - payout_value (direct payouts)
      - lead_fee (PPL)
      - schedule_fee (per-schedule)
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    r = sb.table("call_logs").select(
        "id, created_at, buyer_id, niche, channel, caller_number, "
        "fee_earned, payout_value, lead_fee, schedule_fee, "
        "per_minute_fee, settlement_fee, qualified, is_billable, source, "
        "caller_state, status, affiliate_code"
    ).gte("created_at", cutoff).order("created_at", desc=True).limit(5000).execute()
    rows = r.data or []

    if not rows:
        return {"fetched": 0, "inserted": 0, "skipped_dup": 0, "skipped_no_revenue": 0}

    # Pre-fetch already-synced IDs
    existing = _existing_source_ids(sb, "call_log") if not dry_run else set()

    inserted = 0
    skipped_no_revenue = 0
    skipped_dup = 0
    entries_to_insert = []

    for row in rows:
        call_id = str(row["id"])

        if call_id in existing:
            skipped_dup += 1
            continue

        # Determine the primary revenue amount
        fee_earned = float(row.get("fee_earned") or 0)
        payout_value = float(row.get("payout_value") or 0)
        lead_fee = float(row.get("lead_fee") or 0)
        schedule_fee = float(row.get("schedule_fee") or 0)
        per_minute_fee = float(row.get("per_minute_fee") or 0)
        settlement_fee = float(row.get("settlement_fee") or 0)

        # Use the highest non-zero amount as the primary amount
        amounts = [
            ("fee_earned", fee_earned),
            ("payout_value", payout_value),
            ("lead_fee", lead_fee),
            ("schedule_fee", schedule_fee),
            ("per_minute_fee", per_minute_fee),
            ("settlement_fee", settlement_fee),
        ]
        amounts_with_value = [(k, v) for k, v in amounts if v > 0]

        if not amounts_with_value:
            skipped_no_revenue += 1
            continue

        primary_key, primary_amount = max(amounts_with_value, key=lambda x: x[1])

        # Build description
        niche = row.get("niche") or "?"
        channel = row.get("channel") or "?"
        source = row.get("source") or "?"
        caller_number = row.get("caller_number") or ""
        called_state = row.get("caller_state") or ""

        breakdown = " + ".join(f"${v:,.0f} {k}" for k, v in amounts_with_value)
        description = (
            f"Call revenue — ${primary_amount:,.2f} ({breakdown}) "
            f"· {niche}/{channel} · {called_state}"
        )

        created_at = row.get("created_at")

        entry = {
            "status":            "accrued",
            "source_type":       "call_log",
            "source_id":         call_id,
            "amount":            primary_amount,
            "usdc_amount":       primary_amount,
            "description":       description,
            "sender_address":    "call_log:system",
            "destination_address": "call_log:system",
            "tracking_memo":     f"call:{call_id[:12]}" if call_id else None,
            "block_time_stamp":  created_at,
            "logged_at":         created_at or datetime.now(timezone.utc).isoformat(),
            "meta": {
                "call_id": call_id,
                "buyer_id": row.get("buyer_id"),
                "niche": niche,
                "channel": channel,
                "source": source,
                "caller_number": caller_number,
                "caller_state": called_state,
                "qualified": row.get("qualified"),
                "is_billable": row.get("is_billable"),
                "affiliate_code": row.get("affiliate_code"),
                "fee_earned": fee_earned,
                "payout_value": payout_value,
                "lead_fee": lead_fee,
                "schedule_fee": schedule_fee,
                "per_minute_fee": per_minute_fee,
                "settlement_fee": settlement_fee,
            },
        }

        if dry_run:
            log.info(f"  [DRY-RUN] would insert call_log {call_id[:12]} — ${primary_amount:,.2f} ({breakdown})")
        else:
            entries_to_insert.append(entry)
        inserted += 1

    # Batch insert
    if entries_to_insert and not dry_run:
        try:
            sb.table("empire_revenue_ledger").insert(entries_to_insert).execute()
            log.info(f"  Inserted {len(entries_to_insert)} call_log rows")
        except Exception as e:
            log.warning(f"  Batch insert failed for {len(entries_to_insert)} call_logs: {e}")
            saved = 0
            for ent in entries_to_insert:
                try:
                    sb.table("empire_revenue_ledger").insert(ent).execute()
                    saved += 1
                except Exception:
                    pass
            log.info(f"  Salvaged {saved}/{len(entries_to_insert)} call_logs via single inserts")
            inserted = saved

    return {
        "fetched": len(rows),
        "inserted": inserted,
        "skipped_dup": skipped_dup,
        "skipped_no_revenue": skipped_no_revenue,
    }


def run_sync(
    hours: int = 24,
    dry_run: bool = False,
    backfill: bool = False,
) -> dict:
    """Run the ledger sync for fee_events and call_logs.

    Args:
        hours: Lookback window (used for sync mode; backfill uses a large value)
        dry_run: If True, report only — no writes
        backfill: If True, sync ALL records (hours=87600 = 10 years)
    """
    sb = _sb()
    started_at = datetime.now(timezone.utc)

    if backfill:
        hours = 87600  # 10 years — effectively all records
        log.info("=== REVENUE LEDGER BACKFILL ===")
    else:
        log.info(f"=== REVENUE LEDGER SYNC (last {hours}h) ===")

    if dry_run:
        log.info("DRY-RUN MODE — no writes will be performed")

    # ── 1. Sync fee_events ─────────────────────────────────────────────
    log.info("Syncing fee_events...")
    fee_result = _sync_fee_events(sb, hours=hours, dry_run=dry_run)
    log.info(
        f"  fee_events: fetched={fee_result['fetched']} "
        f"inserted={fee_result['inserted']} "
        f"skipped_dup={fee_result['skipped_dup']}"
    )

    # ── 2. Sync call_logs ──────────────────────────────────────────────
    log.info("Syncing call_logs...")
    call_result = _sync_call_logs(sb, hours=hours, dry_run=dry_run)
    log.info(
        f"  call_logs: fetched={call_result['fetched']} "
        f"inserted={call_result['inserted']} "
        f"skipped_dup={call_result['skipped_dup']} "
        f"skipped_no_revenue={call_result['skipped_no_revenue']}"
    )

    # ── 3. Summary ─────────────────────────────────────────────────────
    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()

    # Get total count in ledger
    try:
        count_r = sb.table("empire_revenue_ledger").select("id", count="exact").limit(0).execute()
        total_ledger = count_r.count if hasattr(count_r, 'count') else "?"
    except Exception:
        total_ledger = "?"

    summary = {
        "mode": "backfill" if backfill else "sync",
        "dry_run": dry_run,
        "hours": hours,
        "fee_events": fee_result,
        "call_logs": call_result,
        "total_inserted": fee_result["inserted"] + call_result["inserted"],
        "total_ledger_rows": total_ledger,
        "elapsed_seconds": round(elapsed, 1),
    }

    log.info("=== SUMMARY ===")
    log.info(f"Mode:          {'BACKFILL' if backfill else 'SYNC'}")
    log.info(f"Dry-run:       {dry_run}")
    log.info(f"Fee events:    {fee_result['inserted']} inserted ({fee_result['skipped_dup']} dup)")
    log.info(f"Call logs:     {call_result['inserted']} inserted "
              f"({call_result['skipped_dup']} dup, {call_result['skipped_no_revenue']} no revenue)")
    log.info(f"Total written: {summary['total_inserted']}")
    log.info(f"Ledger total:  {total_ledger} rows")
    log.info(f"Elapsed:       {elapsed:.1f}s")

    return summary


def main():
    p = argparse.ArgumentParser(
        description="Unified Revenue Ledger Sync — populate empire_revenue_ledger from fee_events and call_logs"
    )
    p.add_argument("--backfill", action="store_true",
                    help="Backfill ALL existing fee_events and call_logs")
    p.add_argument("--sync", action="store_true",
                    help="Incremental sync (last N hours, default 24)")
    p.add_argument("--hours", type=int, default=24,
                    help="Lookback window in hours (default: 24, used with --sync)")
    p.add_argument("--dry-run", action="store_true",
                    help="Report only — no writes")
    args = p.parse_args()

    if not args.backfill and not args.sync:
        # Default: sync last 24h
        args.sync = True
        log.info("Default mode: sync (last 24h). Use --backfill for full backfill.")

    result = run_sync(
        hours=args.hours,
        dry_run=args.dry_run,
        backfill=args.backfill,
    )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
