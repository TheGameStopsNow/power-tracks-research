
import json
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any
import glob
from pathlib import Path

# Configuration

# Operational Rules
IMPACTOR_RULES = {
    "min_runup_1d": 0.10,  # 10%
    "sigma_mult": 2.0      # 2 sigma
}
BINDER_RULES = {
    "min_return_30_90": 0.10, # 10%
    "min_path_skew": 0.70     # 70% time above start
}

def load_minute_bars(symbol: str, date_str: str, base_dir: Path, days_forward: int = 5) -> pd.DataFrame:
    """Loads minute bars for a symbol starting from a date."""
    start_date = datetime.strptime(date_str, "%Y-%m-%d")
    end_date = start_date + timedelta(days=days_forward + 5) # Buffer
    minute_bars_dir = base_dir / "data" / "minute_bars"
    
    dfs = []
    current = start_date
    while current <= end_date:
        d_str = current.strftime("%Y-%m-%d")
        file_path = minute_bars_dir / f"{symbol}_{d_str}_minute.csv"
        if file_path.exists():
            try:
                df = pd.read_csv(file_path)
                # Ensure columns
                if 'timestamp' in df.columns and 'close' in df.columns:
                    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_localize(None)
                    dfs.append(df)
            except Exception:
                pass
        current += timedelta(days=1)
    
    if not dfs:
        return pd.DataFrame()
    
    full_df = pd.concat(dfs).sort_values('timestamp').reset_index(drop=True)
    return full_df

# ... (skipping unchanged metric functions) ...

def compute_short_term_metrics(bars: pd.DataFrame, start_time: datetime) -> Dict[str, float]:
    """Computes 1d, 3d, 5d returns and runups."""
    if bars.empty:
        return {}
    
    # Filter to start time
    bars = bars[bars['timestamp'] >= start_time].copy()
    if bars.empty:
        return {}
    
    start_price = bars.iloc[0]['close']
    metrics = {}
    
    for days in [1, 3, 5]:
        cutoff = start_time + timedelta(days=days)
        period_bars = bars[bars['timestamp'] <= cutoff]
        
        if period_bars.empty:
            continue
            
        end_price = period_bars.iloc[-1]['close']
        max_price = period_bars['close'].max()
        
        ret = np.log(end_price / start_price)
        runup = np.log(max_price / start_price)
        
        if days == 1 and start_time.year == 2024 and start_time.month == 5 and start_time.day == 13:
             print(f"DEBUG: StartTime={start_time} StartPrice={start_price} EndTime={period_bars.iloc[-1]['timestamp']} EndPrice={end_price} MaxPrice={max_price} Return={ret}")

        metrics[f"return_{days}d"] = ret
        metrics[f"runup_{days}d"] = runup
        
    return metrics

def compute_path_skew(bars: pd.DataFrame, start_time: datetime, days: int = 90) -> float:
    """Computes fraction of time price is above start price."""
    if bars.empty:
        return 0.0
        
    cutoff = start_time + timedelta(days=days)
    period_bars = bars[(bars['timestamp'] >= start_time) & (bars['timestamp'] <= cutoff)]
    
    if period_bars.empty:
        return 0.0
        
    start_price = period_bars.iloc[0]['close']
    above_count = (period_bars['close'] > start_price).sum()
    total_count = len(period_bars)
    
    return above_count / total_count if total_count > 0 else 0.0

