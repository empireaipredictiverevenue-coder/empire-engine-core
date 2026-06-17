"""
EMPIRE V49 · LANGFUSE TRACING HELPERS
======================================
Convenience functions for creating Langfuse traces and generations
around LLM calls. All functions are safe to call when Langfuse is
disabled — they return None and become no-ops.

Usage:
    from observability.tracing import TraceContext

    async with TraceContext(name="brain.decide", model="llama3.2:3b") as ctx:
        result = await call_llm(prompt, system)
        ctx.set_output(result, tokens_in=50, tokens_out=20, latency_ms=1200)
"""

import time
import logging
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

from observability.langfuse_client import get_langfuse, flush

log = logging.getLogger("empire.observability.tracing")


class TraceContext:
    """Async context manager for wrapping a single LLM call in a Langfuse
    generation span.

    The context manager creates:
      - A root trace (grouped by task/name + session)
      - A generation span inside the trace for the LLM call

    When Langfuse is disabled, the context manager is a transparent no-op.

    Usage:
        async with TraceContext(
            name="brain.decide",
            model="llama3.2:3b",
            input="prompt text...",
            system="system prompt...",
            task="brain.decide",
            metadata={"target": "foo", "severity": "severe"},
        ) as ctx:
            result = await call_llm(...)
            ctx.set_output(
                output=result,
                tokens_in=50,
                tokens_out=20,
                latency_ms=1200,
            )
    """

    def __init__(
        self,
        *,
        name: str,
        model: str,
        input: str = "",
        system: Optional[str] = None,
        task: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ):
        self.name = name
        self.model = model
        self.input = input
        self.system = system
        self.task = task or name
        self.metadata = dict(metadata or {})
        if system:
            self.metadata["system"] = system[:500]
        self.tags = tags or []
        self._trace = None
        self._generation = None
        self._start_time = None
        self._lf = None
        self._ended = False  # prevent double-end calls

    async def __aenter__(self):
        self._start_time = time.time()
        self._lf = get_langfuse()
        if self._lf is None:
            return self

        try:
            # Create root trace
            trace_tags = list(self.tags)
            if "env" not in [t.split(":")[0] for t in trace_tags if ":" in t]:
                trace_tags.append(f"env:{self._detect_env()}")

            self._trace = self._lf.trace(
                name=self.task,
                metadata={
                    **self.metadata,
                    "input_preview": self.input[:200] if self.input else "",
                },
                tags=trace_tags if trace_tags else None,
            )

            # Create generation span
            model_params = {}
            if self.system:
                model_params["system"] = True

            self._generation = self._trace.generation(
                name=self.name,
                model=self.model,
                input=self.input if self.input else None,
                model_parameters=model_params if model_params else None,
                metadata=self.metadata,
            )
        except Exception as e:
            log.debug(f"[tracing] failed to create trace: {e}")
            self._trace = None
            self._generation = None

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._lf is None or self._generation is None:
            return

        # If the generation was already ended by set_output(), skip.
        if self._ended:
            return

        self._ended = True
        elapsed_ms = int((time.time() - self._start_time) * 1000) if self._start_time else 0

        try:
            if exc_type is not None:
                self._generation.end(
                    output=None,
                    level="ERROR",
                    status_message=f"{exc_type.__name__}: {exc_val}",
                    usage=None,
                )
                if self._trace:
                    self._trace.update(
                        level="ERROR",
                        status_message=f"Failed: {exc_type.__name__}: {exc_val}",
                    )
            else:
                # Generation was never ended — end with a placeholder
                self._generation.end(
                    output=None,
                    metadata={"latency_ms": elapsed_ms, "incomplete": True},
                )
        except Exception as e:
            log.debug(f"[tracing] failed to end generation: {e}")

        # Opportunistic flush
        try:
            flush()
        except Exception:
            pass

    def set_output(
        self,
        output: str = "",
        *,
        tokens_in: int = 0,
        tokens_out: int = 0,
        latency_ms: int = 0,
        error: Optional[str] = None,
    ):
        """Record the LLM output and usage stats on the generation span."""
        if self._lf is None or self._generation is None:
            return

        elapsed = latency_ms or int((time.time() - self._start_time) * 1000) if self._start_time else 0
        usage = {"prompt_tokens": tokens_in, "completion_tokens": tokens_out}
        if tokens_in + tokens_out > 0:
            usage["total_tokens"] = tokens_in + tokens_out

        if self._ended:
            return  # already ended — prevent double-end
        self._ended = True

        try:
            if error:
                self._generation.end(
                    output=output[:5000] if output else None,
                    usage=usage,
                    level="WARNING" if "json" in error.lower() else "ERROR",
                    status_message=error[:200],
                    metadata={"latency_ms": elapsed},
                )
            else:
                self._generation.end(
                    output=output[:5000] if output else None,
                    usage=usage,
                    metadata={"latency_ms": elapsed},
                )
        except Exception as e:
            log.debug(f"[tracing] set_output failed: {e}")

    @staticmethod
    def _detect_env() -> str:
        """Detect deployment environment from env vars or hostname."""
        import socket
        host = socket.gethostname()
        if host == "empire-ai":
            return "production"
        return "development"


# ── Simple function wrapper ───────────────────────────────────────────
def trace_llm_call(func):
    """Decorator that wraps an async function returning LLM results with
    Langfuse tracing.

    The wrapped function must return a dict with keys:
        text, tokens_in, tokens_out, latency_ms (or error)
    Compatible with AIRouter._call_ollama() return format.
    """
    from functools import wraps

    @wraps(func)
    async def wrapper(*args, **kwargs):
        name = kwargs.get("task") or func.__name__
        model = kwargs.get("model", "unknown")
        prompt = kwargs.get("prompt", "")
        system = kwargs.get("system")

        async with TraceContext(
            name=name,
            model=model,
            input=prompt[:2000] if prompt else "",
            system=system,
            task=name,
        ) as ctx:
            result = await func(*args, **kwargs)
            if isinstance(result, dict):
                ctx.set_output(
                    output=result.get("text", ""),
                    tokens_in=result.get("tokens_in", 0),
                    tokens_out=result.get("tokens_out", 0),
                    latency_ms=result.get("latency_ms", 0),
                    error=result.get("error"),
                )
            return result

    return wrapper
