# EDGX Deep Decode (Operation Glasshouse)

Deep decode of EDGX tick data to detect/stress-test opcode grammar, burst storms,
and non-random bitstreams. Inputs live under `data/samples/sample_YYYY-MM-DD/`
and outputs are written to `results/` inside this phase.

## Quickstart

```bash
# From repo root
cd research/edgx_deep_decode
python3 main.py
```

This will:

1) Load the most recent `data/samples/sample_*/raw_ticks/<SYMBOL>_trades.csv`
   (EDGX only, venue 4/`EDGX`).
2) Detect burst storms, extract candidate bitstreams (first 50k trades), and run
   cryptanalysis.
3) Save artifacts under `results/` (bursts CSV, cryptanalysis JSON, spectrograms).

## Input layout (expected)

```
data/samples/sample_YYYY-MM-DD/
  raw_ticks/
    GME_YYYY-MM-DD_trades.csv   # includes venue column
```

Tip: use the manifest in `docs/raw_data_manifest.json` (repo root) to fetch the
exact windows if needed.

## Outputs (in `results/`)

- `bursts_<date>.csv` — detected burst storms summary
- `cryptanalysis_<date>.json` — per-signal entropy/chi²/autocorr
- `spectrogram_<signal>_<date>.png` — visual diagnostics (only for long streams)
- `deep_value_analysis.csv` — strategy/backtest summary
- `storm_vs_calm_grammar.png` — grammar comparison visual
- `extracted_signals_*.csv`, `frame_detection_*.json`, `master_vocabulary.json`, etc.

## Core scripts

## Playbooks (organized)

- **Run First:** `playbooks/main.py` — end-to-end decode (load → detect → extract → analyze → export)
- **Live/Sim & Trading:** `playbooks/live_decoder.py`, `playbooks/strategy_backtester.py`, `playbooks/operation_glasshouse/`*
- **Alpha/Validation:** `playbooks/price_correlation.py`, `playbooks/walk_forward.py`, `playbooks/multidate_validator.py`, `playbooks/universal_grammar_validator.py`
- **Protocol/Grammar:** `playbooks/semantic_mapper.py`, `playbooks/grammar_analysis.py`, `playbooks/sequence_mapper.py`, `playbooks/vocab_vectorizer.py`, `playbooks/protocol_inspector.py`, `playbooks/protocol_fingerprint.py`, `playbooks/packet_decoder.py`, `playbooks/frame_detection.py`, `playbooks/dle_checker.py`
- **Scanners & Maps:** `playbooks/scan_pre_event.py`, `playbooks/cross_symbol.py`, `playbooks/cross_symbol_verify.py`, `playbooks/cross_date_stability.py`, `playbooks/deep_exploration.py`, `playbooks/power_map_generator.py`, `playbooks/power_track_decoder.py`, `playbooks/extended_analysis.py`, `playbooks/sequence_miner.py`
- **Seeds/Fractals/TISA:** `playbooks/prepare_tisa_input.py`, `playbooks/tisa_extended.py`, `playbooks/fractal_matcher.py`, `playbooks/fractal_inspector.py`
- **Visualization:** `playbooks/language_visualizer.py` (produces `results/storm_vs_calm_grammar.png`), `playbooks/rhythm_analysis.py`
- **Fuzzing/Experiments:** `playbooks/protocol_fuzzer.py`, `playbooks/adversarial_decoding.py`
- **Helpers:** `playbooks/check_data_range.py`, `playbooks/check_venues.py`

\* Operation Glasshouse playbooks live in `playbooks/operation_glasshouse/` (imports already wired).

- Core modules now live in `core/` (loader, burst_detector,## Usage

1. **Download Data**:

    ```bash
    python download_data.py
    ```

2. **Run Cryptanalysis**:

    ```bash
    python -m core.analysis
    ```

    *Note: Run from `research/edgx_deep_decode/` directory.*

## Structure

- **`core/`**: Analysis logic and tools.
  - `analysis.py`: Main cryptanalysis suite.
  - `loader.py`: EDGX-specific data loader.
- **`data/`**: Local data cache (gitignored).
- **`docs/`**: Briefs and reports (`DIRECTIVE.md`, `WALKTHROUGH.md`).
- **`output/`**: Results (`.json`) and spectrograms (`.png`).
- **`scripts/`**: Auxiliary files and seeds.
- **`operation_glasshouse/`**: Specific sub-operation reports.

## Findings

(See `docs/PHASE4_SUMMARY.md` for details)
- **Entropy Dip**: Detected 18% entropy reduction on May 16th.
- **Pattern 101010**: Strong cyclic component at 200ms intervals.
- **Venue Lock**: 94% of suspicious prints routed to EDGX.`sample_*`

- `burst_detector.py` — burst/“storm” detection
- `extractors.py` — signal/bitstream extraction
- `analysis.py` — entropy, chi², autocorr, spectrogram generation

## Analysis helpers (selected)

- Robustness: `walk_forward.py`, `cross_date_stability.py`, `deep_exploration.py`
- Grammar: `semantic_mapper.py`, `grammar_analysis.py`, `vocab_vectorizer.py`
- Fuzzing/edge cases: `protocol_fuzzer.py`, `adversarial_decoding.py`
- Backtests: `strategy_backtester.py` (see `operation_glasshouse/`)

## References

- `WALKTHROUGH.md` — full step-by-step narrative
- `DIRECTIVE.md`, `PHASE4_SUMMARY.md` — phase notes and directives
- `operation_glasshouse/FULL_REPORT.md` — detailed study
