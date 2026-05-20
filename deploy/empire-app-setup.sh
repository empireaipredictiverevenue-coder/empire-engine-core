#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# EMPIRE V49 · APP SETUP
# ═══════════════════════════════════════════════════════════════════════════
# Creates the Dokku app, configures domain, WebSocket proxy, storage.
# Run AFTER hetzner-bootstrap.sh has completed.
#
# Environment variables (set by the PowerShell wrapper or manually):
#   APP_NAME           default: empire-ai-uk
#   DOMAIN             default: empire-ai.co.uk
#   LETSENCRYPT_EMAIL  required for SSL · default: unset
#   USE_POSTGRES       1 to create a local Postgres add-on (default 0)
#   USE_REDIS          1 to create a Redis add-on (default 1)
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

APP_NAME="${APP_NAME:-empire-ai-uk}"
DOMAIN="${DOMAIN:-empire-ai.co.uk}"
LETSENCRYPT_EMAIL="${LETSENCRYPT_EMAIL:-}"
USE_POSTGRES="${USE_POSTGRES:-0}"
USE_REDIS="${USE_REDIS:-1}"

echo ""
echo "═══════════════════════════════════════════════════════════════════════"
echo "  EMPIRE V49 · APP SETUP · $APP_NAME · $DOMAIN"
echo "═══════════════════════════════════════════════════════════════════════"
echo ""

if [ "$EUID" -ne 0 ]; then
    echo "✗ Must run as root"
    exit 1
fi

if ! command -v dokku &> /dev/null; then
    echo "✗ Dokku not installed · run hetzner-bootstrap.sh first"
    exit 1
fi

# ─────────────────────────────────────────────────────────────────────
# 1. Create the app
# ─────────────────────────────────────────────────────────────────────
echo "▸ Creating Dokku app $APP_NAME..."
if dokku apps:exists "$APP_NAME" 2>/dev/null; then
    echo "  ✓ App already exists"
else
    dokku apps:create "$APP_NAME"
    echo "  ✓ App created"
fi

# ─────────────────────────────────────────────────────────────────────
# 2. Set domains
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "▸ Configuring domains..."

current_domains=$(dokku domains:report "$APP_NAME" --domains-app-vhosts 2>/dev/null || echo "")
if [[ "$current_domains" != *"$DOMAIN"* ]]; then
    dokku domains:add "$APP_NAME" "$DOMAIN"
    echo "  ✓ Added domain: $DOMAIN"
fi

if [[ "$current_domains" != *"www.$DOMAIN"* ]]; then
    dokku domains:add "$APP_NAME" "www.$DOMAIN"
    echo "  ✓ Added domain: www.$DOMAIN"
fi

# Remove the default app domain
DEFAULT_DOMAIN=$(hostname -f 2>/dev/null || true)
if [[ "$current_domains" == *"$APP_NAME.$DEFAULT_DOMAIN"* ]]; then
    dokku domains:remove "$APP_NAME" "$APP_NAME.$DEFAULT_DOMAIN" 2>/dev/null || true
fi

# ─────────────────────────────────────────────────────────────────────
# 3. WebSocket-friendly proxy timeouts
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "▸ Configuring nginx for WebSockets..."

dokku nginx:set "$APP_NAME" proxy-read-timeout 3600s
dokku nginx:set "$APP_NAME" proxy-send-timeout 3600s
dokku nginx:set "$APP_NAME" client-max-body-size 32m
echo "  ✓ Timeouts set to 1 hour, body size 32MB"

# ─────────────────────────────────────────────────────────────────────
# 4. Create storage directory for persistent files
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "▸ Creating storage directory..."

STORAGE_DIR="/var/lib/dokku/data/storage/$APP_NAME"
mkdir -p "$STORAGE_DIR"
chown -R dokku:dokku "$STORAGE_DIR" 2>/dev/null || chown -R 32767:32767 "$STORAGE_DIR" 2>/dev/null || true
echo "  ✓ Storage at $STORAGE_DIR"

