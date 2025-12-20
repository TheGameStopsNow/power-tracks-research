#!/usr/bin/env python3
"""
EDGX Data Loader
=================

Loads and filters tick data specifically from EDGX exchange for deep decode analysis.
"""

from pathlib import Path
from typing import List, Optional
import pandas as pd


# Exchange venue codes (from Polygon.io data)
# EDGX = 4 (confirmed from edgx_spike_20240517.md documentation)
# Note: Some samples use string 'EDGX' instead of ID 4
EDGX_VENUE_IDS = [4, 'EDGX']  # EDGX Exchange

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "samples"



def load_edgx_data(
    sample_dir: Path,
    symbol: str = "GME",
    venue_ids: Optional[List[int]] = None
) -> pd.DataFrame:
    """
    Load tick data filtered for EDGX exchange.
    
    Args:
        sample_dir: Path to sample_YYYYMMDD directory
        symbol: Stock symbol
        venue_ids: List of venue IDs to filter (default: EDGX_VENUE_IDS)
    
    Returns:
        DataFrame with EDGX-only trades
    """
    if venue_ids is None:
        venue_ids = EDGX_VENUE_IDS
    
    # Find trades CSV
    trades_files = list(sample_dir.glob(f"raw_ticks/{symbol}*_trades.csv"))
    if not trades_files:
        raise FileNotFoundError(f"No trades file found for {symbol} in {sample_dir}")
    
    # Load data
    df = pd.read_csv(trades_files[0])
    
    # Parse timestamp with timezone awareness
    # Parse timestamp with timezone awareness
    try:
        df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed', utc=True)
    except Exception:
        # Fallback for tough cases
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    
    # Filter for EDGX venue
    df_edgx = df[df['venue'].isin(venue_ids)].copy()
    
    # Sort by timestamp
    df_edgx = df_edgx.sort_values('timestamp').reset_index(drop=True)
    
    return df_edgx


def load_all_venues_summary(sample_dir: Path, symbol: str = "GME") -> pd.DataFrame:
    """
    Load data and summarize all venues present (for debugging/analysis).
    
    Returns:
        DataFrame with venue counts
    """
    trades_files = list(sample_dir.glob(f"raw_ticks/{symbol}*_trades.csv"))
    if not trades_files:
        raise FileNotFoundError(f"No trades file found for {symbol} in {sample_dir}")
    
    df = pd.read_csv(trades_files[0])
    
    venue_counts = df['venue'].value_counts().sort_values(ascending=False)
    
    return pd.DataFrame({
        'venue': venue_counts.index,
        'count': venue_counts.values,
        'percentage': (venue_counts.values / len(df) * 100).round(2)
    })


def get_sample_dirs(data_dir: Path = DATA_DIR) -> List[Path]:
    """Get all sample directories sorted by date."""
    return sorted([d for d in data_dir.glob("sample_*") if d.is_dir()])


if __name__ == "__main__":
    # Test loader
    import sys
    
    print(f"BASE_DIR: {BASE_DIR}")
    print(f"DATA_DIR: {DATA_DIR}")
    print(f"DATA_DIR exists: {DATA_DIR.exists()}")
    
    if DATA_DIR.exists():
        sample_dirs = get_sample_dirs()
        print(f"Found {len(sample_dirs)} sample directories")
    else:
        print(f"Data directory not found. Using hardcoded test path...")
        # Use a known path from the existing research
        test_path = BASE_DIR / "data" / "samples" / "sample_2024-05-13"
        if test_path.exists():
            sample_dirs = [test_path]
        else:
            # List what's actually in data/
            data_root = BASE_DIR / "data"
            if data_root.exists():
                print(f"\nContents of {data_root}:")
                for item in data_root.iterdir():
                    print(f"  {item.name}")
            sys.exit(1)
    
    if not sample_dirs:
        print("No sample directories found")
        sys.exit(1)
    
    test_dir = sample_dirs[-1]  # Most recent
    print(f"\nTesting with: {test_dir.name}")
    
    # Show venue distribution
    print("\n=== Venue Distribution ===")
    venue_summary = load_all_venues_summary(test_dir)
    print(venue_summary.head(10))
    
    # Check for EDGX in the data
    print("\n=== Checking for EDGX (based on web search, venue ID should be 14 or code 'K') ===")
    
    # Try venue 14 first
    for venue_id in [14, 4, 11, 12]:
        try:
            df_test = load_edgx_data(test_dir, venue_ids=[venue_id])
            if len(df_test) > 0:
                print(f"\n✓ Venue {venue_id}: {len(df_test)} trades found")
                print(f"  Time range: {df_test['timestamp'].min()} to {df_test['timestamp'].max()}")
                print(f"  Price range: ${df_test['price'].min():.2f} - ${df_test['price'].max():.2f}")
                print(f"\n  First 3 trades:")
                print(df_test[['timestamp', 'price', 'volume', 'venue']].head(3))
                break
        except Exception as e:
            print(f"  Venue {venue_id}: Error - {e}")

