# Meme Coin Sniping — Complete Reference

## What is Meme Coin Sniping?
Sniping is buying a newly launched token within seconds or minutes of its liquidity pool being created, before the broader market discovers it. The goal is to get in at the lowest possible price and sell to later buyers at a profit.

## Solana Meme Coin Ecosystem
- **PumpFun**: Launchpad where anyone can create a token for ~2 SOL. Token graduates to Raydium when market cap reaches ~$69K.
- **Raydium**: Main AMM DEX on Solana. Most meme coins get initial liquidity here.
- **Meteora**: Newer AMM with concentrated liquidity (higher capital efficiency).
- **Orca**: User-friendly DEX with some meme pairs.
- **Jupiter**: DEX aggregator — routes swaps across all Solana DEXs for best price.

## Sniping Pipeline

### Step 1: Discovery
- Poll PumpFun API for new tokens (websocket preferred)
- Monitor Raydium's new pool creation logs
- Scan Twitter/X for trending tokens (verify before buying!)
- Track DexScreener new pairs feed

### Step 2: Filtering
```
CRITICAL FILTERS (bypass if any fail):
  - Honeypot check:           Can you sell? (buy 0.001 SOL, try to sell)
  - Mint authority revoked:   ✅ must be revoked
  - Freeze authority:         ✅ must be revoked or null
  - LP liquidity locked:      ✅ must be locked (check LP unlock time)
  - Token ownership renounced: ✅ preferred
  
TIER 1 FILTERS:
  - Initial liquidity:        ≥ 5 SOL preferred
  - Holder count at launch:   ≥ 10 unique holders in first 5 min
  - Top-10 holder %:          < 30% (less whale risk)
  - Social presence:          Twitter, Telegram created before launch
  
TIER 2 FILTERS:
  - Contract verified:        ✅ on Solscan
  - No high-tax buy/sell:     buy + sell tax < 10% each
  - No blacklist:             token contract doesn't have blacklist function
  - Slippage test:            swap works with 25% slippage
```

### Step 3: Entry
```python
# Optimal entry parameters
entry_params = {
    "max_slippage": 25,           # bps (0.25% — high for meme)
    "compute_limit": 200_000,     # CU budget
    "compute_price": 0.01,        # SOL priority fee
    "amount": 0.1,                # SOL per snipe
    "use_jupiter": True,          # Route through aggregator
    "auto_approve": False,        # Never auto-approve — always check!
}
```

### Step 4: Exit Strategy
```
GREEN EXIT (profitable):
  +100% in < 1h:     sell 50%, trailing stop 15% on remainder
  +200% in < 4h:     sell 75%, let 25% ride
  +500% anytime:     sell 100%
  +1000% anytime:    you got lucky, sell everything

RED EXIT (loss):
  -25% from entry:   sell 50%
  -50% from entry:   sell 100% (stop loss)
  Rug detected:      sell immediately, accept loss

TIME STOP:
  No movement in 24h: sell 100% (capital efficiency)
```

## Rug Pull Detection Checklist
- [x] Honeypot test passed (can buy AND sell)
- [x] No mint function in contract
- [x] No freeze authority
- [x] LP tokens burned or locked > 6 months
- [x] Token creator doesn't hold > 10% of supply
- [x] Contract verified on Solscan/blockscout
- [x] No high buy/sell tax (> 15%)
- [x] Liquidity pool has > $10K initial liquidity
- [x] Not blacklisted by known scam detectors
- [x] Socials existed before launch

## Tools & APIs
- **Helius WebSocket**: real-time new token detection
- **Birdeye API**: token metadata, holders, top holders
- **DexScreener API**: new pairs, price charts
- **Jupiter API**: swap routing, price impact, quotes
- **Solscan API**: contract verification, holder analysis
- **RugCheck.xyz**: automated rug detection scoring
