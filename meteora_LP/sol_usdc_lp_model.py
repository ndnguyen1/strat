"""
SOL-USDC DLMM LP Position Model — 14-day backtest
Three fee tiers compared:
  Pool A: 0.04% fee, bin_step=4,  TVL ~$1.9M  (lowest fee, most volume)
  Pool B: 0.10% fee, bin_step=10, TVL ~$4.9M  (mid fee — the "higher tier")
  Pool C: 0.20% fee, bin_step=20, TVL ~$2.1M  (highest fee, least volume)

Entry: Mar 21 open ($89.82)  |  Exit: Apr 3 close ($80.40)
SOL price range over period: $78.89 – $91.74

Range scenarios modelled:
  Tight  ±5%:  [$85.33, $94.31] — exits range, SOL dipped below on multiple days
  Medium ±10%: [$80.84, $98.80] — stays in range all 14 days (just barely, min $78.89)
  Wide   ±15%: [$76.35, $103.29] — comfortably in range throughout

Price is USDC per SOL. Everything naturally in USD.
"""

import math

# ── Pool definitions ──────────────────────────────────────────────────────────

POOLS = {
    "0.04% (bin=4)":  {"fee_pct": 0.04, "tvl": 1_912_246},
    "0.10% (bin=10)": {"fee_pct": 0.10, "tvl": 4_884_593},
    "0.20% (bin=20)": {"fee_pct": 0.20, "tvl": 2_104_463},
}

# ── Raw daily data ────────────────────────────────────────────────────────────
# Merged from two API calls (start_time and latest 10), deduplicated.
# Price = USDC per SOL (close of day).
# Fees are pool-total USD fees per day.
# Entry open price (Mar 21 open) = Mar 20 close = $89.82

ENTRY_PRICE = 89.82   # USDC per SOL at start of day 1

raw = [
    # date           sol_close   fees_004pct   fees_010pct   fees_020pct
    ("2026-03-21",   87.52,        787.14,       8_647.42,      1_072.71),
    ("2026-03-22",   86.16,      2_107.52,      15_958.73,      2_849.08),
    ("2026-03-23",   91.45,      6_727.64,      41_938.81,      5_565.85),
    ("2026-03-24",   90.80,      3_451.74,      20_915.53,      2_442.40),
    ("2026-03-25",   91.67,      3_041.01,      12_940.20,      1_781.62),
    ("2026-03-26",   86.47,      2_829.87,      12_214.72,      2_139.95),
    ("2026-03-27",   83.08,      1_664.45,      10_073.46,      2_789.52),
    ("2026-03-28",   82.03,      1_420.91,       6_628.38,      1_332.06),
    ("2026-03-29",   81.37,      1_045.30,       7_322.19,      1_749.00),
    ("2026-03-30",   82.49,      5_584.64,      17_012.27,      2_950.81),
    ("2026-03-31",   83.15,      5_082.25,      21_070.85,      3_620.58),
    ("2026-04-01",   81.18,     18_272.70,     108_053.22,     13_055.12),
    ("2026-04-02",   78.94,      2_381.10,      14_374.34,      2_736.34),
    ("2026-04-03",   80.40,      5_637.01,       8_886.75,      1_478.81),
]

POSITION_SIZE = 10_000   # USD

# At entry: 50% SOL / 50% USDC
INIT_SOL_AMT  = (POSITION_SIZE / 2) / ENTRY_PRICE   # SOL tokens
INIT_USDC_AMT = POSITION_SIZE / 2                    # USDC tokens

# ── Concentrated liquidity math ───────────────────────────────────────────────

def initial_liquidity(p0, pa, pb, value_usd):
    """Solve for L (in USDC terms) given position value at price p0 in [pa, pb]."""
    p0c = max(pa, min(pb, p0))
    denom = 2*math.sqrt(p0c) - p0c/math.sqrt(pb) - math.sqrt(pa)
    return value_usd / denom if denom > 0 else 0

def position_value(p, pa, pb, L):
    """
    Value (USD) and composition of a concentrated LP at price p.
    Returns (value, sol_amount, usdc_amount, in_range).
    Price p = USDC per SOL.
    """
    if p <= pa:
        sol  = L * (1/math.sqrt(pa) - 1/math.sqrt(pb))
        usdc = 0.0
        in_range = False
    elif p >= pb:
        sol  = 0.0
        usdc = L * (math.sqrt(pb) - math.sqrt(pa))
        in_range = False
    else:
        sol  = L * (1/math.sqrt(p)  - 1/math.sqrt(pb))
        usdc = L * (math.sqrt(p)    - math.sqrt(pa))
        in_range = True
    return sol * p + usdc, sol, usdc, in_range

def hodl_value(p):
    return INIT_SOL_AMT * p + INIT_USDC_AMT

# ── Run a single scenario (one pool + one range) ──────────────────────────────

def run(pool_name, range_pct, fee_col_idx):
    pa = ENTRY_PRICE * (1 - range_pct)
    pb = ENTRY_PRICE * (1 + range_pct)
    L  = initial_liquidity(ENTRY_PRICE, pa, pb, POSITION_SIZE)
    tvl = POOLS[pool_name]["tvl"]
    lp_share = POSITION_SIZE / tvl

    cum_fees = 0.0
    days = []
    for row in raw:
        date, sol_close = row[0], row[1]
        pool_fees = row[fee_col_idx]

        val, sol_amt, usdc_amt, in_range = position_value(sol_close, pa, pb, L)
        il = val - hodl_value(sol_close)
        daily_fee = lp_share * pool_fees if in_range else 0.0
        cum_fees += daily_fee

        days.append({
            "date": date, "price": sol_close, "in_range": in_range,
            "lp_val": val, "hodl_val": hodl_value(sol_close),
            "il": il, "day_fee": daily_fee, "cum_fees": cum_fees,
            "net_pnl": cum_fees + il,
            "sol": sol_amt, "usdc": usdc_amt,
        })
    return days, pa, pb, lp_share

