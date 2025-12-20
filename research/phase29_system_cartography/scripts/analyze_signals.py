
import json
import pandas as pd
import numpy as np
from pathlib import Path
import sys

# Constants
PHASE29_DIR = Path(__file__).resolve().parent.parent
REPORT_PATH = PHASE29_DIR / "output" / "SYSTEM_CARTOGRAPHY_REPORT.json"
REPO_ROOT = PHASE29_DIR.parent.parent
# Fallback data path via repo structure
DATA_DIR = REPO_ROOT.parent / "power-tracks-data" / "storage" / "ticks"
OUTPUT_PATH = PHASE29_DIR / "output" / "SIGNAL_EFFICACY_REPORT.md"

def load_report():
    if not Path(REPORT_PATH).exists():
        print(f"Report not found at {REPORT_PATH}")
        return {}
    with open(REPORT_PATH, 'r') as f:
        return json.load(f)

def get_file_path(filename_stem):
    # Try to find the file in the data dir
    # Filename stem example: GME_2021-03-08_20210308_121400_ticks
    # Actual file likely has .csv extension
    p = Path(DATA_DIR) / f"{filename_stem}.csv"
    if p.exists():
        return p
    # Try recursively if needed, but run_cartography used simple paths.
    # Let's assume flat structure or use the find tool if this fails.
    # Actually run_cartography found them in DATA_DIR.
    return None

def analyze_price_delta_efficacy(report):
    print("Analyzing Price Delta Signal Efficacy...")
    matches = []
    
    # Extract matches
    for filename, data in report.items():
        if filename.startswith("GLOBAL"): continue
        pd_hunt = data.get('price_delta_hunt', {})
        timestamps = pd_hunt.get('price_delta_741_matches', [])
        for ts in timestamps:
            matches.append({'file': filename, 'timestamp': ts})
            
    print(f"Found {len(matches)} signals to backtest.")
    
    results = []
    
    for m in matches:
        fpath = get_file_path(m['file'])
        if not fpath:
            continue
            
        try:
            df = pd.read_csv(fpath)
            # Normalize
            df.columns = [c.lower() for c in df.columns]
            if 'time' in df.columns and 'timestamp' not in df.columns:
                df['timestamp'] = df['time']
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Find signal index
            signal_ts = pd.to_datetime(m['timestamp'])
            
            # Get data after signal
            # We assume signal_ts is in the file.
            # Using searchsorted or simple masking
            mask = df['timestamp'] >= signal_ts
            post_signal = df[mask].copy()
            
            if post_signal.empty:
                continue
                
            entry_price = post_signal.iloc[0]['close'] if 'close' in post_signal.columns else post_signal.iloc[0]['price']
            entry_time = post_signal.iloc[0]['timestamp']
            
            # Check duration available
            file_end = df.iloc[-1]['timestamp']
            duration_available = file_end - entry_time
            
            # T+10s (Short duration check)
            t_10s = entry_time + pd.Timedelta(seconds=10)
            subset_10s = post_signal[post_signal['timestamp'] >= t_10s]
            ret_10s = np.nan
            if not subset_10s.empty:
                 price_10s = subset_10s.iloc[0]['close'] if 'close' in subset_10s.columns else subset_10s.iloc[0]['price']
                 ret_10s = (price_10s - entry_price) / entry_price
                 
            # Limit check for T+1m etc
            ret_1m = np.nan
            if duration_available >= pd.Timedelta(minutes=1):
                t_1m = entry_time + pd.Timedelta(minutes=1)
                subset_1m = post_signal[post_signal['timestamp'] >= t_1m]
                if not subset_1m.empty:
                    price_1m = subset_1m.iloc[0]['close']
                    ret_1m = (price_1m - entry_price) / entry_price
            
            # If we simply returned 0.0 before, that was misleading.
            # We should return NaN or the "End of File" return.
            
            ret_eof = (df.iloc[-1]['close'] if 'close' in df.columns else df.iloc[-1]['price'] - entry_price) / entry_price
            
            # Store results
            results.append({
                'signal': '7-4-1 Price Delta',
                'file': m['file'], # Add filename to debug
                'timestamp': str(entry_time),
                'available_duration': str(duration_available),
                'ret_10s': ret_10s,
                'ret_1m': ret_1m,
                'ret_eof': ret_eof # Return to end of chunk
            })
            
        except Exception as e:
            # print(f"Error processing {m['file']}: {e}")
            pass
            
    return results

