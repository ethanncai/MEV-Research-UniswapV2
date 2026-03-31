# MEV Frontrunning Analysis Report

## 1. Introduction and Objective

Uniswap V2 is a representative decentralized exchange based on the automated market maker (AMM) model. In this setting, the execution result of a swap can depend on its position in the transaction sequence of a block. This creates opportunities for MEV and related frontrunning behavior. This project studies such behavior on Uniswap V2 through historical on-chain transaction data collected from Ethereum mainnet.

The objective of this project is to build a reproducible workflow for MEV-oriented transaction analysis on Uniswap V2. The project collects historical event logs for selected trading pairs, converts them into structured swap records, and applies heuristic rules to detect four suspicious patterns: sandwich attacks, displacement frontrunning, back-running, and suppression. Based on the detected events, it further conducts profit estimation and gas analysis to summarize the observable impact of transaction-ordering strategies.

## 2. System Structure

This project is organized as a compact pipeline with three connected stages: data fetching, MEV pattern detection, and post-analysis. The fetching stage collects historical Uniswap V2 event logs from Ethereum mainnet through the Etherscan API. It works on block ranges, supports checkpoint-based resume, and uses parallel requests to improve efficiency. After collection, the raw logs are decoded into structured event records for later analysis.

```text
+------------------------------------------------------+
|                    Fetcher Module                    |
|  Block-range crawling | Resume | Parallel fetching   |
+------------------------------------------------------+
                        |
                        v
+------------------------------------------------------+
|                   Detection Module                   |
|  Sandwich | Displacement | Back-running |            |
|  Suppression                                         |
+------------------------------------------------------+
                        |
                        v
+------------------------------------------------------+
|                    Analysis Module                   |
|  Profit estimation | Gas analysis | Figures          |
+------------------------------------------------------+
```

The detection stage operates on structured swap data. It applies heuristic rules to identify suspicious trading behavior. In this project, the detector focuses on four categories: sandwich attacks, displacement frontrunning, back-running, and suppression. These patterns are inferred from transaction ordering, trade direction, and gas-related signals within the same block.

The analysis stage transforms detected candidates into interpretable results. It estimates potential profit, compares gas-related characteristics, and examines market impact. It also produces the final outputs used in the report, including result tables, charts, and export files. Under this design, the project can be understood as a workflow of data collection, detection, and analysis.

## 3. Data Crawling and Processing

### 3.1 Data Source

The data used in this project comes from Ethereum mainnet and is collected through the Etherscan API. The crawler targets a set of Uniswap V2 pair contracts selected for analysis. The main pairs are `WETH_USDC`, `WETH_USDT`, `WETH_DAI`, `WETH_WBTC`, and `USDC_USDT`. These pairs provide a consistent event-level dataset across major markets and form the basis of the later MEV analysis.

### 3.2 Event Types

The crawler collects four core Uniswap V2 event types: `Swap`, `Sync`, `Mint`, and `Burn`. `Swap` records user trading activity, `Sync` records reserve updates, `Mint` records liquidity addition, and `Burn` records liquidity removal. Raw logs returned by Etherscan are decoded into structured event records before storage. Among these events, `Swap` is the main input for frontrunning detection, while `Sync` is important for reserve tracking and price-related analysis.

### 3.3 Crawling Workflow

The crawling workflow is organized around block-range retrieval. For each pair contract, the fetcher requests logs over a block interval and receives raw event data from Etherscan. The returned logs are decoded and written into CSV files for downstream analysis. To support large historical ranges, the crawler includes retry logic for unstable responses, rate limiting with multi-key rotation, adaptive block stepping, and checkpoint-based resume. This allows interrupted jobs to continue from the last completed block instead of restarting from the beginning.

```text
Pair contract
     ↓
Block-range log requests
     ↓
Raw event logs
     ↓
Event decoding
     ↓
Structured records
     ↓
CSV storage + checkpoint update
```

**[Insert Figure 1 here: crawler workflow or pipeline diagram, if you have one.]**

### 3.4 Storage

The processed data is stored in a structured directory layout. Each trading pair is assigned its own folder. Each event type is written into a separate CSV file, such as `swaps.csv`, `syncs.csv`, `mints.csv`, and `burns.csv`. The crawler also maintains a checkpoint file to record progress and an error log to capture failed requests or API-related issues. This structure keeps the historical data organized and makes the dataset easy to reuse in later stages.

```text
data/
  checkpoint.json
  error.log
  WETH_USDC/
    swaps.csv
    syncs.csv
    mints.csv
    burns.csv
  WETH_USDT/
    swaps.csv
    syncs.csv
    mints.csv
    burns.csv
  ...
```

