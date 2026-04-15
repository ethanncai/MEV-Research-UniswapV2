#!/usr/bin/env python3
"""
MEV Frontrunning Analysis — main entry point.
Detects four types: Sandwich, Displacement, Arbitrage/Back-run, Suppression.
"""
import os
import sys
import time

from config import OUTPUT_DIR
from data_loader import load_all_pairs, build_eth_price_index, build_btc_eth_index
from detectors import (detect_sandwiches, detect_displacement,
                       detect_arbitrage, detect_suppression, detect_gas_anomalies)
from analyzers import (calculate_sandwich_profits, calculate_displacement_profits,
                       calculate_arbitrage_profits, analyze_market_impact)
from visualizer import generate_all_charts, generate_report
from excel_export import export_excel

import pandas as pd


def main():
    t0 = time.time()

    print('=' * 60)
    print('  MEV Frontrunning Analysis Tool')
    print('  COMP5566 — Project 8')
    print('  Detecting: Sandwich · Displacement · Arbitrage · Suppression')
    print('=' * 60)

    # ---- 1. Load data ----
    print('\n[1/5] Loading data ...')
    pair_data = load_all_pairs()
    if not pair_data:
        print('No data found. Make sure the data/ directory exists.')
        sys.exit(1)

    # ---- 2. ETH price index ----
    print('\n[2/5] Building price indices ...')
    eth_price_idx = build_eth_price_index(pair_data)
    if eth_price_idx.empty:
        print('  Warning: Could not build ETH price index; using fallback.')
    else:
        print(f'  ETH/USD: {len(eth_price_idx):,} data points, '
              f'range ${eth_price_idx.min():,.0f} – ${eth_price_idx.max():,.0f}')

    btc_eth_idx = build_btc_eth_index(pair_data)
    if btc_eth_idx.empty:
        print('  Warning: Could not build BTC/ETH index; using fallback ratio 15.0.')
    else:
        print(f'  BTC/ETH: {len(btc_eth_idx):,} data points, '
              f'range {btc_eth_idx.min():.1f} – {btc_eth_idx.max():.1f}')

    # ---- 3. Detect all frontrunning types ----
    print('\n[3/5] Detecting frontrunning activities ...')

    all_sandwiches, all_victims = [], []
    all_displacements, all_arbitrages, all_suppressions = [], [], []
    all_gas_anomalies = {}

    for pair_name, data in pair_data.items():
        swaps = data['swaps']
        print(f'\n  ── {pair_name} ({len(swaps):,} swaps) ──')

        # Sandwich
        sw, vic = detect_sandwiches(swaps, pair_name)
        if not sw.empty:
            all_sandwiches.append(sw)
            all_victims.append(vic)
        print(f'    Sandwich (Insertion):  {len(sw):,} attacks, {len(vic):,} victims')

        # Displacement
        disp = detect_displacement(swaps, pair_name)
        if not disp.empty:
            all_displacements.append(disp)
        print(f'    Displacement:          {len(disp):,} events')

        # Arbitrage / back-run
        arb = detect_arbitrage(swaps, pair_name)
        if not arb.empty:
            all_arbitrages.append(arb)
        print(f'    Arbitrage / Back-run:  {len(arb):,} events')

        # Suppression
        supp = detect_suppression(swaps, pair_name)
        if not supp.empty:
            all_suppressions.append(supp)
        print(f'    Suppression:           {len(supp):,} events')

        anomalies, entity_summary = detect_gas_anomalies(swaps, pair_name)
        all_gas_anomalies[pair_name] = (anomalies, entity_summary)

    sandwiches_df  = pd.concat(all_sandwiches,    ignore_index=True) if all_sandwiches    else pd.DataFrame()
    victims_df     = pd.concat(all_victims,        ignore_index=True) if all_victims        else pd.DataFrame()
    disp_df        = pd.concat(all_displacements,  ignore_index=True) if all_displacements  else pd.DataFrame()
    arb_df         = pd.concat(all_arbitrages,     ignore_index=True) if all_arbitrages     else pd.DataFrame()
    supp_df        = pd.concat(all_suppressions,   ignore_index=True) if all_suppressions   else pd.DataFrame()

    print(f'\n  ── Totals ──')
    print(f'    Sandwich:     {len(sandwiches_df):,}')
    print(f'    Displacement: {len(disp_df):,}')
    print(f'    Arbitrage:    {len(arb_df):,}')
    print(f'    Suppression:  {len(supp_df):,}')

    # ---- 4. Analyse profits ----
    print('\n[4/5] Analysing profits and market impact ...')
    sandwiches_df = calculate_sandwich_profits(sandwiches_df, eth_price_idx, btc_eth_idx)
    disp_df       = calculate_displacement_profits(disp_df, eth_price_idx, btc_eth_idx, pair_data)
    arb_df        = calculate_arbitrage_profits(arb_df, eth_price_idx, btc_eth_idx)
    market_impact = analyze_market_impact(sandwiches_df, pair_data)

    if not sandwiches_df.empty and 'net_profit_usd' in sandwiches_df.columns:
        print(f'  Sandwich net profit:   ${sandwiches_df["net_profit_usd"].sum():,.2f}')
    if not disp_df.empty and 'victim_loss_usd' in disp_df.columns:
        print(f'  Displacement victim loss: ${disp_df["victim_loss_usd"].sum():,.2f}')
        print(f'  Displacement est. profit: ${disp_df["estimated_profit_usd"].sum():,.2f}')
    if not arb_df.empty and 'net_profit_usd' in arb_df.columns:
        print(f'  Arbitrage net profit:  ${arb_df["net_profit_usd"].sum():,.2f}')

    # ---- 5. Output ----
    print('\n[5/5] Generating report, charts and Excel ...')
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    detection_results = {
        'sandwiches': sandwiches_df,
        'victims': victims_df,
        'displacement': disp_df,
        'arbitrage': arb_df,
        'suppression': supp_df,
    }

    # CSV
    for name, df in detection_results.items():
        if not df.empty:
            p = os.path.join(OUTPUT_DIR, f'{name}.csv')
            df.to_csv(p, index=False)

    # Excel
    xlsx_path = export_excel(detection_results, OUTPUT_DIR)
    print(f'  Excel workbook  → {xlsx_path}')

    # Charts & report
    generate_all_charts(detection_results, all_gas_anomalies, market_impact, OUTPUT_DIR)
    generate_report(detection_results, all_gas_anomalies, market_impact, OUTPUT_DIR)

    elapsed = time.time() - t0
    print(f'\nDone in {elapsed:.1f}s.  Results → {OUTPUT_DIR}/')


if __name__ == '__main__':
    main()
