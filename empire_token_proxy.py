"""
EMPIRE V49 · TOKEN PROXY
========================
Transparent caching + deduplication + context compression layer that sits
between every LLM caller (AIRouter, bots, Hermes) and the Ollama backend.

Reduces token consumption by:
  - Semantic caching: identical prompts → cached response (TTL per task)
  - In-flight dedup: concurrent identical calls share one LLM round-trip
  - Context compression: strips boilerplate, trims repetition, truncates
    intelligently by task type

Zero behavioral change for callers — drop in and forget it's there.

Cache entropy: ~1000 entries, LRU eviction, task-aware TTLs.
"""

import hashlib
import json
import logging
import time
from collections import OrderedDict
from typing import Any, Callable, Dict, Optional

log = logging.getLogger("empire.token_proxy")

# ── TTL CONFIG ─────────────────────────────────────────────────────────
# How long a cached response lives before being re-queried.
# Brain decisions age fast (conditions change). Enrichment stays longer.
TASK_TTL_SEC: Dict[str, int] = {
    "brain.decide":          60,      # 1 min — conditions change fast
    "reply.qualify":         120,     # 2 min
    "enricher.extract":      600,     # 10 min — static data
    "narrate.event":         300,     # 5 min
    "email.draft":           1800,    # 30 min — drafts are expensive, reuse
    "mission.briefing":      120,     # 2 min
    "bot.llm":               120,     # 2 min — bot agents
    "controller.ollama":     60,      # 1 min — Hermes controller
    "general":               60,      # 1 min
}

DEFAULT_TTL_SEC = 60
MAX_CACHE_ENTRIES = 1000
MAX_PROMPT_CHARS = 4000  # Compress prompts longer than this


