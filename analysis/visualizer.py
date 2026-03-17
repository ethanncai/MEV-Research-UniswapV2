"""
Generate charts and a Markdown report covering all four frontrunning types.
"""
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pandas as pd
import numpy as np
from datetime import datetime

from config import PAIR_CONFIG, OUTPUT_DIR

COLORS = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6',
          '#1abc9c', '#e67e22', '#34495e']


def _save(fig, name, output_dir):
    fig.savefig(os.path.join(output_dir, name), dpi=150, bbox_inches='tight')
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════
#  Chart functions
# ══════════════════════════════════════════════════════════════════

def plot_frontrun_overview(results, output_dir):
    """Bar chart comparing all four detection types across pairs."""
    sw  = results.get('sandwiches', pd.DataFrame())
    dp  = results.get('displacement', pd.DataFrame())
    arb = results.get('arbitrage', pd.DataFrame())
    sup = results.get('suppression', pd.DataFrame())

    pairs = sorted(set(
        list(sw['pair'].unique() if not sw.empty else [])
        + list(dp['pair'].unique() if not dp.empty else [])
        + list(arb['pair'].unique() if not arb.empty else [])
        + list(sup['pair'].unique() if not sup.empty else [])
    ))
    if not pairs:
        return

    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(len(pairs))
    w = 0.2

    def _cnt(df, p):
        return len(df[df['pair'] == p]) if not df.empty else 0

    ax.bar(x - 1.5 * w, [_cnt(sw, p) for p in pairs],  w, label='Sandwich', color='#e74c3c')
    ax.bar(x - 0.5 * w, [_cnt(dp, p) for p in pairs],  w, label='Displacement', color='#3498db')
    ax.bar(x + 0.5 * w, [_cnt(arb, p) for p in pairs], w, label='Arbitrage', color='#2ecc71')
    ax.bar(x + 1.5 * w, [_cnt(sup, p) for p in pairs], w, label='Suppression', color='#f39c12')

    ax.set_xticks(x)
    ax.set_xticklabels(pairs, rotation=20)
    ax.set_ylabel('Events Detected')
    ax.set_title('Frontrunning Activities by Type and Pair')
    ax.legend()
    _save(fig, '01_frontrun_overview.png', output_dir)


def plot_sandwich_timeline(results, output_dir):
    sw = results.get('sandwiches', pd.DataFrame())
    if sw.empty:
        return
    fig, ax = plt.subplots(figsize=(13, 5))
    df = sw.copy()
    df['date'] = pd.to_datetime(df['timestamp'], unit='s')
    df['month'] = df['date'].dt.to_period('M')
    monthly = df.groupby(['month', 'pair']).size().unstack(fill_value=0)
    monthly.index = monthly.index.to_timestamp()
    monthly.plot(ax=ax, linewidth=2, marker='o', markersize=4)
    ax.set_ylabel('Sandwich Attacks')
    ax.set_title('Sandwich Attacks Over Time (Monthly)')
    ax.legend(title='Pair', fontsize=8)
    _save(fig, '02_sandwich_timeline.png', output_dir)


def plot_profit_distribution(results, output_dir):
    sw = results.get('sandwiches', pd.DataFrame())
    if sw.empty or 'net_profit_usd' not in sw.columns:
        return
    profits = sw['net_profit_usd'].dropna()
    if profits.empty:
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    axes[0].hist(profits.clip(-500, 5000), bins=80, color='#3498db', edgecolor='white', alpha=.85)
    axes[0].axvline(0, color='red', ls='--', lw=1)
    axes[0].set_xlabel('Net Profit (USD)')
    axes[0].set_ylabel('Count')
    axes[0].set_title('Sandwich Net Profit Distribution')

    pos = profits[profits > 0]
    if not pos.empty:
        axes[1].hist(np.log10(pos.clip(lower=0.01)), bins=60, color='#2ecc71', edgecolor='white', alpha=.85)
        axes[1].set_xlabel('log₁₀(Net Profit USD)')
        axes[1].set_ylabel('Count')
        axes[1].set_title('Profitable Sandwiches (log scale)')
    fig.tight_layout()
    _save(fig, '03_profit_distribution.png', output_dir)


