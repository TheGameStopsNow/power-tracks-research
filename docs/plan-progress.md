# Power Tracks Engine Improvement Plan – Progress Tracker

_Last updated: 2025-11-10_

This file mirrors the action plan documented in `docs/Audit of the Power Tracks Engine for Pow.md` so we can mark progress over time. Update the checkboxes and notes as work advances.

## Sprint 1 – “Stability and Integrity”

- [x] Integrate track decoding (CRC validation, decoded payload persistence, tests)
  - Notes: Added `packages/core/src/decoder/trackDecoder.ts` with XOR mask trials, CRC-7 checks, varint parsing, price-path preview, plus Jest coverage. `PowerTrackDetector` now synthesizes burst payloads from real window ticks, decodes them automatically, and persists `decoded_burst.json` + timestamped `price_path.json` alongside `window_ticks.csv`/`summary.json`. Fixtures copied from the shared hub power end-to-end Jest coverage (`decodedArtifacts.integration.test.ts`) so we continuously verify the detector’s artifacts against the canonical `lag_manifest.json`/`decoded_fields.csv` outputs consumed by `/v1/tracks/path`, and the daemon’s filesystem loader reuses the exact same builder/decoder to regenerate bursts whenever `decoded_burst.json` is missing.
- [x] Prevent duplicate tracks (hash-based IDs, duplicate guard, regression test)
  - Notes: `PowerTrackStorage` now normalizes candidates into stable hashes/IDs, skips writes when a hash already exists, and has Jest coverage (`storage.duplicates.test.ts`).
- [x] Format handling fix for JSON minute bars (loader updates, config tweaks)
  - Notes: `FilesystemLoader.loadMinuteBars` now detects JSON minute-bar directories, parses nested arrays/JSONL, preserves validation, and has Jest coverage for the JSON fallback path.
- [x] Basic Auth on API (middleware, configuration, README update)
  - Notes: Added configurable API key middleware (`server.auth`), enforced on all routes except explicit public ones, with tests and README instructions for `ENGINE_API_KEY`.

## Sprint 2 – “Analytics and Performance”

- [x] Entropy & regime feature (analytics computation, tagging, `/v1/state`)
  - Notes: Detector now maintains rolling decodability history, persists regime classification per track, `/v1/state`/`summary` expose regime breakdowns plus decibel aggregates, and SQLite snapshots store primary regimes + decibel JSON for dashboard queries. Added Jest coverage for state/summary payloads and live aggregator outputs.
- [x] Options context integration for macro tracks
  - Notes: Macro summaries now call Polygon snapshots (with caching) to attach gamma/vega/theta context and classify pressure; tracks expose `optionsContext` + `optionsPressure`, with Jest coverage.
- [x] Track index in SQLite (retro migration, API refactor)
  - Notes: `FilesystemLoader.listAllTracks` now hydrates the SQLite snapshot store, queries via `TrackSnapshotStore.listSnapshots` (detection-time order, limit/offset), and falls back to filesystem scan only when the store is empty. Added in-memory snapshot store helpers for tests plus Jest coverage that exercises symbol + ALL pagination paths.
- [x] Pagination & limits on track APIs
  - Notes: `/v1/tracks` accepts `offset`, enforces per-symbol limits via the snapshot store, and replies with the applied offset for dashboards. Snapshot queries gained `orderBy`, `limit`, and `offset` knobs to support API consumers.

## Sprint 3 – “Observability and Hardening”

- [x] Prometheus metrics & dashboard
  - Notes: Integrated `prom-client` with the daemon, added `/metrics` (public by default), instrumented HTTP latency histogram, track detection counters, sink error counters, and covered the endpoint with Jest to ensure detections increment metrics.
- [x] Alerting rules for critical signals
  - Notes: Added Prometheus alert examples (`docs/prometheus-alerts.example.yaml`) covering detection drought, feed reconnect storms, and sink write failures, leveraging the new `/metrics` counters.
