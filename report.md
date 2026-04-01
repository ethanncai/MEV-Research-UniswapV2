# MEV Frontrunning Analysis Report


## 1. Introduction

Maximum Extractable Value (MEV) refers to the additional value that can be captured by controlling transaction ordering during block construction. On automated market maker (AMM) protocols such as Uniswap V2, swap execution depends directly on the order of transactions within a block. This creates opportunities for frontrunning, back-running, and other transaction-ordering strategies.

This project studies MEV-related behavior on Uniswap V2 using historical Ethereum mainnet event logs. The analysis focuses on five major trading pairs: `WETH_USDC`, `WETH_USDT`, `WETH_DAI`, `WETH_WBTC`, and `USDC_USDT`. Based on structured swap records reconstructed from on-chain event data, the project detects four suspicious patterns:

- Sandwich attacks
- Displacement frontrunning
- Arbitrage / back-running
- Suppression

The goal of the project is to build a reproducible workflow for MEV-oriented transaction analysis and to evaluate these suspicious behaviors through ordering patterns, gas-price signals, and profit-related estimates.

---

## 2. System Workflow

The system is organized as a three-stage pipeline: data loading and preprocessing, MEV pattern detection, and post-analysis.

1. **Data loading and preprocessing**  
   Historical Uniswap V2 `Swap` and `Sync` event data are loaded from pair-specific CSV files. Numeric fields are cleaned, transactions are ordered by block position, and trader entities are heuristically identified.

2. **Detection of suspicious transaction-ordering patterns**  
   The detector scans block-level swap sequences and applies four rule-based heuristics to identify sandwich attacks, displacement frontrunning, arbitrage / back-running, and suppression.

3. **Post-analysis and visualization**  
   After detection, the system estimates profits where possible, analyzes gas-price behavior, summarizes pair-level statistics, and generates charts and export files.

This workflow allows the entire analysis to be reproduced from structured historical event logs without relying on mempool data.

---

## 3. Data Collection and Processing

### 3.1 Ingestion stack (Etherscan API + Uniswap V2 `Pair`)

We do **not** scrape block-explorer HTML. Ingestion is implemented in Python (`uniswap_fetcher/`) and uses the **Etherscan HTTP API v2** only.

**API endpoint and query shape.** Calls use `GET https://api.etherscan.io/v2/api` with `module=logs`, `action=getLogs`, and `chainid=1` (Ethereum mainnet). The JSON payload is the same **event-log shape** you would expect from JSON-RPC `eth_getLogs`, but obtained through Etherscan’s gateway instead of a self-hosted node.

**Per-request filters.** Each call is constrained to:

- one **Uniswap V2 `Pair` contract** (the pool whose events we ingest), and  
- a **closed block interval** `[fromBlock, toBlock]` (inclusive endpoints).

**Pagination and adaptive block windows.** Etherscan returns at most **1000** logs per response (`offset=1000`). The fetcher therefore walks history in **block chunks**, not a single range. Chunk size is adaptive:

- Default step is on the order of **25k** blocks, clamped between **500** and **80k**.  
- If a chunk returns **1000** logs, the window is treated as **saturated**; the step **shrinks** and the overlapping range is refined until responses are not truncated.  
- If a chunk is **sparse**, the step **increases** to cut down the number of HTTP calls.

**API keys, rate limits, and retries.** Keys are listed in `api_keys.txt` (one per line) and **rotated** so each request is attributed to a single key. A **token-bucket limiter** enforces **calls per second** and tracks **daily** usage per key. On rate limits or transient failures (timeouts, “server busy”), the client retries with **exponential backoff** (up to **eight** attempts) over a persistent **`requests.Session`**.

**Checkpointing and optional parallelism.** For each pair, `data/checkpoint.json` stores the last completed block and cumulative per-event counts so a run can **resume** after quota exhaustion or `Ctrl+C`. Several pairs may be processed concurrently via a **thread pool**; workers share the same limiter so concurrency does not violate per-key caps.

**Decoding and on-disk layout.** Raw logs are decoded offline with **`eth_abi`** into `Swap`, `Sync`, `Mint`, and `Burn` records (selected by **`topic0`** = keccak event signature). Outputs are append-friendly CSVs under `data/<PAIR_NAME>/`: `swaps.csv`, `syncs.csv`, `mints.csv`, `burns.csv`.

**Public repository.** The collected datasets, the fetcher, and the analysis code are hosted on GitHub so reviewers can **clone a frozen snapshot** without re-querying Etherscan:

