"""
EMPIRE V49 · CLOSING AGENT
============================
Takes qualified leads through the full close cycle — voice pipeline, objection
handling, deal structuring, payment collection, and onboarding handoff.

Pulls from existing infrastructure:
  - empire_ai_closer.py   → HumanClosingEngine, ClosingExpert (objection handling)
  - empire_payouts.py     → PayoutEngine (payment processing)
  - empire_contractors.py → Contractor signup (onboarding handoff)

Fleet parent: sales_director
Receives handoffs from: sdr_agent (booked meetings via /api/sdr/handoff)

Close pipeline stages:
  intake → discovery → proposal → negotiation → closed_won → closed_lost → onboarding

Routes:
  GET    /api/closing/overview       — Pipeline dashboard overview
  GET    /api/closing/pipeline       — Deals by pipeline stage
  POST   /api/closing/intake         — Intake a lead from SDR handoff
  POST   /api/closing/propose        — Generate a deal proposal
  PATCH  /api/closing/deal           — Update deal stage
  POST   /api/closing/objection      — Handle an objection
  POST   /api/closing/payment        — Generate payment / invoice
  GET    /api/closing/deals          — All deals with filters
  POST   /api/closing/onboard        — Mark deal as onboarded
  GET    /api/closing/snapshot       — Condensed fleet snapshot
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable

log = logging.getLogger("empire.closing_agent")

# ── Close pipeline stages ──────────────────────────────────────────
CLOSE_STAGES = [
    "intake",           # Received from SDR handoff
    "discovery",        # Needs discovery call / qualification
    "proposal",         # Proposal sent to lead
    "negotiation",      # Active negotiation / objection handling
    "closed_won",       # Deal won — payment pending
    "closed_lost",      # Deal lost — with reason
    "onboarding",       # Payment received — onboarding in progress
    "completed",        # Fully onboarded and active
]

# ── Deal types ─────────────────────────────────────────────────────
DEAL_TYPES = {
    "contractor_subscription": {
        "label": "Contractor Priority Dispatch",
        "default_amount": 99.00,
        "currency": "USDC",
        "payment_frequency": "monthly",
    },
    "lead_gen_subscription": {
        "label": "B2B Lead Subscription",
        "default_amount": 199.00,
        "currency": "USDC",
        "payment_frequency": "monthly",
    },
    "suite_subscription": {
        "label": "Empire AI Suite",
        "default_amount": 499.00,
        "currency": "USDC",
        "payment_frequency": "monthly",
    },
    "custom_contract": {
        "label": "Custom Deal",
        "default_amount": 0.0,
        "currency": "USDC",
        "payment_frequency": "one_time",
    },
}

# ── Payment methods ────────────────────────────────────────────────
PAYMENT_METHODS = ["usdc_solana", "stripe", "wire_transfer", "ach"]

# ── Onboarding tasks ───────────────────────────────────────────────
ONBOARDING_TASKS = [
    "send_welcome_email",
    "schedule_kickoff_call",
    "create_account",
    "provision_access",
    "review_terms",
    "collect_deliverables",
]

# ── Objection categories (mirrors ClosingExpert from empire_ai_closer.py) ──
CLOSE_OBJECTIONS = {
    "not_interested":         "Not interested / don't need it",
    "too_expensive":          "Too expensive / budget concerns",
    "need_to_think":          "Need to think about it / call me later",
    "already_have_provider":  "Already working with someone",
    "not_decision_maker":     "Not the decision maker",
    "call_back_later":        "Call back later / busy now",
    "need_approval":          "Need approval from management",
    "timing_not_right":       "Timing isn't right",
    "too_risky":              "Too risky / unproven",
    "dont_understand":        "Don't understand the value",
}


class ClosingAgent:
    """Closing Agent — leads through full close cycle.

    Five core capabilities:
      1. Pipeline Management — stage tracking, velocity, conversion
      2. Objection Handling — expert responses via ClosingExpert
      3. Deal Structuring — pricing, terms, multi-product bundling
      4. Payment Collection — invoices, payment links, status tracking
      5. Onboarding Handoff — account creation, welcome, kickoff
    """

    def __init__(self, get_db: Callable):
        self.get_db = get_db
        self._deals: list[dict] = []       # deal records
        self._invoices: list[dict] = []    # payment invoices
        self._onboardings: list[dict] = [] # onboarding records
        self._objections_log: list[dict] = []  # objection history
        self._pipeline_history: list[dict] = []  # stage transitions

        # Lazy-load the ClosingExpert from empire_ai_closer.py for objection handling
        self._closing_expert = None

        # Predictive cloud context (lazy-loaded)
        self._predictive_cr = None  # close rate from predictive engine
        self._predictive_forecast = None  # cached forecast data

    def _db(self):
        return self.get_db()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _days_ago(self, d: int) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=d)).isoformat()

    def _get_closing_expert(self):
        """Lazy-load the ClosingExpert for expert objection handling."""
        if self._closing_expert is None:
            try:
                from empire_ai_closer import ClosingExpert, HumanClosingEngine
                self._closing_expert = {
                    "expert": ClosingExpert(),
                    "human_closing": HumanClosingEngine(),
                }
            except (ImportError, AttributeError) as e:
                log.debug(f"[closing] ClosingExpert not available: {e}")
                self._closing_expert = False  # mark as attempted
        return self._closing_expert if self._closing_expert else None

    # ── 1. PIPELINE MANAGEMENT ───────────────────────────────────────

    def _get_predictive_close_rate(self) -> float:
        """Get the current close rate from the predictive revenue engine."""
        if self._predictive_cr is not None:
            return self._predictive_cr
        try:
            from bots import predictive_revenue
            self._predictive_cr = predictive_revenue.get_close_rate()
        except Exception as e:
            log.debug(f"[closing] predictive close rate unavailable: {e}")
            self._predictive_cr = 0.15
        return self._predictive_cr

    def _get_predictive_forecast(self) -> dict:
        """Get per-lane forecast data from predictive engine."""
        if self._predictive_forecast is not None:
            return self._predictive_forecast
        try:
            from bots import predictive_revenue
            fc = predictive_revenue.per_lane_forecast() or {}
            self._predictive_forecast = {
                "mrr_projected": fc.get("totals", {}).get("mrr_projected", 0),
                "revenue_24h": fc.get("totals", {}).get("revenue_24h", 0),
                "lanes_active": fc.get("totals", {}).get("lanes_active", 0),
                "health": fc.get("health", {}),
            }
        except Exception as e:
            log.debug(f"[closing] predictive forecast unavailable: {e}")
            self._predictive_forecast = {"mrr_projected": 0, "revenue_24h": 0, "lanes_active": 0, "health": {}}
        return self._predictive_forecast

    def _create_deal(self, lead: dict) -> dict:
        """Create a new deal record from an incoming lead."""
        deal_id = f"DL-{uuid.uuid4().hex[:8].upper()}"
        now = self._now()

        # Use predictive close rate for initial probability
        pred_cr = self._get_predictive_close_rate()

        deal = {
            "deal_id": deal_id,
            "lead_id": lead.get("lead_id", lead.get("id", "")),
            "target_name": lead.get("target_name", lead.get("name", "Unknown")),
            "company": lead.get("company", lead.get("warehouse_name", "")),
            "phone": lead.get("phone", ""),
            "email": lead.get("email", ""),
            "city": lead.get("city", ""),
            "state": lead.get("state", ""),
            "niche": (lead.get("niche") or "").lower(),
            "stage": "intake",
            "deal_type": "custom_contract",
            "amount": 0.0,
            "currency": "USDC",
            "payment_frequency": "one_time",
            "terms": "",
            "notes": lead.get("notes", ""),
            "handoff_source": lead.get("source", "sdr_agent"),
            "sdr_booking_id": lead.get("booking_id", ""),
            "sdr_handoff_notes": lead.get("handoff_instructions", ""),
            "probability": pred_cr,
            "predictive_close_rate": pred_cr,
            "stage_history": [{"stage": "intake", "timestamp": now}],
            "created_at": now,
            "updated_at": now,
        }
        self._deals.append(deal)
        self._pipeline_history.append({
            "deal_id": deal_id,
            "from_stage": None,
            "to_stage": "intake",
            "timestamp": now,
            "source": "intake",
        })
        return deal

    def _advance_stage(self, deal_id: str, to_stage: str,
                        reason: str = "") -> Optional[dict]:
        """Advance a deal to a new pipeline stage."""
        deal = self._get_deal(deal_id)
        if not deal:
            return None

        if to_stage not in CLOSE_STAGES:
            return None

        from_stage = deal["stage"]
        now = self._now()

        deal["stage"] = to_stage
        deal["stage_history"].append({
            "stage": to_stage,
            "timestamp": now,
            "reason": reason,
        })
        deal["updated_at"] = now

        # Probability adjustments based on stage + predictive close rate
        pred_cr = self._get_predictive_close_rate()
        stage_prob = {
            "intake": pred_cr * 1.3,
            "discovery": pred_cr * 2.3,
            "proposal": pred_cr * 3.3,
            "negotiation": pred_cr * 4.3,
            "closed_won": 1.0,
            "closed_lost": 0.0,
            "onboarding": 0.95,
            "completed": 1.0,
        }
        deal["probability"] = min(1.0, max(0.0, stage_prob.get(to_stage, pred_cr)))

        self._pipeline_history.append({
            "deal_id": deal_id,
            "from_stage": from_stage,
            "to_stage": to_stage,
            "timestamp": now,
            "reason": reason,
        })

        return deal

    def _get_deal(self, deal_id: str) -> Optional[dict]:
        """Find a deal by ID."""
        for d in self._deals:
            if d["deal_id"] == deal_id:
                return d
        return None

    def _stage_counts(self) -> dict:
        """Return count of deals in each stage."""
        counts = {}
        for stage in CLOSE_STAGES:
            counts[stage] = sum(1 for d in self._deals if d["stage"] == stage)
        return counts

    def _pipeline_velocity(self) -> dict:
        """Calculate pipeline velocity: avg days from intake to won."""
        won_deals = [d for d in self._deals if d["stage"] in ("closed_won", "onboarding", "completed")]
        if not won_deals:
            return {"avg_days_to_close": 0, "total_won": 0}

        total_days = 0
        count = 0
        for d in won_deals:
            history = d.get("stage_history", [])
            intake_time = None
            won_time = None
            for h in history:
                if h["stage"] == "intake":
                    intake_time = h.get("timestamp", "")
                if h["stage"] in ("closed_won",):
                    won_time = h.get("timestamp", "")
            if intake_time and won_time:
                try:
                    i = datetime.fromisoformat(intake_time.replace("Z", "+00:00"))
                    w = datetime.fromisoformat(won_time.replace("Z", "+00:00"))
                    total_days += (w - i).days
                    count += 1
                except Exception:
                    pass

        return {
            "avg_days_to_close": round(total_days / max(count, 1), 1),
            "total_won": len(won_deals),
        }

    # ── 2. OBJECTION HANDLING ────────────────────────────────────────

    def handle_objection(self, deal_id: str, objection_text: str) -> dict:
        """Handle an objection against a deal.

        Uses ClosingExpert from empire_ai_closer.py when available,
        falls back to the built-in objection knowledge base.
        """
        deal = self._get_deal(deal_id)
        target_name = deal["target_name"] if deal else "the lead"
        location = f"{deal.get('city', '')}, {deal.get('state', '')}".strip(", ") if deal else ""

        # Try ClosingExpert first
        expert = self._get_closing_expert()
        if expert:
            try:
                closing = expert["expert"]
                result = closing.get_objection_response(
                    objection_text=objection_text,
                    lead_name=target_name,
                    location=location,
                )
                if result:
                    self._objections_log.append({
                        "deal_id": deal_id,
                        "objection_text": objection_text,
                        "response": result.get("response", ""),
                        "technique": result.get("technique", ""),
                        "source": "closing_expert",
                        "timestamp": self._now(),
                    })
                    return {
                        "ok": True,
                        "objection": objection_text[:200],
                        "response": result["response"],
                        "technique": result.get("technique", "unknown"),
                        "label": result.get("label", ""),
                        "source": "closing_expert",
                    }
            except Exception as e:
                log.debug(f"[closing] ClosingExpert objection handling failed: {e}")

        # Fallback: built-in keyword matching
        objection_lower = objection_text.lower().strip()
        matched_key = None
        for key, label in CLOSE_OBJECTIONS.items():
            kw = key.replace("_", " ")
            if any(word in objection_lower for word in kw.split()):
                matched_key = key
                break

        if not matched_key:
            # Check for individual keywords
            keyword_map = [
                (["not interested", "no thanks", "don't need", "stop"], "not_interested"),
                (["expensive", "budget", "cost", "price", "afford", "too much"], "too_expensive"),
                (["think about", "later", "not now", "maybe", "call me back"], "need_to_think"),
                (["already", "current", "existing", "my guy", "my team"], "already_have_provider"),
                (["manager", "boss", "owner", "partner", "not my decision"], "not_decision_maker"),
                (["busy", "meeting", "can't talk", "bad time"], "call_back_later"),
                (["approval", "board", "committee", "sign off"], "need_approval"),
                (["timing", "not ready", "too soon", "not yet"], "timing_not_right"),
                (["risk", "unproven", "new", "never heard", "scam"], "too_risky"),
                (["understand", "confused", "how does this", "what exactly"], "dont_understand"),
            ]
            for keywords, obj_key in keyword_map:
                if any(kw in objection_lower for kw in keywords):
                    matched_key = obj_key
                    break

        # Generate response from built-in templates
        responses = {
            "not_interested": (
                f"I understand, {target_name} — most of our partners felt the same way "
                f"until they saw what we can deliver. Let me share a quick case study "
                f"from a business similar to yours. If it's not relevant, no pressure at all."
            ),
            "too_expensive": (
                f"The cost concern makes sense, {target_name}. What if I told you our "
                f"partners see an average 3x ROI within the first 90 days? "
                f"There's no upfront commitment — we only earn when you do."
            ),
            "need_to_think": (
                f"Absolutely — I want you to be confident in this decision. "
                f"The opportunity window is open, and I don't want you to feel rushed. "
                f"How about I send you a one-page summary and follow up in a few days?"
            ),
            "already_have_provider": (
                f"That's great that you're already working with someone, {target_name}. "
                f"What we offer is complementary — our AI-driven pipeline surfaces "
                f"opportunities your current provider can't. No conflict, just more leads."
            ),
            "not_decision_maker": (
                f"Who should I speak with? I'm happy to share a brief overview — "
                f"no hard sell. What's the best way to get on their radar?"
            ),
            "call_back_later": (
                f"Of course — I don't want to keep you. When would be a better time? "
                f"I'll send a calendar invite so we don't miss each other."
            ),
            "need_approval": (
                f"Makes sense — I respect the process. Let me put together a one-pager "
                f"you can share with leadership. What would make the decision easier for them?"
            ),
            "timing_not_right": (
                f"I appreciate the honesty, {target_name}. What would be the ideal "
                f"timeline for you? I want to make sure we circle back at the right moment."
            ),
            "too_risky": (
                f"I hear you — trying something new is always a consideration. "
                f"We've onboarded over {12} businesses in your area this quarter alone. "
                f"I'd be happy to connect you with a reference — we're that confident."
            ),
            "dont_understand": (
                f"Let me clarify. What we do is simple: our AI predicts storm damage "
                f"before it becomes a claim, matches it to the right contractor, and "
                f"handles the lead flow. Your business gets qualified opportunities "
                f"without the overhead. Does that help?"
            ),
        }

        response_text = responses.get(matched_key, (
            f"I appreciate you sharing that, {target_name}. Let me make sure I understand "
            f"your concern fully. What's the main thing holding you back from moving forward?"
        ))

        self._objections_log.append({
            "deal_id": deal_id,
            "objection_text": objection_text,
            "matched_key": matched_key or "generic",
            "response": response_text,
            "source": "builtin",
            "timestamp": self._now(),
        })

        return {
            "ok": True,
            "objection": objection_text[:200],
            "response": response_text,
            "matched_category": CLOSE_OBJECTIONS.get(matched_key, "generic") if matched_key else "generic",
            "source": "builtin",
        }

    # ── 3. DEAL STRUCTURING ─────────────────────────────────────────

    def structure_deal(self, deal_id: str, deal_type: str = "custom_contract",
                        amount: float = 0.0, currency: str = "USDC",
                        payment_frequency: str = "one_time",
                        terms: str = "") -> dict:
        """Structure a deal with pricing, terms, and payment details."""
        deal = self._get_deal(deal_id)
        if not deal:
            return {"ok": False, "error": f"Deal {deal_id} not found"}

        deal_type_info = DEAL_TYPES.get(deal_type, DEAL_TYPES["custom_contract"])

        # Apply type defaults if not overridden
        if amount <= 0 and deal_type_info["default_amount"] > 0:
            amount = deal_type_info["default_amount"]

        deal["deal_type"] = deal_type
        deal["amount"] = amount
        deal["currency"] = currency or deal_type_info["currency"]
        deal["payment_frequency"] = payment_frequency or deal_type_info["payment_frequency"]
        deal["terms"] = terms or deal_type_info["label"]
        deal["updated_at"] = self._now()

        # Advance to proposal stage if in intake/discovery
        if deal["stage"] in ("intake", "discovery"):
            self._advance_stage(deal_id, "proposal",
                                reason=f"Deal structured: {deal_type_info['label']} · ${amount:.0f} {currency}")

        return {
            "ok": True,
            "deal_id": deal_id,
            "deal_type": deal_type,
            "deal_type_label": deal_type_info["label"],
            "amount": amount,
            "currency": deal["currency"],
            "payment_frequency": deal["payment_frequency"],
            "terms": deal["terms"],
            "stage": deal["stage"],
        }

    def add_proposal_notes(self, deal_id: str, notes: str) -> dict:
        """Add negotiation notes to a deal."""
        deal = self._get_deal(deal_id)
        if not deal:
            return {"ok": False, "error": f"Deal {deal_id} not found"}
        existing = deal.get("notes", "")
        deal["notes"] = (existing + "\n---\n" + notes) if existing else notes
        deal["updated_at"] = self._now()
        return {"ok": True, "deal_id": deal_id, "notes_length": len(deal["notes"])}

    # ── 4. PAYMENT COLLECTION ───────────────────────────────────────

    def generate_invoice(self, deal_id: str, amount: Optional[float] = None,
                          method: str = "usdc_solana",
                          due_days: int = 15) -> dict:
        """Generate a payment invoice for a deal."""
        deal = self._get_deal(deal_id)
        if not deal:
            return {"ok": False, "error": f"Deal {deal_id} not found"}

        invoice_amount = amount if amount is not None else deal.get("amount", 0)
        if invoice_amount <= 0:
            return {"ok": False, "error": "Invoice amount must be > 0"}

        invoice_id = f"INV-{uuid.uuid4().hex[:8].upper()}"
        now = self._now()
        due_date = (datetime.now(timezone.utc) + timedelta(days=due_days)).isoformat()

        invoice = {
            "invoice_id": invoice_id,
            "deal_id": deal_id,
            "target_name": deal["target_name"],
            "company": deal.get("company", ""),
            "email": deal.get("email", ""),
            "amount": invoice_amount,
            "currency": deal.get("currency", "USDC"),
            "payment_method": method,
            "status": "pending",
            "due_date": due_date,
            "created_at": now,
            "paid_at": None,
            "payment_tx": None,
            "notes": f"Invoice for {deal.get('deal_type', 'custom')} · {deal['target_name']}",
        }
        self._invoices.append(invoice)

        return {
            "ok": True,
            "invoice": invoice,
            "payment_instructions": self._payment_instructions(method, invoice_amount),
        }

    def _payment_instructions(self, method: str, amount: float) -> str:
        """Return human-readable payment instructions."""
        instructions = {
            "usdc_solana": (
                f"Send {amount:.2f} USDC to the Empire vault wallet on Solana. "
                f"Reference your invoice ID in the memo field. "
                f"Once confirmed on-chain, the deal advances to onboarding."
            ),
            "stripe": (
                f"A payment link will be sent to the contact email. "
                f"Pay via credit card or USDC through Stripe checkout. "
                f"Payment is processed immediately."
            ),
            "wire_transfer": (
                f"Wire {amount:.2f} USDC equivalent to the Empire vault account. "
                f"Reference your deal ID. Settlement typically takes 1-2 business days."
            ),
            "ach": (
                f"ACH transfer of {amount:.2f} USDC equivalent. "
                f"Processing takes 3-5 business days. "
                f"Credentials will be provided upon request."
            ),
        }
        return instructions.get(method, f"Pay {amount:.2f} via {method}")

    def mark_paid(self, invoice_id: str, payment_tx: str = "") -> dict:
        """Mark an invoice as paid."""
        for inv in self._invoices:
            if inv["invoice_id"] == invoice_id:
                inv["status"] = "paid"
                inv["paid_at"] = self._now()
                inv["payment_tx"] = payment_tx

                # Advance the deal to closed_won
                deal = self._get_deal(inv["deal_id"])
                if deal and deal["stage"] in ("proposal", "negotiation"):
                    self._advance_stage(
                        inv["deal_id"], "closed_won",
                        reason=f"Payment received: {invoice_id}",
                    )

                return {
                    "ok": True,
                    "invoice_id": invoice_id,
                    "status": "paid",
                    "paid_at": inv["paid_at"],
                    "deal_stage": deal["stage"] if deal else "unknown",
                }

        return {"ok": False, "error": f"Invoice {invoice_id} not found"}

    def get_payment_status(self, deal_id: str) -> dict:
        """Get payment status for a deal."""
        deal_invoices = [inv for inv in self._invoices if inv["deal_id"] == deal_id]
        if not deal_invoices:
            return {"has_invoice": False, "status": "no_invoice"}

        paid = [inv for inv in deal_invoices if inv["status"] == "paid"]
        pending = [inv for inv in deal_invoices if inv["status"] == "pending"]

        return {
            "has_invoice": True,
            "total_invoices": len(deal_invoices),
            "total_amount": sum(inv["amount"] for inv in deal_invoices),
            "paid_amount": sum(inv["amount"] for inv in paid),
            "pending_amount": sum(inv["amount"] for inv in pending),
            "status": "paid" if paid and not pending else "pending",
            "invoices": deal_invoices,
        }

    # ── 5. ONBOARDING HANDOFF ────────────────────────────────────────

    def initiate_onboarding(self, deal_id: str) -> dict:
        """Start the onboarding process for a closed-won deal."""
        deal = self._get_deal(deal_id)
        if not deal:
            return {"ok": False, "error": f"Deal {deal_id} not found"}

        if deal["stage"] not in ("closed_won", "onboarding", "completed"):
            # Auto-advance to onboarding if payment is confirmed
            payment_status = self.get_payment_status(deal_id)
            if payment_status.get("status") != "paid" and deal["stage"] != "closed_won":
                return {
                    "ok": False,
                    "error": f"Deal is in '{deal['stage']}' stage. "
                             f"Must be 'closed_won' or payment must be confirmed first.",
                    "payment_status": payment_status,
                }

        # Advance stage
        self._advance_stage(deal_id, "onboarding",
                            reason="Payment confirmed — starting onboarding")

        onboarding_id = f"ONBRD-{uuid.uuid4().hex[:8].upper()}"
        now = self._now()

        onboarding = {
            "onboarding_id": onboarding_id,
            "deal_id": deal_id,
            "target_name": deal["target_name"],
            "company": deal.get("company", ""),
            "email": deal.get("email", ""),
            "phone": deal.get("phone", ""),
            "niche": deal.get("niche", ""),
            "deal_type": deal.get("deal_type", ""),
            "tasks": [
                {
                    "task_id": f"TASK-{uuid.uuid4().hex[:8].upper()}",
                    "name": task_name,
                    "status": "pending",
                    "assigned_to": "closing_agent",
                    "created_at": now,
                }
                for task_name in ONBOARDING_TASKS
            ],
            "completed_tasks": 0,
            "total_tasks": len(ONBOARDING_TASKS),
            "status": "in_progress",
            "created_at": now,
            "completed_at": None,
        }
        self._onboardings.append(onboarding)

        # Generate welcome message
        welcome = self._generate_welcome_message(deal)

        return {
            "ok": True,
            "onboarding": onboarding,
            "welcome_message": welcome,
            "kickoff_suggestions": self._kickoff_suggestions(deal),
            "next_steps": [
                "Send welcome email to lead",
                "Schedule 30-min kickoff call",
                "Set up account credentials",
                "Send onboarding checklist",
            ],
        }

    def _generate_welcome_message(self, deal: dict) -> str:
        """Generate a personalized welcome message for the new partner."""
        name = deal.get("target_name", "Partner")
        company = deal.get("company", "your company")
        deal_type = deal.get("deal_type", "subscription")
        deal_type_label = DEAL_TYPES.get(deal_type, {}).get("label", deal_type)

        return (
            f"Welcome to Empire AI, {name}! 🎉\n\n"
            f"We're excited to have {company} as our newest {deal_type_label} partner. "
            f"Here's what to expect in the next 48 hours:\n\n"
            f"1. **Welcome Kit** — You'll receive a detailed welcome email with "
            f"your account credentials, getting-started guide, and key contact info.\n\n"
            f"2. **Kickoff Call** — We'll schedule a 30-minute onboarding call "
            f"to walk through setup, answer questions, and align on goals.\n\n"
            f"3. **First Delivery** — Your first set of qualified opportunities "
            f"will start flowing within 72 hours of kickoff.\n\n"
            f"4. **Success Plan** — Your dedicated account manager will outline "
            f"a 90-day success plan tailored to {company}'s goals.\n\n"
            f"If you have any questions before then, reply to this message or "
            f"email support@empire-ai.co.uk. We're here to help!\n\n"
            f"— The Empire AI Team"
        )

    def _kickoff_suggestions(self, deal: dict) -> list:
        """Generate kickoff call agenda suggestions."""
        return [
            "Introduce the Empire AI platform and key features",
            f"Review {deal.get('target_name', 'partner')}'s goals and success metrics",
            "Walk through the dashboard and reporting",
            "Set up integrations and data sources",
            "Schedule weekly check-in cadence",
            "Identify first opportunities to pursue",
        ]

    def complete_onboarding(self, deal_id: str) -> dict:
        """Mark onboarding as complete and deal as completed."""
        deal = self._get_deal(deal_id)
        if not deal:
            return {"ok": False, "error": f"Deal {deal_id} not found"}

        # Update onboarding record
        for o in self._onboardings:
            if o["deal_id"] == deal_id:
                o["status"] = "completed"
                o["completed_at"] = self._now()
                o["completed_tasks"] = o["total_tasks"]

        # Advance deal to completed
        self._advance_stage(deal_id, "completed", reason="Onboarding complete")

        return {
            "ok": True,
            "deal_id": deal_id,
            "stage": "completed",
            "onboarding_complete": True,
        }

    # ── 6. DASHBOARD / OVERVIEW ─────────────────────────────────────

    def overview(self) -> dict:
        """Pipeline dashboard — stage counts, velocity, conversion rates — with predictive cloud context."""
        stage_counts = self._stage_counts()
        velocity = self._pipeline_velocity()
        pred_cr = self._get_predictive_close_rate()
        pred_fc = self._get_predictive_forecast()

        total_deals = len(self._deals)
        won = sum(stage_counts.get(s, 0) for s in ("closed_won", "onboarding", "completed"))
        lost = stage_counts.get("closed_lost", 0)
        active = total_deals - won - lost

        total_pipeline_value = sum(d.get("amount", 0) for d in self._deals
                                   if d["stage"] not in ("closed_lost", "completed"))
        total_won_value = sum(d.get("amount", 0) for d in self._deals
                              if d["stage"] in ("closed_won", "onboarding", "completed"))

        # Invoices
        total_invoiced = sum(inv.get("amount", 0) for inv in self._invoices)
        total_collected = sum(inv.get("amount", 0) for inv in self._invoices
                              if inv["status"] == "paid")
        pending_invoices = len([inv for inv in self._invoices if inv["status"] == "pending"])

        # Onboardings
        active_onboardings = len([o for o in self._onboardings
                                  if o["status"] == "in_progress"])
        completed_onboardings = len([o for o in self._onboardings
                                     if o["status"] == "completed"])

        # Recent objections
        recent_objections = sorted(self._objections_log,
                                   key=lambda o: o.get("timestamp", ""), reverse=True)[:5]

        return {
            "ts": self._now(),
            "predictive": {
                "close_rate": round(pred_cr, 3),
                "mrr_projected": pred_fc.get("mrr_projected", 0),
                "revenue_24h": pred_fc.get("revenue_24h", 0),
                "lanes_active": pred_fc.get("lanes_active", 0),
                "health": pred_fc.get("health", {}),
            },
            "pipeline": {
                "total": total_deals,
                "active": active,
                "won": won,
                "lost": lost,
                "by_stage": stage_counts,
                "avg_days_to_close": velocity.get("avg_days_to_close", 0),
                "pipeline_value": round(total_pipeline_value, 2),
                "won_value": round(total_won_value, 2),
            },
            "conversion": {
                "win_rate_pct": round(won / max(won + lost, 1) * 100, 1),
                "active_to_won_pct": round(
                    won / max(total_deals, 1) * 100, 1
                ),
                "close_rate": round(pred_cr, 3),
            },
            "revenue": {
                "total_invoiced": round(total_invoiced, 2),
                "total_collected": round(total_collected, 2),
                "collection_rate_pct": round(
                    total_collected / max(total_invoiced, 1) * 100, 1
                ),
                "pending_invoices": pending_invoices,
            },
            "onboarding": {
                "active": active_onboardings,
                "completed": completed_onboardings,
                "total": len(self._onboardings),
            },
            "objections": {
                "total_handled": len(self._objections_log),
                "recent": recent_objections,
            },
        }

    def deals(self, stage_filter: str = "", deal_type: str = "",
              limit: int = 50) -> dict:
        """Return deals, optionally filtered by stage or type."""
        results = self._deals
        if stage_filter:
            results = [d for d in results if d["stage"] == stage_filter]
        if deal_type:
            results = [d for d in results if d.get("deal_type") == deal_type]

        # Sort by updated_at descending
        results.sort(key=lambda d: d.get("updated_at", ""), reverse=True)

        # Group by stage
        by_stage = {}
        for stage in CLOSE_STAGES:
            stage_deals = [d for d in results if d["stage"] == stage]
            if stage_deals:
                by_stage[stage] = sorted(stage_deals,
                                         key=lambda d: d.get("updated_at", ""),
                                         reverse=True)[:limit]

        return {
            "ts": self._now(),
            "total": len(results),
            "stage_filter": stage_filter or "all",
            "deal_type_filter": deal_type or "all",
            "by_stage": by_stage,
            "all": results[:limit],
        }

    def pipeline(self) -> dict:
        """Pipeline view — deals organized by stage with value totals."""
        by_stage = {}
        for stage in CLOSE_STAGES:
            stage_deals = [d for d in self._deals if d["stage"] == stage]
            if not stage_deals:
                continue
            total_value = sum(d.get("amount", 0) for d in stage_deals)
            by_stage[stage] = {
                "count": len(stage_deals),
                "total_value": round(total_value, 2),
                "deals": sorted(stage_deals, key=lambda d: d.get("updated_at", ""), reverse=True),
            }

        return {
            "ts": self._now(),
            "stages": by_stage,
            "stage_order": CLOSE_STAGES,
        }

    # ── SNAPSHOT ─────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Condensed snapshot for fleet dashboard."""
        o = self.overview()
        return {
            "active_deals": o.get("pipeline", {}).get("active", 0),
            "won_deals": o.get("pipeline", {}).get("won", 0),
            "pipeline_value": o.get("pipeline", {}).get("pipeline_value", 0),
            "win_rate_pct": o.get("conversion", {}).get("win_rate_pct", 0),
            "total_collected": o.get("revenue", {}).get("total_collected", 0),
            "pending_invoices": o.get("revenue", {}).get("pending_invoices", 0),
            "active_onboardings": o.get("onboarding", {}).get("active", 0),
            "objections_handled": o.get("objections", {}).get("total_handled", 0),
            "avg_days_to_close": o.get("pipeline", {}).get("avg_days_to_close", 0),
            "modified": self._now(),
        }


