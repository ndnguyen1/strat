"""
JLP pair DLMM LP Model — 14-day backtest (Mar 21 – Apr 3)

Why JLP pairs are different:
  - JLP is a basket: SOL + ETH + BTC + USDC + USDT, diversified
  - JLP earns ~30-60% APR internally from Jupiter perps fees (already in price)
  - Result: JLP price is more stable than SOL alone → lower IL for LP positions
  - JLP/SOL drifts UP when JLP outperforms (it did: JLP -5.2% USD vs SOL -10.5%)
  - JLP/USDC drifts with underlying assets minus the perp fee accrual

Three pools modelled:
  Pool A: JLP-SOL  0.03% fee, bin=2,  TVL ~$86K   (small, high LP share)
  Pool B: JLP-USDC 0.03% fee, bin=2,  TVL ~$472K  (active, best fee/TVL)
  Pool C: JLP-USDC 0.15% fee, bin=15, TVL ~$1.9M  (deepest liquidity, lower yield)

All against same $10,000 entry position.
"""

import math

# ── Pool definitions ──────────────────────────────────────────────────────────

POOLS = {
    "JLP-SOL  0.03%": {"tvl": 86_451,   "quote": "SOL",  "fee_pct": 0.03},
    "JLP-USDC 0.03%": {"tvl": 471_798,  "quote": "USDC", "fee_pct": 0.03},
    "JLP-USDC 0.15%": {"tvl": 1_878_352,"quote": "USDC", "fee_pct": 0.15},
}

# SOL/USD price per day (for converting JLP-SOL to USD)
SOL_USD = {
    "2026-03-21": 87.52, "2026-03-22": 86.16, "2026-03-23": 91.45,
    "2026-03-24": 90.80, "2026-03-25": 91.67, "2026-03-26": 86.47,
    "2026-03-27": 83.08, "2026-03-28": 82.03, "2026-03-29": 81.37,
    "2026-03-30": 82.49, "2026-03-31": 83.15, "2026-04-01": 81.18,
    "2026-04-02": 78.94, "2026-04-03": 80.40,
}

# ── Raw daily data ────────────────────────────────────────────────────────────
# Price = quote token per JLP (SOL/JLP or USDC/JLP)
# Fees = pool-total USD fees that day

# JLP-SOL: price in SOL per JLP, fees in USD
# Entry open (Mar 21) = 0.0429 SOL/JLP
JLP_SOL_ENTRY = 0.0429
raw_jlp_sol = [
    # date          close_sol_per_jlp  fees_usd
    ("2026-03-21",  0.0433,  109.78),
    ("2026-03-22",  0.0435,  103.24),
    ("2026-03-23",  0.0425,  241.07),
    ("2026-03-24",  0.0427,  269.86),
    ("2026-03-25",  0.0426,  181.85),
    ("2026-03-26",  0.0436,  143.61),
    ("2026-03-27",  0.0443,   84.97),
    ("2026-03-28",  0.0446,  130.97),
    ("2026-03-29",  0.0448,   67.73),
    ("2026-03-30",  0.0446,  244.42),
    ("2026-03-31",  0.0446,  188.03),
    ("2026-04-01",  0.0454,  772.31),
    ("2026-04-02",  0.0458,  168.00),
    ("2026-04-03",  0.0454,  159.90),
]

# JLP-USDC 0.03%: price in USDC per JLP, fees in USD
JLP_USDC_ENTRY = 3.8554
raw_jlp_usdc_003 = [
    ("2026-03-21",  3.7896,   104.92),
    ("2026-03-22",  3.7489,   429.38),
    ("2026-03-23",  3.8894,   553.34),
    ("2026-03-24",  3.8739,   265.17),
    ("2026-03-25",  3.9035,   167.73),
    ("2026-03-26",  3.7700,   264.56),
    ("2026-03-27",  3.6769,   238.64),
    ("2026-03-28",  3.6571,   157.54),
    ("2026-03-29",  3.6432,   126.84),
    ("2026-03-30",  3.6762,   298.59),
    ("2026-03-31",  3.7087,   269.52),
    ("2026-04-01",  3.6813, 1_315.31),
    ("2026-04-02",  3.6128, 2_113.23),
    ("2026-04-03",  3.6440,   169.95),
]