def plot_top_attackers(results, output_dir):
    sw = results.get('sandwiches', pd.DataFrame())
    if sw.empty or 'net_profit_usd' not in sw.columns:
        return
    agg = sw.groupby('attacker').agg(
        count=('block_number', 'size'),
        total_profit=('net_profit_usd', 'sum'),
    ).sort_values('total_profit', ascending=False).head(15)
    if agg.empty:
        return

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    labels = [f'{a[:6]}…{a[-4:]}' for a in agg.index]
    axes[0].barh(labels, agg['count'], color='#e74c3c')
    axes[0].set_xlabel('Number of Sandwiches')
    axes[0].set_title('Top 15 Attackers by Count')
    axes[0].invert_yaxis()
    axes[1].barh(labels, agg['total_profit'], color='#f39c12')
    axes[1].set_xlabel('Total Net Profit (USD)')
    axes[1].set_title('Top 15 Attackers by Profit')
    axes[1].invert_yaxis()
    axes[1].xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f'${x:,.0f}'))
    fig.tight_layout()
    _save(fig, '04_top_attackers.png', output_dir)


def plot_gas_analysis(results, market_impact, output_dir):
    sw = results.get('sandwiches', pd.DataFrame())
    if sw.empty:
        return
    pairs_with_data = [p for p in market_impact if market_impact[p]['gas_attack_median'] > 0]
    if not pairs_with_data:
        return
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(pairs_with_data))
    w = 0.35
    ax.bar(x - w / 2, [market_impact[p]['gas_attack_median'] / 1e9 for p in pairs_with_data],
           w, label='Sandwich Blocks', color='#e74c3c')
    ax.bar(x + w / 2, [market_impact[p]['gas_normal_median'] / 1e9 for p in pairs_with_data],
           w, label='Normal Blocks', color='#3498db')
    ax.set_xticks(x)
    ax.set_xticklabels(pairs_with_data, rotation=20)
    ax.set_ylabel('Median Gas Price (Gwei)')
    ax.set_title('Median Gas Price: Sandwich Blocks vs Normal Blocks')
    ax.legend()
    _save(fig, '05_gas_analysis.png', output_dir)


