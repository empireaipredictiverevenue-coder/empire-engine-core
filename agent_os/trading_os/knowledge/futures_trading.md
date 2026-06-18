# Futures / Perpetuals Trading Reference

## Perpetual Swaps vs Traditional Futures

### Perpetual Swaps (Crypto)
- No expiry date — hold indefinitely
- Funding rate mechanism keeps price close to spot
- 8h funding intervals (some exchanges use 1h)
- Funding positive: longs pay shorts (bullish sentiment)
- Funding negative: shorts pay longs (bearish sentiment)
- Leverage: 1x-125x depending on exchange and asset

### Traditional Futures (Forex/Commodities)
- Fixed expiry date (quarterly: Mar/Jun/Sep/Dec)
- Contract rollover required before expiry
- Contango: futures price > spot price (normal)
- Backwardation: futures price < spot price (rare, usually commodity shortages)
- Leverage: varies by broker and asset class

## Funding Rate Analysis
```python
FUNDING_SIGNAL = {
    "> 0.01%": "Strong bullish sentiment, potential top",
    "0.005% - 0.01%": "Moderate bullish, trend likely intact",
    "0% - 0.005%": "Neutral",
    "-0.005% - 0%": "Moderate bearish",
    "< -0.01%": "Strong bearish sentiment, potential bottom"
}
```
- Sustained high funding (>0.1%) for 24h+ = crowded long = crash risk
- Negative funding during uptrend = healthy, room to run
- Funding rate extremes are often contrarian indicators

## Open Interest Analysis
- Rising OI + rising price = new money entering, trend confirmed
- Rising OI + falling price = new shorts, bearish momentum
- Falling OI + rising price = shorts covering, may be a bounce
- Falling OI + falling price = longs exiting, capitulation
- OI spike + price consolidation = explosive move imminent

## Liquidation Tracking
### Long Liquidation Cascade
```
Price drops → leveraged longs get margin called
  → forced sell orders → price drops more
  → more longs liquidated → cascade continues
```
### Short Squeeze
```
Price rises → leveraged shorts get margin called
  → forced buy orders → price rises more
  → more shorts liquidated → squeeze continues
```

### Liquidation Zones
- Major liquidation clusters act as price magnets
- Price often sweeps through liquidation zones before reversing
- Check liquidation heatmap for entry/exit levels
- Largest liquidations happen at round numbers and key S/R

## Position Sizing for Futures
```python
# With leverage
position_size_usd = account_balance * risk_percent / (stop_loss_percent / leverage)

# Example
# Account: $5,000, Risk: 2%, Stop: 5%, Leverage: 10x
# Size = 5000 * 0.02 / (0.05 / 10) = 100 / 0.005 = $20,000

# Collateral required = $20,000 / 10 = $2,000
# Risk in USD = $20,000 * 0.05 = $1,000 (20% of account — too high!)
# → Reduce leverage or position size
```

## Crypto Futures Specific
| Exchange | Max Leverage | Funding Interval | Notable Pairs |
|---|---|---|---|
| Binance | 125x | 8h | BTC, ETH, SOL, 200+ pairs |
| Bybit | 100x | 8h | BTC, ETH, SOL, alts |
| OKX | 100x | 8h | BTC, ETH, most alts |
| dYdX | 20x | 1h | BTC, ETH, SOL (on-chain) |
| Hyperliquid | 50x | 1h | BTC, ETH, SOL + perps |
| Jupiter Perps | 100x | 1h | Via Solana (on-chain) |

## Risk Management for Futures
- **Never use max leverage** — 3-5x is aggressive enough
- **Always set stop loss** — futures can go to 0 instantly
- **Monitor funding rates** hourly — high funding eats PnL
- **Reduce size at ATH/ATL** — highest volatility zones
- **Don't hold through funding settlement** — especially high rates
- **Track liquidation price** — know exactly where you get wiped
