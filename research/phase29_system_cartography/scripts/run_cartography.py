#!/usr/bin/env python3
"""
Operation System Cartography: Master Execution
==============================================
Phase 29

Orchestrates the mapping of the Global Market System.

Modules:
1. Grammar Decoder (The Language)
2. Options Overlay (The Grid)
3. TISA Chronos (The Timeline)
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import json

# Import Phase 29 Modules
PHASE29_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PHASE29_DIR))

from grammar_decoder import GrammarDecoder
from options_overlay import OptionsOverlay


# Import Data Loaders from EDGX
RESEARCH_DIR = PHASE29_DIR.parent
EDGX_DIR = RESEARCH_DIR / "edgx_deep_decode"
sys.path.insert(0, str(EDGX_DIR))

try:
    from loader import load_edgx_data, get_sample_dirs
except ImportError:
    print("Warning: Could not import EDGX native loaders. using mock/fallback?")

# Define Data Paths
# Define Data Paths
REPO_ROOT = PHASE29_DIR.parent.parent.parent
RESEARCH_DATA_PATH = REPO_ROOT / "research"
# Fallback for external data if it exists relative to the repo
POWER_TRACKS_DATA_PATH = REPO_ROOT.parent / "power-tracks-data" / "storage" / "ticks"

def get_all_files():
    """Recursively find all csv files in data directories."""
    files = []
    
    # scan research dir
    print(f"[1] Identifying Targets across Research Directory...")
    research_files = list(RESEARCH_DATA_PATH.rglob("*.csv")) + list(RESEARCH_DATA_PATH.rglob("*.json"))
    print(f"  Found {len(research_files)} files in {RESEARCH_DATA_PATH}")
    files.extend(research_files)

    # scan external data repo (Deep History)
    if POWER_TRACKS_DATA_PATH.exists():
        print(f"[1b] Identifying Targets in Deep History Archive...")
        history_files = list(POWER_TRACKS_DATA_PATH.rglob("*.csv"))
        print(f"  Found {len(history_files)} files in {POWER_TRACKS_DATA_PATH}")
        files.extend(history_files)
    else:
        print(f"Warning: External data path not found: {POWER_TRACKS_DATA_PATH}")

    return files

def run_system_cartography():
    print("=" * 60)
    print("OPERATION SYSTEM CARTOGRAPHY: PHASE 29")
    print("=" * 60)
    
    # 1. Target Identification
    print("[1] Identifying Targets across Research Directory...")
    
    # Define paths to scan (Phases with large data)
    all_files = get_all_files()
    
    # Filter for tick data or high fidelity
    # accepted: *ticks.csv, *super_res.csv
    target_files = [f for f in all_files if 'ticks' in f.name or 'res' in f.name or 'trade' in f.name]
    
    # REMOVED LIMITS - PROCESSING ALL TARGETS
    # Prioritize GME and recent dates for reporting order, but process everything.
    target_files.sort(key=lambda x: (not 'GME' in x.name, x.stat().st_mtime), reverse=True)
    
    print(f"Targets Selected: {len(target_files)} files (Full Cartography Mode).")
    
    if not target_files:
        print("No data files found in research directories. Aborting.")
        return

    
    print(f"Targets Selected: {len(target_files)} files (Full Cartography Mode).")
    
    report = {}
    daily_summaries = [] # Store date/close for Tisa Chronos
    
    # 2. Execution Loop
    for file_path in target_files:
        target_name = file_path.stem
        # print(f"Processing: {target_name}")
        
        # Load Data (Generic CSV/JSON Loader)
        try:
            if file_path.suffix == '.json':
                with open(file_path, 'r') as f:
                    data = json.load(f)
                # Polygon raw format wrapper
                if isinstance(data, dict) and 'results' in data:
                    df = pd.DataFrame(data['results'])
                else:
                    df = pd.DataFrame(data)
                
                # Polygon JSON fields mapping
                if 'sip_timestamp' in df.columns:
                    df['timestamp'] = pd.to_datetime(df['sip_timestamp'], unit='ns')
                if 't' in df.columns: # aggregates
                     df['timestamp'] = pd.to_datetime(df['t'], unit='ms')
            else:
                df = pd.read_csv(file_path)
            
            # Normalize column names to lowercase
            df.columns = [c.lower() for c in df.columns]
            
            # Map common variations to standard 'price' and 'close'
            if 'price' in df.columns:
                df['close'] = df['price']
            elif 'close' in df.columns:
                df['price'] = df['close']
            elif 'last' in df.columns:
                df['price'] = df['last']
                df['close'] = df['last']
                
            # If still missing, we can't process
            if 'close' not in df.columns:
                # print(f"Skipping {file_path.name}: Missing 'close'/'price' column. Found: {df.columns.tolist()}")
                continue
                
            # Synthesize timestamp if missing (some old files might define it differently)
            if 'timestamp' not in df.columns:
                if 'time' in df.columns:
                    df['timestamp'] = df['time']
                else:
                    # If index is monotonic, use index as dummy time
                    df['timestamp'] = df.index
        except Exception as e:
            # print(f"Failed to load {file_path.name}: {e}")
            continue
        
        symbol_results = {}
        
        # A. Grammar Decoding & 7-4-1 Hunt
        try:
            decoder = GrammarDecoder(df)
            symbol_results['grammar_seqs'] = decoder.find_sequences(length=3, top_n=5)
            # hunt_741 returns dict, safe to serialize
            symbol_results['741_hunt'] = decoder.hunt_741()
            # Phase 29b: 1-4-7 Reverse Hunt
            rev_hunt = decoder.hunt_reverse_sequence()
            symbol_results['147_hunt'] = rev_hunt
            
            # Phase 29g: High-Fidelity Pattern Search (Counts & Deltas)
            count_hunt = decoder.hunt_order_counts(df)
            symbol_results['order_count_hunt'] = count_hunt
            
            delta_hunt = decoder.hunt_price_deltas(df)
            symbol_results['price_delta_hunt'] = delta_hunt
        except Exception as e:
             symbol_results['error_grammar'] = str(e)
        
        # B. Options Overlay
        try:
            # Mocking flow for now as we might not have it strictly aligned
            mock_flow = pd.DataFrame({
                "strike_price": [10, 20, 30],
                "size": [1000, 500, 100]
            })
            # Check for overlay requirements before running
            if 'close' in df.columns:
                overlay = OptionsOverlay(df, mock_flow)
                magnets = overlay.identify_magnets()
                symbol_results['gravity'] = overlay.calculate_gravity_score(magnets)
                
                # Capture Daily Summary for Chronos (using mean price of day)
                # Parse date from filename or use timestamp
                try:
                    # GME_YYYY-MM-DD...
                    date_str = file_path.name.split('_')[1]
                    daily_mean = df['close'].mean()
                    daily_summaries.append({'date': pd.to_datetime(date_str), 'close': daily_mean})
                except:
                    pass
        except Exception as e:
            # symbol_results['error_options'] = str(e)
            pass
        

    # 3. Report Generation
    print("\n" + "=" * 60)
    print("SYSTEM MAP GENERATED")
    print("=" * 60)
    
    report_path = PHASE29_DIR / "output" / "SYSTEM_CARTOGRAPHY_REPORT.json"
    
    # Convert sets/tuples to lists for JSON
    def serialize(obj):
        if isinstance(obj, tuple):
            return list(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        return str(obj)
        
    print(f"\n[4] Saving System Map to {report_path}...")
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)
        
    print("=" * 60)
    print(f"Report saved to {report_path}")
    
    # Check for 7-4-1 Success
    hits_741 = 0
    try:
        for target, res in report.items(): # Changed 'results' to 'report' here
            if '741_hunt' in res and 'sequence_741_matches' in res['741_hunt']:
                matches = res['741_hunt']['sequence_741_matches']
                if matches:
                    hits_741 += len(matches)
                    print(f"!!! 7-4-1 SEQUENCE DETECTED IN {target} !!!")
    except Exception as e:
        print(f"Error generating summary: {e}")
            
    if hits_741 == 0:
        print("Status: No direct '0x07 -> 0x04 -> 0x01' sequences found in sample set.")
        print("Recommendation: Expand search to Time Intervals or larger datasets.")

if __name__ == "__main__":
    try:
        run_system_cartography()
    except Exception as e:
        print(f"CRITICAL FAILURE in Cartography: {e}")
        import traceback
        traceback.print_exc()
