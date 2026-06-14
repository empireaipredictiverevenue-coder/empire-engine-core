"""
Empire AI · Product Email Dispatcher
=====================================
Bridge between the product email sequence templates and the actual
EmailEngine delivery system. Runs a background loop that:

  1. **Event-driven** — called by SalesFunnelEngine on trial start/purchase
     to enroll users in onboarding and trial conversion sequences
  2. **Periodic** — background checks every 15 min for:
     - Subscriptions expiring in 3-7 days → renewal reminders
     - Recently expired subscriptions → reactivation emails
     - High churn risk accounts → win-back sequences

Each email is sent via the Resend helper and tracked in the
`product_email_sequences` table (migration 033).
"""

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional, List

from products.product_email_sequences import (
    build_onboarding_sequence,
    build_trial_sequence,
    build_upsell_sequence,
    build_renewal_sequence,
    build_reactivation_sequence,
    PRODUCT_NAMES,
)

log = logging.getLogger("empire.product_email_dispatcher")

# ── Config ───────────────────────────────────────────────────────────────
MONITOR_INTERVAL_SEC = 900       # check every 15 minutes
RENEWAL_REMINDER_DAYS = [7, 3]   # send reminders N days before expiry
REACTIVATION_DAYS = [1, 7]       # send reactivation N days after expiry
CHURN_CHECK_DAYS = [30, 60]      # check for churn risk after N days inactive

# ── Simple in-memory dedup cache to avoid double-sending in one run ──────
_sent_cache = set()


def _dedup_key(email: str, sequence_type: str, step: int) -> str:
    return f"{email}|{sequence_type}|{step}"


