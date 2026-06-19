"""
EMPIRE V49 · AFFILIATE RECRUITER BOT
=====================================
Autonomous agent that finds, recruits, and converts affiliate partners
to drive calls through the Empire AI affiliate network.

PIPELINE:
  1. PROSPECT — Find candidates from buyers table (active buyers without
     affiliate links), contractors table, and other sources
  2. ENROLL — Create referral links + affiliate records for candidates
  3. OUTREACH — Send personalized email with unique referral link + offer
  4. NURTURE — Follow up with affiliates who signed up but haven't driven
     traffic (7 days of inactivity)
  5. TRACK — Monitor which affiliates are driving calls and revenue
  6. REPORT — Pipeline summary with actions taken

Wire-up in hub.py:
    from bots.affiliate_recruiter import run_loop as affiliate_recruiter_run_loop
    asyncio.create_task(affiliate_recruiter_run_loop())

Routes:
    GET  /api/v1/affiliate-recruiter/snapshot   — full pipeline status
    POST /api/v1/affiliate-recruiter/run-cycle  — force a cycle
"""

import os
import sys
import json
import asyncio
import logging
import secrets
import string
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Callable, Any
from collections import defaultdict

import httpx

sys.path.insert(0, "/root/empire-v49")

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("empire.affiliate_recruiter")

# ── CONFIG ───────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
HUB_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8001")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_AFFILIATE_KEY = os.environ.get("RESEND_AFFILIATE_KEY", "") or RESEND_API_KEY

_sb = None