### 3.5 Why Processing Matters

This stage is essential because the later MEV analysis depends on precise on-chain ordering and well-structured event records. The fields `tx_index` and `log_index` are needed to reconstruct the execution order of swaps within a block. `gas_price` is required for priority-related analysis such as displacement and suppression. `Sync` events provide reserve information for reserve tracking and price reconstruction. The structured CSV output also makes it possible to rerun detection, profit estimation, and visualization without repeating the entire historical crawl.

## 4. Detection Method
<<<<<<< HEAD
The project implements a heuristic-based detection system to identify four primary types of MEV activities. These methods rely on analyzing the sequence of events within a single block, using `tx_index` and `log_index` to reconstruct the exact execution order.

### 4.1 Sandwich
The sandwich detection logic identifies a sequence where a "victim" trade is preceded and followed by trades from a single attacker entity.

* **Identification Logic**: The algorithm looks for three related transactions within the same block. An attacker first performs a "front-run" swap, followed by one or more victim swaps in the same direction, and concludes with a "back-run" swap by the attacker in the opposite direction.
* **Operational Rules**: The system validates that the attacker's two transactions belong to the same `from_address` and that the victim's transaction is "sandwiched" between them in the transaction index.

### 4.2 Displacement
Displacement occurs when an attacker identifies a pending transaction and executes an identical trade earlier by paying a higher gas fee.
* **Identification Logic**: The detector searches for transactions in the same block and same direction (e.g., both buying WETH) but from different entities.
* **Operational Rules**: A match is flagged if the earlier transaction (attacker) has a gas price significantly higher than the later one (victim). The code specifically applies a heuristic where the gas price ratio $\ge 1.5$ and the transaction index gap is within 5 positions.

### 4.3 Back-running
Back-running (often related to arbitrage) targets the price impact or state change caused by a large "trigger" transaction.
* **Identification Logic**: The system first identifies "trigger" trades that exceed the 90th percentile in volume for a specific pair.
* **Operational Rules**: It then looks for a subsequent transaction within 3 transaction positions in the same block that executes a trade in the opposite direction, capturing the price reversion or balancing the pool.

### 4.4 Suppression
Suppression involves an entity "clogging" a block with high-gas transactions to delay or exclude other users' trades.
* **Identification Logic**: The algorithm tracks the number of transactions sent by a single entity within one block.
* **Operational Rules**: It flags suppression if a single entity sends at least 3 swap transactions and the median gas price of these transactions is at least 1.5 times the median gas price of the entire block.

---

## 5. Profit Estimation

The analysis phase quantifies the economic outcomes of detected MEV activities by reconstructing token flows and subtracting transaction costs.

### 5.1 Sandwich Profit
The profit for a sandwich attack is calculated by analyzing the net balance change of the attacker's address across the front-run and back-run transaction pair within the same block.

* **Methodology**: The system identifies the initial token spend in the front-run swap and the subsequent token receipt in the back-run swap. The "Gross Profit" is the USD value of the surplus tokens held by the attacker after the sequence completes.
* **Formula**:
    $$Net\ Profit_{sandwich} = Gross\ Profit - Gas\ Cost$$
    Where:
    $$Gross\ Profit = (Token\ Out_{backrun} - Token\ In_{frontrun}) \times Price_{USD}$$
    $$Gas\ Cost = \sum (Gas\ Used \times Gas\ Price \times ETH\ Price)$$
* **Implementation**: As defined in `analyzers.py`, the system uses `ESTIMATED_GAS_PER_SWAP` to account for the gas consumed by both legs of the attack.

### 5.2 Back-run Profit
Back-run (Arbitrage) profit measures the gain from a single transaction that captures price imbalances created by a preceding large-volume trade.

* **Methodology**: The profit is derived from the net change in the attacker's balance for a specific token pair after the execution of the back-run swap. Since back-runs often involve competing in high-gas environments, the gas cost significantly impacts the final margin.
* **Formula**:
    $$Net\ Profit_{backrun} = Gross\ Profit - Gas\ Cost$$
    Where:
    $$Gross\ Profit = Net\ Token\ Gain \times Price_{USD}$$
    $$Gas\ Cost = Gas\ Used \times Gas\ Price \times ETH\ Price$$
* **Valuation**: For non-stablecoin pairs, the `Price_USD` is derived using the `Sync` event reserves to calculate the spot price, or through a historical index as implemented in the `_token_to_usd` helper function.


---
=======

