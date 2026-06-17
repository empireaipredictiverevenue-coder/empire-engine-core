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

log = logging.getLogger("empire.ai.router")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("AI_DEFAULT_MODEL", "llama3.2:3b")
MAX_CONCURRENT = int(os.environ.get("AI_MAX_CONCURRENT", "2"))
TIMEOUT_SEC = int(os.environ.get("AI_TIMEOUT_SEC", "90"))

# Task → model routing. Fast model for high-volume; bigger model for writing.
TASK_MODEL = {
    "brain.decide":          os.environ.get("AI_MODEL_DECIDE",   "llama3.2:3b"),
    "reply.qualify":         os.environ.get("AI_MODEL_QUALIFY",  "llama3.2:3b"),
    "enricher.extract":      os.environ.get("AI_MODEL_ENRICH",   "llama3.2:3b"),
    "narrate.event":         os.environ.get("AI_MODEL_NARRATE",  "llama3.2:3b"),
    "email.draft":           os.environ.get("AI_MODEL_DRAFT",    "llama3.1:latest"),
    "mission.briefing":      os.environ.get("AI_MODEL_BRIEFING", "qwen2.5-coder:14b"),
    "general":               DEFAULT_MODEL,
}


class AIRouter:
    PROVIDER = "ollama"

    def __init__(self, get_db: Optional[Callable] = None):
        self._get_db = get_db
        self._sem = asyncio.Semaphore(MAX_CONCURRENT)

    def _model_for_task(self, task: str, override: Optional[str] = None) -> str:
        if override:
            return override
        return TASK_MODEL.get(task, DEFAULT_MODEL)

    async def generate(
        self, prompt: str, *, task: str = "general", model: Optional[str] = None,
        system: Optional[str] = None, temperature: float = 0.4, max_tokens: int = 1024,
        context: Optional[Dict] = None,
    ) -> str:
        chosen = self._model_for_task(task, model)
        result = await self._call_ollama(prompt=prompt, model=chosen, system=system,
                                          temperature=temperature, max_tokens=max_tokens,
                                          format=None, task=task)
        await self._log_call(task=task, prompt=prompt, system=system, output=result.get("text", ""),
                             model=chosen, tokens_in=result.get("tokens_in", 0),
                             tokens_out=result.get("tokens_out", 0), latency_ms=result.get("latency_ms", 0),
                             context=context, error=result.get("error"))
        return result.get("text", "")

    async def generate_json(
        self, prompt: str, *, task: str = "general", model: Optional[str] = None,
        system: Optional[str] = None, temperature: float = 0.2, max_tokens: int = 1024,
        context: Optional[Dict] = None, retries: int = 2,
    ) -> Dict[str, Any]:
        chosen = self._model_for_task(task, model)
        last_err = None
        raw = ""
        for attempt in range(retries + 1):
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
            "options": {"temperature": temperature, "num_predict": max_tokens},
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
    ):
        if not self._get_db:
            return
        try:
            db = self._get_db()
            db.table("ai_call_log").insert({
                "task": task, "provider": self.PROVIDER, "model": model,
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
