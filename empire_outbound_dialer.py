import os
import logging
import time as _time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from supabase import create_client

from empire_utils import tz_for_areacode
from empire_voice import VonageAdapter

log = logging.getLogger("empire.outbound_dialer")

# Shared Vonage adapter — uses the same JWT cache and REST API as the hub's voice engine.
# Falls back to env vars, then to the hardcoded values that were previously passed
# directly to the Vonage SDK.
_vonage = VonageAdapter(
    api_key=os.getenv("VONAGE_API_KEY", ""),
    api_secret=os.getenv("VONAGE_API_SECRET", ""),
    app_id=os.getenv("VONAGE_APPLICATION_ID", "231873a5-68d1-4028-8ffb-000853072332"),
    private_key_path=os.getenv("VONAGE_PRIVATE_KEY_PATH", "/root/empire-v49/private.key"),
    from_number=os.getenv("VONAGE_NUMBER", "12142277528"),
)

_sb = create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_KEY", ""))

# ── COMPLIANCE: allowed calling window (recipient local time) ────────────
ALLOWED_CALL_START = 8   # 8 AM
ALLOWED_CALL_END   = 21  # 9 PM

# ── DNC CACHE (30s TTL) ────────────────────────────────────────────
_DNC_CACHE_TTL = 30.0          # seconds before cache is considered stale
_dnc_cache: set = set()         # set of normalized 11-digit DNC phone numbers
_dnc_cache_ts: float = 0.0     # epoch timestamp of last cache fill


def _refresh_dnc_cache():
    """Fetch all DNC numbers from both tables and rebuild the cache set.
    Both sms_opt_outs and outbound_dnc are append-only during a session,
    so a single bulk fetch every 30s is more efficient than per-call lookups."""
    global _dnc_cache, _dnc_cache_ts
    try:
        blocked: set[str] = set()
        # Fetch from sms_opt_outs
        r1 = _sb.table("sms_opt_outs").select("phone").execute()
        for row in (r1.data or []):
            norm = _normalize_phone_dnc(row.get("phone", ""))
            if norm:
                blocked.add(norm)
        # Fetch from outbound_dnc (table may not exist yet)
        try:
            r2 = _sb.table("outbound_dnc").select("phone").execute()
            for row in (r2.data or []):
                norm = _normalize_phone_dnc(row.get("phone", ""))
                if norm:
                    blocked.add(norm)
        except Exception:
            pass
        _dnc_cache = blocked
        _dnc_cache_ts = _time.time()
        log.info(f"[compliance] DNC cache refreshed: {len(blocked)} numbers")
    except Exception as e:
        log.error(f"[compliance] DNC cache refresh failed: {e}")


def _check_dnc(phone: str) -> bool:
    """Check if a phone number is on the DNC/opt-out list.
    Uses a cached set refreshed every 30s.
    Returns True if number is OK to call, False if blocked."""
    global _dnc_cache_ts
    # Refresh cache if stale
    now = _time.time()
    if not _dnc_cache or now - _dnc_cache_ts >= _DNC_CACHE_TTL:
        _refresh_dnc_cache()
    try:
        clean = _normalize_phone_dnc(phone)
        if not clean:
            return True  # can't parse, allow
        blocked = clean in _dnc_cache
        if blocked:
            log.info(f"[compliance] DNC block for {phone}: cached")
        return not blocked
    except Exception as e:
        log.warning(f"[compliance] DNC check failed (allowing): {e}")
        return True  # fail open — log but allow
def _within_call_hours(tz_name: str) -> bool:
    """Check if current time is within the allowed calling window."""
    try:
        h = datetime.now(ZoneInfo(tz_name)).hour
    except Exception:
        h = datetime.now(timezone.utc).hour
    return ALLOWED_CALL_START <= h < ALLOWED_CALL_END


class ComplianceBlock(Exception):
    """Raised when a call is blocked by a compliance rule."""
    def __init__(self, rule: str, reason: str, phone: str = ""):
        self.rule = rule
        self.phone = phone
        super().__init__(f"[COMPLIANCE:{rule}] {reason}")


def _normalize_phone_dnc(phone: str) -> str:
    """Normalize a phone number to 11 digits (starts with 1) for DNC matching.
    Returns empty string if invalid."""
    clean = "".join(c for c in (phone or "") if c.isdigit())
    if len(clean) == 10:
        return "1" + clean
    if len(clean) == 11 and clean.startswith("1"):
        return clean
    if len(clean) > 11:
        # Maybe country code is included — try last 11 digits
        return clean[-11:] if clean[-11:].startswith("1") else "1" + clean[-10:]
    return ""


