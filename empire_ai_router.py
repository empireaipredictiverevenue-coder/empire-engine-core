"""
EMPIRE V49 · AI ROUTER
=======================
Provider-agnostic LLM dispatcher. Local Ollama first.
Routes by task type to the best-fit model.
Logs every call to ai_call_log + brain_training_log + Langfuse traces.
"""
import os
import json
import time
import logging
import asyncio
from typing import Dict, Any, Optional, Callable
import httpx

from observability.tracing import TraceContext

# Local RAG: pull Obsidian vault context for every LLM call. Cheap (~1ms,
# 8-note vault). Fails silent if vault missing.
try:
    from empire_obsidian_rag import build_context as _build_obsidian_context
    _RAG_AVAILABLE = True
except ImportError:
    _RAG_AVAILABLE = False
    _build_obsidian_context = None

# Cap on how big the injected context block can get (chars)
_RAG_CONTEXT_CAP = int(os.environ.get("RAG_MAX_CONTEXT_CHARS", "1500"))

log = logging.getLogger("empire.ai.router")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("AI_DEFAULT_MODEL", "llama3.2:3b")
MAX_CONCURRENT = int(os.environ.get("AI_MAX_CONCURRENT", "2"))
TIMEOUT_SEC = int(os.environ.get("AI_TIMEOUT_SEC", "90"))

# ── Cloud provider config (defined BEFORE TASK_MODEL so the routing
# defaults below can reference MINIMAX_API_KEY safely) ────────────
MINIMAX_API_KEY       = os.environ.get("MINIMAX_API_KEY", "")
MINIMAX_BASE_URL      = os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.io/v1")
# Re-evaluated at AIRouter.__init__ so post-import env loads are picked up
_MINIMAX_OK = bool(os.environ.get("MINIMAX_API_KEY", ""))  # may be empty at import

# Task → model routing. Fast model for high-volume; bigger model for writing.
# Defaults route to MiniMax when MINIMAX_API_KEY is set, else Ollama. Override
# with AI_MODEL_* env vars per task.
TASK_MODEL = {
    "brain.decide":          os.environ.get("AI_MODEL_DECIDE",
                                             "MiniMax-M3" if _MINIMAX_OK else "llama3.2:3b"),
    "reply.qualify":         os.environ.get("AI_MODEL_QUALIFY",
                                             "MiniMax-M2.1" if _MINIMAX_OK else "llama3.2:3b"),
    "enricher.extract":      os.environ.get("AI_MODEL_ENRICH",
                                             "MiniMax-M2.1" if _MINIMAX_OK else "llama3.2:3b"),
    "narrate.event":         os.environ.get("AI_MODEL_NARRATE",
                                             "MiniMax-M2.5" if _MINIMAX_OK else "llama3.2:3b"),
    "email.draft":           os.environ.get("AI_MODEL_DRAFT",
                                             "MiniMax-M2.5" if _MINIMAX_OK else "llama3.1:latest"),
    "mission.briefing":      os.environ.get("AI_MODEL_BRIEFING",
                                             "MiniMax-M2.7" if _MINIMAX_OK else "qwen2.5-coder:14b"),
    "general":               DEFAULT_MODEL,
}

# ── Cloud provider config ────────────────────────────────────────────
# Activated only when the corresponding API key is set in env.
# `glm-` / `zhipu:` / `zai/` model names → Z.ai (OpenAI-compatible endpoint).
# `claude-` / `anthropic:` model names → Anthropic Messages API.
ZAI_API_KEY       = os.environ.get("ZAI_API_KEY", "")            # GLM 5.2 etc.
ZAI_BASE_URL      = os.environ.get("ZAI_BASE_URL", "https://api.z.ai/api/paas/v4")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")      # already in env
ANTHROPIC_MODEL_DEFAULT = os.environ.get("ANTHROPIC_MODEL_DEFAULT", "claude-sonnet-4-5")
ZAI_MODEL_DEFAULT = os.environ.get("ZAI_MODEL_DEFAULT", "glm-5.2")


def _provider_for_model(model: str) -> str:
    """Return 'minimax', 'zhipu', 'anthropic', or 'ollama' based on model name conventions."""
    if not model:
        return "ollama"
    m = model.lower()
    if m.startswith(("MiniMax", "minimax:", "minimax/")) or "minimax-m" in m:
        return "minimax"
    if m.startswith(("glm-", "zhipu:", "zai/")) or "glm-5" in m:
        return "zhipu"
    if m.startswith(("claude-", "anthropic:")):
        return "anthropic"
    return "ollama"


