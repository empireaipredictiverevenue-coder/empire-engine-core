#!/usr/bin/env bash
# ============================================================================
# Empire AI · CRM Deployment Script
# ============================================================================
# One-shot script to deploy and configure both CRM tools:
#   1. ListMonk — Email campaigns (port 9000)
#   2. Twenty CRM — Pipeline management (port 3003)
#
# Idempotent: safe to re-run. Skips already-deployed services.
#
# Usage:
#   ./scripts/deploy_crms.sh                  # full deploy
#   ./scripts/deploy_crms.sh --dry-run         # preview only
#   ./scripts/deploy_crms.sh --listmonk-only   # deploy only ListMonk
#   ./scripts/deploy_crms.sh --twenty-only     # deploy only Twenty
#   ./scripts/deploy_crms.sh --import-only     # import contractors into ListMonk
#   ./scripts/deploy_crms.sh --fix-config      # regenerate config.toml + restart ListMonk
#
# Prerequisites:
#   - Docker + docker-compose-plugin installed
#   - /root/.env with SUPABASE_URL, SUPABASE_SERVICE_KEY, RESEND_API_KEY,
#     VONAGE_API_KEY, VONAGE_API_SECRET, VONAGE_NUMBER
# ============================================================================

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Colors ──────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*"; }
info() { echo -e "${CYAN}[i]${NC} $*"; }

# ── Parse args ──────────────────────────────────────────────────────────
DRY_RUN=false
DEPLOY_LISTMONK=true
DEPLOY_TWENTY=true
IMPORT_ONLY=false
FIX_CONFIG=false

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --listmonk-only) DEPLOY_TWENTY=false ;;
    --twenty-only) DEPLOY_LISTMONK=false ;;
    --import-only) IMPORT_ONLY=true; DEPLOY_LISTMONK=false; DEPLOY_TWENTY=false ;;
    --fix-config) FIX_CONFIG=true ;;
    *) err "Unknown arg: $arg"; exit 1 ;;
  esac
done

# ── Prerequisite check ────────────────────────────────────────────────
PREREQS=("python3" "openssl" "curl" "docker")
for cmd in "${PREREQS[@]}"; do
  if ! command -v "$cmd" &>/dev/null; then
    err "Required command not found: $cmd"
    exit 1
  fi
done
# docker compose plugin (v2) is a separate binary from the docker CLI
if ! docker compose version &>/dev/null; then
  err "docker compose plugin (v2) required — install with: apt install docker-compose-v2"
  exit 1
fi
log "All prerequisites available: ${PREREQS[*]}"

# ── Load env ────────────────────────────────────────────────────────────
if [ -f /root/.env ]; then
  set -a; source /root/.env; set +a
else
  err "/root/.env not found — CRM services require API keys"
  exit 1
fi

LISTMONK_ADMIN_PASS="${LISTMONK_ADMIN_PASS:-$(openssl rand -base64 16 | tr -d '+/' | cut -c1-16)}"
LISTMONK_API_TOKEN="${LISTMONK_API_TOKEN:-lm_api_token_2026}"

# ════════════════════════════════════════════════════════════════════════
#  PHASE 1: LISTMONK
# ════════════════════════════════════════════════════════════════════════

