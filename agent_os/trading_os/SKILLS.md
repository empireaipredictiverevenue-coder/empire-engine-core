# TRADING BRAIN · Skills Registry

## Registered Skills

### 1. `trading.market.analyze`
Analyze market conditions across crypto, forex, futures, or gold.
- Input: market (crypto|forex|futures|gold), symbol/pair, timeframe (1m|5m|15m|1h|4h|1d)
- Output: trend direction, key levels, volatility assessment, market regime
- Dependencies: trading.indicators.calculate

### 2. `trading.indicators.calculate`
Calculate technical indicators for any symbol/pair.
- Input: symbol, timeframe, indicators list (RSI, MACD, MA, BB, VWAP, Volume Profile, OBV, Stochastic)
- Output: dict of indicator_name → value/signal (bullish|bearish|neutral)
- Dependencies: none (pure computation or API call)

### 3. `trading.meme.sniper`
Identify and execute meme coin sniping opportunities on Solana.
- Input: min_liquidity (SOL), max_age_seconds, max_market_cap, snipe_amount (SOL)
- Output: token address, risk score (0-100), entry tx signature, expected slippage
- Dependencies: trading.swap.execute, trading.rug.detect
- Tags: [mode:execution, risk:high]

### 4. `trading.meme.scan`
Scan for new meme coin launches on Solana DEXs (PumpFun, Raydium, Meteora).
- Input: min_liquidity, max_age, min_holders, exclude_honeypot (bool)
- Output: list of token addresses with metadata, liquidity, holder count, age
- Tags: [mode:scan, risk:low]

### 5. `trading.rug.detect`
Run rug-pull detection checks on a token.
- Input: token_address
- Output: risk score (0-100), flags (honeypot, mint_authority, freeze_authority, lp_locked, high_slippage, low_liquidity)
- Tags: [mode:safe, risk:none]

### 6. `trading.swap.execute`
Execute a token swap on Solana via Jupiter aggregator.
- Input: input_mint, output_mint, amount (in input token), slippage_bps (default 50)
- Output: tx_signature, input_amount, output_amount, price_impact
- Dependencies: SOLANA_RPC_URL, wallet private key
- Destructive: YES (spends funds)

### 7. `trading.portfolio.rebalance`
Analyze current portfolio and suggest rebalancing actions.
- Input: target_allocation dict (asset → %), rebalance_threshold (default 5%)
- Output: suggested trades to rebalance, current vs target allocation table
- Tags: [mode:analysis]

### 8. `trading.risk.assess`
Assess risk of a potential trade.
- Input: symbol, entry_price, stop_loss, take_profit, position_size, leverage
- Output: risk_score (0-100), risk_reward_ratio, max_loss_usd, suggestion (accept|reduce|skip)
- Tags: [mode:safe]

### 9. `trading.forex.analyze`
Analyze forex pair with fundamentals and technicals.
- Input: pair (EUR/USD, GBP/USD, XAU/USD, etc.), timeframe
- Output: trend, key support/resistance, fundamental catalysts, sentiment
- Dependencies: trading.indicators.calculate

### 10. `trading.futures.analyze`
Analyze futures/perpetuals market conditions.
- Input: symbol, exchange, timeframe
- Output: funding_rate, open_interest trend, liquidation levels, basis
- Tags: [mode:analysis]

### 11. `trading.gold.analyze`
Analyze gold (XAU/USD, XAU/EUR, COMEX futures).
- Input: symbol (default XAU/USD), timeframe
- Output: trend, key levels, correlation with DXY, real yield context, central bank positioning
- Dependencies: trading.indicators.calculate

### 12. `trading.strategy.backtest`
Backtest a trading strategy against historical data.
- Input: strategy_params, symbol, timeframe, lookback_period
- Output: win_rate, max_drawdown, sharpe_ratio, total_return, trade_log
- Tags: [mode:analysis]

### 13. `trading.signal.generate`
Generate a consolidated trading signal across all configured markets.
- Input: markets list (crypto|forex|futures|gold), min_confidence (0-1)
- Output: list of signals with symbol, direction (long|short), confidence, reasoning, suggested entry
- Tags: [mode:analysis]

### 14. `trading.order.place`
Place a limit or market order on a configured exchange.
- Input: exchange, symbol, side (buy|sell), type (market|limit), amount, price (if limit)
- Output: order_id, status, filled_amount, avg_price
- Destructive: YES (spends funds)
- Dependencies: exchange API key

## Dependencies
- `trading.meme.sniper` → `trading.swap.execute` + `trading.rug.detect`
- `trading.meme.scan` → Helius RPC / Birdeye API
- `trading.forex.analyze` → `trading.indicators.calculate`
- `trading.gold.analyze` → `trading.indicators.calculate`
- `trading.signal.generate` → all market analysis skills
- `trading.order.place` → exchange credentials
