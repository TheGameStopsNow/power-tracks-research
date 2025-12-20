#!/usr/bin/env python3
"""
Grammar Decoder & The 7-4-1 Hunt
================================
Phase 29: System Cartography

Objectives:
1. Map the "Language" of the market (Opcode Vocabulary, Transition Probabilities).
2. Hunt for the "7-4-1" Connection (Sequences, Time Intervals).
"""

import sys
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import numpy as np
import pandas as pd
from collections import Counter, defaultdict

# Add parent directory to path to import from edgx_deep_decode
# Assuming structure: research/phase29_system_cartography/grammar_decoder.py
# We need to reach research/edgx_deep_decode
RESEARCH_DIR = Path(__file__).resolve().parent.parent
EDGX_DIR = RESEARCH_DIR / "edgx_deep_decode"
sys.path.insert(0, str(EDGX_DIR))

try:
    from loader import load_edgx_data, get_sample_dirs
    from extractors import extract_all_signals
    from adversarial_decoding import bits_to_bytes
except ImportError:
    print(f"Warning: Could not import modules from {EDGX_DIR}. Using mocks.")
    # Mock functions to prevent ImportErrors crashing the script
    def bits_to_bytes(bits): return []
    def load_edgx_data(*args, **kwargs): return pd.DataFrame()
    def get_sample_dirs(): return []
    def extract_all_signals(*args, **kwargs): return pd.DataFrame()

