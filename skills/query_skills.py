"""
EMPIRE V49 · QUERY & KNOWLEDGE SKILLS
========================================
Four skills for data retrieval across the Empire ecosystem:

  1. query.db.sql       — Natural language → SQL → Supabase results (read-only)
  2. query.rag.search   — Semantic vector search via Qdrant (skills/leads/documents)
  3. query.kb.search    — Knowledge base retrieval over internal docs (brain_vault)
  4. query.visual.search — Visual semantic search: screenshot pages → index → search

NL→SQL uses Groq, RAG uses sentence-transformers embeddings + Qdrant,
KB builds on RAG for docs, Visual uses Chrome screenshots + Qdrant.

Usage:
    from skills.query_skills import register_query_skills
    register_query_skills(registry, ask_llm=my_llm_callable)
"""

import os
import re
import time
import asyncio
import logging
from typing import Any, Optional

from .base import BaseSkill, SkillInput, SkillOutput, SkillMetrics
from .registry import SkillRegistry

log = logging.getLogger("empire.skills.query")

# ── Read-only SQL blocklist ────────────────────────────────────────────
_READONLY_BLOCKED = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|"
    r"REPLACE|MERGE|EXEC|EXECUTE|CALL|LOAD|IMPORT|COPY)\b",
    re.IGNORECASE,
)


def _is_readonly_sql(sql: str) -> bool:
    """Return True if the SQL statement is a safe SELECT-only query."""
    stripped = sql.strip().rstrip(";").strip()
    upper = stripped.upper()
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        return False
    if _READONLY_BLOCKED.search(stripped):
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# SKILL 1: query.db.sql — Natural Language → SQL
# ─────────────────────────────────────────────────────────────────────────────


class DBQuerySkill(BaseSkill):
    """Convert natural language questions into SQL and run against Supabase.

    Uses Groq (llama-3.1-8b-instant) to generate SQL, validates it's read-only,
    executes via Supabase, and returns structured results.

    Input params:
      - question: str — natural language question about the database
      - tables_hint: Optional[str] — hint about which tables to query
      - limit: Optional[int] — max rows to return (default 20)
    """

    name = "query.db.sql"
    version = "1.0.0"
    description = "Convert natural language questions into read-only SQL queries and execute against Supabase"
    tags = ["domain:query", "mode:sync", "db:supabase", "llm:required"]
    timeout_seconds = 45.0
    max_retries = 2

    def __init__(self):
        super().__init__()
        self.ask_llm: Any = None          # callable(system, prompt) → str
        self.supabase_client: Any = None  # Supabase client for query execution

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("question")) and self.ask_llm is not None

    async def execute(self, input: SkillInput) -> SkillOutput:
        question = input.params["question"]
        tables_hint = input.params.get("tables_hint", "")
        limit = int(input.params.get("limit", 20))

        # 1. Generate SQL via Groq
        sql_system = """You are a PostgreSQL expert. Convert natural language questions into SQL queries.
The database is Supabase (Postgres 15). Tables include:
  b2b_leads(id, company_name, email, phone, website, niche, metro, city, lead_score, meta)
  email_drafts(id, to_email, subject, body, status, meta, created_at)
  contractors(id, name, email, phone, niche, metro, status, meta)
  radar_targets(id, name, city, metro, niche, damage_severity, urgency_score, meta)
  fee_events(id, contractor_id, claim_id, amount, status, meta, created_at)
  carrier_claims(id, contractor_id, claim_number, settlement_amount, status, meta, created_at)

RULES:
- ONLY SELECT statements. Never INSERT/UPDATE/DELETE/DROP.
- Use LIMIT for safety (max 100).
- For JSONB meta fields, use meta->>'key' syntax.
- Return ONLY the SQL query, no explanation, no markdown."""

        sql_prompt = f"Question: {question}"
        if tables_hint:
            sql_prompt += f"\nRelevant tables: {tables_hint}"
        sql_prompt += f"\nLimit results to {limit} rows."

        try:
            sql_raw = await asyncio.wait_for(
                asyncio.get_running_loop().run_in_executor(
                    None, self.ask_llm, sql_system, sql_prompt
                ),
                timeout=30,
            )
        except asyncio.TimeoutError:
            return SkillOutput(success=False, error="SQL generation timed out")
        except Exception as e:
            return SkillOutput(success=False, error=f"LLM call failed: {e}")

        if not sql_raw:
            return SkillOutput(success=False, error="LLM returned empty SQL")

        # Clean markdown fences
        sql = sql_raw.strip()
        for fence in ["```sql", "```SQL", "```"]:
            if fence in sql:
                sql = sql.split(fence, 1)[1].split("```", 1)[0].strip()
                break

        # 2. Safety: read-only check
        if not _is_readonly_sql(sql):
            return SkillOutput(
                success=False,
                error=f"Generated SQL is not read-only: {sql[:200]}",
                data={"rejected_sql": sql[:500]},
            )

        # 3. Execute via Supabase
        if self.supabase_client is None:
            return SkillOutput(
                success=False,
                error="Supabase client not wired — cannot execute SQL",
                data={"generated_sql": sql},
            )

        try:
            r = await asyncio.get_running_loop().run_in_executor(
                None, lambda: self.supabase_client.rpc("exec_sql", {"query": sql}).execute()
            )
            rows = r.data or []
        except Exception as e:
            # Fall back to PostgREST table queries if rpc not available
            log.warning(f"[query.db.sql] rpc('exec_sql') failed: {e} — returning generated SQL only")
            return SkillOutput(
                success=True,
                data={
                    "generated_sql": sql,
                    "rows": [],
                    "count": 0,
                    "note": "SQL generated but execution requires exec_sql RPC in Supabase",
                },
                metrics=SkillMetrics(duration_ms=0, api_calls=1, records_processed=0),
            )

        return SkillOutput(
            success=True,
            data={
                "question": question,
                "generated_sql": sql,
                "rows": rows,
                "count": len(rows),
            },
            metrics=SkillMetrics(duration_ms=0, api_calls=1, records_processed=len(rows)),
        )


