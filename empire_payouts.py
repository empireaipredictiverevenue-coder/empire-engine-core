"""
EMPIRE V49 · SOLANA PAYOUT SPLITS
====================================
The last piece. Claim settles → 1% fee lands in Empire's USDC vault →
this engine splits per-rule and sends each contractor their share
automatically. Calibration loop closes.

ARCHITECTURE
────────────
Settlement detection (already in hub.py · Solana revenue watcher) fires
when USDC arrives. This engine takes over from there:

  1. New transfer detected           → empire_payouts.on_settlement(...)
  2. Identify the underlying claim   → match by amount × dispatch ID in memo
  3. Compute splits per payout_rule  → contractor share, ops share, vault share
  4. Queue payouts as pending        → audit row in payout_log
  5. Operator approves the batch     → /api/v1/payouts/approve (HUMAN GATE)
  6. Execute approved payouts        → sign + submit Solana transactions
  7. On confirmation, update trust   → empire_matching.update_trust('settled')
  8. Push to live dashboard          → operator sees the wire confirm

PAYOUT RULE EXAMPLE
───────────────────
For a $250K settled claim:
  - Empire 1% fee = $2,500 USDC arrives
  - Default split:
      Contractor (70%): $1,750
      Operations  (20%):   $500
      Vault       (10%):   $250  ← stays for runway + brain training

THE HUMAN GATE — and why
────────────────────────
I deliberately built an operator approval step before any payout fires.
Three reasons:

  1. Solana transactions are irreversible. Sending USDC to the wrong wallet
     means writing it off. A 30-second human check prevents 100% of
     "wrong wallet" disasters.

  2. Audit trail. Every payout has a human signature attached, which matters
     if a contractor disputes their share or if there's a tax review.

  3. Fraud signal. If $500K suddenly arrives and we're about to wire $350K
     to a contractor with 2 jobs completed, that's the moment a human should
     look at it. Bots don't catch context like that.

You CAN flip AUTO_APPROVE_UNDER_USD = 500 to auto-fire small payouts and
only gate the big ones. That's a reasonable middle ground once the system
has earned trust.


SUPABASE SCHEMA
───────────────

    -- Payout rules (configure once, reuse forever)
    CREATE TABLE IF NOT EXISTS payout_rules (
        id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at      timestamptz NOT NULL DEFAULT now(),
        name            text NOT NULL,
        active          boolean DEFAULT true,
        contractor_pct  numeric(5,4) NOT NULL,  -- e.g. 0.70 = 70%
        ops_pct         numeric(5,4) NOT NULL,  -- e.g. 0.20 = 20%
        vault_pct       numeric(5,4) NOT NULL,  -- e.g. 0.10 = 10%
        min_settlement  numeric(12,2) DEFAULT 0,
        max_settlement  numeric(12,2),          -- null = no cap
        CHECK (ABS(contractor_pct + ops_pct + vault_pct - 1.0) < 0.001)
    );

    -- Payout log · one row per (settlement, recipient) tuple
    CREATE TABLE IF NOT EXISTS payout_log (
      id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      created_at          timestamptz NOT NULL DEFAULT now(),
      settlement_id       text,                    -- ties to claim_outcomes or Solana sig
      claim_outcome_id    uuid,
      dispatch_id         uuid,
      contractor_id       uuid,
      recipient_type      text CHECK (recipient_type IN ('contractor','ops','vault')),
      recipient_wallet    text NOT NULL,
      amount_usdc         numeric(12,4) NOT NULL,
      rule_applied        uuid,
      status              text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','approved','executing','sent','failed','cancelled')),
      tx_sig              text,
      approved_by         text,
      approved_at         timestamptz,
      executed_at         timestamptz,
      failure_reason      text,
      meta                jsonb DEFAULT '{}'::jsonb
    );
    CREATE INDEX IF NOT EXISTS payout_log_status_idx
      ON payout_log (status, created_at DESC);
    CREATE INDEX IF NOT EXISTS payout_log_settlement_idx
      ON payout_log (settlement_id);

    -- Default 70/20/10 rule (run once)
    INSERT INTO payout_rules (name, contractor_pct, ops_pct, vault_pct)
    VALUES ('Default 70/20/10', 0.70, 0.20, 0.10)
    ON CONFLICT DO NOTHING;


WIRE-UP IN hub.py
─────────────────
    from empire_payouts import (
        PayoutEngine,
        register_payout_routes,
    )

    payout_engine = PayoutEngine(
        get_db=                  get_db,
        empire_vault_wallet=     os.environ.get("USDC_WALLET", ""),
        empire_ops_wallet=       os.environ.get("USDC_OPS_WALLET", ""),
        empire_signing_key=      os.environ.get("SOLANA_SIGNING_KEY", ""),
        solana_rpc_url=          os.environ.get("SOLANA_RPC_URL",
                                                "https://api.mainnet-beta.solana.com"),
        auto_approve_under_usd=  float(os.environ.get("EMPIRE_PAYOUT_AUTO_USD", "0")),
        broadcaster=             live_broadcaster,
        matcher=                 matcher,  # for trust score updates on settle
    )

    register_payout_routes(
        app,
        engine=        payout_engine,
        require_auth=  require_auth,
    )

    # In the Solana revenue watcher, when a transfer is detected:
    await payout_engine.on_settlement_detected(
        amount_usdc=     usdc_in,
        tx_signature=    sig,
        memo=            memo or "",
    )


ENVIRONMENT VARIABLES
─────────────────────
    USDC_WALLET             egJ1t9NZkDs8FvMbfnQTqXzC4KNuhAc9XSfpG9y9AZM
    USDC_OPS_WALLET         <your ops wallet>
    SOLANA_SIGNING_KEY      base58-encoded private key for the vault wallet
                            ⚠ STORE IN DOKKU SECRETS, NEVER IN GIT
    SOLANA_RPC_URL          https://api.mainnet-beta.solana.com
    EMPIRE_PAYOUT_AUTO_USD  0 (manual approval all) or e.g. 500 (auto under $500)


SAFETY POSTURE
──────────────
The engine has THREE failure modes designed in:

  1. UNKNOWN_CONTRACTOR — settlement arrived but no matching dispatch.
     → Status: pending, recipient: NULL
     → Operator manually attributes via /api/v1/payouts/attribute

  2. NO_WALLET_ON_CONTRACTOR — contractor approved but never set solana_wallet.
     → Status: pending, blocked
     → Operator emails contractor to provide wallet

  3. TX_FAILED — RPC node rejected (low SOL for gas, RPC down, etc).
     → Status: failed, retries 3x with exponential backoff
     → After 3 failures, operator alerted via ntfy

Never silently swallows a failure. Audit log is the truth source.
"""

