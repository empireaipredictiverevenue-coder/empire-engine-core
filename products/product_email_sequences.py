"""
Empire AI · Product Email Sequences
====================================
Automated email sequence templates for all 13 products.
Each product has 5 sequence types:
  1. ONBOARDING  — welcome + setup guide + first value (3 touches)
  2. TRIAL       — trial conversion reminders (3 touches over 14 days)
  3. UPSELL      — feature-based upgrade recommendations (2 touches)
  4. RENEWAL     — renewal reminders (2 touches before expiry)
  5. REACTIVATE  — win-back for churned/inactive accounts (2 touches)

Each template returns (subject, body_html, delay_hours).
All templates include the CAN-SPAM footer (handled by EmailEngine).
"""

import logging
from typing import List, Tuple, Optional

log = logging.getLogger("empire.email_sequences")

# ── Helper: build email body with Empire branding ───────────────────────────
def _shell(body_html: str, product_name: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0A1A2F;font-family:-apple-system,system-ui,'Helvetica Neue',sans-serif;">
<table cellpadding="0" cellspacing="0" border="0" width="100%">
<tr><td align="center" style="padding:32px 16px;">
  <table cellpadding="0" cellspacing="0" border="0" width="560" style="max-width:560px;background:#15263F;border:1px solid rgba(122,140,163,0.18);">
    <tr><td style="padding:28px 32px 0;border-bottom:1px solid rgba(122,140,163,0.12);">
      <div style="font-size:11px;color:#7A8CA3;letter-spacing:.18em;text-transform:uppercase;">Empire AI · {product_name}</div>
      <div style="font-size:9px;color:#4A5A72;letter-spacing:.14em;text-transform:uppercase;margin-top:4px;">Predictive Revenue Engine</div>
    </td></tr>
    <tr><td style="padding:24px 32px 16px;">{body_html}</td></tr>
    <tr><td style="padding:16px 32px 28px;border-top:1px solid rgba(122,140,163,0.12);font-size:10px;color:#4A5A72;line-height:1.7;">
      Empire AI Ltd · {product_name}<br>
      <a href="{'{{unsubscribe_link}}'}" style="color:#44E5B8;">Unsubscribe</a>
    </td></tr>
  </table>
</td></tr>
</table>
</body></html>"""


def _greeting(name: str = "") -> str:
    return f"Hi {name}," if name else "Hi there,"


# ═══════════════════════════════════════════════════════════════════════════
# 1. ONBOARDING SEQUENCES (3 touches)
# ═══════════════════════════════════════════════════════════════════════════

def onboarding_welcome(product: str, tier: str, features: list) -> Tuple[str, str, int]:
    """Touch 1: Welcome + what to expect."""
    feat_list = "".join(f'<li style="padding:4px 0;color:#C8D4E4;font-size:13px;">→ {f}</li>' for f in features[:5])
    subject = f"Welcome to {product} ({tier}) — Let's get started"
    body = f"""
      <div style="font-size:22px;font-weight:600;color:#F8FAFD;letter-spacing:-0.02em;margin-bottom:16px;">
        Welcome to <span style="color:#44E5B8;">{product}</span>
      </div>
      <p style="font-size:14px;line-height:1.7;color:#C8D4E4;margin:0 0 14px;">
        {_greeting()}
      </p>
      <p style="font-size:14px;line-height:1.7;color:#C8D4E4;margin:0 0 14px;">
        Your <strong style="color:#F8FAFD;">{tier}</strong> subscription to <strong>{product}</strong> is active.
        Here's what's included:
      </p>
      <ul style="margin:0 0 18px;padding-left:0;list-style:none;">{feat_list}</ul>
      <div style="margin:20px 0;padding:16px 20px;background:#0A1A2F;border-left:3px solid #44E5B8;">
        <p style="font-size:13px;color:#C8D4E4;margin:0;line-height:1.6;">
          <strong style="color:#F8FAFD;">Quick start:</strong> Open the Command Dashboard at <a href="{'{{dashboard_url}}'}" style="color:#44E5B8;">empire-ai.co.uk/command</a>
          to configure your settings and see your first results.
        </p>
      </div>
    """
    return subject, _shell(body, product), 0  # send immediately


def onboarding_setup(product: str, tier: str) -> Tuple[str, str, int]:
    """Touch 2: Setup guide + tips (sent 24h after welcome)."""
    subject = f"Setting up {product} — 3 things to configure"
    body = f"""
      <div style="font-size:20px;font-weight:600;color:#F8FAFD;letter-spacing:-0.02em;margin-bottom:16px;">
        Make the most of <span style="color:#5AC8FA;">{product}</span>
      </div>
      <p style="font-size:14px;line-height:1.7;color:#C8D4E4;margin:0 0 14px;">
        {_greeting()}
      </p>
      <p style="font-size:14px;line-height:1.7;color:#C8D4E4;margin:0 0 14px;">
        Here are 3 things to configure to get the most out of {product}:
      </p>
      <ol style="margin:0 0 18px;padding-left:20px;color:#C8D4E4;font-size:13px;line-height:1.8;">
        <li><strong style="color:#F8FAFD;">Connect your data sources</strong> — go to Settings → Integrations to link your accounts</li>
        <li><strong style="color:#F8FAFD;">Set your preferences</strong> — configure notification frequency and alert thresholds</li>
        <li><strong style="color:#F8FAFD;">Invite your team</strong> — add team members from the Operators panel</li>
      </ol>
      <p style="font-size:13px;color:#7A8CA3;line-height:1.6;">
        Need help? Reply to this email or use the Console in the Command Dashboard.
      </p>
    """
    return subject, _shell(body, product), 24  # 24h after


def onboarding_value(product: str, tier: str) -> Tuple[str, str, int]:
    """Touch 3: First value milestone (sent 72h after welcome)."""
    subject = f"Your first week with {product} — here's what we found"
    body = f"""
      <div style="font-size:20px;font-weight:600;color:#F8FAFD;letter-spacing:-0.02em;margin-bottom:16px;">
        Your first <span style="color:#44E5B8;">results</span> are in
      </div>
      <p style="font-size:14px;line-height:1.7;color:#C8D4E4;margin:0 0 14px;">
        {_greeting()}
      </p>
      <p style="font-size:14px;line-height:1.7;color:#C8D4E4;margin:0 0 14px;">
        After your first week with <strong>{product}</strong> ({tier} tier), here are
        some highlights and recommendations based on your usage:
      </p>
      <div style="margin:18px 0;padding:16px 20px;background:#0A1F3A;border:1px solid rgba(68,229,184,0.15);">
        <div style="font-family:monospace;font-size:11px;color:#44E5B8;margin-bottom:8px;">► Usage snapshot available in your dashboard</div>
        <div style="font-family:monospace;font-size:11px;color:#7A8CA3;">For detailed metrics, visit <a href="{'{{dashboard_url}}'}" style="color:#5AC8FA;">/command</a></div>
      </div>
      <p style="font-size:13px;color:#7A8CA3;line-height:1.6;">
        We're here to help — reply to this email anytime.
      </p>
    """
    return subject, _shell(body, product), 72  # 72h after


# ═══════════════════════════════════════════════════════════════════════════
# 2. TRIAL CONVERSION SEQUENCES (3 touches over 14 days)
# ═══════════════════════════════════════════════════════════════════════════

def trial_day3(product: str, tier: str, days_left: int = 11) -> Tuple[str, str, int]:
    """Touch 1: Day 3 of trial — engagement check."""
    subject = f"3 days in — how's {product} working for you?"
    body = f"""
      <div style="font-size:20px;font-weight:600;color:#F8FAFD;letter-spacing:-0.02em;margin-bottom:16px;">
        <span style="color:#5AC8FA;">3 days</span> into your {product} trial
      </div>
      <p style="font-size:14px;line-height:1.7;color:#C8D4E4;margin:0 0 14px;">
        {_greeting()}
      </p>
      <p style="font-size:14px;line-height:1.7;color:#C8D4E4;margin:0 0 14px;">
        You're 3 days into your free trial of <strong>{product}</strong> ({tier}).
        You have <strong style="color:#44E5B8;">{days_left} days left</strong> to explore everything.
      </p>
      <p style="font-size:14px;line-height:1.7;color:#C8D4E4;margin:0 0 14px;">
        Here's what to try next:
      </p>
      <ul style="margin:0 0 18px;padding-left:20px;color:#C8D4E4;font-size:13px;line-height:1.8;">
        <li>Run your first analysis in the dashboard</li>
        <li>Configure alerts and notifications</li>
        <li>Explore the API documentation</li>
      </ul>
      <p style="font-size:13px;color:#7A8CA3;line-height:1.6;">
        When you're ready, convert to a paid plan from your dashboard settings.
      </p>
    """
    return subject, _shell(body, product), 72  # 72h after trial start


def trial_day7(product: str, tier: str, days_left: int = 7) -> Tuple[str, str, int]:
    """Touch 2: Day 7 — halfway point, feature deep-dive."""
    subject = f"Halfway through your {product} trial — {days_left} days left"
    body = f"""
      <div style="font-size:20px;font-weight:600;color:#F8FAFD;letter-spacing:-0.02em;margin-bottom:16px;">
        <span style="color:#FFB800;">Halfway point</span> — {days_left} days remaining
      </div>
      <p style="font-size:14px;line-height:1.7;color:#C8D4E4;margin:0 0 14px;">
        {_greeting()}
      </p>
      <p style="font-size:14px;line-height:1.7;color:#C8D4E4;margin:0 0 14px;">
        You're at the halfway mark of your <strong>{product}</strong> trial.
        Here's a feature you may not have tried yet:
      </p>
      <div style="margin:18px 0;padding:16px 20px;background:#0A1F3A;border:1px solid rgba(90,200,250,0.2);">
        <div style="font-size:14px;font-weight:600;color:#5AC8FA;margin-bottom:8px;">💡 Pro tip</div>
        <p style="font-size:13px;color:#C8D4E4;margin:0;line-height:1.6;">
          Connect your existing workflows through the API to unlock the full power of {product}.
          Check the docs at <a href="{'{{dashboard_url}}'}/docs" style="color:#44E5B8;">docs.empire-ai.co.uk</a>
        </p>
      </div>
      <p style="font-size:13px;color:#7A8CA3;line-height:1.6;">
        Convert before the trial ends to keep your data and settings.
        <a href="{'{{dashboard_url}}'}/#/products" style="color:#44E5B8;">Upgrade now →</a>
      </p>
    """
    return subject, _shell(body, product), 168  # 7 days


def trial_day13(product: str, tier: str) -> Tuple[str, str, int]:
    """Touch 3: Last day — conversion urgency."""
    subject = f"Last day of your {product} trial — don't lose your setup"
    body = f"""
      <div style="font-size:20px;font-weight:600;color:#F8FAFD;letter-spacing:-0.02em;margin-bottom:16px;">
        <span style="color:#FF4444;">Last day</span> — your trial expires today
      </div>
      <p style="font-size:14px;line-height:1.7;color:#C8D4E4;margin:0 0 14px;">
        {_greeting()}
      </p>
      <p style="font-size:14px;line-height:1.7;color:#C8D4E4;margin:0 0 14px;">
        Your free trial of <strong>{product}</strong> ends today. Here's what happens:
      </p>
      <ul style="margin:0 0 18px;padding-left:20px;color:#C8D4E4;font-size:13px;line-height:1.8;">
        <li>✅ Your data is preserved for 30 days</li>
        <li>❌ Access to {product} features will be paused</li>
        <li>🔄 Reactivate anytime from your dashboard</li>
      </ul>
      <div style="margin:20px 0;padding:16px 20px;background:#0A1F3A;border:1px solid rgba(68,229,184,0.3);text-align:center;">
        <a href="{'{{dashboard_url}}'}/#/products" style="display:inline-block;padding:12px 24px;background:#44E5B8;color:#000;text-decoration:none;font-weight:700;font-size:13px;letter-spacing:.04em;">
          Convert to paid →
        </a>
      </div>
    """
    return subject, _shell(body, product), 312  # 13 days


# ═══════════════════════════════════════════════════════════════════════════
# 3. UPSELL SEQUENCES (2 touches)
# ═══════════════════════════════════════════════════════════════════════════

def upsell_touch1(product: str, current_tier: str, suggested_tier: str,
                  current_price: float, suggested_price: float, features: list) -> Tuple[str, str, int]:
    """Touch 1: Feature-based upgrade recommendation."""
    feat_list = "".join(f'<li style="padding:3px 0;color:#C8D4E4;font-size:12px;">→ {f}</li>' for f in features[:4])
    subject = f"Unlock more with {product} {suggested_tier}"
    body = f"""
      <div style="font-size:20px;font-weight:600;color:#F8FAFD;letter-spacing:-0.02em;margin-bottom:16px;">
        Level up to <span style="color:#44E5B8;">{suggested_tier}</span>
      </div>
      <p style="font-size:14px;line-height:1.7;color:#C8D4E4;margin:0 0 14px;">
        {_greeting()}
      </p>
      <p style="font-size:14px;line-height:1.7;color:#C8D4E4;margin:0 0 14px;">
        You're currently on <strong>{current_tier}</strong> (${current_price}/mo).
        Based on your usage patterns, upgrading to <strong style="color:#44E5B8;">{suggested_tier}</strong>
        (${suggested_price}/mo) would unlock:
      </p>
      <ul style="margin:0 0 18px;padding-left:0;list-style:none;">{feat_list}</ul>
      <p style="font-size:13px;color:#7A8CA3;line-height:1.6;">
        <a href="{'{{dashboard_url}}'}/#/products" style="color:#44E5B8;">See upgrade options →</a>
      </p>
    """
    return subject, _shell(body, product), 0  # immediate


def upsell_touch2(product: str, current_tier: str, suggested_tier: str,
                  price_increase: float) -> Tuple[str, str, int]:
    """Touch 2: Follow-up with value justification (72h after touch 1)."""
    monthly_diff = price_increase
    subject = f"Quick question about your {product} plan"
    body = f"""
      <div style="font-size:20px;font-weight:600;color:#F8FAFD;letter-spacing:-0.02em;margin-bottom:16px;">
        <span style="color:#5AC8FA;">Still considering</span> the upgrade?
      </div>
      <p style="font-size:14px;line-height:1.7;color:#C8D4E4;margin:0 0 14px;">
        {_greeting()}
      </p>
      <p style="font-size:14px;line-height:1.7;color:#C8D4E4;margin:0 0 14px;">
        Following up on our last note about upgrading from <strong>{current_tier}</strong>
        to <strong style="color:#44E5B8;">{suggested_tier}</strong>.
      </p>
      <p style="font-size:14px;line-height:1.7;color:#C8D4E4;margin:0 0 14px;">
        The increase of <strong style="color:#44E5B8;">${monthly_diff}/mo</strong> gives you access to
        advanced features that most teams find pays for itself within the first month.
      </p>
      <p style="font-size:13px;color:#7A8CA3;line-height:1.6;">
        Questions? Reply to this email — we're happy to help you decide.
      </p>
    """
    return subject, _shell(body, product), 72  # 72h after touch 1


# ═══════════════════════════════════════════════════════════════════════════
# 4. RENEWAL SEQUENCES (2 touches)
# ═══════════════════════════════════════════════════════════════════════════

def renewal_reminder(product: str, tier: str, days_left: int, price: float) -> Tuple[str, str, int]:
    """Touch 1: Renewal reminder (7 days before expiry)."""
    urgency = "⚠️ " if days_left <= 3 else ""
    subject = f"{urgency}Your {product} subscription renews in {days_left} days"
    body = f"""
      <div style="font-size:20px;font-weight:600;color:#F8FAFD;letter-spacing:-0.02em;margin-bottom:16px;">
        Subscription <span style="color:{"#FF4444" if days_left <= 3 else "#FFB800"};">renewal notice</span>
      </div>
      <p style="font-size:14px;line-height:1.7;color:#C8D4E4;margin:0 0 14px;">
        {_greeting()}
      </p>
      <p style="font-size:14px;line-height:1.7;color:#C8D4E4;margin:0 0 14px;">
        Your <strong>{product}</strong> ({tier}) subscription renews in <strong>{days_left} days</strong>
        at <strong style="color:#44E5B8;">${price}/mo</strong>.
      </p>
      <p style="font-size:13px;color:#7A8CA3;line-height:1.6;">
        No action needed if you'd like to continue. To cancel or change your plan,
        visit <a href="{'{{dashboard_url}}'}/#/products" style="color:#44E5B8;">your subscription settings</a>.
      </p>
    """
    return subject, _shell(body, product), 0


def renewal_expired(product: str, tier: str) -> Tuple[str, str, int]:
    """Touch 2: Post-expiry reactivation (1 day after expiry)."""
    subject = f"Your {product} subscription has expired — reactivate anytime"
    body = f"""
      <div style="font-size:20px;font-weight:600;color:#F8FAFD;letter-spacing:-0.02em;margin-bottom:16px;">
        <span style="color:#FF4444;">Subscription expired</span>
      </div>
      <p style="font-size:14px;line-height:1.7;color:#C8D4E4;margin:0 0 14px;">
        {_greeting()}
      </p>
      <p style="font-size:14px;line-height:1.7;color:#C8D4E4;margin:0 0 14px;">
        Your <strong>{product}</strong> ({tier}) subscription has ended.
      </p>
      <p style="font-size:14px;line-height:1.7;color:#C8D4E4;margin:0 0 14px;">
        Your data is safe and preserved for 30 days. Reactivate anytime to pick up
        where you left off — no setup required.
      </p>
      <div style="margin:20px 0;padding:16px 20px;background:#0A1F3A;border:1px solid rgba(68,229,184,0.2);text-align:center;">
        <a href="{'{{dashboard_url}}'}/#/products" style="display:inline-block;padding:12px 24px;background:#44E5B8;color:#000;text-decoration:none;font-weight:700;font-size:13px;letter-spacing:.04em;">
          Reactivate →
        </a>
      </div>
    """
    return subject, _shell(body, product), 24  # 24h after expiry


# ═══════════════════════════════════════════════════════════════════════════
# 5. REACTIVATION / WIN-BACK (2 touches)
# ═══════════════════════════════════════════════════════════════════════════

def reactivate_touch1(product: str, tier: str, days_gone: int) -> Tuple[str, str, int]:
    """Touch 1: Win-back after 30+ days inactive."""
    subject = f"Come back to {product} — we've made improvements"
    body = f"""
      <div style="font-size:20px;font-weight:600;color:#F8FAFD;letter-spacing:-0.02em;margin-bottom:16px;">
        <span style="color:#44E5B8;">We miss you</span> — it's been {days_gone} days
      </div>
      <p style="font-size:14px;line-height:1.7;color:#C8D4E4;margin:0 0 14px;">
        {_greeting()}
      </p>
      <p style="font-size:14px;line-height:1.7;color:#C8D4E4;margin:0 0 14px;">
        It's been <strong>{days_gone} days</strong> since you last used <strong>{product}</strong>.
        Since then, we've shipped several improvements:
      </p>
      <ul style="margin:0 0 18px;padding-left:20px;color:#C8D4E4;font-size:13px;line-height:1.8;">
        <li>Faster performance and reduced latency</li>
        <li>New integrations and API endpoints</li>
        <li>Improved dashboard with better insights</li>
      </ul>
      <p style="font-size:13px;color:#7A8CA3;line-height:1.6;">
        Reactivate your {tier} plan and see what's new.
        <a href="{'{{dashboard_url}}'}/#/products" style="color:#44E5B8;">Come back →</a>
      </p>
    """
    return subject, _shell(body, product), 0


def reactivate_touch2(product: str, tier: str, promo: str = "LAUNCH20") -> Tuple[str, str, int]:
    """Touch 2: Win-back with incentive (7 days after touch 1)."""
    subject = f"Special offer — 20% off your first month back on {product}"
    body = f"""
      <div style="font-size:20px;font-weight:600;color:#F8FAFD;letter-spacing:-0.02em;margin-bottom:16px;">
        <span style="color:#44E5B8;">20% off</span> your first month back
      </div>
      <p style="font-size:14px;line-height:1.7;color:#C8D4E4;margin:0 0 14px;">
        {_greeting()}
      </p>
      <p style="font-size:14px;line-height:1.7;color:#C8D4E4;margin:0 0 14px;">
        We'd love to have you back on <strong>{product}</strong> ({tier}).
        Use code <strong style="color:#44E5B8;">{promo}</strong> at checkout for 20% off your first month.
      </p>
      <p style="font-size:13px;color:#7A8CA3;line-height:1.6;">
        Offer valid for 14 days. <a href="{'{{dashboard_url}}'}/#/products" style="color:#44E5B8;">Redeem now →</a>
      </p>
    """
    return subject, _shell(body, product), 168  # 7 days after touch 1


# ═══════════════════════════════════════════════════════════════════════════
# SEQUENCE BUILDER
# ═══════════════════════════════════════════════════════════════════════════

PRODUCT_NAMES = {
    "inbound_router": "Inbound Router",
    "data_vault": "Data Vault",
    "buyer_spy": "Buyer Spy AI",
    "omni_bridge": "Omni Bridge",
    "agent_orchestrator": "Agent Orchestrator",
    "b2b_pro": "B2B Pro",
    "lead_score": "LeadScore AI",
    "compliant": "Compliant",
    "strike_campaigns": "Strike Campaigns",
    "forecast": "Forecast",
    "market_eye": "Market Eye",
    "content_pulse": "Content Pulse",
    "contractor_exchange": "Contractor Exchange",
}


def build_onboarding_sequence(product_slug: str, tier: str, features: list) -> List[dict]:
    """Build the full onboarding sequence for a product."""
    name = PRODUCT_NAMES.get(product_slug, product_slug)
    t1 = onboarding_welcome(name, tier, features)
    t2 = onboarding_setup(name, tier)
    t3 = onboarding_value(name, tier)
    return [
        {"step": 1, "subject": t1[0], "body": t1[1], "delay_hours": t1[2]},
        {"step": 2, "subject": t2[0], "body": t2[1], "delay_hours": t2[2]},
        {"step": 3, "subject": t3[0], "body": t3[1], "delay_hours": t3[2]},
    ]


def build_trial_sequence(product_slug: str, tier: str) -> List[dict]:
    """Build the trial conversion sequence."""
    name = PRODUCT_NAMES.get(product_slug, product_slug)
    t1 = trial_day3(name, tier)
    t2 = trial_day7(name, tier)
    t3 = trial_day13(name, tier)
    return [
        {"step": 1, "subject": t1[0], "body": t1[1], "delay_hours": t1[2]},
        {"step": 2, "subject": t2[0], "body": t2[1], "delay_hours": t2[2]},
        {"step": 3, "subject": t3[0], "body": t3[1], "delay_hours": t3[2]},
    ]


def build_upsell_sequence(product_slug: str, current_tier: str, suggested_tier: str,
                           current_price: float, suggested_price: float, features: list) -> List[dict]:
    """Build the upsell sequence."""
    name = PRODUCT_NAMES.get(product_slug, product_slug)
    t1 = upsell_touch1(name, current_tier, suggested_tier, current_price, suggested_price, features)
    t2 = upsell_touch2(name, current_tier, suggested_tier, suggested_price - current_price)
    return [
        {"step": 1, "subject": t1[0], "body": t1[1], "delay_hours": t1[2]},
        {"step": 2, "subject": t2[0], "body": t2[1], "delay_hours": t2[2]},
    ]


def build_renewal_sequence(product_slug: str, tier: str, days_left: int, price: float) -> List[dict]:
    """Build the renewal reminder sequence."""
    name = PRODUCT_NAMES.get(product_slug, product_slug)
    t1 = renewal_reminder(name, tier, days_left, price)
    t2 = renewal_expired(name, tier)
    return [
        {"step": 1, "subject": t1[0], "body": t1[1], "delay_hours": t1[2]},
        {"step": 2, "subject": t2[0], "body": t2[1], "delay_hours": t2[2]},
    ]


def build_reactivation_sequence(product_slug: str, tier: str, days_gone: int) -> List[dict]:
    """Build the win-back reactivation sequence."""
    name = PRODUCT_NAMES.get(product_slug, product_slug)
    t1 = reactivate_touch1(name, tier, days_gone)
    t2 = reactivate_touch2(name, tier)
    return [
        {"step": 1, "subject": t1[0], "body": t1[1], "delay_hours": t1[2]},
        {"step": 2, "subject": t2[0], "body": t2[1], "delay_hours": t2[2]},
    ]
