#!/usr/bin/env python3
"""
Detection Harness
=================

Orchestrates Layers 0-4 to hunt for covert channels.
"""

import argparse
import json
import pandas as pd
import numpy as np
from pathlib import Path
import sys

# Repo root
BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))

# Layers
from research.phase57_detection_stack.layer0_data_harness import TickLoader, RegimeConditioner
from research.phase57_detection_stack.layer1_point_process import HawkesEstimator, ks_test_uniformity
from research.phase57_detection_stack.layer2_cyclostationary import MultiScaleScanner
from research.phase57_detection_stack.layer3_latency import VenueLagTracker
from research.phase57_detection_stack.layer4_motif import MotifMiner

# Regulator A Modules (Phase 72)
from research.phase72_rega import layer2_phase_locking as l2_reg
from research.phase72_rega import layer3_dense_dynamics as l3_dense
from research.phase72_rega import layer3_temporal_coherence as l3_coh

def run_harness(ticker, date, output_file=None, jitter_ns=0, extended_hours=False):
    print(f"=== Detection Harness (v2 Hardened): {ticker} on {date} (Extended: {extended_hours}) ===")
    
    # Paths
    PHASE_DIR = Path(__file__).resolve().parent
    DATA_DIR = PHASE_DIR / "data"

    # 1. Load Data
    # Prefer local phase data, fall back to global if empty
    loader = TickLoader(data_dir=DATA_DIR)
    df = loader.load_ticks(date, ticker, jitter_amount_ns=jitter_ns)
    
    # Fallback to global if local failed
    if df is None:
        print("Local data not found, trying global repo data...")
        loader = TickLoader() # Default global
        df = loader.load_ticks(date, ticker, jitter_amount_ns=jitter_ns)

    if df is None: return

    # Phase 57b: Data QA Gate
    from research.phase57_detection_stack.layer0_data_harness import DataQualityGate
    gate = DataQualityGate()
    qa_res = gate.check_quality(df)
    
    print(f"Data Loaded: {len(df)} trades. QA: {qa_res}")
    
    # Phase 61: Assert Date Match (Global Control Validity)
    # df['timestamp'] is UTC datetime
    # requested 'date' is YYYY-MM-DD string
    if not df.empty:
        loaded_dates = df['timestamp'].dt.date.unique()
        requested_dt = pd.Timestamp(date).date()
        
        # Check if requested date is PRESENT in loaded data
        if requested_dt not in loaded_dates:
            print(f"CRITICAL ERROR: Loaded data does NOT contain requested date {date}.")
            print(f"Loaded Dates: {loaded_dates}")
            raise ValueError(f"CRITICAL: Data Verification Failed. Requested {date} not found in loaded data. Aborting.")

        # Explicitly filter to requested date (if multi-day file loaded)
        df = df[df['timestamp'].dt.date == requested_dt].copy()
        print(f"Date Match Verified: {requested_dt}")
    
    # Phase 57b: Time Slicing Fix
    # Generate windows
    
    if extended_hours:
        # 04:00 to 20:00 ET (08:00 to 24:00+ UTC approx)
        # Or just take the whole dataframe for that UTC day
        t_open = df['timestamp'].iloc[0].normalize() + pd.Timedelta(hours=4) # 4 AM UTC? Pre-market starts 4AM ET = 8AM UTC
        # Let's just use the whole loaded day if extended_hours is True, 
        # or maybe filter 08:00 UTC to 00:00 UTC next day?
        # Simpler: If extended, process all ticks for that date.
        df_session = df.copy()
        print("Extended Hours: Using full 24h day ticks.")
    else:
        # Regular Session starts 13:30 UTC (9:30 ET) or 14:30 UTC depending on DST.
        # May 14 2024 is DST -> EDT is UTC-4.
        # 9:30 AM EDT = 13:30 UTC.
        
        t_open = df['timestamp'].iloc[0].normalize() + pd.Timedelta(hours=13, minutes=30)
        t_close = t_open + pd.Timedelta(hours=6, minutes=30)
        
        # Filter to session
        df_session = df[(df['timestamp'] >= t_open) & (df['timestamp'] < t_close)].copy()
        if df_session.empty:
            print("No session data found. Using all data.")
            df_session = df.copy()
        
    print(f"Processing Data: {len(df_session)} trades.")
    
    # Conditioning
    print("Conditioning...")
    conditioner = RegimeConditioner()
    df_session = conditioner.label_regimes(df_session)
    
    # Loop Windows
    window_size = 5 * 60 # 5 mins
    start_ts = df_session['timestamp'].min()
    end_ts = df_session['timestamp'].max()
    
    current_ts = start_ts
    windows_results = []
    
    window_limit = 500 if extended_hours else 10 # Process more windows for extended hours?
    w_count = 0
    
    while current_ts < end_ts and w_count < window_limit:
        next_ts = current_ts + pd.Timedelta(seconds=window_size)
        slice_df = df_session[(df_session['timestamp'] >= current_ts) & (df_session['timestamp'] < next_ts)].copy()
        
        current_ts = next_ts
        if len(slice_df) < 500: continue
        w_count += 1
        
        print(f"\n--- Processing Window {w_count} ({slice_df['timestamp'].min()} - {slice_df['timestamp'].max()}) ---")
        
        w_res = {
            'window_id': w_count,
            'start': str(slice_df['timestamp'].min()),
            'count': len(slice_df),
            'regime': slice_df['regime'].mode()[0] if not slice_df['regime'].empty else 'Unknown'
        }
        
        # Layer 1: Point Process
        timestamps = slice_df['timestamp'].astype(np.int64) / 1e9
        timestamps = timestamps.values
        if len(timestamps) > 2000: # subsample for Hawkes speed
            timestamps_l1 = timestamps[:2000]
        else:
            timestamps_l1 = timestamps
            
        try:
            hwk = HawkesEstimator(decay_beta=100.0)
            hwk.fit(timestamps_l1)
            # Re-get residuals on same set
            metrics = ks_test_uniformity(hwk.get_residuals(timestamps_l1))
            w_res['L1'] = {'ks_stat': metrics['statistic'], 'p_val': metrics['pvalue']}
        except Exception as e:
            w_res['L1'] = {'error': str(e)}

        # Layer 2: Cyclo
        try:
            scanner = MultiScaleScanner(bin_sizes_ms=[1, 2, 5, 10, 20])
            peaks = scanner.scan_all(timestamps)
            w_res['L2'] = {'signals': peaks[:3]} # Store top 3 persistent
            
            # Phase 61: Phase Locking (Absolute & Relative)
            # Reference for Absolute Phase: Midnight UTC of the day
            # slice_df['timestamp'] are UTC.
            # Find midnight of that day
            day_midnight = slice_df['timestamp'].iloc[0].normalize()
            t_ref_abs = day_midnight.value / 1e9 # seconds
            t_ref_rel = timestamps[0] # seconds
            
            # Convert timestamps to nanoseconds for the new method
            ts_ns = slice_df['timestamp'].astype(np.int64).values
            
            for sig in w_res['L2']['signals']:
                try:
                    f = sig['freq_hz']
                    
                    # Regulator A: Global Phase Locking Metrics
                    # We need event counts in bins for the RegA module (which expects binned series)
                    # Use the bin size from the signal signal['bin_size'] (ms)
                    # Convert ms to Hz sampling rate
                    bin_ms = sig.get('bin_size', 10)
                    fs_hz = 1000.0 / bin_ms
                    
                    # Re-bin the timestamps (L2 module wants event_counts array)
                    duration_s = timestamps[-1] - timestamps[0]
                    n_bins = int(np.ceil(duration_s * fs_hz))
                    counts, _ = np.histogram(timestamps - timestamps[0], bins=n_bins)
                    
                    plv_res = l2_reg.phase_locking_metrics(
                        counts, 
                        fs_hz, 
                        f, 
                        min_segments=5
                    )
                    
                    sig['plv'] = plv_res.get('plv', 0.0)
                    sig['rayleigh_p'] = plv_res.get('rayleigh_p', 1.0)
                    sig['drift_slope_hz'] = plv_res.get('drift_slope_hz', 0.0)
                    sig['phase_drift_rms'] = plv_res.get('phase_drift_rms', 0.0)
                    sig['amp_cv'] = plv_res.get('amp_cv', 1.0)
                    sig['lock_score_adj'] = plv_res.get('lock_score_adj', 0.0)
                    
                    # Legacy fields for backward compat
                    sig['phase_var_abs'] = plv_res.get('circ_var', 1.0)
                    
                except Exception as e:
                    sig['phase_error'] = str(e)
                    sig['plv'] = 0.0
                    sig['rayleigh_p'] = 1.0
        except Exception as e:
            w_res['L2'] = {'error': str(e)}

        # Layer 3: Latency
        try:
            # Lit only defaults
            v_counts = slice_df['venue'].astype(str).value_counts()
            # Filter lit
            lit_candidates = [v for v in v_counts.index if v not in ['OTC', '4', 'nan']]
            
            if len(lit_candidates) >= 2:
                v1, v2 = lit_candidates[0], lit_candidates[1]
                tracker = VenueLagTracker(v1, v2, exclude_otc=True)
                
                # Phase 61: Added lag_times return
                lags, lag_times = tracker.compute_lags(slice_df)
                
                dist_stats = tracker.analyze_distribution(lags)
                
                # Regulator A: Dense Dynamics & Temporal Coherence
                coherence_res = {}
                switching_score = 0.0
                
                if dist_stats and dist_stats.get('multimodal'):
                    # 1. Get GMM Params
                    comps = dist_stats['components']
                    # sorted by mean in dist_stats already
                    m0, m1 = comps[0]['mean'], comps[1]['mean']
                    w0, w1 = comps[0]['weight'], comps[1]['weight']
                    v0 = comps[0].get('var', 1e-4)
                    v1 = comps[1].get('var', 1e-4) # Fallback if var missing
                    
                    # 2. Compute Dense Dynamics (Global GMM -> Local Weights)
                    # using updated lag_times from tracker
                    if len(lags) > 0 and len(lag_times) > 0:
                        # Normalize times to window start
                        w_start_sec = pd.Timestamp(w_res['start']).value / 1e9
                        times_rel = lag_times - w_start_sec
                        
                        dense_dyn = l3_dense.compute_dense_dynamics(
                            lags, times_rel,
                            (m0, m1), (v0, v1),
                            subwindow_size_s=10.0,
                            hop_size_s=2.0,
                            uncertainty_epsilon=0.10
                        )
                        
                        if dense_dyn.get('status') == 'ok':
                            # 3. Compute Coherence on Dense Sequence
                            # Prepare mock "dynamics" list format expected by l3_coh
                            # It expects a list of dicts with means/weights for each subwindow.
                            # But we already have the WEIGHT SERIES from dense_dyn.
                            # We can just reconstruct a "dynamics"-like object or update l3_coh to accept raw series.
                            # Actually, l3_coh.coherence_from_dynamics expects a list of subwindow fits.
                            # We can synthesize this:
                            
                            synth_dynamics = []
                            w0_s = dense_dyn['weight_series_0']
                            w1_s = dense_dyn['weight_series_1']
                            dom_s = dense_dyn['dominant_state']
                            
                            for i in range(len(w0_s)):
                                synth_dynamics.append({
                                    "valid": True,
                                    "means": [m0, m1], # Global means (fixed)
                                    "weights": [w0_s[i], w1_s[i]], # Local weights
                                    "dominant_state": dom_s[i] # Explicit state (handles -1 uncertainty)
                                })
                                
                            coherence_res = l3_coh.coherence_from_dynamics(synth_dynamics)
                            w_res['L3_dense'] = dense_dyn # Store raw dense series for evidence pack
                            
                            switching_score = coherence_res.get('p_sticky_block', 1.0) # Lower is more structured? 
                            # Actually score report uses p-values directly.
                    
                w_res['L3'] = {
                    'pair': [v1, v2], 
                    'stats': dist_stats, 
                    'coherence': coherence_res,
                    'switching_score': switching_score # placeholder
                }

            else:
                w_res['L3'] = {'status': 'Not enough lit venues'}
        except Exception as e:
            import traceback
            traceback.print_exc()
            w_res['L3'] = {'error': str(e)}

        # Layer 4: Motifs
        try:
            # Subsample for speed
            motif_df = slice_df.iloc[:2000]
            miner = MotifMiner(ngram_len=3)
            # Block shuffle
            motifs = miner.analyze_motifs(motif_df, n_perms=50, block_size=20)
            w_res['L4'] = {'top_motifs': motifs[:5]}
        except Exception as e:
            w_res['L4'] = {'error': str(e)}
            
        windows_results.append(w_res)

    results = {
        'meta': {'ticker': ticker, 'date': date, 'qa': qa_res},
        'windows': windows_results
    }
    
    if output_file:
        with open(output_file, 'w') as f:
            def default(o):
                if isinstance(o, (np.int64, np.int32, int)): return int(o)
                if isinstance(o, (np.float64, np.float32, float)): return float(o)
                if isinstance(o, (np.ndarray,)): return o.tolist()
                try: return str(o)
                except: return None
            json.dump(results, f, indent=2, default=default)
        print(f"Results saved to {output_file}")
    
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--ticker', type=str, default='GME')
    parser.add_argument('--tickers', type=str, help='Comma-separated list of tickers to run')
    parser.add_argument('--date', type=str, default='2024-05-14') 
    default_output = str(Path(__file__).resolve().parent / 'output/detection_report.json')
    parser.add_argument('--output', type=str, default=default_output)
    parser.add_argument('--jitter', action='store_true', help='Enable Zero-DT jitter')
    parser.add_argument('--extended', action='store_true', help='Process extended hours (all available ticks)')
    
    args = parser.parse_args()
    
    ticker_list = []
    if args.tickers:
        ticker_list = [t.strip() for t in args.tickers.split(',')]
    else:
        ticker_list = [args.ticker]
        
    for t in ticker_list:
        out_file = args.output
        if len(ticker_list) > 1:
            # Modify output filename
            p = Path(args.output)
            out_file = str(p.parent / f"{p.stem}_{t}{p.suffix}")
            
        print(f"\nProcessing {t}...")
        # Map boolean jitter to 1000ns (1us) default for backward compat
        j_ns = 1000 if args.jitter else 0
        run_harness(t, args.date, out_file, jitter_ns=j_ns, extended_hours=args.extended)
