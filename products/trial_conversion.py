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

log = logging.getLogger("empire.trial_conversion")

# ── Config ───────────────────────────────────────────────────────────────
CHECK_INTERVAL_SEC = 3600       # check every hour
CONVERSION_GRACE_HOURS = 24     # wait 24h after trial ends before auto-converting


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

        # Find the subscription by customer_account_id (which is the email)
        sub = self.subscriptions.get_subscription(email)
        if not sub:
            self.stats["skipped_no_subscription"] += 1
            return {"ok": False, "error": f"No subscription found for {email}"}

        # Skip if already paid (MRR > 0)
        current_mrr = float(sub.get("monthly_recurring_revenue", 0) or 0)
        if current_mrr > 0:
            self.stats["skipped_already_paid"] += 1
            return {"ok": False, "error": f"Subscription for {email} already has MRR ${current_mrr:.2f}"}

        # Look up the tier price
        price = self._get_tier_price(product_slug, tier)
        if price is None or price <= 0:
            # Fallback: try to compute from tier name prefix
            price = self._compute_tier_price(tier)
        if price is None or price <= 0:
            return {"ok": False, "error": f"Could not determine price for tier '{tier}'"}

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
                self.stats["emails_sent"] += 1
            else:
                log.warning(f"[trial] conversion email send returned: {result}")
        except Exception as e:
            log.warning(f"[trial] conversion email exception: {e}")

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
        """Background loop: scan for expired trials every hour."""
        await asyncio.sleep(300)  # let hub finish booting (5 min)
        log.info("[trial] monitoring loop started (interval=%ds)", CHECK_INTERVAL_SEC)
        while not self._stop_loop:
            try:
                self.run_once()
            except Exception as e:
                log.warning(f"[trial] monitoring error: {e}")
            await asyncio.sleep(CHECK_INTERVAL_SEC)

    def stop(self):
        self._stop_loop = True

    # ── Stats snapshot ──────────────────────────────────────────────

    def stats_snapshot(self) -> dict:
        return {
            "engine": dict(self.stats),
            "check_interval_sec": CHECK_INTERVAL_SEC,
            "conversion_grace_hours": CONVERSION_GRACE_HOURS,
        }