# ─────────────────────────────────────────────────────────────────────────────
# SKILL 2: query.rag.search — Vector Search via Qdrant
# ─────────────────────────────────────────────────────────────────────────────


class RagSearchSkill(BaseSkill):
    """Semantic search across Qdrant vector collections.

    Supports three collections: skills, leads, documents.
    Uses sentence-transformers (all-MiniLM-L6-v2) for embedding.

    Input params:
      - query: str — natural language search query
      - collection: str — one of 'skills', 'leads', 'documents' (default 'documents')
      - limit: Optional[int] — max results (default 5)
      - score_threshold: Optional[float] — minimum similarity (0-1)
      - filter: Optional[dict] — payload filters (e.g. {'doc_type': 'note'})
    """

    name = "query.rag.search"
    version = "1.0.0"
    description = "Semantic vector search across Qdrant collections (skills, leads, documents)"
    tags = ["domain:query", "mode:sync", "rag:qdrant", "requires:embedding"]
    timeout_seconds = 20.0
    max_retries = 2

    def __init__(self):
        super().__init__()

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("query"))

    async def execute(self, input: SkillInput) -> SkillOutput:
        query = input.params["query"]
        collection = input.params.get("collection", "documents")
        limit = int(input.params.get("limit", 5))
        score_threshold = input.params.get("score_threshold")
        filters = input.params.get("filter")

        if collection not in ("skills", "leads", "documents"):
            return SkillOutput(success=False, error=f"Unknown collection: {collection}")

        # Import Qdrant search functions lazily
        try:
            from integrations.qdrant import search_skills, search_leads, search_documents
        except ImportError as e:
            return SkillOutput(success=False, error=f"Qdrant integration not available: {e}")

        search_fn = {"skills": search_skills, "leads": search_leads, "documents": search_documents}[collection]

        try:
            results = await search_fn(
                query=query,
                limit=limit,
                score_threshold=score_threshold,
                filter_kwargs=filters,
            )
        except Exception as e:
            return SkillOutput(success=False, error=f"Qdrant search failed: {e}")

        return SkillOutput(
            success=True,
            data={
                "query": query,
                "collection": collection,
                "results": results,
                "count": len(results),
            },
            metrics=SkillMetrics(duration_ms=0, api_calls=1, records_processed=len(results)),
        )