The project uses a heuristic-based detection framework to identify four types of suspicious MEV-related behavior. All methods operate on structured swap records and rely on block-level execution order reconstructed from `tx_index` and `log_index`. The goal of this stage is not to prove malicious intent directly, but to identify transaction patterns that are strongly consistent with common MEV strategies.

### 4.1 Sandwich

A sandwich pattern describes a case in which one entity trades before and after another user's swap in the same block. The intuition is that the first trade opens a position, the intermediate trade moves the pool price, and the final trade closes the position after the price change.

In this project, a sandwich candidate is flagged when two swaps from the same entity appear in the same block and have opposite directions. Between these two swaps, there must be at least one swap from a different entity, and the intermediate swap must have the same direction as the attacker's first trade. This rule identifies a front-run, victim, and back-run sequence within the reconstructed transaction order.

### 4.2 Displacement

Displacement refers to a situation in which one trader obtains execution priority over another trader who is attempting a similar trade. The intuition is that both transactions target the same side of the market, but the earlier one gains an advantage by paying more for priority.

In this project, displacement is detected when two different entities trade in the same direction in the same block, the earlier transaction executes first, the gas price ratio is at least 1.5, and the transaction index gap is no more than 5 positions. These conditions are used as a conservative on-chain heuristic for priority-taking behavior.

### 4.3 Back-running

Back-running describes a rapid reaction to a large trade that has already changed pool conditions. The intuition is that a large trigger trade moves the price, and another trader responds in the opposite direction to exploit the resulting change.

In this project, the detector first identifies a trigger trade whose size is above the 90th percentile for that trading pair. It then searches for a swap from a different entity in the same block, within the next 3 transaction positions, and in the opposite direction. If these conditions are satisfied, the event is marked as a back-running candidate.

### 4.4 Suppression

Suppression refers to a block-level pattern in which one entity submits multiple aggressive swaps and may crowd out other activity through unusually high gas prices. The intuition is not to prove direct victim loss for every transaction, but to identify unusually dominant behavior within a single block.

In this project, suppression is flagged when a single entity sends at least 3 swap transactions in the same block and the median gas price of that entity's swaps is at least 3 times the median gas price of the block. This rule is used as a heuristic indicator of concentrated and aggressive priority bidding.


## 5. Profit Estimation

The analysis stage quantifies the economic outcomes of detected MEV activities by reconstructing token flows and subtracting transaction costs.

### 5.1 Sandwich Profit

For a detected sandwich, profit is estimated from the attacker’s net gain across the front-run and back-run legs. The token gains are converted into USD using block-level ETH prices, and the estimated gas cost is then deducted to obtain net profit.

The gas cost follows the fixed gas model used in the report:

```math
\text{GasCostUSD}
=
\frac{(\texttt{gas\_price}_{front}+\texttt{gas\_price}_{back})\times 150000}{10^{18}}
\times P_{\mathrm{ETH}}(B)
```

The final net profit is defined as:

```math
\text{NetProfitUSD}
=
\text{ProfitUSD}
-
\text{GasCostUSD}
```

In the implementation, `ProfitUSD` is obtained from the attacker’s net token balance after the two legs are completed, while `GasCostUSD` uses the fixed estimate of 150,000 gas per swap.

### 5.2 Back-run Profit

For back-running, profit is estimated from the back-runner’s net token output in the reacting transaction. The net token gain is converted into USD, and the gas cost of the back-run transaction is subtracted to obtain the final net profit.

The calculation follows the same general structure:

```math
\text{NetProfitUSD}
=
\text{ProfitUSD}
-
\text{GasCostUSD}
```

Here, `ProfitUSD` denotes the USD value of the back-runner’s net token gain, and `GasCostUSD` is computed using the same fixed gas assumption and block-level ETH price. This provides a consistent valuation framework across the different detected MEV patterns.

### 5.3 Valuation and Price Conversion

USD valuation depends on token type and historical price information. Stablecoins such as USDC, USDT, and DAI are treated directly in USD terms. For WETH and other non-stablecoin assets, valuation is based on reserve-derived ETH prices and the historical ETH price index constructed during preprocessing.

This design allows profits from different pairs to be compared under a common unit of account. It also supports the later gas analysis and result summaries reported in the final output.



>>>>>>> f3f08cfb584794d5ba81fdbe79ab90d7c9a9cfa8

## 6. Results

### 6.1 Summary
Across the analyzed dataset of over 1.3 million swaps, a total of 6,417 MEV-related events were confirmed.

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

### 6.2 Sandwich
Based on the detection rules defined in Section 4.1, a total of 845 sandwich incidents were identified. The following table summarizes the distribution across the five major trading pairs:

