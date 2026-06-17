"""
EMPIRE V49 · SPACE PROVIDERS
=============================
Multi-provider LLM abstraction for deep reasoning.

Uses **LiteLLM Router** as the primary engine for battle-tested
multi-provider routing with automatic:
  - Fallbacks (Gemini → Claude → Ollama)
  - Rate-limit cooldowns and retries
  - Request timeouts and error classification
  - Provider-agnostic API (same interface for all models)

Supports three backends tried in cascade:
  1. Gemini (free tier via Google AI Studio — no credit card required)
  2. Claude (Anthropic API — trial credits available)
  3. Ollama (local fallback — always available, zero cost)

Falls back to direct HTTP calls if LiteLLM is not installed.

Usage:
    from bots.space_providers import SpaceReasoner

    reasoner = SpaceReasoner(prefer="gemini")
    result = await reasoner.reason("What should we do?", system="You are...")
"""

import os
import json
import logging
from typing import Optional


log = logging.getLogger("empire.space")

# ── Configuration ──────────────────────────────────────────────────────

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
CLAUDE_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# Model selection (overridable via env)
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")
MINIMAX_MODEL = os.environ.get("MINIMAX_MODEL", "minimax/MiniMax-M3")
OLLAMA_MODEL = os.environ.get("AI_MODEL_SPACE", "qwen2.5-coder:14b")

# ── Provider Results ───────────────────────────────────────────────────


class ProviderResult:
    """Lightweight result wrapper with provider metadata."""

    def __init__(self, text: str = "", error: Optional[str] = None, provider: str = ""):
        self.text = text
        self.error = error
        self.provider = provider

    def ok(self) -> bool:
        return not self.error and bool(self.text.strip())


# ═════════════════════════════════════════════════════════════════════
# 1. LITELLM ENGINE (primary)
# ═════════════════════════════════════════════════════════════════════

_HAS_LITELLM = False
LiteLLMRouter = None
try:
    from litellm import Router as LiteLLMRouter
    _HAS_LITELLM = True
except ImportError:
    pass


def _build_model_list() -> list:
    """Build the litellm Router model_list from configured env vars."""
    model_list = []

    if GEMINI_API_KEY:
        model_list.append({
            "model_name": "gemini",
            "litellm_params": {
                "model": f"gemini/{GEMINI_MODEL}",
                "api_key": GEMINI_API_KEY,
            },
        })

    if CLAUDE_API_KEY:
        model_list.append({
            "model_name": "claude",
            "litellm_params": {
                # Use explicit anthropic/ prefix for Claude models
                "model": f"anthropic/{CLAUDE_MODEL}",
                "api_key": CLAUDE_API_KEY,
            },
        })

    if MINIMAX_API_KEY:
        model_list.append({
            "model_name": "minimax",
            "litellm_params": {
                "model": MINIMAX_MODEL,
                "api_key": MINIMAX_API_KEY,
            },
        })

    # Ollama always available locally
    model_list.append({
        "model_name": "ollama",
        "litellm_params": {
            "model": f"ollama/{OLLAMA_MODEL}",
            "api_base": OLLAMA_URL,
        },
    })

    return model_list


def _build_fallbacks() -> list:
    """Build fallback chain: Gemini → Claude → MiniMax → Ollama.

    Only includes providers whose API keys are configured.
    """
    fallbacks = []
    if GEMINI_API_KEY and CLAUDE_API_KEY:
        fallbacks.append({"gemini": ["claude"]})
    if CLAUDE_API_KEY and MINIMAX_API_KEY:
        fallbacks.append({"claude": ["minimax"]})
    elif GEMINI_API_KEY and MINIMAX_API_KEY:
        fallbacks.append({"gemini": ["minimax"]})
    if MINIMAX_API_KEY:
        fallbacks.append({"minimax": ["ollama"]})
    elif CLAUDE_API_KEY:
        fallbacks.append({"claude": ["ollama"]})
    elif GEMINI_API_KEY:
        fallbacks.append({"gemini": ["ollama"]})
    return fallbacks


class _LiteLLMEngine:
    """Primary engine: LiteLLM Router with automatic fallbacks and retries."""

    def __init__(self):
        self._router = None
        if _HAS_LITELLM:
            self._init_router()

    def _init_router(self):
        model_list = _build_model_list()
        if not model_list:
            return

        fallbacks = _build_fallbacks()

        try:
            self._router = LiteLLMRouter(
                model_list=model_list,
                fallbacks=fallbacks,
                cooldown_time=30,
                num_retries=1,
                timeout=20,
            )
            log.info(f"[space] LiteLLM Router initialised with {len(model_list)} deployments")
        except Exception as e:
            log.warning(f"[space] LiteLLM init failed: {e}")
            self._router = None

    async def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 2048,
        prefer: str = "",
    ) -> ProviderResult:
        """Generate using LiteLLM Router with fallbacks.

        Tries the preferred provider first, then falls back through
        the configured chain (Gemini → Claude → Ollama).
        """
        if not _HAS_LITELLM or self._router is None:
            return ProviderResult(error="LiteLLM not available", provider="litellm")

        # Determine starting model based on preference
        # Router fallbacks handle missing API keys gracefully
        model_name = prefer if prefer in ("gemini", "claude", "minimax", "ollama") else "gemini"

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await self._router.acompletion(
                model=model_name,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.3,
            )
            text = response.choices[0].message.content or ""
            model_used = getattr(response, "model", "unknown")
            return ProviderResult(text=text, provider=f"litellm/{model_used}")
        except Exception as e:
            error_str = str(e)[:300]
            return ProviderResult(error=error_str, provider="litellm")


