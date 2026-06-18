# Technical Indicators Reference

## Momentum Indicators
### RSI (Relative Strength Index)
- Formula: 100 - (100 / (1 + avg_gain / avg_loss))
- Period: default 14
- Overbought: > 70 (bearish signal)
- Oversold: < 30 (bullish signal)
- Divergence: price makes higher high, RSI makes lower high = bearish divergence
- Best for: crypto and forex ranging markets

### MACD (Moving Average Convergence Divergence)
- Components: MACD line (12 EMA - 26 EMA), Signal line (9 EMA of MACD), Histogram
- Bullish: MACD crosses above signal line
- Bearish: MACD crosses below signal line
- Zero cross: MACD above zero = bullish momentum
- Best for: trend confirmation in all markets

### Stochastic Oscillator
- %K = (Current Close - Lowest Low) / (Highest High - Lowest Low) × 100
- %D = 3-period SMA of %K
- Overbought: > 80
- Oversold: < 20
- Fast settings: 5, 3, 3 for crypto scalping

## Trend Indicators
### Moving Averages
- SMA: Simple moving average (equal weight)
- EMA: Exponential moving average (more weight to recent)
- Key periods: 9/21 (short), 50/100 (medium), 200 (long-term)
- Golden cross: 50 SMA crosses above 200 SMA = bullish
- Death cross: 50 SMA crosses below 200 SMA = bearish
- EMA ribbon: multiple EMAs stacked = strong trend direction

### VWAP (Volume Weighted Average Price)
- VWAP = Σ(Price × Volume) / Σ(Volume)
- Above VWAP = bullish intraday bias
- Below VWAP = bearish intraday bias
- Best for: intraday trading, crypto

### Ichimoku Cloud
- Tenkan-sen (Conversion): (9-high + 9-low)/2
- Kijun-sen (Base): (26-high + 26-low)/2
- Senkou Span A: (Tenkan + Kijun)/2, shifted 26 periods
- Senkou Span B: (52-high + 52-low)/2, shifted 26 periods
- Price above cloud = bullish, below = bearish
- Cloud thickness = volatility

## Volume Indicators
### OBV (On-Balance Volume)
- If close > previous close: OBV += volume
- If close < previous close: OBV -= volume
- Rising OBV with flat price = accumulation
- Falling OBV with rising price = distribution

### Volume Profile
- Shows volume at each price level
- High Volume Node (HVN) = support/resistance
- Low Volume Node (LVN) = price will move through quickly
- Value Area: 70% of volume around POC (Point of Control)
- Best for: futures and forex

## Volatility Indicators
### Bollinger Bands
- Middle: 20-period SMA
- Upper: SMA + (2 × StdDev)
- Lower: SMA - (2 × StdDev)
- Squeeze: bands contract = upcoming breakout
- Walk: price walking upper band = strong trend
- Best for: mean reversion strategies

### ATR (Average True Range)
- TR = max(high - low, |high - prev_close|, |low - prev_close|)
- ATR = EMA of TR (default 14 periods)
- High ATR = high volatility
- Used for: stop-loss placement (2-3x ATR), position sizing

## Crypto-Specific
- MVRV Z-Score: Market Value / Realized Value (overbought/oversold)
- Puell Multiple: miner revenue / 365-day MA (cap cycle tops/bottoms)
- NUPL: Net Unrealized Profit/Loss (market sentiment stages)
- Funding Rate: > 0.01% = bullish sentiment, < -0.01% = bearish
- Open Interest: rising OI + rising price = trend confirmed
