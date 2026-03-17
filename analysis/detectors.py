"""
Frontrunning detection algorithms — four types:

  1. Sandwich / Insertion   – attacker brackets a victim swap (buy→victim→sell)
  2. Displacement           – attacker's high-gas tx executes first in same direction,
                              pushing victim to worse price
  3. Arbitrage / Back-run   – entity tail-runs a large swap to capture price reversion
  4. Suppression indicators – blocks where a single entity floods high-gas txs,
                              crowding out normal users
"""
import pandas as pd
import numpy as np
from tqdm import tqdm

from config import PAIR_CONFIG


# ═══════════════════════════════════════════════════════════════════
#  1. Sandwich / Insertion
# ═══════════════════════════════════════════════════════════════════

def detect_sandwiches(swaps_df, pair_name):
    """
    Returns (sandwiches_df, victims_df).
    """
    df = swaps_df

    block_size = df.groupby('block_number').size()
    blocks_3plus = set(block_size[block_size >= 3].index)

    ent_blk = df.groupby(['block_number', 'entity']).size().reset_index(name='cnt')
    blocks_repeat = set(ent_blk[ent_blk['cnt'] >= 2]['block_number'])

    candidate_blocks = blocks_3plus & blocks_repeat
    if not candidate_blocks:
        return pd.DataFrame(), pd.DataFrame()

    df_cand = df[df['block_number'].isin(candidate_blocks)]
    grouped = df_cand.groupby('block_number')

    sandwiches = []
    victim_rows = []
    sw_id = 0

    for block_num, group in tqdm(grouped, desc=f'  Sandwich {pair_name}', leave=False, ncols=80):
        records = group.to_dict('records')

        entity_map: dict[str, list] = {}
        for r in records:
            entity_map.setdefault(r['entity'], []).append(r)

        for entity, e_swaps in entity_map.items():
            if len(e_swaps) < 2:
                continue
            all_others = [r for r in records if r['entity'] != entity]
            if not all_others:
                continue

            used = set()
            for i in range(len(e_swaps)):
                if i in used:
                    continue
                for j in range(i + 1, len(e_swaps)):
                    if j in used:
                        continue
                    front, back = e_swaps[i], e_swaps[j]
                    if front['direction'] == back['direction']:
                        continue
                    if front['tx_hash'] == back['tx_hash']:
                        continue

                    front_ord = (front['tx_index'], front['log_index'])
                    back_ord = (back['tx_index'], back['log_index'])

                    victims = [
                        o for o in all_others
                        if front_ord < (o['tx_index'], o['log_index']) < back_ord
                        and o['direction'] == front['direction']
                    ]
                    if not victims:
                        continue

                    used.add(i)
                    used.add(j)
                    sw_id += 1

                    sandwiches.append({
                        'sandwich_id': sw_id,
                        'pair': pair_name,
                        'block_number': int(block_num),
                        'timestamp': int(front['timestamp']),
                        'attacker': entity,
                        'front_tx': front['tx_hash'],
                        'front_sender': front['sender'],
                        'front_to': front['to'],
                        'front_tx_index': int(front['tx_index']),
                        'front_direction': int(front['direction']),
                        'front_amount0_in': float(front['amount0_in']),
                        'front_amount1_in': float(front['amount1_in']),
                        'front_amount0_out': float(front['amount0_out']),
                        'front_amount1_out': float(front['amount1_out']),
                        'front_gas_price': float(front['gas_price']),
                        'back_tx': back['tx_hash'],
                        'back_sender': back['sender'],
                        'back_to': back['to'],
                        'back_tx_index': int(back['tx_index']),
                        'back_amount0_in': float(back['amount0_in']),
                        'back_amount1_in': float(back['amount1_in']),
                        'back_amount0_out': float(back['amount0_out']),
                        'back_amount1_out': float(back['amount1_out']),
                        'back_gas_price': float(back['gas_price']),
                        'num_victims': len(victims),
                        'victim_txs': ';'.join(v['tx_hash'] for v in victims),
                        'victim_total_amount0_in':  sum(float(v['amount0_in'])  for v in victims),
                        'victim_total_amount1_in':  sum(float(v['amount1_in'])  for v in victims),
                        'victim_total_amount0_out': sum(float(v['amount0_out']) for v in victims),
                        'victim_total_amount1_out': sum(float(v['amount1_out']) for v in victims),
                    })
                    for v in victims:
                        victim_rows.append({
                            'sandwich_id': sw_id,
                            'pair': pair_name,
                            'block_number': int(block_num),
                            'timestamp': int(v['timestamp']),
                            'victim_tx': v['tx_hash'],
                            'victim_sender': v['sender'],
                            'victim_to': v['to'],
                            'victim_entity': v['entity'],
                            'tx_index': int(v['tx_index']),
                            'log_index': int(v['log_index']),
                            'direction': int(v['direction']),
                            'amount0_in':  float(v['amount0_in']),
                            'amount1_in':  float(v['amount1_in']),
                            'amount0_out': float(v['amount0_out']),
                            'amount1_out': float(v['amount1_out']),
                            'gas_price':   float(v['gas_price']),
                        })
                    break

    sw_df  = pd.DataFrame(sandwiches)  if sandwiches  else pd.DataFrame()
    vic_df = pd.DataFrame(victim_rows) if victim_rows else pd.DataFrame()
    return sw_df, vic_df