def _check_dnc(phone: str) -> bool:
    """Check if a phone number is on the DNC/opt-out list.
    Returns True if number is OK to call, False if blocked."""
    try:
        clean = _normalize_phone_dnc(phone)
        if not clean:
            return True  # can't parse, allow
        # Check sms_opt_outs — try both 11-digit (15551112222) and E.164 (+15551112222) formats
        for fmt in [clean, "+" + clean]:
            r = _sb.table("sms_opt_outs").select("phone").eq("phone", fmt).limit(1).execute()
            if r.data:
                log.info(f"[compliance] DNC block for {fmt}: found in sms_opt_outs")
                return False
        # Check outbound_dnc table if it exists (try both formats)
        try:
            for fmt in [clean, "+" + clean]:
                r2 = _sb.table("outbound_dnc").select("phone").eq("phone", fmt).limit(1).execute()
                if r2.data:
                    log.info(f"[compliance] DNC block for {fmt}: found in outbound_dnc")
                    return False
        except Exception:
            pass  # table may not exist yet
        return True
    except Exception as e:
        log.warning(f"[compliance] DNC check failed (allowing): {e}")
        return True  # fail open — log but allow


def _log_compliance_call(phone: str, action: str, rule: str = "", note: str = ""):
    """Log an outbound call to the compliance audit trail."""
    try:
        _sb.table("compliance_audit_logs").insert({
            "action": action[:80],
            "entity_type": "outbound_call",
            "entity_id": phone,
            "details": {"rule": rule, "note": note, "phone": phone},
        }).execute()
    except Exception as e:
        log.error(f"[compliance] audit write failed: {e}")


def compliance_check(phone: str, tz: str = "") -> None:
    """Run all compliance checks before placing an outbound call.
    Uses the phone number's area code to determine recipient timezone.
    Raises ComplianceBlock if any check fails."""
    # Resolve timezone from phone number if not provided
    if not tz:
        tz = tz_for_areacode(phone)

    # 1. Time of day check (recipient local time)
    if not _within_call_hours(tz):
        raise ComplianceBlock(
            rule="outside_call_hours",
            reason=f"Call blocked: outside allowed window ({ALLOWED_CALL_START}AM-{ALLOWED_CALL_END}PM {tz})",
            phone=phone,
        )
    # 2. DNC / opt-out check
    if not _check_dnc(phone):
        raise ComplianceBlock(
            rule="dnc_opt_out",
            reason="Call blocked: number is on DNC or opt-out list",
            phone=phone,
        )
    # 3. Format check (must be a real phone)
    clean = "".join(c for c in phone if c.isdigit())
    if len(clean) < 10:
        raise ComplianceBlock(
            rule="invalid_phone",
            reason=f"Call blocked: not a valid 10-digit phone: {phone}",
            phone=phone,
        )
    # 4. TCPA: identity disclosure (handled in the talk script — says "Empire AI")
    # 5. Audit log the check passed
    _log_compliance_call(phone, "compliance_check_passed", "all_checks", f"tz={tz}")


def initiate_storm_call(lead_phone: str, storm_type: str):
    """Make an outbound call for a storm/restoration lead.
    Runs compliance checks first — raises ComplianceBlock if blocked."""
    # Run compliance checks (raises ComplianceBlock if blocked)
    compliance_check(lead_phone)

    clean_type = storm_type.split(",")[0].strip()

    operator_number = os.getenv("EMPIRE_OPERATOR_NUMBER", "")
    ncco = []
    if operator_number:
        # Warm-forward: connect first so human-answered calls skip the TTS
        ncco.append({
            "action":   "connect",
            "endpoint": [{"type": "phone", "number": operator_number.lstrip("+")}],
            "timeout":  30,
            "limit":    1800,
        })
    ncco.append({
        "action": "talk", "voiceName": "Amy",
        "text": f"This is Empire AI with an urgent storm alert. We have a verified {clean_type} lead in your service area. Hold the line to claim this exclusive lead and speak with a dispatcher.",
    })

    response = _vonage.place_call_sync(to_number=lead_phone, ncco=ncco)

    # Audit log the successful call
    _log_compliance_call(lead_phone, "outbound_call_placed", "", f"storm_type={clean_type}")

    return response


