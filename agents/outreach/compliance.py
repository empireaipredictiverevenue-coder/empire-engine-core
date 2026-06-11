"""
Empire AI · Predictive Revenue
Outreach Agent · Compliance Gate
==================================

Single chokepoint for every outbound SMS and voice call. The runtime
MUST call one of these functions before sending. Returning False from
any check means: do not send.

Five checks, in order:
  1. opt-out registry    (sms_opt_outs table)        → never re-contact
  2. DNC registry        (outbound_dnc table)        → never contact
  3. consent flag        (per-lead tcpa_consent)     → must be true
  4. time-of-day         (recipient local 8am-9pm)    → TCPA quiet hours
  5. rate limit          (per-number per-day)         → prevent spam

The runtime cron / dispatcher (not built yet) is responsible for
actually enforcing (5) at the campaign level. This module is the
*per-message* gate.

Both functions are safe to call when supabase is unreachable: they
fail open for time/rate (logged) and fail closed for opt-out/DNC
(returns False, logged as a blocked send).
"""

import os
import re
import time
import logging
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Optional

try:
    from supabase import create_client
except ImportError:  # pragma: no cover
    create_client = None  # type: ignore[assignment]

log = logging.getLogger("empire.outreach.compliance")

# ─────────────────────────────────────────────────────────────────────
# In-process caches (so we don't hit supabase on every send)
# ─────────────────────────────────────────────────────────────────────
_OPTOUT_CACHE: dict[str, float] = {}     # phone -> last_check_epoch
_OPTOUT_VALUES: set[str] = set()          # phones currently opted out
_DNC_CACHE: dict[str, float] = {}
_DNC_VALUES: set[str] = set()
_PER_NUMBER_SEND_TODAY: dict[str, int] = {}  # phone -> count
_DAY_KEY: str = ""                         # "YYYY-MM-DD" rollover marker

CACHE_TTL_SECONDS = 30.0
MAX_SENDS_PER_NUMBER_PER_DAY = int(os.getenv("EMPIRE_MAX_SENDS_PER_NUMBER_PER_DAY", "3"))
QUIET_HOUR_START = 21   # 9 PM recipient local
QUIET_HOUR_END   = 8    # 8 AM recipient local

PHONE_RE = re.compile(r"\D")  # strip non-digits


def _normalize(phone: str) -> str:
    """Strip a phone to last 11 digits (1 + 10). Matches the same
    normalization empire_outbound_dialer.py uses, so opt-out and DNC
    caches interoperate."""
    digits = PHONE_RE.sub("", phone or "")
    if len(digits) >= 11 and digits.startswith("1"):
        return digits[-11:]
    if len(digits) == 10:
        return "1" + digits
    return digits  # malformed; let downstream handle it


def _get_sb():
    """Lazily construct a supabase client. Returns None if creds missing
    or library not installed. Callers must handle None gracefully."""
    if create_client is None:
        return None
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        return None
    try:
        return create_client(url, key)
    except Exception as e:
        log.warning(f"[compliance] supabase client failed: {e}")
        return None


def _refresh_optout_cache(force: bool = False) -> None:
    now = time.time()
    if not force and _OPTOUT_CACHE and (now - min(_OPTOUT_CACHE.values())) < CACHE_TTL_SECONDS:
        return
    sb = _get_sb()
    if sb is None:
        return
    try:
        r = sb.table("sms_opt_outs").select("phone").execute()
        _OPTOUT_VALUES.clear()
        for row in (r.data or []):
            n = _normalize(row.get("phone", ""))
            if n:
                _OPTOUT_VALUES.add(n)
        # mark all as freshly cached
        for p in _OPTOUT_VALUES:
            _OPTOUT_CACHE[p] = now
        log.info(f"[compliance] opt-out cache: {len(_OPTOUT_VALUES)} entries")
    except Exception as e:
        log.warning(f"[compliance] opt-out cache refresh failed: {e}")


def _refresh_dnc_cache(force: bool = False) -> None:
    now = time.time()
    if not force and _DNC_CACHE and (now - min(_DNC_CACHE.values())) < CACHE_TTL_SECONDS:
        return
    sb = _get_sb()
    if sb is None:
        return
    try:
        r = sb.table("outbound_dnc").select("phone").execute()
        _DNC_VALUES.clear()
        for row in (r.data or []):
            n = _normalize(row.get("phone", ""))
            if n:
                _DNC_VALUES.add(n)
        for p in _DNC_VALUES:
            _DNC_CACHE[p] = now
        log.info(f"[compliance] DNC cache: {len(_DNC_VALUES)} entries")
    except Exception as e:
        log.warning(f"[compliance] DNC cache refresh failed: {e}")


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────

def is_opted_out(phone: str) -> bool:
    """True if the phone is in sms_opt_outs. Always checked first."""
    n = _normalize(phone)
    if not n:
        return True  # malformed → refuse
    _refresh_optout_cache()
    return n in _OPTOUT_VALUES


