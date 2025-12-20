# Multi-Symbol Scaling Guide

## Overview

As your symbol universe grows, run multiple instances of the Power Tracks Engine (PTE) so each handles a shard of tickers. This guide outlines a pattern using Docker Compose overrides.

## Sharding Strategy

- **Symbol lists**: assign fixed symbol sets via `feed.polygon.symbols` or env `POLYGON_SYMBOLS` per engine.
- **Data allowlists**: mirror the symbol shard in `data.allowlist` to keep filesystem lookups bounded.
- **Sink separation**: each engine writes to its own SQLite file or to shared Postgres with unique worker IDs.

## Docker Compose Overlay Example

Create `docker-compose.override.yml` in your deployment repo:

```yaml
services:
  engine-a:
    image: power-tracks-engine:latest
    environment:
      - POLYGON_API_KEY=${POLYGON_API_KEY}
      - POLYGON_SYMBOLS=GME,AMC,BBBY
      - SQLITE_PATH=/data/engine-a.sqlite
      - ENGINE_API_KEY=${ENGINE_API_KEY}
    volumes:
      - ./data/engine-a:/data

  engine-b:
    image: power-tracks-engine:latest
    environment:
      - POLYGON_API_KEY=${POLYGON_API_KEY}
      - POLYGON_SYMBOLS=TSLA,NVDA,AAPL
      - SQLITE_PATH=/data/engine-b.sqlite
      - ENGINE_API_KEY=${ENGINE_API_KEY}
    volumes:
      - ./data/engine-b:/data
```

Back your load balancer or Studio backend with awareness of which instance serves which symbols.

## Horizontal Scaling Checklist

1. Define symbol shards and update `POLYGON_SYMBOLS`/`data.allowlist` accordingly.
2. Provision data directories or Postgres schemas per instance.
3. Configure Prometheus scrape targets per engine (`/metrics`).
4. Roll out instances via Compose/Helm; verify `/status` and `/v1/tracks` per shard.
5. Update Studio to query the appropriate engine for each symbol.

## Resources

- Observatory counters: `powertracks_track_detections_total`, `powertracks_feed_reconnects_total` per instance.
- Synthetic throughput: `npm run --workspace @powertracks/daemon perf:load`.
