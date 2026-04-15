# Free Call Option — Delta Hedge Strategy

## Overview

A machine provides free 4-year American style call options on ETH. The strategy monetises these through delta hedging with short perpetual futures, capturing realized volatility as P&L with zero theta cost.

---

## Strategy Rules

1. At initiation, receive a free call option struck **10% OTM** from current ETH spot
2. Model the option as **1-year tenor, IV=60%** for all delta calculations regardless of calendar time
3. Calculate delta daily using Black-Scholes with those parameters
4. Maintain a **short perp position = delta × notional** (rebalance daily)
5. If ETH goes down: do nothing to the option, just rebalance the short perp as delta shrinks
6. If the call reaches **20% ITM** (S/K ≥ 1.20): exercise, capture intrinsic value, receive a new free call struck 10% OTM from current spot, reset the delta hedge
7. There is no downside reset — hold the option indefinitely as it goes OTM
8. Pay perp funding daily on the short position

---

## P&L Mechanics

- **Core engine:** gamma scalping — daily delta rebalancing captures realized vol
- **Upside reset:** locks in intrinsic value and reloads gamma from near-ATM
- **Downside:** short perps earn as ETH falls, option goes OTM but cost basis is zero
- **Only cost:** perp funding rate on the short position

```
Daily P&L ≈ ½ × Γ × (dS)²  −  funding_rate × |short_notional| × dt
```

Since there is no premium paid, there is no theta drain. Any positive realized vol generates positive gamma P&L.

---

## Key Parameters

| Parameter | Value |
|-----------|-------|
| Strike at issuance | 10% OTM |
| Model tenor (BS) | 1 year (fixed, never ages) |
| Model IV (BS) | 60% |
| Upside reset trigger | S/K ≥ 1.20 (20% ITM) |
| Downside reset | None |
| Perp funding (model) | 10% annualized (flat) |
| Rebalance frequency | Daily |

---

## Initial Delta (at rebond, Apr 2026)

- Spot: $2,242 | Strike: $2,466
- BS Delta ≈ **0.56** → short 0.56 ETH equiv in perps per option

---

## Historical Backtest — 6 Months (Oct 2025 – Apr 2026)

ETH fell **−50%** over the period ($4,454 → $2,242). Zero upside resets triggered.

| Metric | Value |
|--------|-------|
| Cash P&L (realised) | +$960 |
| Option mark (final) | +$87 |
| Total P&L | **+$1,047 (+23.5%)** |
| Funding paid | −$43 |
| Upside resets | 0 |
| Final delta | ~0.12 (option deeply OTM) |

The strategy profited entirely through short perp gains as ETH fell. By April 2026 the option was deeply OTM (strike $4,900 vs spot $2,242) with delta ~0.12 — minimal hedge remaining, option worth $87 as a lottery ticket.

---

## Monte Carlo — Rebond Now (Apr 2026)

Fresh option: spot $2,242, strike $2,466. 200 GBM paths, 1-year horizon, σ_sim=80%, σ_hedge=60%, funding=10%.

| Metric | Value |
|--------|-------|
| Mean P&L | **+$1,102 (+49%)** |
| Median P&L | +$931 (+42%) |
| 5th percentile | +$556 |
| 95th percentile | +$2,427 |
| % profitable | **100%** |
| Avg funding paid | $98 |
| Avg resets | 1.2 |
| Max resets (single path) | 6 |

**P&L by ETH outcome:**

| ETH 1Y Return | Paths | Avg P&L |
|---------------|-------|---------|
| < −50% | 60 | +$690 |
| −50% to −25% | 37 | +$842 |
| −25% to 0% | 30 | +$894 |
| 0% to +25% | 23 | +$1,192 |
| +25% to +50% | 17 | +$1,447 |
| +50% to +100% | 13 | +$1,748 |
| > +100% | 20 | +$2,315 |

---

## Vol Sensitivity Sweep

200 paths per cell. σ_sim (realized) vs σ_hedge (model IV).

**Mean P&L ($):**

| σ_sim \ σ_hedge | 40% | 60% | 80% |
|-----------------|-----|-----|-----|
| 20% | +226 | +380 | +539 |
| 40% | +426 | +567 | +722 |
| 60% | +686 | +812 | +958 |
| 80% | +1,012 | +1,124 | +1,262 |
| 100% | +1,380 | +1,474 | +1,599 |
| 120% | +1,814 | +1,891 | +2,006 |

**Strategy is profitable at all tested vol combinations.** Break-even is not reached within the tested range — even at 20% realized vol vs 40% hedge vol, P&L is positive because the option is free (no theta cost to offset gamma).

---

## Why Always Profitable (and What's Missing)

**Theoretically sound:** with free options, theta = 0. Gamma P&L is always positive for any realized vol > 0. Funding is the only cost and is small relative to gamma earned.

**What the model does not capture:**

1. **Transaction costs / slippage** on 365 daily perp rebalances — could erode 30-50% of gamma P&L in low-vol environments
2. **Funding rate stress** — in ETH bull markets, short perp funding has hit 50-100%+ annualized. Our flat 10% is optimistic in those scenarios
3. **T=1 perpetual assumption** — we never let the option age; in reality a 4-year option loses time value over its life
4. **Gap risk** — GBM has no jumps; a 30% overnight crash leaves the delta hedge badly wrong
5. **Rebond costs** — any fee or slippage on the exercise + re-issuance changes the economics

---

## Files

```
options_backtest/
├── strategy.ipynb     # Full notebook: backtest + Monte Carlo + vol sweep
├── backtest.py        # Standalone 6-month historical backtest
├── monte_carlo.py     # Standalone 200-path Monte Carlo
├── STRATEGY.md        # This file
└── venv/              # Python venv (numpy, pandas, scipy, matplotlib, jupyter)
```

To run the notebook:
```bash
source options_backtest/venv/bin/activate
jupyter notebook options_backtest/strategy.ipynb
```
