# MEV Frontrunning Analysis Report
*Generated: 2026-03-17 15:41:37*

## 1. Executive Summary

- **Total swap transactions analysed**: 1,315,097
- **Trading pairs**: WETH_USDC, WETH_USDT, WETH_DAI, WETH_WBTC, USDC_USDT

| Frontrunning Type | Events Detected |
|-------------------|----------------|
| Sandwich (Insertion) | 845 |
| Displacement | 758 |
| Arbitrage / Back-run | 4,796 |
| Suppression | 18 |
| **Total** | **6,417** |

- Sandwich net profit: **$402,379.84**
- Arbitrage net profit: **$17,024,829.75**
- Unique sandwich attackers: **83**

![Frontrunning Overview](analysis/output/01_frontrun_overview.png)

## 2. Methodology

### Data Source and Scope

- Data source: UniswapV2 event logs collected from Ethereum mainnet through the Etherscan API
- Trading pairs: `WETH_USDC`, `WETH_USDT`, `WETH_DAI`, `WETH_WBTC`, `USDC_USDT`
- Event types used in the analysis:
  - `Swap`
  - `Sync`
  - `Mint`
  - `Burn`

### Preprocessing Rules

- Each swap is ordered inside a block by the tuple:

$$
\operatorname{ord}(x) = (\texttt{tx\_index}_x,\ \texttt{log\_index}_x)
$$

- The trading entity is identified heuristically. If a swap is sent through a known router, we use the `to` field as the effective entity; otherwise we use `sender`.
- Trade direction is simplified into two cases: token0-in or token1-in. This lets us compare swaps consistently within the same pair and block.

### Detection Rules

#### 2.1 Sandwich (Insertion)

We mark a sandwich candidate when the same entity submits two swaps in the same block with opposite directions, and at least one other swap lies between them in execution order. The intermediate swap or swaps must come from a different entity and move in the same direction as the front-run. In simple terms, the attacker opens a position, the victim trade moves the price, and the attacker closes the position later in the same block.

#### 2.2 Displacement

We detect displacement when two different entities trade in the same direction in the same block, but one pays much higher gas and executes first. We require the two transactions to be close to each other in block position, specifically within five transaction indices, and we use the following gas threshold:

$$
\frac{\texttt{gas\_price}_f}{\texttt{gas\_price}_v} \ge 1.5
$$

This is a conservative on-chain heuristic: it captures priority-taking behavior visible in the final block, but it cannot prove what happened earlier in the mempool.

#### 2.3 Arbitrage / Back-running

We first identify a large trigger trade, then check whether another entity reacts immediately with an opposite-direction swap in the same block. Trade size is measured after normalizing token amounts by decimals, and a trigger trade is defined as one above the pair-level 90th percentile:

$$
S(t) \ge Q_{0.90}(S)
$$

We then look for a different entity that trades in the opposite direction within the next three transaction positions. This captures rapid same-block reactions to large price-moving swaps.

#### 2.4 Suppression

We define suppression as a block-level pattern where one entity sends at least three swaps in the same block and does so at a much higher gas level than the block median. In practice, we compare that entity's median gas price with the block median and flag unusually aggressive cases. This signal is intended to identify crowding-out behavior rather than to prove direct victim loss for every transaction.

### Profit Estimation

#### Sandwich Profit

For a detected sandwich, we compute the attacker's net token gain across the front-run and back-run legs, convert those token gains into USD using reserve-derived ETH prices, and then subtract the estimated gas cost.

Estimated gas cost is:

$$
\text{GasCostUSD} =
\frac{(\texttt{gas\_price}_{front} + \texttt{gas\_price}_{back}) \times 150000}{10^{18}}
\times P_{\text{ETH}}(B)
$$

and net profit is:

$$
\text{NetProfitUSD} = \text{ProfitUSD} - \text{GasCostUSD}
$$

#### Back-run Profit

For back-running, profit is estimated from the back-runner's net token output, converted into USD, then reduced by estimated gas cost using the same gas model.

### Limitations

- The analysis uses on-chain data only; failed or dropped mempool transactions are not observable.
- Displacement is therefore measured conservatively and should be interpreted as a lower bound.
- Gas cost uses a fixed estimate of `150,000` gas per swap.
- ETH price is reconstructed from reserve data, mainly from `WETH_USDC` and fallback stablecoin pairs.
- Entity identification is heuristic: router-mediated trades are mapped to the `to` field, otherwise to `sender`.

## 3. Engineering Efforts

We built our own Python crawler to collect UniswapV2 history automatically. This was important because our MEV analysis needed large amounts of ordered transaction data, not just a few manually exported files.

### What We Collected

- Blockchain: Ethereum mainnet
- Protocol: UniswapV2 pair contracts
- Start point: block `10000835`
- Main pairs:

```yaml
pairs:
  - address: "0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc"
    name: "WETH_USDC"
  - address: "0x0d4a11d5EEaaC28EC3F61d100daF4d40471f1852"
    name: "WETH_USDT"
  - address: "0xA478c2975Ab1Ea89e8196811F51A7B7Ade33eB11"
    name: "WETH_DAI"
  - address: "0xBb2b8038a1640196FbE3e38816F3e67Cba72D940"
    name: "WETH_WBTC"
  - address: "0x3041CbD36888bECc7bbCBc0045E3B1f144466f5f"
    name: "USDC_USDT"
```

### What Each Crawled Event Means

- `Swap`: a user trade happened
- `Sync`: the pool reserves changed
- `Mint`: liquidity was added
- `Burn`: liquidity was removed

