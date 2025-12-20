# Power Tracks Engine – Architecture Draft

## Goals

1. Provide a single, audited implementation of Power Track detection, storage, and distribution that can be embedded anywhere.
2. Support three interaction models without code forks:
   - **SDK**: import the detector/storage classes directly.
   - **Daemon**: run a long-lived service that ingests feeds and publishes detections.
   - **CLI/TUI**: empower operators with PowerDecoder-style tooling for ad-hoc analysis.
3. Preserve data provenance and zero-synthetic-data guarantees regardless of ingress path (Polygon live feed, historical ZIPs, or pipeline exports).
4. Offer flexible egress (filesystem manifests, SQL/NoSQL, message buses, HTTP webhooks) so AlgoRythym and other systems can subscribe without bespoke glue.

## Component Map

```
┌────────────────────────────────────────────────────────────┐
│                         Interfaces                         │
│  - REST/gRPC API  - WebSocket events  - CLI/TUI (pte)       │
└────────────────────────────────────────────────────────────┘
            │                         │                          
┌───────────────────┐   ┌──────────────────────────┐   ┌──────────────────┐
│  Service Daemon   │   │     Pipeline Adapter     │   │   SDK Consumers  │
│  (Fastify + WS)   │   │  (Python / notebooks)    │   │  (AlgoRythym, etc.) │
└───────────────────┘   └──────────────────────────┘   └──────────────────┘
            │                     │                          │
            └──────────┬──────────┴──────────────┬───────────┘
                       │                         │
                ┌────────────────────────────────────────┐
                │           Core Engine (TS)             │
                │  - Tick ingestion + validation         │
                │  - FFT/ROC hybrid detection            │
                │  - Track storage + hashes              │
                │  - Config + schema validation          │
                │  - Event emitter / telemetry           │
                └────────────────────────────────────────┘
                       │                         │
        ┌──────────────┘                         └──────────────┐
┌────────────────────────────┐             ┌────────────────────┐
│   Connectors / Ingress     │             │  Egress Destinations│
│ - Polygon WS + REST        │             │ - Filesystem JSONL  │
│ - Historical CSV/Parquet   │             │ - SQLite/Postgres   │
│ - Pipeline bundle importer │             │ - Kafka/Redis/SQS   │
└────────────────────────────┘             │ - Webhooks / gRPC   │
                                           └────────────────────┘
```

## Key Modules

### `packages/core`
- **Detector**: Port of `src/data/power_track_detector.js` with TypeScript types and dependency injection for FFT/ROC utilities.
- **Storage**: Extends the JSON file writer to support pluggable drivers (FS, SQLite, Postgres). Includes hashing + metadata.
- **Config**: Shared schema (Zod) enforcing the documented thresholds (`window=50`, `power_thresh=1`, `roc=0.0001`, etc.).
- **Telemetry**: Structured events for audits; emits to console, pino logger, or hooks used by the service daemon.
- **Macro Stitcher**: Scans decoded manifests across days, groups compatible opcode families, and enforces mask drift tolerance (default ±1). Exported via `stitchMacroTracks` for CLI/daemon reuse.

### `services/daemon`
- Fastify app with:
  - **REST**: `/status`, `/tracks/:symbol`, `/tracks/:symbol/:date`, `/candidates/live`.
  - **WebSocket**: `tracks.live`, `tracks.symbol.<symbol>`, `telemetry.events`.
  - **Jobs**: BullMQ/Graphile worker to replay historical data, run manifest builds, or pre-seed catalogs.
  - **Sink adapters**: Writers for filesystem, SQL, Redis Streams, Kafka.
  - **Hook system**: configure “when track detected ⇒ POST to webhook / enqueue DB writer”.
  - **Macro Endpoint**: `/v1/macro` stitches decoded directories defined in `engine.config.yaml#macro`, writes `macro_tracks.json` per symbol under `data/power_tracks/`, and returns dashboard-ready summaries.

