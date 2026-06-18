"""
EMPIRE V49 · SOVEREIGN CONSOLE
================================
The voice + text command bar that sits inside Empire. Press Cmd+K, speak
or type, system executes. Like Linear's command bar with voice on top.

ARCHITECTURE
────────────
  Operator says/types command
        ↓
  Claude · action router (LLM)
        ↓
  Returns structured action: {action: "approve_contractor", params: {...}}
        ↓
  Validate against allowed_actions registry
        ↓
  If destructive  → show preview, wait for operator confirmation
  If informational → execute immediately
        ↓
  Call the corresponding internal API
        ↓
  Stream the result back

SAFETY POSTURE
──────────────
Every action is registered with a `destructive` flag. Destructive actions
ALWAYS show a confirmation card before firing. The operator either
explicitly confirms (Enter/click) or cancels. No misheard voice command
can wire $50K USDC.

The router prompts Claude to return ONLY one of the registered actions —
never freeform code, never an arbitrary database write. This is the same
pattern OpenAI uses for function-calling: the LLM picks a function from
a typed schema, parameters get validated, then the function runs.

ACTIONS REGISTERED OUT OF THE BOX
─────────────────────────────────
INFORMATIONAL (execute immediately):
  show_hot_leads(metro?, limit?)
  show_funnel(days?)
  show_anomalies()
  show_today_summary()
  show_audit_log(operator_id?, limit?)
  show_contractor_leaderboard(limit?)
  show_inbound_calls(status?)
  show_pending_payouts()
  search_leads(query)

DESTRUCTIVE (require confirmation):
  approve_contractor(application_id)
  reject_contractor(application_id, reason?)
  pause_sms_sequence(phone)
  resume_sms_sequence(phone)
  trigger_dispatch(lead_id, urgency?)
  approve_payout(settlement_id)
  cancel_payout(payout_id, reason)
  send_test_sms(phone)
  invite_operator(email, name, role)

The action set is intentionally bounded. Operator wants something new?
Add it here. The LLM cannot call unregistered actions.


WIRE-UP IN hub.py
─────────────────
    from empire_console import (
        SovereignConsole,
        register_console_routes,
        CONSOLE_CLIENT_JS,
    )

    console = SovereignConsole(
        anthropic_key= os.environ.get("ANTHROPIC_API_KEY", ""),
        get_db=        get_db,
    )

    register_console_routes(
        app,
        console=      console,
        require_auth= require_auth,
        get_db=       get_db,
    )

    # Inject CONSOLE_CLIENT_JS into base_layout() so every operator page
    # has the Cmd+K bar available. Already wired into the layout below.
"""

import asyncio
import json
import time as _console_time
import logging
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional

import httpx
from fastapi import FastAPI, Request, Depends, HTTPException, Query

from observability.tracing import TraceContext


log = logging.getLogger("empire.console")


