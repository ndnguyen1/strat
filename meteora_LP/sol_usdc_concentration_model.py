"""
SOL-USDC: Can we hit 1%/day by concentrating liquidity?

In a DLMM/v3 pool, concentrating into a tighter range amplifies your share of pool fees
because your liquidity per dollar is higher at the active tick. But tighter range =
more days out of range = fewer days earning, and higher IL when you rebalance.

Key formula — concentration multiplier vs pool average:
    mult(r) = 2 / (2 - 1/sqrt(1+r) - sqrt(1-r))   where r = half-range fraction

This tells you: relative to the pool average LP, how much more fee-per-dollar you earn.
If pool avg is ±8% (mult=25.5x) and you set ±2% (mult=100.7x), you earn
100.7/25.5 = 3.95x more fees per dollar — but only on days price stays in range.

Two strategies modelled:
  Static:  set range once at entry, never adjust
  Managed: rebalance to re-centre range whenever price closes outside it
           (rebalance cost = 0.1% pool fee on repositioning swap = $10 per event)

Pool: SOL-USDC 0.1% fee (bin_step=10), TVL ~$4.88M
Pool avg concentration assumed: ±8% range → 25.5x multiplier
$10K position, 14-day window (Mar 21 – Apr 3 2026)
"""

import math

# ── Constants ─────────────────────────────────────────────────────────────────

POSITION      = 10_000
POOL_TVL      = 4_884_593
POOL_AVG_RANGE = 0.08          # assumed pool average LP range (±8%)
REBALANCE_COST = 10.0          # USD per rebalance event (0.1% fee on $10K swap)
ENTRY_PRICE   = 89.82          # SOL/USDC at Mar 21 open

# 0.1% SOL-USDC pool: daily fees (USD)
daily_fees = [
    ("2026-03-21", 87.52,   8_647.42),
    ("2026-03-22", 86.16,  15_958.73),
    ("2026-03-23", 91.45,  41_938.81),
    ("2026-03-24", 90.80,  20_915.53),
    ("2026-03-25", 91.67,  12_940.20),
    ("2026-03-26", 86.47,  12_214.72),
    ("2026-03-27", 83.08,  10_073.46),
    ("2026-03-28", 82.03,   6_628.38),
    ("2026-03-29", 81.37,   7_322.19),
    ("2026-03-30", 82.49,  17_012.27),
    ("2026-03-31", 83.15,  21_070.85),
    ("2026-04-01", 81.18, 108_053.22),
    ("2026-04-02", 78.94,  14_374.34),
    ("2026-04-03", 80.40,   8_886.75),
]

# ── Core math ─────────────────────────────────────────────────────────────────

def concentration_mult(r):
    """Capital efficiency multiplier for ±r range vs full range."""
    denom = 2 - 1/math.sqrt(1 + r) - math.sqrt(1 - r)
    return 2 / denom if denom > 0 else float('inf')

def il_pct(price_ratio):
    """Standard concentrated LP IL vs holding 50/50, for price ratio p1/p0."""
    r = price_ratio
    return 2*math.sqrt(r)/(1+r) - 1   # always ≤ 0

POOL_AVG_MULT = concentration_mult(POOL_AVG_RANGE)
BASE_SHARE    = POSITION / POOL_TVL   # naive LP share without concentration

def effective_daily_fee(pool_fee_usd, my_mult):
    """Fee income per day when in range, given our concentration multiplier."""
    rel = my_mult / POOL_AVG_MULT
    return BASE_SHARE * rel * pool_fee_usd

# ── Static model (no rebalancing) ─────────────────────────────────────────────

def run_static(range_pct):
    pa = ENTRY_PRICE * (1 - range_pct)
    pb = ENTRY_PRICE * (1 + range_pct)
    my_mult = concentration_mult(range_pct)

    cum_fees = 0.0
    in_range_days = 0
    rows = []
    for date, sol_close, pool_fee in daily_fees:
        in_range = pa <= sol_close <= pb
        fee = effective_daily_fee(pool_fee, my_mult) if in_range else 0.0
        cum_fees += fee
        price_ratio = sol_close / ENTRY_PRICE
        il_dollar = il_pct(price_ratio) * POSITION
        in_range_days += int(in_range)
        rows.append({
            "date": date, "price": sol_close, "in_range": in_range,
            "fee": fee, "cum_fees": cum_fees,
            "il": il_dollar, "net_pnl": cum_fees + il_dollar,
        })
    return rows

# ── Managed model (re-centre on exit) ─────────────────────────────────────────

