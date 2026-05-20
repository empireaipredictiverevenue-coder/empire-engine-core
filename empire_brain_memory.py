"""
EMPIRE V49 · BRAIN MEMORY
===========================
Stores every brain decision with the outcome attached when it lands.
Uses pgvector embeddings in Supabase for similarity search.

Before each new brain decision, we retrieve the 5 most similar past leads
(by embedding cosine similarity) along with how they actually settled.
Those become few-shot examples in the brain prompt.

This is the honest "the brain learns" feature. Not magic AGI — just
retrieval-augmented decision-making that compounds over time.


HOW IT WORKS
────────────
  1. Brain evaluates a lead → record_decision() stores it in brain_memory
     with an embedding of {address + city + severity + asset_value + urgency}

  2. Operator records the outcome (settled/denied/withdrawn) → we link
     it back to brain_memory.outcome_id

  3. Next time the brain evaluates a similar lead, retrieve_similar()
     pulls the 5 closest past memories and their outcomes

  4. Those go into the brain prompt as:
       "Past similar leads:
        - {warehouse in Dallas, severe wind, $2M asset, urgency 8/10}
          → DECIDED: GO, OUTCOME: settled $185K
        - {warehouse in Houston, severe hail, $4M asset, urgency 9/10}
          → DECIDED: GO, OUTCOME: denied (no damage found)
        ..."

  5. Brain now decides with context. Win rate compounds.


SCHEMA
──────
    -- Enable pgvector (run once)
    CREATE EXTENSION IF NOT EXISTS vector;

    CREATE TABLE IF NOT EXISTS brain_memory (
      id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      created_at      timestamptz NOT NULL DEFAULT now(),
      lead_id         uuid,
      decision        text NOT NULL CHECK (decision IN ('GO','NO_GO')),
      urgency         int,
      reasoning       text,
      context_text    text NOT NULL,       -- the human-readable summary used for embedding
      embedding       vector(1536),         -- OpenAI text-embedding-3-small or similar
      asset_value     numeric(14,2),
      severity        text,
      city            text,
      outcome_id      uuid,                 -- links to claim_outcomes when known
      outcome         text,                 -- 'settled' | 'denied' | 'withdrawn' | 'pending'
      actual_fee      numeric(12,2),
      meta            jsonb DEFAULT '{}'::jsonb
    );
    CREATE INDEX IF NOT EXISTS brain_memory_city_severity_idx
      ON brain_memory (city, severity);
    CREATE INDEX IF NOT EXISTS brain_memory_outcome_idx
      ON brain_memory (outcome) WHERE outcome IS NOT NULL;

    -- The pgvector ANN index for fast similarity search
    CREATE INDEX IF NOT EXISTS brain_memory_embedding_idx
      ON brain_memory USING ivfflat (embedding vector_cosine_ops)
      WITH (lists = 100);


WIRE-UP IN hub.py
─────────────────
    from empire_brain_memory import BrainMemory, render_few_shot

    brain_memory = BrainMemory(
        get_db=         get_db,
        openai_key=     os.environ.get("OPENAI_API_KEY", ""),
        embedding_model="text-embedding-3-small",
    )

    # In the brain evaluation path, BEFORE calling Claude:
    similar = await brain_memory.retrieve_similar(
        address=p["address"],
        city=p["city"],
        severity=severity,
        asset_value=asset_val_num,
        urgency_signal=alert.get("event", ""),
        k=5,
    )
    few_shot_block = render_few_shot(similar)

    # Inject few_shot_block into the brain prompt
    brain_prompt = build_brain_prompt(
        target=p,
        alert=alert,
        memory_context=few_shot_block,  # NEW
    )

    # AFTER Claude returns a decision, record it:
    memory_id = await brain_memory.record_decision(
        lead_id=p.get("id"),
        decision=analysis["decision"],
        urgency=analysis.get("urgency", 0),
        reasoning=analysis.get("reasoning", ""),
        address=p["address"],
        city=p["city"],
        severity=severity,
        asset_value=asset_val_num,
    )

    # In record_outcome, link the outcome back to brain_memory:
    await brain_memory.attach_outcome(
        lead_id=outcome["lead_id"],
        outcome=outcome["outcome"],
        actual_fee=outcome.get("actual_fee", 0),
    )
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional

import httpx


log = logging.getLogger("empire.brain.memory")


EMBEDDING_DIM_DEFAULT = 1536  # text-embedding-3-small


class BrainMemory:
    """Manages embedding storage + retrieval for brain decisions."""

    def __init__(
        self,
        *,
        get_db: Callable,
        openai_key: str = "",
        embedding_model: str = "text-embedding-3-small",
    ):
        self.get_db          = get_db
        self.openai_key      = openai_key
        self.embedding_model = embedding_model
        self.enabled         = bool(openai_key)
        self.stats = {
            "decisions_recorded":   0,
            "outcomes_attached":    0,
            "retrievals_done":      0,
            "embeddings_generated": 0,
            "last_error":           None,
        }
        if not self.enabled:
            log.warning("[brain.memory] OPENAI_API_KEY not set · running in NOOP mode")

    # ── RECORD A DECISION ───────────────────────────────────────────────
    async def record_decision(
        self,
        *,
        lead_id: str,
        decision: str,
        urgency: int,
        reasoning: str,
        address: str,
        city: str,
        severity: str,
        asset_value: float,
    ) -> Optional[str]:
        """Insert a brain_memory row with embedding. Returns memory_id."""
        if not self.enabled:
            return None

        # Build the human-readable summary that gets embedded
        context_text = self._build_context_text(
            address=address,
            city=city,
            severity=severity,
            asset_value=asset_value,
            urgency=urgency,
        )

        # Generate the embedding
        embedding = await self._embed(context_text)
        if embedding is None:
            log.warning("[brain.memory] embedding failed · skipping record")
            return None

        try:
            db = self.get_db()
            ins = db.table("brain_memory").insert({
                "lead_id":      lead_id,
                "decision":     decision,
                "urgency":      urgency,
                "reasoning":    reasoning[:1000] if reasoning else None,
                "context_text": context_text[:2000],
                "embedding":    embedding,
                "asset_value":  asset_value,
                "severity":     severity,
                "city":         city,
            }).execute()
            self.stats["decisions_recorded"] += 1
            return ins.data[0]["id"] if ins.data else None
        except Exception as e:
            log.error(f"[brain.memory] record failed: {e}")
            self.stats["last_error"] = str(e)
            return None

    # ── ATTACH AN OUTCOME ────────────────────────────────────────────────
    async def attach_outcome(
        self,
        *,
        lead_id: str,
        outcome: str,
        actual_fee: float = 0,
    ) -> bool:
        """When a claim resolves, attach the outcome to the matching memory row."""
        if not lead_id:
            return False
        try:
            db = self.get_db()
            db.table("brain_memory").update({
                "outcome":    outcome,
                "actual_fee": actual_fee,
            }).eq("lead_id", lead_id).execute()
            self.stats["outcomes_attached"] += 1
            return True
        except Exception as e:
            log.error(f"[brain.memory] attach_outcome failed: {e}")
            return False

    # ── RETRIEVE SIMILAR PAST LEADS ──────────────────────────────────────
    async def retrieve_similar(
        self,
        *,
        address: str,
        city: str,
        severity: str,
        asset_value: float,
        urgency_signal: str = "",
        k: int = 5,
        only_with_outcomes: bool = True,
    ) -> list[dict]:
        """
        Find the k most similar past leads. Returns the memory rows with
        their decisions and outcomes attached.
        """
        if not self.enabled:
            return []

        # Build query embedding
        query_text = self._build_context_text(
            address=address,
            city=city,
            severity=severity,
            asset_value=asset_value,
            urgency=0,
        )
        if urgency_signal:
            query_text += f" event: {urgency_signal}"

        embedding = await self._embed(query_text)
        if embedding is None:
            return []

        try:
            db = self.get_db()
            # pgvector cosine similarity search via Supabase RPC
            # NOTE: this requires a database function. SQL provided below.
            rpc_payload = {
                "query_embedding":  embedding,
                "match_count":      k * 2,  # over-fetch then filter
            }
            res = db.rpc("match_brain_memory", rpc_payload).execute()
            rows = res.data or []

            # Filter to only memories with outcomes (more useful for learning)
            if only_with_outcomes:
                rows = [r for r in rows if r.get("outcome") and r["outcome"] != "pending"]

            self.stats["retrievals_done"] += 1
            return rows[:k]
        except Exception as e:
            log.debug(f"[brain.memory] similarity search failed (RPC may not be installed): {e}")
            # Fallback: pull recent memories of same city + severity
            return await self._retrieve_fallback(
                city=city,
                severity=severity,
                k=k,
                only_with_outcomes=only_with_outcomes,
            )

    async def _retrieve_fallback(
        self,
        city: str,
        severity: str,
        k: int = 5,
        only_with_outcomes: bool = True,
    ) -> list[dict]:
        """No-pgvector fallback · just recent rows of similar city/severity."""
        try:
            db = self.get_db()
            q = db.table("brain_memory").select("*") \
                .eq("city", city) \
                .eq("severity", severity) \
                .order("created_at", desc=True).limit(k * 2)
            if only_with_outcomes:
                q = q.not_.is_("outcome", "null").neq("outcome", "pending")
            return (q.execute().data or [])[:k]
        except Exception as e:
            log.debug(f"[brain.memory] fallback retrieval failed: {e}")
            return []

    # ── EMBEDDING GENERATION ─────────────────────────────────────────────
    async def _embed(self, text: str) -> Optional[list[float]]:
        """Generate an embedding vector via OpenAI."""
        if not self.enabled:
            return None
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={
                        "Authorization": f"Bearer {self.openai_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.embedding_model,
                        "input": text[:8000],
                    },
                )
                if r.status_code != 200:
                    log.warning(f"[brain.memory] embedding HTTP {r.status_code}: {r.text[:200]}")
                    return None
                data = r.json()
                self.stats["embeddings_generated"] += 1
                return data["data"][0]["embedding"]
        except Exception as e:
            log.error(f"[brain.memory] embedding error: {e}")
            return None

    def _build_context_text(
        self,
        address: str,
        city: str,
        severity: str,
        asset_value: float,
        urgency: int,
    ) -> str:
        """Build the human-readable context string used for embedding."""
        # Bucket asset value to reduce noise (small variations shouldn't move
        # the embedding much)
        if asset_value <= 0:
            asset_band = "unknown value"
        elif asset_value < 500_000:
            asset_band = "sub-500K"
        elif asset_value < 1_000_000:
            asset_band = "mid-six-figure"
        elif asset_value < 5_000_000:
            asset_band = "low-million"
        elif asset_value < 25_000_000:
            asset_band = "mid-million"
        else:
            asset_band = "large-asset"

        urg_band = "low-urgency" if urgency < 5 else ("mid-urgency" if urgency < 8 else "high-urgency")

        return (
            f"property: {address[:120]} in {city}. "
            f"damage severity: {severity}. "
            f"asset class: {asset_band}. "
            f"signal: {urg_band}."
        )


# ─────────────────────────────────────────────────────────────────────────────
# FEW-SHOT RENDERING — turns retrieved memories into brain-prompt context
# ─────────────────────────────────────────────────────────────────────────────
def render_few_shot(memories: list[dict]) -> str:
    """
    Returns a string block to inject into the brain prompt.
    Empty string if no memories.
    """
    if not memories:
        return ""

    lines = ["", "PAST SIMILAR LEADS (for calibration · learn from these):"]
    for i, m in enumerate(memories, 1):
        context = m.get("context_text", "")[:160]
        decision = m.get("decision", "?")
        urgency  = m.get("urgency", "?")
        outcome  = m.get("outcome") or "no outcome yet"
        fee      = m.get("actual_fee") or 0
        fee_str  = f" · ${fee:,.0f} fee" if fee > 0 else ""

        lines.append(
            f"  {i}. {context}\n"
            f"     → brain said: {decision} (urgency {urgency}/10)\n"
            f"     → actual outcome: {outcome}{fee_str}"
        )

    lines.append("")
    lines.append(
        "Use the pattern of those past outcomes to calibrate this new decision. "
        "If similar leads have repeatedly NO_GO'd, weight conservatism. "
        "If similar leads have repeatedly settled high, lean GO with confidence."
    )
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# SUPABASE RPC · install this once via SQL editor to enable fast similarity search
# ─────────────────────────────────────────────────────────────────────────────
MATCH_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION match_brain_memory(
  query_embedding vector(1536),
  match_count int
)
RETURNS TABLE (
  id uuid,
  context_text text,
  decision text,
  urgency int,
  reasoning text,
  city text,
  severity text,
  asset_value numeric,
  outcome text,
  actual_fee numeric,
  similarity float
)
LANGUAGE sql STABLE AS $$
  SELECT
    bm.id,
    bm.context_text,
    bm.decision,
    bm.urgency,
    bm.reasoning,
    bm.city,
    bm.severity,
    bm.asset_value,
    bm.outcome,
    bm.actual_fee,
    1 - (bm.embedding <=> query_embedding) as similarity
  FROM brain_memory bm
  WHERE bm.embedding IS NOT NULL
  ORDER BY bm.embedding <=> query_embedding
  LIMIT match_count;
$$;
"""