# ─────────────────────────────────────────────────────────────────────────────
# ACTION REGISTRY · the bounded set of things the console can do.
# Every action has: name, description, params schema, destructive flag,
# and the handler (resolved at runtime in execute_action).
# ─────────────────────────────────────────────────────────────────────────────
ACTIONS = {
    # ─────────────────── INFORMATIONAL ───────────────────────────────────
    "show_hot_leads": {
        "description": "Show the hottest leads ranked by urgency × freshness × asset value.",
        "params": {
            "metro": {"type": "string", "required": False, "description": "Filter by metro (e.g. 'Dallas')"},
            "limit": {"type": "integer", "required": False, "default": 10},
        },
        "destructive": False,
    },
    "show_funnel": {
        "description": "Show the conversion funnel: scraped → enrolled → contacted → replied → dispatched → settled.",
        "params": {
            "days": {"type": "integer", "required": False, "default": 7},
        },
        "destructive": False,
    },
    "show_anomalies": {
        "description": "Show current anomalies (stalled sequences, ghosted contractors, etc).",
        "params": {},
        "destructive": False,
    },
    "show_today_summary": {
        "description": "Show today's stats: strikes, brain GO decisions, dispatches accepted, fees earned.",
        "params": {},
        "destructive": False,
    },
    "show_pending_payouts": {
        "description": "Show payouts awaiting operator approval.",
        "params": {},
        "destructive": False,
    },
    "show_contractor_leaderboard": {
        "description": "Show top contractors by trust score and completed jobs.",
        "params": {
            "limit": {"type": "integer", "required": False, "default": 20},
        },
        "destructive": False,
    },
    "show_inbound_calls": {
        "description": "Show inbound calls awaiting follow-up.",
        "params": {
            "status": {"type": "string", "required": False, "default": "new"},
        },
        "destructive": False,
    },
    "search_leads": {
        "description": "Search radar_targets by address, city, phone, or email substring.",
        "params": {
            "query": {"type": "string", "required": True, "description": "Search text"},
        },
        "destructive": False,
    },
    "show_audit_log": {
        "description": "Show recent privileged actions and which operator performed them.",
        "params": {
            "limit": {"type": "integer", "required": False, "default": 25},
        },
        "destructive": False,
    },

    # ───────────────── DESTRUCTIVE (require confirmation) ────────────────
    "approve_contractor": {
        "description": "Approve a pending contractor application. Creates the contractor record.",
        "params": {
            "application_id": {"type": "string", "required": True},
        },
        "destructive": True,
        "min_role": "operator",
    },
    "reject_contractor": {
        "description": "Reject a pending contractor application.",
        "params": {
            "application_id": {"type": "string", "required": True},
            "reason": {"type": "string", "required": False},
        },
        "destructive": True,
        "min_role": "operator",
    },
    "pause_sms_sequence": {
        "description": "Pause the active SMS sequence for a phone number.",
        "params": {
            "phone": {"type": "string", "required": True},
        },
        "destructive": True,
        "min_role": "operator",
    },
    "resume_sms_sequence": {
        "description": "Resume a paused SMS sequence.",
        "params": {
            "phone": {"type": "string", "required": True},
        },
        "destructive": True,
        "min_role": "operator",
    },
    "trigger_dispatch": {
        "description": "Manually trigger dispatch fan-out for a lead. Matches contractors and emails them.",
        "params": {
            "lead_id": {"type": "string", "required": True},
            "urgency": {"type": "integer", "required": False, "default": 7},
        },
        "destructive": True,
        "min_role": "operator",
    },
    "approve_payout": {
        "description": "Approve all pending payouts for a settlement (owner-only).",
        "params": {
            "settlement_id": {"type": "string", "required": True},
        },
        "destructive": True,
        "min_role": "owner",
    },
    "cancel_payout": {
        "description": "Cancel a specific pending or approved payout (owner-only).",
        "params": {
            "payout_id": {"type": "string", "required": True},
            "reason": {"type": "string", "required": False, "default": "operator cancelled"},
        },
        "destructive": True,
        "min_role": "owner",
    },
    "invite_operator": {
        "description": "Invite a new operator account (owner-only).",
        "params": {
            "email": {"type": "string", "required": True},
            "name":  {"type": "string", "required": True},
            "role":  {"type": "string", "required": False, "default": "operator"},
        },
        "destructive": True,
        "min_role": "owner",
    },
    "run_synthetic_pipeline": {
        "description": "Run the autonomous Synthetic Intelligence media pipeline — LLM strategy → Kokoro TTS voiceover → FFmpeg video render → QC self-correction.",
        "params": {
            "objective": {"type": "string", "required": True, "description": "e.g. 'Build a high-impact roofing ad for Atlanta. Use +18885551234.'"},
        },
        "destructive": True,
        "min_role": "operator",
    },
    "update_lead_status": {
        "description": "Update an inbound lead's status (new, contacted, qualified, closed, rejected).",
        "params": {
            "lead_id": {"type": "string", "required": True, "description": "Lead UUID or ID"},
            "status":  {"type": "string", "required": True, "description": "new status (new, contacted, qualified, closed, rejected)"},
        },
        "destructive": True,
        "min_role": "operator",
    },

    # ───────────────── JARVIS: CONTENT GENERATION ────────────────────────
    "generate_storm_page": {
        "description": "Build an SEO-optimized storm damage landing page for any city/state metro. Auto-discovers live radar targets and generates JSON-LD structured data, FAQ, and keyword targeting.",
        "params": {
            "city":  {"type": "string", "required": True, "description": "City name, e.g. 'Dallas'"},
            "state": {"type": "string", "required": True, "description": "Two-letter state code, e.g. 'TX'"},
        },
        "destructive": False,
    },
    "show_system_status": {
        "description": "Show the status of all Empire AI systems: agents, services, lanes, revenue, and health checks in a single snapshot.",
        "params": {},
        "destructive": False,
    },
    "generate_predictive_report": {
        "description": "Generate a comprehensive predictive revenue report with per-lane forecasts, health alerts, SI evolution status, and AGI calibration analysis.",
        "params": {
            "days": {"type": "integer", "required": False, "default": 7, "description": "Number of days to analyze"},
        },
        "destructive": False,
    },
    "list_generated_pages": {
        "description": "List all generated storm landing pages with metadata, creation date, and URL.",
        "params": {},
        "destructive": False,
    },
    "recruit_contractor_affiliates": {
        "description": "Run the affiliate recruiter bot's contractor pipeline: find active contractors without affiliate links, enroll them, send welcome emails with referral links, and report results.",
        "params": {
            "limit": {"type": "integer", "required": False, "default": 20, "description": "Max contractors to enroll this cycle"},
        },
        "destructive": False,
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# THE CONSOLE ENGINE
# ─────────────────────────────────────────────────────────────────────────────
class SovereignConsole:
    """
    Routes natural language commands to structured actions via Claude.
    """

    def __init__(
        self,
        *,
        anthropic_key: str = "",
        get_db:        Callable,
        model:         str = "claude-sonnet-4-6",
        broadcaster:   Optional[object] = None,
    ):
        self.anthropic_key = anthropic_key
        self.get_db        = get_db
        self.model         = model
        self.broadcaster   = broadcaster
        self.enabled       = bool(anthropic_key)
        self.stats = {
            "commands_received": 0,
            "actions_resolved":  0,
            "actions_executed":  0,
            "actions_confirmed": 0,
            "actions_cancelled": 0,
            "router_errors":     0,
        }

    # ── PUBLIC: PARSE A COMMAND ──────────────────────────────────────────
    async def parse(self, command: str, operator_role: str = "viewer") -> dict:
        """
        Send a natural-language command to Claude. Return a structured action.

        Returns:
          {ok: bool, action: str, params: dict, destructive: bool, error?: str}
        """
        self.stats["commands_received"] += 1

        if not self.enabled:
            return {"ok": False, "error": "Claude not configured (no ANTHROPIC_API_KEY)"}

        command = (command or "").strip()
        if not command:
            return {"ok": False, "error": "Empty command"}

        # Filter actions visible to this role
        visible_actions = self._actions_for_role(operator_role)

        # Build the system prompt
        action_specs = []
        for name, spec in visible_actions.items():
            params_desc = ", ".join(
                f"{p_name}: {p_def.get('type','any')}{' (required)' if p_def.get('required') else ''}"
                for p_name, p_def in spec.get("params", {}).items()
            ) or "no parameters"
            tag = " [DESTRUCTIVE]" if spec.get("destructive") else ""
            action_specs.append(f"  • {name}{tag} — {spec['description']}\n      params: {params_desc}")

        system_prompt = (
            "You are the action router for the Empire AI autonomous revenue engine. "
            "Your job is to translate an operator's natural-language command into ONE structured "
            "action from the allowed set below.\n\n"
            "ALLOWED ACTIONS:\n"
            + "\n".join(action_specs)
            + "\n\nRULES:\n"
            "1. Return ONLY a JSON object with this exact shape:\n"
            '   {"action": "<action_name>", "params": {<param_name>: <value>}, "explanation": "<one sentence>"}\n'
            "2. The action MUST be one of the names above. Do not invent new ones.\n"
            "3. If you cannot map the command to an allowed action, return:\n"
            '   {"action": null, "params": {}, "explanation": "<reason in plain English>"}\n'
            "4. For destructive actions, include enough params to execute unambiguously. "
            "If params are ambiguous (e.g. 'approve the contractor' without specifying which), "
            "return action: null and explain what's missing.\n"
            "5. Do not return surrounding prose or markdown — JSON only."
        )

        user_prompt = f'Operator command: "{command}"'

        try:
            _start = _console_time.time()
            async with TraceContext(
                name="console.claude_parse",
                model=self.model,
                input=user_prompt[:2000],
                system=system_prompt[:500],
                task="console.parse",
                tags=["provider:anthropic", f"model:{self.model}", "source:empire_console"],
            ) as ctx:
                async with httpx.AsyncClient(timeout=20) as c:
                    r = await c.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "x-api-key":         self.anthropic_key,
                            "anthropic-version": "2023-06-01",
                            "Content-Type":      "application/json",
                        },
                        json={
                            "model":      self.model,
                            "max_tokens": 400,
                            "system":     system_prompt,
                            "messages":   [{"role": "user", "content": user_prompt}],
                        },
                    )
                    if r.status_code != 200:
                        log.warning(f"[console] Claude HTTP {r.status_code}: {r.text[:200]}")
                        self.stats["router_errors"] += 1
                        ctx.set_output(error=f"HTTP {r.status_code}: {r.text[:200]}")
                        return {"ok": False, "error": f"router error · HTTP {r.status_code}"}
                    body = r.json()
                    text = body.get("content", [{}])[0].get("text", "")
                    elapsed = int((_console_time.time() - _start) * 1000)
                    # Estimate tokens: ~4 chars per token for Claude
                    tokens_in = body.get("usage", {}).get("input_tokens", 0)
                    tokens_out = body.get("usage", {}).get("output_tokens", 0)
                    ctx.set_output(
                        output=text[:1000],
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        latency_ms=elapsed,
                    )

            # Parse the JSON
            import re
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                return {"ok": False, "error": "router did not return JSON"}
            parsed = json.loads(match.group(0))

            action_name = parsed.get("action")
            if not action_name:
                return {
                    "ok":          False,
                    "error":       parsed.get("explanation", "Command not understood"),
                    "explanation": parsed.get("explanation", ""),
                }

            if action_name not in visible_actions:
                return {
                    "ok":          False,
                    "error":       f"Action '{action_name}' is not allowed for role '{operator_role}'",
                }

            spec = visible_actions[action_name]
            self.stats["actions_resolved"] += 1

            return {
                "ok":          True,
                "action":      action_name,
                "params":      parsed.get("params", {}),
                "destructive": spec.get("destructive", False),
                "explanation": parsed.get("explanation", ""),
                "description": spec.get("description", ""),
            }
        except json.JSONDecodeError as e:
            log.warning(f"[console] JSON parse failed: {e}")
            return {"ok": False, "error": "could not parse router response"}
        except Exception as e:
            log.error(f"[console] parse error: {e}")
            self.stats["router_errors"] += 1
            return {"ok": False, "error": str(e)}

    # ── PUBLIC: EXECUTE A RESOLVED ACTION ────────────────────────────────
    async def execute(
        self,
        *,
        action_name: str,
        params: dict,
        operator: dict,
        services: dict,
    ) -> dict:
        """
        Run the action. `services` is a dict of injected services
        (matcher, sms_engine, email_engine, etc) provided by the wiring layer.

        Returns: {ok, result | error}
        """
        if action_name not in ACTIONS:
            return {"ok": False, "error": f"unknown action: {action_name}"}

        spec = ACTIONS[action_name]

        # Role check
        op_role = operator.get("role", "viewer")
        op_level = {"owner": 3, "operator": 2, "viewer": 1}.get(op_role, 0)
        min_role = spec.get("min_role", "viewer")
        min_level = {"owner": 3, "operator": 2, "viewer": 1}[min_role]
        if op_level < min_level:
            return {"ok": False, "error": f"requires {min_role} role"}

        try:
            result = await self._dispatch(action_name, params, services)
            self.stats["actions_executed"] += 1
            return {"ok": True, "result": result}
        except Exception as e:
            log.error(f"[console] execute {action_name} failed: {e}")
            return {"ok": False, "error": str(e)}

    # ─────────────────────────────────────────────────────────────────────
    # INTERNALS
    # ─────────────────────────────────────────────────────────────────────
    def _actions_for_role(self, role: str) -> dict:
        """Return only the actions this role is allowed to invoke."""
        op_level = {"owner": 3, "operator": 2, "viewer": 1}.get(role, 0)
        visible = {}
        for name, spec in ACTIONS.items():
            min_role = spec.get("min_role", "viewer")
            min_level = {"owner": 3, "operator": 2, "viewer": 1}[min_role]
            if op_level >= min_level:
                visible[name] = spec
        return visible

    async def _dispatch(self, action_name: str, params: dict, services: dict) -> dict:
        """Route to the right handler."""
        db = self.get_db()

        # ── INFORMATIONAL ────────────────────────────────────────────────
        if action_name == "show_hot_leads":
            metro = params.get("metro")
            limit = int(params.get("limit", 10))
            q = db.table("radar_targets").select(
                "id, address, phone, email, city, urgency_score, damage_severity, created_at"
            ).eq("status", "active").order("urgency_score", desc=True).limit(limit)
            if metro:
                q = q.ilike("city", f"%{metro}%")
            return {"type": "list", "title": "Hot leads", "rows": q.execute().data or []}

        if action_name == "show_funnel":
            days = int(params.get("days", 7))
            since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            counts = {}
            for table, label in [
                ("radar_targets", "Scraped"),
                ("sms_sequences", "SMS Enrolled"),
                ("email_sequences", "Email Enrolled"),
                ("dispatches", "Dispatched"),
                ("claim_outcomes", "Outcomes Recorded"),
            ]:
                try:
                    r = db.table(table).select("id", count="exact") \
                        .gte("created_at", since).execute()
                    counts[label] = r.count or 0
                except Exception:
                    counts[label] = 0
            return {"type": "stats", "title": f"Funnel · {days}d", "stats": counts}

        if action_name == "show_today_summary":
            today_start = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ).isoformat()
            stats = {}
            for table, label in [
                ("strike_log", "Strikes"),
                ("brain_decisions", "Brain decisions"),
                ("dispatches", "Dispatches sent"),
            ]:
                try:
                    r = db.table(table).select("id", count="exact") \
                        .gte("created_at", today_start).execute()
                    stats[label] = r.count or 0
                except Exception:
                    stats[label] = 0
            try:
                r = db.table("claim_outcomes").select("actual_fee") \
                    .eq("outcome", "settled") \
                    .gte("created_at", today_start).execute()
                fees = sum(float(row.get("actual_fee") or 0) for row in (r.data or []))
                stats["Fees earned"] = f"${fees:,.0f}"
            except Exception:
                stats["Fees earned"] = "$0"
            return {"type": "stats", "title": "Today", "stats": stats}

        if action_name == "show_anomalies":
            try:
                r = db.table("sms_sequences").select("id, phone, last_sent_at, current_step") \
                    .eq("status", "active") \
                    .lte("last_sent_at", (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()) \
                    .limit(10).execute()
                rows = [{"type": "stalled_sms", "phone": x["phone"], "step": x["current_step"]} for x in (r.data or [])]
            except Exception:
                rows = []
            return {"type": "list", "title": "Anomalies", "rows": rows}

        if action_name == "show_pending_payouts":
            try:
                r = db.table("payout_log").select(
                    "id, settlement_id, recipient_type, recipient_wallet, amount_usdc, meta"
                ).eq("status", "pending").neq("recipient_type", "vault") \
                    .order("created_at", desc=True).limit(50).execute()
                return {"type": "list", "title": "Pending payouts", "rows": r.data or []}
            except Exception as e:
                return {"type": "error", "error": str(e)}

        if action_name == "show_contractor_leaderboard":
            limit = int(params.get("limit", 20))
            r = db.table("contractors").select(
                "id, name, metro, trust_score, completed_jobs, specialties"
            ).eq("active", True).order("trust_score", desc=True).limit(limit).execute()
            return {"type": "list", "title": "Contractor leaderboard", "rows": r.data or []}

        if action_name == "show_inbound_calls":
            status = params.get("status", "new")
            q = db.table("inbound_calls").select(
                "id, from_number, transcript, urgency_score, intent, created_at"
            ).order("urgency_score", desc=True).order("created_at", desc=True).limit(25)
            if status != "all":
                q = q.eq("status", status)
            return {"type": "list", "title": f"Inbound calls · {status}", "rows": q.execute().data or []}

        if action_name == "search_leads":
            q = params.get("query", "").strip()
            if not q:
                return {"type": "error", "error": "query required"}
            res = db.table("radar_targets").select(
                "id, address, phone, email, city, urgency_score, status"
            ).ilike("address", f"%{q}%").limit(20).execute()
            return {"type": "list", "title": f"Search · {q}", "rows": res.data or []}

        if action_name == "show_audit_log":
            limit = int(params.get("limit", 25))
            r = db.table("audit_log").select("*").order("created_at", desc=True).limit(limit).execute()
            return {"type": "list", "title": "Audit log", "rows": r.data or []}

        # ── DESTRUCTIVE ──────────────────────────────────────────────────
        if action_name == "approve_contractor":
            app_id = params.get("application_id")
            if not app_id:
                return {"ok": False, "error": "application_id required"}
            # Delegate to the existing contractor approval flow (we re-use
            # the route via internal call rather than re-implementing logic)
            return {"type": "action", "delegated_to": "/api/v1/contractors/approve",
                    "body": {"application_id": app_id}}

        if action_name == "reject_contractor":
            return {"type": "action", "delegated_to": "/api/v1/contractors/reject",
                    "body": {
                        "application_id": params.get("application_id"),
                        "reason": params.get("reason", "Rejected via console"),
                    }}

        if action_name == "pause_sms_sequence":
            phone = self._normalize_phone(params.get("phone", ""))
            if not phone:
                return {"ok": False, "error": "valid phone required"}
            db.table("sms_sequences").update({"status": "paused"}).eq("phone", phone).execute()
            return {"type": "ok", "message": f"Paused SMS sequence for {phone}"}

        if action_name == "resume_sms_sequence":
            phone = self._normalize_phone(params.get("phone", ""))
            if not phone:
                return {"ok": False, "error": "valid phone required"}
            db.table("sms_sequences").update({"status": "active"}).eq("phone", phone).execute()
            return {"type": "ok", "message": f"Resumed SMS sequence for {phone}"}

        if action_name == "trigger_dispatch":
            return {"type": "action", "delegated_to": "/api/v1/matching/dispatch",
                    "body": {
                        "lead_id": params.get("lead_id"),
                        "urgency": int(params.get("urgency", 7)),
                    }}

        if action_name == "approve_payout":
            return {"type": "action", "delegated_to": "/api/v1/payouts/approve",
                    "body": {"settlement_id": params.get("settlement_id")}}

        if action_name == "cancel_payout":
            return {"type": "action", "delegated_to": "/api/v1/payouts/cancel",
                    "body": {
                        "payout_id": params.get("payout_id"),
                        "reason":    params.get("reason", "operator cancelled"),
                    }}

        if action_name == "invite_operator":
            return {"type": "action", "delegated_to": "/api/v1/auth/invite",
                    "body": {
                        "email": params.get("email"),
                        "name":  params.get("name"),
                        "role":  params.get("role", "operator"),
                    }}

        if action_name == "run_synthetic_pipeline":
            objective = params.get("objective", "").strip()
            if not objective:
                return {"type": "error", "error": "objective required (e.g. 'Build a roofing ad for Atlanta')"}
            return {"type": "action", "delegated_to": "/api/v1/synthetic/run",
                    "body": {"objective": objective}}

        if action_name == "update_lead_status":
            lead_id = params.get("lead_id", "").strip()
            status = params.get("status", "").strip().lower()
            if not lead_id or not status:
                return {"type": "error", "error": "lead_id and status required (e.g. 'mark lead abc123 as contacted')"}
            if status not in ("new", "contacted", "qualified", "closed", "rejected"):
                return {"type": "error", "error": f"invalid status '{status}' — must be new, contacted, qualified, closed, or rejected"}
            return {"type": "action", "delegated_to": "/api/v1/inbound/leads/update",
                    "body": {"lead_id": lead_id, "status": status}}

        # ── JARVIS: GENERATE STORM PAGE ───────────────────────────────────
        if action_name == "generate_storm_page":
            city = params.get("city", "").strip()
            state = params.get("state", "").strip().upper()
            if not city or not state:
                return {"type": "error", "error": "city and state are required (e.g. 'Dallas, TX')"}
            if len(state) != 2 or not state.isalpha():
                return {"type": "error", "error": f"state must be a 2-letter code, got '{state}'"}
            # Generate the page using empire_storm_landing
            from empire_storm_landing import _slugify, storm_landing_page
            slug = _slugify(city, state)
            # Render via thread pool to avoid blocking the event loop
            page_html = await asyncio.to_thread(
                storm_landing_page, city=city, state=state, slug=slug, get_db=self.get_db
            )
            # Log to generated_pages table
            try:
                db = self.get_db()
                db.table("generated_pages").insert({
                    "slug": slug,
                    "page_type": "storm_landing",
                    "city": city,
                    "state": state,
                    "url": f"/storm/{slug}",
                    "html_length": len(page_html),
                    "status": "active",
                }).execute()
            except Exception as log_e:
                log.debug(f"[console] log generated_page: {log_e}")
            # Broadcast to live dashboards
            if hasattr(self, 'broadcaster') and self.broadcaster:
                try:
                    asyncio.create_task(self.broadcaster.broadcast({
                        "type": "page_generated",
                        "slug": slug,
                        "city": city,
                        "state": state,
                        "page_type": "storm_landing",
                    }))
                except Exception:
                    pass
            return {
                "type": "page_generated",
                "title": f"Storm landing page for {city}, {state}",
                "slug": slug,
                "url": f"/storm/{slug}",
                "city": city,
                "state": state,
                "html_size": len(page_html),
                "message": f"✅ Built storm landing page for {city}, {state} at /storm/{slug}",
            }

        # ── JARVIS: SHOW SYSTEM STATUS ───────────────────────────────────
        if action_name == "show_system_status":
            try:
                db = self.get_db()
                status_data = {}
                # Agent registry status
                try:
                    r = db.table("agent_registry").select("agent_name,status,last_ping,role_name") \
                        .order("agent_name").limit(50).execute()
                    status_data["agents"] = [
                        {"name": a.get("agent_name", "?"), "status": a.get("status", "?"),
                         "role": a.get("role_name", "?"), "last_ping": (a.get("last_ping") or "")[:16]}
                        for a in (r.data or [])
                    ]
                except Exception:
                    status_data["agents"] = []
                # Active lanes
                try:
                    from mesh_orchestrator import LANES
                    lane_count = len(LANES)
                except Exception:
                    lane_count = 32
                # Revenue
                try:
                    from bots import predictive_revenue
                    fc = predictive_revenue.per_lane_forecast() or {}
                    rev_totals = fc.get("totals", {})
                    rev_health = fc.get("health", {})
                    status_data["revenue"] = {
                        "revenue_24h": rev_totals.get("revenue_24h", 0),
                        "mrr_projected": rev_totals.get("mrr_projected", 0),
                        "active_buyers": rev_totals.get("active_buyers", 0),
                        "lanes_active": rev_totals.get("lanes_active", 0),
                        "health": rev_health.get("status", "unknown"),
                    }
                except Exception:
                    status_data["revenue"] = {}
                # Storm pages count
                try:
                    r = db.table("generated_pages").select("id", count="exact") \
                        .eq("status", "active").execute()
                    status_data["storm_pages"] = r.count or 0
                except Exception:
                    status_data["storm_pages"] = 0
                # Bridge sessions
                try:
                    r = db.table("bridge_sessions").select("id", count="exact") \
                        .is_("ended_at", "null").execute()
                    status_data["active_sessions"] = r.count or 0
                except Exception:
                    status_data["active_sessions"] = 0

                return {
                    "type": "system_status",
                    "title": "Empire AI System Status",
                    "status": status_data,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }
            except Exception as e:
                return {"type": "error", "error": f"status fetch failed: {e}"}

        # ── JARVIS: GENERATE PREDICTIVE REPORT ───────────────────────────
        if action_name == "generate_predictive_report":
            days = int(params.get("days", 7))
            try:
                from bots import predictive_revenue
                fc = predictive_revenue.comprehensive_forecast() or {}
                narrative = fc.get("narrative", {})
                per_lane = fc.get("per_lane", {})
                health = fc.get("health", {})
                sms_signal = fc.get("sms_log_signal", {})

                return {
                    "type": "predictive_report",
                    "title": f"Predictive Revenue Report · {days}d",
                    "executive_summary": narrative.get("executive_summary", "No narrative available"),
                    "totals": per_lane.get("totals", {}),
                    "health": health,
                    "sms_signal": {
                        "global_reply_rate": sms_signal.get("global_reply_rate", 0),
                        "sent_24h": sms_signal.get("sent_24h", 0),
                        "replied_24h": sms_signal.get("replied_24h", 0),
                        "samples": sms_signal.get("samples", 0),
                    },
                    "narrative_highlights": narrative.get("lane_highlights", []),
                    "risks": narrative.get("risks", []),
                    "advice": narrative.get("actionable_advice", ""),
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }
            except Exception as e:
                return {"type": "error", "error": f"report generation failed: {e}"}

        # ── JARVIS: LIST GENERATED PAGES ─────────────────────────────────
        if action_name == "list_generated_pages":
            try:
                db = self.get_db()
                r = db.table("generated_pages").select("slug,page_type,city,state,url,status,created_at") \
                    .order("created_at", desc=True).limit(50).execute()
                pages = [
                    {
                        "slug": p.get("slug", ""),
                        "type": p.get("page_type", ""),
                        "city": p.get("city", ""),
                        "state": p.get("state", ""),
                        "url": p.get("url", ""),
                        "status": p.get("status", ""),
                        "created": (p.get("created_at") or "")[:16],
                    }
                    for p in (r.data or [])
                ]
                return {
                    "type": "list",
                    "title": f"Generated Pages ({len(pages)})",
                    "rows": pages,
                }
            except Exception as e:
                return {"type": "error", "error": f"list failed: {e}"}

        # ── JARVIS: RECRUIT CONTRACTOR AFFILIATES ────────────────────────────
        if action_name == "recruit_contractor_affiliates":
            limit = int(params.get("limit", 20))
            try:
                from bots.affiliate_recruiter import AffiliateRecruiter
                recruiter = AffiliateRecruiter()
                # Run the contractor-specific prospect cycle
                results = await recruiter.run_cycle()
                # Get a pipeline snapshot
                snap = recruiter.snapshot()
                return {
                    "type": "list",
                    "title": f"Contractor Affiliate Recruitment · {results.get('enrolled', 0)} enrolled",
                    "rows": [
                        {"label": "Buyers found", "value": results.get("buyers_found", 0)},
                        {"label": "Contractors found", "value": results.get("contractors_found", 0)},
                        {"label": "Affiliates enrolled", "value": results.get("enrolled", 0)},
                        {"label": "Welcome emails sent", "value": results.get("welcomes_sent", 0)},
                        {"label": "Nurture emails sent", "value": results.get("nurtures_sent", 0)},
                    ],
                    "snapshot": {
                        "total_affiliates": snap.get("pipeline", {}).get("total_affiliates", 0),
                        "active_affiliates": snap.get("pipeline", {}).get("active_affiliates", 0),
                        "remaining_buyer_targets": snap.get("pipeline", {}).get("remaining_buyer_targets", 0),
                    },
                    "message": f"Cycle complete. {results.get('enrolled', 0)} new affiliates enrolled, {results.get('welcomes_sent', 0)} welcome emails sent.",
                }
            except Exception as e:
                log.warning(f"[console] recruit_contractor_affiliates failed: {e}")
                return {"type": "error", "error": f"Affiliate recruitment failed: {e}"}

        return {"type": "error", "error": f"action handler not implemented: {action_name}"}

    def _normalize_phone(self, phone: str) -> str:
        import re
        digits = re.sub(r"\D", "", phone or "")
        if len(digits) == 10:
            return f"+1{digits}"
        if len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"
        if phone and phone.startswith("+"):
            return phone
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI ROUTES
# ─────────────────────────────────────────────────────────────────────────────
def register_console_routes(
    app: FastAPI,
    *,
    console: SovereignConsole,
    require_auth: Callable,
    get_db: Callable,
):
    """Wire the console endpoints."""

    @app.post("/api/v1/console/parse")
    async def console_parse(
        request: Request,
        op: dict = Depends(require_auth),
    ):
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")
        command = body.get("command", "")
        result = await console.parse(command, operator_role=op.get("role", "viewer"))
        return result

    @app.post("/api/v1/console/execute")
    async def console_execute(
        request: Request,
        op: dict = Depends(require_auth),
    ):
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")
        action = body.get("action")
        params = body.get("params", {}) or {}
        if not action:
            raise HTTPException(400, "action required")
        result = await console.execute(
            action_name=action,
            params=params,
            operator=op,
            services={},   # services injected if needed
        )
        # If this was a destructive confirmed action, log to audit
        if action in ACTIONS and ACTIONS[action].get("destructive"):
            console.stats["actions_confirmed"] += 1
        return result

    @app.get("/api/v1/console/actions")
    async def console_actions(op: dict = Depends(require_auth)):
        """Returns the action set visible to this operator's role."""
        visible = console._actions_for_role(op.get("role", "viewer"))
        # Strip the handler fields, return just the spec
        return {
            "actions": [
                {
                    "name":        name,
                    "description": spec["description"],
                    "params":      spec.get("params", {}),
                    "destructive": spec.get("destructive", False),
                    "min_role":    spec.get("min_role", "viewer"),
                }
                for name, spec in visible.items()
            ]
        }

    @app.get("/api/v1/console/stats")
    async def console_stats(op: dict = Depends(require_auth)):
        return console.stats

    log.info("[console] Routes registered · /api/v1/console/{parse,execute,actions,stats}")


# ─────────────────────────────────────────────────────────────────────────────
# CLIENT-SIDE JS · the Cmd+K command bar overlay
# Inject into base_layout() so every operator page has it.
# ─────────────────────────────────────────────────────────────────────────────
CONSOLE_CLIENT_JS = r"""
<style>
.sov-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(3, 8, 16, 0.85);
  backdrop-filter: blur(12px);
  display: none;
  align-items: flex-start; justify-content: center;
  padding-top: 12vh;
  animation: sovFadeIn 0.15s ease-out;
}
.sov-overlay.open { display: flex; }
@keyframes sovFadeIn { from {opacity:0;} to {opacity:1;} }

.sov-panel {
  width: min(680px, 92vw);
  background: #15263F;
  border: 1px solid rgba(122,140,163,0.24);
  box-shadow: 0 30px 80px rgba(0,0,0,0.55);
  font-family: 'Geist','Inter',sans-serif;
  color: #F8FAFD;
  letter-spacing: -0.02em;
}

.sov-input-row {
  display: flex; align-items: center; gap: 14px;
  padding: 18px 22px;
  border-bottom: 1px solid rgba(122,140,163,0.18);
}
.sov-icon {
  width: 18px; height: 18px; flex-shrink: 0;
  color: #44E5B8;
  font-family: 'JetBrains Mono', monospace; font-size: 18px;
  display: flex; align-items: center; justify-content: center;
}
.sov-icon.listening {
  color: #5AC8FA;
  animation: sovPulse 1.2s ease-in-out infinite;
}
@keyframes sovPulse { 0%,100%{opacity:1;} 50%{opacity:0.4;} }

.sov-input {
  flex: 1;
  background: transparent; border: none; outline: none;
  color: #F8FAFD; font-size: 18px;
  font-family: 'Geist','Inter',sans-serif;
  letter-spacing: -0.02em;
}
.sov-input::placeholder { color: #4A5A72; }

.sov-mic-btn {
  background: rgba(68,229,184,0.08);
  border: 1px solid rgba(68,229,184,0.22);
  color: #44E5B8;
  font-family: 'JetBrains Mono', monospace; font-size: 10px;
  letter-spacing: 0.18em; text-transform: uppercase;
  padding: 7px 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.sov-mic-btn:hover { background: rgba(68,229,184,0.15); }
.sov-mic-btn.listening {
  color: #5AC8FA; border-color: rgba(90,200,250,0.4);
  background: rgba(90,200,250,0.1);
}
.sov-kbd {
  font-family: 'JetBrains Mono', monospace; font-size: 10px;
  color: #4A5A72; letter-spacing: 0.12em;
}

.sov-status {
  padding: 12px 22px;
  font-family: 'JetBrains Mono', monospace; font-size: 11px;
  color: #7A8CA3; letter-spacing: 0.04em;
  min-height: 44px;
  display: flex; align-items: center;
  border-bottom: 1px solid rgba(122,140,163,0.08);
}
.sov-status.error { color: #f43f5e; }
.sov-status.confirm { color: #f59e0b; }

.sov-preview {
  padding: 16px 22px;
  background: rgba(68,229,184,0.04);
  border-bottom: 1px solid rgba(68,229,184,0.15);
  display: none;
}
.sov-preview.show { display: block; }
.sov-preview.destructive {
  background: rgba(245,166,35,0.06);
  border-bottom-color: rgba(245,166,35,0.25);
}

.sov-preview-action {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px; color: #44E5B8;
  letter-spacing: 0.14em; text-transform: uppercase;
  margin-bottom: 6px;
}
.sov-preview.destructive .sov-preview-action { color: #f59e0b; }

.sov-preview-explanation {
  font-size: 14px; color: #F8FAFD;
  line-height: 1.6; margin-bottom: 10px;
}

.sov-preview-params {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px; color: #7A8CA3; line-height: 1.6;
  background: rgba(0,0,0,0.3);
  padding: 10px 12px;
  margin-bottom: 14px;
  white-space: pre-wrap;
}

.sov-preview-actions {
  display: flex; gap: 10px;
}
.sov-btn {
  font-family: 'Geist', 'Inter', sans-serif;
  font-weight: 600; font-size: 13px;
  padding: 9px 18px;
  cursor: pointer;
  letter-spacing: -0.01em;
  transition: all 0.15s;
  border: none;
}
.sov-btn-confirm {
  background: #44E5B8; color: #000;
}
.sov-btn-confirm.destructive { background: #f59e0b; }
.sov-btn-confirm:hover { transform: translateY(-1px); }
.sov-btn-cancel {
  background: transparent; color: #7A8CA3;
  border: 1px solid rgba(122,140,163,0.25);
}
.sov-btn-cancel:hover { color: #F8FAFD; }

.sov-result {
  padding: 16px 22px;
  max-height: 50vh; overflow-y: auto;
}
.sov-result-title {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px; color: #7A8CA3;
  letter-spacing: 0.18em; text-transform: uppercase;
  margin-bottom: 12px;
}
.sov-result-stats {
  display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px;
}
.sov-stat {
  background: rgba(255,255,255,0.02);
  border-left: 2px solid #44E5B8;
  padding: 10px 12px;
}
.sov-stat-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px; color: #7A8CA3;
  letter-spacing: 0.18em; text-transform: uppercase;
  margin-bottom: 4px;
}
.sov-stat-value {
  font-family: 'Geist Mono', monospace;
  font-weight: 600; font-size: 18px;
  color: #F8FAFD;
}

.sov-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 9px 12px;
  margin-bottom: 4px;
  background: rgba(255,255,255,0.02);
  font-size: 12px;
}
.sov-row-main { color: #F8FAFD; font-weight: 500; }
.sov-row-meta { color: #7A8CA3; font-family: 'JetBrains Mono', monospace; font-size: 10px; }

.sov-footer {
  padding: 10px 22px;
  border-top: 1px solid rgba(122,140,163,0.12);
  display: flex; justify-content: space-between;
  font-family: 'JetBrains Mono', monospace; font-size: 9px;
  color: #4A5A72; letter-spacing: 0.14em; text-transform: uppercase;
}
.sov-footer kbd {
  display: inline-block;
  padding: 2px 6px;
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(122,140,163,0.2);
  font-family: inherit; font-size: 9px;
  color: #C8D4E4;
  margin: 0 2px;
}
</style>

<div class="sov-overlay" id="sov-overlay" role="dialog" aria-label="Empire Sovereign Console">
  <div class="sov-panel">
    <div class="sov-input-row">
      <span class="sov-icon" id="sov-icon">›</span>
      <input class="sov-input" id="sov-input" type="text"
        placeholder="Type or speak a command · e.g. show hottest leads in Dallas"
        autocomplete="off" spellcheck="false">
      <button class="sov-mic-btn" id="sov-mic" type="button" aria-label="Toggle voice">
        <span id="sov-mic-label">🎙 voice</span>
      </button>
      <span class="sov-kbd">ESC</span>
    </div>
    <div class="sov-status" id="sov-status">Press Enter to send · ⌘K to close</div>
    <div class="sov-preview" id="sov-preview"></div>
    <div class="sov-result" id="sov-result" style="display:none;"></div>
    <div class="sov-footer">
      <span>EMPIRE · SOVEREIGN CONSOLE</span>
      <span>
        <kbd>⌘K</kbd> open · <kbd>Enter</kbd> send · <kbd>Esc</kbd> close
      </span>
    </div>
  </div>
</div>

<script>
(function() {
  const TOKEN = window.EMPIRE_TOKEN || localStorage.getItem('hub_token') || '';
  const overlay = document.getElementById('sov-overlay');
  const input   = document.getElementById('sov-input');
  const status  = document.getElementById('sov-status');
  const preview = document.getElementById('sov-preview');
  const result  = document.getElementById('sov-result');
  const micBtn  = document.getElementById('sov-mic');
  const micLabel= document.getElementById('sov-mic-label');
  const icon    = document.getElementById('sov-icon');
  let pendingAction = null;
  let recognition = null;
  let listening = false;

  function openConsole() {
    overlay.classList.add('open');
    setTimeout(() => input.focus(), 50);
    setStatus('Press Enter to send · ⌘K to close');
  }
  function closeConsole() {
    overlay.classList.remove('open');
    input.value = '';
    preview.classList.remove('show', 'destructive');
    preview.innerHTML = '';
    result.style.display = 'none';
    result.innerHTML = '';
    pendingAction = null;
    if (listening) toggleVoice();
  }
  function setStatus(msg, cls = '') {
    status.className = 'sov-status ' + cls;
    status.textContent = msg;
  }

  // Keyboard handler
  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      if (overlay.classList.contains('open')) closeConsole();
      else openConsole();
    } else if (e.key === 'Escape' && overlay.classList.contains('open')) {
      closeConsole();
    }
  });

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) closeConsole();
  });

  // Submit handler
  input.addEventListener('keydown', async (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      const cmd = input.value.trim();
      if (!cmd) return;
      await runCommand(cmd);
    }
  });

  async function runCommand(cmd) {
    setStatus('Thinking...');
    preview.classList.remove('show', 'destructive');
    result.style.display = 'none';
    try {
      const r = await fetch('/api/v1/console/parse', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + TOKEN,
        },
        body: JSON.stringify({ command: cmd }),
      });
      const d = await r.json();
      if (!d.ok) {
        setStatus('✗ ' + (d.error || 'Command not understood'), 'error');
        return;
      }

      // Show preview for destructive, auto-execute for informational
      if (d.destructive) {
        showConfirmation(d);
      } else {
        await executeAction(d.action, d.params);
      }
    } catch (e) {
      setStatus('✗ Network error', 'error');
    }
  }

  function showConfirmation(d) {
    pendingAction = d;
    setStatus('⚠ Destructive action · review and confirm', 'confirm');
    preview.classList.add('show', 'destructive');
    preview.innerHTML = `
      <div class="sov-preview-action">⚠ ${d.action.replace(/_/g, ' ')}</div>
      <div class="sov-preview-explanation">${d.explanation || d.description}</div>
      <div class="sov-preview-params">${JSON.stringify(d.params, null, 2)}</div>
      <div class="sov-preview-actions">
        <button class="sov-btn sov-btn-confirm destructive" id="sov-confirm">Confirm & execute</button>
        <button class="sov-btn sov-btn-cancel" id="sov-cancel">Cancel</button>
      </div>`;
    document.getElementById('sov-confirm').onclick = async () => {
      await executeAction(d.action, d.params);
      pendingAction = null;
    };
    document.getElementById('sov-cancel').onclick = () => {
      preview.classList.remove('show', 'destructive');
      preview.innerHTML = '';
      setStatus('Cancelled');
      pendingAction = null;
    };
  }

  async function executeAction(action, params) {
    setStatus('Executing...');
    preview.classList.remove('show', 'destructive');
    try {
      const r = await fetch('/api/v1/console/execute', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + TOKEN,
        },
        body: JSON.stringify({ action, params }),
      });
      const d = await r.json();
      if (!d.ok) {
        setStatus('✗ ' + (d.error || 'Execution failed'), 'error');
        return;
      }

      // If the result is a delegated action, call the actual endpoint
      const res = d.result || {};
      if (res.type === 'action' && res.delegated_to) {
        const r2 = await fetch(res.delegated_to, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + TOKEN,
          },
          body: JSON.stringify(res.body || {}),
        });
        const d2 = await r2.json();
        if (r2.ok) {
          setStatus('✓ Done');
          renderResult({ type: 'ok', message: 'Action completed', data: d2 });
        } else {
          setStatus('✗ ' + (d2.error || 'Action failed'), 'error');
        }
      } else {
        setStatus('✓ Done');
        renderResult(res);
      }
    } catch (e) {
      setStatus('✗ Network error', 'error');
    }
  }

  function renderResult(res) {
    result.style.display = 'block';
    if (res.type === 'stats') {
      result.innerHTML = `
        <div class="sov-result-title">${res.title}</div>
        <div class="sov-result-stats">
          ${Object.entries(res.stats).map(([k,v]) => `
            <div class="sov-stat">
              <div class="sov-stat-label">${k}</div>
              <div class="sov-stat-value">${v}</div>
            </div>`).join('')}
        </div>`;
    } else if (res.type === 'list') {
      const rows = res.rows || [];
      if (!rows.length) {
        result.innerHTML = `<div class="sov-result-title">${res.title}</div>
          <div style="color:#4A5A72; font-family:'JetBrains Mono';font-size:11px;
           letter-spacing:0.18em;text-transform:uppercase;text-align:center;padding:24px;">
           No results</div>`;
        return;
      }
      result.innerHTML = `
        <div class="sov-result-title">${res.title} · ${rows.length}</div>
        ${rows.map(row => {
          const main = row.address || row.name || row.from_number || row.phone || row.settlement_id || row.action || '—';
          const meta = [
            row.city, row.metro, row.urgency_score && `urg ${row.urgency_score}`,
            row.trust_score && `trust ${row.trust_score}`,
            row.amount_usdc && `$${row.amount_usdc}`,
            row.operator_name,
          ].filter(Boolean).join(' · ');
          return `<div class="sov-row">
            <span class="sov-row-main">${String(main).slice(0,60)}</span>
            <span class="sov-row-meta">${meta}</span>
          </div>`;
        }).join('')}`;
    } else if (res.type === 'ok') {
      result.innerHTML = `
        <div class="sov-result-title">${res.message || 'OK'}</div>
        <div style="color:#44E5B8;font-family:'JetBrains Mono';font-size:11px;
          letter-spacing:0.12em;padding:12px;">✓ Complete</div>`;
    } else if (res.status && res.meta && res.strategy) {
      // Synthetic pipeline result — side-by-side: LLM strategy vs rendered output
      const strat = res.strategy || {};
      const meta = res.meta || {};
      const passed = res.status === 'COMPLETED';
      const statusColor = passed ? '#44E5B8' : res.status === 'FAILED' ? '#f43f5e' : '#f59e0b';
      result.innerHTML = `
        <div class="sov-result-title">Synthetic Pipeline · ${res.status}</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:10px;">
          <div style="background:rgba(68,229,184,0.04);border:1px solid rgba(68,229,184,0.15);padding:14px;">
            <div style="font-family:'JetBrains Mono';font-size:9px;color:#7A8CA3;letter-spacing:0.18em;text-transform:uppercase;margin-bottom:12px;">🧠 LLM Strategy</div>
            <div style="font-family:'JetBrains Mono';font-size:10px;line-height:1.7;">
              ${['script_copy','chosen_template','target_phone','voice_profile','text_overlay_color','canvas_format'].map(k => {
                const v = strat[k];
                if (v == null) return '';
                return `<div style="margin-bottom:8px;">
                  <span style="color:#4A5A72;font-size:9px;letter-spacing:0.1em;text-transform:uppercase;">${k.replace(/_/g,' ')}</span><br>
                  <span style="color:#C8D4E4;word-break:break-word;">${escape(String(v))}</span>
                </div>`;
              }).join('')}
            </div>
          </div>
          <div style="background:rgba(90,200,250,0.04);border:1px solid rgba(90,200,250,0.15);padding:14px;">
            <div style="font-family:'JetBrains Mono';font-size:9px;color:#7A8CA3;letter-spacing:0.18em;text-transform:uppercase;margin-bottom:12px;">📦 Rendered Output</div>
            <div style="font-family:'JetBrains Mono';font-size:10px;line-height:1.7;">
              ${['script_executed','voice_profile','system_template_used','production_location'].map(k => {
                const v = meta[k];
                if (v == null) return '';
                const display = k === 'production_location' ? v.split('/').slice(-2).join('/') : v;
                return `<div style="margin-bottom:8px;">
                  <span style="color:#4A5A72;font-size:9px;letter-spacing:0.1em;text-transform:uppercase;">${k.replace(/_/g,' ')}</span><br>
                  <span style="color:#C8D4E4;word-break:break-word;">${String(display).slice(0,80)}</span>
                </div>`;
              }).join('')}
              ${res.error ? `<div style="margin-top:8px;padding:8px;background:rgba(244,63,94,0.08);border:1px solid rgba(244,63,94,0.3);color:#f43f5e;font-size:10px;">⚠ ${escape(res.error)}</div>` : ''}
            </div>
          </div>
        </div>
        <div style="margin-top:14px;background:rgba(0,0,0,0.3);padding:12px;font-family:'JetBrains Mono';font-size:10px;color:#7A8CA3;border-left:2px solid ${statusColor};">
          <span style="color:#C8D4E4;">🔍 QC Verdict:</span> ${escape(res.agent_diagnostics || '—')}
        </div>`;
    } else {
      result.innerHTML = `<div class="sov-result-title">Result</div>
        <pre style="color:#C8D4E4;font-family:'JetBrains Mono';font-size:11px;
          background:rgba(0,0,0,0.3);padding:12px;overflow:auto;">${JSON.stringify(res, null, 2)}</pre>`;
    }
  }

  // ── VOICE INPUT (Web Speech API) ──────────────────────────────────────
  function setupVoice() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      micBtn.style.display = 'none';
      return;
    }
    recognition = new SR();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onstart = () => {
      listening = true;
      micBtn.classList.add('listening');
      icon.classList.add('listening');
      micLabel.textContent = '🎙 listening';
      setStatus('Listening...');
    };
    recognition.onresult = (e) => {
      let text = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        text += e.results[i][0].transcript;
      }
      input.value = text;
    };
    recognition.onend = () => {
      listening = false;
      micBtn.classList.remove('listening');
      icon.classList.remove('listening');
      micLabel.textContent = '🎙 voice';
      if (input.value.trim()) {
        runCommand(input.value.trim());
      } else {
        setStatus('No speech detected');
      }
    };
    recognition.onerror = (e) => {
      listening = false;
      micBtn.classList.remove('listening');
      icon.classList.remove('listening');
      micLabel.textContent = '🎙 voice';
      setStatus('✗ Voice error: ' + e.error, 'error');
    };
  }

  function toggleVoice() {
    if (!recognition) setupVoice();
    if (!recognition) return;
    if (listening) {
      recognition.stop();
    } else {
      try { recognition.start(); } catch (e) {}
    }
  }
  micBtn.addEventListener('click', toggleVoice);
  setupVoice();
})();
</script>
"""
