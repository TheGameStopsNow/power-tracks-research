Power Tracks System — Full Technical Specification
==================================================

Overview
--------

Power Tracks is a comprehensive system for detecting and analyzing **Power Track** events in market data, and delivering those insights via APIs and a web-based Studio UI. It encompasses data ingestion, real-time detection, encoded burst decoding, multi-day macro track assembly, forecasting, and visualization. The system is architected to preserve **zero synthetic data** and full provenance of market inputs – all outputs are derived from real market ticks with no fabricated points[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L2-L5). It aligns with strict research guidelines for detection parameters (frequency band, threshold values) and ensures reproducible, deterministic behavior given the same inputs. Every detected track carries a unique ID (`PT-YYYYMMDD-HHMMSS-XXXX`) based on its timestamp to guarantee unique identification and ordering[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L66-L73)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L67-L75). The design goals are to provide a single audited implementation of Power Track detection and analysis that can be used in multiple modes (embedded SDK, standalone service, or CLI), maintain data integrity (no data leakage or mutation), and offer flexible integration points for other systems[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L5-L12).

At a high level, **Power Tracks** can be described as discrete bursts of market activity embedded with an encoded “instruction sequence.” Each burst (or **track**) is identified by a rapid sequence of trades with a concentrated spectral frequency (0.5–3.0 Hz) and a sharp price acceleration (≥0.7% in 5 seconds)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L10-L18)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L30-L37). These bursts carry structure: they are detected via frequency and ROC analysis, then **decoded** to reveal a series of frames containing opcodes, timestamps, prices, etc. Unfolding these frames yields predicted price paths (corridors) over multiple time horizons. The system distinguishes short-term intraday tracks from **macro tracks** that may span days or weeks. Macro tracks are assembled by linking related bursts over time (details in the Macro Model section). In all cases, the system enforces scientific rigor – for example, it warns or clamps parameters that deviate from research-approved values (e.g. minimum spectral power threshold 10,000, ROC 0.7%)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L9-L13). A multi-layered classification is applied to each track, labeling its **cluster type** (Impactor, Binder, Echo, Macro) and **regime** (“scripted”, “organic”, or “transitional”) once sufficient decoding metrics are available[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/openapi/power-tracks-engine.yaml#L132-L140)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/packages/core/README.md#L138-L143). Additionally, key metrics like **decodability** (D score) and signal-to-noise ratio are computed to characterize track quality and predictability (outlined later).

This document serves as the canonical technical specification for the entire Power Tracks system. It consolidates prior designs and research into a single source of truth for implementation. All architecture components – the Data subsystem, Core Engine, and Studio UI – are detailed, along with their interactions. We describe the full end-to-end workflow: from data ingestion and track detection, through decoding and unfolding of bursts, to orchestration of historical backfills and live streaming of results. We specify all APIs, data schemas, event formats, storage conventions, and integration points with other services. Validation metrics, testing strategies, failure modes, and deterministic behavior guarantees are included to ensure engineering teams can implement and maintain the system with confidence. The remainder of this document is organized into sections covering Architecture, Detection Algorithm, Decoding/Unfolding, Macro Model, Forecasting, Engine API, Studio UI, Orchestration, Streaming, Data Storage, Testing/QA, Deployment, and Appendices.

System Architecture
-------------------

### Component Overview

The Power Tracks system is composed of three primary subsystems, each focused on a stage of the workflow:

* **Power Tracks Data** (Data Pipeline): A Python-based pipeline responsible for **harvesting market data** from Polygon.io and staging it for analysis. This subsystem fetches raw trade ticks and aggregates (minute bars), ensures data completeness, and organizes the data in a standardized directory structure (or cloud storage) ready for detection and decoding. It provides a CLI (`pt-data`) with commands to harvest data, validate completeness, and sync artifacts to cloud storage[GitHub](https://github.com/TheGameStopsNow/power-tracks-data/blob/aabfb89e788ea236dee68d9153fd74907821b507/docs/data-pipeline-guide.md#L50-L59)[GitHub](https://github.com/TheGameStopsNow/power-tracks-data/blob/aabfb89e788ea236dee68d9153fd74907821b507/docs/data-pipeline-guide.md#L60-L62). The data pipeline does not itself perform Power Track detection; instead, it gathers and normalizes the inputs (tick files, etc.) and, optionally, invokes the engine to run detection/decoding on historical data via orchestration jobs. Configuration for this component is kept in `pt_data.yaml`, specifying Polygon API keys, storage paths, and Backblaze B2 (object storage) credentials[GitHub](https://github.com/TheGameStopsNow/power-tracks-data/blob/aabfb89e788ea236dee68d9153fd74907821b507/docs/data-pipeline-guide.md#L121-L129)[GitHub](https://github.com/TheGameStopsNow/power-tracks-data/blob/aabfb89e788ea236dee68d9153fd74907821b507/docs/data-pipeline-guide.md#L138-L146). The output of this stage includes raw tick data stored in files, minute-by-minute OHLC bars, and any preliminary manifests or partial outputs from legacy pipelines that can be consumed by the engine.
    
* **Power Tracks Engine** (Core Detection & Analysis Engine): A TypeScript/Node.js service (with some Rust or C++ extensions for FFT as needed) that performs **real-time Power Track detection, decoding, and analysis**. This is the core analytics engine. It can run as an embedded library (via an NPM package `@powertracks/core` for direct SDK use), as a long-running daemon with an API, or invoked via CLI for batch processing[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L5-L12). The engine ingests tick streams (either live via WebSocket from Polygon or from historical files) and runs a dual detection algorithm: a spectral power scan and a rate-of-change (ROC) threshold trigger. When a potential track (burst) is detected, the engine captures that tick window and immediately attempts to decode it (extracting the embedded frames). The engine then stores the results (both raw and decoded forms) to persistent storage and emits events for consumers. Architecturally, the engine daemon exposes a Fastify HTTP server with REST and WebSocket endpoints, and it uses a modular design with pluggable ingress and egress adapters[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L18-L24)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L38-L43). We describe the engine internals in detail in the next section.
    
* **Power Tracks Studio** (Visualization & Orchestration UI): A web application (Next.js frontend with a FastAPI backend) providing the **user interface and integration layer**. The Studio allows analysts and operators to visualize detected tracks, macro tracks, and forecasted trajectories in real-time, as well as manage backfills and data processing jobs. The Next.js **dashboard** presents interactive charts and tables: e.g., a Tracks grid showing recent detections (with filters by cluster type, severity, etc.), a Macro Tracks view to explore multi-day chains, and a composite forecast chart that overlays active track projections[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L42-L48)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/dashboard/components/CompositeForecastChart.tsx#L34-L42). The Studio also includes an **Orchestration page** where users can queue or monitor data processing tasks (harvesting data, running backfill detection, etc.)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L26-L34). Under the hood, the Studio’s FastAPI layer (referred to as the “API” service in Docker) acts as a proxy and cache between the frontend and the engine: it queries the engine’s REST endpoints (or reads directly from the database/filesystem) and merges in additional data like options analytics for a richer response. This API layer is also responsible for rate limiting and provides Server-Sent Events (SSE) for live updates to the frontend. The Studio is typically deployed via Docker Compose along with the Engine, a Postgres database, Redis cache, and MinIO (S3-compatible storage)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/end-to-end-setup.md#L201-L210)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/end-to-end-setup.md#L212-L219) – reflecting the full production stack.
    

These components operate in concert to cover the full workflow. In a typical deployment, **Power Tracks Data** will periodically fetch new market data (or receive it in near-real-time if integrated with a live data stream) and place it in shared storage. The **Engine** (running in daemon mode) will pick up live ticks directly from Polygon’s feed as well as utilize the staged historical data for backfills or macro analysis. The **Studio API** connects to the engine (via HTTP calls or even direct database access) to retrieve detection results and computed analytics, optionally caching them in Redis for performance[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L87-L95)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L96-L104). The **Studio Frontend** subscribes to a streaming endpoint to get push updates for new detections and state changes, enabling a real-time UI without constant polling[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L18-L25)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L19-L23).

### Engine Architecture and Modules

The Power Tracks Engine is the analytical heart of the system. It is designed as a modular, extensible core with multiple interface layers on top. The engine’s architecture can be visualized as follows:

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

**Interfaces:** At the top, the engine provides multiple interfaces. In **daemon mode**, it runs a Fastify web server that exposes a RESTful API (with endpoints for health, track queries, state, macro analysis, etc.) and a WebSocket endpoint for pushing events to clients[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L18-L24)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L56-L64). This allows integration with web UIs or other services via HTTP or real-time subscriptions. There is also a command-line interface **`pte`** (Power Tracks Engine CLI) which wraps common operations for operators – for example, `pte serve` to launch the daemon, `pte detect --file data.csv` to run detection on a file, `pte monitor` to tail live detections via WebSocket, and `pte export` to dump detected tracks to CSV[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L65-L73). Finally, the core engine is packaged as a library (`@powertracks/core` on NPM) so that it can be embedded directly into other JavaScript/TypeScript projects or even loaded in-process by the Studio’s Python backend via Node bindings if needed[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L99-L107). These interface layers all utilize the same underlying core logic.

**Core Engine:** The core of the engine (written in TypeScript, possibly with performance-critical parts in WASM or native code) is responsible for the primary logic of tick processing and detection. Key modules within the core include:

* **Detector** – Implements the sliding window detection algorithm (detailed in the next section). It ingests ticks (trades) and maintains an internal buffer (the current analysis window, e.g. 60 seconds of data). Every few seconds (configurable step, e.g. 10s), it computes the power spectral density and other features, checking for the Power Track signature. When a candidate burst is identified, the Detector packages the relevant data (tick window and computed metrics) as a **PowerTrackCandidate** object and emits a `'candidate'` event[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/packages/core/README.md#L42-L49)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/packages/core/README.md#L164-L171). The Detector also performs some validation (e.g. ensuring data is real and not missing) and basic quality checks (volume spikes, etc.) as guardrails[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L12-L16). All detection parameters are configurable via a **DetectorConfig** (with defaults matching research: 60s window, 10s step, 0.5–3.0Hz band, power ≥10,000, ROC ≥0.7%)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L30-L37)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L34-L42), and the engine enforces that these remain within allowed ranges (it can log warnings or adjust values if non-compliant, unless an override flag is set)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L9-L17).
    
* **Decoder & Unfolder** – Handles decoding the binary encoded burst once a track is detected. This involves converting the tick data (the rapid sequence of price changes) into a binary waveform and then interpreting that bitstream according to the Power Track protocol. The decoding process is described in detail in a later section; briefly, it searches for a correct XOR mask (0x00–0x1F) to decode bytes, parses varint-encoded fields from 56-bit frames, validates a CRC-7 checksum, and then **unfolds** the frames to reconstruct a price/time path (applying zig-zag decoding for signed values, scaling by volume codes, etc.)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L91-L100)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L128-L136). The engine’s decoder module outputs a structured result for each track: a sequence of decoded frames (with fields like opcode, timestamp offsets, duration scales, anchor prices, etc.) and the derived **unfolded price path** – essentially a series of predicted price points or ranges implied by the track. Unfolding uses the frames’ encoded instructions (like projection horizons and compression ratios) to place the track’s influence on a timeline. The core engine ensures no synthetic data is introduced in this process: the decoded price path (corridor) is built strictly from the recorded price changes observed in the track’s data, anchored on real prices[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L2-L5). (Any interpolation for visualization is done purely for plotting convenience and does not invent new points.)
    
* **Storage** – Responsible for persisting track data. Upon detecting and decoding a track, the engine writes out the artifacts to the **structured file system** and to the **catalog database**. By default, the engine will create a JSON Lines manifest in the file system under `data/power_tracks/<SYMBOL>/<TRACK_ID>/` containing the track’s details (this is called a **lag manifest**, which includes detection info and possibly lag sweep metrics)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L7-L14). It will also save the decoded frames and price path, often as JSON or CSV in the same directory. In addition, the engine can store the detection in an SQLite or Postgres **tracks** table for quick querying[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L42-L48). The Storage module abstracts these outputs: it can use different drivers – local FS, cloud object storage, SQL databases, etc. – based on configuration[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L49-L57). Every stored track includes metadata like the symbol, detection timestamp, cluster classification, and possibly an embedded snippet of the decoded data (or a hash reference to the file containing it). The engine uses unique track IDs and directory names to ensure no collisions and easy audit of what data corresponds to each detection.
    
* **Config & Schema** – The engine centralizes all configuration in a schema (using a schema validation library like Zod). This covers detection thresholds (window, freq band, etc.), data source settings, output paths, macro track stitching parameters, etc. On startup, the engine loads `engine.config.yaml` (or uses defaults) and validates it. This prevents misconfiguration – e.g. if a threshold is set too low or a required path is missing, the engine will fail fast with an error or apply a safe default[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L54-L58). The schema is also important for **determinism**: by having explicit values for each parameter, the engine ensures that running the detection on the same data with the same config yields identical results. The config includes a field for each known research constant (e.g., `power_thresh=10000`) so that these values are not hardcoded but remain transparent and adjustable (with guardrails).
    
* **Event Emitter & Telemetry** – The engine emits structured events for important occurrences. For example, when a new track is detected and stored, the engine will emit a `candidate` event with the track’s ID and summary[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/packages/core/README.md#L42-L49). It may also emit telemetry events like `telemetry` or `log` events for internal state, or alerts if data issues are encountered (like incomplete tick data). In the daemon mode, these events are bridged to WebSocket topics so external subscribers can receive them in real-time[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L58-L64). The telemetry events include details such as the track’s computed spectral power, ROC, decodability metrics, etc., and can be logged or consumed by monitoring systems. Prometheus metrics are also exposed (e.g., `powertracks_track_detections_total` labeled by symbol and regime, or `powertracks_feed_reconnects_total`) to facilitate operational monitoring[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/runbook.md#L10-L18)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/runbook.md#L12-L16).
    

**Ingress Connectors:** The engine supports multiple **data ingestion sources**. In live operation, the primary ingress is the Polygon WebSocket feed for trades: the engine subscribes to one or more symbols and receives a real-time stream of tick data. This live feed is the basis for real-time detection. If the WebSocket temporarily lags or misses data (e.g. due to rate limits), the engine can fall back to Polygon’s REST API to fetch recent aggregates or missing bars[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/data-architecture-analysis.md#L20-L29)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/data-architecture-analysis.md#L22-L30) – this ensures robust live operation (for instance, the engine’s `/v1/state` endpoint can use REST to get minute bars if it doesn’t find them in local storage[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/data-architecture-summary.md#L8-L16)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/data-architecture-summary.md#L9-L17)). For historical processing, the engine can ingest from **filesystem files**: it can read pre-harvested tick CSVs or Parquet files for a given symbol and date. This is used in backfill mode (e.g., `pte backfill --ticks-dir ...` to process past data)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/end-to-end-setup.md#L139-L147). Another connector is the **Pipeline adapter** – the engine can import already processed results from the legacy pipeline outputs. For example, if the older Python pipeline had produced intermediate files (like minute-level candidate lists or partially decoded frames), the engine can ingest those to avoid re-computation[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L40-L43). Finally, in a cluster deployment, multiple engine instances could partition symbols among them (using an allowlist per instance)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/runbook.md#L43-L51); each instance would subscribe only to its symbols’ feed to scale horizontally.

**Egress Destinations:** The engine is designed to broadcast or store results flexibly. Detected tracks are **persisted to disk** in a structured folder as described, and optionally inserted into **SQLite or Postgres** for query[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L41-L48). The engine can also push events to a **message queue or stream** – for example, publishing each detection to a Redis Stream, Kafka topic, or AWS SQS queue[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L38-L43). This decouples the engine from downstream consumers: AlgoRythym or other systems can subscribe to these streams to get notified of new tracks in real-time without polling. In the current design, a simple Redis Stream (e.g., `powertracks:tracks`) is planned for internal fan-out of detection events[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L12-L17). The advantage of using Redis Streams is that multiple consumers (like a database writer and a notifications service) can independently consume the events with their own offsets. Additionally, the engine’s **Hook system** allows configurable webhooks – e.g., “when a track is detected, POST it to this external HTTP endpoint” – which is useful for integrating with external alerting or storage systems[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L60-L63). Finally, macro track results are also stored both in files (`macro_tracks.json`) and inserted into the tracks database with a special flag (e.g., `detection_mode = 'macro_chain'`)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L42-L48)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L2-L5) so that they can be retrieved alongside normal tracks.

**Deployment Modes:** The engine can run in-process or as a standalone service. For local testing or embedding, one can import the `PowerTrackDetector` and related classes directly to process data in memory (SDK mode)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/packages/core/README.md#L16-L24)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/packages/core/README.md#L40-L48). For production, the typical deployment is the **Service Daemon**: running `pte serve` starts the Fastify server on a configurable port (default 4020) with all API endpoints enabled[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L56-L64). The daemon process can be Dockerized – a Dockerfile and docker-compose setup exist for running the engine along with its dependencies. In such a setup, multiple processes might be involved: one instance may handle the WebSocket ingestion and detection, while another might handle heavy storage writing or macro computation as a worker (the architecture mentions BullMQ or Graphile Worker jobs for things like replaying historical data or building macro manifests)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L58-L64)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L14-L17). This allows scaling: one can run several stateless detector workers in parallel (each gets ticks for certain symbols) and a separate set of storage workers that read from the Redis/Kafka queue to write results to the database or files[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L81-L89)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/runbook.md#L44-L51). The engine is stateless in terms of detection logic, so horizontal scaling is feasible as long as each tick stream is processed by one instance to avoid duplicate detections.

**Security & Compliance:** The engine includes basic security features such as API authentication (via API keys or an OAuth proxy in front)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L91-L95). In a production API deployment, all requests to modify data or retrieve sensitive info would require an `X-API-Key` header. The engine’s `.env` configuration supports storing secrets (like the Polygon API key) which the engine reads at startup[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/end-to-end-setup.md#L31-L38). As part of compliance, the engine logs an **audit trail** for each track detection, recording the provenance of the data used – e.g., the source of ticks (which Polygon feed or file, including file hashes or websocket message IDs if available)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L93-L96). The stored manifest for a track can include a `provenance` object with identifiers linking it back to raw data files or polygon query IDs, ensuring that any result can be traced back and verified. The principle of “zero synthetic data” is enforced here: since all track price paths are derived from actual trade data, the provenance info and hashing allow one to verify no tampering or fabrication occurred[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L2-L5). (A future improvement is to store the SHA-256 of the raw tick sequence for each track as part of the metadata.)

In summary, the Engine is a self-contained detection and decoding service, designed with modular inputs/outputs and rigorous data handling. Next, we delve into the detection algorithm and how a burst is identified and processed.

Detection Algorithm (FFT/ROC Hybrid)
------------------------------------

**Signal Definition:** A “Power Track” signal is characterized by a sudden, intense burst of trading activity with specific frequency and price-change patterns. In formal terms, it exhibits: (1) a **temporal concentration** – the event is confined to a short time window (anywhere from ~10 seconds up to at most ~10 minutes), (2) a **spectral signature** – a significant concentration of energy in the 0.5 to 3.0 Hz frequency range (reflecting a rhythmic or periodic component in the trade timing), and (3) a **rate-of-change acceleration** – a rapid price move of at least 0.7% within a few seconds, often accompanied by elevated volume[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L12-L20)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L30-L37). These criteria come from the Phase 1 research and form the basis of the detection algorithm.