# JLP-USDC 0.15%: same price, different fees/TVL
raw_jlp_usdc_015 = [
    ("2026-03-21",  3.7848,   146.17),
    ("2026-03-22",  3.7566,   368.55),
    ("2026-03-23",  3.8883,   998.15),
    ("2026-03-24",  3.8767,   551.68),
    ("2026-03-25",  3.9059,   351.76),
    ("2026-03-26",  3.7735,   287.18),
    ("2026-03-27",  3.6676,   602.39),
    ("2026-03-28",  3.6566,   292.37),
    ("2026-03-29",  3.6456,   323.34),
    ("2026-03-30",  3.6676,   850.95),
    ("2026-03-31",  3.7007,   648.87),
    ("2026-04-01",  3.6841, 1_059.19),
    ("2026-04-02",  3.6130,   923.36),
    ("2026-04-03",  3.6402,   213.64),
]

POSITION_SIZE = 10_000

# ── LP math (same as previous models) ────────────────────────────────────────

def initial_L(p0, pa, pb, value):
    p0c = max(pa, min(pb, p0))
    denom = 2*math.sqrt(p0c) - p0c/math.sqrt(pb) - math.sqrt(pa)
    return value / denom if denom > 0 else 0

def lp_val(p, pa, pb, L):
    if   p <= pa: x = L*(1/math.sqrt(pa) - 1/math.sqrt(pb)); y = 0.0;  ir = False
    elif p >= pb: x = 0.0;  y = L*(math.sqrt(pb) - math.sqrt(pa));     ir = False
    else:         x = L*(1/math.sqrt(p) - 1/math.sqrt(pb)); y = L*(math.sqrt(p) - math.sqrt(pa)); ir = True
    return x*p + y, x, y, ir

# ── Run scenario ──────────────────────────────────────────────────────────────

def run(pool_name, raw, entry_p, range_pct, usd_convert=None):
    """
    usd_convert: dict of date->SOL_USD for JLP-SOL pools.
                 None for JLP-USDC pools (price already in USD).

    For JLP-SOL: price is in SOL/JLP, position must be expressed in SOL.
    For JLP-USDC: price is in USDC/JLP, position is already in USD.
    """
    pa = entry_p * (1 - range_pct)
    pb = entry_p * (1 + range_pct)
    tvl  = POOLS[pool_name]["tvl"]
    lp_share = POSITION_SIZE / tvl

    if usd_convert:
        # JLP-SOL: convert $10K to SOL at entry, compute L in SOL units
        entry_sol_usd = list(usd_convert.values())[0]
        position_in_sol = POSITION_SIZE / entry_sol_usd      # e.g. $10K / $87.52 = 114.3 SOL
        init_jlp   = (position_in_sol / 2) / entry_p         # JLP tokens (half in JLP)
        init_quote = position_in_sol / 2                      # SOL tokens
        L = initial_L(entry_p, pa, pb, position_in_sol)
    else:
        # JLP-USDC: POSITION_SIZE is already in USDC
        init_jlp   = (POSITION_SIZE / 2) / entry_p           # JLP tokens
        init_quote = POSITION_SIZE / 2                        # USDC
        L = initial_L(entry_p, pa, pb, POSITION_SIZE)

    cum_fees = 0.0
    rows = []
    for date, close_p, pool_fees in raw:
        sol_usd = usd_convert[date] if usd_convert else 1.0
        p_usd   = close_p * sol_usd

        # LP value in quote units, then convert to USD
        val_quote, jlp_amt, quote_amt, ir = lp_val(close_p, pa, pb, L)
        val_usd  = val_quote * sol_usd

        # HODL value: initial split held at current prices
        hodl_usd = (init_jlp * close_p + init_quote) * sol_usd

        il_usd   = val_usd - hodl_usd
        daily_fee = lp_share * pool_fees if ir else 0.0
        cum_fees += daily_fee

        rows.append({
            "date": date, "price_usd": p_usd, "in_range": ir,
            "lp_usd": val_usd, "hodl_usd": hodl_usd, "il_usd": il_usd,
            "day_fee": daily_fee, "cum_fees": cum_fees,
            "net_pnl": cum_fees + il_usd,
            "jlp_amt": jlp_amt, "quote_amt": quote_amt,
        })
    return rows, pa, pb, lp_share