def analyze_gravity_efficacy(report):
    print("Analyzing Gravity Signal Efficacy...")
    # Gravity is a file-level score. We can treat the *start* of the high gravity day/file as the signal, 
    # OR if gravity implies a "Pin", we check if price stayed within a range.
    # Let's assume High Gravity = Prediction of Low Volatility / Pinning? 
    # User Q: "Does the gravity score tell us anything and can it be used as a signal?"
    # Let's verify if High Gravity -> Lower Future Volatility (Pinning worked).
    
    events = []
    for filename, data in report.items():
        if filename.startswith("GLOBAL"): continue
        g_data = data.get('gravity', {})
        score = g_data.get('gravity_score', 0.0) if isinstance(g_data, dict) else 0.0
        
        if score > 8.0: # High Gravity Threshold
            events.append({'file': filename, 'score': score})
            
    results = []
    for e in events:
        fpath = get_file_path(e['file'])
        if not fpath: continue
        
        try:
            df = pd.read_csv(fpath)
            # Normalize
            if 'price' in df.columns: df['close'] = df['price']
            
            # Calculate volatility of the file (Intraday Vol)
            # Std Dev of returns
            if len(df) > 100:
                rets = df['close'].pct_change().dropna()
                vol = rets.std()
                
                # We interpret High Gravity -> "Pinning" -> Expect Low Volatility?
                # OR does High Gravity appear on High Vol days (fighting the move)?
                # Let's record the Volatility.
                results.append({
                    'signal': 'High Gravity (>8.0)',
                    'score': e['score'],
                    'intraday_vol': vol,
                    'price_range_pct': (df['close'].max() - df['close'].min()) / df['close'].min()
                })
        except:
            pass
            
    return results

def write_report(delta_res, gravity_res):
    with open(OUTPUT_PATH, 'w') as f:
        f.write("# SIGNAL EFFICACY REPORT\n")
        f.write("## Phase 29h Analysis\n\n")
        
        # 1. PRICE DELTA
        f.write("## 1. Price Delta Signal: [0.07, 0.04, 0.01]\n")
        if delta_res:
            df_res = pd.DataFrame(delta_res)
            # Save Raw Data
            csv_path = Path(OUTPUT_PATH).parent / "price_delta_signals.csv"
            df_res.to_csv(csv_path, index=False)
            print(f"Saved raw Price Delta data to {csv_path}")
            
            avg_10s = df_res['ret_10s'].mean() * 100
            avg_eof = df_res['ret_eof'].mean() * 100
            
            f.write(f"- **Sample Size:** {len(df_res)}\n")
            f.write(f"- **Raw Data:** [price_delta_signals.csv](./price_delta_signals.csv)\n")
            f.write(f"- **Avg 10-Second Return:** {avg_10s:.4f}%\n")
            f.write(f"- **Avg Move to End-of-File:** {avg_eof:.4f}%\n")
            f.write(f"- **Note:** Most files are short segments (<1 min). T+30m analysis requires stitching.\n\n")
            
            f.write("### Interpretation:\n")
            if abs(avg_eof) > 0.01:
                direction = "Positive" if avg_eof > 0 else "Negative"
                f.write(f"Immediate post-signal drift is **{direction}**.\n")
            else:
                 f.write("The signal shows no immediate directional bias (Noise/Calibration).\n")
                 
            f.write("\n### Detailed Log (Top 10)\n")
            # f.write(df_res.head(10).to_markdown())
            for i, r in df_res.head(10).iterrows():
                f.write(f"- {r['timestamp']} ({r['file']}): Prior Dur={r['available_duration']}, EOF Ret={r['ret_eof']:.4f}\n")
        else:
            f.write("No valid Price Delta signals backtested.\n")
            
        f.write("\n## 2. Gravity Score Analysis\n")
        if gravity_res:
             df_g = pd.DataFrame(gravity_res)
             # Save Raw Data
             csv_path_g = Path(OUTPUT_PATH).parent / "gravity_signals.csv"
             df_g.to_csv(csv_path_g, index=False)
             print(f"Saved raw Gravity data to {csv_path_g}")

             avg_range = df_g['price_range_pct'].mean() * 100
             f.write(f"- **High Gravity Days (Score > 8.0):** {len(df_g)}\n")
             f.write(f"- **Raw Data:** [gravity_signals.csv](./gravity_signals.csv)\n")
             f.write(f"- **Avg Intraday Price Range:** {avg_range:.2f}%\n")
             
             corr = df_g['score'].corr(df_g['price_range_pct'])
             f.write(f"- **Correlation (Gravity vs Volatility):** {corr:.4f}\n\n")
             
             f.write("### Interpretation:\n")
             if corr > 0.3:
                 f.write("High Gravity coincides with **High Volatility** (The Magnet is Fighting/Breaking).\n")
             elif corr < -0.3:
                 f.write("High Gravity coincides with **Low Volatility** (Pinning Successful).\n")
             else:
                 f.write("Gravity Score is independent of Volatility magnitude.\n")
                 
             f.write("\n### Top Gravity Events\n")
             for i, r in df_g.sort_values('score', ascending=False).head(10).iterrows():
                 f.write(f"- Score {r['score']:.2f}: Range={r['price_range_pct']*100:.2f}%\n")
        else:
            f.write("No High Gravity events analyzed.\n")

    print(f"Report saved to {OUTPUT_PATH}")

if __name__ == "__main__":
    rep = load_report()
    if rep:
        d_res = analyze_price_delta_efficacy(rep)
        g_res = analyze_gravity_efficacy(rep)
        write_report(d_res, g_res)
