"""
What happens to the managed ±2-3% strategy when SOL spikes?

Two effects pull in opposite directions:
  GOOD:  high-vol / trending days = more pool fees (more arb volume)
  BAD:   trending price = constant rebalancing, always selling your winners

Key mechanic: in a monotonic rally, price keeps hitting your upper bound.
Each time it does, you've converted all SOL → USDC, then rebalance back to 50/50
by buying SOL at a higher price. You're systematically selling the rally.

Scenarios modelled (all starting from SOL = $80):
  A) Slow grind: +150% over 90 days (~0.88%/day)
  B) Fast run:   +150% over 30 days (~2.9%/day)
  C) Parabolic:  +300% over 30 days (~4.8%/day) — SOL back to $320
  D) Pump+dump:  +100% in 15d, then -50% in 15d (back near start)
  E) Choppy:     ±5%/day random walk, flat trend (high vol, no direction)

Compare against: HODL 50/50 SOL+USDC from entry
"""

import math
import random

# ── Constants (same as other models) ──────────────────────────────────────────

POSITION       = 10_000
POOL_TVL       = 4_884_593
POOL_AVG_RANGE = 0.08
POOL_AVG_MULT  = 2 / (2 - 1/math.sqrt(1.08) - math.sqrt(0.92))
REBALANCE_COST = 10.0
BASE_SHARE     = POSITION / POOL_TVL
ENTRY_PRICE    = 80.17   # current SOL price

# Fee model: use mean ppm (spike days are high-vol = more fees)
FEE_PPM_MEAN   = 6.40e-6
AVG_CG_VOL     = 5.29e9   # avg CoinGecko daily SOL volume over last 6 months

# Scale CG volume by price ratio (volume roughly scales with price)
# At SOL=$232 avg daily vol was ~$7B; at $80 it's ~$2B → linear-ish scaling
def cg_vol_at_price(p):
    return AVG_CG_VOL * (p / 160)   # rough linear scale (160 = 6-month avg price)

def pool_fee_at_price(p):
    return cg_vol_at_price(p) * FEE_PPM_MEAN

# ── Math ───────────────────────────────────────────────────────────────────────

def concentration_mult(r):
    denom = 2 - 1/math.sqrt(1 + r) - math.sqrt(1 - r)
    return 2 / denom if denom > 0 else float("inf")

def effective_daily_fee(pool_fee, my_mult):
    return BASE_SHARE * (my_mult / POOL_AVG_MULT) * pool_fee

def il_pct(price_ratio):
    r = price_ratio
    return 2 * math.sqrt(r) / (1 + r) - 1

def hodl_value(current_price, entry_price=ENTRY_PRICE):
    """50/50 SOL+USDC hodl from entry."""
    sol_amt  = (POSITION / 2) / entry_price
    usdc_amt = POSITION / 2
    return sol_amt * current_price + usdc_amt

# ── Managed strategy runner ────────────────────────────────────────────────────

def run_managed(price_path, range_pct):
    """
    price_path: list of daily close prices
    Returns summary dict.
    """
    my_mult = concentration_mult(range_pct)

    centre      = price_path[0]
    pa, pb      = centre * (1 - range_pct), centre * (1 + range_pct)
    prev_centre = centre

    cum_fees   = 0.0
    cum_il     = 0.0
    rebal_cost = 0.0
    n_rebal    = 0
    in_days    = 0
    rows       = []

    for price in price_path:
        pool_fee = pool_fee_at_price(price)
        in_range = pa <= price <= pb
        fee = effective_daily_fee(pool_fee, my_mult) if in_range else 0.0
        cum_fees += fee
        in_days  += int(in_range)

        if not in_range:
            boundary = pb if price > pb else pa
            cum_il     += il_pct(boundary / prev_centre) * POSITION
            cum_fees   -= REBALANCE_COST
            rebal_cost += REBALANCE_COST
            n_rebal    += 1
            prev_centre = price
            centre      = price
            pa = centre * (1 - range_pct)
            pb = centre * (1 + range_pct)

        rows.append({
            "price":    price,
            "in_range": in_range,
            "fee":      fee,
            "cum_fees": cum_fees,
            "cum_il":   cum_il,
            "net_pnl":  cum_fees + cum_il,
        })

    final      = rows[-1]
    hodl       = hodl_value(price_path[-1])
    hodl_pnl   = hodl - POSITION
    lp_vs_hodl = final["net_pnl"] - hodl_pnl

    return {
        "fees":       final["cum_fees"],
        "il":         final["cum_il"],
        "rebal_cost": rebal_cost,
        "n_rebal":    n_rebal,
        "net_pnl":    final["net_pnl"],
        "net_pct":    final["net_pnl"] / POSITION * 100,
        "hodl_pnl":   hodl_pnl,
        "hodl_pct":   hodl_pnl / POSITION * 100,
        "lp_vs_hodl": lp_vs_hodl,  # positive = LP better than hodl
        "in_days":    in_days,
        "n_days":     len(price_path),
        "exit_price": price_path[-1],
    }

