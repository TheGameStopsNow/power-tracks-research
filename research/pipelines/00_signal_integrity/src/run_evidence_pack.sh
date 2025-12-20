#!/usr/bin/env bash
# One-shot reproducibility run for the evidence pack.
# - Creates venv and installs requirements.
# - Rebuilds samples for specified dates (requires POLYGON_API_KEY).
# - Verifies SHA256/frames/signals.
# - Refreshes predictiveness/TISA reports and plots.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -z "${POLYGON_API_KEY:-}" ]]; then
  echo "POLYGON_API_KEY is required" >&2
  exit 1
fi

DATES=("2024-05-13" "2024-05-14" "2024-05-15" "2024-05-16" "2024-05-17")

echo "[1/5] Creating venv and installing dependencies..."
rm -rf .venv
PYBIN="${PYBIN:-python3.11}"
"${PYBIN}" -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "[2/5] Rebuild ticks -> frames -> signals for target dates..."
for d in "${DATES[@]}"; do
  echo "  - Rebuilding $d"
  python scripts/rebuild_day.py --symbol GME --date "$d"
done

echo "[3/5] Verify SHA256 + frame/signal validity..."
for d in "${DATES[@]}"; do
  python scripts/verify_reproducibility.py \
    --sample-dir "sample_${d}" \
    --manifest "sample_2024-05-13/MANIFEST.json" \
    --sha256 "sample_${d}/SHA256SUMS"
done

echo "[4/5] Predictiveness and TISA reports/plots..."
# Predictiveness (assumes features already built or available)
# If features are missing, build_features.py should be run beforehand.
if ls features/*.csv >/dev/null 2>&1; then
  python scripts/eval_predictiveness.py \
    --features features/*.csv \
    --output reports/predictiveness.json
fi
# Base TISA per day
for d in "${DATES[@]}"; do
  python scripts/tisa_validate.py \
    --signals "sample_${d}/signals/price_paths.csv" \
    --bars-dir bars_range \
    --symbol GME \
    --date "$d" \
    --horizons 1 4 7 30 90 180 \
    --scales 0.5 0.75 1.0 1.25 2.0 4.0 \
    --output "reports/tisa_${d}.json"
done
# Extended TISA (windowed, z-RMSE/DTW with shuffled baselines)
for d in "${DATES[@]}"; do
  python scripts/tisa_extended.py \
    --signals "sample_${d}/signals/price_paths.csv" \
    --bars-dir bars_range \
    --symbol GME \
    --date "$d" \
    --windows 0-30 60-70 70-80 80-90 150-180 \
    --scales 0.5 0.75 1.0 1.25 2.0 4.0 \
    --output "reports/tisa_extended_${d}.json"
done
# Plots (predictiveness, TISA base, extended, overlays)
python scripts/plot_reports.py
python scripts/plot_tisa_extended.py
python scripts/plot_tisa_overlays.py

echo "[5/5] Done. Key artifacts refreshed under reports/ and sample_*/."
