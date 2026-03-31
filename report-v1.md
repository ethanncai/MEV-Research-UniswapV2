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

## 9. References