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

$$
\text{GasCostUSD}
=
\frac{(\texttt{gas\_price}_{front}+\texttt{gas\_price}_{back})\times 150000}{10^{18}}
\times P_{\mathrm{ETH}}(B)
$$

The final net profit is defined as:

$$
\text{NetProfitUSD}
=
\text{ProfitUSD}
-
\text{GasCostUSD}
$$

In the implementation, `ProfitUSD` is obtained from the attacker’s net token balance after the two legs are completed, while `GasCostUSD` uses the fixed estimate of 150,000 gas per swap.

### 5.2 Back-run Profit

For back-running, profit is estimated from the back-runner’s net token output in the reacting transaction. The net token gain is converted into USD, and the gas cost of the back-run transaction is subtracted to obtain the final net profit.

The calculation follows the same general structure:

$$
\text{NetProfitUSD}
=
\text{ProfitUSD}
-
\text{GasCostUSD}
$$

Here, `ProfitUSD` denotes the USD value of the back-runner’s net token gain, and `GasCostUSD` is computed using the same fixed gas assumption and block-level ETH price. This provides a consistent valuation framework across the different detected MEV patterns.

### 5.3 Valuation and Price Conversion

USD valuation depends on token type and historical price information. Stablecoins such as USDC, USDT, and DAI are treated directly in USD terms. For WETH and other non-stablecoin assets, valuation is based on reserve-derived ETH prices and the historical ETH price index constructed during preprocessing.

This design allows profits from different pairs to be compared under a common unit of account. It also supports the later gas analysis and result summaries reported in the final output.



## 6. Results
### 6.1 Summary
### 6.2 Sandwich
### 6.3 Displacement
### 6.4 Back-running
### 6.5 Suppression
### 6.6 Gas Analysis

## 7. Discussion and Limitations

## 8. Conclusion

This project builds a complete workflow for analyzing MEV-related behavior on Uniswap V2 from historical on-chain data. It combines historical data collection, heuristic detection, and post-analysis of profit and gas characteristics. Through this workflow, raw event logs are transformed into structured evidence for later interpretation.

The results suggest that multiple likely MEV patterns can be identified from ordered swap data. Among the detected patterns, back-running is the most frequent, while sandwich attacks show more concentrated profitability. At the same time, the method is limited by on-chain visibility and cannot directly recover mempool competition or trader intent. Even so, it remains useful for studying transaction-ordering behavior on decentralized exchanges.

## 9. References

[1] Frontrunner jones and the raiders of the dark forest: An empirical study of frontrunning on the ethereum blockchain. Usenix security 2021.

[2] Quantifying Blockchain Extractable Value: How dark is the forest? SP 2022.