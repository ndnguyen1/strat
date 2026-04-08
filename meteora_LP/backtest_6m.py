"""
SOL-USDC 0.1% DLMM — 6-month managed rebalancing backtest
Oct 7 2025 – Apr 4 2026

Price data: CoinGecko daily SOL/USD close
Fee data:   estimated from CoinGecko total SOL trading volume ×
            a calibration ratio derived from the 14 days (Mar 21–Apr 3)
            where we have actual Meteora pool fees.

            Calibration: median pool_fee / cg_volume = 3.52ppm
            We run at both median (conservative) and mean (6.40ppm,
            includes spike days) to show the range.

Strategy modelled: managed concentration
  - Set ±r% range centred at current price
  - When day's close exits the range → remove, re-centre, re-add
  - Rebalance cost = $10 per event (0.1% fee on $10K repositioning swap)
  - Position size = $10,000, held constant (fees reinvested implicitly)

Pool average concentration assumed: ±8% → 25.5× multiplier
"""

import math
import urllib.request
import json
from datetime import datetime

# ── Constants ──────────────────────────────────────────────────────────────────

POSITION       = 10_000
POOL_TVL       = 4_884_593
POOL_AVG_RANGE = 0.08
REBALANCE_COST = 10.0

# Fee calibration (from 14-day overlap with real Meteora data)
FEE_PPM_MEDIAN = 3.52e-6   # conservative: median day
FEE_PPM_MEAN   = 6.40e-6   # includes spike days

# ── Fetch data ─────────────────────────────────────────────────────────────────

def fetch_coingecko():
    url = ("https://api.coingecko.com/api/v3/coins/solana/market_chart"
           "?vs_currency=usd&days=180&interval=daily")
    with urllib.request.urlopen(url, timeout=20) as r:
        d = json.load(r)
    prices  = d["prices"]
    volumes = d["total_volumes"]
    assert len(prices) == len(volumes)

    days = []
    for (ts, p), (_, v) in zip(prices, volumes):
        dt = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
        days.append({"date": dt, "price": p, "cg_vol": v})
    return days

# ── Core math (same as concentration model) ────────────────────────────────────

def concentration_mult(r):
    denom = 2 - 1/math.sqrt(1 + r) - math.sqrt(1 - r)
    return 2 / denom if denom > 0 else float("inf")

POOL_AVG_MULT = concentration_mult(POOL_AVG_RANGE)
BASE_SHARE    = POSITION / POOL_TVL

def effective_daily_fee(pool_fee_usd, my_mult):
    return BASE_SHARE * (my_mult / POOL_AVG_MULT) * pool_fee_usd

def il_pct(price_ratio):
    r = price_ratio
    return 2 * math.sqrt(r) / (1 + r) - 1

# ── Managed strategy ───────────────────────────────────────────────────────────

def run_managed(days, range_pct, fee_ppm):
    my_mult = concentration_mult(range_pct)

    centre = days[0]["price"]
    pa, pb = centre * (1 - range_pct), centre * (1 + range_pct)

    cum_fees   = 0.0
    cum_il     = 0.0
    rebal_cost = 0.0
    n_rebal    = 0
    prev_centre = centre
    rows = []

    for day in days:
        price     = day["price"]
        pool_fee  = day["cg_vol"] * fee_ppm

        in_range = pa <= price <= pb
        fee = effective_daily_fee(pool_fee, my_mult) if in_range else 0.0
        cum_fees += fee

        if not in_range:
            boundary = pb if price > pb else pa
            il_at_boundary = il_pct(boundary / prev_centre) * POSITION
            cum_il     += il_at_boundary
            cum_fees   -= REBALANCE_COST
            rebal_cost += REBALANCE_COST
            n_rebal    += 1
            # Re-centre
            prev_centre = price
            centre      = price
            pa = centre * (1 - range_pct)
            pb = centre * (1 + range_pct)

        rows.append({
            "date":      day["date"],
            "price":     price,
            "in_range":  in_range,
            "fee":       fee,
            "cum_fees":  cum_fees,
            "cum_il":    cum_il,
            "net_pnl":   cum_fees + cum_il,
            "rebal":     not in_range,
            "n_rebal":   n_rebal,
        })

    return rows, n_rebal, rebal_cost

# ── Static strategy (for comparison) ──────────────────────────────────────────

