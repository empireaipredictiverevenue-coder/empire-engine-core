#!/bin/bash
# deploy.sh — Empire AI production deploy
#
# Usage:
#   bash deploy.sh                 # standard update (git pull + pip + pm2 restart)
#   bash deploy.sh --hetzner       # full Hetzner bootstrap (first run on a new box)
#   bash deploy.sh --hetzner --nginx   # same, but with Nginx instead of Caddy
#   bash deploy.sh --help          # show this help
#
# Env vars (for --hetzner):
#   BRAIN_HOSTNAME    FQDN to set up TLS for (default: brain.your-domain.com)
#   EMPIRE_REPO_URL   Git URL to clone on first run (required only if $EMPIRE_HOME
#                     doesn't already exist on the box)
#   CERTBOT_EMAIL     Email for Let's Encrypt cert registration (default: ops@localhost)
#   EMPIRE_HOME       Install path (default: /root/empire-v49)
#
# The --hetzner path assumes:
#   - Ubuntu 22.04 LTS
#   - Root or sudo access (we use set -euo pipefail + apt + systemd)
#   - Port 80/443 reachable (Hetzner Cloud firewall in infra/terraform/ opens them)
#   - DNS A record for $BRAIN_HOSTNAME already pointing at this box's public IP
#     (created by infra/terraform/ or manually)
#   - /root/.env already on disk (operator scp'd it from a backup) with the
#     required vars: SYNTHETIC_BRAIN_API_KEY, EMPIRE_PUBLIC_BASE_URL,
#     OLLAMA_MODEL, VONAGE_API_KEY, VONAGE_API_SECRET, etc.

set -euo pipefail

# ── Help text (used by --help + echoed at the top of --hetzner output) ──
print_help() {
    sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
}

# ── Argument parsing ────────────────────────────────────────────────────
HETZNER_MODE=0
USE_NGINX=0
for arg in "$@"; do
    case "$arg" in
        --hetzner)  HETZNER_MODE=1 ;;
        --nginx)    USE_NGINX=1 ;;
        --help|-h)  print_help; exit 0 ;;
        *) echo "[DEPLOY] Unknown argument: $arg" >&2; print_help >&2; exit 1 ;;
    esac
done

# ── Paths + env-var defaults ───────────────────────────────────────────
EMPIRE_HOME="${EMPIRE_HOME:-/root/empire-v49}"
REPO_URL="${EMPIRE_REPO_URL:-}"
BRAIN_HOSTNAME="${BRAIN_HOSTNAME:-brain.your-domain.com}"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-ops@localhost}"