- [x] Robust error handling (retries, fail-fast guards)
  - Notes: Added retry/backoff to options snapshot fetch with cached fallback, exposed sink write retries + Prometheus counters, and instrumented feed reconnects; expanded Jest coverage for the new behaviors.
- [x] Documentation & DevOps updates (runbook, logging polish)
  - Notes: Added `docs/runbook.md` with monitoring/alert guidance, linked Prometheus alert templates, and updated README/audit to reflect observability improvements.

## Sprint 4 – “Polish and Future-Proofing”

- [x] User feature review & quick wins
  - Notes: Added `/v1/tracks/daily` endpoint for Studio heatmaps, exposing per-day track totals along with regime/status breakdowns, plus Jest coverage via direct route tests.
- [x] Performance tuning tests (multi-symbol load)
  - Notes: Added `npm run --workspace @powertracks/daemon perf:load` synthetic tick benchmark to gauge detector throughput across multiple symbols; produces throughput stats for quick regression checks.
- [x] Prepare for multi-symbol scaling (deployment guidance, config)
  - Notes: Authored `docs/multi-symbol-scaling.md` with symbol sharding patterns, compose overlay, and operational checklist; README/runbook now link to the scaling guide.
- [x] OpenAPI & client libraries
  - Notes: Daemon now serves the canonical YAML spec directly, `npm run openapi:clients` regenerates the JSON spec plus a TypeScript SDK (`clients/typescript`) and a lightweight Python client (`clients/python`), and stale inline spec exports were removed.

## Sprint 5 – “Automation & Shared Clients”

- [x] Single CLI runbook (Polygon → detector → decoder → catalog/B2)
  - Notes: `cli/pte/src/index.ts` now drives batch diagnostics, pipeline decoding, optional Postgres catalog migration, and optional B2 sync from one `pte runbook` command, emitting `PTE_RUNBOOK_RESULT` lines with ledger, manifest, detection counts, and status per trade date for operators and log shipping.
- [x] Orchestrator parity with CLI decoder artifacts
  - Notes: `dashboard/lib/orchestration/queue.ts` invokes `scripts/run_power_track_pipeline.js` after each detector pass, records manifest summaries + detection counts in job runtime metadata, and the orchestration panel surfaces both detector and decoder manifest paths.
- [x] Studio routes migrated to the generated SDK
  - Notes: `/api/bars` and `/api/replay` now call `StateService.getV1RawBars` via `@powertracks/client` (falling back to Polygon/API only on 5xx errors), preserving the Polygon-style payload so the chart and replay components stay in sync with the OpenAPI schema.
- [x] Minute-bar consolidation helper
  - Notes: Added `power-tracks-data/scripts/consolidate_minute_bars.py` plus documentation so operators can generate `data/polygon_min/{SYMBOL}.csv` directly from the JSON storage tree when backfills or decodability scripts need the legacy CSV layout.

## Work Log

