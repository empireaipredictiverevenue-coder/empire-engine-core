"""
EMPIRE V49 · OMNICHANNEL ENGINE — Layer 3: AGENDA CONTROLLER
=============================================================
Scheduling, follow-up cadences, and omnichannel routing.

Takes classified leads and builds multi-channel outreach agendas:
  - SMS cadences (immediate, 24h, 72h, 7d)
  - Email sequences (via ListMonk campaigns)
  - Voice call scheduling (via Twenty CRM tasks)
  - Follow-up tracking and auto-escalation

Pipeline:
    Classified lead (with temperature + key_message)
        → Route to channel (SMS/email/voice) based on temperature
        → Build agenda entry with timing, channel, content
        → Sync agenda to Twenty CRM (tasks) + ListMonk (campaign)

Usage:
    agenda = AgendaController()
    items = await agenda.schedule_lead(lead)
    batch = await agenda.schedule_batch(classified_leads)
"""

import os
import json
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

log = logging.getLogger("empire.omni.agenda")

# ── Cadence definitions ───────────────────────────────────────────────

# Timing in hours from now for each follow-up step
CADENCES = {
    "hot": [
        {"step": 1, "channel": "sms",    "delay_hours": 0,   "label": "Immediate dispatch"},
        {"step": 2, "channel": "voice",  "delay_hours": 1,   "label": "Follow-up call"},
        {"step": 3, "channel": "email",  "delay_hours": 4,   "label": "Info packet email"},
        {"step": 4, "channel": "sms",    "delay_hours": 24,  "label": "24h check-in"},
        {"step": 5, "channel": "voice",  "delay_hours": 72,  "label": "72h re-engagement"},
    ],
    "warm": [
        {"step": 1, "channel": "email",  "delay_hours": 0,   "label": "Welcome email"},
        {"step": 2, "channel": "sms",    "delay_hours": 24,  "label": "Intro text"},
        {"step": 3, "channel": "email",  "delay_hours": 72,  "label": "Case study email"},
        {"step": 4, "channel": "sms",    "delay_hours": 168, "label": "7-day check-in"},
    ],
    "cold": [
        {"step": 1, "channel": "email",  "delay_hours": 0,   "label": "Drip campaign start"},
        {"step": 2, "channel": "email",  "delay_hours": 168, "label": "Weekly digest"},
        {"step": 3, "channel": "email",  "delay_hours": 336, "label": "Monthly re-engagement"},
    ],
}

# Channel routing based on temperature
ROUTING = {
    "hot":   ["sms", "voice", "email"],
    "warm":  ["email", "sms"],
    "cold":  ["email"],
}


class AgendaController:
    """Layer 3: Scheduling, follow-up cadences, and omnichannel routing.

    Builds agenda items with timing, channel, and content for each lead
    based on its temperature classification. Syncs to Twenty CRM as tasks
    and triggers ListMonk campaigns for email sequences.
    """

    def __init__(self):
        self.stats = {"scheduled": 0, "sms": 0, "email": 0, "voice": 0}

    # ── SCHEDULING ─────────────────────────────────────────────────────

    async def schedule_lead(self, lead: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build a multi-step agenda for a single classified lead.

        Returns a list of agenda items with {step, channel, scheduled_at, content, lead_id}.
        """
        temperature = lead.get("temperature", "cold")
        cadence = CADENCES.get(temperature, CADENCES["cold"])
        now = datetime.now(timezone.utc)
        key_msg = lead.get("key_message", "")
        name = lead.get("name", "Property Owner")

        items = []
        for step in cadence:
            scheduled_at = now + timedelta(hours=step["delay_hours"])
            channel = step["channel"]
            content = self._build_content(lead, step, key_msg)

            item = {
                "lead_id": lead.get("id", ""),
                "lead_name": name,
                "lead_phone": lead.get("phone", ""),
                "lead_email": lead.get("email", ""),
                "temperature": temperature,
                "step": step["step"],
                "label": step["label"],
                "channel": channel,
                "scheduled_at": scheduled_at.isoformat(),
                "delay_hours": step["delay_hours"],
                "content": content,
                "status": "pending",
            }
            items.append(item)
            self.stats[channel] = self.stats.get(channel, 0) + 1

        self.stats["scheduled"] += 1
        return items

    async def schedule_batch(self, leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Schedule agenda items for a batch of classified leads."""
        all_items = []
        for lead in leads:
            items = await self.schedule_lead(lead)
            all_items.extend(items)
        log.info(f"[agenda] scheduled {len(all_items)} items for {len(leads)} leads")
        return all_items

    def _build_content(self, lead: dict, step: dict, key_msg: str) -> str:
        """Build personalized outreach content for each step."""
        name = (lead.get("name") or "there").split()[0] if lead.get("name") else "there"
        channel = step["channel"]

        if channel == "sms":
            return key_msg or f"Hi {name}, storm damage detected in your area. Free inspection — reply YES."
        elif channel == "voice":
            return (
                f"Call {name} at {lead.get('phone', 'N/A')}. "
                f"Script: Introduce Empire AI, mention storm damage in {lead.get('city', 'their area')}, "
                f"offer free inspection. Handle objection: {lead.get('objection_handling', 'No cost — insurance covers it.')}"
            )
        elif channel == "email":
            return (
                f"Subject: Storm damage assessment for your property in {lead.get('city', 'your area')}\n\n"
                f"Hi {name},\n\n"
                f"{key_msg or 'We noticed recent storm activity in your area and wanted to reach out.'}\n\n"
                f"Our AI-powered platform connects you with vetted contractors who handle the entire "
                f"insurance claim process — at no cost to you.\n\n"
                f"Reply to this email or call us to schedule your free inspection.\n\n"
                f"– Empire AI"
            )
        return key_msg or ""

    # ── CRM SYNC ──────────────────────────────────────────────────────

    async def sync_agenda_to_twenty(self, items: List[dict], api_token: str = "") -> int:
        """Create Twenty CRM tasks from agenda items."""
        token = api_token or os.getenv("TWENTY_API_TOKEN", "")
        if not token:
            return 0

        import httpx
        created = 0
        async with httpx.AsyncClient(timeout=30) as client:
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            for item in items[:50]:  # batch limit
                try:
                    await client.post(
                        "http://localhost:3003/rest/tasks",
                        headers=headers,
                        json={
                            "title": f"[{item['temperature'].upper()}] {item['label']}: {item['lead_name'][:50]}",
                            "body": item.get("content", "")[:500],
                            "dueAt": item.get("scheduled_at", ""),
                            "status": "TODO",
                        },
                    )
                    created += 1
                except Exception:
                    pass

        log.info(f"[agenda] synced {created} tasks to Twenty CRM")
        return created

    def get_cadence_report(self, temperature: str = "") -> dict:
        """Return the cadence definition for a given temperature."""
        if temperature:
            return {"temperature": temperature, "cadence": CADENCES.get(temperature, CADENCES["cold"])}
        return {"temperatures": {t: len(c) for t, c in CADENCES.items()}, "routing": ROUTING}

    def snapshot(self) -> dict:
        return {
            "cadences": {t: len(c) for t, c in CADENCES.items()},
            "routing": ROUTING,
            **self.stats,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