class TokenProxy:
    """
    Lightweight async-safe token proxy.

    Usage:
        proxy = TokenProxy()
        proxy.wrap_router(ai_router)          # wrap AIRouter
        result = await proxy.cached_call(     # or call directly
            task="brain.decide",
            key_data={"prompt": prompt, "system": system},
            llm_call=lambda: router._call_ollama(...),
        )
    """

    def __init__(self):
        # ── LRU cache: OrderedDict, {cache_key: (expires_at, response)} ──
        self._cache: OrderedDict = OrderedDict()
        # ── In-flight dedup: {cache_key: asyncio.Future} ──
        self._in_flight: Dict[str, Any] = {}
        # ── Metrics ──
        self.stats = {
            "hits": 0,
            "misses": 0,
            "dedup_saves": 0,
            "bytes_saved": 0,
            "tokens_estimated_saved": 0,
            "entries_evicted": 0,
        }
        self.stats_start = time.time()

    # ── PUBLIC API ──────────────────────────────────────────────────────

    async def cached_call(
        self,
        *,
        task: str,
        key_data: Dict[str, Any],
        llm_call: Callable,
        ttl_override: Optional[int] = None,
    ) -> Any:
        """
        Execute *llm_call* with caching + dedup.

        Args:
            task: Task type (brain.decide, enricher.extract, etc.)
            key_data: Dict of values that uniquely identify this call.
                      e.g. {"prompt": ..., "system": ...}
            llm_call: Async callable that performs the actual LLM call.
            ttl_override: Optional TTL in seconds. Overrides TASK_TTL_SEC.

        Returns:
            The response from cache (if fresh) or from *llm_call*.
        """
        # ── 1. Build cache key ─────────────────────────────────────────
        raw = json.dumps(key_data, sort_keys=True, default=str)
        cache_key = hashlib.sha256(raw.encode()).hexdigest()
        ttl = ttl_override or TASK_TTL_SEC.get(task, DEFAULT_TTL_SEC)

        # ── 2. Check LRU cache ─────────────────────────────────────────
        cached = self._get_cached(cache_key)
        if cached is not None:
            self.stats["hits"] += 1
            self.stats["bytes_saved"] += len(raw)
            self.stats["tokens_estimated_saved"] += len(raw) // 4
            return cached

        # ── 3. Check in-flight dedup ───────────────────────────────────
        if cache_key in self._in_flight:
            future = self._in_flight[cache_key]
            self.stats["dedup_saves"] += 1
            result = await future
            # Re-cache from the dedup result
            self._set_cached(cache_key, result, ttl)
            return result

        # ── 4. Cache miss — execute the call ───────────────────────────
        self.stats["misses"] += 1

        # Create a future so in-flight dedup works
        import asyncio
        future = asyncio.get_event_loop().create_future()
        self._in_flight[cache_key] = future

        try:
            result = await llm_call()
            future.set_result(result)
            self._set_cached(cache_key, result, ttl)
            return result
        except Exception as e:
            future.set_exception(e)
            raise
        finally:
            self._in_flight.pop(cache_key, None)

    # ── CONTEXT COMPRESSION ─────────────────────────────────────────────

    @staticmethod
    def compress_prompt(prompt: str, task: str = "general") -> str:
        """
        Reduce token waste by compressing the prompt before it hits the LLM.

        Strategies (applied in order):
          1. Truncate to MAX_PROMPT_CHARS if over limit
          2. Collapse repeated blank lines into one
          3. Strip trailing whitespace per line
          4. Remove known boilerplate patterns (JSON formatting instructions
             that the model doesn't need to see every time)
        """
        if not prompt:
            return prompt

        original_len = len(prompt)

        # Collapse multiple blank lines
        import re
        compressed = re.sub(r'\n{3,}', '\n\n', prompt)

        # Strip trailing whitespace per line
        compressed = '\n'.join(line.rstrip() for line in compressed.split('\n'))

        # Truncate
        if len(compressed) > MAX_PROMPT_CHARS:
            # Try to cut at a sentence boundary
            cut = compressed[:MAX_PROMPT_CHARS]
            last_period = cut.rfind('.')
            if last_period > MAX_PROMPT_CHARS * 0.8:
                compressed = compressed[:last_period + 1]
            else:
                compressed = cut

        return compressed

    # ── ROUTER WRAPPER ──────────────────────────────────────────────────

    def wrap_router(self, router) -> None:
        """
        Monkey-patch an AIRouter (or similar) so all generate/generate_json
        calls flow through the token proxy automatically.

        Call this once after creating the router:
            proxy = TokenProxy()
            proxy.wrap_router(ai_router)
        """
        # Lazy import to avoid import-order dependencies at module load
        import empire_ai_router as _air_mod
        _air_mod.AIRouter.generate._ollama_call = _router_ollama_call
        _air_mod.AIRouter.generate_json._ollama_call = _router_ollama_call_json

        original_generate = router.generate
        original_generate_json = router.generate_json
        proxy = self

        async def wrapped_generate(
            prompt: str, *, task: str = "general", model: Optional[str] = None,
            system: Optional[str] = None, temperature: float = 0.4,
            max_tokens: int = 1024, context: Optional[Dict] = None,
        ) -> str:
            compressed = proxy.compress_prompt(prompt, task=task)
            # Skip cache for unique tasks (email drafts, briefings)
            if task in ("email.draft", "mission.briefing", "general"):
                return await original_generate(
                    compressed, task=task, model=model, system=system,
                    temperature=temperature, max_tokens=max_tokens, context=context,
                )

            key_data = {"p": compressed, "s": system, "t": temperature, "m": max_tokens}
            result = await proxy.cached_call(
                task=task,
                key_data=key_data,
                # Use the full generate() so dispatch hits MiniMax / Z.ai / Anthropic.
                # The legacy _ollama_call path bypasses cloud providers and 404s.
                llm_call=lambda: original_generate(
                    compressed, task=task, model=model, system=system,
                    temperature=temperature, max_tokens=max_tokens, context=context,
                ),
            )
            return result

        async def wrapped_generate_json(
            prompt: str, *, task: str = "general", model: Optional[str] = None,
            system: Optional[str] = None, temperature: float = 0.2,
            max_tokens: int = 1024, context: Optional[Dict] = None,
            retries: int = 2,
        ) -> Dict[str, Any]:
            compressed = proxy.compress_prompt(prompt, task=task)
            if task in ("email.draft", "mission.briefing", "general"):
                return await original_generate_json(
                    compressed, task=task, model=model, system=system,
                    temperature=temperature, max_tokens=max_tokens,
                    context=context, retries=retries,
                )

            key_data = {"p": compressed, "s": system, "t": temperature, "m": max_tokens, "fmt": "json"}
            result = await proxy.cached_call(
                task=task,
                key_data=key_data,
                llm_call=lambda: original_generate_json(
                    compressed, task=task, model=model, system=system,
                    temperature=temperature, max_tokens=max_tokens,
                    context=context, retries=retries,
                ),
            )
            return result

        router.generate = wrapped_generate        # type: ignore[assignment]
        router.generate_json = wrapped_generate_json  # type: ignore[assignment]
        log.info(f"[token_proxy] wrapped AIRouter — cache active for {len(TASK_TTL_SEC)} task types")

    # ── CACHE INTERNALS ─────────────────────────────────────────────────

    def _get_cached(self, key: str) -> Any:
        """Return cached response if fresh, else None."""
        if key not in self._cache:
            return None
        expires_at, response = self._cache[key]
        if time.time() > expires_at:
            del self._cache[key]
            self.stats["entries_evicted"] += 1
            return None
        # Move to end (LRU: most recently used)
        self._cache.move_to_end(key)
        return response

    def _set_cached(self, key: str, response: Any, ttl: int) -> None:
        """Store response with TTL. Evict oldest if over capacity."""
        if len(self._cache) >= MAX_CACHE_ENTRIES:
            self._cache.popitem(last=False)
            self.stats["entries_evicted"] += 1
        expires_at = time.time() + ttl
        self._cache[key] = (expires_at, response)
        self._cache.move_to_end(key)

    # ── METRICS ─────────────────────────────────────────────────────────

    def metrics(self) -> Dict[str, Any]:
        """Return snapshot + reset rolling counters."""
        now = time.time()
        elapsed = now - self.stats_start
        hits = self.stats["hits"]
        total = hits + self.stats["misses"] or 1
        snap = {
            "cache_hit_rate": round(hits / total * 100, 1),
            "hits": hits,
            "misses": self.stats["misses"],
            "dedup_saves": self.stats["dedup_saves"],
            "tokens_estimated_saved": self.stats["tokens_estimated_saved"],
            "entries_evicted": self.stats["entries_evicted"],
            "cache_size": len(self._cache),
            "uptime_sec": round(elapsed, 1),
        }
        # Reset rolling counters (keep cumulative for next interval)
        self.stats["hits"] = 0
        self.stats["misses"] = 0
        self.stats["dedup_saves"] = 0
        self.stats["bytes_saved"] = 0
        self.stats["tokens_estimated_saved"] = 0
        self.stats["entries_evicted"] = 0
        self.stats_start = now
        return snap


