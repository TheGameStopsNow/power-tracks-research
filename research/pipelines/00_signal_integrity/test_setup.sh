#!/bin/bash
# Quick test script to verify the bundle works with your API key

set -euo pipefail

echo "============================================================"
echo "Power Tracks Reproducibility Bundle - Setup Test"
echo "============================================================"
echo ""

# Check for API key
if [ -z "${POLYGON_API_KEY:-}" ]; then
    echo "⚠️  POLYGON_API_KEY not set"
    echo ""
    echo "Please set your API key:"
    echo "  export POLYGON_API_KEY='your_key_here'"
    echo ""
    echo "Or run:"
    echo "  POLYGON_API_KEY='your_key' $0"
    exit 1
fi

echo "✓ API key found"
echo ""

# Test Python dependencies
echo "Checking Python dependencies..."
if ! python3 -c "import requests, pandas, pytz" 2>/dev/null; then
    echo "⚠️  Missing dependencies. Installing..."
    pip install -q requests pandas pytz
fi
echo "✓ Dependencies OK"
echo ""

# Test fetch script
echo "Testing fetch_sample_data.py..."
python3 scripts/fetch_sample_data.py \
    --symbol GME \
    --date 2024-05-13 \
    --output-dir sample_2024-05-13/raw_ticks

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Setup test passed!"
    echo ""
    echo "Next steps:"
    echo "  1. Run pipeline: ./scripts/pipeline_verify.sh --input sample_2024-05-13/raw_ticks"
    echo "  2. Share decoded data (see DATA_SHARING.md)"
else
    echo ""
    echo "❌ Setup test failed"
    exit 1
fi


