# Meteora DLMM LP Research
*Date: 2026-04-04*

## Core Question: Is 1%/day (~365% APR) Real?

**Yes — but it's not a steady-state yield. It's episodic and requires active management.**

Documented real examples:
- SOL-USDC during high-volume periods: **~680% APR annualized** (1.04% fee/TVL in 24h)
- JUP token launch (Jan 2024): **~6%/day** ($10M fees, $164M TVL in a single day)
- Meme coin launches: documented cases of **50–100%/day** for a brief window
- TRUMP-USDC launch spike (Jan 2025): 0.1–0.7%/day (36–255% APR)

Steady-state realistic APR:
| Pool Type | Typical APR |
|---|---|
| Stable pairs | 5–30% |
| SOL-USDC, major liquid pairs | 30–200%+ (active management) |
| Volatile mid-caps | 50–500%+ |
| Meme launches | 500–several thousand% briefly |

---

## The "Short Volatility" Risk

Your friend is right — DLMM LPs are structurally **short gamma / short volatility**. More precisely:

- **Long theta**: time passing with price stable in range = fee income accrues
- **Short gamma**: large price moves = IL accelerates faster than fees compensate
- **Short vega**: higher volatility hurts you

vs. a standard AMM (Uniswap v2-style), the key difference:
- Standard AMM: always earns *some* fees regardless of price (active across full range)
- DLMM: earns **zero fees** once price exits your bin range. The position fully converts to the weaker token.

A 2x price move on a tight range = near-100% conversion to the depreciating token.
A meme coin that 5x-then-rugs = you caught the rug bag, having only earned fees during the narrow window.

**When does 1%/day justify the risk?**
Only if realized vol is low enough that price stays in range long enough for fees to exceed IL. The claim "1% a day while volatility is low" is actually the correct framing — the strategy only works in low-vol regimes.

---

## Pairs Worth Investigating

Best yield comes from:
1. **New token launches / Pump.fun migrations** — highest peak fees but near-total IL risk within 24–72h
2. **SOL-USDC during market surges** — more sustainable, manageable IL
3. **Meme coins mid-pump** (WIF, BONK, etc.) during meme season — high vol, but fees may compensate if you rebalance

---

## Data Sources & APIs

### Live Pool Data
- **Meteora App**: https://app.meteora.ag/pools — sort by 24h fee APR
- **Metlex.tools** — real-time high-APR pool discovery

### APIs
```
# Legacy pairs API (most useful for APR screening)
GET https://dlmm-api.meteora.ag/pair/all

# Returns per-pool fields:
# - apr (annualized)
# - fee_tvl_ratio.hour_24
# - fees.hour_24
# - liquidity (TVL)
# - trade_volume_24h

# New datapi (paginated, Swagger at /swagger-ui/)
GET https://dlmm.datapi.meteora.ag/pools
GET https://dlmm.datapi.meteora.ag/pools/{address}
GET https://dlmm.datapi.meteora.ag/stats/protocol_metrics
# Rate limit: 30 req/s
```

### Analytics Dashboards (Dune)
- Fee stats per pool: https://dune.com/kagren0/dlmm-fee-stats
- Fee/TVL ratios: https://dune.com/geeklad/meteora-dlmm-fee-to-tvl
- Pool overview: https://dune.com/gm365/dlmm-pools

### P&L Analysis
- GeekLad profit analysis tool: https://geeklad.github.io/meteora-profit-analysis/
  - Analyzes your wallet's actual DLMM net return (fees minus IL)

### DeFiLlama
- https://defillama.com/protocol/meteora-dlmm (TVL, fees)
- https://yields.llama.fi/pools (APY for tracked Meteora pools)

---

## Next Steps

- [ ] Pull `dlmm-api.meteora.ag/pair/all` and screen for consistent high fee/TVL pairs
- [ ] Build a simple screener: filter pools with 24h fee/TVL > 0.5% AND TVL > $100K (filters out tiny pools)
- [ ] Look at Dune data for which pairs *consistently* hit 1%/day vs which only spike on launch day
- [ ] Evaluate whether active rebalancing (moving bins as price moves) actually captures fees or just chases losses