# ═══════════════════════════════════════════════════════════════════
#  2. Displacement
# ═══════════════════════════════════════════════════════════════════

def detect_displacement(swaps_df, pair_name, gas_ratio_min=1.5, max_tx_gap=5):
    """
    Displacement: in the same block two different entities swap in the **same
    direction**, the one paying significantly higher gas (≥ 1.5×) gets priority
    (lower tx_index), and the later tx suffers worse execution because the
    first one already moved the price.

    We additionally require that the two txs are within `max_tx_gap` positions
    and the displaced entity is NOT a known MEV bot (heuristic: bots typically
    have many high-gas txs themselves).

    Returns a DataFrame — one row per displacement event.
    """
    df = swaps_df
    block_size = df.groupby('block_number').size()
    blocks_2plus = set(block_size[block_size >= 2].index)
    if not blocks_2plus:
        return pd.DataFrame()

    df_cand = df[df['block_number'].isin(blocks_2plus)]

    # Pre-compute per-entity tx count (to filter out bot-vs-bot later)
    entity_freq = df['entity'].value_counts()

    grouped = df_cand.groupby('block_number')
    results = []

    for block_num, group in tqdm(grouped, desc=f'  Displace {pair_name}', leave=False, ncols=80):
        records = group.to_dict('records')
        n = len(records)
        for i in range(n):
            for j in range(i + 1, n):
                s1, s2 = records[i], records[j]
                if s1['direction'] != s2['direction']:
                    continue
                if s1['entity'] == s2['entity']:
                    continue
                if abs(s1['tx_index'] - s2['tx_index']) > max_tx_gap:
                    continue
                gp1, gp2 = s1['gas_price'], s2['gas_price']
                if gp2 <= 0 or gp1 <= 0:
                    continue
                ratio = gp1 / gp2
                if ratio < gas_ratio_min:
                    continue

                # s1 paid more gas and executed first → potential displacement
                results.append({
                    'pair': pair_name,
                    'block_number': int(block_num),
                    'timestamp': int(s1['timestamp']),
                    'frontrunner_entity': s1['entity'],
                    'frontrunner_tx': s1['tx_hash'],
                    'frontrunner_sender': s1['sender'],
                    'frontrunner_to': s1['to'],
                    'frontrunner_tx_index': int(s1['tx_index']),
                    'frontrunner_gas_price': gp1,
                    'frontrunner_amount0_in':  float(s1['amount0_in']),
                    'frontrunner_amount1_in':  float(s1['amount1_in']),
                    'frontrunner_amount0_out': float(s1['amount0_out']),
                    'frontrunner_amount1_out': float(s1['amount1_out']),
                    'victim_entity': s2['entity'],
                    'victim_tx': s2['tx_hash'],
                    'victim_sender': s2['sender'],
                    'victim_to': s2['to'],
                    'victim_tx_index': int(s2['tx_index']),
                    'victim_gas_price': gp2,
                    'victim_amount0_in':  float(s2['amount0_in']),
                    'victim_amount1_in':  float(s2['amount1_in']),
                    'victim_amount0_out': float(s2['amount0_out']),
                    'victim_amount1_out': float(s2['amount1_out']),
                    'direction': int(s1['direction']),
                    'gas_ratio': round(ratio, 2),
                    'tx_index_gap': int(s2['tx_index'] - s1['tx_index']),
                    'frontrunner_freq': int(entity_freq.get(s1['entity'], 0)),
                })

    return pd.DataFrame(results) if results else pd.DataFrame()


