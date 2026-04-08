"""
PUMPCADE-SOL DLMM LP Position Model — 14-day backtest
Pool: uw84JwsBzRVcQM1ykWGTwzxhPQB8tWECbYGaQA6VhBC

Models a $10,000 entry position under three range scenarios:
  A) ±50% range  — wide, stays in range longer, lower capital efficiency
  B) ±25% range  — moderate
  C) ±10% range  — tight, highest fees-per-dollar but exits range fast

For each scenario:
  - Fees earned: LP's share of pool fees each day (in range only)
  - IL: concentrated liquidity IL formula vs holding 50/50 at entry
  - Net P&L: fees - IL, all in USD

Key simplification: pool TVL held approximately constant at $114K.
LP share = $10K / $114K = 8.77%. When out of range, fee share = 0.

Concentrated liquidity IL mechanics:
  - In range [pa, pb]: position holds both tokens, IL follows modified v2 formula
  - Below pa: position = 100% PUMPCADE (base token, SOL-denominated)
  - Above pb: position = 100% SOL (quote token)
  Once out of range, LP stays fully in one token until rebalanced.
"""

import math
from dataclasses import dataclass, field

# ── Raw data (PUMPCADE price in SOL, fees in USD, SOL in USD) ────────────────

# Merged from two API calls: Mar 21 – Apr 3 (14 days)
raw = [
    # date         pumpcade_open   pumpcade_close  pool_fees_usd  sol_usd
    ("2026-03-21", 8.4647e-05,     1.1384e-04,     1142.05,       87.52),
    ("2026-03-22", 1.1384e-04,     1.0571e-04,      166.09,       86.16),
    ("2026-03-23", 1.0571e-04,     1.0313e-04,       36.11,       91.45),
    ("2026-03-24", 1.0313e-04,     1.0313e-04,       53.92,       90.80),
    ("2026-03-25", 1.0313e-04,     1.0313e-04,        5.91,       91.67),
    ("2026-03-26", 1.0313e-04,     1.0571e-04,       56.79,       86.47),
    ("2026-03-27", 1.0571e-04,     9.1156e-05,       93.26,       83.08),
    ("2026-03-28", 9.1156e-05,     1.2566e-04,      328.88,       82.03),
    ("2026-03-29", 1.2566e-04,     1.2566e-04,      322.28,       81.37),
    ("2026-03-30", 1.2566e-04,     1.1669e-04,      201.41,       82.49),
    ("2026-03-31", 1.3532e-04,     1.2880e-04,      202.70,       83.15),
    ("2026-04-01", 1.3202e-04,     1.4217e-04,      273.77,       81.18),
    ("2026-04-02", 1.4217e-04,     2.5088e-04,     5289.53,       78.94),
    ("2026-04-03", 2.5088e-04,     2.1106e-04,     1895.84,       80.08),
]

POSITION_SIZE_USD = 10_000
POOL_TVL_USD      = 114_316   # approximate; used for LP share calculation
LP_SHARE          = POSITION_SIZE_USD / POOL_TVL_USD  # ~8.75%

# Entry: use day 0 open price
ENTRY_PRICE_SOL   = raw[0][1]   # SOL per PUMPCADE
ENTRY_SOL_USD     = raw[0][4]   # USD per SOL on entry day

# At entry: 50/50 split between PUMPCADE and SOL (standard AMM deposit)
# Initial PUMPCADE value = $5000, initial SOL value = $5000
INIT_PUMPCADE_USD = POSITION_SIZE_USD / 2
INIT_SOL_USD      = POSITION_SIZE_USD / 2
INIT_PUMPCADE_AMT = INIT_PUMPCADE_USD / (ENTRY_PRICE_SOL * ENTRY_SOL_USD)  # in PUMPCADE tokens
INIT_SOL_AMT      = INIT_SOL_USD / ENTRY_SOL_USD                            # in SOL

# ── Concentrated liquidity math ───────────────────────────────────────────────

def clamp_price(p, pa, pb):
    return max(pa, min(pb, p))

