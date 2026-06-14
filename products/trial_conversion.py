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
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional

from products.sales_funnel import PRODUCT_CATALOG, TRIAL_CONFIG
from products.product_email_sequences import PRODUCT_NAMES

log = logging.getLogger("empire.trial_conversion")

# ── Config ───────────────────────────────────────────────────────────────
CHECK_INTERVAL_SEC = 3600       # check every hour
CONVERSION_GRACE_HOURS = 24     # wait 24h after trial ends before auto-converting
SLA_BUFFER_HOURS = 24           # additional buffer before flagging as SLA breach (trial_end + grace + buffer)
EXPIRING_SOON_DAYS = [3, 1]     # send reminders N days before trial ends
WIN_BACK_FOLLOWUP_DAYS = 7  # send follow-up win-back email N days after first win-back

# ── Win-back A/B variant system ─────────────────────────────────────────
# Each variant has:
#   - id: unique identifier
#   - name: display name for the SPA
#   - subject: subject line template ({product_name}, {tier}, {price} placeholders)
#   - tone: 'warm' | 'urgent' — determines which email builder to use
#   - weight: split ratio weight (e.g., 50 = 50% of traffic)

WIN_BACK_VARIANTS_DEFAULT = [
    {
        "id": "A",
        "name": "Warm Reassurance",
        "subject": "We Miss You at {product_name} — reactivate your {tier} plan",
        "tone": "warm",
        "weight": 50,
    },
    {
        "id": "B",
        "name": "Urgent Action",
        "subject": "Your {product_name} {tier} access is at risk — reactivate now",
        "tone": "urgent",
        "weight": 50,
    },
]


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
            "win_back_followups_sent": 0,
            "win_backs_opted_out": 0,
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
    def _build_win_back_followup_email(product_name: str, tier: str, price: float) -> str:
        """Build HTML second-touch win-back email — more urgent/last-chance tone."""
        return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0a0f;color:#e2e8f0;padding:32px">
  <div style="max-width:560px;margin:0 auto;background:#14141e;border:1px solid #1e293b;border-radius:12px;padding:32px;text-align:center">
    <div style="font-size:36px;margin-bottom:8px">⏳</div>
    <h1 style="font-weight:200;font-size:24px;letter-spacing:-0.02em;margin:0 0 4px">Last Chance — <em style="color:#44E5B8;font-style:italic;font-weight:500">{product_name}</em></h1>
    <p style="font-family:'SF Mono','Fira Code',monospace;font-size:10px;color:#94a3b8;letter-spacing:0.14em;text-transform:uppercase;margin:0 0 20px">Your reactivation offer expires soon</p>
    <p style="font-size:14px;color:#cbd5e1;line-height:1.7;margin:0 0 8px">
      A week ago we reached out about reactivating your <strong>{tier}</strong> plan. This is a final reminder — your previous rate of <strong style="color:#44E5B8">${price:.2f}/mo</strong> won't be available forever.
    </p>
    <div style="background:#0f0f17;border:1px solid #1e293b;border-radius:8px;padding:20px;margin:16px 0;text-align:left">
      <div style="font-family:'SF Mono','Fira Code',monospace;font-size:10px;color:#94a3b8;letter-spacing:0.14em;text-transform:uppercase;margin-bottom:12px">Still Available</div>
      <div style="font-size:14px;color:#e2e8f0;margin-bottom:4px">{product_name} · <strong>{tier}</strong></div>
      <div style="font-family:'SF Mono','Fira Code',monospace;font-size:28px;color:#44E5B8;font-weight:600">${price:.2f}<span style="font-size:12px;color:#94a3b8;font-weight:400">/mo</span></div>
      <div style="font-size:12px;color:#94a3b8;line-height:1.6;margin-top:8px;padding-top:12px;border-top:1px solid #1e293b">
        ✓ Full feature access · Priority support · No setup fees
      </div>
    </div>
    <p style="font-size:13px;color:#FFB800;line-height:1.6;margin:0 0 24px">
      ⚠️ This offer will expire in 7 days. Reactivate now to lock in your rate.
    </p>
    <a href="https://empire-ai.co.uk/command#/products" style="display:inline-block;padding:14px 32px;background:#44E5B8;color:#000;text-decoration:none;font-weight:700;font-family:'SF Mono','Fira Code',monospace;font-size:12px;letter-spacing:0.14em;text-transform:uppercase;border-radius:6px">Reactivate Now</a>
    <p style="font-size:11px;color:#64748b;line-height:1.5;margin:24px 0 0;padding-top:16px;border-top:1px solid #1e293b">
      Questions? Reply to this email — we're here to help.
    </p>
  </div>