# ── Print table ───────────────────────────────────────────────────────────────

def print_table(pool_name, range_pct, fee_col_idx):
    days, pa, pb, lp_share = run(pool_name, range_pct, fee_col_idx)
    f = days[-1]
    in_range_count = sum(1 for d in days if d["in_range"])

    print(f"\n{'─'*105}")
    print(f"  {pool_name}  |  ±{range_pct*100:.0f}% range  "
          f"[${pa:.2f} – ${pb:.2f}]  |  LP share: {lp_share*100:.3f}%")
    print(f"{'─'*105}")
    print(f"  {'Date':<12} {'SOL':>7} {'InRng':>6} {'LP Val':>9} {'HODL':>9} {'IL':>9} {'DayFee':>8} {'CumFee':>9} {'NetP&L':>10}")
    print(f"  {'-'*100}")
    for d in days:
        ir = "Y" if d["in_range"] else "N"
        print(
            f"  {d['date']:<12} ${d['price']:>6.2f} {ir:>6}"
            f" ${d['lp_val']:>8,.0f} ${d['hodl_val']:>8,.0f}"
            f" ${d['il']:>+8,.0f} ${d['day_fee']:>7,.0f}"
            f" ${d['cum_fees']:>8,.0f} ${d['net_pnl']:>+9,.0f}"
        )
    print(f"\n  Final:  SOL={f['sol']:.3f}  USDC=${f['usdc']:,.2f}")
    print(f"  Fees: ${f['cum_fees']:,.2f}  |  IL: ${f['il']:+,.2f}  |  Net P&L: ${f['net_pnl']:+,.2f} ({f['net_pnl']/POSITION_SIZE*100:+.2f}%)  |  In-range: {in_range_count}/14 days")

# ── Summary matrix ────────────────────────────────────────────────────────────

def summary():
    FEE_COLS = {"0.04% (bin=4)": 2, "0.10% (bin=10)": 3, "0.20% (bin=20)": 4}
    ranges = [("±5%",  0.05), ("±10%", 0.10), ("±15%", 0.15)]

    print(f"\n\n{'='*105}")
    print("SUMMARY MATRIX — $10,000 position, 14 days (Mar 21 – Apr 3)")
    print(f"SOL: ${ENTRY_PRICE:.2f} → ${raw[-1][1]:.2f}  ({(raw[-1][1]/ENTRY_PRICE-1)*100:+.1f}%)")
    print(f"{'='*105}")
    print(f"{'':30} {'±5% range':>22} {'±10% range':>22} {'±15% range':>22}")
    print(f"{'Pool':<30} {'Fees':>7} {'IL':>8} {'Net':>8}  {'Fees':>7} {'IL':>8} {'Net':>8}  {'Fees':>7} {'IL':>8} {'Net':>8}")
    print(f"{'─'*105}")

    for pool_name, fee_col in FEE_COLS.items():
        row = f"{pool_name:<30}"
        for label, pct in ranges:
            days, pa, pb, lp_share = run(pool_name, pct, fee_col)
            f = days[-1]
            row += f"  ${f['cum_fees']:>6,.0f} ${f['il']:>+7,.0f} ${f['net_pnl']:>+7,.0f}"
        print(row)

    print(f"\n  Benchmark (HODL 50/50 SOL+USDC):  ${hodl_value(raw[-1][1]):,.2f}  ({(hodl_value(raw[-1][1])/POSITION_SIZE-1)*100:+.2f}%)")
    print(f"  Benchmark (100% SOL):              ${INIT_SOL_AMT*2 * raw[-1][1]:,.2f}  ({(INIT_SOL_AMT*2*raw[-1][1]/POSITION_SIZE-1)*100:+.2f}%)")
    print(f"  Benchmark (100% USDC):             ${POSITION_SIZE:,.2f}  (0.00%)")


# ── Main ──────────────────────────────────────────────────────────────────────

print("SOL-USDC DLMM LP Model — 14-day backtest")
print(f"Entry: {raw[0][0]} @ ${ENTRY_PRICE:.2f}  |  Exit: {raw[-1][0]} @ ${raw[-1][1]:.2f}")
print(f"SOL move: {(raw[-1][1]/ENTRY_PRICE-1)*100:+.2f}%")
print(f"Price range seen: ${min(r[1] for r in raw):.2f} – ${max(r[1] for r in raw):.2f}")

# Detailed table for the "higher tier" (0.1%) pool at each range
FEE_COLS = {"0.04% (bin=4)": 2, "0.10% (bin=10)": 3, "0.20% (bin=20)": 4}
for range_label, range_pct in [("±5%", 0.05), ("±10%", 0.10), ("±15%", 0.15)]:
    print(f"\n\n{'='*105}")
    print(f"RANGE SCENARIO: {range_label}  [${ENTRY_PRICE*(1-range_pct):.2f} – ${ENTRY_PRICE*(1+range_pct):.2f}]")
    for pool_name, fee_col in FEE_COLS.items():
        print_table(pool_name, range_pct, fee_col)

summary()