# ── Print table ───────────────────────────────────────────────────────────────

def print_pool(pool_name, raw, entry_p, range_pct, usd_convert=None):
    rows, pa, pb, lp_share = run(pool_name, raw, entry_p, range_pct, usd_convert)
    f = rows[-1]
    in_range_days = sum(1 for r in rows if r["in_range"])
    q = POOLS[pool_name]["quote"]

    pa_usd = pa * (list(usd_convert.values())[0] if usd_convert else 1.0)
    pb_usd = pb * (list(usd_convert.values())[0] if usd_convert else 1.0)

    print(f"\n  {'─'*98}")
    print(f"  {pool_name}  |  ±{range_pct*100:.0f}% range  "
          f"[${pa_usd:.4f} – ${pb_usd:.4f} USD/JLP]  |  LP share: {lp_share*100:.3f}%")
    print(f"  {'─'*98}")
    print(f"  {'Date':<12} {'JLP(USD)':>9} {'InRng':>6} {'LP Val':>9} {'HODL':>9} "
          f"{'IL':>9} {'DayFee':>8} {'CumFee':>9} {'NetP&L':>10}")
    print(f"  {'-'*95}")
    for r in rows:
        ir = "Y" if r["in_range"] else "N"
        print(f"  {r['date']:<12} ${r['price_usd']:>8.4f} {ir:>6}"
              f" ${r['lp_usd']:>8,.0f} ${r['hodl_usd']:>8,.0f}"
              f" ${r['il_usd']:>+8,.0f} ${r['day_fee']:>7,.0f}"
              f" ${r['cum_fees']:>8,.0f} ${r['net_pnl']:>+9,.0f}")

    final_jlp_usd = f["price_usd"]
    print(f"\n  Final holdings: {f['jlp_amt']:.3f} JLP  +  {f['quote_amt']:.4f} {q}")
    if usd_convert:
        sol_today = SOL_USD["2026-04-03"]
        print(f"  = {f['jlp_amt']:.3f} JLP (${f['jlp_amt']*final_jlp_usd:,.2f}) "
              f"+ {f['quote_amt']:.4f} SOL (${f['quote_amt']*sol_today:,.2f})")
    else:
        print(f"  = {f['jlp_amt']:.3f} JLP (${f['jlp_amt']*final_jlp_usd:,.2f}) "
              f"+ ${f['quote_amt']:,.2f} USDC")
    print(f"  Fees: ${f['cum_fees']:,.2f}  |  IL: ${f['il_usd']:+,.2f}  "
          f"|  Net P&L: ${f['net_pnl']:+,.2f} ({f['net_pnl']/POSITION_SIZE*100:+.2f}%)  "
          f"|  In-range: {in_range_days}/14 days")

# ── Summary matrix ────────────────────────────────────────────────────────────