def lp_value_concentrated(p, pa, pb, L, sol_usd):
    """
    Value of a concentrated LP position in USD.
    Price p = SOL per PUMPCADE (Y per X), range [pa, pb].
    L = liquidity constant.
    Returns (value_usd, pumpcade_amount, sol_amount, in_range)
    """
    if p <= pa:
        # Below range: 100% PUMPCADE
        x = L * (1/math.sqrt(pa) - 1/math.sqrt(pb))
        y = 0.0
        in_range = False
    elif p >= pb:
        # Above range: 100% SOL
        x = 0.0
        y = L * (math.sqrt(pb) - math.sqrt(pa))
        in_range = False
    else:
        # In range: both tokens
        x = L * (1/math.sqrt(p) - 1/math.sqrt(pb))
        y = L * (math.sqrt(p) - math.sqrt(pa))
        in_range = True
    value_usd = x * p * sol_usd + y * sol_usd
    return value_usd, x, y, in_range

def initial_liquidity(p0, pa, pb, position_usd, sol_usd):
    """
    Solve for L given initial position value V0 at price p0 in range [pa, pb].
    V0 (SOL) = L * (2*sqrt(p0) - p0/sqrt(pb) - sqrt(pa))
    """
    p0_clamped = clamp_price(p0, pa, pb)
    v0_sol = position_usd / sol_usd
    # From the value formula at p0:
    denom = 2*math.sqrt(p0_clamped) - p0_clamped/math.sqrt(pb) - math.sqrt(pa)
    if denom <= 0:
        return 0
    return v0_sol / denom

def hodl_value(p, p0, initial_pumpcade, initial_sol, sol_usd):
    """Value of holding the initial 50/50 split at new price p (in USD)."""
    return initial_pumpcade * p * sol_usd + initial_sol * sol_usd


# ── Scenario runner ───────────────────────────────────────────────────────────

@dataclass
class DayResult:
    date: str
    price_sol: float      # PUMPCADE price in SOL
    price_usd: float      # PUMPCADE price in USD
    sol_usd: float
    in_range: bool
    lp_value_usd: float
    hodl_value_usd: float
    il_usd: float         # IL = lp_value - hodl_value (negative = loss)
    fees_usd: float       # LP's share of fees today
    net_pnl_usd: float    # cumulative: fees earned - IL loss
    cum_fees: float
    pumpcade_held: float
    sol_held: float

def run_scenario(range_pct: float) -> list[DayResult]:
    """
    range_pct: half-width of price range as fraction (e.g. 0.5 = ±50%)
    """
    pa = ENTRY_PRICE_SOL * (1 - range_pct)
    pb = ENTRY_PRICE_SOL * (1 + range_pct)

    L = initial_liquidity(ENTRY_PRICE_SOL, pa, pb, POSITION_SIZE_USD, ENTRY_SOL_USD)

    results = []
    cum_fees = 0.0

    for date, open_p, close_p, pool_fees, sol_usd in raw:
        # Use close price as end-of-day price
        p = close_p

        lp_val, pumpcade_amt, sol_amt, in_range = lp_value_concentrated(p, pa, pb, L, sol_usd)
        hodl_val = hodl_value(p, ENTRY_PRICE_SOL, INIT_PUMPCADE_AMT, INIT_SOL_AMT, sol_usd)
        il = lp_val - hodl_val

        # Fees: only earned if price is in range today
        daily_fees = LP_SHARE * pool_fees if in_range else 0.0
        cum_fees += daily_fees

        results.append(DayResult(
            date=date,
            price_sol=p,
            price_usd=p * sol_usd,
            sol_usd=sol_usd,
            in_range=in_range,
            lp_value_usd=lp_val,
            hodl_value_usd=hodl_val,
            il_usd=il,
            fees_usd=daily_fees,
            net_pnl_usd=cum_fees + il,  # il is already negative when losing
            cum_fees=cum_fees,
            pumpcade_held=pumpcade_amt,
            sol_held=sol_amt,
        ))

    return results


# ── Print results ─────────────────────────────────────────────────────────────