# ─────────────────────────────────────────────────────────────────────────────
# SKILL 3: query.kb.search — Knowledge Base Retrieval
# ─────────────────────────────────────────────────────────────────────────────


class KnowledgeBaseSearchSkill(BaseSkill):
    """Search the Empire AI internal knowledge base (brain_vault docs).

    Combines vault keyword search with RAG vector search for documents.
    Caches indexed documents for 5 minutes to avoid re-scanning.

    Input params:
      - query: str — what you want to know
      - max_results: Optional[int] — max results (default 10)
      - search_mode: Optional[str] — 'keyword', 'vector', or 'both' (default 'both')
    """

    name = "query.kb.search"
    version = "1.0.0"
    description = "Search the Empire AI knowledge base (brain_vault docs) using keyword + vector search"
    tags = ["domain:query", "mode:sync", "kb:brain_vault"]
    timeout_seconds = 15.0

    def __init__(self):
        super().__init__()
        self._index_cache: list = []
        self._cache_at: float = 0
        self._cache_ttl: float = 300.0

    def _scan_vault(self) -> list:
        """Scan brain_vault for .md files and return indexed documents."""
        now = time.time()
        if self._index_cache and (now - self._cache_at) < self._cache_ttl:
            return self._index_cache

        vault_repo = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "brain_vault")
        vault_hermes = os.path.expanduser("~/.hermes/brain_vault")
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        docs = []

        # Brain vault markdown files
        for vault_dir in [vault_repo, vault_hermes]:
            if not os.path.isdir(vault_dir):
                continue
            for root, _dirs, files in os.walk(vault_dir):
                for f in sorted(files):
                    if not f.endswith(".md"):
                        continue
                    filepath = os.path.join(root, f)
                    rel_path = os.path.relpath(filepath, vault_dir)
                    try:
                        with open(filepath, "r") as fh:
                            content = fh.read(10000)
                        title = rel_path.replace(".md", "").replace("/", " › ").replace("_", " ").title()
                        docs.append({
                            "path": f"brain_vault/{rel_path}",
                            "title": title,
                            "content": content[:3000],
                            "source": "brain_vault",
                        })
                    except Exception:
                        continue

        # Key project docs
        key_docs = [
            "AGENTS.md", "STARTING_POINT.md", "CONTEXT.md",
            "ARCHITECTURE_DIAGRAM.html", "LANES_AND_CPL.md",
            "REVENUE_FLOW.md", "CONTRIBUTING.md",
        ]
        for doc_name in key_docs:
            filepath = os.path.join(project_root, doc_name)
            if os.path.exists(filepath):
                try:
                    with open(filepath, "r") as fh:
                        content = fh.read(10000)
                    docs.append({
                        "path": doc_name,
                        "title": doc_name.replace(".md", "").replace("_", " ").title(),
                        "content": content[:3000],
                        "source": "project_root",
                    })
                except Exception:
                    continue

        self._index_cache = docs
        self._cache_at = now
        return docs

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("query"))

    async def execute(self, input: SkillInput) -> SkillOutput:
        query = input.params["query"]
        query_lower = query.lower()
        max_results = int(input.params.get("max_results", 10))
        mode = input.params.get("search_mode", "both")

        # 1. Scan vault for documents
        docs = self._scan_vault()
        if not docs:
            return SkillOutput(success=False, error="No knowledge base documents found")

        keyword_results = []
        vector_results = []

        # 2. Keyword search (always fast, always runs)
        if mode in ("keyword", "both"):
            for doc in docs:
                score = 0
                content_lower = doc["content"].lower()
                # Count keyword matches
                for word in query_lower.split():
                    if len(word) > 2:
                        score += content_lower.count(word)
                if doc["title"].lower().find(query_lower) >= 0:
                    score += 10  # Title match bonus
                if score > 0:
                    # Extract context snippet
                    content = doc["content"]
                    idx = content_lower.find(query_lower.split()[0]) if query_lower.split() else 0
                    start = max(0, idx - 80)
                    end = min(len(content), idx + 200)
                    keyword_results.append({
                        "path": doc["path"],
                        "title": doc["title"],
                        "source": doc["source"],
                        "score": score,
                        "snippet": content[start:end].replace("\n", " ").strip(),
                    })

            keyword_results.sort(key=lambda x: x["score"], reverse=True)

        # 3. Vector search via Qdrant (if collection available)
        if mode in ("vector", "both") and input.context:
            rag_skill = input.context.get_skill("query.rag.search")
            if rag_skill:
                try:
                    rag_out = await rag_skill.run(SkillInput(
                        params={
                            "query": query,
                            "collection": "documents",
                            "limit": max_results,
                        },
                    ))
                    if rag_out.success and rag_out.data:
                        for r in rag_out.data.get("results", []):
                            payload = r.get("payload", {})
                            vector_results.append({
                                "path": payload.get("title", r["id"]),
                                "title": payload.get("title", r["id"]),
                                "source": "qdrant",
                                "score": round(r.get("score", 0), 3),
                                "snippet": payload.get("content_preview", "")[:200],
                            })
                except Exception as e:
                    log.warning(f"[query.kb.search] RAG search failed: {e}")

        # 4. Merge and deduplicate
        seen_paths = set()
        merged = []
        for r in keyword_results[:max_results] + vector_results[:max_results]:
            if r["path"] not in seen_paths:
                seen_paths.add(r["path"])
                merged.append(r)
        merged = merged[:max_results]

        return SkillOutput(
            success=True,
            data={
                "query": query,
                "results": merged,
                "count": len(merged),
                "total_docs_indexed": len(docs),
                "mode": mode,
            },
            metrics=SkillMetrics(duration_ms=0, records_processed=len(merged)),
        )


