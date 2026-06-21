"""
VONAGE SMS DELIVERY ENGINEER AGENT — Empire AI
===============================================
Small looping agent that monitors SMS delivery health using a timeout-based
approach. Vonage Messages API v1 has NO GET endpoint for status lookup — 
delivery receipts only arrive via webhook (POST /api/v1/vonage/sms-status).

What it does every cycle (default: every 5 min):
  1. Scan sms_log for outbound messages where delivered IS NULL and
     created_at > STALE_TIMEOUT_MINUTES ago (no webhook confirmation)
  2. Mark stale messages as delivered=false (assumed undelivered)
  3. Scan for messages where delivered=True (webhook confirmed)
     and feed them to SI/AGI — uses a processed-ID set to avoid duplicates
  4. Feed delivery outcomes to SI for strategy evolution (per area code)
  5. Emit sms.delivery.* events on the event bus for AGI revenue calibration
  6. Track cumulative delivery health metrics

The webhook at /api/v1/vonage/sms-status is the ONLY delivery status source.
This agent is the safety net for messages where the webhook never fires
(Vonage dashboard not configured, network issues, etc.).

Agent_runner compatible via run_loop(interval_seconds) or standalone.
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO.parent / ".env")
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("vonage.engineer")

# ── Config ─────────────────────────────────────────────────────────────
STALE_TIMEOUT_MINUTES = 30  # Mark as undelivered if no webhook after this
LOOKBACK_HOURS = 4          # How far back to scan for undelivered messages
BATCH_SIZE = 50             # Max messages to check per cycle
AGENT_NAME = "vonage_engineer_agent"


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        return None
    return create_client(url, key)


async def _record_si_outcome(phone: str, delivered: bool, strategy: str = "SMS_DIRECT") -> None:
    """Feed delivery outcome into SI for strategy evolution.

    SMS delivery is treated as a pseudo-niche so SI can track which
    area codes/carriers perform best and evolve delivery strategies.
    """
    try:
        from empire_si_strategy import StrategyEvolution
        si = StrategyEvolution.get_shared_instance()
        if si is None:
            return
        digits = "".join(c for c in phone if c.isdigit())
        area = digits[:3] if len(digits) >= 3 else "unknown"
        si.record_outcome(
            strategy_name=strategy,
            niche=f"sms_delivery_{area}",
            success=delivered,
            revenue=0.0,
        )
    except Exception as e:
        log.debug(f"[vonage_engineer] SI record skipped: {e}")


async def _emit_delivery_event(
    phone: str,
    message_uuid: str,
    delivered: bool,
    source: str = "timeout",
) -> None:
    """Emit an event on the bus for AGI consumption.

    AGI uses sms.delivery.* event rates to factor delivery health into
    revenue calibration (close_rate, confidence_decay, etc.).
    """
    try:
        from empire_event_bus import bus
        await bus.emit(
            "sms.delivery.status",
            data={
                "phone": phone,
                "message_uuid": message_uuid,
                "delivered": delivered,
                "source": source,
            },
            source=AGENT_NAME,
            severity="info" if delivered else "warn",
        )
    except Exception as e:
        log.debug(f"[vonage_engineer] event emit skipped: {e}")


async def _get_stale_undelivered(sb) -> list[dict]:
    """Fetch outbound SMS where delivered IS NULL and sent > STALE_TIMEOUT ago.

    These are messages the Vonage webhook never confirmed — we mark them
    as undelivered (assumed failure).
    """
    stale_cutoff = (datetime.now(timezone.utc) - timedelta(minutes=STALE_TIMEOUT_MINUTES)).isoformat()
    lookback_cutoff = (datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)).isoformat()

    try:
        r = (
            sb.table("sms_log")
            .select("id,phone,message_uuid,delivered,created_at")
            .eq("direction", "outbound")
            .is_("delivered", "null")
            .gte("created_at", lookback_cutoff)
            .lte("created_at", stale_cutoff)
            .order("created_at", desc=True)
            .limit(BATCH_SIZE)
            .execute()
        )
        return r.data or []
    except Exception as e:
        log.warning(f"[vonage_engineer] sms_log query failed: {e}")
        return []


async def _get_recently_delivered(sb) -> list[dict]:
    """Fetch outbound SMS where delivered=True (webhook confirmed)
    in the last STALE_TIMEOUT_MINUTES window.

    Uses a wide window (30 min) because created_at is send time,
    not update time. The caller deduplicates via a processed-ID set.
    """
    since = (datetime.now(timezone.utc) - timedelta(minutes=STALE_TIMEOUT_MINUTES)).isoformat()
    try:
        r = (
            sb.table("sms_log")
            .select("id,phone,message_uuid,delivered,created_at")
            .eq("direction", "outbound")
            .eq("delivered", True)
            .gte("created_at", since)
            .order("created_at", desc=True)
            .limit(BATCH_SIZE)
            .execute()
        )
        return r.data or []
    except Exception as e:
        log.warning(f"[vonage_engineer] recent query failed: {e}")
        return []


class VonageEngineerAgent:
    """Small autonomous agent that monitors SMS delivery via timeout detection.

    Vonage has no GET status endpoint — delivery receipts only arrive via
    webhook. This agent is the safety net: any message still undelivered
    after STALE_TIMEOUT_MINUTES is assumed undelivered. Messages confirmed
    by the webhook are fed to SI/AGI for intelligence.
    """

    def __init__(self):
        self.cycles = 0
        self.total_stale = 0
        self.total_delivered = 0
        self.total_failed = 0
        self._processed_ids: set = set()   # deduplicate SI/AGI feeds
        self._processed_max = 2000          # cap set size to prevent unbounded growth

    async def run_cycle(self) -> dict:
        """One monitoring cycle. Called by run_loop or standalone."""
        sb = _sb()
        if not sb:
            return {"error": "no supabase connection"}

        self.cycles += 1

        # ── 1. Mark stale undelivered messages as failed ──────────────
        stale = await _get_stale_undelivered(sb)
        failed_count = 0

        for msg in stale:
            msg_uuid = msg.get("message_uuid", "")
            try:
                sb.table("sms_log").update({"delivered": False}).eq("id", msg["id"]).execute()
                failed_count += 1
                phone = msg.get("phone", "")
                await asyncio.gather(
                    _record_si_outcome(phone, False),
                    _emit_delivery_event(phone, msg_uuid, False, source="timeout"),
                    return_exceptions=True,
                )
            except Exception as e:
                log.warning(f"[vonage_engineer] stale update failed: {e}")

        # ── 2. Feed webhook-confirmed messages to SI/AGI ─────
        # Use a wide window (created_at is send time, not update time)
        # and a processed-ID set to avoid duplicate SI/AGI feeds across cycles
        recent = await _get_recently_delivered(sb)
        delivered_count = 0

        for msg in recent:
            msg_id = msg["id"]
            if msg_id in self._processed_ids:
                continue
            self._processed_ids.add(msg_id)

            # Clear the set when it exceeds the cap — a 30-min window only
            # needs ~300 IDs at current volumes, so this is a safety valve
            if len(self._processed_ids) > self._processed_max:
                self._processed_ids.clear()

            is_delivered = msg.get("delivered") is True
            if is_delivered:
                delivered_count += 1
            phone = msg.get("phone", "")
            msg_uuid = msg.get("message_uuid", "")
            await asyncio.gather(
                _record_si_outcome(phone, is_delivered),
                _emit_delivery_event(phone, msg_uuid, is_delivered, source="webhook"),
                return_exceptions=True,
            )

        self.total_stale += failed_count
        self.total_delivered += delivered_count
        self.total_failed += failed_count

        summary = {
            "stale_marked_failed": failed_count,
            "recent_delivered": delivered_count,
            "cycles": self.cycles,
            "cumulative_stale": self.total_stale,
            "cumulative_delivered": self.total_delivered,
        }

        if failed_count or delivered_count:
            log.info(
                f"[vonage_engineer] cycle {self.cycles}: "
                f"stale→failed={failed_count} webhook→delivered={delivered_count}"
            )

        return summary


# ── Agent Runner Compat ──────────────────────────────────────────────────


async def run_loop(interval_seconds: int = 300):
    """Loop wrapper for agent_runner. Default: every 5 minutes."""
    agent = VonageEngineerAgent()
    while True:
        try:
            result = await agent.run_cycle()
            if result.get("stale_marked_failed") or result.get("recent_delivered"):
                log.info(f"[vonage_engineer] result: {json.dumps(result, default=str)}")
        except Exception as e:
            log.error(f"[vonage_engineer] cycle error: {e}")
        await asyncio.sleep(interval_seconds)


def run_once():
    """Single cycle — for manual testing."""
    async def _run():
        agent = VonageEngineerAgent()
        return await agent.run_cycle()
    return asyncio.run(_run())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(name)s] %(message)s")
    asyncio.run(run_loop())