**Sliding Window Scan:** The engine’s detector operates by scanning incoming ticks in a rolling window. By default, the window size is 60 seconds of data, and the detector advances (slides) this window every 10 seconds (the **step interval**)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L30-L37)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L38-L46). For each window, it performs an FFT-based spectral analysis and a parallel ROC calculation:

* _Frequency Analysis:_ The tick price series (or returns) within the window is analyzed using Welch’s method for spectral density. The power spectral density (PSD) is computed over the window (using, e.g., 256-point FFT segments)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L30-L38). The algorithm then **integrates the spectral power in the target band 0.5–3.0 Hz** – effectively summing the power of any periodic components with periods roughly between 0.3 and 2 seconds (since 1 Hz = 1 cycle/sec). A high band-specific power indicates a repetitive or oscillatory behavior in the tick data (which is hypothesized as an encoded signal).
    
* _ROC (Rate of Change):_ Concurrently, the algorithm computes the price change over a shorter sub-window (default 5 seconds) within that 60s window – typically looking at the first and last portion or doing a linear fit. It then calculates the **rate of change** as a percentage: `(Price_end - Price_start) / Price_start`. This must exceed the threshold (0.7%) to qualify[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L34-L42)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L46-L50). Additionally, some implementations also check for a minimum instantaneous spike (e.g., at least 0.5% jump at any moment)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L46-L50).
    

**Detection Criteria:** A window is flagged as containing a Power Track **candidate** if **both** the spectral power and ROC conditions are satisfied at the same time. In research terms: _spectral_power_band(0.5–3Hz) ≥ 1×10^4_ AND _ROC_5s ≥ 0.7%_[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L34-L42)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L44-L50). These values are configurable as `powerThresh` and `roc.threshold` in the engine config, but the engine will by default enforce these minima (with guardrails preventing lower values unless explicitly overridden for testing)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/packages/core/README.md#L194-L203)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L9-L17). When a window triggers the criteria, the detector takes note of the **timestamp of detection** (usually the end of that window, or the specific tick that caused the threshold crossing) and treats that as the moment a Power Track began.

**Candidate Extraction:** Once a detection event is triggered, the engine constructs a **PowerTrackCandidate** object. This includes:

* The symbol and timestamp of detection (often using the timestamp of the last tick in the window or the peak tick).
    
* The window of tick data that was analyzed (often extended a bit before and after to capture context). By default the system captures ±10 seconds around the detection point (so potentially a 20s snippet, ensuring some lead-in and aftermath)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L54-L61). This is sometimes referred to as **pre-burst** and **post-burst** capture for context.
    
* The computed metrics: spectral power value, the ROC value, possibly SNR (signal-to-noise) if calculated, and any quality heuristics. The research spec expects SNR ≥ 15 dB and completeness checks, but in the current engine these are not fully implemented – a simplified quality check or volume spike detection may be noted instead[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L12-L16). Future versions plan to compute SNR and venue coverage at this stage.
    
* A unique track ID, generated as described (the prefix `PT-` with date-time and a random or sequence suffix)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L66-L73). This ID tagging happens here so that all subsequent references (filename, database) use this consistent ID.
    

At this point, the candidate is emitted as an event (`'candidate'`) internally[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/packages/core/README.md#L42-L49). The engine’s event loop ensures that detection is **single-threaded per symbol stream** – meaning within one symbol’s tick sequence, it won’t emit two overlapping tracks; it will mark one and then ignore further triggers until the current one is processed (this avoids double-detecting the same burst). However, tracks on different symbols are processed independently (and possibly in parallel if separate tasks or threads are assigned per symbol). The deterministic nature of the algorithm (no randomness in FFT or thresholds) means given the same tick sequence, the same window will always trigger at the same point.

**Buffering and Data Enrichment:** Upon detection, the system may retrieve additional data related to the burst:

* It confirms **venue completeness** by checking if all expected venues (exchanges like EDGX, CBOE, etc.) were present in the tick data. The system is designed to ingest multi-venue data if available (the data pipeline can include off-exchange/OTC trades as well). If any known feed was missing data during the burst, that can be flagged (though currently not all completeness metrics are enforced)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L56-L65).
    
* It might also mark any anomalies: e.g., if there were exchange delays (latency) or if the tick count is lower than expected for that period, that could reduce confidence.
    
* The candidate object may also include a **volume spike indicator** or a measure of volume during the burst compared to baseline, as part of quality metrics.
    
* The system ensures that the **tick data snippet** for the burst is saved (this raw data is needed later for decoding the burst). This snippet often forms the content of a “raw ledger” file in the track’s `raw/` artifact folder[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-refactor-plan.md#L10-L17).
    

Finally, the engine’s state resets the detection window after capturing a track – in practice, once a track is detected at time T, the detector may impose a short refractory period (e.g., don’t trigger again for a few seconds) to avoid picking up the same burst twice as the window slides. Alternatively, it will slide the window past the burst. This ensures distinct tracks are well-separated.

**Venue and Quality Checks:** The research specification included requirements like cross-venue synchronization and tick completeness (≥99% ticks present)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L60-L67). The current engine does basic validation (e.g., no NaNs in data, presence of ticks) via a `validateRealData` function[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L14-L16), but does not yet enforce a detailed completeness or SNR check (that is noted as a to-do in the audit)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L12-L16)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L14-L16). However, the architecture is ready to incorporate these: the detection pipeline could compute SNR of the signal (perhaps comparing power in the target band vs power in other bands as noise) and store it in the metrics. It could also compare the tick count in the window to reference data (expected number of ticks for that interval given known market data rates) to estimate completeness. For now, such fields (e.g., `snr` or `venueCompleteness`) might be left null or at default, but the structures exist to populate them.

**Research Guardrails:** To remain scientifically valid, the detection uses hard-coded minima and warns on non-compliance. For example, if an integrator tries to run the detector with a 30-second window or a ROC of 0.5%, the engine will log that this is outside research-approved settings and either adjust it or require an override flag[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L9-L17). There’s an environment variable `ALLOW_NON_COMPLIANT_THRESHOLDS` which if set, will let the detector run with experimental values (useful for unit tests or exploring alternate parameters)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/packages/core/README.md#L212-L219), but otherwise it defaults to enforcing the standard values. This ensures consistency with published research results.

**Output of Detection:** The outcome of the detection stage is a _detected track candidate_ with: time of detection, symbol, basic metrics (spectral power, ROC, quality flags), raw tick sequence (for decode), and a preliminary classification. At this point, the track is often labeled with a **cluster type** if obvious from context – e.g., extremely large amplitude events might be tagged as “Impactor”, repeated daily bursts might be “Binder”, echoes following an impact could be “Echo”, etc. Initially, many tracks may be “unclassified” or have a provisional label; deeper classification can occur after decoding and analyzing the content (described in Regime Detection later). The candidate then flows into the next stage: decoding the burst.

Decoding and Unfolding of Track Bursts
--------------------------------------

Once a Power Track burst has been detected and isolated, the next step is to **decode the embedded message** contained in that burst. This involves converting the raw price/time data of the burst into a binary bitstream and interpreting it according to the assumed encoding scheme from the research. The decoding process is complex but deterministic, consisting of several sub-steps: waveform processing, bit conversion, frame parsing, and then unfolding the frames to a readable outcome.

**Waveform to Bitstream Conversion:** The raw burst is essentially a series of tick timestamps and prices. The research suggests that the burst encodes information via precise timing and price changes. The engine first normalizes this data into a form suitable for binary interpretation:

* **Resampling:** Ticks are timestamped to the millisecond or better. The engine resamples or interpolates the tick data onto a uniform high-frequency timeline (for example, 1 kHz = 1 sample per millisecond)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L79-L86). This may involve holding the last price constant between trades (zero-order hold) to fill gaps, so that we have a continuous time series.
    
* **Envelope Extraction:** Using the analytic signal technique (Hilbert transform), the engine computes the amplitude envelope of the price series[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L79-L86). Essentially it finds the instantaneous magnitude of price oscillations, highlighting where significant pulses occur.
    
* **Thresholding:** The envelope is then run through an adaptive threshold – typically the 15th and 85th percentile values of the envelope serve as low and high thresholds[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L79-L86). Everything above the high threshold is considered a “pulse” (bit = 1) and everything below the low threshold is considered no pulse (bit = 0). The region between may be uncertain; an algorithm might use hysteresis or just set intermediate values to whichever side they lean. The key is to derive a binary pulse train from the analog waveform.
    
* **Debouncing:** Very short pulses (e.g., glitches or noise spikes shorter than a certain duration, like 200 microseconds) are likely not real encoded bits but microstructure noise[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L82-L90). The decoder applies a debouncing filter, removing any pulses that are too brief to be intentional, thereby cleaning the pulse train of spurious flips.
    

After these steps, we have a binary time-series representing pulses in the burst. For example, a sequence might look like _1011001110..._ with irregular spacing depending on the timing of trades.

**Frame Extraction (56-bit frames):** According to the research specification, the binary stream is organized into frames of a fixed total length (56 bits) comprising a header and a payload:

* Each **frame** is 56 bits which includes: a 6-byte (48-bit) header, plus a 1-byte (8-bit) trailer containing a CRC and stop bit[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L128-L136)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L149-L157). The header fields are bit-packed as:
    
    * Opcode (6 bits) – identifies the type of instruction or data in this frame (like an operation code).
        
    * Version (2 bits) – protocol version.
        
    * Start Timestamp (16 bits) – a relative timestamp for the start of this frame’s effect, likely measured from the session start (e.g., in seconds or smaller units).
        
    * Duration Scale (6 bits) – a scaling factor for how long this frame’s effect lasts.
        
    * Compression Ratio (2 bits) – indicating if time is compressed (like an encoding of time jump).
        
    * Anchor Price (8 bits) – a base price reference (probably in minor units like cents).
        
    * Volume Code (6 bits) – a code representing volume or an order of magnitude of volume associated.
        
    * Parity (2 bits) – likely parity bits for error checking beyond CRC.
        
    * Finally, the **trailer byte** has a 7-bit CRC (for error detection) and a 1-bit frame terminator (stop bit)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L149-L157)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L136-L144).
        

The decoder must identify frame boundaries in the bitstream. There is likely a known pattern or preamble that helps align to the 56-bit boundary. In practice, because the frames are back-to-back, the decoder might rely on the stop bit and CRC: it can slide a 56-bit window along the bitstream and check if any 7-bit CRC at the end validates the preceding 55 bits as a proper frame (given the CRC polynomial). It tries possible alignments until the bits parse correctly with a valid CRC. The research spec calls for testing masks which ties into this alignment (next step).

**Mask Search (XOR key discovery):** The captured binary pulses might be XOR-masked with a certain 6-bit key to obfuscate the actual bits. Research indicated trying masks from `0x00` through `0x1F` (i.e., 0 to 31 in decimal)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L91-L100). The decoder will attempt to decode the frames under each candidate mask:

* It XORs the entire bit stream (or maybe each byte) with the mask and then tries to parse frames. For each mask, it will perform varint decoding of payloads and check plausibility.
    
* Heuristics guide mask selection: The “correct” mask likely yields frames where the payloads decode into reasonable values (e.g., number of varints in range, timestamps monotonic, etc.). The engine scores each mask based on criteria: proportion of frames that decode without error, how many varint values are within expected ranges, etc[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L97-L105)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L101-L110).
    
* The mask with the highest score above a threshold (e.g., must decode >25% of frames validly) is chosen as the correct mask[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L101-L105). If none pass the threshold, the track may be marked as “undecodable” or gets a low decodability score (D).
    

During mask testing, the decoder specifically does:

* **Varint decoding** of the frame payload under each mask: The payload portion of each 56-bit frame is varint-encoded data. The engine attempts to interpret it with 7-bit continuation (i.e., each byte’s MSB indicates if more bytes follow)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L91-L100)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L111-L119). This yields numeric values that should correspond to things like time offsets or price differentials.
    
* **Validation scoring:** For each mask, it tallies:
    
    * The fraction of frames that yielded entirely valid varints (no missing continuation, etc).
        
    * **Timestamp monotonicity:** If frames carry time offsets, decoding with the correct mask should show these offsets increasing or at least making sense (e.g., if one frame starts at 10:00 and duration 5min, next shouldn’t start at 9:50).
        
    * **Price plausibility:** Using the anchor price and subsequent deltas from varints, the resulting price path should be plausible (no huge jumps that are impossible).
        
    * The number of varint values per frame falling in an expected range (the research suggests typically 3–20 values per frame is normal)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L97-L105).
        
* The mask with the highest aggregate score that meets minimum criteria (score > 25% typically) is selected[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L97-L105). If a mask passes, the assumption is it correctly decoded at least a quarter of the frames, which gives confidence it’s the right one.
    

After choosing the XOR mask, the decoder now can finalize parsing of all frames with that mask. Frames with failing CRC or impossible fields might be dropped or flagged, but ideally most frames decode.

**Varint & Zigzag Decoding:** The payload varints themselves often encode signed numbers (like price differences). The engine applies **zig-zag decoding** on varints to recover signed values[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L111-L119). Zig-zag is a standard method where the least significant bit of the encoded number indicates sign (0 for positive, 1 for negative), and the remaining bits give magnitude (with a bit-shift): `decoded = (n >> 1) ^ (-(n & 1))`[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L113-L121). This yields positive and negative integers from the originally unsigned varints. Using this, the engine obtains:

* Price changes (some varints likely represent deltas from an anchor price).
    
* Time durations (some varints represent time lengths or offsets; these could be encoded in microseconds or some compressed form).
    
* Volume or other quantities (if any).
    

**Assembling the Decoded Frames:** At this point, each frame can be represented as a structured object:

```
Frame {
  opcode: <number>,
  version: <number>,
  start_time: <some unit>,
  duration: <some unit>,
  compression: <factor>,
  anchor_price: <price>,
  volume: <code>,
  fields: [decoded varint values...],
  crc_ok: <bool>
}
```

For frames where CRC failed or something didn’t parse, the engine might exclude them from further analysis. The decoding process, if successful, yields a sequence of frames sorted by their intended start times (which ideally align with chronological order of detection, but could have overlaps or gaps).

**Lag (7-4-1) Structure & Unfolding:** The research mentions a “7–4–1 lag cadence with projection limits”[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L22-L26) – this likely refers to how far out each frame projects the price, and how multiple frames might be structured (7-day, 4-week, 1-quarter projections, for example). The engine’s decoder takes each frame and **unfolds** it into concrete price points on a timeline:

* Using the **start_time** and **duration_scale**, the engine calculates when that frame’s effect ends. For instance, if a frame starts at T0 (relative to track detection) and has a duration code indicating “4 units”, perhaps that means 4 days. The engine would then mark that frame as covering T0 to T0+4 days.
    
* Within the frame’s payload, certain varint sequences may encode intermediate target prices or adjustments at specific sub-intervals. For example, an opcode might mean “project an exponential decay in price from anchor to anchor - X over Y time”. The engine knows how to interpret each opcode’s payload to derive a series of time-price points.
    
* By doing this for each frame, the engine builds an **unfolded price path** for that frame – essentially a set of timestamped price points that represent the price trajectory implied by that frame.
    
* Critically, if multiple frames are part of a single track, they likely represent different time-horizon effects: e.g., one frame could be short-term (7 days), another medium (4 weeks), another long (1 quarter). The engine combines them to form an overall **price corridor**. Typically, the shorter frames might refine the path within the longer frame’s envelope.
    

**Corridor Envelope:** The output is often represented as a **corridor** with upper and lower bounds (this term appears in macro context as well). As frames might define a min/max envelope of price, the engine can derive an upper bound series and lower bound series over time. For instance, if frame A says price goes from $100 to $110 in 7 days, and frame B says from $100 to $105 in 4 days, then for the first 4 days frame B’s prediction is tighter (lower upper bound), after day 4 up to day 7 frame A’s broader prediction holds. The combined effect is a piecewise envelope.

In implementation, after decoding, the engine often writes out:

* The **lag manifest**: a JSON containing the list of frames decoded and some summary info (like timescales/times covered by each). This was historically called `lag_manifest.json` per track[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L7-L14).
    
* The **unfolded path**: possibly as a CSV or JSON of time vs price vs high vs low.
    
* Possibly **visual artifacts**: the engine could generate a spectrogram image of the burst or other diagnostics (the pipeline plan mentions storing spectrograms under visuals/).
    

**Error Handling in Decoding:** Not all bursts will decode cleanly. If no mask works, the track is considered **undecryptable** – it might still be stored for record, but its decoded frames list will be empty or marked invalid. The engine assigns a **decodability score D** to every track indicating how well it could be decoded[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L38-L44). For example, D might be based on fraction of frames decoded and entropy measures (the research suggests using spectral bandpower, permutation entropy, varint success rate as inputs)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/packages/core/README.md#L130-L139). A perfectly decoded track gets a high D (close to 1 perhaps), whereas an indecipherable one gets 0. A threshold D* (D-star) may be defined as the minimum acceptable decode confidence; tracks below D* might be flagged as “weak” and possibly ignored in macro analysis[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L38-L44). (As of the latest audit, this D/D* calculation was not yet exposed via API, but the engine computes it internally when possible[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L40-L44).)

Additionally, the engine classifies the **regime** of each track post-decoding. By analyzing the permutation entropy of the price sequence and other factors, it can label a track’s market regime influence: **scripted** (highly algorithmic, predictable pattern), **organic** (random or naturally occurring), or **transitional** (mix)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L38-L44)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L40-L44). A fully decoded track with low entropy and high structure might be “scripted”, whereas a track that appears but doesn’t decode might remain “unclassified” or default to “organic”. This regime classification ties into how the track is displayed (e.g., maybe color-coded in UI) and is part of the track metadata.

**Example:** Suppose a track is detected on GME at 10:30:00 with spectral power 15000 and ROC 0.8%. The raw burst from 10:29:50 to 10:30:30 is processed. The decoder finds that with XOR mask `0x0E`, it can parse 3 frames out of 4 with valid CRC and plausible data. The frames decode to:

* Frame1 (opcode 5, version 1): start_time=0, duration_scale=2 (meaning 7 days perhaps), anchor_price=$1600 (in cents, $16.00), volume_code=10. Its payload indicates target +5%.
    
* Frame2 (opcode 3, version 1): start_time=0, duration_scale=1 (meaning 4 hours maybe), anchor_price=$1600, volume_code=8. Payload indicates short-term drop -2%.
    
* Frame3 (opcode 9, version 1): start_time=120 (2 minutes later), duration_scale=0 (meaning 30 minutes), anchor_price=$1580, volume_code=8. Payload indicates small oscillation.  
    Frame4 fails CRC and is dropped.
    

The engine unfolds these: Frame1 suggests an overall +5% move in a week. Frame2 suggests an immediate -2% dip in first 4 hours. Frame3 suggests a volatility pattern in first 30 minutes. Combining: it produces an unfolded path that drops 2% then oscillates, then trends upward to +5% by week’s end. The track’s decodability is high since 3/4 frames decoded; D might be ~0.9, above D* threshold. The regime might be “scripted” because the pattern is very structured (low entropy in payload). The engine stores all this in the track’s manifest and also computes a **composite severity** or **magnitude** for the track (maybe based on spectral power and price impact). This severity is used to rank tracks or filter by “Pass Level” etc. (In the UI and API, one can filter tracks by severity or cluster type.)

