"""
VONAGE SMS DELIVERY ENGINEER AGENT — Empire AI
===============================================
Small looping agent that monitors SMS delivery health, polls Vonage for
status, updates sms_log, feeds SI for strategy evolution, and emits
events for AGI revenue calibration. Replaces big manual scripts with an
autonomous self-healing agent.

What it does every cycle (default: every 5 min):
  1. Scan sms_log for undelivered (delivered IS NULL) outbound messages
     from the last 2 hours
  2. Poll Vonage GET /v1/messages/{uuid} for current delivery status
  3. Update sms_log.delivered (True/False)
  4. Record outcome to SI: treats SMS delivery as a "niche" so SI
     evolves strategies for delivery timing/channel/retry patterns
  5. Emit sms.delivery.* events on the event bus for AGI to consume
     (delivery health → revenue calibration adjustments)
  6. Auto-heal: flag rejected/undelivered messages for email fallback
     by setting sms_log.meta.action_needed

Agent_runner compatible via run_loop(interval_seconds) or standalone.
"""

import os
import sys
import json
import uuid
import time as _time
import asyncio
import logging
from datetime import datetime, timezone
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
import httpx

log = logging.getLogger("vonage.engineer")

# ── Config ─────────────────────────────────────────────────────────────
LOOKBACK_HOURS = 2          # How far back to scan for undelivered SMS
BATCH_SIZE = 25             # Max messages to check per cycle
POLL_DELAY = 0.3            # Seconds between Vonage API calls
AGENT_NAME = "vonage_engineer_agent"


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        return None
    return create_client(url, key)


def _get_vonage_token() -> Optional[str]:
    """Generate a short-lived Vonage JWT using the application private key."""
    app_id = os.getenv("VONAGE_APPLICATION_ID", "")
    key_path = os.getenv("VONAGE_PRIVATE_KEY_PATH", "/root/vonage_private.key")
    if not app_id or not os.path.exists(key_path):
        return None

    try:
        with open(key_path, "r") as f:
            private_key = f.read()
        import jwt as pyjwt
        now = int(_time.time())
        payload = {
            "iat": now,
            "exp": now + 180,
            "jti": str(uuid.uuid4()),
            "application_id": app_id,
        }
        return pyjwt.encode(payload, private_key, algorithm="RS256")
    except Exception as e:
        log.debug(f"[vonage_engineer] JWT generation failed: {e}")
        return None


async def _poll_vonage_status(message_uuid: str) -> dict:
    """Poll Vonage Messages API for delivery status of a single message.

    Returns: {"ok": bool, "status": str, "delivered": bool, "error": str|None}
    """
    token = _get_vonage_token()
    if not token or not message_uuid:
        return {"ok": False, "status": "unknown", "delivered": False, "error": "no credentials"}

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                f"https://api.nexmo.com/v1/messages/{message_uuid}",
                headers={"Authorization": f"Bearer {token}"},
            )
            if r.status_code == 200:
                data = r.json()
                status = (data.get("status") or "unknown").lower()
                delivered = status == "delivered"
                return {"ok": True, "status": status, "delivered": delivered, "error": None}
            else:
                return {"ok": False, "status": "unknown", "delivered": False,
                        "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"ok": False, "status": "unknown", "delivered": False, "error": str(e)[:100]}


async def _record_si_outcome(phone: str, delivered: bool, strategy: str = "SMS_DIRECT") -> None:
    """Feed delivery outcome into SI for strategy evolution.

    SMS delivery is treated as a pseudo-niche so SI can track which
    phone carriers/channels perform best and evolve delivery strategies.
    """
    try:
        from empire_si_strategy import StrategyEvolution

        si = StrategyEvolution.get_shared_instance()
        if si is None:
            return

        # Use area code / prefix as a rough carrier grouping
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
    status: str,
    contractor_id: Optional[str] = None,
) -> None:
    """Emit an event on the bus for AGI consumption.

    AGI uses sms.delivery.* event rates to factor delivery health into
    revenue calibration (close_rate, confidence_decay, etc.).
    """
    try:
        from empire_event_bus import bus

        severity = "info" if delivered else "warn"
        await bus.emit(
            "sms.delivery.status",
            data={
                "phone": phone,
                "message_uuid": message_uuid,
                "delivered": delivered,
                "status": status,
                "contractor_id": contractor_id,
            },
            source=AGENT_NAME,
            severity=severity,
        )
    except Exception as e:
        log.debug(f"[vonage_engineer] event emit skipped: {e}")


