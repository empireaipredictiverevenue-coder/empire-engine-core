# Production deploy: Empire AI on Hetzner

Deploys the synthetic_brain server (Kokoro TTS + WebSocket stream) and
the voice_streaming_agent on a Hetzner Cloud box, fronted by Caddy or
Nginx for TLS. Vonage reaches the brain through the public hostname
defined in `EMPIRE_PUBLIC_BASE_URL`.

## Architecture

```
Internet
   |
   v
Hetzner public IP (e.g. 138.68.x.x)
   |
   v
Caddy / Nginx (TLS + reverse proxy)  -- listens on :443
   |
   v
127.0.0.1:8005  uvicorn synthetic_brain:app  (loopback only)
                 + voice_streaming_agent bot
                 + Ollama (llama3.2:3b) on 127.0.0.1:11434
```

The synthetic_brain is **never** exposed directly to the internet — only
through the reverse proxy. The reverse proxy is the only thing listening
on public ports.

## What runs where

| Service | Bind | Port | Process manager |
|---|---|---|---|
| Caddy / Nginx (TLS + proxy) | 0.0.0.0 | 80, 443 | systemd |
| synthetic_brain (uvicorn) | 127.0.0.1 | 8005 | PM2 (`synthetic_brain`) |
| voice_streaming_agent (bot) | n/a | n/a | PM2 (`voice_streaming_agent`) |
| Ollama | 127.0.0.1 | 11434 | systemd (`ollama.service`) |

## 1. Provision the Hetzner Cloud box

- **CX22** (4 GB RAM, 2 vCPU) or larger — Kokoro + Ollama want ~3 GB
- **Ubuntu 22.04 LTS**, x86_64
- **Public IPv4** enabled
- **Cloud firewall** (Hetzner dashboard): allow TCP 22 (SSH), 80, 443. Drop everything else inbound.

## 2. Install the runtime

```bash
# Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:3b
systemctl enable --now ollama

# Python + ffmpeg
apt install -y python3-pip python3-venv ffmpeg git
pip install -r /root/empire-v49/requirements.txt  # or use a venv

# PM2 (Node process manager)
npm install -g pm2

# Code
git clone <your-repo-url> /root/empire-v49
cd /root/empire-v49
chmod +x deploy/hetzner/*.sh
mkdir -p /var/log/empire
```

## 3. Configure env

Add to `/root/.env`:

```bash
# Synthetic brain auth + LLM
SYNTHETIC_BRAIN_API_KEY=<long-random-string>   # openssl rand -hex 32
OLLAMA_MODEL=llama3.2:3b

# Public base URL (this is what Vonage sees in the wss:// URL)
EMPIRE_PUBLIC_BASE_URL=https://brain.your-domain.com

# Vonage (already set in dev)
VONAGE_API_KEY=...
VONAGE_API_SECRET=...
VONAGE_APPLICATION_ID=...
VONAGE_NUMBER=+1...
VONAGE_PRIVATE_KEY_PATH=/root/empire-v49/private.key

# Optional: warm-forward operator (when connect times out, the TTS stream plays)
EMPIRE_OPERATOR_NUMBER=+1...

# Voice streaming agent tunables
STREAM_CONFIDENCE_THRESHOLD=0.7
VOICE_STREAMING_INTERVAL_HOURS=0.5
```

## 4. Set up the reverse proxy

### Option A: Caddy (recommended — auto-TLS)

Drop the contents of `deploy/hetzner/Caddyfile.snippet` into your
`/etc/caddy/Caddyfile` (rename `brain.your-domain.com` to your actual
hostname). Caddy auto-provisions the Let's Encrypt cert.

```bash
sudo systemctl reload caddy
```

### Option B: Nginx

```bash
# Drop the snippet into a real site config
sudo cp deploy/hetzner/nginx.conf.snippet /etc/nginx/sites-available/brain
sudo ln -s /etc/nginx/sites-available/brain /etc/nginx/sites-enabled/brain
# Provision the cert with certbot (auto-edits the config for the ssl_certificate lines)
sudo certbot --nginx -d brain.your-domain.com
sudo systemctl reload nginx
```