### `cli/`
- Node-based CLI (`pte`) using Commander + Ink (for TUI) to replicate PowerDecoder polish:
  - `pte init` – guided config writer.
  - `pte serve` – launch daemon with live logs.
  - `pte detect --file ...` – run batch detection on CSV/Parquet.
  - `pte monitor` – tail live detections via WS, display in Rich-like table.
  - `pte export` – dump tracks to Qlib-ready CSV (feeds Market-Power-Tracks use case).

### `python/pipeline_adapter`
- Thin client that:
  - Calls the service API for detection, or
  - Spawns the CLI with `--json` output and streams results back into the Makefile stages.
- Ships with helper scripts so `Power-Tracks-Pipeline` can drop-in replace stage 10/40/60 detectors with the shared engine.

## Service Deployment

- **Local**: `pte serve --config config/local.yaml`
- **Server**: Dockerfile + Compose definitions to run ingestion workers + API + DB sink.
- **Scaling**: Detector workers are stateless (subscribe to Polygon, push results to queue). Storage writers subscribe to queue for fan-out.

## Database Integration

- Default sink: SQLite (easy local).
- Production sink: Postgres/Timescale (AlgoRythym can read via SQL + listen/notify or via service API).
- Additional sink modules: ClickHouse, DynamoDB, S3 (for raw manifests).

## Security / Compliance Hooks

- API auth via API keys or OAuth proxy.
- Configured secrets (Polygon keys) pulled from environment.
- Audit log ensures every candidate has `provenance.inputs` (file hashes, websocket IDs, etc.).

## Integration & API

### NPM Package

The core package is published as `@powertracks/core` and can be used as a standalone SDK:

```typescript
import { PowerTrackDetector, PowerTrackStorage } from '@powertracks/core';
```

See [Core Package README](../packages/core/README.md) for usage examples.

### REST API

The daemon exposes a REST API with OpenAPI 3.1 specification:

- **OpenAPI Spec**: [docs/openapi/power-tracks-engine.yaml](openapi/power-tracks-engine.yaml)
- **Integration Guide**: [Core Integration Guide](core-integration-guide.md)

Key endpoints:
- `GET /v1/tracks` - List power tracks
- `GET /v1/tracks/path` - Get track price path
- `GET /v1/macro` - Get macro tracks
- `GET /v1/stream` - Server-sent events stream

### Python Client

Python client SDK can be generated from the OpenAPI specification:

```bash
openapi-generator-cli generate -i docs/openapi/power-tracks-engine.yaml -g python
```

See [Core Integration Guide](core-integration-guide.md) for Python usage examples.

## Current Focus

1. ✅ **CLI platform** – We standardized on the existing Node-based CLI (`cli/pte`, built with Commander + TypeScript) so engine pipelines, detector helpers, and daemon config parsing can be reused without a language bridge. Future command additions should continue to land in this workspace to keep the toolchain consistent.
2. ✅ **Internal queue** – Redis Streams is the default fan-out bus for detector events and macro backfills. The orchestrator components expect `REDIS_URL` (see `.env` example and `docs/end-to-end-setup.md`), so pending ingestion/batch jobs will publish detection payloads into `streams:powertracks:*` keys before downstream sinks consume them. Kafka/NATS remain future options but are not required for Sprint‑1 scope.
3. ✅ **Track persistence format** – Canonical storage remains human-readable JSON (per `data/tracks/<SYMBOL>_<DATE>_tracks.json`) plus mirrored artifact bundles under `storage/power_tracks/**`, while the SQLite snapshot store is used purely for query acceleration (`services/daemon/src/snapshots/trackSnapshotStore.ts`). Parquet is unnecessary until we tackle historical analytics exports.
4. ✅ **Python adapter packaging** – OpenAPI spec + generated TS/Python clients (`clients/`) cover this; see `docs/core-integration-guide.md`.
5. ✅ **Monitoring/metrics** – The daemon exposes `/metrics` via `prom-client` (see `services/daemon/src/server.ts`), and the progress tracker/runbook capture the Prometheus alert hooks. OpenTelemetry spans remain optional, but baseline metrics are live.
