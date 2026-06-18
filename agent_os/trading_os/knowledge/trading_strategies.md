# Trading Strategies Reference

## Scalping (Short-term, high frequency)
- Timeframe: 1m-5m charts
- Indicators: EMA 9/21 ribbon, Volume profile, order flow
- Entry criteria: sudden volume spike + EMA cross + momentum confirmation
- Exit: take profit at 0.5-1.5% (crypto), 10-20 pips (forex)
- Stop loss: tight, 0.3-0.5% below support
- Risk per trade: 0.5-1% of portfolio
- Best for: high-liquidity pairs, news events

## Swing Trading (Medium-term)
- Timeframe: 4h-1d charts
- Indicators: RSI, MACD, VWAP, Ichimoku Cloud
- Entry criteria: RSI divergence + MACD cross + price at key support/resistance
- Exit: at next significant resistance/support or 1:3 risk/reward
- Stop loss: below structure (2-4% for crypto, 50-100 pips for forex)
- Risk per trade: 1-2% of portfolio
- Hold time: 2 days to 2 weeks
- Best for: trending markets, after news events settle

## Trend Following
- Timeframe: 1d-1w charts
- Indicators: 50/200 EMA, ADX, MACD
- Entry criteria: ADX > 25 (strong trend) + price above both EMAs + higher highs
- Exit: EMA cross (golden cross entry, death cross exit)
- Stop loss: below the most recent swing low
- Risk per trade: 1-2% of portfolio
- Best for: strong directional markets (crypto bull runs, forex trends)

## Mean Reversion
- Timeframe: 15m-1h charts
- Indicators: Bollinger Bands, RSI, Stochastic
- Entry criteria: price touches lower band + RSI < 30 + Stochastic < 20
- Exit: price touches middle band or upper band
- Stop loss: 2x ATR below entry
- Best for: ranging markets, after large moves

## Meme Coin Sniping Strategy
### Pre-Launch Preparation
- Fund wallet with SOL for gas fees + snipe amount
- Monitor PumpFun / new Raydium pairs via Helius WebSocket
- Pre-compute buy parameters for target tokens
- Set slippage: 15-25% (meme coins are volatile)

### Launch Detection
- Filter criteria: min liquidity 5 SOL, max market cap $500K, age < 10 min
- Check holder count, top-10 concentration
- Run rug detection before ANY buy
- Flags: mint authority still active, freeze authority active, LP not locked

### Entry
- Gas priority: set compute unit price to 0.01 SOL (high priority)
- Buy amount: 0.1-0.5 SOL per snipe
- Use Jupiter for routing if token is already on Raydium
- Set take profit at 2x-5x, trailing stop at 20%

### Exit Rules
- If rug detected within 30 min → sell immediately (any loss acceptable)
- If 2x in 1 hour → sell 50%, hold 50%
- If 5x anytime → sell 100%
- If down 50% from entry → sell immediately

## Grid Trading
- Place buy orders at regular price intervals below current price
- Place sell orders at regular intervals above current price
- Profit from each grid level as price oscillates
- Best for: stablecoin pairs, ranging markets
- Grid width: 1-3% per level, 10-20 levels

## Arbitrage
- Triangular: trade across 3 pairs on same exchange
- Cross-exchange: buy low on exchange A, sell high on exchange B
- Funding rate: long perpetual with positive funding, hedge with spot
- Requires: fast execution, multiple exchange accounts, low latency
