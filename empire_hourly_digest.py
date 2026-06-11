"""
EMPIRE V49 · HOURLY DIGEST
===========================
Plain-text activity report generated every hour. No AI, no Ollama —
just raw stats from every subsystem written to hourly_digest.txt.

ARCHITECTURE
────────────
  1. HourlyCollector  — pulls last 60 minutes from all subsystems
  2. HourlyFormatter  — renders collected data as plain text
  3. HourlyDigestLoop — background asyncio task, 1-hour tick

OUTPUT FILE
───────────
    /root/empire-v49/hourly_digest.txt  (overwritten each cycle)

WIRE-UP
───────
    hub.py startup:
        from empire_hourly_digest import HourlyDigestLoop
        hourly_digest = HourlyDigestLoop()
        asyncio.create_task(hourly_digest.run())
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List

sys.path.insert(0, "/root/empire-v49")

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("empire.hourly")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
DIGEST_PATH = os.environ.get("HOURLY_DIGEST_PATH", "/root/empire-v49/hourly_digest.txt")

# Runtime-configurable interval (env var DIGEST_INTERVAL_MINUTES, default 60.0)
try:
    _digest_interval = float(os.environ.get("DIGEST_INTERVAL_MINUTES", "60.0")) * 60  # seconds
except (ValueError, TypeError):
    _digest_interval = 3600.0

def get_digest_interval() -> float:
    """Return the current HourlyDigest interval in seconds."""
    return _digest_interval

def set_digest_interval(minutes: float):
    """Update the HourlyDigest interval at runtime (clamped 1–1440 min / 1 day)."""
    global _digest_interval
    _digest_interval = max(60.0, min(86400.0, float(minutes) * 60))
    log.info(f"[hourly] interval set to {_digest_interval / 60:.1f}min")

_sb = None

def _get_db():
    global _sb
    if _sb is None:
        _sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _sb


class HourlyCollector:
    """Pulls last-hour activity from all subsystems."""

    def __init__(self, lookback_hours: float = 1.0):
        self.lookback_hours = lookback_hours

    def _since(self) -> str:
        return (datetime.now(timezone.utc) - timedelta(hours=self.lookback_hours)).isoformat()

    async def collect_all(self) -> Dict:
        since = self._since()
        results = {}

        # ── Panel Court ──
        try:
            db = _get_db()
            r = db.table("panel_court_decisions") \
                .select("verdict,score,winner_agent_id,created_at") \
                .gte("created_at", since) \
                .order("created_at", desc=True).limit(200).execute()
            rows = r.data or []
            dispatched = sum(1 for r in rows if r.get("verdict") == "DISPATCH")
            rejected = sum(1 for r in rows if r.get("verdict") == "REJECT")
            results["panel_court"] = {
                "decisions": len(rows),
                "dispatched": dispatched,
                "rejected": rejected,
                "dispatch_rate": round(dispatched / len(rows), 3) if rows else 0,
            }
        except Exception as e:
            results["panel_court"] = {"error": str(e)[:80]}

        # ── Brain Memory ──
        try:
            r = db.table("brain_memory") \
                .select("decision,outcome,actual_fee,urgency,created_at") \
                .gte("created_at", since) \
                .order("created_at", desc=True).limit(300).execute()
            rows = r.data or []
            go_count = sum(1 for r in rows if r.get("decision") == "GO")
            no_go = sum(1 for r in rows if r.get("decision") == "NO_GO")
            settled = [r for r in rows if r.get("outcome") == "settled"]
            total_fees = sum(float(r.get("actual_fee") or 0) for r in settled)
            results["brain"] = {
                "decisions": len(rows),
                "go": go_count,
                "no_go": no_go,
                "settled": len(settled),
                "settled_revenue": round(total_fees, 2),
            }
        except Exception as e:
            results["brain"] = {"error": str(e)[:80]}

        # ── SEO ──
        try:
            r = db.table("seo_content") \
                .select("keyword,converted,created_at") \
                .gte("created_at", since).limit(100).execute()
            ct_rows = r.data or []
            converted = sum(1 for r in ct_rows if r.get("converted"))
            results["seo"] = {
                "content_generated": len(ct_rows),
                "content_converted": converted,
            }
        except Exception as e:
            results["seo"] = {"error": str(e)[:80]}

        # ── Dispatches ──
        try:
            r = db.table("dispatches") \
                .select("status,created_at") \
                .gte("created_at", since).limit(200).execute()
            rows = r.data or []
            sent = sum(1 for r in rows if r.get("status") == "sent")
            conv = sum(1 for r in rows if r.get("status") in ("converted", "settled"))
            results["dispatches"] = {
                "total": len(rows),
                "sent": sent,
                "converted": conv,
            }
        except Exception as e:
            results["dispatches"] = {"error": str(e)[:80]}

        # ── Call Logs ──
        try:
            r = db.table("call_logs") \
                .select("qualified,duration_s,created_at") \
                .gte("created_at", since).limit(200).execute()
            rows = r.data or []
            qualified = sum(1 for r in rows if r.get("qualified"))
            total_dur = sum(int(r.get("duration_s") or 0) for r in rows)
            results["calls"] = {
                "total": len(rows),
                "qualified": qualified,
                "total_seconds": total_dur,
            }
        except Exception as e:
            results["calls"] = {"error": str(e)[:80]}

        # ── Inbound Leads ──
        try:
            r = db.table("inbound_leads") \
                .select("status,source,created_at") \
                .gte("created_at", since).limit(200).execute()
            rows = r.data or []
            new_leads = sum(1 for r in rows if r.get("status") in ("new", None))
            qualified_leads = sum(1 for r in rows if r.get("status") == "qualified")
            results["inbound"] = {
                "new_leads": len(rows),
                "new": new_leads,
                "qualified": qualified_leads,
            }
        except Exception as e:
            results["inbound"] = {"error": str(e)[:80]}

        # ── Radar Targets (lead gen) ──
        try:
            r = db.table("radar_targets") \
                .select("source,created_at") \
                .gte("created_at", since).limit(200).execute()
            rows = r.data or []
            results["radar"] = {"targets_found": len(rows)}
        except Exception as e:
            results["radar"] = {"error": str(e)[:80]}

        # ── SI Strategy ──
        try:
            r = db.table("si_strategy_history") \
                .select("strategy_name,niche,win_rate,status,created_at") \
                .gte("created_at", since).limit(50).execute()
            rows = r.data or []
            active = [r for r in rows if r.get("status") == "active"]
            results["si_strategy"] = {
                "strategies_run": len(rows),
                "active": len(active),
            }
        except Exception as e:
            results["si_strategy"] = {"error": str(e)[:80]}

        # ── Dream Memory (latest cycle) ──
        try:
            r = db.table("dream_memory") \
                .select("dream_cycle,insights,risk_flags,wisdom_context,created_at") \
                .order("dream_cycle", desc=True).limit(1).execute()
            if r.data:
                d = r.data[0]
                insights = d.get("insights") or []
                risks = d.get("risk_flags") or []
                if isinstance(insights, str):
                    import json as _j
                    try: insights = _j.loads(insights)
                    except: insights = []
                if isinstance(risks, str):
                    import json as _j
                    try: risks = _j.loads(risks)
                    except: risks = []
                results["dream"] = {
                    "latest_cycle": d.get("dream_cycle"),
                    "insight_count": len(insights),
                    "risk_count": len(risks),
                    "risks": risks[:5] if risks else [],
                    "wisdom_snippet": (d.get("wisdom_context") or "")[:200],
                }
            else:
                results["dream"] = {"latest_cycle": None}
        except Exception as e:
            results["dream"] = {"error": str(e)[:80]}

        results["_meta"] = {
            "since": since,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "lookback_hours": self.lookback_hours,
        }
        return results


class HourlyFormatter:
    """Renders collected data as a clean plain-text report."""

    def format(self, data: Dict) -> str:
        meta = data.get("_meta", {})
        pc = data.get("panel_court", {})
        brain = data.get("brain", {})
        seo = data.get("seo", {})
        dsp = data.get("dispatches", {})
        calls = data.get("calls", {})
        inbound = data.get("inbound", {})
        radar = data.get("radar", {})
        si = data.get("si_strategy", {})
        dream = data.get("dream", {})

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            "╔══════════════════════════════════════════════════════════════╗",
            "║  EMPIRE V49 · HOURLY ACTIVITY DIGEST                       ║",
            f"║  {now_str}                                         ║",
            "╚══════════════════════════════════════════════════════════════╝",
            "",
            "─── PANEL COURT ───",
            f"  Ensemble decisions : {pc.get('decisions', '?')}",
            f"  Dispatched         : {pc.get('dispatched', '?')}",
            f"  Rejected           : {pc.get('rejected', '?')}",
            f"  Dispatch rate      : {pc.get('dispatch_rate', '?')}",
            "",
            "─── BRAIN MEMORY ───",
            f"  Total decisions    : {brain.get('decisions', '?')}",
            f"  GO                 : {brain.get('go', '?')}",
            f"  NO_GO              : {brain.get('no_go', '?')}",
            f"  Settled            : {brain.get('settled', '?')}",
            f"  Settled revenue    : ${brain.get('settled_revenue', 0):,.2f}",
            "",
            "─── SEO ───",
            f"  Content generated  : {seo.get('content_generated', '?')}",
            f"  Content converted  : {seo.get('content_converted', '?')}",
            "",
            "─── DISPATCHES ───",
            f"  Total              : {dsp.get('total', '?')}",
            f"  Sent               : {dsp.get('sent', '?')}",
            f"  Converted          : {dsp.get('converted', '?')}",
            "",
            "─── CALLS ───",
            f"  Total calls        : {calls.get('total', '?')}",
            f"  Qualified          : {calls.get('qualified', '?')}",
            f"  Total talk time    : {calls.get('total_seconds', 0)}s",
            "",
            "─── INBOUND LEADS ───",
            f"  New leads          : {inbound.get('new_leads', '?')}",
            f"  Fresh (unread)     : {inbound.get('new', '?')}",
            f"  Qualified          : {inbound.get('qualified', '?')}",
            "",
            "─── RADAR ───",
            f"  Targets found      : {radar.get('targets_found', '?')}",
            "",
            "─── SI STRATEGY ───",
            f"  Strategies run     : {si.get('strategies_run', '?')}",
            f"  Active strategies  : {si.get('active', '?')}",
            "",
            "─── DREAM MEMORY ───",
        ]

        if dream.get("latest_cycle"):
            lines += [
                f"  Latest cycle       : #{dream.get('latest_cycle')}",
                f"  Insights           : {dream.get('insight_count', 0)}",
                f"  Risk flags         : {dream.get('risk_count', 0)}",
            ]
            for risk in dream.get("risks", []):
                lines.append(f"    ⚠ {risk}")
            if dream.get("wisdom_snippet"):
                lines.append(f"  Wisdom             : {dream['wisdom_snippet']}")
        else:
            lines.append("  No dreams recorded yet.")

        lines += [
            "",
            "─── TOTALS ───",
        ]

        total_events = (
            pc.get("decisions", 0)
            + brain.get("decisions", 0)
            + seo.get("content_generated", 0)
            + dsp.get("total", 0)
            + calls.get("total", 0)
            + inbound.get("new_leads", 0)
            + radar.get("targets_found", 0)
            + si.get("strategies_run", 0)
        )
        lines.append(f"  Total events       : {total_events}")

        total_revenue = brain.get("settled_revenue", 0)
        lines.append(f"  Revenue (settled)  : ${total_revenue:,.2f}")

        lines += [
            "",
            f"  Generated {now_str} · Empire V49 · Next digest in ~60 min",
            "",
        ]

        return "\n".join(lines)


class HourlyDigestLoop:
    """Background task. Collects and writes digest every hour."""

    def __init__(self):
        self.collector = HourlyCollector(lookback_hours=1.0)
        self.formatter = HourlyFormatter()
        self.cycles = 0

    async def run(self):
        log.info(f"[hourly] Digest Loop ONLINE · {_digest_interval / 60:.0f}min tick → {DIGEST_PATH}")
        while True:
            try:
                data = await self.collector.collect_all()
                text = self.formatter.format(data)
                tmp_path = DIGEST_PATH + ".tmp"
                with open(tmp_path, "w") as f:
                    f.write(text)
                os.replace(tmp_path, DIGEST_PATH)
                self.cycles += 1
                log.info(f"[hourly] Digest #{self.cycles} written → {DIGEST_PATH} ({len(text)} chars)")
            except Exception as e:
                log.error(f"[hourly] Digest failed: {e}")
            await asyncio.sleep(_digest_interval)


# ═══════════════════════════════════════════════════════════════════════════
# STANDALONE CLI
# ═══════════════════════════════════════════════════════════════════════════
async def digest_once():
    """Run one digest cycle for testing."""
    loop = HourlyDigestLoop()
    data = await loop.collector.collect_all()
    text = loop.formatter.format(data)
    print(text)
    tmp_path = DIGEST_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        f.write(text)
    os.replace(tmp_path, DIGEST_PATH)
    print(f"\nSaved to {DIGEST_PATH}")


if __name__ == "__main__":
    asyncio.run(digest_once())