**https://github.com/ethanncai/MEV-Analyzer**

That repository is intended to match the on-disk tree used here (`data/<PAIR_NAME>/`, checkpoints, configuration files, and processing scripts).

**Pair contracts configured for this project** (each row is one `UniswapV2Pair` deployed address):

| `name` (output folder) | Pair contract (checksummed / config as stored) |
|------------------------|-----------------------------------------------|
| `WETH_USDC` | `0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc` |
| `WETH_USDT` | `0x0d4a11d5EEaaC28EC3F61d100daF4d40471f1852` |
| `WETH_DAI` | `0xA478c2975Ab1Ea89e8196811F51A7B7Ade33eB11` |
| `WETH_WBTC` | `0xBb2b8038a1640196FbE3e38816F3e67Cba72D940` |
| `USDC_USDT` | `0x3041CbD36888bECc7bbCBc0045E3B1f144466f5f` |

Default **maximize** mode starts near Uniswap V2 factory deployment (`maximize_from_block: 10000835`) and advances toward chain tip unless a finite `(from_block, to_block)` is set in `config.yaml`.

### 3.2 Event Types

The project uses the following Uniswap V2 event types:

- **Swap**: records token exchange activity and serves as the primary input for MEV detection.
- **Sync**: records reserve updates and is used for reserve tracking and ETH price reconstruction.
- **Mint**: records liquidity additions.
- **Burn**: records liquidity removals.

Among these, `Swap` and `Sync` are the most important for the final analysis.

### 3.3 Entity Identification

The effective trading entity is defined heuristically. If the `sender` address is a known Uniswap V2 router, the system uses the `to` address as the actual entity; otherwise, it uses the `sender` itself. This design attempts to recover the real trader behind router-mediated transactions.

### 3.4 Transaction Ordering

To reconstruct the execution order inside each block, swaps are sorted by `block_number`, `tx_index`, and `log_index`. Formally, the in-block order of a transaction is represented as:

$$
\mathrm{ord}(x) = (\mathrm{txIndex}_x,\ \mathrm{logIndex}_x)
$$

This ordering is essential because all four detection methods rely on the exact relative position of swaps inside the same block.

### 3.5 Trade Direction Assignment

For each swap, the project assigns a binary direction:

- `direction = 0`: token0 flows into the pair
- `direction = 1`: token1 flows into the pair

If the input side is unambiguous, the direction is inferred directly from the non-zero input field. Otherwise, the system compares decimal-normalized token inputs to avoid bias caused by different token units.

### 3.6 Price Reconstruction and Valuation Setup

To estimate profits in USD terms, the system builds a historical ETH price index from Uniswap V2 reserves. It first uses `WETH_USDC` reserve data. If this pair is unavailable, it falls back to `WETH_USDT` and then `WETH_DAI`.

Stablecoins such as `USDC`, `USDT`, and `DAI` are treated directly as USD-denominated assets. `WETH` is converted using the reconstructed ETH price series. `WBTC` is converted using an approximate fixed ratio to ETH:

$$
\mathrm{BTCETHRatioApprox} = 15.0
$$

### 3.7 Output Summary

The final detected output contains:

- **845** sandwich events
- **758** displacement events
- **4,796** arbitrage / back-running events
- **18** suppression events

![Frontrun Overview](analysis/output/01_frontrun_overview.png)

**Figure 1.** Detected frontrunning activities by type and trading pair.


These outputs form the basis of the later detection analysis and gas-price discussion.

---

## 4. Detection Method

### 4.1 Sandwich Attacks

#### 4.1.1 Intuition

A sandwich attack occurs when one entity places a trade before a victim transaction and another trade after it in the same block. The front-run opens a position, the victim trade moves the AMM price, and the back-run closes the position after the induced price change.

#### 4.1.2 Implementation Logic

The detector first identifies candidate blocks that contain at least three swaps and at least one repeated entity. Inside each such block, it groups swaps by entity and searches for two swaps from the same entity with opposite directions.

A sandwich candidate is recorded when all of the following conditions are satisfied:

1. The same entity appears at least twice in the same block.
2. The two swaps have opposite directions.
3. The two swaps are different transactions.
4. At least one swap from a different entity lies strictly between them in execution order.
5. The intermediate swap has the same direction as the attacker's first trade.

This logic reconstructs a standard front-run -> victim -> back-run sequence directly from ordered swap data.

#### 4.1.3 Profit Calculation Logic

