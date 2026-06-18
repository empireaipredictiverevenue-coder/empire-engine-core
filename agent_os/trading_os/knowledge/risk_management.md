# Risk Management Framework

## Core Principles
1. **Capital preservation is priority #1** — Don't lose money you need to trade tomorrow
2. **Every position has a defined exit** — before entry, know your stop and target
3. **Risk per trade is fixed** — never variable based on "feeling"
4. **Correlation-aware** — multiple correlated positions compound risk
5. **Drawdown management** — reduce risk after losses, increase after wins

## Position Sizing Formula
```
Position Size = (Account × Risk%) / (Entry - Stop)

Risk% recommended: 0.5-1.0% per trade (crypto), 0.5-2.0% (forex)

Example:
  Account: $10,000
  Risk: 1% = $100
  Entry: $100, Stop: $95 (5% stop)
  Position: $100 / $5 = $2,000 worth (20 units if price $100)
```

## Kelly Criterion (optimal position sizing)
```
f* = (p × b - q) / b

Where:
  f* = fraction of capital to risk
  p = probability of winning
  q = probability of losing (1-p)
  b = payout ratio (win / loss)

Conservative approach: use 25% of Kelly (half-Kelly)
```

## Maximum Drawdown Management
```
DRAWDOWN STAGES:
  0-5%:    Normal trading, standard risk
  5-10%:   Reduce position size by 25%
  10-15%:  Reduce position size by 50%, stop trading altcoins
  15-20%:  Stop all trading, close all positions, go to cash
  >20%:    Emergency shutdown, review strategy
  
RECOVERY:
  After drawdown, trade at 50% normal risk until back to even
  After recovery, return to standard risk
```

## Risk by Asset Class
| Asset | Max Risk/Trade | Stop Loss Range | Leverage Limit |
|---|---|---|---|
| BTC/ETH | 1.0% | 2-5% | 5x |
| Altcoins | 0.5% | 5-10% | 3x |
| Meme coins | 0.25% | 15-25% | 1x (spot only) |
| Forex majors | 1.5% | 30-100 pips | 10x |
| Gold (XAU) | 1.0% | $5-15 | 10x |
| Futures | 0.5% | 2-5% | 3x |

## Risk/Reward Calculation
```
Position A: Risk $50 to make $150 → R:R = 1:3 ✅
Position B: Risk $100 to make $100 → R:R = 1:1 ⚠️
Position C: Risk $50 to make $30 → R:R = 1:0.6 ❌ reject

Minimum acceptable R:R: 1:2 for swing trades, 1:1.5 for scalps
```

## Correlation Risk Matrix
```python
# Avoid trading these pairs simultaneously (compounds risk)
CORRELATED_PAIRS = {
    "EUR/USD": ["GBP/USD", "USD/CHF", "EUR/JPY"],
    "GBP/USD": ["EUR/USD", "USD/CHF"],
    "USD/JPY": ["USD/CHF", "Gold"],
    "Gold": ["USD/CHF", "DXY"],
    "BTC": ["ETH", "SOL", "most alts"],
}
```

## Daily Trading Rules
- Max trades per day: 5 (prevents overtrading)
- Max consecutive losses before stop: 3 (take a break)
- Daily loss limit: 5% of account (hard stop)
- Min trade interval: 5 minutes (no revenge trading)
- No trading 30 min before/after major news
- Review all trades at end of day

## Major News Events to Avoid
| Event | Impact | Timing |
|---|---|---|
| NFP (US Employment) | Extreme | 1st Friday, 13:30 UTC |
| FOMC Rate Decision | Extreme | 8 weeks, 19:00 UTC |
| CPI (US Inflation) | High | Monthly, 13:30 UTC |
| GDP (US) | High | Quarterly |
| Central Bank Speeches | Moderate | Various |
| Jobless Claims | Moderate | Weekly Thursday |
| Retail Sales | Moderate | Monthly |
| Consumer Confidence | Moderate | Monthly |

## Black Swan Protection
- Never go all-in on one position
- Always keep 10-20% in stablecoins/USD for opportunity
- Use stop losses on EVERY position (no exceptions)
- Consider portfolio hedge (e.g., put options on BTC)
- During extreme events, stop trading and observe
