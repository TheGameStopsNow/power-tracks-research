import pyarrow.parquet as pq
import sys

# Try loading just the schema (fast)
try:
    base_dir = Path(__file__).resolve().parent.parent.parent
    parquet_file = base_dir / 'data/raw/data/options_library/GME/2021-01-04/reconstructed_snapshot.parquet'
    print(f"Inspecting: {parquet_file}")
    
    # Read schema only
    schema = pq.read_schema(parquet_file)
    print("Columns found:")
    for name in schema.names:
        print(f"- {name}")
        
    required = ['open_interest', 'implied_volatility', 'strike', 'type', 'expiration']
    missing = [c for c in required if c not in schema.names]
    
    if missing:
        print(f"MISSING CRITICAL COLUMNS: {missing}")
    else:
        print("All required columns present.")
        
except Exception as e:
    print(f"Error: {e}")