For each detected sandwich, the project computes the attacker's net token gain across the front-run and back-run legs. Let the attacker's net token balances after both legs be `net_token0` and `net_token1`. These are converted into USD using token-specific valuation rules.

The gross profit is:

$$
\mathrm{ProfitUSD} = \mathrm{USD}(n_0) + \mathrm{USD}(n_1)
$$

Gas cost is estimated using a fixed gas model of 150,000 gas per swap:

$$
\mathrm{GasCostUSD} = \frac{(g_{\mathrm{front}} + g_{\mathrm{back}}) \times 150000}{10^{18}} \times P_{\mathrm{ETH}}(B)
$$

The final estimated net profit is:

$$
\mathrm{NetProfitUSD} = \mathrm{ProfitUSD} - \mathrm{GasCostUSD}
$$

This is the most direct and complete profit model among the four detection categories.

#### 4.1.4 Findings

A total of **845** sandwich attacks were detected. Among them, **198** have positive estimated net profit, which means that profitable events account for about **23.4%** of all detected sandwiches.

The aggregate sandwich profitability is:

- Profitable: **206** / 845 (24.4%)
- Gross profit: **$877,638.22**
- Net profit: **$402,379.84**
- Avg / Median net: $476.19 / $-23.06

These results suggest that sandwich profitability is highly concentrated. Many detected cases generate low or negative net profit after gas costs, while a relatively small number of highly profitable attacks contribute a large fraction of total gains.

Pair-level sandwich counts are as follows:

| Pair | Sandwiches | % Blocks | % Volume |
|------|-----------|---------|---------|
| WETH_USDC | 201 | 0.08% | 0.19% |
| WETH_USDT | 178 | 0.08% | 0.19% |
| WETH_DAI | 133 | 0.05% | 0.14% |
| WETH_WBTC | 164 | 0.09% | 0.25% |
| USDC_USDT | 169 | 0.07% | 0.21% |

#### 4.1.5 Figure 

![Sandwich Timeline](analysis/output/02_sandwich_timeline.png)

**Figure 2.** Monthly number of detected sandwich attacks across the analyzed pairs.

![Profit Distribution](analysis/output/03_profit_distribution.png)

**Figure 3.** Distribution of estimated sandwich net profit, including the skewness of profitable cases.

![Top Attackers](analysis/output/04_top_attackers.png)

**Figure 4.** Top sandwich attackers by event count and cumulative estimated net profit.

---

### 4.2 Displacement Frontrunning

#### 4.2.1 Intuition

Displacement frontrunning describes a case in which one trader obtains execution priority over another trader attempting a similar trade. Both transactions move in the same direction, but the earlier one pays more gas and is executed first, potentially leaving the later trader with a worse execution result.

#### 4.2.2 Implementation Logic

The detector scans pairs of swaps inside the same block and flags a displacement event when all of the following conditions hold:

1. The two swaps belong to different entities.
2. The two swaps have the same direction.
3. The first swap executes earlier in the block (`tx_index` strictly smaller).
4. The transactions are within five transaction positions of each other.
5. The gas-price ratio satisfies:

$$
\frac{g_f}{g_v} \ge 1.5
$$

Here, the first transaction is treated as the potential frontrunner and the later transaction as the potential victim.

This is a conservative same-block heuristic. It does not directly observe the mempool and therefore cannot prove that the victim originally intended to execute first.

#### 4.2.3 Value / Profit Interpretation

Unlike sandwich attacks, displacement does not yield a clean realized-profit formula from swap data alone. The code therefore does **not** reconstruct a strict counterfactual profit. Instead, it reports:

- the USD value of the frontrunner's swap,
- the USD value of the victim's swap, and
- the frontrunner's estimated gas cost.

The economic interpretation is that the frontrunner obtains an execution advantage by paying more for priority. In other words, the observed benefit is primarily an **ordering advantage** rather than a directly closed-form arbitrage profit.

#### 4.2.4 Findings

A total of **758** displacement events were detected.

The gas-ratio statistics show strong skewness:

- Total displacement events: **758**
- Avg gas ratio (frontrunner / victim): **2258.79×**
- Pairs: WETH_USDC, WETH_USDT, WETH_DAI, WETH_WBTC, USDC_USDT

The very large mean indicates the presence of extreme outliers, while the median gives a more stable picture of typical same-block priority bidding.

Top 5 Displacement Frontrunners are:

