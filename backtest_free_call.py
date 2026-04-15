"""
Backtest: Free Call Option + Dynamic Delta Hedge
Strategy:
  - Own a free 4yr call option, strike = 20% above spot on day 0
  - Short ETH dynamically based on OTM%:
      >50% OTM  : 0-D short
      50% -> 20% OTM : linear 0-D -> 50-D
      20% -> 0% OTM  : linear 50-D -> 60-D
      ITM (OTM < 0%) : flat 60-D
  - Rebalance daily (end of day price)
  - P&L = cumulative short mark-to-market + option payoff at end
"""

import math
from scipy.stats import norm

# --- Price data (CoinGecko daily, last 30 days) ---
raw = [
    [1768348800000,3319.9354070565078],[1768435200000,3356.4964063628336],[1768521600000,3318.2037023491666],[1768608000000,3296.062650076136],[1768694400000,3306.8712226908783],[1768780800000,3284.3194316465483],[1768867200000,3185.6644636922747],[1768953600000,2935.6234193160412],[1769040000000,2976.0491465641335],[1769126400000,2948.277889615024],[1769212800000,2950.9128485703054],[1769299200000,2949.197384616335],[1769385600000,2814.1853835458546],[1769472000000,2927.836546921288],[1769558400000,3021.091516998928],[1769644800000,3006.8071129555346],[1769731200000,2818.817890220326],[1769817600000,2702.40799526457],[1769904000000,2443.9290245632774],[1769990400000,2269.3288518651166],[1770076800000,2344.512261445349],[1770163200000,2226.985635575225],[1770249600000,2152.0870116729375],[1770336000000,1820.5693215574129],[1770422400000,2060.7349645674162],[1770508800000,2091.040353689534],[1770595200000,2095.1305644770564],[1770681600000,2104.4577921908335],[1770768000000,2018.9237788543585],[1770854400000,1939.4321739711042],[1770940800000,1945.7351413092624],[1771027200000,2047.3626742531244],[1771113600000,2085.5236826118394],[1771200000000,1963.9572853026268],[1771286400000,2000.6104432030938],[1771372800000,1992.004854467171],[1771459200000,1954.7534951528544],[1771545600000,1946.9092613594232],[1771632000000,1967.8121148578189],[1771718400000,1973.6643315860636],[1771804800000,1954.1913563168575],[1771891200000,1853.695790383818],[1771977600000,1852.8102933693347],[1772064000000,2053.1886740789387],[1772150400000,2027.3015182289616],[1772236800000,1931.3205870910035],[1772323200000,1965.036620141305],[1772409600000,1938.411487707785],[1772496000000,2029.443994398502],[1772582400000,1982.4582786533451],[1772668800000,2125.8345858015964],[1772755200000,2074.5222481851615],[1772841600000,1980.7782841320018],[1772928000000,1969.6937981965013],[1773014400000,1938.6249253514961],[1773100800000,1992.355228734493],[1773187200000,2035.2089486782504],[1773273600000,2051.7311684113824],[1773360000000,2076.5162283684745],[1773446400000,2093.00633968562],[1773532800000,2096.556369062344],[1773619200000,2175.059915408281],[1773705600000,2351.172929558985],[1773792000000,2318.1196031651903],[1773878400000,2203.380058379178],[1773964800000,2137.450038431429],[1774051200000,2146.971987874902],[1774137600000,2078.0492129718186],[1774224000000,2053.1449566818205],[1774310400000,2151.498274966905],[1774396800000,2155.6817607237],[1774483200000,2168.2595767488515],[1774569600000,2059.332619583916],[1774656000000,1991.9001004362854],[1774742400000,1992.7681119939894],[1774828800000,1983.184167632635],[1774915200000,2023.82401658508],[1775001600000,2104.8765857093113],[1775088000000,2139.0578887146285],[1775174400000,2056.8902960008427],[1775260800000,2053.6088145168164],[1775347200000,2064.9940579142453],[1775433600000,2109.005555869251],[1775520000000,2107.828320222534],[1775606400000,2241.8159903072574],[1775692800000,2190.478568186725],[1775779200000,2188.9744265525896],[1775865600000,2245.0457222392993],[1775952000000,2285.4701387600003],[1776038400000,2192.1608453362987],
]

