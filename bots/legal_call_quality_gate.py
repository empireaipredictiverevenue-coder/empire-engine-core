"""
EMPIRE V49 · LEGAL CALL QUALITY GATE
=====================================
Three hard rules that every legal-lane outbound call must pass
before the bridge dials. Replaces the "5-panel LLM consensus"
blueprint with deterministic if-statements that run in <1ms, cost
$0, and are auditable.

  Rule 1  Active buyer with a real phone
          The buyer row must have is_active=true AND
          destination_phone is not None. Skips silently (no fake
          dialling) when this fails, matching the existing bridge
          behavior.

  Rule 2  Within call window (recipient local time)
          Uses the buyer's hours_open..hours_close + timezone (or
          area-code fallback via empire_utils.tz_for_areacode).
          Outside the window = skip, log "outside hours."

  Rule 3  Recall is real and addressable
          The recall must have a real classification (Class I/II/III,
          not null) and a non-empty product_description. Recalls
          with no description or unknown classification are skipped
          because we can't build a meaningful call script.

The gate returns a (passed: bool, reason: str) tuple. The bridge
caller is responsible for the actual skip/dial decision.

Patched 2026-06-12 (replaces the 5-panel LLM consensus design):
  - All 3 rules are deterministic and auditable.
  - 0 LLM calls per gate evaluation.
  - Same gate for all 5 legal sub_niches (no per-sub_niche
    override needed for the basic case).
"""

import os
import sys
from datetime import datetime
from typing import Tuple


# Manual .env loader (sniper_env may not have python-dotenv).
ENV_PATH = "/root/.env"
if os.path.exists(ENV_PATH):
    with open(ENV_PATH) as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _v = _line.split("=", 1)
            _v = _v.strip()
            if (_v.startswith('"') and _v.endswith('"')) or (_v.startswith("'") and _v.endswith("'")):
                _v = _v[1:-1]
            os.environ[_k.strip()] = _v


# Optional empire_utils import for the timezone helper. Falls back
# to UTC if the helper isn't available so the gate never crashes.
try:
    sys.path.insert(0, "/root/empire-v49")
    from empire_utils import tz_for_areacode
    _HAS_TZ_HELPER = True
except ImportError:
    _HAS_TZ_HELPER = False


# ── RULE 1: ACTIVE BUYER WITH PHONE ─────────────────────────────────────
def _rule1_active_buyer_with_phone(buyer: dict) -> Tuple[bool, str]:
    if not buyer:
        return False, "buyer row missing"
    if not buyer.get("is_active"):
        return False, "buyer is_active=false"
    phone = buyer.get("destination_phone")
    if not phone or not str(phone).strip():
        return False, "buyer has no destination_phone"
    return True, "ok"


# ── RULE 2: WITHIN CALL WINDOW ──────────────────────────────────────────
def _rule2_within_call_window(buyer: dict, now_utc: datetime = None) -> Tuple[bool, str]:
    if now_utc is None:
        now_utc = datetime.utcnow()

    hours_open = buyer.get("hours_open", 8)
    hours_close = buyer.get("hours_close", 21)

    # Resolve recipient timezone: explicit timezone column wins,
    # then area-code fallback, then UTC.
    tz_name = buyer.get("timezone")
    if not tz_name and _HAS_TZ_HELPER:
        phone = buyer.get("destination_phone") or ""
        try:
            tz_name = tz_for_areacode(phone)
        except Exception:
            tz_name = None

    if tz_name:
        try:
            from zoneinfo import ZoneInfo
            local_now = now_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(tz_name))
        except Exception:
            local_now = now_utc
    else:
        local_now = now_utc

    hour = local_now.hour
    if hours_open <= hour < hours_close:
        return True, f"ok (local hour {hour}, window {hours_open}-{hours_close})"
    return False, f"outside call window (local hour {hour}, window {hours_open}-{hours_close})"


# ── RULE 3: RECALL IS REAL ──────────────────────────────────────────────
_VALID_CLASSIFICATIONS = {"Class I", "Class II", "Class III"}


def _rule3_recall_is_real(recall: dict) -> Tuple[bool, str]:
    classification = (recall.get("classification") or "").strip()
    if classification not in _VALID_CLASSIFICATIONS:
        return False, f"recall classification={classification!r} (expected one of {sorted(_VALID_CLASSIFICATIONS)})"

    desc = (recall.get("product_description") or "").strip()
    if not desc:
        return False, "recall has empty product_description"

    return True, "ok"


# ── PUBLIC ENTRY POINT ──────────────────────────────────────────────────
def evaluate(buyer: dict, recall: dict, now_utc: datetime = None) -> Tuple[bool, str]:
    """
    Run all 3 rules. Returns (passed, reason). The first failing
    rule short-circuits so the log shows the exact reason.

    passed=True  means the bridge may dial.
    passed=False means the bridge should skip and log the reason.
    """
    for rule_fn, label in (
        (lambda: _rule1_active_buyer_with_phone(buyer), "rule1_active_buyer"),
        (lambda: _rule2_within_call_window(buyer, now_utc), "rule2_call_window"),
        (lambda: _rule3_recall_is_real(recall), "rule3_recall_real"),
    ):
        ok, reason = rule_fn()
        if not ok:
            return False, f"{label}: {reason}"
    return True, "all rules passed"


# ── SELF-TEST ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    sample_buyer = {
        "is_active": True,
        "destination_phone": "+12145550999",
        "hours_open": 8,
        "hours_close": 21,
        "timezone": "America/Chicago",
    }
    sample_recall = {
        "classification": "Class II",
        "product_description": "MAHURKAR 12 Fr catheter",
    }
    ok, reason = evaluate(sample_buyer, sample_recall)
    print(f"sample good:  passed={ok}  reason={reason}")

    # Failing rule 1: no phone
    no_phone_buyer = dict(sample_buyer); no_phone_buyer["destination_phone"] = None
    ok, reason = evaluate(no_phone_buyer, sample_recall)
    print(f"no phone:     passed={ok}  reason={reason}")

    # Failing rule 3: bad classification
    bad_recall = dict(sample_recall); bad_recall["classification"] = "Class X"
    ok, reason = evaluate(sample_buyer, bad_recall)
    print(f"bad recall:   passed={ok}  reason={reason}")