| Entity | Events |
|--------|--------|
| `0xfbd4cdb4…794c37` | 82 |
| `0x66a9893c…dba8af` | 79 |
| `0x3328f7f4…309c49` | 58 |
| `0x3fc91a3a…2b7fad` | 21 |
| `0x80a64c6d…cd5d9e` | 20 |


#### 4.2.5 Figure 

![Displacement](analysis/output/07_displacement.png)

**Figure 5.** Distribution of displacement gas ratios and pair-level event counts.

---

### 4.3 Arbitrage / Back-running

#### 4.3.1 Intuition

Arbitrage / back-running occurs when a trader reacts immediately after a large trade that has already changed the pool price. The trigger trade creates temporary price impact, and the back-runner exploits the resulting imbalance with an opposite-direction swap.

#### 4.3.2 Implementation Logic

The detector first computes a trade-size measure for each swap as the larger of the two decimal-normalized token inputs. A swap is treated as a trigger trade if its size is above the pair-specific 90th percentile:

$$
S(t) \ge Q_{0.90}(S)
$$

For each trigger trade, the detector searches for a later swap in the same block such that:

1. it belongs to a different entity,
2. it has the opposite direction,
3. it occurs within the next three transaction positions.

When these conditions are satisfied, the follower is recorded as an arbitrage / back-running event.

#### 4.3.3 Profit Calculation Logic

For each detected back-runner, the project computes the net token output of the reaction trade and converts it into USD. If the back-runner receives more of a token than it sends, the difference contributes to estimated profit.

The resulting gross value is then reduced by estimated gas cost:

$$
\mathrm{NetProfitUSD} = \mathrm{ProfitUSD} - \mathrm{GasCostUSD}
$$

where:

$$
\mathrm{GasCostUSD} = \frac{g_{\mathrm{back}} \times 150000}{10^{18}} \times P_{\mathrm{ETH}}(B)
$$

This gives a consistent profit proxy for comparing back-running opportunities across pairs.

#### 4.3.4 Findings

A total of **3,593** arbitrage / back-running events were detected, making this the most frequent suspicious pattern in the dataset.

Estimated profitability is substantial:

- Total back-run events: **4,796**
- Net profit: **$17,024,829.75**
- Avg net profit: **$3,549.80**

Top 5 Back-runners are:

| Entity | Events |
|--------|--------|
| `0xa69babef…56e78c` | 210 |
| `0xa57bd001…fdd6cf` | 179 |
| `0x6b75d8af…009a80` | 153 |
| `0x51c72848…502a7f` | 141 |
| `0x860bd2db…d78f66` | 120 |


#### 4.3.5 Figure 

![Arbitrage](analysis/output/08_arbitrage.png)

**Figure 6.** Estimated net-profit distribution and pair-level counts for detected arbitrage / back-running events.

---

### 4.4 Suppression

#### 4.4.1 Intuition

Suppression refers to block-level behavior in which one entity submits multiple high-gas swap transactions within the same block, potentially crowding out other market participants or dominating block-level execution.

#### 4.4.2 Implementation Logic

The detector first computes the median gas price for each block. It then aggregates swaps by `(block_number, entity)` and flags a suppression candidate when:

1. one entity submits at least three swaps in the same block, and
2. the entity's median gas price is at least three times the block median.

Formally, the gas-premium threshold is:

$$
\mathrm{GasPremium} = \frac{\mathrm{EntityMedianGas}}{\mathrm{BlockMedianGas}} \ge 3.0
$$

This detector is intentionally heuristic. It is designed to identify unusually aggressive same-block gas bidding, not to prove direct victim loss in every case.

#### 4.4.3 Value / Profit Interpretation

Suppression does not have a directly recoverable realized-profit formula from swap logs alone. Its economic role is more indirect than sandwich or back-running. A suppressor may be:

- protecting another strategy,
- overwhelming local competition,
- or exploiting temporary block-level ordering dominance.

For this reason, the report interprets suppression primarily through **gas premium**, **swap concentration**, and **block dominance**, rather than exact realized net profit.

#### 4.4.4 Findings

Only **18** suppression events were detected, making suppression the rarest pattern in the dataset.

However, the gas-premium signal is extremely strong:

- Total suppression events: **18**
- Avg gas premium: **907.1×**

The large gap between mean and median again indicates heavy-tailed outliers.

Top 5 Suppressors are:

| Entity | Events |
|--------|--------|
| `0x6b75d8af…009a80` | 10 |
| `0x1f2f10d1…6df387` | 3 |
| `0x00000000…120e49` | 1 |
| `0x3328f7f4…309c49` | 1 |
| `0x7c63795c…bcfde8` | 1 |