deploy_listmonk() {
  echo -e "\n${CYAN}═══════════════════════════════════════════════════════════${NC}"
  echo -e "${CYAN}  PHASE 1: ListMonk (Email Campaigns) → :9000${NC}"
  echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}\n"

  # ── 1. Create Docker network ───────────────────────────────────────
  if ! docker network ls --format '{{.Name}}' | grep -q '^listmonk-net$'; then
    if $DRY_RUN; then
      info "[DRY-RUN] Would create Docker network: listmonk-net"
    else
      docker network create listmonk-net 2>/dev/null
      log "Created Docker network: listmonk-net"
    fi
  else
    log "Docker network listmonk-net already exists"
  fi

  # ── 2. Start PostgreSQL ────────────────────────────────────────────
  if ! docker ps --format '{{.Names}}' | grep -q '^listmonk-db$'; then
    if $DRY_RUN; then
      info "[DRY-RUN] Would start PostgreSQL container: listmonk-db"
    else
      docker run -d --name listmonk-db \
        --network listmonk-net \
        -e POSTGRES_USER=listmonk \
        -e POSTGRES_PASSWORD=listmonk \
        -e POSTGRES_DB=listmonk \
        -v listmonk-data:/var/lib/postgresql/data \
        postgres:16-alpine 2>/dev/null
      log "Started PostgreSQL: listmonk-db"
      sleep 5  # wait for PG to be ready
    fi
  else
    log "PostgreSQL container listmonk-db already running"
  fi

  # ── 3. Always write config.toml (regenerated every run) ─────────
  #    This ensures the SMTP password stays in sync with the current
  #    RESEND_API_KEY from /root/.env even after container redeploy.
  mkdir -p /tmp/listmonk-config
  if $DRY_RUN; then
    info "[DRY-RUN] Would write config.toml to /tmp/listmonk-config/config.toml"
  else
    # Write config with placeholder, then replace the password via sed
    cat > /tmp/listmonk-config/config.toml << 'TOML'
[app]
address = "0.0.0.0:9000"

[db]
host = "listmonk-db"
port = 5432
user = "listmonk"
password = "listmonk"
database = "listmonk"
ssl_mode = "disable"
max_open = 25
max_idle = 25
max_lifetime = "300s"
params = ""