class AIRouter:
    PROVIDER = "ollama"

    def __init__(self, get_db: Optional[Callable] = None):
        self._get_db = get_db
        self._sem = asyncio.Semaphore(MAX_CONCURRENT)
        # Re-evaluate provider availability + per-task routing defaults
        # at instantiation. This handles the case where the env file is
        # loaded AFTER this module was first imported (e.g. hub.py loads
        # /root/.env inside main(), after `from empire_ai_router import ...`).
        self._minimax_ok = bool(os.environ.get("MINIMAX_API_KEY", ""))
        self._zhipu_ok = bool(os.environ.get("ZAI_API_KEY", ""))
        self._anthropic_ok = bool(os.environ.get("ANTHROPIC_API_KEY", ""))
        self._task_model = {
            "brain.decide":          os.environ.get("AI_MODEL_DECIDE",
                                                     "MiniMax-M3" if self._minimax_ok else "llama3.2:3b"),
            "reply.qualify":         os.environ.get("AI_MODEL_QUALIFY",
                                                     "MiniMax-M2.1" if self._minimax_ok else "llama3.2:3b"),
            "enricher.extract":      os.environ.get("AI_MODEL_ENRICH",
                                                     "MiniMax-M2.1" if self._minimax_ok else "llama3.2:3b"),
            "narrate.event":         os.environ.get("AI_MODEL_NARRATE",
                                                     "MiniMax-M2.5" if self._minimax_ok else "llama3.2:3b"),
            "email.draft":           os.environ.get("AI_MODEL_DRAFT",
                                                     "MiniMax-M2.5" if self._minimax_ok else "llama3.1:latest"),
            "mission.briefing":      os.environ.get("AI_MODEL_BRIEFING",
                                                     "MiniMax-M2.7" if self._minimax_ok else "qwen2.5-coder:14b"),
            "general":               DEFAULT_MODEL,
        }

    def _model_for_task(self, task: str, override: Optional[str] = None) -> str:
        if override:
            return override
        return getattr(self, "_task_model", TASK_MODEL).get(task, DEFAULT_MODEL)

    async def generate(
        self, prompt: str, *, task: str = "general", model: Optional[str] = None,
        system: Optional[str] = None, temperature: float = 0.4, max_tokens: int = 1024,
        context: Optional[Dict] = None,
    ) -> str:
        chosen = self._model_for_task(task, model)
        provider = _provider_for_model(chosen)
        # Pull Obsidian vault context relevant to this prompt. Cheap (~1ms),
        # scoped to the top-K scoring notes. Appends to the system message.
        if _RAG_AVAILABLE and prompt:
            try:
                rag_block = _build_obsidian_context(prompt)
                if rag_block:
                    system = (system or "") + "\n\n" + rag_block
            except Exception as rag_err:
                log.debug(f"[router] RAG failed: {rag_err}")
        # Re-read env per call so provider keys set after import still work.
        if provider == "minimax" and os.environ.get("MINIMAX_API_KEY"):
            result = await self._call_minimax(prompt=prompt, model=chosen, system=system,
                                              temperature=temperature, max_tokens=max_tokens, task=task)
        elif provider == "zhipu" and os.environ.get("ZAI_API_KEY"):
            result = await self._call_zhipu(prompt=prompt, model=chosen, system=system,
                                             temperature=temperature, max_tokens=max_tokens, task=task)
        elif provider == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
            result = await self._call_anthropic(prompt=prompt, model=chosen, system=system,
                                                temperature=temperature, max_tokens=max_tokens, task=task)
        else:
            result = await self._call_ollama(prompt=prompt, model=chosen, system=system,
                                              temperature=temperature, max_tokens=max_tokens,
                                              format=None, task=task)
        await self._log_call(task=task, prompt=prompt, system=system, output=result.get("text", ""),
                             model=chosen, provider=provider,
                             tokens_in=result.get("tokens_in", 0),
                             tokens_out=result.get("tokens_out", 0), latency_ms=result.get("latency_ms", 0),
                             context=context, error=result.get("error"))
        return result.get("text", "")

    async def generate_json(
        self, prompt: str, *, task: str = "general", model: Optional[str] = None,
        system: Optional[str] = None, temperature: float = 0.2, max_tokens: int = 1024,
        context: Optional[Dict] = None, retries: int = 2,
    ) -> Dict[str, Any]:
        chosen = self._model_for_task(task, model)
        provider = _provider_for_model(chosen)
        if _RAG_AVAILABLE and prompt:
            try:
                rag_block = _build_obsidian_context(prompt)
                if rag_block:
                    system = (system or "") + "\n\n" + rag_block
            except Exception as rag_err:
                log.debug(f"[router] RAG failed: {rag_err}")
        last_err = None
        raw = ""
        for attempt in range(retries + 1):
            if provider == "minimax" and os.environ.get("MINIMAX_API_KEY"):
                result = await self._call_minimax(prompt=prompt, model=chosen, system=system,
                                                  temperature=temperature, max_tokens=max_tokens, task=task)
            elif provider == "zhipu" and os.environ.get("ZAI_API_KEY"):
                result = await self._call_zhipu(prompt=prompt, model=chosen, system=system,
                                                 temperature=temperature, max_tokens=max_tokens, task=task)
            elif provider == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
                result = await self._call_anthropic(prompt=prompt, model=chosen, system=system,
                                                    temperature=temperature, max_tokens=max_tokens, task=task)
            else:
                result = await self._call_ollama(prompt=prompt, model=chosen, system=system,
                                                  temperature=temperature, max_tokens=max_tokens,
                                                  format="json", task=task)
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
                await self._log_call(task=task, prompt=prompt, system=system, output=raw,
                                     model=chosen, tokens_in=result.get("tokens_in", 0),
                                     tokens_out=result.get("tokens_out", 0),
                                     latency_ms=result.get("latency_ms", 0),
                                     context=context, error=None)
                return parsed
            except Exception as e:
                last_err = f"json parse: {e} · raw: {raw[:200]}"
                log.warning(f"[router] parse fail (attempt {attempt + 1}): {last_err}")
                continue
        await self._log_call(task=task, prompt=prompt, system=system, output=raw,
                             model=chosen, tokens_in=0, tokens_out=0, latency_ms=0,
                             context=context, error=last_err)
        return {"_error": last_err, "_raw": raw}

    async def _call_ollama(
        self, prompt: str, model: str, system: Optional[str],
        temperature: float, max_tokens: int, format: Optional[str] = None,
        task: str = "general",
    ) -> Dict:
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            # Keep model loaded for 30min between calls so we don't pay
            # the ~60s cold-load penalty every background tick.
            "keep_alive": "30m",
            "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": 4096},
        }
        if system:
            payload["system"] = system
        if format == "json":
            payload["format"] = "json"
        start = time.time()

        # Langfuse trace wraps the entire call
        async with TraceContext(
                name=f"ollama.{task}",
                model=model,
                input=prompt[:3000],
                system=system,
                task=task,
                metadata={"format": format, "temperature": temperature},
                tags=["provider:ollama", f"model:{model}", f"task:{task}"],
            ) as ctx:
                # Semaphore inside the trace for accurate HTTP latency
                async with self._sem:
                    try:
                        async with httpx.AsyncClient(timeout=TIMEOUT_SEC) as client:
                            r = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
                            r.raise_for_status()
                            data = r.json()
                            result = {
                                "text": data.get("response", ""),
                                "tokens_in": data.get("prompt_eval_count", 0),
                                "tokens_out": data.get("eval_count", 0),
                                "latency_ms": int((time.time() - start) * 1000),
                            }
                            ctx.set_output(
                                output=result["text"],
                                tokens_in=result["tokens_in"],
                                tokens_out=result["tokens_out"],
                                latency_ms=result["latency_ms"],
                            )
                            return result
                    except Exception as e:
                        log.error(f"[router] Ollama call failed ({model}): {e}")
                        result = {"text": "", "tokens_in": 0, "tokens_out": 0, "latency_ms": 0, "error": str(e)}
                        ctx.set_output(error=str(e))
                        return result

    async def _log_call(
        self, task: str, prompt: str, system: Optional[str], output: str,
        model: str, tokens_in: int, tokens_out: int, latency_ms: int,
        context: Optional[Dict] = None, error: Optional[str] = None,
        provider: str = "ollama",
    ):
        if not self._get_db:
            return
        try:
            db = self._get_db()
            db.table("ai_call_log").insert({
                "task": task, "provider": provider or self.PROVIDER, "model": model,
                "tokens_in": tokens_in, "tokens_out": tokens_out,
                "latency_ms": latency_ms, "cost_usd": 0.0, "error": error,
            }).execute()
            db.table("brain_training_log").insert({
                "task": task, "system": system, "prompt": prompt[:8000],
                "output": (output or "")[:8000], "context": context or {},
                "model_used": model,
            }).execute()
        except Exception as e:
            log.error(f"[router] log failed: {e}")


    # ── Cloud provider call: MiniMax (MiniMax-M3 etc.) ───────────────────
    async def _call_minimax(
        self, prompt: str, model: str, system: Optional[str],
        temperature: float, max_tokens: int, task: str = "general",
    ) -> Dict:
        """OpenAI-compatible call to MiniMax API. Used for MiniMax-M3.

        MiniMax models emit a <think>...</think> reasoning block by default.
        We strip it for the 'text' field (so downstream callers get clean output)
        and expose it via 'reasoning_content' for callers that want it.
        """
        url = f"{MINIMAX_BASE_URL.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {MINIMAX_API_KEY}",
            "Content-Type": "application/json",
        }
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        # Strip provider prefix if present ("minimax:MiniMax-M3" → "MiniMax-M3",
        # "minimax/MiniMax-M3" → "MiniMax-M3")
        api_model = model
        for prefix in ("minimax:", "minimax/"):
            if api_model.lower().startswith(prefix):
                api_model = api_model[len(prefix):]
                break
        payload = {
            "model": api_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        start = time.time()
        async with TraceContext(
                name=f"minimax.{task}",
                model=api_model,
                input=prompt[:3000],
                system=system,
                task=task,
                tags=["provider:minimax", f"model:{api_model}", f"task:{task}"],
        ) as ctx:
            async with self._sem:
                try:
                    async with httpx.AsyncClient(timeout=TIMEOUT_SEC) as client:
                        r = await client.post(url, json=payload, headers=headers)
                        r.raise_for_status()
                        data = r.json()
                        choice = (data.get("choices") or [{}])[0]
                        msg = choice.get("message") or {}
                        raw_content = msg.get("content") or ""
                        # Extract <think>...</think> block if present
                        reasoning = None
                        import re as _re
                        think = _re.search(r"<think>(.*?)</think>", raw_content, _re.DOTALL)
                        if think:
                            reasoning = think.group(1).strip()
                            text = _re.sub(r"<think>.*?</think>\s*", "", raw_content, flags=_re.DOTALL).strip()
                        else:
                            text = raw_content
                        usage = data.get("usage") or {}
                        result = {
                            "text": text,
                            "reasoning_content": reasoning,
                            "tokens_in": int(usage.get("prompt_tokens", 0)),
                            "tokens_out": int(usage.get("completion_tokens", 0)),
                            "latency_ms": int((time.time() - start) * 1000),
                        }
                        ctx.set_output(
                            output=text[:1000],
                            tokens_in=result["tokens_in"],
                            tokens_out=result["tokens_out"],
                            latency_ms=result["latency_ms"],
                        )
                        return result
                except Exception as e:
                    log.error(f"[router] MiniMax call failed ({api_model}): {e}")
                    return {"text": "", "tokens_in": 0, "tokens_out": 0, "latency_ms": 0, "error": str(e)}

    # ── Cloud provider call: Z.ai (GLM 5.2 etc.) ─────────────────────
    async def _call_zhipu(
        self, prompt: str, model: str, system: Optional[str],
        temperature: float, max_tokens: int, task: str = "general",
    ) -> Dict:
        """OpenAI-compatible call to Z.ai API. Used for GLM 5.2."""
        url = f"{ZAI_BASE_URL.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {ZAI_API_KEY}",
            "Content-Type": "application/json",
        }
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": model if not model.startswith(("zhipu:", "zai/")) else model.split(":", 1)[1].split("/", 1)[1],
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        # GLM 5.2 supports reasoning_effort; let users opt in via env
        if os.environ.get("ZAI_THINKING", "false").lower() in ("1", "true", "yes"):
            payload["thinking"] = {"type": "enabled"}
        start = time.time()
        async with TraceContext(
                name=f"zhipu.{task}",
                model=model,
                input=prompt[:3000],
                system=system,
                task=task,
                tags=["provider:zhipu", f"model:{model}", f"task:{task}"],
        ) as ctx:
            async with self._sem:
                try:
                    async with httpx.AsyncClient(timeout=TIMEOUT_SEC) as client:
                        r = await client.post(url, json=payload, headers=headers)
                        r.raise_for_status()
                        data = r.json()
                        choice = (data.get("choices") or [{}])[0]
                        msg = choice.get("message") or {}
                        text = msg.get("content") or ""
                        usage = data.get("usage") or {}
                        result = {
                            "text": text,
                            "tokens_in": int(usage.get("prompt_tokens", 0)),
                            "tokens_out": int(usage.get("completion_tokens", 0)),
                            "latency_ms": int((time.time() - start) * 1000),
                        }
                        # Estimate cost: GLM 5.2 = $1.40/M in, $4.40/M out
                        cost = (result["tokens_in"] / 1e6) * 1.40 + (result["tokens_out"] / 1e6) * 4.40
                        result["cost_usd"] = round(cost, 6)
                        ctx.set_output(
                            output=text[:1000],
                            tokens_in=result["tokens_in"],
                            tokens_out=result["tokens_out"],
                            latency_ms=result["latency_ms"],
                        )
                        return result
                except Exception as e:
                    log.error(f"[router] Z.ai call failed ({model}): {e}")
                    return {"text": "", "tokens_in": 0, "tokens_out": 0, "latency_ms": 0, "error": str(e)}

    # ── Cloud provider call: Anthropic Messages API ─────────────────
    async def _call_anthropic(
        self, prompt: str, model: str, system: Optional[str],
        temperature: float, max_tokens: int, task: str = "general",
    ) -> Dict:
        """Anthropic Messages API call. Used for Claude Sonnet 4 / Opus etc."""
        url = "https://api.anthropic.com/v1/messages"
        # Strip 'anthropic:' prefix if present
        api_model = model.split(":", 1)[1] if model.startswith("anthropic:") else model
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": api_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system
        start = time.time()
        async with TraceContext(
                name=f"anthropic.{task}",
                model=model,
                input=prompt[:3000],
                system=system,
                task=task,
                tags=["provider:anthropic", f"model:{model}", f"task:{task}"],
        ) as ctx:
            async with self._sem:
                try:
                    async with httpx.AsyncClient(timeout=TIMEOUT_SEC) as client:
                        r = await client.post(url, json=payload, headers=headers)
                        r.raise_for_status()
                        data = r.json()
                        blocks = data.get("content") or []
                        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
                        usage = data.get("usage") or {}
                        result = {
                            "text": text,
                            "tokens_in": int(usage.get("input_tokens", 0)),
                            "tokens_out": int(usage.get("output_tokens", 0)),
                            "latency_ms": int((time.time() - start) * 1000),
                        }
                        # Estimate cost: Sonnet 4 = $3/M in, $15/M out
                        cost = (result["tokens_in"] / 1e6) * 3.0 + (result["tokens_out"] / 1e6) * 15.0
                        result["cost_usd"] = round(cost, 6)
                        ctx.set_output(
                            output=text[:1000],
                            tokens_in=result["tokens_in"],
                            tokens_out=result["tokens_out"],
                            latency_ms=result["latency_ms"],
                        )
                        return result
                except Exception as e:
                    log.error(f"[router] Anthropic call failed ({model}): {e}")
                    return {"text": "", "tokens_in": 0, "tokens_out": 0, "latency_ms": 0, "error": str(e)}

    # ── Dispatch helper for external callers (hub brain proxy etc.) ──
    async def call_any(
        self, prompt: str, *, model: str, system: Optional[str] = None,
        temperature: float = 0.4, max_tokens: int = 1024,
    ) -> Dict:
        """Provider-aware dispatch used by the hub brain proxy."""
        provider = _provider_for_model(model)
        if provider == "minimax" and os.environ.get("MINIMAX_API_KEY"):
            return await self._call_minimax(prompt=prompt, model=model, system=system,
                                             temperature=temperature, max_tokens=max_tokens)
        if provider == "zhipu" and os.environ.get("ZAI_API_KEY"):
            return await self._call_zhipu(prompt=prompt, model=model, system=system,
                                          temperature=temperature, max_tokens=max_tokens)
        if provider == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
            return await self._call_anthropic(prompt=prompt, model=model, system=system,
                                               temperature=temperature, max_tokens=max_tokens)
        return await self._call_ollama(prompt=prompt, model=model, system=system,
                                        temperature=temperature, max_tokens=max_tokens)


    async def snapshot(self) -> Dict:
        snap = {
            "provider": self.PROVIDER, "default_model": DEFAULT_MODEL,
            "ollama_url": OLLAMA_URL, "max_concurrent": MAX_CONCURRENT,
            "task_models": TASK_MODEL,
        }
        if self._get_db:
            try:
                db = self._get_db()
                r = db.table("ai_call_log").select("id", count="exact").execute()
                snap["calls_total"] = r.count if hasattr(r, "count") else len(r.data or [])
            except Exception:
                pass
        return snap
