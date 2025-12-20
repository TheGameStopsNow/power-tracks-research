#!/usr/bin/env python3
"""
Protocol Fuzzer (Genetic Algorithm)
===================================

Evolves frame extraction parameters to maximize the regularity/structure
of the extracted bitstream.

Parameters to optimize:
- Frame Length (bits)
- Offset (start bit index)
- Stride/Skip (decoding pattern)
- Sync Marker (if using periodic markers)
"""

import random
import numpy as np
from typing import List, Dict, Tuple
from joblib import Parallel, delayed
import json
from pathlib import Path
import copy

# Import local modules
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs, BASE_DIR
from core.extractors import extract_all_signals


class Gene:
    """Defines the parameter space for the genetic algorithm."""
    def __init__(self, 
                 frame_length: int, 
                 offset: int, 
                 bit_skip: int = 1,
                 sync_pattern_len: int = 0):
        self.frame_length = frame_length
        self.offset = offset
        self.bit_skip = bit_skip
        self.sync_pattern_len = sync_pattern_len

    @classmethod
    def random(cls, max_bits: int):
        return cls(
            frame_length=random.randint(64, 512),
            offset=random.randint(0, 1000),
            bit_skip=random.choice([1, 1, 1, 2, 4, 8]),  # Weighted towards 1
            sync_pattern_len=random.choice([0, 8, 16, 24, 32])
        )

    def mutate(self):
        r = random.random()
        if r < 0.3:
            self.frame_length += random.randint(-10, 10)
            self.frame_length = max(32, min(2048, self.frame_length))
        elif r < 0.6:
            self.offset += random.randint(-50, 50)
            self.offset = max(0, self.offset)
        elif r < 0.8:
            self.bit_skip = random.choice([1, 2, 4, 8])
        else:
            self.sync_pattern_len = random.choice([0, 8, 16, 24, 32])


def calculate_fitness(gene: Gene, bitstream: np.ndarray) -> float:
    """
    Calculate fitness score based on frame regularity and autocorrelation.
    """
    bits = bitstream[gene.offset::gene.bit_skip]
    
    if len(bits) < gene.frame_length * 10:
        return 0.0
    
    # 1. Reshape into frames
    n_frames = len(bits) // gene.frame_length
    frames = bits[:n_frames * gene.frame_length].reshape(n_frames, gene.frame_length)
    
    # 2. Calculate vertical regularity (consistency of bits across frames)
    # Mean of columns should differ from 0.5 if there's structure
    col_means = np.mean(frames, axis=0)
    structure_score = np.mean(np.abs(col_means - 0.5)) * 2  # 0 to 1 scale
    
    # 3. Calculate horizontal autocorrelation (periodicity)
    # We want rows to look somewhat similar to neighbors?
    # Or maybe we just want the `structure_score` to be high.
    
    # Let's add a penalty for trivial solutions (like extremely short frames)
    length_penalty = 1.0
    if gene.frame_length < 32:
        length_penalty = 0.5
        
    return float(structure_score * length_penalty)


def run_genetic_fuzzer(
    bitstream: List[int],
    population_size: int = 100,
    generations: int = 30,
    n_jobs: int = -1
):
    """
    Run the genetic algorithm.
    """
    bits_arr = np.array(bitstream, dtype=int)
    
    # Initialize population
    population = [Gene.random(len(bits_arr)) for _ in range(population_size)]
    
    # Seed with our "detected" hypotheses from Phase 4
    population[0] = Gene(frame_length=274, offset=0, bit_skip=1)
    population[1] = Gene(frame_length=64, offset=0, bit_skip=1)
    
    best_overall = None
    best_score = -1.0
    
    print(f"Starting Fuzzer: {len(bits_arr)} bits, {generations} generations")
    
    for gen in range(generations):
        # Evaluate fitness
        scores = Parallel(n_jobs=n_jobs)(
            delayed(calculate_fitness)(gene, bits_arr) for gene in population
        )
        
        # Sort
        paired = sorted(zip(population, scores), key=lambda x: x[1], reverse=True)
        population = [p for p, s in paired]
        scores = [s for p, s in paired]
        
        current_best_score = scores[0]
        current_best_gene = population[0]
        
        if current_best_score > best_score:
            best_score = current_best_score
            best_overall = copy.deepcopy(current_best_gene)
            print(f"  Gen {gen}: New best score = {best_score:.4f} (Len: {best_overall.frame_length}, Off: {best_overall.offset})")
        
        # Selection & Reproduction
        survivors = population[:population_size // 5]  # Top 20%
        
        new_population = [copy.deepcopy(p) for p in survivors]
        
        while len(new_population) < population_size:
            parent = random.choice(survivors)
            child = copy.deepcopy(parent)
            child.mutate()
            new_population.append(child)
            
        population = new_population
        
    return best_overall, best_score


if __name__ == "__main__":
    print("=" * 70)
    print("EDGX PROTOCOL FUZZER (Genetic Algorithm)")
    print("=" * 70)
    
    # Load Data
    sample_dirs = get_sample_dirs()
    if not sample_dirs:
        print("No samples found.")
        sys.exit(1)
        
    test_dir = sample_dirs[-1]
    print(f"Loading data from: {test_dir.name}")
    
    df = load_edgx_data(test_dir).head(50000)
    signals = extract_all_signals(df)
    
    # Target the most predictive signal
    target_signal = 'price_lsb_1c'
    bits = signals[target_signal]
    
    print(f"Fuzzing signal: {target_signal} ({len(bits)} bits)")
    
    best_gene, score = run_genetic_fuzzer(bits, generations=20, population_size=200)
    
    print("\n" + "=" * 70)
    print("OPTIMIZATION RESULTS")
    print("=" * 70)
    print(f"Max Regularity Score: {score:.4f}")
    print(f"Best Frame Length:    {best_gene.frame_length}")
    print(f"Best Offset:          {best_gene.offset}")
    print(f"Best Bit Skip:        {best_gene.bit_skip}")
    
    # Save results
    output_path = BASE_DIR / "research" / "edgx_deep_decode" / "results" / "fuzzer_results.json"
    with open(output_path, 'w') as f:
        json.dump({
            'signal': target_signal,
            'max_score': score,
            'frame_length': best_gene.frame_length,
            'offset': best_gene.offset,
            'bit_skip': best_gene.bit_skip
        }, f, indent=2)
    print(f"Results saved to {output_path}")