In summary, decoding translates the initially inscrutable burst into actionable information: time-bound forecasts (encoded in frames) and metadata that can feed into the macro analysis. The next section will discuss how multiple tracks can be combined into macro tracks and how the model has evolved to treat macro-scale patterns.

Macro Tracks Model (Revised Burst-Based Approach)
-------------------------------------------------

Macro Tracks refer to multi-day or long-horizon patterns formed by chaining together Power Track bursts that appear to be part of a larger sequence. Originally, the system’s approach to macro tracks was **chain-based**: it would look at decoded tracks across consecutive days and attempt to “stitch” them if they belonged to the same **family** (e.g., shared an opcode sequence or a decoding mask) within a tolerance. The older method grouped track segments by attributes like symbol and some family identifier (perhaps derived from the opcode or frame content version) and then linked them if they occurred within certain gaps, allowing a small “mask drift” (like if the XOR mask changed by ±1 between days, it still considered them part of the same chain)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L12-L19). The output was a stitched chain of daily tracks forming a longer trajectory, labeled with `cluster: 'macro'`.

**Revised Burst-Based Model:** The new model replaces this with a more **burst-centric reassembly** that works at the tick/data level rather than just post-hoc manifest linking. The approach is as follows:

* When a Power Track is detected and decoded on a given day, the engine not only stores it but also keeps its **decoded signature** (this could be a simplified representation of the frame sequence or the pattern of pulses).
    
* The system defines a forward-looking **active window** for macro continuation. For example, after a track on Day1, it might consider the next 5 trading days as a window in which a continuation burst might occur. Only future days are considered (forward-only), meaning we don’t try to link backwards or out of order – this prevents arbitrary matching and ensures the macro track is a chronological sequence.
    
* On each subsequent day within that window, the first time a new track is detected for that symbol, the engine will compare its characteristics to the prior track’s. If certain **alignment conditions** are met, it will treat it as part of the same macro track. These conditions can include:
    
    * **Decode-time alignment:** If both bursts were decoded, do their frames line up in a logical way? For instance, if Track1’s last frame projected out 7 days, does Track2 occur within that projection and perhaps represent a refinement? Or if Track1 ended with a certain anchor price, does Track2’s anchor or start price coincide with that? Essentially, the content of the decoded messages are checked for continuity. This is a deeper criterion than the older method which might have just matched “family” or mask; here we inspect the actual decoded instructions.
        
    * **Mask or Opcode similarity:** If the tracks are not fully decoded or to double-check, we verify that the opcode patterns or mask keys are compatible. E.g., if Track1 used mask 0x0E and Track2 used 0x0F, that’s a drift of +1 which might be acceptable. Or if both have an opcode sequence starting with 5 then 3 then 9 (like in the example above), that’s a strong hint they are part of one macro scenario.
        
    * **Temporal gap tolerance:** Ensure the gap between Track1 and Track2 is within an expected range (no larger than, say, 5 trading days unless a frame explicitly projected that far).
        
* If a new track meets the criteria, it is **attached to the macro track** as the next segment. Internally, the engine will mark them as linked. If it does not meet criteria, then the macro sequence is considered ended and a new macro sequence would start.
    

This burst-based reassembly essentially constructs a macro track incrementally, day by day, rather than after the fact. It treats each day’s detection as either belonging to an ongoing macro or as the start of a new macro. This contrasts with the older retrospective stitching which would scan all decoded files in a date range to find chains after the fact[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L12-L19).

**Active Window Forward-Only:** The phrase “forward-only active windows” emphasizes that the macro linking does not go backwards in time and does not reconsider groupings once time moves on. For example, if you have tracks on Jan 1 and Jan 5 and they link, that’s one macro track. If Jan 3 had none, that’s fine. But if Jan 7 sees another track that aligns, it can extend the macro track forward. It would not try to link something from Dec 30 after Jan 1 has started a macro. This simplification ensures macro tracks are anchored at a start date and grow forward until no continuation appears within the allowed horizon. It avoids the ambiguity of possibly circular linking or needing to choose the “best chain” among overlapping possibilities.

**Decode-Time Alignment:** This is the key upgrade. It means the decision to chain tracks uses the decoded content, not just detection metadata. Concretely:

* If Track A’s decoding yielded a projected price at Day B that matches (within epsilon) the actual price at which Track B was detected, that’s a strong alignment signal. Possibly the encoded instructions anticipated a movement that indeed happened when the next burst occurred.
    
* If Track A’s frames indicated, say, a “flip” or turning point expected at a certain time, and Track B’s burst corresponds to that time, this suggests track B is the fulfillment or continuation of track A’s script.
    
* The engine may align by adjusting for overnight gaps. For instance, if a frame’s “start_time” in Track B’s decode is slightly offset but essentially picks up where Track A left off (taking into account that markets closed and reopened), the engine will align those in the macro timeline.
    

Under the hood, the macro stitching algorithm can replay each track’s **price path** and see if the end of one path connects smoothly to the beginning of the next[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L14-L19)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L16-L19). When it finds a chain, it records the chain segments.

**Mask Drift Tolerance:** We still allow a small drift in masks or other low-level parameters between segments. The default tolerance remains ±1 on the mask key difference[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L52-L54)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L53-L54) (meaning if one day’s track used mask 0x0E and the next used 0x0F, it won’t break the chain). This accounts for the idea that the encoding might shift slightly over long periods (perhaps intentionally to avoid detection or due to sampling differences).

**Macro Track Assembly Output:** When a macro track is identified, the engine (or the orchestration process) produces:

* A combined **corridor path** that spans the entire macro horizon. This is built by merging each segment’s unfolded path. Practically, if each daily track had an envelope for its projections, those are concatenated chronologically, but also note that when one segment ends the next begins, there might be an overlap day where both had projections – in such case, the later track’s data supersedes or refines the earlier. The result is one continuous path from the start of the macro to its end, with possibly different confidence bands at different sections.
    
* Metadata for the macro: start date, end date, how many segments (days) were stitched, and the parameters used (minDays, mask drift, etc).
    
* A list of the constituent **track IDs** that formed the macro chain, for traceability[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L14-L19). This is stored in the macro output so we know which individual detections were linked.
    
* The macro track is given a new unique ID or simply uses the first track’s ID as a base. In practice, the system might insert a row in the database with `detection_mode = 'macro_chain'` that contains a JSON payload of the whole chain[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L42-L48). The `tracks` table can thus hold macro tracks alongside intraday tracks (distinguished by that field).
    

The engine also writes a `macro_tracks.json` file per symbol, which is essentially a cache of the latest macro chains for that symbol[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L40-L48). Each time the macro stitching is run (manually or via API), this file is updated with the new chains found. Studio can load this file for offline analysis or use the API.

**Macro API and Usage:** The Engine daemon provides an endpoint `GET /v1/macro` to trigger macro track stitching on-demand[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L22-L29). One can specify query parameters like `symbol`, `start`, `end` to limit the date range considered, as well as `min_days` (minimum number of segments to consider a valid macro) and `mask_drift` tolerance[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L24-L31). The endpoint returns a JSON including:

* `tracks[]`: an array of stitched macro tracks. Each macro track in the array includes the list of segments (with their dates and track IDs), the combined corridor path (down-sampled for plotting), and summary metrics.
    
* `available_dates` and `used_dates`: diagnostics indicating which dates in the range had track data and which of those were utilized in the macro chain[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L26-L34).
    
* An echo of the config parameters used (so that the UI knows the assumptions).
    

The CLI has an equivalent `pte macro` command to run this locally, with `--lookback` defaulting to 180 days[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L34-L38). In local mode, it can output the macro JSON to console or file.

**Macro Detection vs. Replay:** The system can run in two modes:

* **Live Macro Updates:** The idea is that as days progress, the macro track can extend. For instance, each morning the engine (or orchestrator) could automatically stitch macro tracks including the previous trading day. This could potentially alert if a macro pattern is continuing. In practice, one might run a cron job to call `/v1/macro` each evening or morning.
    
* **Historical Macro Stitching:** One can retrospectively generate macro tracks for past data by specifying a date range. This is useful to populate the database with all macro tracks over the last N months for analysis. The `scripts/generateMacroTracksJsonl.ts` was provided to assist in generating daily `tracks.jsonl` files (decoded track indexes) from pipeline outputs, precisely to facilitate macro stitching across historical data[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/end-to-end-setup.md#L123-L131)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/end-to-end-setup.md#L127-L135). This script reads the existing daily lag_manifests and writes a consolidated `decoded/<DATE>/tracks.jsonl` which lists all tracks that day with essential info. The macro stitcher then uses those JSONL files as input for stitching.
    

**Comparison to Old Model:** In the older chain-based model, macro tracks were determined by grouping by family and then applying mask drift and minDays, but that process didn’t leverage the actual price path alignment as strongly. The revised model’s advantage is a more **causally consistent chain** – we only chain if decode content aligns, which should reduce false chains. It also allows for dynamic extension of macros as data comes in, rather than doing a heavy scan each time (though internally, `/v1/macro` still scans decoded files, it is more direct because it knows what to look for). The chain logic ensures macro tracks can span up to the configured `defaultLookbackDays` (e.g., 180 days) but no more unless specified[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L34-L38)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L62-L70).

**Macro Track Example:** Suppose we had tracks detected on 2025-01-10, 2025-01-13, and 2025-01-18 for symbol XYZ. The first one’s decoded frames indicate a long-term upward move with a critical point around the 13th. Indeed on the 13th, another track appears which seems to pick up on that (its anchor price is exactly where the first predicted). These two get chained. The third on the 18th is slightly outside the projection of the second (maybe the second had a horizon to 15th only). However, if the content of the third matches the overall trend (mask difference within tolerance and projecting further up), the system might still chain it if `maskDriftTolerance` allows and minDays is met. Let’s say `minDays=3` so it needs at least three segments to consider it a full macro track[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L14-L19)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L62-L70). In this case, all three join into one macro track spanning Jan 10 to Jan 18 (which is 3 segments over 8 calendar days, possibly 6 trading days). The macro track corridor is built from Jan 10 onward. The macro summary might show “stitched_count: 3” segments, and correlation if calculated (the engine could compute how correlated the price movements of segments were – e.g., did each segment move in the same direction as expected; the openapi defines a `correlation` field for macro track)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/openapi/power-tracks-engine.yaml#L182-L190)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/openapi/power-tracks-engine.yaml#L184-L191). The macro’s `cluster` is labeled 'macro', and it might also carry a severity (perhaps cumulative). This macro gets stored as an entry in the database and can be shown in the UI as a single row with an expandable list of segments.

**Technical Implementation:** The macro stitching logic is implemented in the engine’s `MacroStitcher` module (TypeScript), which reads daily track manifests and tries to build chains[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L12-L19). When the macro endpoint is called, it loads all track candidates from the configured `decodedRoots` directories (which typically include `ENGINE_DATA_PATH/power_tracks/<SYM>/decoded/` directories of JSONL files)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L62-L70)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L70-L73). It then groups those by family/version internally and checks sequences. The MacroStitcher enforces at least `minDays` days in a chain and that each consecutive pair satisfies `maskDriftTolerance` (default 1)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L14-L19). It then calls a corridor extraction function which essentially replays each track’s price path in sequence to build the combined corridor[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L14-L19)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L16-L19). In the code, after forming a macro, it also inserts that macro into the SQLite/PG `power_tracks` table with `detection_mode='macro_chain'`[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L42-L48). The macro is given an entry such that it can appear in the same list as individual tracks if needed.

**Usage in Studio:** In the UI, Macro Tracks are surfaced in two ways: (1) On the main tracks table, a user can toggle “include macro” which will include macro tracks (those with detection_mode macro) alongside intraday ones[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/end-to-end-setup.md#L212-L219). They might be highlighted differently (since they span multiple days). (2) There is a dedicated Macro view or dashboard card where one can fetch the macro corridor via the API and display the price envelope chart[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L50-L59). In that chart, usually the **aggregate corridor** (combined macro path) is plotted as a bold line or area, and each segment’s own corridor can be drawn in lighter lines to illustrate how they overlap[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L54-L59). The UI also likely shows the date range the macro covers and any drift parameter. If the macro segments had different masks, the drift used would be shown (e.g., tolerance = ±1 used).

With the macro model explained, we can now address the forecasting logic that builds on these tracks (micro and macro) and external data to predict future price movements.

Forecasting and IVCM Logic
--------------------------

The Power Tracks system includes a forecasting component, often referred to internally as **IVCM** (Implied Volatility Corridor Model). This is a forecasting algorithm that uses the information gleaned from active power tracks (and potentially options market data) to project an expected price trajectory with confidence bounds for the near future. The goal is to synthesize all current signals (like active intraday tracks, any macro track influence, and volatility context) into a single cohesive forecast that can be visualized as a **composite forecast** in the Studio.

**Inputs to Forecast:**

1. **Live State Data:** The current market state for the symbol – this includes recent price bars (OHLC data, e.g., last few hours or days) and indicators derived from them. The engine or studio backend compiles a state payload with arrays of timestamps, opens, highs, lows, closes, etc., as well as technical indicators like ATR (Average True Range) and potentially Bollinger bands (upper/lower) or similar[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L636-L644)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L651-L659). This state payload may also include the latest decodability (D) series and entropy values computed for recent data windows[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L641-L649)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L653-L661).
    
2. **Active Power Tracks:** A list of currently active track influences. If one or more power tracks have been detected and not “expired” yet (e.g., within the last day or within their projected horizon), those are relevant. Each such track has a projected path (from its decoding) that could influence the forecast. The system classifies tracks by lifecycle: active or dormant[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/dashboard/components/CompositeForecastChart.tsx#L94-L101)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/dashboard/components/CompositeForecastChart.tsx#L99-L105). Active tracks might be those whose projected end time is still in the future.
    
3. **Options/Volatility Data:** The “IV” in IVCM suggests using Implied Volatility data from the options market. The engine can fetch an **options hinges** snapshot (which might include key points like where gamma exposure is highest, or implied volatility levels at certain strikes – often these are called “hinges”)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L66-L74)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L68-L71). The API has an endpoint `/v1/options` or `/v1/options-hinges` which provides a summary of the options landscape (like major open interest strikes, etc.)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L66-L74). The forecast algorithm can use this to adjust confidence bounds or anticipate mean-reversion levels.
    
4. **Historical Patterns:** The system can incorporate learned behavior, for example, previous forecasts vs actual outcomes to calibrate confidence. This is more advanced and ties into the **calibration** endpoint – which computes how often past forecasts’ confidence intervals captured the real moves[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L760-L769)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L770-L778). The calibration payload includes coverage percentage of actual closes within prior forecast bands, average band width, etc. The forecast logic may use this calibration to adjust current confidence (for instance, if historically the bands were too narrow, widen them).
    

**Composite Forecast Computation:**  
The forecasting logic is implemented in the Studio API (FastAPI) as `compute_forecast_payload`, which takes the current state payload as input[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L8-L11)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L8-L11). It produces a forecast output that includes:

* A **history** list: key recent points (with timestamp, actual price, and possibly the existing upper/lower bands from state)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L644-L652)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L653-L661). This basically repackages recent actual data with any existing band (e.g., Bollinger band or envelope).
    
* A **path** list: a sequence of forecast future points, each with a timestamp (`ts`), a projected value, and an upper and lower bound, plus a confidence value[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L680-L689)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L686-L694).
    
* A **horizon_minutes** indicating how far out the forecast goes (e.g., 15 minutes, 60 minutes, etc)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L702-L708).
    
* A **tracks** summary: this is essentially which track influences were considered. In the current implementation, they sometimes include a “Composite” track with weight 1.0 and a confidence figure[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L708-L716). In a more advanced scenario, if multiple tracks were active, this array could list each with a weight (how much it influences the forecast) and confidence in each. For now, it often just lists one composite track of combined influence.
    
* **spot**: the last known price (current price)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L714-L718).
    

How is the forecast path generated? The current logic (IVCM v1) takes a fairly straightforward approach:

* Determine the **price trend** in recent data. Typically by linear regression or difference: the code calculates a `slope` by polyfitting the last N closes (where N might be 20)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L666-L673). This slope represents a simple trend (units: price change per step, where a step could be one minute as coded).
    
* It sets a forecast horizon, e.g., 15 minutes (horizon=15)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L664-L671).
    
* It uses the last close price as a starting point (`last_close`)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L664-L671).
    
* For each minute step from 1 to 15, it computes a **forecasted value** = `last_close + slope * step`[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L680-L689)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L682-L690). Essentially a linear extrapolation.
    
* It determines a **band width** for confidence intervals. The code takes the last ATR value (`atr_last`) – ATR is a measure of volatility (average true range) – and scales it by a factor related to confidence[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L672-L680)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L682-L690). Specifically, it calculates a `confidence_scale = 1/(1+|D_last|)` using the last decodability score[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L676-L684)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L677-L685). If D_last (decodability) is large (meaning a strong signal but perhaps an “unnatural” one), the confidence_scale is smaller; if D is near 0, confidence_scale ~1. Then `band_width = atr_last * (1 + (1 - confidence_scale))`[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L680-L689)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L682-L690). If confidence_scale is low (like 0.2), then (1 + (1-0.2)) = 1 + 0.8 = 1.8, so band ~1.8 * ATR (wider band because we’re less confident). If confidence_scale is high (0.9), then band factor = 1 + 0.1 = 1.1, so just slightly above ATR.
    
* For each forecast step, it sets upper = forecast_value + band_width, lower = forecast_value - band_width[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L686-L694).
    
* It also caps the confidence between 0.1 and 0.99 for safety[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L686-L694). The `confidence` in each output point might just mirror that composite confidence_scale.
    

Thus, the forecast is basically a **linear extrapolation plus a volatility corridor** where the corridor width is determined by recent volatility (ATR) adjusted by how confident we are (which in turn is influenced by D – a measure of how “scripted”/predictable the recent activity was). This indeed forms an **“implied volatility corridor”**, albeit “implied” here is partly from technical ATR and partly from track decodability (one could integrate actual implied volatility from options by replacing ATR with an IV-based range).

**Integration of Track Signals:** The above description might sound like it doesn’t explicitly incorporate the decoded macro or micro track trajectories. However, indirectly it does: if a track is active and predicted, say, an upward movement, likely the actual price action and the D score reflect that (scripted buying etc.), so the slope might be upward and D might be significant. In future iterations, the forecast could be more explicitly tied to track projections:

* For example, if an active track projects a price of X in 10 minutes, the forecast algorithm could bias the extrapolated line toward that point instead of a simple linear fit. That would require solving for a line or curve that reaches near the track’s target.
    
* If multiple tracks (like an intraday and a macro) are active, perhaps the forecast is a weighted blend: the macro might provide a slow-moving baseline, and the intraday track adds a short-term deviation. The `tracks` array in forecast payload is intended for such multi-track composite logic (each with weight)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/dashboard/components/CompositeForecastChart.tsx#L138-L146)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/dashboard/components/CompositeForecastChart.tsx#L144-L152).
    

