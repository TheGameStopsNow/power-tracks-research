# Power Tracks Core Integration Guide

This guide covers integrating the Power Tracks core package and REST API into external applications.

## Table of Contents

1. [NPM Package Integration](#npm-package-integration)
2. [REST API Integration](#rest-api-integration)
3. [Python Client SDK](#python-client-sdk)
4. [End-to-End Examples](#end-to-end-examples)
5. [Troubleshooting](#troubleshooting)

## NPM Package Integration

### Installation

```bash
npm install @powertracks/core
```

### Basic Usage

See [Core Package README](../packages/core/README.md) for detailed usage examples.

### TypeScript Integration

```typescript
import {
  PowerTrackDetector,
  PowerTrackStorage,
  type Tick,
  type PowerTrackCandidate
} from '@powertracks/core';

// Type-safe configuration
const config = {
  fft: {
    window: 60,
    step: 10,
    freqRange: [0.5, 3.0] as [number, number],
    powerThresh: 10000
  },
  roc: {
    threshold: 0.007,
    timeWindow: 5
  }
};

const detector = new PowerTrackDetector(config);
```

### Custom Storage Backend

```typescript
import type { PowerTrackStorageLike } from '@powertracks/core';

class PostgreSQLStorage implements PowerTrackStorageLike {
  async storeCandidate(candidate: PowerTrackCandidate): Promise<void> {
    await db.query(
      'INSERT INTO power_tracks (id, symbol, timestamp, data) VALUES ($1, $2, $3, $4)',
      [candidate.id, candidate.symbol, candidate.timestamp, JSON.stringify(candidate)]
    );
  }
  
  // Implement other methods...
}
```

## REST API Integration

### Authentication

All endpoints (except `/health` and `/metrics`) require API key authentication:

```bash
# Using x-api-key header
curl -H "x-api-key: your-api-key" http://localhost:4020/v1/tracks?symbol=GME

# Using Authorization Bearer
curl -H "Authorization: Bearer your-api-key" http://localhost:4020/v1/tracks?symbol=GME
```

### Base URL

- **Local Development**: `http://localhost:4020`
- **Production**: Configure in your environment

### Common Endpoints

#### List Power Tracks

```bash
GET /v1/tracks?symbol=GME&limit=100&offset=0&date=2024-05-13
```

**Response:**
```json
{
  "symbol": "GME",
  "tracks": [
    {
      "id": "PT-20240513-133000-XXXX",
      "symbol": "GME",
      "timestamp": "2024-05-13T13:30:00Z",
      "spectral_power": 15000,
      "roc_value": 0.008,
      "venue": "OTC",
      "cluster_type": "impactor"
    }
  ],
  "count": 1,
  "offset": 0,
  "generated_at": "2024-05-13T14:00:00Z"
}
```

#### Get Track Price Path

```bash
GET /v1/tracks/path?symbol=GME&trackId=PT-20240513-133000-XXXX&limit=240
```

**Response:**
```json
{
  "track_id": "PT-20240513-133000-XXXX",
  "symbol": "GME",
  "path": [
    {
      "timestamp": "2024-05-13T13:30:00Z",
      "price": 100.50
    }
  ],
  "limit": 240
}
```

#### Get Macro Tracks

```bash
GET /v1/macro?symbol=GME&start=2024-05-01&end=2024-05-31
```

**Response:**
```json
[
  {
    "symbol": "GME",
    "start_date": "2024-05-01",
    "end_date": "2024-05-31",
    "tracks": [...],
    "correlation": 0.85,
    "stitched_count": 5
  }
]
```

### JavaScript/TypeScript Client

```typescript
class PowerTracksClient {
  constructor(private baseUrl: string, private apiKey: string) {}

  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      headers: {
        'x-api-key': this.apiKey,
        'Content-Type': 'application/json',
        ...options?.headers
      }
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }

    return response.json();
  }

  async getTracks(symbol: string, options?: {
    limit?: number;
    offset?: number;
    date?: string;
  }) {
    const params = new URLSearchParams({
      symbol,
      ...(options?.limit && { limit: options.limit.toString() }),
      ...(options?.offset && { offset: options.offset.toString() }),
      ...(options?.date && { date: options.date })
    });

    return this.request(`/v1/tracks?${params}`);
  }

  async getTrackPath(symbol: string, trackId: string, limit = 240) {
    const params = new URLSearchParams({
      symbol,
      trackId,
      limit: limit.toString()
    });

    return this.request(`/v1/tracks/path?${params}`);
  }

  async getMacroTracks(symbol: string, options?: {
    start?: string;
    end?: string;
    lookback?: number;
  }) {
    const params = new URLSearchParams({
      symbol,
      ...(options?.start && { start: options.start }),
      ...(options?.end && { end: options.end }),
      ...(options?.lookback && { lookback: options.lookback.toString() })
    });

    return this.request(`/v1/macro?${params}`);
  }
}

// Usage
const client = new PowerTracksClient('http://localhost:4020', 'your-api-key');
const tracks = await client.getTracks('GME', { limit: 10 });
```

## Python Client SDK

### Installation

```bash
pip install power-tracks-client
```

### Basic Usage

```python
from powertracks import PowerTracksClient

# Initialize client
client = PowerTracksClient(
    base_url='http://localhost:4020',
    api_key='your-api-key'
)

# List tracks
tracks = client.get_tracks(
    symbol='GME',
    limit=100,
    offset=0,
    date='2024-05-13'
)

print(f"Found {tracks['count']} tracks")

# Get track path
path = client.get_track_path(
    symbol='GME',
    track_id='PT-20240513-133000-XXXX',
    limit=240
)

print(f"Path has {len(path['path'])} points")

# Get macro tracks
macros = client.get_macro_tracks(
    symbol='GME',
    start='2024-05-01',
    end='2024-05-31'
)

print(f"Found {len(macros)} macro tracks")
```

### Generated Clients (OpenAPI)

Run the workspace helper to sync the YAML → JSON spec and regenerate both client SDKs:

```bash
npm run openapi:clients
```

- **TypeScript**: `clients/typescript` (`@powertracks/client`) – build with `npm run build --workspace @powertracks/client`.
- **Python**: `clients/python` (`powertracks-client`) – install with `pip install ./clients/python`.

## End-to-End Examples

### Example 1: Real-Time Detection with Custom Storage

```typescript
import { PowerTrackDetector } from '@powertracks/core';
import { PowerTracksClient } from './client';

// Custom storage that syncs to REST API
class APIClientStorage implements PowerTrackStorageLike {
  constructor(private apiClient: PowerTracksClient) {}

  async storeCandidate(candidate: PowerTrackCandidate): Promise<void> {
    // Store locally first, then sync to API
    await this.apiClient.createTrack(candidate);
  }
}

// Setup
const apiClient = new PowerTracksClient('http://localhost:4020', 'api-key');
const storage = new APIClientStorage(apiClient);
const detector = new PowerTrackDetector(config, storage);

// Process ticks from your data source
yourDataFeed.on('tick', (tick) => {
  detector.processTick(tick);
});
```

### Example 2: Batch Analysis with Python

```python
from powertracks import PowerTracksClient
import pandas as pd

client = PowerTracksClient('http://localhost:4020', 'api-key')

# Fetch tracks for analysis
tracks = client.get_tracks('GME', limit=1000)

# Convert to DataFrame
df = pd.DataFrame(tracks['tracks'])

# Analyze
print(f"Total tracks: {len(df)}")
print(f"By cluster type:\n{df['cluster_type'].value_counts()}")
print(f"Average spectral power: {df['spectral_power'].mean()}")

# Get paths for top tracks
top_tracks = df.nlargest(10, 'spectral_power')
for _, track in top_tracks.iterrows():
    path = client.get_track_path('GME', track['id'])
    # Analyze path...
```

### Example 3: Macro Track Correlation Analysis

```typescript
import { PowerTracksClient } from './client';

const client = new PowerTracksClient('http://localhost:4020', 'api-key');

async function analyzeMacroCorrelation(symbol: string) {
  const macros = await client.getMacroTracks(symbol, {
    start: '2024-05-01',
    end: '2024-05-31'
  });

  for (const macro of macros) {
    console.log(`Macro track: ${macro.start_date} to ${macro.end_date}`);
    console.log(`  Tracks: ${macro.stitched_count}`);
    console.log(`  Correlation: ${macro.correlation}`);
    console.log(`  Symbol: ${macro.symbol}`);
  }
}

analyzeMacroCorrelation('GME');
```

## Troubleshooting

### Common Issues

#### Authentication Errors

**Error**: `401 Unauthorized`

**Solution**:
1. Verify API key is correct
2. Check header name (`x-api-key` or `Authorization: Bearer`)
3. Ensure key is not expired (if using token-based auth)

#### Service Unavailable

**Error**: `503 Service Unavailable`

**Solution**:
1. Check if data loader is configured
2. Verify engine daemon is running
3. Check logs for specific error messages

#### CORS Issues (Browser)

**Error**: CORS policy blocks requests

**Solution**:
1. Configure CORS in engine daemon config
2. Use server-side proxy for browser requests
3. Use Python/Node.js client instead of browser fetch

### Debug Mode

Enable verbose logging:

```typescript
// TypeScript/Node.js
process.env.DEBUG = 'powertracks:*';

// Python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### API Versioning

The API uses `/v1/` prefix for versioning. Future versions will use `/v2/`, etc.

## OpenAPI Specification

The complete OpenAPI 3.1 specification is available at:

- **File**: `docs/openapi/power-tracks-engine.yaml`
- **Served**: `http://localhost:4020/openapi.json` (when integrated)

Validate the spec:

```bash
npx @apidevtools/swagger-cli validate docs/openapi/power-tracks-engine.yaml
```

## Next Steps

- See [Core Package README](../packages/core/README.md) for NPM package details
- See [Core Scope Documentation](core-scope.md) for package boundaries
- See [OpenAPI Specification](openapi/power-tracks-engine.yaml) for complete API reference
