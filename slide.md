---
marp: true
header: '![](https://www.polyu.edu.hk/assets/img/main-logo-1x.png)'
paginate: true
style: |
  section {
    font-size: 24px;
    line-height: 1.15;
    padding: 72px 48px 40px 48px;
  }

  header {
    top: 18px;
    right: 28px;
    left: auto;
    width: auto;
  }

  header img {
    height: 48px;
  }

  h1, h2 {
    color: #9d2235;
  }

  strong {
    color: #9d2235;
  }

  table {
    font-size: 19px;
  }

  code {
    font-size: 0.9em;
  }
---

# COMP5566 Project Presentation
## Quantifying Frontrunning Activities on Ethereum and Their Impacts on Marketplace

**Group 1**

---

## 1. Project Brief & Requirements

**Goal**: Collect historical Ethereum DEX transactions, detect frontrunning patterns, quantify adversary profits, and measure market impact on Uniswap V2.

**Project 8 — Main steps**

1. Collect historical Ethereum transactions
2. Detect Frontrunning activities (Displacement, Insertion, Suppression)
3. Analyze the profits of adversaries
4. Analyze the impact on Ethereum marketplace (e.g., token price)

**Our pipeline**

```
Etherscan API v2  →  Event Decoder  →  CSV Storage
    →  4 MEV Detectors  →  Profit Analyzer  →  Charts + Excel
```

---

## 2. Requirement Coverage

| Lecture Requirement | Our Implementation |
| --- | --- |
| Collect historical transactions | Etherscan API v2, 5 Uniswap V2 pairs, adaptive block chunking, checkpoint resume |
| Detect Displacement | Same-block, same-direction, gas ratio >= 1.5x |
| Detect Insertion | Sandwich detector: front-run + victim + back-run in same block |
| Detect Suppression | Entity >= 3 swaps with >= 3x block median gas |
| Analyze adversary profits | USD profit model for sandwich & arbitrage, gas cost estimation |
| Analyze market impact | Gas price comparison, price time-series, block/volume penetration |

**Bonus**: Arbitrage / back-running detection

---

## 3. Data Collection & Preprocessing

**5 Uniswap V2 pairs**: WETH/USDC, WETH/USDT, WETH/DAI, WETH/WBTC, USDC/USDT
**Events**: `Swap`, `Sync`, `Mint`, `Burn` from block `10000835` to chain tip

**Key engineering**
- Adaptive block windows (25k default, auto shrink/grow)
- Multi-key rate limiter with daily quota tracking
- Checkpoint resume + parallel fetching

**Preprocessing**
- **Entity ID**: if sender is UniswapV2 router, use `to` address instead
- **Ordering**: sort by `(block_number, tx_index, log_index)`
- **ETH price index**: built from WETH/USDC reserves (fallback USDT, DAI)

---

## 4. Detection Methods

| Type | Logic | Key Threshold |
| --- | --- | --- |
| **Sandwich (Insertion)** | Same entity, same block, opposite-direction pair with victim swap between them | victim same direction as front-run |
| **Displacement** | Same block, same direction, different entities, frontrunner executes first | gas ratio >= **1.5x** |
| **Arbitrage / Back-run** | Opposite-direction trade immediately after a large swap (>P90) | within **3 tx** positions |
| **Suppression** | Single entity >= 3 swaps in block with extreme gas | gas premium >= **3x** block median |

**Profit model (sandwich)**:

$$\text{Net} = \text{USD}(n_0) + \text{USD}(n_1) - \frac{(g_f + g_b) \times 150000}{10^{18}} \times P_{ETH}$$

---

## 5. Overall Detection Results

| Type | Events | Key Metric | Proportion |
| --- | --- | --- | --- |
| **Sandwich** | 845 (13.2%) | Net profit: **$402,379** | 24.4% profitable |
| **Displacement** | 758 (11.8%) | Avg gas ratio: **2,258x** | ordering advantage |
| **Arbitrage / Back-run** | 4,796 (74.7%) | Net profit: **$17,024,829** | avg $3,549/event |
| **Suppression** | 18 (0.3%) | Avg gas premium: **907x** | extreme but rare |
| **Total** | **6,417** | **$17.4M+** aggregate | |

- Arbitrage / back-running dominates both in **frequency** and **total profit**
- Sandwich profitability is **highly concentrated** — most attempts lose money on gas
- Suppression is the rarest but shows **extreme** gas competition (907x block median)

---

## 6. Sandwich Attack Findings

- **845** events, only **206** profitable (**24.4%**) — profitability highly concentrated
- Gross profit: **$877,638**; Net profit (after gas): **$402,379**
- Avg net: $476; Median net: **-$23** (most attackers lose money on gas)

## 7. Displacement, Arbitrage

**Displacement (758 events)** — ordering advantage via gas premium
- Avg gas ratio: **2,258x** (extreme outliers); Top frontrunner: **82** events

**Arbitrage / Back-running (4,796 events)** — most frequent pattern
- Net profit: **$17,024,829** (avg **$3,549** per event); Top back-runner: **210** events

**Suppression (18 events)** — rarest but most extreme, avg gas premium: **907x**

---

## 8. Market impact
- Sandwich-related blocks show **significantly higher** median gas prices
- **WETH_DAI**, **WETH_WBTC**, **USDC_USDT**: large gas premiums in suspicious blocks
- MEV activity increases gas costs for **all users** in affected blocks
- Entity `0x6b75…80` appears in both back-running and suppression, suggesting **multi-strategy** operation

![w:700](analysis/output/05_gas_analysis.png)

---

## 9. Limitations

- **On-chain only**: no mempool visibility; dropped/replaced txs invisible
- **Heuristic entity ID**: router-based approach may merge/split entities
- **Fixed gas estimate**: 150k gas per swap is an approximation
- **Price approximation**: reserve-derived ETH prices, fixed WBTC ratio
- **Threshold sensitivity**: 1.5x, P90, 3x thresholds affect detection counts
- **Interpretation**: patterns are *consistent with* MEV but do not prove intent

---

## 10. Project Summary

- Complete pipeline: **collection -> detection -> profit analysis -> visualization**
- Covers all **Project 8 requirements**: Displacement, Insertion, Suppression + bonus Arbitrage
- **6,417 events** detected, **$17.4M+** aggregate adversary profit quantified
- Gas-price analysis confirms MEV raises costs for normal traders

**Deliverables**
- Python source code (fetcher + analysis pipeline)
- Collected datasets (CSV) + 9 analysis charts + Excel workbook
- Markdown report + GitHub repo for reproducibility



## Thank You