At present, the **Composite forecast** shown in the Studio is drawn by taking this forecast payload (with its `path` array for the future) and plotting it as a bold line, with the area between upper and lower as a translucent band[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/dashboard/components/CompositeForecastChart.tsx#L282-L291)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/dashboard/components/CompositeForecastChart.tsx#L285-L293). It also plots the actual recent candlesticks and, optionally, it overlays the individual track projections as thin dashed lines for comparison (the UI can toggle a “subway map” mode where each track’s line is shown distinctly)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/dashboard/components/CompositeForecastChart.tsx#L332-L340)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/dashboard/components/CompositeForecastChart.tsx#L339-L348). In standard mode, active track influences might be shown as faint lines or not at all, focusing on the composite result[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/dashboard/components/CompositeForecastChart.tsx#L349-L355). The different cluster types of tracks (impactor, binder, echo, macro) could be color-coded if displayed[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/dashboard/components/CompositeForecastChart.tsx#L34-L42)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/dashboard/components/CompositeForecastChart.tsx#L44-L52).

**Options Influence:** The forecast code also includes integration of the `options_payload` and a `summary_payload`. The `options_payload` often provides an “asof” timestamp and a message (for example, it might say something like “Max pain at $20, high gamma at $22 strike” or similar). While not directly numeric, this could be used by the UI to annotate the forecast or summary. The `summary_payload` (compute_summary_payload) compiles interesting stats: e.g., the percentage of bars lately that were classified “scripted” (scripted_pct), the last entropy value, etc. It also picks out something called `hinge_count` and `options_msg` from the options payload[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L780-L788)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L781-L790). This suggests the summary knows how many “hinges” (maybe significant option strikes) and any message from the options module. The summary might combine this info into an actionable insight, for example: “Scripted activity high (80% of last 50 bars). Forecast confidence 0.8. Nearest option hinge at $22 (resistance).” These would be displayed in the UI’s **Insights Panel** or as a note on the chart.

**Calibration and Confidence:** The `calibration_payload` computed by `compute_calibration_payload` is used to gauge how accurate the forecast bands have been recently[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L760-L769)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L770-L778). It calculates the proportion of historical closes that fell inside the previous forecast upper/lower (coverage), the average relative band width, and the last forecast error percentage[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L736-L744)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L745-L754). These metrics can feed back to adjust the next forecast. For instance, if historically only 50% of actual moves stayed in the forecast bands (which is low if bands supposed to be ~90% confidence), the system might decide to widen future bands or reduce confidence rating. This calibration info might also be displayed in a diagnostics UI for the developers or as hidden values used in summary.

**IVCM Evolution:** The current model (slope + ATR band scaled by D) is a first-pass. The name implies future integration of implied volatility. For example, the band width could be set using the stock’s implied volatility for the horizon (from option IV, one could derive an expected 1-sigma move). That would perhaps be more accurate than ATR which is backward-looking. If we incorporate IV, we might call it truly “implied vol corridor”. If combined with decodability D, it’s effectively mixing market’s expectation of volatility with our confidence in track-driven predictability.

**Example Forecast:** Using the earlier example track scenario: Suppose GME is trading around $20. A power track just triggered and decodes suggesting a controlled 5% rise intraday (scripted buying). The last few bars show an uptrend. The detector’s D (decodability) is high (strong signal). ATR for last hour is, say, 0.4 (stock moved ~40c on average each minute). The forecast algorithm might output something like:

* Horizon: 15 minutes.
    
* Projected slope: e.g., +0.05 $/min (stock rising).
    
* Last close: $20.00.
    
* So in 15 minutes maybe expecting ~$20.75 if it continued (which is +3.75%).
    
* D is high, say 0.8, so confidence_scale = 1/(1+0.8)=0.556. That’s relatively low (meaning actually that we see a strong anomaly, which ironically yields lower numeric confidence scale – the logic is that a large D means scenario is very non-random, but maybe also implies potential volatility).
    
* ATR_last = 0.4. Then band_width = 0.4 * (1 + (1-0.556)) = 0.4 * (1 + 0.444) = 0.4 * 1.444 = 0.5776.
    
* So initial forecast minute: value ~20.05, upper ~20.627, lower ~19.472. By minute 15: value ~20.75, upper ~21.327, lower ~20.173.
    
* Confidence probably capped at 0.99 or min 0.1; in this case we might mark confidence ~0.56 (or perhaps we treat track present as high confidence – the current formula ironically lowers it for high D, might be counter-intuitive. Possibly it expects D to measure unpredictability? Need interpretation: if D is decodability fraction of anomaly, maybe a high D implies the phenomenon is strong but not necessarily more confident in price outcome? Anyway).
    
* The forecast track listing might just have ["Composite": weight 1.0, confidence 0.56, entropy=some value].
    

The UI would then draw from $20 gradually to $20.75 over 15 minutes, with a green band from ~$20.17 to ~$21.33 at the end. That indicates a predicted upward drift with a margin of error roughly ±$0.58 by end, which is about ±2.9%. If an options snapshot indicates heavy call open interest at $21, the system might note that as a potential cap (resistance), which conveniently lies near the upper band.

**Continuous Updates:** The SSE streaming endpoint in Studio pushes out a fresh forecast payload every few seconds (the stream loop calls `adapter.get_forecast` at some interval, probably the `stream_interval_seconds` which might be 5 or 10 seconds)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L649-L657)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L681-L689). This means as new ticks come in, the forecast continuously shifts (the slope recalculates, last_close updates, etc.). The UI’s chart updates the line and band smoothly (the frontend likely animates transitions). If a new power track is detected during that time, the state payload will show a big change (spike or drop and a regime flip maybe), which could drastically alter the forecast on the next iteration. This live feedback loop is crucial for the system to reflect sudden changes.

In summary, the **IVCM forecasting logic** takes the outputs of the detection (like decodability D, track signals) and combines them with market volatility measures to produce a short-term probabilistic forecast. It’s an evolving part of the system – intended to become more sophisticated by incorporating more of the decoded track intelligence and options market data. The current implementation yields a composite forecast path and confidence interval that is displayed in Studio, giving traders a sense of expected move and uncertainty in the immediate future.

Engine API and Data Contracts
-----------------------------

The Power Tracks Engine exposes a set of APIs for accessing its functionality and data. These are primarily RESTful HTTP endpoints (with some supporting WebSocket topics for push data). The Fastify server in the engine daemon is documented via an OpenAPI 3.1 spec[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L109-L117), ensuring that both internal and external consumers know how to interact. Below we detail the key API endpoints, their request/response schema, and how they tie into the engine’s data structures.

### Authentication

All engine API endpoints (except health checks and metrics) require an API key. The key can be provided either as an `x-api-key` header or a Bearer token in the `Authorization` header[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/openapi/power-tracks-engine.yaml#L10-L18)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/openapi/power-tracks-engine.yaml#L46-L55). In many deployments, the Studio backend will be the one authenticating to the engine (so the API key is set in the Studio’s environment and passed along). The engine supports multiple API keys if needed (configured via env or config file), but commonly a single shared secret is used. Unauthorized requests get a 401.

### Health and Metrics

* **GET `/health`** – A public endpoint that simply returns a status object, e.g. `{"status": "ok"}` if the service is up[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L20-L28). This can be used by load balancers or Kubernetes liveness probes. The engine typically also includes an uptime and maybe some build info in a more detailed `/status` endpoint.
    
* **GET `/metrics`** – Also public (by default), returns Prometheus metrics in plain text. It includes internal metrics like request durations, detection counters, last detection timestamp per symbol, feed reconnect counts, sink error counts, etc., as mentioned earlier[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/runbook.md#L10-L18). This is not JSON but a text format meant for scraping.
    
* **GET `/status`** – This returns a server status summary (protected by API key). It can include engine uptime, current config summary, and subcomponent statuses (detector running or not, feed connected, sinks active). The spec defines a ServerStatus schema with fields like `detector`, `sinks`, `feed`, `server`, `data` etc[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/openapi/power-tracks-engine.yaml#L81-L89)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/openapi/power-tracks-engine.yaml#L94-L102). Each of those might have nested info: for example, `feed` might say connected:true and last_message_time, `data` might list which data mode is active (filesystem vs polygon).
    

### Power Track Retrieval

* **GET `/v1/tracks`** – Returns a list of detected tracks (the track catalog). Query parameters allow filtering:
    
    * `symbol` can filter to a specific stock symbol (if not provided, it returns tracks for all symbols)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L98-L103).
        
    * `limit` to limit the number of tracks (e.g., last 100)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L98-L103).
        
    * `offset` for pagination.
        
    * Filters like `cluster` (to show only specific cluster types, e.g., cluster=macro or cluster=impactor)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L98-L103), `timescale` or `severity` perhaps, as indicated by internal usage in code (the code in main includes cluster, timescale, severity in log message parsing the request, implying these filters exist)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L8-L16)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L8-L16).
        
    * Possibly `start` and `end` date filters (to get tracks in a date range).  
        The response includes an array of tracks and a count. Each **PowerTrack** object has fields:
        
        * `id` (the track ID string)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/openapi/power-tracks-engine.yaml#L114-L122),
            
        * `symbol`,
            
        * `timestamp` (ISO date-time of detection)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/openapi/power-tracks-engine.yaml#L118-L125),
            
        * `spectral_power`[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/openapi/power-tracks-engine.yaml#L124-L131), `roc_value`[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/openapi/power-tracks-engine.yaml#L124-L131),
            
        * `venue` (primary venue code)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/openapi/power-tracks-engine.yaml#L128-L133),
            
        * `cluster_type` (impactor, binder, echo, macro)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/openapi/power-tracks-engine.yaml#L132-L140),
            
        * `decodability` (object containing D, D* etc. or other metrics)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/openapi/power-tracks-engine.yaml#L136-L140),
            
        * `regime` (scripted/organic/transitional)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/openapi/power-tracks-engine.yaml#L138-L143),
            
        * possibly others like `severity` or `passLabel` if defined (the UI code references something called `passLabel` as perhaps an alias of cluster or severity)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/dashboard/components/CompositeForecastChart.tsx#L46-L53).  
            The OpenAPI `TrackListResponse` defines the shape with `tracks` array and some metadata[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/openapi/power-tracks-engine.yaml#L148-L157)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/openapi/power-tracks-engine.yaml#L154-L163). The engine likely sources this data from its database or manifest index via `listAllTracks()` which scans file directories[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/data-architecture-analysis.md#L30-L38)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/data-architecture-analysis.md#L32-L40) and the SQLite database if connected. If macro tracks are included (via a param like `?include=macro` or if cluster filter=macro), those will appear as well, with cluster_type 'macro'. Macro tracks will have their own IDs (or reuse an ID scheme) and timestamp (maybe of the last segment or when macro was compiled).
            
* **GET `/v1/tracks/path`** – Returns the price path for a specific track[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L607-L615). Takes `symbol` and `track_id` as query or path parameters (the spec shows them as query, but main.py implements it as function parameters)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L607-L615). Also an optional `limit` can specify max number of points (to downsample a long path to say 240 points)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L607-L615)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L610-L618). The response is a JSON with:
    
    * `track_id`, `symbol` repeated,
        
    * `path`: an array of { timestamp, price } points making up the track’s unfolded price path[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/openapi/power-tracks-engine.yaml#L194-L202)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/openapi/power-tracks-engine.yaml#L204-L212). If upper/lower bounds exist per point, the current schema doesn’t show them, so likely it’s just the central path. However, in macro context, the corridor had min/max – perhaps those are stored elsewhere or the path includes them if down-sampled for macro corridors.
        
    * `limit`: the number of points returned[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/openapi/power-tracks-engine.yaml#L208-L216).  
        Essentially, this endpoint is used by the UI if someone wants to see the actual shape of a track’s predicted movement (for instance, plotting the unfolding from start to finish). For intraday tracks, this might be a few hours long. For macro tracks, it could be months long path, hence down-sampling.
        

### Macro Track API

* **GET `/v1/macro`** – As described, triggers macro track stitching. Query params:
    
    * `symbol` (required to focus on one symbol; some implementations might allow 'ALL' but macro assembly is typically symbol-specific)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L22-L29).
        
    * `start` and `end` dates to restrict the range (or a `lookback` days parameter alternatively)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L22-L29).
        
    * `min_days` (minimum segments to qualify)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L24-L31).
        
    * `mask_drift` tolerance if wanting to override default.  
        The response includes a **MacroTrack** object (or list of them if multiple separate chains found in that window). The OpenAPI `MacroTrack` schema has:
        
        * `symbol`, `start_date`, `end_date`[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/openapi/power-tracks-engine.yaml#L172-L180),
            
        * `tracks`: an array of PowerTrack objects (the segments)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/openapi/power-tracks-engine.yaml#L180-L188),
            
        * `correlation` (perhaps the correlation of those segments’ price movements or spectral similarity)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/openapi/power-tracks-engine.yaml#L184-L190),
            
        * `stitched_count` (how many tracks were stitched)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/openapi/power-tracks-engine.yaml#L184-L191).  
            In practice, the engine returns an array under `tracks[]` (one level up in response) which might correspond to macro tracks found. But according to macro-flow documentation, the API returns a payload with `tracks` array of macro segments and also diagnostic fields like used_dates[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L26-L34). It likely wraps the MacroTrack in another object containing `available_dates` etc. For consistency, it might be:
            

```
{
  "symbol": "GME",
  "tracks": [ {macroTrack1}, {macroTrack2}, ... ],
  "available_dates": [...],
  "used_dates": [...],
  "min_days": X,
  "mask_drift": Y,
  "generated_at": timestamp
}
```

Given the macro is often run one at a time, usually it might return one macro chain (if any) or none (with maybe status empty).

If macro track is found, the engine also writes the `macro_tracks.json` file and inserts into DB as mentioned. So subsequent calls or UI toggles can fetch macro tracks via either the macro endpoint or via the general tracks list with cluster=macro (since those were inserted in DB as detection_mode macro_chain).

### State and Analytics Endpoints

The engine provides several endpoints under the “State” tag that serve data used for analytics and UI beyond just detected tracks:

* **GET `/v1/state`** – Returns the current aggregated state of the symbol. This includes the last N bars of data (minute bars typically) and any known state metrics. It basically powers the “live state card” in UI – e.g., it might provide an OHLC series for the day along with overlays marking where tracks occurred and perhaps state classifications per bar (scripted vs organic). The internal payload likely has arrays for `ts`, `open`, `high`, `low`, `close`, and possibly derived arrays `upper`, `lower` (like Bollinger band), `state` (scripted/organic label per bar), `D` (decodability per interval), `entropy`, `volume` etc[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L163-L171)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L175-L183). In the streaming SSE, the engine indeed provides `state` with up to 600 points (10 hours if minute bars) trimmed[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L163-L171)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L175-L183). The engine obtains this by reading stored minute bars (via FilesystemLoader or polygon API fallback)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/data-architecture-analysis.md#L20-L28). If minute bars CSV for symbol exists, it loads it; otherwise it calls Polygon REST to get recent aggregate bars[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/data-architecture-analysis.md#L20-L28)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/data-architecture-analysis.md#L22-L30). This ensures the UI has context even if local data not pre-harvested.  
    The state response also likely includes a `status` field (“live” if receiving live ticks, “fallback” if using REST) and possibly a `lastUpdate` timestamp. The Studio API wraps engine’s state and adds a cache layer with such metadata[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L90-L99)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L115-L123).
    
* **GET `/v1/flip`** – This likely returns “flip points” or pivot points. The code references a `flip_payload` and something about `flip_alerts`[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L669-L677). Possibly it identifies points where regime flips from organic to scripted or vice versa. The polygon_proxy has `_build_flip_series` which identifies local highs/lows (pivots) by looking for when a bar is highest among ±N bars (depth=5)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L176-L179)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L177-L179). The output might be a series of “boxes” (the code mentions trim boxes list to 40 in stream)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L664-L672). Perhaps “flip” refers to a specific analytic (maybe related to binder tracks that flip direction, or just pivot detection).  
    In any case, flip endpoint returns some object with presumably a list of notable pivot points or “flip” events and maybe some interpretive text or score. It’s tagged as requiring data loader (meaning it needs historical data to identify flips).
    
* **GET `/v1/entropy`** – Would provide time series of permutation entropy or similar metric for the recent data (like a rolling entropy of returns). Possibly a simple list of entropy values over time to gauge how unpredictable the recent market is. Not much detail in code except that in SSE, they cut off `entropy` list to 600 length[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L175-L183).
    
* **GET `/v1/bursts`** – This might list raw “burst” periods found in the day aside from full tracks. Possibly it returns sub-track structures or the initial detections prior to decode (like candidate windows flagged even if they didn’t decode). Unclear, but since it’s in state tag, it might identify all bursts (detected or marginal) on that date.
    
* **GET `/v1/keyframes`** – Possibly returns key frames of the track decodings if any, or key time points (e.g., predicted points). Could also mean something like capturing representative points from price series.
    
* **GET `/v1/raw-bars`** – Returns raw OHLC bars for the day (like a more direct route to fetch minute bars as JSON). Useful if the UI or others want candlestick data directly. It likely has the same info as state but maybe in a simpler schema (time, open, high, low, close arrays).
    
* **GET `/v1/summary`** – Provides a summarized view combining other data: might include the latest price, what % of day was scripted, last entropy, a combined confidence measure, any macro insight, etc. The polygon_proxy `compute_summary_payload` uses state, forecast, options, calibration to produce fields like `last_price`, `scripted_pct`, `last_entropy`, `last_d`, plus info from forecast (like forecast_conf and horizon) and from options (like hinge_count, options_msg)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L760-L769)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L770-L778)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L780-L788). So the summary endpoint likely aggregates everything into one convenient JSON for UI to display on a dashboard card.
    
* **GET `/v1/forecast`** – Returns the forecast data as computed by IVCM (which we detailed). The response likely includes the `history`, `path`, `horizon_minutes`, `tracks`, `spot` fields described earlier[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L702-L710)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L711-L718). The Studio API may call engine’s forecast and then possibly combine it with state to generate composite or to feed into summary. However, in code, `get_forecast` is directly used in SSE generator and in `forecast_endpoint` calls serve_endpoint with loader=adapter.get_forecast, which ultimately calls engine if available or computes via polygon_proxy if engine doesn’t do it. The implementation (as we saw in compute_forecast_payload) uses primarily state payload (which includes possibly `upper`/`lower` arrays maybe from Bollinger). So engine’s forecast might require having called state first.
    
* **GET `/v1/calibration`** – Returns how well the forecast has been doing: coverage, avg band %, last error, etc as we saw computed[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L720-L728)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L736-L744). This is more of a diagnostic but could inform UI or at least logs. For example, if coverage is 0.5, maybe show an alert that forecast bands captured only 50% of moves -> meaning we were underestimating volatility.
    
* **GET `/v1/options` and `/v1/options-hinges`** – Likely fetches current options market analytics. Possibly hitting Polygon’s options API internally or using cached results. Options-hinges might specifically return crucial points like highest gamma exposures (“hinges”). The code `compute_options_hinges` likely collects open interest or implied vol at various strikes and picks out something to call "hinges". The output might include:
    
    * `asof`: timestamp of data,
        
    * `hinges`: an array of key strike levels or pivot vol levels,
        
    * `message`: a human-readable summary (e.g., “High call OI at 25, could act as resistance, put wall at 20 support”).  
        This is somewhat speculative, but since the summary combines `options_msg` and `hinge_count`[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L780-L788)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L781-L790), presumably `hinges` is a list of levels, and `message` is textual.
        

### WebSocket and Streaming

