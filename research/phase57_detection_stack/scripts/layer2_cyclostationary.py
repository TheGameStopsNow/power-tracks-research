#!/usr/bin/env python3
"""
Layer 2: Cyclostationarity Detector
===================================

Detects "Clock-Synced" signals (Periodic Modulation) in event intensity.

Method:
1. Discretize event times into fine bins (e.g., 1ms).
2. Compute Event Count series x(t).
3. Compute Power Spectral Density (PSD) via Welch's method.
4. Detect peaks > K * NoiseFloor (e.g. 5-sigma).
5. Map peaks to periods (e.g., 10Hz -> 100ms matches).
"""

import numpy as np
import pandas as pd
from scipy import signal
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))

from research.phase57_detection_stack.layer0_data_harness import TickLoader, RegimeConditioner

class MultiScaleScanner:
    def __init__(self, bin_sizes_ms: list = [1, 2, 5, 10, 20]):
        self.bin_sizes = bin_sizes_ms
        
    def _scan_single(self, timestamps: np.ndarray, bin_size_ms: int, threshold: float = 5.0):
        bin_size = bin_size_ms / 1000.0
        duration = timestamps[-1] - timestamps[0]
        t_rel = timestamps - timestamps[0]
        
        bins = np.arange(0, duration + bin_size, bin_size)
        counts, _ = np.histogram(t_rel, bins=bins)
        
        fs = 1.0 / bin_size
        freqs, psd = signal.welch(counts, fs, nperseg=min(len(counts), 4096))
        
        # Robust Noise Floor (Rolling Median) to handle 1/f noise
        window_len = max(5, int(len(psd) * 0.1))
        if window_len % 2 == 0: window_len += 1
        noise_floor = signal.medfilt(psd, kernel_size=window_len)
        
        # Avoid div by zero
        noise_floor[noise_floor == 0] = 1e-9
        
        z_scores = (psd - noise_floor) / noise_floor
        
        peak_indices, _ = signal.find_peaks(z_scores, height=threshold)
        
        results = []
        for idx in peak_indices:
            f = freqs[idx]
            if f < 0.1: continue # Ignore DC / drift
            
            results.append({
                'freq_hz': f,
                'power_ratio': z_scores[idx],
                'bin_size': bin_size_ms
            })

        return results

    def scan_all(self, timestamps: np.ndarray):
        all_peaks = []
        detected_bins = set()
        
        for b in self.bin_sizes:
            peaks = self._scan_single(timestamps, b)
            if peaks:
                detected_bins.add(b)
                all_peaks.extend(peaks)
                
        # Calculate Persistence using Frequency Bucketing
        # If we see ~10Hz in 5ms bin and 10ms bin, that's persistence.
        # Group by freq (tolerance 5%)
        
        from collections import defaultdict
        freq_groups = defaultdict(list)
        
        for p in all_peaks:
            # Round to nearest 0.5 Hz for grouping
            f_key = round(p['freq_hz'] * 2) / 2
            freq_groups[f_key].append(p)
            
        persistent_signals = []
        for f, group in freq_groups.items():
            if f < 0.1: continue # Explicitly exclude DC bucket after rounding
            
            unique_bins = set(g['bin_size'] for g in group)
            persistence_score = len(unique_bins) / len(self.bin_sizes)
            max_power = max(g['power_ratio'] for g in group)
            
            if persistence_score >= 0.4: # Present in at least 2 bins
                persistent_signals.append({
                    'freq_hz': f,
                    'period_sec': 1.0/f if f>0 else 0,
                    'persistence': persistence_score,
                    'max_power': max_power,
                    'bins': list(unique_bins)
                })
                
        return sorted(persistent_signals, key=lambda x: x['persistence'], reverse=True)

    def phase_locking_metrics(self, event_times_sec: np.ndarray, freq_hz: float, t_ref_sec: float) -> dict:
        """
        Computes Phase Locking Value (PLV) relative to a reference time t_ref.
        PLV = |mean(exp(j * 2*pi * f * (t - t_ref)))|
        Returns {plv, phase_var}.
        """
        if len(event_times_sec) < 50 or freq_hz <= 0:
            return {"plv": 0.0, "phase_var": 1.0}
            
        phi = 2.0 * np.pi * freq_hz * (event_times_sec - t_ref_sec)
        z = np.exp(1j * phi)
        plv = float(np.abs(np.mean(z)))
        return {"plv": plv, "phase_var": 1.0 - plv}

    def phase_var_abs_eventtrain(self, ts_ns: np.ndarray, freq_hz: float, seg_sec: int = 60, min_events: int = 50) -> dict:
        """
        Absolute phase variance relative to UTC midnight, computed across subwindows
        using the event-train Fourier coefficient (no binning).
        Returns dict with phase_var and mean phase stats.
        """
        if len(ts_ns) < min_events:
            return {"phase_var": 1.0, "phase_mean_rad": 0.0, "phase_mean_deg": 0.0}

        try:
            ts = pd.to_datetime(ts_ns, unit='ns', utc=True)
            midnight = ts[0].normalize()  # UTC midnight for that day
            # Absolute time in seconds from midnight
            t = (ts - midnight).total_seconds().to_numpy()
        except Exception as e:
            print(f"DEBUG: L2 Phase Error Init: {e}, ts_ns type: {type(ts_ns)}")
            return {"phase_var": 1.0, "phase_mean_rad": 0.0, "phase_mean_deg": 0.0}

        # Segment index inside the window (absolute anchor aligned to window start or midnight?)
        # For simplicity and robustness, we use t (secs from midnight).
        # We want segments of length seg_sec.
        # But we need them to be full windows?
        # Just binning 't' by seg_sec works.
        # seg = floor(t / seg_sec) would align to midnight.
        # But user implementation used floor((t - t.min()) / seg_sec).
        # Let's stick to user implementation as it isolates local drift.
        seg = np.floor((t - t.min()) / seg_sec).astype(int)
        
        phases = []
        weights = []

        w = 2.0 * np.pi * float(freq_hz)

        for s in np.unique(seg):
            tt = t[seg == s]
            if len(tt) < 10: # Min events per segment
                continue
            
            # Event train Fourier: A = sum(exp(-j * w * t))
            # Note: A is calculated using 'tt' which is Absolute Secs from Midnight.
            # So the phase is Absolute.
            A = np.sum(np.exp(-1j * w * tt))
            amp = np.abs(A)
            if amp < 1e-9:
                continue
                
            phases.append(np.angle(A))
            # Weight by amplitude (proxy for coherence/count)
            weights.append(amp)

        if len(phases) < 3:
            print(f"DEBUG: L2 Fail len(phases)={len(phases)}. Unique Segs: {len(np.unique(seg))}. Amp ex: {weights[:3] if len(weights)>0 else 'None'}")
            return {"phase_var": 1.0, "phase_mean_rad": 0.0, "phase_mean_deg": 0.0}

        phases = np.asarray(phases)
        weights = np.asarray(weights)
        
        # Mean Phasor
        # Z = sum(w * exp(j * phi)) / sum(w)
        Z = np.sum(weights * np.exp(1j * phases)) / np.sum(weights)
        R = np.abs(Z)
        mean_angle = np.angle(Z)
        
        print(f"DEBUG: L2 Success. F={freq_hz}, R={R}, Var={1-R}")
        
        return {
            "phase_var": float(1.0 - R),
            "phase_mean_rad": float(mean_angle),
            "phase_mean_deg": float(np.degrees(mean_angle))
        }

