import sys
from pathlib import Path
from dotenv import load_dotenv

# Add repo root to path to import scripts
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(repo_root))

import scripts.fetch_manifest as fetcher
import scripts.build_price_paths as converter

if __name__ == "__main__":
    load_dotenv() # Load .env variables
    print("--- Downloading Sample Data for Decoder Tools ---")
    
    # Point to the local manifest
    manifest_path = Path(__file__).resolve().parent / "manifest.json"
    
    # Verify manifest exists
    if not manifest_path.exists():
        print(f"Error: Manifest not found at {manifest_path}")
        sys.exit(1)
        
    # Inject manifest argument for the fetcher script
    sys.argv = [sys.argv[0], "--manifest", str(manifest_path)]
    fetcher.main()
    
    # Post-processing: Convert JSON to CSV for the tool
    print("--- Converting to CSV ---")
    
    # Path resolution (matching manifest logic)
    # Manifest destination: "../../data/samples/gme_20240517/tools_sample"
    # Relative to manifest location: scripts/tools/manifest.json
    output_dir = manifest_path.resolve().parent / "../../data/samples/gme_20240517/tools_sample"
    output_dir = output_dir.resolve()
    
    source_json = output_dir / "trades.json"
    dest_csv = output_dir / "sample_data.csv"
    
    if source_json.exists():
        print(f"Converting {source_json} -> {dest_csv}")
        converter.build_price_paths(source=source_json, out=dest_csv, limit=None)
        print(f"\n✅ Sample data ready at: {dest_csv}")
        print(f"   Usage: export PTE_CSV_PATH={dest_csv}")
    else:
        print(f"Warning: {source_json} not found. Conversion skipped.")