def run_managed(range_pct):
    """
    Range is re-centred at each day's close whenever price moves outside it.
    Cost per rebalance = REBALANCE_COST.
    """
    my_mult  = concentration_mult(range_pct)
    centre   = ENTRY_PRICE
    pa, pb   = centre * (1-range_pct), centre * (1+range_pct)

    cum_fees      = 0.0
    total_rebal   = 0
    rebal_cost    = 0.0
    cum_il        = 0.0
    prev_centre   = ENTRY_PRICE
    rows          = []

    for date, sol_close, pool_fee in daily_fees:
        in_range = pa <= sol_close <= pb
        fee = effective_daily_fee(pool_fee, my_mult) if in_range else 0.0
        cum_fees += fee

        if not in_range:
            # Rebalance: recenter at today's close
            # IL is realised at the boundary that was breached
            boundary = pb if sol_close > pb else pa
            il_at_boundary = il_pct(boundary / prev_centre) * POSITION
            cum_il  += il_at_boundary
            cum_fees -= REBALANCE_COST   # rebalance cost
            rebal_cost += REBALANCE_COST
            total_rebal += 1
            # Reset
            prev_centre = sol_close
            centre      = sol_close
            pa          = centre * (1-range_pct)
            pb          = centre * (1+range_pct)

        rows.append({
            "date": date, "price": sol_close, "in_range": in_range,
            "fee": fee, "cum_fees": cum_fees,
            "il": cum_il, "net_pnl": cum_fees + cum_il,
            "rebal_this_day": not in_range,
        })

    return rows, total_rebal, rebal_cost

# ── Print static summary table ─────────────────────────────────────────────────

def print_static_summary():
    ranges = [0.01, 0.02, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20]

    print(f"\n{'='*100}")
    print(f"STATIC POSITION — range set once at entry ${ENTRY_PRICE:.2f}, never adjusted")
    print(f"Pool avg assumed ±{POOL_AVG_RANGE*100:.0f}% (mult {POOL_AVG_MULT:.1f}x)  |  "
          f"Base LP share: {BASE_SHARE*100:.4f}%  |  14-day avg pool fees: "
          f"${sum(r[2] for r in daily_fees)/len(daily_fees):,.0f}/day")
    print(f"{'─'*100}")
    print(f"{'Range':<8} {'Mult':>7} {'Fee$/day':>9} {'Fee%/day':>9} "
          f"{'Days in':>8} {'14d Fees':>10} {'IL':>10} {'Net P&L':>10}")
    print(f"{'─'*100}")
    for r in ranges:
        rows = run_static(r)
        m    = concentration_mult(r)
        f    = rows[-1]
        in_r = sum(1 for d in rows if d["in_range"])
        avg_fee_per_day   = f["cum_fees"] / 14
        avg_fee_pct       = avg_fee_per_day / POSITION * 100
        in_range_fee_rate = f["cum_fees"] / in_r / POSITION * 100 if in_r else 0
        flag = " ◄ 1%/day avg" if avg_fee_pct >= 1.0 else ""
        flag2 = " ◄ 1%/day in-range" if in_range_fee_rate >= 1.0 and not flag else ""
        print(
            f"  ±{r*100:>4.1f}%  {m:>7.1f}x  ${avg_fee_per_day:>7,.1f}/d  "
            f"{avg_fee_pct:>7.3f}%    {in_r:>2}/14  "
            f"${f['cum_fees']:>8,.0f}  ${f['il']:>+9,.0f}  ${f['net_pnl']:>+9,.0f}"
            f"{flag}{flag2}"
        )

    print(f"\n  Note: IL column shows unrealised IL at exit. Static position holds till day 14.")
    print(f"  'Days in' = days where close is inside original range.")

# ── Day-by-day table for key scenario ─────────────────────────────────────────

def print_static_detail(range_pct):
    rows = run_static(range_pct)
    m    = concentration_mult(range_pct)
    pa   = ENTRY_PRICE * (1 - range_pct)
    pb   = ENTRY_PRICE * (1 + range_pct)
    lp_fee_share = BASE_SHARE * (m / POOL_AVG_MULT) * 100

    print(f"\n{'─'*95}")
    print(f"  Static ±{range_pct*100:.0f}%  [{pa:.2f}–{pb:.2f}]  "
          f"mult={m:.1f}x  effective fee share={lp_fee_share:.4f}%")
    print(f"{'─'*95}")
    print(f"  {'Date':<12} {'SOL':>7} {'InRng':>6} {'DayFee':>9} {'Fee%/day':>9} {'CumFees':>9} {'IL':>10} {'NetP&L':>10}")
    print(f"  {'-'*90}")
    for d in rows:
        ir  = "Y" if d["in_range"] else "N"
        pct = d["fee"]/POSITION*100
        print(f"  {d['date']:<12} ${d['price']:>6.2f} {ir:>6} "
              f"${d['fee']:>8,.1f}  {pct:>7.3f}% "
              f"${d['cum_fees']:>8,.0f} ${d['il']:>+9,.0f} ${d['net_pnl']:>+9,.0f}")
    f = rows[-1]
    print(f"\n  Total fees: ${f['cum_fees']:,.2f}  |  IL: ${f['il']:+,.2f}  "
          f"|  Net: ${f['net_pnl']:+,.2f}  |  "
          f"In-range: {sum(1 for d in rows if d['in_range'])}/14")

# ── Managed vs static comparison ──────────────────────────────────────────────

