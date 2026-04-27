"""
Profit calculation and market-impact analysis for all frontrunning types.
"""
import pandas as pd
import numpy as np
from config import PAIR_CONFIG, ESTIMATED_GAS_PER_SWAP


# ---------------------------------------------------------------------------
# Price helpers
# ---------------------------------------------------------------------------

def _get_eth_price(block_number, eth_price_idx):
    """Return ETH/USD price at or before *block_number* (floor / ffill)."""
    if eth_price_idx is None or eth_price_idx.empty:
        return 2000.0
    idx = eth_price_idx.index.searchsorted(block_number, side='right') - 1
    if idx < 0:
        idx = 0
    return float(eth_price_idx.iloc[idx])


def _get_eth_price_before(block_number, eth_price_idx):
    """Return ETH/USD price strictly *before* block_number.

    Used as a pre-impact reference price for arbitrage profit estimation:
    the trigger trade in the current block has already moved the pool
    reserves, so using the same-block price would be circular.
    """
    if eth_price_idx is None or eth_price_idx.empty:
        return 2000.0
    # side='left' gives the first index >= block_number; minus 1 gives
    # the last entry strictly < block_number.
    idx = eth_price_idx.index.searchsorted(block_number, side='left') - 1
    if idx < 0:
        idx = 0
    return float(eth_price_idx.iloc[idx])


def _get_btc_eth_ratio(block_number, btc_eth_idx):
    """Return dynamic BTC/ETH ratio at or before *block_number*.

    Falls back to 15.0 when no index is available (matches the historical
    average over the dataset's time range).
    """
    if btc_eth_idx is None or btc_eth_idx.empty:
        return 15.0
    idx = btc_eth_idx.index.searchsorted(block_number, side='right') - 1
    if idx < 0:
        idx = 0
    return float(btc_eth_idx.iloc[idx])


def _token_to_usd(amount, token_name, block_number, eth_price_idx,
                   btc_eth_idx=None):
    """Convert a token amount to USD.

    Stablecoins are 1:1.  WETH uses the ETH/USD price index.
    WBTC uses a *dynamic* BTC/ETH ratio derived from the WETH_WBTC pool
    reserves (instead of the old fixed 15× constant).
    """
    if token_name in ('USDC', 'USDT', 'DAI'):
        return amount
    if token_name == 'WETH':
        return amount * _get_eth_price(block_number, eth_price_idx)
    if token_name == 'WBTC':
        eth_price = _get_eth_price(block_number, eth_price_idx)
        btc_eth = _get_btc_eth_ratio(block_number, btc_eth_idx)
        return amount * eth_price * btc_eth
    return amount


def _swap_value_usd(row, prefix, pair_cfg, eth_price_idx, btc_eth_idx=None):
    """Estimate the USD value of one side of a swap (inputs or outputs)."""
    d0, d1 = pair_cfg['token0_decimals'], pair_cfg['token1_decimals']
    t0, t1 = pair_cfg['token0_name'], pair_cfg['token1_name']
    blk = row['block_number']

    a0 = row.get(f'{prefix}_amount0_in', 0) + row.get(f'{prefix}_amount0_out', 0)
    a1 = row.get(f'{prefix}_amount1_in', 0) + row.get(f'{prefix}_amount1_out', 0)
    usd0 = _token_to_usd(a0 / (10 ** d0), t0, blk, eth_price_idx, btc_eth_idx)
    usd1 = _token_to_usd(a1 / (10 ** d1), t1, blk, eth_price_idx, btc_eth_idx)
    return max(usd0, usd1)


# ---------------------------------------------------------------------------
# 1. Sandwich profit
# ---------------------------------------------------------------------------

def calculate_sandwich_profits(sandwiches_df, eth_price_idx, btc_eth_idx=None):
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

        profit_usd = _token_to_usd(net0, t0, blk, eth_price_idx, btc_eth_idx) \
                   + _token_to_usd(net1, t1, blk, eth_price_idx, btc_eth_idx)

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
# Uniswap V2 AMM formula
# ---------------------------------------------------------------------------

def _uniswap_v2_get_amount_out(amount_in, reserve_in, reserve_out):
    """Uniswap V2 getAmountOut — exact on-chain formula with 0.3% fee.

    Solidity original:
        amountInWithFee = amountIn * 997
        numerator       = amountInWithFee * reserveOut
        denominator     = reserveIn * 1000 + amountInWithFee
        amountOut       = numerator / denominator
    """
    if reserve_in <= 0 or reserve_out <= 0 or amount_in <= 0:
        return 0.0
    amount_in_with_fee = amount_in * 997
    numerator = amount_in_with_fee * reserve_out
    denominator = reserve_in * 1000 + amount_in_with_fee
    return numerator / denominator


# ---------------------------------------------------------------------------
# 2. Displacement profit — counterfactual analysis
# ---------------------------------------------------------------------------

