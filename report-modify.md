# MEV Frontrunning Analysis Report

## 1. Introduction

Maximum Extractable Value (MEV) refers to the additional value that can be captured by influencing transaction ordering during block construction. On automated market maker (AMM) protocols such as Uniswap V2, the outcome of a swap depends not only on pool reserves and trade size, but also on where the transaction appears within the block. Transaction ordering is therefore economically meaningful and creates room for strategies such as frontrunning, back-running, and sandwiching.

This project examines MEV-related behavior on Uniswap V2 using historical Ethereum mainnet event logs. The analysis focuses on five major trading pairs: `WETH_USDC`, `WETH_USDT`, `WETH_DAI`, `WETH_WBTC`, and `USDC_USDT`. Based on structured swap records reconstructed from on-chain event data, the study identifies four suspicious patterns:

- Sandwich attacks
- Displacement frontrunning
- Arbitrage / back-running
- Suppression

The goal is not to infer intent from isolated transactions. Instead, the report develops a reproducible workflow for studying ordering-sensitive behavior on AMM markets. By combining swap ordering, gas-price signals, and profit-related estimates, the analysis evaluates how closely the observed patterns align with known MEV strategies.


## 2. System Workflow

The analysis is organized as a three-stage pipeline: data loading and preprocessing, MEV pattern detection, and post-analysis.

1. **Data loading and preprocessing**  
   Historical Uniswap V2 `Swap` and `Sync` event data are loaded from pair-specific CSV files. Numeric fields are cleaned, transactions are ordered by block position, and trader entities are heuristically identified.

2. **Detection of suspicious transaction-ordering patterns**  
   The detector scans block-level swap sequences and applies four rule-based heuristics to identify sandwich attacks, displacement frontrunning, arbitrage / back-running, and suppression.

3. **Post-analysis and visualization**  
   After detection, the system estimates profits where possible, analyzes gas-price behavior, summarizes pair-level statistics, and generates charts and export files.

Even without mempool data, this workflow provides a practical basis for comparing suspicious transaction-ordering patterns across major Uniswap V2 pairs. That limitation still matters, but ordered on-chain logs are sufficient to support a meaningful comparative analysis.


## 3. Data Collection and Processing

### 3.1 Crawler Outcome 

The crawler is implemented in Python (`uniswap_fetcher/`) and uses Etherscan's `getLogs` API to collect Uniswap V2 pair events from the Ethereum main network. This section no longer emphasizes the API mechanism, but summarizes the result data set.

The crawler covers the period from the early history of Uniswap V2 to March 2026, covering **14,639,489 blocks**. A total of **2,690,493** original logs were obtained, and **2,690,473** decoding records were retained after filtering and normalization. The five pairs of trading combinations included in the analysis are 'WETH_USDC', 'WETH_USDT', 'WETH_DAI', 'WETH_WBTC' and 'USDC_USDT'.

Under key rotation, rate limit and retry control, the whole collection process is completed within about **8 hours**. In order to support reprodacibility, the data obtained is also published on Kaggle for independent verification: 
**https://www.kaggle.com/datasets/chickenbilibili/uniswapv2-exchange-history**

 The decoded logs are exported to `Swap`, `Sync`, `Mint` and `Burn` CSV files under `data/<PAIR_NAME>/`.

**Pair contracts configured for this project** (each row is one `UniswapV2Pair` deployed address):

| `name` (output folder) | Pair contract (checksummed / config as stored) |
|------------------------|-----------------------------------------------|
| `WETH_USDC` | `0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc` |
| `WETH_USDT` | `0x0d4a11d5EEaaC28EC3F61d100daF4d40471f1852` |
| `WETH_DAI` | `0xA478c2975Ab1Ea89e8196811F51A7B7Ade33eB11` |
| `WETH_WBTC` | `0xBb2b8038a1640196FbE3e38816F3e67Cba72D940` |
| `USDC_USDT` | `0x3041CbD36888bECc7bbCBc0045E3B1f144466f5f` |

The default **maximization** mode starts from near the Uniswap V2 factory deployment (`maximize_from_block: 10000835`) and continues to move towards the tip of the chain, unless a limited `(from_block, to_block)` range is specified in `config.yaml`.



The project uses four Uniswap V2 event types:

**Swap**: Record the token exchange activity and use it as the main input for MEV detection.

**Sync**: Record reserve updates and support reserve tracking and ETH price reconstruction.

**Mint**: Record the increase in liquidity.

