"""
EMPIRE V49 - COMPLIANCE RULES ENGINE
=====================================
EXPLICIT hardcoded rules (NOT an LLM guessing at law - that would give false confidence).
Real protection: any risky action passes through check() and is ALLOWED or BLOCKED with a reason.
Encodes the non-negotiable lines: no homeowner cold-contact, billing gated on qualified+90s,
no cold outreach from main domain, no banned-platform scraping.
"""
import re

PROTECTED_DOMAINS = ["empire-ai.co.uk"]
BANNED_SCRAPE_PLATFORMS = ["linkedin"]

def _looks_like_homeowner_contact(payload):
    target = str(payload.get("target_type", "")).lower()
    if target in ("homeowner", "consumer", "individual", "resident"):
        return True
    if payload.get("is_individual") is True and payload.get("channel") in ("sms", "call", "email"):
        return True
    return False

def check(action_type, payload=None):
    """Return {allowed, reason, rule}. Deterministic, no LLM."""
    payload = payload or {}
    at = (action_type or "").lower()

    # RULE 1: never cold-contact individual homeowners (TCPA/privacy)
    if at in ("outreach", "contact", "send", "dial"):
        if _looks_like_homeowner_contact(payload):
            return {"allowed": False, "rule": "no_homeowner_cold_contact",
                    "reason": "Blocked: contacting an individual homeowner directly (TCPA/privacy). Homeowners must reach us inbound."}

    # RULE 2: revenue may only book on qualified + 90s+ calls
    if at in ("book_revenue", "charge", "bill"):
        dur = payload.get("duration_seconds", 0) or 0
        qualified = payload.get("qualified", False)
        if not (qualified and dur >= 90):
            reason = "Blocked: billing requires qualified=True AND duration>=90s (got qualified=" + str(qualified) + ", duration=" + str(dur) + ")."
            return {"allowed": False, "rule": "billing_gate", "reason": reason}

    # RULE 3: no cold/bulk outreach from a protected (transactional) domain
    if at in ("outreach", "send", "email"):
        frm = str(payload.get("from_domain", "")).lower()
        is_cold = payload.get("cold", False)
        if is_cold and any(d in frm for d in PROTECTED_DOMAINS):
            reason = "Blocked: cold outreach from protected domain " + frm + " would poison magic-link reputation. Use a burner domain."
            return {"allowed": False, "rule": "protect_transactional_domain", "reason": reason}

    # RULE 4: no scraping banned platforms
    if at in ("scrape", "harvest"):
        plat = str(payload.get("platform", "")).lower()
        if any(b in plat for b in BANNED_SCRAPE_PLATFORMS):
            reason = "Blocked: scraping " + plat + " violates ToS. Use the official API / Sales Navigator CSV export instead."
            return {"allowed": False, "rule": "no_banned_scraping", "reason": reason}

    return {"allowed": True, "rule": "none", "reason": "ok"}

def assert_allowed(action_type, payload=None):
    """Raise if blocked - for code paths that must hard-stop on violation."""
    v = check(action_type, payload)
    if not v["allowed"]:
        raise PermissionError("[COMPLIANCE:" + v["rule"] + "] " + v["reason"])
    return True

if __name__ == "__main__":
    tests = [
        ("outreach", {"target_type": "homeowner", "channel": "sms"}),
        ("outreach", {"target_type": "business", "channel": "email", "from_domain": "burner.com"}),
        ("book_revenue", {"qualified": True, "duration_seconds": 120}),
        ("book_revenue", {"qualified": False, "duration_seconds": 200}),
        ("send", {"cold": True, "from_domain": "empire-ai.co.uk"}),
        ("scrape", {"platform": "linkedin"}),
        ("scrape", {"platform": "google_places"}),
    ]
    for at, pl in tests:
        v = check(at, pl)
        mark = "ALLOW" if v["allowed"] else "BLOCK"
        print("[" + mark + "] " + at + " " + str(pl) + " -> " + v["reason"])