# ─────────────────────────────────────────────────────────────────────
# 5. Optional: Postgres add-on
# ─────────────────────────────────────────────────────────────────────
if [ "$USE_POSTGRES" = "1" ]; then
    echo ""
    echo "▸ Creating Postgres service..."
    PG_NAME="${APP_NAME}-db"
    if dokku postgres:exists "$PG_NAME" 2>/dev/null; then
        echo "  ✓ Postgres $PG_NAME already exists"
    else
        dokku postgres:create "$PG_NAME"
        echo "  ✓ Postgres $PG_NAME created"
    fi

    if ! dokku postgres:linked "$PG_NAME" "$APP_NAME" &>/dev/null; then
        dokku postgres:link "$PG_NAME" "$APP_NAME"
        echo "  ✓ Postgres linked to $APP_NAME"
    fi
fi

# ─────────────────────────────────────────────────────────────────────
# 6. Optional: Redis add-on (for caching)
# ─────────────────────────────────────────────────────────────────────
if [ "$USE_REDIS" = "1" ]; then
    echo ""
    echo "▸ Creating Redis service..."
    REDIS_NAME="${APP_NAME}-cache"
    if dokku redis:exists "$REDIS_NAME" 2>/dev/null; then
        echo "  ✓ Redis $REDIS_NAME already exists"
    else
        dokku redis:create "$REDIS_NAME"
        echo "  ✓ Redis $REDIS_NAME created"
    fi

    if ! dokku redis:linked "$REDIS_NAME" "$APP_NAME" &>/dev/null; then
        dokku redis:link "$REDIS_NAME" "$APP_NAME"
        echo "  ✓ Redis linked to $APP_NAME"
    fi
fi

# ─────────────────────────────────────────────────────────────────────
# 7. Resource limits (prevent runaway costs)
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "▸ Setting resource limits..."

dokku resource:limit --memory 1024m --cpu 100 "$APP_NAME" 2>/dev/null || \
    echo "  ⚠ resource plugin not available (optional · skip)"

dokku ps:scale "$APP_NAME" web=1 2>/dev/null || echo "  ⚠ scale will apply after first deploy"

# ─────────────────────────────────────────────────────────────────────
# 8. Set Let's Encrypt email if provided
# ─────────────────────────────────────────────────────────────────────
echo ""
if [ -n "$LETSENCRYPT_EMAIL" ]; then
    echo "▸ Setting Let's Encrypt email for $APP_NAME..."
    dokku letsencrypt:set "$APP_NAME" email "$LETSENCRYPT_EMAIL"
    echo "  ✓ Email: $LETSENCRYPT_EMAIL"
    echo "  ↳ SSL will be enabled after first deploy completes"
else
    echo "▸ No LETSENCRYPT_EMAIL provided · SSL must be enabled manually after deploy"
fi

# ─────────────────────────────────────────────────────────────────────
# 9. Health check setup
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "▸ Configuring health checks..."

dokku checks:set "$APP_NAME" wait-to-retire 30
dokku checks:set "$APP_NAME" web /api/market-pulse 200 2>/dev/null || true
echo "  ✓ Health check on /api/market-pulse"

# ─────────────────────────────────────────────────────────────────────
# 10. Done
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════════════"
echo "  ✓ APP SETUP COMPLETE"
echo "═══════════════════════════════════════════════════════════════════════"
echo ""
echo "  App name      : $APP_NAME"
echo "  Domains       : $DOMAIN, www.$DOMAIN"
echo "  Storage       : $STORAGE_DIR"
echo "  WebSockets    : proxy timeouts = 1h"
if [ "$USE_POSTGRES" = "1" ]; then
    echo "  Postgres      : ${APP_NAME}-db (linked)"
fi
if [ "$USE_REDIS" = "1" ]; then
    echo "  Redis         : ${APP_NAME}-cache (linked)"
fi
echo ""
echo "  Next steps:"
echo "    1. dokku config:set $APP_NAME KEY=VALUE  (set your env vars)"
echo "    2. From your dev machine: git push dokku main"
echo "    3. dokku letsencrypt:enable $APP_NAME  (after DNS points here)"
echo ""