def main():
    base_dir = Path(__file__).resolve().parent.parent
    input_file = base_dir / "data" / "historical_bursts.json"
    output_file = base_dir / "output" / "effect_roles_labels.json"
    
    print(f"Loading {input_file}...")
    if not input_file.exists():
        print(f"Error: {input_file} not found. Please place historical_bursts.json in data/.")
        return

    with open(input_file) as f:
        data = json.load(f)
    
    bursts = data.get("perBurst", [])
    labeled_bursts = []
    
    print(f"Processing {len(bursts)} bursts...")
    
    # Load TISA Echo Data (GME vs GME 2021)
    # Map: date -> min_score across all templates
    echo_matches = {}
    
    # We specifically want to validate the "Echo" role as a replay of the 2021 event.
    tisa_output_dir = base_dir.parent / "01_selectivity" / "output"
    tisa_files = list(tisa_output_dir.glob("tisa_spike_signatures_GME_vs_GME_2021_*.json"))
    
    print(f"Loading {len(tisa_files)} TISA files for Echo (GME vs GME 2021)...")
    
    for tf in tisa_files:
        try:
            with open(tf) as f:
                tisa_data = json.load(f)
                for entry in tisa_data:
                    d = entry.get('date')
                    score = entry.get('realBest', 999.0)
                    
                    if d not in echo_matches or score < echo_matches[d]:
                        echo_matches[d] = score
        except Exception:
            pass

    # Compute Macro Counts (Unique Symbols per Date)
    burst_counts = {}
    date_symbols = {}
    for b in bursts:
        d = b.get('date')
        sym = b.get('symbol')
        if d and sym:
            if d not in date_symbols:
                date_symbols[d] = set()
            date_symbols[d].add(sym)
            
    for d, syms in date_symbols.items():
        burst_counts[d] = len(syms)

    # DEBUG: Print Echo Score Distribution
    scores = [s for s in echo_matches.values()]
    if scores:
        print(f"DEBUG: Echo Scores (N={len(scores)})")
        print(f"Min: {min(scores)}")
        print(f"Max: {max(scores)}")
        print(f"Mean: {sum(scores)/len(scores)}")
        print(f"Percentiles: {np.percentile(scores, [0, 25, 50, 75, 100])}")
        print(f"Scores < 2.5: {len([s for s in scores if s < 2.5])}")
    else:
        print("DEBUG: No Echo scores found.")

    for i, burst in enumerate(bursts):
        track_id = burst.get("trackId")
        symbol = burst.get("symbol")
        date_str = burst.get("date")
        
        # ... (load bars) ...
        # file_path = f"{MINUTE_BARS_DIR}/{symbol}_{date_str}_minute.csv" # Removed manually constructed path
        bars_short = load_minute_bars(symbol, date_str, base_dir, days_forward=5)
        start_time = datetime.strptime(date_str, "%Y-%m-%d")
        impactor_metrics = compute_short_term_metrics(bars_short, start_time)
        
        # Impactor
        is_impactor = False
        if impactor_metrics.get("runup_1d", 0) > IMPACTOR_RULES["min_runup_1d"]:
            is_impactor = True
            
        # Binder
        is_binder = False
        horizons = burst.get("horizons", {})
        h90 = horizons.get("90", {})
        h30 = horizons.get("30", {})
        ret_90 = h90.get("logReturn", 0)
        ret_30 = h30.get("logReturn", 0)
        if ret_90 > BINDER_RULES["min_return_30_90"] or ret_30 > BINDER_RULES["min_return_30_90"]:
            is_binder = True
            
        # Echo Logic (GME vs GME 2021)
        is_echo = False
        if symbol == "GME" and date_str in echo_matches:
            score = echo_matches[date_str]
            if score < 2.5:
                is_echo = True
                
        # Macro Logic
        is_macro = False
        if burst_counts.get(date_str, 0) > 3:
            is_macro = True
            
        burst["effect"] = {
            "impactor": is_impactor,
            "binder": is_binder,
            "echo": is_echo,
            "macro": is_macro,
            "metrics": impactor_metrics
        }
        labeled_bursts.append(burst)
        
        if i % 10 == 0:
            print(f"Processed {i}/{len(bursts)}")

    output_data = {"perBurst": labeled_bursts}
    output_file.parent.mkdir(exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)
    
    print(f"Saved to {output_file}")

if __name__ == "__main__":
    main()