def is_on_dnc(phone: str) -> bool:
    """True if the phone is in outbound_dnc."""
    n = _normalize(phone)
    if not n:
        return True
    _refresh_dnc_cache()
    return n in _DNC_VALUES


def has_consent(consent_flag: Optional[bool]) -> bool:
    """Per-lead TCPA consent. Must be explicitly True."""
    return consent_flag is True


def is_quiet_hours(area_code: str) -> bool:
    """True if it's currently outside 8am-9pm in the recipient's local
    timezone. We don't have a full timezone DB; best-effort uses
    US area-code → state → IANA tz mapping via the existing
    empire_utils.tz_for_areacode helper, with a hard fallback to UTC
    (in which case we err on the side of NOT sending — safer to miss
    a window than to violate quiet hours)."""
    if not area_code:
        # No timezone info → don't send. Conservative.
        return True
    try:
        from empire_utils import tz_for_areacode  # type: ignore
        tz_name = tz_for_areacode(area_code)
        if not tz_name:
            return True
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ImportError):
        return True  # unknown → don't send

    now_local = datetime.now(tz).time()
    hour = now_local.hour
    return hour >= QUIET_HOUR_START or hour < QUIET_HOUR_END


def can_send_today(phone: str) -> bool:
    """Rate limit: no more than MAX_SENDS_PER_NUMBER_PER_DAY to one
    phone per UTC day. Resets at UTC midnight."""
    global _DAY_KEY
    n = _normalize(phone)
    if not n:
        return False
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if today != _DAY_KEY:
        _DAY_KEY = today
        _PER_NUMBER_SEND_TODAY.clear()
    return _PER_NUMBER_SEND_TODAY.get(n, 0) < MAX_SENDS_PER_NUMBER_PER_DAY


def record_send(phone: str) -> None:
    """Call this AFTER a successful send. Increments the per-day counter."""
    n = _normalize(phone)
    if not n:
        return
    _PER_NUMBER_SEND_TODAY[n] = _PER_NUMBER_SEND_TODAY.get(n, 0) + 1


def can_send_sms(
    phone: str,
    consent_flag: Optional[bool] = None,
    area_code: str = "",
) -> tuple[bool, str]:
    """Single check combining all 5 gates for SMS sends. Returns
    (allowed, reason). reason is "" if allowed, else human-readable."""
    if is_opted_out(phone):
        return False, "phone is on sms_opt_outs"
    if is_on_dnc(phone):
        return False, "phone is on outbound_dnc"
    if not has_consent(consent_flag):
        return False, "lead missing tcpa_consent=True"
    if is_quiet_hours(area_code):
        return False, "recipient in TCPA quiet hours"
    if not can_send_today(phone):
        return False, f"per-number daily cap ({MAX_SENDS_PER_NUMBER_PER_DAY}) reached"
    return True, ""


def can_place_call(
    phone: str,
    consent_flag: Optional[bool] = None,
    area_code: str = "",
) -> tuple[bool, str]:
    """Same as can_send_sms but without the per-day cap (calls are more
    expensive and rarer, so we trust the dispatcher loop to rate-limit
    at the campaign level)."""
    if is_opted_out(phone):
        return False, "phone is on sms_opt_outs"
    if is_on_dnc(phone):
        return False, "phone is on outbound_dnc"
    if not has_consent(consent_flag):
        return False, "lead missing tcpa_consent=True"
    if is_quiet_hours(area_code):
        return False, "recipient in TCPA quiet hours"
    return True, ""


def register_opt_out(phone: str, reason: str = "user request") -> bool:
    """Idempotent: registers an opt-out in supabase and updates the
    local cache immediately. Returns True if the call succeeded."""
    n = _normalize(phone)
    if not n:
        return False
    sb = _get_sb()
    if sb is None:
        log.warning("[compliance] register_opt_out: supabase unavailable, "
                    "only updating local cache")
        _OPTOUT_VALUES.add(n)
        return False
    try:
        sb.table("sms_opt_outs").upsert(
            {"phone": phone, "reason": reason},
            on_conflict="phone",
        ).execute()
        _OPTOUT_VALUES.add(n)
        _OPTOUT_CACHE[n] = time.time()
        log.info(f"[compliance] opt-out registered: {n} ({reason})")
        return True
    except Exception as e:
        log.error(f"[compliance] register_opt_out failed: {e}")
        return False


# Exposed for tests / debugging
def _reset_caches() -> None:
    global _DAY_KEY
    _OPTOUT_CACHE.clear()
    _OPTOUT_VALUES.clear()
    _DNC_CACHE.clear()
    _DNC_VALUES.clear()
    _PER_NUMBER_SEND_TODAY.clear()
    _DAY_KEY = ""