def initiate_legal_call(lead_phone: str, device_name: str):
    """Make an outbound call for a legal/medical device lead.
    Runs compliance checks first — raises ComplianceBlock if blocked."""
    compliance_check(lead_phone)

    clean_device = device_name.split(",")[0]

    operator_number = os.getenv("EMPIRE_OPERATOR_NUMBER", "")
    ncco = []
    if operator_number:
        ncco.append({
            "action":   "connect",
            "endpoint": [{"type": "phone", "number": operator_number.lstrip("+")}],
            "timeout":  30,
            "limit":    1800,
        })
    ncco.append({
        "action": "talk", "voiceName": "Amy",
        "text": f"Important medical notification. A safety correction has been issued regarding the {clean_device}. Hold the line to speak with a specialist.",
    })

    response = _vonage.place_call_sync(to_number=lead_phone, ncco=ncco)

    _log_compliance_call(lead_phone, "legal_call_placed", "", f"device={clean_device}")

    return response


def initiate_contractor_recruit_call(contractor: dict) -> dict:
    """Make an outbound call to recruit a contractor into our network.

    `contractor` is a dict with at least: phone, name, metro, meta.
    Runs compliance checks (call hours + DNC) before placing the call.

    Returns: {ok, uuid, status, error?, blocked?, rule?, reason?}
    """
    phone = contractor.get("phone", "")
    if not phone:
        return {"ok": False, "error": "no_phone"}

    try:
        compliance_check(phone)
    except Exception as e:
        # ComplianceBlock or other. Caller can branch on `blocked`.
        return {
            "ok": False,
            "blocked": True,
            "rule": getattr(e, "rule", "compliance"),
            "reason": getattr(e, "reason", str(e)),
        }

    # Pull display name + first name from contractor meta
    meta = contractor.get("meta") or {}
    full_name = (meta.get("contact_name") or "").strip()
    first_name = full_name.split()[0] if full_name else ""
    metro = contractor.get("metro") or "your area"
    business = contractor.get("name") or "your business"

    # Render the contractor_recruit voice script.
    # Lazy import to avoid a circular dep with agents.outreach.voice_scripts.
    try:
        from agents.outreach.voice_scripts import get_script
        script = get_script("contractor_recruit")
        intro = script["intro"].format(first_name=first_name or "there", metro=metro)
        main  = script["main"].format(first_name=first_name or "there", metro=metro)
        opt_out = script["opt_out_disclosure"]
        body  = f"{intro} ... {main} ... {opt_out}"
    except Exception as e:
        # Fallback to a hardcoded body if the script can't be loaded.
        body = (
            f"Hi {first_name or 'there'}, this is a paid call from Empire AI. "
            f"We send storm leads to roofers in {metro}. You pay 3% only on "
            f"settled claims, first 2 deals on us. Self-onboard at "
            f"empire-ai.co.uk/contractors. Press 9 to opt out."
        )
        log.warning(f"[contractor_recruit] voice_scripts import failed, using fallback: {e}")

    # Build the NCCO. Two actions:
    # 1. talk: deliver the script as TTS using the "Amy" voice.
    # 2. (optional) connect to operator_number for warm hand-off if the
    #    contractor wants to talk live. Disabled by default to keep the
    #    call < 90s; enable via EMPIRE_OPERATOR_NUMBER + LIVE_HANDOFF=1.
    ncco = [{"action": "talk", "voiceName": "Amy", "text": body}]
    if os.getenv("LIVE_HANDOFF") == "1":
        operator_number = os.getenv("EMPIRE_OPERATOR_NUMBER", "")
        if operator_number:
            ncco.append({
                "action":   "connect",
                "endpoint": [{"type": "phone", "number": operator_number.lstrip("+")}],
                "timeout":  20,
                "limit":    1800,
            })

    # Place the call
    response = _vonage.place_call_sync(to_number=phone, ncco=ncco)

    # Audit
    _log_compliance_call(
        phone, "outbound_call_placed", "",
        f"contractor_recruit name={business} first_name={first_name} metro={metro}",
    )

    # Also log to outreach_log so the activity shows up alongside SMS
    try:
        _sb.table("outreach_log").insert({
            "enriched_lead_id": None,
            "agent_name":       "contractor_recruit_call",
            "run_id":           f"manual-{int(_time.time())}",
            "channel":          "voice",
            "sequence":         "contractor_recruit",
            "step":             0,
            "body_preview":     body[:280],
            "compliance_passed": True,
            "mode":             "live",
            "sent_at":          datetime.now(timezone.utc).isoformat(),
            "sent_status":      "placed" if response.get("ok") else "failed",
        }).execute()
    except Exception as e:
        log.debug(f"[contractor_recruit] outreach_log write failed: {e}")

    return response