The engine itself, in daemon mode, opens a WebSocket that clients can connect to. It defines some channels (likely using a pub/sub model internally):

* **`tracks.live`** – Broadcasts each new track detection in real-time to all subscribers[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L58-L64). The payload would be the PowerTrackCandidate in JSON.
    
* **`tracks.symbol.<symbol>`** – Same as above but filtered to a specific symbol. So if a client only cares about GME, they subscribe to `tracks.symbol.GME` and get events only when GME tracks occur.
    
* **`telemetry.events`** – Possibly streams out various telemetry logs, or more granular candidate events (like “window scanned, power=5000 no trigger” or others, though likely not by default as that’s too verbose).  
    These WebSocket topics allow building real-time dashboards or triggering other services. In our case, the Studio front-end does not connect to engine WS directly (due to cross-origin and complexity), instead the Studio backend uses SSE to push a composite snapshot. The SSE `/v1/stream` essentially aggregates multiple engine endpoints (state, flip, summary, options, forecast, composite) into one event payload that the UI consumes conveniently[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L649-L658)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L707-L715). But if one were building a custom client, they could also connect to engine’s WS and individually call REST for state etc.
    

The **SSE `/v1/stream`** in the Studio API is worth summarizing: it creates an event stream that periodically (every `stream_interval_seconds`, e.g., 5 sec) gathers:

* state (with last ~720 points),
    
* flip (with trimmed boxes list),
    
* summary (if available),
    
* options,
    
* forecast,
    
* composite (if engine supports composite snapshots; composite might be some combined view, but in code it’s marked optional and can error without failing stream)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L681-L689)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L685-L693).  
    Then it compares with last sent version to avoid sending duplicates (if nothing changed, it waits)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L692-L700)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L694-L702). When new data is ready (like last_state_ts changed or summary_generated changed, etc), it packages into an object:
    

```
{
 "symbol": "XYZ",
 "date": "2025-11-09",
 "generated_at": "...",
 "state": { ... trimmed arrays ... },
 "flip": { ... },
 "summary": { ... },
 "options": { ... },
 "forecast": { ... },
 "composite": { ... or error if composite failed }
}
```

and sends as an SSE event named "snapshot"[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L706-L714)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L715-L723). If any exception happens (like engine not responding), it yields an "error" event with the error message, but keeps the connection alive for next attempt[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L720-L728). This SSE is what the Studio frontend listens to for live updates, ensuring everything updates synchronously.

### Database Schema (Postgres)

In local default, engine uses SQLite (`powertracks.sqlite` file). In production, we migrate this to Postgres (e.g., on Railway). The core schema as implied by earlier docs:

* **Table `tracks` (or `power_tracks`)**: stores each detection. Likely columns:
    
    * id (text primary key),
        
    * symbol (text, indexed),
        
    * timestamp (datetime),
        
    * spectral_power (real),
        
    * roc_value (real),
        
    * venue (text or smallint code),
        
    * cluster_type (text or smallint),
        
    * regime (text),
        
    * decodability_json (JSON or separate columns for d_score, d_star, maybe entropy, varint_success, etc. Alternatively decodability fields could be stored directly as numeric columns if consistent).
        
    * detection_mode (text) – e.g., 'live' or 'macro_chain'. For macro stitched entries, this is 'macro_chain'[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L42-L48), for normal it could be 'live' or null.
        
    * payload (JSON) – possibly a blob of additional data (like the entire decoded frames or corridor). In the artifact plan, they mentioned embedding metadata fragments in the catalog[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-refactor-plan.md#L4-L8). It's common to store a JSON of the track details in a column so that one can reconstruct the track fully from DB alone. If the JSON contains e.g. the track’s price path or frames, it might be large, but maybe just storing small summary (like timescale summary, horizon).
        
    * perhaps columns for `timescale_summary` (like [7d,4d,1d] if a binder covers these horizons), or horizon_seconds, etc., if easy to parse into columns.
        
    * version info (detector_version, decoder_version).
        
    * provenance (maybe stored in JSON or separate table linking track to artifact file hash).
        
    
    According to the artifact doc: _“tracks: one row per track_id with symbol, detection window, detector/decoder versions, and embedded metadata fragments.”_[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-refactor-plan.md#L2-L8)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-refactor-plan.md#L4-L8). So that confirms the above.
    
* **Table `artifacts`**: maps each track to files. It likely has:
    
    * track_id,
        
    * stage (enum: raw, decoded, analytics, visuals, detect),
        
    * artifact_path or link (maybe a relative path or URL to where the artifact is stored, e.g., a JSON file or PNG image),
        
    * possibly a hash or size.  
        The artifact repository standard folders (raw/, decoded/, etc.) mean each track ideally populates multiple rows here. E.g., track T1 might have:
        
        * raw: ledger.csv (raw ticks)
            
        * raw: minute_candidates.csv (if any)
            
        * decoded: frames.parquet or frames.json
            
        * analytics: lag_manifest.json (with metrics)
            
        * visuals: spectrogram.png  
            etc. The `orphan_artifacts` table collects any files not mapped to a track.
            
    
    But as of writing, not all data is in DB because migration to PG is still to be done (it was flagged as next priority)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/MIGRATION_SUMMARY.md#L42-L50).
    
* **Table `orphan_artifacts`**: listing files found that don’t have a track entry (so they need either track entry or should be moved). This helps to audit completeness (should ideally be empty if all artifacts linked to track rows).
    

If using TimescaleDB (which is mentioned as an idea for production sink[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L87-L95)), the `tracks` table could be a hypertable partitioned by date for performance. But a simpler approach is a normal table with an index on date/symbol.

### Redis Keys

When Redis is integrated:

* **Stream for detections**: likely a stream key such as `powertracks:events` or `powertracks:tracks`. Not explicitly stated, but the decision was to use Redis Streams for fan-out[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L12-L17). If so, each detection might be XADD to `powertracks:tracks` with fields of the track JSON. Consumers can create consumer groups on that stream. The key strategy might prefix everything with `powertracks:` to namespace.
    
* **Cache keys**: As seen in Studio API, they use keys like `pt:v1:{endpoint}:{symbol}:{date}` for caching responses[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L87-L95). For example, the state of GME for 2025-01-01 might be cached at key `pt:v1:state:GME:2025-01-01`. They store the whole JSON payload under that key in Redis with an expiry (s-maxage etc. indicates maybe a TTL of say 30 seconds)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L90-L98)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L92-L100). The keys also store a nested `cache` field in the JSON with status and maybe lastUpdate times. The use of `pt:v1:` prefix is consistent and ensures uniqueness per endpoint. Also note, they might use a separate shorter-term key for streaming SSE last state or keep alive, but likely not needed.
    
* **Rate limiter**: They instantiate a `RateLimiter` using the Redis client, likely using keys to track requests per IP. Possibly keys like `pt:rl:IP:minute` to count requests and expire each minute.
    
* **Engine internal**: If the engine uses Redis for work queue (BullMQ), it will use keys for the queue like `bull:tracksQueue` or such. But that's internal to bull. For Redis Streams if manual, the key would be set by engine config (not shown, but maybe `engine.queue.streamKey`). If multiple engine instances share Redis, they'd coordinate via such keys. That’s likely a future scaling design.
    

**Object Storage Structure (MinIO/B2):**  
When using cloud storage (Backblaze B2 or S3):

* The artifacts stored in `data/power_tracks/<symbol>/<track_id>/...` on local disk need to be synced to a bucket. The `pt-data sync` command uses config specifying `source_dir` and base path in bucket[GitHub](https://github.com/TheGameStopsNow/power-tracks-data/blob/aabfb89e788ea236dee68d9153fd74907821b507/docs/data-pipeline-guide.md#L136-L144)[GitHub](https://github.com/TheGameStopsNow/power-tracks-data/blob/aabfb89e788ea236dee68d9153fd74907821b507/docs/data-pipeline-guide.md#L138-L146). They likely upload everything under `data/power_tracks/` to the bucket under a prefix `artifacts/` (as per config)[GitHub](https://github.com/TheGameStopsNow/power-tracks-data/blob/aabfb89e788ea236dee68d9153fd74907821b507/docs/data-pipeline-guide.md#L138-L146). So in B2, you might have:
    
    * `artifacts/XYZ/track1234/raw/ledger.csv`
        
    * `artifacts/XYZ/track1234/decoded/frames.parquet`  
        etc.
        
* The plan is that the DB (catalog) would store the references such that if you want to retrieve an artifact, you either find it locally or construct the B2 URL (like `https://f000.backblazeb2.com/file/bucket-name/artifacts/XYZ/track1234/decoded/frames.parquet`). MinIO in Docker serves as a local stand-in for S3; the compose file likely sets up a MinIO container with bucket accessible at `http://localhost:9000` which Studio API can talk to for artifact retrieval.
    
* In practice, the **structured artifact repository** is considered the source of truth for all track data beyond the summary in DB[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-artifacts.md#L14-L22). This means that anything not easily stored in DB (like full frame-by-frame info or images) is in the object store. The DB catalogs them for quick search.
    
* **Storage pointer strategy:** In production, the engine might not store large JSON in DB but rather pointer to an object store file. For example, the track’s decoded frames might be a Parquet in S3; the DB track row could have a column `frames_url` if needed, or the consumer just knows to fetch it from the artifacts service. But likely they'd rely on static file serving.
    

The `power-track-artifacts.md` also suggests that after migration, downstream systems should rely on the **catalog** (DB) or its JSON export instead of scanning the file system ad-hoc[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-artifacts.md#L40-L48). So the plan is to generate a single JSON or use DB queries for any introspection, with direct file access only when needing the heavy data (like for re-decoding or deep analysis).

**CI/CD Integration:**  
The development process is integrated with CI to maintain determinism and data integrity:

* They have a `power-track:ci` npm script that runs a battery of checks: inventory artifacts, migrate, seed catalog, then run a catalog report to ensure no orphans and 100% core stage coverage[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-refactor-plan.md#L2-L5)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-refactor-plan.md#L2-L5). If any artifacts are unaccounted (or coverage <100%), it fails the build[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-refactor-plan.md#L2-L5)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-refactor-plan.md#L3-L5). This ensures that any new code that outputs tracks or changes data structures updates everything properly.
    
* Tests: There are likely unit tests for the detection algorithm (using easier thresholds to get quick triggers on small sample data)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L54-L58), for decoding (maybe using known encoded sequences), and integration tests that run the engine on historical data and compare outputs to expected. Because the research alignment is crucial, tests might assert that default config yields no spurious detections on quiet data, or that it catches known events.
    
* The CI example in docs shows using GitHub Actions to run these checks on every push, including environment variables needed for calling Polygon (they inject a Polygon API key in CI)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-refactor-plan.md#L100-L108)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-refactor-plan.md#L111-L115). After CI passes (ensuring no orphans etc.), they likely publish the updated package or deploy.
    
* **Deterministic outputs:** One important testing strategy is to guarantee that given the same dataset, the engine produces identical results. This can be verified by running the detection on stored data multiple times or on different platforms and comparing hashes of outputs (manifest JSONs). Because no randomness is used, differences would indicate a bug or uninitialized variable etc. Part of the CI might involve doing a short replay of known data and ensuring the output file matches a golden file.
    
* **Continuous Deployment:** The migration summary mentions templates for Railway and Render (PaaS providers) with environment config for easy deployment[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/MIGRATION_SUMMARY.md#L28-L36)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/MIGRATION_SUMMARY.md#L30-L36). This implies that the project can be deployed on those services in CI after tests, possibly automatically. E.g., commit to main triggers CI, on success triggers deploy to a staging or prod instance on Railway via those templates.
    
* **Versioning:** The OpenAPI spec has version 1.0.0 for engine API[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/openapi/power-tracks-engine.yaml#L12-L19). They likely bump that as breaking changes occur. The NPM package @powertracks/core is versioned as well (so integrators can rely on a stable interface). The technical spec in this document should be considered tied to a certain version baseline and updated as the system evolves.
    

### Failure Modes and Deterministic Behavior

The system is built to handle various failure scenarios gracefully and to ensure consistent behavior:

* **Data Gaps:** If live data is missing (e.g., Polygon feed disconnects), the engine uses fallback REST data for state and tries to reconnect the feed. It increments a `feed_reconnects_total` metric which can alert ops if frequent[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/runbook.md#L12-L16). During a gap, detection might pause (since no ticks), but once reconnected it resumes. If some ticks were missed entirely, a track could be missed or have partial data; such scenario is hard to fix retrospectively except via backfill. The engine does log feed issues to telemetry.
    
* **Decode Failures:** If decoding fails (no mask works), the engine still outputs the track detection but with `decodability` metrics indicating failure (maybe D=0, entropy high, etc.). The track can be stored even if not decoded, and flagged. This ensures deterministic output: the presence of a weird burst is recorded, not silently dropped. It’s up to consumers whether to ignore a track with no decode.
    
* **Sink Failures:** If writing to database or file fails (e.g., disk full, DB down), the engine increments `powertracks_sink_errors_total` with the sink name[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/runbook.md#L12-L16). It may retry or buffer in memory. For example, if Postgres is down, engine might fall back to writing JSON only, or queue the DB writes for later. The Hook system tries/catches webhooks; failures there might be logged but won’t crash the engine.
    
* **Multiple Detections Colliding:** Deterministic logic prevents double-detection of one event. The refractory period logic and track windowing ensures that two overlapping windows won’t both fire for the same burst. This was important to avoid duplicates. So “one burst, one track.” If bursts are truly separate (e.g., one starts 2 seconds after another ended), the engine could detect two tracks close in time, that’s fine. In testing, they might verify that no track IDs are duplicated and the times make sense.
    
* **Timezones and Trading Hours:** The engine’s date handling: likely it uses US/Eastern for trading day boundaries by convention (Polygon data is in UTC or Eastern). The Studio API’s `resolve_date()` uses America/New_York as default[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L54-L61), meaning when requesting “today” it aligns with the Eastern trading day. This ensures that date-based endpoints (/v1/state?date=2025-11-09) return the data for that trading date. The deterministic behavior is that results should not depend on the server’s local timezone. They explicitly use zoneinfo to control that.
    
* **Non-deterministic sources:** Using live data can be non-deterministic if data arrives slightly differently or if polygon’s feed has minor variations. However, for reproducibility, any track found live should also be found when re-running on historical data from Polygon (since it’s the same ticks). If the engine uses some randomness (none known in detection), that would be a problem. But currently, it doesn’t; even the FFT might have minor floating error differences across platforms but threshold checks should handle that (also they are large values, 1e4 scale).
    
* **Order of processing:** In a single thread per symbol, ticks are processed in order received. If multi-threading were used across symbols, that’s fine (no cross-talk). The outputs for one symbol won’t affect another (except maybe macro if they ever consider cross-symbol macro, which is not implemented but was envisioned for cross-asset analysis[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L46-L51)). So determinism per symbol holds.
    
* **Unhandled Exceptions:** The engine is presumably robust to bad data: if ticks have NaN or negative prices (shouldn’t happen normally), `validateRealData` would catch and skip them[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L14-L16). If the FFT or other algorithm throws due to some numeric issue, it might log and continue. The system was tested to ensure that no matter what data is fed (even zero ticks), it doesn’t crash but maybe yields no detection.
    
* **Quantization Effects:** Minor differences in data or environment should not cause dramatically different results. For instance, if the spectral power is exactly at threshold 10000, a tiny difference might cause one run to detect, another not. The engine likely floors/ceil values or uses >= comparisons consistently to minimize that corner. It’s still possible a borderline case could flip detection yes/no if any floating rounding occurs. But given typical data noise, such an exact tie is rare.
    
* **Replay and Backtesting:** Running the engine on historical data should produce the same track list as stored from live. This is a design aim. The Data pipeline and orchestrator provide ways to verify that: e.g., harvest data for a day and run `pte detect` in batch, then compare output to what the live run stored (if available). This can highlight any differences, which should ideally be none.
    
* **Stable Output Formats:** The JSON structures of manifest, macro output etc., are versioned and backward-compatible where possible. If a format changes (say they add a new field to decodability), they would bump an internal version or at least ensure old readers don’t break (maybe by only appending new fields, not removing existing ones). The internal documentation would reflect those changes.
    

Overall, by consolidating everything in this specification, we ensure that all engineers and integrated AI agents have a unified understanding of the system’s design and behavior. All the components from detection to UI have been described with their interactions, and all relevant data schemas and protocols have been enumerated. This document should serve as a stable reference for implementation and further development of the Power Tracks system, ensuring consistency and scientific integrity across the board.

Studio UI and Workflow Integration
----------------------------------

_(This section consolidates how the Studio front-end is structured and how it integrates with the engine and data orchestration, as well as describing the user-facing layout.)_

**UI Architecture:** The Power Tracks Studio application is a **Next.js** React app, with a co-hosted **FastAPI** backend. They run together via Docker Compose along with engine and supporting services[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/end-to-end-setup.md#L201-L210). The Next.js app (the “dashboard” service) handles the interactive visualizations and user commands, while the FastAPI (“api” service) handles API requests from the UI and communicates with the engine and Redis/DB.

The UI is designed with a **responsive, data-rich dashboard** paradigm, inspired by professional trading platforms. Key sections of the UI include:

* **Homepage / Dashboard:** The landing view gives an overview of the system status and quick links. It features a **Toolbox layout** – a grid of panels providing quick actions and info[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L36-L44). For example:
    
    * A “Live Feed Activity” widget showing detection counts per minute (with perhaps a sparkline)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L40-L48).
        
    * An “Orchestration Status” widget summarizing any running data jobs (if applicable).
        
    * Shortcuts for frequently viewed symbols or recently active stocks (populated dynamically, showing badge if new tracks occurred)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L36-L44).
        
    * Possibly a macro tracker summary or “Insights” snippet.
        
    
    There is also a single **status banner** at top indicating whether the system is live or offline (green for live, blue for offline data mode, gray for market closed, red for error)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L13-L21)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L59-L63). This is consistently visible to reassure the user about data timeliness.
    
* **Power Tracks Grid (Tracks Table):** This is a core view listing detected tracks in a tabular form. Each row is a track detection. Columns include time, symbol, cluster type, spectral power, ROC, decodability (D or D*), regime, and perhaps an action to view more details. The grid supports:
    
    * **Filtering**: filter by cluster (Impactor, Binder, Echo, Macro)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L42-L48), by severity (like maybe power or length), by symbol.
        
    * **Sorting**: e.g., by time or spectral power.
        
    * **Real-time updates**: When new tracks are detected live, they animate into the list (like an email inbox receiving new mails)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L19-L27)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L20-L28). The UI animates the insertion, possibly highlighting the new row briefly.
        
    * There is an option to **include macro tracks** in the list or view them separately. If included, macro chains might be shown with a special icon or color (and possibly an expand/collapse to see segments).
        
    * A **compare view** might be offered: the user can select 2–3 tracks (with checkboxes) and compare them side by side[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L42-L48). Compare might open a modal with charts of each track’s price path or metrics.
        
    
    Each track row likely can be clicked to bring up a detail modal or side panel showing that track’s decoded corridor chart, metadata, and possibly allow adding notes.
    
* **Macro Tracks View:** A dedicated page or modal that shows the results of macro stitching. This might present the current macro corridor as a chart (with time on x-axis spanning months, price on y-axis, showing the corridor). It highlights the segments (days) that were stitched, possibly with vertical markers or color segments, so user sees how multi-day structure forms[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L50-L59). The user can adjust parameters (min days, lookback) via UI controls that call `/v1/macro` with those params – maybe an advanced user feature. But typically macro is by default last 180 days with ≥3 segments[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L34-L42)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L62-L70).
    
    In the main tracks grid, macro entries could be listed either as single entries or not at all; but a separate UI (like a Macro tab) ensures the user sees if any macro chain is currently identified for a symbol. The Studio likely also adds macro data as an overlay in the charts (e.g., in forecast chart, macro might appear as a long-term line).
    