| Pair | Sandwiches | % Blocks | % Volume |
|------|-----------|---------|---------|
| WETH_USDC | 201 | 0.08% | 0.19% |
| WETH_USDT | 178 | 0.08% | 0.19% |
| WETH_DAI | 133 | 0.05% | 0.14% |
| WETH_WBTC | 164 | 0.09% | 0.25% |
| USDC_USDT | 169 | 0.07% | 0.21% |

**Key Financial Metrics:**
- **Profitable Events**: 198 / 845 (23.4%)
- **Gross Profit**: $891,887.84
- **Total Net Profit**: $417,952.46
- **Average / Median Net**: $494.62 / $-21.64

The results indicate that while the gross profit is substantial, the low profitability rate and negative median net profit highlight the significant impact of gas costs and the competitive nature of the MEV searcher market. A negative median suggests that more than half of the detected sandwich attempts resulted in a net loss after accounting for gas fees.

Furthermore, the sandwich attacker landscape shows extreme centralization, as shown in the top 10 attackers by net profit:

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

**Observations:**
* **Dominance**: The top two entities alone account for a massive share of the total net profit, suggesting that professional searchers with optimized infrastructure dominate the market.
* **Outliers**: Address `0x93dabae1…955579` realized over $30,000 in profit from a single event, indicating the detection of rare, extremely high-slippage opportunities.
* **Optimization**: Multiple top attackers use "0x0000" vanity addresses, a technical optimization used by sophisticated bots to minimize gas costs during execution.

### 6.3 Displacement
A total of 758 displacement events were detected. The defining characteristic was the extreme gas competition, with attackers paying over 2,200 times the victim's gas price on average.

> **[ACTION: 请在此处插入报告第6页的 "Top Displacement Entities" 表格。]**

| Entity | Events |
|--------|--------|
| `0xfbd4cdb4…794c37` | 82 |
| `0x66a9893c…dba8af` | 79 |
| `0x3328f7f4…309c49` | 58 |
| `0x3fc91a3a…2b7fad` | 21 |
| `0x80a64c6d…cd5d9e` | 20 |

### 6.4 Back-running
This was the most frequent (4,796 events) and most profitable category, generating over $17 million in net profit. It was most prevalent in the WETH_WBTC pair.

### 6.5 Suppression
Suppression was the rarest form (18 events) but showed the highest average gas premium (907.1x), indicating highly targeted block space manipulation.

### 6.6 Gas Analysis
The results show a clear correlation between MEV activity and increased network costs. In the WETH_DAI pair, blocks with sandwich attacks had a median gas price 201% higher than blocks without them.

> **[ACTION: 请在此处插入报告第8页的 "Median Gas Price Comparison" 柱状图。]**

![Gas Analysis](analysis/output/05_gas_analysis.png)

---

## 7. Discussion and Limitations

### 7.1 Discussion
The data suggests that **Back-running (Arbitrage)** remains the dominant and most lucrative MEV strategy on UniswapV2, likely due to the constant price fluctuations between different pools and exchanges. Conversely, **Sandwich attacks** are highly concentrated, with a small number of sophisticated "searchers" capturing the vast majority of the profits.

### 7.2 Limitations
The current analysis is subject to several constraints:
* **On-chain Visibility Only**: We cannot see the "Mempool" (pending transactions), meaning we can only infer intent from the final block execution order.
* **Heuristic Entity Identification**: Entities are identified solely by `from_address`. Sophisticated attackers using multiple accounts or sub-contracts may be undercounted.
* **Fixed Gas Estimates**: Profit calculations rely on recorded gas prices; however, complex internal transactions or MEV-Share/Flashbots bundles might have "hidden" costs or rebates not captured in standard on-chain logs.

## 8. Conclusion

This project builds a complete workflow for analyzing MEV-related behavior on Uniswap V2 from historical on-chain data. It combines historical data collection, heuristic detection, and post-analysis of profit and gas characteristics. Through this workflow, raw event logs are transformed into structured evidence for later interpretation.

The results suggest that multiple likely MEV patterns can be identified from ordered swap data. Among the detected patterns, back-running is the most frequent, while sandwich attacks show more concentrated profitability. At the same time, the method is limited by on-chain visibility and cannot directly recover mempool competition or trader intent. Even so, it remains useful for studying transaction-ordering behavior on decentralized exchanges.

## 9. References

[1] Frontrunner jones and the raiders of the dark forest: An empirical study of frontrunning on the ethereum blockchain. Usenix security 2021.

[2] Quantifying Blockchain Extractable Value: How dark is the forest? SP 2022.