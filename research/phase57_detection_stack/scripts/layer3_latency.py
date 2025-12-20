#!/usr/bin/env python3
"""
Layer 3: Cross-Venue Latency
============================

Detects "State-Switching" in routing delays.

Method:
1. Select two major venues (e.g. NYSE vs EDGX).
2. For each trade in Venue A, find nearest trade in Venue B (within window, e.g. +/- 10ms).
3. Compute lags: Delta = t_B - t_A.
4. Fit Gaussian Mixture Model (GMM) to lag distribution.
5. If >1 component and weights/means shift over time -> Anomaly.
"""

import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))

from research.phase57_detection_stack.layer0_data_harness import TickLoader

class VenueLagTracker:
    def __init__(self, venue_a: int, venue_b: int, max_lag_ms: float = 50.0, exclude_otc: bool = False):
        self.va = venue_a
        self.vb = venue_b
        self.max_lag = max_lag_ms / 1000.0 # seconds
        self.exclude_otc = exclude_otc

        
    def compute_lags(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        """
        Compute lag distribution between Venue A and Venue B.
        Returns (lags_seconds, lag_times_seconds).
        lag_times_seconds corresponds to the timestamp of the Venue A trade.
        """
        # Exclude OTC (Codes 'OTC', '4') if detected, unless specifically requested
        # Phase 57b: Strict Lit Only
        # We assume va/vb are already valid Lit IDs.
        if self.exclude_otc:
            # Common OTC venue codes are 'OTC' (string) or '4' (integer, sometimes represented as string)
            # We need to ensure the 'venue' column is string type for consistent comparison
            df_filtered = df[~df['venue'].astype(str).isin(['OTC', '4'])].copy()
        else:
            df_filtered = df.copy()

        # Convert to string to ensure matching
        df_filtered['venue'] = df_filtered['venue'].astype(str)
        va_str = str(self.va)
        vb_str = str(self.vb)
        
        df_a = df_filtered[df_filtered['venue'] == va_str].sort_values('timestamp')
        df_b = df_filtered[df_filtered['venue'] == vb_str].sort_values('timestamp')
        
        # print(f"DEBUG: filtered A={len(df_a)}, B={len(df_b)} from {len(df)} total")
        
        if df_a.empty or df_b.empty:
            return np.array([]), np.array([])
            
        t_a = df_a['timestamp'].values.astype(np.int64) / 1e9
        t_b = df_b['timestamp'].values.astype(np.int64) / 1e9
        
        # For every A, find closest B
        # indices in b where a would insert
        idx_right = np.searchsorted(t_b, t_a)
        
        lags = []
        lag_times = []
        
        for i, idx in enumerate(idx_right):
            # Candidates are t_b[idx] and t_b[idx-1]
            time_a = t_a[i]
            candidates = []
            
            if idx < len(t_b):
                candidates.append(t_b[idx])
            if idx > 0:
                candidates.append(t_b[idx-1])
                
            if not candidates: continue
            
            # Find closest
            diffs = [c - time_a for c in candidates]
            abs_diffs = [abs(d) for d in diffs]
            min_idx = np.argmin(abs_diffs)
            best_lag = diffs[min_idx]
            
            if abs(best_lag) <= self.max_lag:
                lags.append(best_lag)
                lag_times.append(time_a) # Time of the A-side event
                
        return np.array(lags), np.array(lag_times)

    def analyze_distribution(self, lags: np.ndarray):
        """
        Fit GMM to discrete component lags.
        """
        if len(lags) < 100:
            return None
            
        X = lags.reshape(-1, 1)
        
        # Try 1 vs 2 components
        bic_1 = GaussianMixture(n_components=1).fit(X).bic(X)
        
        gmm_2 = GaussianMixture(n_components=2, random_state=42)
        gmm_2.fit(X)
        bic_2 = gmm_2.bic(X)
        
        best_gmm = gmm_2 if bic_2 < bic_1 - 10 else None # Prefer 2 only if significantly better
        
        if best_gmm:
            means = best_gmm.means_.flatten()
            weights = best_gmm.weights_.flatten()
            covars = best_gmm.covariances_.flatten()
            # Sort indices by MEAN ascending to keep "Lag Modes" stable
            order = np.argsort(means)
            components = [{'mean': float(means[i]), 'weight': float(weights[i]), 'var': float(covars[i])} for i in order]
        else:
            components = []

        return {
                'mean_lag': np.mean(lags),
                'std_lag': np.std(lags),
                'bic_1': bic_1,
                'bic_2': bic_2,
                'multimodal': bic_2 < bic_1 - 10,
                'components': components
            }

    def l3_temporal_coherence(self, lags: np.ndarray, lag_times: np.ndarray, window_start: float, 
                             subwindow_sec: float = 60.0, n_sub: int = 5, 
                             bic_delta: float = 10.0, n_boot: int = 500):
        """
        Bootstrap Test for Temporal Coherence of Multimodality.
        
        Method:
        1. Fit Global GMM on entire window.
        2. Compute responsibility-weighted mean of weights per sub-window.
        3. Switching Metric S = mean(|diff(weights)|).
        4. Bootstrap Null: Shuffle lag labels, recompute S_null.
        5. p-value = P(S_null >= S_obs).
        
        Returns dict with switching stats.
        """
        out = {
            "multimodal": False,
            "valid_switch": False,
            "sep_ms": 0.0,
            "min_weight": 0.0,
            "switching_score": 0.0,
            "switching_p": 1.0,
            "w_series": [],
            "components": []
        }

        if len(lags) < 200:
            return out  # insufficient power

        X = lags.reshape(-1, 1)

        # 1. Global Fit
        g1 = GaussianMixture(n_components=1, random_state=42).fit(X)
        g2 = GaussianMixture(n_components=2, random_state=42).fit(X)

        bic1 = g1.bic(X)
        bic2 = g2.bic(X)
        
        if (bic1 - bic2) < bic_delta:
            return out # Not multimodal enough

        # Sort components by MEAN ascending to prevent label flipping
        weights = g2.weights_.flatten()
        means = g2.means_.flatten()
        order = np.argsort(means) # Ascending
        
        means = means[order]
        weights = weights[order]

        out["multimodal"] = True
        out["components"] = [{"mean": float(means[i]), "weight": float(weights[i])} for i in range(2)]

        sep_ms = float(abs(means[1] - means[0]) * 1000.0)
        min_w = float(min(weights))

        out["sep_ms"] = sep_ms
        out["min_weight"] = min_w
        
        # Valid Gating (2ms sep, 10% weight)
        if sep_ms < 2.0 or min_w < 0.10:
            return out # Not a valid structural anomaly to check for switching
            
        out["valid_switch"] = True

        # 2. Compute Subwindow Weights via Responsibilities
        # Responsibilities with stable ordering (Global Fit)
        resp = g2.predict_proba(X)[:, order]  # (N,2)
        # pick slower mode = higher mean (index 1 after sorting)
        slow_idx = 1
        
        w_series = []
        n_series = []
        
        # Vectorized binning
        # We need to handle the case where lag_times might not be monotonic if multiple venues mixed?
        # But lag_times comes from tracker which sorts.
        
        sub_id = np.floor((lag_times - window_start) / subwindow_sec).astype(int)
        
        for k in range(n_sub):
            mask = (sub_id == k)
            n_k = mask.sum()
            if n_k < 10: # Minimum to estimate weight
                w_series.append(np.nan)
                n_series.append(0)
            else:
                # Mean responsibility of being in Slow Mode
                # This is "soft count" / total
                w_val = float(resp[mask, slow_idx].mean())
                w_series.append(w_val)
                n_series.append(int(n_k))
                
        out["w_series"] = w_series
        # Store n_by_seg for debugging/validation
        out["n_by_seg"] = n_series

        # Filter for valid segments
        valid_mask = np.isfinite(w_series)
        ws = np.array(w_series)[valid_mask]
        ns = np.array(n_series)[valid_mask]
        
        if len(ws) < 3:
            # Not enough subwindows
            out["switching_score"] = 0.0
            out["switching_p"] = 1.0
            return out

        # 3. Switching Metric (Total Variation)
        S_obs = float(np.sum(np.abs(np.diff(ws))))
        out["switching_score"] = S_obs

        # 4. Binomial Null (Static Mixture)
        # User's Logic: Simulate K_t ~ Binomial(n_t, p_global)
        # p_global estimated from weighted average of segment weights or global count
        
        # Global p estimate (weighted by N)
        p_global = np.sum(ws * ns) / np.sum(ns)
        # Clip for safety
        p_global = np.clip(p_global, 1e-4, 1 - 1e-4)
        
        rng = np.random.default_rng(42)
        S_boot = []
        
        for _ in range(n_boot):
            # Simulate weights for each segment under null
            # w_sim = Binomial(n, p) / n
            w_sim = rng.binomial(ns, p_global) / ns
            S_sim = np.sum(np.abs(np.diff(w_sim)))
            S_boot.append(S_sim)

        if len(S_boot) > 0:
            S_boot = np.array(S_boot)
            # p-value: P(S_null >= S_obs)
            p_val = (np.sum(S_boot >= S_obs) + 1) / (len(S_boot) + 1)
            out["switching_p"] = float(p_val)
        else:
            out["switching_p"] = 1.0

        return out



if __name__ == "__main__":
    loader = TickLoader()
    test_date = "2024-05-14"
    symbol = "GME"
    
    print(f"Loading {symbol}...")
    df = loader.load_ticks(test_date, symbol)
    
    if df is not None:
        # Find top 2 venues
        v_counts = df['venue'].value_counts()
        print(f"Top Venues:\n{v_counts.head()}")
        
        if len(v_counts) >= 2:
            v1 = v_counts.index[0]
            v2 = v_counts.index[1]
            try:
                # Ensure they are ints if possible, usually they are
                v1 = int(v1)
                v2 = int(v2)
            except:
                pass
                
            print(f"Tracking Lags between V{v1} and V{v2}...")
            tracker = VenueLagTracker(v1, v2)
            
            # Use slice from middle for better mix
            start_idx = len(df) // 2
            sub = df.iloc[start_idx : start_idx + 10000].copy()
            lags, lag_times = tracker.compute_lags(sub)

            
            print(f"Computed {len(lags)} lags.")
            if len(lags) > 0:
                stats = tracker.analyze_distribution(lags)
                if stats:
                    print("Analysis:")
                    print(f"  Mean Lag: {stats['mean_lag']*1000:.3f} ms")
                    print(f"  Multimodal: {stats['multimodal']}")
                    if stats['multimodal']:
                        for i, c in enumerate(stats['components']):
                            print(f"    Mode {i}: {c['mean']*1000:.3f} ms (Weight: {c['weight']:.2f})")
                            
                        # Test Coherence
                        print("Testing Coherence...")
                        t_start_sec = sub['timestamp'].min().value / 1e9
                        coh = tracker.l3_temporal_coherence(lags, lag_times, t_start_sec)
                        print(f"  Valid Switch: {coh['valid_switch']}")
                        print(f"  Switching Score: {coh['switching_score']:.5f}")
                        print(f"  p-value: {coh['switching_p']:.4f}")