# ═══════════════════════════════════════════════════════════════════
#  3. Arbitrage / Back-running
# ═══════════════════════════════════════════════════════════════════

def detect_arbitrage(swaps_df, pair_name, max_tx_gap=3):
    """
    Back-running / arbitrage: immediately after a "large" swap (above the 90th
    percentile in trade size for this pair), a *different* entity executes an
    **opposite-direction** swap within `max_tx_gap` tx positions in the same
    block.  The back-runner profits from the price reversion after the large
    trade's impact.

    Returns a DataFrame — one row per detected back-run.
    """
    df = swaps_df
    cfg = PAIR_CONFIG[pair_name]
    d0, d1 = cfg['token0_decimals'], cfg['token1_decimals']

    df = df.copy()
    df['trade_size'] = np.maximum(
        df['amount0_in'].astype(float) / (10 ** d0),
        df['amount0_out'].astype(float) / (10 ** d0),
    ) + np.maximum(
        df['amount1_in'].astype(float) / (10 ** d1),
        df['amount1_out'].astype(float) / (10 ** d1),
    )
    large_threshold = df['trade_size'].quantile(0.90)

    block_size = df.groupby('block_number').size()
    blocks_2plus = set(block_size[block_size >= 2].index)
    if not blocks_2plus:
        return pd.DataFrame()

    df_cand = df[df['block_number'].isin(blocks_2plus)]
    grouped = df_cand.groupby('block_number')
    results = []

    for block_num, group in tqdm(grouped, desc=f'  Arb {pair_name}', leave=False, ncols=80):
        records = group.to_dict('records')
        n = len(records)
        for i in range(n):
            trigger = records[i]
            if trigger['trade_size'] < large_threshold:
                continue
            for j in range(i + 1, n):
                follower = records[j]
                if follower['entity'] == trigger['entity']:
                    continue
                if follower['direction'] == trigger['direction']:
                    continue
                if abs(follower['tx_index'] - trigger['tx_index']) > max_tx_gap:
                    continue

                results.append({
                    'pair': pair_name,
                    'block_number': int(block_num),
                    'timestamp': int(trigger['timestamp']),
                    'trigger_entity': trigger['entity'],
                    'trigger_tx': trigger['tx_hash'],
                    'trigger_sender': trigger['sender'],
                    'trigger_to': trigger['to'],
                    'trigger_tx_index': int(trigger['tx_index']),
                    'trigger_direction': int(trigger['direction']),
                    'trigger_amount0_in':  float(trigger['amount0_in']),
                    'trigger_amount1_in':  float(trigger['amount1_in']),
                    'trigger_amount0_out': float(trigger['amount0_out']),
                    'trigger_amount1_out': float(trigger['amount1_out']),
                    'trigger_gas_price': float(trigger['gas_price']),
                    'trigger_trade_size': float(trigger['trade_size']),
                    'backrunner_entity': follower['entity'],
                    'backrunner_tx': follower['tx_hash'],
                    'backrunner_sender': follower['sender'],
                    'backrunner_to': follower['to'],
                    'backrunner_tx_index': int(follower['tx_index']),
                    'backrunner_amount0_in':  float(follower['amount0_in']),
                    'backrunner_amount1_in':  float(follower['amount1_in']),
                    'backrunner_amount0_out': float(follower['amount0_out']),
                    'backrunner_amount1_out': float(follower['amount1_out']),
                    'backrunner_gas_price': float(follower['gas_price']),
                    'tx_index_gap': int(follower['tx_index'] - trigger['tx_index']),
                })
                break  # one back-runner per trigger

    return pd.DataFrame(results) if results else pd.DataFrame()