</body>
</html>"""

    async def _send_win_back_followups(self) -> int:
        """Send follow-up win-back emails for churns where 7+ days have passed since first win-back.

        Scans win_back_sent events older than WIN_BACK_FOLLOWUP_DAYS, checks no
        trial_converted event exists for the same email+product AFTER the first win-back
        (meaning the user hasn't reactivated), and sends a second-touch email.

        Returns count of followups sent.
        """
        if not self.send_email:
            return 0

        db = self.get_db()
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=WIN_BACK_FOLLOWUP_DAYS)

        # Fetch all win_back_sent events older than cutoff
        r = db.table("sales_events") \
            .select("email, product_slug, tier, created_at") \
            .eq("event_type", "win_back_sent") \
            .order("created_at", desc=False) \
            .execute()
        win_backs = r.data or []

        # Fetch all win_back_followup_sent events for dedup
        r2 = db.table("sales_events") \
            .select("email, product_slug") \
            .eq("event_type", "win_back_followup_sent") \
            .execute()
        already_followed = set()
        for ev in (r2.data or []):
            already_followed.add((ev.get("email", ""), ev.get("product_slug", "")))

        # Fetch all trial_converted events to check for reactivation
        r3 = db.table("sales_events") \
            .select("email, product_slug, created_at") \
            .eq("event_type", "trial_converted") \
            .order("created_at", desc=False) \
            .execute()
        converted_events = r3.data or []

        # Build opt-out set once for efficient lookup
        r4 = db.table("sales_events") \
            .select("email, product_slug") \
            .eq("event_type", "win_back_opted_out") \
            .execute()
        opted_out_set = set()
        for ev in (r4.data or []):
            opted_out_set.add((ev.get("email", ""), ev.get("product_slug", "")))

        sent_count = 0
        for wb in win_backs:
            email = wb.get("email", "")
            product_slug = wb.get("product_slug", "")
            tier = wb.get("tier", "")
            created_str = wb.get("created_at", "")

            if not email or not product_slug:
                continue

            # Check if followup already sent
            key = (email, product_slug)
            if key in already_followed:
                continue

            # Check if user opted out (fast set lookup, no extra DB query)
            if key in opted_out_set:
                log.debug(f"[trial] win-back followup skipped — {email} opted out of {product_slug}")
                continue

            # Check if win_back_sent is old enough
            if not created_str:
                continue
            try:
                wb_dt = datetime.fromisoformat(str(created_str).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue

            if wb_dt > cutoff:
                continue  # not yet 7 days old

            # Check if the user reactivated (new trial_converted event after win_back)
            reactivated = False
            for conv in converted_events:
                if conv.get("email") == email and conv.get("product_slug") == product_slug:
                    conv_created = conv.get("created_at", "")
                    if conv_created:
                        try:
                            conv_dt = datetime.fromisoformat(str(conv_created).replace("Z", "+00:00"))
                            if conv_dt > wb_dt:
                                reactivated = True
                                break
                        except (ValueError, TypeError):
                            pass

            if reactivated:
                log.debug(f"[trial] win-back followup skipped — {email} already reactivated {product_slug}")
                continue

            # Send followup email
            product_name = PRODUCT_CATALOG.get(product_slug, {}).get("name", product_slug)
            price = self._get_tier_price(product_slug, tier) or 0

            subject = f"⏳ Last chance — {product_name} {tier} at ${price:.0f}/mo"
            body = self._build_win_back_followup_email(product_name, tier, price)

            ok = await self._send_email_async(email, subject, body)
            if ok:
                sent_count += 1
                self.stats["win_back_followups_sent"] += 1

                # Log to prevent repeats
                try:
                    db.table("sales_events").insert({
                        "email": email,
                        "product_slug": product_slug,
                        "event_type": "win_back_followup_sent",
                        "tier": tier,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }).execute()
                except Exception as e:
                    log.debug(f"[trial] failed to log win_back_followup_sent: {e}")

                log.info(f"[trial] win-back followup sent to {email} for {product_slug}/{tier}")

        if sent_count:
            log.info(f"[trial] win-back followup scan: {sent_count} followup(s) sent")
        return sent_count

    # ═══════════════════════════════════════════════════════════════════
    # WIN-BACK A/B VARIANT SYSTEM
    # ═══════════════════════════════════════════════════════════════════

    def _read_win_back_config(self) -> dict:
        """Read win-back A/B variant config from agent_config table.

        Returns dict with:
          - enabled: bool
          - variants: list of variant dicts
          - split_override: optional dict of email->variant_id for manual assignments
        """
        default = {
            "enabled": True,
            "variants": list(WIN_BACK_VARIANTS_DEFAULT),
            "split_override": {},
        }
        try:
            db = self.get_db()
            r = db.table("agent_config") \
                .select("config_json") \
                .eq("agent_name", "win_back_ab_test") \
                .limit(1) \
                .execute()
            if r.data:
                cfg = r.data[0].get("config_json") or {}
                return {
                    "enabled": cfg.get("enabled", True),
                    "variants": cfg.get("variants", list(WIN_BACK_VARIANTS_DEFAULT)),
                    "split_override": cfg.get("split_override", {}),
                }
        except Exception as e:
            log.debug(f"[trial] win-back config read failed: {e}")
        return default

    def _save_win_back_config(self, config: dict) -> dict:
        """Save win-back A/B variant config to agent_config table.

        Args:
            config: Dict with enabled, variants, split_override.

        Returns:
            {"ok": True/False, "error": "..."}
        """
        try:
            db = self.get_db()
            db.table("agent_config") \
                .upsert({
                    "agent_name": "win_back_ab_test",
                    "config_json": config,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }) \
                .execute()
            return {"ok": True}
        except Exception as e:
            log.warning(f"[trial] win-back config save failed: {e}")
            return {"ok": False, "error": str(e)}

    def _assign_win_back_variant(self, email: str, product_slug: str) -> dict:
        """Assign a win-back variant for a given email+product.

        Uses a hash-based consistent assignment so the same user always
        gets the same variant. Checks split_override first for manual
        operator assignments.

        Returns the selected variant dict.
        """
        config = self._read_win_back_config()
        variants = config.get("variants", [])
        if not variants:
            variants = list(WIN_BACK_VARIANTS_DEFAULT)

        # Check operator override first
        override_key = f"{email}::{product_slug}"
        overrides = config.get("split_override", {})
        if override_key in overrides:
            override_id = overrides[override_key]
            for v in variants:
                if v["id"] == override_id:
                    return v

        # Hash-based consistent assignment using weights
        total_weight = sum(v.get("weight", 50) for v in variants)
        if total_weight <= 0:
            total_weight = 100

        # Hash the email+product to get a consistent number 0..total_weight-1
        # Uses hashlib.md5 for deterministic assignment across restarts
        hash_input = f"{email}::{product_slug}"
        hash_bytes = hashlib.md5(hash_input.encode()).digest()
        hash_int = int.from_bytes(hash_bytes[:4], "big")
        hash_val = hash_int % total_weight

        cumulative = 0
        for v in variants:
            cumulative += v.get("weight", 50)
            if hash_val < cumulative:
                return v

        # Fallback
        return variants[0]

    @staticmethod
    def _build_win_back_email_warm(product_name: str, tier: str, price: float) -> str:
        """Build warm/reassuring tone win-back email — variant A."""
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

    @staticmethod
    def _build_win_back_email_urgent(product_name: str, tier: str, price: float) -> str:
        """Build urgent/direct tone win-back email — variant B."""
        return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0a0f;color:#e2e8f0;padding:32px">
  <div style="max-width:560px;margin:0 auto;background:#14141e;border:1px solid #1e293b;border-radius:12px;padding:32px;text-align:center">
    <div style="font-size:36px;margin-bottom:8px">⚠️</div>
    <h1 style="font-weight:200;font-size:24px;letter-spacing:-0.02em;margin:0 0 4px">Your <em style="color:#FFB800;font-style:italic;font-weight:500">{product_name}</em> Access Is At Risk</h1>
    <p style="font-family:'SF Mono','Fira Code',monospace;font-size:10px;color:#94a3b8;letter-spacing:0.14em;text-transform:uppercase;margin:0 0 20px">Reactivate within 7 days · {tier} tier reserved</p>
    <p style="font-size:14px;color:#cbd5e1;line-height:1.7;margin:0 0 8px">
      Your <strong>{product_name}</strong> subscription has been canceled, but your <strong>{tier}</strong> tier is still reserved for you at <strong style="color:#44E5B8">${price:.2f}/mo</strong>.
    </p>
    <div style="background:#0f0f17;border:1px solid #1e293b;border-radius:8px;padding:20px;margin:16px 0;text-align:left;border-left:3px solid #FFB800">
      <div style="font-family:'SF Mono','Fira Code',monospace;font-size:10px;color:#FFB800;letter-spacing:0.14em;text-transform:uppercase;margin-bottom:12px">⏳ Offer Expires Soon</div>
      <div style="font-size:14px;color:#e2e8f0;margin-bottom:4px">{product_name} · <strong>{tier}</strong></div>
      <div style="font-family:'SF Mono','Fira Code',monospace;font-size:28px;color:#44E5B8;font-weight:600">${price:.2f}<span style="font-size:12px;color:#94a3b8;font-weight:400">/mo</span></div>
      <div style="font-size:12px;color:#cbd5e1;line-height:1.6;margin-top:8px;padding-top:12px;border-top:1px solid #1e293b">
        ✓ Full feature access · ✓ Priority support · ✓ No setup fees
      </div>
    </div>
    <p style="font-size:13px;color:#FFB800;line-height:1.6;margin:0 0 24px">
      ⚠️ Your {tier} rate of ${price:.2f}/mo will expire in 7 days. Reactivate now to lock it in.
    </p>
    <a href="https://empire-ai.co.uk/command#/products" style="display:inline-block;padding:14px 32px;background:#44E5B8;color:#000;text-decoration:none;font-weight:700;font-family:'SF Mono','Fira Code',monospace;font-size:12px;letter-spacing:0.14em;text-transform:uppercase;border-radius:6px">Reactivate Now →</a>
    <p style="font-size:11px;color:#64748b;line-height:1.5;margin:24px 0 0;padding-top:16px;border-top:1px solid #1e293b">
      Questions? Reply to this email. Already reactivated? Ignore this message.
    </p>
  </div>
</body>
</html>"""

    def _build_win_back_variant(self, variant: dict, product_name: str, tier: str, price: float) -> str:
        """Build win-back email HTML for a given variant."""
        tone = variant.get("tone", "warm")
        if tone == "urgent":
            return self._build_win_back_email_urgent(product_name, tier, price)
        return self._build_win_back_email_warm(product_name, tier, price)

    def get_win_back_variant_stats(self) -> list[dict]:
        """Return per-variant win-back A/B test stats.

        Returns list of dicts with:
          - variant_id: str
          - name: str
          - sent: int
          - followups_sent: int
          - reactivations: int
          - reactivation_rate: float
        """
        config = self._read_win_back_config()
        variants = config.get("variants", [])
        if not variants:
            return []

        try:
            db = self.get_db()

            # Fetch all win_back_sent events with variant info
            r = db.table("sales_events") \
                .select("email, product_slug, created_at, notes") \
                .eq("event_type", "win_back_sent") \
                .execute()
            win_backs = r.data or []

            # Fetch all win_back_followup_sent events
            r2 = db.table("sales_events") \
                .select("email, product_slug, created_at, notes") \
                .eq("event_type", "win_back_followup_sent") \
                .execute()
            followups = r2.data or []
            followup_keys = set()
            for f in followups:
                followup_keys.add((f.get("email", ""), f.get("product_slug", "")))

            # Fetch recent trial_converted events for reactivation check
            r3 = db.table("sales_events") \
                .select("email, product_slug, created_at") \
                .eq("event_type", "trial_converted") \
                .order("created_at", desc=True) \
                .execute()
            recent_converted = r3.data or []
            latest_conv: dict[tuple[str, str], str] = {}
            for ce in recent_converted:
                ck = (ce.get("email", ""), ce.get("product_slug", ""))
                if ck not in latest_conv:
                    latest_conv[ck] = str(ce.get("created_at", ""))

            # Determine variant for each win_back_sent from notes or by re-assignment
            # Notes format: "variant=A|"
            variant_wins: dict[str, int] = {}
            variant_sent: dict[str, int] = {}
            variant_followup: dict[str, int] = {}

            for wb in win_backs:
                notes = wb.get("notes", "") or ""
                # Extract variant from notes using prefix check (no split to avoid delimiter issues)
                variant_id = None
                if notes.startswith("variant="):
                    # variant=A|Warm Reassurance  → extract "A"
                    after_prefix = notes[len("variant="):]
                    pipe_idx = after_prefix.find("|")
                    if pipe_idx >= 0:
                        variant_id = after_prefix[:pipe_idx].strip()
                    else:
                        variant_id = after_prefix.strip()

                if not variant_id:
                    # Legacy win-backs without variant — assign one retroactively
                    variant_id = self._assign_win_back_variant(
                        wb.get("email", ""), wb.get("product_slug", "")
                    ).get("id", "A")

                variant_sent[variant_id] = variant_sent.get(variant_id, 0) + 1

                # Check for followup
                key = (wb.get("email", ""), wb.get("product_slug", ""))
                if key in followup_keys:
                    variant_followup[variant_id] = variant_followup.get(variant_id, 0) + 1

                # Check for reactivation
                wb_created = str(wb.get("created_at", ""))
                conv_created = latest_conv.get(key, "")
                if conv_created and conv_created > wb_created:
                    variant_wins[variant_id] = variant_wins.get(variant_id, 0) + 1

            # Build results for each variant
            results = []
            for v in variants:
                vid = v["id"]
                sent = variant_sent.get(vid, 0)
                wins = variant_wins.get(vid, 0)
                results.append({
                    "variant_id": vid,
                    "name": v.get("name", vid),
                    "tone": v.get("tone", "warm"),
                    "weight": v.get("weight", 50),
                    "subject": v.get("subject", ""),
                    "sent": sent,
                    "followups_sent": variant_followup.get(vid, 0),
                    "reactivations": wins,
                    "reactivation_rate": round(wins / max(sent, 1), 3),
                })

            return results

        except Exception as e:
            log.warning(f"[trial] win-back variant stats failed: {e}")
            return []

    def set_win_back_variants_config(self, config: dict) -> dict:
        """Update win-back A/B variant configuration.

        Accepts a dict with optional keys:
          - enabled: bool
          - variants: list of variant dicts
          - split_override: dict of email::product_slug -> variant_id

        Merges with existing config — only provided keys are updated.
        """
        existing = self._read_win_back_config()

        # Merge provided fields
        if "enabled" in config:
            existing["enabled"] = bool(config["enabled"])
        if "variants" in config:
            existing["variants"] = config["variants"]
        if "split_override" in config:
            existing["split_override"] = config["split_override"]

        return self._save_win_back_config(existing)

    def assign_win_back_variant_override(self, email: str, product_slug: str, variant_id: str) -> dict:
        """Manually assign a win-back variant for a specific user.

        This creates an override in the config so the user will always
        get this variant, bypassing the hash-based assignment.
        """
        if not email or not product_slug or not variant_id:
            return {"ok": False, "error": "email, product_slug, and variant_id are required"}

        config = self._read_win_back_config()

        # Validate variant_id exists
        valid_ids = {v["id"] for v in config.get("variants", WIN_BACK_VARIANTS_DEFAULT)}
        if variant_id not in valid_ids:
            return {"ok": False, "error": f"Invalid variant_id '{variant_id}'. Valid: {sorted(valid_ids)}"}

        overrides = config.get("split_override", {})
        key = f"{email}::{product_slug}"
        overrides[key] = variant_id
        config["split_override"] = overrides

        result = self._save_win_back_config(config)
        if result.get("ok"):
            return {"ok": True, "email": email, "product_slug": product_slug, "variant_id": variant_id}
        return result

    def _is_win_back_opted_out(self, email: str, product_slug: str) -> bool:
        """Check if a user has opted out of win-back emails for a specific product."""
        try:
            db = self.get_db()
            r = db.table("sales_events") \
                .select("id") \
                .eq("email", email) \
                .eq("product_slug", product_slug) \
                .eq("event_type", "win_back_opted_out") \
                .limit(1) \
                .execute()
            if r.data:
                return True
        except Exception as e:
            log.debug(f"[trial] opt-out check failed: {e}")
        return False

    def log_win_back_opt_out(self, email: str, product_slug: str, reason: str = "user_requested") -> dict:
        """Log a win-back opt-out event for a user.

        Once logged, the user will not receive any further win-back emails
        for the given product.

        Args:
            email: User's email.
            product_slug: Product slug.
            reason: Opt-out reason (e.g. "user_requested", "bounced", "spam_complaint").

        Returns:
            {"ok": True/False, ...}
        """
        if not email or not product_slug:
            return {"ok": False, "error": "email and product_slug are required"}

        # Check if already opted out
        if self._is_win_back_opted_out(email, product_slug):
            return {"ok": True, "already_opted_out": True, "email": email, "product_slug": product_slug}

        try:
            db = self.get_db()
            db.table("sales_events").insert({
                "email": email,
                "product_slug": product_slug,
                "event_type": "win_back_opted_out",
                "notes": reason[:200],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
            self.stats["win_backs_opted_out"] += 1
            log.info(f"[trial] win-back opt-out logged: {email} for {product_slug} ({reason[:80]})")
            return {"ok": True, "email": email, "product_slug": product_slug, "reason": reason[:200]}
        except Exception as e:
            log.warning(f"[trial] failed to log win-back opt-out: {e}")
            return {"ok": False, "error": str(e)}

    async def _send_win_back(self, email: str, product_slug: str, tier: str) -> bool:
        """Send a win-back reactivation email for a churned trial.

        Uses the win-back A/B variant system to select the subject line
        and tone. Respects opt-out: if the user has opted out, no email is sent.
        Checks for existing win_back_sent event to avoid repeat sends.
        Returns True if email was sent.
        """
        if not self.send_email or not email:
            return False

        # Check opt-out before sending
        if self._is_win_back_opted_out(email, product_slug):
            log.debug(f"[trial] win-back skipped — {email} opted out of {product_slug}")
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

        # Select variant using hash-based consistent assignment
        variant = self._assign_win_back_variant(email, product_slug)
        variant_id = variant.get("id", "A")
        variant_name = variant.get("name", "A")

        product_name = PRODUCT_CATALOG.get(product_slug, {}).get("name", product_slug)
        price = self._get_tier_price(product_slug, tier) or 0

        # Build subject from variant template
        subject_tmpl = variant.get("subject", "We Miss You at {product_name} — reactivate your {tier} plan")
        subject = subject_tmpl.format(product_name=product_name, tier=tier, price=price)
        body = self._build_win_back_variant(variant, product_name, tier, price)

        ok = await self._send_email_async(email, subject, body)
        if ok:
            self.stats["win_backs_sent"] += 1

            # Log the event to prevent repeat sends — include variant in notes
            notes = f"variant={variant_id}|{variant_name}"
            try:
                db.table("sales_events").insert({
                    "email": email,
                    "product_slug": product_slug,
                    "event_type": "win_back_sent",
                    "tier": tier,
                    "notes": notes,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }).execute()
            except Exception as e:
                log.debug(f"[trial] failed to log win_back_sent event: {e}")

            log.info(f"[trial] win-back email sent to {email} for {product_slug}/{tier} [variant {variant_id}]")

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

    def trial_pipeline_sla(self) -> dict:
        """Check SLA compliance for the trial conversion pipeline.

        Evaluates each trial_start event against the SLA:
        - trial_end + CONVERSION_GRACE_HOURS = SLA deadline
        - trial_end + grace + SLA_BUFFER_HOURS = hard breach threshold

        Returns dict with:
          - total_expired: trial_start events past trial_end
          - total_past_sla: past SLA deadline (trial_end + grace)
          - on_time: converted before SLA deadline
          - breached: past SLA deadline and not converted
          - pending: within grace window (not yet past SLA)
          - breach_rate: breached / total_past_sla
          - breaches: list of breached trials with details
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

        # Fetch all trial_converted events
        r2 = db.table("sales_events") \
            .select("email, product_slug") \
            .eq("event_type", "trial_converted") \
            .execute()
        converted = set()
        for ev in (r2.data or []):
            converted.add((ev.get("email", ""), ev.get("product_slug", "")))

        sla_deadline_hours = CONVERSION_GRACE_HOURS + SLA_BUFFER_HOURS

        total_expired = 0
        total_past_sla = 0
        on_time = 0
        breached = 0
        pending = 0
        breaches = []

        for t in trials:
            trial_end_str = t.get("trial_end")
            if not trial_end_str:
                continue

            try:
                end_dt = datetime.fromisoformat(str(trial_end_str).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue

            # Skip trials that haven't ended yet
            if now < end_dt:
                continue

            total_expired += 1
            email = t.get("email", "")
            product_slug = t.get("product_slug", "")
            key = (email, product_slug)
            is_converted = key in converted

            grace_end = end_dt + timedelta(hours=CONVERSION_GRACE_HOURS)

            if now < grace_end:
                # Within grace window — still acceptable
                pending += 1
                continue

            total_past_sla += 1
            sla_end = end_dt + timedelta(hours=sla_deadline_hours)
            hours_overdue = round((now - grace_end).total_seconds() / 3600, 1)

            if is_converted:
                # Converted but late — check if within buffer
                if now < sla_end:
                    # Converted within buffer — ok but late
                    on_time += 1
                else:
                    # Converted but after SLA buffer — still counts as on-time
                    on_time += 1
            else:
                breached += 1
                breach_severity = "warning" if now < sla_end else "critical"
                breaches.append({
                    "email": email,
                    "product_slug": product_slug,
                    "product_name": PRODUCT_NAMES.get(product_slug, product_slug),
                    "tier": t.get("tier", ""),
                    "trial_end": str(trial_end_str)[:19],
                    "grace_end": str(grace_end.isoformat())[:19],
                    "hours_overdue": hours_overdue,
                    "severity": breach_severity,
                    "is_converted": is_converted,
                })

        breach_rate = round(breached / max(total_past_sla, 1), 3)

        # Log breaches as warnings
        if breached:
            log.warning(
                f"[trial.sla] {breached} SLA breach(es) out of {total_past_sla} past-deadline trials "
                f"(rate={breach_rate:.1%}, buffer={SLA_BUFFER_HOURS}h)"
            )

        return {
            "total_expired": total_expired,
            "total_past_sla": total_past_sla,
            "on_time": on_time,
            "breached": breached,
            "pending": pending,
            "breach_rate": breach_rate,
            "sla_grace_hours": CONVERSION_GRACE_HOURS,
            "sla_buffer_hours": SLA_BUFFER_HOURS,
            "sla_deadline_hours": sla_deadline_hours,
            "breaches": sorted(breaches, key=lambda x: -x["hours_overdue"]),
        }

    async def monitoring_loop(self):
        """Background loop: send expiring-soon reminders + convert expired trials + track churn + win-back followups + SLA check."""
        await asyncio.sleep(300)  # let hub finish booting (5 min)
        log.info("[trial] monitoring loop started (interval=%ds)", CHECK_INTERVAL_SEC)
        while not self._stop_loop:
            try:
                # 0. Track churn on converted trials
                self.track_churn()
                # 0.5. Send win-back follow-ups (7d after first win-back)
                await self._send_win_back_followups()
                # 1. Send expiring-soon reminders (trials ending in 3 or 1 days)
                await self._send_expiring_soon_reminders()
                # 2. Convert expired trials (ended more than 24h ago)
                self.run_once()
                # 3. Check SLA compliance
                sla = self.trial_pipeline_sla()
                if sla["breached"]:
                    log.warning(
                        f"[trial.sla] {sla['breached']} breach(es) — "
                        f"rate={sla['breach_rate']:.1%}, "
                        f"worst={sla['breaches'][0]['hours_overdue']:.1f}h overdue"
                    )
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

        # Fetch win-back stats
        r_wb = db.table("sales_events") \
            .select("email, product_slug, created_at") \
            .eq("event_type", "win_back_sent") \
            .execute()
        win_back_events = r_wb.data or []
        win_backs_sent = len(win_back_events)

        r_wbf = db.table("sales_events") \
            .select("email, product_slug, created_at") \
            .eq("event_type", "win_back_followup_sent") \
            .execute()
        win_back_followups_sent = len(r_wbf.data or [])

        # Fetch opt-out count
        r_opt = db.table("sales_events") \
            .select("id", count="exact") \
            .eq("event_type", "win_back_opted_out") \
            .execute()
        win_backs_opted_out = getattr(r_opt, "count", len(r_opt.data or []))

        # Compute reactivation rate: churned users who later converted again
        # Build lookup: for each win_back_sent, check if there's a trial_converted
        # event (for same email+product) created AFTER the win_back_sent
        r_recent_conv = db.table("sales_events") \
            .select("email, product_slug, created_at") \
            .eq("event_type", "trial_converted") \
            .order("created_at", desc=True) \
            .execute()
        recent_converted = r_recent_conv.data or []
        # Group by email+product with latest created_at
        latest_conv_by_key: dict[tuple[str, str], str] = {}
        for ce in recent_converted:
            ck = (ce.get("email", ""), ce.get("product_slug", ""))
            if ck not in latest_conv_by_key:
                latest_conv_by_key[ck] = str(ce.get("created_at", ""))

        reactivations = 0
        for wb in win_back_events:
            wb_key = (wb.get("email", ""), wb.get("product_slug", ""))
            wb_created = str(wb.get("created_at", ""))
            conv_created = latest_conv_by_key.get(wb_key, "")
            if conv_created and conv_created > wb_created:
                reactivations += 1

        reactivation_rate = round(reactivations / max(win_backs_sent, 1), 3)

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
            "win_back_stats": {
                "win_backs_sent": win_backs_sent,
                "followups_sent": win_back_followups_sent,
                "reactivations": reactivations,
                "reactivation_rate": reactivation_rate,
                "opted_out": win_backs_opted_out,
                "variants": self.get_win_back_variant_stats(),
            },
            "sla_stats": self.trial_pipeline_sla(),
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
