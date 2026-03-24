# MEV Frontrunning Analysis Report
*Generated: 2026-03-18 18:50:26*

## 1. Executive Summary

- **Total swap transactions analysed**: 1,315,097
- **Trading pairs**: WETH_USDC, WETH_USDT, WETH_DAI, WETH_WBTC, USDC_USDT

| Frontrunning Type | Events Detected |
|-------------------|----------------|
| Sandwich (Insertion) | 845 |
| Displacement | 758 |
| Arbitrage / Back-run | 3,593 |
| Suppression | 18 |
| **Total** | **5,214** |

- Sandwich net profit: **$417,952.46**
- Arbitrage net profit: **$10,889,739.32**
- Unique sandwich attackers: **83**

![Frontrunning Overview](01_frontrun_overview.png)

## 2. Sandwich Attacks (Insertion)

A sandwich attack places a **front-run** trade before and a **back-run** trade after a victim's swap in the same block, profiting from the price movement caused by the victim.

| Pair | Sandwiches | % Blocks | % Volume |
|------|-----------|---------|---------|
| WETH_USDC | 201 | 0.08% | 0.19% |
| WETH_USDT | 178 | 0.08% | 0.19% |
| WETH_DAI | 133 | 0.05% | 0.14% |
| WETH_WBTC | 164 | 0.09% | 0.25% |
| USDC_USDT | 169 | 0.07% | 0.21% |

- Profitable: **198** / 845 (23.4%)
- Gross profit: **$891,887.84**
- Net profit: **$417,952.46**
- Avg / Median net: $494.62 / $-21.64

### Top 10 Sandwich Attackers

| Attacker | Count | Net Profit (USD) |
|----------|-------|-----------------|
| `0x00000000…0f594e` | 33 | $216,483.71 |
| `0x00000000…416b40` | 55 | $122,496.35 |
| `0xe8c060f8…38a2e5` | 38 | $43,635.23 |
| `0x93dabae1…955579` | 1 | $30,928.08 |
| `0x90414447…b275e6` | 1 | $29,058.41 |
| `0x7cf09d7a…d1604f` | 6 | $19,468.76 |
| `0x00000000…4e8987` | 19 | $11,458.29 |
| `0xd78a3280…486d44` | 5 | $7,531.42 |
| `0x3bc1588f…514326` | 2 | $7,277.87 |
| `0xf70a5d55…511b79` | 1 | $6,915.04 |

![Sandwich Timeline](02_sandwich_timeline.png)
![Profit Distribution](03_profit_distribution.png)
![Top Attackers](04_top_attackers.png)

## 3. Displacement Frontrunning

Displacement occurs when a frontrunner observes a pending swap and submits their own transaction **in the same direction** with a **higher gas price**, getting executed first and leaving the victim with a worse price.

- Total displacement events: **758**
- Avg gas ratio (frontrunner / victim): **2258.79×**
- Pairs: WETH_USDC, WETH_USDT, WETH_DAI, WETH_WBTC, USDC_USDT

### Top 5 Displacement Frontrunners

| Entity | Events |
|--------|--------|
| `0xfbd4cdb4…794c37` | 82 |
| `0x66a9893c…dba8af` | 79 |
| `0x3328f7f4…309c49` | 58 |
| `0x3fc91a3a…2b7fad` | 21 |
| `0x80a64c6d…cd5d9e` | 20 |

![Displacement](07_displacement.png)

## 4. Arbitrage / Back-running

Back-running occurs when an entity detects a large swap and immediately trades in the **opposite direction** to profit from the price reversion after the large trade's impact.

- Total back-run events: **3,593**
- Net profit: **$10,889,739.32**
- Avg net profit: **$3,030.82**

### Top 5 Back-runners

| Entity | Events |
|--------|--------|
| `0xa69babef…56e78c` | 210 |
| `0xa57bd001…fdd6cf` | 179 |
| `0x6b75d8af…009a80` | 153 |
| `0x51c72848…502a7f` | 141 |
| `0x860bd2db…d78f66` | 120 |

![Arbitrage](08_arbitrage.png)

## 5. Suppression

Suppression involves an entity flooding a block with **many high-gas transactions**, crowding out normal users and/or delaying their txs.

- Total suppression events: **18**
- Avg gas premium: **907.1×**

### Top 5 Suppressors

| Entity | Events |
|--------|--------|
| `0x6b75d8af…009a80` | 10 |
| `0x1f2f10d1…6df387` | 3 |
| `0x00000000…120e49` | 1 |
| `0x3328f7f4…309c49` | 1 |
| `0x7c63795c…bcfde8` | 1 |

![Suppression](09_suppression.png)

## 6. Gas Price Analysis

| Pair | Sandwich Block Gas | Normal Block Gas | Premium |
|------|-------------------|-----------------|---------|
| WETH_USDC | 25.67 Gwei | 23.05 Gwei | +11.4% |
| WETH_USDT | 20.99 Gwei | 19.42 Gwei | +8.1% |
| WETH_DAI | 66.48 Gwei | 22.09 Gwei | +201.0% |
| WETH_WBTC | 47.00 Gwei | 22.00 Gwei | +113.6% |
| USDC_USDT | 63.65 Gwei | 22.84 Gwei | +178.6% |

![Gas Analysis](05_gas_analysis.png)
![Price Timeseries](06_price_timeseries.png)

## 7. Methodology & Limitations

### Detection Algorithms

1. **Sandwich (Insertion)**: Same block, same entity executes two swaps in opposite directions with ≥ 1 victim swap (same direction as front-run) between them.
2. **Displacement**: Same block, same direction, different entities; frontrunner pays ≥ 1.5× gas price of victim and executes first (within 5 tx positions).
3. **Arbitrage / Back-run**: Within 3 tx positions after a large swap (> 90th percentile), a different entity trades in the opposite direction.
4. **Suppression**: An entity submits ≥ 3 swaps in one block with ≥ 3× the block median gas price.

### Limitations

- Only on-chain data; mempool-level displacement (dropped victim txs) is invisible.
- Gas cost uses fixed 150k gas/swap estimate.
- USD conversion from reserve-derived ETH prices; BTC/ETH ratio approximated.
- Entity identification is heuristic (router → `to` field; else `sender`).
- Displacement detection is conservative; true rate is likely higher.