class GrammarDecoder:
    def __init__(self, data: pd.DataFrame):
        self.df = data
        
        # Calculate LSBs directly to avoid dependency on 'volume' via extract_all_signals
        # LSB = Last digit of price scaled to cents (int(price * 100) & 1) or just last digit
        # EDGX standard is usually 1c precision LSB.
        # Ensure we use the right column
        col = 'price' if 'price' in self.df.columns else 'close'
        prices = self.df[col].values
        
        # Check if prices are float or already int scaled? Assume float.
        # int(p * 100) might have float point errors. round(p, 2) first.
        self.bits = [int(round(p, 2) * 100) & 1 for p in prices]
        
        self.byte_stream = bits_to_bytes(self.bits)
        
        # Timestamp mapping
        if 'timestamp' in self.df.columns:
            ts = self.df['timestamp'].values
        elif 'timestamp_us' in self.df.columns:
            ts = self.df['timestamp_us'].values
        else:
            ts = self.df.index.values
            
        # We need 1 timestamp for every 8 bits (1 byte)
        self.ts_stream = ts[::8][:len(self.byte_stream)]

    def build_transition_matrix(self, top_n: int = 20) -> pd.DataFrame:
        """Standard Markov Transition Matrix"""
        counts = Counter(self.byte_stream)
        top_tokens = [k for k, v in counts.most_common(top_n)]
        
        transitions = defaultdict(Counter)
        for i in range(len(self.byte_stream) - 1):
            curr = self.byte_stream[i]
            next_ = self.byte_stream[i+1]
            if curr in top_tokens and next_ in top_tokens:
                transitions[curr][next_] += 1
                
        matrix = pd.DataFrame(0.0, index=top_tokens, columns=top_tokens)
        for curr in top_tokens:
            total = sum(transitions[curr].values())
            if total > 0:
                for next_ in top_tokens:
                    matrix.loc[curr, next_] = transitions[curr][next_] / total
        return matrix

    def find_sequences(self, length: int = 3, top_n: int = 10) -> List[Tuple]:
        """Finds frequent N-grams"""
        seq_counts = Counter()
        for i in range(len(self.byte_stream) - length):
            seq = tuple(self.byte_stream[i : i+length])
            # Filter noise
            if set(seq).issubset({0, 255}): 
                continue
            seq_counts[seq] += 1
        return seq_counts.most_common(top_n)

    def hunt_741(self) -> Dict:
        """
        The Search for the 7-4-1 Connection.
        1. Opcode Sequence: 0x07 -> 0x04 -> 0x01
        2. Opcode Counts: 7 of X, 4 of Y, 1 of Z?
        3. Time Intervals? (Not implemented in this static byte check)
        """
        results = {}
        
        # 1. Direct Opcode Sequence Search (7, 4, 1)
        # 0x07 = 7, 0x04 = 4, 0x01 = 1
        target_seq = (7, 4, 1)
        seq_matches = []
        
        for i in range(len(self.byte_stream) - 3):
            window = tuple(self.byte_stream[i : i+3])
            if window == target_seq:
                seq_matches.append({
                    'index': i,
                    'timestamp': self.ts_stream[i] if i < len(self.ts_stream) else "N/A"
                })
        
        results['sequence_741_matches'] = seq_matches
        
        # 2. Variable Spacing Search?
        # e.g., 0x07 ... (N bytes) ... 0x04 ... (M bytes) ... 0x01
        # This is expensive, skipping for V1.
        
        # 3. Check for Opcodes 0x07, 0x04, 0x01 individually
        counts = Counter(self.byte_stream)
        results['opcode_counts'] = {
            '0x07': counts.get(7, 0),
            '0x04': counts.get(4, 0),
            '0x01': counts.get(1, 0)
        }
        
        return results

    def hunt_reverse_sequence(self) -> Dict:
        """
        The Search for the 1-4-7 Connection (Reverse).
        Opcode Sequence: 0x01 -> 0x04 -> 0x07
        """
        results = {}
        target_seq = (1, 4, 7)
        seq_matches = []
        
        for i in range(len(self.byte_stream) - 3):
            window = tuple(self.byte_stream[i : i+3])
            if window == target_seq:
                seq_matches.append({
                    'index': i,
                    'timestamp': self.ts_stream[i] if i < len(self.ts_stream) else "N/A"
                })
        
        results['sequence_147_matches'] = seq_matches
        return results

    def hunt_order_counts(self, df: pd.DataFrame) -> Dict:
        """
        Hunt for the [7, 4, 1] Order Count sequence in consecutive seconds.
        """
        matches = []
        if 'timestamp' not in df.columns:
            return {}
            
        try:
            # Resample to 1s counts
            temp = df[['timestamp']].copy()
            temp['timestamp'] = pd.to_datetime(temp['timestamp'])
            counts = temp.set_index('timestamp').resample('1s').size()
            
            # Convert to list for scanning
            seq = counts.values
            target = [7, 4, 1]
            
            # Simple sliding window
            for i in range(len(seq) - 2):
                if seq[i] == 7 and seq[i+1] == 4 and seq[i+2] == 1:
                    matches.append(str(counts.index[i]))
                    
        except Exception:
            pass
            
        return {'order_count_741_matches': matches}

    def hunt_price_deltas(self, df: pd.DataFrame) -> Dict:
        """
        Hunt for the [0.07, 0.04, 0.01] Price Delta sequence.
        """
        matches = []
        col = 'close' if 'close' in df.columns else 'price'
        if col not in df.columns:
            return {}
            
        try:
            # Calculate absolute price deltas
            deltas = df[col].diff().abs().round(2) # Round to cent
            
            # Convert to list
            seq = deltas.values
            
            # Scan
            for i in range(len(seq) - 2):
                if seq[i] == 0.07 and seq[i+1] == 0.04 and seq[i+2] == 0.01:
                    # Get timestamp if available
                    ts = df.iloc[i]['timestamp'] if 'timestamp' in df.columns else i
                    matches.append(str(ts))
                    
        except Exception:
            pass
            
        return {'price_delta_741_matches': matches}

def run_decoder_test():
    print("Testing Grammar Decoder...")
    sample_dirs = get_sample_dirs()
    if not sample_dirs:
        print("No data found.")
        return

    # Just pick the last one
    target_dir = sample_dirs[-1]
    print(f"Loading {target_dir.name}...")
    df = load_edgx_data(target_dir, symbol='GME')
    
    decoder = GrammarDecoder(df)
    
    print("\n[Grammar Analysis]")
    seqs = decoder.find_sequences(length=3)
    for seq, count in seqs:
        hex_seq = " -> ".join([f"0x{b:02X}" for b in seq])
        print(f"  {hex_seq}: {count}")
        
    print("\n[The 7-4-1 Hunt]")
    hunt_results = decoder.hunt_741()
    print(f"  Sequence (0x07 -> 0x04 -> 0x01) Matches: {len(hunt_results['sequence_741_matches'])}")
    print(f"  Opcode Counts: {hunt_results['opcode_counts']}")

if __name__ == "__main__":
    run_decoder_test()