def print_managed_comparison():
    ranges = [0.01, 0.02, 0.03, 0.05, 0.08, 0.10, 0.15]

    print(f"\n\n{'='*100}")
    print(f"STATIC vs MANAGED COMPARISON (managed = rebalance on exit, ${REBALANCE_COST:.0f}/event)")
    print(f"{'─'*100}")
    print(f"{'Range':<8}  {'──── STATIC ────':^32}  {'──── MANAGED ────':^38}")
    print(f"{'':8}  {'Fees':>9} {'IL':>9} {'Net':>9}   "
          f"{'Fees':>9} {'IL':>9} {'Rebals':>7} {'Net':>9}")
    print(f"{'─'*100}")

    for r in ranges:
        s_rows = run_static(r)
        m_rows, n_rebal, rc = run_managed(r)
        sf = s_rows[-1]
        mf = m_rows[-1]
        flag = " ◄" if mf["net_pnl"] >= 100 else ""
        print(
            f"  ±{r*100:>4.1f}%   "
            f"${sf['cum_fees']:>8,.0f} ${sf['il']:>+8,.0f} ${sf['net_pnl']:>+8,.0f}   "
            f"${mf['cum_fees']:>8,.0f} ${mf['il']:>+8,.0f}  {n_rebal:>5}x  ${mf['net_pnl']:>+8,.0f}"
            f"{flag}"
        )

    print(f"\n  Managed IL is realised at each range boundary (smaller, not full path IL)")
    print(f"  Managed rebalances reset the IL clock — each period starts fresh")

# ── 1%/day threshold analysis ─────────────────────────────────────────────────

def print_threshold_analysis():
    print(f"\n\n{'='*100}")
    print(f"WHAT RANGE IS NEEDED TO AVERAGE 1%/DAY?")
    print(f"{'─'*100}")

    # Target: $100/day = 1% of $10K
    TARGET = POSITION * 0.01

    print(f"\n  1%/day = ${TARGET:.0f}/day on ${POSITION:,.0f}")
    print(f"\n  Daily pool fees ranged from ${min(r[2] for r in daily_fees):,.0f} to "
          f"${max(r[2] for r in daily_fees):,.0f}")
    print(f"  Median: ${sorted(r[2] for r in daily_fees)[7]:,.0f}  |  "
          f"Mean: ${sum(r[2] for r in daily_fees)/14:,.0f}")
    print(f"\n  To hit ${TARGET:.0f}/day when in range, with pool avg ±{POOL_AVG_RANGE*100:.0f}% (mult {POOL_AVG_MULT:.1f}x):\n")
    print(f"  {'Range':<10} {'Mult':>8} {'In-range $/day':>16} {'In-range %/day':>16} "
          f"{'Days hit >1%':>14} {'On median day':>15}")
    print(f"  {'-'*82}")

    median_fees = sorted(r[2] for r in daily_fees)[7]

    for r in [0.01, 0.02, 0.03, 0.05, 0.08, 0.10]:
        m = concentration_mult(r)
        pa = ENTRY_PRICE * (1-r)
        pb = ENTRY_PRICE * (1+r)
        in_range_days = sum(1 for _, p, _ in daily_fees if pa <= p <= pb)

        # Fee per in-range day
        in_range_fees = [effective_daily_fee(f, m) for _, p, f in daily_fees if pa <= p <= pb]
        avg_inrange_fee = sum(in_range_fees)/len(in_range_fees) if in_range_fees else 0
        days_over_target = sum(1 for x in in_range_fees if x >= TARGET)
        median_fee = effective_daily_fee(median_fees, m) if in_range_days > 0 else 0

        print(f"  ±{r*100:>4.1f}%      {m:>6.0f}x  ${avg_inrange_fee:>13,.1f}    "
              f"{avg_inrange_fee/POSITION*100:>13.3f}%    "
              f"{days_over_target:>5}/{in_range_days} in-rng  "
              f"${median_fee:>7.1f}/d {'✓' if median_fee >= TARGET else '✗'}")

    print(f"\n  Key insight: on 'average' days ({sorted(r[2] for r in daily_fees)[7]:,.0f} pool fees/day),")
    for r in [0.02, 0.03, 0.05]:
        m = concentration_mult(r)
        median_fee = effective_daily_fee(median_fees, m)
        print(f"    ±{r*100:.0f}% range earns ${median_fee:.1f}/day ({median_fee/POSITION*100:.3f}%/day)")
    print(f"\n  Apr 1 was a $108K fee day. On such days:")
    for r in [0.02, 0.03, 0.05]:
        m = concentration_mult(r)
        big_fee = effective_daily_fee(108053.22, m)
        print(f"    ±{r*100:.0f}% range earns ${big_fee:.1f}/day ({big_fee/POSITION*100:.2f}%/day)")

# ── Main ──────────────────────────────────────────────────────────────────────

print("SOL-USDC Concentration Model — targeting 1%/day")
print(f"Pool: 0.1% fee, TVL ${POOL_TVL:,.0f}  |  Entry: ${ENTRY_PRICE}  |  Position: ${POSITION:,}")
print(f"Pool avg concentration: ±{POOL_AVG_RANGE*100:.0f}% → {POOL_AVG_MULT:.1f}x multiplier (assumption)")

print_static_summary()
print_static_detail(0.02)   # ±2% — the interesting target range
print_static_detail(0.05)   # ±5% — more conservative
print_managed_comparison()
print_threshold_analysis()
