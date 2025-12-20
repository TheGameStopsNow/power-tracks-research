import json
from collections import Counter

from pathlib import Path

PHASE29_DIR = Path(__file__).resolve().parent.parent
REPORT_PATH = PHASE29_DIR / "output" / "SYSTEM_CARTOGRAPHY_REPORT.json"

def analyze():
    print("Loading report...")
    with open(REPORT_PATH, 'r') as f:
        data = json.load(f)
    
    total_files = len(data)
    print(f"Total Files Analyzed: {total_files}")
    
    matches_741 = []
    gravity_scores = []
    grammar_counter = Counter()
    
    global_chronos = {}
    intraday_corrs = {'1s_lag_1': [], '1s_lag_4': [], '1s_lag_7': []}
    fractal_total = 0
    fractal_breakdown = []
    matches_order_count = []
    matches_price_delta = []
    fractal_spectra = [] # List of lists
    
    for filename, result in data.items():
        if filename == 'GLOBAL_CHRONOS_ANALYSIS':
            global_chronos = result
            continue
        if filename == 'GLOBAL_CHRONOS_ERROR':
            # print(f"Global Chronos Error: {result}")
            continue
            
        # 1. Check 7-4-1
        # Expecting result['741_hunt'] to be a dict. Check 'sequence_741_matches' list
        hunt = result.get('741_hunt', {})
        if hunt and len(hunt.get('sequence_741_matches', [])) > 0:
             matches_741.append((filename, hunt))
        
        # 1b. Check 1-4-7 (Reverse)
        hunt_rev = result.get('147_hunt', {})
        if hunt_rev and len(hunt_rev.get('sequence_147_matches', [])) > 0:
             matches_741.append((filename + " (REVERSE)", hunt_rev))


        # 1e. Order Count Matches (7-4-1)
        oc_hunt = result.get('order_count_hunt', {})
        if oc_hunt and len(oc_hunt.get('order_count_741_matches', [])) > 0:
            count = len(oc_hunt.get('order_count_741_matches', []))
            matches_order_count.append((filename, count))
            
        # 1f. Price Delta Matches (0.07-0.04-0.01)
        pd_hunt = result.get('price_delta_hunt', {})
        if pd_hunt and len(pd_hunt.get('price_delta_741_matches', [])) > 0:
            count = len(pd_hunt.get('price_delta_741_matches', []))
            matches_price_delta.append((filename, count))

        # 2. Gravity Scores
        # Expecting result['gravity'] to be a dict
        g_data = result.get('gravity', {})
        if isinstance(g_data, dict):
            g = g_data.get('gravity_score', 0.0)
        else:
            g = 0.0
            
        if g > 0:
            gravity_scores.append((filename, g))
            
        # 3. Common Grammar
        seqs = result.get('grammar_seqs', [])
        for seq_entry in seqs:
            # seq_entry is [[op1, op2, op3], count]
            try:
                ngram = tuple(seq_entry[0])
                count = seq_entry[1]
                grammar_counter[ngram] += count
            except:
                pass

    print("\n--- 7-4-1 / 1-4-7 FINDINGS ---")
    if matches_741:
        print(f"FOUND {len(matches_741)} MATCHES!")
        for m in matches_741:
            print(f"  {m[0]}: {m[1]}")
    else:
        print("No direct 7-4-1 or 1-4-7 matches found.")
            
    print("\n--- HIGH-FIDELITY PATTERN SEARCH ---")
    print(f"Order Count (7-4-1) Matches: {sum(x[1] for x in matches_order_count)} in {len(matches_order_count)} files")
    if matches_order_count:
        matches_order_count.sort(key=lambda x: x[1], reverse=True)
        print("  Top Files:", matches_order_count[:5])
        
    print(f"Price Delta (0.07-0.04-0.01) Matches: {sum(x[1] for x in matches_price_delta)} in {len(matches_price_delta)} files")
    if matches_price_delta:
        matches_price_delta.sort(key=lambda x: x[1], reverse=True)
        print("  Top Files:", matches_price_delta[:5])

    print("\n--- TOP GRAVITY SCORES (Potential Pins) ---")
    # Sort by score desc
    gravity_scores.sort(key=lambda x: x[1], reverse=True)
    for name, score in gravity_scores[:10]:
        print(f"  {name}: {score:.4f}")

    print("\n--- TOP 5 COMMON GRAMMAR SEQUENCES ---")
    for seq, count in grammar_counter.most_common(5):
        print(f"  {seq}: {count}")

if __name__ == "__main__":
    analyze()
