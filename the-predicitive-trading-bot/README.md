# The Predicitive Trading Bot

Standalone Solana trading bot with stop loss monitoring, token swap execution,
trading intelligence skills, strategy framework, backtesting, and parameter
optimization.

## Architecture

```
├── stoploss_bot.py        # PM2 service — monitors positions, checks prices, triggers stop losses
├── stoploss_routes.py     # FastAPI REST API for position management
├── trading_bot.py         # Main orchestrator entry point
├── ecosystem.config.js    # PM2 process configuration
├── skills/
│   ├── base.py            # BaseSkill abstract base + data contracts
│   ├── indicators.py      # 11 technical indicator calculators
│   ├── trading_skills.py  # 10+ trading skill implementations
│   ├── strategy.py        # Strategy base, registry, 3 built-in strategies
│   ├── strategy_runner.py # Walk-forward strategy evaluation engine
│   ├── strategy_optimizer.py # Scipy/grid search parameter optimization
│   ├── strategy_backtest.py  # Real backtesting with IC + rolling metrics
│   ├── ai_analysis.py     # AI-powered market analysis & sentiment
│   ├── risk_management.py # Portfolio risk: VaR, Kelly, drawdown
│   └── __init__.py        # Package exports
└── requirements.txt
```

## Source Repositories

These modules are adapted from three open-source quant trading repositories:

| Repository | GitHub | What We Adapted |
|---|---|---|
| **QuantMuse** | `0xemmkty/QuantMuse` | Architecture: skill system, strategy registry, risk engine (C++), factor calculator, backtester, optimizer, AI agent |
| **Sunday Quant Scientist** | `quant-science/sunday-quant-scientist` | Individual indicator math: MACD, RSI, Bollinger Bands, Kelly criterion, mean reversion |
| **je-suis-tm quant-trading** | `je-suis-tm/quant-trading` | Strategy implementations, pattern recognition on indicators, breakout logic |

> **Attribution:** ~60 adaptations across the codebase reference QuantMuse methods
> (`FactorCalculator`, `StrategyBase`, `SentimentAnalyzer`, `LangChainAgent`,
> `RiskManager`, `StrategyOptimizer`, `FactorBacktest`). The C++ risk engine
> headers (`risk_manager.hpp`) and `config.example.json` informed the
> portfolio risk defaults.

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

### Technical Indicators (`skills/indicators.py`)
11 real indicator calculators (no pandas dependency):
- **RSI** — Relative Strength Index (smoothed average gain/loss)
- **MACD** — Moving Average Convergence Divergence (EMA-based, cross detection)
- **SMA / EMA** — Multi-period moving averages (9, 21, 50, 200 by default)
- **Bollinger Bands** — SMA ± k·σ with position tracking
- **VWAP** — Volume-Weighted Average Price
- **OBV** — On-Balance Volume (cumulative flow)
- **Stochastic** — %K / %D oscillator
- **Volatility** — Daily + annualized (√252)
- **Sharpe Ratio** — Annualized risk-adjusted return
- **Max Drawdown** — Peak-to-trough tracking
- **Momentum** — Multi-period price momentum + acceleration

*Adapted from QuantMuse FactorCalculator.*

### Strategy Framework (`skills/strategy.py`)
Composable strategy system:
- **StrategyBase** — Abstract base with preprocess → generate → postprocess → metrics pipeline
- **StrategyRegistry** — Class + instance registration, market-aware lookup
- **3 Built-in strategies:**
  - `strategy.momentum` — RSI + MACD momentum with trend confirmation
  - `strategy.mean_reversion` — Buy below MA, sell at mean (Bollinger Bands)
  - `strategy.breakout` — Volume-confirmed BB breakout with VWAP filter

*Adapted from QuantMuse StrategyBase + strategy_registry.*

### Strategy Runner (`skills/strategy_runner.py`)
Walk-forward simulation engine:
- `run_strategy()` — Single-point strategy execution
- `evaluate_strategy()` — Real walk-forward over historical prices, tracking P&L, equity curve, trades
- `evaluate_multiple()` — Batch evaluation across strategies
- Computes: Sharpe, max drawdown, win rate, profit factor, win/loss ratio

*Adapted from QuantMuse StrategyRunner.*

### Strategy Optimizer (`skills/strategy_optimizer.py`)
Parameter optimization with 3 methods:
- **Grid search** — Exhaustive over discrete values (always available)
- **Scipy L-BFGS-B** — Gradient-based optimization (requires `scipy`)
- **Differential evolution** — Genetic algorithm (requires `scipy`)
- Objective functions: Sharpe ratio, total return, win rate, profit factor
- Graceful fallback to grid search when scipy is not installed

*Adapted from QuantMuse StrategyOptimizer.*

### Strategy Backtester (`skills/strategy_backtest.py`)
Real backtesting (replaces the old simulated-random skill):
- Full walk-forward evaluation via StrategyRunner
- **Information Coefficient (IC)** — Pearson + Spearman rank correlation between strategy signals and forward returns
- **Rolling metrics** — Sliding window win rate, avg return, profit factor
- **Strategy comparison** — Side-by-side multi-strategy ranking
- **Performance reports** — Formatted text summaries