[smtp]
host = "smtp.resend.com"
port = 587
auth_protocol = "login"
username = "resend"
password = "__SMTP_PASSWORD__"
from_email = "ops@empire-ai.co.uk"
TOML
    # Replace placeholder with actual password (escaping special chars for sed)
    ESCAPED_PASS=$(echo "${RESEND_API_KEY}" | sed 's/[&/\]/\\&/g')
    sed -i "s/__SMTP_PASSWORD__/${ESCAPED_PASS}/g" /tmp/listmonk-config/config.toml
    log "Written config.toml with current SMTP settings"
  fi

  # ── 4. Determine if DB needs first-time install ──────────────
  #    The --install --yes flag WIPES all data and recreates tables.
  #    It must ONLY run once on first deploy. Every restart should
  #    use plain ./listmonk to preserve data and custom SMTP settings.
  DB_NEEDS_INSTALL=false
  if docker ps -a --format '{{.Names}}' | grep -q '^listmonk-db$'; then
    # Check if campaigns table exists (sign of prior install)
    DB_HAS_TABLES=$(docker exec -i listmonk-db psql -U listmonk -d listmonk -c \
      "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name='campaigns');" 2>/dev/null | grep -c 't' || echo "0")
    if [ "$DB_HAS_TABLES" != "1" ]; then
      DB_NEEDS_INSTALL=true
    fi
  else
    # No DB container yet — will need install after DB starts
    DB_NEEDS_INSTALL=true
  fi

  # ── 5. Remove old container and recreate ───────────────────────────
  if docker ps -a --format '{{.Names}}' | grep -q '^listmonk-q$'; then
    if $DRY_RUN; then
      info "[DRY-RUN] Would remove listmonk-q and recreate with fresh config"
    else
      docker rm -f listmonk-q 2>/dev/null
      log "Removed old listmonk-q container"
    fi
  fi

  if $DRY_RUN; then
    if $DB_NEEDS_INSTALL; then
      info "[DRY-RUN] Would start ListMonk with --install --yes (first-time DB setup)"
    else
      info "[DRY-RUN] Would start ListMonk without --install (DB already initialized)"
    fi
  else
    if $DB_NEEDS_INSTALL; then
      docker run -d --name listmonk-q \
        -p 9000:9000 \
        -v /tmp/listmonk-config/config.toml:/listmonk/config.toml:ro \
        -e LISTMONK_ADMIN_USER="admin" \
        -e LISTMONK_ADMIN_PASSWORD="${LISTMONK_ADMIN_PASS}" \
        --network listmonk-net \
        listmonk/listmonk:latest sh -c './listmonk --install --yes && ./listmonk' 2>/dev/null
      log "Started ListMonk with --install --yes (first-time DB setup)"
      sleep 5  # wait for install to complete
    else
      docker run -d --name listmonk-q \
        -p 9000:9000 \
        -v /tmp/listmonk-config/config.toml:/listmonk/config.toml:ro \
        -e LISTMONK_ADMIN_USER="admin" \
        -e LISTMONK_ADMIN_PASSWORD="${LISTMONK_ADMIN_PASS}" \
        --network listmonk-net \
        listmonk/listmonk:latest ./listmonk 2>/dev/null
      log "Started ListMonk without --install (preserving DB data + SMTP settings)"
    fi
  fi

  # ── 6. Override DB SMTP settings to use Resend ───────────────────
  #    The --install command creates a default SMTP setting pointing at
  #    smtp.yoursite.com:25. We override it here to use Resend so that
  #    the DB settings match the config.toml (fixing the init message).
  if ! $DRY_RUN; then
    # Wait for the config to be loaded and the settings table to exist
    sleep 3
    docker exec -i listmonk-db psql -U listmonk -d listmonk -c "
      -- Match config.toml keys: user/pass/auth_type (not username/password/auth_protocol)
      UPDATE settings SET value = jsonb_build_array(jsonb_build_object(
        'enabled', true,
        'host', 'smtp.resend.com',
        'port', 465,
        'auth_type', 'login',
        'user', 'resend',
        'pass', '${RESEND_API_KEY}',
        'from_email', 'ops@empire-ai.co.uk',
        'max_conns', 10,
        'ssl_skip_verify', false
      )) WHERE key = 'smtp';
    " 2>/dev/null && log "Updated DB SMTP setting to use Resend (port 465, implicit TLS)" || warn "Could not update DB SMTP setting (may need restart)"
  fi

  # ── 7. Wait for health ─────────────────────────────────────────────
  if ! $DRY_RUN; then
    info "Waiting for ListMonk to be ready..."
    for i in $(seq 1 12); do
      if curl -s -o /dev/null -w '%{http_code}' http://localhost:9000/ 2>/dev/null | grep -q '200'; then
        log "ListMonk ready on http://localhost:9000"
        break
      fi
      sleep 5
    done

    # Check if admin was created
    ADMIN_EXISTS=$(docker exec -t listmonk-db psql -U listmonk -d listmonk -c \
      "SELECT id FROM users WHERE username = 'admin';" 2>/dev/null | grep -E '^[0-9]' | head -1)
    if [ -z "$ADMIN_EXISTS" ]; then
      # Re-run install
      docker exec -t listmonk-q ./listmonk --install --yes 2>/dev/null
      log "Admin user created via --install"
    fi

    # Create API user via SQL
    API_EXISTS=$(docker exec -t listmonk-db psql -U listmonk -d listmonk -c \
      "SELECT id FROM users WHERE username = 'api_token';" 2>/dev/null | grep -E '^[0-9]' | head -1)
    if [ -z "$API_EXISTS" ]; then
      # Generate bcrypt hash matching ListMonk's format ($2a$06$)
      HASH=$(python3 -c "
import bcrypt
h = bcrypt.hashpw(b'${LISTMONK_API_TOKEN}', bcrypt.gensalt(rounds=6, prefix=b'2a'))
print(h.decode())
" 2>/dev/null)
      docker exec -t listmonk-db psql -U listmonk -d listmonk -c "
        INSERT INTO users (username, password, email, name, type, status, user_role_id, created_at, updated_at)
        VALUES ('api_token', '${HASH}', 'api@empire-ai.co.uk', 'API Token', 'api', 'enabled', 1, NOW(), NOW())
        ON CONFLICT (username) DO NOTHING;
      " 2>/dev/null
      log "API user created: api_token"
    else
      log "API user api_token already exists"
    fi
  fi

  echo -e "\n${GREEN}  ✅ ListMonk: http://localhost:9000/admin${NC}"
  echo -e "     Username: admin"
  echo -e "     Password: ${LISTMONK_ADMIN_PASS}"
  echo -e "     API:      api_token / ${LISTMONK_API_TOKEN}"
}