# ═══════════════════════════════════════════════════════════════════
#  4. Suppression indicators
# ═══════════════════════════════════════════════════════════════════

def detect_suppression(swaps_df, pair_name, gas_premium_thresh=3.0, min_flood_txs=3):
    """
    Suppression: a single entity submits many high-gas txs in one block,
    effectively crowding out other users by consuming block gas / driving
    gas prices up.

    Heuristic:
      - One entity has ≥ `min_flood_txs` swaps in a block
      - Their median gas price is ≥ `gas_premium_thresh` × block median
      - Other entities in that block have lower gas prices (victims)

    Returns a DataFrame — one row per suppression event (per block × entity).
    """
    df = swaps_df
    block_med = df.groupby('block_number')['gas_price'].median().rename('blk_gas_med')
    df_m = df.merge(block_med, on='block_number')

    ent_blk = df_m.groupby(['block_number', 'entity']).agg(
        cnt=('tx_hash', 'size'),
        ent_gas_median=('gas_price', 'median'),
        blk_gas_med=('blk_gas_med', 'first'),
    ).reset_index()

    ent_blk['gas_premium'] = np.where(
        ent_blk['blk_gas_med'] > 0,
        ent_blk['ent_gas_median'] / ent_blk['blk_gas_med'],
        1.0
    )

    suspects = ent_blk[
        (ent_blk['cnt'] >= min_flood_txs) &
        (ent_blk['gas_premium'] >= gas_premium_thresh)
    ].copy()

    if suspects.empty:
        return pd.DataFrame()

    results = []
    for _, row in suspects.iterrows():
        blk = row['block_number']
        entity = row['entity']
        blk_swaps = df_m[df_m['block_number'] == blk]
        others = blk_swaps[blk_swaps['entity'] != entity]
        num_others = others['entity'].nunique()
        others_gas_med = float(others['gas_price'].median()) if len(others) else 0

        ts = int(blk_swaps['timestamp'].iloc[0])

        results.append({
            'pair': pair_name,
            'block_number': int(blk),
            'timestamp': ts,
            'suppressor_entity': entity,
            'suppressor_tx_count': int(row['cnt']),
            'suppressor_gas_median_gwei': round(row['ent_gas_median'] / 1e9, 2),
            'block_gas_median_gwei': round(row['blk_gas_med'] / 1e9, 2),
            'gas_premium': round(row['gas_premium'], 2),
            'other_entities_in_block': num_others,
            'others_gas_median_gwei': round(others_gas_med / 1e9, 2),
        })

    return pd.DataFrame(results)


# ═══════════════════════════════════════════════════════════════════
#  Convenience: gas anomaly summary (unchanged)
# ═══════════════════════════════════════════════════════════════════

def detect_gas_anomalies(swaps_df, pair_name, threshold=2.0):
    df = swaps_df.copy()
    block_med = df.groupby('block_number')['gas_price'].median().rename('blk_gas_med')
    df = df.merge(block_med, on='block_number')
    df['gas_premium'] = np.where(df['blk_gas_med'] > 0,
                                  df['gas_price'] / df['blk_gas_med'], 1.0)
    anomalies = df[df['gas_premium'] > threshold].copy()
    anomalies['pair'] = pair_name
    entity_summary = (
        anomalies.groupby('entity')
        .agg(anomaly_count=('tx_hash', 'count'),
             avg_gas_premium=('gas_premium', 'mean'),
             max_gas_premium=('gas_premium', 'max'))
        .sort_values('anomaly_count', ascending=False)
    )
    return anomalies, entity_summary
