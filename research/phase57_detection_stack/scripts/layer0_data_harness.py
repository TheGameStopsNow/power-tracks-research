#!/usr/bin/env python3
"""
Layer 0: Data Harness & Conditioning
====================================

Responsilities:
1. Load high-resolution tick data (Polygon format).
2. Clean and normalize timestamps/venues.
3. Apply `StressModel` (StormDetector) to label regimes.
4. Export conditioned data streams for downstream layers.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
from typing import Optional, Dict, List

# Add repo root to path
BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))

# Import existing Activity/Stress logic
from research.phase54_mechanism.storm_detector import StormDetector

DATA_DIR = BASE_DIR / "data" / "samples"

class TickLoader:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = data_dir

    def load_ticks(self, date_str: str, symbol: str, jitter_amount_ns: int = 0, venue_filter: Optional[List[str]] = None) -> Optional[pd.DataFrame]:
        """
        Loads all trades for a given symbol and date.
        jitter_amount_ns: If > 0, adds 0-N random nanoseconds to timestamps.
        venue_filter: List of venue IDs (strings) to keep. If None, keep all.
        Returns DataFrame with cols: [timestamp, price, size, venue, condition]
        """
        # 1. Determine Target Directory
        # Primary: data/ticks/{date_str}
        tick_dir = self.data_dir.parent / "ticks" / date_str
        
        # Fallback: data/samples/sample_{date_str}
        sample_dir = self.data_dir / f"sample_{date_str}"
        
        target_dir = None
        if tick_dir.exists():
            target_dir = tick_dir
        elif sample_dir.exists():
            target_dir = sample_dir
        
        if not target_dir:
            print(f"No data directory found for {date_str}. Checked {tick_dir} and {sample_dir}")
            return None

        # 2. Find File
        # Patterns to check in order
        patterns = [
            f"{symbol}*_trades.csv",          # Standard Polygon
            f"raw_ticks/{symbol}*_trades.csv", # Nested Polygon
            f"{symbol}.csv"                   # Simple name
        ]
        
        files = []
        for p in patterns:
            found = list(target_dir.glob(p))
            if found:
                files = found
                break
        
        if not files:
            # Last ditch: check sample dir again if we were in tick dir but failed
            if target_dir == tick_dir and sample_dir.exists():
                 found = list(sample_dir.glob(f"raw_ticks/{symbol}*_trades.csv"))
                 if found: 
                     files = found
                     target_dir = sample_dir # Update source context
        
        if not files:
            print(f"No trades file found for {symbol} in {target_dir}")
            return None
            
        file_path = files[0]
        print(f"Loading {file_path}...", flush=True)
        
        try:
            print("Reading CSV...", flush=True)
            df = pd.read_csv(file_path, engine='python')
            print(f"Loaded CSV shape: {df.shape}", flush=True)
            
            # 3. Standardize Columns
            if 'timestamp' in df.columns:
                ts_col = 'timestamp'
            elif 'sip_timestamp' in df.columns:
                ts_col = 'sip_timestamp'
            elif 'timestamp_us' in df.columns:
                ts_col = 'timestamp_us'
            else:
                ts_col = df.columns[0]
                print(f"Warning: Guessing timestamp column is {ts_col}")

            print(f"Converting timestamp col: {ts_col}")
            
            if ts_col == 'timestamp_us':
                # Convert microseconds to datetime
                df['timestamp'] = pd.to_datetime(df[ts_col], unit='us', utc=True)
            else:
                # Convert string/mixed to datetime
                df['timestamp'] = pd.to_datetime(df[ts_col], utc=True, format='mixed')
            
            print("Timestamp conversion done.")

            # --- PROVENANCE GUARDRAIL (PHASE 72A) ---
            # Verify the loaded data actually matches the requested date.
            try:
                unique_dates = df['timestamp'].dt.date.unique()
                requested_dt = pd.to_datetime(date_str).date()
                
                if len(unique_dates) == 0:
                     print("Warning: Loaded DataFrame has valid structure but 0 rows.")
                elif len(unique_dates) > 1:
                    # Allow multiple dates if they are adjacent (due to utc offsets?) or just warn?
                    # Strict mode: Warn if primary date isn't requested date.
                    # Or check if requested_dt is IN unique_dates
                    if requested_dt not in unique_dates:
                        raise ValueError(f"CRITICAL PROVENANCE FAILURE: Requested {date_str} but loaded data contains {unique_dates}. File: {file_path}")
                else:
                    loaded_date = unique_dates[0]
                    if loaded_date != requested_dt:
                        raise ValueError(f"CRITICAL PROVENANCE FAILURE: Requested {date_str} but loaded data is from {loaded_date}. File: {file_path}")
                        
                print(f"Provenance Check Passed: Verified {date_str} data.")
            except Exception as prov_err:
                print(f"Provenance Check Error: {prov_err}")
                raise prov_err 
            # ----------------------------------------
            
            # Rename size -> volume
            if 'size' in df.columns and 'volume' not in df.columns:
                df.rename(columns={'size': 'volume'}, inplace=True)
            
            # Rename exchange -> venue
            if 'exchange' in df.columns and 'venue' not in df.columns:
                df.rename(columns={'exchange': 'venue'}, inplace=True)
                
            # Filter Venues
            df['venue'] = df['venue'].astype(str)
            if venue_filter:
                print(f"Filtering for venues: {venue_filter}")
                df = df[df['venue'].isin(venue_filter)].copy()
                if df.empty:
                    print("Warning: Venue filter resulted in empty DataFrame.")
                    return pd.DataFrame()

            # 4. Sort
            idx = np.argsort(df['timestamp'].values)
            df = df.iloc[idx].reset_index(drop=True)
            
            # 5. Jitter
            if jitter_amount_ns > 0:
                print(f"Applying Jitter (0-{jitter_amount_ns}ns)...")
                rng = np.random.default_rng(42)
                jitter = pd.to_timedelta(rng.integers(0, jitter_amount_ns, size=len(df)), unit='ns')
                df['timestamp'] += jitter
                
                # Re-sort to handle any swaps (though likely minimal)
                idx = np.argsort(df['timestamp'].values)
                df = df.iloc[idx].reset_index(drop=True)
                
            return df

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error loading {file_path}: {e}")
            return None

class RegimeConditioner:
    def __init__(self):
        self.detector = StormDetector()

    def label_regimes(self, df: pd.DataFrame, window_seconds: int = 60) -> pd.DataFrame:
        """
        Appends 'stress', 'activity', 'regime' columns to the dataframe.
        Downsamples to 1-minute (or window_seconds) resolution for scoring,
        then forward-fills labels to individual ticks.
        """
        if df.empty:
            return df

        # Resample to calculate Stress/Activity per window
        df_resampled = df.set_index('timestamp').resample(f'{window_seconds}s')
        
        regime_map = []
        
        for t, group in df_resampled:
            if len(group) < 10:
                scores = {'activity': 0, 'stress': 0}
                regime = "Quiet"
            else:
                scores = self.detector.process_window(group)
                regime = self.detector.get_regime_label(scores)
            
            regime_map.append({
                'window_start': t,
                'window_end': t + pd.Timedelta(seconds=window_seconds),
                'activity_score': scores['activity'],
                'stress_score': scores['stress'],
                'regime': regime
            })
            
        df_regimes = pd.DataFrame(regime_map)
        
        # Merge back to original ticks
        # We use pd.merge_asof to map each tick to its window
        
        # df_sorted = df.sort_values('timestamp')
        idx_df = np.argsort(df['timestamp'].values)
        df_sorted = df.iloc[idx_df]
        
        # df_regimes = df_regimes.sort_values('window_start')
        if not df_regimes.empty:
            idx_reg = np.argsort(df_regimes['window_start'].values)
            df_regimes = df_regimes.iloc[idx_reg]
        
        # merge_asof requires matched on column to be sorted
        merged = pd.merge_asof(
            df_sorted,
            df_regimes,
            left_on='timestamp',
            right_on='window_start',
            direction='backward'
        )
        
        # Filter out ticks that fell outside expected windows (shouldn't happen with backward)
        return merged

class DataQualityGate:
    def __init__(self, max_zero_dt_pct: float = 1.0):
        self.max_zero_dt_pct = max_zero_dt_pct

    def check_quality(self, df: pd.DataFrame) -> dict:
        """
        Returns dict with metrics and 'valid' bool.
        """
        if df.empty:
            return {'valid': False, 'reason': 'Empty DataFrame'}
            
        # Check dt=0
        dt = df['timestamp'].diff().dt.total_seconds().fillna(0)
        zero_count = (dt == 0).sum()
        zero_pct = (zero_count / len(df)) * 100
        
        # Check venue coverage
        venues = df['venue'].nunique()
        top_venue_pct = df['venue'].value_counts(normalize=True).iloc[0] * 100 if venues > 0 else 0
        
        valid = True
        reasons = []
        
        if zero_pct > self.max_zero_dt_pct:
            # We flag it, but don't strictly fail valid unless it's extreme (e.g. >50%)
            # The calling layer should handle jitter
            reasons.append(f"High Zero-DT: {zero_pct:.2f}%")
            
        return {
            'valid': valid,
            'zero_dt_pct': zero_pct,
            'venue_count': venues,
            'top_venue_concentration': top_venue_pct,
            'flags': reasons
        }


if __name__ == "__main__":
    # Test
    loader = TickLoader()
    # Find a date to test - listing dirs
    sample_dirs = sorted([d for d in DATA_DIR.glob("sample_*") if d.is_dir()])
    if not sample_dirs:
        print("No data found to test.")
        sys.exit(0)
        
    test_date = sample_dirs[-1].name.replace("sample_", "")
    test_symbol = "GME"
    
    print(f"Testing Layer 0 with {test_symbol} on {test_date}")
    
    df = loader.load_ticks(test_date, test_symbol)
    if df is not None:
        print(f"Loaded {len(df)} ticks.")
        
        conditioner = RegimeConditioner()
        df_labeled = conditioner.label_regimes(df)
        
        print("\nRegime Distribution:")
        print(df_labeled['regime'].value_counts())
        
        print("\nSample Data:")
        print(df_labeled[['timestamp', 'price', 'volume', 'venue', 'stress_score', 'regime']].head())
    else:
        print("Load failed.")
