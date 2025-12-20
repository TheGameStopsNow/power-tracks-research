#!/usr/bin/env bash
set -euo pipefail

# One-click helper for Power Tracks Research
# - Prompts for Polygon API key (optional)
# - Writes .env (if missing)
# - Creates micro sample from committed data (or fetched local)
# - Runs the magic demo

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"
EXAMPLE_ENV="$ROOT/.env.example"

echo "==> Power Tracks Research one-click setup"

# 1) Ensure .env exists
if [ ! -f "$ENV_FILE" ]; then
  echo "No .env found; copying from .env.example"
  cp "$EXAMPLE_ENV" "$ENV_FILE"
fi

# 2) Prompt for Polygon API key if missing
if ! grep -q "^POLYGON_API_KEY=" "$ENV_FILE"; then
  read -r -p "Enter your POLYGON_API_KEY (or leave blank to skip live fetch): " POLY_KEY
  echo "POLYGON_API_KEY=${POLY_KEY}" >> "$ENV_FILE"
else
  echo "POLYGON_API_KEY already present in .env"
fi

# Reload env so POLYGON_API_KEY is exported
set -a
[ -f "$ENV_FILE" ] && . "$ENV_FILE"
set +a

cd "$ROOT"

echo "==> Creating venv and installing Python deps"
python3 -m venv .venv
. .venv/bin/activate
pip install --quiet -r requirements.txt

TRADES_DEFAULT="data/raw/polygon/gme/2024-05-13/trades.json"
LOCAL_PRICE_PATHS="data/samples/local/gme_20240513/price_paths.csv"

# If key present, fetch raw sample into gitignored local dir, then build micro from it
if [ -n "${POLYGON_API_KEY:-}" ]; then
  echo "==> Fetching raw slices from docs/raw_data_manifest.json (gitignored)"
  python3 scripts/fetch_manifest.py || echo "Raw fetch skipped/failed; will use committed sample."
  if [ ! -f "$TRADES_DEFAULT" ]; then
    TRADES_DEFAULT="$(find data/raw/polygon/gme/2024-05-13 -name 'trades.json' | head -n1 || true)"
  fi
  if [ -n "$TRADES_DEFAULT" ] && [ -f "$TRADES_DEFAULT" ]; then
    echo "==> Deriving price_paths.csv from fetched trades ($TRADES_DEFAULT)"
    python3 scripts/build_price_paths.py --source "$TRADES_DEFAULT" --out "$LOCAL_PRICE_PATHS" --limit 2000 || true
  else
    echo "Trades not found; falling back to make data (small sample)"
    make data SYMBOL=GME DATE=2024-05-13 OUT="$LOCAL_PRICE_PATHS" || true
  fi
else
  echo "POLYGON_API_KEY not set; using committed sample."
fi

echo "==> Building micro sample"
if [ -f "$LOCAL_PRICE_PATHS" ]; then
  make micro-sample MICRO_SOURCE="$LOCAL_PRICE_PATHS"
else
  make micro-sample MICRO_SOURCE=data/samples/sample_2024-05-13/signals/price_paths.csv
fi

echo "==> Running magic demo"
make demo

cat <<'EOS'

Setup complete.

Next options:
  - Open labs (notebooks): jupyter notebook labs/00_packet_analysis.ipynb
  - Run suites (sample-safe): make suite-selectivity (or clusters/gating/portability/temporal/options/risk)
  - Run tests: make test   | make test-nbval

For a full tour, see docs/walkthrough.md and docs/troubleshooting.md.
EOS