def _get_sb():
    global _sb
    if _sb is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            log.error("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
            sys.exit(1)
        _sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _sb


# ── AFFILIATE OFFER CONFIG ──────────────────────────────────────────
OFFER = {
    "commission_rate": 0.10,
    "commission_label": "10%",
    "pitch": (
        "Earn 10% commission on every qualified lead you refer to Empire AI. "
        "Share your unique referral link via email, social media, or your website. "
        "When someone clicks and converts, you earn. No contracts, no exclusivity."
    ),
    "subject_template": "Empire AI Affiliate Program — Your {offer_type} Link Inside",
}

# ── EMAIL TEMPLATES ─────────────────────────────────────────────────

BUYER_OUTREACH_TEMPLATE = """\
<p style="font-size:14px;line-height:1.7;color:#a1a1aa;">
Hi <strong>{name}</strong>,
</p>
<p style="font-size:14px;line-height:1.7;color:#a1a1aa;">
You're already a valued partner in the Empire AI revenue network. We'd like to invite you to <strong>join our Affiliate Program</strong> and earn <strong style="color:#44E5B8;">{commission} commission</strong> on every qualified lead you refer.
</p>
<p style="font-size:14px;line-height:1.7;color:#a1a1aa;">
Your unique referral link is ready:
</p>
<div style="background:rgba(0,0,0,0.3);border:1px solid rgba(68,229,184,0.25);padding:14px 18px;font-family:monospace;font-size:13px;color:#44E5B8;word-break:break-all;margin:16px 0;text-align:center;">
<a href="{referral_url}" style="color:#44E5B8;text-decoration:none;">{referral_url}</a>
</div>
<p style="font-size:14px;line-height:1.7;color:#a1a1aa;">
Share this link with your network. When someone clicks and converts, {commission} is yours. No minimums, no exclusivity.
</p>
<p style="font-size:14px;line-height:1.7;color:#a1a1aa;">
You can track your clicks, leads, and earnings anytime at your affiliate dashboard:
<a href="{dashboard_url}" style="color:#44E5B8;">{dashboard_url}</a>
</p>
<p style="font-size:14px;line-height:1.7;color:#a1a1aa;">
Start sharing and welcome to the team.<br>
<strong>— Empire AI Ops</strong>
</p>
"""

CONTRACTOR_OUTREACH_TEMPLATE = """\
<p style="font-size:14px;line-height:1.7;color:#a1a1aa;">
Hi <strong>{name}</strong>,
</p>
<p style="font-size:14px;line-height:1.7;color:#a1a1aa;">
You're already part of the Empire AI contractor network. Now we want to help you earn even more — by <strong>referring other contractors</strong> to our platform.
</p>
<p style="font-size:14px;line-height:1.7;color:#a1a1aa;">
Share your unique referral link and earn <strong style="color:#44E5B8;">{commission} commission</strong> on every qualified lead generated through your referrals.
</p>
<div style="background:rgba(0,0,0,0.3);border:1px solid rgba(68,229,184,0.25);padding:14px 18px;font-family:monospace;font-size:13px;color:#44E5B8;word-break:break-all;margin:16px 0;text-align:center;">
<a href="{referral_url}" style="color:#44E5B8;text-decoration:none;">{referral_url}</a>
</div>
<p style="font-size:14px;line-height:1.7;color:#a1a1aa;">
Share the link, earn commissions. It's that simple.<br>
<strong>— Empire AI Ops</strong>
</p>
"""

NURTURE_TEMPLATE = """\
<p style="font-size:14px;line-height:1.7;color:#a1a1aa;">
Hi <strong>{name}</strong>,
</p>
<p style="font-size:14px;line-height:1.7;color:#a1a1aa;">
Just checking in — your Empire AI affiliate link is ready and waiting:
</p>
<div style="background:rgba(0,0,0,0.3);border:1px solid rgba(68,229,184,0.25);padding:14px 18px;font-family:monospace;font-size:13px;color:#44E5B8;word-break:break-all;margin:16px 0;text-align:center;">
<a href="{referral_url}" style="color:#44E5B8;text-decoration:none;">{referral_url}</a>
</div>
<p style="font-size:14px;line-height:1.7;color:#a1a1aa;">
Here are some quick ideas to start earning <strong style="color:#44E5B8;">{commission}</strong>:
</p>
<ul style="font-size:14px;line-height:1.7;color:#a1a1aa;padding-left:20px;">
  <li>Add the link to your email signature</li>
  <li>Share it in industry Facebook groups</li>
  <li>Post it on your business social media</li>
  <li>Email it to your existing customers</li>
  <li>Pin it to your LinkedIn profile</li>
</ul>
<p style="font-size:14px;line-height:1.7;color:#a1a1aa;">
Every click counts. Start today!<br>
<strong>— Empire AI Ops</strong>
</p>
"""


# ── HELPERS ─────────────────────────────────────────────────────────
def _generate_referral_code(name: str) -> str:
    """Generate a unique referral code from a name + random suffix."""
    base = name.strip().lower()
    base = "".join(c if c.isalnum() else "-" for c in base)
    base = "-".join(part for part in base.split("-") if part)
    base = base[:20].rstrip("-")
    suffix = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(4))
    return f"{base}-{suffix}"


async def _send_email_direct(to: str, subject: str, html: str) -> dict:
    """Send an email via Resend API using the affiliate-dedicated key.
    Falls back to RESEND_API_KEY if RESEND_AFFILIATE_KEY is not set."""
    if not RESEND_AFFILIATE_KEY:
        return {"ok": False, "error": "RESEND_AFFILIATE_KEY (and RESEND_API_KEY fallback) missing"}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_AFFILIATE_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": "Empire AI Ops <ops@empire-ai.co.uk>",
                    "to": [to],
                    "subject": subject,
                    "html": html,
                },
            )
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            ok = r.status_code < 300
            if ok:
                log.info(f"[affiliate_recruiter] Email sent to {to}: {data.get('id', '?')}")
            else:
                log.warning(f"[affiliate_recruiter] Email send to {to} failed: {data}")
            return {"ok": ok, "id": data.get("id"), "raw": data}
    except Exception as e:
        log.error(f"[affiliate_recruiter] Email send error for {to}: {e}")
        return {"ok": False, "error": str(e)}


