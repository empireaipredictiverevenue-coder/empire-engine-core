# Gold Trading Reference

## Gold Instruments
### XAU/USD (Spot Gold)
- Most liquid gold instrument
- 24/5 trading (Sunday 23:00 UTC — Friday 21:00 UTC)
- 1 lot = 100 troy ounces
- Pip value: $10 per standard lot ($1 for mini)
- Typical spread: 20-50 pips
- Average daily range: $15-30

### XAU/EUR (Gold priced in Euros)
- Alternative to XAU/USD for Euro-based traders
- Used to trade gold without USD exposure
- Less liquid than XAU/USD

### COMEX Gold Futures (GC)
- Futures contract on CME/COMEX
- Contract size: 100 troy ounces
- Tick size: $0.10 per ounce ($10 per contract)
- Expiry: Feb, Apr, Jun, Aug, Oct, Dec
- Most active: front month (nearest expiry)
- Institutional — drives spot price
- Trading hours: Sunday 18:00 — Friday 17:00 EST

### Gold ETFs
- GLD: SPDR Gold Trust (largest, most liquid)
- IAU: iShares Gold Trust (lower expense ratio)
- PHYS: Sprott Physical Gold Trust
- Not recommended for active trading (24h market better)

## Key Drivers of Gold Price

### 1. US Dollar Strength (Inverse Correlation)
- Stronger USD → lower gold price (gold is USD-denominated)
- DXY index: primary gauge of USD strength
- Correlation typically -0.5 to -0.8

### 2. Real Yields (Primary Long-term Driver)
- Gold has no yield → competes with yield-bearing assets
- Falling real yields (TIPS yields) → gold rises
- Rising real yields → gold falls
- **This is the strongest long-term correlation**

### 3. Inflation
- Gold is a traditional inflation hedge
- CPI, PCE, PPI all matter
- Inflation surprises → gold spikes
- Disinflation → gold underperforms

### 4. Geopolitical Risk
- Wars, sanctions, political instability → gold up
- "Flight to safety" flows
- Examples: Russia-Ukraine, Middle East, US debt ceiling

### 5. Central Bank Buying
- Major central banks (China, India, Turkey, Russia, Poland) are net buyers
- Record central bank purchases in 2022-2026
- De-dollarization trend supports gold
- Follow PBOC, RBI, TCMB gold reserve reports

### 6. Interest Rates
- Lower rates → lower opportunity cost of holding gold → gold up
- Rate cuts → gold rallies
- Rate hikes → gold initially falls, then recovers (forward-looking)

### 7. Gold-Silver Ratio
- XAU/XAG ratio: ounces of silver to buy 1 oz of gold
- Historical average: ~60:1
- Ratio > 80: silver undervalued (buy silver)
- Ratio < 40: silver overvalued (buy gold)
- Falling ratio = risk-on environment

## Gold Trading Strategies

### Intraday Gold
```python
# Best hours: 12:00-16:00 UTC (London/NY overlap)
# News events: Fed rate decisions, NFP, CPI (major gold movers)
strategy = {
    "timeframe": "15m-1h",
    "indicators": ["EMA 9/21", "VWAP", "RSI 14", "Volume"],
    "entry": "Retest of VWAP after news event + RSI confirmation",
    "stop": "Below previous session low or $5 below entry",
    "target": "2:1 risk/reward minimum",
}
```

### Swing Gold
```python
strategy = {
    "timeframe": "4h-1d",
    "indicators": ["50/200 EMA", "MACD daily", "Real yields trend"],
    "entry": "Pullback to 50 EMA in uptrend + bullish MACD cross",
    "stop": "Below 200 EMA or 2% below entry",
    "target": "Previous high or 1:3 risk/reward",
}
```

### Gold Correlation Matrix
| Asset | Correlation | Strength |
|---|---|---|
| DXY (USD Index) | Negative | Strong |
| US 10Y Real Yield | Negative | Very Strong |
| Silver (XAG/USD) | Positive | Strong |
| Bitcoin | Weak Positive | Weak |
| S&P 500 | Mixed | Time-dependent |
| Oil (WTI) | Weak Positive | Weak |

## Key Levels & Technical Notes
- **$2,000**: Major psychological level since 2020
- **Gold loves round numbers**: $1,800, $1,900, $2,000, $2,100
- **200-day MA**: Major trend filter (above = bull, below = bear)
- **Volume Profile at all-time highs**: low volume = false breakout
- **Gold tends to gap**: watch Monday opens closely
- **Options expiry (COMEX)**: monthly, can cause gamma squeezes