* **Composite Forecast Chart:** This is an interactive chart combining multiple data layers:
    
    * Recent actual price candles (perhaps last one or two days of 1-min or 5-min candles) plotted as candlesticks[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/dashboard/components/CompositeForecastChart.tsx#L273-L281)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/dashboard/components/CompositeForecastChart.tsx#L275-L283).
        
    * The **composite forecast line** and its confidence band (shaded area) over the next horizon[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/dashboard/components/CompositeForecastChart.tsx#L284-L292)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/dashboard/components/CompositeForecastChart.tsx#L285-L293).
        
    * Optionally, the individual **track projection lines** (“subway map” mode): if multiple tracks are active, each track’s projected path is drawn in a distinct color, possibly dashed, converging into the composite. This view shows how different tracks (impactor vs binder maybe) are contributing[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/dashboard/components/CompositeForecastChart.tsx#L331-L339)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/dashboard/components/CompositeForecastChart.tsx#L333-L341). For active tracks marked as “active” (lifecycleState), those lines might be highlighted vs dormant tracks’ lines faded[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/dashboard/components/CompositeForecastChart.tsx#L349-L355)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/dashboard/components/CompositeForecastChart.tsx#L44-L52).
        
    * The user can toggle between standard and “subway map” mode via a UI control (perhaps a button or switch named “Show individual tracks”)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/dashboard/components/CompositeForecastChart.tsx#L327-L335)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/dashboard/components/CompositeForecastChart.tsx#L333-L341).
        
    * The chart also might display markers for **flip points** or detection points. For instance, when a track was detected, maybe a small icon is shown on the price chart (like a little lightning bolt at that timestamp), and tool-tip can show details. Flip points (pivots) might be shown as triangles or boxes on the chart time series.
        
    
    The composite forecast chart likely resides on a panel in the dashboard, showing the currently selected symbol’s situation. The user might choose the symbol from a dropdown or clicking a symbol in tracks grid which then populates this chart. In a multi-symbol context, they may allow toggling the main view to different symbols.
    
* **Live Mode & Offline Mode Handling:** The UI provides clear indication and adjustments if live data is streaming or not. In **live mode**, as mentioned, a WebSocket status card (or SSE status) shows connection health, and detection rate (tracks per hour or so)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L14-L22). If connection drops, it might show a retry countdown. The UI avoids “blaming” errors in a scary way; e.g., if market is closed, it shows a calm state indicating no live data (blue) rather than error[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L15-L23)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L59-L67). If offline/historical mode, certain elements (like real-time feed or orchestration invites) appear to guide the user to run a backfill analysis instead.
    
* **Orchestration Page (Data Jobs):** This page shows the interface to manage historical data processing tasks. It lists jobs (like “Harvest GME Jan 2021”, “Backfill detection for GME Jan 2021”) with their status (queued, running, done, failed). The UI allows multi-select of jobs for bulk actions[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L26-L34):
    
    * **Multi-select checkboxes** to select many jobs.
        
    * **Clear Queue** to remove all pending jobs (with confirm)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L26-L34).
        
    * **Bulk Delete** to delete selected (completed or failed) jobs[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L28-L36).
        
    * **Bulk Retry** to retry selected failed jobs at once[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L28-L36).
        
    * Input fields to create new jobs (like pick symbol, date range, operation type).
        
    * Possibly a toggle or info showing “Live vs Backfill” mode – an explanation that in live mode tracks come from streaming, in offline you can run pipeline to get missed days[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L32-L35)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L33-L35).
        
    
    This UI ties into the orchestration backend (partly Studio API, partly the engine/data job runners). The `start_harvest` endpoint now enqueues a harvest job and returns a `job_id`, with `/v1/jobs/{id}` for status, backed by an async task that calls the data-plane fetcher. The UI uses SSE (`/v1/stream`) or WebSocket (`/ws/stream`) to get live snapshots, and can poll `/v1/jobs/{id}` for job progress.
    
* **Insights and Analytics Panels:** The Studio also envisions advanced analytics:
    
    * **Time-of-Day Heatmap:** A visualization showing at what times of day tracks occur most often, maybe aggregated by frequency (like a 2D heatmap with time of day vs date)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L49-L56).
        
    * **Pattern Analysis (Binary Pattern)**: Could display the actual bit patterns or frame opcodes frequency to see if certain patterns repeat in tracks.
        
    * **Cadence Dashboard:** Possibly showing periodicity, like if tracks often happen daily at certain times or weekly cycles, drawn as a calendar or timeline.
        
    * **Insights Panel:** Summarizes actionable insights – e.g., “Scripted activity detected, forecast bullish with 80% confidence, next gamma flip at $X, entropy dropping (market increasingly algorithmic).” These insights combine data from summary, options, etc., into plain language for the user (like a commentary).
        
    * **Pattern Alignment (TISA)**: TISA might refer to some Time-Interval Signature Alignment, perhaps an algorithm to align and compare price series of different instances of tracks. They mention comparing price series in UI[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L52-L55) – maybe an overlay of multiple track events normalized to start to see common shape.
        
    * **Diagnostics Panel:** For internal use or advanced users – showing system health (feed status, cache status, recent errors). Possibly listing if any data source (Polygon, B2, Postgres) is not reachable (like a traffic light display). Actually, they added endpoints like `/diagnostics/*` for connection and cache health[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L104-L113)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L552-L560) which presumably feed such a panel.
        

These advanced panels might not all be fully implemented yet but are planned given references in UI standards doc[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L49-L56).

**User Interaction Flow:** A typical user scenario might be:

* User opens Studio, sees on homepage a status “Live” and a quick stat like “3 power tracks detected in last hour on GME”.
    
* User navigates to Tracks Grid, filters symbol = GME, sees a list of recent tracks. One has cluster “Impactor” and high spectral power.
    
* User clicks that track row to open details: a modal shows its price path chart, an interpretation (like “Large upward burst with low entropy – likely algorithmic pump”).
    
* The modal has a button “Show Forecast Impact” which takes them to the composite forecast chart focusing on that time – or maybe highlights on forecast how that track influenced.
    
* Meanwhile, as time passes, a new track comes in (if live). The grid dynamically adds it at top, maybe with a highlight animation. The user hears a sound or sees a notification if enabled (for important cluster types).
    
* The user then checks Macro Tracks tab. They see that in last month, 1 macro chain of 3 segments formed. They click it to expand segments. They might then click “View macro corridor” to see the combined path and how those segments link – maybe noticing an overall downward price corridor spanning weeks (maybe indicating a long manipulation).
    
* The user can then use Orchestration to backfill older data: e.g., they want to see if 2020 had macro tracks. They schedule a harvest and detection job for 2020 data via the Orchestration page: select symbol, date range, submit job.
    
* The Orchestration page shows the job queued, then running (with a log tail possibly), then done. The user can then go to tracks grid, filter date range, and see results.
    
* At any point, the user can bring up the Diagnostics (maybe hidden behind a debug mode) to see system statuses if something seems off.
    

**UI Design Considerations:**  
The UI must remain **high-performance**:

* It updates in real-time without full reloads (SSE/WS push)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L19-L27).
    
* It avoids flicker or heavy re-renders by using virtualization for large lists (the tracks grid could accumulate thousands of entries if left running; virtualization ensures only visible rows render)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L79-L82).
    
* It uses debouncing on search inputs and throttle on resizing etc. to keep it responsive[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L80-L84).
    
* It is accessible (keyboard navigation, high-contrast mode, etc. as listed)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L85-L93)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L93-L101).
    