# ── Price path generators ──────────────────────────────────────────────────────

def grind(start, end, n_days):
    """Smooth exponential grind from start to end over n_days."""
    r = (end / start) ** (1 / n_days)
    p = start
    path = []
    for _ in range(n_days):
        p *= r
        path.append(p)
    return path

def pump_dump(start, peak_mult, n_up, n_down):
    """Pump then dump symmetrically."""
    up   = grind(start, start * peak_mult, n_up)
    down = grind(up[-1], start * (peak_mult**0.5) * 0.7, n_down)  # dumps to ~50% of peak
    return up + down

def choppy(start, daily_vol_pct, n_days, seed=42):
    """Random walk with ~zero drift but high daily vol."""
    random.seed(seed)
    p = start
    path = []
    for _ in range(n_days):
        chg = random.gauss(0, daily_vol_pct)
        p = max(p * (1 + chg), 1)
        path.append(p)
    return path

# ── Print ──────────────────────────────────────────────────────────────────────

RANGES = [0.01, 0.02, 0.03, 0.05, 0.10]

def print_scenario(name, path, note=""):
    entry   = ENTRY_PRICE
    exit_p  = path[-1]
    sol_chg = (exit_p / entry - 1) * 100
    n       = len(path)
    hodl    = hodl_value(exit_p)

    print(f"\n{'='*110}")
    print(f"  {name}  ({n} days)")
    print(f"  SOL: ${entry:.2f} → ${exit_p:.2f} ({sol_chg:+.1f}%)")
    print(f"  HODL 50/50 P&L: ${hodl - POSITION:+,.0f} ({(hodl/POSITION-1)*100:+.1f}%)")
    if note:
        print(f"  Note: {note}")
    print(f"{'─'*110}")
    print(f"  {'Range':<8} {'Mult':>7} {'Fees':>9} {'IL':>9} {'RC':>6} "
          f"{'Net P&L':>10} {'Net%':>7} {'vs HODL':>10} {'Rebals':>7} {'In-rng':>8}")
    print(f"  {'─'*100}")

    for r in RANGES:
        res = run_managed(path, r)
        m   = concentration_mult(r)
        vs  = res["lp_vs_hodl"]
        vs_str = f"${vs:>+9,.0f}"
        marker = " ◄ LP wins" if vs > 0 else ""
        print(
            f"  ±{r*100:>4.1f}%  {m:>7.1f}×  "
            f"${res['fees']:>8,.0f}  ${res['il']:>+8,.0f}  "
            f"${res['rebal_cost']:>4,.0f}  "
            f"${res['net_pnl']:>+9,.0f}  {res['net_pct']:>6.1f}%  "
            f"{vs_str}  {res['n_rebal']:>5}×  "
            f"{res['in_days']:>3}/{res['n_days']}"
            f"{marker}"
        )

def print_rebal_mechanics(name, path, range_pct):
    """Show the rebalance event detail for one scenario."""
    my_mult = concentration_mult(range_pct)
    centre  = path[0]
    pa, pb  = centre * (1 - range_pct), centre * (1 + range_pct)
    prev_c  = centre
    cum_fees = 0.0
    cum_il   = 0.0
    events   = []

    for i, price in enumerate(path):
        pool_fee = pool_fee_at_price(price)
        in_range = pa <= price <= pb
        fee      = effective_daily_fee(pool_fee, my_mult) if in_range else 0.0
        cum_fees += fee
        if not in_range:
            boundary = pb if price > pb else pa
            il_event = il_pct(boundary / prev_c) * POSITION
            cum_il  += il_event
            cum_fees -= REBALANCE_COST
            events.append({
                "day": i+1, "price": price, "from": prev_c,
                "boundary": boundary, "il": il_event, "cum_il": cum_il,
                "cum_fees": cum_fees,
            })
            prev_c  = price
            centre  = price
            pa = centre * (1 - range_pct)
            pb = centre * (1 + range_pct)

    print(f"\n{'─'*90}")
    print(f"  Rebalance events — {name} at ±{range_pct*100:.0f}% (first 15 shown)")
    print(f"{'─'*90}")
    print(f"  {'Day':>4} {'Price':>8} {'From':>8} {'Boundary':>9} "
          f"{'IL/event':>10} {'CumIL':>10} {'CumFees':>10}")
    print(f"  {'-'*80}")
    for e in events[:15]:
        print(f"  {e['day']:>4}  ${e['price']:>7.2f}  ${e['from']:>7.2f}  "
              f"${e['boundary']:>8.2f}  ${e['il']:>+9.2f}  "
              f"${e['cum_il']:>+9.2f}  ${e['cum_fees']:>+9.2f}")
    if len(events) > 15:
        print(f"  ... ({len(events)-15} more events)")
    print(f"  Total rebalances: {len(events)}")