def _save_draft(sb, to_email: str, subject: str, body_html: str, meta: dict = None):
    """Save an email draft to email_drafts table for the email engine to send."""
    try:
        sb.table("email_drafts").insert({
            "to_email": to_email,
            "subject": subject[:200],
            "body": body_html,
            "status": "pending",
            "meta": meta or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        return True
    except Exception as e:
        log.warning(f"[affiliate_recruiter] draft save failed for {to_email}: {e}")
        return False


class AffiliateRecruiter:
    """
    Autonomous affiliate recruiter bot.

    Pipeline: Prospect → Enroll → Outreach → Nurture → Track → Report
    """

    def __init__(self):
        self.stats = {
            "cycles_run": 0,
            "prospects_found": 0,
            "affiliates_enrolled": 0,
            "outreaches_sent": 0,
            "nurtures_sent": 0,
            "errors": 0,
        }
        self._last_cycle: Optional[str] = None

    # ── PHASE 1: PROSPECT ───────────────────────────────────────────

    def _prospect_buyers(self) -> List[Dict]:
        """
        Find active buyers who don't yet have an affiliate link.
        These are the highest-priority prospects — they're already
        in the system and understand the value.
        """
        try:
            sb = _get_sb()
            # Buyers who are active
            buyers = sb.table("buyers").select("id,buyer_name,email,niche") \
                .eq("is_active", True) \
                .limit(500) \
                .execute()
            all_buyers = buyers.data or []

            # Find which ones already have affiliate links
            buyer_ids = [b["id"] for b in all_buyers]
            if not buyer_ids:
                return []

            links = sb.table("affiliate_links").select("buyer_id") \
                .in_("buyer_id", buyer_ids) \
                .execute()
            linked_buyer_ids = set(l["buyer_id"] for l in (links.data or []))

            # Filter to buyers without links
            prospects = []
            for b in all_buyers:
                if str(b["id"]) not in linked_buyer_ids:
                    # Check if they already have an affiliate record
                    aff = sb.table("affiliates").select("id") \
                        .eq("email", b.get("email", "")).limit(1).execute()
                    if not aff.data:
                        prospects.append({
                            "source": "buyer",
                            "source_id": str(b["id"]),
                            "name": b.get("buyer_name", ""),
                            "email": b.get("email", ""),
                            "phone": b.get("phone", ""),
                            "niche": b.get("niche", ""),
                            "offer_type": "partner",
                            "email_quality": "high",  # buyers are trusted partners
                        })

            return prospects
        except Exception as e:
            log.warning(f"[affiliate_recruiter] prospect_buyers error: {e}")
            return []

    def _prospect_contractors(self) -> List[Dict]:
        """
        Find active contractors who could become affiliates.
        They already know the platform and could refer other contractors.
        """
        try:
            sb = _get_sb()
            contractors = sb.table("contractors").select("id,name,email,phone,metro,meta") \
                .eq("active", True) \
                .limit(500) \
                .execute()
            all_cts = contractors.data or []

            prospects = []
            for c in all_cts:
                email = c.get("email", "")
                if not email or "prospector.placeholder" in str(email):
                    continue
                # Check if already an affiliate
                aff = sb.table("affiliates").select("id") \
                    .eq("email", email).limit(1).execute()
                if not aff.data:
                    meta = c.get("meta", {}) or {}
                    if not isinstance(meta, dict):
                        meta = {}
                    email_quality = meta.get("email_quality", "") if isinstance(meta, dict) else ""
                    prospects.append({
                        "source": "contractor",
                        "source_id": str(c["id"]),
                        "name": c.get("name", ""),
                        "email": email,
                        "phone": c.get("phone", ""),
                        "metro": c.get("metro", ""),
                        "offer_type": "referral",
                        "email_quality": email_quality,
                    })

            return prospects
        except Exception as e:
            log.warning(f"[affiliate_recruiter] prospect_contractors error: {e}")
            return []

    def _prospect_owned(self) -> List[Dict]:
        """
        Find people who already signed up via /affiliates but have
        0 clicks — they need a nudge to start promoting.
        """
        try:
            sb = _get_sb()
            dormant = sb.table("affiliates").select("*") \
                .eq("status", "active") \
                .eq("total_clicks", 0) \
                .gte("created_at", (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()) \
                .execute()
            return [
                {
                    "id": str(a["id"]),
                    "source": "dormant_affiliate",
                    "source_id": str(a["id"]),
                    "name": a.get("name", ""),
                    "email": a.get("email", ""),
                    "phone": a.get("phone", ""),
                    "referral_code": a.get("referral_code", ""),
                    "commission_rate": float(a.get("commission_rate", 0.10)),
                    "offer_type": "nurture",
                    "created_at": a.get("created_at"),
                    "notes": a.get("notes", ""),
                }
                for a in (dormant.data or [])
            ]
        except Exception as e:
            log.warning(f"[affiliate_recruiter] prospect_dormant error: {e}")
            return []

    # ── PHASE 2: ENROLL ─────────────────────────────────────────────

    async def _enroll_affiliate(self, prospect: dict) -> Optional[dict]:
        """
        Create an affiliate record and referral link for a prospect.
        For buyer-sourced prospects, also creates an affiliate_links
        record so the tracking pixel (/track/aff/{code}) works.
        Returns the affiliate record or None on failure.
        """
        try:
            sb = _get_sb()
            name = prospect["name"]
            email = prospect["email"]
            phone = prospect.get("phone", "")
            source = prospect.get("source", "manual")

            # Generate unique referral code
            referral_code = _generate_referral_code(name)
            for _ in range(10):
                chk = sb.table("affiliates").select("id") \
                    .eq("referral_code", referral_code).limit(1).execute()
                if not chk.data:
                    break
                referral_code = _generate_referral_code(name)

            # Insert affiliate record
            aff_row = {
                "name": name,
                "email": email,
                "phone": phone or None,
                "company": prospect.get("niche", prospect.get("metro", "")),
                "referral_code": referral_code,
                "commission_rate": OFFER["commission_rate"],
                "status": "active",
                "is_active": True,
                "source": source,
                "notes": f"Auto-enrolled by affiliate_recruiter bot. Source: {source} ({prospect.get('source_id', '')})",
                "metadata": {
                    "source_id": prospect.get("source_id", ""),
                    "source_type": source,
                    "enrolled_by": "affiliate_recruiter_bot",
                    "offer_type": prospect.get("offer_type", "standard"),
                },
            }
            r = sb.table("affiliates").insert(aff_row).execute()
            if not r.data:
                log.warning(f"[affiliate_recruiter] enroll failed for {email}")
                return None

            affiliate = r.data[0]
            self.stats["affiliates_enrolled"] += 1
            log.info(f"[affiliate_recruiter] Enrolled: {name} <{email}> → code={referral_code}")

            # For buyer-sourced prospects, also create an affiliate_links
            # record so the tracking pixel fires on /track/aff/{code}
            if source == "buyer" and prospect.get("source_id"):
                try:
                    sb.table("affiliate_links").insert({
                        "buyer_id": prospect["source_id"],
                        "code": referral_code,
                        "label": f"{name} — Auto-enrolled by recruiter",
                        "active": True,
                        "click_count": 0,
                        "conversion_count": 0,
                    }).execute()
                    log.info(f"[affiliate_recruiter] affiliate_links created for buyer {prospect['source_id']}")
                except Exception as link_e:
                    log.warning(f"[affiliate_recruiter] affiliate_links insert failed: {link_e}")

            return {
                "id": str(affiliate["id"]),
                "name": name,
                "email": email,
                "referral_code": referral_code,
                "commission_rate": float(affiliate.get("commission_rate", 0.10)),
            }

        except Exception as e:
            err_str = str(e).lower()
            if "unique" in err_str or "duplicate" in err_str:
                log.info(f"[affiliate_recruiter] {email} already enrolled, skipping")
                return None
            log.warning(f"[affiliate_recruiter] enroll error for {prospect.get('email')}: {e}")
            return None

    # ── PHASE 3: OUTREACH ───────────────────────────────────────────

    async def _send_welcome(self, affiliate: dict, offer_type: str) -> bool:
        """Send the initial outreach email with referral link."""
        name = affiliate["name"]
        email = affiliate["email"]
        code = affiliate["referral_code"]
        referral_url = f"{HUB_URL.rstrip('/')}/ref/{code}"
        dashboard_url = f"{HUB_URL.rstrip('/')}/portal/affiliate/login"
        commission = OFFER["commission_label"]

        if offer_type == "nurture":
            # This is a follow-up, not initial outreach
            return False

        if offer_type == "referral" or offer_type == "contractor":
            html = CONTRACTOR_OUTREACH_TEMPLATE.format(
                name=name, commission=commission,
                referral_url=referral_url, dashboard_url=dashboard_url,
            )
        else:
            html = BUYER_OUTREACH_TEMPLATE.format(
                name=name, commission=commission,
                referral_url=referral_url, dashboard_url=dashboard_url,
            )

        subject = OFFER["subject_template"].format(offer_type=offer_type.capitalize())

        # Send via Resend directly
        result = await _send_email_direct(to=email, subject=subject, html=html)
        if result.get("ok"):
            self.stats["outreaches_sent"] += 1
            # Also save as draft for the record
            sb = _get_sb()
            _save_draft(sb, email, subject, html, meta={
                "type": "affiliate_welcome",
                "affiliate_id": affiliate["id"],
                "referral_code": code,
                "offer_type": offer_type,
            })
            return True

        # Fallback: save as pending draft for manual review
        sb = _get_sb()
        _save_draft(sb, email, subject, html, meta={
            "type": "affiliate_welcome",
            "affiliate_id": affiliate["id"],
            "referral_code": code,
            "offer_type": offer_type,
            "send_failed": True,
            "error": result.get("error", ""),
        })
        return False

    async def _send_nurture(self, affiliate: dict) -> bool:
        """Send a follow-up nurture email to a dormant affiliate."""
        name = affiliate["name"]
        email = affiliate["email"]
        code = affiliate["referral_code"]
        referral_url = f"{HUB_URL.rstrip('/')}/ref/{code}"
        commission = OFFER["commission_label"]

        html = NURTURE_TEMPLATE.format(
            name=name, commission=commission, referral_url=referral_url,
        )
        subject = f"Your {commission} affiliate link is ready — here's how to start"

        result = await _send_email_direct(to=email, subject=subject, html=html)
        if result.get("ok"):
            self.stats["nurtures_sent"] += 1
            sb = _get_sb()
            _save_draft(sb, email, subject, html, meta={
                "type": "affiliate_nurture",
                "affiliate_id": affiliate["id"],
                "referral_code": code,
            })
            # Mark the affiliate as nurtured (update notes)
            try:
                sb = _get_sb()
                cur = sb.table("affiliates").select("notes").eq("id", affiliate["id"]).limit(1).execute()
                if cur.data:
                    existing_notes = cur.data[0].get("notes", "") or ""
                    sb.table("affiliates").update({
                        "notes": existing_notes + f"\n[Nurture sent {datetime.now(timezone.utc).isoformat()[:10]}]",
                    }).eq("id", affiliate["id"]).execute()
            except Exception:
                pass
            return True
        return False

    # ── PHASE 4: FULL CYCLE ─────────────────────────────────────────

    async def run_cycle(self) -> Dict:
        """
        One full affiliate recruiter cycle:
        1. Find prospects (buyers without links, contractors, dormant)
        2. Enroll new prospects as affiliates
        3. Send welcome emails with referral links
        4. Send nurture emails to dormant affiliates
        5. Report pipeline
        """
        self.stats["cycles_run"] += 1
        self._last_cycle = datetime.now(timezone.utc).isoformat()

        results = {
            "buyers_found": 0,
            "contractors_found": 0,
            "dormant_found": 0,
            "enrolled": 0,
            "welcomes_sent": 0,
            "nurtures_sent": 0,
            "errors": 0,
        }

        # ── Phase 1: Prospect ────────────────────────────────────────
        buyer_prospects = self._prospect_buyers()
        contractor_prospects = self._prospect_contractors()
        dormant_prospects = self._prospect_owned()

        results["buyers_found"] = len(buyer_prospects)
        results["contractors_found"] = len(contractor_prospects)
        results["dormant_found"] = len(dormant_prospects)

        log.info(
            f"[affiliate_recruiter] Cycle {self.stats['cycles_run']}: "
            f"{len(buyer_prospects)} buyer prospects, "
            f"{len(contractor_prospects)} contractor prospects, "
            f"{len(dormant_prospects)} dormant affiliates"
        )

        self.stats["prospects_found"] += len(buyer_prospects) + len(contractor_prospects)

        # ── Phase 2-3: Enroll + Welcome (max 20 per cycle) ────────
        cap = 20
        enrolled_count = 0
        for prospect in buyer_prospects + contractor_prospects:
            if enrolled_count >= cap:
                log.info(f"[affiliate_recruiter] Reached batch limit of {cap}, deferring remaining")
                results["deferred"] = len(buyer_prospects) + len(contractor_prospects) - enrolled_count
                break
            try:
                affiliate = await self._enroll_affiliate(prospect)
                if affiliate:
                    results["enrolled"] += 1
                    enrolled_count += 1
                    # Determine email quality — phone-matched="high", name-pattern="guess"
                    email_quality = prospect.get("email_quality", "")
                    is_high_quality = email_quality == "high"
                    
                    if is_high_quality:
                        # Verified email from phone match — send welcome
                        sent = await self._send_welcome(affiliate, prospect.get("offer_type", "standard"))
                        if sent:
                            results["welcomes_sent"] += 1
                        await asyncio.sleep(0.3)  # respect Resend 5 req/s rate limit
                    else:
                        # Name-pattern generated email or unknown quality — skip email, mark for SMS
                        log.info(f"[affiliate_recruiter] {affiliate['name']} — email_quality={email_quality or 'unknown'}, skipping welcome (SMS preferred)")
                        results["sms_preferred"] = results.get("sms_preferred", 0) + 1
            except Exception as e:
                log.warning(f"[affiliate_recruiter] Error processing prospect {prospect.get('email')}: {e}")
                results["errors"] += 1
                self.stats["errors"] += 1

        # ── Phase 3b: Welcome for dormant affiliates who never got one ──
        # This is for affiliates who signed up via web form but never got
        # a welcome email (they auto-enrolled, no outreach happened)
        # Skip — they're handled by nurture below

        # ── Phase 4: Nurture dormant affiliates (>7d, 0 clicks) ──────
        nurture_cap = 10  # max nurtures per cycle to preserve email quota
        nurture_sent_count = 0
        for dormant in dormant_prospects:
            if nurture_sent_count >= nurture_cap:
                log.info(f"[affiliate_recruiter] Nurture batch cap of {nurture_cap} reached, deferring {len(dormant_prospects) - nurture_sent_count}")
                results["nurtures_deferred"] = len(dormant_prospects) - nurture_sent_count
                break
            try:
                created_raw = dormant.get("created_at", "")
                if created_raw:
                    try:
                        created = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                        age_days = (datetime.now(timezone.utc) - created).days
                    except Exception:
                        age_days = 30
                else:
                    age_days = 30

                # Only nurture if at least 7 days old (give them time)
                if age_days >= 7 and "nurture" not in (dormant.get("notes", "") or "").lower():
                    sent = await self._send_nurture(dormant)
                    if sent:
                        results["nurtures_sent"] += 1
                        nurture_sent_count += 1
                    await asyncio.sleep(0.3)  # respect Resend 5 req/s rate limit
            except Exception as e:
                log.warning(f"[affiliate_recruiter] Nurture error: {e}")
                results["errors"] += 1

        # ── Persist cycle report ─────────────────────────────────────
        self._persist_cycle(results)

        log.info(
            f"[affiliate_recruiter] Cycle complete: "
            f"{results['enrolled']} enrolled, "
            f"{results['welcomes_sent']} welcomes sent, "
            f"{results['nurtures_sent']} nurtures sent"
        )

        return results

    def _persist_cycle(self, results: dict):
        """Save cycle results to agent_activity table."""
        try:
            import uuid as _uuid
            sb = _get_sb()
            sb.table("agent_activity").insert({
                "agent_name": "affiliate_recruiter",
                "run_id": str(_uuid.uuid4()),
                "status": "ok",
                "meta": {
                    "enrolled": results.get("enrolled", 0),
                    "results": results,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }).execute()
            log.info(f"[affiliate_recruiter] Cycle persisted to agent_activity")
        except Exception as e:
            log.warning(f"[affiliate_recruiter] Could not persist cycle: {e}")

    # ── API METHODS ──────────────────────────────────────────────────

    def snapshot(self) -> Dict:
        """Return full pipeline status."""
        try:
            sb = _get_sb()
            # Count total affiliates
            r1 = sb.table("affiliates").select("id", count="exact").limit(1).execute()
            total = getattr(r1, "count", 0) or len((r1.data or []))

            # Active
            r2 = sb.table("affiliates").select("id", count="exact") \
                .eq("status", "active").limit(1).execute()
            active = getattr(r2, "count", 0) or len((r2.data or []))

            # With clicks
            r3 = sb.table("affiliates").select("id").gt("total_clicks", 0).execute()
            with_clicks = len(r3.data or [])

            # With conversions
            r4 = sb.table("affiliates").select("id").gt("total_conversions", 0).execute()
            with_conversions = len(r4.data or [])

            # Total earnings
            r5 = sb.table("affiliates").select("total_earned_usd").execute()
            total_earned = sum(float(a.get("total_earned_usd", 0) or 0) for a in (r5.data or []))

            # Total clicks
            r6 = sb.table("affiliates").select("total_clicks").execute()
            total_clicks = sum(int(a.get("total_clicks", 0) or 0) for a in (r6.data or []))

            # Buyers without affiliate links (still can be recruited)
            r7 = sb.table("buyers").select("id").eq("is_active", True).execute()
            total_active_buyers = len(r7.data or [])
            r8 = sb.table("affiliate_links").select("buyer_id").execute()
            linked_buyers = len(set(l["buyer_id"] for l in (r8.data or [])))

            # Dormant affiliates (0 clicks, >7 days old)
            r9 = sb.table("affiliates").select("id").eq("total_clicks", 0) \
                .eq("status", "active").execute()
            dormant = len(r9.data or [])

            # Count cycles_run from agent_activity (durable across CLI invocations)
            try:
                past = sb.table("agent_activity").select("id", count="exact") \
                    .eq("agent_name", "affiliate_recruiter").limit(1).execute()
                durable_cycles = getattr(past, "count", 0)
            except Exception:
                durable_cycles = 0

            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "last_cycle": self._last_cycle,
                "cycles_run": durable_cycles,
                "pipeline": {
                    "total_affiliates": total,
                    "active_affiliates": active,
                    "affiliates_with_clicks": with_clicks,
                    "affiliates_with_conversions": with_conversions,
                    "dormant_affiliates": dormant,
                    "total_clicks": total_clicks,
                    "total_earned_usd": round(total_earned, 2),
                    "remaining_buyer_targets": max(0, total_active_buyers - linked_buyers),
                },
                "stats": dict(self.stats),
            }
        except Exception as e:
            return {"error": str(e)[:200]}

    def pipeline(self) -> Dict:
        """Return detailed pipeline breakdown."""
        try:
            sb = _get_sb()
            # Recent affiliates
            recent = sb.table("affiliates").select("name,email,referral_code,total_clicks,total_leads,total_conversions,total_earned_usd,source,created_at") \
                .order("created_at", desc=True).limit(20).execute()

            # Top performers
            top = sb.table("affiliates").select("name,email,referral_code,total_clicks,total_conversions,total_earned_usd") \
                .gt("total_earned_usd", 0) \
                .order("total_earned_usd", desc=True).limit(10).execute()

            # Prospects (active buyers without links)
            buyers = sb.table("buyers").select("id,buyer_name,email,niche").eq("is_active", True).limit(500).execute()
            links = sb.table("affiliate_links").select("buyer_id").execute()
            linked = set(l["buyer_id"] for l in (links.data or []))
            prospects = [b for b in (buyers.data or []) if str(b["id"]) not in linked]

            return {
                "recent_affiliates": recent.data or [],
                "top_performers": top.data or [],
                "prospects_remaining": prospects[:20],
                "prospect_count": len(prospects),
            }
        except Exception as e:
            return {"error": str(e)[:200]}


# ── GLOBAL SINGLETON ─────────────────────────────────────────────────
_AFFILIATE_RECRUITER: Optional[AffiliateRecruiter] = None


def get_affiliate_recruiter() -> AffiliateRecruiter:
    global _AFFILIATE_RECRUITER
    if _AFFILIATE_RECRUITER is None:
        _AFFILIATE_RECRUITER = AffiliateRecruiter()
    return _AFFILIATE_RECRUITER


# ── BACKGROUND LOOP ──────────────────────────────────────────────────
async def run_loop(interval_minutes: int = 60):
    """
    Background loop: run affiliate recruiter cycles periodically.
    Configure via AFFILIATE_RECRUITER_INTERVAL env var (default 60 min).
    """
    if interval_minutes is None:
        try:
            interval_minutes = int(os.environ.get("AFFILIATE_RECRUITER_INTERVAL", "60"))
        except (ValueError, TypeError):
            interval_minutes = 60

    log.info(f"[affiliate_recruiter] Bot ONLINE · interval={interval_minutes}m")
    recruiter = get_affiliate_recruiter()

    # Heartbeat to agent registry
    async def heartbeat():
        try:
            sb = _get_sb()
            sb.table("agent_registry").upsert({
                "agent_name": "affiliate_recruiter",
                "role_name": "affiliate_specialist",
                "status": "ACTIVE",
                "last_ping": datetime.now(timezone.utc).isoformat(),
                "enabled": True,
                "capabilities": [
                    "manage_affiliates", "recruit_partners",
                    "track_affiliate_performance", "affiliate_enrollment",
                    "affiliate_outreach", "referral_link_management",
                    "affiliate_nurture",
                ],
                "task_types": ["affiliate.recruit", "affiliate.report", "affiliate.optimize"],
            }, on_conflict="agent_name").execute()
        except Exception:
            pass

    await heartbeat()

    while True:
        try:
            log.info("[affiliate_recruiter] Running cycle...")
            result = await recruiter.run_cycle()
            enrolled = result.get("enrolled", 0)
            welcomed = result.get("welcomes_sent", 0)
            log.info(f"[affiliate_recruiter] Cycle complete — {enrolled} enrolled, {welcomed} welcomed")
            await heartbeat()
        except Exception as e:
            log.error(f"[affiliate_recruiter] Cycle error: {e}")
            recruiter.stats["errors"] += 1

        await asyncio.sleep(interval_minutes * 60)


# ── FASTAPI ROUTES ──────────────────────────────────────────────────
def register_affiliate_recruiter_routes(
    app: "FastAPI",
    *,
    require_auth: Callable,
):
    """Wire affiliate recruiter API routes on the hub."""
    from fastapi import Depends, Query

    recruiter = get_affiliate_recruiter()

    @app.get("/api/v1/affiliate-recruiter/snapshot")
    async def ar_snapshot(auth: bool = Depends(require_auth)):
        return recruiter.snapshot()

    @app.get("/api/v1/affiliate-recruiter/pipeline")
    async def ar_pipeline(auth: bool = Depends(require_auth)):
        return recruiter.pipeline()

    @app.post("/api/v1/affiliate-recruiter/run-cycle")
    async def ar_run_cycle(auth: bool = Depends(require_auth)):
        result = await recruiter.run_cycle()
        return {"ok": True, "results": result}

    log.info("[affiliate_recruiter] Routes registered · /api/v1/affiliate-recruiter/{snapshot,pipeline,run-cycle}")


# ── STANDALONE CLI ───────────────────────────────────────────────────
def run():
    """Sync entry point for main.py agent loop compatibility."""
    asyncio.run(run_loop())


if __name__ == "__main__":
    import sys
    if "--cycle" in sys.argv:
        result = asyncio.run(get_affiliate_recruiter().run_cycle())
        print(json.dumps(result, indent=2, default=str))
    elif "--snapshot" in sys.argv:
        snap = get_affiliate_recruiter().snapshot()
        print(json.dumps(snap, indent=2, default=str))
    else:
        asyncio.run(run_loop())