* It is visually consistent with color coding cluster types (the CompositeForecastChart code had a color map for track types[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/dashboard/components/CompositeForecastChart.tsx#L34-L42), e.g., impactor=red, binder=green, echo=magenta, macro=light blue, etc., and these colors used across UI for labels and lines).
    
* It handles errors gracefully: e.g., if engine is down, instead of crashing, the UI might show an offline mode suggestion “Engine disconnected. Try restarting or check API key.” (But likely the engine will be running if UI is).
    
* If data is not available (like macro endpoints returns empty), UI shows “No macro data” calmly, as indicated in troubleshooting table[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/end-to-end-setup.md#L224-L231).
    

Every element is documented internally with Cursor rules to maintain design consistency (the UI standards doc is part of that). The focus is to make a complex data system intuitive: color-coded, real-time, and interactive with explanatory tooltips for metrics (e.g., hover over “D*” shows what decodability is).

In summary, the Studio UI ties all backend capabilities into an operator-friendly interface. It allows one to monitor real-time tracks, analyze patterns, run historical analyses, and glean insights from the Power Tracks system. The UI is effectively the command center and visualization hub for everything the engine detects.

Orchestration and Workflows
---------------------------

_(This section brings together how historical data processing is orchestrated and how the system can be operated in both live and batch modes.)_

While the engine focuses on real-time detection, the **Power Tracks Pipeline** (historical orchestration) ensures that the system can backfill and maintain a comprehensive database of tracks. The orchestration involves coordinating the Data subsystem, the Engine, and storage tasks.

**Historical Data Ingestion (Power-Tracks-Data):** To analyze past periods or fill gaps, the Data pipeline is used:

* The CLI command `pt-data harvest` fetches raw tick data and minute bars for specified symbols and date ranges from the Polygon API[GitHub](https://github.com/TheGameStopsNow/power-tracks-data/blob/aabfb89e788ea236dee68d9153fd74907821b507/docs/data-pipeline-guide.md#L50-L58). It stores them under `storage/ticks/<symbol>/<YYYY-MM-DD>.csv` and `storage/minute_bars/<symbol>/<YYYY>/<MM>/<DD>/*.json` (or Parquet, depending on config)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/end-to-end-setup.md#L61-L69)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/data-architecture-analysis.md#L7-L16). It can optionally compress or convert them. Data integrity is checked via `pt-data validate` which ensures completeness and computes checksums[GitHub](https://github.com/TheGameStopsNow/power-tracks-data/blob/aabfb89e788ea236dee68d9153fd74907821b507/docs/data-pipeline-guide.md#L54-L62).
    
* Once ticks are available, the orchestration can invoke detection:
    
    * Option A: **Use Engine’s batch mode.** For example, `pte backfill --symbol XYZ --start-date 2024-01-01 --end-date 2024-01-31 --ticks-dir ../power-tracks-data/storage/ticks --out-dir ../power-tracks-data/storage/pipeline_outputs`[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/end-to-end-setup.md#L137-L145)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/end-to-end-setup.md#L141-L149). This command (from engine CLI) would read the tick files for that range, run detection (and perhaps decoding) for each day, and output results in the `pipeline_outputs` directory (which is a similar structure to what a legacy pipeline produced). Specifically, it might output for each day that had a track:
        
        * `pipeline_outputs/<SYMBOL>/<YYYY>/<MM>/<DD>/<track_id>/lag_manifest.json` (the detection output)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/data-architecture-analysis.md#L7-L16).
            
        * Possibly the decode results if the engine is integrated enough to decode on the fly.
            
    * Option B: **Use Legacy pipeline** if it existed (less relevant now since engine replaced it).
        
* After detection runs, we need to ensure the decoded artifacts are present for macro stitching. If the engine backfill didn’t produce the `decoded/<DATE>/tracks.jsonl`, we use the provided script `generateMacroTracksJsonl.ts` to synthesize those JSONL index files from the pipeline outputs[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/end-to-end-setup.md#L123-L131)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/end-to-end-setup.md#L133-L141). Essentially, it scans each daily directory for lag_manifests and compiles a list of tracks with key info into `power_tracks/<SYM>/decoded/<YYYY-MM-DD>/tracks.jsonl` for that day. This is so that macro analysis can treat legacy outputs like live outputs.
    
* **Catalog seeding**: The script `power_track_catalog_seed.js` reads all artifact files and populates the SQLite/PG database accordingly[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-artifacts.md#L32-L40)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-artifacts.md#L34-L39). This step will insert rows into `tracks` table for each detection found in `reports` or `pipeline_outputs`, ensuring the DB reflects reality. It also creates placeholder stage folders for any track that might have been missing some (for consistent structure)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-artifacts.md#L14-L22)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-artifacts.md#L16-L24). After seeding, a `power_track_catalog_report.json` is generated to summarize how many tracks, artifacts per track, and find if any orphans remain[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-artifacts.md#L34-L41)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-artifacts.md#L36-L39).
    
* **Backfill and Refresh Automation:** Ideally, this process (harvest -> detect -> seed -> macro) can be automated nightly. The maintenance roadmap suggests a nightly job to ingest new polygon data, run detection, update catalog, and archive previous snapshots for comparison[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-refactor-plan.md#L54-L62)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-refactor-plan.md#L56-L64). This ensures the data stays up to date even if the engine was offline at some times.
    

The **Orchestration Queue:** The Studio backend now has a minimal async job queue for orchestration (harvest). It can be extended to Redis/BullMQ or Postgres/Graphile Worker for durability, but currently returns real job IDs and exposes `/v1/jobs/{id}` for status. FastAPI endpoints like `start_harvest` kick off the work; live updates flow via `/v1/stream` or `/ws/stream`.

* When user triggers a job via UI, the API enqueues it in Redis (e.g., LPUSH to a list or XADD to a stream consumed by a worker).
    
* A background worker (could be a separate process or thread, maybe the engine itself or a small Python worker) picks up the job and executes `pt-data` or `pte` commands accordingly.
    
* The job’s progress can be monitored. Possibly by tailing logs or by having the worker send periodic status updates (for example, writing to a Redis key or using PubSub events).
    
* Once done, results (artifacts) are in place and the UI can refresh the view (catalog seed might run as part of job or after a series of jobs).
    

The Orchestration page in UI then shows e.g., “Harvest GME Jan 2025 – Completed” and then maybe triggers the macro refresh or instructs the user to refresh macro view. In next iterations, this will be more seamless (jobs chain automatically, e.g., after harvest, run detect, then macro, etc.).

**Integration of Live and Historical Data:** They ensure that the live engine and historical pipeline output end up in the same storage and database:

* The engine’s live detections are written to `data/power_tracks/<SYM>/<ID>/...` and also inserted to DB immediately (if using DB sink). So live results appear in tracks table with detection_mode 'live' (or null).
    
* The pipeline backfill when seeded into DB will fill in older entries that live might have missed (like overnight macro only visible retrospectively).
    
* The macro chains can include both live and backfilled tracks as segments – because macro stitching just looks at all decoded tracks in that range (regardless of when they were added).
    
* If duplicates or overlaps occur (like one track found live and backfill finds it again), the seeding logic needs to reconcile (maybe by matching IDs or times). Ideally, since track IDs include timestamp, a backfill detection of the same event would produce the same timestamp and likely the same ID (if the ID generation uses timestamp + maybe an index). But if not, one could end up with duplicate in DB. The audit script would flag duplicates if found. They might rely on the uniqueness of track IDs as primary key to avoid insertion of duplicates; if a duplicate ID arises, then it's literally the same event. If a track is found in backfill that live missed (maybe because the engine was down), then it gets a new ID and is inserted – which is fine because it was truly missed earlier.
    
* **Provenance tagging:** One idea is to tag tracks with how they were detected (live vs backfill). However, since ultimately they should be identical if conditions were same, this might not be necessary beyond detection_mode if needed.
    

**Failure Modes in Orchestration:**

* If a harvest job fails (network error, etc.), the UI should show it as failed (with a message). The user can retry. The system may implement exponential backoff for API calls. Partial data (like half a day downloaded) is okay; the validation step would catch incomplete data.
    
* If detection (pte backfill) fails mid-run (maybe due to a bug or memory issue), possibly some tracks were written, others not. The catalog seeding after would only include those processed. They might re-run detection for that range. To avoid duplicating partial results, one might clear or mark incomplete tracks and remove them first (the pipeline plan mentions filling missing ledger artifacts for legacy with a script to resolve audit warnings)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-refactor-plan.md#L50-L59)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-refactor-plan.md#L51-L59).
    
* If the macro stitching fails for some reason on a range (maybe not enough data), it returns no macro found (not a crash). The user can adjust parameters and try again.
    

**Determinism and Orchestration:** Running the pipeline multiple times on same raw data should produce the same tracks. The CI likely runs the pipeline on a fixed small dataset as a test each build to ensure no nondeterministic behavior creeps in.

**Continuous Integration of Orchestration:** As mentioned, CI could automatically run a small pipeline example to check all stages. They have steps to ensure no new orphans (meaning if any new artifacts produced by pipeline don’t have a DB entry or vice versa, that’s a problem)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-refactor-plan.md#L2-L5)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-refactor-plan.md#L3-L5). Also, coverage below 100% (meaning maybe not all tracks had all 4 artifact types or some stage missing) would fail CI as well, pushing developers to fix it.

**Deployment Considerations:** The system can be deployed in various modes:

* **Local Dev:** All three repos (data, engine, studio) on one machine, with .env files pointing to each other (ENGINE_REPO_PATH etc.)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/end-to-end-setup.md#L191-L199). Developer runs data tasks manually or via UI.
    
* **Server / Cloud Deploy:** likely on a platform like Railway, they run the engine and API in one container (maybe combined or separate services). Postgres and Redis provided as cloud add-ons. The data harvesting might run externally due to large data pulls (maybe triggered by a GitHub action nightly rather than in Railway due to resource/time constraints? Or using an AWS Lambda for harvest).
    
* **Airflow or others:** The roadmap considered possibly using a more robust orchestrator (Airflow/Dagster) if pipeline becomes complex[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-refactor-plan.md#L38-L41). For now, simpler scripting suffices.
    

**Failover / Data Consistency:** Since the artifact storage is the ultimate truth, even if DB is lost, one could rebuild it by re-running `catalog_seed.js` on the artifacts. They regularly produce `power_track_catalog_report.json` which can be monitored (e.g., ensure track counts increasing daily or stable). They even consider pushing metrics from that report to monitoring (Grafana)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-refactor-plan.md#L62-L69)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-refactor-plan.md#L63-L66) to get alerted if something off (like orphan count > 0 unexpectedly).

With orchestration in place, the system ensures that both historical and live data can be analyzed uniformly. Operators can investigate past patterns just as easily as current activity, making the Power Tracks system a comprehensive tool for both real-time monitoring and historical research.

Data Storage, Formats, and Persistence
--------------------------------------

_(This section recaps the data storage conventions, databases, and file formats used throughout the system, consolidating from earlier mentions.)_

**File-system Repository (Local/Cloud):** All track-related artifacts are organized under a base directory (often referred to by the environment variable `ENGINE_DATA_PATH` or `DATA_STORAGE_PATH`). Within this, the standardized structure is:

```
data/power_tracks/<SYMBOL>/<TRACK_ID>/
    raw/        (raw inputs like tick ledger, original detection files)
    decoded/    (decoded frames and unfolded paths)
    analytics/  (analysis outputs like manifest, summaries, metrics)
    visuals/    (visual artifacts: spectrogram images, thumbnails)
```

This structure is enforced by the refactored pipeline as canonical[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-artifacts.md#L14-L22). For example:

* `raw/ledger.csv` might contain the tick-by-tick log around detection (with columns timestamp, price, volume, exchange).
    
* `raw/minute_candidates.csv` could list all 1-minute bars in that day with a flag if that minute had any spectral spike (legacy output).
    
* `decoded/frames.parquet` or `.json` holds the decoded frame data for that track (each frame’s fields opcode, version, etc., plus decoded varints).
    
* `decoded/path.csv` holds the unfolded price path (timestamp vs price points of the corridor).
    
* `analytics/lag_manifest.json` is a JSON containing detection metrics (window size, power, ROC, D, etc.), possibly some aggregated info from frames (like timescale_summary, if available).
    
* `analytics/corridor_summary.json` might summarize the min/max envelope of the path.
    
* `visuals/spectrogram.png` an image of the FFT spectrum for the window, useful for analysts to confirm the frequency content.
    
* `visuals/corridor_plot.png` could be an automatically generated chart of the price path vs actual price if available (perhaps created in analysis stage).
    
* There could also be a `detect/` stage if splitting detection-phase artifacts, but in design they merged detect outputs into raw or analytics.
    

**Naming Conventions:** Track directories are named by `TRACK_ID`, which includes date and time, ensuring uniqueness and lexicographical ordering by time. E.g., `PT-20250115-093000-0001` could indicate a track detected Jan 15 2025 09:30:00, ID 0001. This ID is used throughout (filename references, DB primary key). The use of uppercase/lowercase in symbol is consistent (e.g., all directories are perhaps uppercase symbol) – the code lowercases symbol for filenames sometimes (noted in JSON minute bars code)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/data-architecture-fixes.md#L44-L52)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/data-architecture-fixes.md#L46-L54). The pipeline ensures to use one format to avoid duplicates (e.g., `GME` vs `gme`).

**PostgreSQL (or SQLite) Schema:**

* **power_tracks (tracks) table:** Each row corresponds to a track. The main fields were discussed; likely DDL would be:
    

```sql
CREATE TABLE power_tracks (
    id TEXT PRIMARY KEY,
    symbol TEXT,
    timestamp TIMESTAMPTZ,
    spectral_power DOUBLE PRECISION,
    roc_value DOUBLE PRECISION,
    venue TEXT,
    cluster_type TEXT,
    regime TEXT,
    detection_mode TEXT,  -- e.g., 'live' or 'macro_chain'
    payload JSONB,        -- stores decodability metrics, timescales, etc.
    created_at TIMESTAMPTZ DEFAULT now()
);
```

Indices on (symbol, timestamp) for retrieval by symbol and time. Possibly a gist index on payload->decodability for querying by D range if needed (unlikely).  
For macro chains, special handling: when macro is inserted, cluster_type might be 'macro', detection_mode 'macro_chain'. The `payload` might store the segments: e.g., an array of track IDs included, plus the combined corridor in some compressed form (maybe not full, but key points). Alternatively, they could store macro details in separate table, but the audit doc suggests they just mark it in same table[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L42-L48).

* **Artifacts table:**
    

```sql
CREATE TABLE power_track_artifacts (
    track_id TEXT REFERENCES power_tracks(id),
    stage TEXT,    -- 'raw','decoded','analytics','visuals'
    artifact_type TEXT,  -- e.g., 'ledger', 'frames', 'spectrogram'
    path TEXT,     -- e.g., 's3://bucket/artifacts/GME/PT-.../raw/ledger.csv' or relative 'GME/PT-.../raw/ledger.csv'
    size_bytes BIGINT,
    hash_sha256 TEXT
);
```

Composite primary key (track_id, stage, artifact_type) or an internal serial. This table is populated by inventory script; it's mainly for audit and possibly retrieval (the Studio backend might query it to find a link to say spectrogram image to display).  
But if using object store, one might just construct URLs from known patterns rather than DB.

* **orphan_artifacts table:** For audit:
    

```sql
CREATE TABLE orphan_artifacts (
    path TEXT PRIMARY KEY,
    found_at TIMESTAMPTZ
);
```

The inventory script finds files in storage that it cannot associate with any track_id in DB, and logs them here for review. Ideally empty after migration.

* Possibly **power_track_analysis table** if they wanted to store daily summary stats like total tracks per day, etc., but not mentioned. Instead, those summaries (like tracks_by_type per day) might be computed on the fly or stored in JSON inside power_tracks under certain pseudo-IDs (the openapi had DailyStats schema for state endpoint)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/openapi/power-tracks-engine.yaml#L214-L222)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/openapi/power-tracks-engine.yaml#L224-L232). Actually, `DailyStats` appears to be for summarizing tracks counts by type in a date range for a symbol, likely used in UI analytics.
    

**Redis usage recap:**

* The `Cache` class in Studio backend likely uses Redis to cache entire responses for short periods (like 30s) to reduce load on engine for heavy endpoints (state, forecast)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L90-L99)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L92-L100). It uses keys like `pt:v1:state:GME:2025-11-09`. The cached data also includes a `.cache` field when returned to indicate if it was live or fallback[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L96-L104)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L98-L104). This mechanism means if UI is refreshing state often or multiple users request same symbol, it will mostly hit cache, not engine each time.
    
* RateLimiter uses Redis to count requests per IP[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L30-L38)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L32-L35). It probably uses a key with IP and minute. The config `api_rate_limit_per_minute` is used.
    
* Orchestration job queue if using Redis: keys possibly `pt:jobs` list or `bull:...`. Not finalized in text, but something to consider.
    
* Engine use of Redis Streams: if implemented, maybe `pt:stream:tracks` or similar for detection events.
    

**Server-Sent Events format:** SSE is just a text stream. The format they send in code is:

```
event: snapshot
data: {"symbol":"GME", "date":"2025-11-09", "generated_at":"...","state":{...}, ... }
```

This repeats, separated by blank line. The UI EventSource picks up `event: snapshot` and then JSON parse the data. They do this instead of default event (which would be `message`) so they can potentially have multiple event types (they have 'error' events too)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L718-L725). The SSE event frequency is controlled by `stream_interval_seconds` (likely configured to a few seconds)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L652-L660).

**DataRetention and Archiving:** They plan for data archiving strategies long-term:

* The `storage-migration.md` suggests eventually moving all artifacts from local to Backblaze B2 cloud (phase 2)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/state-cards/storage-migration.md#L14-L19)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/state-cards/storage-migration.md#L30-L38). After that, the local storage might be pruned.
    
* Archiving old tracks: They consider when to compress or remove old ones[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/data-architecture-analysis.md#L75-L82)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/data-architecture-analysis.md#L77-L85). Possibly anything older than a year could be zipped or moved to a cold storage. But they'd maintain at least catalog entries to know it existed.
    
* Because tracks are relatively small (just JSON and images, maybe a few KB each plus possibly some MB if including tick data), they could keep a lot. But if thousands of tracks accumulate, listing performance might degrade. That’s where using Postgres helps for queries and possibly partition by date or symbol.
    

**Deterministic Data Handling:**

* File writes are done in a specific order to avoid partial updates (maybe writing to temp then renaming).
    
* Hashes (like SHA256) of raw ledgers can allow verifying no tampering or corruption. The audit recommended storing manifest hash in SQLite payload[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L22-L26)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L2-L5). It's not confirmed they implemented it yet, but it's advisable. They do ensure minute bar fallback uses vetted data only (no placeholder)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L60-L65).
    
* If any mismatch is found in monthly audits (like a track's ledger changed or a track missing an artifact), they log it and possibly fix by re-harvesting or re-seeding.
    

All these details ensure that engineers working on each part (data, engine, UI) know exactly where data resides, in what format, and how it flows through the system – enabling stable, repeatable operations and easier debugging when issues arise.

Testing, Validation, and Quality Assurance
------------------------------------------

Quality assurance in the Power Tracks system spans multiple levels: unit tests for algorithm correctness, integration tests for end-to-end behavior, and continuous validation against the research criteria and real-world data.

**Unit Tests (Engine):** The engine repository includes tests for:

* **Detection Algorithm:** using small synthetic tick sequences to trigger or not trigger detections. For example, feeding a sine-wave-like tick pattern of 0.5 Hz with a price jump should yield a detection. Tests cover threshold enforcement (ensuring that with power just below 10000 no detection, at 10000 detection occurs, unless override flag is set)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L9-L17). They likely also test the guardrails: if one tries to initialize detector with freqRange outside allowed, it clamps and logs a warning (the test can capture the warning).
    
* **Decoding Routine:** Possibly test decoding on known encoded data. If any example of frames (maybe from historical known track or artificially encoded frames) is available, they ensure `decodeTrackBurst` returns expected frames and path[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/packages/core/README.md#L85-L93)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/packages/core/README.md#L95-L103). If not actual, they might test components like the mask search function by constructing a bitstream with a known mask and checking it finds it.
    
* **Utility Functions:** e.g., computing decodability metrics – test that `computeDecodabilityScore` returns correct D and D* for given inputs (the function might implement a formula combining bandpower, entropy, varint success rates). Without actual formula given here, they'd confirm that certain edge input yields expected result (e.g., if varintSuccess=1 and entropy low, D high).
    
* **Storage Adapters:** tests for the storage interface: storeCandidate writes to SQLite and can retrieve it, custom storage stub behaves, etc.[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/packages/core/README.md#L61-L69)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/packages/core/README.md#L67-L75). They might use a temporary SQLite for testing and ensure retrieving yields same data, and listCandidates with filters works (like filtering by symbol returns those records).
    
* **Edge cases:** no ticks (should not detect), constant price (should not detect any high ROC but maybe triggers low-power track? Should not), extreme volume spike (the engine isn't explicitly thresholding volume now, but tests might verify it can handle huge volume values).
    
* **Performance**: They include a performance harness (there's mention of `npm run perf:load` in runbook)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/runbook.md#L45-L48), but in CI they might not run heavy perf tests, rather use smaller data and ensure it completes within time.
    

**Integration Tests (Engine & Pipeline):** These simulate realistic scenarios:

* **Live Tick Stream Simulation:** Feed a sequence of ticks through the `PowerTrackDetector.processTick()` method (maybe via a stubbed Polygon feed) and verify that expected track events are emitted. They may use known historical data (like the famous GME Jan 2021 events) truncated to a short snippet that definitely triggers tracks. Compare the output track’s attributes with known good values (like if we know around 10:05 there was a track with certain spectral power, check it).
    
* **Full Pipeline Backfill Test:** Using the `power-tracks-data` component, run a small harvest for e.g., 1 day 1 symbol, run detection via engine CLI, then run catalog seed, and finally call the macro stitch. Assert that:
    
    * The track count in DB matches the number of track files created.
        
    * The macro result, if expected (maybe if there were 0 or 1 tracks, macro should output none with status empty).
        
    * If using a known scenario with two artificially linked days, macro outputs 1 chain with those two.
        
    * The JSON reports (inventory, catalog report) have no orphans and 100% coverage (the test can parse the report JSON).
        
* **API Endpoint Tests:** Using a test client (maybe via FastAPI’s TestClient or just requests to running engine in CI container):
    
    * call `/v1/tracks?symbol=XYZ` after seeding test data, ensure it returns that track with correct fields.
        
    * call `/v1/track/path?track_id=...` and ensure the data points correspond to the known path from decode output.
        
    * call `/v1/state?symbol=...` after loading some minute data (maybe load artificial OHLC with a scripted state pattern) and ensure the response includes arrays of correct length and includes the “state” classification (if test data included a scripted period, perhaps mark it and see if state array labels it as such).
        
    * call `/v1/forecast` given a scenario – might be tricky without launching the full SSE loop. But maybe test the computeForecastPayload function directly: give it a sample state_payload (with say a rising close series, known ATR, D) and check the returned path values follow the linear formula expected[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L680-L689)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L682-L690). For instance, put closes = [100, 101, 102], ATR ~1, D=0, expecting slope ~+1, confidence_scale ~1, band ~maybe something slight above 1, etc. That could be a straightforward numeric test of forecast logic.
        
* **UI Tests:** Possibly they have some end-to-end tests (maybe Cypress or Playwright) that spin up the environment with dummy data and simulate user flows:
    
    * Ensure that when a track event is emitted on WebSocket, the tracks table updates in the UI within, say, 1s.
        
    * Ensure filtering and sorting in UI produce correct ordering (maybe by mocking the API responses).
        
    * Ensure that toggling “include macro” indeed shows macro entries (for that, stub the API to return a macro track).
        
    * Visual regression tests might be used for charts (maybe comparing known chart screenshot with expected – but that’s advanced, maybe not yet in scope).
        

**Research Validation Tests:** They also ensure the system adheres to research spec:

* They might run the detector on known synthetic cases from research paper examples and see if the detection happens where expected.
    
* Confirm default config always uses research-approved values. Possibly a test that loads engine.config.yaml and asserts window=60, power_thresh=10000, etc., matching the document.
    
* Test that enabling the override (ALLOW_NON_COMPLIANT) indeed allows a custom threshold. (i.e. set env var in test, then instantiate detector with threshold 0.001 and see that it doesn’t clamp or warn).
    

**Metrics Validation:** They likely verify that decodability D is computed correctly:

* Perhaps they have a test for `classifyRegime`: feed it metrics with D and entropy values and check it returns 'scripted' if D > D* and entropy low, 'organic' if D low etc., based on chosen logic. Because they said it’s not implemented fully, maybe just test that function returns one of three strings for any given input (like never error out).
    
* Similarly, verify that the telemetry events include expected fields. If they have a test hook for events, ensure that when detector emits candidate, the event object contains id, symbol, spectralPower, roc, etc. matching the candidate’s properties.
    

**Continuous QA:**

* The research audit doc itself is a checklist they might semi-automatically verify. For items like "D not implemented", they may mark them as expected fails for now until implemented. But things like "validateRealData ensures no synthetic data" they can test by feeding synthetic data and ensuring it rejects or cleans it (e.g., if tick price is a placeholder like 0 or -1, the validate function might throw an error).
    
* Weekly or monthly, an engineer or automated job might run an **end-to-end audit**: run the pipeline on recent data, then cross-check:
    
    * Did any expected track not occur? (maybe by comparing to an external source or known events – not trivial to automate unless they have known bench scenarios).
        
    * Are any tracks out of compliance (like cluster=macro with only 1 day, which shouldn’t happen because minDays=3; if it did, that’s a bug).
        
    * Are the number of tracks plausible (not skyrocketing erroneously)? If one day yields hundreds of tracks, maybe a threshold issue.
        
    * They keep an eye on `scripted_pct` from summary – if it suddenly reads 100% for a long time, maybe the classifier is overzealous or data is weird.
        

**CI with Real Data:** Possibly they incorporate a small real dataset (maybe from a calm day and a volatile day) into the test suite (if licensing allows storing it) to ensure system doesn’t break on actual shapes. E.g., embed a 5-minute snippet of GME trading around Jan 28, 2021 (when known anomalies occurred) and assert it finds something, or at least doesn’t error. They have to be careful with sharing market data though; if not allowed, they rely on synthetic generation or user-provided logs.

**Deterministic Output Tests:** A powerful test is to run detection on the same input twice and compare output bit-for-bit. They could do that within a single test run (no randomness should yield identical objects). Also, run on two different OS or Node versions – the CI might cover multiple platforms (maybe in matrix, run tests on Linux and Windows) to catch any non-deterministic issues (like file system differences or float rounding differences).

**Memory/Performance Tests:** They may simulate heavy load (like continuous ticks at high rate for some minutes) to ensure no memory leaks (observing that after GC, memory usage returns to baseline). They might use Node’s --inspect or other tools in dev to monitor that. The runbook/perf notes likely inform that (there’s a `perf:load` script presumably to feed a high-volume data to measure throughput)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/runbook.md#L45-L48).

**CI/Deployment gating:** They have set up branch protection likely requiring all tests pass and the CI pipeline (with catalog consistency checks) to pass before merging. Also, releasing to production might require an explicit manual review but the templates are ready to deploy as soon as main is updated, indicating a continuous deployment style.

**QA Team Manual Testing:** If there’s any manual QA, they would use the Studio UI extensively on a staging environment:

* They might replay known historical extreme scenarios (like memestock saga, a crypto flash crash) and verify the system behaves logically (detects tracks in chaotic times but not too many false ones in quiet times).
    
* They verify UI usability (all buttons, filters working, no crashes on switching symbols rapidly, etc.).
    
* They test resilience: e.g., kill the engine process while UI running (simulate engine down) and see UI shows error properly and recovers when engine back up (the SSE should reconnect).
    
* They test cross-compatibility: various browsers (Chrome, Firefox, Safari) for UI, and integration with other systems if any (like ensure the Python client generation from OpenAPI can call the engine without issues).
    

By maintaining this comprehensive set of tests and validations, the team ensures that the Power Tracks system remains reliable, scientifically valid, and robust against both expected and unexpected conditions. Every new code change is checked against this suite to prevent regressions, making this technical specification not just documentation but also a baseline for ongoing quality control.

Deployment and CI/CD
--------------------

The Power Tracks system is deployed through a combination of containerization and cloud services, with an emphasis on reproducibility and ease of scaling. The project uses a modern DevOps approach to integrate testing, deployment, and monitoring.

**Containerization:** All components (Engine, Studio API, Studio UI, plus dependencies like Redis, Postgres, MinIO) are containerized via Docker. A **docker-compose.yml** is provided in power-tracks-studio repository to orchestrate a full stack for local or server use[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/end-to-end-setup.md#L201-L209)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/end-to-end-setup.md#L211-L219). The compose defines services:

* `db`: Postgres database (with a volume for persistence).
    
* `redis`: for caching and job queue.
    
* `minio`: an S3-compatible object store (with environment setting up a default bucket). It’s used to simulate B2 cloud storage; it stores artifacts in containers and can be accessed via S3 API (the Studio API might use boto3 to talk to it using credentials given in .env)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/end-to-end-setup.md#L191-L199)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/state-cards/storage-migration.md#L46-L55).
    
* `engine`: the Node.js Power Tracks Engine service. Possibly built from the power-tracks-engine Dockerfile, running `npm start` (Fastify server on port 4020).
    
* `api`: the FastAPI backend, built from power-tracks-studio/api Dockerfile, on port 8000, which connects to engine (ENV ENGINE_HTTP_URL) and uses the same Redis/DB.
    
* `studio`: the Next.js front-end, built from power-tracks-studio/dashboard Dockerfile, served (maybe via Node or static export served by nginx) on port 8080.
    

The environment variables (in .env files) tie them together:

* `ENGINE_HTTP_URL=http://engine:8001` is used by API to call engine (note: engine in container listens maybe on 8001 internally)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/end-to-end-setup.md#L191-L199)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/end-to-end-setup.md#L201-L209).
    
* `POLYGON_API_KEY`, `DATA_STORAGE_PATH=/app/data` etc. The `DATA_STORAGE_PATH` is mounted so all containers see the same data volume at /app/data (compose uses volumes or bind mounts for ../power-tracks-data/storage -> /app/data in each container)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/end-to-end-setup.md#L201-L209)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/end-to-end-setup.md#L207-L215). This ensures the engine and API and MinIO are all looking at the same actual artifact files. For example, engine writes to /app/data/power_tracks, and MinIO might also serve /app/data as an S3 bucket (if configured that way).
    

**Cloud Deployment:** They have templates for Railway and Render:

* **Railway:** a railway.json is present, likely defining services (maybe one combined or separate)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/MIGRATION_SUMMARY.md#L28-L36). Possibly they run as separate Railway services (one for engine+api, one for UI as static site, one for DB via Railway's plugin, one for Redis plugin). Railway allows one-click deployments, so presumably in README they’ll include “Deploy on Railway” button.
    
* **Render:** similarly, a render.yaml for infrastructure as code specifying the Docker images to run, environment variables, and connecting to a managed Postgres/Redis or running their own in containers[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/MIGRATION_SUMMARY.md#L28-L36).
    
* For Backblaze B2, they might not spin up a container; rather, you’d supply B2 credentials in env and the system will use B2 cloud directly in production (MinIO would be only for dev). The config file had B2 details with environment override capabilities[GitHub](https://github.com/TheGameStopsNow/power-tracks-data/blob/aabfb89e788ea236dee68d9153fd74907821b507/docs/data-pipeline-guide.md#L120-L129)[GitHub](https://github.com/TheGameStopsNow/power-tracks-data/blob/aabfb89e788ea236dee68d9153fd74907821b507/docs/data-pipeline-guide.md#L168-L176). On Railway/Render, those env vars would be set, and likely one would not run the minio container; instead, the API would connect to B2 endpoints. The migration summary emphasizes moving to B2 for production storage[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/state-cards/storage-migration.md#L50-L58)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/state-cards/storage-migration.md#L52-L55). So the docker-compose might be for dev; in production, they'd omit minio and point to B2.
    

**CI Pipeline:** GitHub Actions (or similar CI) is configured to run on push:

* It checks out code, sets up Node (for engine & UI tests), Python (for API tests), Postgres service (to run integration tests for DB code), and maybe Redis.
    
* Steps:
    
    1. **Install dependencies** for each component.
        
    2. **Run linters/formatters** (ensuring code style consistent).
        
    3. **Run unit tests** for engine (`npm run test` in engine package).
        
    4. **Run API tests** (maybe `pytest` for FastAPI app).
        
    5. **Run any UI tests** (maybe `npm run test` in dashboard if they wrote any using React testing library).
        
    6. **Build the Docker images** to ensure dockerfiles are up to date (and maybe push to registry if needed).
        
    7. **Integration tests** – possibly via docker-compose up in CI to simulate a mini deployment:
        
        * Spin up engine, db, etc.
            
        * Run a script to feed sample data to engine and call APIs to validate they all work in a deployed-like environment.  
            They might instead just do this via invoking API functions directly in tests (the adapter classes allow integration testing without actual network).
            
    8. **Check data integrity** – the earlier described `power-track:ci` which does inventory and ensures no orphans etc., might be run as `npm run --workspace @powertracks/engine power-track:ci` or similar. The YAML snippet in docs suggests they run a CI pipeline where:
        
        * They use secrets for polygon if needed,
            
        * They run `npm run power-track:ci -- --report` in staging to produce a report[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-refactor-plan.md#L100-L108)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-refactor-plan.md#L111-L115).  
            Possibly in CI, they'd run a subset because full inventory of all tracks is heavy. More likely, that step is used in a nightly job or as part of a deployment gating.
            
    9. **Publish artifacts** – e.g. if tests pass, publish NPM package (maybe automatic version bump if they decided to), or container images. They likely push images to GitHub Container Registry or Docker Hub for the `engine`, `api`, and `studio` services. The Railway/Render might be configured to pull latest images from these or build from repo on deploy.
        
* The CI ensures that at all times main branch is deployable and passes all tests, following the criteria:
    
    * 0 test failures
        
    * 0 audit warnings (like orphan artifacts)
        
    * 100% coverage on critical pipeline (they might enforce some threshold for test coverage as well with codecov, but not mentioned).
        

**Release Workflow:**

* For the NPM package `@powertracks/core`, they might manually update version in package.json and run `npm publish`. Possibly automated via CI on tagging a release. The architecture mentions publishing the core package for external integration[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L99-L107).
    
* The OpenAPI spec for engine is part of code; maybe they publish that to some URL or include in distribution for clients to generate their own.
    
* The UI being static can be served on e.g. GitHub Pages or a CDN, but since it’s interactive with API, they likely serve it via the Node server in container.
    

**Monitoring & Alerts:**

* They integrate Prometheus metrics; a running production deployment would scrape the `/metrics` endpoint of engine (and possibly FastAPI if it exposes any custom metrics).
    
* Prometheus/Alertmanager can then alert on conditions defined (like no detections in >30 min, feed reconnect storm, sink errors as given in runbook)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/runbook.md#L19-L27)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/runbook.md#L20-L28).
    
* They likely also monitor the SSE feed: maybe a browser or agent that ensures SSE is sending data (though Prom metrics about last detection timestamp partly cover that).
    
* The UI might have some built-in alert banner if certain conditions (like if summary shows `scripted_pct` spiking or an error event came) – but generally rely on back-end monitoring.
    

**Rollback Strategy:** If a deployment goes bad (e.g., a bug causes false detections), they can:

* Rollback container images to previous stable versions (Railway/Render allow redeploying an earlier commit or image).
    
* The database migrations: if any, are likely additive so rollback isn't complex (e.g. if they drop a column, they'd ensure backward compatibility).
    
* The data (artifacts) remain and are forward-compatible usually, so a new engine version reading old artifacts or vice versa mostly okay (worst-case some new fields missing but should not break core functionalities).
    

**Deterministic Environments:** They pin dependencies (specific version ranges) and use lock files (package-lock for Node, requirements.txt for Python) to ensure the environment is consistent between developer machines and CI. The MIGRATION_SUMMARY shows they cleaned up multiple lockfiles to avoid confusion[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/HOUSEKEEPING.md#L32-L40)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/HOUSEKEEPING.md#L34-L38) (ensuring one source of truth for dependencies).

**Security Considerations:**

* API keys are kept out of code, loaded from env (and not logged).
    
* They might integrate a basic auth or require engine API key even internally (Studio API likely sets `X-API-Key` when calling engine using the one from its env).
    
* CORS is configured to allow the front-end origin to call the API (in dev open to all)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L43-L50)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L44-L48).
    
* Data in transit: if deploying on cloud, they'd use HTTPS (Railway/Render handle TLS termination).
    
* They mention OAuth proxy possible in front of engine for external access[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L91-L95), which means if exposing to outside users, they'd put an auth layer; for now, probably just API keys since it's internal.
    
* They consider gating some endpoints (like heavy ones) with proper caching and rate limits to avoid abuse.
    

In summary, the CI/CD and deployment strategy is designed so that the Power Tracks system can be reliably updated with minimal downtime and immediate feedback if something goes wrong. The comprehensive tests and monitoring ensure that any deviation is caught quickly, making the system stable for production use.

Appendices
----------

### A. Engine Configuration Defaults

_(Key default values and thresholds used in the engine, for reference)_

* Detection window: **60 seconds**; Step (scan interval): **10 seconds**[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L30-L38)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L34-L42).
    
* Frequency band: **0.5 Hz to 3.0 Hz** (target band for spectral power)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L30-L38).
    
* Spectral power threshold: **10,000** (in band power units)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L34-L42).
    
* ROC threshold: **0.7%** (5-second price change)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L34-L42).
    
* Volume/quality checks: (In research: SNR ≥15 dB, completeness ≥99%; engine currently logs but doesn’t enforce)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L12-L16).
    
* Decodability: D and D* not yet set in config (planned to calibrate; initially treat D* as threshold like 0.5 meaning 50% decodable frames might be considered sufficient).
    
* Macro stitching minDays: **3** days by default[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L62-L70).
    
* Macro mask drift tolerance: **±1** (mask code difference)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L14-L19).
    
* Macro lookback: **180** trading days default[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L34-L38).
    
* Engine data mode default: “**filesystem**” if ENGINE_DATA_PATH given; otherwise “polygon” (live feed) if API key present. It will autodetect order of sources as per priority built[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/engine_adapter.py#L140-L148)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/engine_adapter.py#L155-L163).
    
* Engine service port: **8001** (in Docker compose, mapped to host 4020) – health at `/health`, API at `/v1/...`.
    
* API rate limit: default e.g. **60 requests/minute** (configurable, in Settings).
    
* SSE stream interval: **3 seconds** (for example, to push updates; actual value from `settings.stream_interval_seconds`, often 2–5 sec).
    

### B. Data Schema Examples

**PowerTrack (JSON example):**

```json
{
  "id": "PT-20250115-093000-0001",
  "symbol": "GME",
  "timestamp": "2025-01-15T09:30:00-05:00",
  "spectral_power": 15600.5,
  "roc_value": 0.0081,
  "venue": "XNYSE",
  "cluster_type": "impactor",
  "decodability": {
    "d_score": 0.85,
    "d_star_score": null, 
    "frames_decoded": 12,
    "frames_total": 14,
    "varint_success_rate": 0.92,
    "entropy": 0.7
  },
  "regime": "scripted"
}
```

_(If decodability not computed, d_score may be null and regime default to "organic".)_

**Lag Manifest (lag_manifest.json) example:**

```json
{
  "track_id": "PT-20250115-093000-0001",
  "symbol": "GME",
  "detection_ts": "2025-01-15T09:30:00Z",
  "window_sec": 60,
  "spectral_power": 15600.5,
  "roc": 0.0081,
  "volume": 35000,
  "quality": {
    "snr_db": 18.2,
    "venue_completeness": 0.998
  },
  "metrics": {
    "decodability": 0.85,
    "entropy": 0.7,
    "regime": "scripted"
  },
  "timescale_summary": [
    {"timescale": "intraday", "horizon_seconds": 14400}, 
    {"timescale": "swing", "horizon_seconds": 604800}
  ]
}
```

(This manifest includes detection info and a snippet indicating from decode that there were intraday and swing-term frames, 4h and 7-day respectively.)

**Decoded Frames (frames.json) excerpt:**

```json
[
  {
    "index": 0,
    "opcode": 5,
    "version": 1,
    "start_offset_ms": 0,
    "duration_scale": 3,
    "compression": 0,
    "anchor_price": 1600, 
    "volume_code": 10,
    "decoded_payload": [ 420,  7,  -3 ],
    "meaning": "Project +4.20% over 7 days, slight pullback -3% mid-way",
    "crc_ok": true
  },
  {
    "index": 1,
    "opcode": 9,
    "version": 1,
    "start_offset_ms": 600000,
    "duration_scale": 1,
    "compression": 0,
    "anchor_price": 1650,
    "volume_code": 8,
    "decoded_payload": [  50, -10 ],
    "meaning": "After 10min, pivot: drop 1.0% then recover",
    "crc_ok": true
  }
]
```

**Composite Forecast (API /v1/forecast) example:**

```json
{
  "symbol": "GME",
  "generated_at": "2025-01-15T09:45:00Z",
  "history": [
    {"ts": 1610716200000, "value": 16.5, "upper": 16.8, "lower": 16.2, "confidence": 0.5},
    {"ts": 1610716260000, "value": 16.7, "upper": 17.0, "lower": 16.4, "confidence": 0.55},
    ...
  ],
  "path": [
    {"ts": 1610716320000, "value": 16.9, "upper": 17.3, "lower": 16.5, "confidence": 0.6},
    {"ts": 1610716380000, "value": 17.0, "upper": 17.4, "lower": 16.6, "confidence": 0.6},
    ...
    {"ts": 1610717220000, "value": 17.5, "upper": 17.9, "lower": 17.1, "confidence": 0.7}
  ],
  "horizon_minutes": 15,
  "tracks": [
    {"label": "Composite", "weight": 1.0, "confidence": 0.6, "entropy": 0.7}
  ],
  "spot": 16.7
}
```

**Streaming SSE snapshot example (event: snapshot):**

```json
{
  "symbol": "GME",
  "date": "2025-01-15",
  "generated_at": "2025-01-15T09:45:00Z",
  "state": {
    "ts": [1610715600000, 1610715660000, ..., 1610716260000],
    "open": [15.8, 15.9, ..., 16.7],
    "high": [15.95, 16.1, ..., 16.8],
    "low":  [15.7, 15.85, ..., 16.6],
    "close":[15.9, 16.0, ..., 16.7],
    "volume": [...],
    "state": ["organic","organic",...,"scripted"],
    "upper": [16.2, 16.3, ..., 17.0],
    "lower": [15.6, 15.7, ..., 16.4],
    "D": [0.1, 0.2, ..., 0.85],
    "entropy": [0.95, 0.9, ..., 0.7]
  },
  "flip": {
    "boxes": [
      {"ts": 1610715900000, "price": 16.2, "type": "high"},
      {"ts": 1610716080000, "price": 15.9, "type": "low"}
    ]
  },
  "summary": {
    "symbol": "GME",
    "date": "2025-01-15",
    "last_price": 16.7,
    "scripted_pct": 0.5,
    "scripted_bars": 30,
    "forecast_conf": 0.6,
    "horizon": 15,
    "hinge_count": 2,
    "options_msg": "Call OI peak @ $18, Put support @ $15",
    "coverage": 0.9,
    "sample": 50,
    "avg_band_pct": 0.02,
    "last_error_pct": 0.005
  },
  "options": {
    "asof": "2025-01-15T09:40:00Z",
    "hinges": [15, 18],
    "message": "Max Pain at $16, major OI at $18 call and $15 put"
  },
  "forecast": { ... as per /v1/forecast above ... },
  "composite": {
    "asOf": "2025-01-15T09:45:00Z",
    "tracks": [
      {
        "trackId": "PT-20250115-093000-0001",
        "cluster": "macro",
        "segment_count": 3,
        "path": [ ... combined macro path points ... ]
      }
    ]
  }
}
```

_(Note: composite field is optional; here assuming engine supports a composite snapshot such as active macro chain data or multi-track overlay.)_

### C. Glossary of Terms

* **Power Track:** A short-term market event characterized by periodic microstructure activity and rapid price change, believed to encode future price movement instructions.
    
* **Burst:** The raw manifestation of a Power Track in tick data – a flurry of trades in a short time.
    
* **Detection Window:** Time window of tick data analyzed at once for spectral/ROC signals (default 60s).
    
* **Spectral Power:** The amount of signal energy in the target frequency band (0.5–3 Hz) for the window – high values indicate a periodic signal likely present[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L30-L38).
    
* **ROC (Rate of Change):** Price change over a short interval (5s default) in the window, expressed as a fraction or percentage.
    
* **Decodability (D):** A metric from 0 to 1 indicating how well the burst could be decoded into frames (higher means more of the encoded message was recovered).
    
* __D_ (D-star):_* A threshold or expected decodability needed to have confidence in interpretation; if D ≥ D*, the track is likely actionable.
    
* **Regime Classification:** Categorization of market behavior during the track – _scripted_ (algorithm-dominated, low entropy), _organic_ (natural, high entropy), _transitional_ (mix)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L38-L44).
    
* **Frame:** In decoding, a fixed-size chunk of bits (56 bits) containing one instruction or part of the encoded message[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L128-L136).
    
* **Mask (XOR mask):** A 6-bit key used to obfuscate the bits in the burst; found by trying all 0x00–0x1F possibilities[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L91-L100).
    
* **Varint:** A variable-length integer encoding (7 bits per byte with continuation), used to encode numeric fields compactly in frames[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L111-L119).
    
* **Zigzag Encoding:** A way to map signed integers to unsigned for varint (to encode negative numbers efficiently)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L113-L121).
    
* **Unfolding:** Converting the decoded frame instructions into an actual time-price path (price trajectory) – essentially “executing” the encoded plan to see the effect on price over time.
    
* **Macro Track:** A multi-session phenomenon where consecutive days’ tracks form a continuous larger pattern. Essentially a chain of daily Power Tracks interpreted as one extended instruction sequence[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L10-L18).
    
* **Mask Drift:** Small changes in the XOR mask between related tracks (±1 tolerance means yesterday’s mask 0x0E and today’s 0x0F can still be linked)[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L14-L19).
    
* **Active Window (Macro):** The forward time span after a track during which a subsequent track is considered part of the same macro chain if alignment conditions hold (e.g., next ~5 trading days).
    
* **Composite Forecast:** The unified price forecast that blends all current signals (track projections, trend, volatility) into a single prediction band for the near future.
    
* **IVCM:** Implied Volatility Corridor Model – the forecasting methodology using implied/realized volatility and track-driven confidence to produce upper/lower price bounds (the “corridor”).
    
* **Confidence (Forecast):** A value in [0,1] indicating confidence in forecast; used inversely to widen/narrow the predicted price band (low confidence => wide band)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L680-L689)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/polygon_proxy.py#L682-L690).
    
