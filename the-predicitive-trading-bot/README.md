# The Predicitive Trading Bot

Standalone Solana trading bot with stop loss monitoring, token swap execution, and trading intelligence skills.

## Architecture

```
├── stoploss_bot.py       # PM2 service — monitors positions, checks prices, triggers stop losses
├── stoploss_routes.py    # FastAPI REST API for position management
├── trading_bot.py        # Main orchestrator entry point
├── ecosystem.config.js   # PM2 process configuration
├── skills/
│   ├── base.py           # BaseSkill abstract base + data contracts
│   └── trading_skills.py # 10 trading skill implementations
└── requirements.txt
```

## Components

### Stop Loss Bot (`stoploss_bot.py`)
Standalone PM2-managed service that:
- Tracks open trading positions in a SQLite database (WAL mode)
- Fetches token prices via Jupiter Price API
- Supports fixed and trailing stop losses
- Executes live swaps via Jupiter aggregator when a stop is triggered
- Handles confirmation polling on Solana

### API Routes (`stoploss_routes.py`)
FastAPI endpoints for managing positions:
- `POST /api/v1/stoploss/add` — Add a position
- `GET /api/v1/stoploss/list` — List all positions
- `POST /api/v1/stoploss/cancel` — Cancel/remove a position
- `GET /api/v1/stoploss/status` — Bot health + position stats

### Trading Skills (`skills/trading_skills.py`)
10 skill modules for the Brain framework:
1. `trading.market.analyze` — Market conditions analysis
2. `trading.indicators.calculate` — RSI, MACD, MA, BB, VWAP
3. `trading.meme.scan` — Solana DEX meme coin scanner
4. `trading.rug.detect` — Rug-pull and honeypot detection
5. `trading.risk.assess` — Position sizing, R:R, max loss
6. `trading.signal.generate` — Consolidated trading signals
7. `trading.meme.sniper` — Full sniper pipeline
8. `trading.strategy.backtest` — Win rate, Sharpe, drawdown
9. `trading.swap.execute` — Jupiter aggregator swap execution
10. `trading.brain.advise` — Market context for Brain decisions

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
```bash
export STOPLOSS_WALLET_PRIVATE_KEY="your_base58_private_key"
export SOLANA_RPC_URL="https://api.mainnet-beta.solana.com"
```

### 3. Start the stop loss monitor
```bash
python3 stoploss_bot.py --loop
```

Or via PM2:
```bash
pm2 start ecosystem.config.js --only stop-loss-bot
```

### 4. Add a position
```bash
python3 stoploss_bot.py --add <TOKEN_MINT> <ENTRY_PRICE> <AMOUNT> <STOP_LOSS_PCT> --trailing
```

### 5. Check status
```bash
python3 stoploss_bot.py --status
```

## API (when used with FastAPI)
```bash
# Add position
curl -X POST /api/v1/stoploss/add \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"token_mint": "...", "entry_price": 100, "amount": 10, "stop_loss_percent": 0.05}'

# Check status
curl /api/v1/stoploss/status -H "Authorization: Bearer $TOKEN"
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `STOPLOSS_WALLET_PRIVATE_KEY` | — | Base58-encoded Solana private key (live execution) |
| `SOLANA_RPC_URL` | `https://api.mainnet-beta.solana.com` | Solana RPC endpoint |
| `STOPLOSS_INTERVAL_SEC` | `15` | Price check interval |
| `STOPLOSS_SOLANA_TIMEOUT` | `30` | Transaction confirmation timeout |
| `HELIUS_API_KEY` | — | Helius RPC (trading skills) |
| `BIRDEYE_API_KEY` | — | Birdeye API (trading skills) |
| `JUPITER_API_KEY` | — | Jupiter API key |

## Safety

- **Dry-run by default** — no real swaps without `STOPLOSS_WALLET_PRIVATE_KEY`
- **Confirmation polling** — waits for on-chain confirmation before reporting success
- **SIGTERM handling** — graceful shutdown via PM2 signals
- **WAL mode SQLite** — concurrent-safe position storage
- **Auto-migration** — legacy JSON files are migrated to SQLite on first run
