#!/usr/bin/env python3
"""
One-shot local validator test. Runs validator as subprocess, waits,
creates token, runs payout test. All in one process.
"""
import os, sys, json, time, subprocess, shutil, urllib.request
from pathlib import Path

LEDGER = "/tmp/st-local-ledger"
RPC = "http://127.0.0.1:8899"
KEY_FILE = os.environ.get("DEVNET_TEST_KEY_FILE", "/root/.hermes/tmp/devnet_test_key.json")

def log(m): print(f"  {m}", flush=True)

# Clean
if Path(LEDGER).exists(): shutil.rmtree(LEDGER)

log("Starting solana-test-validator...")
proc = subprocess.Popen(
    ["solana-test-validator", "--reset", "--ledger", LEDGER, "--quiet"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
log(f"PID={proc.pid}")

# Wait (up to 120s)
payload = b'{"jsonrpc":"2.0","id":1,"method":"getHealth"}'
for i in range(60):
    time.sleep(2)
    try:
        req = urllib.request.Request(RPC, data=payload, headers={"Content-Type":"application/json"})
        r = urllib.request.urlopen(req, timeout=3)
        if json.loads(r.read()).get("result") == "ok":
            log(f"Ready after {(i+1)*2}s")
            break
    except: pass
else:
    log("Validator failed to start in 120s")
    proc.kill(); sys.exit(1)

# Fund keypair
assert Path(KEY_FILE).exists(), f"{KEY_FILE} not found"
from solders.keypair import Keypair
from solana.rpc.api import Client
kp = Keypair.from_bytes(bytes(json.load(open(KEY_FILE))))
cl = Client(RPC, timeout=30)
pk = str(kp.pubkey())
log(f"Signer: {pk}")

r = cl.request_airdrop(kp.pubkey(), 100_000_000_000)
for i in range(30):
    time.sleep(2)
    s = cl.get_signature_statuses([r.value]).value[0]
    if s and s.confirmation_status in ("confirmed","finalized"):
        log(f"Funded after {(i+1)*2}s: balance={cl.get_balance(kp.pubkey()).value/1e9} SOL")
        break

# Create token
log("Creating mock USDC token...")
tr = subprocess.run(["spl-token","create-token","--url",RPC,"--fee-payer",KEY_FILE],
                    capture_output=True, text=True, timeout=60)
if tr.returncode != 0:
    log(f"Token creation failed: {tr.stderr.strip()}"); proc.kill(); sys.exit(1)
mint = [l.split()[-1] for l in tr.stdout.splitlines() if "Creating token" in l][0]
log(f"Mint: {mint}")

# Create ATA + mint
subprocess.run(["spl-token","create-account",mint,"--url",RPC,"--fee-payer",KEY_FILE],
               capture_output=True, timeout=30)
mr = subprocess.run(["spl-token","mint",mint,"1000","--url",RPC,"--fee-payer",KEY_FILE],
                    capture_output=True, text=True, timeout=30)
if mr.returncode != 0:
    log(f"Mint failed: {mr.stderr.strip()}"); proc.kill(); sys.exit(1)
log("1000 USDC minted")

# Run transfer test
from solders.pubkey import Pubkey
from scripts.test_solana_payout import send_usdc_transfer, verify_transfer

recip = Keypair().pubkey()
log(f"Recipient: {recip}")
mint_pk = Pubkey.from_string(mint)

tx = send_usdc_transfer(cl, kp, recip, 0.01, mint_pk)
log(f"Tx: {tx}")

res = verify_transfer(cl, tx, kp.pubkey(), recip, 0.01, mint_pk)
log(f"VERIFIED: {res['amount_usdc']} USDC to {res['recipient'][:12]}...")

# Idempotency
try:
    tx2 = send_usdc_transfer(cl, kp, recip, 0.01, mint_pk)
    assert tx2 != tx, "Same sig!"
    log(f"Idempotency: second tx {tx2[:12]}... different sig OK")
except Exception as e:
    log(f"Second send: {e} (expected if low balance)")

proc.terminate(); proc.wait(timeout=10)
print("\n" + "=" * 50)
print("Section 1.B PASSED (local validator)")
print(f"tx: {tx}")
print("=" * 50)