# ── FASTAPI ROUTES ──────────────────────────────────────────────────────

def register_closing_routes(app, get_db=None, require_auth=None):
    """Register Closing Agent routes on a FastAPI app."""
    from fastapi import Depends, HTTPException, Query

    if get_db is None:
        log.warning("[closing] No get_db — agent will return errors on DB calls")
    _ca = ClosingAgent(get_db=get_db) if get_db else None

    def _get_ca():
        if _ca is None:
            raise HTTPException(503, "Closing Agent not initialized (no get_db)")
        return _ca

    @app.get("/api/closing/overview")
    async def closing_overview(auth=Depends(require_auth) if require_auth else None):
        """Pipeline dashboard — stage counts, velocity, conversion, revenue, onboarding."""
        return _get_ca().overview()

    @app.get("/api/closing/pipeline")
    async def closing_pipeline(auth=Depends(require_auth) if require_auth else None):
        """Deals organized by pipeline stage with value totals."""
        return _get_ca().pipeline()

    @app.post("/api/closing/intake")
    async def closing_intake(
        lead_id: str = Query("", description="Lead ID from SDR handoff"),
        target_name: str = Query("", description="Lead/company name"),
        phone: str = Query("", description="Contact phone"),
        email: str = Query("", description="Contact email"),
        city: str = Query("", description="City"),
        state: str = Query("", description="State"),
        niche: str = Query("", description="Lead niche"),
        company: str = Query("", description="Company name"),
        notes: str = Query("", description="Handoff notes from SDR"),
        source: str = Query("sdr_agent", description="Handoff source"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Intake a lead from SDR handoff into the close pipeline."""
        ca = _get_ca()
        deal = ca._create_deal({
            "lead_id": lead_id,
            "target_name": target_name,
            "name": target_name,
            "phone": phone,
            "email": email,
            "city": city,
            "state": state,
            "niche": niche,
            "company": company,
            "warehouse_name": company,
            "notes": notes,
            "source": source,
        })
        return {
            "ok": True,
            "deal": deal,
            "next_stages": CLOSE_STAGES,
        }

    @app.post("/api/closing/propose")
    async def closing_propose(
        deal_id: str = Query("", description="Deal ID"),
        deal_type: str = Query("custom_contract",
                               description="Deal type: contractor_subscription|lead_gen_subscription|suite_subscription|custom_contract"),
        amount: float = Query(0.0, description="Deal amount (0 for type default)"),
        currency: str = Query("USDC", description="Currency"),
        payment_frequency: str = Query("one_time", description="one_time|monthly|annual"),
        terms: str = Query("", description="Payment terms / deal description"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Structure a deal proposal with pricing and terms."""
        result = _get_ca().structure_deal(
            deal_id=deal_id, deal_type=deal_type,
            amount=amount, currency=currency,
            payment_frequency=payment_frequency, terms=terms,
        )
        status = 200 if result.get("ok") else 404
        return result

    @app.patch("/api/closing/deal")
    async def closing_update_deal(
        deal_id: str = Query("", description="Deal ID"),
        stage: str = Query("", description=f"Target stage: {', '.join(CLOSE_STAGES)}"),
        reason: str = Query("", description="Reason for stage change"),
        notes: str = Query("", description="Additional notes"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Update a deal's pipeline stage and/or add notes."""
        ca = _get_ca()
        if not deal_id:
            raise HTTPException(400, "deal_id is required")

        result = {"ok": True, "deal_id": deal_id}

        if stage:
            if stage not in CLOSE_STAGES:
                raise HTTPException(400, f"Invalid stage. Valid: {', '.join(CLOSE_STAGES)}")
            adv = ca._advance_stage(deal_id, stage, reason=reason)
            if not adv:
                raise HTTPException(404, f"Deal {deal_id} not found")
            result["stage"] = stage

        if notes:
            ca.add_proposal_notes(deal_id, notes)
            result["notes_added"] = True

        return result

    @app.post("/api/closing/objection")
    async def closing_handle_objection(
        deal_id: str = Query("", description="Deal ID"),
        objection_text: str = Query("", description="The objection text from the lead"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Handle an objection against a deal with an expert response."""
        if not deal_id or not objection_text:
            raise HTTPException(400, "deal_id and objection_text are required")
        result = _get_ca().handle_objection(deal_id, objection_text)
        return result

    @app.post("/api/closing/payment")
    async def closing_generate_payment(
        deal_id: str = Query("", description="Deal ID"),
        amount: Optional[float] = Query(None, description="Override amount (optional)"),
        method: str = Query("usdc_solana", description=f"Payment method: {'|'.join(PAYMENT_METHODS)}"),
        due_days: int = Query(15, description="Days until due"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Generate an invoice and payment instructions for a deal."""
        if not deal_id:
            raise HTTPException(400, "deal_id is required")
        result = _get_ca().generate_invoice(
            deal_id=deal_id, amount=amount,
            method=method, due_days=due_days,
        )
        status = 200 if result.get("ok") else 404
        return result

    @app.post("/api/closing/payment/mark-paid")
    async def closing_mark_paid(
        invoice_id: str = Query("", description="Invoice ID"),
        payment_tx: str = Query("", description="Payment transaction ID (optional)"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Mark an invoice as paid and advance the deal to closed_won."""
        if not invoice_id:
            raise HTTPException(400, "invoice_id is required")
        result = _get_ca().mark_paid(invoice_id=invoice_id, payment_tx=payment_tx)
        status = 200 if result.get("ok") else 404
        return result

    @app.get("/api/closing/payment/status")
    async def closing_payment_status(
        deal_id: str = Query("", description="Deal ID"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Get payment status for a deal."""
        if not deal_id:
            raise HTTPException(400, "deal_id is required")
        return _get_ca().get_payment_status(deal_id)

    @app.get("/api/closing/deals")
    async def closing_deals(
        stage: str = Query("", description=f"Filter by stage: {', '.join(CLOSE_STAGES)}"),
        deal_type: str = Query("", description="Filter by deal type"),
        limit: int = Query(50, ge=1, le=200),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """All deals with optional filters."""
        return _get_ca().deals(stage_filter=stage, deal_type=deal_type, limit=limit)

    @app.post("/api/closing/onboard")
    async def closing_start_onboarding(
        deal_id: str = Query("", description="Deal ID to onboard"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Initiate onboarding for a closed-won deal — generates welcome, kickoff, tasks."""
        if not deal_id:
            raise HTTPException(400, "deal_id is required")
        result = _get_ca().initiate_onboarding(deal_id)
        status = 200 if result.get("ok") else 400
        return result

    @app.post("/api/closing/onboard/complete")
    async def closing_complete_onboarding(
        deal_id: str = Query("", description="Deal ID to mark complete"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Mark onboarding as complete and deal as completed."""
        if not deal_id:
            raise HTTPException(400, "deal_id is required")
        result = _get_ca().complete_onboarding(deal_id)
        status = 200 if result.get("ok") else 404
        return result

    @app.get("/api/closing/snapshot")
    async def closing_snapshot(auth=Depends(require_auth) if require_auth else None):
        """Condensed snapshot for fleet dashboard."""
        return _get_ca().snapshot()

    log.info("[closing] Routes registered · /api/closing/{overview,pipeline,intake,propose,deal,objection,payment,deals,onboard,snapshot}")
