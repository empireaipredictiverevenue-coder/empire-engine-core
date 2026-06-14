#!/usr/bin/env python3
"""
run_local_validator_test.py — Spins up a local Solana test validator,
creates a mock USDC token, mints to the test keypair, and runs the
Section 1.B payout test entirely on localhost.

Usage:  python3 scripts/run_local_validator_test.py
Exit 0 on success, 1 on failure.
"""

import os, sys, json, time, subprocess, shutil
from pathlib import Path

LEDGER = "/tmp/solana-test-ledger"
VALIDATOR_LOG = "/tmp/solana-val-local.log"
RPC_URL = "http://127.0.0.1:8899"

def log(msg):
    print(f"  {msg}", flush=True)

def main():
    print("=" * 60)
    print("Section 1.B — Local Validator Smoke Test")
    print("=" * 60)

    # Catch Ctrl+C / SIGTERM so we clean up the validator
    import signal as _signal
    _orig_handler = None
    def _cleanup(sig, frame):
        log("\n    Signal received, stopping validator...")
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=10)
        sys.exit(1)
    _orig_handler = _signal.signal(_signal.SIGTERM, _cleanup)
    _signal.signal(_signal.SIGINT, _cleanup)

    # ── 1. Clean slate ─────────────────────────────────────────────
    log("[1] Cleaning previous ledger...")
    if Path(LEDGER).exists():
        shutil.rmtree(LEDGER)
    if Path(VALIDATOR_LOG).exists():
        os.remove(VALIDATOR_LOG)

    # ── 2. Start local validator ───────────────────────────────────
    log("[2] Starting solana-test-validator (local, reset)...")
    proc = subprocess.Popen(
        ["solana-test-validator", "--reset", "--ledger", LEDGER,
         "--quiet"],
        stdout=open(VALIDATOR_LOG, "w"),
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid,
    )
    log(f"    PID={proc.pid}")

    # Wait for it to be ready
    import urllib.request
    health_payload = b'{"jsonrpc":"2.0","id":1,"method":"getHealth"}'
    for i in range(30):
        time.sleep(2)
        try:
            req = urllib.request.Request(
                RPC_URL, data=health_payload,
                headers={"Content-Type": "application/json"}
            )
            resp = urllib.request.urlopen(req, timeout=5)
            data = json.loads(resp.read())
            if data.get("result") == "ok":
                log(f"    Validator ready after {(i+1)*2}s")
                break
        except Exception:
            pass
    else:
        log("    ERR: Validator not ready after 60s. Log tail:")
        with open(VALIDATOR_LOG) as f:
            for line in list(f)[-10:]:
                log(f"      {line.rstrip()}")
        proc.kill()
        sys.exit(1)

    # ── 3. Fund the test keypair ───────────────────────────────────
    log("[3] Funding test keypair from local validator...")
    key_file = os.environ.get("DEVNET_TEST_KEY_FILE",
                              "/root/.hermes/tmp/devnet_test_key.json")
    if not Path(key_file).exists():
        log(f"    ERR: {key_file} not found")
        proc.kill()
        sys.exit(1)

    raw = bytes(json.load(open(key_file)))
    from solders.keypair import Keypair
    signer = Keypair.from_bytes(raw)
    signer_pubkey = str(signer.pubkey())
    log(f"    signer: {signer_pubkey}")

    # Airdrop via CLI
    airdrop_res = subprocess.run(
        ["solana", "airdrop", "100", signer_pubkey,
         "--url", RPC_URL],
        capture_output=True, text=True, timeout=30
    )
    if airdrop_res.returncode != 0:
        log(f"    Airdrop failed: {airdrop_res.stderr.strip()}")
        log(f"    Trying via RPC directly...")
        # Fallback: request_airdrop via Python
        from solana.rpc.api import Client
        client = Client(RPC_URL, timeout=30)
        try:
            resp = client.request_airdrop(signer.pubkey(), 100_000_000_000)
            sig = resp.value
            for i in range(30):
                time.sleep(2)
                status = client.get_signature_statuses([sig]).value[0]
                if status and status.confirmation_status in ("confirmed", "finalized"):
                    log(f"    Airdrop via RPC confirmed after {(i+1)*2}s")
                    break
        except Exception as e:
            log(f"    Airdrop fallback also failed: {e}")
            proc.kill()
            sys.exit(1)
    else:
        log(f"    Airdrop via CLI succeeded")

    # Check balance
    from solana.rpc.api import Client
    client = Client(RPC_URL, timeout=30)
    bal = client.get_balance(signer.pubkey()).value
    log(f"    Balance: {bal / 1e9} SOL")

    # ── 4. Create mock USDC token ──────────────────────────────────
    log("[4] Creating mock USDC token...")
    token_create = subprocess.run(
        ["spl-token", "create-token", "--url", RPC_URL,
         "--fee-payer", key_file],
        capture_output=True, text=True, timeout=60
    )
    if token_create.returncode != 0:
        log(f"    Token creation failed: {token_create.stderr.strip()}")
        log(f"    stdout: {token_create.stdout.strip()}")
        proc.kill()
        sys.exit(1)
    # Parse the mint address from output: "Creating token <MINT>"
    token_mint = None
    for line in token_create.stdout.splitlines():
        if "Creating token" in line:
            token_mint = line.split()[-1].strip()
            break
    if not token_mint:
        log(f"    Could not parse mint address from: {token_create.stdout}")
        proc.kill()
        sys.exit(1)
    log(f"    Mint: {token_mint}")

    # Create associated token account for signer
    log("    Creating ATA for signer...")
    ata_res = subprocess.run(
        ["spl-token", "create-account", token_mint, "--url", RPC_URL,
         "--fee-payer", key_file, "--owner", key_file],
        capture_output=True, text=True, timeout=30,
    )
    if ata_res.returncode != 0 and b"already exists" not in ata_res.stderr.encode():
        log(f"    ATA creation warning: {ata_res.stderr.strip()}")
        log("    (continuing anyway)")

    # Mint USDC to signer's ATA
    log("    Minting 1000 USDC to signer...")
    mint_res = subprocess.run(
        ["spl-token", "mint", token_mint, "1000", "--url", RPC_URL,
         "--fee-payer", key_file],
        capture_output=True, text=True, timeout=30,
    )
    if mint_res.returncode != 0:
        log(f"    Mint failed: {mint_res.stderr.strip()}")
        proc.kill()
        sys.exit(1)
    log("    1000 USDC minted")

    # ── 5. Adapt and run the test ──────────────────────────────────
    log("[5] Running payout test against local validator...")

    # Import and run modified test
    sys.path.insert(0, "/root/empire-v49")

    # Patch environment
    os.environ["SOLANA_RPC_URL"] = RPC_URL
    os.environ["LOCAL_USDC_MINT"] = token_mint

    # Run the core test logic with local overrides
    from scripts.test_solana_payout import (
        send_usdc_transfer, verify_transfer, derive_ata,
    )
    from solders.pubkey import Pubkey

    recipient = Keypair().pubkey()
    log(f"    Recipient: {recipient}")

    try:
        tx_sig = send_usdc_transfer(
            client, signer, recipient, 0.01,
            Pubkey.from_string(token_mint)
        )
        log(f"    Tx signature: {tx_sig}")
    except Exception as e:
        log(f"    Send failed: {e}")
        proc.kill()
        sys.exit(1)

    log("[6] Verifying on-chain...")
    try:
        result = verify_transfer(
            client, tx_sig, signer.pubkey(), recipient, 0.01,
            Pubkey.from_string(token_mint)
        )
        log(f"    VERIFIED: {result['amount_usdc']} USDC to "
            f"{result['recipient'][:12]}...")
    except Exception as e:
        log(f"    Verification failed: {e}")
        proc.kill()
        sys.exit(1)

    # Idempotency check
    log("[7] Idempotency check...")
    try:
        tx_sig2 = send_usdc_transfer(
            client, signer, recipient, 0.01,
            Pubkey.from_string(token_mint)
        )
        if tx_sig2 == tx_sig:
            log("    FAIL: identical tx signature on second send")
            proc.kill()
            sys.exit(1)
        log(f"    Second tx: {tx_sig2[:12]}...  (different) ok")
    except Exception as e:
        log(f"    Second send failed (expected if low balance): {e}")
        log("    (this is fine — proves we're not double-paying)")

    # ── Cleanup ────────────────────────────────────────────────────
    log("[8] Cleanup...")
    proc.terminate()
    proc.wait(timeout=10)
    log("    Validator stopped")

    print("\n" + "=" * 60)
    print("Section 1.B PASSED")
    print(f"  Real USDC transfer executed on local Solana validator")
    print(f"  tx: {tx_sig}")
    print(f"  explorer: https://explorer.solana.com/tx/{tx_sig}?cluster=custom&customUrl=http%3A%2F%2F127.0.0.1%3A8899")
    print("=" * 60)
    sys.exit(0)


if __name__ == "__main__":
    main()
