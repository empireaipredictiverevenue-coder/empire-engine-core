"""
EMPIRE V49 · SHARED LLM HELPER
===============================
Single source of truth for Ollama JSON calls across all bot agents.
Eliminates the `_ollama_json` duplication in seo_agent, research_agent,
content_agent, and any future agents.

Usage:
    from bots._llm import llm_json

    result = await llm_json(
        prompt="...",
        system="...",
        temperature=0.3,
        max_tokens=800,
    )
"""

import os
import json
import logging

import httpx

log = logging.getLogger("empire.llm")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("AI_MODEL_SEO", "llama3.2:3b")


async def llm_json(
    prompt: str,
    system: str,
    temperature: float = 0.3,
    max_tokens: int = 800,
    model: str = None,
) -> dict:
    """
    Query local Ollama for structured JSON output.
    Returns parsed dict, or {"_error": str} on failure.
    """
    chosen = model or OLLAMA_MODEL
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            r = await client.post(
                f"{OLLAMA_URL.rstrip('/')}/api/chat",
                json={
                    "model": chosen,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                },
            )
            r.raise_for_status()
            raw = r.json().get("message", {}).get("content", "{}")
            clean = raw.strip()
            if "```json" in clean:
                clean = clean.split("```json")[1].split("```")[0].strip()
            elif "```" in clean:
                clean = clean.split("```")[1].split("```")[0].strip()
            return json.loads(clean)
    except Exception as e:
        log.error(f"[llm] Ollama call failed: {e}")
        return {"_error": str(e)}