* **Studio:** The front-end dashboard for visualizing Power Tracks data and controlling the pipeline (includes UI and FastAPI backend).
    
* **Orchestration:** Coordinating data fetching, detection on historical data, and other batch processes, usually via a job queue system and scripts.
    
* **Catalog:** The database of all detected tracks (and macro tracks) with metadata, which acts as the index for all artifact files[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-refactor-plan.md#L4-L9).
    
* **Artifact:** Any file produced in the pipeline (raw data, manifests, frame dumps, images). The structured repository organizes these by track.
    

### D. References

_(Citations to internal design documents, code, and discussions as embedded in the text above.)_

[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L5-L12) _Power Tracks Engine – Architecture Draft_ (Engine Goals and Interface map)  
[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L38-L44) _Research Compliance Audit – Regime detection expectations_  
[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/macro-flow.md#L12-L19) _Macro Track Flow – stitching logic and mask drift tolerance_  
[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L30-L38)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L34-L42) _Algo Spec – Detection sliding window and criteria_  
[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L128-L136)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/cursor-rules/04-algorithm-specifications.mdc#L149-L157) _Algo Spec – Frame structure (56-bit layout)_  
[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/packages/core/README.md#L130-L139) _Core README – computing decodability D and regime classification_  
[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/research-audit.md#L2-L5) _Research Audit – Zero synthetic data provenance chain_  
[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/architecture.md#L14-L17) _Architecture Qs – Use Redis Streams for fan-out (queue decision)_  
[GitHub](https://github.com/TheGameStopsNow/power-tracks-engine/blob/ed13d45be9826ba2ed7eb1cf0d7dcbff6f46311d/docs/runbook.md#L10-L18) _Runbook – Prometheus metrics exposed (track detections, reconnects, sink errors)_  
[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/.cursor/rules/02-ui-ux-standards.mdc#L42-L48) _UI Standards – Power Tracks Grid features (clusters, filters, compare)_  
[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/dashboard/components/CompositeForecastChart.tsx#L331-L339)[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/dashboard/components/CompositeForecastChart.tsx#L333-L341) _CompositeForecastChart.tsx – Subway map mode (individual track lines)_  
[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L87-L95) _FastAPI main – Cache key strategy (pt:v1:endpoint:Symbol:Date)_  
[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/api/app/main.py#L707-L715) _SSE stream – snapshot event payload construction_  
[GitHub](https://github.com/TheGameStopsNow/power-tracks-studio/blob/6a828cb5acd73115ac5717671cbfe804c6a830b5/docs/archive/power-track-refactor-plan.md#L4-L9) _Refactor Plan – central catalog and artifact repository definitions_
