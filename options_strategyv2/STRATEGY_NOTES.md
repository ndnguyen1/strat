# Free Call + Dynamic Delta Hedge — Strategy Notes

## The Setup

- Receive a **free call option** (zero cost basis), ~4yr expiry, struck 20% above spot
- Run a dynamic short hedge against it to capture gamma scalp P&L
- Net position is always long delta (option delta always exceeds short)
- At expiry: collect option payoff on top of all hedge P&L

---

## How Gamma Scalping Works Here

Short size is driven by OTM% = (Strike − Spot) / Spot.

**The rule for gamma-positive hedging**: as price falls → reduce short (cover at lows). As price rises → increase short (sell at highs).

This means short must **decrease** as price falls (OTM% increases). Any zone where short increases as price falls is **anti-gamma** — it bleeds money on oscillations.

---

## Versions

### v1 — Single Tranche

| OTM% | Short |
|---|---|
| ITM | 60-D flat |
| 0–20% | 60-D → 50-D |
| 20–50% | 50-D → 0-D |
| >50% | 0-D |

Pure gamma scalp throughout. Simple, clean.

---

### v2 — Two Tranches (with upslope)

Adds a second tranche that fires in deep OTM:

| OTM% | Short |
|---|---|
| ITM | 60-D flat |
| 0–20% | 60-D → 50-D |
| 20–50% | 50-D → 0-D (T1) |
| 50–65% | 0-D → 20-D (T2 upslope) ⚠️ |
| 65–80% | 20-D → 0-D (T2 downslope) ✓ |
| >80% | 0-D |

**Problem with v2**: the upslope (50–65% OTM) is **anti-gamma**. Short increases as price falls, so oscillations in that zone lose money. It's a directional momentum bet on continued downside, not a hedge reinvigoration.

- T2 downslope (65–80%): genuine gamma scalp ✓
- T2 upslope (50–65%): anti-gamma, bleeds on oscillations ✗

v2 only outperforms v1 when ETH crashes hard and fast through 50–80% OTM without pausing (e.g. the Jan–Apr 2026 backtest).

---

### v4 — Pure Gamma T2 (downslope only)

Remove the upslope entirely. Gap zone 50–65%, step to 20-D at 65%, linear decay to 0 at 80%.

| OTM% | Short |
|---|---|
| ITM | 60-D flat |
| 0–20% | 60-D → 50-D |
| 20–50% | 50-D → 0-D (T1) |
| 50–65% | 0-D (gap) |
| 65–80% | 20-D → 0-D (T2 downslope only) ✓ |
| >80% | 0-D |

Small discontinuity at 65% OTM (0 → 20-D step). Every oscillation in T2 is now gamma-positive.

---

## Backtest Results (Jan 13 – Apr 13 2026, ETH -34%)

| | v1 | v2 | v4 |
|---|---|---|---|
| Hedge P&L ($) | +$249 | +$317 | +$287 |
| Total P&L (%) | +7.5% | +9.5% | +8.6% |

v2 wins here because ETH fell nearly straight from 20% OTM to >80% OTM — the upslope's directional short captured real crash P&L. v4 misses the 50–65% zone but still catches the downslope.

---

## Monte Carlo (n=200, S0=$2000, σ=0.75, T=1yr, μ=0)

| Metric | v1 | v2 | v4 |
|---|---|---|---|
| Mean P&L ($) | 440.82 | 439.60 | 440.49 |
| Median P&L ($) | 367.02 | 363.60 | 353.78 |
| Std P&L ($) | 378.31 | 371.92 | 376.75 |
| Mean P&L (%) | 22.0% | 22.0% | 22.0% |
| % paths positive | 98% | 98% | 98% |
| % paths > +10% | 80.5% | 83.0% | 82.5% |
| Worst P&L ($) | -55 | -79 | -63 |
| Best P&L ($) | 2770 | 2754 | 2770 |
| 5th pctile ($) | 50 | 50 | 50 |
| 95th pctile ($) | 1059 | 997 | 1045 |

**Key findings:**
- v4 is strictly better than v2 (worse worst case fixed: -$63 vs -$79; better upside tail)
- v4 vs v1 is a wash — same mean, same 5th pctile, v1 slightly better median
- Adding T2 in any form doesn't meaningfully increase expected value over v1
- T2's main benefit is directional crash coverage, not vol capture

---

## Key Concepts

**Why T2 upslope is anti-gamma:**
On the upslope (50–65% OTM), as price falls you add short at lower prices. When it bounces, you cover at higher prices — the opposite of buy low / sell high. Net loss on oscillations.

**When T2 makes money:**
1. Sustained directional crash through the zone (directional P&L from being short)
2. Oscillations on the downslope (65–80%) — genuine gamma scalp
3. Crash all the way past 80% then recover — you kept all the directional profit, 0 short by the time it bounces

**When T2 loses money:**
Price enters the upslope zone (50–65%) and oscillates without breaking through.

---

## Files

| File | Description |
|---|---|
| `strategy.ipynb` | v1 — single tranche baseline |
| `strategyv2.ipynb` | v2 — two tranches with upslope |
| `strategyv3.ipynb` | v3 — 1.5x option notional multiplier |
| `strategyv4.ipynb` | v4 — pure gamma T2 (downslope only) |
| `backtest_results_v2.png` | v1 vs v2 backtest charts |
| `backtest_results_v4.png` | v1 vs v2 vs v4 backtest charts |
| `monte_carlo_v2.png` | v2 MC charts |
| `monte_carlo_v3.png` | v3 MC charts |
| `monte_carlo_v4.png` | v1 vs v4 MC charts |
