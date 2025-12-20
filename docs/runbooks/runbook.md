---
title: Power Tracks Engine Runbook
---

# Monitoring & Operations

## Prometheus Metrics

The daemon publishes Prometheus metrics at `http://<host>:4020/metrics` and the endpoint is public by default (auth bypassed via `server.auth.publicRoutes`). Metrics include:

- `powertracks_http_request_duration_seconds` (histogram): Fastify request latency.
- `powertracks_track_detections_total{symbol,regime}` (counter): Tracks emitted by the detector.
- `powertracks_track_last_detection_timestamp{symbol}` (gauge): Unix timestamp of the most recent detection per symbol.
- `powertracks_sink_errors_total{sink}` (counter): Failed sink writes.
- `powertracks_feed_reconnects_total{reason}` (counter): Polygon websocket reconnects.

Pull metrics into Prometheus and apply alerts such as those in `docs/prometheus-alerts.example.yaml`.

## Alerts

See `docs/prometheus-alerts.example.yaml` for starter rules covering:

- No detections in 30 minutes.
- Feed reconnect storm (>3 reconnects in 5 minutes).
- Sink write failures.

Hook alerts into Alertmanager/PagerDuty and adjust thresholds for production volumes.

## Common Operational Checks

1. **Daemon health**: `curl http://engine:4020/health` (public).
2. **Authentication**: `curl -H "X-API-Key: $ENGINE_API_KEY" http://engine:4020/status`.
3. **Recent tracks**: `curl -H "X-API-Key: $ENGINE_API_KEY" 'http://engine:4020/v1/tracks?symbol=GME&limit=50'`.
4. **Metrics scrape**: `curl http://engine:4020/metrics`.

## Handling Issues

- **No detections, feed connected**: Check `/metrics` counters, inspect Polygon connectivity, verify upstream data (Studio ingest). The `powertracks_feed_reconnects_total` counter indicates replay storms.
- **Sink errors**: `sink_errors_total` increments per sink; correlate with daemon logs.
- **Options snapshot failures**: The engine retries automatically and falls back to cached data; inspect logs for repeated warnings and verify Polygon API status.
- **Live Aggregator**: `/metrics` includes request latencies; use `/status` to ensure `liveAggregator.getStatus()` reports bars for tracked symbols.

## Scaling for Multiple Symbols

- **Shard symbols**: Use `feed.polygon.symbols` and `data.allowlist` to constrain each engine instance to a subset of tickers. Run multiple instances behind load balancing to cover a larger universe.
- **Data partitioning**: Ensure unique SQLite paths per instance (e.g., `SQLITE_PATH=/data/engine-A.sqlite`) or switch to Postgres for shared storage.
- **CPU/memory**: Start with `NODE_OPTIONS=--max-old-space-size=4096` on modern hosts. Detector throughput reference: `npm run --workspace @powertracks/daemon perf:load`.
- **Network**: For high tick rates, deploy close to Polygon POPs and enable the REST fallback cache.
- **Live feeds**: Monitor `powertracks_feed_reconnects_total`; heavy reconnects may indicate the need to split symbol sets or increase Polygon subscription limits.
- **Horizontal workers**: Pair each engine instance with separate ingestion/sink workers (or dedicated Postgres schemas) to prevent contention; coordinate with Studio to ensure each symbol routes to one active engine.