*Adapted from QuantMuse FactorBacktest.*

### AI Analysis (`skills/ai_analysis.py`)
LLM-powered analysis with heuristic fallbacks:
- `trading.ai.market.analyze` — Market regime, trend, volatility, risk, opportunities
- `trading.ai.sentiment` — Sentiment scoring from news/text with keyword fallback
- `trading.ai.advise` — Consolidated trading advice (action, confidence, risk warnings)
- Uses OpenAI-compatible API (`OPENAI_API_KEY`); graceful fallback to heuristics

*Adapted from QuantMuse LangChainAgent + SentimentAnalyzer.*

### Portfolio Risk (`skills/risk_management.py`)
Portfolio-level risk engine:
- **VaR** — Parametric (normal) + historical with CVaR
- **Kelly Criterion** — Full + fractional Kelly position sizing
- **Concentration / Diversification** — HHI-based scoring
- **Drawdown tracking** — Peak-to-trough with daily loss limits
- **Risk budget allocation** — Equal, inverse-vol, and Kelly-based
- **Position risk** — Per-position sizing, stop loss, risk contribution

*Adapted from QuantMuse C++ risk_manager + config.example.json.*

### Trading Skills (`skills/trading_skills.py`)
14 skill modules for the Brain framework:
1. `trading.market.analyze` — Market conditions analysis
2. `trading.indicators.calculate` — RSI, MACD, MA, BB, VWAP (delegates to indicators.py)
3. `trading.meme.scan` — Solana DEX meme coin scanner
4. `trading.rug.detect` — Rug-pull and honeypot detection
5. `trading.risk.assess` — Position sizing, R:R, max loss
6. `trading.signal.generate` — Consolidated trading signals
7. `trading.meme.sniper` — Full sniper pipeline
8. `trading.strategy.backtest` — **Real** walk-forward backtesting (v2.0.0)
9. `trading.swap.execute` — Jupiter aggregator swap execution
10. `trading.brain.advise` — Market context for Brain decisions
11. `trading.ai.market.analyze` — AI market analysis (from ai_analysis.py)
12. `trading.ai.sentiment` — AI sentiment scoring (from ai_analysis.py)
13. `trading.ai.advise` — AI trading advice (from ai_analysis.py)
14. `trading.risk.portfolio` — Portfolio risk assessment (from risk_management.py)

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

Optional for advanced optimization:
```bash
pip install scipy  # L-BFGS-B + differential evolution
```

### 2. Configure environment
```bash
export STOPLOSS_WALLET_PRIVATE_KEY="your_base58_private_key"
export SOLANA_RPC_URL="https://api.mainnet-beta.solana.com"
```

Optional for AI analysis:
```bash
export OPENAI_API_KEY="sk-..."
export AI_MODEL="gpt-4o-mini"
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

### 6. Run a backtest (Python)
```python
from skills.strategy import StrategyRegistry, register_builtin_strategies
from skills.strategy_backtest import StrategyBacktester

reg = StrategyRegistry()
register_builtin_strategies(reg)
backtester = StrategyBacktester(reg)

result = await backtester.run_backtest("strategy.momentum", "BTC/USD", price_history)
print(backtester.generate_report(result))
```

### 7. Optimize parameters (Python)
```python
from skills.strategy_optimizer import StrategyOptimizer

optimizer = StrategyOptimizer(reg)
result = await optimizer.optimize(
    "strategy.mean_reversion", "SOL/USDC", price_history,
    parameter_ranges={"ma_period": [20, 50, 100], "deviation_threshold": [0.03, 0.05, 0.08]},
    objective="sharpe_ratio", method="grid",
)
```

## API (when used with FastAPI)
```bash
# Add position
curl -X POST /api/v1/stoploss/add \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"token_mint": "...", "entry_price": 100, "amount": 10, "stop_loss_percent": 0.05}'

# List skills + strategies
curl /api/v1/skills

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
| `OPENAI_API_KEY` | — | OpenAI API key (AI analysis skills) |
| `AI_MODEL` | `gpt-4o-mini` | Model for AI analysis |
| `AI_MAX_TOKENS` | `500` | Max tokens per AI response |
| `AI_TEMPERATURE` | `0.3` | AI response temperature |

## Safety

- **Dry-run by default** — no real swaps without `STOPLOSS_WALLET_PRIVATE_KEY`
- **Confirmation polling** — waits for on-chain confirmation before reporting success
- **SIGTERM handling** — graceful shutdown via PM2 signals
- **WAL mode SQLite** — concurrent-safe position storage
- **Auto-migration** — legacy JSON files are migrated to SQLite on first run
- **AI heuristic fallbacks** — all AI skills operate without OpenAI if no key is set
- **Graceful scipy fallback** — optimizer uses grid search when scipy is not installed
