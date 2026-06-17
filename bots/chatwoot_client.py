"""
EMPIRE V49 · CHATWOOT CLIENT
==============================
Omnichannel messaging client for Chatwoot (open-source customer engagement
platform). Wires into Hermes controller as an additional messaging channel
alongside Telegram.

Supports:
  - List inboxes
  - Create/identify contacts
  - Create conversations
  - Send messages
  - Fetch conversation history

Configuration (env vars):
  CHATWOOT_URL              — Base URL (e.g. https://app.chatwoot.com or self-hosted)
  CHATWOOT_ACCESS_TOKEN     — API access token (from profile settings)
  CHATWOOT_ACCOUNT_ID       — Account ID (integer, from URL /accounts/:id)
  CHATWOOT_ENABLED          — Set "true" to enable (default: false)
"""

import os
import json
import logging
from typing import Optional

import httpx

log = logging.getLogger("empire.chatwoot")

# ── Configuration ──────────────────────────────────────────────────────

CHATWOOT_URL = os.environ.get("CHATWOOT_URL", "").rstrip("/")
CHATWOOT_ACCESS_TOKEN = os.environ.get("CHATWOOT_ACCESS_TOKEN", "")
CHATWOOT_ACCOUNT_ID = os.environ.get("CHATWOOT_ACCOUNT_ID", "")
CHATWOOT_ENABLED = os.environ.get("CHATWOOT_ENABLED", "false").lower() == "true"

# ── Chatwoot Client ───────────────────────────────────────────────────


