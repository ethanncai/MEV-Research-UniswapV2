"""
Profit calculation and market-impact analysis for all frontrunning types.
"""
import pandas as pd
import numpy as np
from config import PAIR_CONFIG, ESTIMATED_GAS_PER_SWAP, BTC_ETH_RATIO_APPROX


# ---------------------------------------------------------------------------
# ETH price helpers
# ---------------------------------------------------------------------------

def _get_eth_price(block_number, eth_price_idx):
    if eth_price_idx is None or eth_price_idx.empty:
        return 2000.0
    idx = eth_price_idx.index.searchsorted(block_number)
    if idx >= len(eth_price_idx):
        idx = len(eth_price_idx) - 1
    return float(eth_price_idx.iloc[idx])


def _token_to_usd(amount, token_name, block_number, eth_price_idx):
    if token_name in ('USDC', 'USDT', 'DAI'):
        return amount
    if token_name == 'WETH':
        return amount * _get_eth_price(block_number, eth_price_idx)
    if token_name == 'WBTC':
        return amount * _get_eth_price(block_number, eth_price_idx) * BTC_ETH_RATIO_APPROX
    return amount


def _swap_value_usd(row, prefix, pair_cfg, eth_price_idx):
    """Estimate the USD value of one side of a swap (inputs or outputs)."""
    d0, d1 = pair_cfg['token0_decimals'], pair_cfg['token1_decimals']
    t0, t1 = pair_cfg['token0_name'], pair_cfg['token1_name']
    blk = row['block_number']

    a0 = row.get(f'{prefix}_amount0_in', 0) + row.get(f'{prefix}_amount0_out', 0)
    a1 = row.get(f'{prefix}_amount1_in', 0) + row.get(f'{prefix}_amount1_out', 0)
    usd0 = _token_to_usd(a0 / (10 ** d0), t0, blk, eth_price_idx)
    usd1 = _token_to_usd(a1 / (10 ** d1), t1, blk, eth_price_idx)
    return max(usd0, usd1)


# ---------------------------------------------------------------------------
# 1. Sandwich profit
# ---------------------------------------------------------------------------

def calculate_sandwich_profits(sandwiches_df, eth_price_idx):
    if sandwiches_df.empty:
        return sandwiches_df

    rows = []
    for _, s in sandwiches_df.iterrows():
        cfg = PAIR_CONFIG[s['pair']]
        d0, d1 = cfg['token0_decimals'], cfg['token1_decimals']
        t0, t1 = cfg['token0_name'], cfg['token1_name']
        blk = s['block_number']

        net0_raw = (s['front_amount0_out'] + s['back_amount0_out']) \
                 - (s['front_amount0_in']  + s['back_amount0_in'])
        net1_raw = (s['front_amount1_out'] + s['back_amount1_out']) \
                 - (s['front_amount1_in']  + s['back_amount1_in'])

        net0 = net0_raw / (10 ** d0)
        net1 = net1_raw / (10 ** d1)

        profit_usd = _token_to_usd(net0, t0, blk, eth_price_idx) \
                   + _token_to_usd(net1, t1, blk, eth_price_idx)

        gas_cost_eth = ((s['front_gas_price'] + s['back_gas_price'])
                        * ESTIMATED_GAS_PER_SWAP) / 1e18
        gas_cost_usd = gas_cost_eth * _get_eth_price(blk, eth_price_idx)

        rows.append({
            'net_token0': net0, 'net_token1': net1,
            'profit_usd': profit_usd,
            'gas_cost_eth': gas_cost_eth, 'gas_cost_usd': gas_cost_usd,
            'net_profit_usd': profit_usd - gas_cost_usd,
        })

    return pd.concat([sandwiches_df.reset_index(drop=True),
                       pd.DataFrame(rows)], axis=1)


# ---------------------------------------------------------------------------
# 2. Displacement profit estimate
# ---------------------------------------------------------------------------

