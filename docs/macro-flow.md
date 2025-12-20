# Macro Track Flow

This document captures how **macro tracks** are produced by the engine and where they surface for downstream consumers (CLI, API, dashboards).

## 1. Source Data

1. The detector writes raw track artifacts into the fallback data tree (e.g. `${ENGINE_DATA_PATH}/data/power_tracks/<SYMBOL>/<TRACK_ID>/`).
2. Each track directory contains the `lag_manifest.json` plus decoded paths / unfolded price corridors that power the later corridor summaries.

## 2. Stitching Long-Horizon Chains

| Step | Code | Notes |
|------|------|-------|
| Load decoded days | `packages/core/src/macro/macroStitcher.ts` | Reads daily `tracks.jsonl`, groups records by `family`/`version`, and captures the constituent `trackIds`. |
| Validate macro candidates | same | Enforces `minDays`, mask drift tolerance, and assigns `cluster: 'macro'`. |
| Corridor extraction | `services/daemon/src/loaders/filesystemLoader.ts:605` | Replays each segment’s underlying track via `getTrackPricePath`, honouring the track’s declared `horizon_seconds` / `timescale_summary` windows, and builds min/max envelopes plus down-sampled price paths. |

The stitcher returns per-segment metadata (date, frames, mask, source directories, corridor) as well as an aggregate corridor for the entire chain.

## 3. Surfacing the Data

### API (`/v1/macro`)

Defined in `services/daemon/src/server.ts:394`.

- Query parameters: `symbol`, optional `start`, `end`, `lookback`, `min_days`, `mask_drift`.
- Response payload includes:
  - `tracks[]`: stitched macro chains with `cluster: 'macro'`, segments, and full-corridor metadata.
  - `available_dates` / `used_dates` for the diagnostics window.
  - Config echo (minDays, mask drift tolerance, lookback) so dashboards know the window that was evaluated.

### CLI (`pte macro`)

`cli/pte/src/index.ts:206`

- Mirrors the API results locally; optional `--json` output is identical to the REST payload.
- Default `--lookback` is 180 trading days so the CLI captures month-scale chains unless the operator narrows the window.

### Persisted Artifacts

| Location | Description |
|----------|-------------|
| `data/power_tracks/<SYMBOL>/macro_tracks.json` | Written on every `/v1/macro` call for offline dashboards. |
| `powertracks.sqlite` → `power_tracks` table | Chains are inserted with `detection_mode = 'macro_chain'` (see `services/daemon/src/loaders/filesystemLoader.ts:771`), allowing the UI to pull them alongside intraday detections. |

The stored payload contains everything required to render the corridor without having to recompute stitch results.

## 4. UI Integration Points

The Next.js Studio (or any consumer) can surface macro guidance in two ways:

1. **Live view** – call `GET /v1/macro?symbol=GME` and render the returned corridor path (the `tracks[].corridor.path` array is already down-sampled for plotting).
2. **Catalog view** – query SQLite for `SELECT payload FROM power_tracks WHERE detection_mode = 'macro_chain'` to show stitched macro chains next to intraday tracks (payload schema matches the API structure).

In both cases, the UI should highlight:

- The aggregate corridor (full chain) for the directional envelope.
- Per-segment corridors to show how each decoded day contributed.
- Date range and mask drift tolerance used for the run (these are echoed in the response/config block).

## 5. Configuration Knobs

`engine.config.yaml` carries the defaults:

```yaml
macro:
  minDays: 3
  maskDriftTolerance: 1
  defaultLookbackDays: 180
  decodedRoots:
    - "${ENGINE_DATA_PATH}/collection/power_tracks_project/decoded"
    - "${ENGINE_DATA_PATH}/decoded"
```

You can override them via CLI flags (`pte macro --min-days …`) or query parameters (`/v1/macro?min_days=5`), letting power users experiment with sensitivity without redeploying the service.
