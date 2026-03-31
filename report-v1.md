# MEV Frontrunning Analysis Report

## 1. Introduction and Objective

## 2. System Structure

## 3. Data Crawling and Processing

## 4. Detection Method
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

## 5. Profit and Impact Analysis
The analysis phase quantifies the economic outcomes and network effects of the detected MEV activities.

## 5. Profit and Impact Analysis

The analysis phase quantifies the economic outcomes and network effects of the detected MEV activities by reconstructing token flows and estimating gas expenditures.

### 5.1 Profit Calculation Methodology
The profit calculation follows a standardized pipeline to convert on-chain swaps into a comparable net USD value:

* **Gross Profit Reconstruction**: For each MEV event, the system calculates the net balance change of the involved tokens. 
    * **Sandwich**: Sum of token changes from both the front-run and back-run transactions.
    * **Arbitrage/Back-run**: The net token gain from the single or atomic set of arbitrage swaps.
* **USD Normalization**: Profits are converted to USD based on the spot price at the time of the transaction.
    * Stablecoins (USDC, USDT, DAI) are treated as $1.
    * WETH price is derived from `Sync` events or a historical index.
    * WBTC is valued using a fixed `BTC_ETH_RATIO_APPROX`.
* **Net Profit Formula**: As shown in the research framework, the net profit is the gross profit minus the estimated gas cost:
    $$Net\ Profit = Gross\ Profit\ (USD) - (Gas\ Used \times Gas\ Price \times ETH\ Price)$$
    *Note: A constant `ESTIMATED_GAS_PER_SWAP` is applied to account for the overhead of standard UniswapV2 interactions.*

> **[ACTION: 请在此处插入报告中展示利润计算公式和逻辑步骤的截图（对应 image_21fc41.png）。]**

### 5.2 Results Distribution
The financial impact is visualized through cumulative growth and individual event distributions:
* **Cumulative Net Profit**: Tracks the aggregate earnings over the analyzed period, highlighting phases of high MEV activity.
* **Profit Distribution**: Analyzes the frequency of profit magnitudes, revealing that while many events have small margins, the total profit is heavily driven by high-value outliers.

> **[ACTION: 请在此处插入 "Cumulative Net Profit over Time" 曲线图（对应 image_1f2fa2.png）。]**
> **[ACTION: 请在此处插入 "Arbitrage / Back-run Profit Distribution" 直方图（对应 image_1f2fd8.png）。]**

### 5.3 Market Impact (Gas Analysis)
The system evaluates how MEV competition affects the broader network:
* **Gas Premium**: Measured as the ratio of the MEV transaction's gas price to the block's median gas price.
* **Network Crowding**: High-frequency attacks (like Suppression) are analyzed for their role in inflating block-level gas costs, which impacts the execution environment for regular users.
* **Market Impact**: Beyond direct profit, the system measures "Gas Premium." It compares the median gas price of "attack blocks" (blocks containing MEV) against "normal blocks" to quantify how MEV competition drives up costs for average users.

---

## 6. Results

### 6.1 Summary
Across the analyzed dataset of over 1.3 million swaps, a total of 6,417 MEV-related events were confirmed.

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

### 6.2 Sandwich
Detection identified 845 sandwich incidents. While the success rate (profitability) was approximately 24.4%, the total net profit reached $402,379.84. 

> **[ACTION: 请在此处插入报告第5页的 "Top 10 Sandwich Attackers by Net Profit" 表格。]**

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

## 9. References