def print_scenario(label: str, range_pct: float):
    results = run_scenario(range_pct)
    pa = ENTRY_PRICE_SOL * (1 - range_pct)
    pb = ENTRY_PRICE_SOL * (1 + range_pct)

    print(f"\n{'='*100}")
    print(f"Scenario {label}: ±{range_pct*100:.0f}% range")
    print(f"  Range: [{pa:.6f}, {pb:.6f}] SOL/PUMPCADE")
    print(f"  Entry price: {ENTRY_PRICE_SOL:.6f} SOL/PUMPCADE = ${ENTRY_PRICE_SOL * ENTRY_SOL_USD:.4f}")
    print(f"  Entry: ${POSITION_SIZE_USD:,.0f} | LP share: {LP_SHARE*100:.2f}% of pool")
    print(f"{'='*100}")
    print(f"{'Date':<12} {'Price(SOL)':>11} {'Price(USD)':>10} {'InRange':>7} {'LP Val':>10} {'HODL Val':>10} {'IL':>10} {'DayFees':>8} {'CumFees':>9} {'NetP&L':>10}")
    print(f"{'-'*100}")

    for r in results:
        hodl_delta = r.hodl_value_usd - POSITION_SIZE_USD
        print(
            f"{r.date:<12}"
            f" {r.price_sol:>11.6f}"
            f" {r.price_usd:>10.4f}"
            f" {'YES' if r.in_range else 'NO ':>7}"
            f" ${r.lp_value_usd:>9,.0f}"
            f" ${r.hodl_value_usd:>9,.0f}"
            f" ${r.il_usd:>+9,.0f}"
            f" ${r.fees_usd:>7,.0f}"
            f" ${r.cum_fees:>8,.0f}"
            f" ${r.net_pnl_usd:>+9,.0f}"
        )

    final = results[-1]
    print(f"\n  Summary after {len(results)} days:")
    print(f"    PUMPCADE price move:  {ENTRY_PRICE_SOL:.6f} → {final.price_sol:.6f} SOL  ({(final.price_sol/ENTRY_PRICE_SOL - 1)*100:+.1f}%)")
    print(f"    Total fees earned:    ${final.cum_fees:,.2f}")
    print(f"    IL vs HODL:           ${final.il_usd:+,.2f}")
    print(f"    Net P&L:              ${final.net_pnl_usd:+,.2f}  ({final.net_pnl_usd/POSITION_SIZE_USD*100:+.2f}%)")
    print(f"    Days in range:        {sum(1 for r in results if r.in_range)} / {len(results)}")
    out_days = [r for r in results if not r.in_range]
    if out_days:
        print(f"    Out-of-range on:      {', '.join(r.date for r in out_days)}")


# ── Main ──────────────────────────────────────────────────────────────────────

print(f"PUMPCADE-SOL LP Position Model — 14-day backtest")
print(f"Entry date: {raw[0][0]}  |  Exit date: {raw[-1][0]}")
print(f"Entry price: {ENTRY_PRICE_SOL:.6f} SOL/PUMPCADE = ${ENTRY_PRICE_SOL * ENTRY_SOL_USD:.4f}")
print(f"Exit price:  {raw[-1][2]:.6f} SOL/PUMPCADE = ${raw[-1][2] * raw[-1][4]:.4f}")
price_ratio = raw[-1][2] / raw[-1][1]
print(f"Price move (SOL-denominated): {(raw[-1][2]/raw[0][1] - 1)*100:+.1f}%")
print(f"USD-denominated PUMPCADE move: {(raw[-1][2]*raw[-1][4]/(raw[0][1]*raw[0][4]) - 1)*100:+.1f}%")
print(f"SOL/USD move: {raw[0][4]:.2f} → {raw[-1][4]:.2f} ({(raw[-1][4]/raw[0][4] - 1)*100:+.1f}%)")
print(f"\nTotal pool fees over period: ${sum(r[3] for r in raw):,.2f}")
print(f"LP share of pool ({LP_SHARE*100:.2f}%) fee take: ${sum(r[3] for r in raw)*LP_SHARE:,.2f}")

print_scenario("A", 0.50)   # ±50%
print_scenario("B", 0.25)   # ±25%
print_scenario("C", 0.10)   # ±10%

print("\n\nComparison summary")
print(f"{'='*60}")
print(f"{'Scenario':<15} {'Fees':>8} {'IL':>10} {'Net P&L':>10} {'In-range':>10}")
print(f"{'-'*60}")
for label, pct in [("±50% (A)", 0.50), ("±25% (B)", 0.25), ("±10% (C)", 0.10)]:
    r = run_scenario(pct)
    f = r[-1]
    in_range = sum(1 for x in r if x.in_range)
    print(f"{label:<15} ${f.cum_fees:>7,.0f} ${f.il_usd:>+9,.0f} ${f.net_pnl_usd:>+9,.0f} {in_range:>4}/{len(r)} days")