#### 4.4.5 Figure 

![Suppression](analysis/output/09_suppression.png)

**Figure 7.** Gas-premium distribution and pair-level counts for detected suppression events.

---

## 5. Gas Price Analysis

Gas price is one of the most important on-chain proxies for transaction priority. Since MEV strategies depend heavily on execution order, gas-price behavior provides supporting evidence for strategic bidding and competition within blocks.

The gas analysis in this project compares gas-price patterns between suspicious blocks and ordinary blocks, especially for sandwich-related activity.

The pair-level comparison shows that suspicious blocks often have noticeably higher median gas prices than normal blocks. This premium is modest in some pairs but extremely large in others, suggesting that gas competition differs substantially across markets.

From the generated gas chart, the main pattern is clear:

- `WETH_USDC` and `WETH_USDT` show moderate gas premiums in sandwich-related blocks.
- `WETH_DAI`, `WETH_WBTC`, and `USDC_USDT` show much larger gas premiums.
- This supports the idea that gas-price competition is an important supporting signal for MEV-related activity, particularly sandwich attacks and suppression-like behavior.

The gas analysis therefore strengthens the interpretation of the detected events: suspicious transaction-ordering patterns are not only visible in block order, but also often accompanied by unusually strong gas-price signals.

### Figure 

![Gas Analysis](analysis/output/05_gas_analysis.png)

**Figure 8.** Median gas price in sandwich-related blocks versus normal blocks across the analyzed pairs.

---

## 6. Limitation

This study has several important limitations.

- **On-Chain Visibility Only**

The analysis uses on-chain event data only. Failed, dropped, or replaced mempool transactions are not observable. As a result, the study cannot directly reconstruct the full competition process that happened before final block inclusion.

- **Heuristic Entity Identification**

Trader identity is approximated using a router-based heuristic. When a transaction is sent through a known router, the `to` address is treated as the actual entity; otherwise, the `sender` is used. This improves practical grouping, but it may still merge unrelated transactions or split activity that belongs to the same trader.

- **Simplified Gas Model**

Gas cost is estimated using a fixed assumption of **150,000 gas per swap**. Actual gas usage may vary across transactions, so reported net profit values should be interpreted as estimates rather than exact realized outcomes.

- **Price Approximation**

USD valuation relies on reserve-derived ETH prices and a fixed approximate conversion rule for WBTC. Although this makes consistent comparison possible, it introduces approximation error, especially in volatile periods.

- **Threshold Sensitivity**

Several detection rules depend on heuristic thresholds, including:

- displacement gas ratio threshold (`1.5x`),
- arbitrage trigger threshold (pair-specific `90th percentile`),
- suppression gas premium threshold (`3x`),
- maximum same-block position gaps for displacement and arbitrage.

Changing these thresholds would change the number of detected events and may affect the balance between false positives and false negatives.

- **Interpretation Caution**

The report identifies patterns that are strongly consistent with known MEV strategies, but it does not prove malicious intent in every case. Some flagged events may reflect ordinary reactive trading or legitimate high-priority execution rather than explicit predatory behavior.

---

## 7. Conclusion

This project builds a complete workflow for detecting and analyzing MEV-related frontrunning behavior on Uniswap V2 using historical Ethereum mainnet event data. By combining structured swap ordering, heuristic entity identification, and post-analysis of profits and gas prices, the system transforms raw event logs into interpretable evidence of suspicious transaction-ordering behavior.

The results show that different MEV patterns exhibit different economic characteristics:

- **Sandwich attacks** are less frequent than back-running but show concentrated profitability.
- **Displacement frontrunning** is best understood as an ordering-advantage signal supported by gas asymmetry.
- **Arbitrage / back-running** is the most frequent pattern and contributes the largest aggregate estimated profit.
- **Suppression** is rare but associated with extreme gas-price premiums.

Overall, the analysis shows that ordered swap data and gas-price behavior together provide a useful basis for studying MEV on AMM-based decentralized exchanges. Although the approach is limited by the absence of mempool visibility and by heuristic assumptions, it remains a practical and reproducible framework for investigating transaction-ordering behavior on Uniswap V2.

## 8. References

[1] Frontrunner jones and the raiders of the dark forest: An empirical study of frontrunning on the ethereum blockchain. Usenix security 2021.

[2] Quantifying Blockchain Extractable Value: How dark is the forest? SP 2022.