prices = [p for _, p in raw]
dates = [ts // 1000 for ts, _ in raw]

# --- Params ---
S0     = prices[0]
STRIKE = S0 * 1.20          # 20% OTM at start
SIGMA  = 0.75               # ETH implied vol (4yr)
R      = 0.05               # risk-free rate
T0     = 4.0                # years to expiry at start


def bs_delta(S, K, T, r, sigma):
    """Black-Scholes call delta."""
    if T <= 0:
        return 1.0 if S > K else 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    return norm.cdf(d1)


def target_short(S, K):
    """
    Hedge ratio (fraction of ETH to short) based on OTM%.
    OTM% = (K - S) / S  [positive = OTM, negative = ITM]
    """
    otm = (K - S) / S

    if otm > 0.50:
        return 0.0
    elif otm > 0.20:
        # Linear: 0 at 50% OTM -> 0.5 at 20% OTM
        return 0.5 * (0.50 - otm) / (0.50 - 0.20)
    elif otm >= 0.0:
        # Linear: 0.5 at 20% OTM -> 0.6 at ATM
        return 0.5 + 0.1 * (0.20 - otm) / 0.20
    else:
        # ITM: flat 0.6
        return 0.60


# --- Backtest ---
print(f"Strike:       ${STRIKE:.2f}")
print(f"Start price:  ${S0:.2f}")
print(f"End price:    ${prices[-1]:.2f}")
print(f"Option payoff at end: ${max(0, prices[-1] - STRIKE):.2f}")
print()
print(f"{'Day':>4} {'Price':>8} {'OTM%':>6} {'Short':>6} {'BS_D':>6} {'Net_D':>6} {'Day_PnL':>9} {'Cum_PnL':>9}")
print("-" * 70)

cum_pnl       = 0.0
short_pos     = target_short(S0, STRIKE)  # initial short at day 0 open
daily_records = []

for i in range(1, len(prices)):
    P_prev = prices[i - 1]
    P_curr = prices[i]
    T      = T0 - (i / 365.0)

    # P&L on existing short position (held from prev close to curr close)
    day_pnl = short_pos * (P_prev - P_curr)
    cum_pnl += day_pnl

    # OTM% and BS delta at current price
    otm    = (STRIKE - P_curr) / P_curr
    bs_d   = bs_delta(P_curr, STRIKE, T, R, SIGMA)
    net_d  = bs_d - short_pos  # net long delta

    # Rebalance to new target (takes effect next day)
    new_short = target_short(P_curr, STRIKE)

    print(f"{i:>4} {P_curr:>8.1f} {otm*100:>5.1f}% {short_pos:>6.3f} {bs_d:>6.3f} {net_d:>6.3f} {day_pnl:>9.2f} {cum_pnl:>9.2f}")

    daily_records.append({
        'day': i, 'price': P_curr, 'otm_pct': otm,
        'short': short_pos, 'bs_delta': bs_d,
        'day_pnl': day_pnl, 'cum_pnl': cum_pnl
    })

    short_pos = new_short

print("-" * 70)

# Final option payoff
option_payoff = max(0, prices[-1] - STRIKE)
total_pnl     = cum_pnl + option_payoff

print(f"\nHedge P&L:    ${cum_pnl:>8.2f}")
print(f"Option payoff:${option_payoff:>8.2f}")
print(f"TOTAL P&L:    ${total_pnl:>8.2f}")
print(f"\nAs % of start price: {total_pnl / S0 * 100:.2f}%")
print(f"ETH spot return:     {(prices[-1]/S0 - 1)*100:.2f}%")

# Highlight best/worst days
best = max(daily_records, key=lambda x: x['day_pnl'])
worst = min(daily_records, key=lambda x: x['day_pnl'])
print(f"\nBest day:  day {best['day']} (${best['price']:.0f}) → ${best['day_pnl']:.2f}")
print(f"Worst day: day {worst['day']} (${worst['price']:.0f}) → ${worst['day_pnl']:.2f}")