- _2025-11-05_: Created progress tracker file and initialized sprint checklists.
- _2025-11-05_: Implemented decoder module, unit tests, and hooked decode summaries into `PowerTrackDetector`.
- _2025-11-05_: Added duplicate-track guard with stable IDs and regression test coverage.
- _2025-11-05_: Extended filesystem loader to ingest JSON minute bars, added parsing helpers, and verified via Jest.
- _2025-11-05_: Introduced API key auth middleware, config defaults, tests, and documentation updates.
- _2025-11-05_: Enhanced decodability/regime analytics across detector, storage, and APIs; added live/regime breakdowns and decibel summaries.
- _2025-11-06_: Extended snapshot schema with primary regimes and decibel aggregates, and added integration tests covering filesystem state/summary + live aggregator analytics.
- _2025-11-06_: Backed track listings with the SQLite snapshot index, added API pagination support, and introduced jest-friendly SQLite mocks/in-memory stores to keep tests green.
- _2025-11-06_: Added Prometheus instrumentation via `/metrics`, tracked detections/HTTP latency, and validated metrics output in new Jest coverage.
- _2025-11-06_: Authored Prometheus alert rules for detection stalls, feed reconnect floods, and sink failures (see `docs/prometheus-alerts.example.yaml`).
- _2025-11-06_: Hardened error paths with options snapshot retry/fallback, sink write retry logging, and additional metrics for reconnects; added targeted Jest regression tests.
- _2025-11-05_: Wired macro track outputs to Polygon options snapshots, added pressure labelling, and cached exposure summaries.
- _2025-11-09_: Created `codex/progress-tracking` branches across Engine/Data/Studio repos to stage the next round of spec and implementation updates per instructions.
- _2025-11-09_: Synced the daemon with the canonical OpenAPI YAML, added the `openapi:clients` generator, and committed the new TypeScript + Python client libraries.
- _2025-11-09_: Ported `validateRealData` into `@powertracks/core`, updated orchestrator/daemon to consume the shared helper, and deleted the duplicate daemon-only implementation.
- _2025-11-09_: Added artifact bundling to `PowerTrackStorage` (window tick CSV + summary JSON) and plumbed tick-window snapshots through the detector so every saved track preserves its burst context for downstream decoding.
- _2025-11-10_: Exported the detector burst builder, taught the daemon loader to reconstruct `decoded_burst.json` from shared window ticks, and added a second GME storage fixture so the integration suite mirrors the live `storage/power_tracks/**` corpus.
- _2025-11-10_: Re-exported the burst builder via the daemon package, imported the third canonical GME fixture for regression tests, and synchronized the unified plan/status docs with the new artifact validation flow.
- _2025-11-10_: Added a fourth GME decoded-burst fixture (`gme_20240513t092724000z_*`) so regression tests cover contiguous detections and the daemon keeps matching the shared hub bundles.
- _2025-11-10_: Wired dependency-injected logging into `PowerTrackDetector`, documented the option in the core README, and checked the release checklist item in `docs/core-scope.md`.
- _2025-11-10_: Documented the entire public API surface in the core README, added a Quick Start example + standalone integration test that exercises package-level exports, and refreshed package metadata for release readiness.
- _2025-11-10_: Produced dual build artifacts (CommonJS + ESM) with `dist/esm` packaging, added toolchain scripts to mark/fix ESM imports, and validated a fresh `npm init` project can require/import `@powertracks/core`.
- _2025-11-10_: Added manifest-level decodability guarantees in `PowerTrackStorage` (recomputes metrics from artifact window ticks, syncs summary metadata, and enforces regime annotations) with expanded artifact tests to assert every persisted track carries decodability state.
- _2025-11-10_: Closed the architecture open questions by locking the CLI to the existing Node/Commander workspace, standardizing on Redis Streams for internal fan-out, reaffirming JSON + artifact bundles as the canonical persistence format, and documenting the live Prometheus metrics stack.
- _2025-11-10_: Authored `docs/data-architecture.md` to document minute-bar ingestion, artifact storage, and decodability lifecycles, and updated the data architecture analysis to mark the minute-bar/documentation fixes complete.
- _2025-11-10_: Reduced manifest scan overhead by teaching `FilesystemLoader` to hydrate the SQLite snapshot store lazily (using `TrackSnapshotStore.getSymbolStats()` + TTL caching) and updated the data architecture analysis to mark the manifest/index performance fix as shipped.
- _2025-11-10_: Unified shared storage defaults—`loadEngineConfig` now auto-detects the `power-tracks-data` root (env/config) and backfills `detector.storage` paths, with the behavior documented in `docs/data-architecture.md#shared-root-discovery`.
- _2025-11-10_: Captured the retention/monitoring plan (90-day track ledgers, 180-day artifact retention, JSON minute-bar compression, Prometheus/node-exporter hooks) in `docs/data-architecture.md#data-retention--monitoring` and checked the archival TODO off the analysis list.
- _2025-11-10_: Extracted the API-key middleware into `registerAuthPlugin`, added fast unit tests, and removed the long-running server-based test so the daemon suite exits cleanly.