def calculate_displacement_profits(disp_df, eth_price_idx, btc_eth_idx=None,
                                   pair_data=None):
    """Calculate displacement profit via counterfactual reserve simulation.

    For each displacement event we:
      1. Find pool reserves just BEFORE the frontrunner's tx (from Sync data)
      2. Simulate the victim's swap at those "clean" reserves using x*y=k
      3. Compare counterfactual output vs actual output
      4. victim_loss = counterfactual_output − actual_output
      5. estimated_profit ≈ victim_loss − gas_cost

    This gives the price advantage the frontrunner captured by executing first.
    """
    if disp_df.empty:
        return disp_df

    # ── Pre-build per-pair Sync lookup (binary search on composite key) ──
    sync_lookup = {}
    if pair_data:
        for pair_name, data in pair_data.items():
            syncs = data['syncs'].copy()
            syncs = syncs.sort_values(['block_number', 'tx_index', 'log_index'])
            # Composite key: block * 1M + tx_index  (supports up to 1M txs/block)
            sync_keys = (syncs['block_number'].values.astype(np.int64) * 1_000_000
                         + syncs['tx_index'].values.astype(np.int64))
            sync_lookup[pair_name] = {
                'keys': sync_keys,
                'reserve0': syncs['reserve0'].values.astype(float),
                'reserve1': syncs['reserve1'].values.astype(float),
            }

    rows = []
    for _, r in disp_df.iterrows():
        cfg = PAIR_CONFIG[r['pair']]
        d0, d1 = cfg['token0_decimals'], cfg['token1_decimals']
        t0, t1 = cfg['token0_name'], cfg['token1_name']
        blk = r['block_number']
        direction = int(r['direction'])

        fr_val = _swap_value_usd(r, 'frontrunner', cfg, eth_price_idx, btc_eth_idx)
        vic_val = _swap_value_usd(r, 'victim', cfg, eth_price_idx, btc_eth_idx)
        gas_eth = r['frontrunner_gas_price'] * ESTIMATED_GAS_PER_SWAP / 1e18
        gas_usd = gas_eth * _get_eth_price(blk, eth_price_idx)

        # ── Counterfactual analysis ──
        victim_loss_usd = 0.0

        if r['pair'] in sync_lookup:
            lookup = sync_lookup[r['pair']]
            # Find the last Sync strictly before the frontrunner's tx
            target_key = int(blk) * 1_000_000 + int(r['frontrunner_tx_index'])
            idx = int(np.searchsorted(lookup['keys'], target_key, side='left')) - 1

            if idx >= 0:
                r0_before = lookup['reserve0'][idx]
                r1_before = lookup['reserve1'][idx]

                if direction == 0:
                    # Victim sends token0 → receives token1
                    victim_in = float(r['victim_amount0_in'])
                    victim_actual_out = float(r['victim_amount1_out'])
                    counterfactual_out = _uniswap_v2_get_amount_out(
                        victim_in, r0_before, r1_before)
                    loss_raw = counterfactual_out - victim_actual_out
                    victim_loss_usd = _token_to_usd(
                        loss_raw / (10 ** d1), t1, blk,
                        eth_price_idx, btc_eth_idx)
                else:
                    # Victim sends token1 → receives token0
                    victim_in = float(r['victim_amount1_in'])
                    victim_actual_out = float(r['victim_amount0_out'])
                    counterfactual_out = _uniswap_v2_get_amount_out(
                        victim_in, r1_before, r0_before)
                    loss_raw = counterfactual_out - victim_actual_out
                    victim_loss_usd = _token_to_usd(
                        loss_raw / (10 ** d0), t0, blk,
                        eth_price_idx, btc_eth_idx)

        rows.append({
            'frontrunner_value_usd': fr_val,
            'victim_value_usd': vic_val,
            'gas_cost_usd': gas_usd,
            'victim_loss_usd': round(victim_loss_usd, 2),
            'estimated_profit_usd': round(victim_loss_usd - gas_usd, 2),
        })

    return pd.concat([disp_df.reset_index(drop=True),
                       pd.DataFrame(rows)], axis=1)


# ---------------------------------------------------------------------------
# 3. Arbitrage / back-run profit estimate
# ---------------------------------------------------------------------------

def calculate_arbitrage_profits(arb_df, eth_price_idx, btc_eth_idx=None):
    """Estimate back-runner profit using a *pre-impact* reference price.

    The trigger trade in the current block has already moved the pool
    reserves, so the same-block ETH price (derived from those reserves)
    is distorted.  We therefore use the ETH price from the *previous*
    block as the fair-market reference when converting the back-runner's
    net token change to USD.

    The result represents the price-discrepancy profit the back-runner
    captures by buying at the distorted in-pool price and (implicitly)
    selling at the undistorted market price elsewhere.
    """
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

        # ── Key change: use pre-impact (previous-block) ETH price ──
        # This avoids circular pricing: the trigger trade already moved
        # the pool reserves that feed the same-block ETH price index.
        eth_ref = _get_eth_price_before(blk, eth_price_idx)

        def _to_usd_ref(amount, token_name):
            """Convert using the pre-impact ETH reference price."""
            if token_name in ('USDC', 'USDT', 'DAI'):
                return amount
            if token_name == 'WETH':
                return amount * eth_ref
            if token_name == 'WBTC':
                btc_eth = _get_btc_eth_ratio(blk, btc_eth_idx)
                return amount * eth_ref * btc_eth
            return amount

        profit_usd = _to_usd_ref(net0, t0) + _to_usd_ref(net1, t1)

        gas_eth = r['backrunner_gas_price'] * ESTIMATED_GAS_PER_SWAP / 1e18
        gas_usd = gas_eth * eth_ref

        rows.append({
            'backrun_profit_usd': profit_usd,
            'gas_cost_usd': gas_usd,
            'net_profit_usd': profit_usd - gas_usd,
            'trigger_value_usd': _swap_value_usd(r, 'trigger', cfg,
                                                  eth_price_idx, btc_eth_idx),
            'eth_ref_price': eth_ref,
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