# ════════════════════════════════════════════════════════════════════════
#  PHASE 2: TWENTY CRM
# ════════════════════════════════════════════════════════════════════════

deploy_twenty() {
  echo -e "\n${CYAN}═══════════════════════════════════════════════════════════${NC}"
  echo -e "${CYAN}  PHASE 2: Twenty CRM (Pipeline Management) → :3003${NC}"
  echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}\n"

  DEPLOY_DIR="/root/deploy/twenty-crm"
  mkdir -p "$DEPLOY_DIR"

  # ── 1. Write docker-compose.yml ────────────────────────────────────
  if $DRY_RUN; then
    info "[DRY-RUN] Would write docker-compose.yml to ${DEPLOY_DIR}/"
  else
    cat > "${DEPLOY_DIR}/docker-compose.yml" << 'COMPOSE'
name: twenty

services:
  server:
    image: twentycrm/twenty:latest
    ports:
      - "3003:3000"
    environment:
      SERVER_URL: http://localhost:3003
      ENCRYPTION_KEY: ${ENCRYPTION_KEY}
      PG_DATABASE_HOST: db
      PG_DATABASE_PORT: 5432
      PG_DATABASE_NAME: default
      PG_DATABASE_USER: postgres
      PG_DATABASE_PASSWORD: ${PG_DATABASE_PASSWORD}
      STORAGE_TYPE: local
      ACCESS_TOKEN_EXPIRES_IN: "3600000"
      LOGIN_TOKEN_EXPIRES_IN: "900000"
      REFRESH_TOKEN_EXPIRES_IN: "86400000"
      REDIS_URL: redis://redis:6379
      MESSAGE_QUEUE_TYPE: sync
    volumes:
      - server-local-data:/app/local-storage
    healthcheck:
      test: ["CMD-SHELL", "curl --fail http://localhost:3000/healthz || exit 1"]
      interval: 10s
      timeout: 10s
      retries: 180
      start_period: 300s
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped

  worker:
    image: twentycrm/twenty:latest
    command: ["yarn", "worker:prod"]
    environment:
      SERVER_URL: http://localhost:3003
      ENCRYPTION_KEY: ${ENCRYPTION_KEY}
      PG_DATABASE_HOST: db
      PG_DATABASE_PORT: 5432
      PG_DATABASE_NAME: default
      PG_DATABASE_USER: postgres
      PG_DATABASE_PASSWORD: ${PG_DATABASE_PASSWORD}
      STORAGE_TYPE: local
      REDIS_URL: redis://redis:6379
      MESSAGE_QUEUE_TYPE: sync
    depends_on:
      server:
        condition: service_healthy
    restart: unless-stopped

  db:
    image: postgres:16
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${PG_DATABASE_PASSWORD}
      POSTGRES_DB: default
    volumes:
      - db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 10
    restart: unless-stopped

  redis:
    image: redis
    command: redis-server --save "" --appendonly no --maxmemory-policy noeviction
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 10
    restart: unless-stopped

volumes:
  db-data:
  server-local-data:
COMPOSE
    log "Written docker-compose.yml"
  fi

  # ── 2. Generate .env ───────────────────────────────────────────────
  if $DRY_RUN; then
    info "[DRY-RUN] Would generate .env with fresh encryption keys"
  else
    ENCRYPTION_KEY="${ENCRYPTION_KEY:-$(openssl rand -base64 32)}"
    PG_PASS="${PG_DATABASE_PASSWORD:-$(openssl rand -base64 16 | tr -d '+/=' | cut -c1-16)}"

    cat > "${DEPLOY_DIR}/.env" << ENVEOF
