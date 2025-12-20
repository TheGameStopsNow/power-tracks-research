
import pandas as pd
from pathlib import Path

# Configuration
SIGNAL_LOG = Path("research/phase30_interconnectedness/signal_log.csv")
OUTPUT_MD = Path("research/phase30_interconnectedness/latency_stats.md")

WINDOW_MS = 1000  # Look for reactions within 1000ms (1 second)

def main():
    if not SIGNAL_LOG.exists():
        print(f"Signal log not found at {SIGNAL_LOG}")
        return

    df = pd.read_csv(SIGNAL_LOG)
    
    # Ensure sorted by time
    df.sort_values("timestamp_us", inplace=True)
    
    pairs = []
    
    # Iterate through events
    groups = df.groupby("date")
    
    for date, group in groups:
        print(f"Processing interactions for {date} ({len(group)} signals)...")
        group = group.reset_index(drop=True)
        
        for i in range(len(group)):
            leader = group.iloc[i]
            
            for j in range(i + 1, len(group)):
                follower = group.iloc[j]
                
                delta_us = follower['timestamp_us'] - leader['timestamp_us']
                delta_ms = delta_us / 1000
                
                if delta_us > (WINDOW_MS * 1000):
                    break
                    
                if leader['symbol'] == follower['symbol']:
                    continue
                    
                pairs.append({
                    "date": date,
                    "leader": leader['symbol'],
                    "follower": follower['symbol'],
                    "delta_ms": delta_ms,
                    "leader_type": leader['type'],
                    "follower_type": follower['type']
                })

    if not pairs:
        print("No interactions found within window.")
        return
        
    pairs_df = pd.DataFrame(pairs)
    
    print("\n--- Latency Analysis ---")
    print(pairs_df.describe())
    
    leader_counts = pairs_df['leader'].value_counts()
    print("\nTop Leaders:")
    print(leader_counts)
    
    pivot = pairs_df.pivot_table(index='leader', columns='follower', values='delta_ms', aggfunc='count', fill_value=0)
    
    with open(OUTPUT_MD, "w") as f:
        f.write("# Latency Analysis Report\n\n")
        f.write(f"Window: {WINDOW_MS}ms\n\n")
        f.write("## Top Leaders\n")
        f.write("```\n")
        f.write(leader_counts.to_string())
        f.write("\n```\n\n")
        
        f.write("## Interaction Matrix (Count)\n")
        f.write("```\n")
        f.write(pivot.to_string())
        f.write("\n```\n\n")
        
        f.write("## Detail Stats (Mean Latency ms)\n")
        avg_latency = pairs_df.pivot_table(index='leader', columns='follower', values='delta_ms', aggfunc='mean').round(2)
        f.write("```\n")
        f.write(avg_latency.to_string())
        f.write("\n```\n")

    print(f"Saved stats to {OUTPUT_MD}")

if __name__ == "__main__":
    main()