**Burn**: Record the removal of liquidity.


### 3.2 Entity Identification

Effective transaction entities are defined by heuristics. If the "sender" address is a known Uniswap V2 router, the system uses the "to" address as the actual entity; otherwise, it uses `sender` itself. This does not completely solve the problem of attribution, but it is a reasonable compromise to group the router-mediated exchange under the participants most directly involved in the transaction results.

### 3.3 Transaction Ordering and Direction Assignment

In order to reconstruct the execution order inside each block, the exchange is sorted by `block_number`, `tx_index` and `log_index`. Formally, the order in the block of the transaction is represented as:

$$
\mathrm{ord}(x) = (\mathrm{txIndex}_x,\ \mathrm{logIndex}_x)
$$

This sorting is the core of the analysis, because each detection rule depends on the relative position of the exchange operation in the same piece.



For each exchange, we will specify a binary direction:

`direction = 0`: token0 flows to pair

`direction = 1`: token1 flows to pair

When the input end is clear, the direction can be inferred directly from the non-zero input field. Otherwise, compare the decimal normalized mark input so that different mark units will not distort the directional distribution.

### 3.4 Price Reconstruction and Valuation Setup

In order to estimate profits in US dollars, the project established a historical ETH price index based on Uniswap V2 reserves. It first uses `WETH_USDC` to retain data. If this pair is not available, go back to `WETH_USDT`, and then `WETH_DAI`.

Stablecoins such as `USDC`, `USDT` and ``DAI` are directly regarded as dollar-denomination assets. 'WETH` uses the reconstructed ETH price sequence for conversion. WBTC" is valued by the dynamic BTC/ETH ratio derived from the "WETH_WBTC" pool reserves, which is more suitable for historical analysis than using fixed approximation.

### 3.5 Output Summary

Before the detector is executed, the crawler will generate the following event-level records:  **Sync**: 1,349,490；**Swap**: 1,315,097；**Mint**: 13,381；**Burn**: 12,505；**Total**: **2,690,473**

The subsequent detector output contains: **845** sandwich events；**758** displacement events；**3,593** arbitrage / back-running events；**18** suppression events

![Frontrun Overview](analysis/output/01_frontrun_overview.png)

**Figure 1.** Detected frontrunning activities by type and trading pair.

These test results constitute the empirical basis for later discussing profitability, gasoline price behavior and cross-differences.


## 4. Detection Method

### 4.1 Sandwich Attacks

#### 4.1.1 Intuition

A sandwich attack occurs when one entity trades before a victim transaction and then trades again after it in the same block. The first trade opens a position, the victim transaction moves the AMM price, and the second trade closes the position after that price movement. The attacker is therefore attempting to profit from the price impact created by the victim.

#### 4.1.2 Implementation Logic

The detector first identifies candidate blocks that contain at least three swaps and at least one repeated entity. Within each such block, swaps are grouped by entity, and the code searches for two swaps from the same entity with opposite directions.

A sandwich candidate is recorded when all of the following conditions are satisfied:

1. The same entity appears at least twice in the same block.
2. The two swaps have opposite directions.
3. The two swaps are different transactions.
4. At least one swap from a different entity lies strictly between them in execution order.
5. The intermediate swap has the same direction as the attacker's first trade.

These conditions are designed to recover the standard front-run → victim → back-run structure directly from ordered swap data.

#### 4.1.3 Profit Calculation Logic

For each detected sandwich, the project computes the attacker's net token gain across the front-run and back-run legs. Let the attacker's net token balances after both legs be `net_token0` and `net_token1`. These balances are then converted into USD using token-specific valuation rules.

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

Among the four detection categories, this is the most direct profit model because it evaluates the same-block round-trip position created by the attacker.

#### 4.1.4 Findings

A total of **845** sandwich attacks were detected. Among them, **179** have positive estimated net profit, so profitable cases account for about **21.2%** of all detected sandwiches.

The aggregate sandwich profitability is:

- Profitable: **179** / 845 (21.2%)
- Gross profit: **$668,920.24**
- Net profit: **$194,984.86**
- Avg / Median net: $230.75 / $-23.27

Sandwich profits are clearly uneven rather than broadly distributed. Many detected cases become small or negative once gas cost is included, while a smaller set of profitable events contributes a large share of the total gains.

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


### 4.2 Displacement Frontrunning

#### 4.2.1 Intuition

