# Empire AI · Key Rotation Runbook

## Status
The `private.key` file used for Vonage voice signing was committed to the
repository history or exposed in logs. This runbook documents the rotation
procedure and establishes a recurring 30-day rotation policy.

## Scope
| Key | Used By | Rotation Impact |
|-----|---------|----------------|
| `private.key` | Vonage (outbound dialer, voice streaming) | Requires Vonage app re-auth |
| `SOLANA_SIGNING_KEY` | empire_payouts.py (USDC transfers) | Requires new wallet generation |
| `SOLANA_RPC_URL` | empire_payouts.py, Solana watcher | No rotation needed (URL only) |
| `EMPIRE_VAULT_WALLET` | empire_payouts.py (vault address) | Must match signing key |
| `HUB_TOKEN` | WebSocket authentication | Rotate and restart hub |
| `SECRET_KEY` | empire_tokens.py (session signing) | Rotate and restart hub |
| `SUPABASE_SERVICE_KEY` | All DB access | Rotate via Supabase dashboard |

---

## Emergency Rotation (Leaked Key)

### 1. Vonage Private Key

```bash
# 1. Generate a new RSA keypair
openssl genrsa -out private_new.key 2048

# 2. Create the new Vonage application
#    Go to https://dashboard.nexmo.com/applications
#    → Create New Application
#    → Upload public key from: openssl rsa -in private_new.key -pubout
#    → Enable Voice capability
#    → Copy the new Application ID

# 3. Update environment
dokku config:set empire-ai-uk \
  VONAGE_APPLICATION_ID="<new-app-id>" \
  VONAGE_PRIVATE_KEY_PATH="/root/empire-v49/private.key"

# 4. Replace the key file
cp private_new.key /root/empire-v49/private.key
chmod 600 /root/empire-v49/private.key

# 5. Verify outbound calling still works
python3 -c "
from empire_outbound_dialer import OutboundDialer
d = OutboundDialer()
print('Dialer initialized OK')
"

# 6. Restart hub
dokku ps:restart empire-ai-uk

# 7. Delete old key from Vonage dashboard
#    → Your Applications → Old App → Delete
```

### 2. Solana Signing Key

```bash
# 1. Generate a new Solana keypair (devnet first)
pip install solders==0.21.0
python3 -c "
from solders.keypair import Keypair
kp = Keypair()
print(f'Public:  {kp.pubkey()}')
print(f'Private: {kp.secret().hex()}')
"

# 2. Fund the new wallet on devnet
solana airdrop 1 <NEW_PUBKEY> --url devnet

# 3. Update environment
dokku config:set empire-ai-uk \
  SOLANA_SIGNING_KEY="<base58-encoded-secret>" \
  EMPIRE_VAULT_WALLET="<new-pubkey>" \
  EMPIRE_SOLANA_NETWORK=devnet

# 4. Test a $0.01 USDC transfer
python3 -c "
import asyncio
from empire_payouts import PayoutEngine
# Dry-run: engine will attempt signing against devnet
# See docs/PAYOUTS_SIGNING.md for full test procedure
"

# 5. Once confirmed on devnet, switch to mainnet
dokku config:set empire-ai-uk EMPIRE_SOLANA_NETWORK=mainnet-beta

# 6. Transfer remaining funds from old wallet to new wallet
#    Use Phantom/Solflare CLI or any Solana wallet
```

### 3. Supabase Service Key

```bash
# 1. Go to https://supabase.com/dashboard/project/<ref>/settings/api
# 2. Click "Revoke" on the current service_role key
# 3. Copy the new service_role key
# 4. Update all deployments
dokku config:set empire-ai-uk SUPABASE_SERVICE_KEY="<new-key>"

# 5. Restart all services
dokku ps:restart empire-ai-uk
```

---

## 30-Day Rotation Policy

### Automated Reminder
A cron job or GitHub Actions scheduled workflow runs monthly:

```yaml
# .github/workflows/key-rotation-reminder.yml
name: Key Rotation Reminder
on:
  schedule:
    - cron: "0 9 1 * *"  # 1st of each month at 09:00 UTC
jobs:
  remind:
    runs-on: ubuntu-latest
    steps:
      - name: Post reminder
        run: |
          echo "🔐 Monthly key rotation due — see docs/KEY_ROTATION.md"
```

### Rotation Checklist
- [ ] Rotate `private.key` (Vonage) — generate new RSA keypair, update dashboard
- [ ] Rotate `SOLANA_SIGNING_KEY` — generate new keypair, transfer funds
- [ ] Rotate `SUPABASE_SERVICE_KEY` — revoke/regenerate in dashboard
- [ ] Rotate `HUB_TOKEN` — generate new random string
- [ ] Rotate `SECRET_KEY` — generate new random string
- [ ] Update `.env.example` if any defaults changed
- [ ] Verify all services restart cleanly
- [ ] Run `pytest tests/` to confirm no regressions

### Key Storage
- **NEVER** store private keys in git
- Use `dokku config:set` for production secrets
- Use `.env` (gitignored) for local development
- Backup keys to a secure password manager (1Password, Bitwarden)

---

## Recovery
If a key is lost (not leaked):

| Key | Recovery |
|-----|----------|
| Vonage private.key | Generate new keypair, register new Vonage app |
| Solana signing key | **IRRECOVERABLE** — funds in old wallet are lost unless you have the mnemonic/seed phrase |
| Supabase service key | Regenerate via dashboard — no data loss |
| HUB_TOKEN | Generate new — existing WS connections drop, clients reconnect |

---

## Verification
After any key rotation, run:

```bash
# Vonage
python3 -c "from empire_outbound_dialer import OutboundDialer; print('OK')"

# Solana (devnet)
python3 -c "
from solders.keypair import Keypair
import base58, os
key = base58.b58decode(os.environ['SOLANA_SIGNING_KEY'])
kp = Keypair.from_bytes(key)
print(f'Wallet: {kp.pubkey()}')
"

# Supabase
python3 -c "
from supabase import create_client
import os
sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY'])
print(sb.table('operators').select('count').execute())
"

# Full test suite
pytest tests/ -v --tb=short
```

## Sign-off
- [ ] Operator reviewed this document
- [ ] Emergency rotation performed within 24h of leak detection
- [ ] 30-day rotation schedule configured
- [ ] All production keys stored in dokku config (not git)