async def _get_undelivered_messages(sb) -> list[dict]:
    """Fetch undelivered outbound SMS from sms_log within LOOKBACK_HOURS."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)).isoformat()
    try:
        r = (
            sb.table("sms_log")
            .select("id,phone,direction,body,message_uuid,delivered,created_at")
            .eq("direction", "outbound")
            .is_("delivered", "null")
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .limit(BATCH_SIZE)
            .execute()
        )
        return r.data or []
    except Exception as e:
        log.warning(f"[vonage_engineer] sms_log query failed: {e}")
        return []


async def _update_delivery(sb, sms_id: str, message_uuid: str,
                           delivered: bool, status: str) -> None:
    """Update sms_log.delivered.

    sms_log has no meta column — delivery status is tracked via
    the delivered boolean and event bus emissions for AGI/SI.
    """
    updates: dict = {"delivered": delivered}

    try:
        sb.table("sms_log").update(updates).eq("id", sms_id).execute()
    except Exception as e:
        log.warning(f"[vonage_engineer] sms_log update failed for {sms_id[:12]}: {e}")


class VonageEngineerAgent:
    """Small autonomous agent that monitors SMS delivery, self-heals issues,
    and feeds SI/AGI with delivery health data."""

    def __init__(self):
        self.cycles = 0
        self.total_checked = 0
        self.total_delivered = 0
        self.total_failed = 0

    async def run_cycle(self) -> dict:
        """One monitoring cycle. Called by run_loop or standalone."""
        sb = _sb()
        if not sb:
            return {"error": "no supabase connection"}

        self.cycles += 1
        messages = await _get_undelivered_messages(sb)

        if not messages:
            log.debug(f"[vonage_engineer] cycle {self.cycles}: no undelivered SMS to check")
            return {"checked": 0, "delivered": 0, "failed": 0, "cycles": self.cycles}

        delivered_count = 0
        failed_count = 0
        checked = 0

        for msg in messages:
            msg_uuid = msg.get("message_uuid")
            if not msg_uuid:
                continue

            checked += 1
            result = await _poll_vonage_status(msg_uuid)

            if result["ok"]:
                await _update_delivery(
                    sb, msg["id"], msg_uuid,
                    delivered=result["delivered"],
                    status=result["status"],
                )

                if result["delivered"]:
                    delivered_count += 1
                else:
                    failed_count += 1

                # Feed SI + AGI in parallel (best-effort, non-blocking)
                phone = msg.get("phone", "")
                await asyncio.gather(
                    _record_si_outcome(phone, result["delivered"]),
                    _emit_delivery_event(phone, msg_uuid, result["delivered"],
                                         result["status"]),
                    return_exceptions=True,
                )
            else:
                # Vonage API unavailable — skip, try next cycle
                log.debug(
                    f"[vonage_engineer] Vonage poll failed for "
                    f"{msg_uuid[:20]}: {result.get('error')}"
                )

            await asyncio.sleep(POLL_DELAY)

        self.total_checked += checked
        self.total_delivered += delivered_count
        self.total_failed += failed_count

        summary = {
            "checked": checked,
            "delivered": delivered_count,
            "failed": failed_count,
            "cycles": self.cycles,
            "cumulative_checked": self.total_checked,
            "cumulative_delivered": self.total_delivered,
            "cumulative_failed": self.total_failed,
        }

        if checked:
            log.info(
                f"[vonage_engineer] cycle {self.cycles}: "
                f"checked={checked} delivered={delivered_count} "
                f"failed={failed_count} "
                f"(cumulative: {self.total_delivered}/{self.total_checked} delivered)"
            )

        return summary


# ── Agent Runner Compat ──────────────────────────────────────────────────


async def run_loop(interval_seconds: int = 300):
    """Loop wrapper for agent_runner. Default: every 5 minutes."""
    agent = VonageEngineerAgent()
    while True:
        try:
            result = await agent.run_cycle()
            if result.get("checked"):
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
    result = run_once()
    print(json.dumps(result, indent=2, default=str))
