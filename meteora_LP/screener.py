"""
Meteora DLMM volatile pair screener with risk guardrails.

Targets: fee_tvl_ratio.24h >= 0.5%/day (target 1%)
Guardrails:
  1. Min TVL $50K — filters micro-pools susceptible to manipulation
  2. Not blacklisted
  3. freeze_authority_disabled on BOTH tokens — if false, tokens can be frozen (rug vector)
  4. Min holders on the volatile token (non-stable) >= 200
  5. Pool age >= 1 day — filters launch-day spikes
  6. Fee consistency: annualised 1h fee rate vs 24h fee rate within 0.1x–10x
     (catches one-hour spikes masquerading as sustained yield)
"""

import requests
import json
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────

API_BASE = "https://dlmm.datapi.meteora.ag"
PAGE_SIZE = 100
MAX_PAGES = 50            # cap at 5000 pools to keep runtime reasonable

MIN_TVL = 50_000          # USD
MIN_FEE_TVL_24H = 0.5     # 0.5%/day minimum to be worth screening
                           # NOTE: fee_tvl_ratio field is in percent units (0.5 = 0.5%/day)
MIN_HOLDERS = 200          # for the volatile (non-stable) token
MIN_POOL_AGE_DAYS = 1
CONSISTENCY_LO = 0.1       # 1h annualised / 24h rate must be > this (not drying up)
CONSISTENCY_HI = 10.0      # ... and < this (not a one-hour spike)

STABLE_SYMBOLS = {"USDC", "USDT", "PYUSD", "DAI", "USDH", "UXD", "ISC"}
STABLECOIN_ADDRS = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def is_stable(token: dict) -> bool:
    return (
        token["symbol"].upper() in STABLE_SYMBOLS
        or token["address"] in STABLECOIN_ADDRS
    )

def volatile_token(pool: dict) -> dict:
    """Return the non-stable token (or token_x if both volatile)."""
    if is_stable(pool["token_y"]) and not is_stable(pool["token_x"]):
        return pool["token_x"]
    if is_stable(pool["token_x"]) and not is_stable(pool["token_y"]):
        return pool["token_y"]
    # Both volatile — return the one with fewer holders (higher risk = the one to check)
    if pool["token_x"]["holders"] <= pool["token_y"]["holders"]:
        return pool["token_x"]
    return pool["token_y"]

def pool_age_days(pool: dict) -> float:
    created_ms = pool.get("created_at", 0)
    if not created_ms:
        return 0
    now_ms = datetime.now(timezone.utc).timestamp() * 1000
    return (now_ms - created_ms) / (1000 * 86400)

def fee_consistency(pool: dict) -> float:
    """Ratio of annualised 1h fee rate to 24h fee rate. ~1.0 = consistent."""
    r = pool["fee_tvl_ratio"]
    r24 = r.get("24h", 0)
    r1h = r.get("1h", 0)
    if r24 == 0 or r1h == 0:
        return 0
    annualised_1h = r1h * 24   # scale 1h to same 24h basis
    return annualised_1h / r24

def risk_flags(pool: dict) -> list[str]:
    flags = []
    tx = pool["token_x"]
    ty = pool["token_y"]
    vt = volatile_token(pool)

    if not tx["freeze_authority_disabled"] or not ty["freeze_authority_disabled"]:
        flags.append("FREEZE_AUTH")        # tokens can be frozen
    if not tx["is_verified"] and not ty["is_verified"]:
        flags.append("UNVERIFIED")         # neither token verified
    if vt["holders"] < 500:
        flags.append(f"LOW_HOLDERS({vt['holders']})")
    if vt["market_cap"] < 500_000:
        flags.append(f"LOW_MCAP(${vt['market_cap']:,.0f})")
    if pool_age_days(pool) < 3:
        flags.append(f"NEW_POOL({pool_age_days(pool):.1f}d)")
    cons = fee_consistency(pool)
    if cons < CONSISTENCY_LO:
        flags.append("YIELD_DRYING")       # recent yield dropping fast
    if cons > CONSISTENCY_HI:
        flags.append("SPIKE_1H")           # last hour was anomalously hot

    return flags

# ── Hard filter ───────────────────────────────────────────────────────────────

