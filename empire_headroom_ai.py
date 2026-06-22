"""
EMPIRE V49 · HEADROOM-AI CONTEXT COMPRESSOR
============================================
Wraps headroom-ai (headroomlabs-ai/headroom) for use by Empire AI agents.

Reduces LLM context size by 60-95% by compressing tool outputs, logs,
RAG chunks, and files before they're sent to the LLM. Saves tokens
while maintaining task accuracy.

Usage:
    from empire_headroom_ai import compress_context, headroom_proxy

    # Compress a single payload
    compressed = compress_context(original_text)

    # Or use as a context manager for agent loops
    with headroom_proxy() as proxy:
        result = proxy.compress(agent_output)
"""

import logging
import os
from typing import Optional

log = logging.getLogger("empire.headroom_ai")

# ── Lazy import — headroom-ai is heavy, only load on first use ──────────
_HEADROOM_LOADED = False
_HeadroomCompressor = None


def _ensure_loaded():
    """Lazy-load headroom-ai on first call."""
    global _HEADROOM_LOADED, _HeadroomCompressor
    if _HEADROOM_LOADED:
        return True
    try:
        from headroom import Headroom
        _HeadroomCompressor = Headroom
        _HEADROOM_LOADED = True
        log.info("[headroom-ai] loaded successfully")
        return True
    except ImportError:
        log.warning("[headroom-ai] package not installed — run: pip install 'headroom-ai[all]'")
        return False


def compress_context(
    text: str,
    max_tokens: Optional[int] = None,
    preserve_structure: bool = True,
) -> str:
    """Compress a text payload to reduce LLM token usage.

    Uses headroom-ai's compression pipeline: removes redundant text,
    collapses repeated patterns, and tersifies verbose output while
    preserving key information.

    Args:
        text: The raw text to compress (tool output, log, RAG chunk, etc.)
        max_tokens: Optional target token limit after compression.
        preserve_structure: Keep JSON/table/markdown structure intact.

    Returns:
        Compressed text string (typically 60-95% smaller).
    """
    if not _ensure_loaded():
        log.debug("[headroom-ai] fallback: returning uncompressed text")
        return text

    if not text or len(text) < 200:
        # Not worth compressing tiny inputs — overhead > savings
        return text

    try:
        compressor = _HeadroomCompressor(
            max_tokens=max_tokens,
            preserve_structure=preserve_structure,
        )
        result = compressor.compress(text)
        ratio = 1 - (len(result) / max(len(text), 1))
        log.debug(f"[headroom-ai] compressed {len(text)} → {len(result)} chars ({ratio:.0%} reduction)")
        return result
    except Exception as e:
        log.error(f"[headroom-ai] compression failed: {e}")
        return text  # Fallback: return uncompressed


def compress_for_agent(
    agent_name: str,
    context: dict,
) -> dict:
    """Compress all text fields in an agent's context dict.

    Designed for Empire agents that pass structured context to their LLM:
      {
        "system_prompt": "...",
        "tool_outputs": ["...", "..."],
        "conversation_history": "...",
      }

    Args:
        agent_name: Name of the calling agent (for logging).
        context: Dict with text fields to compress.

    Returns:
        Dict with compressed text fields.
    """
    if not _ensure_loaded():
        return context

    compressed = {}
    for key, value in context.items():
        if isinstance(value, str) and len(value) > 200:
            compressed[key] = compress_context(value)
        elif isinstance(value, list):
            compressed[key] = [
                compress_context(item) if isinstance(item, str) and len(item) > 200 else item
                for item in value
            ]
        else:
            compressed[key] = value

    total_orig = sum(len(str(v)) for v in context.values())
    total_new = sum(len(str(v)) for v in compressed.values())
    if total_orig > 0:
        log.info(
            f"[headroom-ai] {agent_name}: {total_orig} → {total_new} chars "
            f"({(1 - total_new / total_orig):.0%} reduction)"
        )

    return compressed