if __name__ == "__main__":
    # Test
    loader = TickLoader()
    test_date = "2024-05-14"
    symbol = "GME"
    
    print(f"Loading {symbol}...")
    df = loader.load_ticks(test_date, symbol)
    
    if df is not None:
        # Filter to High Volatility to see structure
        # Or take a 5-minute slice
        start_t = df['timestamp'].iloc[0]
        end_t = start_t + pd.Timedelta(minutes=5)
        
        sub = df[(df['timestamp'] >= start_t) & (df['timestamp'] < end_t)]
        
        timestamps = sub['timestamp'].astype(np.int64) / 1e9
        timestamps = timestamps.values
        
        scanner = SpectralScanner(bin_size_ms=10) # 10ms bins = 100Hz Nyquist
        print(f"Discretizing {len(timestamps)} events into 10ms bins...")
        
        counts = scanner.discretize_events(timestamps)
        
        print("Scanning Spectrum...")
        peaks = scanner.scan_spectrum(counts)
        
        print(f"Found {len(peaks)} significant spectral peaks:")
        for p in peaks[:10]:
            print(f"  F={p['freq_hz']:.2f}Hz (T={p['period_sec']*1000:.1f}ms) | Signal/Noise={p['power_ratio']:.1f}x")
            
        if not peaks:
            print("  No clock-like signals found.")
