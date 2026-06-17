"""
EMPIRE V49 · LANGFUSE CLIENT SINGLETON
=======================================
Lazy-initialised Langfuse client with graceful degradation.
If Langfuse is not installed or not configured, all calls become
safe no-ops so the rest of the system is unaffected.

Usage:
    from observability.langfuse_client import get_langfuse, is_enabled
    lf = get_langfuse()
    if lf:
        trace = lf.trace(name="my-trace")
        generation = trace.generation(...)

ENV:
    LANGFUSE_PUBLIC_KEY   — Langfuse project public key
    LANGFUSE_SECRET_KEY   — Langfuse project secret key
    LANGFUSE_HOST         — Langfuse host (default: https://cloud.langfuse.com)
    LANGFUSE_ENABLED      — Set to "false" to disable (default: enabled if keys present)
"""

import os
import logging
from typing import Optional, Any

log = logging.getLogger("empire.observability")

try:
    from langfuse import Langfuse
    _HAS_PACKAGE = True
except ImportError:
    _HAS_PACKAGE = False
    log.warning("[langfuse] package not installed — install with `pip install langfuse`")

# ── Singleton state ───────────────────────────────────────────────────
_langfuse_instance: Optional[Any] = None
_langfuse_enabled: bool = False
_langfuse_attempted: bool = False  # True after first init attempt


def get_langfuse() -> Optional[Any]:
    """Return the Langfuse singleton, or None if not configured/available."""
    global _langfuse_instance, _langfuse_enabled, _langfuse_attempted

    if _langfuse_attempted:
        return _langfuse_instance if _langfuse_enabled else None

    _langfuse_attempted = True

    # 1. Check package availability
    if not _HAS_PACKAGE:
        log.info("[langfuse] skipping init — package not installed")
        _langfuse_enabled = False
        return None

    # 2. Check explicit disable
    enabled_override = os.environ.get("LANGFUSE_ENABLED", "true").strip().lower()
    if enabled_override == "false":
        log.info("[langfuse] explicitly disabled via LANGFUSE_ENABLED=false")
        _langfuse_enabled = False
        return None

    # 3. Check credentials
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip()
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "").strip()
    host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com").strip()

    if not public_key or not secret_key:
        log.info(
            "[langfuse] not configured — set LANGFUSE_PUBLIC_KEY and "
            "LANGFUSE_SECRET_KEY env vars to enable"
        )
        _langfuse_enabled = False
        return None

    # 4. Initialize
    try:
        _langfuse_instance = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
            # Reduce SDK noise in logs; we handle logging ourselves
            debug=False,
        )
        _langfuse_enabled = True
        log.info(f"[langfuse] initialized — host={host}")
    except Exception as e:
        log.warning(f"[langfuse] init failed: {e} — observability disabled")
        _langfuse_enabled = False

    return _langfuse_instance if _langfuse_enabled else None


def is_enabled() -> bool:
    """Check whether Langfuse is active without triggering init."""
    global _langfuse_enabled, _langfuse_attempted
    if not _langfuse_attempted:
        get_langfuse()  # triggers init
    return _langfuse_enabled


def flush():
    """Flush pending Langfuse events. Safe to call even when disabled."""
    if not is_enabled():
        return
    try:
        _langfuse_instance.flush()  # type: ignore[union-attr]
    except Exception as e:
        log.debug(f"[langfuse] flush failed: {e}")


def shutdown():
    """Shutdown Langfuse — flush + shutdown. Call on app shutdown."""
    if not is_enabled():
        return
    try:
        _langfuse_instance.flush()  # type: ignore[union-attr]
        _langfuse_instance.shutdown()  # type: ignore[union-attr]
        log.info("[langfuse] shutdown complete")
    except Exception as e:
        log.debug(f"[langfuse] shutdown failed: {e}")