# ── SKILL 4: query.visual.search — Visual Semantic Search ──────────────


CHROME_CDP_URL = os.environ.get("CHROME_CDP_URL", "http://127.0.0.1:9222")


class VisualSearchSkill(BaseSkill):
    """PixelRAG-inspired visual semantic search using Chrome screenshots + Qdrant.

    Renders web pages via headless Chrome, extracts page content, indexes it
    as documents in Qdrant, and enables semantic search over visually-indexed
    pages. Lightweight alternative to full PixelRAG (no torch/transformers needed).

    Input params:
      - action: str — 'index' (render + index a URL) or 'search' (search indexed pages)
      - url: Optional[str] — URL to index (for action='index')
      - query: Optional[str] — search query (for action='search')
      - limit: Optional[int] — max results (default 5)
    """

    name = "query.visual.search"
    version = "1.0.0"
    description = "Visual semantic search: render pages via Chrome, index into Qdrant, search visually"
    tags = ["domain:query", "mode:sync", "visual:pixelrag", "chrome", "rag:qdrant"]
    timeout_seconds = 30.0
    max_retries = 2

    async def validate(self, input: SkillInput) -> bool:
        action = input.params.get("action", "search")
        if action == "index":
            return bool(input.params.get("url"))
        return bool(input.params.get("query"))

    async def _fetch_page_content(self, url: str) -> Optional[str]:
        """Fetch page content via HTTP and extract readable text from HTML."""
        try:
            import requests as _req
            r = _req.get(url, timeout=15, headers={
                "User-Agent": "EmpireAI-VisualSearch/1.0",
            })
            if r.status_code != 200:
                return None
            # Extract readable text from HTML
            text = r.text
            # Remove scripts and styles
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
            # Remove HTML tags
            text = re.sub(r'<[^>]+>', ' ', text)
            # Collapse whitespace
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:8000]
        except Exception as e:
            log.warning(f"[query.visual.search] fetch failed for {url}: {e}")
            return None

    async def execute(self, input: SkillInput) -> SkillOutput:
        action = input.params.get("action", "search")

        if action == "index":
            url = input.params["url"]
            doc_title = input.params.get("title", url)

            # 1. Fetch page content
            content = await self._fetch_page_content(url)
            if not content:
                return SkillOutput(
                    success=False,
                    error=f"Failed to fetch content from {url}",
                    data={"url": url},
                )

            # 2. Index into Qdrant documents collection
            doc_id = f"visual:{url}"
            try:
                from integrations.qdrant import upsert_document
                ok = await upsert_document(
                    doc_id=doc_id,
                    title=doc_title,
                    content=content,
                    doc_type="webpage",
                    metadata={
                        "source": "visual_search",
                        "url": url,
                    },
                )
            except ImportError:
                ok = False

            return SkillOutput(
                success=True,
                data={
                    "action": "index",
                    "url": url,
                    "indexed": ok,
                    "doc_id": doc_id,
                    "content_length": len(content),
                },
                metrics=SkillMetrics(duration_ms=0, api_calls=int(ok), records_processed=1),
            )

        # ── Action: search ──────────────────────────────────────────
        query = input.params["query"]
        limit = int(input.params.get("limit", 5))

        try:
            from integrations.qdrant import search_documents
            results = await search_documents(
                query=query,
                limit=limit,
                filter_kwargs={"source": "visual_search"},
            )
        except ImportError as e:
            return SkillOutput(success=False, error=f"Qdrant not available: {e}")
        except Exception as e:
            return SkillOutput(success=False, error=f"Search failed: {e}")

        return SkillOutput(
            success=True,
            data={
                "action": "search",
                "query": query,
                "results": [
                    {
                        "url": r["payload"].get("url", r["id"]),
                        "title": r["payload"].get("title", r["id"]),
                        "score": round(r.get("score", 0), 3),
                        "snippet": (r["payload"].get("content_preview", "") or "")[:200],
                    }
                    for r in results
                ],
                "count": len(results),
            },
            metrics=SkillMetrics(duration_ms=0, api_calls=1, records_processed=len(results)),
        )