In both cases, point a DNS A-record (and AAAA if you want IPv6) for
`brain.your-domain.com` at the Hetzner box's public IP **before** the
TLS provisioning step.

## 5. Start the brain + agent under PM2

```bash
cd /root/empire-v49
# The ecosystem file in deploy/hetzner/ launches the wrapper scripts which
# load /root/.env, verify the env, then exec uvicorn / python.
cp deploy/hetzner/ecosystem.config.js ecosystem.config.prod.js
pm2 start ecosystem.config.prod.js
pm2 save
pm2 startup   # follow the printed command for boot persistence
```

Expected PM2 output:

```
┌────┬──────────────────────────┬─────────┬──────┬───────────┐
│ id │ name                     │ mode    │ ↺    │ status    │
├────┼──────────────────────────┼─────────┼──────┼───────────┤
│ 0  │ synthetic_brain          │ fork    │ 0    │ online    │
│ 1  │ voice_streaming_agent    │ fork    │ 0    │ online    │
└────┴──────────────────────────┴─────────┴──────┴───────────┘
```

## 6. Verify end-to-end

```bash
# (a) Public hostname reaches the FastAPI docs
curl https://brain.your-domain.com/docs
# Expect: HTML page (FastAPI Swagger UI)

# (b) The /api/v1/synthetic/stream WebSocket is reachable through the proxy.
#     Expect a 4001 close with reason "unknown or expired voice_id" — this
#     means the WebSocket upgrade succeeded (the cert is valid, the proxy
#     forwards WS frames, the worker accepts the connection).
curl -i -N \
  -H "Connection: Upgrade" -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  -H "Sec-WebSocket-Version: 13" \
  "https://brain.your-domain.com/api/v1/synthetic/stream?voice_id=invalid&sig=invalid"
# Expect: HTTP/1.1 101 Switching Protocols (upgrade OK) then close 4001

# (c) The /register_stream endpoint returns a wss:// URL with your hostname
python3 -c "
import os, sys; sys.path.insert(0, '/root/empire-v49')
from synthetic_brain import _register_stream
rec = _register_stream('test', 'am_michael', public_base_url=os.environ['EMPIRE_PUBLIC_BASE_URL'])
print(rec['ws_url'])
assert rec['ws_url'].startswith('wss://brain.your-domain.com/'), rec['ws_url']
print('OK: wss:// URL uses public hostname')
"

# (d) Full E2E: register + WebSocket round-trip with L16 audio
python3 scripts/smoke_voice_streaming.py
# Expect: 111 KB of L16 16kHz mono PCM streamed in ~2 s, stop event received.
```

The smoke test in step (d) should also be wired into the agent_registry's
health checks — if `voice_streaming_agent` stops heartbeating, the AGI
governor's staleness gate flips to HOLD.

## Updating

```bash
cd /root/empire-v49
git pull
pip install -r requirements.txt
pm2 restart ecosystem.config.prod.js
pm2 save
```

## Monitoring

```bash
pm2 logs synthetic_brain voice_streaming_agent   # live tail
pm2 monit                                       # resource usage
pm2 status                                      # health overview
```

External: the agent's heartbeat row in `agent_registry` confirms liveness;
the AGI governor's `/api/v1/governor/health` endpoint reports staleness;
the `model_benchmark` table (from migrations/003) tracks per-night LLM
quality and auto-switches models if success rate drops below 70% for
3 consecutive nights.

## Backups

- `/root/.env` — back up off-box (it has all your secrets)
- `private.key` — Vonage app private key
- Supabase — already cloud-managed, point-in-time recovery enabled

## Disaster recovery

If the Hetzner box dies, the rebuild is:

1. Provision new CX22, configure cloud firewall
2. `git clone` + `pip install -r requirements.txt` + `npm install -g pm2`
3. Restore `/root/.env` from backup
4. Pull `private.key` from backup
5. Update DNS A-record for `brain.your-domain.com` to the new IP
6. `pm2 start ecosystem.config.prod.js && pm2 save && pm2 startup`

The orchestrator's agents + the synthetic_brain are stateless, so a
cold start takes ~3 minutes (Ollama warmup is the bottleneck).