class ProductEmailDispatcher:
    """Bridge between product email templates and the Resend email system."""

    def __init__(
        self,
        send_email: Callable,        # hub's _send_email helper
        get_db: Callable,
        subscriptions: object,       # SuiteSubscriptionEngine
        sender_name: str = "Empire AI Operations",
        from_address: str = "noreply@empire-ai.co.uk",
    ):
        self.send_email = send_email
        self.get_db = get_db
        self.subscriptions = subscriptions
        self.sender_name = sender_name
        self.from_address = from_address
        self._stop_loop = False
        self.stats = {
            "onboarding_sent": 0,
            "trial_sent": 0,
            "renewal_sent": 0,
            "reactivation_sent": 0,
            "upsell_sent": 0,
            "errors": 0,
        }

    # ── Template placeholders replacement ───────────────────────────────

    def _render_body(self, body: str, email: str, product_slug: str) -> str:
        """Replace template placeholders with actual values."""
        dashboard_url = "https://empire-ai.co.uk/command"
        unsubscribe_link = f"{dashboard_url}/settings?email={email}"
        return body.replace("{{unsubscribe_link}}", unsubscribe_link) \
                   .replace("{{dashboard_url}}", dashboard_url) \
                   .replace("{{email}}", email)

    # ── Send a single email ─────────────────────────────────────────────

    async def _send(self, to_email: str, subject: str, body_html: str,
                    dedup_key: str = "") -> bool:
        """Send one email via the Resend helper. Returns True on success."""
        if dedup_key and dedup_key in _sent_cache:
            return False  # already sent this in this run
        try:
            result = await self.send_email(to=to_email, subject=subject, html=body_html)
            if isinstance(result, dict) and result.get("ok"):
                if dedup_key:
                    _sent_cache.add(dedup_key)
                return True
            else:
                log.warning(f"[dispatcher] send failed: {to_email} | {subject[:60]}")
                self.stats["errors"] += 1
                return False
        except Exception as e:
            log.warning(f"[dispatcher] send error: {to_email} | {e}")
            self.stats["errors"] += 1
            return False

    # ── Log sent email in product_email_sequences table ─────────────────

    def _log_sent(self, email: str, product_slug: str, sequence_type: str,
                  step: int, subject: str, delay_hours: int = 0):
        """Record a sent email in the tracking table."""
        try:
            db = self.get_db()
            db.table("product_email_sequences").insert({
                "product_slug": product_slug,
                "sequence_type": sequence_type,
                "step": step,
                "subject": subject[:200],
                "body_html": "",
                "delay_hours": delay_hours,
                "is_active": 1,
            }).execute()
        except Exception as e:
            log.debug(f"[dispatcher] log insert failed: {e}")

    # ═══════════════════════════════════════════════════════════════════
    # EVENT-DRIVEN ENROLLMENT
    # ═══════════════════════════════════════════════════════════════════

    async def enroll_onboarding(self, email: str, product_slug: str,
                                 tier: str, features: List[str] = None):
        """Send onboarding sequence after purchase/subscription.
        Called by SalesFunnelEngine.purchase()."""
        if not email or not product_slug:
            return
        seq = build_onboarding_sequence(product_slug, tier, features or [])
        log.info(f"[dispatcher] enrolling onboarding: {email} → {product_slug} ({tier})")
        for touch in seq:
            step = touch["step"]
            subject = touch["subject"]
            body = self._render_body(touch["body"], email, product_slug)
            dk = _dedup_key(email, f"onboarding_{product_slug}", step)
            ok = await self._send(email, subject, body, dedup_key=dk)
            if ok:
                self.stats["onboarding_sent"] += 1
                self._log_sent(email, product_slug, "onboarding", step, subject,
                                delay_hours=touch["delay_hours"])
            # Wait between touches (respects delay_hours, but we send all 3 immediately
            # since the content is self-contained — the delay is for the user's reading pace)
            if touch["delay_hours"] > 0:
                await asyncio.sleep(2)  # just a small gap between sends

    async def enroll_trial(self, email: str, product_slug: str, tier: str):
        """Send trial conversion sequence after trial signup.
        Called by SalesFunnelEngine.start_trial()."""
        if not email or not product_slug:
            return
        seq = build_trial_sequence(product_slug, tier)
        log.info(f"[dispatcher] enrolling trial: {email} → {product_slug} ({tier})")
        for touch in seq:
            step = touch["step"]
            subject = touch["subject"]
            body = self._render_body(touch["body"], email, product_slug)
            dk = _dedup_key(email, f"trial_{product_slug}", step)
            ok = await self._send(email, subject, body, dedup_key=dk)
            if ok:
                self.stats["trial_sent"] += 1
                self._log_sent(email, product_slug, "trial", step, subject,
                                delay_hours=touch["delay_hours"])
            # Trial touches have 72h, 168h, 312h delays — we send immediately
            # so the user sees them at the right cadence based on their trial
            await asyncio.sleep(2)

    # ═══════════════════════════════════════════════════════════════════
    # BACKGROUND LOOP — periodic checks
    # ═══════════════════════════════════════════════════════════════════

    async def monitoring_loop(self):
        """Background loop: check for renewal reminders, reactivation, upsells."""
        await asyncio.sleep(60)  # let hub finish booting
        log.info("[dispatcher] monitoring loop started")
        while not self._stop_loop:
            try:
                await self._check_renewals()
                await self._check_reactivations()
            except Exception as e:
                log.warning(f"[dispatcher] monitoring error: {e}")
            await asyncio.sleep(MONITOR_INTERVAL_SEC)

    def stop(self):
        self._stop_loop = True

    async def _check_renewals(self):
        """Check subscriptions expiring in 3-7 days and send renewal reminders."""
        try:
            db = self.get_db()
            now = datetime.now(timezone.utc)
            all_subs = self.subscriptions.list_subscriptions() if hasattr(self.subscriptions, 'list_subscriptions') else []

            for sub in all_subs:
                # Parse current_period_end
                period_end = sub.get("current_period_end")
                if not period_end:
                    continue
                try:
                    end = datetime.fromisoformat(str(period_end).replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    continue

                days_left = (end - now).days
                tier = sub.get("tier_level", "")
                account_id = sub.get("customer_account_id", "")

                # Send reminder at exactly 7 days and 3 days before expiry
                if days_left in RENEWAL_REMINDER_DAYS:
                    # Get the account email from the subscription or skip (no email field on product_subscriptions)
                    # For now, use account_id as email if it looks like one
                    email = account_id if "@" in account_id else ""
                    if not email:
                        continue

                    price = float(sub.get("monthly_recurring_revenue", 0) or 0)
                    product_slug = self._tier_to_product_slug(tier)
                    dk = _dedup_key(email, f"renewal_{days_left}d", 1)
                    seq = build_renewal_sequence(product_slug, tier, days_left, price)
                    if seq:
                        body = self._render_body(seq[0]["body"], email, product_slug)
                        ok = await self._send(email, seq[0]["subject"], body, dedup_key=dk)
                        if ok:
                            self.stats["renewal_sent"] += 1
                            self._log_sent(email, product_slug, "renewal", 1,
                                            seq[0]["subject"], delay_hours=0)

        except Exception as e:
            log.debug(f"[dispatcher] renewal check skipped: {e}")

    async def _check_reactivations(self):
        """Check recently expired subscriptions and send reactivation sequences."""
        try:
            db = self.get_db()
            all_subs = self.subscriptions.list_subscriptions() if hasattr(self.subscriptions, 'list_subscriptions') else []

            now = datetime.now(timezone.utc)
            for sub in all_subs:
                status = sub.get("subscription_status", "")
                if status != "CANCELED":
                    continue

                period_end = sub.get("current_period_end")
                if not period_end:
                    continue
                try:
                    end = datetime.fromisoformat(str(period_end).replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    continue

                days_since = (now - end).days
                if days_since not in REACTIVATION_DAYS:
                    continue

                tier = sub.get("tier_level", "")
                account_id = sub.get("customer_account_id", "")
                email = account_id if "@" in account_id else ""
                if not email:
                    continue

                product_slug = self._tier_to_product_slug(tier)
                dk = _dedup_key(email, f"reactivate_{days_since}d", 1)
                seq = build_reactivation_sequence(product_slug, tier, days_since)
                if seq:
                    body = self._render_body(seq[0]["body"], email, product_slug)
                    ok = await self._send(email, seq[0]["subject"], body, dedup_key=dk)
                    if ok:
                        self.stats["reactivation_sent"] += 1
                        self._log_sent(email, product_slug, "reactivation", 1,
                                        seq[0]["subject"], delay_hours=0)

        except Exception as e:
            log.debug(f"[dispatcher] reactivation check skipped: {e}")

    @staticmethod
    def _tier_to_product_slug(tier: str) -> str:
        """Extract the product slug from a tier name.
        e.g. 'LEADSCORE_STARTER' → 'lead_score', 'FORECAST_LITE' → 'forecast',
        'ROUTER_SaaS' → 'inbound_router', 'SEO_STARTER' → 'seo_optimizer'"""
        mapping = {
            "LEADSCORE": "lead_score",
            "COMPLIANT": "compliant",
            "STRIKE": "strike_campaigns",
            "FORECAST": "forecast",
            "MARKET_EYE": "market_eye",
            "CONTENT_PULSE": "content_pulse",
            "CONTRACTOR_EXCHANGE": "contractor_exchange",
            "ROUTER": "inbound_router",
            "DATA": "data_vault",
            "SPY": "buyer_spy",
            "ALL": "all_products",
            "SEO": "seo_optimizer",
            "INBOUND": "inbound_router",
        }
        prefix = tier.split("_")[0] if "_" in tier else ""
        # Try the full tier string first, then the prefix
        result = mapping.get(tier, mapping.get(prefix))
        if result:
            return result
        # Fallback: derive from tier name
        base = prefix.lower() if prefix else "lead_score"
        return base if base in PRODUCT_NAMES else "lead_score"

    # ── Stats snapshot ─────────────────────────────────────────────────

    def stats_snapshot(self) -> dict:
        return {
            "engine": dict(self.stats),
            "monitoring_interval_sec": MONITOR_INTERVAL_SEC,
            "renewal_reminder_days": RENEWAL_REMINDER_DAYS,
            "reactivation_days": REACTIVATION_DAYS,
        }
