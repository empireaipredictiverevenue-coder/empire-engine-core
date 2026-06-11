"""
EMPIRE V49 · DREAM MEMORY SYSTEM
=================================
Cross-system offline reflection engine. Every 6 hours, collects all recent
activity from every subsystem, runs an Ollama "dream" reflection, generates
actionable insights and rule adjustments, and stores consolidated wisdom.

ARCHITECTURE
────────────
  1. DreamCollector  — pulls recent data from Panel Court, Brain, SEO,
                        Voice, Dispatch, SI Strategy, Agent Mesh
  2. DreamProcessor  — builds a comprehensive prompt, calls Ollama for
                        pattern recognition and cross-system insight
  3. DreamMemory     — stores dreams in dream_memory Supabase table,
                        retrieves latest wisdom for context injection
  4. DreamLoop       — background asyncio task, 6-hour tick

  5. context_inject  — renders the latest dream's wisdom as a prompt block
                        that Brain + Panel Court inject into their decisions

WIRE-UP
───────
    hub.py startup:
        from empire_dream import DreamLoop
        dream_loop = DreamLoop()
        asyncio.create_task(dream_loop.run())

    empire_brain_decide.py / panel_court.py:
        from empire_dream import get_latest_wisdom
        wisdom = await get_latest_wisdom()
        prompt += wisdom  # inject as calibration context

SUPABASE TABLE
──────────────
    CREATE TABLE IF NOT EXISTS dream_memory (
      id                uuid DEFAULT gen_random_uuid() PRIMARY KEY,
      created_at        timestamptz DEFAULT now(),
      dream_cycle       int NOT NULL,
      sources_analyzed  jsonb DEFAULT '[]'::jsonb,
      sample_sizes      jsonb DEFAULT '{}'::jsonb,
      insights          jsonb DEFAULT '[]'::jsonb,
      rule_suggestions  jsonb DEFAULT '[]'::jsonb,
      wisdom_context    text DEFAULT '',
      narrative         text DEFAULT '',
      applied_rules     jsonb DEFAULT '[]'::jsonb,
      meta              jsonb DEFAULT '{}'::jsonb
    );
    CREATE INDEX IF NOT EXISTS idx_dream_cycle ON dream_memory (dream_cycle DESC);
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

import httpx

sys.path.insert(0, "/root/empire-v49")

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

from supabase import create_client

# Runtime-configurable interval (env var DREAM_INTERVAL_HOURS, default 6.0)
try:
    _dream_interval = float(os.environ.get("DREAM_INTERVAL_HOURS", "6.0"))
except (ValueError, TypeError):
    _dream_interval = 6.0

def get_dream_interval() -> float:
    """Return the current DreamLoop interval in hours."""
    return _dream_interval

def set_dream_interval(hours: float):
    """Update the DreamLoop interval at runtime (clamped 0.1–24.0h)."""
    global _dream_interval
    _dream_interval = max(0.1, min(24.0, float(hours)))
    logging.getLogger("empire.dream").info(f"[dream] interval set to {_dream_interval:.1f}h")

log = logging.getLogger("empire.dream")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DREAM_MODEL = os.environ.get("DREAM_MODEL", "llama3.1:latest")  # bigger model for deeper analysis
DREAM_MAX_TOKENS = int(os.environ.get("DREAM_MAX_TOKENS", "800"))

_sb = None

def _get_db():
    global _sb
    if _sb is None:
        _sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _sb


async def _push_dream_ntfy(cycle: int, risk_count: int, wisdom: str) -> None:
    """Push a ntfy.sh notification when a dream finds risks. Operators subscribe via the app's NTFY_TOPIC."""
    topic = os.environ.get("NTFY_TOPIC", "")
    if not topic:
        log.debug("[dream] NTFY_TOPIC not configured — skipping ntfy push")
        return
    try:
        import httpx
        token = os.environ.get("NTFY_TOKEN", "")
        title = f"Dream #{cycle}: {risk_count} risk{'s' if risk_count != 1 else ''} found"
        snippet = (wisdom or "").replace("\n", " ")[:200]
        body = f"{risk_count} risk flag(s) in cycle #{cycle}.\n{snippet}"
        headers = {"Title": title[:200], "Tags": "warning,dream", "Priority": "4"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient(timeout=10) as _client:
            await _client.post(
                f"https://ntfy.sh/{topic}",
                content=body[:1000],
                headers=headers,
            )
        log.info(f"[dream] ntfy push sent: cycle {cycle} {risk_count} risks")
    except Exception as e:
        log.warning(f"[dream] ntfy push failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# DREAM COLLECTOR
# ═══════════════════════════════════════════════════════════════════════════
class DreamCollector:
    """Pulls recent activity from all subsystems."""

    def __init__(self, lookback_hours: int = 6):
        self.lookback_hours = lookback_hours

    def _since(self) -> str:
        return (datetime.now(timezone.utc) - timedelta(hours=self.lookback_hours)).isoformat()

    async def collect_all(self) -> Dict[str, Any]:
        """Collect from all data sources. Returns a structured bundle."""
        since = self._since()

        panel_court = await self._collect_panel_court(since)
        brain_memory = await self._collect_brain_memory(since)
        seo = await self._collect_seo(since)
        dispatches = await self._collect_dispatches(since)
        si_strategy = await self._collect_si_strategy(since)

        # Cross-system derived stats
        cross = self._derive_cross_system(panel_court, brain_memory, seo, dispatches)

        return {
            "panel_court": panel_court,
            "brain_memory": brain_memory,
            "seo": seo,
            "dispatches": dispatches,
            "si_strategy": si_strategy,
            "cross_system": cross,
            "since": since,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _collect_panel_court(self, since: str) -> Dict:
        """Recent Panel Court ensemble decisions."""
        try:
            db = _get_db()
            # Schema: case_id, confidence, consensus_score, created_at, decision,
            #         id, niches, panel_size, reasoning, votes
            r = db.table("panel_court_decisions") \
                .select("decision,consensus_score,reasoning,created_at,case_id,niches,panel_size") \
                .gte("created_at", since) \
                .order("created_at", desc=True) \
                .limit(200) \
                .execute()
            rows = r.data or []
            decisions = [str(r.get("decision") or "").upper() for r in rows]
            dispatched = sum(1 for d in decisions if d == "DISPATCH")
            rejected = sum(1 for d in decisions if d in ("REJECT", "REJECTED"))
            scores = [float(r.get("consensus_score") or 0) for r in rows if r.get("consensus_score")]
            return {
                "total": len(rows),
                "dispatched": dispatched,
                "rejected": rejected,
                "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
                "top_wiche": self._top_values(rows, "niches"),
                "sample_verdicts": [
                    {"verdict": r.get("decision"), "score": r.get("consensus_score"),
                     "case_id": r.get("case_id"),
                     "reasoning": (r.get("reasoning") or "")[:120]}
                    for r in rows[:5]
                ],
            }
        except Exception as e:
            log.warning(f"[dream] panel_court collection failed: {e}")
            return {"error": str(e), "total": 0}

    async def _collect_brain_memory(self, since: str) -> Dict:
        """Recent Brain decisions with outcomes."""
        try:
            db = _get_db()
            r = db.table("brain_memory") \
                .select("decision,urgency,outcome,actual_fee,city,severity,asset_value,context_text,created_at") \
                .gte("created_at", since) \
                .order("created_at", desc=True) \
                .limit(300) \
                .execute()
            rows = r.data or []
            go_count = sum(1 for r in rows if r.get("decision") == "GO")
            no_go_count = sum(1 for r in rows if r.get("decision") == "NO_GO")
            with_outcome = [r for r in rows if r.get("outcome") and r.get("outcome") != "pending"]
            settled = [r for r in with_outcome if r.get("outcome") == "settled"]
            avg_fee = sum(float(r.get("actual_fee") or 0) for r in settled) / len(settled) if settled else 0
            return {
                "total": len(rows),
                "go": go_count,
                "no_go": no_go_count,
                "with_outcomes": len(with_outcome),
                "settled": len(settled),
                "settle_rate": round(len(settled) / len(with_outcome), 3) if with_outcome else 0,
                "avg_settled_fee": round(avg_fee, 2),
                "top_cities": self._top_values(rows, "city"),
                "sample_decisions": [
                    {"context": (r.get("context_text") or "")[:100], "decision": r.get("decision"),
                     "outcome": r.get("outcome"), "fee": r.get("actual_fee")}
                    for r in rows[:5]
                ],
            }
        except Exception as e:
            log.warning(f"[dream] brain_memory collection failed: {e}")
            return {"error": str(e), "total": 0}

    async def _collect_seo(self, since: str) -> Dict:
        """Recent SEO content performance, keyword conversions, and genome evolution."""
        try:
            db = _get_db()
            # Keywords with conversion data
            kw_r = db.table("seo_keywords") \
                .select("keyword,conversions,conversion_rate,total_revenue,niche,metro,last_outcome") \
                .not_.is_("last_outcome", "null") \
                .gte("last_outcome_ts", since) \
                .order("conversion_rate", desc=True) \
                .limit(100) \
                .execute()
            kw_rows = kw_r.data or []
            # Content with attribution
            ct_r = db.table("seo_content") \
                .select("keyword,niche,converted,attributed_lead_id,created_at") \
                .gte("created_at", since) \
                .limit(100) \
                .execute()
            ct_rows = ct_r.data or []
            converted = [r for r in ct_rows if r.get("converted")]
            # Genome evolution history
            genome_r = db.table("seo_genome_history") \
                .select("generation,genome,top_keywords,avg_conversion_rate,created_at") \
                .gte("created_at", since) \
                .order("generation", desc=True) \
                .limit(20) \
                .execute()
            genome_rows = genome_r.data or []
            # Parse genome JSONB if needed
            parsed_genomes = []
            for g in genome_rows[:5]:
                gm = g.get("genome") or {}
                if isinstance(gm, str):
                    try: gm = json.loads(gm)
                    except Exception: pass
                parsed_genomes.append({
                    "gen": g.get("generation"),
                    "traits": {
                        k: round(float(v), 3) if isinstance(v, (int, float)) else v
                        for k, v in (gm.items() if isinstance(gm, dict) else {})
                    },
                    "top_kw": (g.get("top_keywords") or [])[:3] if isinstance(g.get("top_keywords"), list) else [],
                    "conv_rate": g.get("avg_conversion_rate"),
                })
            # Detect genome trait trends across generations
            trend = None
            if len(genome_rows) >= 2:
                newest = genome_rows[0].get("genome") or {}
                oldest = genome_rows[-1].get("genome") or {}
                if isinstance(newest, str):
                    try: newest = json.loads(newest)
                    except Exception: pass
                if isinstance(oldest, str):
                    try: oldest = json.loads(oldest)
                    except Exception: pass
                if isinstance(newest, dict) and isinstance(oldest, dict):
                    trend = {}
                    for trait in ["keyword_competitiveness", "local_intent", "content_depth", "technical_rigor", "link_authority"]:
                        nv = float(newest.get(trait, 0))
                        ov = float(oldest.get(trait, 0))
                        if ov is not None and ov != 0:
                            trend[trait] = round((nv - ov) / ov, 3)
            return {
                "keywords_tracked": len(kw_rows),
                "content_generated": len(ct_rows),
                "content_converted": len(converted),
                "conversion_rate": round(len(converted) / len(ct_rows), 3) if ct_rows else 0,
                "genome_evolutions": len(genome_rows),
                "genome_generations": parsed_genomes,
                "genome_trend": trend,
                "top_keywords": [
                    {"kw": r.get("keyword"), "rate": r.get("conversion_rate"), "revenue": r.get("total_revenue")}
                    for r in kw_rows[:5]
                ],
                "sample_content": [
                    {"kw": r.get("keyword"), "converted": r.get("converted")}
                    for r in ct_rows[:5]
                ],
            }
        except Exception as e:
            log.warning(f"[dream] SEO collection failed: {e}")
            return {"error": str(e), "total": 0}

    async def _collect_dispatches(self, since: str) -> Dict:
        """Recent dispatches and conversion rates."""
        try:
            db = _get_db()
            r = db.table("dispatches") \
                .select("status,created_at") \
                .gte("created_at", since) \
                .limit(200) \
                .execute()
            rows = r.data or []
            sent = sum(1 for r in rows if r.get("status") == "sent")
            converted = sum(1 for r in rows if r.get("status") in ("converted", "settled"))
            return {
                "total": len(rows),
                "sent": sent,
                "converted": converted,
                "conversion_rate": round(converted / sent, 3) if sent else 0,
            }
        except Exception as e:
            log.warning(f"[dream] dispatch collection failed: {e}")
            return {"error": str(e), "total": 0}

    async def _collect_si_strategy(self, since: str) -> Dict:
        """Recent SI Strategy performance."""
        try:
            db = _get_db()
            # Schema: avg_conversion_rate, created_at, generation, genome, id,
            #         sample_size, top_keywords (renamed from si_strategy_history)
            r = db.table("seo_genome_history") \
                .select("generation,genome,top_keywords,avg_conversion_rate,sample_size,created_at") \
                .gte("created_at", since) \
                .order("created_at", desc=True) \
                .limit(100) \
                .execute()
            rows = r.data or []
            rates = [float(r.get("avg_conversion_rate") or 0) for r in rows if r.get("avg_conversion_rate") is not None]
            return {
                "total": len(rows),
                "active_strategies": len(rows),  # every genome row is an active generation
                "avg_win_rate": round(sum(rates) / len(rates), 4) if rates else 0,
                "top_keywords": self._top_values([{"kw": k} for r in rows for k in (r.get("top_keywords") or [])], "kw"),
                "sample": [
                    {"generation": r.get("generation"),
                     "avg_conversion_rate": r.get("avg_conversion_rate"),
                     "sample_size": r.get("sample_size"),
                     "top_keywords": r.get("top_keywords")}
                    for r in rows[:5]
                ],
            }
        except Exception as e:
            log.warning(f"[dream] SI strategy collection failed: {e}")
            return {"error": str(e), "total": 0}

    def _derive_cross_system(self, panel: Dict, brain: Dict, seo: Dict, dispatch: Dict) -> Dict:
        """Cross-system derived insights from raw data."""
        return {
            "panel_dispatch_rate": round(panel.get("dispatched", 0) / max(panel.get("total", 1), 1), 3),
            "brain_go_rate": round(brain.get("go", 0) / max(brain.get("total", 1), 1), 3),
            "seo_conversion_rate": seo.get("conversion_rate", 0),
            "dispatch_conversion_rate": dispatch.get("conversion_rate", 0),
            "total_activity": (panel.get("total", 0) + brain.get("total", 0) +
                               seo.get("content_generated", 0) + dispatch.get("total", 0)),
        }

    def _top_agents(self, rows: List[Dict], key: str, top_n: int = 3) -> List[Dict]:
        from collections import Counter
        cnt = Counter(r.get(key) for r in rows if r.get(key))
        return [{"id": k, "count": v} for k, v in cnt.most_common(top_n)]

    def _top_values(self, rows: List[Dict], key: str, top_n: int = 5) -> List[Dict]:
        from collections import Counter
        cnt = Counter(r.get(key) for r in rows if r.get(key))
        return [{"value": k, "count": v} for k, v in cnt.most_common(top_n)]


# ═══════════════════════════════════════════════════════════════════════════
# DREAM PROCESSOR
# ═══════════════════════════════════════════════════════════════════════════
class DreamProcessor:
    """Builds the dream prompt, calls Ollama, parses the reflection."""

    DREAM_SYSTEM = """You are the Empire V49 Dream Engine — a deep offline reflection AI that consolidates
all recent activity across the Empire's subsystems and extracts actionable wisdom.

You receive a structured report of recent activity from:
- Panel Court (10-agent ensemble decisions with critiques, hybrid verdicts, agent pool state)
- Brain Memory (urgency-based GO/NO_GO decisions with real-world outcomes and settlement fees)
- SEO (content generation, keyword conversion tracking, genome evolution)
- Dispatch (lead-to-buyer dispatches with conversion rates)
- SI Strategy (adaptive strategy evolution with win rates and revenue)

Your job — THINK DEEPLY:
1. IDENTIFY PATTERNS — what's working, what's failing, what's correlated? Look for non-obvious
   connections. E.g., "agents with temperature 0.08-0.10 win 3x more when leads are from storm sources"
2. CROSS-SYSTEM INSIGHTS — spot connections between systems. E.g., "when Panel Court dispatches
   at score >85 AND the lead came from SEO content, conversion rate is 42% vs 18% baseline"
3. TREND DETECTION — are things getting better or worse? Which direction are the rates moving?
4. RULE SUGGESTIONS — propose concrete, actionable threshold/rules adjustments with confidence (1-10).
   Include current context so operators understand what you're changing.
5. WISDOM — write a focused calibration narrative (2-4 sentences) that future Brain + Panel Court
   decisions can reference. Be specific: cite rates, patterns, and what to watch for.
6. RISK FLAGS — if you see something concerning (plummeting rates, bias toward one agent, zero
   conversions from a source), call it out explicitly.

Return ONLY this JSON format:
{
  "insights": [
    {"text": "pattern description with specific numbers", "confidence": 1-10,
     "systems": ["panel_court","brain"], "action": "concrete next step"}
  ],
  "rule_suggestions": [
    {"rule": "rule_name", "current": "current value with context", "suggested": "new value",
     "confidence": 1-10, "reasoning": "data-driven justification"}
  ],
  "wisdom": "2-4 sentence calibration narrative for context injection",
  "narrative": "comprehensive dream reflection, 3-5 paragraphs with specific numbers",
  "risk_flags": ["concern 1", "concern 2"]
}"""

    def __init__(self, ollama_url: str = OLLAMA_URL):
        self.url = ollama_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))
        self.cycle = 0

    async def close(self):
        await self._client.aclose()

    async def dream(self, data: Dict) -> Dict:
        """Run one dream cycle on collected data."""
        self.cycle += 1
        prompt = self._build_dream_prompt(data)
        log.info(f"[dream] cycle {self.cycle} — processing {data.get('cross_system', {}).get('total_activity', 0)} events")

        try:
            r = await self._client.post(
                f"{self.url}/api/chat",
                json={
                    "model": DREAM_MODEL,
                    "messages": [
                        {"role": "system", "content": self.DREAM_SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.3, "num_predict": DREAM_MAX_TOKENS},
                },
            )
            r.raise_for_status()
            raw = r.json().get("message", {}).get("content", "{}")
            return self._parse(raw)
        except Exception as e:
            log.error(f"[dream] Ollama call failed: {e}")
            return {"_error": str(e), "insights": [], "rule_suggestions": [],
                    "wisdom": "", "narrative": f"Dream cycle {self.cycle} failed: {e}"}

    def _build_dream_prompt(self, data: Dict) -> str:
        """Build the dream prompt from collected data."""
        pc = data.get("panel_court", {})
        bm = data.get("brain_memory", {})
        seo = data.get("seo", {})
        dsp = data.get("dispatches", {})
        si = data.get("si_strategy", {})
        cross = data.get("cross_system", {})

        lines = [
            f"=== DREAM CYCLE {self.cycle} === Period: last {data.get('since', '?')} to now",
            "",
            "─── CROSS-SYSTEM OVERVIEW ───",
            f"Total activity events: {cross.get('total_activity', 0)}",
            f"Panel dispatch rate: {cross.get('panel_dispatch_rate', 0)}",
            f"Brain GO rate: {cross.get('brain_go_rate', 0)}",
            f"SEO conversion rate: {cross.get('seo_conversion_rate', 0)}",
            f"Dispatch conversion rate: {cross.get('dispatch_conversion_rate', 0)}",
            "",
            "─── PANEL COURT (10-agent ensemble) ───",
            f"Decisions: {pc.get('total', 0)} | Dispatched: {pc.get('dispatched', 0)} | Rejected: {pc.get('rejected', 0)} | Avg score: {pc.get('avg_score', 0)}",
            f"Top winning agents: {json.dumps(pc.get('top_winner_agents', []))}",
            "Recent verdicts:",
        ]
        for v in pc.get("sample_verdicts", []):
            lines.append(f"  {v.get('verdict')} score={v.get('score')} winner=Agent#{v.get('winner')} | {v.get('reasoning', '')}")

        lines += [
            "",
            "─── BRAIN MEMORY ───",
            f"Decisions: {bm.get('total', 0)} | GO: {bm.get('go', 0)} | NO_GO: {bm.get('no_go', 0)}",
            f"With outcomes: {bm.get('with_outcomes', 0)} | Settled: {bm.get('settled', 0)} | Settle rate: {bm.get('settle_rate', 0)}",
            f"Avg settled fee: ${bm.get('avg_settled_fee', 0):,.2f}",
            f"Top cities: {json.dumps(bm.get('top_cities', []))}",
            "Recent decisions:",
        ]
        for d in bm.get("sample_decisions", []):
            lines.append(f"  {d.get('context', '')} | decision={d.get('decision')} outcome={d.get('outcome')} fee=${d.get('fee', 0)}")

        lines += [
            "",
            "─── SEO ───",
            f"Content generated: {seo.get('content_generated', 0)} | Converted: {seo.get('content_converted', 0)} | Rate: {seo.get('conversion_rate', 0)}",
            f"Keywords tracked: {seo.get('keywords_tracked', 0)}",
            f"Genome evolutions this period: {seo.get('genome_evolutions', 0)}",
            f"Top keywords: {json.dumps(seo.get('top_keywords', []))}",
        ]
        # Add genome evolution details if available
        generations = seo.get("genome_generations") or []
        if generations:
            lines.append("Genome evolution timeline:")
            for g in generations:
                traits_str = ", ".join(f"{k}={v}" for k, v in (g.get("traits") or {}).items())
                lines.append(f"  Gen#{g.get('gen')} conv_rate={g.get('conv_rate')} traits=[{traits_str}] top_kw={g.get('top_kw')}")
        trend = seo.get("genome_trend")
        if trend:
            trend_str = ", ".join(f"{k}: {'+' if v >= 0 else ''}{v}" for k, v in trend.items())
            lines.append(f"Genome trait drift (oldest→newest): {trend_str}")
        lines += [
            "",
            "─── DISPATCHES ───",
            f"Total: {dsp.get('total', 0)} | Sent: {dsp.get('sent', 0)} | Converted: {dsp.get('converted', 0)} | Rate: {dsp.get('conversion_rate', 0)}",
            "",
            "─── SI STRATEGY (Strategy Evolution + Media Pipeline) ───",
            f"Strategies: {si.get('total', 0)} | Active: {si.get('active_strategies', 0)} | Avg win rate: {si.get('avg_win_rate', 0)}",
            f"Top niches: {json.dumps(si.get('top_niches', []))}",
            "",
            "Analyze all of the above including SI strategy evolution patterns. Find cross-system correlations. Suggest improvements. Return JSON.",
        ]

        return "\n".join(lines)  # no truncation — bigger model handles it

    def _parse(self, raw: str) -> Dict:
        # Reuse the shared JSON parser from panel_court
        try:
            from bots.panel_court import _parse_json
            parsed = _parse_json(raw)
            if parsed.get("_parse_error"):
                return {"_parse_error": True, "_raw": raw[:200],
                        "insights": [], "rule_suggestions": [],
                        "wisdom": "", "narrative": f"Dream parse failed: {raw[:200]}"}
            return parsed
        except ImportError:
            clean = raw.strip()
            if "```json" in clean:
                clean = clean.split("```json")[1].split("```")[0].strip()
            elif "```" in clean:
                clean = clean.split("```")[1].split("```")[0].strip()
            try:
                return json.loads(clean)
            except json.JSONDecodeError:
                return {"_parse_error": True, "_raw": raw[:200],
                        "insights": [], "rule_suggestions": [],
                        "wisdom": "", "narrative": f"Dream parse failed: {raw[:200]}"}


# ═══════════════════════════════════════════════════════════════════════════
# DREAM MEMORY STORE
# ═══════════════════════════════════════════════════════════════════════════
class DreamMemory:
    """Stores and retrieves dreams from Supabase."""

    def __init__(self, collector: DreamCollector, processor: DreamProcessor, broadcaster=None):
        self.collector = collector
        self.processor = processor
        self.broadcaster = broadcaster
        self.stats = {"dreams_completed": 0, "rules_applied": 0, "last_dream_at": None, "last_error": None}

    async def run_dream_cycle(self) -> Dict:
        """Full dream cycle: collect → process → store → apply rules."""
        try:
            # 1. Collect
            data = await self.collector.collect_all()

            # 2. Dream
            dream = await self.processor.dream(data)

            # 3. Store
            await self._store(data, dream)

            # 4. Apply high-confidence rule suggestions
            applied = await self._apply_rules(dream.get("rule_suggestions", []))

            self.stats["dreams_completed"] += 1
            self.stats["rules_applied"] += len(applied)
            self.stats["last_dream_at"] = datetime.now(timezone.utc).isoformat()

            log.info(f"[dream] cycle {self.processor.cycle} complete — "
                     f"{len(dream.get('insights', []))} insights, "
                     f"{len(applied)} rules applied")

            # Broadcast dream event to WebSocket clients
            if self.broadcaster:
                try:
                    await self.broadcaster.broadcast({
                        "type": "dream_stored",
                        "cycle": self.processor.cycle,
                        "insight_count": len(dream.get("insights", [])),
                        "risk_count": len(dream.get("risk_flags") or []),
                        "rule_count": len(dream.get("rule_suggestions", [])),
                        "rules_applied": len(applied),
                        "wisdom_snippet": (dream.get("wisdom", "") or "")[:200],
                        "risk_flags": dream.get("risk_flags") or [],
                    })
                except Exception:
                    pass
            # Push ntfy notification when risks are found
            risk_flags_now = dream.get("risk_flags") or []
            if risk_flags_now:
                try:
                    await _push_dream_ntfy(self.processor.cycle, len(risk_flags_now), dream.get("wisdom", "") or "")
                except Exception:
                    pass

            return {
                "ok": True,
                "cycle": self.processor.cycle,
                "insights": len(dream.get("insights", [])),
                "rule_suggestions": len(dream.get("rule_suggestions", [])),
                "rules_applied": len(applied),
                "wisdom": (dream.get("wisdom", "") or "")[:200],
            }
        except Exception as e:
            log.error(f"[dream] cycle failed: {e}")
            self.stats["last_error"] = str(e)
            return {"ok": False, "error": str(e)}

    async def _store(self, data: Dict, dream: Dict):
        """Persist dream to Supabase. Strips any fields not in the actual
        dream_memory schema to keep the write path schema-tolerant."""
        # Actual dream_memory columns (verified via PostgREST introspection)
        ALLOWED_COLUMNS = {
            "dream_cycle", "collection_window_hours", "sources", "sample_sizes",
            "insights", "rule_suggestions", "wisdom_context", "narrative",
            "applied_rules", "risk_flags", "meta", "created_at",
        }
        try:
            db = _get_db()
            sources = [k for k in ["panel_court", "brain_memory", "seo", "dispatches", "si_strategy"]
                       if data.get(k, {}).get("total", 0) > 0]
            sample_sizes = {k: data.get(k, {}).get("total", 0) for k in sources}

            payload = {
                "dream_cycle": self.processor.cycle,
                "sources": sources,
                "sample_sizes": sample_sizes,
                "insights": dream.get("insights", []),
                "rule_suggestions": dream.get("rule_suggestions", []),
                "wisdom_context": (dream.get("wisdom", "") or "")[:2000],
                "narrative": (dream.get("narrative", "") or "")[:3000],
                "applied_rules": [],
                "risk_flags": dream.get("risk_flags") or [],
                "meta": {"collected_at": data.get("collected_at"), "cross_system": data.get("cross_system", {})},
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            # Defensive: drop anything not in the known schema
            payload = {k: v for k, v in payload.items() if k in ALLOWED_COLUMNS}

            db.table("dream_memory").insert(payload).execute()
        except Exception as e:
            log.warning(f"[dream] DB store failed (table may not exist): {e}")

    async def _apply_rules(self, suggestions: List[Dict]) -> List[Dict]:
        """Auto-apply rules with confidence >= 8. Pushes SEO genome rules to SEO agent."""
        applied = []
        seo_traits = {"keyword_competitiveness", "local_intent", "content_depth",
                       "technical_rigor", "link_authority"}
        for s in suggestions:
            conf = s.get("confidence", 0)
            if conf >= 8:
                rule_name = s.get("rule", "unknown")
                suggested = s.get("suggested", "")
                log.info(f"[dream] auto-applying rule '{rule_name}': {suggested} (confidence={conf})")
                # Push SEO genome rules to the SEO agent
                rule_lower = rule_name.lower().replace(" ", "_")
                if any(trait in rule_lower for trait in seo_traits):
                    try:
                        from bots.seo_agent import get_seo_agent
                        agent = get_seo_agent()
                        applied_trait = agent.apply_dream_rule(s)
                        if applied_trait:
                            log.info(f"[dream] pushed genome rule to SEO agent: {rule_name}")
                    except Exception as e:
                        log.warning(f"[dream] failed to push SEO rule: {e}")
                applied.append(s)
            elif conf >= 5:
                log.info(f"[dream] rule '{s.get('rule')}' flagged for review (confidence={conf})")
        return applied

    async def get_latest_wisdom(self) -> Optional[str]:
        """Return the most recent dream's wisdom context for injection."""
        try:
            db = _get_db()
            r = db.table("dream_memory") \
                .select("wisdom_context,dream_cycle,created_at") \
                .order("dream_cycle", desc=True) \
                .limit(1) \
                .execute()
            rows = r.data or []
            if rows and rows[0].get("wisdom_context"):
                return rows[0]["wisdom_context"]
        except Exception:
            pass
        return None


# ═══════════════════════════════════════════════════════════════════════════
# DREAM LOOP
# ═══════════════════════════════════════════════════════════════════════════
class DreamLoop:
    """Background task. Runs dream cycles every 6 hours."""

    def __init__(self, broadcaster=None):
        self.collector = DreamCollector(lookback_hours=24.0)  # full day of activity
        self.processor = DreamProcessor()
        self.memory = DreamMemory(self.collector, self.processor, broadcaster=broadcaster)

    async def run(self):
        """Forever loop. Dreams every interval_hours."""
        log.info(f"[dream] Dream Loop ONLINE · {_dream_interval:.1f}h tick")
        while True:
            try:
                result = await self.memory.run_dream_cycle()
                if not result.get("ok"):
                    log.warning(f"[dream] cycle returned error: {result.get('error')}")
            except Exception as e:
                log.error(f"[dream] loop crash: {e}")
            await asyncio.sleep(_dream_interval * 3600)

    def stats(self) -> Dict:
        return self.memory.stats


# ═══════════════════════════════════════════════════════════════════════════
# CONTEXT INJECTION — use in Brain + Panel Court prompts
# ═══════════════════════════════════════════════════════════════════════════
_DREAM_LOOP_SINGLETON: Optional[DreamLoop] = None

def set_dream_loop(loop: DreamLoop):
    global _DREAM_LOOP_SINGLETON
    _DREAM_LOOP_SINGLETON = loop

async def get_latest_wisdom() -> str:
    """Return the latest dream's wisdom as a prompt block, or empty string."""
    if _DREAM_LOOP_SINGLETON is None:
        return ""
    wisdom = await _DREAM_LOOP_SINGLETON.memory.get_latest_wisdom()
    if not wisdom:
        return ""
    return (
        "\n\n=== DREAM MEMORY (recent patterns discovered across all systems) ===\n"
        f"{wisdom}\n"
        "Use these patterns to calibrate your decision.\n"
    )


# ═══════════════════════════════════════════════════════════════════════════
# STANDALONE CLI
# ═══════════════════════════════════════════════════════════════════════════
async def dream_once():
    """Run one dream cycle for testing."""
    loop = DreamLoop()
    result = await loop.memory.run_dream_cycle()
    print(json.dumps(result, indent=2, default=str))
    await loop.processor.close()


if __name__ == "__main__":
    asyncio.run(dream_once())