Displacement frontrunning describes a case in which one trader gains execution priority over another trader attempting a similar trade. The two transactions move in the same direction, but the earlier one pays more gas and is included first, potentially leaving the later trader with a worse execution result.

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

This is still a same-block heuristic rather than direct proof of frontrunning. Because mempool data are unavailable, the method cannot show whether the later trader originally expected to execute first. What it can show is a repeated pattern of close-proximity, same-direction trading accompanied by a meaningful gas-price advantage.

#### 4.2.3 Value / Profit Interpretation

Compared with sandwich attacks, displacement is harder to evaluate because the outcome depends on a counterfactual question: how much worse was the later trade because it lost priority? For that reason, the report does not treat displacement profit as directly realized profit in the same sense as a completed sandwich round trip.

However, the code does estimate the economic effect of this ordering advantage. It reports:

- the USD value of the frontrunner's swap,
- the USD value of the victim's swap,
- the frontrunner's estimated gas cost,
- the victim's estimated loss under the counterfactual benchmark, and
- an estimated profit signal derived from that loss.

The interpretation should therefore remain cautious: displacement is best treated as an ordering-advantage pattern with an estimated economic effect, not as a clean realized arbitrage payoff.

#### 4.2.4 Findings

A total of **758** displacement events were detected.

The gas-ratio statistics show strong skewness:

- Total displacement events: **758**
- Median gas ratio (frontrunner / victim): **3.2×**
- Pairs: WETH_USDC, WETH_USDT, WETH_DAI, WETH_WBTC, USDC_USDT

The gap between ordinary and extreme cases appears substantial. A few very large gas ratios pull the mean upward, while the median gives a more stable picture of typical same-block priority bidding.

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

This rule is meant to capture immediate reaction trades rather than broader multi-step arbitrage paths. In practice, it highlights traders who appear to respond quickly to a large price-moving transaction inside the same block.

#### 4.3.3 Profit Calculation Logic

For each detected back-runner, the project computes the net token output of the reaction trade and converts it into USD. To avoid circular pricing, the system uses the ETH price from the **previous block** as the fair-market reference, since the trigger trade in the current block has already changed the pool reserves and distorted the same-block price.

If the back-runner receives more of a token than it sends, the difference contributes to estimated profit. The resulting gross value is then reduced by estimated gas cost:

$$
\mathrm{NetProfitUSD} = \mathrm{ProfitUSD} - \mathrm{GasCostUSD}
$$

where:

$$
\mathrm{GasCostUSD} = \frac{g_{\mathrm{back}} \times 150000}{10^{18}} \times P_{\mathrm{ETH}}^{\mathrm{pre}}(B)
$$

Here $P_{\mathrm{ETH}}^{\mathrm{pre}}(B)$ denotes the ETH price from the block immediately before block $B$, which serves as an undistorted market reference.

This provides a workable profit proxy for comparing back-running opportunities across the analyzed pairs.

#### 4.3.4 Findings

A total of **3,593** arbitrage / back-running events were detected, making this the most frequent suspicious pattern in the dataset.

Estimated profitability is substantial:

- Total back-run events: **3,593**
- Net profit: **$9,895,543.96**
- Avg net profit: **$2,754.12**

Top 5 Back-runners are:

| Entity | Events |
|--------|--------|
| `0xa69babef…56e78c` | 210 |
| `0xa57bd001…fdd6cf` | 179 |
| `0x6b75d8af…009a80` | 153 |
| `0x51c72848…502a7f` | 141 |
| `0x860bd2db…d78f66` | 120 |

Back-running dominates the dataset both in frequency and in aggregate estimated profitability. That pattern is consistent with AMM market structure: large swaps create short-lived local imbalances, and traders able to react within the same block can often exploit them quickly.

#### 4.3.5 Figure

![Arbitrage](analysis/output/08_arbitrage.png)

**Figure 6.** Estimated net-profit distribution and pair-level counts for detected arbitrage / back-running events.


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

Suppression does not have a directly recoverable realized-profit formula from swap logs alone. Its economic role is therefore more indirect than sandwich or back-running. A suppressor may be protecting another strategy, overwhelming nearby competition, or exploiting temporary block-level ordering dominance.

For that reason, the report interprets suppression mainly through **gas premium**, **swap concentration**, and **block dominance**, rather than exact realized net profit.

#### 4.4.4 Findings

Only **18** suppression events were detected, making suppression the rarest pattern in the dataset.

However, the gas-premium signal is extremely strong:

- Total suppression events: **18**
- Median gas premium: **20.5×**