def calculate_displacement_profits(disp_df, eth_price_idx):
    """
    The frontrunner's 'profit' from displacement is the price advantage they
    obtained by executing first.  We estimate it as:
      frontrunner_output_value − victim_output_value  (normalised by input size)
    Because exact counterfactual reserves are unavailable, we report the raw
    trade values for transparency and a rough estimated_advantage_usd.
    """
    if disp_df.empty:
        return disp_df

    rows = []
    for _, r in disp_df.iterrows():
        cfg = PAIR_CONFIG[r['pair']]
        blk = r['block_number']
        fr_val = _swap_value_usd(r, 'frontrunner', cfg, eth_price_idx)
        vic_val = _swap_value_usd(r, 'victim', cfg, eth_price_idx)
        gas_eth = r['frontrunner_gas_price'] * ESTIMATED_GAS_PER_SWAP / 1e18
        gas_usd = gas_eth * _get_eth_price(blk, eth_price_idx)
        rows.append({
            'frontrunner_value_usd': fr_val,
            'victim_value_usd': vic_val,
            'gas_cost_usd': gas_usd,
        })

    return pd.concat([disp_df.reset_index(drop=True),
                       pd.DataFrame(rows)], axis=1)


# ---------------------------------------------------------------------------
# 3. Arbitrage / back-run profit estimate
# ---------------------------------------------------------------------------

def calculate_arbitrage_profits(arb_df, eth_price_idx):
    if arb_df.empty:
        return arb_df

    rows = []
    for _, r in arb_df.iterrows():
        cfg = PAIR_CONFIG[r['pair']]
        d0, d1 = cfg['token0_decimals'], cfg['token1_decimals']
        t0, t1 = cfg['token0_name'], cfg['token1_name']
        blk = r['block_number']

        net0 = (r['backrunner_amount0_out'] - r['backrunner_amount0_in']) / (10 ** d0)
        net1 = (r['backrunner_amount1_out'] - r['backrunner_amount1_in']) / (10 ** d1)
        profit_usd = _token_to_usd(net0, t0, blk, eth_price_idx) \
                   + _token_to_usd(net1, t1, blk, eth_price_idx)

        gas_eth = r['backrunner_gas_price'] * ESTIMATED_GAS_PER_SWAP / 1e18
        gas_usd = gas_eth * _get_eth_price(blk, eth_price_idx)

        rows.append({
            'backrun_profit_usd': profit_usd,
            'gas_cost_usd': gas_usd,
            'net_profit_usd': profit_usd - gas_usd,
            'trigger_value_usd': _swap_value_usd(r, 'trigger', cfg, eth_price_idx),
        })

    return pd.concat([arb_df.reset_index(drop=True),
                       pd.DataFrame(rows)], axis=1)


# ---------------------------------------------------------------------------
# Market impact (unchanged logic, used by visualizer)
# ---------------------------------------------------------------------------

def analyze_market_impact(sandwiches_df, pair_data):
    results = {}
    for pair_name, data in pair_data.items():
        cfg = PAIR_CONFIG[pair_name]
        swaps, syncs = data['swaps'], data['syncs']
        d0, d1 = cfg['token0_decimals'], cfg['token1_decimals']

        pair_sw = (sandwiches_df[sandwiches_df['pair'] == pair_name]
                   if not sandwiches_df.empty else pd.DataFrame())

        sc = syncs.copy()
        r0 = sc['reserve0'].astype(float) / (10 ** d0)
        r1 = sc['reserve1'].astype(float) / (10 ** d1)
        with np.errstate(divide='ignore', invalid='ignore'):
            sc['price'] = np.where(r1 > 0, r0 / r1, np.nan)
        sc.dropna(subset=['price'], inplace=True)

        total_swaps = len(swaps)
        total_blocks = swaps['block_number'].nunique()
        sandwich_count = len(pair_sw)
        sandwich_blocks = pair_sw['block_number'].nunique() if sandwich_count else 0
        sandwich_txs = sandwich_count * 3

        sw_blocks = set(pair_sw['block_number']) if sandwich_count else set()
        gas_attack = swaps[swaps['block_number'].isin(sw_blocks)]['gas_price'] if sw_blocks else pd.Series(dtype=float)
        gas_normal = swaps[~swaps['block_number'].isin(sw_blocks)]['gas_price']

        results[pair_name] = {
            'total_swaps': total_swaps,
            'total_blocks': total_blocks,
            'sandwich_count': sandwich_count,
            'sandwich_blocks': sandwich_blocks,
            'sandwich_block_pct': sandwich_blocks / total_blocks * 100 if total_blocks else 0,
            'sandwich_swap_pct': sandwich_txs / total_swaps * 100 if total_swaps else 0,
            'gas_attack_median': float(gas_attack.median()) if len(gas_attack) else 0,
            'gas_normal_median': float(gas_normal.median()) if len(gas_normal) else 0,
            'price_series': sc[['block_number', 'timestamp', 'price']],
        }
    return results
