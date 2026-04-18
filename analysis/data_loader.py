"""
Load and preprocess UniswapV2 swap/sync CSV data for all trading pairs.
"""
import os
import pandas as pd
import numpy as np
from config import DATA_DIR, PAIR_CONFIG, KNOWN_ROUTERS


def load_pair_data(pair_name):
    pair_dir = os.path.join(DATA_DIR, pair_name)

    swaps = pd.read_csv(os.path.join(pair_dir, 'swaps.csv'))
    syncs = pd.read_csv(os.path.join(pair_dir, 'syncs.csv'))

    swap_numeric = ['block_number', 'tx_index', 'log_index', 'timestamp',
                    'amount0_in', 'amount1_in', 'amount0_out', 'amount1_out', 'gas_price']
    for col in swap_numeric:
        if col in swaps.columns:
            swaps[col] = pd.to_numeric(swaps[col], errors='coerce').fillna(0)

    sync_numeric = ['block_number', 'tx_index', 'log_index', 'timestamp', 'reserve0', 'reserve1']
    for col in sync_numeric:
        if col in syncs.columns:
            syncs[col] = pd.to_numeric(syncs[col], errors='coerce').fillna(0)

    swaps['sender'] = swaps['sender'].astype(str).str.lower()
    swaps['to'] = swaps['to'].astype(str).str.lower()

    is_router = swaps['sender'].isin(KNOWN_ROUTERS)
    swaps['entity'] = np.where(is_router, swaps['to'], swaps['sender'])

    # direction 0 = token0 flows in (sell token0 / buy token1)
    # direction 1 = token1 flows in (sell token1 / buy token0)
    cfg = PAIR_CONFIG[pair_name]
    d0, d1 = cfg['token0_decimals'], cfg['token1_decimals']
    # Fallback compares decimal-normalised amounts so that raw unit magnitude
    # differences between tokens (e.g. 1e18 WETH vs 1e6 USDC) do not bias
    # the direction assignment.
    norm0_in = swaps['amount0_in'] / (10 ** d0)
    norm1_in = swaps['amount1_in'] / (10 ** d1)
    swaps['direction'] = np.where(
        (swaps['amount0_in'] > 0) & (swaps['amount1_in'] == 0), 0,
        np.where(
            (swaps['amount1_in'] > 0) & (swaps['amount0_in'] == 0), 1,
            np.where(norm0_in >= norm1_in, 0, 1)
        )
    ).astype(int)

    swaps.sort_values(['block_number', 'tx_index', 'log_index'], inplace=True)
    swaps.reset_index(drop=True, inplace=True)
    syncs.sort_values(['block_number', 'tx_index', 'log_index'], inplace=True)
    syncs.reset_index(drop=True, inplace=True)

    return {'swaps': swaps, 'syncs': syncs}


def load_all_pairs():
    data = {}
    for pair_name in PAIR_CONFIG:
        pair_dir = os.path.join(DATA_DIR, pair_name)
        if not os.path.isdir(pair_dir):
            continue
        print(f"  Loading {pair_name} ...")
        pair = load_pair_data(pair_name)
        print(f"    {len(pair['swaps']):,} swaps, {len(pair['syncs']):,} syncs")
        data[pair_name] = pair
    return data


def build_eth_price_index(pair_data):
    """
    Build a Series mapping block_number -> ETH price in USD using WETH_USDC reserves.
    Falls back to WETH_USDT / WETH_DAI if WETH_USDC is unavailable.
    """
    for source_pair, cfg in [('WETH_USDC', PAIR_CONFIG['WETH_USDC']),
                              ('WETH_USDT', PAIR_CONFIG['WETH_USDT']),
                              ('WETH_DAI',  PAIR_CONFIG['WETH_DAI'])]:
        if source_pair not in pair_data:
            continue
        syncs = pair_data[source_pair]['syncs'].copy()
        d0 = cfg['token0_decimals']
        d1 = cfg['token1_decimals']
        r0 = syncs['reserve0'].astype(float) / (10 ** d0)
        r1 = syncs['reserve1'].astype(float) / (10 ** d1)

        if cfg['usd_token'] == 0:
            syncs['eth_price'] = np.where(r1 > 0, r0 / r1, np.nan)
        else:
            syncs['eth_price'] = np.where(r0 > 0, r1 / r0, np.nan)

        syncs.dropna(subset=['eth_price'], inplace=True)
        price_idx = syncs.groupby('block_number')['eth_price'].last().sort_index()
        price_idx = price_idx[(price_idx > 10) & (price_idx < 100_000)]
        if len(price_idx) > 0:
            return price_idx

    return pd.Series(dtype=float)


def build_btc_eth_index(pair_data):
    """
    Build a Series mapping block_number -> BTC/ETH ratio using WETH_WBTC
    pool reserves.  This replaces the fixed BTC_ETH_RATIO_APPROX constant
    and gives a historically-accurate conversion for WBTC -> USD.

    BTC/ETH ratio = WETH_reserve / WBTC_reserve  (how many ETH per 1 BTC)
    """
    if 'WETH_WBTC' not in pair_data:
        return pd.Series(dtype=float)

    cfg = PAIR_CONFIG['WETH_WBTC']
    syncs = pair_data['WETH_WBTC']['syncs'].copy()
    d0 = cfg['token0_decimals']   # WBTC = 8
    d1 = cfg['token1_decimals']   # WETH = 18

    r0 = syncs['reserve0'].astype(float) / (10 ** d0)   # WBTC amount
    r1 = syncs['reserve1'].astype(float) / (10 ** d1)   # WETH amount

    # ratio = WETH per WBTC  (e.g. 15 means 1 BTC ≈ 15 ETH)
    syncs['btc_eth_ratio'] = np.where(r0 > 0, r1 / r0, np.nan)
    syncs.dropna(subset=['btc_eth_ratio'], inplace=True)

    ratio_idx = syncs.groupby('block_number')['btc_eth_ratio'].last().sort_index()
    # Filter obvious outliers
    ratio_idx = ratio_idx[(ratio_idx > 1) & (ratio_idx < 200)]

    return ratio_idx if len(ratio_idx) > 0 else pd.Series(dtype=float)