def run_static(days, range_pct, fee_ppm):
    my_mult = concentration_mult(range_pct)
    entry   = days[0]["price"]
    pa, pb  = entry * (1 - range_pct), entry * (1 + range_pct)

    cum_fees = 0.0
    n_in     = 0
    rows     = []
    for day in days:
        price    = day["price"]
        pool_fee = day["cg_vol"] * fee_ppm
        in_range = pa <= price <= pb
        fee      = effective_daily_fee(pool_fee, my_mult) if in_range else 0.0
        cum_fees += fee
        n_in     += int(in_range)
        il_dollar = il_pct(price / entry) * POSITION
        rows.append({
            "date":      day["date"],
            "price":     price,
            "in_range":  in_range,
            "fee":       fee,
            "cum_fees":  cum_fees,
            "il":        il_dollar,
            "net_pnl":   cum_fees + il_dollar,
        })
    return rows, n_in

# ── Monthly breakdown helper ───────────────────────────────────────────────────

def monthly_summary(rows):
    months = {}
    for r in rows:
        m = r["date"][:7]
        if m not in months:
            months[m] = {"fees": 0.0, "rebals": 0, "days": 0, "in_days": 0}
        months[m]["fees"]    += r["fee"]
        months[m]["rebals"]  += int(r.get("rebal", False))
        months[m]["days"]    += 1
        months[m]["in_days"] += int(r["in_range"])
    return months

# ── Print ──────────────────────────────────────────────────────────────────────

def print_strategy_summary(days, label, fee_ppm):
    print(f"\n{'='*105}")
    print(f"  {label}  (fee_ppm={fee_ppm*1e6:.2f})")
    print(f"  Pool avg ±{POOL_AVG_RANGE*100:.0f}% → {POOL_AVG_MULT:.1f}× | "
          f"Position ${POSITION:,} | TVL ${POOL_TVL:,} | "
          f"Base share {BASE_SHARE*100:.4f}%")
    print(f"  Entry: {days[0]['date']} @ ${days[0]['price']:.2f}   "
          f"Exit: {days[-1]['date']} @ ${days[-1]['price']:.2f}   "
          f"SOL: {(days[-1]['price']/days[0]['price']-1)*100:+.1f}%")

    ranges = [0.01, 0.02, 0.03, 0.05, 0.08, 0.10, 0.15]
    print(f"\n{'Range':<8} {'Mult':>7} {'Fees':>10} {'IL':>10} {'RC':>7} "
          f"{'Net P&L':>10} {'Net%':>7} {'Rebals':>7} {'In-rng':>8}")
    print(f"{'─'*85}")

    for r in ranges:
        m_rows, n_rebal, rc = run_managed(days, r, fee_ppm)
        s_rows, n_in        = run_static(days, r, fee_ppm)
        mf  = m_rows[-1]
        my_mult = concentration_mult(r)
        n_days  = len(days)
        in_days = sum(1 for x in m_rows if x["in_range"])
        net_pct = mf["net_pnl"] / POSITION * 100
        print(
            f"  ±{r*100:>4.1f}%  {my_mult:>7.1f}×  "
            f"${mf['cum_fees']:>8,.0f}  ${mf['cum_il']:>+9,.0f}  "
            f"${rc:>5,.0f}  ${mf['net_pnl']:>+9,.0f}  "
            f"{net_pct:>6.1f}%  {n_rebal:>5}×  {in_days:>4}/{n_days}"
        )

def print_monthly_detail(days, range_pct, fee_ppm):
    my_mult = concentration_mult(range_pct)
    m_rows, n_rebal, rc = run_managed(days, range_pct, fee_ppm)
    months  = monthly_summary(m_rows)

    print(f"\n{'─'*75}")
    print(f"  Monthly detail — managed ±{range_pct*100:.0f}%  mult={my_mult:.1f}×  "
          f"fee_ppm={fee_ppm*1e6:.2f}")
    print(f"{'─'*75}")
    print(f"  {'Month':<10} {'Fees':>9} {'Fee%/mo':>9} {'Fee%/d':>8} "
          f"{'Rebals':>7} {'In-days':>9}")
    print(f"  {'-'*65}")
    cum = 0.0
    for m, d in sorted(months.items()):
        cum += d["fees"]
        fee_pct_mo = d["fees"] / POSITION * 100
        fee_pct_d  = fee_pct_mo / d["days"]
        print(f"  {m}    ${d['fees']:>8,.0f}  {fee_pct_mo:>7.2f}%  "
              f"{fee_pct_d:>6.3f}%  {d['rebals']:>5}×   "
              f"{d['in_days']:>3}/{d['days']}")
    print(f"  {'TOTAL':<10} ${m_rows[-1]['cum_fees']:>8,.0f}  "
          f"{m_rows[-1]['cum_fees']/POSITION*100:>7.2f}%")

    f = m_rows[-1]
    print(f"\n  Net P&L: ${f['net_pnl']:+,.2f} ({f['net_pnl']/POSITION*100:+.2f}%)  |  "
          f"IL: ${f['cum_il']:+,.0f}  |  Rebal cost: ${rc:,.0f}  |  "
          f"Rebalances: {n_rebal}×")

