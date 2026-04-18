"""
Configuration for MEV Frontrunning Analysis.
Pair metadata, token decimals, known router addresses, and paths.
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, 'data')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')

# UniswapV2 routers — when sender is one of these, the real trader is the `to` address
KNOWN_ROUTERS = {
    '0xf164fc0ec4e93095b804a4795bbe1e041497b92a',  # UniswapV2Router01
    '0x7a250d5630b4cf539739df2c5dacb4c659f2488d',  # UniswapV2Router02
}

# Token ordering follows UniswapV2 convention: token0 < token1 by address
PAIR_CONFIG = {
    'WETH_USDC': {
        'token0_name': 'USDC', 'token0_decimals': 6,
        'token1_name': 'WETH', 'token1_decimals': 18,
        'has_stablecoin': True,
        'usd_token': 0,
    },
    'WETH_USDT': {
        'token0_name': 'WETH', 'token0_decimals': 18,
        'token1_name': 'USDT', 'token1_decimals': 6,
        'has_stablecoin': True,
        'usd_token': 1,
    },
    'WETH_DAI': {
        'token0_name': 'DAI', 'token0_decimals': 18,
        'token1_name': 'WETH', 'token1_decimals': 18,
        'has_stablecoin': True,
        'usd_token': 0,
    },
    'WETH_WBTC': {
        'token0_name': 'WBTC', 'token0_decimals': 8,
        'token1_name': 'WETH', 'token1_decimals': 18,
        'has_stablecoin': False,
        'usd_token': None,
    },
    'USDC_USDT': {
        'token0_name': 'USDC', 'token0_decimals': 6,
        'token1_name': 'USDT', 'token1_decimals': 6,
        'has_stablecoin': True,
        'usd_token': 0,
    },
}

ESTIMATED_GAS_PER_SWAP = 150_000
# BTC_ETH_RATIO_APPROX is no longer used — replaced by dynamic ratio
# from WETH_WBTC pool reserves in data_loader.build_btc_eth_index().
# The fallback value (15.0) is now hard-coded in analyzers._get_btc_eth_ratio().