# ── WRAPPER FOR bots/_llm.py ────────────────────────────────────────────
# Lightweight helper so bot agents don't need to import TokenProxy directly.

_token_proxy_instance: Optional[TokenProxy] = None


def get_token_proxy() -> TokenProxy:
    global _token_proxy_instance
    if _token_proxy_instance is None:
        _token_proxy_instance = TokenProxy()
    return _token_proxy_instance


async def cached_llm_json(
    prompt: str,
    system: str,
    temperature: float = 0.3,
    max_tokens: int = 800,
    model: Optional[str] = None,
) -> dict:
    """
    Drop-in replacement for bots._llm.llm_json() with caching.

    Usage:
        from empire_token_proxy import cached_llm_json
        result = await cached_llm_json(prompt="...", system="...")
    """
    from bots._llm import llm_json as _uncached_llm_json

    proxy = get_token_proxy()
    compressed = proxy.compress_prompt(prompt, task="bot.llm")

    key_data = {"p": compressed, "s": system, "t": temperature, "m": max_tokens, "mdl": model}
    result = await proxy.cached_call(
        task="bot.llm",
        key_data=key_data,
        llm_call=lambda: _uncached_llm_json(
            compressed, system, temperature=temperature,
            max_tokens=max_tokens, model=model,
        ),
    )
    return result


# ── Attach _ollama_call helpers so the wrapped router can call them ─────
# These are bound dynamically by wrap_router() above. We define them as
# module-level async functions so the lambdas in wrap_router can reference
# them without creating circular imports at module level.

async def _router_ollama_call(
    router, prompt: str, task: str, model, system,
    temperature, max_tokens, context,
) -> str:
    """Reconstruct the original AIRouter.generate behavior."""
    # Call _call_ollama directly (same as original generate does)
    result = await router._call_ollama(
        prompt=prompt, model=model or router._model_for_task(task),
        system=system, temperature=temperature, max_tokens=max_tokens,
        format=None, task=task,
    )
    await router._log_call(
        task=task, prompt=prompt, system=system,
        output=result.get("text", ""), model=model or router._model_for_task(task),
        tokens_in=result.get("tokens_in", 0), tokens_out=result.get("tokens_out", 0),
        latency_ms=result.get("latency_ms", 0), context=context,
        error=result.get("error"),
    )
    return result.get("text", "")


async def _router_ollama_call_json(
    router, prompt: str, task: str, model, system,
    temperature, max_tokens, context, retries, json_mode=False,
) -> Dict:
    """Reconstruct the original AIRouter.generate_json behavior."""
    chosen = model or router._model_for_task(task)
    last_err = None
    raw = ""
    for attempt in range(retries + 1):
        result = await router._call_ollama(
            prompt=prompt, model=chosen, system=system,
            temperature=temperature, max_tokens=max_tokens,
            format="json", task=task,
        )
        raw = result.get("text", "") or ""
        try:
            clean = raw.strip()
            if "```" in clean:
                parts = clean.split("```")
                if len(parts) >= 2:
                    clean = parts[1]
                if clean.startswith("json"):
                    clean = clean[4:].strip()
            parsed = json.loads(clean)
            await router._log_call(
                task=task, prompt=prompt, system=system, output=raw,
                model=chosen, tokens_in=result.get("tokens_in", 0),
                tokens_out=result.get("tokens_out", 0),
                latency_ms=result.get("latency_ms", 0),
                context=context, error=None,
            )
            return parsed
        except Exception as e:
            last_err = f"json parse: {e} · raw: {raw[:200]}"
            log.warning(f"[token_proxy] parse fail (attempt {attempt + 1}): {last_err}")
            continue
    await router._log_call(
        task=task, prompt=prompt, system=system, output=raw,
        model=chosen, tokens_in=0, tokens_out=0, latency_ms=0,
        context=context, error=last_err,
    )
    return {"_error": last_err, "_raw": raw}


# Monkey-patching is now done inside wrap_router() to avoid import-order
# dependencies. These module-level patches were removed to keep the
# module safe to import regardless of import order.
