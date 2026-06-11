"""
EMPIRE V49 · LOCAL BRAIN (OLLAMA INTERFACE)
=============================================
Direct low-overhead loopback to the local Ollama instance.
Used by bots and agents that need quick LLM access without
the full AIRouter logging/telemetry overhead.

For structured JSON generation and task-routed calls, use
empire_ai_router.AIRouter instead — it includes logging,
concurrency control, and model routing by task type.
"""

import json
import logging
from typing import Optional, Dict, Any

import httpx

log = logging.getLogger("empire.local_brain")

OLLAMA_URL = "http://localhost:11434"


class LocalBrain:
    """
    Thin wrapper around Ollama's /api/chat endpoint.
    For serious use, wire through empire_ai_router.AIRouter instead.
    """

    def __init__(self, model: str = "qwen2.5-coder:14b", ollama_url: str = OLLAMA_URL):
        self.model = model
        self.url = ollama_url.rstrip("/")

    def think(self, prompt: str) -> str:
        """
        Synchronous convenience. Calls the LLM and returns raw text.
        """
        result = self.chat(prompt)
        if result.get("error"):
            return f"[BRAIN ERROR] {result['error']}"
        return result.get("content", "")

    def think_json(self, prompt: str, system: Optional[str] = None) -> Dict[str, Any]:
        """
        Synchronous convenience. Calls the LLM in JSON mode and returns parsed JSON.
        """
        result = self.chat(prompt, system=system, format_json=True)
        if result.get("error"):
            return {"_error": result["error"]}
        try:
            return json.loads(result.get("content", "{}"))
        except json.JSONDecodeError as e:
            return {"_error": f"JSON parse failed: {e}", "_raw": result.get("content", "")}

    def chat(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        format_json: bool = False,
        temperature: float = 0.4,
        max_tokens: int = 1024,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a chat completion request to the local Ollama instance.
        Returns {"content": str} or {"error": str}.
        """
        chosen = model or self.model
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": chosen,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if format_json:
            payload["format"] = "json"

        try:
            with httpx.Client(timeout=90.0) as client:
                r = client.post(f"{self.url}/api/chat", json=payload)
                r.raise_for_status()
                data = r.json()
                content = data.get("message", {}).get("content", "")
                return {"content": content, "model": chosen}
        except httpx.ConnectError:
            msg = f"Ollama not reachable at {self.url}"
            log.error(f"[local_brain] {msg}")
            return {"error": msg}
        except Exception as e:
            log.error(f"[local_brain] call failed: {e}")
            return {"error": str(e)}