# ════════════════════════════════════════════════════════════════════════
#   HETZNER FIRST-RUN BOOTSTRAP
# ════════════════════════════════════════════════════════════════════════
if [ "$HETZNER_MODE" -eq 1 ]; then
    echo "[DEPLOY:hetzner] starting first-run bootstrap"
    echo "[DEPLOY:hetzner]   hostname:  $BRAIN_HOSTNAME"
    echo "[DEPLOY:hetzner]   proxy:     $([ "$USE_NGINX" -eq 1 ] && echo nginx || echo caddy)"
    echo "[DEPLOY:hetzner]   home:      $EMPIRE_HOME"
    echo ""

    # Fail-closed: /root/.env must already be on disk (operator scp'd it from a backup)
    if [ ! -f /root/.env ]; then
        echo "[DEPLOY:hetzner] FATAL: /root/.env not found" >&2
        echo "[DEPLOY:hetzner]   create it from a backup before re-running. Required vars:" >&2
        echo "    SYNTHETIC_BRAIN_API_KEY, EMPIRE_PUBLIC_BASE_URL, OLLAMA_MODEL, VONAGE_*" >&2
        exit 1
    fi

    # Need root for apt + systemd + writing to /etc/
    if [ "$(id -u)" -ne 0 ]; then
        echo "[DEPLOY:hetzner] FATAL: must be run as root (or via sudo)" >&2
        exit 1
    fi

    # 1. apt update + base packages
    echo "[DEPLOY:hetzner] (1/10) apt update + base packages"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y \
        curl \
        wget \
        git \
        ca-certificates \
        gnupg \
        apt-transport-https \
        python3-pip \
        python3-venv \
        ffmpeg

    # 2. Ollama (LLM for synthetic_brain strategy planner + critic)
    echo "[DEPLOY:hetzner] (2/10) Ollama + model pull"
    if ! command -v ollama >/dev/null 2>&1; then
        curl -fsSL https://ollama.com/install.sh | sh
    fi
    systemctl enable --now ollama
    OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.2:3b}"
    # Idempotent — Ollama skips if already present
    ollama pull "$OLLAMA_MODEL" \
        || echo "[DEPLOY:hetzner] WARN: ollama pull failed (non-fatal; will retry on first run)"

    # 3. PM2 (Node process manager)
    echo "[DEPLOY:hetzner] (3/10) PM2"
    if ! command -v pm2 >/dev/null 2>&1; then
        npm install -g pm2
    fi

    # 4. Clone the repo (or use the existing one)
    echo "[DEPLOY:hetzner] (4/10) git clone/pull"
    if [ ! -d "$EMPIRE_HOME" ]; then
        if [ -z "$REPO_URL" ]; then
            echo "[DEPLOY:hetzner] FATAL: $EMPIRE_HOME doesn't exist and EMPIRE_REPO_URL is not set" >&2
            echo "[DEPLOY:hetzner]   e.g. export EMPIRE_REPO_URL=git@github.com:you/empire-v49.git" >&2
            exit 1
        fi
        echo "[DEPLOY:hetzner] cloning $REPO_URL -> $EMPIRE_HOME"
        git clone "$REPO_URL" "$EMPIRE_HOME"
    fi
    cd "$EMPIRE_HOME"
    git pull origin master 2>/dev/null || echo "[DEPLOY:hetzner] (no remote / already current)"

    # 5. Python deps
    echo "[DEPLOY:hetzner] (5/10) pip install requirements.txt"
    # The --break-system-packages flag is needed for PEP 668 systems (Ubuntu 22.04+).
    # We fall back to a venv-style install if pip refuses.
    pip install -r requirements.txt --break-system-packages 2>/dev/null \
        || pip install -r requirements.txt

    # 6. Log dir (PM2 + uvicorn write here; PM2 rotates)
    echo "[DEPLOY:hetzner] (6/10) /var/log/empire"
    mkdir -p /var/log/empire
    chmod 755 /var/log/empire

    # 7. Make the wrapper scripts executable
    echo "[DEPLOY:hetzner] (7/10) chmod wrapper scripts"
    if [ -d deploy/hetzner ]; then
        chmod +x deploy/hetzner/*.sh
    fi

    # 8. Reverse proxy: Caddy (default) or Nginx
    echo "[DEPLOY:hetzner] (8/10) reverse proxy"
    if [ "$USE_NGINX" -eq 1 ]; then
        echo "[DEPLOY:hetzner]   setting up Nginx + certbot"
        apt-get install -y nginx certbot python3-certbot-nginx
        # Substitute the operator's hostname into the snippet, then install
        sed "s/brain\.your-domain\.com/$BRAIN_HOSTNAME/g" \
            deploy/hetzner/nginx.conf.snippet > /etc/nginx/sites-available/brain
        ln -sf /etc/nginx/sites-available/brain /etc/nginx/sites-enabled/brain
        # Remove the default site (port 80 already taken by our config)
        rm -f /etc/nginx/sites-enabled/default
        nginx -t
        systemctl reload nginx || systemctl restart nginx
        # Certbot provisions Let's Encrypt cert. --non-interactive fails fast
        # if cert can't be issued (usually means DNS doesn't resolve yet).
        certbot --nginx -d "$BRAIN_HOSTNAME" --non-interactive --agree-tos -m "$CERTBOT_EMAIL" \
            || echo "[DEPLOY:hetzner] WARN: certbot failed (DNS not propagated yet? re-run: certbot --nginx -d $BRAIN_HOSTNAME --non-interactive --agree-tos -m $CERTBOT_EMAIL)"
    else
        echo "[DEPLOY:hetzner]   setting up Caddy (auto-TLS)"
        # Caddy needs the official repo for the latest stable
        apt-get install -y debian-keyring debian-archive-keyring
        curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
            | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg 2>/dev/null
        curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
            | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
        apt-get update -y
        apt-get install -y caddy
        # Substitute the operator's hostname into the snippet
        sed "s/brain\.your-domain\.com/$BRAIN_HOSTNAME/g" \
            deploy/hetzner/Caddyfile.snippet > /etc/caddy/Caddyfile
        # Caddy auto-provisions the Let's Encrypt cert on first request
        systemctl reload caddy || systemctl restart caddy
    fi

    # 9. PM2 ecosystem + start the apps
    echo "[DEPLOY:hetzner] (9/10) pm2 start"
    pm2 delete all 2>/dev/null || true   # clear any stale entries
    pm2 start deploy/hetzner/ecosystem.config.js
    pm2 save

    # 10. Boot persistence (operator must run the printed command on first boot)
    echo "[DEPLOY:hetzner] (10/10) pm2 startup"
    pm2 startup \
        || echo "[DEPLOY:hetzner] WARN: pm2 startup failed (you may need to run it manually)"

    echo ""
    echo "[DEPLOY:hetzner] ✓ done. Verify with:"
    echo "    pm2 list"
    echo "    curl -i https://$BRAIN_HOSTNAME/docs"
    echo "    python3 scripts/smoke_voice_streaming.py  (from $EMPIRE_HOME)"
    echo ""
    echo "[DEPLOY:hetzner]   if certbot/Caddy TLS failed above, DNS may not have"
    echo "[DEPLOY:hetzner]   propagated yet. Re-run certbot (Nginx) or just wait"
    echo "[DEPLOY:hetzner]   for Caddy to retry (it polls every ~30s)."
    echo ""
    exit 0
fi

# ════════════════════════════════════════════════════════════════════════
#   STANDARD UPDATE PATH (unchanged from previous deploy.sh)
# ════════════════════════════════════════════════════════════════════════
echo "[DEPLOY] Pulling latest code..."
cd "$EMPIRE_HOME"
git pull origin master 2>/dev/null || echo "[DEPLOY] No git remote / already current"

echo "[DEPLOY] Installing dependencies..."
pip install -r requirements.txt --break-system-packages 2>/dev/null || pip install praw beautifulsoup4 requests supabase python-dotenv httpx --break-system-packages

echo "[DEPLOY] Restarting services..."
pm2 restart empire-hub empire-agents

echo "[DEPLOY] Saving PM2 state..."
pm2 save

echo "[DEPLOY] Done. Status:"
pm2 list