def summary():
    configs = [
        ("JLP-SOL  0.03%", raw_jlp_sol,      JLP_SOL_ENTRY,  SOL_USD),
        ("JLP-USDC 0.03%", raw_jlp_usdc_003, JLP_USDC_ENTRY, None),
        ("JLP-USDC 0.15%", raw_jlp_usdc_015, JLP_USDC_ENTRY, None),
    ]
    ranges = [("±5%", 0.05), ("±10%", 0.10), ("±15%", 0.15)]

    print(f"\n\n{'='*105}")
    print("SUMMARY — $10,000 position, 14 days")
    print(f"JLP/SOL: {JLP_SOL_ENTRY:.4f} → {raw_jlp_sol[-1][1]:.4f}  ({(raw_jlp_sol[-1][1]/JLP_SOL_ENTRY-1)*100:+.1f}% in SOL)")
    print(f"JLP/USD: ${JLP_USDC_ENTRY:.4f} → ${raw_jlp_usdc_015[-1][1]:.4f}  ({(raw_jlp_usdc_015[-1][1]/JLP_USDC_ENTRY-1)*100:+.1f}% in USD)")
    print(f"SOL/USD: $89.82 → $80.40  (-10.5%)")
    print(f"{'='*105}")
    print(f"{'':25} {'±5% range':>22} {'±10% range':>22} {'±15% range':>22}")
    print(f"{'Pool':<25} {'Fees':>7} {'IL':>8} {'Net':>8}  {'Fees':>7} {'IL':>8} {'Net':>8}  {'Fees':>7} {'IL':>8} {'Net':>8}")
    print(f"{'─'*105}")

    for pool_name, raw, entry_p, usd_conv in configs:
        row = f"{pool_name:<25}"
        for _, range_pct in ranges:
            rows, _, _, _ = run(pool_name, raw, entry_p, range_pct, usd_conv)
            f = rows[-1]
            in_r = sum(1 for r in rows if r["in_range"])
            row += f"  ${f['cum_fees']:>6,.0f} ${f['il_usd']:>+7,.0f} ${f['net_pnl']:>+7,.0f}"
        print(row)

    print(f"\n  Benchmarks (JLP-USDC):")
    # HODL 50/50 JLP + USDC
    init_jlp_amt = (POSITION_SIZE/2) / JLP_USDC_ENTRY
    exit_jlp_usd = raw_jlp_usdc_015[-1][1]
    hodl_5050 = init_jlp_amt * exit_jlp_usd + POSITION_SIZE/2
    print(f"    HODL 50/50 JLP+USDC: ${hodl_5050:,.2f}  ({(hodl_5050/POSITION_SIZE-1)*100:+.2f}%)")
    # HODL 100% JLP
    hodl_jlp = (POSITION_SIZE / JLP_USDC_ENTRY) * exit_jlp_usd
    print(f"    HODL 100% JLP:       ${hodl_jlp:,.2f}  ({(hodl_jlp/POSITION_SIZE-1)*100:+.2f}%)")
    # HODL 100% USDC
    print(f"    HODL 100% USDC:      ${POSITION_SIZE:,.2f}  (0.00%)")

    print(f"\n  Compare to SOL-USDC 0.1% ±15% (from previous model): +$465 (+4.65%)")
    print(f"  Note: JLP earns ~30-60% APR internally from Jupiter perps — already in price.")


# ── Main ──────────────────────────────────────────────────────────────────────

entry_jlp_usd = JLP_SOL_ENTRY * SOL_USD["2026-03-21"]
exit_jlp_usd  = raw_jlp_sol[-1][1] * SOL_USD["2026-04-03"]
print("JLP Pair LP Model — 14-day backtest")
print(f"JLP price: ${entry_jlp_usd:.4f} → ${exit_jlp_usd:.4f} USD  ({(exit_jlp_usd/entry_jlp_usd-1)*100:+.1f}%)")
print(f"JLP/SOL:  {JLP_SOL_ENTRY:.4f} → {raw_jlp_sol[-1][1]:.4f}  ({(raw_jlp_sol[-1][1]/JLP_SOL_ENTRY-1)*100:+.1f}%)")
print(f"SOL:       $89.82 → $80.40  (-10.5%)")
print(f"JLP price range (USD): ${min(r[1]*SOL_USD[r[0]] for r in raw_jlp_sol):.4f} – ${max(r[1]*SOL_USD[r[0]] for r in raw_jlp_sol):.4f}")

print(f"\n\n{'='*105}")
print("JLP-SOL  (0.03% fee, $86K TVL)")
for range_label, range_pct in [("±5%", 0.05), ("±10%", 0.10), ("±15%", 0.15)]:
    print(f"\n  Range: {range_label}")
    print_pool("JLP-SOL  0.03%", raw_jlp_sol, JLP_SOL_ENTRY, range_pct, SOL_USD)

print(f"\n\n{'='*105}")
print("JLP-USDC (0.03% fee, $472K TVL)")
for range_label, range_pct in [("±5%", 0.05), ("±10%", 0.10), ("±15%", 0.15)]:
    print(f"\n  Range: {range_label}")
    print_pool("JLP-USDC 0.03%", raw_jlp_usdc_003, JLP_USDC_ENTRY, range_pct, None)

print(f"\n\n{'='*105}")
print("JLP-USDC (0.15% fee, $1.9M TVL)")
for range_label, range_pct in [("±5%", 0.05), ("±10%", 0.10), ("±15%", 0.15)]:
    print(f"\n  Range: {range_label}")
    print_pool("JLP-USDC 0.15%", raw_jlp_usdc_015, JLP_USDC_ENTRY, range_pct, None)

summary()
