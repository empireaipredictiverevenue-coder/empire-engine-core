# ═══════════════════════════════════════════════════════════════════════════
# PREDICITIVE TRADING BOT · DOCKERFILE
# ═══════════════════════════════════════════════════════════════════════════
# Multi-stage build: base → deps → runtime
#
# Build:
#   docker build -t predicitive-trading-bot:latest .
#
# Run (full stack: API + stop loss monitor):
#   docker run -d --name trading-bot \
#     -p 8050:8050 \
#     -e SOLANA_RPC_URL="https://api.mainnet-beta.solana.com" \
#     -e STOPLOSS_WALLET_PRIVATE_KEY="..." \
#     predicitive-trading-bot:latest
#
# Run (stop loss monitor only):
#   docker run -d --name trading-stoploss \
#     -e SOLANA_RPC_URL="https://api.mainnet-beta.solana.com" \
#     -e STOPLOSS_WALLET_PRIVATE_KEY="..." \
#     predicitive-trading-bot:latest \
#     python3 stoploss_bot.py --loop
#
# Run with docker-compose (recommended):
#   docker compose up -d
# ═══════════════════════════════════════════════════════════════════════════

# ── Stage 1: Base ────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install system deps (curl for healthchecks, ca-certificates for SSL)
RUN apt-get update -qq && apt-get install -y -qq \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── Stage 2: Dependencies ────────────────────────────────────────────────
FROM base AS deps

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 3: Runtime ────────────────────────────────────────────────────
FROM deps AS runtime

# Copy the entire trading bot codebase
COPY . .

# Make scripts executable
RUN chmod +x *.sh 2>/dev/null || true

# Default env vars (overridable via docker run -e or docker-compose env)
ENV SOLANA_RPC_URL="https://api.mainnet-beta.solana.com" \
    STOPLOSS_INTERVAL_SEC="15" \
    STOPLOSS_SOLANA_TIMEOUT="30" \
    HOST="0.0.0.0" \
    PORT=8050

# Persistent data volume (SQLite DB for positions)
VOLUME ["/app/data"]

# Healthcheck — the FastAPI /api/v1/health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:${PORT}/api/v1/health || exit 1

EXPOSE ${PORT}

# Default: run the full stack (API + stop loss monitor)
CMD ["python3", "trading_bot.py"]
