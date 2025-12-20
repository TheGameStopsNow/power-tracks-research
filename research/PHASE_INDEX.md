# Phase Index (Research)

Quick pointers for recent phases (paths are repo-relative; each phase is self-contained).

## Core phases
- **Phase 3 – Comparative (Deep Decode vs Varints)**  
  - Data: `research/phase3_comparative/data` (GME Roaring Kitty window, May 13–17, 2024).  
  - Scripts: `comparative_pipeline.py`, `correlation_study.py`, `fuzz_storm_frames.py`.  
  - Report: `research/phase3_comparative/README.md`.
- **Phase 8 – Cross-Symbol Chatter**  
  - Data: `research/phase8_cross_symbol_chatter/data` (basket GME/AMC/KOSS/BB/...; May 13–17, 2024).  
  - Scripts: `analyze_chatter.py`, `extract_basket_signals.py`, `fetch_basket.py`.  
  - Reports: `CROSS_SYMBOL_REPORT.md`, `CROSS_SYMBOL_MICRO_REPORT.md`; brief in `README.md`.
- **Phase 9 – Chatter Vocabulary**  
  - Data: `research/phase9_chatter_vocabulary/data/basket_events_ticks.csv` (generated).  
  - Scripts: `vocab_analyzer.py`, `generate_conversation_graph.py`.  
  - Outputs: `CHATTER_DICTIONARY.md`, `charts/conversation_graph.png`.
- **Phase 10 – Rosetta Stone**  
  - Data: `research/phase10_rosetta_stone/data/chatter.db`.  
  - Scripts: `build_codex.py`, `classify_motifs.py`, `fetch_week_ticks.py`.  
  - Report: `ROSETTA_REPORT.md`.
- **Phase 12 – Broad Market**  
  - Data: `research/phase12_broad_market/data/basket_sweep_density.csv`.  
  - Script: `scan_basket_sweep.py`.  
  - Report: `COMPARATIVE_REPORT.md`.
- **Phase 13 – Temporal**  
  - Data: `research/phase13_temporal/data` (AAPL, GME, GROV, SPY; 2024-05-13 → 2024-05-17, RTH 13:30Z–20:00Z).  
  - Script: `run_overnight_study.py`.  
  - Report: `TEMPORAL_DYNAMICS_REPORT.md`.
- **Phase 14 – Genome**  
  - Data: `research/phase14_genome/data/influence_edges.csv`.  
  - Script: `run_genome_project.py`.  
  - Report: `GENOME_REPORT.md`.
- **Phase 15 – Atlas**  
  - Data: `research/phase15_atlas/data` (~48 symbols; Peace 2024-04-15 → 04-19, War 2024-05-13 → 05-17, RTH 13:30Z–20:00Z).  
  - Script: `run_atlas_project.py`.  
  - Report: `ATLAS_REPORT.md`; outputs inside the phase.
- **Phase 18 – Ripple**  
  - Data: `research/phase18_ripple/data` (50+ symbols; 2024-04-29 → 2024-05-31, RTH 13:30Z–20:00Z).  
  - Scripts: `run_study.py`, `analyze_timeline.py`, `generate_charts.py`.  
  - Outputs: `charts/`; report `RIPPLE_REPORT.md`.
- **Phase 21 – 2021 Retrospective**  
  - Data: `research/phase21_2021_retro/data`.  
  - Outputs: `retro_timeline.png`, `retro_density_matrix.csv`; summary in `README.md`.
- **Phase 24 – Full Market Scan**  
  - Data: `research/phase24_full_scan/data/dragnet_results.csv`.  
  - Scripts: see phase README (dragnet scan).  
  - Outputs: `charts/`; summary in `README.md`.
- **Phase 29 – System Cartography**  
  - Data: `research/phase29_system_cartography/real_ticks/` (tick slices per seed), audit `DATA_AUDIT_REPORT.md`.  
  - Scripts: `run_cartography.py`, `scan_reverse_signal.py`, `analyze_real_signal_efficacy.py`.  
  - Outputs: `*REPORT.md`, `cycle_backtest.txt`.
- **Phase 30 – Interconnectedness**  
  - Data: `research/phase30_interconnectedness/signal_log.csv`.  
  - Scripts: `scan_network.py`, `measure_impact.py`, `map_latency.py`.  
  - Reports: `significance_report.md`, `latency_stats.md`, `DIRECTIVE.md`, `README.md`.

- **Phase 22 – Synchronicity**
  - Data: `research/phase22_synchronicity/data/synchronicity_matrix.csv`.
  - Scripts: `run_analysis.py`, `generate_synchronicity_charts.py`.
  - Outputs: `cluster_events.csv`, `jaccard_matrix.csv`.

- **Phase 23 – Causality (Lead-Lag)**
  - Data: `research/phase23_causality/data/lead_lag_results.csv`.
  - Scripts: `run_causality.py`, `generate_causality_charts.py`.
  - Report: `CAUSALITY_REPORT.md` (implied).

- **Phase 25 – Energy (Surface Mapping)**
  - Data: `research/phase25_energy/data/energy_surface_15m.csv`.
  - Scripts: `run_surface_mapping.py`, `generate_flow_animation.py`.
  - Outputs: `charts/energy_surface_15m.png`, `flow_animation.gif`.

- **Phase 27 – Options (Cycle Analysis)**
  - Inputs: Uses Phase 25 Energy Surface.
  - Scripts: `run_options_analysis.py`.
  - Outputs: `charts/energy_return_cycle.png`, `charts/strike_gravity.png`.

- **Phase 26 – Hydraulics**
  - Scripts: `run_pressure_validation.py`.
  - Report: Validation of pressure mechanics.

- **Phase 74 – RegA (Gamma Proof)**
  - Data: `research/phase74_rega/daily_metrics.csv` (GME 2021-2025), `GME_2024-05-17_trades.csv`.
  - Scripts: `calculate_metrics.py`, `fit_vol_model.py`, `barrier_event_study.py`.
  - Report: `research/phase74_rega/README.md` (The Gamma Suppression Theorem).

## Steganography Research
- Location: `research/steganography/`
- Modules: `01_lsb_detection`, `02_timing_channels`, `03_order_book`, `04_steganalysis`, etc.
- Scripts: `lsb_analysis.py`, `timing_analysis.py`.
- Purpose: Advanced investigation into covert channels in market data.

## EDGX Deep Decode (Operation Glasshouse)
- Location: `research/edgx_deep_decode/`
- Entry: `playbooks/main.py` (uses `core/` modules; outputs to `results/`).
- Playbooks organized in `playbooks/` (live, alpha, protocol, scanners, viz, fuzzing).
- References: `WALKTHROUGH.md`, `DIRECTIVE.md`, `PHASE4_SUMMARY.md`, `operation_glasshouse/FULL_REPORT.md`.

## Keeping the manifest current
Run `python scripts/add_research_to_manifest.py` after adding new raw slices so `docs/raw_data_manifest.json` lists the exact windows. Use the paid Polygon key with `pt-data harvest` (preferred) or extend `scripts/fetch_manifest.py` for tick-level pulls.
