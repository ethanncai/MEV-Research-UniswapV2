# COMP5566 — UniswapV2 & MEV Data Fetcher

This repository contains **UniswapV2 core contract references** and a **Python-based historical data fetcher** that pulls UniswapV2 event logs from Etherscan for downstream MEV analysis (sandwich attacks, front-running, etc.).

---

## Repository structure

```
COMP5566/
├── v2-core/                 # UniswapV2 Solidity contracts (reference)
│   ├── contracts/           # UniswapV2Pair, UniswapV2Factory, interfaces
│   └── ...
├── uniswap_fetcher/         # Python data fetcher package
│   ├── config.py            # YAML config loader
│   ├── csv_writer.py        # CSV output by pair and event type
│   ├── etherscan_client.py  # Etherscan API V2 client with retries
│   ├── event_decoder.py     # Swap / Sync / Mint / Burn decoder
│   ├── fetcher.py           # Block-range fetch, checkpoint resume
│   ├── main.py              # CLI entry point
│   ├── models.py            # Event dataclasses and topic constants
│   └── rate_limiter.py      # Multi-key rate limiting
├── config.yaml              # Fetcher config (pairs, limits, paths)
├── api_keys.txt             # Etherscan API keys (one per line)
├── requirements.txt         # Python dependencies
├── mev/                     # Virtual environment (create with instructions below)
└── data/                    # Output directory (created on first run)
    ├── checkpoint.json      # Resume state per pair
    └── <PAIR_NAME>/
        ├── swaps.csv
        ├── syncs.csv
        ├── mints.csv
        └── burns.csv
```

---

## Prerequisites

- **Python 3.9+**
- **Etherscan API key(s)** — [Etherscan API](https://etherscan.io/apis): Free tier is 3 calls/sec, 100k calls/day per key.

---

## Setup

### 1. Create and activate the virtual environment

```bash
cd COMP5566
python3 -m venv mev
source mev/bin/activate   # On Windows: mev\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure API keys

Put your Etherscan API key(s) in `api_keys.txt`, one per line (blank lines and lines starting with `#` are ignored). Multiple keys are rotated to increase effective rate and daily quota.

```
# api_keys.txt
YourEtherscanApiKey1
YourEtherscanApiKey2
```

### 4. Optional: adjust config

Edit `config.yaml` to change:

- **Block range**: `from_block` / `to_block` (omit to use “latest − 50000” to “latest”)
- **Trading pairs**: add or remove entries under `pairs` (each needs `address` and `name`)
- **Rate limits**: `calls_per_second` and `daily_limit` (e.g. 5/sec and 100k/day for Lite)
- **Paths**: `output_dir`, `checkpoint_file`, `api_keys_file`

---

## Usage

### Run the fetcher (maximize mode — default)

```bash
source mev/bin/activate
python -m uniswap_fetcher.main
```

With no block range given, the fetcher runs in **maximize mode**: it fetches from the earliest block (see `maximize_from_block` in `config.yaml`, default UniswapV2 deployment `10000835`) to the latest block, and uses **all API keys in rotation until their daily limits are exhausted**. Progress is checkpointed; the next run (e.g. next day) continues from where it stopped. This way you get as much data as possible without manually specifying ranges.

### Optional: specify block range

If you want a fixed range instead of “as much as possible”:

```bash
python -m uniswap_fetcher.main --from-block 19000000 --to-block 19100000
```

### Use a different config or API keys file

```bash
python -m uniswap_fetcher.main -c my_config.yaml --keys my_keys.txt
```

### Verbose logging

```bash
python -m uniswap_fetcher.main -v
```

### Interrupt and resume

You can stop the run with `Ctrl+C`. Progress is saved in `data/checkpoint.json`; the next run continues from the last block for each pair.

When **all API keys hit their daily limit**, the fetcher stops gracefully, saves progress, and exits. Run again the next day (or add more keys to `api_keys.txt`) to continue.

---

## Output format

Under `data/<PAIR_NAME>/` you get:

| File       | Contents |
|-----------|----------|
| `swaps.csv` | Swap events: `block_number`, `tx_hash`, `tx_index`, `log_index`, `timestamp`, `sender`, `to`, `amount0_in`, `amount1_in`, `amount0_out`, `amount1_out`, `gas_price` |
| `syncs.csv` | Sync events: `block_number`, `tx_hash`, `tx_index`, `log_index`, `timestamp`, `reserve0`, `reserve1` |
| `mints.csv` | Mint (add liquidity) events |
| `burns.csv` | Burn (remove liquidity) events |

For MEV analysis:

- **Order within a block**: `tx_index` and `log_index` define ordering; sandwich detection uses transactions that are adjacent in the same block.
- **Gas**: `gas_price` in `swaps.csv` supports front-running and priority analysis.
- **Reserves**: `syncs.csv` gives post-trade reserves; pair with `tx_hash` to get pre/post state per trade.

---

## Rate limits

- **Free**: 3 calls/sec, 100k calls/day per key.
- **Lite**: 5 calls/sec, 100k calls/day per key (set `calls_per_second: 5` in `config.yaml` if you use Lite).

The fetcher uses per-key rate limiting and daily counters, and rotates keys when one hits its daily limit. Transient “timeout / server busy” and rate-limit responses are retried with backoff.

---

## UniswapV2 reference (v2-core)

The `v2-core/` directory holds the official UniswapV2 Solidity contracts (Pair, Factory, interfaces). The fetcher is built to match these events:

- **Swap** — `Swap(address,uint256,uint256,uint256,uint256,address)`
- **Sync** — `Sync(uint112,uint112)`
- **Mint** — `Mint(address,uint256,uint256)`
- **Burn** — `Burn(address,uint256,uint256,address)`

No need to run or compile `v2-core` for the fetcher; it is here for reference and for aligning with the on-chain event layout.

---

## License

See the respective licenses under `v2-core/` (Uniswap) and the fetcher source files.