TAG=latest
SERVER_URL=http://localhost:3003
ENCRYPTION_KEY=${ENCRYPTION_KEY}
PG_DATABASE_PASSWORD=${PG_PASS}
STORAGE_TYPE=local
ACCESS_TOKEN_EXPIRES_IN=3600000
LOGIN_TOKEN_EXPIRES_IN=900000
REFRESH_TOKEN_EXPIRES_IN=86400000
REDIS_URL=redis://twenty-redis:6379
MESSAGE_QUEUE_TYPE=sync
ENVEOF
    log "Generated .env with fresh encryption key"
  fi

  # ── 3. Pull image & start ──────────────────────────────────────────
  if $DRY_RUN; then
    info "[DRY-RUN] Would pull twentycrm/twenty:latest and start services"
  else
    cd "$DEPLOY_DIR"
    warn "Pulling Twenty CRM image (1.86GB)..."
    docker compose pull server 2>/dev/null && log "Image pulled" || warn "Pull failed — using cached"

    warn "Starting Twenty CRM (this may take a while for first-time migrations)..."
    docker compose up -d 2>&1 | tail -3
    log "Twenty CRM services started"

    info "Migrations running in background. Check status with:"
    info "  cd ${DEPLOY_DIR} && docker compose ps"
    info "  curl -s -o /dev/null -w '%{http_code}' http://localhost:3003/"
  fi

  echo -e "\n${GREEN}  ✅ Twenty CRM: http://localhost:3003/${NC}"
  echo -e "     (Complete first-run setup via web UI)"
  echo -e "     First visit → create workspace → create admin account"
}

# ════════════════════════════════════════════════════════════════════════
#  PHASE 3: IMPORT CONTRACTORS INTO LISTMONK
# ════════════════════════════════════════════════════════════════════════

import_contractors() {
  echo -e "\n${CYAN}═══════════════════════════════════════════════════════════${NC}"
  echo -e "${CYAN}  PHASE 3: Import Contractors → ListMonk${NC}"
  echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}\n"

  if ! docker ps --format '{{.Names}}' | grep -q '^listmonk-q$'; then
    err "ListMonk not running — deploy it first or run without --import-only"
    exit 1
  fi

  if $DRY_RUN; then
    warn "[DRY-RUN] Would run: python3 ${REPO_DIR}/scripts/import_listmonk.py"
    python3 "${REPO_DIR}/scripts/import_listmonk.py" --dry-run 2>&1
  else
    python3 "${REPO_DIR}/scripts/import_listmonk.py" 2>&1
  fi
}

# ════════════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════════════

main() {
  echo -e "${CYAN}"
  echo '  ╔══════════════════════════════════════════════════════╗'
  echo '  ║        Empire AI · CRM Deployment Script            ║'
  echo '  ║     ListMonk (:9000) + Twenty CRM (:3003)           ║'
  echo '  ╚══════════════════════════════════════════════════════╝'
  echo -e "${NC}"

  if $DRY_RUN; then
    warn "=== DRY RUN MODE — no changes will be made ===\n"
  fi

  if $IMPORT_ONLY; then
    import_contractors
  elif $FIX_CONFIG; then
    # --fix-config: regenerate config.toml + restart listmonk-q only
    info "=== --fix-config mode: regenerate config + restart ==="
    deploy_listmonk
  else
    if $DEPLOY_LISTMONK; then deploy_listmonk; fi
    if $DEPLOY_TWENTY; then deploy_twenty; fi
    import_contractors
  fi

  echo -e "\n${GREEN}═══════════════════════════════════════════════════════════${NC}"
  echo -e "${GREEN}  Deployment complete!${NC}"
  echo -e ""
  echo -e "  ${CYAN}ListMonk${NC}  →  http://localhost:9000/admin"
  echo -e "              admin / ${LISTMONK_ADMIN_PASS}"
  echo -e ""
  echo -e "  ${CYAN}Twenty CRM${NC} →  http://localhost:3003/"
  echo -e "              (set up admin via first-run web UI)"
  echo -e ""
  echo -e "  Admin password saved to: /root/.listmonk_admin"
  echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}\n"

  # Save admin password
  if ! $DRY_RUN; then
    echo "listmonk_admin_password=${LISTMONK_ADMIN_PASS}" > /root/.listmonk_admin
    chmod 600 /root/.listmonk_admin
  fi
}

main "$@"