The distribution is heavily right-skewed, with a small number of extreme cases pulling the mean far above the median. This suggests that suppression is uncommon, but the observed cases are unusually aggressive in terms of gas-price competition.

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


## 5. Gas Price Analysis

Natural gas price is one of the most important priority indicators for on-chain transactions. Since the MEV strategy largely depends on the order of execution, natural gas price behavior provides supporting evidence for strategic bidding and intra-block competition.

In this project, the analysis of natural gas prices compared the gas price patterns in the suspect areas and the normal areas, particularly regarding activities related to sandwiches. Through a 2:2 comparison, it was found that the median gas price in the suspect areas was typically significantly higher than that in the normal areas.This premium is moderate in some pairs, but very large in others, indicating the intensity of natural gas competition in different markets.

Judging from the generated gas diagram, the main mode is very clear:

"WETH_USDC" and "WETH_USDT" show a slight increase in the price of natural gas in sandwich-related blocks.

`WETH_DAI`, `WETH_WBTC` and `USDC_USDT` show a greater natural gas premium.

This supports the view that natural gas price competition is an important support signal for mev-related activities, especially sandwich attacks and similar suppression behaviors.

Gas analysis enhances the broader interpretation of detected events. Suspicious transaction patterns not only occur during the transaction process, but also frequently appear in the gas prices paid to suppliers, with the aim of ensuring priority supply rights.

### Figure

![Gas Analysis](analysis/output/05_gas_analysis.png)

**Figure 8.** Median gas price in sandwich-related blocks versus normal blocks across the analyzed pairs.


## 6. Limitations

This study has several important limitations.

**On-Chain Visibility Only：**

This analysis only uses on-chain event data. Memory pool transactions that have not been successful, discarded or replaced cannot be observed. Therefore, the study cannot directly reproduce the complete competition process that occurred before the final block was included.

**Heuristic Entity Identification：**

The identity of the trader is inferred through the heuristic algorithm based on the router.This method improves the actual classification effect, but it may merge unrelated transactions together or separate activities belonging to the same trader.

**Simplified Gas Model：**

The cost of gas is estimated on the assumption of a fixed consumption of 150,000 units of gas per transaction. The actual gas usage may vary depending on the transaction, so the reported net profit value should be regarded as an estimate, not the exact actual result.

**Price Approximation；**

The valuation of the US dollar depends on the price of ether based on reserves, in which WBTC is converted from the "WETH_WBTC" reserve pool according to the dynamic BTC/ETH ratio to ensure the accuracy of historical data. In order to avoid cyclic pricing in arbitrage profit estimation, the system will use the Ethereum price of the previous block as a pre-impact reference value, but there may be an approximate error during high volatility.

**Threshold Sensitivity：**

These detection rules rely on heuristic thresholds—specifically the **displacement gas ratio (1.5x)**, the **pair-specific 90th percentile arbitrage trigger**, the **suppression gas premium (3x)**, and the **maximum same-block position gaps** for displacement and arbitrage—meaning that any adjustments to these parameters will fluctuate the detection volume and necessitate a recalibration of the balance between **false positives** and **false negatives**.

**Interpretation Caution：**

The report identifies patterns that are strongly consistent with known MEV strategies, but it does not prove malicious intent in every case. Some flagged events may reflect ordinary reactive trading or legitimate high-priority execution rather than explicit predatory behavior.


## 7. Conclusion

The project uses the historical event data of the Ethereum main network to build a complete workflow for detecting and analyzing advance transaction behaviors related to MEV on Uniswap V2. By combining structured transaction orders, heuristic entity identification, and follow-up analysis of profits and gas prices, the system converts the original event logs into explainable evidence of suspicious transaction order behavior.

These four market effect models have obvious different characteristics: ** arbitrage/reverse follow-up** is the most common and profitable mode; **pinch attack** is rare, but the profit concentration is high; **substitutional early trading** is an order advantage caused by gas differences, not a pure arbitrage behavior; and **suppression** is rare, but has a very high gas premium characteristics.

Although there are certain limitations in the transparency of the trading pool and some intuition-based assumptions, the analysis of ordered transaction data and transaction fee behavior provides a reliable and repeatable framework for the study of transaction sequences in Uniswap V2.

## 8. References

[1] Frontrunner jones and the raiders of the dark forest: An empirical study of frontrunning on the ethereum blockchain. Usenix security 2021.

[2] Quantifying Blockchain Extractable Value: How dark is the forest? SP 2022.