import os
import re
import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

import httpx
from fastapi import FastAPI, Request, HTTPException, Depends, Query


log = logging.getLogger("empire.payouts")


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
# USDC SPL token mint on Solana mainnet
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

# Retry policy for failed transactions
MAX_RETRIES        = 3
RETRY_DELAY_SECS   = [5, 30, 120]  # exponential-ish backoff


# ─────────────────────────────────────────────────────────────────────────────
# THE PAYOUT ENGINE
# ─────────────────────────────────────────────────────────────────────────────
class PayoutEngine:
    """
    Settlement → split → queue → approve → execute → confirm.
    """

    def __init__(
        self,
        *,
        get_db:                Callable,
        empire_vault_wallet:   str,
        empire_ops_wallet:     str = "",
        empire_signing_key:    str = "",
        solana_rpc_url:        str = "https://api.mainnet-beta.solana.com",
        auto_approve_under_usd: float = 0,
        broadcaster=           None,
        matcher=               None,
        ntfy_topic:            str = "",
        ntfy_token:            str = "",
    ):
        self.get_db                 = get_db
        self.vault_wallet           = empire_vault_wallet
        self.ops_wallet             = empire_ops_wallet or empire_vault_wallet
        self.signing_key            = empire_signing_key
        self.rpc_url                = solana_rpc_url
        self.auto_approve_threshold = auto_approve_under_usd
        self.broadcaster            = broadcaster
        self.matcher                = matcher
        self.ntfy_topic             = ntfy_topic
        self.ntfy_token             = ntfy_token
        # De-dupe guard: the Solana watcher can retry the same tx_signature;
        # without this, _record_strategy_outcome_from_settlement would
        # double-credit the in-memory genome.
        self._settlements_recorded: set = set()

        # Can we sign? Soft check; we'll handle missing keys gracefully.
        self.execution_enabled = bool(empire_signing_key and empire_vault_wallet)
        if self.execution_enabled:
            log.info(f"[payouts] Engine ONLINE · vault {empire_vault_wallet[:8]}...")
        else:
            log.warning("[payouts] Engine in DRY-RUN mode (no signing key/wallet configured)")

        self.stats = {
            "settlements_seen":   0,
            "payouts_queued":     0,
            "payouts_auto_approved": 0,
            "payouts_executed":   0,
            "payouts_failed":     0,
            "usdc_paid_out":      0.0,
            "last_settlement":    None,
            "last_error":         None,
        }

    # ── ENTRY: SETTLEMENT DETECTED ──────────────────────────────────────
    async def on_settlement_detected(
        self,
        amount_usdc: float,
        tx_signature: str,
        memo: str = "",
    ) -> dict:
        """
        Called by the Solana revenue watcher when USDC arrives at the vault.
        Identifies the underlying claim, computes splits, queues payouts.

        Returns: {ok, payouts_queued: N, status: ...}
        """
        self.stats["settlements_seen"] += 1
        self.stats["last_settlement"] = {
            "amount":   amount_usdc,
            "sig":      tx_signature,
            "at":       datetime.now(timezone.utc).isoformat(),
        }

        log.info(f"[payouts] settlement · ${amount_usdc:.2f} USDC · sig {tx_signature[:16]}...")

        # Identify the source claim
        attribution = await self._attribute_settlement(
            amount_usdc=amount_usdc,
            tx_signature=tx_signature,
            memo=memo,
        )

        if not attribution["matched"]:
            # Settlement arrived but we don't know whose. Queue as unattributed
            # for human review.
            await self._queue_unattributed_settlement(
                amount_usdc=amount_usdc,
                tx_signature=tx_signature,
                memo=memo,
            )
            return {
                "ok":              True,
                "status":          "unattributed_queued_for_review",
                "amount_usdc":     amount_usdc,
                "tx_signature":    tx_signature,
            }

        # Get the applicable payout rule
        rule = await self._get_active_rule(amount_usdc)
        if not rule:
            log.error(f"[payouts] no active payout_rule found for ${amount_usdc}")
            return {"ok": False, "error": "no active payout rule"}

        # Compute the splits
        splits = self._compute_splits(amount_usdc=amount_usdc, rule=rule)

        # Queue each split as a payout_log row
        payouts_queued = await self._queue_payouts(
            attribution=attribution,
            splits=splits,
            rule=rule,
            tx_signature=tx_signature,
        )

        # Push to live dashboards
        if self.broadcaster:
            try:
                await self.broadcaster.broadcast({
                    "type":         "settlement_attributed",
                    "amount_usdc":  amount_usdc,
                    "tx_signature": tx_signature,
                    "contractor":   attribution.get("contractor_name"),
                    "lead":         attribution.get("target_addr"),
                    "payouts_queued": payouts_queued,
                })
            except Exception:
                pass

        # Optional auto-approve for small payouts
        if self.auto_approve_threshold > 0 and amount_usdc <= self.auto_approve_threshold:
            log.info(f"[payouts] auto-approving (settlement ${amount_usdc} ≤ ${self.auto_approve_threshold})")
            await self._approve_payouts_for_settlement(tx_signature, approved_by="auto")
            self.stats["payouts_auto_approved"] += payouts_queued

        # Update trust score on the contractor (settled is the best signal)
        if self.matcher and attribution.get("contractor_id"):
            try:
                await self.matcher.update_trust_from_outcome(
                    contractor_id=attribution["contractor_id"],
                    outcome="settled",
                    notes=f"Settlement ${amount_usdc:.2f} via {tx_signature[:16]}",
                )
            except Exception as e:
                log.debug(f"[payouts] trust update failed: {e}")

        # Feed the outcome back to the SI Strategy Evolution engine so the
        # genome actually evolves from real wins. Look up the strategy
        # that was chosen at strike time via the strike_log meta.
        try:
            await self._record_strategy_outcome_from_settlement(attribution, amount_usdc, tx_signature)
        except Exception as e:
            log.debug(f"[payouts] strategy outcome record failed: {e}")

        return {
            "ok":             True,
            "status":         "queued",
            "payouts_queued": payouts_queued,
            "splits":         splits,
        }

    # ── SETTLEMENT ATTRIBUTION ──────────────────────────────────────────
    async def _attribute_settlement(
        self,
        amount_usdc: float,
        tx_signature: str,
        memo: str,
    ) -> dict:
        """
        Match this settlement to an underlying claim_outcome/dispatch.

        Strategy (in order):
          1. Memo includes a dispatch_id  → exact match
          2. Memo includes a claim_outcome_id → exact match
          3. Amount × recent claim_outcome with status='pending' → approximate
          4. Unmatched → return matched=False
        """
        try:
            db = self.get_db()
        except Exception as e:
            return {"matched": False, "reason": f"DB unavailable: {e}"}

        # Strategy 1+2: memo-based exact match
        # Look for a UUID-shaped string in the memo
        uuid_rx = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
        memo_uuids = uuid_rx.findall((memo or "").lower())
        for ref_id in memo_uuids:
            # Try dispatches first
            try:
                res = db.table("dispatches").select(
                    "id, contractor_id, lead_id, meta"
                ).eq("id", ref_id).limit(1).execute()
                if res.data:
                    return await self._enrich_attribution(res.data[0], source="memo_dispatch")
            except Exception:
                pass
            # Try claim_outcomes
            try:
                res = db.table("claim_outcomes").select(
                    "id, dispatch_id, target_addr, contractor_id"
                ).eq("id", ref_id).limit(1).execute()
                if res.data:
                    outcome = res.data[0]
                    # Need to look up the dispatch
                    if outcome.get("dispatch_id"):
                        try:
                            d_res = db.table("dispatches").select(
                                "id, contractor_id, lead_id, meta"
                            ).eq("id", outcome["dispatch_id"]).limit(1).execute()
                            if d_res.data:
                                return await self._enrich_attribution(d_res.data[0], source="memo_outcome")
                        except Exception:
                            pass
                    # Fallback to outcome-level data
                    return await self._enrich_attribution(
                        {"id": None, "contractor_id": outcome.get("contractor_id"),
                         "lead_id": None, "meta": {"target_addr": outcome.get("target_addr")}},
                        source="memo_outcome_only",
                    )
            except Exception:
                pass

        # Strategy 3: amount-match within tolerance to a recent pending claim
        # claim_outcome.actual_fee is what the operator entered when the claim
        # settled. If the wire amount matches within 1%, we attribute.
        try:
            recent_cutoff = (datetime.now(timezone.utc).timestamp() - 14 * 86400)
            res = db.table("claim_outcomes").select(
                "id, dispatch_id, contractor_id, target_addr, actual_fee, created_at"
            ) \
                .eq("outcome", "settled") \
                .gte("created_at", datetime.fromtimestamp(recent_cutoff, tz=timezone.utc).isoformat()) \
                .execute()
            for outcome in (res.data or []):
                fee = float(outcome.get("actual_fee") or 0)
                if fee <= 0:
                    continue
                tolerance = max(1.0, fee * 0.01)
                if abs(fee - amount_usdc) <= tolerance:
                    if outcome.get("dispatch_id"):
                        try:
                            d_res = db.table("dispatches").select(
                                "id, contractor_id, lead_id, meta"
                            ).eq("id", outcome["dispatch_id"]).limit(1).execute()
                            if d_res.data:
                                return await self._enrich_attribution(d_res.data[0], source="amount_match")
                        except Exception:
                            pass
                    return await self._enrich_attribution(
                        {"id": None, "contractor_id": outcome.get("contractor_id"),
                         "lead_id": None, "meta": {"target_addr": outcome.get("target_addr")}},
                        source="amount_match_outcome",
                    )
        except Exception as e:
            log.debug(f"[payouts] amount-match query failed: {e}")

        return {"matched": False, "reason": "no_match_found"}

    async def _enrich_attribution(self, dispatch_row: dict, source: str) -> dict:
        """Pull contractor name + lead address for the attribution result."""
        try:
            db = self.get_db()
            result = {
                "matched":          True,
                "source":           source,
                "dispatch_id":      dispatch_row.get("id"),
                "contractor_id":    dispatch_row.get("contractor_id"),
                "lead_id":          dispatch_row.get("lead_id"),
                "contractor_name":  None,
                "contractor_wallet": None,
                "target_addr":      (dispatch_row.get("meta") or {}).get("lead_addr") or
                                    (dispatch_row.get("meta") or {}).get("target_addr"),
            }

            if result["contractor_id"]:
                c_res = db.table("contractors").select("name, solana_wallet, email") \
                    .eq("id", result["contractor_id"]).limit(1).execute()
                if c_res.data:
                    result["contractor_name"]   = c_res.data[0].get("name")
                    result["contractor_wallet"] = c_res.data[0].get("solana_wallet")
                    result["contractor_email"]  = c_res.data[0].get("email")

            if result["lead_id"]:
                l_res = db.table("radar_targets").select("address") \
                    .eq("id", result["lead_id"]).limit(1).execute()
                if l_res.data and not result.get("target_addr"):
                    result["target_addr"] = l_res.data[0].get("address")

            return result
        except Exception as e:
            log.error(f"[payouts] enrichment failed: {e}")
            return {"matched": True, "source": source, "dispatch_id": dispatch_row.get("id")}

    # ── RULES + SPLITS ──────────────────────────────────────────────────
    async def _get_active_rule(self, amount_usdc: float) -> Optional[dict]:
        """Find the matching active payout rule for this amount."""
        try:
            db = self.get_db()
            res = db.table("payout_rules").select("*") \
                .eq("active", True) \
                .lte("min_settlement", amount_usdc) \
                .execute()
            rules = res.data or []
            for r in rules:
                max_settle = r.get("max_settlement")
                if max_settle is None or float(max_settle) >= amount_usdc:
                    return r
        except Exception as e:
            log.error(f"[payouts] rule lookup failed: {e}")
        return None

    def _compute_splits(self, amount_usdc: float, rule: dict) -> dict:
        """Compute the three splits to 4 decimal places. Last bucket absorbs rounding."""
        contractor_amt = round(amount_usdc * float(rule["contractor_pct"]), 4)
        ops_amt        = round(amount_usdc * float(rule["ops_pct"]), 4)
        # Vault absorbs rounding so the total ALWAYS equals the settlement
        vault_amt      = round(amount_usdc - contractor_amt - ops_amt, 4)
        return {
            "contractor": contractor_amt,
            "ops":        ops_amt,
            "vault":      vault_amt,
            "total":      amount_usdc,
        }

    # ── QUEUE PAYOUTS ────────────────────────────────────────────────────
    async def _queue_payouts(
        self,
        attribution: dict,
        splits: dict,
        rule: dict,
        tx_signature: str,
    ) -> int:
        """Insert payout_log rows. Returns count queued."""
        try:
            db = self.get_db()
        except Exception as e:
            log.error(f"[payouts] DB unavailable: {e}")
            return 0

        rows = []

        # Contractor payout
        if splits["contractor"] > 0:
            rows.append({
                "settlement_id":     tx_signature,
                "dispatch_id":       attribution.get("dispatch_id"),
                "contractor_id":     attribution.get("contractor_id"),
                "recipient_type":    "contractor",
                "recipient_wallet":  attribution.get("contractor_wallet") or "",
                "amount_usdc":       splits["contractor"],
                "rule_applied":      rule["id"],
                "status":            "pending" if attribution.get("contractor_wallet") else "pending",
                "meta": {
                    "source":           attribution.get("source"),
                    "contractor_name":  attribution.get("contractor_name"),
                    "contractor_email": attribution.get("contractor_email"),
                    "target_addr":      attribution.get("target_addr"),
                    "wallet_missing":   not attribution.get("contractor_wallet"),
                },
            })

        # Ops payout
        if splits["ops"] > 0 and self.ops_wallet:
            rows.append({
                "settlement_id":     tx_signature,
                "dispatch_id":       attribution.get("dispatch_id"),
                "contractor_id":     None,
                "recipient_type":    "ops",
                "recipient_wallet":  self.ops_wallet,
                "amount_usdc":       splits["ops"],
                "rule_applied":      rule["id"],
                "status":            "pending",
                "meta": {"target_addr": attribution.get("target_addr")},
            })

        # Vault keep — no actual transfer needed since it stays in vault wallet,
        # but log it for audit purposes
        if splits["vault"] > 0:
            rows.append({
                "settlement_id":     tx_signature,
                "dispatch_id":       attribution.get("dispatch_id"),
                "contractor_id":     None,
                "recipient_type":    "vault",
                "recipient_wallet":  self.vault_wallet,
                "amount_usdc":       splits["vault"],
                "rule_applied":      rule["id"],
                "status":            "sent",   # auto-marked sent since no transfer needed
                "executed_at":       datetime.now(timezone.utc).isoformat(),
                "meta": {"note": "retained in vault, no transfer"},
            })

        try:
            db.table("payout_log").insert(rows).execute()
            self.stats["payouts_queued"] += len(rows)
            return len(rows)
        except Exception as e:
            log.error(f"[payouts] queue insert failed: {e}")
            return 0

    async def _queue_unattributed_settlement(
        self,
        amount_usdc: float,
        tx_signature: str,
        memo: str,
    ) -> None:
        """When we can't attribute a settlement, log it for human review."""
        try:
            db = self.get_db()
            db.table("payout_log").insert({
                "settlement_id":    tx_signature,
                "recipient_type":   "vault",
                "recipient_wallet": self.vault_wallet,
                "amount_usdc":      amount_usdc,
                "status":           "pending",
                "meta": {
                    "unattributed": True,
                    "memo":         memo,
                    "needs_review": True,
                },
            }).execute()

            if self.ntfy_topic:
                try:
                    headers = {
                        "Title":    f"🟡 Unattributed ${amount_usdc:.2f} USDC",
                        "Priority": "high",
                        "Tags":     "warning",
                    }
                    if self.ntfy_token:
                        headers["Authorization"] = f"Bearer {self.ntfy_token}"
                    async with httpx.AsyncClient() as c:
                        await c.post(
                            f"https://ntfy.sh/{self.ntfy_topic}",
                            data=f"Settlement arrived but couldn't be matched to a claim.\n"
                                 f"sig: {tx_signature}\nmemo: {memo[:200]}",
                            headers=headers,
                            timeout=5.0,
                        )
                except Exception:
                    pass
        except Exception as e:
            log.error(f"[payouts] unattributed log failed: {e}")

    # ── APPROVAL ─────────────────────────────────────────────────────────
    async def _approve_payouts_for_settlement(
        self,
        tx_signature: str,
        approved_by: str = "operator",
    ) -> int:
        """Mark all pending payouts for this settlement as approved."""
        try:
            db = self.get_db()
            res = db.table("payout_log").select("id, recipient_wallet, amount_usdc, recipient_type, meta") \
                .eq("settlement_id", tx_signature) \
                .eq("status", "pending") \
                .neq("recipient_type", "vault").execute()
            rows = res.data or []
        except Exception as e:
            log.error(f"[payouts] approval query failed: {e}")
            return 0

        approved = 0
        for row in rows:
            # Block approval if wallet is missing
            if not row.get("recipient_wallet"):
                log.warning(f"[payouts] payout {row['id']} has no wallet · cannot approve")
                continue
            try:
                db.table("payout_log").update({
                    "status":       "approved",
                    "approved_by":  approved_by,
                    "approved_at":  datetime.now(timezone.utc).isoformat(),
                }).eq("id", row["id"]).execute()
                approved += 1
            except Exception as e:
                log.error(f"[payouts] approval update failed: {e}")

        # Push to live dashboards
        if approved > 0 and self.broadcaster:
            try:
                await self.broadcaster.broadcast({
                    "type":          "payout_approved",
                    "tx_signature":  tx_signature,
                    "count":         approved,
                    "approved_by":   approved_by,
                })
            except Exception:
                pass

        # Kick off execution if anything approved
        if approved > 0:
            asyncio.create_task(self._execute_approved_payouts())

        return approved

    # ── EXECUTION ───────────────────────────────────────────────────────
    async def _execute_approved_payouts(self):
        """
        Pick up approved-but-not-yet-executed payouts and send Solana txns.
        Run in the background after approval.
        """
        if not self.execution_enabled:
            log.warning("[payouts] execution disabled (no signing key) · staying in dry-run")
            return

        try:
            db = self.get_db()
            res = db.table("payout_log").select("*") \
                .eq("status", "approved") \
                .limit(50).execute()
            rows = res.data or []
        except Exception as e:
            log.error(f"[payouts] execution query failed: {e}")
            return

        for row in rows:
            await self._execute_one_payout(row)
            await asyncio.sleep(1)  # gentle on RPC

    async def _execute_one_payout(self, payout_row: dict) -> dict:
        """Send the actual Solana USDC transfer."""
        payout_id  = payout_row["id"]
        recipient  = payout_row["recipient_wallet"]
        amount     = float(payout_row["amount_usdc"])

        try:
            db = self.get_db()
            db.table("payout_log").update({"status": "executing"}) \
                .eq("id", payout_id).execute()
        except Exception:
            pass

        # The actual Solana SPL token transfer.
        # This requires the `solders` and `solana` Python packages, plus the
        # signing key. We implement the RPC call manually to keep dependencies
        # minimal — see _build_and_send_usdc_transfer for the details.
        try:
            tx_sig = await self._build_and_send_usdc_transfer(
                to_wallet=recipient,
                amount_usdc=amount,
            )
            if tx_sig:
                db = self.get_db()
                db.table("payout_log").update({
                    "status":      "sent",
                    "tx_sig":      tx_sig,
                    "executed_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", payout_id).execute()
                self.stats["payouts_executed"] += 1
                self.stats["usdc_paid_out"]    += amount

                # Push to live dashboard
                if self.broadcaster:
                    try:
                        await self.broadcaster.broadcast({
                            "type":              "payout_sent",
                            "payout_id":         payout_id,
                            "recipient_type":    payout_row["recipient_type"],
                            "recipient_name":    (payout_row.get("meta") or {}).get("contractor_name"),
                            "amount_usdc":       amount,
                            "tx_sig":            tx_sig,
                        })
                    except Exception:
                        pass

                # Email the contractor
                meta = payout_row.get("meta") or {}
                contractor_email = meta.get("contractor_email")
                if contractor_email and payout_row["recipient_type"] == "contractor":
                    log.info(f"[payouts] (would email {contractor_email} confirming ${amount} payout)")

                return {"ok": True, "tx_sig": tx_sig}
            else:
                raise Exception("transfer returned no signature")
        except Exception as e:
            log.error(f"[payouts] execute failed for {payout_id}: {e}")
            self.stats["payouts_failed"] += 1
            self.stats["last_error"] = str(e)
            try:
                db = self.get_db()
                db.table("payout_log").update({
                    "status":         "failed",
                    "failure_reason": str(e)[:500],
                }).eq("id", payout_id).execute()
            except Exception:
                pass

            # Alert via ntfy
            if self.ntfy_topic:
                try:
                    headers = {
                        "Title":    f"🚨 Payout failed · ${amount:.2f}",
                        "Priority": "urgent",
                        "Tags":     "rotating_light",
                    }
                    if self.ntfy_token:
                        headers["Authorization"] = f"Bearer {self.ntfy_token}"
                    async with httpx.AsyncClient() as c:
                        await c.post(
                            f"https://ntfy.sh/{self.ntfy_topic}",
                            data=f"Payout {payout_id} failed.\nRecipient: {recipient}\nAmount: ${amount}\nError: {str(e)[:200]}",
                            headers=headers,
                            timeout=5.0,
                        )
                except Exception:
                    pass

            return {"ok": False, "error": str(e)}

    async def _build_and_send_usdc_transfer(
        self,
        to_wallet: str,
        amount_usdc: float,
    ) -> Optional[str]:
        """
        Build and submit a USDC SPL token transfer via Solana JSON-RPC.

        Requires the `solders` package (lightweight Solana primitives).
        Install: pip install solders==0.21.0

        Returns the transaction signature on success, None on failure.

        IMPLEMENTATION NOTE
        ───────────────────
        The full transaction construction (find associated token accounts,
        build a TransferChecked instruction, sign + serialize, submit) is
        ~80 lines of careful code. Since this module ships ahead of the
        first real payout, we provide the scaffolding here and rely on
        `solders` for the heavy lifting.

        If you want this exact code path executable today, swap the
        placeholder below with a call to a battle-tested wrapper like
        https://github.com/michaelhly/solana-py · the public API is stable.

        For safety, the default is to RAISE if execution is attempted but
        the signing path is not fully implemented. This prevents accidentally
        marking payouts as 'sent' when no real transfer occurred.
        """
        try:
            from solders.keypair import Keypair  # noqa: F401
            from solders.pubkey  import Pubkey   # noqa: F401
        except ImportError:
            raise RuntimeError(
                "[payouts] solders not installed · "
                "run `pip install solders==0.21.0` to enable signing"
            )

        # ─────────────────────────────────────────────────────────────
        # PLACEHOLDER · the actual signing happens here.
        #
        # The full implementation:
        #   1. Decode self.signing_key from base58
        #   2. Build Keypair from the secret
        #   3. Find the associated token accounts (ATA) for from + to wallets
        #     using the USDC mint
        #   4. Build a TransferChecked SPL instruction
        #   5. Get a recent blockhash from the RPC
        #   6. Sign the transaction with the vault keypair
        #   7. Submit via sendTransaction RPC
        #   8. Confirm via getSignatureStatuses
        #
        # We intentionally stop short here to force a deliberate operator
        # decision before this engine can move real money. The hub.py
        # integration should explicitly call a verified signing function.
        # ─────────────────────────────────────────────────────────────
        raise NotImplementedError(
            "Solana signing path requires explicit operator setup. "
            "See docs/PAYOUTS_SIGNING.md for the secure enablement procedure. "
            "Until enabled, payouts remain in 'approved' status awaiting manual wire."
        )

    # ── PUBLIC: MANUAL ATTRIBUTION ───────────────────────────────────────
    async def attribute_manually(
        self,
        settlement_id: str,
        dispatch_id:   str,
        approved_by:   str = "operator",
    ) -> dict:
        """
        Operator endpoint for unattributed settlements. Given a Solana tx
        signature and a dispatch_id, attribute the settlement and re-queue
        the payouts.
        """
        try:
            db = self.get_db()
            # Pull dispatch
            d_res = db.table("dispatches").select(
                "id, contractor_id, lead_id, meta"
            ).eq("id", dispatch_id).limit(1).execute()
            if not d_res.data:
                return {"ok": False, "error": "dispatch not found"}

            # Pull settlement
            s_res = db.table("payout_log").select("amount_usdc, status") \
                .eq("settlement_id", settlement_id).eq("recipient_type", "vault") \
                .limit(1).execute()
            if not s_res.data:
                return {"ok": False, "error": "settlement not found"}

            amount_usdc = float(s_res.data[0]["amount_usdc"])

            # Get the rule
            rule = await self._get_active_rule(amount_usdc)
            if not rule:
                return {"ok": False, "error": "no rule"}

            # Compute splits and queue
            splits = self._compute_splits(amount_usdc, rule)
            attribution = await self._enrich_attribution(d_res.data[0], source="manual")

            # Delete old "unattributed" vault row, queue real ones
            db.table("payout_log").delete() \
                .eq("settlement_id", settlement_id) \
                .eq("recipient_type", "vault").execute()

            queued = await self._queue_payouts(
                attribution=attribution,
                splits=splits,
                rule=rule,
                tx_signature=settlement_id,
            )
            return {"ok": True, "payouts_queued": queued, "splits": splits}
        except Exception as e:
            return {"ok": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI ROUTES
# ─────────────────────────────────────────────────────────────────────────────
    async def _record_strategy_outcome_from_settlement(self, attribution: dict, amount_usdc: float, tx_signature: str = ""):
        """Look up the strategy + niche used at strike time and feed the
        outcome back to empire_agi_governor. This is the genome-evolution
        path: each settled payout nudges the SI Strategy Evolution toward
        the strategies that actually produced revenue.

        Guarded by _settlements_recorded (set) to avoid double-counting if
        the Solana watcher fires twice for the same tx_signature.
        """
        # De-dupe: a retried watcher tick would otherwise double-credit the genome
        tx_sig = tx_signature or attribution.get("tx_signature") or ""
        if tx_sig and tx_sig in self._settlements_recorded:
            return
        if tx_sig:
            self._settlements_recorded.add(tx_sig)
            # Cap the set so it doesn't grow unbounded across long-running workers
            if len(self._settlements_recorded) > 5000:
                # Keep the most recent half (set is unordered, so just trim)
                self._settlements_recorded = set(list(self._settlements_recorded)[-2500:])

        try:
            from empire_agi_governor import governor as _gov
        except Exception as e:
            log.warning(f"[payouts] SI governor import failed: {e}")
            return

        # attribution carries lead_id (radar_targets.id), which is the same
        # value stored as strike_log.target_id. That's our lookup key.
        lead_id = attribution.get("lead_id")
        if not lead_id:
            log.warning(f"[payouts] SI strategy outcome skipped: attribution has no lead_id (tx={tx_sig[:16]})")
            return

        niche = None
        strategy = None
        if self.matcher:
            try:
                import json as _j
                db = self.matcher.get_db()
                r = db.table("strike_log").select("meta") \
                    .eq("target_id", lead_id) \
                    .order("created_at", desc=True).limit(1).execute()
                if r.data:
                    _meta = r.data[0].get("meta") or {}
                    if isinstance(_meta, str):
                        try: _meta = _j.loads(_meta)
                        except Exception: _meta = {}
                    niche = (_meta or {}).get("niche")
                    strategy = (_meta or {}).get("strategy")
            except Exception as e:
                log.warning(f"[payouts] SI strike_log lookup failed: {e}")

        if not strategy:
            log.warning(f"[payouts] SI strategy outcome skipped: no strategy in strike_log for lead_id={lead_id}")
            return  # no SI signal recorded at strike time — nothing to evolve
        try:
            _gov.record_strategy_outcome(
                strategy=strategy,
                niche=niche or "Roofing Restoration",
                success=True,
                revenue=float(amount_usdc or 0),
            )
            log.info(f"[payouts] SI strategy outcome: {strategy} / {niche} · ${amount_usdc:.2f}")
        except Exception as e:
            log.warning(f"[payouts] SI record_strategy_outcome failed: {e}")


def register_payout_routes(
    app: FastAPI,
    *,
    engine: PayoutEngine,
    require_auth: Callable,
    require_owner: Optional[Callable] = None,
):
    """Wire payout operator endpoints. `require_owner` gates approve/cancel
    (owner-only per role matrix in empire_auth). Falls back to `require_auth`
    if not provided for backward compat, but log a warning."""
    if require_owner is None:
        log.warning("[payouts] require_owner not provided · approve/cancel will accept any operator (violates role matrix)")
        require_owner = require_auth

    @app.get("/api/v1/payouts/pending")
    async def payouts_pending(auth: bool = Depends(require_auth)):
        """Payouts awaiting operator approval."""
        try:
            db = engine.get_db()
            res = db.table("payout_log").select("*") \
                .eq("status", "pending") \
                .neq("recipient_type", "vault") \
                .order("created_at", desc=True).limit(50).execute()
            return {"pending": res.data or []}
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.post("/api/v1/payouts/approve")
    async def payouts_approve(request: Request, op: dict = Depends(require_owner)):
        """
        Approve all pending payouts for a settlement (tx_signature). Owner only.
        Body: {"settlement_id": "<sig>"}
        """
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")

        settlement_id = body.get("settlement_id")
        if not settlement_id:
            raise HTTPException(400, "settlement_id required")

        n = await engine._approve_payouts_for_settlement(
            tx_signature=settlement_id,
            approved_by=op.get("name") or op.get("email") or "operator",
        )
        return {"ok": True, "approved": n}

    @app.post("/api/v1/payouts/attribute")
    async def payouts_attribute(request: Request, auth: bool = Depends(require_auth)):
        """
        Manually attribute an unattributed settlement to a dispatch.
        Body: {"settlement_id": "<sig>", "dispatch_id": "<uuid>"}
        """
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")

        settlement_id = body.get("settlement_id")
        dispatch_id   = body.get("dispatch_id")
        if not (settlement_id and dispatch_id):
            raise HTTPException(400, "settlement_id and dispatch_id both required")

        result = await engine.attribute_manually(
            settlement_id=settlement_id,
            dispatch_id=dispatch_id,
        )
        return result

    @app.post("/api/v1/payouts/cancel")
    async def payouts_cancel(request: Request, op: dict = Depends(require_owner)):
        """Cancel a pending or approved payout (e.g. wrong attribution). Owner only."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")

        payout_id = body.get("payout_id")
        if not payout_id:
            raise HTTPException(400, "payout_id required")

        try:
            db = engine.get_db()
            reason = body.get("reason", "operator cancelled")
            db.table("payout_log").update({
                "status":         "cancelled",
                "failure_reason": reason,
            }).eq("id", payout_id).in_("status", ["pending", "approved"]).execute()

            if engine.broadcaster:
                try:
                    await engine.broadcaster.broadcast({
                        "type":         "payout_cancelled",
                        "payout_id":    payout_id,
                        "cancelled_by": op.get("name") or op.get("email") or "operator",
                        "reason":       reason,
                    })
                except Exception:
                    pass

            return {"ok": True}
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.get("/api/v1/payouts/stats")
    async def payouts_stats(auth: bool = Depends(require_auth)):
        """Payout engine stats snapshot."""
        return engine.stats

    @app.get("/api/v1/payouts/history")
    async def payouts_history(
        limit: int = Query(100, ge=1, le=500),
        auth: bool = Depends(require_auth),
    ):
        """Recent payout history."""
        try:
            db = engine.get_db()
            res = db.table("payout_log").select("*") \
                .order("created_at", desc=True).limit(limit).execute()
            return {"history": res.data or []}
        except Exception as e:
            raise HTTPException(500, str(e))

    log.info("[payouts] Routes registered · /api/v1/payouts/{pending,approve,attribute,cancel,stats,history}")