```python
SWAP_TOPIC = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
SYNC_TOPIC = "0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1"
MINT_TOPIC = "0x4c209b5fc8ad50758f13e2e1088ba56a560dff690a1c6fef26394f4c03821c4f"
BURN_TOPIC = "0xdccd412f0b1252819cb1fd330b93224ca42612892bb3f4f789976e6d81936496"
```

### How We Stored the Data

- We saved one folder per trading pair
- We saved one CSV file per event type
- We kept a checkpoint file so the crawler could continue after stopping
- We kept an error log for timeouts and API problems

```text
data/
  checkpoint.json
  error.log
  WETH_USDC/
    swaps.csv
    syncs.csv
    mints.csv
    burns.csv
```

### Example Output

- `swaps.csv` records the exact position of a trade in a block

```csv
block_number,tx_hash,tx_index,log_index,timestamp,sender,to,amount0_in,amount1_in,amount0_out,amount1_out,gas_price
```

- `syncs.csv` records the pool reserves after a change

```csv
block_number,tx_hash,tx_index,log_index,timestamp,reserve0,reserve1
```

### Practical Problems We Had to Solve

- API limit problem:
  - Etherscan limits how many requests one key can send
  - We solved this by rotating across multiple API keys

```python
limiter = RateLimiter(
    api_keys=api_keys,
    calls_per_second=cfg.calls_per_second,
    daily_limit=cfg.daily_limit,
)
```

- Unstable network / server problem:
  - Some requests fail because of timeout, rate limit, or busy server
  - We retry automatically instead of stopping the whole job

- Large history problem:
  - Some block ranges contain very few events, while others contain many
  - We changed the query size dynamically to crawl faster without missing data

```python
if num_events < 500:
    step *= 3.5
elif num_events < 900:
    step *= 3
else:
    step *= 2.5
```

- Long-running job problem:
  - Crawling historical data can take hours or days
  - We save progress continuously so the next run can resume

```json
{
  "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc": {
    "pair_name": "WETH_USDC",
    "last_block": 19123456,
    "event_counts": {
      "swap": 123456,
      "sync": 123456
    }
  }
}
```

### Why This Was Important

- We needed `tx_index` and `log_index` to know the exact order of trades inside one block
- We needed `gas_price` to study who paid more gas to get priority
- We needed `Sync` events to reconstruct how pool reserves changed over time
- We needed a clean CSV structure so the later detection code could run repeatedly and reproducibly

## 4. Sandwich Attacks (Insertion)

A sandwich attack places a **front-run** trade before and a **back-run** trade after a victim's swap in the same block, profiting from the price movement caused by the victim.

| Pair | Sandwiches | % Blocks | % Volume |
|------|-----------|---------|---------|
| WETH_USDC | 201 | 0.08% | 0.19% |
| WETH_USDT | 178 | 0.08% | 0.19% |
| WETH_DAI | 133 | 0.05% | 0.14% |
| WETH_WBTC | 164 | 0.09% | 0.25% |
| USDC_USDT | 169 | 0.07% | 0.21% |

- Profitable: **206** / 845 (24.4%)
- Gross profit: **$877,638.22**
- Net profit: **$402,379.84**
- Avg / Median net: $476.19 / $-23.06

### Top 10 Sandwich Attackers

| Attacker | Count | Net Profit (USD) |
|----------|-------|-----------------|
| `0x00000000…0f594e` | 33 | $231,432.98 |
| `0x00000000…416b40` | 55 | $112,393.30 |
| `0xe8c060f8…38a2e5` | 38 | $56,577.63 |
| `0x93dabae1…955579` | 1 | $34,264.40 |
| `0x7cf09d7a…d1604f` | 6 | $16,937.66 |
| `0x00000000…4e8987` | 19 | $11,418.62 |
| `0x90414447…b275e6` | 1 | $9,086.68 |
| `0xf70a5d55…511b79` | 1 | $7,125.03 |
| `0xd78a3280…486d44` | 5 | $7,031.14 |
| `0x83f893cc…dec77e` | 4 | $5,638.26 |

![Sandwich Timeline](analysis/output/02_sandwich_timeline.png)
![Profit Distribution](analysis/output/03_profit_distribution.png)
![Top Attackers](analysis/output/04_top_attackers.png)

## 5. Displacement Frontrunning

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

![Displacement](analysis/output/07_displacement.png)

## 6. Arbitrage / Back-running

Back-running occurs when an entity detects a large swap and immediately trades in the **opposite direction** to profit from the price reversion after the large trade's impact.

- Total back-run events: **4,796**
- Net profit: **$17,024,829.75**
- Avg net profit: **$3,549.80**

### Top 5 Back-runners

| Entity | Events |
|--------|--------|
| `0xa57bd001…fdd6cf` | 332 |
| `0xa69babef…56e78c` | 262 |
| `0x51c72848…502a7f` | 181 |
| `0x860bd2db…d78f66` | 175 |
| `0x6b75d8af…009a80` | 175 |

![Arbitrage](analysis/output/08_arbitrage.png)

## 7. Suppression

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

![Suppression](analysis/output/09_suppression.png)

## 8. Gas Price Analysis

| Pair | Sandwich Block Gas | Normal Block Gas | Premium |
|------|-------------------|-----------------|---------|
| WETH_USDC | 25.67 Gwei | 23.05 Gwei | +11.4% |
| WETH_USDT | 20.99 Gwei | 19.42 Gwei | +8.1% |
| WETH_DAI | 66.48 Gwei | 22.09 Gwei | +201.0% |
| WETH_WBTC | 47.00 Gwei | 22.00 Gwei | +113.6% |
| USDC_USDT | 63.65 Gwei | 22.84 Gwei | +178.6% |

![Gas Analysis](analysis/output/05_gas_analysis.png)
![Price Timeseries](analysis/output/06_price_timeseries.png)