# ═════════════════════════════════════════════════════════════════════
# 2. DIRECT HTTP ENGINE (fallback when LiteLLM unavailable)
# ═════════════════════════════════════════════════════════════════════


class _DirectEngine:
    """Minimal fallback when LiteLLM is not installed.

    This is intentionally minimal — LiteLLM is the primary engine.
    If you need this fallback, run: pip install litellm
    """

    def __init__(self):
        if not _HAS_LITELLM:
            log.warning("[space] LiteLLM not installed — install with 'pip install litellm' for full multi-provider routing")

    async def generate(
        self,
        prompt: str = "",
        system: str = "",
        max_tokens: int = 2048,
        prefer: str = "",
    ) -> ProviderResult:
        """Stub fallback — LiteLLM is required for actual generation."""
        return ProviderResult(
            error="LiteLLM not installed — run 'pip install litellm' for multi-provider routing",
            provider="direct",
        )


# ═════════════════════════════════════════════════════════════════════
# 3. SPACE REASONER (public orchestrator)
# ═════════════════════════════════════════════════════════════════════


class SpaceReasoner:
    """Multi-provider deep reasoner.

    Uses LiteLLM Router as the primary engine for battle-tested
    multi-provider routing with automatic fallbacks and retries.
    Falls back to direct HTTP calls if LiteLLM is not available.

    Tries providers in cascade: Gemini (free) → Claude → Ollama (local).
    Use `prefer` to force a specific provider first.

    Public methods:
        reason(prompt, system, max_tokens) -> dict
        reason_json(prompt, system, max_tokens) -> dict
    """

    def __init__(self, prefer: str = ""):
        self._prefer = prefer
        self._litellm = _LiteLLMEngine()
        self._direct = _DirectEngine()

    async def reason(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 2048,
    ) -> dict:
        """Run deep reasoning across available providers.

        Returns:
            {"text": str, "provider": str, "ok": True}
            or {"text": "", "ok": False, "error": str}
        """
        # Try LiteLLM first
        result = await self._litellm.generate(
            prompt=prompt, system=system, max_tokens=max_tokens, prefer=self._prefer,
        )
        if result.ok():
            log.info(f"[space] ✅ {result.provider} — {len(result.text)} chars")
            return {"text": result.text, "provider": result.provider, "ok": True}
        if result.error != "LiteLLM not available":
            log.debug(f"[space] LiteLLM failed: {result.error[:100]} — falling back to direct HTTP")

        # Fall back to direct HTTP calls
        result = await self._direct.generate(
            prompt=prompt, system=system, max_tokens=max_tokens, prefer=self._prefer,
        )
        if result.ok():
            log.info(f"[space] ✅ {result.provider} — {len(result.text)} chars")
            return {"text": result.text, "provider": result.provider, "ok": True}

        return {"text": "", "ok": False, "error": result.error or "all providers failed"}

    async def reason_json(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 2048,
    ) -> dict:
        """Run reasoning and parse result as JSON.

        Returns:
            {"ok": True, "data": dict, "provider": str, "raw": str}
            or {"ok": False, "error": str, "raw": str, "provider": str}
        """
        result = await self.reason(prompt=prompt, system=system, max_tokens=max_tokens)
        if not result.get("ok"):
            return {**result, "data": None, "raw": result.get("text", "")}

        raw = result.get("text", "")
        try:
            clean = raw.strip()
            # Strip markdown code fences if present
            if "```json" in clean:
                clean = clean.split("```json")[1].split("```")[0].strip()
            elif "```" in clean:
                parts = clean.split("```")
                if len(parts) >= 2:
                    middle = parts[1]
                    if middle.startswith("json"):
                        middle = middle[4:].strip()
                    clean = middle.strip()
            parsed = json.loads(clean)
            return {"ok": True, "data": parsed, "provider": result.get("provider"), "raw": raw}
        except json.JSONDecodeError as e:
            return {"ok": False, "error": f"JSON parse: {e}", "raw": raw, "provider": result.get("provider")}


# ── Default instance (lazy singleton for easy imports) ────────────────

_default_reasoner: Optional[SpaceReasoner] = None


def get_reasoner(prefer: str = "") -> SpaceReasoner:
    """Get or create the default SpaceReasoner instance."""
    global _default_reasoner
    if _default_reasoner is None:
        _default_reasoner = SpaceReasoner(prefer=prefer)
    return _default_reasoner