def plot_price_timeseries(market_impact, output_dir):
    fig, axes = plt.subplots(3, 2, figsize=(16, 14))
    axes = axes.flatten()
    pairs = list(market_impact.keys())
    for idx, pair in enumerate(pairs):
        if idx >= len(axes):
            break
        ax = axes[idx]
        ps = market_impact[pair]['price_series']
        if ps.empty:
            ax.set_visible(False)
            continue
        ps = ps.copy()
        ps['date'] = pd.to_datetime(ps['timestamp'], unit='s')
        sampled = ps.iloc[::max(1, len(ps) // 2000)]
        ax.plot(sampled['date'], sampled['price'], lw=0.6, color=COLORS[idx % len(COLORS)])
        cfg = PAIR_CONFIG[pair]
        ax.set_ylabel(f'{cfg["token0_name"]}/{cfg["token1_name"]}', fontsize=9)
        ax.set_title(pair, fontsize=10)
        ax.tick_params(labelsize=8)
    for idx in range(len(pairs), len(axes)):
        axes[idx].set_visible(False)
    fig.suptitle('Token Price Over Time (from Reserves)', fontsize=13, y=1.01)
    fig.tight_layout()
    _save(fig, '06_price_timeseries.png', output_dir)


def plot_displacement_gas(results, output_dir):
    dp = results.get('displacement', pd.DataFrame())
    if dp.empty:
        return
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    ax = axes[0]
    dp['gas_ratio'].clip(upper=20).hist(bins=50, ax=ax, color='#3498db', edgecolor='white', alpha=.85)
    ax.set_xlabel('Gas Price Ratio (Frontrunner / Victim)')
    ax.set_ylabel('Count')
    ax.set_title('Displacement: Gas Ratio Distribution')

    ax = axes[1]
    by_pair = dp.groupby('pair').size().sort_values()
    by_pair.plot(kind='barh', ax=ax, color=COLORS[:len(by_pair)])
    ax.set_xlabel('Events')
    ax.set_title('Displacement Events by Pair')

    fig.tight_layout()
    _save(fig, '07_displacement.png', output_dir)


def plot_arbitrage(results, output_dir):
    arb = results.get('arbitrage', pd.DataFrame())
    if arb.empty or 'net_profit_usd' not in arb.columns:
        return
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    ax = axes[0]
    profits = arb['net_profit_usd'].clip(-500, 5000)
    profits.hist(bins=60, ax=ax, color='#2ecc71', edgecolor='white', alpha=.85)
    ax.axvline(0, color='red', ls='--', lw=1)
    ax.set_xlabel('Net Profit (USD)')
    ax.set_title('Arbitrage / Back-run Profit Distribution')

    ax = axes[1]
    by_pair = arb.groupby('pair').size().sort_values()
    by_pair.plot(kind='barh', ax=ax, color=COLORS[:len(by_pair)])
    ax.set_xlabel('Events')
    ax.set_title('Arbitrage / Back-run Events by Pair')

    fig.tight_layout()
    _save(fig, '08_arbitrage.png', output_dir)


def plot_suppression(results, output_dir):
    sup = results.get('suppression', pd.DataFrame())
    if sup.empty:
        return
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    ax = axes[0]
    sup['gas_premium'].clip(upper=50).hist(bins=40, ax=ax, color='#f39c12', edgecolor='white', alpha=.85)
    ax.set_xlabel('Gas Premium (×)')
    ax.set_title('Suppression: Gas Premium Distribution')

    ax = axes[1]
    by_pair = sup.groupby('pair').size().sort_values()
    by_pair.plot(kind='barh', ax=ax, color=COLORS[:len(by_pair)])
    ax.set_xlabel('Events')
    ax.set_title('Suppression Events by Pair')

    fig.tight_layout()
    _save(fig, '09_suppression.png', output_dir)


# ══════════════════════════════════════════════════════════════════
#  Generate all charts
# ══════════════════════════════════════════════════════════════════

def generate_all_charts(results, gas_anomalies, market_impact, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    print('  Generating charts ...')
    plot_frontrun_overview(results, output_dir)
    plot_sandwich_timeline(results, output_dir)
    plot_profit_distribution(results, output_dir)
    plot_top_attackers(results, output_dir)
    plot_gas_analysis(results, market_impact, output_dir)
    plot_price_timeseries(market_impact, output_dir)
    plot_displacement_gas(results, output_dir)
    plot_arbitrage(results, output_dir)
    plot_suppression(results, output_dir)


# ══════════════════════════════════════════════════════════════════
#  Markdown report
# ══════════════════════════════════════════════════════════════════

def generate_report(results, gas_anomalies, market_impact, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    lines = []
    L = lines.append

    sw   = results.get('sandwiches', pd.DataFrame())
    dp   = results.get('displacement', pd.DataFrame())
    arb  = results.get('arbitrage', pd.DataFrame())
    sup  = results.get('suppression', pd.DataFrame())

    L('# MEV Frontrunning Analysis Report')
    L(f'*Generated: {datetime.now():%Y-%m-%d %H:%M:%S}*\n')

    # ── Executive Summary ──
    L('## 1. Executive Summary\n')
    total_swaps = sum(m['total_swaps'] for m in market_impact.values())
    L(f'- **Total swap transactions analysed**: {total_swaps:,}')
    L(f'- **Trading pairs**: {", ".join(market_impact.keys())}\n')
    L('| Frontrunning Type | Events Detected |')
    L('|-------------------|----------------|')
    L(f'| Sandwich (Insertion) | {len(sw):,} |')
    L(f'| Displacement | {len(dp):,} |')
    L(f'| Arbitrage / Back-run | {len(arb):,} |')
    L(f'| Suppression | {len(sup):,} |')
    L(f'| **Total** | **{len(sw) + len(dp) + len(arb) + len(sup):,}** |')
    L('')

    if not sw.empty and 'net_profit_usd' in sw.columns:
        L(f'- Sandwich net profit: **${sw["net_profit_usd"].sum():,.2f}**')
    if not arb.empty and 'net_profit_usd' in arb.columns:
        L(f'- Arbitrage net profit: **${arb["net_profit_usd"].sum():,.2f}**')
    unique = sw['attacker'].nunique() if not sw.empty else 0
    L(f'- Unique sandwich attackers: **{unique}**')
    L('')

    L('![Frontrunning Overview](01_frontrun_overview.png)\n')

    # ── Sandwich ──
    L('## 2. Sandwich Attacks (Insertion)\n')
    L('A sandwich attack places a **front-run** trade before and a **back-run** '
      'trade after a victim\'s swap in the same block, profiting from the price '
      'movement caused by the victim.\n')

    L('| Pair | Sandwiches | % Blocks | % Volume |')
    L('|------|-----------|---------|---------|')
    for pair, m in market_impact.items():
        L(f"| {pair} | {m['sandwich_count']:,} "
          f"| {m['sandwich_block_pct']:.2f}% | {m['sandwich_swap_pct']:.2f}% |")
    L('')

    if not sw.empty and 'net_profit_usd' in sw.columns:
        profitable = (sw['net_profit_usd'] > 0).sum()
        L(f'- Profitable: **{profitable:,}** / {len(sw):,} ({profitable / len(sw) * 100:.1f}%)')
        L(f'- Gross profit: **${sw["profit_usd"].sum():,.2f}**')
        L(f'- Net profit: **${sw["net_profit_usd"].sum():,.2f}**')
        L(f'- Avg / Median net: ${sw["net_profit_usd"].mean():,.2f} / '
          f'${sw["net_profit_usd"].median():,.2f}\n')

        top = (sw.groupby('attacker')
               .agg(count=('block_number', 'size'), total=('net_profit_usd', 'sum'))
               .sort_values('total', ascending=False).head(10))
        L('### Top 10 Sandwich Attackers\n')
        L('| Attacker | Count | Net Profit (USD) |')
        L('|----------|-------|-----------------|')
        for addr, row in top.iterrows():
            L(f'| `{addr[:10]}…{addr[-6:]}` | {int(row["count"]):,} | ${row["total"]:,.2f} |')
        L('')

    L('![Sandwich Timeline](02_sandwich_timeline.png)')
    L('![Profit Distribution](03_profit_distribution.png)')
    L('![Top Attackers](04_top_attackers.png)\n')

    # ── Displacement ──
    L('## 3. Displacement Frontrunning\n')
    L('Displacement occurs when a frontrunner observes a pending swap and submits '
      'their own transaction **in the same direction** with a **higher gas price**, '
      'getting executed first and leaving the victim with a worse price.\n')
    L(f'- Total displacement events: **{len(dp):,}**')
    if not dp.empty:
        L(f'- Avg gas ratio (frontrunner / victim): **{dp["gas_ratio"].mean():.2f}×**')
        L(f'- Pairs: {", ".join(dp["pair"].unique())}')
        L('')
        top_fr = dp['frontrunner_entity'].value_counts().head(5)
        L('### Top 5 Displacement Frontrunners\n')
        L('| Entity | Events |')
        L('|--------|--------|')
        for addr, cnt in top_fr.items():
            L(f'| `{addr[:10]}…{addr[-6:]}` | {cnt:,} |')
    L('')
    L('![Displacement](07_displacement.png)\n')

    # ── Arbitrage ──
    L('## 4. Arbitrage / Back-running\n')
    L('Back-running occurs when an entity detects a large swap and immediately '
      'trades in the **opposite direction** to profit from the price reversion '
      'after the large trade\'s impact.\n')
    L(f'- Total back-run events: **{len(arb):,}**')
    if not arb.empty and 'net_profit_usd' in arb.columns:
        L(f'- Net profit: **${arb["net_profit_usd"].sum():,.2f}**')
        L(f'- Avg net profit: **${arb["net_profit_usd"].mean():,.2f}**')
        top_br = arb['backrunner_entity'].value_counts().head(5)
        L('')
        L('### Top 5 Back-runners\n')
        L('| Entity | Events |')
        L('|--------|--------|')
        for addr, cnt in top_br.items():
            L(f'| `{addr[:10]}…{addr[-6:]}` | {cnt:,} |')
    L('')
    L('![Arbitrage](08_arbitrage.png)\n')

    # ── Suppression ──
    L('## 5. Suppression\n')
    L('Suppression involves an entity flooding a block with **many high-gas '
      'transactions**, crowding out normal users and/or delaying their txs.\n')
    L(f'- Total suppression events: **{len(sup):,}**')
    if not sup.empty:
        L(f'- Avg gas premium: **{sup["gas_premium"].mean():.1f}×**')
        top_s = sup['suppressor_entity'].value_counts().head(5)
        L('')
        L('### Top 5 Suppressors\n')
        L('| Entity | Events |')
        L('|--------|--------|')
        for addr, cnt in top_s.items():
            L(f'| `{addr[:10]}…{addr[-6:]}` | {cnt:,} |')
    L('')
    L('![Suppression](09_suppression.png)\n')

    # ── Gas ──
    L('## 6. Gas Price Analysis\n')
    L('| Pair | Sandwich Block Gas | Normal Block Gas | Premium |')
    L('|------|-------------------|-----------------|---------|')
    for pair, m in market_impact.items():
        ga = m['gas_attack_median'] / 1e9 if m['gas_attack_median'] else 0
        gn = m['gas_normal_median'] / 1e9 if m['gas_normal_median'] else 0
        prem = (ga / gn - 1) * 100 if gn > 0 else 0
        L(f'| {pair} | {ga:.2f} Gwei | {gn:.2f} Gwei | {prem:+.1f}% |')
    L('')
    L('![Gas Analysis](05_gas_analysis.png)')
    L('![Price Timeseries](06_price_timeseries.png)\n')

    # ── Methodology ──
    L('## 7. Methodology & Limitations\n')
    L('### Detection Algorithms\n')
    L('1. **Sandwich (Insertion)**: Same block, same entity executes two swaps in '
      'opposite directions with ≥ 1 victim swap (same direction as front-run) between them.')
    L('2. **Displacement**: Same block, same direction, different entities; frontrunner '
      'pays ≥ 1.5× gas price of victim and executes first (within 5 tx positions).')
    L('3. **Arbitrage / Back-run**: Within 3 tx positions after a large swap (> 90th '
      'percentile), a different entity trades in the opposite direction.')
    L('4. **Suppression**: An entity submits ≥ 3 swaps in one block with ≥ 3× the '
      'block median gas price.\n')
    L('### Limitations\n')
    L('- Only on-chain data; mempool-level displacement (dropped victim txs) is invisible.')
    L('- Gas cost uses fixed 150k gas/swap estimate.')
    L('- USD conversion from reserve-derived ETH prices; BTC/ETH ratio approximated.')
    L('- Entity identification is heuristic (router → `to` field; else `sender`).')
    L('- Displacement detection is conservative; true rate is likely higher.\n')

    report_path = os.path.join(output_dir, 'report.md')
    with open(report_path, 'w') as f:
        f.write('\n'.join(lines))
    print(f'  Report saved to {report_path}')
