# ═══════════════════════════════════════════════════════════════════════════
# EMPIRE AI V49 · WHITE-LABEL CONTAINER
# ═══════════════════════════════════════════════════════════════════════════
# Multi-stage build: base → deps → runtime
#
# Build:
#   docker build -t empireai/hub:latest .
#
# Run (standalone hub):
#   docker run -d --name empire-hub \
#     -p 8000:8001 \
#     -v /root/.env:/root/.env:ro \
#     empireai/hub:latest
#
# Run (full suite, with compose):
#   docker compose up -d
#
# White-label partner (custom branding):
#   docker run -d --name partner-acme \
#     -p 8001:8001 \
#     -v /root/.env:/root/.env:ro \
#     -e PARTNER_ID=acme \
#     -e PARTNER_NAME="Acme Restoration" \
#     -e BRAND_PRIMARY_COLOR="#00FF88" \
#     -e BRAND_LOGO_URL="https://acme.com/logo.png" \
#     -e TIER=enterprise \
#     empireai/hub:latest
# ═══════════════════════════════════════════════════════════════════════════

# ── Stage 1: Base ────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install system deps (ffmpeg for video, curl for healthchecks, git for version info)
RUN apt-get update -qq && apt-get install -y -qq \
    ffmpeg \
    curl \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── Stage 2: Dependencies ────────────────────────────────────────────────
FROM base AS deps

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 3: Runtime ────────────────────────────────────────────────────
FROM deps AS runtime

# Copy the entire empire codebase
COPY . .

# Make scripts executable
RUN chmod +x *.sh 2>/dev/null || true

# Default branding env vars (overridable per partner container)
ENV PARTNER_ID="" \
    PARTNER_NAME="" \
    BRAND_PRIMARY_COLOR="#44E5B8" \
    BRAND_SECONDARY_COLOR="#0A0A0F" \
    BRAND_LOGO_URL="" \
    BRAND_FAVICON_URL="" \
    BRAND_CUSTOM_DOMAIN="" \
    TIER="" \
    CONTAINER_MODE="hub" \
    HUB_PORT=8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:${HUB_PORT}/api/hub/diagnostics || exit 1

EXPOSE ${HUB_PORT}

# Default: run the hub
CMD ["python3", "-m", "uvicorn", "hub:app", "--host", "0.0.0.0", "--port", "8001"]