# ── Main ───────────────────────────────────────────────────────────────────────

print("SOL SPIKE ANALYSIS — managed rebalancing strategy")
print(f"Entry: ${ENTRY_PRICE:.2f} | Position: ${POSITION:,} | Fee model: mean ppm (includes spikes)")

# Scenario A: slow grind +150% over 90 days (SOL $80 → $200)
path_A = grind(ENTRY_PRICE, ENTRY_PRICE * 2.5, 90)
print_scenario("A) SLOW GRIND  +150% over 90 days  (SOL $80 → $200)", path_A,
               "~0.9%/day, like a sustained bull run")

# Scenario B: fast run +150% over 30 days (SOL $80 → $200)
path_B = grind(ENTRY_PRICE, ENTRY_PRICE * 2.5, 30)
print_scenario("B) FAST RUN    +150% over 30 days  (SOL $80 → $200)", path_B,
               "~3%/day, aggressive rally")

# Scenario C: parabolic +300% over 30 days (SOL $80 → $320)
path_C = grind(ENTRY_PRICE, ENTRY_PRICE * 5.0, 30)
print_scenario("C) PARABOLIC   +300% over 30 days  (SOL $80 → $320)", path_C,
               "SOL back to ATH territory, extreme rebalancing pressure")

# Scenario D: pump+dump +150% then partial dump
path_D = pump_dump(ENTRY_PRICE, 2.5, 30, 30)
print_scenario(f"D) PUMP+DUMP   +150% then partial dump over 60 days  (exit ~${path_D[-1]:.0f})", path_D,
               "Rally then retrace — tests whether you capture gains on the way down")

# Scenario E: choppy, zero drift, ±5%/day
path_E = choppy(ENTRY_PRICE, 0.05, 90)
print_scenario(f"E) CHOPPY      ±5%/day random walk, 90 days  (exit ~${path_E[-1]:.0f})", path_E,
               "High vol, no trend — ideal for short-vol LP strategies")

# Scenario F: slow grind down -50% (continuation of current trend)
path_F = grind(ENTRY_PRICE, ENTRY_PRICE * 0.5, 90)
print_scenario("F) BEAR CONT.  -50% over 90 days  (SOL $80 → $40)", path_F,
               "Current downtrend continues — stress test")

# ── Rebalance mechanics detail for scenario B (fast run, ±2%) ──────────────────

print(f"\n\n{'='*110}")
print("REBALANCE MECHANICS DETAIL")
print_rebal_mechanics("Fast Run +150%/30d", path_B, 0.02)
print_rebal_mechanics("Fast Run +150%/30d", path_B, 0.05)
print_rebal_mechanics("Slow Grind +150%/90d", path_A, 0.02)
print_rebal_mechanics("Pump+Dump", path_D, 0.02)

# ── Summary comparison ─────────────────────────────────────────────────────────

print(f"\n\n{'='*110}")
print("SUMMARY: LP ±2% managed vs HODL 50/50  (+ = LP beats hodl, - = hodl beats LP)")
print(f"{'─'*80}")
print(f"  {'Scenario':<35} {'LP Net P&L':>12} {'HODL P&L':>12} {'LP vs HODL':>12} {'Rebals':>8}")
print(f"  {'─'*75}")
scenarios = [
    ("A) Slow grind +150%/90d", path_A),
    ("B) Fast run +150%/30d",   path_B),
    ("C) Parabolic +300%/30d",  path_C),
    ("D) Pump+dump",            path_D),
    ("E) Choppy ±5%/day/90d",   path_E),
    ("F) Bear cont. -50%/90d",  path_F),
]
for label, path in scenarios:
    res = run_managed(path, 0.02)
    mark = " ◄ LP" if res["lp_vs_hodl"] > 0 else " ◄ HODL"
    print(f"  {label:<35} ${res['net_pnl']:>+10,.0f}  ${res['hodl_pnl']:>+10,.0f}  "
          f"${res['lp_vs_hodl']:>+10,.0f}  {res['n_rebal']:>6}×{mark}")