class ChatwootClient:
    """HTTP client for Chatwoot's Application API.

    Uses an API access token for authentication. All methods return
    dicts with at minimum {"ok": True/False} and optionally "data" or "error".
    """

    def __init__(self):
        self._base_url = f"{CHATWOOT_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}"
        self._headers = {
            "api_access_token": CHATWOOT_ACCESS_TOKEN,
            "Content-Type": "application/json",
        }

    # ── Inboxes ──────────────────────────────────────────────────────

    async def list_inboxes(self) -> dict:
        """List all inboxes for this account."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    f"{self._base_url}/inboxes",
                    headers=self._headers,
                )
                r.raise_for_status()
                data = r.json()
                return {"ok": True, "inboxes": data.get("payload", []) if isinstance(data, dict) else data}
        except Exception as e:
            log.warning(f"[chatwoot] list_inboxes failed: {e}")
            return {"ok": False, "error": str(e)[:200]}

    # ── Contacts ─────────────────────────────────────────────────────

    async def create_contact(self, name: str, email: str = "", phone: str = "", inbox_id: int = None) -> dict:
        """Create or identify a contact.

        If a contact with the given email/phone exists, it returns the
        existing contact (upsert behavior via the API).
        """
        payload: dict = {
            "inbox_id": inbox_id,
            "name": name,
        }
        if email:
            payload["email"] = email
        if phone:
            payload["phone_number"] = phone

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(
                    f"{self._base_url}/contacts",
                    headers=self._headers,
                    json=payload,
                )
                r.raise_for_status()
                data = r.json()
                contact = data.get("payload", {}).get("contact", {})
                return {"ok": True, "contact": contact, "contact_id": contact.get("id")}
        except Exception as e:
            log.warning(f"[chatwoot] create_contact failed: {e}")
            return {"ok": False, "error": str(e)[:200]}

    async def list_contacts(self, page: int = 1) -> dict:
        """List contacts, paginated."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    f"{self._base_url}/contacts",
                    params={"page": page},
                    headers=self._headers,
                )
                r.raise_for_status()
                data = r.json()
                return {"ok": True, "contacts": data.get("payload", []), "meta": data.get("meta", {})}
        except Exception as e:
            log.warning(f"[chatwoot] list_contacts failed: {e}")
            return {"ok": False, "error": str(e)[:200]}

    # ── Conversations ────────────────────────────────────────────────

    async def create_conversation(self, contact_id: int, inbox_id: int, message: str = "") -> dict:
        """Create a new conversation for a contact in an inbox.

        Optionally starts with an initial message.
        """
        payload: dict = {
            "contact_id": contact_id,
            "inbox_id": inbox_id,
        }
        if message:
            payload["message"] = {
                "content": message,
                "message_type": "outgoing",
            }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(
                    f"{self._base_url}/conversations",
                    headers=self._headers,
                    json=payload,
                )
                r.raise_for_status()
                data = r.json()
                return {"ok": True, "conversation": data, "conversation_id": data.get("id")}
        except Exception as e:
            log.warning(f"[chatwoot] create_conversation failed: {e}")
            return {"ok": False, "error": str(e)[:200]}

    async def list_conversations(self, status: str = "open", page: int = 1) -> dict:
        """List conversations by status (open, resolved, all)."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    f"{self._base_url}/conversations",
                    params={"status": status, "page": page},
                    headers=self._headers,
                )
                r.raise_for_status()
                data = r.json()
                return {"ok": True, "conversations": data.get("data", []), "meta": data.get("meta", {})}
        except Exception as e:
            log.warning(f"[chatwoot] list_conversations failed: {e}")
            return {"ok": False, "error": str(e)[:200]}

    # ── Messages ─────────────────────────────────────────────────────

    async def send_message(self, conversation_id: int, content: str, message_type: str = "outgoing") -> dict:
        """Send a message to an existing conversation.

        message_type: "outgoing" (agent → contact) or "incoming" (contact → agent).
        """
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(
                    f"{self._base_url}/conversations/{conversation_id}/messages",
                    headers=self._headers,
                    json={
                        "content": content,
                        "message_type": message_type,
                    },
                )
                r.raise_for_status()
                data = r.json()
                return {"ok": True, "message": data, "message_id": data.get("id")}
        except Exception as e:
            log.warning(f"[chatwoot] send_message failed: {e}")
            return {"ok": False, "error": str(e)[:200]}

    # ── High-level helper: notify a contact ──────────────────────────

    async def notify(self, inbox_id: int, contact_name: str, message: str,
                     contact_email: str = "", contact_phone: str = "") -> dict:
        """High-level: ensure contact exists → create conversation → send message.

        Returns {"ok": True, "conversation_id": int, "message_id": int} or error.
        """
        # Step 1: Create/get contact
        contact_res = await self.create_contact(
            name=contact_name,
            email=contact_email,
            phone=contact_phone,
            inbox_id=inbox_id,
        )
        if not contact_res.get("ok"):
            return contact_res
        contact_id = contact_res["contact_id"]
        if not contact_id:
            return {"ok": False, "error": "no contact_id returned"}

        # Step 2: Create conversation
        conv_res = await self.create_conversation(
            contact_id=contact_id,
            inbox_id=inbox_id,
        )
        if not conv_res.get("ok"):
            return conv_res
        conversation_id = conv_res["conversation_id"]

        # Step 3: Send message
        msg_res = await self.send_message(
            conversation_id=conversation_id,
            content=message,
        )
        if not msg_res.get("ok"):
            return msg_res

        return {
            "ok": True,
            "conversation_id": conversation_id,
            "message_id": msg_res.get("message_id"),
        }


# ── Default singleton (lazy) ──────────────────────────────────────────

_default_client: Optional[ChatwootClient] = None


def get_chatwoot() -> Optional[ChatwootClient]:
    """Get or create the default ChatwootClient.

    Returns None if Chatwoot is not configured (CHATWOOT_ENABLED != true).
    """
    global _default_client
    if not CHATWOOT_ENABLED:
        return None
    if _default_client is None:
        if not all([CHATWOOT_URL, CHATWOOT_ACCESS_TOKEN, CHATWOOT_ACCOUNT_ID]):
            log.warning("[chatwoot] CHATWOOT_URL, CHATWOOT_ACCESS_TOKEN, and CHATWOOT_ACCOUNT_ID must be set")
            return None
        _default_client = ChatwootClient()
    return _default_client
