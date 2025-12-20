
from datetime import date

# Key FRACTAL CLUSTER Dates (from Phase 29d Findings)
dates = [
    date(2021, 1, 26),  # The Sneeze (Buildup)
    date(2021, 2, 25),  # The Resurgence
    date(2021, 3, 10),  # The Flash Crash
    date(2021, 6, 9),   # June Run (Adding from general knowledge/data)
    date(2022, 3, 25)   # The 2022 Run
]

def analyze_cycle():
    print("--- MASTER CYCLE ANALYSIS ---")
    print(f"Analyzing Spacing between {len(dates)} High-Fractality Clusters:\n")
    
    for i in range(len(dates)-1):
        d1 = dates[i]
        d2 = dates[i+1]
        delta = (d2 - d1).days
        print(f"{d1} -> {d2}: {delta} days")
        
        # Check harmonics
        if delta == 147:
            print("  *** MATCH: 147 DAYS! ***")
        elif delta == 741:
             print("  *** MATCH: 741 DAYS! ***")
        elif delta % 74 == 1: # 7-4-1
             print("  * Potential 7-4-1 Harmonic")

    # Long-Range Checks
    print("\n--- LONG RANGE ARCS ---")
    start = dates[0] # Jan 26 2021
    end = dates[-1]  # Mar 25 2022
    total = (end - start).days
    print(f"Total Range ({start} -> {end}): {total} days")
    
    if total == 423: # 147 * 3? No.
        print(f"  Note: 423 days.")

if __name__ == "__main__":
    analyze_cycle()
