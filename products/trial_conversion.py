"""
Empire AI · Trial Conversion Webhook
=====================================
Scans for expired free trials and auto-converts them to paid subscriptions.

Architecture:
  - Queries `sales_events` for trial_start rows where trial_end is in the past
  - Skips trials already converted (checks for trial_converted event)
  - Looks up the tier price from PRODUCT_CATALOG / TRIAL_CONFIG
  - Updates the SuiteSubscriptionEngine subscription MRR
  - Logs a trial_converted event in sales_events
  - Sends a conversion notification email
  - Runs as a background loop (hourly) + exposes an API endpoint for manual fire
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional

from products.sales_funnel import PRODUCT_CATALOG, TRIAL_CONFIG
from products.product_email_sequences import PRODUCT_NAMES

log = logging.getLogger("empire.trial_conversion")

# ── Config ───────────────────────────────────────────────────────────────
CHECK_INTERVAL_SEC = 3600       # check every hour
CONVERSION_GRACE_HOURS = 24     # wait 24h after trial ends before auto-converting
EXPIRING_SOON_DAYS = [3, 1]     # send reminders N days before trial ends


class TrialConversionEngine:
    """Background engine that detects expired trials and auto-converts to paid."""

    def __init__(
        self,
        get_db: Callable,
        subscriptions: object,    # SuiteSubscriptionEngine
        send_email: Optional[Callable] = None,
    ):
        self.get_db = get_db
        self.subscriptions = subscriptions
        self.send_email = send_email
        self._stop_loop = False
        self.stats = {
            "scans": 0,
            "converted": 0,
            "skipped_already_converted": 0,
            "skipped_no_subscription": 0,
            "skipped_already_paid": 0,
            "errors": 0,
            "emails_sent": 0,
            "expiring_soon_reminders_sent": 0,
            "skipped_already_reminded": 0,
            "auto_created": 0,
            "churn_detected": 0,
            "churn_reported": 0,
            "win_backs_sent": 0,
        }

    # ── Core: find and convert expired trials ───────────────────────────

    def _find_expired_trials(self) -> list[dict]:
        """Query sales_events for trial_start rows past their trial_end.

        Returns rows that:
          - Have event_type = 'trial_start'
          - Have trial_end <= now (expired)
          - Have no corresponding trial_converted event (same email + product)
        """
        db = self.get_db()
        now_iso = datetime.now(timezone.utc).isoformat()

        # Fetch all trial_start events
        r = db.table("sales_events") \
            .select("*") \
            .eq("event_type", "trial_start") \
            .order("created_at", desc=False) \
            .execute()
        trials = r.data or []

        # Fetch all trial_converted events for exclusion check
        r2 = db.table("sales_events") \
            .select("email, product_slug") \
            .eq("event_type", "trial_converted") \
            .execute()
        converted = set()
        for ev in (r2.data or []):
            converted.add((ev.get("email", ""), ev.get("product_slug", "")))

        expired = []
        for t in trials:
            trial_end = t.get("trial_end")
            if not trial_end:
                continue

            # Check if past trial_end (plus grace period)
            try:
                end_dt = datetime.fromisoformat(str(trial_end).replace("Z", "+00:00"))
                grace_end = end_dt + timedelta(hours=CONVERSION_GRACE_HOURS)
            except (ValueError, TypeError):
                continue

            now = datetime.now(timezone.utc)
            if now < grace_end:
                continue  # still within trial or grace period

            # Check if already converted
            email = t.get("email", "")
            product_slug = t.get("product_slug", "")
            if (email, product_slug) in converted:
                self.stats["skipped_already_converted"] += 1
                continue

            expired.append(t)

        return expired

    def _get_tier_price(self, product_slug: str, tier: str) -> Optional[float]:
        """Look up the monthly price for a given tier from the catalog."""
        product = PRODUCT_CATALOG.get(product_slug)
        if not product:
            return None
        tier_data = product["tiers"].get(tier)
        if not tier_data:
            return None
        return float(tier_data.get("price", 0))

    def _convert_trial(self, trial: dict) -> dict:
        """Convert a single expired trial to a paid subscription.

        Returns dict with status and details.
        """
        email = trial.get("email", "")
        product_slug = trial.get("product_slug", "")
        tier = trial.get("tier", "")

        if not email or not product_slug:
            return {"ok": False, "error": "Missing email or product_slug"}

        # Look up the tier price before handling subscription
        price = self._get_tier_price(product_slug, tier)
        if price is None or price <= 0:
            # Fallback: try to compute from tier name prefix
            price = self._compute_tier_price(tier)
        if price is None or price <= 0:
            return {"ok": False, "error": f"Could not determine price for tier '{tier}'"}

        # Find the subscription by customer_account_id (which is the email)
        sub = self.subscriptions.get_subscription(email)
        if not sub:
            # Fallback: auto-create a subscription via SuiteSubscriptionEngine
            log.info(f"[trial] no subscription found for {email} — auto-creating")
            create_result = self.subscriptions.create_subscription(
                customer_account_id=email,
                tier_level=tier,
                monthly_recurring_revenue=price,
                notes=f"Auto-created from trial conversion — {product_slug}/{tier}",
            )
            if not create_result.get("ok"):
                self.stats["errors"] += 1
                return {"ok": False, "error": create_result.get("error", "Create failed"),
                        "auto_create_attempted": True}
            sub = create_result.get("subscription") or self.subscriptions.get_subscription(email)
            sub_id = sub.get("subscription_id", "") if isinstance(sub, dict) else ""
            self.stats["auto_created"] += 1
            log.info(f"[trial] auto-created subscription for {email} → {tier} at ${price:.2f}/mo")
        else:
            # Skip if already paid (MRR > 0)
            current_mrr = float(sub.get("monthly_recurring_revenue", 0) or 0)
            if current_mrr > 0:
                self.stats["skipped_already_paid"] += 1
                return {"ok": False, "error": f"Subscription for {email} already has MRR ${current_mrr:.2f}"}

            # Update the subscription: set MRR to the tier price
            sub_id = sub.get("subscription_id", "")
            update_result = self.subscriptions.update_subscription(sub_id, {
                "monthly_recurring_revenue": price,
            })
            if not update_result.get("ok"):
                self.stats["errors"] += 1
                return {"ok": False, "error": update_result.get("error", "Update failed")}


        # Log the conversion event in sales_events
        try:
            db = self.get_db()
            db.table("sales_events").insert({
                "email": email,
                "product_slug": product_slug,
                "event_type": "trial_converted",
                "tier": tier,
                "amount_usd": price,
                "name": trial.get("name", ""),
                "company": trial.get("company", ""),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception as e:
            log.warning(f"[trial] failed to log conversion event: {e}")

        # Send conversion notification email
        if self.send_email and email:
            try:
                product_name = PRODUCT_CATALOG.get(product_slug, {}).get("name", product_slug)
                subject = f"Your {product_name} trial has been upgraded — you're now on {tier}"
                body = self._build_conversion_email(product_name, tier, price)
                asyncio.create_task(self._send_email_async(email, subject, body))
            except Exception as e:
                log.warning(f"[trial] conversion email send failed: {e}")

        self.stats["converted"] += 1
        log.info(
            f"[trial] converted {email} → {product_slug}/{tier} "
            f"(MRR: $0.00 → ${price:.2f}/mo)"
        )

        return {
            "ok": True,
            "email": email,
            "product_slug": product_slug,
            "tier": tier,
            "price": price,
            "subscription_id": sub_id,
        }

    @staticmethod
    def _compute_tier_price(tier: str) -> Optional[float]:
        """Fallback: estimate tier price from known tier patterns."""
        # Check TRIAL_CONFIG for the trial_tier mapping to find base price
        for slug, cfg in TRIAL_CONFIG.items():
            if cfg.get("trial_tier") == tier:
                # Look up in PRODUCT_CATALOG
                product = PRODUCT_CATALOG.get(slug)
                if product and tier in product["tiers"]:
                    return float(product["tiers"][tier].get("price", 0))
        return None

    @staticmethod
    def _build_conversion_email(product_name: str, tier: str, price: float) -> str:
        """Build a simple HTML email body for the conversion notification."""
        return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0a0f;color:#e2e8f0;padding:32px">
  <div style="max-width:560px;margin:0 auto;background:#14141e;border:1px solid #1e293b;border-radius:12px;padding:32px">
    <div style="font-size:28px;margin-bottom:4px">🚀</div>
    <h1 style="font-weight:200;font-size:22px;letter-spacing:-0.02em;margin:0 0 4px">Your Trial Has Been <em style="color:#44E5B8;font-style:italic;font-weight:500">Upgraded</em></h1>
    <p style="font-family:'SF Mono','Fira Code',monospace;font-size:10px;color:#94a3b8;letter-spacing:0.14em;text-transform:uppercase;margin:0 0 20px">{product_name} · {tier}</p>
    <p style="font-size:14px;color:#cbd5e1;line-height:1.7;margin:0 0 16px">
      Your free trial of <strong>{product_name}</strong> has ended, and we've automatically upgraded you to the <strong>{tier}</strong> plan at <strong style="color:#44E5B8">${price:.2f}/mo</strong>.
    </p>
    <p style="font-size:14px;color:#cbd5e1;line-height:1.7;margin:0 0 24px">
      You'll continue to have full access to all the features you've been using. Your billing cycle starts today.
    </p>
    <a href="https://empire-ai.co.uk/command#/products" style="display:inline-block;padding:12px 24px;background:#44E5B8;color:#000;text-decoration:none;font-weight:700;font-family:'SF Mono','Fira Code',monospace;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;border-radius:6px">Manage Subscription</a>
    <p style="font-size:12px;color:#64748b;line-height:1.5;margin:24px 0 0;padding-top:16px;border-top:1px solid #1e293b">
      If you'd like to cancel or change your plan, visit the Command Center. Questions? Reply to this email.
    </p>
  </div>
</body>
</html>"""

    async def _send_email_async(self, to: str, subject: str, body: str):
        """Send the email asynchronously."""
        if not self.send_email:
            return
        try:
            result = await self.send_email(to=to, subject=subject, html=body)
            if isinstance(result, dict) and result.get("ok"):
                return True
            else:
                log.warning(f"[trial] email send returned: {result}")
                return False
        except Exception as e:
            log.warning(f"[trial] email exception: {e}")
            return False

    # ═══════════════════════════════════════════════════════════════════
    # EXPIRING SOON REMINDERS
    # ═══════════════════════════════════════════════════════════════════

    def _find_trials_expiring_soon(self) -> list[dict]:
        """Query sales_events for trial_start rows ending in 3 or 1 days.

        Returns rows that:
          - Have event_type = 'trial_start'
          - Have trial_end within 1 or 3 days from now (exact day match)
          - Have no corresponding trial_converted event
          - Have no expiring_soon_reminder_sent event (to avoid repeats)
        """
        db = self.get_db()
        now = datetime.now(timezone.utc)

        # Fetch all trial_start events
        r = db.table("sales_events") \
            .select("*") \
            .eq("event_type", "trial_start") \
            .order("created_at", desc=False) \
            .execute()
        trials = r.data or []

        # Fetch all converted events for exclusion
        r2 = db.table("sales_events") \
            .select("email, product_slug") \
            .in_("event_type", ["trial_converted", "expiring_soon_reminder_sent"]) \
            .execute()
        excluded = set()
        for ev in (r2.data or []):
            excluded.add((ev.get("email", ""), ev.get("product_slug", "")))

        soon = []
        for t in trials:
            trial_end = t.get("trial_end")
            if not trial_end:
                continue

            try:
                end_dt = datetime.fromisoformat(str(trial_end).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue

            # Check if ending in approximately 1 or 3 days (rounded to nearest day)
            days_until = round((end_dt - now).total_seconds() / 86400)
            if days_until not in EXPIRING_SOON_DAYS:
                continue

            email = t.get("email", "")
            product_slug = t.get("product_slug", "")

            # Skip if already converted or already reminded
            if (email, product_slug) in excluded:
                self.stats.setdefault("skipped_already_reminded", 0)
                self.stats["skipped_already_reminded"] += 1
                continue

            soon.append({**t, "days_until": days_until})

        return soon

    @staticmethod
    def _build_expiring_soon_email(product_name: str, tier: str, price: float,
                                    days_until: int, email: str) -> str:
        """Build HTML email reminding user their trial is expiring soon."""
        urgency = "⚠️" if days_until <= 1 else "⏰"
        urgency_text = "tomorrow" if days_until <= 1 else f"in {days_until} days"
        return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0a0f;color:#e2e8f0;padding:32px">
  <div style="max-width:560px;margin:0 auto;background:#14141e;border:1px solid #1e293b;border-radius:12px;padding:32px">
    <div style="font-size:28px;margin-bottom:4px">{urgency}</div>
    <h1 style="font-weight:200;font-size:22px;letter-spacing:-0.02em;margin:0 0 4px">Your Trial Expires <em style="color:#FFB800;font-style:italic;font-weight:500">{urgency_text}</em></h1>
    <p style="font-family:'SF Mono','Fira Code',monospace;font-size:10px;color:#94a3b8;letter-spacing:0.14em;text-transform:uppercase;margin:0 0 20px">{product_name} · {tier}</p>
    <p style="font-size:14px;color:#cbd5e1;line-height:1.7;margin:0 0 8px">
      Your free trial of <strong>{product_name}</strong> is expiring <strong>{urgency_text}</strong>. To keep using it, upgrade to the <strong>{tier}</strong> plan.
    </p>
    <div style="background:#0f0f17;border:1px solid #1e293b;border-radius:8px;padding:16px;margin:16px 0">
      <div style="font-family:'SF Mono','Fira Code',monospace;font-size:10px;color:#94a3b8;letter-spacing:0.14em;text-transform:uppercase;margin-bottom:8px">Plan Details</div>
      <div style="font-size:14px;color:#e2e8f0;margin-bottom:4px">{product_name} · <strong>{tier}</strong></div>
      <div style="font-family:'SF Mono','Fira Code',monospace;font-size:24px;color:#44E5B8;font-weight:600">${price:.2f}<span style="font-size:12px;color:#94a3b8;font-weight:400">/mo</span></div>
    </div>
    <p style="font-size:13px;color:#94a3b8;line-height:1.6;margin:0 0 24px">
      If you don't upgrade, your access will be automatically converted to a paid plan. You can also cancel anytime.
    </p>
    <a href="https://empire-ai.co.uk/command#/products" style="display:inline-block;padding:12px 24px;background:#44E5B8;color:#000;text-decoration:none;font-weight:700;font-family:'SF Mono','Fira Code',monospace;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;border-radius:6px">Upgrade Now</a>
    <p style="font-size:12px;color:#64748b;line-height:1.5;margin:24px 0 0;padding-top:16px;border-top:1px solid #1e293b">
      Questions? Reply to this email or visit the <a href="https://empire-ai.co.uk/command" style="color:#44E5B8">Command Center</a>.
    </p>
  </div>
</body>
</html>"""

    async def _send_expiring_soon_reminders(self):
        """Find trials expiring soon and send reminder emails."""
        soon = self._find_trials_expiring_soon()
        sent_count = 0
        for trial in soon:
            email = trial.get("email", "")
            product_slug = trial.get("product_slug", "")
            tier = trial.get("tier", "")
            days_until = trial.get("days_until", 3)

            if not email or not product_slug:
                continue

            product_name = PRODUCT_CATALOG.get(product_slug, {}).get("name", product_slug)
            price = self._get_tier_price(product_slug, tier) or 0

            subject = f"⏰ Your {product_name} trial expires {days_until}d" if days_until > 1 \
                      else f"⚠️ Your {product_name} trial expires tomorrow"
            body = self._build_expiring_soon_email(product_name, tier, price, days_until, email)

            ok = await self._send_email_async(email, subject, body)
            if ok:
                sent_count += 1
                self.stats["expiring_soon_reminders_sent"] += 1

                # Log the reminder event in sales_events to prevent repeats
                try:
                    db = self.get_db()
                    db.table("sales_events").insert({
                        "email": email,
                        "product_slug": product_slug,
                        "event_type": "expiring_soon_reminder_sent",
                        "tier": tier,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }).execute()
                except Exception as e:
                    log.debug(f"[trial] failed to log reminder event: {e}")

                log.info(f"[trial] sent expiring-soon reminder ({days_until}d) to {email} for {product_slug}")

        if sent_count:
            log.info(f"[trial] sent {sent_count} expiring-soon reminder(s)")
        return sent_count

    # ═══════════════════════════════════════════════════════════════════
    # WIN-BACK EMAILS
    # ═══════════════════════════════════════════════════════════════════

    @staticmethod
    def _build_win_back_email(product_name: str, tier: str, price: float) -> str:
        """Build HTML reactivation email for churned trial users."""
        return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0a0f;color:#e2e8f0;padding:32px">
  <div style="max-width:560px;margin:0 auto;background:#14141e;border:1px solid #1e293b;border-radius:12px;padding:32px;text-align:center">
    <div style="font-size:36px;margin-bottom:8px">🔄</div>
    <h1 style="font-weight:200;font-size:24px;letter-spacing:-0.02em;margin:0 0 4px">We Miss You at <em style="color:#44E5B8;font-style:italic;font-weight:500">{product_name}</em></h1>
    <p style="font-family:'SF Mono','Fira Code',monospace;font-size:10px;color:#94a3b8;letter-spacing:0.14em;text-transform:uppercase;margin:0 0 20px">Come back · Reactivate your {tier} plan</p>
    <p style="font-size:14px;color:#cbd5e1;line-height:1.7;margin:0 0 8px">
      You recently unsubscribed from <strong>{product_name}</strong>. We'd love to have you back.
    </p>
    <div style="background:#0f0f17;border:1px solid #1e293b;border-radius:8px;padding:20px;margin:16px 0;text-align:left">
      <div style="font-family:'SF Mono','Fira Code',monospace;font-size:10px;color:#94a3b8;letter-spacing:0.14em;text-transform:uppercase;margin-bottom:12px">Your Previous Plan</div>
      <div style="font-size:14px;color:#e2e8f0;margin-bottom:4px">{product_name} · <strong>{tier}</strong></div>
      <div style="font-family:'SF Mono','Fira Code',monospace;font-size:28px;color:#44E5B8;font-weight:600">${price:.2f}<span style="font-size:12px;color:#94a3b8;font-weight:400">/mo</span></div>
      <div style="font-size:12px;color:#94a3b8;line-height:1.6;margin-top:8px;padding-top:12px;border-top:1px solid #1e293b">
        ✓ Full feature access · Priority support · No setup fees
      </div>
    </div>
    <p style="font-size:13px;color:#94a3b8;line-height:1.6;margin:0 0 24px">
      Reactivate within 30 days and we'll honor your previous rate. No questions asked.
    </p>
    <a href="https://empire-ai.co.uk/command#/products" style="display:inline-block;padding:14px 32px;background:#44E5B8;color:#000;text-decoration:none;font-weight:700;font-family:'SF Mono','Fira Code',monospace;font-size:12px;letter-spacing:0.14em;text-transform:uppercase;border-radius:6px">Reactivate Now</a>
    <p style="font-size:11px;color:#64748b;line-height:1.5;margin:24px 0 0;padding-top:16px;border-top:1px solid #1e293b">
      Questions or want a different plan? Reply to this email and we'll help.
    </p>
  </div>
</body>
</html>"""

    async def _send_win_back(self, email: str, product_slug: str, tier: str) -> bool:
        """Send a win-back reactivation email for a churned trial.

        Checks for existing win_back_sent event to avoid repeat sends.
        Returns True if email was sent.
        """
        if not self.send_email or not email:
            return False

        db = self.get_db()

        # Check if win-back already sent for this churn
        r = db.table("sales_events") \
            .select("id") \
            .eq("email", email) \
            .eq("product_slug", product_slug) \
            .eq("event_type", "win_back_sent") \
            .limit(1) \
            .execute()
        if r.data:
            log.debug(f"[trial] win-back already sent to {email} for {product_slug}")
            return False

        product_name = PRODUCT_CATALOG.get(product_slug, {}).get("name", product_slug)
        price = self._get_tier_price(product_slug, tier) or 0

        subject = f"🔄 Come back to {product_name} — reactivate your {tier} plan"
        body = self._build_win_back_email(product_name, tier, price)

        ok = await self._send_email_async(email, subject, body)
        if ok:
            self.stats["win_backs_sent"] += 1

            # Log the event to prevent repeat sends
            try:
                db.table("sales_events").insert({
                    "email": email,
                    "product_slug": product_slug,
                    "event_type": "win_back_sent",
                    "tier": tier,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }).execute()
            except Exception as e:
                log.debug(f"[trial] failed to log win_back_sent event: {e}")

            log.info(f"[trial] win-back email sent to {email} for {product_slug}/{tier}")

        return ok

    # ═══════════════════════════════════════════════════════════════════
    # TRIAL CHURN TRACKING
    # ═══════════════════════════════════════════════════════════════════

    def track_churn(self, reason: Optional[str] = None) -> list[dict]:
        """Scan converted trials for subscriptions that have since churned.

        Looks for trial_converted events, checks the subscription status,
        and logs a trial_churned event if the sub is now CANCELED/PAST_DUE
        and no trial_churned event has been logged yet.

        Args:
            reason: Optional default reason string ("auto-detected" if None).

        Returns:
            List of churn events logged this scan.
        """
        db = self.get_db()
        reason = reason or "auto-detected: subscription status changed"

        # Fetch all trial_converted events
        r = db.table("sales_events") \
            .select("email, product_slug, tier, amount_usd, name, company, created_at") \
            .eq("event_type", "trial_converted") \
            .order("created_at", desc=True) \
            .execute()
        converted = r.data or []

        # Fetch all trial_churned events for dedup
        r2 = db.table("sales_events") \
            .select("email, product_slug") \
            .eq("event_type", "trial_churned") \
            .execute()
        already_churned = set()
        for ev in (r2.data or []):
            already_churned.add((ev.get("email", ""), ev.get("product_slug", "")))

        logged = []
        for conv in converted:
            email = conv.get("email", "")
            product_slug = conv.get("product_slug", "")

            if not email or not product_slug:
                continue

            # Skip if already logged
            key = (email, product_slug)
            if key in already_churned:
                continue

            # Check subscription status
            sub = self.subscriptions.get_subscription(email)
            if not sub:
                # Subscription gone entirely — treat as churn
                status = "CANCELED"
                old_mrr = float(conv.get("amount_usd", 0) or 0)
            else:
                status = sub.get("subscription_status", "ACTIVE")
                if status not in ("CANCELED", "PAST_DUE"):
                    continue  # still active — skip
                old_mrr = float(sub.get("monthly_recurring_revenue", 0) or 0)

            # Log the trial_churned event
            notes = f"Churn detected: {reason[:200]} | prior: {product_slug}/{conv.get('tier','')} at ${old_mrr:.2f}/mo"
            try:
                db.table("sales_events").insert({
                    "email": email,
                    "product_slug": product_slug,
                    "event_type": "trial_churned",
                    "tier": conv.get("tier", ""),
                    "amount_usd": old_mrr,
                    "notes": notes,
                    "name": conv.get("name", ""),
                    "company": conv.get("company", ""),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }).execute()
            except Exception as e:
                log.warning(f"[trial] failed to log churn event for {email}: {e}")
                continue

            self.stats["churn_detected"] += 1
            logged.append({
                "email": email,
                "product_slug": product_slug,
                "tier": conv.get("tier", ""),
                "prior_mrr": old_mrr,
                "status": status,
                "reason": reason[:200],
            })
            log.info(f"[trial] churn detected: {email} → {product_slug} ({status}) lost ${old_mrr:.2f}/mo")

            # Send win-back reactivation email
            tier = conv.get("tier", "")
            asyncio.create_task(self._send_win_back(email, product_slug, tier))

        if logged:
            log.info(f"[trial] churn scan: {len(logged)} new churn event(s) logged, win-backs dispatched")
        return logged

    def report_churn(self, email: str, product_slug: str, reason: str) -> dict:
        """Manually report a churn reason for a converted trial.

        Args:
            email: Trial user's email.
            product_slug: Product slug.
            reason: Operator-provided churn reason.

        Returns:
            {"ok": True/False, ...}
        """
        if not email or not product_slug or not reason:
            return {"ok": False, "error": "email, product_slug, and reason are required"}

        db = self.get_db()

        # Verify a trial_converted event exists
        r = db.table("sales_events") \
            .select("*") \
            .eq("email", email) \
            .eq("product_slug", product_slug) \
            .eq("event_type", "trial_converted") \
            .limit(1) \
            .execute()
        if not r.data:
            return {"ok": False, "error": f"No trial_converted event found for {email}/{product_slug}"}

        conv = r.data[0]

        # Check if already churn-logged
        r2 = db.table("sales_events") \
            .select("id") \
            .eq("email", email) \
            .eq("product_slug", product_slug) \
            .eq("event_type", "trial_churned") \
            .limit(1) \
            .execute()
        if r2.data:
            # Update the existing churn event with new reason
            try:
                db.table("sales_events") \
                    .update({"notes": f"Churn reason updated: {reason[:500]}"}) \
                    .eq("id", r2.data[0]["id"]) \
                    .execute()
                self.stats["churn_reported"] += 1
                return {"ok": True, "updated": True, "email": email, "product_slug": product_slug, "reason": reason[:500]}
            except Exception as e:
                return {"ok": False, "error": f"Failed to update churn reason: {e}"}

        # Check subscription status
        sub = self.subscriptions.get_subscription(email)
        status = sub.get("subscription_status", "CANCELED") if sub else "CANCELED"
        old_mrr = float(conv.get("amount_usd", 0) or 0)

        notes = f"Churn reported by operator: {reason[:400]}"
        try:
            db.table("sales_events").insert({
                "email": email,
                "product_slug": product_slug,
                "event_type": "trial_churned",
                "tier": conv.get("tier", ""),
                "amount_usd": old_mrr,
                "notes": notes,
                "name": conv.get("name", ""),
                "company": conv.get("company", ""),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception as e:
            return {"ok": False, "error": f"Failed to log churn event: {e}"}

        self.stats["churn_reported"] += 1
        log.info(f"[trial] churn reported by operator: {email} → {product_slug} — {reason[:80]}")

        # Send win-back reactivation email
        asyncio.create_task(self._send_win_back(email, product_slug, conv.get("tier", "")))

        return {
            "ok": True,
            "email": email,
            "product_slug": product_slug,
            "tier": conv.get("tier", ""),
            "prior_mrr": old_mrr,
            "status": status,
            "reason": reason[:500],
            "win_back_dispatched": True,
        }

    # ═══════════════════════════════════════════════════════════════════
    # RUN LOOP
    # ═══════════════════════════════════════════════════════════════════

    def run_once(self) -> dict:
        """Scan for expired trials and convert them. Returns summary."""
        self.stats["scans"] += 1
        expired = self._find_expired_trials()
        results = []
        for trial in expired:
            result = self._convert_trial(trial)
            results.append(result)
        summary = {
            "scanned": len(expired),
            "converted": sum(1 for r in results if r.get("ok")),
            "failed": sum(1 for r in results if not r.get("ok")),
            "details": results,
        }
        log.info(
            f"[trial] scan complete: {summary['scanned']} expired, "
            f"{summary['converted']} converted, {summary['failed']} failed"
        )
        return summary

    async def monitoring_loop(self):
        """Background loop: send expiring-soon reminders + convert expired trials + track churn."""
        await asyncio.sleep(300)  # let hub finish booting (5 min)
        log.info("[trial] monitoring loop started (interval=%ds)", CHECK_INTERVAL_SEC)
        while not self._stop_loop:
            try:
                # 0. Track churn on converted trials (runs first to catch churns promptly)
                self.track_churn()
                # 1. Send expiring-soon reminders (trials ending in 3 or 1 days)
                await self._send_expiring_soon_reminders()
                # 2. Convert expired trials (ended more than 24h ago)
                self.run_once()
            except Exception as e:
                log.warning(f"[trial] monitoring error: {e}")
            await asyncio.sleep(CHECK_INTERVAL_SEC)

    def stop(self):
        self._stop_loop = True

    # ── Trial Pipeline Stats ────────────────────────────────────────

    def trial_pipeline_stats(self) -> dict:
        """Aggregate stats for the trial pipeline SPA view.

        Returns:
          - active: count of trials still within trial period
          - expiring_soon: count ending within 7 days
          - expired_unconverted: past grace period, no trial_converted event
          - converted: total trial_converted events
          - churned: converted trials whose subscription is now canceled/past_due
          - win_rate: converted / (converted + expired_unconverted)
          - potential_monthly_mrr: sum of tier prices for active trials
          - daily_starts: trial_start count per day for last 14 days
          - by_product: breakdown per product_slug
          - recent: last 20 trial_start events with status
        """
        db = self.get_db()
        now = datetime.now(timezone.utc)

        # Fetch all trial_start events
        r = db.table("sales_events") \
            .select("*") \
            .eq("event_type", "trial_start") \
            .order("created_at", desc=True) \
            .execute()
        trials = r.data or []

        # Fetch all trial_converted events
        r2 = db.table("sales_events") \
            .select("email, product_slug, tier, created_at, amount_usd") \
            .eq("event_type", "trial_converted") \
            .execute()
        converted_events = r2.data or []
        converted_by_key: dict[str, dict] = {}
        for ev in converted_events:
            key = (ev.get("email", ""), ev.get("product_slug", ""))
            converted_by_key[key] = ev

        # Fetch all subscriptions to check churn status
        all_subs = self.subscriptions.list_subscriptions() if hasattr(self.subscriptions, 'list_subscriptions') else []
        sub_by_account: dict[str, dict] = {}
        for s in all_subs:
            sub_by_account[s.get("customer_account_id", "")] = s

        # Fetch all trial_churned events for churn stats
        r_churn = db.table("sales_events") \
            .select("email, product_slug, amount_usd, notes") \
            .eq("event_type", "trial_churned") \
            .execute()
        churned_events = r_churn.data or []
        churned_by_key: dict[str, dict] = {}
        total_mrr_lost = 0.0
        reason_groups: dict[str, int] = {}
        for ev in churned_events:
            key = (ev.get("email", ""), ev.get("product_slug", ""))
            churned_by_key[key] = ev
            mrr = float(ev.get("amount_usd", 0) or 0)
            total_mrr_lost += mrr
            # Extract reason from notes for grouping
            notes = (ev.get("notes") or "")
            if "reported by operator" in notes:
                reason_groups["operator_reported"] = reason_groups.get("operator_reported", 0) + 1
            elif "pricing" in notes.lower() or "price" in notes.lower() or "cost" in notes.lower():
                reason_groups["pricing"] = reason_groups.get("pricing", 0) + 1
            elif "feature" in notes.lower() or "capability" in notes.lower():
                reason_groups["missing_features"] = reason_groups.get("missing_features", 0) + 1
            elif "support" in notes.lower():
                reason_groups["support"] = reason_groups.get("support", 0) + 1
            elif "competitor" in notes.lower() or "switching" in notes.lower():
                reason_groups["competitor"] = reason_groups.get("competitor", 0) + 1
            else:
                reason_groups["other"] = reason_groups.get("other", 0) + 1

        # Categorize each trial
        active = 0
        expiring_soon = 0
        expired_unconverted = 0
        converted_count = 0
        churned = 0
        potential_mrr = 0.0
        by_product: dict[str, dict] = {}
        daily_starts: dict[str, int] = {}
        recent_trials: list[dict] = []

        for t in trials:
            email = t.get("email", "")
            product_slug = t.get("product_slug", "")
            tier = t.get("tier", "")
            trial_end_str = t.get("trial_end", "")
            created_str = t.get("created_at", "")

            # Daily breakdown
            if created_str:
                day = str(created_str)[:10]
                daily_starts[day] = daily_starts.get(day, 0) + 1

            # Determine trial end
            if not trial_end_str:
                continue
            try:
                end_dt = datetime.fromisoformat(str(trial_end_str).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue

            grace_end = end_dt + timedelta(hours=CONVERSION_GRACE_HOURS)
            key = (email, product_slug)
            is_converted = key in converted_by_key

            if is_converted:
                converted_count += 1
                # Check if the converted subscription later churned
                if key in churned_by_key:
                    churned += 1
            elif now < end_dt:
                active += 1
                # Check if expiring soon (within 7 days)
                days_left = round((end_dt - now).total_seconds() / 86400)
                if 1 <= days_left <= 7:
                    expiring_soon += 1
                # Estimate potential MRR
                price = self._get_tier_price(product_slug, tier) or 0
                potential_mrr += price
            elif now < grace_end:
                # In grace period — still counts as active-ish but expiring
                expiring_soon += 1
                price = self._get_tier_price(product_slug, tier) or 0
                potential_mrr += price
            else:
                expired_unconverted += 1

            # By-product breakdown
            if product_slug not in by_product:
                by_product[product_slug] = {
                    "product": product_slug,
                    "name": PRODUCT_NAMES.get(product_slug, product_slug),
                    "trials": 0,
                    "active": 0,
                    "converted": 0,
                    "expired": 0,
                }
            bp = by_product[product_slug]
            bp["trials"] += 1
            if is_converted:
                bp["converted"] += 1
            elif now < end_dt:
                bp["active"] += 1
            else:
                bp["expired"] += 1

            # Recent trials list (last 20)
            if len(recent_trials) < 20:
                status = "converted" if is_converted else ("active" if now < end_dt else ("grace" if now < grace_end else "expired"))
                product_name = PRODUCT_NAMES.get(product_slug, product_slug)
                recent_trials.append({
                    "email": email,
                    "product": product_name,
                    "product_slug": product_slug,
                    "tier": tier,
                    "trial_end": str(trial_end_str)[:19],
                    "created": str(created_str)[:19] if created_str else "",
                    "status": status,
                    "days_left": round((end_dt - now).total_seconds() / 86400) if now < end_dt else 0,
                })

        total_expired_or_converted = converted_count + expired_unconverted
        win_rate = round(converted_count / total_expired_or_converted, 3) if total_expired_or_converted > 0 else 0

        # Sort reason groups for display
        top_reasons = [{"reason": k.replace("_", " ").title(), "count": v}
                       for k, v in sorted(reason_groups.items(), key=lambda x: -x[1])]

        return {
            "summary": {
                "total_trial_starts": len(trials),
                "active": active,
                "expiring_soon": expiring_soon,
                "expired_unconverted": expired_unconverted,
                "converted": converted_count,
                "churned": churned,
                "win_rate": win_rate,
                "potential_monthly_mrr": round(potential_mrr, 2),
                "grace_hours": CONVERSION_GRACE_HOURS,
            },
            "churn_stats": {
                "total_mrr_lost": round(total_mrr_lost, 2),
                "total_churned": len(churned_events),
                "churn_rate": round(churned / max(converted_count, 1), 3),
                "mrr_per_churn": round(total_mrr_lost / max(len(churned_events), 1), 2),
                "top_reasons": top_reasons,
            },
            "by_product": sorted(by_product.values(), key=lambda x: x["trials"], reverse=True),
            "daily_starts": [{"date": k, "count": v} for k, v in sorted(daily_starts.items(), reverse=True)],
            "recent": recent_trials,
            "engine_stats": dict(self.stats),
        }

    # ── Trial Audit History ────────────────────────────────────────

    def trial_audit_history(self, limit: int = 50, offset: int = 0,
                             event_type: Optional[str] = None) -> dict:
        """Return recent trial audit events for operator visibility.

        Queries sales_events for trial-related event types:
          - trial_start
          - trial_converted
          - expiring_soon_reminder_sent

        Args:
            limit: Max events to return (default 50, max 200).
            offset: Pagination offset.
            event_type: Optional filter — one of the event types above, or None for all.

        Returns:
            {
                "events": [...],
                "total": total matching events,
                "limit": limit,
                "offset": offset,
                "event_types": [...unique types present],
            }
        """
        db = self.get_db()
        limit = max(1, min(limit, 200))
        offset = max(0, offset)

        # Build the query
        trial_event_types = ["trial_start", "trial_converted", "expiring_soon_reminder_sent"]
        query = db.table("sales_events") \
            .select("*") \
            .in_("event_type", [event_type] if event_type else trial_event_types) \
            .order("created_at", desc=True)

        # Count total matching events
        try:
            count_res = db.table("sales_events") \
                .select("id", count="exact") \
                .in_("event_type", [event_type] if event_type else trial_event_types) \
                .execute()
            total = getattr(count_res, "count", 0) or len(count_res.data or [])
        except Exception:
            total = 0

        # Fetch paginated results
        r = query.range(offset, offset + limit - 1).execute()
        raw = r.data or []

        events = []
        for ev in raw:
            et = ev.get("event_type", "")
            created = str(ev.get("created_at", ""))[:19] if ev.get("created_at") else ""

            entry = {
                "id": ev.get("id", ""),
                "event_type": et,
                "created_at": created,
                "email": ev.get("email", ""),
                "product_slug": ev.get("product_slug", ""),
                "product_name": PRODUCT_NAMES.get(ev.get("product_slug", ""), ev.get("product_slug", "")),
                "tier": ev.get("tier", ""),
            }

            # Enrich with event-specific fields
            if et == "trial_start":
                entry["trial_end"] = str(ev.get("trial_end", ""))[:19] if ev.get("trial_end") else ""
                entry["name"] = ev.get("name", "")
                entry["company"] = ev.get("company", "")
                entry["max_checks"] = ev.get("max_checks", "")
                # Determine if still active
                trial_end = ev.get("trial_end")
                if trial_end:
                    try:
                        end_dt = datetime.fromisoformat(str(trial_end).replace("Z", "+00:00"))
                        now = datetime.now(timezone.utc)
                        if now < end_dt:
                            days = round((end_dt - now).total_seconds() / 86400)
                            entry["days_remaining"] = max(0, days)
                            entry["trial_status"] = "active"
                        elif now < end_dt + timedelta(hours=CONVERSION_GRACE_HOURS):
                            entry["trial_status"] = "grace"
                        else:
                            entry["trial_status"] = "expired"
                    except (ValueError, TypeError):
                        entry["trial_status"] = "unknown"
            elif et == "trial_converted":
                entry["amount_usd"] = float(ev.get("amount_usd", 0) or 0)
            elif et == "expiring_soon_reminder_sent":
                entry["days_until"] = ev.get("days_until", None)

            events.append(entry)

        # Collect unique event types present
        present_types = sorted(set(e["event_type"] for e in events))

        return {
            "events": events,
            "total": total,
            "limit": limit,
            "offset": offset,
            "event_types": present_types,
        }

    # ── Trial Grace Extension ───────────────────────────────────────

    def extend_trial_grace(self, email: str, product_slug: str,
                            extra_days: int, reason: str = "") -> dict:
        """Extend a trial's grace period by adding extra days to trial_end.

        Looks up the trial_start event by email + product_slug, verifies the
        trial hasn't already been converted, then updates trial_end and logs
        a trial_extended event.

        Args:
            email: Trial user's email.
            product_slug: Product slug for the trial.
            extra_days: Number of days to add (1-90).
            reason: Operator-provided reason for the extension.

        Returns:
            {
                "ok": True/False,
                "old_trial_end": "...",
                "new_trial_end": "...",
                "extra_days": N,
                "error": "..." (if not ok),
            }
        """
        extra_days = max(1, min(extra_days, 90))

        if not email or not product_slug:
            return {"ok": False, "error": "email and product_slug are required"}

        db = self.get_db()

        # Find the trial_start event
        r = db.table("sales_events") \
            .select("*") \
            .eq("email", email) \
            .eq("product_slug", product_slug) \
            .eq("event_type", "trial_start") \
            .limit(1) \
            .execute()
        trials = r.data or []
        if not trials:
            return {"ok": False, "error": f"No trial_start event found for {email}/{product_slug}"}

        trial = trials[0]
        trial_id = trial.get("id", "")

        # Check if already converted
        r2 = db.table("sales_events") \
            .select("id") \
            .eq("email", email) \
            .eq("product_slug", product_slug) \
            .eq("event_type", "trial_converted") \
            .limit(1) \
            .execute()
        if r2.data:
            return {"ok": False, "error": f"Trial for {email}/{product_slug} has already been converted"}

        # Compute new trial_end
        old_trial_end = trial.get("trial_end", "")
        try:
            old_end_dt = datetime.fromisoformat(str(old_trial_end).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            old_end_dt = datetime.now(timezone.utc)

        new_end_dt = old_end_dt + timedelta(days=extra_days)
        new_trial_end_iso = new_end_dt.isoformat()

        # Update the trial_start record's trial_end
        try:
            db.table("sales_events") \
                .update({"trial_end": new_trial_end_iso}) \
                .eq("id", trial_id) \
                .execute()
        except Exception as e:
            self.stats["errors"] += 1
            return {"ok": False, "error": f"Failed to update trial_end: {e}"}

        # Log the trial_extended event (details go in notes column to match schema)
        try:
            notes = f"Extended {extra_days}d — reason: {reason[:200]} | old_end: {str(old_trial_end)[:19]} → new_end: {str(new_trial_end_iso)[:19]}"
            db.table("sales_events").insert({
                "email": email,
                "product_slug": product_slug,
                "event_type": "trial_extended",
                "tier": trial.get("tier", ""),
                "name": trial.get("name", ""),
                "company": trial.get("company", ""),
                "notes": notes,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception as e:
            log.warning(f"[trial] failed to log trial_extended event: {e}")

        self.stats["extensions"] = self.stats.get("extensions", 0) + 1
        log.info(f"[trial] extended trial for {email}/{product_slug} by {extra_days}d (reason: {reason[:80]})")

        return {
            "ok": True,
            "email": email,
            "product_slug": product_slug,
            "extra_days": extra_days,
            "old_trial_end": str(old_trial_end)[:19],
            "new_trial_end": str(new_trial_end_iso)[:19],
            "reason": reason[:500],
        }

    # ── Stats snapshot ──────────────────────────────────────────────

    def stats_snapshot(self) -> dict:
        return {
            "engine": dict(self.stats),
            "check_interval_sec": CHECK_INTERVAL_SEC,
            "conversion_grace_hours": CONVERSION_GRACE_HOURS,
            "expiring_soon_days": EXPIRING_SOON_DAYS,
        }
