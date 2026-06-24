"""
EMPIRE V49 · MASS TORT BRIDGE (recall -> legal buyer dialer)
============================================================
Pulls the latest FDA recalls (across drugs, devices, food endpoints),
classifies each into one of the 5 legal sub_niches via the
recall_classifier, and dials the matching legal buyer's vonage number
- but only after the legal_call_quality_gate passes for that lead.

This is step 3 of the mass-tort lane-sort plan: the bridge no longer
hardcodes a single destination phone, and no longer fires every
recall to every sub_niche. Each recall routes to exactly one buyer
based on (niche='Legal', sub_niche=<classified>).

Routing is data-driven (buyers table) not code-driven. To add a new
legal buyer, INSERT a row with the right sub_niche. No code change.

Patched 2026-06-12:
  - Replaced the hardcoded `+12142277528` with a buyers-table lookup.
  - Replaced the single-endpoint FDA pull with the multi-endpoint
    recall_classifier.
  - One call per (sub_niche, recall) - not all 5 sub-niches on
    every recall.
  - Idempotent: if a sub_niche has no active buyer with a real phone
    number, it is skipped (no fake-number dialling).
  - Compliance audit logging preserved.
  - Quality gate (legal_call_quality_gate) enforced before every
    dial. Replaces the proposed 5-panel LLM consensus with 3
    deterministic if-statements. 0 LLM calls per dial decision.
"""

import os
import sys

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


from supabase import create_client


# Lazy imports so a syntax error in either module doesn't kill the
# import chain (helps with debugging).
try:
    from bots.recall_classifier import fetch_one_per_sub_niche
except ImportError:
    sys.path.insert(0, "/root/empire-v49")
    from bots.recall_classifier import fetch_one_per_sub_niche

try:
    from bots.legal_call_quality_gate import evaluate as gate_evaluate
except ImportError:
    sys.path.insert(0, "/root/empire-v49")
    from bots.legal_call_quality_gate import evaluate as gate_evaluate


# These are imported lazily inside the function so a missing
# dialer / compliance module produces a clean log line, not a
# traceback at import time.
def _get_dialer():
    try:
        from empire_outbound_dialer import initiate_legal_call, ComplianceBlock
        return initiate_legal_call, ComplianceBlock
    except ImportError as e:
        print(f"[BRIDGE] empire_outbound_dialer not importable: {e}")
        return None, None


def _log_compliance_block(sb, phone: str, rule: str, reason: str, device: str = ""):
    try:
        sb.table("compliance_audit_logs").insert({
            "action": "legal_bridge_blocked",
            "entity_type": "outbound_call",
            "entity_id": phone,
            "details": {"rule": rule, "reason": reason, "device": device},
        }).execute()
    except Exception:
        pass


def _lookup_buyer(sb, sub_niche: str) -> dict | None:
    """
    Return the active Legal buyer for the given sub_niche, or None.
    """
    res = (
        sb.table("buyers")
        .select("id, buyer_name, destination_phone, base_payout, is_active, "
                "hours_open, hours_close, timezone, state_coverage")
        .eq("niche", "Legal")
        .eq("sub_niche", sub_niche)
        .eq("is_active", True)
        .execute()
    )
    rows = [r for r in res.data if r.get("destination_phone")]
    if not rows:
        return None
    return rows[0]


def _log_call(sb, call_uuid: str, status: str, device: str):
    try:
        from empire_revenue_tracker import log_call
        log_call(call_uuid, status, device)
    except ImportError:
        # Fall back to a direct insert. The supabase table is
        # public.call_logs (not call_ledger). Insert with a
        # best-effort column set; ignore if columns don't match.
        try:
            sb.table("call_logs").insert({
                "call_uuid": call_uuid,
                "status": status,
                "device": device,
            }).execute()
        except Exception:
            pass


def bridge_live_targets() -> int:
    """
    Process the latest recall from each legal sub_niche and dial the
    matching buyer's number (if the quality gate passes). Returns the
    number of calls successfully initiated.
    """
    if not os.environ.get("SUPABASE_URL") or not os.getenv("SUPABASE_SERVICE_KEY"):
        print("[BRIDGE] SUPABASE_URL / SUPABASE_SERVICE_KEY missing")
        return 0

    sb = create_client(os.environ["SUPABASE_URL"], os.getenv("SUPABASE_SERVICE_KEY"))
    initiate_legal_call, ComplianceBlock = _get_dialer()
    if initiate_legal_call is None:
        return 0

    recalls = fetch_one_per_sub_niche()
    print(f"[BRIDGE] {len(recalls)} recalls to route (one per sub_niche)")

    calls_initiated = 0
    for recall in recalls:
        sub_niche = recall["sub_niche"]
        device = recall.get("product_description", "Unknown device")

        buyer = _lookup_buyer(sb, sub_niche)
        if not buyer:
            print(f"[BRIDGE] No active Legal/{sub_niche} buyer with a phone. Skipping recall {recall.get('event_id')}.")
            continue

        # ── QUALITY GATE ────────────────────────────────────────────────
        ok, reason = gate_evaluate(buyer, recall)
        if not ok:
            print(f"[GATE]   {sub_niche:<20} BLOCKED recall {recall.get('event_id')}: {reason}")
            continue

        phone = buyer["destination_phone"]
        buyer_name = buyer["buyer_name"]
        print(f"[BRIDGE] {sub_niche:<20} recall {recall.get('event_id')} -> {buyer_name} ({phone})")

        try:
            response = initiate_legal_call(phone, device)
            _log_call(sb, response.uuid, response.status, device)
            print(f"[BRIDGE]   Dispatched: {response.uuid} status={response.status}")
            calls_initiated += 1
        except ComplianceBlock as cb:
            print(f"[COMPLIANCE] {sub_niche} call blocked: {cb}")
            _log_compliance_block(sb, phone, cb.rule, str(cb), device)
        except Exception as e:
            print(f"[BRIDGE ERROR] {sub_niche}: {e}")

    return calls_initiated


# Backwards-compatible alias: original entry point was bridge_live_target
# (singular). The new function is plural to reflect that it processes
# one per sub_niche. The singular is preserved as a wrapper.
def bridge_live_target() -> int:
    return bridge_live_targets()


if __name__ == "__main__":
    n = bridge_live_targets()
    print(f"[BRIDGE] Done. {n} call(s) initiated.")