def passes_hard_filter(pool: dict) -> bool:
    if pool.get("is_blacklisted"):
        return False
    if pool["tvl"] < MIN_TVL:
        return False
    fee24h = pool["fee_tvl_ratio"].get("24h", 0)
    if fee24h < MIN_FEE_TVL_24H:
        return False
    tx, ty = pool["token_x"], pool["token_y"]
    if not tx["freeze_authority_disabled"] or not ty["freeze_authority_disabled"]:
        return False   # hard reject — freeze authority is a non-negotiable rug vector
    vt = volatile_token(pool)
    if vt["holders"] < MIN_HOLDERS:
        return False
    if pool_age_days(pool) < MIN_POOL_AGE_DAYS:
        return False
    return True

# ── Fetch ─────────────────────────────────────────────────────────────────────

def fetch_pools() -> list[dict]:
    """Fetch pools sorted by APY desc, stop when yield drops below threshold."""
    pools = []
    page = 1
    print(f"Fetching pools from {API_BASE} ...")
    while page <= MAX_PAGES:
        resp = requests.get(
            f"{API_BASE}/pools",
            params={"limit": PAGE_SIZE, "page": page, "order_by": "apy", "order": "desc"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("data", [])
        if not batch:
            break

        pools.extend(batch)
        last_fee = batch[-1]["fee_tvl_ratio"].get("24h", 0)
        print(f"  page {page}/{data['pages']}  |  pools so far: {len(pools)}  |  last 24h fee/TVL: {last_fee:.3f}%")
        page += 1

    print(f"Total fetched: {len(pools)}")
    return pools

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    pools = fetch_pools()

    candidates = [p for p in pools if passes_hard_filter(p)]
    print(f"\nPassed hard filters: {len(candidates)} / {len(pools)}")

    # Sort by 24h fee/TVL descending
    candidates.sort(key=lambda p: p["fee_tvl_ratio"].get("24h", 0), reverse=True)

    print(f"\n{'='*110}")
    print(f"{'Rank':<5} {'Pair':<22} {'TVL':>10} {'24h fee%':>9} {'APY%':>8} {'Age(d)':>7} {'Cons':>6} {'Risk Flags'}")
    print(f"{'='*110}")

    shown = 0
    results = []
    for i, pool in enumerate(candidates):
        flags = risk_flags(pool)
        fee24 = pool["fee_tvl_ratio"].get("24h", 0)
        cons = fee_consistency(pool)
        age = pool_age_days(pool)
        tvl = pool["tvl"]
        apy = pool["apy"]

        row = {
            "rank": i + 1,
            "name": pool["name"],
            "address": pool["address"],
            "tvl": tvl,
            "fee_tvl_24h_pct": fee24,   # already in percent units (0.5 = 0.5%/day)
            "apy_pct": apy,
            "age_days": round(age, 1),
            "consistency": round(cons, 2),
            "risk_flags": flags,
            "token_x": pool["token_x"]["symbol"],
            "token_y": pool["token_y"]["symbol"],
            "volatile_token_holders": volatile_token(pool)["holders"],
            "volatile_token_mcap": volatile_token(pool)["market_cap"],
        }
        results.append(row)

        flag_str = ", ".join(flags) if flags else "CLEAN"
        print(
            f"{i+1:<5} {pool['name']:<22} ${tvl:>9,.0f} {fee24:>8.3f}% {apy:>7.0f}% "
            f"{age:>6.1f}d {cons:>5.2f}x  {flag_str}"
        )
        shown += 1

    # Save results
    out_path = "results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved {len(results)} results → {out_path}")
    print("\nLegend:")
    print("  24h fee%     = daily fee yield as % of TVL (target: ≥1%)")
    print("  APY%         = annualised compounded yield")
    print("  Cons         = (annualised 1h rate) / (24h rate)  — ~1.0 = consistent")
    print("  FREEZE_AUTH  = freeze authority not disabled (hard rejected by default)")
    print("  UNVERIFIED   = neither token verified on-chain")
    print("  LOW_HOLDERS  = volatile token has <500 holders")
    print("  LOW_MCAP     = volatile token market cap <$500K")
    print("  NEW_POOL     = pool <3 days old (launch spike risk)")
    print("  YIELD_DRYING = last 1h yield << 24h average (momentum fading)")
    print("  SPIKE_1H     = last 1h yield >> 24h average (unsustained burst)")

if __name__ == "__main__":
    main()