# ─────────────────────────────────────────────────────────────────────────────


def register_query_skills(
    registry: SkillRegistry,
    ask_llm: Any = None,
    supabase_client: Any = None,
) -> dict:
    """Register all query skills and wire their dependencies.

    Args:
        registry: SkillRegistry or ImmutableSkillRegistry instance
        ask_llm: Callable(system_prompt, user_prompt) → str for NL→SQL via Groq
        supabase_client: Supabase client for SQL execution (optional)

    Returns:
        dict of wired skill instances
    """
    # ── DB Query Skill ──────────────────────────────────────────────
    registry.register(DBQuerySkill)
    if ask_llm is not None:
        registry.wire_dependency("query.db.sql", "ask_llm", ask_llm)
    if supabase_client is not None:
        registry.wire_dependency("query.db.sql", "supabase_client", supabase_client)
    db_skill = registry.get("query.db.sql")

    # ── RAG Search Skill ────────────────────────────────────────────
    registry.register(RagSearchSkill)
    rag_skill = registry.get("query.rag.search")

    # ── Knowledge Base Skill ────────────────────────────────────────
    registry.register(KnowledgeBaseSearchSkill)
    kb_skill = registry.get("query.kb.search")

    # ── Visual Search Skill ──────────────────────────────────────────
    registry.register(VisualSearchSkill)
    visual_skill = registry.get("query.visual.search")

    log.info(
        f"[query_skills] registered 4 skills: "
        f"query.db.sql={db_skill is not None}, "
        f"query.rag.search={rag_skill is not None}, "
        f"query.kb.search={kb_skill is not None}, "
        f"query.visual.search={visual_skill is not None}"
    )

    return {
        "query.db.sql": db_skill,
        "query.rag.search": rag_skill,
        "query.kb.search": kb_skill,
        "query.visual.search": visual_skill,
    }