def print_drawdown_analysis(days, range_pct, fee_ppm):
    m_rows, _, _ = run_managed(days, range_pct, fee_ppm)
    # Find longest out-of-range streak
    streak = max_streak = 0
    for r in m_rows:
        if not r["in_range"]:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    # Find worst net P&L drawdown
    peak = 0.0
    max_dd = 0.0
    for r in m_rows:
        peak = max(peak, r["net_pnl"])
        dd   = r["net_pnl"] - peak
        max_dd = min(max_dd, dd)

    in_days = sum(1 for r in m_rows if r["in_range"])
    out_days = len(m_rows) - in_days
    print(f"  ±{range_pct*100:.0f}%: in-range {in_days}/{len(m_rows)}d  "
          f"| longest out-streak {max_streak}d  "
          f"| max net P&L drawdown ${max_dd:+,.0f}")

# ── Main ───────────────────────────────────────────────────────────────────────

print("Fetching 6-month SOL price + volume from CoinGecko...")
days = fetch_coingecko()
print(f"Got {len(days)} days: {days[0]['date']} → {days[-1]['date']}")
print(f"SOL: ${days[0]['price']:.2f} → ${days[-1]['price']:.2f} "
      f"({(days[-1]['price']/days[0]['price']-1)*100:+.1f}%)")

avg_daily_cg_vol = sum(d["cg_vol"] for d in days) / len(days)
print(f"Avg daily CG vol: ${avg_daily_cg_vol/1e9:.2f}B")
print(f"Implied avg pool fees:  median ${avg_daily_cg_vol*FEE_PPM_MEDIAN:,.0f}/d  "
      f"| mean ${avg_daily_cg_vol*FEE_PPM_MEAN:,.0f}/d")

# ── Summary tables ──────────────────────────────────────────────────────────────

print_strategy_summary(days, "MANAGED STRATEGY — 6-MONTH SUMMARY (conservative, median ppm)", FEE_PPM_MEDIAN)
print_strategy_summary(days, "MANAGED STRATEGY — 6-MONTH SUMMARY (with spike days, mean ppm)", FEE_PPM_MEAN)

# ── Monthly breakdown for key scenarios ────────────────────────────────────────

print(f"\n\n{'='*105}")
print("MONTHLY BREAKDOWN — conservative estimate (median ppm = 3.52)")
for r in [0.02, 0.03, 0.05]:
    print_monthly_detail(days, r, FEE_PPM_MEDIAN)

print(f"\n\n{'='*105}")
print("MONTHLY BREAKDOWN — with spike days (mean ppm = 6.40)")
for r in [0.02, 0.03, 0.05]:
    print_monthly_detail(days, r, FEE_PPM_MEAN)

# ── Risk/drawdown ───────────────────────────────────────────────────────────────

print(f"\n\n{'='*105}")
print("DRAWDOWN / OUT-OF-RANGE ANALYSIS (managed, median ppm)")
print(f"{'─'*75}")
for r in [0.01, 0.02, 0.03, 0.05, 0.08, 0.10]:
    print_drawdown_analysis(days, r, FEE_PPM_MEDIAN)

# ── Regime comparison: high-vol vs low-vol months ──────────────────────────────

print(f"\n\n{'='*105}")
print("SOL PRICE PATH SUMMARY")
print(f"{'─'*50}")
prev = days[0]["price"]
for d in days:
    if d["date"][8:] == "01" or d == days[0] or d == days[-1]:
        chg = (d["price"] / prev - 1) * 100 if d != days[0] else 0
        print(f"  {d['date']}  ${d['price']:>7.2f}  ({chg:+.1f}% from prev shown)")
        prev = d["price"]
